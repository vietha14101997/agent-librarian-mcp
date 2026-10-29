"""Three dimensions, safe v1 migration and declaration-integrity regression tests."""
from pathlib import Path
import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from agent_librarian.catalog.model import CatalogError,load_catalog,migrate_catalog
from agent_librarian.policy.planner import sync_plan,policy_fingerprint

ROOT=Path(__file__).resolve().parents[1]
TEMP=Path(os.environ.get('AGENT_LIBRARIAN_TEST_DIR',ROOT/'state/test-runs'));TEMP.mkdir(parents=True,exist_ok=True)

def approved():
    catalog=migrate_catalog(json.loads((ROOT/'examples/catalog.approved.json').read_text()))
    d=catalog['documents'][0]
    d.update(curation_status='ACCEPTED_FOR_RESEARCH',curation_evidence={'decision_id':'synthetic-curation-02',
        'reviewer':'synthetic-owner','content_sha256':d['content_sha256'],'provenance':'Synthetic explicit research curation review',
        'status':'ACCEPTED_FOR_RESEARCH'})
    return catalog,json.loads((ROOT/'examples/sync-policy.json').read_text())

class PolicyV2Tests(unittest.TestCase):
    def setUp(self):self.catalog,self.policy=approved();self.doc=self.catalog['documents'][0]
    def action(self):return sync_plan(self.catalog,self.policy)['plan'][0]['action']
    def authority(self,status):
        self.doc['authority_status']=status;self.doc['authority_evidence']='Synthetic explicit '+status+' classification'
        before=copy.deepcopy(self.doc)
        self.assertEqual(self.action(),'ADD_CANDIDATE');self.assertEqual(self.doc,before)
    def test_01_historical_eligible(self):self.authority('HISTORICAL')
    def test_02_proposal_eligible(self):self.authority('DESIGN_PROPOSED')
    def test_03_dev_selected_eligible_without_promotion(self):self.authority('DEV_SELECTED')
    def test_04_production_local_only_blocked(self):
        self.doc.update(authority_status='PRODUCTION_INTEGRATED',disclosure_status='LOCAL_ONLY')
        self.assertEqual(self.action(),'BLOCKED_APPROVAL')
    def test_05_missing_curation_blocked(self):
        self.doc.update(curation_status='UNKNOWN',curation_evidence=None);self.assertEqual(self.action(),'BLOCKED_APPROVAL')
    def test_06_revoked_disclosure_blocked(self):
        self.policy['approvals'][0]['revoked']=True;self.assertEqual(self.action(),'BLOCKED_APPROVAL')
    def test_07_approved_revision_mismatch(self):
        self.policy['approvals'][0]['content_sha256']='a'*64;self.assertEqual(self.action(),'BLOCKED_REVISION')
    def test_08_wrong_notebook_and_account(self):
        for field in ['notebook_id','account_id']:
            c,p=approved();p['approvals'][0][field]='wrong'
            self.assertEqual(sync_plan(c,p)['plan'][0]['action'],'BLOCKED_APPROVAL')
    def test_09_unknown_remote_state(self):
        d=self.doc;mapping=self.policy['mappings'][0]
        self.policy['remote_sources']=[{**mapping,'account_id':self.policy['account_id'],'source_id':'synthetic-source','revision':d['content_sha256'],'status':'UNKNOWN'}]
        self.assertEqual(self.action(),'REVIEW_REQUIRED')
    def test_10_v1_preserves_uncertainty_and_provenance(self):
        raw=copy.deepcopy(self.catalog);raw['schema_version']=1
        for d in raw['documents']:d.pop('curation_status');d.pop('curation_evidence')
        before=copy.deepcopy(raw);new=migrate_catalog(raw)
        self.assertEqual(raw,before);self.assertEqual(new['schema_version'],2)
        d=new['documents'][0]
        for key,value in before['documents'][0].items():self.assertEqual(d[key],value)
        self.assertEqual(d['curation_status'],'UNKNOWN');self.assertIsNone(d['curation_evidence'])
        self.assertEqual(sync_plan(raw,self.policy)['plan'][0]['action'],'BLOCKED_APPROVAL')
    def test_11_v2_validates(self):self.assertEqual(load_catalog(self.catalog)[0].curation_status,'ACCEPTED_FOR_RESEARCH')
    def test_12_conflicting_evidence_rejected(self):
        self.doc['curation_evidence']['status']='REJECTED'
        with self.assertRaisesRegex(CatalogError,'CONFLICTING_CURATION_EVIDENCE'):load_catalog(self.catalog)
    def test_13_tampering_fingerprint_detects_change(self):
        fingerprint=policy_fingerprint(self.policy);self.policy['approvals'][0]['approval_id']='tampered-decision'
        with self.assertRaisesRegex(CatalogError,'POLICY_CHANGED_SINCE_REVIEW'):sync_plan(self.catalog,self.policy,fingerprint)
    def test_14_local_declaration_is_not_trusted_authorization(self):
        self.policy['approvals'][0]['approval_id']='agent-editable-self-declaration'
        result=sync_plan(self.catalog,self.policy)
        self.assertEqual(result['plan'][0]['action'],'ADD_CANDIDATE')
        self.assertFalse(result['trusted_authorization']);self.assertFalse(result['execution_enabled'])
        self.assertEqual(result['authorization_basis'],'UNTRUSTED_PLANNING_DECLARATION')
    def test_15_stale_curation_revision(self):
        self.doc['curation_evidence']['content_sha256']='f'*64;self.assertEqual(self.action(),'BLOCKED_REVISION')
    def test_16_accepted_curation_needs_evidence(self):
        self.doc['curation_evidence']=None
        with self.assertRaisesRegex(CatalogError,'CURATION_EVIDENCE_REQUIRED'):load_catalog(self.catalog)
    def test_17_v1_cannot_smuggle_curation(self):
        self.catalog['schema_version']=1
        with self.assertRaisesRegex(CatalogError,'AMBIGUOUS_V1_CURATION'):migrate_catalog(self.catalog)
    def test_18_v2_missing_fields_rejected(self):
        del self.doc['curation_status']
        with self.assertRaisesRegex(CatalogError,'V2_CURATION_FIELDS_REQUIRED'):load_catalog(self.catalog)
    def test_19_cli_migration_preserves_input(self):
        with tempfile.TemporaryDirectory(dir=TEMP) as t:
            source=Path(t)/'v1.json';target=Path(t)/'v2.json'
            raw=json.loads((ROOT/'examples/catalog.json').read_text());source.write_text(json.dumps(raw));original=source.read_bytes()
            r=subprocess.run([sys.executable,'-I','-B','-m','agent_librarian','migrate','--input',str(source),'--output',str(target)],capture_output=True,text=True,timeout=5)
            self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(source.read_bytes(),original)
            self.assertEqual(json.loads(target.read_text())['documents'][0]['curation_status'],'UNKNOWN')
            r=subprocess.run([sys.executable,'-I','-B','-m','agent_librarian','migrate','--input',str(source),'--output',str(source)],capture_output=True,text=True)
            self.assertEqual(r.returncode,2);self.assertEqual(source.read_bytes(),original)
    def test_20_unknown_disclosure_never_promoted(self):
        self.doc['disclosure_status']='UNKNOWN'
        migrated=migrate_catalog(self.catalog)
        self.assertEqual(migrated['documents'][0]['disclosure_status'],'UNKNOWN');self.assertEqual(self.action(),'BLOCKED_APPROVAL')
