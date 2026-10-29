# Portable installation contract

The installing agent discovers its host, OS, Python/package tooling, persistent
user-local runtime location, native MCP registration schema, and Skill discovery
directories. No IDE, LLM or agent configuration format is mandatory. Google Drive
Desktop, Drive APIs, and Drive synchronization are not required.

## Reuse or install

Check for `librarian`, an installed `agent-librarian` Skill, or `installation.json`
beside that Skill. Reuse the recorded interpreter, `installation_home` and
`state_dir`; do not replace existing runtimes, authentication or registrations just
because a new chat starts. Inspect a conflicting registration before modifying it.

For a new install, clone/download the public repository into a persistent location
chosen for the user's environment. Run `./scripts/install.sh` there, or create a
persistent Python 3.11+ environment and install the wheel using normal Python
package tooling. The script uses `uv sync --locked`; it changes only the checkout's
virtual environment and emits a contract. It does not choose an agent client.

Run that runtime's `librarian setup contract --project PROJECT` (use actual paths,
not literal placeholder names). Its JSON supplies:

- `command` and `args`: an absolute interpreter and argument array for MCP stdio.
- `tools`: the exact four research tools to discover after registration.
- `skill_source`: the packaged Skill to install in the host's native Skill location.
- `installation_home` and `state_dir`: resolved persistent mapping and auth locations.

Translate the contract to the host's native configuration; preserve unrelated
settings. Copy the Skill, and save the contract as `installation.json` beside it
for fresh-session discovery (or retain equivalent native persistent metadata).
Keep authentication out of Skill/configuration files. The contract contains no
secrets and writes no files. It works without authentication or a mapping.

Determine the actual intended project from the host workspace/cwd and resolve its
absolute directory. The emitted `--project` pins that directory. For a host that
starts each MCP process in the selected workspace, omit `--project` so the process
inherits its cwd. Reconfigure/restart for another project if the host shares one
process across workspaces. Call `librarian_list_notebooks` to verify project identity;
unmapped projects must return `PROJECT_NOT_MAPPED`. SDK stdio initialization works
offline; host registration/Skill discovery still needs host-specific verification.

Defaults resolve from the current user's home: macOS retains the established
`Library/Application Support/AgentLibrarian/{installation,personal-local}` paths;
other Unix hosts use `XDG_DATA_HOME` or `.local/share/agent-librarian`. Override with
`AGENT_LIBRARIAN_HOME` / `AGENT_LIBRARIAN_STATE`, or explicit `--home` / `--state-dir`.
MCP and research use `--installation-home` for the same maps directory. Preserve
recorded paths on every command. Native Windows is not supported (POSIX locks).

## Connection

Check `auth status` / `browser status` offline first. With no state, request an
explicit owner connection and follow [Personal Local](personal-local.md). The
current native path requires macOS Brave and its dedicated existing Keychain
account binding. It is not a general cross-platform or automatic first-install
Connect flow. Historical login methods remain explicit options, never fallbacks.
No Drive installation or synchronization is involved. `browser connect
--consent-discovery` requires permission and refreshes current-account metadata;
`--active-tab` additionally approves replacing the pinned tab. Restoring an expired
login or unavailable browser requires the owner, not silent account switching.

## Project onboarding

`librarian setup onboard --project PROJECT` resolves the nearest mapped ancestor.
If the mapping is present and its IDs remain in the bound inventory, it is reused.
A stale map is reported for review; missing authentication requires connection,
not a new mapping. No mapping returns `CHOICE_REQUIRED` with existing/new/skip.
The agent asks that question and waits for the owner's choice.

For an existing Notebook:

1. With discovery consent run `setup onboard --project PROJECT --choice existing
   --discover`. Show the returned IDs/titles and account binding. A call without
   `--discover` reads cached inventory and explicitly labels it cached.
2. Ask which Notebook to use. Even one entry requires explicit selection. Never
   infer from project names, matching titles, similarity or inventory order.
3. With owner selection, run `setup onboard --project PROJECT --choice existing
   --notebook-id SELECTED_ID --account-id RETURNED_ACCOUNT_ID --approve`.
   The selected ID must be in that account's discovery cache. This stores and
   verifies the mapping. Account mismatch/unknown IDs fail without linking.

For a new Notebook:

1. Run `setup onboard --project PROJECT --choice new` to propose a title and show
   the bound Google email, local account ID, and operation ID. This accesses only
   the dedicated account binding, with no network dispatch. Confirm the exact
   title and Google account with the owner before creation.
2. Pass the returned `--operation-id`, `--account-id`, confirmed `--account-email`,
   `--title`, and `--approve` with `--choice new`. The default result is
   `MANUAL_CREATION_REQUIRED`: the owner creates once in that Google account,
   reports the actual Notebook ID, then consents to discovery and explicitly links
   that ID using the existing workflow. Do not guess or derive an ID.
3. **Optional experimental path:** only if the owner separately approves trying
   unverified browser creation, also pass `--experimental-browser-create`. This
   dispatches one create operation using the existing pinned, account-checked
   browser transport. It is implemented and tested with synthetic responses, but
   has no successful live creation test and must not be described as reliable.
   It captures the actual returned ID, refreshes inventory, links only that ID,
   and verifies the saved mapping. It never uploads sources.

Before experimental dispatch, a durable receipt is stored under the user-local
installation `onboarding` directory. A per-installation lock serializes creation
and mapping. Failed, interrupted, malformed or unknown outcomes block all further
creation for that project, including attempts with a new operation ID. A successful
create followed by discovery/mapping failure retains the actual returned ID.
Do not delete the receipt or retry creation. Inspect the account with consent, then
use `--choice recover --approve --account-id ID --account-email EMAIL`. A known
returned ID is preserved; an uncertain receipt additionally requires an explicit
owner-selected `--notebook-id ID`. Recovery performs discovery and linking only.
Receipts remain as replay guards after recovery/unmap. This guards local retries,
not deletions of local state or creation performed separately outside this CLI.

`--choice skip` makes no writes, no credential access and no network requests.
`--dry-run` returns an offline preview without changes. A declined/missing mapping
never grants research access. The retained low-level `setup map` command is for
explicit administrative ID changes; agents should use verified onboarding.
`setup unmap` removes only an exact mapping; a mapped parent can still apply.

## Optional Codex adapter and existing installations

The receipt-based `setup install/plan/status/doctor/repair/update/uninstall`
commands retain their existing Codex behavior. Use `./scripts/install.sh --client
codex --dry-run` before initial registration and then omit `--dry-run`.
Choose `--codex-home`, `--skills-home`, `--home`, and `--state-dir` consistently for
nondefault targets. `setup repair --dry-run` previews repair of owned non-secret
files. `setup update --wheel WHEEL` validates a replacement before switching and
keeps the previous runtime. Existing entries require explicit `--adopt-existing`.
Do not run that adapter to register another host; translate `setup contract` instead.

Uninstall removes only unchanged receipt-owned components and retains maps,
creation receipts, authentication, Keychain, backups, external/modified runtimes
and Notebook content. No daemon or privileged component is required. Existing
working installations are not altered by this source update.
