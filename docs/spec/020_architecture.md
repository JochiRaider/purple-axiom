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
  - 033_execution_adapters.md
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

### Scope

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
  - If the run lock cannot be acquired because it already exists, the orchestrator MUST fail the
    invocation deterministically and MUST NOT create or mutate `runs/<run_id>/` unless an explicit,
    per-invocation operator override is present (see "Port: `RunLock`").
  - v0.1 MUST NOT use time-based lock expiry/leases for liveness. The only stale-lock recovery
    mechanism is a manual break-glass override (default-off) (see "Port: `RunLock`").
- Materialize/pin operator inputs under `runs/<run_id>/inputs/` (at minimum `inputs/range.yaml` and
  `inputs/scenario.yaml`; when the plan execution model is enabled (v0.2+), also pin
  `inputs/plan_draft.yaml`) before running the first stage.
- Any verb that executes one or more stages MUST record stage outcomes in `manifest.json` per
  [ADR-0005: Stage outcomes and failure classification][adr-0005]. When health files are enabled
  (`operability.health.emit_health_files=true`), it MUST also record the same ordered outcomes in
  `logs/health.json`.
- Any verb that writes stage-produced contract-backed artifacts MUST follow the publish gate rules
  in this document (staging + validation + atomic publish).
  - Exception (v0.1): build-time ingestion/pinning of operator-supplied inputs under `inputs/` (for
    example `inputs/range.yaml` and `inputs/plan_draft.yaml`) is reception/pass-through and is
    performed outside `StagePublishSession`. These pinned inputs MUST still be schema-validated per
    the active contract registry before being written to their contracted paths.
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
    - Ingress YAML snapshotting (normative, v0.1):
      - For any input snapshot that is contract-backed with `validation_mode="yaml_document"` (for
        example `inputs/range.yaml` and `inputs/plan_draft.yaml` when present), the orchestrator
        MUST:
        - validate the operator-supplied YAML bytes via `pa.yaml_decode.v1` and JSON Schema
          validation before writing them to `runs/<run_id>/inputs/...` (see
          `026_contract_spine.md`),
        - compute `yaml_semantic_sha256_v1` for the bytes and record the digest string in the run
          manifest field defined for that input. For `inputs/plan_draft.yaml`, record it at
          `manifest.extensions.operator_interface.plan_draft_sha256` and record the snapshot path at
          `manifest.extensions.operator_interface.plan_draft_path`, and
        - write the original bytes into `runs/<run_id>/inputs/...` verbatim (opaque copy; no
          rewriting or normalization).
      - Canonical YAML byte emission is intentionally unspecified in v0.1; this is reception and
        pass-through only.
    - These inputs MUST be treated as read-only by all stages. Implementations MUST NOT mutate these
      snapshots after `build` completes.
  - MUST NOT execute scenario actions or collect telemetry.

- `simulate`

  - Stages executed: the canonical v0.1 pipeline stage order, filtered to the stages enabled for
    this run by `025_data_contracts.md`'s `stage_enablement_matrix_v1` (see
    [Stage execution order](#stage-execution-order) and
    [ADR-0004: Deployment architecture and inter-component communication][adr-0004]).
  - Intent: perform a complete run and produce a complete run bundle.
  - When environment configuration is enabled, the orchestrator MUST record an additive `runner`
    substage `runner.environment_config` before any action enters the `prepare` lifecycle phase.
  - When regression comparison is enabled, `simulate` MUST treat any pre-existing artifacts under
    `inputs/**` as read-only. See "Run bundle (coordination plane)" for baseline reference
    materialization semantics.

- `replay`

  - Default stages executed (when enabled): `normalization` → `validation` → `detection` → `scoring`
    → `reporting` (and optional `signing`).
  - Verb selection and config gates further restrict this subset:
    - Verbs select a deterministic subset of stages.
    - Per-run stage enablement is defined by `025_data_contracts.md`'s `stage_enablement_matrix_v1`.
    - Stages that are disabled for a run MUST be absent from the outcome surface (not recorded as
      `skipped`) per ADR-0005.
  - Preconditions: the candidate run bundle MUST already contain `ground_truth.jsonl` and either:
    - `raw_parquet/**` (full replay; `normalization` and `validation` are executed), OR
    - a normalized event store (normalized-input replay; v0.1+):
      - `normalized/ocsf_events/_schema.json` (contract-backed; Parquet schema snapshot), AND
      - `normalized/ocsf_events/**` (Parquet dataset directory; canonical normalized store), AND
      - `normalized/mapping_profile_snapshot.json`.
  - Normalized-input replay fast path (v0.1+; normative when used):
    - If a normalized event store exists and its normalization provenance matches the current
      version control for the run, the orchestrator MUST skip directly to `detection`.
    - Match criteria (normative):
      - `normalized/ocsf_events/_schema.json` MUST validate against the data contracts.
      - `normalized/mapping_profile_snapshot.json` MUST validate against the data contracts.
      - `normalized/mapping_profile_snapshot.json.ocsf_version` MUST equal
        `manifest.versions.ocsf_version`.
      - `normalized/mapping_profile_snapshot.json.mapping_profile_sha256` MUST equal the expected
        mapping profile hash for the run, computed using the hashing rules in
        `025_data_contracts.md` ("mapping_profile_snapshot.json").
    - Stage behavior (normative):
      - Stages executed: the enabled subset of `detection` → `scoring` → `reporting` (and optional
        `signing`), preserving canonical relative order.
      - The orchestrator MUST record `normalization` as `status="skipped"` with
        `fail_mode="warn_and_skip"` and `reason_code="normalized_store_reused"`.
      - If `validation` is enabled for this run, the orchestrator MUST record `validation` as
        `status="skipped"` with `fail_mode="warn_and_skip"` and
        `reason_code="normalized_store_reused"`.
      - If the match criteria fail and `raw_parquet/**` is absent:
        - The orchestrator MUST record `normalization` as `status="failed"` with
          `fail_mode="fail_closed"` and `reason_code="normalized_store_incompatible"`.
        - The orchestrator MUST record each subsequent enabled stage as `status="skipped"` with
          `fail_mode="warn_and_skip"` and `reason_code="blocked_by_upstream_failure"`.
  - Input immutability (normative): `replay` MUST treat `ground_truth.jsonl`, `raw_parquet/**` (when
    present), and `normalized/**` (when present) as read-only.
  - MUST NOT execute `runner` or `telemetry`, and MUST NOT create new artifacts under `runner/**` or
    `raw_parquet/**` except for operability logs under `logs/` (classified per ADR-0009).
  - When regression comparison is enabled, `replay` MUST treat any pre-existing artifacts under
    `inputs/**` as read-only and MUST NOT rewrite them. See "Run bundle (coordination plane)" for
    baseline reference materialization semantics.

- `export`

  - Stages executed: none.
  - Intent: package a run bundle (or disclosed subset) for sharing or archival.
  - By default, exports MUST exclude the configured quarantine directory resolved from
    `security.redaction.unredacted_dir` and MUST NOT disclose artifacts that are not redaction-safe
    under the configured policy.
  - `export` MUST treat `runs/<run_id>/` as read-only input and MUST NOT create, modify, or delete
    any run-bundle artifacts.
  - Export outputs MUST be written under the reserved run export namespace
    `<workspace_root>/exports/<run_id>/<export_id>/` and MUST include `export_manifest.json`. Output
    filenames within the export bundle are implementation-defined.

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

#### Telemetry configuration tiers (v0.1; normative)

Purple Axiom v0.1 supports three explicit tiers for how collector configuration is provisioned and
maintained. This tiering exists to keep telemetry capture deterministic, auditable, and safe by
default.

| Tier                         | Mechanism                                                                                   | v0.1 Status                 | Who / When                                                                             |
| ---------------------------- | ------------------------------------------------------------------------------------------- | --------------------------- | -------------------------------------------------------------------------------------- |
| **Pre-provisioned config**   | Configs baked before any run; collectors start pre-configured                               | REQUIRED baseline           | Operator/lab setup; outside run lifecycle                                              |
| **Environment config apply** | `runner.environment_config` in apply mode; may place/restart collectors as pre-run substage | PERMITTED, explicitly gated | Runner, before `runner` enters the `prepare` lifecycle phase; must be enabled + logged |
| **Control-plane RPC**        | Active remote management channel (SSH/WinRM/gRPC) used mid-run                              | FORBIDDEN                   | `control_plane.enabled` MUST be `false`                                                |

Tier semantics (normative):

- Tier-1 (pre-provisioned config) is the REQUIRED baseline for v0.1 runs.
- Tier-2 (environment config apply) is permitted only when `runner.environment_config.mode="apply"`,
  and MUST be recorded as the additive substage `runner.environment_config` with deterministic
  operability evidence under `runs/<run_id>/logs/`.
- Tier-3 (control-plane RPC) refers to a long-lived management channel used to mutate collector
  configuration or runtime behavior outside the runner action lifecycle. It does not forbid remote
  execution used by the `runner` stage to execute scenario actions.

### Run bundle (coordination plane)

The run bundle (`runs/<run_id>/`) is the authoritative coordination substrate:

- Stages MUST communicate by reading and writing **contract-backed artifacts** under the run bundle
  root.
- The manifest (`runs/<run_id>/manifest.json`) MUST remain the authoritative index of what exists
  and which versions/config hashes were used.
