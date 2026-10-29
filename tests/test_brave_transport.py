"""Native bridge tests: synthetic page, credential store and responses only."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from dataclasses import replace
import unittest
from unittest.mock import patch
from agent_librarian.gateway.common import Rejected,NAMES
from agent_librarian.personal.state import PersonalState,write_private
from agent_librarian.personal.brave_transport import BraveTransport,connect,browser_status,CONNECTION
from agent_librarian.personal.runtime import prepare,direct_call
from agent_librarian.providers.gemini import ReadRequest,LIST_RPC,QUERY_ENDPOINT
from agent_librarian.providers.gemini_mock import MockGeminiTransport
from tests.http_fakes import MemoryStore,session,SECRET

ROOT=Path(__file__).resolve().parents[1]
PAGE={'window_id':'1','tab_id':'2','origin':'https://notebook.google.com'}

class FakePage:
    def __init__(self):
        fixture=json.loads((ROOT/'tests/fixtures/research.json').read_text())
        self.backend=MockGeminiTransport(fixture,'synthetic-research-01',SECRET)
        self.requests=[];self.actions=[];self.error=None;self.pending=False
    def __call__(self,source):
        if 'var w=a.windows[0]' in source:return dict(PAGE,status='OK')
        raw=source.split('return String(t.execute({javascript:',1)[1].split('}));',1)[0]
        javascript=json.loads(raw)
        payload=json.loads(javascript.rsplit('})(',1)[1].strip()[:-1])
        action=payload['action'];self.actions.append(action)
        if action=='start':
            if self.error:return {'status':'ERROR','code':self.error}
            r=ReadRequest(**payload['request']);self.requests.append(r)
            value=self.backend.request(r)
            self.body=value if r.kind=='stream' else ")]}'\n1\n"+json.dumps([['wrb.fr',r.method,json.dumps(value)]])+'\n'
            return {'status':'DISPATCHED'}
        if action=='cancel':return {'status':'CANCELLED'}
        if self.pending:return {'status':'PENDING'}
        return {'status':'DONE','http_status':200,'text':self.body}

class BraveTransportTests(unittest.TestCase):
    def setUp(self):
        (ROOT/'state').mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'state');self.addCleanup(self.temp.cleanup)
        self.state=PersonalState(Path(self.temp.name)/'personal',create=True)
        self.page=FakePage();self.saved=replace(session(),account_id=self.state.load()['account_id'],expires_at=time.time()+300,host='notebook.google.com')
        self.store=MemoryStore(self.saved)
        self.books={'notebook-approved':{'title':'Synthetic','sources':{'source-approved':'Synthetic'}}}
    def transport(self,**kwargs):return BraveTransport(PAGE,self.saved.account_id,self.saved.expected_email,self.books,runner=self.page,**kwargs)
    def test_01_consent_before_keychain_or_browser_access(self):
        with patch.object(self.store,'load',side_effect=AssertionError('No access')):
            with self.assertRaises(Rejected):connect(self.state,False,self.store,self.page)
        self.assertFalse(self.page.requests)
    def test_02_connect_one_discovery_keychain_unchanged(self):
        result=connect(self.state,True,self.store,self.page)
        self.assertEqual(result['status'],'BROWSER_DISCOVERY_VERIFIED');self.assertEqual(len(self.page.requests),1)
        self.assertEqual(self.store.saved,0);self.assertFalse(self.store.deleted)
        self.assertIsNone(self.state.load()['selected_notebook'])
        self.assertTrue(browser_status(self.state)['authenticated'])
        self.assertNotIn(SECRET,(self.state.path/CONNECTION).read_text())
    def test_03_closed_operations_rejected_before_apple_events(self):
        transport=self.transport()
        for request in [ReadRequest('rpc','source_delete','/',[]),ReadRequest('rpc','rLM1Ne','/notebook/foreign',['foreign',None,[2],None,0])]:
            with self.assertRaises(Rejected):transport.request(request)
        self.assertFalse(self.page.actions)
    def test_04_account_mismatch_no_dispatch_no_cookie_fallback(self):
        self.page.error='ACCOUNT_IDENTITY_MISMATCH'
        with self.assertRaises(Rejected) as e:self.transport().request(ReadRequest('rpc',LIST_RPC,'/',[None,1,None,[2]]))
        self.assertEqual(e.exception.code,'ACCOUNT_IDENTITY_MISMATCH');self.assertFalse(self.page.requests)
    def test_05_fresh_process_status_needs_no_brave_or_keychain(self):
        connect(self.state,True,self.store,self.page)
        process=subprocess.run([sys.executable,'-I','-B','-m','agent_librarian','browser','status','--state-dir',str(self.state.path)],capture_output=True,text=True)
        self.assertEqual(process.returncode,0,process.stderr)
        self.assertEqual(json.loads(process.stdout)['network_operations'],0)
    def test_06_native_subprocess_keeps_source_off_arguments(self):
        from agent_librarian.personal.brave_transport import osascript
        with patch('subprocess.run',return_value=subprocess.CompletedProcess([],0,b'{"status":"PENDING"}',b'')) as run:
            self.assertEqual(osascript('SYNTHETIC_PRIVATE_SOURCE')['status'],'PENDING')
        self.assertNotIn('SYNTHETIC_PRIVATE_SOURCE',str(run.call_args.args));self.assertEqual(run.call_args.kwargs['input'],b'SYNTHETIC_PRIVATE_SOURCE')
    def test_07_provider_reuses_browser_connection_and_query_permit(self):
        connect(self.state,True,self.store,self.page);self.state.select('notebook-approved')
        factory=lambda connection,account,email,books,**kwargs:BraveTransport(connection,account,email,books,runner=self.page,**kwargs)
        with patch('agent_librarian.personal.brave_transport.BraveTransport',side_effect=factory),patch('agent_librarian.personal.runtime.GeminiHTTPS',side_effect=AssertionError('No HTTP replay')):
            result=direct_call(self.state,NAMES[2],{'notebook_id':'notebook-approved','query':'Synthetic question'},self.store)
            self.assertEqual(result['code'],'PERSONAL_QUERY_APPROVAL_REQUIRED')
            self.state.approve_query('Synthetic question',True)
            result=direct_call(self.state,NAMES[2],{'notebook_id':'notebook-approved','query':'Synthetic question'},self.store)
            self.assertEqual(result['status'],'OK');self.assertTrue(result['citations'])
        self.assertEqual(len(self.page.requests),2)
    def test_08_query_lost_response_unknown_no_retry(self):
        ticks=iter([0,0,1]);self.page.pending=True
        transport=self.transport(timeout=.05,clock=lambda:next(ticks),sleep=lambda _:None)
        request=ReadRequest('stream',QUERY_ENDPOINT,'/notebook/notebook-approved',[[[['source-approved']]],'Synthetic question',None,[2,None,[1]],'12345678-1234-4234-8234-123456789abc'])
        with self.assertRaises(Rejected) as error:transport.request(request)
        self.assertEqual(error.exception.outcome,'UNKNOWN');self.assertEqual(len(self.page.requests),1)
        self.assertEqual(self.page.actions[-1],'cancel')
    def test_09_disabled_runtime_does_not_dispatch(self):
        with self.assertRaises(Rejected):self.transport(disabled=lambda:True).request(ReadRequest('rpc',LIST_RPC,'/',[None,1,None,[2]]))
        self.assertFalse(self.page.actions)
    def test_10_failed_bridge_retains_connection_failure_and_session(self):
        self.page.error='BRAVE_PAGE_CONTEXT_UNAVAILABLE'
        with self.assertRaises(Rejected):connect(self.state,True,self.store,self.page)
        self.assertEqual(browser_status(self.state)['status'],'BROWSER_RPC_FAILED')
        self.assertEqual(self.store.saved,0);self.assertFalse(self.store.deleted)
    def test_11_reconnect_uses_pinned_tab_when_another_tab_is_active(self):
        connect(self.state,True,self.store,self.page)
        original=self.page
        def no_active_tab(source):
            if 'var w=a.windows[0]' in source:raise AssertionError('Should reuse the saved tab handle')
            return original(source)
        result=connect(self.state,True,self.store,no_active_tab)
        self.assertEqual(result['status'],'BROWSER_DISCOVERY_VERIFIED')
