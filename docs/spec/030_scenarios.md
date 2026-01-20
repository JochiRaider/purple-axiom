---
title: Scenario model
description: Defines scenario types, execution model, action identity, and ground truth expectations for runs.
status: draft
---

# Scenario model

This document defines the scenario model used by Purple Axiom, covering how scenarios describe
targets, actions, and execution constraints. It also specifies the runner requirements for identity,
determinism, and ground truth artifacts.

## Overview

Scenarios specify what to run, how to parameterize it, and which targets should be selected. The
runner executes actions through a deterministic lifecycle, emits stable identifiers, and records
ground truth for scoring and comparison. Expected telemetry is linked through criteria packs when
available.

## Separation of concerns

- A scenario defines WHAT to execute and HOW to parameterize it.
- A lab provider defines WHERE it runs by resolving concrete target assets.
- Scenarios should target assets via stable selectors (`asset_id`, `tags`, `roles`), then the
  provider resolves those selectors to concrete hosts for the run.

## Scenario types

v0.1 support (normative):

- The v0.1 runner MUST support `plan.type: "atomic"` only.
- If any other `plan.type` is encountered in v0.1, the runner MUST fail closed before execution with
  `reason_code="plan_type_reserved"`.

Plan types (evolution path):

- `atomic` (v0.1): single action, single target.
- `matrix` (reserved): combinatorial expansion over axes (targets, input variants, techniques).
- `sequence` (reserved): ordered action list with explicit dependency semantics.
- `campaign` (reserved): DAG/graph of named fragments; Caldera-style operations map here.
- `adaptive` (reserved): runtime branching based on observed results.

1. Caldera operation (reserved; not supported in v0.1)
   - One or more adversary profiles or abilities
   - Agents and target groups
   - Stop conditions and safety toggles
1. Atomic test plan
   - Technique ID and test IDs (Atomic GUIDs)
   - Prereqs, input args, cleanup steps
   - Safe mode flags
1. Mixed plan (reserved; not supported in v0.1)
   - A Caldera operation plus a set of Atomics
   - Used for "breadth + depth" runs
1. Matrix plan (reserved; not supported in v0.1)
   - Combinatorial expansion over declared axes (techniques, targets, input variants)
   - Enables "run this test on ALL matching targets" workflows
   - Produces multiple `action_id` entries within a single `run_id`
   - See [ADR-0006](../adr/ADR-0006-plan-execution-model.md) for architectural rationale

## Execution model (runner requirements)

Purple Axiom treats scenario execution as the per-action lifecycle defined below (`prepare`,
`execute`, `revert`, `teardown`), with optional per-action state reconciliation controlled by
`plan.reconciliation`.

### Action lifecycle

Purple Axiom models each action execution as a four-phase lifecycle:

- `prepare`: resolve inputs and evaluate or satisfy prerequisites.
- `execute`: attempt the technique payload.
- `revert`: undo execute-side effects so the action can be executed again on the same target.
- `teardown`: remove per-action prerequisites (when safe and applicable) and verify the target is in
  a known-good state.

Idempotence indicates whether `execute` MAY be re-attempted without a successful `revert`:

- `idempotent`: `execute` MAY be repeated without `revert`.
- `non_idempotent`: `execute` MUST NOT be repeated on the same target without a successful `revert`.
- `unknown`: treat as `non_idempotent` for safety.

Cleanup policy (scenario input, normative):

- The `plan.cleanup` flag controls whether the runner attempts the `revert` and `teardown` phases.
  - If `plan.cleanup` is omitted in v0.1, the runner MUST treat the effective value as `true`.
  - If `plan.cleanup = true`, the runner MUST attempt `revert` and `teardown` subject to the allowed
    transition rules below.
  - If `plan.cleanup = false`, the runner MUST set `revert.phase_outcome = skipped` and
    `teardown.phase_outcome = skipped`.
    - Rationale: `plan.cleanup = false` is an explicit operator request to retain post-action
      effects and/or prerequisites for debugging, and MUST NOT trigger destructive cleanup
      behaviors.
