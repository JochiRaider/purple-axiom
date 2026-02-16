---
title: 'ADR-0005: Stage outcomes and failure classification'
description: Defines deterministic stage outcomes, reason codes, and failure taxonomy for v0.1 runs.
status: draft
category: adr
---

# ADR-0005: Stage outcomes and failure classification

## Status

Draft

## Context

Purple Axiom v0.1 requires deterministic, machine-readable failure classification to support:

- operator triage (which stage failed and why)
- CI gating (fail closed vs warn and skip)
- run status derivation (`success | partial | failed`)
- health file emission (`runs/<run_id>/logs/health.json`)

The system already specifies:

- a stable, staged pipeline (lab provider -> runner -> telemetry -> normalization -> validation ->
  detection -> scoring -> reporting -> signing)
- a local-first run bundle (`runs/<run_id>/...`) and manifest-driven reproducibility
- operability requirements for `logs/health.json`, run limits, and exit codes

This ADR defines the normative behavior for stage outcomes, reason codes, and the failure taxonomy
that the orchestrator and all stage implementations MUST follow.

## Decision

1. **Every enabled stage MUST produce a deterministic stage outcome** (or a deterministic fatal exit
   when outcome recording is impossible due to lock or storage I/O constraints).
1. **Stage outcomes are the sole inputs** to:
   - `manifest.status` derivation (`success | partial | failed`)
   - `logs/health.json` stage list
   - deterministic exit code selection (`0 | 10 | 20`)
1. **Reason codes are stable tokens** (`lower_snake_case`) drawn from a normative catalog defined in
   this ADR.
1. **Warnings do not belong in `logs/health.json`**. Warning-only information is written to
   `logs/warnings.jsonl` (optional) and/or `logs/run.log` (required).

## Definitions

### Stage identifiers

Stages are identified by a stable `stage_id` string. v0.1 defines the following stage identifiers:

- `lab_provider`
- `runner`
- `telemetry`
- `normalization`
- `validation`
- `detection`
- `scoring`
- `reporting`
- `signing` (only when enabled)

Substages MAY be expressed as dotted identifiers (for example, `lab_provider.connectivity`,
`telemetry.windows_eventlog.raw_mode`, `validation.run_limits`) and are additive. Substages MUST NOT
change the semantics of the parent stage outcome.

Substage outcomes, when emitted, are treated as additional stage outcomes for run status derivation
(see "Manifest status derivation"). Substage outcomes MUST NOT be interpreted as changing the
success criteria of the parent stage; they provide additional, independently gateable outcomes.

### Stage outcome

A stage outcome is a tuple emitted for each enabled pipeline stage (and for any defined substages
that the implementation chooses to record):

- `stage` (string): stable stage identifier
- `status` (string): `success | failed | skipped`
- `fail_mode` (string): `fail_closed | warn_and_skip`
- `reason_code` (string, optional): stable token explaining failure or skip

Implementations MAY include additional fields in the persisted representation (for example
timestamps, counters, file pointers), but:

- consumers MUST derive run status only from the tuple above
- additional fields MUST NOT affect determinism-sensitive computations (for example event identity)

### Failure severity

This ADR uses the following severity mapping:

- **FATAL (fail-closed):** `status="failed"` and `fail_mode="fail_closed"`
- **NON-FATAL (degraded):** `status="failed"` and `fail_mode="warn_and_skip"`
- **SKIPPED:** `status="skipped"` (always requires a `reason_code`)

### Outcome recording requirement

The orchestrator MUST record the stage outcome in:

- `runs/<run_id>/manifest.json`, and
- when enabled, `runs/<run_id>/logs/health.json`

Single-writer invariant (normative):

- `manifest.json` and `logs/health.json` are run-level index artifacts. The orchestrator (the
  run-lock holder) MUST be the only component that persists outcomes into these files.
- Stage implementations (including per-stage CLI commands) MUST NOT open, patch, or rewrite these
  files directly. They MUST surface outcome tuples to the orchestrator (for example by returning an
  outcome object or emitting via an injected `OutcomeSink` owned by the orchestrator).
- Outcome writes to `manifest.json` and `logs/health.json` MUST be atomic replace operations (write
  to a temp file in the same directory, then atomic rename), so the files are always readable JSON.

**Exception:** Outcome recording MUST NOT be attempted when doing so would violate locking
guarantees or is impossible due to storage I/O failure.

In those exceptional cases:

- the orchestrator MUST emit the failure to stderr
- the orchestrator MUST exit with the correct process exit code (see "Exit codes")

Rationale: two fatal conditions can prevent safe outcome writes:

- `storage_io_error` (cannot write reliably)
- `lock_acquisition_failed` (cannot safely mutate the run bundle without the lock)

### Warning-only entries

Warning-only entries (non-fatal degradations, informational signals) MUST be written to:

- `runs/<run_id>/logs/warnings.jsonl` (optional structured log), and/or
- `runs/<run_id>/logs/run.log` (required text log)

`runs/<run_id>/logs/health.json` MUST contain only stage outcomes.

Per-gap classification (for example `measurement_layer` and deterministic evidence pointers used in
reports) is a reporting/scoring concern. It MUST be emitted in stage output artifacts (for example
under `runs/<run_id>/report/**`) and MUST NOT change `logs/health.json` semantics or structure.

## Determinism requirements

### Stable ordering

`logs/health.json.stages[]` and any stage list in `manifest.json` MUST be emitted in deterministic
order.

