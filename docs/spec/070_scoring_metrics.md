# Scoring and Metrics

## Concepts
- Ground truth action: a known technique/test execution (with timestamp + target)
- Detection: a rule hit mapped to run_id + technique_id

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
