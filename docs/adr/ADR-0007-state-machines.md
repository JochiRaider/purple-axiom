---
title: ADR-0007 State machines for lifecycle semantics
description: Defines when and how Purple Axiom specifications should use explicit state machines for pipeline and executor lifecycles, and provides a reusable template.
status: draft
category: adr
tags: [state-machines, lifecycle, pipeline, executor, determinism, observability, conformance]
related:
  - ADR-0001-project-naming-and-versioning.md
  - ADR-0003-redaction-policy.md
  - ADR-0004-deployment-architecture-and-inter-component-communication.md
  - ADR-0005-stage-outcomes-and-failure-classification.md
  - ADR-0006-plan-execution-model.md
  - ../spec/020_architecture.md
  - ../spec/025_data_contracts.md
  - ../spec/030_scenarios.md
  - ../spec/031_plan_execution_model.md
  - ../spec/032_atomic_red_team_executor_integration.md
  - ../spec/040_telemetry_pipeline.md
  - ../spec/100_test_strategy_ci.md
  - ../spec/110_operability.md
---

# ADR-0007: State machines for lifecycle semantics

This ADR introduces a consistent, specification-first way to describe lifecycle behavior as explicit
state machines where doing so improves determinism, observability, and testability. It also provides
a copy/paste state machine definition template intended for use in specs.

## Context

Purple Axiom is specified as a stage-scoped pipeline where each stage reads inputs from the run
bundle and writes outputs back to the run bundle, with deterministic publish gates and stage
outcomes.

Even in a strictly linear pipeline, there are multiple lifecycles that are naturally stateful:

- Run-scoped orchestration (locks, stage sequencing, publish gates, completion)
- Stage-scoped execution (pending/running/published/failed/skipped)
- Action-scoped execution within the runner (prepare/execute/revert/teardown)
- Plan-scoped scheduling (node readiness, execution, completion and skips)
- Telemetry-scoped reliability behaviors (checkpointing and validation gates)

Several existing specifications already define lifecycle rules that are, in practice, finite-state
machines (FSMs), but they are not always explicitly presented as such.

As the project grows (for example, additional plan types, retries, richer resume semantics, more
substage outcomes), the risk increases that lifecycle behavior becomes implicit, divergent across
components, or hard to test.

## Decision

Purple Axiom specifications MAY use explicit state machines to describe lifecycle behavior. When a
spec chooses to introduce lifecycle semantics as a state machine, it MUST do so using the template
in this ADR and MUST conform to the requirements below.

This ADR is intentionally specification-focused. It does not require adopting a specific runtime
state machine framework.

### Normative vs representational state machines

Purple Axiom specifications MAY use state machine notation in two distinct ways:

1. **Normative state machine definitions (conformance-critical)**

   These define or override lifecycle semantics and MUST be treated as part of the specification
   contract.

   - Normative state machines MUST use the template in this ADR.
   - Normative state machines MUST include conformance tests as required by this ADR.

1. **Representational state machines (non-normative)**

   These are diagrams or simplified lists used to explain an existing flow. They MUST NOT introduce
   new lifecycle requirements.

   - Representational state machines MUST be explicitly labeled as representational/non-normative.
   - Representational state machines MUST cite their lifecycle authority references and MUST NOT
     conflict with those authoritative semantics.
   - Representational state machines MUST NOT be used as the sole conformance-critical signal for CI
     gating.

### What a "state machine" means in Purple Axiom specs

A **state machine definition** is a specification artifact that:

- enumerates a closed set of states
- enumerates allowed transitions between those states
- defines triggers/guards for transitions
- defines entry/exit actions (including side effects)
- defines what is observable at each state and transition
- defines conformance tests that prove an implementation matches the definition

A state machine definition is not required to introduce new storage artifacts. When possible, it
SHOULD map state to existing contracted artifacts (manifest, stage outcomes, ground truth, evidence
artifacts) rather than introducing a new "state store".

If a normative state machine requires a new persisted artifact (for authoritative state and/or
required observability), the owning spec MUST:

