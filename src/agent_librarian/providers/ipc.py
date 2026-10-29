"""Closed Unix-domain research IPC; kernel peer identity, bounded frames, no TCP."""
import ctypes
import json
import os
from pathlib import Path
import socket
import stat
import struct
import sys
import threading
import uuid
from ..gateway.common import NAMES,Rejected,strict_json,MAX_RESPONSE

def peer_identity(sock):
    if sys.platform=='darwin':
        libc=ctypes.CDLL(None,use_errno=True);fn=libc.getpeereid
        fn.argtypes=[ctypes.c_int,ctypes.POINTER(ctypes.c_uint),ctypes.POINTER(ctypes.c_uint)];fn.restype=ctypes.c_int
        uid=ctypes.c_uint();gid=ctypes.c_uint()
        if fn(sock.fileno(),ctypes.byref(uid),ctypes.byref(gid))!=0:raise Rejected('PEER_IDENTITY_UNAVAILABLE')
        return uid.value,gid.value
    if sys.platform.startswith('linux') and hasattr(socket,'SO_PEERCRED'):
        _,uid,gid=struct.unpack('iII',sock.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,struct.calcsize('iII')))
        return uid,gid
    raise Rejected('PLATFORM_PEER_IDENTITY_UNSUPPORTED')

def socket_path(path):
    p=Path(path).absolute()
    if not str(p) or len(os.fsencode(p))>100 or any(x.is_symlink() for x in [p,*p.parents]):
        raise Rejected('IPC_PATH_UNSAFE_OR_TOO_LONG')
    return p

def read_frame(conn,limit=65536):
    data=bytearray()
    while True:
        block=conn.recv(min(4096,limit+1-len(data)))
        if not block:raise Rejected('IPC_CONNECTION_CLOSED')
        data.extend(block)
        if len(data)>limit:raise Rejected('IPC_FRAME_LIMIT')
        if b'\n' in block:
            if not data.endswith(b'\n') or data.count(b'\n')!=1:raise Rejected('IPC_FRAME_INVALID')
            try:return strict_json(data)
            except (ValueError,UnicodeError,RecursionError):raise Rejected('IPC_FRAME_INVALID') from None

def send_frame(conn,value,limit=MAX_RESPONSE):
    try:data=json.dumps(value,allow_nan=False,separators=(',',':')).encode()+b'\n'
    except (ValueError,TypeError,RecursionError):raise Rejected('IPC_RESPONSE_INVALID') from None
    if len(data)>limit:raise Rejected('IPC_FRAME_LIMIT')
    conn.sendall(data)