Default ordering MUST follow the canonical pipeline order:

1. `lab_provider`
1. `runner`
1. `telemetry`
1. `normalization`
1. `validation`
1. `detection`
1. `scoring`
1. `reporting`
1. `signing`

Substages, when present, MUST be ordered immediately after their parent stage, sorted
lexicographically by full `stage` string.

### Stable reason codes

- This ADR governs stage/substage outcome `reason_code` values only (those emitted in
  `manifest.stage_outcomes[]` and `logs/health.json`).

- Other contract-backed artifacts may also use a field named `reason_code`; those vocabularies are
  scoped to their owning schema and are not governed by this ADR.

- `reason_code` MUST be ASCII `lower_snake_case`.

- `reason_code` MUST be stable across runs and versions within v0.1.

- `reason_code` MUST be selected from the normative catalog in this ADR for the relevant
  `(stage, reason_code)` pair.

### CI conformance (normative)

CI MUST validate deterministic outcome emission:

- CI MUST reject `logs/health.json` and `manifest.json` stage lists that violate "Stable ordering".
- CI MUST reject any emitted `(stage, reason_code)` pair that is not present in the normative
  catalog in this ADR.

## Global failure rules

### Downstream stages on upstream failure

If a stage fails with `fail_mode="fail_closed"`:

- the orchestrator MUST stop executing subsequent stages
- all remaining enabled stages MUST be recorded as `status="skipped"`,
  `fail_mode=<their configured value>`, `reason_code="blocked_by_upstream_failure"`

If a stage fails with `fail_mode="warn_and_skip"`:

- the orchestrator MAY continue executing subsequent stages
- subsequent stages MUST use their configured `fail_mode` and MUST not silently upgrade or downgrade
  severity

### Publish gate on fatal failure

If a stage fails with `fail_mode="fail_closed"`:

- the stage MUST NOT publish its final output directory (no partial promotion)
- the orchestrator SHOULD still attempt to write final `manifest.json` and `logs/health.json` and
  record downstream skips

**Exception:** When prevented by lock or I/O constraints (see "Outcome recording requirement").

## Exit codes

The orchestrator MUST use deterministic exit codes:

- `0`: run status `success`
- `10`: run status `partial`
- `20`: run status `failed`

## Manifest status derivation (normative)

`manifest.status` MUST be derived from stage outcomes:

- `failed`: any enabled stage has `status="failed"` and `fail_mode="fail_closed"`
- `partial`: any enabled stage has `status="failed"` and `fail_mode="warn_and_skip"`
- `success`: all enabled stages have `status="success"` (and any disabled stages are absent)

Quality gates (for example Tier 1 coverage thresholds) MUST be represented as a `warn_and_skip`
stage failure (or substage failure) so that `manifest.status` derivation remains purely
outcome-driven.

## Stage outcome registry (implementation guidance)

Implementations SHOULD maintain a registry mapping `(stage, reason_code)` to default severity and
policy overrides:

```text
registry[(stage_id, reason_code)] -> {
  default_fail_mode: "fail_closed" | "warn_and_skip",
  override_rules: [...]
}
```

Override rules MUST be deterministic and MUST reference only explicit configuration inputs (for
example `normalization.strict_mode`, `reporting.emit_html`).

## Failure taxonomy (normative reason codes)

This section defines the authoritative stage outcome reason codes for v0.1. Codes not listed here
MUST NOT be emitted as a stage outcome `reason_code` in `logs/health.json` (or
`manifest.stage_outcomes[]`) without a spec update.

### Cross-cutting (applies to any stage)

These reason codes MAY be used for any stage.

| Reason code                          | Severity | Description                                                                                                                                                                        |
| ------------------------------------ | -------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `redaction_policy_error`             | FATAL    | Redaction engine failed or post-check failed; artifacts cannot be safely persisted.                                                                                                |
| `config_schema_invalid`              | FATAL    | A required config artifact is schema-invalid (for example `inputs/range.yaml`, `manifest.json`, `inputs/scenario.yaml` or `inputs/plan_draft.yaml` when plan building is enabled). |
| `input_missing`                      | FATAL    | Required upstream input artifact missing or unreadable.                                                                                                                            |
| `integration_credentials_missing`    | FATAL    | Required integration credential reference missing, empty, or cannot be resolved by the configured secret provider.                                                                 |
| `integration_credentials_invalid`    | FATAL    | Integration credential resolved but failed integration validation/authentication.                                                                                                  |
| `integration_credentials_leaked`     | FATAL    | Resolved integration credential value detected in persisted output (artifacts or logs); safety violation.                                                                          |
| `lock_acquisition_failed`            | FATAL    | Exclusive lock could not be acquired.                                                                                                                                              |
| `storage_io_error`                   | FATAL    | Storage error prevents atomic writes (for example ENOSPC or EIO).                                                                                                                  |
| `blocked_by_upstream_failure`        | SKIPPED  | Stage did not run because an upstream stage failed fail-closed.                                                                                                                    |
| `threat_intel_pack_not_found`        | FATAL    | Threat intelligence pack requested but not found (resolved directory missing and/or required files absent).                                                                        |
| `threat_intel_pack_ambiguous`        | FATAL    | Multiple sources match the same `(threat_intel_pack_id, threat_intel_pack_version)` but differ in content; selection is ambiguous.                                                 |
| `threat_intel_pack_invalid`          | FATAL    | Threat intelligence pack failed validation (schema invalid, hash mismatch, or indicators JSONL parse/validation failure).                                                          |
| `threat_intel_snapshot_inconsistent` | FATAL    | Existing `inputs/threat_intel/` snapshot does not match resolved pins/hashes and would break reproducibility.                                                                      |

