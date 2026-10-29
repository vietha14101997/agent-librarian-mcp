# Install once, research across projects

KN-OSS-05 adds a portable Skill, user-local notebook mappings and receipt-based
Codex installation. The original Personal Local Brave/Keychain pipeline is reused.
Google Drive synchronization, source uploads and automatic refresh are outside the
active roadmap. Catalogs and provenance remain available.

## Install from a source checkout

On macOS, install [uv](https://docs.astral.sh/uv/getting-started/installation/), then:

```sh
./scripts/install.sh --dry-run
./scripts/install.sh
```

The script uses the committed lockfile and builds a wheel. `setup install` creates
one persistent runtime from that wheel using uv, verifies its imports, registers
the user Skill and the single `agent_librarian_personal` MCP entry, and installs a
CLI launcher. Only package installation can download Python/dependencies; setup
never contacts Google. Run the same command again: identical installation is a no-op.
The script requires source checkout write access to `.venv` and `dist`; installed
research does not depend on that checkout afterward.

The install result contains the absolute `cli` path. To use `librarian` from any
shell, add the following directory to PATH in your shell configuration:

```sh
export PATH="$HOME/Library/Application Support/AgentLibrarian/installation/bin:$PATH"
```

Generated paths are local to the installing user. The wheel and source contain no
user-specific registration, credentials or browser data. Distribution from a
prebuilt local wheel is also supported:

```sh
uv tool run --from ./agent_librarian_mcp-0.5.0-py3-none-any.whl librarian setup install \
  --wheel ./agent_librarian_mcp-0.5.0-py3-none-any.whl --dry-run
# Repeat without --dry-run after reviewing the target paths.
```

`setup install --runtime-python /ABS/PERSISTENT/venv/bin/python` reuses a compatible
existing runtime instead of creating one. Do not point a persistent installation
at a disposable checkout or uv cache environment. The installer rejects runtimes
without the project-aware implementation. Reused external runtimes are never
removed by uninstall.

## Existing KN-OSS-04 installation

An existing server or Skill without a KN-OSS-05 receipt is preserved by default.
To migrate it, first review the concrete preview:

```sh
./scripts/install.sh --adopt-existing --dry-run
./scripts/install.sh --adopt-existing
```

Only the Agent Librarian server table and its Skill files are replaced. The
complete Codex config and every replaced file are backed up under the installation
home before changes. Unknown, inline or nested server-table layouts fail with an
actionable error. No unrelated settings or other tools are changed. Runtime
validation precedes registration. The previous runtime remains available for
rollback: use `setup update --runtime-python /ABS/PREVIOUS/COMPATIBLE/python`, or
restore the reviewed Agent Librarian table/Skill from backup for a legacy rollback.
Do not overwrite an entire backup config after other tools have changed it.

## Select notebooks for each project

Reuse the existing owner-approved discovery cache:

```sh
librarian notebooks list
librarian setup map --project /PATH/PROJECT_A --notebook-id DISCOVERED_ID_A
librarian setup map --project /PATH/PROJECT_B --notebook-id DISCOVERED_ID_B
librarian setup status --project /PATH/PROJECT_A
librarian setup doctor --project /PATH/PROJECT_A
```

A mapping contains only `provider: gemini` and `notebook_ids`. Repeat
`--notebook-id` to allow more than one notebook. Mapping replaces that project's
allowlist; the same mapping is a no-op. IDs must match the cached authenticated
inventory before research works. No project files or Notebook sources are touched.

Maps live in a private user-local `projects.json`, keyed by canonical absolute
project path. The nearest explicitly mapped ancestor applies to subdirectories;
a child mapping takes precedence. Unmapped projects have **no notebook access**,
including when the old global pilot selection exists. Inventory discovery grants
no research access. Moving a project requires mapping its new path.

```sh
librarian setup map --project /PATH/PROJECT_A --notebook-id REPLACEMENT_ID --dry-run
librarian setup unmap --project /PATH/PROJECT_A --dry-run
librarian setup unmap --project /PATH/PROJECT_A
```

Unmap removes the exact path, so an explicitly mapped parent can still apply.
Use status to inspect the effective result. Mapping changes are read on every MCP
call and do not require reinstalling. An already dispatched operation is not undone.

## Fresh Agent operation

Restart Codex after initial installation so it discovers the user Skill and MCP
registration. Launch the session in the intended project. The shared registration
inherits that session's working directory; no project MCP config is needed. A client
that does not inherit cwd must pass `--project /PATH/PROJECT` to the same runtime.
The Skill instructs the Agent to compare CLI mapping with `librarian_list_notebooks`
(which returns project, mapping origin and allowed IDs) before research.

All four tools initialize offline even without authentication or a project mapping.
`list_notebooks` returns only mapped, cached identities. Notebook/source reads reuse
the existing adapter and account binding. Queries retain the KN-OSS-04 exact-question
permit and history acknowledgment; a mapping does not create a permit. The pilot
keeps one outstanding permit per user, so approving another question replaces it:

```sh
librarian research approve --project /PATH/PROJECT_A --notebook-id DISCOVERED_ID_A \
  --question 'The exact authorized question' --ack-history
```

Then the Agent can prepare/call `librarian_query` with that notebook and question,
read cited sources with `librarian_get_source`, and report evidence and verification
limits. Unknown query outcomes must not be retried automatically. The legacy
`mcp-serve --provider personal` and non-project CLI remain explicit single-notebook
pilot interfaces; the installer always registers the project-aware provider.

Authentication remains outside projects and installation packages. Existing valid
state is reused without another login. A different computer needs an initial,
user-authorized Brave/account connection through the Personal Local setup described
in [personal-local.md](personal-local.md). That macOS consented bootstrap remains a
pilot; this milestone does not promise a public one-click Connect flow or zero-login
portability across machines. A missing or closed pinned tab requires owner action,
not reinstalling, cookie extraction or an automatic new profile/login.

## Lifecycle

| Command | Behavior |
|---|---|
| `setup install` | Create/reuse runtime, Skill, launcher and one MCP registration |
| `setup status --project PATH` | Inspect installation, cached authentication and effective mapping; exit 0 |
| `setup doctor --project PATH` | Same offline diagnostics; exit 2 when attention is needed |
| `setup plan` / `setup install --dry-run` | Preview paths and exact proposed MCP table, no configuration writes |
| `setup repair --dry-run` then `setup repair` | Restore missing/changed owned non-secret files; back up replacements |
| `setup update --wheel PATH` | Validate a new wheel runtime before switching registration; keep old runtime |
| `setup update --runtime-python PATH` | Switch to an explicitly selected compatible persistent runtime |
| `setup uninstall --dry-run` then `setup uninstall` | Remove unchanged owned registration, Skill, launcher and managed runtimes |

Status distinguishes `HEALTHY_OFFLINE` from live health: it does not read Keychain,
contact Google or inspect running Brave tabs. A closed tab or expired Google session
is detected only during an authorized dispatch. Damaged cached configuration,
missing mappings, disabled state and missing installed files are reported offline.
Repair never clears authentication state, Keychain, project maps or browser profiles.

Uninstall preserves modified components instead of deleting owner edits. It retains
unrelated Skill files, project mappings, backups, external/shared runtimes, modified
managed runtimes, authentication, Keychain credentials and all Notebook content.
Stop research sessions before uninstalling/updating. No service, daemon or privilege
subsystem is installed. Repeated repair/uninstall is safe.

Defaults:

| Component | User-local location |
|---|---|
| Receipt, maps, backups, managed runtimes, launcher | `~/Library/Application Support/AgentLibrarian/installation/` |
| Skill and discovery metadata | `~/.agents/skills/agent-librarian/` |
| Codex server table | `$CODEX_HOME/config.toml`, otherwise `~/.codex/config.toml` |
| Existing authentication/account binding | `~/Library/Application Support/AgentLibrarian/personal-local/` and dedicated Keychain item |

For isolated installations, provide `--home`, `--codex-home`, `--skills-home` and
`--state-dir` to setup commands consistently. Research uses `--installation-home`
instead of `--home`; MCP records both its installation and authentication state paths.
The Skill metadata records the runtime and state locations for fresh sessions.

Codex is the verified client. The Skill format, mapping resolver and runtime are
separate from the Codex table adapter; other clients require their own verified
registration adapter. Discovery/config conventions follow official OpenAI
[Skill guidance](https://learn.chatgpt.com/docs/build-skills) and
[configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference).

## Offline acceptance

```sh
uv sync --locked --python 3.12
.venv/bin/python -B -m unittest tests.test_installation tests.test_skill_setup \
  tests.test_personal tests.test_brave_transport
.venv/bin/python -I -B tests/run.py --output state/kn05-regression.json
uv build --wheel
.venv/bin/python -I -B scripts/verify_installation.py \
  --wheel dist/agent_librarian_mcp-0.5.0-py3-none-any.whl \
  --codex "$(command -v codex)" --output state/kn05-acceptance.json
```

The acceptance script installs the actual wheel into a clean temporary home,
repeats installation, maps two temporary projects, repairs damaged configuration,
starts three isolated ephemeral Codex processes, discovers the installed Skill and
four MCP tools, checks both distinct mappings and the unmapped denial through
Codex, and uninstalls only owned files. It starts no model turn or Google operation;
authentication metadata and notebook identities are synthetic. Omit `--codex` when
only package/CLI acceptance is needed; that does not claim Codex verification.
