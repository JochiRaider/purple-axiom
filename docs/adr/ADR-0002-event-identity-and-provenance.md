---
title: 'ADR-0002: Event identity and provenance'
description: Defines deterministic event identity computation and provenance model for reproducible detection matching
status: draft
category: adr
tags: [event-identity, provenance, ocsf, determinism, deduplication]
related:
  - ../spec/042_osquery_integration.md
  - ../spec/040_telemetry_pipeline.md
  - ../spec/050_normalization_ocsf.md
  - ../spec/045_storage_formats.md
  - ../spec/120_config_reference.md
---

# ADR-0002: Event identity and provenance

## Context

Purple Axiom requires a stable, deterministic event identifier to support:

- Reproducible detection matching (ground truth ↔ telemetry ↔ detections).
- At-least-once collection semantics (duplicates on restart/replay are expected).
- Reprocessing from stored raw logs or other stored artifacts without changing joins.

v0.1 constraint (normative):

- Event identity computation and joins MUST NOT require native container exports. Identity MUST be
  computable from record-oriented telemetry and structured stored artifacts.

Timestamp precision and clock variance are not reliable uniqueness mechanisms. OpenTelemetry
explicitly distinguishes event time (`Timestamp`) from collection/observation time
(`ObservedTimestamp`), and the latter must not influence identity. Likewise, Windows Event Log
provides a stable record identifier (`EventRecordID`) that can anchor deterministic identity.

## Decision

Define two identifiers:

1. `metadata.event_id` (required): deterministic identity for a *source event* (join key).
1. `metadata.extensions.purple_axiom.ingest_id` (optional): identity for a particular ingestion
   attempt (debug only; never used for joins). If emitted, it MUST be treated as a volatile field
   and SHOULD be omitted from contract-backed normalized event stores unless explicitly enabled.

For OCSF-conformant outputs, producers MUST set `metadata.uid` equal to `metadata.event_id` and MUST
emit both fields on every normalized event. Consumers MUST NOT treat `metadata.uid` and
`metadata.event_id` as independent identifiers.

Provenance surfaces (normative):

- `metadata.source_event_id` MUST be present. For Tier 1 and Tier 2, it MUST be populated with the
  exact opaque source-native identifier (or stable cursor) that anchored identity. For Tier 3 it
  MUST be `null`.
- `metadata.identity_tier` MUST be present on every event and MUST be one of `1 | 2 | 3`, matching
  the tier used to compute `metadata.event_id`.
- `metadata.extensions.purple_axiom.raw_ref` MUST be present for identity tiers 1 and 2 and MUST be
  `null` for identity tier 3. It MUST provide a stable provenance pointer that can identify the raw
  origin record (see "Raw origin pointer" below).

Terminology note (normative):

- `metadata.identity_tier` refers to event identity strength tiers (1|2|3) defined in this ADR.
- This is distinct from OCSF field tiering (Tier 0/1/2/3/R in `055_ocsf_field_tiers.md`) and MUST
  NOT be conflated in reporting or gate naming.
- Human-facing outputs and gate descriptions SHOULD qualify tier references as either "identity
  tier" (IT1/IT2/IT3) or "field tier" (FT0/FT1/FT2/FT3/FT-R). They SHOULD NOT use unqualified "Tier
  N" where ambiguity is possible.

### Raw origin pointer: `metadata.extensions.purple_axiom.raw_ref`

For identity tiers 1 and 2, every **telemetry-derived** normalized event MUST carry a stable pointer
to the raw record that originated it. This enables deterministic cross-layer debugging from
normalized OCSF → simple view → raw artifact / raw_parquet.

`raw_ref` is an object with one of the following shapes:

- `kind: "file_cursor_v1"`: points into a run-bundled raw file/blob (Tier 1, `raw/`)
- `kind: "dataset_row_v1"`: points to a row in a Parquet dataset (Tier 2, `raw_parquet/`)

Schema (normative):

```json
{
  "kind": "file_cursor_v1 | dataset_row_v1",
  "path": "raw/... or raw_parquet/... (run-relative POSIX path)",
  "cursor": "li:<u64> | bo:<u64>",
  "row_locator": { "key": "value" }
}
```

Requirements (normative):

- `path` MUST be a run-relative POSIX path (see `045_storage_formats.md`) and MUST NOT include the
  `runs/<run_id>/` prefix.
- For `kind="file_cursor_v1"`, `cursor` MUST be present and MUST use the stable cursor formats
  defined for Unix log ingestion (`044_unix_log_ingestion.md`): `li:<u64>` (line index) or
  `bo:<u64>` (byte offset).
- For `kind="dataset_row_v1"`, `row_locator` MUST be present and MUST uniquely identify the raw
  record within the referenced dataset for the run.
- If evidence-tier raw preservation is enabled and the source supports stable cursors/offsets,
  producers SHOULD emit `file_cursor_v1` pointing into `raw/`.
