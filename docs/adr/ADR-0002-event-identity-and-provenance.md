<!-- docs/adr/ADR-0002-event-identity-and-provenance.md -->

---
title: "ADR-0002: Event identity and provenance"
description: "Defines deterministic event identity computation and provenance model for reproducible detection matching"
status: proposed
category: adr
tags: [event-identity, provenance, ocsf, determinism, deduplication]
related:
  - ../spec/042_osquery_integration.md
  - ../spec/040_telemetry_pipeline.md
  - ../spec/050_normalization_ocsf.md
  - ../spec/120_config_reference.md
---

# ADR-0002: Event identity and provenance

| Property  | Value                    |
| --------- | ------------------------ |
| Status    | proposed                 |
| Date      | 2026-01-XX               |
| Deciders  | TBD                      |

## Context

Purple Axiom requires a stable, deterministic event identifier to support:

- Reproducible detection matching (ground truth ↔ telemetry ↔ detections).
- At-least-once collection semantics (duplicates on restart/replay are expected).
- Reprocessing from stored artifacts (for example: EVTX rehydration) without changing joins.

Timestamp precision and clock variance are not reliable uniqueness mechanisms. OpenTelemetry
explicitly distinguishes event time (`Timestamp`) from collection/observation time
(`ObservedTimestamp`), and the latter must not influence identity. Likewise, Windows Event Log
provides a stable record identifier (`EventRecordID`) that can anchor deterministic identity.

## Decision

**Summary**: Define deterministic `metadata.event_id` using tiered identity bases with RFC 8785
canonicalization, prioritizing source-native identifiers when available.

Define two identifiers:

1. `metadata.event_id` (required): deterministic identity for a *source event*.
1. `metadata.ingest_id` (optional): identity for a particular ingestion attempt (for debugging only;
   never used for joins).

For OCSF-conformant outputs, `metadata.uid` MUST equal `metadata.event_id`. If an upstream consumer
requires OCSF-only fields, `metadata.event_id` MAY be omitted provided `metadata.uid` is present and
equal.

### Event ID format

`metadata.event_id` MUST be computed as:

- Prefix: `pa:eid:v1:`
- Digest: `sha256(identity_basis_canonical)` truncated to 128 bits (32 hex chars)

Example: `pa:eid:v1:4b2d3f3f6b7b2a1c9a1d2c3b4a5f6e7d`

### Identity basis (v1)

The `identity_basis` is a minimal set of source-derived fields. It MUST exclude run-specific and
pipeline-specific values:

- MUST NOT include: `run_id`, `scenario_id`, `collector_version`, `normalizer_version`,
  ingest/observed timestamps, file offsets, collector hostnames, or any execution metadata.

Identity basis selection is tiered:

#### Tier 1: Source-native record identity (preferred)

Use when the source provides a stable per-record identifier or cursor.

**Windows Event Log / EVTX (generic)**

- `source_type`: `windows_eventlog`
- `origin.host`: event's source computer name (from the event payload)
- `origin.channel`: event channel (Security/System/Application/ForwardedEvents, etc.)
- `origin.record_id`: Windows `EventRecordID` from the event payload
- `origin.provider`: provider name and/or provider GUID (include both when available)
- `origin.event_id`: the Windows EventID (include qualifiers/version if available)

> **Note**: `origin.record_id` is unique only within `(origin.host, origin.channel)`; both MUST be
> included. Do not include event time in Tier 1 (avoid precision drift across collectors).

**Windows Sysmon (Microsoft-Windows-Sysmon/Operational)**

- `source_type`: `sysmon`
- `origin.host`: event's source computer name (from the event payload)
- `origin.channel`: `Microsoft-Windows-Sysmon/Operational`
- `origin.record_id`: Windows `EventRecordID` from the event payload
- `origin.provider`: provider name and/or provider GUID (include both when available)
- `origin.event_id`: the Sysmon EventID (include qualifiers/version if available)

Source-type selection rule (normative):

- For events collected via Windows Event Log / EVTX, the normalizer MUST set
  `identity_basis.source_type = "sysmon"` if and only if `origin.channel` equals
  `Microsoft-Windows-Sysmon/Operational`. Otherwise it MUST set
  `identity_basis.source_type = "windows_eventlog"`.

**Other examples (non-exhaustive)**

