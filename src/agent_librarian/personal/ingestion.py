"""CLI-only, journaled file ingestion. Never imported by the research gateway."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
from ..gateway.common import Rejected, ident, strict_json
from ..projects import ProjectMappings, project_path
from .state import private_dir, read_private, write_private

MAX_FILE = 8 * 1024 * 1024
MAX_FILES = 100
MAX_TOTAL = 32 * 1024 * 1024
# Narrow subset of the consumer-file registry reviewed in upstream constants.py.
FORMATS = {'.md', '.txt', '.pdf', '.docx', '.csv', '.pptx', '.epub'}
UNCERTAIN = {'REGISTERING', 'STARTING', 'FINALIZING', 'UNKNOWN'}


def digest(data):return hashlib.sha256(data).hexdigest()


def file_bytes(path):
    p=Path(path).absolute()
    if any(x.is_symlink() for x in (p,*p.parents)):raise Rejected('IMPORT_SYMLINK_REJECTED')
    if '..' in p.parts:raise Rejected('IMPORT_PATH_UNSAFE')
    directory=os.open(p.anchor,os.O_RDONLY|os.O_DIRECTORY)
    try:
        for part in p.parts[1:-1]:
            nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=directory);os.close(directory);directory=nxt
        fd=os.open(p.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
        with os.fdopen(fd,'rb') as f:
            start=os.fstat(f.fileno())
            if not stat.S_ISREG(start.st_mode) or start.st_nlink!=1 or not 0<start.st_size<=MAX_FILE:raise Rejected('IMPORT_FILE_INVALID_OR_TOO_LARGE')
            raw=f.read(MAX_FILE+1);end=os.fstat(f.fileno());named=os.stat(p.name,dir_fd=directory,follow_symlinks=False)
            fields=lambda x:(x.st_dev,x.st_ino,x.st_size,x.st_mtime_ns,x.st_ctime_ns)
            if fields(start)!=fields(end) or fields(end)!=fields(named) or len(raw)!=end.st_size:raise Rejected('IMPORT_LOCAL_FILE_CHANGED')
    finally:os.close(directory)
    if len(raw)>MAX_FILE:raise Rejected('IMPORT_FILE_INVALID_OR_TOO_LARGE')
    return raw


def payload(entry):
    raw=file_bytes(entry['path'])
    if digest(raw)!=entry['sha256']:raise Rejected('IMPORT_LOCAL_FILE_CHANGED')
    if entry['json_adapter']:
        try:strict_json(raw)
        except (ValueError,UnicodeError,RecursionError):raise Rejected('IMPORT_JSON_INVALID') from None
        raw=('# '+entry['relative_path']+'\n\n```json\n').encode()+raw+(b'' if raw.endswith(b'\n') else b'\n')+b'```\n'
    if len(raw)>MAX_FILE or digest(raw)!=entry['upload_sha256']:raise Rejected('IMPORT_PAYLOAD_CHANGED')
    return raw


def filename(name):
    if (not isinstance(name,str) or not name or len(name)>240 or name in ('.','..')
            or any(ord(c)<32 or 0xD800<=ord(c)<=0xDFFF or c in '/\\' for c in name)):raise Rejected('IMPORT_FILENAME_INVALID')
    return name


def directory_entries(root):
    stack=[root];seen=0
    while stack:
        directory=stack.pop();children=[]
        with os.scandir(directory) as entries:
            for entry in entries:
                seen+=1
                if seen>1000:raise Rejected('IMPORT_DIRECTORY_ENTRY_LIMIT')
                children.append(entry)
        for entry in sorted(children,key=lambda e:e.name):
            path=Path(entry.path)
            if entry.is_dir(follow_symlinks=False):stack.append(path)
            else:yield path


def plan(path,project,notebook_id,relative_names=False,json_as_markdown=False):
    root=Path(path).expanduser().absolute();project=project_path(project);ident(notebook_id)
    if any(p.is_symlink() for p in (root,*root.parents)):raise Rejected('IMPORT_SYMLINK_REJECTED')
    if not root.exists():raise Rejected('IMPORT_PATH_MISSING')
    entries=[];excluded=[];errors=[];names=set();total=0
    files=[root] if root.is_file() else directory_entries(root)
    for p in files:
        rel=p.name if root.is_file() else p.relative_to(root).as_posix()
        if p.name=='.DS_Store' or p.name.startswith('._'):
            excluded.append(rel);continue
        if p.is_symlink():errors.append({'path':rel,'code':'IMPORT_SYMLINK_REJECTED'});continue
        if p.is_dir():continue
        if len(entries)+len(errors)>=MAX_FILES:raise Rejected('IMPORT_FILE_COUNT_LIMIT')
        try:
            raw=file_bytes(p);adapter=p.suffix.lower()=='.json' and json_as_markdown
            if p.suffix.lower() not in FORMATS and not adapter:raise Rejected('IMPORT_FORMAT_UNSUPPORTED')
            name=filename(rel.replace('/','__') if relative_names else p.name)
            if adapter:
                strict_json(raw);name=filename(name+'.md')
            if name in names:raise Rejected('IMPORT_FILENAME_COLLISION')
            names.add(name)
            e={'path':str(p),'relative_path':rel,'filename':name,'sha256':digest(raw),'bytes':len(raw),'json_adapter':adapter}
            upload=('# '+rel+'\n\n```json\n').encode()+raw+(b'' if raw.endswith(b'\n') else b'\n')+b'```\n' if adapter else raw
            if len(upload)>MAX_FILE:raise Rejected('IMPORT_FILE_INVALID_OR_TOO_LARGE')
            e.update(upload_sha256=digest(upload),upload_bytes=len(upload));entries.append(e);total+=len(upload)
            if total>MAX_TOTAL:raise Rejected('IMPORT_TOTAL_LIMIT')
        except OSError:errors.append({'path':rel,'code':'IMPORT_FILE_UNREADABLE'})
        except (ValueError,UnicodeError,RecursionError):errors.append({'path':rel,'code':'IMPORT_JSON_INVALID'})
        except Rejected as error:
            if error.code=='IMPORT_TOTAL_LIMIT':raise
            errors.append({'path':rel,'code':error.code})
    data={'schema_version':1,'project':project,'notebook_id':notebook_id,'root':str(root),'entries':entries,
          'excluded':excluded,'errors':errors,'network_operations':0,'total_upload_bytes':total}
    data['plan_sha256']=plan_hash(data)
    return data


def plan_hash(data):return digest(json.dumps({k:v for k,v in data.items() if k!='plan_sha256'},sort_keys=True,separators=(',',':')).encode())


def validate_plan(data):
    if not isinstance(data,dict) or data.get('schema_version')!=1 or data.get('plan_sha256')!=plan_hash(data):raise Rejected('IMPORT_PLAN_INVALID')
    if data.get('errors') or not isinstance(data.get('entries'),list) or not 1<=len(data['entries'])<=MAX_FILES:raise Rejected('IMPORT_PLAN_NOT_EXECUTABLE')
    ident(data['notebook_id']);project_path(data['project']);names=set();total=0
    for entry in data['entries']:
        name=filename(entry['filename'])
        root=Path(data['root']);source=Path(entry['path'])
        if not source.is_absolute() or not (source==root or source.is_relative_to(root)):raise Rejected('IMPORT_PLAN_PATH_MISMATCH')
        if name in names:raise Rejected('IMPORT_FILENAME_COLLISION')
        names.add(name)
        if type(entry.get('json_adapter')) is not bool:raise Rejected('IMPORT_PLAN_INVALID')
        if Path(entry['path']).suffix.lower() not in FORMATS and not (entry['json_adapter'] and Path(entry['path']).suffix.lower()=='.json'):raise Rejected('IMPORT_FORMAT_UNSUPPORTED')
        total+=len(payload(entry))
    if total>MAX_TOTAL:raise Rejected('IMPORT_TOTAL_LIMIT')


class Importer:
    def __init__(self,home,state,project,notebook_id,admin_factory=None):
        self.home=Path(home).absolute();self.state=state;self.project=project_path(project);self.nb=ident(notebook_id)
        mapping=ProjectMappings(self.home).resolve(project)
        if mapping['status']!='MAPPED' or self.nb not in mapping['notebook_ids']:raise Rejected('NOTEBOOK_NOT_ALLOWED')
        self.account=state.load()['account_id']
        self.folder=self.home/'imports'
        self.path=self.folder/(digest((self.account+'\n'+self.nb).encode())+'.json')
        self.admin_factory=admin_factory

    @contextmanager
    def lock(self):
        private_dir(self.folder,create=True)
        fd=os.open(self.folder/'imports.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
        try:fcntl.flock(fd,fcntl.LOCK_EX);yield
        finally:os.close(fd)

    def load(self):
        data=read_private(self.path) if self.path.exists() else {'schema_version':1,'account_id':self.account,'notebook_id':self.nb,'entries':{}}
        if data.get('schema_version')!=1 or data.get('account_id')!=self.account or data.get('notebook_id')!=self.nb or not isinstance(data.get('entries'),dict):raise Rejected('IMPORT_JOURNAL_INVALID')
        return data

    def save(self,data):
        write_private(self.path,data)
        fd=os.open(self.folder,os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)

    def result(self,data):
        entries=[{k:v for k,v in e.items() if k not in ('session_url','baseline_ids')} for e in data['entries'].values()]
        return {'status':'COMPLETE' if entries and all(e['state']=='READY' for e in entries) else 'INCOMPLETE',
                'notebook_id':self.nb,'entries':entries,'source_count':len(entries)}

    def status(self):return self.result(self.load())

    def authorized(self):
        config=self.state.load()
        if config['account_id']!=self.account:raise Rejected('ACCOUNT_IDENTITY_MISMATCH')
        if not config['authenticated'] or (self.state.path/'DISABLED').exists():raise Rejected('AUTHENTICATION_REQUIRED')
        mapping=ProjectMappings(self.home).resolve(self.project)
        if mapping['status']!='MAPPED' or self.nb not in mapping['notebook_ids']:raise Rejected('NOTEBOOK_NOT_ALLOWED')

    def admin(self):
        self.authorized()
        if self.admin_factory:return self.admin_factory()
        from .source_admin import browser_source_admin
        return browser_source_admin(self.state,self.nb)

    def reconcile(self,data,sources):
        for entry in data['entries'].values():
            sid=entry.get('source_id');matches=[s for s in sources if s['id']==sid] if sid else []
            if len(matches)==1:
                source=matches[0]
                if source['title']!=entry['filename']:
                    entry['failure']='IMPORT_REMOTE_TITLE_CHANGED';continue
                entry['processing_status']=source.get('status')
                if source.get('status')==2 and entry['state'] in ('FINALIZING','SUBMITTED','READY'):entry.update(state='READY',failure=None)
                elif source.get('status')==3 and source.get('source_type') in (1,2,4,11,14):entry.update(state='FAILED',failure='SOURCE_PROCESSING_FAILED')
                # Other/unknown status is never treated as successful completion.
            elif sid:entry['failure']='SOURCE_NOT_IN_INVENTORY'
            elif entry['state'] in UNCERTAIN:
                # Candidate title/diff is evidence for owner selection, never automatic adoption.
                entry['candidate_source_ids']=[s['id'] for s in sources if s['title']==entry['filename'] and s['id'] not in entry.get('baseline_ids',[])]
        return data

    def refresh_cache(self,sources):
        inventory=self.state.inventory()
        if inventory.get('account_id')!=self.account:raise Rejected('ACCOUNT_IDENTITY_MISMATCH')
        found=[b for b in inventory['notebooks'] if b['notebook_id']==self.nb]
        if len(found)!=1:raise Rejected('NOTEBOOK_NOT_DISCOVERED')
        found[0]['sources']=[{'id':x['id'],'title':x['title']} for x in sources]
        write_private(self.state.path/'notebooks.json',inventory)

    def check(self):
        with self.lock(),self.state.lock():
            data=self.load();admin=self.admin()
            try:
                sources=admin.inventory(self.nb);self.reconcile(data,sources);self.refresh_cache(sources)
            finally:admin.close()
            self.save(data);return self.result(data)

    def run(self,data,approve=False):
        validate_plan(data)
        if data['project']!=self.project or data['notebook_id']!=self.nb:raise Rejected('IMPORT_PLAN_TARGET_MISMATCH')
        if not approve:return {'status':'PREVIEW','plan':data,'network_operations':0}
        # Approval is CLI-only; serializes against account logout/rebind and all imports.
        with self.lock(), self.state.lock():
            journal=self.load();admin=self.admin()
            try:
                sources=admin.inventory(self.nb);self.reconcile(journal,sources)
                new_names={e['filename'] for e in data['entries'] if e['filename'] not in journal['entries'] and not any(s['title']==e['filename'] for s in sources)}
                if len(sources)+len(new_names)>100:raise Rejected('IMPORT_NOTEBOOK_SOURCE_LIMIT')
                for e in data['entries']:
                    name=e['filename'];entry=journal['entries'].get(name)
                    if any(old['state'] in UNCERTAIN and old['filename']!=name and (old['sha256']==e['sha256'] or old['upload_sha256']==e['upload_sha256']) for old in journal['entries'].values()):
                        raise Rejected('IMPORT_UNCERTAIN_MATCHING_HASH')
                    if entry and entry['upload_sha256']!=e['upload_sha256']:raise Rejected('IMPORT_FILENAME_HASH_CONFLICT')
                    if entry is None:
                        if len(journal['entries'])>=MAX_FILES:raise Rejected('IMPORT_JOURNAL_LIMIT')
                        entry={'filename':name,'sha256':e['sha256'],'upload_sha256':e['upload_sha256'],'state':'PLANNED','project':self.project}
                        journal['entries'][name]=entry
                    if entry['state'] in UNCERTAIN or entry['state'] in ('READY','FAILED','SUBMITTED'):continue
                    if entry['state']=='PLANNED' and any(s['title']==name for s in sources):
                        entry.update(state='FAILED',failure='IMPORT_EXISTING_TITLE_UNKNOWN_HASH');self.save(journal);continue
                    raw=payload(e) # Recheck exact bytes immediately before any mutation; use this snapshot for upload.
                    if entry['state']=='PLANNED':
                        self.authorized()
                        entry.update(state='REGISTERING',baseline_ids=[s['id'] for s in sources]);self.save(journal)
                        entry['source_id']=ident(admin.register(self.nb,name));entry.pop('baseline_ids',None);entry['state']='REGISTERED';self.save(journal)
                    if entry['state']=='REGISTERED':
                        self.authorized()
                        entry['state']='STARTING';self.save(journal)
                        entry['session_url']=admin.start_upload(self.nb,name,len(raw),entry['source_id']);entry['state']='SESSION_READY';self.save(journal)
                    if entry['state']=='SESSION_READY':
                        # Staging is browser-local and may safely restart. Finalization is single-dispatch.
                        token=admin.stage(raw)
                        self.authorized()
                        entry['state']='FINALIZING';self.save(journal)
                        admin.finalize(entry['session_url'],token,len(raw))
                        entry['state']='SUBMITTED';self.save(journal)
                    sources=admin.inventory(self.nb);self.reconcile(journal,sources);self.refresh_cache(sources);self.save(journal)
            except BaseException as error:
                # Preserve REGISTERING/STARTING/FINALIZING even on KeyboardInterrupt or process loss.
                if isinstance(locals().get('entry'),dict):entry['failure']=error.code if isinstance(error,Rejected) else 'IMPORT_INTERRUPTED_OR_UNKNOWN'
                self.save(journal)
                if not isinstance(error,Exception):raise
                result=self.result(journal);result.update(status='ERROR',code=error.code if isinstance(error,Rejected) else 'IMPORT_OUTCOME_UNKNOWN')
                return result
            finally:admin.close()
            self.save(journal);return self.result(journal)
