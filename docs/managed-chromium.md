# Managed Chromium authentication and transport

Version 0.8 adds the default connection for **new** Personal Local states. Existing
Brave installations and their protected account bindings remain unchanged until
explicit migration. Live Google acceptance is separate from offline validation.

## Install and sign in

Install the optional browser client in the chosen persistent runtime:

```sh
uv sync --locked --extra personal
librarian browser install
```

The second command previews the executable dependency. Obtain owner approval
before `librarian browser install --approve-download`. It reuses the pinned
Playwright Chromium executable if present, otherwise downloads it to Playwright's
user-local browser cache. It never downloads from `auth login`. Network gateway
or certificate failures stop installation; do not disable TLS verification.

```sh
librarian auth login --consent-discovery
librarian auth status
librarian auth check
librarian auth refresh
```

First login opens a dedicated Chromium window. Complete Google sign-in there.
The command waits up to ten minutes (configurable `--timeout`, maximum fifteen).
It accepts login only after a real notebook-list RPC parses successfully. An
empty valid inventory is allowed. A homepage HTTP 200 is insufficient. If Google
refuses this build or challenges sign-in, report that result and let the owner
complete Google's normal flow; there is no challenge bypass or browser spoofing.

Future Python/MCP processes reuse the same profile. `auth login` first checks an
existing managed session without another interactive prompt. Read-only checks
have at most two discovery attempts with one fresh navigation between them.
`auth refresh` is the same bounded check with freshly loaded page metadata.
No operation retries a research question, registration, upload or creation.

`auth status` is entirely offline and returns `OFFLINE_CACHED`, with the last
check labeled separately. It never presents cached authentication as a live
verification. `auth check` distinguishes `AUTHENTICATED_VERIFIED`, `OFFLINE`,
`BROWSER_TEMPORARILY_UNAVAILABLE`, `SESSION_EXPIRED`, `GOOGLE_RPC_REJECTED`,
`REAUTHENTICATION_REQUIRED`, and account mismatch. `auth status --show-account`
shows the non-secret account binding. An ordinary expired login reuses the same
profile via `auth login --consent-discovery`; it does not delete cookies or reset
the profile in an attempt to recover.

`auth logout` clears cookies in this dedicated context, closes its browser,
disables the runtime and consumes outstanding question authorization. It retains
the profile directory, account binding, mappings and legacy Keychain item. It does
not claim to revoke Google's server sessions. Signing in as a different account
requires a separate explicitly initialized state; no account switch is inferred.

## Lifecycle and storage

Profiles live under dynamically resolved user application data:
`AgentLibrarian/managed-chromium/RUNTIME_ID` on macOS, or
`$XDG_DATA_HOME/agent-librarian/managed-chromium/RUNTIME_ID` on Unix (standard
user-local fallback when unset). They are separate from project state and Git;
repository ancestors and symlinked paths are rejected. Never archive this tree.
Chromium manages its own credential storage using its normal platform facilities;
the application does not export cookies or create another plaintext token store.
There is no custom password-store override, cookie DB reader, or daemon.

Authentication is independent of notebook selection and project maps. The only
extra app receipts are transport selection, account email and bounded health
metadata. Existing private ingestion journals may contain resumable upload URLs;
they remain excluded from CLI output and all review bundles.

Browsers use `--remote-debugging-port=0` and a loopback address. Chromium selects
the port atomically; the application reads its bounded `DevToolsActivePort` file
and constructs only a `ws://127.0.0.1` endpoint. Before reconnecting or closing, it
checks `Browser.getBrowserCommandLine` against the exact dedicated profile and
debugging flags. There is no endpoint scan or personal-browser attachment.
A nonblocking profile lease serializes controllers; conflicts return
`MANAGED_BROWSER_BUSY`. An unowned endpoint fails closed.

Normal operations start headless Chromium when needed and close the process they
started, retaining its profile. `librarian browser start` explicitly keeps a window
open; independent processes reconnect to it and leave it open. `browser close`
closes only that proven owned browser and never starts one to close it. A CDP
`Browser.close` command is required: closing an attached Playwright connection
alone only disconnects. Abrupt process loss can leave an owned browser available
for reconnect; unknown operation outcomes still must not be replayed.

The implementation uses portable Chromium/CDP and Python. The filesystem lease
is isolated here and currently uses Unix `flock`. Native Windows is untested and
unsupported. Native macOS browser tests use synthetic routed responses; they do
not prove that Google will permit login or accept uploads.

