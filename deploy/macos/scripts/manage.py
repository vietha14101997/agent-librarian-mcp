#!/usr/bin/env python3
"""Owner-run deployment tool. Prints a plan by default. --apply is privileged.

Never run the privileged branch from an agent chat. No account/group changes,
login, network, dependencies or authentication capture are performed here.
"""
import argparse
import grp
import hashlib
import json
import os
from pathlib import Path
import plistlib
import pwd
import re
import shutil
import stat
import subprocess
import sys

BASE=Path('/Library/AgentLibrarian')
RELEASE=BASE/'releases/0.3.0'
SOCKET=Path('/private/var/run/agent-librarian/research.sock')
PLIST=Path('/Library/LaunchDaemons/org.agentlibrarian.provider.plist')
LABEL='org.agentlibrarian.provider'

def fail(code):raise ValueError(code)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def safe_path(path,owners=(0,),missing=False):
    p=Path(path)
    if not p.is_absolute() or '..' in p.parts:fail('UNSAFE_PATH')
    for part in [*reversed(p.parents),p]:
        if missing and not part.exists() and not part.is_symlink():continue
        s=part.lstat()
        if stat.S_ISLNK(s.st_mode) or s.st_uid not in owners or s.st_mode&0o022:fail('UNTRUSTED_PATH')
    return p

def read_bundle(bundle,expected,owners=(0,)):
    bundle=safe_path(bundle,owners);manifest=safe_path(bundle/'manifest.json',owners)
    if manifest.stat().st_size>2*1024*1024 or sha(manifest)!=expected:fail('BUNDLE_MANIFEST_MISMATCH')
    entries=json.loads(manifest.read_text())
    if not isinstance(entries,dict) or not 1<=len(entries)<=20000:fail('BUNDLE_MANIFEST_INVALID')
    total=0
    for relative,digest in entries.items():
        if not isinstance(relative,str) or Path(relative).is_absolute() or '..' in Path(relative).parts:fail('BUNDLE_PATH_INVALID')
        p=safe_path(bundle/relative,owners);s=p.lstat();total+=s.st_size
        if not stat.S_ISREG(s.st_mode) or s.st_nlink!=1 or s.st_size>200*1024*1024 or total>1024*1024*1024:fail('BUNDLE_FILE_INVALID')
        if any(x in ('.git','.venv','__pycache__','.DS_Store','export') or x.startswith('._') for x in Path(relative).parts):fail('BUNDLE_FILE_INVALID')
        if not isinstance(digest,str) or not re.fullmatch('[0-9a-f]{64}',digest) or sha(p)!=digest:fail('BUNDLE_FILE_MISMATCH')
    actual={str(p.relative_to(bundle)) for p in bundle.rglob('*') if p.is_file()}
    if actual!=set(entries)|{'manifest.json'} or any(p.is_symlink() for p in bundle.rglob('*')):fail('BUNDLE_UNLISTED_FILE')
    required={'runtime/bin/python3','libexec/keychain-helper','libexec/launcher.py','policy.json','fixture.json'}
    if not required<=set(entries):fail('BUNDLE_INCOMPLETE')
    if not os.access(bundle/'runtime/bin/python3',os.X_OK) or not os.access(bundle/'libexec/keychain-helper',os.X_OK):fail('BUNDLE_NOT_EXECUTABLE')
    if any(n.endswith('.pth') for n in entries):fail('EXECUTABLE_PTH_NOT_ACCEPTED')
    return entries

def identities(service,agent,group):
    if not all(re.fullmatch('[A-Za-z_][A-Za-z0-9_-]{0,31}',x) for x in (service,agent,group)):fail('IDENTITY_NAME_INVALID')
    s=pwd.getpwnam(service);a=pwd.getpwnam(agent);g=grp.getgrnam(group)
    if min(s.pw_uid,a.pw_uid,g.gr_gid)<=0 or s.pw_uid==a.pw_uid:fail('DISTINCT_NONROOT_IDENTITIES_REQUIRED')
    for p in (s,a):
        groups=os.getgrouplist(p.pw_name,p.pw_gid)
        if 80 in groups or 204 in groups:fail('ADMIN_OR_DEVELOPER_PRINCIPAL_REJECTED')
        if g.gr_gid not in groups:fail('PREEXISTING_CLIENT_GROUP_MEMBERSHIP_REQUIRED')
    return s,a,g