- When `runner.environment_config.mode != "off"`, the orchestrator MUST record the configuration
  boundary as additive substage `runner.environment_config` in the stage outcome surface
  (`manifest.json`, and `logs/health.json` when enabled) and MUST ensure structured operability
  evidence is emitted under `runs/<run_id>/logs/` (log classification is file-level per ADR-0009;
  schema and filenames are implementation-defined here; see the
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

- Stages (and the orchestrator when publishing orchestrator-owned artifacts) MUST write candidate
  outputs under `runs/<run_id>/.staging/<stage_id>/`, where `<stage_id>` is the active publish owner
  id (a `stage_owner` value from the contract registry; pipeline stage ids plus the reserved owner
  token `orchestrator`).
- Before publishing, the publisher MUST validate required contract-backed artifacts (presence +
  schema).
- Publishing MUST be an atomic rename/move from staging into final run-bundle paths.
- If validation fails, the publisher MUST NOT partially publish final-path artifacts.
- On contract validation failure, the publisher MUST emit a contract validation report at
  `runs/<run_id>/logs/contract_validation/<stage_id>.json` (use `<stage_id>="orchestrator"` for
  orchestrator-owned publish sessions).

## Run bundle layout

The run bundle is a deterministic on-disk folder rooted at:

- `<workspace_root>/runs/<run_id>/`

**This section is explicitly non-exhaustive.**

- The machine-authoritative inventory of **contract-backed** run-bundle artifacts (including
  ownership) is `contract_registry.json` (run-bundle) and, for workspace-root artifacts,
  `workspace_contract_registry.json`.
- Human-readable layout semantics and feature-gated requiredness are defined in
  `025_data_contracts.md`.

Selected stable paths (non-exhaustive; run-relative):

| Path                                     | Purpose                                                                                                                                                                    |
| ---------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `manifest.json`                          | Run index and stage outcomes surface (contract-backed).                                                                                                                    |
| `run_results.json`                       | Compact run summary for CI time-to-signal (contract-backed; orchestrator-owned).                                                                                           |
| `range/`                                 | The selected range, its sources, and any derived stable snapshots.                                                                                                         |
| `runner/`                                | Runner invocation and executable identity/provenance.                                                                                                                      |
| `raw/`                                   | Raw telemetry dumps (optional; redaction-sensitive).                                                                                                                       |
| `raw_parquet/`                           | Raw telemetry as Parquet parts (optional; for replay / debugging).                                                                                                         |
| `normalized/`                            | Normalized event store(s) and mapping artifacts.                                                                                                                           |
| `criteria/`                              | Validation criteria inputs, results, and provenance.                                                                                                                       |
| `detections/`                            | Detection outputs and evidence.                                                                                                                                            |
| `scoring/`                               | Scoring outputs and evidence.                                                                                                                                              |
| `report/`                                | Reporting products (e.g., `report/report.json`, `report/thresholds.json`).                                                                                                 |
| `inputs/`                                | Input snapshots and pointers materialized for determinism and replay.                                                                                                      |
| `inputs/plan_draft.yaml`                 | Finalized plan draft snapshot (contract-backed; orchestrator-owned).                                                                                                       |
| `inputs/environment_noise_profile.json`  | Optional environment noise profile snapshot (contract-backed; orchestrator-owned).                                                                                         |
| `inputs/telemetry_baseline_profile.json` | Optional telemetry baseline profile snapshot (contract-backed; orchestrator-owned).                                                                                        |
| `inputs/baseline_run_ref.json`           | Regression baseline pointer (contract-backed; reporting-owned; required when regression is enabled).                                                                       |
| `inputs/baseline/manifest.json`          | Optional baseline manifest snapshot (contract-backed; reporting-owned; immutable when present).                                                                            |
| `logs/`                                  | Operability surface: deterministic evidence + volatile diagnostics (see ADR-0009); deterministic evidence under `logs/` MUST be retained for the full run retention period |
| `logs/counters.json`                     | Tier-0 operability counters snapshot (contract-backed; orchestrator-owned).                                                                                                |
| `logs/telemetry_validation.json`         | Telemetry validation evidence (required when telemetry stage is enabled).                                                                                                  |
| `logs/contract_validation/`              | Per-owner contract validation reports on publish-gate failures.                                                                                                            |
| `logs/lab_inventory_snapshot.json`       | Deterministic lab environment inventory snapshot for auditability.                                                                                                         |
| `logs/cache_provenance.json`             | Run cache hit/miss and upstream provenance for replay fast paths.                                                                                                          |
| `logs/dedupe_index/**`                   | Volatile restart/deduplication index (diagnostic only).                                                                                                                    |
| `security/`                              | Redaction policies and security posture snapshots.                                                                                                                         |
| `plan/`                                  | Execution plan artifacts, including finalized plan and provenance.                                                                                                         |
| `control/`                               | Control-plane requests/decisions and audit trail (reserved; v0.2+ forward-compat).                                                                                         |

Per-action evidence location (normative):

- `build` MUST add `range/` source snapshots and update `manifest.json`.
- `simulate` MUST populate the output surfaces for each enabled stage and update `manifest.json`
  (e.g., `runner/` always; `raw_parquet/` when telemetry is enabled; `normalized/` always;
  `criteria/`, `detections/`, `scoring/`, and `report/` when their stages are enabled).
- `replay` MUST populate (or reuse) `normalized/` and MUST populate the output surfaces for each
  enabled downstream stage (`criteria/`, `detections/`, `scoring/`, `report/`), and update
  `manifest.json`.
- `simulate` and `replay` SHOULD publish `run_results.json` (contract-backed; orchestrator-owned)
  after `reporting` completes (and after `signing` when enabled), per the derivation rules in the
  [data contracts specification][data-contracts].
- `export` MUST write export bundles under the reserved run export namespace
  `<workspace_root>/exports/<run_id>/<export_id>/` (outside the run bundle) and MUST treat
  `runs/<run_id>/` as read-only input (it MUST NOT create, modify, or delete run-bundle artifacts).

See ADR-0004 for the full workspace and evidence-tier layout rules.

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
| `artifacts/`                   | Workspace-local artifacts (CI findings/fixtures, connector outputs) | reserved         |
| `exports/`                     | Derived exports and export manifests                                | reserved         |
| `cache/`                       | Cross-run caches and derived state (explicitly gated; optional use) | reserved         |
| `logs/`                        | Workspace-local logs/audit (v0.2+)                                  | reserved         |
| `plans/`                       | Operator-authored plan drafts and draft metadata (v0.2+)            | reserved         |

Notes:

- v0.1 tooling MUST NOT require `state/`, `artifacts/`, `logs/`, `plans/`, `exports/`, or `cache/` to exist unless the invoked feature explicitly uses that directory.
- For the authoritative default scope profile (including which v0.2 seams are inert by default), see
  the project charter: [Target contract surface and scope profile][charter-scope].
- `runs/` is the only directory whose contents are treated as authoritative pipeline outputs.
- `runs/.locks/` is reserved for lockfiles and is not a run directory; scanners MUST ignore it.
- `state/`, `artifacts/`, `exports/`, `cache/`, `logs/`, and `plans/` MUST NOT be treated as run artifact roots and MUST NOT be included in run-bundle export packaging unless a spec explicitly says so.

### Reserved exports namespaces

`exports/` is a reserved workspace-root child used for **workspace-global export products** (derived
artifacts that are not run bundles). Export products are organized into explicit **export
namespaces** under `exports/`. These namespaces are reserved even though they are already under the
reserved `exports/` root: workspace write-boundary enforcement MUST treat them as first-class,
explicitly allowlisted destinations (no "it's under exports so it's fine" ambiguity).

Reserved export namespaces (v0.1+; normative):

- **Run export products** (for example archives produced by the `export` verb):
  - `<workspace_root>/exports/<run_id>/<export_id>/`
- **Detection baseline packages (BDPs)** (see `086_detection_baseline_library.md`):
  - `<workspace_root>/exports/baselines/<baseline_id>/<baseline_version>/`
- **Dataset releases** (see `085_golden_datasets.md`):
  - `<workspace_root>/exports/datasets/<dataset_id>/<dataset_version>/`

Reserved export staging root (v0.1+; reserved):

- `<workspace_root>/exports/.staging/` is reserved scratch space for crash-safe export staging.
  - Export/packaging commands that publish export products under `exports/**` MUST stage outputs
    under `exports/.staging/**` and MUST publish by atomic rename into the final `exports/**`
    location (see `045_storage_formats.md`, "Workspace-global export staging directories").
  - Producers SHOULD namespace staging by export kind (for example:
    `<workspace_root>/exports/.staging/datasets/<dataset_id>/<dataset_version>/`).
  - Producers MUST NOT create per-product staging directories under the final export namespaces
    (for example `exports/datasets/.staging/**` or `exports/baselines/.staging/**`).
  - Staging directories MUST be treated as non-authoritative and safe to delete when no export is
    in progress.

Mechanical enforcement guidance (non-normative):

- Implementations SHOULD maintain an **export namespace allowlist** (for example: `baselines`,
  `datasets`, and run-export products) so write-boundary enforcement is mechanical and does not
  require one-off special cases.

### Workspace write boundary

Normative requirements:

- Stages MUST treat `runs/<run_id>/` as their only persistent output surface.

- Export/packaging commands that produce workspace-global artifacts under `exports/` MUST treat
  `runs/<run_id>/` as read-only input and MUST NOT create or modify artifacts under any run bundle
  directory.

- The orchestrator MAY write outside the run bundle only in reserved workspace locations:

  - `runs/.locks/<run_id>.lock` (required)
  - `<workspace_root>/cache/` (optional; only when cross-run caching is explicitly enabled)
  - `<workspace_root>/exports/` (optional; only for explicit export/packaging commands; writes MUST
    be confined to reserved export namespaces such as `exports/<run_id>/<export_id>/`,
    `exports/baselines/**`, `exports/datasets/**`, and `exports/.staging/**`)
  - `<workspace_root>/artifacts/` (optional; for CI and other workspace-local, contract-backed
    artifacts such as findings/fixtures and connector outputs; see
    `docs/contracts/workspace_contract_registry.json`)
  - `<workspace_root>/state/` and `<workspace_root>/logs/` (reserved control-plane roots; v0.1
    MAY write the contract-backed control-plane artifacts defined by the workspace registry,
    including `state/run_registry.json`, `logs/ui_audit.jsonl`, and `logs/contract_validation/**`.
    Other subpaths remain reserved and SHOULD be left untouched when unused.)

- Tooling MUST NOT create or modify other workspace-root siblings as a side effect of a run.

- Tooling MUST NOT write durable artifacts outside `<workspace_root>/` (for example `~/.cache`,
  `~/.config`, `/var/tmp`) for correctness or resumability.

Scope note: Which reserved workspace seams are written to and/or required is defined by the selected
scope profile. See the project charter: [Target contract surface and scope profile][charter-scope].

### Run discovery surfaces

- A run MUST be considered present if and only if `runs/<run_id>/manifest.json` exists and validates
  against the manifest contract.

- If initialization fails before a valid `manifest.json` can be published, the run MUST be treated
  as not present by this rule. If the failure is due to contract validation of orchestrator-owned
  artifacts, the orchestrator MUST still emit
  `runs/<run_id>/logs/contract_validation/orchestrator.json` as the deterministic forensic surface.

- Implementations MAY maintain a derived workspace run registry at
  `<workspace_root>/state/run_registry.json` for fast discovery when enabled by the selected scope
  profile (see [charter-scope]); if implemented, it MUST be rebuildable by a deterministic scan of
  `runs/<run_id>/manifest.json` surfaces:

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

Note: The identifiers in the table below are **pipeline stage ids**. Contract ownership uses
`stage_owner` ids from the contract registry, which include all pipeline stage ids plus the reserved
owner token `orchestrator`. A stage being marked "Optional" here refers to a capability (e.g.
`signing`) rather than config gating. If a pipeline stage is disabled for a run by configuration, it
MUST be absent from the outcome surface (not recorded as `skipped`) per ADR-0005.

## Architecture viewpoints

Purple Axiom documentation is organized using explicit architecture viewpoints (context, logical and
data, process and state, deployment, operational). This section provides:

1. A viewpoint index mapping each major concern to the single authoritative document.
1. The authoritative system context and trust boundary view for v0.1.

### Viewpoint index

Context

- Authority: this section for actors, trust boundaries, and allowed/denied flows.
- Enforcement detail: `090_security_safety.md` and `110_operability.md`.

Logical and data

- `025_data_contracts.md` (artifact schemas and contract bindings)
- `045_storage_formats.md` (JSONL/Parquet formats and schema snapshots)
- `050_normalization_ocsf.md` and `055_ocsf_field_tiers.md` (OCSF mapping rules and tiering)
- `065_sigma_to_ocsf_bridge.md` and `060_detection_sigma.md` (Sigma compilation, bridge IR,
  evaluator IO)

Process and state

- ADR-0004 (deterministic stage ordering and inter-component communication)
- ADR-0005 (stage outcome semantics and reason codes)
- ADR-0007 (lifecycle state machine templates and conformance)

Deployment

- `015_lab_providers.md` (provider boundary and asset topology)
- `040_telemetry_pipeline.md` (collector deployment, ingest/export, telemetry validation
  checkpoints)

Operational

- `110_operability.md` (health, canaries, counters, failure handling)
- `100_test_strategy_ci.md` (fixture-driven conformance and CI gates)
- `120_config_reference.md` (config keys for network, secrets, signing, and safety defaults)

### System context and trust boundaries

This section is authoritative for the system context and trust boundary model. It MUST remain
consistent with the enforcement requirements in `090_security_safety.md` and the canary and health
requirements in `110_operability.md`.

#### External actors and systems

- Operator: invokes the pipeline via CLI or future UI.
- CI runner: invokes the pipeline in automated workflows.
- Secret provider: supplies credential material referenced by config (environment, CI secrets,
  vault).
- Pack sources and registries: sources of scenarios, criteria packs, mapping packs, and rule packs.
- Lab provider: provisions lab assets and enforces lab network policy.
- Lab assets: Windows/Linux endpoints under test.
- Telemetry collector: privileged local service on each asset that exports telemetry to the
  orchestrator.

#### Trust boundaries

Each trust boundary is named so other specs and tests can refer to it unambiguously.

- TB-ORCH: Orchestrator host boundary.

  - Includes the orchestrator process, adapter implementations, and the run workspace.
  - Assumption: local host executes the pipeline, but all external inputs are untrusted by default.

- TB-EVAL: Evaluator sandbox boundary.

  - A constrained execution boundary used for criteria and detection evaluation.
  - Assumption: evaluator inputs (rules, packs, event data) are untrusted; sandbox must enforce
    least privilege.

- TB-LAB: Lab boundary.

  - Includes the lab provider control plane, lab networks, and target assets.
  - Assumption: lab assets may be adversarial or compromised during execution; containment is
    required.

- TB-COL: Collector boundary.

  - The telemetry collector service on a lab asset that ingests local signals and exports them
    off-host.
  - Assumption: collector is privileged on the asset; it must be constrained and its export must be
    authenticated.

- TB-SUPPLY: Supply chain boundary.

  - Any external content source (git, registries, downloaded packs, pinned baseline datasets).
  - Assumption: content is untrusted until pinned, hashed, and when enabled, signature-verified.

- TB-SECRETS: Secret material boundary.

  - Credential values resolved from secret providers.
  - Assumption: secrets must not cross into logs, artifacts, or evaluator execution contexts.

#### Context and trust boundary diagram

```text
+--------------------------+         +--------------------------------------+
| External actors          |         | TB-SUPPLY: Pack sources/registries   |
|                          |         | (untrusted until pinned/verified)    |
|  - Operator              |         |  - scenarios, packs, rules, BDPs     |
|  - CI runner             |         +-------------------+------------------+
+------------+-------------+                             |
             | invoke (local CLI)                        | explicit fetch/resolve
             v                                           | (pinned + hashed)
+----------------------------------------------------------------------------------+
| TB-ORCH: Orchestrator host                                                        |
|                                                                                   |
|  Orchestrator (one-shot pipeline driver + adapter registry)                       |
|    |                                                                              |
|    | writes                                                                       |
|    v                                                                              |
|  runs/<run_id>/... (contract-backed artifacts + deterministic logs)               |
|                                                                                   |
|  +----------------------------------+                                             |
|  | TB-EVAL: Evaluator sandbox       |                                             |
|  |  - criteria evaluation           |  Deny by default: outbound network          |
|  |  - sigma evaluation              |  Constrain FS: read-only inputs, write-only |
|  +----------------------------------+  outputs under runs/<run_id>/               |
|                                                                                   |
|  Allowed outbound calls from TB-ORCH are limited to:                              |
|   - Lab provider API (TB-LAB)                                                     |
|   - Explicit, pinned content fetch (TB-SUPPLY)                                    |
+----------------------------+-----------------------------------------------------+
                             |
                             | provision / remote execution / containment policy
                             v
+----------------------------------------------------------------------------------+
| TB-LAB: Lab provider + assets                                                     |
|                                                                                   |
|  Lab provider control plane (inventory, provision, enforce lab network policy)    |
|                                                                                   |
|  +-----------------------------+                                                  |
|  | Target asset(s)             |                                                  |
|  |   +----------------------+  |    Telemetry export (mTLS)                       |
|  |   | TB-COL: OTel         |--+----------------------------------------------->  |
|  |   | Collector            |        Ingest receiver on TB-ORCH                   |
|  |   +----------------------+                                                     |
|  |   Default: outbound egress denied (provider-enforced)                          |
|  +-----------------------------+                                                  |
+----------------------------------------------------------------------------------+
```

#### Allowed and denied flows

The following flows are normative for v0.1.

Allowed

- Operator/CI MAY invoke the orchestrator locally and provide config/scenario inputs.
- TB-ORCH MAY call the lab provider control plane to provision assets and execute scenarios.
- TB-COL MAY export telemetry off-host to TB-ORCH using authenticated transport (mTLS).
- TB-ORCH MAY retrieve content from TB-SUPPLY only via an explicit fetch/resolve step that:
  - pins versions and/or hashes, and
  - records provenance in the run bundle.

Denied by default

- TB-EVAL MUST NOT have outbound network access by default.
- Lab asset outbound egress MUST be denied by default; allowlisting MUST be explicit and recorded.
- Secrets from TB-SECRETS MUST NOT be persisted to logs or artifacts and MUST NOT be accessible to
  TB-EVAL unless explicitly passed as data inputs.

#### Failure domains and blast radius

- Orchestrator crash or kill:

  - Effect: run may be incomplete; outputs may be partially written.
  - Containment: publish gate semantics and run lock must prevent partially published artifacts.

- Collector crash or misconfiguration:

  - Effect: telemetry missing/incomplete; telemetry validation gates fail.
  - Containment: telemetry stage must fail closed when required signals/canaries are absent.

- Lab egress policy misconfiguration:

  - Effect: unintended outbound reachability from assets.
  - Containment: network egress canary must detect and fail the run when effective policy is deny.

- Pack corruption or tampering:

  - Effect: inputs or exported bundles may be modified.
  - Containment: checksums/signatures must fail closed when tampering is detected.

#### Boundary enforcement test map

Every trust boundary listed above MUST have at least one enforcement test referenced here. The test
strategy doc is the authoritative index for fixture roots and CI gates.

- TB-ORCH:

  - `run_lock_exclusive_single_writer`
  - `run_lock_break_glass_requires_explicit_force`
  - `publish_gate_output_root_guardrail_fail_closed`

- TB-SECRETS:

  - `tests/fixtures/integration_credentials/v1/` (`leak_detected_fails_closed`)

- TB-LAB egress:

  - `telemetry.network.egress_policy` canary
  - `egress_policy_canary_smoke` (telemetry fixture set)

- TB-COL:

  - `synthetic_marker_smoke` (telemetry fixture set)

- TB-EVAL:

  - `evaluator_sandbox_network_egress_denied_by_default`
  - `evaluator_sandbox_filesystem_write_outside_run_bundle_denied`

- TB-SUPPLY:

  - `tests/fixtures/signing/v1/` (`tamper_detected`)

## Stage execution order

Preamble (normative, per
[ADR-0004: Deployment architecture and inter-component communication][adr-0004]):

- The orchestrator MUST acquire the run lock (atomic create of `runs/.locks/<run_id>.lock`) before
  creating or mutating any run bundle artifacts (including the initial `manifest.json` skeleton and
  all stage outputs).
- The orchestrator MUST create `runs/<run_id>/` and write an initial `manifest.json` skeleton before
  running the first stage.
- The orchestrator MUST treat `manifest.json` as the authoritative run index throughout the run.

The orchestrator MUST execute the enabled pipeline stages in the canonical relative order below for
v0.1. "Enabled" is determined by the verb semantics and then further filtered by
`025_data_contracts.md`'s `stage_enablement_matrix_v1`.

Canonical relative order (v0.1):

1. `lab_provider`
1. `runner`
1. `telemetry`
1. `normalization`
1. `validation`
1. `detection`
1. `scoring`
1. `reporting`
1. `signing` (capability-optional; when enabled, MUST be last)

Rules:

- Verbs (for example `replay`) select a deterministic subset of stages; config gates further
  restrict that subset.
- Stages that are disabled for a run MUST be absent from the outcome surface (not recorded as
  `skipped`) per ADR-0005.
- Stages that are enabled but deliberately short-circuited (for example `normalized_store_reused`)
  MUST be recorded as `status="skipped"` with a stage-scoped `reason_code` per ADR-0005.

Note: Telemetry collection MAY run concurrently with `runner` (collectors are typically started
before `runner` begins and stopped after it completes). The `telemetry` stage boundary refers to the
post-run harvest/validation/publish step that materializes `raw_parquet/**` for downstream stages.

When `runner.environment_config.mode != "off"`, the orchestrator MUST record an additive `runner`
substage `runner.environment_config` after `lab_provider` completes and before any action enters the
runner `prepare` lifecycle phase. This substage MUST be observable via stage outcomes in
`manifest.json` and, when `operability.health.emit_health_files=true`, via `logs/health.json`.

## Lifecycle state machine integrations (v0.1; normative)

This architecture relies on lifecycle semantics that are naturally stateful (run execution,
per-stage publication, and per-action execution). Where these semantics are conformance-critical,
they are defined as explicit finite-state machines (FSMs) using the required template from
[ADR-0007: State machines for lifecycle semantics][adr-0007].

This document defines the two cross-cutting insertion points called out by ADR-0007 as needing
contract-grade lifecycle modeling:

1. **Orchestrator run lifecycle** (scope: run)
1. **Stage execution lifecycle** (scope: stage)

Other lifecycle machines (for example runner action lifecycle and telemetry checkpointing/replay)
are defined in their owning specifications and are referenced here only for context.

### State machine: Orchestrator run lifecycle

#### Purpose

- **What it represents**: The orchestrator-owned lifecycle for producing or resuming a single run
  bundle identified by `run_id`. It constrains: (1) single-writer lock acquisition, (2) run bundle
  initialization, (3) deterministic reconciliation of prior partial artifacts, (4) canonical stage
  execution order, and (5) finalization to a terminal `manifest.status`.
- **Scope**: run
- **Machine ID**: `orchestrator-run-lifecycle` (see ADR-0001 `id_slug_v1`)
- **Version**: `0.1.0`

#### Lifecycle authority references

This state machine overlays and reuses lifecycle semantics defined elsewhere:

- [ADR-0004: Deployment architecture and inter-component communication][adr-0004] (run lock
  acquisition, reconciliation pass, stage completion semantics)
- [ADR-0005: Stage outcomes and failure classification][adr-0005] (stage outcome requirements and
  run-status derivation)
- `025_data_contracts.md` (stage enablement, required outputs matrix, cross-artifact invariants)
- This document:
  - "Stage execution order" (canonical pipeline ordering)
  - "Port: `RunLock`" and "Port: `PublishGate`" (single-writer + publication mechanics)

If this state machine definition conflicts with the linked lifecycle authority, the linked lifecycle
authority is authoritative unless this document explicitly states it is overriding those semantics.

#### Entities and identifiers

- **Machine instance key**: `run_id`
- **Correlation identifiers**:
  - Run lock path: `runs/.locks/<run_id>.lock`
  - Run bundle root: `runs/<run_id>/`
  - Manifest path: `runs/<run_id>/manifest.json`
  - Health path (optional): `runs/<run_id>/logs/health.json`

#### Authoritative state representation

- **Source of truth**:
  - The run manifest (`runs/<run_id>/manifest.json`) for in-bundle state derivation, and
  - the run lock path (`runs/.locks/<run_id>.lock`) for acquisition/refusal observability.
- **Derivation rule** (deterministic):
  - If `runs/<run_id>/manifest.json` exists and is valid per the `manifest` contract:
    - if `manifest.status == "success"`, state is `completed_success`
    - else if `manifest.status == "partial"`, state is `completed_partial`
    - else if `manifest.status == "failed"`, state is `completed_failed`
    - else (status absent), state is `in_progress`
  - Else if `runs/.locks/<run_id>.lock` exists, state is `locked_no_manifest`
  - Else state is `not_started`
  - `lock_denied` is an invocation-terminal state that is derived from the attempted lock
    acquisition result (`RunLock.acquire(run_id) == false`) and is not persisted in the run bundle.
- **Persistence requirement**:
  - MUST persist: yes (terminal state)
  - MUST be persisted in: `runs/<run_id>/manifest.json` as `manifest.status` (per
    `025_data_contracts.md`), with atomic replace semantics.

#### Events / triggers

- `event.acquire_run_lock`: Attempt to acquire the run lock using `RunLock.acquire(run_id)`.
- `event.force_acquire_run_lock`: Attempt to acquire the run lock with break-glass enabled
  (`--force-run-lock=true`).
- `event.initialize_run_bundle`: Ensure `runs/<run_id>/` exists and a contract-valid initial
  `manifest.json` skeleton has been written.
- `event.reconcile_run_bundle`: Perform the deterministic reconciliation pass defined in ADR-0004.
- `event.execute_enabled_stages`: Execute enabled pipeline stages in canonical order, driving the
  per-stage machine defined below for each enabled stage.
- `event.finalize_run`: Compute and persist the terminal `manifest.status`, enforce post-run
  invariants (including publish-scratch hygiene), and release the run lock (best-effort).

Event requirements (normative):

- Events MUST be named with ASCII `lower_snake_case` after the `event.` prefix.
- When `event.execute_enabled_stages` drives multiple per-stage executions, stage order MUST be the
  canonical relative order defined in "Stage execution order" and filtered by the stage enablement
  matrix in `025_data_contracts.md`.

#### States

Closed set (v0.1):

State requirements (normative):

- States MUST be named as ASCII `lower_snake_case`.
- States MUST be stable within the declared version.
- Terminal states MUST be explicitly identified.

| State                | Kind           | Description                                                                    | Invariants (normative)                                                                                        | Observable signals                                 |
| -------------------- | -------------- | ------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------- | -------------------------------------------------- |
| `not_started`        | `initial`      | No active or completed run bundle is present for this `run_id`.                | `runs/<run_id>/manifest.json` absent. `runs/.locks/<run_id>.lock` absent.                                     | Run bundle absent.                                 |
| `lock_denied`        | `terminal`     | Invocation could not acquire the run lock and therefore performed no work.     | `RunLock.acquire(run_id)==false` and `--force-run-lock==false`. `runs/<run_id>/` MUST NOT be created/mutated. | Run bundle absent; lockfile present.               |
| `locked_no_manifest` | `intermediate` | Run lock exists but the run manifest is absent (pre-init or crashed pre-init). | `runs/.locks/<run_id>.lock` present. `runs/<run_id>/manifest.json` absent.                                    | Lockfile present; run bundle absent or incomplete. |
| `in_progress`        | `intermediate` | A run bundle exists and is being produced or resumed; terminal status absent.  | `runs/<run_id>/manifest.json` present and contract-valid. `manifest.status` absent.                           | Manifest present; `manifest.status` absent.        |
| `completed_success`  | `terminal`     | Run bundle is complete with `manifest.status="success"`.                       | `manifest.status=="success"`. Lock SHOULD be released (lockfile absent unless crash).                         | `manifest.status="success"`.                       |
| `completed_partial`  | `terminal`     | Run bundle is complete with `manifest.status="partial"`.                       | `manifest.status=="partial"`. Lock SHOULD be released (lockfile absent unless crash).                         | `manifest.status="partial"`.                       |
| `completed_failed`   | `terminal`     | Run bundle is complete with `manifest.status="failed"`.                        | `manifest.status=="failed"`. Lock SHOULD be released (lockfile absent unless crash).                          | `manifest.status="failed"`.                        |

#### Transition rules

Guards MUST be explicit and deterministic.

| From state           | Event                          | Guard (deterministic)                                                        | To state                                                       | Actions (entry/exit)                                                                                                                                                                                                                                                                                     | Outcome mapping                                                                                       | Observable transition evidence                                                                              |
| -------------------- | ------------------------------ | ---------------------------------------------------------------------------- | -------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| `not_started`        | `event.acquire_run_lock`       | `RunLock.acquire(run_id)==true`                                              | `locked_no_manifest`                                           | Atomically create `runs/.locks/<run_id>.lock` (or equivalent exclusive mechanism).                                                                                                                                                                                                                       | None.                                                                                                 | Lockfile exists at primary path.                                                                            |
| `not_started`        | `event.acquire_run_lock`       | `RunLock.acquire(run_id)==false` AND `--force-run-lock==false`               | `lock_denied`                                                  | MUST exit fail-closed. MUST NOT create or mutate `runs/<run_id>/`.                                                                                                                                                                                                                                       | Invocation failure classified as `lock_acquisition_failed` for CLI/exit-code purposes (see ADR-0005). | Run bundle absent; deterministic error output; non-zero exit code.                                          |
| `not_started`        | `event.force_acquire_run_lock` | `--force-run-lock==true` AND break-glass rename + retry acquisition succeeds | `locked_no_manifest`                                           | Apply break-glass procedure from "Port: `RunLock`" (rename to `.stale.<nnnn>`, retry acquire). Defer recording `break_glass_events[]` until `event.initialize_run_bundle` when a manifest exists.                                                                                                        | None.                                                                                                 | `.stale.<nnnn>` lockfile preserved; primary lockfile exists.                                                |
| `not_started`        | `event.force_acquire_run_lock` | `--force-run-lock==true` AND break-glass rename + retry acquisition fails    | `lock_denied`                                                  | MUST exit fail-closed. MUST NOT create or mutate `runs/<run_id>/`.                                                                                                                                                                                                                                       | Invocation failure classified as `lock_acquisition_failed` for CLI/exit-code purposes (see ADR-0005). | Run bundle absent; deterministic error output; non-zero exit code.                                          |
| `locked_no_manifest` | `event.initialize_run_bundle`  | Manifest is absent OR (manifest exists and is contract-valid)                | `in_progress`                                                  | Create `runs/<run_id>/` (if absent). Write or validate an initial contract-valid `manifest.json` skeleton (atomic replace). If break-glass was used, append `extensions.orchestrator.run_lock.break_glass_events[]` entry (atomic replace).                                                              | None.                                                                                                 | Manifest exists and validates; break-glass extension (if applicable).                                       |
| `in_progress`        | `event.reconcile_run_bundle`   | Run lock is held by the current invocation                                   | `in_progress`                                                  | Perform deterministic reconciliation per ADR-0004 (including inconsistent stage artifact handling). MUST NOT execute any stage before this completes.                                                                                                                                                    | May append derived stage outcomes and/or mark downstream stages skipped per ADR-0004/ADR-0005.        | Deterministic stage outcome deltas; contract validation reports (when emitted).                             |
| `in_progress`        | `event.execute_enabled_stages` | Run lock is held by the current invocation                                   | `in_progress`                                                  | Execute enabled stages in canonical order. For each enabled stage without a terminal outcome, drive the stage execution lifecycle machine to a terminal state and record the resulting stage outcome in the manifest (atomic replace).                                                                   | Stage outcomes appended in deterministic order (ADR-0005 / `025_data_contracts.md`).                  | `manifest.stage_outcomes[]` grows deterministically; published stage outputs appear under contracted paths. |
| `in_progress`        | `event.finalize_run`           | All enabled stages have terminal outcomes recorded                           | `completed_success` / `completed_partial` / `completed_failed` | Compute `manifest.status` deterministically from stage outcomes (`025_data_contracts.md`). Enforce publish-scratch hygiene (`runs/<run_id>/.staging/` MUST be absent or empty). Persist `manifest.status` (atomic replace). Emit `logs/health.json.status` when enabled. Release run lock (best-effort). | Run status MUST equal derived `manifest.status`.                                                      | `manifest.status` set; lock released; `.staging/` absent/empty.                                             |
| `completed_success`  | `event.finalize_run`           | `manifest.status=="success"`                                                 | `completed_success`                                            | Idempotent no-op (MUST NOT rewrite state-defining fields). MAY attempt best-effort lock release.                                                                                                                                                                                                         | None.                                                                                                 | No artifact diffs in state-defining fields.                                                                 |
| `completed_partial`  | `event.finalize_run`           | `manifest.status=="partial"`                                                 | `completed_partial`                                            | Idempotent no-op (MUST NOT rewrite state-defining fields). MAY attempt best-effort lock release.                                                                                                                                                                                                         | None.                                                                                                 | No artifact diffs in state-defining fields.                                                                 |
| `completed_failed`   | `event.finalize_run`           | `manifest.status=="failed"`                                                  | `completed_failed`                                             | Idempotent no-op (MUST NOT rewrite state-defining fields). MAY attempt best-effort lock release.                                                                                                                                                                                                         | None.                                                                                                 | No artifact diffs in state-defining fields.                                                                 |

#### Entry actions and exit actions

- **Entry actions**:

  - `locked_no_manifest`:
    - MUST NOT create or mutate `runs/<run_id>/` until the lock is acquired.
  - `in_progress`:
    - MUST run `event.reconcile_run_bundle` before executing any stage.
  - `completed_*`:
    - MUST release the run lock (best-effort) and MUST leave `.staging/` absent or empty.

- **Exit actions**:

  - `in_progress`:
    - When exiting to a terminal state, MUST persist `manifest.status` using atomic replace.

Requirements (normative):

- Artifact writes that define or advance state MUST be atomic or fail closed.
- Entry/exit actions MUST be idempotent with respect to the authoritative state representation.

#### Illegal transitions

- **Policy**: `fail_closed`
- **Classification**:
  - If the illegal transition is detected before `manifest.json` exists, the orchestrator MUST abort
    the invocation with a deterministic error and MUST NOT create or mutate `runs/<run_id>/`.
  - If the illegal transition is detected after `manifest.json` exists, the orchestrator MUST abort
    further stage execution, MUST NOT publish additional stage outputs, and SHOULD proceed to
    `event.finalize_run` if it can do so without violating atomicity/invariant requirements.
- **Observable evidence**: deterministic non-zero exit code and a deterministic error message. When
  `logs/health.json` is enabled and writable, implementations SHOULD additionally surface an
  operator-visible health error.

Requirements (normative):

- Illegal transitions MUST NOT silently mutate state.
- Illegal transitions MUST be observable.

#### Inconsistent artifact state handling

The orchestrator MUST handle the following inconsistent artifact cases deterministically during
`event.reconcile_run_bundle` (authority: ADR-0004):

- **Published outputs present but stage outcome missing**:
  - MUST rerun contract validation for the published artifacts.
  - If validation passes, MUST record the missing stage outcome as `status="success"`.
  - If validation fails, MUST treat the stage as `status="failed", fail_mode="fail_closed"` and MUST
    mark downstream enabled stages `status="skipped"` with an ADR-0005 stage-scoped reason code.
- **Stage outcome recorded but publication invariants violated** (for example output present where
  outputs must be absent, or required outputs missing where outputs must be present):
  - MUST fail closed and MUST NOT continue stage execution. Prefer `reason_code="storage_io_error"`
    when the inconsistency reflects filesystem corruption/partial publish, and prefer
    `reason_code="input_missing"` when it reflects missing required inputs.
- **Non-empty publish scratch after terminalization** (`runs/<run_id>/.staging/` non-empty when the
  run is being finalized):
  - MUST fail closed with `reason_code="storage_io_error"` (see `025_data_contracts.md` invariants).

#### Observability

- **Required artifacts**:
  - `runs/<run_id>/manifest.json` (including `stage_outcomes[]` and terminal `manifest.status`)
  - `runs/.locks/<run_id>.lock` and any preserved `runs/.locks/<run_id>.lock.stale.<nnnn>`
  - `runs/<run_id>/logs/health.json` when `operability.health.emit_health_files=true`
- **Human-readable logs**:
  - Orchestrator log output MUST include deterministic error strings for lock denial and other
    illegal transitions.
- **Counters/metrics** (optional):
  - Implementations MAY emit counters for reconciliation repairs and illegal transitions, but these
    MUST NOT be the sole conformance-critical signal.

Requirements (normative):

- Observability signals MUST be deterministic for equivalent inputs.
- If this state machine affects CI gating, it MUST map to deterministic artifacts consumed by
  reporting and/or CI (manifest and, when enabled, health).

#### Conformance tests

Minimum conformance suite (normative):

1. **Happy path**: acquire lock → initialize bundle → reconcile → execute enabled stages → finalize
   to `completed_success`.
1. **Each terminal failure mode**:
   - `lock_denied` (existing lock; no force)
   - `completed_failed` (at least one stage fails `fail_closed`)
   - `completed_partial` (at least one stage fails `warn_and_skip`)
1. **Illegal transition handling**: attempt `event.execute_enabled_stages` without owning the lock
   and verify fail-closed behavior and observability.
1. **Idempotency**: run `event.reconcile_run_bundle` twice on the same fixture and verify identical
   stage outcomes and no duplicated side effects.
1. **Determinism**: run the same fixture twice and assert identical state-related artifact content
   (`manifest.json`, and `logs/health.json` when enabled), excluding fields explicitly permitted to
   vary by their own contracts.

Tests MUST be automatable in CI and SHOULD reuse or extend the run-lock fixture suite described in
`100_test_strategy_ci.md`.

### State machine: Stage execution lifecycle

#### Purpose

- **What it represents**: The per-stage lifecycle for producing a top-level pipeline stage outcome
  (`lab_provider`, `runner`, `telemetry`, `normalization`, `validation`, `detection`, `scoring`,
  `reporting`, `signing`) within a run bundle. It constrains how a stage moves from "enabled and not
  yet executed" to a terminal stage outcome while enforcing publish-gate invariants (staged →
  validated → atomically promoted or absent).
