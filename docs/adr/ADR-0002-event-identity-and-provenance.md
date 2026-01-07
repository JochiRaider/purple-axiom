<!-- docs/adr/ADR-0002-event-identity-and-provenance.md -->
# ADR-0002: Event identity and provenance

## Status
Proposed

## Context
Purple Axiom requires a stable, deterministic event identifier to support:

- Reproducible detection matching (ground truth ↔ telemetry ↔ detections).
- At-least-once collection semantics (duplicates on restart/replay are expected).
- Reprocessing from stored artifacts (for example: EVTX rehydration) without changing joins.

Timestamp precision and clock variance are not reliable uniqueness mechanisms. OpenTelemetry explicitly distinguishes event time (`Timestamp`) from collection/observation time (`ObservedTimestamp`), and the latter must not influence identity. Likewise, Windows Event Log provides a stable record identifier (`EventRecordID`) that can anchor deterministic identity.

## Decision
Define two identifiers:

1. `metadata.event_id` (required): deterministic identity for a *source event*.
2. `metadata.ingest_id` (optional): identity for a particular ingestion attempt (for debugging only; never used for joins).

For OCSF-conformant outputs, `metadata.uid` MUST equal `metadata.event_id`. If an upstream consumer requires OCSF-only fields, `metadata.event_id` MAY be omitted provided `metadata.uid` is present and equal.

### event_id format
`metadata.event_id` MUST be computed as:

- Prefix: `pa:eid:v1:`
- Digest: `sha256(identity_basis_canonical)` truncated to 128 bits (32 hex chars)

Example: `pa:eid:v1:4b2d3f3f6b7b2a1c9a1d2c3b4a5f6e7d`

### Identity basis (v1)
The `identity_basis` is a minimal set of source-derived fields. It MUST exclude run-specific and pipeline-specific values:

- MUST NOT include: `run_id`, `scenario_id`, `collector_version`, `normalizer_version`, ingest/observed timestamps, file offsets, collector hostnames, or any execution metadata.

Identity basis selection is tiered:

#### Tier 1: Source-native record identity available (preferred)
Use when the source provides a stable per-record identifier or cursor.

**Windows Event Log / EVTX**
- `source_type`: `windows_eventlog`
- `origin.host`: event's source computer name (from the event payload)
- `origin.channel`: event channel (Security/System/Application/ForwardedEvents, etc.)
- `origin.record_id`: Windows `EventRecordID` from the event payload
- `origin.provider`: provider name and/or provider GUID (include both when available)
- `origin.event_id`: the Windows EventID (include qualifiers/version if available)

Notes:
- `origin.record_id` is unique only within `(origin.host, origin.channel)`; both MUST be included.
- Do not include event time in Tier 1 (avoid precision drift across collectors).

**Other examples (non-exhaustive)**
- journald: cursor
- Zeek: `uid`
- EDR: stable event GUID

#### Tier 2: Stable stream cursor exists
Use when a stream identity plus a stable cursor exists, but no per-record ID is exposed in the event body.

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
- `payload.fingerprint` (sha256 of canonical stable payload fields; exclude volatile fields)

Tier 3 MUST record `metadata.identity_tier = 3` for auditability.

### Linux identity basis (auditd / journald / syslog)

This section defines minimal, stable identity bases for common Linux log sources so that
`metadata.event_id` remains deterministic across collector restarts and reprocessing.

Normative goals:
- Prefer Tier 1 whenever the source includes a stable, source-native identifier.
- Avoid Tier 3 fingerprinting for Linux text logs when a stable cursor can be persisted, because
  timestamp precision and repeated message bodies commonly collide.

#### Auditd (audit.log / audisp)

The Linux audit subsystem emits a source-native event correlation identifier in the `msg` field.
In typical `audit.log` records, this takes the form:

`msg=audit(<epoch_seconds>.<fractional>:<serial>)`

Multiple records (lines) that describe one audit event share the same `<epoch_seconds>.<fractional>:<serial>`
pair, while record `type=...` distinguishes the per-record payload within that event.

##### Tier selection (normative)

1) **Audit event aggregation available (preferred)**
   - If the ingestion path aggregates multiple audit records into one logical “audit event” object
     prior to OCSF normalization, the normalizer MUST use a Tier 1 identity basis defined below.

