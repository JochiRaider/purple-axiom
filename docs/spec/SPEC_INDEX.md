# Spec navigator (docs/spec only)

This file exists to keep agent working sets small. It is a one-page map over the spec markdown files
in `docs/spec/` so agents do not need to load every document to find the authoritative section.

## Entrypoints (open these first)

- `000_charter.md`
- `010_scope.md`
- `020_architecture.md`
- `025_data_contracts.md`
- `030_scenarios.md`
- `040_telemetry_pipeline.md`
- `050_normalization_ocsf.md`
- `060_detection_sigma.md`
- `070_scoring_metrics.md`
- `080_reporting.md`
- `120_config_reference.md`

## File map (covers all spec files)

| Spec file                                     | Primary purpose (authoritative for)                             |
| --------------------------------------------- | --------------------------------------------------------------- |
| `000_charter.md`                              | Mission, principles, and project charter constraints            |
| `010_scope.md`                                | In-scope / out-of-scope boundaries and definitions              |
| `015_lab_providers.md`                        | Lab provider model and environment assumptions                  |
| `020_architecture.md`                         | System architecture and stage boundaries                        |
| `025_data_contracts.md`                       | Run bundle artifacts and cross-artifact invariants              |
| `030_scenarios.md`                            | Scenario model, action identity expectations, and run semantics |
| `031_plan_execution_model.md`                 | Plan graph model and matrix plan semantics (reserved v0.2)      |
| `032_atomic_red_team_executor_integration.md` | Atomic Red Team executor integration contract and artifacts     |
| `035_validation_criteria.md`                  | Criteria evaluation semantics and cleanup verification model    |
| `040_telemetry_pipeline.md`                   | Telemetry collection invariants and capture requirements        |
| `042_osquery_integration.md`                  | Osquery collection path and normalization expectations          |
| `044_unix_log_ingestion.md`                   | Unix log ingestion paths, dedupe policy, and audit correlation  |
| `045_storage_formats.md`                      | Storage formats and schema evolution expectations               |
| `050_normalization_ocsf.md`                   | Normalization rules into OCSF and mapping approach              |
| `055_ocsf_field_tiers.md`                     | OCSF field tiers and coverage expectations                      |
| `060_detection_sigma.md`                      | Detection representation and Sigma-specific semantics           |
| `065_sigma_to_ocsf_bridge.md`                 | Sigma→OCSF bridge behavior and outputs                          |
| `070_scoring_metrics.md`                      | Scoring model, coverage metrics, and gating language            |
| `080_reporting.md`                            | Reporting outputs, summaries, and operator-facing artifacts     |
| `090_security_safety.md`                      | Security and safety requirements (spec-level)                   |
| `100_test_strategy_ci.md`                     | Test strategy, fixtures, CI gates, and conformance expectations |
| `110_operability.md`                          | Operability requirements and run-time expectations              |
| `120_config_reference.md`                     | Configuration surface area and defaults                         |

## Common tasks (fast paths)

| Need                                               | Read first                                    | Then (if needed)                                                                    |
| -------------------------------------------------- | --------------------------------------------- | ----------------------------------------------------------------------------------- |
| “What is Purple Axiom trying to do?”               | `000_charter.md`                              | `010_scope.md`                                                                      |
| “Is X in scope?”                                   | `010_scope.md`                                | `000_charter.md`                                                                    |
| “How do stages fit together?”                      | `020_architecture.md`                         | `040_telemetry_pipeline.md`, `050_normalization_ocsf.md`, `080_reporting.md`        |
| “What artifacts exist in a run bundle?”            | `025_data_contracts.md`                       | `045_storage_formats.md`, `080_reporting.md`                                        |
| “How are scenarios defined and compared?”          | `030_scenarios.md`                            | `035_validation_criteria.md`, `070_scoring_metrics.md`                              |
| “How does the Atomic Red Team executor integrate?” | `032_atomic_red_team_executor_integration.md` | `025_data_contracts.md`, `030_scenarios.md`, `035_validation_criteria.md`           |
| “What does cleanup verification mean?”             | `035_validation_criteria.md`                  | `030_scenarios.md`                                                                  |
| “What telemetry must be captured?”                 | `040_telemetry_pipeline.md`                   | `042_osquery_integration.md`, `044_unix_log_ingestion.md`                           |
| “How is osquery ingested?”                         | `042_osquery_integration.md`                  | `040_telemetry_pipeline.md`, `050_normalization_ocsf.md`                            |
| “How are Unix logs ingested?”                      | `044_unix_log_ingestion.md`                   | `040_telemetry_pipeline.md`, `050_normalization_ocsf.md`                            |
| “What storage formats are required?”               | `045_storage_formats.md`                      | `025_data_contracts.md`                                                             |
| “How do we normalize into OCSF?”                   | `050_normalization_ocsf.md`                   | `055_ocsf_field_tiers.md`, `docs/mappings/MAPPINGS_DOC_INDEX.md`                    |
| “What coverage is required for OCSF fields?”       | `055_ocsf_field_tiers.md`                     | `docs/mappings/coverage_matrix.md`                                                  |
| “How are detections represented and evaluated?”    | `060_detection_sigma.md`                      | `065_sigma_to_ocsf_bridge.md`, `070_scoring_metrics.md`                             |
| “How does the Sigma bridge behave?”                | `065_sigma_to_ocsf_bridge.md`                 | `060_detection_sigma.md`, `docs/research/R-03_DuckDB_Backend_Plugin_for_pySigma.md` |
| “How are scores computed and gated?”               | `070_scoring_metrics.md`                      | `080_reporting.md`                                                                  |
| “What reports are produced?”                       | `080_reporting.md`                            | `025_data_contracts.md`, `070_scoring_metrics.md`                                   |
| “What are security/safety requirements?”           | `090_security_safety.md`                      | `docs/adr/ADR-0003-redaction-policy.md`                                             |
| “What must CI enforce?”                            | `100_test_strategy_ci.md`                     | `docs/research/RESEARCH_INDEX.md` (conformance harnesses)                           |
| “How should operators run/observe this?”           | `110_operability.md`                          | `080_reporting.md`, `100_test_strategy_ci.md`                                       |
| “What config keys exist and what are defaults?”    | `120_config_reference.md`                     | `docs/contracts/CONTRACTS_INDEX.md` (schema validation surface)                     |
| “How do matrix/multi-target plans work?”           | `031_plan_execution_model.md`                 | `docs/adr/ADR-0006-plan-execution-model.md`                                         |

## Update rule (required)

- Update this index and keep it one page.
- Do not include the agent, index or readme files.
- Prefer pointers to authoritative sections over duplicated prose.
- Unless stated otherwise, lists and tables are sorted lexicographically by path.
- The “Entrypoints” section above is intentionally sorted by recommended read order.
