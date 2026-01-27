---
title: Atomic Red Team executor integration contract
description: Defines the integration contract between Purple Axiom and Invoke-AtomicRedTeam for atomic actions.
status: draft
---

# Atomic Red Team executor integration contract

This document defines the normative integration contract between Purple Axiom and the
Invoke-AtomicRedTeam executor stack for `engine = "atomic"` actions. It specifies the following and
is designed to make runs reproducible and cross-run comparable while preserving operator-debuggable
evidence.

- Deterministic Atomic YAML parsing
- Deterministic input resolution (defaults, overrides, template expansion)
- Prerequisites (dependencies) evaluation and optional fetch workflow and evidence artifacts
- Transcript capture and storage requirements (encoding, redaction, layout)
- Cleanup invocation and cleanup verification workflow and artifacts

## Overview

This spec defines how the runner discovers and parses Atomic YAML, resolves inputs, canonicalizes
identity-bearing materials, evaluates prerequisites, captures transcripts, and records cleanup
verification. It sets the deterministic behavior, evidence artifacts, and failure modes needed for
cross-run comparability.

## Relationship to other specs

This document is additive and MUST be read alongside:

- [Data contracts spec](025_data_contracts.md) for hashing, `parameters.resolved_inputs_sha256`, run
  bundle layout, runner evidence artifact semantics, and ground-truth evidence pointer requirements
- [Scenario model spec](030_scenarios.md) for stable `action_key` basis, lifecycle phase semantics,
  and Atomic Test Plan scenarios
- [Validation criteria spec](035_validation_criteria.md) for cleanup verification semantics
- [Storage formats spec](045_storage_formats.md) for run bundle layout and artifact naming
  conventions
- [Configuration reference](120_config_reference.md) for `runner.atomic.*` feature gates and
  defaults
- [State machines ADR](../adr/ADR-0007-state-machines.md) for lifecycle state machine integration
  and recovery semantics
- [Redaction policy ADR](../adr/ADR-0003-redaction-policy.md) for deterministic redaction
  requirements

If this document conflicts with any of the above, the conflict MUST be resolved explicitly via a
spec patch (do not implement "best effort" divergence).

## Lifecycle phase mapping

Purple Axiom's action lifecycle is defined in the scenario model. For `engine = "atomic"` actions,
the runner MUST map Atomic semantics to lifecycle phases as follows:

| Atomic semantic                                         | Lifecycle phase | Notes                                                                                      |
| ------------------------------------------------------- | --------------- | ------------------------------------------------------------------------------------------ |
| Dependency evaluation (`prereq_command`)                | `prepare`       | prereqs transcript + executor evidence prereqs block                                       |
| Dependency fetch (`get_prereq_command`)                 | `prepare`       | Any prerequisite materialization is recorded as `prepare`.                                 |
| Primary command invocation (`executor.command`)         | `execute`       | The detonation attempt.                                                                    |
| Cleanup command invocation (`executor.cleanup_command`) | `revert`        | Undo detonation side-effects to enable a safe re-run.                                      |
| Cleanup verification (`cleanup_verification.json`)      | `teardown`      | Post-run verification. Teardown MAY also remove runner-created prereq artifacts when safe. |

Revert vs teardown (normative):

- The runner MUST record `revert` separately from `teardown`. `revert` exists to undo execute
  side-effects; `teardown` exists to remove per-action prerequisites (when applicable) and to record
  cleanup verification outcomes.
  - The runner MUST NOT attempt to uninstall or remove system-wide prerequisites by default (risk:
    deleting prerequisites shared by other techniques). Any prerequisite removal behavior MUST be
    explicit, opt-in, and deterministic.

Idempotence (normative):

- Unless the scenario/action descriptor explicitly declares otherwise, Atomic actions MUST default
  `idempotence` to `unknown`.
  - When `idempotence` is `unknown`, the runner MUST treat the action as `non_idempotent` for safety
    (do not assume it is safe to re-run without a successful `revert`).

## Runner-enforced lifecycle guards (normative)

The runner MUST enforce the lifecycle order and phase applicability constraints defined in the
scenario model spec. Ground truth lifecycle records MUST include the phase order:

`prepare -> execute -> revert -> teardown`

and phases that are not attempted MUST be recorded as `phase_outcome=skipped` with a stable
`reason_domain="ground_truth"` and `reason_code` (see `025_data_contracts.md`).

Guard conditions (normative):

1. Cleanup suppression (policy, not an error)

- If effective `plan.cleanup=false`, the runner MUST NOT attempt `revert` or cleanup-dependent
  `teardown` work for the action.
- Ground truth MUST record `revert.phase_outcome=skipped` and `teardown.phase_outcome=skipped` with
  `reason_domain="ground_truth"` and `reason_code=cleanup_suppressed`.

2. Prior-phase blocked (normal lifecycle short-circuit, not an error)

- If `execute` was not attempted for an action instance (for example: requirements caused `prepare`
  to be skipped, or `execute` was skipped/failed before invocation), the runner MUST NOT attempt
  `revert`.
- In this case, if cleanup is otherwise enabled, ground truth MUST record
  `revert.phase_outcome=skipped` with `reason_code=prior_phase_blocked`.

3. Invalid lifecycle transition (true violation)

- The runner MUST reserve `reason_code=invalid_lifecycle_transition` for explicit/forced lifecycle
  transition requests that violate the allowed transitions (e.g., external resume/orchestrator
  asking to run `revert` for an action instance that has no `execute` attempt record and is not
  explainable by `prior_phase_blocked` or `cleanup_suppressed` semantics).

Rerun safety:

- If a run is restarted and an action is detected as already executed but not reverted, the runner
  MUST:
  - block unsafe reruns if `runner.atomic.rerun.block_if_not_reverted=true` and emit
    `reason_code = unsafe_rerun_blocked`
  - otherwise, mark action as already executed and proceed to cleanup if allowed

Re-run safety refusal (normative):

