"""Selected-profile reader and native crypto vectors. Never uses a real browser/key."""
import base64
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from agent_librarian.gateway.common import Rejected
from agent_librarian.personal.state import PersonalState
from agent_librarian.personal.existing_brave import selected_records,AUTH_NAMES,COOKIE_HOSTS,connect,decrypt_records,account_probe
from agent_librarian.personal.storage import KeychainFailure
from tests.http_fakes import MemoryStore,ReplayHTTP,session
ROOT=Path(__file__).resolve().parents[1]

class ExistingBraveTests(unittest.TestCase):
    def setUp(self):
        p=ROOT/'state';p.mkdir(exist_ok=True);self.temp=tempfile.TemporaryDirectory(prefix='b',dir=p);self.root=Path(self.temp.name).resolve()
        self.state=PersonalState(self.root/'personal',create=True)
        self.browser=self.root/'browser';(self.browser/'Default').mkdir(parents=True)
        self.db=self.browser/'Default/Cookies'
        with sqlite3.connect(self.db) as c:
            c.execute('CREATE TABLE meta(key TEXT,value TEXT)');c.execute("INSERT INTO meta VALUES('version','24')")
            c.execute('CREATE TABLE cookies(name TEXT,host_key TEXT,path TEXT,is_secure INTEGER,expires_utc INTEGER,encrypted_value BLOB)')
            for name in ('SID','HSID','SSID','APISID','SAPISID'):c.execute('INSERT INTO cookies VALUES(?,?,?,?,?,?)',(name,'.google.com','/',1,0,b'v10'+b'x'*16))
            c.execute('INSERT INTO cookies VALUES(?,?,?,?,?,?)',('UNRELATED','.example.invalid','/',1,0,b'v10'+b'z'*16))
    def tearDown(self):self.temp.cleanup()
    def error(self,code,fn):
        with self.assertRaises(Rejected) as e:fn()
        self.assertEqual(e.exception.code,code);return e.exception
    def test_01_only_selected_google_auth_rows_no_writes_or_copy(self):
        before=(self.db.stat().st_mtime_ns,hashlib.sha256(self.db.read_bytes()).hexdigest());files=set(self.root.rglob('*'))
        payload=selected_records('Default',self.browser)
        self.assertEqual(len(payload['records']),5);self.assertNotIn('UNRELATED',json.dumps(payload))
        self.assertEqual(before,(self.db.stat().st_mtime_ns,hashlib.sha256(self.db.read_bytes()).hexdigest()))
        self.assertEqual(files,set(self.root.rglob('*')))
    def test_02_profile_traversal_rejected(self):self.error('BRAVE_PROFILE_SELECTION_REQUIRED',lambda:selected_records('../Default',self.browser))
    def test_03_unsupported_schema_stops(self):
        with sqlite3.connect(self.db) as c:c.execute("UPDATE meta SET value='25'")
        self.error('BRAVE_COOKIE_SCHEMA_UNSUPPORTED',lambda:selected_records('Default',self.browser))
    def test_04_unsupported_cipher_no_fallback(self):
        with sqlite3.connect(self.db) as c:c.execute("UPDATE cookies SET encrypted_value=? WHERE name='SID'",(b'v20'+b'x'*32,))
        self.error('BRAVE_COOKIE_ENCRYPTION_UNSUPPORTED',lambda:selected_records('Default',self.browser))
    def test_05_cookie_store_symlink_rejected(self):
        old=self.browser/'Default/old';self.db.rename(old);self.db.symlink_to(old)
        self.error('BRAVE_COOKIE_PATH_UNSAFE',lambda:selected_records('Default',self.browser))
    def test_06_expired_required_cookie_not_used(self):
        with sqlite3.connect(self.db) as c:c.execute("UPDATE cookies SET expires_utc=1 WHERE name='SID'")
        self.error('BRAVE_REQUIRED_AUTH_COOKIES_MISSING',lambda:selected_records('Default',self.browser))
    def test_07_plaintext_record_not_accepted(self):
        with sqlite3.connect(self.db) as c:c.execute("UPDATE cookies SET encrypted_value=? WHERE name='SID'",(b'',))
        self.error('BRAVE_COOKIE_ENCRYPTION_UNSUPPORTED',lambda:selected_records('Default',self.browser))
    def test_08_consent_checked_before_reading(self):
        with patch('agent_librarian.personal.existing_brave.selected_records',side_effect=AssertionError('No access')):
            self.error('EXISTING_BRAVE_ACCESS_APPROVAL_REQUIRED',lambda:connect(self.state,None,'Default',False))
    def test_09_keychain_denial_safe(self):
        result=subprocess.CompletedProcess([],42,b'',b'{"code":"BRAVE_SAFE_STORAGE_UNAVAILABLE","os_status":-128}')
        with patch('subprocess.run',return_value=result):
            e=self.error('BRAVE_SAFE_STORAGE_UNAVAILABLE',lambda:decrypt_records(self.state,{'records':[]},helper='/SYNTHETIC/helper'))
        self.assertEqual(e.os_status,-128)
    def test_10_bridge_response_scope_checked(self):
        result=subprocess.CompletedProcess([],0,b'{"cookies":[{"name":"OTHER","domain":".example.invalid","path":"/","secure":true}]}',b'')
        with patch('subprocess.run',return_value=result):self.error('BRAVE_COOKIE_BRIDGE_RESPONSE_INVALID',lambda:decrypt_records(self.state,{},helper='/SYNTHETIC/helper'))
    def test_11_approved_capture_one_discovery_then_keychain(self):
        s=replace(session(),account_id=self.state.load()['account_id'],expires_at=time.time()+300)
        store=MemoryStore(s);store.probe=lambda:None
        fixture=json.loads((ROOT/'tests/fixtures/research.json').read_text());http=ReplayHTTP(fixture)
        result=connect(self.state,store,'Default',True,sender=http,reader=lambda _: {'records':[]},decryptor=lambda *_:[],probe=lambda *_:s)
        self.assertEqual(result['status'],'AUTHENTICATED');self.assertEqual(len(http.calls),1);self.assertEqual(store.saved,1)
        self.assertNotIn('cookies',(self.state.path/'personal.json').read_text())
    def test_12_no_broader_retry_after_auth_failure(self):
        store=MemoryStore();store.probe=lambda:None
        calls=[]
        def denied(*a):calls.append(1);raise Rejected('AUTHENTICATION_EXPIRED')
        self.error('AUTHENTICATION_EXPIRED',lambda:connect(self.state,store,'Default',True,reader=lambda _: {},decryptor=lambda *_:[],probe=denied))
        self.assertEqual(calls,[1]);self.assertEqual(store.saved,0)

    def test_14_nonsecure_legacy_cookie_is_applicable_to_fixed_https(self):
        with sqlite3.connect(self.db) as c:c.execute("UPDATE cookies SET is_secure=0 WHERE name='SID'")
        payload=selected_records('Default',self.browser)
        row=next(r for r in payload['records'] if r['name']=='SID');self.assertEqual(row['secure'],'false')

