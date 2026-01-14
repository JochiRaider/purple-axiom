---
title: Detection Rules (Sigma)
description: Defines how Purple Axiom compiles and evaluates Sigma rules against normalized OCSF events.
status: draft
category: spec
tags: [sigma, detection, ocsf]
related:
  - 065_sigma_to_ocsf_bridge.md
  - 070_scoring_metrics.md
  - 080_reporting.md
  - 025_data_contracts.md
  - ADR-0005-stage-outcomes-and-failure-classification.md
---

# Detection Rules (Sigma)

This specification defines how Purple Axiom compiles and evaluates Sigma rules against normalized
OCSF events using the Sigma-to-OCSF Bridge.

## Overview

Sigma rules are the default, portable detection language for Purple Axiom. Rules are evaluated
against **normalized OCSF events** (not raw logs) using the **Sigma-to-OCSF Bridge**.

See the [Sigma-to-OCSF Bridge specification][sigma-bridge].

## Why Sigma

- Portable, generic detection rule format (YAML) with broad community content
- Separates detection logic from any specific SIEM or query language

## Rule selection and filtering

### Supported rule metadata

In addition to the required fields, Purple Axiom recognizes the following Sigma metadata for
filtering and reporting:

| Field            | Purpose                                                         | Default behavior                              |
| ---------------- | --------------------------------------------------------------- | --------------------------------------------- |
| `status`         | Rule maturity (`experimental`, `test`, `stable`)                | All statuses evaluated unless filtered        |
| `level`          | Severity (`informational`, `low`, `medium`, `high`, `critical`) | All levels evaluated unless filtered          |
| `falsepositives` | Known false positive contexts                                   | Recorded in compiled plan for operator review |
| `author`         | Rule authorship                                                 | Recorded for provenance                       |
| `references`     | External references (URLs)                                      | Recorded for provenance                       |

### Configuration-driven filtering

Rule selection MAY be constrained via configuration (see the
[configuration reference](120_config_reference.md)):

- `technique_allowlist` / `technique_denylist`: filter by ATT&CK technique ID
- `status_allowlist`: filter by Sigma `status` (example: `[stable, test]`)
- `level_minimum`: exclude rules below a severity threshold (example: `medium`)

When filters are applied, the run manifest MUST record the effective filter set, and excluded rules
MUST NOT appear in coverage metrics.

## ATT&CK technique mapping

### Tag extraction

Sigma rules encode ATT&CK mappings in the `tags` array using the `attack.tXXXX` convention.

The detection engine MUST:

- Extract technique IDs from tags matching the pattern `attack\.t\d{4}(?:\.\d{3})?`
  (case-insensitive).
- Normalize extracted IDs to uppercase (example: `attack.t1059.001` → `T1059.001`).
- Populate `technique_ids` in detection instances as a deduplicated, sorted array.

### Sub-technique handling

When a rule tags both a technique and its sub-technique (example: `attack.t1059`,
`attack.t1059.001`):

- The detection instance MUST include both.
- Coverage metrics MUST credit the most specific match (sub-technique) for scoring joins.

### Unmapped rules

Rules without valid ATT&CK tags:

- Are still evaluated and may produce detection instances.
- Are excluded from technique coverage metrics.
- SHOULD be flagged in `bridge/coverage.json` under `rules_without_technique_mapping`.

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
   - Route the rule: `sigma.logsource` to an OCSF class filter (and optional producer/source
     predicates via `filters[]` OCSF filter objects).
   - Rewrite Sigma field references to OCSF JSONPaths (or SQL column expressions).
   - Produce a backend plan:
     - Batch: SQL over Parquet (DuckDB SQL MUST be the v0.1 default when
       `detection.sigma.bridge.backend` is omitted).
     - Streaming: expression plan over in-memory or stream processors.
1. **Evaluate**
   - Execute the plan over the run's OCSF event store.
   - Emit `detection_instance` rows for each match group.

## Non-executable rules

A rule is classified as **non-executable** when the bridge cannot produce a valid backend plan.
Non-executable rules are recorded in `bridge/compiled_plans/<rule_id>.plan.json` with
`executable: false` and a stable `reason_code`.

