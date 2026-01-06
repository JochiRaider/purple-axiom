<!-- docs/spec/100_test_strategy_ci.md -->
# Test Strategy and CI

## Unit tests
- Mapping unit tests: raw input -> expected OCSF output
- Rule compilation tests: Sigma -> evaluation plan
- Lab provider parser tests: provider inventory export -> canonical `lab.assets` list
- Scenario selection tests: target selectors -> resolved target set (using a fixed inventory snapshot fixture)

## Integration tests
- “Golden run” fixture: deterministic scenario + captured telemetry to validate end-to-end outputs.
- “Scenario suite” fixture: a small, representative set of techniques used as a regression pack.
- Baseline comparison: compare current run outputs to a pinned baseline run bundle.

## CI gates (seed)
- Schema validation of produced OCSF events
- Linting/validation for Sigma rules
- Report generation sanity checks
- Artifact manifest completeness check
- Cross-artifact invariants:
  - run_id/scenario_id consistency
  - referential integrity (detections reference existing event_ids)
  - inventory snapshot hash matches manifest input hash
- Regression gates (configurable thresholds):
  - technique coverage must not drop more than X relative to baseline
  - latency percentiles must not exceed Y
  - “missing_telemetry” and “normalization_gap” rates must not exceed Z

## CI workflow pattern (recommended)
1. Resolve lab inventory (provider or fixture)
2. Execute scenario suite (runner)
3. Collect and normalize telemetry (OTel -> OCSF)
4. Evaluate detections (Sigma) and score gaps
5. Produce report + machine-readable summary
6. Compare to baseline and fail the pipeline when thresholds are violated