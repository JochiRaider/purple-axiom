<!-- docs/adr/ADR-0005-stage-outcomes-and-failure-classification.md -->

# ADR-0005: Stage outcomes and failure classification (v0.1)

## Status

Proposed

## Context

Purple Axiom v0.1 requires deterministic, machine-readable failure classification to support:

- operator triage (which stage failed and why)
- CI gating (fail closed vs warn and skip)
- run status derivation (`success | partial | failed`)
- health file emission (`runs/<run_id>/logs/health.json`)

The system already specifies:

- a stable, staged pipeline (lab provider → runner → telemetry → normalization → validation →
  detection → scoring → reporting → signing),
- a local-first run bundle (`runs/<run_id>/…`) and manifest-driven reproducibility,
- operability requirements for `logs/health.json`, run limits, and exit codes.

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

### Stage outcome

A stage outcome is a tuple emitted for each enabled pipeline stage (and for any defined substages
that the implementation chooses to record):

- `stage` (string): stable stage identifier
- `status` (string): `success | failed | skipped`
- `fail_mode` (string): `fail_closed | warn_and_skip`
- `reason_code` (string, optional): stable token explaining failure/skip

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

**Exception:** Outcome recording MUST NOT be attempted when doing so would violate locking
guarantees or is impossible due to storage I/O failure.

In those exceptional cases:

- the orchestrator MUST emit the failure to stderr
- the orchestrator MUST exit with the correct process exit code (see “Exit codes”)

Rationale: two fatal conditions can prevent safe outcome writes:

- `storage_io_error` (cannot write reliably)
- `lock_acquisition_failed` (cannot safely mutate the run bundle without the lock)

### Warning-only entries

Warning-only entries (non-fatal degradations, informational signals) MUST be written to:

- `runs/<run_id>/logs/warnings.jsonl` (optional structured log), and/or
- `runs/<run_id>/logs/run.log` (required text log)

`runs/<run_id>/logs/health.json` MUST contain only stage outcomes.

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

- `reason_code` MUST be ASCII `lower_snake_case`.
- `reason_code` MUST be stable across runs and versions within v0.1.
- `reason_code` MUST be selected from the normative catalog in this ADR for the relevant
  `(stage, reason_code)` pair.

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

**Exception:** When prevented by lock or I/O constraints (see “Outcome recording requirement”).

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

```
registry[(stage_id, reason_code)] -> {
  default_fail_mode: "fail_closed" | "warn_and_skip",
  override_rules: [...]
}
```

Override rules MUST be deterministic and MUST reference only explicit configuration inputs (for
example `normalization.strict_mode`, `reporting.emit_html`).

## Failure taxonomy (normative reason codes)

This section defines the authoritative reason codes for v0.1. Codes not listed here MUST NOT be
emitted in `logs/health.json` without a spec update.

### Cross-cutting (applies to any stage)

These reason codes MAY be used for any stage.

| Reason code                   | Severity | Description                                                                              |
| ----------------------------- | -------- | ---------------------------------------------------------------------------------------- |
| `redaction_policy_error`      | FATAL    | Redaction engine failed or post-check failed; artifacts cannot be safely persisted.      |
| `config_schema_invalid`       | FATAL    | A required config artifact is schema-invalid (for example `manifest.json`, `plan.json`). |
| `input_missing`               | FATAL    | Required upstream input artifact missing or unreadable.                                  |
| `lock_acquisition_failed`     | FATAL    | Exclusive lock could not be acquired.                                                    |
| `storage_io_error`            | FATAL    | Storage error prevents atomic writes (for example ENOSPC/EIO).                           |
| `blocked_by_upstream_failure` | SKIPPED  | Stage did not run because an upstream stage failed fail-closed.                          |

### Lab provider stage (`lab_provider`)

Default `fail_mode`: `fail_closed`

#### FATAL reason codes

| Reason code                    | Severity | Description                                                                     |
| ------------------------------ | -------- | ------------------------------------------------------------------------------- |
| `inventory_resolution_failed`  | FATAL    | Provider inventory cannot be resolved (missing file, parse error, API failure). |
| `asset_id_collision`           | FATAL    | Duplicate `asset_id` detected in resolved inventory.                            |
| `invalid_inventory_format`     | FATAL    | Inventory artifact does not conform to declared `format`.                       |
| `provider_api_error`           | FATAL    | Provider API returned an error or timeout (when provider is API-based).         |
| `unstable_asset_id_resolution` | FATAL    | Resolved `asset_id` set is non-deterministic across retries.                    |

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

| Reason code                    | Severity | Description                                                               |
| ------------------------------ | -------- | ------------------------------------------------------------------------- |
| `unstable_asset_id_resolution` | FATAL    | `target_asset_id` cannot be resolved deterministically.                   |
| `executor_not_found`           | FATAL    | Required executor binary/module is missing.                               |
| `ground_truth_write_failed`    | FATAL    | Cannot write `ground_truth.jsonl`.                                        |
| `action_key_collision`         | FATAL    | Duplicate `action_key` within the run.                                    |
| `cleanup_invocation_failed`    | FATAL    | Cleanup command cannot be invoked (missing definition, executor failure). |

