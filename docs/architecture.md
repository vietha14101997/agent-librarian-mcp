# Architecture and data contracts

catalog/model.py defines the provider-independent Document model. Every record
includes document_id, title, relative_path, content_sha256, source_identity,
source_version, document_kind, authority_status, curation_status, curation_evidence, disclosure_status,
related_document_ids, supersedes and last_indexed_revision. Explicit authority
also requires authority_evidence. Controlled enums include UNKNOWN/UNCLASSIFIED
so discovery never invents document type, authority or disclosure approval.

catalog/filesystem.py anchors a document root using POSIX descriptors.
catalog/operations.py creates metadata snapshots, checks hashes/relationships and
compares snapshots by stable ID. Scan outputs are deterministic and contain no
document bodies or timestamps. A curated manifest supplies durable identity
across rename/move/root relocation. Unmanaged discovery uses deterministic
root/path UUIDs: its identity is stable for repeated scans, not arbitrary renames.
No automatic hash-based identity merge is attempted when duplicates exist.

The native manifest/snapshot shape has schema_version=2, root_id and documents;
issues and duplicate-content groups are optional. Examples are complete fixtures.
v1 is migrated safely in memory with unknown curation. Scanner updates measured
hash/index revision, while preserving explicit authority.
A mismatch against a supplied manifest is retained as an issue requiring review.
Validate does not silently erase prior scan uncertainty.

catalog/osagent.py adapts the existing Library manifest's documents/id/path/
sha256/kind/authority/provenance fields without changing the Library. Explicit
HISTORICAL_REFERENCE maps to HISTORICAL; unrecognized authority remains UNKNOWN.
Missing disclosure information is always UNKNOWN. The adapter adds a global
disclosure-reconciliation issue and does not invent source identity links for
format adapters. A later curated manifest must resolve those gaps before planning.
The implementation has no OSAgent runtime or repository dependency.

policy/planner.py evaluates explicit curation acceptance independently of engineering
authority, then checks account, notebook mapping,
revision-bound disclosure approval, verified Drive revision, remote identity and
prior sync records. Its output is ADD_CANDIDATE, UPDATE_CANDIDATE, UNCHANGED,
BLOCKED_APPROVAL, BLOCKED_IDENTITY, BLOCKED_REVISION or REVIEW_REQUIRED.
execution_enabled is always false. Existing remote presence is not approval.
Unknown outcomes, stale registries and duplicate identities never mean success.
No delete, public sharing, publication, daemon or mutation executor exists.

providers/base.py defines a closed ResearchProvider and a future read-only remote
inventory contract. providers/fake.py implements four fixed synthetic operations
using a killable local worker and account handshake before request transmission.
No caller chooses an executable, module, profile, account or administrative method.
Future providers can use these contracts without changing catalog semantics.

gateway/policy.py and common.py retain KN-MCP-02's validation, projection and
permission checks. gateway/sdk.py delegates MCP transport to the official SDK
2.3.0, using its low-level Server to preserve exact schemas and structured errors.
The handler validates arguments explicitly even though they are advertised in
tools/list. SDK parsing/protocol errors may differ from the old custom transport;
adapted tests require rejection rather than the old private error-code convention.

Research policy is independent of catalog state. No file appearing in a catalog
automatically becomes an allowed remote source. All shipped allowlists and
approvals are synthetic examples. Remote citation revision attestation, live
Google transport and host-isolated credential deployment are unfinished, blocked work.

providers/ipc.py connects the existing gateway to providers/service.py over a
closed Unix protocol. Each endpoint verifies the other's kernel UID. The service
owns a separate policy object and startup-only synthetic store; it runs the same
strict validation independently. providers/gemini.py adapts four reviewed protocol
layouts through an injected transport, with only gemini_mock.py supplied. Neither
IPC nor a subprocess changes the OS principal automatically.

Catalog and research policy remain independent. Plans carry a policy fingerprint
for change detection and trusted_authorization=false. Future publication requires
an owner authority outside agent write access; no execution capability exists.
See knowledge-policy.md, ipc.md, gemini-adapter.md and host-setup.md for contracts.
