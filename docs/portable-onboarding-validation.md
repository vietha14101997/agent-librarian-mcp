# Portable distribution and onboarding validation

Release: 0.6.0. Validation date: 2026-10-30.

Implemented a neutral MCP stdio/Skill contract, environment-resolved locations,
explicit existing/new/skip project onboarding, account/title confirmation,
CLI-only experimental creation and durable replay-blocking receipts. The four
research MCP schemas and allowlists remain unchanged. Existing macOS default
locations, mapping format, authentication stores and optional Codex lifecycle
adapter are retained. No live installation migration was performed.

## Offline results

- Full suite: **344 run, 342 passed, 2 skipped, 0 failures/errors**.
- New onboarding, native creation contract and location tests: **34 passed**.
- The two existing skips require owner-authorized separate OS identities for
  deployment/IPC canary tests. No account or privileged runtime was provisioned.
- Actual built wheel installed into an isolated temporary runtime: **PASS**.
  Fresh packaged CLI emitted the neutral contract, required explicit Notebook
  selection, verified its saved mapping, skipped without changes, initialized
  exactly four SDK stdio tools, and denied an unmapped project.
- Legacy installation acceptance: **PASS** for repeat install, offline diagnostics,
  repair preserving synthetic auth, two-project selection and owned-only uninstall.
  The optional fresh Codex process probe was not requested for this release.
- Skill frontmatter validation, shell syntax, browser JavaScript syntax and
  `git diff --check`: **PASS**. The distributed JavaScript was also exercised in a
  synthetic Node VM: wrong operations, malformed create parameters and wrong
  accounts were rejected before the single mocked fetch.
- Distribution/wheel scan: **PASS**, with no developer home paths, personal
  identifiers or model prescriptions. Skill, creation program and both license
  notices are packaged. Private runtime/auth/state, Apple metadata and Git data
  are excluded. Synthetic fixture identities and legal attribution are retained.

The sanitized review archive includes exact per-test JSON, isolated package
acceptance JSON, distribution scan results, source snapshot and wheel. Its SHA-256
is supplied beside the archive. No real Notebook was created, no live research
query was executed, and no Notebook source was changed. Live Google operations
were zero. Runtime/authentication state was not deleted or migrated; synthetic
preservation tests passed.

## Commands

```sh
uv sync --locked
.venv/bin/python -I -B tests/run.py --output state/portable-tests.json
.venv/bin/python -B -m unittest tests.test_onboarding tests.test_notebook_admin tests.test_portability
uv build --wheel
.venv/bin/python -I -B scripts/verify_installation.py \
  --wheel dist/agent_librarian_mcp-0.6.0-py3-none-any.whl \
  --output state/portable-package-results.json
sh -n scripts/install.sh
node --check src/agent_librarian/personal/brave_create.js
git diff --check
```

The skill-creator frontmatter validator ran with its isolated YAML dependency;
no dependency was added to this package for validation.

## Limits

Automatic creation is **experimental and not live-verified**. Normal onboarding
returns a manual creation and explicit ID-linking fallback. The experimental path
requires separate owner approval, confirmed account/title/operation ID and the
additional opt-in flag. Failure/uncertainty retains a receipt and blocks replay,
even with a new operation ID or after unmapping. Recovery discovers and links only:
a known returned ID is retained; an uncertain result needs explicit owner selection.
Concurrency, abrupt dispatch interruption, malformed responses, failed post-create
discovery and failed mapping are covered by synthetic tests. Local receipts are
not provider-side idempotency and cannot guard against deleting local state or
creating separately outside the CLI.

The live transport remains the opt-in macOS Brave pilot with its existing dedicated
Keychain account binding. New-machine connection is not an automatic public login
flow. Native Windows is unsupported; other agent hosts must verify their own native
registration. Offline status does not prove current browser/session health. No
fresh live research/creation or cross-platform certification is claimed.
