# Data contracts

This document defines the data contracts for Purple Axiom run artifacts. The goal is to make runs reproducible, diffable, and CI-validatable, while preserving enough provenance to support defensible detection evaluation.

Contracts are enforced through JSON Schemas in `docs/contracts/` plus a small set of cross-artifact invariants that cannot be expressed in JSON Schema alone.

## Goals

- Deterministic run artifacts suitable for regression testing and trending.
- Strong provenance and identity for every event and derived result.
- Clear separation between:
  - ground truth (what was executed)
  - telemetry (what was observed)
  - normalization (how telemetry was mapped)
  - detections (what fired)
  - scoring (how we judged outcomes)
  - reporting (how we communicate results)
- Forward-compatible extension points without schema sprawl.

## Non-goals

- Full validation of the entire OCSF specification payload. We only enforce a minimal required envelope plus provenance fields required for evaluation.
- Mandating a single telemetry source. Multiple sources may contribute events, provided they satisfy provenance requirements.

## Terminology

- Contract: A schema plus invariants for one artifact type.
- Run bundle: The folder `runs/<run_id>/` containing all artifacts for one execution.
- JSONL: JSON Lines, one JSON object per line.
- OCSF event: A normalized event that conforms to the required envelope fields and may include additional OCSF fields and vendor extensions.

## Contract registry

Schemas live in:

- `docs/contracts/manifest.schema.json`
- `docs/contracts/ground_truth.schema.json`
- `docs/contracts/criteria_pack_manifest.schema.json`
- `docs/contracts/criteria_entry.schema.json`
- `docs/contracts/criteria_result.schema.json`
- `docs/contracts/ocsf_event_envelope.schema.json`
- `docs/contracts/detection_instance.schema.json`
- `docs/contracts/summary.schema.json`
- `docs/contracts/mapping_coverage.schema.json` (optional)

Each schema includes a `contract_version` constant. The contract version is bumped only when the contract meaningfully changes (new required fields, semantics changes, or validation tightening).

## Run bundle layout

A run bundle is stored at `runs/<run_id>/` and follows this layout:

- `manifest.json` (single JSON object)
- `ground_truth.jsonl` (JSONL)
- `criteria/` (criteria pack snapshot + criteria evaluation results)
- `raw/` (telemetry as collected, plus source-native evidence where applicable)
- `runner/` (runner evidence: transcripts, executor metadata, cleanup verification)
- `normalized/` (normalized event store and mapping coverage)
- `bridge/` (Sigma-to-OCSF bridge artifacts: mapping pack snapshot, compiled plans, bridge coverage)
- `detections/` (detections emitted by evaluators)
- `scoring/` (joins and summary metrics)
- `report/` (HTML and JSON report outputs)
- `logs/` (debug logs; not considered long-term storage)

The manifest is the authoritative index for what exists in the bundle and which versions were used.

## Artifact contracts

### 1) Run manifest (`manifest.json`)

Purpose:
- Provides run-level provenance and reproducibility metadata.
- Pins versions and input hashes for deterministic replay.
- Lists target assets (lab endpoints) and optional artifact paths.
- Records lab provider identity and the resolved inventory snapshot used for the run.

Validation:
- Must validate against `manifest.schema.json`.

Key semantics:
- `run_id` is the unique identifier for the run bundle folder.
- `status` reflects the overall run outcome:
  - `success`: pipeline completed and artifacts are present and valid
  - `partial`: pipeline produced some outputs but one or more stages failed
  - `failed`: run failed early or outputs are not usable
- `inputs.*_sha256` are SHA-256 hashes of the exact configs used.

Recommended manifest additions (normative in schema when implemented):
- `lab.provider` (string): `manual | ludus | terraform | other`
- `lab.inventory_snapshot_sha256` (string): hash of the resolved inventory snapshot
- `lab.assets` (array): resolved assets used by the run (or pointer to `logs/lab_inventory_snapshot.json`)

### 2) Ground truth timeline (`ground_truth.jsonl`)

Purpose:
- Records what activity was executed, when, where, and with what expected telemetry.
- Serves as the canonical basis for scoring and failure classification.

Format:
- JSON Lines. Each line is one executed action.

Validation:
- Each line must validate against `ground_truth.schema.json`.

Key semantics:
- `timestamp_utc` is the start time of the action (UTC).
- `command_summary` must be safe and redacted; store `command_sha256` for integrity.
- Ground truth MUST include stable action identity:
  - `action_id` (unique within the run)
  - `action_key` (stable join key across runs for equivalent executions)