- **Scope**: stage
- **Machine ID**: `stage-execution-lifecycle` (see ADR-0001 `id_slug_v1`)
- **Version**: `0.1.0`

#### Lifecycle authority references

This state machine overlays and reuses lifecycle semantics defined elsewhere:

- [ADR-0004] (stage completion semantics; reconciliation rules)
- [ADR-0005] (stage outcome schema; failure classification; run-status derivation)
- `025_data_contracts.md` (stage enablement and required contract outputs)
- This document:
  - "Port: `PublishGate`" (stage publication rules and invariants)
  - "Stage IO boundaries" (allowed output roots by stage owner)

If this state machine definition conflicts with the linked lifecycle authority, the linked lifecycle
authority is authoritative unless this document explicitly states it is overriding those semantics.

#### Entities and identifiers

- **Machine instance key**: `(run_id, stage_id)`
- **Correlation identifiers**:
  - Stage outcome record: `runs/<run_id>/manifest.json.stage_outcomes[]` entry where
    `stage==stage_id`
  - Stage publish scratch: `runs/<run_id>/.staging/<stage_id>/`
  - Stage contracted outputs: artifact paths bound to `stage_owner==stage_id` in
    `contract_registry.json`

#### Authoritative state representation

- **Source of truth**:
  - Stage outcome record in `runs/<run_id>/manifest.json` (authoritative for terminal states), and
  - presence/absence of the stage publish scratch directory for the `running` intermediate state.