### Reason codes (normative)

| Reason code              | Category      | Description                                               |
| ------------------------ | ------------- | --------------------------------------------------------- |
| `unrouted_logsource`     | Routing       | Sigma `logsource` matches no router entry                 |
| `unmapped_field`         | Field alias   | Sigma field has no alias mapping                          |
| `raw_fallback_disabled`  | Field alias   | Rule requires `raw.*` but fallback is disabled            |
| `ambiguous_field_alias`  | Field alias   | Alias resolution is ambiguous for the routed scope        |
| `unsupported_modifier`   | Sigma feature | Modifier cannot be expressed in the backend               |
| `unsupported_operator`   | Sigma feature | Operator not in supported subset                          |
| `unsupported_regex`      | Sigma feature | Regex uses PCRE-only constructs (v0.1 default for `\|re`) |
| `unsupported_value_type` | Sigma feature | Value type incompatible with operator                     |
| `backend_compile_error`  | Backend       | Backend compilation failed                                |
| `backend_eval_error`     | Backend       | Backend evaluation failed at runtime                      |

Non-executable rules do not produce detection instances but are included in bridge coverage
reporting and contribute to gap classification.

See [ADR-0005](ADR-0005-stage-outcomes-and-failure-classification.md) for stage-level failure
semantics.

### Fail-closed behavior

If a rule cannot be routed (unknown `logsource`) or references unmapped fields, it MUST be reported
as **non-executable** for that run, with reasons recorded in the run report.

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

**Summary**: The evaluator MUST write `detections/detections.jsonl` deterministically to support
reproducible diffs and regression tests.

- Each detection instance MUST sort `matched_event_ids` using bytewise UTF-8 lexical ordering
  (case-sensitive, no locale).
- The file MUST be ordered deterministically by the following stable key tuple:
  1. `rule_id` ascending (bytewise UTF-8 lexical ordering)
  1. `first_seen_utc` ascending
  1. `last_seen_utc` ascending
  1. `matched_event_ids` ascending by lexicographic comparison of the (already-sorted) string array
- Each JSONL line MUST be encoded as UTF-8 and MUST end with a single LF (`\n`).
- Implementations SHOULD serialize each object without insignificant whitespace and with a
  deterministic key ordering to maximize byte-level stability across runtimes.

## Joining detections to ground truth

The scoring stage joins detection instances to ground truth actions to compute coverage and latency
metrics.

### Join semantics

A detection instance is **attributed** to a ground truth action when:

1. The detection's `technique_ids` intersect with the action's `technique_id`.
1. The detection's `first_seen_utc` falls within the configured time window relative to the action's
   `timestamp_utc`:
   - Window start: `action.timestamp_utc - clock_skew_tolerance_seconds`
   - Window end: `action.timestamp_utc + max_allowed_latency_seconds`
1. The detection's matched events originate from the action's `target_asset_id` (when asset
   attribution is available).

### Unattributed detections

Detections that match events but cannot be attributed to a ground truth action:

- Are recorded in `detections/detections.jsonl`.
- Are excluded from technique coverage metrics.
- MAY indicate:
  - Legitimate background activity (true positives unrelated to the scenario).
  - Rule logic issues (overly broad detection).
  - Time window misalignment.

The report SHOULD surface unattributed detection counts for operator review.

## Detection instance schema

Detection instances MUST validate against
[`detection_instance.schema.json`](../contracts/detection_instance.schema.json).

### Required fields

| Field               | Type   | Description                                      |
| ------------------- | ------ | ------------------------------------------------ |
| `rule_id`           | string | Sigma rule UUID                                  |
| `rule_title`        | string | Sigma rule title                                 |
| `rule_source`       | string | Always `"sigma"` for Sigma-originated detections |
| `run_id`            | string | Run identifier                                   |
| `first_seen_utc`    | string | ISO 8601 timestamp of earliest matched event     |
| `last_seen_utc`     | string | ISO 8601 timestamp of latest matched event       |
| `matched_event_ids` | array  | Sorted array of `metadata.event_id` references   |

### Recommended fields

