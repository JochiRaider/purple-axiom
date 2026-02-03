---
title: 'Project charter: continuous purple-team range'
description: Defines Purple Axiom's mission, MVP outcomes, intended users, normative dependencies, and definition of done.
status: draft
category: spec
tags: [charter, scope]
---

# Project charter: continuous purple-team range

This charter defines Purple Axiom's mission, MVP outcomes, intended users, and definition of done
for v0.1.

## Summary

Purple Axiom is a local-first cyber range that runs safe adversary-emulation scenarios, captures
telemetry, normalizes events into OCSF, evaluates detections, and produces reproducible run bundles
and scorecards.

In v0.1, the pipeline is specified as a one-shot orchestrator that executes a fixed stage sequence.
Each stage reads inputs from the run bundle and publishes outputs back into the run bundle (the
filesystem is the inter-stage contract boundary). Core stages MUST NOT require service-to-service
RPC in v0.1.

Conformance anchors (v0.1):

- **Run bundle root:** `runs/<run_id>/` (the run directory name MUST equal the run id recorded in
  `manifest.json`).
- **Run lock (outside the bundle):** the orchestrator acquires `runs/.locks/<run_id>.lock` before
  creating or mutating `runs/<run_id>/`.
- **Workspace root layout (v0.1+; reserved paths):** the workspace root (directory containing
  `runs/`) has reserved top-level directories for forward compatibility. v0.1 tooling MUST ignore
  unknown workspace files/directories and MUST NOT write persistent artifacts outside the run bundle
  except under explicitly reserved workspace locations (for example `runs/.locks/`, `cache/`, and
  `exports/`). See the Architecture spec "Workspace layout (v0.1+ normative)".
- **Stage staging root:** stages write to `runs/<run_id>/.staging/<stage_id>/` and MUST publish by
  per-path atomic replace (rename/replace) into final run-bundle paths after publish-gate
  validation.
- **Stage identifiers vs output directories:** stage identifiers appear in stage outcomes
  (`manifest.json` and `logs/health.json` when enabled) and do not necessarily match output
  directory names (for example, stage `reporting` publishes under `report/`, and stage `signing`
  publishes under `security/`).
- **Stage ↔ contract-backed outputs (machine-readable):**
  `contract_registry.json.bindings[].stage_owner` declares ownership for each contract-backed
  `artifact_glob` and MUST be used to construct publish-gate `expected_outputs[]` without hardcoding
  stage→contract mappings.

Stages MUST publish via deterministic filesystem semantics: write into a staging location, validate
contract-backed outputs at the publish gate, then atomically publish into the run bundle. A stage is
considered complete only when its outcome is recorded in the run manifest (and in `logs/health.json`
when enabled) and its outputs are either published or absent according to its failure mode.

Run-level status is recorded in `manifest.json` as `success | partial | failed`. In v0.1: `partial`
means artifacts are mechanically usable but one or more quality gates and/or warn-and-skip failures
occurred; `failed` means the run is not mechanically usable (including fail-closed stage failures or
missing required artifacts).

Status derivation note (v0.1):

- `manifest.status` MUST be derivable solely from recorded stage (and dotted substage) outcomes so
  run status is mechanically explainable without inspecting stage-specific artifacts.
- Any quality gate that degrades a run (for example, thresholds and/or regression comparability)
  MUST be recorded as a `warn_and_skip` failure on an appropriate stage or dotted substage so that
  `manifest.status` derivation remains purely outcome-driven.

The stable stage identifiers are:

- `lab_provider`
- `runner`
- `telemetry`
- `normalization`
- `validation`
- `detection`
- `scoring`
- `reporting`
- `signing` (when enabled)

See the
[deployment architecture ADR (ADR-0004)](../adr/ADR-0004-deployment-architecture-and-inter-component-communication.md)
for the normative run sequence, IO boundaries, publish semantics, and completion rules. Run status
derivation and stage outcome semantics are defined in ADR-0005 and the data contracts specification.

## Motivation

- Replace ad-hoc "run a test, eyeball logs" workflows with repeatable ground-truth runs and
  measurable detection outcomes
- Enable regression testing for detections, telemetry pipelines, schema mappings, and evaluation
  joins by capturing the full run bundle as a reproducible artifact set

## Principles

### Determinism and reproducibility

- A run MUST be explainable and comparable across time by inspecting the run bundle and manifest,
  not by relying on external mutable state.
