---
title: Architecture
description: Defines the high-level system flow, stage identifiers, IO boundaries, and extension points.
status: draft
category: spec
tags: [architecture, pipeline, stages, orchestrator]
related:
  - ADR-0004-deployment-architecture-and-inter-component-communication.md
  - ADR-0005-stage-outcomes-and-failure-classification.md
  - 025_data_contracts.md
  - 040_telemetry_pipeline.md
  - 065_sigma_to_ocsf_bridge.md
---

# Architecture

This document describes the high-level architecture of Purple Axiom, including the deployment
topology, pipeline stages, stage IO boundaries, and supported extension points.

## Overview

**Summary**: Purple Axiom is a one-shot, local-first pipeline that executes adversary emulation
scenarios, captures telemetry, normalizes events into OCSF, evaluates detections, and produces
reproducible run bundles.

The system resolves lab inventory, executes scenarios, captures telemetry, normalizes events,
evaluates criteria, runs detection rules, computes scores, and generates reports. Each stage reads
inputs from the run bundle and writes outputs back to the run bundle. The filesystem is the
inter-stage contract boundary.

## Scope

This document covers:

- Deployment topology and orchestration model
- Stable stage identifiers and execution order
- Stage IO boundaries (minimum inputs and outputs)
- Component responsibilities
- Extension points

This document does NOT cover:

- Detailed artifact schemas (see [data contracts specification][data-contracts])
- Configuration surface area (see [configuration reference][config-ref])
- Failure classification and reason codes (see [ADR-0005])
- Telemetry collection details (see [telemetry pipeline specification][telemetry-spec])

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

### Telemetry plane

Telemetry collection follows the canonical OpenTelemetry model:

- **Agent tier (required)**: Collector on each endpoint to read OS sources (Windows Event Log with
  `raw: true`, syslog, osquery results).
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

See [ADR-0004] for the normative deployment topology and inter-component communication contract.

## High-level flow

```text
┌────────────────────────────────┐
│        lab_provider            │ ← Resolve inventory (manual, Ludus, Terraform)
└───────────────┬────────────────┘
                │ Inventory snapshot (deterministic, hashable)
                ▼
┌────────────────────────────────┐
│           runner               │ ← Execute scenarios (Atomic Red Team v0.1)
└───────────────┬────────────────┘
                │ ground_truth.jsonl + runner/** evidence
                ▼
┌────────────────────────────────┐
│          telemetry             │ ← OTel Collector topology + runtime canaries
└───────────────┬────────────────┘
                │ raw_parquet/** + telemetry_validation.json
                ▼
┌────────────────────────────────┐
│        normalization           │ ← Map raw → OCSF envelopes
└───────────────┬────────────────┘
                │ normalized/** + mapping_coverage.json
                ▼
┌────────────────────────────────┐
│          validation            │ ← Evaluate criteria packs + cleanup verification
└───────────────┬────────────────┘
                │ criteria/** results
                ▼
┌────────────────────────────────┐
│          detection             │ ← Sigma-to-OCSF bridge + rule evaluation
└───────────────┬────────────────┘
                │ bridge/** + detections/**
                ▼
┌────────────────────────────────┐
│           scoring              │ ← Join ground truth, criteria, detections
└───────────────┬────────────────┘
                │ scoring/summary.json
                ▼
┌────────────────────────────────┐
│          reporting             │ ← Generate HTML scorecard + JSON outputs
└───────────────┬────────────────┘
                │ report/**
                ▼
┌────────────────────────────────┐
│           signing              │ ← (Optional) Sign run bundle artifacts
└────────────────────────────────┘
                │ security/** (when enabled)
```

## Stage identifiers

**Summary**: Each stage has a stable identifier used in manifests, health files, configuration, and
logs. Substages use dotted notation.

| Stage ID        | Description                                 | Optional |
| --------------- | ------------------------------------------- | -------- |
| `lab_provider`  | Resolve and snapshot lab inventory          | No       |
| `runner`        | Execute scenario actions, emit ground truth | No       |
| `telemetry`     | Capture raw events, validate collection     | No       |
| `normalization` | Map raw telemetry to OCSF envelopes         | No       |
| `validation`    | Evaluate criteria packs, verify cleanup     | No       |
| `detection`     | Compile/evaluate Sigma via bridge           | No       |
| `scoring`       | Compute coverage, latency, gap metrics      | No       |
| `reporting`     | Generate human/machine-readable reports     | No       |
| `signing`       | Sign artifacts for integrity verification   | Yes      |

