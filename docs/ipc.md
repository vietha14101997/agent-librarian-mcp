# Restricted provider IPC

The agent-facing MCP gateway uses IPCResearchProvider. A separate provider-service
process owns its startup policy, synthetic canary store and injected adapter.
The service runs its own Gateway validation and output projection. Widening the
front policy does not widen server permissions. This is an application boundary;
the same-UID demo does not establish a separate OS security domain.

The only transport is a local Unix-domain stream socket. No TCP listener exists.
Each connection carries one newline-terminated JSON request, maximum 65536 bytes,
and one response, maximum 131072 bytes. Duplicate keys, extra envelope/argument
fields, unknown operations and malformed frames fail closed. No generic provider
or CLI dispatch exists.

Request keys are exactly version (integer 1), request_id (32 lowercase hex),
client_id, operation and arguments. Operations and arguments are:

| Operation | Arguments |
|---|---|
| librarian_list_notebooks | {} |
| librarian_get_notebook | notebook_id |
| librarian_query | notebook_id, query; optional source_ids |
| librarian_get_source | notebook_id, source_id |

Response keys are version, request_id, account_id and result. The client checks
correlation and account identity, then the outer gateway projects again. Errors
use safe codes; raw exceptions and credentials are never intentionally returned.
Notebook/source references remain SOURCE_NOT_VERIFIED.

Before reading a body, the server checks kernel peer UID: getpeereid on macOS,
SO_PEERCRED on Linux. The client independently checks the service UID. client_id
is an additional label, not a secret or authentication token. A body-supplied UID
cannot override kernel identity. Unsupported platforms fail closed; Linux code
has not been run in this milestone.

Startup file paths are operator arguments, never IPC arguments. The service
rejects symlinks, oversized/nonregular files and group/world writable state;
the canary store must belong to the current service UID with no group/world bits.
The synthetic store accepts only {synthetic_only:true, account_id, secret}, with
a bounded SYNTHETIC_ prefix. These checks cannot defeat an attacker of the same UID.
The socket parent must be owned by the service and not group/world writable;
socket mode 0660 is defense in depth, not host isolation.

The service fingerprints its policy at startup and refuses calls after a file
change. Reload requires owner review and restart. DISABLED in the socket control
directory rejects new calls. SIGTERM closes the service and removes only its own
socket inode; closing the front client prevents further calls. There is no retry
on timeout. Unknown query outcomes must be reconciled before a future retry;
a live research query may persist conversation history.

Results are bounded and projected; the known synthetic secret is also redacted
inside the service. Unknown/encoded secrets cannot be universally detected.
Sequential service handling and fixed backlog limit throughput, not denial of
service by an authorized UID. Socket path races, equivalent UID access, process
memory inspection and agent-owned launch configuration require a real OS boundary.