class IPCResearchProvider:
    """Agent-side client; never receives a credential-store path or credential value."""
    def __init__(self,path,service_uid,client_id,account_id,timeout=2):
        self.path=socket_path(path);self.service_uid=service_uid;self.client_id=client_id
        self.account_id=account_id;self.timeout=timeout;self.closed=False;self.active=None;self.lock=threading.Lock()
    def _call(self,name,args):
        with self.lock:
            if self.closed:raise Rejected('SERVICE_DISABLED')
            conn=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);self.active=conn
        try:
            conn.settimeout(self.timeout);conn.connect(str(self.path))
            if peer_identity(conn)[0]!=self.service_uid:raise Rejected('SERVICE_PRINCIPAL_MISMATCH')
            rid=uuid.uuid4().hex
            send_frame(conn,{'version':1,'request_id':rid,'client_id':self.client_id,'operation':name,'arguments':args},65536)
            response=read_frame(conn,MAX_RESPONSE)
            if not isinstance(response,dict) or set(response)!={'version','request_id','account_id','result'} or response['version']!=1 or response['request_id']!=rid:
                raise Rejected('IPC_RESPONSE_INVALID')
            if response['account_id']!=self.account_id:raise Rejected('ACCOUNT_IDENTITY_MISMATCH')
            safe=response['result']
            if not isinstance(safe,dict):raise Rejected('IPC_RESPONSE_INVALID')
            if safe.get('status')!='OK':
                failure=Rejected(safe.get('code') if safe.get('code') in SAFE_ERRORS else 'PROVIDER_FAILURE')
                if safe.get('outcome')=='UNKNOWN':failure.outcome='UNKNOWN'
                raise failure
            if name==NAMES[0]:data={'notebooks':[{'id':b['notebook_id'],'title':b['title']} for b in safe['notebooks']]}
            elif name==NAMES[1]:data={'notebook_id':safe['notebook_id'],'title':safe['title'],'sources':[{'id':s['source_id'],'title':s['title']} for s in safe['sources']]}
            elif name==NAMES[2]:data={'notebook_id':safe['notebook_id'],'answer':safe['answer'],'citations':[{k:v for k,v in c.items() if k in ('source_id','citation_number','title','cited_text') and v is not None} for c in safe['citations']]}
            else:
                data={'notebook_id':safe['notebook_id'],'source_id':safe['source_id'],'title':safe['title'],'content':safe['content']}
                if 'offset' in safe:data['source_page']={k:safe[k] for k in ('offset','total_chars','truncated','next_offset')}
            return {'account_id':self.account_id,'status':'ok','provider_kind':'IPC_RESEARCH_SERVICE' if safe.get('provider')=='GEMINI_HTTPS_UNVERIFIED' else 'IPC_SYNTHETIC_SERVICE','data':data}
        except socket.timeout:raise Rejected('PROVIDER_TIMEOUT_OUTCOME_UNKNOWN') from None
        except (OSError,KeyError,TypeError,ValueError):raise Rejected('IPC_SERVICE_UNAVAILABLE_OR_INVALID') from None
        finally:
            conn.close()
            with self.lock:
                if self.active is conn:self.active=None
    def list_notebooks(self):return self._call(NAMES[0],{})
    def get_notebook(self,notebook_id):return self._call(NAMES[1],{'notebook_id':notebook_id})
    def query(self,notebook_id,query,source_ids):return self._call(NAMES[2],{'notebook_id':notebook_id,'query':query,'source_ids':source_ids})
    def get_source(self,notebook_id,source_id):return self._call(NAMES[3],{'notebook_id':notebook_id,'source_id':source_id})
    def get_source_page(self,notebook_id,source_id,offset=0,max_chars=16000):return self._call(NAMES[3],{'notebook_id':notebook_id,'source_id':source_id,'offset':offset,'max_chars':max_chars})
    def close(self):
        with self.lock:
            self.closed=True
            if self.active:
                try:self.active.shutdown(socket.SHUT_RDWR)
                except OSError:pass

SAFE_ERRORS={'FORBIDDEN_OPERATION','NOTEBOOK_NOT_ALLOWED','SOURCE_NOT_ALLOWED','QUERY_INVALID','INVALID_ARGUMENTS',
    'ACCOUNT_IDENTITY_MISMATCH','AUTHENTICATION_EXPIRED','SERVICE_DISABLED','BUSY','QUERY_DESTINATION_REJECTED',
    'PROVIDER_TIMEOUT_OUTCOME_UNKNOWN','PROVIDER_PROTOCOL_ERROR','PROVIDER_STRUCTURE_INVALID','UNIMPLEMENTED_SOURCE_GAP',
    'PROVIDER_NOTEBOOK_MISMATCH','PROVIDER_SOURCE_MISMATCH','PROVIDER_CITATION_NOT_ALLOWED','PROVIDER_CONTENT_REJECTED',
    'CALLER_PRINCIPAL_REJECTED','IPC_FRAME_INVALID','IPC_REQUEST_INVALID','IPC_CLIENT_ID_REJECTED','SERVICE_POLICY_CHANGED'}

SAFE_ERRORS.update({'QUERY_OUTCOME_UNKNOWN','PROVIDER_TIMEOUT','HTTP_TRANSPORT_FAILURE','HTTP_STATUS_REJECTED',
    'HTTP_REDIRECT_REJECTED','HTTP_RESPONSE_INVALID','HTTP_RESPONSE_LIMIT','HTTP_CONTENT_TYPE_REJECTED',
    'HTTP_ENCODING_REJECTED','SESSION_REFRESH_STRUCTURE_CHANGED','CREDENTIAL_STORE_UNAVAILABLE',
    'CREDENTIAL_STORE_INVALID','SESSION_INVALID','PROVIDER_RPC_MISMATCH'})
