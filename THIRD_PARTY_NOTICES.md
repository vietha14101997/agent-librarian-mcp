# Third-party provenance and notices

## Selective reconstruction

The owner authorized reconstruction of local KN-MCP-02 artifacts into this
independent project. Those artifacts had no separate public Git repository or
commit: commit provenance is NOT_APPLICABLE; source hashes identify the input.
The project MIT license covers this owner-authorized adaptation.

| New component | Original local artifact/component | Modification | Known limitation |
|---|---|---|---|
| gateway/common.py | KN-MCP-02 gateway/server.py policy primitives and schemas | Move into package; retain strict checks and redaction | Text scrubbing is not a universal secret detector |
| gateway/policy.py | KN-MCP-02 gateway/server.py Gateway | Retain validation/projection; dispatch four explicit ResearchProvider methods | Same-UID processes are not credential isolation |
| providers/fake.py | KN-MCP-02 gateway/server.py FakeBoundary | Fixed worker path in package; explicit read/query methods | Synthetic handshake, no Google account attestation |
| providers/worker.py | KN-MCP-02 gateway/fake_worker.py | Package resource location; synthetic behavior retained | No real knowledge provider |
| tests/test_gateway.py and fixtures | KN-MCP-02 tests/test_gateway.py and synthetic fixture/policy | Installed-package subprocess entry; adapt SDK protocol rejection codes | Only tested transports/platforms are supported evidence |

Input file SHA-256 values:

- gateway/server.py: `9a5bb9ae701eeab1a326ca1b93fd52dea516f93aa3e8d63cede748dfeba03dfd`
- gateway/fake_worker.py: `16b071cb7e7217c7bfa9aedb5bb362d71930e92a1f60a9b7994e8d103ba3eb88`
- tests/test_gateway.py: `32fcdb8938287e5caa239dd9eedfba4404cbd4d1fe1dbe2ee3e9e3ce4e81d56c`

The KN-MCP-02 hand-written JSON-RPC transport was not copied into the running
server. Official MCP SDK 2.3.0 replaces it now that an isolated compatible Python
interpreter is available; the tested policy was retained rather than rebuilt.

## Gemini Notebook selective source adaptation

Repository: https://github.com/jacob-bd/gemini-notebook-mcp-cli
Pinned commit: `8ac9728ec5b128b05077e9d7c4c8bb11b5830c61` (0.15.8).
Copyright (c) 2025 Jacob Ben David; MIT notice retained below.

Local providers/gemini.py adapts protocol constants, positional response layouts
and bounded text/citation extraction from these original paths:

| Original path under src/notebooklm_tools | Adapted detail |
|---|---|
| core/base.py | Three read RPC identifiers and query endpoint |
| core/notebooks.py | list_notebooks/get_notebook request parameters and row fields |
| services/notebooks.py | Wrapped notebook metadata normalization |
| core/conversation.py | Query parameters, wrb.fr parsing, source references and cited text |
| core/sources.py | get_source_fulltext parameters and nested indexed-text extraction |

Local modifications: injected transport/account capability; four explicit methods;
strict bounded schemas/identities/allowlists; safe errors; no thinking fallback,
raw logs, tables, live HTTP envelopes or auth discovery. gemini_mock.py constructs
synthetic source-shaped fixtures for tests, not captured Google success responses.
No upstream executable module, unrestricted client, CLI/auth/profile subsystem,
sharing, download or administrative helper is installed/imported.

The 2026-10-29 review rechecked the five selected files against publicly fetched
main bytes: all matched the pinned files. Repository-wide GitHub compare failed
and remains NOT_VERIFIED. Current CHANGELOG described unreleased CI checksum/
certificate changes and 0.15.8 signed-out/session fixes outside the adapted parsers.
This limited review does not establish that all later security fixes are absent.
No floating branch code was merged; re-review before any live transport.

Earlier advisory review covered response-log redaction
[GHSA-jhrc-qgxv-3c2g](https://github.com/jacob-bd/gemini-notebook-mcp-cli/security/advisories/GHSA-jhrc-qgxv-3c2g),
authenticated HTML dumps
[GHSA-747w-q55c-m74m](https://github.com/jacob-bd/gemini-notebook-mcp-cli/security/advisories/GHSA-747w-q55c-m74m),
external binding/cleanup
[GHSA-v558-4774-r6wq](https://github.com/jacob-bd/gemini-notebook-mcp-cli/security/advisories/GHSA-v558-4774-r6wq),
and download writes
[GHSA-92q4-9x75-55rf](https://github.com/jacob-bd/gemini-notebook-mcp-cli/security/advisories/GHSA-92q4-9x75-55rf).
Those paths are excluded. Safe projection, no raw response logging, no TCP and no
downloads address analogous surfaces, not production certification. Live account
attestation and complete wire compatibility remain unverified.

### Upstream MIT notice

MIT License

Copyright (c) 2025 Jacob Ben David

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## MCP SDK dependency

The official modelcontextprotocol/python-sdk is installed as mcp==2.3.0, under MIT.
It is not vendored. uv.lock records exact runtime dependency versions and artifact
hashes; pyproject.toml pins the build backend flit_core==3.12.0. Dependency licenses
remain with their distributions. This notice does not imply a complete dependency
vulnerability or redistribution audit.

### SDK MIT notice

MIT License

Copyright (c) 2024 Anthropic, PBC

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
