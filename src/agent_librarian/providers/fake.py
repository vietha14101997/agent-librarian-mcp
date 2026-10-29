"""Fixed synthetic subprocess provider adapted from KN-MCP-02."""
import json, os, select, subprocess, sys, threading, time
from pathlib import Path
from ..gateway.common import NAMES, Rejected, strict_json, MAX_RESPONSE
HERE=Path(__file__).resolve().parent

class FakeProvider:
    """Killable, bounded IPC to a fixed synthetic worker. No live credential boundary."""
    def __init__(self, fixture, timeout, account_id):
        self.fixture = str(Path(fixture).resolve())
        self.timeout = timeout
        self.account_id = account_id
        self.lock = threading.Lock()
        self.process = None
        self.closed = False

    def _invoke(self, operation, args):
        if operation not in NAMES:
            raise Rejected('FORBIDDEN_OPERATION')
        with self.lock:
            if self.closed:
                raise Rejected('SERVICE_DISABLED')
            # Caller arguments cannot select executable, account, env, module or fixture.
            process = subprocess.Popen([sys.executable,'-I','-B',str(HERE/'worker.py'),self.fixture],
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                env={'LANG':'C','PYTHONIOENCODING':'utf-8'},close_fds=True)
            self.process = process
        try:
            deadline=time.monotonic()+self.timeout
            header=b''
            while b'\n' not in header:
                remaining=deadline-time.monotonic()
                if remaining<=0 or not select.select([process.stdout],[],[],remaining)[0]:
                    raise Rejected('PROVIDER_TIMEOUT_OUTCOME_UNKNOWN')
                chunk=os.read(process.stdout.fileno(),1024)
                if not chunk or len(header)+len(chunk)>1024:
                    raise Rejected('PROVIDER_STRUCTURE_INVALID')
                header+=chunk
            if header.count(b'\n')!=1 or not header.endswith(b'\n'):
                raise Rejected('PROVIDER_STRUCTURE_INVALID')
            try:identity=strict_json(header)
            except (ValueError,UnicodeError):raise Rejected('PROVIDER_STRUCTURE_INVALID')
            if not isinstance(identity,dict) or identity.get('kind')!='identity' or identity.get('account_id')!=self.account_id:
                raise Rejected('ACCOUNT_IDENTITY_MISMATCH')
            if identity.get('status')=='expired':raise Rejected('AUTHENTICATION_EXPIRED')
            if identity.get('status')!='ok':raise Rejected('PROVIDER_FAILURE')
            # Identity is checked before sending query text or any request arguments.
            request=json.dumps(dict(operation=operation,arguments=args),allow_nan=False).encode()+b'\n'
            # Fixed worker bounds output before writing. This is not a generic subprocess API.
            stdout,_=process.communicate(request,timeout=max(.001,deadline-time.monotonic()))
            if process.returncode or len(stdout)>MAX_RESPONSE:
                raise Rejected('PROVIDER_FAILURE')
            try:
                return strict_json(stdout)
            except (ValueError,UnicodeError,RecursionError):
                raise Rejected('PROVIDER_STRUCTURE_INVALID')
        except subprocess.TimeoutExpired:
            process.kill();process.communicate()
            raise Rejected('PROVIDER_TIMEOUT_OUTCOME_UNKNOWN')
        finally:
            if process.poll() is None:
                process.kill();process.communicate()
            with self.lock:
                if self.process is process:
                    self.process=None

    def close(self):
        with self.lock:
            self.closed=True
            if self.process and self.process.poll() is None:
                self.process.kill()

    def list_notebooks(self): return self._invoke(NAMES[0], {})
    def get_notebook(self, notebook_id): return self._invoke(NAMES[1], {'notebook_id': notebook_id})
    def query(self, notebook_id, query, source_ids):
        return self._invoke(NAMES[2], {'notebook_id': notebook_id, 'query': query, 'source_ids': source_ids})
    def get_source(self, notebook_id, source_id):
        return self._invoke(NAMES[3], {'notebook_id': notebook_id, 'source_id': source_id})