- `expected_telemetry_hints` MAY be present as coarse hints, but validation MUST prefer criteria evaluation when available.
- Cleanup is modeled as a staged lifecycle (invoke -> verify) and is always surfaced in reporting.
- Ground truth SHOULD include resolved target identity (hostname/ip/provider ref) so that the run remains interpretable even if the provider inventory changes later.
+### 2a) Criteria pack snapshot (`criteria/criteria.jsonl` + `criteria/manifest.json`)

Purpose:
- Externalizes “expected telemetry” away from Atomic YAML and away from ground truth authoring.
- Allows environment-specific expectations to be versioned and curated without changing execution definitions.

Format:
- `criteria/manifest.json` (single JSON object, pinned in run manifest)
- `criteria/criteria.jsonl` (JSONL; each line is one criteria entry)

Validation:
- `criteria/manifest.json` must validate against `criteria_pack_manifest.schema.json`.
- Each line of `criteria/criteria.jsonl` must validate against `criteria_entry.schema.json`.

Key semantics:
- Criteria entries are keyed by stable identifiers (minimum):
  - `engine` (atomic|caldera|custom)
  - `technique_id`
  - `engine_test_id` (Atomic GUID / Caldera ability ID)
- Criteria entries define expected signals in terms of normalized OCSF predicates (example: class_uid + optional constraints) and time windows relative to the action start.

### 2b) Criteria evaluation results (`criteria/results.jsonl`)

Purpose:
- Records whether expected signals were observed for each executed action.
- Provides the authoritative source for “missing telemetry” classification when criteria exist.

Format:
- JSON Lines. Each line is one evaluated action.

Validation:
- Each line must validate against `criteria_result.schema.json`.

Key semantics:
- Results reference `action_id` and `action_key` from ground truth.
- Results include a status (`pass|fail|skipped`) plus evidence references (example: counts of matching events, sample event_ids, query plans used).

### 2c) Runner evidence (`runner/`)

Purpose:
- Captures executor-level artifacts needed for defensible debugging and repeatability.

Minimum contents (recommended):
- `runner/actions/<action_id>/stdout.txt`
- `runner/actions/<action_id>/stderr.txt`
- `runner/actions/<action_id>/executor.json` (exit_code, duration, executor type/version, timestamps)
- `runner/actions/<action_id>/cleanup_verification.json` (checks + results)

Validation:
- `executor.json` and `cleanup_verification.json` SHOULD be schema validated when present.

### 3) Normalized events (`normalized/ocsf_events.*`)

Purpose:
- Provides a vendor-neutral event stream for detection evaluation.
- Enforces required provenance and stable event identity.

Validation:
- For JSONL, each line must validate against `ocsf_event_envelope.schema.json`.
- For Parquet, the required columns and types are enforced by the storage spec and validator logic (see `docs/spec/045_storage_formats.md`).

Required envelope (minimum):
- `time` (ms since epoch, UTC)
- `class_uid`
- `metadata.event_id` (stable, deterministic identifier; see `ADR-0002-event-identity-and-provenance.md`)
- `metadata.run_id`
- `metadata.scenario_id`
- `metadata.collector_version`
- `metadata.normalizer_version`
- `metadata.source_type`
- `metadata.source_event_id` (native upstream ID when meaningful; example: Windows `EventRecordID`)
- `metadata.identity_tier` (1|2|3; see ADR-0002)

Key semantics:
- The OCSF event payload may include additional fields (full OCSF and vendor extensions). The contract enforces minimum provenance only.
- `metadata.event_id` MUST be stable across re-runs when the source event and normalization inputs are identical.
- `metadata.event_id` MUST be computed without using ingest/observation time (at-least-once delivery and collector restarts are expected).
- `metadata.source_event_id` SHOULD be populated when the source provides a meaningful native identifier (example: Windows `EventRecordID`).
- For OCSF-conformant outputs, `metadata.uid` MUST equal `metadata.event_id`.

### 4) Detections (`detections/detections.jsonl`)

Purpose:
- Captures rule hits in a format suitable for scoring and reporting.

Format:
- JSON Lines. Each line is one detection instance.

Validation:
- Each line must validate against `detection_instance.schema.json`.

Key semantics:
- `rule_id` is stable for the rule and should not change across runs unless the rule itself changes.
- `matched_event_ids` must reference `metadata.event_id` values from the normalized store.
- `first_seen_utc` and `last_seen_utc` are event-time, not ingest-time.