- declare the artifact path as part of the run bundle IO boundary for the owning stage/component,
  and
- define schema and validation requirements for the artifact using the project’s contract workflow.

### Where state machines fit

State machines are appropriate anywhere Purple Axiom needs a deterministic, testable lifecycle with
observable boundaries.

The following are the primary intended "state machine insertion points". These are guidance, not a
new normative stage list.

1. **Orchestrator run lifecycle machine**

   - Represents: orchestration control flow for a run (lock acquisition, stage execution loop,
     completion).
   - Primary lifecycle authority: ADR-0004 (run sequence / IO boundaries / publish semantics) and
     ADR-0005 (stage outcome and run status derivation).

1. **Stage execution machine (per stage)**

   - Represents: stage-level lifecycle ("pending → running → published", plus failure/skip
     behavior).
   - Primary lifecycle authority: ADR-0004 publish gate semantics and ADR-0005 stage outcomes.

1. **Runner action lifecycle machine (per action)**

   - Represents: the action lifecycle phases and the allowed phase transitions.
   - Primary lifecycle authority: scenarios (action lifecycle), runner/executor integration, and
     runner-specific outcome aggregation rules.

1. **Plan node lifecycle machine (per node)**

   - Represents: plan execution scheduling and node status transitions.
   - Primary lifecycle authority: ADR-0006 and the plan execution model spec.

1. **Reliability and safety lifecycles**

   - Represents: bounded stateful behaviors such as "checkpoint is absent/healthy/corrupt",
     "redaction allowed/withheld/quarantined", "egress canary passed/failed".
   - Primary lifecycle authority: the relevant pipeline stage spec plus ADR-0003/ADR-0005 as
     applicable.

#### Canonical artifact anchors (guidance)

State machines SHOULD prefer contracted run-bundle artifacts as both:

- the **authoritative state representation** (crash recovery / resume), and
- the **primary observability surface** (explainability and CI gating).

The table below summarizes typical artifact anchors by machine scope. This table is guidance only;
each spec that defines a machine MUST still declare its authoritative representation using the
template in this ADR.

| Machine scope               | Typical authoritative artifacts                                                                                                                                      | Typical terminal outcome record                                                                                                 |
| --------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| Run                         | Run lock (`runs/.locks/<run_id>.lock`), `manifest.json`, and `logs/health.json` (when enabled)                                                                       | `manifest.status` (derived), plus stage outcomes in `manifest.json` (and mirrored in `logs/health.json` when enabled)           |
| Stage                       | Stage outcome entry in `manifest.json` (and `logs/health.json.stages[]` when enabled), plus publish-gate output artifacts per the stage’s IO boundary table          | Stage `status/fail_mode/reason_code` in `manifest.json` (and in `logs/health.json` when enabled), which feeds `manifest.status` |
| Action                      | `runner/actions/<action_id>/side_effect_ledger.json` (ordered entries), per-action evidence artifacts, `ground_truth.jsonl` (timeline)                               | Per-action outcomes recorded in contracted artifacts (ground truth and/or runner evidence)                                      |
| Plan node                   | Ground truth timeline and/or a plan execution journal artifact (when present)                                                                                        | Node terminal status recorded in the chosen journal/ground truth form                                                           |
| Reliability/safety canaries | Dotted stage outcomes in `manifest.json` (and `logs/health.json` when enabled), plus deterministic evidence artifacts (for example `logs/telemetry_validation.json`) | Dotted stage outcomes that feed the parent stage and run status                                                                 |

### Requirements for state machines in specs

When a spec defines a state machine using the template below:

1. **Closed vocabulary**

   - The set of states MUST be explicitly enumerated.
   - The set of events/triggers that drive transitions MUST be explicitly enumerated.

1. **Deterministic transitions**

   - For any `(state, event)` pair, behavior MUST be deterministic.
   - If multiple transitions could apply, the spec MUST define a deterministic precedence rule.

