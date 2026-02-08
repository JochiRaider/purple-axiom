---
title: Sigma-to-OCSF bridge
description: Defines the routing, aliasing, and backend adapter contract for executing Sigma over OCSF.
status: draft
category: spec
tags: [bridge, sigma, ocsf]
related:
  - 060_detection_sigma.md
  - 050_normalization_ocsf.md
  - 025_data_contracts.md
  - 080_reporting.md
  - 120_config_reference.md
  - 070_scoring_metrics.md
  - ../adr/ADR-0001-project-naming-and-versioning.md
  - ../adr/ADR-0002-event-identity-and-provenance.md
  - ../adr/ADR-0005-stage-outcomes-and-failure-classification.md
  - ../adr/ADR-0007-state-machines.md
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

- "Run every Sigma rule unmodified" as a hard guarantee.
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

## Logsource router

### Inputs

Sigma `logsource` fields:

- `category` (primary)
- `product`, `service` (secondary, optional)

### Output

An OCSF query scope:

- required: one or more OCSF `class_uids` (integer class_uids) for execution.
  - Mapping packs MAY carry class names for authoring/readability, but the router/bridge MUST
    resolve any such names to `class_uids` deterministically before emitting compiled plans.
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
- `value` (any): required for all operators except `exists`
  - For `op=exists`, `value` MAY be omitted (defaults to `true`); if provided, it MUST be a boolean.
- `notes` (string, optional)

#### Semantics (normative)

- The effective routed scope is:

  - `class_uid IN routed_scope.class_uids` (union semantics; see below), AND
  - all `filters[]` evaluate true (conjunction / logical AND).

- If `filters[]` is omitted or empty, only the class scope applies.

- Path resolution:

  - `path` is a dot-delimited field path into the event JSON object.
  - Resolution yields one of:
    - MISSING: any path segment is absent
    - NULL: path exists but value is JSON null
    - VALUE: any non-null JSON value (including false, 0, "", empty arrays, empty objects)

- `op=exists` truth table:

  - If `value` is omitted, it defaults to `true`.
  - If `value` is present, it MUST be boolean; otherwise the filter is invalid and the mapping pack
    MUST be rejected as invalid (detection stage fatal `bridge_mapping_pack_invalid`).
  - Evaluate:
    - `exists=true` => match iff resolution is VALUE
    - `exists=false` => match iff resolution is MISSING or NULL

- For all other operators:

  - If resolution is MISSING or NULL, the predicate MUST evaluate to `false` (fail-closed at filter
    level).

- Type and operator behavior:

  - Comparisons are type-strict. Implementations MUST NOT perform implicit type coercion.
  - `eq` / `neq`:
    - If resolved VALUE is a scalar, use JSON equality / inequality.
    - If resolved VALUE is an array:
      - `eq` matches iff any element equals `value`.
      - `neq` matches iff no element equals `value`.
  - `in` / `nin`:
    - `value` MUST be an array. If `value` is not an array, the filter is invalid and the mapping
      pack MUST be rejected as invalid (detection stage fatal `bridge_mapping_pack_invalid`).
    - If resolved VALUE is a scalar:
      - `in` matches iff the scalar is equal to any element of `value`.
      - `nin` matches iff the scalar is equal to no elements of `value`.
    - If resolved VALUE is an array:
      - `in` matches iff any element is equal to any element of `value`.
      - `nin` matches iff no element is equal to any element of `value` (intersection empty).
  - `contains` / `prefix` / `suffix`:
    - `value` MUST be a string. If `value` is not a string, the filter is invalid and the mapping
      pack MUST be rejected as invalid (detection stage fatal `bridge_mapping_pack_invalid`).
    - Resolved VALUE MUST be a string, or an array of strings.
    - When resolved VALUE is an array, the predicate matches iff any element matches.
    - `prefix` is equivalent to a "starts with" match; `suffix` is equivalent to an "ends with"
      match.
  - `regex`:
    - `value` MUST be a string. If `value` is not a string, the filter is invalid and the mapping
      pack MUST be rejected as invalid (detection stage fatal `bridge_mapping_pack_invalid`).
    - Resolved VALUE MUST be a string, or an array of strings (any-element semantics).
    - Patterns MUST be compatible with the configured regex dialect (default: PCRE2).
    - `regex` is a search match unless the pattern is explicitly anchored.

Determinism:

- When emitting `filters[]`, the router MUST preserve the order as stored in the router table
  snapshot.
- Mapping pack authors SHOULD order filters deterministically (RECOMMENDED: sort by `path`, then
  `op`, then canonical JSON of `value`).

Example (router table route entry):

Note: `metadata.source_type` values MUST use mapping-pack `event_source_type` tokens (see ADR-0002)
and MUST conform to `id_slug_v1` (see ADR-0001).

```json
{
  "sigma_logsource": { "category": "process_creation", "product": "windows" },
  "ocsf_scope": { "class_uids": [1007] },
  "filters": [
    { "path": "metadata.source_type", "op": "eq", "value": "windows-security" },
    { "path": "raw.channel", "op": "eq", "value": "Security" },
    { "path": "raw.provider", "op": "eq", "value": "Microsoft-Windows-Security-Auditing" }
  ]
}
```

