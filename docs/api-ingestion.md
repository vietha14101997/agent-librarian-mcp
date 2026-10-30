# CLI file ingestion and bounded notebook research

This release adds a narrow consumer-file import CLI. It uses the selected managed Chromium/CDP session, or the retained
Brave compatibility account binding, with authenticated in-page API requests.
[Managed authentication](managed-chromium.md) documents selection and lifecycle. It requires no file picker, DevTools procedure, Drive,
cookie export or new MCP mutation tool. Upload compatibility is **offline tested;
live validation is pending**. Existing installations are not automatically updated.

## Protocol findings

Actual implementation reviewed at upstream commit
[`8ac9728ec5b128b05077e9d7c4c8bb11b5830c61`](https://github.com/jacob-bd/gemini-notebook-mcp-cli/tree/8ac9728ec5b128b05077e9d7c4c8bb11b5830c61):

- [`core/sources.py`](https://github.com/jacob-bd/gemini-notebook-mcp-cli/blob/8ac9728ec5b128b05077e9d7c4c8bb11b5830c61/src/notebooklm_tools/core/sources.py),
  `_register_file_source`, `_start_resumable_upload`, `_upload_file_streaming`,
  `add_file`, `get_notebook_sources_with_types`, `wait_for_source_ready` and
  `get_source_fulltext`.
- [`core/base.py`](https://github.com/jacob-bd/gemini-notebook-mcp-cli/blob/8ac9728ec5b128b05077e9d7c4c8bb11b5830c61/src/notebooklm_tools/core/base.py),
  upload URL, `o4cbdc` identifier and batchexecute form envelope.
- [`core/constants.py`](https://github.com/jacob-bd/gemini-notebook-mcp-cli/blob/8ac9728ec5b128b05077e9d7c4c8bb11b5830c61/src/notebooklm_tools/core/constants.py),
  consumer-file extension registry.

The second supplied LobeHub listing returned HTTP 403. The corresponding guessed
public GitHub repository returned not found, and that user's public repository
inventory did not contain a matching project. No implementation claims are taken
from that inaccessible listing, and no equivalent source was guessed or copied.

The reviewed upload sequence is:

1. POST `o4cbdc` through `/_/LabsTailwindUi/data/batchexecute`, with
   `source-path=/notebook/ID`. Parameters are `[[[filename]], ID, [2], options]`;
   options are `[1,null,null,null,null,null,null,null,null,null,[1]]`.
   The `wrb.fr` result's first nested value supplies the registered source ID.
2. POST `/upload/_/?authuser=0` with `x-goog-upload-command: start`,
   `x-goog-upload-protocol: resumable`, and
   `x-goog-upload-header-content-length: BYTE_COUNT`. The JSON body has
   `PROJECT_ID`, `SOURCE_NAME` and `SOURCE_ID`. The response header
   `x-goog-upload-url` supplies the session URL.
3. POST the unchanged file bytes to that URL with
   `x-goog-upload-command: upload, finalize` and `x-goog-upload-offset: 0`.
4. Independently read the notebook's source inventory and reconcile the actual
   source ID, exact title and processing status. Status 2 means ready; 1/5 mean
   in progress. Missing/unknown status is not success. Status 3 is terminal only
   for the known non-media types; ambiguous types remain pending.

Upstream uses cookie-authenticated HTTP. Agent Librarian instead retains the
existing in-page credentials, account attestation and CSRF/session/build form
fields; tokens are never exported. Returned session URLs are accepted only on
the active reviewed Notebook origin at `/upload/_/`, without credentials or fragments.
Cross-origin session URLs fail closed. Only the default consumer-account slot is
supported. No Enterprise, URL, Drive, replacement or deletion API is added.
Upstream's mutation retry/auth-recovery mechanisms are deliberately not used.

## CLI usage

Use the checkout's `.venv/bin/librarian` or its built wheel. Keep the recorded
installation home and state directory when they differ from platform defaults.
The project must already map to the explicitly selected notebook for execution.
Planning reads local files only and requires no authentication or mapping change.

```sh
# Directory preview; writes a reviewable manifest outside the source directory.
librarian sources plan --project /path/to/pilot --notebook-id NOTEBOOK_ID \
  --path /path/to/documents --output /path/to/import-plan.json

# Explicit path-derived names for repeated basenames; optional unchanged JSON adapter.
librarian sources plan --project /path/to/pilot --notebook-id NOTEBOOK_ID \
  --path /path/to/Library --relative-names --json-as-markdown \
  --output /path/to/import-plan.json

# Preview again, then execute only after owner authorization for these exact files.
librarian sources import --project /path/to/pilot --notebook-id NOTEBOOK_ID \
  --plan /path/to/import-plan.json
librarian sources import --project /path/to/pilot --notebook-id NOTEBOOK_ID \
  --plan /path/to/import-plan.json --approve

# One source: omission of --approve is an offline preview.
librarian sources add --project /path/to/pilot --notebook-id NOTEBOOK_ID \
  --path /path/to/notes.md --approve

# Local status; check performs one read-only live inventory reconciliation.
librarian sources status --project /path/to/pilot --notebook-id NOTEBOOK_ID \
  --plan /path/to/import-plan.json
librarian sources check --project /path/to/pilot --notebook-id NOTEBOOK_ID \
  --plan /path/to/import-plan.json
```

Default names retain each basename. Repeated basenames block the whole plan;
`--relative-names` explicitly encodes relative paths using `__`. JSON is not
assumed to be a supported file type: the optional adapter appends `.md` and wraps
the unchanged payload. Every entry records original and upload SHA-256 and size.
Markdown is sent byte-for-byte. The admitted upstream subset is `.md`, `.txt`,
`.pdf`, `.docx`, `.csv`, `.pptx`, `.epub`; admission does not guarantee processing.
Limits are 8 MiB/file, 100 files/import and journal, 32 MiB/import, and 1,000
filesystem entries. Execution also stops before the notebook would exceed the
existing research policy limit of 100 source identities. Symlinks/hardlinks and source drift are rejected. Unsupported
files and name conflicts are reported; only macOS metadata is silently excluded.

`COMPLETE` means all journaled source IDs were observed ready, not just that a
POST succeeded. `INCOMPLETE` requires inspection or another read-only `check`.
The journal is notebook/account scoped and may also include earlier batches.

## Reconciliation and resuming

Private 0600 journals live under `INSTALLATION_HOME/imports` in a 0700 directory.
Their lock serializes imports to a notebook across plans/processes. Directory
fsync and durable pre-dispatch states guard interrupted registration, upload
session creation and finalization. Session URLs remain private and are excluded
from normal CLI output. Do not publish or include these journals in reviews.

- A known completed filename/hash/source ID is reused. Changed bytes with the
  same journaled filename are blocked; no replacement is inferred.
- An existing remote title without a journaled hash is a conflict, not proof of
  identical content. No source is created to resolve it.
- Known registration/session state can resume after a purely local staging
  interruption, using the same source and session. File bytes are rechecked.
- `REGISTERING`, `STARTING` and `FINALIZING` states block further mutation even
  from another plan. Matching uncertain content hashes also block registration
  under a different filename. A read-only check can resolve a known finalized ID to ready.
  Unknown registration candidates are reported by ID/title/diff for review;
  they are never automatically adopted, deleted or re-registered. Unknown
  registration or session-start outcomes can require owner-led recovery outside
  this minimal CLI. There is no force/retry switch that discards replay guards.

After an accepted inventory read, the target notebook's discovery source cache
is updated for subsequent mapped MCP reads. No project allowlist or query permit
is created or changed. Source mutations remain outside the four research tools.

## Large notebook handling

The old Brave reader buffered an entire ordinary response up to 128 KiB and an
entire query stream up to 2 MiB. The HTTPS path still applied 128 KiB to queries.
Repeated streamed answer/citation frames could exceed those aggregate limits
with a small final answer. Large `rLM1Ne` metadata could exceed the ordinary bound
before its unused fields were discarded. These request paths and threshold
failures are reproduced with bounded synthetic fixtures; the old pilot's raw
responses were not retained, so their actual framing/byte counts are unknown.

New readers process UTF-8 incrementally and release processed frames. RPC
correlation and error envelopes are checked; unused notebook/source metadata is
projected away, and only completed query evidence is retained. No thinking-only
answer is accepted. The memory/work budgets are independent: 2 MiB/frame,
256 frames, 64 MiB total wire input, depth 24, 100,000 nodes/frame, and the existing
128 KiB projected result boundary (2 MiB internal source envelope before paging).
The frame budget reuses the previous stream bound; the total wire budget permits
repeated progress without retaining it. Oversized individual frames remain errors.
This is bounded frame parsing, not arbitrary-size JSON token streaming.

The reviewed `hizoJc` content-block layout is unchanged. Its former 16,000-character
text field rejected larger valid indexed text. Source decoding now accepts a
bounded text body, redacts before slicing, and returns explicit pages:

```json
{"notebook_id":"NOTEBOOK_ID","source_id":"SOURCE_ID","offset":0,"max_chars":16000}
```

`librarian_get_source` includes `total_chars`, `offset`, `truncated`, `next_offset`.
Follow `next_offset` until null. Offsets address the sanitized text, not raw bytes;
revision identity is not attested between pages. No tool is added. The research
CLI also accepts `research source --offset N --max-chars N`. The service/IPC path
preserves pagination across both gateway boundaries.

The three pilot originals (execution-receipt Markdown adapter, execution-receipt
JSON, catalogue JSON) all exceed 16,000 characters and reproduce the old error in
the reviewed shape. A targeted live read-only trace could not reach Brave
(`BRAVE_AUTOMATION_UNAVAILABLE`); consequently no different live response shape
has been verified, and no speculative layout relaxation was added. Live upload,
large-notebook query and those three source reads remain acceptance gates.
