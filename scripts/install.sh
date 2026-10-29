#!/bin/sh
# Persistent source environment; generic registration remains native to the host.
set -eu
project=$(pwd -P)
repo=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repo"
command -v uv >/dev/null 2>&1 || { echo 'Install uv first: https://docs.astral.sh/uv/getting-started/installation/' >&2; exit 2; }
client=generic
if [ "${1:-}" = '--client' ]; then
    client=${2:-}
    shift 2
fi
case "$client" in
    generic|codex) ;;
    *) echo 'Use --client generic (default), or --client codex for the optional receipt adapter.' >&2; exit 2 ;;
esac
uv sync --locked
if [ "$client" = codex ]; then
    uv build --wheel
    package_version=$(.venv/bin/python -c 'from importlib.metadata import version; print(version("agent-librarian-mcp"))')
    exec .venv/bin/librarian setup install --wheel "$repo/dist/agent_librarian_mcp-$package_version-py3-none-any.whl" "$@"
fi
exec .venv/bin/librarian setup contract --project "$project" "$@"
