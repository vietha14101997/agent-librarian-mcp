"""Actual service/client/process boundaries, using synthetic canaries only."""
import anyio
from contextlib import redirect_stderr
import copy
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import uuid
from mcp import Client,StdioServerParameters
from agent_librarian.gateway.common import Rejected,NAMES
from agent_librarian.gateway.policy import Gateway
from agent_librarian.providers.ipc import IPCResearchProvider,read_frame,send_frame

ROOT=Path(__file__).resolve().parents[1]
IPC_ROOT=Path(os.environ.get('AGENT_LIBRARIAN_IPC_DIR',ROOT/'state'));IPC_ROOT.mkdir(parents=True,exist_ok=True)

class IPCTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='i',dir=IPC_ROOT);self.dir=Path(self.temp.name).resolve()
        self.sock=self.dir/'s';self.policy_path=self.dir/'policy.json';self.fixture_path=self.dir/'fixture.json';self.store=self.dir/'canary.json'
        self.policy=json.loads((ROOT/'examples/research-policy.json').read_text());self.policy['enabled']=True
        self.fixture=json.loads((ROOT/'tests/fixtures/research.json').read_text());self.process=None;self.stderr=''
        self.secret='SYNTHETIC_CANARY_12345'
        fd=os.open(self.store,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as f:json.dump({'synthetic_only':True,'account_id':self.policy['account_id'],'secret':self.secret},f)
        self.start()
    def start(self,allowed_uid=None):
        self.policy_path.write_text(json.dumps(self.policy));self.fixture_path.write_text(json.dumps(self.fixture))
        cmd=[sys.executable,'-I','-B','-m','agent_librarian','provider-service','--socket',str(self.sock),
            '--service-policy',str(self.policy_path),'--fixture',str(self.fixture_path),'--canary-store',str(self.store),
            '--allowed-uid',str(os.geteuid() if allowed_uid is None else allowed_uid),'--client-id','research-client','--adapter','gemini-mock']
        self.process=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env={'LANG':'C','PYTHONIOENCODING':'utf-8'})
        deadline=time.monotonic()+4
        while not self.sock.exists():
            if self.process.poll() is not None:
                _,err=self.process.communicate();raise AssertionError('Synthetic service startup failed: '+err.decode())
            if time.monotonic()>deadline:raise AssertionError('Service readiness timeout')
            time.sleep(.01)
    def stop(self):
        if self.process:
            if self.process.poll() is None:self.process.terminate()
            try:_,err=self.process.communicate(timeout=3)
            except subprocess.TimeoutExpired:self.process.kill();_,err=self.process.communicate()
            self.stderr=err.decode();self.process=None
    def tearDown(self):self.stop();self.temp.cleanup()
    def restart(self,**kw):self.stop();self.start(**kw)
    def client(self,**kw):
        args=dict(path=self.sock,service_uid=os.geteuid(),client_id='research-client',account_id=self.policy['account_id'],timeout=2)
        args.update(kw);return IPCResearchProvider(**args)
    def envelope(self,op=NAMES[2],args=None,**extra):
        value={'version':1,'request_id':uuid.uuid4().hex,'client_id':'research-client','operation':op,
            'arguments':{'notebook_id':'notebook-approved','query':'Synthetic question','source_ids':['source-approved']} if args is None else args}
        value.update(extra);return value
    def raw(self,request):
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:
            s.settimeout(2);s.connect(str(self.sock));send_frame(s,request);return read_frame(s,131072)
    def query(self,client):return client.query('notebook-approved','Synthetic question',['source-approved'])
    def test_source_pages_through_both_service_and_client_gateways(self):
        content='Synthetic source passage. '*1500
        self.fixture['notebooks']['notebook-approved']['sources']['source-approved']['content']=content;self.restart()
        front=Gateway(self.policy_path,self.fixture_path,self.dir,provider=self.client());pieces=[];offset=0
        try:
            while True:
                result=front.call(NAMES[3],{'notebook_id':'notebook-approved','source_id':'source-approved','offset':offset})
                self.assertEqual(result['status'],'OK',result);pieces.append(result['content'])
                if result['next_offset'] is None:break
                offset=result['next_offset']
            self.assertEqual(''.join(pieces),content)
        finally:front.close()

    def test_01_gateway_never_receives_canary(self):
        self.fixture['answer']='Synthetic response contains {{SERVICE_CANARY}}.';self.restart()
        front=Gateway(self.policy_path,self.fixture_path,self.dir,provider=self.client())
        with patch('builtins.open',side_effect=AssertionError('Agent must not open a credential store')),redirect_stderr(io.StringIO()) as log:
            result=front.call(NAMES[2],{'notebook_id':'notebook-approved','query':'Synthetic question'})
        self.assertEqual(result['status'],'OK');self.assertNotIn(self.secret,json.dumps(result)+log.getvalue())
        self.assertIn('[REDACTED]',result['answer']);front.close()
    def test_02_forged_operation_rejected(self):
        self.assertEqual(self.raw(self.envelope('notebook_delete',{'confirm':True}))['result']['code'],'FORBIDDEN_OPERATION')
    def test_03_forged_notebook_rejected(self):
        args={'notebook_id':'forged','query':'Question','source_ids':['source-approved']}
        self.assertEqual(self.raw(self.envelope(args=args))['result']['code'],'NOTEBOOK_NOT_ALLOWED')
    def test_04_cross_notebook_source_rejected(self):
        r=self.raw(self.envelope(NAMES[3],{'notebook_id':'notebook-approved','source_id':'source-second'}))
        self.assertEqual(r['result']['code'],'SOURCE_NOT_ALLOWED')
    def test_05_credential_path_injection_rejected(self):
        args=self.envelope()['arguments'];args['canary_store']='/SYNTHETIC/arbitrary-store'
        self.assertEqual(self.raw(self.envelope(args=args))['result']['code'],'INVALID_ARGUMENTS')
    def test_06_profile_injection_rejected(self):
        args=self.envelope()['arguments'];args['profile']='owner-primary'
        self.assertEqual(self.raw(self.envelope(args=args))['result']['code'],'INVALID_ARGUMENTS')
    def test_07_timeout_unknown_no_retry(self):
        self.fixture['mode']='timeout';self.policy['timeout_seconds']=.1;self.restart()
        with self.assertRaises(Rejected) as r:self.query(self.client())
        self.assertEqual(r.exception.code,'PROVIDER_TIMEOUT_OUTCOME_UNKNOWN')
    def test_08_service_shutdown(self):
        client=self.client();self.stop();self.assertFalse(self.sock.exists())
        with self.assertRaises(Rejected):self.query(client)
    def test_09_malformed_provider_response(self):
        self.fixture['mode']='bad_structure';self.restart()
        with self.assertRaises(Rejected) as r:self.query(self.client())
        self.assertEqual(r.exception.code,'UNIMPLEMENTED_SOURCE_GAP')
    def test_10_credential_redaction_in_source(self):
        self.fixture['notebooks']['notebook-approved']['sources']['source-approved']['content']='Value {{SERVICE_CANARY}}'
        self.restart();r=self.client().get_source('notebook-approved','source-approved')
        self.assertNotIn(self.secret,json.dumps(r));self.assertIn('[REDACTED]',r['data']['content'])
    def test_11_policy_replacement_through_request_rejected(self):
        args=self.envelope()['arguments'];args['policy']={'notebooks':['forged']}
        self.assertEqual(self.raw(self.envelope(args=args))['result']['code'],'INVALID_ARGUMENTS')
    def test_12_same_uid_isolation_negative(self):
        result=subprocess.check_output([sys.executable,'-I','-B','-c',
            'import json,sys; print(json.load(open(sys.argv[1]))["synthetic_only"])',str(self.store)],text=True)
        self.assertEqual(result.strip(),'True') # Expected NEGATIVE host-isolation evidence, not isolation PASS.
    @unittest.skip('No authorized existing disposable separate-identity runtime; account/privileged provisioning is prohibited.')
    def test_13_separate_identity_canary(self):pass
    def test_14_peer_uid_is_kernel_bound(self):
        self.restart(allowed_uid=os.geteuid()+1)
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:
            s.settimeout(2);s.connect(str(self.sock));r=read_frame(s,131072)
        self.assertEqual(r['result']['code'],'CALLER_PRINCIPAL_REJECTED');self.assertEqual(r['account_id'],'')
    def test_15_body_cannot_forge_uid(self):
        self.assertEqual(self.raw(self.envelope(uid=os.geteuid()+1))['result']['code'],'IPC_REQUEST_INVALID')
    def test_16_wrong_client_identity_rejected(self):
        self.assertEqual(self.raw(self.envelope(client_id='forged-client'))['result']['code'],'IPC_CLIENT_ID_REJECTED')
    def test_17_client_checks_service_principal(self):
        with self.assertRaises(Rejected) as r:self.query(self.client(service_uid=os.geteuid()+1))
        self.assertEqual(r.exception.code,'SERVICE_PRINCIPAL_MISMATCH')
    def test_18_server_independently_rejects_widened_gateway_policy(self):
        widened=copy.deepcopy(self.policy);widened['notebooks']['forged']={'title':'Forged','sources':{'forged-source':'Forged'}}
        path=self.dir/'front.json';path.write_text(json.dumps(widened))
        gateway=Gateway(path,self.fixture_path,self.dir,provider=self.client())
        with redirect_stderr(io.StringIO()):r=gateway.call(NAMES[1],{'notebook_id':'forged'})
        self.assertEqual(r['code'],'NOTEBOOK_NOT_ALLOWED');gateway.close()
    def test_19_gateway_shutdown_stops_new_calls(self):
        client=self.client();client.close()
        with self.assertRaises(Rejected) as r:self.query(client)
        self.assertEqual(r.exception.code,'SERVICE_DISABLED');self.assertIsNone(self.process.poll())
    def test_20_service_policy_tampering_stops_requests(self):
        data=copy.deepcopy(self.policy);data['query_max_chars']=100
        self.policy_path.write_text(json.dumps(data))
        self.assertEqual(self.raw(self.envelope())['result']['code'],'SERVICE_POLICY_CHANGED')
    def test_21_malformed_wire_not_echoed(self):
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:
            s.settimeout(2);s.connect(str(self.sock));s.sendall(b'{bad synthetic secret\n');r=read_frame(s,131072)
        self.assertEqual(r['result']['code'],'IPC_FRAME_INVALID');self.assertNotIn('bad synthetic secret',json.dumps(r))
    def test_22_mcp_subprocess_through_service(self):
        async def exercise():
            params=StdioServerParameters(command=sys.executable,args=['-I','-B','-m','agent_librarian','mcp-serve',
                '--provider','service','--policy',str(self.policy_path),'--service-socket',str(self.sock),
                '--service-uid',str(os.geteuid()),'--control-dir',str(self.dir)],env={'LANG':'C','PYTHONIOENCODING':'utf-8'})
            async with Client(params) as client:
                listing=await client.list_tools();self.assertEqual({t.name for t in listing.tools},set(NAMES))
                result=await client.call_tool(NAMES[2],{'notebook_id':'notebook-approved','query':'Synthetic question'})
                self.assertEqual(result.structured_content['status'],'OK');self.assertNotIn(self.secret,json.dumps(result.structured_content))
                result=await client.call_tool('source_add',{'file_path':'/SYNTHETIC/forbidden'})
                self.assertEqual(result.structured_content['code'],'FORBIDDEN_OPERATION')
        anyio.run(exercise)
