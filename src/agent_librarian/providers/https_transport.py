"""Fixed-host verified TLS transport; only four source-derived research requests.

Wire envelopes adapted from upstream 8ac9728ec5b128b05077e9d7c4c8bb11b5830c61
core/base.py and core/conversation.py. Copyright (c) 2025 Jacob Ben David (MIT).
No upstream runtime, cookies/profile discovery, redirects, proxies or retries.
"""
from dataclasses import dataclass,field
import http.client
import json
import re
import socket
import ssl
import time
from urllib.parse import urlencode
from ..gateway.common import Rejected,strict_json,ident,URL_PATH
from .gemini import LIST_RPC,GET_RPC,SOURCE_RPC,QUERY_ENDPOINT,bounded,parse_discovery,ReadRequest
from .session import GOOGLE_HOSTS,page_session

RPC_PATH='/_/LabsTailwindUi/data/batchexecute'
@dataclass(repr=False,frozen=True)
class HttpReply:
    status:int
    headers:dict=field(repr=False)
    body:bytes=field(repr=False)

class FixedTLS:
    """Internal sender. Its only host comes from protected startup configuration."""
    def __init__(self,host):
        if host not in GOOGLE_HOSTS:raise Rejected('HTTP_DESTINATION_REJECTED')
        self.host=host;self.context=ssl.create_default_context();self.active=None
    def send(self,method,path,headers,body,timeout,limit):
        if method not in ('GET','POST') or not path.startswith('/') or path.startswith('//') or '\r' in path or '\n' in path:raise Rejected('HTTP_DESTINATION_REJECTED')
        started=time.monotonic();conn=http.client.HTTPSConnection(self.host,timeout=timeout,context=self.context);self.active=conn
        try:
            conn.request(method,path,body=body,headers=headers);response=conn.getresponse()
            content_length=response.getheader('Content-Length')
            if content_length is not None and (not content_length.isdigit() or int(content_length)>limit):raise Rejected('HTTP_RESPONSE_LIMIT')
            result=bytearray()
            while True:
                remaining=timeout-(time.monotonic()-started)
                if remaining<=0:raise TimeoutError()
                if conn.sock is not None:conn.sock.settimeout(remaining)
                block=response.read1(min(8192,limit+1-len(result)))
                if not block:break
                result.extend(block)
                if len(result)>limit:raise Rejected('HTTP_RESPONSE_LIMIT')
            # Duplicate security-sensitive headers fail instead of being collapsed.
            values={}
            for k,v in response.getheaders():
                key=k.lower()
                if key in values and key in ('content-type','content-length','content-encoding'):raise Rejected('HTTP_RESPONSE_INVALID')
                values[key]=v
            return HttpReply(response.status,values,bytes(result))
        finally:
            conn.close()
            if self.active is conn:self.active=None
    def close(self):
        if self.active:self.active.close()

def frames(body):
    try:stream=body.decode('utf-8')
    except UnicodeError:raise Rejected('PROVIDER_PROTOCOL_ERROR') from None
    if not stream.startswith(")]}'"):raise Rejected('PROVIDER_PROTOCOL_ERROR')
    lines=iter(stream[4:].splitlines())
    for line in lines:
        line=line.strip()
        if not line:continue
        if line.isdigit():
            if len(line)>8:raise Rejected('PROVIDER_PROTOCOL_ERROR')
            count=int(line);line=next(lines,'')
            if count!=len(line.encode()):raise Rejected('PROVIDER_PROTOCOL_ERROR')
        try:value=strict_json(line)
        except (ValueError,RecursionError):raise Rejected('PROVIDER_PROTOCOL_ERROR') from None
        bounded(value)
        if not isinstance(value,list):raise Rejected('UNIMPLEMENTED_SOURCE_GAP')
        yield value

def rpc_result(body,method):
    results=[]
    for frame in frames(body):
        for item in frame:
            if not isinstance(item,list) or len(item)<3 or item[0]!='wrb.fr':continue
            if item[1]!=method:raise Rejected('PROVIDER_RPC_MISMATCH')
            if len(item)>5 and isinstance(item[5],list) and item[5]:
                raise Rejected('AUTHENTICATION_EXPIRED' if item[5][0]==16 else 'PROVIDER_PROTOCOL_ERROR')
            if not isinstance(item[2],str):raise Rejected('UNIMPLEMENTED_SOURCE_GAP')
            try:data=strict_json(item[2])
            except (ValueError,RecursionError):raise Rejected('PROVIDER_PROTOCOL_ERROR') from None
            results.append(bounded(data))
    if len(results)!=1:raise Rejected('UNIMPLEMENTED_SOURCE_GAP')
    return results[0]

