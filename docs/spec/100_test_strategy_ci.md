---
title: Test strategy and CI
description: Defines the unit, integration, and CI gating expectations for deterministic runs.
status: draft
---

# Test strategy and CI

This document defines the required unit tests, integration fixtures, and CI gates for Purple Axiom
runs. It focuses on deterministic outputs, pinned-version conformance, and regression protection.

## Unit tests

- Canonicalization tests: RFC 8785 (JCS) vectors + Purple Axiom hash-basis fixtures (byte-for-byte).
- Redaction tests: policy fixture vectors (argv redaction, regex redaction, truncation determinism,
  post-checks).
- Windows Event Log raw XML tests: identity-field extraction without RenderingInfo; binary field
  detection; payload limit truncation + SHA-256.
- Linux event identity basis tests: auditd/journald/syslog fixture vectors (Tier 1/Tier 2) + Tier 3
  collision fixture under `tests/fixtures/event_id/v1/`.
- Redaction posture tests: `security.redaction.enabled=false` MUST produce deterministic
  placeholders or quarantine-only outputs and MUST label the run as unredacted in metadata.
- Mapping unit tests: raw input -> expected OCSF output
- Mapping pack conformance tests: mapping YAML MUST parse deterministically (no duplicate keys, no
  anchors/aliases/merge keys), routing MUST be overlap-free, and
  `normalized/mapping_profile_snapshot.json` MUST include hashes for the complete mapping material
  boundary defined by the
  [OCSF mapping profile authoring guide](../mappings/ocsf_mapping_profile_authoring_guide.md).
- OCSF schema regression tests: representative normalized fixtures MUST validate against the pinned
  OCSF version used by v0.1.
- Parquet schema evolution tests (normalized store):
  - Given two Parquet fixtures for `normalized/ocsf_events/` where fixture B adds one new nullable
    column relative to fixture A, readers MUST be able to scan both together using union-by-name
    semantics, and the missing column MUST read as NULL for fixture A rows.
  - Given a deprecated column name and an `_schema.json` alias mapping, the query layer MUST resolve
    the canonical column name deterministically (prefer first alias; fall through to next; then NULL
    if none exist).
