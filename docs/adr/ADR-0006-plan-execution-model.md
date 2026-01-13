---
title: 'ADR-0006: Plan execution model and target cardinality'
description: Establishes the plan graph execution model and reserves matrix plan semantics for multi-target iteration.
status: draft
category: adr
---

# ADR-0006: Plan execution model and target cardinality

## Status

Draft

## Context

Purple Axiom v0.1 enforces a strict 1:1 relationship between an action and a target asset:

> Each executed action MUST resolve to exactly one `target_asset_id` in `ground_truth.jsonl`. If a
> selector matches multiple assets, the runner/provider MUST select deterministically [one].

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

**Plan graph definition:**

```
plan_graph:
  nodes:
    - id: "<action_instance_id>"
      action: { technique_id, engine_test_id, target_asset_id, input_args, ... }
      status: pending | running | succeeded | failed | skipped
  edges:
    - from: "<node_id>"
      to: "<node_id>"
      condition: "always | on_success | on_failure | on_any"
```

**Key properties:**

- A plan graph with no edges represents embarrassingly parallel execution (matrix semantics).
- A plan graph with linear edges represents sequential execution.
- A plan graph with branching edges represents conditional/campaign execution (future).

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

A matrix plan declares axes and expansion rules:

```yaml
plan:
  type: "matrix"
  axes:
    techniques: ["T1059.001"]
    engine_test_ids: ["<guid>"]
    targets:
      selector: { os: "windows" }
      foreach_matched: true
    input_variants: ["default"]  # future: support multiple input sets
  expand: ["targets"]  # which axes to iterate; others are held constant
  execution:
    order: "sequential"  # or "parallel"
    concurrency: 1       # max parallel actions (1 = serial)
```

**Expansion semantics:**

- For each axis listed in `expand`, the planner enumerates all matching values.
- The Cartesian product of expanded axes determines the set of action instances.
- Each action instance receives a unique `action_id` and computes its own `action_key`.

**Determinism requirements:**

- Axis enumeration MUST be deterministic (targets sorted by `asset_id` bytewise lexical; techniques
  and test IDs sorted lexically).
- Execution order (when `order: "sequential"`) MUST follow the enumeration order.
- The expanded plan graph MUST be recorded in the run bundle for reproducibility.

### 4. Ground truth and reporting implications

**Ground truth:**

- Each (test × target) pair emits its own line in `ground_truth.jsonl`.
- `action_key` remains the stable join key (already includes `target_asset_id`).
- A new field `plan_expansion_ref` MAY link back to the matrix cell coordinates.

**Reporting:**

- Summary aggregation gains a `by_target` dimension.
- Matrix runs produce a coverage matrix artifact showing (technique × target × status).
- Regression comparison can diff `action_key` sets across runs to detect coverage changes.

### 5. v0.1 amendment: Explicit reservation

The scenario model spec (`030_scenarios.md`) MUST be amended to:

1. Explicitly state that multi-target iteration is not supported in v0.1.
1. Reserve the `matrix` plan type for v0.2.
1. Note that the `action_key` design is forward-compatible with target expansion.
1. Require implementations to fail closed with `reason_code=plan_type_reserved` if a matrix plan is
   encountered in v0.1.

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
- The plan graph model adds conceptual overhead for simple single-action scenarios.

### Trade-offs

- Choosing the DAG model over simpler iteration means more upfront design work, but avoids
  architectural debt.
- Exposing `foreach_matched` as a selector-level flag (Option A from initial analysis) would be
  simpler but less extensible; the matrix plan type is preferred for long-term flexibility.

## Implementation notes

### Plan graph schema (seed)

The plan graph schema will be defined in a dedicated spec document (`031_plan_execution_model.md`).
Key requirements:

- `plan_graph.schema.json` MUST validate expanded plan graphs.
- The schema MUST support node status tracking for progress reporting.
- The schema MUST support edge conditions for future sequencing.

### Daemon/UI considerations

For daemon or UI implementations:

- The plan graph is introspectable (UI can enumerate nodes and show progress).
- Total action count = number of nodes (enables progress bars).
- Each node has independent status (enables partial failure display).
- Plan templates can expose axes as user-selectable parameters.

### Migration path

- v0.1 runs with `plan.type: "atomic"` compile to a single-node graph internally.
- v0.2 introduces the `matrix` compiler; existing atomic plans remain valid.
- v0.3+ adds edge support for sequencing.

## References

- [Scenario model spec](../spec/030_scenarios.md)
- [Data contracts spec](../spec/025_data_contracts.md)
- [Lab providers spec](../spec/015_lab_providers.md)

## Changelog

| Date      | Change        |
| --------- | ------------- |
| 1/13/2026 | Initial draft |
