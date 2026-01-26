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
    - Patterns MUST be RE2-compatible.
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

- `detection.sigma.bridge.mapping_pack` (pack id)
- `detection.sigma.bridge.mapping_pack_version` (pack version)

The resolved `(mapping_pack_id, mapping_pack_version)` MUST be recorded in run provenance
(`manifest.json.versions.*`) per ADR-0001.

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
  field path (example for DuckDB structs: `process.name`).

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

- For v0.1, if `detection.sigma.bridge.backend` is omitted, the bridge MUST use `duckdb_sql` (DuckDB
  SQL over Parquet).
- The `duckdb_sql` backend MUST enforce deterministic DuckDB session settings:
  - `SET threads = 1;`
  - `SET TimeZone = 'UTC';`
- If the implementation allows overriding these settings for performance, it MUST record the
  effective values in backend provenance (see "Backend provenance").
- Compile Sigma -> SQL (after routing + aliasing)
- Execute over OCSF Parquet using DuckDB
- Output (normative, v0.1):
  - The backend MUST produce match results at *event granularity*.
  - Each match group MUST correspond to exactly one matched event id.
  - The evaluator MUST emit one detection instance per matched event with:
    - `matched_event_ids = [<event_id>]`
    - `first_seen_utc == last_seen_utc` (event time derived from the OCSF `time` field; UTC)

Version pinning (normative):

- The `duckdb_sql` backend MUST use the pinned DuckDB version defined in the
  [supported versions reference](../../SUPPORTED_VERSIONS.md).
- The bridge MUST record the effective runtime versions used for:
  - DuckDB (library/runtime version),
  - pySigma (library version), in backend provenance within each compiled plan.
  - pySigma OCSF pipeline version (e.g., `pySigma-pipeline-ocsf`)
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

Any backend implementation (including `duckdb_sql` and `tenzir` in v0.2) MUST satisfy the following.
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
- **Explained failure modes**: non-executable compiled plans MUST include a stable, machine-readable
  `non_executable_reason.reason_code` and a human-readable explanation in `non_executable_reason`.

### Backend adapter contract (normative, v0.1)

This section defines the minimum executable subset and deterministic compilation requirements for
the evaluator backend adapter. It is authoritative for:

- what the bridge MUST compile and execute in v0.1 (supported subset),
- how compilation MUST be made deterministic, and
- which conditions MUST be classified as non-executable (fail-closed).

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
  - `field: [<scalar> . .]` (list membership)
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
- Temporal aggregation semantics (for example: `count()`, `near`, `within`, "threshold" rules)
- Field modifiers that require binary transforms (example: `base64`, `utf16`, `windash`) unless the
  mapping pack has already materialized an equivalent normalized value
- PCRE-only regex constructs (lookaround, backreferences, etc.). Regex matching is supported only in
  an RE2-compatible subset; non-conforming patterns MUST be treated as Non-executable.

#### DuckDB SQL adapter requirements (duckdb_sql, normative)

This section defines the backend adapter contract for compiling Sigma expressions into DuckDB SQL.
This contract is aligned with research report R-03 (DuckDB backend plugin for pySigma).

#### MVP compilation gate

MVP compilation is allowed only when all constructs required by the rule are explicitly listed as
Supported by this specification and the configured backend section.

Any construct that is not explicitly listed as Supported MUST be treated as Non-executable and MUST
map to exactly one `non_executable_reason.reason_code`.

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
  DuckDB regex functions use RE2 and accept option flags.
- Timestamp extraction: `|hour`, `|day`, `|month`, `|year` against the canonical `time` field.
- LIST semantics: equality against LIST-typed fields MUST mean any element matches. The adapter MUST
  use DuckDB list functions when the field is LIST-typed.

#### Deferred (post-MVP)

The following constructs are explicitly deferred and MUST be treated as Non-executable in v0.1:

- CIDR match (`|cidr`) pending extension packaging and type policy decisions.
- Base64 transforms (`|base64`, `|base64offset`).
- Field reference (`|fieldref`) pending typing policy.
- Case-sensitive mode (`|cased`) beyond the DuckDB regex option surface.

#### SQL compilation requirements (normative)

##### SQL safety (normative)

- Generated queries MUST be read-only and MUST be a single statement of the form
  `WITH ... SELECT ...` or `SELECT ...`.
- The adapter MUST compile against a pre-registered relation containing the normalized OCSF events
  (table or view), and MUST NOT embed file paths or use DuckDB table functions (for example,
  `read_csv`, `read_parquet`) in generated SQL.
- The adapter MUST NOT emit statements that can mutate state or load code (non-exhaustive): `COPY`,
  `ATTACH`, `DETACH`, `EXPORT`, `IMPORT`, `CREATE`, `INSERT`, `UPDATE`, `DELETE`, `INSTALL`, `LOAD`.

##### Type policy (normative)

- The adapter MUST determine field types using the normalized store schema snapshot (when present),
  otherwise it MAY introspect the backend catalog.
- If a required field’s type is unknown, the rule MUST be non-executable with
  `reason_code="unsupported_value_type"` (fail closed).
- The adapter MUST NOT apply implicit casts.

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
     - For non-string types: `field IN (v1, v2, . .)`
     - For string-typed membership: `lower(field) IN (lower(v1), lower(v2), . .)`
   - Ordering: list value expansions MUST preserve the input order from the Sigma rule and MUST NOT
     be reordered as a "determinism" technique.

