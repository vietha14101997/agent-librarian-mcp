"""Offline planning and explicit CLI dispatch; no login, mapping or query side effects."""
from pathlib import Path
from ..gateway.common import Rejected
from ..projects import DEFAULT_HOME
from ..cli import read_json,write_json
from .state import PersonalState,DEFAULT_STATE
from .ingestion import plan,Importer


def dispatch(args):
    action=args.source_action
    if action in ('plan','add'):
        if not args.path or args.plan:raise Rejected('IMPORT_PATH_REQUIRED')
        data=plan(args.path,args.project,args.notebook_id,args.relative_names,args.json_as_markdown)
        if action=='add' and not Path(args.path).is_file():raise Rejected('IMPORT_SINGLE_FILE_REQUIRED')
        if args.output:
            if action!='plan':raise Rejected('IMPORT_PLAN_OUTPUT_ONLY')
            root=Path(args.path).absolute()
            write_json(args.output,data,root=root if root.is_dir() else root.parent)
        if action=='plan' or not args.approve:
            return {'status':'ERROR' if data['errors'] else 'PREVIEW','code':'IMPORT_PLAN_ERRORS' if data['errors'] else None,'plan':data,'network_operations':0}
    else:
        if not args.plan or args.path or args.output:raise Rejected('IMPORT_PLAN_REQUIRED')
        data=read_json(args.plan)
        if data.get('project')!=str(Path(args.project).resolve()) or data.get('notebook_id')!=args.notebook_id:raise Rejected('IMPORT_PLAN_TARGET_MISMATCH')
    state=PersonalState(args.state_dir or DEFAULT_STATE)
    importer=Importer(args.home or DEFAULT_HOME,state,args.project,args.notebook_id)
    if action=='status':return importer.status()
    if action=='check':return importer.check()
    return importer.run(data,approve=args.approve)
