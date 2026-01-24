---
title: Architecture
description: Defines the high-level system flow, stage identifiers, IO boundaries, and extension points.
status: draft
category: spec
tags: [architecture, pipeline, stages, orchestrator]
related:
  - ADR-0004-deployment-architecture-and-inter-component-communication.md
  - ADR-0005-stage-outcomes-and-failure-classification.md
  - ADR-0007-state-machines.md
  - 025_data_contracts.md
  - 031_plan_execution_model.md
  - 040_telemetry_pipeline.md
  - 045_storage_formats.md
  - 065_sigma_to_ocsf_bridge.md
---

# Architecture

This document describes the high-level architecture of Purple Axiom, including the deployment
topology, pipeline stages, stage IO boundaries, and supported extension points.

## Overview

**Summary**: Purple Axiom is a one-shot, local-first pipeline that executes adversary emulation
scenarios, captures telemetry, normalizes events into OCSF, evaluates detections, and produces
reproducible run bundles.

The system resolves lab inventory, applies run-scoped environment configuration, executes scenarios,
captures telemetry, normalizes events, evaluates criteria, runs detection rules, computes scores,
and generates reports. In regression mode, the pipeline compares a candidate run to a baseline run
using pinned inputs and emits deterministic deltas in reporting artifacts. Each stage reads inputs
from the run bundle and writes outputs back to the run bundle. The filesystem is the inter-stage
contract boundary. Operators and CI drive the orchestrator via a small set of range lifecycle verbs
(build, simulate, replay, export, destroy) that map to deterministic stage subsets.

Module boundaries (v0.1; normative where stated):

- **Provision**: resolve and snapshot lab inventory (maps to `lab_provider`).
- **Configure**: apply run-scoped environment readiness work required for telemetry collection and
  scenario execution. When performed, it MUST be recorded as additive runner substage
  `runner.environment_config` and MUST NOT introduce a new stable stage identifier in v0.1.
- **Simulate**: execute scenario actions and emit ground truth + runner evidence (maps to `runner`).

Agent navigation (non-normative):

- For exact artifact paths, schemas, and hashing rules, use the
  [data contracts specification][data-contracts] and the
  [storage formats specification][storage-formats-spec].
- Authority:
  - This document is normative for stable stage identifiers, canonical stage execution order, and
    minimum stage IO boundaries.
  - [ADR-0004: Deployment architecture and inter-component communication][adr-0004] is authoritative
    for v0.1 deployment topology and inter-component communication constraints.
  - [ADR-0005: Stage outcomes and failure classification][adr-0005] is authoritative for stage
    outcome semantics, reason codes, and run status derivation.
  - [Data contracts][data-contracts] and [storage formats][storage-formats-spec] are authoritative
    for artifact schemas, publish-gate validation behavior, hashing rules, and storage layout.
  - If this document conflicts with any of the references above, the referenced ADR/spec is
    authoritative.

## Scope

This document covers:

- Deployment topology and orchestration model
- Stable stage identifiers and execution order
- Stage IO boundaries (minimum inputs and outputs)
- Component responsibilities
- Extension points
- Run bundle layout overview

This document does NOT cover:

- Detailed artifact schemas (see [data contracts specification][data-contracts])
- Storage formats and long-term retention rules (see
  [storage formats specification][storage-formats-spec])
- Configuration surface area (see [configuration reference][config-ref])
- Failure classification and reason codes (see
  [ADR-0005: Stage outcomes and failure classification][adr-0005])
- Telemetry collection details (see [telemetry pipeline specification][telemetry-spec])

## Version scope

This specification describes two scopes:

- **v0.1 (normative)**: Single-scenario runs with Atomic Red Team execution. All v0.1 requirements
  use RFC 2119 keywords (MUST, SHOULD, MAY).
- **v0.2+ (reserved)**: Multi-action plans, matrix expansion, and Caldera integration. These
  features are documented for forward compatibility but are not yet implemented.

When a section applies only to v0.2+, it is explicitly marked.

## Deployment topology

**Summary**: Purple Axiom v0.1 uses a single-host, local-first topology with a one-shot orchestrator
and file-based stage coordination.

### Orchestrator

The pipeline MUST be driven by a single **orchestrator** running on the "run host" (the machine that
owns `runs/<run_id>/`).

- The orchestrator MUST run as a **one-shot process per run** (invoked manually or via external
  scheduling).
- The orchestrator SHOULD execute core pipeline stages **in a single process** for v0.1, even if
  some steps invoke external binaries.
- Core stages MUST NOT require service-to-service RPC for coordination.

### Range lifecycle verbs (v0.1; normative where stated)

The orchestrator MAY expose a small set of stable **range lifecycle verbs** that define how
operators and CI drive the pipeline. Verbs are orchestrator entrypoints that map to a deterministic
subset of stages and to deterministic run-bundle side effects.

Common invariants (normative, v0.1):

- Every verb invocation MUST target exactly one run bundle (`runs/<run_id>/`) and MUST acquire the
  run lock (atomic create of `runs/.locks/<run_id>.lock` per
  [ADR-0004: Deployment architecture and inter-component communication][adr-0004]) before creating
  or mutating any run bundle artifacts (including `manifest.json`).
