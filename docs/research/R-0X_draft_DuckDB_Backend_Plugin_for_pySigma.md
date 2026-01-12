# DuckDB Backend Plugin for pySigma (Purple Axiom)

Research Report Draft v0 (research-first)

## Research posture and prototype-start objective

This document is a **research synthesis plus a prototype-start plan**. It is intentionally written
to avoid locking in behavior where the semantics are not yet confirmed in the pinned environment.

Accordingly:

- Any SQL pattern or behavioral statement that depends on runtime semantics MUST be treated as a
  **candidate** until it is verified by a recorded prototype experiment.
- Anything marked **Requires validation** in the Supported Features Matrix is treated as
  **Non-executable** for MVP compilation until it is promoted by a recorded experiment.
- Prototype-oriented materials (fixtures, validation SQL, and work packages) are included as
  **appendices** so they are clearly scoped as prototyping inputs rather than settled research
  conclusions.

## 1. Purpose

Define the researched ground truth and an initial, testable capability plan for a **pySigma DuckDB
backend plugin** that emits **DuckDB SQL** for executing Sigma rules against **OCSF-normalized
data** in Purple Axiom.

This report is a draft; all validation work is planned and tracked via the research gaps checklist
(Section 8) and the phased prototype plan (Section 9).

## 2. Scope and non-goals

### 2.1 In scope

- Implement a **pySigma backend** that compiles Sigma detection conditions into **DuckDB SQL**
  (string output).
- Define a deterministic, test-driven **supported modifier surface** for MVP.
- Define required validation experiments for correctness and determinism.

pySigma backend responsibilities and conventions: emit query strings; no data-model mapping; accept
backend options via `__init__(**backend_options)`.

### 2.2 Out of scope (owned by pipelines or Purple Axiom)

- Sigma field-name and taxonomy translation to OCSF. This is pipeline work.
- OCSF normalization itself (telemetry → normalized envelope).
- Result scoring, reporting, and run-bundle packaging (owned elsewhere in Purple Axiom specs).

## 3. Authoritative sources (initial anchor set)

- pySigma: Backends (backend contract, option passing).
- pySigma: Plugin System (namespace package conventions).
- SigmaHQ plugin directory metadata patterns (sigma-cli discovery).
- Sigma specification appendix: standardized modifiers and semantics (including chaining order,
  default case-insensitivity, and `cased`).
- DuckDB documentation: `LIKE` / `ILIKE` semantics.
- DuckDB documentation: regex uses **RE2** and function-based matching with options.
- DuckDB documentation: struct and list access/functionality.
- DuckDB documentation: inet extension for CIDR containment operators.
- Reference precedent: pySigma SQLite backend “Supported Features” pattern.

## 4. Integration model for Purple Axiom

### 4.1 Flow

1. Sigma rule (YAML)
1. Processing pipeline applies OCSF field mapping and rule conditioning
1. DuckDB backend compiles the post-pipeline rule into DuckDB SQL
1. Purple Axiom executes SQL against DuckDB tables/views representing normalized OCSF events

This separation is aligned with pySigma’s stated division of responsibilities: backends emit
queries, pipelines handle data-model alignment.

### 4.2 Data projection assumptions (must be validated)

Purple Axiom is expected to query OCSF-normalized events stored in a shape DuckDB can access,
likely:

- nested STRUCT columns for OCSF objects, and
- LIST columns for OCSF arrays.

DuckDB supports struct access via dot/bracket notation and list operations via list functions and
`unnest`.

A key risk is missing-field semantics. DuckDB notes `struct_extract` throws on missing keys. This
can affect compilation of `exists` and safe field access.

## 5. Backend packaging and discovery

### 5.1 Runtime import contract

Backends live under `sigma.backends.<name>` and export a dict named `backends` mapping identifiers
to backend classes.

### 5.2 sigma-cli discovery contract

sigma-cli also relies on the SigmaHQ plugin directory format (UUID primary key, plugin type, package
spec, pysigma version constraints, metadata URLs).

## 6. Determinism controls (draft requirements)

These are draft requirements intended to become spec language later:

- The backend MUST emit SQL with **stable ordering** for boolean expansions:

  - list value default OR expansion order MUST follow the input value order.
  - `all` MUST switch OR to AND while preserving input order.

- The backend MUST define canonical escaping:

  - identifier quoting policy (likely double quotes),
  - string literal quoting policy (single quotes, with deterministic escaping),
  - LIKE pattern escaping policy (documented `ESCAPE` usage).

- The backend MUST define a stable policy for Sigma’s default case-insensitive semantics, because
  Sigma defaults to case-insensitive matching and `cased` requests case-sensitive matching. The
  *selection* of that policy (e.g., `ILIKE` vs `lower()` vs collation) is a research item (see
  GAP-01) and MUST NOT be treated as executable for MVP until validated.

## 7. Supported Features Matrix (DuckDB SQL candidates)

### 7.1 Legend