2) **No aggregation (each audit record is normalized independently)**
   - If each audit record line is normalized as its own OCSF event, the normalizer MUST NOT use a Tier 1
     basis that would collide across records within the same audit event.
   - In this case, the normalizer MUST use Tier 2 with a stable stream cursor for the stored artifact:
     - `stream.name`: stable identifier of the stored audit artifact (example: `audit.log`)
     - `stream.cursor`: stable per-record cursor within that stored artifact (example: `line_index` in the
       stored raw table, or byte offset of the line start), persisted as evidence.

Rationale: many audit events emit multiple record types (SYSCALL, PATH, CWD, PROCTITLE, EOE, etc.)
sharing the same `msg=audit(...)` identifier. A Tier 1 basis that omits a per-record discriminator would
cause deterministic collisions when record lines are treated as independent events.

##### Tier 1 identity basis for aggregated audit events (normative)

When aggregating audit records into one logical audit event, the identity basis MUST be:

- `source_type`: `linux_auditd`
- `origin.host`: the emitting host identity (prefer a host value derived from the event origin, not the collector)
- `origin.audit_node` (optional): the `node=...` value if present in the record; else omit
- `origin.audit_msg_id`: the literal `audit(<epoch_seconds>.<fractional>:<serial>)` substring,
  captured exactly as present in the raw record (no float parsing)

Rules:
- `origin.audit_msg_id` MUST be treated as an opaque string.
  - Implementations MUST NOT parse it into floating point types.
  - Implementations MUST NOT normalize fractional precision (no trimming or padding).
- If `origin.audit_msg_id` cannot be extracted deterministically, the implementation MUST fall back to
  Tier 2 (preferred, when a stable cursor exists) or Tier 3 (last resort), and MUST record the chosen
  tier via `metadata.identity_tier`.

#### Journald (systemd journal)

Journald provides a stable per-entry cursor that can be used to resume iteration (“after cursor”),
and is therefore suitable as Tier 1 identity input.

##### Tier 1 identity basis (normative)

- `source_type`: `journald`
- `origin.host`: the emitting host identity
- `origin.journald_cursor`: the journald cursor string as emitted by the source (`__CURSOR` or equivalent),
  treated as an opaque string

Rules:
- The cursor MUST be captured exactly (opaque string); implementations MUST NOT attempt to interpret it.
- When journald is collected as a stream, the pipeline SHOULD checkpoint the cursor as a per-stream
  checkpoint under `runs/<run_id>/logs/telemetry_checkpoints/` per the checkpoint persistence rules in this ADR.

#### Syslog (RFC3164/RFC5424 and file-tailed text)

Plain syslog text frequently lacks a stable, source-native unique record identifier. Repeated,
byte-identical messages in the same timestamp bucket are common.

##### Tier selection (normative)

- Preferred: obtain syslog via journald (Tier 1 via journald cursor), when feasible.
- Otherwise: use Tier 2 if and only if a stable cursor exists for a stored artifact, and that cursor is
  persisted as evidence.
- Tier 3 fingerprinting MAY be used only when neither Tier 1 nor Tier 2 inputs exist, and SHOULD be
  treated as lower confidence in coverage/operability reporting.

##### Tier 2 identity basis (normative)

When syslog is collected from a stored artifact (example: a captured syslog file that is included in the
run bundle or raw store), the identity basis MUST be:

- `source_type`
- `origin.host`
- `stream.name`: stable identifier of the stored artifact (example: `syslog`, `messages`, or a stable logical stream id)
- `stream.cursor`: stable per-record cursor within that stored artifact (example: `line_index` in the stored raw table,
  or byte offset of the line start), persisted as evidence

Rules:
- The cursor MUST be stable under reprocessing of the same stored artifact.
- Implementations MUST NOT use an ephemeral collector read offset unless it is persisted with the stored artifact
  and remains stable for that artifact under reprocessing.

### Canonicalization rules
To ensure cross-implementation determinism, implementations MUST use
JSON Canonicalization Scheme (RFC 8785, JCS) for serializing identity bases prior to hashing.

