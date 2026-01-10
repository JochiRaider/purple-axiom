<!-- docs/spec/110_operability.md -->

# Operability

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

- **Disk**: per-run maximum raw retention size, per-run maximum normalized store size.
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
  - Measurement methodology is specified in `040_telemetry_pipeline.md` §2 “Performance and
    footprint controls (agent)”.

Budgets are configuration-driven and surfaced in reports when exceeded.

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
- `dedupe_duplicates_dropped_total`
- `dedupe_conflicts_total`

Implementations SHOULD also record:

- dedupe index location and size (bytes)
- checkpoint directory location
- replay start mode used on restart (`resume` vs `reset` fallback)

## Telemetry validation (gating)

A telemetry stage is only considered "validated" for an asset when a validation run produces:

- raw Windows Event Log events captured in raw/unrendered mode
  - verified by a runtime canary:
    - captured XML begins with `<Event`
    - captured XML MUST NOT contain `<RenderingInfo>`
    - see `040_telemetry_pipeline.md` §2

Additional normative checks:

- The validator MUST emit a `health.json.stages[]` entry with
  `stage: "telemetry.windows_eventlog.raw_mode"`.
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
- stable parsing of required identity fields (channel, provider, record id)
- successful parsing when rendered message strings are missing (manifest/publisher metadata failures
  must not be fatal)
- no unbounded growth under exporter throttling
- footprint within configured budgets at target event rate
- payload limits enforced and observable:
  - oversized `event_xml` produces `event_xml_truncated=true` plus `event_xml_sha256`
  - binary fields honor `max_binary_bytes` and produce deterministic
    `binary_present/binary_oversize` signals

The validator MUST write `runs/<run_id>/logs/telemetry_validation.json`, conforming to
`docs/contracts/telemetry_validation.schema.json`; the manifest SHOULD include a pointer to it.

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

When run limits are configured (see `operability.run_limits` in `120_config_reference.md`), the
pipeline MUST behave as follows:

| Limit             | Exceeded behavior                      | Run status          | Exit code      | Accounting required                                                                                                                                                                            |
| ----------------- | -------------------------------------- | ------------------- | -------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `max_run_minutes` | Hard-fail, stop immediately            | `failed`            | `20`           | Record `reason_code=run_timeout` in `logs/health.json` and include a `limits_exceeded[]` entry in `manifest.extensions.operability`.                                                           |
| `max_disk_gb`     | Stop gracefully and finalize artifacts | `partial` (default) | `10` (default) | Record `reason_code=disk_limit_exceeded` with the truncation timestamp and disk watermark in `logs/health.json`, and include a `limits_exceeded[]` entry in `manifest.extensions.operability`. |
| `max_memory_mb`   | Hard-fail (OOM is fatal)               | `failed`            | `20`           | Record `reason_code=memory_limit_exceeded` (or `oom_killed`) in `logs/health.json`.                                                                                                            |

Disk limit configurability (normative):

- If `operability.run_limits.disk_limit_behavior=hard_fail`, exceeding `max_disk_gb` MUST produce
  `failed` (exit code `20`) instead of `partial`.
- Regardless of behavior, the report output MUST explicitly state which stages were truncated and
  the time window captured.

Minimum accounting fields (normative):

- `limit` (one of `max_run_minutes|max_disk_gb|max_memory_mb`)
- `configured` (numeric)
- `observed` (numeric)
- `behavior` (`partial|hard_fail`)
- `stage` (stable stage identifier)
- `truncated_at_utc` (ISO-8601, required for disk truncation)
