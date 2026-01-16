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

> **Status: Reserved for v0.2**
>
> This document defines the v0.2+ plan execution model. v0.1 remains single-action only (see "v0.1
> behavior"). Where this document uses normative language, it applies only when the feature is
> implemented and enabled.

## Purpose

Define the internal plan graph model and the user-facing plan types that compile to it. This spec
governs how plans with multiple actions (matrix expansion, sequencing, dependencies) are
represented, executed, and recorded.

A core objective is to preserve cross-run comparability by separating:

- reusable procedure definitions (templates), and
- run-scoped executions of those procedures (instances).

## Scope

When implemented, this spec defines:

- Plan graph schema (`plan_graph.schema.json`)
- Action template vs action instance model (stable procedure identity vs run-scoped execution)
- Plan types and compilation rules (`matrix`, `sequence`, `campaign`, `adaptive`)
- Matrix expansion rules (axes, binding, cell coordinates)
- Execution ordering and concurrency semantics
- Progress tracking, partial failure handling, and resumability hooks (reserved)
- Ground truth emission for multi-action plans
- Plan artifacts and deterministic hashing requirements
- Verification hooks (fixtures and conformance tests)

## Concepts and terminology

### Entities

- **Action template**: A reusable procedure definition (stable identity) that describes *what to
  run* independent of any particular run. Templates are comparable across time.
- **Action instance**: A run-scoped instantiation of an action template after plan expansion. An
  instance binds a concrete target and concrete input bindings.
- **Plan**: A user-facing specification that selects templates and declares expansion and execution
  semantics.
- **Plan graph**: The compiled internal representation (nodes + edges) that the runner executes.
- **Group**: An optional reporting organization construct (folder-like). Groups MUST NOT affect
  execution semantics.
- **Threat-driven index** (optional, v0.2+): A curated list of prioritized techniques or templates
  used to generate plans. Indexes evolve over time and should be versioned.

### Concept mapping (informative)

This table is informational only and exists to keep vocabulary consistent across the spec set.

| External concept class | Closest Purple Axiom concept        |
| ---------------------- | ----------------------------------- |
| Environment            | Range / lab environment             |
| Assessment             | Run (`run_id`)                      |
| Campaign               | Plan group + compiled plan graph    |
| Test case template     | Action template (v0.2+)             |
| Test execution         | Action instance node + evidence log |

## v0.1 behavior (normative)

In v0.1, the plan execution model is implicit:

- Only `atomic` plan type is supported.
- Each plan compiles to a single-node graph with no edges.
- Target selection resolves to exactly one asset per action.

If a v0.1 runner encounters a plan type other than `atomic`, it MUST fail with
`reason_code=plan_type_reserved`.

## Plan types

### Reserved plan types

The following plan types are reserved and will be defined in future versions:

| Plan type  | Target version | Description                           |
| ---------- | -------------- | ------------------------------------- |
| `matrix`   | v0.2           | Combinatorial expansion over axes     |
| `sequence` | v0.3+          | Ordered action list with dependencies |
| `campaign` | v0.4+          | DAG with conditional edges            |
| `adaptive` | Future         | Runtime branching based on results    |

### Plan compilation phases (v0.2+, normative)

When enabled, plan compilation MUST proceed in deterministic phases:

1. **Template resolution**: resolve all referenced action templates into a run-scoped snapshot.
1. **Axis enumeration** (matrix only): enumerate axis values deterministically.
1. **Expansion**: produce action instances (nodes) and record cell coordinates.
1. **Dependency construction**: produce edges (explicit or implied by order).
1. **Deterministic node ordering**: compute the canonical execution order basis.

Each phase MUST emit sufficient intermediate data to reproduce the final graph exactly.

## Identity, determinism, and hashing

This project is determinism-driven. Plan identity must be stable and reproducible.

### Action template identity (v0.2+, normative)

An action template MUST have a stable identifier `template_id` that is:

- stable across runs, and
- stable across machines given identical template source content.

`technique_id` alone is NOT a stable procedure identifier.

A conforming implementation MUST compute `template_id` as:

- Prefix: `pa:tpl:v1:`
- Digest: `sha256(canonical_json_bytes(template_basis_v1))` truncated to 128 bits (32 hex chars)

`template_basis_v1` MUST include only stable inputs:

- `engine` (example: `atomic`)
- `engine_test_id` (example: Atomic GUID)
- `technique_id`
- `name` (template name)
- `phase` (execution phase or ATT&CK tactic label, if used)
- `source_ref` (upstream revision identifier, when available)
- `source_tree_sha256` (deterministic source tree hash, when available)

Canonical JSON MUST follow the same rules used elsewhere in the project (see
`025_data_contracts.md`).

Rationale: template identity must survive run-to-run and preserve comparability.

### Action instance identity (v0.2+, normative)

An action instance MUST have a run-scoped identifier `action_instance_id` that is unique within a
run and deterministic given identical compilation inputs.

A conforming implementation MUST compute `action_instance_id` as:

- Prefix: `pa:ainst:v1:`
- Digest: `sha256(canonical_json_bytes(instance_basis_v1))` truncated to 128 bits (32 hex chars)

`instance_basis_v1` MUST include:

- `run_id`
- `template_id`
- `target_asset_id`
- `input_bindings` (post-expansion, fully resolved)
- `cell` (matrix coordinate object, or omitted if not a matrix plan)
- `group_id` (if present)

### Execution ordering determinism (v0.2+, normative)

The runner MUST execute a plan graph deterministically.

- If the graph is a DAG, the canonical order MUST be a deterministic topological sort.
- When multiple nodes are eligible (no unsatisfied dependencies), tie-breaking MUST be deterministic
  using the tuple:
  1. `group_id` (missing sorts first)
  1. `cell.path` (lexicographic, missing sorts first)
  1. `action_instance_id`

Concurrency MAY be introduced, but the selected ordering basis MUST still be recorded so execution
can be replayed and audited.

## Plan graph schema (seed)

This section defines the seed structure for the v0.2 plan graph. It is non-normative until v0.2, but
is intended to be directly translatable into JSON Schema.

```yaml
# Seed structure (non-normative until v0.2)
plan_graph:
  version: "0.2.0"

  # Snapshot of the templates referenced by this plan, so the run remains reproducible even if the
  # repo changes later.
  template_snapshot:
    source: "repo"
    templates:
      - template_id: "pa:tpl:v1:<sha256-128>"
        engine: "atomic"
        technique_id: "T1059.001"
        engine_test_id: "<guid>"
        name: "<template_name>"
        phase: "<optional_phase>"
        source_ref: "<optional_upstream_revision>"
        source_tree_sha256: "<optional_tree_hash>"

  # Optional organizational groups for reporting. Groups MUST NOT affect execution semantics.
  groups:
    - group_id: "pa:group:v1:<sha256-128>"
      name: "Execution - PowerShell"
      tags: ["baseline"]

  nodes:
    - action_instance_id: "pa:ainst:v1:<sha256-128>"
      template_id: "pa:tpl:v1:<sha256-128>"
      technique_id: "T1059.001"
      engine: "atomic"
      engine_test_id: "<guid>"
      target_asset_id: "<asset_id>"

      # Canonical key/value bindings applied for this instance (matrix cell).
      # Values MUST be recorded post-expansion (resolved) for determinism and auditing.
      input_bindings: {}

      # Matrix coordinate information. Omit if the plan is not a matrix.
      cell:
        path: ["targets", "variables.user"]
        coord:
          targets: "<asset_id>"
          variables.user: "alice"

      # Optional execution artifacts dropped to disk prior to execution (runner-resolved).
      execution_artifacts: []

      # Optional cleanup actions executed after the main action completes.
      cleanup: []

      # Run-time status fields are recorded in execution logs, not in the compiled graph.
      # (The compiled graph is immutable evidence.)

  edges:
    - from: "pa:ainst:v1:<sha256-128>"
      to: "pa:ainst:v1:<sha256-128>"
      kind: "depends_on" # reserved enum: depends_on | ordered_before | conditional

```

## Matrix plan syntax (seed)

```yaml
# Seed structure (non-normative until v0.2)
plan:
  type: "matrix"

  # Optional grouping label for reporting (maps to plan_graph.groups[]).
  group:
    name: "Execution - PowerShell"
    tags: ["baseline"]

  # Axes define how the plan expands.
  axes:
    # Template selection axis (by technique_id, template_id, tag, or index entry).
    templates:
      techniques: ["T1059.001"]
      # Optional: explicit template_id references (preferred when available).
      template_ids: []

    # Target expansion axis.
    targets:
      selector: { os: "windows" }
      foreach_matched: true

    # Optional variable axes used to parameterize actions deterministically.
    variables:
      user: ["alice", "bob"]

  # Determines which axes produce expansion (cartesian product).
  expand: ["targets", "variables.user"]

  execution:
    order: "sequential"   # reserved: sequential | parallel | dag
    concurrency: 1
```

## Threat-driven index packs (optional, v0.2+)

A threat-driven index is a curated list of prioritized testing entries derived from threat groups
and relevant techniques. Indexes evolve over time and should be treated as versioned inputs.

### Index pack goals

- Provide an operator-friendly way to generate repeatable plans from a curated priority list.
- Permit sector-specific or environment-specific prioritization without changing template identity.
- Support evolution over time via explicit index versioning and changelogs.

### Proposed artifact shape (seed)

```yaml
# Seed structure (non-normative until implemented)
threat_index:
  index_id: "example-finance"
  index_version: "2026.1.0"
  description: "Curated priority list derived from threat groups relevant to <domain>."
  entries:
    - entry_id: "T1059.001"
      technique_id: "T1059.001"
      priority: "P0" # reserved: P0 | P1 | P2 | P3
      rationale: "Why this technique is prioritized."
      template_selectors:
        - { engine: "atomic", technique_id: "T1059.001" }
      tags: ["execution", "baseline"]
```

### Plan integration (non-normative guidance)

A plan MAY reference an index pack as a template selection input:

- `axes.templates.index_ref: { index_id, index_version }`

When an index is used, the plan compiler MUST snapshot the effective index document into the run
bundle and record its hash in the manifest.

## Execution logging and evidence

Compiled plans are immutable evidence. Run-time state is recorded separately.

### Required plan artifacts (v0.2+, normative when implemented)

When plans are enabled, the runner MUST produce:

- `runs/<run_id>/plan/expanded_graph.json` (compiled plan graph, immutable)
- `runs/<run_id>/plan/expansion_manifest.json` (axis enumeration + cell coordinates)
- `runs/<run_id>/plan/template_snapshot.json` (the template snapshot, if not embedded)
- `runs/<run_id>/plan/execution_log.jsonl` (one record per action instance execution attempt)

`ground_truth.jsonl` MUST be enhanced to reference action instances (see below).

### Execution log record (seed)

```yaml
# Seed structure (non-normative until implemented)
execution_record:
  action_instance_id: "pa:ainst:v1:<sha256-128>"
  template_id: "pa:tpl:v1:<sha256-128>"
  attempt: 1
  status: "success" # reserved: success | failed | skipped
  started_at: "2026-01-15T20:12:05Z"
  ended_at: "2026-01-15T20:12:15Z"
  exit_code: 0
  duration_ms: 10000
  evidence:
    stdout_path: "runner/actions/<action_instance_id>/stdout.txt"
    stderr_path: "runner/actions/<action_instance_id>/stderr.txt"
    executor_path: "runner/actions/<action_instance_id>/executor.json"
    cleanup_verification_path: "runner/actions/<action_instance_id>/cleanup_verification.json"
  reason_code: null
```

Determinism requirements:

- `execution_log.jsonl` MUST be emitted in canonical node execution order.
- Paths MUST be run-relative using POSIX separators.

## Ground truth emission for multi-action plans (reserved)

When implemented, `ground_truth.jsonl` MUST include:

- `template_id`
- `action_instance_id`
- `plan_expansion_ref` (pointer to cell coordinates in `expansion_manifest.json`)

This enables joins across stages without requiring the plan compiler to be re-run.

## Outcome model (reserved, vendor neutral)

Some assessment workflows record outcomes per defensive control (for example, one outcome per tool)
plus an overall outcome for the test. This project MAY adopt a similar model as a scoring input, but
it MUST remain vendor neutral and file-backed.

When implemented:

- Outcome records MUST be stored as artifacts under the run bundle.
- A per-control outcome model MUST NOT change template identity.
- If per-control outcomes are used, an overall outcome MUST be derivable deterministically from the
  per-control outcomes using documented rules.

## Failure semantics (v0.2+, normative when implemented)

Plan execution MUST integrate with the project stage outcome model:

- The runner stage MUST still emit a stage outcome per ADR-0005.

- Individual action instance failures MUST be recorded in `execution_log.jsonl` with stable reason
  codes.

- A plan MAY declare an error policy (reserved), such as:

  - stop on first failure
  - continue and record partial

Regardless of policy, the runner MUST NOT silently drop action instances from reporting.

## Verification hooks (v0.2+, required when implemented)

A conforming implementation MUST include fixture-driven tests:

1. **Template identity stability**

   - Same template source material produces identical `template_id` across platforms.

1. **Matrix expansion determinism**

   - Axis enumeration produces identical `expansion_manifest.json` for the same inputs.

1. **Graph ordering determinism**

   - Canonical execution ordering is identical across runs given identical compilation inputs.

1. **Action instance identity stability**

   - Same run inputs produce identical `action_instance_id` values.

1. **Artifact completeness**

   - A multi-action run produces all required plan artifacts and references them from the manifest.

## References

- [ADR-0006: Plan execution model](../adr/ADR-0006-plan-execution-model.md) (placeholder reference)
- [Scenario model spec](030_scenarios.md)
- [Data contracts spec](025_data_contracts.md)
- [ADR-0004: Deployment architecture and inter-component communication](../adr/ADR-0004-deployment-architecture-and-inter-component-communication.md)
- [ADR-0005: Stage outcomes and failure classification](../adr/ADR-0005-stage-outcomes-and-failure-classification.md)

## Changelog

| Date      | Change                                     |
| --------- | ------------------------------------------ |
| 1/12/2026 | Initial stub (reserved for v0.2)           |
| 1/15/2026 | Expanded template/instance and index model |