Substages MAY be expressed as dotted identifiers (for example, `lab_provider.connectivity`,
`telemetry.windows_eventlog.raw_mode`, `validation.cleanup`). Substages are additive and MUST NOT
change the semantics of the parent stage outcome.

See [ADR-0005] for stage outcome definitions and failure classification.

## Stage IO boundaries

**Summary**: Each stage reads inputs from the run bundle and writes outputs back. The table below
defines the minimum IO contract for v0.1.

| Stage ID        | Minimum inputs                                                        | Minimum outputs                                                              |
| --------------- | --------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| `lab_provider`  | Run configuration, provider inputs                                    | Inventory snapshot artifact (referenced by manifest)                         |
| `runner`        | Inventory snapshot, scenario plan                                     | `ground_truth.jsonl`, `runner/**` evidence                                   |
| `telemetry`     | Inventory snapshot, time window (from runner)                         | `raw_parquet/**`, `logs/telemetry_validation.json` (when validation enabled) |
| `normalization` | `raw_parquet/**`, mapping profiles                                    | `normalized/**`, `normalized/mapping_coverage.json`                          |
| `validation`    | `ground_truth.jsonl`, `normalized/**`, criteria pack snapshot         | `criteria/**` (results + cleanup verification)                               |
| `detection`     | `normalized/**`, bridge mapping pack, Sigma rule packs                | `bridge/**`, `detections/detections.jsonl`                                   |
| `scoring`       | `ground_truth.jsonl`, `criteria/**`, `detections/**`, `normalized/**` | `scoring/summary.json`                                                       |
| `reporting`     | `scoring/**`, `criteria/**`, `detections/**`, manifest                | `report/**` (HTML + supplemental artifacts)                                  |
| `signing`       | Finalized manifest, selected artifacts                                | `security/**` (checksums, signature, public key)                             |

> **Note**: This table defines the **minimum** contract. Implementations MAY produce additional
> artifacts, but MUST produce at least these outputs for the stage to be considered successful.

See [ADR-0004] for detailed publish semantics and filesystem coordination rules.

## Components

### `lab_provider` (inventory resolution)

**Summary**: Resolves a concrete list of target assets and connection metadata, producing a
deterministic snapshot for the run.

Responsibilities:

- Resolve target assets from an external source (manual config, Ludus export, Terraform output)
- Validate connectivity to resolved assets (substage: `lab_provider.connectivity`)
- Produce a run-scoped inventory snapshot recorded in the run bundle
- Ensure the snapshot is hashable and diffable for determinism

Implementations:

- `manual`: Inline `lab.assets` in run configuration
- `ludus`: Parse Ludus-generated inventory export
- `terraform`: Parse `terraform output -json` or exported inventory file

The inventory snapshot is treated as an input for determinism; the manifest records
`lab.inventory_snapshot_sha256`.

### `runner` (scenario execution)

**Summary**: Executes test plans and emits an append-only ground truth timeline with evidence
artifacts.

Responsibilities:

- Execute scenario actions per the test plan (Atomic Red Team for v0.1; Caldera is a future
  candidate)
- Emit `ground_truth.jsonl`: what ran, when, where, with what resolved inputs
- Record resolved target identifiers (`asset_id` + resolved host identity)
- Capture executor transcripts (stdout/stderr), exit codes, and durations
- Invoke and verify cleanup actions (staged lifecycle: invoke → verify)

Ground truth records MUST include deterministic `action_key` values that remain stable across
replays. See the [scenarios specification][scenarios-spec] for ground truth schema.

Evidence artifacts are stored under `runner/**` (transcripts, executor metadata, cleanup
verification results).

### `telemetry` (collection and validation)

**Summary**: Captures raw events via OpenTelemetry Collectors and validates collection invariants.

Responsibilities:

- Ensure raw Windows Event Log events are captured in raw/unrendered mode (`raw: true`)
- Support optional osquery results ingestion (event format NDJSON via `filelog` receiver)
- Execute runtime canaries (substage: `telemetry.windows_eventlog.raw_mode`)
- Validate checkpointing and dedupe behavior (substage: `telemetry.checkpointing.storage_integrity`)
- Produce `raw_parquet/**` for downstream normalization

