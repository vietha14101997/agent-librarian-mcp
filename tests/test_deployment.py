"""Deployment validation and rollback in disposable local fixtures, never privileged."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from agent_librarian.gateway.common import Rejected
from agent_librarian.providers import runtime
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('macos_manage',ROOT/'deploy/macos/scripts/manage.py');manage=importlib.util.module_from_spec(spec);spec.loader.exec_module(manage)

class DeploymentTests(unittest.TestCase):
    def setUp(self):
        state=ROOT/'state';state.mkdir(exist_ok=True);self.temp=tempfile.TemporaryDirectory(prefix='d',dir=state);self.dir=Path(self.temp.name).resolve()
    def tearDown(self):self.temp.cleanup()
    def code(self,expected,fn):
        with self.assertRaises(Rejected) as error:fn()
        self.assertEqual(error.exception.code,expected)
    def test_01_root_owned_configuration_rejects_agent_file(self):
        p=self.dir/'config.json';p.write_text('{}')
        self.code('DEPLOYMENT_PATH_UNTRUSTED',lambda:runtime.protected_path(p))
    def test_02_unsafe_symlink_rejected(self):
        p=self.dir/'config.json';p.write_text('{}');link=self.dir/'link';link.symlink_to(p)
        self.code('DEPLOYMENT_PATH_UNTRUSTED',lambda:runtime.protected_path(link,owners=(0,os.geteuid())))
    def test_03_traversal_deployment_path_rejected(self):
        self.code('DEPLOYMENT_PATH_INVALID',lambda:runtime.protected_path(self.dir/'..'/'file'))
    def test_04_writable_parent_rejected(self):
        child=self.dir/'parent';child.mkdir();child.chmod(0o777);p=child/'file';p.write_text('synthetic')
        try:self.code('DEPLOYMENT_PATH_UNTRUSTED',lambda:runtime.protected_path(p,owners=(0,os.geteuid())))
        finally:child.chmod(0o700)
    def test_05_executable_manifest_detects_tampering(self):
        root=self.dir/'release';root.mkdir();p=root/'python3';p.write_text('Synthetic executable')
        manifest=self.dir/'integrity.json';manifest.write_text(json.dumps({'python3':hashlib.sha256(p.read_bytes()).hexdigest()}))
        real=runtime.protected_path
        def local(path,**kw):return real(path,**(kw|{'owners':(0,os.geteuid())}))
        with patch.object(runtime,'protected_path',side_effect=local):
            runtime.verify_integrity(root,manifest)
            p.write_text('Tampered synthetic executable')
            self.code('EXECUTABLE_INTEGRITY_MISMATCH',lambda:runtime.verify_integrity(root,manifest))
    def test_06_unlisted_import_file_rejected(self):
        root=self.dir/'release';root.mkdir();p=root/'python3';p.write_text('Synthetic executable')
        manifest=self.dir/'integrity.json';manifest.write_text(json.dumps({'python3':hashlib.sha256(p.read_bytes()).hexdigest()}));(root/'injected.pth').write_text('import synthetic')
        real=runtime.protected_path
        with patch.object(runtime,'protected_path',side_effect=lambda path,**kw:real(path,**(kw|{'owners':(0,os.geteuid())}))):
            self.code('EXECUTABLE_MANIFEST_INCOMPLETE',lambda:runtime.verify_integrity(root,manifest))
    def config(self):
        s=SimpleNamespace(pw_uid=1001);a=SimpleNamespace(pw_uid=1002);g=SimpleNamespace(gr_gid=1003)
        return manage.payload_plan(s,a,g,'a'*64)
    def test_07_wrong_process_identity_rejected(self):
        with patch.object(runtime,'protected_json',return_value=(self.config(),'b'*64)):
            self.code('SERVICE_PRINCIPAL_MISMATCH',lambda:runtime.load_runtime(self.dir/'unused'))
    def test_08_same_uid_configuration_rejected(self):
        c=self.config();c['agent_uid']=c['service_uid']
        with patch.object(runtime,'protected_json',return_value=(c,'b'*64)):
            self.code('SERVICE_PRINCIPAL_MISMATCH',lambda:runtime.load_runtime(self.dir/'unused',False))
    def test_09_root_service_rejected(self):
        c=self.config();c['service_uid']=0
        with patch.object(runtime,'protected_json',return_value=(c,'b'*64)):
            self.code('DEPLOYMENT_PRINCIPAL_INVALID',lambda:runtime.load_runtime(self.dir/'unused',False))
    def test_10_policy_digest_tampering(self):
        c=self.config();c['executable']=str(self.dir/'python3');c['keychain_helper']=str(self.dir/'helper');c['release_root']=str(self.dir)
        for name in ('python3','helper'):(self.dir/name).write_text('synthetic');(self.dir/name).chmod(0o700)
        def data(path):return (c,'b'*64) if str(path).endswith('config') else ({},'c'*64)
        with patch.object(runtime,'protected_json',side_effect=data),patch.object(runtime,'verify_integrity',return_value={'python3':'x','helper':'y'}),patch.object(runtime,'protected_path',side_effect=lambda p,**kw:Path(p)):
            self.code('SERVICE_POLICY_CHANGED',lambda:runtime.load_runtime(self.dir/'config',False))
    def test_11_live_gate_config_defaults_false(self):
        c=self.config();self.assertFalse(c['live_enabled']);self.assertFalse(any(c['gates'].values()));self.assertEqual(c['owner_approval_id'],'')
    def test_12_no_credentials_in_launchd_arguments(self):
        p=manage.launch_plist('synthetic-service','synthetic-client')
        self.assertNotEqual(p['UserName'],'root');self.assertFalse(p['KeepAlive']);self.assertFalse(p['RunAtLoad'])
        self.assertEqual(p['ProgramArguments'][-1],'/Library/AgentLibrarian/releases/0.3.0/libexec/launcher.py')
        self.assertFalse(any('cookie' in v.lower() or 'token' in v.lower() for v in p['ProgramArguments']))
    def test_13_default_operations_do_not_execute(self):
        with patch('subprocess.run',side_effect=AssertionError('No privileged command')):
            for action in ('start','stop','restart','disable','enable','rollback'):
                self.assertFalse(manage.operate(action,False)['apply'])
    def test_14_rollback_rejects_changed_plist(self):
        base=self.dir/'install';base.mkdir();plist=self.dir/'service.plist';plist.write_text('changed')
        (base/'installation.json').write_text(json.dumps({'plist_sha256':'a'*64}))
        with patch.object(manage,'BASE',base),patch.object(manage,'PLIST',plist),patch.object(manage,'safe_path',side_effect=lambda p,**kw:Path(p)),patch.object(manage.os,'geteuid',return_value=0),patch.object(manage.sys,'platform','darwin'),patch('subprocess.run',side_effect=AssertionError('No launchctl after tampering')):
            with self.assertRaisesRegex(ValueError,'ROLLBACK_INTEGRITY_MISMATCH'):manage.operate('rollback',True)
        self.assertTrue(plist.exists())
    def test_15_rollback_preserves_private_state_and_exact_plist(self):
        base=self.dir/'install';base.mkdir();state=base/'state';state.mkdir();(state/'canary.json').write_text('SYNTHETIC_ONLY')
        plist=self.dir/'service.plist';body=b'Synthetic plist';plist.write_bytes(body)
        (base/'installation.json').write_text(json.dumps({'plist_sha256':hashlib.sha256(body).hexdigest()}))
        with patch.object(manage,'BASE',base),patch.object(manage,'PLIST',plist),patch.object(manage,'safe_path',side_effect=lambda p,**kw:Path(p)),patch.object(manage.os,'geteuid',return_value=0),patch.object(manage.sys,'platform','darwin'),patch('subprocess.run',return_value=subprocess.CompletedProcess([],0)) as calls:
            result=manage.operate('rollback',True);self.assertTrue(result['code_and_private_state_preserved']);self.assertEqual(calls.call_count,2)
        self.assertFalse(plist.exists());self.assertEqual((base/'rollback'/plist.name).read_bytes(),body)
        self.assertEqual((state/'canary.json').read_text(),'SYNTHETIC_ONLY')
    def test_16_bundle_symlink_not_accepted(self):
        bundle=self.dir/'bundle';bundle.mkdir();(bundle/'manifest.json').symlink_to(self.dir/'outside')
        with self.assertRaises(ValueError):manage.read_bundle(bundle,'a'*64,owners=(0,os.geteuid()))
    def test_17_installer_refuses_execution_without_root(self):
        with patch.object(manage.os,'geteuid',return_value=1002):
            with self.assertRaisesRegex(ValueError,'OWNER_ROOT_EXECUTION_REQUIRED'):manage.operate('stop',True)
    def test_19_bundle_hash_and_copied_executable_bytes(self):
        bundle=self.dir/'bundle';bundle.mkdir();entries={}
        for name in ('runtime/bin/python3','libexec/keychain-helper','libexec/launcher.py','policy.json','fixture.json'):
            p=bundle/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('SYNTHETIC_'+name);p.chmod(0o700)
            entries[name]=hashlib.sha256(p.read_bytes()).hexdigest()
        manifest=bundle/'manifest.json';manifest.write_text(json.dumps(entries));digest=hashlib.sha256(manifest.read_bytes()).hexdigest()
        self.assertEqual(manage.read_bundle(bundle,digest,owners=(0,os.geteuid())),entries)
        (bundle/'runtime/bin/python3').write_text('Tampered synthetic interpreter')
        with self.assertRaisesRegex(ValueError,'BUNDLE_FILE_MISMATCH'):manage.read_bundle(bundle,digest,owners=(0,os.geteuid()))
    def test_20_socket_path_substitution_rejected(self):
        from agent_librarian.providers.ipc import socket_path
        target=self.dir/'target';target.mkdir();link=self.dir/'socket-parent';link.symlink_to(target)
        self.code('IPC_PATH_UNSAFE_OR_TOO_LONG',lambda:socket_path(link/'s'))
    @unittest.skip('Owner has not authorized account creation/privileged deployment; no permitted separate-identity environment exists.')
    def test_18_actual_separate_uid_positive_canary(self):pass
