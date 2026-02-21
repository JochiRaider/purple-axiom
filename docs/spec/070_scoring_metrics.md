---
title: Scoring and metrics
description: Defines scoring metrics, gates, thresholds, and default weights for run evaluation.
status: draft
category: spec
tags: [scoring, metrics, gates, thresholds]
related:
  - 025_data_contracts.md
  - 055_ocsf_field_tiers.md
  - 060_detection_sigma.md
  - 080_reporting.md
  - 100_test_strategy_ci.md
  - 120_config_reference.md
  - ../adr/ADR-0005-stage-outcomes-and-failure-classification.md
---

# Scoring and metrics

## Stage contract header

### Stage ID

- `stage_id`: `scoring`

### Owned output roots (published paths)

- `scoring/`

### Inputs/Outputs

This section is the stage-local view of:

- the stage boundary table in
  [ADR-0004](../adr/ADR-0004-deployment-architecture-and-inter-component-communication.md), and
- the contract bindings in [contract_registry.json](../contracts/contract_registry.json).

#### Contract-backed outputs

| contract_id | path/glob              | Required?                              |
| ----------- | ---------------------- | -------------------------------------- |
| `summary`   | `scoring/summary.json` | required (when `scoring.enabled=true`) |

#### Required inputs

| contract_id           | Where found                        | Required?                                        |
| --------------------- | ---------------------------------- | ------------------------------------------------ |
| `range_config`        | `inputs/range.yaml`                | required                                         |
| `ground_truth`        | `ground_truth.jsonl`               | required                                         |
| `criteria_result`     | `criteria/results.jsonl`           | required (when `validation.enabled=true`)        |
| `detection_instance`  | `detections/detections.jsonl`      | required (when `detection.sigma.enabled=true`)   |
| `mapping_coverage`    | `normalized/mapping_coverage.json` | required                                         |
| `parquet_schema_snapshot` | `normalized/ocsf_events/_schema.json` | required (Tier 1 coverage + latency attribution; consumes Parquet dataset at `normalized/ocsf_events/**`) |

Notes:

- For `manifest.versions.contracts_version >= 0.2.0`, JSONL (`normalized/ocsf_events.jsonl`) MUST NOT be required/used; it is legacy v0.1.x only.

- Scoring consumes additional stage outputs (for example `bridge/`,
  `normalized/mapping_profile_snapshot.json`) but those are not required for the minimal contracted
  scoring summary.

### Config keys used

- `scoring.*` (gap taxonomy selection, thresholds, weights)

### Default fail mode and outcome reasons

- Default `fail_mode`: `fail_closed`
- Stage outcome reason codes: see
  [ADR-0005](../adr/ADR-0005-stage-outcomes-and-failure-classification.md) § "Scoring stage
  (`scoring`)".

### Isolation test fixture(s)

- `tests/fixtures/scoring/`
- See also: `tests/fixtures/reporting/defense_outcomes/` and the measurement contract fixtures
  described in `100_test_strategy_ci.md` (scoring inputs exercised end-to-end).