Multi-class routing semantics (normative):

- A route that produces multiple `class_uid` values is a valid, fully-determined route.
- The evaluator MUST evaluate the rule against the **union** of all routed classes.
  - Equivalent semantics: `class_uid IN (<uids. .>)` or `(class_uid = u1 OR class_uid = u2 OR . .)`.
  - The evaluator MUST NOT pick an arbitrary single class when multiple classes are routed.
- For determinism and diffability, the router MUST emit multi-class `class_uid` sets in ascending
  numeric order.
- Backend implementations MAY realize union semantics via:
  - a single query with `class_uid IN (. .)`, or
  - multiple per-class subqueries combined as a deterministic UNION of results.

### Rules

Route selection MUST be deterministic and MUST be computed only from:

- the Sigma rule `logsource` object, and
- `bridge/router_table.json` `routes[]` content.

#### Token normalization (normative)

For matching purposes, implementations MUST normalize each token by:

1. trimming ASCII whitespace, then
1. ASCII-lowercasing (`A-Z` → `a-z`).

This applies to:

- `logsource.category`, `logsource.product`, `logsource.service`
- `routes[].sigma_logsource.{category,product,service}`

#### Matching (normative)

A route `r` matches a rule `L` iff:

- `r.sigma_logsource.category == L.category`, AND
- if `r.sigma_logsource.product` is present, `L.product` MUST be present and equal, AND
- if `r.sigma_logsource.service` is present, `L.service` MUST be present and equal.

Notes:

- A route MUST NOT match a rule by "assuming" a missing `product/service`.
  - If a rule omits `product/service`, only routes that also omit those fields may match.

#### Specificity and selection (normative)

Define:

- `specificity(r) = count_present(r.sigma_logsource.product) + count_present(r.sigma_logsource.service)`

Selection algorithm:

1. Compute `matches = { r | r matches L }`.
1. If `matches` is empty:
   - The rule MUST be marked non-executable with `reason_code="unroutable_logsource"`.
   - `non_executable_reason.explanation` MUST include the normalized `logsource` tuple and MUST
     state whether the category was unknown vs known-but-unmatched on product/service.
1. Else:
   - Let `m = max_{r in matches} specificity(r)`.
   - Let `best = { r in matches | specificity(r) == m }`.
   - If `best` contains exactly one route, select it.
   - If `best` contains more than one route:
     - The rule MUST be marked non-executable with `reason_code="unroutable_logsource"`.
     - `non_executable_reason.explanation` MUST begin with `Ambiguous routing:` and MUST list the
       matching route signatures (`category`, `product`, `service`) in deterministic order.

#### Selected route output (normative)

For the selected route:

- `ocsf_scope.class_uids` MUST be emitted as an ascending numeric list.
- `filters[]` MUST be preserved in the stored order of the router table snapshot.
- Multi-class routing is a union scope, not an ambiguity.

### Mapping packs

#### Selection and pins (normative)

When `detection.sigma.enabled=true`, the bridge MUST resolve a mapping pack using:

- `detection.sigma.bridge.mapping_pack_id` (pack id)
- `detection.sigma.bridge.mapping_pack_version` (pack version)

The resolved `(mapping_pack_id, mapping_pack_version)` MUST be recorded in run provenance
(`manifest.versions.*`) per ADR-0001.

If mapping pack resolution or contract validation fails, the detection stage MUST fail with
`reason_code="bridge_mapping_pack_invalid"`. The stage `fail_mode` MUST follow
`detection.sigma.bridge.fail_mode` (default: `fail_closed`).

#### Authoring guidance (non-normative)

Adopt SigmaHQ’s OCSF routing where possible, then constrain to the pinned OCSF version and the
enabled normalization mapping profiles for the run (`normalization.mapping_profiles`).

#### Version domain (normative)

The mapping pack version domain is independent of:

- the Sigma ruleset version
- the Purple Axiom pipeline version

## Field alias map

Translate Sigma field references into backend-evaluable OCSF field selectors.

Terminology:

- OCSF field path: a dot-delimited path rooted at the OCSF event object (example: `process.name`).
- Backend field expression: a backend-specific expression derived deterministically from an OCSF
  field path (example for struct-typed values: `process.name`).

### Structure

Field aliases SHOULD be scoped by router result (at minimum by `logsource.category`), because field
meaning varies by event family.

### Multi-class aliasing note (normative)

If a rule routes to multiple OCSF classes, each referenced Sigma field MUST resolve
deterministically.

- If a Sigma field maps to different OCSF field paths/expressions per routed class, the bridge MUST
  either:
  - emit a deterministic resolution expression (for example, a class-ordered `COALESCE(. .)`), or
  - mark the rule non-executable with `reason_code="ambiguous_field_alias"`.

A deterministic resolution expression is permitted only when:

- each candidate expression is type-compatible under the backend, and
- the expression ordering is deterministic (ascending by `class_uid`), and
- the semantics are explicitly "value from any routed class" (union semantics at the field level).

Recommended structure (conceptual):

