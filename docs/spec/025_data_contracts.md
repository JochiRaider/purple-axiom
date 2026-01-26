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

### Document boundaries and ownership

This specification is authoritative for:

- contract registry semantics and registry-backed validation (schemas under `docs/contracts/`)
- run bundle layout and deterministic artifact paths under `runs/<run_id>/`
- cross-artifact invariants required for joins, reproducibility, and CI validation
- shared shapes referenced by multiple stage specs (for example, `evidence_refs[]`)
- optional signing artifact formats and selection rules (when signing is enabled)

This specification is not the primary home for stage implementation behavior beyond what is needed
to make artifact contracts testable. Detailed stage behavior, feature flags, and failure mapping
MUST live in the owning stage spec (for example, telemetry, normalization, detection, reporting),
with this document referenced as needed.

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
- Run-relative path: A POSIX-style path interpreted as relative to the run bundle root
  (`runs/<run_id>/`). Run-relative paths MUST NOT include the `runs/<run_id>/` prefix.
- JSONL: JSON Lines, one JSON object per line.
- OCSF event: A normalized event that conforms to the required envelope fields and may include
  additional OCSF fields and vendor extensions.

## Contract registry

Schemas live in `docs/contracts/`.

### Authoritative contract registry index (normative)

The authoritative registry is a **schema-backed index** that maps:

- **artifact selectors** (run-relative paths or glob patterns) to a `contract_id`, and
- `contract_id` to a concrete schema file and declared `contract_version`.

Registry files (required for implementations):

- `docs/contracts/contract_registry.json` (the registry instance)
- `docs/contracts/contract_registry.schema.json` (schema for the registry instance)

Normative requirements:

- Implementations MUST treat `docs/contracts/contract_registry.json` as the single source of truth
  for:
  - which artifacts are contract-backed, and
  - which schema validates each artifact.
- This spec MAY include a human-readable list of schema files for convenience, but that list is
  non-authoritative and MUST NOT be consumed by the validation engine.
- Each schema referenced by the registry MUST include a `contract_version` constant as described
  below.

#### Minimal registry shape (normative)

The registry instance MUST include, at minimum:

- `registry_version` (SemVer; independent of contract versions)
- `contracts[]`:
  - `contract_id` (stable identifier; RECOMMENDED: schema filename without extension)
  - `schema_path` (repo-relative path under `docs/contracts/`)
  - `contract_version` (string; MUST match the schema constant)
- `bindings[]`:
  - `artifact_glob` (run-relative POSIX glob, for example `runner/actions/*/executor.json`)
  - `contract_id` (must exist in `contracts[]`)

#### Contract version constant (normative)

Each schema MUST include a `contract_version` constant as a SemVer string (for example, `"1.0.0"`),
expressed in JSON Schema via a `const` value. The `contract_version` value:

- MUST be bumped per the Versioning and compatibility policy in this document when the contract
  meaningfully changes (new required fields, semantic changes, or validation tightening).
  Documentation-only edits do not require a bump.

If a schema’s `contract_version` disagrees with the registry entry for that `contract_id`, contract
validation tooling MUST fail closed (treat as misconfiguration).

### Human-readable schema inventory (non-authoritative)

The following list is for navigation only. The authoritative mapping is
`docs/contracts/contract_registry.json`.

- `docs/contracts/manifest.schema.json`
- `docs/contracts/ground_truth.schema.json`
- `docs/contracts/principal_context.schema.json`
- `docs/contracts/defense_outcomes.schema.json`
- `docs/contracts/cache_provenance.schema.json`
- `docs/contracts/counters.schema.json`
- `docs/contracts/audit_event.schema.json`
- `docs/contracts/runner_executor_evidence.schema.json`
- `docs/contracts/resolved_inputs_redacted.schema.json`
- `docs/contracts/requirements_evaluation.schema.json`
- `docs/contracts/cleanup_verification.schema.json`
- `docs/contracts/side_effect_ledger.schema.json`
- `docs/contracts/state_reconciliation_report.schema.json`
- `docs/contracts/criteria_pack_manifest.schema.json`
- `docs/contracts/criteria_entry.schema.json`
- `docs/contracts/criteria_result.schema.json`
- `docs/contracts/ocsf_event_envelope.schema.json`
- `docs/contracts/detection_instance.schema.json`
- `docs/contracts/summary.schema.json`
- `docs/contracts/report.schema.json`
- `docs/contracts/range_config.schema.json`
- `docs/contracts/redaction_profile_set.schema.json`
- `docs/contracts/telemetry_baseline_profile.schema.json`
- `docs/contracts/telemetry_validation.schema.json`
- `docs/contracts/duckdb_conformance_report.schema.json`
- `docs/contracts/pcap_manifest.schema.json`
- `docs/contracts/netflow_manifest.schema.json`
- `docs/contracts/lab_inventory_snapshot.schema.json`
- `docs/contracts/mapping_profile_input.schema.json`
- `docs/contracts/mapping_profile_snapshot.schema.json`
- `docs/contracts/mapping_coverage.schema.json`
- `docs/contracts/bridge_router_table.schema.json`
- `docs/contracts/bridge_mapping_pack.schema.json`
- `docs/contracts/bridge_compiled_plan.schema.json`
- `docs/contracts/bridge_coverage.schema.json`
- `docs/contracts/threat_intel_indicator.schema.json`
- `docs/contracts/threat_intel_pack_manifest.schema.json`

See **Contract version constant (normative)** above for the required `contract_version` constant and
bump rules.

### Contract lifecycle workflow (normative)

When introducing a new contract-backed artifact or changing an existing contract:

1. Update `docs/contracts/contract_registry.json`:
   - add or update the `contracts[]` entry (`contract_id`, `schema_path`, `contract_version`)
   - add or update the `bindings[]` entry that maps the run-relative `artifact_glob` to the
     `contract_id`
1. Add or update the schema under `docs/contracts/`:
   - `$schema` MUST be Draft 2020-12
   - the schema MUST include the `contract_version` constant referenced by the registry
1. Update the producing stage (or orchestrator, as applicable) to enforce publish-gate validation:
   - validate in staging before atomic publish
   - fail per configured `fail_mode` and record a stable `reason_code` on failure
1. If the change introduces or modifies a cross-artifact invariant, update this document (and the
   invariant checker) in the same change.
1. Add or update CI fixtures:
   - at least one valid instance fixture, and
   - at least one invalid instance fixture that exercises the new or tightened constraint.

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

- `artifact_path`: run-relative path using POSIX separators (`/`).
- `contract_id`: contract identifier from `docs/contracts/contract_registry.json`.
- `instance_path`: JSON Pointer to the failing instance location (`""` for the document root).
- `schema_path`: JSON Pointer to the failing schema location (`""` if unavailable, for example on
  parse failure).
- `keyword`: OPTIONAL JSON Schema keyword that triggered the failure (example: `required`, `type`).
- `message`: human-readable error message.
- `line_number`: REQUIRED for JSONL validation errors and JSONL parse errors (1-indexed); omitted
  otherwise.

JSONL parse failures (normative):

