"""Restricted consumer Notebook adapter; injected transport only, no HTTP/auth discovery.

Protocol layouts adapted from jacob-bd/gemini-notebook-mcp-cli at
8ac9728ec5b128b05077e9d7c4c8bb11b5830c61. Copyright (c) 2025 Jacob Ben David.
MIT notice in THIRD_PARTY_NOTICES.md. No upstream client/auth runtime is imported.
"""
from dataclasses import dataclass
import json
from typing import Protocol
import uuid
from ..gateway.common import Rejected, ident, text, URL_PATH, strict_json

LIST_RPC='wXbhsf'
GET_RPC='rLM1Ne'
SOURCE_RPC='hizoJc'
QUERY_ENDPOINT='/_/LabsTailwindUi/data/google.internal.labs.tailwind.orchestration.v1.LabsTailwindOrchestrationService/GenerateFreeFormStreamed'

@dataclass(frozen=True)
class AccountCapability:
    """Service-injected account binding, not a caller-supplied credential/token."""
    account_id: str

@dataclass(frozen=True)
class ReadRequest:
    kind: str
    method: str
    path: str
    params: list

class AuthenticatedReadTransport(Protocol):
    """Implementations own authentication. Return decoded RPC data or stream text.

    Protected-runtime HTTPS is implemented separately; mock transport is the default.
    """
    def account_identity(self) -> str: ...
    def request(self,request:ReadRequest): ...
    def close(self): ...

def bounded(value):
    try:encoded=json.dumps(value,allow_nan=False)
    except (ValueError,TypeError,RecursionError):raise Rejected('PROVIDER_PROTOCOL_ERROR') from None
    if len(encoded.encode())>131072:raise Rejected('PROVIDER_RESPONSE_LIMIT')
    stack=[(value,0)];count=0
    while stack:
        item,depth=stack.pop();count+=1
        if depth>24 or count>10000:raise Rejected('PROVIDER_RESPONSE_LIMIT')
        if isinstance(item,list):stack.extend((x,depth+1) for x in item)
        elif isinstance(item,dict):stack.extend((x,depth+1) for x in item.values())
    return value

def notebook_row(row):
    if not isinstance(row,list) or len(row)<3 or not isinstance(row[1],list):raise Rejected('UNIMPLEMENTED_SOURCE_GAP')
    nb=ident(row[2]);title=text(row[0]);sources=[];seen=set()
    if len(row[1])>1000:raise Rejected('PROVIDER_RESPONSE_LIMIT')
    for src in row[1]:
        if not isinstance(src,list) or len(src)<2 or not isinstance(src[0],list) or not src[0]:raise Rejected('UNIMPLEMENTED_SOURCE_GAP')
        sid=ident(src[0][0])
        if sid in seen:raise Rejected('PROVIDER_STRUCTURE_INVALID')
        seen.add(sid);sources.append({'id':sid,'title':text(src[1])})
    return {'notebook_id':nb,'title':title,'sources':sources}

def parse_discovery(raw):
    bounded(raw)
    if raw==[]:return []
    if not isinstance(raw,list) or len(raw)!=1 or not isinstance(raw[0],list):raise Rejected('UNIMPLEMENTED_SOURCE_GAP')
    if len(raw[0])>1000:raise Rejected('PROVIDER_RESPONSE_LIMIT')
    return [notebook_row(row) for row in raw[0]]

def parse_notebook(raw,expected):
    bounded(raw)
    if not isinstance(raw,list) or len(raw)!=1:raise Rejected('UNIMPLEMENTED_SOURCE_GAP')
    book=notebook_row(raw[0])
    if book['notebook_id']!=expected:raise Rejected('PROVIDER_NOTEBOOK_MISMATCH')
    return book