Recommended (for reproducibility and gap attribution):
- Populate `rule_source = "sigma"` when the evaluator is Sigma-based.
- Store Sigma-to-OCSF bridge provenance under `extensions.bridge`:
  - `mapping_pack_id` and `mapping_pack_version` (router + field aliases)
  - `backend` (example: duckdb-sql, tenzir, other)
  - `compiled_at_utc`
  - `fallback_used` (boolean) when any `raw.*` fields were required
  - `unmapped_sigma_fields` (array) when compilation required dropping selectors or failing the rule
- Store the original Sigma `logsource` under `extensions.sigma.logsource` (verbatim), when available.

### 5) Scoring summary (`scoring/summary.json`)

Purpose:
- Single-file summary intended for trending, gating, and regressions.

Validation:
- Must validate against `summary.schema.json`.

Key semantics:
- Coverage is computed relative to executed techniques in ground truth.
- Latency metrics are derived from joins between ground truth action timestamps and detections.

### 6) Mapping coverage (`normalized/mapping_coverage.json`)

Purpose:
- Quantifies how well raw telemetry mapped into normalized classes and required fields.
- Supports failure classification, debugging, and prioritization.

Validation:
- Must validate against `mapping_coverage.schema.json` if present.

## Cross-artifact invariants

These are enforced by validators in code and CI. They are not fully expressible in JSON Schema.

Required invariants:
1. `manifest.run_id` must match:
   - `ground_truth.run_id` for every line
   - `normalized.metadata.run_id` for every event
   - `detections.run_id` for every detection
   - `summary.run_id`
   - `criteria.results.run_id` for every criteria result (when present)
2. `manifest.scenario.scenario_id` must match:
   - `ground_truth.scenario_id` for every line
   - `normalized.metadata.scenario_id` for every event (unless explicitly multi-scenario)
   - `summary.scenario_id`
3. Time bounds:
   - All `ground_truth.timestamp_utc` and normalized event times must be within `[manifest.started_at_utc, manifest.ended_at_utc]` when `ended_at_utc` is present, allowing a small tolerance for clock skew (configurable).
4. Event identity:
   - `metadata.event_id` must be unique within a run bundle for normalized events.
5. Referential integrity:
   - `detections.matched_event_ids` must exist in the normalized store for that run.
   - `criteria.results.action_id` must reference an `action_id` present in `ground_truth.jsonl` (when present).
   - `criteria.results.action_key` must equal the corresponding ground truth `action_key` (when present).
6. Deterministic ordering requirements (for diffability):
   - When writing JSONL outputs, lines are sorted deterministically (see storage spec).
   - When writing Parquet, within-file ordering is deterministic (see storage spec).

Optional invariants (recommended when signatures are enabled):
- `checksums.txt` includes hashes for all long-term artifacts.
- `signature.ed25519` signs `checksums.txt` using a run signing key.

## Versioning and compatibility policy

Contract versioning:
- Patch: documentation-only changes or loosening constraints that do not change meaning.
- Minor: additive changes that preserve backward compatibility (new optional fields, new extensions).
- Major: breaking changes (new required fields, meaning changes, tighter validation that can invalidate existing artifacts).

Compatibility expectations:
- The pipeline must be able to read at least the previous minor contract version for one release window.
- Report generators must accept older run bundles and emit a clear warning when fields are missing.

## Extensions and vendor fields

Strict artifacts (manifest, ground truth, detections, summary) are intentionally `additionalProperties: false` with a single extension point:

- `extensions`: object, free-form, reserved for forward-compatible additions.

Normalized events:
- Are intentionally permissive to allow full OCSF payloads and source-specific structures.
- Must still satisfy required provenance and identity fields.

## Redaction and sensitive data

- Raw commands and secrets must not be written into run bundles.
- `command_summary` is always redacted-safe. If a full command is needed for debugging, it should remain in volatile logs and never enter long-term storage.
- When storing raw telemetry, apply a configurable redaction policy for known sensitive fields (credentials, tokens, PII) before promotion into long-term stores.

## Validation workflow

Recommended validation stages:
1. Schema validation of each artifact (JSON and per-line JSONL).
2. Cross-artifact invariants check.
3. Storage invariants check (Parquet schema, partition structure, deterministic ordering).
4. Optional signature verification.

CI gates should fail closed on contract violations.