- If a JSONL line cannot be parsed as JSON, implementations MUST emit one error with:
  - `line_number` set to the failing line (1-indexed),
  - `instance_path=""`,
  - `schema_path=""`,
  - `keyword` omitted,
  - `message` describing the parse error.

Ordering (normative):

- Errors MUST be sorted by the tuple below using UTF-8 byte order (no locale):
  1. `artifact_path`
  1. `line_number` (treat missing as `0`)
  1. `instance_path`
  1. `schema_path`
  1. `keyword` (treat missing as empty string)
  1. `message`

Error caps (normative):

- Implementations MUST apply a maximum error cap per artifact (`max_errors_per_artifact`).
- If not configured, `max_errors_per_artifact` MUST default to `50`.
- When the cap is reached, implementations MUST:
  - set `errors_truncated=true` in the validation summary, and
  - stop collecting additional errors for that artifact (deterministically).

### Contract validation report artifact (normative)

When publish-gate contract validation fails, stages MUST persist a structured validation report so
CI and operators can inspect deterministic failure details.

Location (normative):

- `runs/<run_id>/logs/contract_validation/<stage_id>.json`

Minimum fields (normative):

- `run_id`
- `stage_id`
- `generated_at_utc`
- `max_errors_per_artifact`
- `artifacts[]`:
  - `artifact_path`
  - `contract_id`
  - `contract_version`
  - `status` (`valid | invalid`)
  - `errors_truncated` (boolean)
  - `errors[]` (the deterministic, capped, sorted error list defined above)

Notes:

- This report is a **deterministic evidence log** (Tier 0). When present, it MUST be included in
  default exports and in `security/checksums.txt` when signing is enabled (see ADR-0009 and the
  storage formats Tier 0 export classification).
- Stages MUST still record the stage outcome with a stable `reason_code` per ADR-0005 and
  operability rules.

#### Deterministic artifact path rule (normative)

- All contracted artifacts under `runs/<run_id>/` MUST use stable, spec-defined paths and MUST NOT
  include timestamps in filenames.

- “Timestamped exports” (if ever needed for ad-hoc operator workflows) MUST:

  - be written only under an explicitly non-contracted scratch area (RECOMMENDED:
    `runs/<run_id>/logs/scratch/`), and
  - MUST NOT be referenced by the manifest’s contracted artifact list, and
  - MUST NOT participate in hashing/signing/trending inputs.

### Validation scope and timing

#### Publish-gate contract validation (required)

For any stage that publishes contract-backed artifacts:

- The stage MUST write outputs to `runs/<run_id>/.staging/<stage_id>/...` and MUST perform contract
  validation as a publish gate before atomic publish.
- `.staging/` is a reserved, non-contracted scratch area:
  - Stages MUST NOT write long-term artifacts outside their `.staging/<stage_id>/` subtree until
    publish.
  - `.staging/**` MUST NOT be referenced by `evidence_refs[]` (or any other contracted evidence
    pointer) and MUST be excluded from signing/checksumming inputs.
- Atomic publish and cleanup:
  - Publishing MUST be implemented as an atomic rename/move from staging into final run-bundle
    paths.
  - On successful publish, the stage MUST delete (or leave empty) its
    `runs/<run_id>/.staging/<stage_id>/` directory.
  - If validation fails, stages MUST NOT partially publish final-path artifacts.
- A stage MUST NOT publish contract-invalid artifacts into their final locations under
  `runs/<run_id>/`.
- State machine integration hook (derivability; see ADR-0007):
  - For any stage that records a terminal stage outcome, the outcome plus the presence/absence of
    the stage’s published contracted outputs (minimum outputs for that stage when enabled) MUST be
    sufficient to derive the stage’s terminal state.
  - If terminal state cannot be derived due to inconsistent artifacts (for example, outputs present
    but the stage outcome is missing), implementations MUST fail closed with a cross-cutting
    `reason_code` (`input_missing` or `storage_io_error` per ADR-0005).

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
  - `runs/<run_id>/inputs/baseline_run_ref.json` when regression is enabled
  - `runs/<run_id>/inputs/baseline/manifest.json` when produced (regression baseline snapshot form)
  - `runs/<run_id>/inputs/telemetry_baseline_profile.json` when
    `telemetry.baseline_profile.enabled=true`
  - `runs/<run_id>/inputs/threat_intel/manifest.json` (when threat intelligence is enabled; v0.2+)
  - `runs/<run_id>/inputs/threat_intel/indicators.jsonl` (when threat intelligence is enabled;
    v0.2+)
  - `runner/**` artifacts that have contracts (for example, executor evidence, side-effect ledger,
    cleanup verification)
  - `runs/<run_id>/runner/principal_context.json`
  - `runs/<run_id>/logs/cache_provenance.json`
  - `runs/<run_id>/logs/counters.json`
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

- **Agent liveness (push-only DOA detection):** `telemetry.agent.liveness`
- **Telemetry baseline profile gate:** `telemetry.baseline_profile`
- **Windows raw-mode canary:** `telemetry.windows_eventlog.raw_mode`
- **Checkpointing and replay validation:** `telemetry.checkpointing.storage_integrity`
- **Resource budget enforcement:** `telemetry.resource_budgets`

Authoritative definitions for these canaries, reason codes, and required evidence pointers are in
the [operability spec](110_operability.md) and the
[telemetry pipeline spec](040_telemetry_pipeline.md).

## Run bundle layout

A run bundle is stored at `runs/<run_id>/` and follows this layout:

- `.staging/` (transient scratch for publish-gate writes; MUST be absent or empty in a finalized run
  bundle)
- `manifest.json` (single JSON object)
- `ground_truth.jsonl` (JSONL)
- `inputs/` (input snapshots and references used to interpret and compare runs)
  - `inputs/range.yaml` (required) is the pinned range configuration snapshot used for this run.
  - `inputs/scenario.yaml` (required) is the pinned scenario definition snapshot used for this run.
  - `inputs/plan_draft.yaml` (v0.2+; optional; plan draft snapshot when plan building is enabled).
  - `inputs/baseline_run_ref.json` (required when regression is enabled; regression baseline pointer
    form)
  - `inputs/baseline/manifest.json` (optional; regression baseline snapshot form)
  - `inputs/telemetry_baseline_profile.json` (optional; REQUIRED when telemetry baseline profile
    gate is enabled)
  - `inputs/threat_intel/manifest.json` (v0.2+; REQUIRED when threat intelligence is enabled; threat
    intel pack snapshot manifest)
  - `inputs/threat_intel/indicators.jsonl` (v0.2+; REQUIRED when threat intelligence is enabled;
    threat intel indicators snapshot)
- `plan/` (v0.2+; compiled plan graph and expansion manifests)
- `control/` (v0.2+; operator control-plane requests/decisions, when implemented)
  - `control/audit.jsonl` (v0.2+; deterministic control-plane audit transcript when enabled; see
    `control_plane.audit.enabled`)
  - `control/cancel.json` (v0.2+; durable cancellation request).
  - `control/resume_request.json` (v0.2+; durable resume request).
  - `control/resume_decision.json` (v0.2+; durable resume decision).
  - `control/retry_request.json` (v0.2+; durable retry request).
  - `control/retry_decision.json` (v0.2+; durable retry decision).
