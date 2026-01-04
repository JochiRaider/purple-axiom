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
  - missing_telemetry: technique executed but expected event classes absent
  - mapping_gap: events present but unmapped to needed OCSF fields
  - rule_logic_gap: fields present but rule did not fire

## Methodology inspiration
- Prefer transparent reporting tied to specific behaviors/techniques rather than opaque vendor-style scores.
