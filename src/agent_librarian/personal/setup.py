"""Read-only deterministic installation status/plan; never mutates a project."""
from importlib.metadata import version,PackageNotFoundError
import json
from pathlib import Path
import sys
from .state import PersonalState,DEFAULT_STATE
from ..gateway.common import Rejected

def inspect(project,state_dir=DEFAULT_STATE):
    p=Path(project).absolute()
    if not p.is_dir() or p.is_symlink():raise Rejected('PROJECT_PATH_INVALID')
    try:installed=version('agent-librarian-mcp')
    except PackageNotFoundError:installed=None
    skill=p/'.agents/skills/agent-librarian/SKILL.md';mapping=p/'.agent-librarian/project.json'
    mcp=p/'.codex/config.toml'
    auth=False
    state_dir=Path(state_dir)
    if state_dir.exists():auth=PersonalState(state_dir).load()['authenticated']
    return {'status':'CHECKED','runtime_installed':installed is not None,'version':installed,'interpreter':sys.executable,
        'project':str(p),'skill_present':skill.is_file() and not skill.is_symlink(),
        'project_mapping_present':mapping.is_file() and not mapping.is_symlink(),
        'project_mcp_config_present':mcp.is_file() and not mcp.is_symlink(),
        'mcp_configuration_verified':False,'user_authentication_record_present':auth,
        'auth_validity_checked_online':False,'network_operations':0,'project_writes':0}

def plan(project,state_dir=DEFAULT_STATE):
    result=inspect(project,state_dir);p=Path(result['project'])
    return {'status':'PLAN_ONLY','project':str(p),'requires_explicit_owner_authorization':True,
        'proposed_paths':[str(p/'.agents/skills/agent-librarian/SKILL.md'),str(p/'.agent-librarian/project.json')],
        'would_preserve_existing_skill':result['skill_present'],'would_preserve_existing_mapping':result['project_mapping_present'],
        'active_agent_configuration_change':'SEPARATE_REVIEW_REQUIRED','authentication_change':False,'project_writes':0,
        'installer_implementation':'FOLLOW_UP_CONTRACT_PREPARED'}