- `criteria/` (criteria pack snapshot + criteria evaluation results)
- `raw_parquet/` (raw telemetry datasets, long-term; see storage formats)
- `raw/` (evidence-tier blobs and source-native payloads where applicable)
- `runner/` (runner evidence: transcripts, executor metadata, side-effect ledger, cleanup
  verification, state reconciliation)
  - `runner/principal_context.json` (run-level principal identity mapping)
- `normalized/` (normalized event store and mapping coverage)
- `bridge/` (Sigma-to-OCSF bridge artifacts: mapping pack snapshot, compiled plans, bridge coverage)
- `detections/` (detections emitted by evaluators)
- `scoring/` (joins and summary metrics)
- `security/` (integrity artifacts and redaction policy snapshot when enabled)
- `report/` (HTML and JSON report outputs)
  - Regression results (when enabled) are embedded only in `report/report.json` under the
    `regression` object (see `docs/spec/080_reporting.md` for the contract).
- `logs/` (Tier 0 operability surface: deterministic evidence + volatile diagnostics; see ADR-0009)
  - Deterministic evidence (included in default exports/checksums when present):
    - `logs/health.json` (when enabled; see the [operability spec](110_operability.md))
    - `logs/counters.json` (schema-backed per-run counters and gauges; see the
      [operability spec](110_operability.md))
    - `logs/telemetry_validation.json` (when telemetry validation is enabled; see the
      [telemetry pipeline spec](040_telemetry_pipeline.md))
    - `logs/cache_provenance.json` (when caching is enabled; see the
      [architecture spec](020_architecture.md))
    - `logs/lab_inventory_snapshot.json` (canonical lab inventory snapshot; see
      [lab providers](015_lab_providers.md))
    - `logs/lab_provider_connectivity.json` (optional provider connectivity canary; see
      [lab providers](015_lab_providers.md))
    - `logs/contract_validation/` (publish-gate contract validation reports; see the
      [architecture spec](020_architecture.md))
  - Volatile diagnostics (excluded from default exports/checksums):
    - `logs/run.log` (unstructured operator log; see ADR-0005)
    - `logs/warnings.jsonl` (optional warning stream; see ADR-0005)
    - `logs/eps_baseline.json` (optional resource baseline; see the
      [operability spec](110_operability.md))
    - `logs/telemetry_checkpoints/` (receiver checkpoint state; see ADR-0002)
    - `logs/dedupe_index/` (normalization runtime index; see ADR-0002)
    - `logs/scratch/` (timestamped scratch outputs; non-contracted)

The manifest is the authoritative index for what exists in the bundle and which versions were used.

## Artifact contracts

### Evidence references (shared shape)

This section defines the canonical `evidence_refs[]` entry shape used across run artifacts to point
to supporting evidence deterministically (for example, in reporting outputs). Any artifact that
emits `evidence_refs[]` MUST follow this shape and the selector grammar below.

Other specs MUST reference this section and MUST NOT redefine the `evidence_refs[]` field set or
selector prefixes. Examples in other specs MAY include evidence refs, but MUST use the exact field
names, prefix forms, and ordering rules defined here.

Minimum evidence ref fields (normative):

- `artifact_path` (string, required): run-relative path to the evidence artifact.
- `selector` (string, optional): sub-selection within the artifact (see Selector constraints below).
- `handling` (string, optional): how the referenced evidence is handled. Allowed values:
  `present | withheld | quarantined | absent` (default: `present`).

Handling semantics (normative):

- `present`: `artifact_path` exists and contains the referenced evidence.
- `withheld`: `artifact_path` exists but contains a deterministic redaction/placeholder; the
  underlying evidence is intentionally not retained.
- `quarantined`: `artifact_path` exists but is quarantined (for example, under
  `runs/<run_id>/unredacted/**`) and MUST NOT be used for scoring/trending outputs.
- `absent`: evidence was expected for this reference but is not present; `artifact_path` SHOULD
  indicate the expected location.

Artifact path requirements (normative):

- `artifact_path` MUST be run-relative (no leading `/` and no `runs/<run_id>/` prefix), must not
  contain `..` segments, and must be normalized to use `/` separators.
- `artifact_path` MUST refer to a deterministic path defined by the storage formats spec.
- Within any `evidence_refs` array, entries MUST be sorted deterministically using UTF-8 byte order
  (no locale) by the tuple:
  1. `artifact_path`
  1. `selector` (treat missing as empty string)
  1. `handling` (treat missing as `present`, and sort by the fixed order: `present`, `withheld`,
     `quarantined`, `absent`)

Selector constraints (normative when present):

- `selector` MUST be ASCII, \<=256 chars.
- `selector` MUST be one of:
  - `json_pointer:<RFC6901 JSON Pointer>` (selects subobject from JSON file)
  - `jsonl_line:<N>` (selects 1-indexed line from JSONL)

### Run counters (operability) (normative)

Purpose:

- Provides a per-run snapshot of stable counters and gauges for debugging, CI assertions, and
  deterministic regression triage.

Location (normative):

- `runs/<run_id>/logs/counters.json`

Validation (normative):

- Must validate against `counters.schema.json`.

Contract registry binding (normative):

- `artifact_glob`: `logs/counters.json`
- `contract_id`: `counters`
- `schema_path`: `docs/contracts/counters.schema.json`

Minimum required fields (normative):

- `contract_version` (schema constant)
- `schema_version` (const: `pa:counters:v1`)
- `run_id` (string; MUST equal `manifest.run_id`)
- `generated_at_utc` (string; RFC 3339 UTC)
- `counters` (object; map of `counter_name -> u64`)
- `gauges` (object; optional; map of `gauge_name -> number`)

Type constraints (normative):

- Every `counters` value MUST be an integer in the inclusive range `[0, 2^64-1]`.
- Every `gauges` value MUST be a finite JSON number (no NaN or Infinity).

Determinism constraints (normative):

- The emitted JSON serialization MUST sort `counters` keys by UTF-8 byte order (no locale).
- When present, the emitted JSON serialization MUST sort `gauges` keys by UTF-8 byte order (no
  locale).

Counter naming and semantics (normative):

- This contract does not require a fixed set of counter keys.
- Required counter keys and omit-vs-zero semantics are defined by stage specifications (for
  telemetry+ETL, see the operability and telemetry pipeline specs).

Conformance tests (normative):

- CI MUST include, at minimum:
  - one valid counters fixture (minimum required fields and at least one counter), and
  - one invalid counters fixture that fails schema validation (for example, missing `run_id` or an
    invalid `schema_version` constant).
- CI MUST include a determinism test that asserts `counters.json` key ordering is stable when
  serialized (sorted keys) for a fixture with multiple counter keys.

### Regression baseline reference inputs (normative)

