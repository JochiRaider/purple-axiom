---
title: osquery integration (telemetry and normalization)
description: Defines v0.1 osquery ingestion, staging, normalization, and conformance requirements.
status: draft
category: spec
tags: [telemetry, osquery, ingestion, normalization, ocsf]
related:
  - 040_telemetry_pipeline.md
  - 050_normalization_ocsf.md
  - 045_storage_formats.md
  - 120_config_reference.md
  - ADR-0002-event-identity-and-provenance.md
---

# osquery integration (telemetry and normalization)

## Overview

This document defines the v0.1 integration path for osquery as a telemetry source.

- Canonical continuous monitoring output format.
- OpenTelemetry Collector ingestion.
- Raw staging layout in the run bundle.
- Minimal, deterministic normalization to OCSF, including routing semantics.

## Canonical osquery output format (continuous monitoring)

### Required: filesystem logger in event format NDJSON

When osquery is enabled, collectors MUST ingest the osquery scheduled query results log emitted by
`osqueryd` using the filesystem logger.

Canonical format (v0.1):

- One JSON object per line (NDJSON).
- Each line MUST include `name` (string), `hostIdentifier` (string), `unixTime` (string), and
  `action` (string: `added`, `removed`, or `snapshot`).
- `unixTime` MUST be a base-10 integer string representing epoch seconds (UTC) and MUST be parseable
  to a signed 64-bit integer. Fractional seconds MUST NOT be used.
- If `action` is `added` or `removed`, the line MUST include `columns` (object) and MUST NOT include
  `snapshot`.
- If `action` is `snapshot`, the line MUST include `snapshot` (array of objects) and MUST NOT
  include `columns`.

Non-canonical forms:

- Status logs (`INFO`, `WARNING`, `ERROR`, `FATAL`) are not part of the results stream and MUST NOT
  be mixed into the results log stream.
- Batch result formats MAY be supported later, but are out of scope for v0.1 unless explicitly
  enabled and covered by fixtures.

### Timestamp handling

- The normalizer MUST parse `unixTime` as a base-10 integer epoch seconds value (`unix_time_s`).
  - If parsing fails (non-integer, missing, overflow), the record MUST be treated as an ingest/parse
    error and MUST NOT produce a normalized event.
- The normalizer MUST derive `time` as epoch milliseconds with zeroed sub-second precision:
  `time = unix_time_s * 1000`.
- The normalizer MUST set `metadata.time_precision = "s"` for osquery-derived normalized events.
- The normalizer MUST treat `calendarTime` as non-authoritative and MUST NOT use it for identity or
  ordering.
- If an observation timestamp is available from ingestion, the normalizer MAY record it as
  `metadata.ingest_time_utc` (RFC3339 UTC string), but `metadata.event_id` MUST NOT incorporate
  `metadata.ingest_time_utc`.

## Raw staging in the run bundle

When `telemetry.sources.osquery.enabled=true` and `telemetry.raw_preservation.enabled=true`, the
pipeline MUST stage the source-native results log under
`runs/<run_id>/raw/osquery/osqueryd.results.log`.

Notes:

- This staged path is the canonical evidence-tier representation path for osquery results (when
  evidence-tier raw preservation is enabled).
- When `telemetry.raw_preservation.enabled=true`, the file at this path MUST appear in either
  `present`, `withheld`, or `quarantined` form under the project redaction policy (path is constant,
  but content may be a deterministic placeholder and/or stored under the run quarantine directory).
- When `telemetry.raw_preservation.enabled=false`, the pipeline MUST NOT create this file (it MUST
  be absent) and MUST still produce the derived analytics-tier dataset under `raw_parquet/osquery/`
  (see below).
- This path corresponds to `telemetry.sources.osquery.output_path` (v0.1 conformance value:
  `raw/osquery/`), which is REQUIRED only when `telemetry.raw_preservation.enabled=true`.
- The pipeline MAY also stage adjacent files (example: `osqueryd.*.log`) under the same directory,
  but they MUST be clearly separated from the results log.

## OpenTelemetry Collector ingestion

### Collection model

The preferred ingestion model is:

- osquery writes NDJSON results to the local filesystem.
- The OTel Collector tails the results file via the `filelog` receiver.
- The collector parses JSON and exports logs via OTLP (local file or OTLP and optional gateway),
  consistent with the canonical topology in the
  [telemetry pipeline spec](040_telemetry_pipeline.md).

### Minimal filelog receiver example

This example is intentionally minimal and is designed to tail osquery results, parse NDJSON into
attributes, and preserve the original line for forensic or debug use.

```yaml
receivers:
  filelog/osquery:
    include:
      # Linux default (package dependent)
      - /var/log/osquery/osqueryd.results.log
      # Include common numeric-suffix rotations (plain NDJSON). Extend if your catch-up window needs more history.
      - /var/log/osquery/osqueryd.results.log.[0-9]
      - /var/log/osquery/osqueryd.results.log.[0-9][0-9]
      # Windows example (explicit is strongly preferred)
      - C:\\ProgramData\\osquery\\log\\osqueryd.results.log
      - C:\\ProgramData\\osquery\\log\\osqueryd.results.log.[0-9]
      - C:\\ProgramData\\osquery\\log\\osqueryd.results.log.[0-9][0-9]
    start_at: beginning
    include_file_path: true
    # Required for durable offset tracking across restarts; see telemetry pipeline spec "Checkpointing and replay semantics"
    storage: file_storage
    operators:
      # Preserve the original line before parsing (useful for forensic review and parse-error handling).
      - type: copy
        from: body
        to: attributes["log.record.original"]
      # Parse JSON. If parsing fails, DO NOT drop the record; send it onward as an unstructured log entry.
      # Be explicit about the parse destination to keep downstream field moves/copies stable.
      - type: json_parser
        parse_from: body
        parse_to: attributes
        on_error: send
      # Copy (do not move) key fields into a stable namespace for routing/identity while preserving
      # the original NDJSON field names (`name`, `action`) for telemetry baseline-profile matching.
      - type: copy
        from: attributes.name
        to: attributes["osquery.query_name"]
        on_error: send_quiet
      - type: copy
        from: attributes.hostIdentifier
        to: attributes["osquery.host_identifier"]
        on_error: send_quiet
      - type: copy
        from: attributes.unixTime
        to: attributes["osquery.unix_time"]
        on_error: send_quiet
      - type: copy
        from: attributes.action
        to: attributes["osquery.action"]
        on_error: send_quiet
```

**Durable offset tracking note (required)**: This receiver example assumes the collector enables a
storage extension (v0.1 reference: `file_storage` or filestorage) and points it at a durable on-disk
directory. Loss, corruption, or reset of that directory MUST be treated as checkpoint loss per the
[telemetry pipeline spec](040_telemetry_pipeline.md). Replay or duplication is expected; gaps must
be recorded.

### Rotation and compression constraints (required)

- The `filelog` receiver MUST be able to read every rotated segment necessary to cover the
  worst-case catch-up window (see [telemetry pipeline spec](040_telemetry_pipeline.md) section
  "Checkpointing and replay semantics").
- osquery filesystem logger rotation MAY produce Zstandard-compressed rotated files (`*.zst`). The
  v0.1 pipeline MUST NOT assume that the `filelog` receiver can read `*.zst` segments.
- Operators MUST ensure the osquery results rotation policy yields rotated history that is readable
  by `filelog` for the full catch-up window. Acceptable strategies include keeping rotated segments
  uncompressed until after the catch-up window expires or using gzip (`*.gz`) for rotated segments
  and configuring `filelog` `compression: gzip` (append-only; MUST NOT recompress-overwrite existing
  files).
- If unreadable rotated segments lead to missing results, the validator MUST record the gap as a
  telemetry failure (not silently ignored).

### Telemetry validation gates (baseline profile and continuity)

This section does not introduce new osquery semantics. It makes the osquery ingestion path
explicitly compatible with telemetry-stage gates defined in the telemetry pipeline and stage-outcome
ADRs.

Baseline profile gate (fail closed when enabled):

- When `telemetry.baseline_profile.enabled=true`, the telemetry validator evaluates
  `runs/<run_id>/inputs/telemetry_baseline_profile.json` and emits a health substage outcome with
  `stage="telemetry.baseline_profile"`.
