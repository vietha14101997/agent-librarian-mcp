"""Managed lifecycle/auth contracts; native CDP test uses synthetic routed pages."""
import json
import os
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from agent_librarian.gateway.common import Rejected
from agent_librarian.gateway.policy import safe_diagnostics
from agent_librarian.personal.state import PersonalState, write_private
from agent_librarian.personal import managed_auth as auth
from agent_librarian.personal.managed_browser import ManagedBrowser, profile_lock, profile_for, install_browser
from agent_librarian.personal.managed_transport import ManagedTransport, ManagedNotebookAdmin
from agent_librarian.personal.runtime import prepare
from agent_librarian.providers.gemini import LIST_RPC, GET_RPC, SOURCE_RPC, QUERY_ENDPOINT, ReadRequest, parse_query, parse_source
from agent_librarian.providers.wire import project_response

EMAIL = 'owner@example.invalid'
BOOKS = [{'notebook_id': 'notebook-test', 'title': 'Synthetic', 'sources': [{'id': 'source-test', 'title': 'Source'}]}]


def frame(method, data):
    return (json.dumps([['wrb.fr', method, json.dumps(data)]]) + '\n').encode()


class ManagedTests(unittest.TestCase):
    def setUp(self):
        # Outside every checkout; tests never open a real user profile.
        self.temp = tempfile.TemporaryDirectory(prefix='librarian-managed-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.state = PersonalState(self.root / 'state', create=True)
        self.paths = patch('agent_librarian.personal.managed_browser.user_data', return_value=self.root / 'data')
        self.paths.start(); self.addCleanup(self.paths.stop)

    def bind(self):
        auth.accept(self.state, EMAIL, BOOKS, {'bytes_read': 123, 'frames': 1})

    def error(self, code, function):
        with self.assertRaises(Rejected) as result: function()
        self.assertEqual(result.exception.code, code)
        return result.exception

    def test_profile_is_private_persistent_and_outside_checkout_or_state(self):
        p = profile_for(self.state)
        (p / 'synthetic-marker').write_text('retained')
        independent = PersonalState(self.state.path)
        self.assertEqual(profile_for(independent), p)
        self.assertFalse(p.is_relative_to(self.state.path))
        self.assertEqual(p.stat().st_mode & 0o777, 0o700)
        with profile_lock(p): self.error('MANAGED_BROWSER_BUSY', lambda: profile_lock(p).__enter__())

    def test_repository_profile_location_rejected(self):
        (self.root / '.git').mkdir()
        self.error('MANAGED_PROFILE_INSIDE_REPOSITORY', lambda: profile_for(self.state))

    def test_endpoint_never_accepts_remote_host_or_symlink(self):
        b = ManagedBrowser(self.state)
        p = b.profile / 'DevToolsActivePort'
        for value in ('9222\nws://attacker.invalid/devtools/browser/x', '0\n/devtools/browser/x', '9222\n/other/x'):
            p.write_text(value); self.error('MANAGED_BROWSER_ENDPOINT_INVALID', b._endpoint)
        p.write_text('43210\n/devtools/browser/synthetic-id')
        self.assertEqual(b._endpoint(), 'ws://127.0.0.1:43210/devtools/browser/synthetic-id')
        p.unlink(); p.symlink_to(self.root / 'foreign')
        self.error('MANAGED_BROWSER_ENDPOINT_INVALID', b._endpoint)

    def test_no_download_or_launch_without_existing_executable(self):
        engine = SimpleNamespace(chromium=SimpleNamespace(executable_path=str(self.root / 'missing')), stop=Mock())
        with patch('subprocess.Popen') as popen:
            b = ManagedBrowser(self.state, engine_factory=lambda: SimpleNamespace(start=lambda: engine))
            self.error('MANAGED_CHROMIUM_INSTALL_APPROVAL_REQUIRED', b.__enter__)
            popen.assert_not_called()
        engine.stop.assert_called_once()
        with profile_lock(b.profile): pass  # Startup failure released the lease.

    def test_close_does_not_start_new_browser(self):
        b = ManagedBrowser(self.state, start_if_missing=False)
        b.engine = Mock()
        self.error('MANAGED_BROWSER_NOT_RUNNING', b._connect_or_start)
        b.engine.chromium.connect_over_cdp.assert_not_called()

    def test_endpoint_ownership_is_proven_before_close(self):
        browser = Mock(); browser.new_browser_cdp_session.return_value.send.return_value = {'arguments': ['--user-data-dir=/foreign']}
        b = ManagedBrowser(self.state); b.engine = SimpleNamespace(chromium=Mock())
        b.engine.chromium.connect_over_cdp.return_value = browser
        self.error('MANAGED_BROWSER_OWNERSHIP_MISMATCH', lambda: b._attach('ws://127.0.0.1:43210/devtools/browser/synthetic'))
        browser.close.assert_not_called()

    def test_cached_status_never_claims_live_authentication(self):
        self.bind(); result = auth.status(self.state)
        self.assertFalse(result['authenticated']); self.assertTrue(result['cached_authenticated'])
        self.assertEqual(result['status'], 'OFFLINE_CACHED'); self.assertEqual(result['network_operations'], 0)
        self.assertNotIn('account', result); self.assertEqual(auth.status(self.state, True)['account'], EMAIL)

    def test_identity_mismatch_never_rebinds(self):
        self.bind()
        page = SimpleNamespace(url='https://notebook.google.com/', evaluate=lambda _: 'other@example.invalid')
        self.error('ACCOUNT_IDENTITY_MISMATCH', lambda: auth.verify(self.state, Mock(), page, EMAIL))
        self.assertEqual(auth.binding(self.state), EMAIL)

    def test_account_homepage_is_not_rpc_verification(self):
        page = SimpleNamespace(url='https://notebook.google.com/', evaluate=lambda _: EMAIL)
        with patch.object(ManagedTransport, 'request', side_effect=Rejected('GOOGLE_RPC_REJECTED')) as rpc:
            self.error('GOOGLE_RPC_REJECTED', lambda: auth.verify(self.state, Mock(), page, None))
            self.assertEqual(rpc.call_count, 1)
        self.assertFalse(self.state.load()['authenticated'])

    def test_interactive_login_once_then_noninteractive_verified_reuse(self):
        page = SimpleNamespace(url='https://notebook.google.com/', evaluate=lambda _: EMAIL, is_closed=lambda: False)
        browser = Mock(); browser.context.pages = [page]; browser.page.return_value = page
        browser.__enter__ = Mock(return_value=browser); browser.__exit__ = Mock(return_value=False)
        factory = Mock(return_value=browser)
        with patch.object(auth, 'verify', return_value=(EMAIL, BOOKS, {'frames': 1})) as verify:
            self.assertEqual(auth.login(self.state, True, browser_factory=factory)['status'], 'AUTHENTICATED_VERIFIED')
            self.assertEqual(auth.login(self.state, True, browser_factory=factory)['status'], 'AUTHENTICATED_VERIFIED')
        self.assertEqual(verify.call_count, 2)
        self.assertEqual(sum(call.kwargs.get('headless') is False for call in factory.call_args_list), 1)
        self.assertEqual(auth.binding(PersonalState(self.state.path)), EMAIL)

    def test_expired_refresh_has_exact_two_read_only_attempt_budget(self):
        self.bind(); browser = Mock(); browser.__enter__ = Mock(return_value=browser); browser.__exit__ = Mock(return_value=False)
        with patch.object(auth, 'verify', side_effect=Rejected('AUTHENTICATION_EXPIRED')) as verify:
            result = auth.check(self.state, browser_factory=lambda _: browser)
        self.assertEqual(result['status'], 'SESSION_EXPIRED'); self.assertEqual(verify.call_count, 2)
        self.assertEqual(browser.page.call_count, 2); self.assertEqual(auth.binding(self.state), EMAIL)

    def test_ordinary_refresh_preserves_permit_mapping_and_generation(self):
        self.bind(); self.state.select('notebook-test'); self.state.approve_query('New question', True)
        before = self.state.load(); auth.accept(self.state, EMAIL, BOOKS, {})
        self.assertEqual(self.state.load(), before)

    def test_health_distinguishes_offline_browser_rpc_and_login(self):
        self.bind()
        for code, expected in [('MANAGED_BROWSER_OFFLINE', 'OFFLINE'), ('CDP_DISCONNECTED', 'BROWSER_TEMPORARILY_UNAVAILABLE'),
                               ('GOOGLE_RPC_REJECTED', 'GOOGLE_RPC_REJECTED'), ('REAUTHENTICATION_REQUIRED', 'REAUTHENTICATION_REQUIRED')]:
            def fail(_): raise Rejected(code)
            self.assertEqual(auth.check(self.state, browser_factory=fail)['status'], expected)

    def test_existing_brave_connection_does_not_override_managed_selection(self):
        self.bind(); self.state.select('notebook-test')
        write_private(self.state.path / 'browser-connection.json', {'status': 'SYNTHETIC_OLD_CONNECTION'})
        with patch('agent_librarian.personal.runtime.PersonalKeychainStore', side_effect=AssertionError('No cookie store')):
            _, provider = prepare(self.state)
            self.assertIsInstance(provider.sessions, ManagedTransport)
            provider.close()

    def test_cdp_disconnect_has_no_replay_and_query_is_unknown(self):
        self.bind()
        transport = ManagedTransport(self.state, EMAIL, {'notebook-test': {'sources': {'source-test': 'Source'}}})
        cdp = Mock(); cdp.send.side_effect = RuntimeError('SYNTHETIC_SECRET')
        transport.browser = Mock(); transport.page = Mock(); transport.cdp = cdp
        # Exercise the real provider's UNKNOWN contract, including a lost start ack.
        from agent_librarian.providers.gemini import GeminiResearchProvider, AccountCapability
        provider = GeminiResearchProvider(transport, AccountCapability(transport.account_id), transport.notebooks)
        error = self.error('CDP_DISCONNECTED', lambda: provider.query('notebook-test', 'New question', ['source-test']))
        self.assertEqual(error.outcome, 'UNKNOWN'); self.assertEqual(cdp.send.call_count, 1)
        self.assertNotIn('SYNTHETIC_SECRET', str(error)); transport.close()

    def test_only_bounded_numeric_and_enumerated_diagnostics_escape(self):
        self.assertEqual(safe_diagnostics({'cookie': 'secret', 'stage': 'secret', 'rpc': 'secret', 'frames': 2, 'bytes_read': True}), {'frames': 2})
        self.assertEqual(install_browser()['status'], 'DOWNLOAD_APPROVAL_REQUIRED')

    def test_fresh_python_process_uses_managed_selection_and_four_tool_policy(self):
        self.bind(); self.state.select('notebook-test')
        script = '''
import json,sys
from agent_librarian.personal.state import PersonalState
from agent_librarian.personal.runtime import direct_call
from agent_librarian.personal.managed_transport import ManagedTransport
def request(self, r): return [['Synthetic', [[['source-test'], 'Source']], 'notebook-test']]
ManagedTransport.request = request
state = PersonalState(sys.argv[1])
print(json.dumps(direct_call(state, 'librarian_get_notebook', {'notebook_id':'notebook-test'})))
'''
        result = subprocess.run([sys.executable, '-I', '-B', '-c', script, str(self.state.path)], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        body = json.loads(result.stdout); self.assertEqual(body['status'], 'OK')
        self.assertEqual(body['provider'], 'GEMINI_MANAGED_CDP_UNVERIFIED')
        self.assertEqual(body['sources'][0]['source_id'], 'source-test')

    def test_new_default_login_does_not_construct_legacy_store(self):
        from agent_librarian.cli import parser
        from agent_librarian.personal.commands import dispatch
        args = parser().parse_args(['auth', 'login', '--state-dir', str(self.state.path), '--consent-discovery'])
        with patch.object(auth, 'login', return_value={'status': 'SYNTHETIC'}) as login, patch('agent_librarian.personal.commands.PersonalKeychainStore', side_effect=AssertionError()):
            self.assertEqual(dispatch(args)['status'], 'SYNTHETIC'); login.assert_called_once()

    def test_equal_length_final_frames_keep_citations(self):
        detail = [None] * 6; detail[5] = [[['source-test']]]
        citation = [None, detail]
        row = lambda citations: [['same answer', None, None, None, [None, None, None, citations, 1]]]
        raw = b")]}'\n" + frame(None, row([])) + frame(None, row([citation])) + frame(None, row([]))
        parsed = parse_query(project_response([raw], None).decode(), ['source-test'])
        self.assertEqual(parsed['citations'][0]['source_id'], 'source-test')

    def test_google_rpc_error_code_is_distinct_from_malformed_frame(self):
        raw = b")]}'\n" + json.dumps([['wrb.fr', LIST_RPC, None, None, None, [8]]]).encode() + b'\n'
        error = self.error('GOOGLE_RPC_REJECTED', lambda: project_response([raw], LIST_RPC))
        self.assertEqual(error.diagnostics['rpc_error_code'], 8)

    def test_truncated_marker_is_distinct_from_malformed_frame(self):
        self.error('HTTP_FRAME_TRUNCATED', lambda: project_response([b")]}'\n123\n"], LIST_RPC))
        self.error('PROVIDER_PROTOCOL_ERROR', lambda: project_response([b")]}'\n{bad}\n"], LIST_RPC))

    def test_logout_clears_dedicated_context_and_invalidates_existing_provider(self):
        self.bind(); self.state.select('notebook-test')
        _, provider = prepare(self.state)
        browser = Mock(); browser.__enter__ = Mock(return_value=browser); browser.__exit__ = Mock(return_value=False)
        with patch.object(auth, 'ManagedBrowser', return_value=browser): result = auth.logout(self.state)
        browser.context.clear_cookies.assert_called_once(); browser.close_browser.assert_called_once()
        self.assertEqual(result['status'], 'LOGGED_OUT'); self.assertTrue(result['legacy_keychain_unchanged'])
        self.error('SERVICE_DISABLED', provider.list_notebooks); provider.close()
        self.assertEqual(auth.binding(self.state), EMAIL)

    def test_source_shape_diagnostics_do_not_include_source_body(self):
        from agent_librarian.providers.gemini import GeminiResearchProvider, AccountCapability
        transport = Mock(account_identity=lambda: 'account-test', request=lambda _: ['SYNTHETIC_BODY'], diagnostics={'frames': 1})
        provider = GeminiResearchProvider(transport, AccountCapability('account-test'), {'notebook-test': {'sources': {'source-test': 'Source'}}})
        error = self.error('UNIMPLEMENTED_SOURCE_GAP', lambda: provider.get_source('notebook-test', 'source-test'))
        self.assertEqual(error.diagnostics['stage'], 'SOURCE_DECODE'); self.assertNotIn('SYNTHETIC_BODY', json.dumps(error.diagnostics))


@unittest.skipUnless(os.environ.get('KN_TEST_CHROMIUM_BIN'), 'Native CDP test requires an explicitly selected test Chromium binary')
class NativeCDPTests(unittest.TestCase):
    """No Google traffic: every page/request is fulfilled with synthetic data."""
    setUp = ManagedTests.setUp
    def factory(self, state, **kwargs):
        if os.environ.get('KN_TEST_MANAGED_DEFAULT') == '1': return ManagedBrowser(state, **kwargs)
        from playwright.sync_api import sync_playwright
        def start():
            engine = sync_playwright().start()
            chromium = SimpleNamespace(executable_path=os.environ['KN_TEST_CHROMIUM_BIN'], connect_over_cdp=engine.chromium.connect_over_cdp)
            return SimpleNamespace(chromium=chromium, stop=engine.stop)
        return ManagedBrowser(state, engine_factory=lambda: SimpleNamespace(start=start), **kwargs)

    def test_native_launch_reconnect_persistence_cdp_rpc_and_upload(self):
        from agent_librarian.personal.source_admin import SourceAdmin
        marker = profile_for(self.state) / 'synthetic-marker'; marker.write_text('retain')
        if os.environ.get('KN_TEST_MANAGED_DEFAULT') == '1':
            self.assertEqual(install_browser(approve=True)['status'], 'MANAGED_CHROMIUM_REUSED')
        with self.factory(self.state, keep_open=True) as browser:
            page = browser.context.new_page(); page.goto('about:blank')
            process = browser.process
            def cleanup():
                if process.poll() is None: process.terminate()
                process.wait(timeout=10)
            self.addCleanup(cleanup)
        child = '''
import json,sys
from pathlib import Path
from unittest.mock import patch
from agent_librarian.personal.state import PersonalState
from agent_librarian.personal.managed_browser import ManagedBrowser
with patch('agent_librarian.personal.managed_browser.user_data', return_value=Path(sys.argv[2])):
    with ManagedBrowser(PersonalState(sys.argv[1]), start_if_missing=False) as browser:
        print(json.dumps({'reconnected': not browser.launched, 'value': browser.context.pages[0].evaluate('6*7')}))
'''
        result = subprocess.run([sys.executable, '-c', child, str(self.state.path), str(self.root / 'data')], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {'reconnected': True, 'value': 42})
        with self.factory(PersonalState(self.state.path), start_if_missing=False) as browser:
            self.assertFalse(browser.launched)
            args = browser.browser.new_browser_cdp_session().send('Browser.getBrowserCommandLine')['arguments']
            self.assertIn('--remote-debugging-port=0', args)
            self.assertIn('--remote-debugging-address=127.0.0.1', args)
            calls = []
            sources = [[[f'source-{i}'], f'doc-{i}.md', [None, None, None, None, 11, 'x' * 5000], [None, 2]] for i in range(53)]
            html = '<script>WIZ_global_data = ' + json.dumps({'oPEP7c': EMAIL, 'SNlM0e': 'synthetic-token', 'FdrFJe': '123', 'cfb2h': 'synthetic-build'}) + ';</script>'
            def route_handler(route):
                request = route.request; calls.append(request.method)
                if request.method == 'GET': route.fulfill(status=200, content_type='text/html', body=html); return
                if '/upload/_/' in request.url:
                    headers = {'x-goog-upload-url': 'https://notebook.google.com/upload/_/?upload_id=SYNTHETIC'}
                    route.fulfill(status=200, headers=headers, body=''); return
                if 'GenerateFreeFormStreamed' in request.url:
                    progress = [['thinking ' * 1800, None, None, None, [None, None, None, [], 0]]]
                    detail = [None] * 6; detail[5] = [[['source-0']]]
                    answer = [['Synthetic final answer', None, None, None, [None, None, None, [[None, detail]], 1]]]
                    uncited = [['Synthetic final answer', None, None, None, [None, None, None, [], 1]]]
                    route.fulfill(status=200, content_type='application/json', body=b")]}'\n" + frame(None, progress) * 200 + frame(None, uncited) + frame(None, answer) + frame(None, uncited)); return
                from urllib.parse import urlsplit, parse_qs
                rpc = parse_qs(urlsplit(request.url).query)['rpcids'][0]
                if rpc == GET_RPC: value = [['Synthetic', sources, 'notebook-test']]
                elif rpc == SOURCE_RPC: value = [[['source-0'], 'Source', []], None, None, [[[0, 60000, 'passage ' * 8000]]]]
                elif rpc == 'o4cbdc': value = [[[['source-new']]]]
                elif rpc == 'CCqFvf': value = ['New Notebook', None, 'created-test']
                else: value = [[['Synthetic', sources, 'notebook-test']]]
                route.fulfill(status=200, content_type='application/json', body=b")]}'\n" + frame(rpc, value))
            browser.context.route('**/*', route_handler)
            page = browser.page()
            browser.context.add_cookies([{'name':'synthetic-persistence','value':'not-a-credential','url':'https://notebook.google.com/','expires':2000000000}])
            self.assertEqual(auth.page_identity(page), EMAIL)
            transport = ManagedTransport(self.state, EMAIL, {'notebook-test': {'sources': {f'source-{i}': '' for i in range(53)}}}, browser=browser, page=page)
            result = transport.request(ReadRequest('rpc', GET_RPC, '/notebook/notebook-test', ['notebook-test', None, [2], None, 0]))
            self.assertEqual(len(result[0][1]), 53); self.assertGreater(transport.diagnostics['bytes_read'], 131072)
            result = transport.request(ReadRequest('rpc', SOURCE_RPC, '/', [['source-0'], [2], [2]]))
            self.assertEqual(parse_source(result, 'source-0')['content'], 'passage ' * 8000)
            params = [[[[sid]] for sid in ['source-0']], 'Synthetic question', None, [2, None, [1]], '00000000-0000-4000-8000-000000000000']
            result = transport.request(ReadRequest('stream', QUERY_ENDPOINT, '/notebook/notebook-test', params))
            self.assertEqual(parse_query(result, ['source-0'])['citations'][0]['source_id'], 'source-0')
            self.assertGreater(transport.diagnostics['bytes_read'], 2097152)
            self.assertEqual(transport.diagnostics['rpc'], 'QUERY_STREAM')
            notebook_admin = ManagedNotebookAdmin(self.state, EMAIL, {}, browser=browser, page=page)
            self.assertEqual(len(notebook_admin.discover()[0]['sources']), 53)
            self.assertEqual(notebook_admin.create('New Notebook'), 'created-test')
            notebook_admin.close()
            admin = SourceAdmin(transport, 'notebook-test')
            self.assertEqual(admin.register('notebook-test', 'synthetic.md'), 'source-new')
            url = admin.start_upload('notebook-test', 'synthetic.md', 4, 'source-new')
            token = admin.stage(b'data'); admin.finalize(url, token, 4)
            self.assertEqual(calls.count('POST'), 8)
            admin.close(); browser.close_browser()
        self.assertEqual(marker.read_text(), 'retain')
        with self.factory(self.state) as browser:
            self.assertTrue(browser.launched)
            cookies = browser.context.cookies(['https://notebook.google.com/'])
            self.assertEqual([(c['name'],c['value']) for c in cookies], [('synthetic-persistence','not-a-credential')])
        self.assertEqual(marker.read_text(), 'retain')