| Field               | Type   | Description                                          |
| ------------------- | ------ | ---------------------------------------------------- |
| `scenario_id`       | string | Scenario identifier (when available)                 |
| `technique_ids`     | array  | Extracted ATT&CK technique IDs                       |
| `extensions.bridge` | object | Bridge provenance (mapping pack, backend, fallback)  |
| `extensions.sigma`  | object | Original Sigma metadata (`logsource`, `level`, etc.) |

## Rule provenance

Detection instances SHOULD include rule provenance in `extensions.sigma`:

| Field             | Type   | Description                                       |
| ----------------- | ------ | ------------------------------------------------- |
| `logsource`       | object | Original Sigma `logsource` (verbatim)             |
| `level`           | string | Sigma severity level                              |
| `status`          | string | Sigma maturity status                             |
| `rule_sha256`     | string | SHA-256 of canonical rule content                 |
| `rule_source_ref` | string | Origin reference (example: `sigmahq/sigma@v0.22`) |

Rule provenance enables:

- Attribution of community vs custom rules in reporting.
- Regression detection when rule content changes.
- Filtering by rule maturity in downstream dashboards.

## Gap classification

When a ground truth action lacks a matching detection, the scoring stage classifies the gap using
the normative taxonomy defined in [Scoring metrics](070_scoring_metrics.md).

Detection-related gap categories:

| Category             | Description                                                   |
| -------------------- | ------------------------------------------------------------- |
| `bridge_gap_mapping` | OCSF fields exist but bridge lacks aliases or router entries  |
| `bridge_gap_feature` | Rule requires unsupported Sigma features (correlation, regex) |
| `bridge_gap_other`   | Bridge failure not otherwise classified                       |
| `rule_logic_gap`     | Fields present, rule executable, but rule did not fire        |

Gap classification enables prioritized remediation:

- `bridge_gap_mapping`: addressable via mapping pack work
- `bridge_gap_feature`: addressable via backend enhancement
- `rule_logic_gap`: addressable via rule tuning

## Scope limitations (v0.1)

### Correlation rules

Sigma correlation rules (multi-event sequences, temporal conditions, aggregations with thresholds)
are **out of scope for v0.1**.

Rules containing `correlation` blocks MUST be marked non-executable with
`reason_code: "unsupported_correlation"`.

### Aggregation functions

Sigma aggregation keywords (`count`, `sum`, `avg`, `min`, `max`, `near`) are **out of scope for
v0.1** unless the backend explicitly supports them.

The DuckDB backend (`duckdb_sql`) does not support aggregation in v0.1. Rules requiring aggregation
MUST be marked non-executable with `reason_code: "unsupported_aggregation"`.

### Timeframe modifiers

The `timeframe` modifier is **out of scope for v0.1**. Rules specifying `timeframe` SHOULD be
evaluated without the temporal constraint, with the limitation recorded in
`extensions.bridge.ignored_modifiers`.

## References

- [Sigma-to-OCSF Bridge specification][sigma-bridge]
- [Scoring metrics specification][scoring-spec]
- [Reporting specification][reporting-spec]
- [Data contracts specification][data-contracts]
- [Configuration reference][config-ref]
- [ADR-0005: Stage outcomes and failure classification][adr-0005]
- [Sigma detection format documentation](https://sigmahq.io/docs/)
- [Sigma rule repository (SigmaHQ/sigma)](https://github.com/SigmaHQ/sigma)
- [Sigma specification repository (SigmaHQ/sigma-specification)](https://github.com/SigmaHQ/sigma-specification)
- [pySigma library (SigmaHQ/pySigma)](https://github.com/SigmaHQ/pySigma)

## Changelog

| Date       | Change            |
| ---------- | ----------------- |
| 2026-01-12 | Formatting update |

[adr-0005]: ADR-0005-stage-outcomes-and-failure-classification.md
[config-ref]: 120_config_reference.md
[data-contracts]: 025_data_contracts.md
[reporting-spec]: 080_reporting.md
[scoring-spec]: 070_scoring_metrics.md
[sigma-bridge]: 065_sigma_to_ocsf_bridge.md
