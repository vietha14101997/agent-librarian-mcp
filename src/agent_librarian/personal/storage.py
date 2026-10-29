"""macOS Keychain-only persistence. Operates only the dedicated Personal Local item."""
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from ..gateway.common import Rejected,strict_json
from ..providers.session import Session
from .state import private_dir,read_private,write_private

class KeychainFailure(Rejected):
    def __init__(self,code,status=None):super().__init__(code);self.os_status=status

def prepare_helper(state):
    if sys.platform!='darwin':raise Rejected('PERSONAL_KEYCHAIN_MACOS_REQUIRED')
    directory=private_dir(state.path/'libexec',create=True)
    source=Path(__file__).with_name('keychain.swift');digest=hashlib.sha256(source.read_bytes()).hexdigest()
    target=directory/'keychain-helper';receipt=directory/'build.json'
    if target.is_symlink() or receipt.is_symlink():raise Rejected('PERSONAL_PATH_UNSAFE')
    if target.exists() and receipt.exists():
        old=read_private(receipt)
        if old.get('source_sha256')==digest and old.get('binary_sha256')==hashlib.sha256(target.read_bytes()).hexdigest() and not target.is_symlink():return target
    cache=private_dir(state.path/'compiler-cache',create=True)
    try:
        sdk=subprocess.run(['/usr/bin/xcrun','--sdk','macosx','--show-sdk-path'],capture_output=True,text=True,timeout=10,check=True).stdout.strip()
        compiler=subprocess.run(['/usr/bin/xcrun','--find','swiftc'],capture_output=True,text=True,timeout=10,check=True).stdout.strip()
        args=[compiler,'-O','-sdk',sdk,'-target','arm64-apple-macosx14.0' if os.uname().machine=='arm64' else 'x86_64-apple-macosx14.0',
            '-module-cache-path',str(cache),str(source),'-o',str(target)]
        env={k:v for k,v in os.environ.items() if k in ('PATH','HOME','LANG','USER','LOGNAME')}
        env.update(TMPDIR=str(cache),CLANG_MODULE_CACHE_PATH=str(cache))
        result=subprocess.run(args,capture_output=True,timeout=60,env=env)
        if result.returncode!=0:raise Rejected('PERSONAL_KEYCHAIN_HELPER_BUILD_FAILED')
    except Rejected:raise
    except Exception:raise Rejected('PERSONAL_KEYCHAIN_HELPER_BUILD_FAILED') from None
    target.chmod(0o700);write_private(receipt,{'source_sha256':digest,'binary_sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
    return target

class PersonalKeychainStore:
    def __init__(self,state,helper=None):
        self.state=state;self.selector=state.load()['runtime_id'];self.helper=Path(helper) if helper else prepare_helper(state)
    def _call(self,operation,payload=None):
        try:r=subprocess.run([str(self.helper),operation,self.selector],input=payload,capture_output=True,timeout=15,
            env={k:v for k,v in os.environ.items() if k in ('PATH','HOME','LANG','USER','LOGNAME')})
        except Exception:raise KeychainFailure('PERSONAL_KEYCHAIN_UNAVAILABLE') from None
        if r.returncode!=0:
            status=None
            try:status=strict_json(r.stderr).get('os_status')
            except Exception:pass
            if type(status) is not int:status=None
            raise KeychainFailure('AUTHENTICATION_REQUIRED' if status==-25300 else 'PERSONAL_KEYCHAIN_UNAVAILABLE',status)
        if r.stderr or len(r.stdout)>65536:raise KeychainFailure('PERSONAL_KEYCHAIN_RESPONSE_INVALID')
        return r.stdout
    def probe(self):
        if self._call('probe'):raise KeychainFailure('PERSONAL_KEYCHAIN_RESPONSE_INVALID')
    def load(self):
        try:return Session(**strict_json(self._call('read'))).validate()
        except Rejected:raise
        except Exception:raise KeychainFailure('PERSONAL_KEYCHAIN_RESPONSE_INVALID') from None
    def save(self,session):
        session.validate();data=json.dumps(asdict(session),allow_nan=False,separators=(',',':')).encode()
        if len(data)>65536:raise KeychainFailure('PERSONAL_KEYCHAIN_RESPONSE_LIMIT')
        if self._call('write',data):raise KeychainFailure('PERSONAL_KEYCHAIN_RESPONSE_INVALID')
    def delete(self):
        if self._call('delete'):raise KeychainFailure('PERSONAL_KEYCHAIN_RESPONSE_INVALID')
