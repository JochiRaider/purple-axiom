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
- `Status recommendation`: The CI-facing status computed by the reporting stage; recorded in
  `runs/<run_id>/report/thresholds.json.status_recommendation` (authoritative) and mirrored in
  `runs/<run_id>/report/report.json.status` for reportable runs.
- Pipeline contract violation: A CI-detected nonconformance to required artifact presence, schema
  validity, or cross-artifact coupling (including unexpected exit codes). Pipeline contract
  violations are fail-closed and MUST force the CI verdict to `failed` (CI exit code `20`) even when
  other status signals indicate `success` or `partial`.
- CI verdict: The CI job’s final recommendation `(success | partial | failed)` plus an exit-code
  mapping `(0|10|20)` for the CI job step that enforces this contract.
- Reportable: A run with mechanically usable artifacts and the required reporting outputs for its
  enabled feature set (see reporting “required artifacts / required reporting outputs” and data
  contracts publish-gate requirements).

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

For a given `run_id`, CI MUST determine the verdict source in the following order. Any fail-closed
pipeline contract violation (for example, missing/invalid required evidence or mismatched coupled
signals) MUST override the selected verdict source and force the CI verdict to `failed`.

1. If `runs/<run_id>/report/thresholds.json` exists and validates against its schema, CI MUST use
   `runs/<run_id>/report/thresholds.json.status_recommendation`.
1. Else, if `runs/<run_id>/manifest.json` exists and validates against its schema, CI MUST use
   `runs/<run_id>/manifest.json.status`.
1. Else, if the run bundle root `runs/<run_id>/` exists, CI MUST derive status from the orchestrator
   process exit code captured by CI:
   - `0 -> success`
   - `10 -> partial`
   - `20 -> failed`
   - Any other exit code MUST be treated as `failed` and MUST be recorded as a pipeline contract
     violation.
   - If the orchestrator process exit code is not available to CI in this scenario, CI MUST treat
     the run as `failed` and MUST record a pipeline contract violation.

Reporting output coupling (fail closed):

- If any of the following report artifacts are present:
  - `runs/<run_id>/report/thresholds.json`
  - `runs/<run_id>/report/report.json`
  - `runs/<run_id>/report/run_timeline.md` then CI MUST require all three to be present.
- `runs/<run_id>/report/thresholds.json` and `runs/<run_id>/report/report.json` MUST be
  schema-valid.
- Any mismatch MUST be treated as a fail-closed pipeline contract violation.

If the run bundle root `runs/<run_id>/` does not exist (for example, failure before run directory
creation), CI MUST treat the run as `failed`. When the orchestrator process exit code is available
to CI as a captured signal in this case, it MUST be `20`; any other exit code MUST be treated as a
pipeline contract violation and MUST fail closed.

#### Consistency checks (fail closed)

When the following artifacts are present, CI MUST fail closed if their status signals disagree:

- When `runs/<run_id>/report/thresholds.json` and `runs/<run_id>/report/report.json` are present,
  `runs/<run_id>/report/thresholds.json.status_recommendation` MUST equal
  `runs/<run_id>/report/report.json.status`.
- When `runs/<run_id>/report/run_timeline.md` is present, it MUST be timeline-conformant per
  `080_reporting.md` (including UTF-8 encoding, LF newlines, required columns, and stable ordering).
- When `runs/<run_id>/manifest.json` and `runs/<run_id>/report/report.json` are present,
  `runs/<run_id>/manifest.json.run_id` MUST equal `runs/<run_id>/report/report.json.run_id`.
- `runs/<run_id>/report/report.json.status_reasons[]` MUST contain unique reason codes and MUST be
  emitted sorted ascending (UTF-8 byte order, no locale) when `runs/<run_id>/report/report.json` is
  present.
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

When this exception occurs, CI MUST treat the run as `failed`. The captured orchestrator exit code
MUST be `20`; any other exit code MUST be treated as a pipeline contract violation and MUST fail
closed. CI MUST surface the absence of outcomes as an operational error requiring reconciliation.

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

- `runs/<run_id>/logs/health.json` MUST exist and conform to schema when
  `operability.health.emit_health_files=true` (default).
- `runs/<run_id>/logs/telemetry_validation.json` MUST exist and conform when telemetry validation is
  enabled (`telemetry.emit_validation=true` or config-specific).
- `runs/<run_id>/logs/run.log` MUST exist (human-readable execution log; primary surface for
  warn-only diagnostics).
- `runs/<run_id>/logs/warnings.jsonl` is OPTIONAL; it may include warn-only entries for non-gating
  anomalies.

