"""Full synthetic SDK-client workflow; writes only the explicit local state directory."""
import argparse
import anyio
import json
from pathlib import Path
import sys
from mcp import Client, StdioServerParameters

async def demo(state):
    root=Path(__file__).resolve().parents[1]
    state=Path(state).resolve();state.mkdir(parents=True,exist_ok=True)
    policy=json.loads((root/'examples/research-policy.json').read_text());policy['enabled']=True
    target=state/'research-policy.json';target.write_text(json.dumps(policy,indent=2)+'\n')
    params=StdioServerParameters(command=sys.executable,args=['-I','-B','-m','agent_librarian','mcp-serve',
        '--policy',str(target),'--fixture',str(root/'tests/fixtures/research.json'),'--control-dir',str(state)],
        env={'LANG':'C','PYTHONIOENCODING':'utf-8'})
    async with Client(params) as client:
        listing=await client.list_tools()
        outputs={'transport':'actual MCP SDK stdio subprocess','protocol_version':client.protocol_version,
            'tools':[t.name for t in listing.tools],'google_operations':0}
        for name,args in [
            ('librarian_list_notebooks',{}),
            ('librarian_get_notebook',{'notebook_id':'notebook-approved'}),
            ('librarian_get_source',{'notebook_id':'notebook-approved','source_id':'source-approved'}),
            ('librarian_query',{'notebook_id':'notebook-approved','query':'What synthetic queue decision was made?'}),
            ('notebook_delete',{'confirm':True}),
        ]:
            result=await client.call_tool(name,args)
            outputs[name]=result.structured_content
    print(json.dumps(outputs,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--state-dir',required=True)
    args=parser.parse_args();anyio.run(demo,args.state_dir)
