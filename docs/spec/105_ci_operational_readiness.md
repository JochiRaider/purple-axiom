---
title: CI and Operational Readiness
description: Stitches existing v0.1 CI gates, publish gates, and health signals into a single normative CI pipeline contract.
status: draft
category: spec
tags: [ci, devops, secdevops, sre, operability, gates]
related:
  - 000_charter.md
  - 070_scoring_metrics.md
  - 100_test_strategy_ci.md
  - 110_operability.md
  - 120_config_reference.md
  - 025_data_contracts.md
  - 080_reporting.md
  - 090_security_safety.md
  - ADR-0003-redaction-policy.md
  - ADR-0004-deployment-architecture-and-inter-component-communication.md
  - ADR-0005-stage-outcomes-and-failure-classification.md
  - ADR-0007-state-machines.md
---

# CI + Operational Readiness

## Overview

This document defines the normative CI pipeline contract for Purple Axiom v0.1 implementations by
stitching together already-specified gates and evidence surfaces into a single, deterministic CI
verdict model.

This spec MUST NOT introduce new pipeline stages, new artifact classes, or new contract schemas. It
only consolidates and operationalizes existing v0.1 requirements across:

- CI gates (100_test_strategy_ci.md)
- Publish-gate and artifact contracts (025_data_contracts.md)
- Run health and operational safeguards (110_operability.md)
- CI-facing reporting and exit code semantics (080_reporting.md)
- Failure classification (ADR-0005)
- Lifecycle state machines (ADR-0007)

## Scope

In-scope (v0.1):

- A deterministic CI verdict derived from contracted artifacts and existing exit-code semantics.
- A single “pipeline contract” view of the already-required CI gates.
- Explicit mapping from gates to evidence surfaces (schemas, reports, health files, and thresholds).

Out-of-scope:

- Continuous deployment to production environments.
- Adding new stages, new artifact directories, or new schemas beyond v0.1 docs.
- Mandating a specific CI vendor or workflow engine.

## Normative sources

All MUST / MUST NOT statements in this spec are restatements or compositions of requirements already
present in v0.1 documents listed in the frontmatter.

If a conflict is discovered between sources, the implementation MUST follow the more specific
contract document for the artifact in question (e.g., data contracts for run bundle paths) and MUST
raise an issue to reconcile the discrepancy.

## Definitions

- Run bundle: The contracted run directory rooted at `runs/<run_id>/`.
- Gate: A pass/fail rule evaluated by CI over contracted artifacts and v0.1 exit-code semantics.
- Fail-closed gate: A gate where any failure MUST yield a `failed` run status.
- Threshold gate: A gate where violations degrade the run status to `partial` (or `failed` when the
  underlying contract requires hard failure) while keeping the run mechanically reportable.
- Run status: The canonical `(success | partial | failed)` value recorded in
  `runs/<run_id>/manifest.json.status` (derived from stage outcomes per ADR-0005).
- CI verdict: The CI job’s final recommendation `(success | partial | failed)` plus an exit-code
  mapping `(0|10|20)` for the CI job step that enforces this contract.
- Reportable: A run with mechanically usable artifacts and the required reporting outputs for its
  enabled feature set (see reporting “required artifacts” and data contracts publish-gate
  requirements).

## CI contract

### CI decision surface

CI MUST compute a single verdict for each `run_id` using only contracted artifacts and the exit-code
mapping defined by v0.1.

This section is a consolidation of existing requirements: reporting defines the CI-facing status
recommendation, data contracts define manifest status derivation, and operability/ADR-0005 define
exit-code and outcome semantics.

Unless otherwise stated, paths in this document are workspace-rooted under `runs/<run_id>/` (for
example, `runs/<run_id>/manifest.json`). CI implementations MAY `cd` into `runs/<run_id>/` and treat
the remaining paths as run-relative so long as the resolved paths are equivalent.

#### Evidence precedence

For a given `run_id`, CI MUST determine the verdict source in the following order:

1. If `runs/<run_id>/report/thresholds.json` exists and validates against its schema, CI MUST use
   `runs/<run_id>/report/thresholds.json.status_recommendation`.
1. Else, if `runs/<run_id>/manifest.json` exists and validates against its schema, CI MUST use
   `runs/<run_id>/manifest.json.status`.
1. Else, CI MUST derive status from the orchestrator process exit code:
   - `0 -> success`
   - `10 -> partial`
   - `20 -> failed`
   - Any other exit code MUST be treated as `failed` and MUST be recorded as a pipeline contract
     violation.