- Any verb that executes one or more stages MUST record stage outcomes in `manifest.json` per
  [ADR-0005: Stage outcomes and failure classification][adr-0005]. When health files are enabled
  (`operability.health.emit_health_files=true`), it MUST also record the same ordered outcomes in
  `logs/health.json`.
- Any verb that writes contract-backed artifacts MUST follow the publish gate rules in this document
  (staging + validation + atomic publish).
- Verbs MUST NOT introduce service-to-service RPC for coordination.

Verb definitions (v0.1):

- `build`

  - Stages executed: `lab_provider`.
  - Intent: initialize the run bundle skeleton and produce an inventory snapshot.
  - MUST NOT execute scenario actions or collect telemetry.

- `simulate`

  - Stages executed: the canonical v0.1 stage sequence (see
    [ADR-0004: Deployment architecture and inter-component communication][adr-0004]).
  - Intent: perform a complete run and produce a complete run bundle.
  - When environment configuration is enabled, the orchestrator MUST record an additive `runner`
    substage `runner.environment_config` before any action enters the `prepare` lifecycle phase.
  - When regression comparison is enabled, `simulate` MUST treat any pre-existing artifacts under
    `inputs/**` as read-only. See "Run bundle (coordination plane)" for baseline reference
    materialization semantics.

- `replay`

  - Stages executed: `normalization` → `validation` → `detection` → `scoring` → `reporting` (and
    optional `signing`).
  - Preconditions: the candidate run bundle MUST already contain `raw_parquet/**` and
    `ground_truth.jsonl`. `replay` MUST treat these inputs as read-only.
  - MUST NOT execute `runner` or `telemetry`, and MUST NOT create new artifacts under `runner/**` or
    `raw_parquet/**` except for operability logs under `logs/**`.
  - When regression comparison is enabled, `replay` MUST treat any pre-existing artifacts under
    `inputs/**` as read-only and MUST NOT rewrite them. See "Run bundle (coordination plane)" for
    baseline reference materialization semantics.

- `export`

  - Stages executed: none.
  - Intent: package a run bundle (or disclosed subset) for sharing or archival.
  - By default, exports MUST exclude `unredacted/**` and MUST NOT disclose artifacts that are not
    redaction-safe under the configured policy.
  - Export outputs (for example, an archive file) are implementation-defined and MAY be written
    outside the run bundle.

- `destroy`

  - Stages executed: none.
  - Intent: clean up run-local resources and (optionally) tear down lab resources.
  - Provider mutation (for example, deleting lab resources) MUST be explicitly enabled and MUST be
    recorded deterministically in operability logs; it MUST NOT be implied by default.

### Telemetry plane

Telemetry collection follows the canonical OpenTelemetry model:

- **Agent tier (required)**: Collector on each endpoint to read OS sources (Windows Event Log with
  `raw: true`, Sysmon, Linux auditd, syslog, osquery results).
- **Gateway tier (optional)**: Collector service that receives OTLP from agents and applies
  buffering/fan-out.

OTLP MAY be used between Collector tiers but MUST NOT be required between Purple Axiom's core
stages.

### Run bundle (coordination plane)

The run bundle (`runs/<run_id>/`) is the authoritative coordination substrate:

- Stages MUST communicate by reading and writing **contract-backed artifacts** under the run bundle
  root.
- The manifest (`runs/<run_id>/manifest.json`) MUST remain the authoritative index of what exists
  and which versions/config hashes were used.
- When environment configuration is enabled, the orchestrator MUST record the configuration boundary
  as additive substage `runner.environment_config` in the stage outcome surface (`manifest.json`,
  and `logs/health.json` when enabled) and MUST ensure deterministic operability evidence is emitted
  under `runs/<run_id>/logs/**` (schema and filenames are implementation-defined here; see the
  [operability specification][operability-spec]).

Regression comparison (when enabled) reads baseline reference artifacts under
`runs/<run_id>/inputs/` and emits deltas under `runs/<run_id>/report/**`.

- `inputs/` contains both operator-supplied run inputs (always read-only) and pipeline-materialized
  baseline reference artifacts.
- The following paths are **reserved for pipeline materialization** when regression is enabled:
  - `inputs/baseline_run_ref.json`
  - `inputs/baseline/**` Operators MUST NOT pre-populate these reserved paths.
- All stages MUST treat any pre-existing files under `inputs/**` as read-only.
- When regression comparison is enabled, the `reporting` stage MUST ensure that
  `inputs/baseline_run_ref.json` exists and is contract-valid before emitting regression results in
  `report/report.json`:
  - If `inputs/baseline_run_ref.json` already exists, `reporting` MUST treat it as read-only, MUST
    validate it, and MUST reuse it. It MUST NOT rewrite it.
  - If it does not exist, `reporting` MUST materialize it via the publish gate (staging + validation
    \+ atomic publish).
- When baseline resolution succeeds and the baseline manifest bytes are readable, the `reporting`
  stage SHOULD materialize `inputs/baseline/manifest.json` (see the
  [storage formats specification][storage-formats-spec]):
  - If `inputs/baseline/manifest.json` already exists, `reporting` MUST treat it as read-only, MUST
    validate it, and MUST reuse it. It MUST NOT rewrite it.
  - If it does not exist, `reporting` SHOULD materialize it via the publish gate.

