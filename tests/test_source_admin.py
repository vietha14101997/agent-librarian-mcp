"""Real Python upload adapter with fake native bridge; no browser or credentials."""
import base64
import json
import unittest
from types import SimpleNamespace
from agent_librarian.personal.source_admin import SourceAdmin,REGISTER_RPC,registration_params
from agent_librarian.gateway.common import Rejected

class SourceAdminTests(unittest.TestCase):
    def setUp(self):
        self.reader=SimpleNamespace(connection={'window_id':'1','tab_id':'2','origin':'https://notebook.google.com'},account_id='synthetic',expected_email='owner@example.invalid',notebooks={},runner=lambda _:None,disabled=lambda:False,close=lambda:None)
        self.admin=SourceAdmin(self.reader,'notebook-test')
    def test_registration_exact_params_and_returned_id(self):
        calls=[]
        def execute(operation,**values):
            calls.append((operation,values));return {'text':")]}'\n"+json.dumps([['wrb.fr',REGISTER_RPC,json.dumps([[[['source-test']]]])]])+'\n'}
        self.admin.execute=execute
        self.assertEqual(self.admin.register('notebook-test','notes.md'),'source-test')
        self.assertEqual(calls,[('register',{'params':registration_params('notebook-test','notes.md')})])
    def test_ambiguous_id_and_wrong_notebook_fail(self):
        self.admin.execute=lambda *a,**kw:{'text':")]}'\n"+json.dumps([['wrb.fr',REGISTER_RPC,json.dumps([None,['unrelated-id']])]])+'\n'}
        with self.assertRaises(Rejected):self.admin.register('notebook-test','notes.md')
        with self.assertRaises(Rejected):self.admin.register('foreign','notes.md')
    def test_chunked_browser_local_staging_keeps_exact_bytes(self):
        raw=bytes(range(256))*500;parts=[]
        def execute(p):
            self.assertEqual(p['offset'],sum(map(len,parts)));parts.append(base64.b64decode(p['data']));return {'status':'STAGED','bytes':sum(map(len,parts))}
        self.admin.bridge._execute=execute
        self.admin.stage(raw);self.assertEqual(b''.join(parts),raw);self.assertTrue(all(len(p)<=49152 for p in parts))
    def test_processing_status_absence_is_not_ready_and_titles_preserved(self):
        title='This_is_a_long_source_filename_preserved_verbatim.md'
        self.reader.request=lambda _:[['Synthetic',[[['source-test'],title,[]]],'notebook-test']]
        source=self.admin.inventory('notebook-test')[0]
        self.assertEqual(source['title'],title);self.assertIsNone(source['status'])
    def test_single_dispatch_poll_and_close(self):
        actions=[]
        def execute(p):actions.append(p['action']);return {'status':'DISPATCHED'} if p['action']=='start' else {'status':'DONE','text':'synthetic'}
        self.admin.bridge._execute=execute
        self.assertEqual(self.admin.execute('register',params=registration_params('notebook-test','notes.md'))['text'],'synthetic')
        self.assertEqual(actions,['start','poll']);self.admin.close()
