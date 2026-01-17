---
title: Test strategy and CI
description: Defines the unit, integration, and CI gating expectations for deterministic runs.
status: draft
category: spec
related:
  - 065_sigma_to_ocsf_bridge.md
  - 110_operability.md
  - 040_telemetry_pipeline.md
---

# Test strategy and CI

This document defines the required unit tests, integration fixtures, and CI gates for Purple Axiom
runs. It establishes the testing approach that ensures deterministic outputs, pinned-version
conformance, and regression protection across all pipeline stages.

## Overview

**Summary**: Purple Axiom requires deterministic, reproducible pipeline outputs. This spec defines
the testing layers (unit, integration, CI gates) that enforce determinism, detect drift, and protect
against regressions.

The testing strategy addresses three core concerns. First, determinism verification ensures that
identical inputs produce byte-identical outputs across runs, platforms, and time. Second, version
conformance validates that all pipeline stages use pinned dependency versions and produce outputs
conforming to pinned schemas. Third, regression protection detects coverage drops, performance
degradation, and semantic drift before they reach production.

## Scope

This document covers:

- Unit test requirements for each pipeline component
- Integration test fixtures and harnesses
- CI gate definitions and failure semantics
- Recommended CI workflow patterns

This document does NOT cover:

- Implementation details of specific test frameworks
- Manual QA procedures
- Performance benchmarking beyond latency regression gates

## Unit tests

**Summary**: Unit tests validate individual components in isolation using deterministic fixtures.
Each test category targets a specific pipeline stage or cross-cutting concern.

### Event identity and canonicalization

Canonicalization tests validate RFC 8785 (JCS) vectors plus Purple Axiom hash-basis fixtures,
requiring byte-for-byte determinism.

Windows Event Log raw XML tests validate identity-field extraction without RenderingInfo, binary
field detection, and payload limit truncation with SHA-256 computation.

Linux event identity basis tests use auditd/journald/syslog fixture vectors covering Tier 1 and Tier
2 fields, plus Tier 3 collision fixtures under `tests/fixtures/event_id/v1/`.

### Redaction

Redaction tests validate policy fixture vectors including argv redaction, regex redaction,
truncation determinism, and post-checks.

Redaction posture tests validate that `security.redaction.enabled=false` MUST produce deterministic
placeholders or quarantine-only outputs and MUST label the run as unredacted in metadata.

### Normalization and mapping

Mapping unit tests validate raw input to expected OCSF output transformations.

Mapping pack conformance tests validate that mapping YAML MUST parse deterministically (no duplicate
keys, no anchors/aliases/merge keys), routing MUST be overlap-free, and
`normalized/mapping_profile_snapshot.json` MUST include hashes for the complete mapping material
boundary defined by the
[OCSF mapping profile authoring guide](../mappings/ocsf_mapping_profile_authoring_guide.md).

OCSF schema regression tests validate that representative normalized fixtures MUST validate against
the pinned OCSF version used by v0.1.

### Runner contracts (ground truth lifecycle)

Ground truth schema tests MUST validate representative fixtures against the pinned
`ground_truth.schema.json`, including lifecycle and idempotence fields:

- Fixtures MUST include `idempotence` and a `lifecycle.phases[]` array containing all four phases:
  - `prepare`, `execute`, `revert`, `teardown`.
- Phase records MUST be ordered and MUST include `started_at_utc`, `ended_at_utc`, and
  `phase_outcome`.
- The fixture suite MUST include at least one failure case where `revert` or `teardown` is `failed`
  and is surfaced deterministically in runner-stage outcomes and reporting inputs.

### Schema evolution

Parquet schema evolution tests for the normalized store cover two scenarios.

For additive columns: given two Parquet fixtures for `normalized/ocsf_events/` where fixture B adds
one new nullable column relative to fixture A, readers MUST be able to scan both together using
union-by-name semantics, and the missing column MUST read as NULL for fixture A rows.

For alias resolution: given a deprecated column name and an `_schema.json` alias mapping, the query
layer MUST resolve the canonical column name deterministically (prefer first alias, fall through to
next, then NULL if none exist).

The same fixture MUST assert lifecycle conformance:

- Ground truth MUST include `idempotence` and `lifecycle.phases[]`.
- `lifecycle.phases[]` MUST be in phase order and MUST include `prepare` and `execute`.
- When cleanup verification is enabled, `teardown` MUST include a stable reference to
  `runner/actions/<action_id>/cleanup_verification.json` and reflect the aggregate outcome.