For artifact shapes and selection rules, see the [data contracts specification][data-contracts], the
[storage formats specification][storage-formats-spec], and the
[reporting specification][reporting-spec].

See [ADR-0004: Deployment architecture and inter-component communication][adr-0004] for the
normative deployment topology and inter-component communication contract.

#### Run-scoped session state (normative)

- All durable "discovered state" (environment facts, identity summaries, cache provenance) MUST be
  written under `runs/<run_id>/`.
  - Examples include `runs/<run_id>/runner/principal_context.json` and
    `runs/<run_id>/logs/cache_provenance.json`.
- Implementations MUST NOT rely on a global per-user session database (for example, home-directory
  session stores) for correctness.
- If any global cache exists, it MUST be treated as an optimization only.
  - Any cache use that could affect run outputs MUST be recorded in the run bundle (see
    `runs/<run_id>/logs/cache_provenance.json`).

#### Publish gate (normative, v0.1)

- Stages MUST write candidate outputs under `runs/<run_id>/.staging/<stage_id>/`.
- Before publishing, stages MUST validate required contract-backed artifacts (presence + schema).
- Publishing MUST be an atomic rename/move from staging into final run-bundle paths.
- If validation fails, stages MUST NOT partially publish final-path artifacts.
- On contract validation failure, the stage MUST emit a contract validation report at
  `runs/<run_id>/logs/contract_validation/<stage_id>.json`.

## Run bundle layout

**Summary**: The run bundle (`runs/<run_id>/`) is the filesystem contract boundary between stages.
Paths are stable (no timestamps in filenames), and `manifest.json` is the authoritative index of
what exists in the bundle.

Normative top-level entries (run-relative):

| Path                               | Purpose                                                                          |
| ---------------------------------- | -------------------------------------------------------------------------------- |
| `manifest.json`                    | Authoritative run index and provenance pins                                      |
| `inputs/`                          | Operator-supplied run inputs (read-only) and regression baseline references      |
| `inputs/baseline/`                 | Baseline run snapshot materialization (regression; optional but recommended)     |
| `inputs/baseline_run_ref.json`     | Baseline selection and resolution record (regression; required when enabled)     |
| `ground_truth.jsonl`               | Append-only action timeline (what was attempted)                                 |
| `runner/`                          | Runner evidence (per-action subdirs, ledgers, verification, reconciliation)      |
| `runner/principal_context.json`    | Run-level runner evidence (principal/execution context; when enabled)            |
| `raw_parquet/`                     | Raw telemetry datasets (Parquet)                                                 |
| `raw/`                             | Evidence-tier payloads and source-native blobs (when enabled)                    |
| `normalized/`                      | OCSF-normalized event store and mapping coverage                                 |
| `criteria/`                        | Criteria pack snapshot and evaluation results                                    |
| `bridge/`                          | Sigma-to-OCSF bridge artifacts (router tables, compiled plans, coverage)         |
| `detections/`                      | Detection output artifacts                                                       |
| `scoring/`                         | Scoring summaries and metrics                                                    |
| `report/`                          | Report outputs (required: `report/report.json`, `report/thresholds.json`)        |
| `logs/`                            | Operability summaries and debug logs; not considered long-term storage           |
| `logs/health.json`                 | Stage/substage outcomes mirror (when enabled; see operability)                   |
| `logs/telemetry_validation.json`   | Telemetry validation evidence (when validation enabled)                          |
| `logs/lab_inventory_snapshot.json` | Inventory snapshot produced by `lab_provider` (referenced by manifest)           |
| `logs/contract_validation/`        | Contract validation reports by stage (emitted on validation failure)             |
| `logs/cache_provenance.json`       | Cache provenance and determinism logs (when caching is enabled)                  |
| `security/`                        | Integrity artifacts when signing is enabled                                      |
| `unredacted/`                      | Quarantined sensitive artifacts (when enabled); excluded from default disclosure |
| `plan/`                            | [v0.2+] Plan expansion and execution artifacts                                   |

Common per-action evidence location (run-relative):

- `runner/actions/<action_id>/...` (contracted per-action evidence; for example: `stdout.txt`,
  `stderr.txt`, `executor.json`, and additional artifacts such as `cleanup_verification.json`,
  `requirements_evaluation.json`, `side_effect_ledger.json`, `state_reconciliation_report.json`).

See [ADR-0004: Deployment architecture and inter-component communication][adr-0004] for filesystem
publish semantics, the [data contracts specification][data-contracts] for contracted artifact paths
and schemas, and the [storage formats specification][storage-formats-spec] for Parquet and
evidence-tier layout rules.

## Stage identifiers

**Summary**: Each stage has a stable identifier used in manifests, health files, configuration, and
logs. Substages use dotted notation.

| Stage ID        | Description                                 | Optional |
| --------------- | ------------------------------------------- | -------- |
| `lab_provider`  | Resolve and snapshot lab inventory          | No       |
| `runner`        | Execute scenario actions, emit ground truth | No       |
| `telemetry`     | Capture raw events, validate collection     | No       |
| `normalization` | Map raw telemetry to OCSF envelopes         | No       |
| `validation`    | Evaluate criteria packs                     | No       |
| `detection`     | Compile/evaluate Sigma via bridge           | No       |
| `scoring`       | Compute coverage, latency, gap metrics      | No       |
| `reporting`     | Generate human/machine-readable reports     | No       |
| `signing`       | Sign artifacts for integrity verification   | Yes      |