- Otherwise, producers MUST emit `dataset_row_v1` pointing into `raw_parquet/`.
- When multiple candidate raw records could be considered the origin (for example, replay
  duplicates), producers MUST choose a canonical `raw_ref` deterministically:
  1. smallest `path` (byte-wise lexicographic)
  1. if both candidates include `cursor`: smallest numeric cursor value
  1. otherwise: smallest canonical JSON serialization of `row_locator` (sorted keys)
- `raw_ref` MUST NOT participate in the `metadata.event_id` hashing basis.

Downstream join digest (optional; normative when used):

- Downstream producers MAY compute a stable digest for `raw_ref` for join use (for example, dataset
  releases) as:
  - `raw_ref_sha256 = "sha256:" + sha256_hex(canonical_json_bytes(raw_ref_norm))`
- `raw_ref_norm` SHOULD omit optional keys whose value is `null` to avoid multiple encodings of the
  same logical pointer.
- This digest MUST NOT be interpreted as participating in `metadata.event_id` computation.

Optional multi-origin extension:

- Producers MAY additionally emit `metadata.extensions.purple_axiom.raw_refs` as an array of
  additional `raw_ref` objects when an emitted event is derived from multiple raw records. If
  present, `raw_refs` MUST include `raw_ref` as one element.

### `metadata.source_type` vs `identity_basis.source_type`

Purple Axiom distinguishes between a *pack/event discriminator* and an *identity-family
discriminator*:

- `metadata.source_type` (**event_source_type**): the producer / mapping-pack discriminator for the
  normalized event stream.
- `identity_basis.source_type` (**identity_source_type**): the identity-family discriminator that
  participates in `metadata.event_id` hashing.

`metadata.source_type` and `identity_basis.source_type` MAY differ. Implementations MUST NOT assume
they are equal.

Examples (non-normative):

| `metadata.source_type` (event_source_type) | `identity_basis.source_type` (identity_source_type) |
| ------------------------------------------ | --------------------------------------------------- |
| `windows-security`                         | `windows_eventlog`                                  |
| `windows-sysmon`                           | `sysmon`                                            |
| `osquery`                                  | `osquery`                                           |

Derivation and recording (normative):

- When using OCSF mapping profiles, the normalizer MUST derive:
  - `metadata.source_type` from the profile `event_source_type`, and
  - `identity_basis.source_type` from the profile `identity_source_type` (or a deterministic
    derivation defined by that profile).
- The chosen mapping profile (including `event_source_type` and `identity_source_type`) MUST be
  recorded in the run bundle at `runs/<run_id>/normalized/mapping_profile_snapshot.json`.
- Implementations MAY emit `metadata.extensions.purple_axiom.identity_source_type` (string) on each
  normalized event for debugging; if emitted, it MUST equal the value used for
  `identity_basis.source_type`.

### Event ID format

`metadata.event_id` MUST be computed as:

- Prefix: `pa:eid:v1:`
- Digest:
  - Compute `sha256(identity_basis_canonical)` over the raw canonical bytes.
  - Take the first 16 bytes of the digest (bytes `0..15`).
  - Hex-encode those 16 bytes as lowercase ASCII (32 hex chars).

Example: `pa:eid:v1:4b2d3f3f6b7b2a1c9a1d2c3b4a5f6e7d`

Versioning (normative):

- Any change that would alter `metadata.event_id` values for the same source records MUST bump the
  prefix version (`pa:eid:v2:` etc.). Implementations MUST NOT silently change v1 behavior.
- Implementations SHOULD retain the ability to compute v1 identities for legacy stored artifacts
  while v2 (or later) is introduced.

### Identity basis (v1)

The `identity_basis` is a minimal set of source-derived fields. It MUST exclude run-specific and
pipeline-specific values:

- MUST NOT include: `run_id`, `scenario_id`, `collector_version`, `normalizer_version`,
  `metadata.extensions.purple_axiom.synthetic_correlation_marker`,
  `metadata.extensions.purple_axiom.synthetic_correlation_marker_token`,
  `metadata.extensions.purple_axiom.ingest_id`, ingest/observed timestamps, file offsets, collector
  hostnames, or any execution metadata.

Rationale: `metadata.extensions.purple_axiom.synthetic_correlation_marker` and
`metadata.extensions.purple_axiom.synthetic_correlation_marker_token` are intentionally
per-run/per-action correlation metadata. Including either in `identity_basis` would make
`metadata.event_id` vary across runs and reprocessing, breaking stable joins and deterministic
deduplication.

Identity basis selection is tiered:

Terminology note (normative): within `identity_basis`, the `source_type` field is the
**identity_source_type** discriminator used for event-id hashing. It MUST NOT be confused with
`metadata.source_type` (event_source_type).

Additional rules (normative):

- The normalizer MUST set `metadata.identity_tier` to the selected tier number (`1`, `2`, or `3`).
- `identity_basis.source_type` MUST be set to the identity-family discriminator
  (**identity_source_type**) used for identity computation. Implementations MUST NOT assume it
  equals `metadata.source_type`.
  - When using OCSF mapping profiles, `identity_basis.source_type` MUST equal the mapping profile
    `identity_source_type` (see the mapping profile authoring guide).
  - If `metadata.extensions.purple_axiom.identity_source_type` is emitted, it MUST equal
    `identity_basis.source_type`.
