<!-- docs/spec/065_sigma_to_ocsf_bridge.md -->

# Sigma-to-OCSF Bridge

## Problem statement

Sigma rules typically assume a **producer-specific log schema** (Windows Security, Sysmon, auditd,
Zeek, etc.) expressed through:

- `logsource` (routing signal)
- field names referenced in `detection` selectors

Purple Axiom normalizes telemetry into **OCSF** before evaluation. The Sigma-to-OCSF Bridge provides
a contract-driven compatibility layer that makes Sigma rules executable against OCSF events without
abandoning OCSF as the canonical store.

## Goals

- Make Sigma evaluation **first-class** in an OCSF-first pipeline.
- Keep the bridge deterministic, versioned, and auditable.
- Attribute misses to one of: missing telemetry, normalization gap, bridge gap, rule logic gap.

## Non-goals

- “Run every Sigma rule unmodified” as a hard guarantee.
- Perfect semantic equivalence between producer-specific event types and OCSF classes for all
  sources.
- Correlation / multi-event sequence semantics beyond what the chosen evaluator backend supports in
  MVP.

## Core concept

The bridge is a composition of three artifacts:

1. **Logsource router**
1. **Field alias map**
1. **Evaluator backend adapter**

Together, these compile Sigma rules into an executable plan over OCSF events.

## 1) Logsource router

### Inputs

Sigma `logsource` fields:

- `category` (primary)
- `product`, `service` (secondary, optional)

### Output

An OCSF query scope:

- required: one or more OCSF class filters (preferred: `class_uid` or class name)
- optional: producer/source predicates via `filters[]` expressed as OCSF filter objects
  (`{path, op, value}`; see below)

### Producer predicates (`filters[]`)

Producer predicates are an optional, structured narrowing mechanism for routing and evaluation. They
exist to disambiguate producer-specific subsets within a routed class scope (example: Windows Event
Log `Security` channel vs Sysmon, multiple tables within a data lake, or safe use of `raw.*`
fallback under a clearly identified producer).

#### Syntax (normative)

When present, producer predicates MUST be expressed as an array of **OCSF filter objects** matching
the shape used in:

- `docs/contracts/bridge_router_table.schema.json` (`routes[].filters[]`)
- `docs/contracts/bridge_compiled_plan.schema.json` (`compilation.routed_scope.filters[]`)

Each filter object MUST have:

- `path` (string): dot-delimited OCSF field path (examples: `metadata.source_type`, `raw.channel`,
  `raw.provider`)
- `op` (string): one of `eq | neq | in | nin | exists | contains | prefix | suffix | regex`
- `value` (any): required for all operators except `exists` (see semantics)
- `notes` (string, optional)

#### Semantics (normative)

- The effective routed scope is:
  - `class_uid IN routed_scope.class_uids` (union semantics; see below), AND
  - all `filters[]` evaluate true (conjunction / logical AND).
- If `filters[]` is omitted or empty, only the class scope applies.

Path resolution and missing data:

- If `path` is missing or resolves to null:
  - `op=exists` MUST evaluate to false when `value` is omitted or true.
  - `op=exists` MUST evaluate to true when `value` is false.
  - All other operators MUST evaluate to false (fail-closed narrowing).

Type and operator behavior:

- Comparisons are type-strict. Implementations MUST NOT perform implicit type coercion.
- `eq` / `neq`: JSON equality / inequality on the resolved value.
- `in` / `nin`: `value` MUST be an array. If the resolved value is scalar, membership is tested
  against the array. If the resolved value is an array, the predicate matches when any element is
  (not) in `value`.
- `contains` / `prefix` / `suffix`: resolved value MUST be a string (or an array of strings, matched
  element-wise).
- `regex`: resolved value MUST be a string (or an array of strings, matched element-wise). Patterns
  MUST be RE2-compatible. `regex` is a search match unless the pattern is explicitly anchored.

Determinism:

- When emitting `filters[]`, the router MUST preserve the order as stored in the router table
  snapshot.
- Mapping pack authors SHOULD order filters deterministically (RECOMMENDED: sort by `path`, then
  `op`, then canonical JSON of `value`).

Example (router table route entry):

