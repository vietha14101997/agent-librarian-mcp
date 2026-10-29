# v0.7.0 — file ingestion and large-notebook validation

Baseline: v0.6.0, `1a42e91`. Branch: `feat/api-source-ingestion`.
Date: 2026-10-30. **OFFLINE PASS; LIVE COMPATIBILITY NOT VERIFIED.**
The implementation commit is recorded in the review archive's `COMMIT.txt`.

## Delivered behavior

- CLI-only `sources plan`, `add`, `import`, `status`, `check`. No research MCP
  mutation method added; four tool names remain.
- Exact filenames by default, optional path-derived names, local/upload SHA-256,
  explicit unchanged-JSON adapters, bounded file reads and private durable journals.
- Existing-title conflicts and changed hashes block automatic imports. Registered
  IDs persist before upload. Uncertain registration/session/finalization is never
  replayed; matching uncertain hashes also block renamed-file bypasses. Definite
  local staging interruptions resume with the same source/session. Inventory
  checks distinguish HTTP acceptance, pending processing and actual readiness.
- Incremental UTF-8/frame consumption and bounded projection replace aggregate
  buffering of query progress and unused notebook metadata. Source text is paged,
  with service/IPC pagination preserved. No speculative source layout was added.

## Reproducible checks

```sh
uv sync --locked --offline
.venv/bin/python -I -B tests/run.py --output state/ingestion-validation/test-accepted.json
uv build --wheel --offline
.venv/bin/python -I -B scripts/verify_installation.py \
  --wheel dist/agent_librarian_mcp-0.7.0-py3-none-any.whl \
  --output state/ingestion-validation/package-accepted.json
```

The actual package run additionally used the local Codex executable via `--codex`
to check Skill discovery, exact four-tool initialization, project A/project B
mapping resolution and unmapped denial. These are synthetic client sessions,
not model turns or real Notebook queries.

| Check | Actual result |
|---|---|
| Full implementation suite | 385 total: 383 PASS, 2 SKIP, 0 failures/errors |
| Focused ingestion, browser, decoder, transport, IPC checks | 132 total: 131 PASS, 1 existing SKIP |
| Isolated wheel install, idempotence, repair/uninstall preservation | PASS |
| Packaged source CLI preview without authentication | PASS |
| Packaged upload/parser JavaScript and long-source decoder | PASS |
| Native Codex synthetic project/MCP checks | PASS for two mapped projects and an unmapped project |
| OSAgent Library plan | 45 Markdown + 8 JSON adapters; 53 accounted for, 6 macOS metadata files excluded |
| Original Library hashes | All 53 unchanged against the prior pilot manifest |
| Live uploads / research queries / notebook creation / deletions | 0 / 0 / 0 / 0 |
| Existing shared runtime | v0.5.0, HEALTHY_OFFLINE, not upgraded |
| Existing pilot mapping and cached source IDs | Preserved; 53 IDs match the prior pilot |
| Wheel modules/resources vs checkout | Exact byte match |
| Whitespace and distributed JS syntax | PASS |

The two existing suite skips concern separate-identity/privileged deployment
that the owner has not authorized. They do not cover upload/parser checks.
Full JSON evidence, per-test names and module hashes are in the review bundle's
`validation/test-accepted.json`. Package results are in
`validation/package-accepted.json`. Offline Library reproduction and preservation
records are included there too. No source Library payloads or authentication
state are bundled.

Wheel SHA-256: `4903c9212a4e2d7f80d26524d0fa20d6f40c79104dd09c51a4ddbc93eb5d8692`.

## What the failure investigation establishes

The exact paths are ordinary `rLM1Ne` notebook metadata, `hizoJc` source text, and
`GenerateFreeFormStreamed` research. Old Brave bounds were 128 KiB for an entire
ordinary response and 2 MiB for an entire query stream; the old HTTPS path still
used 128 KiB for queries. Synthetic 53-source metadata exceeding 128 KiB and 200
repeated progress frames exceeding 2 MiB reproduce these aggregate failures.
The new Python and distributed JavaScript projectors pass those cases while
retaining limits on individual frames, total bytes, traversal, frame count and
projected output. Malformed/truncated/deep/foreign frames are rejected.

All three previously unreadable originals exceed the old 16,000-character field
limit: approximately 60,520 characters for the execution-receipt Markdown
adapter, 60,024 for the JSON adapter, and 37,599 for the catalogue JSON adapter in
the prepared fixtures. The reviewed source-block shape containing these unchanged
local payloads reproduces `PROVIDER_STRUCTURE_INVALID`; the new decoder accepts
bounded text and explicit pages. These are source-derived synthetic fixtures,
not recovered live captures or proof that the old live responses had those shapes.

A targeted read-only diagnostic attempted the notebook and three source reads;
all returned `BRAVE_AUTOMATION_UNAVAILABLE`. Its sanitized evidence is included.
No raw failing response was recovered; the actual pilot frame count/byte size,
unused fields and any additional live shape differences remain unverified.
Accordingly this release does not claim either live blocker is conclusively
resolved. It corrects the demonstrated buffering/text-limit failures and prepares
bounded tracing for the next approved live test.

## Limits and next test

[Protocol details and CLI examples](api-ingestion.md) specify all budgets, admitted
formats, exact API stages and journal behavior. Unknown registration/session-start
outcomes can require owner-led recovery; the minimal CLI provides no destructive
or force-retry override. Large single frames, streams beyond the work budget,
more than 100 notebook source identities, cross-origin upload sessions and
unsupported formats remain bounded failures. Generic long-token redaction can
still mask legitimate source text; pagination uses sanitized offsets and does
not attest a stable remote revision. Upload uses the existing macOS Brave
consumer/default-account path, not a cross-platform or Enterprise transport.

The second supplied LobeHub listing was inaccessible and no matching public
implementation could be retrieved. Findings rely on the pinned actual source
implementation linked in the protocol document, not its README claims.

[The prepared live proposal](live-ingestion-test-proposal.md) names one new
230-byte disposable source, its SHA-256, the existing notebook, read-only source
checks and one exact new question with history acknowledgment. Separate approval
is required before that proposal is executed. The old UNKNOWN query is excluded.
No shared-runtime activation or real account/session recovery was performed.
