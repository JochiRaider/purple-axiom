<!-- docs/mappings/osquery_to_ocsf_1.7.0.md -->

# osquery → OCSF 1.7.0 Mapping Profile (v0.1)

## Status

Draft (v0.1 target)

## Purpose

This document defines the **osquery** mapping profile for Purple Axiom’s OCSF v1.7.0 normalizer.

It is designed to be:

- implementable (rules are explicit and deterministic)
- reviewable (humans can validate class and field intent)
- testable (fixtures can assert routing, semantics, and coverage)

The machine-executable mapping rules referenced by this document live under:

- `mappings/normalizer/ocsf/1.7.0/osquery/**`

## Scope

In scope (v0.1):

- osquery **scheduled query results** in NDJSON event format (`osqueryd.results.log`)
- Routing by `query_name` (`name` in osquery results)
- The v0.1 routed tables required by the coverage matrix fixture minimum:
  - `process_events` (process activity)
  - `socket_events` (network activity)
  - `file_events` (file system activity)

Out of scope (v0.1):

- osquery status logs (`INFO|WARNING|ERROR|FATAL`)
- osquery batch formats (unless explicitly enabled and fixture-covered)
- Full coverage of all osquery tables and platform-specific event families

## Mapping stance: OCSF-core plus Purple pivots

This profile follows the project’s “OCSF-core plus pivots” strategy:

1. **OCSF-native primary fields MUST be populated** when authoritative source values exist.
1. **Convenience pivots MAY be populated** to support cross-source joins, but MUST NOT conflict with
   OCSF-native values.

Constraints (normative):

- The mapping MUST NOT infer values (no synthesis from unrelated fields).
- If a value is not authoritative, the field MUST be absent (not null, not empty string).
- If multiple possible inputs exist, the profile MUST define a stable precedence order.

### Device IP representation

The v0.1 coverage matrix allows either `device.ip` or `device.ips[]` to satisfy the “device IP
pivot”. This profile SHOULD prefer `device.ips[]` for consistency and multi-IP representation.

- If only one IP is authoritative, emitting `device.ip` alone is permitted, but implementations
  SHOULD also emit `device.ips[] = [device.ip]` when supported (sorted, de-duplicated).

## Inputs and prerequisites

This profile assumes the canonical osquery ingestion and staging defined in:

- `docs/spec/042_osquery_integration.md` (telemetry + raw staging + identity basis)
- `docs/spec/050_normalization_ocsf.md` (pinned OCSF version, envelope requirements, coverage
  artifacts)
- `docs/spec/055_ocsf_field_tiers.md` and `docs/mappings/coverage_matrix.md` (tier semantics and CI
  conformance)

### Expected raw input shape

The normalizer is expected to receive osquery scheduled results lines containing:

- `name` (string) and/or `osquery.query_name` (string): the query identifier for routing
- `hostIdentifier` (string) and/or `osquery.host_identifier` (string)
- `unixTime` (string) and/or `osquery.unix_time` (string)
- `action` (string) and/or `osquery.action` (string): `added | removed | snapshot`
- exactly one of:
  - `columns` (object)
  - `snapshot` (array of objects)

The mapping MUST NOT depend on locale-specific fields such as `calendarTime` for identity, ordering,
or routing.

## Canonicalization rules (determinism)

Canonicalization is applied prior to mapping and hashing.

### Strings

- MUST be trimmed of leading/trailing whitespace.
- MUST preserve original case unless a field is explicitly case-normalized below.

### Integers represented as strings

Some osquery fields are string-typed numbers (for example `unixTime`).

- Numeric strings MUST be parsed as base-10 integers when required by the OCSF target field type.
- If parsing fails, the target field MUST be absent and the raw value MUST be preserved under
  `unmapped.osquery`.

### Paths