- **Derivation rule** (deterministic):
  - If a stage outcome entry exists for `stage_id`:
    - if `status=="success"`, state is `succeeded`
    - else if `status=="failed"` and `fail_mode=="fail_closed"`, state is `failed_fail_closed`
    - else if `status=="failed"` and `fail_mode=="warn_and_skip"`, state is `failed_warn_and_skip`
    - else if `status=="skipped"`, state is `skipped`
  - Else if `runs/<run_id>/.staging/<stage_id>/` exists, state is `running`
  - Else state is `pending`
- **Persistence requirement**:
  - MUST persist: yes (terminal state)
  - MUST be persisted in: `runs/<run_id>/manifest.json.stage_outcomes[]` (atomic replace), with
    `manifest.status` derived only when the run finalizes.

#### Events / triggers

- `event.stage_begin`: The orchestrator begins executing `stage_id` and opens a publish session via
  `PublishGate.begin_stage(stage_id)`.
- `event.stage_complete_success`: The stage completes and publishes outputs successfully
  (`StagePublishSession.finalize(...)` succeeds) and the orchestrator records `status="success"`.
- `event.stage_complete_failed_fail_closed`: The stage completes in a fail-closed failure mode and
  the orchestrator records `status="failed", fail_mode="fail_closed"` after aborting publication.
