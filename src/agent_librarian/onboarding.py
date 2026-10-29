"""Agent-driven project onboarding. Prompts are data; only owner choices mutate state."""
import hashlib
import os
from pathlib import Path
import re
import uuid
from .gateway.common import Rejected, ident
from .projects import ProjectMappings, project_path
from .personal.state import PersonalState, private_dir, read_private, write_private
from .personal.notebook_admin import browser_admin, create_params


def inventory(state):
    config = state.load()
    if not config['authenticated']:
        raise Rejected('AUTHENTICATION_REQUIRED')
    if (state.path / 'DISABLED').exists():
        raise Rejected('SERVICE_DISABLED')
    data = state.inventory()
    if data.get('account_id') != config['account_id']:
        raise Rejected('ACCOUNT_IDENTITY_MISMATCH')
    books = data.get('notebooks')
    if not isinstance(books, list):
        raise Rejected('NOTEBOOK_INVENTORY_INVALID')
    ids = []
    for book in books:
        if not isinstance(book, dict) or not isinstance(book.get('title'), str) or not isinstance(book.get('sources'), list):
            raise Rejected('NOTEBOOK_INVENTORY_INVALID')
        ids.append(ident(book.get('notebook_id')))
    if len(ids) != len(set(ids)):
        raise Rejected('NOTEBOOK_INVENTORY_INVALID')
    return config, books


def persist_receipt(path, data):
    write_private(path, data)
    # A dispatched receipt must be durable before a non-idempotent network call.
    for directory in (path.parent, path.parent.parent):
        fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def registration_contract(project, home, state_dir):
    """Native client config translation is owned by the installing agent."""
    import sys
    from .installation import SKILL, SERVER
    from .gateway.common import NAMES
    from . import __version__
    return {'status': 'CONTRACT', 'schema_version': 1, 'distribution': 'agent-librarian-mcp',
            'version': __version__, 'interpreter': str(Path(sys.executable).absolute()),
            'transport': 'stdio', 'server_name': SERVER,
            'command': str(Path(sys.executable).absolute()),
            'args': ['-I', '-B', '-m', 'agent_librarian', 'mcp-serve', '--provider', 'project',
                     '--project', project_path(project), '--installation-home', str(Path(home).expanduser().absolute()),
                     '--state-dir', str(Path(state_dir).expanduser().absolute())],
            'tools': list(NAMES), 'skill_source': str(SKILL),
            'installation_home': str(Path(home).expanduser().absolute()),
            'state_dir': str(Path(state_dir).expanduser().absolute()),
            'project_selection': 'Set --project per workspace, or omit it and inherit the project cwd.',
            'registration': 'Discover the current agent host native MCP and Skill conventions; preserve unrelated settings.',
            'network_operations': 0, 'configuration_writes': 0}


