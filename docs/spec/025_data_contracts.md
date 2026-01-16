---
title: Data contracts
description: Defines data contracts, schemas, and invariants for Purple Axiom run artifacts.
status: draft
---

# Data contracts

This document defines the data contracts for Purple Axiom run artifacts. The goal is to make runs
reproducible, diffable, and CI-validatable while preserving enough provenance to support defensible
detection evaluation.

Contracts are enforced through JSON Schemas in `docs/contracts/` plus a small set of cross-artifact
invariants that cannot be expressed in JSON Schema alone.

## Overview

This spec defines the artifact schemas, run bundle layout, and cross-artifact invariants that make
runs reproducible and comparable. It covers the normative requirements for manifest status, ground
truth identity, normalized event envelopes, and optional signing.

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

- Full validation of the entire OCSF specification payload. We only enforce a minimal required
  envelope plus provenance fields required for evaluation.
- Mandating a single telemetry source. Multiple sources may contribute events, provided they satisfy
  provenance requirements.

## Terminology

- Contract: A schema plus invariants for one artifact type.
- Run bundle: The folder `runs/<run_id>/` containing all artifacts for one execution.
- JSONL: JSON Lines, one JSON object per line.
- OCSF event: A normalized event that conforms to the required envelope fields and may include
  additional OCSF fields and vendor extensions.

## Contract registry

Schemas live in:

- `docs/contracts/manifest.schema.json`
- `docs/contracts/ground_truth.schema.json`
- `docs/contracts/action_descriptor.schema.json`
- `docs/contracts/runner_executor_evidence.schema.json`
- `docs/contracts/cleanup_verification.schema.json`
- `docs/contracts/criteria_pack_manifest.schema.json`
- `docs/contracts/criteria_entry.schema.json`
- `docs/contracts/criteria_result.schema.json`
- `docs/contracts/ocsf_event_envelope.schema.json`
- `docs/contracts/detection_instance.schema.json`
- `docs/contracts/summary.schema.json`
- `docs/contracts/telemetry_validation.schema.json`
- `docs/contracts/duckdb_conformance_report.schema.json`
- `docs/contracts/pcap_manifest.schema.json`
- `docs/contracts/netflow_manifest.schema.json`
- `docs/contracts/mapping_profile_input.schema.json`
- `docs/contracts/mapping_profile_snapshot.schema.json`
- `docs/contracts/mapping_coverage.schema.json`
- `docs/contracts/bridge_router_table.schema.json`
- `docs/contracts/bridge_mapping_pack.schema.json`
- `docs/contracts/bridge_compiled_plan.schema.json`
- `docs/contracts/bridge_coverage.schema.json`

Each schema includes a `contract_version` constant. The contract version is bumped only when the
contract meaningfully changes (new required fields, semantics changes, or validation tightening).

## Validation engine and publish gates

This section is normative for how Purple Axiom enforces artifact contracts at runtime. It defines
JSON Schema dialect requirements, reference resolution rules, deterministic error reporting, and the
minimum validation scope at stage publish boundaries.

This section uses the term "contract validation" to refer to schema validation of artifacts. It is
distinct from the pipeline stage named `validation`, which refers to criteria evaluation and cleanup
verification.

### Definitions

- Contract validation: Validation of an artifact instance against its associated JSON Schema
  contract and any contract-scoped invariants defined by this spec.
- Publish gate: The final validation step a stage performs after writing outputs in staging and
  before atomically publishing them into the run bundle.
- Runtime canary: A stage-executed check that validates runtime behavior or data quality properties
  that are not expressible as JSON Schema (for example, raw Windows Event Log mode), and whose
  outcome is recorded in health artifacts.

### JSON Schema dialect (normative)

- All JSON Schema contracts under `docs/contracts/` MUST be authored for JSON Schema Draft 2020-12.
- Implementations MUST use a validator that supports Draft 2020-12 semantics.
- If a contract schema declares a `$schema` value that is not Draft 2020-12, the implementation MUST
  treat this as a configuration error and MUST fail closed for any stage that requires the affected
  contract.

### Reference resolution (local-only, normative)

To preserve determinism and prevent network-dependent behavior:

- Implementations MUST resolve `$ref` using local, repository-supplied schema resources only.
- Implementations MUST NOT fetch remote references over the network (for example, `http://` or
  `https://`) during validation.
- Implementations MUST fail closed if any `$ref` resolves outside the local contract registry root
  (`docs/contracts/`) or an explicitly embedded equivalent.
- Relative `$ref` values MUST be resolved relative to the referencing schema document location.

### Deterministic error ordering and error caps (normative)

Contract validation outputs MUST be deterministic to support regression testing and stable failure
classification.

For any artifact that fails contract validation, implementations MUST produce a bounded list of
validation errors with deterministic ordering:

Minimum error fields (per error):

- `artifact_path`: run-relative path using POSIX separators (`/`)
- `contract`: contract identifier (for example, the schema filename)
- `instance_path`: JSON Pointer to the failing instance location
- `schema_path`: JSON Pointer to the failing schema location
- `message`: human-readable error message
- `line_number`: REQUIRED for JSONL validation errors (1-indexed), omitted otherwise

Ordering (normative):

- Errors MUST be sorted by the tuple below using UTF-8 byte order (no locale):
  1. `artifact_path`
  1. `line_number` (treat missing as `0`)
  1. `instance_path`
  1. `schema_path`
  1. `message`

Error caps (normative):

- Implementations MUST apply a maximum error cap per artifact (`max_errors_per_artifact`).
- If not configured, `max_errors_per_artifact` MUST default to `50`.
- When the cap is reached, implementations MUST:
  - set `errors_truncated=true` in the validation summary, and
  - stop collecting additional errors for that artifact (deterministically).

### Validation scope and timing

#### Publish-gate contract validation (required)

For any stage that publishes contract-backed artifacts:

- The stage MUST write outputs to `runs/<run_id>/.staging/<stage_id>/...` and MUST perform contract
  validation as a publish gate before atomic publish.
