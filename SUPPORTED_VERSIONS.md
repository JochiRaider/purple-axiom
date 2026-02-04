---
title: Supported versions
description: Pinned external dependency versions tested and supported for Purple Axiom v0.1.
status: v0.1
---

# Supported versions

This file defines the pinned external dependency versions that are tested and supported for Purple
Axiom v0.1.

This file lists **top-level pins** for runtime and CI toolchain dependencies. Transitive
dependencies are pinned by lockfiles (for example, `uv.lock`) and are intentionally not enumerated
here.

## Runtime version pins (normative)

For v0.1 builds and CI runs, the implementation MUST use the pinned versions below, unless a spec
update explicitly changes the pins.

| Dependency                                                     | Pinned version | Used by                                            | Notes                                                                                                                                                                                                            |
| -------------------------------------------------------------- | -------------: | -------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| OpenTelemetry Collector Contrib (otelcol-contrib distribution) |        0.143.1 | Telemetry collection                               | Pin the released distribution artifacts (`opentelemetry-collector-releases`). Upstream component source tags may differ by patch due to release automation.                                                      |
| pySigma                                                        |          1.1.0 | Sigma parsing + compilation                        | CI and production MUST use the same pySigma major/minor to avoid compilation drift.                                                                                                                              |
| pySigma-pipeline-ocsf                                          |          0.1.1 | Sigma-to-OCSF bridge (OCSF pipeline)               | Pin exact version to avoid field/logsource mapping drift that would destabilize compiled plans and golden fixtures.                                                                                              |
| PCRE2 (libpcre2-8)                                             |          10.47 | Regex engine for native evaluator (`native_pcre2`) | Pin exact version for stable regex semantics and bounded execution behavior across "golden run" fixtures.                                                                                                        |
| pyarrow                                                        |         22.0.0 | Storage formats (Parquet)                          | Pin exact version for stable Parquet scanning behavior and deterministic schema inspection across CI and "golden run" fixtures.                                                                                  |
| jsonschema                                                     |         4.26.0 | Contract validation (JSON/JSONL)                   | Pin exact version for stable JSON Schema Draft 2020-12 validation behavior and deterministic error reporting across CI and production.                                                                           |
| osquery                                                        |         5.14.1 | Endpoint telemetry (osqueryd)                      | Pin official packages for lab assets; CI fixtures should record `osqueryd --version` for provenance.                                                                                                             |
| OCSF schema                                                    |          1.7.0 | Normalization target                               | v0.1 is pinned to OCSF 1.7.0; see the [OCSF normalization specification](docs/spec/050_normalization_ocsf.md) for migration policy and the [config reference](docs/spec/120_config_reference.md) for config pin. |
| PowerShell                                                     |          7.4.6 | Runner (Atomic executor)                           | Pin exact version for stable transcript encoding and module behavior                                                                                                                                             |
| Desired State Configuration (DSC) v3 (`dsc`)                   |          3.1.2 | Runner (environment_config)                        | Pin exact version for stable baseline provisioning semantics across platforms and deterministic pre-flight evidence; record `dsc --version` for provenance when used.                                            |
| asciinema                                                      |          2.4.0 | Runner (terminal session recording)                | Pin v2.x to preserve asciicast v2 output expected by Purple Axiom; record `asciinema --version` for provenance when capture is enabled.                                                                          |

## Toolchain and CI pins (normative for CI and guidance for local)

CI MUST run using the pinned toolchain versions below. Local developer environments SHOULD match
these pins. If local versions differ, they MUST NOT be used to generate or bless "golden" fixtures.

Toolchain baseline (v0.1):

- Python: **3.12.3**
  - Enforcement hooks: `.python-version` and `pyproject.toml` (`requires-python`) SHOULD be set to
    prevent drift.
- uv: **0.9.18**
  - Enforcement hooks: CI SHOULD run `uv --version` and MUST fail if it differs from the pinned
    value.

| Dependency         | Pinned version | Used by                    | Notes                         |
| ------------------ | -------------: | -------------------------- | ----------------------------- |
| pytest             |          9.0.2 | Unit + integration tests   | CI gate                       |
| pytest-regressions |          2.9.1 | Golden/regression fixtures | CI gate for "golden outputs"  |
| ruff               |        0.14.11 | Lint + format              | Lint + format gate            |
| pyright            |        1.1.408 | Type checking              | type-check gate               |
| mdformat           |          1.0.0 | MD Format checking         | MD Format gate                |
| pre-commit         |          4.5.1 | Local + CI hook runner     | CI SHOULD enforce hook parity |

## Version drift policy (normative)

1. CI MUST fail closed if any dependency version differs from the pins above for an enabled stage.
1. Any dependency bump MUST be accompanied by:

- updated pins in this file, and
- reviewed updates to "golden" fixture outputs where behavior changes are observable.

## Compatibility notes (v0.1 guidance)

- **Collector upgrades:** treat as potentially behavior-changing for receivers and processors;
  re-run Windows Event Log raw-mode conformance fixtures and checkpoint/rotation fixtures.
- **pySigma upgrades:** treat as behavior-changing for rule parsing/modifier semantics; re-run rule
  compilation fixtures and "golden equivalence" backend gates.
- **pySigma pipeline upgrades:** treat as behavior-changing for logsource routing assumptions and
  field alias behavior; re-run rule compilation fixtures and "golden equivalence" backend gates.
- **PCRE2 upgrades:** treat as behavior-changing for regex semantics and match limits; re-run
  evaluator fixtures, especially regex-heavy Sigma and correlation fixtures.
- **osquery upgrades:** treat as potentially behavior-changing for table schemas and event backends;
  re-run mapping fixtures for any affected event tables and update "known limitations" documentation
  as needed.
- **Toolchain upgrades (pytest, ruff, pyright, pre-commit):** treat as potentially behavior-changing
  for CI gating and fixture stability; re-run formatting, typecheck, and "golden outputs" gates and
  review diffs before blessing updates.
