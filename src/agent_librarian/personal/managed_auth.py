"""Explicit login and bounded read-only health recovery; no query/mutation replay."""
import time
from urllib.parse import urlsplit

from ..gateway.common import Rejected
from ..providers.gemini import LIST_RPC, ReadRequest, parse_discovery
from ..providers.session import GOOGLE_HOSTS
from .managed_browser import ManagedBrowser
from .managed_transport import ManagedTransport
from .state import read_private, write_private

SELECTION = 'transport.json'
AUTH = 'managed-auth.json'
HEALTH = 'managed-health.json'


def selected(state):
    path = state.path / SELECTION
    if not path.exists(): return False
    selection = read_private(path)
    if selection != {'transport': 'MANAGED_CDP', 'runtime_id': state.load()['runtime_id']}:
        raise Rejected('TRANSPORT_SELECTION_INVALID')
    return True


def binding(state):
    data = read_private(state.path / AUTH)
    if (data.get('account_id') != state.load()['account_id'] or not isinstance(data.get('email'), str)
            or not data['email'] or len(data['email']) > 320):
        raise Rejected('ACCOUNT_IDENTITY_MISMATCH')
    return data['email']


def page_identity(page):
    u = urlsplit(page.url)
    if u.hostname == 'accounts.google.com': raise Rejected('REAUTHENTICATION_REQUIRED')
    if u.scheme != 'https' or u.hostname not in GOOGLE_HOSTS or u.path != '/':
        raise Rejected('MANAGED_PAGE_NOT_READY')
    # Return account identity only. Never export page HTML, cookies or tokens.
    try: result = page.evaluate('''() => {
      const values = new Set();
      for (const s of document.scripts) {
        if (!(s.textContent || '').includes('WIZ_global_data')) continue;
        for (const m of s.textContent.matchAll(/"oPEP7c"\\s*:\\s*("(?:[^"\\\\]|\\\\.)*")/g)) values.add(JSON.parse(m[1]));
      }
      return values.size === 1 ? [...values][0] : null;
    }''')
    except Exception: raise Rejected('CDP_DISCONNECTED') from None
    if not isinstance(result, str) or '@' not in result or len(result) > 320:
        raise Rejected('MANAGED_PAGE_NOT_READY')
    return result


def record_health(state, status, **values):
    record = {'status': status, 'checked_at': int(time.time()), **values}
    write_private(state.path / HEALTH, record)
    return record


def status(state, show_account=False):
    c = state.load()
    result = {'transport': 'MANAGED_CDP', 'status': 'OFFLINE_CACHED' if c['authenticated'] else 'REAUTHENTICATION_REQUIRED',
              'authenticated': False, 'cached_authenticated': c['authenticated'], 'network_operations': 0,
              'storage': 'DEDICATED_CHROMIUM_PROFILE', 'disabled': (state.path / 'DISABLED').exists()}
    if (state.path / HEALTH).exists(): result['last_check'] = read_private(state.path / HEALTH)
    if show_account and (state.path / AUTH).exists(): result['account'] = binding(state)
    return result


def verify(state, browser, page, expected):
    actual = page_identity(page)
    if expected and actual.lower() != expected.lower(): raise Rejected('ACCOUNT_IDENTITY_MISMATCH')
    transport = ManagedTransport(state, actual, {}, browser=browser, page=page)
    try:
        books = parse_discovery(transport.request(ReadRequest('rpc', LIST_RPC, '/', [None, 1, None, [2]])))
        return actual, books, transport.diagnostics
    finally: transport.close()


def accept(state, email, books, diagnostics):
    with state.lock():
        c = state.load()
        if not selected(state):
            c.update(generation=c['generation']+1, query_permit=None)
        # Keep selected identities and query permits intact during ordinary refresh.
        c.update(authenticated=True, host='notebook.google.com')
        write_private(state.path / AUTH, {'account_id': c['account_id'], 'email': email})
        write_private(state.path / 'notebooks.json', {'account_id': c['account_id'], 'notebooks': books})
        write_private(state.path / SELECTION, {'transport': 'MANAGED_CDP', 'runtime_id': c['runtime_id']})
        state.save(c)
        marker = state.path / 'DISABLED'
        if marker.exists() and not marker.is_symlink(): marker.unlink()
    return record_health(state, 'AUTHENTICATED_VERIFIED', discovery_requests=1, diagnostics=diagnostics)


