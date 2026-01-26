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

Unless otherwise specified, artifact paths in this document are run-relative (i.e., relative to the
run bundle root `runs/<run_id>/` and MUST NOT include the `runs/<run_id>/` prefix).

## Separation of concerns

- A scenario defines WHAT to execute and HOW to parameterize it.
- A lab provider defines WHERE it runs by resolving concrete target assets.
- Scenarios should target assets via stable selectors (`asset_ids`, `tags`, `roles`), then the
  provider resolves those selectors to concrete hosts for the run.

## Operational posture

Scenarios MAY declare a **posture** that describes the assumed compromise state of the environment
and attacker foothold at the start of the run. Posture is a planning input (v0.2+) and a reporting
dimension; it is intentionally distinct from:

- `safety`: safety constraints and lab enforcement controls, and
- `plan.execution.principal_alias`: the non-secret alias the runner uses to select an execution
  principal for the action(s).

### `posture`

Minimal shape:

- `posture.mode` (string enum; optional; default: `baseline`)

Allowed values (closed set):

- `baseline`: Assume no prior attacker foothold. Plans MAY include techniques representing initial
  compromise and post-compromise activity.
- `assumed_compromise`: Assume an attacker foothold already exists at run start. Plans SHOULD focus
  on post-compromise techniques (credential access, discovery, lateral movement, persistence) and
  MUST NOT rely on pre-compromise assumptions unless explicitly modeled by the plan.

Normative requirements:

- If `posture` is omitted, the runner MUST treat the effective posture as `baseline`.
- If `posture.mode` is present and is not one of the allowed values above, the runner MUST fail
  closed before execution and MUST record the stage outcome `reason_code="invalid_posture_mode"`
  (see
  [ADR-0005: Stage outcomes and failure classification](../adr/ADR-0005-stage-outcomes-and-failure-classification.md))
  in `logs/health.json` (and `manifest.stage_outcomes[]`).
- `posture` MUST be non-secret. It MUST NOT include credentials, tokens, usernames, hostnames, IPs,
  or any other sensitive identifiers.
- Changing `posture.mode` changes scenario semantics. Scenario authors MUST bump `scenario_version`
  when changing posture.

Reserved (v0.1):

- Additional keys under `posture` are reserved for future versions and MUST NOT be relied on until
  they are specified and schema-backed.

Provenance (normative):

- The runner MUST record the effective posture in the run manifest (`manifest.scenario.posture`).
- When the plan execution model is enabled (v0.2+), the compiler MUST also record the effective
  posture in `plan/expanded_graph.json` (`scenario_posture` at the graph root).

## Scenario types

v0.1 support (normative):

- The v0.1 runner MUST support `plan.type: "atomic"` only.
- If any other `plan.type` is encountered in v0.1, the runner MUST fail closed before execution and
  MUST record the stage outcome `reason_code="plan_type_reserved"` (see
  [ADR-0005: Stage outcomes and failure classification](../adr/ADR-0005-stage-outcomes-and-failure-classification.md))
  in `logs/health.json` (and `manifest.stage_outcomes[]`).

Plan types (evolution path):

| Plan type  | Description                                                       | Target version |
| ---------- | ----------------------------------------------------------------- | -------------- |
| `atomic`   | Single action, single target.                                     | v0.1           |
| `matrix`   | Combinatorial expansion over axes (targets, input variants, etc). | v0.2           |
| `sequence` | Ordered action list with explicit dependency semantics.           | v0.3+          |
| `campaign` | DAG/graph of named fragments; Caldera-style operations map here.  | v0.4+          |
| `adaptive` | Runtime branching based on observed results.                      | Future         |

Notes:

- A "Caldera operation" maps to `plan.type=campaign` (reserved; not supported in v0.1).
- "Mixed plan" is not a distinct `plan.type`; it is a composition style expressed as a `campaign`
  plan composed of atomic nodes (reserved; not supported in v0.1).
- Multi-action plans produce multiple `action_id` entries within a single `run_id` (v0.2+).
- See [ADR-0006](../adr/ADR-0006-plan-execution-model.md) for architectural rationale.

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

#### Allowed transitions (finite-state machine, normative):