Substages MAY be expressed as dotted identifiers (for example, `lab_provider.connectivity`,
`runner.environment_config`, `telemetry.windows_eventlog.raw_mode`,
`telemetry.checkpointing.storage_integrity`, `validation.cleanup`, `runner.requirements`,
`runner.lifecycle_enforcement`, `runner.state_reconciliation`, `reporting.regression_compare`). The
reserved substage `runner.environment_config` represents run-scoped environment configuration
("configure") without introducing a new stable stage identifier in v0.1. Substages are additive and
MUST NOT change the semantics of the parent stage outcome.

See [ADR-0005: Stage outcomes and failure classification][adr-0005] for stage outcome definitions
and failure classification.

## Stage execution order

Preamble (normative, per
[ADR-0004: Deployment architecture and inter-component communication][adr-0004]):

- The orchestrator MUST acquire the run lock (atomic create of `runs/.locks/<run_id>.lock`) before
  creating or mutating any run bundle artifacts (including the initial `manifest.json` skeleton and
  all stage outputs).
- The orchestrator MUST create `runs/<run_id>/` and write an initial `manifest.json` skeleton before
  running the first stage.
- The orchestrator MUST treat `manifest.json` as the authoritative run index throughout the run.

The orchestrator MUST execute stages in the following order for v0.1:

1. `lab_provider`
1. `runner`
1. `telemetry`
1. `normalization`
1. `validation`
1. `detection`
1. `scoring`
1. `reporting`
1. `signing` (optional; when enabled, MUST be last)

Note: Telemetry collection MAY run concurrently with `runner` (collectors are typically started
before `runner` begins and stopped after it completes). The `telemetry` stage boundary refers to the
post-run harvest/validation/publish step that materializes `raw_parquet/**` for downstream stages.

When environment configuration is enabled, the orchestrator MUST record an additive `runner`
substage `runner.environment_config` after `lab_provider` completes and before any action enters the
runner `prepare` lifecycle phase. This substage MUST be observable via stage outcomes in
`manifest.json` and, when health files are enabled, via `logs/health.json`.

## Lifecycle state machine integrations (v0.1; guidance)

This architecture describes lifecycles that are naturally stateful (run execution, per-stage
publish, per-action execution). Implementations SHOULD model these lifecycles as explicit
finite-state machines (FSMs) when doing so improves determinism, resume safety, and testability.

Reference: [ADR-0007: State machines for lifecycle semantics][adr-0007] defines the required FSM
template and conformance expectations when a spec introduces normative lifecycle machines.

Recommended integration points (non-normative in v0.1):

1. **Orchestrator run lifecycle**

   - Authority: [ADR-0004] and [ADR-0005].
   - Canonical artifact anchors: run lock (`runs/.locks/<run_id>.lock`), `manifest.json`, and
     `logs/health.json` (when enabled).

1. **Stage publish gate lifecycle**

   - Authority: [ADR-0004] and the publish gate rules in this document.
   - Canonical artifact anchors: `runs/<run_id>/.staging/<stage_id>/`, the stage’s published output
     paths, and the recorded stage outcome.

1. **Runner action lifecycle**

   - Authority: [scenario model][scenarios-spec] (prepare → execute → revert → teardown) and runner
     integration specs.
   - Canonical artifact anchors: `ground_truth.jsonl` plus per-action runner evidence under
     `runner/actions/<action_id>/` (especially `side_effect_ledger.json`).

1. **Telemetry reliability and validation canaries**

   - Authority: [telemetry pipeline specification][telemetry-spec] and [ADR-0005] (outcome
     recording).
   - Canonical artifact anchors: `logs/telemetry_validation.json` and `raw_parquet/**`.

If a future revision of this document introduces a conformance-critical state machine definition, it
MUST use the template and conformance test requirements in [ADR-0007].

## Stage IO boundaries

**Summary**: Each stage reads inputs from the run bundle and writes outputs back. The table below
defines the minimum IO contract for v0.1.

| Stage ID        | Minimum inputs                                                                                       | Minimum outputs                                                                                                                                                                                                  |
| --------------- | ---------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `lab_provider`  | Run configuration, provider inputs                                                                   | `logs/lab_inventory_snapshot.json` (inventory snapshot; referenced by manifest)                                                                                                                                  |
| `runner`        | Inventory snapshot, scenario plan                                                                    | `ground_truth.jsonl`, `runner/actions/<action_id>/**` evidence; `runner/principal_context.json` (when enabled); \[v0.2+: `plan/**`\]                                                                             |
| `telemetry`     | Inventory snapshot, `ground_truth.jsonl` lifecycle timestamps (plus configured padding)              | `raw_parquet/**`, `raw/**` (when raw preservation enabled), `logs/telemetry_validation.json` (when validation enabled)                                                                                           |
| `normalization` | `raw_parquet/**`, mapping profiles                                                                   | `normalized/**`, `normalized/mapping_coverage.json`, `normalized/mapping_profile_snapshot.json`                                                                                                                  |
| `validation`    | `ground_truth.jsonl`, `normalized/**`, criteria pack snapshot                                        | `criteria/manifest.json`, `criteria/criteria.jsonl`, `criteria/results.jsonl`                                                                                                                                    |
| `detection`     | `normalized/**`, bridge mapping pack, Sigma rule packs                                               | `bridge/**`, `detections/detections.jsonl`                                                                                                                                                                       |
| `scoring`       | `ground_truth.jsonl`, `criteria/**`, `detections/**`, `normalized/**`                                | `scoring/summary.json`                                                                                                                                                                                           |
| `reporting`     | `scoring/**`, `criteria/**`, `detections/**`, `manifest.json`, `inputs/**` (when regression enabled) | `report/report.json`, `report/thresholds.json`, `report/**` (optional HTML + supplemental artifacts), `inputs/baseline_run_ref.json` (when regression enabled), `inputs/baseline/manifest.json` (when available) |
| `signing`       | Finalized `manifest.json`, selected artifacts                                                        | `security/**` (checksums, signature, public key)                                                                                                                                                                 |

