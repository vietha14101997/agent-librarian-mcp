"""Explicit human Brave login, owned fresh profile and pipe-backed Playwright.

Managed-profile/token/cookie checks selectively adapted from upstream utils/cdp.py
and core/auth.py at 8ac9728ec5b128b05077e9d7c4c8bb11b5830c61 (MIT), copyright
(c) 2025 Jacob Ben David. No upstream browser discovery/recovery/store is imported.
"""
import asyncio
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urlsplit
from ..gateway.common import Rejected
from ..providers.session import Session,SessionManager,page_session,GOOGLE_HOSTS
from ..providers.gemini import ReadRequest,LIST_RPC,parse_discovery
from ..providers.https_transport import GeminiHTTPS
from .state import write_private
from .progress import LoginProgress

BRAVE=Path('/Applications/Brave Browser.app/Contents/MacOS/Brave Browser')

@contextmanager
def quiet_browser_environment():
    names=('DEBUG','PWDEBUG','PLAYWRIGHT_DEBUG','NODE_OPTIONS','NODE_EXTRA_CA_CERTS','NODE_TLS_REJECT_UNAUTHORIZED')
    previous={k:os.environ.pop(k) for k in names if k in os.environ}
    try:yield
    finally:os.environ.update(previous)

def browser_session(html,cookies,url,account_id):
    u=urlsplit(url)
    if u.scheme!='https' or u.hostname not in GOOGLE_HOSTS or u.port not in (None,443) or '/notebook/' in u.path:raise Rejected('BRAVE_NOT_ON_NOTEBOOK_HOME')
    if not isinstance(html,str) or len(html.encode())>2*1024*1024:raise Rejected('SESSION_REFRESH_STRUCTURE_CHANGED')
    hits=re.findall(r'"oPEP7c"\s*:\s*("(?:[^"\\]|\\.)*")',html)
    try:emails={json.loads(x) for x in hits}
    except ValueError:raise Rejected('SESSION_REFRESH_STRUCTURE_CHANGED') from None
    if len(emails)!=1:raise Rejected('BRAVE_LOGIN_NOT_READY')
    selected={}
    if not isinstance(cookies,list) or len(cookies)>500:raise Rejected('BRAVE_COOKIE_LIMIT')
    # Most-specific applicable domain/path wins; never use cookies from unrelated domains.
    for c in sorted(cookies,key=lambda x:(len(x.get('domain','')),len(x.get('path','')))):
        domain=c.get('domain','').lstrip('.')
        if domain and (u.hostname==domain or u.hostname.endswith('.'+domain)) and (not str(c.get('name','')).startswith('__Secure-') or c.get('secure') is True):
            selected[c.get('name')]=c.get('value')
    if not any(k in selected for k in ('SID','__Secure-1PSID','__Secure-3PSID')):raise Rejected('BRAVE_LOGIN_NOT_READY')
    email=emails.pop()
    seed=Session(account_id,email,selected,'pending','1','pending',1,u.hostname)
    return page_session(html,seed,time.time())

def seed_manager(store,session):
    manager=SessionManager(store,session.account_id,session.expected_email,session.host)
    manager._accept_binding(session)
    if session.expires_at>time.time():
        manager.current=session;manager._redactions=session.secrets();manager.state='VALIDATED_PERSONAL_CACHE'
    return manager

