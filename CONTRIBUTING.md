# Contributing

Use Python 3.11+ and the committed uv.lock. With uv installed:

```sh
uv sync --locked --python 3.12
.venv/bin/python -I -B tests/run.py --output state/test-results.json
```

Choose an output outside the document root; keep generated results out of commits.
Tests create disposable synthetic state under ignored state/test-runs by default.
AGENT_LIBRARIAN_TEST_DIR may select another explicit local test directory.

Keep catalog operations deterministic and provider-independent. Add a focused
test for changed behavior. Preserve dispatch validation when updating the MCP
SDK; schemas/tool visibility do not replace executable authorization. Use only
synthetic documents, accounts, IDs and secret-like test strings. Never add a live
provider, remote synchronization, browser extraction or credentials as a shortcut
to a passing test.

Document source provenance and license notices for copied or substantially
adapted code. Review pinned dependency changes and upstream security advisories.
Do not automatically merge an upstream branch. A dependency lock is not a full
security audit.

Use semantic versions while keeping pre-1.0 schema/contract changes explicit.
Before a public release, establish maintainer/security contacts, license review,
dependency auditing, supported-platform CI and a reproducible build process.
This initial repository has no remote or publication workflow. Release/tag/push
operations require a separate owner decision.
