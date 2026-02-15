---
title: Operability
description: Defines health signals, validation gates, and operational safeguards for runs.
status: draft
---

# Operability

This document defines operational requirements for health visibility, resource constraints, and
deterministic failure handling. It focuses on the signals and artifacts needed to keep runs
observable and reproducible in unattended lab environments.

Purple Axiom is intended to run continuously, unattended, on local lab infrastructure. Operability
requirements focus on:

- health visibility (did the pipeline run, and where did it fail?)
- bounded resource usage (avoid runaway CPU/RAM/disk)
- reproducibility (same inputs yield comparable outputs)
- failure classification (collector issue vs mapping gap vs detection logic gap)

## Conformance and registry alignment (normative)

- Stage identifiers (`health.json.stages[].stage`) and stage ordering MUST follow the canonical
  stage and substage registry in ADR-0005.
- Stable `reason_code` tokens MUST be drawn from the same registry. If this document introduces a
  new `reason_code`, ADR-0005 MUST be updated in the same change set.
- State machine behaviors (for example: runner lifecycle enforcement and runner state
  reconciliation) SHOULD follow ADR-0007:
  - `logs/health.json` is a stage-outcome surface and MUST NOT be treated as a per-transition event
    log.
  - When per-transition evidence is required for debugging or CI, implementations SHOULD surface it
    via deterministic counters and/or schema-backed evidence artifacts referenced from the manifest.

## Service health model

Each major pipeline stage exposes a minimal health signal and MUST record a stage outcome in the run
manifest. When health files are enabled, the same stage outcomes MUST also be reflected in
`runs/<run_id>/logs/health.json`.

Minimum per-stage health signals (non-exhaustive):

- **Lab Provider (`lab_provider`)**: inventory resolution success, snapshot hash, resolved asset
  count, drift detection (optional).
- **Runner (`runner`)**: scenario execution status, per-action outcomes, cleanup status, lifecycle
  enforcement outcome (when enabled), state reconciliation outcome (when enabled).
- **Telemetry (`telemetry`)**: receiver health, export success, queue depth/drops, checkpoint
  integrity outcome, telemetry validation canary outcomes.
- **Normalization (`normalization`)**: input read completeness, parse errors, mapping coverage.
- **Validation (`validation`)**: criteria pack load success, evaluation coverage, run-limit
  enforcement outcome.
- **Detection (`detection`)**: rule load success, compilation failures, match counts, performance
  budget gate outcome (when enabled).
- **Scoring (`scoring`)**: join completeness, latency distributions.
- **Reporting (`reporting`)**: report generation status, evidence linkage checks, regression
  comparability (when enabled).
- **Signing (`signing`)**: bundle signature generation status and verification (when enabled).

The run manifest reflects the overall outcome (`success`, `partial`, `failed`) and includes
stage-level outcomes and stable `reason_code` tokens used to explain failures and degradations.

## Inventory snapshot (required)

- Each run MUST write `runs/<run_id>/logs/lab_inventory_snapshot.json` as the canonical resolved
  inventory used for that run.
  - This requirement applies to `lab.provider: manual` as well.
- The manifest MUST include, at minimum:
  - provider type (`lab.provider`)
  - snapshot hash (sha256; `lab.inventory_snapshot_sha256`)
  - either:
    - the resolved asset list, or
    - a run-relative pointer to `logs/lab_inventory_snapshot.json`

## Collector observability (required)

The OpenTelemetry Collector MUST expose internal telemetry to support debugging and capacity
planning.

Minimum required endpoints (v0.1):

- health endpoint (health check extension)
- metrics endpoint (Prometheus scrape endpoint, or OTLP metrics to a local backend that is captured
  as run evidence)

Optional lab-only endpoints:

- pprof/zpages for profiling

Minimum collector metrics to track (as time series, per receiver/exporter where applicable):

- received log records per receiver
- exporter send successes/failures
- exporter queue size and queue drops
- memory limiter activation events
- processor dropped spans/logs (if any)
- `otelcol_process_cpu_seconds` (for CPU budget evaluation)
- `otelcol_process_memory_rss` (for memory budget evaluation)

## Resource budgets

The pipeline MUST enforce upper bounds:

- **disk**: per-run max raw retention size `max_raw_bytes_per_run`, per-run max normalized store
  size `max_normalized_bytes_per_run`.
- **Memory**: collector memory limit (via memory limiter) and normalizer process RSS guardrails.
- **CPU**: continuous runs should not starve endpoints; target sustained CPU under a configurable
  threshold.

### Detection evaluation budgets (normative)

To prevent slow detections from creeping in unnoticed, the pipeline MUST support deterministic
performance/footprint budgets for Sigma rule compilation and evaluation. The budget gate MUST be
enforceable without relying on wall-clock time.

Budgets are configured under `detection.sigma.limits` (see `120_config_reference.md`). When any
detection performance budget key is configured (non-null), the pipeline MUST compute the metrics
defined below and write them to `runs/<run_id>/logs/counters.json`.

The pipeline MUST also record a stage outcome entry with:

- `stage: "detection.performance_budgets"`
- `reason_domain: "operability"`
- `status: "success" | "failed"`

If one or more configured budgets are exceeded, the stage outcome MUST be recorded as:

- `status: "failed"`
- `fail_mode: "warn_and_skip"`
- `reason_code: "detection_budget_exceeded"`

If the budget gate is enabled but required metrics are missing (cannot be computed
deterministically), the stage outcome MUST be recorded as:

- `status: "failed"`
- `fail_mode: "fail_closed"`
- `reason_code: "detection_budget_metrics_missing"`

#### Required deterministic metrics (counters.json)

When the budget gate is enabled, the following counters MUST be emitted in `logs/counters.json`.

- `detection_sigma_rules_compiled_total` (rules compiled, regardless of executable status)

- `detection_sigma_predicate_ast_op_nodes_total` (sum across compiled, executable rules)

- `detection_sigma_predicate_ast_op_nodes_max` (max across rules)

- `detection_sigma_compile_cost_units_total`

- `detection_sigma_compile_cost_units_max`

- `detection_sigma_candidate_events_total` (sum of per-rule candidate event counts)

- `detection_sigma_candidate_events_max` (max per-rule candidate event count)

- `detection_sigma_eval_cost_units_total`

- `detection_sigma_eval_cost_units_max`

- `detection_sigma_budget_violation_rules_total` (number of rules that violated any configured
  per-rule budget)

- `detection_sigma_budget_violation_total` (number of violated budget checks across all configured
  budgets)

Optional (recommended) plan complexity counters:

- `detection_sigma_predicate_ast_max_depth_max`
- `detection_sigma_predicate_ast_regex_nodes_max`

#### Metric definitions (normative)

- `predicate_ast_op_nodes_per_rule` counts **operator nodes** in the compiled plan predicate AST
  (`pa_eval_v1`) as defined in `065_sigma_to_ocsf_bridge.md`.
- `candidate_events_per_rule` is the number of normalized events in the run whose `class_uid` is in
  the rule's `backend.plan.scope.class_uids`. Implementations MAY compute this from a per-class
  count index; otherwise they MUST compute it by scanning the normalized store.
- `compile_cost_units_per_rule` is defined as `predicate_ast_op_nodes_per_rule` (v0.1).
- `eval_cost_units_per_rule` is defined as
  `predicate_ast_op_nodes_per_rule * candidate_events_per_rule` (v0.1).

Totals are sums across rules. Max values are maxima across rules.

### EPS baselines (planning targets; v0.1)

Purple Axiom uses EPS (events per second) targets to (a) size collectors and (b) define the
“footprint within configured budgets at target event rate” gate in telemetry validation.

Definitions:

- `sustained_eps_target`: 10-minute rolling average EPS (per asset, aggregated across enabled
  telemetry sources).
- `burst_eps_target_p95_1m`: 95th percentile of 1-minute EPS windows during the same 10-minute
  interval.

Planning baseline targets (initial defaults; operators SHOULD replace with measured baselines for
their lab). Empirical measurement methodology and guidance for replacing these defaults is defined
in [R-04 EPS baseline quantification](../research/R-04_EPS_baseline_quantification.md):

| Asset role                | Telemetry profile                                               | Sustained EPS target | Burst EPS target (p95 1m) | Collector CPU target (p95) | Collector RSS target (p95) | Raw write estimate (MiB/s)† |
| ------------------------- | --------------------------------------------------------------- | -------------------: | ------------------------: | -------------------------: | -------------------------: | --------------------------: |
| Windows endpoint          | Windows Event Log (Application + Security + Sysmon)             |                   50 |                       150 |             ≤ 5% of 1 vCPU |                  ≤ 350 MiB |                     0.1–0.9 |
| Windows domain controller | Windows Event Log (Application + Security + Directory Services) |                  300 |                      1000 |            ≤ 10% of 1 vCPU |                  ≤ 700 MiB |                     0.6–6.0 |
| Linux server              | auditd + osquery (evented + scheduled)                          |                  100 |                       300 |             ≤ 5% of 1 vCPU |                  ≤ 512 MiB |                     0.2–1.8 |

† Raw write estimate assumes 2–6 KiB average serialized event payload per record and is intended
only for order-of-magnitude disk sizing. Implementations MUST measure and report observed raw bytes
per second during validation.

#### EPS baseline artifact (recommended)

Implementations that perform EPS baseline quantification (for example, to tune or replace the
planning defaults above) SHOULD write `runs/<run_id>/logs/eps_baseline.json`.

`eps_baseline.json` MUST be treated as an analytical artifact and MUST NOT affect run status. When
present, it MUST include, at minimum:

- `schema_version` (string; MUST be `pa:eps_baseline:v1`)
- `asset_role` (string; MUST match the asset role used for target resolution)
- `time_window`:
  - `warmup_seconds` (integer)
  - `sustained_window_seconds` (integer; MUST be `600`)
  - `burst_window_seconds` (integer; MUST be `60`)
- `eps`:
  - `sustained_mean` (number)
  - `burst_p95_1m` (number)
- `resources`:
  - `cpu_p95_pct` (number)
  - `rss_p95_bytes` (integer)
- `disk`:
  - `raw_bytes_written_total` (integer)
  - `normalized_bytes_written_total` (integer)
- `inputs`:
  - `scenario_id` (string)
  - `atomic_tests` (array of strings; MUST be sorted by UTF-8 byte order)

