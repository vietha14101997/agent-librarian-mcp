# MCP agent setup

Codex is the first supported client for the install-once Personal Local Skill and
project-aware MCP registration. The KN-OSS-05 package acceptance script verifies
fresh ephemeral Codex discovery and all four tools using synthetic cached state,
without model turns, authentication or Google requests. See the
[installation guide](skill-installation.md). The official Python MCP SDK 2.3.0
stdio client is also covered by regression tests.

Claude Code, Gemini CLI and other MCP hosts remain unverified. They can reuse the
provider-neutral mapping resolver and runtime, but need a separately verified
Skill/MCP registration adapter. The advanced restricted-service template below
is separate from the ordinary Personal Local installer.

All hosts should launch the same absolute command with an argument array:

```text
/ABS/venv/bin/librarian mcp-serve --provider service
  --policy /ABS/front-policy.json --service-socket /SHORT/service/research.sock
  --service-uid SERVICE_NUMERIC_UID --client-id research-client
  --control-dir /ABS/front-control
```

This is a command/argument template, not shell code or a host configuration file.
Do not pass a canary store, authentication profile or credentials to the gateway.
Use the fake provider demo for development; use gemini-mock service only for
synthetic IPC testing. examples/codex.disabled.toml remains a disabled illustrative
configuration, not registration or a compatibility claim. Enable a server only
after reviewing its four-tool registry and deployment boundaries. MCP host tool
approval does not isolate credentials from an agent that can run shell commands.
