---
title: Reporting
description: Defines reporting artifacts, required outputs, trending keys, and human-readable report structure for run evaluation.
status: draft
category: spec
tags: [reporting, scoring, ci, trending]
related:
  - 070_scoring_metrics.md
  - 055_ocsf_field_tiers.md
  - 065_sigma_to_ocsf_bridge.md
  - 025_data_contracts.md
  - ADR-0005-stage-outcomes-and-failure-classification.md
---

# Reporting

This document defines the reporting artifacts, required outputs, and trending keys for Purple Axiom
runs. It specifies both machine-readable JSON outputs for CI integration and human-readable report
structures for operator review.

## Overview

The reporting stage transforms scoring outputs into actionable artifacts. Reports serve three
primary audiences: CI pipelines that gate on thresholds, operators triaging detection gaps, and
analysts tracking coverage trends over time. The reporting contract emphasizes determinism,
traceability to upstream artifacts, and alignment with the normative gap taxonomy defined in
[Scoring metrics](070_scoring_metrics.md).

## Scope

This document covers:

- Run artifact bundle structure and required outputs
- Machine-readable JSON report contracts
- Human-readable report sections and content requirements
- Trending keys for historical comparison
- Regression analysis semantics

This document does NOT cover:

- Scoring computation logic (see [Scoring metrics](070_scoring_metrics.md))
- Gap taxonomy definitions (see [Scoring metrics](070_scoring_metrics.md))
- Stage outcome semantics (see [ADR-0005](ADR-0005-stage-outcomes-and-failure-classification.md))

## Run artifact bundle

Each run produces a deterministic artifact bundle under `runs/<run_id>/`. The reporting stage
consumes upstream artifacts and emits outputs to `report/`.

### Required artifacts (v0.1)

The following artifacts MUST be present for a run to be considered reportable:

| Path                               | Source stage  | Purpose                                        |
| ---------------------------------- | ------------- | ---------------------------------------------- |
| `manifest.json`                    | orchestrator  | Run-level provenance, status, and version pins |
| `ground_truth.jsonl`               | runner        | Executed actions timeline                      |
| `scoring/summary.json`             | scoring       | Primary metrics rollup for CI and trending     |
| `normalized/mapping_coverage.json` | normalization | OCSF field coverage by class                   |
| `bridge/coverage.json`             | detection     | Sigma-to-OCSF bridge quality metrics           |
| `criteria/manifest.json`           | validation    | Criteria pack snapshot metadata (when enabled) |
| `criteria/results.jsonl`           | validation    | Per-action criteria outcomes (when enabled)    |
| `detections/detections.jsonl`      | detection     | Rule hits with matched event references        |
| `logs/health.json`                 | orchestrator  | Stage outcomes for run status derivation       |

### Optional artifacts

| Path                                       | Source stage  | Purpose                                        |
| ------------------------------------------ | ------------- | ---------------------------------------------- |
| `runner/`                                  | runner        | Per-action transcripts and cleanup evidence    |
| `runner/principal_context.json`            | runner        | Redaction-safe principal context summary       |
| `logs/cache_provenance.json`               | orchestrator  | Cache hit/miss provenance (when enabled)       |
| `plan/expanded_graph.json`                 | runner        | Compiled plan graph (v0.2+)                    |
| `plan/expansion_manifest.json`             | runner        | Matrix expansion manifest (v0.2+)              |
| `normalized/ocsf_events.*`                 | normalization | Full normalized event store (JSONL or Parquet) |
| `bridge/mapping_pack_snapshot.json`        | detection     | Bridge inputs snapshot for reproducibility     |
| `bridge/compiled_plans/`                   | detection     | Per-rule compilation outputs                   |
| `normalized/mapping_profile_snapshot.json` | normalization | Mapping profile snapshot for drift detection   |
| `security/checksums.txt`                   | signing       | SHA-256 checksums for long-term artifacts      |
| `security/signature.ed25519`               | signing       | Ed25519 signature over checksums               |

## Required JSON outputs (v0.1)

The reporting stage MUST produce the following machine-readable outputs:

| File                     | Purpose                                    | Schema reference                             |
| ------------------------ | ------------------------------------------ | -------------------------------------------- |
| `report/report.json`     | Consolidated report for external tooling   | [report schema](#report-json-schema)         |
| `report/thresholds.json` | Threshold evaluation results for CI gating | [thresholds schema](#thresholds-json-schema) |

The reporting stage MUST NOT modify upstream artifacts. It reads from `scoring/summary.json`,
`bridge/coverage.json`, `normalized/mapping_coverage.json`, and other inputs, then emits derived
outputs to `report/`.

### Upstream artifacts (consumed, not produced)

These artifacts are produced by upstream stages and referenced in the report:

| File                               | Purpose                           | Schema reference                                                    |
| ---------------------------------- | --------------------------------- | ------------------------------------------------------------------- |
| `manifest.json`                    | Run-level provenance and outcomes | [manifest schema](manifest_schema.json)                             |
| `scoring/summary.json`             | Operator-facing metrics rollup    | [summary schema](summary_schema.json)                               |
| `bridge/coverage.json`             | Sigma-to-OCSF bridge quality      | [bridge coverage schema](bridge_coverage_schema.json)               |
| `normalized/mapping_coverage.json` | OCSF normalization coverage       | [mapping coverage schema](mapping_coverage_schema.json)             |
| `criteria/manifest.json`           | Criteria pack snapshot metadata   | [criteria pack manifest schema](criteria_pack_manifest_schema.json) |

## Run status summary

The report MUST prominently display run status and the reasons for any degradation. Run status is
derived from stage outcomes per [ADR-0005](ADR-0005-stage-outcomes-and-failure-classification.md).

### Status definitions

| Status    | Meaning                                                                        | Exit code |
| --------- | ------------------------------------------------------------------------------ | --------- |
| `success` | All stages completed; all quality gates passed                                 | `0`       |
| `partial` | Artifacts usable but one or more quality gates failed or were indeterminate    | `10`      |
| `failed`  | Run not mechanically usable; required artifacts missing or stage failed closed | `20`      |

### Status degradation reasons

When status is `partial` or `failed`, the report MUST enumerate the contributing factors. Common
degradation reasons include:

| Reason code                          | Gate type     | Description                                                |
| ------------------------------------ | ------------- | ---------------------------------------------------------- |
| `tier1_coverage_below_threshold`     | Quality gate  | Tier 1 field coverage < configured threshold (default 80%) |
| `tier1_coverage_indeterminate`       | Quality gate  | No in-scope events to compute coverage                     |
| `technique_coverage_below_threshold` | Quality gate  | Technique coverage < configured threshold (default 75%)    |
| `latency_above_threshold`            | Quality gate  | Detection latency p95 > configured threshold               |
| `gap_rate_exceeded`                  | Quality gate  | One or more gap category rates exceeded budget             |
| `stage_failed_closed`                | Stage outcome | A required stage failed with `fail_closed` mode            |
| `regression_alert`                   | Quality gate  | Regression delta exceeded configured threshold(s)          |
| `cleanup_verification_failed`        | Validation    | Cleanup checks failed; run may be tainted                  |
| `revert_failed`                      | Runner        | One or more actions failed during lifecycle `revert`       |
| `teardown_failed`                    | Runner        | One or more actions failed during lifecycle `teardown`     |
| `unsupported_platform`               | Runner        | One or more actions skipped due to platform requirements   |
| `insufficient_privileges`            | Runner        | One or more actions skipped due to privilege requirements  |
| `missing_tool`                       | Runner        | One or more actions skipped due to tool/capability gates   |

## Human-readable report sections

The HTML report MUST include the following sections. JSON equivalents SHOULD be emitted in
`report/report.json` for programmatic consumption.

### Executive summary

**Summary**: High-level run outcome for operator triage.

Required content:

- Run status (`success`, `partial`, `failed`) with visual indicator
- Scenario ID, version, and technique count
- Execution window (start/end timestamps, duration)
- Target asset summary (count by OS, roles)
- Top-line coverage percentage
- Status degradation reasons (if not `success`)

### Execution context

**Summary**: Safe-by-default execution context summary that supports “show your work” debugging
without exposing sensitive raw details.

Principal context summary:

- Evidence reference: `runner/principal_context.json`.
- The report MUST treat principal context as sensitive and MUST render only redaction-safe summary
  fields (no raw usernames, SIDs, emails, access key IDs, or other secret-like identifiers).
- The report MUST disclose principal context handling as one of:
  - `present`
  - `withheld`
  - `quarantined`
  - `absent` (not produced)
- Count of principals by `kind` (from `principal_context.principals[]`).
- Count of actions with `kind=unknown` attribution (from `principal_context.action_principal_map[]`,
  counting rows whose referenced principal resolves to `kind=unknown`).
- Principals table (stable ordering, required when `handling != absent`):
  - Columns: `principal_id`, `kind`
  - Sort rows by `principal_id` ascending (UTF-8 byte order, no locale).

Cache provenance summary (when present):

- Evidence reference: `logs/cache_provenance.json` (when produced).
- Counts of cache results grouped by `(component, cache_name)`:
  - `hits` (entries with `result=hit`)
  - `misses` (entries with `result=miss`)
  - `bypassed` (entries with `result=bypassed`, when present in the contract)
- Cache summary table (stable ordering, required when the artifact is present):
  - Columns: `component`, `cache_name`, `hits`, `misses`, `bypassed` (optional), `total`
  - Sort rows by `(component, cache_name)` ascending (UTF-8 byte order, no locale).
- The report MUST NOT disclose per-entry cache `key` values unless a future explicit debug-only
  configuration gate allows it.

Deterministic ordering (normative):

- Principals MUST be sorted by `principal_id` as specified above.
- If the report renders any per-entry cache provenance rows (debug-only), it MUST follow the cache
  provenance contract ordering (entries sorted by `(component, cache_name, key)`).

JSON equivalent (recommended):

- The report JSON SHOULD mirror this section under
  `report/report.json.extensions.execution_context`, including `principals[]` sorted by
  `principal_id` and cache summaries sorted by `(component, cache_name)`.

### Action lifecycle outcomes

**Summary**: Operator-visible action execution health, separated by lifecycle phase.

Required content:

- Idempotence distribution over executed actions:
  - counts for `idempotent | non_idempotent | unknown`
- Per-phase outcome counts aggregated over actions:
  - `prepare`, `execute`, `revert`, `teardown` each with counts for `success | failed | skipped`
- A table (or list) of actions with non-success lifecycle phases (limit 25), including:
  - `action_id`, technique ID, target asset id
  - `idempotence` (`idempotent | non_idempotent | unknown`) for the action
  - non-success phase(s) and per-phase `phase_outcome`
    - When multiple non-success phases exist, phases MUST be listed in lifecycle order: `prepare`,
      `execute`, `revert`, `teardown`.
    - When retries are present in ground truth, the report MUST render attempt ordinals
      deterministically (example: `execute[0]`, `execute[1]`) and MUST preserve lifecycle order.
  - evidence references (paths under `runner/actions/<action_id>/`), including requirements
    evaluation, resolved inputs evidence, and cleanup verification references when present
    - When `runner/actions/<action_id>/resolved_inputs_redacted.json` is present, the report MUST
      treat it as sensitive and MUST NOT render resolved input values; the report SHOULD render only
      the evidence reference (artifact path) and handling.
    - The report SHOULD prefer rendering evidence links that are referenced by the ground truth
      lifecycle phase `evidence` pointers (when present), and otherwise fall back to the
      conventional runner paths.

Deterministic ordering (normative):

- The non-success lifecycle actions table MUST be sorted deterministically by the tuple:
  1. `primary_phase` order: `prepare` < `execute` < `revert` < `teardown`, where `primary_phase` is
     the earliest lifecycle phase that is not `success` for the action (considering retries).
  1. `primary_outcome` order: `failed` < `skipped`.
  1. `action_id` ascending (UTF-8 byte order, no locale).
- If multiple actions share identical tuple values (rare), implementations MAY add additional stable
  tie-breakers, but MUST NOT depend on input iteration order.

### Synthetic correlation marker

**Summary**: Correlate synthetic activity using a durable marker emitted by the runner and preserved
in normalized events.

Required content (when marker emission is enabled):

- Marker status: `enabled | disabled`.
- The marker value(s) used for the run (displayed verbatim).
- Per-action marker observability table (stable ordering, required):
  - Sort rows by `action_id` ascending.
  - Columns:
    - `action_id` (and action name when available)
    - `marker_value`
    - `observed` (`yes | no`)
    - `gap_category` (when `observed=no`, MUST be `missing_telemetry`)
- Narrative and gap integration (normative):
  - When `observed=no` for any action, the report MUST surface those actions under the existing
    `missing_telemetry` gap category in [Gap analysis](#gap-analysis) and MUST include a concise
    remediation hint that points to telemetry pipeline filtering/sampling misconfiguration as a
    primary suspect.

JSON equivalent (recommended):

- The report JSON SHOULD mirror this section under `report/report.json.extensions`, for example
  `extensions.synthetic_correlation_marker`, including aggregate counts and a `per_action[]` list
  sorted by `action_id` ascending.

### Coverage metrics

**Summary**: Detection coverage relative to executed techniques.

Required content:

- `techniques_executed`: count of unique techniques in ground truth
- `techniques_covered`: count with at least one detection
- `coverage_pct`: `techniques_covered / techniques_executed * 100`
- Per-technique breakdown table with columns: technique ID, executed (bool), covered (bool),
  detection count, first detection latency (ms)

### Latency distribution

**Summary**: Time from action execution to first detection.

Required content:

- Percentile distribution: p50, p90, p95, max (in milliseconds)
- Histogram or distribution visualization (HTML only)
- Techniques with latency exceeding threshold (flagged)

### Detection fidelity

**Summary**: Quality of detection matches.

Required content:

- Fidelity tier counts from `scoring/summary.json`:
  - `exact`: detection matched expected event with high confidence
  - `partial`: detection matched with reduced confidence (time window, field subset)
  - `weak`: detection present but match quality uncertain
- Fidelity breakdown by technique (when available)

### Gap analysis

**Summary**: Categorized failure reasons aligned with the normative gap taxonomy.

The report MUST classify failures using the categories defined in
[Scoring metrics](070_scoring_metrics.md). Failure categories are mutually exclusive and
collectively exhaustive for detection gaps.

#### Gap taxonomy (normative)

| Category                      | Description                                               | Addressability                |
| ----------------------------- | --------------------------------------------------------- | ----------------------------- |
| `missing_telemetry`           | Expected signals absent for executed action               | Collector/endpoint config     |
| `criteria_unavailable`        | No matching criteria entry in pinned pack                 | Criteria pack authoring       |
| `criteria_misconfigured`      | Criteria entry exists but cannot be evaluated             | Criteria pack fix             |
| `normalization_gap`           | Events exist but required OCSF fields missing             | Mapping profile work          |
| `bridge_gap_mapping`          | OCSF fields exist but bridge lacks aliases/router entries | Mapping pack work             |
| `bridge_gap_feature`          | Rule requires unsupported Sigma features                  | Backend enhancement           |
| `bridge_gap_other`            | Bridge failure not otherwise classified                   | Investigation required        |
| `rule_logic_gap`              | Fields present, rule executable, but rule did not fire    | Rule tuning                   |
| `cleanup_verification_failed` | Cleanup invoked but verification checks failed            | Runner/scenario investigation |

Required content:

- Aggregate counts per gap category
- Top failures by category (limit 10 per category) with:
  - Technique ID
  - Measurement layer
  - Evidence references (paths to relevant artifacts)
  - Actionable remediation hint
- Gap rate percentages relative to executed actions

#### Measurement contract for conclusions (normative)

Every reported gap MUST be attributable to exactly one measurement layer. This enables deterministic
triage by answering "which layer is broken" and "which artifacts prove it" for every conclusion.

Measurement layers (closed set):

- `telemetry`
- `normalization`
- `detection`
- `scoring`

Normative requirements:

- Each gap entry MUST include `measurement_layer`.
- `measurement_layer` MUST match the mapping in [Scoring metrics](070_scoring_metrics.md) (Gap
  category to measurement layer mapping, normative).
- Each gap entry MUST include `evidence_refs[]` that justify the classification.
- Evidence refs MUST be run-relative artifact paths. Selectors are optional.
- Evidence refs MUST NOT embed secrets or raw sensitive identifiers.

Minimum evidence refs by measurement layer:

- telemetry: MUST include `logs/health.json` and SHOULD include `telemetry/` validation artifacts
  when present.
- normalization: MUST include `normalized/mapping_coverage.json`.
- detection: MUST include `bridge/coverage.json` and SHOULD include `detections/detections.jsonl`.
- scoring: MUST include `scoring/summary.json` and SHOULD include `criteria/**` artifacts when
  applicable to the gap category.

Evidence ref shape (recommended for JSON):

- `artifact_path` (string; run-relative)
- `selector` (string; optional; see selector grammar in `025_data_contracts.md`)
- `handling` (enum): `present | withheld | quarantined | absent`

Deterministic ordering (normative):

- Any `top_failures[]` array MUST be sorted by:
  1. `gap_category` ascending (UTF-8 byte order, no locale)
  1. `technique_id` ascending (UTF-8 byte order, no locale)
  1. `action_id` ascending (UTF-8 byte order, no locale), when present
- Within any `evidence_refs[]` array, entries MUST be sorted by `artifact_path` ascending.

### Tier 1 normalization coverage

**Summary**: OCSF Core Common field presence across normalized events.

This section surfaces the Tier 1 coverage gate defined in
[OCSF field tiers](055_ocsf_field_tiers.md).

Required content:

- `tier1_field_coverage_pct`: aggregate coverage percentage
- `tier1_field_coverage_state`: `ok`, `below_threshold`, or `indeterminate_no_events`
- `tier1_field_coverage_threshold_pct`: configured threshold (default 80%)
- Gate outcome: pass/fail with explanation
- Per-field breakdown table (SHOULD include):
  - Field path (e.g., `device.hostname`, `actor.user.name`)
  - Presence count
  - Presence percentage
  - Fields below 50% presence (flagged)

### Per-source breakdown

**Summary**: Metrics segmented by telemetry source type.

Detection engineering requires understanding which sources contribute to coverage and gaps.

Required content (per `source_type`):

- Event count
- Tier 1 field coverage percentage
- Detection count
- Gap breakdown (counts per category)
- Top unmapped fields (when `normalization_gap` present)

Source types MUST align with `metadata.source_type` values in normalized events (e.g., `sysmon`,
`windows_security`, `osquery`, `auditd`).

### Sigma-to-OCSF bridge health

**Summary**: Bridge compilation and routing quality.

Required content (from `bridge/coverage.json`):

- `total_rules`: rules attempted
- `routed_rules`: rules with valid logsource routing
- `executable_rules`: rules that compiled successfully
- `non_executable_rules`: rules that failed compilation
- `fallback_used_rules`: rules requiring `raw.*` fallback

Breakdown tables:

- By `logsource.category`: routed vs unrouted counts
- Top unrouted categories (limit 20)
- Top unmapped Sigma fields (limit 20) with occurrence counts
- Non-executable reason distribution (from `non_executable_reasons`)

### Criteria evaluation

**Summary**: Validation outcomes against criteria packs (when enabled).

Required content:

- Criteria pack ID and version (from `criteria/manifest.json`)
- Aggregate rates:
  - `criteria_pass_rate`
  - `criteria_fail_rate`
  - `criteria_skipped_rate`
- Per-technique criteria outcomes
- Criteria signal latency (p50, p90) when measurable
- Skipped reasons breakdown (no matching criteria, evaluation disabled, action failed)

### Requirements & environment gates

**Summary**: Action-level preflight gates derived from declared requirements (platform, privilege,
tools/capabilities) when requirements evaluation is enabled.

Required content:

- Aggregate unmet requirement counts by `reason_code`:
  - `unsupported_platform`
  - `insufficient_privileges`
  - `missing_tool`
- Affected actions table (limit 50) including:
  - `action_id` and technique ID (and action name when available)
  - primary unmet `reason_code` (one of the above)
  - Evidence reference: link to `runner/actions/<action_id>/requirements_evaluation.json`
  - Evidence handling note: `present | withheld | quarantined`
- Narrative integration (normative):
  - When any unmet requirements exist, the report MUST include the corresponding reason codes in
    [Status degradation reasons](#status-degradation-reasons) and MUST surface a concise explanation
    in the executive summary “why did it fail?” narrative.

Disclosure minimization (normative):

- Unless explicitly configured otherwise, this section MUST NOT render over-specific probe details
  (example: exact tool paths, full version strings); it MUST prefer reason codes and run-relative
  evidence references.

### Cleanup verification

**Summary**: Post-action cleanup status.

Required content:

- Cleanup invocation count vs skipped count
- Verification outcomes: pass/fail counts
- Failed verifications with evidence references (links to `runner/` artifacts)
- Cleanup policy applied (from scenario or range config)

### State reconciliation

**Summary**: Post-action drift detection between recorded effects and observed environment state
(when enabled).

Required content:

- Reconciliation coverage:
  - Actions reconciled count vs not-enabled/skipped count
- Action-level status distribution (from per-action reconciliation reports):
  - `clean`
  - `drift_detected`
  - `unknown`
  - `skipped`
- Aggregate item counts (sum of `summary` fields across actions):
  - `items_total`
  - `drift_detected`
  - `unknown`
  - `skipped`
- Remediation disposition summary:
  - `repaired` vs `requires_review`
  - For v0.1, repair is out of scope; the report MUST render `repaired=0` and MUST treat every drift
    item as `requires_review`.
- Drift details table (limit 50):
  - `action_id` and `action_key`
  - `source` (`cleanup_verification | side_effect_ledger`)
  - `check_id` (when `source=cleanup_verification`) or `ledger_seq` (when
    `source=side_effect_ledger`)
  - `status` (`match | mismatch | unknown | skipped`)
  - `reason_code`
  - Evidence reference: link to `runner/actions/<action_id>/state_reconciliation_report.json`

### Event volume metrics

**Summary**: Telemetry throughput for capacity planning.

Required content:

- Total events captured (raw)
- Total events normalized
- Events per second (EPS) during execution window:
  - Peak EPS
  - Average EPS
- Events by `source_type`
- Events by `class_uid`

### Version inventory

**Summary**: Component versions for reproducibility.

Required content (from `manifest.versions`):

- `purple_axiom`
- `ocsf_version`
- `otel_collector_version`
- `normalizer_version`
- `sigma_compiler_version`
- `pipeline_version`
- `rule_set_version`

Additional provenance:

- Mapping pack version (from `bridge/coverage.json` → `mapping_pack_ref`)
- Criteria pack version (from `criteria/manifest.json`)
- Range config SHA-256 (from `manifest.inputs.range_yaml_sha256`)

## Regression analysis

When a baseline run is provided, the report MUST include a regression summary comparing the current
run against the baseline.

### Regression JSON contract (normative)

When regression analysis is performed, the report JSON MUST include `report/report.json.regression`
as a structured object. This object is the authoritative machine-readable regression surface for CI
and downstream tools. The authoritative regression surface is `report/report.json.regression`.
Implementations MUST NOT emit `report/regression.json` or `report/regression_deltas.jsonl`.

Required fields:

- `baseline`:
  - `run_id` (string; baseline run id)
  - `generated_at_utc` (string; baseline report generation timestamp)
  - `manifest_ref` (string; run-relative artifact path or content-addressed reference)
- `comparability_checks[]`:
  - Each entry MUST include:
    - `key` (string)
    - `baseline_value` (string)
    - `current_value` (string)
    - `match` (boolean)
  - `comparability_checks[]` MUST include all keys listed in [Comparable keys](#comparable-keys).
  - The array MUST be emitted in the same order as the table in [Comparable keys](#comparable-keys).
- `metric_surface_ref`:
  - A string reference to the comparable metric surface defined in
    [Scoring metrics](070_scoring_metrics.md) (Regression comparable metric surface, normative).
- `deltas[]`:
  - Each entry MUST include:
    - `metric_id` (string)
    - `kind` (string)
    - `unit` (string)
    - `baseline_value` (number or integer; may be `null` when indeterminate)
    - `current_value` (number or integer; may be `null` when indeterminate)
    - `delta` (number or integer; may be `null` when indeterminate)
    - `tolerance` (number or integer)
    - `within_tolerance` (boolean; MUST be false when any of baseline/current/delta is null)
    - `regression_flag` (boolean)
  - `deltas[]` MUST be sorted by `metric_id` ascending (UTF-8 byte order, no locale).
  - Delta rounding, tolerance semantics, and indeterminate handling MUST follow
    [Scoring metrics](070_scoring_metrics.md) (Deterministic comparison semantics, normative).
- `regression_alerted` (boolean)
- `alert_reasons[]`:
  - Stable list of tokens describing which thresholds were exceeded.
  - MUST be sorted ascending (UTF-8 byte order, no locale).

Interaction with status recommendation (normative):

- If `regression_alerted=true`, then:
  - `report/thresholds.json.status_recommendation` MUST be downgraded to at least `partial`, and
  - `report/report.json.status_reasons[]` MUST include `regression_alert`.
- Implementations MAY support a strict policy that treats regression alerts as `failed`, but that
  policy MUST be explicitly configured and MUST be recorded in `report/thresholds.json` (TODO:
  specify the config key in `120_config_reference.md`).

### Comparable keys

Two runs are comparable when the following keys match:

| Key                | Source                               | Match requirement |
| ------------------ | ------------------------------------ | ----------------- |
| `scenario_id`      | `manifest.scenario.scenario_id`      | MUST match        |
| `scenario_version` | `manifest.scenario.scenario_version` | SHOULD match      |
| `ocsf_version`     | `manifest.versions.ocsf_version`     | SHOULD match      |

Runs with mismatched `scenario_id` MUST NOT be compared. Mismatched `scenario_version` or
`ocsf_version` SHOULD trigger a warning in the regression summary.

### Regression deltas

The report MUST compute deltas for comparable metrics as defined in
[Scoring metrics](070_scoring_metrics.md) (Regression comparable metric surface, normative).

At minimum, the report MUST compute regression deltas for:

| Metric                          | Delta computation    | Regression threshold |
| ------------------------------- | -------------------- | -------------------- |
| `technique_coverage_rate`       | `current - baseline` | < -0.0500            |
| `detection_latency_p95_seconds` | `current - baseline` | > +60.000            |
| `tier1_field_coverage_pct`      | `current - baseline` | < -0.0500            |
| `missing_telemetry_count`       | `current - baseline` | > +2                 |
| `bridge_gap_mapping_count`      | `current - baseline` | > +5                 |

A regression is flagged when any delta exceeds the configured threshold.

### Regression summary content

- Baseline `run_id` and timestamp
- Comparable keys status (match/mismatch warnings)
- Delta table with: metric, baseline value, current value, delta, regression flag
- New failures not present in baseline (technique ID + gap category)
- Resolved failures present in baseline but not current

Deterministic ordering (normative):

- The delta table MUST be sorted by `metric_id` ascending (UTF-8 byte order, no locale).
- The "new failures" list and "resolved failures" list MUST be sorted by:
  1. `gap_category` ascending (UTF-8 byte order, no locale)
  1. `technique_id` ascending (UTF-8 byte order, no locale)
  1. `action_id` ascending (UTF-8 byte order, no locale), when present

## Trend tracking

Trending enables longitudinal analysis across runs. Downstream dashboards and exporters MUST use the
stable trending dimensions defined here.

### Trending keys (normative)

| Key                                         | Source                                      | Requirement |
| ------------------------------------------- | ------------------------------------------- | ----------- |
| `scenario_id`                               | `manifest.scenario.scenario_id`             | REQUIRED    |
| `scenario_version`                          | `manifest.scenario.scenario_version`        | SHOULD      |
| `rule_set_version`                          | `manifest.versions.rule_set_version`        | REQUIRED    |
| `pipeline_version`                          | `manifest.versions.pipeline_version`        | REQUIRED    |
| `extensions.bridge.mapping_pack_version`    | `bridge/coverage.json` → `mapping_pack_ref` | RECOMMENDED |
| `versions.ocsf_version`                     | `manifest.versions.ocsf_version`            | RECOMMENDED |
| `extensions.criteria.criteria_pack_version` | `criteria/manifest.json`                    | RECOMMENDED |

### Non-trending keys

- `run_id`: unique per execution; MUST NOT be used as a trending key
- `started_at_utc`, `ended_at_utc`: timestamps for ordering, not grouping

### Trend history table

Implementations MAY maintain a history table for trend queries. Recommended schema:

```sql
CREATE TABLE run_trends (
  scenario_id TEXT NOT NULL,
  scenario_version TEXT,
  rule_set_version TEXT NOT NULL,
  pipeline_version TEXT NOT NULL,
  mapping_pack_version TEXT,
  ocsf_version TEXT,
  criteria_pack_version TEXT,
  run_id TEXT NOT NULL,
  started_at_utc TIMESTAMP NOT NULL,
  coverage_pct REAL,
  latency_p95_ms INTEGER,
  tier1_coverage_pct REAL,
  status TEXT,
  PRIMARY KEY (run_id)
);
```

### Regression alerts

Exporters SHOULD emit alerts when:

- Coverage drops > 5 percentage points vs trailing 5-run average
- Latency p95 increases > 50% vs trailing 5-run average
- New gap categories appear that were not present in prior runs

## Threshold evaluation output

The reporting stage MUST emit `report/thresholds.json` for CI integration.

### Thresholds JSON schema

```json
{
  "contract_version": "0.1.0",
  "run_id": "<uuid>",
  "evaluated_at_utc": "<ISO8601>",
  "overall_pass": true,
  "gates": [
    {
      "gate_id": "min_technique_coverage",
      "threshold": 0.75,
      "actual": 0.82,
      "pass": true
    },
    {
      "gate_id": "min_tier1_field_coverage",
      "threshold": 0.80,
      "actual": 0.78,
      "pass": false,
      "degradation_reason": "tier1_coverage_below_threshold"
    }
  ],
  "status_recommendation": "partial"
}
```

Required gates (v0.1):

- `min_technique_coverage` (default: 0.75)
- `max_allowed_latency_seconds` (default: 300)
- `min_tier1_field_coverage` (default: 0.80)
- `max_missing_telemetry_rate` (default: 0.10)
- `max_normalization_gap_rate` (default: 0.05)
- `max_bridge_gap_mapping_rate` (default: 0.10)
- `max_bridge_gap_feature_rate` (default: 0.40)
- `max_bridge_gap_other_rate` (default: 0.02)

Regression gates (required only when a baseline is provided):

- `regression_alert`:
  - The gate MUST fail when `report/report.json.regression.regression_alerted=true`.
  - When the gate fails, `degradation_reason` MUST be `regression_alert`.
  - The reporting stage MUST apply the "Interaction with status recommendation" rules in
    [Regression JSON contract](#regression-json-contract-normative).

## Report JSON schema

The `report/report.json` output MUST conform to the following structure:

```json
{
  "contract_version": "0.1.0",
  "run_id": "<uuid>",
  "generated_at_utc": "<ISO8601>",
  "status": "success | partial | failed",
  "status_reasons": ["<reason_code>"],
  "status_reason_details": [
    {
      "reason_code": "<reason_code>",
      "measurement_layer": "telemetry | normalization | detection | scoring",
      "evidence_refs": [
        {
          "artifact_path": "<run-relative path>",
          "selector": "<optional selector>",
          "handling": "present | withheld | quarantined | absent"
        }
      ]
    }
  ],
  "executive_summary": {
    "scenario_id": "<string>",
    "scenario_version": "<string>",
    "techniques_executed": 10,
    "techniques_covered": 8,
    "coverage_pct": 80.0,
    "duration_seconds": 300,
    "target_count": 2
  },
  "plan": {
    "model_version": "<semver>",
    "plan_type": "<string>",
    "node_count": 10,
    "group_count": 1,
    "templates_executed": 10
  },  
  "coverage": { },
  "latency": { },
  "fidelity": { },
  "gaps": {
    "by_category": {
      "<gap_category>": {
        "measurement_layer": "telemetry | normalization | detection | scoring",
        "count": 0,
        "rate": 0.0,
        "top_failures": [
          {
            "gap_category": "<gap_category>",
            "measurement_layer": "telemetry | normalization | detection | scoring",
            "technique_id": "<string>",
            "action_id": "<string>",
            "evidence_refs": [
              {
                "artifact_path": "<run-relative path>",
                "selector": "<optional selector>",
                "handling": "present | withheld | quarantined | absent"
              }
            ],
            "remediation_hint": "<string>"
          }
        ]
      }
    },
    "top_failures": [
      {
        "gap_category": "<gap_category>",
        "measurement_layer": "telemetry | normalization | detection | scoring",
        "technique_id": "<string>",
        "action_id": "<string>",
        "evidence_refs": [
          {
            "artifact_path": "<run-relative path>",
            "selector": "<optional selector>",
            "handling": "present | withheld | quarantined | absent"
          }
        ],
        "remediation_hint": "<string>"
      }
    ]
  },
  "tier1_coverage": { },
  "per_source": [ ],
  "bridge_health": { },
  "criteria_evaluation": { },
  "cleanup_verification": { },
  "event_volume": { },
  "versions": { },
  "regression": {
    "baseline": {
      "run_id": "<uuid>",
      "generated_at_utc": "<ISO8601>",
      "manifest_ref": "<string>"
    },
    "comparability_checks": [
      {
        "key": "<string>",
        "baseline_value": "<string>",
        "current_value": "<string>",
        "match": true
      }
    ],
    "metric_surface_ref": "070_scoring_metrics.md#regression-comparable-metric-surface-normative",
    "deltas": [
      {
        "metric_id": "<string>",
        "kind": "<string>",
        "unit": "<string>",
        "baseline_value": 0,
        "current_value": 0,
        "delta": 0,
        "tolerance": 0,
        "within_tolerance": true,
        "regression_flag": false
      }
    ],
    "regression_alerted": false,
    "alert_reasons": [ ]
  },
  "extensions": {
    "execution_context": {
      "principal_context": {
        "artifact_path": "runner/principal_context.json",
        "handling": "present | withheld | quarantined | absent",
        "counts_by_kind": { },
        "unknown_kind_actions": 0,
        "principals": [ ]
      },
      "cache_provenance": {
        "artifact_path": "logs/cache_provenance.json",
        "present": false,
        "by_cache": [ ]
      }
    }
  }
}
```

Full schema definition: `report_schema.json` (to be added to contracts/).

## HTML report structure

The HTML report SHOULD follow this layout:

1. **Header**: Run ID, status badge, scenario name, execution timestamp
1. **Executive summary card**: Key metrics at a glance
1. **Navigation**: Jump links to each section
1. **Sections**: Each section from [Human-readable report sections](#human-readable-report-sections)
1. **Footer**: Version inventory, generation timestamp, links to raw artifacts

### Styling guidance

- Use semantic HTML5 elements
- Status indicators: green (success), yellow (partial), red (failed)
- Tables SHOULD be sortable where appropriate
- Threshold violations SHOULD be visually flagged
- Include collapsible detail sections for large tables

## CI integration

### Exit codes

The reporting stage MUST set exit codes aligned with
[ADR-0005](ADR-0005-stage-outcomes-and-failure-classification.md):

| Exit code | Meaning                                                 |
| --------- | ------------------------------------------------------- |
| `0`       | Run status `success`; all gates passed                  |
| `10`      | Run status `partial`; artifacts usable but gates failed |
| `20`      | Run status `failed`; artifacts not usable               |

### CI workflow integration

```yaml
# Example GitHub Actions step
- name: Evaluate thresholds
  run: |
    STATUS=$(jq -r '.status_recommendation' report/thresholds.json)
    if [ "$STATUS" = "failed" ]; then exit 20; fi
    if [ "$STATUS" = "partial" ]; then exit 10; fi
    exit 0
```

## References

- [Manifest schema](manifest_schema.json)
- [Summary schema](summary_schema.json)
- [Bridge coverage schema](bridge_coverage_schema.json)
- [Mapping coverage schema](mapping_coverage_schema.json)
- [Criteria pack manifest schema](criteria_pack_manifest_schema.json)
- [Scoring metrics specification](070_scoring_metrics.md)
- [OCSF field tiers specification](055_ocsf_field_tiers.md)
- [Sigma-to-OCSF bridge specification](065_sigma_to_ocsf_bridge.md)
- [ADR-0005: Stage outcomes and failure classification](ADR-0005-stage-outcomes-and-failure-classification.md)

## Changelog

| Date       | Change                                                                                     |
| ---------- | ------------------------------------------------------------------------------------------ |
| 2026-01-18 | Codify regression JSON contract and measurement-layer evidence pointers for gaps           |
| 2026-01-13 | Major revision: added normative requirements, gap taxonomy alignment, per-source breakdown |
| 2026-01-12 | Formatting update                                                                          |
