# MCP agent setup

The tested client is the official Python MCP SDK 2.3.0 over stdio, on this macOS
host. Codex, Claude Code, Gemini CLI and other MCP hosts are intended clients;
no host-specific interoperability has been verified. Their configuration formats
and security semantics must be checked against their current official documentation
before registration. This milestone changes no active host configuration.

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
