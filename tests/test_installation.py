"""KN-OSS-05 lifecycle and per-project acceptance, synthetic identifiers only."""
from dataclasses import replace
import io
from contextlib import redirect_stderr
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch
from agent_librarian.gateway.common import NAMES, Rejected
from agent_librarian.installation import Installation, SERVER, patch as patch_toml
from agent_librarian.personal.state import PersonalState, write_private
from agent_librarian.personal.brave_transport import CONNECTION
from agent_librarian.personal.runtime import prepare
from agent_librarian.projects import ProjectMappings
from agent_librarian.project_runtime import ProjectGateway
from tests.http_fakes import MemoryStore, ReplayHTTP, session

ROOT = Path(__file__).resolve().parents[1]


class InstallationTests(unittest.TestCase):
    def setUp(self):
        (ROOT/'state').mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='install-', dir=ROOT/'state')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.a, self.b, self.c = [self.root/n for n in ('project-a', 'project-b', 'unmapped')]
        for p in (self.a, self.b, self.c):
            p.mkdir()
        self.install = Installation(self.root/'installation', self.root/'codex', self.root/'skills', self.root/'personal')
        self.maps = ProjectMappings(self.install.home)
        self.unrelated = '# Keep this comment\nmodel = "synthetic-model"\n[mcp_servers.other]\ncommand = "another-tool"\n'
        self.install.config.parent.mkdir()
        self.install.config.write_text(self.unrelated)

    def error(self, code, callback):
        with self.assertRaises(Rejected) as error:
            callback()
        self.assertTrue(error.exception.code.startswith(code), error.exception.code)

    def cli(self, action, *extra):
        return subprocess.run([sys.executable, '-I', '-B', '-m', 'agent_librarian', 'setup', action,
            '--home', str(self.install.home), '--codex-home', str(self.install.config.parent),
            '--skills-home', str(self.install.skill_dir.parent), '--state-dir', str(self.install.state_dir),
            '--project', str(self.a), *extra], capture_output=True, text=True, timeout=25)

    def synthetic_state(self):
        state = PersonalState(self.install.state_dir, create=True)
        config = state.load()
        config['authenticated'] = True
        config['host'] = 'notebook.google.com'
        # Leave the historical global selection unset: mappings must be sufficient.
        state.save(config)
        write_private(state.path/'notebooks.json', {'account_id': config['account_id'], 'notebooks': [
            {'notebook_id': 'notebook-approved', 'title': 'Project A', 'sources': [{'id': 'source-approved', 'title': 'A'}]},
            {'notebook_id': 'notebook-second', 'title': 'Project B', 'sources': [{'id': 'source-second', 'title': 'B'}]}]})
        write_private(state.path/CONNECTION, {'status': 'BROWSER_DISCOVERY_VERIFIED',
            'account_id': config['account_id'], 'origin': 'https://notebook.google.com', 'window_id': '1', 'tab_id': '2'})
        return state

    def test_clean_install_repeat_preserves_other_tools_and_projects(self):
        before = {p: list(p.iterdir()) for p in (self.a, self.b)}
        first = self.install.install(runtime_python=sys.executable)
        raw = self.install.config.read_bytes()
        receipt = self.install.receipt_path.read_bytes()
        second = self.install.install()
        self.assertEqual(first['status'], 'INSTALLED')
        self.assertEqual(second['status'], 'UNCHANGED')
        self.assertEqual(raw, self.install.config.read_bytes())
        self.assertEqual(receipt, self.install.receipt_path.read_bytes())
        self.assertEqual(self.install.config.read_text().count(f'[mcp_servers.{SERVER}]'), 1)
        self.assertTrue(self.install.config.read_text().startswith(self.unrelated))
        self.assertEqual(before, {p: list(p.iterdir()) for p in before})
        backups = list((self.install.home/'backups').glob('*config.toml'))
        self.assertEqual(backups[0].read_text(), self.unrelated)

    def test_install_preview_writes_nothing(self):
        before = set(self.root.rglob('*'))
        result = self.install.install(runtime_python=sys.executable, dry_run=True)
        self.assertEqual(result['status'], 'PREVIEW')
        self.assertEqual(before, set(self.root.rglob('*')))

    def test_two_projects_distinct_maps_and_no_default(self):
        self.maps.change(self.a, ['notebook-approved'])
        self.maps.change(self.b, ['notebook-second'])
        self.assertEqual(self.maps.resolve(self.a)['notebook_ids'], ['notebook-approved'])
        self.assertEqual(self.maps.resolve(self.b)['notebook_ids'], ['notebook-second'])
        self.assertEqual(self.maps.resolve(self.c)['status'], 'PROJECT_NOT_MAPPED')
        self.assertEqual(self.maps.change(self.a, ['notebook-approved'])['changed'], False)
        self.assertEqual(list(self.a.iterdir()), [])
        self.assertNotIn('credential', self.maps.path.read_text())

    def test_nearest_ancestor_and_exact_unmap(self):
        child = self.a/'child'; child.mkdir()
        self.maps.change(self.a, ['notebook-approved'])
        self.assertEqual(self.maps.resolve(child)['mapping_project'], str(self.a))
        self.maps.change(child, ['notebook-second'])
        self.assertEqual(self.maps.resolve(child)['notebook_ids'], ['notebook-second'])
        self.maps.change(child)
        self.assertEqual(self.maps.resolve(child)['notebook_ids'], ['notebook-approved'])
        self.maps.change(self.a)
        self.assertEqual(self.maps.resolve(child)['status'], 'PROJECT_NOT_MAPPED')

    def test_mapping_replacement_unmap_and_previews(self):
        result = self.maps.change(self.a, ['notebook-approved'], dry_run=True)
        self.assertTrue(result['changed']); self.assertFalse(self.install.home.exists())
        self.maps.change(self.a, ['notebook-approved', 'notebook-second'])
        self.maps.change(self.a, ['notebook-second'])
        self.assertEqual(self.maps.resolve(self.a)['notebook_ids'], ['notebook-second'])
        self.assertTrue(self.maps.change(self.a, dry_run=True)['changed'])
        self.assertEqual(self.maps.resolve(self.a)['status'], 'MAPPED')
        self.maps.change(self.a)
        self.assertFalse(self.maps.change(self.a)['changed'])

    def test_mapping_invalid_ids_and_secret_fields_rejected(self):
        self.error('INVALID_ARGUMENTS', lambda: self.maps.change(self.a, ['../foreign']))
        self.maps.change(self.a, ['notebook-approved'])
        value = self.maps.load(); value['projects'][str(self.a)]['token'] = 'SYNTHETIC'
        write_private(self.maps.path, value)
        self.error('PROJECT_MAPPING_INVALID', lambda: self.maps.resolve(self.a))

    def test_missing_mapping_and_foreign_notebook_fail_before_auth(self):
        gateway = ProjectGateway(self.a, self.install.home, self.install.state_dir)
        with patch('agent_librarian.project_runtime.PersonalState', side_effect=AssertionError('No authentication access')):
            self.assertEqual(gateway.call(NAMES[0], {})['code'], 'PROJECT_NOT_MAPPED')
            self.maps.change(self.a, ['notebook-approved'])
            self.assertEqual(gateway.call(NAMES[1], {'notebook_id': 'notebook-second'})['code'], 'NOTEBOOK_NOT_ALLOWED')
            self.assertEqual(gateway.call('source_delete', {})['code'], 'FORBIDDEN_OPERATION')

    def test_running_gateway_observes_map_change_without_reinstall(self):
        state = self.synthetic_state()
        before = state.config_path.read_bytes()
        gateway = ProjectGateway(self.a, self.install.home, self.install.state_dir)
        self.maps.change(self.a, ['notebook-approved'])
        with patch('agent_librarian.personal.runtime.PersonalKeychainStore', side_effect=AssertionError('No Keychain')):
            self.assertEqual(gateway.call(NAMES[0], {})['notebooks'][0]['notebook_id'], 'notebook-approved')
            self.maps.change(self.a, ['notebook-second'])
            self.assertEqual(gateway.call(NAMES[0], {})['notebooks'][0]['notebook_id'], 'notebook-second')
            self.maps.change(self.a)
            self.assertEqual(gateway.call(NAMES[0], {})['code'], 'PROJECT_NOT_MAPPED')
        self.assertEqual(before, state.config_path.read_bytes())

    def test_multi_notebook_prepare_does_not_change_global_selection_or_policy(self):
        state = self.synthetic_state()
        # Test the retained native adapter using a synthetic page, never Apple Events.
        from tests.test_brave_transport import FakePage
        from agent_librarian.personal.brave_transport import BraveTransport
        saved = replace(session(), account_id=state.load()['account_id'], host='notebook.google.com')
        page = FakePage(); store = MemoryStore(saved)
        factory = lambda connection, account, email, books, **kw: BraveTransport(connection, account, email, books, runner=page, **kw)
        before = state.config_path.read_bytes()
        with patch('agent_librarian.personal.brave_transport.BraveTransport', side_effect=factory):
            policy, provider = prepare(state, store, notebook_ids=['notebook-approved', 'notebook-second'])
            self.assertEqual(set(policy['notebooks']), {'notebook-approved', 'notebook-second'})
            self.assertEqual(len(provider.list_notebooks()['data']['notebooks']), 2)
            from agent_librarian.gateway.policy import Gateway
            gateway = Gateway(policy, None, state.path, provider=provider)
            with redirect_stderr(io.StringIO()):
                result = gateway.call(NAMES[1], {'notebook_id': 'notebook-approved'})
            self.assertEqual(result['status'], 'OK', result)
            provider.close()
        self.assertEqual(before, state.config_path.read_bytes())
        self.assertFalse((state.path/'research-policy.json').exists())

    def test_doctor_healthy_and_unhealthy_no_live_access(self):
        self.install.install(runtime_python=sys.executable)
        self.maps.change(self.a, ['notebook-approved'])
        self.synthetic_state()
        with patch('subprocess.run', wraps=subprocess.run) as run:
            result = self.install.status(self.a)
            self.assertEqual(result['status'], 'HEALTHY_OFFLINE', result)
            self.assertEqual(len(run.call_args_list), 1) # isolated runtime import probe only
        (self.install.skill_dir/'SKILL.md').unlink()
        self.assertEqual(self.install.status(self.a)['status'], 'NEEDS_ATTENTION')
        self.assertEqual(self.cli('doctor').returncode, 2)

    def test_repair_missing_and_modified_files_preserves_auth_and_unrelated(self):
        self.install.install(runtime_python=sys.executable)
        self.maps.change(self.a, ['notebook-approved'])
        state = self.synthetic_state()
        before = {p: p.read_bytes() for p in state.path.iterdir()}
        (self.install.skill_dir/'SKILL.md').write_text('Damaged synthetic Skill')
        self.install.config.write_text(self.unrelated)
        preview = self.install.install(repair=True, dry_run=True)
        self.assertEqual(preview['status'], 'PREVIEW')
        self.assertEqual(self.install.config.read_text(), self.unrelated)
        self.install.install(repair=True)
        self.assertEqual(self.install.status(self.a)['status'], 'HEALTHY_OFFLINE')
        self.assertTrue(self.install.config.read_text().startswith(self.unrelated))
        self.assertEqual(before, {p: p.read_bytes() for p in state.path.iterdir()})

    def test_uninstall_only_owned_files_and_repeat(self):
        self.install.install(runtime_python=sys.executable)
        self.maps.change(self.a, ['notebook-approved'])
        state = self.synthetic_state()
        before = state.config_path.read_bytes()
        extra = self.install.skill_dir/'owner-notes.txt'; extra.write_text('Keep')
        preview = self.install.uninstall(dry_run=True)
        self.assertEqual(preview['status'], 'PREVIEW'); self.assertTrue(self.install.receipt_path.exists())
        self.install.uninstall()
        self.assertEqual(tomllib.loads(self.install.config.read_text()), tomllib.loads(self.unrelated))
        self.assertEqual(extra.read_text(), 'Keep')
        self.assertEqual(state.config_path.read_bytes(), before)
        self.assertTrue(self.maps.path.exists()); self.assertTrue(Path(sys.executable).exists())
        self.assertEqual(self.install.uninstall()['status'], 'UNCHANGED')

    def test_uninstall_refuses_modified_owned_component(self):
        self.install.install(runtime_python=sys.executable)
        (self.install.skill_dir/'SKILL.md').write_text('Owner edit')
        self.error('OWNED_SKILL_CHANGED', self.install.uninstall)
        self.assertTrue(self.install.receipt_path.exists())
        self.assertIn(SERVER, self.install.config.read_text())

    def test_existing_config_requires_explicit_migration_and_backup(self):
        legacy = self.unrelated + f'\n[mcp_servers.{SERVER}]\ncommand = "legacy-runtime"\n'
        self.install.config.write_text(legacy)
        self.error('MCP_ENTRY_EXISTS', self.install.install)
        self.install.install(runtime_python=sys.executable, adopt_existing=True, dry_run=True)
        self.assertEqual(self.install.config.read_text(), legacy)
        self.install.install(runtime_python=sys.executable, adopt_existing=True)
        self.assertIn(legacy, [p.read_text() for p in (self.install.home/'backups').glob('*config.toml')])

    def test_invalid_toml_and_symlinks_rejected_without_modification(self):
        self.install.config.write_text('broken = [')
        self.error('CODEX_TOML_INVALID', self.install.install)
        self.assertEqual(self.install.config.read_text(), 'broken = [')
        self.install.config.unlink(); self.install.config.symlink_to(self.root/'elsewhere')
        self.error('INSTALL_PATH_SYMLINK_OR_TRAVERSAL', lambda: Installation(self.install.home, self.install.config.parent, self.install.skill_dir.parent))

    def test_inline_or_nested_toml_not_silently_rewritten(self):
        for text in (f'mcp_servers = {{ {SERVER} = {{command="x"}} }}\n',
                     f'[mcp_servers.{SERVER}]\ncommand="x"\n[mcp_servers.{SERVER}.env]\nA="b"\n'):
            self.error('CODEX_TABLE_LAYOUT_UNSUPPORTED', lambda: patch_toml(text, ''))

    def test_fresh_cli_discovers_persistent_skill_map_and_server(self):
        self.assertEqual(self.cli('install', '--runtime-python', sys.executable).returncode, 0)
        self.assertEqual(self.cli('map', '--notebook-id', 'notebook-approved').returncode, 0)
        self.synthetic_state()
        result = self.cli('doctor')
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data['mapping']['notebook_ids'], ['notebook-approved'])
        self.assertTrue(data['user_authentication_record_present'])
        self.assertEqual(data['network_operations'], 0)
        record = json.loads((self.install.skill_dir/'installation.json').read_text())
        self.assertEqual(record['mcp_server'], SERVER)
        self.assertIn('--provider', self.install.config.read_text())

    def test_mcp_initializes_from_project_cwd_with_no_auth_or_mapping(self):
        import anyio
        from mcp import Client, StdioServerParameters
        self.install.install(runtime_python=sys.executable)
        config = tomllib.loads(self.install.config.read_text())['mcp_servers'][SERVER]
        async def run():
            parameters = StdioServerParameters(command=config['command'], args=config['args'], cwd=str(self.c))
            async with Client(parameters) as client:
                self.assertEqual({t.name for t in (await client.list_tools()).tools}, set(NAMES))
                data = (await client.call_tool(NAMES[0], {})).structured_content
                self.assertEqual(data['code'], 'PROJECT_NOT_MAPPED')
        anyio.run(run)

    def test_fresh_mcp_each_project_uses_one_shared_registration(self):
        import anyio
        from mcp import Client, StdioServerParameters
        self.install.install(runtime_python=sys.executable)
        self.synthetic_state()
        self.maps.change(self.a, ['notebook-approved'])
        self.maps.change(self.b, ['notebook-second'])
        config = tomllib.loads(self.install.config.read_text())['mcp_servers'][SERVER]
        raw = self.install.config.read_bytes()
        async def run():
            for project, notebook in ((self.a, 'notebook-approved'), (self.b, 'notebook-second')):
                async with Client(StdioServerParameters(command=config['command'], args=config['args'], cwd=str(project))) as client:
                    self.assertEqual(len((await client.list_tools()).tools), 4)
                    result = (await client.call_tool(NAMES[0], {})).structured_content
                    self.assertEqual(result['project'], str(project))
                    self.assertEqual([b['notebook_id'] for b in result['notebooks']], [notebook])
                    foreign = 'notebook-second' if notebook == 'notebook-approved' else 'notebook-approved'
                    denied = (await client.call_tool(NAMES[1], {'notebook_id': foreign})).structured_content
                    self.assertEqual(denied['code'], 'NOTEBOOK_NOT_ALLOWED')
        anyio.run(run)
        self.assertEqual(raw, self.install.config.read_bytes())

    def test_project_query_permit_does_not_require_or_change_pilot_selection(self):
        state = self.synthetic_state()
        self.maps.change(self.a, ['notebook-approved'])
        self.error('QUERY_HISTORY_ACK_REQUIRED', lambda: state.approve_query('Synthetic question', False, 'notebook-approved'))
        state.approve_query('Synthetic question', True, 'notebook-approved')
        self.assertIsNone(state.load()['selected_notebook'])
        state.consume_query('notebook-approved', 'Synthetic question')
        self.error('PERSONAL_QUERY_APPROVAL_REQUIRED', lambda: state.consume_query('notebook-approved', 'Synthetic question'))

    def test_update_requires_concrete_target_and_preserves_healthy_install(self):
        self.install.install(runtime_python=sys.executable)
        self.maps.change(self.a, ['notebook-approved'])
        self.synthetic_state()
        before = self.install.config.read_bytes()
        result = self.cli('update')
        self.assertEqual(result.returncode, 2)
        self.assertIn('UPDATE_TARGET_REQUIRED', result.stderr)
        result = self.cli('update', '--runtime-python', sys.executable)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(before, self.install.config.read_bytes())
        self.assertEqual(self.install.status(self.a)['status'], 'HEALTHY_OFFLINE')

    def test_invalid_replacement_runtime_does_not_replace_working_registration(self):
        self.install.install(runtime_python=sys.executable)
        before = self.install.config.read_bytes()
        skill = (self.install.skill_dir/'SKILL.md').read_bytes()
        self.error('RUNTIME_INVALID', lambda: self.install.install(runtime_python='/nonexistent/synthetic-python', repair=True))
        self.assertEqual(before, self.install.config.read_bytes())
        self.assertEqual(skill, (self.install.skill_dir/'SKILL.md').read_bytes())

    def test_doctor_malformed_personal_metadata_remains_actionable(self):
        self.install.install(runtime_python=sys.executable)
        self.maps.change(self.a, ['notebook-approved'])
        state = self.synthetic_state()
        state.config_path.write_text('{"invalid":true}')
        result = self.cli('doctor')
        self.assertEqual(result.returncode, 2)
        data = json.loads(result.stdout)
        self.assertEqual(data['status'], 'NEEDS_ATTENTION')
        self.assertTrue(any(c['check'] == 'personal_configuration' and c['action'] for c in data['checks']))

    def test_running_gateway_rejects_concurrent_dispatch(self):
        gateway = ProjectGateway(self.a, self.install.home, self.install.state_dir)
        gateway.busy.acquire()
        try:
            self.assertEqual(gateway.call(NAMES[0], {})['code'], 'BUSY')
        finally:
            gateway.busy.release()
        gateway.close()
        self.assertEqual(gateway.call(NAMES[0], {})['code'], 'SERVICE_DISABLED')

    def test_fresh_project_cli_prepares_exact_question_without_live_request(self):
        state = self.synthetic_state()
        self.maps.change(self.a, ['notebook-approved'])
        result = subprocess.run([sys.executable, '-I', '-B', '-m', 'agent_librarian', 'research', 'approve',
            '--state-dir', str(state.path), '--project', str(self.a), '--installation-home', str(self.install.home),
            '--notebook-id', 'notebook-approved', '--question', 'Synthetic preparation only', '--ack-history'],
            capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'], 'APPROVED_ONE_QUERY')
        self.assertIsNone(state.load()['selected_notebook'])
        self.assertEqual(state.load()['query_permit']['state'], 'APPROVED')
