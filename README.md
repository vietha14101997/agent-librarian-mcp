# Agent Librarian MCP

A local Python package for deterministic document catalogs, provenance, change
detection, disclosure-aware synchronization planning and restricted MCP research.
The research provider is synthetic. Google Gemini Notebook is a planned adapter,
not an operational integration. Authentication remains
**BLOCKED_PENDING_ISOLATED_RUNTIME**.

This project is independent development infrastructure. It is not an OSAgent
product module or a general autonomous document-editing agent. It never uploads,
edits or publishes documents, executes a sync plan, shares/deletes sources or
starts a public MCP endpoint.

## Install locally

Use Python 3.11+ and uv. Python 3.12.12 on macOS arm64 was used for local tests.
The official MCP SDK is pinned to 2.3.0; transitive versions/hashes are in uv.lock.

```sh
uv sync --locked --python 3.12
.venv/bin/librarian --help
```

The build backend is flit_core==3.12.0. No upstream Notebook CLI is installed or
needed. A virtual environment isolates dependencies, not Google credentials.
macOS POSIX filesystem behavior and a local synthetic MCP client were tested;
Windows scanning currently fails closed and other hosts are not universally
certified. This repository is local and unpublished.

## Catalog and planning demo

From the repository root:

```sh
mkdir -p state
.venv/bin/librarian scan --root examples/documents --manifest examples/catalog.json --output state/catalog.snapshot.json
.venv/bin/librarian validate --root examples/documents --manifest state/catalog.snapshot.json
.venv/bin/librarian changes --previous state/catalog.snapshot.json --current state/catalog.snapshot.json
.venv/bin/librarian sync-plan --catalog state/catalog.snapshot.json --policy examples/sync-policy.json
.venv/bin/librarian sync-plan --catalog examples/catalog.approved.json --policy examples/sync-policy.json
```

The first plan is BLOCKED_APPROVAL; technical acceptance is not external
disclosure approval. The second is a synthetic ADD_CANDIDATE, with
execution_enabled=false and zero remote operations. Every approval, Drive ID,
account and notebook in examples/ is synthetic. Existing files on Drive do not
gain retroactive approval.

Without a manifest, scan discovers metadata with UNKNOWN authority/disclosure and
UNCLASSIFIED kind. It does not infer acceptance from names or recency. Explicit
manifests supply stable IDs; discovery-only IDs are path-based. A changed hash,
missing file, broken relationship or unsafe path is visible as an issue. Output
files must be outside the scanned root. A scan still reads each eligible file to
hash it; saved metadata reduces repeated LLM document reading, not all disk I/O.

An OSAgent Library metadata adapter is available:

```sh
.venv/bin/librarian scan --root examples/documents --manifest examples/library-manifest.synthetic.json --adapter osagent --output state/adapted.snapshot.json
```

The adapter preserves explicit metadata, defaults absent disclosure to UNKNOWN
and requires reconciliation. It does not alter Library or invent historical
approvals. These examples use synthetic metadata only.

## Fake-provider MCP demo

```sh
.venv/bin/python -I -B examples/fake_demo.py --state-dir state/demo
```

This launches a real MCP subprocess using the official SDK client and exercises
discovery, notebook metadata, source read, query and direct forbidden deletion.
The fake answer is deterministic, not an external model response. Citations carry
returned source IDs; SOURCE_NOT_VERIFIED means semantic support and revision
provenance are not independently attested. Retrieved text is always untrusted.

Exactly four tools are exposed:

- librarian_list_notebooks
- librarian_get_notebook
- librarian_query
- librarian_get_source

The default packaged research policy is disabled. The demo enables only a copy
of the synthetic policy in its explicit state directory. For manual stdio use:

```sh
.venv/bin/librarian mcp-serve --policy state/demo/research-policy.json --fixture tests/fixtures/research.json --control-dir state/demo
```

Create state/demo/DISABLED or stop the process to disable calls. Query input is
bounded, concurrent provider calls are rejected and timeout does not retry.
Future real queries may persist Notebook chat history. The `google` provider
option always refuses startup. No browser profile or credential input is accepted
through MCP. examples/codex.disabled.toml is a disabled configuration example,
not an active registration or proof of Codex-host compatibility.

## Test and review

```sh
.venv/bin/python -I -B tests/run.py --output state/test-results.json
```

Tests use synthetic fixtures and actual CLI/MCP subprocesses. See
[architecture](docs/architecture.md), [security](SECURITY.md),
[contributing](CONTRIBUTING.md), and [provenance](THIRD_PARTY_NOTICES.md).
Version 0.1.0 is an initial foundation, not a production security claim.
Secure authenticated adapters, signed approval storage, broader platform tests,
dependency auditing and public release approval remain open gates.
