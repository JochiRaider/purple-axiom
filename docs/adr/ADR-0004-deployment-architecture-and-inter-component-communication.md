---
title: 'ADR-0004: Deployment architecture and inter-component communication'
description: Defines the v0.1 deployment topology and inter-component communication contract.
status: draft
category: adr
---

# ADR-0004: Deployment architecture and inter-component communication

## Context

Purple Axiom v0.1 specifies a staged pipeline (lab provider, runner, telemetry, normalization,
validation, detection, scoring, reporting, signing (when enabled)) and a local-first "run bundle"
rooted at `runs/<run_id>/`. The specs already define:

- a canonical OpenTelemetry Collector topology (required agent tier, optional gateway tier)
- run bundle layout and storage tiers
- deterministic writing rules for artifacts and datasets

What is not yet explicit is the intended **deployment model** and the **communication pattern**
between pipeline components, which impacts determinism, operability, and implementation choices
(single process vs multiple processes, file coordination vs OTLP/RPC between stages).

This ADR defines the normative v0.1 deployment topology and the inter-component communication
contract.

## Decision

### Normative v0.1 topology

Purple Axiom v0.1 MUST use a **single-host, local-first** topology with a **one-shot orchestrator**
and **file-based stage coordination**.

#### Orchestrator (execution plane)

- The pipeline MUST be driven by a single **orchestrator** running on the "run host" (the machine
  that owns `runs/<run_id>/`).
- The orchestrator MUST run as a **one-shot process per run** (invoked manually or via external
  scheduling such as cron or systemd timers).
- The orchestrator SHOULD execute the core pipeline stages **in a single process** for v0.1
  (monolith implementation), even if some steps invoke external binaries (executors, collectors,
  packagers).
- To preserve the optional "local multi-process" evolution path (see "Future options"), stage logic
  SHOULD be implemented as ports-injected cores with optional per-stage CLI wrappers that call the
  same core.
- The orchestrator MUST acquire an exclusive run lock before creating or mutating a run bundle.
  - The orchestrator MUST create `runs/.locks/` if absent.
  - Lock primitive (normative): atomic creation of `runs/.locks/<run_id>.lock` (reserved for
    lockfiles; not part of any run bundle).
  - Failure to acquire the run lock MUST be treated as `lock_acquisition_failed` (see ADR-0005).

Non-goal (v0.1): a required long-running daemon or scheduler control plane.

#### Telemetry plane (OpenTelemetry Collector tiers)

- Telemetry collection MUST follow the canonical OTel model:
  - **Agent tier (required):** Collector on each endpoint to read OS sources (Windows Event Log
    (including Sysmon) with `raw: true`, Linux auditd, syslog, osquery results).
  - **Gateway tier (optional):** A collector service that receives OTLP from agents and applies
    buffering/fan-out.
- OTLP MAY be used between Collector tiers (agent to gateway, gateway to sinks).
- OTLP MUST NOT be required as a coordination mechanism between Purple Axiom's core stages
  (`lab_provider`, `runner`, `telemetry`, `normalization`, `validation`, `detection`, `scoring`,
  `reporting`, `signing`). Core-stage coordination is file-based.

#### Run bundle (coordination and evidence plane)

- The run bundle (`runs/<run_id>/`) is the authoritative coordination substrate for all core stages.
- Stages MUST communicate by reading and writing **contract-backed artifacts** under the run bundle
  root.
- The manifest (`runs/<run_id>/manifest.json`) MUST remain the authoritative index of what exists
  and which versions/config hashes were used.
- `inputs/**` (when present) contains run-scoped operator inputs and baseline references (when
  regression is enabled). All stages MUST treat `inputs/**` as read-only.
- When environment configuration is enabled, the runner MUST record the configuration boundary as
  additive substage `runner.environment_config` and MUST emit deterministic operability evidence
  under `runs/<run_id>/logs/**`.

#### Optional packaging (Docker Compose)

Docker Compose MAY be provided for ease of installation and home lab setup, but in v0.1 it MUST be
considered packaging only:

- One-shot containers for stages (jobs) writing to a shared volume for `runs/`.
- Optional long-running containers for supporting services (for example, a gateway collector, a
  read-only UI, or a user-noise simulator coordinator such as a GHOSTS API server).
