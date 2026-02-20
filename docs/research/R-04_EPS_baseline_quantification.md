---
title: EPS baseline quantification
description: Establishes realistic EPS baselines for Windows endpoint telemetry in lab scenarios and seeds v0.1 defaults for max EPS, memory limits, and disk budgets.
status: draft
---

# EPS baseline quantification

## Research question

What are realistic events-per-second (EPS) rates for Windows endpoint telemetry in lab scenarios
(including Atomic Red Team execution), and what resource budgets (memory, disk) are appropriate for
collector sizing and CI thresholds?

## Why it matters

Purple Axiom performs resource budget validation and throughput validation using collector
self-telemetry and run artifacts. Without numeric baselines, implementers cannot size collectors,
set safe defaults, or establish CI gates that distinguish "collector misconfigured or overloaded"
from "scenario produced low signal."

## Scope

This document focuses on Windows endpoint telemetry collected via OpenTelemetry Collector
(otelcol-contrib), including Windows Event Log and common endpoint telemetry sources (e.g., Sysmon,
osquery where applicable), executed in isolated lab scenarios.

Out of scope:

- Enterprise-scale fleet sizing (beyond referencing public guidance for plausibility checks).
- Network telemetry sizing (pcap/netflow), which is reserved elsewhere.
- Vendor-specific SIEM ingestion sizing.

## Definitions

### EPS

EPS is the rate of accepted log records, measured from collector internal telemetry:

- Primary metric: `otelcol_receiver_accepted_log_records` (or the equivalent accepted log records
  metric exposed by the Collector’s internal telemetry pipeline).

EPS MUST be computed from accepted records (post-receiver), not from exported records, to avoid
downstream backpressure obscuring ingestion load.

### Sustained vs burst EPS

Purple Axiom’s operability model defines two complementary targets:

- **Sustained EPS**: average EPS over a stable 10-minute window after warmup.
- **Burst EPS (p95, 1-minute)**: p95 of a 1-minute rolling average during the run.

These terms align with the resource budget validation schema in Operability.

### Disk budgets

Disk budgets are evaluated at run level using raw and normalized output byte totals. This document
uses the existing v0.1 seed per-record size estimates to produce deterministic “bytes-per-hour vs
EPS” curves.

## Published evidence (sanity bounds)

The primary goal of published sources here is to provide sanity bounds for what a single collector
can handle, and to anchor the relationship between EPS and memory/CPU.

### Windows Event Forwarding (WEC) guidance

Microsoft’s Windows Event Forwarding guidance provides an order-of-magnitude bound for “events/sec
per collector” for Windows event collection use cases:

- For stable WEC operation on commodity hardware, Microsoft recommends planning for a total average
  of roughly **3,000 events per second** across all subscriptions on a collector. (This is not a
  per-endpoint rate; it is a total ingestion bound for a collector instance.)
- Microsoft also documents performance characteristics and scaling considerations (including
  client-to-collector ratios and memory growth behavior) that imply "thousands of EPS per collector"
  is a reasonable operating envelope when tuned.

### OpenTelemetry Collector performance (logs)

Public OTel Collector log throughput varies widely by pipeline design (processors/exporters),
payload size, and deployment environment. Vendor and community benchmarks indicate:

- At 1 KB log event sizes, collectors can sustain **thousands to tens of thousands of log events per
  second** on modest resources, with CPU and memory rising predictably as EPS increases.

These published bounds support keeping Purple Axiom’s *default lab* EPS targets in the low hundreds
per endpoint (and low thousands per single collector) while retaining headroom for bursty behavior
during Atomic execution.

## v0.1 seed defaults (recommended)

This section seeds default values that are "reasonable for labs" and consistent with Purple Axiom’s
existing operability targets.

### Per-asset role: EPS and resource targets

The Operability spec already seeds planning targets by asset role. This document formalizes those
targets as the default baseline to implement against:

| Asset role       | sustained EPS target (10m) | max EPS (burst p95, 1m) | cpu p95 target (%) | rss p95 target (MiB) |
| ---------------- | -------------------------: | ----------------------: | -----------------: | -------------------: |
| Windows endpoint |                         50 |                     150 |                  5 |                  350 |
| Windows DC       |                        300 |                   1,000 |                 10 |                  700 |
| Linux server     |                        100 |                     300 |                  5 |                  512 |

Notes:

- **max EPS** in this document corresponds to the Operability "burst_eps_target_p95_1m" concept.
  Implementations MAY name this field differently, but the semantics must match: a p95 threshold on
  a 1-minute rolling EPS window.

### Collector memory limiter (recommended defaults)

Purple Axiom’s telemetry pipeline currently seeds a baseline memory limiter of 512 MiB. For v0.1:

- **Windows endpoint**: `memory_limiter.limit_mib` SHOULD default to **512 MiB**.
- **Windows DC**: `memory_limiter.limit_mib` SHOULD default to **1024 MiB** (derived from the higher
  rss p95 target; see "Calibration" below).
- **Linux server**: `memory_limiter.limit_mib` SHOULD default to **768 MiB** (derived).

Additional configuration guidance:

- `check_interval` SHOULD be **1s**.
- `spike_limit_mib` SHOULD default to **20% of limit_mib** (soft limit = hard limit − spike).

Rationale:

- These settings are consistent with widely documented memory limiter behavior (soft/hard
  thresholds, 20% spike default, 1s check interval).
- For lab assets, the goal is fail-closed safety under accidental pipeline amplification (e.g.,
  misconfigured receivers or exporter backpressure) rather than maximizing throughput at all costs.

### Run-level disk budgets (recommended defaults)

For v0.1, default run-level budgets SHOULD match the Operability seed values:

- `run_limits.max_disk_gb`: **15 GB**
- `run_limits.max_raw_bytes_per_run`: **3 GB**
- `run_limits.max_normalized_bytes_per_run`: **3 GB**

These defaults are intended to prevent runaway disk usage while allowing multi-hour runs at the
seeded EPS levels.

## Derived utilization curves (bytes-per-hour vs EPS)

This section provides deterministic disk growth estimates at common EPS rates using v0.1 seed size
estimates:

- raw bytes per record: **1300 bytes**
- normalized bytes per record: **900 bytes**

Assuming EPS is constant over the interval, estimated write volume per hour is:

|   EPS | raw MiB/hour | normalized MiB/hour | total MiB/hour |
| ----: | -----------: | ------------------: | -------------: |
|     1 |          4.5 |                 3.1 |            7.6 |
|     5 |         22.3 |                15.4 |           37.8 |
|    10 |         44.6 |                30.9 |           75.5 |
|    50 |        223.2 |               154.5 |          377.7 |
|   150 |        669.5 |               463.5 |        1,133.0 |
|   300 |      1,339.0 |               927.0 |        2,265.9 |
| 1,000 |      4,463.2 |             3,089.9 |        7,553.1 |

Implications for default 3 GB raw / 3 GB normalized budgets:

- At **150 EPS** sustained, raw budget exhausts in ~**4.6 hours**, normalized in ~**6.6 hours**.
- At **50 EPS** sustained, raw budget exhausts in ~**13.8 hours**, normalized in ~**19.9 hours**.

These curves are meant for preflight sizing and for explaining budget failures; actual runs will
vary with event sizes and compression.

## Calibration plan (how to replace seed defaults with empirical baselines)

This section defines what "good evidence" looks like for Purple Axiom and produces an implementable
measurement contract.

### Measurement requirements

An EPS baseline run MUST capture:

1. Collector internal telemetry for accepted log records (EPS basis).
1. Collector process CPU and RSS over time (to compute p95 CPU% and p95 RSS).
1. Raw and normalized output byte totals from run artifacts.