Measurement methodology and replacement criteria are defined in
[R-04 EPS baseline quantification](../research/R-04_EPS_baseline_quantification.md).

Normative requirements:

- Telemetry validation MUST treat these values as planning defaults only; operators MAY override
  them via configuration or asset-specific profiles.
- The validator SHOULD record observed EPS and footprint statistics (CPU, RSS, raw bytes/sec) for
  each validated asset to make regressions and sizing errors detectable.
  - Measurement methodology is specified in the
    [telemetry pipeline specification](040_telemetry_pipeline.md) §2 "Performance and footprint
    controls (agent)".

Budgets are configuration-driven and enforced deterministically during telemetry validation.

- For telemetry validation, missing required budget configuration or missing required measurements
  MUST fail closed with stable reason codes (see "Telemetry validation (gating)" and "Resource
  budget quality gate (validation)").
- For other stages, budgets MAY be surfaced in reports without failing the run, but any such
  non-telemetry budget reporting MUST NOT change the run status unless explicitly specified by this
  document.

## Resiliency and backpressure

Expect backpressure and partial failures:

- Exporters may block or fail transiently.
- Collector restarts and at-least-once delivery are normal in labs.

Practices:

- Use batching and bounded queues in collectors.
- Prefer explicit drops with counters over unbounded memory growth.
- Ensure downstream dedupe can tolerate duplicates created by collector restart/retry.

## Checkpointing and dedupe observability (normative)

To support debugging and CI verification, implementations MUST emit the following counters/gauges
per run (at minimum into `runs/<run_id>/logs/counters.json` and optionally into metrics backends):

- `telemetry_records_received_total`
- `telemetry_records_written_total`
- `telemetry_records_skipped_total`
- `telemetry_checkpoints_written_total`
- `telemetry_checkpoint_loss_total`
- `telemetry_checkpoint_corruption_total`
- `dedupe_duplicates_dropped_total`
- `dedupe_conflicts_total`

### Counter artifact format (normative)

`runs/<run_id>/logs/counters.json` MUST be a JSON object with:

- `contract_version` (string; schema constant; see contract registry)
- `schema_version` (string; MUST be `pa:counters:v1`)
- `run_id` (string)
- `generated_at_utc` (string; RFC 3339 UTC timestamp)
- `counters` (object; map of counter name → u64)
- `gauges` (optional object; map of gauge name → number)

Determinism requirements:

- The emitted JSON serialization MUST sort `counters` keys by UTF-8 byte order (no locale).
- When present, the emitted JSON serialization MUST sort `gauges` keys by UTF-8 byte order (no
  locale).

Unless explicitly stated otherwise, all per-run counters and gauges required by this document MUST
be emitted into this file.

Implementations SHOULD also record:

- dedupe index location and size (bytes)
- checkpoint directory location
- replay start mode used on restart (`resume | reset_missing | reset_corrupt | reset_manual`)

Replay start mode definitions (normative):

- `resume`: checkpoint existed and was used.
- `reset_missing`: checkpoint missing; replay expected.
- `reset_corrupt`: checkpoint corrupt and recovery was applied (fresh state); replay expected.
- `reset_manual`: operator explicitly requested reset (ignore checkpoints).

### Counter presence and zero semantics (normative)

This document distinguishes between:

- always-required per-run counters (listed unconditionally), and
- feature-conditional counter groups (introduced with "when <feature> is enabled" or "when
  <artifact> is produced").

Rules:

- Always-required counters MUST be emitted for every run. If a behavior is disabled or does not
  occur, the counter MUST be present with value `0`.

- Feature-conditional counter groups MUST follow "omit vs zero" semantics:

  - If the feature is disabled for the run and the corresponding schema-backed artifact is not
    produced, the counters in that feature group MUST be omitted.
  - If the feature is enabled for the run, the counters in that feature group MUST be present. If no
    qualifying events occurred, the counters MUST be present with value `0`.
  - If a counter is explicitly marked optional (for example, `cache_provenance_bypassed_total`),
    implementations MAY omit it even when the feature is enabled; consumers MUST treat omission as
    value `0`.

### Telemetry ETL counter semantics (normative)

This counter group provides a stable "stats aggregation" surface for telemetry+ETL.

Definitions (normative):

- **received**: a telemetry record accepted by the pipeline from collectors (after any
  collector-side retry/replay behavior, before raw-store write decisions).
- **written**: a received record that is persisted into the run's raw telemetry store.
- **skipped**: a received record that is intentionally not written to the raw store under
  `fail_mode=warn_and_skip` due to a deterministic validation/QC failure (for example
  `RAW_XML_UNAVAILABLE`).

Requirements (normative):

- `telemetry_records_received_total` MUST increment exactly once per received record.
- `telemetry_records_written_total` MUST increment exactly once per record written to the raw store.
- `telemetry_records_skipped_total` MUST increment exactly once per skipped record.
- For any run, `telemetry_records_received_total` MUST equal
  `telemetry_records_written_total + telemetry_records_skipped_total`.

### Windows Event Log raw XML counters (when Windows Event Log is enabled) (normative)

When Windows Event Log collection is enabled for any asset in the run, implementations MUST emit the
following additional counters (u64). These counters are feature-conditional:

- If Windows Event Log collection is disabled for the run, these counters MUST be omitted.
- If Windows Event Log collection is enabled for the run, these counters MUST be present (zero when
  not observed).

Counters (normative):

- `wineventlog_raw_unavailable_total`
- `wineventlog_raw_malformed_total`
- `wineventlog_used_log_record_original_total`
- `wineventlog_rendering_metadata_missing_total`
- `wineventlog_binary_decode_failed_total`
- `wineventlog_payload_overflow_total`
- `wineventlog_sidecar_write_failed_total`

Semantics (normative):

- The `wineventlog_*` counters MUST follow the definitions in
  [Raw or unrendered Windows Event Log failure modes](040_telemetry_pipeline.md#raw-or-unrendered-windows-event-log-failure-modes).
- Under `fail_mode=warn_and_skip`, records counted by `wineventlog_raw_unavailable_total` or
  `wineventlog_raw_malformed_total` MUST also increment `telemetry_records_skipped_total`.

Conformance tests (normative):

- CI MUST include a counters fixture where Windows Event Log is enabled and all `wineventlog_*`
  counters are present (including zero values).
- CI MUST include a counters fixture where Windows Event Log is disabled and `wineventlog_*`
  counters are omitted.

### Additional stable counters (principal context, cache provenance, dependency immutability) (normative)

In addition to the checkpointing and dedupe counters above, implementations MUST emit the following
stable per-run counters (u64) when the corresponding feature is enabled. Where a feature produces a
schema-backed artifact, the counters are conditional on that artifact being produced.

Principal context (when `runs/<run_id>/runner/principal_context.json` is produced):

- `runner_principal_context_total`
- `runner_principal_context_known_total`
- `runner_principal_context_unknown_total`

Cache provenance (when `runs/<run_id>/logs/cache_provenance.json` is produced):

- `cache_provenance_hit_total`
- `cache_provenance_miss_total`
- `cache_provenance_bypassed_total` (optional; recommended)

Dependency mutation blocked (when dependency immutability enforcement is enabled):

- `runner_dependency_mutation_blocked_total`

#### Counter semantics (normative)

Principal context:

- `runner_principal_context_total` MUST equal the number of entries in
  `principal_context.principals[]`.
- `runner_principal_context_unknown_total` MUST equal the number of entries in
  `principal_context.principals[]` with `kind=unknown`.
- `runner_principal_context_known_total` MUST equal the number of entries in
  `principal_context.principals[]` whose `kind != unknown`.

Cache provenance:

- `cache_provenance_hit_total` MUST equal the number of `cache_provenance.entries[]` with
  `result=hit`.
- `cache_provenance_miss_total` MUST equal the number of `cache_provenance.entries[]` with
  `result=miss`.
- `cache_provenance_bypassed_total` (when emitted) MUST equal the number of
  `cache_provenance.entries[]` with `result=bypassed`.

Dependency mutation blocked:

- `runner_dependency_mutation_blocked_total` MUST increment once per runner-side dependency mutation
  attempt that is blocked under the effective policy (for example, a runtime self-update attempt
  that is refused).

## State reconciliation observability (normative)

When state reconciliation is enabled, implementations MUST emit both:

1. A `health.json.stages[]` entry with:

   - `stage: "runner.state_reconciliation"`

   Tuple alignment (normative):

   - The emitted `runner.state_reconciliation` substage `fail_mode` MUST be policy-controlled via
     the runner stage `fail_mode` (see ADR-0005).

   Required substage semantics (v0.1):

   - status is `failed` with `reason_code=reconcile_failed` when one or more actions' reconciliation
     cannot be completed deterministically.
   - otherwise, status is `failed` with `reason_code=drift_detected` when drift is detected for one
     or more actions.
   - otherwise, status is `success` (and MUST omit `reason_code`).

   Deterministic reason selection (normative):

   - If any action's reconciliation cannot be completed deterministically, the substage
     `reason_code` MUST be `reconcile_failed`.
   - Else if any drift is detected, the substage `reason_code` MUST be `drift_detected`.
   - Else, the substage MUST be `status=success` and MUST omit `reason_code`.

   Default run status mapping (normative):

   - If the runner stage `fail_mode=fail_closed`, the run MUST be marked `failed` when this substage
     is recorded as `status=failed`.
   - If the runner stage `fail_mode=warn_and_skip`, the run MAY be marked `partial` when this
     substage is recorded as `status=failed`.

   Reason codes (stable tokens, v0.1):

   - `drift_detected`
   - `reconcile_failed`

1. Stable per-run counters (at minimum into `runs/<run_id>/logs/` and optionally into a metrics
   backend):

   - `runner_state_reconciliation_items_total`
   - `runner_state_reconciliation_drift_detected_total`
   - `runner_state_reconciliation_skipped_total`
   - `runner_state_reconciliation_unknown_total`
   - `runner_state_reconciliation_probe_error_total`
   - `runner_state_reconciliation_repairs_attempted_total`
   - `runner_state_reconciliation_repairs_succeeded_total`
   - `runner_state_reconciliation_repairs_failed_total`
   - `runner_state_reconciliation_repair_blocked_total`

   v0.1 repair constraints (normative):

   - v0.1 implementations MUST NOT attempt destructive repair as part of reconciliation.
   - Therefore, the following counters MUST be zero for v0.1 runs:
     - `runner_state_reconciliation_repairs_attempted_total`
     - `runner_state_reconciliation_repairs_succeeded_total`
     - `runner_state_reconciliation_repairs_failed_total`
   - If a run requests repair (scenario policy or future config) but repair is not
     enabled/supported, implementations MUST increment
     `runner_state_reconciliation_repair_blocked_total`.

### Counter semantics (normative):

- `items_total` MUST count reconciliation items emitted across all action reports for the run.
- `drift_detected_total` MUST count items where observed state mismatched the recorded expectation.
- `skipped_total` MUST count items not probed due to policy or missing deterministic probe targets.
- `unknown_total` MUST count items with indeterminate outcomes (probe executed but result could not
  be classified deterministically).
- `probe_error_total` MUST count probe executions that returned an error (timeout, auth failure, API
  error), regardless of whether an item is later classified as `unknown`.

### Runner lifecycle enforcement observability (normative)

When the runner enforces lifecycle transition guards and rerun-safety rules, it MUST emit both:

1. A `health.json.stages[]` substage outcome with:

   - `stage: "runner.lifecycle_enforcement"`

   Required semantics (v0.1):

   - status is `success` if no invalid transitions or unsafe re-runs were attempted.
   - status is `failed` with `fail_mode=warn_and_skip` if unsafe behavior was blocked but the run
     can proceed safely.
   - status is `failed` with `fail_mode=fail_closed` only when the configured policy requires abort.

   Reason codes (stable tokens, v0.1):

   - `invalid_lifecycle_transition`
   - `unsafe_rerun_blocked`

   Deterministic reason selection:

   - If any unsafe reruns occurred (even if invalid transitions also occurred):
     `unsafe_rerun_blocked`
   - Else (only invalid transitions occurred): `invalid_lifecycle_transition`

1. Stable per-run counters (at minimum into `runs/<run_id>/logs/counters.json` and optionally into a
   metrics backend):

   - `runner_invalid_lifecycle_transition_total` (u64): count of invalid transitions attempted and
     blocked.
   - `runner_unsafe_rerun_blocked_total` (u64): count of unsafe reruns attempted and blocked.

## Telemetry validation (gating)

A telemetry stage is only considered "validated" for an asset when a validation run produces the
required raw telemetry for the enabled sources on that asset. For Windows assets with Windows Event
Log collection enabled, this includes:

- raw Windows Event Log events captured in raw/unrendered mode
  - verified by a runtime canary:
    - captured XML begins with `<Event`
    - the `<System>` stanza includes:
      - `<Channel>` (correct channel)
      - `<Provider Name="...">` (optional requirement, when provider pinned)
      - `<EventID>` (optional requirement, when pinned)
  - canary should be observed at a deterministic path such as:
    - `runs/<run_id>/raw/<asset_id>/windows_eventlog/<channel>/...` (implementation-defined file
      name, but stable)

Additional normative checks:

- `runs/<run_id>/logs/telemetry_validation.json` MUST include a `capture_window` object with
  explicit start/end timestamps and any correlation marker strategy used for joins between layers.
  - Required fields: `capture_window.start_time_utc`, `capture_window.end_time_utc`.
  - If `runner.atomic.synthetic_correlation_marker.enabled=true`,
    `capture_window.correlation_marker_strategy` MUST describe the synthetic marker join surface
    (ground truth carrier: `extensions.synthetic_correlation_marker`; normalized carrier:
    `metadata.extensions.purple_axiom.synthetic_correlation_marker`).
- The validator MUST emit a `health.json.stages[]` entry with `stage: "telemetry.agent.liveness"`.
  - The validator MUST treat collector self-telemetry as the OS-neutral heartbeat for each asset
    with `telemetry.otel.enabled=true` (see the telemetry pipeline specification).
  - If no heartbeat is observed for one or more expected assets within
    `telemetry.otel.agent_liveness.startup_grace_seconds` from the start of the telemetry window
    (`telemetry_validation.capture_window.start_time_utc`), the stage MUST be `status=failed`,
    `fail_mode=fail_closed`, `reason_code=agent_heartbeat_missing`.
  - The validator MUST record per-asset liveness evidence in
    `runs/<run_id>/logs/telemetry_validation.json` under `agent_liveness`.
- The validator MUST emit a `health.json.stages[]` entry with
  `stage: "telemetry.windows_eventlog.raw_mode"`.
- When `telemetry.baseline_profile.enabled=true`, the validator MUST emit a `health.json.stages[]`
  entry with `stage: "telemetry.baseline_profile"`.
  - The validator MUST evaluate the contract-backed baseline profile snapshot at
    `runs/<run_id>/inputs/telemetry_baseline_profile.json` (see `040_telemetry_pipeline.md`).
  - If the profile is missing or unreadable, the stage MUST be `status=failed`,
    `fail_mode=fail_closed`, `reason_code=baseline_profile_missing`.
  - If the profile fails contract validation, the stage MUST be `status=failed`,
    `fail_mode=fail_closed`, `reason_code=baseline_profile_invalid`.
  - If one or more required baseline signals are not observed for one or more assets in the
    validation window, the stage MUST be `status=failed`, `fail_mode=fail_closed`,
    `reason_code=baseline_profile_not_met`.
  - The validator MUST record per-asset baseline profile evidence in
    `runs/<run_id>/logs/telemetry_validation.json` under `baseline_profile`.
- When collector checkpoint corruption prevents the collector from starting, the validator MUST emit
  a `health.json.stages[]` entry with `stage: "telemetry.checkpointing.storage_integrity"` and
  `reason_code=checkpoint_store_corrupt`.
- When automatic checkpoint corruption recovery is enabled and observed (fresh DB created), the
  validator SHOULD emit the same stage with `status=success` and record replay start mode
  `reset_corrupt` in `telemetry_validation.json`.
- When the raw-mode canary check fails, `reason_code` MUST be one of:
  - `winlog_raw_missing` (no raw XML captured for the canary event)
  - `winlog_rendering_detected` (`<RenderingInfo>` present in the captured payload)
- The validator MUST record where the canary was observed so operators can reproduce the check
  without guesswork.
  - `runs/<run_id>/logs/telemetry_validation.json` MUST include a
    `windows_eventlog_raw_mode.canary_observed_at` object with, at minimum:
    - `asset_id` (string)
    - `channel` (string)
    - `path` (string; run-relative path to the concrete raw artifact or dataset file)
  - `canary_observed_at.path` MUST use POSIX-style separators (`/`) and MUST be interpreted as
    relative to `runs/<run_id>/`.
  - Example (illustrative only): `raw/<asset_id>/windows_eventlog/<channel>/...` or
    `raw_parquet/windows_eventlog/part-00000.parquet`.
  - If the canary is observed in a Parquet dataset, the validator SHOULD also include a minimal
    `row_locator` (for example, `event_record_id` and `provider`) sufficient to re-query the dataset
    deterministically.
- outbound egress deny posture enforcement (required when effective outbound policy is denied):
  - The validator MUST compute `effective_allow_outbound` as the logical AND of:
    - `scenario.safety.allow_network`(from the pinned scenario definition snapshot under
      `inputs/scenario.yaml`), and
    - `security.network.allow_outbound` from the pinned range configuration snapshot under
      `inputs/range.yaml`.
  - When `effective_allow_outbound=false`, the validator MUST run a TCP connect canary from the
    target asset to `security.network.egress_canary`.
    - The canary MUST be considered enabled when `security.network.egress_canary.required_on_deny`
      is `true` (default) and effective outbound policy is denied.
    - When the canary is enabled but `security.network.egress_canary` is missing or incomplete, the
      run MUST fail closed.
  - The validator MUST emit a `health.json.stages[]` entry with
    `stage: "telemetry.network.egress_policy"`.
  - When the egress canary check fails, `reason_code` MUST be one of:
    - `egress_canary_unconfigured` (no canary endpoint configured when required)
    - `egress_probe_unavailable` (probe could not be executed on the asset)
    - `egress_violation` (probe succeeded despite deny policy)
  - The validator MUST record deterministic evidence in
    `runs/<run_id>/logs/telemetry_validation.json` under `network_egress_policy` with, at minimum:
    - `asset_id` (string)
    - `effective_allow_outbound` (bool)
    - `canary` (object):
      - `address` (string; literal IP address)
      - `port` (int)
      - `timeout_ms` (int)
    - `probe_observed` (object):
      - `outcome` (one of `blocked | reachable | error`)
      - `error_code` (optional string; ASCII `lower_snake_case` when present)
  - A `reachable` outcome when `effective_allow_outbound=false` MUST fail the run (fail closed).
- disk capacity preflight (hard fail / fail closed) before the validation window begins:
  - The validator MUST compute `free_bytes_at_runs_root` for the filesystem containing the resolved
    runs root directory (the directory that contains `runs/<run_id>/`; typically
    `reporting.output_dir`).
  - `free_bytes_at_runs_root` MUST use the OS "bytes available to the current user" API (for
    example, POSIX `statvfs.f_bavail * f_frsize` or Windows `GetDiskFreeSpaceEx`'s
    `FreeBytesAvailable`).
  - The validator MUST compute:
    - `disk_headroom_bytes` (default `2147483648` (2 GiB) unless configured)
    - `required_free_bytes = max_raw_bytes_per_run + max_normalized_bytes_per_run + disk_headroom_bytes`
  - If `free_bytes_at_runs_root < required_free_bytes`, the run MUST fail closed:
    - `health.json` stage: `telemetry.disk.preflight`
    - `status=failed`, `fail_mode=fail_closed`, `reason_code=disk_free_space_insufficient`
    - run status: `failed`
  - If any required value cannot be computed deterministically (including missing paths/permissions,
    unsupported platform API, or unknown/unset disk budget inputs), the run MUST fail closed with
    stable reason code:
    - `reason_code=disk_metrics_missing`
  - The validator MUST record `free_bytes_at_runs_root`, `required_free_bytes`, and the three inputs
    used to compute it in `telemetry_validation.json` for deterministic debugging.
- stable parsing of required identity fields (channel, provider, record id)
- successful parsing when rendered message strings are missing (manifest/publisher metadata failures
  must not be fatal)
- no unbounded growth under exporter throttling
- footprint within configured budgets at target event rate
- payload limits enforced and observable:
  - oversized `event_xml` produces `event_xml_truncated=true` plus `event_xml_sha256`
  - binary fields honor `max_binary_bytes` and produce deterministic
    `binary_present/binary_oversize` signals

### Resource budget quality gate (validation)

The telemetry validator MUST evaluate collector footprint against configured budget targets during
the same steady-state window used to compute sustained EPS.

This section defines the fail semantics for the "footprint within configured budgets at target event
rate" gate and provides deterministic run outcome mapping when budgets are exceeded.

#### Inputs (normative)

Configured targets (per validated asset):

- `cpu_target_p95_pct` (number): maximum allowed p95 CPU percent for the steady-state window.
  - CPU percent MUST be computed as:
    - `cpu_pct = rate(otelcol_process_cpu_seconds[1m]) * 100`
- `rss_target_p95_bytes` (integer): maximum allowed p95 RSS bytes for the steady-state window.

Target resolution (v0.1):

- If an explicit per-asset footprint budget is configured, the validator MUST use it.
- Otherwise, the validator MUST use the planning defaults in
  [EPS baselines](#eps-baselines-planning-targets-v01) for the asset's `role`.
- If neither applies, the validator MUST fail closed with
  `reason_code=resource_budgets_unconfigured`.

Required measurements (per asset):

- A 10-minute steady-state window where `sustained_eps_observed >= sustained_eps_target`.
- `cpu_pct_p95` and `rss_bytes_p95` computed over that same window.
- queue-pressure evidence over that same window (drops/limiter activations as defined below).

If the required measurements cannot be computed (missing collector self-telemetry, missing EPS
series, or the sustained EPS target was not met), the validator MUST fail closed with
`reason_code=resource_metrics_missing` or `reason_code=eps_target_not_met`.

#### Queue pressure evaluation (normative)

Queue pressure is considered present when any of the following are observed during the steady-state
window:

- exporter queue drops > 0
- processor dropped logs/spans > 0
- memory limiter activation events > 0

Queue pressure detection MUST be deterministic: any non-zero value for any of the above signals
within the window is sufficient to treat queue pressure as present.

#### Tolerance and evaluation (normative)

To reduce false negatives from measurement noise, budget enforcement uses a deterministic tolerance.

Defaults (v0.1):

- CPU tolerance: `max(1.0 percentage point, 10% of cpu_target_p95_pct)`
- RSS tolerance: `max(64 MiB, 10% of rss_target_p95_bytes)`

A budget is considered exceeded when:

- `cpu_pct_p95 > cpu_target_p95_pct + cpu_tolerance`
- `rss_bytes_p95 > rss_target_p95_bytes + rss_tolerance`
- queue pressure is present (as defined in "Queue pressure evaluation (normative)")

#### Health accounting and outcomes (normative)

The validator MUST emit a `health.json.stages[]` entry with `stage: "telemetry.resource_budgets"`.

Outcome mapping (quality gate semantics):

- If no budgets are exceeded, the stage MUST be `status=success`.
- If one or more budgets are exceeded, the stage MUST be `status=failed` with
  `fail_mode=warn_and_skip`, and the overall run `manifest.status` MUST be `partial` unless it is
  already `failed` for another reason.

Reason codes (stable tokens):

- `resource_budget_cpu_exceeded`
- `resource_budget_memory_exceeded`
- `resource_budget_queue_pressure`
- `resource_budgets_unconfigured` (fail-closed)
- `resource_metrics_missing` (fail-closed)
- `eps_target_not_met` (fail-closed)

Reason code selection (normative):

Let `exceeded` be the set of exceeded budget dimensions across: `cpu`, `memory`, `queue_pressure`.

- If `exceeded` is empty, `status=success`.
- If `exceeded` contains `queue_pressure`, use `resource_budget_queue_pressure`.
- Else if `exceeded` contains `memory`, use `resource_budget_memory_exceeded`.
- Else (only `cpu` remains), use `resource_budget_cpu_exceeded`.

The validator SHOULD record the observed p95 values, targets, tolerances, the window definition, and
queue pressure evidence in `runs/<run_id>/logs/telemetry_validation.json` to make regressions
reviewable.

The validator MUST write `runs/<run_id>/logs/telemetry_validation.json`, conforming to the
[telemetry validation schema](../contracts/telemetry_validation.schema.json); the manifest SHOULD
include a pointer to it.

#### Deterministic disk accounting (recommended; non-gating)

The validator SHOULD compute `raw_bytes_written_total` and `normalized_bytes_written_total`
deterministically (for reporting and capacity planning), but these totals MUST NOT affect run status
in v0.1.

If computed, they SHOULD be recorded in `runs/<run_id>/logs/telemetry_validation.json`.

Deterministic disk measurement rules (recommended):

- Use OS-reported logical file sizes (not allocated blocks).
- Enumeration MUST be recursive.
- Symlinks MUST NOT be followed.
- If a required directory cannot be read/enumerated deterministically, the implementation SHOULD
  omit the totals and record a structured measurement error in `telemetry_validation.json` (and
  continue).

## Health files (normative, v0.1)

When `operability.health.emit_health_files=true`, the pipeline MUST write
`runs/<run_id>/logs/health.json`.

`health.json` MUST include, at minimum:

- `run_id` (string)
- `status` (`success | partial | failed`)
- `stages` (array), where each entry includes:
  - `stage` (string; stable identifier)
  - `status` (`success | failed | skipped`)
  - `fail_mode` (`fail_closed | warn_and_skip`)
  - `reason_code` (optional string; stable token)

Determinism requirements:

- `stages[]` MUST be ordered deterministically using the canonical pipeline stage order:
  `lab_provider`, `runner`, `telemetry`, `normalization`, `validation`, `detection`, `scoring`,
  `reporting`, `signing`.
  - Substage entries of the form `<stage>.<substage>` MUST appear immediately after their parent
    stage entry.
  - Within the substage group for a given parent stage, entries MUST be sorted by full `stage`
    string using UTF-8 byte order (no locale).
- `health.json.status` MUST equal `manifest.status` for the same run.

## Process exit codes (normative, v0.1)

For a one-shot pipeline invocation, the process exit code MUST be:

- `0` when `manifest.status=success`
- `10` when `manifest.status=partial`
- `20` when `manifest.status=failed`

## Incident-style debugging workflow

When a run is `partial` or `failed`, prefer this order:

1. Confirm the collector is alive and exporting (health endpoint, exporter counters).
1. Validate raw event presence in `raw/` for the asset and time window.
1. Inspect normalizer parse/mapping errors and mapping coverage deltas.
1. Only then inspect rule logic and scorer joins.

This prevents "rule debugging" when the root cause is missing telemetry.

## Run limit enforcement (normative)

When run limits are configured (see `operability.run_limits` in the
[configuration reference](120_config_reference.md)), the pipeline MUST behave as follows:

| Limit             | Exceeded behavior                                               | Run status impact     | Exit code    | Accounting required                            |
| ----------------- | --------------------------------------------------------------- | --------------------- | ------------ | ---------------------------------------------- |
| `max_run_minutes` | stop pipeline, mark `failed`                                    | `failed`              | `20`         | `validation.run_limits: run_timeout`           |
| `max_disk_gb`     | stop pipeline, mark `partial` (default) or `failed` (hard mode) | `partial` or `failed` | `10` or `20` | `validation.run_limits: disk_limit_exceeded`   |
| `max_memory_mb`   | stop pipeline, mark `failed`                                    | `failed`              | `20`         | `validation.run_limits: memory_limit_exceeded` |

Additionally, when the pipeline process is killed by the OS OOM killer, the pipeline (or supervising
orchestrator) MUST record `validation.run_limits: oom_killed`, mark the run `failed`, and use exit
code `20`.

Fail mode mapping (normative):

- For `max_run_minutes` and `max_memory_mb`, `validation.run_limits.fail_mode` MUST be
  `fail_closed`.
- For `max_disk_gb`, `validation.run_limits.fail_mode` MUST be:
  - `warn_and_skip` when disk limit behavior is default (graceful stop → `partial`), and
  - `fail_closed` when disk limit behavior is configured as hard-fail (stop → `failed`).

The pipeline MUST record run-limit enforcement outcomes in `logs/health.json` (stage:
`validation.run_limits`) and in `manifest.json` stage outcomes.

Disk limit configurability (normative):

- If `operability.run_limits.disk_limit_behavior=hard_fail`, exceeding `max_disk_gb` MUST produce
  `failed` (exit code `20`) instead of `partial`.
- Regardless of behavior, the report output MUST explicitly state which stages were truncated and
  the time window captured.

Disk enforcement during telemetry validation is defined in:

- "Telemetry validation (gating)" (disk capacity preflight; fail closed), and
- "Resource budget quality gate (validation)" (collector CPU/memory/queue pressure gate;
  warn-and-skip / partial).

Disk exhaustion prevention during any stage is enforced by `operability.run_limits.max_disk_gb`
(run-limit stop behavior).

`operability.run_limits.max_disk_gb` is a separate runtime safeguard (stop/truncate behavior) and
MUST NOT be treated as equivalent to the per-run sizing budgets.

Minimum accounting fields (normative):

Each entry in `manifest.extensions.operability.limits_exceeded[]` MUST include:

- `limit` (one of `max_run_minutes|max_disk_gb|max_memory_mb`)
- `configured` (numeric)
- `observed` (numeric)
- `behavior` (`partial|hard_fail`)
- `stage` (stable stage identifier)
- `truncated_at_utc` (ISO-8601, required for disk truncation)

## References

- [Telemetry pipeline specification](040_telemetry_pipeline.md)
- [R-04 EPS baseline quantification](../research/R-04_EPS_baseline_quantification.md)
- [Configuration reference](120_config_reference.md)
- [Telemetry validation schema](../contracts/telemetry_validation.schema.json)

## Changelog

| Date       | Change                                                        |
| ---------- | ------------------------------------------------------------- |
| 2026-01-21 | update                                                        |
| 2026-01-13 | Add EPS baseline link and eps_baseline.json artifact contract |
| 2026-01-13 | Add network egress canary to telemetry validation gating      |
| 2026-01-12 | Formatting update                                             |
