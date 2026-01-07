<!-- docs/spec/070_scoring_metrics.md -->
# Scoring and Metrics

## Concepts
- Ground truth action: a known technique/test execution (with timestamp + target)
- Detection: a rule hit mapped to run_id + technique_id

### Normalization coverage gate (Tier 1 Core Common)

Scoring and operator pivots assume that "Core Common" (Tier 1) fields exist at high frequency. Because Tier 1
fields are specified as event-level SHOULD (not MUST), pipeline health MUST include an explicit normalization
coverage gate that can downgrade the run to `partial` without treating the run as schema-invalid.

#### Metric

The pipeline **MUST** compute:

- `tier1_field_coverage_pct` as defined in `055_ocsf_field_tiers.md`
- `tier1_field_coverage_state` in `{ ok, below_threshold, indeterminate_no_events }`
- `tier1_field_coverage_threshold_pct` (default `0.80`)

#### Gate rule

Let `T = tier1_field_coverage_threshold_pct` (default 0.80).

- If `tier1_field_coverage_pct` is `null` with state `indeterminate_no_events`, then run status **MUST** be `partial`.
- Else if `tier1_field_coverage_pct < T`, then run status **MUST** be `partial`.
- Else, this gate does not downgrade the run.

#### Interaction with run status

Run status is a small set of operator-facing classifications:

- `failed`: the run is not mechanically usable (required artifacts missing, schema conformance failures on required
  artifacts, or an earlier stage that prevents evaluation).
- `partial`: artifacts are mechanically usable, but one or more quality gates did not meet minimum thresholds or were
  indeterminate (including Tier 1 normalization coverage).
- `ok`: artifacts are mechanically usable and minimum quality gates are met.

Tier 1 coverage is explicitly a quality gate. Missing Tier 1 fields in individual events do not, by themselves,
cause schema conformance failure.

#### CI gating guidance

CI conformance gates **MUST** fail the pipeline for `failed`.
CI policies **SHOULD** surface `partial` prominently (for example, as a failing check in strict mode, or as a warning
in default mode), since it changes operator expectations and the interpretability of scoring pivots.

## Primary metrics (seed)
- Coverage:
  - technique_covered = at least one detection for a technique executed
- Latency:
  - detection_latency = first_detection_time - ground_truth_time
- Fidelity:
  - match_quality tiers (exact, partial, weak-signal)
- Pipeline health:
  - missing_telemetry: expected signals absent for an executed action (criteria-based when available; else hint-based)
  - criteria_unavailable: action executed but no matching criteria entry was found in the pinned criteria pack
  - criteria_misconfigured: criteria entry exists but cannot be evaluated (invalid predicate, unsupported operator, etc.)
  - normalization_gap: events exist but required OCSF fields are missing (normalizer coverage issue)
  - bridge_gap: OCSF fields exist but the Sigma-to-OCSF Bridge lacks aliases/router entries (rule not executable)
  - rule_logic_gap: fields present and rule executable, but rule did not fire
  - cleanup_verification_failed: cleanup invoked, but verification checks failed (run may be considered tainted)

- Criteria evaluation (when criteria packs are enabled):
  - criteria_pass_rate: fraction of executed actions with criteria status `pass`
  - criteria_fail_rate: fraction of executed actions with criteria status `fail`
  - criteria_skipped_rate: fraction skipped (no matching criteria, evaluation disabled, or action failed before evaluation)
  - criteria_signal_latency: time from action start to first matching expected signal (when measurable)
  
- Bridge quality (Sigma-to-OCSF):
  - logsource_route_rate: fraction of rules whose `logsource` routes to at least one OCSF class filter
  - field_alias_coverage: fraction of referenced Sigma fields that map to OCSF (per rule and aggregate)
  - fallback_rate: fraction of evaluated rules that required `raw.*` fallback predicates
  - compile_failures: count and reasons (unknown logsource, unmapped fields, unsupported modifiers)

## Methodology inspiration
- Prefer transparent reporting tied to specific behaviors/techniques rather than opaque vendor-style scores.
