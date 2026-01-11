<!-- docs/adr/ADR-0004-deployment-architecture-and-inter-component-communication.md -->
# ADR-0004: Deployment architecture and inter-component communication (v0.1)

## Status

Proposed

## Context

Purple Axiom v0.1 specifies a staged pipeline (lab provider, runner, telemetry, normalization, criteria evaluation, detection, scoring, reporting) and a local-first “run bundle” rooted at `runs/<run_id>/`. The specs already define:

- a canonical OpenTelemetry Collector topology (agent tier, optional gateway tier),
- run bundle layout and storage tiers,
- deterministic writing rules for artifacts and datasets.

What is not yet explicit is the intended **deployment model** and the **communication pattern** between pipeline components, which impacts determinism, operability, and implementation choices (single process vs multiple processes, file coordination vs OTLP/RPC between stages).

This ADR defines the normative v0.1 deployment topology and the inter-component communication contract.

## Decision

### 1) Normative v0.1 topology

Purple Axiom v0.1 MUST use a **single-host, local-first** topology with a **one-shot orchestrator** and **file-based stage coordination**.

#### 1.1 Orchestrator (execution plane)

- The pipeline MUST be driven by a single **orchestrator** running on the “run host” (the machine that owns `runs/<run_id>/`).
- The orchestrator MUST run as a **one-shot process per run*- (invoked manually or via external scheduling such as cron or systemd timers).
- The orchestrator SHOULD execute the core pipeline stages **in a single process** for v0.1 (monolith implementation), even if some steps invoke external binaries (executors, collectors, packagers).

Non-goal (v0.1): a required long-running daemon or scheduler control plane.

#### 1.2 Telemetry plane (OpenTelemetry Collector tiers)

- Telemetry collection MUST follow the canonical OTel model:

  - **Agent tier (preferred):** Collector on each endpoint to read OS sources (for example, Windows Event Log with `raw: true`).
  - **Gateway tier (optional):** A collector service that receives OTLP from agents and applies buffering/fan-out.
- OTLP MAY be used between Collector tiers (agent to gateway, gateway to sinks).
- OTLP MUST NOT be required as a coordination mechanism between Purple Axiom’s core stages (runner, normalizer, evaluator, scorer, reporting). Core-stage coordination is file-based.

#### 1.3 Run bundle (coordination and evidence plane)

- The run bundle (`runs/<run_id>/`) is the authoritative coordination substrate for all core stages.
- Stages MUST communicate by reading and writing **contract-backed artifacts** under the run bundle root.
- The manifest (`runs/<run_id>/manifest.json`) MUST remain the authoritative index of what exists and which versions/config hashes were used.

#### 1.4 Optional packaging (Docker Compose)

Docker Compose MAY be provided for ease of installation and home lab setup, but in v0.1 it MUST be treated as packaging only:

- One-shot containers for stages (jobs) writing to a shared volume for `runs/`.
- Optional long-running containers for supporting services (for example, a gateway collector, a read-only UI).
- Compose MUST NOT introduce a distributed control plane that changes stage semantics or determinism guarantees.

### 2) Inter-component communication contract (v0.1)

#### 2.1 Communication patterns

Core stages MUST use one of the following mechanisms, in priority order:

1. **Filesystem artifacts in the run bundle** (required).
2. **Local process invocation** (optional implementation detail).
3. **OTLP within the telemetry plane only** (allowed for collectors, not for stage coordination).

Core stages MUST NOT require service-to-service RPC between runner, normalizer, evaluator, detection, scoring, and reporting in v0.1.

#### 2.2 Stable stage identifiers

Stage outcomes and stage-scoped outputs MUST use stable stage identifiers consistent with the pipeline:

- `lab_provider`
- `runner`
- `telemetry`
- `normalization`
- `validation`
- `detection`
- `scoring`
- `reporting`
- `signing` (when enabled)

Substages MAY be expressed as dotted identifiers (for example, `lab_provider.connectivity`, `telemetry.windows_eventlog.raw_mode`) provided they remain stable and are only additive.

### 3) Stage IO boundaries (normative)

Each stage MUST be implementable as “read inputs from run bundle, write outputs to run bundle.” Implementations MAY structure code internally as functions, classes, or subprocesses, but the observable contract is the filesystem.

Minimum v0.1 IO boundaries:

| Stage           | Minimum inputs                                                        | Minimum outputs (published paths)                                                              |
| --------------- | --------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| `lab_provider`  | configuration (run config, provider inputs)                           | inventory snapshot artifact referenced by manifest                                             |
| `runner`        | inventory snapshot, scenario plan                                     | `ground_truth.jsonl`, `runner/**` evidence                                                     |
| `telemetry`     | inventory snapshot, time window derived from runner                   | `raw_parquet/**` and optional `raw/**` evidence, `logs/telemetry_validation.json` when enabled |
| `normalization` | `raw_parquet/**`, mapping profiles                                    | `normalized/**` (OCSF store), `normalized/mapping_coverage.json`                               |
| `validation`    | `ground_truth.jsonl`, `normalized/**`, criteria pack snapshot         | `criteria/**` results and cleanup verification outputs                                         |
| `detection`     | `normalized/**`, bridge artifacts, sigma packs                        | `bridge/**`, `detections/detections.jsonl`                                                     |
| `scoring`       | `ground_truth.jsonl`, `criteria/**`, `detections/**`, `normalized/**` | `scoring/summary.json` and optional supporting tables                                          |
| `reporting`     | `scoring/**`, `criteria/**`, `detections/**`, manifest                | `report/**` (HTML and any supplemental report artifacts)                                       |
| `signing`       | finalized manifest, selected artifacts                                | `security/**` signature metadata                                                               |

