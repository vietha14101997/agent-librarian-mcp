# Security

PERSONAL_LOCAL is the default current-user profile in 0.4.0. Its guarantees cover
the restricted official research interface, explicit login/selection/query consent,
Keychain-only session storage, user-only state, output projection/redaction and no
administrative MCP operations. It does not establish OS credential isolation from
same-user shells. The owner accepts this residual risk; a primary account expands
the exposure. The opt-in native Brave transport reuses one approved Notebook homepage through
Apple Events; it does not extract cookies or attach a debugger. macOS Automation
and Brave JavaScript permissions are browser-wide, despite the adapter tab gate.

The remainder describes the optional advanced isolated deployment and shared
controls. HOST_ISOLATION_PENDING_OWNER_SETUP does not block Personal Local mode.


The advanced 0.3.0 isolated deployment remains blocked pending owner setup.
Its synthetic providers and restricted Unix IPC are separate from the working
Personal Local native pilot. There is no synchronization executor or public TCP endpoint.
The local Unix listener checks kernel peer identity, fixed schemas and independent
service policy; it does not establish host isolation under the same UID.

Enforced controls include fixed MCP dispatch, explicit argument validation,
account/notebook/source allowlists, bounded queries, one provider operation at a
time, provider timeout without retry, output projection, credential-pattern
scrubbing, safe error codes and metadata-only receipts. A DISABLED sentinel in
the configured control directory rejects new operations and discards a pending
result. Stop/restart is required to reload policy. Live query history may persist; the fake provider does not contact Google.

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
credential boundary. Advanced isolated deployment requires a separate OS identity and protected state;
Personal Local instead accepts trusted same-user process access. Credentials must
remain in protected user storage, never project files, logs or archives.

Returned document text is untrusted data. It cannot change tool policy. Citation
source IDs are provider associations, not proof of semantic support or exact
revision provenance; results explicitly say SOURCE_NOT_VERIFIED. Text scrubbing
does not guarantee removal of unknown or encoded secrets. No universal agent
compatibility or production security is claimed.

Before publication, report findings privately to the repository owner through an
agreed private channel. No hosted reporting channel exists yet; choosing one is
a release gate. Never include real cookies, tokens, browser profiles or private
documents in an issue, test fixture, log or archive.

The source-derived Gemini adapter uses injected transport/auth capabilities;
it never discovers credentials. A synthetic-only store and exact known-canary
redaction test the boundary. A restricted HTTPS/session backend and Keychain helper bridge are supplied as
prepared code. Automatic tests use synthetic stores only; Keychain integration
and protected interactive capture are unverified and live activation is gated.
The same-UID negative test confirms the host isolation blocker remains. See
[owner prerequisites](docs/host-setup.md) and [IPC limitations](docs/ipc.md).

The current agent identity has admin/developer membership and the normal Brave
bundle is agent-owned. A distinct service UID alone does not satisfy isolation.
Effective elevation, ACLs, immutable code/launch policy, process memory and endpoint
ownership require owner verification. The default deployment is disabled/synthetic;
no privileged setup or login has been performed. See deploy/macos/README.md.
The HTTPS sender verifies TLS and rejects redirects, unexpected types/compression,
oversize data and unreviewed operations. It never retries a query. Query timeouts,
disconnects and parse failures can have unknown history effects. Local gate flags
summarize owner evidence; they do not independently prove that evidence exists.

Scoped normal-Brave cookie reuse is never a silent default. The personal pilot
requires explicit profile/row/Keychain consent and validates v10/schema24/domain
binding. The browser-wide key remains in a short-lived native helper; no DB copy,
key export, browser write/restart/debugger or plaintext fallback is implemented.
Earlier standalone replay reached homepage authentication but research RPC
returned error 16. No further cookie expansion or unchanged HTTP retry is planned.
The approved native path subsequently completed discovery and research. The preferred public architecture to evaluate
is extension/native messaging, not browser-wide key extraction.
