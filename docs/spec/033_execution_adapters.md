---
title: Execution adapters
description: Defines the internal execution adapter interface used by the runner to execute actions, declare capabilities, and emit deterministic evidence.
status: draft
category: spec
tags: [runner, adapters, execution, determinism, evidence]
related:
  - 020_architecture.md
  - 025_data_contracts.md
  - 030_scenarios.md
  - 031_plan_execution_model.md
  - 032_atomic_red_team_executor_integration.md
  - 035_validation_criteria.md
  - 090_security_safety.md
  - 100_test_strategy_ci.md
  - 120_config_reference.md
---

# Execution adapters

## Purpose

Execution adapters are first-class, swappable runner backends (Threatest "detonator" analogs) that
perform technique execution while preserving a stable, contract-backed evidence surface.

The goal is to make it feasible to add non-Atomic execution backends (for example: cloud technique
runners or agent-based frameworks) without polluting the runner core control flow.

## Scope

This specification defines:

- A stable internal interface for an **execution adapter**:
  - declares capabilities (local vs remote exec, cloud API execution, import-only, etc.)
  - declares supported correlation carriers
  - surfaces deterministic evidence metadata via contract-backed artifacts
- How execution adapters participate in:
  - adapter selection + provenance recording (composition root, adapter registry)
  - runner evidence emission (`runner/actions/<action_id>/...`)
- Shared verification hooks:
  - a conformance test suite all execution adapters MUST pass

This specification does **not** define:

- The full runner lifecycle state machine (see ADR-0007).
- The Atomic Red Team integration details (see `032_atomic_red_team_executor_integration.md`).
- The multi-action plan graph compiler (reserved for v0.2+, see `031_plan_execution_model.md`).

## Definitions

- **Execution adapter**: a concrete implementation selected by `runner.type` that can execute one or
  more action instances and emit deterministic evidence.
- **Executor variant**: an adapter-internal execution mechanism selector. In v0.1 Atomic execution,
  this is `runner.atomic.executor` (for example `invoke_atomic_red_team`).
- **Correlation marker**: a deterministic value computed by the runner (per action) and injected
  into telemetry so detections can be joined back to ground truth (for example
  `extensions.synthetic_correlation_marker` and `extensions.synthetic_correlation_marker_token`).
- **Correlation carrier**: a runner-declared correlation mechanism (capability id) that defines how
  a correlation marker is produced, recorded, and surfaced into telemetry (for example
  `synthetic_correlation_marker`).
- **Correlation carrier matrix**: an adapter-declared, deterministic mapping that specifies which
  transport surfaces are supported/required for a given correlation carrier, and any constraints
  that force tokenized forms.

## Architecture integration

Execution adapters are extension adapters and MUST follow the adapter wiring/provenance rules in
`020_architecture.md` ("Adapter wiring and provenance (v0.1; normative)").

### Port id and adapter ids

Adapter provenance entry requirements (normative):

- The execution adapter MUST be recorded as an adapter provenance binding with:
  - `port_id = "runner-execution-adapter"` (id_slug_v1)
  - `adapter_id = <runner.type>` (id_slug_v1; v0.1: `atomic`)
- Implementations MUST fail closed if `runner.type` selects an adapter that is not present in the
  adapter registry.

Notes:

- `runner.type` is a user-facing config value (see `120_config_reference.md`).
- The **executor variant** is not an adapter id. It is recorded in per-action evidence (for example
  `runner/actions/<action_id>/executor.json.executor`) and used for criteria selection (see
  `035_validation_criteria.md`).

### Execution adapter boundary

To keep the runner core unpolluted:

- The runner core MUST NOT contain backend-specific logic for executing Atomics, invoking cloud
  APIs, or driving 3rd-party frameworks.
- The runner core MUST call the selected execution adapter through the stable interface defined here
  and MUST treat the adapter as the only component allowed to:
  - invoke backend tooling to perform technique execution, and
  - emit backend-specific evidence artifacts under `runner/actions/<action_id>/`.

The runner core remains responsible for:

- deterministic input resolution and hashing (`parameters.resolved_inputs_sha256`)
- writing ground truth timeline rows (`ground_truth.jsonl`)
- enforcing policy and stage boundaries (publish gate, redaction posture, egress posture)
- selecting and recording adapter provenance and run-level version pins

## Capability declaration

Execution adapters MUST declare capabilities to allow:

- deterministic selection (by the composition root) and
- deterministic validation of feature gates (for example, correlation carrier enablement).

### Capability object shape

Each execution adapter MUST provide a **capability descriptor** (in-memory object) with this shape:

- `schema_version` (required): `"pa:execution-adapter-capabilities:v1"`
- `adapter_id` (required; id_slug_v1): matches the adapter provenance `adapter_id` (example:
  `atomic`).
- `supported_execution_scopes` (required): array of supported execution scopes.
  - Allowed values (v1):
    - `local_exec` — executes on the orchestrator host
    - `remote_exec` — executes on a resolved target asset (agentless or agent-based)
    - `cloud_api` — executes via a cloud control plane API (no direct host command execution)
    - `import_only` — does not execute; imports externally generated evidence
  - Ordering: MUST be sorted ascending by UTF-8 byte order.
- `supported_correlation_carriers` (required): array of correlation carrier ids.
  - Ordering: MUST be sorted ascending by UTF-8 byte order.
  - v0.1 baseline: MUST include `synthetic_correlation_marker` for adapters that support that
    feature gate.
- `correlation_carrier_matrix`: object describing adapter-specific correlation injection behavior.
  - REQUIRED when `supported_correlation_carriers` includes `synthetic_correlation_marker`.
  - `schema_version` MUST equal `pa:correlation-carrier-matrix:v1`.
  - See "Correlation carrier matrix" for the normative shape and semantics.
- `supported_engines` (required): array of supported action engines.
  - Allowed values (v1): `atomic | caldera | custom`
  - Ordering: MUST be sorted ascending by UTF-8 byte order.
- `supported_executor_variants` (optional): array of supported executor variant identifiers.
  - Comparison: MUST be performed on lowercased values (see `035_validation_criteria.md` selector
    semantics).
  - Ordering: MUST be sorted ascending by UTF-8 byte order of the lowercased value.
  - v0.1 Atomic adapter: SHOULD include `invoke_atomic_red_team`, and MAY include `atomic_operator`
    and `other`.

Determinism requirements (normative):

- The capability descriptor MUST be fully deterministic:
  - MUST NOT include timestamps, hostnames, absolute host paths, random values, or per-run ids.
  - MUST use stable ordering for arrays as defined above.
- The adapter MUST validate its own capability descriptor at startup and fail closed if the
  descriptor is invalid.

## Correlation carriers

A correlation carrier is a runner-declared mechanism for embedding a correlation marker into
telemetry.

Correlation injection is adapter-specific: different execution adapters (detonator types) use
different transport surfaces (process arguments, environment variables, HTTP headers, marker events,
etc.). Purple Axiom MUST make this explicit via a per-adapter correlation carrier matrix.

### Correlation carrier matrix (normative)

Correlation is only as strong as its weakest backend. A single backend that cannot reliably carry
the marker forces heuristic fallbacks, which Purple Axiom avoids by default.

Each execution adapter that declares any correlation carrier in `supported_correlation_carriers`
MUST also declare `correlation_carrier_matrix` in its capability descriptor. The matrix MUST fully
describe, for that adapter, which transports are available and which are REQUIRED for deterministic
correlation.

#### Matrix object shape (normative)

`correlation_carrier_matrix`:

- `schema_version` (required): `pa:correlation-carrier-matrix:v1`
- `carriers` (required): array of carrier declarations.
  - Ordering: MUST be sorted ascending by UTF-8 byte order of `carrier_id`.
  - The matrix MUST include exactly one entry for each value in `supported_correlation_carriers`.
- `carriers[]` entry:
  - `carrier_id` (required): MUST match one of the values in `supported_correlation_carriers`.
  - `transports` (required): array of transport declarations for this carrier.
    - Ordering: MUST be sorted ascending by UTF-8 byte order of `transport_id`.
