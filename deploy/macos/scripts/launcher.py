#!/usr/bin/env python3
"""Fixed macOS launch entry; installed root-owned inside the reviewed release."""
import grp
import json
import os
from pathlib import Path
import pwd
import sys
from agent_librarian.providers.runtime import run_runtime,protected_json
from agent_librarian.gateway.common import Rejected

CONFIG=Path('/Library/AgentLibrarian/config/runtime.json')
def launch():
    if sys.platform!='darwin':raise Rejected('PLATFORM_UNSUPPORTED')
    c,_=protected_json(CONFIG)
    for uid in (c['service_uid'],c['agent_uid']):
        user=pwd.getpwuid(uid);groups=os.getgrouplist(user.pw_name,user.pw_gid)
        if 80 in groups or 204 in groups:raise Rejected('ADMIN_OR_DEVELOPER_PRINCIPAL_REJECTED')
    run_runtime(CONFIG)
if __name__=='__main__':
    try:launch()
    except Rejected as e:print(json.dumps({'status':'ERROR','code':e.code}),file=sys.stderr);raise SystemExit(2)
    except Exception:print('{"status":"ERROR","code":"PROTECTED_STARTUP_FAILED"}',file=sys.stderr);raise SystemExit(2)