Precedence (normative):

- If the detected secret is a resolved integration credential value, implementations MUST emit
  `reason_code=integration_credentials_leaked` (more specific) rather than `redaction_policy_error`.
- `redaction_policy_error` remains reserved for redaction engine failures and post-check failures
  unrelated to integration credentials.

### Lab provider stage (`lab_provider`)

Default `fail_mode`: `fail_closed`

#### FATAL reason codes

| Reason code                    | Severity | Description                                                                                 |
| ------------------------------ | -------- | ------------------------------------------------------------------------------------------- |
| `inventory_resolution_failed`  | FATAL    | Provider inventory cannot be resolved (missing file, parse error, API failure).             |
| `asset_id_collision`           | FATAL    | Duplicate `asset_id` detected in resolved inventory.                                        |
| `invalid_inventory_format`     | FATAL    | Inventory artifact does not conform to declared `format`.                                   |
| `provider_api_error`           | FATAL    | Provider API returned an error or timeout (when provider is API-based, reserved for v0.3+). |
| `unstable_asset_id_resolution` | FATAL    | Resolved `asset_id` set is non-deterministic across retries.                                |

#### NON-FATAL reason codes (substage: `lab_provider.connectivity`)

Connectivity checks are an operational degradation, not a determinism failure. When recorded, they
MUST be recorded as a separate substage.

| Reason code                | Severity  | Description                                     |
| -------------------------- | --------- | ----------------------------------------------- |
| `partial_connectivity`     | NON-FATAL | Some resolved targets are unreachable.          |
| `connectivity_check_error` | NON-FATAL | Connectivity probe failed (timeout/auth error). |

### Runner stage (`runner`)

Default `fail_mode`: `fail_closed`

Minimum artifacts when enabled: `ground_truth.jsonl`, `runner/**`

#### FATAL reason codes

| Reason code                         | Severity | Description                                                                                                                              |
| ----------------------------------- | -------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| `target_connection_address_missing` | FATAL    | Target asset is resolved but has no usable address fields (no `asset.ip` and no `asset.hostname`) in `logs/lab_inventory_snapshot.json`. |
| `unstable_asset_id_resolution`      | FATAL    | `target_asset_id` cannot be resolved deterministically.                                                                                  |
| `plan_type_reserved`                | FATAL    | Plan type is reserved and not supported in this version.                                                                                 |
| `interactive_prompt_blocked`        | FATAL    | Runner received an interactive user prompt.                                                                                              |
| `plan_expansion_limit`              | FATAL    | Plan expansion exceeded configured limits; runner refused to execute the expanded plan.                                                  |
| `invalid_posture_mode`              | FATAL    | `posture.mode` is present but not one of the allowed enum values.                                                                        |
| `executor_not_found`                | FATAL    | Required executor binary/module is missing.                                                                                              |
| `ground_truth_write_failed`         | FATAL    | Cannot write `ground_truth.jsonl`.                                                                                                       |
| `action_key_collision`              | FATAL    | Duplicate `action_key` within the run.                                                                                                   |
| `invalid_lifecycle_transition`      | FATAL    | Runner detected an invalid lifecycle transition request (contract violation).                                                            |
| `unsafe_rerun_blocked`              | FATAL    | Runner refused to re-execute a non-idempotent action without successful `revert`.                                                        |
| `cleanup_invocation_failed`         | FATAL    | Cleanup command cannot be invoked (missing definition, executor failure).                                                                |
| `prepare_failed`                    | FATAL    | One or more actions failed during lifecycle `prepare`.                                                                                   |
| `execute_failed`                    | FATAL    | One or more actions failed during lifecycle `execute`.                                                                                   |
| `revert_failed`                     | FATAL    | One or more actions failed during lifecycle `revert`.                                                                                    |
| `teardown_failed`                   | FATAL    | One or more actions failed during lifecycle `teardown`.                                                                                  |

- Multi-target iteration (matrix plans) is reserved for v0.2; v0.1 enforces 1:1 action-target
  resolution.

#### FATAL reason codes (substage: `runner.integration_credentials`)

This substage records **credential preflight** for any runner-owned external integration that
requires authentication (for example an orchestration backend).

Default `fail_mode`: `fail_closed`

| Reason code                       | Severity | Description                                                                                               |
| --------------------------------- | -------- | --------------------------------------------------------------------------------------------------------- |
| `integration_credentials_missing` | FATAL    | A required credential reference is missing/empty or cannot be resolved by the configured secret provider. |
| `integration_credentials_invalid` | FATAL    | A credential resolves but fails integration validation/authentication.                                    |
| `integration_credentials_leaked`  | FATAL    | Resolved integration credential value detected in persisted output (artifacts or logs); safety violation. |

Normative requirements:

- This substage MUST run before the runner makes any external call that requires credentials.
- When this substage fails, the runner MUST NOT attempt execution that depends on the
  missing/invalid credentials.
- Implementations MUST NOT include resolved credential values in any outcome record, error message,
  or deterministic artifact.