Regression analysis compares a candidate run to a baseline run. When regression is enabled
(`reporting.regression.enabled=true`), implementations MUST materialize baseline reference inputs
under `runs/<run_id>/inputs/` as defined by the storage formats spec (`045_storage_formats.md`).
These artifacts are treated as inputs used to interpret and compare runs and MAY be referenced by
`evidence_refs[]` in reporting artifacts.

Implementations MUST support two baseline reference forms. The pointer form is required when
regression is enabled; the snapshot form is optional but RECOMMENDED when the baseline manifest is
readable.

Baseline reference artifacts under `runs/<run_id>/inputs/` are owned by the reporting stage and are
immutable once published:

- Operators MUST NOT pre-populate `inputs/baseline_run_ref.json` or any `inputs/baseline/**` paths.

- All stages MUST treat `inputs/**` as read-only inputs; only reporting (or the orchestrator
  component that owns regression) may materialize baseline reference artifacts under these reserved
  paths.

- If a run is resumed/replayed and these baseline reference artifacts already exist, implementations
  MUST validate them and MUST NOT rewrite them.

- Pointer form: `inputs/baseline_run_ref.json` (required when regression enabled)

- Snapshot form: `inputs/baseline/manifest.json` (optional, recommended)

The pointer form includes:

Baseline selection (exactly one is REQUIRED):

- `baseline_run_id`: string, run_id of the baseline run whose manifest will be fetched from storage.
- `baseline_manifest_path`: string, path to a manifest.json file that is directly accessible.

Optional integrity field:

- `baseline_manifest_sha256`: string (hex). If the baseline manifest is readable, implementations
  SHOULD populate this field to pin the exact bytes used for comparison.

Output guarantees:

- The reporting stage MUST include the pointer form. If snapshot form is present, it MUST match the
  bytes of the baseline manifest referenced by the pointer (by sha256).

Resolution algorithm (normative):

1. Determine `baseline_manifest_ref` based on the configured baseline selection:

   - If `baseline_run_id` selected, `baseline_manifest_ref = runs/<baseline_run_id>/manifest.json`.
   - If `baseline_manifest_path` selected, `baseline_manifest_ref = <that path>`.

1. Materialize or reuse the pointer form prior to regression comparison:

   - If `inputs/baseline_run_ref.json` exists, implementations MUST read and validate it and MUST
     use its contents (do not rewrite). If it conflicts with the configured baseline selection, the
     implementation MUST fail closed (use `baseline_incompatible` in the reporting regression
     substage).
   - Otherwise, implementations MUST attempt to read baseline manifest bytes from
     `baseline_manifest_ref` (best effort) in order to populate `baseline_manifest_sha256` when
     possible, and then MUST write `inputs/baseline_run_ref.json` atomically once with:
     - the selected baseline fields,
     - `baseline_manifest_ref`, and
     - `baseline_manifest_sha256` if the bytes were successfully read.

1. Materialize or reuse the snapshot form (best-effort, recommended):

   - If `inputs/baseline/manifest.json` exists, implementations MUST validate it and MUST NOT
     rewrite it.
   - Otherwise, if baseline manifest bytes were successfully read, implementations SHOULD write
     `inputs/baseline/manifest.json` to exactly those bytes (atomic write).

#### Deterministic baseline resolution and failure mapping (normative)

Inputs:

- Baseline selection is provided by configuration via `reporting.regression.baseline_run_id` or
  `reporting.regression.baseline_manifest_path` (see `120_config_reference.md`).

Output guarantees (when regression is enabled):

- `runs/<run_id>/inputs/baseline_run_ref.json` MUST be materialized.
- At least one baseline reference form MUST be present under `runs/<run_id>/inputs/`.
- When the baseline manifest bytes are readable, implementations SHOULD also materialize
  `runs/<run_id>/inputs/baseline/manifest.json` (snapshot form).

Resolution algorithm (normative):

1. Determine `baseline_manifest_ref`:
   - If `baseline_run_id` is selected, `baseline_manifest_ref` MUST be
     `runs/<baseline_run_id>/manifest.json` (relative to `reporting.output_dir`).
   - If `baseline_manifest_path` is selected, `baseline_manifest_ref` MUST be the provided
     `baseline_manifest_path` (relative to `reporting.output_dir`).
1. Implementations MUST write `inputs/baseline_run_ref.json` with the selected baseline fields and
   `baseline_manifest_ref` prior to regression comparison.
1. Implementations MUST attempt to read the baseline manifest bytes from `baseline_manifest_ref`:
   - On success, implementations MUST compute `baseline_manifest_sha256` over the exact bytes read
     and SHOULD snapshot those same bytes to `inputs/baseline/manifest.json`.
   - On failure, implementations MUST omit `baseline_manifest_sha256` from
     `inputs/baseline_run_ref.json` and MUST classify the condition as `baseline_missing`.

Failure mapping (normative):

- Failure to locate or read the baseline manifest MUST be classified as `baseline_missing` (maps to
  the ADR-0005 `reporting.regression_compare` substage reason code).
- Missing required baseline or candidate artifacts for regression comparison, or schema/contract
  version incompatibility, MUST be classified as `baseline_incompatible`.
- Unexpected runtime errors during regression comparison MUST be classified as
  `regression_compare_failed`.

### Measurement layers for conclusions (triage taxonomy)

Some reported gaps and conclusions are not best triaged by pipeline stage alone. To enable stable
triage, reportable gaps MUST be attributable to exactly one measurement layer.

Measurement layers (closed set):

- `telemetry`
- `normalization`
- `detection`
- `scoring`

Normative requirements (for reporting artifacts):

- Any report gap entry that contributes to status degradation or a failing `status_recommendation`
  MUST include:
  - `measurement_layer`, and
  - `evidence_refs[]` (at least one entry).
- Any gap category identifier used in reporting/scoring outputs (for example,
  `top_failures[].gap_category` in the report JSON, or the map keys under `gaps.by_category`) MUST
  be one of the canonical scoring taxonomy tokens defined in `070_scoring_metrics.md` (Pipeline
  health, v0.1). Implementations MUST NOT emit additional gap category tokens.
- `measurement_layer` MUST match the normative mapping defined in `070_scoring_metrics.md` (gap
  category to measurement layer mapping).
