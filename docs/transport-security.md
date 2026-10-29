# Restricted HTTPS transport — implemented, synthetic-tested

GeminiHTTPS accepts only reviewed ReadRequest descriptors for list_notebooks,
get_notebook, query and get_source. Notebook/source allowlists and exact request
parameters are enforced again in the transport. No MCP argument selects a method,
URL, profile, cookie value, store or debugging endpoint.

The sender uses stdlib HTTPSConnection and default certificate/hostname verification.
Hosts are exactly notebooklm.google.com or notebook.google.com, selected in protected
startup/session configuration. Redirects, including redirects between those hosts,
are rejected. No proxy environment, HTTP fallback, custom CA override, generic
client RPC or upstream runtime is imported. TLS connection is made only at dispatch.

Requests use the pinned batchexecute/stream form envelopes, source path, build label,
CSRF and session ID. RPC response correlation and structured auth errors are checked.
XSSI/count framing is parsed strictly; unknown layouts fail closed. Headers include
identity encoding only; unexpected compression/content type, duplicate sensitive
headers, oversize data and invalid UTF-8 are rejected. Binary credentials and raw
responses have no debug dump or log path. Known session values are redacted inside
the service before gateway projection; unknown or encoded secrets are not universally
removable.

HTTP read/connection timeouts are configured and response reads share a remaining
budget. OS DNS resolution and host scheduling are not a certified hard wall-clock
bound; DNS/network behavior needs live acceptance. RPC/stream responses are capped
at 131072 bytes; token refresh HTML is capped at 2 MiB. Excessive response sizes
may reject legitimate large notebooks/sources. No automatic retries exist. Query
transport failures, timeouts or parser failures remain unknown outcomes; a Notebook
conversation entry may have persisted. No result is reported as success without
accepted parsing and account/identity checks.

The injected session manager first validates known internal account/token fields
from a fixed-host page and then a valid notebook-discovery response. Signed-out
HTTP 200, missing/ambiguous fields and account mismatch fail. Tokens refresh before
dispatch, never by retrying a possibly persisted query. Cookie/PSIDTS renewal, browser
recovery, multi-account switching, enterprise endpoints and administrative RPCs are
unsupported. The owner must reauthenticate when the cookies expire.

Provider kind GEMINI_HTTPS_UNVERIFIED and IPC_RESEARCH_SERVICE identify a code path,
not live verification. Results retain SOURCE_NOT_VERIFIED. Returned source association
does not prove semantic support or exact remote revision. Tests use synthetic page,
HTTP and session data only. No authenticated Google request has been made.