@unittest.skipUnless(sys.platform=='darwin','Native CommonCrypto test requires macOS SDK; no real Keychain is accessed.')
class NativeBraveCryptoTests(unittest.TestCase):
    def test_13_independent_v10_schema24_vector_without_keychain(self):
        from cryptography.hazmat.primitives.ciphers import Cipher,algorithms,modes
        from cryptography.hazmat.primitives import padding
        root=ROOT/'state';root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='native',dir=root) as t:
            work=Path(t).resolve();source=(ROOT/'src/agent_librarian/personal/brave_cookie_bridge.swift').read_text()
            start=source.index('// Exact item only;');end=source.index('let derived = password.withUnsafeBytes',start)
            source=source[:start]+'var password=Data("SYNTHETIC_BRAVE_PASSWORD".utf8)\nvar key=Data(count:16)\nlet salt=Array("saltysalt".utf8)\n'+source[end:]
            path=work/'synthetic.swift';path.write_text(source);binary=work/'synthetic'
            sdk=subprocess.check_output(['/usr/bin/xcrun','--sdk','macosx','--show-sdk-path'],text=True).strip()
            compiler=subprocess.check_output(['/usr/bin/xcrun','--find','swiftc'],text=True).strip()
            env=dict(os.environ,TMPDIR=str(work),CLANG_MODULE_CACHE_PATH=str(work/'cache'))
            built=subprocess.run([compiler,'-sdk',sdk,'-target','arm64-apple-macosx14.0' if os.uname().machine=='arm64' else 'x86_64-apple-macosx14.0','-module-cache-path',str(work/'cache'),str(path),'-o',str(binary)],capture_output=True,timeout=60,env=env)
            self.assertEqual(built.returncode,0,built.stderr.decode())
            key=hashlib.pbkdf2_hmac('sha1',b'SYNTHETIC_BRAVE_PASSWORD',b'saltysalt',1003,16)
            host='.google.com';value='SYNTHETIC_AUTH_ONLY'
            raw=hashlib.sha256(host.encode()).digest()+value.encode();pad=padding.PKCS7(128).padder();plain=pad.update(raw)+pad.finalize()
            enc=Cipher(algorithms.AES(key),modes.CBC(b' '*16)).encryptor();encrypted=b'v10'+enc.update(plain)+enc.finalize()
            payload={'schema_version':24,'records':[{'name':'SID','domain':host,'path':'/','secure':'true','encrypted_value':base64.b64encode(encrypted).decode()}]}
            result=subprocess.run([str(binary)],input=json.dumps(payload).encode(),capture_output=True,timeout=5)
            self.assertEqual(result.returncode,0,result.stderr.decode());self.assertEqual(json.loads(result.stdout)['cookies'][0]['value'],value)
            payload['records'][0]['domain']='google.com'
            result=subprocess.run([str(binary)],input=json.dumps(payload).encode(),capture_output=True,timeout=5)
            self.assertNotEqual(result.returncode,0);self.assertIn(b'BRAVE_COOKIE_HOST_BINDING_INVALID',result.stderr)
