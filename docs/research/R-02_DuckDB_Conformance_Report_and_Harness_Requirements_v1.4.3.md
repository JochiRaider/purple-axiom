---
title: R-02 DuckDB query plan stability conformance report and harness requirements v1.4.3
description: Defines a deterministic DuckDB conformance harness and report contract for plan and result stability.
status: draft
---

# R-02 DuckDB query plan stability conformance report and harness requirements v1.4.3

This report defines a deterministic conformance harness and report contract for DuckDB plan and
result stability. It describes the matrix, artifact layout, and pass or fail criteria for v1.4.3.

## Status

Draft (evidence capture pending)

## Summary

Purple Axiom relies on DuckDB for detection evaluation (Sigma) and expects deterministic outputs
suitable for golden fixtures and CI gating. This report defines:

- a concrete conformance report structure (machine-readable)
- the harness requirements needed to generate it deterministically
- the pass/fail criteria and failure classification semantics for CI

This document is a research artifact that links determinism risks to a specific, repeatable
conformance method. It is not a runtime run-bundle report.

## Research question

Does DuckDB `1.4.3` produce stable, byte-identical artifacts for identical inputs across:

- different OS platforms (Linux, macOS, Windows)
- different CPU architectures (x86_64, ARM64)
- patch and minor version bumps (example: `1.4.3` to `1.4.4`, `1.5.0`)

"Stable artifacts" are broken into two dimensions:

- **Plan stability**: `EXPLAIN (FORMAT json)` plan representation
- **Result stability**: query result set content, serialized deterministically

## Why it matters

If DuckDB plan or result artifacts drift across platform or patch/minor versions, Purple Axiom
golden fixtures and CI regressions can fail unpredictably. This increases operational burden,
weakens reproducibility claims, and complicates upgrade decisions.

## Scope

In scope:

- deterministic capture of DuckDB plans and results for a fixed Parquet fixture set and fixed SQL
  query set
- a conformance report contract suitable for CI gating and longitudinal comparisons
- explicit failure taxonomy aligned with project failure classification style

Out of scope:

- performance benchmarking (EPS, latency)
- correctness validation of Sigma logic beyond "same inputs produce same outputs"
- full Parquet byte-identity guarantees for `COPY TO PARQUET` outputs (tracked separately if needed)

## Assumptions

- The determinism goal for Purple Axiom is primarily **result stability** for evaluation outputs.
- Plan stability is diagnostic by default, not a release blocker, unless explicitly enabled as a
  gate.
- Conformance harness runs are executed in controlled environments where version pins are respected.

## Related normative artifacts

- Contract schema:
  [DuckDB conformance report schema](../contracts/duckdb_conformance_report.schema.json)
- CI integration requirements: [Test strategy CI spec](../spec/100_test_strategy_ci.md) section
  "DuckDB determinism conformance harness (toolchain qualification)"

## Conformance harness requirements

This section defines the required behavior of the harness that produces the conformance report.

### Matrix axes

The harness MUST support the following axes:

- `duckdb_version_semver`: example values `1.4.3`, `1.4.4`, `1.5.0`
- `os`: `linux | macos | windows`
- `arch`: `x86_64 | arm64`

A "cell" is one combination of `(duckdb_version_semver, os, arch)`.

### Deterministic DuckDB session settings

For each cell, the harness MUST set the following before any query executes:

- `SET threads = 1;`
- `SET TimeZone = 'UTC';`
- `SET explain_output = 'physical_only';`

The harness MUST NOT use `EXPLAIN ANALYZE` in the plan stability path.

### Query constraints

Each query fixture MUST be a single `SELECT` statement (CTEs allowed) and MUST define deterministic
row ordering:

- RECOMMENDED: outermost `ORDER BY ALL`

If a query cannot be made deterministically ordered, it MUST be excluded from conformance gating and
tracked as a separate research item.

### Fixture constraints

The harness MUST operate on a fixed Parquet fixture set and MUST compute deterministic fixture
fingerprints:

- `fixture_manifest_sha256`
- `parquet_schema_fingerprint_sha256`

All file enumerations MUST be stable:

- file lists MUST be sorted lexicographically by relative POSIX path before use
- report references MUST use forward slashes (`/`), even on Windows

## Canonicalization and hashing rules

### Hash algorithm

All hashes MUST be `sha256` and emitted as lowercase hex.

### JSON canonicalization

All JSON that is hashed for determinism MUST be canonicalized using RFC 8785 JSON Canonicalization
Scheme (JCS):

- UTF-8 encoding
- deterministic object key ordering (JCS)
- no insignificant whitespace
- no trailing newline unless explicitly stated (default: none)

### SQL bytes canonicalization

To avoid OS checkout differences, SQL fixtures MUST be normalized before hashing:

- input MUST be interpreted as UTF-8 (invalid UTF-8 is a fatal error)
- normalize line endings to LF
- remove trailing whitespace per line
- ensure exactly one trailing LF at end of file
- hash the resulting bytes as `sql_bytes_sha256`

### Plan capture and hashing

For each query in each cell:

- execute `EXPLAIN (FORMAT json) <query>`

- persist:

  - `plan.raw.json` (exact bytes as captured, UTF-8)
  - `plan.jcs.json` (parsed then JCS-canonicalized)

- compute:

  - `plan_raw_sha256`
  - `plan_jcs_sha256`

Conformance comparisons MUST use `plan_jcs_sha256` (not `plan_raw_sha256`).

### Result capture and hashing

For each query in each cell:

- execute the query and capture:

  - ordered column names
  - ordered DuckDB logical types
  - ordered rows

Canonical result encoding MUST be JSON in the shape:

```json
{
  "columns": [{"name": "col_a", "type": "VARCHAR"}],
  "rows": [["alice"], ["bob"]]
}
```

Value encoding rules:

- `NULL` -> JSON `null`
- booleans -> JSON boolean
- integers within safe JSON range -> JSON number
- any value that can exceed safe integer range (or is represented as exact decimal) MUST be encoded
  as JSON string
- timestamps MUST be encoded in a timezone-stable UTC form (RFC 3339 with `Z`)

The harness MUST persist `result.jcs.json` (JCS-canonicalized) and compute `result_jcs_sha256`.

## Output artifact layout

The harness MUST write outputs to a dedicated toolchain conformance artifact root (CI artifact), not
to `runs/<run_id>/...`.

Required path conventions:

- report root: `artifacts/duckdb_conformance/<report_id>/`
- consolidated report: `artifacts/duckdb_conformance/<report_id>/report.json`

A recommended per-cell layout is:

```text
artifacts/duckdb_conformance/<report_id>/
  report.json
  cells/
    duckdb=<duckdb_version>/os=<os>/arch=<arch>/
      env.json
      queries/<query_id>/
        query.sql
        plan.raw.json
        plan.jcs.json
        result.jcs.json
        hashes.json
```

Report consumers MUST rely on `report.json` as the index of record.

## Report contract

The consolidated report MUST conform to:

- `docs/contracts/duckdb_conformance_report.schema.json`

At minimum, the report MUST include:

- matrix axes (versions, oses, arches)

- fixture fingerprints

- query fingerprints

- per-cell, per-query hashes:

  - `plan_jcs_sha256`
  - `result_jcs_sha256`

- per-cell, per-query status and reason codes when not `pass`

- aggregated stability analysis:

  - within-version stability (plan and result)
  - cross-version drift markers

## Failure classification

The harness MUST classify failures deterministically.

### Status values

Per query per cell:

- `pass`
- `fail`
- `skipped`

If `status != pass`, a `reason_code` MUST be present.

### Reason codes

The following reason codes are reserved (non-exhaustive). Additional codes MAY be added using
`x_<token>` extension codes.

Harness/internal failures (fail-closed by default):

- `fixture_manifest_missing`
- `fixture_manifest_invalid`
- `fixture_schema_fingerprint_failed`
- `duckdb_init_failed`
- `query_execution_failed`
- `plan_capture_failed`
- `plan_parse_failed`
- `result_encode_failed`

Observed drift (policy-controlled):

- `result_hash_mismatch`
- `plan_hash_mismatch`

Skip (explicit, non-fatal):

- `unsupported_platform`
- `unsupported_duckdb_version`
- `insufficient_resources`

### CI gating policy

Default policy (RECOMMENDED):

- `result_hash_mismatch` MUST fail CI (fail closed)
- `plan_hash_mismatch` SHOULD warn and MUST NOT fail CI unless "plan stability gate" is explicitly
  enabled

## Test matrix and reporting template

This section is the expected structure for the first executed conformance run.

### Matrix under test

| DuckDB | OS      | Arch   | Cell executed | Result stable | Plan stable | Notes |
| ------ | ------- | ------ | ------------- | ------------- | ----------- | ----- |
| 1.4.3  | linux   | x86_64 | pending       | pending       | pending     |       |
| 1.4.3  | linux   | arm64  | pending       | pending       | pending     |       |
| 1.4.3  | macos   | x86_64 | pending       | pending       | pending     |       |
| 1.4.3  | macos   | arm64  | pending       | pending       | pending     |       |
| 1.4.3  | windows | x86_64 | pending       | pending       | pending     |       |
| 1.4.3  | windows | arm64  | pending       | pending       | pending     |       |

Version drift extensions (when executed):

| From  | To    | Result drift observed | Plan drift observed | Notes |
| ----- | ----- | --------------------- | ------------------- | ----- |
| 1.4.3 | 1.4.4 | pending               | pending             |       |
| 1.4.3 | 1.5.0 | pending               | pending             |       |

### Acceptance criteria for v1.4.3 qualification

To qualify DuckDB `1.4.3` as "supported" for Purple Axiom determinism purposes:

- result stability MUST hold within version across supported OS and architectures
- plan stability MAY drift; any drift MUST be recorded and attributable (via report artifacts)

If result stability does not hold:

- the report MUST identify the specific queries and cells

- the project MUST either:

  - tighten query constraints and canonicalization rules, or
  - narrow the supported platform matrix, or
  - pin a different DuckDB version

## Known determinism risk areas to watch

These items are tracked here to guide interpretation of results and future harness hardening:

- multi-threading effects (mitigated by `threads=1`)
- row ordering effects when queries lack a total ordering
- value rendering for time, timestamp, and high-precision numeric types
- Parquet writer byte-layout stability (out of scope for this report unless explicitly added)

## Recommended upgrade path and fixture refresh policy

- Treat DuckDB patch and minor upgrades as "conformance required" events.

- If only plan drift is observed:

  - allow upgrade without fixture refresh (default)
  - retain conformance report artifacts for traceability

- If result drift is observed:

  - block upgrade by default

  - require either:

    - a harness/encoding fix that restores stability, or
    - an explicit fixture refresh decision (documented with rationale)

## Next steps

1. Implement the harness to emit `duckdb_conformance_report_v1` and store CI artifacts under
   `artifacts/duckdb_conformance/<report_id>/`.

1. Execute the v1.4.3 matrix, attach `report.json` outputs, and update this research report with:

   - completed matrix tables
   - identified drift patterns
   - any required mitigations or narrowed support claims
