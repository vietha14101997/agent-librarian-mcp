"""Local CLI; catalog operations and planning have no provider execution path."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from .catalog.model import CatalogError, strict_json, migrate_catalog
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
    p=argparse.ArgumentParser(prog='librarian',description='Local catalogs, dry-run sync planning, and restricted research MCP. Explicit Personal Local login; no sync execution.')
    sub=p.add_subparsers(dest='command',required=True)
    for name in ('scan','validate'):
        c=sub.add_parser(name);c.add_argument('--root',required=True,help='Explicitly approved local document root')
        c.add_argument('--manifest',required=name=='validate');c.add_argument('--adapter',choices=('native','osagent'),default='native')
        c.add_argument('--output',help='Optional metadata output outside the document root; otherwise stdout')
        if name=='scan':
            c.add_argument('--max-file-bytes',type=int,default=2*1024*1024);c.add_argument('--max-files',type=int,default=1000)
            c.add_argument('--max-total-bytes',type=int,default=16*1024*1024)
    c=sub.add_parser('changes');c.add_argument('--previous',required=True);c.add_argument('--current',required=True);c.add_argument('--output')
    c=sub.add_parser('sync-plan');c.add_argument('--catalog',required=True);c.add_argument('--policy',required=True);c.add_argument('--output');c.add_argument('--policy-sha256')
    c=sub.add_parser('migrate');c.add_argument('--input',required=True);c.add_argument('--output',required=True)
    c=sub.add_parser('mcp-serve',help='Four-tool MCP stdio server; project mappings or explicit provider configuration')
    c.add_argument('--policy');c.add_argument('--fixture');c.add_argument('--control-dir');c.add_argument('--provider',choices=('fake','service','personal','project','google'),default='fake')
    # Service connection parameters are local startup configuration, never MCP arguments.
    c.add_argument('--state-dir');c.add_argument('--project',default='.');c.add_argument('--installation-home');c.add_argument('--service-socket');c.add_argument('--service-uid',type=int);c.add_argument('--client-id',default='research-client')
    c=sub.add_parser('setup',help='Install once, map projects and manage the shared Skill/MCP runtime')
    c.add_argument('setup_action',choices=('install','status','doctor','plan','contract','onboard','map','unmap','repair','update','uninstall'))
    c.add_argument('--project',default='.');c.add_argument('--state-dir')
    c.add_argument('--home',help='User-local installation receipt and mappings directory')
    c.add_argument('--codex-home',help='Codex configuration directory')
    c.add_argument('--skills-home',help='User Agent Skills directory')
    c.add_argument('--notebook-id',action='append',help='Repeat for multiple notebooks; map replaces the project allowlist')
    c.add_argument('--wheel',help='Provision a shared runtime from this local wheel, using uv')
    c.add_argument('--runtime-python',help='Reuse an existing persistent compatible runtime')
    c.add_argument('--dry-run',action='store_true',help='Preview without writing any files')
    c.add_argument('--adopt-existing',action='store_true',help='Back up and migrate the existing Agent Librarian entry/Skill only')
    c.add_argument('--choice',choices=('existing','new','skip','recover'),help='Explicit onboarding choice; omitted returns a question for the agent')
    c.add_argument('--approve',action='store_true',help='Records the owner explicit approval of this selection or creation')
    c.add_argument('--discover',action='store_true',help='Owner consent to refresh current-account notebook inventory')
    c.add_argument('--title',help='Owner-confirmed new notebook title')
    c.add_argument('--account-id',help='Confirm the account binding returned by onboarding')
    c.add_argument('--account-email',help='Confirm the Google account shown in the creation proposal')
    c.add_argument('--operation-id',help='Use the ID returned in the creation proposal')
    c.add_argument('--experimental-browser-create',action='store_true',help='Explicitly opt into live-unverified creation; default is manual creation')
    c=sub.add_parser('sources',help='CLI-only file imports; never exposed through research MCP')
    c.add_argument('source_action',choices=('plan','add','import','status','check'))
    c.add_argument('--project',required=True);c.add_argument('--notebook-id',required=True)
    c.add_argument('--home');c.add_argument('--state-dir');c.add_argument('--path');c.add_argument('--plan')
    c.add_argument('--output',help='Write an offline plan outside its source root')
    c.add_argument('--relative-names',action='store_true',help='Encode relative paths with __ to avoid basename collisions')
    c.add_argument('--json-as-markdown',action='store_true',help='Wrap unchanged JSON bytes in a Markdown code fence')
    c.add_argument('--approve',action='store_true',help='Approve mutation for this exact reviewed file/plan; default is preview')
    c=sub.add_parser('auth',help='Explicit Personal Local Brave login and Keychain session')
    auth=c.add_subparsers(dest='auth_action',required=True)
    for action in ('login','status','logout'):
        a=auth.add_parser(action);a.add_argument('--state-dir');a.add_argument('--show-account',action='store_true')
        if action=='login':a.add_argument('--method',choices=('existing-brave','managed-brave'));a.add_argument('--brave-profile');a.add_argument('--consent-existing-session',action='store_true');a.add_argument('--consent-discovery',action='store_true');a.add_argument('--timeout',type=int,default=600);a.add_argument('--notify',action=argparse.BooleanOptionalAction,default=True)
    c=sub.add_parser('notebooks',help='Cached discovered inventory and explicit notebook selection')
    books=c.add_subparsers(dest='notebook_action',required=True)
    for action in ('list','select'):
        a=books.add_parser(action);a.add_argument('--state-dir')
        if action=='select':a.add_argument('--notebook-id',required=True)
    c=sub.add_parser('browser',help='Opt-in native Brave connection; no debugger or cookie export')
    browser=c.add_subparsers(dest='browser_action',required=True)
    for action in ('connect','status'):
        a=browser.add_parser(action);a.add_argument('--state-dir')
        if action=='connect':
            a.add_argument('--consent-discovery',action='store_true');a.add_argument('--active-tab',action='store_true',help='Explicitly replace a previous pinned Notebook tab')
    c=sub.add_parser('research',help='Four restricted Personal Local operations')
    research=c.add_subparsers(dest='research_action',required=True)
    for action in ('approve','query','notebook','source'):
        a=research.add_parser(action);a.add_argument('--state-dir');a.add_argument('--project');a.add_argument('--installation-home');a.add_argument('--notebook-id')
        if action in ('approve','query'):a.add_argument('--question',required=True)
        if action=='approve':a.add_argument('--ack-history',action='store_true')
        if action=='source':
            a.add_argument('--source-id',required=True);a.add_argument('--offset',type=int,default=0);a.add_argument('--max-chars',type=int,default=16000)
    for command in ('provider-runtime','provider-status'):
        c=sub.add_parser(command,help='Protected deployment runtime; no caller credential inputs');c.add_argument('--config',required=True)
    c=sub.add_parser('provider-service',help='Restricted Unix service, synthetic credentials and mocked provider only')
    c.add_argument('--socket',required=True);c.add_argument('--service-policy',required=True);c.add_argument('--fixture',required=True)
    c.add_argument('--canary-store',required=True);c.add_argument('--allowed-uid',required=True,type=int);c.add_argument('--client-id',default='research-client')
    c.add_argument('--adapter',choices=('fake','gemini-mock'),default='gemini-mock')
    return p

def main(argv=None):
    args=parser().parse_args(argv)
    try:
        if args.command=='setup':
            from .installation import Installation
            from .projects import DEFAULT_HOME,ProjectMappings
            from .gateway.common import Rejected
            try:
                home=args.home or DEFAULT_HOME
                if args.setup_action in ('contract','onboard'):
                    from .onboarding import Onboarding, registration_contract
                    from .personal.state import DEFAULT_STATE
                    state_dir=args.state_dir or DEFAULT_STATE
                    if args.setup_action=='contract':
                        result=registration_contract(args.project,home,state_dir)
                    else:
                        if args.notebook_id and len(args.notebook_id)!=1:
                            raise Rejected('EXPLICIT_SINGLE_NOTEBOOK_SELECTION_REQUIRED')
                        result=Onboarding(args.project,home,state_dir).run(choice=args.choice,
                            notebook_id=args.notebook_id[0] if args.notebook_id else None,
                            approve=args.approve,discover=args.discover,title=args.title,
                            account_id=args.account_id,account_email=args.account_email,operation_id=args.operation_id,
                            experimental_browser_create=args.experimental_browser_create,dry_run=args.dry_run)
                elif args.setup_action in ('map','unmap'):
                    if args.setup_action=='map' and not args.notebook_id:
                        raise Rejected('NOTEBOOK_ID_REQUIRED: use notebooks list, then map --notebook-id ID')
                    result=ProjectMappings(home).change(args.project,args.notebook_id if args.setup_action=='map' else None,args.dry_run)
                else:
                    install=Installation(home,args.codex_home,args.skills_home,args.state_dir)
                    if args.setup_action in ('install','repair','update','plan'):
                        if args.setup_action=='update' and not (args.wheel or args.runtime_python):
                            raise Rejected('UPDATE_TARGET_REQUIRED: provide --wheel PATH or --runtime-python PATH')
                        result=install.install(wheel=args.wheel,runtime_python=args.runtime_python,
                            dry_run=args.dry_run or args.setup_action=='plan',repair=args.setup_action in ('repair','update'),
                            adopt_existing=args.adopt_existing)
                    elif args.setup_action=='uninstall':result=install.uninstall(args.dry_run)
                    else:
                        result=install.status(args.project)
                        # Legacy local status fields remain available to existing clients.
                        from .personal.setup import inspect
                        try:
                            legacy=inspect(args.project,args.state_dir or install.state_dir)
                            for key,value in legacy.items():result.setdefault(key,value)
                        except (Rejected,OSError) as error:
                            result['legacy_status_error']=getattr(error,'code','PERSONAL_CONFIGURATION_UNAVAILABLE')
                        result['skill_present']=any(c['check']=='SKILL.md' and c['ok'] for c in result['checks']) or result.get('skill_present',False)
                        result['project_mapping_present']=result['mapping']['status']=='MAPPED'
                        result['mcp_configuration_verified']=any(c['check']=='mcp_registration' and c['ok'] for c in result['checks'])
            except Rejected as e:raise CatalogError(e.code) from None
            print(json.dumps(result));return 2 if args.setup_action=='doctor' and result['status']=='NEEDS_ATTENTION' else 0
        if args.command=='sources':
            from .personal.ingestion_cli import dispatch as ingest
            from .gateway.common import Rejected
            try:result=ingest(args)
            except (Rejected,OSError,ValueError,KeyError,TypeError) as e:
                print(json.dumps({'status':'ERROR','code':e.code if isinstance(e,Rejected) else 'IMPORT_INPUT_INVALID'}),file=sys.stderr);return 2
            print(json.dumps(result,ensure_ascii=False,allow_nan=False));return 2 if result.get('status')=='ERROR' else 0
        if args.command in ('auth','notebooks','research','browser'):
            from .personal.commands import dispatch
            from .gateway.common import Rejected
            try:result=dispatch(args)
            except Rejected as e:
                error={'status':'ERROR','code':e.code}
                if type(getattr(e,'os_status',None)) is int:error['keychain_os_status']=e.os_status
                if hasattr(e,'diagnostics'):error['diagnostics']=e.diagnostics
                print(json.dumps(error),file=sys.stderr);return 2
            print(json.dumps(result,ensure_ascii=False,allow_nan=False));return 0 if result.get('status')!='ERROR' else 2
        if args.command in ('provider-runtime','provider-status'):
            from .providers.runtime import run_runtime,runtime_status
            from .gateway.common import Rejected
            try:
                if args.command=='provider-runtime':run_runtime(args.config)
                else:print(json.dumps(runtime_status(args.config)))
            except Rejected as e:raise CatalogError(e.code) from None
            return 0
        if args.command=='provider-service':
            from .providers.service import run_service
            from .gateway.common import Rejected
            try:run_service(path=args.socket,policy=args.service_policy,fixture=args.fixture,canary_store=args.canary_store,
                allowed_uid=args.allowed_uid,client_id=args.client_id,adapter=args.adapter)
            except Rejected as e:raise CatalogError(e.code) from None
            return 0
        if args.command=='mcp-serve':
            if args.provider=='google':raise CatalogError('BLOCKED_PENDING_ISOLATED_RUNTIME')
            import anyio
            from .gateway.sdk import serve
            base=Path(__file__).parent
            policy=args.policy or base/'gateway/default-policy.json'
            fixture=args.fixture or base/'providers/synthetic.json'
            control=args.control_dir or Path(policy).absolute().parent
            provider=None
            if args.provider=='project':
                if any((args.policy,args.fixture,args.service_socket,args.service_uid is not None,args.control_dir)):
                    raise CatalogError('PROJECT_STARTUP_CONFIGURATION_INVALID')
                from .project_runtime import ProjectGateway
                from .projects import DEFAULT_HOME,project_path
                from .personal.state import DEFAULT_STATE
                gateway=ProjectGateway(project_path(args.project),args.installation_home or DEFAULT_HOME,args.state_dir or DEFAULT_STATE)
                try:anyio.run(serve,None,None,None,None,gateway)
                except KeyboardInterrupt:return 0
                return 0
            if args.provider=='personal':
                if any((args.policy,args.fixture,args.service_socket,args.service_uid is not None,args.control_dir)):raise CatalogError('PERSONAL_STARTUP_CONFIGURATION_INVALID')
                from .personal.state import PersonalState,DEFAULT_STATE
                from .personal.runtime import prepare
                from .gateway.common import Rejected
                try:
                    state=PersonalState(args.state_dir or DEFAULT_STATE);policy,provider=prepare(state);control=state.path
                except Rejected as e:raise CatalogError(e.code) from None
            if args.provider=='service':
                if not args.service_socket or args.service_uid is None or args.fixture:raise CatalogError('IPC_STARTUP_CONFIGURATION_INVALID')
                from .gateway.common import load_policy
                from .providers.ipc import IPCResearchProvider
                config=load_policy(policy)
                provider=IPCResearchProvider(args.service_socket,args.service_uid,args.client_id,config['account_id'],config['timeout_seconds']+1)
            try:anyio.run(serve,policy,fixture,control,provider)
            except KeyboardInterrupt:return 0
            except CatalogError:raise
            except Exception:raise CatalogError('MCP_SERVICE_FAILURE') from None
            return 0
        if args.command=='migrate':
            if Path(args.input).resolve()==Path(args.output).resolve():raise CatalogError('MIGRATION_INPUT_OVERWRITE_REJECTED')
            result=migrate_catalog(read_json(args.input))
        elif args.command in ('scan','validate'):
            manifest=read_json(args.manifest) if args.manifest else None
            if args.adapter=='osagent':
                if manifest is None:raise CatalogError('MANIFEST_REQUIRED_FOR_ADAPTER')
                manifest=adapt_library(manifest)
            if args.command=='scan':result=scan(args.root,manifest,max_file_bytes=args.max_file_bytes,max_files=args.max_files,max_total_bytes=args.max_total_bytes)
            else:result=validate(args.root,manifest)
        elif args.command=='changes':result=changes(read_json(args.previous),read_json(args.current))
        else:result=sync_plan(read_json(args.catalog),read_json(args.policy),args.policy_sha256)
        if args.output:write_json(args.output,result,getattr(args,'root',None))
        else:print(json.dumps(result,sort_keys=True,allow_nan=False))
        return 2 if args.command=='validate' and not result['valid'] else 0
    except CatalogError as e:
        print(json.dumps({'status':'ERROR','code':e.code}),file=sys.stderr);return 2
    except (OSError,ValueError,TypeError,KeyError):
        print(json.dumps({'status':'ERROR','code':'INPUT_OR_FILESYSTEM_INVALID'}),file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())