### Sigma compilation (bridge)

Rule compilation tests validate Sigma to evaluation plan compilation for the authoritative supported
subset and non-executable classification defined in
[Sigma-to-OCSF bridge: backend adapter contract](065_sigma_to_ocsf_bridge.md#backend-adapter-contract-normative-v01).

Fixtures for `duckdb_sql` compilation patterns MUST cover:

- Case-insensitive equality using `lower(field) = lower(value)` and inequality using
  `IS DISTINCT FROM`
- LIKE/ILIKE escaping for `$`, `%`, and `_`
- Regex acceptance for RE2-compatible patterns and rejection of PCRE-only constructs with
  `unsupported_regex` and a stable `PA_SIGMA_...` code in the explanation
- LIST-typed field semantics using `list_contains`, `list_has_any`, and `list_has_all` selection
  based on schema type

Bridge router multi-class routing tests validate that given a `logsource.category` routed to
multiple `class_uid` values, compilation MUST scope evaluation to the union (`IN (...)` / OR
semantics) and the routed `class_uid` set MUST be emitted in ascending numeric order for
deterministic output.

### Runner and execution

Lab provider parser tests validate provider inventory export to canonical `lab.assets` list
transformation.

Scenario selection tests validate target selectors to resolved target set conversion using a fixed
inventory snapshot fixture.

Atomic runner determinism fixtures under `tests/fixtures/runner/atomic/` validate that extracted
Atomic test to resolved inputs to `$ATOMICS_ROOT` canonicalization produces stable
`resolved_inputs_sha256` and `action_key`.

State reconciliation fixtures under `tests/fixtures/runner/state_reconciliation/` validate
deterministic environment drift reporting (distinct from baseline drift in evaluator and
conformance harnesses).

The fixture set MUST include at least:

- `record_present_reality_absent`:
  - Input: a `side_effect_ledger.json` entry indicating a resource is present/created.
  - Probe snapshot: observed state indicates the resource is absent.
  - Expected: `state_reconciliation_report.status=drift_detected` with a deterministic
    `reason_code`.
- `record_absent_reality_present`:
  - Input: a `side_effect_ledger.json` entry indicating a resource is absent/deleted.
  - Probe snapshot: observed state indicates the resource is present.
  - Expected: `state_reconciliation_report.status=drift_detected` with a deterministic
    `reason_code`.
- `clean_match`:
  - Input: a `side_effect_ledger.json` entry indicating a resource is present/created.
  - Probe snapshot: observed state indicates the resource is present.
  - Expected: `state_reconciliation_report.status=clean`.

For each fixture, the runner reconciliation implementation MUST:

- Emit `runner/actions/<action_id>/state_reconciliation_report.json` with deterministic item
  ordering as specified in the data contracts.
- In the test harness, compute a stable hash over the report content (RECOMMENDED:
  `report_jcs_sha256` over RFC 8785 JCS canonicalized JSON) and assert the hash is identical
  across repeated runs with identical inputs and probe snapshots.

### Criteria evaluation

Criteria pack versioning tests validate that
`criteria/packs/<pack_id>/<pack_version>/manifest.json.pack_version` MUST match the directory
`pack_version`. If multiple search paths contain the same `(pack_id, pack_version)`, CI MUST fail
unless the pack snapshots are byte-identical (manifest plus criteria content hashes match).

Criteria drift detection tests validate that given a criteria pack manifest upstream with
`(engine, source_ref, source_tree_sha256)` and a runner provenance that differs, the evaluator MUST
set criteria drift to detected and MUST mark affected actions `status=skipped` with a deterministic
drift reason field.

## Integration tests

**Summary**: Integration tests validate cross-component behavior using realistic fixtures and
harnesses. They cover end-to-end scenarios, platform-specific behaviors, and recovery from failure
conditions.

### DuckDB conformance harness

The DuckDB determinism conformance harness qualifies the DuckDB toolchain for deterministic
evaluation outputs. It is the default backend for
[Sigma-to-OCSF bridge: evaluator backend adapter](065_sigma_to_ocsf_bridge.md#3-evaluator-backend-adapter).

Purpose: qualify DuckDB (version × OS × arch) for deterministic evaluation outputs over fixed
Parquet fixtures and fixed SQL queries, and record drift across patch/minor upgrades.

The harness MUST run each matrix cell with the following settings:

```sql
SET threads = 1;
SET TimeZone = 'UTC';
SET explain_output = 'physical_only';
```

For each query fixture, the harness MUST execute `EXPLAIN (FORMAT json) <query>` and compute
`plan_jcs_sha256` over a JCS-canonicalized JSON plan representation, execute the query and compute
`result_jcs_sha256` over a JCS-canonicalized JSON result representation, and require a deterministic
total ordering of rows (RECOMMENDED: outermost `ORDER BY ALL`).

The harness MUST emit a consolidated report to
`artifacts/duckdb_conformance/<report_id>/report.json` conforming to the
[DuckDB conformance report schema](../contracts/duckdb_conformance_report.schema.json).

Failure classification MUST be explicit per cell and per query. Harness internal failures (init,
execute, parse, encode) MUST be recorded as `status=fail` with a stable `reason_code`. Observed
drift MUST be recorded deterministically as `result_hash_mismatch` (result drift) or
`plan_hash_mismatch` (plan drift). Unsupported cells MAY be recorded as `status=skipped` with a
stable `reason_code`.

### End-to-end fixtures

The "golden run" fixture uses a deterministic scenario plus captured telemetry to validate
end-to-end outputs.

The "scenario suite" fixture provides a small, representative set of techniques used as a regression
pack.

The atomic runner conformance fixture (lab-gated) executes a pinned Atomic action twice with
identical inputs and asserts stable `resolved_inputs_sha256` and stable `action_key`. See
`tests/integration/test_atomic_runner_conformance.py`.

The baseline comparison fixture compares current run outputs to a pinned baseline run bundle.

### Telemetry collection

The telemetry fixture provides a raw Windows event XML corpus including missing rendered messages
and at least one event containing binary-like payload data.

#### Windows Event Log raw-mode conformance

This test validates the collector plus validator integration. Use an OTel collector config where
every enabled `windowseventlog/*` receiver sets `raw: true`. Inject a canary event and assert the
captured payload begins with `<Event` and MUST NOT contain `<RenderingInfo>`. The validator MUST
record the outcome as `health.json` stage `telemetry.windows_eventlog.raw_mode` (see the
[operability specification](110_operability.md)).

#### Windows Event Log failure modes

Missing publisher/manifest metadata with raw XML present MUST NOT fail ingestion and MUST increment
`wineventlog_rendering_metadata_missing_total`.

Raw XML unavailable MUST fail telemetry stage under `fail_mode: fail_closed`. Under
`fail_mode: warn_and_skip`, it MUST skip the record and increment
`wineventlog_raw_unavailable_total`.

Oversize raw XML MUST truncate deterministically and create a content-addressed sidecar
`${sha256}.xml` with `payload_overflow_ref` pointing to `${sidecar.path}/${sha256}.xml`.

Binary decode failure MUST NOT drop the record. It MUST emit bounded summary and increment
`wineventlog_binary_decode_failed_total`.

### Schema and version migration

The Parquet historical-runs query fixture builds two minimal run bundles with different
`normalized/ocsf_events/_schema.json` plus Parquet schemas (additive change only) and asserts that
the scoring/reporting query set completes successfully over both runs without requiring manual
schema rewrites.

The OCSF migration fixture validates that when bumping the pinned `ocsf_version`, CI MUST
re-normalize a fixed raw telemetry fixture set and compare to reviewed "golden" normalized outputs.

### Reliability and recovery

#### Checkpoint-loss replay

Run normalization on a fixed raw telemetry fixture. Delete or move
`runs/<run_id>/logs/telemetry_checkpoints/` and restart normalization over the same inputs. Assert
that the normalized store remains unique by `metadata.event_id`, that
`dedupe_duplicates_dropped_total > 0`, and that normalized outputs are deterministic relative to the
baseline fixture.

#### File-tailed crash and rotation continuity (R-01)

Use a synthetic NDJSON writer that emits a monotonic `seq` field and rotates the file at a fixed
byte or line threshold. Configure the collector `filelog` receiver with `storage: file_storage`
(filestorage) and capture the storage directory as a test artifact.

The minimum matrix covers OS (Windows, Linux) × rotation (rename+create, copytruncate) × crash
(graceful stop, hard kill).

Assert per matrix cell that `loss_pct == 0` for the window spanning pre-rotation, rotation, and
post-rotation plus the crash boundary. Compute and record `dup_pct` (duplication is acceptable but
MUST be bounded and observable). Results include collector config hash and a deterministic
fingerprint of the checkpoint directory contents.

## CI gates

**Summary**: CI gates define pass/fail criteria for pipeline runs. Gates are categorized as
fail-closed (blocking) or configurable (threshold-based).

### Schema validation

Schema validation of produced OCSF events ensures all normalized events conform to the pinned OCSF
schema.

Schema validation of effective configuration validates `range.yaml` against
`docs/contracts/range_config.schema.json`.

### Version conformance

Pinned-version consistency checks (fail closed) validate that `manifest.normalization.ocsf_version`
(when present), `mapping_profile_snapshot.ocsf_version`, and bridge mapping pack `ocsf_version`
(when present) MUST match.

External dependency version matrix (fail closed; v0.1) requires CI MUST run the integration and
"golden run" fixtures using the pinned dependency versions in the
[supported versions reference](../../SUPPORTED_VERSIONS.md). CI MUST fail if any runtime dependency
version differs from the pins for an enabled stage.

The minimum pinned set for v0.1:

| Dependency                      | Version |
| ------------------------------- | ------- |
| OpenTelemetry Collector Contrib | 0.143.1 |
| pySigma                         | 1.1.0   |
| DuckDB                          | 1.4.3   |
| osquery                         | 5.14.1  |
| OCSF schema                     | 1.7.0   |

### Determinism gates

The DuckDB conformance gate (toolchain determinism; configurable) enforces deterministic query
execution. Default CI behavior (RECOMMENDED): `result_hash_mismatch` MUST fail CI (fail closed) and
`plan_hash_mismatch` SHOULD warn but MUST NOT fail CI unless explicitly enabled as a gate.

CI SHOULD retain the conformance report as a build artifact to support fixture refresh review on
DuckDB upgrades, platform qualification (OS/arch) changes, and drift triage when golden fixtures
regress.

### Artifact validation

Linting and validation for Sigma rules ensures syntactic and semantic correctness.

Report generation sanity checks validate that reports render without errors.

Artifact manifest completeness check ensures all expected artifacts are present.

### Cross-artifact invariants

Cross-artifact invariants enforce consistency across pipeline outputs:

- `run_id` and `scenario_id` consistency across all artifacts
- Referential integrity (detections reference existing `event_id` values)
- Inventory snapshot hash matches manifest input hash
- When `operability.health.emit_health_files=true`, `runs/<run_id>/logs/health.json` MUST exist and
  MUST satisfy the minimum schema in the [operability specification](110_operability.md) ("Health
  files (normative, v0.1)")

### Regression gates

Regression gates (configurable thresholds) protect against coverage and performance degradation:

- Technique coverage must not drop more than X relative to baseline
- Latency percentiles must not exceed Y
- `missing_telemetry` and `normalization_gap` rates must not exceed Z

## CI workflow pattern

The recommended CI workflow proceeds through six stages:

1. Resolve lab inventory (provider or fixture)
1. Execute scenario suite (runner)
1. Collect and normalize telemetry (OTel to OCSF)
1. Evaluate detections (Sigma) and score gaps
1. Produce report plus machine-readable summary
1. Compare to baseline and fail the pipeline when thresholds are violated

## Key decisions

- Unit tests are organized by pipeline stage to enable targeted validation and clear ownership.
- The DuckDB conformance harness provides toolchain qualification across the version × OS × arch
  matrix.
- CI gates use fail-closed semantics for version conformance and configurable thresholds for
  regression protection.
- Fixtures cover both happy-path determinism and failure-mode recovery scenarios.

## References

- [OCSF mapping profile authoring guide](../mappings/ocsf_mapping_profile_authoring_guide.md)
- [Sigma-to-OCSF bridge specification](065_sigma_to_ocsf_bridge.md)
- [Operability specification](110_operability.md)
- [Telemetry pipeline specification](040_telemetry_pipeline.md)
- [Normalization to OCSF specification](050_normalization_ocsf.md)
- [Data contracts specification](025_data_contracts.md)
- [DuckDB conformance report schema](../contracts/duckdb_conformance_report.schema.json)
- [Supported versions reference](../../SUPPORTED_VERSIONS.md)

## Changelog

| Date       | Change                           |
| ---------- | -------------------------------- |
| 2026-01-13 | Style guide conformance reformat |
| 2026-01-12 | Formatting update                |
