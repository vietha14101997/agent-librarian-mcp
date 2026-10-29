"""Personal Local synthetic tests: never invoke Brave, Keychain or live Google."""
import asyncio
from dataclasses import replace
import io
from contextlib import redirect_stderr
import json
import os
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch,AsyncMock
from agent_librarian.gateway.common import Rejected,NAMES
from agent_librarian.gateway.policy import Gateway
from agent_librarian.personal.state import PersonalState,write_private,private_dir
from agent_librarian.personal.storage import PersonalKeychainStore,KeychainFailure
from agent_librarian.personal.browser_auth import login,browser_session,capture_brave,seed_manager
from agent_librarian.personal.runtime import prepare,status,logout,direct_call
from tests.http_fakes import ReplayHTTP,MemoryStore,session,SECRET
ROOT=Path(__file__).resolve().parents[1]

class PersonalTests(unittest.TestCase):
    def setUp(self):
        root=ROOT/'state';root.mkdir(exist_ok=True);self.temp=tempfile.TemporaryDirectory(prefix='p',dir=root)
        self.state=PersonalState(Path(self.temp.name)/'personal',create=True)
        self.s=replace(session(),account_id=self.state.load()['account_id'],expires_at=20000000000)
        self.store=MemoryStore(self.s);self.store.probe=lambda:None
        self.fixture=json.loads((ROOT/'tests/fixtures/research.json').read_text());self.http=ReplayHTTP(self.fixture)
    def tearDown(self):self.temp.cleanup()
    def error(self,code,fn):
        with self.assertRaises(Rejected) as e:fn()
        self.assertEqual(e.exception.code,code);return e.exception
    def authenticated(self):
        async def capture(state,timeout):return self.s
        return asyncio.run(login(self.state,self.store,True,capture=capture,sender=self.http))
    def selected(self):
        self.authenticated();self.state.select('notebook-approved')
    def test_01_fresh_state_private_and_no_auth(self):
        self.assertEqual(self.state.path.stat().st_mode&0o777,0o700);self.assertFalse(self.state.load()['authenticated'])
    def test_02_existing_unrelated_directory_rejected(self):
        p=self.state.path/'unrelated';p.mkdir(mode=0o700);(p/'private.txt').write_text('SYNTHETIC')
        self.error('PERSONAL_DIRECTORY_NOT_EMPTY',lambda:PersonalState(p,create=True))
    def test_03_state_symlink_rejected(self):
        p=self.state.path/'link';p.symlink_to(self.state.path)
        self.error('PERSONAL_PATH_UNSAFE',lambda:PersonalState(p))
    def test_04_nonprivate_state_rejected(self):
        self.state.path.chmod(0o755)
        self.error('PERSONAL_STATE_PERMISSIONS_INVALID',lambda:PersonalState(self.state.path))
        self.state.path.chmod(0o700)
    def test_05_login_requires_explicit_discovery_consent(self):
        self.error('LOGIN_AND_DISCOVERY_CONSENT_REQUIRED',lambda:asyncio.run(login(self.state,self.store,False)))
        self.assertFalse(self.http.calls)
    def test_06_keychain_failure_before_browser(self):
        self.store.probe=lambda:(_ for _ in ()).throw(KeychainFailure('PERSONAL_KEYCHAIN_UNAVAILABLE',-25308))
        capture=AsyncMock()
        error=self.error('PERSONAL_KEYCHAIN_UNAVAILABLE',lambda:asyncio.run(login(self.state,self.store,True,capture=capture)))
        capture.assert_not_called();self.assertEqual(error.os_status,-25308)
    def test_07_login_success_exactly_one_discovery(self):
        result=self.authenticated();self.assertEqual(result['discovery_requests'],1)
        self.assertEqual(sum(c[0]=='POST' for c in self.http.calls),1);self.assertEqual(len(self.http.calls),2);self.assertEqual(self.store.saved,1)
        self.assertEqual(self.state.load()['host'],self.s.host);self.assertTrue(self.state.load()['authenticated'])
    def test_08_login_http_failure_does_not_persist_auth(self):
        self.http.next_reply=TimeoutError()
        self.error('PROVIDER_TIMEOUT',self.authenticated)
        self.assertFalse(self.state.load()['authenticated']);self.assertEqual(self.store.saved,0)
    def test_09_dedicated_profile_only(self):
        self.assertEqual(self.state.profile(),self.state.path/'browser-profile')
        self.assertEqual(self.state.profile().stat().st_mode&0o777,0o700)
    def test_10_login_page_domain_not_query_string(self):
        html=json.dumps({'oPEP7c':'research@example.invalid'})
        self.error('BRAVE_NOT_ON_NOTEBOOK_HOME',lambda:browser_session(html,[],'https://accounts.google.com/?continue=https://notebooklm.google.com','synthetic-account'))
    def test_11_browser_session_only_applicable_secure_cookies(self):
        html=json.dumps({'oPEP7c':'research@example.invalid','SNlM0e':'SYNTHETIC_CSRF','FdrFJe':'-123','cfb2h':'synthetic_build'})
        cookies=[{'name':'SID','value':SECRET,'domain':'.google.com','path':'/','secure':True},
            {'name':'FOREIGN','value':'SYNTHETIC_FOREIGN','domain':'.example.invalid','path':'/','secure':True}]
        result=browser_session(html,cookies,'https://notebooklm.google.com/','synthetic-account')
        self.assertNotIn('FOREIGN',result.cookies);self.assertEqual(result.session_id,'-123')
    def test_12_notebook_content_page_not_login_capture(self):
        self.error('BRAVE_NOT_ON_NOTEBOOK_HOME',lambda:browser_session('',[],'https://notebooklm.google.com/notebook/private','synthetic-account'))
    def test_13_unknown_notebook_not_selectable(self):
        self.authenticated();self.error('NOTEBOOK_NOT_DISCOVERED',lambda:self.state.select('invented-id'))
    def test_14_selection_requires_login(self):self.error('AUTHENTICATION_REQUIRED',lambda:self.state.select('notebook-approved'))
    def test_15_startup_requires_selected_notebook(self):
        self.authenticated();self.error('NOTEBOOK_SELECTION_REQUIRED',lambda:prepare(self.state,self.store,self.http))
    def test_16_one_notebook_allowlist(self):
        self.selected();policy,provider=prepare(self.state,self.store,self.http)
        gateway=Gateway(policy,None,self.state.path,provider=provider)
        with redirect_stderr(io.StringIO()):result=gateway.call(NAMES[1],{'notebook_id':'notebook-second'})
        self.assertEqual(result['code'],'NOTEBOOK_NOT_ALLOWED');gateway.close()
    def test_17_query_requires_exact_approval(self):
        self.selected();result=direct_call(self.state,NAMES[2],{'notebook_id':'notebook-approved','query':'Question'},self.store,self.http)
        self.assertEqual(result['code'],'PERSONAL_QUERY_APPROVAL_REQUIRED')
    def test_18_history_ack_required(self):
        self.selected();self.error('QUERY_HISTORY_ACK_REQUIRED',lambda:self.state.approve_query('Question',False))
    def test_19_approved_query_once_and_citations_mapped(self):
        self.selected();self.state.approve_query('Synthetic question',True)
        result=direct_call(self.state,NAMES[2],{'notebook_id':'notebook-approved','query':'Synthetic question'},self.store,self.http)
        self.assertEqual(result['status'],'OK');self.assertEqual(result['source_ids'],['source-approved'])
        again=direct_call(self.state,NAMES[2],{'notebook_id':'notebook-approved','query':'Synthetic question'},self.store,self.http)
        self.assertEqual(again['code'],'PERSONAL_QUERY_APPROVAL_REQUIRED')
    def test_20_wrong_question_not_authorized(self):
        self.selected();self.state.approve_query('Exact question',True)
        result=direct_call(self.state,NAMES[2],{'notebook_id':'notebook-approved','query':'Other question'},self.store,self.http)
        self.assertEqual(result['code'],'PERSONAL_QUERY_APPROVAL_REQUIRED')
    def test_21_timeout_does_not_restore_query_permit(self):
        self.selected();self.state.approve_query('Synthetic question',True);self.http.next_reply=TimeoutError()
        result=direct_call(self.state,NAMES[2],{'notebook_id':'notebook-approved','query':'Synthetic question'},self.store,self.http)
        self.assertEqual(result['outcome'],'UNKNOWN');self.assertEqual(self.state.load()['query_permit']['state'],'DISPATCHED_NO_AUTOMATIC_RETRY')
    def test_22_logout_disables_existing_provider(self):
        self.selected();policy,provider=prepare(self.state,self.store,self.http)
        result=logout(self.state,self.store);self.assertTrue(self.store.deleted);self.assertFalse(result['provider_sessions_revoked'])
        self.error('SERVICE_DISABLED',provider.list_notebooks);provider.close()
    def test_23_status_offline_and_account_opt_in(self):
        self.authenticated();before=len(self.http.calls)
        result=status(self.state,self.store);self.assertNotIn('account',result);self.assertEqual(result['network_operations'],0)
        self.assertEqual(status(self.state,self.store,True)['account'],'research@example.invalid');self.assertEqual(len(self.http.calls),before)
    def test_24_keychain_account_mismatch(self):
        self.selected();self.store.value=replace(self.s,account_id='wrong-account')
        self.error('ACCOUNT_IDENTITY_MISMATCH',lambda:prepare(self.state,self.store,self.http))
    def test_25_close_prevents_calls(self):
        self.selected();_,provider=prepare(self.state,self.store,self.http);provider.close()
        self.error('SERVICE_DISABLED',provider.list_notebooks)
    def test_26_credential_absent_from_mcp_data_and_receipts(self):
        self.selected();self.fixture['answer']='Synthetic secret '+SECRET;self.state.approve_query('Synthetic question',True)
        policy,provider=prepare(self.state,self.store,self.http);gateway=Gateway(policy,None,self.state.path,provider=provider)
        log=io.StringIO()
        with redirect_stderr(log):result=gateway.call(NAMES[2],{'notebook_id':'notebook-approved','query':'Synthetic question'})
        self.assertNotIn(SECRET,json.dumps(result)+log.getvalue());self.assertIn('[REDACTED]',result['answer']);gateway.close()
    def test_27_administrative_operation_rejected(self):
        self.selected();result=direct_call(self.state,'source_delete',{},self.store,self.http)
        self.assertEqual(result['code'],'FORBIDDEN_OPERATION')
    def test_28_changed_upstream_structure_not_success(self):
        self.selected();self.state.approve_query('Synthetic question',True);self.fixture['mode']='thinking_only'
        result=direct_call(self.state,NAMES[2],{'notebook_id':'notebook-approved','query':'Synthetic question'},self.store,self.http)
        self.assertEqual(result['code'],'UNIMPLEMENTED_SOURCE_GAP');self.assertEqual(result['outcome'],'UNKNOWN')
    def test_29_keychain_osstatus_is_safe_no_plaintext_fallback(self):
        store=PersonalKeychainStore(self.state,helper='/SYNTHETIC/helper')
        error=subprocess.CompletedProcess([],42,b'',b'{"code":"KEYCHAIN_OPERATION_FAILED","os_status":-25308}')
        with patch('subprocess.run',return_value=error),patch('builtins.open',side_effect=AssertionError('No plaintext fallback')):
            result=self.error('PERSONAL_KEYCHAIN_UNAVAILABLE',store.load)
        self.assertEqual(result.os_status,-25308)
    def test_30_private_state_has_no_cookie_material(self):
        self.authenticated()
        self.assertNotIn(SECRET,(self.state.path/'personal.json').read_text()+(self.state.path/'notebooks.json').read_text())
    def test_31_cached_discovery_does_not_repeat_network(self):
        self.selected();before=len(self.http.calls);_,provider=prepare(self.state,self.store,self.http)
        self.assertEqual(len(provider.list_notebooks()['data']['notebooks']),1);self.assertEqual(len(self.http.calls),before);provider.close()
    def test_32_reselection_revokes_old_query(self):
        self.selected();self.state.approve_query('Question',True);self.state.select('notebook-approved')
        self.assertIsNone(self.state.load()['query_permit'])
    def test_33_browser_login_failure_is_sanitized(self):
        class Failing:
            async def __aenter__(self):raise RuntimeError(SECRET)
            async def __aexit__(self,*args):pass
        with patch('pathlib.Path.is_file',return_value=True):
            error=self.error('BRAVE_LOGIN_FAILED',lambda:asyncio.run(capture_brave(self.state,1,launcher=Failing)))
        self.assertNotIn(SECRET,str(error))
    def test_34_cli_auth_commands_are_available(self):
        result=subprocess.run([sys.executable,'-I','-B','-m','agent_librarian','auth','--help'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0);self.assertIn('login',result.stdout);self.assertIn('logout',result.stdout)
    def test_35_personal_mcp_start_without_login_fails_closed(self):
        result=subprocess.run([sys.executable,'-I','-B','-m','agent_librarian','mcp-serve','--provider','personal','--state-dir',str(self.state.path)],capture_output=True,text=True)
        self.assertEqual(result.returncode,2);self.assertIn('AUTHENTICATION_REQUIRED',result.stderr)

    def test_36_saved_session_reused_without_browser_or_discovery(self):
        self.authenticated();before=len(self.http.calls);capture=AsyncMock()
        result=asyncio.run(login(self.state,self.store,True,capture=capture,sender=self.http))
        capture.assert_not_called();self.assertEqual(result['status'],'AUTHENTICATED_REUSED')
        self.assertEqual(result['discovery_requests'],0);self.assertEqual(len(self.http.calls),before)
    def test_37_empty_page_handoff_does_not_cancel_or_close_early(self):
        from agent_librarian.personal.state import read_private
        state=self.state
        html=json.dumps({'oPEP7c':'research@example.invalid','SNlM0e':'SYNTHETIC_CSRF','FdrFJe':'-123','cfb2h':'synthetic_build'})
        class Page:
            url='https://notebooklm.google.com/'
            def on(self,*a):pass
            async def goto(self,*a,**kw):context.pages=[]
            async def evaluate(self,*a):return html
        class Context:
            def __init__(self):self.pages=[Page()];self.browser=None;self.handlers={};self.closed=False
            def on(self,key,callback):self.handlers[key]=callback
            async def cookies(self,*a):return [{'name':'SID','value':SECRET,'domain':'.google.com','secure':True,'path':'/'}]
            async def close(self):self.closed=True;self.handlers['close']()
        context=Context()
        class Launcher:
            async def __aenter__(self):return SimpleNamespace(chromium=SimpleNamespace(launch_persistent_context=AsyncMock(return_value=context)))
            async def __aexit__(self,*a):pass
        async def handoff(_):context.pages=[Page()]
        with patch('pathlib.Path.is_file',return_value=True),patch('asyncio.sleep',side_effect=handoff):
            captured=asyncio.run(capture_brave(state,1,launcher=Launcher))
        self.assertEqual(captured.expected_email,'research@example.invalid')
        events=read_private(state.path/'last-login.json')['events'];kinds=[x['event'] for x in events]
        self.assertLess(kinds.index('session_captured_without_persistence'),kinds.index('controller_cleanup_requested'))
        self.assertTrue(context.closed)
    def test_38_status_exposes_sanitized_login_outcome(self):
        from agent_librarian.personal.progress import LoginProgress
        progress=LoginProgress(self.state,reset=True);progress.event('capture_stopped',code='BRAVE_WINDOW_CLOSED')
        result=status(self.state,None)
        self.assertEqual(result['last_login']['events'][-1]['code'],'BRAVE_WINDOW_CLOSED')
        self.assertNotIn(SECRET,json.dumps(result))

    def test_39_personal_mcp_stdio_synthetic_end_to_end(self):
        import anyio
        from mcp import Client,StdioServerParameters
        self.selected();self.state.approve_query('Synthetic question',True)
        fixture=self.state.path/'synthetic-fixture.json';fixture.write_text(json.dumps(self.fixture))
        async def run():
            params=StdioServerParameters(command=sys.executable,args=['-I','-B',str(ROOT/'tests/personal_mcp_worker.py'),'--state-dir',str(self.state.path),'--fixture',str(fixture)])
            async with Client(params) as client:
                self.assertEqual({x.name for x in (await client.list_tools()).tools},set(NAMES))
                for name,args in [(NAMES[0],{}),(NAMES[1],{'notebook_id':'notebook-approved'}),
                    (NAMES[2],{'notebook_id':'notebook-approved','query':'Synthetic question'}),
                    (NAMES[3],{'notebook_id':'notebook-approved','source_id':'source-approved'})]:
                    result=(await client.call_tool(name,args)).structured_content
                    self.assertEqual(result['status'],'OK',result);self.assertNotIn(SECRET,json.dumps(result))
                result=(await client.call_tool('notebook_delete',{})).structured_content
                self.assertEqual(result['code'],'FORBIDDEN_OPERATION')
                result=(await client.call_tool(NAMES[2],{'notebook_id':'notebook-approved','query':'Synthetic question'})).structured_content
                self.assertEqual(result['code'],'PERSONAL_QUERY_APPROVAL_REQUIRED')
        anyio.run(run)
    def test_40_http_account_mismatch_prevents_discovery_and_persistence(self):
        self.s=replace(self.s,expected_email='other@example.invalid')
        self.error('ACCOUNT_IDENTITY_MISMATCH',self.authenticated)
        self.assertEqual(self.store.saved,0);self.assertEqual(sum(c[0]=='POST' for c in self.http.calls),0)