- Compose MUST NOT introduce a distributed control plane that changes stage semantics or determinism
  guarantees.

### Inter-component communication contract (v0.1)

#### Communication patterns

Core stages MUST use one of the following mechanisms, in priority order:

1. **Filesystem artifacts in the run bundle** (required).
1. **Local process invocation** (optional implementation detail).
1. **OTLP within the telemetry plane only** (allowed for collectors, not for stage coordination).

Core stages MUST NOT require service-to-service RPC between `lab_provider`, `runner`, `telemetry`,
`normalization`, `validation`, `detection`, `scoring`, `reporting`, and `signing` in v0.1.

#### Stable stage identifiers

Stage outcomes and stage-scoped outputs MUST use stable stage identifiers consistent with the
pipeline:

- `lab_provider`
- `runner`
- `telemetry`
- `normalization`
- `validation`
- `detection`
- `scoring`
- `reporting`
- `signing` (when enabled)

Substages MAY be expressed as dotted identifiers (for example, `lab_provider.connectivity`,
`runner.environment_config`, `telemetry.windows_eventlog.raw_mode`, `reporting.regression_compare`)
provided they remain stable and are only additive.

### Stage IO boundaries (normative)

Each stage MUST be implementable as "read inputs from run bundle, write outputs to run bundle."
Implementations MAY structure code internally as functions, classes, or subprocesses, but the
observable contract is the filesystem.

Minimum v0.1 IO boundaries:

| Stage           | Minimum inputs                                                                                                                       | Minimum outputs (published paths)                                                                                                                                  |
| --------------- | ------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `lab_provider`  | run configuration, provider inputs                                                                                                   | inventory snapshot artifact (referenced by manifest)                                                                                                               |
| `runner`        | inventory snapshot, scenario plan                                                                                                    | `ground_truth.jsonl`, `runner/actions/<action_id>/**` evidence; \[v0.2+: `plan/**`\]                                                                               |
| `telemetry`     | inventory snapshot, `inputs/range.yaml`, `inputs/scenario.yaml`, `ground_truth.jsonl` lifecycle timestamps (plus configured padding) | `raw_parquet/**`, `raw/**` (when raw preservation enabled), `logs/telemetry_validation.json` (when validation enabled)                                             |
| `normalization` | `raw_parquet/**`, mapping profiles                                                                                                   | `normalized/**`, `normalized/mapping_coverage.json`, `normalized/mapping_profile_snapshot.json`                                                                    |
| `validation`    | `ground_truth.jsonl`, `normalized/**`, criteria pack snapshot                                                                        | `criteria/manifest.json`, `criteria/criteria.jsonl`, `criteria/results.jsonl`                                                                                      |
| `detection`     | `normalized/**`, bridge mapping pack, Sigma rule packs                                                                               | `bridge/**`, `detections/detections.jsonl`                                                                                                                         |
| `scoring`       | `ground_truth.jsonl`, `criteria/**`, `detections/**`, `normalized/**`                                                                | `scoring/summary.json`                                                                                                                                             |
| `reporting`     | `scoring/**`, `criteria/**`, `detections/**`, manifest, `inputs/**` (when regression enabled)                                        | `report/**` (MUST include `report/report.json`, `report/thresholds.json`, and `report/run_timeline.md`; HTML and other supplemental artifacts MAY also be emitted) |
| `signing`       | finalized manifest, selected artifacts                                                                                               | `security/**` (checksums, signature, public key)                                                                                                                   |

Note: This table defines the minimum published paths for v0.1 stage boundaries. Stages MAY emit
additional artifacts, but MUST NOT weaken determinism guarantees or change the meaning of the paths
listed above.

Note: This ADR does not redefine the detailed contracts or schemas for these artifacts. It
constrains deployment and inter-stage communication such that existing and future contracts remain
implementable and testable.

### Filesystem publish and completion semantics (normative)

To preserve determinism and avoid partial reads:

#### Single-writer rule

- For a given `(run_id, stage_id)`, there MUST be at most one writer publishing stage outputs at a
  time.

#### Staging then atomic publish

For any stage that writes a directory or multi-file artifact set:

1. The stage MUST write outputs into a staging location under the run bundle:
   - `runs/<run_id>/.staging/<stage_id>/`
1. The stage MUST validate required contracts for the outputs it intends to publish (presence +
   schema validation where applicable).
   - Stage ↔ contract-backed outputs MUST be machine-discoverable via the contract registry:
     - `contract_registry.json.bindings[].stage_owner` declares the owning stage ID (or
       `orchestrator`) for each contract-backed `artifact_glob`.
     - Orchestrator/stage wrappers MUST construct the publish gate `expected_outputs[]` list by
       filtering `bindings[]` on `stage_owner == <stage_id>` and mapping concrete artifact paths to
       `contract_id`.
1. On contract validation failure, the stage MUST emit a deterministic contract validation report
   at:
   - `runs/<run_id>/logs/contract_validation/<stage_id>.json`
1. Contract validation behavior (dialect, `$ref` restrictions, deterministic error reporting) is
   defined in `../spec/025_data_contracts.md` (Validation engine and publish gates).
1. The stage MUST publish outputs by an atomic rename/move from staging into the final location
   under `runs/<run_id>/`.
1. If the stage fails before publish, it MUST NOT create or partially populate the final output
   directory.

Cleanup note: `.staging/` is an internal scratch area. Implementations SHOULD remove any remaining
stage staging directories under `runs/<run_id>/.staging/` during run finalization or resume (after
acquiring the run lock), but such cleanup MUST be limited to `.staging/**` and MUST NOT delete
published outputs or logs.

#### Completion requires outcome recording

A stage MUST be considered complete only when:

Outcome writer (normative): stage outcome persistence MUST be performed by the orchestrator (the
run-lock holder) to preserve a single writer for `manifest.json` and `logs/health.json`. Stages and
any per-stage commands MUST NOT write those files directly.

- its stage outcome has been recorded in the manifest (and in `logs/health.json` when enabled), and
- its outputs are either:
  - published (when `status="success"`, or when `status="failed"` with `fail_mode="warn_and_skip"`),
    or
  - absent (when `status="skipped"`, or when `status="failed"` with `fail_mode="fail_closed"`).

Stage outcome recording and failure classification are defined in the
[stage outcomes ADR](ADR-0005-stage-outcomes-and-failure-classification.md).

#### State reconciliation rules (normative)

- The orchestrator MUST perform a deterministic reconciliation pass after acquiring the run lock and
  before executing any stage.
- The orchestrator MUST treat stage outcomes recorded in `manifest.json` as the authoritative record
  of stage completion. Published outputs MUST be treated as authoritative only when they are
  consistent with a recorded outcome.
- For any stage with a recorded outcome that implies outputs are published, the orchestrator MUST
  verify the required published paths exist (and MUST run publish-gate contract validation where
  applicable) before executing any downstream stage.
- If published output paths for a stage exist but no stage outcome is recorded, the orchestrator
  MUST re-run publish-gate contract validation on those outputs and then:
  - if validation passes, record the missing stage outcome as `status="success"` (it SHOULD annotate
    the outcome with an implementation-defined "reconciled from filesystem" marker), or
  - if validation fails, fail closed and mark downstream stages `skipped`.
- `.staging/**` entries MUST NOT be treated as published outputs during reconciliation.

### Error propagation and partial failures (v0.1)

- The orchestrator MUST derive `manifest.status` from the set of recorded stage outcomes using the
  normative derivation rules in the data contracts spec.
- Stages configured (or defaulted) as `fail_closed` MUST cause the run to halt and mark downstream
  stages `skipped`.
- Stages configured as `warn_and_skip` MAY allow the run to continue, but MUST record deterministic
  degradation evidence (stage outcome plus reason codes and structured logs where defined).

This ADR constrains how failures propagate operationally (halt vs continue) but delegates the
specific failure taxonomy and reason-code requirements to the stage outcomes ADR.

## Canonical run sequence (v0.1)

The following sequence is normative at the level of stage ordering and artifact publication.