See the [telemetry pipeline specification][telemetry-spec] for collection invariants, Windows Event
Log requirements, and osquery integration.

### `normalization` (OCSF mapping)

**Summary**: Maps raw telemetry to OCSF categories/classes and attaches provenance fields.

Responsibilities:

- Map raw events to OCSF 1.7.0 envelopes per the configured mapping profile
- Attach provenance fields: `metadata.source_type`, host identity, tool version, `scenario_id`,
  `run_id`
- Compute deterministic `metadata.event_id` / `metadata.uid` per [ADR-0002]
- Emit `normalized/**` as the canonical OCSF event store
- Emit `normalized/mapping_coverage.json` summarizing field coverage and unmapped events

See the [OCSF normalization specification][ocsf-spec] for mapping rules and the
[field tiers specification][field-tiers] for coverage requirements.

### `validation` (criteria evaluation)

**Summary**: Evaluates versioned criteria packs against the normalized OCSF store and verifies
cleanup outcomes.

Responsibilities:

- Load criteria pack snapshot pinned in the run manifest
- For each ground truth action, match the appropriate criteria entry
- Evaluate expected signals within configured time windows
- Emit `criteria/criteria_results.jsonl` for scoring
- Emit cleanup verification results (as part of criteria or referenced by them)

Criteria packs are externalized and versioned independently of the pipeline. The manifest records
`criteria.pack_sha256`.

### `detection` (Sigma evaluation)

**Summary**: Compiles and evaluates Sigma rules against normalized OCSF events via the Sigma-to-OCSF
bridge.

The detection stage has two sub-components:

#### Sigma-to-OCSF bridge

A contract-driven compatibility layer that routes Sigma rules to OCSF event classes.

Artifacts produced:

- `bridge/router_table_snapshot.json`: Logsource → OCSF class routing table
- `bridge/mapping_pack_snapshot.json`: Full bridge inputs (router + field aliases + fallback policy)
- `bridge/compiled_plans/<rule_id>.plan.json`: Per-rule compilation output
- `bridge/coverage.json`: Bridge success/failure summary

Bridge components:

- **Logsource router**: Maps `sigma.logsource` → OCSF `class_uid` filter (+ optional producer/source
  predicates via `filters[]`)
- **Field alias map**: Maps Sigma field names → OCSF JSONPaths (or backend-specific expressions)
- **Backend adapters**: Compile to batch plan (SQL over Parquet) or stream plan

See the [Sigma-to-OCSF bridge specification][bridge-spec] for routing rules and field alias
semantics.

#### Detection engine

Evaluates compiled Sigma rules against the normalized OCSF event store.

Responsibilities:

- Load Sigma rules and evaluate via the bridge
- Produce `detections/detections.jsonl` (one line per detection instance)
- Report non-executable rules with reasons (fail-closed behavior)
- Compute technique coverage and detection latency

**Fail-closed behavior**: If the bridge cannot route a rule (unknown `logsource`) or map a
referenced field, the rule is reported as **non-executable** for that run. Non-executable rules do
not produce detection instances but are included in coverage reporting.

See the [Sigma detection specification][sigma-spec] for evaluation model and output schema.

### `scoring` (metrics computation)

**Summary**: Joins ground truth, validation results, and detections to produce coverage and latency
metrics.

Responsibilities:

- Join `ground_truth.jsonl` with `criteria/**` and `detections/**`
- Compute technique coverage, detection latency, and gap metrics
- Apply threshold gates when configured
- Emit `scoring/summary.json` as the machine-readable scoring output

The scoring summary is the primary input for the reporting stage and for CI threshold gates.

### `reporting` (output generation)

**Summary**: Generates human-readable and machine-readable report outputs from scoring data.

Responsibilities:

- Render HTML scorecard from `scoring/summary.json`
- Emit JSON report artifacts for external tooling
- Include run manifest summary and artifact index
- Support diffing and trending across runs

Outputs are stored under `report/**`.

### `signing` (integrity verification, optional)

**Summary**: When enabled, signs the finalized run bundle for integrity verification.