Normative definition:
- `identity_basis_canonical = canonical_json_bytes(identity_basis)` where `canonical_json_bytes`
  is RFC 8785 output (UTF-8; deterministic property order; minimal form; no BOM; no trailing newline).

Fallback policy:
- Implementations MUST vendor or invoke a known-good RFC 8785 implementation.
- Substituting a non-JCS “canonical JSON” serializer is not permitted unless it passes the
  JCS fixture suite byte-for-byte.

Pre-hash normalization (Tier 1 Windows, optional but deterministic if used):
- If applied, restrict to ASCII-safe transforms only:
  - `origin.host`, `origin.channel`, `origin.provider`: trim ASCII whitespace; lowercase ASCII.

### Timestamp handling
Store two timestamps when available:

- `time` / event time: when the event occurred at the origin (OpenTelemetry `Timestamp` concept).
- `metadata.observed_time` (optional): when the event was observed by the collector (OpenTelemetry `ObservedTimestamp` concept).

Rules:
- `metadata.event_id` MUST NOT incorporate `metadata.observed_time`.
- When mapping sources with limited precision (for example: seconds), `time` MUST be represented in ms since epoch with sub-second components set to zero. Emit `metadata.time_precision` as one of: `s|ms|us|ns`.

### Deduplication and replay
Normalization and storage MUST be idempotent w.r.t. `metadata.event_id`.

At-least-once delivery is expected: duplicates and replays can occur due to collector retries,
transport retries, restarts, or operator-initiated reprocessing.

Downstream deduplication is required. For this reason, `metadata.event_id` MUST be stable across
replays, and dedupe MUST be based on `metadata.event_id`.

### Deduplication scope and window (normative)

- **Scope:** Deduplication MUST be enforced for the normalized event store within a single run bundle
  (example: `runs/<run_id>/normalized/ocsf_events/`).
- **Non-goal:** The project does not require `metadata.event_id` to be globally unique across run
  bundles. Replays across different runs MAY intentionally produce the same `metadata.event_id`.
- **Window:** The deduplication window MUST be the full run window (unbounded within the run), i.e.,
  dedupe MUST consider all previously-emitted normalized events for the run, not only “recent” events.

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

### Collector restarts and checkpoints (Windows)
Windows collectors SHOULD persist read state using bookmarks/checkpoints to minimize duplicates on restart. Duplicates can still occur; identity and dedupe rules above remain authoritative.

### Checkpoint persistence (normative)

To reduce replay volume while preserving at-least-once correctness:

- The telemetry pipeline MUST persist **per-stream checkpoints** for sources that support a stable
  upstream cursor (example: Windows `EventRecordID`).
- Checkpoints MUST be stored inside the run bundle under `runs/<run_id>/logs/telemetry_checkpoints/`.
  The default layout SHOULD be:
  - `runs/<run_id>/logs/telemetry_checkpoints/<source_type>/<asset_id>/<stream_id>.json`
- Checkpoint updates MUST be atomic (write temp file, fsync, rename).
- The pipeline MUST flush checkpoints at least once every `N` events or `T` seconds (configurable).

### Checkpoint loss / corruption (normative)

If a checkpoint is missing or corrupt at restart:

- The pipeline MUST fall back to replaying from the start of the run window (subject to configured
  clock-skew tolerance), and MUST rely on the dedupe index to prevent duplicates in normalized output.
- The pipeline MUST record that checkpoint loss occurred in run-scoped logs and summary metrics
  (example: `telemetry_checkpoint_lost=true`, `telemetry_checkpoint_loss_total += 1`).

### EVTX reprocessing invariants
When reprocessing from EVTX:

- Extract Tier 1 identity inputs from the EVTX record system fields (do not rely on rendered message strings).
- Ensure `origin.host`, `origin.channel`, and `origin.record_id` reflect the *original* event when the EVTX record is a forwarded wrapper.

With these inputs, `metadata.event_id` remains stable across:
- live collection
- collector restarts
- EVTX reprocessing

## Consequences
- Stable event joins and reproducible scoring become practical.
- Requires collectors/normalizers to capture `source_event_id`-class fields (for example: Windows `EventRecordID`) whenever available.
- Tier 3 fallback is allowed but is explicitly weaker; coverage metrics should track how often it is used.