```json
{
  "sigma_logsource": { "category": "process_creation", "product": "windows" },
  "ocsf_scope": { "class_uids": [1007] },
  "filters": [
    { "path": "metadata.source_type", "op": "eq", "value": "windows_eventlog" },
    { "path": "raw.channel", "op": "eq", "value": "Security" },
    { "path": "raw.provider", "op": "eq", "value": "Microsoft-Windows-Security-Auditing" }
  ]
}
```

Multi-class routing semantics (normative):

- A route that produces multiple `class_uid` values is a valid, fully-determined route.
- The evaluator MUST evaluate the rule against the **union** of all routed classes.
  - Equivalent semantics: `class_uid IN (<uids...>)` or `(class_uid = u1 OR class_uid = u2 OR ...)`.
  - The evaluator MUST NOT pick an arbitrary single class when multiple classes are routed.
- For determinism and diffability, the router MUST emit multi-class `class_uid` sets in ascending
  numeric order.
- Backend implementations MAY realize union semantics via:
  - a single query with `class_uid IN (...)`, or
  - multiple per-class subqueries combined as a deterministic UNION of results.

### Rules

- Route primarily on `logsource.category`.
- Use `product/service` only to **narrow** when necessary.
- If routing cannot be determined (no matching route), the rule is **non-executable** (fail-closed).
- Routing to multiple classes MUST NOT be treated as “undetermined routing”.

### Mapping packs

Adopt SigmaHQ’s OCSF routing where possible, then constrain to your pinned OCSF version and enabled
profiles.

The mapping pack is versioned independently of:

- the Sigma ruleset version
- the Purple Axiom pipeline version

## 2) Field alias map

### Purpose

Translate Sigma field references into OCSF JSONPaths (or evaluator-specific column expressions).

### Structure

Field aliases SHOULD be scoped by router result (at minimum by `logsource.category`), because field
meaning varies by event family.

Multi-class aliasing note (recommended):

- When a `logsource.category` routes to multiple `class_uid` values, field aliases SHOULD be scoped
  such that alias resolution remains unambiguous.
  - Recommended: scope by `(logsource.category, class_uid)` (even if materialized internally), or
  - ensure the alias mapping for that category is valid for all routed classes used in evaluation.

Recommended structure (conceptual):

- `aliases[logsource.category][sigma_field] -> ocsf_path_or_expr`
- `normalizers[sigma_field] -> value transforms` (case folding, path normalization, enum
  harmonization)

### Fallback policy (`raw.*`)

A controlled escape hatch is permitted for MVP:

- If an event attribute cannot be mapped yet, allow evaluation to reference `raw.*` when:
  - the event is still within the correct OCSF class scope, and
  - provenance clearly identifies the producer/source
- If fallback is used, it MUST be recorded (see “Bridge provenance in detections”).
- Fallback enablement MUST be controlled by `detection.sigma.bridge.raw_fallback_enabled` (see
  `120_config_reference.md`).
- If fallback is used, `extensions.bridge.fallback_used` MUST be `true` in emitted detection
  instances.
- Any list of fallback-related fields (example: `extensions.bridge.unmapped_sigma_fields`) MUST be
  sorted by UTF-8 byte order (no locale).

Over time, the target is to reduce fallback rate by expanding normalized fields.

### Unsupported fields or modifiers

- If a rule references an unmapped field and fallback is disabled, the rule is **non-executable**.
- If a Sigma modifier cannot be expressed in the backend (example: complex regex semantics), the
  rule is **non-executable**.
- Non-executable rules are reported with reasons and counts.

Non-executable `reason_code` values (normative, v0.1):

- `unmapped_field`
- `raw_fallback_disabled`
- `unsupported_modifier`
- `backend_compile_error`
- `backend_eval_error`

## 3) Evaluator backend adapter

### Batch backend (v0.1 default)

- For v0.1, if `detection.sigma.bridge.backend` is omitted, the bridge MUST use `duckdb_sql` (DuckDB
  SQL over Parquet).
- Compile Sigma -> SQL (after routing + aliasing)
- Execute over OCSF Parquet using DuckDB
- Return:
  - matched event ids (`metadata.event_id`)
  - first/last seen timestamps

### Streaming backend (optional)

- Compile Sigma -> expression plan
- Evaluate over a stream processor (example: Tenzir)
- Emit matches in near real time

### Decision criteria for adding Tenzir

Tenzir support SHOULD be added only when there is an explicit requirement that the batch backend
cannot satisfy.

At least one of the following MUST be true to justify adding or enabling Tenzir:

- **Latency**: detections MUST be emitted within a bounded interval (example: 1-10s) from event
  observation, during an active run.
- **Streaming semantics**: the evaluator MUST support continuous evaluation over live event streams
  (not only over stored Parquet).
- **In-flow evaluation**: detections MUST be computed as part of the telemetry flow (example:
  operator feedback or pre-storage reduction).

### Backend conformance gates (CI)

Any backend implementation (including `duckdb_sql` and `tenzir`) MUST satisfy the following
conformance gates (validated via unit + integration tests; see `docs/spec/100_test_strategy_ci.md`).

- **Golden equivalence (supported subset)**: for a pinned fixture corpus and a pinned Sigma subset,
  backends MUST produce identical `matched event ids` per rule. If a backend intentionally differs,
  the rule MUST be marked non-executable with an explicit reason.
- **Deterministic ordering**: any emitted list of `metadata.event_id` MUST be sorted
  deterministically before writing `detections/detections.jsonl`.
- **Backend provenance**: each `compiled_plans/<rule_id>.plan.json` MUST record the backend
  identifier and backend version (or build metadata).
- **Explained failure modes**: non-executable rules MUST include a stable, machine-readable
  `reason_code` and a human-readable explanation.

### Backend contract

Regardless of backend, the evaluator MUST produce `detection_instance` rows in
`detections/detections.jsonl` and MUST be able to explain non-executable rules.

## Bridge artifacts in the run bundle

When Sigma evaluation is enabled, the bridge SHOULD emit a small, contract-validated set of
artifacts under `runs/<run_id>/bridge/` so routing, compilation, and coverage are mechanically
testable:

- `router_table.json` (required)

  - Snapshot of `logsource` routing (Sigma category to OCSF scope).
  - Schema: `bridge_router_table.schema.json`.

- `mapping_pack_snapshot.json` (required)

  - Snapshot of the full bridge inputs (router + alias map + fallback policy).
  - Schema: `bridge_mapping_pack.schema.json`.
  - `mapping_pack_sha256` MUST be computed over stable mapping inputs and MUST NOT include
    run-specific fields.

- `compiled_plans/`

  - `compiled_plans/<rule_id>.plan.json` (required for each evaluated rule)
  - Deterministic compilation output for the chosen backend (SQL or IR), including non-executable
    reasons.
  - Schema: `bridge_compiled_plan.schema.json` per file.

- `coverage.json` (required)

  - Summary metrics and top failure modes (unrouted categories, unmapped fields, fallback usage).
  - Schema: `bridge_coverage.schema.json`.

These artifacts are intentionally small and diffable, and they enable CI to distinguish:

- telemetry gaps (no events)
- normalization gaps (missing required/core fields)
- bridge gaps (unrouted categories, unmapped fields, unsupported modifiers)
- rule logic gaps (compiled and executed but did not match expected activity)

## Bridge provenance in detections

Detection instances SHOULD include bridge metadata in `extensions.bridge`:

- `mapping_pack_id`
- `mapping_pack_version`
- `backend`
- `compiled_at_utc`
- `fallback_used`
- `unmapped_sigma_fields` (when applicable)
- `non_executable_reason` (when applicable)

Also store the original Sigma logsource under `extensions.sigma.logsource` (verbatim) when
available.

## Determinism and reproducibility requirements

- Compilation is deterministic given:
  - rule content
  - mapping pack id/version
  - backend id/version
- Ordering:
  - `detections.jsonl` written in a deterministic order (see storage requirements)
- Fail-closed:
  - unknown logsource, unmapped fields (without fallback), or unsupported modifiers MUST not
    silently degrade into “no matches”

## Testing guidance (MVP)

- Golden tests:
  - For a small curated Sigma ruleset, compile to plans and assert stable outputs (diffable).
- Router tests:
  - For each supported `logsource.category`, assert the expected OCSF class scope.
- Alias tests:
  - For each supported category, assert that required Sigma fields map to existing OCSF fields in
    representative events.
- Backend tests:
  - Run the compiled plan against a fixed Parquet fixture and assert match sets and timestamps.

## MVP scope recommendation

Start with the event families that cover the majority of safe adversary emulation scenarios:

- process execution
- network connections
- DNS queries
- authentication/logon
- file writes (selectively)

Expand iteratively, using bridge coverage metrics to guide where mapping work has the highest
scoring impact.
