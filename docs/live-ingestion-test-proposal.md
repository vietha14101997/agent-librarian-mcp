# Proposed live acceptance — separate owner approval required

**Prepared only. No live upload or research query has been run for this change.**

Use the existing notebook `82de00a1-7a2a-4216-baea-861a96aed218` and pilot
project `workspace/knowledge-pilots/osagent-library-live-test` within the existing
workspace. Keep all 53 original sources and the installed runtime/configuration.
Use the v0.8 development interpreter with a **separate** user-local test state,
separate test mapping home and dedicated managed Chromium profile. Do not copy
cookies, authenticated profiles or Keychain contents from the existing pilot.

First, the owner completes interactive Google login in the managed window. Login
includes one authenticated discovery RPC to prove the session. Preserve the profile
and verify reuse from an independent process. This sign-in step grants no upload,
reconciliation import execution, or research question authorization.

**After login, request one approval for the exact A–G set below.** That approval
must explicitly include the one disposable upload (D), duplicate/reconciliation
execution (E), and the exact new history-persisting question (F). If the owner
approves only a subset, execute only that subset. No E or F before specific approval.

A–G bounded verification set:

A. Verify the bound Google account and notebook discovery (one health check).
B. Read these three previously failing source IDs, following source continuation
   offsets until null; retain bounded shape/stage/byte/frame diagnostics:

   | Original | Source ID |
   |---|---|
   | execution-receipt schema Markdown | `0f36dab2-6ba6-4a45-bfdd-1a7d966adf19` |
   | execution-receipt schema JSON adapter | `8a52a037-b468-4f3a-8a34-3f88ff57aa2e` |
   | Library manifest JSON adapter | `699be9a7-0248-435a-b051-bde39bf09cbd` |

   These IDs come from the original local pilot acceptance report, not new Google
   reads. Compare source ordering and relevant text with the original documents.
C. Read the 53-source notebook metadata, retain its baseline ID set, and confirm
   the four-tool MCP and exact pilot mapping.
D. Upload the single disposable source described in step 2 below once.
E. Perform read-only processing reconciliation, then repeat the identical approved
   import once to prove it reuses the ready journal ID without another upload.
F. Grant one exact-question permit and dispatch the question in step 5 once,
   restricted to the new returned source ID. Never replay an UNKNOWN result.
G. Check the returned answer and actual citation against the new source text;
   confirm all original 53 IDs remain. Retain receipts; do not delete the source.

Execution details:

1. Read current notebook metadata; retain all 53 original source IDs as baseline.
   Confirm the new MCP advertises exactly four research tools and the mapping
   resolves only the existing notebook. If managed Chromium or authentication is unavailable, stop;
   no personal-browser access, profile reset, or alternative transport dispatch.
2. Upload one new disposable file, once, through `sources add --approve`:
   `examples/ingestion/agent-librarian-ingestion-smoke-20261030.md`.
   Its exact content is committed in the review bundle. Size: **230 bytes**.
   SHA-256: `79faf514dc897508202c056743c298b0c604f065e4dfd718541c3626aad1ffb5`.
3. Use `sources check` to verify the actual returned ID, exact filename and status
   2. All original 53 IDs must remain; expected inventory becomes 54 sources.
   Re-running the identical import must return the journaled ready ID without
   registration or finalization. Any uncertain mutation outcome stops the test;
   reconcile by ID with read-only checks, never upload another source to recover.
4. Read the three previously failing sources with the new MCP and follow
   `next_offset` until null. Compare relevant text against the local originals,
   while reporting sanitization and remote-revision limits. No fixture-derived
   shape is to be presented as a captured live response. Read notebook metadata
   without the former aggregate-response failure.
5. Approve and issue exactly this **new** question, acknowledging that chat
   history may persist:

   > Using only agent-librarian-ingestion-smoke-20261030.md, what is the confirmed smoke-test value? Cite that source.

   Record the exact CLI permit using `research approve --project PILOT
   --notebook-id 82de00a1-7a2a-4216-baea-861a96aed218 --question QUESTION
   --ack-history` and the recorded `--installation-home` / `--state-dir`.
   Call `librarian_query` once with `source_ids` restricted to the new returned
   source ID. Expected answer: **cobalt-17**, with a citation to that actual ID.
   Retrieve the cited source and verify the answer against its text. On any
   unknown outcome, do not retry or register another permit automatically.
6. Save sanitized request-kind/frame/byte counters and receipts, source IDs,
   preserved original-ID comparison, and a PASS/PARTIAL/BLOCKED report. Retain
   the disposable source and its import receipt; deletion is outside this
   proposal. Close only the managed test browser; retain its dedicated profile.

The prior OSAgent authority-classification question with UNKNOWN outcome is
explicitly excluded and must never be replayed by this test. This proposal does
not authorize deployment, shared-runtime switching, another notebook, more files,
additional questions or cleanup deletion. Restricting the new question to one
source tests the query/citation path inside the large notebook; it does not prove
all-source 53-document research reliability. A broader question would require
separate owner authorization. Large repeated-frame behavior is currently tested
offline only.
