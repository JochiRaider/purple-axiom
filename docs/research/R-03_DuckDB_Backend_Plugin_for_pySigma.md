---
title: R-03 DuckDB backend plugin for pySigma
description: Defines the pySigma DuckDB backend capability surface, compilation patterns, and policy decisions for Purple Axiom.
status: draft
---

# R-03 DuckDB backend plugin for pySigma

This document defines the capability surface, compilation patterns, and policy decisions for a
pySigma backend plugin that emits DuckDB SQL for executing Sigma rules against OCSF-normalized
Parquet data in Purple Axiom.

## Overview

Purple Axiom requires a pySigma backend that compiles Sigma detection conditions into DuckDB SQL.
This document establishes the supported modifier surface, documents the SQL compilation patterns,
and records policy decisions for ambiguous cases.

Determinism and cross-platform stability are validated separately by the R-02 DuckDB conformance
harness. This document assumes R-02 acceptance criteria are met.

## Pinned versions

Per [Supported versions](../../SUPPORTED_VERSIONS.md):

| Dependency            | Version |
| --------------------- | ------: |
| DuckDB                |   1.4.3 |
| pySigma               |   1.1.0 |
| pySigma-pipeline-ocsf |   0.1.1 |
| Python                |  3.12.3 |

## Scope

This document covers:

- pySigma backend emitting DuckDB SQL strings.
- Supported Sigma modifier surface for MVP.
- SQL compilation patterns for each supported construct.
- Policy decisions for case sensitivity, escaping, and regex.

This document does NOT cover:

- Field name translation to OCSF (see the
  [Sigma-to-OCSF bridge specification](../spec/065_sigma_to_ocsf_bridge.md)).
- OCSF normalization (see the
  [OCSF normalization specification](../spec/050_normalization_ocsf.md)).
- Determinism validation (see the
  [R-02 DuckDB conformance report](R-02_DuckDB_Conformance_Report_and_Harness_Requirements_v1_4_3.md)).
- Result scoring and reporting (see the
  [Scoring metrics specification](../spec/070_scoring_metrics.md) and
  [Reporting specification](../spec/080_reporting.md)).

## Authoritative references

The capability claims in this document are grounded in the following sources:

| Topic                      | Source                                                                                  |
| -------------------------- | --------------------------------------------------------------------------------------- |
| DuckDB pattern matching    | [DuckDB Pattern Matching](https://duckdb.org/docs/sql/functions/pattern_matching)       |
| DuckDB regular expressions | [DuckDB Regular Expressions](https://duckdb.org/docs/sql/functions/regular_expressions) |
| DuckDB nested types        | [DuckDB Nested Types](https://duckdb.org/docs/sql/data_types/nested)                    |
| DuckDB list functions      | [DuckDB List Functions](https://duckdb.org/docs/sql/functions/list)                     |
| DuckDB date functions      | [DuckDB Date Functions](https://duckdb.org/docs/sql/functions/timestamp)                |
| RE2 syntax                 | [RE2 Syntax](https://github.com/google/re2/wiki/Syntax)                                 |
| Sigma specification        | [SigmaHQ Specification](https://github.com/SigmaHQ/sigma-specification)                 |

## Supported features matrix

### Legend

- **Supported**: Documented DuckDB behavior; included in MVP
- **Supported (post-MVP)**: Documented behavior; deferred for implementation priority
- **Non-executable**: Rejected at compile time with reason code

### MVP capability surface

| Capability                  | Sigma construct           | DuckDB SQL pattern                               | Status    |
| --------------------------- | ------------------------- | ------------------------------------------------ | --------- |
| Boolean OR                  | list values (default)     | `(expr OR expr OR ...)`                          | Supported |
| Boolean AND                 | `all` modifier            | `(expr AND expr AND ...)`                        | Supported |
| Equality                    | implicit                  | `field = value`                                  | Supported |
| Equality (case-insensitive) | implicit (default)        | `lower(field) = lower(value)`                    | Supported |
| Inequality                  | `neq`                     | `field IS DISTINCT FROM value`                   | Supported |
| Substring match             | `contains`                | `field ILIKE '%' \|\| value \|\| '%' ESCAPE '$'` | Supported |
| Prefix match                | `startswith`              | `field ILIKE value \|\| '%' ESCAPE '$'`          | Supported |
| Suffix match                | `endswith`                | `field ILIKE '%' \|\| value ESCAPE '$'`          | Supported |
| Existence                   | `exists`                  | `field IS NOT NULL` / `field IS NULL`            | Supported |
| Numeric comparison          | `lt\|lte\|gt\|gte`        | `field < \| <= \| > \| >= value`                 | Supported |
| Regex match                 | `re`                      | `regexp_matches(field, pattern)`                 | Supported |
| Regex case-insensitive      | `re\|i`                   | `regexp_matches(field, pattern, 'i')`            | Supported |
| Regex multiline             | `re\|m`                   | `regexp_matches(field, pattern, 'm')`            | Supported |
| Regex dotall                | `re\|s`                   | `regexp_matches(field, pattern, 's')`            | Supported |
| Time extraction             | `hour\|day\|month\|year`  | `date_part('x', epoch_ms(time))`                 | Supported |
| List membership             | scalar on LIST field      | `list_contains(field, value)`                    | Supported |
| List any-of                 | list values on LIST field | `list_has_any(field, [values])`                  | Supported |
| List all-of                 | `all` on LIST field       | `list_has_all(field, [values])`                  | Supported |

### Deferred (post-MVP)

| Capability        | Sigma construct        | Reason                                                     |
| ----------------- | ---------------------- | ---------------------------------------------------------- |
| CIDR match        | `cidr`                 | Requires inet extension packaging decision                 |
| Base64 transforms | `base64\|base64offset` | Rarely needed for OCSF-normalized data                     |
| Field reference   | `fieldref`             | Rare in detection rules; typing policy needed              |
| Case-sensitive    | `cased`                | Lower priority; default case-insensitive covers most rules |

### Non-executable

| Capability            | Sigma construct      | Reason code                                        |
| --------------------- | -------------------- | -------------------------------------------------- |
| Correlation rules     | `correlation`        | `unsupported_rule_type`                            |
| Placeholder expansion | `expand`             | `placeholder_unresolved` (pipeline responsibility) |
| Unsupported regex     | PCRE-only constructs | `unsupported_regex`                                |

## Policy decisions

### P1: Case-insensitive string matching

**Decision:** Use `lower(field) = lower(value)` for equality comparisons.

**Rationale:** Sigma specifies case-insensitive matching as the default. While `ILIKE` is simpler
for pattern matching, `lower()` normalization provides consistent semantics across equality and
pattern operations and avoids any locale-dependent behavior.

**Reference:**
[Sigma Specification - Modifiers](https://github.com/SigmaHQ/sigma-specification/blob/main/specification/sigma-modifiers-appendix.md)

### P2: Wildcard and escape handling

**Decision:** Use `$` as the ESCAPE character for LIKE patterns. Escape `%`, `_`, and `$` in
user-provided values.

**Pattern:**

```sql
-- contains: 'test'
field ILIKE '%test%' ESCAPE '$'

-- contains: 'test%value' (literal percent)
field ILIKE '%test$%value%' ESCAPE '$'

-- startswith: 'C:\Windows'
field ILIKE 'C:\Windows%' ESCAPE '$'
```

**Escaping function:**

```python
def escape_like(value: str) -> str:
    return value.replace('$', '$$').replace('%', '$%').replace('_', '$_')
```

**Reference:** [DuckDB LIKE](https://duckdb.org/docs/sql/functions/pattern_matching#like)

### P3: Regex compatibility (RE2 subset)

**Decision:** Accept RE2-compatible patterns only. Reject patterns containing PCRE-only constructs
at compile time with `unsupported_regex` reason code.

**Supported RE2 constructs:**

- Character classes: `\d`, `\w`, `\s`, `[abc]`, `[^abc]`
- Anchors: `^`, `$`, `\b`
- Quantifiers: `*`, `+`, `?`, `{n}`, `{n,}`, `{n,m}`
- Groups: `(...)`, `(?:...)`, `(?P<name>...)`
- Alternation: `|`
- Escape sequences: `\.`, `\\`, etc.

**Rejected PCRE constructs (non-exhaustive):**

| Construct              | Example                | Reason               |
| ---------------------- | ---------------------- | -------------------- |
| Lookahead              | `(?=...)`, `(?!...)`   | Not supported in RE2 |
| Lookbehind             | `(?<=...)`, `(?<!...)` | Not supported in RE2 |
| Backreferences         | `\1`, `\k<name>`       | Not supported in RE2 |
| Possessive quantifiers | `*+`, `++`             | Not supported in RE2 |
| Atomic groups          | `(?>...)`              | Not supported in RE2 |
| Conditional patterns   | `(?(cond)yes\|no)`     | Not supported in RE2 |

**Implementation:** Use `re2` Python library to validate patterns at compile time. If pattern fails
RE2 compilation, emit `unsupported_regex` with the RE2 error message.

**Reference:** [RE2 Syntax](https://github.com/google/re2/wiki/Syntax)

### P4: Nested field access

**Decision:** Use direct dot notation for field access. Assume pipeline-provided field names are
schema-valid.

**Pattern:**

```sql
-- Simple nested access
SELECT metadata.uid, actor.user.name FROM events;

-- Existence check
WHERE actor.user.name IS NOT NULL
```

**Rationale:** Purple Axiom's OCSF schema contract guarantees Tier 0/1 fields are present in the
Parquet schema. The pipeline is responsible for mapping Sigma fields to valid OCSF paths. If a field
path is invalid, DuckDB will return a clear error at query time.

**Reference:**
[DuckDB Struct Access](https://duckdb.org/docs/sql/data_types/struct#creating-structs)

### P5: Timestamp handling

**Decision:** Use `epoch_ms(time)` to convert the INT64 millisecond timestamp to TIMESTAMP for date
part extraction.

**Pattern:**

```sql
-- Extract hour
WHERE date_part('hour', epoch_ms(time)) = 14

-- Extract day
WHERE date_part('day', epoch_ms(time)) = 15
```

**Rationale:** Purple Axiom stores `time` as INT64 milliseconds since epoch (UTC). DuckDB's
`epoch_ms()` function converts this to a TIMESTAMP suitable for `date_part()` extraction.

**Reference:**
[DuckDB Timestamp Functions](https://duckdb.org/docs/sql/functions/timestamp#epoch_msmilliseconds)

### P6: LIST field semantics

**Decision:** Scalar comparison against LIST field means "any element matches". Use
`list_contains()` for single values, `list_has_any()` for multiple values.

**Pattern:**

```sql
-- Single value: any IP equals '10.0.0.1'
WHERE list_contains(device.ips, '10.0.0.1')

-- Multiple values: any IP in list
WHERE list_has_any(device.ips, ['10.0.0.1', '192.168.1.1'])

-- All modifier: all candidate values present
WHERE list_has_all(device.ips, ['10.0.0.1', '192.168.1.1'])

-- Pattern on list elements (requires unnest)
WHERE EXISTS (
  SELECT 1 FROM unnest(device.ips) AS t(ip)
  WHERE ip ILIKE '10.%' ESCAPE '$'
)
```

**Reference:**
[DuckDB List Functions](https://duckdb.org/docs/sql/functions/list#list_containslist-element)

## Error taxonomy

When a rule cannot be compiled, the backend MUST return a structured error with the following codes.
Codes are prefixed `PA_SIGMA_` to disambiguate from upstream pySigma exceptions.

| Code                                    | Trigger                                 | Notes                                            |
| --------------------------------------- | --------------------------------------- | ------------------------------------------------ |
| `PA_SIGMA_E0001_UNSUPPORTED_RULE_TYPE`  | Correlation or other non-detection rule | Document as out of scope                         |
| `PA_SIGMA_E0002_UNSUPPORTED_MODIFIER`   | Modifier outside supported set          | Include modifier name and `gap_id` if applicable |
| `PA_SIGMA_E0003_UNSUPPORTED_REGEX`      | PCRE-only regex construct               | Include RE2 error message                        |
| `PA_SIGMA_E0004_TYPE_MISMATCH`          | Numeric op on non-numeric value         | Include field, operator, value                   |
| `PA_SIGMA_E0005_PLACEHOLDER_UNRESOLVED` | Unexpanded `%placeholder%`              | Pipeline contract failure                        |
| `PA_SIGMA_E0006_BACKEND_OPTION_INVALID` | Missing or invalid backend option       | Fail before compilation                          |

**Error payload shape:**

```json
{
  "code": "PA_SIGMA_E0003_UNSUPPORTED_REGEX",
  "message": "Regex pattern contains unsupported lookahead construct",
  "rule_id": "abc123",
  "field": "CommandLine",
  "pattern": "cmd.exe(?=.*-enc)",
  "re2_error": "invalid escape sequence: (?="
}
```

## Backend options

The backend accepts the following options via `__init__(**backend_options)`:

| Option          | Type | Default   | Description                        |
| --------------- | ---- | --------- | ---------------------------------- |
| `table_name`    | str  | `events`  | Table or view name for FROM clause |
| `output_format` | str  | `default` | SQL formatting style               |

## Determinism contract

The backend MUST emit SQL with stable, deterministic ordering:

1. List value expansions preserve input order
1. Boolean predicates use consistent parenthesization
1. String literals use single quotes with deterministic escaping
1. Identifiers use double quotes when required

Deterministic query results are the responsibility of the query (via `ORDER BY`) and the DuckDB
session settings defined in the
[Sigma-to-OCSF bridge specification](../spec/065_sigma_to_ocsf_bridge.md):

```sql
SET threads = 1;
SET TimeZone = 'UTC';
```

Cross-platform result stability is validated by R-02.

## Implementation checklist

- [ ] Implement `SigmaDuckDBBackend` class extending `sigma.backends.Backend`
- [ ] Implement compilation for each supported modifier
- [ ] Implement `escape_like()` value escaping
- [ ] Implement RE2 pattern validation (use `re2` library or `google-re2`)
- [ ] Implement LIST field detection and appropriate function selection
- [ ] Implement error taxonomy with structured payloads
- [ ] Register backend in `sigma.backends.duckdb` namespace
- [ ] Add unit tests for each compilation pattern
- [ ] Add negative tests for rejected constructs

## References

- [R-02 DuckDB conformance report](R-02_DuckDB_Conformance_Report_and_Harness_Requirements_v1_4_3.md)
- [Sigma-to-OCSF bridge specification](../spec/065_sigma_to_ocsf_bridge.md)
- [Sigma detection specification](../spec/060_detection_sigma.md)
- [Supported versions](../../SUPPORTED_VERSIONS.md)
