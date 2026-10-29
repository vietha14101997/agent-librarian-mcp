"""Restricted HTTP/session behavior. Every credential and HTTP reply is synthetic."""
from dataclasses import replace
import importlib.util
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import anyio
from mcp import Client,StdioServerParameters
from agent_librarian.gateway.common import Rejected,NAMES
from agent_librarian.providers.gemini import GeminiResearchProvider,AccountCapability,ReadRequest,LIST_RPC,QUERY_ENDPOINT
from agent_librarian.providers.session import SessionManager,page_session
from agent_librarian.providers.https_transport import GeminiHTTPS,FixedTLS,HttpReply,rpc_result
from agent_librarian.providers.credential_store import KeychainSessionStore
from agent_librarian.providers.ipc import IPCResearchProvider
from tests.http_fakes import ReplayHTTP,MemoryStore,session,SECRET
ROOT=Path(__file__).resolve().parents[1]

class TransportTests(unittest.TestCase):
    def setUp(self):
        self.policy=json.loads((ROOT/'examples/research-policy.json').read_text());self.policy['enabled']=True
        self.fixture=json.loads((ROOT/'tests/fixtures/research.json').read_text())
        self.store=MemoryStore();self.sessions=SessionManager(self.store,self.policy['account_id'],'research@example.invalid','notebooklm.google.com')
        self.http=ReplayHTTP(self.fixture);self.transport=GeminiHTTPS(self.sessions,self.policy['notebooks'],sender=self.http)
        self.provider=GeminiResearchProvider(self.transport,AccountCapability(self.policy['account_id']),self.policy['notebooks'])
    def tearDown(self):self.provider.close()
    def prime(self):self.provider.list_notebooks();self.http.calls.clear()
    def query(self):return self.provider.query('notebook-approved','What synthetic decision?',['source-approved'])
    def code(self,expected,fn):
        with self.assertRaises(Rejected) as result:fn()
        self.assertEqual(result.exception.code,expected);return result.exception
    def test_01_four_operations_real_wire_mock_http(self):
        self.assertEqual(len(self.provider.list_notebooks()['data']['notebooks']),2)
        self.assertEqual(self.provider.get_notebook('notebook-approved')['data']['notebook_id'],'notebook-approved')
        self.assertIn('bounded queue',self.query()['data']['answer'])
        self.assertIn('bounded queue',self.provider.get_source('notebook-approved','source-approved')['data']['content'])
        self.assertEqual(self.store.saved,1)
    def test_02_admin_rpc_rejected_before_network(self):
        self.code('HTTP_OPERATION_REJECTED',lambda:self.transport.request(ReadRequest('rpc','source_delete','/',[])));self.assertFalse(self.http.calls)
    def test_03_cross_notebook_denied_before_http(self):
        self.code('SOURCE_NOT_ALLOWED',lambda:self.provider.get_source('notebook-approved','source-second'));self.assertFalse(self.http.calls)
    def test_04_cookie_header_injection_rejected(self):
        self.store.value=replace(session(),cookies={'SID':'SYNTHETIC\r\nInjected: value'})
        self.code('SESSION_INVALID',self.provider.list_notebooks);self.assertFalse(self.http.calls)
    def test_05_account_mismatch_before_request(self):
        self.store.value=replace(session(),expected_email='other@example.invalid')
        self.code('ACCOUNT_IDENTITY_MISMATCH',self.provider.list_notebooks);self.assertFalse(self.http.calls)
    def test_06_page_account_mismatch(self):
        self.http.next_reply=HttpReply(200,{'content-type':'text/html'},b'{"oPEP7c":"other@example.invalid"}')
        self.code('ACCOUNT_IDENTITY_MISMATCH',self.provider.list_notebooks);self.assertEqual(self.store.saved,0)
    def test_07_expired_cookie_no_browser_fallback(self):
        self.http.next_reply=HttpReply(401,{'content-type':'text/html'},b'expired')
        with patch('subprocess.Popen',side_effect=AssertionError('No browser fallback')):self.code('AUTHENTICATION_EXPIRED',self.provider.list_notebooks)
        self.assertEqual(self.store.saved,0)
    def test_08_signed_out_200_not_authenticated(self):
        self.http.next_reply=HttpReply(200,{'content-type':'text/html'},b'landing-header-signin')
        self.code('AUTHENTICATION_EXPIRED',self.provider.list_notebooks)
    def test_09_refresh_structure_change_fails(self):
        self.http.next_reply=HttpReply(200,{'content-type':'text/html'},b'{"new-layout":true}')
        self.code('SESSION_REFRESH_STRUCTURE_CHANGED',self.provider.list_notebooks);self.assertEqual(self.store.saved,0)
    def test_10_negative_session_id_preserved(self):
        self.prime();self.provider.get_notebook('notebook-approved')
        self.assertIn('f.sid=-12345',self.http.calls[0][1])
    def test_11_redirect_no_follow_or_retry(self):
        self.prime();self.http.next_reply=HttpReply(302,{'location':'https://accounts.google.com/','content-type':'text/html'},b'')
        self.code('HTTP_REDIRECT_REJECTED',self.query);self.assertEqual(len(self.http.calls),1)
    def test_12_content_type_rejected(self):
        self.prime();self.http.next_reply=HttpReply(200,{'content-type':'text/html'},b'<html>changed</html>')
        self.code('HTTP_CONTENT_TYPE_REJECTED',self.query)
    def test_13_response_limit(self):
        self.prime();self.http.next_reply=HttpReply(200,{'content-type':'application/json'},b'x'*131073)
        self.code('HTTP_RESPONSE_LIMIT',self.query)
    def test_14_compression_not_accepted(self):
        self.prime();self.http.next_reply=HttpReply(200,{'content-type':'application/json','content-encoding':'gzip'},b'x')
        self.code('HTTP_ENCODING_REJECTED',self.query)
    def test_15_query_timeout_unknown_no_retry(self):
        self.prime();self.http.next_reply=TimeoutError(SECRET)
        error=self.code('PROVIDER_TIMEOUT_OUTCOME_UNKNOWN',self.query)
        self.assertEqual(error.outcome,'UNKNOWN');self.assertEqual(len(self.http.calls),1);self.assertNotIn(SECRET,str(error))
    def test_16_query_disconnect_unknown(self):
        self.prime();self.http.next_reply=OSError(SECRET)
        self.assertEqual(self.code('QUERY_OUTCOME_UNKNOWN',self.query).outcome,'UNKNOWN')
    def test_17_rpc_timeout_is_not_query_retry(self):
        self.prime();self.http.next_reply=TimeoutError()
        self.code('PROVIDER_TIMEOUT',self.provider.list_notebooks);self.assertEqual(len(self.http.calls),1)
    def test_18_changed_query_layout_unknown(self):
        self.prime();self.http.next_reply=HttpReply(200,{'content-type':'application/json'},b'changed protocol')
        error=self.code('PROVIDER_PROTOCOL_ERROR',self.query);self.assertEqual(error.outcome,'UNKNOWN')
    def test_19_wrong_rpc_correlation(self):
        self.prime()
        raw=json.dumps([['wrb.fr','forbidden',json.dumps([[]])]])
        self.http.next_reply=HttpReply(200,{'content-type':'application/json'},(")]}'\n"+raw).encode())
        self.code('PROVIDER_RPC_MISMATCH',self.provider.list_notebooks)
    def test_20_rpc_error16_invalidates_result(self):
        self.prime();raw=json.dumps([['wrb.fr',LIST_RPC,None,None,None,[16]]])
        self.http.next_reply=HttpReply(200,{'content-type':'application/json'},(")]}'\n"+raw).encode())
        self.code('AUTHENTICATION_EXPIRED',self.provider.list_notebooks);self.assertEqual(self.sessions.state,'AUTH_REQUIRED')
    def test_21_disable_prevents_requests(self):
        self.transport.disabled=lambda:True
        self.code('SERVICE_DISABLED',self.query);self.assertFalse(self.http.calls)
    def test_22_credential_repr_and_store_errors_safe(self):
        self.assertNotIn(SECRET,repr(session()));store=KeychainSessionStore('/SYNTHETIC/no-helper')
        with patch('subprocess.run',side_effect=OSError(SECRET)):
            self.code('CREDENTIAL_STORE_UNAVAILABLE',store.load)
    def test_23_no_plaintext_store_fallback(self):
        store=KeychainSessionStore('/SYNTHETIC/helper')
        with patch('subprocess.run',return_value=subprocess.CompletedProcess([],42,b'',b'')),patch('builtins.open',side_effect=AssertionError('No fallback file')):
            self.code('CREDENTIAL_STORE_UNAVAILABLE',store.load)
    def test_24_expired_local_validation_refreshes_once(self):
        self.prime();self.sessions.current=replace(self.sessions.current,expires_at=1)
        self.provider.get_notebook('notebook-approved');self.assertEqual(self.store.saved,2)
        self.assertEqual(sum(c[0]=='GET' for c in self.http.calls),1)
    def test_25_revoke_prevents_further_use(self):
        self.prime();self.sessions.revoke();self.assertTrue(self.store.deleted)
        self.code('SERVICE_DISABLED',self.query);self.assertFalse(self.http.calls)
    def test_26_fixed_host_tls_and_no_connection_during_construction(self):
        self.code('HTTP_DESTINATION_REJECTED',lambda:FixedTLS('attacker.example.invalid'))
        with patch('socket.socket',side_effect=AssertionError('No network before request')):
            sender=FixedTLS('notebooklm.google.com')
        self.assertEqual(sender.context.verify_mode,ssl.CERT_REQUIRED);self.assertTrue(sender.context.check_hostname)
    def test_27_no_credentials_in_http_reply_repr(self):
        self.assertNotIn(SECRET,repr(HttpReply(200,{},SECRET.encode())))
    def test_28_invalid_utf8_query_unknown(self):
        self.prime();self.http.next_reply=HttpReply(200,{'content-type':'application/json'},b'\xff')
        self.assertEqual(self.code('PROVIDER_PROTOCOL_ERROR',self.query).outcome,'UNKNOWN')

