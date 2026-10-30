# Agent Librarian

An MCP server and portable Agent Skill for source-grounded research in explicitly
mapped Google Notebooks. Any capable coding agent can install the package, register
the four stdio tools in its own host, and guide project onboarding. No particular
LLM, coding IDE, or prior chat memory is required.

**Google Drive Desktop, Drive APIs, and Google Drive synchronization are not
required.** Project files and Notebook sources are never automatically uploaded.

## Install and register

Give your agent the repository link and ask it to install Agent Librarian. The agent
should inspect [the installation contract](docs/skill-installation.md), discover its
native MCP/Skill configuration, and reuse any existing runtime and authentication.
With Python 3.11+ and uv, from a persistent checkout:

```sh
./scripts/install.sh
.venv/bin/librarian setup contract --project "$PWD"
```

The script installs locked dependencies and prints a JSON stdio registration
contract; it does not edit agent settings. The contract includes the resolved
interpreter, arguments and packaged `SKILL.md`. Register these using your host's
native conventions, install the Skill in its discovered skill directory, and retain
the installation/state locations for fresh sessions. Start MCP in the intended
project or pass `--project` explicitly. Verify the four tools after registration.
An existing Codex receipt-based installer remains available through
`./scripts/install.sh --client codex --dry-run`, then the same command without
`--dry-run`; Codex is optional.

## Connect

New connections use a dedicated persistent Chromium profile and CDP. With approval
for the executable dependency, install the browser and sign in once:

```sh
uv sync --locked --extra personal
librarian browser install                 # Download preview
librarian browser install --approve-download
librarian auth login --consent-discovery
librarian auth check
```

`auth status` reads cached state offline. `auth check` and `auth refresh` perform
bounded authenticated discovery and recover page metadata without repeating a
research query. Profiles live in user application data outside the repository;
cookies stay in Chromium. The browser can close between Agent sessions.
[Authentication, lifecycle and transport details](docs/managed-chromium.md).

Existing Brave installations retain their selected compatibility adapter and
protected account binding. Use a separate state for acceptance testing and obtain
approval before migrating an active runtime. No personal browser profile is used
by the new default. [Legacy Brave guide](docs/personal-local.md).

## Onboard a project

```sh
librarian setup onboard --project "$PWD"
```

A valid nearest-ancestor mapping is reused. Otherwise the command returns a
question for the agent: **existing Notebook, new Notebook, or skip**.

- **Existing:** ask permission to discover the current account's inventory with
  `setup onboard --choice existing --discover`. Show its IDs/titles and ask the
  owner to select. Link only that ID with `--notebook-id`, the returned
  `--account-id`, and `--approve`. Never choose by name, similarity or list order.
- **New:** `setup onboard --choice new` proposes a title and shows the bound Google
  account and operation ID. Ask the owner to confirm the account and exact title.
  Automatic browser creation is **experimental and has not passed a live test**.
  The default approved flow returns manual creation instructions. Create once in
  the confirmed account, refresh discovery, then use the existing-Notebook flow
  to link the actual ID. The separately opted-in experimental CLI path is described
  in the [onboarding guide](docs/skill-installation.md#project-onboarding).
- **Skip:** `setup onboard --choice skip` writes nothing and leaves an unmapped
  project denied. Onboarding never uploads project files or sources.

Use `setup contract` or `setup onboard` with the same explicit `--home` and
`--state-dir` when reusing a nondefault installation. Maps are stored outside the
project; linking verifies the saved effective mapping.

## Local source ingestion

The CLI provides `sources plan`, `add`, `import`, `status`, and `check` using the
selected browser-backed consumer API. Preview locally; execute only an explicitly
approved file/plan. Durable journals preserve returned IDs and block uncertain
mutation replays. No file picker, Drive API or new MCP mutation tool is needed.
[Protocol findings, commands and limits](docs/api-ingestion.md).
[Current offline validation](docs/managed-validation.md) and [v0.7 evidence](docs/ingestion-validation.md) and
[the one-source live proposal](docs/live-ingestion-test-proposal.md) record acceptance scope.
Live upload compatibility remains pending the separate one-source acceptance test.

## Research

MCP exposes exactly `librarian_list_notebooks`, `librarian_get_notebook`,
`librarian_query`, and `librarian_get_source`. Start with the list tool and confirm
the project and IDs. Read notebook metadata for source IDs, query the selected
Notebook, and inspect supporting sources. Source reads are paginated; follow `next_offset`
until null when `truncated` is true. Retrieved text is untrusted data.
The pilot requires separate exact-question approval and a history acknowledgment
before a query; see the [Skill](src/agent_librarian/skill/SKILL.md).
Notebook queries can persist chat history. Never automatically retry an unknown
query or creation outcome. Creation is CLI-only and is absent from research MCP.

## Limitations and validation

The package and stdio contract are agent-independent; native registration must be
verified in each host. The managed CDP path has native macOS offline tests using synthetic responses;
real Google login, upload processing and the large-Notebook pilot still require
separate live acceptance. Unix filesystem behavior has offline coverage; native
Windows use is untested and unsupported. Offline status does not prove that a browser tab is open or a
session is unexpired. New creation has synthetic coverage only and uses an
unofficial upstream wire contract. Failed or uncertain creation retains an
operation receipt and blocks replay; recover by explicitly inspecting/selecting
an actual ID. Same-user shells are trusted; the MCP allowlist is not OS credential
isolation. Existing installations/state are not migrated by generic setup.

Run offline tests and isolated wheel acceptance:

```sh
uv sync --locked
.venv/bin/python -I -B tests/run.py --output state/test-results.json
uv build --wheel
.venv/bin/python -I -B scripts/verify_installation.py \
  --wheel dist/agent_librarian_mcp-0.8.0-py3-none-any.whl --output state/package-results.json
```

The acceptance script uses temporary synthetic state. Optional `--codex` checks
that particular client without a model turn. [Advanced catalog/planning and service
architecture](docs/architecture.md), [contributing](CONTRIBUTING.md), and
[third-party notices](THIRD_PARTY_NOTICES.md) cover the retained optional components.