- `event.stage_complete_failed_warn_and_skip`: The stage completes in warn-and-skip mode and the
  orchestrator records `status="failed", fail_mode="warn_and_skip"` after successful publication.
- `event.stage_complete_skipped`: The orchestrator intentionally short-circuits the stage (enabled
  but not executed) and records `status="skipped"` with a stage-scoped `reason_code`.
- `event.reconcile_outputs_without_outcome`: Reconciliation detects published outputs for `stage_id`
  but no stage outcome record exists.

Event requirements (normative):

- Events MUST be named with ASCII `lower_snake_case` after the `event.` prefix.
- When multiple stage machines are driven within a run, the orchestrator MUST process stages in the
  canonical order defined in "Stage execution order". Within a stage, if multiple substage outcomes
  are emitted, ordering MUST follow ADR-0005 / `025_data_contracts.md`.

#### States

Closed set (v0.1):

| State                  | Kind           | Description                                               | Invariants (normative)                                                                                                               | Observable signals                      |
| ---------------------- | -------------- | --------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------- |
| `pending`              | `initial`      | Stage is enabled for the run but has no outcome.          | No top-level stage outcome record for `stage_id`. No published outputs for `stage_id` are required to exist.                         | Stage outcome absent.                   |
| `running`              | `intermediate` | Stage is executing and has an active publish session.     | `runs/<run_id>/.staging/<stage_id>/` exists. No top-level stage outcome record for `stage_id`.                                       | Staging directory exists.               |
| `succeeded`            | `terminal`     | Stage completed successfully and published outputs.       | Stage outcome `status="success"`. Staging directory absent. Outputs MUST be published under allowed roots.                           | Stage outcome present; outputs present. |
| `failed_fail_closed`   | `terminal`     | Stage failed in fail-closed mode; outputs must be absent. | Stage outcome `status="failed", fail_mode="fail_closed"`. Staging directory absent. Published outputs for `stage_id` MUST be absent. | Stage outcome present; outputs absent.  |
| `failed_warn_and_skip` | `terminal`     | Stage failed but published outputs (warn-and-skip).       | Stage outcome `status="failed", fail_mode="warn_and_skip"`. Staging directory absent. Outputs MUST be published under allowed roots. | Stage outcome present; outputs present. |
| `skipped`              | `terminal`     | Stage was enabled but intentionally not executed.         | Stage outcome `status="skipped"`. Staging directory absent. Published outputs for `stage_id` MUST be absent.                         | Stage outcome present; outputs absent.  |

#### Transition rules

| From state | Event                                       | Guard (deterministic)                                                                                    | To state               | Actions (entry/exit)                                                                                                                                                                                                                                                                  | Outcome mapping                                                                                                                         | Observable transition evidence                                    |
| ---------- | ------------------------------------------- | -------------------------------------------------------------------------------------------------------- | ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| `pending`  | `event.stage_begin`                         | Stage is enabled AND no terminal stage outcome record exists for `stage_id`                              | `running`              | Open `PublishGate.begin_stage(stage_id)`; stage writes only under `runs/<run_id>/.staging/<stage_id>/`.                                                                                                                                                                               | None.                                                                                                                                   | Staging directory exists.                                         |
| `pending`  | `event.stage_complete_skipped`              | Stage is enabled AND stage not executed (short-circuited)                                                | `skipped`              | Record stage outcome `status="skipped"` with a stage-scoped `reason_code` per ADR-0005. MUST NOT publish outputs. MUST ensure staging directory absent.                                                                                                                               | Append stage outcome record in manifest (and health when enabled).                                                                      | Stage outcome present; outputs absent.                            |
| `running`  | `event.stage_complete_success`              | `StagePublishSession.finalize(...)` succeeds AND required outputs are present per expected outputs rules | `succeeded`            | Finalize publication (validate, then atomically promote). Record stage outcome `status="success"` (atomic replace of manifest). MUST remove staging directory (or make empty) before returning.                                                                                       | Append stage outcome record in manifest (and health when enabled).                                                                      | Outputs present at contracted paths; stage outcome present.       |
| `running`  | `event.stage_complete_failed_fail_closed`   | Stage failure classified as `fail_closed`                                                                | `failed_fail_closed`   | Abort publication (`StagePublishSession.abort()`), ensuring no staged outputs are promoted. Record stage outcome `status="failed", fail_mode="fail_closed", reason_code=...` (atomic replace). MUST remove staging directory (or make empty) before returning.                        | Append stage outcome record in manifest (and health when enabled). Downstream enabled stages MUST be marked skipped by the run machine. | Stage outcome present; outputs absent.                            |
| `running`  | `event.stage_complete_failed_warn_and_skip` | Stage failure classified as `warn_and_skip` AND `StagePublishSession.finalize(...)` succeeds             | `failed_warn_and_skip` | Finalize publication (validate, then atomically promote). Record stage outcome `status="failed", fail_mode="warn_and_skip", reason_code=...` (atomic replace). MUST remove staging directory (or make empty) before returning.                                                        | Append stage outcome record in manifest (and health when enabled).                                                                      | Stage outcome present; outputs present.                           |
| `pending`  | `event.reconcile_outputs_without_outcome`   | Published outputs for `stage_id` are present AND contract validation passes                              | `succeeded`            | Rerun contract validation for the published artifacts. Record missing stage outcome as `status="success"` (atomic replace).                                                                                                                                                           | Append stage outcome record in manifest (and health when enabled).                                                                      | Stage outcome present; validation evidence (if emitted).          |
| `pending`  | `event.reconcile_outputs_without_outcome`   | Published outputs for `stage_id` are present AND contract validation fails                               | `failed_fail_closed`   | Record stage outcome `status="failed", fail_mode="fail_closed"`. Prefer `reason_code="contract_validation_failed"` when schema/content invalid; prefer `reason_code="storage_io_error"` when unreadable/corrupt. Downstream enabled stages MUST be marked skipped by the run machine. | Append stage outcome record in manifest (and health when enabled).                                                                      | Stage outcome present; deterministic validation failure evidence. |

#### Entry actions and exit actions

- **Entry actions**:

  - `running`:
    - MUST write all stage outputs into the stage's publish scratch directory and MUST NOT mutate
      published output paths directly.
  - `succeeded` / `failed_warn_and_skip`:
    - MUST ensure that any promoted outputs lie within the stage's allowed output roots and that
      contract-backed outputs validate before promotion.
  - `failed_fail_closed` / `skipped`:
    - MUST ensure published outputs for `stage_id` are absent.

- **Exit actions**:

  - `running`:
    - MUST either `finalize()` or `abort()` the publish session and MUST ensure the staging
      directory is removed or empty.

Requirements (normative):

- Artifact writes that define or advance state MUST be atomic or fail closed.
- Entry/exit actions MUST be idempotent with respect to the authoritative state representation.

#### Illegal transitions

- **Policy**: `fail_closed`
- **Classification**:
  - Implementations MUST NOT execute a stage when a terminal stage outcome record already exists for
    that `stage_id` in the current run bundle.
  - If an illegal transition occurs while a stage is `running`, the stage MUST be recorded as
    `status="failed", fail_mode="fail_closed"` with a deterministic `reason_code` (prefer
    `storage_io_error` for publication/invariant violations).
- **Observable evidence**: a terminal stage outcome record reflecting the failure plus deterministic
  publish-gate/validator error evidence (when emitted).

Requirements (normative):

- Illegal transitions MUST NOT silently mutate state.
- Illegal transitions MUST be observable.

#### Inconsistent artifact state handling

During run reconciliation (authority: ADR-0004) and during stage completion, implementations MUST
handle these cases deterministically:

- **Outcome implies outputs present but outputs missing**:
  - If stage outcome is `succeeded` or `failed_warn_and_skip` but required published outputs are
    absent, the run MUST fail closed. Prefer `reason_code="storage_io_error"` when the path existed
    but is corrupt/unreadable; prefer `reason_code="input_missing"` when the artifact is missing.
- **Outcome implies outputs absent but outputs present**:
  - If stage outcome is `failed_fail_closed` or `skipped` but published outputs are present, the run
    MUST fail closed with `reason_code="storage_io_error"`.
- **Staging directory present after terminalization**:
  - If `runs/<run_id>/.staging/<stage_id>/` remains non-empty after a terminal outcome is recorded,
    the run MUST fail closed with `reason_code="storage_io_error"`.

#### Observability

- **Required artifacts**:
  - Stage outcome record in `runs/<run_id>/manifest.json.stage_outcomes[]`
  - `runs/<run_id>/.staging/<stage_id>/` (transient; presence/absence is observable during execution
    and reconciliation)
  - Published stage outputs under run-relative contracted paths (as bound in
    `contract_registry.json`)
- **Structured logs** (optional):
  - Contract validation reports and publish-gate errors, when emitted, MUST be deterministic for
    equivalent inputs.
- **Human-readable logs**:
  - Stage wrappers SHOULD log lifecycle transitions, but logs MUST NOT be the sole conformance
    signal for CI.

Requirements (normative):

- Observability signals MUST be deterministic for equivalent inputs.
- Stage lifecycle state MUST be inferable from `manifest.json` for terminal states.

#### Conformance tests

Minimum conformance suite (normative):

1. **Happy path**: `pending` → `running` → `succeeded` with deterministic stage outcome and
   published outputs.
1. **Each terminal failure mode**:
   - `failed_fail_closed` (no outputs published)
   - `failed_warn_and_skip` (outputs published)
   - `skipped` (no outputs published)
1. **Illegal transition handling**: attempt to begin a stage with an existing terminal outcome and
   verify fail-closed behavior and observability.
1. **Idempotency**: simulate crash after outputs are promoted but before the stage outcome is
   recorded; then run reconciliation and verify `event.reconcile_outputs_without_outcome` records a
   single `succeeded` outcome without duplicating outputs.
1. **Determinism**: run the same fixture twice and assert identical stage outcome records and
   published artifact content for state-related outputs (excluding fields explicitly permitted to
   vary by their own contracts).

Tests MUST be automatable in CI and SHOULD reuse publish-gate conformance fixtures and the
stage-required-output matrix fixtures described in `100_test_strategy_ci.md`.

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

Lock file location (normative):

- Primary lock path: `runs/.locks/<run_id>.lock` (workspace-root relative; `runs/.locks/` is
  reserved for lockfiles and is not part of any run bundle).
- The orchestrator MUST create `runs/.locks/` if absent before attempting acquisition.

Required operations (minimum):

- `acquire(run_id) -> acquired: bool`
  - Semantics: MUST be an exclusive acquisition using atomic-create semantics for the primary lock
    path (or an equivalent mechanism with identical exclusivity).
  - If the lock already exists, it MUST return `false`.
- `release(run_id) -> void` (best-effort; MAY be a no-op on crash)

Stale lock policy (manual break-glass; deterministic):

- Default posture: **no automatic expiry**. Time-based leasing MUST NOT be used in v0.1.
- If `acquire(run_id)` returns `false`, the orchestrator MUST fail the invocation deterministically
  and MUST NOT create or mutate `runs/<run_id>/` unless an explicit operator override is present.

Operator override (normative when a CLI is exposed):

- Implementations that expose a CLI MUST provide a boolean flag `--force-run-lock` (default: false).
- `--force-run-lock` MUST be opt-in per invocation and MUST NOT be enabled by default in config
  files or environment variables.

Break-glass procedure (normative when `--force-run-lock=true`):

- If `runs/.locks/<run_id>.lock` exists, the orchestrator MUST preserve it by atomically renaming it
  within `runs/.locks/` to a deterministic stale-lock path:
  - Format: `runs/.locks/<run_id>.lock.stale.<nnnn>` where `<nnnn>` is a zero-padded decimal ordinal
    starting at `0001`.
  - Selection: choose the smallest `<nnnn>` such that the destination path does not already exist.