- `transports[]` entry:
  - `transport_id` (required; `id_slug_v1`): transport surface identifier (see below).
  - `required` (required): boolean.
  - `value_form` (required): `canonical | token | either`
    - `canonical`: transport MUST carry `extensions.synthetic_correlation_marker`.
    - `token`: transport MUST carry `extensions.synthetic_correlation_marker_token`.
    - `either`: transport MAY carry either form.
  - `constraints` (optional): object describing carrier limits that influence value form selection.
    - `max_chars` (optional): integer (character count; for these marker forms this is equivalent to
      byte count because they are ASCII).
    - `allowed_chars_regex` (optional): regex string (RE2-compatible recommended).
    - `notes` (optional): string

#### Value form selection (normative)

- The runner MUST compute and record both marker forms (canonical + token) as defined in
  `025_data_contracts.md`.
- For any transport where `value_form` includes `canonical`, the adapter MUST ensure the canonical
  marker satisfies the transport’s declared constraints (when present). For any transport where
  `value_form` includes `token`, the adapter MUST ensure the token satisfies the transport’s
  declared constraints (when present).
- Implementations MUST NOT perform heuristic correlation to compensate for missing required
  transport surfaces. When required transports cannot be used, the run MUST surface deterministic
  "missing telemetry" outcomes downstream.

#### Standard transport ids (v1, normative)

The following `transport_id` values are reserved for v1:

- `env-var-injection`: marker carried via environment variables.
- `parent-process-naming`: marker carried via parent process naming / parent identity fields.
- `command-line-argument-tagging`: marker carried via process command-line arguments.
- `http-header-tagging`: marker carried via HTTP headers and/or user-agent tagging (web/cloud
  techniques).
- `marker-event-emission`: marker carried via a dedicated marker-bearing event emitted immediately
  before the primary action execution.

#### v0.1 baseline matrices (normative)

`adapter_id="atomic"`:

- For carrier `synthetic_correlation_marker`, the adapter MUST declare at least one `required=true`
  transport and MUST ensure that transport results in marker-bearing telemetry when the carrier is
  enabled.
- v0.1 RECOMMENDED minimum required transport: `marker-event-emission`.

### v0.1 carrier: `synthetic_correlation_marker`

If enabled (`runner.atomic.synthetic_correlation_marker.enabled=true`):

- The runner MUST compute and record **both** of the following per action:
  - `extensions.synthetic_correlation_marker` (canonical marker string; see `025_data_contracts.md`)
  - `extensions.synthetic_correlation_marker_token` (deterministic derived token; see
    `025_data_contracts.md`)
- Marker-bearing telemetry emission is adapter-specific and MUST follow the adapter’s declared
  correlation carrier matrix:
  - For each `required=true` transport, the adapter MUST emit marker-bearing telemetry that carries
    either the canonical marker, the token, or both as specified by that transport’s `value_form`.
- The runner MUST also record the marker emission attempt in
  `runner/actions/<action_id>/side_effect_ledger.json` (contract: `side_effect_ledger`) before the
  emission attempt is made (see `032_atomic_red_team_executor_integration.md`).

The marker canonical format and token derivation are defined in `025_data_contracts.md`
(`extensions.synthetic_correlation_marker*`).

### v0.2+ carrier options (non-normative)

Future execution adapters MAY introduce additional carrier types, for example:

- `cloud_resource_tag`: tag cloud resources with a run/action token that surfaces in audit logs
- `framework_operation_id`: propagate a framework-native operation id (for example a Caldera
  operation id) into ground truth and evaluator join logic
- `trace_id`: propagate an OpenTelemetry trace/span id into telemetry (requires end-to-end trace
  plumbing)

Any new carrier MUST:

- be explicitly declared in adapter capabilities (`supported_correlation_carriers`)
- have deterministic formatting rules and storage locations
- have a contract-backed evidence surface (ground truth + normalized telemetry field)

## Evidence surfaces

Execution adapters MUST surface deterministic evidence metadata via contract-backed artifacts.

### Required evidence artifacts (v0.1 baseline)

The canonical runner evidence surface (paths + contract ids) is defined in:

- `025_data_contracts.md` ("Runner evidence"), and
- `030_scenarios.md` ("Runner evidence artifacts under runner/").