- The runner MUST attempt phases in order: `prepare` -> `execute` -> `revert` -> `teardown`.
- A phase MAY be `skipped` when it is not applicable, is blocked by an earlier phase outcome, or is
  suppressed by operator intent (for example `plan.cleanup=false`).
- A lifecycle phase that is not attempted MUST be recorded as `phase_outcome=skipped` with a stable
  `reason_domain="ground_truth"` and `reason_code` (see data contracts).

Gating:

- `execute` MUST be attempted only when `prepare.phase_outcome=success`.
  - If `prepare.phase_outcome` is `failed` or `skipped`, `execute` MUST be recorded as `skipped`.
- `revert` MUST NOT be attempted unless `execute` was attempted.
  - If `execute` was not attempted and cleanup is otherwise enabled, `revert` MUST be recorded as
    `skipped` with `reason_domain="ground_truth"` and `reason_code=prior_phase_blocked`.

Cleanup suppression (policy, not an error):

- If effective `plan.cleanup=false`, the runner MUST NOT attempt `revert` or cleanup-dependent
  `teardown` work for the action.
- Ground truth MUST record:
  - `revert.phase_outcome=skipped` with `reason_domain="ground_truth"` and `reason_code=cleanup_suppressed`, and
  - `teardown.phase_outcome=skipped` with `reason_domain="ground_truth"` and `reason_code=cleanup_suppressed`.

Teardown behavior:

- When cleanup is enabled (`plan.cleanup=true`), `teardown` SHOULD be attempted even if `execute` or
  `revert` failed, but MUST record its outcome.

Enforcement events:

- The runner MUST reserve `reason_code=invalid_lifecycle_transition` for explicit/forced lifecycle
  transition requests that violate the allowed transitions and are not explainable by
  `prior_phase_blocked` or `cleanup_suppressed` semantics.
- If the runner refuses an unsafe re-run of a `non_idempotent` action (including
  `idempotence="unknown"`), it MUST record the affected `execute` phase as `skipped` with
  `reason_code=unsafe_rerun_blocked`.

Retries:

- If the runner records more than four lifecycle phase records for an action (retry semantics),
  additional records MUST follow the rules in the data contracts spec (additional `execute` and/or
  `revert` retry records with monotonic `attempt_ordinal`).

Health integration:

- When `logs/health.json` is enabled, enforcement events (`invalid_lifecycle_transition` and
  `unsafe_rerun_blocked`) MUST also be surfaced as a `runner.lifecycle_enforcement` health substage
  outcome with the same `reason_code` (see ADR-0005).

#### Recording requirements (normative):

Ground truth MUST record (minimum):

- `run_id`, `scenario_id`, `scenario_version`, `action_id`, `action_key`.
- `template_id` (optional; v0.2+ only): stable procedure identity of the action template.
- `timestamp_utc`:
  - MUST be an ISO-8601 UTC timestamp string, and
  - when `lifecycle` is present, MUST equal `lifecycle.phases[0].started_at_utc`.
- `engine`, `engine_test_id`, `technique_id`, `target_asset_id`.
- `parameters.*` including `parameters.resolved_inputs_sha256` (string; `sha256:<hex>` form).
- `idempotence`.
- `requirements.*` (when requirements evaluation is performed):
  - `requirements.declared`, `requirements.evaluation`, `requirements.results[]` (see data
    contracts).
- `lifecycle.phases[]`:
  - MUST include (at minimum) these phases in order: `prepare`, `execute`, `revert`, `teardown`.
  - Additional retry records (v0.2+) MUST follow the data contracts rules (additional `execute`
    and/or `revert` records with monotonic `attempt_ordinal`).
  - Each phase MUST include `started_at_utc`, `ended_at_utc`, and `phase_outcome`.
  - If `phase_outcome` is `failed` or `skipped`, the phase MUST include `reason_domain` and `reason_code`.
  - `reason_domain` (string; required when not `success`; MUST equal `ground_truth`)
- `extensions.synthetic_correlation_marker` (when synthetic marker emission is enabled and `execute`
  was attempted).
- `evidence_refs[]` (when external evidence artifacts exist) using deterministic, stable artifact
  references.

