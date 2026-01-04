# Test Strategy and CI

## Unit tests
- Mapping unit tests: raw input -> expected OCSF output
- Rule compilation tests: Sigma -> evaluation plan

## Integration tests
- “Golden run” fixture: deterministic scenario + captured telemetry to validate end-to-end outputs.

## CI gates (seed)
- Schema validation of produced OCSF events
- Linting/validation for Sigma rules
- Report generation sanity checks
- Artifact manifest completeness check