- If a resolved integration credential value is detected in any persisted output bytes
  (contract-backed artifacts or any persisted logs), this substage MUST fail closed with
  `reason_code=integration_credentials_leaked`.

#### FATAL reason codes (substage: `runner.environment_config`)

This substage records run-scoped environment configuration and input-preparation work performed
prior to any action entering lifecycle `prepare` (including version pin validation, deterministic
SemVer resolution when permitted, and pack snapshotting).

Default `fail_mode`: `fail_closed`

| Reason code                    | Severity | Description                                                                |
| ------------------------------ | -------- | -------------------------------------------------------------------------- |
| `invalid_posture_mode`         | FATAL    | `posture.mode` is present but not one of the allowed enum values.          |
| `version_pin_missing`          | FATAL    | Required version pin is missing for an enabled feature (rules/packs/etc.). |
| `version_pin_unparseable`      | FATAL    | A `semver_v1` pin cannot be parsed as SemVer.                              |
| `version_resolution_failed`    | FATAL    | Omitted SemVer pin cannot be resolved deterministically (no candidates).   |
| `version_resolution_ambiguous` | FATAL    | Multiple candidates exist with same id/version but differing content hash. |
| `pin_consistency_violation`    | FATAL    | Canonical pins disagree across required mirrored locations/artifacts.      |
| `artifact_snapshot_failed`     | FATAL    | Selected pack-like artifact could not be snapshotted into the run bundle.  |
| `environment_config_failed`    | FATAL    | Environment configuration checks/apply failed or could not be verified.    |

#### NON-FATAL reason codes

| Reason code                   | Severity  | Description                                                                            |
| ----------------------------- | --------- | -------------------------------------------------------------------------------------- |
| `cleanup_verification_failed` | NON-FATAL | Cleanup verification failed or was indeterminate (policy-controlled).                  |
| `action_timeout`              | NON-FATAL | Action exceeded `timeout_seconds`.                                                     |
| `drift_detected`              | NON-FATAL | State reconciliation detected drift between recorded effects and observed state.       |
| `reconcile_failed`            | NON-FATAL | State reconciliation could not complete deterministically or report generation failed. |

Cleanup verification policy (normative):

- `cleanup.verification.status` in ground truth MUST be one of:
  `success | failed | indeterminate | skipped | not_applicable`.

- `failed` and `indeterminate` are **not success**.

- Default v0.1 behavior:

  - if runner stage `fail_mode=fail_closed`, a run MUST be marked `failed` when any action cleanup
    verification is `failed` or `indeterminate`
  - if runner stage `fail_mode=warn_and_skip`, cleanup verification failures MUST be recorded under
    `cleanup_verification_failed` and the run MAY be `partial`

- Ground truth MUST record lifecycle phase outcomes for each action, including a `teardown` phase.

- When cleanup verification is enabled, the runner MUST:

  - write `runner/actions/<action_id>/cleanup_verification.json`, and
  - reflect the aggregate result in the `teardown` phase `phase_outcome`.

State reconciliation policy (normative):

- When state reconciliation is enabled, the runner MUST:

  - write `runner/actions/<action_id>/state_reconciliation_report.json`, and
  - record a `logs/health.json` substage outcome with `stage: "runner.state_reconciliation"`.

- `reason_code` for `runner.state_reconciliation` MUST be constrained to:

  - `drift_detected`
  - `reconcile_failed`

  Deterministic selection (normative):

  - If any action's reconciliation cannot be completed deterministically (emit
    `reason_code=reconcile_failed` for that action report), the runner MUST record the substage
    outcome as `status="failed"` with `reason_code="reconcile_failed"`.
  - Otherwise, if any action report indicates drift (emit `reason_code=drift_detected` for that
    action report), the runner MUST record the substage outcome as `status="failed"` with
    `reason_code="drift_detected"`.
  - Otherwise, the runner MUST record the substage outcome as `status="success"` (and MUST omit
    `reason_code`).

- Default v0.1 behavior (policy-controlled via runner stage `fail_mode`):

  - if runner stage `fail_mode=fail_closed`, the run MUST be marked `failed` when:

    - any action reconciliation report indicates drift (emit `reason_code=drift_detected`), or
    - reconciliation cannot be completed deterministically for an action (emit
      `reason_code=reconcile_failed`).

  - if runner stage `fail_mode=warn_and_skip`, the runner MUST record the corresponding reason code
    under `runner.state_reconciliation` and the run MAY be `partial`.

- Relationship to the parent runner stage outcome:

  - If `runner.state_reconciliation` is recorded as `status="failed"`, the runner stage outcome MUST
    NOT be recorded as `status="success"`.

Lifecycle reason code guidance (normative):

- When a runner-stage failure can be attributed to a specific lifecycle phase, implementations MUST
  prefer emitting `prepare_failed | execute_failed | revert_failed | teardown_failed`.
- `cleanup_invocation_failed` is a v0.1 legacy alias for a `revert_failed` condition.
- `cleanup_verification_failed` is a v0.1 legacy alias for a `teardown_failed` condition.

Runner lifecycle aggregation (normative; deterministic):

- A stage outcome entry in `logs/health.json.stages[]` MUST include exactly one `reason_code`.
  - Multiple concurrent failures MUST be represented by:
    - choosing a single deterministic aggregate `reason_code` per the rules below, and
    - surfacing per-action detail in runner evidence and reports (out of scope for this ADR).
  - Separate substage outcomes (for example `runner.state_reconciliation`) are permitted and do not
    change this rule.

