"""Offline wire contracts derived from reviewed upstream pure builders.

The fixture is synthetic, not an authenticated capture. The upstream runtime,
browser and credential stores are never used by these tests.
"""
import json
from pathlib import Path
import unittest
from urllib.parse import parse_qs
from unittest.mock import patch

from agent_librarian.gateway.common import Rejected
from agent_librarian.personal.browser_auth import browser_session,seed_manager
from agent_librarian.providers.gemini import ReadRequest,LIST_RPC,QUERY_ENDPOINT
from agent_librarian.providers.https_transport import GeminiHTTPS,HttpReply
from tests.http_fakes import MemoryStore

ROOT=Path(__file__).resolve().parents[1]

class WireContractTests(unittest.TestCase):
    def setUp(self):
        fixture=json.loads((ROOT/'tests/fixtures/upstream-wire.synthetic.json').read_text())
        self.context=fixture['context'];self.contracts={x['operation']:x for x in fixture['contracts']}
        c=self.context
        html=json.dumps({'oPEP7c':c['email'],'SNlM0e':c['csrf'],'FdrFJe':c['session_id'],'cfb2h':c['build_label']})
        self.session=browser_session(html,c['cookies'],'https://'+c['host']+'/','synthetic-research-01')
        self.calls=[];self.reply=None
        owner=self
        class Sender:
            def send(self,method,path,headers,body,*bounds):
                owner.calls.append((method,path,headers,body))
                if owner.reply is not None:return owner.reply
                rpc=parse_qs(path.partition('?')[2]).get('rpcids',[None])[0]
                payload=json.dumps([['wrb.fr',rpc,'[]']]) if rpc else json.dumps([['wrb.fr',None,json.dumps([['Synthetic answer',None,None,None,[None,None,None,[],1]]])]])
                return HttpReply(200,{'content-type':'application/json'},(")]}'\n"+payload).encode())
            def close(self):pass
        self.sessions=seed_manager(MemoryStore(self.session),self.session)
        self.transport=GeminiHTTPS(self.sessions,{'notebook-approved':{'sources':{'source-approved':'Synthetic'}}},sender=Sender(),validate_discovery=False)
        self.offline=patch('socket.create_connection',side_effect=AssertionError('No network in wire contract tests'))
        self.offline.start();self.addCleanup(self.offline.stop);self.addCleanup(self.transport.close)

    def check_rpc(self,name):
        expected=self.contracts[name]
        self.transport._rpc(self.session,expected['rpc'],expected['source_path'],expected['params'])
        self.assertEqual(len(self.calls),1)
        method,path,headers,body=self.calls[0]
        self.assertEqual(method,expected['method'])
        self.assertEqual('https://'+self.session.host+path,expected['url'])
        self.assertEqual(body,expected['body'].encode())
        headers={k.lower():v for k,v in headers.items()}
        for key,value in expected['headers'].items():self.assertEqual(headers[key],value)

    def test_discovery_request_matches_upstream(self):self.check_rpc('list')
    def test_notebook_request_matches_upstream(self):self.check_rpc('get')
    def test_source_request_matches_upstream(self):self.check_rpc('source')

    def test_query_form_has_upstream_semantics(self):
        expected=self.contracts['query']
        self.transport.request(ReadRequest('stream',QUERY_ENDPOINT,expected['source_path'],expected['params']))
        method,path,headers,body=self.calls[0]
        self.assertEqual('https://'+self.session.host+path,expected['url'])
        actual_form=parse_qs(body.decode());reference_form=parse_qs(expected['body'])
        self.assertEqual(json.loads(actual_form['f.req'][0]),json.loads(reference_form['f.req'][0]))
        self.assertEqual(actual_form['at'],reference_form['at'])
        self.assertEqual(headers['Content-Type'],expected['headers']['content-type'])

    def test_session_context_uses_distinct_fields_and_cookie_domains(self):
        self.check_rpc('list')
        _,path,headers,body=self.calls[0]
        fields=parse_qs(path.partition('?')[2]);form=parse_qs(body.decode())
        self.assertEqual(fields['f.sid'],[self.context['session_id']])
        self.assertTrue(fields['f.sid'][0].startswith('-'))
        self.assertEqual(fields['bl'],[self.context['build_label']])
        self.assertEqual(form['at'],[self.context['csrf']])
        self.assertEqual(headers['X-Goog-Csrf-Token'],form['at'][0])
        self.assertIn('OSID=SYNTHETIC_OSID_ONLY',headers['Cookie'])
        self.assertNotIn('LSID=',headers['Cookie'])

    def test_rpc_16_remains_auth_failure_and_is_not_retried(self):
        frame=json.dumps([['wrb.fr',LIST_RPC,None,None,None,[16]]])
        self.reply=HttpReply(200,{'content-type':'application/json'},(")]}'\n"+frame).encode())
        with self.assertRaises(Rejected) as error:
            self.transport.request(ReadRequest('rpc',LIST_RPC,'/',[None,1,None,[2]]))
        self.assertEqual(error.exception.code,'AUTHENTICATION_EXPIRED')
        self.assertEqual(self.sessions.state,'AUTH_REQUIRED')
        self.assertEqual(len(self.calls),1)