- After renaming, the orchestrator MUST retry `acquire(run_id)` and MUST proceed only if acquisition
  succeeds.
- If the rename fails because the lock disappeared (concurrent release), the orchestrator MUST retry
  `acquire(run_id)` once without renaming and MUST proceed only if acquisition succeeds.
- If `acquire(run_id)` still fails after the above, the orchestrator MUST treat the run as locked,
  MUST NOT mutate `runs/<run_id>/`, and MUST exit (fail closed).

Provenance recording (normative):

- When break-glass succeeds, the orchestrator MUST record an append-only event in
  `runs/<run_id>/manifest.json` under:

  - `extensions.orchestrator.v` = `1`
  - `extensions.orchestrator.run_lock.break_glass_events[]`

- Each event object MUST include:

  - `seq` (integer >= 1): 1-based sequence number; MUST equal the event's position in the array.
  - `stale_lock_filename` (string): `<run_id>.lock.stale.<nnnn>`
  - `stale_lock_sha256` (string): lowercase hex `sha256(file_bytes)` of the stale lock file.
  - `policy` (string): constant `manual_break_glass_v1`.

- Producers MUST NOT record operator identity, hostnames, usernames, or timestamps in this field.

- Producers MUST update `manifest.json` using atomic replace semantics.

Recovery hook:

- After acquiring the lock (whether normally or via break-glass), the orchestrator MUST perform the
  deterministic reconciliation pass defined in ADR-0004 before executing any stage.

Observability:

- If the lock cannot be acquired, the orchestrator MUST NOT create or mutate `runs/<run_id>/` and
  MUST fail the invocation deterministically (see conformance tests).
- When break-glass is used, the preserved stale lock file and its hash are observable via the
  manifest extension fields above.

#### Port: `PublishGate`

Purpose: provide "transaction-like" artifact publication: stage writes are staged, validated, and
then atomically promoted.

Required operations (minimum):

- `begin_stage(stage_id) -> StagePublishSession`
- `StagePublishSession.write_bytes(artifact_path, bytes) -> void`
- `StagePublishSession.write_json(artifact_path, obj, canonical: bool=true) -> void`
- `StagePublishSession.write_jsonl(artifact_path, rows_iterable) -> void`
- `StagePublishSession.finalize(expected_outputs: list[ExpectedOutput], unexpected_outputs_policy: UnexpectedOutputsPolicy = "lenient") -> PublishResult`
- `StagePublishSession.abort() -> void`

Where:

- `artifact_path` is run-relative (e.g., `logs/health.json`), NOT an absolute path.

- `ExpectedOutput` includes:

  - `artifact_path` (run-relative)
  - `contract_id` (optional; schema/contract identity as used by the contract validator)
    - When present/non-null, it MUST map to a contract in the registry (`contract_registry.json`).
    - When absent/null, the artifact is treated as **non-contract** (no schema validation).
    - If `artifact_path` matches a contract-registry binding, `contract_id` MUST be present and MUST
      equal the bound `contract_id` (fail closed).
  - `required: bool` (default `true`)

- `UnexpectedOutputsPolicy` is an enum: `strict` | `lenient`.

`PublishResult` is implementation-defined, but MUST expose (minimum):

- `unexpected_outputs: list[str]` (run-relative, sorted; see finalize semantics)
- `missing_required_outputs: list[str]` (run-relative, sorted; see finalize semantics)