```text
Orchestrator (one-shot, run host)
  |
  |-- acquire run lock (exclusive writer; runs/.locks/<run_id>.lock)
  |-- create runs/<run_id>/ (staging allowed)
  |-- write initial manifest.json skeleton (run metadata, toolchain versions, config hashes)
  |-- materialize/pin operator inputs into `runs/<run_id>/inputs/` (at minimum `inputs/range.yaml` and `inputs/scenario.yaml`)
  |
  |-- [lab_provider] resolve inventory snapshot -> publish inventory artifact -> record stage outcome
  |
  |-- [runner.environment_config] (optional) preflight/readiness gate: validate resources + config invariants + required collectors/log sources -> logs/** -> record substage outcome
  |
  |-- [runner] execute scenario actions -> write ground_truth.jsonl + runner/actions/<action_id>/** -> record stage outcome
  |
  |-- [telemetry] ensure collection window captured + validate canaries -> publish raw_parquet/** (and raw/** when enabled) + logs/telemetry_validation.json -> record stage outcome
  |
  |-- [normalization] map raw_parquet/** -> publish normalized/** + normalized/mapping_coverage.json + normalized/mapping_profile_snapshot.json -> record stage outcome
  |
  |-- [validation] snapshot criteria pack + evaluate criteria -> publish criteria/manifest.json + criteria/criteria.jsonl + criteria/results.jsonl -> record stage outcome
  |
  |-- [detection] compile/evaluate sigma via bridge -> publish bridge/** + detections/detections.jsonl -> record stage outcome
  |
  |-- [scoring] join ground truth, criteria, detections -> publish scoring/summary.json -> record stage outcome
  |
  |-- [reporting] (optional regression) materialize inputs/baseline/** -> publish report/report.json + report/thresholds.json + report/run_timeline.md (and optional HTML) 
  |   -> record stage outcome
  |
  |-- [signing] (optional) sign artifacts -> publish security/** -> record stage outcome
  |
  |-- finalize manifest.status and seal manifest.json
  |-- release run lock
```

## Consequences

### Positive

- Determinism is improved by minimizing concurrency and by making the run bundle the single source
  of truth for stage coordination.
- Operability is improved because operators can reproduce and debug runs by inspecting a single run
  bundle tree and manifest.
- Future extensibility remains viable because stage boundaries are defined by stable file contracts,
  not by in-process implementation details.
- Docker Compose can be introduced as an installation convenience without changing architecture
  semantics.

### Trade-offs

- v0.1 does not provide a built-in scheduler control plane. Scheduling is external.
- A one-shot orchestrator requires explicit rules for resuming/retrying runs, which are handled via
  run bundle state, locks, and stage outcomes rather than a daemon database.
- Streaming cross-stage pipelines (service mesh with OTLP between stages) are intentionally deferred
  due to determinism and safety risk.

## Future options (non-normative)

The following may be added later without breaking v0.1 contracts if the filesystem stage IO
boundaries remain stable:

- A "local multi-process" mode where each stage is a separately invocable command, still reading and
  writing the same run bundle artifact contracts.

  - Stage commands should be thin wrappers over the same ports-injected stage cores used by the
    in-process orchestrator mode.
  - Stage outcome recording should remain orchestrator-owned to preserve a single writer for
    `manifest.json` and `logs/health.json`.

- A long-running daemon that schedules runs and maintains a queue, provided:

  - it uses the same lock and atomic publish rules, and
  - UI actions do not bypass contract validation.

- Remote execution runners or distributed collection backends, provided the run bundle still
  captures a complete, deterministic snapshot of inputs and outputs required for reproducibility.

- Optional control-plane RPC for endpoint management (for example, pushing validated collector
  configuration or triggering canary actions), provided:

  - it is default-off and explicitly enabled via `control_plane.enabled`,
  - the run bundle remains the authoritative coordination and evidence plane (stages still publish
    artifacts via filesystem contracts), and
  - every remote action is recorded into the run bundle as an auditable transcript (inputs, targets,
    results, timestamps, and stable hashes).

## References

- [Stage outcomes and failure classification ADR](ADR-0005-stage-outcomes-and-failure-classification.md)
- [Data contracts specification](../spec/025_data_contracts.md)

## Changelog

| Date       | Change            |
| ---------- | ----------------- |
| 2026-01-12 | Formatting update |