Runner lifecycle enforcement substage (normative; when emitted):

- When the runner enforces lifecycle transition guards or rerun-safety rules, it SHOULD record a
  `logs/health.json` substage outcome with `stage: "runner.lifecycle_enforcement"`.

- `reason_code` for `runner.lifecycle_enforcement` MUST be constrained to:

  - `invalid_lifecycle_transition`
  - `unsafe_rerun_blocked`

- Deterministic selection (normative):

  - If both enforcement conditions occur within a run, `runner.lifecycle_enforcement.reason_code`
    MUST be `unsafe_rerun_blocked` (and the runner MUST still increment counters for both
    conditions, if emitted elsewhere).

- Relationship to the parent runner stage outcome:

  - If `runner.lifecycle_enforcement` is recorded as `status="failed"`, the runner stage outcome
    MUST NOT be recorded as `status="success"`.
  - If the runner stage is recorded as `status="failed"` due to runner-enforced guards, the runner
    stage `reason_code` MUST be the corresponding enforcement code (see below).

- If the runner stage is recorded as `status="failed"` due to **runner-enforced guards** (for
  example invalid transition prevention or deterministic rerun refusal), the runner MUST set the
  runner stage `reason_code` directly to the corresponding enforcement code:

  - `invalid_lifecycle_transition`, or
  - `unsafe_rerun_blocked`. These enforcement codes MUST take precedence over lifecycle-derived
    aggregation rules below.

- If the runner stage is recorded as `status="failed"` due to lifecycle phase outcomes, the runner
  MUST derive the runner stage `reason_code` deterministically from per-action lifecycle records
  (ground truth), using the following precedence:

  1. `prepare_failed` (any action has `prepare.phase_outcome="failed"`)
  1. `execute_failed` (otherwise, any action has `execute.phase_outcome="failed"`)
  1. `revert_failed` (otherwise, any action has `revert.phase_outcome="failed"`)
  1. `teardown_failed` (otherwise, any action has `teardown.phase_outcome="failed"`)

  Notes:

  - “Any action” MUST be evaluated over the set of ground truth rows for the run. Implementations
    MUST NOT depend on input iteration order; they MUST treat ground truth as the source of truth.
  - If multiple phases fail across different actions, the earliest phase in the precedence list MUST
    win. This ensures stable root-cause reporting (fix earlier failures first).

- Legacy alias handling (deterministic):

  - Implementations SHOULD NOT emit legacy aliases in new builds.
  - If a legacy alias is emitted, it MUST be treated as equivalent to its canonical lifecycle code
    for aggregation:
    - `cleanup_invocation_failed` is equivalent to `revert_failed`.
    - `cleanup_verification_failed` is equivalent to `teardown_failed`.
  - Implementations MUST NOT emit both a legacy alias and its canonical lifecycle code for the same
    run.

- Cleanup verification interaction (deterministic):

  - When cleanup verification failures are treated as fail-closed for the runner stage, the runner
    stage `reason_code` MUST be `teardown_failed` (not `cleanup_verification_failed`).
  - When cleanup verification failures are treated as warn-and-skip for the runner stage, the runner
    stage `reason_code` MUST be `cleanup_verification_failed` and the run MAY be `partial` (per
    policy).

### Telemetry stage (`telemetry`)

Default `fail_mode`: `fail_closed` (v0.1 baseline)

Minimum artifacts when enabled: `raw_parquet/**`, `manifest.json`

#### FATAL reason codes

| Reason code                     | Severity | Description                                                                                            |
| ------------------------------- | -------- | ------------------------------------------------------------------------------------------------------ |
| `required_source_missing`       | FATAL    | Required telemetry source is not installed or configured (for example Sysmon).                         |
| `source_not_implemented`        | FATAL    | Source is enabled but not implemented in v0.1 (for example pcap placeholder).                          |
| `baseline_profile_missing`      | FATAL    | Telemetry baseline profile gate enabled but profile is missing or unreadable.                          |
| `baseline_profile_invalid`      | FATAL    | Telemetry baseline profile is present but fails contract validation.                                   |
| `baseline_profile_not_met`      | FATAL    | Telemetry baseline profile requirements not met for one or more assets.                                |
| `collector_startup_failed`      | FATAL    | Collector cannot start (config parse error, binding failure).                                          |
| `checkpoint_store_corrupt`      | FATAL    | Checkpoint/offset store corruption prevents reliable ingestion or collector startup.                   |
| `agent_heartbeat_missing`       | FATAL    | No agent self-telemetry heartbeat observed for one or more expected assets within startup grace.       |
| `disk_free_space_insufficient`  | FATAL    | Disk preflight indicates insufficient free space for configured run budgets.                           |
| `disk_metrics_missing`          | FATAL    | Disk preflight metrics could not be computed deterministically.                                        |
| `resource_budgets_unconfigured` | FATAL    | Resource budget thresholds are required but not configured.                                            |
| `resource_metrics_missing`      | FATAL    | Required collector self-telemetry measurements are missing.                                            |
| `eps_target_not_met`            | FATAL    | Sustained EPS target was not met, preventing deterministic budget measurement window selection.        |
| `egress_canary_unconfigured`    | FATAL    | Egress canary endpoint is required but not configured.                                                 |
| `egress_probe_unavailable`      | FATAL    | Egress probe could not be executed on the asset.                                                       |
| `egress_violation`              | FATAL    | Egress probe succeeded despite deny policy.                                                            |
| `raw_xml_unavailable`           | FATAL^   | Required raw XML (or equivalent raw record) cannot be acquired when strict fail-closed policy applies. |

