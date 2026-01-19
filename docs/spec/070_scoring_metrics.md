---
title: Scoring and metrics
description: Defines scoring metrics, gates, thresholds, and default weights for run evaluation.
status: draft
---

# Scoring and metrics

This document defines how Purple Axiom computes scoring metrics, applies quality gates, and
interprets results for CI and operator reporting. It establishes default thresholds and weightings
for v0.1 while keeping evaluation deterministic and auditable.

## Concepts

- Ground truth action: a known technique/test execution (with timestamp + target)
- Action template: stable procedure identity (`template_id`) used for cross-run aggregation.
- Action instance: a run-scoped execution instance (`action_id`).
  - v0.1: legacy `s<positive_integer>`.
  - v0.2+: deterministic `pa_aid_v1_<32hex>` (see data contracts).
- Detection: a rule hit mapped to `run_id` + `technique_id`

### Normalization coverage gate (Tier 1 Core Common)

Scoring and operator pivots assume that "Core Common" (Tier 1) fields exist at high frequency.
Because Tier 1 fields are specified as event-level SHOULD (not MUST), pipeline health MUST include
an explicit normalization coverage gate that can downgrade the run to `partial` without treating the
run as schema-invalid.

#### Metric

The pipeline **MUST** compute:

- `tier1_field_coverage_pct` as defined in the
  [OCSF field tiers specification](055_ocsf_field_tiers.md)
- `tier1_field_coverage_state` in `{ ok, below_threshold, indeterminate_no_events }`
- `tier1_field_coverage_threshold_pct` (default `0.80`)

#### Gate rule

Let `T = tier1_field_coverage_threshold_pct` (default 0.80).

- If `tier1_field_coverage_pct` is `null` with state `indeterminate_no_events`, then run status
  **MUST** be `partial`.
- Else if `tier1_field_coverage_pct < T`, then run status **MUST** be `partial`.
- Else, this gate does not downgrade the run.

#### Interaction with run status

Run status is a small set of operator-facing classifications:

- `failed`: the run is not mechanically usable (required artifacts missing, schema conformance
  failures on required artifacts, or an earlier stage that prevents evaluation).
- `partial`: artifacts are mechanically usable, but one or more quality gates did not meet minimum
  thresholds or were indeterminate (including Tier 1 normalization coverage).
- `ok`: artifacts are mechanically usable and minimum quality gates are met.

Tier 1 coverage is explicitly a quality gate. Missing Tier 1 fields in individual events do not, by
themselves, cause schema conformance failure.

#### CI gating guidance

CI conformance gates **MUST** fail the pipeline for `failed`. CI policies **SHOULD** surface
`partial` prominently (for example, as a failing check in strict mode, or as a warning in default
mode), since it changes operator expectations and the interpretability of scoring pivots.

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

### Regression comparable metric surface (normative)

When regression analysis is enabled, the scoring stage MUST expose a small, stable set of comparable
metrics suitable for deterministic cross-run diffs.

Definitions:

- "baseline": a prior run selected for comparison.
- "current": the run being evaluated.
- "comparable metric": a metric with stable identifier, type, and unit that can be diffed between
  baseline and current.

Normative requirements:

- Comparable metrics MUST be derived from `scoring/summary.json` only.
- Comparable metrics MUST be emitted deterministically (stable rounding and stable ordering).
- If a comparable metric cannot be computed, it MUST be recorded as `null` and accompanied by a
  deterministic `indeterminate_reason` token.
- Implementations MUST NOT omit a metric from the comparable metric surface due to configuration
  (for example, disabled gap categories). Instead, the metric MUST be present with value `null` and
  `indeterminate_reason="excluded_by_config"`.

Indeterminate reasons (normative):

- `not_applicable`: the metric does not apply to the run (feature disabled, pack not enabled, or no
  eligible denominator).
- `excluded_by_config`: the metric is part of the comparable surface but is suppressed by explicit
  configuration; emitted as `null` to preserve stable metric identifiers for regression.
- `taxonomy_mismatch`: the metric depends on a configured gap taxonomy (for example, inclusion or
  aggregation over a selected set), and baseline/current runs used different effective taxonomy
  selections; emitted as `null` to preserve stable metric identifiers and deterministic regression
  semantics.
- `incomparable_pins`: regression delta computation is not permitted because baseline/current runs
  are not comparable (see Deterministic comparison semantics below).

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
  `metric_id` values), the table MUST be a stable row set:

  - One row per canonical `gap_category` token in the v0.1 taxonomy (see "Primary metrics (seed)" →
    "Pipeline health"), in that canonical order.
  - Each row MUST include: `gap_category`, `value` (number or null), and `indeterminate_reason`
    (string or null).

Effective taxonomy recording (normative):

- `scoring/summary.json` MUST record the effective gap taxonomy used for any metrics that aggregate
  "over categories" (for example, totals computed over a configured subset).
  - Required: `meta.effective_gap_taxonomy` as an ordered list of included `gap_category` tokens.
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
      "rule_logic_gap"
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

Notes:

- `*_rate` metrics MUST use `executed_actions_total` as the denominator, unless the category is not
  applicable to the run, in which case the metric MUST be `null` with an `indeterminate_reason`.
- Implementations MAY include additional comparable metrics, but MUST NOT change the identifiers,
  meaning, or typing of the minimum set above within a contract version.

### Deterministic comparison semantics (normative)

Regression delta computation MUST be deterministic and reproducible across platforms.

