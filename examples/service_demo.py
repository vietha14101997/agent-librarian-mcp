"""Synthetic service -> Unix IPC -> gateway -> official SDK client; no Google calls."""
import argparse
import anyio
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time
from mcp import Client,StdioServerParameters
from agent_librarian.providers.ipc import socket_path

async def exercise(state):
    root=Path(__file__).resolve().parents[1]
    state=Path(state).resolve();state.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='d',dir=state) as temporary:
        work=Path(temporary);sock=socket_path(work/'s')
        config=json.loads((root/'examples/research-policy.json').read_text());config['enabled']=True
        policy=work/'service.json';policy.write_text(json.dumps(config))
        front=work/'front.json';front.write_text(json.dumps(config))
        canary=work/'canary.json'
        fd=os.open(canary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as handle:
            json.dump({'synthetic_only':True,'account_id':config['account_id'],
                'secret':'SYNTHETIC_'+secrets.token_hex(16)},handle)
        command=[sys.executable,'-I','-B','-m','agent_librarian','provider-service','--socket',str(sock),
            '--service-policy',str(policy),'--fixture',str(root/'tests/fixtures/research.json'),
            '--canary-store',str(canary),'--allowed-uid',str(os.geteuid()),'--adapter','gemini-mock']
        # Service output is deliberately not forwarded; no credential dump facility exists.
        process=subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            deadline=time.monotonic()+5
            while not sock.exists():
                if process.poll() is not None or time.monotonic()>deadline:
                    raise RuntimeError('SYNTHETIC_SERVICE_STARTUP_FAILED')
                await anyio.sleep(.01)
            params=StdioServerParameters(command=sys.executable,args=['-I','-B','-m','agent_librarian','mcp-serve',
                '--provider','service','--policy',str(front),'--service-socket',str(sock),
                '--service-uid',str(os.geteuid()),'--control-dir',str(work)],
                env={'LANG':'C','PYTHONIOENCODING':'utf-8'})
            outputs={'google_operations':0,'host_isolation':'HOST_ISOLATION_PENDING_OWNER_SETUP',
                'transport':'official MCP SDK stdio -> real Unix socket -> synthetic service -> Gemini mock'}
            async with Client(params) as client:
                outputs['tools']=[tool.name for tool in (await client.list_tools()).tools]
                for name,args in [
                    ('librarian_list_notebooks',{}),
                    ('librarian_get_notebook',{'notebook_id':'notebook-approved'}),
                    ('librarian_get_source',{'notebook_id':'notebook-approved','source_id':'source-approved'}),
                    ('librarian_query',{'notebook_id':'notebook-approved','query':'What synthetic decision?'}),
                    ('source_add',{'file_path':'/SYNTHETIC/forbidden'})]:
                    outputs[name]=(await client.call_tool(name,args)).structured_content
            if any(outputs[name]['status']!='OK' for name in outputs['tools']):
                raise RuntimeError('SYNTHETIC_DEMO_OPERATION_FAILED')
            if outputs['source_add'].get('code')!='FORBIDDEN_OPERATION':
                raise RuntimeError('SYNTHETIC_DEMO_DISPATCH_FAILED')
            print(json.dumps(outputs,indent=2))
        finally:
            if process.poll() is None:process.terminate()
            try:process.wait(timeout=3)
            except subprocess.TimeoutExpired:process.kill();process.wait()

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--state-dir',required=True)
    args=parser.parse_args();anyio.run(exercise,args.state_dir)