The runner MUST persist:

- Ground truth timeline entries (contracted).

- For `engine = "atomic"` actions, the runner MUST implement the integration contract defined in the
  [Atomic Red Team executor integration spec](032_atomic_red_team_executor_integration.md)
  (deterministic YAML parsing, input resolution, prerequisites handling, transcript capture, cleanup
  invocation, and cleanup verification).

- Runner evidence artifacts under `runner/` MUST include, at minimum (see data contracts "Runner
  evidence"):

  Per-action (under `runner/actions/<action_id>/`):

  - `stdout.txt`, `stderr.txt`
  - `executor.json`
  - `resolved_inputs_redacted.json` (required for `engine="atomic"`; optional for other engines)
  - `requirements_evaluation.json` (when requirements evaluation is performed)
  - `prereqs_stdout.txt`, `prereqs_stderr.txt` (when prerequisites are invoked)
  - `cleanup_stdout.txt`, `cleanup_stderr.txt` (when cleanup is invoked)
  - `side_effect_ledger.json` (append-only)
  - `cleanup_verification.json` (when cleanup verification is enabled)
  - `state_reconciliation_report.json` (when state reconciliation is enabled)
  - `attire.json` (required for `engine="atomic"`; optional for other engines)

  Per-run:

  - `runner/principal_context.json`

### State reconciliation policy (per action)

State reconciliation is an optional runner capability that performs post-action drift detection
using runner evidence artifacts (side-effect ledger and, when present, cleanup verification).

Enablement (normative):

- State reconciliation is performed only when it is enabled in runner configuration (for example,
  `runner.atomic.state_reconciliation.enabled=true`) and the effective per-action policy is not
  `none`.
- When reconciliation is disabled in runner configuration, the runner MUST NOT attempt
  reconciliation regardless of scenario policy and MUST NOT emit
  `runner/actions/<action_id>/state_reconciliation_report.json`.

For v0.1 (single-action plans), the reconciliation policy is expressed under `plan.reconciliation`.

Scenario inputs (normative):

- Scenarios MAY declare a reconciliation policy per action:
  - `none`: do not perform reconciliation.
  - `observe_only`: perform read-only probes and emit reconciliation reports.
  - `repair`: request destructive reconciliation (reserved; not supported in v0.1).

v0.1 repair handling (normative):

- `repair` is reserved in v0.1. Implementations MUST NOT mutate targets as part of reconciliation.
- If a scenario requests `policy=repair` but repair is not enabled/supported (for example,
  `runner.atomic.state_reconciliation.allow_repair=false`), the runner MUST:
  - perform reconciliation probes in observe-only mode, and
  - record the blocked intent deterministically in the reconciliation report (SHOULD be per-item 
    `reason_domain="state_reconciliation_report"` and `reason_code="repair_blocked"` for affected items), and
  - surface drift via reconciliation outputs (do not downgrade/omit drift because repair was
    blocked).

Optional scope control (normative; when reconciliation is enabled):

- Default sources are `sources=[cleanup_verification, side_effect_ledger]` (in that order).
- Scenarios MAY constrain sources via `plan.reconciliation.sources` (when present).

Operability linkage (recommended):

- When reconciliation is enabled, implementations SHOULD surface aggregate reconciliation status via
  `logs/health.json` as substage `runner.state_reconciliation` (see ADR-0005).

### Technique requirements (permissions and environment assumptions)

Scenarios MAY declare explicit action requirements used for deterministic preflight gating and
explainable failures.

For v0.1 (single-action plans), requirements are expressed under `plan.requirements`.

`plan.requirements` (v0.1) minimal shape:

- `platform` (optional object): OS constraints.
  - `os` (optional array of strings): allowed OS families allowed OS families (`windows`, `linux`,
    `macos`, `bsd`, `appliance`, `other`).
- `privilege` (optional string enum): `user | admin | system | unknown`
- `tools` (optional array of strings): required tools/capabilities.

Normative requirements:

- `requirements` MUST be machine-readable; free-form prose fields MUST NOT be used for gating.
- When `requirements` is present, it MUST participate in action identity by being incorporated into
  the canonical basis used to compute `parameters.resolved_inputs_sha256` (see
  [Stable action identity (join keys)](#stable-action-identity-join-keys)).

## Safety controls

Scenarios declare safety constraints under `safety`. These constraints are normative run inputs and
MUST NOT be treated as advisory hints.

Note: Some documents use the dotted prefix `scenario.safety.*` to disambiguate scenario fields from
runner configuration (for example `security.*`). In v0.1 scenario YAML, `safety` is a top-level key
(no nested `scenario` object).

- `safety.allow_network` (boolean; default: false)
  - When false, outbound network egress MUST be denied for action execution.
    - Enforcement MUST be performed at the lab boundary (lab provider / lab controls); the runner
      MUST NOT be treated as a sufficient isolation mechanism.
    - The runner MAY apply defense-in-depth best-effort egress denial, but it is not the safety
      boundary of record.
  - Effective policy is computed as:
    `effective_allow_outbound = safety.allow_network AND security.network.allow_outbound`.

Reserved (v0.1):

- Additional keys under `safety` are reserved for future versions and MUST NOT be relied on until
  they are specified and schema-backed.

Verification hook:

- When effective outbound policy is denied, telemetry validation MUST perform the network egress
  canary check defined in telemetry pipeline and operability specs.

## Stable action identity (join keys)

v0.1 constraint (normative):

- `action_key_basis_v1.engine` MUST be `atomic`.

Each executed action MUST include two identifiers:

- `action_id`: identifies the action instance within a run.
  - v0.1: legacy string `s<positive_integer>` (single action, so always `s1`).
  - v0.2+: deterministic `pa_aid_v1_<32hex>` (see data contracts).
- `action_key`: identifies the *semantic* action (same intent + same target + same resolved inputs)
  across runs; this is the primary cross-run join key.

`action_key_basis_v1` (canonical object):

```json
{
  "v": 1,
  "engine": "atomic",
  "technique_id": "<Txxxx>",
  "engine_test_id": "<atomic-guid>",
  "parameters": {
    "resolved_inputs_sha256": "sha256:<hex>"
  },
  "target_asset_id": "<lab-asset-id>"
}
```

Computation (normative):

- `action_key = sha256_hex(canonical_json_bytes(action_key_basis_v1))`
- `canonical_json_bytes(value)` means RFC 8785 (JCS) canonical JSON, encoded as UTF-8 bytes (no BOM,
  no trailing newline).
- `sha256_hex(...)` means the lower-case hex string of the SHA-256 digest.
- The hash MUST be computed over the canonical bytes of the `action_key_basis_v1` object itself (do
  not wrap it in an outer object).

Uniqueness (normative):

- Within a single `run_id`, every action MUST have a unique `action_key`. If a duplicate
  `action_key`\
  is detected, the runner MUST fail closed (see ADR-0005: `reason_code=action_key_collision`).

Target identity (normative):

- `target_asset_id` MUST be the stable Purple Axiom logical asset id and MUST NOT be a
  provider-native\
  identifier.

v0.1 constraint:

- `action_key_basis_v1.engine` MUST be `atomic`.

Inputs that MUST participate in action identity:

- The action's _effective_ resolved input basis (including scenario overrides and template-derived\
  defaults) MUST participate via `parameters.resolved_inputs_sha256`.
  - This value MUST NOT embed secrets; only hashes and redacted/canonical forms are permitted.
  - When available, the runner SHOULD persist
    `runner/actions/<action_id>/resolved_inputs_redacted.json`\
    as evidence for the resolved input basis used.
- The action's _effective_ requirements MUST participate by being incorporated into the resolved\
  inputs hash basis under the reserved key `__pa_action_requirements_v1` (see the Atomic executor\
  integration spec for canonical embedding rules).
- The action's _effective_ principal alias MUST participate by being incorporated into the resolved\
  inputs hash basis under the reserved key `__pa_principal_alias_v1` (string; non-secret).
  - Reserved-key collisions MUST fail closed.

Action requirements and identity (normative):

- If the scenario declares action requirements (`plan.requirements` in v0.1;
  `actions[].requirements` in v0.2+), the runner MUST incorporate the effective requirements object
  into the canonical basis used to compute `parameters.resolved_inputs_sha256`, so `action_key`
  changes deterministically when requirements change. See the Atomic executor integration spec for
  the canonical embedding rules.

Then:

- `action_key` is the computed sha256_hex(canonical_json_bytes(action_key_basis_v1))\` value defined
  above.

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

Scenarios MAY point to evaluation criteria packs that encode expected telemetry for a
technique/test. The runner does not need to know all criteria semantics; it just records stable
references.

- `criteria_pack_id` (optional): stable pack identifier.
- `criteria_pack_version` (optional): SemVer string when a specific pack snapshot is pinned.
- `criteria_entry_id` (optional): stable criteria entry identifier within the pack.

Ground truth MAY include `expected_telemetry_hints` as coarse, non-authoritative hints (lossy
projection).

When a criteria entry is selected for an action (including auto-selection by the runner), ground
truth SHOULD include `criteria_ref` as an object:

- `criteria_ref.criteria_pack_id`
- `criteria_ref.criteria_pack_version`
- `criteria_ref.criteria_entry_id`

Scoring MUST prefer criteria evaluation outputs when present and treat `expected_telemetry_hints` as
non-authoritative.

## Scenario identity

- `scenario_id`: stable identifier (string; MUST conform to `id_slug_v1` from ADR-0001).
- `scenario_version`: MUST be a SemVer 2.0.0 string (e.g., `0.1.0`).
- `run_id`: MUST be an RFC 4122 UUID string in canonical hyphenated form.

Rationale: scenario versions must support ordered compatibility semantics; run identifiers must be
globally unique and format-validated.

## Target selection (seed)

Targets are declared under `targets[]`. Each entry contains a `selector` object describing the
candidate set. The runner/provider resolves selectors against the lab inventory snapshot.

**selector**: Selection criteria for targets.

- `asset_ids` (optional): explicit list
- `tags` (optional): match-any tags
- `roles` (optional): match-any roles
- `os` (optional): constrain to OS families (must match `lab.assets[].os`; one of
  `windows | linux | macos | bsd | appliance | other`)

The resolved target set for a run MUST be captured in:

- the run manifest (as resolved target metadata), and
- the provider inventory snapshot artifact (`logs/lab_inventory_snapshot.json`).

v0.1 determinism constraints (normative):

- Each executed action MUST resolve to exactly one `target_asset_id` in `ground_truth.jsonl`.
- If a selector (or the union of selectors in `targets[]`) matches multiple assets, the
  runner/provider MUST select deterministically using a stable ordering over `lab.assets[].asset_id`
  (bytewise lexical ordering of UTF-8), and SHOULD record the selection rule in runner evidence so
  the choice is explainable.

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

## Ground truth timeline schema

v0.1 uses JSONL, one action per line.

Fields (per line):

- `run_id` (uuid)
- `scenario_id` (string)
- `scenario_version` (semver)
- `action_id` (string)
- `action_key` (string; join key)
- `timestamp_utc` (string; ISO-8601 UTC)
- `engine` (string; e.g., `atomic`)
- `engine_test_id` (string; e.g., atomic GUID)
- `template_id` (string; optional; v0.2+ only; stable procedure identity of action template)
- `technique_id` (string; ATT&CK)
- `target_asset_id` (string; lab asset stable ID)
- `resolved_target` (object; optional metadata derived from the inventory snapshot):
  - `role` (string; optional; when present, matches `lab.assets[].role`)
  - `os` (string; optional; when present, matches `lab.assets[].os`)
  - `hostname` (string; optional; inventory hostname/DNS identifier)
  - `ip` (string; optional; management IP address literal (no port))
  - `tags` (array of strings; optional)
  - `provider_asset_ref` (string; optional; provider native ID)
- `parameters` (object):
  - `input_args_redacted` (object)
  - `input_args_sha256` (string)
  - `resolved_inputs_sha256` (string; `sha256:<hex>` form)
  - `command_summary` (string; redacted-safe or placeholder)
- `criteria_ref` (object; optional; if known):
  - `criteria_pack_id` (string)
  - `criteria_pack_version` (string)
  - `criteria_entry_id` (string)
- `expected_telemetry_hints` (object; optional; lossy, non-authoritative)
- `idempotence` (string; `idempotent|non_idempotent|unknown`)
- `requirements` (object; optional; present when requirements evaluation is performed):
  - `declared` (object)
  - `evaluation` (string; `satisfied|unsatisfied|unknown`)
  - `results` (array)
- `lifecycle` (object):
  - `phases` (array of objects), each:
    - `phase` (`prepare|execute|revert|teardown`)
    - `attempt_ordinal` (int; optional; present for retries; monotonic for a given phase)
    - `phase_outcome` (`success|failed|skipped`)
    - `reason_domain` (string; required when not `success`; MUST equal `ground_truth`)
    - `reason_code` (string; required when not `success`)
    - `started_at_utc`, `ended_at_utc` (ISO-8601 UTC)
    - `evidence` (object; optional pointers to artifacts under `runner/actions/<action_id>/...`)
- `extensions` (object; optional):
  - `synthetic_correlation_marker` (string; present when enabled and `execute` was attempted)
  - (other keys reserved)

### Principal selection (non-secret) (normative)

Scenarios MAY specify a human-meaningful principal selector:

- `plan.execution.principal_alias` (string, optional)

Requirements:

- The value MUST be a non-secret alias token (examples: `user`, `admin`, `svc`).
- The runner MUST map the alias to an actual execution principal via runner configuration. Scenarios
  MUST NOT embed credentials or secret material.
- The effective principal alias (explicit or default) MUST participate in action identity:
  - It MUST be incorporated into the resolved inputs hash basis under the reserved key
    `__pa_principal_alias_v1` (string).
  - Reserved-key collisions MUST fail closed.

Evidence:

- The runner records the typed principal identity context for the run in
  `runner/principal_context.json`.

## Seed schema: Scenario definition (v0.1)

```yaml
scenario_id: "scn-2026-01-001"
scenario_version: "0.1.0"
name: "Atomic T1059.001 Powershell"
description: "Basic PowerShell execution and related telemetry"
posture:
  mode: "assumed_compromise"
safety:
  allow_network: false
targets:
  - selector:
      roles: ["endpoint"]
      os: ["windows"]
plan:
  type: "atomic"
  technique_id: "T1059.001"
  engine_test_id: "<atomic-guid>"
  idempotence: "unknown"
  execution:
    principal_alias: "admin"
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
  "run_id": "<uuid>",
  "scenario_id": "scn-2026-01-001",
  "scenario_version": "0.1.0",
  "action_id": "s1",
  "action_key": "<sha256-hex>",
  "timestamp_utc": "2026-01-03T12:00:00Z",
  "engine": "atomic",
  "engine_test_id": "<atomic-guid>",
  "technique_id": "T1059.001",
  "target_asset_id": "asset-001",
  "resolved_target": {
    "role": "endpoint",
    "os": "windows",
    "hostname": "host-001",
    "ip": "192.0.2.10"
  },
  "criteria_ref": {
    "criteria_pack_id": "ocsf-win",
    "criteria_pack_version": "1.0.0",
    "criteria_entry_id": "T1059.001"
  },
  "expected_telemetry_hints": {
    "ocsf_class_uids": [1001, 1005]
  },
  "parameters": {
    "input_args_redacted": {
      "command": "whoami"
    },
    "input_args_sha256": "<sha256-hex>",
    "resolved_inputs_sha256": "sha256:<hex>",
    "command_summary": "<WITHHELD:REDACTION_DISABLED>"
  },
  "requirements": {
    "declared": {
      "platform": { "os": ["windows"] },
      "privilege": "admin",
      "tools": ["powershell"]
    },
    "evaluation": "satisfied",
    "results": [
      { "kind": "platform", "key": "windows", "status": "satisfied", "reason_domain": "requirements_evaluation", "reason_code": "satisfied" },
      { "kind": "privilege", "key": "admin", "status": "satisfied", "reason_domain": "requirements_evaluation", "reason_code": "satisfied" },
      { "kind": "tool", "key": "powershell", "status": "satisfied", "reason_domain": "requirements_evaluation", "reason_code": "satisfied" }
    ]
  },
  "idempotence": "unknown",
  "lifecycle": {
    "phases": [
      {
        "phase": "prepare",
        "phase_outcome": "success",
        "started_at_utc": "2026-01-03T12:00:00Z",
        "ended_at_utc": "2026-01-03T12:00:01Z",
        "evidence": {
          "requirements_evaluation_ref": "runner/actions/s1/requirements_evaluation.json"
        }
      },
      {
        "phase": "execute",
        "phase_outcome": "success",
        "started_at_utc": "2026-01-03T12:00:01Z",
        "ended_at_utc": "2026-01-03T12:00:05Z",
        "evidence": {
          "executor_ref": "runner/actions/s1/executor.json",
          "stdout_ref": "runner/actions/s1/stdout.txt",
          "stderr_ref": "runner/actions/s1/stderr.txt"
        }
      },
      {
        "phase": "revert",
        "phase_outcome": "success",
        "started_at_utc": "2026-01-03T12:00:05Z",
        "ended_at_utc": "2026-01-03T12:00:06Z",
        "evidence": {
          "executor_ref": "runner/actions/s1/executor.json",
          "cleanup_stdout_ref": "runner/actions/s1/cleanup_stdout.txt",
          "cleanup_stderr_ref": "runner/actions/s1/cleanup_stderr.txt"
        }
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
  },
  "extensions": {
    "synthetic_correlation_marker": "pa:synth:v1:<uuid>:s1:execute"
  }
}
```

## Ground truth timeline entry (v0.2+; deterministic action_id)

When the plan execution model is enabled (multi-action plans), each emitted action line MUST use a
deterministic `action_id` of the form `pa_aid_v1_<32hex>` as defined in the data contracts spec.

```json
{
  "run_id": "<uuid>",
  "scenario_id": "scn-2026-01-001",
  "scenario_version": "0.1.0",
  "action_id": "pa_aid_v1_4d3a9c0f2b1e7a1f6c8d9e0a1b2c3d4e",
  "action_key": "<sha256-hex>",
  "template_id": "atomic/T1059.001/<atomic-guid>",
  "timestamp_utc": "2026-01-03T12:00:00Z",
  "engine": "atomic",
  "engine_test_id": "<atomic-guid>",
  "technique_id": "T1059.001",
  "target_asset_id": "asset-001",
  "parameters": {
    "resolved_inputs_sha256": "sha256:<hex>"
  },
  "idempotence": "unknown",
  "lifecycle": {
    "phases": [
      { "phase": "prepare", "phase_outcome": "success", "started_at_utc": "2026-01-03T12:00:00Z", "ended_at_utc": "2026-01-03T12:00:01Z" },
      { "phase": "execute", "phase_outcome": "success", "started_at_utc": "2026-01-03T12:00:01Z", "ended_at_utc": "2026-01-03T12:00:05Z" },
      { "phase": "revert", "phase_outcome": "success", "started_at_utc": "2026-01-03T12:00:05Z", "ended_at_utc": "2026-01-03T12:00:06Z" },
      { "phase": "teardown", "phase_outcome": "success", "started_at_utc": "2026-01-03T12:00:06Z", "ended_at_utc": "2026-01-03T12:00:07Z" }
    ]
  }
}
```

## Key decisions

- Scenarios define what to execute while lab providers resolve concrete targets.
- v0.1 supports atomic test plans and treats other scenario types as reserved.
- Scenario posture is expressed via `posture.mode` and is recorded in run provenance for planning
  and reporting.
- Action identity is derived from `action_key_basis_v1` using RFC 8785 canonicalization.
- Target selection must be deterministic when selectors match multiple assets.

## Appendix: Action lifecycle state machine representation

This appendix is **representational only**. It is included to make the action lifecycle easier to
reason about and to align the document with ADR-0007's guidance for state machine notation. It MUST
NOT be treated as introducing new lifecycle requirements.

Lifecycle authority references:

- This document:
  - [Action lifecycle](#action-lifecycle)
  - [Allowed transitions (finite-state machine, normative)](#allowed-transitions-finite-state-machine-normative)
  - [Recording requirements (normative)](#recording-requirements-normative)
- [ADR-0007 State machines for lifecycle semantics](../adr/ADR-0007-state-machines.md)

### Machine overview

- **Scope**: per-action lifecycle for a single `(run_id, action_id)` pair.
- **Authoritative state representation**: `ground_truth.jsonl` -> `lifecycle.phases[]` ordering and
  `(phase, phase_outcome, reason_code)` tuples.

### States (closed set)

| State      | Kind         | Description (mapping)                                                           |
| ---------- | ------------ | ------------------------------------------------------------------------------- |
| `init`     | initial      | No lifecycle phase records have been written for the action.                    |
| `prepare`  | intermediate | `prepare` phase is being attempted (or is the next phase to attempt).           |
| `execute`  | intermediate | `execute` phase is being attempted (or is the next phase to attempt).           |
| `revert`   | intermediate | `revert` phase is being attempted (or is the next phase to attempt).            |
| `teardown` | intermediate | `teardown` phase is being attempted (or is the next phase to attempt).          |
| `done`     | terminal     | The lifecycle has been fully recorded through `teardown` (including `skipped`). |

### Events and triggers

| Event                     | Meaning                                                       |
| ------------------------- | ------------------------------------------------------------- |
| `event.prepare_recorded`  | A `prepare` phase record is present in `lifecycle.phases[]`.  |
| `event.execute_recorded`  | An `execute` phase record is present in `lifecycle.phases[]`. |
| `event.revert_recorded`   | A `revert` phase record is present in `lifecycle.phases[]`.   |
| `event.teardown_recorded` | A `teardown` phase record is present in `lifecycle.phases[]`. |

### Transition mapping

This table summarizes the *allowed* ordering and the most important gating rules described in this
spec. Guards are expressed in terms of the phase outcomes recorded in ground truth.

| From state | Event                     | Guard (authoritative semantics)                                                                                                                                                                                       | To state   |
| ---------- | ------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- |
| `init`     | `event.prepare_recorded`  | Always                                                                                                                                                                                                                | `prepare`  |
| `prepare`  | `event.execute_recorded`  | `prepare.phase_outcome=success` -> `execute` is attempted; otherwise `execute.phase_outcome=skipped` with a stable `reason_code`                                                                                      | `execute`  |
| `execute`  | `event.revert_recorded`   | `revert` is attempted only when `execute` was attempted; otherwise `revert.phase_outcome=skipped` with `reason_code=prior_phase_blocked` (when cleanup is enabled) or `cleanup_suppressed` (when cleanup is disabled) | `revert`   |
| `revert`   | `event.teardown_recorded` | `teardown` is recorded after `revert` (attempted or skipped). When cleanup is enabled, `teardown` is typically attempted even when earlier phases failed.                                                             | `teardown` |
| `teardown` | `event.teardown_recorded` | Once `teardown` is recorded, the lifecycle is complete for the action.                                                                                                                                                | `done`     |

### Illegal transition surface

If an implementation is asked to force an invalid lifecycle ordering or to re-run a `non_idempotent`
action unsafely, this spec requires that the lifecycle evidence surfaces stable enforcement reason
codes (emitted in lifecycle phase records with `reason_domain="ground_truth"`):

- `invalid_lifecycle_transition`
- `unsafe_rerun_blocked`

See the authoritative "Allowed transitions" section for the normative requirements and the
`logs/health.json` linkage.

## References

- [Data contracts spec](025_data_contracts.md)
- [Lab providers spec](015_lab_providers.md)
- [Atomic Red Team executor integration spec](032_atomic_red_team_executor_integration.md)
- [Validation criteria spec](035_validation_criteria.md)
- [Redaction policy ADR](../adr/ADR-0003-redaction-policy.md)
- [State machines ADR](../adr/ADR-0007-state-machines.md)

## Changelog

| Date      | Change                                                                                               |
| --------- | ---------------------------------------------------------------------------------------------------- |
| 1/24/2026 | update                                                                                               |
| 1/19/2026 | align scenario types with plan execution model; align ground truth seed/examples with data contracts |
| 1/13/2026 | Define allow_network enforcement + validation hook                                                   |
| 1/10/2026 | Style guide migration (no technical changes)                                                         |
