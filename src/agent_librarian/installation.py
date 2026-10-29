"""Receipt-based user installation. No project writes or authentication access."""
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import sys
import tempfile
import tomllib
from .gateway.common import NAMES, Rejected
from .personal.state import private_dir, read_private, write_private
from .projects import DEFAULT_HOME, ProjectMappings

SERVER = 'agent_librarian_personal'
HEADER = f'[mcp_servers.{SERVER}]'
SKILL = Path(__file__).with_name('skill') / 'SKILL.md'


def safe(path):
    p = Path(path).expanduser().absolute()
    if '..' in p.parts or any(x.is_symlink() for x in (p, *p.parents)):
        raise Rejected('INSTALL_PATH_SYMLINK_OR_TRAVERSAL: choose a regular user-local target')
    return p


def digest(data):
    return hashlib.sha256(data).hexdigest()


def runtime_fingerprint(root):
    records = {}
    for path in sorted(Path(root).rglob('*')):
        if '__pycache__' in path.parts:
            continue
        name = str(path.relative_to(root))
        if path.is_symlink():
            records[name] = 'link:' + os.readlink(path)
        elif path.is_file():
            records[name] = digest(path.read_bytes())
    return digest(json.dumps(records, sort_keys=True).encode())


def atomic(path, data):
    path = safe(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.librarian-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def probe(python):
    try:
        result = subprocess.run([str(python), '-I', '-B', '-c',
            "import json; from importlib.metadata import version; from agent_librarian.project_runtime import ProjectGateway; "
            "from agent_librarian.installation import SKILL; from agent_librarian.gateway.common import NAMES; "
            "import agent_librarian; assert agent_librarian.__version__ == version('agent-librarian-mcp'); "
            "print(json.dumps({'version':version('agent-librarian-mcp'),'tools':list(NAMES),'skill':SKILL.read_text()}))"],
            capture_output=True, text=True, timeout=20)
        if result.returncode:
            raise ValueError()
        data = json.loads(result.stdout)
        if data['tools'] != list(NAMES) or not data['skill'].startswith('---\nname: agent-librarian\n'):
            raise ValueError()
        return data
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
        raise Rejected('RUNTIME_INVALID: install a KN-OSS-05 wheel or supply a compatible --runtime-python') from None


def section(text):
    """Only edit our explicit table; TOML inline/quoted variants fail closed."""
    try:
        parsed = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        raise Rejected('CODEX_TOML_INVALID: fix TOML syntax before setup') from None
    current = parsed.get('mcp_servers', {}).get(SERVER)
    lines = text.splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines) if line.strip().split('#', 1)[0].strip() == HEADER]
    if current is not None and len(starts) != 1:
        raise Rejected('CODEX_TABLE_LAYOUT_UNSUPPORTED: use an explicit Agent Librarian table')
    if not starts:
        return parsed, None, None, ''
    start = starts[0]
    end = next((i for i in range(start + 1, len(lines)) if lines[i].lstrip().startswith('[')), len(lines))
    # Nested tables for this entry are deliberately not rewritten implicitly.
    if end < len(lines) and lines[end].strip().startswith(f'[mcp_servers.{SERVER}.'):
        raise Rejected('CODEX_TABLE_LAYOUT_UNSUPPORTED: review nested Agent Librarian settings')
    return parsed, start, end, ''.join(lines[start:end])


def patch(text, block):
    before, start, end, _ = section(text)
    lines = text.splitlines(keepends=True)
    if start is None:
        result = text + ('\n' if text and not text.endswith('\n\n') else '') + block
    else:
        result = ''.join(lines[:start]) + block + ''.join(lines[end:])
    after = tomllib.loads(result)
    for data in (before, after):
        servers = data.get('mcp_servers', {})
        servers.pop(SERVER, None)
        if not servers:
            data.pop('mcp_servers', None)
    if before != after:
        raise Rejected('UNRELATED_CODEX_CONFIGURATION_CHANGE_REJECTED')
    return result


