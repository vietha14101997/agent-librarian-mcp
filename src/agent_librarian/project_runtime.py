"""One shared registration, scoped to the MCP process working project.

Initialization is offline and needs neither a map nor authentication. Resolve the
map on every call so unmap/change takes effect in already running sessions.
"""
import threading
from .gateway.common import NAMES, Rejected, exact
from .gateway.policy import Gateway
from .personal.state import PersonalState, DEFAULT_STATE
from .projects import ProjectMappings


class ProjectGateway:
    def __init__(self, project, home, state_dir=DEFAULT_STATE, prepare_fn=None):
        self.project, self.home, self.state_dir = project, home, state_dir
        self.prepare_fn = prepare_fn
        self.stopped = False
        self.busy = threading.Lock()

    def call(self, name, arguments):
        if not self.busy.acquire(blocking=False):
            return {'status': 'ERROR', 'code': 'BUSY'}
        try:
            return self._call(name, arguments)
        finally:
            self.busy.release()

    def _call(self, name, arguments):
        try:
            if self.stopped:
                raise Rejected('SERVICE_DISABLED')
            if name not in NAMES:
                raise Rejected('FORBIDDEN_OPERATION')
            mapping = ProjectMappings(self.home).resolve(self.project)
            if mapping['status'] != 'MAPPED':
                raise Rejected('PROJECT_NOT_MAPPED')
            ids = mapping['notebook_ids']
            # Reject foreign identities before touching authentication or Brave.
            if name != NAMES[0] and (not isinstance(arguments, dict) or arguments.get('notebook_id') not in ids):
                raise Rejected('NOTEBOOK_NOT_ALLOWED')
            state = PersonalState(self.state_dir)
            config = state.load()
            if not config['authenticated']:
                raise Rejected('AUTHENTICATION_REQUIRED')
            if (state.path / 'DISABLED').exists():
                raise Rejected('SERVICE_DISABLED')
            inventory = state.inventory()
            if inventory.get('account_id') != config['account_id']:
                raise Rejected('ACCOUNT_IDENTITY_MISMATCH')
            books = {b['notebook_id']: b for b in inventory['notebooks']}
            if any(nb not in books for nb in ids):
                raise Rejected('MAPPED_NOTEBOOK_NOT_DISCOVERED')
            if name == NAMES[0]:
                exact(arguments, ())
                return {'status': 'OK', 'project': mapping['project'], 'mapping_project': mapping['mapping_project'],
                        'inventory_origin': 'OWNER_APPROVED_DISCOVERY_CACHE', 'network_operations': 0,
                        'notebooks': [{'notebook_id': nb, 'title': books[nb]['title']} for nb in ids]}
            from .personal.runtime import prepare
            policy, provider = (self.prepare_fn or prepare)(state, notebook_ids=ids)
            gateway = Gateway(policy, None, state.path, provider=provider)
            try:
                return gateway.call(name, arguments)
            finally:
                gateway.close()
        except Rejected as error:
            return {'status': 'ERROR', 'code': error.code}
        except (OSError, ValueError, KeyError, TypeError):
            return {'status': 'ERROR', 'code': 'PROJECT_OR_PERSONAL_CONFIGURATION_INVALID'}

    def close(self):
        self.stopped = True
