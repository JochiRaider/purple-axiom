---
title: "Architecture"
description: "Defines the high-level system flow, components, and extension points."
status: draft
---

# Architecture

This document describes the high-level architecture of Purple Axiom, including the primary components, execution flow, and supported extension points.

## Overview

The system resolves lab inventory, executes scenarios, captures telemetry, normalizes events, evaluates criteria, and produces detection and reporting outputs. Each component is designed to preserve determinism and evidence for scoring and comparison.

## High-level flow

```text
Lab provider -> Resolved lab inventory snapshot -> Scenario runner -> Ground truth timeline + runner artifacts -> Telemetry collectors -> OTel collector pipeline -> Normalizer -> OCSF event store -> Criteria evaluator (sidecar pack) -> Criteria results -> Sigma-to-OCSF bridge (router + field aliases) -> Detection engine (Sigma) -> Results -> Report generator -> HTML + JSON + artifacts
```

## Components

### Lab provider (inventory resolution)

- Resolves a concrete list of target assets and connection metadata from an external source.
- Implementations may be:
  - manual (inline `lab.assets`)
  - Ludus (consume generated inventory export)
  - Terraform (consume `terraform output -json` or an exported inventory file)
- Produces a run-scoped "lab inventory snapshot" recorded in the run bundle and referenced by the manifest.
- This snapshot is treated as an input for determinism (hashable, diffable).

### Scenario runner

- Executes test plans (Atomic tests for v0.1; Caldera operations are a future candidate).
- Emits a signed, append-only timeline: what ran, when, where, and with what *resolved* inputs.
- MUST record resolved target identifiers (asset_id plus resolved host identity) so that ground truth remains valid even if the provider inventory changes later.

**Runner artifacts (evidence tier)**:

- Captures executor transcripts (stdout/stderr) and execution metadata (exit codes, durations).
- Treats cleanup as a staged lifecycle (invoke -> verify) and records verification results.

### Telemetry collectors

- Endpoint logs (Windows Event Log receiver for OTel contrib; includes Sysmon Operational channel on Windows; Linux journald/syslog options later).
- Optional: osquery, EDR exports. Network sensors (pcap/netflow) are phase 2 for collection, but v0.1 reserves placeholder contracts.

### Normalizer

- Maps raw telemetry to OCSF categories/classes.
- Attaches provenance fields: source, host, tool version, scenario_id, run_id.

### Criteria evaluator

Evaluates an externalized, versioned criteria pack against the normalized OCSF store.

Responsibilities:

- Load a criteria pack snapshot pinned in the run manifest.
- For each executed action (ground truth), match the appropriate criteria entry and evaluate expected signals within configured time windows.
- Emit `criteria_results.jsonl` for scoring and reporting.
- Emit cleanup verification results (either as part of criteria results or as runner-side evidence referenced by them).

### Sigma-to-OCSF bridge

- Contract-driven compatibility layer that allows Sigma rules (logsource + fields) to be evaluated against OCSF-normalized events.
- Artifacts:
  - Logsource router: `sigma.logsource` -> OCSF class filter (and optional producer/source predicates)
  - Field alias map: Sigma field names -> OCSF JSONPaths (or SQL column expressions)
  - Backend adapters: compile to a batch plan (SQL over Parquet) or stream plan (in-memory)

### Detection engine

- Loads Sigma rules and evaluates them against normalized OCSF events via the Sigma-to-OCSF Bridge.
- Produces detection instances, technique coverage, and latency measures.
- Fail-closed behavior: if the bridge cannot route a rule (unknown `logsource`) or map a referenced field, the rule is reported as non-executable for that run.

### Reporting

- Generates report bundle: HTML scorecard + JSON results + run manifest.

## Extension points

- New lab providers (manual, Ludus, Terraform, other)
- New runners (beyond Caldera/Atomic)
- New telemetry sources
- New schema mappings (OCSF profiles/versions)
- New rule languages (beyond Sigma, like yara or suricata)
- New Sigma bridge mapping packs (logsource router + field aliases)
- New evaluator backends (DuckDB/SQL, Tenzir, other engines)

## Key decisions

- Lab providers resolve target inventory into a run-scoped snapshot for determinism.
- Scenario runners emit ground truth and evidence artifacts for traceability.
- Criteria evaluation and Sigma detection depend on normalized OCSF event storage.
- Bridge failures are treated as fail-closed rule evaluation.

## References

- TODO: Add links to scenario, data contract, and pipeline specs used by this architecture.

## Changelog

| Date | Change |
| --- | --- |
| TBD | Style guide migration (no technical changes) |
