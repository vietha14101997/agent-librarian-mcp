# Personal Local authentication and controlled-pilot status

`auth login` reuses an existing saved application session when present. With no
saved session it requires explicit method selection. It never accesses a normal
profile or creates a managed profile automatically. The scoped existing-Brave
method requires `--method existing-brave --brave-profile <owner-selected ID>
--consent-existing-session --consent-discovery`. It is an opt-in personal pilot.
The managed method is an explicit alternative, not a Personal Local requirement.

The controlled attempt decrypted the approved records, but account validation
received HTTP 302 to Google sign-in. It stopped without saving a session, discovery
or query. This does not establish that normal Brave is signed out. The cause
(browser-live/WAL freshness, account context or provider compatibility) is not
established. No broader extraction or browser restart/debugger attachment followed.
An extension/native-messaging Connect flow is the preferred future evaluation.

# Personal Local authentication — current strategy

The owner prefers reuse of an existing authenticated Brave profile. `auth login`
now stops with EXISTING_BRAVE_ACCESS_APPROVAL_REQUIRED before opening a profile.
The scoped read-only cookie/Keychain route and an extension/native-messaging route
have been assessed; normal-profile access awaits separate explicit approval. No
normal cookies, browser Keychain item or debugger endpoint has been accessed.

The managed-profile implementation below remains an optional, explicit alternative
(`auth login --method managed-brave --consent-discovery`), not a mandatory Personal
Local requirement and not an automatic fallback. It is stopped for this pilot.


Personal Local runs as your current macOS user, on demand, with the existing
four-tool research gateway. It needs no root, launchd, new account or VM. The
advanced host-isolated deployment profile remains optional and separate.

```sh
uv sync --locked --extra personal --python 3.12
.venv/bin/librarian auth login --consent-discovery
.venv/bin/librarian auth status
.venv/bin/librarian notebooks list
.venv/bin/librarian notebooks select --notebook-id YOUR_DISCOVERED_ID
.venv/bin/librarian research approve --question 'YOUR_EXACT_NONSENSITIVE_QUESTION' --ack-history
.venv/bin/librarian research query --question 'YOUR_EXACT_NONSENSITIVE_QUESTION'
```

Brave and Apple Command Line Tools are required by the supported macOS flow.
No Playwright browser download is required: the pinned optional dependency uses
installed Brave. Default state is ~/Library/Application Support/AgentLibrarian/
personal-local/, outside your repository. Newly created runtime directories and
configuration are user-only. Never use a normal browser profile as --state-dir.

## Sign-in and visible outcomes

The currently supported explicit sign-in method launches/resumes one managed Brave
profile under that runtime directory, using a private Playwright pipe. The normal
Brave profile is never searched, opened, read for cookies, or attached to a debugger.
Sign in normally in the managed window and remain on the Notebook home page.
Previously saved Google sign-in in that profile is retained between attempts.
Temporary empty page lists, popup handoffs and navigation transitions are not
user cancellation. Only a confirmed closed context or timeout ends capture.

Successful login checks browser and HTTP account binding, completes one bounded
read-only discovery, persists session material to a new runtime-specific macOS
Keychain item, and returns AUTHENTICATED plus the account/notebook inventory. A
native outcome alert accompanies the CLI result; --no-notify disables the alert.
If an already saved session is usable, login returns AUTHENTICATED_REUSED without
opening a browser or repeating discovery. auth status is offline and shows the
last sanitized lifecycle outcome; --show-account explicitly displays the account.
No cookie, token, CSRF value or raw authenticated response is printed or logged.

Lifecycle metadata distinguishes page closure, browser disconnection and
controller cleanup. A window closing does not by itself prove Google sign-in
failed or succeeded. The profile can retain sign-in even when no Keychain session
was committed. Check auth status before repeating login.

## Why this is not an ordinary OAuth callback

The reviewed unofficial consumer API transport uses browser-session cookies and
page tokens. It supplies no accepted OAuth callback for returning a system-browser
login to this application. Personal Local itself is profile-independent and takes
a credential-store capability; a separate profile is not an OS security requirement.
The supported managed flow uses one to obtain consented session material without
touching unrelated sessions. Accessing an already-running normal Brave session
would need separate explicit authorization for cookies/debugger access (or another
reviewed integration). The tool does not silently do that or claim an OAuth flow
exists. Do not reuse another application's OAuth tokens.

## Discovery, selection and one-query pilot

Discovery may enumerate notebooks accessible to your account before the gateway
filters results. It reads metadata, not notebook source bodies. Choose the actual
notebook ID from the returned list; no ID is guessed. Selection is persisted locally.
The gateway permits only the selected notebook and its approved source IDs. Local
list operations reuse discovered metadata, preventing accidental repeated inventory
requests. Session page refresh does not add a discovery request in this mode.

The initial pilot uses one exact question approval with explicit acknowledgment
that Notebook can persist chat history. The permit is consumed before dispatch,
including an uncertain failure; there is no automatic query retry. For an MCP pilot,
run a direct metadata check, then send the single approved query through MCP rather
than running a second query. Returned source references are associations, not proof
of semantic support or exact revision. A successful answer without independently
checked citations remains SOURCE_VERIFICATION_INCOMPLETE.

## MCP integration

```sh
.venv/bin/librarian mcp-serve --provider personal
```

This starts only stdio, in process. Exactly list_notebooks, get_notebook, query and
get_source research tools are exposed under their librarian_ names. It exposes no
login/profile/store/admin arguments through MCP. Close the MCP process to stop it;
local logout or state generation changes invalidate existing providers. See
examples/codex.personal.disabled.toml. Review the concrete host configuration and
approve it before modifying active Codex settings; avoid duplicate Notebook servers.

The pilot's exact-query permit is intentionally finite. Unattended ongoing research
has not been enabled by that permit. A natural-language host request still needs
its applicable owner/tool approval; catalog/disclosure planning does not authorize
remote writes. No synchronization, import, deletion or sharing is implemented.

## Expiry, logout and removal

Expired page tokens refresh against the same approved account without browser
recovery or a query retry. Expired Google cookies require explicit auth login;
retained managed-profile sign-in may avoid entering credentials again. Account
mismatch fails closed; switching Google accounts is never an MCP operation.

```sh
.venv/bin/librarian auth logout
```

Logout disables running providers and deletes only this runtime's Keychain session
item. It retains the managed browser profile and does not revoke Google's sessions.
Revoke provider sessions through Google's own account controls if needed. After
stopping all Librarian processes, you may explicitly remove only the dedicated
AgentLibrarian runtime directory to remove its browser state, compiler cache and
metadata. Never remove a normal Brave profile. Logout before removing state so
the runtime-specific Keychain selector remains available for deletion.

## Errors and risk

PERSONAL_KEYCHAIN_UNAVAILABLE includes a numeric OSStatus when available. A locked
or inaccessible Keychain, missing compiler or denied helper operation is reported;
there is no plaintext cookie-file fallback. BRAVE_WINDOW_CLOSED means the context
closed, not that Google rejected a password. BRAVE_LOGIN_TIMEOUT retains profile
state. SESSION_REFRESH_STRUCTURE_CHANGED means reviewed page fields no longer
match; do not dump the page or blindly retry queries. auth status never refreshes
or contacts Google by itself.

Keychain protection and user-only permissions reduce accidental disclosure; they
do not isolate credentials from a trusted same-user shell. The managed browser
also retains protected authentication state. A primary Google account exposes a
broader credential/account inventory surface than a research-only account. Untrusted
text can contain prompt injections; retrieved data never changes gateway dispatch.
No mandatory host-isolation gate applies to Personal Local mode.
