"""Closed native creation contract; synthetic Apple Events and JS context only."""
import json
from pathlib import Path
import subprocess
import shutil
import unittest
from agent_librarian.gateway.common import Rejected
from agent_librarian.personal.notebook_admin import NotebookAdmin, CREATE_RPC, create_params
from agent_librarian.personal.brave_transport import BraveTransport
from agent_librarian.providers.gemini import LIST_RPC, ReadRequest
from tests.test_brave_transport import PAGE, FakePage

ROOT = Path(__file__).resolve().parents[1]


class CreationPage(FakePage):
    def __call__(self, source):
        if 'return String(t.execute({javascript:' not in source:
            return super().__call__(source)
        raw = source.split('return String(t.execute({javascript:', 1)[1].split('}));', 1)[0]
        javascript = json.loads(raw)
        payload = json.loads(javascript.rsplit('})(', 1)[1].strip()[:-1])
        if payload['action'] == 'start' and payload['request']['method'] == CREATE_RPC:
            self.requests.append(ReadRequest(**payload['request']))
            self.body = ")]}'\n1\n"+json.dumps([['wrb.fr', CREATE_RPC, json.dumps(['Confirmed title', None, 'actual-created-id'])]])+'\n'
            return {'status': 'DISPATCHED'}
        return super().__call__(source)


class NotebookAdminTests(unittest.TestCase):
    def test_creation_envelope_and_returned_id_use_existing_bounded_bridge(self):
        page = CreationPage()
        admin = NotebookAdmin(PAGE, 'synthetic-account', 'owner@example.invalid', {}, runner=page)
        self.assertEqual(admin.create('Confirmed title'), 'actual-created-id')
        self.assertEqual(page.requests, [ReadRequest('rpc', CREATE_RPC, '/', create_params('Confirmed title'))])

    def test_research_transport_rejects_creation_before_browser_access(self):
        page = CreationPage()
        transport = BraveTransport(PAGE, 'synthetic-account', 'owner@example.invalid', {}, runner=page)
        with self.assertRaises(Rejected):
            transport.request(ReadRequest('rpc', CREATE_RPC, '/', create_params('Confirmed title')))
        self.assertFalse(page.requests)

    def test_admin_request_cannot_accept_arbitrary_rpc_or_research(self):
        page = CreationPage()
        admin = NotebookAdmin(PAGE, 'synthetic-account', 'owner@example.invalid', {}, runner=page)
        for request in (ReadRequest('rpc', 'WWINqb', '/', []), ReadRequest('rpc', 'rLM1Ne', '/', []),
                        ReadRequest('rpc', LIST_RPC, '/', ['wrong'])):
            with self.assertRaises(Rejected):
                admin.request(request)
        self.assertFalse(page.requests)

    def test_ambiguous_creation_result_rejected(self):
        page = CreationPage()
        admin = NotebookAdmin(PAGE, 'synthetic-account', 'owner@example.invalid', {}, runner=page)
        for value in (None, [], [['Confirmed title', None, 'id']], ['Different title', None, 'id'],
                      ['Confirmed title', None, '../bad']):
            admin._request = lambda _, value=value: value
            with self.assertRaises(Rejected):
                admin.create('Confirmed title')

    @unittest.skipUnless(shutil.which('node'), 'Node.js is needed only for synthetic browser JavaScript validation')
    def test_javascript_contract_and_account_attestation_with_synthetic_page(self):
        # Run the actual distributed JS in node VM with a fake page and fetch.
        # No network APIs from the execution environment enter that VM.
        script = r'''
const fs=require('fs'),vm=require('vm');
const source=fs.readFileSync(process.argv[1],'utf8');
let calls=[];
const context={location:{origin:'https://notebook.google.com',pathname:'/'},
 document:{scripts:[{textContent:'WIZ_global_data = {"oPEP7c":"owner@example.invalid","SNlM0e":"synthetic-token","FdrFJe":"123","cfb2h":"synthetic-build"}'}]},
 URL,URLSearchParams,AbortController,TextDecoder,Uint8Array,setTimeout,clearTimeout,
 fetch:async (url,options)=>{calls.push({url,body:options.body});return {status:401,headers:{get:()=>''}}}};
vm.createContext(context);
function run(request,email='owner@example.invalid'){
 return JSON.parse(vm.runInContext(source.replace('__LIBRARIAN_INPUT__',JSON.stringify({action:'start',id:String(Math.random()),
 expected_email:email,request,timeout_ms:1000})),context));
}
const create={kind:'rpc',method:'CCqFvf',path:'/',params:['Confirmed title',null,null,[2],[1,null,null,null,null,null,null,null,null,null,[1]]]};
const result=[run({...create,method:'WWINqb'}),run({...create,params:['title']}),run(create,'other@example.invalid'),run(create)];
process.stdout.write(JSON.stringify({result,calls}));
'''
        result = subprocess.run(['node', '-e', script, str(ROOT/'src/agent_librarian/personal/brave_create.js')],
                                capture_output=True, text=True, timeout=5, check=True)
        value = json.loads(result.stdout)
        self.assertEqual([x.get('code', x['status']) for x in value['result']],
                         ['FORBIDDEN_OPERATION', 'FORBIDDEN_OPERATION', 'ACCOUNT_IDENTITY_MISMATCH', 'DISPATCHED'])
        self.assertEqual(len(value['calls']), 1)
        from urllib.parse import parse_qs
        envelope = json.loads(parse_qs(value['calls'][0]['body'])['f.req'][0])
        self.assertEqual(json.loads(envelope[0][0][1]), create_params('Confirmed title'))
