"""One-request synthetic provider. No network, Google, shell or dynamic imports."""
import json
from pathlib import Path
import sys
import time

OPS={'librarian_list_notebooks','librarian_get_notebook','librarian_query','librarian_get_source'}

def main():
    fixture=json.loads(Path(sys.argv[1]).read_text())
    sys.stdout.write(json.dumps({'kind':'identity','account_id':fixture['account_id'],
        'status':'expired' if fixture.get('mode')=='expired' else 'ok'})+'\n')
    sys.stdout.flush()
    raw=sys.stdin.buffer.readline(65537)
    if len(raw)>65536:raise ValueError('oversized')
    request=json.loads(raw)
    if set(request)!={'operation','arguments'} or request['operation'] not in OPS:
        raise ValueError('forbidden')
    op=request['operation'];args=request['arguments'];mode=fixture.get('mode','normal')
    if mode=='timeout':time.sleep(2)
    if mode=='slow':time.sleep(.15)
    if mode=='malformed':
        sys.stdout.write('not JSON\n');return
    if mode=='exception':raise RuntimeError('SYNTHETIC_SECRET_MUST_NOT_PROPAGATE')
    if mode=='expired':
        result={'account_id':fixture['account_id'],'status':'expired','debug':'SID=SYNTHETIC_SECRET'}
    else:
        notebooks=fixture['notebooks']
        if op=='librarian_list_notebooks':
            data={'notebooks':[{'id':k,'title':v['title']} for k,v in notebooks.items()]}
        else:
            nb=args['notebook_id'];book=notebooks[nb]
            if op=='librarian_get_notebook':
                data={'notebook_id':nb,'title':book['title'],
                    'sources':[{'id':k,'title':v['title']} for k,v in book['sources'].items()]}
            elif op=='librarian_get_source':
                s=book['sources'][args['source_id']]
                data={'notebook_id':nb,'source_id':args['source_id'],'title':s['title'],'content':s['content']}
            else:
                # Query text is data, never instructions or a selector for fake fault modes.
                sid=args['source_ids'][0];source=book['sources'][sid]
                data={'notebook_id':nb,'answer':fixture.get('answer','The synthetic decision uses a bounded queue.'),
                    'citations':[{'citation_number':1,'source_id':sid,'title':source['title'],'cited_text':source['content']}]}
        if mode=='bad_structure':data=[]
        if mode=='foreign_citation' and op=='librarian_query':data['citations'][0]['source_id']='source-foreign'
        if mode=='missing_citations' and op=='librarian_query':data.pop('citations')
        if mode=='wrong_notebook' and op!='librarian_list_notebooks':data['notebook_id']='forged-notebook'
        result={'account_id':fixture['account_id'],'status':'ok','data':data,
            'cookies':{'SID':'SYNTHETIC_SECRET_MUST_NOT_PROPAGATE'},
            'csrf_token':'SYNTHETIC_CSRF','raw_html':'<html>authenticated synthetic dump</html>'}
    encoded=json.dumps(result,ensure_ascii=True,allow_nan=False)
    if len(encoded)>131000:raise ValueError('oversized')
    sys.stdout.write(encoded+'\n')

if __name__=='__main__':main()
