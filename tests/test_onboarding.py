"""Synthetic onboarding, no Google, research queries, Keychain or real browser."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from agent_librarian.gateway.common import NAMES, Rejected
from agent_librarian.onboarding import Onboarding, registration_contract
from agent_librarian.personal.state import PersonalState, write_private
from agent_librarian.projects import ProjectMappings
from agent_librarian.project_runtime import ProjectGateway

ROOT = Path(__file__).resolve().parents[1]
EMAIL = 'owner@example.invalid'


class Admin:
    expected_email = EMAIL
    def __init__(self, books):
        self.books = books
        self.calls = []
        self.failure = None
        self.hidden = False
        self.closed = False
    def discover(self):
        self.calls.append('discover')
        if self.failure == 'discover':
            raise Rejected('BROWSER_REQUEST_LOST')
        return self.books
    def create(self, title):
        self.calls.append(('create', title))
        if self.failure == 'create':
            raise Rejected('BROWSER_REQUEST_LOST')
        if self.failure == 'interrupt':
            raise KeyboardInterrupt()
        if self.failure == 'invalid-id':
            return '../invalid'
        if not self.hidden:
            self.books.append({'notebook_id': 'actual-returned-id', 'title': title, 'sources': []})
        return 'actual-returned-id'
    def close(self):
        self.closed = True


class OnboardingTests(unittest.TestCase):
    def setUp(self):
        (ROOT/'state').mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/'state')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.project = self.root/'project'; self.project.mkdir()
        self.home = self.root/'installation'
        self.state = PersonalState(self.root/'personal', create=True)
        config = self.state.load(); config['authenticated'] = True; self.state.save(config)
        self.account = config['account_id']
        # Deliberately matching title is second; neither order nor similarity is selection.
        self.books = [{'notebook_id': 'first-id', 'title': 'Unrelated', 'sources': []},
                      {'notebook_id': 'matching-title-id', 'title': 'project', 'sources': []}]
        write_private(self.state.path/'notebooks.json', {'account_id': self.account, 'notebooks': self.books})
        self.admin = Admin(self.books)
        self.onboard = Onboarding(self.project, self.home, self.state.path, lambda _: self.admin)
        self.maps = ProjectMappings(self.home)

    def options(self, **extra):
        values = dict(choice='new', approve=True, title='Owner-approved title',
                      account_id=self.account, account_email=EMAIL,
                      operation_id='1'*32, experimental_browser_create=True)
        values.update(extra)
        return values

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def reject(self, code, **options):
        with self.assertRaises(Rejected) as error:
            self.onboard.run(**options)
        self.assertTrue(error.exception.code.startswith(code), error.exception.code)

    def test_default_question_and_skip_need_no_auth_and_make_no_changes(self):
        onboarding = Onboarding(self.project, self.home, self.root/'absent', lambda _: self.fail('No credentials'))
        before = self.snapshot()
        result = onboarding.run()
        self.assertEqual(result['choices'], ['existing', 'new', 'skip'])
        self.assertEqual(result['proposed_title'], 'project — Research')
        self.assertEqual(onboarding.run(choice='skip', discover=True, approve=True)['status'], 'SKIPPED')
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.home.exists())

    def test_existing_requires_explicit_selection_even_for_single_book(self):
        for books in (self.books, self.books[:1]):
            write_private(self.state.path/'notebooks.json', {'account_id': self.account, 'notebooks': books})
            self.assertEqual(self.onboard.run(choice='existing')['status'], 'NOTEBOOK_SELECTION_REQUIRED')
            self.reject('EXPLICIT_NOTEBOOK_SELECTION_REQUIRED', choice='existing', approve=True, account_id=self.account)
            self.assertEqual(self.maps.resolve(self.project)['status'], 'PROJECT_NOT_MAPPED')
        self.assertFalse(self.admin.calls)

    def test_inventory_discovery_does_not_map_or_reset_global_state(self):
        before = self.state.config_path.read_bytes()
        result = self.onboard.run(choice='existing', discover=True)
        self.assertEqual(result['origin'], 'LIVE_ACCOUNT_DISCOVERY')
        self.assertEqual(len(result['notebooks']), 2)
        self.assertEqual(self.admin.calls, ['discover'])
        self.assertEqual(before, self.state.config_path.read_bytes())
        self.assertFalse(self.maps.path.exists())

    def test_explicit_choice_maps_only_owner_selected_id_and_verifies(self):
        self.onboard.run(choice='existing', discover=True)
        result = self.onboard.run(choice='existing', approve=True, notebook_id='first-id', account_id=self.account)
        self.assertTrue(result['mapping_verified'])
        self.assertEqual(self.maps.resolve(self.project)['notebook_ids'], ['first-id'])
        self.assertEqual(list(self.project.iterdir()), [])
        self.assertEqual(result['source_uploads'], 0)

    def test_existing_foreign_account_or_unknown_id_rejected_without_mapping(self):
        self.reject('ACCOUNT_IDENTITY_MISMATCH', choice='existing', approve=True, notebook_id='first-id', account_id='foreign')
        self.reject('ACCOUNT_CONFIRMATION_REQUIRED', choice='existing', approve=True, notebook_id='first-id')
        self.reject('NOTEBOOK_NOT_DISCOVERED', choice='existing', approve=True, notebook_id='invented-id', account_id=self.account)
        self.assertFalse(self.maps.path.exists())
        self.assertFalse(self.admin.calls)

    def test_cache_account_mismatch_and_duplicate_ids_fail_closed(self):
        write_private(self.state.path/'notebooks.json', {'account_id': 'foreign', 'notebooks': self.books})
        self.reject('ACCOUNT_IDENTITY_MISMATCH', choice='existing')
        write_private(self.state.path/'notebooks.json', {'account_id': self.account, 'notebooks': self.books*2})
        self.reject('NOTEBOOK_INVENTORY_INVALID', choice='existing')
        self.assertFalse(self.maps.path.exists())

    def test_valid_inherited_mapping_reused_without_admin_or_child_write(self):
        self.maps.change(self.root, ['first-id'])
        self.onboard.admin_factory = lambda _: self.fail('No browser or Keychain access')
        before = self.snapshot()
        result = self.onboard.run(**self.options())
        self.assertTrue(result['reused'])
        self.assertEqual(result['mapping']['mapping_project'], str(self.root))
        self.assertEqual(before, self.snapshot())

    def test_stale_mapping_or_missing_auth_reports_review_without_replacement(self):
        self.maps.change(self.project, ['no-longer-discovered'])
        before = self.maps.path.read_bytes()
        self.assertEqual(self.onboard.run(choice='new')['status'], 'MAPPING_REQUIRES_REVIEW')
        config = self.state.load(); config['authenticated'] = False; self.state.save(config)
        self.assertEqual(self.onboard.run(choice='new')['status'], 'MAPPING_REQUIRES_CONNECTION')
        self.assertEqual(before, self.maps.path.read_bytes())
        self.assertFalse(self.admin.calls)

    def test_new_proposal_shows_account_title_and_needs_approval(self):
        before = self.snapshot()
        result = self.onboard.run(choice='new')
        self.assertEqual(before, self.snapshot())
        self.assertFalse(self.home.exists())
        self.assertEqual(result['status'], 'CREATION_APPROVAL_REQUIRED')
        self.assertEqual(result['account_email'], EMAIL)
        self.assertEqual(result['account_id'], self.account)
        self.assertEqual(len(result['operation_id']), 32)
        self.assertFalse(self.admin.calls)
        self.assertFalse(self.onboard.receipt_path.exists())
        self.assertFalse(self.maps.path.exists())

    def test_account_and_title_confirmation_before_creation(self):
        for extra, code in (({'account_email': 'other@example.invalid'}, 'OWNER_ACCOUNT_CONFIRMATION_REQUIRED'),
                            ({'account_id': None}, 'OWNER_ACCOUNT_CONFIRMATION_REQUIRED'),
                            ({'title': None}, 'CONFIRMED_TITLE_AND_OPERATION_ID_REQUIRED'),
                            ({'operation_id': None}, 'CONFIRMED_TITLE_AND_OPERATION_ID_REQUIRED'),
                            ({'title': 'bad\ntitle'}, 'NOTEBOOK_TITLE_INVALID')):
            self.reject(code, **self.options(**extra))
        self.assertFalse(self.admin.calls)
        self.assertFalse(self.onboard.receipt_path.exists())

    def test_manual_default_does_not_dispatch_or_map(self):
        result = self.onboard.run(**self.options(experimental_browser_create=False))
        self.assertEqual(result['status'], 'MANUAL_CREATION_REQUIRED')
        self.assertEqual(result['account_email'], EMAIL)
        self.assertFalse(self.admin.calls)
        self.assertFalse(self.onboard.receipt_path.exists())
        self.assertFalse(self.maps.path.exists())

    def test_create_uses_actual_returned_id_and_verifies_mapping(self):
        before = self.state.config_path.read_bytes()
        result = self.onboard.run(**self.options())
        self.assertTrue(result['mapping_verified'])
        self.assertEqual(result['notebook_id'], 'actual-returned-id')
        self.assertEqual(self.admin.calls, [('create', 'Owner-approved title'), 'discover'])
        self.assertEqual(self.maps.resolve(self.project)['notebook_ids'], ['actual-returned-id'])
        self.assertEqual(self.onboard.receipt()['state'], 'MAPPED')
        self.assertEqual(before, self.state.config_path.read_bytes())
        self.assertFalse(result['creation_live_verified'])
        self.assertTrue(self.admin.closed)
        self.onboard.run(**self.options())
        self.assertEqual(len([c for c in self.admin.calls if isinstance(c, tuple)]), 1)

    def test_failed_uncertain_interrupted_and_malformed_creation_never_replays(self):
        for failure in ('create', 'interrupt', 'invalid-id'):
            with self.subTest(failure=failure):
                self.admin.failure = failure
                self.reject('CREATION_OUTCOME_UNKNOWN', **self.options())
                self.assertEqual(self.onboard.receipt()['state'], 'UNKNOWN')
                calls = list(self.admin.calls)
                # A fresh process/object and a different operation ID still cannot replay.
                other = Onboarding(self.project, self.home, self.state.path, lambda _: self.admin)
                self.assertEqual(other.run(**self.options(operation_id='2'*32))['status'], 'CREATION_REQUIRES_REVIEW')
                self.assertEqual(self.admin.calls, calls)
                self.assertEqual(self.maps.resolve(self.project)['status'], 'PROJECT_NOT_MAPPED')
                self.onboard.receipt_path.unlink()  # Synthetic scenario reset only.

    def test_receipt_is_durable_before_dispatch_and_contains_no_credentials(self):
        original = self.admin.create
        def create(title):
            record = self.onboard.receipt()
            self.assertEqual(record['state'], 'DISPATCHED')
            self.assertEqual(record['account_email'], EMAIL)
            self.assertIsNone(record['notebook_id'])
            return original(title)
        self.admin.create = create
        self.onboard.run(**self.options())
        record = self.onboard.receipt()
        self.assertEqual(set(record), {'schema_version', 'project', 'operation_id', 'account_id', 'account_email', 'title', 'state', 'notebook_id'})

    def test_discovery_failure_after_creation_preserves_id_for_recovery(self):
        self.admin.failure = 'discover'
        self.reject('BROWSER_REQUEST_LOST', **self.options())
        self.assertEqual(self.onboard.receipt()['notebook_id'], 'actual-returned-id')
        self.assertEqual(self.onboard.receipt()['state'], 'CREATED')
        self.assertFalse(self.maps.path.exists())
        self.admin.failure = None
        result = self.onboard.run(choice='recover', approve=True, account_id=self.account, account_email=EMAIL)
        self.assertTrue(result['mapping_verified'])
        self.assertFalse(result['creation_replayed'])
        self.assertEqual(len([c for c in self.admin.calls if isinstance(c, tuple)]), 1)

    def test_unknown_outcome_recovery_requires_explicit_owner_id(self):
        self.admin.failure = 'create'
        self.reject('CREATION_OUTCOME_UNKNOWN', **self.options())
        self.admin.failure = None
        self.reject('OWNER_ACCOUNT_CONFIRMATION_REQUIRED', choice='recover', account_id=self.account, account_email=EMAIL)
        self.reject('EXPLICIT_NOTEBOOK_SELECTION_REQUIRED', choice='recover', approve=True, account_id=self.account, account_email=EMAIL)
        result = self.onboard.run(choice='recover', approve=True, account_id=self.account, account_email=EMAIL, notebook_id='first-id')
        self.assertEqual(result['notebook_id'], 'first-id')
        self.assertEqual(self.admin.calls, [('create', 'Owner-approved title'), 'discover'])
        self.maps.change(self.project)
        self.assertEqual(self.onboard.run(**self.options())['status'], 'CREATION_REQUIRES_REVIEW')

    def test_known_receipt_cannot_be_rebound_to_another_id(self):
        self.admin.hidden = True
        self.reject('CREATED_NOTEBOOK_NOT_DISCOVERED', **self.options())
        self.reject('CREATION_RECEIPT_NOTEBOOK_MISMATCH', choice='recover', approve=True, account_id=self.account,
                    account_email=EMAIL, notebook_id='first-id')
        self.assertFalse(self.maps.path.exists())

    def test_mapping_failure_keeps_created_id_and_does_not_create_on_retry(self):
        with patch.object(self.onboard, 'link', side_effect=OSError('Synthetic disk failure')):
            with self.assertRaises(OSError):
                self.onboard.run(**self.options())
        self.assertEqual(self.onboard.receipt()['state'], 'CREATED')
        self.assertEqual(self.onboard.run(**self.options())['status'], 'CREATION_REQUIRES_REVIEW')
        self.assertEqual(len([c for c in self.admin.calls if isinstance(c, tuple)]), 1)

    def test_dry_run_never_accesses_credentials_or_writes(self):
        self.onboard.admin_factory = lambda _: self.fail('No auth')
        before = self.snapshot()
        self.assertEqual(self.onboard.run(**self.options(dry_run=True, discover=True))['status'], 'PREVIEW')
        self.assertEqual(before, self.snapshot())

    def test_missing_connection_and_disabled_state_fail_without_mapping(self):
        self.onboard.admin_factory = lambda _: (_ for _ in ()).throw(Rejected('BROWSER_CONNECTION_REQUIRED'))
        self.reject('BROWSER_CONNECTION_REQUIRED', choice='new')
        (self.state.path/'DISABLED').touch()
        self.reject('SERVICE_DISABLED', **self.options())
        self.assertFalse(self.onboard.receipt_path.exists())
        self.assertFalse(self.maps.path.exists())

    def test_unmapped_gateway_still_denied_before_authentication(self):
        self.onboard.run(choice='skip')
        gateway = ProjectGateway(self.project, self.home, self.root/'missing')
        for name in NAMES:
            self.assertEqual(gateway.call(name, {})['code'], 'PROJECT_NOT_MAPPED')
        self.assertEqual(gateway.call('librarian_create_notebook', {})['code'], 'FORBIDDEN_OPERATION')

    def test_neutral_contract_works_without_client_auth_or_configuration_writes(self):
        before = self.snapshot()
        result = registration_contract(self.project, self.home, self.root/'absent')
        self.assertEqual(result['tools'], list(NAMES))
        self.assertEqual(result['transport'], 'stdio')
        self.assertEqual(result['interpreter'], result['command'])
        self.assertEqual(result['distribution'], 'agent-librarian-mcp')
        self.assertIn(str(self.project), result['args'])
        self.assertTrue(Path(result['skill_source']).is_file())
        self.assertEqual(before, self.snapshot())

    def test_fresh_cli_question_skip_and_contract_need_no_agent_client(self):
        base = [sys.executable, '-I', '-B', '-m', 'agent_librarian', 'setup']
        for action, extra, expected in [('onboard', [], 'CHOICE_REQUIRED'),
                                        ('onboard', ['--choice', 'skip'], 'SKIPPED'),
                                        ('contract', [], 'CONTRACT')]:
            result = subprocess.run(base+[action, '--project', str(self.project), '--home', str(self.home),
                '--state-dir', str(self.root/'absent')]+extra, capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['status'], expected)
        self.assertFalse(self.home.exists())

    def test_concurrent_approved_creation_dispatches_once(self):
        entered, release = threading.Event(), threading.Event()
        original = self.admin.create
        def blocked(title):
            entered.set()
            if not release.wait(5):
                raise RuntimeError('Synthetic test timeout')
            return original(title)
        self.admin.create = blocked
        results, errors = [], []
        def run():
            try:
                onboarding = Onboarding(self.project, self.home, self.state.path, lambda _: self.admin)
                results.append(onboarding.run(**self.options()))
            except Exception as error:
                errors.append(error)
        first = threading.Thread(target=run)
        first.start()
        self.assertTrue(entered.wait(5))
        second = threading.Thread(target=run)
        second.start()
        release.set()
        first.join(5); second.join(5)
        self.assertFalse(first.is_alive() or second.is_alive())
        self.assertFalse(errors, errors)
        self.assertEqual(len(results), 2)
        self.assertEqual([call for call in self.admin.calls if isinstance(call, tuple)], [('create', 'Owner-approved title')])
        self.assertTrue(all(value['status'] == 'MAPPED' for value in results))

    def test_dispatched_receipt_after_crash_blocks_replay(self):
        # Simulate abrupt termination after the durable DISPATCHED record, before
        # exception handling or a response can update it.
        original = self.admin.create
        def crash(title):
            self.assertEqual(self.onboard.receipt()['state'], 'DISPATCHED')
            return original(title)
        self.admin.create = crash
        self.admin.failure = 'create'
        with patch('agent_librarian.onboarding.persist_receipt', wraps=__import__('agent_librarian.onboarding', fromlist=['persist_receipt']).persist_receipt) as persist:
            count = [0]
            real = persist._mock_wraps
            def save(path, value):
                count[0] += 1
                if count[0] == 2:
                    raise OSError('Synthetic crash before outcome receipt')
                real(path, value)
            persist.side_effect = save
            with self.assertRaises(OSError):
                self.onboard.run(**self.options())
        self.assertEqual(self.onboard.receipt()['state'], 'DISPATCHED')
        self.assertEqual(self.onboard.run(**self.options())['status'], 'CREATION_REQUIRES_REVIEW')
        self.assertEqual(len(self.admin.calls), 1)

    def test_reused_existing_id_in_creation_response_is_uncertain(self):
        self.admin.create = lambda _: 'first-id'
        self.reject('CREATION_OUTCOME_UNKNOWN', **self.options())
        self.assertEqual(self.onboard.receipt()['state'], 'UNKNOWN')
        self.assertFalse(self.maps.path.exists())
