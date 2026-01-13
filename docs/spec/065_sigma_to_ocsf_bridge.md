---
title: Sigma-to-OCSF bridge
description: Defines the routing, aliasing, and backend adapter contract for executing Sigma over OCSF.
status: draft
---

# Sigma-to-OCSF bridge

This document defines the Sigma-to-OCSF bridge contract for compiling Sigma rules into executable
plans over OCSF events. It covers routing, aliasing, backend adapter requirements, and deterministic
artifacts for evaluation.

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

### Producer predicates (filters array)

Producer predicates are an optional, structured narrowing mechanism for routing and evaluation. They
exist to disambiguate producer-specific subsets within a routed class scope (example: Windows Event
Log `Security` channel vs Sysmon, multiple tables within a data lake, or safe use of `raw.*`
fallback under a clearly identified producer).

#### Syntax (normative)

When present, producer predicates MUST be expressed as an array of **OCSF filter objects** matching
the shape used in:

- [Bridge router table schema](../contracts/bridge_router_table.schema.json) (`routes[].filters[]`)
- [Bridge compiled plan schema](../contracts/bridge_compiled_plan.schema.json)
  (`compilation.routed_scope.filters[]`)

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

### Fallback policy (raw field fallback)

A controlled escape hatch is permitted for MVP:

- If an event attribute cannot be mapped yet, allow evaluation to reference `raw.*` when:
  - the event is still within the correct OCSF class scope, and
  - provenance clearly identifies the producer/source
- If fallback is used, it MUST be recorded (see “Bridge provenance in detections”).
- Fallback enablement MUST be controlled by `detection.sigma.bridge.raw_fallback_enabled` (see the
  [configuration reference](120_config_reference.md)).
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

Routing and mapping:

- `unrouted_logsource` (no router entry for the rule `logsource`)
- `unmapped_field` (Sigma field cannot be resolved to an OCSF path or backend expression)
- `raw_fallback_disabled` (an unmapped field was encountered and `raw.*` fallback was not permitted)
- `ambiguous_field_alias` (alias resolution is not uniquely determined for the routed scope)

Expression support:

- `unsupported_operator` (Sigma operator cannot be represented in the selected backend)
- `unsupported_modifier` (Sigma modifier cannot be represented in the selected backend)
- `unsupported_value_type` (value type is unsupported for the operator and field expression)
- `unsupported_regex` (regex use is unsupported or disallowed by backend policy)

Backend execution:

- `backend_compile_error` (backend failed to compile a valid executable plan)
- `backend_eval_error` (backend failed during evaluation)

## 3) Evaluator backend adapter

### Batch backend (v0.1 default)

- For v0.1, if `detection.sigma.bridge.backend` is omitted, the bridge MUST use `duckdb_sql` (DuckDB
  SQL over Parquet).
- The `duckdb_sql` backend MUST enforce deterministic DuckDB session settings:
  - `SET threads = 1;`
  - `SET TimeZone = 'UTC';`
- If the implementation allows overriding these settings for performance, it MUST record the
  effective values in backend provenance (see “Backend provenance”).
- Compile Sigma -> SQL (after routing + aliasing)
- Execute over OCSF Parquet using DuckDB
- Return:
  - matched event ids (`metadata.event_id`)
  - first/last seen timestamps

Version pinning (normative):

- The `duckdb_sql` backend MUST use the pinned DuckDB version defined in the
  [supported versions reference](../../SUPPORTED_VERSIONS.md).
- The bridge MUST record the effective runtime versions used for:
  - DuckDB (library/runtime version),
  - pySigma (library version), in backend provenance within each compiled plan.
- If the effective version differs from the pins, the evaluator stage MUST fail closed (see the
  version drift policy in the [supported versions reference](../../SUPPORTED_VERSIONS.md)).

### Streaming backend (optional v0.2)

- Compile Sigma -> expression plan
- Evaluate over a stream processor (example: Tenzir)
- Emit matches in near real time

### Decision criteria for adding Tenzir (v0.2)

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

