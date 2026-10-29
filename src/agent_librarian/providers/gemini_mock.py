"""Synthetic source-shaped transport. No network or real authentication implementation."""
import json
import time
from .gemini import LIST_RPC,GET_RPC,SOURCE_RPC,QUERY_ENDPOINT
from ..gateway.common import Rejected

class MockGeminiTransport:
    def __init__(self,fixture,account_id,synthetic_secret='',timeout=1):
        self.fixture=fixture;self.account_id=account_id;self.secret=synthetic_secret;self.timeout=timeout;self.closed=False;self.calls=[]
    def account_identity(self):
        if self.closed:raise Rejected('SERVICE_DISABLED')
        return self.account_id
    def request(self,req):
        if self.closed:raise Rejected('SERVICE_DISABLED')
        if (req.kind,req.method) not in {('rpc',LIST_RPC),('rpc',GET_RPC),('rpc',SOURCE_RPC),('stream',QUERY_ENDPOINT)}:
            raise Rejected('FORBIDDEN_OPERATION')
        self.calls.append(req)
        mode=self.fixture.get('mode','normal')
        if mode=='timeout':time.sleep(self.timeout);raise Rejected('PROVIDER_TIMEOUT_OUTCOME_UNKNOWN')
        if mode=='expired':raise Rejected('AUTHENTICATION_EXPIRED')
        if mode=='exception':raise Rejected('PROVIDER_PROTOCOL_ERROR')
        if mode=='bad_structure':return {'unknown':'changed protocol'}
        books=self.fixture['notebooks']
        def row(nb):
            b=books[nb]
            return [b['title'],[[[sid],s['title'],[None,None,None,None,1]] for sid,s in b['sources'].items()],nb]
        if req.method==LIST_RPC:return [[row(nb) for nb in books]]
        if req.method==GET_RPC:return [row(req.params[0])]
        if req.method==SOURCE_RPC:
            sid=req.params[0][0]
            for book in books.values():
                if sid in book['sources']:
                    source=book['sources'][sid]
                    content=source['content'].replace('{{SERVICE_CANARY}}',self.secret)
                    return [[[sid],source['title'],[None,None,None,None,1]],None,None,[[[0,len(content),content]]]]
            raise Rejected('SOURCE_NOT_ALLOWED')
        ids=[s[0][0] for s in req.params[0]]
        answer=self.fixture.get('answer','The synthetic decision uses a bounded queue.').replace('{{SERVICE_CANARY}}',self.secret)
        passages=[] if mode=='missing_citations' else [[['synthetic-passage'],[None,None,None,None,[],[[[ids[0]]]]]]]
        nested=[[answer,None,['synthetic-conversation'],None,[None,None,None,passages,1]]]
        if mode=='thinking_only':nested[0][4][-1]=2
        if mode=='foreign_citation':passages[0][1][5][0][0][0]='source-foreign'
        line=json.dumps([['wrb.fr',None,json.dumps(nested)]])
        return ")]}'\n"+str(len(line.encode()))+'\n'+line+'\n'
    def close(self):self.closed=True