For v0.1 `engine="atomic"` actions, the runner MUST also implement the integration contract in
`032_atomic_red_team_executor_integration.md`, including its "Contracted runner artifacts" section.

This document normatively specifies only the adapter-owned portion of that surface.

For each attempted action where the execution adapter is invoked, the adapter MUST ensure the run
bundle contains, at minimum:

- `runner/actions/<action_id>/executor.json` (contract: `runner_executor_evidence`)
- `runner/actions/<action_id>/side_effect_ledger.json` (contract: `side_effect_ledger`)
- `runner/actions/<action_id>/side_effect_ledger.json` (contract: `side_effect_ledger`)
  - Required across all engines/adapters. When unsupported/not applicable, implementations MUST
    still emit the artifact at the standard path as a deterministic placeholder with
    `placeholder.handling=absent` (see `090_security_safety.md`).
- `runner/actions/<action_id>/resolved_inputs_redacted.json` (contract: `resolved_inputs_redacted`)
  - Required across all engines/adapters.
  - When the resolved inputs evidence cannot be produced deterministically for this engine/adapter,
    implementations MUST still emit the artifact at the standard path as a deterministic placeholder
    with `placeholder.handling=absent` (see `090_security_safety.md`).
  - Produced by the runner core input resolution step; execution adapters MUST treat it as an input.
- Transcript artifacts as configured (for example `stdout.txt`, `stderr.txt`) when enabled by the
  runner config and supported by the adapter.
  - If transcript capture is disabled, transcript artifacts MUST be absent (do not emit
    placeholders).
  - If transcript capture is enabled but content is withheld/quarantined by redaction policy,
    standard paths MUST contain deterministic placeholder artifacts per `090_security_safety.md`.
- Any engine-specific evidence required by the engine integration spec (for example `attire.json`
  for `engine="atomic"` actions; optional for other engines).

The execution adapter MUST NOT write evidence artifacts outside the `runner/` stage boundary.

### Deterministic evidence metadata requirements

At minimum, adapter evidence MUST make the following observable without relying on transcripts:

- which adapter executed the action (`runner.type`, recorded in manifest adapter provenance)
- which executor variant was used (recorded in `executor.json.executor` or equivalent)
- the redacted executed command representation (or a stable digest thereof)
  - v0.1 baseline for Atomic execution: `ground_truth.jsonl.extensions.command_sha256` (when
    available) plus `executor.json.invocation.*` per `032_atomic_red_team_executor_integration.md`
- which correlation carrier (if any) was used and its value or digest (via ground truth extension
  and side-effect ledger evidence)

If an adapter cannot provide a required metadata element, it MUST fail closed for that action unless
the metadata element is explicitly optional by contract or explicitly gated off by configuration.
Redaction-driven withholding/quarantine MUST be represented via placeholder artifacts, not silent
omission.

### Integration credential handling

Execution adapters frequently invoke external tooling or services that require authentication
(credentials, API tokens, private keys). These credentials MUST be treated as **integration
credentials** per the security specification.

Normative requirements:

- Execution adapters MUST obtain any required credentials via secret references (see
  `security.integration_credentials` in `120_config_reference.md`).
- Resolved credential values MUST be treated as in-memory only and MUST NOT be:
  - written into any contract-backed artifact under `runner/actions/<action_id>/`,
  - written into any other run bundle path (including `unredacted/` quarantine), or
  - written to logs.
- If a child process must receive a secret value and the integration supports environment-variable
  configuration, adapters MUST pass secret values via environment variables rather than argv.

## Interface contract (informative)

This specification is implementation-language agnostic. A conforming implementation SHOULD model the
execution adapter as an injected port with a stable interface similar to:

- `capabilities() -> capability_descriptor`
- `execute_action(action_context) -> execution_result`

Where:

- `action_context` includes only deterministic inputs:
  - run identifiers (`run_id`, `action_id`, `action_key`)
  - resolved target snapshot (from `lab_inventory_snapshot.json` selection)
  - resolved inputs artifact reference (`resolved_inputs_redacted.json`, when present)
  - effective runner config (with secrets withheld/redacted)
  - effective policy snapshot