Any backend implementation (including `duckdb_sql` and `tenzir` in v0.2) MUST satisfy the following
Conformance fixtures for these gates are defined in
[test strategy CI: unit tests](100_test_strategy_ci.md#unit-tests) (rule compilation, multi-class
routing) and [test strategy CI: integration tests](100_test_strategy_ci.md#integration-tests)
(DuckDB determinism conformance harness).

- **Golden equivalence (supported subset)**: for a pinned fixture corpus and a pinned Sigma subset,
  backends MUST produce identical `matched event ids` per rule. If a backend intentionally differs,
  the rule MUST be marked non-executable with an explicit reason.
- **Deterministic ordering**: any emitted list of `metadata.event_id` MUST be sorted
  deterministically before writing `detections/detections.jsonl`.
- **Backend provenance**: each `compiled_plans/<rule_id>.plan.json` MUST record the backend
  identifier and backend version (or build metadata).
  - If the backend is `duckdb_sql`, the compiled plan MUST also record:
    - `backend.settings.threads` (integer)
    - `backend.settings.timezone` (string; MUST be `UTC` unless explicitly configured)
- **Explained failure modes**: non-executable rules MUST include a stable, machine-readable
  `reason_code` and a human-readable explanation.

### Backend adapter contract (normative, v0.1)

This section defines the minimum executable subset and deterministic compilation requirements for
the evaluator backend adapter. It is authoritative for:

- what the bridge MUST compile and execute in v0.1 (supported subset),
- how compilation MUST be made deterministic, and
- which conditions MUST be classified as non-executable (fail-closed).

#### Common requirements (all backends)

1. Output artifacts:

   - For each evaluated Sigma rule, the bridge MUST emit exactly one compiled plan file under
     `bridge/compiled_plans/<rule_id>.plan.json` (see “Bridge artifacts in the run bundle”).
   - A compiled plan MUST either:
     - be executable (contains backend-specific executable content), or
     - be explicitly non-executable (contains `reason_code` and an explanation).

1. Fail-closed semantics:

   - If routing is unknown, aliasing is unknown, or backend compilation cannot represent the rule,
     the bridge MUST mark the rule non-executable. It MUST NOT silently degrade into “no matches”.

1. Deterministic match sets:

   - Any emitted list of matched `metadata.event_id` MUST be sorted deterministically prior to
     writing `detections/detections.jsonl`.

1. Deterministic compilation inputs:

   - Compilation MUST be a pure function of:
     - rule content,
     - router output (routed scope),
     - mapping pack snapshot (aliases, transforms, fallback policy),
     - backend id and version,
     - backend determinism settings (if any).

#### Supported Sigma expression subset (bridge-level, v0.1 MVP)

The following MUST be supported by the v0.1 evaluator adapter for the default backend (`duckdb_sql`)
after routing and alias resolution.

Selector primitives (field-to-value comparisons):

- Equality:
  - `field: <scalar>` (string, number, boolean)
  - `field: [<scalar> ...]` (list membership)
- Existence:
  - `field|exists: true|false`
- Relational (numeric only):
  - `field|lt`, `field|lte`, `field|gt`, `field|gte`
- String matching:
  - `field|contains`
  - `field|startswith`
  - `field|endswith`

Boolean composition:

- `and`, `or`, `not` over selections and subexpressions
- `1 of selection*` and `all of selection*` (wildcard selection groups)

Out of scope in v0.1 (MUST be marked non-executable when encountered):

- Correlation and multi-event sequence semantics (beyond single-event matching)
- Temporal aggregation semantics (for example: `count()`, `near`, `within`, “threshold” rules)
- Field modifiers that require binary transforms (example: `base64`, `utf16`, `windash`) unless the
  mapping pack has already materialized an equivalent normalized value
- PCRE-only regex constructs (lookaround, backreferences, etc.). Regex matching is supported only in
  an RE2-compatible subset; non-conforming patterns MUST be treated as Non-executable.

#### DuckDB SQL adapter requirements (duckdb_sql, normative)

This section defines the backend adapter contract for compiling Sigma expressions into DuckDB SQL.
This contract is aligned with research report R-03 (DuckDB backend plugin for pySigma).

#### MVP compilation gate

MVP compilation is allowed only when **all** required constructs are **Supported** by this section.
Anything marked **Requires validation** MUST be treated as **Non-executable** until promoted to
Supported by a recorded experiment.

#### Supported capability surface (v0.1)

The `duckdb_sql` adapter MUST support the following constructs for v0.1:

- Boolean OR: list values (default) compile to parenthesized OR chains.
- Boolean AND: `all` modifier compiles to parenthesized AND chains.
- Equality: implicit equality comparisons.
  - For string-typed comparisons, matching MUST be case-insensitive by default.
- Inequality: `|neq` modifier (NULL-safe).
- String modifiers: `|contains`, `|startswith`, `|endswith` (case-insensitive).
- Existence: `|exists` (`IS NOT NULL` / `IS NULL` depending on positive vs negated context).
- Numeric comparisons: `|lt`, `|lte`, `|gt`, `|gte`.
- Regex match: `|re` with RE2-compatible patterns only; unsupported constructs are Non-executable.
  DuckDB regex functions use RE2 and accept option flags. :contentReference[oaicite:0]{index=0}
- Timestamp extraction: `|hour`, `|day`, `|month`, `|year` against the canonical `time` field.
- LIST semantics: equality against LIST-typed fields MUST mean any element matches. The adapter MUST
  use DuckDB list functions when the field is LIST-typed. :contentReference[oaicite:1]{index=1}

#### Deferred (post-MVP)

The following constructs are explicitly deferred and MUST be treated as Non-executable in v0.1:

- CIDR match (`|cidr`) pending extension packaging and type policy decisions.
- Base64 transforms (`|base64`, `|base64offset`).
- Field reference (`|fieldref`) pending typing policy.
- Case-sensitive mode (`|cased`) beyond the DuckDB regex option surface.

#### SQL compilation requirements (normative)

1. Identifiers and quoting:

   - Field references MUST be quoted with double quotes when required (reserved keywords,
     punctuation), using a deterministic quoting function.

1. Nested fields:

   - Struct access MUST use DuckDB dot notation (for example, `actor.user.uid`).

1. Equality, inequality, and membership (scalar fields):

   - Scalar equality MUST compile to `field = value` for non-string types.
   - For string-typed equality, the adapter MUST compile case-insensitive semantics using:
     - `lower(field) = lower(value)`
   - Inequality (`|neq`) MUST compile NULL-safe using:
     - `field IS DISTINCT FROM value`
   - List values on scalar fields MUST compile to membership semantics:
     - For non-string types: `field IN (v1, v2, ...)`
     - For string-typed membership: `lower(field) IN (lower(v1), lower(v2), ...)`
   - Ordering: list value expansions MUST preserve the input order from the Sigma rule and MUST NOT
     be reordered as a “determinism” technique.

1. LIST-typed field semantics:

   - If the resolved field expression is LIST-typed, scalar comparisons MUST mean “any element
     matches” and MUST compile using DuckDB list functions:
     - Single value: `list_contains(field, value)`
     - Multiple values (default OR semantics): `list_has_any(field, [values...])`
     - `all` modifier: `list_has_all(field, [values...])` :contentReference[oaicite:2]{index=2}
   - Pattern matching against LIST-typed fields MUST unnest and use `EXISTS` with a correlated
     predicate (exact formatting is implementation-defined, semantics are normative).

1. Boolean combinations:

   - Default selector expansion MUST compile to parenthesized OR chains.
   - `all` expansion MUST compile to parenthesized AND chains.
   - Parentheses are REQUIRED for determinism and to avoid precedence ambiguity.

1. String matching and wildcards:

   - `contains`, `startswith`, and `endswith` MUST compile to `ILIKE` patterns with an explicit
     `ESCAPE` character.
   - The adapter MUST use `$` as the escape character and MUST escape `$`, `%`, and `_` in user
     provided values before embedding them in patterns.
   - Canonical patterns:
     - contains: `field ILIKE '%' || value || '%' ESCAPE '$'`
     - startswith: `field ILIKE value || '%' ESCAPE '$'`
     - endswith: `field ILIKE '%' || value ESCAPE '$'`

1. Regex (`|re`) support (RE2-only):

   - Regex matching MUST compile to `regexp_matches(field, pattern[, options])`.
     :contentReference[oaicite:3]{index=3}
   - The adapter MUST validate patterns as RE2-compatible at compile time.
   - PCRE-only constructs (lookahead, lookbehind, backreferences, atomic groups, etc.) MUST be
     rejected as Non-executable with reason_code `unsupported_regex`.
   - Options mapping:
     - `|re|i` MUST compile with option `i` (case-insensitive).
       :contentReference[oaicite:4]{index=4}
     - `|re|m` MUST compile with a newline-sensitive option (`m` or its DuckDB equivalents).
       :contentReference[oaicite:5]{index=5}
     - `|re|s` MUST compile with option `s` (non-newline sensitive).
       :contentReference[oaicite:6]{index=6}

1. Timestamp extraction:

   - The adapter MUST treat `time` as INT64 epoch milliseconds (UTC) and MUST compile date-part
     operations using `epoch_ms(time)` and `date_part()`.

1. Failure reporting:

   - When a rule cannot be compiled, the bridge MUST record a Non-executable compiled plan entry
     with:
     - a stable `reason_code`, and
     - a deterministic `explanation` string.
   - For backend-originated compilation failures, the `explanation` MUST include the stable backend
     error code prefix `PA_SIGMA_...` (as defined by R-03) to support deterministic aggregation.

1. Determinism requirements:

   - Generated SQL MUST be stable with fixed parenthesization, deterministic literal escaping,
     deterministic identifier quoting, and preserved input ordering for list expansions.

#### Non-executable classification mapping (normative)

The adapter MUST select the most specific applicable reason:

- No router match for `logsource` -> `unrouted_logsource`
- Alias resolution missing -> `unmapped_field` (or `raw_fallback_disabled` when applicable)
- Alias resolution ambiguous -> `ambiguous_field_alias`
- Operator not in supported subset -> `unsupported_operator`
- Modifier not in supported subset -> `unsupported_modifier`
- Regex encountered (v0.1 default) -> `unsupported_regex`
- Value type incompatible with operator -> `unsupported_value_type`
- Backend compilation exception -> `backend_compile_error`
- Backend execution exception -> `backend_eval_error`

## Bridge artifacts in the run bundle

When Sigma evaluation is enabled, the bridge SHOULD emit a small, contract-validated set of
artifacts under `runs/<run_id>/bridge/` so routing, compilation, and coverage are mechanically
testable:

- `router_table.json` (required)

  - Snapshot of `logsource` routing (Sigma category to OCSF scope).
  - Schema: [bridge router table schema](../contracts/bridge_router_table.schema.json).

- `mapping_pack_snapshot.json` (required)

  - Snapshot of the full bridge inputs (router + alias map + fallback policy).
  - Schema: [bridge mapping pack schema](../contracts/bridge_mapping_pack.schema.json).
  - `mapping_pack_sha256` MUST be computed over stable mapping inputs and MUST NOT include
    run-specific fields.

- `compiled_plans/`

  - `compiled_plans/<rule_id>.plan.json` (required for each evaluated rule)
  - Deterministic compilation output for the chosen backend (SQL or IR), including non-executable
    reasons.
  - Schema: [bridge compiled plan schema](../contracts/bridge_compiled_plan.schema.json) per file.
  - For `duckdb_sql`, the plan MUST include the effective DuckDB determinism settings recorded in
    backend provenance (see above).

- `coverage.json` (required)

  - Summary metrics and top failure modes (unrouted categories, unmapped fields, fallback usage).
  - Schema: [bridge coverage schema](../contracts/bridge_coverage.schema.json).

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

## References

- [Detection rules specification](060_detection_sigma.md)
- [Supported versions reference](../../SUPPORTED_VERSIONS.md)
- [Test strategy CI specification](100_test_strategy_ci.md)
- [Bridge router table schema](../contracts/bridge_router_table.schema.json)
- [Bridge compiled plan schema](../contracts/bridge_compiled_plan.schema.json)
- [Bridge mapping pack schema](../contracts/bridge_mapping_pack.schema.json)
- [Bridge coverage schema](../contracts/bridge_coverage.schema.json)

## Changelog

| Date       | Change            |
| ---------- | ----------------- |
| 2026-01-12 | Formatting update |