**Note**: This table defines the **minimum** contract. Implementations MAY produce additional
artifacts, but MUST produce at least these outputs for the stage to be considered successful.

**Note**: All enabled stages MUST record a stage outcome in `manifest.json` per
[ADR-0005: Stage outcomes and failure classification][adr-0005]. When health files are enabled
(`operability.health.emit_health_files=true`), the orchestrator MUST also write the same ordered
outcomes to `logs/health.json`.

See [ADR-0004: Deployment architecture and inter-component communication][adr-0004] for detailed
publish semantics and filesystem coordination rules.

## Components

### Lab provider (inventory resolution)

**Summary**: The `lab_provider` stage resolves a concrete list of target assets and connection
metadata, producing a deterministic snapshot for the run.

Responsibilities:

- Resolve target assets from an external source (manual config, Ludus export, Terraform output,
  Vagrant export).
- Validate connectivity to resolved assets (substage: `lab_provider.connectivity`).
- Produce `logs/lab_inventory_snapshot.json` (contract-backed inventory snapshot) recorded in the
  run bundle and referenced by the manifest.
- Ensure the snapshot is hashable and diffable for determinism.
- MUST NOT implicitly provision, modify, or tear down lab resources as a side effect of inventory
  resolution; provider mutation requires an explicit operator gate and deterministic logging (see
  `destroy`).
- MUST NOT perform run-scoped environment configuration (telemetry agent bootstrap, collector
  configuration placement, readiness canaries). When environment configuration is required, it MUST
  be recorded as additive runner substage `runner.environment_config` (see Runner below).

Implementations:

- `manual`: Inline `lab.assets` in run configuration.
- `ludus`: Parse Ludus-generated inventory export (inventory format: `json`).
- `terraform`: Parse Terraform output JSON (inventory format: `json`) and normalize provider wrapper
  shape when present.
- `vagrant`: Parse Vagrant-exported inventory artifacts and map them into canonical `lab.assets`
  (inventory format: `json` RECOMMENDED).

Inventory input formats are defined by `lab.inventory.format` (supported: `json`, `ansible_yaml`,
`ansible_ini`).

The inventory snapshot is treated as an input for determinism; the manifest records
`lab.inventory_snapshot_sha256`.

See the [lab providers specification][lab-providers-spec] for input format details and adapter
requirements.

### Runner (scenario execution)

**Summary**: The `runner` stage executes test plans and emits an append-only ground truth timeline
with evidence artifacts.

Environment configuration boundary (normative, v0.1):

- The runner MAY perform run-scoped environment configuration work that is required to make the lab
  ready for telemetry collection and scenario execution (for example: telemetry agent bootstrap,
  collector configuration placement, baseline desired-state configuration (for example: DSC v3),
  readiness canaries).
- When such configuration is performed, the orchestrator MUST record an additive substage outcome
  `runner.environment_config` in `manifest.json` and, when health files are enabled, in
  `logs/health.json`. It MUST also emit deterministic operability evidence under
  `runs/<run_id>/logs/**` (schema and filenames are implementation-defined here; see the
  [operability specification][operability-spec]).
- Environment configuration is distinct from per-action requirements evaluation in `prepare`. It
  MUST NOT change the semantics of per-action lifecycle outcomes.

Preflight / Readiness Gate:

- Run before scenario execution.
- Validate resources + config invariants + required collectors/log sources.
- Implementations MAY emit a `runner.preflight` substage outcome for quick triage.
  - If emitted, it MUST be recorded in `manifest.json` and, when health files are enabled, in
    `logs/health.json`.
  - It MUST NOT introduce new `reason_code` values without updating
    [ADR-0005: Stage outcomes and failure classification][adr-0005].

Responsibilities:

- Execute scenario actions per the test plan (Atomic Red Team for v0.1; additional runners are
  future candidates).
- Execute actions through a staged lifecycle: **prepare → execute → revert → teardown**
  - `prepare`: When requirements evaluation is enabled/performed, evaluate declared
    requirements/prerequisites; emit `runner/actions/<action_id>/requirements_evaluation.json`; and
    enforce per configured policy.
  - `execute`: Invoke the primary command (detonation).
  - `revert`: Invoke cleanup commands.
  - `teardown`: Verify cleanup post-conditions.
- Requirements evaluation summary fields (when present) MUST be copied into the corresponding ground
  truth action record for deterministic downstream joins.
