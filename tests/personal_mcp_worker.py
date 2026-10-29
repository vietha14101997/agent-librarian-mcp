"""Synthetic-only Personal Local MCP process. Never accesses Brave or Keychain."""
import argparse,json,sys,time
from dataclasses import replace
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
import anyio
from http_fakes import ReplayHTTP,MemoryStore,session
from agent_librarian.personal.state import PersonalState
from agent_librarian.personal.runtime import prepare
from agent_librarian.gateway.sdk import serve
p=argparse.ArgumentParser();p.add_argument('--state-dir',required=True);p.add_argument('--fixture',required=True);a=p.parse_args()
state=PersonalState(a.state_dir);value=replace(session(),account_id=state.load()['account_id'],expires_at=time.time()+300)
policy,provider=prepare(state,MemoryStore(value),ReplayHTTP(json.loads(Path(a.fixture).read_text())))
anyio.run(serve,policy,None,state.path,provider)
