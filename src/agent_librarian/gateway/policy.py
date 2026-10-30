"""Executable research policy adapted from KN-MCP-02, not a credential boundary."""
import json, sys, threading, time, uuid
from pathlib import Path
from .common import MAX_RESPONSE, NAMES, Rejected, load_policy, exact, ident, text, URL_PATH
from ..providers.fake import FakeProvider

def safe_diagnostics(values):
    if not isinstance(values,dict):return {}
    numeric={'http_status','bytes_read','frames','frame_limit','wire_limit','response_limit','rpc_error_code','outer_length','content_wrapper_length'}
    result={k:v for k,v in values.items() if k in numeric and type(v) is int and 0<=v<=67108864}
    if values.get('rpc') in ('wXbhsf','rLM1Ne','hizoJc','QUERY_STREAM'):result['rpc']=values['rpc']
    if values.get('stage') in ('SOURCE_DECODE','BROWSER_FETCH_OR_PROJECTION','RPC_ENVELOPE','CDP_EVALUATE'):result['stage']=values['stage']
    return result

class Gateway:
    def __init__(self, policy, fixture, control_dir, provider=None):
        self.policy=load_policy(policy)
        self.control=Path(control_dir)
        self.provider=provider if provider is not None else FakeProvider(fixture,self.policy['timeout_seconds'],self.policy['account_id'])
        self.busy=threading.Lock()
        self.stopped=False

    def disabled(self):
        return self.stopped or not self.policy['enabled'] or (self.control/'DISABLED').exists()

    def close(self):
        self.stopped=True
        self.provider.close()

    def validate(self,name,args):
        if name not in NAMES:
            raise Rejected('FORBIDDEN_OPERATION')
        if name==NAMES[0]:
            exact(args,());return {}
        if name==NAMES[1]:exact(args,('notebook_id',))
        elif name==NAMES[2]:exact(args,('notebook_id','query'),('source_ids',))
        elif name==NAMES[3]:exact(args,('notebook_id','source_id'),('offset','max_chars'))
        nb=ident(args['notebook_id'])
        if nb not in self.policy['notebooks']:
            raise Rejected('NOTEBOOK_NOT_ALLOWED')
        allowed=self.policy['notebooks'][nb]['sources']
        result={'notebook_id':nb}
        if name==NAMES[3]:
            sid=ident(args['source_id'])
            if sid not in allowed:raise Rejected('SOURCE_NOT_ALLOWED')
            result['source_id']=sid
            for key,default,minimum,maximum in (('offset',0,0,1048576),('max_chars',16000,1,16000)):
                value=args.get(key,default)
                if type(value) is not int or not minimum<=value<=maximum:raise Rejected('INVALID_ARGUMENTS')
                if key in args:result[key]=value
        if name==NAMES[2]:
            q=args['query']
            if not isinstance(q,str) or not q.strip() or len(q)>self.policy['query_max_chars']:
                raise Rejected('QUERY_INVALID')
            if URL_PATH.search(q) or any(ord(c)<32 and c not in '\n\t' for c in q):
                raise Rejected('QUERY_DESTINATION_REJECTED')
            sources=args.get('source_ids',list(allowed))
            if not isinstance(sources,list) or not 1<=len(sources)<=len(allowed):
                raise Rejected('SOURCE_NOT_ALLOWED')
            if any(ident(s) not in allowed for s in sources) or len(set(sources))!=len(sources):
                raise Rejected('SOURCE_NOT_ALLOWED')
            result.update(query=q,source_ids=sources)
        return result

    def project(self,name,args,raw):
        if not isinstance(raw,dict) or raw.get('account_id')!=self.policy['account_id']:
            raise Rejected('ACCOUNT_IDENTITY_MISMATCH')
        status=raw.get('status')
        if status=='expired':raise Rejected('AUTHENTICATION_EXPIRED')
        if status!='ok':raise Rejected('PROVIDER_FAILURE')
        data=raw.get('data')
        if not isinstance(data,dict):raise Rejected('PROVIDER_STRUCTURE_INVALID')
        kind=raw.get('provider_kind','SYNTHETIC_OFFLINE')
        if kind not in {'SYNTHETIC_OFFLINE','GEMINI_SOURCE_DERIVED_MOCK','IPC_SYNTHETIC_SERVICE','IPC_RESEARCH_SERVICE','GEMINI_HTTPS_UNVERIFIED','GEMINI_BROWSER_UNVERIFIED','GEMINI_MANAGED_CDP_UNVERIFIED'}:raise Rejected('PROVIDER_STRUCTURE_INVALID')
        base=dict(status='OK',provider_status='ok',provider=kind,
            untrusted_research_data=True,verification_limitations=['No Google operation performed.'] if kind in {'SYNTHETIC_OFFLINE','GEMINI_SOURCE_DERIVED_MOCK','IPC_SYNTHETIC_SERVICE'} else ['Live transport result; provenance and semantic support not independently attested.'])
        if name==NAMES[0]:
            notebooks=data.get('notebooks')
            if not isinstance(notebooks,list) or len(notebooks)>1000:
                raise Rejected('PROVIDER_STRUCTURE_INVALID')
            result=[];seen=set()
            for item in notebooks:
                if not isinstance(item,dict) or not isinstance(item.get('id'),str):
                    raise Rejected('PROVIDER_STRUCTURE_INVALID')
                nb=item['id']
                if nb in self.policy['notebooks']:
                    if nb in seen:raise Rejected('PROVIDER_STRUCTURE_INVALID')
                    seen.add(nb);result.append(dict(notebook_id=nb,title=text(item.get('title'))))
            return dict(base,notebooks=result)
        nb=args['notebook_id']
        if data.get('notebook_id')!=nb:raise Rejected('PROVIDER_NOTEBOOK_MISMATCH')
        base['notebook_id']=nb
        allowed=self.policy['notebooks'][nb]['sources']
        if name==NAMES[1]:
            sources=data.get('sources')
            if not isinstance(sources,list) or len(sources)>1000:raise Rejected('PROVIDER_STRUCTURE_INVALID')
            selected=[];seen=set()
            for s in sources:
                if not isinstance(s,dict) or not isinstance(s.get('id'),str):raise Rejected('PROVIDER_STRUCTURE_INVALID')
                if s['id'] in allowed:
                    if s['id'] in seen:raise Rejected('PROVIDER_STRUCTURE_INVALID')
                    seen.add(s['id']);selected.append(dict(source_id=s['id'],title=text(s.get('title'))))
            return dict(base,title=text(data.get('title')),sources=selected)
        if name==NAMES[3]:
            if data.get('source_id')!=args['source_id']:raise Rejected('PROVIDER_SOURCE_MISMATCH')
            page=self.source_page(args,data)
            content=text(data.get('content'),max_chars=1048576)
            if 'source_page' not in data:content=content[args.get('offset',0):args.get('offset',0)+args.get('max_chars',16000)]
            return dict(base,source_id=args['source_id'],title=text(data.get('title')),
                content=content,**page,verification_status='SOURCE_NOT_VERIFIED',
                verification_limitations=['Identity matched approved notebook/source; content provenance/revision not attested.'])
        citations=data.get('citations',[])
        if not isinstance(citations,list) or len(citations)>100:raise Rejected('PROVIDER_STRUCTURE_INVALID')
        projected=[]
        for c in citations:
            if not isinstance(c,dict):raise Rejected('PROVIDER_STRUCTURE_INVALID')
            sid=c.get('source_id')
            if sid not in args['source_ids']:raise Rejected('PROVIDER_CITATION_NOT_ALLOWED')
            number=c.get('citation_number')
            if type(number) is not int or not 1<=number<=100:raise Rejected('PROVIDER_STRUCTURE_INVALID')
            projected.append(dict(citation_number=number,source_id=sid,
                title=text(c['title']) if 'title' in c else None,
                cited_text=text(c['cited_text']) if 'cited_text' in c else None,
                association='PROVIDER_RETURNED',verification_status='SOURCE_NOT_VERIFIED'))
        return dict(base,answer=text(data.get('answer')),citations=projected,
            source_ids=sorted({c['source_id'] for c in projected}),
            query_status='COMPLETED',query_history_side_effect='MAY_PERSIST_NOTEBOOK_CHAT',
            verification_status='SOURCE_NOT_VERIFIED',
            verification_limitations=['Provider source associations returned; semantic support and remote revision not independently verified.',
                'A live query may persist conversation history; fake execution does not.'])

    def source_page(self,args,data):
        if 'source_page' in data:
            p=data['source_page'];exact(p,('offset','total_chars','truncated','next_offset'))
            start=args.get('offset',0);size=args.get('max_chars',16000);total=p['total_chars']
            if type(total) is not int or not start<=total<=1048576:raise Rejected('PROVIDER_STRUCTURE_INVALID')
            end=min(total,start+size)
            if (p['offset']!=start or type(p['truncated']) is not bool or p['truncated']!=(end<total) or p['next_offset']!=(end if end<total else None)
                    or len(text(data.get('content')))!=end-start):raise Rejected('PROVIDER_STRUCTURE_INVALID')
            return p
        content=data.get('content');total=len(text(content,max_chars=1048576));offset=args.get('offset',0)
        if offset>total:raise Rejected('INVALID_ARGUMENTS')
        end=min(total,offset+args.get('max_chars',16000))
        return {'offset':offset,'total_chars':total,'truncated':end<total,'next_offset':end if end<total else None}

    def call(self,name,args):
        request_id=uuid.uuid4().hex
        started=time.monotonic();code='INTERNAL_ERROR'
        try:
            if self.disabled():raise Rejected('SERVICE_DISABLED')
            checked=self.validate(name,args)
            if not self.busy.acquire(blocking=False):raise Rejected('BUSY')
            try:
                if self.disabled():raise Rejected('SERVICE_DISABLED')
                if name==NAMES[0]:raw=self.provider.list_notebooks()
                elif name==NAMES[1]:raw=self.provider.get_notebook(**checked)
                elif name==NAMES[2]:raw=self.provider.query(**checked)
                elif name==NAMES[3]:
                    raw=self.provider.get_source_page(**checked) if hasattr(self.provider,'get_source_page') else self.provider.get_source(notebook_id=checked['notebook_id'],source_id=checked['source_id'])
                else:raise Rejected('FORBIDDEN_OPERATION')
                result=self.project(name,checked,raw)
                diagnostics=safe_diagnostics(raw.get('diagnostics',{})) if isinstance(raw,dict) else {}
                if diagnostics:result['diagnostics']=diagnostics
                if self.disabled():raise Rejected('SERVICE_DISABLED')
            finally:self.busy.release()
            if len(json.dumps(result,ensure_ascii=False,allow_nan=False).encode())>MAX_RESPONSE:raise Rejected('PROVIDER_PROJECTION_LIMIT')
            code='OK'
            return result
        except Rejected as e:
            code=e.code
            result=dict(status='ERROR',code=code,provider_status='NOT_ACCEPTED',
                outcome=getattr(e,'outcome','UNKNOWN' if code in {'PROVIDER_TIMEOUT_OUTCOME_UNKNOWN','QUERY_OUTCOME_UNKNOWN'} else 'NOT_VERIFIED'))
            if hasattr(e,'diagnostics'):
                result['diagnostics']=safe_diagnostics(e.diagnostics)
            return result
        except Exception:
            return dict(status='ERROR',code='INTERNAL_ERROR',provider_status='NOT_ACCEPTED')
        finally:
            # No caller IDs, arguments, provider bodies, exception text or account metadata.
            receipt=dict(receipt_id=request_id,operation=name if name in NAMES else 'REJECTED',
                status=code,elapsed_ms=int((time.monotonic()-started)*1000))
            sys.stderr.write(json.dumps(receipt)+'\n');sys.stderr.flush()