The Operability validator already defines fail-closed reason codes when telemetry is missing or
sustained targets are not met; baseline collection MUST ensure these signals exist to avoid
ambiguous failures.

### Baseline workload definition (Atomic representative)

A "representative" baseline workload SHOULD include:

- A minimum of N Atomic tests spanning common telemetry generators:
  - process creation (cmd, powershell, rundll32)
  - file create/delete and rename
  - registry create/modify/delete
  - network connect (internal-only, respecting lab safety policy)
- A defined concurrency level (e.g., 1, 2, 4 parallel actions), because concurrency is the dominant
  driver of burst EPS.

This document does not lock in a specific Atomic list; it requires that the chosen list be versioned
and recorded in the run bundle so EPS results remain comparable.

### Computation rules (deterministic)

To ensure reproducibility across runs and platforms:

- Sustained EPS MUST be computed as the mean of per-second EPS samples over a contiguous 10-minute
  window after warmup.
- Burst EPS MUST be computed as p95 of the 1-minute rolling mean over the entire run.
- CPU p95 MUST be computed over the same stable window used for sustained EPS unless explicitly
  stated otherwise in the run bundle.
- RSS p95 MUST be computed over the same stable window used for sustained EPS.

### Output artifact: baseline JSON

Each baseline run MUST produce a machine-readable artifact:

`run_bundle/telemetry/eps_baseline.json`

Schema (v0.1 draft):

- `schema_version` (string; e.g., `"pa:eps_baseline:v1"`)
- `collector_instance_id` (string; stable ID for the collector under test)
- `asset_role` (enum: `windows_endpoint`, `windows_dc`, `linux_server`)
- `time_window`:
  - `warmup_seconds` (int)
  - `sustained_window_seconds` (int; MUST be 600 for v0.1)
- `eps`:
  - `sustained_mean` (number)
  - `burst_p95_1m` (number)
  - `samples_per_second` (int; SHOULD be 1)
- `resources`:
  - `cpu_p95_pct` (number)
  - `rss_p95_bytes` (int)
- `disk`:
  - `raw_bytes` (int)
  - `normalized_bytes` (int)
- `inputs`:
  - `scenario_id` (string)
  - `scenario_version` (string or null)
  - `atomic_pack_ref` (string or null)
  - `atomic_tests` (array of strings; stable ordering)
- `notes` (string; optional)

### Acceptance criteria for updating defaults

A seed default MAY be replaced only when:

- At least 5 baseline runs per role exist (to reduce single-run noise).
- The chosen new default is:
  - at or below the 80th percentile of observed sustained EPS for the workload (for sustained
    target), and
  - at or below the 80th percentile of observed burst p95 1m (for max EPS),
  - while preserving a safety margin for CPU/RSS/disk budgets.

Rationale: defaults should "usually pass" for representative workloads, while still detecting
abnormal conditions.

## Recommended initial configuration mapping

Until the baseline JSON corpus exists, implementers SHOULD map defaults as follows:

- `max_eps` (if a single field exists): use the role’s "max EPS (burst p95, 1m)" from the table
  above.
- `sustained_eps_target`: use the role’s sustained target from the table above.
- `rss_target_p95_bytes`: use the role’s rss target (MiB × 1024 × 1024).
- `cpu_target_p95_pct`: use the role’s cpu target.
- Disk budgets: use the run-level defaults in this document.

## References

- Purple Axiom Operability: planning EPS and budget targets, run disk budgets, per-record sizing
  seeds, and validator reason codes.
- Purple Axiom Telemetry Pipeline: baseline collector pipeline and memory limiter seed values.
- Microsoft Windows Event Forwarding guidance: collector-level EPS and performance scaling notes.
- OpenTelemetry Collector ecosystem guidance: memory limiter behavior and configuration best
  practices.
- Public log throughput benchmarks for collectors (logs/sec vs CPU/RSS) to anchor memory scaling
  expectations.
