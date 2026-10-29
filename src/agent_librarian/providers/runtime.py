"""Portable protected-runtime validation. macOS paths/templates live in deploy/macos."""
import fcntl
import hashlib
import os
from pathlib import Path
import signal
import stat
import sys
from ..gateway.common import Rejected,strict_json,load_policy
from .service import ProviderService,SecretConfinement
from .credential_store import KeychainSessionStore
from .session import SessionManager,GOOGLE_HOSTS
from .https_transport import GeminiHTTPS
from .gemini import GeminiResearchProvider,AccountCapability

GATES=tuple('G'+str(i) for i in range(1,13))

def protected_path(path,owners=(0,),directory=False,private=False):
    p=Path(path)
    if not p.is_absolute() or '..' in p.parts:raise Rejected('DEPLOYMENT_PATH_INVALID')
    for part in [*reversed(p.parents),p]:
        s=part.lstat()
        if stat.S_ISLNK(s.st_mode) or s.st_uid not in owners or s.st_mode&0o022:raise Rejected('DEPLOYMENT_PATH_UNTRUSTED')
    s=p.lstat()
    if (directory and not stat.S_ISDIR(s.st_mode)) or (not directory and (not stat.S_ISREG(s.st_mode) or s.st_nlink!=1)):raise Rejected('DEPLOYMENT_PATH_INVALID')
    if private and s.st_mode&0o077:raise Rejected('DEPLOYMENT_PRIVATE_MODE_REQUIRED')
    return p

def protected_json(path,limit=131072):
    p=protected_path(path)
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as f:
        if os.fstat(f.fileno()).st_size>limit:raise Rejected('DEPLOYMENT_FILE_LIMIT')
        raw=f.read(limit+1)
    if len(raw)>limit:raise Rejected('DEPLOYMENT_FILE_LIMIT')
    try:return strict_json(raw),hashlib.sha256(raw).hexdigest()
    except (ValueError,RecursionError):raise Rejected('DEPLOYMENT_CONFIGURATION_INVALID') from None

def verify_integrity(root,manifest):
    root=protected_path(root,directory=True);entries,_=protected_json(manifest,limit=2*1024*1024)
    if not isinstance(entries,dict) or not 1<=len(entries)<=20000:raise Rejected('EXECUTABLE_MANIFEST_INVALID')
    for relative,expected in entries.items():
        if not isinstance(relative,str) or Path(relative).is_absolute() or '..' in Path(relative).parts:raise Rejected('EXECUTABLE_MANIFEST_INVALID')
        path=protected_path(root/relative)
        if not isinstance(expected,str) or len(expected)!=64 or path.stat().st_size>200*1024*1024:raise Rejected('EXECUTABLE_MANIFEST_INVALID')
        h=hashlib.sha256()
        with path.open('rb') as f:
            for block in iter(lambda:f.read(1048576),b''):h.update(block)
        if h.hexdigest()!=expected:raise Rejected('EXECUTABLE_INTEGRITY_MISMATCH')
    # Unlisted executable or .pth/import injection must not ride beside reviewed files.
    actual={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}
    if actual!=set(entries):raise Rejected('EXECUTABLE_MANIFEST_INCOMPLETE')
    for p in root.rglob('*'):
        if p.is_symlink():raise Rejected('DEPLOYMENT_PATH_UNTRUSTED')
    return entries

