<!-- docs/spec/100_test_strategy_ci.md -->
# Test Strategy and CI

## Unit tests
- Canonicalization tests: RFC 8785 (JCS) vectors + Purple Axiom hash-basis fixtures (byte-for-byte).
- Redaction tests: policy fixture vectors (argv redaction, regex redaction, truncation determinism, post-checks).
- Windows Event Log raw XML tests: identity-field extraction without RenderingInfo; binary field detection; payload limit truncation + SHA-256.
- Redaction posture tests: `security.redaction.enabled=false` MUST produce deterministic placeholders or quarantine-only outputs and MUST label the run as unredacted in metadata.
- Mapping unit tests: raw input -> expected OCSF output
- OCSF schema regression tests: representative normalized fixtures MUST validate against the pinned OCSF version used by v0.1.
- Parquet schema evolution tests (normalized store):
  - Given two Parquet fixtures for `normalized/ocsf_events/` where fixture B adds one new nullable column relative to fixture A,
    readers MUST be able to scan both together using union-by-name semantics, and the missing column MUST read as NULL for fixture A rows.
  - Given a deprecated column name and an `_schema.json` alias mapping, the query layer MUST resolve the canonical column name deterministically
    (prefer first alias; fall through to next; then NULL if none exist).
- Rule compilation tests: Sigma -> evaluation plan
- Bridge router multi-class routing tests:
  - Given a `logsource.category` routed to multiple `class_uid` values, compilation MUST scope evaluation to the union (`IN (...)` / OR semantics).
  - The routed `class_uid` set MUST be emitted in ascending numeric order (deterministic output).
- Lab provider parser tests: provider inventory export -> canonical `lab.assets` list
- Scenario selection tests: target selectors -> resolved target set (using a fixed inventory snapshot fixture)
- Criteria pack versioning tests:
  - `criteria/packs/<pack_id>/<pack_version>/manifest.json.pack_version` MUST match the directory `pack_version`.
  - If multiple search paths contain the same `(pack_id, pack_version)`, CI MUST fail unless the pack snapshots are byte-identical
    (manifest + criteria content hashes match).
- Criteria drift detection tests:
  - Given a criteria pack manifest upstream `(engine, source_ref, source_tree_sha256)` and a runner provenance that differs,
    the evaluator MUST set criteria drift to detected and MUST mark affected actions `status=skipped` with a deterministic drift reason field.
     
## Integration tests
- “Golden run” fixture: deterministic scenario + captured telemetry to validate end-to-end outputs.
- “Scenario suite” fixture: a small, representative set of techniques used as a regression pack.
- Telemetry fixture: raw Windows event XML corpus including missing rendered messages and at least one event containing binary-like payload data.
- Baseline comparison: compare current run outputs to a pinned baseline run bundle.
- Parquet historical-runs query fixture:
  - Build two minimal run bundles with different `normalized/ocsf_events/_schema.json` + Parquet schemas (additive change only).
  - Assert: the scoring/reporting query set completes successfully over both runs without requiring manual schema rewrites.
- OCSF migration fixture: when bumping the pinned `ocsf_version`, CI MUST re-normalize a fixed raw telemetry fixture set and compare to reviewed “golden” normalized outputs.
- Checkpoint-loss replay fixture:
  - Run normalization on a fixed raw telemetry fixture.
  - Delete/move `runs/<run_id>/logs/telemetry_checkpoints/` and restart normalization over the same inputs.
  - Assert: (1) normalized store remains unique by `metadata.event_id`, (2) `dedupe_duplicates_dropped_total > 0`,
    and (3) normalized outputs are deterministic relative to the baseline fixture.
    
## CI gates (seed)
- Schema validation of produced OCSF events
- Pinned-version consistency checks (fail closed):
  - `manifest.normalization.ocsf_version` (when present), `mapping_profile_snapshot.ocsf_version`, and bridge mapping pack `ocsf_version` (when present) MUST match.
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