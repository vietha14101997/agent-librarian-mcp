#!/bin/sh
# Source-checkout entrypoint. uv creates dependencies; setup owns registration.
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repo"
command -v uv >/dev/null 2>&1 || { echo 'Install uv first: https://docs.astral.sh/uv/getting-started/installation/' >&2; exit 2; }
uv sync --locked --python 3.12
uv build --wheel
exec .venv/bin/librarian setup install --wheel "$repo/dist/agent_librarian_mcp-0.5.0-py3-none-any.whl" "$@"
