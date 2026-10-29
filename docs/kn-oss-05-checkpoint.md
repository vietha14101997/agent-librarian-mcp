# KN-OSS-05 checkpoint

Baseline: `e4b223f54a5828c614f7167450b7ff4039518fb6` (KN-OSS-04).
Implementation: version 0.5.0; see [installation and usage](skill-installation.md).

Implemented source/wheel installation, a persistent shared runtime and CLI launcher,
receipt-owned Skill/Codex registration, project mappings outside repositories,
offline status/doctor, repair/update/uninstall and change previews. The four-tool
research contract and Brave/account/Keychain path are retained. Unmapped projects
are denied; nearest mapped ancestor wins. Mapping changes apply at the next call.

Validation on macOS, Python 3.12.16, Codex CLI 0.165.0-alpha.1.2:

- Focused lifecycle/Personal Local/Brave tests: 80 passed.
- Full regression suite: 310 run, 308 passed, 2 skipped (existing separate-identity
  isolation prerequisites; no new skipped tests).
- Actual wheel installed into a clean temporary target, repeated without duplicates;
  fresh CLI processes resolved two distinct synthetic project mappings.
- Three isolated ephemeral Codex processes discovered the installed Skill and all
  four tools, confirmed two mappings and denied the unmapped project through MCP.
  Notebook-read requests were prepared, without dispatching live reads or queries.
- Doctor detected healthy/unhealthy cached configuration; repair restored damaged
  non-secret files and preserved synthetic authentication metadata.
- Uninstall removed unchanged owned components and preserved unrelated settings,
  maps, authentication metadata, external runtimes and an owner-modified runtime.
- Skill validator and shell syntax checks passed. Wheel inspection confirmed Skill
  and licenses and excluded user-specific paths and private installation/browser state.

Exact commands are in the guide. The sanitized review archive includes the final
source snapshot, wheel, full per-test JSON, package/Codex acceptance JSON and a
KN-OSS-04 preservation summary. SHA-256 is delivered alongside it.

No live Google request, research query, Keychain access or real user configuration
change was performed. The working version 0.4.0 installation remains in place and
its offline cached status is `BROWSER_DISCOVERY_VERIFIED`. Activation of 0.5.0 is a
separate explicit installation/migration operation using the documented preview.

Limits: initial connection on another computer remains a consented macOS pilot;
offline doctor does not verify open tabs or live session expiry; one outstanding
exact-question permit is retained per user; other Agent clients are unverified.
No Drive sync, source upload/refresh, daemon or new privilege subsystem was added.