When either `runs/<run_id>/report/thresholds.json` or `runs/<run_id>/report/report.json` is present,
CI MUST require the other report artifact to also be present and schema-valid. Any report-pair
mismatch MUST be treated as a fail-closed pipeline contract violation.

If none of the evidence artifacts exist (for example, failure before run directory creation), CI
MUST treat the run as `failed`.

#### Consistency checks (fail closed)

When the following artifacts are present, CI MUST fail closed if their status signals disagree:

- When `runs/<run_id>/report/thresholds.json` and `runs/<run_id>/report/report.json` are present,
  `runs/<run_id>/report/thresholds.json.status_recommendation` MUST equal
  `runs/<run_id>/report/report.json.status`.
- `runs/<run_id>/manifest.json.status` MUST equal `runs/<run_id>/logs/health.json.status` when
  health files are enabled and `runs/<run_id>/logs/health.json` is present.
- The CI job step that enforces this contract MUST exit with `(0|10|20)` matching the derived
  verdict.
- When the orchestrator process exit code is available to CI as a captured signal (for example, from
  a prior job step), it MUST match the derived verdict. Any mismatch MUST be treated as a
  fail-closed pipeline contract violation.

CI MUST also fail closed if any required evidence artifact is present but fails schema validation.

#### Allowed absence of outcomes

v0.1 allows a narrow exception where stage outcomes cannot be recorded due to operational failures
(for example, `lock_acquisition_failed` or `storage_io_error`). In this case,
`runs/<run_id>/manifest.json` and/or `runs/<run_id>/logs/health.json` MAY be missing.

When this exception occurs, CI MUST treat the run as `failed` using the exit code and MUST surface
the absence of outcomes as an operational error requiring reconciliation.

### Required gate catalog

CI MUST enforce the required gate categories already defined by the test strategy:

| Gate category             | Required?                       | Primary evidence                                                     | Fail mode                                                                                                      |
| ------------------------- | ------------------------------- | -------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| Schema validation         | REQUIRED                        | schema validation output / errors                                    | fail-closed                                                                                                    |
| Version conformance       | REQUIRED                        | supported version pins + artifacts                                   | fail-closed                                                                                                    |
| Determinism gates         | REQUIRED when enabled           | DuckDB conformance report + determinism fixtures                     | fail-closed for `result_hash_mismatch`; warn-only for `plan_hash_mismatch` unless explicitly enabled as a gate |
| Artifact validation       | REQUIRED                        | run bundle paths + contract reports                                  | fail-closed                                                                                                    |
| Cross-artifact invariants | REQUIRED                        | manifest/run_id joins + referential checks                           | fail-closed                                                                                                    |
| Operational readiness     | REQUIRED when enabled (default) | `logs/health.json`, `logs/telemetry_validation.json`, `logs/run.log` | fail-closed for required canaries; threshold-based (partial allowed) for configured budgets                    |
| Regression gates          | REQUIRED when enabled           | baseline compare outputs + thresholds                                | threshold-based (partial allowed)                                                                              |

This table is a consolidation view; details remain in the underlying specs.

### Publish-gate enforcement

CI MUST verify publish-gate requirements by checking that:

- Stage outputs are written to staging then atomically published into contracted run bundle paths.
- Contract validation outputs (when emitted) are present under:
  - `runs/<run_id>/logs/contract_validation/<stage_id>.json` (per stage)
- Deterministic artifact path rules are enforced (no timestamps in contracted filenames).

CI SHOULD perform a post-run publish-gate sanity check by asserting that
`runs/<run_id>/.staging/<stage_id>/` does not remain populated after orchestrator completion. Any
leftover staged output indicates incomplete atomic publish and MUST be treated as a fail-closed
contract failure.

Note: v0.1 contract documents specify per-stage contract validation logs at
`runs/<run_id>/logs/contract_validation/<stage_id>.json`. If any CI fixtures reference a different
path, that discrepancy MUST be reconciled in the source documents; CI implementations MUST follow
the artifact contract path.

### Operational readiness evidence surfaces

Where enabled by v0.1 specs/config:

- When `operability.health.emit_health_files=true` (default), `runs/<run_id>/logs/health.json` MUST
  exist and conform to the health schema.
- When telemetry validation is enabled for the run, `runs/<run_id>/logs/telemetry_validation.json`
  MUST exist and conform to the telemetry validation schema.

