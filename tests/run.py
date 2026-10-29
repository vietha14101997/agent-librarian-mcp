"""Run actual implementation tests and emit portable JSON evidence."""
from pathlib import Path
import argparse
import hashlib
import json
import sys
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
entries=[]
class Result(unittest.TextTestResult):
    def startTest(self,test):test.started=time.monotonic();super().startTest(test)
    def addSuccess(self,test):
        super().addSuccess(test);entries.append(dict(name=test.id(),status='PASS',elapsed_ms=int((time.monotonic()-test.started)*1000)))
    def addFailure(self,test,err):super().addFailure(test,err);entries.append(dict(name=test.id(),status='FAIL'))
    def addError(self,test,err):super().addError(test,err);entries.append(dict(name=test.id(),status='ERROR'))
    def addSkip(self,test,reason):super().addSkip(test,reason);entries.append(dict(name=test.id(),status='SKIP',reason=reason))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output');args=p.parse_args()
    suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'),top_level_dir=str(ROOT))
    result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(suite)
    report=dict(kind='ACTUAL_IMPLEMENTATION_TESTS',version='0.5.0',total=result.testsRun,
        passed=sum(x['status']=='PASS' for x in entries),tests=entries,
        skipped=sum(x['status']=='SKIP' for x in entries),
        google_operations=0,prior_milestone_simulations_counted=False,
        credential_isolation='HOST_ISOLATION_PENDING_OWNER_SETUP',
        live_google_verified=False,authentication_material='SYNTHETIC_ONLY',
        source_sha256={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted((ROOT/'src').rglob('*.py'))})
    if args.output:Path(args.output).write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
