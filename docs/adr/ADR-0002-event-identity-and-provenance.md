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

### Canonicalization rules
To ensure cross-implementation determinism, `identity_basis_canonical` MUST be serialized using canonical JSON:

- UTF-8 encoding
- Sorted keys (lexicographic)
- No insignificant whitespace
- Numbers rendered in base-10 without leading zeros
- Strings normalized:
  - trim surrounding whitespace
  - lowercase for host/channel/provider identifiers

### Timestamp handling
Store two timestamps when available:

- `time` / event time: when the event occurred at the origin (OpenTelemetry `Timestamp` concept).
- `metadata.observed_time` (optional): when the event was observed by the collector (OpenTelemetry `ObservedTimestamp` concept).

Rules:
- `metadata.event_id` MUST NOT incorporate `metadata.observed_time`.
- When mapping sources with limited precision (for example: seconds), `time` MUST be represented in ms since epoch with sub-second components set to zero. Emit `metadata.time_precision` as one of: `s|ms|us|ns`.

### Deduplication and replay
Normalization and storage MUST be idempotent w.r.t. `metadata.event_id`.

- If multiple events with the same `metadata.event_id` appear in a run, the normalizer MUST treat later instances as duplicates.
- The normalized event store MUST contain at most one canonical row per `metadata.event_id`.
- The pipeline SHOULD emit duplicate counters for observability and troubleshooting (for example: `duplicates_dropped_total` per source_type/channel).

### Collector restarts and checkpoints (Windows)
Windows collectors SHOULD persist read state using bookmarks/checkpoints to minimize duplicates on restart. Duplicates can still occur; identity and dedupe rules above remain authoritative.

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