# Rollback

No privileged step has been executed by KN-OSS-03. The owner-run tool defaults to
printing plans. After installation approval, use its fixed paths and review each
plan before separately running --apply:

```sh
/REVIEWED/python3 /ROOT_OWNED/manage.py disable --apply
/REVIEWED/python3 /ROOT_OWNED/manage.py stop --apply
/REVIEWED/python3 /ROOT_OWNED/manage.py rollback --apply
```

Run in an owner-controlled root terminal, never by granting the AI agent sudo.
Rollback verifies the installed plist hash, unloads the job if loaded, and moves
the same plist inode into /Library/AgentLibrarian/rollback without overwriting an
existing backup. It preserves the reviewed release, configuration, synthetic
canary, browser profile and Keychain state for owner recovery. It does not revoke
Google sessions; future session revocation is a separate owner action.

Partial installs deliberately retain created paths for inspection. No recursive
root deletion exists. Compare each retained file against the approved bundle and
remove only verified task-owned files after checking no service is running. Never
remove accounts/groups, a normal browser profile or private state automatically.
To restore a rolled-back deployment, the owner must review the saved plist,
restore it exclusively with original root:wheel 0644 ownership, recheck integrity,
and bootstrap only after clearing DISABLED deliberately. Do not overwrite a newer
installation. Full private-data deletion requires a separate explicit decision.