class GeminiHTTPS:
    provider_kind='GEMINI_HTTPS_UNVERIFIED'
    def __init__(self,sessions,notebooks,timeout=10,sender=None,disabled=lambda:False,validate_discovery=True):
        if not .05<=timeout<=30:raise Rejected('HTTP_CONFIGURATION_INVALID')
        self.sessions=sessions;self.notebooks=notebooks;self.timeout=timeout
        self.sender=sender if sender is not None else FixedTLS(sessions.host)
        self.disabled=disabled;self.closed=False;self.reqid=100000;self.validate_discovery=validate_discovery
    def _check(self):
        if self.closed or self.disabled():raise Rejected('SERVICE_DISABLED')
    def _headers(self,s):
        return {'Content-Type':'application/x-www-form-urlencoded;charset=UTF-8','Origin':'https://'+s.host,
            'Referer':'https://'+s.host+'/','X-Same-Domain':'1','X-Goog-Csrf-Token':s.csrf,
            'Cookie':s.cookie_header(),'Accept-Encoding':'identity',
            'User-Agent':'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
    def _http(self,method,path,s,body=None,html=False,query=False):
        self._check();limit=2*1024*1024 if html else 131072
        try:r=self.sender.send(method,path,self._headers(s),body,self.timeout,limit)
        except Rejected:raise
        except (TimeoutError,socket.timeout):raise Rejected('PROVIDER_TIMEOUT_OUTCOME_UNKNOWN' if query else 'PROVIDER_TIMEOUT') from None
        except (OSError,http.client.HTTPException,ssl.SSLError):raise Rejected('QUERY_OUTCOME_UNKNOWN' if query else 'HTTP_TRANSPORT_FAILURE') from None
        except Exception:raise Rejected('QUERY_OUTCOME_UNKNOWN' if query else 'HTTP_TRANSPORT_FAILURE') from None
        self._check()
        if not isinstance(r,HttpReply) or type(r.status) is not int or not isinstance(r.headers,dict) or not isinstance(r.body,bytes):raise Rejected('HTTP_RESPONSE_INVALID')
        if len(r.body)>limit:raise Rejected('HTTP_RESPONSE_LIMIT')
        if r.status in (401,403):self.sessions.invalidate();raise Rejected('AUTHENTICATION_EXPIRED')
        if 300<=r.status<400:raise Rejected('HTTP_REDIRECT_REJECTED')
        if r.status!=200:raise Rejected('QUERY_OUTCOME_UNKNOWN' if query else 'HTTP_STATUS_REJECTED')
        content_type=r.headers.get('content-type','').split(';')[0].strip().lower()
        if content_type not in (('text/html',) if html else ('application/json','application/json+protobuf')):raise Rejected('HTTP_CONTENT_TYPE_REJECTED')
        if r.headers.get('content-encoding','identity').lower()!='identity':raise Rejected('HTTP_ENCODING_REJECTED')
        return r.body
    def _rpc(self,s,method,path,params):
        fields={'rpcids':method,'source-path':path,'bl':s.build_label,'hl':'en','rt':'c','f.sid':s.session_id}
        envelope=[[[method,json.dumps(params,separators=(',',':'),ensure_ascii=False),None,'generic']]]
        body=(urlencode({'f.req':json.dumps(envelope,separators=(',',':'),ensure_ascii=False),'at':s.csrf})+'&').encode()
        try:return rpc_result(self._http('POST',RPC_PATH+'?'+urlencode(fields),s,body),method)
        except Rejected as e:
            if e.code=='AUTHENTICATION_EXPIRED':self.sessions.invalidate()
            raise
    def _refresh(self,old,now):
        # No cookie rotation or browser recovery: unavailable/expired sessions require human action.
        html=self._http('GET','/',old,html=True)
        try:page=html.decode('utf-8')
        except UnicodeError:raise Rejected('SESSION_REFRESH_STRUCTURE_CHANGED') from None
        new=page_session(page,old,now)
        if self.validate_discovery:parse_discovery(self._rpc(new,LIST_RPC,'/',[None,1,None,[2]]))
        return new
    def account_identity(self):
        self._check();return self.sessions.ensure(self._refresh).account_id
    def _allowed(self,r):
        if not isinstance(r,ReadRequest):raise Rejected('HTTP_OPERATION_REJECTED')
        if r.kind=='rpc' and r.method==LIST_RPC and r.path=='/' and r.params==[None,1,None,[2]]:return
        if r.kind=='rpc' and r.method==GET_RPC:
            nb=r.path.removeprefix('/notebook/')
            if nb in self.notebooks and r.path=='/notebook/'+nb and r.params==[nb,None,[2],None,0]:return
        if r.kind=='rpc' and r.method==SOURCE_RPC:
            for book in self.notebooks.values():
                for sid in book['sources']:
                    if r.path=='/' and r.params==[[sid],[2],[2]]:return
        if r.kind=='stream' and r.method==QUERY_ENDPOINT:
            nb=r.path.removeprefix('/notebook/');p=r.params
            if nb not in self.notebooks or r.path!='/notebook/'+nb or not isinstance(p,list) or len(p)!=5:raise Rejected('HTTP_OPERATION_REJECTED')
            sources=[[[s]] for s in self.notebooks[nb]['sources']]
            if (isinstance(p[0],list) and p[0] and all(s in sources for s in p[0]) and len(p[0])<=100
                and isinstance(p[1],str) and p[1].strip() and len(p[1])<=4000 and not URL_PATH.search(p[1])
                and p[2] is None and p[3]==[2,None,[1]] and isinstance(p[4],str)
                and re.fullmatch('[a-f0-9-]{36}',p[4])):return
        raise Rejected('HTTP_OPERATION_REJECTED')
    def request(self,r):
        self._check();self._allowed(r);s=self.sessions.ensure(self._refresh)
        if r.kind=='rpc':return self._rpc(s,r.method,r.path,r.params)
        self.reqid+=100000
        fields={'bl':s.build_label,'hl':'en','_reqid':str(self.reqid),'rt':'c','f.sid':s.session_id}
        body=(urlencode({'f.req':json.dumps([None,json.dumps(r.params,separators=(',',':'),ensure_ascii=False)],separators=(',',':')),'at':s.csrf})+'&').encode()
        raw=self._http('POST',QUERY_ENDPOINT+'?'+urlencode(fields),s,body,query=True)
        try:return raw.decode('utf-8')
        except UnicodeError:
            failure=Rejected('PROVIDER_PROTOCOL_ERROR');failure.outcome='UNKNOWN';raise failure from None
    def invalidate_auth(self):self.sessions.invalidate()
    def close(self):self.closed=True;self.sender.close();self.sessions.close()
