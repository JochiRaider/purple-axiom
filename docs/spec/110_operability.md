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

## Service health model

Each major stage exposes a minimal health signal:

- **Lab Provider**: inventory resolution success, snapshot hash, resolved asset count, drift
  detection (optional).
- **Runner**: scenario execution status, per-action outcomes, cleanup status.
- **Telemetry (collector)**: receiver health, export success, queue depth, dropped counts.
- **Normalizer**: input read completeness, parse errors, mapping coverage.
- **Evaluator**: rule load success, compilation failures, match counts.
- **Scoring**: join completeness, latency distributions.

The run manifest reflects the overall outcome (`success`, `partial`, `failed`) and includes
stage-level failure reasons.

## Inventory snapshot (required when provider != manual)

- Each run SHOULD write `runs/<run_id>/logs/lab_inventory_snapshot.json` as the canonical resolved
  inventory used for that run.
- The manifest SHOULD include:
  - provider type
  - snapshot hash (sha256)
  - resolved asset list (or a pointer to the snapshot)

## Collector observability (required)

The OpenTelemetry Collector should expose internal telemetry to support debugging and capacity
planning:

- health endpoint (health check extension)
- metrics endpoint (Prometheus, or OTLP metrics to a local backend)
- optional pprof/zpages for profiling in the lab

Minimum collector metrics to track:

- received log records per receiver
- exporter send successes/failures
- queue size and queue drops
- memory limiter activation events
- processor dropped spans/logs (if any)

## Resource budgets

The pipeline MUST enforce upper bounds:

- **disk**: per-run max raw retention size `max_raw_bytes_per_run`, per-run max normalized store size
  `max_normalized_bytes_per_run`.
- **Memory**: collector memory limit (via memory limiter) and normalizer process RSS guardrails.
- **CPU**: continuous runs should not starve endpoints; target sustained CPU under a configurable
  threshold.

### EPS baselines (planning targets; v0.1)

Purple Axiom uses EPS (events per second) targets to (a) size collectors and (b) define the
“footprint within configured budgets at target event rate” gate in telemetry validation.

Definitions:

- `sustained_eps_target`: 10-minute rolling average EPS (per asset, aggregated across enabled
  telemetry sources).
- `burst_eps_target_p95_1m`: 95th percentile of 1-minute EPS windows during the same 10-minute
  interval.

Planning baseline targets (initial defaults; operators SHOULD replace with measured baselines for
their lab):

| Asset role                | Telemetry profile                                        | Sustained EPS target | Burst EPS target (p95 1m) | Collector CPU target (p95) | Collector RSS target (p95) | Raw write estimate (MB/s)† |
| ------------------------- | -------------------------------------------------------- | -------------------: | ------------------------: | -------------------------: | -------------------------: | -------------------------: |
| Windows endpoint          | Windows Event Log (Application/Security/System) + Sysmon |                   50 |                       150 |             ≤ 5% of 1 vCPU |                   ≤ 350 MB |                    0.1–0.9 |
| Windows domain controller | Windows Event Log (Application/Security/System)          |                  300 |                     1,000 |            ≤ 15% of 1 vCPU |                   ≤ 500 MB |                    0.6–6.0 |
| Linux server              | auditd + osquery (evented + scheduled)                   |                  100 |                       300 |            ≤ 10% of 1 vCPU |                   ≤ 250 MB |                    0.2–1.8 |

† Raw write estimate assumes 2–6 KB average serialized event payload per record and is intended only
for order-of-magnitude disk sizing. Implementations MUST measure and report observed raw bytes per
second during validation.

Normative requirements:

- Telemetry validation MUST treat these values as planning defaults only; operators MAY override
  them via configuration or asset-specific profiles.
- The validator SHOULD record observed EPS and footprint statistics (CPU, RSS, raw bytes/sec) for
  each validated asset to make regressions and sizing errors detectable.
  - Measurement methodology is specified in the
    [telemetry pipeline specification](040_telemetry_pipeline.md) §2 "Performance and footprint
    controls (agent)".

Budgets are configuration-driven and enforced deterministically during telemetry validation.

- For telemetry validation, missing required budget configuration or missing required measurements MUST
  fail closed with stable reason codes (see "Telemetry validation (gating)" and
  "Resource budget quality gate (validation)").
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
per run (at minimum into `runs/<run_id>/logs/` and optionally into metrics backends):

- `telemetry_checkpoints_written_total`
- `telemetry_checkpoint_loss_total`
- `telemetry_checkpoint_corruption_total`
- `dedupe_duplicates_dropped_total`
- `dedupe_conflicts_total`

Implementations SHOULD also record:

- dedupe index location and size (bytes)
- checkpoint directory location
- replay start mode used on restart (`resume | reset_missing | reset_corrupt | reset_manual`)

Replay start mode definitions (normative):