- `identity_basis` MUST be a JSON object. Optional fields MUST be omitted when absent (do not emit
  `null`).
- Identity-basis values whose semantics are identifiers or cursors (examples: `origin.record_id`,
  `origin.journald_cursor`, `origin.flow_id`, `stream.cursor`) MUST be represented as strings in the
  `identity_basis` object to avoid cross-language integer precision drift.
  - Recommended encoding for numeric identifiers: base-10 ASCII digits with no separators and no
    leading `+`.
- Values with numeric measurement semantics (examples: ports, packet counts, byte counts) SHOULD
  remain JSON numbers (integers) as specified by the relevant tier definition.

#### Tier 1: Source-native record identity (preferred)

Use when the source provides a stable per-record identifier or cursor.

**Windows Event Log (generic)**

- `source_type`: `windows_eventlog`
- `origin.host`: event's source computer name (from the event payload)
- `origin.channel`: event channel (Security/System/Application/ForwardedEvents, etc.)
- `origin.record_id`: Windows `EventRecordID` from the event payload (base-10 string)
- `origin.provider_name`: provider name
- `origin.provider_guid`: provider GUID
- `origin.event_id`: the Windows EventID (include qualifiers/version if available)
- `origin.event_qualifiers` (optional)
- `origin.event_version` (optional)

> **Note**: `origin.record_id` is unique only within `(origin.host, origin.channel)`; both MUST be
> included. Do not include event time in Tier 1 (avoid precision drift across collectors).

**Windows Sysmon (Microsoft-Windows-Sysmon/Operational)**

- `source_type`: `sysmon`
- `origin.host`: event's source computer name (from the event payload)
- `origin.channel`: `Microsoft-Windows-Sysmon/Operational`
- `origin.record_id`: Windows `EventRecordID` from the event payload (base-10 string)
- `origin.provider_name`: provider name
- `origin.provider_guid`: provider GUID
- `origin.event_id`: the Sysmon EventID (include qualifiers/version if available)
- `origin.event_qualifiers` (optional)
- `origin.event_version` (optional)

Identity-source-type selection rule (normative):

- For events collected via Windows Event Log, the normalizer MUST set
  `identity_basis.source_type = "sysmon"` if and only if `origin.channel` equals
  `Microsoft-Windows-Sysmon/Operational`. Otherwise it MUST set
  `identity_basis.source_type = "windows_eventlog"`. This rule constrains only identity computation;
  `metadata.source_type` MAY be a different pack/event discriminator.

**Other examples (non-exhaustive)**