See the [fixture index](100_test_strategy_ci.md#fixture-index) for the canonical fixture-root
mapping.

This document defines how Purple Axiom computes scoring metrics, applies quality gates, and
interprets results for CI and operator reporting. It establishes default thresholds and weightings
for v0.1 while keeping evaluation deterministic and auditable.

## Concepts

- Ground truth action: a known technique/test execution (with timestamp + target)
- Action template: stable procedure identity (`template_id`) used for cross-run aggregation.
- Action instance: a run-scoped execution instance (`action_id`).
  - v0.1: legacy `s<positive_integer>`.
  - v0.2+: deterministic `pa_aid_v1_<32hex>` (see data contracts).
- Detection: a rule hit recorded in `detections/detections.jsonl` as a detection instance.
  - Required identifiers: `run_id`, `rule_id`.
  - Required time bounds: `first_seen_utc`, `last_seen_utc`.
  - Required evidence linkage: `matched_event_ids` (OCSF `metadata.event_id` values).
  - `technique_ids` SHOULD be present when the rule provides ATT&CK tags; technique coverage joins
    MUST ignore detections without any technique ids (see
    [Detection Rules (Sigma)](060_detection_sigma.md)).

### Defense outcomes v0.1 (normative)

Purpose: Provide an operator-facing outcome classification per action instance and per technique,
derived deterministically from per-tool outcomes. This is modeled after VECTR’s "tool outcomes →
test case outcome" derivation (priority-based reduction).

#### Outcome tokens (normative)

The following outcome tokens are the complete, closed set for v0.1:

- `blocked`: The action was prevented by a security control (future-proofed; MUST NOT be emitted by
  v0.1 derivation unless an explicit prevention signal is present).
- `alerted`: At least one detection was produced for the action (by any enabled detection tool).
- `logged`: Telemetry evidence exists for the action, but no detection was produced.
- `none`: No telemetry evidence exists for the action (expected signals absent).
- `not_applicable`: The action was not executed (e.g., skipped due to requirements, platform
  mismatch, or safety gating).
- `tbd`: Outcome is indeterminate due to evaluation being unavailable/misconfigured or missing
  necessary inputs.

Implementations MUST NOT emit any additional outcome tokens.

#### Outcome precedence (normative)

Derived outcomes MUST be computed using this fixed precedence order (highest → lowest):

`blocked` > `alerted` > `logged` > `none` > `not_applicable` > `tbd`

#### Tool outcomes (normative, v0.1)

v0.1 defines two tool dimensions:

1. Telemetry validation tool outcome (`tool_kind = telemetry`)
1. Detection tool outcome for Sigma evaluation (`tool_kind = detection`)

Each tool produces an outcome token per action instance; the action’s derived outcome is the
precedence-reduction over the tool outcomes (plus any explicit override, if present).

#### Deterministic derivation per action (normative)

Inputs (authoritative, in priority order where applicable):

- `ground_truth.jsonl` for action execution status and technique attribution.
- `criteria/results.jsonl` for telemetry presence when available (preferred).
- Synthetic correlation marker observability (if enabled) MAY be used as a fallback telemetry
  signal.
- `detections/detections.jsonl` for detection presence.

Telemetry tool outcome for an action_id:

- If the action’s execute phase was skipped: outcome = `not_applicable`.
- Else, if a criteria result row exists for the action:
  - `status = pass` → `logged`
  - `status = fail` → `none`
  - `status = skipped` → `tbd` (reason_code conveys `criteria_unavailable` /
    `criteria_misconfigured` etc.)
- Else, if synthetic marker observability is available for the action (marker emission enabled):
  - observed = yes → `logged`
  - observed = no → `none`
- Else: `tbd`

Detection tool outcome for an action_id (Sigma v0.1):

- If the action’s execute phase was skipped: outcome = `not_applicable`.
- Else, if detection evaluation was not performed (missing detections output, or stage
  skipped/failed): outcome = `tbd`.
- Else, if there exists ≥1 detection instance attributed to the action: `alerted`.
- Else (no detections attributed):
  - if telemetry tool outcome is `logged` → `logged`
  - if telemetry tool outcome is `none` → `none`
  - else → `tbd`

Derived action outcome:

- Reduce the set of tool outcomes using Outcome precedence.

#### Deterministic derivation per technique (normative)

For each `technique_id`, gather all action instances in ground truth with that technique_id.
Compute:

- `outcome_counts`: counts of derived action outcomes by token.
- `outcome_best`: the highest-precedence token with count > 0 (using the same precedence list).

The report MUST expose at least `outcome_best` plus `outcome_counts` to prevent "single-row masking"
when a technique has multiple action variants/targets.

#### Deterministic ordering (normative)

Whenever outcomes are emitted as arrays:

- Per-action rows MUST be sorted by `action_id` ascending (UTF-8 byte order, no locale).
- Per-technique rows MUST be sorted by `technique_id` ascending (UTF-8 byte order, no locale).
- Per-action `tool_outcomes[]` MUST be sorted by `(tool_kind, tool_id)` ascending.

### Normalization coverage gate (Tier 1 Core Common)

Scoring and operator pivots assume that "Core Common" (Tier 1) fields exist at high frequency.
Because Tier 1 fields are specified as event-level SHOULD (not MUST), pipeline health MUST include
an explicit normalization coverage gate that can downgrade the run to `partial` without treating the
run as schema-invalid.

#### Metric

The pipeline MUST compute:

- `tier1_field_coverage_pct` as defined in the
  [OCSF field tiers specification](055_ocsf_field_tiers.md).
  - Unit: unitless fraction in `[0.0, 1.0]` (despite `_pct`, it is not `0-100`).
- `tier1_field_coverage_state` in `{ ok, below_threshold, indeterminate_no_events }`
- `tier1_field_coverage_threshold_pct` (unitless fraction in `[0.0, 1.0]`), derived from
  `scoring.thresholds.min_tier1_field_coverage` (default `0.80`).

#### Gate rule

Let `T = tier1_field_coverage_threshold_pct` (default `0.80`).

- If `tier1_field_coverage_state = indeterminate_no_events`, then run status MUST be `partial`.
- Else if `tier1_field_coverage_pct < T`, then run status MUST be `partial`.
- Else, this gate does not downgrade the run.

Invariant:

- `tier1_field_coverage_pct` MUST be `null` if and only if
  `tier1_field_coverage_state = indeterminate_no_events`.

#### Interaction with run status

Run status is a small set of operator-facing classifications:

- `failed`: the run is not mechanically usable (required artifacts missing, schema conformance
  failures on required artifacts, or an earlier stage that prevents evaluation).
- `partial`: artifacts are mechanically usable, but one or more quality gates did not meet minimum
  thresholds or were indeterminate (including Tier 1 normalization coverage).
- `success`: artifacts are mechanically usable and minimum quality gates are met.

Tier 1 coverage is explicitly a quality gate. Missing Tier 1 fields in individual events do not, by
themselves, cause schema conformance failure.

#### CI gating guidance

CI conformance gates MUST fail the pipeline for `failed`. CI policies SHOULD surface `partial`
prominently (for example, as a failing check in strict mode, or as a warning in default mode), since
it changes operator expectations and the interpretability of scoring pivots.

## Metric surface (normative)

This section defines naming, units, denominators, and determinism requirements for metrics emitted
by the scoring stage and consumed by reporting and regression.

### Naming and units

- Metric identifiers (`metric_id`) MUST be stable strings.
- Any metric id suffixed with `_pct` or `_rate` MUST be a unitless fraction in `[0.0, 1.0]`.
  - Producers MUST NOT emit `0-100` percentage values in machine-readable artifacts.
- `*_seconds` metrics MUST be durations in seconds.

### Denominators

Unless otherwise specified, the scoring stage MUST compute and emit these denominators in
`scoring/summary.json`:

- `executed_actions_total`: count of action instances whose `lifecycle.execute.phase_outcome` is not
  `"skipped"` in `ground_truth.jsonl`.
- `executed_techniques_total`: count of distinct `technique_id` values across the executed actions.
- `detections_total`: detection hits considered by scoring (rows in `detections/detections.jsonl`
  after deterministic dedupe). Only applicable when the detections stage is enabled.

When a denominator is zero, any derived `rate` metric that would divide by that denominator MUST be
emitted as `null` with `indeterminate_reason="not_applicable"`.

### Deterministic ordering

Unless a contract states otherwise, any arrays emitted in `scoring/summary.json` MUST be
deterministically ordered. Sorting MUST use UTF-8 byte order with no locale collation.

Note: Canonical rounding for regression comparables and deltas is defined in "Deterministic
comparison semantics (normative)".

## Primary metrics (seed)

- Coverage:

  - technique_covered = at least one detection for a technique executed

- Latency:

  - detection_latency = first_detection_time - ground_truth_time

- Fidelity:

  - match_quality tiers (exact, partial, weak-signal)

- Pipeline health:

  - missing_telemetry: expected signals absent for an executed action (criteria-based when
    available; else hint-based)
  - criteria_unavailable: action executed but no matching criteria entry was found in the pinned
    criteria pack
  - criteria_misconfigured: criteria entry exists but cannot be evaluated (invalid predicate,
    unsupported operator, etc.)
  - normalization_gap: events exist but required OCSF fields are missing (normalizer coverage issue)
  - bridge_gap_mapping: OCSF fields exist but the Sigma-to-OCSF Bridge lacks aliases or router
    entries required by the rule (addressable via mapping pack work)
  - bridge_gap_feature: Rule requires Sigma features outside the MVP-supported subset (correlation,
    aggregation, deferred modifiers like `cidr`, or PCRE-only regex constructs); not addressable
    without backend enhancement
  - bridge_gap_other: Bridge compilation or evaluation failed for reasons not classified above
    (catch-all for unexpected failures)
  - rule_logic_gap: fields present and rule executable, but rule did not fire
  - cleanup_verification_failed: cleanup invoked, but verification checks failed (run may be
    considered tainted)

Terminology note (normative):

- The gap category token `missing_telemetry` refers to missing expected telemetry signals for an
  executed action.

- It MUST NOT be used to represent missing artifact files. Missing artifacts are surfaced as stage
  failures (for example `input_missing`) or reader errors (`artifact_missing`) per
  `025_data_contracts.md`.

- Criteria evaluation (when criteria packs are enabled):

  - criteria_pass_rate: fraction of executed actions with criteria status `pass`
  - criteria_fail_rate: fraction of executed actions with criteria status `fail`
  - criteria_skipped_rate: fraction skipped (no matching criteria, evaluation disabled, or action
    failed before evaluation)
  - criteria_signal_latency: time from action start to first matching expected signal (when
    measurable)

- Bridge quality (Sigma-to-OCSF):

  - logsource_route_rate: fraction of rules whose `logsource` routes to at least one OCSF class
    filter
  - field_alias_coverage: fraction of referenced Sigma fields that map to OCSF (per rule and
    aggregate)
  - fallback_rate: fraction of evaluated rules that required `raw.*` fallback predicates
  - compile_failures: count and reasons (unknown logsource, unmapped fields, unsupported modifiers)

### Detection fidelity (seed; v0.1)

This scoring surface is intended to prevent overfitting to attack-only telemetry by making false
positive behavior measurable under a deterministic baseline noise workload.

Definitions:

- A detection hit is a row in `detections/detections.jsonl` after deterministic dedupe.
- A detection hit is a true positive when `pa.attribution.v1` attributes it to at least one executed
  action.
- A detection hit is a false positive when `pa.attribution.v1` cannot attribute it to any executed
  action.

#### Attribution algorithm (pa.attribution.v1)

Purpose. Deterministically attribute detection hits to executed actions for:

- detection fidelity classification (true-positive vs false-positive),
- latency attribution (max allowed latency gate), and
- per-action defense outcome derivation (alerted vs no_alert).

Inputs (v0.1). The attribution algorithm consumes:

- `detections/detections.jsonl` (detection instances; required)
- `ground_truth.jsonl` (executed actions; required)
- `normalized/ocsf_events.jsonl` (event envelope; REQUIRED for marker join)
- `criteria/results.jsonl` (criteria evaluation outputs; OPTIONAL; used when present)

Executed action. An action is considered executed for attribution if
`ground_truth.lifecycle.phases[].phase="execute"` has `phase_outcome != "skipped"`.

Eligibility gate (technique). A detection hit MUST only be considered for attribution to an action
when the hit’s `technique_ids[]` contains the action’s `technique_id`.

Join precedence (normative). For each detection hit, candidates MUST be evaluated in this order:

1. Marker join (highest confidence). If:

   - the ground-truth action includes `extensions.synthetic_correlation_marker` and/or
     `extensions.synthetic_correlation_marker_token`, and
   - at least one matched event (by `matched_event_ids[]`) includes a matching value in the
     corresponding normalized envelope field:
     - `metadata.extensions.purple_axiom.synthetic_correlation_marker`, and/or
     - `metadata.extensions.purple_axiom.synthetic_correlation_marker_token`, then the hit MUST be
       attributed to that action with `match_quality="exact"`.

1. Criteria-window join (secondary). If marker join produces no candidates, and
   `criteria/results.jsonl` is present, then a hit MUST be attributed to an action when:

   - `criteria/results.jsonl` contains a result row for that `action_id` with a `time_window`
     object,
   - `detections/detections.jsonl.first_seen_utc` is within the inclusive interval
     `[time_window.start_time_utc, time_window.end_time_utc]`, and
   - (when available) the hit’s matched events are attributable to the action’s `target_asset_id`.
     In this case the `match_quality` MUST be `"partial"`.

1. Pivot join (fallback). If neither marker nor criteria-window join yields candidates, a hit MAY be
   attributed using a deterministic pivot join:

   - the hit `first_seen_utc` MUST be within a fallback window around the action timestamp:
     `[action.timestamp_utc - skew_tolerance, action.timestamp_utc + max_allowed_latency_seconds]`
     where `max_allowed_latency_seconds` is taken from
     `scoring.thresholds.max_allowed_latency_seconds`, and `skew_tolerance` is fixed at 1 second
     (v0.1),
   - and (when available) the hit’s matched events originate from the action’s target asset. In this
     case the `match_quality` MUST be `"weak_signal"`.

Candidate selection and tie-breaks (normative).

- If multiple actions match in the same precedence tier, implementations MUST select a single
  `primary_action_id` deterministically using the following total ordering (lowest tuple wins):

  1. `abs(parse_ts(first_seen_utc) - parse_ts(action.timestamp_utc))` ascending
  1. `action_id` ascending (UTF-8 byte order, no locale)

- Implementations MAY also emit `attributed_action_ids[]` (for debugging), but if emitted it MUST:

  - include the `primary_action_id` first, and
  - be sorted by the same ordering as above.

- The attribution decision MUST be stable across repeated runs over identical inputs (byte-for-byte
  identical `manifest.json`, `ground_truth.jsonl`, `criteria/results.jsonl` when present, normalized
  events, and detections).

#### match_quality (normative)

`match_quality` is a coarse confidence tier for attribution used by scoring and reporting.

Allowed values (v0.1):

- `exact`: marker join succeeded (canonical marker and/or marker token evidence).
- `partial`: criteria-window join succeeded (no marker evidence).
- `weak_signal`: pivot join was required (no marker and no criteria-window evidence).

Metric rules (normative):

- When the detections stage is disabled or the detections artifact is absent, the metrics below MUST
  be emitted as `null` with `indeterminate_reason="not_applicable"`.
- When `detections_total == 0`, `false_positive_detection_rate` MUST be `null` with
  `indeterminate_reason="not_applicable"`.

### Regression comparable metric surface (normative)

When regression analysis is enabled, the scoring stage MUST expose a small, stable set of comparable
metrics suitable for deterministic cross-run diffs.

Definitions:

- "baseline": a prior run selected for comparison.
- "candidate": the run being evaluated.
- "comparable metric": a metric with stable identifier, kind, and unit that can be diffed between
  baseline and candidate.

Normative requirements:

- The comparable metric surface for a run MUST be fully materialized in `scoring/summary.json`.
  Reporting and regression computations MUST read comparable metric values from
  `scoring/summary.json` and MUST NOT recompute them from upstream artifacts.
- Comparable metrics MUST be emitted deterministically (stable rounding and stable ordering).
- If a comparable metric cannot be computed for a run, it MUST be recorded as `null` and accompanied
  by a deterministic `indeterminate_reason` token.
- Implementations MUST NOT omit a metric from the comparable metric surface due to configuration
  (for example, disabled gap categories). Instead, the metric MUST be present with value `null` and
  `indeterminate_reason="excluded_by_config"`.

Indeterminate reasons for per-run metric values (normative):

- `not_applicable`: the metric does not apply to the run (feature disabled, pack not enabled, or no
  eligible denominator).
- `excluded_by_config`: the metric is part of the comparable surface but is suppressed by explicit
  configuration; emitted as `null` to preserve stable metric identifiers for regression.

Scoring summary metadata (recommended):

- `scoring/summary.json` SHOULD include `meta.versions`, a normalized subset of `manifest.versions`
  sufficient to compute regression joins without re-reading `manifest.json` (for example:
  `scenario_id`, `scenario_version`, `pipeline_version`, `ocsf_version`, and any enabled pack ids
  and versions).

#### Stable emission and indeterminate semantics (normative)

The regression comparable metric surface is a contract for a stable row set across runs and
configurations.

- For every `metric_id` in the comparable surface, `scoring/summary.json` MUST include a value entry
  for that metric identifier.

  - The entry MUST include either a numeric `value` or `value=null` with a deterministic
    `indeterminate_reason` token.
  - Implementations MUST NOT omit a `metric_id` due to configuration (including
    `scoring.gap_taxonomy` exclusions).

- If an implementation represents per-gap-category values as a table (rather than distinct
  `metric_id` values), the table MUST be a stable row set with exactly one row per canonical
  `gap_category` token, in the following canonical order (v0.1, closed set):

  1. `missing_telemetry`
  1. `criteria_unavailable`
  1. `criteria_misconfigured`
  1. `normalization_gap`
  1. `bridge_gap_mapping`
  1. `bridge_gap_feature`
  1. `bridge_gap_other`
  1. `rule_logic_gap`
  1. `cleanup_verification_failed`

  Each row MUST include: `gap_category`, `value` (number or null), and `indeterminate_reason`
  (string or null).

Effective taxonomy recording (normative):

- `scoring/summary.json` MUST record the effective gap taxonomy used for any metrics that aggregate
  "over categories" (for example, totals computed over a configured subset).
  - Required: `meta.effective_gap_taxonomy` as an ordered list of included `gap_category` tokens in
    the canonical order defined above.
  - Optional: `meta.effective_gap_taxonomy_sha256` as SHA-256 over the RFC 8785 canonical JSON
    encoding of `meta.effective_gap_taxonomy` (UTF-8). The value MUST be a lowercase hex string.

Aggregate comparability (normative):

- Metrics whose definition depends on the effective included set (for example, aggregates computed
  over `meta.effective_gap_taxonomy`) are comparable only when baseline and current runs have
  identical `meta.effective_gap_taxonomy` values.
  - Otherwise, regression deltas for those metrics MUST be indeterminate with
    `indeterminate_reason="taxonomy_mismatch"`.

Example (non-normative): stable emission for excluded categories

```json
{
  "meta": {
    "effective_gap_taxonomy": [
      "missing_telemetry",
      "normalization_gap",
      "bridge_gap_mapping",
      "bridge_gap_feature",
      "bridge_gap_other",
      "rule_logic_gap",
      "cleanup_verification_failed"
    ],
    "effective_gap_taxonomy_sha256": "<hex>"
  },
  "pipeline_health_by_gap_category": [
    {
      "gap_category": "missing_telemetry",
      "value": 0.0312,
      "indeterminate_reason": null
    },
    {
      "gap_category": "criteria_unavailable",
      "value": null,
      "indeterminate_reason": "excluded_by_config"
    },
    {
      "gap_category": "criteria_misconfigured",
      "value": null,
      "indeterminate_reason": "excluded_by_config"
    },
    {
      "gap_category": "normalization_gap",
      "value": 0.0125,
      "indeterminate_reason": null
    },
    {
      "gap_category": "bridge_gap_mapping",
      "value": 0.0833,
      "indeterminate_reason": null
    },
    {
      "gap_category": "bridge_gap_feature",
      "value": 0.2500,
      "indeterminate_reason": null
    },
    {
      "gap_category": "bridge_gap_other",
      "value": 0.0000,
      "indeterminate_reason": null
    },
    {
      "gap_category": "rule_logic_gap",
      "value": 0.1875,
      "indeterminate_reason": null
    },
    {
      "gap_category": "cleanup_verification_failed",
      "value": 0.0000,
      "indeterminate_reason": null
    }
  ]
}
```

Comparable metrics (v0.1 minimum set):

- Coverage:
  - `technique_coverage_rate` (kind: `rate`, unit: unitless fraction in `[0.0, 1.0]`)
- Latency:
  - `detection_latency_p95_seconds` (kind: `duration_seconds`, unit: seconds)
- Normalization coverage (Tier 1):
  - `tier1_field_coverage_pct` (kind: `rate`, unit: unitless fraction in `[0.0, 1.0]`)
- Pipeline health (counts and rates per gap category):
  - `missing_telemetry_count` (kind: `count`, unit: actions)
  - `missing_telemetry_rate` (kind: `rate`, unit: unitless fraction)
  - `criteria_unavailable_count` (kind: `count`, unit: actions)
  - `criteria_unavailable_rate` (kind: `rate`, unit: unitless fraction)
  - `criteria_misconfigured_count` (kind: `count`, unit: actions)
  - `criteria_misconfigured_rate` (kind: `rate`, unit: unitless fraction)
  - `normalization_gap_count` (kind: `count`, unit: actions)
  - `normalization_gap_rate` (kind: `rate`, unit: unitless fraction)
  - `bridge_gap_mapping_count` (kind: `count`, unit: actions)
  - `bridge_gap_mapping_rate` (kind: `rate`, unit: unitless fraction)
  - `bridge_gap_feature_count` (kind: `count`, unit: actions)
  - `bridge_gap_feature_rate` (kind: `rate`, unit: unitless fraction)
  - `bridge_gap_other_count` (kind: `count`, unit: actions)
  - `bridge_gap_other_rate` (kind: `rate`, unit: unitless fraction)
  - `rule_logic_gap_count` (kind: `count`, unit: actions)
  - `rule_logic_gap_rate` (kind: `rate`, unit: unitless fraction)
  - `cleanup_verification_failed_count` (kind: `count`, unit: actions)
  - `cleanup_verification_failed_rate` (kind: `rate`, unit: unitless fraction)
- Detection fidelity:
  - `detections_total` (kind: `count`, unit: detections)
  - `false_positive_detection_count` (kind: `count`, unit: detections)
  - `false_positive_detection_rate` (kind: `rate`, unit: unitless fraction)

Notes:

- `*_rate` metrics MUST use `executed_actions_total` as the denominator, unless explicitly stated
  otherwise for a metric. `false_positive_detection_rate` uses `detections_total`. When a metric is
  not applicable to the run (including a zero denominator), the metric MUST be `null` with an
  `indeterminate_reason`.
- Implementations MAY include additional comparable metrics, but MUST NOT change the identifiers,
  meaning, or typing of the minimum set above within a contract version.

### Deterministic comparison semantics (normative)

Regression delta computation MUST be deterministic and reproducible across platforms.

Comparability prerequisites (normative):

- Regression deltas MUST be computed only when reporting-level comparability checks are not
  indeterminate.

  - Implementations MUST treat `report/report.json.regression.comparability.status="indeterminate"`
    as not comparable (no deltas computed).
  - Implementations MAY compute deltas when `comparability.status` is `comparable` or `warning`.

- When runs are not comparable (`comparability.status="indeterminate"`):

  - Implementations MUST NOT emit computed numeric deltas for any comparable metric.
  - The regression delta surface MUST emit an empty `deltas[]` array (`[]`) deterministically.
  - Implementations MUST NOT interpret the absence of delta rows as `delta=0`.

Delta entry indeterminate reasons (normative):

- When `comparability.status` is `comparable` or `warning`, a delta entry MAY still be
  indeterminate. In that case, the delta surface MUST use only the following `indeterminate_reason`
  tokens:
  - `not_applicable`
  - `excluded_by_config`
  - `taxonomy_mismatch`

Per-metric indeterminate rules (normative):

- If a metric is `not_applicable` in either baseline or candidate (i.e., `value=null` with
  `indeterminate_reason="not_applicable"`), the delta entry MUST be indeterminate with
  `indeterminate_reason="not_applicable"`.
- When a metric is excluded by configuration:
  - If the metric is excluded in both baseline and candidate runs, `delta` MUST be `null` with
    `indeterminate_reason="excluded_by_config"`.
  - If the metric is excluded in exactly one of baseline or candidate runs, `delta` MUST be `null`
    with `indeterminate_reason="taxonomy_mismatch"`.
- When a metric’s definition depends on the effective included set (for example, aggregates computed
  over `meta.effective_gap_taxonomy`), and baseline/candidate `meta.effective_gap_taxonomy` values
  are not identical, `delta` MUST be `null` with `indeterminate_reason="taxonomy_mismatch"`.

Canonical rounding:

- `rate` values MUST be rounded to 4 decimal places using round-half-up.
- `duration_seconds` values MUST be rounded to 3 decimal places using round-half-up.
- `count` values MUST be integers.

Delta rules:

- Delta MUST be computed as `candidate_value - baseline_value` after canonical rounding.
- For `count`, delta MUST be an integer difference.
- For `rate` and `duration_seconds`, delta MUST be the rounded numeric difference.

Default tolerances (v0.1):

- `technique_coverage_rate`: tolerance `0.0001`
- `detection_latency_p95_seconds`: tolerance `0.010`
- `tier1_field_coverage_pct`: tolerance `0.0001`
- All `*_rate` gap metrics: tolerance `0.0001`
- All `*_count` gap metrics: tolerance `0`

Stable ordering:

- Any Any regression delta table MUST be sorted by `metric_id` ascending (UTF-8 byte order, no
  locale).

### Verification hooks (regression comparability)

CI MUST include fixtures that validate regression delta determinism under comparability failures:

- Pins differ but scoring metrics are otherwise valid:
  - Setup: baseline and candidate runs produce valid `scoring/summary.json`, but at least one
    required `manifest.versions.*` pin differs (for example, `mapping_pack_version`).
  - Expected: `report/report.json.regression.comparability.status` MUST be `indeterminate` and
    `report/report.json.regression.deltas[]` MUST be an empty array (`[]`).
- Excluded category does not cause omission instability:
  - Setup: a gap category metric is excluded by configuration in both baseline and candidate.
  - Expected: the comparable `metric_id` MUST remain present in the delta surface when
    `comparability.status` is `comparable` or `warning`, and the delta entry MUST be indeterminate
    with `indeterminate_reason="excluded_by_config"` (not silently omitted).

## Methodology inspiration

- Prefer transparent reporting tied to specific behaviors/techniques rather than opaque vendor-style
  scores.

## Default thresholds and weights (v0.1)

Unless overridden via configuration, v0.1 implementations MUST apply the following defaults for CI
gating and score computation.

### Reason code to gap category mapping (normative)

Input is the `(reason_domain, reason_code)` pair.

- For v0.1, this mapping applies to `reason_domain="bridge_compiled_plan"` only.

The scoring stage MUST map compiled plan `non_executable_reason.reason_code` values to gap
categories as follows:

| `non_executable_reason.reason_code` (from compiled plan) | Gap Category         | Notes                                                                                           |
| -------------------------------------------------------- | -------------------- | ----------------------------------------------------------------------------------------------- |
| `unmapped_field`                                         | `bridge_gap_mapping` | Field alias missing in mapping pack                                                             |
| `unroutable_logsource`                                   | `bridge_gap_mapping` | No router entry for Sigma logsource                                                             |
| `raw_fallback_disabled`                                  | `bridge_gap_mapping` | Rule needs raw.\* but policy disallows                                                          |
| `ambiguous_field_alias`                                  | `bridge_gap_mapping` | Multiple conflicting aliases                                                                    |
| `unsupported_modifier`                                   | `bridge_gap_feature` | Modifier (base64, windash, etc.) not supported                                                  |
| `unsupported_operator`                                   | `bridge_gap_feature` | Operator semantics not implementable                                                            |
| `unsupported_value_type`                                 | `bridge_gap_feature` | Value type incompatible with operator                                                           |
| `unsupported_regex`                                      | `bridge_gap_feature` | Regex pattern or options rejected by policy (RE2-only; PCRE-only constructs are Non-executable) |
| `unsupported_correlation`                                | `bridge_gap_feature` | Correlation / multi-event semantics out of scope                                                |
| `unsupported_aggregation`                                | `bridge_gap_feature` | Aggregation semantics out of scope                                                              |
| `backend_compile_error`                                  | `bridge_gap_other`   | Unexpected compilation failure                                                                  |
| `backend_eval_error`                                     | `bridge_gap_other`   | Runtime evaluation failure                                                                      |

Unknown reason codes MUST be classified as `bridge_gap_other` and SHOULD trigger a warning log.

### Gap category to measurement layer mapping (normative)

For reporting and triage, each gap category MUST also map to a measurement layer. The measurement
layer answers "which pipeline layer is broken" independent of remediation ownership.

Measurement layers (closed set):

- `telemetry`
- `normalization`
- `detection`
- `scoring`

Mapping (v0.1):

| Gap category                  | Measurement layer |
| ----------------------------- | ----------------- |
| `missing_telemetry`           | `telemetry`       |
| `normalization_gap`           | `normalization`   |
| `bridge_gap_mapping`          | `detection`       |
| `bridge_gap_feature`          | `detection`       |
| `bridge_gap_other`            | `detection`       |
| `rule_logic_gap`              | `detection`       |
| `criteria_unavailable`        | `scoring`         |
| `criteria_misconfigured`      | `scoring`         |
| `cleanup_verification_failed` | `scoring`         |

Conformance (normative):

- The v0.1 pipeline-health gap taxonomy tokens are defined in this specification (see "Primary
  metrics (seed)" → "Pipeline health").
- Every gap category token in that taxonomy MUST appear exactly once in the mapping table above.
- The mapping table MUST NOT contain gap category tokens that are not present in the taxonomy.

### Evidence pointer requirements (normative)

Implementations MUST be able to provide run-relative evidence pointers that justify any gap
classification. Evidence pointers MUST be stable artifact paths (selectors are optional).

Evidence pointers in scoring and reporting outputs MUST conform to the evidence ref shape and
selector grammar defined in `025_data_contracts.md` (Evidence references (shared shape)).

Minimum evidence pointer set by measurement layer (normative):

- telemetry:
  - MUST include `manifest.json`.
  - MUST include `logs/health.json` when present.
  - SHOULD include `logs/telemetry_validation.json` when telemetry validation is enabled and the
    artifact is present.
- normalization:
  - MUST include `normalized/mapping_coverage.json`.
- detection:
  - MUST include `bridge/coverage.json`.
  - SHOULD include `detections/detections.jsonl`.
- scoring:
  - MUST include `scoring/summary.json`.

Conditional minimums by gap category (normative):

- `missing_telemetry`:
  - Evidence pointers MUST include `manifest.json`.
  - Evidence pointers MUST include `logs/health.json` when present.
  - Evidence pointers SHOULD include the most directly causal telemetry validation artifact(s) when
    present.
- `criteria_unavailable`, `criteria_misconfigured`:
  - When criteria validation is enabled, evidence pointers MUST include `criteria/manifest.json` and
    `criteria/results.jsonl`.
- `cleanup_verification_failed`:
  - Evidence pointers MUST include runner cleanup verification evidence under `runner/` when
    present.

### Thresholds (CI gates)

```yaml
scoring:
  thresholds:
    # Technique coverage: % of executed techniques with ≥1 detection
    min_technique_coverage: 0.75

    # Latency gate: maximum allowed detection latency at p95 (batch evaluation tolerance)
    max_allowed_latency_seconds: 300

    # Normalization quality gate (already defined above)
    min_tier1_field_coverage: 0.80

    # Gap budgets (rates in [0.0, 1.0])
    max_missing_telemetry_rate: 0.10
    max_normalization_gap_rate: 0.05

    # Bridge gap budgets (split by addressability)
    max_bridge_gap_mapping_rate: 0.10  # Addressable via mapping pack work
    max_bridge_gap_feature_rate: 0.40  # Expected given MVP feature scope
    max_bridge_gap_other_rate: 0.02    # Should be rare; indicates bridge bugs

    # False positive rate
    max_false_positive_detection_rate: 0.05
    max_false_positive_detection_count: 10 
```

### Weights (composite score)

```yaml
scoring:
  weights:
    coverage_weight: 0.60
    latency_weight: 0.25
    fidelity_weight: 0.15
```

### CI interpretation (normative)

- If any threshold is violated, the run SHOULD be marked `partial` (exit code `10`), not `failed`,
  unless a stage-level `fail_closed` condition is met.
- Threshold evaluation MUST be based on metrics emitted in `scoring/summary.json`, and the report
  MUST enumerate which thresholds failed.

## Verification hooks

Golden regression fixture (normative):

- Given two runs with identical pinned inputs (scenario, mapping pack snapshot, rule set snapshot,
  criteria pack snapshot when enabled), the implementation MUST produce identical values for every
  metric in "Regression comparable metric surface (normative)".
- The regression delta report for such a pair MUST contain deltas of zero for all comparable metrics
  and MUST be deterministically ordered by `metric_id` ascending.

## References

- [OCSF field tiers specification](055_ocsf_field_tiers.md)
- [Sigma to OCSF bridge specification](065_sigma_to_ocsf_bridge.md)
- [Detection rules (Sigma) specification](060_detection_sigma.md)
- [Test strategy CI specification](100_test_strategy_ci.md)

## Changelog

| Date       | Change                                                       |
| ---------- | ------------------------------------------------------------ |
| 2026-01-21 | Consistency fixes: status naming, regression delta semantics |
| 2026-01-18 | Regression comparable surface and measurement-layer contract |
| 2026-01-12 | Formatting update                                            |
