---
title: 'ADR-0006: Plan execution model and target cardinality'
description: Establishes the plan graph execution model and reserves matrix plan semantics for multi-target iteration.
status: draft
category: adr
---

# ADR-0006: Plan execution model and target cardinality

## Context

Purple Axiom v0.1 enforces a strict 1:1 relationship between an action and a target asset:

> Each executed action MUST resolve to exactly one `target_asset_id` in `ground_truth.jsonl`. If a
> selector matches multiple assets, the runner/provider MUST select deterministically using stable
> ordering over `lab.assets[].asset_id` (UTF-8 byte order, no locale).

Note: `target_asset_id` is the stable lab asset identifier (`lab.assets[].asset_id`) resolved from the run's pinned inventory snapshot (`logs/lab_inventory_snapshot.json`). v0.1 "single-target" selection is therefore deterministic over that snapshot, not dependent on live provider state.

This design makes it impossible to express scenarios like:

- "Run T1059.001 on ALL Windows hosts" (to test coverage across OS versions)
- "Execute this technique against both the domain controller and a workstation"
- "Regression test this detection rule across Server 2016, Server 2019, and Windows 11"

**Consequences of the current design:**

- The range becomes a single-host test harness rather than a multi-asset validation platform.
- Broad regression testing requires generating many separate run bundles, which fragments reporting
  and complicates trend analysis.
- Future daemon, TUI, or web interfaces cannot offer "run across all matching targets" as a single
  operation.

**Why the 1:1 constraint exists:**

The v0.1 constraint was intentional for initial simplicity:

1. Determinism is easier to guarantee with single-target resolution.
1. `action_key` computation (which includes `target_asset_id`) already supports distinct keys per
   (test × target) pair—this is forward-compatible with expansion.
1. Multi-action complexity was deferred to focus on core pipeline validation.

This ADR establishes the architectural direction for lifting the 1:1 constraint while preserving
determinism and enabling future UI/daemon capabilities.

## Decision

### 1. Internal execution model: Plan graph

The plan execution engine MUST be designed around a directed acyclic graph (DAG) model internally,
even when the user-facing plan type is simpler.

**Plan graph shape (illustrative; non-normative):**

```yaml

plan_graph:
  scenario_posture:
    mode: "baseline" # baseline | assumed_compromise
  nodes:
    - action_id: "<action_id>"
      action_key: "<action_key>"
      node_ordinal: 0
      template_id: "<template_id>"
      target_asset_id: "<target_asset_id>"
      parameters:
        resolved_inputs_sha256: "sha256:<hex>"
      extensions: {}
  edges:
    - from: "<action_id>"
      to: "<action_id>"
      condition: "always | on_success | on_failure | on_any"
      extensions: {}
  extensions: {}
```

Notes:

- In v0.2+, the immutable expanded node/edge set MUST be recorded in `plan/expanded_graph.json`.
- When plan execution is enabled (v0.2+), the graph root MUST record the effective posture
  (`scenario_posture.mode`) for auditability.
- Node execution status is runtime state and MUST be tracked without mutating the compiled plan
  artifacts (for example via the ground truth timeline plus runner evidence, and optionally a
  separate scheduler journal such as `plan/execution_log.jsonl` when defined/implemented).

**Key properties:**

- A plan graph with no edges encodes no inter-node dependencies (a "matrix" fragment). Nodes MAY
  still be executed sequentially or in parallel depending on scheduler configuration.
- A plan graph with linear edges encodes explicit ordering dependencies (sequence semantics).
- A plan graph with branching edges encodes conditional activation (campaign semantics; reserved).

**Rationale:**

Designing around the DAG model from the start avoids architectural rewrites when adding sequencing,
dependencies, or adaptive execution. User-facing plan types become "compilers" that emit plan
graphs.

### 2. User-facing plan types (evolution path)

| Version | Plan type         | Description                           | Graph shape           |
| ------- | ----------------- | ------------------------------------- | --------------------- |
| v0.1    | `atomic` (single) | Single action, single target          | Single node, no edges |
| v0.2    | `matrix`          | Combinatorial expansion over axes     | N nodes, no edges     |
| v0.3+   | `sequence`        | Ordered action list with dependencies | Linear chain          |
| v0.4+   | `campaign`        | DAG with conditional edges            | Arbitrary DAG         |
| Future  | `adaptive`        | Runtime branching based on results    | Dynamic DAG           |

### 3. Matrix plan type (reserved for v0.2)

A matrix plan declares axes and expansion rules. This ADR reserves the semantics; the v0.2 authoring
schema is specified in the scenario model spec.

Illustrative example (non-normative):

```yaml
plan:
  type: "matrix"
  axes:
    templates:
      - "atomic/T1059.001/<guid>"  # template_id: atomic/<technique_id>/<engine_test_id>
    targets:
      selector: { os: "windows" }
    input_variants: ["default"]    # reserved for future input sets
  expand: ["targets"]              # which axes to iterate; others are held constant
  execution:
    order: "sequential"            # or "parallel"
    concurrency: 1                 # requested max parallel actions (1 = serial)
```