- `revert.phase_outcome` MUST be `skipped` with `reason_code="cleanup_suppressed"`.
- `teardown.phase_outcome` MUST be `skipped` with `reason_code="cleanup_suppressed"`.

Prerequisite scope (per-action vs shared, normative):

- The prerequisite set is engine-defined (for example Atomic `dependencies`) and MAY be constrained
  by scenario inputs (reserved for v0.2+).
- **Per-action prerequisites** are prerequisites that are attributable to a single action instance
  because the runner satisfied them by making changes during `prepare` (for example installing a
  tool, enabling a feature, or creating a temporary artifact).
- **Shared prerequisites** are prerequisites that were already present, or are not provably
  introduced by the current action instance.
- During `teardown`, the runner MUST remove only **per-action prerequisites**.
- The runner MUST NOT remove **shared prerequisites**.
- If the runner cannot deterministically classify a prerequisite as per-action, it MUST treat the
  prerequisite as shared.

Allowed transitions (finite-state machine, normative):

- The runner MUST attempt phases in order: `prepare` -> `execute` -> `revert` -> `teardown`.
- A phase MAY be `skipped` when it is not applicable or is blocked by an earlier failure.
- If `prepare` is `failed`, `execute` MUST be `skipped`.
- `revert` MUST NOT be attempted unless `execute` was attempted.
- When `plan.cleanup = true`, `teardown` SHOULD be attempted even if `execute` or `revert` failed,
  but MUST record its outcome.
- When a lifecycle phase is `skipped` or `failed`, the phase record MUST include a stable
  `reason_code` (see data contracts).

Recording requirements (normative):

Ground truth MUST record (minimum):

- `run_id`, `scenario_id`, `scenario_version`, `action_id`, `action_key`.
- `timestamp_utc`:
  - MUST be an ISO-8601 UTC timestamp string, and
  - when `lifecycle` is present, MUST equal `lifecycle.phases[0].started_at_utc`.
- `engine`, `engine_test_id`, `technique_id`, `target_asset_id`.
- `parameters.*` including `parameters.resolved_inputs_sha256` (string; `sha256:<hex>` form).
- `idempotence`.
- `lifecycle.phases[]`:
  - MUST include exactly these phases in order: `prepare`, `execute`, `revert`, `teardown`.
  - Each phase MUST include `phase_outcome`.
  - If `phase_outcome` is `failed` or `skipped`, the phase MUST include `reason_code`.
- `evidence_refs[]` (when external evidence artifacts exist) using deterministic, stable artifact
  references.

The runner MUST persist:

- Ground truth timeline entries (contracted).
- For `engine = "atomic"` actions, the runner MUST implement the integration contract defined in the
  [Atomic Red Team executor integration spec](032_atomic_red_team_executor_integration.md)
  (deterministic YAML parsing, input resolution, prerequisites handling, transcript capture, cleanup
  invocation, and cleanup verification).
- Runner evidence artifacts under `runner/` MUST include, at minimum (see data contracts “Runner
  evidence”): Per-action (under `runner/actions/<action_id>/`):
  - `stdout.txt`, `stderr.txt`
  - `executor.json`
  - `requirements_evaluation.json` (when requirements evaluation is performed)
  - `side_effect_ledger.json` (append-only)
  - `cleanup_verification.json` (when cleanup verification is enabled)
  - `state_reconciliation_report.json` (when state reconciliation is enabled) Per-run:
  - `runner/principal_context.json`

### State reconciliation policy (per action)

State reconciliation is an optional runner capability that performs post-action drift detection
using runner evidence artifacts (side-effect ledger and, when present, cleanup verification).

For v0.1 (single-action plans), the reconciliation policy is expressed under `plan.reconciliation`.

Scenario inputs (normative):

- Scenarios MAY declare a reconciliation policy per action:
  - `none`: do not perform reconciliation.
  - `observe_only`: perform read-only probes and emit reconciliation reports.
  - `repair`: request destructive reconciliation (reserved; not supported in v0.1).