async def capture_brave(state,timeout=600,launcher=None):
    if not 1<=timeout<=900:raise Rejected('BRAVE_LOGIN_TIMEOUT_INVALID')
    profile=state.profile()
    if not BRAVE.is_file():raise Rejected('BRAVE_NOT_INSTALLED')
    try:
        if launcher is None:
            from playwright.async_api import async_playwright
            launcher=async_playwright
    except ImportError:raise Rejected('PERSONAL_DEPENDENCIES_REQUIRED') from None
    progress=LoginProgress(state,reset=True);progress.event('browser_launch_requested')
    phase='launching'
    try:
        with quiet_browser_environment():
            async with launcher() as engine:
                context=await engine.chromium.launch_persistent_context(str(profile),executable_path=str(BRAVE),
                    headless=False,chromium_sandbox=True,accept_downloads=False,
                    ignore_default_args=['--enable-automation'],
                    args=['--no-first-run','--no-default-browser-check','--disable-extensions'])
                progress.event('browser_started');progress.attach(context)
                try:
                    page=context.pages[0] if context.pages else await context.new_page()
                    phase='opening_home'
                    try:await page.goto('https://notebooklm.google.com/',wait_until='domcontentloaded',timeout=30000)
                    except Exception:
                        if progress.context_closed:raise Rejected('BRAVE_WINDOW_CLOSED')
                    phase='waiting_for_human';progress.event('waiting_for_human')
                    deadline=time.monotonic()+timeout
                    while time.monotonic()<deadline:
                        if progress.context_closed:raise Rejected('BRAVE_WINDOW_CLOSED')
                        for candidate in context.pages:
                            u=urlsplit(candidate.url)
                            if u.scheme!='https' or u.hostname not in GOOGLE_HOSTS or '/notebook/' in u.path:continue
                            try:
                                html=await candidate.evaluate('document.documentElement.outerHTML.slice(0,2097152)')
                                cookies=await context.cookies(['https://'+u.hostname+'/'])
                                captured=browser_session(html,cookies,candidate.url,state.load()['account_id'])
                                progress.event('session_captured_without_persistence')
                                return captured
                            except Exception:continue
                        await asyncio.sleep(.5)
                    progress.event('login_timeout');raise Rejected('BRAVE_LOGIN_TIMEOUT')
                finally:
                    if not progress.context_closed:
                        progress.cleanup_requested=True;progress.event('controller_cleanup_requested')
                        await context.close()
    except Rejected as failure:
        progress.event('capture_stopped',code=failure.code);raise
    except Exception as exception:
        error=Rejected('BRAVE_LOGIN_FAILED')
        description=str(exception)
        error.diagnostics={'phase':phase,'exception_type':type(exception).__name__,
            'permission_denied':'Operation not permitted' in description or 'EACCES' in description,
            'browser_closed':'closed' in description.lower(),'executable_missing':'executable' in description.lower() and 'exist' in description.lower()}
        progress.event('capture_stopped',code=error.code,**error.diagnostics)
        raise error from None

async def login(state,store,consent,timeout=600,capture=capture_brave,sender=None):
    if not consent:raise Rejected('LOGIN_AND_DISCOVERY_CONSENT_REQUIRED')
    store.probe() # Prove Keychain availability before asking the human to sign in.
    config=state.load()
    if config['authenticated']:
        saved=store.load()
        if saved.account_id!=config['account_id'] or saved.host!=config['host']:raise Rejected('ACCOUNT_IDENTITY_MISMATCH')
        sessions=seed_manager(store,saved);check=GeminiHTTPS(sessions,{},sender=sender,validate_discovery=False)
        try:
            sessions.ensure(check._refresh)
            discovery_requests=0
            if not (state.path/'notebooks.json').exists():
                if not consent:raise Rejected('DISCOVERY_CONSENT_REQUIRED_SESSION_RETAINED')
                books=parse_discovery(check.request(ReadRequest('rpc',LIST_RPC,'/',[None,1,None,[2]])))
                with state.lock():
                    write_private(state.path/'notebooks.json',{'account_id':config['account_id'],'notebooks':books})
                discovery_requests=1
            return {'status':'AUTHENTICATED_REUSED','mode':'PERSONAL_LOCAL','account':saved.expected_email,'storage':'MACOS_KEYCHAIN',
                'discovery_requests':discovery_requests,'browser_reopened':False,
                'notebooks':[{'notebook_id':b['notebook_id'],'title':b['title']} for b in state.inventory()['notebooks']]}
        finally:check.close()
    session=await capture(state,timeout)
    progress=LoginProgress(state);progress.event('validating_http_account')
    manager=seed_manager(store,session)
    transport=GeminiHTTPS(manager,{},timeout=15,sender=sender,validate_discovery=False)
    try:
        # Exactly one explicit bounded discovery; do not repeat it for validation.
        html=transport._http('GET','/',session,html=True).decode('utf-8')
        session=page_session(html,session,time.time())
        manager.current=session;manager._redactions=session.secrets()
        books=parse_discovery(transport.request(ReadRequest('rpc',LIST_RPC,'/',[None,1,None,[2]])))
        progress.event('discovery_completed',discovery_requests=1,notebook_count=len(books))
        store.save(session);progress.event('keychain_session_saved')
        with state.lock():
            c=state.load();c.update(authenticated=True,host=session.host,selected_notebook=None,query_permit=None,generation=c['generation']+1)
            write_private(state.path/'notebooks.json',{'account_id':c['account_id'],'notebooks':books})
            state.save(c)
            disabled=state.path/'DISABLED'
            if disabled.exists() and not disabled.is_symlink():disabled.unlink()
        progress.event('authentication_complete')
        return {'status':'AUTHENTICATED','mode':'PERSONAL_LOCAL','account':session.expected_email,
            'storage':'MACOS_KEYCHAIN','discovery_requests':1,
            'notebooks':[{'notebook_id':b['notebook_id'],'title':b['title']} for b in books],
            'next_action':'Approve an exact notebook and question; queries may persist chat history.'}
    finally:transport.close()
