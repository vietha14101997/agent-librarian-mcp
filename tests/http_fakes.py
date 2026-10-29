"""Synthetic HTTP/page/session fixtures. Contains no live account or credential."""
from dataclasses import replace
import json
import time
from urllib.parse import parse_qs,urlsplit
from agent_librarian.providers.gemini import ReadRequest,LIST_RPC
from agent_librarian.providers.gemini_mock import MockGeminiTransport
from agent_librarian.providers.https_transport import HttpReply,QUERY_ENDPOINT
from agent_librarian.providers.session import Session

SECRET='SYNTHETIC_CANARY_OSS03'
def session():return Session('synthetic-research-01','research@example.invalid',{'SID':SECRET},'SYNTHETIC_CSRF_03','-12345','synthetic_build_03',1)
class MemoryStore:
    def __init__(self,value=None):self.value=value or session();self.saved=0;self.deleted=False
    def load(self):return self.value
    def save(self,value):self.value=value;self.saved+=1
    def delete(self):self.deleted=True
class ReplayHTTP:
    def __init__(self,fixture):
        self.mock=MockGeminiTransport(fixture,'synthetic-research-01',SECRET);self.calls=[];self.next_reply=None;self.closed=False
    def send(self,method,path,headers,body,timeout,limit):
        self.calls.append((method,path,headers,body,timeout,limit))
        if self.next_reply is not None:
            reply=self.next_reply;self.next_reply=None
            if isinstance(reply,Exception):raise reply
            return reply
        if method=='GET':
            html=json.dumps({'oPEP7c':'research@example.invalid','SNlM0e':'SYNTHETIC_CSRF_03','FdrFJe':'-12345','cfb2h':'synthetic_build_03'})
            return HttpReply(200,{'content-type':'text/html'},('<script>WIZ_global_data='+html+';</script>').encode())
        query=parse_qs(urlsplit(path).query);form=parse_qs(body.decode());envelope=json.loads(form['f.req'][0])
        if path.startswith(QUERY_ENDPOINT):
            params=json.loads(envelope[1]);raw=self.mock.request(ReadRequest('stream',QUERY_ENDPOINT,'/notebook/notebook-approved',params))
        else:
            item=envelope[0][0];rpc=item[0];params=json.loads(item[1]);source=query['source-path'][0]
            value=self.mock.request(ReadRequest('rpc',rpc,source,params))
            frame=json.dumps([['wrb.fr',rpc,json.dumps(value)]]);raw=")]}'\n"+str(len(frame.encode()))+'\n'+frame+'\n'
        return HttpReply(200,{'content-type':'application/json; charset=utf-8'},raw.encode())
    def close(self):self.closed=True
