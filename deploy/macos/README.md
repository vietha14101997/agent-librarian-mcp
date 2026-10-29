# macOS protected research deployment — 0.3.0

Status: PREPARED, NOT INSTALLED. HOST_ISOLATION_PENDING_OWNER_SETUP.
The repository contains working offline code and inspectable owner-run tools.
No system account, group, launchd job, browser profile or Keychain item was created.
No Google account was authenticated. Live transport is tested with synthetic HTTP.
Interactive credential capture remains UNIMPLEMENTED_PENDING_REVIEW; a live pilot
cannot proceed using this release alone. Do not manually paste cookies or tokens.

## Recommended security profile

Use a dedicated unprivileged service account and a separate non-admin agent
account, or place the agent in a properly restricted VM. The service is a launchd
system job with explicit UserName/GroupName; it never runs authenticated work as
root. Installation/control uses an owner-controlled administrator terminal.
Neither service nor agent may be in admin or _developer, have an unattended sudo/
impersonation path, writable launch/code dependencies, or debugging privileges
that can inspect the service. Audit ACLs, groups, login automation, cached elevation,
SSH/remote access, taskgated policy and developer entitlements as part of acceptance.
Installer and fixed launcher reject admin/developer principals; these checks do
not discover every privilege path. The actual agent and service must be tested.

On the inspected host: macOS 26.6.2 arm64, SIP enabled; the current agent belongs
to admin and _developer. The installed Brave bundle is agent-owned. That environment
is NOT accepted as isolated. SIP documentation protects certain system processes;
it does not certify this third-party Python service or replace privilege review.
No sudo, debugger attachment or credential access was attempted.

A separate UID is necessary but incomplete evidence. Agent must fail credential/
profile reads, policy/code/launch writes, endpoint replacement, process-memory
inspection and impersonation. An unauthorized third UID must fail socket access
or kernel UID authorization. Service access to its own synthetic canary and only
the four research operations must succeed. Current automatic tests use one UID;
they explicitly do not satisfy this host gate.

## Fixed installation layout

| Path | Owner/mode | Purpose |
|---|---|---|
| /Library/AgentLibrarian/releases/0.3.0 | root, directories 0755 | Immutable self-contained Python/runtime, package and dependencies |
| /Library/AgentLibrarian/config | root:client-group 0750 | Fixed runtime and service policy, files 0640 |
| /Library/AgentLibrarian/integrity.json | root 0644 | Exact reviewed release member hashes |
| /Library/AgentLibrarian/state | service 0700 | Synthetic canary, audit and future private browser state |
| /private/var/run/agent-librarian | service:client-group 02750 | Socket parent; no agent writes |
| research.sock in that directory | service:client-group 0660 | UID-checked research IPC |
| /Library/LaunchDaemons/org.agentlibrarian.provider.plist | root:wheel 0644 | Fixed nonroot job |

Only service and the approved agent belong to the narrow client group. Group
membership permits socket connection; kernel UID still selects the authorized
caller. The parent setgid bit supplies the socket group. Check actual group/mode
at deployment; supplementary membership and ACLs must not broaden write access.
Code/config are administrator-owned for stronger immutability; the service owns
its private runtime/authentication state. A service compromise can expose its
credentials. Use a research-only Google account with minimal notebook access.

## Exact owner steps, requiring separate approval

1. In a trusted administrator session choose/create the dedicated service account,
   non-admin agent account or VM, and client group through approved macOS account
   management. This tool creates no users/groups and changes no sudoers settings.
   Audit effective elevation, debugging and remote-control paths. Do not grant the
   agent administrator passwords or execute root steps from the agent chat.
2. Review the commit/archive and build the wheel with uv.lock. In a root-controlled
   staging directory such as /private/var/root/agent-librarian-stage/0.3.0, construct
   this self-contained, symlink-free bundle:

   ```text
   manifest.json                   # relative-file -> SHA-256; excludes itself
   runtime/bin/python3             # actual relocatable interpreter, no venv symlink
   runtime/...                     # stdlib, locked dependencies, installed wheel
   libexec/keychain-helper          # owner-built from templates/keychain-helper.swift
   libexec/launcher.py              # exact reviewed scripts/launcher.py
   policy.json                     # enabled SYNTHETIC research policy copy
   fixture.json                    # SYNTHETIC research.json fixture
   ```

   Use an independently reviewed standalone Python distribution; copying an editable
   venv or agent-owned interpreter is insufficient. The immutable-runtime supply
   chain, relocatability, code signing and clean-home import behavior remain owner
   acceptance checks. Compile the helper in owner staging; never invoke it during
   automated tests. Review every bundle file and retain the manifest SHA-256 out
   of band. Root-own the staging tree and all ancestors; no symlinks, .pth startup
   files, private documents or credential files are accepted. Do not execute a
   root installer script directly from an agent-writable checkout: review/copy it
   into root staging first. No installation hooks or online dependency download
   occurs in manage.py.
