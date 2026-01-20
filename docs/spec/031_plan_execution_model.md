---
title: Plan execution model
description: Defines the plan graph model, template-vs-instance semantics, and execution ordering for multi-action runs.
status: reserved
category: spec
tags: [plan, execution, matrix, graph]
related:
  - 030_scenarios.md
  - 025_data_contracts.md
  - ADR-0004-deployment-architecture-and-inter-component-communication.md
  - ADR-0005-stage-outcomes-and-failure-classification.md
---

# Plan execution model

> **Status: Reserved for v0.2+**
>
> This document defines the v0.2+ plan execution model and seeds v0.3+ (`sequence`), v0.4+
> (`campaign`), and future adaptive branching. v0.1 remains single-action only (see "v0.1
> behavior").
>
> Where this document uses normative language (MUST/SHOULD/MAY), it applies only when the described
> feature is implemented and enabled. In v0.1, reserved plan types MUST fail closed as specified.

## Purpose

Define:

- The internal compiled plan graph model executed by the runner.
- The template-vs-instance semantics that preserve cross-run comparability.
- The deterministic compilation and scheduling rules required for reproducibility, auditing, and
  fixture-driven verification.

A core objective is to preserve comparability by separating:

- reusable procedure definitions (templates), and
- run-scoped executions of those procedures (instances).

## Scope

When implemented, this spec defines:

- Compiled plan artifacts written to the run bundle:

  - `plan/expanded_graph.json` (compiled plan graph; immutable evidence)
  - `plan/expansion_manifest.json` (enumeration inputs + expansion coordinate mapping)
  - `plan/template_snapshot.json` (optional; may be embedded in `expanded_graph.json`)
  - `plan/execution_log.jsonl` (optional; scheduler journal for multi-action runs)

- Template vs instance model:

  - stable procedure identity (`template_id`)
  - run-scoped correlation (`action_id`)
  - stable cross-run join key (`action_key`)

- Plan types and compilation rules:

  - v0.1: `atomic`
  - v0.2+: `matrix`
  - v0.3+: `sequence` (seed)
  - v0.4+: `campaign` (seed)
  - future: `adaptive` (seed)

- Deterministic expansion rules (axes, binding, coordinates)

- Deterministic execution ordering and concurrency semantics

- Forward-compatibility rules for schema evolution (`extensions`, reserved fields)

- Verification hooks (fixtures and conformance tests)

This spec does not replace the scenario authoring model spec. The scenario spec governs user-facing
scenario YAML; this spec governs the compiled graph representation and runner execution semantics.

## Design goals

### Determinism and reproducibility

A conforming implementation MUST be able to:

- deterministically compile the same plan inputs into byte-equivalent canonical identity bases, and
- deterministically schedule eligible actions in a stable order basis, regardless of platform.

### Forward compatibility

The v0.2 design MUST preserve the ability to add future plan models without redesigning the core
runner by enforcing:

- A single internal representation: a directed graph of action instance nodes plus dependency edges.
- Versioned, additive schema evolution:
  - strict core fields, plus
  - free-form `extensions` objects for future and project-specific growth.

### Auditability and testability

- Compilation MUST emit sufficient artifacts to reproduce the compiled graph exactly.
- Ordering MUST be explainable and fixture-testable.
- Failures MUST be observable via stable `reason_code`s and evidence references.

### Safety and redaction

Plan artifacts MUST be safe to retain as long-term evidence. Sensitive values MUST NOT be written
unredacted into plan artifacts; see `ADR-0003-redaction-policy.md` and `025_data_contracts.md`.

## Concepts and terminology

### Entities

- **Action template**: A reusable procedure definition that describes what to run independent of a
  particular run. Templates are comparable across time. A template has a stable `template_id`.
- **Action instance**: A run-scoped instantiation of an action template after plan expansion. An
  instance binds a concrete target and concrete inputs and has:
  - `action_id` (run-scoped correlation key; deterministic in v0.2+)
  - `action_key` (stable across runs; join key for regression)
- **Plan**: A user-facing specification that selects templates and declares expansion and execution
  semantics.
- **Plan graph**: The compiled internal representation (nodes + edges) that the runner executes.
- **Expansion coordinate**: A structured coordinate attached to a node that records which expanded
  dimensions produced the node (for example target and variable axes). In this document the field is
  called `cell` for continuity; it is not limited to matrix-only semantics.
- **Node ordinal (`node_ordinal`)**: A deterministic 0-based ordinal assigned to each node in the
  canonical execution order basis. Used for stable identity and reporting.
- **Group**: An optional reporting organization construct (folder-like). Groups MUST NOT affect
  identity, ordering, or execution.
- **Threat-driven index** (optional, v0.2+ seed): A curated list of prioritized techniques or
  templates used to generate plans. Indexes evolve over time and should be versioned.

### Concept mapping (informative)

| External concept class | Closest Purple Axiom concept        |
| ---------------------- | ----------------------------------- |
| Environment            | Range / lab environment             |
| Assessment             | Run (`run_id`)                      |
| Campaign               | Plan group + compiled plan graph    |
| Test case template     | Action template (v0.2+)             |
| Test execution         | Action instance node + evidence log |

## Compatibility and versioning

### Plan model version vs contract version

Compiled plan artifacts carry two version surfaces:

- **Contract version**: `contract_version` identifies the JSON schema for validation (for example
  `plan_graph_v1`).
- **Plan model version**: `plan_model_version` identifies the semantics version of the plan compiler
  and scheduler as a SemVer string (for example `0.2.0`).

Schema evolution rules:

- Patch/minor plan model versions MUST be backwards compatible within the same contract major.
- Breaking changes require a new contract version and a new plan model major.

### Extensibility rules

To preserve forward compatibility:

- Core objects in contracted artifacts SHOULD set `additionalProperties=false` in their schemas.
- Each core object that requires future growth MUST include an `extensions` object:
  - `extensions` MUST be a JSON object.
  - Consumers MUST ignore unknown keys under `extensions`.
  - Producers MUST NOT rely on consumers understanding `extensions` keys for core correctness.

Reserved fields:

- Fields documented as "reserved" MAY appear in artifacts only when the corresponding feature gate
  is enabled. When present, reserved fields MUST be deterministic and schema-backed (or carried
  under `extensions`).

## v0.1 behavior (normative)

In v0.1, the plan execution model is intentionally constrained:

- Only `atomic` plan type is supported.
- Each plan compiles to a single-node graph with no edges.
- Target selection resolves to exactly one asset per action.

If a v0.1 runner encounters a plan type other than `atomic`, it MUST fail closed with
`reason_code=plan_type_reserved`.

Implementation guidance (non-normative):

- Even in v0.1, implementations SHOULD compile the `atomic` plan into the same internal plan graph
  structure used by v0.2+ (single node, no edges). This minimizes architectural churn when
  multi-action plans are enabled.

## Plan types

### Reserved plan types

The following plan types are reserved and will be defined in future versions:

| Plan type  | Target version | Description                                             |
| ---------- | -------------- | ------------------------------------------------------- |
| `matrix`   | v0.2           | Combinatorial expansion over axes                       |
| `sequence` | v0.3+          | Ordered plan fragments with explicit ordering semantics |
| `campaign` | v0.4+          | DAG of named fragments with conditional edges           |
| `adaptive` | Future         | Runtime branching based on results (dynamic graph)      |

### Plan composition model (v0.2+ intent)

All plan types compile to the same compiled representation:

- **Nodes** represent action instances (fully specified: template + target + resolved inputs).
- **Edges** encode dependencies and activation conditions.

The compiler MAY internally treat user plans as hierarchical fragments (for example a sequence of
matrix fragments), but the emitted `expanded_graph.json` MUST be a flattened graph of action
instance nodes.

Forward-compatibility invariants:

- A compiled plan graph MUST be valid even if the plan authoring surface evolves.
- A node MUST be joinable to:
  - its action evidence (`runner/actions/<action_id>/...`),
  - ground truth timeline rows (`ground_truth.jsonl`),
  - and (optionally) expansion coordinates (`plan/expansion_manifest.json`).

## Graph model invariants (v0.2+, normative when implemented)

Unless explicitly stated otherwise for a future plan type:

- The compiled plan graph MUST be a directed acyclic graph (DAG).
- Each node MUST have:
  - `action_id` (unique within the run)
  - `action_key` (unique within the run; collision is fatal)
  - `node_ordinal` (unique within the run; 0-based)
- Each edge MUST reference existing node ids.
- Node and edge arrays in the emitted graph MUST be deterministically ordered (see "Deterministic
  serialization and ordering").
- The compiler MUST enforce a maximum expanded node count:
  - The limit MUST be configurable (see config reference `plan.max_nodes`).
  - If the limit is exceeded, the runner MUST fail closed before executing any action instances.

## Plan compilation phases (v0.2+, normative when implemented)

Plan compilation MUST proceed in deterministic phases.

### Phase 0: Input materialization and pinning

The compiler MUST materialize a run-scoped view of all plan inputs required for compilation, such
as:

- the scenario plan document (as provided),
- the inventory snapshot and any selector results,
- execution definition sources (Atomic/Caldera/custom),
- any optional index packs.

Where a plan depends on external packs or discovery results, the compiler MUST snapshot or record
hashes sufficient to reproduce the same compilation outputs.

### Phase 1: Template resolution

The compiler MUST resolve all referenced action templates into a run-scoped snapshot:

- Each resolved template MUST have a stable `template_id` (see "Action template identity").
- The compiler MUST record sufficient descriptive metadata in `template_snapshot` to support audit
  without requiring the upstream repo checkout.

### Phase 2: Axis enumeration (matrix and other expansion dimensions)

For plans that expand over axes, the compiler MUST enumerate axis values deterministically and
record the enumeration basis in `expansion_manifest.json`.

### Phase 3: Expansion into node candidates

The compiler MUST produce an initial set of node candidates from the cartesian product of the
selected templates and the expanded coordinate space.

Each node candidate MUST include:

- `template_id`
- `engine`, `technique_id`, `engine_test_id` (or equivalent engine identifiers)
- `target_asset_id`
- an expansion coordinate `cell` (when expansion applies)

### Phase 4: Input resolution and hashing

For each node candidate, the compiler (or runner, prior to execution) MUST compute:

- a deterministically resolved and redaction-safe inputs basis, and
- `parameters.resolved_inputs_sha256` (as specified by the data contracts spec and engine
  integration).

Note: `parameters.resolved_inputs_sha256` MUST incorporate the effective principal alias and merged
requirements when those inputs are part of the scenario semantics (see scenario model stable
identity requirements).

### Phase 5: Dependency and edge construction

The compiler MUST construct dependency edges:

- Explicit edges from the user plan (sequence/campaign).
- Implied edges (for example sequence step ordering semantics).

For v0.2 matrix-only plans with no ordering constraints, the edge set MAY be empty.

### Phase 6: Canonical ordering and `node_ordinal` assignment

The compiler MUST compute a deterministic canonical ordering basis and assign `node_ordinal` as a
0-based index in that order.

- For a DAG, the canonical ordering MUST be a deterministic topological sort (see below).
- For an edgeless graph, the canonical ordering MUST be a deterministic total order over node
  candidates derived from expansion enumeration.

### Phase 7: `action_id` and `action_key` computation and uniqueness checks

The compiler or runner MUST compute:

- `action_key` from `action_key_basis_v1` as defined by the data contracts spec.
- `action_id` (v0.2+) from `action_instance_basis_v1` as defined by the data contracts spec.

Uniqueness and safety checks (normative):

- `action_key` MUST be unique within the run. Duplicate `action_key` MUST fail closed with
  `reason_code=action_key_collision`.
- `action_id` MUST be unique within the run. Duplicate `action_id` indicates a deterministic
  identity bug and MUST fail closed.

### Phase 8: Artifact emission

The runner MUST emit plan artifacts prior to executing nodes (unless v0.1 single-action mode):

- `plan/expanded_graph.json`
- `plan/expansion_manifest.json`

`plan/template_snapshot.json` MAY be emitted separately or embedded in the expanded graph.

If `plan/execution_log.jsonl` is emitted, it MUST be written deterministically (see below).

## Deterministic expansion coordinates (cell encoding)

### Dimension token rules (normative)

- Dimension tokens (including `expand[]` entries) MUST be treated as opaque strings.
- Dimension tokens MUST NOT be split or tokenized (for example, `variables.user` is a single token).

### `cell.path` rules (normative)

- `cell.path` MUST be an array of dimension tokens in deterministic order.
- For a pure v0.2 `matrix` plan, `cell.path` MUST equal the plan’s `expand[]` array exactly (same
  elements, same order).
- For composite plan types (sequence/campaign), the compiler MAY inject additional reserved
  dimension tokens. When injected, they MUST be appended after all user-specified `expand[]` tokens,
  and MUST be recorded in the manifest.

### `cell.coord` rules (normative)

- `cell.coord` MUST be an object whose keys are exactly the dimension tokens listed in `cell.path`.
- `cell.coord` MUST include exactly one value per token in `cell.path` (no extra keys, no missing
  keys).
- Coordinate values MUST be JSON scalars (string/number/bool) unless the plan model explicitly
  permits structured values in a future version.

## Axis enumeration determinism (v0.2 matrix; normative when implemented)

For matrix plans, compilation MUST define a total order over:

- template selections, and
- axis values,

so the expanded graph is reproducible.

### Template enumeration rules

- Resolved templates MUST be enumerated in ascending lexical order of `template_id` (bytewise UTF-8,
  no locale).

### Axis value enumeration rules

- The `targets` axis results MUST be enumerated in ascending lexical order of `target_asset_id`.
- User-supplied axis value arrays (for example `variables.user: ["alice", "bob"]`) MUST be
  enumerated in the order provided in the plan document.
- Any axis values derived from selectors, queries, or discovery MUST be enumerated in a
  deterministic sorted order defined by the compiler and recorded in `expansion_manifest.json`.

## Identity, determinism, and hashing

This project is determinism-driven. Plan identity must be stable and reproducible.

### Stable identifiers overview (informative)

Within a run:

- `action_id` joins runner evidence artifacts to ground truth. Across runs:
- `action_key` is the stable join key for regression comparisons. Within and across runs:
- `template_id` is the stable procedure identity.

### Action template identity (v0.2+, normative when implemented)

An action template MUST have a stable identifier `template_id` that is:

- stable across runs, and
- stable across machines given identical template identity inputs.

`template_id` MUST be treated as an opaque string by consumers.

#### Engine-defined `template_id` rules (normative)

Each engine integration spec MUST define how `template_id` is computed.

For `engine=atomic`, `template_id` MUST be:

- `atomic/<technique_id>/<engine_test_id>`

(See `032_atomic_red_team_executor_integration.md`.)

#### Optional filename-safe derived id (reserved)

Some contexts require filename-safe tokens. A future version MAY define a derived identifier
`template_uid` computed as a truncated SHA-256 of a canonical identity basis object:

- `template_uid` is reserved for file naming and internal indexing only.
- `template_uid` MUST NOT replace or rename `template_id`.

### Action instance identity and join keys (v0.2+, normative when implemented)

A conforming implementation MUST compute:

- `action_key` per `action_key_basis_v1` (stable across runs).
- `action_id` per `action_instance_basis_v1` (run-scoped correlation key; deterministic in v0.2+).

These bases and hashing rules are defined in the data contracts spec and scenario model spec. This
document adds plan-graph-specific constraints:

- The `node_ordinal` used in `action_instance_basis_v1` MUST be derived from the canonical ordering
  algorithm defined in this spec.
- Groups and other presentational metadata MUST NOT participate in identity-bearing bases.

### Execution ordering determinism (v0.2+, normative when implemented)

The runner MUST execute a plan graph deterministically in terms of scheduling decisions.

- If the graph is a DAG, the canonical order MUST be a deterministic topological sort.
- When multiple nodes are eligible (no unsatisfied dependencies), tie-breaking MUST be deterministic
  using an ordering key tuple that MUST NOT depend on runtime timing and MUST NOT depend on
  `action_id` (to avoid circularity).

#### Canonical ordering key (normative)

The compiler MUST compute a deterministic per-node ordering key:

1. `cell.path` (missing sorts first; otherwise lexicographic by element)
1. `cell.coord` (missing sorts first; otherwise compared by canonical JSON bytes)
1. `template_id` (lexicographic)
1. `target_asset_id` (lexicographic)
1. `parameters.resolved_inputs_sha256` (lexicographic)
1. `engine_test_id` (lexicographic; when applicable; missing sorts first)

Notes:

- `cell.*` MAY be omitted for non-expanded plans; omission sorts before presence.
- Comparing `cell.coord` by canonical JSON bytes implies the canonicalization rules defined in
  `025_data_contracts.md`.

#### Deterministic topological sort (normative)

For DAG ordering, the compiler MUST:

- perform a Kahn-style topological sort, and
- maintain a stable priority queue of eligible nodes ordered by the canonical ordering key above.

Cycle handling:

- If a cycle is detected, compilation MUST fail closed before execution.
- The reason code for cycle detection is reserved for v0.2+ and MUST be specified before emission.

#### Concurrency interaction (normative)

Concurrency MAY be introduced, but:

- the canonical ordering basis MUST still be recorded (via `node_ordinal` and stable node arrays),
  and
- eligible node selection MUST follow canonical ordering when choosing which node(s) to start next.

## Scheduling semantics (v0.2+, normative when implemented)

### Execution modes

Plans MAY request an execution mode via `plan.execution.order`:

- `sequential`: execute one eligible node at a time (concurrency effectively 1)
- `parallel`: execute eligible nodes concurrently without dependency edges (reserved)
- `dag`: execute eligible nodes concurrently subject to dependency edges

Configuration clamps:

- The effective concurrency MUST be bounded by:
  - plan requested concurrency, and
  - global config `plan.execution.concurrency`.
- If the plan requests `dag` but the implementation does not support DAG scheduling yet, the runner
  MUST fail closed (reserved reason code).

### Fail-fast policy

Plans MAY declare a fail-fast policy (v0.2+ intent), and config provides a default:

- `plan.fail_fast` (default `false` per config reference)

Semantics:

- If fail-fast is enabled, once any node execution attempt results in a terminal failed outcome, the
  scheduler MUST stop scheduling new nodes and MUST mark remaining unscheduled nodes as skipped with
  a stable reason code (reserved).
- Already-running nodes MAY be allowed to complete; cancellation semantics are reserved and MUST be
  explicitly specified before destructive cancellation is introduced.

## Plan graph schema (seed)

This section defines the seed structure for the v0.2 plan graph. It is non-normative until v0.2, but
is intended to be directly translatable into JSON Schema.

```yaml
# Seed structure (non-normative until v0.2)
plan_graph:
  contract_version: "plan_graph_v1"
  plan_model_version: "0.2.0"
  run_id: "<run_id>"
  scenario_id: "<scenario_id>"
  scenario_version: "<scenario_version>"
  generated_at_utc: "2026-01-15T20:12:00Z"
  plan_type: "matrix" # or "atomic", "sequence", "campaign", "adaptive" (reserved)

  # Snapshot of the templates referenced by this plan, so the run remains reproducible even if the
  # upstream repo changes later.
  template_snapshot:
    source: "repo"
    templates:
      - template_id: "atomic/T1059.001/<guid>" # engine-defined stable template id
        engine: "atomic"
        technique_id: "T1059.001"
        engine_test_id: "<guid>"
        name: "<template_name>"
        phase: "<optional_phase>"
        source_ref: "<optional_upstream_revision>"
        source_tree_sha256: "<optional_tree_hash>"

  # Optional organizational groups for reporting. Groups MUST NOT affect execution semantics.
  groups:
    - group_id: "pa_gid_v1_<sha256-128>"
      name: "Execution - PowerShell"
      tags: ["baseline"]

  nodes:
    - action_id: "pa_aid_v1_<sha256-128>"
      action_key: "pa_ak_v1_<sha256-128>"
      node_ordinal: 0

      template_id: "atomic/T1059.001/<guid>"
      technique_id: "T1059.001"
      engine: "atomic"
      engine_test_id: "<guid>"
      target_asset_id: "<asset_id>"

      parameters:
        resolved_inputs_sha256: "sha256:<hex>"

      # Optional reporting group association (presentational only).
      # Group membership MUST NOT affect identity or ordering.
      group_id: "pa_gid_v1_<sha256-128>"

      # Expansion coordinate information. Omit if the plan does not expand.
      cell:
        path: ["targets", "variables.user"]
        coord:
          targets: "<asset_id>"
          variables.user: "alice"

      # Schema-managed extension space for future versions.
      extensions: {}

  edges:
    - from: "pa_aid_v1_<sha256-128>"
      to: "pa_aid_v1_<sha256-128>"

      # Structural meaning of the edge.
      kind: "depends_on" # reserved enum: depends_on | ordered_before | conditional

      # Activation semantics (reserved; aligns with campaign/adaptive models).
      # For v0.2 matrix DAGs, producers SHOULD emit "always" when present.
      condition: "always" # reserved: always | on_success | on_failure | on_any

      extensions: {}
```