- Runs intended to be diffable (CI, regression, trending) MUST pin and record effective versions and
  content hashes for pack-like inputs (scenario, mapping packs/profiles, rule sets, criteria packs
  when enabled). When version pins are omitted, any resolution MUST be deterministic and recorded.
  See ADR-0001 and the data contracts specification.
- Contracted artifacts MUST have deterministic paths (no timestamped contracted filenames).
  Timestamps belong inside artifact content, not in filenames. See the storage formats and data
  contracts specifications.
- Asset identity MUST be stable across runs (provider-native identifiers are treated as optional
  metadata, not the identity basis). See the [lab providers specification](015_lab_providers.md).
- Action identity MUST support deterministic joins across runs via a stable `action_key` basis
  canonicalized using RFC 8785 (JCS). See the [scenarios specification](030_scenarios.md) and the
  [data contracts specification](025_data_contracts.md).
- If caching is enabled, cross-run caching MUST be explicitly gated and MUST be observable. When any
  cache can influence stage outputs, the run MUST emit deterministic cache provenance under
  `logs/cache_provenance.json` and reporting MUST summarize cache provenance without relying on
  non-deterministic host state. See the configuration reference and reporting specification.

### Contract-driven, stage-scoped execution

- Each stage MUST be implementable as "read inputs from run bundle, write outputs to run bundle."
- Each stage MUST validate required contract-backed artifacts at its publish gate before atomically
  publishing outputs. Contract validation behavior (dialect, `$ref` restrictions, deterministic
  error reporting) is defined in the data contracts specification.
- For v0.1, stage ordering and the minimum published outputs are normative at the stage level (see
  ADR-0004).
- Stage outcomes MUST be recorded deterministically with stable stage identifiers and reason codes,
  such that failures can be triaged mechanically using `(stage, status, fail_mode, reason_code)`.
  See ADR-0005.

### Safety-by-default operation

Purple Axiom intentionally runs adversary emulation and MUST be safe to run in a lab. The platform
MUST default to an isolated, egress-deny posture and MUST fail closed when safety controls are
violated. Scenario-level network intent is expressed by `scenario.safety.allow_network`, but the
effective isolation posture is enforced at the lab boundary (the runner is not considered a
sufficient isolation mechanism). See the [security and safety specification](090_security_safety.md)
and the [scenarios specification](030_scenarios.md).

Evidence artifacts MUST be handled under explicit redaction and quarantine rules. Reports MUST
minimize disclosure by default and MUST surface sensitive artifacts (such as principal context) via
run-relative evidence references and coarse handling status (present/withheld/quarantined/absent),
not by rendering raw identifiers. See the security/safety spec, the redaction policy ADR, and the
reporting spec.

## Scope of the current v0.1 specification set

The current spec set defines a complete "run bundle" pipeline with deterministic artifacts and stage
outcomes, including:

- Pluggable lab provider inventory resolution and deterministic inventory snapshotting.
- Scenario execution producing a ground truth timeline with deterministic action identity, stable
  action keys for cross-run joins, and resolved targets.
- Telemetry collection over the run window, including deterministic telemetry validation evidence
  and health signals (for example, network egress canary and resource safeguards).
- Normalization into OCSF with mapping coverage outputs and deterministic per-source ordering
  suitable for regression comparisons.
- Validation against criteria packs and cleanup verification outputs (when enabled).
- Detection evaluation via the Sigma-to-OCSF bridge producing per-rule/per-technique outcomes.
- Scoring that joins ground truth, validation, detections, and normalization quality gates into a
  machine-readable summary.
- Reporting that renders human-readable artifacts and machine-readable report/threshold outputs,
  including CI-friendly status recommendations and (when enabled) regression comparability checks
  and deltas.
- Optional signing as a stage with explicit failure semantics and deterministic signature metadata.
- Contract registry and publish-gate validation as the mechanism that makes the run bundle layout
  and artifact schemas mechanically enforceable.
- Plan cardinality note (v0.1):
  - The canonical v0.1 plan shape is a single Atomic action resolved to exactly one target asset
    (1:1 action↔target).
  - Multi-action plan graphs and multi-target expansion/matrix semantics are reserved for v0.2+ and
    are intentionally out of scope for v0.1.

