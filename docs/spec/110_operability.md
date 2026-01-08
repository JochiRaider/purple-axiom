<!-- docs/spec/110_operability.md -->
# Operability

Purple Axiom is intended to run continuously, unattended, on local lab infrastructure. Operability requirements focus on:

- health visibility (did the pipeline run, and where did it fail?)
- bounded resource usage (avoid runaway CPU/RAM/disk)
- reproducibility (same inputs yield comparable outputs)
- failure classification (collector issue vs mapping gap vs detection logic gap)

## Service health model

Each major stage exposes a minimal health signal:

- **Lab Provider**: inventory resolution success, snapshot hash, resolved asset count, drift detection (optional).
- **Runner**: scenario execution status, per-action outcomes, cleanup status.
- **Telemetry (collector)**: receiver health, export success, queue depth, dropped counts.
- **Normalizer**: input read completeness, parse errors, mapping coverage.
- **Evaluator**: rule load success, compilation failures, match counts.
- **Scoring**: join completeness, latency distributions.

The run manifest reflects the overall outcome (`success`, `partial`, `failed`) and includes stage-level failure reasons.

## Inventory snapshot (required when provider != manual)
- Each run SHOULD write `runs/<run_id>/logs/lab_inventory_snapshot.json` as the canonical resolved inventory used for that run.
- The manifest SHOULD include:
  - provider type
  - snapshot hash (sha256)
  - resolved asset list (or a pointer to the snapshot)

## Collector observability (required)

The OpenTelemetry Collector should expose internal telemetry to support debugging and capacity planning:

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
- **CPU**: continuous runs should not starve endpoints; target sustained CPU under a configurable threshold.

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
- stable parsing of required identity fields (channel, provider, record id)
- successful parsing when rendered message strings are missing (manifest/publisher metadata failures must not be fatal)
- no unbounded growth under exporter throttling
- footprint within configured budgets at target event rate
- payload limits enforced and observable:
  - oversized `event_xml` produces `event_xml_truncated=true` plus `event_xml_sha256`
  - binary fields honor `max_binary_bytes` and produce deterministic `binary_present/binary_oversize` signals

The validator writes a summary to `runs/<run_id>/logs/telemetry_validation.json` and the manifest SHOULD include a pointer to it.

## Health files (normative, v0.1)

When `operability.health.emit_health_files=true`, the pipeline MUST write `runs/<run_id>/logs/health.json`.

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
2. Validate raw event presence in `raw/` for the asset and time window.
3. Inspect normalizer parse/mapping errors and mapping coverage deltas.
4. Only then inspect rule logic and scorer joins.

This prevents "rule debugging" when the root cause is missing telemetry.