def login(state, consent, timeout=600, browser_factory=ManagedBrowser):
    if not consent: raise Rejected('LOGIN_AND_DISCOVERY_CONSENT_REQUIRED')
    if not 1 <= timeout <= 900: raise Rejected('MANAGED_LOGIN_TIMEOUT_INVALID')
    expected = binding(state) if (state.path / AUTH).exists() else None
    # An explicit migration must retain the protected old account binding.
    if expected is None and state.load()['authenticated']:
        from .storage import PersonalKeychainStore
        expected = PersonalKeychainStore(state).load().expected_email
    if selected(state) and state.load()['authenticated']:
        checked = check(state, browser_factory=browser_factory)
        if checked['status'] == 'AUTHENTICATED_VERIFIED': return checked
        if checked['status'] not in ('SESSION_EXPIRED', 'REAUTHENTICATION_REQUIRED'): return checked
    deadline = time.monotonic() + timeout
    with browser_factory(state, headless=False) as browser:
        page = browser.page()
        while time.monotonic() < deadline:
            candidates = list(browser.context.pages)
            ready = None
            for candidate in candidates:
                try: page_identity(candidate); ready = candidate; break
                except Rejected as error:
                    if error.code not in ('REAUTHENTICATION_REQUIRED', 'MANAGED_PAGE_NOT_READY'): raise
            if ready:
                email, books, diagnostics = verify(state, browser, ready, expected)
                return accept(state, email, books, diagnostics)
            if page.is_closed(): raise Rejected('MANAGED_LOGIN_WINDOW_CLOSED')
            time.sleep(.5)
    raise Rejected('MANAGED_LOGIN_TIMEOUT')


def check(state, *, refresh=False, browser_factory=ManagedBrowser):
    expected = binding(state)
    if (state.path / 'DISABLED').exists(): raise Rejected('REAUTHENTICATION_REQUIRED')
    attempts = 0
    try:
        with browser_factory(state) as browser:
            page = browser.page()
            # At most two safe discovery RPCs; fresh page metadata before retry.
            for attempt in range(2):
                attempts += 1
                try:
                    email, books, diagnostics = verify(state, browser, page, expected)
                    result = accept(state, email, books, diagnostics)
                    result['attempts'] = attempts
                    return result
                except Rejected as error:
                    if attempt or error.code not in ('AUTHENTICATION_EXPIRED', 'BRAVE_PAGE_CONTEXT_UNAVAILABLE'):
                        raise
                    page = browser.page()  # bounded noninteractive CSRF/session refresh
    except Rejected as error:
        status_code = {'AUTHENTICATION_EXPIRED': 'SESSION_EXPIRED', 'REAUTHENTICATION_REQUIRED': 'REAUTHENTICATION_REQUIRED',
                       'MANAGED_PAGE_NOT_READY': 'REAUTHENTICATION_REQUIRED', 'GOOGLE_RPC_REJECTED': 'GOOGLE_RPC_REJECTED',
                       'MANAGED_BROWSER_OFFLINE': 'OFFLINE', 'ACCOUNT_IDENTITY_MISMATCH': 'ACCOUNT_IDENTITY_MISMATCH'}.get(error.code, 'BROWSER_TEMPORARILY_UNAVAILABLE')
        return record_health(state, status_code, error_code=error.code, attempts=attempts,
                             diagnostics=getattr(error, 'diagnostics', {}))


def logout(state):
    # Clear only this dedicated browser context. Failure must not pretend sign-out.
    with ManagedBrowser(state) as browser:
        browser.context.clear_cookies()
        browser.close_browser()
    with state.lock():
        c = state.load(); c.update(authenticated=False, query_permit=None, generation=c['generation'] + 1)
        state.save(c); write_private(state.path / 'DISABLED', {'reason': 'OWNER_LOGOUT'})
    return record_health(state, 'LOGGED_OUT', browser_profile_retained=True, legacy_keychain_unchanged=True,
                         provider_sessions_revoked=False)