- journald: cursor
- Zeek: `uid`
- EDR: stable event GUID
- osquery: results log entry (v0.1 uses Tier 3; see [Osquery identity basis](#osquery-identity-basis-v01) below)

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
- `event.time_bucket` (event time truncated to the source's true precision)
- `payload` (canonical stable payload fields; exclude volatile fields), or
- `payload.fingerprint` (sha256 of canonical stable payload fields; exclude volatile fields)

Tier 3 MUST record `metadata.identity_tier = 3` for auditability.

Tier 3 payload guidance (normative):

- Implementations SHOULD prefer `payload.fingerprint` when payload size is unbounded or would
  materially increase identity basis size.
- If `payload.fingerprint` is used, it MUST be computed as `sha256(canonical_stable_payload)` where
  `canonical_stable_payload` is serialized using RFC 8785 (JCS) and excludes volatile fields.
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
- Implementations MUST NOT use an ephemeral collector read offset unless it is persisted with the
  stored artifact and remains stable for that artifact under reprocessing.

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

- If applied, restrict to ASCII-safe transforms only:
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

### Deduplication and replay

Normalization and storage MUST be idempotent w.r.t. `metadata.event_id`.

At-least-once delivery is expected: duplicates and replays can occur due to collector retries,
transport retries, restarts, or operator-initiated reprocessing.

Downstream deduplication is required. For this reason, `metadata.event_id` MUST be stable across
replays, and dedupe MUST be based on `metadata.event_id`.

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

### Non-identical duplicates (normative)

If two instances share the same `metadata.event_id` but are not byte-equivalent after removing
volatile pipeline fields:

- The normalizer MUST treat this as a **dedupe conflict** (a data-quality signal).
- The normalizer MUST select the canonical instance deterministically by choosing the instance with
  the lowest `sha256_hex(canonical_json(instance_without_volatile_fields))`.
- The normalizer MUST increment a `dedupe_conflicts_total` counter and record details in
  `runs/<run_id>/logs/` (without writing sensitive payloads into long-term artifacts).

### Collector restarts and checkpoints (Windows Event Log)

Windows Event Log collectors (including sources normalized under `windows_eventlog` and `sysmon`)
SHOULD persist read state using bookmarks/checkpoints to minimize duplicates on restart. Duplicates
can still occur; identity and dedupe rules above remain authoritative.

### Checkpoint persistence (normative)

To reduce replay volume while preserving at-least-once correctness:

- The telemetry pipeline MUST persist **per-stream checkpoints** for sources that support a stable
  upstream cursor (example: Windows `EventRecordID`).
- Checkpoints MUST be stored inside the run bundle under
  `runs/<run_id>/logs/telemetry_checkpoints/`. The default layout SHOULD be:
  - `runs/<run_id>/logs/telemetry_checkpoints/<source_type>/<asset_id>/<stream_id>.json`
- Checkpoint updates MUST be atomic (write temp file, fsync, rename).
- The pipeline MUST flush checkpoints at least once every `N` events or `T` seconds (configurable).

File-tailed sources (optional tightening, normative):

- For file-tailed sources (for example: syslog files and osquery results logs), the pipeline SHOULD
  persist per-stream checkpoints using the same layout.
- These checkpoints are pipeline state intended to reduce replay volume. Implementations MUST NOT
  incorporate file tail offsets into `metadata.event_id` unless the offset is persisted as part of a
  stable stored artifact cursor and the source is explicitly using Tier 2 identity for that stored
  artifact.

### Checkpoint loss / corruption (normative)

If a checkpoint is missing at restart:

- The pipeline MUST fall back to replaying from the start of the run window (subject to configured
  clock-skew tolerance), and MUST rely on the dedupe index to prevent duplicates in normalized
  output.
- The pipeline MUST record that checkpoint loss occurred in run-scoped logs and summary metrics
  (example: `telemetry_checkpoint_lost=true`, `telemetry_checkpoint_loss_total += 1`).

If a checkpoint store is corrupt at restart:

- Behavior depends on the collector/storage backend and configured recovery policy (see the
  [telemetry pipeline specification](../spec/040_telemetry_pipeline.md) "Checkpointing and replay
  semantics" and the [configuration reference](../spec/120_config_reference.md)
  `telemetry.otel.checkpoint_corruption`).
- If the collector refuses to start or cannot open its checkpoint store (fail-closed), the telemetry
  stage MUST fail closed and MUST use a stable reason code `checkpoint_store_corrupt`.
- If the storage backend automatically recovers by starting a fresh database (example: OTel
  `file_storage` with `recreate: true`), this MUST be treated as checkpoint loss. The pipeline MAY
  replay historical events and MUST rely on the dedupe index to prevent duplicates in normalized
  output. Implementations MUST record:
  - checkpoint loss (`telemetry_checkpoint_loss_total += 1`), and
  - replay start mode `reset_corrupt` (operator-visible), and
  - recovery evidence when available (example: `.backup` file emitted).

### EVTX reprocessing invariants

When reprocessing from EVTX:

- Extract Tier 1 identity inputs from the EVTX record system fields (do not rely on rendered message
  strings).
- Ensure `origin.host`, `origin.channel`, and `origin.record_id` reflect the *original* event when
  the EVTX record is a forwarded wrapper.

With these inputs, `metadata.event_id` remains stable across:

- live collection
- collector restarts
- EVTX reprocessing

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

**Why rejected**: Timestamp precision is not reliable enough for cross-collector determinism.
The tiered approach allows using timestamps only when no better identifier exists (Tier 3).

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
- EVTX reprocessing produces identical identities to live collection.

### Negative

- Requires collectors/normalizers to capture `source_event_id`-class fields (for example: Windows
  `EventRecordID`) whenever available.
- Tier 3 fallback is explicitly weaker; coverage metrics should track how often it is used.
- Introducing a distinct `source_type = "sysmon"` changes the Tier 1 identity basis for Sysmon
  events (because `source_type` participates in the identity hash). Implementations MUST treat this
  as join-key drift relative to older artifacts that used `windows_eventlog` for Sysmon and SHOULD
  regenerate golden fixtures/baselines accordingly.

### Neutral

- RFC 8785 (JCS) dependency adds a canonicalization requirement but is well-specified and has
  reference implementations.

## References

- [OCSF normalization specification](../spec/050_normalization_ocsf.md)
- [Telemetry pipeline specification](../spec/040_telemetry_pipeline.md)
- [Osquery integration specification](../spec/042_osquery_integration.md)
- [Configuration reference](../spec/120_config_reference.md)
- [RFC 8785: JSON Canonicalization Scheme (JCS)](https://www.rfc-editor.org/rfc/rfc8785)
- [OpenTelemetry Log Data Model - Timestamp](https://opentelemetry.io/docs/specs/otel/logs/data-model/#field-timestamp)

## Changelog

| Date       | Change                                                |
| ---------- | ----------------------------------------------------- |
| 2026-01-XX | Added Linux identity basis (auditd/journald/syslog)   |
| 2026-01-XX | Added osquery identity basis (Tier 3)                 |
| 2026-01-XX | Added alternatives considered section                 |
| 2026-01-XX | Initial draft                                         |