This stage model and the minimum published output paths are specified in the
[deployment architecture ADR](../adr/ADR-0004-deployment-architecture-and-inter-component-communication.md).
Run status derivation is specified in the data contracts spec; stage outcome semantics are specified
in ADR-0005.

## Primary outcomes

### MVP outcomes (v0.1)

The MVP outcome is a single "one-click" run that produces a reproducible run bundle containing, at
minimum:

- **Run manifest**: `manifest.json` capturing run identity, pinned versions and content hashes,
  inputs hashes, stage outcomes, and run status derivation inputs. See the
  [data contracts specification](025_data_contracts.md) and
  [ADR-0001](../adr/ADR-0001-project-naming-and-versioning.md).
- **Inventory snapshot**: a run-scoped snapshot that preserves the resolved target set even if the
  provider state changes later. See the [lab providers specification](015_lab_providers.md).
- **Ground truth timeline**: `ground_truth.jsonl`, one action per line, including deterministic
  action identity, stable action key, and resolved target metadata. See the
  [scenarios specification](030_scenarios.md).
- **Stage-scoped runner evidence**: runner evidence under `runner/**`, including structured
  execution records used to derive `ground_truth.jsonl`. See the
  [Atomic executor integration specification](032_atomic_red_team_executor_integration.md).
- **Telemetry validation evidence**: `logs/telemetry_validation.json` as the deterministic evidence
  surface for canaries and safeguards (for example, network egress policy enforcement). See the
  [operability specification](110_operability.md) and the telemetry pipeline spec.
- **Normalized event store**: `normalized/**` as the canonical normalized dataset for downstream
  detection and scoring, with mapping coverage outputs (`normalized/mapping_coverage.json`). See the
  [normalization specification](050_normalization_ocsf.md).
- **Bridge artifacts**: `bridge/**` containing the Sigma-to-OCSF mapping pack snapshot, compiled
  plans, and bridge coverage for reproducibility. See the
  [Sigma-to-OCSF bridge specification](065_sigma_to_ocsf_bridge.md).
- **Detection outcomes**: `detections/detections.jsonl` produced from Sigma evaluation via the
  detection stage.
- **Machine-readable scorecard**: `scoring/summary.json` as the required machine-readable run
  summary output and quality-gate metric basis. See the
  [scoring metrics specification](070_scoring_metrics.md).
- **Machine-readable report + CI gate surface**:
  - `report/report.json` as the canonical report JSON output for automation and dashboards, and
  - `report/thresholds.json` as the CI-friendly threshold evaluation and status recommendation
    surface (used to select exit codes). See the [reporting specification](080_reporting.md).
- **Human-readable report**: `report/**` as presentation outputs derived from scoring and other run
  artifacts (for example, HTML).
- **Health signals** (when enabled): `logs/health.json` emitting per-stage outcomes and substage
  health for operator triage and mechanical gating. See the
  [operability specification](110_operability.md).
- **Regression baseline reference** (optional when regression is enabled):
  - `inputs/baseline/manifest.json` (preferred snapshot form), and/or
  - `inputs/baseline_run_ref.json` (allowed pointer form), materialized deterministically during
    reporting publish. See the [storage formats specification](045_storage_formats.md) and
    [reporting specification](080_reporting.md).
- **Optional signing artifacts** (when enabled): `security/**` with deterministic signature metadata
  and checksums. See ADR-0004 and the security/safety spec.

Notes on required artifact paths (v0.1):

- **Inventory snapshot canonical path:** `logs/lab_inventory_snapshot.json` is the run-scoped
  resolved inventory artifact retained with the run bundle and referenced (and hashed) in
  `manifest.json`.
- **Run counters (operability + CI):** `logs/counters.json` is the stable per-run counters and
  gauges surface used for deterministic triage and CI assertions.
- **Run timeline (reporting):** `report/run_timeline.md` is a deterministic, human-readable run
  chronology derived from `manifest.json` and `ground_truth.jsonl` (UTC), intended as an
  operator-friendly single-file summary and export anchor.

Run bundle stage model, publish semantics, and minimum output paths are defined in ADR-0004. Run
status derivation and stage outcome semantics are defined in ADR-0005 and the data contracts spec.

### Operational safety outcomes (v0.1)

