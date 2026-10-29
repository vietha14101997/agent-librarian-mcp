"""Actual journal and planning code against synthetic consumer responses; no Google."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from agent_librarian.gateway.common import Rejected,NAMES,TOOLS
from agent_librarian.personal.ingestion import plan,payload,Importer,validate_plan,plan_hash,MAX_FILE
from agent_librarian.personal.state import PersonalState,write_private
from agent_librarian.projects import ProjectMappings

ROOT=Path(__file__).resolve().parents[1]

class Admin:
    def __init__(self):self.sources=[];self.calls=[];self.fail=None;self.ready=True;self.closed=False
    def inventory(self,nb):return [dict(s) for s in self.sources]
    def register(self,nb,name):
        sid='source-'+str(len(self.sources)+1);self.sources.append({'id':sid,'title':name,'status':1,'source_type':11});self.calls.append('register')
        if self.fail=='register':raise Rejected('IMPORT_OUTCOME_UNKNOWN')
        return sid
    def start_upload(self,nb,name,size,sid):
        self.calls.append('start')
        if self.fail=='start':raise Rejected('IMPORT_OUTCOME_UNKNOWN')
        return 'https://notebook.google.com/upload/_/?upload_id=SYNTHETIC_SESSION'
    def stage(self,raw):
        self.calls.append('stage');self.raw=raw
        if self.fail=='stage':raise Rejected('BROWSER_REQUEST_LOST')
        return 'synthetic-token'
    def finalize(self,url,token,size):
        self.calls.append('finalize')
        if self.fail=='finalize':raise Rejected('IMPORT_OUTCOME_UNKNOWN')
        if self.ready:self.sources[-1]['status']=2
    def close(self):self.closed=True

class IngestionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'state');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.docs=self.root/'docs';self.docs.mkdir();self.project=self.root/'project';self.project.mkdir()
        self.file=self.docs/'notes.md';self.file.write_bytes(b'# Synthetic notes\nKeep exact bytes.\n')
        self.state=PersonalState(self.root/'personal',create=True);c=self.state.load();c['authenticated']=True;self.state.save(c)
        write_private(self.state.path/'notebooks.json',{'account_id':c['account_id'],'notebooks':[{'notebook_id':'notebook-test','title':'Synthetic','sources':[]}]})
        self.home=self.root/'installation';ProjectMappings(self.home).change(self.project,['notebook-test'])
        self.admin=Admin();self.importer=Importer(self.home,self.state,self.project,'notebook-test',lambda:self.admin)
    def plan(self,path=None,**kwargs):return plan(path or self.docs,self.project,'notebook-test',**kwargs)
    def test_preview_never_constructs_browser_or_changes_auth(self):
        before=self.state.config_path.read_bytes();data=self.plan()
        self.importer.admin_factory=lambda:(_ for _ in ()).throw(AssertionError('No browser'))
        self.assertEqual(self.importer.run(data)['status'],'PREVIEW');self.assertFalse(self.importer.path.exists())
        self.assertEqual(before,self.state.config_path.read_bytes())
    def test_exact_bytes_and_hashes(self):
        e=self.plan()['entries'][0];self.assertEqual(payload(e),self.file.read_bytes());self.assertEqual(e['sha256'],hashlib.sha256(self.file.read_bytes()).hexdigest())
    def test_json_adapter_preserves_original(self):
        raw=b'{"exact": 1, "text": "Ti\\u1ebfng"}';f=self.docs/'schema.json';f.write_bytes(raw)
        data=self.plan(json_as_markdown=True);e=next(e for e in data['entries'] if e['json_adapter'])
        self.assertIn(raw,payload(e));self.assertEqual(e['filename'],'schema.json.md');self.assertEqual(f.read_bytes(),raw)
    def test_basename_collisions_reported_and_relative_names_resolve(self):
        sub=self.docs/'nested';sub.mkdir();(sub/'notes.md').write_text('other')
        self.assertEqual(self.plan()['errors'][0]['code'],'IMPORT_FILENAME_COLLISION')
        data=self.plan(relative_names=True);self.assertFalse(data['errors']);self.assertEqual(len({e['filename'] for e in data['entries']}),2)
    def test_unsupported_files_are_accounted_for(self):
        (self.docs/'not-accepted.exe').write_bytes(b'no');self.assertEqual(self.plan()['errors'][0]['code'],'IMPORT_FORMAT_UNSUPPORTED')
        with self.assertRaises(Rejected):validate_plan(self.plan())
    def test_metadata_exclusion_only_and_symlink_rejection(self):
        (self.docs/'.DS_Store').write_bytes(b'ignored');(self.docs/'alias.md').symlink_to(self.file)
        p=self.plan();self.assertEqual(p['excluded'],['.DS_Store']);self.assertEqual(p['errors'][0]['code'],'IMPORT_SYMLINK_REJECTED')
    def test_changed_source_prevents_dispatch(self):
        p=self.plan();self.file.write_text('changed')
        with self.assertRaises(Rejected):self.importer.run(p,True)
        self.assertFalse(self.admin.calls)
    def test_tampered_plan_rejected(self):
        p=self.plan();p['notebook_id']='foreign'
        with self.assertRaises(Rejected):self.importer.run(p,True)
    def test_full_three_stage_success_requires_processing_ready(self):
        p=self.plan();r=self.importer.run(p,True)
        self.assertEqual(r['status'],'COMPLETE');self.assertEqual(self.admin.calls,['register','start','stage','finalize']);self.assertEqual(self.admin.raw,self.file.read_bytes())
        self.assertNotIn('SYNTHETIC_SESSION',json.dumps(r));self.assertEqual(self.state.inventory()['notebooks'][0]['sources'][0]['id'],'source-1')
    def test_http_success_alone_is_not_completion(self):
        self.admin.ready=False;r=self.importer.run(self.plan(),True)
        self.assertEqual(r['status'],'INCOMPLETE');self.assertEqual(r['entries'][0]['state'],'SUBMITTED')
        self.admin.sources[0]['status']=2;self.assertEqual(self.importer.check()['status'],'COMPLETE')
    def test_duplicate_success_is_not_reimported(self):
        p=self.plan();self.importer.run(p,True);calls=self.admin.calls[:]
        self.importer.run(p,True);self.assertEqual(self.admin.calls,calls);self.assertEqual(len(self.admin.sources),1)
    def test_existing_remote_title_without_hash_is_blocked(self):
        self.admin.sources=[{'id':'existing','title':'notes.md','status':2}]
        r=self.importer.run(self.plan(),True);self.assertEqual(r['entries'][0]['failure'],'IMPORT_EXISTING_TITLE_UNKNOWN_HASH');self.assertFalse(self.admin.calls)
    def test_unknown_registration_blocks_new_plan_and_fresh_importer(self):
        self.admin.fail='register';p=self.plan();r=self.importer.run(p,True)
        self.assertEqual(r['entries'][0]['state'],'REGISTERING');self.assertTrue(self.admin.closed)
        fresh=Importer(self.home,self.state,self.project,'notebook-test',lambda:self.admin)
        self.admin.fail=None;fresh.run(self.plan(),True);self.assertEqual(self.admin.calls,['register'])
        self.assertEqual(fresh.check()['entries'][0]['candidate_source_ids'],['source-1'])
    def test_unknown_session_start_preserves_source_and_never_registers_again(self):
        self.admin.fail='start';p=self.plan();r=self.importer.run(p,True)
        self.assertEqual(r['entries'][0]['source_id'],'source-1');self.assertEqual(r['entries'][0]['state'],'STARTING')
        self.admin.fail=None;self.importer.run(p,True);self.assertEqual(self.admin.calls,['register','start'])
    def test_uncertain_finalize_is_reconciled_without_reupload(self):
        self.admin.fail='finalize';p=self.plan();self.importer.run(p,True);calls=self.admin.calls[:]
        self.admin.fail=None;self.importer.run(p,True);self.assertEqual(calls,self.admin.calls)
        self.admin.sources[0]['status']=2;self.assertEqual(self.importer.check()['status'],'COMPLETE');self.assertEqual(calls,self.admin.calls)
    def test_interrupted_local_staging_resumes_same_source_session(self):
        self.admin.fail='stage';p=self.plan();self.importer.run(p,True);self.admin.fail=None
        self.assertEqual(self.importer.run(p,True)['status'],'COMPLETE');self.assertEqual(self.admin.calls.count('register'),1);self.assertEqual(self.admin.calls.count('start'),1)
    def test_register_placeholder_ready_does_not_skip_finalization(self):
        self.admin.fail='stage';p=self.plan();self.importer.run(p,True);self.admin.sources[0]['status']=2;self.admin.fail=None
        self.assertEqual(self.importer.run(p,True)['status'],'COMPLETE');self.assertIn('finalize',self.admin.calls)
    def test_hash_conflict_stops_and_journal_is_private(self):
        self.importer.run(self.plan(),True);self.assertEqual(self.importer.path.stat().st_mode&0o777,0o600)
        self.file.write_text('different');r=self.importer.run(self.plan(),True);self.assertEqual(r['code'],'IMPORT_FILENAME_HASH_CONFLICT');self.assertEqual(self.admin.calls.count('register'),1)
    def test_readonly_check_never_mutates_sources(self):
        self.importer.run(self.plan(),True);calls=self.admin.calls[:];self.importer.check();self.assertEqual(calls,self.admin.calls)
    def test_wrong_mapping_rejected_before_authentication(self):
        with self.assertRaises(Rejected):Importer(self.home,self.state,self.project,'foreign',lambda:self.admin)
    def test_four_research_tools_only(self):
        self.assertEqual(len(TOOLS),4);self.assertEqual(tuple(t['name'] for t in TOOLS),NAMES)
        self.assertFalse(any('upload' in t['name'] for t in TOOLS))

    def test_abrupt_interrupt_is_durable_and_does_not_replay(self):
        def interrupted(nb,name):
            self.admin.calls.append('register');raise KeyboardInterrupt()
        self.admin.register=interrupted;p=self.plan()
        with self.assertRaises(KeyboardInterrupt):self.importer.run(p,True)
        self.assertEqual(self.importer.status()['entries'][0]['state'],'REGISTERING')
        fresh=Importer(self.home,self.state,self.project,'notebook-test',lambda:self.admin)
        fresh.run(p,True);self.assertEqual(self.admin.calls,['register'])
    def test_source_capacity_is_checked_before_registration(self):
        self.admin.sources=[{'id':f'existing-{i}','title':f'existing-{i}.md','status':2} for i in range(100)]
        r=self.importer.run(self.plan(),True);self.assertEqual(r['code'],'IMPORT_NOTEBOOK_SOURCE_LIMIT');self.assertFalse(self.admin.calls)

    def test_unknown_upload_cannot_be_bypassed_by_renaming_same_bytes(self):
        self.admin.fail='register';self.importer.run(self.plan(),True)
        self.file.rename(self.docs/'renamed.md');self.admin.fail=None
        r=self.importer.run(self.plan(),True)
        self.assertEqual(r['code'],'IMPORT_UNCERTAIN_MATCHING_HASH');self.assertEqual(self.admin.calls,['register'])
