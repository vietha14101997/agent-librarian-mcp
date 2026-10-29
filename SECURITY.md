# Security

Version 0.2.0 is a local prototype with synthetic providers and restricted Unix IPC. Authenticated
integration is **BLOCKED_PENDING_ISOLATED_RUNTIME**. There is no Google login,
cookie import, browser extraction, TCP listener or synchronization executor.
The local Unix listener checks kernel peer identity, fixed schemas and independent
service policy; it does not establish host isolation under the same UID.

Enforced controls include fixed MCP dispatch, explicit argument validation,
account/notebook/source allowlists, bounded queries, one provider operation at a
time, provider timeout without retry, output projection, credential-pattern
scrubbing, safe error codes and metadata-only receipts. A DISABLED sentinel in
the configured control directory rejects new operations and discards a pending
result. Stop/restart is required to reload policy. Query history may persist when
a real provider is introduced; the fake provider does not contact Google.

The POSIX scanner uses descriptor-relative no-follow opens, rejects symlinks and
hardlinks, checks file identity/metadata before and after hashing and bounds file
sizes, total bytes, entries, depth and file count. Root documents are never
executed or edited. Hidden/private/credential/cache paths are excluded. These are
path defenses, not sensitive-content classification: a secret copied into an
ordinary allowed file remains sensitive. Choose document roots deliberately.

Snapshots are observations, not filesystem transactions. Changes after hashing,
concurrent directory changes and writers with equivalent OS permissions remain
risks. Future remote execution would need fresh hash, identity and approval checks
at dispatch. There is no such execution path in this version.

Local policies and approvals are declarations supplied by the operator; they are
not signed owner attestations or tamper-proof stores. A same-UID shell can modify
these files and run other code. A subprocess or virtual environment is not a
credential boundary. Do not put real Google credentials into this environment.
Future integration requires a separate OS identity, protected state inaccessible
to the agent, restricted authenticated IPC, fixed account attestation, safe
logging and tested revocation. Existing Brave sessions must not be reused.

Returned document text is untrusted data. It cannot change tool policy. Citation
source IDs are provider associations, not proof of semantic support or exact
revision provenance; results explicitly say SOURCE_NOT_VERIFIED. Text scrubbing
does not guarantee removal of unknown or encoded secrets. No universal agent
compatibility or production security is claimed.

Before publication, report findings privately to the repository owner through an
agreed private channel. No hosted reporting channel exists yet; choosing one is
a release gate. Never include real cookies, tokens, browser profiles or private
documents in an issue, test fixture, log or archive.

The source-derived Gemini adapter uses injected mock transport/auth capabilities;
it never discovers credentials. A synthetic-only store and exact known-canary
redaction test the boundary. No live credential store implementation is supplied.
The same-UID negative test confirms the host isolation blocker remains. See
[owner prerequisites](docs/host-setup.md) and [IPC limitations](docs/ipc.md).
