"""Opt-in macOS selected-tab transport; no cookie extraction or debugger.

Uses Brave's native Apple Events command and the reviewed upstream in-page form
fetch pattern. JS and all request data travel over private stdin/stdout pipes.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import time
import uuid
from ..gateway.common import Rejected,strict_json
from ..providers.gemini import LIST_RPC,ReadRequest,parse_discovery,MAX_QUERY_STREAM_BYTES
from ..providers.https_transport import GeminiHTTPS,rpc_result
from .state import read_private,write_private

CONNECTION='browser-connection.json'
SAFE_ERRORS={'BRAVE_NOTEBOOK_HOMEPAGE_REQUIRED','BROWSER_REQUEST_LOST','BROWSER_REQUEST_REJECTED',
    'FORBIDDEN_OPERATION','BRAVE_PAGE_CONTEXT_UNAVAILABLE','ACCOUNT_IDENTITY_MISMATCH',
    'HTTP_STATUS_REJECTED','HTTP_CONTENT_TYPE_REJECTED','HTTP_RESPONSE_LIMIT',
    'HTTP_FRAME_LIMIT','HTTP_FRAME_COUNT_LIMIT','HTTP_WIRE_BUDGET_LIMIT','PROVIDER_PROJECTION_LIMIT',
    'PROVIDER_PROTOCOL_ERROR','PROVIDER_RESPONSE_LIMIT','PROVIDER_RPC_MISMATCH',
    'UNIMPLEMENTED_SOURCE_GAP','AUTHENTICATION_EXPIRED',
    'BROWSER_OUTCOME_UNKNOWN','BROWSER_CONTEXT_FAILURE','BRAVE_AUTOMATION_UNAVAILABLE',
    'IMPORT_UPLOAD_URL_REJECTED','IMPORT_UPLOAD_URL_MISSING','IMPORT_ARGUMENTS_INVALID',
    'IMPORT_STAGE_INVALID','IMPORT_HTTP_REJECTED','IMPORT_OUTCOME_UNKNOWN'}

def osascript(source):
    try:
        result=subprocess.run(['/usr/bin/osascript','-l','JavaScript','-'],input=source.encode(),capture_output=True,timeout=10,
            env={k:v for k,v in os.environ.items() if k in ('PATH','HOME','LANG','USER','LOGNAME')})
        if result.returncode or result.stderr or len(result.stdout)>8*1024*1024:raise Rejected('BRAVE_AUTOMATION_UNAVAILABLE')
        return strict_json(result.stdout)
    except Rejected:raise
    except Exception:raise Rejected('BRAVE_AUTOMATION_UNAVAILABLE') from None

def active_page(runner=osascript):
    # Only the active tab in the front Brave window; no other-tab enumeration.
    result=runner('''function run(){try{var a=Application('com.brave.Browser');if(!a.running())throw 0;
var w=a.windows[0],t=w.activeTab(),u=String(t.url());
if(!/^https:\\/\\/notebook\\.google\\.com(\\/)?([?#].*)?$/.test(u))return JSON.stringify({status:'ERROR',code:'BRAVE_NOTEBOOK_HOMEPAGE_REQUIRED'});
return JSON.stringify({status:'OK',window_id:String(w.id()),tab_id:String(t.id()),origin:'https://notebook.google.com'});
}catch(_){return JSON.stringify({status:'ERROR',code:'BRAVE_AUTOMATION_UNAVAILABLE'});}}''')
    if result.get('status')!='OK':raise Rejected(result.get('code') if result.get('code') in SAFE_ERRORS else 'BRAVE_AUTOMATION_UNAVAILABLE')
    return validate_connection(result)

def validate_connection(c):
    if not isinstance(c,dict) or c.get('origin')!='https://notebook.google.com' or any(not isinstance(c.get(k),str) or not re.fullmatch(r'\d{1,20}',c[k]) for k in ('window_id','tab_id')):
        raise Rejected('BROWSER_CONNECTION_INVALID')
    return {k:c[k] for k in ('window_id','tab_id','origin')}

class BraveTransport:
    provider_kind='GEMINI_BROWSER_UNVERIFIED'
    def __init__(self,connection,account_id,expected_email,notebooks,timeout=30,runner=osascript,clock=time.monotonic,sleep=time.sleep,disabled=lambda:False):
        self.connection=validate_connection(connection);self.account_id=account_id;self.expected_email=expected_email
        self.notebooks=notebooks;self.timeout=timeout;self.runner=runner;self.clock=clock;self.sleep=sleep;self.closed=False;self.reqid=100000
        self.disabled=disabled
        if not .05<=timeout<=30:raise Rejected('HTTP_CONFIGURATION_INVALID')
        self.javascript=Path(__file__).with_name('brave_rpc.js').read_text().replace('__LIBRARIAN_WIRE__',Path(__file__).with_name('wire.js').read_text())
    def _execute(self,payload):
        javascript=self.javascript.replace('__LIBRARIAN_INPUT__',json.dumps(payload,ensure_ascii=True,separators=(',',':')))
        c=self.connection
        source='''function run(){try{var a=Application('com.brave.Browser');if(!a.running())throw 0;
var w=a.windows.byId(%s),t=w.tabs.byId(%s),u=String(t.url());
if(!/^https:\\/\\/notebook\\.google\\.com(\\/)?([?#].*)?$/.test(u))return JSON.stringify({status:'ERROR',code:'BRAVE_NOTEBOOK_HOMEPAGE_REQUIRED'});
return String(t.execute({javascript:%s}));
}catch(_){return JSON.stringify({status:'ERROR',code:'BRAVE_AUTOMATION_UNAVAILABLE'});}}'''%(json.dumps(c['window_id']),json.dumps(c['tab_id']),json.dumps(javascript,ensure_ascii=True))
        result=self.runner(source)
        if not isinstance(result,dict):raise Rejected('BROWSER_RESPONSE_INVALID')
        if result.get('status')=='ERROR':
            error=Rejected(result.get('code') if result.get('code') in SAFE_ERRORS else 'BROWSER_CONTEXT_FAILURE')
            error.diagnostics={k:result[k] for k in ('http_status','bytes_read','response_limit','frames','frame_limit','wire_limit') if type(result.get(k)) is int}
            raise error
        return result
    def account_identity(self):
        if self.closed or self.disabled():raise Rejected('SERVICE_DISABLED')
        # Every dispatch validates the real page account before sending a request.
        return self.account_id
    def secrets(self):return (self.expected_email,)
    def request(self,r):
        if self.closed or self.disabled():raise Rejected('SERVICE_DISABLED')
        GeminiHTTPS._allowed(self,r) # Shared closed operation/argument contract.
        return self._request(r)
    def _request(self,r):
        # Shared bounded single dispatch; CLI administration supplies its own closed contract.
        if self.closed or self.disabled():raise Rejected('SERVICE_DISABLED')
        rid=uuid.uuid4().hex;self.reqid+=100000;dispatched=False;done=False
        try:
            start=self._execute({'action':'start','id':rid,'expected_email':self.expected_email,
                'request':{'kind':r.kind,'method':r.method,'path':r.path,'params':r.params},'reqid':self.reqid,'timeout_ms':int(self.timeout*1000)})
            if start.get('status')!='DISPATCHED':raise Rejected('BROWSER_RESPONSE_INVALID')
            dispatched=True;deadline=self.clock()+self.timeout
            while self.clock()<deadline:
                reply=self._execute({'action':'poll','id':rid})
                if self.disabled():raise Rejected('SERVICE_DISABLED')
                if reply.get('status')=='PENDING':self.sleep(.2);continue
                if reply.get('status')!='DONE':raise Rejected('BROWSER_RESPONSE_INVALID')
                done=True
                if reply.get('http_status') in (401,403):raise Rejected('AUTHENTICATION_EXPIRED')
                if reply.get('http_status')!=200 or not isinstance(reply.get('text'),str):raise Rejected('BROWSER_RESPONSE_INVALID')
                body=reply['text'].encode()
                if len(body)>(MAX_QUERY_STREAM_BYTES if r.kind=='stream' or r.method=='hizoJc' else 131072):raise Rejected('HTTP_RESPONSE_LIMIT')
                return rpc_result(body,r.method,large_source=r.method=='hizoJc') if r.kind=='rpc' else reply['text']
            raise Rejected('PROVIDER_TIMEOUT_OUTCOME_UNKNOWN' if r.kind=='stream' else 'PROVIDER_TIMEOUT')
        except Rejected as error:
            if r.kind=='stream' and dispatched:error.outcome='UNKNOWN'
            raise
        finally:
            if dispatched and not done:
                try:self._execute({'action':'cancel','id':rid})
                except Exception:pass
    def invalidate_auth(self):pass # Never re-login, rotate, or replay automatically.
    def close(self):self.closed=True # Does not close/navigate Brave.

def browser_status(state):
    path=state.path/CONNECTION
    if not path.exists():return {'status':'NOT_CONNECTED','transport':'BRAVE_APPLE_EVENTS','network_operations':0}
    c=read_private(path);validate_connection(c)
    disabled=(state.path/'DISABLED').exists()
    return {'status':'DISABLED' if disabled else c.get('status','INCOMPLETE'),'mode':'PERSONAL_LOCAL','transport':'BRAVE_APPLE_EVENTS',
        'authenticated':not disabled and state.load()['authenticated'] and c.get('status')=='BROWSER_DISCOVERY_VERIFIED','session_validation':c.get('status'),
        'storage':'EXISTING_BRAVE_SESSION','network_operations':0,'keychain_session_unchanged':True}

def connect(state,consent,store=None,runner=osascript,*,active_tab=False):
    if not consent:raise Rejected('LOGIN_AND_DISCOVERY_CONSENT_REQUIRED')
    from .storage import PersonalKeychainStore
    store=store or PersonalKeychainStore(state)
    saved=store.load() # Existing protected identity binding; no save/delete.
    config=state.load()
    if saved.account_id!=config['account_id']:raise Rejected('ACCOUNT_IDENTITY_MISMATCH')
    path=state.path/CONNECTION
    if path.exists() and not active_tab:
        existing=read_private(path)
        if existing.get('account_id')!=config['account_id']:raise Rejected('ACCOUNT_IDENTITY_MISMATCH')
        connection=validate_connection(existing)
    else:connection=active_page(runner)
    connection.update(status='BROWSER_RPC_PENDING',account_id=config['account_id'])
    write_private(state.path/CONNECTION,connection)
    transport=BraveTransport(connection,config['account_id'],saved.expected_email,{},timeout=20,runner=runner)
    decoded=None
    try:
        decoded=transport.request(ReadRequest('rpc',LIST_RPC,'/',[None,1,None,[2]]))
        books=parse_discovery(decoded)
        with state.lock():
            config=state.load();config.update(authenticated=True,host='notebook.google.com',selected_notebook=None,query_permit=None,generation=config['generation']+1)
            write_private(state.path/'notebooks.json',{'account_id':config['account_id'],'notebooks':books});state.save(config)
            connection['status']='BROWSER_DISCOVERY_VERIFIED';write_private(state.path/CONNECTION,connection)
            marker=state.path/'DISABLED'
            if marker.exists() and not marker.is_symlink():marker.unlink()
        return {'status':'BROWSER_DISCOVERY_VERIFIED','transport':'BRAVE_APPLE_EVENTS','account':saved.expected_email,
            'discovery_requests':1,'notebooks':[{'notebook_id':b['notebook_id'],'title':b['title']} for b in books]}
    except Rejected as error:
        if error.code in ('UNIMPLEMENTED_SOURCE_GAP','PROVIDER_STRUCTURE_INVALID','INVALID_ARGUMENTS'):
            # Shape-only diagnostics; never notebook names/IDs, tokens or raw body.
            shape={'phase':'DISCOVERY_PROJECTION' if decoded is not None else 'RPC_ENVELOPE',
                'payload_type':type(decoded).__name__,'outer_length':len(decoded) if isinstance(decoded,list) else None}
            if isinstance(decoded,list) and decoded and isinstance(decoded[0],list):
                shape['rows']=[{'type':type(row).__name__,'length':len(row) if isinstance(row,list) else None,
                    'source_field_type':type(row[1]).__name__ if isinstance(row,list) and len(row)>1 else None}
                    for row in decoded[0][:8]]
            error.diagnostics=shape
        connection.update(status='BROWSER_RPC_FAILED',error_code=error.code);write_private(state.path/CONNECTION,connection);raise
    finally:transport.close()
