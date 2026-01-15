# Contracts navigator (docs/contracts only)

This file is a one-page map over the JSON Schema contracts under `docs/contracts/`.

## Entrypoints (open these first)

Sort key: recommended reading order (not lexicographic).

- `index.json` (machine-readable schema registry, if present)
- `docs/spec/025_data_contracts.md` (artifact semantics and invariants)
- `manifest.schema.json` (run manifest contract)
- `ocsf_event_envelope.schema.json` (normalized event envelope contract)

## Schema map

Rows are sorted lexicographically by filename.

| Schema file                             | Artifact / contract surface (high-level)                         |
| --------------------------------------- | ---------------------------------------------------------------- |
| `bridge_compiled_plan.schema.json`      | Schema for Sigma bridge compiled plan outputs                    |
| `bridge_coverage.schema.json`           | Schema for Sigma bridge routing/coverage summaries               |
| `bridge_mapping_pack.schema.json`       | Schema for a serialized bridge mapping pack snapshot             |
| `bridge_router_table.schema.json`       | Schema for Sigma bridge router table snapshots                   |
| `cleanup_verification.schema.json`      | Schema for cleanup verification results                          |
| `criteria_entry.schema.json`            | Schema for a single validation criteria entry                    |
| `criteria_pack_manifest.schema.json`    | Schema for criteria pack identity and metadata                   |
| `criteria_result.schema.json`           | Schema for criteria evaluation results                           |
| `detection_instance.schema.json`        | Schema for a single detection hit / finding                      |
| `duckdb_conformance_report.schema.json` | Schema for DuckDB conformance harness reports                    |
| `ground_truth.schema.json`              | Schema for ground-truth execution evidence                       |
| `manifest.schema.json`                  | Schema for the run manifest root object                          |
| `mapping_coverage.schema.json`          | Schema for mapping coverage summaries                            |
| `mapping_profile_input.schema.json`     | Schema for mapping profile input YAML files                       |
| `mapping_profile_snapshot.schema.json`  | Schema for mapping profile snapshots                             |
| `netflow_manifest.schema.json`          | Schema for NetFlow/flow artifacts (placeholder / optional)       |
| `ocsf_event_envelope.schema.json`       | Schema for normalized OCSF event envelope                        |
| `pcap_manifest.schema.json`             | Schema for pcap artifacts (placeholder / optional)               |
| `range_config.schema.json`              | Schema for range.yaml configuration inputs                       |
| `runner_executor_evidence.schema.json`  | Schema for runner/executor evidence outputs                      |
| `summary.schema.json`                   | Schema for run-level summary outputs                             |
| `telemetry_validation.schema.json`      | Schema for telemetry validation outputs                          |

## Update rule (required)

- Update this index (keep it one page).
- Do not include the agent, index or readme files.
- Ensure `docs/spec/025_data_contracts.md` remains the normative source for artifact semantics.
- Unless stated otherwise, lists and tables are sorted lexicographically by path.