#### NON-FATAL reason codes

| Reason code                   | Severity  | Description                                                           |
| ----------------------------- | --------- | --------------------------------------------------------------------- |
| `cleanup_verification_failed` | NON-FATAL | Cleanup verification failed or was indeterminate (policy-controlled). |
| `action_timeout`              | NON-FATAL | Action exceeded `timeout_seconds`.                                    |

Cleanup verification policy (normative):

- `cleanup.verification.status` in ground truth MUST be one of:
  `success | failed | indeterminate | skipped | not_applicable`.

- `failed` and `indeterminate` are **not success**.

- Default v0.1 behavior:

  - if runner stage `fail_mode=fail_closed`, a run MUST be marked `failed` when any action cleanup
    verification is `failed` or `indeterminate`
  - if runner stage `fail_mode=warn_and_skip`, cleanup verification failures MUST be recorded under
    `cleanup_verification_failed` and the run MAY be `partial`

### Telemetry stage (`telemetry`)

Default `fail_mode`: `fail_closed` (v0.1 baseline)

Minimum artifacts when enabled: `raw_parquet/**`, `manifest.json`

#### FATAL reason codes

| Reason code                   | Severity | Description                                                                                            |
| ----------------------------- | -------- | ------------------------------------------------------------------------------------------------------ |
| `required_source_missing`     | FATAL    | Required telemetry source is not installed/configured (for example Sysmon).                            |
| `source_not_implemented`      | FATAL    | Source is enabled but not implemented in v0.1 (for example pcap placeholder).                          |
| `collector_startup_failed`    | FATAL    | Collector cannot start (config parse error, binding failure).                                          |
| `checkpoint_corruption_fatal` | FATAL    | Checkpoint is corrupt and automatic recovery failed.                                                   |
| `raw_xml_unavailable`         | FATAL^   | Required raw XML (or equivalent raw record) cannot be acquired when strict fail-closed policy applies. |

^ Policy-dependent override:

- If telemetry stage `fail_mode=fail_closed` (default), `raw_xml_unavailable` is FATAL.
- If telemetry stage `fail_mode=warn_and_skip`, affected records MUST be skipped and counted; stage
  MAY complete as NON-FATAL degraded with a warning entry and stable counters.

#### Windows raw-mode canary (substage: `telemetry.windows_eventlog.raw_mode`)

When enabled, the Windows raw-mode canary MUST be recorded as a substage outcome in
`logs/health.json` with `reason_code` constrained to:

- `winlog_raw_missing`
- `winlog_rendering_detected`

These codes MUST NOT be replaced by an aggregate code in the raw-mode substage outcome.

#### NON-FATAL reason codes

| Reason code                      | Severity  | Description                                                   |
| -------------------------------- | --------- | ------------------------------------------------------------- |
| `checkpoint_loss`                | NON-FATAL | Checkpoint lost/reset; replay occurred (dedupe mitigates).    |
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
`disk_limit_exceeded` yields `failed` / `20`.

### Detection stage (`detection`)

Default `fail_mode`: `fail_closed`

Minimum artifacts when enabled: `detections/detections.jsonl`, `bridge/**`

#### FATAL reason codes

| Reason code                   | Severity | Description                                    |
| ----------------------------- | -------- | ---------------------------------------------- |
| `bridge_mapping_pack_invalid` | FATAL    | Bridge mapping pack missing or schema-invalid. |
| `backend_driver_failed`       | FATAL    | Backend cannot open/mount dataset.             |

#### NON-FATAL reason codes (per-rule; rule-level fail-closed)

These are emitted at rule granularity (for example in compiled plans). Stage continues.

| Reason code             | Severity  | Description                                                                       |
| ----------------------- | --------- | --------------------------------------------------------------------------------- |
| `unroutable_logsource`  | NON-FATAL | Sigma `logsource` matches no router entry. Rule is non-executable.                |
| `unmapped_field`        | NON-FATAL | Sigma field has no alias mapping. Rule is non-executable unless fallback enabled. |
| `raw_fallback_disabled` | NON-FATAL | Rule requires `raw.*` but fallback is disabled.                                   |
| `unsupported_modifier`  | NON-FATAL | Sigma modifier cannot be expressed.                                               |
| `backend_compile_error` | NON-FATAL | Backend compilation failed.                                                       |
| `backend_eval_error`    | NON-FATAL | Backend evaluation failed.                                                        |

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

### Signing stage (`signing`)

Default `fail_mode`: `fail_closed` (when enabled)

#### FATAL reason codes

| Reason code                     | Severity | Description                                     |
| ------------------------------- | -------- | ----------------------------------------------- |
| `signing_key_unavailable`       | FATAL    | Required signing key/material not available.    |
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