Comparability prerequisites (normative):

- Regression deltas MUST be computed only when reporting-level comparability checks pass.
  - Implementations MUST treat `report/report.json.regression.comparability.status="indeterminate"`
    as not comparable.
- When runs are not comparable (comparability is indeterminate):
  - Implementations MUST NOT emit a computed numeric delta for any comparable metric.
  - Implementations SHOULD emit one delta row per `metric_id` in the comparable surface with
    `delta=null` and `indeterminate_reason="incomparable_pins"`.
  - Implementations MAY alternatively emit an empty delta table, but MUST do so deterministically
    and MUST NOT interpret the absence of a row as `delta=0`.
- When a metric is excluded by configuration:
  - If the metric is excluded in both baseline and current runs, `delta` MUST be `null` with
    `indeterminate_reason="excluded_by_config"`.
  - If the metric is excluded in exactly one of baseline or current runs, `delta` MUST be `null`
    with `indeterminate_reason="taxonomy_mismatch"`.
- When a metric’s definition depends on the effective included set (for example, aggregates computed
  over `meta.effective_gap_taxonomy`), and baseline/current `meta.effective_gap_taxonomy` values are
  not identical, `delta` MUST be `null` with `indeterminate_reason="taxonomy_mismatch"`.

Canonical rounding:

- `rate` values MUST be rounded to 4 decimal places using round-half-up.
- `duration_seconds` values MUST be rounded to 3 decimal places using round-half-up.
- `count` values MUST be integers.

Delta rules:

- Delta MUST be computed as `current_value - baseline_value` after canonical rounding.
- For `count`, delta MUST be an integer difference.
- For `rate` and `duration_seconds`, delta MUST be the rounded numeric difference.

Default tolerances (v0.1):

- `technique_coverage_rate`: tolerance `0.0001`
- `detection_latency_p95_seconds`: tolerance `0.010`
- `tier1_field_coverage_pct`: tolerance `0.0001`
- All `*_rate` gap metrics: tolerance `0.0001`
- All `*_count` gap metrics: tolerance `0`

Stable ordering:

- Any regression delta table MUST be sorted by `metric_id` ascending (ASCII byte order).

### Verification hooks (regression comparability)

CI MUST include fixtures that validate regression delta determinism under comparability failures:

- Pins differ but scoring metrics are otherwise valid:
  - Setup: baseline and current runs produce valid `scoring/summary.json`, but at least one required
    `manifest.versions.*` pin differs (for example, `mapping_pack_version`).
  - Expected: regression deltas MUST be indeterminate and MUST use
    `indeterminate_reason="incomparable_pins"` (or the implementation’s documented deterministic
    alternate shape, such as an empty delta table).
- Excluded category does not cause omission instability:
  - Setup: a gap category metric is excluded by configuration in both baseline and current.
  - Expected: the comparable metric identifier MUST remain present in the delta surface, and delta
    MUST be indeterminate with `indeterminate_reason="excluded_by_config"` (not silently omitted).

## Methodology inspiration

- Prefer transparent reporting tied to specific behaviors/techniques rather than opaque vendor-style
  scores.

## Default thresholds and weights (v0.1)

Unless overridden via configuration, v0.1 implementations MUST apply the following defaults for CI
gating and score computation.

### Reason code to gap category mapping (normative)

The scoring stage MUST map compiled plan `reason_code` values to gap categories as follows:

| `reason_code` (from compiled plan) | Gap Category         | Notes                                                                                           |
| ---------------------------------- | -------------------- | ----------------------------------------------------------------------------------------------- |
| `unmapped_field`                   | `bridge_gap_mapping` | Field alias missing in mapping pack                                                             |
| `unroutable_logsource`             | `bridge_gap_mapping` | No router entry for Sigma logsource                                                             |
| `raw_fallback_disabled`            | `bridge_gap_mapping` | Rule needs raw.\* but policy disallows                                                          |
| `ambiguous_field_alias`            | `bridge_gap_mapping` | Multiple conflicting aliases                                                                    |
| `unsupported_regex`                | `bridge_gap_feature` | Regex pattern or options rejected by policy (RE2-only; PCRE-only constructs are Non-executable) |
| `unsupported_modifier`             | `bridge_gap_feature` | Modifier (base64, windash, etc.) not supported                                                  |
| `unsupported_operator`             | `bridge_gap_feature` | Operator semantics not implementable                                                            |
| `unsupported_value_type`           | `bridge_gap_feature` | Value type incompatible with operator                                                           |
| `backend_compile_error`            | `bridge_gap_other`   | Unexpected compilation failure                                                                  |
| `backend_eval_error`               | `bridge_gap_other`   | Runtime evaluation failure                                                                      |

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
  - MUST include `logs/health.json`.
  - SHOULD include telemetry validation artifacts under `telemetry/` when present.
- normalization:
  - MUST include `normalized/mapping_coverage.json`.
- detection:
  - MUST include `bridge/coverage.json`.
  - SHOULD include `detections/detections.jsonl`.
- scoring:
  - MUST include `scoring/summary.json`.

Conditional minimums by gap category (normative):

- `missing_telemetry`:
  - Evidence pointers MUST include `logs/health.json`.
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
- [Test strategy CI specification](100_test_strategy_ci.md)

## Changelog

| Date       | Change                                                       |
| ---------- | ------------------------------------------------------------ |
| 2026-01-18 | Regression comparable surface and measurement-layer contract |
| 2026-01-12 | Formatting update                                            |