def load_runtime(path,require_identity=True):
    config,digest=protected_json(path)
    keys={'schema_version','version','service_uid','agent_uid','client_gid','client_id','release_root','integrity_manifest',
        'executable','keychain_helper','policy','policy_sha256','socket','state_dir','canary_store','fixture','live_enabled',
        'host','expected_email','gates','owner_approval_id'}
    if not isinstance(config,dict) or set(config)!=keys or type(config['schema_version']) is not int or config['schema_version']!=1 or config['version']!='0.3.0':raise Rejected('DEPLOYMENT_CONFIGURATION_INVALID')
    for key in ('service_uid','agent_uid','client_gid'):
        if type(config[key]) is not int or config[key]<=0:raise Rejected('DEPLOYMENT_PRINCIPAL_INVALID')
    if config['service_uid']==config['agent_uid'] or require_identity and os.geteuid()!=config['service_uid']:raise Rejected('SERVICE_PRINCIPAL_MISMATCH')
    if type(config['live_enabled']) is not bool or config['host'] not in GOOGLE_HOSTS:raise Rejected('DEPLOYMENT_CONFIGURATION_INVALID')
    release=Path(config['release_root']);entries=verify_integrity(release,config['integrity_manifest'])
    for key in ('executable','keychain_helper'):
        p=protected_path(config[key])
        if not p.is_relative_to(release) or str(p.relative_to(release)) not in entries or not os.access(p,os.X_OK):raise Rejected('EXECUTABLE_INTEGRITY_MISMATCH')
    policy=protected_path(config['policy']);_,policy_digest=protected_json(policy)
    if policy_digest!=config['policy_sha256']:raise Rejected('SERVICE_POLICY_CHANGED')
    state=protected_path(config['state_dir'],owners=(0,config['service_uid']),directory=True,private=True)
    parent=protected_path(Path(config['socket']).parent,owners=(0,config['service_uid']),directory=True)
    if parent.stat().st_uid!=config['service_uid'] or parent.stat().st_gid!=config['client_gid']:raise Rejected('DEPLOYMENT_SOCKET_OWNER_INVALID')
    if Path(config['socket']).exists():
        s=Path(config['socket']).lstat()
        if not stat.S_ISSOCK(s.st_mode) or s.st_uid!=config['service_uid']:raise Rejected('DEPLOYMENT_SOCKET_OWNER_INVALID')
        if require_identity:raise Rejected('IPC_SOCKET_EXISTS')
    if require_identity and Path(sys.executable).resolve()!=Path(config['executable']):raise Rejected('EXECUTABLE_INTEGRITY_MISMATCH')
    for key in ('canary_store','fixture'):
        p=Path(config[key])
        if not p.is_relative_to(state):raise Rejected('CREDENTIAL_PATH_REJECTED')
        if not config['live_enabled']:protected_path(p,owners=(0,config['service_uid']),private=key=='canary_store')
    if config['live_enabled']:
        if (not isinstance(config['gates'],dict) or set(config['gates'])!=set(GATES)
            or any(v is not True for v in config['gates'].values()) or not isinstance(config['owner_approval_id'],str)
            or not config['owner_approval_id'].strip()):raise Rejected('LIVE_OWNER_GATES_REQUIRED')
        if not isinstance(config['expected_email'],str) or '@' not in config['expected_email']:raise Rejected('LIVE_ACCOUNT_APPROVAL_REQUIRED')
    return config,digest

def runtime_status(path):
    c,_=load_runtime(path,require_identity=False)
    return {'status':'CONFIGURATION_VERIFIED_NOT_HOST_ISOLATION','version':c['version'],
        'live_enabled':c['live_enabled'],'disabled':(Path(c['state_dir'])/'DISABLED').exists(),
        'network_operations':0,'account_identity_verified':False}

def run_runtime(path):
    c,digest=load_runtime(path);state=Path(c['state_dir'])
    # Service-only lock prevents competing session refresh writers and browser fallback.
    fd=os.open(state/'runtime.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    lock=os.fdopen(fd,'r+')
    try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except OSError:lock.close();raise Rejected('SERVICE_ALREADY_RUNNING') from None
    service=None
    try:
        if (state/'DISABLED').exists():raise Rejected('SERVICE_DISABLED')
        def disabled():
            if (state/'DISABLED').exists():return True
            try:return protected_json(path)[1]!=digest
            except Exception:return True
        if c['live_enabled']:
            policy=load_policy(c['policy']);store=KeychainSessionStore(c['keychain_helper'])
            sessions=SessionManager(store,policy['account_id'],c['expected_email'],c['host'])
            transport=GeminiHTTPS(sessions,policy['notebooks'],policy['timeout_seconds'],disabled=disabled)
            backend=GeminiResearchProvider(transport,AccountCapability(policy['account_id']),policy['notebooks'],policy['query_max_chars'])
            provider=SecretConfinement(backend,sessions.secrets)
            service=ProviderService(c['socket'],c['policy'],c['fixture'],None,c['agent_uid'],c['client_id'],provider=provider)
        else:
            service=ProviderService(c['socket'],c['policy'],c['fixture'],c['canary_store'],c['agent_uid'],c['client_id'])
        # Root-owned protected config is checked per call as well as the service policy.
        original=service.gateway.disabled
        service.gateway.disabled=lambda:original() or disabled()
        previous=signal.signal(signal.SIGTERM,lambda _s,_f:(_ for _ in ()).throw(SystemExit(0)))
        try:service.run()
        finally:signal.signal(signal.SIGTERM,previous)
    finally:
        if service:service.close()
        lock.close()
