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
  scenario execution. This MAY include enabling benign background activity/noise generators used to
  improve dataset realism (for example scheduled tasks/cron, domain activity generators, or user
  simulation agents). When performed, it MUST be recorded as additive runner substage
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

For v0.1 compliance, the orchestrator MUST perform deterministic run initialization ("build
semantics") for every run. Implementations MAY expose this as a distinct `build` verb; otherwise,
`simulate` MUST execute the same build semantics as its first step.

Common invariants (normative, v0.1):

- Every verb invocation MUST target exactly one run bundle (`runs/<run_id>/`) and MUST acquire the
  run lock (atomic create of `runs/.locks/<run_id>.lock` per
  [ADR-0004: Deployment architecture and inter-component communication][adr-0004]) before creating
  or mutating any run bundle artifacts (including `manifest.json`).
- Materialize/pin operator inputs under `runs/<run_id>/inputs/` (at minimum `inputs/range.yaml` and
  `inputs/scenario.yaml`; when the plan execution model is enabled (v0.2+), also pin
  `inputs/plan_draft.yaml`) before running the first stage.
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
  - Intent: initialize the run bundle skeleton, materialize/pin operator inputs under
    `runs/<run_id>/inputs/`, and produce an inventory snapshot.
  - Build-time input ingestion (normative, v0.1):
    - The orchestrator MUST materialize the effective inputs used for the run into the run bundle
      as:
      - `inputs/range.yaml` (range configuration snapshot)
      - `inputs/scenario.yaml` (scenario definition snapshot)
      - `inputs/plan_draft.yaml` (v0.2+; plan draft snapshot when plan compilation/execution is
        enabled)
    - These inputs MUST be treated as read-only by all stages. Implementations MUST NOT mutate these
      snapshots after `build` completes.
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

  - Default stages executed: `normalization` → `validation` → `detection` → `scoring` → `reporting`
    (and optional `signing`).
  - Preconditions: the candidate run bundle MUST already contain `ground_truth.jsonl` and either:
    - `raw_parquet/**` (full replay; `normalization` and `validation` are executed), OR
    - a normalized event store (normalized-input replay; v0.2+):
      - `normalized/ocsf_events/` (Parquet dataset; MUST include
        `normalized/ocsf_events/_schema.json`), OR `normalized/ocsf_events.jsonl`, AND
      - `normalized/mapping_profile_snapshot.json`.
  - Normalized-input replay fast path (v0.2+; normative when used):
    - If a normalized event store exists and its normalization provenance matches the current
      version control for the run, the orchestrator MUST skip directly to `detection`.
    - Match criteria (normative):
      - `normalized/mapping_profile_snapshot.json` MUST validate against the data contracts.
      - `normalized/mapping_profile_snapshot.json.ocsf_version` MUST equal
        `manifest.versions.ocsf_version`.
      - `normalized/mapping_profile_snapshot.json.mapping_profile_sha256` MUST equal the expected
        mapping profile hash for the run, computed using the hashing rules in
        `025_data_contracts.md` ("mapping_profile_snapshot.json").
    - Stage behavior (normative):
      - Stages executed: `detection` → `scoring` → `reporting` (and optional `signing`).
      - The orchestrator MUST record `normalization` and `validation` as `status="skipped"` with
        `fail_mode="warn_and_skip"` and `reason_code="normalized_store_reused"`.
      - If the match criteria fail and `raw_parquet/**` is absent, `replay` MUST fail closed with
        `reason_code="normalized_store_incompatible"`.
  - Input immutability (normative): `replay` MUST treat `ground_truth.jsonl`, `raw_parquet/**` (when
    present), and `normalized/**` (when present) as read-only.
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
- `inputs/threat_intel/` (when threat intelligence is enabled; v0.2+)
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

#### Cross-run caches and derived state (optional; explicitly gated)

"Derived state" is any materialized output that can be deterministically recomputed from pinned,
run-scoped inputs (for example compiled plans, parsed schemas, resolved inventories, or intermediate
indexes). Derived state MAY be cached for performance, including across runs, provided determinism
and provenance rules are upheld.

Normative requirements:

- The pipeline MUST remain correct when any cross-run cache is empty, missing, corrupted, or
  cleared.
  - Implementations MUST NOT require cross-run cache state to reproduce or interpret a run bundle.
- Cross-run caches MUST be explicitly enabled (see `cache.cross_run_allowed` in the
  [configuration reference][config-ref]).
  - When cross-run caching is enabled, `logs/cache_provenance.json` MUST be written and MUST record
    every cache lookup that can influence stage outputs (`hit | miss | bypassed`).
- Cross-run cache storage MUST be workspace-scoped.
  - Any cross-run cache directory MUST resolve under `<workspace_root>/cache/` (see Workspace
    layout) and MUST NOT be a per-user home directory cache (for example `~/.cache`) or a global OS
    temp directory.
- Cached values MUST NOT bypass publish-gate validation.
  - If a cached value is used to populate a contract-backed artifact, the artifact MUST still be
    validated against its schema before publish, and MUST be published atomically via the publish
    gate.
- Cache keys MUST be stable and redaction-safe.
  - Keys SHOULD be content-addressed (RECOMMENDED: `sha256:<hex>` over a canonical JSON key-basis
    object). Keys MUST NOT embed absolute paths, hostnames, or raw inputs that may contain secrets.

##### SQLite-backed cross-run cache (non-normative implementation guidance)

A practical implementation of a cross-run cache is a single SQLite database under a configured cache
directory (for example a component's `*_cache_dir`), storing content-addressed blobs plus stable
metadata.

Recommended schema shape (illustrative):

```sql
-- Content-addressed value store.
CREATE TABLE IF NOT EXISTS blobs (
  blob_sha256 TEXT PRIMARY KEY,
  bytes BLOB NOT NULL,
  size_bytes INTEGER NOT NULL,
  content_type TEXT,
  created_at_utc TEXT
);

-- Lookup keys to blob references (one namespace per logical cache).
CREATE TABLE IF NOT EXISTS cache_entries (
  namespace TEXT NOT NULL,
  key_sha256 TEXT NOT NULL,
  value_blob_sha256 TEXT NOT NULL REFERENCES blobs(blob_sha256),
  meta_jcs BLOB NOT NULL,
  created_at_utc TEXT,
  PRIMARY KEY (namespace, key_sha256)
);
```

Implementation notes:

- `key_sha256` SHOULD match the `entries[].key` value recorded in `logs/cache_provenance.json`
  (without the `sha256:` prefix).
- `meta_jcs` SHOULD be RFC 8785 JCS canonical JSON bytes and SHOULD NOT include volatile values
  (timestamps, absolute paths).
- Any eviction policy is acceptable as long as it only affects performance (not outputs).

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

| Path                                      | Purpose                                                                                           |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------- |
| `manifest.json`                           | Authoritative run index and provenance pins                                                       |
| `inputs/`                                 | Pinned run inputs (scenario, range config; optional plan draft when enabled).                     |
| `inputs/plan_draft.yaml`                  | Plan draft snapshot (v0.2+; when plan compilation/execution is enabled).                          |
| `inputs/baseline/`                        | Baseline run snapshot materialization (regression; optional but recommended)                      |
| `inputs/baseline_run_ref.json`            | Baseline selection and resolution record (regression; required when enabled)                      |
| `ground_truth.jsonl`                      | Append-only action timeline (what was attempted)                                                  |
| `runner/`                                 | Runner evidence (per-action subdirs, ledgers, verification, reconciliation)                       |
| `runner/principal_context.json`           | Run-level runner evidence (principal/execution context; when enabled)                             |
| `raw_parquet/`                            | Raw telemetry datasets (Parquet)                                                                  |
| `raw/`                                    | Evidence-tier payloads and source-native blobs (when enabled)                                     |
| `normalized/`                             | OCSF-normalized event store and mapping coverage                                                  |
| `criteria/`                               | Criteria pack snapshot and evaluation results                                                     |
| `bridge/`                                 | Sigma-to-OCSF bridge artifacts (router tables, compiled plans, coverage)                          |
| `detections/`                             | Detection output artifacts                                                                        |
| `scoring/`                                | Scoring summaries and metrics                                                                     |
| `report/`                                 | Report outputs (required: `report/report.json`, `report/thresholds.json`)                         |
| `logs/`                                   | Operability summaries and debug logs; not considered long-term storage                            |
| `logs/health.json`                        | Stage/substage outcomes mirror (when enabled; see operability)                                    |
| `logs/telemetry_validation.json`          | Telemetry validation evidence (when validation enabled)                                           |
| `logs/lab_inventory_snapshot.json`        | Inventory snapshot produced by `lab_provider` (referenced by manifest)                            |
| `logs/contract_validation/`               | Contract validation reports by stage (emitted on validation failure)                              |
| `logs/cache_provenance.json`              | Cache provenance and determinism logs (when caching is enabled)                                   |
| `logs/dedupe_index/`                      | Volatile normalization runtime index (restart-oriented; excluded from default exports/checksums). |
| `security/`                               | Integrity artifacts when signing is enabled                                                       |
| `security/redaction_policy_snapshot.json` | Snapshot of the effective redaction policy (recommended when redaction is enabled).               |
| `unredacted/`                             | Quarantined sensitive artifacts (when enabled); excluded from default disclosure                  |
| `plan/`                                   | [v0.2+] Plan expansion and execution artifacts                                                    |

Common per-action evidence location (run-relative):

- `runner/actions/<action_id>/...` (contracted per-action evidence; for example: `stdout.txt`,
  `stderr.txt`, `executor.json`, and additional artifacts such as `cleanup_verification.json`,
  `requirements_evaluation.json`, `side_effect_ledger.json`, `state_reconciliation_report.json`).

See [ADR-0004: Deployment architecture and inter-component communication][adr-0004] for filesystem
publish semantics, the [data contracts specification][data-contracts] for contracted artifact paths
and schemas, and the [storage formats specification][storage-formats-spec] for Parquet and
evidence-tier layout rules.

## Workspace layout (v0.1+ normative)

**Summary**: The workspace root (`<workspace_root>/`) is the stable filesystem boundary that
contains run bundles and all other durable Purple Axiom artifacts. Even though v0.1 is a one-shot
CLI, the workspace layout is treated as a forward-compatible filesystem API: introducing a UI,
concurrency, or resumability MUST NOT require directory migrations or re-keying.

### Workspace root definition

- `<workspace_root>` is any directory that contains a `runs/` child directory.
- Default `<workspace_root>` for v0.1 CLI: the current working directory.
- Tooling MUST tolerate and ignore unknown files/directories at `<workspace_root>/` (do not assume
  an empty directory).

### Reserved workspace-root children

The following workspace-root children are **reserved names**. Implementations MUST NOT place
unrelated content at these paths, and v0.1 tooling MUST ignore their presence when unused.

| Path (workspace-root relative) | Purpose                                                             | v0.1 requirement |
| ------------------------------ | ------------------------------------------------------------------- | ---------------- |
| `runs/`                        | Run bundles (authoritative pipeline outputs)                        | required         |
| `state/`                       | Durable control-plane state (run registry, secrets, UI/daemon)      | reserved         |
| `exports/`                     | Derived exports and export manifests                                | reserved         |
| `cache/`                       | Cross-run caches and derived state (explicitly gated; optional use) | reserved         |
| `logs/`                        | Workspace-local logs/audit (v0.2+)                                  | reserved         |
| `plans/`                       | Operator-authored plan drafts and draft metadata (v0.2+)            | reserved         |

Notes:

- v0.1 tooling MUST NOT require `state/`, `logs/`, `plans/`, `exports/`, or `cache/` to exist unless
  the invoked feature explicitly uses that directory.
- `runs/` is the only directory whose contents are treated as authoritative pipeline outputs.
- `runs/.locks/` is reserved for lockfiles and is not a run directory; scanners MUST ignore it.
- `state/`, `exports/`, `cache/`, `logs/`, and `plans/` MUST NOT be treated as run artifact roots
  and MUST NOT be included in run-bundle export packaging unless a spec explicitly says so.

### Workspace write boundary

Normative requirements:

- Stages MUST treat `runs/<run_id>/` as their only persistent output surface.

- The orchestrator MAY write outside the run bundle only in reserved workspace locations:

  - `runs/.locks/<run_id>.lock` (required)
  - `<workspace_root>/cache/` (optional; only when cross-run caching is explicitly enabled)
  - `<workspace_root>/exports/` (optional; only for explicit export/packaging commands)
  - `<workspace_root>/state/` and `<workspace_root>/logs/` (reserved for v0.2+ control-plane
    features; v0.1 SHOULD leave these untouched)

- Tooling MUST NOT create or modify other workspace-root siblings as a side effect of a run.

- Tooling MUST NOT write durable artifacts outside `<workspace_root>/` (for example `~/.cache`,
  `~/.config`, `/var/tmp`) for correctness or resumability.

### Run discovery surfaces

- A run MUST be considered present if and only if `runs/<run_id>/manifest.json` exists and validates
  against the manifest contract.

- Implementations MAY maintain a derived workspace run registry at
  `<workspace_root>/state/run_registry.json` for fast discovery, but it MUST be rebuildable by a
  deterministic scan of `runs/<run_id>/manifest.json` surfaces:

  - The scan MUST ignore non-run directories under `runs/` (for example `runs/.locks/`).
  - The scan order MUST be deterministic: enumerate candidate run directories and sort by `run_id`
    ascending (UTF-8 byte order) before reading manifests.

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

## Cross-cutting patterns (v0.1; normative)

**Summary**: This section defines cross-cutting design patterns that MUST be applied consistently
across v0.1 stages and extension points. These patterns exist to preserve: (1) deterministic,
contract-backed run bundles, (2) crash-safe reruns/replay behavior, and (3) safety-by-default
operation in a lab-isolated environment.

### Stage cores and CLI wrappers (v0.1; guidance)

To preserve the optional evolution path to a "local multi-process" stage-per-command mode (see
[ADR-0004]), implementations SHOULD structure each stage as:

- a ports-injected **core** entrypoint (library function/module) that contains the stage logic and
  depends only on port interfaces and explicit parameters, and
- an optional **stage CLI wrapper** that performs argument parsing + composition root wiring and
  then calls the same core.

Requirements (normative when a stage CLI wrapper exists):

- A stage CLI wrapper MUST NOT re-implement stage logic; it MUST delegate to the stage core.
- The orchestrator MAY call stage cores directly in-process (v0.1 baseline) and MAY invoke stage CLI
  wrappers in a future multi-process mode without changing stage semantics.
- Stage outcome persistence remains orchestrator-owned: stage cores and stage CLI wrappers MUST NOT
  write `manifest.json` or `logs/health.json` directly; they MUST emit outcomes via `OutcomeSink`
  (see [ADR-0005]).

### Cross-cutting ports (interfaces)

Implementations MAY choose any runtime framework, but the orchestrator and each stage MUST be
written against the following logical ports (language-agnostic). Concrete implementations MAY add
fields, but MUST preserve the semantics below.

#### Port: `RunLock`

Purpose: enforce the single-writer invariant for a run bundle.

Required operations (minimum):

- `acquire(run_id) -> acquired: bool`
  - Semantics: MUST be an exclusive acquisition using atomic-create semantics for
    `runs/.locks/<run_id>.lock` (or an equivalent mechanism with identical exclusivity).
- `release(run_id) -> void` (best-effort; MAY be a no-op on crash)

Observability:

- If the lock cannot be acquired, the orchestrator MUST NOT create or mutate `runs/<run_id>/` and
  MUST fail the invocation deterministically (see conformance tests).

#### Port: `PublishGate`

Purpose: provide “transaction-like” artifact publication: stage writes are staged, validated, and
then atomically promoted.

Required operations (minimum):

- `begin_stage(stage_id) -> StagePublishSession`
- `StagePublishSession.write_bytes(artifact_path, bytes) -> void`
- `StagePublishSession.write_json(artifact_path, obj, canonical: bool=true) -> void`
- `StagePublishSession.write_jsonl(artifact_path, rows_iterable) -> void`
- `StagePublishSession.finalize(expected_outputs: list[ExpectedOutput]) -> PublishResult`
- `StagePublishSession.abort() -> void`

Where:

- `artifact_path` is run-relative (e.g., `logs/health.json`), NOT an absolute path.
- `ExpectedOutput` includes:
  - `artifact_path` (run-relative)
  - `contract_id` (schema/contract identity as used by the contract validator)
  - `required: bool` (default `true`)

Deterministic stage → contract-backed outputs (normative):

- The contract registry (`contract_registry.json`) is the source of truth for stage ownership of
  contract-backed artifacts via `bindings[].stage_owner`.
- The contract registry (`contract_registry.json`) is also the source of truth for validation
  dispatch of contract-backed artifacts via `bindings[].validation_mode` (see
  `025_data_contracts.md`).
- The orchestrator (or stage wrapper) MUST construct `expected_outputs[]` by joining the current
  `stage_id` to `bindings[].stage_owner` and mapping concrete artifact paths to `contract_id` via
  `artifact_glob`.
  - Expansion rule: for any binding with glob metacharacters (for example `*` or `**`), the stage
    wrapper MUST expand `artifact_glob` using `glob_v1` semantics defined in `025_data_contracts.md`
    ("Glob semantics (glob_v1)") over the set of staged regular files under
    `runs/<run_id>/.staging/<stage_id>/`.
  - Ordering rule: the resulting `expected_outputs[]` list MUST be sorted by `artifact_path`
    (ascending, bytewise/lexicographic) to keep validation and reporting deterministic.
- Ownership invariant: a stage MUST NOT publish any contract-backed output whose registry binding
  has `stage_owner != stage_id` (fail closed).

Finalize semantics (normative):

- All outputs for a stage MUST be written under `runs/<run_id>/.staging/<stage_id>/` first.
- Output-root guardrail: a stage MUST NOT write or promote any run-bundle output outside its
  declared output roots (see "Stage IO boundaries" above). Violations MUST fail closed.
- `finalize()` MUST validate all `expected_outputs[]` using `ContractValidator` before any atomic
  promotion.
- `finalize()` MUST treat missing required outputs as a validation failure: if any
  `expected_outputs[]` entry with `required=true` is absent, `finalize()` MUST fail closed and MUST
  NOT promote any staged outputs.
- When `finalize()` fails, the orchestrator MUST record a fail-closed stage outcome (see
  `ADR-0005-stage-outcomes-and-failure-classification.md`).
- If validation fails, `finalize()` MUST NOT promote any staged outputs into their final run bundle
  locations.
- Atomicity scope (normative; v0.1):
  - Filesystem-level atomicity MUST be defined per destination path (per
    `ExpectedOutput.artifact_path`).
  - The publish gate MUST NOT claim or rely on filesystem-global atomicity across the entire
    `expected_outputs[]` set.
  - Stage-level durability is logical and outcome-driven:
    - Contract-backed outputs MUST be treated as durable/published only when the terminal stage
      outcome has been recorded for that stage (the outcome is the commit record).
    - If a restart observes output/outcome mismatch, the orchestrator MUST apply deterministic
      reconciliation rules (see ADR-0004).
- Crash mid-promotion (normative; v0.1):
  - If, after acquiring the run lock, a restart observes one or more final-path outputs present for
    a stage but no recorded terminal stage outcome, the orchestrator MUST perform deterministic
    reconciliation per ADR-0004 (re-validate the final-path outputs; record success if valid;
    otherwise fail closed and mark downstream stages skipped).
  - `.staging/**` MUST NOT be treated as published outputs during reconciliation.
- If validation succeeds, `finalize()` MUST promote outputs using atomic publish semantics (atomic
  rename / replace into final locations).
- After a successful `finalize()`, the publish gate implementation MUST delete (or leave empty)
  `runs/<run_id>/.staging/<stage_id>/` before returning.
- Publish-scratch hygiene: once a run is in a terminal state (success/partial/failed),
  `runs/<run_id>/.staging/**` MUST be absent (or empty).
- After a successful `finalize()`, the stage core MUST emit a terminal stage outcome via
  `OutcomeSink` before control returns to the orchestrator stage loop.
  - Persistence authority: the `OutcomeSink` implementation is orchestrator-owned and is responsible
    for writing `manifest.json` and, when enabled, `logs/health.json`.

Reference publisher SDK requirement (normative):

- The repository MUST provide a reference publisher implementation ("pa.publisher.v1") that
  implements the `PublishGate` and `ContractValidator` ports exactly as specified.
- The orchestrator composition root and any first-party stage CLI wrappers MUST bind these ports to
  the reference publisher SDK and MUST NOT ship divergent implementations.
- The semantics/versioning and CI conformance fixtures are defined in `025_data_contracts.md`
  ("Producer tooling: reference publisher semantics") and `100_test_strategy_ci.md` ("Producer
  tooling conformance").

#### Port: `ContractValidator`

Purpose: deterministic schema/contract validation for run-bundle artifacts.

Required operations (minimum):

- `validate_artifact(artifact_path, contract_id) -> ValidationResult`
- `validate_many(expected_outputs: list[ExpectedOutput]) -> ContractValidationReport`

Validation dispatch (normative):

- The validator MUST select the parsing + validation strategy for an artifact using the registry
  binding's `validation_mode` (not filename extension heuristics).

Required report behavior (normative):

- When any contract-backed artifact fails validation, the implementation MUST emit a contract
  validation report artifact under `runs/<run_id>/logs/contract_validation/`.
- Validation error lists MUST be deterministically ordered as specified by the data contracts rules.

#### Port: `OutcomeSink`

Purpose: treat stage outcomes as the single source of truth for run status and CI gating.

Required operations (minimum):

- `record_stage_outcome(stage, status, fail_mode, reason_code?: string|null, details?: object|null) -> void`
- `record_substage_outcome(stage, status, fail_mode, reason_code?: string|null, details?: object|null) -> void`

Persistence semantics (normative):

- `OutcomeSink` MUST be implemented and owned by the orchestrator (composition root) and MUST be the
  only component that persists outcomes into `runs/<run_id>/manifest.json` and, when enabled,
  `runs/<run_id>/logs/health.json`.
- Stage core logic and stage CLI wrappers MUST NOT open, patch, or rewrite `manifest.json` or
  `logs/health.json` directly; they MUST emit outcomes only through `OutcomeSink`.
- Calls to `record_stage_outcome` MUST be durable: when the call returns successfully, the
  corresponding outcome tuple MUST be present in `manifest.json` and, when enabled, in
  `logs/health.json`.

Required ordering behavior (normative):

- Stage outcomes MUST be emitted in stable ordering (canonical stage order).
- Substages, when present, MUST be ordered immediately after their parent stage, sorted
  lexicographically by full `stage` string.

#### Port: `PolicyEngine`

Purpose: centralize enforcement of safety-by-default rules and determinism-sensitive feature gates.

Required operations (minimum):

- `effective_policy() -> PolicySnapshot`
- `assert_allowed(operation: PolicyOperation) -> void`
  - MUST fail closed (raise/return denial) when the policy forbids an operation.
- `redact_or_withhold(artifact_path, bytes, classification) -> RedactionDecision`
  - `RedactionDecision` MUST be explainable and MUST map to the project’s redaction posture
    (present/withheld/quarantined semantics).

#### Port: `Adapter` (Ports-and-adapters pattern)

Purpose: isolate external integrations (lab providers, telemetry tooling, rule engines, etc.) from
the orchestrator and stage core logic.

Each extension implementation MUST:

- implement an adapter interface (or equivalent) that can be swapped without changing orchestrator
  control flow,
- validate its configuration deterministically,
- provide stable identity + provenance metadata for selection recording (at minimum: `adapter_id`,
  `adapter_version`, `source_kind`, `source_ref`),
- record its identity/version inputs into the run bundle (manifest and/or deterministic evidence),
- avoid introducing service-to-service RPC dependencies for stage coordination.

### Adapter wiring and provenance (v0.1; normative)

This section defines how concrete adapters are selected and injected, and how those selections are
recorded for determinism, explainability, and regression comparability.

#### Composition root (dependency wiring)

Purpose: define a single, explicit place where concrete implementations of ports and adapters are
selected, constructed, and injected into the orchestrator and stage execution control flow.

Normative requirements:

- Implementations MUST define exactly one composition root per orchestrator process invocation.
- The composition root MUST be the only place where concrete adapter implementations are selected
  and constructed.
- Stage core logic MUST NOT import, construct, or look up concrete adapters by name; it MUST depend
  only on port interfaces and values passed in via explicit parameters.
- Dependency injection MUST be achieved using explicit constructor/function parameters (manual DI).
  This spec MUST NOT require (and MUST NOT assume) any third-party DI framework or container.
- The composition root MUST resolve adapter selections using only:
  - validated configuration inputs, and
  - the effective policy snapshot (`PolicyEngine.effective_policy()`).
- If a required port binding cannot be resolved (unknown adapter id, missing implementation, invalid
  configuration), the orchestrator MUST fail closed and MUST record a deterministic stage (or dotted
  substage) outcome.
  - The outcome `reason_code` MUST be selected from ADR-0005. Implementations SHOULD use
    `reason_code=config_schema_invalid` unless a more specific stage-scoped reason code is defined.

#### Adapter registry (selection and inventory)

Purpose: centralize the set of available adapter implementations and resolve port → adapter bindings
deterministically.

Normative requirements:

- The adapter registry MUST be an in-process mapping from `(port_id, adapter_id)` to:
  - an adapter factory (constructor/function) and
  - static metadata required for provenance recording (see "Adapter provenance recording (v0.1)").
- The registry MUST be constructed in the composition root at startup and MUST NOT be mutated after
  stage execution begins.
- The registry MAY be implemented as a static mapping; this spec does not require dynamic plugin
  discovery.
- If the registry is populated from packaged adapters (out-of-repo or otherwise), inventory
  construction MUST be explicit and deterministic:
  - The set of available packaged adapters MUST be fully determined by the effective configuration
    (and policy snapshot) for the run.
  - Ambient discovery (for example: scanning system site-packages/entrypoints, current working
    directory, or environment variables) is forbidden.
  - Any filesystem enumeration performed during registry construction MUST sort candidates using
    UTF-8 byte order and MUST treat ties deterministically.
- Core stage logic MUST NOT access the registry directly; resolved adapter instances MUST be
  injected via ports by the composition root.
- Adapter selection MUST be deterministic:
  - Given the same effective configuration and policy snapshot, the registry MUST resolve the same
    bindings.
  - Unknown adapters MUST be rejected (fail closed) unless an explicit warn-and-skip policy exists
    for that port in the effective policy snapshot.

#### Adapter provenance recording (v0.1)

For every resolved adapter binding (including built-in adapters), the orchestrator MUST record an
adapter provenance entry in the run manifest so runs remain explainable and comparable.

Storage location (normative):

- The run manifest MUST record adapter provenance under `manifest.extensions.adapter_provenance`.
- `manifest.extensions.adapter_provenance.entries[]` MUST be present even when all selected adapters
  are built-in.

Entry shape (normative):

Type names such as `id_slug_v1`, `semver_v1`, and `version_token_v1` refer to
[ADR-0001: Project naming and versioning][adr-0001].

- `port_id` (id_slug_v1; REQUIRED): stable identifier of the port being satisfied.
- `adapter_id` (id_slug_v1; REQUIRED): stable identifier of the selected adapter implementation.
- `adapter_version` (semver_v1 | version_token_v1; REQUIRED): pinned version/token used for this
  run.
- `source_kind` (id_slug_v1; REQUIRED): coarse source classification (for example: `builtin`,
  `container_image`, `local_path`, `python_module`).
- `source_ref` (string; REQUIRED): stable reference for the selected implementation source.
  - MUST NOT be an absolute host path.
  - For container images, tag-only references are forbidden; the reference MUST be digest-pinned.
- `source_digest` (string; CONDITIONALLY REQUIRED): immutable content digest for the selected
  implementation source, recorded as `sha256:<hex>`.
  - REQUIRED when `source_kind != "builtin"`.
  - For container images, `source_digest` MUST equal the digest in `source_ref`
    (`<image>@sha256:<digest>`).
  - For directory-based sources (`source_kind="local_path"`), implementations MUST compute
    `source_digest` as `hash_basis_v1` over the referenced directory tree with:
    - `artifact_kind="adapter"`
    - `artifact_id=adapter_id`
    - `artifact_version=adapter_version` (see [ADR-0001: Project naming and versioning][adr-0001]).
  - Implementations MUST fail closed if `source_digest` cannot be determined for a non-builtin
    adapter.
- `signature` (object; OPTIONAL): Ed25519 signature over the adapter provenance tuple, used for
  supply-chain attestations when adapters are provided out-of-repo.
  - `sig_alg` (string; REQUIRED): `ed25519`
  - `public_key_b64` (string; REQUIRED): base64 of the 32 raw Ed25519 public key bytes
  - `key_id` (string; REQUIRED): `sha256(public_key_bytes)` encoded as 64 lowercase hex characters
  - `signature_b64` (string; REQUIRED): base64 of the 64 raw signature bytes
  - Signature payload (normative):
    - Compute RFC 8785 (JCS) canonical JSON of the following object (with the exact field names and
      values shown), then sign the canonical bytes using Ed25519:
      ```json
      {
        "v": "adapter_signature_v1",
        "adapter_id": "<adapter_id>",
        "adapter_version": "<adapter_version>",
        "source_kind": "<source_kind>",
        "source_ref": "<source_ref>",
        "source_digest": "<source_digest>"
      }
      ```
- `config_sha256` (string; OPTIONAL): `sha256:<hex>` of canonical JSON of the adapter's effective
  configuration after redaction/withholding of secrets.
  - When present, canonical JSON MUST use RFC 8785 (JCS) serialization.
  - Implementations SHOULD include `config_sha256` when the adapter's configuration can affect any
    contract-backed output or any regression-comparable metric.

Determinism requirements (normative):

- `entries[]` MUST be sorted by `(port_id asc, adapter_id asc)` using UTF-8 byte order (no locale).
- The provenance record MUST NOT include hostnames, machine-specific absolute paths, or timestamps.
- If `source_kind != "builtin"`, `source_digest` MUST be present and MUST match
  `^sha256:[0-9a-f]{64}$`.
- If adapter signatures are required by the effective policy snapshot
  (`security.adapters.require_signatures=true`), every non-builtin entry MUST include a `signature`
  object whose `key_id` is in `security.adapters.trusted_key_ids` and whose signature verifies
  against the canonical payload above.
- If adapter provenance cannot be recorded deterministically, the orchestrator MUST fail closed and
  MUST record a deterministic stage (or dotted substage) outcome.

Third-party adapter policy (decision):

- Adapters MAY be provided out-of-repo as packaged plugins; the architecture does not restrict
  adapters to in-repo-only implementations.
- v0.1 default posture: third-party adapters are disabled. A run MUST fail closed if it attempts to
  select a non-builtin adapter when `security.adapters.allow_third_party=false`.
- When `security.adapters.allow_third_party=true`, every non-builtin adapter MUST:
  - be explicitly selected (no auto-discovery),
  - be pinned by `adapter_version` and `source_digest`, and
  - satisfy any configured signature requirements (for example
    `security.adapters.require_signatures=true`).

### Contract-first modularity (v0.1; guidance)

Implementation guidance (non-normative):

Purple Axiom’s stage model is intentionally “contract-first”: each stage can be implemented as a
black box that consumes only its contracted inputs and emits only its contracted outputs. This is
intended to support parallel development mediated solely by schema contracts and fixtures.

Recommended patterns:

1. **Dependency injection at the composition root**

   - The orchestrator SHOULD act as the composition root: it selects and constructs concrete adapter
     implementations (lab providers, telemetry tools, evaluator backends, etc.) and passes them into
     stage cores via the port interfaces defined in this section.
   - Stage core logic SHOULD NOT instantiate concrete adapters directly. Instead, it SHOULD depend
     on:
     - contracted input artifacts in the run bundle,
     - the cross-cutting ports (`PublishGate`, `ContractValidator`, `OutcomeSink`, `PolicyEngine`),
       and
     - adapter interfaces for any external integration.
   - This supports unit testing stages against fixtures by substituting deterministic fakes/mocks
     for external integrations.

1. **Strategy pattern for swappable behaviors**

   - Any configurable behavior that materially changes how a stage reads inputs or produces
     contracted outputs SHOULD be expressed as a strategy behind an adapter interface.
   - Strategy selection SHOULD be config-driven and deterministic. Avoid environment-dependent or
     “auto-discovery” selection unless it is explicitly ordered and pinned by configuration.
   - Strategy identity and version SHOULD be recorded in the run bundle via adapter provenance (see
     "Adapter provenance recording (v0.1)").

1. **Fixture-first, contract-backed stage tests**

   - Each stage SHOULD have a minimal fixture set consisting of:
     - only the contracted inputs required for the stage, and
     - the expected contracted outputs for those inputs.
   - Fixtures SHOULD be runnable without executing upstream stages (fixture inputs are treated as
     authoritative snapshots).
   - Tests SHOULD validate outputs using `ContractValidator` and SHOULD fail when any contracted
     output is invalid, missing, or non-deterministic.

Anti-patterns to avoid (non-normative):

- Cross-stage in-process calls or shared mutable state that bypasses run bundle artifacts as the
  source of truth.
- Discovery mechanisms whose behavior depends on non-deterministic iteration order (filesystem, hash
  maps, plugin registries) rather than explicit ordering and pinning.
- Hidden side-effect channels (for example background daemons or network services) that are not
  represented in the run bundle and therefore cannot be reproduced from a run bundle alone.

### Cross-cutting invariants (normative)

These invariants apply to the orchestrator, all stages, and all extension adapters.

1. **Single-writer run bundle**

   - A run bundle MUST have exactly one writer at a time (the orchestrator invocation holding the
     run lock).
   - Stage implementations MUST NOT write outside the publish-gate staging area and MUST NOT bypass
     the lock.

1. **File-based inter-stage coordination**

   - Stages MUST communicate by reading/writing contract-backed artifacts under `runs/<run_id>/`.
   - Core stages MUST NOT require service-to-service RPC for coordination (v0.1).

1. **Single composition root and explicit dependency injection**

   - The orchestrator MUST define exactly one composition root responsible for selecting and wiring
     concrete implementations of ports/adapters into the stage execution control flow.
   - Stages and other core components MUST NOT select adapters by name at runtime (no service
     locator in core logic). They MUST accept dependencies via explicit parameters from the
     composition root.

1. **Deterministic adapter selection and provenance**

   - Adapter selection MUST be mediated by the adapter registry constructed in the composition root.
   - For every resolved port binding, the run manifest MUST include an adapter provenance entry that
     meets the "Adapter provenance recording (v0.1)" requirements above.
   - If adapter provenance cannot be recorded deterministically, the run MUST fail closed.

1. **Publish-gate only for contract-backed outputs**

   - Any write to a contract-backed location MUST go through `PublishGate`.
   - Partial promotion is forbidden: if a stage fails fail-closed, it MUST NOT publish its final
     output directory.

1. **Deterministic artifact paths**

   - Contract-backed artifacts MUST use deterministic paths.
   - Timestamped contracted filenames are disallowed: timestamps belong inside artifact content, not
     in filenames.
   - Implementations MUST treat any filename containing date/time-like tokens (e.g., `YYYY-MM-DD`,
     `YYYYMMDD`, RFC3339-like `...T...Z`) as “timestamped” for the purposes of this rule (a stricter
     detector is allowed).

1. **Deterministic serialization and ordering**

   - Canonical JSON (RFC 8785 / JCS) MUST be used when canonical bytes are required for hashing or
     deterministic comparisons.
   - Arrays and ordered collections that participate in contracted artifacts or
     regression-comparable metrics MUST be stably ordered using UTF-8 byte order (no locale).

1. **Deterministic contract validation reports**

   - Validation error ordering MUST be deterministic.
   - The contract validation report artifact path MUST be stable and MUST be emitted on validation
     failure.

1. **Outcome-sourced status**

   - `manifest.status` MUST be derived from stage outcomes, not from ad-hoc runtime heuristics.
   - Stage outcome `reason_code` MUST be selected from a stable, stage-scoped set (ADR-0005).
     Unknown stage-outcome reason codes are forbidden.
   - Stage/substage outcomes MUST NOT emit `reason_domain`. The outcome domain is implicit as
     `stage_outcome` and its reason-code catalog is scoped by ADR-0005.
   - Any non-stage artifact that emits a `reason_code` field MUST also emit a sibling
     `reason_domain` field:
     - Pairing rule: `reason_domain` MUST be present iff `reason_code` is present.
     - Contract alignment: for contract-backed artifacts, `reason_domain` MUST equal the artifact
       schema’s `contract_id` (see `docs/contracts/contract_registry.json`).
     - For non-contract placeholder/operator-interface artifacts, `reason_domain` MUST be one of the
       explicitly documented constants (`artifact_placeholder`, `operator_interface`).

   Note: This architecture spec does not define per-stage default `fail_mode` values. The v0.1
   baseline defaults are specified in ADR-0005 and summarized in `025_data_contracts.md` ("Stage
   outcomes"). The "fail-closed" principle here refers to publish-gate semantics and fatal stop
   conditions, not an assertion that every stage defaults to `fail_closed` (for example,
   `validation` defaults to `warn_and_skip` in v0.1).

1. **Safety policy is enforced, not advisory**

   - The system MUST be local-first and lab-isolated by default.
   - Unexpected network egress MUST be denied by default and treated as run-fatal when violated.
   - Evidence artifacts MUST follow the effective redaction posture; if redaction cannot be applied
     deterministically, artifacts MUST be withheld or quarantined rather than written into standard
     long-term locations.

1. **Determinism-sensitive features are explicitly gated**

   - Cross-run caching MUST be default-off.
   - If cross-run caching is enabled, cache usage MUST be recorded deterministically in
     `logs/cache_provenance.json` with stable ordering.
   - If forbidden cache usage is detected at runtime, the run MUST fail closed.

### Cross-cutting conformance tests (required)

CI MUST include automated conformance tests that verify the invariants above. The following tests
are mandatory (names are suggestions; harness/framework is implementation-defined).

1. `run_lock_exclusive_single_writer`

   - Setup: start two orchestrator invocations targeting the same `run_id`.
   - Assert: at most one acquires the lock; the other fails deterministically without mutating the
     run bundle.

1. `publish_gate_atomic_publish_no_partial_outputs`

   - Setup: simulate a stage that writes multiple outputs; force an injected failure between “write”
     and “finalize”.
   - Assert: no contracted outputs appear in final locations; only staging contains partial data.
   - Assert: rerun behavior is deterministic (either cleanly resumes and publishes, or fails closed
     with a stable storage/consistency reason code).

1. `contract_validation_report_location_and_ordering`

   - Setup: produce a schema-invalid artifact via publish gate.
   - Assert: a report is written under `logs/contract_validation/`.
   - Assert: errors are deterministically ordered per the contract rules.

1. `artifact_path_timestamped_filename_blocked`

   - Setup: attempt to publish a contract-backed artifact with a timestamped filename.
   - Assert: validation fails with the stable timestamped-filename disallow rule and emits the
     validation report.

1. `outcome_ordering_and_health_mirroring`

   - Setup: run a minimal pipeline with at least one substage outcome.
   - Assert: stage ordering is stable; substages follow immediately after the parent and are sorted.
   - Assert: when `operability.health.emit_health_files=true`, `logs/health.json` mirrors the same
     ordered outcomes as `manifest.json`.

1. `adapter_provenance_entries_present_sorted_and_sanitized`

   - Setup: run a minimal pipeline (or a binding-only harness) with at least two adapter bindings
     resolved for distinct ports.
   - Assert: `manifest.extensions.adapter_provenance.entries[]` is present and is sorted by
     `(port_id, adapter_id)` using UTF-8 byte ordering.
   - Assert: each `source_ref` is stable and is not an absolute host path.
   - Assert: when `source_kind=container_image`, `source_ref` is digest-pinned
     (`<image>@sha256:<digest>`).
   - Assert: when `source_kind != "builtin"`, `source_digest` is present and matches
     `^sha256:[0-9a-f]{64}$`.
   - Assert: when `source_kind=container_image`, `source_digest` equals the digest in `source_ref`.
   - Assert: when policy requires adapter signatures, each non-builtin entry includes a `signature`
     object and the signature verifies against the canonical payload.
   - Assert: the provenance record contains no timestamps, hostnames, or machine-specific absolute
     paths.

1. `unknown_adapter_id_fail_closed_with_deterministic_outcome`

   - Setup: supply a configuration that selects an unknown `adapter_id` for a required `port_id`.
   - Assert: the orchestrator fails closed and records a deterministic failure outcome tuple
     `(stage, status, fail_mode, reason_code)` for the same inputs on repeated runs.
   - Assert: no contracted outputs for the affected stage are published.

1. `cache_cross_run_gate_and_provenance`

   - Setup: attempt to use a cache directory under `<workspace_root>/cache/` (outside
     `runs/<run_id>/`) with `cross_run_allowed=false`.
   - Assert: config validation rejects the configuration OR runtime detection fails closed.
   - Setup: enable cross-run caching explicitly and configure a cache directory under
     `<workspace_root>/cache/`.
   - Assert: `logs/cache_provenance.json` is emitted and deterministically ordered by
     `(component, cache_name, key)`.

1. `workspace_unknown_entries_ignored`

   - Setup: create a workspace root containing additional unrelated files/directories alongside the
     reserved workspace-root children.
   - Assert: the orchestrator completes a minimal run and does not treat unknown workspace entries
     as errors.

1. `workspace_write_boundary_reserved_paths_only`

   - Setup: snapshot the workspace filesystem tree; execute a minimal run; snapshot again.
   - Assert: all new/modified files are under `runs/<run_id>/` or explicitly reserved workspace
     locations used by the run (for example `runs/.locks/`, `<workspace_root>/cache/`, and
     `<workspace_root>/exports/`).
   - Assert: the run does not create new top-level directories at the workspace root other than the
     reserved set.

## Stage IO boundaries

**Summary**: Each stage reads inputs from the run bundle and writes outputs back. The table below
defines the minimum IO contract for v0.1.

| Stage ID        | Minimum inputs                                                                                             | Minimum outputs                                                                                                                                                                                                                            |
| --------------- | ---------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `lab_provider`  | Run configuration, provider inputs                                                                         | `logs/lab_inventory_snapshot.json` (inventory snapshot; referenced by manifest)                                                                                                                                                            |
| `runner`        | Inventory snapshot, scenario plan                                                                          | `ground_truth.jsonl`, `runner/actions/<action_id>/**` evidence; `runner/principal_context.json` (when enabled); (v0.2+: `plan/**`)                                                                                                         |
| `telemetry`     | inventory snapshot, `inputs/range.yaml`, `inputs/scenario.yaml`, `ground_truth.jsonl` lifecycle timestamps | `raw_parquet/**`, `raw/**` (when raw preservation is enabled), `logs/telemetry_validation.json` (when telemetry validation is enabled)                                                                                                     |
| `normalization` | `raw_parquet/**`, mapping profiles                                                                         | `normalized/**`, `normalized/mapping_coverage.json`, `normalized/mapping_profile_snapshot.json`                                                                                                                                            |
| `validation`    | `ground_truth.jsonl`, `normalized/**`, criteria pack snapshot                                              | `criteria/manifest.json`, `criteria/criteria.jsonl`, `criteria/results.jsonl`                                                                                                                                                              |
| `detection`     | `normalized/**`, bridge mapping pack, Sigma rule packs                                                     | `bridge/**`, `detections/detections.jsonl`                                                                                                                                                                                                 |
| `scoring`       | `ground_truth.jsonl`, `criteria/**`, `detections/**`, `normalized/**`                                      | `scoring/summary.json`                                                                                                                                                                                                                     |
| `reporting`     | `scoring/**`, `criteria/**`, `detections/**`, `manifest.json`, `inputs/**` (when regression enabled)       | `report/report.json`, `report/thresholds.json`, `report/run_timeline.md`, `report/**` (optional HTML + supplemental artifacts), `inputs/baseline_run_ref.json` (when regression enabled), `inputs/baseline/manifest.json` (when available) |
| `signing`       | Finalized `manifest.json`, selected artifacts                                                              | `security/**` (checksums, signature, public key)                                                                                                                                                                                           |

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
  - It MUST NOT introduce new stage outcome `reason_code` values without updating
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
- When plan execution is enabled (v0.2+), compile plans into executable sub-steps (actions) and
  assign deterministic action instance ids (`action_id`) per `025_data_contracts.md` (v0.2+ MUST NOT
  use the legacy ordinal form `s<positive_integer>`).
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
- Support Linux auditd log ingestion (normalized events use
  `metadata.source_type = "linux-auditd"`).
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

Terminology note (normative): `metadata.source_type` uses the **event_source_type** namespace
(hyphenated `id_slug_v1` literals such as `linux-auditd`). It MUST NOT be conflated with
`identity_basis.source_type` (**identity_source_type**; typically lower_snake_case such as
`windows_eventlog`, `linux_auditd`) used for deterministic `metadata.event_id` computation
(ADR-0002).

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

| Extension type            | Examples                                                                     | Interface                                     |
| ------------------------- | ---------------------------------------------------------------------------- | --------------------------------------------- |
| Lab providers             | Manual, Ludus, Terraform, Vagrant, custom                                    | Inventory snapshot contract                   |
| Environment configurators | Ansible, DSC v3, scripts, image-baked profiles, custom                       | Readiness profile + deterministic operability |
| Scenario runners          | Atomic Red Team, Caldera, custom                                             | Ground truth + evidence contracts             |
| Telemetry sources         | Windows Event Log, Sysmon, osquery, Linux auditd (`linux-auditd`), EDR, pcap | OTel receiver + raw schema                    |
| Schema mappings           | OCSF 1.7.0, future OCSF versions, profiles                                   | Mapping profile contract                      |
| Rule languages            | Sigma, YARA, Suricata (future)                                               | Bridge + evaluator contracts                  |
| Bridge mapping packs      | Logsource routers, field alias maps                                          | Mapping pack schema                           |
| Evaluator backends        | DuckDB/SQL, Tenzir, streaming engines                                        | Compiled plan + detection contract            |
| Criteria packs            | Default, environment-specific                                                | Criteria pack manifest + entries              |
| Redaction policies        | Default patterns, custom patterns                                            | Redaction policy contract                     |

Environment configurators are also the v0.1 integration point for generating realistic background
activity (“noise”) so that datasets are not comprised solely of attack actions. Examples include:

- domain and directory baseline activity (for example AD-Lab-Generator and ADTest.exe), and
- server/workstation workload activity via scheduled tasks (Windows) and cron jobs (Linux).

User simulation frameworks that require a coordinating server (for example GHOSTS) SHOULD be
deployed as optional supporting services (outside core stage boundaries) and integrated by
configuring endpoint agents via `runner.environment_config`.

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

- [ADR-0001: Project naming and versioning][adr-0001]
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

| Date       | Change                                                                         |
| ---------- | ------------------------------------------------------------------------------ |
| 2026-01-26 | Define composition root, adapter registry, and adapter provenance requirements |
| 2026-01-22 | Add Vagrant as an optional lab provider example                                |
| 2026-01-17 | Major revision: align with ADR-0004/0005, fix IO paths, add run bundle layout  |
| 2026-01-15 | Added `scoring` and `signing` stages; aligned with ADR-0004/ADR-0005           |
| 2026-01-14 | Added stage IO boundaries table; updated to stable stage identifiers           |
| 2026-01-13 | Added deployment topology section; expanded bridge artifacts                   |
| 2026-01-12 | Style guide migration; added frontmatter, scope, references                    |

<!-- Reference-style links -->

[adr-0001]: ../adr/ADR-0001-project-naming-and-versioning.md
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