- Windows paths MAY contain `\`; POSIX paths contain `/`.
- When deriving `name` from a path, the basename algorithm MUST:
  - treat both `\` and `/` as separators
  - ignore trailing separators
  - return the final non-empty segment
- When splitting `file.parent_folder` and `file.name`, the split MUST:
  - be deterministic
  - treat both `\` and `/` as separators
  - set `file.name` to basename, and `file.parent_folder` to the remaining prefix (if any)

### IP addresses and ports

- IPs MUST be emitted in normalized textual form.
- Ports MUST be emitted as integers when parseable; otherwise absent.

## Classification and identifiers

### OCSF version pinning

- This profile targets `ocsf_version = "1.7.0"` and expects the run to record that pin in
  provenance.

### Class routing

Routing is based on the osquery `query_name` (`name` in the results log).

The routing table is normative and versioned in:

- `mappings/normalizer/ocsf/1.7.0/osquery/routing.yaml` (MUST validate against
  `bridge_router_table.schema.json` or an equivalent routing schema)

v0.1 required routes:

| `query_name`     | OCSF target class    | `class_uid` | `category_uid` |
| ---------------- | -------------------- | ----------: | -------------: |
| `process_events` | Process Activity     |        1007 |              1 |
| `file_events`    | File System Activity |        1001 |              1 |
| `socket_events`  | Network Activity     |        4001 |              4 |

Category UID values (OCSF 1.7.0):

- `1` = System Activity
- `4` = Network Activity

Unrouted behavior (normative):

- The normalizer MUST NOT guess a `class_uid` for an unknown `query_name`.
- Unknown `query_name` rows MUST be preserved in `raw/` and MUST be counted as unrouted/unmapped in
  `normalized/mapping_coverage.json`.

### OCSF classification fields

For every emitted event, the normalizer MUST set:

- `class_uid`
- `activity_id`
- `type_uid`

Rules:

- `type_uid` MUST be computed as: `class_uid * 100 + activity_id`.
- `category_uid` SHOULD be set when known for the class.
- `severity_id` MAY be set if an authoritative mapping exists; otherwise it MUST be absent.
- For `action = "snapshot"` rows, `activity_id` MUST be `99` (Other) because snapshot rows represent
  point-in-time state observations rather than discrete activity events. This aligns with
  `042_osquery_integration.md` "Known Mapping Limitations".

### Event identity and `metadata.uid`

osquery does not provide a stable record id. Therefore osquery-derived `metadata.event_id` is Tier
3\.

Normative requirements (per ADR-0002 and `055_ocsf_field_tiers.md` Tier 0):

- `metadata.uid` MUST be present and MUST equal `metadata.event_id`.
- `metadata.event_id` MUST be computed from the osquery identity basis defined below.

`metadata.event_id` MUST be computed from the osquery identity basis:

```json
{
  "source_type": "osquery",
  "host_identifier": "<hostIdentifier>",
  "query_name": "<name>",
  "action": "<action>",
  "unix_time": <unixTime_int>,
  "payload": <columns_or_snapshot_canonical_json>
}
```

Rules (normative):

- `payload` MUST be canonical JSON (RFC 8785 JCS) for `columns` or `snapshot`.
- `calendarTime` MUST NOT be included.

Recommended `metadata.source_event_id` (normative if emitted):

- Because osquery has no upstream record id, implementations SHOULD set:

  - `metadata.source_event_id = "osquery:" + <event_id>`
  - or a stable basis string derived from the identity basis (but MUST NOT be run-local).

### Snapshot expansion rule (required)

When `action == "snapshot"` and the record contains a `snapshot` array:

- The normalizer MUST emit one normalized event per snapshot row.

- The expansion MUST be deterministic:

  - Each snapshot row MUST be canonicalized to JCS bytes.
  - Rows MUST be sorted by lexicographic ordering of their JCS byte sequences prior to emission.

- Each emitted event MUST use `payload = <row_object_canonical_json>` in the identity basis.

- The full original snapshot array MUST still be preserved under `unmapped.osquery.raw_json`.

## Field mapping: shared (all osquery events)

This section defines baseline field population rules that apply to all routed osquery records.

### Metadata (source provenance)

At minimum:

- `metadata.product.name` SHOULD be `osquery`.
- `metadata.source_type` MUST be `osquery`.
- `metadata.source_event_id` SHOULD be set per the recommendations above.
- Any collector or pipeline instance identifiers MAY be recorded in `metadata`, but MUST NOT
  participate in event identity hashing.

### Device

Device identity for osquery MUST be deterministic and SHOULD be consistent with other sources.

Rules:

- `device.hostname` SHOULD be populated from `host_identifier` when it is a hostname-like value.
- `device.uid` MUST be populated from deterministic run context when available (recommended:
  resolved `asset_id` from the inventory snapshot). If `device.uid` cannot be resolved
  deterministically, it MUST be absent rather than guessed.
- `device.ip` / `device.ips[]` MAY be populated only when an authoritative device IP exists in
  deterministic run context (example: inventory snapshot) or in the raw record (rare for osquery
  tables). If multiple IPs exist, they MUST be emitted sorted and de-duplicated.

### Actor user

osquery tables may provide numeric user IDs and, depending on configuration, user names.

Rules:

- If an authoritative numeric UID exists in the row:

  - `actor.user.uid` SHOULD be populated using the base-10 string form of that UID.

- If an authoritative user name exists in the row:

  - `actor.user.name` SHOULD be populated as provided (trimmed).

- UID to name resolution MUST NOT perform external lookups. If the project supports UID to name
  mapping, it MUST be derived only from a deterministic, snapshotted local context.

### Raw retention and unmapped preservation (`unmapped.*` namespace)

For every routed osquery record, the normalizer MUST preserve:

- `unmapped.osquery.query_name`
- `unmapped.osquery.action`
- `unmapped.osquery.columns` or `unmapped.osquery.snapshot` (whichever was present)
- `unmapped.osquery.raw_json` (the original object, or a redacted-safe representation)

Namespace rationale:

- This profile uses `unmapped.<source_type>.*` rather than `raw.*` to clearly indicate that these
  fields were not mapped to OCSF-native fields (as opposed to being intentionally retained raw
  evidence).
- The `unmapped` namespace aligns with `050_normalization_ocsf.md` "route unmapped fields into an
  explicit `unmapped` / `raw` object so nothing is silently dropped".
- Implementations MAY additionally populate `raw.*` for forensic evidence retention if the project
  requires both namespaces.

## Routed event families (v0.1)

This section defines the v0.1 required osquery routes and their minimal field mapping obligations.

### 1) `process_events` → Process Activity

Class:

- Process Activity (`class_uid = 1007`)

Activity mapping (normative):

- The mapping pack MUST define an explicit `activity_id` mapping keyed by:

  - `action` (`added|removed|snapshot`)
  - and, if needed, additional table-specific fields.

- If no explicit mapping applies, `activity_id` MUST be `0` (Unknown) rather than guessed.

Minimum mapping obligations (when authoritative values exist):

- `actor.process.pid` MUST be populated when `pid` is present and parseable.

- `actor.process.parent_process.pid` SHOULD be populated when `ppid` is present and parseable.

- `actor.process.cmd_line` SHOULD be populated when `cmdline` is present and permitted by redaction
  policy.

- `actor.process.name` MUST be populated when a process path is present by applying the
  deterministic basename algorithm to the authoritative executable path.

  - If no path is present, `actor.process.name` MUST be absent.

Redaction note:

- Any command-line fields MUST be filtered by the effective redaction policy before emission.

### 2) `socket_events` → Network Activity

Class:

- Network Activity (`class_uid = 4001`)

Activity mapping (normative):

- The mapping pack MUST define an explicit `activity_id` mapping based on:

  - `action`
  - and, when authoritative, connection direction semantics present in the table backend.

- If direction cannot be determined authoritatively, `activity_id` MUST be `0` (Unknown).

Endpoint mapping (normative, when authoritative values exist):

- For socket tables that expose local and remote endpoints:

  - `src_endpoint.*` MUST represent the local endpoint.
  - `dst_endpoint.*` MUST represent the remote endpoint.

- `src_endpoint.ip` MUST be populated when an authoritative local address exists.

- `dst_endpoint.ip` MUST be populated when an authoritative remote address exists.

- Ports SHOULD be populated when parseable.

Process attribution:

- If the table exposes `pid`, then `actor.process.pid` MUST be populated when parseable.
- `actor.process.name` SHOULD be derived from an authoritative process path when available;
  otherwise absent.

### 3) `file_events` → File System Activity

Class:

- File System Activity (`class_uid = 1001`)

Known limitation (normative):

- Initiating process attribution is not available from `file_events` in v0.1.

  - Therefore `actor.process.*` is `N/A` for this route and MUST NOT be inferred.

Minimum mapping obligations (when authoritative values exist):

- `file.name` MUST be populated from the target file path using the deterministic basename
  algorithm.

- `file.parent_folder` MUST be populated from the target file path using the deterministic split
  rule.

- `actor.user.uid` SHOULD be populated when an authoritative UID exists in the row.

- `activity_id` MUST be derived only from explicit `file_events` action indicators in the row.

  - Unknown action tokens MUST map to `activity_id = 0` (Unknown).

## Applicability and coverage

This profile is designed to work with the applicability-aware coverage model defined by:

- `docs/mappings/coverage_matrix.md`

Normative conformance requirements:

- Fields are only required when authoritative values exist.
- Fields marked `N/A` for osquery routes (example: `actor.process.*` for `file_events`) MUST remain
  absent.

## Verification hooks (CI)

Minimum conformance tests for this profile:

1. Routing tests:

   - Given raw fixtures for each v0.1 `query_name`, the normalizer MUST select the expected
     `class_uid`.

1. Determinism tests:

   - Re-running normalization on the same raw fixture MUST produce byte-identical normalized JSON
     after canonicalization and stable ordering.

1. Coverage tests:

   - Coverage computation MUST treat non-authoritative fields as “not applicable” and MUST NOT count
     them as missing.
   - Tests MUST assert that `N/A` fields remain absent.

Minimum fixture set (aligned to the coverage matrix CI requirements):

- Raw fixtures: `tests/fixtures/raw/osquery/**`

  - includes at least:

    - 1 `process_events` record
    - 1 `socket_events` record
    - 1 `file_events` record

- Golden normalized outputs:

  - `tests/fixtures/normalized/ocsf/1.7.0/osquery/**`

## Known limitations (v0.1)

- `file_events` lacks initiating process attribution. Any detections requiring actor process context
  for file writes MUST use a different source (example: audit-based process file events) rather than
  inferring from `file_events`.
- Port availability for `socket_events` depends on the backend. Ports should be treated as optional
  unless the raw provides them.
- Identity is Tier 3 and depends on payload canonicalization. Large snapshot payloads may increase
  hashing cost; implementations SHOULD ensure canonicalization is bounded and observable (metrics),
  without changing identity semantics.