1. **Idempotency and crash safety**

   - Entry/exit actions that write contracted artifacts MUST be idempotent.
   - If the machine can be observed across process boundaries (for example, a crash and rerun), the
     spec MUST define the authoritative state representation derived from run bundle artifacts.
   - For run- and stage-scoped lifecycle machines, the authoritative state SHOULD be derivable from
     publish-gate boundaries and outcome artifacts. In particular, stage terminal state SHOULD be
     derivable from:
     - the recorded stage outcome, and
     - the presence/absence of the stage’s published outputs as defined by ADR-0004 completion
       semantics and the stage’s IO boundary table.
   - Specs MUST define deterministic handling for inconsistent artifact states (for example,
     published outputs present but no recorded terminal outcome), and SHOULD fail closed by default.

- When the inconsistency implies a missing required artifact, specs SHOULD prefer
  `reason_code = input_missing`.
- When the inconsistency implies partial publish, unreadable artifacts, or storage corruption, specs
  SHOULD prefer `reason_code = storage_io_error`.

1. **Observability is not optional**

   - Each state MUST declare at least one observable signal (artifact presence/content, log line
     pattern, counter, stage outcome).

   - Each transition MUST declare its observable signals, including failure modes.

     Note: `logs/health.json` is a stage outcome surface (stage outcomes only) and MUST NOT be
     treated as a generic per-transition event log. Transition-level evidence SHOULD be captured via
     deterministic counters, structured logs, and/or dedicated evidence artifacts as defined by the
     owning spec.

1. **Alignment with outcome semantics**

   - If a state machine drives or aggregates stage outcomes, the mapping MUST be consistent with
     ADR-0005.
   - If a state machine introduces new stage-level `reason_code` values, ADR-0005 MUST be updated in
     the same change set. (This ADR does not add reason codes.)

1. **Conformance tests are required**

   - The definition MUST include a minimal set of conformance tests that can be automated.
   - Tests MUST verify both allowed transitions and illegal transition handling.

### Interlocking state machines and boundaries

State machines in Purple Axiom commonly compose in a parent/child structure:

- **Run lifecycle (orchestrator)** is the parent machine for the run.
- **Stage machines** are child machines executed under the run lifecycle.
- The **runner stage** commonly owns additional child machines, including:
  - **plan node lifecycle** (scheduling),
  - **action lifecycle** (execution and cleanup).

Composition requirements (normative):

- A parent machine MUST integrate with a child machine only through:
  - the child machine’s contracted artifacts, and/or
  - the child machine’s terminal outcome (status + reason classification) as recorded in the run
    bundle.
- A parent machine MUST NOT depend on a child machine’s in-memory state or non-contracted side
  effects.
- If a child machine’s internal state must be recovered after process restart, it MUST be
  represented by contracted artifacts in the run bundle.

Rationale: this preserves the "run bundle as single source of truth" property and keeps runs
explainable by inspection.

### What this represents in development

A state machine definition typically translates to a small set of concrete implementation artifacts:

- **State and event enums**: closed sets matching the spec.

- **A pure transition function**: `next_state = transition(current_state, event, context)` plus a
  list of intended side effects.

- **A side-effect layer** that performs artifact writes atomically and idempotently (publish gate
  semantics apply where relevant).

- **Guards and refusal behavior** for illegal transitions, with observable signals (stage outcomes
  in `logs/health.json`, counters).

- **Conformance tests** that exercise transitions and validate the produced artifacts (golden files
  where applicable).

Implementations MAY use an off-the-shelf state machine library, but they MUST preserve:

- deterministic transition selection
- stable identifiers and reason codes
- artifact-based observability

For executor implementations specifically:

- The executor SHOULD treat the per-action lifecycle phases as a state machine and enforce allowed
  transitions (for example, preventing re-execution of non-idempotent actions without successful
  revert), with outcomes surfaced via ground truth and runner stage/substage outcomes.
  - For action lifecycle enforcement, implementations SHOULD reuse the existing observability
    surfaces:
    - `runner.lifecycle_enforcement` substage semantics (when `health.json` is enabled), including
      `reason_code` values such as `invalid_lifecycle_transition` and `unsafe_rerun_blocked` (see
      ADR-0005 and the executor integration specs).
    - stable counters for illegal transitions and unsafe rerun blocks as defined by operability.

