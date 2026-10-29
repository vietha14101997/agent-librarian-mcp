"""Local CLI; catalog operations and planning have no provider execution path."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from .catalog.model import CatalogError, strict_json
from .catalog.operations import scan, validate, changes
from .catalog.osagent import adapt_library
from .policy.planner import sync_plan

def read_json(path):
    p=Path(path)
    if p.is_symlink() or not p.is_file() or p.stat().st_size>8*1024*1024:
        raise CatalogError('INPUT_FILE_MISSING_UNSAFE_OR_OVERSIZED')
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as f:
        raw=f.read(8*1024*1024+1)
    if len(raw)>8*1024*1024:raise CatalogError('INPUT_FILE_OVERSIZED')
    return strict_json(raw)

def write_json(path,value,root=None):
    target=Path(path).absolute()
    if target.is_symlink() or any(p.is_symlink() for p in target.parents):raise CatalogError('OUTPUT_SYMLINK_REJECTED')
    if root is not None and target.resolve().is_relative_to(Path(root).resolve()):
        raise CatalogError('OUTPUT_INSIDE_DOCUMENT_ROOT_REJECTED')
    if not target.parent.is_dir():raise CatalogError('OUTPUT_PARENT_MISSING')
    fd,tmp=tempfile.mkstemp(prefix='.librarian-',dir=target.parent)
    try:
        with os.fdopen(fd,'w') as f:
            json.dump(value,f,sort_keys=True,indent=2,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
        os.replace(tmp,target)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def parser():
    p=argparse.ArgumentParser(prog='librarian',description='Local catalogs, dry-run sync planning, and fake-provider MCP. No Google authentication or sync execution.')
    sub=p.add_subparsers(dest='command',required=True)
    for name in ('scan','validate'):
        c=sub.add_parser(name);c.add_argument('--root',required=True,help='Explicitly approved local document root')
        c.add_argument('--manifest',required=name=='validate');c.add_argument('--adapter',choices=('native','osagent'),default='native')
        c.add_argument('--output',help='Optional metadata output outside the document root; otherwise stdout')
        if name=='scan':
            c.add_argument('--max-file-bytes',type=int,default=2*1024*1024);c.add_argument('--max-files',type=int,default=1000)
            c.add_argument('--max-total-bytes',type=int,default=16*1024*1024)
    c=sub.add_parser('changes');c.add_argument('--previous',required=True);c.add_argument('--current',required=True);c.add_argument('--output')
    c=sub.add_parser('sync-plan');c.add_argument('--catalog',required=True);c.add_argument('--policy',required=True);c.add_argument('--output')
    c=sub.add_parser('mcp-serve',help='Official SDK stdio transport, synthetic provider only')
    c.add_argument('--policy');c.add_argument('--fixture');c.add_argument('--control-dir');c.add_argument('--provider',choices=('fake','google'),default='fake')
    return p

def main(argv=None):
    args=parser().parse_args(argv)
    try:
        if args.command=='mcp-serve':
            if args.provider!='fake':raise CatalogError('BLOCKED_PENDING_ISOLATED_RUNTIME')
            import anyio
            from .gateway.sdk import serve
            base=Path(__file__).parent
            policy=args.policy or base/'gateway/default-policy.json'
            fixture=args.fixture or base/'providers/synthetic.json'
            control=args.control_dir or Path(policy).absolute().parent
            try:anyio.run(serve,policy,fixture,control)
            except KeyboardInterrupt:return 0
            except CatalogError:raise
            except Exception:raise CatalogError('MCP_SERVICE_FAILURE') from None
            return 0
        if args.command in ('scan','validate'):
            manifest=read_json(args.manifest) if args.manifest else None
            if args.adapter=='osagent':
                if manifest is None:raise CatalogError('MANIFEST_REQUIRED_FOR_ADAPTER')
                manifest=adapt_library(manifest)
            if args.command=='scan':result=scan(args.root,manifest,max_file_bytes=args.max_file_bytes,max_files=args.max_files,max_total_bytes=args.max_total_bytes)
            else:result=validate(args.root,manifest)
        elif args.command=='changes':result=changes(read_json(args.previous),read_json(args.current))
        else:result=sync_plan(read_json(args.catalog),read_json(args.policy))
        if args.output:write_json(args.output,result,getattr(args,'root',None))
        else:print(json.dumps(result,sort_keys=True,allow_nan=False))
        return 2 if args.command=='validate' and not result['valid'] else 0
    except CatalogError as e:
        print(json.dumps({'status':'ERROR','code':e.code}),file=sys.stderr);return 2
    except (OSError,ValueError,TypeError,KeyError):
        print(json.dumps({'status':'ERROR','code':'INPUT_OR_FILESYSTEM_INVALID'}),file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())
