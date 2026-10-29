# Service authentication lifecycle and remaining login gate

Implemented: injected Session/SessionManager; strict fixed account/host binding;
short-lived page/RPC validation; negative session ID preservation; expiration/error
handling; revocation/disable states; a narrow Keychain helper bridge; no plaintext
fallback. All automatic tests use MemoryStore and synthetic HTTP, never Keychain.

The Swift helper stores exactly one generic-password item under
org.agentlibrarian.research.session / service-session-v1, within the service user's
Keychain security context. It accepts read/write/delete internally; secret data
travels only through anonymous pipes. The helper has no MCP exposure, secret argv,
secret environment, log output or credential file fallback. The installed binary
and caller runtime must be root-owned/hashed, and the service must be nonroot.
Keychain locked/UI-required/failure states fail closed. Do not grant broad access
via security add-generic-password -A or embed an unlock password. The helper is
prepared source, not a verified daemon-session Keychain integration.

Session startup treats stored data as UNVALIDATED even if it has an old future
expiry. It checks expected_email against the unique reviewed internal oPEP7c field,
SNlM0e CSRF, FdrFJe session and cfb2h build label, then validates discovery response
structure before saving refreshed page state. No generic email guessing is used.
This is source-derived account checking, not a cryptographic account attestation;
actual Google identity remains unverified until a controlled live pilot. A local
account label or cookie presence alone never establishes authentication.

Validation has a five-minute local lifetime. This is not a Google cookie-expiry
claim or cookie renewal. Bad refresh enters AUTH_REQUIRED without saving; revoked
or disabled managers reject further calls. HTTP/protocol auth errors invalidate
cached validation. The runtime lock serializes service instances. There is no
silent browser recovery, cookie mirror, legacy auth file, environment import or
MCP account switch. Revocation deletes the local Keychain item when invoked from
a reviewed service-owner maintenance context; provider-wide session revocation
and clearing the dedicated profile are separate human actions. Stopping the service
or setting its protected DISABLED sentinel immediately blocks new operations and
discards pending results; it does not undo conversation history already persisted.

## Initial interactive login — intentionally blocked

No existing browser or Keychain state was accessed. scripts/login_plan.py only
prints a plan. It does not launch Brave, create a profile, expose CDP or log in.
The first login needs separate approval for the selected account and exact action.
Prefer a dedicated research account. A primary account's credentials could expose
all resources that account can access despite the service's notebook allowlist.

Required future sequence: approve host setup; prove actual credential/profile/code/
policy/endpoint/memory/elevation separation; install a reviewed administrator-owned
Brave copy; open a fresh service-owned profile in that service user's human GUI
session; authenticate interactively; capture through a separately audited private
pipe/signed helper; attest account; persist only to the protected Keychain; close
browser transport; validate the read-only API before enabling research. Do not
attach the normal Brave profile, read cookie databases, expose a loopback CDP port
to the agent, or paste cookies/tokens into chat or a terminal command.

The private capture helper is UNIMPLEMENTED_PENDING_REVIEW. GUI-to-launchd Keychain
access/unlock behavior is NOT VERIFIED. A launch daemon has no ordinary interactive
GUI session; the owner must verify the chosen security/audit context and locked-
Keychain behavior without a plaintext password/file fallback. Those missing pieces
block login and live transport activation. Do not seed credentials manually as a
shortcut. Browser-dependent renewal remains a human reauthentication operation.
