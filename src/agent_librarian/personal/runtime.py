"""Current-user in-process provider. Four research methods; no privileged machinery."""
from contextlib import contextmanager
import time
from pathlib import Path
from ..gateway.common import Rejected,NAMES
from ..gateway.policy import Gateway
from ..providers.gemini import GeminiResearchProvider,AccountCapability
from ..providers.https_transport import GeminiHTTPS
from ..providers.service import SecretConfinement
from .browser_auth import seed_manager
from .storage import PersonalKeychainStore
from .state import PersonalState,write_private

class PersonalProvider:
    runtime_mode='PERSONAL_LOCAL'
    def __init__(self,state,backend,sessions,generation):
        self.state=state;self.backend=backend;self.sessions=sessions;self.generation=generation;self.closed=False
    def _check(self):
        c=self.state.load()
        if self.closed or not c['authenticated'] or c['generation']!=self.generation or (self.state.path/'DISABLED').exists():raise Rejected('SERVICE_DISABLED')
        return c
    def list_notebooks(self):
        c=self._check();b=c['selected_notebook']
        return {'account_id':c['account_id'],'status':'ok','provider_kind':'GEMINI_HTTPS_UNVERIFIED',
            'data':{'notebooks':[{'id':b['notebook_id'],'title':b['title']}]},'inventory_origin':'OWNER_APPROVED_DISCOVERY_CACHE'}
    def get_notebook(self,notebook_id):self._check();return self.backend.get_notebook(notebook_id)
    def get_source(self,notebook_id,source_id):self._check();return self.backend.get_source(notebook_id,source_id)
    def query(self,notebook_id,query,source_ids):
        self._check();self.state.consume_query(notebook_id,query)
        return self.backend.query(notebook_id,query,source_ids)
    def close(self):self.closed=True;self.backend.close()

def prepare(state,store=None,sender=None):
    c=state.load();book=c['selected_notebook']
    if not c['authenticated']:raise Rejected('AUTHENTICATION_REQUIRED')
    if not book:raise Rejected('NOTEBOOK_SELECTION_REQUIRED')
    if (state.path/'DISABLED').exists():raise Rejected('SERVICE_DISABLED')
    store=store if store is not None else PersonalKeychainStore(state)
    s=store.load()
    if s.account_id!=c['account_id'] or s.host!=c['host']:raise Rejected('ACCOUNT_IDENTITY_MISMATCH')
    notebooks={book['notebook_id']:{'title':book['title'],'sources':{x['id']:x['title'] for x in book['sources']}}}
    if not notebooks[book['notebook_id']]['sources']:raise Rejected('SELECTED_NOTEBOOK_HAS_NO_SOURCES')
    policy={'version':1,'enabled':True,'account_id':c['account_id'],'notebooks':notebooks,'query_max_chars':2000,'timeout_seconds':30}
    write_private(state.path/'research-policy.json',policy)
    sessions=seed_manager(store,s)
    def disabled():
        latest=state.load()
        return not latest['authenticated'] or latest['generation']!=c['generation'] or (state.path/'DISABLED').exists()
    transport=GeminiHTTPS(sessions,notebooks,timeout=30,sender=sender,disabled=disabled,validate_discovery=False)
    backend=GeminiResearchProvider(transport,AccountCapability(c['account_id']),notebooks)
    provider=PersonalProvider(state,SecretConfinement(backend,sessions.secrets),sessions,c['generation'])
    return state.path/'research-policy.json',provider

def status(state,store,show_account=False):
    c=state.load();result={'mode':'PERSONAL_LOCAL','authenticated':False,'storage':'MACOS_KEYCHAIN','network_operations':0,
        'selected_notebook_id':c['selected_notebook']['notebook_id'] if c['selected_notebook'] else None,
        'same_user_credential_isolation':False,'disabled':(state.path/'DISABLED').exists()}
    journal=state.path/'last-login.json'
    if journal.exists():
        from .state import read_private
        result['last_login']=read_private(journal)
    if not c['authenticated']:return result
    s=store.load()
    if s.account_id!=c['account_id'] or s.host!=c['host']:raise Rejected('ACCOUNT_IDENTITY_MISMATCH')
    result.update(authenticated=True,session_validation='CACHED' if s.expires_at>time.time() else 'REFRESH_REQUIRED_AT_NEXT_APPROVED_READ')
    if show_account:result['account']=s.expected_email
    return result

def logout(state,store):
    with state.lock():
        c=state.load();c.update(authenticated=False,selected_notebook=None,query_permit=None,generation=c['generation']+1);state.save(c)
        write_private(state.path/'DISABLED',{'reason':'OWNER_LOGOUT'})
    store.delete()
    return {'status':'LOGGED_OUT','local_keychain_item_deleted':True,'runtime_disabled':True,
        'browser_profile_retained':True,'provider_sessions_revoked':False}

def direct_call(state,name,args,store=None,sender=None):
    policy,provider=prepare(state,store,sender)
    gateway=Gateway(policy,None,state.path,provider=provider)
    try:return gateway.call(name,args)
    finally:gateway.close()
