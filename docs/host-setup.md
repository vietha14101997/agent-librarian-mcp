# macOS host setup and credential lifecycle

Status: HOST_ISOLATION_PENDING_OWNER_SETUP. No account, privileged service,
Keychain item, security setting or active agent configuration was created.
The same-UID 0600 canary test intentionally demonstrates readable state. There
was no permitted existing disposable separate-identity runtime; that test is
explicitly skipped. A venv, process, Unix socket or chmod alone is insufficient.

## Owner-executed prerequisite sequence

1. Select a separate noninteractive service principal, managed sandbox or VM.
   The agent principal must have no sudo/impersonation path, login credentials,
   writable service executable/dependencies, or control of service launch settings.
   Review local macOS account/MDM rules with the host administrator before creating
   that principal. Do not reuse the owner's existing Brave session.
2. Install the reviewed immutable wheel and its locked dependencies in a location
   the agent cannot write. Use administrator-owned launch configuration with a
   fixed executable and fixed startup paths. Do not install this editable checkout
   or execute owner instructions automatically. This release has no live service.
3. Assign service-owned state (0700), policy (0600), and credential store (0600).
   Assign a service-owned socket directory (0750), with a narrowly selected client
   group for traversal and socket access (0660). The agent cannot write the parent,
   service policy, fixture, DISABLED sentinel or launch definition. Use numeric UIDs
   from the chosen principals, not a client-supplied claim. Audit group membership.
4. Run the synthetic-only service as the chosen service principal using this fixed
   template with absolute reviewed paths and independently determined UID values:

   ```sh
   /ABS/venv/bin/librarian provider-service --socket /SHORT/service/research.sock \
     --service-policy /PROTECTED/service-policy.json --fixture /PROTECTED/research.json \
     --canary-store /PROTECTED/synthetic-canary.json --allowed-uid AGENT_NUMERIC_UID \
     --client-id research-client --adapter gemini-mock
   ```

   The Unix socket path must be at most 100 bytes. Keep parent ownership consistent
   with the service startup checks. This template does not provision users/groups.
5. From the actual agent identity, prove canary read, policy modification, executable
   replacement and direct privileged provider access fail. From a third unauthorized
   identity prove IPC calls fail. From the authorized agent prove only the four
   research operations work and the service kernel UID matches. Preserve receipts
   without secret values. Repeat after reboot/restart and after revocation.
6. Only after those checks, independently review a future live transport and dedicated
   authentication flow. Authenticate outside the agent environment to a dedicated
   research account with access only to selected notebooks. A primary account would
   expand credential exposure to all resources accessible by that account; do not
   treat an application allowlist as restricting stolen account credentials.

## Revocation and future live acceptance

An owner can stop the service or create its protected DISABLED sentinel to revoke
new operations; review in-flight outcomes without retrying blindly. Revoke account
sessions at the provider when needed, remove/rotate protected state, update allowlists
and approvals, then review and restart. Policy changes fail closed until restart.
The live service must implement tested expiration, refresh, account attestation,
least privilege, safe logs/backups and credential rotation without returning secrets.
The current synthetic store does not implement those live lifecycle operations.

An owner-controlled approval service must separately bind disclosure to revision,
account, destination and revocation. Publication execution remains absent until
that provenance is enforceable outside agent write access. No next milestone,
Google call, host installation or public release is authorized by these instructions.
