# Mappings navigator (docs/mappings only)

This file exists to keep agent working sets small. It is a one-page map over the mapping reference
docs in `docs/mappings/` so agents do not need to load every document to find the authoritative
section.

## Entrypoints (open these first)

Rows are sorted lexicographically by filename.

- `coverage_matrix.md` (field coverage expectations by source)
- `ocsf_mapping_profile_authoring_guide.md` (deterministic mapping pack authoring rules)

## File map (covers all docs/mappings files)

| Mapping doc file                          | Primary purpose (authoritative for)                                                                   |
| ----------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `coverage_matrix.md`                      | Required vs optional vs N/A field coverage expectations per `source_type` and event family            |
| `ocsf_mapping_profile_authoring_guide.md` | Deterministic authoring rules for machine-executable mapping packs (YAML), structure, and constraints |
| `windows-security_to_ocsf_1.7.0.md`       | Windows Security (Event Log: Security) mapping rules to OCSF 1.7.0; routing intent and field mapping  |
| `windows-sysmon_to_ocsf_1.7.0.md`         | Windows Sysmon mapping rules to OCSF 1.7.0; event-ID-based routing intent and field mapping           |
| `osquery_to_ocsf_1.7.0.md`                | osquery scheduled-results mapping rules to OCSF 1.7.0; `query_name` routing intent and field mapping  |
| `linux-auditd_to_ocsf_1.7.0.md`           | Linux auditd mapping rules to OCSF 1.7.0; audit record routing and field mapping                      |

## Common tasks (fast paths)

| Need                                                                 | Read first                                | Then (if needed)                                                                                                    |
| -------------------------------------------------------------------- | ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| “What fields are required for mapping completeness by source?”       | `coverage_matrix.md`                      | (follow the per-class Tier 2 tables; then add fixtures to satisfy required `R[...]` cells)                          |
| “How do I author a mapping pack that is deterministic and testable?” | `ocsf_mapping_profile_authoring_guide.md` | `docs/spec/100_test_strategy_ci.md` (mapping pack conformance gates), `docs/spec/050_normalization_ocsf.md`         |
| “Where is the Windows Security mapping spec?”                        | `windows-security_to_ocsf_1.7.0.md`       | `docs/spec/050_normalization_ocsf.md` (envelope requirements), `docs/adr/ADR-0002-event-identity-and-provenance.md` |
| “Where is the Sysmon mapping spec?”                                  | `windows-sysmon_to_ocsf_1.7.0.md`         | `coverage_matrix.md` (required pivots for Sysmon), `docs/adr/ADR-0002-event-identity-and-provenance.md`             |
| “Where is the osquery mapping spec?”                                 | `osquery_to_ocsf_1.7.0.md`                | `docs/spec/042_osquery_integration.md` (raw shape + routing constraints), `coverage_matrix.md`                      |
| “I need to add a new source_type mapping (new telemetry source)”     | `ocsf_mapping_profile_authoring_guide.md` | `coverage_matrix.md` (add a row/expectations), then add a new per-source mapping doc under `docs/mappings/`         |
| “What does CI enforce for mapping packs and mapping outputs?”        | `docs/spec/100_test_strategy_ci.md`       | `coverage_matrix.md` (fixture minimums), `docs/spec/025_data_contracts.md` (mapping snapshot artifacts)             |


## Update rule (required)

- Update this index to point to the authoritative mapping doc (keep it one page).
- Do not include the agent, index or readme files.
- Prefer pointers to existing sections over duplicated prose.
- Unless stated otherwise, lists and tables are sorted lexicographically by path.