- `resume`: checkpoint existed and was used.
- `reset_missing`: checkpoint missing; replay expected.
- `reset_corrupt`: checkpoint corrupt and recovery was applied (fresh state); replay expected.
- `reset_manual`: operator explicitly requested reset (ignore checkpoints).

## Telemetry validation (gating)

A telemetry stage is only considered "validated" for an asset when a validation run produces:

- raw Windows Event Log events captured in raw/unrendered mode
  - verified by a runtime canary:
    - captured XML begins with `<Event`
    - captured XML MUST NOT contain `<RenderingInfo>`
    - see the [telemetry pipeline specification](040_telemetry_pipeline.md) §2

Additional normative checks:

- The validator MUST emit a `health.json.stages[]` entry with
  `stage: "telemetry.windows_eventlog.raw_mode"`.
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
- disk capacity preflight (hard fail / fail closed) before the validation window begins:
  - The validator MUST compute `free_bytes_at_runs_root` for the filesystem containing the resolved
    runs root directory (the directory that contains `runs/<run_id>/`; typically
    `reporting.output_dir`).
  - `free_bytes_at_runs_root` MUST use the OS "bytes available to the current user" API
    (for example, POSIX `statvfs.f_bavail * f_frsize` or Windows `GetDiskFreeSpaceEx`'s
    `FreeBytesAvailable`).
  - The validator MUST compute:
    - `disk_headroom_bytes` (default `2147483648` (2 GiB) unless configured)
    - `required_free_bytes = max_raw_bytes_per_run + max_normalized_bytes_per_run + disk_headroom_bytes`
  - If `free_bytes_at_runs_root < required_free_bytes`, the run MUST fail closed:
    - `health.json` stage: `telemetry.disk.preflight`
    - `status=failed`, `fail_mode=fail_closed`, `reason_code=disk_free_space_insufficient`
    - run status: `failed`
  - If any required value cannot be computed, the run MUST fail closed with stable reason codes:
    - `reason_code=disk_metrics_missing` when free bytes cannot be computed (missing path, permissions,
      unsupported platform API, etc.)
    - `reason_code=resource_budgets_unconfigured` when `max_raw_bytes_per_run` and/or
      `max_normalized_bytes_per_run` are unset/unknown
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

- `cpu_target_p95_pct` (number): CPU utilization target at p95, expressed as percent of **1 vCPU**
  (single-core equivalent).
  - CPU percent MUST be computed as: `cpu_pct = rate(otelcol_process_cpu_seconds[1m]) * 100`.
- `rss_target_p95_bytes` (integer): RSS target at p95 in bytes, derived from
  `otelcol_process_memory_rss`.

Configured targets (per run):

- `max_raw_bytes_per_run` (integer): maximum allowed raw retention bytes for the run.
- `max_normalized_bytes_per_run` (integer): maximum allowed normalized store bytes for the run.

If either disk budget is unset/unknown, the validator MUST fail closed with
`reason_code=resource_budgets_unconfigured`.

Target resolution (v0.1):