def launch_plist(service,group):
    return {'Label':LABEL,'UserName':service,'GroupName':group,
        'ProgramArguments':[str(RELEASE/'runtime/bin/python3'),'-I','-B',str(RELEASE/'libexec/launcher.py')],
        'WorkingDirectory':str(BASE/'state'),'RunAtLoad':False,'KeepAlive':False,
        'EnvironmentVariables':{'PATH':'/usr/bin:/bin','LANG':'en_US.UTF-8','PYTHONDONTWRITEBYTECODE':'1'},
        'Umask':0o077,'ProcessType':'Background','ThrottleInterval':30,
        'StandardOutPath':'/dev/null','StandardErrorPath':str(BASE/'state/audit.jsonl')}

def payload_plan(service,agent,group,policy_digest):
    return {'schema_version':1,'version':'0.3.0','service_uid':service.pw_uid,'agent_uid':agent.pw_uid,
        'client_gid':group.gr_gid,'client_id':'research-client','release_root':str(RELEASE),
        'integrity_manifest':str(BASE/'integrity.json'),'executable':str(RELEASE/'runtime/bin/python3'),
        'keychain_helper':str(RELEASE/'libexec/keychain-helper'),'policy':str(BASE/'config/policy.json'),
        'policy_sha256':policy_digest,'socket':str(SOCKET),'state_dir':str(BASE/'state'),
        'canary_store':str(BASE/'state/canary.json'),'fixture':str(BASE/'state/fixture.json'),
        'live_enabled':False,'host':'notebooklm.google.com','expected_email':'',
        'gates':{'G'+str(i):False for i in range(1,13)},'owner_approval_id':''}

def new_file(path,data,mode,uid=0,gid=0):
    safe_path(path,owners=(0,uid),missing=True)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno());os.fchown(f.fileno(),uid,gid);os.fchmod(f.fileno(),mode)

