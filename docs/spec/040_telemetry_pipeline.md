# Telemetry Pipeline (OpenTelemetry Collector)

## Why OTel Collector
- Vendor-agnostic collector that can receive/process/export telemetry. (Reference: OTel Collector docs)

## Pipeline MVP
- Receivers:
  - windowseventlog receiver (OTel Collector contrib) for Windows channels
- Processors:
  - resourcedetection (where applicable)
  - attributes processor for adding run_id/scenario_id
  - batch
- Exporters:
  - file (JSON lines) or OTLP to a local service
  - optional: parquet writer service (phase 2)

## Windows Event Log collection (seed)
- Channels: Security, System, Application (+ Sysmon if present)
- Baseline filters: limit noise while preserving test coverage (documented allowlist/denylist)

## Determinism requirements
- Collector config is versioned.
- Receiver offsets/bookmarks recorded per run or reset policy explicitly documented.
