<!-- tests/fixtures/duckdb_conformance/README.md -->

# DuckDB Conformance Baselines

This directory contains checked-in baselines used to gate DuckDB determinism conformance in CI.

These baselines are distinct from CI conformance outputs:

- **Baselines (this directory)** are committed and represent the expected hashes for a given DuckDB
  version and fixture set.
- **CI outputs** (full conformance reports) are ephemeral build artifacts and MUST NOT be committed.

## What is being baselined

Baselines capture deterministic expectations for:

- fixture fingerprinting:
  - `fixture_manifest_sha256`
  - `parquet_schema_fingerprint_sha256`
- query identity:
  - `sql_bytes_sha256` for each `query_id`
- conformance expectations:
  - expected `result_jcs_sha256` per query (normative gate)
  - optional expected `plan_jcs_sha256` set per query (diagnostic by default)

Baselines are version-scoped because DuckDB upgrades may legitimately change plan shapes or results.

## Directory structure (normative)

Baselines MUST be stored under:

`tests/baselines/duckdb_conformance/baseline_v1/duckdb-<duckdb_version_semver>/fixture-<fixture_id>/baseline.json`

Where:

- `<duckdb_version_semver>` is the DuckDB semver string (example: `1.4.3`)
- `<fixture_id>` matches the fixture identifier used by the conformance harness

## Baseline file format (normative)

The baseline file MUST be valid UTF-8 JSON and MUST use stable ordering:

- arrays MUST be sorted by `query_id`
- objects SHOULD be serialized deterministically in tooling (do not rely on Python dict insertion
  order)

The baseline file contract version is:

- `duckdb_conformance_baseline_v1`

## CI behavior (normative)

In CI:

1. The harness MUST execute the conformance matrix and emit an ephemeral report:

   - `artifacts/duckdb_conformance/<report_id>/report.json`
   - Report MUST conform to `docs/contracts/duckdb_conformance_report.schema.json`

1. The harness (or a comparator step) MUST compare observed hashes to the checked-in baseline
   matching the pinned DuckDB version and fixture id.

1. CI gating:

   - `result_hash_mismatch` MUST fail CI (fail closed).
   - `plan_hash_mismatch` SHOULD warn and MUST NOT fail CI unless a plan gate is explicitly enabled.

## Baseline update policy (normative)

Baselines MUST only be updated via an explicit decision (for example, a DuckDB version bump or an
intentional fixture refresh).

If result hashes change for a pinned DuckDB version without an intentional change:

- This is a determinism regression and MUST be investigated.
- The baseline MUST NOT be updated as a “fix” unless the project explicitly accepts the change.

If a baseline update is approved:

- The update MUST include:
  - the new `baseline.json`
  - the corresponding ephemeral `report.json` attached to CI logs/artifacts for review
  - a short rationale in the PR description (what changed and why it is acceptable)
