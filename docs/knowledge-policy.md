# Authority, curation and disclosure

These are independent decisions. None promotes another.

| Dimension | Meaning | Accepted values |
|---|---|---|
| Authority | Actual engineering status | UNKNOWN, DESIGN_PROPOSED, DEV_SELECTED, OWNER_APPROVED, STATIC_ACCEPTED, RUNTIME_VERIFIED, PRODUCTION_INTEGRATED, HISTORICAL |
| Curation | Suitability for the research collection | UNKNOWN, CANDIDATE, REVIEW_REQUIRED, ACCEPTED_FOR_RESEARCH, REJECTED |
| Disclosure | Permission to disclose externally | UNKNOWN, LOCAL_ONLY, REVIEW_REQUIRED, RECONCILIATION_REQUIRED, OWNER_APPROVED_FOR_EXTERNAL |

Curation evidence has exactly `decision_id`, `reviewer`, `content_sha256`,
`provenance` and `status`. Its status must agree with curation_status; acceptance
requires evidence. A stale evidence hash blocks planning. Evidence strings are
local declarations, not verified reviewer identities.

HISTORICAL, DESIGN_PROPOSED and DEV_SELECTED can be ADD_CANDIDATE with explicit
curation, disclosure and all identity/revision gates satisfied. Their authority
stays unchanged. PRODUCTION_INTEGRATED with LOCAL_ONLY stays blocked. Filenames,
dates, folders and Drive presence establish none of these decisions.

## Schema migration

Native catalogs now use schema_version=2. v1 remains readable through an in-memory
migration that preserves IDs, provenance, authority, disclosure and relationships,
adding curation_status=UNKNOWN and curation_evidence=null. No acceptance is
inferred. A v1 catalog already containing curation fields is ambiguous and rejected.
v2 requires both fields. Unknown classifications and conflicting evidence fail.

```sh
.venv/bin/librarian migrate --input examples/catalog.json --output state/catalog.v2.json
```

The input is never overwritten by migration. Scan emits v2; changes and validate
accept both versions. The OSAgent adapter emits v2 with unknown curation and
unknown disclosure requiring reconciliation. It does not modify the source
manifest or the real Library.

## Planning declarations and future authorization

The planner requires accepted curation, external disclosure, an unrevoked approval
ID bound to the content hash/account/notebook and drive+notebook scope, a unique
mapping, verified Drive revision and consistent known remote/prior identities.
It retains all seven action names. execution_enabled=false, remote_operations=0
and trusted_authorization=false apply even to eligible candidates.

policy_sha256 is a canonical JSON change detector. Supplying --policy-sha256
rejects a changed declaration. An attacker who can edit both values can bypass
this check. Editable JSON, its fingerprint and candidate plans do not authorize
publication. The future executor must consult an owner-controlled approval
authority outside agent write access, checking fresh revision/destination identity
and revocation at dispatch. Use a standard reviewed signing or protected service
mechanism; this version invents no custom cryptography and has no executor.