- **Supported**: implementable now with documented DuckDB semantics.
- **Requires validation**: plausible SQL exists; experiments required to confirm semantics or Purple
  Axiom assumptions.
- **Non-executable (MVP)**: not claimed for MVP without additional infrastructure or upstream
  pipeline work.

### 7.2 Matrix (by capability)

| Capability                 | Sigma construct                            | DuckDB SQL candidate                                                       | Status                               |                     |                     |                  |                     |
| -------------------------- | ------------------------------------------ | -------------------------------------------------------------------------- | ------------------------------------ | ------------------- | ------------------- | ---------------- | ------------------- |
| Boolean expansion          | list values default OR                     | `(expr(v1) OR expr(v2) OR ...)`                                            | Supported                            |                     |                     |                  |                     |
| Boolean expansion          | `all`                                      | `(expr(v1) AND expr(v2) AND ...)`                                          | Supported                            |                     |                     |                  |                     |
| Equality (string, default) | (implicit)                                 | Prefer `ILIKE`-based strategy                                              | Requires validation                  |                     |                     |                  |                     |
| Case sensitivity           | `cased`                                    | Use `LIKE` (case-sensitive) vs `ILIKE`                                     | Requires validation                  |                     |                     |                  |                     |
| Inequality (null-safe)     | `neq`                                      | `field IS DISTINCT FROM value`                                             | Supported                            |                     |                     |                  |                     |
| Existence                  | `exists: true/false`                       | `field IS NOT NULL` / `field IS NULL`                                      | Requires validation                  |                     |                     |                  |                     |
| Substring match            | `contains`                                 | \`field ILIKE '%'                                                          |                                      | esc(v)              |                     | '%' ESCAPE '$'\` | Requires validation |
| Prefix match               | `startswith`                               | \`field ILIKE esc(v)                                                       |                                      | '%' ESCAPE '$'\`    | Requires validation |                  |                     |
| Suffix match               | `endswith`                                 | \`field ILIKE '%'                                                          |                                      | esc(v) ESCAPE '$'\` | Requires validation |                  |                     |
| Regex match                | `re`                                       | `regexp_matches(field, pattern, opts)`                                     | Requires validation                  |                     |                     |                  |                     |
| Regex options              | `re\|i`                                    | `regexp_matches(field, pattern, 'i')`                                      | Requires validation (policy)         |                     |                     |                  |                     |
| Regex options              | `re\|m`, `re\|s`                           | `regexp_matches(field, pattern, 'm'/'s')`                                  | Requires validation                  |                     |                     |                  |                     |
| CIDR membership            | `cidr`                                     | `CAST(field AS INET) <<= CAST(cidr AS INET)`                               | Requires validation (inet extension) |                     |                     |                  |                     |
| Numeric compare            | `lt/lte/gt/gte`                            | `field < <= > >= value`                                                    | Supported (with casting policy)      |                     |                     |                  |                     |
| Time extraction            | `minute/hour/day/week/month/year`          | `date_part('x', ts_field)`                                                 | Requires validation                  |                     |                     |                  |                     |
| Base64 transforms          | `base64`, `base64offset` (+ utf16 submods) | `to_base64(encode(...))` plus variant generation                           | Requires validation                  |                     |                     |                  |                     |
| Field reference            | `fieldref`                                 | `field = other_field`                                                      | Requires validation (schema typing)  |                     |                     |                  |                     |
| Placeholder expansion      | `expand`                                   | Pipeline responsibility; backend fails closed if unresolved                | Non-executable (MVP)                 |                     |                     |                  |                     |
| OCSF list fields           | scalar compare vs LIST                     | `list_has_any(list_field, [value])` or `EXISTS(SELECT 1 FROM unnest(...))` | Requires validation                  |                     |                     |                  |                     |
| OCSF list fields + all     | `all` on list membership                   | `list_has_all(list_field, [v1..])`                                         | Requires validation                  |                     |                     |                  |                     |

### 7.3 Immediate MVP recommendations (draft)

- Claim “Supported” only for:

  - boolean expansion rules,
  - `all`,
  - `neq` via null-safe inequality,
  - numeric comparisons (with an explicit casting policy).

Everything else stays “Requires validation” or “Non-executable” until experiments pass.

## 8. Known gaps checklist (enumerated, delegable)

Each gap includes a recommended owner and an output artifact.

**GAP-01: Case-insensitive default semantics and determinism**

- Question: Should default string equality/contains use `ILIKE`, `lower()`, or collation?
- Risk: Locale-dependent behavior if `ILIKE` varies with locale.
- Owner: Backend engineer + determinism reviewer
- Output: Decision note + conformance tests over a fixed fixture set
- Sources: Sigma default case-insensitivity; DuckDB `ILIKE`.

**GAP-02: Wildcard translation rules**

- Question: Confirm Sigma wildcard characters and exact translation to DuckDB LIKE (`%`, `_`) with
  `ESCAPE`.
- Owner: Backend engineer
- Output: Unit tests for wildcard escaping and matching correctness
- Sources: DuckDB `LIKE`/`ESCAPE`, Sigma modifiers appendix.

**GAP-03: Safe nested field access for OCSF projection**

- Question: Are OCSF fields queried as nested STRUCT? If so, how to avoid missing-key runtime
  errors?
- Owner: Data engineer + backend engineer
- Output: A documented field-access strategy and fixtures proving behavior
- Sources: DuckDB struct access and missing-key behavior.

**GAP-04: Regex compatibility policy (Sigma PCRE-subset vs DuckDB RE2)**

- Question: Which Sigma regex constructs are accepted, rejected, or rewritten?
- Owner: Detection engineer + backend engineer
- Output: Compatibility matrix and compile-time failure taxonomy
- Sources: DuckDB RE2 regex and Sigma `re` modifiers.

**GAP-05: Regex option mapping for `m` and `s`**

- Question: Do DuckDB regex options match Sigma semantics for multiline and dotall?
- Owner: Backend engineer
- Output: Targeted tests demonstrating correct behavior
- Sources: DuckDB regex options; Sigma `re|m`, `re|s`.

**GAP-06: inet extension policy for `cidr`**

- Question: How is `inet` extension loaded/pinned in offline or deterministic environments?
- Owner: Platform/packaging engineer
- Output: Operational policy + pinned external requirement if needed
- Sources: DuckDB inet extension and containment operators.

**GAP-07: OCSF array/list semantics**

- Question: When a Sigma rule targets a list-typed OCSF field, do we interpret it as “any element
  equals”?
- Owner: Detection engineer + backend engineer
- Output: Documented semantics + list conformance tests
- Sources: DuckDB list functions and `unnest`.

**GAP-08: Timestamp typing and timezone normalization for time-part modifiers**

- Question: Are timestamp columns TIMESTAMP, TIMESTAMP WITH TIME ZONE, or strings? What timezone is
  assumed?
- Owner: Data engineer
- Output: Schema note + tests for `date_part` behavior
- Sources: Sigma time modifiers intent; DuckDB `date_part`.

**GAP-09: Base64 and UTF-16 sub-modifier algorithm correctness**

- Question: Do we need these in Purple Axiom’s normalized OCSF context, or only for raw sources?
- Owner: Detection engineer
- Output: Scope decision; if in-scope, deterministic encoding algorithm + tests
- Sources: Sigma base64 modifiers; DuckDB base64 functions.

**GAP-10: Fieldref typing and cross-field comparisons**

- Question: How to handle comparisons across fields with differing DuckDB types (string vs numeric
  vs timestamp)?
- Owner: Backend engineer
- Output: Casting policy and error behavior tests
- Sources: DuckDB typing and SQL behavior (general).

**GAP-11: Placeholder expansion (`expand`) contract enforcement**

- Question: How do we guarantee expansions occur in pipelines, and that the backend fails closed
  otherwise?
- Owner: Pipeline maintainer
- Output: Pipeline contract tests ensuring no placeholders reach backend
- Sources: Sigma `expand` and pipeline responsibility.

## 9. Follow-up plan (phased, delegable)

### Phase 0: Decide MVP claim boundary (1 to 2 short tasks)

- Approve MVP claim set: boolean expansion, `all`, `neq`, numeric comparisons.
- Decide “fail closed” rules for everything else.

**Deliverable:** MVP capability statement and error taxonomy skeleton.

**Rule (Phase 0 gate):** MVP compilation is allowed only when **all** required rule features are
classified as **Supported** in the Supported Features Matrix (Section 7). Any feature classified as
**Requires validation** MUST be treated as **Non-executable** until it is explicitly promoted to
**Supported** by a recorded validation experiment.

#### Phase 0 deliverable: MVP capability statement

For purposes of this report, the DuckDB backend is considered **MVP-capable** only if it can compile
Sigma rules that use **only** the following constructs:

- Boolean structure:
  - AND / OR / NOT combinations emitted with stable parentheses as required by precedence.
  - List-valued comparisons expanded deterministically:
    - default: OR across values in input order,
    - with `all`: AND across values in input order.
- Comparisons:
  - Numeric comparisons: `lt`, `lte`, `gt`, `gte` against numeric literals.
  - Null-safe inequality: `neq` compiled using `IS DISTINCT FROM`.

The DuckDB backend MVP MUST reject (fail closed) any rule that requires **any other** standardized
Sigma modifier, including (non-exhaustive): `contains`, `startswith`, `endswith`, `re` (and
sub-modifiers), `exists`, `cidr`, time-part modifiers, `base64*`, `fieldref`, and `expand`.

Correlation rules (Sigma correlation) are **out of MVP scope** and MUST be rejected as
non-executable.

#### Phase 0 deliverable: fail-closed policy

- The backend MUST implement a **compile-time** executability check.
- If a rule is not within the MVP capability boundary, the backend MUST NOT emit partial SQL. It
  MUST return a compilation failure with a machine-readable error code (see taxonomy below).

#### Phase 0 deliverable: error taxonomy skeleton

The following taxonomy is a **skeleton** intended to stabilize implementation and tests. Codes are
prefixed with `PA_SIGMA_` to disambiguate from upstream pySigma exceptions.

| Code                                    | Class                | Trigger (compile-time)                                                                      | Notes / expected remediation                                                           |
| --------------------------------------- | -------------------- | ------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| `PA_SIGMA_E0001_UNSUPPORTED_RULE_TYPE`  | Non-executable (MVP) | Rule type is not a basic detection rule (e.g., correlation)                                 | Documented as out-of-scope for MVP.                                                    |
| `PA_SIGMA_E0002_UNSUPPORTED_MODIFIER`   | Non-executable (MVP) | Any modifier outside the MVP set is present                                                 | Where relevant, include `modifier`, `field`, and `gap_id` (e.g., `GAP-01`).            |
| `PA_SIGMA_E0003_UNSUPPORTED_OPERATOR`   | Non-executable (MVP) | Operator not supported by MVP (e.g., wildcard semantics, regex semantics)                   | Use for cases where syntax implies operator behavior rather than an explicit modifier. |
| `PA_SIGMA_E0004_TYPE_POLICY_VIOLATION`  | Non-executable (MVP) | Numeric comparison applied to non-numeric literal, or casting policy rejects the comparison | Include `field`, `operator`, `value` summary, and the casting policy name/version.     |
| `PA_SIGMA_E0005_PLACEHOLDER_UNRESOLVED` | Non-executable (MVP) | Unexpanded placeholder remains (e.g., `expand` not applied upstream)                        | Indicates a pipeline contract failure; backend fails closed.                           |
| `PA_SIGMA_E0006_BACKEND_OPTION_INVALID` | Configuration error  | Backend option missing/invalid (e.g., `table_name` empty)                                   | Fail closed before compilation.                                                        |
| `PA_SIGMA_E0007_INTERNAL_INVARIANT`     | Bug                  | Backend invariant violated (unexpected AST shape)                                           | Treated as an implementation defect; should not occur for validated inputs.            |

##### Error payload shape (informative)

When returning a compilation failure, the backend SHOULD return (or raise) an error object
containing at least:

- `code`: one of the codes above
- `message`: human-readable summary (single line)
- `rule_id`: Sigma `id` if present
- `feature`: modifier/operator/rule-type that triggered the failure
- `field`: field name if applicable
- `gap_id`: optional link to Section 8 gap checklist (e.g., `GAP-01`)

### Phase 1: Schema reality checks (highest leverage)

- Run GAP-03 (nested fields) and GAP-08 (timestamp typing).
- Produce a single “OCSF-in-DuckDB access note” (field access, list behavior, timestamp type).

**Deliverable:** A prototype work package (Appendix C) that defines the minimal fixtures and
validation queries, plus a short note capturing the *verified* results once experiments are
executed.

### Phase 2: String semantics and matching

- Run GAP-01 and GAP-02 and lock:

  - case-insensitive policy,
  - wildcard translation,
  - LIKE escaping rules.

**Deliverable:** Golden SQL emission tests for `contains`, `startswith`, `endswith`, equality.

### Phase 3: Regex policy

- Run GAP-04 and GAP-05 and decide:

  - allowed RE2 subset,
  - compile-time rejection rules.

**Deliverable:** Regex compatibility matrix + negative fixtures for rejected patterns.

### Phase 4: Extensions and advanced modifiers

- Run GAP-06 (inet) and decide packaging pinning approach.
- Decide whether to include base64 family (GAP-09) in MVP or defer.

**Deliverable:** Operational note and updated external requirements if needed.

## 10. What to improve next in this report (concrete upgrades)

For the next revision cycle, the report should incorporate:

1. A **backend option catalog** (initial list: `table_name`, output format, case policy switch,
   timezone policy, inet enablement), explicitly labeled “proposed” until validated.
1. A **compile-time failure classification** for “non-executable” constructs (regex-incompatible,
   schema-dependent access, requires extension, unresolved expand).
1. A **mapping from GAP IDs to test artifacts** (fixture path conventions and golden SQL naming).
1. A short “comparison to precedent” section, explicitly borrowing the SQLite backend’s
   supported-features documentation style and gating pattern.

## Appendix A: DuckDB Version Notes

This note assumes DuckDB 1.0+. Key version-dependent behaviors:

| Feature           | DuckDB Version | Notes                    |
| ----------------- | -------------- | ------------------------ |
| `TRY()` wrapper   | 0.9+           | Returns NULL on error    |
| `epoch_ms()`      | 0.8+           | Converts ms to TIMESTAMP |
| `list_contains()` | 0.3+           | Stable                   |
| `list_has_any()`  | 0.9+           | Multi-value membership   |
| `list_has_all()`  | 0.9+           | All-value membership     |

______________________________________________________________________

## Appendix B: References

- Purple Axiom `docs/spec/045_storage_formats.md` (storage schema contract)
- Purple Axiom `docs/spec/055_ocsf_field_tiers.md` (field tier definitions)
- Purple Axiom `docs/contracts/ocsf_event_envelope.schema.json` (JSON Schema)
- DuckDB Documentation: Nested Types (STRUCT, LIST)
- DuckDB Documentation: Date/Time Functions
- pySigma DuckDB Backend Draft: `R-0X_draft_DuckDB_Backend_Plugin_for_pySigma.md`

## Appendix C: Prototype work packages (planned validation inputs)

The material in this appendix is intentionally written as prototyping inputs. It preserves the
current research and candidate SQL patterns, but it does not claim they are correct until
experiments are recorded.

Phase 1 Deliverable for pySigma DuckDB Backend Plugin

## **GAP-03 (Nested Fields) + GAP-08 (Timestamp Typing) Resolution**

## 1. Executive Summary

This work package defines the behaviors to be verified (via documentation review and prototype
experiments) for accessing OCSF-normalized data in DuckDB, specifically addressing:

- **GAP-03**: Safe nested field access for OCSF STRUCT projections
- **GAP-08**: Timestamp typing and time-part extraction

**Working hypotheses / candidate strategies (to validate):**

| Concern                | Purple Axiom Schema                     | DuckDB Access Strategy                            | Risk Level |
| ---------------------- | --------------------------------------- | ------------------------------------------------- | ---------- |
| Nested STRUCT access   | `metadata.uid`, `actor.user.name`, etc. | Dot notation with TRY_CAST or COALESCE guard      | Medium     |
| Missing keys in STRUCT | Sparse nested objects                   | `struct_extract` throws; use `TRY(...)` wrapper   | High       |
| LIST field membership  | `device.ips[]`, `metadata.labels[]`     | `list_contains()` or `unnest()`                   | Medium     |
| Timestamp type         | `time` (int64 ms), `time_dt` (string)   | `time` for `date_part()`; cast to TIMESTAMP first | Low        |

______________________________________________________________________

## 2. Purple Axiom OCSF Schema Summary

Per `docs/spec/045_storage_formats.md` and `docs/contracts/ocsf_event_envelope.schema.json`:

### 2.1 Minimum Required Columns (Parquet)

```
time              INT64      -- ms since epoch, UTC (Tier 0)
time_dt           VARCHAR    -- ISO-8601/RFC3339 string (convenience)
class_uid         INT32      -- OCSF class identifier (Tier 0)
category_uid      INT32      -- nullable
type_uid          INT32      -- nullable
severity_id       INT32      -- nullable
```

### 2.2 Nested STRUCT Columns

```
metadata          STRUCT     -- provenance object (required)
  .uid            VARCHAR    -- MUST equal .event_id (ADR-0002)
  .event_id       VARCHAR    -- deterministic idempotency key
  .run_id         VARCHAR    -- UUID
  .scenario_id    VARCHAR
  .source_type    VARCHAR    -- e.g., 'sysmon', 'wineventlog', 'osquery'
  .labels         VARCHAR[]  -- array of strings
  ...

