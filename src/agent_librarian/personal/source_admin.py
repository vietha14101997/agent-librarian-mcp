"""Closed CLI-only consumer-file API using the existing pinned Brave session.

Upload protocol reviewed in jacob-bd/gemini-notebook-mcp-cli, core/sources.py
at 8ac9728ec5b128b05077e9d7c4c8bb11b5830c61. No cookie export or upstream retries.
"""
import base64
from pathlib import Path
import time
import uuid
from ..gateway.common import Rejected,ident
from ..providers.gemini import GET_RPC,ReadRequest,parse_notebook
from ..providers.https_transport import rpc_result
from .brave_transport import BraveTransport,CONNECTION
from .state import read_private
from .ingestion import MAX_FILE,filename

REGISTER_RPC='o4cbdc'


def registration_params(notebook_id,name):
    return [[[filename(name)]],ident(notebook_id),[2],[1,None,None,None,None,None,None,None,None,None,[1]]]


class SourceAdmin:
    def __init__(self,reader,notebook_id):
        self.reader=reader;self.nb=ident(notebook_id)
        self.bridge=BraveTransport(reader.connection,reader.account_id,reader.expected_email,reader.notebooks,
            runner=reader.runner,disabled=reader.disabled)
        self.bridge.javascript=Path(__file__).with_name('brave_upload.js').read_text()

    def inventory(self,notebook_id):
        if notebook_id!=self.nb:raise Rejected('NOTEBOOK_NOT_ALLOWED')
        raw=self.reader.request(ReadRequest('rpc',GET_RPC,'/notebook/'+self.nb,[self.nb,None,[2],None,0]))
        parse_notebook(raw,self.nb) # Retain the reviewed identity/structure checks.
        sources=[]
        for row in raw[0][1] or []:
            name=row[1]
            if not isinstance(name,str) or len(name)>1024:raise Rejected('PROVIDER_STRUCTURE_INVALID')
            status=row[3][1] if len(row)>3 and isinstance(row[3],list) and len(row[3])>1 else None
            kind=row[2][4] if len(row)>2 and isinstance(row[2],list) and len(row[2])>4 else None
            sources.append({'id':ident(row[0][0] if isinstance(row[0],list) else row[0]),'title':name,
                            'status':status if type(status) is int else None,'source_type':kind if type(kind) is int else None})
        return sources

    def execute(self,operation,**values):
        rid=uuid.uuid4().hex;dispatched=False;done=False
        try:
            start=self.bridge._execute({'action':'start','id':rid,'expected_email':self.reader.expected_email,
                'operation':operation,'notebook_id':self.nb,'timeout_ms':30000,**values})
            if start.get('status')!='DISPATCHED':raise Rejected('IMPORT_RESPONSE_INVALID')
            dispatched=True;deadline=time.monotonic()+30
            while time.monotonic()<deadline:
                result=self.bridge._execute({'action':'poll','id':rid,'expected_email':self.reader.expected_email})
                if self.reader.disabled():raise Rejected('SERVICE_DISABLED')
                if result.get('status')=='PENDING':time.sleep(.2);continue
                done=True
                if result.get('status')!='DONE':raise Rejected('IMPORT_RESPONSE_INVALID')
                return result
            raise Rejected('IMPORT_OUTCOME_UNKNOWN')
        finally:
            if dispatched and not done:
                try:self.bridge._execute({'action':'cancel','id':rid,'expected_email':self.reader.expected_email})
                except Exception:pass

    def register(self,notebook_id,name):
        if notebook_id!=self.nb:raise Rejected('NOTEBOOK_NOT_ALLOWED')
        result=self.execute('register',params=registration_params(self.nb,name))
        raw=rpc_result(result['text'].encode(),REGISTER_RPC)
        for _ in range(8):
            if isinstance(raw,str):return ident(raw)
            if not isinstance(raw,list) or not raw:break
            raw=raw[0]
        raise Rejected('IMPORT_REGISTRATION_UNCERTAIN')

    def start_upload(self,notebook_id,name,size,source_id):
        if notebook_id!=self.nb or type(size) is not int or not 0<size<=MAX_FILE:raise Rejected('IMPORT_ARGUMENTS_INVALID')
        return self.execute('upload_start',filename=filename(name),size=size,source_id=ident(source_id))['upload_url']

    def stage(self,raw):
        if not isinstance(raw,bytes) or not 0<len(raw)<=MAX_FILE:raise Rejected('IMPORT_FILE_INVALID_OR_TOO_LARGE')
        token=uuid.uuid4().hex
        for offset in range(0,len(raw),49152):
            result=self.bridge._execute({'action':'stage','id':token,'expected_email':self.reader.expected_email,'offset':offset,
                'data':base64.b64encode(raw[offset:offset+49152]).decode(),'size':len(raw)})
            if result.get('status')!='STAGED' or result.get('bytes')!=min(len(raw),offset+49152):raise Rejected('IMPORT_STAGE_INVALID')
        return token

    def finalize(self,url,token,size):return self.execute('finalize',upload_url=url,token=token,size=size)
    def close(self):self.reader.close();self.bridge.close()


def browser_source_admin(state,notebook_id):
    from .storage import PersonalKeychainStore
    config=state.load()
    if not config['authenticated'] or (state.path/'DISABLED').exists():raise Rejected('AUTHENTICATION_REQUIRED')
    connection=read_private(state.path/CONNECTION);saved=PersonalKeychainStore(state).load()
    if connection.get('status')!='BROWSER_DISCOVERY_VERIFIED':raise Rejected('BROWSER_CONNECTION_REQUIRED')
    if saved.account_id!=config['account_id'] or connection.get('account_id')!=config['account_id']:raise Rejected('ACCOUNT_IDENTITY_MISMATCH')
    if notebook_id not in {b['notebook_id'] for b in state.inventory()['notebooks']}:raise Rejected('NOTEBOOK_NOT_DISCOVERED')
    reader=BraveTransport(connection,config['account_id'],saved.expected_email,{notebook_id:{'sources':{}}},
        disabled=lambda:not state.load()['authenticated'] or state.load()['generation']!=config['generation'] or (state.path/'DISABLED').exists())
    return SourceAdmin(reader,notebook_id)