- Each `evidence_refs[]` entry MUST follow the authoritative `evidence_refs[]` shape and selector
  grammar defined in [Evidence references (shared shape)](#evidence-references-shared-shape).
- Reporting publish-gate validation MUST fail closed if the report JSON violates the above
  requirements, including unknown gap category tokens.

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

- `scenario.posture` records the effective scenario posture declared by the scenario input.

  - `mode` (string enum; default: `baseline`): `baseline | assumed_compromise`
  - Producers MUST treat posture as non-secret and MUST NOT record credentials, tokens, usernames,
    hostnames, IPs, or other sensitive identifiers in posture fields.

- v0.1 run bundles MUST be single-scenario. Multi-scenario manifests are reserved for a future
  release.

Status derivation (normative):

Implementations MUST compute an effective outcome for each enabled pipeline stage (a "stage
outcome").

A stage outcome MUST include:

- `stage` (string): stable identifier (`lab_provider`, `runner`, `telemetry`, `normalization`,
  `validation`, `detection`, `scoring`, `reporting`, `signing`), optionally suffixed by substage
  (`reporting.regression_compare`).
- `status` (enum): `success | failed | skipped`.
- `fail_mode` (enum): `fail_closed | warn_and_skip`.
- `reason_code` (string, optional): stable reason token, required on `failed`. If present, it MUST
  be a token allowed by ADR-0005.

Stage outcome ordering (normative):

- Stage outcomes MUST be emitted in deterministic order:
  - pipeline order for top-level stages (`lab_provider`, `runner`, `telemetry`, `normalization`,
    `validation`, `detection`, `scoring`, `reporting`, `signing`), and
  - within a stage, substage outcomes (dot-suffixed) ordered lexicographically by `stage` (UTF-8
    byte order).

`manifest.status` MUST be derived from the set of stage outcomes as:

- `failed` if any enabled stage has `status=failed` and `fail_mode=fail_closed`
- else `partial` if any enabled stage has `status=failed` and `fail_mode=warn_and_skip`
- else `success` if all enabled stages have `status=success`

When `health.emit_health_files=true`, stage outcomes MUST also be written to
`runs/<run_id>/logs/health.json`.

Recommended manifest additions (normative in schema when implemented):

- `lab.provider` (string): `manual | ludus | terraform | vagrant | other`
- `lab.inventory_snapshot_sha256` (string): hash of the resolved inventory snapshot
- `lab.assets` (array): resolved assets used by the run (or pointer to
  `logs/lab_inventory_snapshot.json`)
- `normalization.ocsf_version` (string): pinned OCSF version used by the normalizer for this run.
  - When `normalized/mapping_profile_snapshot.json` is present, `normalization.ocsf_version` SHOULD
    match `mapping_profile_snapshot.ocsf_version`.

Recommended version recording (aligned with ADR-0001; normative if present):

- `versions.contracts` (object): map of `contract_id -> contract_version` for all contract-backed
  artifacts produced in the run.

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
| `signing`       | `fail_closed` (when enabled)                           | `security/checksums.txt`,`security/signature.ed25519`          | If signing is enabled and verification fails or is indeterminate, the run MUST fail closed.                        |

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

Each ground truth entry MUST include:

- `idempotence` (`idempotent | non_idempotent | unknown`)
- `lifecycle.phases[]` (ordered phase records)

Invariants (normative):

- When `lifecycle.phases[]` is present, `timestamp_utc` MUST equal
  `lifecycle.phases[0].started_at_utc`.
- Phases MUST appear in chronological order; within a phase, `attempt_ordinal` increases for
  retries.

Each phase record MUST include:

- `phase` (`prepare | execute | revert | teardown`)
- `attempt_ordinal` (int, starting at 1)
- `started_at_utc`, `ended_at_utc` (RFC3339 UTC)
- `phase_outcome` (`success | failed | skipped`)
- `exit_code` (int or null)
- `error` (object or null), with:
  - `type` (enum):
    `timeout | nonzero_exit | validation_failed | exception | unsafe_rerun_blocked | cleanup_suppressed | invalid_lifecycle_transition | unknown`
  - `message` (string; redacted)
  - `details_ref` (optional evidence ref path)

Phase evidence attachment (normative; when artifacts exist):

- If `runner/actions/<action_id>/requirements_evaluation.json` is produced, the runner MUST attach
  `evidence.requirements_evaluation_ref` to the `prepare` phase record.
- If `execute` is attempted, the runner MUST attach:
  - `evidence.executor_ref`, and
  - `evidence.stdout_ref` and `evidence.stderr_ref` to the `execute` phase record.
- If `runner/actions/<action_id>/terminal.cast` is produced, the runner MUST attach
  `evidence.terminal_recording_ref` to the `execute` phase record.
- If `revert` is attempted, the runner MUST attach:
  - `evidence.executor_ref`, and
  - `evidence.cleanup_stdout_ref` and `evidence.cleanup_stderr_ref` to the `revert` phase record.
- If `runner/actions/<action_id>/cleanup_verification.json` is produced, the runner MUST attach
  `evidence.cleanup_verification_ref` to the `teardown` phase record.
- If `runner/actions/<action_id>/state_reconciliation_report.json` is produced, the runner MUST
  attach `evidence.state_reconciliation_report_ref` to the `teardown` phase record.

Note (normative): `runner/actions/<action_id>/terminal.cast` is an optional asciinema terminal
session recording for human playback and MUST NOT be used for scoring inputs.

Requirements and environment assumptions (normative; when evaluated):

- When the runner evaluates action requirements (permissions and environment assumptions), each
  ground truth entry MUST include a `requirements` object with:
  - `declared` (object): effective requirements after merging scenario overrides and
    template-derived requirements (when applicable).
  - `evaluation` (string enum): `satisfied | unsatisfied | unknown`.
  - `results` (array): one row per evaluated requirement check. Each result MUST include:
    - `kind` (string enum): `platform | privilege | tool`
    - `key` (string): stable token (example: `windows`, `admin`, `powershell`)
    - `status` (string enum): `satisfied | unsatisfied | unknown`
    - `reason_domain` (string): stable reason namespace identifier
      - MUST equal `requirements_evaluation`
    - `reason_code` (string): stable reason token (scoped by `reason_domain`). Minimum set:
      `unsupported_platform`, `insufficient_privileges`, `missing_tool`, `requirement_unknown`.
- `requirements.declared` MUST be canonicalized:
  - any arrays (example: `platform.os`, `tools`) MUST be lowercased, de-duplicated, and sorted
    lexicographically.
  - empty arrays MUST be omitted.
- `requirements.results[]` MUST be ordered deterministically by the tuple `(kind, key)` using UTF-8
  byte order (no locale).
- If `requirements.evaluation=unsatisfied`, the runner MUST set the `prepare` phase
  `phase_outcome=skipped` and MUST NOT attempt `execute`.

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

Re-run safety and refusal recording (normative):

- A ground truth line represents a single **action instance** (`action_id`) and MUST NOT collapse
  distinct planned executions into one line.
  - If a plan (v0.2+) schedules equivalent executions multiple times (same `action_key` and same
    `target_asset_id`), each scheduled execution MUST be represented as a separate ground truth line
    with a distinct `action_id`.
- If a runner refuses to attempt `execute` for an action instance due to re-run safety rules (for
  example, the action is treated as `non_idempotent` and a prior execute-side effect is not proven
  reverted), the runner MUST still emit a ground truth line and MUST record:
  - an `execute` phase record with `phase_outcome="skipped"`, and
  - `reason_domain="ground_truth"`, and `reason_code="unsafe_rerun_blocked"`.
- If `plan.cleanup=false` (or an equivalent operator-intent control) suppresses cleanup behavior for
  an action instance, the runner MUST record:
  - `revert.phase_outcome="skipped"` with `reason_domain="ground_truth"` and
    `reason_code="cleanup_suppressed"`, and
  - `teardown.phase_outcome="skipped"` with `reason_domain="ground_truth"` and
    `reason_code="cleanup_suppressed"`.
  - When suppressed, `teardown.evidence` MUST NOT reference `cleanup_verification.json` (because it
    MUST NOT be produced).
- If a runner performs multiple `execute` attempts within a single action instance (retry behavior),
  it MUST record the additional attempt(s) as retry phase records in `lifecycle.phases[]` using
  `attempt_ordinal`, and MUST NOT silently overwrite the first attempt outcome.

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

`extensions.synthetic_correlation_marker`:

- OPTIONAL stable marker string used to correlate synthetic activity generated by the runner for
  this action without heuristics.
- When synthetic correlation marker emission is enabled, the runner MUST populate
  `extensions.synthetic_correlation_marker` for every action where `execute` is attempted.
- v0.1 marker value format (normative):
  - `pa:synth:v1:<run_id>:<action_id>:execute`
  - `<run_id>` MUST equal `manifest.run_id`.
  - `<action_id>` MUST equal `ground_truth.action_id`.
- Marker values MUST be deterministic (no random suffixes) for the same `(run_id, action_id)`.
- Marker values MUST NOT contain secrets, credentials, or token-like material.
- Marker values MUST NOT be used as part of `action_key` computation (correlation only).

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
    the evaluator MUST emit `status=skipped` and MUST set a stable `reason_domain="criteria_result"`
    and `reason_code`.
- The evaluator MUST NOT suppress results silently; skipped actions MUST remain visible in the
  output.

### Runner evidence

Purpose:

- Captures executor-level artifacts needed for defensible debugging and repeatability.

#### Minimum contents (recommended):

- `runner/actions/<action_id>/stdout.txt`
- `runner/actions/<action_id>/stderr.txt`
- `runner/actions/<action_id>/executor.json` (exit_code, duration, executor type or version,
  timestamps)
- `runner/actions/<action_id>/resolved_inputs_redacted.json` (optional; redaction-safe resolved
  inputs basis used for `parameters.resolved_inputs_sha256`)
- `runner/actions/<action_id>/requirements_evaluation.json` (effective requirements + per-check
  outcomes)
- `runner/actions/<action_id>/side_effect_ledger.json` (append-only side-effect ledger; see below)
- `runner/actions/<action_id>/state_reconciliation_report.json` (when state reconciliation is
  enabled; per-action drift report)
- `runner/actions/<action_id>/attire.json` (when structured execution logging is enabled; Atomic
  uses ATTiRe)
- `runner/actions/<action_id>/atomic_test_extracted.json` (optional; Atomic template snapshot)
- `runner/actions/<action_id>/atomic_test_source.yaml` (optional; Atomic template snapshot)
- `runner/actions/<action_id>/cleanup_verification.json` (checks + results)
- `runs/<run_id>/runner/principal_context.json`
- `runs/<run_id>/logs/cache_provenance.json`

note: see [Atomic Red Team executor integration](032_atomic_red_team_executor_integration.md)

#### Runner evidence JSON header pattern (normative; contract-backed artifacts)

For per-action, contract-backed JSON evidence artifacts under `runner/actions/<action_id>/` (for
example `executor.json`, `resolved_inputs_redacted.json`, `requirements_evaluation.json`,
`side_effect_ledger.json`, `state_reconciliation_report.json`, `cleanup_verification.json`), the
artifact MUST include, at minimum:

- `contract_version` (schema constant)
- `run_id`
- `action_id`
- `action_key`
- `generated_at_utc`

Rationale: consistent joins and deterministic provenance without depending on file paths alone.

#### Requirements evaluation evidence (normative):

- When requirements evaluation is performed for an action, the runner MUST persist
  `runner/actions/<action_id>/requirements_evaluation.json`.
- The artifact MUST validate against `requirements_evaluation.schema.json`.
- The artifact MUST include, at minimum:
  - `action_id`
  - `action_key`
  - `generated_at_utc`
  - `requirements.declared`
  - `requirements.evaluation` (`satisfied | unsatisfied | unknown`)
  - `requirements.results[]` (ordered by `(kind, key)` ascending; no locale)
- The runner MUST copy `requirements.declared`, `requirements.evaluation`, and
  `requirements.results[]` into the corresponding ground truth row so reporting and scoring can
  explain skipped/failed actions without consulting runner-internal logs.
  - Each row for `requirements.results[]` MUST include `reason_domain="requirements_evaluation"`
    when `reason_code` is present.

#### Resolved inputs evidence (optional; schema-backed)

Purpose: Provide a redaction-safe, machine-readable view of the resolved inputs basis used for
`parameters.resolved_inputs_sha256` without requiring re-execution.

Normative requirements:

- When the runner emits a resolved inputs evidence artifact for an action, it MUST persist
  `runner/actions/<action_id>/resolved_inputs_redacted.json`.
- The artifact MUST validate against `resolved_inputs_redacted.schema.json`.
- The artifact MUST include, at minimum:
  - `action_id`
  - `action_key`
  - `generated_at_utc`
  - `resolved_inputs_sha256` (string; `sha256:<hex>` form)
  - `resolved_inputs_redacted` (object; see below)
- `resolved_inputs_redacted` MUST be exactly the redaction-safe resolved input map used as the hash
  basis in the Atomic executor contract (see
  [Resolved inputs hash](032_atomic_red_team_executor_integration.md#resolved-inputs-hash)).
- Hash linkage (verifiable): `resolved_inputs_sha256` MUST equal
  `sha256_hex(canonical_json_bytes(resolved_inputs_redacted))` where `canonical_json_bytes` is RFC
  8785 canonical JSON (JCS), UTF-8 bytes.
- Redaction safety: `resolved_inputs_redacted` MUST be redaction-safe by construction under the
  effective redaction policy (see [ADR-0003](../adr/ADR-0003-redaction-policy.md) and
  [security and safety](090_security_safety.md)).

#### Side-effect ledger (normative):

- The runner MUST persist a per-action side-effect ledger at
  `runner/actions/<action_id>/side_effect_ledger.json`.
- The ledger MUST be treated as append-only within a run:
  - implementations MUST only append new entries,
  - implementations MUST NOT modify or delete previously written entries.
- The ledger MUST contain an ordered `entries[]` array whose order is authoritative.
- Stable ordering requirements:
  - Each entry MUST include a monotonically increasing `seq` (positive integer).
  - `seq` MUST start at `1` and MUST increase by exactly `1` per appended entry.
  - `entries[]` MUST be ordered by `seq` ascending, with no gaps and no duplicates.
- Lifecycle attribution requirements:
  - Each entry MUST include `phase` and `phase` MUST be one of
    `prepare | execute | revert | teardown`.
  - If a side effect spans multiple lifecycle phases, the runner MUST emit one entry per phase (do
    not reuse a single entry across phases).
  - Optional failure annotation (normative):
    - If an entry includes `reason_code`, it MUST also include `reason_domain`.
    - When present, `reason_domain` MUST equal `side_effect_ledger`.
- Recovery write-ahead requirement:
  - Before performing any external or target-mutating side effect, the runner MUST append the
    corresponding ledger entry and MUST flush it to durable storage.
  - Rationale: enables deterministic recovery even if the run aborts mid-action.

#### State reconciliation report (normative; when enabled):

- When state reconciliation is enabled, the runner MUST persist a per-action state reconciliation
  report at `runner/actions/<action_id>/state_reconciliation_report.json`.
- The report MUST validate against `state_reconciliation_report.schema.json`.
- Purpose: record drift between the side-effect ledger (what the runner believes it did) and the
  target environment's observed state at a well-defined reconciliation point.
- Determinism requirements:
  - `items[]` MUST be ordered deterministically:
    - First, items derived from `cleanup_verification.json`, ordered by `check_id` ascending.
    - Then, items derived from side-effect ledger entries, ordered by `seq` ascending.
  - Any nested arrays MUST be ordered by stable key (if present).
- Probing and skip semantics:
  - The runner MUST only perform read-only probes during reconciliation.
  - If an item cannot be probed deterministically under the effective policy, the runner MUST emit
    the item with `status=skipped` (preferred) or `status=unknown`, and MUST set a stable
    `reason_domain="state_reconciliation_report"` and `reason_code`.
- Minimum required fields:
  - `action_id`
  - `action_key`
  - `generated_at_utc`
  - `status` (`clean | drift_detected | unknown | skipped`)
  - `summary` (object): `items_total`, `drift_detected`, `unknown`, `skipped`
  - `items[]` (array):
    - `source` (`cleanup_verification | side_effect_ledger`)
    - `check_id` (required when `source=cleanup_verification`)
    - `ledger_seq` (required when `source=side_effect_ledger`)
    - `status` (`match | mismatch | unknown | skipped`)
    - `reason_code` (required)

Validation:

- When produced and contract-backed, `executor.json`, `side_effect_ledger.json`,
  `cleanup_verification.json`, and `state_reconciliation_report.json` MUST be contract-validated at
  the runner publish gate before being published into their final `runner/actions/<action_id>/`
  locations (see `## Validation engine and publish gates`).

##### Principal context (runner-level evidence, schema-backed)

Purpose: Record the typed principal identity used during the run without secrets, and provide a
deterministic mapping from `action_id` to principal identity.

Format: JSON, schema-backed.

Minimum required fields (normative):

- `contract_version` (const, e.g. `"1.0.0"`)

- `run_id` (string)

- `generated_at_utc` (timestamp string)

- `principals[]` (array; stable order)

  - `principal_id` (string; stable run-local identifier; NOT a username; RECOMMENDED:
    `pa_pid_v1_<32hex>`)

  - `kind` (enum):

    - `local_user | local_admin | domain_user | service_account | ssh_key | cloud_role_session | unknown`

  - `assertion_source` (enum): `live_probe | configured | inferred | unknown`

  - `redacted_fingerprint` (optional string; MUST be redaction-safe; RECOMMENDED hash-only form)

- `action_principal_map[]` (array; stable order)

  - `action_id` (string)
  - `principal_id` (string)

Deterministic ordering (normative):

- `principals[]` MUST be sorted by `principal_id` ascending (UTF-8 byte order).
- `action_principal_map[]` MUST be sorted by `action_id` ascending (UTF-8 byte order).

Ground truth linkage (normative):

- When the runner emits `principal_context.json`, it SHOULD also copy the selected `principal_id`
  onto each action record as `extensions.principal_id` (as defined above) to support report/scoring
  joins without loading runner internals.

Redaction / disclosure (normative):

- `redacted_fingerprint`, if present, MUST be safe to disclose under the default redaction posture
  (hash-only; no raw usernames, no raw SIDs, no cloud credentials).

##### Cache provenance (run-level log, schema-backed)

Purpose: Record cache usage across stages (runner, normalization, detection compilation) as an
observable, deterministic artifact.

Minimum required fields (normative):

- `contract_version`

- `run_id`

- `generated_at_utc`

- `entries[]` (stable order)

  - `component` (string; examples: `runner`, `detection`, `normalization`)
  - `cache_name` (string; examples: `sigma_compile_cache`, `runner_identity_cache`)
  - `policy` (enum): `disabled | per_run_only | cross_run_allowed`
  - `key` (string; MUST NOT contain secrets; RECOMMENDED: `sha256:<hex>`)
  - `result` (enum): `hit | miss | bypassed`
  - `notes` (optional string; MUST be redaction-safe; MUST avoid volatile data that would break
    determinism, such as raw timestamps)

Deterministic ordering (normative):

- `entries[]` MUST be sorted by `(component, cache_name, key)` ascending (UTF-8 byte order for
  strings).

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

Optional envelope extensions (v0.1):

- `metadata.extensions.purple_axiom.synthetic_correlation_marker` (string; optional): stable marker
  used to correlate synthetic activity to a specific action and lifecycle phase.
  - When present, the value MUST be preserved verbatim from ingestion through normalization.
  - The value MUST NOT be used as part of `metadata.event_id` computation (see the event identity
    ADR for identity-basis exclusions).

Vendor-field rule (normative):

- New project-owned envelope extension fields MUST be added under `metadata.extensions.purple_axiom`
  (not as new `metadata.*` siblings), to preserve OCSF envelope compatibility while remaining
  schema-permissive for downstream tools.

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
  `missing_telemetry`.

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
1. Scenario posture (v0.2+ when implemented):
   - If `manifest.scenario.posture` is present, `manifest.scenario.posture.mode` MUST be one of:
     `baseline | assumed_compromise`.
   - When `plan/expanded_graph.json` is present and includes `scenario_posture`, implementations
     MUST enforce that `plan/expanded_graph.json.scenario_posture.mode` equals
     `manifest.scenario.posture.mode`.
1. Scenario cardinality (v0.1):
   - `manifest.scenario.scenario_id` MUST be present.
   - `ground_truth.jsonl.scenario_id` MUST either be absent or equal the manifest scenario_id.
   - The set of distinct scenario IDs observed in `normalized.metadata.scenario_id` across all
     normalized events MUST contain exactly one value.
   - Multi-scenario runs are reserved in v0.1. If more than one distinct scenario ID is observed,
     implementations MUST fail closed.
     - The enforcing stage MUST record a failed stage outcome with a stable `reason_code` drawn from
       ADR-0005’s allowed catalog (codes not listed there MUST NOT be emitted). RECOMMENDED:
       `config_schema_invalid`.
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
1. Publish-scratch hygiene (state machine integration):
   - A finalized run bundle MUST NOT contain a non-empty `runs/<run_id>/.staging/` directory.
   - If `runs/<run_id>/.staging/` exists and is non-empty after orchestration completes,
     implementations MUST fail closed (cross-cutting reason code: `storage_io_error` per ADR-0005).
1. Health/manifest coupling (when health files are emitted):
   - If `runs/<run_id>/logs/health.json` is present, then `health.run_id` MUST equal
     `manifest.run_id` and `health.status` MUST equal `manifest.status`.
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

`security/checksums.txt` MUST include one line per included file, sorted by `path` ascending using
UTF-8 byte order (no locale), in the format: `<sha256_hex><space><path><newline>`. `path` MUST be
run-relative using POSIX separators (`/`). Newlines MUST be `\n` (LF).

`security/checksums.txt` MUST include every file under `runs/<run_id>/` except:

- `<security.redaction.unredacted_dir>/**` (default: `runs/<run_id>/unredacted/`; quarantine, if
  present)
- `.staging/**` (transient publish-gate scratch area)
- Volatile diagnostics under `logs/` (see ADR-0009 and the storage formats spec Tier 0 taxonomy),
  including:
  - `logs/run.log`
  - `logs/warnings.jsonl`
  - `logs/eps_baseline.json`
  - `logs/telemetry_checkpoints/**`
  - `logs/dedupe_index/**`
  - `logs/scratch/**`
  - any other `logs/**` path not explicitly classified as deterministic evidence
- `security/checksums.txt` and `security/signature.ed25519` (to avoid self-reference)

Inclusion notes (normative):

- The following runner evidence artifacts are long-term artifacts. When present at their standard
  paths, they MUST be included in `security/checksums.txt`:
  - `runner/actions/<action_id>/side_effect_ledger.json`
  - `runner/actions/<action_id>/state_reconciliation_report.json`
  - `runner/actions/<action_id>/requirements_evaluation.json`
- If an evidence-tier artifact is withheld-from-long-term, the deterministic placeholder written at
  the standard path MUST be included in `security/checksums.txt`. Any quarantined/unredacted copies
  under `runs/<run_id>/unredacted/**` MUST NOT be included (see `090_security_safety.md`,
  "Redaction").
- Implementations MUST treat `runner/actions/<action_id>/` as part of the long-term artifact set
  (unless excluded above), including additional contract-defined runner evidence artifacts written
  under that directory.

Canonical JSON and stable bytes (normative):

- For deterministic hashing and diffability, the following JSON artifacts MUST be serialized as
  canonical JSON (RFC 8785, JCS):
  - `runner/actions/<action_id>/side_effect_ledger.json`
  - `runner/actions/<action_id>/state_reconciliation_report.json`
  - `runner/actions/<action_id>/requirements_evaluation.json`
- For these artifacts, implementations MUST write exactly `canonical_json_bytes(value)` to disk (no
  additional whitespace). Array ordering requirements defined by each artifact's contract are
  authoritative and MUST be preserved.

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

Recommended signing provenance in `manifest.json` (non-normative for field presence; normative if
present):

- When `security.signing.enabled: true`, implementations SHOULD record signing metadata in
  `manifest.json` under `extensions.security.signing`.
- If any of the following fields are recorded, they MUST match the emitted signing artifacts:
  - `extensions.security.signing.key_id` (string): the `key_id` defined above.
  - `extensions.security.signing.checksums_sha256` (string): `sha256(file_bytes)` of
    `security/checksums.txt`, as 64 lowercase hex characters.
  - `extensions.security.signing.checksums_path` (string): `security/checksums.txt`.
  - `extensions.security.signing.signature_path` (string): `security/signature.ed25519`.
  - `extensions.security.signing.public_key_path` (string): `security/public_key.ed25519`.
  - `extensions.security.signing.signature_alg` (string): `ed25519`.
  - `extensions.security.signing.hash_alg` (string): `sha256`.

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

### Spec breakup guidance (non-normative)

This document is intentionally a single hub for cross-artifact invariants and shared shapes. To keep
it maintainable:

- Stage-specific behavior SHOULD live in the owning stage spec.
- This spec SHOULD retain only the minimum behavior and invariants required to make artifact
  contracts reproducible, diffable, and CI-validatable.

When a section becomes stage-specific or begins duplicating another spec or ADR, prefer to move the
detailed behavior to the owning document and leave a short summary and link here.

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
- Project-reserved namespaces (non-exhaustive; normative if used):
  - `extensions.security`
  - `extensions.bridge`
  - `extensions.sigma`
  - `extensions.runner`
- Each namespace value SHOULD be an object; new fields SHOULD be added within a namespace object
  rather than as top-level scalars.
- Top-level fields outside `extensions` MUST NOT be introduced unless explicitly defined by this
  spec and reflected in the contract schema (strict artifacts remain closed-world by default).
- Optional versioning: namespace objects MAY include `v` (integer >= 1). Increment `v` when meanings
  change or a breaking change is introduced within that namespace; additive fields do not require a
  bump.
- Deterministic ordering: emit namespace keys in lexicographic order; within each namespace, use a
  stable key order for diffability and hashing.

Normalized events:

- Are intentionally permissive to allow full OCSF payloads and source-specific structures.
- Must still satisfy required provenance and identity fields.

#### `extensions.principal_id` (action-scoped, optional)

- `extensions.principal_id` MAY be present on a ground-truth action record.

- If present, it MUST be a **stable run-local identifier** for the principal used for that action
  and MUST NOT be a username.

- RECOMMENDED format: `pa_pid_v1_<32hex>`.

- If `runs/<run_id>/runner/principal_context.json` is present, then:

  - `extensions.principal_id` MUST equal a `principals[].principal_id` value from that artifact, and
  - the action MUST appear in `action_principal_map[]` for the same `principal_id`.

- `extensions.principal_id` MUST NOT contain secrets and MUST be safe under the repo’s redaction
  posture (hash-only or opaque token).

- `extensions.principal_id` MUST NOT participate in:

  - `metadata.event_id` identity basis (ADR-0002), or
  - `action_key` computation / idempotence identity.

## Redaction and sensitive data

- Raw commands and secrets must not be written into run bundles.
- `command_summary` is always redacted-safe. If a full command is needed for debugging, it should
  remain in volatile logs and never enter long-term storage.
- When storing raw telemetry, apply a configurable redaction policy for known sensitive fields
  (credentials, tokens, PII) before promotion into long-term stores.
- `runs/<run_id>/logs/**` contains a mix of:
  - volatile operator-local diagnostics (excluded from default export/checksums), and
  - contract-backed, CI-relevant structured logs (for example `logs/counters.json`,
    `logs/cache_provenance.json`).
- Export/share tooling MUST use a per-source redaction profile set (schema:
  `docs/contracts/redaction_profile_set.schema.json`) to determine disclosure handling and redaction
  posture for each exported artifact, including contract-backed artifacts under `logs/`.
  - If a profile set instance is validated as part of a publish-gate or export-gate, it MUST be
    registered in `docs/contracts/contract_registry.json`.
  - For contract-backed artifacts, redaction MUST preserve schema validity; if not possible, the
    artifact MUST be withheld (or kept quarantine-only) with a stable reason code, rather than
    exporting a schema-invalid file.

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

| Date      | Change                                                                                                              |
| --------- | ------------------------------------------------------------------------------------------------------------------- |
| 1/24/2026 | Clarify `logs/` deterministic evidence vs volatile diagnostics and align signing checksum scope with export policy. |
| 1/22/2026 | Add `vagrant` to `lab.provider` enum                                                                                |
| 1/17/2026 | Style guide migration (no technical changes)                                                                        |