Note: This ADR does not redefine the detailed contracts or schemas for these artifacts. It constrains deployment and inter-stage communication such that existing and future contracts remain implementable and testable.

### 4) Filesystem publish and completion semantics (normative)

To preserve determinism and avoid partial reads:

#### 4.1 Single-writer rule

- For a given `(run_id, stage_id)`, there MUST be at most one writer publishing stage outputs at a time.

#### 4.2 Staging then atomic publish

For any stage that writes a directory or multi-file artifact set:

1. The stage MUST write outputs into a staging location under the run bundle:

   - `runs/<run_id>/.staging/<stage_id>/...`
2. The stage MUST validate required contracts for the outputs it intends to publish (schema validation where applicable).
3. The stage MUST publish outputs by an atomic rename from staging into the final location under `runs/<run_id>/`.
4. If the stage fails before publish, it MUST NOT create or partially populate the final output directory.

#### 4.3 Completion requires outcome recording

A stage MUST be considered complete only when:

- its stage outcome has been recorded in the manifest (and in `logs/health.json` when enabled), and
- its outputs are either:

  - published (for `success` and `warn_and_skip` outcomes), or
  - absent (for `fail_closed` outcomes).

Stage outcome recording and failure classification are defined in a separate ADR (“Stage Outcomes and Failure Classification”).

### 5) Error propagation and partial failures (v0.1)

- The orchestrator MUST derive `manifest.status` from the set of recorded stage outcomes using the normative derivation rules in the data contracts spec.
- Stages configured (or defaulted) as `fail_closed` MUST cause the run to halt and mark downstream stages `skipped`.
- Stages configured as `warn_and_skip` MAY allow the run to continue, but MUST record deterministic degradation evidence (stage outcome plus reason codes and structured logs where defined).

This ADR constrains how failures propagate operationally (halt vs continue) but delegates the specific failure taxonomy and reason-code requirements to the stage outcomes ADR.

## Canonical run sequence (v0.1)

The following sequence is normative at the level of stage ordering and artifact publication.

```text
Orchestrator (one-shot, run host)
  |
  |-- acquire run lock (exclusive writer)
  |-- create runs/<run_id>/ (staging allowed)
  |-- write initial manifest skeleton (run metadata, config hashes)
  |
  |-- [lab_provider] resolve inventory snapshot -> publish inventory artifact -> record stage outcome
  |
  |-- [runner] execute scenario actions -> write ground_truth.jsonl + runner/** -> record stage outcome
  |
  |-- [telemetry] ensure collection window captured + validate canaries -> publish raw_parquet/** and logs/telemetry_validation.json -> record stage outcome
  |
  |-- [normalization] map raw_parquet/** -> normalized/** + mapping_coverage.json -> record stage outcome
  |
  |-- [validation] evaluate criteria packs + cleanup verification -> criteria/** -> record stage outcome
  |
  |-- [detection] compile/evaluate sigma via bridge -> bridge/** + detections/** -> record stage outcome
  |
  |-- [scoring] join ground truth, criteria, detections -> scoring/summary.json -> record stage outcome
  |
  |-- [reporting] generate report/** -> record stage outcome
  |
  |-- [signing] (optional) sign artifacts -> security/** -> record stage outcome
  |
  |-- finalize manifest.status and seal manifest.json
  |-- release run lock
```

## Consequences

### Positive

- Determinism is improved by minimizing concurrency and by making the run bundle the single source of truth for stage coordination.
- Operability is improved because operators can reproduce and debug runs by inspecting a single run bundle tree and manifest.
- Future extensibility remains viable because stage boundaries are defined by stable file contracts, not by in-process implementation details.
- Docker Compose can be introduced as an installation convenience without changing architecture semantics.

### Trade-offs

- v0.1 does not provide a built-in scheduler control plane. Scheduling is external.
- A one-shot orchestrator requires explicit rules for resuming/retrying runs, which are handled via run bundle state, locks, and stage outcomes rather than a daemon database.
- Streaming cross-stage pipelines (service mesh with OTLP between stages) are intentionally deferred due to determinism and safety risk.

## Future options (non-normative)

The following may be added later without breaking v0.1 contracts if the filesystem stage IO boundaries remain stable:

- A “local multi-process” mode where each stage is a separately invocable command, still reading and writing the same run bundle artifact contracts.
- A long-running daemon that schedules runs and maintains a queue, provided:

  - it uses the same lock and atomic publish rules, and
  - UI actions do not bypass contract validation.
- Remote execution runners or distributed collection backends, provided the run bundle still captures a complete, deterministic snapshot of inputs and outputs required for reproducibility.
