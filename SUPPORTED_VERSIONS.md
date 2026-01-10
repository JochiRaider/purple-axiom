<!-- SUPPORTED_VERSIONS.md -->
# External Dependency Requirements (v0.1)

This file defines the pinned external dependency versions that are **tested and supported** for Purple Axiom **v0.1**.

This file lists **top-level pins** for runtime and CI toolchain dependencies. Transitive dependencies are pinned by
lockfiles (for example, `uv.lock`) and are intentionally not enumerated here.

## Runtime version pins (normative)

For v0.1 builds and CI runs, the implementation MUST use the pinned versions below, unless a spec update explicitly
changes the pins.

| Dependency | Pinned version | Used by | Notes |
|---|---:|---|---|
| OpenTelemetry Collector Contrib (otelcol-contrib distribution) | 0.143.1 | Telemetry collection | Pin the released distribution artifacts (`opentelemetry-collector-releases`). Upstream component source tags may differ by patch due to release automation. |
| pySigma | 1.1.0 | Sigma parsing + compilation | CI and production MUST use the same pySigma major/minor to avoid compilation drift. |
| DuckDB | 1.4.3 | Batch evaluator backend (`duckdb_sql`) | Pin exact version for stable query planning behavior across “golden run” fixtures. |
| osquery | 5.14.1 | Endpoint telemetry (osqueryd) | Pin official packages for lab assets; CI fixtures should record `osqueryd --version` for provenance. |
| OCSF schema | 1.7.0 | Normalization target | v0.1 is pinned to OCSF 1.7.0; see `docs/spec/050_normalization_ocsf.md` for migration policy and `docs/spec/120_config_reference.md` for config pin. |

## Toolchain and CI pins (normative for CI; guidance for local)

CI MUST run using the pinned toolchain versions below. Local developer environments SHOULD match these pins. If local
versions differ, they MUST NOT be used to generate or bless “golden” fixtures.

Toolchain baseline (v0.1):
- Python: **3.12.3**
  - Enforcement hooks: `.python-version` and `pyproject.toml` (`requires-python`) SHOULD be set to prevent drift.
- uv: **0.9.18**
  - Enforcement hooks: CI SHOULD run `uv --version` and MUST fail if it differs from the pinned value.

| Dependency         | Pinned version | Used by                     | Notes                                        |
| ------------------ | -------------: | --------------------------- | -------------------------------------------- |
| pytest             |          9.0.2 | Unit + integration tests    | CI gate                                      |
| pytest-regressions |          2.9.1 | Golden/regression fixtures  | CI gate for “golden outputs”                 |
| ruff               |        0.14.11 | Lint + format               | Lint + format gate                           |
| pyright            |        1.1.408 | Type checking               | type-check gate                              |
| pre-commit         |          4.5.1 | Local + CI hook runner      | CI SHOULD enforce hook parity                |

## Version drift policy (normative)

1. CI MUST fail closed if any dependency version differs from the pins above for an enabled stage.
2. Any dependency bump MUST be accompanied by:
   - updated pins in this file, and
   - reviewed updates to “golden” fixture outputs where behavior changes are observable.

## Compatibility notes (v0.1 guidance)

- **Collector upgrades:** treat as potentially behavior-changing for receivers and processors; re-run Windows Event Log raw-mode
  conformance fixtures and checkpoint/rotation fixtures.
- **pySigma upgrades:** treat as behavior-changing for rule parsing/modifier semantics; re-run rule compilation fixtures and
  “golden equivalence” backend gates.
- **DuckDB upgrades:** treat as behavior-changing for SQL execution and parquet scanning; re-run evaluator fixtures and
  report generation sanity checks.
- **osquery upgrades:** treat as potentially behavior-changing for table schemas and event backends; re-run mapping fixtures
  for any affected event tables and update “known limitations” documentation as needed.
- **Toolchain upgrades (pytest, ruff, pyright, pre-commit):** treat as potentially behavior-changing for CI gating and
  fixture stability; re-run formatting, typecheck, and “golden outputs” gates and review diffs before blessing updates.  