^ Policy-dependent override:

- If telemetry stage `fail_mode=fail_closed` (default), `raw_xml_unavailable` is FATAL.
- If telemetry stage `fail_mode=warn_and_skip`, affected records MUST be skipped and counted; stage
  MAY complete as NON-FATAL degraded with a warning entry and stable counters.

#### Telemetry baseline profile gate (substage: `telemetry.baseline_profile`)

When `telemetry.baseline_profile.enabled=true`, the telemetry validator MUST evaluate the
contract-backed baseline profile snapshot at `runs/<run_id>/inputs/telemetry_baseline_profile.json`
(see `040_telemetry_pipeline.md`) and record a substage outcome in `logs/health.json`.

If this substage fails, the telemetry stage MUST fail closed. The telemetry stage MAY use the same
`reason_code` as the substage outcome.

`reason_code` for this substage MUST be constrained to:

- `baseline_profile_missing`
- `baseline_profile_invalid`
- `baseline_profile_not_met`

#### Windows raw-mode canary (substage: `telemetry.windows_eventlog.raw_mode`)

When enabled, the Windows raw-mode canary MUST be recorded as a substage outcome in
`logs/health.json` with `reason_code` constrained to:

- `winlog_raw_missing`
- `winlog_rendering_detected`

These codes MUST NOT be replaced by an aggregate code in the raw-mode substage outcome.

#### Network egress policy canary (substage: `telemetry.network.egress_policy`)

When effective outbound policy is denied for the run, the validator MUST record a substage outcome
`telemetry.network.egress_policy` in `logs/health.json`.

If this substage fails, the telemetry stage MUST fail closed. The telemetry stage MAY use the same
`reason_code` as the substage outcome.

`reason_code` for this substage MUST be constrained to:

- `egress_canary_unconfigured` (no canary endpoint configured when required)
- `egress_probe_unavailable` (probe could not be executed on the asset)
- `egress_violation` (probe succeeded despite deny policy)

#### Agent liveness (substage: `telemetry.agent.liveness`)

This substage distinguishes "agent is idle" from "agent failed before exporting telemetry" in
push-only OTLP architectures by requiring an OS-neutral heartbeat derived from collector
self-telemetry.

If this substage fails, the telemetry stage MUST fail closed. The telemetry stage MAY use the same
`reason_code` as the substage outcome.

`reason_code` for this substage MUST be constrained to:

- `agent_heartbeat_missing` (no self-telemetry heartbeat observed within startup grace)

#### Disk preflight (substage: `telemetry.disk.preflight`)

This substage is a fail-closed safety gate that verifies the run host has sufficient free space to
complete the run within configured disk budgets.

If this substage fails, the telemetry stage MUST fail closed. The telemetry stage MAY use the same
`reason_code` as the substage outcome.

`reason_code` for this substage MUST be constrained to:

- `disk_metrics_missing` (cannot compute free space or required bytes deterministically)
- `disk_free_space_insufficient` (computed free space is less than projected required bytes)

#### Checkpointing storage integrity (substage: `telemetry.checkpointing.storage_integrity`)

This substage records checkpoint store integrity failures that prevent reliable ingestion.

If this substage fails, the telemetry stage MUST fail closed. The telemetry stage MAY use the same
`reason_code` as the substage outcome.

`reason_code` for this substage MUST be constrained to:

- `checkpoint_store_corrupt` (checkpoint corruption prevents collector startup or reliable reads)

#### Resource budgets (substage: `telemetry.resource_budgets`)

This substage enforces comparability gates (EPS and resource budgets) using collector
self-telemetry.

`reason_code` for this substage MUST be constrained to:

- `resource_budgets_unconfigured` (required thresholds are missing; fail closed)
- `resource_metrics_missing` (required self-telemetry measurements missing; fail closed)
- `eps_target_not_met` (cannot select sustained EPS window deterministically; fail closed)
- `resource_budget_cpu_exceeded` (CPU budget exceeded; warn-and-skip)
- `resource_budget_memory_exceeded` (memory budget exceeded; warn-and-skip)
- `resource_budget_queue_pressure` (queue pressure indicates backpressure; warn-and-skip)

#### NON-FATAL reason codes

| Reason code                      | Severity  | Description                                                   |
| -------------------------------- | --------- | ------------------------------------------------------------- |
| `checkpoint_loss`                | NON-FATAL | Checkpoint lost or reset; replay occurred (dedupe mitigates). |
| `publisher_metadata_unavailable` | NON-FATAL | Windows rendering metadata missing but raw record is present. |

### Normalization stage (`normalization`)

Default `fail_mode`: `fail_closed` when `normalization.strict_mode=true`; otherwise `warn_and_skip`

Minimum artifacts when enabled: `normalized/**`, `normalized/mapping_coverage.json`

#### FATAL reason codes

| Reason code                  | Severity | Description                                                                       |
| ---------------------------- | -------- | --------------------------------------------------------------------------------- |
| `mapping_profile_invalid`    | FATAL    | Mapping profile cannot be loaded or is schema-invalid.                            |
| `ocsf_schema_mismatch`       | FATAL    | Pinned OCSF version differs across normalizer and bridge.                         |
| `event_id_generation_failed` | FATAL    | Deterministic event identity cannot be computed for a record under strict policy. |