- A stage MUST NOT publish contract-invalid artifacts into their final locations under
  `runs/<run_id>/`.

Validation by artifact type:

- JSON artifacts (single JSON object):
  - The stage MUST validate the full document against its contract schema before publish.
- JSONL artifacts:
  - The stage MUST validate each line (each JSON object) against its contract schema.
  - The stage MAY validate incrementally while writing the JSONL file, but the publish gate MUST
    ensure the complete file has been validated.
- Parquet datasets:
  - The stage MUST validate the dataset schema (required columns, types, and nullability rules as
    specified) before publish.
  - Row-by-row validation is not required at publish time unless a contract explicitly requires it.

Minimum publish-gate coverage (v0.1):

- When produced, the following artifacts MUST be contract-validated at publish time by the stage
  that publishes them:
  - `manifest.json`
  - `ground_truth.jsonl`
  - `runner/**` artifacts that have contracts (for example, executor evidence, cleanup verification)
  - `criteria/**` artifacts that have contracts (criteria pack snapshot, criteria results)
  - `normalized/**` artifacts that have contracts (OCSF event envelope for JSONL outputs, mapping
    coverage, mapping profile snapshot)
  - `bridge/**` artifacts that have contracts (router tables, mapping pack snapshots, compiled
    plans, bridge coverage)
  - `detections/detections.jsonl`
  - `scoring/summary.json`
  - `logs/telemetry_validation.json` when telemetry validation is enabled
  - any optional placeholder artifacts that are emitted in v0.1 (for example, PCAP or NetFlow
    manifests) when present

Failure behavior (normative):

- If publish-gate contract validation fails for a required artifact, the stage MUST record a failed
  stage outcome with a stable `reason_code`, and MUST follow the configured `fail_mode` semantics
  (`fail_closed` halts the run; `warn_and_skip` permits continuation with deterministic degradation
  evidence).

#### Runtime canaries (required only where specified)

Runtime canaries validate runtime behavior and data quality properties that are not expressible in
JSON Schema. They do not replace publish-gate contract validation.

- A stage MUST execute any runtime canaries that are required by the applicable stage specs when the
  corresponding feature is enabled.
- Canary outcomes MUST be recorded as stage outcomes (including dotted substages where specified).

v0.1 baseline canaries (non-exhaustive; see operability and telemetry specs for full details):

- Telemetry Windows Event Log raw mode canary (`telemetry.windows_eventlog.raw_mode`)
- Telemetry checkpointing storage integrity (`telemetry.checkpointing.storage_integrity`)
- Resource budget enforcement and footprint reporting where required

Authoritative definitions for these canaries, reason codes, and required evidence pointers are in
the [operability spec](110_operability.md) and the
[telemetry pipeline spec](040_telemetry_pipeline.md).

## Run bundle layout

A run bundle is stored at `runs/<run_id>/` and follows this layout:

- `manifest.json` (single JSON object)
- `ground_truth.jsonl` (JSONL)
- `plan/` (v0.2+; compiled plan graph and expansion manifests)
- `criteria/` (criteria pack snapshot + criteria evaluation results)
- `raw/` (telemetry as collected, plus source-native evidence where applicable)
  - `raw/pcap/` (optional; placeholder contract in v0.1)
  - `raw/netflow/` (optional; placeholder contract in v0.1)
- `runner/` (runner evidence: transcripts, executor metadata, cleanup verification)
- `normalized/` (normalized event store and mapping coverage)
- `bridge/` (Sigma-to-OCSF bridge artifacts: mapping pack snapshot, compiled plans, bridge coverage)
- `detections/` (detections emitted by evaluators)
- `scoring/` (joins and summary metrics)
- `report/` (HTML and JSON report outputs)
- `logs/` (structured operability summaries and debug logs; not considered long-term storage)
  - `logs/health.json` (when enabled; see the [operability spec](110_operability.md))
  - `logs/telemetry_validation.json` (when telemetry validation is enabled)

The manifest is the authoritative index for what exists in the bundle and which versions were used.

## Artifact contracts

### Run manifest

Purpose:

- Provides run-level provenance and reproducibility metadata.
- Pins versions and input hashes for deterministic replay.
- Lists target assets (lab endpoints) and optional artifact paths.
- Records lab provider identity and the resolved inventory snapshot used for the run.

Validation:

- Must validate against `manifest.schema.json`.

Key semantics:

- `run_id` is the unique identifier for the run bundle folder.

- `run_id` MUST be a UUID string (RFC 4122, canonical hyphenated form) and MUST be validated as a
  UUID.

- `run_id` is unique per execution and MUST NOT be reused across replays.

- Stable joins across replays MUST use `action_key` and other stable basis fields; `action_key` MUST
  NOT incorporate `run_id`.

- `status` reflects the overall run outcome:

  - `success`: pipeline completed and artifacts are present and valid
  - `partial`: pipeline produced some outputs but one or more stages failed
  - `failed`: run failed early or outputs are not usable

- `inputs.*_sha256` are SHA-256 hashes of the exact configs used.

- `scenario.scenario_id` is the stable scenario identifier for the run.

- v0.1 run bundles MUST be single-scenario. Multi-scenario manifests are reserved for a future
  release.

Status derivation (normative):

