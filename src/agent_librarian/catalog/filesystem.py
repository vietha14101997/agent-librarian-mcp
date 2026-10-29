"""Bounded, descriptor-relative, no-symlink document reads on POSIX systems."""
import hashlib
import os
from pathlib import Path
import stat
from .model import CatalogError, relative_path

SUPPORTED={'.md','.txt','.json','.yaml','.yml','.csv','.rst','.pdf','.docx'}
PRIVATE_DIRS={'.git','.venv','venv','__pycache__','node_modules','.cache','private','secrets','credentials','browser-profiles','chrome-profiles','firefox-profiles'}
PRIVATE_FILES={'auth.json','cookies.json','credentials.json','credentials.enc','tokens.json','token.json','secrets.json','session.json','storage_state.json','login data','cookies','.ds_store'}

def denied(parts):
    return any(p.casefold() in PRIVATE_DIRS or p.startswith('.') or p.casefold() in PRIVATE_FILES
               or p.casefold().endswith(('.pem','.key','.p12','.keychain-db')) for p in parts)

class SafeRoot:
    def __init__(self,root,max_file_bytes=2*1024*1024,max_files=1000,max_total_bytes=16*1024*1024,max_entries=3000):
        self.path=Path(root).absolute()
        if denied([self.path.name]):raise CatalogError('PRIVATE_ROOT_REJECTED')
        if any(p.is_symlink() for p in [self.path,*self.path.parents]):raise CatalogError('ROOT_SYMLINK_REJECTED')
        if not hasattr(os,'O_NOFOLLOW') or os.open not in os.supports_dir_fd:raise CatalogError('PLATFORM_UNSUPPORTED')
        if not self.path.is_dir():raise CatalogError('ROOT_MISSING')
        self.fd=os.open(self.path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        self.max_file_bytes=max_file_bytes;self.max_files=max_files;self.max_total_bytes=max_total_bytes;self.max_entries=max_entries
        if any(type(v) is not int or v<=0 for v in [max_file_bytes,max_files,max_total_bytes,max_entries]):
            self.close();raise CatalogError('LIMIT_INVALID')

    def __enter__(self):return self
    def __exit__(self,*_):self.close()
    def close(self):
        if self.fd is not None:os.close(self.fd);self.fd=None

    def hash_file(self,relative):
        relative_path(relative);parts=relative.split('/')
        if denied(parts):raise CatalogError('PRIVATE_PATH_REJECTED')
        if Path(relative).suffix.lower() not in SUPPORTED:raise CatalogError('UNSUPPORTED_DOCUMENT_TYPE')
        fd=os.dup(self.fd)
        try:
            for p in parts[:-1]:
                nxt=os.open(p,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=nxt
            file_fd=os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
            try:
                start=os.fstat(file_fd)
                if not stat.S_ISREG(start.st_mode) or start.st_nlink!=1:raise CatalogError('NONREGULAR_OR_HARDLINK_REJECTED')
                if start.st_size>self.max_file_bytes:raise CatalogError('FILE_SIZE_LIMIT')
                h=hashlib.sha256();size=0
                while data:=os.read(file_fd,65536):
                    size+=len(data)
                    if size>self.max_file_bytes:raise CatalogError('FILE_SIZE_LIMIT')
                    h.update(data)
                end=os.fstat(file_fd);named=os.stat(parts[-1],dir_fd=fd,follow_symlinks=False)
                fields=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
                if fields(start)!=fields(end) or fields(end)!=fields(named) or size!=end.st_size:
                    raise CatalogError('FILE_CHANGED_DURING_READ')
                return h.hexdigest(),size
            finally:os.close(file_fd)
        except CatalogError:raise
        except (OSError,ValueError):raise CatalogError('FILE_MISSING_OR_UNSAFE') from None
        finally:os.close(fd)

    def inventory(self):
        found={};issues=[];entries=0;total=0
        def walk(fd,prefix,depth):
            nonlocal entries,total
            if depth>16:raise CatalogError('DIRECTORY_DEPTH_LIMIT')
            # Iterate a bounded number before sorting, rather than sorting an unbounded directory.
            names=[]
            with os.scandir(fd) as it:
                for e in it:
                    entries+=1
                    if entries>self.max_entries:raise CatalogError('SCAN_ENTRY_LIMIT')
                    names.append(e.name)
            for name in sorted(names):
                parts=prefix+[name];rel='/'.join(parts)
                if denied(parts):continue
                try:s=os.stat(name,dir_fd=fd,follow_symlinks=False)
                except OSError:issues.append({'relative_path':rel,'code':'FILE_MISSING_OR_UNSAFE'});continue
                if stat.S_ISLNK(s.st_mode):issues.append({'relative_path':rel,'code':'SYMLINK_REJECTED'});continue
                if stat.S_ISDIR(s.st_mode):
                    try:child=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
                    except OSError:issues.append({'relative_path':rel,'code':'DIRECTORY_CHANGED_OR_UNSAFE'});continue
                    try:walk(child,parts,depth+1)
                    finally:os.close(child)
                elif stat.S_ISREG(s.st_mode):
                    if Path(name).suffix.lower() not in SUPPORTED:
                        issues.append({'relative_path':rel,'code':'UNSUPPORTED_DOCUMENT_TYPE'});continue
                    if len(found)>=self.max_files:raise CatalogError('SCAN_FILE_LIMIT')
                    try:h,size=self.hash_file(rel)
                    except CatalogError as e:issues.append({'relative_path':rel,'code':e.code});continue
                    total+=size
                    if total>self.max_total_bytes:raise CatalogError('SCAN_TOTAL_SIZE_LIMIT')
                    found[rel]=h
                else:issues.append({'relative_path':rel,'code':'NONREGULAR_OR_HARDLINK_REJECTED'})
        walk(self.fd,[],0)
        return found,issues