def parse_source(raw,expected):
    bounded(raw)
    if not isinstance(raw,list) or len(raw)<4 or not isinstance(raw[0],list) or len(raw[0])<2:
        raise Rejected('UNIMPLEMENTED_SOURCE_GAP')
    meta=raw[0]
    if not isinstance(meta[0],list) or not meta[0] or meta[0][0]!=expected:raise Rejected('PROVIDER_SOURCE_MISMATCH')
    if not isinstance(raw[3],list) or not raw[3] or not isinstance(raw[3][0],list):raise Rejected('UNIMPLEMENTED_SOURCE_GAP')
    # Upstream core/sources.py:get_source_fulltext and _extract_all_text.
    parts=[]
    def collect(items):
        for item in items:
            if isinstance(item,str) and item:parts.append(item)
            elif isinstance(item,list):collect(item)
    for block in raw[3][0]:
        if not isinstance(block,list):raise Rejected('UNIMPLEMENTED_SOURCE_GAP')
        collect(block)
    return {'source_id':expected,'title':text(meta[1]),'content':text('\n\n'.join(parts))}

def cited_text(detail):
    """Known upstream direct/wrapped text segments only; tables remain unverified."""
    parts=[]
    if len(detail)<=4 or not isinstance(detail[4],list):return None
    for element in detail[4]:
        if not isinstance(element,list) or not element:continue
        segments=[element] if isinstance(element[0],(int,float)) else element
        for segment in segments:
            if not isinstance(segment,list) or len(segment)<3 or not isinstance(segment[0],(int,float)) or not isinstance(segment[2],list):continue
            for group in segment[2]:
                if not isinstance(group,list):continue
                for inner in group:
                    if isinstance(inner,list) and len(inner)>2 and isinstance(inner[2],str) and inner[2].strip():parts.append(inner[2].strip())
    return text(' '.join(parts)) if parts else None

def parse_query(stream,allowed_sources):
    if not isinstance(stream,str):raise Rejected('UNIMPLEMENTED_SOURCE_GAP')
    if len(stream.encode())>131072:raise Rejected('PROVIDER_RESPONSE_LIMIT')
    lines=iter(stream[4:].splitlines() if stream.startswith(")]}'") else stream.splitlines())
    best=None
    for line in lines:
        line=line.strip()
        if not line:continue
        if line.isdigit():
            size=int(line);line=next(lines,'')
            if size!=len(line.encode()):raise Rejected('PROVIDER_PROTOCOL_ERROR')
        try:chunk=strict_json(line)
        except (ValueError,UnicodeError,RecursionError):raise Rejected('PROVIDER_PROTOCOL_ERROR') from None
        bounded(chunk)
        if not isinstance(chunk,list):raise Rejected('UNIMPLEMENTED_SOURCE_GAP')
        for item in chunk:
            if not isinstance(item,list) or len(item)<3 or item[0]!='wrb.fr':continue
            if item[2] is None:
                code=item[5][0] if len(item)>5 and isinstance(item[5],list) and item[5] else None
                raise Rejected('AUTHENTICATION_EXPIRED' if code==16 else 'PROVIDER_PROTOCOL_ERROR')
            if not isinstance(item[2],str):raise Rejected('UNIMPLEMENTED_SOURCE_GAP')
            try:inner=strict_json(item[2])
            except (ValueError,RecursionError):raise Rejected('PROVIDER_PROTOCOL_ERROR') from None
            bounded(inner)
            if not isinstance(inner,list) or not inner or not isinstance(inner[0],list) or len(inner[0])<5:
                raise Rejected('UNIMPLEMENTED_SOURCE_GAP')
            row=inner[0];info=row[4]
            if not isinstance(info,list) or len(info)<5:raise Rejected('UNIMPLEMENTED_SOURCE_GAP')
            if type(info[-1]) is not int or info[-1]!=1:continue
            answer=text(row[0]);citations=[]
            passages=info[3]
            if passages is None:passages=[]
            if not isinstance(passages,list) or len(passages)>100:raise Rejected('PROVIDER_STRUCTURE_INVALID')
            for i,passage in enumerate(passages):
                try:
                    detail=passage[1];sid=detail[5][0][0][0]
                    if not isinstance(detail,list):raise TypeError()
                    sid=ident(sid)
                except (IndexError,KeyError,TypeError):raise Rejected('UNIMPLEMENTED_SOURCE_GAP') from None
                if sid not in allowed_sources:raise Rejected('PROVIDER_CITATION_NOT_ALLOWED')
                citation={'citation_number':i+1,'source_id':sid}
                quoted=cited_text(detail)
                if quoted:citation['cited_text']=quoted
                citations.append(citation)
            if best is None or len(answer)>len(best['answer']):best={'answer':answer,'citations':citations}
    # Unlike upstream's fallback, never represent a thinking-only response as an answer.
    if best is None:raise Rejected('UNIMPLEMENTED_SOURCE_GAP')
    return best