def install(args):
    s,a,g=identities(args.service_user,args.agent_user,args.client_group)
    expected=args.bundle_sha256
    if not re.fullmatch('[0-9a-f]{64}',expected or ''):fail('EXPECTED_BUNDLE_SHA256_REQUIRED')
    # An apply source and every ancestor must be administrator-owned and immutable to the agent.
    entries=read_bundle(Path(args.bundle),expected,owners=(0,) if args.apply else (0,os.geteuid()))
    plan={'action':'INSTALL_SYNTHETIC_ONLY','privileges':'root required for --apply; service runs nonroot',
        'new_paths':[str(BASE),str(SOCKET.parent),str(PLIST)],'live_enabled':False,
        'requires_owner_approval':True,'does_not_bootstrap_launchd':True,'rollback':'manage.py rollback --apply',
        'service_uid':s.pw_uid,'agent_uid':a.pw_uid,'manifest_sha256':expected}
    if not args.apply:return plan
    if sys.platform!='darwin' or os.geteuid()!=0:fail('OWNER_ROOT_EXECUTION_REQUIRED')
    os.umask(0o022)
    # Exclusive creation prevents overwriting preexisting installations/configuration.
    for p in (BASE,SOCKET.parent,PLIST):
        safe_path(p,missing=True)
        if p.exists():fail('EXISTING_INSTALLATION_REFUSED')
    existing=subprocess.run(['/bin/launchctl','print','system/'+LABEL],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    if existing.returncode==0:fail('EXISTING_LAUNCHD_LABEL_REFUSED')
    BASE.mkdir(mode=0o755);(BASE/'releases').mkdir(mode=0o755);RELEASE.mkdir(mode=0o755)
    try:
        for relative,digest in entries.items():
            dest=RELEASE/relative;dest.parent.mkdir(parents=True,exist_ok=True)
            source=Path(args.bundle)/relative
            new_file(dest,source.read_bytes(),0o755 if os.access(source,os.X_OK) else 0o644)
            if sha(dest)!=digest:fail('COPIED_FILE_INTEGRITY_MISMATCH')
        (BASE/'config').mkdir(mode=0o750);os.chown(BASE/'config',0,g.gr_gid)
        (BASE/'state').mkdir(mode=0o700);os.chown(BASE/'state',s.pw_uid,g.gr_gid)
        # Both credentials and profile are private to the service identity; no login is performed.
        (BASE/'state/browser-profile').mkdir(mode=0o700);os.chown(BASE/'state/browser-profile',s.pw_uid,g.gr_gid)
        SOCKET.parent.mkdir(mode=0o750);os.chown(SOCKET.parent,s.pw_uid,g.gr_gid);os.chmod(SOCKET.parent,0o2750)
        policy=(Path(args.bundle)/'policy.json').read_bytes()
        new_file(BASE/'config/policy.json',policy,0o640,0,g.gr_gid)
        config=payload_plan(s,a,g,hashlib.sha256(policy).hexdigest())
        new_file(BASE/'config/runtime.json',(json.dumps(config,indent=2)+'\n').encode(),0o640,0,g.gr_gid)
        new_file(BASE/'integrity.json',(json.dumps(entries,sort_keys=True)+'\n').encode(),0o644)
        new_file(BASE/'state/fixture.json',(Path(args.bundle)/'fixture.json').read_bytes(),0o600,s.pw_uid,g.gr_gid)
        import secrets
        account=json.loads(policy)['account_id']
        new_file(BASE/'state/canary.json',json.dumps({'synthetic_only':True,'account_id':account,'secret':'SYNTHETIC_'+secrets.token_hex(16)}).encode(),0o600,s.pw_uid,g.gr_gid)
        new_file(BASE/'state/DISABLED',b'Owner review and explicit enablement required.\n',0o600,s.pw_uid,g.gr_gid)
        new_file(BASE/'state/audit.jsonl',b'',0o600,s.pw_uid,g.gr_gid)
        plist=plistlib.dumps(launch_plist(s.pw_name,g.gr_name),sort_keys=True)
        new_file(PLIST,plist,0o644)
        new_file(BASE/'installation.json',json.dumps({'version':'0.3.0','plist_sha256':hashlib.sha256(plist).hexdigest(),
            'manifest_sha256':expected,'complete':True},indent=2).encode(),0o600)
    except Exception:
        # Do not recursively remove potentially changed files or private state after a partial install.
        # Owner must inspect partial paths using the documented rollback procedure.
        raise
    return plan|{'installed':True,'started':False,'disabled':True}

def operate(action,apply):
    commands={'status':['/bin/launchctl','print','system/'+LABEL],
        'start':['/bin/launchctl','bootstrap','system',str(PLIST)],
        'stop':['/bin/launchctl','bootout','system/'+LABEL],
        'restart':['/bin/launchctl','kickstart','-k','system/'+LABEL]}
    if not apply:return {'action':action,'apply':False,'command':commands.get(action),'state_preserved':True,'requires_owner_approval':True}
    if sys.platform!='darwin' or os.geteuid()!=0:fail('OWNER_ROOT_EXECUTION_REQUIRED')
    safe_path(BASE/'installation.json');receipt=json.loads((BASE/'installation.json').read_text())
    if action in ('disable','enable'):
        state=BASE/'state';safe_path(state,owners=(0,state.stat().st_uid))
        target=state/'DISABLED'
        if action=='disable':
            if not target.exists():new_file(target,b'Owner disabled\n',0o600,state.stat().st_uid,state.stat().st_gid)
        else:
            safe_path(target,owners=(0,state.stat().st_uid));target.unlink()
        return {'action':action,'verified':True}
    if action=='rollback':
        safe_path(PLIST)
        if sha(PLIST)!=receipt['plist_sha256']:fail('ROLLBACK_INTEGRITY_MISMATCH')
        # Do not delete code/state. Stop first; archive the exact plist without overwriting anything.
        status=subprocess.run(['/bin/launchctl','print','system/'+LABEL],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        if status.returncode==0:
            stopped=subprocess.run(commands['stop'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            if stopped.returncode:fail('ROLLBACK_STOP_FAILED')
        backup=BASE/'rollback';backup.mkdir(mode=0o700,exist_ok=True);safe_path(backup)
        target=backup/PLIST.name
        if target.exists():fail('ROLLBACK_BACKUP_EXISTS')
        os.link(PLIST,target);PLIST.unlink()
        return {'action':'rollback','service_unloaded':True,'plist_preserved':True,'code_and_private_state_preserved':True}
    if action not in commands:fail('UNKNOWN_ACTION')
    if action in ('start','restart') and (BASE/'state/DISABLED').exists():fail('SERVICE_DISABLED')
    safe_path(PLIST)
    if sha(PLIST)!=receipt['plist_sha256']:fail('LAUNCH_CONFIGURATION_CHANGED')
    r=subprocess.run(commands[action],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    return {'action':action,'command_succeeded':r.returncode==0,'exit_code':r.returncode}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('install','status','start','stop','restart','disable','enable','rollback'))
    p.add_argument('--apply',action='store_true');p.add_argument('--bundle');p.add_argument('--bundle-sha256')
    p.add_argument('--service-user');p.add_argument('--agent-user');p.add_argument('--client-group');a=p.parse_args()
    try:
        result=install(a) if a.action=='install' else operate(a.action,a.apply)
        print(json.dumps(result,indent=2));return 0
    except Exception:
        # No exception text: paths/config could contain private account material.
        print(json.dumps({'status':'ERROR','code':'DEPLOYMENT_REJECTED_INSPECT_PRIVATELY'}),file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