## Transport selection and limits

`transport.json` selects managed CDP only after authenticated discovery succeeds.
It wins over a retained Brave connection receipt. A conflicting legacy method is
rejected; use a separate state to exercise compatibility. Without that selection,
an existing Brave state keeps its original adapter. There is no automatic
transport fallback after an operation fails. Do not migrate active installation
state until live acceptance and an exact approved update/rollback preview.

RPC forms execute through Chromium `Runtime.evaluate` and in-page `fetch` using
current cookies and CSRF/session/build fields. Only the account identity leaves
the page before a request. Discovery, notebook/source reads and query envelopes
retain their closed contracts. Creation is a separate CLI program; ingestion has
its own closed registration/start/finalize program. No arbitrary browser or
mutation tool is exposed to the four-tool research MCP.

| Layer | Bound / behavior |
|---|---|
| Network reader in page | Incremental UTF-8, 64 MiB wire work, 256 frames |
| One wire frame | 2 MiB, depth 24, 100,000 visited elements |
| Projection before CDP | 128 KiB; source RPC up to 2 MiB |
| CDP returned JSON | 3 MiB (includes JSON escaping); no raw network body |
| Python decode | RPC match, notebook/source IDs, depth and size checks |
| Source text and pagination | Up to 1,048,576 characters; pages up to 16,000 |
| MCP final output | 128 KiB including diagnostics |
| File transfer | 8 MiB/file, 49,152-byte staging chunks, 32 MiB/import |
| Request time | Network abort/poll budget up to 30 seconds; synchronous JS evaluation 5 seconds |

Counters report bytes read, frames, RPC identifier, HTTP/provider error code and
error stage. Source decoder failures add only wrapper lengths. No raw body,
script text, cookies, CSRF, session IDs or upload URLs are logged. Malformed
framing, RPC rejection, identity mismatch and exceeded budgets have distinct
errors. A trailing marker without a frame is `HTTP_FRAME_TRUNCATED`; malformed complete frames return `PROVIDER_PROTOCOL_ERROR`; marker values
are not assumed to be UTF-8 lengths. Successful query projection retains the full
selected final frame and prefers citation-rich frames when answer lengths tie.

Uploads retain the v0.7 hashes, journals, returned IDs and no-replay rules. See
[the protocol](api-ingestion.md). Upstream uses direct HTTP for upload bytes;
this runtime deliberately uses a separate browser-context file transfer program
for same-origin upload sessions, avoiding cookie export. Browser fetch supports
these headers and bodies in native synthetic tests. Whether Google returns a
compatible same-origin session and completes processing remains a live acceptance
item. A cross-origin upload URL stops with `IMPORT_UPLOAD_URL_REJECTED`; there is
no speculative direct-HTTP fallback. Existing 53 sources must not be reimported.

## Upstream comparison

Inspected current upstream on 2026-10-30:
[`8ac9728ec5b128b05077e9d7c4c8bb11b5830c61`](https://github.com/jacob-bd/gemini-notebook-mcp-cli/tree/8ac9728ec5b128b05077e9d7c4c8bb11b5830c61).
The current `main` patch resolved to that revision. Downloaded `main` sources were
compared byte-for-byte with revision-pinned copies; hashes are in the review
archive's `validation/upstream-review.json`.

Reviewed `utils/cdp.py`, `core/auth.py`, `core/cdp_transport.py`, `core/base.py`,
`core/sources.py`, `core/conversation.py`, and MIT license. Reused patterns are
persistent dedicated profiles, CDP ownership, functional discovery before accepting
auth, headless reuse, known WIZ fields, browser-context form POSTs, resumable upload
parameters and final-answer/citation layouts. Existing MIT notices apply.

Upstream extracts/replays cookies for HTTP and has layered reload/headless recovery,
general retry support and an optional plaintext credential store. This runtime
keeps cookies in Chromium, reloads page metadata, retries only explicit read-only
health discovery (maximum twice), and preserves unknown-outcome barriers. It does
not reuse browser/profile enumeration, fixed-port scans, default personal profiles,
unrestricted client APIs, global browser cleanup, token fallback files or mutations
with automatic replay. Upstream CDP fetch buffers `response.text()`; the local
incremental projector is retained instead. No upstream runtime was copied wholesale.
