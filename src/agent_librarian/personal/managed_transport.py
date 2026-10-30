"""Browser-context RPC over CDP. Cookies and session metadata stay in Chromium."""
import json
from pathlib import Path
import time

from ..gateway.common import Rejected, strict_json
from .brave_transport import BraveTransport, SAFE_ERRORS
from .managed_browser import ManagedBrowser


def program(name):
    source = Path(__file__).with_name(name).read_text()
    return source.replace('__LIBRARIAN_WIRE__', Path(__file__).with_name('wire.js').read_text())


class ManagedTransport(BraveTransport):
    provider_kind = 'GEMINI_MANAGED_CDP_UNVERIFIED'
    def __init__(self, state, expected_email, notebooks, timeout=30, disabled=lambda: False,
                 browser=None, page=None, browser_factory=ManagedBrowser):
        self.state = state; self.account_id = state.load()['account_id']; self.expected_email = expected_email
        self.notebooks = notebooks; self.timeout = timeout; self.disabled = disabled
        self.closed = False; self.reqid = 100000; self.clock = time.monotonic; self.sleep = time.sleep
        self.browser_factory = browser_factory; self.browser = browser; self.page = page
        self.owns_browser = browser is None; self.cdp = None; self.javascript = program('brave_rpc.js')
        self.diagnostics = {}; self.rpc_identity = None
        if not .05 <= timeout <= 30: raise Rejected('HTTP_CONFIGURATION_INVALID')

    def _ready(self):
        if self.closed or self.disabled(): raise Rejected('SERVICE_DISABLED')
        try:
            if self.browser is None:
                self.browser = self.browser_factory(self.state).__enter__()
            if self.page is None: self.page = self.browser.page()
            if self.cdp is None: self.cdp = self.browser.context.new_cdp_session(self.page)
        except Rejected: raise
        except Exception: raise Rejected('CDP_DISCONNECTED') from None

    def _execute(self, payload):
        self._ready()
        source = self.javascript.replace('__LIBRARIAN_INPUT__', json.dumps(payload, ensure_ascii=True, separators=(',', ':')))
        try:
            response = self.cdp.send('Runtime.evaluate', {'expression': source, 'returnByValue': True, 'awaitPromise': False, 'timeout': 5000})
            if response.get('exceptionDetails'): raise Rejected('CDP_EVALUATION_FAILED')
            value = response.get('result', {}).get('value')
            if not isinstance(value, str) or len(value.encode()) > 3 * 1024 * 1024:
                raise Rejected('CDP_RESPONSE_LIMIT')
            result = strict_json(value)
            if not isinstance(result, dict): raise Rejected('BROWSER_RESPONSE_INVALID')
        except Rejected as error:
            error.diagnostics = {'stage': 'CDP_EVALUATE'}
            raise
        except Exception:
            error = Rejected('CDP_DISCONNECTED'); error.diagnostics = {'stage': 'CDP_EVALUATE'}
            raise error from None
        self.diagnostics = {k: result[k] for k in ('http_status', 'bytes_read', 'frames', 'frame_limit', 'wire_limit', 'rpc_error_code')
                            if type(result.get(k)) is int}
        if payload.get('request'):
            self.rpc_identity = payload['request']['method'] if payload['request']['kind'] == 'rpc' else 'QUERY_STREAM'
        if self.rpc_identity: self.diagnostics['rpc'] = self.rpc_identity
        if result.get('status') == 'ERROR':
            error = Rejected(result.get('code') if result.get('code') in SAFE_ERRORS | {'GOOGLE_RPC_REJECTED'} else 'BROWSER_CONTEXT_FAILURE')
            error.diagnostics = {**self.diagnostics, 'stage': 'BROWSER_FETCH_OR_PROJECTION'}
            raise error
        return result

    def invalidate_auth(self):
        from .managed_auth import record_health
        record_health(self.state, 'SESSION_EXPIRED', error_code='AUTHENTICATION_EXPIRED')

    def bridge(self, filename):
        self._ready()
        bridge = ManagedTransport(self.state, self.expected_email, self.notebooks, self.timeout, self.disabled,
                                  browser=self.browser, page=self.page)
        bridge.javascript = program(filename)
        return bridge

    def close(self):
        self.closed = True
        try:
            if self.cdp:
                try: self.cdp.detach()
                except Exception: pass
        finally:
            if self.owns_browser and self.browser: self.browser.close()
            self.cdp = self.browser = self.page = None


class ManagedNotebookAdmin(ManagedTransport):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs); self.javascript = program('brave_create.js')

    # Share the separately reviewed closed CLI administration contract.
    from .notebook_admin import NotebookAdmin as _Admin
    request = _Admin.request
    discover = _Admin.discover
    create = _Admin.create
