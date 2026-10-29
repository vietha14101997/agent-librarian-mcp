#!/usr/bin/env python3
"""Prepare a human login checklist; never launches Brave or touches credentials."""
import json
import os
from pathlib import Path
import sys

BASE=Path('/Library/AgentLibrarian')
def main():
    if sys.platform!='darwin':return {'status':'UNSUPPORTED_PLATFORM','network_operations':0}
    return {'status':'BLOCKED_PENDING_OWNER_ISOLATION_AND_LOGIN_APPROVAL','network_operations':0,
        'profile':str(BASE/'state/browser-profile'),
        'browser_required':'Administrator-owned separately reviewed Brave copy; current agent-owned app is unsuitable.',
        'human_gui_session':'Dedicated service account GUI session required; do not attach the normal profile.',
        'profile_command_template':[str(BASE/'browser/Brave Browser.app/Contents/MacOS/Brave Browser'),
            '--user-data-dir='+str(BASE/'state/browser-profile'),'--no-first-run','--no-default-browser-check','https://notebooklm.google.com/'],
        'command_executed':False,'cdp_endpoint_exposed':False,
        'capture_implementation':'UNIMPLEMENTED_PENDING_REVIEW: private-pipe or signed helper required; no cookie database reads or manual token entry.',
        'keychain_bootstrap':'Service-owned unlocked Keychain plus reviewed helper; daemon-session access must be tested without plaintext fallback.',
        'owner_approvals':['host setup','actual isolation evidence','selected Google account','dedicated interactive login','test notebook and nonsensitive material','query-history persistence','one live research query'],
        'live_enabled':False}
if __name__=='__main__':print(json.dumps(main(),indent=2))
