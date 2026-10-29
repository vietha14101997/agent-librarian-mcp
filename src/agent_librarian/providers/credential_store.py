"""Narrow helper capability for a service-private OS credential store.

The compiled helper is supplied only through protected service configuration.
Secrets travel through anonymous pipes, never argv, environment, logs or files.
No helper is executed at import/construction time. No plaintext fallback exists.
"""
from dataclasses import asdict
import json
import subprocess
from ..gateway.common import Rejected,strict_json
from .session import Session

class KeychainSessionStore:
    def __init__(self,helper):self.helper=str(helper)
    def _call(self,operation,payload=None):
        try:
            result=subprocess.run([self.helper,operation],input=payload,capture_output=True,
                timeout=5,env={'PATH':'/usr/bin:/bin','LANG':'C'},check=False)
        except Exception:raise Rejected('CREDENTIAL_STORE_UNAVAILABLE') from None
        if result.returncode!=0 or len(result.stdout)>65536 or result.stderr:raise Rejected('CREDENTIAL_STORE_UNAVAILABLE')
        return result.stdout
    def load(self):
        try:return Session(**strict_json(self._call('read'))).validate()
        except Rejected:raise
        except Exception:raise Rejected('CREDENTIAL_STORE_INVALID') from None
    def save(self,session):
        session.validate();raw=json.dumps(asdict(session),separators=(',',':'),allow_nan=False).encode()
        if len(raw)>65536:raise Rejected('CREDENTIAL_STORE_INVALID')
        if self._call('write',raw):raise Rejected('CREDENTIAL_STORE_INVALID')
    def delete(self):
        if self._call('delete'):raise Rejected('CREDENTIAL_STORE_INVALID')