class Onboarding:
    def __init__(self, project, home, state_dir, admin_factory=browser_admin):
        self.project = project_path(project)
        self.maps = ProjectMappings(home)
        self.state_dir = state_dir
        self.admin_factory = admin_factory
        key = hashlib.sha256(self.project.encode()).hexdigest()
        self.receipt_path = self.maps.home / 'onboarding' / (key + '.json')

    def receipt(self):
        if not self.receipt_path.exists():
            return None
        data = read_private(self.receipt_path)
        if (data.get('schema_version') != 1 or data.get('project') != self.project
                or data.get('state') not in ('DISPATCHED', 'UNKNOWN', 'CREATED', 'MAPPED', 'RESOLVED_BY_OWNER')
                or not re.fullmatch('[0-9a-f]{32}', data.get('operation_id', ''))):
            raise Rejected('ONBOARDING_RECEIPT_INVALID')
        return data

    def refresh(self, state, admin):
        books = admin.discover()  # Account attested in-page, one read-only dispatch, no retry.
        write_private(state.path / 'notebooks.json', {'account_id': state.load()['account_id'], 'notebooks': books})
        return inventory(state)

    def link(self, notebook_id):
        ident(notebook_id)
        data = self.maps.load()
        data['projects'][self.project] = {'provider': 'gemini', 'notebook_ids': [notebook_id]}
        write_private(self.maps.path, data)  # Caller holds the mappings lock.
        saved = self.maps.resolve(self.project)
        if saved['mapping_project'] != self.project or saved['notebook_ids'] != [notebook_id]:
            raise Rejected('MAPPING_VERIFICATION_FAILED')
        return {'status': 'MAPPED', 'mapping': saved, 'mapping_verified': True,
                'notebook_id': notebook_id, 'project_writes': 0, 'source_uploads': 0}

    def run(self, *, choice=None, notebook_id=None, approve=False, discover=False,
            title=None, account_id=None, account_email=None, operation_id=None,
            experimental_browser_create=False, dry_run=False):
        mapping = self.maps.resolve(self.project)
        if mapping['status'] == 'MAPPED':
            # Preserve existing/inherited mapping; stale inventory calls for review, not replacement.
            try:
                _, books = inventory(PersonalState(self.state_dir))
                valid = set(mapping['notebook_ids']) <= {b['notebook_id'] for b in books}
            except (Rejected, OSError, KeyError, TypeError):
                return {'status': 'MAPPING_REQUIRES_CONNECTION', 'mapping': mapping, 'changed': False}
            return {'status': 'MAPPED' if valid else 'MAPPING_REQUIRES_REVIEW',
                    'mapping': mapping, 'reused': valid, 'changed': False, 'network_operations': 0}
        proposal = title if title is not None else (Path(self.project).name[:180] + ' — Research')
        if choice == 'skip':
            return {'status': 'SKIPPED', 'mapping': mapping, 'changed': False, 'network_operations': 0}
        if choice is None or dry_run:
            return {'status': 'CHOICE_REQUIRED' if not dry_run else 'PREVIEW', 'mapping': mapping,
                    'question': 'Does this project already have a Notebook, should we create one, or skip integration?',
                    'choices': ['existing', 'new', 'skip'], 'proposed_title': proposal,
                    'pending_creation': self.receipt(), 'network_operations': 0, 'changed': False}
        if choice not in ('existing', 'new', 'recover'):
            raise Rejected('ONBOARDING_CHOICE_INVALID')
        if approve and choice == 'existing' and not notebook_id:
            raise Rejected('EXPLICIT_NOTEBOOK_SELECTION_REQUIRED')
        # No authentication initialization or automatic browser/profile fallback.
        state = PersonalState(self.state_dir)
        config, books = inventory(state)
        if account_id is not None and account_id != config['account_id']:
            raise Rejected('ACCOUNT_IDENTITY_MISMATCH')
        if choice == 'existing' and not discover and not approve:
            return {'status': 'NOTEBOOK_SELECTION_REQUIRED', 'account_id': config['account_id'],
                    'origin': 'CACHED_OWNER_APPROVED_DISCOVERY',
                    'notebooks': [{'notebook_id': b['notebook_id'], 'title': b['title']} for b in books],
                    'action': 'With consent, repeat with --discover to refresh this account inventory; ask the owner to select an ID.',
                    'network_operations': 0}
        if choice == 'new' and not approve and not discover:
            create_params(proposal)
            prior = self.receipt()
            if prior:
                return {'status': 'CREATION_REQUIRES_REVIEW', 'receipt': prior,
                        'action': 'Use recover with owner approval; creation will not be replayed.', 'creation_replayed': False}
            admin = self.admin_factory(state)
            try:
                return {'status': 'CREATION_APPROVAL_REQUIRED', 'project': self.project,
                        'proposed_title': proposal, 'account_id': config['account_id'],
                        'account_email': admin.expected_email, 'operation_id': uuid.uuid4().hex,
                        'automatic_creation': 'EXPERIMENTAL_LIVE_UNVERIFIED',
                        'default': 'MANUAL_CREATION_AND_EXPLICIT_ID_LINK', 'network_operations': 0}
            finally:
                admin.close()
        # Serialize against other onboarding/map commands and account changes/logout.
        with self.maps.lock(), state.lock():
            current = self.maps.resolve(self.project)
            if current['status'] == 'MAPPED':
                return {'status': 'MAPPED', 'mapping': current, 'reused': True, 'changed': False}
            config, books = inventory(state)
            if account_id is not None and account_id != config['account_id']:
                raise Rejected('ACCOUNT_IDENTITY_MISMATCH')
            admin = None
            try:
                if discover or choice in ('new', 'recover'):
                    admin = self.admin_factory(state)
                if discover:
                    config, books = self.refresh(state, admin)
                if choice == 'existing':
                    if not approve:
                        return {'status': 'NOTEBOOK_SELECTION_REQUIRED', 'account_id': config['account_id'],
                                'origin': 'LIVE_ACCOUNT_DISCOVERY',
                                'notebooks': [{'notebook_id': b['notebook_id'], 'title': b['title']} for b in books]}
                    if account_id != config['account_id']:
                        raise Rejected('ACCOUNT_CONFIRMATION_REQUIRED')
                    if notebook_id not in {b['notebook_id'] for b in books}:
                        raise Rejected('NOTEBOOK_NOT_DISCOVERED')
                    return self.link(notebook_id)
                prior = self.receipt()
                if choice == 'recover':
                    if not prior:
                        raise Rejected('NO_CREATION_TO_RECOVER')
                    if (not approve or account_id != config['account_id'] or prior['account_id'] != account_id
                            or account_email is None or account_email.casefold() != admin.expected_email.casefold()
                            or prior['account_email'].casefold() != account_email.casefold()):
                        raise Rejected('OWNER_ACCOUNT_CONFIRMATION_REQUIRED')
                    # Never infer from title/diff/order, even if there is exactly one candidate.
                    selected = prior.get('notebook_id')
                    if selected is None:
                        if not notebook_id:
                            raise Rejected('EXPLICIT_NOTEBOOK_SELECTION_REQUIRED')
                        selected = notebook_id
                    elif notebook_id is not None and notebook_id != selected:
                        raise Rejected('CREATION_RECEIPT_NOTEBOOK_MISMATCH')
                    config, books = self.refresh(state, admin)
                    if selected not in {b['notebook_id'] for b in books}:
                        raise Rejected('CREATED_NOTEBOOK_NOT_DISCOVERED')
                    result = self.link(selected)
                    prior.update(state='RESOLVED_BY_OWNER', notebook_id=selected)
                    persist_receipt(self.receipt_path, prior)
                    return dict(result, creation_replayed=False)
                create_params(proposal)
                if prior:
                    return {'status': 'CREATION_REQUIRES_REVIEW', 'receipt': prior,
                            'action': 'Use recover with owner approval; creation will not be replayed.', 'creation_replayed': False}
                if not approve:
                    return {'status': 'CREATION_APPROVAL_REQUIRED', 'project': self.project,
                            'proposed_title': proposal, 'account_id': config['account_id'],
                            'account_email': admin.expected_email, 'operation_id': uuid.uuid4().hex,
                            'automatic_creation': 'EXPERIMENTAL_LIVE_UNVERIFIED',
                            'default': 'MANUAL_CREATION_AND_EXPLICIT_ID_LINK', 'network_operations': int(discover)}
                if (account_id != config['account_id'] or account_email is None
                        or account_email.casefold() != admin.expected_email.casefold()):
                    raise Rejected('OWNER_ACCOUNT_CONFIRMATION_REQUIRED')
                if title is None or not isinstance(operation_id, str) or not re.fullmatch('[0-9a-f]{32}', operation_id):
                    raise Rejected('CONFIRMED_TITLE_AND_OPERATION_ID_REQUIRED')
                if not experimental_browser_create:
                    return {'status': 'MANUAL_CREATION_REQUIRED', 'account_email': admin.expected_email,
                            'title': title, 'url': 'https://notebook.google.com/',
                            'action': 'Create once in the confirmed account, refresh discovery with consent, then explicitly select and link the actual ID using choice existing.',
                            'automatic_creation': 'EXPERIMENTAL_LIVE_UNVERIFIED', 'network_operations': int(discover)}
                private_dir(self.receipt_path.parent, create=True)
                record = {'schema_version': 1, 'project': self.project, 'operation_id': operation_id,
                          'account_id': account_id, 'account_email': admin.expected_email, 'title': title,
                          'state': 'DISPATCHED', 'notebook_id': None}
                persist_receipt(self.receipt_path, record)
                try:
                    created_id = ident(admin.create(title))
                    if created_id in {b['notebook_id'] for b in books}:
                        raise Rejected('CREATION_RESPONSE_UNCERTAIN')
                except BaseException:
                    record['state'] = 'UNKNOWN'
                    persist_receipt(self.receipt_path, record)
                    raise Rejected('CREATION_OUTCOME_UNKNOWN: inspect the account inventory; never retry creation') from None
                record.update(state='CREATED', notebook_id=created_id)
                persist_receipt(self.receipt_path, record)  # Store actual returned ID before discovery/mapping.
                config, books = self.refresh(state, admin)
                if created_id not in {b['notebook_id'] for b in books}:
                    raise Rejected('CREATED_NOTEBOOK_NOT_DISCOVERED: recover later; do not create again')
                result = self.link(created_id)
                record['state'] = 'MAPPED'
                persist_receipt(self.receipt_path, record)
                return dict(result, operation_id=operation_id, creation_live_verified=False)
            finally:
                if admin is not None:
                    admin.close()