- journald: cursor
- Zeek: `uid`
- EDR: stable event GUID
- osquery: results log entry (v0.1 uses Tier 3; see
  [Osquery identity basis](#osquery-identity-basis-v01) below)

#### Tier 2: Stable stream cursor exists

Use when a stream identity plus a stable cursor exists, but no per-record ID is exposed in the event
body.

- `source_type`
- `origin.host`
- `stream.name` (file path, logger name, facility, topic, etc.)
- `stream.cursor` (cursor/offset that is stable for a given stored artifact)

Tier 2 SHOULD be avoided for long-term replay unless the cursor is persisted as evidence.

#### Tier 3: Deterministic fingerprint fallback

Use only when neither Tier 1 nor Tier 2 inputs exist. Identity is a fingerprint over stable fields.

- `source_type`
- `origin.host`
- `stream.name`
- `event.time_bucket` (string; event origin time truncated to the source's true precision; encoded
  as `<precision>:<integer>` where `<precision>` is one of `s|ms|us|ns` and `<integer>` is the epoch
  time in that unit)
- `payload` (canonical stable payload fields; exclude volatile fields), or
- `payload.fingerprint` (sha256 of canonical stable payload fields; exclude volatile fields)

Tier 3 MUST set `metadata.identity_tier = 3`.

Tier 3 payload guidance (normative):

- Implementations SHOULD prefer `payload.fingerprint` when payload size is unbounded or would
  materially increase identity basis size.
- If `payload.fingerprint` is used:
  - It MUST be computed as `sha256(canonical_stable_payload_bytes)` where
    `canonical_stable_payload_bytes = canonical_json_bytes(stable_payload)` and `stable_payload`
    excludes volatile fields.
  - The fingerprint MUST be encoded as lowercase hex of the full 32-byte digest (64 hex chars).
- If `payload` is used, it MUST contain only stable fields and MUST be canonicalizable under RFC
  8785 (JCS).

### Osquery identity basis (v0.1)

For `source_type = "osquery"`, v0.1 uses Tier 3.

Normative requirements:

- The normalizer MUST set `identity_basis.source_type = "osquery"`.
- The normalizer MUST record `metadata.identity_tier = 3`.
- The Tier 3 `identity_basis` fields and stable-payload selection rules for osquery MUST conform to
  the [osquery integration specification](../spec/042_osquery_integration.md) (see "Identity basis
  (Tier 3, v0.1)").
- Implementations MAY use `payload.fingerprint` instead of embedding `payload` when payload size is
  unbounded, subject to the Tier 3 payload guidance above.

### Linux identity basis

This section defines minimal, stable identity bases for common Linux log sources so that
`metadata.event_id` remains deterministic across collector restarts and reprocessing.

Normative goals:

- Prefer Tier 1 whenever the source includes a stable, source-native identifier.
- Avoid Tier 3 fingerprinting for Linux text logs when a stable cursor can be persisted, because
  timestamp precision and repeated message bodies commonly collide.

#### Auditd (audit.log / audisp)

The Linux audit subsystem emits a source-native event correlation identifier in the `msg` field. In
typical `audit.log` records, this takes the form:

`msg=audit(<epoch_seconds>.<fractional>:<serial>)`

Multiple records (lines) that describe one audit event share the same
`<epoch_seconds>.<fractional>:<serial>` pair, while record `type=...` distinguishes the per-record
payload within that event.

##### Tier selection (normative)

1. **Audit event aggregation available (preferred)**

   - If the ingestion path aggregates multiple audit records into one logical "audit event" object
     prior to OCSF normalization, the normalizer MUST use a Tier 1 identity basis defined below.

1. **No aggregation (each audit record is normalized independently)**

   - If each audit record line is normalized as its own OCSF event, the normalizer MUST NOT use a
     Tier 1 basis that would collide across records within the same audit event.
   - In this case, the normalizer MUST use Tier 2 with a stable stream cursor for the stored
     artifact:
     - `stream.name`: stable identifier of the stored audit artifact (example: `audit.log`)
     - `stream.cursor`: stable per-record cursor within that stored artifact (example: `line_index`
       in the stored raw table, or byte offset of the line start), persisted as evidence.

Rationale: many audit events emit multiple record types (SYSCALL, PATH, CWD, PROCTITLE, EOE, etc.)
sharing the same `msg=audit(...)` identifier. A Tier 1 basis that omits a per-record discriminator
would cause deterministic collisions when record lines are treated as independent events.

##### Tier 1 identity basis for aggregated audit events (normative)

When aggregating audit records into one logical audit event, the identity basis MUST be:

- `source_type`: `linux_auditd`
- `origin.host`: the emitting host identity (prefer a host value derived from the event origin, not
  the collector)
- `origin.audit_node` (optional): the `node=...` value if present in the record; else omit
- `origin.audit_msg_id`: the literal `audit(<epoch_seconds>.<fractional>:<serial>)` substring,
  captured exactly as present in the raw record (no float parsing)

Rules:

- `origin.audit_msg_id` MUST be treated as an opaque string.
  - Implementations MUST NOT parse it into floating point types.
  - Implementations MUST NOT normalize fractional precision (no trimming or padding).
- If `origin.audit_msg_id` cannot be extracted deterministically, the implementation MUST fall back
  to Tier 2 (preferred, when a stable cursor exists) or Tier 3 (last resort), and MUST record the
  chosen tier via `metadata.identity_tier`.

#### Journald (systemd journal)

Journald provides a stable per-entry cursor that can be used to resume iteration ("after cursor"),
and is therefore suitable as Tier 1 identity input.

##### Tier 1 identity basis (normative)

- `source_type`: `linux_journald`
- `origin.host`: the emitting host identity
- `origin.journald_cursor`: the journald cursor string as emitted by the source (`__CURSOR` or
  equivalent), treated as an opaque string

Rules:

- The cursor MUST be captured exactly (opaque string); implementations MUST NOT attempt to interpret
  it.
- When journald is collected as a stream, the pipeline SHOULD checkpoint the cursor as a per-stream
  checkpoint under `runs/<run_id>/logs/telemetry_checkpoints/` per the checkpoint persistence rules
  in this ADR.

#### Syslog (RFC3164/RFC5424 and file-tailed text)

Plain syslog text frequently lacks a stable, source-native unique record identifier. Repeated,
byte-identical messages in the same timestamp bucket are common.

##### Tier selection (normative)

- Preferred: obtain syslog via journald (Tier 1 via journald cursor), when feasible.
- Otherwise: use Tier 2 if and only if a stable cursor exists for a stored artifact, and that cursor
  is persisted as evidence.
- Tier 3 fingerprinting MAY be used only when neither Tier 1 nor Tier 2 inputs exist, and SHOULD be
  treated as lower confidence in coverage/operability reporting.
- Duplication note (normative): If overlapping syslog content is ingested from both journald and
  file-tailed `/var/log/*` on the same host, semantic duplicates are expected. Implementations MUST
  NOT attempt to remove these duplicates by comparing `metadata.event_id` (Tier 1 cursor-based IDs
  and Tier 2 artifact-cursor IDs will differ by design). Any overlap-dedupe mode MUST be explicitly
  enabled and recorded as an operator-visible telemetry policy (see Unix log ingestion spec).

##### Tier 2 identity basis (normative)

When syslog is collected from a stored artifact (example: a captured syslog file that is included in
the run bundle or raw store), the identity basis MUST be:

- `source_type`: `linux_syslog`
- `origin.host`: the emitting host identity
- `stream.name`: stable identifier of the stored artifact (example: `syslog`, `messages`, or a
  stable logical stream id)
- `stream.cursor`: stable per-record cursor within that stored artifact (example: `line_index` in
  the stored raw table, or byte offset of the line start), persisted as evidence

Rules:

- The cursor MUST be stable under reprocessing of the same stored artifact.
- The cursor MUST be represented as a string (example encodings: `li:<decimal>` for line index;
  `bo:<decimal>` for byte offset).
- Implementations MUST NOT use ephemeral collector file offsets unless those offsets are persisted
  with the stored artifact and are stable for that artifact under reprocessing.

#### Network flows (NetFlow/IPFIX and derived session logs) (provisional)

Network telemetry ingestion (pcap, NetFlow) is a v0.1 placeholder contract, but operators MAY plug
in custom sources. When a custom source produces normalized Network Activity events, the pipeline
still requires a deterministic `metadata.event_id` / `metadata.uid` identity basis.

This section defines a provisional identity basis for flow and session style records to enable
attemptable integrations while preserving the event identity invariants.

##### Tier selection (normative)

1. If the source provides a stable per-flow identifier scoped to the emitting sensor (example: Zeek
   `uid`), the normalizer MUST use Tier 1.
1. Otherwise, if flow records are read from a stored artifact included in the run bundle (file,
   table, or object store) and a stable per-record cursor can be persisted as evidence, the
   normalizer MUST use Tier 2 with `stream.name` and `stream.cursor`.
1. Otherwise, the normalizer MAY use Tier 3 fingerprinting. Tier 3 for flows MUST be treated as
   lower confidence due to possible collisions.

##### Tier 1 identity basis (stable flow identifier) (normative)

When a stable per-flow identifier is available, the identity basis MUST be:

- `source_type`: implementation-defined, but MUST be stable (recommended: `zeek_conn`,
  `suricata_eve`)
- `origin.host`: emitting sensor identity (from the source record, not the collector)
- `origin.flow_id`: source-native flow identifier (opaque string)

Rules:

- `origin.flow_id` MUST be treated as an opaque string (no numeric parsing or reformatting).
- If `origin.flow_id` cannot be extracted deterministically, the normalizer MUST fall back per the
  tier selection rules and MUST record the chosen `metadata.identity_tier`.

##### Tier 2 identity basis (stored artifact cursor) (normative)

When flow records are collected from a stored artifact, the identity basis MUST be:

- `source_type`: stable discriminator (recommended: `netflow`)
- `origin.host`: emitting exporter / observation point identity
- `stream.name`: stable identifier of the stored artifact (example: `netflow.jsonl`)
- `stream.cursor`: stable per-record cursor within that stored artifact (example: `li:<decimal>`)

Rules:

- Cursor stability and representation rules are identical to Syslog Tier 2.
- Implementations MUST NOT use an ephemeral collector read offset unless it is persisted with the
  stored artifact and remains stable for that artifact under reprocessing.

##### Tier 3 identity basis (5-tuple + start time) (normative)

When neither Tier 1 nor Tier 2 inputs exist, the identity basis MUST include at minimum:

- `source_type`: stable discriminator (recommended: `netflow`)
- `origin.host`: emitting exporter / observation point identity
- `flow.start_time_ms`: flow start time in ms since epoch, UTC
- `flow.src_ip`: source IP address (string)
- `flow.src_port`: source port (integer)
- `flow.dst_ip`: destination IP address (string)
- `flow.dst_port`: destination port (integer)
- `flow.transport`: transport identifier (prefer IANA protocol number; else lowercase name)

Optional fields that MAY be included when available (recommended to reduce collisions):

- `flow.end_time_ms`
- `flow.packets`
- `flow.bytes`
- `flow.tcp_flags`
- `flow.direction`
- `origin.observation_domain_id`

Rules:

- `flow.start_time_ms` MUST reflect event origin time and MUST NOT incorporate ingest time or
  `metadata.observed_time`.
- Implementations SHOULD canonicalize IP address strings prior to hashing (for example, IPv6 to a
  compressed lowercase form) but MUST apply any such transform deterministically and consistently
  across runs.
- Collisions are possible. Implementations MUST treat Tier 3 flow identities as non-unique and MUST
  preserve enough evidence to debug collisions (at minimum: identity basis fields plus any optional
  fields present in the source record).

##### Verification hooks (normative)

If any of the recommended network `source_type` values are implemented, the implementation MUST add
fixture vectors in the same style as the existing identity basis fixtures, including at least one
intentional-collision fixture to validate deterministic collision handling.

#### Linux identity basis fixtures (normative)

Implementations MUST maintain a fixture-driven test suite that exercises identity-basis extraction
and hashing for all implemented `source_type` values, including Tier 3 fallback behavior where
applicable.

At minimum:

- Sources using Tier 2 or Tier 3 (including `osquery`) MUST have fixture-driven identity vectors.
- The fixture suite MUST include at least one case that exercises Tier 3 payload handling using
  `payload` and at least one case using `payload.fingerprint` (when the implementation supports
  both), and MUST validate that the resulting `metadata.event_id` values are stable.

Recommended fixture set (v0.1):

- `tests/fixtures/event_id/v1/linux_identity_vectors.jsonl`
  - JSONL vectors where each line contains: `case`, `identity_tier`, `identity_basis`, and
    `event_id`.
  - Vectors MUST include at least:
    - auditd Tier 1 (aggregated audit event)
    - auditd Tier 2 (no aggregation; per-record cursor)
    - journald Tier 1 (cursor-based)
    - syslog Tier 2 (stored artifact cursor-based)
    - syslog Tier 3 (fingerprint fallback)
- `tests/fixtures/event_id/v1/linux_identity_collision.jsonl`
  - Two or more vectors that intentionally collide (same Tier 3 identity basis), used to validate
    collision accounting and downstream de-duplication behavior.
- Representative raw inputs for extraction tests (recommended):
  - `tests/fixtures/event_id/v1/linux_auditd.audit.log`
  - `tests/fixtures/event_id/v1/linux_journald.jsonl`
  - `tests/fixtures/event_id/v1/linux_syslog.messages`
  - (Additional recommended non-Linux vectors)
    - `tests/fixtures/event_id/v1/osquery_identity_vectors.jsonl`
    - Representative raw osquery results fixtures, as defined by the
      [osquery integration specification](../spec/042_osquery_integration.md)

### Canonicalization rules

**Summary**: All identity bases MUST be serialized using RFC 8785 (JCS) prior to hashing to ensure
cross-implementation determinism.

To ensure cross-implementation determinism, implementations MUST use JSON Canonicalization Scheme
(RFC 8785, JCS) for serializing identity bases prior to hashing.

Normative definition:

- `identity_basis_canonical = canonical_json_bytes(identity_basis)` where `canonical_json_bytes` is
  RFC 8785 output (UTF-8; deterministic property order; minimal form; no BOM; no trailing newline).

Fallback policy:

- Implementations MUST vendor or invoke a known-good RFC 8785 implementation.
- Substituting a non-JCS "canonical JSON" serializer is not permitted unless it passes the JCS
  fixture suite byte-for-byte.

Pre-hash normalization (Tier 1 Windows, optional but deterministic if used):

- If applied, restrict to ASCII-safe transforms only, and apply them to the `identity_basis` values
  prior to RFC 8785 serialization:
  - `origin.host`, `origin.channel`, `origin.provider`: trim ASCII whitespace; lowercase ASCII.

### Timestamp handling

Store two timestamps when available:

- `time` / event time: when the event occurred at the origin (OpenTelemetry `Timestamp` concept).
- `metadata.observed_time` (optional): when the event was observed by the collector (OpenTelemetry
  `ObservedTimestamp` concept).

Rules:

- `metadata.event_id` MUST NOT incorporate `metadata.observed_time`.
- When mapping sources with limited precision (for example: seconds), `time` MUST be represented in
  ms since epoch with sub-second components set to zero. Emit `metadata.time_precision` as one of:
  `s|ms|us|ns`.
- For sources that require timestamp inference (example: RFC 3164 syslog without year/timezone),
  implementations MUST apply deterministic inference rules and SHOULD record the chosen inference
  policy in normalization provenance (for debugging/reprocessing).

### Deduplication and replay

Normalization and storage MUST be idempotent w.r.t. `metadata.event_id`.

At-least-once delivery is expected: duplicates and replays can occur due to collector retries,
transport retries, restarts, or operator-initiated reprocessing.

Downstream deduplication is required. For this reason, `metadata.event_id` MUST be stable across
replays, and dedupe MUST be based on `metadata.event_id`.

Integration with stage outcomes and state machines (normative):

- If `metadata.event_id` cannot be generated for a record and no configured fallback tier can be
  applied deterministically, the normalization stage MUST fail closed with reason code
  `event_id_generation_failed`.
- Checkpoint loss and checkpoint corruption MUST be surfaced in the telemetry stage outcome surface
  using stable reason codes (`checkpoint_loss`, `checkpoint_store_corrupt`) and MUST be reflected in
  run-scoped counters/metrics.

### Deduplication scope and window (normative)

- **Scope:** Deduplication MUST be enforced for the normalized event store within a single run
  bundle (example: `runs/<run_id>/normalized/ocsf_events/`).
- **Non-goal:** The project does not require `metadata.event_id` to be globally unique across run
  bundles. Replays across different runs MAY intentionally produce the same `metadata.event_id`.
- **Window:** The deduplication window MUST be the full run window (unbounded within the run), i.e.,
  dedupe MUST consider all previously-emitted normalized events for the run, not only "recent"
  events.

### Dedupe index persistence (normative)

To make at-least-once delivery compatible with deterministic outputs:

- The normalizer MUST maintain a **durable dedupe index** for the run, keyed by `metadata.event_id`.
- The dedupe index MUST be persisted to disk inside the run bundle under `runs/<run_id>/logs/`
  (example: `runs/<run_id>/logs/dedupe_index/ocsf_events.*`).
- The dedupe index MUST survive process restarts for the same `run_id`.
- If the dedupe index is missing/corrupt on restart, but the normalized store already contains rows,
  the normalizer MUST rebuild the dedupe index by scanning `metadata.event_id` from the existing
  normalized store before appending any new rows.
- When an incoming normalized event is suppressed as an exact duplicate (equivalent after volatile
  field removal) because its `metadata.event_id` is already present in the dedupe index, the
  normalizer MUST increment `dedupe_duplicates_dropped_total`.

### Non-identical duplicates (normative)

Define `instance_without_volatile_fields` as the normalized event with the following fields removed:

- `metadata.ingest_time_utc` (if present)
- `metadata.observed_time` (if present; deprecated alias for ingest/observation time)
- `metadata.extensions.purple_axiom.ingest_id`

Define `instance_canonical_bytes = canonical_json_bytes(instance_without_volatile_fields)`.

If two instances share the same `metadata.event_id` but have different `instance_canonical_bytes`:

- The normalizer MUST treat this as a **dedupe conflict** (a data-quality signal).
- The normalizer MUST compute `conflict_key = sha256_hex(instance_canonical_bytes)` for each
  instance, where `sha256_hex` is lowercase hex of the full 32-byte digest.
- The normalizer MUST ensure that the canonical instance retained for a given `metadata.event_id` is
  the instance with the lexicographically smallest `conflict_key` across all observed instances for
  that `metadata.event_id`, independent of ingestion order.
- The normalizer MUST increment `dedupe_conflicts_total` each time a non-equivalent instance is
  observed for an existing `metadata.event_id`.
- The normalizer MUST record minimal conflict evidence under `runs/<run_id>/logs/` (without writing
  sensitive payloads into long-term artifacts). Minimal evidence SHOULD include:
  - `metadata.event_id`
  - `metadata.source_type`
  - `identity_source_type` (the value used for `identity_basis.source_type`)
  - `metadata.source_event_id`
  - `metadata.identity_tier`
  - `conflict_key` of the incoming instance and the retained canonical instance

### Collector restarts and checkpoints (Windows Event Log)

Windows Event Log collectors (including Sysmon events collected from
`Microsoft-Windows-Sysmon/Operational`) SHOULD persist read state using bookmarks/checkpoints to
minimize duplicates on restart. Duplicates can still occur; identity and dedupe rules above remain
authoritative.

### Checkpoint persistence (normative)

To reduce replay volume while preserving at-least-once correctness:

- The telemetry pipeline MUST persist **per-stream checkpoints** for sources that support a stable
  upstream cursor (example: Windows `EventRecordID`).
- The live checkpoint store MUST be located on the collector host (platform-local;
  implementation-defined) and MUST survive collector restarts for the duration of the run.
  - Implementations MAY snapshot the checkpoint store into the run bundle under
    `runs/<run_id>/logs/telemetry_checkpoints/` for diagnostics and CI reproducibility.
    - Snapshot format is implementation-defined (for example, a single database file for an OTel
      `file_storage` backend).
    - If the snapshot is exported as per-stream JSON files, the layout SHOULD be:
      `runs/<run_id>/logs/telemetry_checkpoints/<source_type>/<asset_id>/<stream_id>.json`

> **Note**: `<source_type>` in the checkpoint snapshot path is a telemetry-collection namespace
> (checkpoint key space). It is not required to match `metadata.source_type` and is typically less
> granular.

- Checkpoint updates MUST be crash-safe (atomic commit semantics).
  - For file-based checkpoint exports, implementations MUST write to a temp file, fsync, then
    rename.
- Each successful checkpoint flush MUST increment `telemetry_checkpoints_written_total`.
- The pipeline MUST flush checkpoints at least once every `N` events or `T` seconds (configurable).

File-tailed sources (optional tightening, normative):

- For file-tailed sources (for example: syslog files and osquery results logs), the pipeline SHOULD
  persist per-stream checkpoints using the same checkpointing approach (and, if snapshotted into the
  run bundle, the same snapshot namespace conventions).
- These checkpoints are pipeline state intended to reduce replay volume. Implementations MUST NOT
  incorporate file tail offsets into `metadata.event_id` unless the offset is persisted as part of a
  stable stored artifact cursor and the source is explicitly using Tier 2 identity for that stored
  artifact.

### Checkpoint loss / corruption (normative)

If a checkpoint is missing at restart:

- The pipeline MUST fall back to replaying from the start of the run window (subject to configured
  clock-skew tolerance), and MUST rely on the dedupe index to prevent duplicates in normalized
  output.
- The pipeline MUST record that checkpoint loss occurred in run-scoped logs and summary metrics:
  - increment `telemetry_checkpoint_loss_total += 1`
  - record `replay_start_mode = "reset_missing"` (operator-visible)

If a checkpoint store is corrupt at restart:

- Behavior depends on the collector/storage backend and configured recovery policy (see the
  [telemetry pipeline specification](../spec/040_telemetry_pipeline.md) "Checkpointing and replay
  semantics" and the [configuration reference](../spec/120_config_reference.md)
  `telemetry.otel.checkpoint_corruption`).
- Any detected checkpoint store corruption or reset MUST increment
  `telemetry_checkpoint_corruption_total`.
- If the collector refuses to start or cannot open its checkpoint store (fail-closed), the telemetry
  stage MUST fail closed and MUST use a stable reason code `checkpoint_store_corrupt`. When
  available, implementations MUST also record an operator-actionable error code in run-scoped
  telemetry validation evidence (example categories: missing store, unwritable store, corrupt
  store).
- If the storage backend automatically recovers by starting a fresh database (example: OTel
  `file_storage` with `recreate: true`), this MUST be treated as checkpoint loss. The pipeline MAY
  replay historical events and MUST rely on the dedupe index to prevent duplicates in normalized
  output. Implementations MUST record:
  - checkpoint loss (`telemetry_checkpoint_loss_total += 1`), and
  - replay start mode `reset_corrupt` (operator-visible), and
  - recovery evidence when available (example: `.backup` file emitted).

### Windows Event Log reprocessing invariants

When reprocessing from stored Windows Event Log artifacts (for example: structured raw tables and
sidecar raw payloads; native container exports, if any, are optional):

- Extract Tier 1 identity inputs from the stored record system fields (do not rely on rendered
  message strings).
- Ensure `origin.host`, `origin.channel`, and `origin.record_id` reflect the *original* event when
  the stored artifact wraps a forwarded event.

With these inputs, `metadata.event_id` remains stable across:

- live collection
- collector restarts
- stored-artifact reprocessing

## Alternatives considered

### Alternative 1: UUID-based identity

Use UUIDv4 generated at collection time for event identity.

**Pros**:

- Simple implementation
- Guaranteed uniqueness without coordination

**Cons**:

- Not deterministic across replays or reprocessing
- Breaks reproducibility requirement for detection matching
- Cannot deduplicate events across collector restarts

**Why rejected**: Violates core requirement for stable joins across reprocessing scenarios.

### Alternative 2: Timestamp + payload hash

Use `sha256(event_timestamp + payload_hash)` as event identity.

**Pros**:

- Deterministic for byte-identical events with identical timestamps

**Cons**:

- Timestamp precision drift across collectors causes identity divergence
- Clock skew between hosts creates false duplicates or missed deduplication
- Sub-second precision varies by source, creating inconsistent behavior

**Why rejected**: Timestamp precision is not reliable enough for cross-collector determinism. The
tiered approach allows using timestamps only when no better identifier exists (Tier 3).

### Alternative 3: Source-only identity (no tiers)

Require all sources to provide a native unique identifier; reject sources that don't.

**Pros**:

- Simpler implementation
- Strongest determinism guarantees

**Cons**:

- Excludes important sources (syslog, some EDR exports, legacy formats)
- Reduces coverage for real-world detection engineering scenarios

**Why rejected**: Overly restrictive for v0.1 goals. Tier 3 fallback with explicit auditability
provides acceptable coverage while maintaining transparency about identity confidence.

## Consequences

### Positive

- Stable event joins and reproducible scoring become practical.
- At-least-once delivery is explicitly supported with clear deduplication semantics.
- Identity tier tracking enables coverage metrics to surface when weaker identity is used.
- Decoupling pack-level `metadata.source_type` from identity-family `identity_basis.source_type`
  prevents event-id drift when mapping pack naming changes.
- Windows Event Log stored-artifact reprocessing produces identical identities to live collection.

### Negative

- Requires collectors/normalizers to capture `source_event_id`-class fields (for example: Windows
  `EventRecordID`) whenever available.
- Tier 3 fallback is explicitly weaker; coverage metrics should track how often it is used.
- Introducing a distinct `identity_source_type = "sysmon"` (i.e., using
  `identity_basis.source_type = "sysmon"`) changes the Tier 1 identity basis for Sysmon events
  (because `identity_basis.source_type` participates in the identity hash). Implementations MUST
  treat this as join-key drift relative to older artifacts that used
  `identity_source_type = "windows_eventlog"` for Sysmon and SHOULD regenerate golden
  fixtures/baselines accordingly.

### Neutral

- RFC 8785 (JCS) dependency adds a canonicalization requirement but is well-specified and has
  reference implementations.

## References

- [OCSF normalization specification](../spec/050_normalization_ocsf.md)
- [Telemetry pipeline specification](../spec/040_telemetry_pipeline.md)
- [Osquery integration specification](../spec/042_osquery_integration.md)
- [Configuration reference](../spec/120_config_reference.md)
- [OCSF mapping profile authoring guide](../mappings/ocsf_mapping_profile_authoring_guide.md)
- [RFC 8785: JSON Canonicalization Scheme (JCS)](https://www.rfc-editor.org/rfc/rfc8785)
- [OpenTelemetry Log Data Model - Timestamp](https://opentelemetry.io/docs/specs/otel/logs/data-model/#field-timestamp)

## Changelog

| Date       | Change                                              |
| ---------- | --------------------------------------------------- |
| 2026-01-23 | Clarified event_source_type vs identity_source_type |
| 2026-01-12 | Added Linux identity basis (auditd/journald/syslog) |
| 2026-01-XX | Added osquery identity basis (Tier 3)               |
| 2026-01-XX | Added alternatives considered section               |
| 2026-01-XX | Initial draft                                       |
