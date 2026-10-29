#!/usr/bin/env python3
"""Owner-approved synthetic host probe. Never opens real credential files.

Run only after privileged setup is separately approved. Positive results are
partial evidence; unattended elevation/ACL/MDM/debugger policy require owner audit.
"""
import argparse
import ctypes
import grp
import json
import os
from pathlib import Path
import stat
import sys

def inaccessible(path,flags):
    try:fd=os.open(path,flags|os.O_NOFOLLOW)
    except PermissionError:return True
    except OSError:return False # Missing/unavailable targets are not isolation proof.
    else:os.close(fd);return False

def process_memory_denied(pid):
    if sys.platform!='darwin' or pid<=0:return None
    lib=ctypes.CDLL(None)
    try:self_task=ctypes.c_uint.in_dll(lib,'mach_task_self_').value
    except (ValueError,AttributeError):return None
    lib.task_for_pid.argtypes=[ctypes.c_uint,ctypes.c_int,ctypes.POINTER(ctypes.c_uint)]
    lib.task_for_pid.restype=ctypes.c_int
    task=ctypes.c_uint();result=lib.task_for_pid(self_task,pid,ctypes.byref(task))
    if result==0:lib.mach_port_deallocate(self_task,task.value)
    return result!=0

def probe(agent_uid,service_pid):
    if os.geteuid()!=agent_uid:raise ValueError('WRONG_AGENT_UID')
    base=Path('/Library/AgentLibrarian');socketdir=Path('/private/var/run/agent-librarian')
    result={'correct_agent_uid':True,'non_admin_non_developer':not ({80,204}&set(os.getgroups())),
        'synthetic_canary_read_denied':inaccessible(base/'state/canary.json',os.O_RDONLY),
        'profile_traversal_denied':not os.access(base/'state/browser-profile',os.R_OK|os.X_OK),
        'policy_write_denied':inaccessible(base/'config/policy.json',os.O_WRONLY),
        'executable_write_denied':inaccessible(base/'releases/0.3.0/runtime/bin/python3',os.O_WRONLY),
        'launch_config_write_denied':inaccessible('/Library/LaunchDaemons/org.agentlibrarian.provider.plist',os.O_WRONLY),
        'endpoint_parent_not_writable':not os.access(socketdir,os.W_OK),
        'process_memory_access_denied':process_memory_denied(service_pid),
        'unattended_elevation':'OWNER_AUDIT_REQUIRED','acl_and_impersonation':'OWNER_AUDIT_REQUIRED',
        'host_isolation':'NOT_ACCEPTED_BY_THIS_PROBE_ALONE'}
    return result
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--agent-uid',required=True,type=int);p.add_argument('--service-pid',required=True,type=int);a=p.parse_args()
    print(json.dumps(probe(a.agent_uid,a.service_pid),indent=2))