- If the runner is asked to attempt `execute` more than once for the same action instance without an
  intervening successful `revert`, and the effective idempotence is treated as `non_idempotent`
  (including `idempotence="unknown"`), the runner MUST refuse the `execute` attempt.
  - The runner MUST still record an `execute` phase record with `phase_outcome="skipped"` and
    `reason_code="unsafe_rerun_blocked"` (see data contracts spec "Re-run safety and refusal
    recording").
  - If the runner records the refusal as an additional attempt within the same action instance, it
    MUST follow the retry ordering requirements in the data contracts spec (`attempt_ordinal`,
    deterministic ordering).

Observability (normative):

- When the runner blocks an invalid transition or refuses an unsafe re-run, it MUST:
  - record the per-action phase `reason_code` as above, and
  - record the enforcement event in `logs/health.json` as substage
    `stage="runner.lifecycle_enforcement"` with `status="failed"` and
    `reason_code="invalid_lifecycle_transition"` or `reason_code="unsafe_rerun_blocked"` (see
    ADR-0005 and `110_operability.md`).

Cleanup suppression interaction (normative):

- If cleanup behavior is suppressed for an action instance (for example, operator config disables
  cleanup invocation and/or verification), the runner MUST treat the action instance as not proven
  reverted and MUST apply the re-run safety refusal rules above for non-idempotent actions.

## Definitions

### Reference executor

For v0.1, the **reference executor** is the tuple:

- PowerShell runtime: **PowerShell 7.4.6**
- Invoke-AtomicRedTeam module: pinned exact version
- Atomic Red Team content: pinned reference (commit SHA, tag, or vendored content hash)

The runner MUST record these pins in run provenance (see
[runner evidence artifacts](#contracted-runner-artifacts)).

### Atomic test identity

- `technique_id`: ATT&CK technique id (example: `T1059.001`)
- `engine_test_id`: Atomic test GUID (`auto_generated_guid`)

For v0.1 runner actions, `engine_test_id` MUST be present and MUST be used as the canonical Atomic
test identifier.

In v0.2+ plan compilation, the runner MUST compute a stable `template_id` for each Atomic action as:
`atomic/<technique_id>/<engine_test_id>`.

### Canonicalization token

`$ATOMICS_ROOT` is a literal token used only for **identity-bearing canonicalization**. It
represents environment-dependent Atomics payload roots and MUST NOT expand to a real path inside
identity-bearing materials.

## Contracted runner artifacts

The normative list of contracted runner evidence artifacts for `engine="atomic"` actions is defined
in [Contracted runner artifacts (normative)](#contracted-runner-artifacts-normative).

Action id semantics (normative):

- `action_id` is a run-scoped correlation key. It MUST be unique within the run and MUST NOT be used
  for cross-run comparisons.
- v0.1 (single-action atomic plans): implementations MUST emit legacy ordinal identifiers of the
  form `s<positive_integer>` (example: `s1`).
- v0.2+ (plan execution model): `action_id` MUST use the deterministic action instance id format
  defined in the data contracts spec (example shape: `pa_aid_v1_<32hex>`).

## Contracted runner artifacts (normative)

Runner evidence is stored under:

- Run-scoped runner evidence:

  - `runs/<run_id>/runner/principal_context.json` (required)

- Action-scoped runner evidence:

  - `runs/<run_id>/runner/actions/<action_id>/`

The following per-action files are RECOMMENDED by the storage formats spec and are REQUIRED by this
contract for `engine="atomic"` actions. Items marked "when ..." are feature-gated as noted:

- `executor.json` (required; execution metadata)
- `stdout.txt` and `stderr.txt` (required; process output transcripts)
- `cleanup_stdout.txt` and `cleanup_stderr.txt` (required when cleanup is invoked)
- `atomic_test_extracted.json` (required when `runner.atomic.template_snapshot.mode != off`)
- `atomic_test_source.yaml` (required when `runner.atomic.template_snapshot.mode = source`)
  - YAML bytes used for selection (post-fetch), written as UTF-8 (no BOM) with LF newlines
    (deterministically normalized).
- `resolved_inputs_redacted.json` (required; may be a deterministic placeholder when content is
  withheld or quarantined)
  - Redaction-safe resolved inputs object as defined in the data contracts spec.
  - MUST include `resolved_inputs_redacted` and `resolved_inputs_sha256` when content is present.
- `requirements_evaluation.json` (required when requirements evaluation is performed)
  - Summary MUST be copied into ground truth (see
    [Requirements evaluation](#requirements-evaluation)).
- `prereqs_stdout.txt` and `prereqs_stderr.txt` (required when prerequisite commands are executed)
- `side_effect_ledger.json` (required; append-only)
- `cleanup_verification.json` (required when cleanup verification is enabled)
- `state_reconciliation_report.json` (required when reconciliation is enabled)
- `attire.json` (required)
  - Structured execution record from ATTiRe / Attire-ExecutionLogger.
- `attire_import_report.json` (required when `attire.json` is imported)

All contract-backed JSON evidence artifacts under `runner/actions/<action_id>/` MUST include the
runner evidence JSON header pattern (`contract_version`, `run_id`, `action_id`, `action_key`,
`generated_at_utc`) and MUST validate against their corresponding schemas per the data contracts
spec.

### Synthetic correlation marker emission (optional; when enabled)

Goal: enable durable correlation of synthetic activity without heuristics (time windows, IP guess,
hostnames, etc.).

When synthetic correlation marker emission is enabled (normative requirements):

- For every action where `execute` is attempted, the runner MUST compute a deterministic marker
  value (v0.1 minimum):
  - `pa:synth:v1:<run_id>:<action_id>:execute`
  - `<run_id>` MUST equal the run's `manifest.run_id`.
  - `<action_id>` MUST equal the action's `ground_truth.action_id`.
- The runner MUST populate `ground_truth.extensions.synthetic_correlation_marker` with the marker
  value for every action where `execute` is attempted.
- The runner MUST attempt to emit at least one marker-bearing telemetry event per action at the
  start of `execute` (immediately before primary command invocation).
  - The emitted event MUST carry the marker value in a way that survives end-to-end ingestion and
    normalization into the OCSF envelope field
    `metadata.extensions.purple_axiom.synthetic_correlation_marker` (see the telemetry pipeline and
    data contracts specs).
- The runner MUST record the emission attempt as evidence:
  - it MUST append an `execute`-phase side-effect ledger entry describing the marker emission
    attempt before attempting emission, and
  - it MUST record whether emission was `success` or `failed` with a stable
    `reason_domain="side_effect_ledger"`, and `reason_code` when failed.

### Side-effect ledger population (normative, v0.1 minimum)

Goal: recovery correctness even if the run aborts mid-action.

- The runner MUST write `runs/<run_id>/runner/actions/<action_id>/side_effect_ledger.json` for each
  Atomic action where execution is attempted.
- The ledger MUST follow the side-effect ledger contract defined in the
  [data contracts spec](025_data_contracts.md) (append-only semantics, stable ordering, and
  lifecycle phase attribution).

Minimum viable population for v0.1:

- Runner-injected effects (synthetic correlation marker): when synthetic correlation marker emission
  is enabled, the runner MUST follow the requirements in
  [Synthetic correlation marker emission](#synthetic-correlation-marker-emission-optional-when-enabled),
  including appending an `execute`-phase ledger entry describing the emission attempt.
- Prerequisite fetch/install attempts: when prerequisites evaluation is enabled and the effective
  prerequisites mode executes `get_prereq_command`, the runner MUST append `prepare`-phase ledger
  entries for each `get_prereq_command` attempt as specified by
  [Prerequisites policy](#prerequisites-policy).
- Cleanup verification checks as expected reverted effects: when `cleanup_verification.json` is
  produced, the runner MUST append one `teardown`-phase ledger entry per cleanup verification result
  row.
  - Each such entry MUST include, at minimum, the `check_id` and the resulting `status`.
- Optional template-declared effects: when template snapshotting is enabled (see
  [Atomic template snapshot](#atomic-template-snapshot)), the runner MAY also append ledger entries
  representing deterministically extracted, template-declared effects.
  - Declared-effect entries MUST be in the `prepare` phase and MUST be explicitly marked as declared
    (not observed).
  - If extraction is ambiguous or non-deterministic, the runner MUST omit declared-effect entries.

### State reconciliation (optional; when enabled)

Goal: detect drift between the side-effect ledger (what the runner believes occurred) and the
environment's observed state at a defined reconciliation point.

When state reconciliation is enabled (normative requirements):

- The runner MUST read the action's `side_effect_ledger.json` and, when present,
  `cleanup_verification.json`.
- The runner MUST attempt to reconcile recorded effects against observed state using read-only
  probes by default (no target mutation during reconciliation).
- The runner MUST write a per-action reconciliation report to:
  - `runs/<run_id>/runner/actions/<action_id>/state_reconciliation_report.json`
- The report MUST conform to the state reconciliation report contract defined in the
  [data contracts spec](025_data_contracts.md).

Repair mode (reserved; policy-gated):

- Reconciliation MAY include an optional repair step only when all of the following are true:
  - the action's effective reconciliation policy is `repair`, and
  - repair is explicitly enabled by configuration (see config reference), and
  - the repair operation is allowlisted by policy.
- v0.1 implementations MUST NOT perform destructive repair as part of reconciliation.
  - If repair is requested (scenario policy or future config) but repair is not enabled/supported,
    the runner MUST NOT mutate the target and MUST record the blocked intent deterministically:
    - per-item `reason_code` SHOULD be `repair_blocked` for affected items in
      `state_reconciliation_report.json`, and
    - the run MUST account for the block via operability counters (see `110_operability.md`).
  - When repair is blocked and drift exists, the runner MUST surface drift via the reconciliation
    outputs (see ADR-0005 `runner.state_reconciliation` substage semantics).

Minimum v0.1 scope (normative):

- If `cleanup_verification.json` exists, the runner MUST include one reconciliation item per cleanup
  verification result row keyed by `check_id`.
- The runner MAY include additional reconciliation items derived from other ledger entries when the
  probe target is unambiguous and probing is permitted by policy.
- For any ledger-derived item that cannot be probed deterministically, the runner MUST emit the item
  with `status=skipped` (preferred) or `status=unknown`, and MUST set a stable
  `reason_domain="state_reconciliation_report"` and `reason_code`.

### State machine: Runner state reconciliation lifecycle

#### Purpose

- **What it represents**: The runner’s reconciliation lifecycle from per-action reconciliation
  results (`runner/actions/<action_id>/state_reconciliation_report.json`) to the run-level health
  substage `runner.state_reconciliation`, including the v0.1 report-status enum.
- **Scope**: run (derived from per-action reconciliation reports).
- **Machine ID**: `runner-state-reconciliation` (id_slug_v1)
- **Version**: `0.1.0`

This state machine is **runner-enforced** and **fixture-backed** in v0.1.

#### Lifecycle authority references

- Scenarios spec:
  - State reconciliation policy (per action): enablement, sources precedence, repair requested but
    not supported in v0.1 (`030_scenarios.md`).
- This document:
  - State reconciliation (optional; when enabled): minimum v0.1 report population, item-level
    requirements, repair blocking behavior.
- ADR-0005: Stage outcomes and failure classification:
  - State reconciliation policy and deterministic health-substage selection.
- Operability spec:
  - Required `runner.state_reconciliation` health substage behavior and counters.
- Test strategy and CI:
  - Reconciliation fixtures are treated as state-machine conformance fixtures.

If this state machine conflicts with the linked lifecycle authority, the linked lifecycle authority
is authoritative.

#### Entities and identifiers

- **Machine instance key**: `run_id`

- **Per-action report key**: `action_id`

- **Eligibility predicate** (deterministic):

  An action is **reconciliation-eligible** for this machine if:

  - effective reconciliation is enabled by runner config, and
  - the action’s effective reconciliation policy is not `none`.

#### Report status enum

Each reconciliation-eligible action MUST emit exactly one top-level reconciliation report:
`runner/actions/<action_id>/state_reconciliation_report.json`.

For v0.1, `state_reconciliation_report.status` is a closed string enum:

| Value            | Meaning (v0.1)                                                                                        |
| ---------------- | ----------------------------------------------------------------------------------------------------- |
| `clean`          | Reconciliation completed deterministically and no drift was detected for any probed item.             |
| `drift_detected` | One or more items were probed and at least one drift condition was detected.                          |
| `unknown`        | No drift was detected, but one or more items had an indeterminate outcome (for example: probe error). |
| `skipped`        | No drift was detected and reconciliation was skipped for all items (policy-gated or non-probeable).   |

Deterministic status derivation (normative):

- The runner MUST compute the top-level `status` from the set of item outcomes with the following
  precedence (highest to lowest):

  1. `drift_detected`
  1. `unknown`
  1. `skipped`
  1. `clean`

- If an action has zero reconciliation items after applying the effective sources and policy, the
  runner MUST set `status="skipped"`.

Top-level `reason_code` conventions (normative):

- When `status="drift_detected"`, the report MUST include a deterministic top-level
  `reason_code="drift_detected"`.
- The report MUST reserve `reason_code="reconcile_failed"` for cases where the runner cannot produce
  a deterministic, contract-valid reconciliation report for an eligible action.
  - If `reason_code="reconcile_failed"` is emitted, the report MUST set `status="unknown"`.

#### States

Run-level states (closed set for v0.1):

| State                     | Kind     | Description                                                                   |
| ------------------------- | -------- | ----------------------------------------------------------------------------- |
| `not_applicable`          | terminal | No reconciliation-eligible actions exist (or reconciliation is disabled).     |
| `collecting`              | initial  | Reconciliation is enabled and the runner is emitting per-action reports.      |
| `success`                 | terminal | Reports complete; no action report indicates drift or reconcile failure.      |
| `failed_drift_detected`   | terminal | At least one action report indicates drift; none indicates reconcile failure. |
| `failed_reconcile_failed` | terminal | At least one action report indicates `reason_code="reconcile_failed"`.        |

#### Events and transitions

| From state       | Event                         | Guard (deterministic)                                           | To state               |
| ---------------- | ----------------------------- | --------------------------------------------------------------- | ---------------------- |
| `collecting`     | `event.action_report_written` | A contract-valid `state_reconciliation_report.json` is written. | `collecting`           |
| `collecting`     | `event.aggregate_computed`    | All reconciliation-eligible actions have emitted a report.      | `success` / `failed_*` |
| `not_applicable` | N/A                           | Reconciliation disabled or no eligible actions.                 | `not_applicable`       |

Aggregate computation (normative):

When computing the aggregate, the runner MUST apply the following deterministic precedence:

1. If any action report has `reason_code="reconcile_failed"`, aggregate state MUST be
   `failed_reconcile_failed`.
1. Else if any action report has `status="drift_detected"`, aggregate state MUST be
   `failed_drift_detected`.
1. Else aggregate state MUST be `success`.

#### Health substage mapping

When the aggregate state is computed, the runner MUST record the run-level health substage
`stage="runner.state_reconciliation"` as follows (see ADR-0005 and operability):

- If aggregate state is `failed_reconcile_failed`:
  - `status="failed"`
  - `reason_code="reconcile_failed"`
- Else if aggregate state is `failed_drift_detected`:
  - `status="failed"`
  - `reason_code="drift_detected"`
- Else if aggregate state is `success`:
  - `status="success"`
  - `reason_code` MUST be omitted

If reconciliation is `not_applicable`, the runner SHOULD omit the `runner.state_reconciliation`
substage entry.

#### Observability

When reconciliation is enabled (i.e., there exists at least one reconciliation-eligible action), the
runner MUST emit:

- per-action reconciliation reports under
  `runner/actions/<action_id>/state_reconciliation_report.json`
- the run-level health substage `runner.state_reconciliation` as above
- deterministic counters as defined by the operability spec:
  - `runner_state_reconciliation_items_total`
  - `runner_state_reconciliation_drift_detected_total`
  - `runner_state_reconciliation_skipped_total`
  - `runner_state_reconciliation_unknown_total`
  - `runner_state_reconciliation_probe_error_total`
  - `runner_state_reconciliation_repairs_attempted_total`
  - `runner_state_reconciliation_repairs_succeeded_total`
  - `runner_state_reconciliation_repairs_failed_total`
  - `runner_state_reconciliation_repair_blocked_total`

#### Conformance tests

Conformance fixtures for this machine live under `tests/fixtures/runner/state_reconciliation/` (see
`100_test_strategy_ci.md`).

The fixture set MUST include, at minimum:

- `record_present_reality_absent` (drift detected)
- `record_absent_reality_present` (drift detected)
- `observe_only_drift_detected` (drift detected; no repair attempted)
- `clean_match` (clean)
- `repair_requested_but_blocked` (repair intent blocked; drift surfaced)

For each fixture where reconciliation is enabled, the harness MUST assert:

- the per-action report `status` matches the expected enum value, and
- the run-level `runner.state_reconciliation` health substage matches the mapping above.

## Atomic YAML parsing

### Technique discovery

Given a technique id `technique_id`, the runner MUST locate the Atomic YAML source as:

- `atomics/<technique_id>/<technique_id>.yaml`

If the file does not exist, the runner MUST fail closed for the action with reason code
`atomic_yaml_not_found`.

### YAML parser requirements

The runner MUST parse Atomic YAML using a pinned implementation (as part of the reference executor).
Parsing MUST be deterministic for equivalent input bytes.

The parser MUST extract, at minimum, for each Atomic test:

- `technique_id` (from the technique selection context)
- `engine_test_id` = `auto_generated_guid`
- `name`
- `description` (if present)
- `supported_platforms` (if present)
- `executor.name` (executor type)
- `executor.command` (one or more command strings)
- `executor.cleanup_command` (optional, one or more command strings)
- `input_arguments` (optional object; keys and per-key `default` values when present)

If `auto_generated_guid` is missing or empty, the runner MUST fail closed with reason code
`missing_engine_test_id` unless the action is configured as `warn_and_skip` (in which case it MUST
emit `skipped` with reason code `missing_engine_test_id`).

### Atomic template snapshot

The runner MAY snapshot the Atomic test template material used for an action into the run bundle so
run review does not require a local checkout of the Atomic Red Team repository.

Config gate (normative):

- `runner.atomic.template_snapshot.mode` (string enum; v0.1 default: `off`)

Allowed values:

- `off`: do not write template snapshot artifacts.
- `extracted`: write `atomic_test_extracted.json` only.
- `source`: write both `atomic_test_extracted.json` and `atomic_test_source.yaml`.

Requirements (normative):

- When `runner.atomic.template_snapshot.mode` is `extracted` or `source`, the runner MUST write
  `atomic_test_extracted.json` for the selected Atomic test before attempting execution or
  prerequisites evaluation.
- When `runner.atomic.template_snapshot.mode` is `source`, the runner MUST also write
  `atomic_test_source.yaml` containing the YAML bytes for the selected Atomic test after newline
  normalization to LF.

Snapshot artifact paths:

- `runs/<run_id>/runner/actions/<action_id>/atomic_test_extracted.json`
- `runs/<run_id>/runner/actions/<action_id>/atomic_test_source.yaml` (mode=`source`)

`atomic_test_extracted.json` contents (minimum):

- `technique_id`
- `engine_test_id`
- `source_relpath` (example: `atomics/T1059.001/T1059.001.yaml`)
- `source_sha256` (sha256 of the exact bytes written to `atomic_test_source.yaml` when present;
  otherwise sha256 of the YAML bytes after deterministic newline normalization to LF)
- `name`
- `description` (if present)
- `supported_platforms` (if present)
- `executor` object:
  - `name`
  - `command` (list of strings; normalized per
    [Command list normalization](#command-list-normalization))
  - `cleanup_command` (optional list of strings; normalized per
    [Command list normalization](#command-list-normalization))
- `input_arguments` (optional object; keys and per-key `default` values when present)
- `dependencies` (optional array in YAML order), each with:
  - `description` (string or null)
  - `prereq_command` (list of strings; normalized per
    [Command list normalization](#command-list-normalization))
  - `get_prereq_command` (list of strings; normalized per
    [Command list normalization](#command-list-normalization))

Template snapshot scope:

- The runner MUST NOT perform input placeholder substitution when writing the snapshot artifacts.
  Snapshot artifacts represent the Atomic template, not the resolved command material.

Determinism requirements:

- Arrays MUST preserve YAML order.
- `atomic_test_extracted.json` MUST be serialized as RFC 8785 canonical JSON (JCS) bytes (UTF-8, no
  BOM, no trailing newline).
- `atomic_test_source.yaml` MUST be UTF-8 (no BOM) with LF newlines.

### Command list normalization

Atomic YAML may express commands as a scalar string or as a list. The runner MUST normalize both
`executor.command` and `executor.cleanup_command` into a list of strings. If `dependencies` are
present, the runner MUST also normalize `dependencies[].prereq_command` and
`dependencies[].get_prereq_command` into lists of strings using the same rules.

Normalized command-bearing fields (when present) MUST preserve list order exactly:

- If scalar, normalize to a single-element list.
- If list, preserve list order exactly.
- Empty strings MUST be rejected (fail closed with reason code `empty_command`).

### Supported platform gate (normative)

If `supported_platforms` is present in Atomic YAML, the runner MUST treat it as a platform
requirement input to requirements evaluation.

If the target OS family (from the run-scoped inventory snapshot) is not included in
`supported_platforms`, the runner MUST:

- record the unmet platform requirement in both:
  - `requirements_evaluation.json`, and
  - the action’s `requirements` object in `ground_truth.jsonl` (per data contracts spec)
- set the action `prepare` phase `phase_outcome=skipped` with `reason_code=unsupported_platform`
- MUST NOT attempt prerequisites evaluation or `execute` for the action

### Action requirements (permissions and environment assumptions)

Scenarios MAY declare machine-readable action requirements (see the
[scenario model spec](030_scenarios.md)). For v0.1 (single-action plans), the requirements override
field is `plan.requirements`.

The runner MUST compute an **effective requirements** object for each `engine = "atomic"` action.
The effective object is used for:

- deterministic preflight gating during `prepare`
- deterministic action identity (via the resolved inputs hash; see
  [Resolved inputs hash](#resolved-inputs-hash))

#### Effective requirements sources and precedence (normative)

Effective requirements are derived from two sources, with field-level precedence:

1. Scenario overrides (`plan.requirements` in v0.1; `actions[].requirements` in v0.2+)
1. Template-derived requirements from the Atomic template snapshot (`atomic_test_extracted.json`)

Field-level precedence: if an override field is present, it replaces the derived field.

#### Derivation rules (minimum, normative)

Platform:

- If `supported_platforms` is present, the runner MUST set `requirements.platform.os` to the
  lowercased, de-duplicated list of OS families from `supported_platforms`, sorted ascending.

Tools:

- The runner MUST include at least one tool token derived from `executor.name` using this mapping:
  - `powershell` -> `powershell`
  - `command_prompt` -> `cmd`
  - `sh` -> `sh`
  - `bash` -> `bash`
  - `python` -> `python`
- Additionally, the runner MAY derive tool tokens from dependency command strings using a bounded,
  versioned matcher set. When enabled, matches MUST be case-insensitive and based on literal
  substring checks (no regex), with the following minimum mappings:
  - `curl` -> `curl`
  - `wget` -> `wget`
  - `bitsadmin` -> `bitsadmin`
  - `certutil` -> `certutil`
  - `invoke-webrequest` -> `invoke_webrequest`
- Any unrecognized `executor.name` MUST result in a derived tools token `unknown_executor` and MUST
  be recorded as a derivation warning in action evidence.

Privilege:

- The runner MUST NOT attempt to infer privilege from Atomic YAML in v0.1. If no scenario override
  is present, `requirements.privilege` MUST be omitted.

#### Canonical form (normative)

For identity-bearing materials, the effective requirements object MUST be canonicalized:

- `platform.os` and `tools` arrays MUST be lowercased, de-duplicated, and sorted lexicographically.
- Empty arrays MUST be omitted.
- If present, `privilege` MUST be one of: `user | admin | system`.

#### Identity embedding into resolved inputs (normative)

Principal alias embedding (normative):

- The runner MUST include the effective principal alias used for the action in the identity-bearing
  resolved inputs map prior to redaction and hashing by adding a reserved top-level key:
  - `__pa_principal_alias_v1`: <effective principal alias string>
- This injection MUST occur even when the effective requirements object is empty.
- The effective principal alias is selected per the scenario model:
  - v0.1: `plan.execution.principal_alias` (or the runner default when absent)
  - v0.2+: `actions[].execution.principal_alias` (or the runner default when absent)

Requirements embedding (normative):

When the effective requirements object is non-empty, the runner MUST include it in the
identity-bearing resolved inputs map prior to redaction and hashing by adding a reserved top-level
key:

- `__pa_action_requirements_v1`: <effective requirements object>

Reserved key collision handling:

- If the scenario input map already includes the reserved key `__pa_principal_alias_v1` or
  `__pa_action_requirements_v1`, the runner MUST fail closed with
  `reason_code=reserved_input_key_collision`.

## Target resolution and remote execution

This section defines how the runner turns `target_asset_id` into a concrete connection address for
`engine = "atomic"` actions.

### Inventory snapshot consumption

For any `engine = "atomic"` action, the runner MUST resolve `target_asset_id` using the run-scoped
inventory snapshot produced by the lab provider stage (see the
[lab providers spec](015_lab_providers.md)).

Source of truth (v0.1):

- Source of truth for target resolution is `runs/<run_id>/logs/lab_inventory_snapshot.json` (see
  architecture spec and lab provider spec).

Resolution rules:

- Locate the target asset in the inventory snapshot `assets[]` where `asset_id == target_asset_id`.
- The runner MUST use `asset.os` (lowercased) as the target OS family input for supported-platform
  checks and requirements evaluation.
- If `asset.ip` is present and non-empty, set `connection_address = asset.ip`.
- Else if `asset.hostname` is present and non-empty, set `connection_address = asset.hostname`.
- Else fail closed with `reason_code = target_connection_address_missing`.

The runner SHOULD populate `resolved_target.hostname`, `resolved_target.ip`, and
`resolved_target.provider_asset_ref` in `ground_truth.jsonl` from the inventory snapshot per
scenario model spec.

Determinism requirements:

- The `connection_address` selection MUST follow the fixed precedence above.
- The runner MUST NOT consult environment variables or provider APIs to resolve `connection_address`
  at execution time.
- `connection_address` is evidence-only and MUST NOT contribute to `action_key` or identity-bearing
  hashes.

### Invoke-AtomicRedTeam remote mapping

For remote execution, the runner MUST translate `connection_address` into a PowerShell remoting
session and then execute `Invoke-AtomicTest` within that session.

Normative v0.1 transport (cross-platform): SSH-based PowerShell remoting:

- The runner MUST create a `PSSession` using the SSH transport parameter set:
  - `New-PSSession -HostName <connection_address> [-UserName <user>] [-Port <port>] [-KeyFilePath <key_path>]`
- The runner SHOULD derive `user` and `port` from allowlisted inventory `vars` when present:
  - `vars.ansible_user` -> `-UserName`
  - `vars.ansible_port` -> `-Port`
- If session creation requires user interaction (for example, a password prompt or host-key trust
  prompt), the runner MUST fail closed with `reason_code=interactive_prompt_blocked`.

Optional transport: WSMan/WinRM (explicit enable; runner-host support required):

- Implementations MAY support WSMan/WinRM sessions when explicitly enabled and when the runner host
  supports WSMan.
- When WSMan is used, `connection_address` MUST map to
  `New-PSSession -ComputerName <connection_address>`.

The created `PSSession` MUST be passed to `Invoke-AtomicTest` via `-Session <PSSession>`.

If a remoting session cannot be created, the runner MUST fail closed with reason code
`executor_invoke_error` (and SHOULD include error details in `stderr.txt` and `executor.json`).

## Input resolution

### Input resolution precedence

Input resolution MUST follow this precedence (highest to lowest):

1. Runner-supplied overrides (`-InputArgs` or an equivalent non-interactive injection mechanism)
1. YAML defaults (`input_arguments.<name>.default`)

Interactive prompting MUST NOT be used for unattended automation:

- The runner MUST NOT enable or rely on `-PromptForInputArgs`.
- If Invoke-AtomicRedTeam attempts to prompt due to missing required inputs, the runner MUST treat
  this as a failure and MUST fail closed with reason code `interactive_prompt_blocked`.

### Required inputs without defaults

If an input argument key exists in YAML but has no `default` value:

- The runner MUST require an override value.
- If no override is provided, the runner MUST fail closed with reason code `missing_required_input`.

### Template expansion rules

Template placeholders use the Atomic convention:

- Placeholder form: `#{<name>}`

The runner MUST perform placeholder substitution using the resolved input map:

- Substitution MUST be exact-match by placeholder name.
- Placeholder names MUST be treated as case-sensitive.
- The runner MUST validate that all placeholders used in `executor.command` and
  `executor.cleanup_command` (and, when present, `dependencies[].prereq_command` and
  `dependencies[].get_prereq_command`) reference keys present in the resolved input map.
  - If any placeholder cannot be resolved, the runner MUST fail closed with reason code
    `unresolved_placeholder`.

### Resolved input fixed point

Resolved inputs MAY reference other inputs (example: a default value containing `#{other_arg}`).

To produce `resolved_inputs` deterministically, the runner MUST apply a fixed-point expansion:

1. Start from the precedence-merged input map (`merged_inputs`).
1. Iteratively substitute placeholders inside input values using the current map, until:
   - no value changes, or
   - `max_resolution_passes` is reached (v0.1 default: 8 passes)
1. If `max_resolution_passes` is reached and values are still changing, the runner MUST fail closed
   with reason code `input_resolution_cycle_or_growth`.

This algorithm MUST be deterministic for the same YAML bytes and the same override object.

### Canonicalization of environment-dependent Atomics paths

Environment-dependent expansions MUST NOT participate in identity-bearing hashing.

For v0.1, the following expansions MUST be treated as evidence-only:

- `PathToAtomicsFolder`
- `$PathToPayloads` (and equivalent payload-root tokens used by Invoke-AtomicRedTeam)

When computing identity-bearing materials (including `parameters.resolved_inputs_sha256`), the
runner MUST canonicalize occurrences of these expansions by replacing them with the literal token:

- `$ATOMICS_ROOT`

This canonicalization applies to:

- resolved input values, and
- the canonical expanded command material (see
  [Canonical expanded command boundary](#canonical-expanded-command-boundary))

The runner MUST record the actual expanded Atomics root path used for execution in `executor.json`
as evidence (see [Executor evidence file](#executor-evidence-file)).

## Identity-bearing hashes and command materials

### Resolved inputs hash

Goal: stable `action_key` identity and downstream joins.

`parameters.resolved_inputs_sha256` MUST be computed as specified in the data contracts spec:

- `"sha256:" + sha256_hex(canonical_json_bytes(resolved_inputs_redacted_canonical))`

Where `resolved_inputs_redacted_canonical` is the resolved input map after:

- Default resolution
- Runner-supplied overrides
- Principal alias embedding (reserved key injection)
- Requirements embedding (reserved key injection, when non-empty)
- Deterministic redaction
- Canonical JSON serialization (RFC 8785)

Redaction for hashing:

- Before hashing resolved_inputs, the runner MUST apply deterministic redaction to the resolved
  inputs object per [ADR-0003](../adr/ADR-0003-redaction-policy.md).
- Plaintext secrets MUST NOT be stored. Secrets in resolved_inputs MUST be redacted
  deterministically or replaced with deterministic references.
- When redaction is enabled, the runner MUST record the redaction policy version and a
  redaction_summary object into `executor.json` (see
  [Redaction status in executor.json](#redaction-status-in-executorjson)).

Resolved inputs evidence artifact (schema-backed; required):

The runner MUST write a `resolved_inputs_redacted.json` artifact for each `engine="atomic"` action.
When resolved inputs content can be made redaction-safe deterministically, the artifact MUST
include:

- `resolved_inputs_redacted`: object (the redacted canonical object used for hashing)
- `resolved_inputs_sha256`: string (`sha256:<hex>` form) corresponding to
  `parameters.resolved_inputs_sha256`

Otherwise, the runner MUST still write this file as a deterministic placeholder artifact.

### Redaction for hashing

Before hashing `resolved_inputs`, the runner MUST apply deterministic redaction per the
[redaction policy ADR](../adr/ADR-0003-redaction-policy.md):

- plaintext secrets MUST NOT be stored in run bundles
- secrets in `resolved_inputs` MUST be:
  - redacted deterministically, or
  - replaced with deterministic references (example: `secretref:<stable_id>`)

When redaction is enabled, the runner MUST record redaction provenance in ground truth extensions as
described in the [data contracts spec](025_data_contracts.md) and MUST ensure the run manifest
includes:

- `redaction_policy_id`
- `redaction_policy_version`
- `redaction_policy_sha256`

### Canonical expanded command boundary

To support operator debugging and cross-run comparability, the runner MUST compute and record a
**canonical expanded command** for both execution and cleanup:

- Boundary: command strings after placeholder substitution, but before executor-specific shell
  rewriting.

The runner MUST record:

- `command_post_merge` (list of strings, in order)
- `cleanup_command_post_merge` (list of strings, in order, if cleanup exists)

These command lists MUST apply `$ATOMICS_ROOT` canonicalization, as described in
[Canonicalization of environment-dependent Atomics paths](#canonicalization-of-environment-dependent-atomics-paths).

These command lists MUST be recorded as evidence and MUST NOT be used as part of `action_key` unless
explicitly added to the action identity contract in the [scenario model spec](030_scenarios.md).

### Command integrity hash compatibility

The [data contracts spec](025_data_contracts.md) defines `extensions.command_sha256` as an OPTIONAL
integrity hash computed over a canonical `{executable, argv_redacted, ...}` object.

This document does not redefine that field.

If the runner emits an integrity hash for the canonical expanded command strings (see
[Canonical expanded command boundary](#canonical-expanded-command-boundary)), it SHOULD use a
separate field name to avoid conflicting semantics (example: `extensions.command_post_merge_sha256`)
and MUST document the basis object and redaction behavior.

### Principal context and action attribution (normative)

The runner MUST record the principal identity context used during the run as a schema-backed
runner-evidence artifact:

- Artifact: `runs/<run_id>/runner/principal_context.json`
- Schema: `docs/contracts/principal_context.schema.json`

When `runner.identity.emit_principal_context=true` (default), the runner MUST:

- Emit `runner/principal_context.json` exactly once per run.
- Populate `principals[]` in stable order.
  - Stable ordering rule: sort by `principal_id` ascending.
- Populate `action_principal_map[]` mapping each action to a `principal_id`.
  - The map MUST include exactly one entry for each `action_id` present in this run's
    `ground_truth.jsonl`, including actions that are skipped before `execute`.
  - The map MUST NOT omit actions. When a principal cannot be asserted safely, the mapping MUST
    reference a principal entry whose `kind=unknown`.
  - Stable ordering rule: sort by `action_id` ascending.

When `runner.identity.emit_principal_context=false`, the runner MUST NOT emit
`runner/principal_context.json` and MUST NOT populate `extensions.principal_id` in action ground
truth.

The runner MUST NOT assume the principal is user-shaped. Implementations MUST support:

- `kind=unknown` when the principal cannot be safely asserted, and
- a non-empty `assertion_source` for each principal describing how the principal was derived (or why
  it is unknown), per the contract schema.

Ground truth linkage (normative):

- When `runner.identity.emit_principal_context=true` and the resolved principal is known, the runner
  SHOULD populate action ground truth `extensions.principal_id` with the corresponding mapped
  `principal_id`.

Safety constraints (normative):

- `principal_context.json` MUST NOT contain secrets (credentials, tokens, private keys, session
  cookies).
- If identity details cannot be represented safely, the runner MUST prefer `kind=unknown` with an
  explicit `assertion_source` over storing raw identifiers.

### Identity probing constraints (normative)

If the runner performs identity probing (for example, to derive or refine principal attribution),
then probes:

- MUST be endpoint-only and local by default.
  - Probes MUST NOT perform network calls (no domain queries, no directory lookups, no cloud API
    calls).
- MUST be read-only and MUST NOT mutate target or runner state.
- MUST NOT capture or store secrets.
- MUST store only a redaction-safe summary or a hash-derived fingerprint.
  - If a fingerprint is recorded, it MUST be computed from a canonical JSON form (for example RFC
    8785 JCS) and a cryptographic hash (for example SHA-256), and MUST NOT be reversible into raw
    identity strings.

Deterministic probe observability (normative):

- Implementations MUST record whether probing was attempted and its outcome deterministically in
  runner evidence.

Config binding (normative):

- If `runner.identity.probe_enabled=false`, the runner MUST NOT perform identity probing beyond
  baseline information already available without additional collection steps.
- If `runner.identity.probe_enabled=true`, probes MUST still obey the constraints above
  (endpoint-only and local by default, read-only, no secrets) and the runner MUST record
  probe-attempt status in runner evidence deterministically.
- If `runner.identity.probe_detail=none`, the runner MUST NOT emit probe summaries or hash-derived
  fingerprints. If `runner.identity.probe_detail=summary`, the runner MAY emit a redaction-safe
  summary and/or a hash-derived fingerprint (as constrained above).

## Prerequisites and dependencies

Atomic tests MAY declare prerequisites via a `dependencies` block. Each dependency commonly
includes:

- `prereq_command`: a command that checks whether a prerequisite is satisfied
- `get_prereq_command`: a command that attempts to satisfy the prerequisite (often by downloading or
  creating payloads)

### Runner runtime dependency immutability (normative)

The runner MUST NOT update or mutate its own runtime dependencies during a run (for example:
module/library self-updates, package-manager upgrades, `git pull` on tool sources, dynamic plugin
installs).

- The runner MUST execute using a pre-resolved and pinned dependency set.
- If a required runner-side dependency is missing or incompatible, the runner MUST fail closed
  rather than attempting an on-the-fly update to satisfy it.

If configuration includes a knob that would permit runtime self-updates (for example,
`runner.dependencies.allow_runtime_self_update`), the v0.1 runner MUST reject configurations that
set `runner.dependencies.allow_runtime_self_update=true` as part of runner configuration validation
(before any action `prepare` begins).

- The runner MUST fail the run without attempting action execution.
- The runner MUST record the rejection as a failed stage outcome per ADR-0005.
- The runner SHOULD use a stable reason code. RECOMMENDED: `disallowed_runtime_self_update`.

### Requirements evaluation (prepare) (normative)

Before running any prerequisites commands, the runner MUST evaluate the effective requirements
object for the action using only read-only probes.

Config policy:

- `runner.atomic.requirements.fail_mode`:
  - `fail_closed` (default): unknown requirement checks MUST be treated as unsatisfied for gating.
  - `warn_and_skip`: unknown requirement checks MUST remain `unknown` in evidence, but the action
    MUST still be skipped with `reason_domain="requirements_evaluation"` and
    `reason_code=requirement_unknown`.

Evidence requirements (v0.1):

- The runner MUST write a schema-backed requirements evaluation artifact to:
  - `runs/<run_id>/runner/actions/<action_id>/requirements_evaluation.json`
- The runner MUST copy `requirements.declared`, `requirements.evaluation`, and
  `requirements.results[]` into the corresponding `ground_truth.jsonl` row (per the data contracts
  spec).
- When `requirements_evaluation.json` is produced, the runner MUST attach
  `evidence.requirements_evaluation_ref` to the `prepare` phase record in ground truth (per the data
  contracts spec).

Minimum checks:

- Platform check: target asset OS family (from inventory snapshot `assets[].os`) is one of
  `requirements.platform.os` (and, when present, satisfies Atomic `supported_platforms`).
- Tool check: each required tool is present on target (or on runner if local execution).
- Privilege check: principal satisfies requested privilege level (admin/root/sudo).
- Unknown: If any requirement cannot be evaluated deterministically, mark that check as `unknown`.

Determinism requirements:

- `requirements.declared` MUST be canonicalized:
  - arrays MUST be lowercased, de-duplicated, and sorted lexicographically
  - empty arrays MUST be omitted
- `requirements.results[]` MUST be ordered deterministically by the tuple `(kind, key)` using UTF-8
  byte order (no locale).

Evaluation semantics:

- `requirements.evaluation = satisfied` iff all checks are `satisfied`.
- `requirements.evaluation = unsatisfied` if any check is `unsatisfied`, OR if any check is
  `unknown` and `runner.atomic.requirements.fail_mode=fail_closed`.
- `requirements.evaluation = unknown` only when at least one check is `unknown`, no check is
  `unsatisfied`, and `runner.atomic.requirements.fail_mode=warn_and_skip`.

Ground-truth gating:

- If `requirements.evaluation != satisfied`, the runner MUST set the `prepare` phase
  `phase_outcome=skipped` and MUST NOT attempt `execute`.

Reason code mapping (minimum; deterministic):

- Determine the action-level `prepare.reason_code` by selecting the first requirement result (after
  deterministic ordering) whose `status != satisfied`:
  - If `status=unknown`, use `reason_domain="requirements_evaluation"` and
    `reason_code=requirement_unknown`.
  - Else map `kind` to a reason code:
    - `platform` -> `unsupported_platform`
    - `privilege` -> `insufficient_privileges`
    - `tool` -> `missing_tool`

### Responsibility model (normative)

- The runner MUST be capable of executing Atomic prerequisites for the selected test when
  `dependencies` are present.
- Lab Providers MAY pre-bake prerequisites into images, but the integration contract MUST NOT rely
  on pre-baking as the only mechanism.
- If prerequisites are not satisfied (and cannot be satisfied per policy), the runner MUST NOT
  attempt the Atomic execution and MUST fail closed for the action with a stable prereq reason code
  (see below).

### Prerequisites policy

The runner MUST support the following prerequisite evaluation modes for Atomic dependencies:

- `runner.atomic.prereqs.mode`:
  - `check_only`: run prerequisite checks, never install
  - `check_then_get`: run checks, if missing then run get commands
  - `get_only`: run get commands, then run checks if present

Default: `check_only` (safe by default).

Per dependency evaluation order:

- Sort dependencies by their index order in Atomic YAML.
- For each dependency:
  - If `prereq_command` exists, run it and capture stdout/stderr.
  - If `get_prereq_command` exists and mode allows get, run it only if prereq check fails.

Failure behavior:

- If any dependency check fails and mode does not allow "get", treat prerequisites as unsatisfied
  and skip execution with `reason_code = prereq_unsatisfied`.
- If any `get_prereq_command` fails (non-zero exit or cannot execute), fail closed with
  `reason_code = prereq_get_failed`.
- If prerequisite commands cannot be run deterministically (interactive prompt), fail closed with
  `reason_code = interactive_prompt_blocked`.

Determinism requirements:

- The effective mode MUST be recorded in `executor.json`.
- Dependency processing order MUST match the YAML `dependencies[]` order exactly.
- Command normalization, input placeholder substitution, and `$ATOMICS_ROOT` canonicalization MUST
  be applied consistently to prerequisite commands using the same rules as for execution and cleanup
  commands.

Side-effect ledger recording (normative):

The runner MUST treat `get_prereq_command` execution as a target-mutating side effect.

- For each attempt to execute `get_prereq_command`, the runner MUST append side-effect ledger
  entries attributable to the `prepare` phase with `effect_type="prereq_install"`.
  - A write-ahead entry MUST be appended and flushed immediately before executing
    `get_prereq_command`.
  - A completion entry MUST be appended after the `get_prereq_command` attempt completes.
- Each `prereq_install` entry MUST include all contract-required fields, plus:
  - `phase="prepare"`
  - `effect_type="prereq_install"`
  - `dependency_index` (1-based index into `dependencies[]`)
  - an outcome field with one of: `attempted | succeeded | failed | blocked`

### Prerequisites execution algorithm (normative)

When prerequisites are evaluated (When `dependencies` are present and the runner performs prereq
check/get per `runner.atomic.prereqs.mode`):

1. For each dependency `d` in `dependencies[]` (in order):
   1. Execute the normalized `d.prereq_command` after placeholder substitution.
   1. If the prereq command indicates success (exit code `0`), mark the dependency `met` and
      continue.
   1. If the prereq command indicates failure (non-zero exit code):
      - If the effective mode does not include `get`, mark dependency `missing` and continue.
      - If the effective mode includes `get`:
        1. If `d.get_prereq_command` is missing or empty, the runner MUST fail closed with reason
           code `prereq_get_command_missing`.
        1. Execute the normalized `d.get_prereq_command` after placeholder substitution.
        1. Re-execute `d.prereq_command` (same rules as above).
        1. If re-check succeeds, mark dependency `met_after_get`; otherwise mark `missing`.
1. If any dependency is `missing`, the runner MUST NOT attempt the Atomic execution and MUST fail
   closed for the action with reason code `prereq_unsatisfied`.

Failure classification (normative):

- If a prereq check command cannot be executed (transport failure, timeout, runner internal error),
  the runner MUST fail closed with reason code `prereq_check_failed`.
- If a get prereq command cannot be executed (transport failure, timeout, runner internal error),
  the runner MUST fail closed with reason code `prereq_get_failed`.

### Prerequisites logs and evidence artifacts

When prerequisites are evaluated (`dependencies` present), the runner MUST write:

- `runs/<run_id>/runner/actions/<action_id>/prereqs_stdout.txt`
- `runs/<run_id>/runner/actions/<action_id>/prereqs_stderr.txt`

These files MUST follow the same encoding/newline and redaction rules as other transcripts (see
[Stdout and stderr transcript files](#stdout-and-stderr-transcript-files) and
[Redaction of transcripts](#redaction-of-transcripts)).

To keep prereq logs machine-checkable and deterministic, the runner SHOULD prefix each prerequisite
command attempt with a delimiter line appended to `prereqs_stdout.txt`:

- `==> prereq[<i>/<n>] <phase>: <description>`

Where:

- `<i>` is 1-based index into `dependencies[]`
- `<n>` is total count of dependencies
- `<phase>` is one of `check`, `get`, `recheck`
- `<description>` is the dependency `description` after placeholder substitution (or a stable
  placeholder if absent)

### Executor evidence requirements (prereqs)

When prerequisites are evaluated, `executor.json` MUST include a `prereqs` object with, at minimum:

- `mode` (string; effective mode)
- `dependencies_count` (integer)
- `status` (`skipped | satisfied | unsatisfied | error`)
- `dependencies` (array in YAML order), each with:
  - `index` (1-based integer)
  - `description` (string; substituted)
  - `check_exit_code` (integer)
  - `get_attempted` (boolean)
  - `get_exit_code` (integer or null)
  - `recheck_exit_code` (integer or null)
  - `status` (`met | met_after_get | missing | error`)

## Transcript capture and storage

### Structured execution record (ATTiRe)

The runner MUST enable `Attire-ExecutionLogger` for Invoke-AtomicRedTeam executions and MUST capture
the structured output as an evidence artifact.

Storage requirement:

- The runner MUST store a per-action copy at:
  - `runs/<run_id>/runner/actions/<action_id>/attire.json`

Normalization requirement:

- The stored `attire.json` MUST be UTF-8 (no BOM) with LF newlines.
- If the upstream logger produces different newlines, the runner MUST normalize them
  deterministically when copying.

### Stdout and stderr transcript files

Transcript capture is controlled by:

- `runner.atomic.capture_transcripts` (boolean)

When `runner.atomic.capture_transcripts = true`, the runner MUST capture transcripts for:

- prerequisites evaluation (check/get)
- execution
- cleanup invocation

Transcript files MUST be stored per-action:

- `stdout.txt` and `stderr.txt` for execution
- `prereqs_stdout.txt` and `prereqs_stderr.txt` for prerequisites
- `cleanup_stdout.txt` and `cleanup_stderr.txt` for cleanup invocation

When transcript artifacts exist, the runner MUST attach the corresponding ground-truth evidence
pointers per the data contracts spec (example: `evidence.stdout_ref`, `evidence.stderr_ref`,
`evidence.cleanup_stdout_ref`, `evidence.cleanup_stderr_ref`).

When `runner.atomic.capture_transcripts = false`, the runner MUST NOT write transcript files into
the run bundle.

Encoding and newline requirements (deterministic):

- Files MUST be UTF-8 without BOM.
- Newlines MUST be normalized to LF (`\n`) regardless of platform.
- The runner MUST NOT introduce an extra trailing newline that was not present in the captured
  content.

Capture semantics:

- The runner SHOULD capture process output as bytes and then apply deterministic decoding and
  normalization.
- Invalid UTF-8 sequences MUST be handled deterministically (example: decode with replacement using
  U+FFFD).

### Terminal session recording (asciinema) (optional)

Purpose: Provide a human-playable terminal session view for debugging and documentation without
serving as mechanical evidence for scoring or test evaluation.

Enablement:

- Controlled by config `runner.atomic.capture_terminal_recordings` (default: `false`).

Storage requirement (when enabled):

- For each attempted execution, the runner MUST store:
  - `terminal.cast` at `runs/<run_id>/runner/actions/<action_id>/terminal.cast`

Format and encoding (normative):

- The recording MUST be an asciinema cast file (v2).
- The file MUST be UTF-8 without BOM and MUST use LF (`\n`) line endings.
- The recording SHOULD capture the combined terminal stream as observed by the executor (stdout and
  stderr interleaved, when available).

Redaction and disabled behavior (normative):

- The recording is treated as evidence-tier text and MUST follow the effective redaction policy (see
  [ADR-0003: Redaction policy](../adr/ADR-0003-redaction-policy.md)).
- When `security.redaction.enabled: true`, the runner MUST redact string content while preserving
  asciinema cast structure (JSON value per line). Only string values are transformed.
- When `security.redaction.enabled: false`, the runner MUST NOT write unredacted recordings to the
  standard long-term path above; it MUST follow the project’s disabled behavior (withhold by
  default, or quarantine only with explicit opt-in).

Fail-closed and placeholders (normative):

- If the recording cannot be made redacted-safe, it MUST be withheld/quarantined and replaced at the
  standard path with a deterministic placeholder cast file (see
  [Placeholder artifacts](090_security_safety.md#placeholder-artifacts)).

### Redaction of transcripts

When `security.redaction.enabled: true` (or equivalent), the runner MUST apply the effective
redaction policy to transcripts before writing them.

- If redaction policy is enabled, transcripts MUST be redacted deterministically before being
  persisted to run bundle storage.
- If redaction fails, the runner MUST fail closed with `reason_code = redaction_failed` and MUST
  withhold transcript artifacts from the published bundle.

### Executor evidence file

For each attempted execution, the runner MUST write:

- `runs/<run_id>/runner/actions/<action_id>/executor.json`

This file MUST capture enough information to support deterministic replay and audit trails without
exposing secrets.

This artifact is contract-backed and therefore MUST:

- validate against `docs/contracts/runner_executor_evidence.schema.json`, and
- include the runner evidence JSON header pattern (`contract_version`, `run_id`, `action_id`,
  `action_key`, `generated_at_utc`) per the data contracts spec.

Minimum required fields (v0.1):

- `executor` (string, normalized executor name)
- `pwsh_version` (string or null; required when executor is PowerShell)
- `invoke_atomicredteam_version` (string or null)
- `started_at_utc` (RFC 3339 timestamp)
- `ended_at_utc` (RFC 3339 timestamp)
- `duration_ms` (integer)
- `exit_code` (integer)
- `atomics_root_actual` (string, evidence-only actual path)
- `command_shell_specific` (string or list of strings, evidence-only actual invocation form)
- `prereqs` (object, required when prerequisites are evaluated; see
  [Prerequisites and dependencies](#prerequisites-and-dependencies))
- `cleanup` (object; required for all attempted executions; records cleanup gating and outcomes),
  with at minimum:
  - `plan_cleanup` (boolean; effective `plan.cleanup` after defaults; see scenario model spec)
  - `invoke_configured` (boolean; effective `runner.atomic.cleanup.invoke`)
  - `verify_configured` (boolean; effective `runner.atomic.cleanup.verify`)
  - `cleanup_command_present` (boolean; whether the Atomic test defines `executor.cleanup_command`)
  - `invoke_effective` (boolean; `plan_cleanup && invoke_configured && cleanup_command_present`)
  - `invoke_attempted` (boolean)
  - `skip_reason` (string enum; required when `invoke_attempted=false`):
    - `disabled_by_scenario` (effective `plan.cleanup=false`)
    - `disabled_by_policy` (effective `runner.atomic.cleanup.invoke=false`)
    - `prior_phase_blocked` (`execute` was not attempted)
    - `not_applicable` (no `cleanup_command` exists)

This file is evidence, not identity.

## Cleanup invocation and verification

### Cleanup invocation strategy (revert) (normative)

Atomic tests may define a cleanup command. Cleanup execution is controlled by:

- plan-level cleanup: `plan.cleanup` (boolean)
- runner config: `runner.atomic.cleanup.invoke` (boolean)
- presence of cleanup command in Atomic YAML

Rules:

- If `plan.cleanup = false` OR `runner.atomic.cleanup.invoke = false`, the runner MUST:

  - skip cleanup command invocation
  - record `revert` phase as skipped with `reason_domain="ground_truth"` and
    `reason_code = cleanup_suppressed`
  - record `teardown` phase as skipped with `reason_domain="ground_truth"` and
    `reason_code = cleanup_suppressed`
  - MUST NOT emit `cleanup_verification.json` for the action

- If cleanup is enabled and a cleanup command is present, the runner MUST:

  - attempt cleanup once after `execute` completes (even if `execute` failed after partial activity)
  - when `runner.atomic.capture_transcripts = true`, capture cleanup stdout/stderr to:
    - `runs/<run_id>/runner/actions/<action_id>/cleanup_stdout.txt`
    - `runs/<run_id>/runner/actions/<action_id>/cleanup_stderr.txt`
  - attach ground-truth evidence pointers on the `revert` phase record (per data contracts spec):
    - `evidence.executor_ref`
    - `evidence.cleanup_stdout_ref` and `evidence.cleanup_stderr_ref` (when transcripts exist)
  - emit executor.json fields for cleanup command variants + digests
  - append cleanup side-effects to side-effect ledger

- If cleanup is enabled but cleanup command is missing, the runner MUST fail closed with
  `reason_code = cleanup_command_missing`.

- If `execute` was not attempted, the runner MUST NOT attempt cleanup and MUST record `revert` as
  `phase_outcome=skipped` with `reason_domain="ground_truth"` and
  `reason_code = prior_phase_blocked` (not `invalid_lifecycle_transition`).

When `runner.atomic.cleanup.invoke: true`:

- The runner MUST invoke cleanup via `Invoke-AtomicTest -Cleanup` (not by executing
  `cleanup_command` directly).
- The runner MUST use the same `-InputArgs` and the same Atomics root configuration used for
  execution.

Rationale (normative): direct execution would require re-implementing Invoke-AtomicRedTeam
substitution and executor semantics, which is not allowed for the v0.1 reference executor.

### Cleanup transcript capture

Cleanup invocation MUST capture transcripts and store them per
[Stdout and stderr transcript files](#stdout-and-stderr-transcript-files).

### Cleanup verification checks

When cleanup verification is enabled (see the
[validation criteria spec](035_validation_criteria.md)):

- Cleanup verification MUST be gated by operator intent:
  - The runner MUST execute cleanup verification checks only when effective `plan.cleanup = true`
    and `runner.atomic.cleanup.verify = true`.
  - If either gate is false, the runner MUST NOT execute checks and MUST NOT write
    `cleanup_verification.json` for the action.
- The runner MUST execute the configured cleanup verification checks after cleanup completes.
- The runner MUST write results to:
  - `runs/<run_id>/runner/actions/<action_id>/cleanup_verification.json`

Result requirements:

- The file MUST be deterministic:
  - stable ordering of results by `check_id` ascending
  - stable ordering of any nested arrays by stable key (if present)
- Each result MUST include:
  - `check_id`
  - `type`
  - `target`
  - `status` (`pass | fail | indeterminate | skipped`)
  - `reason_code` (required)
  - `reason_domain` (string; required when not `passed`; MUST equal `cleanup_verification`)
  - `attempts`
  - `elapsed_ms`

Reason code mapping:

- For `pass | fail | indeterminate`, the runner MUST use the reason code mapping defined in the
  [validation criteria spec](035_validation_criteria.md).
- For `skipped`, the runner MUST use a stable reason code (minimum recommended set):
  - `unsupported_platform`
  - `insufficient_privileges`
  - `exec_error`
  - `disabled_by_policy`

### Ground truth cleanup fields

Ground truth timeline entries for the action MUST reflect cleanup execution and verification
outcomes as specified by the ground truth contract in the
[data contracts spec](025_data_contracts.md), including a reference to `cleanup_verification.json`
when produced.

## Appendix: ATTiRe import mode (optional)

Some environments may execute Atomic tests outside Purple Axiom (for example, via a separate runner
wrapper) while still producing structured ATTiRe execution logs.

Implementations MAY support an "ATTiRe import" mode that ingests external structured execution
records and emits a run bundle that is contract-compatible with downstream stages.

If ATTiRe import mode is implemented (normative requirements):

- The runner MUST write a normalized per-action ATTiRe record to:
  - `runs/<run_id>/runner/actions/<action_id>/attire.json`
- The runner MUST derive `ground_truth.jsonl` entries from the imported `attire.json` using the same
  mapping rules as the execution path (timestamps, action identity fields, and executor status
  fields).
- The runner MUST NOT attempt to execute `Invoke-AtomicTest` when operating in import mode.
- `executor.json` MUST record that the action was imported (example field: `import_mode=true`) and
  MUST include a SHA-256 of the imported ATTiRe bytes after newline normalization (example field:
  `attire_sha256`).
- If the imported record is missing required fields, the runner MUST fail closed for the action with
  `reason_code=attire_import_error` and MUST preserve the raw import file only in a quarantined
  location (if configured).

This appendix does not require import mode for v0.1. When not enabled, `attire.json` is produced
only by the reference executor as specified in
[Structured execution record (ATTiRe)](#structured-execution-record-attire).

## Failure modes and stage outcomes

Failures in this contract MUST be observable in:

- per-action ground truth status fields (where applicable)
- runner evidence files (where applicable)
- stage outcomes recorded in the run manifest per the
  [stage outcomes ADR](../adr/ADR-0005-stage-outcomes-and-failure-classification.md)

Reason code scope (normative):

- Stage/substage outcome `reason_code` values emitted in `manifest.stage_outcomes[]` and
  `logs/health.json` are governed exclusively by ADR-0005.
- The reason codes listed below are action-level reason codes emitted in per-action lifecycle/phase
  records and runner evidence. They MUST NOT be emitted as stage/substage outcome reason codes in
  `logs/health.json` unless the specific code is also present in ADR-0005 for that stage/substage.

When an action-level failure causes the overall runner stage to fail, the runner MUST map it to the
appropriate ADR-0005 runner stage reason code (for example `prepare_failed`, `execute_failed`,
`cleanup_invocation_failed`) while preserving the action-level reason code in the per-action record.

At minimum, the runner MUST emit stable action-level reason codes for these failure classes:

- `atomic_yaml_not_found`
- `atomic_yaml_parse_error`
- `attire_import_error` (only when ATTiRe import mode is enabled)
- `missing_engine_test_id`
- `missing_required_input`
- `interactive_prompt_blocked`
- `unresolved_placeholder`
- `input_resolution_cycle_or_growth`
- `prereq_check_failed`
- `prereq_get_failed`
- `prereq_get_command_missing`
- `prereq_unsatisfied`
- `redaction_failed`
- `executor_invoke_error`
- `cleanup_invoke_error`
- `cleanup_verification_error`
- `target_asset_not_found`
- `target_asset_id_not_unique`
- `target_connection_address_missing`
- `reserved_input_key_collision`
- `missing_tool`
- `insufficient_privileges`
- `unsupported_platform`
- `unsafe_rerun_blocked`
- `invalid_lifecycle_transition`
- `prior_phase_blocked`
- `cleanup_suppressed`
- `empty_command`

Note: `unsafe_rerun_blocked` and `invalid_lifecycle_transition` are also valid stage outcome reason
codes when surfaced via the `runner.lifecycle_enforcement` substage (ADR-0005). All other reason
codes in the list above are action-level only and MUST NOT be emitted in `logs/health.json`.

## Verification hooks

Implementations MUST include fixture-backed tests that validate:

1. YAML parsing determinism: same YAML bytes yield identical extracted fields.
1. Template snapshot determinism: when enabled, `atomic_test_extracted.json` and (if present)
   `atomic_test_source.yaml` are byte-stable for identical YAML bytes and the same pinned parser and
   normalizer versions.
1. Input resolution determinism: same YAML bytes plus same override object yield identical
   `resolved_inputs_redacted_canonical` and identical `parameters.resolved_inputs_sha256`.
1. Requirements embedding determinism: changing `plan.requirements` (or derived requirements)
   changes `resolved_inputs_redacted_canonical` and changes `parameters.resolved_inputs_sha256`.
1. Canonicalization: `$ATOMICS_ROOT` replacement is applied to identity-bearing materials and does
   not vary with actual filesystem paths.
1. Transcript normalization: newline normalization and encoding rules produce byte-identical outputs
   for equivalent captured content.
1. Prerequisites determinism: dependency order, logging artifacts, and prereq outcomes are stable
   for identical inputs.
1. Cleanup verification determinism: result ordering and reason code requirements are stable.

CI SHOULD include a golden fixture conformance test that runs a pinned Atomic test twice with
identical inputs and asserts:

- identical `parameters.resolved_inputs_sha256`
- identical `action_key` (per the [scenario model spec](030_scenarios.md))
- stable emission of required runner evidence files

Fixture selection and gating (unit vs integration) are defined in the
[test strategy and CI spec](100_test_strategy_ci.md).

## Key decisions

- Atomic YAML parsing, input resolution, and transcript handling are deterministic and
  evidence-backed for cross-run comparability.
- The runner canonicalizes environment-dependent Atomics paths to `$ATOMICS_ROOT` for
  identity-bearing materials.
- The runner is responsible for prerequisite evaluation and optional fetch, producing explicit
  prereq artifacts and structured prereq outcomes to avoid relying on lab image pre-baking
- Cleanup uses Invoke-AtomicTest semantics and records verification artifacts for post-run
  validation.
- Failure modes emit stable reason codes tied to ground truth and stage outcomes.

## References

- [Data contracts spec](025_data_contracts.md)
- [Scenario model spec](030_scenarios.md)
- [Validation criteria spec](035_validation_criteria.md)
- [Storage formats spec](045_storage_formats.md)
- [Test strategy and CI spec](100_test_strategy_ci.md)
- [Redaction policy ADR](../adr/ADR-0003-redaction-policy.md)
- [Stage outcomes ADR](../adr/ADR-0005-stage-outcomes-and-failure-classification.md)
- [Supported versions](../../SUPPORTED_VERSIONS.md)

## Changelog

| Date | Change                                       |
| ---- | -------------------------------------------- |
| TBD  | Style guide migration (no technical changes) |