When `operability.health.emit_health_files=false`, `logs/health.json` MAY be absent. In this mode,
CI MUST NOT fail solely due to missing health file, but MUST still require `manifest.json` to
validate and to provide canonical `manifest.status`, unless the
[Allowed absence of outcomes](#allowed-absence-of-outcomes) exception applies.

CI MUST treat missing operational readiness files that are REQUIRED for the run’s enabled feature
set as contract failure (fail closed).

When `logs/health.json` is present, CI MUST validate ADR-0005 conformance properties that are
critical to determinism (violations are fail-closed):

- Stage and substage arrays are emitted in stable order.
- `reason_code` tokens are drawn from the known registry for the relevant stage context.

### Artifact retention (CI publication)

CI SHOULD retain (as build artifacts) the minimum evidence surface required for deterministic
debugging of gate failures:

- `runs/<run_id>/manifest.json`
- `runs/<run_id>/logs/run.log`
- `runs/<run_id>/logs/warnings.jsonl` (when present)
- `runs/<run_id>/report/thresholds.json` (when present)
- `runs/<run_id>/report/report.json` (when present)
- `runs/<run_id>/report/run_timeline.md` (when present)
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

Lifecycle authority references (per ADR-0007 representational requirements):

- Verdict derivation: [CI decision surface](#ci-decision-surface) and ADR-0005 exit-code semantics.
- Reporting coupling: `080_reporting.md` (thresholds status recommendation ↔ report status).
- Health/stage outcomes: `025_data_contracts.md` and ADR-0005 (`logs/health.json` semantics).
- Gate inventory: [Required gate catalog](#required-gate-catalog).

### State machine: CI gate lifecycle (v0.1)

States (closed set):

- `pending`
- `executing`
- `validating`
- `publishing`
- `completed_success`
- `completed_partial`
- `completed_failed`

Events (closed set):

- `ci_job_started`
- `orchestrator_exited`
- `decision_surface_evaluated`
- `artifacts_published`

Transitions:

- `pending -> executing`: CI job starts (`ci_job_started`).
- `executing -> validating`: orchestrator exits (`orchestrator_exited`). CI begins decision-surface
  evaluation and gate enforcement.
- `validating -> publishing`: post-run gate evaluation completes (`decision_surface_evaluated`).
- `publishing -> completed_*`: artifacts retained/published and verdict recorded
  (`artifacts_published`).
- `executing -> completed_failed`: orchestrator exits (`orchestrator_exited`) without producing a
  conformant manifest/health surface due to an allowed outcome-recording exception; CI fails the run
  based on exit code.

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
- Reporting output coupling is enforced when reporting artifacts are present (`report/report.json`,
  `report/thresholds.json`, and `report/run_timeline.md`).
- Status coupling checks are enforced when artifacts/signals are present
  (`thresholds.status_recommendation` \<-> `report.status`; `manifest.status` \<-> `health.status`;
  captured orchestrator exit code \<-> derived verdict).
- ADR-0005 CI conformance checks are enforced for stage outcome ordering and reason code validity.
- CI artifact publication obeys the security/redaction posture (no secrets; unredacted quarantine
  excluded by default).

### Conformance fixture matrix (v0.1)

This matrix defines minimal file-tree fixtures (present/missing/invalid) and the expected CI exit
code. Fixture IDs intentionally align with the required CI fixtures in `100_test_strategy_ci.md`.
Expected exit codes follow the ADR-0005 `(0|10|20)` mapping.

Legend:

- `✓` = present and schema-valid
- `✗` = missing
- `!` = present but schema-invalid
- `≠` = present, schema-valid, but violates a semantic invariant

Unless stated otherwise, fixtures assume `operability.health.emit_health_files=true` (so
`logs/health.json` is required when `runs/<run_id>/` exists).

| Fixture ID                                        | Gate / rule exercised                                              | Minimal fixture (paths relative to `runs/<run_id>/` unless noted)                                                                                                                                                                                                      | Expected CI verdict | Expected CI exit code |
| ------------------------------------------------- | ------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------- | --------------------- |
| `happy_path_success`                              | Decision surface + required couplings                              | `manifest.json` ✓ (`status=success`)<br>`logs/health.json` ✓ (`status=success`)<br>`report/thresholds.json` ✓ (`status_recommendation=success`)<br>`report/report.json` ✓ (`status=success`)<br>`report/run_timeline.md` ✓<br>`logs/run.log` ✓                         | `success`           | `0`                   |
| `happy_path_partial_threshold_degrade`            | Threshold gate degrades run status                                 | `manifest.json` ✓ (`status=partial`)<br>`logs/health.json` ✓ (`status=partial`)<br>`report/thresholds.json` ✓ (`status_recommendation=partial`)<br>`report/report.json` ✓ (`status=partial`)<br>`report/run_timeline.md` ✓<br>`logs/run.log` ✓                         | `partial`           | `10`                  |
| `happy_path_failed_required_artifact_missing`     | Artifact validation (required artifact absent)                     | `manifest.json` ✓ (`status=failed`)<br>`logs/health.json` ✓ (`status=failed`)<br>`report/thresholds.json` ✓ (`status_recommendation=failed`)<br>`report/report.json` ✓ (`status=failed`)<br>`report/run_timeline.md` ✓<br>`logs/run.log` ✓<br>`scoring/summary.json` ✗ | `failed`            | `20`                  |
| `schema_invalid_health`                           | Schema validation (fail closed)                                    | `manifest.json` ✓ (`status=success`)<br>`logs/health.json` !<br>`logs/run.log` ✓                                                                                                                                                                                       | `failed`            | `20`                  |
| `schema_invalid_thresholds`                       | Schema validation (fail closed)                                    | `report/thresholds.json` !<br>`report/report.json` ✓<br>`report/run_timeline.md` ✓<br>`logs/run.log` ✓                                                                                                                                                                 | `failed`            | `20`                  |
| `status_mismatch_report_thresholds`               | Status coupling (`thresholds` ↔ `report`)                          | `report/thresholds.json` ✓ (`status_recommendation=success`)<br>`report/report.json` ✓ (`status=partial`)<br>`report/run_timeline.md` ✓<br>`logs/run.log` ✓                                                                                                            | `failed`            | `20`                  |
| `report_timeline_missing_when_required`           | Reporting output coupling (timeline required)                      | `report/thresholds.json` ✓ (`status_recommendation=success`)<br>`report/report.json` ✓ (`status=success`)<br>`report/run_timeline.md` ✗<br>`logs/run.log` ✓                                                                                                            | `failed`            | `20`                  |
| `orchestrator_exit_code_unknown`                  | Exit-code mapping (unknown => fail closed)                         | (no run bundle required)<br>Captured orchestrator exit code: `2`                                                                                                                                                                                                       | `failed`            | `20`                  |
| `artifact_path_timestamped_filename_blocked`      | Deterministic artifact path enforcement                            | `runner/actions/action_20260101T123000Z.json` ✓ (timestamped filename in contracted dir)<br>`logs/contract_validation/runner.json` ✓ (includes stable error code `timestamped_filename_disallowed`)<br>`logs/run.log` ✓                                                | `failed`            | `20`                  |
| `publish_gate_incomplete_staging_dir`             | Publish-gate enforcement                                           | `.staging/<stage_id>/` ✓ (left behind after run completion)<br>`logs/run.log` ✓                                                                                                                                                                                        | `failed`            | `20`                  |
| `determinism_report_result_hash_mismatch_fail`    | Determinism gates (fail closed)                                    | `artifacts/duckdb_conformance/<case>/report.json` ✓ (`result_hash_mismatch` present)                                                                                                                                                                                   | `failed`            | `20`                  |
| `determinism_report_plan_hash_mismatch_warn_only` | Determinism gates (warn-only)                                      | Same as `happy_path_success` plus:<br>`artifacts/duckdb_conformance/<case>/report.json` ✓ (`plan_hash_mismatch` present)                                                                                                                                               | `success`           | `0`                   |
| `version_pins_mismatch_fail`                      | Version conformance (fail closed)                                  | `manifest.json` ✓ but `manifest.versions.*` ≠ supported pins (per `SUPPORTED_VERSIONS.md`)<br>`logs/run.log` ✓                                                                                                                                                         | `failed`            | `20`                  |
| `cross_artifact_run_id_mismatch_fail`             | Cross-artifact invariants (fail closed)                            | `manifest.json` ✓ (`run_id=A`)<br>`report/thresholds.json` ✓ (`status_recommendation=success`)<br>`report/report.json` ✓ (`run_id=B`, `status=success`) ≠<br>`report/run_timeline.md` ✓<br>`logs/run.log` ✓                                                            | `failed`            | `20`                  |
| `telemetry_validation_missing_when_enabled`       | Operational readiness (telemetry validation required when enabled) | `manifest.json` ✓ (`status=success`)<br>`logs/health.json` ✓ (`status=success`)<br>`logs/telemetry_validation.json` ✗ (telemetry validation enabled)<br>`logs/run.log` ✓                                                                                               | `failed`            | `20`                  |
| `run_log_missing`                                 | Operational readiness (required logging surface)                   | `manifest.json` ✓<br>`logs/run.log` ✗                                                                                                                                                                                                                                  | `failed`            | `20`                  |
| `report_status_reasons_unsorted_or_duplicate`     | Reporting determinism (fail closed)                                | `report/report.json` ✓ but `status_reasons[]` not sorted ascending or contains duplicates<br>`report/thresholds.json` ✓<br>`report/run_timeline.md` ✓<br>`logs/run.log` ✓                                                                                              | `failed`            | `20`                  |

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