3. Inspect the root-staged installer dry-run with the chosen EXISTING identities:

   ```sh
   /REVIEWED/python3 /ROOT_STAGING/manage.py install \
     --bundle /private/var/root/agent-librarian-stage/0.3.0/bundle \
     --bundle-sha256 REVIEWED_MANIFEST_SHA256 \
     --service-user SERVICE_NAME --agent-user AGENT_NAME --client-group CLIENT_GROUP
   ```

   The same command with --apply requires explicit owner root authorization. It
   refuses existing installation paths, validates identities, manifest, file hashes,
   modes and symlinks, and exclusively creates the fixed paths above. It installs
   only synthetic data, live_enabled=false, all G1–G12=false and DISABLED. It does
   NOT bootstrap launchd, authenticate, modify Brave or register MCP. Root policy
   files remain outside agent write authority; hashes are integrity records, not
   an independent owner signature. Partial failure retains paths for inspection.
4. Review actual filesystem owners/modes/ACLs and all release hashes. Run the
   synthetic service first. In an owner root terminal inspect, then deliberately
   --apply enable and --apply start using manage.py. start bootstraps the fixed
   launchd plist. Use --apply status to query launchctl; output is a safe status
   receipt. The fixed launcher checks principals and the protected runtime hashes
   every installed file, rejects unlisted files, wrong UID, stale policy or enabled
   live configuration without all approval records. Root-owned configuration change
   or DISABLED rejects subsequent calls. Stop removes only its own socket.
5. From the actual agent account run verification/agent_probe.py with its numeric
   UID and the synthetic service PID. Separately exercise approved MCP research,
   denied admin/cross-notebook requests, forged client identity, and third-UID
   rejection. Repeat after stop/restart and revocation. Missing targets, mocked
   checks and skipped cases do not count. The probe does not establish unattended
   elevation/ACL/impersonation safety; the owner must audit those separately.
6. Stop/disable and review the isolated browser/login design before any credentials.
   See docs/session-auth.md and scripts/login_plan.py. A separate administrator-owned
   Brave copy and service-owned profile are required. No existing Brave login or
   debugging session is reused. The audited capture mechanism and Keychain access
   across the selected service/GUI sessions are still open. Do not mark those gates
   complete or seed credentials manually to bypass this gap.
7. Only after genuine host isolation, accepted login implementation and explicit
   account/notebook/history/query approvals may an owner-controlled live pilot be
   considered. No such approval or pilot is recorded here. Do not simply set the
   G1–G12 flags to true; they summarize independently verified owner evidence.

## Operations and rollback

manage.py prints plans unless --apply is present. Supported actions: status,
start, stop, restart, disable, enable and rollback. restart uses kickstart only
for a loaded job and refuses DISABLED; stop then start is the reviewed reload
procedure. provider-status checks protected configuration/version/integrity without
network; it is not a credential health check. Query history can persist, including
an unknown timeout outcome. There is no automatic query retry.

See rollback/README.md. Rollback verifies and preserves the plist, unloads the job,
and keeps release/config/private state. It does not delete Google sessions or user
accounts. A full uninstall/private-state destruction needs separate owner approval.

## Apple and portability references

The launchd profile follows Apple's [daemon guide](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html)
and [launchd.plist source](https://github.com/apple-oss-distributions/launchd/blob/main/man/launchd.plist.5).
[SIP runtime protections](https://developer.apple.com/library/archive/documentation/Security/Conceptual/System_Integrity_Protection_Guide/RuntimeProtections/RuntimeProtections.html)
have a narrower scope than a guarantee for this service. Local launchctl help
confirmed system-domain modification requires root on the inspected host.
Linux/Windows deployment profiles are not implemented. Portable provider/catalog
code contains no hardcoded macOS installation path. Browser, Keychain and launchd
acceptance remain macOS owner setup work.
