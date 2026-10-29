"""Test-only service process injecting synthetic HTTP fixtures; no real network."""
import argparse,json,os,signal,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from http_fakes import ReplayHTTP,MemoryStore
from agent_librarian.providers.session import SessionManager
from agent_librarian.providers.https_transport import GeminiHTTPS
from agent_librarian.providers.gemini import GeminiResearchProvider,AccountCapability
from agent_librarian.providers.service import ProviderService,SecretConfinement
p=argparse.ArgumentParser();p.add_argument('--policy');p.add_argument('--fixture');p.add_argument('--socket');a=p.parse_args()
policy=json.loads(Path(a.policy).read_text());fixture=json.loads(Path(a.fixture).read_text())
sessions=SessionManager(MemoryStore(),policy['account_id'],'research@example.invalid','notebooklm.google.com')
transport=GeminiHTTPS(sessions,policy['notebooks'],sender=ReplayHTTP(fixture))
backend=GeminiResearchProvider(transport,AccountCapability(policy['account_id']),policy['notebooks'])
service=ProviderService(a.socket,a.policy,a.fixture,None,os.geteuid(),'research-client',provider=SecretConfinement(backend,sessions.secrets))
signal.signal(signal.SIGTERM,lambda _s,_f:(_ for _ in ()).throw(SystemExit(0)))
try:service.run()
finally:service.close()
