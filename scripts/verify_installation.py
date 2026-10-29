#!/usr/bin/env python3
"""Offline package acceptance. All config/state is synthetic and temporary.

Optional --codex starts isolated ephemeral sessions, never a model turn or login.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import tempfile
import threading
import time
import tomllib

from agent_librarian.gateway.common import NAMES
from agent_librarian.installation import Installation, SERVER
from agent_librarian.personal.state import PersonalState, write_private
from agent_librarian.personal.brave_transport import CONNECTION
from agent_librarian.projects import ProjectMappings

ROOT = Path(__file__).resolve().parents[1]


class CodexProbe:
    def __init__(self, binary, root, project):
        # A child-process test home is deliberately isolated from the owner's auth,
        # global skills, sessions and Codex settings. No environment credentials.
        env = {k: v for k, v in os.environ.items() if k in ('PATH', 'LANG', 'TMPDIR')}
        env.update(HOME=str(root), CODEX_HOME=str(root/'.codex'))
        self.process = subprocess.Popen([binary, 'app-server', '--stdio'], cwd=project,
            env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.messages = queue.Queue()
        self.errors = []
        def read():
            for line in self.process.stdout:
                try:
                    self.messages.put(json.loads(line))
                except ValueError:
                    pass
        def drain():
            for line in self.process.stderr:
                self.errors.append(line)
        threading.Thread(target=read, daemon=True).start()
        threading.Thread(target=drain, daemon=True).start()
        self.seq = 0

    def request(self, method, params):
        self.seq += 1
        self.process.stdin.write(json.dumps({'id': self.seq, 'method': method, 'params': params})+'\n')
        self.process.stdin.flush()
        deadline = time.monotonic()+45
        while time.monotonic() < deadline:
            try:
                value = self.messages.get(timeout=.5)
            except queue.Empty:
                if self.process.poll() is not None:
                    raise RuntimeError('Codex exited: '+''.join(self.errors)[-1500:])
                continue
            if value.get('id') == self.seq:
                if 'error' in value:
                    raise RuntimeError(f'{method}: {value["error"]}')
                return value['result']
        raise RuntimeError(f'Codex timeout: {method}')

    def close(self):
        self.process.terminate()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill(); self.process.wait(timeout=5)


def codex_probe(binary, root, project, expected):
    probe = CodexProbe(binary, root, project)
    try:
        probe.request('initialize', {'clientInfo': {'name': 'kn05-offline-acceptance', 'version': '1.0'},
                                     'capabilities': {'experimentalApi': True}})
        probe.process.stdin.write('{"method":"initialized"}\n'); probe.process.stdin.flush()
        skills = probe.request('skills/list', {'cwds': [str(project)], 'forceReload': True})
        found = [s for entry in skills['data'] for s in entry['skills'] if s['name'] == 'agent-librarian']
        expected_path = root/'.agents/skills/agent-librarian/SKILL.md'
        assert any(s['enabled'] and str(s['path']) == str(expected_path) for s in found), found
        thread = probe.request('thread/start', {'cwd': str(project), 'ephemeral': True,
            'approvalPolicy': 'never', 'sandbox': 'read-only'})
        thread_id = thread['thread']['id']
        servers = probe.request('mcpServerStatus/list', {'threadId': thread_id, 'serverName': SERVER})
        ours = next(s for s in servers['data'] if s['name'] == SERVER)
        tools = ours['tools']
        # The protocol represents tools as a name->metadata map.
        names = {v.get('name', k) for k, v in tools.items()} if isinstance(tools, dict) else {x['name'] for x in tools}
        assert names == set(NAMES), names
        response = probe.request('mcpServer/tool/call', {'threadId': thread_id, 'server': SERVER,
            'tool': NAMES[0], 'arguments': {}})
        value = response.get('structuredContent')
        if not value:
            value = json.loads(response['content'][0]['text'])
        if expected is None:
            assert value.get('code') == 'PROJECT_NOT_MAPPED', value
        else:
            assert value.get('project') == str(project), value
            assert [b['notebook_id'] for b in value['notebooks']] == [expected], value
        return {'skill_discovered': True, 'four_tools_initialized': True,
                'mapped_notebook': expected, 'mapping_checked_via_codex_mcp': True,
                'prepared_read_only_operation': {'tool': NAMES[1], 'arguments': {'notebook_id': expected}} if expected else None,
                'model_turns': 0, 'google_operations': 0}
    finally:
        probe.close()



def generic_probe(interpreter, root, projects, state):
    """Exercise the packaged neutral contract with no IDE/client configuration."""
    import anyio
    from mcp import Client, StdioServerParameters
    home = root/'generic-home'
    def cli(project, action, *extra):
        result = subprocess.run([interpreter, '-I', '-B', '-m', 'agent_librarian', 'setup', action,
            '--project', str(project), '--home', str(home), '--state-dir', str(state.path), *extra],
            capture_output=True, text=True, check=True, timeout=10)
        return json.loads(result.stdout)
    contract = cli(projects[0], 'contract')
    assert contract['transport'] == 'stdio' and contract['tools'] == list(NAMES)
    assert Path(contract['skill_source']).is_file()
    assert not home.exists()
    assert cli(projects[0], 'onboard')['status'] == 'CHOICE_REQUIRED'
    assert cli(projects[0], 'onboard', '--choice', 'skip')['status'] == 'SKIPPED'
    assert not home.exists()
    selection = cli(projects[0], 'onboard', '--choice', 'existing')
    assert selection['status'] == 'NOTEBOOK_SELECTION_REQUIRED'
    assert not home.exists(), 'inventory listing must not select or install'
    mapped = cli(projects[0], 'onboard', '--choice', 'existing', '--approve',
                 '--account-id', selection['account_id'], '--notebook-id', 'notebook-second')
    assert mapped['mapping_verified'] and mapped['notebook_id'] == 'notebook-second'
    assert cli(projects[0], 'onboard')['reused']
    async def run():
        for project, expected in ((projects[0], 'notebook-second'), (projects[2], None)):
            descriptor = cli(project, 'contract')
            async with Client(StdioServerParameters(command=descriptor['command'], args=descriptor['args'])) as client:
                assert {tool.name for tool in (await client.list_tools()).tools} == set(NAMES)
                value = (await client.call_tool(NAMES[0], {})).structured_content
                if expected:
                    assert value['project'] == str(project)
                    assert [book['notebook_id'] for book in value['notebooks']] == [expected]
                else:
                    assert value['code'] == 'PROJECT_NOT_MAPPED'
    anyio.run(run)
    return {'neutral_contract': True, 'no_agent_registration_required': True,
            'explicit_owner_selection_verified': True, 'skip_without_changes': True,
            'packaged_sdk_stdio_four_tools': True, 'unmapped_denied': True,
            'google_operations': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheel', required=True)
    parser.add_argument('--codex', help='Optional path to the installed Codex executable')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    wheel = Path(args.wheel).resolve()
    (ROOT/'state').mkdir(exist_ok=True)
    report = {'milestone': 'API_SOURCE_INGESTION_AND_LARGE_NOTEBOOK', 'wheel_sha256': hashlib.sha256(wheel.read_bytes()).hexdigest(),
              'google_operations': 0, 'live_research_queries': 0, 'credentials': 'SYNTHETIC_METADATA_ONLY',
              'owner_configuration_changed': False}
    with tempfile.TemporaryDirectory(prefix='kn05-', dir=ROOT/'state') as temporary:
        root = Path(temporary).resolve()
        projects = [root/n for n in ('project-a', 'project-b', 'unmapped')]
        for project in projects:
            project.mkdir()
            subprocess.run(['git', 'init', '-q', str(project)], check=True, capture_output=True)
        install = Installation(root/'installation', root/'.codex', root/'.agents/skills', root/'personal')
        install.config.parent.mkdir()
        unrelated = '# Owner settings remain intact\n[features]\nshell_tool = false\n'
        install.config.write_text(unrelated)
        first = install.install(wheel=wheel)
        assert first['status'] == 'INSTALLED'
        interpreter = first['runtime']
        assert install.install(wheel=wheel)['status'] == 'UNCHANGED'
        report['clean_packaged_runtime_install'] = True
        report['repeat_install_without_duplicates'] = True
        # The wheel is usable outside the checkout and contains the portable Skill.
        result = subprocess.run([interpreter, '-I', '-B', '-m', 'agent_librarian', '--help'],
                                cwd=projects[0], capture_output=True, text=True, check=True)
        assert 'setup' in result.stdout
        assert 'sources' in result.stdout
        source = root/'synthetic-upload.md'
        source.write_bytes(b'# Synthetic source\nExact local bytes.\n')
        before = source.read_bytes()
        preview = subprocess.run([interpreter, '-I', '-B', '-m', 'agent_librarian',
            'sources', 'add', '--project', str(projects[0]), '--notebook-id', 'notebook-approved',
            '--path', str(source)], cwd=projects[0], capture_output=True, text=True, check=True)
        preview = json.loads(preview.stdout)
        assert preview['status'] == 'PREVIEW' and preview['network_operations'] == 0
        assert preview['plan']['entries'][0]['sha256'] == hashlib.sha256(before).hexdigest()
        assert source.read_bytes() == before and not install.state_dir.exists()
        resource_probe = r'''
from pathlib import Path
from agent_librarian.personal import source_admin
from agent_librarian.providers.gemini import parse_source
folder=Path(source_admin.__file__).parent
assert all((folder/name).is_file() for name in ('brave_upload.js','wire.js','brave_rpc.js'))
content='Synthetic passage. '*2000
raw=[[['source-test'],'Title'],None,None,[[[0,len(content),content]]]]
assert parse_source(raw,'source-test')['content']==content
'''
        subprocess.run([interpreter, '-I', '-B', '-c', resource_probe], cwd=projects[0],
                       capture_output=True, text=True, check=True)
        report['packaged_ingestion_preview_without_authentication'] = True
        report['packaged_upload_and_wire_javascript_resources'] = True
        report['packaged_large_source_decoder'] = True
        state = PersonalState(install.state_dir, create=True)
        config = state.load(); config.update(authenticated=True, host='notebook.google.com'); state.save(config)
        write_private(state.path/'notebooks.json', {'account_id': config['account_id'], 'notebooks': [
            {'notebook_id': nb, 'title': 'Synthetic '+nb, 'sources': [{'id': source, 'title': 'Synthetic source'}]}
            for nb, source in [('notebook-approved', 'source-approved'), ('notebook-second', 'source-second')]]})
        write_private(state.path/CONNECTION, {'status': 'BROWSER_DISCOVERY_VERIFIED', 'account_id': config['account_id'],
            'origin': 'https://notebook.google.com', 'window_id': '1', 'tab_id': '2'})
        report['generic_package_acceptance'] = generic_probe(interpreter, root, projects, state)
        maps = ProjectMappings(install.home)
        maps.change(projects[0], ['notebook-approved']); maps.change(projects[1], ['notebook-second'])
        assert install.status(projects[0])['status'] == 'HEALTHY_OFFLINE'
        assert install.status(projects[2])['status'] == 'NEEDS_ATTENTION'
        report['doctor_healthy_and_unhealthy'] = True
        before = state.config_path.read_bytes()
        (install.skill_dir/'SKILL.md').unlink()
        install.config.write_text(unrelated)
        assert install.status(projects[0])['status'] == 'NEEDS_ATTENTION'
        install.install(repair=True)
        assert install.status(projects[0])['status'] == 'HEALTHY_OFFLINE'
        assert before == state.config_path.read_bytes()
        report['repair_preserved_authentication_metadata'] = True
        # Invoke the installed launcher in a fresh process from each new project.
        for project, nb in zip(projects[:2], ['notebook-approved', 'notebook-second']):
            result = subprocess.run([str(install.launcher), 'setup', 'status', '--project', str(project),
                '--home', str(install.home), '--codex-home', str(install.config.parent),
                '--skills-home', str(install.skill_dir.parent), '--state-dir', str(state.path)],
                cwd=project, capture_output=True, text=True, check=True)
            assert json.loads(result.stdout)['mapping']['notebook_ids'] == [nb]
        report['fresh_cli_two_project_selection'] = True
        if args.codex:
            report['codex_version'] = subprocess.check_output([args.codex, '--version'], text=True).strip()
            report['fresh_codex_sessions'] = [codex_probe(args.codex, root, project, nb)
                for project, nb in zip(projects, ['notebook-approved', 'notebook-second', None])]
        else:
            report['fresh_codex_sessions'] = 'NOT_REQUESTED'
        # Preview then uninstall; a second invocation is harmless.
        assert install.uninstall(True)['status'] == 'PREVIEW'
        install.uninstall()
        assert not Path(interpreter).exists(), 'installer-owned unmodified runtime must be removed'
        assert tomllib.loads(install.config.read_text()) == tomllib.loads(unrelated)
        assert state.config_path.read_bytes() == before and maps.path.exists()
        assert install.uninstall()['status'] == 'UNCHANGED'
        report['uninstall_only_owned_components'] = True
        # An owner-added runtime file must survive uninstall, never be swept away.
        install.install(wheel=wheel)
        note = Path(interpreter).parent/'owner-note.txt'
        note.write_text('Synthetic owner file; retain this runtime.')
        outcome = install.uninstall()
        assert note.exists() and outcome['retained_runtime_paths']
        report['modified_managed_runtime_preserved'] = True
    report['result'] = 'PASS'
    Path(args.output).write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
