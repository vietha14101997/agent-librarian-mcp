"""CLI orchestration; never exposes authentication through MCP."""
import asyncio
from pathlib import Path
from .state import PersonalState,DEFAULT_STATE
from .storage import PersonalKeychainStore
from .browser_auth import login
from .runtime import status,logout,direct_call
from ..gateway.common import NAMES,Rejected

def dispatch(args):
    path=args.state_dir or DEFAULT_STATE
    login_action=args.command=='auth' and args.auth_action=='login'
    existing=None
    if login_action and Path(path).exists():existing=PersonalState(path)
    cached=existing is not None and existing.load()['authenticated']
    if login_action and not cached:
        method=getattr(args,'method',None)
        if method is None:raise Rejected('AUTHENTICATION_METHOD_SELECTION_REQUIRED')
        if method=='existing-brave' and not getattr(args,'consent_existing_session',False):raise Rejected('EXISTING_BRAVE_ACCESS_APPROVAL_REQUIRED')
        if method=='existing-brave' and not getattr(args,'brave_profile',None):raise Rejected('BRAVE_PROFILE_SELECTION_REQUIRED')
        if not args.consent_discovery:raise Rejected('LOGIN_AND_DISCOVERY_CONSENT_REQUIRED')
    state=existing or PersonalState(path,create=login_action)
    if args.command=='browser':
        from .brave_transport import connect,browser_status
        return connect(state,args.consent_discovery,active_tab=args.active_tab) if args.browser_action=='connect' else browser_status(state)
    if args.command=='auth':
        from .brave_transport import CONNECTION,browser_status
        if args.auth_action in ('status','login') and (state.path/CONNECTION).exists():
            return browser_status(state) # Never fall back to cookie replay or managed login.
        if args.auth_action=='status' and not state.load()['authenticated']:
            return status(state,None,args.show_account)
        store=PersonalKeychainStore(state)
        if args.auth_action=='login':
            from .progress import notify_outcome
            try:
                if getattr(args,'method',None)=='existing-brave' and not cached:
                    from .existing_brave import connect
                    result=connect(state,store,args.brave_profile,args.consent_existing_session and args.consent_discovery)
                else:result=asyncio.run(login(state,store,args.consent_discovery or cached,args.timeout))
            except KeyboardInterrupt:
                from .progress import LoginProgress
                LoginProgress(state).event('stopped_by_owner')
                return {'status':'STOPPED_BY_OWNER','normal_brave_not_targeted':True}
            except Rejected as error:
                if getattr(args,'notify',False):notify_outcome(False,error.code)
                raise
            if getattr(args,'notify',False):notify_outcome(True)
            return result
        if args.auth_action=='status':return status(state,store,args.show_account)
        return logout(state,store)
    if args.command=='notebooks':
        if args.notebook_action=='select':return state.select(args.notebook_id)
        return {'status':'OK','origin':'CACHED_OWNER_APPROVED_DISCOVERY',
            'notebooks':[{'notebook_id':b['notebook_id'],'title':b['title']} for b in state.inventory()['notebooks']]}
    if getattr(args,'project',None):
        from ..projects import ProjectMappings,DEFAULT_HOME
        from ..project_runtime import ProjectGateway
        home=getattr(args,'installation_home',None) or DEFAULT_HOME
        mapping=ProjectMappings(home).resolve(args.project)
        if mapping['status']!='MAPPED':raise Rejected('PROJECT_NOT_MAPPED')
        nb=args.notebook_id
        if nb is None and len(mapping['notebook_ids'])==1:nb=mapping['notebook_ids'][0]
        if nb not in mapping['notebook_ids']:raise Rejected('MAPPED_NOTEBOOK_SELECTION_REQUIRED')
        if args.research_action=='approve':return state.approve_query(args.question,args.ack_history,nb)
        arguments={'notebook_id':nb}
        if args.research_action=='query':arguments['query']=args.question;name=NAMES[2]
        elif args.research_action=='source':arguments['source_id']=args.source_id;name=NAMES[3]
        else:name=NAMES[1]
        return ProjectGateway(args.project,home,path).call(name,arguments)
    if getattr(args,'notebook_id',None):raise Rejected('PROJECT_REQUIRED_WITH_NOTEBOOK_ID')
    if args.research_action=='approve':return state.approve_query(args.question,args.ack_history)
    book=state.load()['selected_notebook']
    if not book:raise Rejected('NOTEBOOK_SELECTION_REQUIRED')
    arguments={'notebook_id':book['notebook_id']}
    if args.research_action=='query':arguments['query']=args.question;name=NAMES[2]
    elif args.research_action=='source':arguments['source_id']=args.source_id;name=NAMES[3]
    else:name=NAMES[1]
    return direct_call(state,name,arguments)