`required` MUST be explicitly set by the stage wrapper for every `ExpectedOutput` entry based on the
stage enablement / required outputs matrix in `025_data_contracts.md` (see "Stage enablement and
required contract outputs (v0.1)"). Implementations MUST NOT rely on the default.

`required` MUST be explicitly set by the stage wrapper for every `ExpectedOutput` entry.

- For **contract-backed** outputs (`contract_id != null`), `required` MUST be derived from the stage
  enablement / required contract outputs matrix in `025_data_contracts.md` (see “Stage enablement
  and required contract outputs (v0.1)”). Implementations MUST NOT rely on the default.
- For **non-contract** outputs (`contract_id == null`), requiredness MUST be defined by the owning
  stage specification. The stage enablement matrix MUST NOT be used to infer requiredness for
  non-contract outputs.

Deterministic stage → contract-backed outputs (normative):

- The contract registry (`contract_registry.json`) is the source of truth for stage ownership of
  contract-backed artifacts via `bindings[].stage_owner`. Each contract-backed artifact path MUST be
  bound to exactly one `stage_owner` (single-writer).
- The contract registry (`contract_registry.json`) is also the source of truth for validation
  dispatch of contract-backed artifacts via `bindings[].validation_mode` (see
  `025_data_contracts.md`).
- When a publish session begins (`PublishGate.begin_stage(stage_id)`), `stage_id` MUST be a valid
  `stage_owner` value from the active contract registry (pipeline stage ids plus the reserved owner
  token `orchestrator`).
  - Orchestrator-owned artifacts that are published via `PublishGate` MUST use a session opened with
    `stage_id="orchestrator"`.
  - Pinned operator input snapshots under `inputs/` are materialized during build-time ingestion and
    are not written through `StagePublishSession` (see "Build-time input ingestion").
- The orchestrator (or stage wrapper) MUST construct `expected_outputs[]` by joining the current
  `stage_id` to `bindings[].stage_owner` and mapping concrete artifact paths to `contract_id` via
  `artifact_glob`.
  - Literal rule: for any binding without glob metacharacters, the stage wrapper MUST include the
    literal `artifact_glob` path in `expected_outputs[]` even if the file is absent in staging (so
    requiredness can be enforced).
  - Expansion rule: for any binding with glob metacharacters (for example `*` or `**`), the stage
    wrapper MUST expand `artifact_glob` using `glob_v1` semantics defined in `025_data_contracts.md`
    ("Glob semantics (glob_v1)") over the set of staged regular files under
    `runs/<run_id>/.staging/<stage_id>/`.
  - Ordering rule: the resulting `expected_outputs[]` list MUST be sorted by `artifact_path`
    (ascending, bytewise/lexicographic) to keep validation and reporting deterministic.
  - The join/expand step above produces the **contract-backed** subset of `expected_outputs[]`.
    - Stages MAY append additional **non-contract** expected outputs by setting `contract_id=null`.
    - Under `unexpected_outputs_policy="strict"`, every staged regular file MUST be declared in
      `expected_outputs[]` (contract-backed or non-contract), otherwise `finalize()` MUST fail
      closed.
- Ownership invariant: a stage MUST NOT publish any contract-backed output whose registry binding
  has `stage_owner != stage_id` (fail closed).

Finalize semantics (normative):

- All outputs for a stage MUST be written under `runs/<run_id>/.staging/<stage_id>/` first.
- Output-root guardrail: a stage MUST NOT write or promote any run-bundle output outside its allowed
  output roots for the active `stage_id`. Allowed roots are derived from the active contract
  registry bindings for that `stage_id` plus an explicit allowlist for non-contract outputs (see
  `026_contract_spine.md`). Violations MUST fail closed.
- `finalize()` MUST validate all **contract-backed** expected outputs (i.e., entries with
  `contract_id` set) using `ContractValidator` before any atomic promotion.
  - Expected outputs with `contract_id=null` are not schema-validated.
- `finalize()` MUST treat missing required outputs as a validation failure: if any
  `expected_outputs[]` entry with `required=true` is absent, `finalize()` MUST fail closed and MUST
  NOT promote any staged outputs.
- `finalize()` MUST treat missing optional outputs as non-failures: if an `expected_outputs[]` entry
  with `required=false` is absent, `finalize()` MUST NOT fail and MUST NOT attempt contract
  validation for that entry.
- Unexpected staged outputs MUST be handled according to `unexpected_outputs_policy`:
  - Define `unexpected_outputs[]` as the set of staged regular files that are not declared in
    `expected_outputs[]` (run-relative `artifact_path`s, sorted).
  - If `unexpected_outputs_policy="strict"`, the presence of any unexpected output MUST be treated
    as a validation failure (no promotion).
  - If `unexpected_outputs_policy="lenient"`, unexpected outputs MUST be promoted (subject to the
    output-root guardrail), but MUST be recorded in the publish result as `unexpected_outputs[]`.
  - Unexpected outputs are treated as non-contract and are not schema-validated.
- When `finalize()` fails, the orchestrator MUST record a fail-closed stage outcome (see
  `ADR-0005-stage-outcomes-and-failure-classification.md`).
- If validation fails, `finalize()` MUST NOT promote any staged outputs into their final run bundle
  locations.
- Atomicity scope (normative; v0.1):
  - Filesystem-level atomicity MUST be defined per destination path (per run-relative artifact
    path).
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
    for writing `manifest.json` and, when `operability.health.emit_health_files=true`,
    `logs/health.json`.

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
  - Implementations MUST ignore any `ExpectedOutput` entries with `contract_id=null` (non-contract).

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
  `runs/<run_id>/logs/health.json` (see `operability.health.emit_health_files`).
- Stage core logic and stage CLI wrappers MUST NOT open, patch, or rewrite `manifest.json` or
  `logs/health.json` directly; they MUST emit outcomes only through `OutcomeSink`.
- Calls to `record_stage_outcome` MUST be durable: when the call returns successfully, the
  corresponding outcome tuple MUST be present in `manifest.json` and, when enabled, in
  `logs/health.json`.

Required ordering behavior (normative):

- Stable ordering: stage outcomes MUST be emitted in canonical stage order, filtered to the stages
  that are present for the run (the sink MUST NOT synthesize outcomes for disabled stages).
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
  - The adapter factory MAY construct an in-process implementation or an in-process proxy that
    delegates to a local out-of-process adapter server (see "Out-of-process adapter profile (local
    IPC; host publish proxy writes)").
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

#### Out-of-process adapter profile (local IPC; host publish proxy writes)

This profile defines how an adapter implementation MAY run out-of-process as a local child process
while remaining compatible with the v0.1 ports-and-adapters architecture, determinism constraints,
and publish-gate contract spine.

This profile is a packaging + invocation contract. It does not change port semantics.

Goals (informative):

- Enable adapters implemented as separate processes without introducing service-to-service RPC.
- Preserve single-writer + publish-gate semantics by ensuring all run-bundle writes are mediated by
  the in-process host using the reference publisher.
- Keep adapter selection deterministic (composition root + in-process adapter registry).
- Support deterministic feature gating via a capabilities handshake.
- Preserve run comparability via manifest adapter provenance pinning.

Non-goals (informative):

- Remote adapters (network sockets, daemon services, agent mesh) are out of scope for v0.1.
- Containerization of adapter servers is out of scope for v0.1 (reserved for v0.2+).
- Ambient discovery of adapters (scanning PATH/site-packages/entrypoints/CWD/env) remains forbidden.
- Allowing an adapter server to write directly to any run-bundle path (including `.staging/**`) is
  forbidden in this profile.

##### Roles and boundaries

- Adapter server (out-of-process):

  - Implements exactly one `(port_id, adapter_id)` binding.
  - Serves a local IPC control channel.
  - MUST NOT write to the run bundle (including `.staging/**`).
  - Returns results and (optionally) host-mediated publish instructions.

- Adapter proxy (in-process):

  - Implements the port interface in-process and translates calls to IPC messages.
  - Owns the adapter server lifecycle (spawn, handshake, init, shutdown).
  - Applies any publish instructions through the in-process reference publisher (`PublishGate` /
    `StagePublishSession`) and other host enforcement surfaces.

- Proxy factory (composition root):

  - A registry factory that constructs the adapter proxy for a specific `(port_id, adapter_id)`
    binding.

##### Local-only IPC constraint (normative)

- The host-adapter control channel MUST use local IPC only.
- The host-adapter control channel MUST NOT use TCP/UDP sockets (including localhost) in v0.1.

Allowed IPC transports (v0.1):

- `stdio_json_lines_v1` (REQUIRED): newline-delimited JSON messages over stdin/stdout.

Other transports (for example AF_UNIX sockets or Windows named pipes) are reserved for v0.2+.

##### Transport: `stdio_json_lines_v1` (normative)

Spawn rules:

- The host MUST spawn the adapter server as a direct child process (no shell).
- The host MUST NOT rely on ambient PATH resolution to locate the adapter server executable/module.
  The spawn target MUST be derived deterministically from the registry-selected adapter provenance
  (and policy gates).

Streams:

- stdin is the request stream (host → server).
- stdout is the response/event stream (server → host).
- stderr is human logs only (not protocol).

stderr handling:

- The host MUST treat stderr as sensitive output.
- The host MUST enforce bounded stderr capture (byte limit) and bounded runtime to prevent hangs.
- Any persisted stderr/stdout diagnostics MUST be subject to the same safety posture as other
  persisted outputs (for example integration-credential leak detection).

Protocol framing:

- Each protocol message MUST be a single JSON object encoded as UTF-8 on exactly one line.
- Line delimiter MUST be LF (`\n`). The host MAY accept CRLF and normalize to LF on read.
- Messages MUST NOT exceed `max_message_bytes` (default 8,388,608 bytes) enforced by both sides.

##### IPC envelope (normative)

All protocol messages MUST use this envelope:

- `v` (string; REQUIRED): `"pa:adapter-ipc:v1"`
- `type` (string; REQUIRED): `request | response | event`
- `id` (integer; REQUIRED for request/response): request id chosen by the host
- `method` (string; REQUIRED for request): method name, ASCII `lower_snake_case` or dotted namespace
- `params` (object; OPTIONAL for request): request parameters
- `result` (object; REQUIRED for successful response): response payload
- `error` (object; REQUIRED for error response):
  - `code` (string; REQUIRED): stable token (`lower_snake_case`)
  - `message` (string; REQUIRED): human-readable; MUST NOT include secrets or absolute host paths
  - `details` (object; OPTIONAL): structured diagnostics; MUST NOT include secrets

Directionality + concurrency rule (v0.1, normative):

- The adapter server MUST NOT send `type="request"` messages in v0.1.
- The host MUST NOT pipeline requests. It MUST wait for the response to request `id=n` before
  sending request `id=n+1`.
- The adapter server MUST assume a single in-flight request.

##### Capabilities handshake (normative)

Immediately after spawn, the host MUST perform a handshake before using the adapter.

Host sends `method="hello"` with:

- `port_id` (id_slug_v1; REQUIRED)
- `adapter_id_expected` (id_slug_v1; REQUIRED)
- `protocols_supported` (array[string]; REQUIRED): MUST include `"pa:adapter-ipc:v1"`
- `features_required` (array[string]; REQUIRED):
  - v0.1 REQUIRED: MUST include `"host_publish_proxy_v1"`
- `limits` (object; REQUIRED):
  - `max_message_bytes` (integer; REQUIRED)

Adapter replies success with `result`:

- `port_id` (id_slug_v1; REQUIRED): the served port id
- `adapter_id` (id_slug_v1; REQUIRED)
- `adapter_version` (semver_v1 | version_token_v1; REQUIRED)
- `capabilities` (object; REQUIRED): port-scoped deterministic capabilities descriptor
  - This object MUST obey the determinism rules of the owning port spec.
- `features_supported` (array[string]; REQUIRED):
  - MUST include `"host_publish_proxy_v1"`
- `capabilities_sha256` (string; OPTIONAL): `sha256:<lowercase_hex>` of RFC 8785 canonical JSON of
  `capabilities`

Host verification (normative):

- The host MUST fail closed if:
  - `adapter_id != adapter_id_expected`, or
  - `port_id` does not match the registry-selected binding, or
  - `features_supported` does not include `"host_publish_proxy_v1"`.

Notes:

- The host MUST NOT treat adapter-reported `adapter_version` as authoritative for provenance.
  Provenance pinning is determined by the registry selection + configured pins.

##### Run-scoped initialization (normative)

Before the first port call, the host MUST send `method="init_run"` with:

- `run_id` (string; REQUIRED)
- `stage_id` (id_slug_v1; REQUIRED): the owning stage for the publish session
- `publish_policy` (object; REQUIRED):
  - `allowed_roots` (array[string]; REQUIRED):
    - Deterministic allowlist of run-relative output roots computed for `stage_id` by the host.
    - Roots that end with `/` are directory roots (prefix containment).
    - Roots that do not end with `/` are file roots (exact match containment).
    - The list MUST be sorted by UTF-8 byte order.
  - `unexpected_outputs_policy` (string; OPTIONAL): `strict | lenient`
    - When present, this value is advisory to the server; the host remains authoritative.

Adapter obligations (normative):

- The adapter server MUST treat `run_id` and `stage_id` as immutable for the lifetime of the
  process.
- The adapter server MUST NOT write to any run-bundle path (including `.staging/**`) regardless of
  `stage_id` or `allowed_roots`.

Process scoping (normative):

- In v0.1, an adapter server process MUST be scoped to exactly one `(run_id, stage_id)` tuple.
- To serve a different run or stage, the host MUST spawn a new process.

##### Host-mediated publish operations (normative)

Because v0.1 requires contract-backed outputs to be published only via the in-process reference
publisher, adapter servers in this profile do not write staged files directly.

Instead, a server MAY return publish instructions to the host as part of any successful response:

- `result.publish_ops` (array; OPTIONAL): list of publish operations for the host to apply through
  the in-process `StagePublishSession` for `stage_id`.

If present:

- `publish_ops[]` MUST be applied by the adapter proxy before returning the port call result to its
  caller.
- `publish_ops[]` MUST be applied in ascending `artifact_path` order (UTF-8 byte order).
- If multiple ops target the same `artifact_path`, the host MUST fail closed.

Publish op schema (v0.1):

Each publish op is an object:

- `op` (string; REQUIRED): `write_json | write_jsonl | write_bytes_base64`
- `artifact_path` (string; REQUIRED): run-relative POSIX path
- `contract_id` (string | null; OPTIONAL):
  - If `artifact_path` resolves to a contract registry binding, `contract_id` MUST be present and
    MUST equal the binding’s `contract_id`.
  - If `artifact_path` does not resolve to a contract registry binding, `contract_id` MUST be `null`
    when present.

`write_json` fields:

- `value` (any JSON value; REQUIRED)

`write_jsonl` fields:

- `rows` (array[object]; REQUIRED): each row is one JSON object (one line)

`write_bytes_base64` fields:

- `bytes_b64` (string; REQUIRED): standard base64 (RFC 4648 alphabet), no whitespace

Path safety (fail closed):

For every `artifact_path` in `publish_ops[]`, the host MUST enforce Contract Spine path requirements
(run-relative POSIX paths). At minimum, the host MUST reject (fail closed) any `artifact_path` that:

- contains a backslash character (U+005C) (separator MUST be `/`),
- starts with `/`,
- contains a drive prefix (for example `C:`),
- contains a NUL byte,
- contains any `..` segment,
- contains empty segments (`//`),
- ends with `/`.

Output-root guardrail (fail closed):

The host MUST enforce stage output-root containment using the `publish_policy.allowed_roots`
allowlist:

- If `artifact_path` is not contained by any `allowed_roots` entry, the host MUST fail closed and
  MUST NOT promote any staged outputs for the stage.

Contract-backed writer restrictions (fail closed):

When applying `publish_ops[]`, the host MUST consult the contract registry binding (if any) for
`artifact_path` and enforce:

- If `validation_mode="json_document"`, only `op="write_json"` is permitted.
- If `validation_mode="jsonl_lines"`, only `op="write_jsonl"` is permitted.
- If `validation_mode="text_document_v1"`, only `op="write_bytes_base64"` is permitted.
- If a server attempts to use `write_bytes_base64` for a contract-backed JSON or JSONL artifact, the
  host MUST fail closed.
- If `validation_mode="yaml_document"`, the host MUST fail closed (contract-backed YAML outputs are
  forbidden in v0.1).

Canonical bytes (normative):

- For `write_json`, the host MUST publish using
  `StagePublishSession.write_json(..., canonical=true)` so bytes match RFC 8785 (JCS).
- For `write_jsonl`, the host MUST publish using `StagePublishSession.write_jsonl(...)` so bytes
  match the JSONL physical invariants (LF-only; canonical JSON per line; trailing LF rule).

##### Proxy factory requirements (normative)

An out-of-process adapter MUST be wired via a proxy factory registered in the in-process adapter
registry.

The proxy factory MUST:

- enforce adapter policy gates before spawn:
  - reject non-builtin adapters when third-party adapters are disallowed
  - verify signatures when required by policy
- spawn the adapter server deterministically (no ambient discovery; no shell; no PATH-based
  resolution)
- perform `hello` handshake and fail closed on mismatch
- perform `init_run` exactly once before any port method call
- translate port interface calls into IPC requests and responses
- apply `result.publish_ops` through the stage’s in-process `StagePublishSession` and enforce:
  - path safety
  - output-root guardrail
  - contract-backed writer restrictions
- bound execution with timeouts and output limits (stdout/stderr bytes) to prevent hangs
- treat adapter server stderr/stdout diagnostics as sensitive and ensure persisted diagnostics do
  not leak integration credentials (fail closed on leak)

The proxy factory MUST NOT:

- mutate the adapter registry after stage execution begins
- allow the adapter server to bypass publish-gate staging and promotion semantics
- pass resolved integration credential values via command-line arguments when invoking the adapter
  server (use environment variables where applicable)

##### Provenance pinning (normative)

Out-of-process adapters participate in the existing adapter provenance record without changes:

- The host MUST record the resolved adapter provenance entry for the binding in the run manifest
  (see "Adapter provenance recording (v0.1)").
- `source_ref` MUST NOT be an absolute host path.

##### Failure mapping (guidance; non-normative)

- Spawn failure because the adapter executable is missing: prefer the stage-specific "tool missing"
  reason code where defined.
- Handshake/protocol mismatch, or policy denial (third-party disallowed / signature invalid): treat
  as configuration invalid (prefer `reason_code=config_schema_invalid` unless a more specific
  stage-scoped reason code exists).

##### Verification hooks (normative)

The repository MUST include conformance fixtures for this profile:

1. Handshake conformance:

   - adapter reports mismatched `adapter_id` => host fails closed
   - adapter omits required feature `"host_publish_proxy_v1"` => host fails closed

1. Output-root guardrail:

   - adapter attempts to publish an artifact outside `publish_policy.allowed_roots` via
     `publish_ops` => host fails closed and stage publishes nothing

1. Path safety:

   - adapter attempts to publish `artifact_path="../manifest.json"` => host rejects (fail closed)

1. Contract-backed writer restrictions:

   - adapter attempts `write_bytes_base64` for a contract-backed JSON/JSONL artifact => host rejects
     (fail closed)

1. Canonical JSON/JSONL:

   - fixtures assert contract-backed JSON/JSONL bytes match publisher canonical serialization rules

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
- `capabilities_sha256` (string; OPTIONAL): `sha256:<hex>` of RFC 8785 (JCS) canonical JSON of the
  adapter's deterministic, port-scoped capability descriptor as observed by the orchestrator at
  adapter load time.
  - This value MUST be computed by the orchestrator host (do not trust adapter-provided values).
  - Implementations SHOULD include `capabilities_sha256` when the owning port defines a
    deterministic capability descriptor that can affect selection, feature gates, or any
    contract-backed output.
  - Port specifications MAY further require `capabilities_sha256` for specific ports.

Determinism requirements (normative):

- `entries[]` MUST be sorted by `(port_id asc, adapter_id asc)` using UTF-8 byte order (no locale).
- The provenance record MUST NOT include hostnames, machine-specific absolute paths, or timestamps.
- If `source_kind != "builtin"`, `source_digest` MUST be present and MUST match
  `^sha256:[0-9a-f]{64}$`.
- If `capabilities_sha256` is present, it MUST match `^sha256:[0-9a-f]{64}$`.
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

Purple Axiom’s stage model is intentionally "contract-first": each stage can be implemented as a
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
     "auto-discovery" selection unless it is explicitly ordered and pinned by configuration.
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

   - Any write that publishes stage-produced contract-backed outputs MUST go through `PublishGate`.
     - Exception (v0.1): orchestrator build-time pinning of operator-supplied inputs under
       `runs/<run_id>/inputs/` is performed outside `StagePublishSession` (see "Build-time input
       ingestion").
   - Partial promotion is forbidden: if a stage fails fail-closed, it MUST NOT publish its final
     output directory.

1. **Deterministic artifact paths**

   - Contract-backed artifacts MUST use deterministic paths.
   - Timestamped contracted filenames are disallowed: timestamps belong inside artifact content, not
     in filenames.
   - Implementations MUST treat any filename containing date/time-like tokens (e.g., `YYYY-MM-DD`,
     `YYYYMMDD`, RFC3339-like `...T...Z`) as "timestamped" for the purposes of this rule (a stricter
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
     - Contract alignment (schema-owned reason fields): for contract-backed artifacts,
       `reason_domain` MUST equal the artifact schema’s `contract_id` (see
       `docs/contracts/contract_registry.json`).
     - Exemption (placeholder namespace): fields under the top-level `placeholder` object are
       governed by the placeholder contract. `placeholder.reason_domain` MUST be
       `artifact_placeholder` (and `placeholder.reason_code` is paired per that contract), and
       `placeholder.reason_domain` MUST NOT be subject to the contract-alignment check. Rationale:
       placeholders must be schema-valid while using a fixed placeholder reason domain (see
       `090_security_safety.md`, "Placeholder artifacts").
     - For non-contract placeholder/operator-interface artifacts, `reason_domain` MUST be one of the
       explicitly documented constants (`artifact_placeholder`, `operator_interface`)..

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

1. `run_lock_break_glass_requires_explicit_force`

   - Setup: create `runs/.locks/<run_id>.lock` with arbitrary bytes (simulate a dead/crashed lock
     owner) and ensure `runs/<run_id>/` is either absent or present but not actively being mutated.
   - Assert (no override): an orchestrator invocation targeting the same `run_id` without an
     explicit break-glass override fails closed and does not create or mutate `runs/<run_id>/`.
   - Assert (override): with the explicit override enabled (canonical CLI flag: `--force-run-lock`),
     the orchestrator:
     - preserves the existing lock by renaming it to `runs/.locks/<run_id>.lock.stale.0001` (or the
       next deterministic ordinal),
     - acquires the new lock at `runs/.locks/<run_id>.lock`,
     - records a provenance event under `extensions.orchestrator.run_lock.break_glass_events[]`, and
     - performs the deterministic reconciliation pass before running any stage (ADR-0004).

1. `publish_gate_atomic_publish_no_partial_outputs`

   - Setup: simulate a stage that writes multiple outputs; force an injected failure between "write"
     and "finalize".
   - Assert: no contracted outputs appear in final locations; only staging contains partial data.
   - Assert: rerun behavior is deterministic (either cleanly resumes and publishes, or fails closed
     with a stable storage/consistency reason code).

1. `publish_gate_output_root_guardrail_fail_closed`

   - Attempt to publish an output outside `allowed_roots(stage_id)` (e.g., `reporting` staging a
     file under `normalized/`), and assert publish fails closed, emits a validation report, and
     promotes nothing.

1. `publish_gate_extra_roots_allow_non_contract_outputs`

   - Telemetry publishes a non-contract artifact under `raw_parquet/` (declared via extra roots) and
     asserts it can be promoted.

1. `publish_gate_registry_roots_consistency`

   - Static test: compute `allowed_roots(stage_owner)` and verify every registry binding’s
     `artifact_glob` is contained by those roots (fails closed on mismatch).

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

1. `noise_engine_provenance_recorded` (v0.2+)

   - Setup: run a minimal pipeline with `runner.environment_config.noise_profile.enabled=true`.
   - Assert: `manifest.extensions.runner.environment_noise_profile` includes the declared noise
     engine
     - adapter pins (and any coordinating server endpoint(s)).
   - Assert: if noise is enabled but any required pin is missing, the orchestrator fails closed and
     records a deterministic failure outcome tuple `(stage, status, fail_mode, reason_code)` for the
     same inputs on repeated runs.

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
     allowlisted export namespaces under `<workspace_root>/exports/` such as `exports/datasets/**`
     and `exports/.staging/datasets/**`).
   - Assert: the run does not create new top-level directories at the workspace root other than the
     reserved set.

## Stage IO boundaries

**Summary**: Each stage reads inputs from the run bundle and writes outputs back. The table below
defines the minimum IO contract for v0.1.

| Stage ID        | Minimum inputs                                                                                             | Minimum outputs                                                                                                                                                                                                                            |
| --------------- | ---------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `lab_provider`  | Run configuration, provider inputs                                                                         | `logs/lab_inventory_snapshot.json` (inventory snapshot; referenced by manifest)                                                                                                                                                            |
| `runner`        | Inventory snapshot, scenario plan                                                                          | `ground_truth.jsonl`, `runner/actions/<action_id>/**` evidence; `runner/principal_context.json` (when enabled); (v0.2+: `plan/**`)                                                                                                         |
| `telemetry`     | inventory snapshot, `inputs/range.yaml`, `inputs/scenario.yaml`, `ground_truth.jsonl` lifecycle timestamps | `raw_parquet/**`, `raw/**` (when raw preservation is enabled), `logs/telemetry_validation.json`                                                                                                                                            |
| `normalization` | `raw_parquet/**`, mapping profiles                                                                         | `normalized/**`, `normalized/mapping_coverage.json`, `normalized/mapping_profile_snapshot.json`                                                                                                                                            |
| `validation`    | `ground_truth.jsonl`, `normalized/ocsf_events/**`, criteria pack snapshot                                  | `criteria/criteria.jsonl`, `criteria/results.jsonl`, `criteria/manifest.json`                                                                                                                                                              |
| `detection`     | `normalized/ocsf_events/**`, bridge mapping pack, Sigma rule packs                                         | `bridge/**`, `detections/detections.jsonl`, `detections/manifest.json`                                                                                                                                                                     |
| `scoring`       | `ground_truth.jsonl`, `criteria/**`, `detections/**`, `normalized/ocsf_events/**`                          | `scoring/summary.json`, `scoring/coverage.json`, `logs/scoring_diagnostics.json`                                                                                                                                                           |
| `reporting`     | `scoring/**`, `criteria/**`, `detections/**`, `manifest.json`, `inputs/**` (when regression enabled)       | `report/report.json`, `report/thresholds.json`, `report/run_timeline.md`, `report/**` (optional HTML + supplemental artifacts), `inputs/baseline_run_ref.json` (when regression enabled), `inputs/baseline/manifest.json` (when available) |
| `signing`       | Finalized `manifest.json`, selected artifacts                                                              | `security/**` (checksums, signature, public key)                                                                                                                                                                                           |

**Note (normative):** "Raw preservation is enabled" means `telemetry.raw_preservation.enabled=true`
(see `120_config_reference.md`).

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
`manifest.lab.inventory_snapshot_sha256`.

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
- When `runner.environment_config.mode="apply"`, the environment configurator MAY place, update, or
  restart telemetry collectors/configuration as needed to satisfy Tier-2 ("Environment config
  apply") in "Telemetry configuration tiers (v0.1; normative)". This work MUST complete before any
  action enters the runner `prepare` lifecycle phase. Mid-run collector mutation via control-plane
  RPC is forbidden in v0.1.
- When such configuration is performed, the orchestrator MUST record an additive substage outcome
  `runner.environment_config` in `manifest.json` and, when
  `operability.health.emit_health_files=true`, in `logs/health.json`. It MUST also emit structured
  operability evidence under `runs/<run_id>/logs/` (log classification is file-level per ADR-0009;
  schema and filenames are implementation-defined here; see the
  [operability specification][operability-spec]).
- Environment configuration is distinct from per-action requirements evaluation in `prepare`. It
  MUST NOT change the semantics of per-action lifecycle outcomes.

Preflight / Readiness Gate:

- Run before scenario execution.
- Validate resources + config invariants + required collectors/log sources.
- Implementations MAY emit a `runner.preflight` substage outcome for quick triage.
  - If emitted, it MUST be recorded in `manifest.json` and, when
    `operability.health.emit_health_files=true`, in `logs/health.json`.
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
  pre-provisioned collector configuration (v0.1 baseline) and runtime canary validation. Per-run
  collector reconfiguration is permitted only as Tier-2 `runner.environment_config` (apply mode)
  before the runner `prepare` lifecycle phase; Tier-3 mid-run control-plane RPC reconfiguration is
  forbidden in v0.1.
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
- Emit `normalized/ocsf_events/**` as the canonical OCSF event store (Parquet dataset; includes
  `normalized/ocsf_events/_schema.json`).
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

#### Detection content release bundles (optional input)

To support reproducible CI, supply-chain integrity, and deterministic "what content was used"
provenance, the detection stage MAY be configured to source its content from a **Detection Content
Release** (a.k.a. **detection content bundle**) instead of reading rules/mapping material directly
from a working tree.

A detection content bundle is a non-run artifact that snapshots:

- the effective ruleset used for the run (Sigma rule files keyed by `rule_id`),
- one or more bridge mapping pack snapshots, and
- optionally, criteria pack snapshots.

When a detection content bundle is used as an input, implementations MUST:

- Validate the bundle offline before use (manifest schema + integrity material) per the
  [data contracts specification][data-contracts].
- Enforce that the run’s pinned versions (for example `manifest.versions.rule_set_id` /
  `rule_set_version` and `manifest.versions.mapping_pack_id` / `mapping_pack_version`) are
  compatible with the content bundle manifest.
- Fail closed if compatibility cannot be established deterministically (do not "best effort" fall
  back to local content).

This input option enables offline provenance validation using only:

`(run bundle + content bundle + contracts bundle)`.

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
  - Record a `reporting.regression_compare` substage outcome in `manifest.json` and, when
    `operability.health.emit_health_files=true`, in `logs/health.json` (even when baseline
    resolution or comparison is indeterminate).
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

| Extension type            | Examples                                                                     | Interface                                                       |
| ------------------------- | ---------------------------------------------------------------------------- | --------------------------------------------------------------- |
| Lab providers             | Manual, Ludus, Terraform, Vagrant, custom                                    | Inventory snapshot contract                                     |
| Environment configurators | Ansible, DSC v3, scripts, image-baked profiles, custom                       | Readiness profile + deterministic operability                   |
| Execution adapters        | Atomic Red Team, Caldera, custom                                             | Execution adapter interface + ground truth + evidence contracts |
| Telemetry sources         | Windows Event Log, Sysmon, osquery, Linux auditd (`linux-auditd`), EDR, pcap | OTel receiver + raw schema                                      |
| Schema mappings           | OCSF 1.7.0, future OCSF versions, profiles                                   | Mapping profile contract                                        |
| Rule languages            | Sigma, YARA, Suricata (future)                                               | Bridge + evaluator contracts                                    |
| Bridge mapping packs      | Logsource routers, field alias maps                                          | Mapping pack schema                                             |
| Evaluator backends        | Native (`native_pcre2`), Tenzir, other engines                               | Compiled plan + detection contract                              |
| Criteria packs            | Default, environment-specific                                                | Criteria pack manifest + entries                                |
| Redaction policies        | Default patterns, custom patterns                                            | Redaction policy contract                                       |

Scenario execution backends are implemented as **execution adapters**: a first-class adapter
interface used by the runner to execute actions, declare capabilities/correlation carriers, and emit
deterministic execution evidence. See `033_execution_adapters.md`.

Environment configurators are also the v0.1 integration point for generating realistic background
activity ("noise") so that datasets are not comprised solely of attack actions. Examples include:

- domain and directory baseline activity (for example AD-Lab-Generator and ADTest.exe), and
- server/workstation workload activity via scheduled tasks (Windows) and cron jobs (Linux).

User simulation frameworks that require a coordinating server (for example GHOSTS) SHOULD be
deployed as optional supporting services (outside core stage boundaries) and integrated by
configuring endpoint agents via `runner.environment_config`.

### Noise engine adapters

Noise engine adapters (v0.2+) are runner-integrated adapters that consume
`runner.environment_config.noise_profile` and drive benign background activity. Implementations MAY
use a host-local agent and MAY rely on an optional server component (for example GHOSTS-style
coordination).

Deterministic input contract (normative):

- The adapter MUST treat the selected noise profile as a deterministic input surface.
  - At minimum: `profile_id`, `profile_version`, `profile_sha256`, `seed`, and any explicit
    schedule/window fields present in the profile definition.
- The adapter MUST NOT introduce hidden nondeterminism (for example: unpinned random sources,
  wall-clock scheduling decisions, or ad-hoc network discovery).

Provenance and pin recording (normative):

- When noise generation is enabled, the run bundle MUST record:
  - adapter name and adapter version
  - engine name and engine version (and image digest if containerized)
  - any endpoint(s) used for coordinating server components (when applicable)
- Canonical location: `manifest.extensions.runner.environment_noise_profile` in `manifest.json`.
  - v0.1 records profile pins here; v0.2+ extends this location with adapter/engine provenance.
  - If any values are mirrored elsewhere, this manifest location is authoritative.
  - Endpoint lists MUST be deterministically ordered (UTF-8 byte ordering).

Supporting services relationship (normative):

- If the engine requires a server component, it MUST be deployed as an optional supporting service
  and wired via `runner.environment_config` (explicit endpoint configuration), not via ad-hoc
  discovery.

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
- [Execution adapters specification][execution-adapters-spec]
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
[execution-adapters-spec]: 033_execution_adapters.md
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