device            STRUCT     -- nullable
  .hostname       VARCHAR
  .uid            VARCHAR
  .ip             VARCHAR
  .ips            VARCHAR[]  -- array of IPs

actor             STRUCT     -- nullable
  .user           STRUCT
    .name         VARCHAR
    .uid          VARCHAR
  .process        STRUCT
    .name         VARCHAR
    .pid          INT32

raw               STRUCT     -- preserved vendor fields (nullable)
```

______________________________________________________________________

## 3. GAP-03: Nested Field Access

### 3.1 Problem Statement

DuckDB's `struct_extract()` (and dot notation which compiles to it) **throws an error** when
accessing a key that does not exist in the STRUCT schema. This affects:

- Sigma rules targeting fields that may be absent in some events
- The `exists` modifier compilation
- Safe access patterns for sparse nested objects

### 3.2 Behavior to confirm (expected per DuckDB documentation; validate in the pinned version)

**Dot notation:**

```sql
SELECT metadata.uid FROM events;           -- OK if 'uid' key exists in schema
SELECT actor.user.name FROM events;        -- OK if full path exists
SELECT actor.user.phone FROM events;       -- ERROR if 'phone' not in schema
```

**Expected behaviors to confirm (DuckDB 1.0+):**

1. Schema-defined keys: Dot access works; NULL if row value is NULL
1. Schema-missing keys: Runtime error on `struct_extract`
1. Entire STRUCT NULL: Accessing nested key returns NULL (no error)

### 3.3 Recommended Access Strategies

#### Strategy A: Schema-Guaranteed Fields (Tier 0/1)

For fields guaranteed by Purple Axiom's contract, use direct dot notation:

```sql
-- Safe: Tier 0 contract-required
SELECT metadata.uid, metadata.source_type, time, class_uid
FROM ocsf_events;