- When plan execution is enabled (v0.2+), compile multi-action plans to a deterministic plan graph
  (expanded nodes + edges), write `plan/expanded_graph.json`, and assign deterministic action
  instance ids (`action_id`).
- Emit `ground_truth.jsonl`: what ran, when, where, with what resolved inputs.
- When enabled, emit a per-action synthetic correlation marker event and ensure it propagates
  through telemetry, normalization, and reporting.
- Record resolved target identifiers (`asset_id` + resolved host identity).
- Capture executor transcripts (stdout/stderr) and execution metadata (exit codes, durations,
  executor identity) under `runner/actions/<action_id>/` (for example: `stdout.txt`, `stderr.txt`,
  `executor.json`).
- When state reconciliation is enabled, the runner MUST consume `side_effect_ledger.json` (and
  `cleanup_verification.json` when present), emit
  `runner/actions/<action_id>/state_reconciliation_report.json`, and record substage outcome under
  `runner.state_reconciliation`. Default is observe-only.
  - v0.1 MUST NOT perform destructive repair. If repair is requested, the runner MUST treat it as
    blocked and record the blocked intent deterministically in reconciliation outputs and outcomes.
  - Repair (when supported) requires an explicit config gate and, when applicable, an allowlist.
- At minimum, for every action where `execute` is attempted, the runner MUST emit
  `runner/actions/<action_id>/side_effect_ledger.json` (append-only: entries MUST be appended and
  previously written entries MUST NOT be modified or reordered) to record observed side effects and
  runner-injected emissions (for example, marker emission). Implementations MAY also record
  additional lifecycle-phase side effects in the ledger when needed for recovery and reconciliation
  correctness.

Ground truth records MUST include deterministic `action_key` values that remain stable across
replays. In v0.2+ (multi-action plans), ground truth records MUST also include deterministic
`action_id` values for action instances. See the [scenarios specification][scenarios-spec] for
ground truth schema and the [plan execution model specification][plan-exec-spec] for v0.2+
semantics.

Evidence artifacts are stored under `runner/actions/<action_id>/` (for example: `stdout.txt`,
`stderr.txt`, `executor.json`, and additional artifacts such as `cleanup_verification.json`,
`requirements_evaluation.json`, `side_effect_ledger.json`, `state_reconciliation_report.json`).

### Telemetry (collection and validation)

**Summary**: The `telemetry` stage captures raw events via OpenTelemetry Collectors and validates
collection invariants. Collectors run concurrently during scenario execution; the `telemetry` stage
boundary is the post-run harvest/validation/serialization step that materializes `raw_parquet/**`
for downstream normalization.

Responsibilities:

- Ensure raw Windows Event Log events are captured in raw/unrendered mode (`raw: true`) via
  pre-provisioned collector configuration and runtime canary validation (not remote config injection
  in v0.1).
- Validate agent liveness (dead-on-arrival detection) using OS-neutral collector self-telemetry
  heartbeats (substage: `telemetry.agent.liveness`).
- Support Sysmon event collection (via Windows Event Log receiver).
- Support optional osquery results ingestion (event format NDJSON via `filelog` receiver).
- Support Linux auditd log ingestion.
- Support Unix syslog ingestion.
- Execute runtime canaries (substage: `telemetry.windows_eventlog.raw_mode`).
- Validate checkpointing and dedupe behavior (substage:
  `telemetry.checkpointing.storage_integrity`).
- Validate resource budgets (substage: `telemetry.resource_budgets`).
- Produce `raw_parquet/**` for downstream normalization.

See the [telemetry pipeline specification][telemetry-spec] for collection invariants, Windows Event
Log requirements, and the [osquery integration specification][osquery-spec] for osquery-specific
details.

### Normalization (OCSF mapping)

**Summary**: The `normalization` stage maps raw telemetry to OCSF categories/classes and attaches
provenance fields.

Responsibilities:

- Map raw events to OCSF 1.7.0 envelopes per the configured mapping profile.
- Preserve the synthetic correlation marker envelope extension field, including for unmapped/raw
  routing.
- Attach provenance fields: `metadata.source_type`, host identity, tool version, `scenario_id`,
  `run_id`.
- Compute deterministic `metadata.event_id` / `metadata.uid` per [ADR-0002].
- Emit `normalized/**` as the canonical OCSF event store.
- Emit `normalized/mapping_coverage.json` summarizing field coverage and unmapped events.
- Emit `normalized/mapping_profile_snapshot.json` capturing the effective mapping profile.

See the [OCSF normalization specification][ocsf-spec] for mapping rules and the
[field tiers specification][field-tiers] for coverage requirements.

### Validation (criteria evaluation)

**Summary**: The `validation` stage evaluates versioned criteria packs against the normalized OCSF
store. Cleanup verification is produced by the runner (teardown) and consumed for scoring/reporting.

Responsibilities:

- Load criteria pack snapshot pinned in the run manifest.
- For each ground truth action, match the appropriate criteria entry.
- Evaluate expected signals within configured time windows.
- Emit `criteria/manifest.json` (pack manifest snapshot).
- Emit `criteria/criteria.jsonl` (criteria entries used).
- Emit `criteria/results.jsonl` (evaluation results per action).
- Consume cleanup verification outcomes produced by the runner (teardown) for scoring/reporting.

