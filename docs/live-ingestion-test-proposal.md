# Proposed live acceptance — separate owner approval required

**Prepared only. No live upload or research query has been run for this change.**

Use the existing notebook `82de00a1-7a2a-4216-baea-861a96aed218` and its existing
OSAgent knowledge-pilot project mapping: `workspace/knowledge-pilots/osagent-library-live-test` within the existing OSAgentProjects root. Do not recreate the notebook or reupload,
rename, replace or delete any of its original 53 sources. Keep the installed
v0.5.0 runtime/authentication unchanged; use a temporary v0.7.0 stdio process with
the exact pilot `--project` and recorded installation/state paths for the test.
The checkout wheel has not been activated as the shared installation.

Approval would cover exactly:

1. Read current notebook metadata; retain all 53 original source IDs as baseline.
   Confirm the new MCP advertises exactly four research tools and the mapping
   resolves only the existing notebook. If Brave transport is unavailable, stop;
   no cookie extraction, browser/profile recreation or silent login recovery.
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
   proposal. Restore the existing pinned homepage if necessary.

The prior OSAgent authority-classification question with UNKNOWN outcome is
explicitly excluded and must never be replayed by this test. This proposal does
not authorize deployment, shared-runtime switching, another notebook, more files,
additional questions or cleanup deletion. Restricting the new question to one
source tests the query/citation path inside the large notebook; it does not prove
all-source 53-document research reliability. A broader question would require
separate owner authorization. Large repeated-frame behavior is currently tested
offline only.