- If an explicit per-asset footprint budget is configured, the validator MUST use it.
- Otherwise, the validator MUST use the planning defaults in
  [EPS baselines](#eps-baselines-planning-targets-v01) for the asset's `role`.
- If neither applies, the validator MUST fail closed with
  `reason_code=resource_budgets_unconfigured`.

Required measurements (per asset):

- A 10-minute steady-state window where `sustained_eps_observed >= sustained_eps_target`.
- `cpu_pct_p95` and `rss_bytes_p95` computed over that same window.

If the required measurements cannot be computed (missing collector self-telemetry, missing EPS
series, or the sustained EPS target was not met), the validator MUST fail closed with
`reason_code=resource_metrics_missing` or `reason_code=eps_target_not_met`.

Required measurements (per run):

- `raw_bytes_written_total` and `normalized_bytes_written_total`, computed deterministically as
  specified in "Deterministic disk measurement rules (normative)".
- These totals MUST be computed at the time the validator emits `health.json` for the run.

If the disk totals cannot be computed (missing paths, permissions, IO error during enumeration, etc.),
the validator MUST fail closed with `reason_code=disk_metrics_missing`.

#### Tolerance and evaluation (normative)

To reduce false negatives from measurement noise, budget enforcement uses a deterministic tolerance.

Defaults (v0.1):

- CPU tolerance: `max(1.0 percentage point, 10% of cpu_target_p95_pct)`
- RSS tolerance: `max(64 MiB, 10% of rss_target_p95_bytes)`
- Disk tolerance (per budget): `max(64 MiB, ceil(0.01 * budget_bytes))`
  - `64 MiB` MUST be interpreted as `67108864` bytes.
  - `ceil()` MUST be applied after multiplication and MUST produce an integer number of bytes.

A budget is considered exceeded when:

- `cpu_pct_p95 > cpu_target_p95_pct + cpu_tolerance`
- `rss_bytes_p95 > rss_target_p95_bytes + rss_tolerance`

#### Health accounting and outcomes (normative)

The validator MUST emit a `health.json.stages[]` entry with `stage: "telemetry.resource_budgets"`.

Outcome mapping (quality gate semantics):

- If no budgets are exceeded, the stage MUST be `status=success`.
- If one or more budgets are exceeded, the stage MUST be `status=failed` with
  `fail_mode=warn_and_skip`, and the overall run `manifest.status` MUST be `partial` unless it is
  already `failed` for another reason.

Reason codes (stable tokens):

- `resource_budget_cpu_exceeded`
- `resource_budget_rss_exceeded`
- `resource_budget_disk_exceeded` (exactly one of raw/normalized disk budgets exceeded)
- `resource_budget_disk_multiple_exceeded` (both raw and normalized disk budgets exceeded)
- `resource_budget_multiple_exceeded` (two or more budgets exceeded, except "disk-only" case above)
- `resource_budgets_unconfigured` (fail-closed)
- `resource_metrics_missing` (fail-closed)
- `disk_metrics_missing` (fail-closed)
- `eps_target_not_met` (fail-closed)

Reason code selection (normative):

Let `exceeded` be the set of exceeded budget dimensions across:
`cpu`, `rss`, `raw_disk`, `normalized_disk`.

- If `exceeded` is empty, `status=success`.
- If `exceeded` contains only `cpu`, use `resource_budget_cpu_exceeded`.
- If `exceeded` contains only `rss`, use `resource_budget_rss_exceeded`.
- If `exceeded` contains exactly one of `raw_disk` or `normalized_disk`, use
  `resource_budget_disk_exceeded`.
- If `exceeded` is exactly `{raw_disk, normalized_disk}`, use
  `resource_budget_disk_multiple_exceeded`.
- Otherwise (any other combination of 2+ exceeded dimensions), use
  `resource_budget_multiple_exceeded`.

The validator SHOULD record the observed p95 values, targets, tolerances, and the window definition
in `runs/<run_id>/logs/telemetry_validation.json` to make regressions reviewable.

The validator MUST write `runs/<run_id>/logs/telemetry_validation.json`, conforming to the
[telemetry validation schema](../contracts/telemetry_validation.schema.json); the manifest SHOULD
include a pointer to it.

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

- `stages[]` MUST be sorted by `stage` using UTF-8 byte order (no locale).
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

| Limit             | Exceeded behavior                      | Run status          | Exit code      | Accounting required                                                                                                                                                                            |
| ----------------- | -------------------------------------- | ------------------- | -------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `max_run_minutes` | Hard-fail, stop immediately            | `failed`            | `20`           | Record `reason_code=run_timeout` in `logs/health.json` and include a `limits_exceeded[]` entry in `manifest.extensions.operability`.                                                           |
| `max_disk_gb`     | Stop gracefully and finalize artifacts | `partial` (default) | `10` (default) | Record `reason_code=disk_limit_exceeded` with the truncation timestamp and disk watermark in `logs/health.json`, and include a `limits_exceeded[]` entry in `manifest.extensions.operability`. |
| `max_memory_mb`   | Hard-fail (OOM is fatal)               | `failed`            | `20`           | Record `reason_code=memory_limit_exceeded` (or `oom_killed`) in `logs/health.json`.                                                                                                            |

The pipeline MUST record run-limit enforcement outcomes under `health.json` stage
`stage: "operability.run_limits"`.

Disk limit configurability (normative):

- If `operability.run_limits.disk_limit_behavior=hard_fail`, exceeding `max_disk_gb` MUST produce
  `failed` (exit code `20`) instead of `partial`.
- Regardless of behavior, the report output MUST explicitly state which stages were truncated and
  the time window captured.

Disk enforcement during telemetry validation is defined in:
- "Telemetry validation (gating)" (disk capacity preflight; fail closed), and
- "Resource budget quality gate (validation)" (disk budget quality gate; warn-and-skip / partial).

`operability.run_limits.max_disk_gb` is a separate runtime safeguard (stop/truncate behavior) and
MUST NOT be treated as equivalent to the per-run sizing budgets.

Minimum accounting fields (normative):

- `limit` (one of `max_run_minutes|max_disk_gb|max_memory_mb`)
- `configured` (numeric)
- `observed` (numeric)
- `behavior` (`partial|hard_fail`)
- `stage` (stable stage identifier)
- `truncated_at_utc` (ISO-8601, required for disk truncation)

## References

- [Telemetry pipeline specification](040_telemetry_pipeline.md)
- [Configuration reference](120_config_reference.md)
- [Telemetry validation schema](../contracts/telemetry_validation.schema.json)

## Changelog

| Date       | Change            |
| ---------- | ----------------- |
| 2026-01-12 | Formatting update |
