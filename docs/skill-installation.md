# Persistent Skill and installation contract

The reusable product has four independent layers:

| Layer | Location / lifetime |
|---|---|
| Agent Skill instructions | Project .agents/skills/agent-librarian/SKILL.md; provider-agnostic |
| Installed CLI/MCP runtime | A pinned user installation, reused by all approved projects |
| Project notebook mapping | Project-local .agent-librarian/project.json, containing provider/IDs, never credentials |
| User authentication | User-only AgentLibrarian runtime state and dedicated OS Keychain item, outside Git |

This repository ships the minimal discoverable skill skeleton and read-only setup
status/planning commands. It does not install into another project or alter active
Agent settings. A newly started CLI process can detect these persisted artifacts
without conversation history. A separately approved user-level pilot installed the Skill in ~/.agents/skills,
a persistent runtime outside Git and one restricted Codex MCP entry. A fresh
ephemeral Codex session found the Skill/runtime and four tools, with local status
checks only and no Google requests. Repeated activation was a no-op. This does not
certify cross-client adapters or a general project installer.

## Implemented deterministic checks

```sh
librarian setup status --project /SELECTED/PROJECT
librarian setup plan --project /SELECTED/PROJECT
librarian auth status
```

Status checks installed version/interpreter, the selected project's skill/mapping/
MCP presence and default user authentication metadata. It never reads normal Brave,
invokes login, changes a project, contacts Google or exposes a credential. A plan
lists intended paths and conflicts; it does not grant installation permission.

## Follow-up idempotent installer contract

Prepare install/repair/update/uninstall as explicit operations against one selected
project. The user must approve the concrete changes before any project/config write.
A versioned receipt must record exactly owned files and hashes. Re-running install
with identical desired state must be a no-op. Detect an existing compatible runtime
and server first; do not install duplicates. Reject unknown/modified conflicts and
preserve unrelated AGENTS.md and Agent configuration. Uninstall removes only
unchanged receipt-owned files; never delete user authentication as a side effect.

MCP verification must parse the chosen Agent's supported configuration and verify
the exact restricted command/tool registry, preserving unrelated entries. Produce
a reviewable config patch before applying it. The personal pilot registration received separate owner approval after the live
pilot passed. No unrelated Agent settings or project files were changed. General
installer activation still requires explicit approval for the selected targets.

Project mapping schema v1 should identify provider, notebook ID, runtime mode and
user-auth reference. It must not contain cookies, tokens, browser paths, passwords
or Keychain exports. The present pilot has a single user-level selected notebook;
full per-project mapping precedence and migration are follow-up implementation.

Repair should fix only approved missing/owned artifacts, not reset authentication.
Update must pin/verify the runtime and support rollback. Installation status and
authentication status are separate: an expired account never justifies reinstalling
an Agent Skill or recreating a browser profile automatically. Ordinary research
should reuse accepted project policy; the finite KN-OSS-04 query permit is not the
final ongoing-research authorization model.

## Portability and remaining tests

Codex project discovery uses .agents/skills. Other clients may need adapters to their
current documented Skill/MCP locations; none are claimed compatible without tests.
Future acceptance: install twice without duplication; fresh Agent loads the skill
with no conversation memory; CLI/MCP version and mapping discovered; valid user
session reused; missing/expired auth reported without silent browser access; repair
preserves unrelated files; safe receipt-based update/uninstall; no cross-project
notebook leakage. Use synthetic credentials for automatic tests.

See [official OpenAI Skill guidance](https://learn.chatgpt.com/docs/build-skills)
for discovery/format. The skeleton keeps provider-specific authentication out of
its instructions; Gemini Notebook is the first provider, not the skill's identity.