class Installation:
    def __init__(self, home=DEFAULT_HOME, codex_home=None, skills_home=None, state_dir=None):
        from .personal.state import DEFAULT_STATE
        self.home = safe(home)
        self.config = safe(Path(codex_home or os.environ.get('CODEX_HOME', Path.home()/'.codex')) / 'config.toml')
        self.skill_dir = safe(Path(skills_home or Path.home()/'.agents/skills') / 'agent-librarian')
        self.state_dir = safe(state_dir or DEFAULT_STATE)
        self.receipt_path = self.home / 'installation.json'
        self.launcher = safe(self.home / 'bin/librarian')

    @contextmanager
    def lock(self):
        private_dir(self.home, create=True)
        fd = os.open(self.home / 'installation.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    def receipt(self):
        if not self.receipt_path.exists():
            return None
        data = read_private(self.receipt_path)
        if (data.get('schema_version') != 1 or data.get('owner') != 'agent-librarian-mcp'
                or data.get('config') != str(self.config) or data.get('skill_dir') != str(self.skill_dir)
                or set(data.get('files', {})) != {'SKILL.md', 'installation.json'}
                or not isinstance(data.get('runtimes'), dict)):
            raise Rejected('INSTALL_RECEIPT_TARGET_MISMATCH: reuse the original installation targets')
        return data

    def block(self, python):
        args = ['-I', '-B', '-m', 'agent_librarian', 'mcp-serve', '--provider', 'project',
                '--installation-home', str(self.home), '--state-dir', str(self.state_dir)]
        return (HEADER + '\ncommand = ' + json.dumps(str(python)) + '\nargs = ' + json.dumps(args) +
                '\nenabled = true\nenabled_tools = ' + json.dumps(list(NAMES)) +
                '\nstartup_timeout_sec = 15\ntool_timeout_sec = 45\n\n')

    def backup(self, path):
        if not path.exists():
            return
        private_dir(self.home/'backups', create=True)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        atomic(self.home/'backups'/f'{stamp}-{path.name}', path.read_bytes())

    def runtime(self, wheel, python, dry_run):
        if not wheel:
            return str(Path(python or sys.executable).absolute()), None
        wheel = safe(wheel)
        if not wheel.is_file() or wheel.suffix != '.whl':
            raise Rejected('WHEEL_REQUIRED: build with uv build --wheel')
        target = self.home/'runtimes'/digest(wheel.read_bytes())/'venv'
        interpreter = target/'bin/python'
        if target.exists():
            old = self.receipt()
            if not old or str(target) not in old['runtimes']:
                raise Rejected('RUNTIME_TARGET_CONFLICT: this runtime is not owned by the installation receipt')
        if not dry_run and not interpreter.exists():
            if target.exists():
                raise Rejected('RUNTIME_TARGET_CONFLICT: move the incomplete runtime aside and retry')
            uv = shutil.which('uv')
            if not uv:
                raise Rejected('UV_REQUIRED: install uv to create the shared runtime')
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                for command in ([uv, 'venv', '--python', sys.executable, str(target)],
                                [uv, 'pip', 'install', '--python', str(interpreter), str(wheel)]):
                    result = subprocess.run(command, capture_output=True, timeout=180)
                    if result.returncode:
                        raise Rejected('RUNTIME_INSTALL_FAILED: check uv package availability; registration was not changed')
                probe(interpreter)
            except BaseException:
                shutil.rmtree(target, ignore_errors=True)
                raise
        return str(interpreter), str(target)

    def install(self, *, wheel=None, runtime_python=None, dry_run=False, repair=False, adopt_existing=False):
        if dry_run:
            return self._install(wheel, runtime_python, True, repair, adopt_existing)
        with self.lock():
            return self._install(wheel, runtime_python, False, repair, adopt_existing)

    def _install(self, wheel, runtime_python, dry_run, repair, adopt_existing):
        old = self.receipt()
        if old and old.get('state_dir') != str(self.state_dir):
            raise Rejected('INSTALL_RECEIPT_TARGET_MISMATCH: preserve the existing authentication state path')
        text = self.config.read_text() if self.config.exists() else ''
        parsed, _, _, previous_block = section(text)
        # Check conflicts before provisioning a runtime.
        if parsed.get('mcp_servers', {}).get(SERVER) is not None and not old and not adopt_existing:
            raise Rejected('MCP_ENTRY_EXISTS: review --dry-run --adopt-existing to back up and migrate only this entry')
        for name in ('SKILL.md', 'installation.json'):
            path = safe(self.skill_dir/name)
            if path.exists():
                expected = old and old['files'].get(name)
                if not expected and not adopt_existing:
                    raise Rejected('SKILL_EXISTS: review --dry-run --adopt-existing before migration')
                if expected and digest(path.read_bytes()) != expected and not repair:
                    raise Rejected('OWNED_SKILL_CHANGED: review setup repair --dry-run')
        if old and previous_block and previous_block != old['mcp_block'] and not repair:
            raise Rejected('OWNED_MCP_ENTRY_CHANGED: review setup repair --dry-run')
        if self.launcher.exists() and (not old or digest(self.launcher.read_bytes()) != old.get('launcher_sha256')) and not repair:
            raise Rejected('CLI_LAUNCHER_CHANGED: review setup repair --dry-run')
        python, owned_runtime = self.runtime(wheel, runtime_python or (old and old['interpreter']), dry_run)
        if wheel and dry_run:
            info = {'version': 'FROM_WHEEL', 'skill': SKILL.read_text()}
        else:
            info = probe(python)
        launcher = ('#!/bin/sh\nexec ' + shlex.quote(python) + ' -I -B -m agent_librarian "$@"\n').encode()
        block = self.block(python)
        updated = patch(text, block)
        metadata = {'schema_version': 1, 'distribution': 'agent-librarian-mcp', 'version': info['version'],
                    'interpreter': python, 'mcp_server': SERVER, 'installation_home': str(self.home),
                    'state_dir': str(self.state_dir), 'cli': str(self.launcher),
                    'codex_home': str(self.config.parent), 'skills_home': str(self.skill_dir.parent), 'project_mapping': 'USER_LOCAL_NEAREST_ANCESTOR_DENY_UNMAPPED'}
        files = {'SKILL.md': info['skill'].encode(),
                 'installation.json': (json.dumps(metadata, indent=2)+'\n').encode()}
        changes = [str(self.skill_dir/n) for n, raw in files.items()
                   if not (self.skill_dir/n).exists() or (self.skill_dir/n).read_bytes() != raw]
        if text != updated:
            changes.append(str(self.config))
        if not self.launcher.exists() or self.launcher.read_bytes() != launcher or not os.access(self.launcher, os.X_OK):
            changes.append(str(self.launcher))
        runtimes = dict((old or {}).get('runtimes', {}))
        if owned_runtime:
            fingerprint = 'PREVIEW' if dry_run else runtime_fingerprint(owned_runtime)
            if not dry_run and owned_runtime in runtimes and runtimes[owned_runtime] != fingerprint:
                raise Rejected('MANAGED_RUNTIME_CHANGED: preserve it and install a fresh wheel version instead')
            runtimes[owned_runtime] = fingerprint
        receipt = {'schema_version': 1, 'owner': 'agent-librarian-mcp', 'interpreter': python,
                   'version': info['version'], 'config': str(self.config), 'skill_dir': str(self.skill_dir),
                   'state_dir': str(self.state_dir), 'mcp_block': block,
                   'files': {n: digest(raw) for n, raw in files.items()},
                   'runtimes': runtimes, 'launcher_sha256': digest(launcher)}
        if not dry_run:
            # Snapshot every file we replace, including the complete Codex config.
            for name, raw in files.items():
                path = self.skill_dir/name
                if str(path) in changes:
                    self.backup(path)
                    atomic(path, raw)
            if text != updated:
                self.backup(self.config)
                atomic(self.config, updated.encode())
            if str(self.launcher) in changes:
                self.backup(self.launcher)
                atomic(self.launcher, launcher)
                self.launcher.chmod(0o700)
            if receipt != old:
                write_private(self.receipt_path, receipt)
        return {'status': 'PREVIEW' if dry_run else ('INSTALLED' if changes or not old else 'UNCHANGED'),
                'changes': changes, 'runtime': python, 'network_operations': 0,
                'package_downloads_possible': bool(wheel), 'project_writes': 0,
                'authentication_changed': False, 'cli': str(self.launcher), 'mcp_block': block}

    def status(self, project='.'):
        receipt = self.receipt()
        checks = []
        def check(name, ok, action):
            checks.append({'check': name, 'ok': bool(ok), 'action': None if ok else action})
        check('installation_receipt', receipt, 'Run librarian setup install.')
        if receipt:
            check('cli_launcher', self.launcher.is_file() and digest(self.launcher.read_bytes()) == receipt['launcher_sha256'] and os.access(self.launcher, os.X_OK), 'Run setup repair.')
            try:
                info = probe(receipt['interpreter'])
                check('runtime', info['version'] == receipt['version'], 'Run setup update --wheel PATH.')
            except Rejected:
                check('runtime', False, 'Run setup repair --runtime-python PATH or setup update --wheel PATH.')
            for name, expected in receipt['files'].items():
                path = safe(self.skill_dir/name)
                check(name, path.is_file() and digest(path.read_bytes()) == expected, 'Run setup repair.')
            try:
                _, _, _, block = section(self.config.read_text() if self.config.exists() else '')
                check('mcp_registration', block == receipt['mcp_block'], 'Run setup repair.')
            except Rejected as error:
                check('mcp_registration', False, error.code)
        mapping = ProjectMappings(self.home).resolve(project)
        check('project_mapping', mapping['status'] == 'MAPPED', mapping.get('action'))
        # Metadata only: no Keychain, Apple Events, tab enumeration or online validity assertion.
        try:
            from .personal.state import PersonalState
            from .personal.brave_transport import CONNECTION, validate_connection
            state = PersonalState(self.state_dir)
            config = state.load()
            check('authentication_metadata', config['authenticated'], 'Complete an explicit initial Brave connection; do not reinstall.')
            check('runtime_enabled', not (state.path/'DISABLED').exists(), 'Review the local DISABLED marker with the owner.')
            c = read_private(state.path/CONNECTION)
            validate_connection(c)
            check('brave_connection_metadata', c.get('status') == 'BROWSER_DISCOVERY_VERIFIED' and c.get('account_id') == config['account_id'],
                  'Ask the owner to restore the pinned Brave Notebook homepage; rebind only with consent.')
            inventory = state.inventory()
            ids = {b['notebook_id'] for b in inventory['notebooks']}
            check('mapped_notebooks_discovered', inventory.get('account_id') == config['account_id'] and
                  mapping['status'] == 'MAPPED' and set(mapping['notebook_ids']) <= ids,
                  'Map IDs from notebooks list; refresh discovery only with explicit consent.')
        except (OSError, Rejected, ValueError, KeyError, TypeError):
            check('personal_configuration', False, 'Run browser status; initial connection requires owner consent. Credentials are preserved.')
        return {'status': 'HEALTHY_OFFLINE' if all(c['ok'] for c in checks) else 'NEEDS_ATTENTION',
                'checks': checks, 'mapping': mapping, 'interpreter': receipt['interpreter'] if receipt else sys.executable,
                'version': receipt['version'] if receipt else version('agent-librarian-mcp'),
                'network_operations': 0, 'project_writes': 0, 'keychain_accesses': 0,
                'live_browser_tab_checked': False, 'auth_validity_checked_online': False,
                'note': 'Offline health checks cached metadata; a closed tab or expired session is detected at approved dispatch.'}

    def uninstall(self, dry_run=False):
        if dry_run:
            return self._uninstall(True)
        with self.lock():
            return self._uninstall(False)

    def _uninstall(self, dry_run):
        old = self.receipt()
        if not old:
            return {'status': 'UNCHANGED', 'changes': []}
        text = self.config.read_text() if self.config.exists() else ''
        _, _, _, block = section(text)
        if block and block != old['mcp_block']:
            raise Rejected('OWNED_MCP_ENTRY_CHANGED: preserve modified entry; review setup repair --dry-run')
        paths = []
        for name, expected in old['files'].items():
            path = safe(self.skill_dir/name)
            if path.exists():
                if digest(path.read_bytes()) != expected:
                    raise Rejected('OWNED_SKILL_CHANGED: preserve modified Skill; review setup repair --dry-run')
                paths.append(path)
        if self.launcher.exists():
            if digest(self.launcher.read_bytes()) != old['launcher_sha256']:
                raise Rejected('CLI_LAUNCHER_CHANGED: preserve modified launcher; review setup repair --dry-run')
            paths.append(self.launcher)
        removable_runtimes, retained_runtimes = [], []
        for runtime, fingerprint in old['runtimes'].items():
            root = safe(runtime)
            if root.parent.parent != self.home/'runtimes' or root.name != 'venv':
                raise Rejected('INSTALL_RECEIPT_RUNTIME_INVALID')
            if root.exists():
                if runtime_fingerprint(root) == fingerprint:
                    removable_runtimes.append(root)
                else:
                    retained_runtimes.append(runtime)
        changes = [str(p) for p in paths] + ([str(self.config)] if block else []) + [str(self.receipt_path)] + [str(p) for p in removable_runtimes]
        if not dry_run:
            if block:
                self.backup(self.config)
                atomic(self.config, patch(text, '').encode())
            for path in paths:
                self.backup(path)
                path.unlink()
            if self.skill_dir.exists() and not any(self.skill_dir.iterdir()):
                self.skill_dir.rmdir()
            self.receipt_path.unlink()
            for root in removable_runtimes:
                shutil.rmtree(root)
        return {'status': 'PREVIEW' if dry_run else 'UNINSTALLED', 'changes': changes,
                'retained': ['reused external runtimes and modified managed runtimes', 'project mappings', 'backups', 'authentication and Keychain', 'all Notebook content'],
                'retained_runtime_paths': retained_runtimes, 'network_operations': 0, 'project_writes': 0}