- Rule compilation tests: Sigma -> evaluation plan (authoritative supported subset and
  non-executable classification:
  [Sigma-to-OCSF bridge: backend adapter contract](065_sigma_to_ocsf_bridge.md#backend-adapter-contract-normative-v01)).
- Bridge router multi-class routing tests:
  - Given a `logsource.category` routed to multiple `class_uid` values, compilation MUST scope
    evaluation to the union (`IN (...)` / OR semantics).
  - The routed `class_uid` set MUST be emitted in ascending numeric order (deterministic output).
- Lab provider parser tests: provider inventory export -> canonical `lab.assets` list
- Scenario selection tests: target selectors -> resolved target set (using a fixed inventory
  snapshot fixture)
- Atomic runner determinism fixtures: extracted Atomic test -> resolved inputs -> `$ATOMICS_ROOT`
  canonicalization -> `resolved_inputs_sha256` and `action_key` under
  `tests/fixtures/runner/atomic/`.
- Criteria pack versioning tests:
  - `criteria/packs/<pack_id>/<pack_version>/manifest.json.pack_version` MUST match the directory
    `pack_version`.
  - If multiple search paths contain the same `(pack_id, pack_version)`, CI MUST fail unless the
    pack snapshots are byte-identical (manifest + criteria content hashes match).
- Criteria drift detection tests:
  - Given a criteria pack manifest upstream `(engine, source_ref, source_tree_sha256)` and a runner
    provenance that differs, the evaluator MUST set criteria drift to detected and MUST mark
    affected actions `status=skipped` with a deterministic drift reason field.

## Integration tests

- DuckDB determinism conformance harness (toolchain qualification; default backend semantics:
  [Sigma-to-OCSF bridge: evaluator backend adapter](065_sigma_to_ocsf_bridge.md#3-evaluator-backend-adapter)):

  - Purpose: qualify DuckDB (version × OS × arch) for deterministic evaluation outputs over fixed
    Parquet fixtures and fixed SQL queries, and record drift across patch/minor upgrades.
  - Harness MUST run each matrix cell with:
    - `SET threads = 1;`
    - `SET TimeZone = 'UTC';`
    - `SET explain_output = 'physical_only';`
  - For each query fixture, the harness MUST:
    - Execute `EXPLAIN (FORMAT json) <query>` and compute `plan_jcs_sha256` over a JCS-canonicalized
      JSON plan representation.
    - Execute the query and compute `result_jcs_sha256` over a JCS-canonicalized JSON result
      representation.
    - Require a deterministic total ordering of rows (RECOMMENDED: outermost `ORDER BY ALL`).
  - The harness MUST emit a consolidated report:
    - Path (CI artifact): `artifacts/duckdb_conformance/<report_id>/report.json`
    - The report MUST conform to the
      [DuckDB conformance report schema](../contracts/duckdb_conformance_report.schema.json).
  - Failure classification MUST be explicit per cell and per query:
    - Harness internal failures (e.g., init/execute/parse/encode) MUST be recorded as `status=fail`
      with a stable `reason_code`.
    - Observed drift MUST be recorded deterministically:
      - `result_hash_mismatch` (result drift)
      - `plan_hash_mismatch` (plan drift)
    - Unsupported cells MAY be recorded as `status=skipped` with a stable `reason_code`.

- “Golden run” fixture: deterministic scenario + captured telemetry to validate end-to-end outputs.

- “Scenario suite” fixture: a small, representative set of techniques used as a regression pack.

- Atomic runner conformance fixture (lab-gated): execute a pinned Atomic action twice with identical
  inputs and assert stable `resolved_inputs_sha256` and stable `action_key`. See
  `tests/integration/test_atomic_runner_conformance.py`.

- Telemetry fixture: raw Windows event XML corpus including missing rendered messages and at least
  one event containing binary-like payload data.

- Windows Event Log raw-mode conformance test (collector + validator):

  - Use an OTel collector config where every enabled `windowseventlog/*` receiver sets `raw: true`.
  - Inject a canary event and assert the captured payload begins with `<Event` and MUST NOT contain
    `<RenderingInfo>`.
  - The validator MUST record the outcome as `health.json` stage
    `telemetry.windows_eventlog.raw_mode` (see the [operability specification](110_operability.md)).

- Windows Event Log raw/unrendered failure-mode tests:

  - Missing publisher/manifest metadata with raw XML present MUST NOT fail ingestion; MUST increment
    `wineventlog_rendering_metadata_missing_total`.
  - Raw XML unavailable MUST fail telemetry stage under `fail_mode: fail_closed`; under
    `fail_mode: warn_and_skip` MUST skip the record and increment
    `wineventlog_raw_unavailable_total`.
  - Oversize raw XML MUST truncate deterministically and create a content-addressed sidecar
    `${sha256}.xml` with `payload_overflow_ref` pointing to `${sidecar.path}/${sha256}.xml`.
  - Binary decode failure MUST not drop the record; MUST emit bounded summary and increment
    `wineventlog_binary_decode_failed_total`.

- Baseline comparison: compare current run outputs to a pinned baseline run bundle.

- Parquet historical-runs query fixture:

  - Build two minimal run bundles with different `normalized/ocsf_events/_schema.json` + Parquet
    schemas (additive change only).
  - Assert: the scoring/reporting query set completes successfully over both runs without requiring
    manual schema rewrites.

- OCSF migration fixture: when bumping the pinned `ocsf_version`, CI MUST re-normalize a fixed raw
  telemetry fixture set and compare to reviewed “golden” normalized outputs.

- Checkpoint-loss replay fixture:

  - Run normalization on a fixed raw telemetry fixture.
  - Delete/move `runs/<run_id>/logs/telemetry_checkpoints/` and restart normalization over the same
    inputs.
  - Assert: (1) normalized store remains unique by `metadata.event_id`, (2)
    `dedupe_duplicates_dropped_total > 0`, and (3) normalized outputs are deterministic relative to
    the baseline fixture.

- File-tailed crash+rotation continuity fixture (R-01):

  - Use a synthetic NDJSON writer that emits a monotonic `seq` field and rotates the file at a fixed
    byte or line threshold.
  - Configure the collector `filelog` receiver with `storage: file_storage` (filestorage) and
    capture the storage directory as a test artifact.
  - Matrix (minimum): OS={Windows, Linux} × rotation={rename+create, copytruncate} × crash={graceful
    stop, hard kill}.
  - Assert per matrix cell:
    - `loss_pct == 0` for the window spanning (pre-rotation, rotation, post-rotation) and the crash
      boundary.
    - `dup_pct` is computed and recorded (duplication is acceptable but MUST be bounded and
      observable).
    - Results include collector config hash and a deterministic fingerprint of the checkpoint
      directory contents.

## CI gates (seed)

- Schema validation of produced OCSF events
- Schema validation of effective configuration (`range.yaml`) against
  `docs/contracts/range_config.schema.json`
- Pinned-version consistency checks (fail closed):
  - `manifest.normalization.ocsf_version` (when present), `mapping_profile_snapshot.ocsf_version`,
    and bridge mapping pack `ocsf_version` (when present) MUST match.
- External dependency version matrix (fail closed; v0.1):
  - CI MUST run the integration and “golden run” fixtures using the pinned dependency versions in
    the [supported versions reference](../../SUPPORTED_VERSIONS.md).
  - CI MUST fail if any runtime dependency version differs from the pins for an enabled stage.
  - Minimum pinned set (v0.1):
    - OpenTelemetry Collector Contrib (otelcol-contrib distribution): `0.143.1`
    - pySigma: `1.1.0`
    - DuckDB: `1.4.3`
    - osquery: `5.14.1`
    - OCSF schema: `1.7.0`
- DuckDB conformance gate (toolchain determinism; configurable):
  - Default CI behavior (RECOMMENDED):
    - `result_hash_mismatch` MUST fail CI (fail closed).
    - `plan_hash_mismatch` SHOULD warn but MUST NOT fail CI unless explicitly enabled as a gate.
  - CI SHOULD retain the conformance report as a build artifact to support:
    - fixture refresh review on DuckDB upgrades
    - platform qualification (OS/arch) changes
    - drift triage when golden fixtures regress
- Linting/validation for Sigma rules
- Report generation sanity checks
- Artifact manifest completeness check
- Cross-artifact invariants:
  - `run_id`/`scenario_id` consistency
  - referential integrity (detections reference existing `event_id` values)
  - inventory snapshot hash matches manifest input hash
  - when `operability.health.emit_health_files=true`, `runs/<run_id>/logs/health.json` MUST exist
    and MUST satisfy the minimum schema in the [operability specification](110_operability.md)
    ("Health files (normative, v0.1)").
- Regression gates (configurable thresholds):
  - technique coverage must not drop more than X relative to baseline
  - latency percentiles must not exceed Y
  - “missing_telemetry” and “normalization_gap” rates must not exceed Z

## CI workflow pattern (recommended)

1. Resolve lab inventory (provider or fixture)
1. Execute scenario suite (runner)
1. Collect and normalize telemetry (OTel -> OCSF)
1. Evaluate detections (Sigma) and score gaps
1. Produce report + machine-readable summary
1. Compare to baseline and fail the pipeline when thresholds are violated

## References

- [OCSF mapping profile authoring guide](../mappings/ocsf_mapping_profile_authoring_guide.md)
- [Sigma to OCSF bridge specification](065_sigma_to_ocsf_bridge.md)
- [Operability specification](110_operability.md)
- [Telemetry pipeline specification](040_telemetry_pipeline.md)
- [DuckDB conformance report schema](../contracts/duckdb_conformance_report.schema.json)
- [Supported versions reference](../../SUPPORTED_VERSIONS.md)

## Changelog

| Date       | Change            |
| ---------- | ----------------- |
| 2026-01-12 | Formatting update |