-- Safe: Tier 1 when populated
SELECT device.hostname, actor.user.name
FROM ocsf_events;
```

#### Strategy B: Sparse/Optional Fields (Tier 2+)

For fields that may not exist in the STRUCT schema, use DuckDB's `TRY()` wrapper:

```sql
-- Returns NULL instead of throwing if path doesn't exist
SELECT TRY(actor.process.parent.name) AS parent_name
FROM ocsf_events;
```

#### Strategy C: Existence Checks (Sigma `exists` modifier)

```sql
-- Check if field is NOT NULL (works for schema-present fields)
SELECT * FROM ocsf_events
WHERE actor.user.name IS NOT NULL;

-- For potentially schema-missing fields, guard with TRY:
SELECT * FROM ocsf_events
WHERE TRY(actor.process.parent.name) IS NOT NULL;
```

### 3.4 Backend Compilation Recommendations

| Sigma Construct           | DuckDB SQL Pattern                         |
| ------------------------- | ------------------------------------------ |
| `field: value` (Tier 0/1) | `field = 'value'` or `field ILIKE 'value'` |
| `field: value` (Tier 2+)  | `TRY(field) = 'value'`                     |
| `field\|exists: true`     | `TRY(field) IS NOT NULL`                   |
| `field\|exists: false`    | `TRY(field) IS NULL`                       |

**MVP Decision:** For MVP, the backend SHOULD assume pipeline-provided field names are schema-valid
and use direct dot notation. The `TRY()` wrapper is recommended for post-MVP or when targeting
heterogeneous schemas.

______________________________________________________________________

## 4. GAP-07 (Related): LIST Field Semantics

### 4.1 OCSF Array Fields in Purple Axiom

```
device.ips[]        VARCHAR[]   -- multiple IPs
metadata.labels[]   VARCHAR[]   -- classification labels
metadata.debug[]    VARCHAR[]   -- debug strings
```

### 4.2 DuckDB LIST Operations

**Membership check (any element equals):**

```sql
-- Preferred: list_contains for scalar equality
SELECT * FROM ocsf_events
WHERE list_contains(device.ips, '10.0.0.1');

