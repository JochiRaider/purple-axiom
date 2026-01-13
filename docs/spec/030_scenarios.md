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

- The v0.1 runner MUST support **Atomic Test Plan** scenarios.
- v0.1 runs MUST be single-scenario (exactly one `scenario_id` per run bundle). Multi-scenario plans
  and manifests are reserved for a future release.
- **Caldera Operation** and **Mixed Plan** are reserved for a future release; if encountered, the
  v0.1 runner MUST fail before execution with a clear error (and a stable `reason_code`).

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

## Execution model (runner requirements)

Purple Axiom treats scenario execution as a staged lifecycle per action:

1. **Resolve** inputs (explicit, repeatable parameter resolution)
1. **Evaluate** and (optionally) satisfy prerequisites (Atomic `dependencies`)
1. **Execute** (capture stdout/stderr + executor metadata)
1. **Cleanup** (invoke cleanup command when applicable)
1. **Cleanup verification** (verify post-conditions; "cleanup ran" is not sufficient)

The runner MUST persist:

- Ground truth timeline entries (contracted).
- Runner evidence artifacts (stdout/stderr transcripts, executor metadata, cleanup verification
  results).
- For `engine = "atomic"` actions, the runner MUST implement the integration contract defined in the
  [Atomic Red Team executor integration spec](032_atomic_red_team_executor_integration.md)
  (deterministic YAML parsing, input resolution, prerequisites handling, transcript capture, cleanup
  invocation, and cleanup verification).

## Stable action identity (join keys)

v0.1 constraint (normative):

- `action_key_basis_v1.engine` MUST be `atomic`.

Each executed action MUST include two identifiers:

- `action_id` (unique within a run): used to correlate all per-run artifacts.
- `action_key` (stable across runs): used as the deterministic join key for regression comparisons.

`action_key` MUST be computed from `action_key_basis_v1` (see the
[data contracts spec](025_data_contracts.md)) canonicalized using `canonical_json_bytes(...)` as
defined by RFC 8785 (JCS).

- `engine` (`atomic` | `caldera` | `custom`)
- `technique_id`
- `engine_test_id` (Atomic test GUID / Caldera ability id / equivalent canonical id)
- `parameters.resolved_inputs_sha256` (hash of resolved inputs; not the raw inputs)
- `target_asset_id` (stable Purple Axiom logical asset id; see the
  [lab providers spec](015_lab_providers.md))

Then:

- `action_key = sha256(canonical_json_bytes(action_key_basis_v1))`

**Notes**:

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

**scenario_id**: stable identifier (human chosen)

**scenario_version**: semver or date-based

**run_id**: unique per execution

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

## Ground truth timeline schema (seed)

- `timestamp_utc`
- `run_id`, `scenario_id`, `scenario_version`
- `target_asset_id`
  - `target_asset_id` MUST be a stable Purple Axiom logical id (matching `lab.assets[].asset_id` in
    the inventory snapshot), not a provider-mutable identifier.
- `resolved_target` (seed)
  - `hostname` (optional)
  - `ip` (optional)
  - `provider_asset_ref` (optional): provider-native identifier
- `action_type` (`caldera_ability` | `atomic_test` | `custom`)
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
- `parameters` (seed)
  - `input_args_redacted` (optional)
  - `input_args_sha256` (optional)
- `expected_telemetry` (channels / event types)
- `cleanup_status`

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
  - selector: { role: "endpoint", os: "windows" }
plan:
  type: "atomic"
  technique_id: "T1059.001"
  engine_test_id: "d3c1...guid"
  input_args:
    command: "whoami"
  cleanup: true
```

## Ground truth timeline entry (v0.1)

Ground truth is emitted as JSONL, one action per line.

```json
{
  "timestamp_utc": "2026-01-03T12:00:00Z",
  "run_id": "run-2026-01-03-001",
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
    "resolved_inputs_sha256": "sha256hex..."
  },
  "criteria_ref": {
    "criteria_pack_id": "default",
    "criteria_pack_version": "0.1.0",
    "criteria_entry_id": "atomic/T1059.001/d3c1...guid/windows"
  },
  "expected_telemetry_hints": {
    "ocsf_class_uids": [1001, 1005]
  },
  "cleanup": {
    "invoked": true,
    "status": "success",
    "verification": {
      "status": "success",
      "results_ref": "runner/actions/s1/cleanup_verification.json"
    }
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

| Date | Change                                       |
| ---- | -------------------------------------------- |
| TBD  | Style guide migration (no technical changes) |
