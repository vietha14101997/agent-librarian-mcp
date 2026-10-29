"""Restricted provider service. Protected live construction is only through runtime.py."""
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import socket
import stat
from ..gateway.common import Rejected,strict_json,load_policy
from ..gateway.policy import Gateway
from .fake import FakeProvider
from .gemini import AccountCapability,GeminiResearchProvider,bounded
from .gemini_mock import MockGeminiTransport
from .ipc import peer_identity,socket_path,read_frame,send_frame

def owned_json(path,private=False):
    p=Path(path)
    if any(x.is_symlink() for x in [p,*p.parents]):raise Rejected('SERVICE_FILE_UNSAFE')
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as f:
        s=os.fstat(f.fileno())
        if not stat.S_ISREG(s.st_mode) or s.st_uid not in (0,os.geteuid()) or s.st_mode&0o022 or s.st_size>131072:
            raise Rejected('SERVICE_FILE_UNSAFE')
        if private and (s.st_uid!=os.geteuid() or s.st_mode&0o077):raise Rejected('SYNTHETIC_STORE_PERMISSIONS_INVALID')
        raw=f.read(131073)
    if len(raw)>131072:raise Rejected('SERVICE_FILE_LIMIT')
    return strict_json(raw),hashlib.sha256(raw).hexdigest()

class SecretConfinement:
    """Exact known-canary redaction plus normal safe projection, not general DLP."""
    def __init__(self,provider,secret):self.provider=provider;self.secret=secret
    def scrub(self,value):
        bounded(value)
        def walk(x):
            if isinstance(x,str):
                secrets=self.secret() if callable(self.secret) else (self.secret,)
                for secret in secrets:
                    if secret:x=x.replace(secret,'[REDACTED]')
                return x
            if isinstance(x,list):return [walk(v) for v in x]
            if isinstance(x,dict):return {walk(k):walk(v) for k,v in x.items()}
            return x
        return walk(value)
    def list_notebooks(self):return self.scrub(self.provider.list_notebooks())
    def get_notebook(self,notebook_id):return self.scrub(self.provider.get_notebook(notebook_id))
    def query(self,notebook_id,query,source_ids):return self.scrub(self.provider.query(notebook_id,query,source_ids))
    def get_source(self,notebook_id,source_id):return self.scrub(self.provider.get_source(notebook_id,source_id))
    def close(self):self.provider.close()