-- Alternative: list_has_any for multiple candidate values
SELECT * FROM ocsf_events
WHERE list_has_any(device.ips, ['10.0.0.1', '192.168.1.1']);
```

**All elements match (Sigma `all` modifier on list):**

```sql
-- Check if ALL candidate values are present
SELECT * FROM ocsf_events
WHERE list_has_all(device.ips, ['10.0.0.1', '192.168.1.1']);
```

**Substring/pattern on list elements:**

```sql
-- Must unnest for LIKE/ILIKE on elements
SELECT * FROM ocsf_events
WHERE EXISTS (
  SELECT 1 FROM unnest(device.ips) AS t(ip)
  WHERE ip ILIKE '10.%'
);
```

### 4.3 Backend Compilation Recommendations

| Sigma Construct                    | Target Field Type | DuckDB SQL Pattern                                             |
| ---------------------------------- | ----------------- | -------------------------------------------------------------- |
| `ips: '10.0.0.1'`                  | LIST              | `list_contains(ips, '10.0.0.1')`                               |
| `ips: ['10.0.0.1', '192.168.1.1']` | LIST              | `list_has_any(ips, [...])`                                     |
| `ips\|all: [...]`                  | LIST              | `list_has_all(ips, [...])`                                     |
| `ips\|contains: '10.'`             | LIST              | `EXISTS(SELECT 1 FROM unnest(ips) t(v) WHERE v ILIKE '%10.%')` |

______________________________________________________________________

## 5. GAP-08: Timestamp Typing

### 5.1 Purple Axiom Timestamp Schema

Per `docs/spec/045_storage_formats.md`:

| Column    | Type    | Semantics                                                  |
| --------- | ------- | ---------------------------------------------------------- |
| `time`    | INT64   | Milliseconds since Unix epoch (UTC)                        |
| `time_dt` | VARCHAR | ISO-8601/RFC3339 UTC string (e.g., `2026-01-08T14:30:00Z`) |

**Contract:**

- `time_dt` MUST be a deterministic rendering of `time` (no locale; UTC only)
- Both are always present (Tier 0)

### 5.2 DuckDB Timestamp Operations

**Converting `time` (ms epoch) to TIMESTAMP:**

```sql
-- Method 1: epoch_ms() function (preferred)
SELECT epoch_ms(time) AS ts FROM ocsf_events;