Responsibilities:

- Compute SHA-256 checksums for all long-term artifacts
- Sign `security/checksums.txt` using Ed25519
- Emit `security/signature.ed25519` and `security/public_key.ed25519`
- Record `key_id` in manifest for downstream trust policies

Signing MUST be the final stage after all other artifacts are materialized. The `signing` stage is
optional and controlled by `security.signing.enabled`.

See the [data contracts specification][data-contracts] for signing artifact formats and long-term
artifact selection rules.

## Extension points

Purple Axiom is designed for extensibility at defined boundaries:

| Extension type       | Examples                                      | Interface                          |
| -------------------- | --------------------------------------------- | ---------------------------------- |
| Lab providers        | Manual, Ludus, Terraform, custom              | Inventory snapshot contract        |
| Scenario runners     | Atomic Red Team, Caldera, custom              | Ground truth + evidence contracts  |
| Telemetry sources    | Windows Event Log, Sysmon, osquery, EDR, pcap | OTel receiver + raw schema         |
| Schema mappings      | OCSF 1.7.0, future OCSF versions, profiles    | Mapping profile contract           |
| Rule languages       | Sigma, YARA, Suricata (future)                | Bridge + evaluator contracts       |
| Bridge mapping packs | Logsource routers, field alias maps           | Mapping pack schema                |
| Evaluator backends   | DuckDB/SQL, Tenzir, streaming engines         | Compiled plan + detection contract |

Extensions MUST preserve the stage IO boundaries and produce contract-compliant artifacts.

## Key decisions

1. **Single-host, local-first execution**: v0.1 runs on a single host with no distributed control
   plane. See [ADR-0004].

1. **File-based stage coordination**: Stages communicate via filesystem artifacts, not RPC. The run
   bundle is the single source of truth.

1. **One-shot orchestrator**: The pipeline runs as a single invocation per run. No daemon required.

1. **Deterministic stage outcomes**: Every stage produces a deterministic outcome (success, failed,
   skipped) with stable reason codes. See [ADR-0005].

1. **Fail-closed detection**: If the bridge cannot route or map a Sigma rule, the rule is
   non-executable (not silently skipped).

1. **Inventory snapshotting**: Lab providers resolve inventory into a run-scoped snapshot for
   determinism and reproducibility.

1. **Ground truth as append-only timeline**: The runner emits an immutable record of executed
   actions for downstream joins.

## References

- [ADR-0004: Deployment architecture and inter-component communication][adr-0004]
- [ADR-0005: Stage outcomes and failure classification][adr-0005]
- [ADR-0002: Event identity and provenance][adr-0002]
- [Data contracts specification][data-contracts]
- [Scenarios specification][scenarios-spec]
- [Telemetry pipeline specification][telemetry-spec]
- [OCSF normalization specification][ocsf-spec]
- [OCSF field tiers specification][field-tiers]
- [Sigma-to-OCSF bridge specification][bridge-spec]
- [Sigma detection specification][sigma-spec]
- [Configuration reference][config-ref]
- [Operability specification][operability-spec]

<!-- Reference-style links -->

## Changelog

| Date | Change                                                               |
| ---- | -------------------------------------------------------------------- |
| TBD  | Added `scoring` and `signing` stages; aligned with ADR-0004/ADR-0005 |
| TBD  | Added stage IO boundaries table; updated to stable stage identifiers |
| TBD  | Added deployment topology section; expanded bridge artifacts         |
| TBD  | Style guide migration; added frontmatter, scope, references          |

[adr-0002]: ../adr/ADR-0002-event-identity-and-provenance.md
[adr-0004]: ../adr/ADR-0004-deployment-architecture-and-inter-component-communication.md
[adr-0005]: ../adr/ADR-0005-stage-outcomes-and-failure-classification.md
[bridge-spec]: 065_sigma_to_ocsf_bridge.md
[config-ref]: 120_config_reference.md
[data-contracts]: 025_data_contracts.md
[field-tiers]: 055_ocsf_field_tiers.md
[ocsf-spec]: 050_normalization_ocsf.md
[operability-spec]: 110_operability.md
[scenarios-spec]: 030_scenarios.md
[sigma-spec]: 060_detection_sigma.md
[telemetry-spec]: 040_telemetry_pipeline.md
