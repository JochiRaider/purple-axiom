---
title: "Detection Rules (Sigma)"
description: "Defines how Purple Axiom compiles and evaluates Sigma rules against normalized OCSF events."
status: draft
category: spec
tags: [sigma, detection, ocsf]
related:
  - 065_sigma_to_ocsf_bridge.md
---

# Detection Rules (Sigma)

This specification defines how Purple Axiom compiles and evaluates Sigma rules against normalized OCSF events using the Sigma-to-OCSF Bridge.

## Overview

Sigma rules are the default, portable detection language for Purple Axiom. Rules are evaluated against **normalized OCSF events** (not raw logs) using the **Sigma-to-OCSF Bridge**.

See the [Sigma-to-OCSF Bridge specification][sigma-bridge].

## Why Sigma

- Portable, generic detection rule format (YAML) with broad community content
- Separates detection logic from any specific SIEM or query language

## Rule lifecycle

- The `rules/` directory is versioned and tagged.
- Each rule MUST declare:
  - `title`, `id`, `status`
  - `logsource` (used for routing via the Sigma-to-OCSF Bridge)
  - `detection` selectors and conditions
  - `tags` (include ATT&CK technique tags when available)

## Execution model

Sigma evaluation is a two-stage process.

1. **Compile (bridge-aware)**
   - Select a bridge mapping pack (router + field aliases).
   - Route the rule: `sigma.logsource` to an OCSF class filter (and optional producer/source predicates via `filters[]` OCSF filter objects).
   - Rewrite Sigma field references to OCSF JSONPaths (or SQL column expressions).
   - Produce a backend plan:
     - Batch: SQL over Parquet (DuckDB SQL MUST be the v0.1 default when `detection.sigma.bridge.backend` is omitted).
     - Streaming: expression plan over in-memory or stream processors.
1. **Evaluate**
   - Execute the plan over the run's OCSF event store.
   - Emit `detection_instance` rows for each match group.

### Fail-closed behavior

If a rule cannot be routed (unknown `logsource`) or references unmapped fields, it MUST be reported as **non-executable** for that run, with reasons recorded in the run report.

## Outputs

- Output file: `detections/detections.jsonl` (one JSONL line per detection instance)

Each detection instance includes:

- `rule_id`, `rule_title`, `rule_source = "sigma"`
- `run_id`, optional `scenario_id`
- `first_seen_utc`, `last_seen_utc`
- `matched_event_ids` (references `metadata.event_id` in the OCSF store)
- `technique_ids` when available
- Recommended: `extensions.bridge` metadata (mapping pack id/version, backend, fallback usage)

### Deterministic emission

**Summary**: The evaluator MUST write `detections/detections.jsonl` deterministically to support reproducible diffs and regression tests.

- Each detection instance MUST sort `matched_event_ids` using bytewise UTF-8 lexical ordering (case-sensitive, no locale).
- The file MUST be ordered deterministically by the following stable key tuple:
  1. `rule_id` ascending (bytewise UTF-8 lexical ordering)
  1. `first_seen_utc` ascending
  1. `last_seen_utc` ascending
  1. `matched_event_ids` ascending by lexicographic comparison of the (already-sorted) string array
- Each JSONL line MUST be encoded as UTF-8 and MUST end with a single LF (`\n`).
- Implementations SHOULD serialize each object without insignificant whitespace and with a deterministic key ordering to maximize byte-level stability across runtimes.

## References

- [Sigma-to-OCSF Bridge specification][sigma-bridge]
- [Sigma detection format documentation](https://sigmahq.io/docs/)
- [Sigma rule repository (SigmaHQ/sigma)](https://github.com/SigmaHQ/sigma)
- [Sigma specification repository (SigmaHQ/sigma-specification)](https://github.com/SigmaHQ/sigma-specification)
- [pySigma library (SigmaHQ/pySigma)](https://github.com/SigmaHQ/pySigma)

[sigma-bridge]: 065_sigma_to_ocsf_bridge.md

## Changelog

| Date       | Change            |
| ---------- | ----------------- |
| 2026-01-12 | Formatting update |