-- Method 2: make_timestamp from microseconds
SELECT make_timestamp(time * 1000) AS ts FROM ocsf_events;
```

**Extracting time parts (Sigma time modifiers):**

```sql
-- date_part on converted timestamp
SELECT date_part('hour', epoch_ms(time)) AS hour FROM ocsf_events;
SELECT date_part('day', epoch_ms(time)) AS day FROM ocsf_events;
SELECT date_part('month', epoch_ms(time)) AS month FROM ocsf_events;
SELECT date_part('year', epoch_ms(time)) AS year FROM ocsf_events;

-- Also available: 'minute', 'second', 'week', 'dayofweek', 'dayofyear'
```

**Using `time_dt` string (alternative):**

```sql
-- Cast string to TIMESTAMP, then extract
SELECT date_part('hour', CAST(time_dt AS TIMESTAMP)) AS hour
FROM ocsf_events;
```

### 5.3 Timezone Considerations

**Purple Axiom contract:** All timestamps are UTC-normalized.

- `time` is epoch ms (inherently UTC)
- `time_dt` is RFC3339 with `Z` suffix (explicit UTC)

**DuckDB behavior:**

- `TIMESTAMP` is timezone-naive (no TZ info stored)
- `TIMESTAMPTZ` is timezone-aware (stores UTC, renders in local TZ)

**Recommendation:** Use `TIMESTAMP` (not `TIMESTAMPTZ`) for Purple Axiom data since UTC is
guaranteed. This avoids any local timezone rendering surprises.

### 5.4 Backend Compilation Recommendations

| Sigma Modifier     | DuckDB SQL Pattern                         |
| ------------------ | ------------------------------------------ |
| `time\|hour: 14`   | `date_part('hour', epoch_ms(time)) = 14`   |
| `time\|day: 15`    | `date_part('day', epoch_ms(time)) = 15`    |
| `time\|month: 6`   | `date_part('month', epoch_ms(time)) = 6`   |
| `time\|year: 2026` | `date_part('year', epoch_ms(time)) = 2026` |
| `time\|minute: 30` | `date_part('minute', epoch_ms(time)) = 30` |
| `time\|week: 2`    | `date_part('week', epoch_ms(time)) = 2`    |

______________________________________________________________________

## 6. Minimal Fixtures

The following SQL creates a minimal test dataset for validating the behaviors documented above.

### 6.1 Fixture: Schema Definition

```sql
-- fixtures/gap_03_08/schema.sql
-- Minimal OCSF-like schema for DuckDB backend testing

