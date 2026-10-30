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

### KN-OSS-03 wire/session adaptation

providers/https_transport.py additionally adapts core/base.py _build_request_body,
_build_url, _parse_response, _extract_rpc_result and core/conversation.py query
form envelopes at the same pinned commit. providers/session.py adapts token and
negative session-ID fields from core/auth.py and core/base.py and only the internal
oPEP7c account field from utils/cdp.py. utils/config.py establishes the two consumer
host names. Copyright remains (c) 2025 Jacob Ben David, MIT.

Modifications: fixed allowlisted hosts/operations; standard verified TLS; strict
size/type/encoding/correlation checks; no redirect, retry, arbitrary endpoint,
raw-response dump, environment override, cookie rotation or browser recovery.
Account extraction rejects absent/ambiguous internal fields instead of generic
email guessing. No upstream auth store, browser/CDP helper or unrestricted runtime
is imported. The original MIT notice below covers these adaptations and is shipped
in wheel metadata. No independent third-party browser code was copied.

On 2026-10-29 selected core/base.py, core/auth.py, core/conversation.py,
utils/cdp.py and utils/config.py current public bytes matched the pinned copies.
The current changelog and four published advisories were reviewed. Negative SID,
signed-out HTTP 200 and stale credential mirror corrections informed safe behavior;
no mirrors/fallback stores are implemented here. No repository-wide audit or live
compatibility is implied. Keychain Swift source uses Apple's standard Security API;
it is project-written, not copied from upstream. Credential capture is not supplied.

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

## KN-OSS-04 Personal Local authentication

personal/browser_auth.py adapts the managed-profile polling, allowed Notebook host,
secure-cookie selection and known account/CSRF/session/build-field behavior from
upstream utils/cdp.py and core/auth.py at the same pinned revision
8ac9728ec5b128b05077e9d7c4c8bb11b5830c61. Copyright (c) 2025 Jacob Ben David, MIT;
the full upstream notice above remains applicable. It excludes upstream profile
search, existing-browser attachment, public CDP ports, cookie databases, plaintext
stores, browser recovery and unrestricted CLI/MCP runtime.

Browser lifecycle/pipe transport uses optional Playwright Python 1.64.1 (Microsoft,
Apache-2.0), with pyee and greenlet locked in uv.lock. It is a dependency, not copied
source. The installed distribution retains its licenses and bundled component
notices. No bundled browser download or Playwright MCP endpoint is launched.
Dedicated-profile application policy, lifecycle receipts and the Personal Local
Keychain helper are project code. No custom browser automation protocol or custom
cryptography was introduced. Custom Brave compatibility still requires local tests.

## Scoped Brave pilot cookie-format support

personal/brave_cookie_bridge.swift uses Apple's Security/CommonCrypto/CryptoKit APIs
for Chromium's documented v10 PBKDF2-HMAC-SHA1/AES-128-CBC format and schema-24 host
binding. Reference: components/os_crypt/os_crypt_mac.mm at ec82d4ab8 (blob
66f77c296754393677dac5350cf3b1b2e35d37ac), copyright 2014 The Chromium Authors;
net/extras/sqlite/sqlite_persistent_cookie_store.cc (reviewed blob
bb61afb851aaf7ef28aa5e705d329bb31bc2e164), copyright 2012 The Chromium Authors.
Local adaptations restrict exact approved names/hosts, reject unknown encryption,
check the domain hash, keep the key in a short-lived helper and omit plaintext
fallback, DB copies/profile writes, key persistence and unrestricted browser access.

The browser_cookie3 Brave mapping was consulted for the exact Brave Safe Storage /
Brave Keychain item. Its general browser reader was not copied or installed; its
whole-database copy fallback was excluded. This is a personal pilot, not the future
public default. No new cryptographic construction or unrestricted upstream runtime
was introduced.

### Chromium BSD notice