class HTTPServiceTests(unittest.TestCase):
    def test_29_actual_mcp_ipc_http_adapter_process_path(self):
        state=ROOT/'state';state.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='h',dir=state) as t:
            work=Path(t);sock=work/'s';policy=work/'policy.json';fixture=work/'fixture.json'
            data=json.loads((ROOT/'examples/research-policy.json').read_text());data['enabled']=True;policy.write_text(json.dumps(data))
            content=json.loads((ROOT/'tests/fixtures/research.json').read_text());content['answer']='Approved synthetic '+SECRET;fixture.write_text(json.dumps(content))
            service=subprocess.Popen([sys.executable,'-I','-B',str(ROOT/'tests/http_service_worker.py'),'--policy',str(policy),'--fixture',str(fixture),'--socket',str(sock)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                deadline=time.monotonic()+5
                while not sock.exists():
                    if service.poll() is not None:raise AssertionError(service.communicate()[1].decode())
                    if time.monotonic()>deadline:raise AssertionError('Synthetic HTTP service readiness timeout')
                    time.sleep(.01)
                async def run():
                    params=StdioServerParameters(command=sys.executable,args=['-I','-B','-m','agent_librarian','mcp-serve','--provider','service','--policy',str(policy),'--service-socket',str(sock),'--service-uid',str(os.geteuid()),'--control-dir',str(work)])
                    async with Client(params) as client:
                        self.assertEqual({x.name for x in (await client.list_tools()).tools},set(NAMES))
                        calls=[(NAMES[0],{}),(NAMES[1],{'notebook_id':'notebook-approved'}),(NAMES[2],{'notebook_id':'notebook-approved','query':'Synthetic question'}),(NAMES[3],{'notebook_id':'notebook-approved','source_id':'source-approved'})]
                        for name,args in calls:
                            result=(await client.call_tool(name,args)).structured_content
                            self.assertEqual(result['status'],'OK',result);self.assertNotIn(SECRET,json.dumps(result))
                            self.assertEqual(result['provider'],'IPC_RESEARCH_SERVICE')
                        denied=(await client.call_tool('source_delete',{})).structured_content;self.assertEqual(denied['code'],'FORBIDDEN_OPERATION')
                anyio.run(run)
                (work/'DISABLED').write_text('Synthetic revocation')
                with self.assertRaises(Rejected) as error:IPCResearchProvider(sock,os.geteuid(),'research-client',data['account_id']).list_notebooks()
                self.assertEqual(error.exception.code,'SERVICE_DISABLED')
            finally:
                if service.poll() is None:service.terminate()
                _,stderr=service.communicate(timeout=5);self.assertNotIn(SECRET,stderr.decode())
            self.assertFalse(sock.exists())

class TLSSenderTests(unittest.TestCase):
    def connection(self,headers,body):
        from unittest.mock import Mock
        response=Mock();response.status=200
        response.getheader.side_effect=lambda key:next((v for k,v in headers if k.lower()==key.lower()),None)
        response.getheaders.return_value=headers
        response.read1.side_effect=[body,b'']
        connection=Mock();connection.getresponse.return_value=response
        return connection,response
    def test_30_tls_sender_uses_fixed_host_and_verified_context(self):
        conn,_=self.connection([('Content-Type','application/json')],b'{}')
        with patch('http.client.HTTPSConnection',return_value=conn) as factory:
            s=FixedTLS('notebooklm.google.com');result=s.send('GET','/',{},None,1,100)
        self.assertEqual(result.body,b'{}');self.assertEqual(factory.call_args.args[0],'notebooklm.google.com')
        self.assertTrue(factory.call_args.kwargs['context'].check_hostname);conn.close.assert_called_once()
    def test_31_duplicate_security_header_rejected(self):
        conn,_=self.connection([('Content-Type','application/json'),('content-type','text/html')],b'{}')
        with patch('http.client.HTTPSConnection',return_value=conn):
            with self.assertRaises(Rejected) as e:FixedTLS('notebooklm.google.com').send('GET','/',{},None,1,100)
        self.assertEqual(e.exception.code,'HTTP_RESPONSE_INVALID');conn.close.assert_called_once()
    def test_32_declared_limit_checked_before_body_read(self):
        conn,response=self.connection([('Content-Length','1000')],b'x')
        with patch('http.client.HTTPSConnection',return_value=conn):
            with self.assertRaises(Rejected) as e:FixedTLS('notebooklm.google.com').send('GET','/',{},None,1,100)
        self.assertEqual(e.exception.code,'HTTP_RESPONSE_LIMIT');response.read1.assert_not_called()
    def test_33_actual_body_limit_no_large_allocation(self):
        conn,_=self.connection([],b'x'*101)
        with patch('http.client.HTTPSConnection',return_value=conn):
            with self.assertRaises(Rejected) as e:FixedTLS('notebooklm.google.com').send('GET','/',{},None,1,100)
        self.assertEqual(e.exception.code,'HTTP_RESPONSE_LIMIT')