- Implementations MUST compute an effective outcome for each enabled pipeline stage (a "stage
  outcome").
- A stage outcome MUST include: `stage` (stable identifier), `status`
  (`success | failed | skipped`), `fail_mode` (`fail_closed | warn_and_skip`), and an optional
  `reason_code` (stable token).
- `manifest.status` MUST be derived from the set of stage outcomes:
  - `failed` if any stage has `status=failed` and `fail_mode=fail_closed`
  - else `partial` if any stage has `status=failed`
  - else `success`
- When `operability.health.emit_health_files=true`, stage outcomes MUST also be written to
  `runs/<run_id>/logs/health.json` (minimum schema in the [operability spec](110_operability.md)).

Recommended manifest additions (normative in schema when implemented):

- `lab.provider` (string): `manual | ludus | terraform | other`
- `lab.inventory_snapshot_sha256` (string): hash of the resolved inventory snapshot
- `lab.assets` (array): resolved assets used by the run (or pointer to
  `logs/lab_inventory_snapshot.json`)
- `normalization.ocsf_version` (string): pinned OCSF version used by the normalizer for this run.
  - When `normalized/mapping_profile_snapshot.json` is present, `normalization.ocsf_version` SHOULD
    match `mapping_profile_snapshot.ocsf_version`.

Plan model provenance (v0.2+; normative when implemented):

- `plan.model_version` (string): the plan execution model version used to compile the run plan.
  - v0.1: absent (implicit single-action plan).
  - When `plan/expanded_graph.json` is present, this field MUST be present and MUST be a semantic
    version string (example: `0.2.0`).
- `plan.expanded_graph_sha256` (string): SHA-256 of the exact bytes of `plan/expanded_graph.json` as
  published in the run bundle.
  - Purpose: detect plan compilation drift within a run bundle and provide an audit pointer for
    deterministic `action_id` generation.

Stage outcomes (v0.1 baseline expectations):

- The following table defines the baseline stage behaviors for v0.1. Implementations MAY add
  additional stages, but MUST keep stage identifiers stable and must surface failures via stage
  outcomes.

| Stage           | Typical `fail_mode` (v0.1 default)                     | Minimum artifacts when enabled                                 | Notes                                                                                                              |
| --------------- | ------------------------------------------------------ | -------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| `lab_provider`  | `fail_closed`                                          | `manifest.json`                                                | Failure to resolve targets deterministically is fatal.                                                             |
| `runner`        | `fail_closed`                                          | `ground_truth.jsonl`, `runner/**`                              | If stable `asset_id` resolution fails, the run MUST fail closed.                                                   |
| `telemetry`     | `fail_closed`                                          | `raw_parquet/**` (when enabled), `manifest.json`               | If required Windows sources are missing (e.g., Sysmon), the run MUST fail closed unless the scenario exempts them. |
| `normalization` | `fail_closed` (when `normalization.strict_mode: true`) | `normalized/ocsf_events.*`, `normalized/mapping_coverage.json` | In `warn_and_skip` style modes (if introduced later), skipped and unmapped counts MUST still be reported.          |
| `validation`    | `warn_and_skip` (default)                              | `criteria/results.jsonl`, `criteria/manifest.json`             | MUST emit a result row per selected action; un-evaluable actions MUST be `skipped` with `reason_code`.             |
| `detection`     | `fail_closed` (default)                                | `detections/detections.jsonl`, `bridge/coverage.json`          | MUST record non-executable rules with stable reasons (compiled plans and coverage).                                |
| `scoring`       | `fail_closed`                                          | `scoring/summary.json`                                         | A missing or invalid summary is fatal when scoring is enabled.                                                     |
| `reporting`     | `fail_closed`                                          | `report/**`                                                    | Reporting failures are fatal when reporting is enabled.                                                            |
| `signing`       | `fail_closed` (when enabled)                           | `signatures/**`                                                | If signing is enabled and verification fails or is indeterminate, the run MUST fail closed.                        |

### Ground truth timeline

Purpose:

- Records what activity was executed, when, where, and with what expectations.
- Serves as the canonical basis for scoring and failure classification.

Format:

- JSON Lines. Each line is one action instance, including its lifecycle phase outcomes.

Validation:

- Each line must validate against `ground_truth.schema.json`.

Generation source (normative):

- The runner MUST derive ground truth entries from a structured execution record produced at runtime
  (for example, an ATTiRe-style JSON execution log for Atomic). For Atomic, the structured execution
  record is stored as `runner/actions/<action_id>/attire.json` (see the
  [Atomic Red Team executor integration spec](032_atomic_red_team_executor_integration.md)).
- The runner MUST write the structured execution record under `runner/actions/<action_id>/` and
  treat `ground_truth.jsonl` as a derived, stable join layer.

Key semantics:

- `timestamp_utc` is the start time of the action (UTC).

Lifecycle semantics (normative):

- Each ground truth entry MUST include:

- `idempotence` (`idempotent | non_idempotent | unknown`), and `lifecycle.phases[]` (ordered phase
  records).

  - `lifecycle.phases[]` MUST be ordered by the phase sequence: `prepare`, `execute`, `revert`,
    `teardown`.
  - Each phase record MUST include:
    - `phase` (`prepare | execute | revert | teardown`)
    - `phase_outcome` (`success | failed | skipped`)
    - `started_at_utc` and `ended_at_utc` (UTC)
    - `timestamp_utc` MUST equal `lifecycle.phases[0].started_at_utc` when the lifecycle is present.

Revert vs teardown (normative):

- `revert` MUST represent undoing execute-side effects so the action can be executed again on the
  same target.
- `teardown` MUST represent removing per-action prerequisites (when applicable) and recording
  cleanup verification outcomes.
- Implementations MUST NOT conflate revert and teardown as a single "cleanup" outcome; they are
  recorded separately to avoid leaving targets in a non-re-runnable state and to avoid deleting
  prerequisites shared by other actions.

Idempotence defaults (normative):

- If `idempotence` is `unknown`, implementations MUST treat the action as `non_idempotent` for
  safety (do not assume it is safe to re-run without a successful `revert`).

### Stable action identity

This section defines `action_id` and `action_key`.

- `action_id` MUST be unique within a run. It is a run-scoped correlation key for per-run artifacts
  and MUST NOT be used for cross-run comparisons.
- `action_key` MUST be a stable join key for equivalent executions across runs.

`action_id` format by plan model version (normative):

- v0.1 (single-action plan): implementations MUST emit legacy ordinal identifiers of the form
  `s<positive_integer>` (example: `s1`).
- v0.2+ (multi-action plan model): `action_id` MUST equal the deterministic action instance
  identifier (`action_instance_id`) defined below. Legacy `sN` identifiers are v0.1-only and MUST
  NOT be emitted by v0.2+ producers.

Deterministic action instance id (`action_instance_id`) (v0.2+):

`action_instance_id` MUST be computed as:

- Prefix: `pa_aid_v1_`
- Digest: `sha256(canonical_json_bytes(action_instance_basis_v1))` truncated to 128 bits (32 hex
  chars)

`action_instance_basis_v1` MUST include, at minimum:

- `v`: 1
- `run_id`
- `node_ordinal` (integer; zero-based ordinal in the runner's deterministic expanded plan order)
- `engine`
- `template_id` (stable procedure identifier; see Plan Execution Model)
- `technique_id`
- `engine_test_id`
- `parameters.resolved_inputs_sha256`
- `target_asset_id`

Notes (normative):

- `node_ordinal` MUST be stable for equivalent plan compilation inputs (same plan template + same
  axis enumeration + same target resolution) and MUST NOT depend on runtime start time or scheduler
  timing.
- `action_id` MUST be derived from the basis above; it MUST NOT be assigned from a mutable counter
  at runtime in v0.2+.

`action_key` (v1) MUST be computed as:

- `sha256(canonical_json_bytes(action_key_basis_v1))`

Where `action_key_basis_v1` MUST include, at minimum:

- `v`: 1
- `engine`
- `technique_id`
- `engine_test_id`
- `parameters.resolved_inputs_sha256`
- `target_asset_id`

Target semantics (normative):

- `target_asset_id` MUST be a **stable Purple Axiom logical asset id** (matching the
  `lab.assets[].asset_id` namespace) and MUST NOT be a provider-mutable identifier (for example:
  ephemeral VM IDs or cloud instance IDs).
- If a provider cannot resolve stable `asset_id`s for the run targets, the pipeline MUST fail closed
  before producing any artifact that depends on `action_key`.

Canonical JSON (normative):

- Any occurrence of `canonical_json(...)` in this spec MUST mean:
  - `canonical_json_bytes(value)` = the exact UTF-8 byte sequence produced by JSON Canonicalization
    Scheme (RFC 8785, JCS).
- Inputs to `canonical_json_bytes` MUST satisfy the RFC 8785 constraints (I-JSON subset), including
  (non-exhaustive): finite numbers only (no NaN or Infinity), unique object member names, and valid
  Unicode strings.
- Implementations MUST NOT substitute "native or default JSON serialization" for JCS.
- Hashing primitive:
  - `sha256_hex = lower_hex(sha256(canonical_json_bytes(value)))`
  - No BOM, no trailing newline; hash is over bytes only.

Failure policy (normative):

- If a value cannot be canonicalized per RFC 8785, the pipeline MUST fail closed for any artifact
  depending on the affected hash.

Fallback when a full JCS library is unavailable:

- Implementations MUST vendor or invoke a known-good RFC 8785 implementation (preferred).
- For **PA JCS Integer Profile** hash bases only, an implementation MAY use a simplified encoder
  that is provably identical to JCS for this restricted data model:
  - Numbers MUST be signed integers within IEEE-754 "safe integer" range (|n| \<=
    9,007,199,254,740,991).
  - No floating point numbers are permitted.
  - Object keys MUST be strings, unique, and sorted lexicographically by Unicode scalar value.
  - Strings MUST be emitted using standard JSON escaping rules with minimal escaping.
  - No insignificant whitespace; UTF-8; no BOM; no trailing newline.
- Any fallback encoder MUST pass the JCS fixture tests under `tests/fixtures/jcs/` byte-for-byte.

### Inputs and reproducible hashing

`parameters.input_args_redacted`:

- Runner inputs with secrets removed or replaced with references (never store plaintext secrets).

`parameters.input_args_sha256` (optional):

- Hash of canonical JSON of the redacted input arguments object (`input_args_redacted`), after
  normalization of key ordering.
- Purpose: detect runner invocation drift independent of template resolution.

`parameters.resolved_inputs_sha256` (required):

- Hash of canonical JSON of the resolved inputs used for execution after variable interpolation and
  defaults are applied, with secrets still redacted or represented as references.
- Purpose: stable basis for `action_key` and for cross-run regression comparisons.

### Command summary, redaction, and command integrity

`command_summary`:

- MUST be safe and redacted.
- MUST be derived from a tokenized command representation (executable + argv tokens) produced by the
  runner, not from ad-hoc string parsing.
- MUST be produced under a versioned redaction policy that is pinned in run artifacts (policy id and
  policy hash).

Redaction policy (normative):

- The runner MUST support a deterministic redaction policy as specified in the
  [redaction policy ADR](../adr/ADR-0003-redaction-policy.md).
- The runner MUST apply the effective policy when `security.redaction.enabled: true`.
- When `security.redaction.enabled: false`, the runner MUST NOT emit unredacted secrets into
  standard long-term artifacts. It MUST either withhold sensitive fields (deterministic
  placeholders) or write them only to a quarantined unredacted evidence location when explicitly
  enabled by config.
- The applied posture (`enabled` vs `disabled`) MUST be recorded in run metadata so downstream
  tooling does not assume redacted-safe content.

When redaction is enabled, the policy MUST include:

- a flag or value model for common secret-bearing arguments (for example: `--token`, `-Password`,
  `-EncodedCommand`)
- regex-based redaction for high-risk token patterns (JWT-like strings, long base64 blobs, long hex
  keys, connection strings)
- deterministic truncation rules (fixed max token length and fixed max summary length)
- The normative policy definition (including "redacted-safe", fail-closed behavior, limits, and
  required test vectors) is defined in the
  [redaction policy ADR](../adr/ADR-0003-redaction-policy.md).
- Runs SHOULD snapshot the effective policy into the run bundle (recommended:
  `runs/<run_id>/security/redaction_policy_snapshot.json`) and record its sha256 in run provenance.

`extensions.command_sha256`:

- OPTIONAL integrity hash for the executed command, computed over a redacted canonical command
  object.
- MUST NOT be used as part of `action_key` (it is an integrity aid, not identity).

`extensions.command_sha256` (v1) MUST be computed as:

- Build `command_material_v1_redacted`:
  - `v`: 1
  - `executor`: normalized executor name (for example: `powershell`, `cmd`, `bash`)
  - `executable`: normalized basename (for example: `powershell.exe`)
  - `argv_redacted`: argv tokens after applying the redaction policy (preserve token order)
  - OPTIONAL: `cwd`, `stdin_present`, `env_refs` (names only; never values)
- Compute `sha256(canonical_json(command_material_v1_redacted))` and encode as 64 hex characters.

Invariants:

- If `parameters.resolved_inputs_sha256` is unchanged and the runner redaction policy is unchanged,
  `extensions.command_sha256` SHOULD remain stable for the same executor implementation.
- A change in redaction policy MUST be reflected in `extensions.redaction_policy_id` and/or
  `extensions.redaction_policy_sha256` so that hash drift is explainable.

### Expected telemetry hints and criteria references

- `criteria_ref` SHOULD be present when a criteria entry is selected for the action.
- `expected_telemetry_hints` MAY be present as coarse hints, but evaluation MUST prefer criteria
  evaluation when available.

Population rules:

- If a criteria entry is selected for the action, the runner MUST populate:
  - `criteria_ref` (pack id and version + entry id)
  - `expected_telemetry_hints` as a lossy projection of the selected criteria entry (for example:
    expected OCSF class_uids and preferred sources).
- If no criteria entry is selected, the runner MAY populate `expected_telemetry_hints` from a
  separate telemetry hints pack or from lab instrumentation defaults.

Cleanup:

- Cleanup is modeled as a staged lifecycle (invoke -> verify) and is always surfaced in reporting.
- Ground truth SHOULD include resolved target identity (hostname, IPs, and/or stable labels) so
  action intent remains interpretable even if provider inventory changes later.

### Criteria pack snapshot

This artifact includes `criteria/criteria.jsonl` and `criteria/manifest.json`.

Purpose:

- Externalizes "expected telemetry" away from Atomic YAML and away from ground truth authoring.
- Allows environment-specific expectations to be versioned and curated without changing execution
  definitions.

Format:

- `criteria/manifest.json` (single JSON object, pinned in run manifest)
- `criteria/criteria.jsonl` (JSONL; each line is one criteria entry)

Validation:

- `criteria/manifest.json` must validate against `criteria_pack_manifest.schema.json`.
- Each line of `criteria/criteria.jsonl` must validate against `criteria_entry.schema.json`.

Key semantics:

- Criteria entries are keyed by stable identifiers (minimum):
  - `engine` (atomic | caldera | custom)
  - `technique_id`
  - `engine_test_id` (Atomic GUID or Caldera ability ID)
- Criteria entries define expected signals in terms of normalized OCSF predicates (example:
  class_uid + optional constraints) and time windows relative to the action start.

### Criteria evaluation results

This artifact is stored at `criteria/results.jsonl`.

Purpose:

- Records whether expected signals were observed for each executed action.
- Provides the authoritative source for "missing telemetry" classification when criteria exist.

Format:

- JSON Lines. Each line is one evaluated action.

Validation:

- Each line must validate against `criteria_result.schema.json`.

Key semantics:

- Results reference `action_id` and `action_key` from ground truth.
- Results include a status (`pass | fail | skipped`) plus evidence references (example: counts of
  matching events, sample event_ids, query plans used).
- The evaluator MUST emit exactly one result row per selected ground truth action.
  - If an action cannot be evaluated (missing telemetry, mapping gaps, executor error, and so on),
    the evaluator MUST emit `status=skipped` and MUST set a stable `reason_code`.
- The evaluator MUST NOT suppress results silently; skipped actions MUST remain visible in the
  output.

### Runner evidence

Purpose:

- Captures executor-level artifacts needed for defensible debugging and repeatability.

Minimum contents (recommended):

- `runner/actions/<action_id>/stdout.txt`
- `runner/actions/<action_id>/stderr.txt`
- `runner/actions/<action_id>/executor.json` (exit_code, duration, executor type or version,
  timestamps)
- `runner/actions/<action_id>/attire.json` (when structured execution logging is enabled; Atomic
  uses ATTiRe)
- `runner/actions/<action_id>/atomic_test_extracted.json` (optional; Atomic template snapshot)
- `runner/actions/<action_id>/atomic_test_source.yaml` (optional; Atomic template snapshot)
- `runner/actions/<action_id>/cleanup_verification.json` (checks + results)

note: see [Atomic Red Team executor integration](032_atomic_red_team_executor_integration.md)
Validation:

- `executor.json` and `cleanup_verification.json` SHOULD be schema validated when present.

### Network sensor placeholders

This section covers `raw/pcap/` and `raw/netflow/`.

Purpose:

- Reserve stable artifact locations and contracts for network telemetry (pcap and netflow) without
  requiring capture or ingestion in v0.1.

When present:

- `raw/pcap/manifest.json` MUST validate against `pcap_manifest.schema.json` and MUST enumerate the
  capture files written under `raw/pcap/`.
- `raw/netflow/manifest.json` MUST validate against `netflow_manifest.schema.json` and MUST
  enumerate the flow log files written under `raw/netflow/`.

Absence semantics:

- These directories and manifests MAY be absent.
- If telemetry config enables a network sensor source but the active build has no implementation for
  it, the telemetry stage MUST fail closed with `reason_code=source_not_implemented`.

### Normalized events

This artifact is stored under `normalized/ocsf_events.*`.

Purpose:

- Provides a vendor-neutral event stream for detection evaluation.
- Enforces required provenance and stable event identity.

Validation:

- For JSONL, each line must validate against `ocsf_event_envelope.schema.json`.
- For Parquet, the required columns and types are enforced by the storage spec and validator logic
  (see the [storage formats spec](045_storage_formats.md)).

Required envelope (minimum):

- `time` (ms since epoch, UTC)
- `class_uid`
- `metadata.event_id` (stable, deterministic identifier; see the
  [event identity ADR](../adr/ADR-0002-event-identity-and-provenance.md))
- `metadata.run_id`
- `metadata.scenario_id`
- `metadata.collector_version`
- `metadata.normalizer_version`
- `metadata.source_type`
- `metadata.source_event_id` (native upstream ID when meaningful; example: Windows `EventRecordID`)
- `metadata.identity_tier` (1 | 2 | 3; see the event identity ADR)

Key semantics:

- The OCSF event payload may include additional fields (full OCSF and vendor extensions). The
  contract enforces minimum provenance only.
- `metadata.event_id` MUST be stable across re-runs when the source event and normalization inputs
  are identical.
- `metadata.event_id` MUST be computed without using ingest or observation time (at-least-once
  delivery and collector restarts are expected).
- `metadata.source_event_id` SHOULD be populated when the source provides a meaningful native
  identifier (example: Windows `EventRecordID`).
- For OCSF-conformant outputs, `metadata.uid` MUST equal `metadata.event_id`.

### Normalization mapping profile snapshot

This artifact is stored at `normalized/mapping_profile_snapshot.json`.

Purpose:

- Records the exact normalization mapping material used to produce the OCSF event store for this
  run.
- Enables deterministic replay and CI drift detection (mapping inputs are pinned and hashed).

Validation:

- Must validate against `mapping_profile_snapshot.schema.json` when present.

Key semantics (normative):

- The snapshot MUST be immutable within a run bundle and MUST be treated as Tier 0 provenance.
- The snapshot MUST include stable SHA-256 hashes over the mapping material so that mapping drift is
  detectable even when filenames are unchanged.
- The snapshot MUST record upstream origins when derived from external projects (example: Security
  Lake transformation library custom source mappings).
- The "mapping material" hashed and recorded by the snapshot MUST correspond to the mapping pack
  boundary defined in `docs/mappings/ocsf_mapping_profile_authoring_guide.md`.

Minimum fields (normative):

- `mapping_profile_id`, `mapping_profile_version`, `mapping_profile_sha256`
- `ocsf_version`

Hashing (normative):

- `mapping_material_sha256` is SHA-256 over the canonical JSON serialization of the embedded
  `mapping_material` object (or, if only `mapping_files[]` are provided, over the canonical JSON
  list of `{path,sha256}` entries).
- `mapping_profile_sha256` is SHA-256 over a canonical JSON object containing only stable inputs:
  - `ocsf_version`
  - `mapping_profile_id`
  - `mapping_profile_version`
  - `source_profiles[]` projected to `{source_type, profile, mapping_material_sha256}`
- The hash basis MUST NOT include run-specific fields (`run_id`, `scenario_id`, `generated_at_utc`)
  so mapping drift can be detected across runs.
- `source_profiles[]`:
  - `source_type` (example: `windows-sysmon`)
  - `mapping_material_sha256`
  - either `mapping_material` (embedded) OR `mapping_files[]` (references), or both

### Detections

This artifact is stored at `detections/detections.jsonl`.

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
  - `backend` (example: duckdb-sql v0.1, tenzir v0.2, other v0.3)
  - `compiled_at_utc`
  - `fallback_used` (boolean) when any `raw.*` fields were required
  - `unmapped_sigma_fields` (array) when compilation required dropping selectors or failing the rule
- Store the original Sigma `logsource` under `extensions.sigma.logsource` (verbatim), when
  available.

### Scoring summary

This artifact is stored at `scoring/summary.json`.

Purpose:

- Single-file summary intended for trending, gating, and regressions.

Validation:

- Must validate against `summary.schema.json`.

Key semantics:

- Coverage is computed relative to executed techniques in ground truth.
- Latency metrics are derived from joins between ground truth action timestamps and detections.

### Mapping coverage

This artifact is stored at `normalized/mapping_coverage.json`.

Purpose:

- Quantifies how well raw telemetry mapped into normalized classes and required fields.
- Supports failure classification, debugging, and prioritization.

Validation:

- Must validate against `mapping_coverage.schema.json` when present.

Key semantics (normative when produced):

- Coverage MUST reference the exact mapping profile used via `mapping_profile_sha256` (from
  `normalized/mapping_profile_snapshot.json`).
- Coverage MUST include totals and per-source-type breakdowns sufficient to detect regressions:
  - total events observed, mapped, unmapped, and dropped
  - per `source_type` totals and per `class_uid` totals
  - missing core field counts for each tracked class (see the
    [OCSF field tiers spec](055_ocsf_field_tiers.md))

### Bridge router table snapshot

This artifact is stored at `bridge/router_table.json`.

Purpose:

- Freezes the Sigma `logsource` routing behavior used for this run.
- Enables deterministic compilation of Sigma rules into OCSF-scoped plans.

Validation:

- Must validate against `bridge_router_table.schema.json` when present.

Key semantics (normative when produced):

- The router table MUST map Sigma `logsource.category` to one or more OCSF `class_uid` filters.
- When a `logsource.category` maps to multiple `class_uid` values, the mapping represents a **union
  scope** for evaluation (boolean OR or `IN (...)` semantics), not an ambiguity (see the
  [Sigma to OCSF bridge spec](065_sigma_to_ocsf_bridge.md)).
- Routes MAY also include `filters[]` (producer or source predicates) expressed as OCSF filter
  objects (`{path, op, value}`) per `bridge_router_table.schema.json`.
  - When present, `filters[]` MUST be interpreted as a conjunction (logical AND) applied in addition
    to the `class_uid` union scope.
  - For determinism, `filters[]` SHOULD be emitted in a stable order (RECOMMENDED: sort by `path`,
    then `op`, then canonical JSON of `value`).
- For determinism and stable hashing and diffs:
  - multi-class `class_uid` sets MUST be emitted in ascending numeric order.
- The router table MUST be versioned and hashed (`router_table_sha256`) so routing drift is
  detectable.

Hashing (normative):

- `router_table_sha256` is SHA-256 over a canonical JSON object containing only stable inputs:
  - `ocsf_version`
  - `router_table_id`
  - `router_table_version`
  - `routes[]` (full route objects)
- The hash basis MUST NOT include `generated_at_utc`.

### Bridge mapping pack snapshot

This artifact is stored at `bridge/mapping_pack_snapshot.json`.

Purpose:

- Freezes the full Sigma-to-OCSF bridge inputs used for this run (router + field alias map +
  fallback policy).
- Serves as the authoritative provenance source for Sigma compilation and evaluation.

Validation:

- Must validate against `bridge_mapping_pack.schema.json` when present.

Key semantics (normative when produced):

- The mapping pack MUST reference the router table by id + SHA-256 and SHOULD embed it for
  single-file reproducibility.
- The mapping pack MUST define the effective `raw.*` fallback policy (enabled or disabled,
  constraints) used for compilation.

Hashing (normative):

- `mapping_pack_sha256` is SHA-256 over a canonical JSON object containing only stable inputs:
  - `ocsf_version`
  - `router_table_ref`
  - `field_aliases`
  - `fallback_policy`
  - `backend_defaults` (if present)
- The hash basis MUST NOT include run-specific fields (`run_id`, `scenario_id`, `generated_at_utc`).

### Bridge compiled plans

This artifact is stored under `bridge/compiled_plans/<rule_id>.plan.json`.

Purpose:

- Stores the deterministic, backend-specific compilation output for each Sigma rule evaluated in
  this run.
- Provides machine-checkable reasons for non-executable rules (routing failure, unmapped fields,
  unsupported modifiers).

Validation:

- Each plan file must validate against `bridge_compiled_plan.schema.json` when present.

Key semantics (normative when produced):

- Plans MUST be keyed by stable `rule_id` and MUST include `rule_sha256` (hash of canonical Sigma
  rule content) for drift detection.
- Plans MUST declare `executable: true | false` and, when false, MUST include
  `non_executable_reason`.

### Bridge coverage

This artifact is stored at `bridge/coverage.json`.

Purpose:

- Summarizes bridge success and failure modes for the run:
  - routed vs unrouted rules
  - executable vs non-executable rules
  - fallback usage
  - top unmapped fields and top unrouted categories

Validation:

- Must validate against `bridge_coverage.schema.json` when present.

Key semantics (normative when produced):

- Coverage MUST reference the mapping pack used via `mapping_pack_sha256`.
- Coverage MUST be sufficient to attribute detection gaps to `bridge_gap` vs `normalization_gap` vs
  `telemetry_gap`.

## Cross-artifact invariants

These are enforced by validators in code and CI. They are not fully expressible in JSON Schema.

Required invariants:

1. `manifest.run_id` must match:
   - `ground_truth.run_id` for every line
   - `normalized.metadata.run_id` for every event
   - `detections.run_id` for every detection
   - `summary.run_id`
   - `criteria.results.run_id` for every criteria result (when present)
1. `manifest.scenario.scenario_id` must match:
   - `ground_truth.scenario_id` for every line
   - `normalized.metadata.scenario_id` for every event
   - `summary.scenario_id`
1. Scenario cardinality (v0.1):
   - The set of distinct scenario IDs observed in `ground_truth.scenario_id` across all lines MUST
     contain exactly one value.
   - The set of distinct scenario IDs observed in `normalized.metadata.scenario_id` across all
     normalized events MUST contain exactly one value.
   - Multi-scenario runs are reserved in v0.1. If more than one distinct scenario ID is observed,
     implementations MUST fail closed with `reason_code=contract.multi_scenario_reserved`.
1. Time bounds:
   - All `ground_truth.timestamp_utc` and normalized event times must be within
     `[manifest.started_at_utc, manifest.ended_at_utc]` when `ended_at_utc` is present, allowing a
     small tolerance for clock skew (configurable).
1. Event identity:
   - `metadata.event_id` must be unique within a run bundle for normalized events.
1. Referential integrity:
   - `detections.matched_event_ids` must exist in the normalized store for that run.
   - `criteria.results.action_id` must reference an `action_id` present in `ground_truth.jsonl`
     (when present).
   - `criteria.results.action_key` must equal the corresponding ground truth `action_key` (when
     present).
1. Deterministic ordering requirements (for diffability):
   - When writing JSONL outputs, lines are sorted deterministically (see storage spec).
   - When writing Parquet, within-file ordering is deterministic (see storage spec).
1. Action identifier model:
   - When `plan/expanded_graph.json` is present, every `ground_truth.action_id` MUST match the
     deterministic action instance id format: `^pa_aid_v1_[0-9a-f]{32}$`.
   - When `plan/expanded_graph.json` is absent (v0.1), every `ground_truth.action_id` MUST match the
     legacy v0.1 format: `^s[1-9][0-9]*$`.

## Optional invariants: run bundle signing

Run bundle signing is **optional** in v0.1 and is controlled by `security.signing.enabled` (see the
[config reference](120_config_reference.md)). When enabled, signing provides integrity guarantees
for the full run bundle without requiring a specific transport or storage backend.

Normative requirements:

- v0.1 signing MUST use **Ed25519** signatures.
- The signing key MUST be provided by reference (`security.signing.key_ref`); private key material
  MUST NOT be written into the run bundle.
- Signing MUST be the final step after all long-term artifacts are materialized.

### Signing artifacts and locations

When signing is enabled, the run bundle MUST include:

- `security/checksums.txt`
- `security/signature.ed25519`
- `security/public_key.ed25519`

The `security/` directory is reserved for security posture artifacts (redaction policy snapshots,
signing artifacts, and related metadata).

### Long-term artifact selection for checksumming

`security/checksums.txt` MUST include every file under `runs/<run_id>/` except:

- `logs/**` (volatile)
- `unredacted/**` (quarantine, if present)
- `security/checksums.txt` and `security/signature.ed25519` (to avoid self-reference)

Path canonicalization:

- Paths in `security/checksums.txt` MUST be relative to the run bundle root.
- Paths MUST use forward slashes (`/`) as separators, even on Windows.
- Path comparison and sorting MUST be case-sensitive and locale-independent.

### Security checksums format (normative)

This section defines the `security/checksums.txt` format.

- Encoding: UTF-8.
- Line endings: LF (`\n`).
- One record per line: `sha256_hex  relative_path` Where:
  - `sha256_hex` is 64 lowercase hex characters of `sha256(file_bytes)`.
  - `relative_path` is the canonicalized relative path.
- Ordering: lines MUST be sorted by `relative_path` using lexicographic order over UTF-8 bytes.

### Public key and key id

This section defines `key_id`.

- `security/public_key.ed25519` MUST contain the Ed25519 public key as base64 of the 32 raw public
  key bytes, followed by a single LF.
- `key_id` is defined as `sha256(public_key_bytes)` encoded as 64 lowercase hex characters.
- Implementations SHOULD record `key_id` in run provenance (for example, `manifest.json` under an
  extensions namespace) to support downstream trust policies.

### Security signature format (normative)

This section defines the `security/signature.ed25519` format.

- The signature MUST be computed over the exact bytes of `security/checksums.txt`.
- `security/signature.ed25519` MUST contain the signature as base64 of the 64 raw signature bytes,
  followed by a single LF.

### Verification semantics

Given a run bundle that includes `security/checksums.txt`, `security/signature.ed25519`, and
`security/public_key.ed25519`, verification MUST:

1. Parse and canonicalize `security/checksums.txt` exactly as specified above.
1. Recompute sha256 for each referenced file and compare to `sha256_hex`.
1. Verify the Ed25519 signature in `security/signature.ed25519` against the bytes of
   `security/checksums.txt` using the public key from `security/public_key.ed25519`.

Verification outcomes:

- **valid**: all checksums match and the signature verifies.
- **invalid**: any checksum mismatch, missing referenced file, or signature verification failure.
- **indeterminate**: required signing artifacts are missing or malformed.

When `security.signing.enabled: true`, the pipeline MUST fail closed if verification would be
`invalid` or `indeterminate` for the artifacts it just emitted.

## Versioning and compatibility policy

Contract versioning:

- Patch: documentation-only changes or loosening constraints that do not change meaning.
- Minor: additive changes that preserve backward compatibility (new optional fields, new
  extensions).
- Major: breaking changes (new required fields, meaning changes, tighter validation that can
  invalidate existing artifacts).

Compatibility expectations:

- The pipeline must be able to read at least the previous minor contract version for one release
  window.
- Report generators must accept older run bundles and emit a clear warning when fields are missing.

## Extensions and vendor fields

Strict artifacts (manifest, ground truth, detections, summary) are intentionally
`additionalProperties: false` with a single extension point:

- `extensions`: object, reserved for forward-compatible additions and vendor-specific data.
- Namespace keys MUST match `^[a-z][a-z0-9_]*$` (lowercase, digits, underscore). Dotted notation in
  docs (for example, `extensions.bridge.mapping_pack_version`) indicates nesting, not literal dots
  in keys.
- Ownership: namespaces defined in this spec are project-reserved; vendors MUST use a unique
  namespace (for example, `extensions.acme` or `extensions.vendor_acme`) and MUST NOT reuse
  project-reserved namespaces.
- Each namespace value SHOULD be an object; new fields SHOULD be added within a namespace object
  rather than as top-level scalars.
- Legacy top-level scalar keys are permitted only when explicitly defined by this spec (for example,
  `extensions.command_sha256`, `extensions.redaction_policy_id`).
- Optional versioning: namespace objects MAY include `v` (integer >= 1). Increment `v` when meanings
  change or a breaking change is introduced within that namespace; additive fields do not require a
  bump.
- Deterministic ordering: emit namespace keys in lexicographic order; within each namespace, use a
  stable key order for diffability and hashing.

Normalized events:

- Are intentionally permissive to allow full OCSF payloads and source-specific structures.
- Must still satisfy required provenance and identity fields.

## Redaction and sensitive data

- Raw commands and secrets must not be written into run bundles.
- `command_summary` is always redacted-safe. If a full command is needed for debugging, it should
  remain in volatile logs and never enter long-term storage.
- When storing raw telemetry, apply a configurable redaction policy for known sensitive fields
  (credentials, tokens, PII) before promotion into long-term stores.

## Validation workflow

Recommended validation stages:

1. Schema validation of each artifact (JSON and per-line JSONL).
1. Cross-artifact invariants check.
1. Storage invariants check (Parquet schema, partition structure, deterministic ordering).
1. Optional signature verification (when signing artifacts are present).

CI gates should fail closed on contract violations.

## Key decisions

- The run bundle and manifest provide the authoritative contract boundaries for stage coordination.
- Action identity uses deterministic hashing over canonical JSON and redacted inputs.
- Cross-artifact invariants and optional signing enforce reproducibility and integrity.

## References

- [Scenario model spec](030_scenarios.md)
- [Storage formats spec](045_storage_formats.md)
- [OCSF field tiers spec](055_ocsf_field_tiers.md)
- [Sigma to OCSF bridge spec](065_sigma_to_ocsf_bridge.md)
- [Operability spec](110_operability.md)
- [Config reference](120_config_reference.md)
- [Event identity ADR](../adr/ADR-0002-event-identity-and-provenance.md)
- [Redaction policy ADR](../adr/ADR-0003-redaction-policy.md)

## Changelog

| Date | Change                                       |
| ---- | -------------------------------------------- |
| TBD  | Style guide migration (no technical changes) |
