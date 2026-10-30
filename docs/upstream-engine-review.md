# Notebook engine decision — KN-OSS-08 checkpoint

**Recommendation: C, a narrow hybrid whose goal is upstream ownership of the
Google-specific engine.** Keep this tested checkpoint intact. In a separately
approved follow-up, put a pinned upstream Python engine behind the existing
`ResearchProvider` boundary. Retain policy, project mapping, operation receipts
and only the compatibility code needed to preserve bounded responses, explicit
identity and single-dispatch guarantees. Do not retain two complete engines as
permanent fallbacks. No backend switch was made in KN-OSS-08.

## Evidence and component ownership

Reviewed current upstream revision:
[`8ac9728ec5b128b05077e9d7c4c8bb11b5830c61`](https://github.com/jacob-bd/gemini-notebook-mcp-cli/tree/8ac9728ec5b128b05077e9d7c4c8bb11b5830c61).
Current-main and pinned copies of seven inspected files matched byte-for-byte;
the archive records their SHA-256 values. This is source inspection and offline
compatibility evidence, not a live evaluation of upstream against this account.

| Component | Finding and proposed ownership |
|---|---|
| Project mappings, deny-by-default gateway, four MCP tools, exact-question permits | Unique Agent Librarian behavior. Keep the facade and its tests regardless of engine. Never expose upstream's broader MCP server or arbitrary methods. |
| Catalogs, explicit file plans, hashes and durable import journals | Agent Librarian product behavior. Keep authorization, reconciliation and unknown-outcome barriers; delegate protocol execution when safe. |
| Managed browser acquisition/profile ownership | Upstream already has named persistent profiles, CDP discovery and headless reuse. Much of our lifecycle duplicates it. Our approved executable acquisition, exact owned profile, OS-assigned loopback port and lease rules are justified compatibility requirements until upstream exposes equivalent controls. Avoid owning another general browser manager. |
| Authentication and session recovery | Upstream already extracts cookies/WIZ metadata, validates candidates and refreshes saved profiles. Custom token parsing and old Brave cookie/Keychain bridges are maintenance debt. Prefer configured upstream protected storage or browser-owned credentials; preserve existing installations during migration. Do not add another auth subsystem. |
| RPC envelopes, RPC IDs, source registration/upload/status layouts | Mostly duplicate upstream Notebook engine knowledge. These are the strongest candidates for direct reuse through a pinned Python dependency. |
| Browser-context RPC | Both implementations support in-page form POSTs; upstream also uses CDP for streamed research when selected. Our closed dispatch, account attestation and no-replay boundary are justified; maintaining a parallel library of Google envelopes is not a long-term advantage. |
| Source and citation decoding | Upstream already understands these layouts. Our final-only acceptance, source identity checks and bounded output are useful requirements, not reasons to own every layout. Prefer upstream decoding plus validated projection once behavioral parity is proved. |
| Incremental response projection and continuation | Justified current compatibility code: upstream's inspected CDP fetch calls `response.text()` and its query parser iterates that complete string. Our wire/frame budgets and final citation retention have targeted regressions. Contribute or adapt upstream streaming support rather than keep two parsers indefinitely. |
| Brave Apple Events adapter | Temporary installation compatibility. Preserve until managed live acceptance and rollback readiness; do not extend it as a second strategic engine. |

The upstream authentication/profile behavior is in
[`utils/cdp.py`](https://github.com/jacob-bd/gemini-notebook-mcp-cli/blob/8ac9728ec5b128b05077e9d7c4c8bb11b5830c61/src/notebooklm_tools/utils/cdp.py)
and [`core/auth.py`](https://github.com/jacob-bd/gemini-notebook-mcp-cli/blob/8ac9728ec5b128b05077e9d7c4c8bb11b5830c61/src/notebooklm_tools/core/auth.py).
RPC construction/recovery is in
[`core/base.py`](https://github.com/jacob-bd/gemini-notebook-mcp-cli/blob/8ac9728ec5b128b05077e9d7c4c8bb11b5830c61/src/notebooklm_tools/core/base.py)
and browser fetching in
[`core/cdp_transport.py`](https://github.com/jacob-bd/gemini-notebook-mcp-cli/blob/8ac9728ec5b128b05077e9d7c4c8bb11b5830c61/src/notebooklm_tools/core/cdp_transport.py).
File ingestion and answer parsing are in
[`core/sources.py`](https://github.com/jacob-bd/gemini-notebook-mcp-cli/blob/8ac9728ec5b128b05077e9d7c4c8bb11b5830c61/src/notebooklm_tools/core/sources.py)
and [`core/conversation.py`](https://github.com/jacob-bd/gemini-notebook-mcp-cli/blob/8ac9728ec5b128b05077e9d7c4c8bb11b5830c61/src/notebooklm_tools/core/conversation.py).
Its MIT license permits selective reuse with the retained attribution.

## Options

| Option | Maintenance | Security and reliability | Portability / existing contracts |
|---|---|---|---|
| A. Keep custom Notebook transport | Highest ongoing Google-protocol ownership; every layout and browser change needs local investigation. Small dependency surface, but duplicate expertise and fixes. | Current closed surface and replay/budget rules are explicit. We own their correctness and all service changes. Offline success still needs live acceptance. | Current native macOS evidence; Windows untested. Existing maps and four tools already work. |
| B. Upstream engine behind policy | Lowest protocol duplication if its public Python methods provide the needed controls. Requires version pinning, adapter tests and upgrade review. | Larger dependency surface; configure protected credentials and prevent fallback/debug-body logging. Upstream defaults cannot simply inherit our security guarantees. | Upstream has broader platform code, but our integration would still need native tests. Existing maps and MCP names can stay unchanged because only the provider implementation changes. |
| C. Narrow hybrid, recommended | Moderate transition cost; low-to-moderate steady-state cost only if each custom component has a documented reason and removal condition. Avoid permanent dual implementations. | Keep local authorization and outcome journals; delegate provider knowledge. Retain a small bounded/single-dispatch transport adapter where upstream controls are insufficient. | Same map schema and four tools. Preserve CLI mutation separation. Test each native platform before claiming support. |

## Constraints on direct reuse

The inspected upstream is not a drop-in backend under our acceptance rules:

- `execute_cdp_command` retries a command by default. An uncertain
  `Runtime.evaluate` containing a POST must not be sent twice. Its low-level
  `retry=False` capability must be respected through the whole call chain.
- `_call_rpc` includes auth and server/rate-limit recovery; its retry controls
  are not one universal mutation no-replay switch. File upload start/finalize use
  `execute_with_retry`. Our CLI journal cannot undo an internal engine replay.
- Upload bytes use cookie-authenticated HTTP upstream, even with CDP RPC selected.
  Browser-bound RPC success therefore does not establish upload compatibility.
  Direct HTTP and browser-context file transfer must be verified separately.
- CDP responses are buffered in full; query parsing permits a thinking-only
  fallback. Our gateway must keep byte/frame/output budgets and reject that
  fallback. Long source pages must preserve ID, ordering and actual citation IDs.
- Protected auth storage is supported, while legacy plaintext fallback paths
  also exist. Integration must choose and test the protected mode explicitly.
  The inspected query code also has raw-response debug logging; it must remain
  disabled or be sanitized before our application enables any such logging.

The smallest next experiment is an **isolated adapter spike**, not a rewrite:
implement the same four provider methods using a pinned upstream dependency,
run existing mapping/identity/permit tests and the 53-source/long-response fixture
suite, and prove that disconnects never replay a mutation or research question.
Reuse the current live plan only after separate owner approval. Adopt components
that pass; retain a compatibility shim only for a demonstrated gap, ideally with
an upstream fix proposed. Do not migrate active state, install upstream's broad
MCP server, replace journals, or remove the current rollback path during that spike.