class ProviderService:
    def __init__(self,path,policy,fixture,canary_store,allowed_uid,client_id,adapter='gemini-mock',*,provider=None):
        if type(allowed_uid) is not int or allowed_uid<0 or not re.fullmatch('[A-Za-z0-9_-]{1,64}',client_id):raise Rejected('SERVICE_PRINCIPAL_INVALID')
        self.path=socket_path(path);self.policy_path=Path(policy)
        _,self.policy_digest=owned_json(policy)
        config=load_policy(policy)
        if provider is None:
            store,_=owned_json(canary_store,private=True)
            if not isinstance(store,dict) or set(store)!={'synthetic_only','account_id','secret'} or store['synthetic_only'] is not True:
                raise Rejected('SYNTHETIC_STORE_REQUIRED')
            secret=store['secret']
            if not isinstance(secret,str) or not secret.startswith('SYNTHETIC_') or not 16<=len(secret)<=128:
                raise Rejected('SYNTHETIC_STORE_REQUIRED')
            if store['account_id']!=config['account_id']:raise Rejected('ACCOUNT_IDENTITY_MISMATCH')
            fixture_data,_=owned_json(fixture)
            if adapter=='gemini-mock':
                backend=GeminiResearchProvider(MockGeminiTransport(fixture_data,store['account_id'],secret,config['timeout_seconds']),
                    AccountCapability(store['account_id']),config['notebooks'],config['query_max_chars'])
            elif adapter=='fake':backend=FakeProvider(fixture,config['timeout_seconds'],config['account_id'])
            else:raise Rejected('BLOCKED_PENDING_ISOLATED_RUNTIME')
            provider=SecretConfinement(backend,secret)
        self.gateway=Gateway(policy,fixture,self.path.parent,provider=provider)
        self.allowed_uid=allowed_uid;self.client_id=client_id;self.timeout=min(5,config['timeout_seconds']+1)
        self.listener=None;self.connection=None;self.stopped=False;self.bound_identity=None

    def handle(self,request,uid):
        rid=None
        try:
            if self.stopped:raise Rejected('SERVICE_DISABLED')
            if uid!=self.allowed_uid:raise Rejected('CALLER_PRINCIPAL_REJECTED')
            if not isinstance(request,dict) or set(request)!={'version','request_id','client_id','operation','arguments'}:
                raise Rejected('IPC_REQUEST_INVALID')
            if type(request['version']) is not int or request['version']!=1 or not isinstance(request['request_id'],str) or not re.fullmatch('[a-f0-9]{32}',request['request_id']):raise Rejected('IPC_REQUEST_INVALID')
            rid=request['request_id']
            if request['client_id']!=self.client_id:raise Rejected('IPC_CLIENT_ID_REJECTED')
            if not isinstance(request['operation'],str):raise Rejected('IPC_REQUEST_INVALID')
            _,digest=owned_json(self.policy_path)
            if digest!=self.policy_digest:raise Rejected('SERVICE_POLICY_CHANGED')
            result=self.gateway.call(request['operation'],request['arguments'])
        except Rejected as e:result={'status':'ERROR','code':e.code}
        except Exception:result={'status':'ERROR','code':'SERVICE_REQUEST_FAILED'}
        return {'version':1,'request_id':rid,'account_id':self.gateway.policy['account_id'] if uid==self.allowed_uid else '', 'result':result}

    def bind(self):
        parent=self.path.parent
        s=parent.stat()
        if s.st_uid!=os.geteuid() or s.st_mode&0o022 or self.path.exists():raise Rejected('IPC_DIRECTORY_UNSAFE_OR_SOCKET_EXISTS')
        self.listener=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        old=os.umask(0o117)
        try:self.listener.bind(str(self.path))
        finally:os.umask(old)
        s=self.path.stat();self.bound_identity=(s.st_dev,s.st_ino)
        self.listener.listen(4);self.listener.settimeout(.1)

    def run(self):
        self.bind()
        try:
            while not self.stopped:
                try:conn,_=self.listener.accept()
                except socket.timeout:continue
                except OSError:
                    if self.stopped:break
                    raise
                self.connection=conn
                with conn:
                    conn.settimeout(self.timeout)
                    try:
                        uid,_=peer_identity(conn)
                        # Do not read a request body from an unauthorized kernel principal.
                        request=read_frame(conn) if uid==self.allowed_uid else None
                        response=self.handle(request,uid)
                    except Rejected as e:response={'version':1,'request_id':None,'account_id':'','result':{'status':'ERROR','code':e.code}}
                    except Exception:response={'version':1,'request_id':None,'account_id':'','result':{'status':'ERROR','code':'IPC_REQUEST_FAILED'}}
                    try:send_frame(conn,response)
                    except (OSError,Rejected):pass
                self.connection=None
        finally:self.close()

    def close(self):
        self.stopped=True;self.gateway.close()
        if self.connection:
            try:self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:pass
        if self.listener:self.listener.close()
        if self.bound_identity:
            try:
                s=self.path.lstat()
                if stat.S_ISSOCK(s.st_mode) and (s.st_dev,s.st_ino)==self.bound_identity:self.path.unlink()
            except FileNotFoundError:pass

def run_service(**kwargs):
    service=ProviderService(**kwargs)
    def stop(_s,_f):service.close();raise SystemExit(0)
    previous=signal.signal(signal.SIGTERM,stop)
    try:service.run()
    finally:service.close();signal.signal(signal.SIGTERM,previous)