Criteria packs are externalized and versioned independently of the pipeline. The manifest records
`criteria.pack_sha256`.

See the [validation criteria specification][criteria-spec] for pack structure, matching semantics,
and cleanup verification.

### Detection (Sigma evaluation)

**Summary**: The `detection` stage compiles and evaluates Sigma rules against normalized OCSF events
via the Sigma-to-OCSF bridge.

The detection stage has two sub-components:

#### Sigma-to-OCSF bridge

A contract-driven compatibility layer that routes Sigma rules to OCSF event classes.

Artifacts produced:

- `bridge/router_table.json`: Logsource → OCSF class routing table.
- `bridge/mapping_pack_snapshot.json`: Full bridge inputs (router + field aliases + fallback
  policy).
- `bridge/compiled_plans/<rule_id>.plan.json`: Per-rule compilation output.
- `bridge/coverage.json`: Bridge success/failure summary.

Bridge components:

- **Logsource router**: Maps `sigma.logsource` → OCSF `class_uid` filter (+ optional producer/source
  predicates via `filters[]`).
- **Field alias map**: Maps Sigma field names → OCSF JSONPaths (or backend-specific expressions).
- **Backend adapters**: Compile to batch plan (SQL over Parquet) or stream plan.

See the [Sigma-to-OCSF bridge specification][bridge-spec] for routing rules and field alias
semantics.

#### Detection engine

Evaluates compiled Sigma rules against the normalized OCSF event store.

Responsibilities:

- Load Sigma rules and evaluate via the bridge.
- Produce `detections/detections.jsonl` (one line per detection instance).
- Report non-executable rules with reasons (fail-closed behavior).
- Compute technique coverage and detection latency.

**Fail-closed behavior**: If the bridge cannot route a rule (unknown `logsource`) or map a
referenced field, the rule is reported as **non-executable** for that run. Non-executable rules do
not produce detection instances but are included in coverage reporting.

See the [Sigma detection specification][sigma-spec] for evaluation model and output schema.

### Scoring (metrics computation)

**Summary**: The `scoring` stage joins ground truth, validation results, and detections to produce
coverage and latency metrics.

Responsibilities:

- Join `ground_truth.jsonl` with `criteria/**` and `detections/**`.
- Compute technique coverage, detection latency, and gap metrics.
- Classify gaps using the normative taxonomy (missing_telemetry, normalization_gap,
  bridge_gap_mapping, bridge_gap_feature, rule_logic_gap, etc.).
- Apply threshold gates when configured.
- Emit `scoring/summary.json` as the machine-readable scoring output.

The scoring summary is the primary input for the reporting stage and for CI threshold gates.

See the [scoring metrics specification][scoring-spec] for gap taxonomy and metric definitions.

### Reporting (output generation)

**Summary**: The `reporting` stage generates human-readable and machine-readable report outputs from
scoring data.

Responsibilities:

- Emit required machine-readable report artifacts:
  - `report/report.json` (primary machine report; includes regression results when enabled)
  - `report/thresholds.json` (threshold evaluation summary and status recommendation)
- When `reporting.emit_html=true`, render HTML scorecard to `report/report.html`.
- Include run manifest summary and artifact index.
- When regression comparison is enabled:
  - Materialize baseline reference artifacts under `inputs/`:
    - MUST write `inputs/baseline_run_ref.json`.
    - SHOULD write `inputs/baseline/manifest.json` when baseline resolution succeeds.
  - Emit regression comparison results under `report/report.json.regression`.
  - Record a `reporting.regression_compare` substage outcome in `manifest.json` and, when health
    files are enabled, in `logs/health.json` (even when baseline resolution or comparison is
    indeterminate).
- Support diffing and trending across runs.

Outputs are stored under `report/**`.

See the [reporting specification][reporting-spec] for output format requirements and trending keys.

### Signing (integrity verification, optional)

**Summary**: The `signing` stage signs the finalized run bundle for integrity verification when
enabled.

Responsibilities:

- Compute SHA-256 checksums for all long-term artifacts.
- Sign `security/checksums.txt` using Ed25519.
- Emit `security/signature.ed25519` and `security/public_key.ed25519`.
- Record `key_id` in manifest for downstream trust policies.

Signing MUST be the final stage after all other artifacts are materialized. The `signing` stage is
optional and controlled by `security.signing.enabled`.

See the [data contracts specification][data-contracts] for signing artifact formats and long-term
artifact selection rules.

## Extension points

Purple Axiom is designed for extensibility at defined boundaries:

| Extension type            | Examples                                              | Interface                                     |
| ------------------------- | ----------------------------------------------------- | --------------------------------------------- |
| Lab providers             | Manual, Ludus, Terraform, Vagrant, custom             | Inventory snapshot contract                   |
| Environment configurators | Ansible, scripts, image-baked profiles, custom        | Readiness profile + deterministic operability |
| Scenario runners          | Atomic Red Team, Caldera, custom                      | Ground truth + evidence contracts             |
| Telemetry sources         | Windows Event Log, Sysmon, osquery, auditd, EDR, pcap | OTel receiver + raw schema                    |
| Schema mappings           | OCSF 1.7.0, future OCSF versions, profiles            | Mapping profile contract                      |
| Rule languages            | Sigma, YARA, Suricata (future)                        | Bridge + evaluator contracts                  |
| Bridge mapping packs      | Logsource routers, field alias maps                   | Mapping pack schema                           |
| Evaluator backends        | DuckDB/SQL, Tenzir, streaming engines                 | Compiled plan + detection contract            |
| Criteria packs            | Default, environment-specific                         | Criteria pack manifest + entries              |
| Redaction policies        | Default patterns, custom patterns                     | Redaction policy contract                     |