- **Egress deny enforcement**: when effective outbound policy is denied, telemetry validation MUST
  run a TCP connect canary from the target asset to the configured egress canary endpoint, MUST
  record deterministic evidence in `logs/telemetry_validation.json`, MUST emit a health stage entry,
  and MUST fail closed if reachability is observed under deny. See the
  [operability specification](110_operability.md) and the
  [scenarios specification](030_scenarios.md).
- **Fail-closed behavior**: safety control violations are run-fatal by default and must be
  observable in deterministic stage outcomes and reason codes. See the
  [security and safety specification](090_security_safety.md).
- **Resource safeguards are observable**: when enabled, resource and disk budget checks MUST be
  recorded as deterministic health outcomes and MUST degrade run status to `partial` (warn-and-skip)
  rather than silently passing when budgets are exceeded. See the
  [operability specification](110_operability.md).

## Intended users

- Detection engineers validating visibility and detection logic.
- SOC analysts validating investigative pivots and alert quality.
- Purple teams and continuous security testing operators running unattended lab workflows.

## Key upstream dependencies

Normative dependencies are those relied upon by the v0.1 pipeline contracts. Pinned versions live in
[SUPPORTED_VERSIONS.md](../../SUPPORTED_VERSIONS.md).

- **Atomic Red Team** as the primary v0.1 scenario plan type (other plan types are reserved). See
  the [scenarios specification](030_scenarios.md) and the
  [Atomic executor integration specification](032_atomic_red_team_executor_integration.md).
- **OpenTelemetry Collector Contrib** as the default telemetry collection mechanism (privileged,
  hardened, and minimized per the security boundary requirements). See the
  [security and safety specification](090_security_safety.md).
- **OCSF schema** as the canonical normalized event model (the `normalized/**` store is the input to
  detection and scoring stages). See the [normalization specification](050_normalization_ocsf.md).
- **Sigma toolchain (pySigma + pySigma-pipeline-ocsf)** as the detection portability layer and
  Sigma-to-OCSF bridge (evaluated in the detection stage). See the
  [Sigma-to-OCSF bridge specification](065_sigma_to_ocsf_bridge.md).
- **Native evaluator (`native_pcre2`)** as the batch evaluator backend.
- **pyarrow** as the Parquet scanning and schema inspection backend.
- **jsonschema** as the contract validation engine (publish gates, deterministic error reporting).
- **osquery** as the endpoint telemetry source (osqueryd).
- **PowerShell** as the Atomic executor runner.
- **RFC 8785 (JCS)** as the canonical JSON normalization requirement for deterministic hash bases
  and stable identity keys.

## Definition of done

Purple Axiom v0.1 is considered "done" when:

- A single command (or equivalent one-shot orchestration) can execute the canonical stage sequence
  and publish the required run bundle artifacts using the normative publish semantics (staging,
  contract validation at publish gates, atomic publish). See ADR-0004 and the data contracts spec.
- The run produces deterministic stage outcomes with stable stage identifiers and reason codes such
  that failures can be triaged mechanically using `(stage, status, fail_mode, reason_code)`. See the
  [stage outcomes ADR](../adr/ADR-0005-stage-outcomes-and-failure-classification.md).
- The run produces the required contracted artifacts (at minimum: `manifest.json`,
  `ground_truth.jsonl`, `normalized/**`, `detections/detections.jsonl`, `scoring/summary.json`,
  `report/report.json`, `report/thresholds.json`, and `logs/telemetry_validation.json`), and missing
  required artifacts are treated as contract failures (fail closed).
- The “at minimum” artifact list above is a convenience summary and is non-exhaustive; the
  authoritative minimum outputs are defined per-stage and enforced via publish-gate validation.
  - For avoidance of doubt in v0.1, reportable runs also require `logs/lab_inventory_snapshot.json`,
    `logs/counters.json`, and `report/run_timeline.md`.
  - The detection stage’s minimum output surface also includes `bridge/**` (including
    `bridge/coverage.json`) for reproducibility and downstream reporting inputs.
- Run status and CI signaling are consistent and mechanical:
  - `manifest.status` is derived per the data contracts spec as `success | partial | failed`, and
  - reporting exit codes align to `success=0`, `partial=10`, `failed=20`. See the reporting spec and
    ADR-0005.
- Re-running with the same pinned inputs MUST produce identical outputs, or MUST explicitly record
  and surface the sources of nondeterminism in the run bundle and stage outcomes (fail-closed is the
  default posture for safety and contract violations). See the security/safety spec, ADR-0001, the
  data contracts spec, and the storage formats spec.
