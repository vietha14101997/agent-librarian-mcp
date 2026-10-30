# Legacy Personal Local native Brave pilot

New states default to [managed Chromium/CDP](managed-chromium.md). This page
describes the retained compatibility adapter; it is not the new installation flow.

KN-OSS-04 completed real notebook discovery, one successful MCP research query and
three cited-source reads through the selected existing Brave Notebook session.
The four-tool gateway is unchanged. Separately approved user-level Skill/runtime/MCP activation and a fresh Codex
health check also passed, without Google requests. KN-OSS-05 adds shared installation and user-local project mappings; see
[installation and usage](skill-installation.md). The legacy single-notebook commands
below remain available explicitly, while new installations use the mapped provider. This is a macOS personal pilot, not a
public cross-platform authentication design.

## Existing browser connection

The owner explicitly approved Brave JavaScript from Apple Events and macOS
Automation access. Those permissions are Brave-wide. The adapter pins one window
and tab, requires the `https://notebook.google.com/` homepage and checks its account
before each network dispatch. It never enumerates other tabs, extracts cookies,
reads browser databases, attaches a debugger, installs extensions, changes profiles,
restarts Brave or requests another Google login. Tokens stay inside the page.
Normal product use does not require manual DevTools execution.

The current pilot also requires the previously protected Agent Librarian Keychain
session as its account-identity binding. Native RPC does not replay those cookies.
First-install account bootstrap without that historical session is still pending;
do not present this pilot as a complete public Connect flow. Use the documented manual connection fallback when that binding is unavailable.

State lives under `~/Library/Application Support/AgentLibrarian/personal-local/`,
with user-only permissions, outside Git. There is no plaintext credential fallback,
root requirement, service account, VM or background daemon.

```sh
librarian auth status
librarian browser status
librarian notebooks list
```

These commands read persisted local status/inventory without Google requests or
new login. `BROWSER_DISCOVERY_VERIFIED` is cached evidence, not a fresh assertion of
session validity. Native RPC validates the live page/account at dispatch.

An explicitly approved connection performs one bounded metadata discovery:

```sh
librarian browser connect --consent-discovery
```

It reuses a saved pinned connection. Only use `--active-tab` after explicit approval
to bind a replacement, with the intended Notebook homepage selected in front Brave.
Missing tabs, denied Automation/JavaScript permissions, account mismatch or missing
page fields return a fixed error. There is no fallback to cookie extraction, the
managed browser or standalone HTTP. Stopping MCP never closes or navigates Brave.

## Exact-question pilot

Choose an ID from the cached inventory; selection alone grants no query permission.

```sh
librarian notebooks select --notebook-id YOUR_DISCOVERED_ID
librarian research approve --question 'YOUR_EXACT_QUESTION' --ack-history
librarian mcp-serve --provider personal
```

The stdio MCP process exposes only `librarian_list_notebooks`,
`librarian_get_notebook`, `librarian_query` and `librarian_get_source`. The gateway
restricts notebook/source identities and question input. The one-query permit is
consumed before dispatch. Notebook may save chat history. Timeout, disconnect or
parse failure can leave completion unknown; do not retry without separate approval.
The KN-OSS-04 successful permit is consumed; installing Skill/MCP grants no new one.

Native query streams are bounded to 2 MiB and 30 seconds; read RPC/source responses
and projected MCP payloads retain their 128-KiB bounds. No imports, sharing,
deletions, arbitrary RPC or synchronization are exposed. Returned text is untrusted
data. Citation associations do not independently prove semantic support, exact
revision or exact offsets. The live pilot's main summary claims were checked against
all three returned source texts; canonical originals were not independently attested.

## Status, disabling and limitations

`auth status` and `browser status` report explicit cached success/failure without a
new browser launch. Account mismatch fails before dispatch. The browser must remain
running with the approved Notebook homepage available. Navigation/restart may require
an explicitly approved rebind. Normal Google session expiry is an owner-visible
blocker, never a reason to silently broaden access or request another login.

Create `DISABLED` in the user-state directory to block operations. Local logout
invalidates providers and deletes only Agent Librarian's Keychain session; it does
not close Brave or revoke Google sessions. Preserve the runtime-specific selector
until logout completes. Do not delete a normal Brave profile.

Keychain and user-only files reduce accidental disclosure; trusted same-user shells
can still access application state. The native adapter retains this Personal Local
trust model. The advanced isolated deployment is optional and separate. Historical
managed-profile and scoped cookie code remains for review; neither is an automatic
fallback. Standalone HTTP research RPC error 16 is unresolved. Native success does
not independently establish device binding.