- `execution_result` includes:
  - stable action phase outcomes and reason codes
  - references to contract-backed evidence artifacts produced under `runner/actions/<action_id>/`

## v0.1 execution adapters

### `atomic` execution adapter (required)

v0.1 implementations MUST support:

- `runner.type = "atomic"` selecting the `atomic` execution adapter, and
- action execution for `engine="atomic"` actions.

The `atomic` adapter’s detailed behavior and evidence contract is specified in
`032_atomic_red_team_executor_integration.md`.

Executor variants (v0.1, informative):

- `invoke_atomic_red_team` (reference executor for v0.1)
- `atomic_operator` (reserved / optional implementation)
- `other` (reserved vocabulary bucket)

## v0.2+ adapter options

This section describes plausible adapter families. It is non-normative and does not require
implementation in v0.1.

### Cloud API technique runners

Examples:

- AWS SSM Run Command / State Manager
- Azure Run Command / Automation
- GCP OS Config / Cloud Run Jobs

Design notes:

- Capability scope: `cloud_api` (may also support `remote_exec` if the adapter uses host agents)
- Preferred correlation carriers: `cloud_resource_tag`, `cloud_audit_marker`, and/or
  `synthetic_correlation_marker` when applicable
- Evidence emphasis: immutable API request/response digests and pinned policy snapshots

### Agent-based frameworks

Examples:

- Caldera (operation/ability model)
- Other adversary emulation platforms

Design notes:

- Capability scope: `remote_exec` (agent-based)
- Correlation carriers: framework-native operation ids and/or synthetic markers
- Evidence: framework result export snapshots + stable mapping to `(engine, engine_test_id)`

### Remote command execution adapters (agentless)

Examples:

- SSH / WinRM
- RPC-based execution on appliances

Design notes:

- Capability scope: `remote_exec`
- Correlation carriers: synthetic marker is the v0.2 "low coupling" default (write eventlog/syslog
  record or filelog line that is collected)

## Verification hooks

### Execution adapter conformance suite (required)

Every execution adapter implementation MUST pass a shared conformance suite.

Minimum conformance checks (normative):

1. **Contract validity**

   - All required artifacts in the fixture run MUST validate against their pinned JSON Schema
     contracts (contract registry binding).
   - The suite MUST fail if:
     - a required artifact is missing, or
     - any required artifact fails contract validation.

1. **Required evidence header**

   - Every contract-backed JSON evidence artifact under `runner/` MUST include the runner evidence
     header fields as defined in `025_data_contracts.md` ("Runner evidence JSON header pattern"):
     `contract_version`, `run_id`, `action_id`, `action_key`, `generated_at_utc`.

1. **Deterministic output ordering**

   - Any arrays declared by contracts or owning specs as "ordered" MUST be in the required stable
     order (UTF-8 byte order or explicitly defined domain order).
   - At minimum, the suite MUST check stable ordering for:
     - `manifest.extensions.adapter_provenance.entries[]` sorting rules, and
     - any adapter-specific ordered arrays (for Atomic execution, see
       `032_atomic_red_team_executor_integration.md` cleanup verification ordering requirements).

1. **Stable reason_code mapping on common failures**

   - For each adapter, the suite MUST include fixtures that trigger common failure classes and
     assert the emitted `reason_domain` + `reason_code` values.
   - Common failure classes (v0.1 baseline for Atomic execution) are enumerated in
     `032_atomic_red_team_executor_integration.md` (for example: `unsupported_executor`,
     `prereq_check_error`, `execution_failed`, `cleanup_failed`).

### Fixture layout (required)

Each adapter MUST provide conformance fixtures under:

- `tests/fixtures/runner/<adapter_id>/`

Minimum required fixture categories:

- `determinism/` — repeated-run fixtures that assert stable identity bases (for example stable
  `action_key` and stable `parameters.resolved_inputs_sha256`).
- `failure_reason_codes/` — fixtures that assert stable reason code mapping for common failures.

See `100_test_strategy_ci.md` ("Runner and execution") for fixture harness requirements.

## Changelog

| Date       | Change                                |
| ---------- | ------------------------------------- |
| 2026-02-11 | Introduce execution adapter interface |
