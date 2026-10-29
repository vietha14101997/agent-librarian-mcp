"""Bounded wire/decoder regressions and actual JS projection, fully synthetic."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest
from agent_librarian.gateway.common import Rejected
from agent_librarian.gateway.policy import Gateway
from agent_librarian.providers.gemini import parse_notebook,parse_source,parse_query,GET_RPC
from agent_librarian.providers.wire import project_response,frames,FRAME_BYTES,MAX_FRAMES
from agent_librarian.providers.service import SecretConfinement

ROOT=Path(__file__).resolve().parents[1]
def frame(method,data):return (json.dumps([['wrb.fr',method,json.dumps(data,ensure_ascii=False)]],ensure_ascii=False)+'\n').encode()
def query_data(answer='Final synthetic answer',complete=1):return [[answer,None,None,None,[None,None,None,[],complete]]]
def split(raw,n=8192):return (raw[i:i+n] for i in range(0,len(raw),n))

class LargeNotebookTests(unittest.TestCase):
    def test_notebook_53_sources_drops_unused_metadata_not_identities(self):
        sources=[[[f'source-{i}'],f'document-{i}.md',[None,None,None,None,11,'x'*5000],[None,2]] for i in range(53)]
        raw=b")]}'\n"+frame(GET_RPC,[['Synthetic',sources,'notebook-test','unused'*2000]])
        self.assertGreater(len(raw),131072)
        compact=project_response(split(raw),GET_RPC);self.assertLess(len(compact),131072)
        from agent_librarian.providers.https_transport import rpc_result
        book=parse_notebook(rpc_result(compact,GET_RPC),'notebook-test');self.assertEqual(len(book['sources']),53)
        self.assertEqual([s['id'] for s in book['sources']],[f'source-{i}' for i in range(53)])
    def test_repeated_query_frames_over_two_mib_keep_final_only(self):
        # 200 bounded frames repeat large progress; aggregate bytes exceed old bound.
        progress=frame(None,query_data('thinking '*1800,0));final=frame(None,query_data())
        raw=b")]}'\n"+progress*200+final
        self.assertGreater(len(raw),2*1024*1024)
        result=project_response(split(raw),None);self.assertLess(len(result),131072)
        self.assertEqual(parse_query(result.decode(),[])['answer'],'Final synthetic answer')
    def test_no_final_answer_and_foreign_rpc_rejected(self):
        with self.assertRaises(Rejected):project_response([b")]}'\n"+frame(None,query_data('thinking',0))],None)
        with self.assertRaises(Rejected):project_response([b")]}'\n"+frame('foreign',[])],GET_RPC)
    def test_unicode_split_at_every_byte_and_non_utf8_marker_unit(self):
        raw=b")]}'\n123\n"+frame(GET_RPC,[['Tiếng Việt 😀',[],'notebook-test']])
        result=project_response(split(raw,1),GET_RPC);self.assertIn('Tiếng Việt',result.decode())
    def test_frame_and_frame_count_bounded(self):
        with self.assertRaises(Rejected) as e:list(frames(split(b")]}'\n"+b'x'*(FRAME_BYTES+1))))
        self.assertEqual(e.exception.code,'HTTP_FRAME_LIMIT')
        with self.assertRaises(Rejected) as e:list(frames(split(b")]}'\n"+b'[]\n'*(MAX_FRAMES+1))))
        self.assertEqual(e.exception.code,'HTTP_FRAME_COUNT_LIMIT')
    def test_malformed_truncated_frames_and_utf8_rejected(self):
        for raw in (b'[]',b")]}'\n1\n",b")]}'\n{bad}\n",b")]}'\n[\xff]\n",b")]}'\n2\n3\n[]\n"):
            with self.subTest(raw=raw),self.assertRaises(Rejected):list(frames(split(raw,1)))
    def test_deep_structure_and_duplicate_rpc_rejected(self):
        nested=None
        for _ in range(30):nested=[nested]
        for raw in (b")]}'\n"+frame(GET_RPC,nested),b")]}'\n"+frame(GET_RPC,[])*2):
            with self.assertRaises(Rejected):project_response(split(raw),GET_RPC)
    def test_long_source_uses_same_reviewed_shape_and_redacts_before_paging(self):
        content='Readable passage. '*4000
        raw=[[['source-test'],'Title',[]],None,None,[[[0,1,content]]]]
        decoded=parse_source(raw,'source-test');self.assertEqual(decoded['content'],content)
        policy=json.loads((ROOT/'examples/research-policy.json').read_text());policy['enabled']=True;policy['notebooks']['notebook-approved']['sources']={'source-test':'Title'}
        class Provider:
            def get_source(self,notebook_id,source_id):return {'account_id':policy['account_id'],'status':'ok','data':{'notebook_id':notebook_id,**decoded}}
            def close(self):pass
        g=Gateway(policy,None,ROOT/'state',provider=Provider());pieces=[];offset=0
        while True:
            r=g.call('librarian_get_source',{'notebook_id':'notebook-approved','source_id':'source-test','offset':offset})
            self.assertEqual(r['status'],'OK');self.assertLessEqual(len(r['content']),16000);pieces.append(r['content'])
            if r['next_offset'] is None:break
            offset=r['next_offset']
        self.assertEqual(''.join(pieces),content)
        for args in ({'offset':True},{'offset':-1},{'max_chars':16001},{'offset':1048577}):
            self.assertEqual(g.call('librarian_get_source',{'notebook_id':'notebook-approved','source_id':'source-test',**args})['status'],'ERROR')
    def test_source_identity_and_shape_stay_strict(self):
        for value in ([[['foreign'],'Title'],None,None,[[['content']]]],[[['source-test'],'Title'],None,None,[['wrong-block']]]):
            with self.assertRaises(Rejected):parse_source(value,'source-test')
    @unittest.skipUnless(shutil.which('node'),'Node only needed for synthetic JS VM')
    def test_actual_upload_js_closed_protocol(self):
        p=subprocess.run(['node',str(ROOT/'tests/browser_ingestion.cjs'),str(ROOT)],capture_output=True,text=True,timeout=10)
        self.assertEqual(p.returncode,0,p.stderr);self.assertTrue(json.loads(p.stdout)['passed'])
    @unittest.skipUnless(shutil.which('node'),'Node only needed for synthetic JS VM')
    def test_actual_browser_projector_matches_python_for_large_stream(self):
        script=r'''
const fs=require('fs'),vm=require('vm');const context={TextDecoder,TextEncoder};vm.createContext(context);
const wire=vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),context);
const enc=new TextEncoder();const progress=JSON.stringify([['wrb.fr',null,JSON.stringify([['thinking '.repeat(1800),null,null,null,[null,null,null,[],0]]])]])+'\n';
const end=JSON.stringify([['wrb.fr',null,JSON.stringify([['Final synthetic answer',null,null,null,[null,null,null,[],1]]])]])+'\n';
const bytes=enc.encode(")]}'\n"+progress.repeat(200)+end);let offset=0;
wire.project({read:async()=>offset>=bytes.length?{done:true}:(()=>{const value=bytes.slice(offset,offset+8093);offset+=value.length;return {done:false,value};})(),cancel:async()=>{}},null).then(x=>process.stdout.write(JSON.stringify({bytes:bytes.length,result:x.text}))).catch(e=>{process.stderr.write(JSON.stringify(e));process.exitCode=1});
'''
        p=subprocess.run(['node','-e',script,str(ROOT/'src/agent_librarian/personal/wire.js')],capture_output=True,text=True,timeout=10)
        self.assertEqual(p.returncode,0,p.stderr);d=json.loads(p.stdout);self.assertGreater(d['bytes'],2097152)
        self.assertEqual(parse_query(d['result'],[])['answer'],'Final synthetic answer')
