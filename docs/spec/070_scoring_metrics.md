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
  - bridge_gap_feature: Rule requires Sigma features outside the MVP-supported subset (regex,
    correlation, aggregation, unsupported modifiers); not addressable without backend enhancement
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

## Methodology inspiration

- Prefer transparent reporting tied to specific behaviors/techniques rather than opaque vendor-style
  scores.

## Default thresholds and weights (v0.1)

Unless overridden via configuration, v0.1 implementations MUST apply the following defaults for CI
gating and score computation.

### Reason code to gap category mapping (normative)

The scoring stage MUST map compiled plan `reason_code` values to gap categories as follows:

| `reason_code` (from compiled plan) | Gap Category         | Notes                                          |
| ---------------------------------- | -------------------- | ---------------------------------------------- |
| `unmapped_field`                   | `bridge_gap_mapping` | Field alias missing in mapping pack            |
| `unroutable_logsource`             | `bridge_gap_mapping` | No router entry for Sigma logsource            |
| `raw_fallback_disabled`            | `bridge_gap_mapping` | Rule needs raw.\* but policy disallows         |
| `ambiguous_field_alias`            | `bridge_gap_mapping` | Multiple conflicting aliases                   |
| `unsupported_regex`                | `bridge_gap_feature` | Regex modifier not in MVP subset               |
| `unsupported_modifier`             | `bridge_gap_feature` | Modifier (base64, windash, etc.) not supported |
| `unsupported_operator`             | `bridge_gap_feature` | Operator semantics not implementable           |
| `unsupported_value_type`           | `bridge_gap_feature` | Value type incompatible with operator          |
| `backend_compile_error`            | `bridge_gap_other`   | Unexpected compilation failure                 |
| `backend_eval_error`               | `bridge_gap_other`   | Runtime evaluation failure                     |

Unknown reason codes MUST be classified as `bridge_gap_other` and SHOULD trigger a warning log.

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
- Threshold evaluation MUST be based on metrics emitted in `scoring/summary.json` (or
  `report/summary.json` if exported), and the report MUST enumerate which thresholds failed.

## References

- [OCSF field tiers specification](055_ocsf_field_tiers.md)
- [Sigma to OCSF bridge specification](065_sigma_to_ocsf_bridge.md)
- [Test strategy CI specification](100_test_strategy_ci.md)

## Changelog

| Date       | Change            |
| ---------- | ----------------- |
| 2026-01-12 | Formatting update |
