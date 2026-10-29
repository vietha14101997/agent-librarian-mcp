"""Pinned-source protocol shapes through mocked capabilities; no Google HTTP."""
from pathlib import Path
import json
import unittest
from unittest.mock import patch
from agent_librarian.gateway.common import Rejected
from agent_librarian.providers.gemini import (GeminiResearchProvider,AccountCapability,ReadRequest,
    parse_discovery,parse_notebook,parse_query,parse_source,LIST_RPC,QUERY_ENDPOINT)
from agent_librarian.providers.gemini_mock import MockGeminiTransport

ROOT=Path(__file__).resolve().parents[1]
class GeminiTests(unittest.TestCase):
    def setUp(self):
        self.policy=json.loads((ROOT/'examples/research-policy.json').read_text())
        self.fixture=json.loads((ROOT/'tests/fixtures/research.json').read_text())
        self.transport=MockGeminiTransport(self.fixture,self.policy['account_id'])
        self.provider=GeminiResearchProvider(self.transport,AccountCapability(self.policy['account_id']),self.policy['notebooks'])
    def tearDown(self):self.provider.close()
    def query(self):return self.provider.query('notebook-approved','What synthetic decision?', ['source-approved'])
    def test_01_discovery_parsing(self):
        r=self.provider.list_notebooks();self.assertEqual(len(r['data']['notebooks']),2)
        self.assertEqual(self.transport.calls[0].method,LIST_RPC)
    def test_02_metadata_parsing(self):
        r=self.provider.get_notebook('notebook-approved')['data'];self.assertEqual(r['notebook_id'],'notebook-approved')
        self.assertEqual([s['id'] for s in r['sources']],['source-approved'])
    def test_03_query_parsing(self):
        r=self.query()['data'];self.assertIn('bounded queue',r['answer'])
        self.assertEqual(self.transport.calls[-1].method,QUERY_ENDPOINT)
        self.assertEqual(self.transport.calls[-1].params[0],[[['source-approved']]])
    def test_04_citations_preserved(self):
        self.assertEqual(self.query()['data']['citations'],[{'citation_number':1,'source_id':'source-approved'}])
    def test_05_source_content_mapping(self):
        r=self.provider.get_source('notebook-approved','source-approved')['data']
        self.assertEqual(r['source_id'],'source-approved');self.assertIn('bounded queue',r['content'])
    def test_06_protocol_error(self):
        stream=json.dumps([['wrb.fr',None,None,None,None,[8]]])
        with self.assertRaises(Rejected) as r:parse_query(stream,['source-approved'])
        self.assertEqual(r.exception.code,'PROVIDER_PROTOCOL_ERROR')
    def test_07_missing_citations_not_invented(self):
        self.fixture['mode']='missing_citations';self.assertEqual(self.query()['data']['citations'],[])
    def test_08_unknown_structure_is_source_gap(self):
        with self.assertRaises(Rejected) as r:parse_notebook({'changed':'response'},'notebook-approved')
        self.assertEqual(r.exception.code,'UNIMPLEMENTED_SOURCE_GAP')
    def test_09_admin_dispatch_absent(self):
        self.assertFalse(hasattr(self.provider,'source_add'));self.assertFalse(hasattr(self.provider,'notebook_delete'))
        with self.assertRaises(Rejected):self.transport.request(ReadRequest('rpc','delete','/',[]))
    def test_10_no_credential_discovery(self):
        with patch('builtins.open',side_effect=AssertionError('No credential reads')),patch('socket.socket',side_effect=AssertionError('No network')):
            self.query();self.provider.list_notebooks();self.provider.get_source('notebook-approved','source-approved')
    def test_11_account_checked_before_request(self):
        self.transport.account_id='wrong'
        with self.assertRaises(Rejected) as r:self.query()
        self.assertEqual(r.exception.code,'ACCOUNT_IDENTITY_MISMATCH');self.assertEqual(self.transport.calls,[])
    def test_12_foreign_source_denied(self):
        with self.assertRaises(Rejected):self.provider.get_source('notebook-approved','source-second')
        self.assertEqual(self.transport.calls,[])
    def test_13_foreign_citation_denied(self):
        self.fixture['mode']='foreign_citation'
        with self.assertRaises(Rejected) as r:self.query()
        self.assertEqual(r.exception.code,'PROVIDER_CITATION_NOT_ALLOWED')
    def test_14_thinking_not_an_answer(self):
        self.fixture['mode']='thinking_only'
        with self.assertRaises(Rejected) as r:self.query()
        self.assertEqual(r.exception.code,'UNIMPLEMENTED_SOURCE_GAP')
    def test_15_source_identity_mismatch(self):
        raw=[[['foreign'],'Title',[]],None,None,[[[0,1,'text']]]]
        with self.assertRaises(Rejected) as r:parse_source(raw,'source-approved')
        self.assertEqual(r.exception.code,'PROVIDER_SOURCE_MISMATCH')
    def test_16_empty_discovery_valid(self):self.assertEqual(parse_discovery([[]]),[])
    def test_17_optional_source_metadata_matches_upstream(self):
        raw=[[['Synthetic',['unexpected'],'invalid']]]
        books=parse_discovery([[['Synthetic',None,'notebook-approved'],['',[],'notebook-empty']]])
        self.assertEqual(books[0]['sources'],[]);self.assertEqual(books[1]['title'],'')
        books=parse_discovery([[['Synthetic',[['source-approved',None]],'notebook-approved']]])
        self.assertEqual(books[0]['sources'],[{'id':'source-approved','title':''}])
        with self.assertRaises(Rejected):parse_discovery(raw)
    def test_18_raw_progress_stream_can_exceed_projected_output_limit(self):
        self.fixture['answer']='Synthetic answer. '*70
        request=ReadRequest('stream',QUERY_ENDPOINT,'/notebook/notebook-approved',[[[['source-approved']]],'Synthetic question',None,[2,None,[1]],'12345678-1234-4234-8234-123456789abc'])
        frame=self.transport.request(request).splitlines()[-1]
        stream=")]}'\n"+'\n'.join([frame]*200)+'\n'
        self.assertGreater(len(stream.encode()),131072)
        parsed=parse_query(stream,['source-approved'])
        self.assertEqual(parsed['answer'],self.fixture['answer'])
        self.assertTrue(parsed['citations'])
        with self.assertRaises(Rejected):parse_query('x'*(2*1024*1024+1),['source-approved'])