**Expansion semantics:**

- For each axis listed in `expand`, the compiler enumerates all matching values:
  - Selector-based axes (for example `targets.selector`) resolve to 0..N concrete values.
  - List-valued axes (for example `templates`, `input_variants`) are enumerated as provided.
- The Cartesian product of the expanded axes determines the action instances (graph nodes).
- Each action instance MUST:
  - be fully specified (template + target + resolved inputs),
  - receive a deterministic `node_ordinal` in canonical order,
  - compute its own `action_id` and `action_key` per the data contracts.

**Determinism and safety requirements:**

- Enumeration MUST be deterministic and MUST be computed solely from the run's pinned inventory
  snapshot (`logs/lab_inventory_snapshot.json`) plus the scenario plan (no live provider queries
  during compilation):
  - Templates MUST be enumerated in ascending lexical order of `template_id` (bytewise UTF-8, no
    locale).
  - Selector-resolved `targets` MUST be sorted by `target_asset_id` ascending (UTF-8 byte order, no
    locale).
  - User-specified axis arrays (for example `input_variants`) MUST be enumerated in the order
    provided (no implicit sorting).
- If any axis listed in `expand` resolves to 0 concrete values (for example a selector matches no
  targets), compilation MUST fail closed before executing any action instances. (TODO: specify the
  `reason_code` in ADR-0005 when matrix plans are implemented.)
- `expand[]` MUST be treated as an ordered list of opaque dimension tokens. For a pure `matrix`
  plan, expansion coordinates MUST use `cell.path == expand[]` (same elements, same order).
- `node_ordinal` MUST be unique within the run and 0-based, and MUST be assigned by the canonical
  ordering algorithm defined in the plan execution model spec (`031_plan_execution_model.md`).
- Execution order (when `order: "sequential"`) MUST follow ascending `node_ordinal`.
- Any axis not listed in `expand` MUST resolve to exactly one concrete value (singleton). If an
  unexpanded axis would yield 2+ values, compilation MUST fail closed (prefer
  `reason_code=config_schema_invalid`).
- The compiler MUST enforce the configured maximum expanded node count (`plan.max_nodes`). If the
  limit is exceeded, the runner MUST fail closed with `reason_code=plan_expansion_limit` before
  executing any action instances.
- Requested per-plan concurrency MUST be clamped to `plan.max_concurrency`.
- The expanded plan graph MUST be recorded in the run bundle for reproducibility:
  - `plan/expanded_graph.json` (required; flattened node/edge graph)
  - `plan/expansion_manifest.json` (required for matrix plans; records axis enumeration and `cell`
    coordinates)

### 4. Ground truth and reporting implications

**Ground truth:**

- Each action instance (template × target × inputs) emits its own line in `ground_truth.jsonl`.
- `action_id` and `action_key` remain the stable join keys across runner evidence, scoring, and
  reporting.
- Matrix expansion coordinates MUST be recoverable by joining `ground_truth.jsonl` rows to
  `plan/expanded_graph.json` and `plan/expansion_manifest.json` (required for matrix plans; may be
  absent for non-expanded `atomic` plans). No new top-level field is required in the ground truth
  contract for this linkage.

**Reporting:**

- Reporting SHOULD support segmentation by `target_asset_id` when more than one target is present.
- For matrix runs, the human report MAY render a technique × target coverage table derived from
  `ground_truth.jsonl` joined to the plan artifacts.
- Regression comparison MAY diff `action_key` sets (or `template_id` × `target_asset_id` pivots)
  across runs to detect coverage changes.

### 5. v0.1 amendment: Explicit reservation

The scenario model spec (`030_scenarios.md`) MUST specify (v0.1):

1. Multi-target iteration is not supported in v0.1.
1. The `matrix` plan type is reserved for v0.2.
1. The `action_key` design is forward-compatible with target expansion.
1. Implementations MUST fail closed with `reason_code=plan_type_reserved` if a matrix plan is
   encountered in v0.1.

### 6. State machine integration (representational; non-normative)

This section is an illustrative lifecycle view only. It does not define new conformance
requirements; conformance is defined by the artifact contracts and stage outcome semantics
referenced below.

**Lifecycle authority references (per ADR-0007):**

- Scenario model spec: action lifecycle phases and `ground_truth.jsonl`
- Plan execution model spec: plan artifacts and scheduling semantics
- ADR-0005: runner stage outcomes and `reason_code` taxonomy

#### State machine: Plan node lifecycle (representational)

- **Machine ID (proposed):** `plan_node_lifecycle`
- **Version (seed):** `0.2.0`

**States (closed set):**