CREATE TABLE ocsf_events (
  -- Tier 0: Core envelope
  time BIGINT NOT NULL,                    -- ms since epoch
  time_dt VARCHAR NOT NULL,                -- ISO-8601 string
  class_uid INTEGER NOT NULL,
  
  -- Tier 0: Metadata (nested STRUCT)
  metadata STRUCT(
    uid VARCHAR,
    event_id VARCHAR,
    run_id VARCHAR,
    source_type VARCHAR,
    labels VARCHAR[]
  ) NOT NULL,
  
  -- Tier 1: Device (nullable nested STRUCT)
  device STRUCT(
    hostname VARCHAR,
    uid VARCHAR,
    ip VARCHAR,
    ips VARCHAR[]
  ),
  
  -- Tier 1/2: Actor (nullable nested STRUCT)
  actor STRUCT(
    "user" STRUCT(
      name VARCHAR,
      uid VARCHAR
    ),
    process STRUCT(
      name VARCHAR,
      pid INTEGER
    )
  ),
  
  -- Tier R: Raw retention
  raw STRUCT(
    provider VARCHAR,
    event_id INTEGER
  )
);
```

### 6.2 Fixture: Sample Data

```sql
-- fixtures/gap_03_08/data.sql
-- Insert test records covering edge cases

INSERT INTO ocsf_events VALUES
  -- Record 1: Full population
  (
    1736344200000,                          -- 2026-01-08T14:30:00Z
    '2026-01-08T14:30:00Z',
    1007,                                   -- Process Activity
    {
      uid: 'evt-001',
      event_id: 'evt-001',
      run_id: 'run-2026-01-08',
      source_type: 'sysmon',
      labels: ['test', 'process']
    },
    {
      hostname: 'host-01',
      uid: 'host-01-guid',
      ip: '10.0.0.1',
      ips: ['10.0.0.1', '192.168.1.100']
    },
    {
      "user": { name: 'alice', uid: 'S-1-5-21-123' },
      process: { name: 'powershell.exe', pid: 4242 }
    },
    { provider: 'Microsoft-Windows-Sysmon', event_id: 1 }
  ),
  
  -- Record 2: Sparse actor (no user)
  (
    1736347800000,                          -- 2026-01-08T15:30:00Z
    '2026-01-08T15:30:00Z',
    1001,                                   -- File Activity
    {
      uid: 'evt-002',
      event_id: 'evt-002',
      run_id: 'run-2026-01-08',
      source_type: 'sysmon',
      labels: ['test', 'file']
    },
    {
      hostname: 'host-02',
      uid: NULL,
      ip: '10.0.0.2',
      ips: ['10.0.0.2']
    },
    {
      "user": NULL,                         -- No user context
      process: { name: 'cmd.exe', pid: 1234 }
    },
    { provider: 'Microsoft-Windows-Sysmon', event_id: 11 }
  ),
  
  -- Record 3: NULL device (osquery scenario)
  (
    1736351400000,                          -- 2026-01-08T16:30:00Z
    '2026-01-08T16:30:00Z',
    1007,
    {
      uid: 'evt-003',
      event_id: 'evt-003',
      run_id: 'run-2026-01-08',
      source_type: 'osquery',
      labels: NULL                          -- No labels
    },
    NULL,                                   -- No device context
    {
      "user": { name: 'root', uid: '0' },
      process: { name: 'bash', pid: 5678 }
    },
    NULL                                    -- No raw retention
  );