- When regression comparison is enabled, the reporting stage materializes a deterministic baseline
  reference and produces deterministic comparability checks and delta outputs, failing closed when
  baseline compatibility requirements are not met. See the reporting and storage formats specs.
- Safety defaults are enforced (isolation/egress deny and fail-closed behavior), and redaction /
  quarantine rules prevent secret-like identifiers from being disclosed in reports by default. See
  the security/safety spec and redaction policy ADR.

## References

Normative or orienting references for v0.1:

- [Scope and non-goals specification](010_scope.md) (in-scope and out-of-scope boundaries)
- [Lab providers specification](015_lab_providers.md) (inventory snapshotting, asset identity)
- [Architecture specification](020_architecture.md) (stage boundaries, component responsibilities)
- [Telemetry pipeline specification](040_telemetry_pipeline.md) (collection and validation surfaces)
- [Storage formats specification](045_storage_formats.md) (artifact tiers, schema evolution,
  regression baseline references)
- [Data contracts specification](025_data_contracts.md) (run bundle layout, artifact schemas,
  publish-gate validation)
- [Scenarios specification](030_scenarios.md) (scenario seed schema, ground truth timeline, action
  identity)
- [Plan execution model specification](031_plan_execution_model.md) (reserved v0.2+ plan graph
  model)
- [Atomic executor integration specification](032_atomic_red_team_executor_integration.md)
  (transcript capture, cleanup verification)
- [Normalization specification](050_normalization_ocsf.md) (OCSF mapping, versioning policy)
- [OCSF field tiers specification](055_ocsf_field_tiers.md) (Tier 1 coverage gate basis)
- [Detection specification](060_detection_sigma.md) (Sigma evaluation stage behavior)
- [Sigma-to-OCSF bridge specification](065_sigma_to_ocsf_bridge.md) (routing, field mapping,
  detection evaluation)
- [Scoring metrics specification](070_scoring_metrics.md) (quality gates, regression comparable
  metric surface)
- [Reporting specification](080_reporting.md) (report JSON, thresholds, exit codes, regression
  reporting)
- [Security and safety specification](090_security_safety.md) (safety posture, boundaries,
  redaction, secrets)
- [Test strategy CI specification](100_test_strategy_ci.md) (fixtures, CI gates, determinism checks)
- [Operability specification](110_operability.md) (health signals, canaries, resource safeguards)
- [Configuration reference](120_config_reference.md) (configuration determinism and secret reference
  rules)
- [SUPPORTED_VERSIONS.md](../../SUPPORTED_VERSIONS.md) (pinned upstream versions)
- [ADR-0001: Project naming and versioning](../adr/ADR-0001-project-naming-and-versioning.md) (pins,
  hashes, trending keys)
- [ADR-0002: Event identity and provenance](../adr/ADR-0002-event-identity-and-provenance.md) (event
  identity, provenance)
- [ADR-0003: Redaction policy](../adr/ADR-0003-redaction-policy.md) (withhold/quarantine rules)
- [ADR-0004: Deployment architecture](../adr/ADR-0004-deployment-architecture-and-inter-component-communication.md)
  (stage model, run sequence, IO boundaries, publish semantics)
- [ADR-0005: Stage outcomes](../adr/ADR-0005-stage-outcomes-and-failure-classification.md) (stage
  outcomes taxonomy and CI gating implications)
- [ADR-0006: Plan execution model](../adr/ADR-0006-plan-execution-model.md) (reserved multi-target
  and matrix plan semantics)

## Changelog

| Date       | Change                                                                                                                                                                                                                           |
| ---------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2026-01-24 | Clarify run-bundle anchors (lock + staging), make status derivation/quality-gate representation explicit, and enumerate `logs/lab_inventory_snapshot.json`, `logs/counters.json`, and `report/run_timeline.md` as v0.1 artifacts |
| 2026-01-19 | Align charter with publish-gate validation, manifest/status semantics, thresholds/regression, and expanded references                                                                                                            |
| 2026-01-17 | Add bridge artifacts to MVP outcomes; expand references section                                                                                                                                                                  |
| 2026-01-13 | Expand charter to reflect current v0.1 stage model, safety, operability                                                                                                                                                          |
| 2026-01-12 | Formatting update                                                                                                                                                                                                                |
