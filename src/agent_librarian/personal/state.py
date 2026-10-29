"""User-only local state. Authentication secrets are never written here."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import uuid
from ..gateway.common import Rejected,strict_json

from ..locations import personal_state

DEFAULT_STATE=personal_state()

def private_dir(path,create=False):
    p=Path(path).absolute()
    if '..' in p.parts or any(x.is_symlink() for x in [p,*p.parents]):raise Rejected('PERSONAL_PATH_UNSAFE')
    if create:
        missing=[];part=p
        while not part.exists():missing.append(part);part=part.parent
        for part in reversed(missing):part.mkdir(mode=0o700)
    s=p.stat()
    if not stat.S_ISDIR(s.st_mode) or s.st_uid!=os.geteuid() or s.st_mode&0o077:raise Rejected('PERSONAL_STATE_PERMISSIONS_INVALID')
    return p

def read_private(path):
    p=Path(path)
    if p.is_symlink():raise Rejected('PERSONAL_PATH_UNSAFE')
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as f:
        s=os.fstat(f.fileno())
        if not stat.S_ISREG(s.st_mode) or s.st_uid!=os.geteuid() or s.st_mode&0o077 or s.st_nlink!=1 or s.st_size>262144:raise Rejected('PERSONAL_STATE_PERMISSIONS_INVALID')
        raw=f.read(262145)
    try:return strict_json(raw)
    except (ValueError,RecursionError):raise Rejected('PERSONAL_CONFIGURATION_INVALID') from None

def write_private(path,value):
    p=Path(path);private_dir(p.parent)
    if p.is_symlink():raise Rejected('PERSONAL_PATH_UNSAFE')
    raw=(json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+'\n').encode()
    if len(raw)>262144:raise Rejected('PERSONAL_CONFIGURATION_LIMIT')
    fd,name=tempfile.mkstemp(prefix='.librarian-',dir=p.parent)
    try:
        with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        os.replace(name,p)
    finally:
        if os.path.exists(name):os.unlink(name)

class PersonalState:
    def __init__(self,path=DEFAULT_STATE,create=False):
        self.path=private_dir(path,create=create);self.config_path=self.path/'personal.json'
        if not self.config_path.exists():
            if not create:raise Rejected('PERSONAL_NOT_INITIALIZED')
            if any(self.path.iterdir()):raise Rejected('PERSONAL_DIRECTORY_NOT_EMPTY')
            self.save({'schema_version':1,'mode':'PERSONAL_LOCAL','runtime_id':uuid.uuid4().hex,
                'account_id':'personal-'+uuid.uuid4().hex,'host':'notebooklm.google.com','authenticated':False,
                'selected_notebook':None,'generation':0,'query_permit':None})
        self.load()
    def load(self):
        c=read_private(self.config_path)
        keys={'schema_version','mode','runtime_id','account_id','host','authenticated','selected_notebook','generation','query_permit'}
        if not isinstance(c,dict) or set(c)!=keys or c['schema_version']!=1 or c['mode']!='PERSONAL_LOCAL':raise Rejected('PERSONAL_CONFIGURATION_INVALID')
        if not isinstance(c['runtime_id'],str) or len(c['runtime_id'])!=32 or any(x not in '0123456789abcdef' for x in c['runtime_id']):raise Rejected('PERSONAL_CONFIGURATION_INVALID')
        return c
    def save(self,config):write_private(self.config_path,config)
    @contextmanager
    def lock(self):
        fd=os.open(self.path/'personal.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
        try:
            if os.fstat(fd).st_uid!=os.geteuid():raise Rejected('PERSONAL_PATH_UNSAFE')
            fcntl.flock(fd,fcntl.LOCK_EX);yield
        finally:os.close(fd)
    def profile(self):
        p=self.path/'browser-profile'
        return private_dir(p,create=True)
    def inventory(self):
        return read_private(self.path/'notebooks.json')
    def select(self,notebook_id):
        with self.lock():
            c=self.load()
            if not c['authenticated']:raise Rejected('AUTHENTICATION_REQUIRED')
            matches=[b for b in self.inventory()['notebooks'] if b['notebook_id']==notebook_id]
            if len(matches)!=1:raise Rejected('NOTEBOOK_NOT_DISCOVERED')
            c.update(selected_notebook=matches[0],generation=c['generation']+1,query_permit=None);self.save(c)
            return {'status':'OK','selected_notebook_id':notebook_id,'source_count':len(matches[0]['sources'])}
    def approve_query(self,question,ack_history,notebook_id=None):
        if not ack_history:raise Rejected('QUERY_HISTORY_ACK_REQUIRED')
        if not isinstance(question,str) or not question.strip() or len(question)>2000:raise Rejected('QUERY_INVALID')
        with self.lock():
            c=self.load()
            if not c['authenticated']:raise Rejected('AUTHENTICATION_REQUIRED')
            if notebook_id is None:
                if not c['selected_notebook']:raise Rejected('NOTEBOOK_SELECTION_REQUIRED')
                notebook_id=c['selected_notebook']['notebook_id']
            if notebook_id not in {b['notebook_id'] for b in self.inventory()['notebooks']}:raise Rejected('NOTEBOOK_NOT_DISCOVERED')
            c['query_permit']={'question_sha256':hashlib.sha256(question.encode()).hexdigest(),
                'notebook_id':notebook_id,'state':'APPROVED','history_acknowledged':True}
            self.save(c)
        return {'status':'APPROVED_ONE_QUERY','notebook_id':notebook_id,'question_sha256':c['query_permit']['question_sha256']}
    def consume_query(self,notebook_id,question):
        with self.lock():
            c=self.load();p=c['query_permit']
            if (not c['authenticated'] or not isinstance(p,dict) or p.get('state')!='APPROVED' or p.get('notebook_id')!=notebook_id
                or p.get('question_sha256')!=hashlib.sha256(question.encode()).hexdigest()):raise Rejected('PERSONAL_QUERY_APPROVAL_REQUIRED')
            p['state']='DISPATCHED_NO_AUTOMATIC_RETRY';self.save(c)