- `aliases[logsource.category][sigma_field] -> ocsf_path_or_expr`
- `normalizers[sigma_field] -> value transforms` (case folding, path normalization, enum
  harmonization)

### Fallback policy (raw field fallback)

This section governs *rule-field* fallback to `raw.*` when the mapping pack does not provide a
normalized OCSF alias for a referenced Sigma field.

#### Distinguish two uses of `raw.*` (normative)

1. `raw.*` in router `filters[]`:

   - Router routes MAY include `filters[]` whose `path` begins with `raw.` for producer
     disambiguation.
   - This usage is independent of `detection.sigma.bridge.raw_fallback_enabled`.

1. `raw.*` in Sigma field aliasing / compilation:

   - A Sigma selector MAY compile to a `raw.*` field path only when fallback is enabled by config
     `detection.sigma.bridge.raw_fallback_enabled=true`.

#### Safety gate: producer identification (normative)

Before evaluating any predicate that references `raw.*` (router filters or rule-field fallback), the
selected route MUST include an explicit producer/source identifier:

- At minimum, the route MUST include a filter:
  `{ "path": "metadata.source_type", "op": "eq", "value": "<event_source_type_token>" }`

If a route contains any `raw.*` filter and does not contain the required `metadata.source_type`
filter, the mapping pack MUST be rejected as invalid (detection stage fatal
`bridge_mapping_pack_invalid`).

If rule compilation requires `raw.*` fallback and the selected route does not contain the required
`metadata.source_type` filter, the rule MUST be marked non-executable with
`reason_code="raw_fallback_disabled"` and an explanation that the safety gate blocked fallback (raw
fallback is treated as effectively disabled for this rule).

#### Recording and determinism (normative)

If rule-field fallback is used, it MUST be observable in emitted outputs:

- `extensions.bridge.fallback_used` MUST be `true` on emitted detection instances.
- The list `extensions.bridge.unmapped_sigma_fields` MUST contain the Sigma field names that
  required fallback and MUST be de-duplicated and sorted by UTF-8 byte order (no locale).

If implementations also record the specific `raw.*` paths referenced, those lists MUST be
de-duplicated and sorted by UTF-8 byte order.

### Unsupported fields or modifiers

The bridge MUST classify Sigma features into one of:

- Supported (compiled into backend predicates),
- Ignored (accepted but does not affect execution in v0.1; recorded for observability), or
- Non-executable (rule cannot be evaluated safely/correctly).

#### Ignored modifiers (v0.1, normative)

- `timeframe`:
  - MUST be ignored for execution in v0.1 (no time-window constraint is applied).
  - MUST be recorded as an ignored modifier.
  - Any `ignored_modifiers[]` list MUST be de-duplicated and sorted by UTF-8 byte order.

#### Non-executable conditions (normative)

- If a rule references an unmapped field and fallback is disabled, the rule is **non-executable**.
- If the Sigma expression requires an operator or modifier outside the supported subset for the
  configured backend, the rule is **non-executable**.
- Non-executable rules MUST be reported via compiled plans and bridge coverage; they MUST NOT
  silently degrade into "no matches".

## Evaluator backend adapter

### Batch backend (v0.1 default)

- For v0.1, if `detection.sigma.bridge.backend` is omitted, the bridge MUST use `native_pcre2`
  (native evaluator with PCRE2 regex).
- The `native_pcre2` backend MUST evaluate compiled plans in-process over the normalized OCSF event
  store:
  - Tier 2: Parquet (preferred when present).
  - Tier 1: JSONL (fallback when Parquet is absent).
- Determinism settings (normative):
  - `threads = 1` (single-thread evaluation).
  - timezone = `UTC` (interpret event `time` as epoch milliseconds UTC).
  - regex dialect = `PCRE2` with bounded execution (see "Regex dialect and safety").
- The backend MUST compile Sigma rules (after routing and alias resolution) to an evaluator plan,
  then execute that plan over the routed OCSF scope.
- Output semantics (normative):
  - **Event rules** (Sigma rules with `logsource` + `detection`):
    - The backend MUST produce match results at event granularity.
    - Each match group MUST correspond to exactly one matched event id.
    - The evaluator MUST emit one detection instance per matched event with:
      - `matched_event_ids = [<event_id>]`
      - `first_seen_utc == last_seen_utc` (event time derived from OCSF `time`; UTC)
  - **Correlation rules** (Sigma rules with `correlation`):
    - The backend MUST produce match results at window granularity (multi-event).
    - Each match group MUST correspond to exactly one `(timespan_bucket_start, group_by_key)` pair.
    - The evaluator MUST emit one detection instance per satisfied group with:
      - `matched_event_ids = [<event_id>, ...]` (see determinism requirements for ordering)
      - `first_seen_utc = min(time)` over contributing events
      - `last_seen_utc = max(time)` over contributing events

Version pinning (normative):

- The `native_pcre2` backend MUST use the pinned PCRE2 version defined in the
  [supported versions reference](../../SUPPORTED_VERSIONS.md).
