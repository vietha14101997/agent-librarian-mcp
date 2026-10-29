"""Explicit selected-profile, read-only Brave session reuse for a personal pilot.

No discovery of cookie stores outside the approved profile, whole-DB copy, profile
write, browser restart/debugging, generic Keychain lookup, or plaintext fallback.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
import time
from urllib.parse import urlsplit
from ..gateway.common import Rejected,strict_json
from ..providers.gemini import LIST_RPC,ReadRequest,parse_discovery
from ..providers.https_transport import FixedTLS,GeminiHTTPS,HttpReply,PAGE_FETCH_HEADERS
from ..providers.session import Session,GOOGLE_HOSTS
from .browser_auth import browser_session,seed_manager
from .state import private_dir,read_private,write_private
from .storage import KeychainFailure
from .progress import LoginProgress

BRAVE_ROOT=Path.home()/'Library/Application Support/BraveSoftware/Brave-Browser'
AUTH_NAMES=('SID','HSID','SSID','APISID','SAPISID','SIDCC','__Secure-1PSID','__Secure-3PSID','__Secure-1PSIDCC','__Secure-3PSIDCC','__Secure-1PSIDTS','__Secure-3PSIDTS')
COOKIE_HOSTS=('.google.com','google.com','notebooklm.google.com','.notebooklm.google.com','notebook.google.com','.notebook.google.com')
SECONDARY_AUTH_NAMES=('OSID','LSID','__Host-GAPS','ACCOUNT_CHOOSER')
SECONDARY_COOKIE_HOSTS=COOKIE_HOSTS+('accounts.google.com','.accounts.google.com')

def permitted_record(row,secondary_bindings=False):
    return (isinstance(row,dict) and row.get('path')=='/' and
        ((row.get('name') in AUTH_NAMES and row.get('domain') in COOKIE_HOSTS) or
         (secondary_bindings and row.get('name') in SECONDARY_AUTH_NAMES and row.get('domain') in SECONDARY_COOKIE_HOSTS)))

def selected_records(profile_id,root=BRAVE_ROOT,*,secondary_bindings=False):
    if not isinstance(profile_id,str) or not re.fullmatch(r'Default|Profile [0-9]+',profile_id):raise Rejected('BRAVE_PROFILE_SELECTION_REQUIRED')
    directory=Path(root)/profile_id
    present=[p for p in (directory/'Network/Cookies',directory/'Cookies') if p.exists()]
    if len(present)!=1:raise Rejected('BRAVE_COOKIE_STORE_MISSING_OR_AMBIGUOUS')
    path=present[0]
    if any(p.is_symlink() for p in [path,*path.parents]):raise Rejected('BRAVE_COOKIE_PATH_UNSAFE')
    s=path.stat()
    if not stat.S_ISREG(s.st_mode) or s.st_uid!=os.geteuid() or s.st_size>128*1024*1024:raise Rejected('BRAVE_COOKIE_PATH_UNSAFE')
    scope='(host_key IN ('+','.join('?' for _ in COOKIE_HOSTS)+') AND name IN ('+','.join('?' for _ in AUTH_NAMES)+'))'
    parameters=COOKIE_HOSTS+AUTH_NAMES
    if secondary_bindings:
        scope+=' OR (host_key IN ('+','.join('?' for _ in SECONDARY_COOKIE_HOSTS)+') AND name IN ('+','.join('?' for _ in SECONDARY_AUTH_NAMES)+'))'
        parameters+=SECONDARY_COOKIE_HOSTS+SECONDARY_AUTH_NAMES
    where='('+scope+") AND path='/' AND (expires_utc=0 OR expires_utc>?)"
    now=int((time.time()+11644473600)*1000000)
    try:
        with sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1',uri=True,timeout=2) as connection:
            version=connection.execute("SELECT value FROM meta WHERE key='version'").fetchone()
            if version is None or str(version[0])!='24':raise Rejected('BRAVE_COOKIE_SCHEMA_UNSUPPORTED')
            rows=connection.execute('SELECT name,host_key,path,encrypted_value,is_secure FROM cookies WHERE '+where+' LIMIT 65',parameters+(now,)).fetchall()
    except Rejected:raise
    except (sqlite3.Error,OSError):raise Rejected('BRAVE_COOKIE_READ_ONLY_UNAVAILABLE') from None
    if not rows or len(rows)>64:raise Rejected('BRAVE_AUTH_COOKIE_RECORDS_UNAVAILABLE')
    records=[]
    for name,host,path,encrypted,secure in rows:
        if not isinstance(encrypted,bytes) or not encrypted.startswith(b'v10') or not 3<len(encrypted)<=16384 or (len(encrypted)-3)%16:raise Rejected('BRAVE_COOKIE_ENCRYPTION_UNSUPPORTED')
        if name.startswith(('__Secure-','__Host-')) and not secure:raise Rejected('BRAVE_AUTH_COOKIE_ATTRIBUTES_INVALID')
        records.append({'name':name,'domain':host,'path':path,'secure':'true' if secure else 'false','encrypted_value':base64.b64encode(encrypted).decode()})
    if not {'SID','HSID','SSID','APISID','SAPISID'}<=set(r['name'] for r in records):raise Rejected('BRAVE_REQUIRED_AUTH_COOKIES_MISSING')
    return {'schema_version':24,'records':records}

def prepare_bridge(state):
    directory=private_dir(state.path/'libexec',create=True);cache=private_dir(state.path/'compiler-cache',create=True)
    source=Path(__file__).with_name('brave_cookie_bridge.swift');target=directory/'brave-cookie-bridge';receipt=directory/'brave-bridge-build.json'
    if target.is_symlink() or receipt.is_symlink():raise Rejected('PERSONAL_PATH_UNSAFE')
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    if target.exists() and receipt.exists():
        old=read_private(receipt)
        if old.get('source_sha256')==digest and old.get('binary_sha256')==hashlib.sha256(target.read_bytes()).hexdigest():return target
    try:
        sdk=subprocess.run(['/usr/bin/xcrun','--sdk','macosx','--show-sdk-path'],capture_output=True,text=True,timeout=10,check=True).stdout.strip()
        compiler=subprocess.run(['/usr/bin/xcrun','--find','swiftc'],capture_output=True,text=True,timeout=10,check=True).stdout.strip()
        env={k:v for k,v in os.environ.items() if k in ('PATH','HOME','LANG','USER','LOGNAME')};env.update(TMPDIR=str(cache),CLANG_MODULE_CACHE_PATH=str(cache))
        result=subprocess.run([compiler,'-O','-sdk',sdk,'-target','arm64-apple-macosx14.0' if os.uname().machine=='arm64' else 'x86_64-apple-macosx14.0',
            '-module-cache-path',str(cache),str(source),'-o',str(target)],capture_output=True,timeout=60,env=env)
        if result.returncode:raise Rejected('BRAVE_COOKIE_BRIDGE_BUILD_FAILED')
    except Rejected:raise
    except Exception:raise Rejected('BRAVE_COOKIE_BRIDGE_BUILD_FAILED') from None
    target.chmod(0o700);write_private(receipt,{'source_sha256':digest,'binary_sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
    return target

def decrypt_records(state,payload,helper=None,*,secondary_bindings=False):
    if any(not permitted_record(row,secondary_bindings) for row in payload.get('records',[])):
        raise Rejected('BRAVE_COOKIE_RECORD_SCOPE_REJECTED')
    helper=helper or prepare_bridge(state)
    raw=json.dumps(payload,separators=(',',':')).encode()
    if len(raw)>262144:raise Rejected('BRAVE_COOKIE_PAYLOAD_LIMIT')
    try:
        r=subprocess.run([str(helper)],input=raw,capture_output=True,timeout=60,
            env={k:v for k,v in os.environ.items() if k in ('PATH','HOME','LANG','USER','LOGNAME')})
    except Exception:raise Rejected('BRAVE_COOKIE_BRIDGE_UNAVAILABLE') from None
    if r.returncode:
        code='BRAVE_COOKIE_BRIDGE_FAILED';status=None
        try:
            error=strict_json(r.stderr)
            if error.get('code') in {'BRAVE_SAFE_STORAGE_UNAVAILABLE','BRAVE_COOKIE_DECRYPTION_FAILED','BRAVE_COOKIE_HOST_BINDING_INVALID','BRAVE_COOKIE_ENCRYPTION_UNSUPPORTED'}:code=error['code']
            if type(error.get('os_status')) is int:status=error['os_status']
        except Exception:pass
        raise KeychainFailure(code,status)
    if r.stderr or len(r.stdout)>65536:raise Rejected('BRAVE_COOKIE_BRIDGE_RESPONSE_INVALID')
    try:cookies=strict_json(r.stdout)['cookies']
    except Exception:raise Rejected('BRAVE_COOKIE_BRIDGE_RESPONSE_INVALID') from None
    if not isinstance(cookies,list) or not 1<=len(cookies)<=64:raise Rejected('BRAVE_COOKIE_BRIDGE_RESPONSE_INVALID')
    for c in cookies:
        if not permitted_record(c,secondary_bindings) or type(c.get('secure')) is not bool or c['name'].startswith(('__Secure-','__Host-')) and not c['secure']:raise Rejected('BRAVE_COOKIE_BRIDGE_RESPONSE_INVALID')
    return cookies

def account_probe(cookies,account_id,host='notebook.google.com',sender_factory=FixedTLS):
    # One fixed-host homepage check; one HTTPS consumer-host rebrand handoff is allowed.
    for attempt in range(2):
        applicable={c['name']:c['value'] for c in sorted(cookies,key=lambda c:len(c['domain'])) if host==c['domain'].lstrip('.') or host.endswith('.'+c['domain'].lstrip('.'))}
        seed=Session(account_id,'unvalidated@example.invalid',applicable,'pending','1','pending',1,host).validate()
        sender=sender_factory(host)
        try:reply=sender.send('GET','/',dict(PAGE_FETCH_HEADERS,Cookie=seed.cookie_header(),**{'Accept-Encoding':'identity'}),None,15,2*1024*1024)
        except Exception:raise Rejected('BRAVE_ACCOUNT_VALIDATION_TRANSPORT_FAILED') from None
        finally:sender.close()
        if not isinstance(reply,HttpReply):raise Rejected('BRAVE_ACCOUNT_VALIDATION_RESPONSE_INVALID')
        if reply.status in (301,302,307,308) and attempt==0:
            target=urlsplit(reply.headers.get('location',''))
            if target.scheme=='https' and target.hostname in GOOGLE_HOSTS and target.port in (None,443) and target.path in ('','/') and not target.query and not target.fragment:
                host=target.hostname;continue
            failure=Rejected('BRAVE_ACCOUNT_REDIRECT_REJECTED')
            failure.diagnostics={'phase':'ACCOUNT_VALIDATION','http_status':reply.status,'redirect_host_allowed':target.hostname in GOOGLE_HOSTS,'redirect_is_signin':target.hostname=='accounts.google.com','home_path':target.path in ('','/'),'has_query':bool(target.query)}
            raise failure
        if reply.status!=200:raise Rejected('AUTHENTICATION_EXPIRED' if reply.status in (401,403) else 'BRAVE_ACCOUNT_VALIDATION_STATUS_REJECTED')
        if reply.headers.get('content-type','').split(';')[0].strip().lower()!='text/html' or reply.headers.get('content-encoding','identity').lower()!='identity' or len(reply.body)>2*1024*1024:raise Rejected('BRAVE_ACCOUNT_VALIDATION_RESPONSE_INVALID')
        try:return browser_session(reply.body.decode('utf-8'),cookies,'https://'+host+'/',account_id)
        except UnicodeError:raise Rejected('SESSION_REFRESH_STRUCTURE_CHANGED') from None
    raise Rejected('BRAVE_ACCOUNT_REDIRECT_REJECTED')

def connect(state,store,profile_id,consent,sender=None,reader=selected_records,decryptor=decrypt_records,probe=account_probe):
    if not consent:raise Rejected('EXISTING_BRAVE_ACCESS_APPROVAL_REQUIRED')
    if not profile_id:raise Rejected('BRAVE_PROFILE_SELECTION_REQUIRED')
    progress=LoginProgress(state,reset=True);progress.event('existing_session_access_started')
    store.probe()
    payload=reader(profile_id);progress.event('approved_cookie_records_read',record_count=len(payload.get('records',[])))
    cookies=decryptor(state,payload);progress.event('approved_records_decrypted_in_memory')
    try:session=probe(cookies,state.load()['account_id'],'notebook.google.com')
    except Rejected as error:
        progress.event('account_validation_failed',code=error.code);raise
    progress.event('http_account_validated')
    # A discovery decoder failure must not discard a validated login.
    store.save(session);progress.event('keychain_session_saved')
    with state.lock():
        c=state.load();c.update(authenticated=True,host=session.host,selected_notebook=None,query_permit=None,generation=c['generation']+1)
        state.save(c)
    # The browser-wide key is absent from this process and not part of Session.
    manager=seed_manager(store,session);transport=GeminiHTTPS(manager,{},timeout=15,sender=sender,validate_discovery=False)
    try:
        books=parse_discovery(transport.request(ReadRequest('rpc',LIST_RPC,'/',[None,1,None,[2]])))
        progress.event('discovery_completed',discovery_requests=1,notebook_count=len(books))
        with state.lock():
            c=state.load()
            write_private(state.path/'notebooks.json',{'account_id':c['account_id'],'notebooks':books})
            write_private(state.path/'existing-session-approval.json',{'method':'SCOPED_READ_ONLY_PERSONAL_PILOT','profile_id':profile_id,
                'profile_writes':False,'database_copied':False,'master_key_persisted':False,'discovery_requests':1})
        progress.event('authentication_complete')
        return {'status':'AUTHENTICATED','mode':'PERSONAL_LOCAL','method':'EXISTING_BRAVE_SCOPED_PILOT','account':session.expected_email,
            'storage':'MACOS_KEYCHAIN','discovery_requests':1,'notebooks':[{'notebook_id':b['notebook_id'],'title':b['title']} for b in books]}
    except Rejected as error:
        progress.event('discovery_failed_session_retained',code=error.code)
        error.diagnostics={'phase':'NOTEBOOK_DISCOVERY','authentication':'SUCCEEDED_KEYCHAIN_SAVED'}
        raise
    finally:transport.close()