// Copyright 2015 The Chromium Authors
//
// Redistribution and use in source and binary forms, with or without
// modification, are permitted provided that the following conditions are
// met:
//
//    * Redistributions of source code must retain the above copyright
// notice, this list of conditions and the following disclaimer.
//    * Redistributions in binary form must reproduce the above
// copyright notice, this list of conditions and the following disclaimer
// in the documentation and/or other materials provided with the
// distribution.
//    * Neither the name of Google LLC nor the names of its
// contributors may be used to endorse or promote products derived from
// this software without specific prior written permission.
//
// THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
// "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
// LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
// A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
// OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
// SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
// LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
// DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
// THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
// (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
// OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

## KN-OSS-04 native Brave RPC transport

personal/brave_rpc.js adapts the in-page fetch/form construction from upstream
core/cdp_transport.py and core/base.py at the same reviewed commit
8ac9728ec5b128b05077e9d7c4c8bb11b5830c61. Copyright (c) 2025 Jacob Ben David, MIT;
the full notice above applies. The upstream debugger lifecycle is not included.
The local bridge uses native Brave Apple Events, a pinned Notebook homepage, an
account check and existing four-operation request validation. It keeps page tokens
in the browser and returns only bounded RPC data. The optional metadata decoder
and streamed-query framing likewise follow the reviewed notebook/conversation
layouts. No unrestricted upstream runtime or browser debugger is installed.

## CLI-only experimental notebook creation

personal/notebook_admin.py adapts the create parameters and returned ID layout from
upstream core/notebooks.py:create_notebook, and the CCqFvf identifier from
core/base.py, at the same pinned commit
`8ac9728ec5b128b05077e9d7c4c8bb11b5830c61` of
https://github.com/jacob-bd/gemini-notebook-mcp-cli. The MIT notice above applies.
personal/brave_create.js reuses the attributed native fetch program with a separate
closed discovery/create contract. No upstream retry, account switching or auth
recovery is included. Research MCP and its browser program retain their four-tool
read/research restriction. Creation is not live-verified; normal onboarding offers
manual creation and explicit ID linking.

### v0.7 file-ingestion protocol review

`personal/source_admin.py` and `personal/brave_upload.js` adapt the registration
parameters, resumable-start JSON/headers, finalization headers, source ID layout
and processing status/type positions in `core/sources.py`, `core/base.py` and
`core/constants.py` at the same pinned Jacob Ben David revision above (MIT).
The upstream file notes its resumable-upload implementation was adapted from
notebooklm-py. This change reconstructs the reviewed wire contract; it imports no
upstream runtime. Local changes add browser-local credential handling, same-origin
session validation, bounded staging and durable no-replay import journals; upstream
mutation retries and auth recovery are not reused. The existing upstream MIT
notice applies to these adaptations. The incremental framing and journal code
are local implementations. See `docs/api-ingestion.md` for exact source links and
the inaccessible second reference; no code was taken from that listing.

## KN-OSS-08 managed Chromium/CDP

Current upstream was re-inspected on 2026-10-30 at the same revision
`8ac9728ec5b128b05077e9d7c4c8bb11b5830c61`. Byte comparisons of current main
against pinned sources and source hashes are recorded in review evidence.
`personal/managed_browser.py`, `managed_auth.py` and `managed_transport.py`
selectively apply dedicated-profile ownership, CDP lifecycle, headless reuse,
functional discovery validation and browser-context fetch patterns from upstream
`utils/cdp.py`, `core/auth.py`, `core/cdp_transport.py` and `core/base.py`.
The existing Jacob Ben David MIT attribution and complete notice above apply.
The upload/source/conversation layouts were re-reviewed in `core/sources.py` and
`core/conversation.py`; no upstream runtime or unrestricted APIs are imported.
Local changes keep cookies in Chromium, use OS-assigned loopback ports, restrict
health retries, preserve mutation/query replay barriers, stream bounded projection
and retain citations on equal-length final answers.

Chromium is an independently downloaded executable dependency, never bundled in
the wheel or review archive. Its distribution carries its own licenses/notices.
Playwright remains the pinned optional Apache-2.0 client dependency.