#### NON-FATAL reason codes

| Reason code              | Severity   | Description                                                    |
| ------------------------ | ---------- | -------------------------------------------------------------- |
| `timestamp_parse_failed` | NON-FATAL^ | Event dropped; counter incremented in `mapping_coverage.json`. |
| `unmapped_source_type`   | NON-FATAL  | Source type has no mapping profile; record in coverage.        |
| `missing_core_field`     | NON-FATAL  | Required core field absent; record in coverage.                |

^ Policy-dependent override:

- If `normalization.strict_mode=true` (or normalization stage `fail_mode=fail_closed`), any
  `timestamp_parse_failed` MAY be escalated to a stage failure (FATAL) if configured as such.
  Default v0.1 policy: drop-and-count, warn-and-skip.

#### Quality gate: Tier 1 coverage (substage permitted)

Tier 1 coverage thresholds MUST NOT be expressed as a fail-closed failure unless explicitly
configured as such. Default v0.1 posture:

- `tier1_coverage_below_gate` is NON-FATAL degraded (recorded as `fail_mode=warn_and_skip`),
  producing `manifest.status=partial`.

### Validation stage (`validation`)

Default `fail_mode`: `warn_and_skip` (v0.1 baseline)

This stage includes criteria pack evaluation and orchestrator-level validation gates (for example
run limits). Implementations MAY record substages.

#### FATAL reason codes

| Reason code            | Severity | Description                                                                                       |
| ---------------------- | -------- | ------------------------------------------------------------------------------------------------- |
| `criteria_pack_error`  | FATAL    | Criteria pack cannot be loaded or is schema-invalid (when validation is enabled and fail-closed). |
| `ground_truth_missing` | FATAL    | `ground_truth.jsonl` missing or unreadable.                                                       |
| `time_window_error`    | FATAL    | Evaluation windows cannot be derived deterministically.                                           |

#### NON-FATAL reason codes

| Reason code             | Severity  | Description                                                       |
| ----------------------- | --------- | ----------------------------------------------------------------- |
| `criteria_query_failed` | NON-FATAL | A specific criteria query failed; mark that criterion as `error`. |

#### Run limits (substage: `validation.run_limits`)

Run limit conditions MUST be recorded deterministically when they occur.

| Reason code             | Run status | Exit code | Description                                       |
| ----------------------- | ---------- | --------- | ------------------------------------------------- |
| `run_timeout`           | `failed`   | `20`      | Run exceeded `max_run_minutes`.                   |
| `disk_limit_exceeded`   | `partial`^ | `10`^     | Run exceeded `max_disk_gb` (graceful truncation). |
| `memory_limit_exceeded` | `failed`   | `20`      | Run exceeded `max_memory_mb`.                     |
| `oom_killed`            | `failed`   | `20`      | Process killed by OS OOM killer.                  |

^ Disk limit override: operators MAY configure disk limit behavior as hard fail; if so,
`disk_limit_exceeded` yields `failed` and `20`.

### Detection stage (`detection`)

Default `fail_mode`: `fail_closed`

Minimum artifacts when enabled: `detections/detections.jsonl`, `bridge/**`

#### FATAL reason codes

| Reason code                   | Severity | Description                                    |
| ----------------------------- | -------- | ---------------------------------------------- |
| `bridge_mapping_pack_invalid` | FATAL    | Bridge mapping pack missing or schema-invalid. |
| `backend_driver_failed`       | FATAL    | Backend cannot open or mount dataset.          |

#### Performance budgets (substage: `detection.performance_budgets`)

This substage is a deterministic quality gate for detection evaluation performance/footprint budgets
(compile and evaluation cost). It MUST be driven by deterministic metrics emitted in
`runs/<run_id>/logs/counters.json` (see `110_operability.md`).

`reason_code` for this substage MUST be constrained to:

- `detection_budget_exceeded` (warn-and-skip): one or more configured detection budget thresholds
  were exceeded.
- `detection_budget_metrics_missing` (fail closed): required deterministic metrics are missing
  (budget gate enabled but cannot be evaluated).

#### NON-FATAL reason codes (per-rule; rule-level fail-closed)

These are emitted at rule granularity (for example in compiled plans). Stage continues.

| Reason code               | Severity  | Description                                                                       |
| ------------------------- | --------- | --------------------------------------------------------------------------------- |
| `unroutable_logsource`    | NON-FATAL | Sigma `logsource` matches no router entry. Rule is non-executable.                |
| `unmapped_field`          | NON-FATAL | Sigma field has no alias mapping. Rule is non-executable unless fallback enabled. |
| `raw_fallback_disabled`   | NON-FATAL | Rule requires `raw.*` but fallback is disabled.                                   |
| `ambiguous_field_alias`   | NON-FATAL | Sigma field alias resolution is ambiguous for the routed scope.                   |
| `unsupported_modifier`    | NON-FATAL | Sigma modifier cannot be expressed.                                               |
| `unsupported_operator`    | NON-FATAL | Sigma operator cannot be expressed.                                               |
| `unsupported_value_type`  | NON-FATAL | Sigma value type cannot be represented for the chosen operator/backend.           |
| `unsupported_regex`       | NON-FATAL | Sigma regex pattern uses unsupported constructs (RE2-only).                       |
| `unsupported_correlation` | NON-FATAL | Sigma correlation / multi-event semantics are out of scope.                       |
| `unsupported_aggregation` | NON-FATAL | Sigma aggregation semantics are out of scope.                                     |
| `backend_compile_error`   | NON-FATAL | Backend compilation failed.                                                       |
| `backend_eval_error`      | NON-FATAL | Backend evaluation failed.                                                        |