### Non-goals

- This ADR does not require a generic "state machine engine" or DSL in the runtime.
- This ADR does not require that every stage or component be rewritten as an explicit state machine.
- This ADR does not change the canonical pipeline stage ordering or stage outcome taxonomy.

## State machine definition template

Copy/paste this section into any spec that needs an explicit state machine. The filled-in version
becomes normative for that spec.

### State machine: \<machine_name>

#### Purpose

- **What it represents**: <one paragraph>
- **Scope**: \<run | stage | action | component | other>
- **Machine ID**: `<id_slug_v1>` (see ADR-0001)
- **Version**: `<semver>` (increment when semantics change)

#### Lifecycle authority references

To avoid duplication, this state machine reuses lifecycle semantics defined elsewhere.

List the authoritative documents/sections here and treat this section as a mapping/overlay:

- <link to existing lifecycle section 1>
- <link to existing lifecycle section 2>

If this state machine definition conflicts with the linked lifecycle authority, the linked lifecycle
authority is authoritative unless this spec explicitly states it is overriding those semantics.

#### Entities and identifiers

- **Machine instance key**: \<how to uniquely identify a machine instance; examples: `run_id`,
  `stage_id`, `action_id`, `node_id`>
- **Correlation identifiers** (optional): \<how transitions correlate to manifest entries, ground
  truth rows, or stage outcome records>

#### Authoritative state representation

Describe how an implementation determines the current state. Prefer derivation from contracted
artifacts.

- **Source of truth**: \<artifact path(s) + selector(s)>
- **Derivation rule**: \<deterministic rule that maps artifact state → machine state>
- **Persistence requirement**:
  - MUST persist: \<yes/no>
  - If yes, MUST be persisted in: \<artifact path(s)>

#### Events / triggers

Enumerate the events that can be presented to the state machine.

- `event.<name>`: <definition>

Event requirements (normative):

- Events MUST be named with ASCII `lower_snake_case` after the `event.` prefix.
- If events can be processed in batches or from streams, the spec MUST define deterministic
  ordering.

#### States

Provide a closed set of states.

State requirements (normative):

- States MUST be named as ASCII `lower_snake_case`.
- States MUST be stable within the declared version.
- Terminal states MUST be explicitly identified.

| State     | Kind                                    | Description | Invariants | Observable signals |
| --------- | --------------------------------------- | ----------- | ---------- | ------------------ |
| `<state>` | `initial` / `intermediate` / `terminal` | <text>      | <text>     | <text>             |

#### Transition rules

Define allowed transitions. Guards must be explicit and deterministic.

Transition requirements (normative):

- Each transition MUST specify:
  - from_state
  - event
  - guard conditions (if any)
  - to_state
  - entry actions and/or exit actions (including artifact writes)
  - failure mapping (how errors are classified and surfaced)

| From state | Event          | Guard (deterministic) | To state  | Actions (entry/exit) | Outcome mapping                                 | Observable transition evidence |
| ---------- | -------------- | --------------------- | --------- | -------------------- | ----------------------------------------------- | ------------------------------ |
| `<state>`  | `event.<name>` | <predicate>           | `<state>` | <actions>            | \<mapping to stage outcome, ground truth, etc.> | <evidence>                     |

#### Entry actions and exit actions

Detail side effects. If actions write artifacts, specify atomicity, validation, and idempotency.

- **Entry actions**:

  - `<state>`:
    - <action>

- **Exit actions**:

  - `<state>`:
    - <action>

Requirements (normative):

- Artifact writes that define or advance state MUST be atomic or fail closed.
- Entry/exit actions MUST be idempotent with respect to the authoritative state representation.
- If an action is intentionally non-idempotent, the spec MUST define the guardrails that prevent
  unsafe re-execution.

#### Illegal transitions

Specify what happens for an unrecognized `(state, event)` or a violated guard.

