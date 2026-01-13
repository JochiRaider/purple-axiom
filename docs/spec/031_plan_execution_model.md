---
title: Plan execution model
description: Defines the plan graph model, matrix plan semantics, and execution ordering for multi-action runs.
status: reserved
category: spec
tags: [plan, execution, matrix, graph]
related:
  - 030_scenarios.md
  - 025_data_contracts.md
---

# Plan execution model

> **Status: Reserved for v0.2**
>
> This document is a placeholder. The plan execution model is defined architecturally in
> [ADR-0006](../adr/ADR-0006-plan-execution-model.md) but normative implementation requirements are
> deferred to v0.2.

## Purpose

Define the internal plan graph model and the user-facing plan types that compile to it. This spec
governs how plans with multiple actions (matrix expansion, sequencing, dependencies) are
represented, executed, and recorded.

## Scope

When implemented, this spec will define:

- Plan graph schema (`plan_graph.schema.json`)
- Matrix plan syntax and expansion rules
- Execution ordering and concurrency semantics
- Plan compilation from user-facing types to internal graph representation
- Progress tracking and partial failure handling
- Ground truth emission for multi-action plans

## v0.1 behavior

In v0.1, the plan execution model is implicit:

- Only `atomic` plan type is supported.
- Each plan compiles to a single-node graph with no edges.
- Target selection resolves to exactly one asset per action.

If a v0.1 runner encounters a plan type other than `atomic`, it MUST fail with
`reason_code=plan_type_reserved`.

## Reserved plan types

The following plan types are reserved and will be defined in future versions:

| Plan type  | Target version | Description                           |
| ---------- | -------------- | ------------------------------------- |
| `matrix`   | v0.2           | Combinatorial expansion over axes     |
| `sequence` | v0.3+          | Ordered action list with dependencies |
| `campaign` | v0.4+          | DAG with conditional edges            |
| `adaptive` | Future         | Runtime branching based on results    |

## Placeholder sections

The following sections will be populated when this spec is implemented:

### Plan graph schema

```yaml
# Seed structure (non-normative until v0.2)
plan_graph:
  version: "0.2.0"
  nodes:
    - id: "<action_instance_id>"
      action:
        engine: "atomic"
        technique_id: "T1059.001"
        engine_test_id: "<guid>"
        target_asset_id: "<asset_id>"
        input_args: {}
      status: "pending"
  edges: []
```

### Matrix plan syntax

```yaml
# Seed structure (non-normative until v0.2)
plan:
  type: "matrix"
  axes:
    techniques: ["T1059.001"]
    targets:
      selector: { os: "windows" }
      foreach_matched: true
  expand: ["targets"]
  execution:
    order: "sequential"
    concurrency: 1
```

### Expansion algorithm

Reserved.

### Execution semantics

Reserved.

### Artifacts

When implemented, matrix plans will produce:

- `runs/<run_id>/plan/expanded_graph.json` — the compiled plan graph
- `runs/<run_id>/plan/expansion_manifest.json` — axis enumeration and cell coordinates
- Enhanced `ground_truth.jsonl` with `plan_expansion_ref` field

## References

- [ADR-0006: Plan execution model](../adr/ADR-0006-plan-execution-model.md)
- [Scenario model spec](030_scenarios.md)
- [Data contracts spec](025_data_contracts.md)

## Changelog

| Date      | Change                           |
| --------- | -------------------------------- |
| 1/12/2026 | Initial stub (reserved for v0.2) |