When `operability.health.emit_health_files=false`, `runs/<run_id>/logs/health.json` MAY be absent.
In this mode, CI MUST NOT fail solely due to the missing health file, but MUST still require
`runs/<run_id>/manifest.json` to validate and to provide the canonical `manifest.status`.

CI MUST treat missing required operational readiness files as a contract failure (fail closed).

Additionally, CI SHOULD retain and/or validate the required operational log surface:

- `runs/<run_id>/logs/run.log` is REQUIRED (human-readable, stable diagnostics).
- `runs/<run_id>/logs/warnings.jsonl` is OPTIONAL (structured warnings).

When `runs/<run_id>/logs/health.json` is present, CI SHOULD validate ADR-0005 conformance properties
that are critical to determinism:

- stable ordering of stages/substages, and
- `reason_code` tokens drawn from the known registry for the relevant stage context.

### Artifact retention (CI publication)

CI SHOULD retain (as build artifacts) the minimum evidence surface required for deterministic
debugging of gate failures:

- `runs/<run_id>/manifest.json`
- `runs/<run_id>/logs/run.log`
- `runs/<run_id>/logs/warnings.jsonl` (when present)
- `runs/<run_id>/report/thresholds.json` (when present)
- `runs/<run_id>/report/report.json` (when present)
- `runs/<run_id>/report/report.html` (when present)
- `runs/<run_id>/logs/health.json` (when present / when enabled)
- `runs/<run_id>/logs/telemetry_validation.json` (when present / when enabled)
- `runs/<run_id>/logs/cache_provenance.json` (when present)
- `runs/<run_id>/logs/contract_validation/` (when present)
- `artifacts/duckdb_conformance/**/report.json` (when determinism gate is enabled)

Security posture for CI artifacts:

- CI artifact publication MUST obey the security/redaction posture. Resolved secrets MUST NOT be
  written into CI artifacts.
- When unredacted evidence quarantine is used, `runs/<run_id>/unredacted/` (or the configured
  `security.redaction.unredacted_dir`) MUST be excluded from default CI artifact publication unless
  an operator explicitly intends to retain unredacted evidence.

## State machine representation

This state machine is an illustrative CI orchestration view only. It does not define or constrain
runtime stage behavior; conformance is defined solely by the artifact contracts and status semantics
in the preceding sections.

### State machine: CI gate lifecycle (v0.1)

States (closed set):

- `pending`
- `executing`
- `validating`
- `publishing`
- `completed_success`
- `completed_partial`
- `completed_failed`

Transitions:

- `pending -> executing`: CI job starts.
- `executing -> validating`: orchestrator exits and `runs/<run_id>/manifest.json` exists.
- `validating -> publishing`: post-run gate evaluation completes.
- `publishing -> completed_*`: artifacts retained/published and verdict recorded.
- `executing -> completed_failed`: orchestrator exits without producing a conformant manifest/health
  surface due to an allowed outcome-recording exception; CI fails the run based on exit code.

Terminal mapping:

- `completed_success` iff verdict is `success` and exit code is `0`.
- `completed_partial` iff verdict is `partial` and exit code is `10`.
- `completed_failed` iff verdict is `failed` and exit code is `20`.

## Verification hooks

A CI pipeline is conformant iff:

- Required gate categories are executed and enforced with the specified fail modes.
- CI verdict is derived deterministically from the decision surface.
- Exit code mapping matches the verdict mapping.
- Missing required artifacts are treated as fail-closed contract failures.
- Status coupling checks are enforced when artifacts are present (thresholds \<-> report \<->
  manifest \<-> health \<-> exit code).
- ADR-0005 CI conformance checks are enforced for stage outcome ordering and reason code validity.
- CI artifact publication obeys the security/redaction posture (no secrets; unredacted quarantine
  excluded by default).

## References

- [Test strategy and CI](100_test_strategy_ci.md)
- [Data contracts](025_data_contracts.md)
- [Operability](110_operability.md)
- [Reporting](080_reporting.md)
- [Security and safety](090_security_safety.md)
- [ADR-0004: Deployment architecture and inter-component communication](../adr/ADR-0004-deployment-architecture-and-inter-component-communication.md)
- [ADR-0005: Stage outcomes and failure classification](../adr/ADR-0005-stage-outcomes-and-failure-classification.md)
- [ADR-0007: State machines for lifecycle semantics](../adr/ADR-0007-state-machines.md)

## Changelog

- v0.1 (draft): Initial stitching spec (no new gates; consolidation only).
