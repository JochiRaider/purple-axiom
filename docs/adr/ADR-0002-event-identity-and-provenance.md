# ADR-0002: Event identity and provenance

## Status
Proposed

## Context
We must correlate detections to ground truth actions while preserving source traceability.

## Decision (seed)
- Each normalized event gets an event_id (stable hash of [source + timestamp + provider event id + host] or equivalent).
- Provenance fields required on every event: run_id, scenario_id, collector_version, normalizer_version.

## Consequences
- Enables deterministic joins for scoring.
- Requires careful handling of timestamp precision and source IDs.