Extensions MUST preserve the stage IO boundaries and produce contract-compliant artifacts.

## Key decisions

1. **Single-host, local-first execution**: v0.1 runs on a single host with no distributed control
   plane. See [ADR-0004: Deployment architecture and inter-component communication][adr-0004].
1. **File-based stage coordination**: Stages communicate via filesystem artifacts, not RPC. The run
   bundle is the single source of truth.
1. **One-shot orchestrator**: The pipeline runs as a single invocation per run. No daemon required.
1. **Deterministic stage outcomes**: Every stage produces a deterministic outcome (success, failed,
   skipped) with stable reason codes. See
   [ADR-0005: Stage outcomes and failure classification][adr-0005].
1. **Fail-closed detection**: If the bridge cannot route or map a Sigma rule, the rule is
   non-executable (not silently skipped).
1. **Inventory snapshotting**: Lab providers resolve inventory into a run-scoped snapshot for
   determinism and reproducibility.
1. **Separation of provision/configure/simulate**: Inventory resolution is isolated in
   `lab_provider`; run-scoped environment configuration (when performed) is recorded as additive
   runner substage `runner.environment_config`; scenario execution and evidence emission remain the
   responsibility of `runner`.
1. **Ground truth as append-only timeline**: The runner emits an immutable record of executed
   actions for downstream joins.
1. **Four-phase action lifecycle**: Actions execute through prepare → execute → revert → teardown
   phases with explicit verification.

## References

- [ADR-0002: Event identity and provenance][adr-0002]
- [ADR-0004: Deployment architecture and inter-component communication][adr-0004]
- [ADR-0005: Stage outcomes and failure classification][adr-0005]
- [ADR-0006: Plan execution model (reserved; v0.2+)][adr-0006]
- [ADR-0007: State machines for lifecycle semantics][adr-0007]
- [Data contracts specification][data-contracts]
- [Lab providers specification][lab-providers-spec]
- [Scenarios specification][scenarios-spec]
- [Plan execution model specification (reserved; v0.2+)][plan-exec-spec]
- [Atomic Red Team executor integration][art-exec-spec]
- [Telemetry pipeline specification][telemetry-spec]
- [osquery integration specification][osquery-spec]
- [OCSF normalization specification][ocsf-spec]
- [OCSF field tiers specification][field-tiers]
- [Validation criteria specification][criteria-spec]
- [Sigma-to-OCSF bridge specification][bridge-spec]
- [Sigma detection specification][sigma-spec]
- [Scoring metrics specification][scoring-spec]
- [Reporting specification][reporting-spec]
- [Configuration reference][config-ref]
- [Operability specification][operability-spec]
- [Storage formats specification][storage-formats-spec]

## Changelog

| Date       | Change                                                                        |
| ---------- | ----------------------------------------------------------------------------- |
| 2026-01-22 | Add Vagrant as an optional lab provider example                               |
| 2026-01-17 | Major revision: align with ADR-0004/0005, fix IO paths, add run bundle layout |
| 2026-01-15 | Added `scoring` and `signing` stages; aligned with ADR-0004/ADR-0005          |
| 2026-01-14 | Added stage IO boundaries table; updated to stable stage identifiers          |
| 2026-01-13 | Added deployment topology section; expanded bridge artifacts                  |
| 2026-01-12 | Style guide migration; added frontmatter, scope, references                   |

<!-- Reference-style links -->

[adr-0002]: ../adr/ADR-0002-event-identity-and-provenance.md
[adr-0004]: ../adr/ADR-0004-deployment-architecture-and-inter-component-communication.md
[adr-0005]: ../adr/ADR-0005-stage-outcomes-and-failure-classification.md
[adr-0006]: ../adr/ADR-0006-plan-execution-model.md
[adr-0007]: ../adr/ADR-0007-state-machines.md
[art-exec-spec]: 032_atomic_red_team_executor_integration.md
[bridge-spec]: 065_sigma_to_ocsf_bridge.md
[config-ref]: 120_config_reference.md
[criteria-spec]: 035_validation_criteria.md
[data-contracts]: 025_data_contracts.md
[field-tiers]: 055_ocsf_field_tiers.md
[lab-providers-spec]: 015_lab_providers.md
[ocsf-spec]: 050_normalization_ocsf.md
[operability-spec]: 110_operability.md
[osquery-spec]: 042_osquery_integration.md
[plan-exec-spec]: 031_plan_execution_model.md
[reporting-spec]: 080_reporting.md
[scenarios-spec]: 030_scenarios.md
[scoring-spec]: 070_scoring_metrics.md
[sigma-spec]: 060_detection_sigma.md
[storage-formats-spec]: 045_storage_formats.md
[telemetry-spec]: 040_telemetry_pipeline.md