```

### 6.3 Fixture: Validation Queries

```sql
-- fixtures/gap_03_08/validate_gap_03.sql
-- GAP-03: Nested field access validation

-- Test 1: Direct dot access on Tier 0 field (should succeed)
SELECT metadata.uid, metadata.source_type FROM ocsf_events;

-- Test 2: Nested STRUCT access with NULL parent
SELECT device.hostname FROM ocsf_events;  -- Returns NULL for record 3

-- Test 3: Deep nested access
SELECT actor."user".name FROM ocsf_events;  -- Returns NULL for record 2

-- Test 4: Existence check pattern
SELECT *
FROM ocsf_events
WHERE actor."user".name IS NOT NULL;  -- Returns records 1, 3

-- Test 5: LIST field membership
SELECT *
FROM ocsf_events
WHERE list_contains(device.ips, '10.0.0.1');  -- Returns record 1

-- Test 6: LIST any-of matching
SELECT *
FROM ocsf_events
WHERE list_has_any(device.ips, ['10.0.0.2', '192.168.1.100']);  -- Records 1, 2

-- Test 7: LIST contains with pattern (requires unnest)
SELECT *
FROM ocsf_events
WHERE EXISTS (
  SELECT 1 FROM unnest(device.ips) AS t(ip)
  WHERE ip LIKE '10.%'
);  -- Records 1, 2
```

```sql
-- fixtures/gap_03_08/validate_gap_08.sql
-- GAP-08: Timestamp typing validation

-- Test 1: Convert epoch ms to timestamp
SELECT time, epoch_ms(time) AS ts FROM ocsf_events;

-- Test 2: Extract hour from epoch
SELECT time, date_part('hour', epoch_ms(time)) AS hour
FROM ocsf_events;
-- Observation goal: 14, 15, 16

-- Test 3: Extract date parts
SELECT
  time,
  date_part('year', epoch_ms(time)) AS year,
  date_part('month', epoch_ms(time)) AS month,
  date_part('day', epoch_ms(time)) AS day
FROM ocsf_events;
-- Observation goal: 2026, 1, 8 for all

-- Test 4: Filter by hour
SELECT * FROM ocsf_events
WHERE date_part('hour', epoch_ms(time)) = 14;  -- Record 1 only

-- Test 5: Verify time_dt string parsing matches time epoch
SELECT
  time,
  time_dt,
  epoch_ms(time) AS from_epoch,
  CAST(time_dt AS TIMESTAMP) AS from_string,
  epoch_ms(time) = CAST(time_dt AS TIMESTAMP) AS match
FROM ocsf_events;
-- Observation goal: match = true for all
```

______________________________________________________________________

## 7. Backend Implementation Checklist

### 7.1 GAP-03 Resolution

- [ ] Use direct dot notation for Tier 0/1 contract fields
- [ ] Document assumption that pipeline-provided field names are schema-valid
- [ ] Consider `TRY()` wrapper for post-MVP sparse field access
- [ ] Implement `exists` modifier as `field IS NOT NULL`

### 7.2 GAP-08 Resolution

- [ ] Use `epoch_ms(time)` to convert ms epoch to TIMESTAMP
- [ ] Use `date_part('x', epoch_ms(time))` for time modifiers
- [ ] Document UTC-only assumption (no timezone conversion needed)

### 7.3 GAP-07 Resolution (LIST fields)

- [ ] Implement scalar equality on LIST as `list_contains(field, value)`
- [ ] Implement multi-value OR on LIST as `list_has_any(field, [...])`
- [ ] Implement `all` modifier on LIST as `list_has_all(field, [...])`
- [ ] Implement pattern modifiers on LIST via `EXISTS(unnest(...)...)`

______________________________________________________________________

## 8. Open Questions for Follow-up

1. **TRY() performance**: Is there measurable overhead from wrapping all field accesses in `TRY()`?
   Requires benchmarking on real datasets.

1. **Schema evolution**: When OCSF schema changes (new fields), do Parquet files written with older
   schemas cause `struct_extract` errors? Mitigated by `union_by_name=true` but needs validation.

1. **LIST + modifier chaining**: How should `ips|contains|all: ['10.', '192.']` compile? (All IPs
   must contain both substrings, or each substring appears in at least one IP?)

______________________________________________________________________