- `node_pending` (node exists in the compiled graph but dependencies/conditions may not yet permit scheduling)
- `node_ready` (node is eligible to be scheduled under the plan's dependency/condition semantics)
- `node_running` (runner has begun the node's action lifecycle)
- `node_succeeded` (node reached terminal success)
- `node_failed` (node reached terminal failure)
- `node_skipped` (node will not be executed)

**Transitions (informative):**

- `node_pending -> node_ready` (dependencies satisfied and conditions met, if any)
- `node_ready -> node_running` (runner starts the action lifecycle for the node)
- `node_running -> node_succeeded`
- `node_running -> node_failed`
- `node_pending | node_ready -> node_skipped` (conditional edge not met, fail-fast policy, or explicit skip policy; reserved)

**Observable signals (informative mapping):**

- Identity and membership: `plan/expanded_graph.json.nodes[]`
- Scheduling journal (when present): `plan/execution_log.jsonl`
- Execution timeline and outcomes: `ground_truth.jsonl` (join on `action_id`) plus per-node evidence
  under `runner/actions/<action_id>/`

## Consequences

### Positive

- The architecture supports future UI/daemon capabilities without a rewrite.
- Operators can express "run across all Windows hosts" as a single plan.
- Regression testing across OS variants becomes a first-class workflow.
- The plan graph model accommodates sequencing and conditional execution when needed.

### Neutral

- v0.1 behavior is unchanged; this ADR only reserves future capability.
- Implementation complexity increases in v0.2 when matrix plans are implemented.

### Negative

- Until v0.2, operators must use external orchestration or multiple run bundles for multi-target
  testing.
- Large selector-based expansions may exceed safety caps (for example `plan.max_nodes`) and be
  rejected deterministically, requiring operators to narrow selectors or split runs.
- The plan graph model adds conceptual overhead for simple single-action scenarios.

### Trade-offs

- Choosing the DAG model over simpler iteration means more upfront design work, but avoids
  architectural debt.
- Exposing `foreach_matched` as a selector-level flag on `atomic` plans would be simpler but less
  extensible; the matrix plan type is preferred for long-term flexibility.

## Implementation notes

### Plan graph schema (seed)

The plan execution model specification (`031_plan_execution_model.md`) defines the contracted v0.2+
plan artifacts and their determinism, versioning, and safety requirements. Key requirements (v0.2+):

- The expanded plan graph MUST be recorded at `plan/expanded_graph.json` and MUST validate against a
  contract schema (registered in `docs/contracts/contract_registry.json`).
- For matrix plans (v0.2+), `plan/expansion_manifest.json` MUST be emitted, MUST validate against
  its contract schema, and MUST be consistent with `plan/expanded_graph.json` (node ids,
  `node_ordinal`, and expansion coordinates).
- Compiled plan artifacts MUST be immutable after publish and MUST be safe to retain (no unredacted
  secrets or sensitive values).
- Runtime execution state (node statuses, scheduling decisions) MUST be tracked without mutating the
  compiled plan artifacts (for example via the ground truth timeline and runner evidence, and
  optionally a separate execution journal such as `plan/execution_log.jsonl` when defined/implemented).
- The compiler MUST enforce `plan.max_nodes`, and the runner MUST clamp requested concurrency to
  `plan.max_concurrency` per the configuration reference.

### Daemon/UI considerations

For daemon or UI implementations:

- The UI SHOULD enumerate nodes from the immutable compiled plan artifact
  (`plan/expanded_graph.json`) when present.
- Total action count = number of nodes in the compiled graph (enables progress bars).
- Per-node status SHOULD be derived from `ground_truth.jsonl` and runner evidence (for example, the
  presence of `runner/actions/<action_id>/executor.json` plus terminal timestamps), not by mutating
  the compiled plan artifact.
- Plan templates SHOULD expose matrix axes as user-selectable parameters, but the emitted expanded
  graph MUST remain deterministic for a given set of inputs.

### Migration path

- v0.1 runs with `plan.type: "atomic"` compile to a single-node graph internally.
- v0.2 introduces the `matrix` compiler; existing atomic plans remain valid.
- v0.3+ adds edge support for sequencing.

## References

- [Scenario model spec](../spec/030_scenarios.md)
- [Plan execution model spec](../spec/031_plan_execution_model.md)
- [Architecture spec](../spec/020_architecture.md)
- [Data contracts spec](../spec/025_data_contracts.md)
- [Config reference](../spec/120_config_reference.md)
- [Reporting spec](../spec/080_reporting.md)
- [ADR-0003: Redaction policy](ADR-0003-redaction-policy.md)
- [ADR-0005: Stage outcomes and failure classification](ADR-0005-stage-outcomes-and-failure-classification.md)
- [ADR-0007: State machines](ADR-0007-state-machines.md) 
- [Lab providers spec](../spec/015_lab_providers.md)

## Changelog

| Date      | Change                                                                    |
| --------- | ------------------------------------------------------------------------- |
| 1/28/2026 | update                                                             |
| 1/19/2026 | Align ADR with v0.2 plan artifacts, determinism ordering, and safety caps |
| 1/13/2026 | Initial draft                                                             |