- For `identity_source_type=osquery` (identity-family discriminator used for identity-scoped
  matching; not `metadata.source_type`; see ADR-0002), baseline signal matching uses the osquery
  NDJSON fields `name` (required) and `action` (optional). Therefore, ingestion/staging SHOULD
  preserve these fields (or preserve their semantics deterministically if renamed in an intermediate
  store).

File-tailed crash/restart + rotation continuity (required when osquery is enabled):

- When osquery (or any file-tailed source) is enabled, telemetry validation MUST perform a
  crash/restart and rotation continuity test and record results in
  `runs/<run_id>/logs/telemetry_validation.json` under `assets[].file_tailed_continuity_test`
  (including `loss_pct` and `dup_pct`).
- In CI, the continuity test asserts `loss_pct == 0` across a window spanning rotation and a crash
  boundary; duplication is acceptable but must be measured and reported as `dup_pct`.

### Required exporter tagging

- The collector or downstream normalizer MUST be able to set `metadata.source_type = "osquery"` for
  records originating from this receiver.

### Failure handling (v0.1)

- If a line fails JSON parsing, the collector SHOULD emit it as an unstructured log record (retain
  the raw line) and the normalizer MUST account for it as an ingest or parse error (see
  [Conformance fixtures and tests](#conformance-fixtures-and-tests)).

### Parse-error accounting (normative)

This section defines the single authoritative measurement point for osquery ingest/parse errors so
CI assertions are deterministic.

- Location: `runs/<run_id>/logs/counters.json` (contract: `counters`; see `025_data_contracts.md`).
- Counter name: `osquery_ndjson_parse_errors_total` (u64).

Semantics:

- When `telemetry.sources.osquery.enabled=true`,
  `counters.counters.osquery_ndjson_parse_errors_total` MUST be present.
- The counter MUST equal the number of osquery result records (one input line from
  `runs/<run_id>/raw/osquery/osqueryd.results.log`) that cannot be normalized due to an ingest/parse
  failure.
  - This includes:
    - JSON parsing failures (the line is not valid JSON), and
    - required-field parse failures (for example missing `unixTime` or `unixTime` not parseable as a
      signed 64-bit integer epoch-seconds value).
  - Each input line MUST contribute at most `+1` to this counter.
- When no ingest/parse failures occur, the counter MUST be present and MUST be `0`.

## Derived raw Parquet (produced when osquery is enabled)

When `telemetry.sources.osquery.enabled=true`, the telemetry stage MUST convert staged NDJSON lines
into a Parquet dataset under `runs/<run_id>/raw_parquet/osquery/` prior to normalization.

Retention and export policy (normative):

- `raw_parquet/**` is an analytics-tier operational staging store. It MUST be excluded from the v0.1
  default export profile and from signing/checksum scope (see
  `ADR-0009-run-export-policy-and-log-classification.md`).
- Implementations MAY prune `raw_parquet/**` after successful normalization, subject to disk budget
  policy (see [storage formats](045_storage_formats.md)). Implementations MUST NOT prune
  `raw_parquet/osquery/` before normalization consumes it.
- Operators who need to export `raw_parquet/osquery/**` (for example, for machine-learning dataset
  purposes) SHOULD use the dataset release workflow under `<workspace_root>/exports/datasets/` (see
  `085_golden_datasets.md`). Dataset releases MAY include raw stores (including
  `raw_parquet/osquery/**`) only when the release posture permits it.

The dataset directory MUST include `_schema.json` (see Parquet dataset conventions in
[storage formats](045_storage_formats.md)).

The dataset MUST include, at minimum, the following columns:

| Column            | Type          | Notes                                                                |
| ----------------- | ------------- | -------------------------------------------------------------------- |
| `time`            | int64         | Epoch ms derived from `unixTime`                                     |
| `query_name`      | string        | From `name`                                                          |
| `host_identifier` | string        | From `hostIdentifier`                                                |
| `action`          | string        | `added`, `removed`, or `snapshot`                                    |
| `columns_json`    | string (JSON) | Present for `added` or `removed`, else null                          |
| `snapshot_json`   | string (JSON) | Present for `snapshot`, else null                                    |
| `raw_json`        | string (JSON) | Canonical JSON representation of the record (see determinism notes)  |
| `raw_line`        | string        | Original line as read (from body / `log.record.original`), else null |
| `log.file.path`   | string        | If provided by the collector, else null                              |

Determinism requirements:

- `raw_json` MUST be the parsed JSON object re-serialized via RFC 8785 (JCS) prior to hashing or
  stable joins (see ADR-0002 "Event Identity and Provenance").

- For `action="snapshot"`, implementations MUST canonicalize the `snapshot` array to a deterministic
  order before serializing `snapshot_json` and `raw_json`:

  - Canonicalize each element object using RFC 8785 (JCS) to a UTF-8 string.
  - Sort elements by that canonical string (bytewise ascending).
  - Serialize the array in that sorted order.

- `raw_line` MUST NOT be used for identity.

- Row ordering (normative): before writing Parquet, implementations MUST sort all rows by the
  following total ordering (lowest tuple wins):

  1. `time` ascending (nulls sort first)
  1. `host_identifier` ascending (nulls sort first; UTF-8 byte order, no locale)
  1. `query_name` ascending (nulls sort first; UTF-8 byte order, no locale)
  1. `action` ascending (nulls sort first; UTF-8 byte order, no locale)
  1. `raw_json` ascending (nulls sort first; UTF-8 byte order, no locale)

- Deterministic dataset emission (normative):

  - The dataset MUST NOT be partitioned in v0.1 (no `key=value/` subdirectories).
  - The dataset directory MUST contain:
    - `_schema.json`
    - one or more Parquet data files named `part-0000.parquet`, `part-0001.parquet`, (zero-padded
      4-digit, monotonically increasing, no gaps)
  - Filenames MUST NOT include UUIDs, timestamps, random salts, or process-derived IDs.

## Normalization to OCSF

### Source type

- The normalizer MUST set `metadata.source_type = "osquery"` for osquery-derived events.
- For all osquery-derived normalized events (routed or unrouted), the normalizer MUST set
  `metadata.extensions.purple_axiom.raw_ref = null` (field MUST be present; Tier 3 contract rule).

### Routing by query_name

Normalization MUST be routed by osquery `query_name` (the `name` field in the results log). The
routing table MUST be captured in the mapping profile snapshot
(`normalized/mapping_profile_snapshot.json`).

v0.1 default routing:

| `query_name`          | OCSF target class    | `class_uid` |
| --------------------- | -------------------- | ----------: |
| `process_events`      | Process Activity     |        1007 |
| `process_etw_events`  | Process Activity     |        1007 |
| `file_events`         | File System Activity |        1001 |
| `ntfs_journal_events` | File System Activity |        1001 |
| `socket_events`       | Network Activity     |        4001 |

Rules:

- The normalizer MUST NOT guess a `class_uid` for unknown `query_name` values.
- Unknown `query_name` rows MUST be counted as unrouted or unmapped in
  `normalized/mapping_coverage.json`.
- Unknown `query_name` rows MUST NOT produce mapped normalized events (that is, `class_uid > 0`).
  Marker-bearing records MUST NOT be dropped; if a record carries
  `metadata.extensions.purple_axiom.synthetic_correlation_marker` and/or
  `metadata.extensions.purple_axiom.synthetic_correlation_marker_token`, the normalizer MUST still
  emit a minimal envelope with `class_uid = 0` and preserve whichever marker fields are present.
  When `normalization.raw_preservation.enabled=true`, the normalizer MUST also preserve the source
  payload under `raw.osquery` per `normalization.raw_preservation.policy` (see
  [Minimal mapping obligations (v0.1)](#minimal-mapping-obligations-v01)). When raw preservation is
  disabled (or `policy=none`), the normalizer MUST NOT include the source payload under
  `raw.osquery`.
- Implementations MAY provide an explicit allowlist of additional `query_name` routes via mapping
  profile material.

### Minimal mapping obligations (v0.1)

For routed rows, the normalizer MUST:

- Emit a valid OCSF envelope as defined in the [OCSF normalization spec](050_normalization_ocsf.md)
  and the [OCSF field tiers spec](055_ocsf_field_tiers.md).
- Preserve source payload under `raw.osquery` only when
  `normalization.raw_preservation.enabled=true`. The exact fields included MUST follow
  `normalization.raw_preservation.policy` (see below).
- The normalizer MUST set:
  - `metadata.identity_tier = 3`
  - `metadata.source_event_id = null` (osquery does not provide a stable native record id)
  - `metadata.time_precision = "s"`

`raw.osquery` payload (conditional):

- If `normalization.raw_preservation.enabled=false` or `normalization.raw_preservation.policy=none`,
  the normalizer MUST NOT emit `raw.osquery`.
- If `normalization.raw_preservation.policy=minimal`, `raw.osquery` MUST include:
  - `query_name`
  - `action`
  - `columns` (object) or `snapshot` (array), whichever was present
  - `raw_json_sha256` (stable digest reference to the canonical record JSON; format:
    `sha256:<64hex>`)
- If `normalization.raw_preservation.policy=full`, `raw.osquery` MUST include all `minimal` fields
  and MAY additionally include:
  - `log.file.path` (if provided by the collector)
- When `raw.osquery` is emitted, it MAY additionally include:
  - `notes` (array of strings; OPTIONAL): redaction-safe, deterministic note tokens describing known
    mapping limitations (example: `snapshot_state_observation_activity_id_99`). Notes MUST NOT
    include raw payload values, host-specific paths, usernames, or timestamps.

Raw record embedding (normative):

- Normalized events MUST NOT embed the full osquery record as a JSON string. Specifically,
  `raw.osquery.raw_json` and `raw.osquery.raw_line` MUST NOT be emitted in normalized outputs.
- The stable link from normalized events to the canonical record is `raw.osquery.raw_json_sha256`,
  computed as SHA-256 over the UTF-8 bytes of the canonical record JSON
  (`raw_parquet/osquery/raw_json`, RFC 8785 (JCS), after snapshot canonicalization).
- The canonical record JSON string and original raw line remain in evidence/analytics-tier
  artifacts:
  - `raw/osquery/osqueryd.results.log` (evidence-tier; placeholder/withheld/quarantine semantics
    apply),
  - `raw_parquet/osquery/raw_json` and `raw_parquet/osquery/raw_line` (analytics-tier; excluded from
    the v0.1 default export profile and signing scope).

Additional mapping (v0.1, optional):

- Map minimal class fields where deterministic and non-lossy (for example, process pid/path/cmdline,
  socket local/remote tuples).
- When mappings are OS-specific (Linux-only, macOS-only), they MUST be gated by platform and the
  mapping profile MUST record the platform guard.

### Identity basis (Tier 3, v0.1)

Each routed osquery-derived normalized event MUST have a deterministic `metadata.event_id` computed
per [ADR-0002](../adr/ADR-0002-event-identity-and-provenance.md) using the Tier 3 rules (event id
format: `pa:eid:v1:<hex32>`).

Identity basis object:

```json
{
  "source_type": "osquery",
  "host_identifier": "<hostIdentifier>",
  "query_name": "<name>",
  "action": "<action>",
  "unix_time": <unixTime_int>,
  "payload": <stable_payload_or_fingerprint_object>
}
```

Rules:

- `unix_time` MUST be derived by parsing `unixTime` as an integer epoch seconds value.

- Stable payload selection (Tier 3):

  - For `action in {"added","removed"}`, `stable_payload` MUST be the `columns` object.
  - For `action="snapshot"`, `stable_payload` MUST be the `snapshot` array after applying the
    snapshot canonicalization rules below.

- Canonical stable payload bytes:

  - `stable_payload_bytes = canonical_json_bytes(stable_payload)` where `canonical_json_bytes` is
    RFC 8785 (JCS) output (UTF-8).

- Inline vs fingerprint payload selection (v0.1 deterministic):

  - Let `OSQUERY_TIER3_PAYLOAD_INLINE_MAX_BYTES = 262144`.

  - If `len(stable_payload_bytes) <= OSQUERY_TIER3_PAYLOAD_INLINE_MAX_BYTES`, then
    `identity_basis.payload` MUST equal `stable_payload`.

  - If `len(stable_payload_bytes) > OSQUERY_TIER3_PAYLOAD_INLINE_MAX_BYTES`, then:

    - `identity_basis.payload` MUST equal `{"fingerprint": "<sha256_hex>"}` and MUST NOT embed
      `stable_payload`.
    - `fingerprint` MUST be computed as `sha256(stable_payload_bytes)` and MUST be encoded as
      lowercase hex of the full 32-byte digest (64 hex chars).
    - The full source-native record bytes MUST remain preserved in the evidence-tier staged results
      log at `runs/<run_id>/raw/osquery/osqueryd.results.log` (or its withheld/quarantined forms),
      so reprocessing can recover the payload even when identity uses a fingerprint.

- Snapshot canonicalization (required when `action="snapshot"` and `stable_payload` is a snapshot
  array):

  - Canonicalize each element object using RFC 8785 (JCS) to a UTF-8 string.
  - Sort elements by that canonical string (bytewise ascending).
  - Use the resulting sorted array as `stable_payload` (for both `stable_payload_bytes` and any
    embedded `identity_basis.payload` form).

- `calendarTime` MUST NOT be included in identity.

- `metadata.extensions.purple_axiom.synthetic_correlation_marker` (if present) MUST NOT be included
  in identity.

- `metadata.extensions.purple_axiom.synthetic_correlation_marker_token` (if present) MUST NOT be
  included in identity.

- For OCSF-conformant outputs, `metadata.uid` MUST equal `metadata.event_id` (see
  [data contracts](025_data_contracts.md)).

### Known mapping limitations (v0.1)

The v0.1 osquery mappings have documented limitations driven by osquery table coverage and
platform-specific backends.

#### macOS and Linux

**file_events (FIM)**: Initiating process attribution is not available from `file_events`. The table
reports file change metadata (including file owner `uid/gid`) and an `action`, but it does not
include a process identifier or executable path for the initiating actor. As a result,
`actor.process` MUST be absent for `file_events` normalized events. If process context is required
for detection content, it MUST be sourced from a process-context file auditing table rather than
inferred from `file_events`. Feasible options include Linux `process_file_events` (audit-based file
activity with process context) and macOS `es_process_file_events` (EndpointSecurity-based file
activity with process context). Operational constraints apply: `process_file_events` requires audit
control (it will not work if `auditd` is running), and it only reports events for directories that
exist before the agent starts.

**socket_events (process and socket auditing)**: `socket_events` provides process linkage, including
`pid` and executed `path`, so `actor.process.pid` can be populated directly when present.
`socket_events` provides an audit user identifier (`auid`). v0.1 normalization SHOULD map this to a
numeric user identifier (for example, `actor.user.uid`) when present. Username resolution is out of
scope for v0.1 unless explicitly supported via additional identity correlation logic. Direction
inference is best-effort and derived from the observed action set (`bind`, `connect`, `accept`);
`connect` is treated as outbound intent, `accept` as inbound acceptance, and `bind` is ambiguous
without additional context.

**action=snapshot (scheduled query snapshot logging)**: Snapshot rows represent bulk table state at
a point in time, not discrete per-entity events. When snapshot rows are emitted as event-like rows
(for example, via snapshot event logging), they MUST be normalized as state observations rather than
activity. v0.1 routes these to the standard class but with `activity_id=99` (Other). When
`raw.osquery` is emitted, the normalizer MUST include the note token
`snapshot_state_observation_activity_id_99` in `raw.osquery.notes`.

#### Windows

**Filesystem activity (ntfs_journal_events)**: On Windows, osquery file integrity monitoring is
sourced from `ntfs_journal_events` (NTFS USN journal), not `file_events`. `ntfs_journal_events` does
not include initiating process identifiers or executable path. Therefore, for file activity
normalized from `ntfs_journal_events`, `actor.process` MUST be absent. User attribution is not
provided directly by `ntfs_journal_events`. Any `actor.user` attribution requires a different
telemetry source. `activity_id` mapping remains best-effort because `action` values reflect USN
journal semantics (for example, write, delete, rename) and do not always cleanly distinguish content
writes from metadata-only changes.

**Network socket activity**: The osquery `socket_events` table is not available on Windows (it is
macOS and Linux only). Therefore, v0.1 does not normalize Windows network connection activity from
osquery. Any Windows network connection normalization MUST be sourced from a non-osquery telemetry
provider or treated as out of scope for v0.1. Scheduled snapshot diffs of socket state are
intentionally not treated as event-equivalent in v0.1 (race-prone and non-deterministic under load).

**Process execution context (process_etw_events)**: Windows process execution telemetry MAY be
sourced from `process_etw_events` (ETW-backed), which can provide `pid`, `ppid`, `path`, `cmdline`,
and `username` when available. `process_etw_events` reliability is build-dependent. v0.1 treats this
source as best-effort and requires fixture validation on the supported Windows build matrix
(including validation that ProcessStart events are emitted as expected).

**action=snapshot**: Snapshot rows remain bulk table state, not discrete events. Snapshot-derived
rows continue to be routed to the standard class with `activity_id=99` (Other). When `raw.osquery`
is emitted, the normalizer MUST include the note token `snapshot_state_observation_activity_id_99`
in `raw.osquery.notes`.

These limitations do not prevent normalization but may affect Tier 1 field coverage metrics (see the
[OCSF field tiers spec](055_ocsf_field_tiers.md)).

## Conformance fixtures and tests

Fixture cases under `tests/fixtures/osquery/` MUST follow the canonical fixture-case layout defined
in `100_test_strategy_ci.md` ("Fixture index"): each case is a leaf directory containing `inputs/`
and `expected/`.

Required fixture case set (v0.1, minimum):

- `osquery_smoke`

`osquery_smoke` structure (normative):

- `tests/fixtures/osquery/osquery_smoke/inputs/osqueryd.results.log` (NDJSON):
  - At least 2 differential rows (`added`, `removed`) for `process_events`.
  - At least 1 snapshot row (`snapshot`) for `file_events`whose canonical stable payload exceeds
    `OSQUERY_TIER3_PAYLOAD_INLINE_MAX_BYTES` (exercises `payload.fingerprint` behavior).
  - At least 1 row for `socket_events`.
  - At least 1 row for an unknown `query_name` (to validate unrouted behavior).
  - At least 1 invalid JSON line (to validate parse-error accounting).
- `tests/fixtures/osquery/osquery_smoke/expected/` MUST include deterministic golden outputs at
  run-relative paths (mirroring the run bundle layout), at minimum:
  - `raw/osquery/osqueryd.results.log` (byte-identical to `inputs/osqueryd.results.log`)
  - `normalized/mapping_coverage.json`
  - `normalized/ocsf_events.jsonl`

### Required assertions

A v0.1 implementation MUST satisfy:

- Parsing:
  - Valid NDJSON lines are ingested and parsed.
  - Invalid JSON lines are counted as ingest or parse errors and do not produce normalized events.
    - The authoritative count MUST be recorded as
      `counters.counters.osquery_ndjson_parse_errors_total` in `runs/<run_id>/logs/counters.json`.
- Routing:
  - `process_events` maps to `class_uid = 1007`.
  - `file_events` maps to `class_uid = 1001`.
  - `socket_events` maps to `class_uid = 4001`.
  - Unknown `query_name` values do not produce mapped normalized events (`class_uid > 0`) and are
    recorded as unrouted or unmapped in `normalized/mapping_coverage.json`.
  - Marker-bearing records (those carrying
    `metadata.extensions.purple_axiom.synthetic_correlation_marker` and/or
    `metadata.extensions.purple_axiom.synthetic_correlation_marker_token`) MUST NOT be dropped; if
    unrouted, they MUST still be emitted with `class_uid = 0`.
- Identity determinism:
  - Re-normalizing the same fixture input produces byte-identical `metadata.event_id` values.
  - The fixture set MUST exercise both Tier 3 payload forms:
    - at least one case where `identity_basis.payload` embeds `stable_payload`, and
    - at least one case where `identity_basis.payload.fingerprint` is used due to
      `OSQUERY_TIER3_PAYLOAD_INLINE_MAX_BYTES`.
- Contract alignment:
  - All osquery-derived normalized events include `metadata.extensions.purple_axiom.raw_ref` and it
    is `null`.
  - When `telemetry.raw_preservation.enabled=true`, the staged raw results log is present at
    `runs/<run_id>/raw/osquery/osqueryd.results.log` (actual content or deterministic placeholder
    when withheld/quarantined).
  - When `telemetry.raw_preservation.enabled=false`, the staged raw results log MUST be absent.
  - When `normalization.raw_preservation.enabled=true` and
    `normalization.raw_preservation.policy != "none"`, routed normalized events contain
    `raw.osquery.raw_json_sha256`.
  - For `action="snapshot"`, when `raw.osquery` is emitted, `raw.osquery.notes` MUST contain the
    note token `snapshot_state_observation_activity_id_99`.
  - Routed normalized events MUST NOT contain `raw.osquery.raw_json` or `raw.osquery.raw_line`.
  - When `normalization.raw_preservation.enabled=false` (or `policy="none"`), routed normalized
    events MUST NOT contain `raw.osquery`.
- Derived raw Parquet:
  - When `telemetry.sources.osquery.enabled=true`, the telemetry stage MUST produce
    `runs/<run_id>/raw_parquet/osquery/_schema.json` and one or more `part-*.parquet` files prior to
    normalization.
  - Implementations MAY prune `raw_parquet/**` after successful normalization (see
    `045_storage_formats.md`). If `runs/<run_id>/raw_parquet/osquery/` is present at end-of-run, it
    MUST include `_schema.json` and one or more `part-*.parquet` files.
  - The dataset directory contains no subdirectories (v0.1 forbids partitioned layouts).
  - Part filenames are deterministic:
    - `part-0000.parquet`, `part-0001.parquet`, ... (zero-padded 4-digit, monotonically increasing,
      no gaps)
    - no timestamps, UUIDs, or random salts in filenames
  - Row ordering is deterministic:
    - When reading the dataset as the concatenation of part files in filename order, rows are sorted
      by `(time, host_identifier, query_name, action, raw_json)` per the "Row ordering (normative)"
      rule above.

## Sample inputs and outputs (non-normative)

### Example osquery NDJSON lines

```json
{"name":"process_events","hostIdentifier":"linux-test-01","unixTime":"1736204345","action":"added","columns":{"pid":"4321","path":"/usr/bin/bash","cmdline":"bash -lc whoami"}}
{"name":"file_events","hostIdentifier":"linux-test-01","unixTime":"1736204347","action":"snapshot","snapshot":[{"target_path":"/tmp/x.txt","action":"CREATED"}]}
{"name":"unknown_query","hostIdentifier":"linux-test-01","unixTime":"1736204349","action":"added","columns":{"foo":"bar"}}
```

### Example normalized OCSF envelope (Process Activity)

```json
{
  "time": 1736204345000,
  "class_uid": 1007,
  "metadata": {
    "event_id": "pa:eid:v1:2f5a0f4b2c1b4bd38c0d9b6f7e9a1c2d",
    "uid": "pa:eid:v1:2f5a0f4b2c1b4bd38c0d9b6f7e9a1c2d",
    "source_event_id": null,
    "identity_tier": 3,
    "time_precision": "s",
    "run_id": "RUN_ID",
    "scenario_id": "SCENARIO_ID",
    "collector_version": "otelcol-contrib",
    "normalizer_version": "purple-axiom-normalizer",
    "source_type": "osquery",
    "extensions": {
      "purple_axiom": {
        "raw_ref": null
      }
    }
  },
  "raw": {
    "osquery": {
      "query_name": "process_events",
      "action": "added",
      "columns": {
        "pid": "4321",
        "path": "/usr/bin/bash",
        "cmdline": "bash -lc whoami"
      },
      "raw_json_sha256": "sha256:<64hex>"
    }
  }
}
```

## Key decisions

- osquery results are ingested from the filesystem logger and converted to analytics-tier Parquet;
  evidence-tier raw staging is optional and controlled by `telemetry.raw_preservation.enabled`.
- Routing to OCSF is keyed by `query_name`, with explicit handling for unknown routes.
- Identity is computed deterministically from canonicalized payloads and timestamps.
- Platform limitations are documented and do not prevent normalization.

## References

- [Telemetry pipeline spec](040_telemetry_pipeline.md)
- [Data contracts](025_data_contracts.md)
- [Config reference](120_config_reference.md)
- [ADR-0002: Event identity and provenance](../adr/ADR-0002-event-identity-and-provenance.md)
- [OCSF normalization spec](050_normalization_ocsf.md)
- [OCSF field tiers](055_ocsf_field_tiers.md)

## Changelog

| Date      | Change                                       |
| --------- | -------------------------------------------- |
| 2/21/2026 | update                                       |
| 1/24/2026 | update                                       |
| 1/18/2026 | spec update                                  |
| TBD       | Style guide migration (no technical changes) |