- The bridge MUST record the effective runtime versions used for:
  - PCRE2 (engine version),
  - pySigma (library version),
  - pySigma OCSF pipeline version (example: `pySigma-pipeline-ocsf`).
- If any effective version differs from the pins, the evaluator stage MUST fail closed (see the
  version drift policy in the [supported versions reference](../../SUPPORTED_VERSIONS.md)).

### Streaming backend (optional v0.2)

- Compile Sigma -> expression plan
- Evaluate over a stream processor (example: Tenzir)
- Emit matches in near real time

Note: streaming backends MAY implement a smaller regex dialect than `native_pcre2`. Any rule whose
required constructs are not supported MUST be marked non-executable (fail closed).

### Decision criteria for adding Tenzir (v0.2)

- Enables streaming evaluation for live lab exercises.
- Provides a composable pipeline language for derived fields and normalization.
- Integrates well with parquet + arrow formats.

### Backend conformance gates (CI)

Any backend implementation (including `native_pcre2` and `tenzir` in v0.2) MUST satisfy the
following.

Determinism and drift gates:

- Unit tests for compilation output normalization:
  - JSON output is canonicalized and stable
  - route selection and alias resolution are deterministic
- Integration tests:
  - the evaluator determinism conformance harness (see
    [test strategy CI: integration tests](../100_test_strategy_ci.md#integration-tests))
  - cross-backend conformance on the same BDP fixture when multiple batch backends are implemented
    (see `100_test_strategy_ci.md`, "Evaluator conformance harness").

Backend provenance requirements:

- Each compiled plan MUST record the backend id and version, and any deterministic settings that can
  affect match sets.
- The compiled plan MUST record:
  - `backend.id` (example: `native_pcre2`)
  - `backend.version` (semver string; the implementation MAY use the current pipeline version)
  - `backend.settings` (object; MUST include all determinism-relevant settings)

For `native_pcre2`, `backend.settings` MUST include at minimum:

- `threads` (integer)
- `timezone` (string; MUST equal `UTC`)
- `regex_dialect` (string; MUST equal `pcre2`)
- `regex_engine_version` (string)
- `regex_match_limit` (integer)
- `regex_depth_limit` (integer)

### Backend adapter contract (normative, v0.1)

This section defines the minimum executable subset and deterministic compilation requirements for
the evaluator backend adapter. It is authoritative for:

- what the bridge MUST compile and execute in v0.1 (supported subset),
- how compilation MUST be made deterministic, and
- which conditions MUST be classified as non-executable (fail closed).

#### Common requirements (all backends)

1. Output artifacts:

   - For each evaluated Sigma rule, the bridge MUST emit exactly one compiled plan file under
     `bridge/compiled_plans/<rule_id>.plan.json` (see "Bridge artifacts in the run bundle").
   - A compiled plan MUST declare `executable: true | false` and MUST either:
     - be executable (`executable=true` and contains backend-specific executable content), or
     - be explicitly non-executable (`executable=false` and contains `non_executable_reason` with a
       stable `reason_code` and a human-readable explanation).

1. Fail-closed semantics:

   - If routing is unknown, aliasing is unknown, or backend compilation cannot represent the rule,
     the bridge MUST mark the rule non-executable. It MUST NOT silently degrade into "no matches".

1. Deterministic match sets:

   - Any emitted list of matched `metadata.event_id` MUST be sorted deterministically prior to
     writing `detections/detections.jsonl`.
   - For correlation detections, each `matched_event_ids` array MUST be sorted by (`event_time` asc,
     then `event_id` asc).

1. Deterministic compilation inputs:

   - Compilation MUST be a pure function of:
     - rule content,
     - router output (routed scope),
     - mapping pack snapshot (aliases, transforms, fallback policy),
     - backend id and version,
     - backend determinism settings (if any).

1. Backend-neutral compiled-plan IR boundary (normative):

   - To support optional backends without losing determinism, compilation MUST produce a
     backend-neutral intermediate representation (IR) after routing + alias resolution and before
     any backend-specific lowering.
   - For v0.1, the IR is the `pa_eval_v1` plan IR defined below. The IR MUST be stored under
     `backend.plan_kind="pa_eval_v1"` and `backend.plan`.
   - Backend adapters MUST treat `pa_eval_v1` as the semantic source of truth. If a backend requires
     an internal representation (for example SQL, an in-memory bytecode, or a streaming query), it
     MUST deterministically lower from this IR.
   - Backends MUST NOT introduce backend-specific semantics at the IR layer. Any backend that cannot
     preserve the IR semantics MUST mark the rule non-executable (fail closed) using the appropriate
     `reason_code`.

1. Deterministic lowering requirements (normative):

   - Lowering MUST be a pure function of:
     - the IR object (`backend.plan`),
     - `backend.id`, `backend.version`, and
     - `backend.settings`.
   - Lowering MUST NOT inspect runtime telemetry values and MUST NOT depend on event distribution.
   - Lowering MUST NOT use randomized identifiers. Any generated names (aliases, temp columns, etc.)
     MUST be derived deterministically from stable inputs (RECOMMENDED: hash of the IR subtree).
   - If lowering fails (compiler exception, unsupported feature), the rule MUST be marked
     non-executable with `reason_code="backend_compile_error"` (it MUST NOT degrade into "no
     matches).

1. IR canonicalization rules (normative):

   These rules ensure different implementations and backends emit a byte-stable, backend-neutral IR.

   - For `predicate` nodes with `op in {"and","or"}`:
     - Implementations MUST flatten nested nodes of the same `op`.
     - `args[]` MUST be sorted by the ascending RFC 8785 canonical JSON byte sequence (JCS) of each
       arg node.
   - For `cmp` nodes:
     - When `value` is an array (Sigma list membership), the array MUST be de-duplicated and sorted
       deterministically by `(type_rank, jcs(element))`, where `type_rank` is:
       `null < false < true < number < string` and `jcs(element)` is the RFC 8785 canonical JSON
       byte sequence for that element.
     - Sigma list membership MUST be represented as a single `cmp` node with `value` as an array.
       Implementations MUST NOT expand membership into an explicit OR tree.

#### Supported Sigma expression subset (bridge-level, v0.1 MVP)

The following MUST be supported by the v0.1 evaluator adapter for the default backend
(`native_pcre2`) after routing and alias resolution.

Event-rule selector primitives (field-to-value comparisons):

- Equality:
  - `field: <scalar>` (string, number, boolean)
  - `field: [<scalar> . .]` (list membership)
- Inequality:
  - `field|neq: <scalar>`
- Existence:
  - `field|exists: true|false`
- Relational (numeric only):
  - `field|lt`, `field|lte`, `field|gt`, `field|gte`
- String matching:
  - `field|contains`
  - `field|startswith`
  - `field|endswith`
- Regex matching:
  - `field|re` (PCRE2; case-insensitive by default)
  - `field|re|i`, `field|re|m`, `field|re|s`, and combinations thereof

Modifiers:

- `|cased` MUST be supported for string and regex matching.

Boolean composition:

- `and`, `or`, `not` over selections and subexpressions
- `1 of selection*` and `all of selection*` (wildcard selection groups)

Sigma correlation rules (supported by default backend):

Rules that include a top-level `correlation` section MUST be supported by the default backend
(`native_pcre2`) as defined in the Sigma correlation rules specification. Supported correlation
types:

- `event_count`
- `value_count`
- `temporal`
- `ordered_temporal`

Supported correlation fields (minimum):

- `correlation.rules` (referenced rule names and/or ids)
- `correlation.type`
- `correlation.timespan`
- `correlation.group-by`
- `correlation.condition` (optional; numeric comparisons, including `gte`, `gt`, `lte`, `lt`, `eq`)
- `correlation.field` (required for `value_count`)
- `correlation.aliases` (optional; correlation field unification)
- `correlation.generate` (optional)

Out of scope in v0.1 (MUST be marked non-executable when encountered):

- Temporal aggregation semantics inside event rules (example: `count()`, `near`, `within`) unless
  expressed as a Sigma correlation rule.
- Field modifiers that require binary transforms (example: `base64`, `utf16`, `windash`) unless the
  mapping pack has already materialized an equivalent normalized value.
- Regex patterns that are not compatible with the configured regex dialect or are rejected by the
  regex safety policy (see "Regex dialect and safety").

#### Native evaluator adapter requirements (native_pcre2, normative)

The `native_pcre2` adapter compiles Sigma rules into a JSON evaluator plan that is executed by the
in-process evaluator.

##### MVP compilation gate

- The adapter MUST treat any Sigma construct not listed in the supported subset as non-executable in
  v0.1.
- The adapter MUST emit `executable=false` with an appropriate `non_executable_reason` whenever:
  - a modifier/operator is not supported,
  - routing is ambiguous or unmapped,
  - alias resolution yields unknown fields and raw fallback is disabled,
  - correlation semantics cannot be represented.

##### Plan IR format (pa_eval_v1)

`pa_eval_v1` is the bridge's backend-neutral plan IR for batch evaluation. The `native_pcre2`
backend executes this IR directly; any other batch backend MUST deterministically lower from this IR
while preserving the semantics defined below.

When `executable=true`, a compiled plan MUST include IR content under `backend.plan` with:

- `backend.plan_kind = "pa_eval_v1"`
- `backend.plan` (object; schema defined below)

For `native_pcre2`, `backend.id` MUST equal `"native_pcre2"`.

`backend.plan` schema (normative):

- `scope` (object)
  - `class_uids` (array of integers; derived from routing)
- `predicate` (object; event-rule predicate AST)
- `correlation` (object; optional; present only for correlation rules)

Predicate AST (normative, minimal):

- Logical:
  - `{ "op": "and", "args": [<expr>, ...] }` (args length >= 2)
  - `{ "op": "or", "args": [<expr>, ...] }` (args length >= 2)
  - `{ "op": "not", "arg": <expr> }`
- Field tests:
  - `{ "op": "exists", "field": "<ocsf_path>", "value": true|false }`
  - `{ "op": "cmp", "cmp": "eq|neq|lt|lte|gt|gte", "field": "<ocsf_path>", "value": <scalar_or_list> }`
  - `{ "op": "match", "kind": "contains|startswith|endswith", "field": "<ocsf_path>", "value": "<string>", "cased": true|false }`
  - `{ "op": "regex", "field": "<ocsf_path>", "pattern": "<string>", "flags": "<string>", "cased": true|false }`

Semantics (normative):

- `<ocsf_path>` uses dot-notation over the normalized OCSF JSON object.
- Missing paths evaluate as NULL.
- For scalar comparisons, NULL evaluates as false.
- For list-typed fields:
  - `cmp:eq` MUST evaluate as true if any element equals the target value.
  - `cmp:neq` MUST evaluate as true if no element equals the target value (and field is present).
- For `field: [v1, v2, ...]` (Sigma list membership), compilation MUST produce a single `cmp:eq`
  node with `value` set to the list (array) of candidate values.
  - The list MUST be de-duplicated and sorted deterministically (see "IR canonicalization rules").

##### Compiled plan semantic validation policy

A semantic validation phase MUST run after compilation and before publishing a compiled plan to
`bridge/compiled_plans/`. The validator ensures that any `executable=true` plan is safe and
meaningful for the selected backend and the pinned OCSF schema version.

The semantic validator MUST be deterministic for a fixed plan + pinned schema inputs and MUST NOT
depend on runtime telemetry values.

Checks (normative; apply to `executable=true` plans):

1. **Field existence (pinned OCSF schema)**:

   - Every referenced `field` path in the predicate AST (`exists|cmp|match|regex`) MUST resolve to a
     valid field path in the pinned OCSF schema version for the run (see `050_normalization_ocsf.md`
     for the v0.1 pin).
   - Exception: `raw.*` paths are allowed only when permitted by the raw fallback policy gates (see
     "Fallback policy (raw field fallback)").
   - If a referenced non-`raw.*` field path cannot be resolved, the rule MUST be marked
     non-executable with `reason_code="unmapped_field"` and a stable, machine-actionable error
     subcode in the explanation (for example `PA_BRIDGE_INVALID_OCSF_PATH`).

1. **Operator allowlist**:

   - Predicate nodes MUST use only the operators enumerated in the Plan format AST above.
   - Unknown operators MUST be rejected deterministically with `reason_code="unsupported_operator"`.

1. **Scope completeness**:

   - `backend.plan.scope.class_uids` MUST be present and MUST be non-empty.
   - `class_uids` MUST be emitted in ascending numeric order (determinism requirement).
   - Missing/empty scope MUST be treated as a compiler/validator error and MUST fail closed as
     `reason_code="backend_compile_error"`.

1. **Complexity budgets**:

   - Regex nodes MUST satisfy the configured regex safety limits (pattern length, match limits, and
     depth limits; see `120_config_reference.md`).

   - When the detection performance budget gate is enabled (see `110_operability.md`),
     implementations MUST compute deterministic predicate-AST complexity metrics for each compiled
     plan:

     - `predicate_ast_op_nodes`: the number of JSON objects with an `"op"` key in
       `backend.plan.predicate` (root included; `args`/`field`/`value` leaf objects without `"op"`
       are not counted).
     - `predicate_ast_max_depth`: maximum nesting depth of `"op"` objects in the predicate tree
       (root depth = 1).
     - `predicate_ast_regex_nodes`: number of predicate operator nodes where `op == "regex"`.

   - Implementations SHOULD also enforce predicate-AST size budgets to prevent pathological
     compilation outputs:

     - `detection.sigma.limits.max_predicate_ast_nodes_per_rule` (optional): maximum allowed
       `predicate_ast_op_nodes` per rule.
     - `detection.sigma.limits.max_predicate_ast_nodes_total` (optional; default RECOMMENDED:
       5,000): maximum allowed sum of `predicate_ast_op_nodes` across all compiled, executable
       rules.

     Exceedance SHOULD be surfaced via the detection performance budget gate
     (`detection.performance_budgets`) as defined in `110_operability.md`.

Verification hook (normative):

- CI MUST include fixtures that demonstrate deterministic rejection for:
  - an invalid field reference,
  - a prohibited regex, and
  - a plan missing required scope. (See `100_test_strategy_ci.md`.)

##### Regex dialect and safety

- The evaluator MUST interpret `regex.pattern` using PCRE2 syntax.
- The evaluator MUST perform regex matching as a search by default (not implicitly anchored).
- Case-insensitive matching MUST be the default unless `cased=true` or an explicit flag is present.
- `regex.flags` MUST be a stable concatenation of single-letter flags in sorted order. Supported
  flags (minimum):
  - `i` (case-insensitive)
  - `m` (multiline)
  - `s` (dot matches newline)
- The evaluator MUST enforce bounded execution for all regex matches:
  - `regex_match_limit` (maximum backtracking steps)
  - `regex_depth_limit` (maximum recursion depth)
- Patterns that exceed configured limits (length, compilation failure, unsupported options) MUST be
  classified as non-executable with `reason_code=unsupported_regex`.

##### Correlation plan and semantics

When present, `backend.plan.correlation` MUST conform to the following minimal schema:

- `type`: `event_count | value_count | temporal | ordered_temporal`
- `rules`: array of referenced rule ids (resolved at compile time; stable order)
- `timespan_ms`: integer (parsed from `correlation.timespan`)
- `group_by`: array of correlation field names (stable order as in source)
- `condition`: optional object `{ "op": "gte|gt|lte|lt|eq", "value": <number> }`
- `field`: required for `value_count` (correlation field name)
- `aliases`: optional mapping:
  - `<correlation_field_name>` -> object:
    - `<rule_id>` -> `<sigma_field_name>`
- `generate`: optional boolean (default false)

Field resolution and key extraction (normative):

- For each referenced rule id, the compiler MUST build a per-rule extraction map from:
  - each correlation `group_by` field name, and the `field` (for `value_count`),
  - to an OCSF field path using that rule's resolved field aliases and transforms.
- If any required field cannot be resolved for any referenced rule, the correlation rule MUST be
  marked non-executable (`reason_code=unsupported_correlation`).
- During evaluation, correlation keys MUST be computed per event by extracting the resolved OCSF
  field values for that rule.

Time bucketing (normative):

- `timespan_bucket_start` MUST be computed by flooring the event's UTC time to the `timespan_ms`
  interval anchored at Unix epoch (`1970-01-01T00:00:00Z`).
- All events with the same `(timespan_bucket_start, group_by_key)` MUST be considered part of the
  same correlation group.

Correlation types (normative, minimal):

- `event_count`: Count the number of matched events across all referenced rules in the group.
- `value_count`: Count distinct values of the `field` across all matched events in the group.
- `temporal`: Count distinct referenced rule ids present in the group.
- `ordered_temporal`: Succeeds if there exists an in-order sequence of matched events whose rule id
  order matches the order in `correlation.rules` within the same group.

Unless otherwise specified by the Sigma rule, the default `condition` for `temporal` and
`ordered_temporal` MUST be: `>= len(correlation.rules)`.

##### Non-executable classification mapping (normative)

The bridge MUST use the following `reason_code` values for common failure modes:

- Unknown logsource -> unroutable_logsource
- Unmapped field without raw fallback -> unmapped_field
- Raw fallback required but disabled or blocked by policy -> raw_fallback_disabled
- Unsupported modifier -> unsupported_modifier
- Unsupported operator -> unsupported_operator
- Unsupported value type -> unsupported_value_type
- Regex rejected by backend policy (example: exceeds regex limits) -> unsupported_regex
- Correlation semantics encountered but not representable -> unsupported_correlation
- Aggregation semantics encountered -> unsupported_aggregation
- Backend compiler exception -> backend_compile_error
- Backend evaluation error -> backend_eval_error

All non-executable classifications MUST be recorded as a `(reason_domain, reason_code)` pair:

- `reason_domain` MUST equal `bridge_compiled_plan`.

## Bridge artifacts in the run bundle

When Sigma evaluation is enabled, the bridge MUST emit a contract-validated set of artifacts under
`runs/<run_id>/bridge/` so routing, compilation, and coverage are reproducible and mechanically
testable.

These artifacts MUST conform to the data contracts specification, including canonical hashing rules.

### Required artifacts (v0.1)

- `router_table.json` (required)

  - MUST include `router_table_id`, `router_table_version`, `ocsf_version`, `routes[]`,
    `router_table_sha256`, and `generated_at_utc`.
  - `router_table_sha256` MUST be computed as specified by the data contracts specification (SHA-256
    over canonical JSON stable inputs; MUST exclude `generated_at_utc`) and MUST be serialized as
    `sha256:<lowercase_hex>`.

- `mapping_pack_snapshot.json` (required)

  - MUST include `mapping_pack_id`, `mapping_pack_version`, `ocsf_version`, `router_table_ref`,
    `field_aliases`, `fallback_policy`, optional `backend_defaults`, `mapping_pack_sha256`, and
    `generated_at_utc`.
  - `router_table_ref` MUST reference the router table by id + version + `router_table_sha256`.
    Mapping packs SHOULD embed the referenced router table for single-file reproducibility.
  - `mapping_pack_sha256` MUST be computed as specified by the data contracts specification (SHA-256
    over canonical JSON stable inputs; MUST exclude run-specific fields such as `run_id`,
    `scenario_id`, and `generated_at_utc`) and MUST be serialized as `sha256:<lowercase_hex>`.

- `compiled_plans/` (directory; required)

  - `compiled_plans/<rule_id>.plan.json` MUST be emitted for each evaluated rule.
  - Each plan MUST include:
    - `rule_id`
    - `rule_sha256` (SHA-256 digest string in `sha256:<lowercase_hex>` form over canonical Sigma
      rule bytes per the data contracts specification; see canonical rule hashing guidance in
      `060_detection_sigma.md`)
    - `mapping_pack_sha256` (`sha256:<lowercase_hex>`)
    - `executable` (boolean)
    - `non_executable_reason` when `executable=false`

- `coverage.json` (required)

  - MUST include:

    - `mapping_pack_ref` (at minimum: `mapping_pack_id`, `mapping_pack_version`,
      `mapping_pack_sha256` (`sha256:<lowercase_hex>`))
    - `mapping_profile_sha256` (`sha256:<lowercase_hex>`)
    - `ocsf_version`
    - `total_rules`
    - `routed_rules`
    - `executable_rules`
    - `matched_rules`
    - `match_events_total`
    - `fallback_used_rules`
    - `non_executable_reason_counts` (map: `reason_code -> count`)
    - `top_unmapped_fields` (array of `{field, count}`; MAY be empty)
    - `top_unroutable_logsources` (array of `{logsource, count}`; MAY be empty)

  - Determinism:

    - `top_unmapped_fields` MUST be sorted by (`count` desc, then `field` asc).
    - `top_unroutable_logsources` MUST be sorted by (`count` desc, then `logsource` asc).

### Cross-artifact invariants (normative)

- `mapping_pack_snapshot.json.ocsf_version` MUST match the run's OCSF version pins (including
  `manifest.versions.ocsf_version`).

- `mapping_pack_snapshot.json.mapping_pack_id` and `mapping_pack_snapshot.json.mapping_pack_version`
  MUST match the resolved mapping pack pins recorded in `manifest.versions.*` (see ADR-0001).

- When present, `bridge/coverage.json.mapping_profile_sha256` MUST match
  `normalized/mapping_profile_snapshot.json.mapping_profile_sha256`.

- Any mismatch MUST fail closed and MUST NOT proceed with rule evaluation.

  - Fail-closed reason code (stage-level): `bridge_mapping_pack_invalid`
  - Stage `fail_mode`: follow `detection.sigma.bridge.fail_mode`

## Bridge provenance in detections

Detection instances (which represent executable rules that produced ≥1 match) SHOULD include bridge
provenance in `extensions.bridge`, such as:

- `mapping_pack_id`, `mapping_pack_version`
- `mapping_pack_sha256` (`sha256:<lowercase_hex>`)
- `backend`, `compiled_at_utc`
- `fallback_used` (when rule-field `raw.*` fallback was required)
- `unmapped_sigma_fields` (when compilation required dropping selectors or using fallback)
- `ignored_modifiers` (when any ignored modifiers were present)

Non-executable rules MUST NOT emit detection instances. Non-executable status MUST be represented
via:

- `bridge/compiled_plans/<rule_id>.plan.json` (`non_executable_reason`), and
- `bridge/coverage.json`.

Also store the original Sigma `logsource` under `extensions.sigma.logsource` (verbatim) when
available.

## Determinism and reproducibility requirements

- Compilation is deterministic given:
  - rule content
  - mapping pack id/version
  - backend id/version
- Ordering:
  - `detections/detections.jsonl` written in a deterministic order (see storage requirements)
- Fail-closed:
  - unknown logsource, unmapped fields (without fallback), or unsupported modifiers MUST not
    silently degrade into "no matches"

## State machine integration hooks (representational, non-normative)

The bridge’s per-rule compilation/evaluation lifecycle is a candidate for explicit state machine
modeling per ADR-0007 to improve determinism, observability, and testability.

Lifecycle authority remains:

- ADR-0005 (stage outcomes and reason codes)
- Data contracts specification (required artifacts when detection is enabled)
- Detection specification (Sigma execution model + representational per-rule lifecycle)
- This specification (routing, aliasing, backend adapter contract, and non-executable reasons)

Representational per-rule lifecycle (v0.1; within the detection stage):

- `loaded` → `compiled(executable=true)` → `evaluated`
- `loaded` → `compiled(executable=true)` → `evaluated(error)` (recorded as non-executable with
  `non_executable_reason.reason_code: "backend_eval_error"`)
- `loaded` → `compiled(executable=false)` (non-executable; recorded in `bridge/compiled_plans/`)

Observable anchors (run bundle):

- Stage outcome: `manifest.json` / `logs/health.json` entry for stage `detection` (status +
  reason_code)
- Publish gate artifacts when enabled: `detections/detections.jsonl` and `bridge/**`
- Per-rule compiled plan files: `bridge/compiled_plans/<rule_id>.plan.json` (executable flag and
  `non_executable_reason`)

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

- [Detection specification](060_detection_sigma.md)
- [Configuration reference](120_config_reference.md)
- [Reporting specification](080_reporting.md)
- [ADR-0001: Project naming and versioning](../adr/ADR-0001-project-naming-and-versioning.md)
- [Supported versions reference](../../SUPPORTED_VERSIONS.md)
- [Test strategy CI](100_test_strategy_ci.md)
- [Bridge router table schema](../contracts/bridge_router_table.schema.json)
- [Bridge mapping pack schema](../contracts/bridge_mapping_pack.schema.json)
- [Bridge compiled plan schema](../contracts/bridge_compiled_plan.schema.json)
- [Bridge coverage schema](../contracts/bridge_coverage.schema.json)

## Changelog

| Date       | Change                                                                                                  |
| ---------- | ------------------------------------------------------------------------------------------------------- |
| 2026-01-24 | Clarify routing determinism, filter semantics, timeframe handling, and bridge artifact/provenance rules |
| 2026-01-12 | Formatting update                                                                                       |