1. LIST-typed field semantics:

   - If the resolved field expression is LIST-typed, scalar comparisons MUST mean "any element
     matches" and MUST compile using DuckDB list functions:
     - Single value: `list_contains(field, value)`
     - Multiple values (default OR semantics): `list_has_any(field, [values. .])`
     - `all` modifier: `list_has_all(field, [values. .])`
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

   - The adapter MUST validate patterns as RE2-compatible at compile time.

   - PCRE-only constructs (lookahead, lookbehind, backreferences, atomic groups, etc.) MUST be
     rejected as Non-executable with reason_code `unsupported_regex`.

   - Options mapping:

     - `|re|i` MUST compile with option `i` (case-insensitive).
     - `|re|m` MUST compile with a newline-sensitive option (`m` or its DuckDB equivalents).
     - `|re|s` MUST compile with option `s` (non-newline sensitive).

1. Timestamp extraction:

   - The adapter MUST treat `time` as INT64 epoch milliseconds (UTC) and MUST compile date-part
     operations using `epoch_ms(time)` and `date_part()`.

1. Failure reporting:

   - When a rule cannot be compiled, the bridge MUST record a Non-executable compiled plan entry
     with:
     - a stable `reason_code`, and
     - a deterministic `explanation` string.
   - For backend-originated compilation failures, the `explanation` MUST include the stable backend
     error code prefix `PA_SIGMA_. .` (as defined by R-03) to support deterministic aggregation.
   - `explanation` strings MUST be deterministic and redaction-safe:
     - MUST NOT include raw event payload fragments or `raw.*` values.
     - SHOULD avoid embedding volatile backend text (file paths, line numbers, memory addresses);
       include only stable error tokens plus minimal, non-sensitive context.

1. Determinism requirements:

   - Generated SQL MUST be stable with fixed parenthesization, deterministic literal escaping,
     deterministic identifier quoting, and preserved input ordering for list expansions.

#### Non-executable classification mapping (normative)

Failure reporting: when a rule cannot be compiled, the adapter MUST record a Non-executable compiled
plan entry with a stable `non_executable_reason.reason_code` and deterministic explanation string.
At a minimum, the following mappings MUST apply:

- Unknown logsource -> unroutable_logsource
- Ambiguous field alias resolution -> ambiguous_field_alias
- Unmapped Sigma field (no alias + fallback disabled) -> unmapped_field
- Raw fallback required but disabled or blocked by policy -> raw_fallback_disabled
- Unsupported modifier -> unsupported_modifier
- Unsupported operator -> unsupported_operator
- Unsupported value type -> unsupported_value_type
- Regex rejected by backend policy (for example non-RE2 constructs) -> unsupported_regex
- Correlation / multi-event semantics encountered -> unsupported_correlation
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
    over canonical JSON stable inputs; MUST exclude `generated_at_utc`).

- `mapping_pack_snapshot.json` (required)

  - MUST include `mapping_pack_id`, `mapping_pack_version`, `ocsf_version`, `router_table_ref`,
    `field_aliases`, `fallback_policy`, optional `backend_defaults`, `mapping_pack_sha256`, and
    `generated_at_utc`.
  - `router_table_ref` MUST reference the router table by id + version + `router_table_sha256`.
    Mapping packs SHOULD embed the referenced router table for single-file reproducibility.
  - `mapping_pack_sha256` MUST be computed as specified by the data contracts specification (SHA-256
    over canonical JSON stable inputs; MUST exclude run-specific fields such as `run_id`,
    `scenario_id`, and `generated_at_utc`).

- `compiled_plans/` (directory; required)

  - `compiled_plans/<rule_id>.plan.json` MUST be emitted for each evaluated rule.
  - Each plan MUST include:
    - `rule_id`
    - `rule_sha256` (SHA-256 over canonical Sigma rule bytes per the data contracts specification;
      see canonical rule hashing guidance in `060_detection_sigma.md`)
    - `mapping_pack_sha256`
    - `executable` (boolean)
    - `non_executable_reason` when `executable=false`

- `coverage.json` (required)

  - MUST include:

    - `mapping_pack_ref` (at minimum: `mapping_pack_id`, `mapping_pack_version`,
      `mapping_pack_sha256`)
    - `mapping_profile_sha256`
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
  `manifest.json.versions.ocsf_version`).

- `mapping_pack_snapshot.json.mapping_pack_id` and `mapping_pack_snapshot.json.mapping_pack_version`
  MUST match the resolved mapping pack pins recorded in `manifest.json.versions.*` (see ADR-0001).

- When present, `bridge/coverage.json.mapping_profile_sha256` MUST match
  `normalized/mapping_profile_snapshot.json.mapping_profile_sha256`.

- Any mismatch MUST fail closed and MUST NOT proceed with rule evaluation.

  - Fail-closed reason code (stage-level): `bridge_mapping_pack_invalid`
  - Stage `fail_mode`: follow `detection.sigma.bridge.fail_mode`

## Bridge provenance in detections

Detection instances (which represent executable rules that produced ≥1 match) SHOULD include bridge
provenance in `extensions.bridge`, such as:

- `mapping_pack_id`, `mapping_pack_version`
- `mapping_pack_sha256`
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
