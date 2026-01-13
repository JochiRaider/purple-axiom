# Fixture navigator (tests/fixtures only)

This file exists to keep agent working sets small. It is a one-page map over the test data directories
in `tests/fixtures/` so developers and agents do not need to traverse the entire tree to find test data.

## Fixture Pack Map (by directory)

| Fixture Pack (Directory) | Primary Purpose (Contains)                                                      |
| ------------------------ | ------------------------------------------------------------------------------- |
| `bridge/`                | **Sigma Bridge**: Compilation rules, router tables, and backend telemetry matches |
| `criteria/`              | **Validation Criteria**: Drift detection scenarios and criteria pack manifests    |
| `duckDB_pySig/`          | **DuckDB/PySigma**: SQL schemas and gap analysis validation data                |
| `event_id/`              | **Event Identity**: Raw logs (Linux/Windows) for testing ID generation          |
| `hash_basis/`            | **Hashing**: Inputs and expected hashes for action keys and command material    |
| `jcs/`                   | **Canonicalization**: JSON Canonicalization Scheme (JCS) test vectors (RFC 8785)|
| `lab/`                   | **Lab Provider**: Mock inventory sources and snapshots                          |
| `normalized/`            | **OCSF Normalization**: Golden OCSF events and coverage assertions              |
| `raw/`                   | **Raw Telemetry**: Raw event samples (NDJSON/JSON) matching the Normalized set  |
| `redaction/`             | **Redaction**: PII/Sensitive data test cases and policy definitions             |
| `reliability/`           | **Reliability**: Chaos engineering scenarios (checkpoint loss, crash rotation)  |
| `runner/`                | **Atomic Runner**: Full golden artifacts for Atomic Red Team execution          |

## Common tasks (fast paths)

| Need                                             | Look here first                                             |
| ------------------------------------------------ | ----------------------------------------------------------- |
| “I need valid OCSF JSON events to validate”      | `normalized/ocsf/{version}/{product}/`                      |
| “I need raw logs to replay into the pipeline”    | `raw/{product}/`                                            |
| “I need to test Sigma rule compilation”          | `bridge/rules/`                                             |
| “I need to verify Event ID generation logic”     | `event_id/v1/`                                              |
| “I need to check how atomic tests are recorded”  | `runner/atomic/golden/`                                     |
| “I need standard JSON canonicalization vectors”  | `jcs/`                                                      |

## Update rule

When you add a new fixture directory:
- Add it to the **Fixture Pack Map** table above with a brief description of its contents.