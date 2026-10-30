# KN-OSS-08 checkpoint — v0.8.0

Date: 2026-10-30. Baseline `65be8c3`, v0.7.0 on
`feat/api-source-ingestion`. Implementation branch `feat/managed-chromium-auth`.
The exact resulting commit is in the review archive's `COMMIT.txt`.

**Implementation: PASS. Live functional acceptance: PENDING OWNER LOGIN AND
BOUNDED LIVE APPROVAL. Overall: PARTIAL. Active installation: not replaced.**

## Offline evidence

- Baseline suite: 385 tests, 383 PASS, two existing privileged-deployment skips.
- Final suite: **409 tests, 407 PASS, two existing skips, zero failures/errors**.
  The new 24 checks include native Chromium/CDP integration rather than counting
  a missing-browser skip as validation. Full per-test results and source hashes
  are in `validation/test-results.json` in the archive.
- Native browser: Playwright **1.64.1**, pinned Chrome for Testing
  **156.0.8078.4**, Chromium revision **1248**, macOS arm64. Launch/reconnect,
  actual independent Python process reuse, cookie persistence after close/reopen,
  profile locking, ownership checks and CDP close all passed. Profiles were
  temporary, outside the checkout, and removed after tests.
- All native Notebook responses were synthetic routed fixtures: 53-source
  metadata over 128 KiB, a source over 16,000 characters, a query stream over
  2 MiB, and final citation retention. Discovery/create and file registration,
  resumable start, byte staging and finalization executed through actual CDP and
  Chromium fetch. No real Google login, research query, upload or creation ran.
- Isolated wheel acceptance: **PASS**. Packaged auth/transport modules and all
  browser programs, download preview, ingestion preview, long-source decoder,
  clean install/repeat install, repair/uninstall preservation, fresh mapped and
  unmapped stdio clients, and exact four tools passed. This used a temporary
  synthetic installation; no active host configuration was changed.
- Whitespace, Python compilation, JS syntax and wheel resource/source matching
  are recorded in the final review checks. Dependency lock remains exact.

Reproduce in a development environment with the approved managed browser installed:

```sh
uv sync --locked --extra personal --offline
# Set KN_TEST_CHROMIUM_BIN to Playwright's resolved Chromium executable path.
# KN_TEST_MANAGED_DEFAULT=1 exercises the actual default runtime lifecycle.
KN_TEST_MANAGED_DEFAULT=1 KN_TEST_CHROMIUM_BIN="$MANAGED_CHROMIUM" \
  .venv/bin/python -I -B tests/run.py --output state/managed-validation/test-results.json
uv build --wheel --offline
.venv/bin/python -I -B scripts/verify_installation.py \
  --wheel dist/agent_librarian_mcp-0.8.0-py3-none-any.whl \
  --output state/managed-validation/package-results.json
```

The owner explicitly approved executable dependency downloads. The Playwright CDN
was blocked by the network gateway; the identical pinned browser version was
downloaded over verified HTTPS from Google's official public storage endpoint.
The 194,831,853-byte ZIP SHA-256 is
`987d2f8499c87d21676f78178550cfcbfb1bb53786821e2cff46c5a7e99b58be`.
Source URL and version are in `validation/browser-download.json`. Executables and
profiles are excluded from the review archive. An initial isolated test using the
installed Chrome binary preceded this; the final native evidence uses the pinned
managed build, with no personal browser profile access.

## Findings and limits

The v0.7 incremental parser, long-source bounds, pagination and import journal were
reviewed before changes and retained. Creation's separate discovery reader still
had the old aggregate bound; it now uses the same incremental projection. A later
equal-length answer frame could add citations that the earlier selection dropped;
Python and JS now prefer the citation-rich final frame. Truncated markers, Google
RPC errors and decoder-stage wrapper diagnostics have explicit safe reporting.
No query fetches large remote notebook metadata as a prerequisite.

The three pilot source IDs were recovered from its existing local acceptance
report, not from fresh Google requests. Their actual failing provider bodies have
not been recovered. Offline cases demonstrate corrected size/text-limit failures;
they do not establish the live response shapes or a live fix. Google account
acceptance, independent-process reuse of a **real** session, the three real reads,
53-source metadata, upload processing and actual citations remain unverified.
Cross-origin uploads remain a deliberate bounded failure. Windows is untested.

The current installation, legacy account/connection state and project mappings
were not migrated. Only non-secret metadata/configuration hashes were read for
preservation checks; no existing browser credential store or Keychain item was
read or copied. No OSAgent production code or Library source was modified.

[Managed authentication and transport](managed-chromium.md) records the design.
[The strategic engine review](upstream-engine-review.md) recommends a narrow
upstream-engine hybrid as the next architectural experiment; this checkpoint
does not switch backends. [The focused A–G live proposal](live-ingestion-test-proposal.md)
preserves all 53 originals and excludes the previous UNKNOWN question.

Stop at owner-controlled login and live authorization. Successful offline tests
do not authorize active runtime replacement. After live acceptance, prepare an
exact installation preview, backup current configuration/runtime, preserve a
rollback target, and obtain approval before activation.