- **Policy**: `<fail_closed | warn_and_skip | ignore>`
- **Classification**: \<how this surfaces in stage outcomes / warnings / logs>
- **Observable evidence**: <what proves this occurred>

Requirements (normative):

- Illegal transitions MUST NOT silently mutate state.
- Illegal transitions MUST be observable.
- If the machine is part of runner/action lifecycle enforcement, the spec SHOULD map illegal
  transition evidence to existing lifecycle enforcement surfaces (for example, a dotted health
  substage and stable counters) rather than inventing new, machine-specific ad-hoc signals.

#### Observability

Define the required observable signals for both steady-state and transitions. For lifecycle
semantics that affect run status, stage outcomes, or CI gating, specs SHOULD prefer deterministic
artifact-based observability (health entries, counters, and evidence artifacts) over console-only
logs. Human-readable logs remain useful, but must not be the sole conformance-critical signal for
CI.

- **Required artifacts**: <list>
- **Structured logs** (optional): <list>
- **Human-readable logs**: <list>
- **Counters/metrics** (optional): <list>

Requirements (normative):

- Observability signals MUST be deterministic for equivalent inputs.
- If a state machine affects run status or CI gating, it MUST map to deterministic artifacts
  consumed by reporting and/or CI.

#### Conformance tests

Define tests that prove an implementation follows the state machine.

Minimum conformance suite (normative):

1. **Happy path**: transitions from initial state to a terminal success state.
1. **Each terminal failure mode**: at least one fixture per terminal failure state.
1. **Illegal transition handling**: attempt an illegal transition and verify policy and
   observability.
1. **Idempotency**: repeat at least one transition (or re-run after simulated crash) and verify no
   duplicated side effects and stable state derivation.
1. **Determinism**: run the same fixture twice and assert identical artifact content for
   state-related outputs (excluding explicitly non-deterministic fields such as timestamps, if
   permitted by the relevant contract).

Tests MUST:

- be automatable in CI
- use deterministic fixtures and golden files where appropriate
- validate both artifact existence and artifact content/schema

## Consequences

Benefits:

- Lifecycle behavior becomes explicit and reviewable.
- "What happens next" and "what can happen" are constrained and testable.
- Observability expectations become contractual, improving operability and CI gating.
- Interlocking lifecycle behavior (run/stage/action/plan) can be described without inventing ad-hoc
  terminology.

Costs:

- Specs gain additional structure that must be maintained.
- Implementations may need small additional plumbing (state enums, transition guards, tests) even
  when the runtime remains linear.

## Follow-ups

Non-blocking follow-ups enabled by this ADR:

- Add explicit state machine sections (using the template) where lifecycle semantics are currently
  implicit, prioritizing:
  - runner action lifecycle enforcement
  - plan node scheduling
  - any reliability-critical telemetry checkpoint behavior
- Add conformance fixtures for lifecycle machines to the test strategy and CI harness.

## References

- [Architecture specification](../spec/020_architecture.md)
- [Data contracts specification](../spec/025_data_contracts.md)
- [Scenarios specification](../spec/030_scenarios.md)
- [Plan execution model specification](../spec/031_plan_execution_model.md)
- [Atomic Red Team executor integration](../spec/032_atomic_red_team_executor_integration.md)
- [Telemetry pipeline specification](../spec/040_telemetry_pipeline.md)
- [Operability specification](../spec/110_operability.md)
- [Test strategy and CI](../spec/100_test_strategy_ci.md)
- [ADR-0001: Project naming and versioning](ADR-0001-project-naming-and-versioning.md)
- [ADR-0003: Redaction policy](ADR-0003-redaction-policy.md)
- [ADR-0004: Deployment architecture and inter-component communication](ADR-0004-deployment-architecture-and-inter-component-communication.md)
- [ADR-0005: Stage outcomes and failure classification](ADR-0005-stage-outcomes-and-failure-classification.md)
- [ADR-0006: Plan execution model](ADR-0006-plan-execution-model.md)

## Changelog

| Date       | Change  |
| ---------- | ------- |
| 2026-01-20 | Updated |
