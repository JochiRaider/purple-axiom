# DuckDB_Backend_Plugin_for_pySigma (Purple Axiom)

Research Report Draft v0

## 1. Purpose

Define the researched ground truth and an initial, testable capability plan for a **pySigma DuckDB
backend plugin** that emits **DuckDB SQL** for executing Sigma rules against **OCSF-normalized
data** in Purple Axiom.

This report is a draft pending validation experiments enumerated in Section 8.

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
  Sigma defaults to case-insensitive matching and `cased` requests case-sensitive matching.

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

The DuckDB backend MVP MUST reject (fail closed) any rule that requires **any other**
standardized Sigma modifier, including (non-exhaustive): `contains`, `startswith`, `endswith`, `re`
(and sub-modifiers), `exists`, `cidr`, time-part modifiers, `base64*`, `fieldref`, and `expand`.

Correlation rules (Sigma correlation) are **out of MVP scope** and MUST be rejected as
non-executable.

#### Phase 0 deliverable: fail-closed policy

- The backend MUST implement a **compile-time** executability check.
- If a rule is not within the MVP capability boundary, the backend MUST NOT emit partial SQL.
  It MUST return a compilation failure with a machine-readable error code (see taxonomy below).

#### Phase 0 deliverable: error taxonomy skeleton

The following taxonomy is a **skeleton** intended to stabilize implementation and tests. Codes are
prefixed with `PA_SIGMA_` to disambiguate from upstream pySigma exceptions.

| Code | Class | Trigger (compile-time) | Notes / expected remediation |
|---|---|---|---|
| `PA_SIGMA_E0001_UNSUPPORTED_RULE_TYPE` | Non-executable (MVP) | Rule type is not a basic detection rule (e.g., correlation) | Documented as out-of-scope for MVP. |
| `PA_SIGMA_E0002_UNSUPPORTED_MODIFIER` | Non-executable (MVP) | Any modifier outside the MVP set is present | Where relevant, include `modifier`, `field`, and `gap_id` (e.g., `GAP-01`). |
| `PA_SIGMA_E0003_UNSUPPORTED_OPERATOR` | Non-executable (MVP) | Operator not supported by MVP (e.g., wildcard semantics, regex semantics) | Use for cases where syntax implies operator behavior rather than an explicit modifier. |
| `PA_SIGMA_E0004_TYPE_POLICY_VIOLATION` | Non-executable (MVP) | Numeric comparison applied to non-numeric literal, or casting policy rejects the comparison | Include `field`, `operator`, `value` summary, and the casting policy name/version. |
| `PA_SIGMA_E0005_PLACEHOLDER_UNRESOLVED` | Non-executable (MVP) | Unexpanded placeholder remains (e.g., `expand` not applied upstream) | Indicates a pipeline contract failure; backend fails closed. |
| `PA_SIGMA_E0006_BACKEND_OPTION_INVALID` | Configuration error | Backend option missing/invalid (e.g., `table_name` empty) | Fail closed before compilation. |
| `PA_SIGMA_E0007_INTERNAL_INVARIANT` | Bug | Backend invariant violated (unexpected AST shape) | Treated as an implementation defect; should not occur for validated inputs. |

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

**Deliverable:** Data projection note + minimal fixtures demonstrating behavior.

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