### Scoring stage (`scoring`)

Default `fail_mode`: `fail_closed`

Minimum artifacts when enabled: `scoring/summary.json`

#### FATAL reason codes

| Reason code               | Severity | Description                                           |
| ------------------------- | -------- | ----------------------------------------------------- |
| `summary_write_failed`    | FATAL    | Cannot write `scoring/summary.json`.                  |
| `scoring_summary_invalid` | FATAL    | Summary fails contract validation.                    |
| `join_incompleteness`     | FATAL^   | Required joins cannot be completed deterministically. |

^ Policy-dependent override:

- Default v0.1 policy: `join_incompleteness` is FATAL.
- Operators MAY configure scoring join behavior to warn-and-skip; if so, record
  `join_incompleteness` as NON-FATAL degraded and set run status `partial`.

#### NON-FATAL reason codes

| Reason code    | Severity  | Description                                                                 |
| -------------- | --------- | --------------------------------------------------------------------------- |
| `join_partial` | NON-FATAL | Join completed but some actions lack detections; record in coverage fields. |

### Reporting stage (`reporting`)

Default `fail_mode`: `fail_closed` (v0.1 baseline)

Minimum artifacts when enabled: `report/**`

Reporting is presentation-oriented. Machine-readable required summary output is produced by the
`scoring` stage.

#### Reason codes

| Reason code           | Severity | Description                                             |
| --------------------- | -------- | ------------------------------------------------------- |
| `report_write_failed` | FATAL    | Cannot write report files.                              |
| `html_render_error`   | FATAL^   | HTML rendering failed (template error, missing inputs). |

^ Policy-dependent override:

- If `reporting.emit_html=true` and `reporting.fail_mode=fail_closed`, `html_render_error` is FATAL.
- If HTML is configured as best-effort (either `emit_html=false` or stage
  `fail_mode=warn_and_skip`), record `html_render_error` as NON-FATAL warning-only.

#### Regression compare substage (`reporting.regression_compare`)

Regression comparison is a quality gate: it evaluates comparability to a baseline run and, when
enabled, produces deterministic regression deltas in reporting artifacts. Regression comparison MUST
NOT affect the reporting stage's ability to publish `report/**` artifacts; it is recorded as a
separate substage outcome.

Default `fail_mode`: `warn_and_skip` (quality gate)

When regression comparison is enabled, the orchestrator or reporting implementation MUST emit a
`logs/health.json` substage outcome with `stage: "reporting.regression_compare"`.

`reason_code` for `reporting.regression_compare` MUST be constrained to:

| Reason code                 | Severity  | Description                                                         |
| --------------------------- | --------- | ------------------------------------------------------------------- |
| `baseline_missing`          | NON-FATAL | Baseline run not found or unreadable.                               |
| `baseline_incompatible`     | NON-FATAL | Required artifacts missing or contract versions are not comparable. |
| `regression_compare_failed` | NON-FATAL | Unexpected runtime error computing regression deltas.               |

Deterministic selection (normative):

1. If the baseline reference cannot be resolved or the baseline run is unreadable, the substage
   outcome MUST be recorded as `status="failed"` with `reason_code="baseline_missing"`.
1. Otherwise, if required baseline or candidate artifacts are missing, or if contract/schema
   versions are not comparable, the substage outcome MUST be recorded as `status="failed"` with
   `reason_code="baseline_incompatible"`.
1. Otherwise, if regression comparison fails due to an unexpected runtime error, the substage
   outcome MUST be recorded as `status="failed"` with `reason_code="regression_compare_failed"`.
1. Otherwise, the substage outcome MUST be recorded as `status="success"` (and MUST omit
   `reason_code`).

### Signing stage (`signing`)

Default `fail_mode`: `fail_closed` (when enabled)

#### FATAL reason codes

| Reason code                     | Severity | Description                                     |
| ------------------------------- | -------- | ----------------------------------------------- |
| `signing_key_unavailable`       | FATAL    | Required signing key or material not available. |
| `signature_write_failed`        | FATAL    | Signature artifacts could not be written.       |
| `signature_verification_failed` | FATAL    | Self-verification of produced signature failed. |

## Consequences

- Operators can triage failures deterministically using `(stage, status, fail_mode, reason_code)`.
- CI gating can be implemented mechanically (exit codes and stage outcomes are authoritative).
- `logs/health.json` remains minimal and deterministic; warnings are separated.
- The orchestrator can be implemented as a one-shot process per run while preserving reproducibility
  and safe failure behavior.
- Policy-dependent overrides are explicitly constrained and deterministic (configuration-driven
  only).

## References

- [Data contracts specification](../spec/025_data_contracts.md)
- [Plan execution model ADR](../adr/ADR-0006-plan-execution-model.md)

## Changelog

| Date       | Change                                                           |
| ---------- | ---------------------------------------------------------------- |
| 2026-01-28 | Replace legacy plan-draft example with `inputs/plan_draft.yaml`. |
| 2026-01-13 | Add telemetry.network.egress_policy canary reason codes          |
| 2026-01-12 | Formatting update                                                |