v0.1 repair handling (normative):

- `repair` is reserved in v0.1. Implementations MUST NOT mutate targets as part of reconciliation.
- If a scenario requests `policy=repair` but repair is not enabled/supported, the runner MUST:
  - perform reconciliation probes in observe-only mode, and
  - record the blocked intent deterministically in the reconciliation report (per-item `reason_code`
    SHOULD be `repair_blocked` for affected items), and
  - surface drift via reconciliation outputs (do not downgrade/omit drift because repair was
    blocked).

Optional scope control (normative; when reconciliation is enabled):

- Default sources are `sources=[cleanup_verification, side_effect_ledger]` (in that order).
- Scenarios MAY constrain sources via `plan.reconciliation.sources` (when present).

### Technique requirements (permissions and environment assumptions)

Scenarios MAY declare explicit action requirements used for deterministic preflight gating and
explainable failures.

For v0.1 (single-action plans), requirements are expressed under `plan.requirements`.

`plan.requirements` (v0.1) minimal shape:

- `platform` (optional object): OS constraints.
  - `os` (optional array of strings): allowed OS families (`windows`, `linux`, `macos`).
- `privilege` (optional string enum): `user | admin | system | unknown`
- `tools` (optional array of strings): required tools/capabilities.

Normative requirements:

- `requirements` MUST be machine-readable; free-form prose fields MUST NOT be used for gating.
- When `requirements` is present, it MUST participate in action identity by being incorporated into
  the canonical basis used to compute `parameters.resolved_inputs_sha256` (see
  [Stable action identity (join keys)](#stable-action-identity-join-keys)).

## Safety controls

Scenarios declare safety constraints under `scenario.safety`. These constraints are normative run
inputs and MUST NOT be treated as advisory hints.

### allow_network

`scenario.safety.allow_network` declares whether the scenario is permitted to have outbound network
egress from target assets.

Effective outbound policy (normative):

- The runner MUST compute:
  `effective_allow_outbound = scenario.safety.allow_network AND security.network.allow_outbound`.
- If `effective_allow_outbound` is false, outbound egress MUST be denied by default (enforced at the
  lab boundary); runner-side controls are defense-in-depth only.

Enforcement responsibility (normative):

- The lab provider MUST enforce the effective outbound posture at the lab boundary (segmentation,
  firewall rules, security groups, or equivalent).
- The runner MUST NOT be the primary enforcement mechanism for outbound isolation. The runner MAY
  apply defense-in-depth measures when available, but the run MUST remain safe if runner-side
  controls are bypassed or unavailable.

Verification hook:

- When effective outbound policy is denied, telemetry validation MUST perform the network egress
  canary check defined in the telemetry pipeline and operability specifications.

## Stable action identity (join keys)

v0.1 constraint (normative):

- `action_key_basis_v1.engine` MUST be `atomic`.

Each executed action MUST include two identifiers:

- `action_id` (run-scoped correlation key): used to correlate all per-run artifacts.
  - v0.1: legacy `s<positive_integer>` (example: `s1`).
  - v0.2+: MUST equal the deterministic action instance id format defined in the data contracts spec
    (`pa_aid_v1_<32hex>`).
- `action_key` (stable across runs): used as the deterministic join key for regression comparisons.

`action_key` MUST be computed as:

`action_key = sha256_hex(canonical_json_bytes(action_key_basis_v1))`

Where `canonical_json_bytes` is RFC 8785 JCS canonical JSON encoded as UTF-8 bytes.

`action_key_basis_v1` (minimum fields) MUST include:

- `v`: `1`
- `engine`: `"atomic"`
- `technique_id`
- `engine_test_id`
- `target_asset_id`
- `resolved_inputs_sha256`: equal to `parameters.resolved_inputs_sha256` (string; `sha256:<hex>`
  form)

Action requirements and identity (normative):

- If the scenario declares action requirements (`plan.requirements` in v0.1;
  `actions[].requirements` in v0.2+), the runner MUST incorporate the effective requirements object
  into the canonical basis used to compute `parameters.resolved_inputs_sha256`, so `action_key`
  changes deterministically when requirements change. See the Atomic executor integration spec for
  the canonical embedding rules.

Then:

- `action_key = sha256(canonical_json_bytes(action_key_basis_v1))`

In v0.2+, ground truth entries SHOULD also include a stable `template_id` field (procedure identity)
in addition to the engine-specific identifiers above. `template_id` MUST be stable across runs and
MUST NOT incorporate `run_id` or timestamps. **Notes**:

- `action_key` MUST NOT incorporate `run_id` or timestamps.
- `action_key` SHOULD NOT embed secrets; use hashes for resolved inputs and store redacted inputs
  separately.
- Canonicalization MUST follow RFC 8785; do not use native JSON serializers.
- `target_asset_id` MUST refer to the **stable** `lab.assets[].asset_id` namespace, not to a
  provider-mutable identifier. If a provider cannot resolve stable `asset_id`s for targets, the run
  MUST fail closed (see the [lab providers spec](015_lab_providers.md)).

## Criteria linkage (expected telemetry)

Expected telemetry is externalized into criteria packs (see the
[validation criteria spec](035_validation_criteria.md)):

- Ground truth MAY include `expected_telemetry_hints` as coarse hints.
- Ground truth SHOULD include a `criteria_ref` when a criteria entry is selected.
- Scoring MUST prefer criteria evaluation outputs when present.

## Scenario identity

- `scenario_id`: stable identifier (string).
- `scenario_version`: MUST be a SemVer 2.0.0 string (e.g., `0.1.0`).
- `run_id`: MUST be an RFC 4122 UUID (string).

Rationale: scenario versions must support ordered compatibility semantics; run identifiers must be
globally unique and format-validated.

## Target selection (seed)

**target_selector**: Selection criteria for targets.

- `asset_ids` (optional): explicit list
- `tags` (optional): match-any tags
- `roles` (optional): match-any roles
- `os` (optional): constrain to OS families

The resolved targets for a run are written into the run manifest and an inventory snapshot artifact.

v0.1 determinism constraints (normative):

- Each executed action MUST resolve to exactly one `target_asset_id` in `ground_truth.jsonl`.
- If a selector matches multiple assets, the runner/provider MUST select deterministically using a
  stable ordering over `lab.assets[].asset_id` (bytewise lexical ordering of UTF-8), and SHOULD
  record the selection rule in runner evidence so the choice is explainable.

**Reserved: Multi-target iteration (v0.2+)**

v0.1 does not support iterating a single plan action across multiple matched targets within one run.
If this capability is required in v0.1, operators MUST either:

- Generate separate run bundles per target, or
- Use external orchestration to invoke multiple runs.

A future release (v0.2) will introduce `matrix` plan semantics to support multi-target iteration
within a single `run_id`. The `action_key` design (which includes `target_asset_id`) is
forward-compatible with this expansion—each (test × target) pair will produce a distinct
`action_key`.

See [ADR-0006](../adr/ADR-0006-plan-execution-model.md) for the plan execution model decision.

## Ground truth timeline schema (seed)

- `timestamp_utc` MUST equal `lifecycle.phases[0].started_at_utc` when lifecycle is present.
- `run_id`, `scenario_id`, `scenario_version`
- `target_asset_id`
  - `target_asset_id` MUST be a stable Purple Axiom logical id (matching `lab.assets[].asset_id` in
    the inventory snapshot), not a provider-mutable identifier.
- `resolved_target` (seed)
  - `hostname` (optional)
  - `ip` (optional)
  - `provider_asset_ref` (optional): provider-native identifier
- `engine`: string (v0.1: `"atomic"`).
- `criteria_ref`: optional string (links to criteria packs).
- `expected_telemetry_hints`: optional array (non-normative hints for operators).
- `technique_id` (ATT&CK)
- `command_summary` (redacted-safe summary)
  - When `security.redaction.enabled: true`, `command_summary` MUST be produced under the effective
    redaction policy and MUST be redacted-safe (see the
    [redaction policy ADR](../adr/ADR-0003-redaction-policy.md)).
  - When `security.redaction.enabled: false`, `command_summary` in the standard ground truth
    artifact MUST be omitted or set to a deterministic placeholder (example:
    `<WITHHELD:REDACTION_DISABLED>`).
  - Unredacted command summaries MAY be stored only in a quarantined unredacted evidence location
    when explicitly enabled by config.
  - MUST be deterministic given the same tokenized command input and the same effective policy.
  - SHOULD be accompanied by policy provenance in `extensions` (policy id/version/sha256) so drift
    is explainable.
- `parameters.resolved_inputs_sha256`: string; `sha256:<hex>` form.
- `idempotence` (`idempotent | non_idempotent | unknown`)
- `lifecycle.phases[]` MUST include `prepare`, `execute`, `revert`, `teardown` (in order).
  - `reason_code` is required when `phase_outcome` is `failed` or `skipped`.

### Principal selection (non-secret) (normative)

Scenarios MAY specify a human-meaningful principal selector:

- `plan.execution.principal_alias` (string, optional)

Requirements:

- The value MUST be a non-secret alias token (examples: `user`, `admin`, `svc`).
- The runner MUST map the alias to an actual execution principal via runner configuration. Scenarios
  MUST NOT embed credentials or secret material.
- The effective principal alias (explicit or default) MUST participate in action identity, because
  execution context affects results.

Evidence:

- The runner records the typed principal identity context for the run in
  `runs/<run_id>/runner/principal_context.json`.

## Seed schema: Scenario definition (v0.1)

```yaml
scenario_id: "scn-2026-01-001"
version: "0.1.0"
name: "Atomic T1059.001 Powershell"
description: "Basic PowerShell execution and related telemetry"
safety:
  max_runtime_seconds: 600
  allow_network: false
  allow_persistence: false
targets:
  - selector:
      roles: ["endpoint"]
      os: ["windows"]
safety:
  allow_network: false
plan:
  type: "atomic"
  technique_id: "T1059.001"
  engine_test_id: "d3c1...guid"
  idempotence: "unknown"
  requirements:
    platform: { os: ["windows"] }
    privilege: "admin"
    tools: ["powershell"]  
  input_args:
    command: "whoami"
  cleanup: true
  reconciliation:
    policy: "observe_only"
    sources: ["cleanup_verification"]
```

## Ground truth timeline entry (v0.1)

Ground truth is emitted as JSONL, one action per line.

```json
{
  "timestamp_utc": "2026-01-03T12:00:00Z",
  "run_id": "<uuid>",  (RFC 4122 UUID)
  "scenario_id": "scn-2026-01-001",
  "scenario_version": "0.1.0",
  "action_id": "s1",
  "action_key": "sha256hex...",
  "engine": "atomic",
  "engine_test_id": "d3c1...guid",
  "technique_id": "T1059.001",
  "target_asset_id": "win11-test-01",
  "resolved_target": {
    "hostname": "WIN11-TEST-01",
    "ip": "192.0.2.10"
  },
  "command_summary": "powershell.exe -NoProfile ... (redacted)",
  "extensions": {
    "redaction": {
      "policy_id": "pa-redaction",
      "policy_version": "1.0.0",
      "policy_sha256": "sha256hex..."
    }
  },
  "parameters": {
    "input_args_redacted": {
      "command": "whoami"
    },
    "input_args_sha256": "sha256hex...",
    "resolved_inputs_sha256": "sha256:<hex>"
  },
  "criteria_ref": {
    "criteria_pack_id": "default",
    "criteria_pack_version": "0.1.0",
    "criteria_entry_id": "atomic/T1059.001/d3c1...guid/windows"
  },
  "expected_telemetry_hints": {
    "ocsf_class_uids": [1001, 1005]
  },
  "idempotence": "unknown",
   "lifecycle": {
     "phases": [
     {
       "phase": "prepare",
       "phase_outcome": "success",
       "started_at_utc": "2026-01-03T12:00:00Z",
       "ended_at_utc": "2026-01-03T12:00:02Z"
     },
     {
       "phase": "execute",
       "phase_outcome": "success",
       "started_at_utc": "2026-01-03T12:00:02Z",
       "ended_at_utc": "2026-01-03T12:00:05Z"  
     },
     {
       "phase": "revert",
       "phase_outcome": "success",
       "started_at_utc": "2026-01-03T12:00:05Z",
       "ended_at_utc": "2026-01-03T12:00:06Z"
     },
     {
       "phase": "teardown", 
       "phase_outcome": "success",
       "started_at_utc": "2026-01-03T12:00:06Z",
       "ended_at_utc": "2026-01-03T12:00:07Z",
       "evidence": {
         "cleanup_verification_ref": "runner/actions/s1/cleanup_verification.json"
       }
     }
    ]
  }
}
```

## Ground truth timeline entry (v0.2+; deterministic action_id)

When the plan execution model is enabled (multi-action plans), each emitted action line MUST use a
deterministic `action_id` of the form `pa_aid_v1_<32hex>` as defined in the data contracts spec.

```json
{
  "timestamp_utc": "2026-01-03T12:00:00Z",
  "run_id": "<uuid>",  (RFC 4122 UUID)
  "scenario_id": "scn-2026-01-001",
  "scenario_version": "0.1.0",
  "action_id": "pa_aid_v1_4b2d3f3f6b7b2a1c9a1d2c3b4a5f6e7d",
  "template_id": "atomic/T1059.001/d3c1...guid",
  "action_key": "sha256hex...",
  "engine": "atomic",
  "engine_test_id": "d3c1...guid",
  "technique_id": "T1059.001",
  "target_asset_id": "win11-test-01",
  "extensions": {
    "plan": {
      "node_ordinal": 0
    }
  },
  "parameters": {
    "resolved_inputs_sha256": "sha256:<hex>"
  },
  "idempotence": "unknown",
  "lifecycle": {
    "phases": [
      {
        "phase": "prepare",
        "phase_outcome": "success",
        "started_at_utc": "2026-01-03T12:00:00Z",
        "ended_at_utc": "2026-01-03T12:00:02Z"
      },
      {
        "phase": "execute",
        "phase_outcome": "success",
        "started_at_utc": "2026-01-03T12:00:02Z",
        "ended_at_utc": "2026-01-03T12:00:05Z"
      },
      {
        "phase": "revert",
        "phase_outcome": "success",
        "started_at_utc": "2026-01-03T12:00:02Z",
        "ended_at_utc": "2026-01-03T12:00:02Z"
      },      
      {
        "phase": "teardown",
        "phase_outcome": "success",
        "started_at_utc": "2026-01-03T12:00:05Z",
        "ended_at_utc": "2026-01-03T12:00:07Z",
        "evidence": {
          "cleanup_verification_ref": "runner/actions/pa_aid_v1_4b2d3f3f6b7b2a1c9a1d2c3b4a5f6e7d/cleanup_verification.json"
        }
      }
    ]
  }
}
```

## Key decisions

- Scenarios define what to execute while lab providers resolve concrete targets.
- v0.1 supports atomic test plans and treats other scenario types as reserved.
- Action identity is derived from `action_key_basis_v1` using RFC 8785 canonicalization.
- Target selection must be deterministic when selectors match multiple assets.

## References

- [Data contracts spec](025_data_contracts.md)
- [Lab providers spec](015_lab_providers.md)
- [Atomic Red Team executor integration spec](032_atomic_red_team_executor_integration.md)
- [Validation criteria spec](035_validation_criteria.md)
- [Redaction policy ADR](../adr/ADR-0003-redaction-policy.md)

## Changelog

| Date      | Change                                                                                               |
| --------- | ---------------------------------------------------------------------------------------------------- |
| 1/19/2026 | align scenario types with plan execution model; align ground truth seed/examples with data contracts |
| 1/13/2026 | Define allow_network enforcement + validation hook                                                   |
| 1/10/2026 | Style guide migration (no technical changes)                                                         |
