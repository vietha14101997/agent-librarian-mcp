"""CLI-only, live-unverified creation; reuse the pinned account's native transport.

Creation envelope/ID layout reviewed in upstream core/notebooks.py and core/base.py
at 8ac9728ec5b128b05077e9d7c4c8bb11b5830c61. No upstream retry/auth recovery.
"""
from pathlib import Path
from ..gateway.common import Rejected, ident
from ..providers.gemini import LIST_RPC, ReadRequest, parse_discovery
from .brave_transport import BraveTransport, CONNECTION
from .state import read_private

CREATE_RPC = 'CCqFvf'


def create_params(title):
    if not isinstance(title, str) or not title.strip() or len(title) > 200 or any(ord(c) < 32 for c in title):
        raise Rejected('NOTEBOOK_TITLE_INVALID')
    return [title, None, None, [2], [1, None, None, None, None, None, None, None, None, None, [1]]]


class NotebookAdmin(BraveTransport):
    """Only discovery/create; not a ResearchProvider and never registered as MCP."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.javascript = Path(__file__).with_name('brave_create.js').read_text().replace('__LIBRARIAN_WIRE__', Path(__file__).with_name('wire.js').read_text())

    def request(self, request):
        if request != ReadRequest('rpc', LIST_RPC, '/', [None, 1, None, [2]]):
            raise Rejected('FORBIDDEN_OPERATION')
        return self._request(request)

    def discover(self):
        return parse_discovery(self.request(ReadRequest('rpc', LIST_RPC, '/', [None, 1, None, [2]])))

    def create(self, title):
        raw = self._request(ReadRequest('rpc', CREATE_RPC, '/', create_params(title)))
        if not isinstance(raw, list) or len(raw) < 3 or not isinstance(raw[0], str) or raw[0] != title:
            raise Rejected('CREATION_RESPONSE_UNCERTAIN')
        notebook_id = ident(raw[2])
        return notebook_id


def browser_admin(state):
    from .managed_auth import selected, binding
    if selected(state):
        from .managed_transport import ManagedNotebookAdmin
        if not state.load()['authenticated'] or (state.path / 'DISABLED').exists():
            raise Rejected('AUTHENTICATION_REQUIRED')
        return ManagedNotebookAdmin(state, binding(state), {}, disabled=lambda: (state.path / 'DISABLED').exists())
    from .storage import PersonalKeychainStore
    config = state.load()
    if not config['authenticated']:
        raise Rejected('AUTHENTICATION_REQUIRED')
    if (state.path / 'DISABLED').exists():
        raise Rejected('SERVICE_DISABLED')
    connection = read_private(state.path / CONNECTION)
    if connection.get('status') != 'BROWSER_DISCOVERY_VERIFIED':
        raise Rejected('BROWSER_CONNECTION_REQUIRED')
    saved = PersonalKeychainStore(state).load()
    if saved.account_id != config['account_id'] or connection.get('account_id') != config['account_id']:
        raise Rejected('ACCOUNT_IDENTITY_MISMATCH')
    return NotebookAdmin(connection, config['account_id'], saved.expected_email, {}, timeout=20,
                         disabled=lambda: (state.path / 'DISABLED').exists())