class GeminiResearchProvider:
    """Four source-derived operations. No credential/file/environment access."""
    def __init__(self,transport:AuthenticatedReadTransport,capability:AccountCapability,notebooks:dict,query_limit=2000):
        self.transport=transport;self.capability=capability;self.notebooks=notebooks;self.query_limit=query_limit

    def _identity(self):
        if self.transport.account_identity()!=self.capability.account_id:raise Rejected('ACCOUNT_IDENTITY_MISMATCH')

    def _book(self,nb):
        ident(nb)
        if nb not in self.notebooks:raise Rejected('NOTEBOOK_NOT_ALLOWED')

    def _result(self,data):
        return {'account_id':self.capability.account_id,'status':'ok','provider_kind':getattr(self.transport,'provider_kind','GEMINI_SOURCE_DERIVED_MOCK'),
            'data':data,'verification_status':'SOURCE_NOT_VERIFIED','limitations':['Source-derived adapter; live Google compatibility and semantic citation support unverified.']}

    def list_notebooks(self):
        self._identity();books=parse_discovery(self.transport.request(ReadRequest('rpc',LIST_RPC,'/',[None,1,None,[2]])))
        return self._result({'notebooks':[{'id':b['notebook_id'],'title':b['title']} for b in books if b['notebook_id'] in self.notebooks]})

    def get_notebook(self,notebook_id):
        self._book(notebook_id);self._identity()
        book=parse_notebook(self.transport.request(ReadRequest('rpc',GET_RPC,f'/notebook/{notebook_id}',[notebook_id,None,[2],None,0])),notebook_id)
        book['sources']=[s for s in book['sources'] if s['id'] in self.notebooks[notebook_id]['sources']]
        return self._result(book)

    def query(self,notebook_id,query,source_ids):
        self._book(notebook_id)
        if not isinstance(query,str) or not query.strip() or len(query)>self.query_limit or URL_PATH.search(query):raise Rejected('QUERY_INVALID')
        if not isinstance(source_ids,list) or not source_ids or len(source_ids)>100 or any(ident(s) not in self.notebooks[notebook_id]['sources'] for s in source_ids):raise Rejected('SOURCE_NOT_ALLOWED')
        self._identity()
        params=[[[[sid]] for sid in source_ids],query,None,[2,None,[1]],str(uuid.uuid4())]
        try:result=parse_query(self.transport.request(ReadRequest('stream',QUERY_ENDPOINT,f'/notebook/{notebook_id}',params)),source_ids)
        except Rejected as e:
            if getattr(self.transport,'provider_kind','')=='GEMINI_HTTPS_UNVERIFIED':
                e.outcome='UNKNOWN'
                if e.code=='AUTHENTICATION_EXPIRED':self.transport.invalidate_auth()
            raise
        return self._result({'notebook_id':notebook_id,**result})

    def get_source(self,notebook_id,source_id):
        self._book(notebook_id)
        if ident(source_id) not in self.notebooks[notebook_id]['sources']:raise Rejected('SOURCE_NOT_ALLOWED')
        self._identity()
        source=parse_source(self.transport.request(ReadRequest('rpc',SOURCE_RPC,'/',[[source_id],[2],[2]])),source_id)
        return self._result({'notebook_id':notebook_id,**source})

    def close(self):self.transport.close()
