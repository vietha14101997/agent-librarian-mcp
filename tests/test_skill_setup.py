"""Fresh-process persistent discovery contract; no live Agent/model or auth access."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from agent_librarian.personal.state import PersonalState
from agent_librarian.personal.setup import inspect,plan
ROOT=Path(__file__).resolve().parents[1]

class SkillSetupTests(unittest.TestCase):
    def setUp(self):
        state=ROOT/'state';state.mkdir(exist_ok=True);self.temp=tempfile.TemporaryDirectory(prefix='skill',dir=state);self.project=Path(self.temp.name).resolve()
        self.user=PersonalState(self.project/'user-state',create=True)
    def tearDown(self):self.temp.cleanup()
    def test_01_status_no_project_mutation_or_auth_access(self):
        before=set(self.project.rglob('*'));result=inspect(self.project,self.user.path)
        self.assertTrue(result['runtime_installed']);self.assertEqual(result['project_writes'],0);self.assertEqual(result['network_operations'],0)
        self.assertEqual(before,set(self.project.rglob('*')))
    def test_02_plan_is_idempotent_and_does_not_install(self):
        self.assertEqual(plan(self.project,self.user.path),plan(self.project,self.user.path))
        self.assertFalse((self.project/'.agents').exists());self.assertTrue(plan(self.project,self.user.path)['requires_explicit_owner_authorization'])
    def test_03_fresh_cli_process_discovers_persistent_skill_and_auth_metadata(self):
        skill=self.project/'.agents/skills/agent-librarian';skill.mkdir(parents=True)
        (skill/'SKILL.md').write_bytes((ROOT/'.agents/skills/agent-librarian/SKILL.md').read_bytes())
        c=self.user.load();c['authenticated']=True;self.user.save(c) # Synthetic flag only; no credential or Google call.
        command=[sys.executable,'-I','-B','-m','agent_librarian','setup','status','--project',str(self.project),'--state-dir',str(self.user.path)]
        first=subprocess.run(command,capture_output=True,text=True,timeout=5);second=subprocess.run(command,capture_output=True,text=True,timeout=5)
        self.assertEqual(first.returncode,0,first.stderr);self.assertEqual(first.stdout,second.stdout)
        data=json.loads(first.stdout);self.assertTrue(data['skill_present']);self.assertTrue(data['user_authentication_record_present'])
        self.assertFalse(data['auth_validity_checked_online']);self.assertEqual(data['network_operations'],0)
    def test_04_existing_agent_instructions_preserved(self):
        path=self.project/'AGENTS.md';path.write_text('Existing project instructions.');before=path.read_bytes()
        plan(self.project,self.user.path);inspect(self.project,self.user.path)
        self.assertEqual(path.read_bytes(),before)
