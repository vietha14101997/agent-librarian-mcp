# Codex gateway example and verification scope

examples/codex.service.disabled.toml points only to the restricted MCP gateway.
It uses documented command/args, enabled=false and the four-tool enabled_tools
allowlist from [official OpenAI MCP documentation](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).
It contains no credential/profile/helper/store input and does not register the
upstream MCP server. No active Codex global configuration was read for secrets or
modified. Only its metadata was checked for preservation.

The actual official Python SDK client -> stdio gateway -> Unix provider service ->
source-derived HTTP transport -> adapter path is tested using synthetic HTTP and
credentials. This is MCP transport evidence, not actual Codex-host integration or
live Google verification. The running Codex app is not separately registered or
certified by those tests. Host setup, login capture, account/notebook approval and
live gates remain open. Do not enable the example until those applicable deployment
checks are accepted. Claude Code, Gemini CLI and other hosts remain untested.
