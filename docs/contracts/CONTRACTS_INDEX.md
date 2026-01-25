# Contracts navigator (docs/contracts only)

This file is a one-page map over the JSON Schema contracts under `docs/contracts/`.

## Entrypoints (open these first)

Sort key: recommended reading order (not lexicographic).

- `docs/contracts/contract_registry.json` (machine-readable schema registry, if present)
- `docs/spec/025_data_contracts.md` (artifact semantics and invariants)
- `docs/contracts/manifest.schema.json` (run manifest contract)
- `docs/contracts/ocsf_event_envelope.schema.json` (normalized event envelope contract)

## Schema map

Rows are sorted lexicographically by filename, all in the `docs/contracts/` diectory.

| Schema file                               | Artifact / contract surface (high-level)                       |
| ----------------------------------------- | -------------------------------------------------------------- |
| `audit_event.schema.json`                 | Schema for UI/control plane audit events                       |
| `bridge_compiled_plan.schema.json`        | Schema for Sigma bridge compiled plan outputs                  |
| `bridge_coverage.schema.json`             | Schema for Sigma bridge routing/coverage summaries             |
| `bridge_mapping_pack.schema.json`         | Schema for a serialized bridge mapping pack snapshot           |
| `bridge_router_table.schema.json`         | Schema for Sigma bridge router table snapshots                 |
| `cache_provenance.schema.json`            | Schema for cache provenance and usage evidence                 |
| `cleanup_verification.schema.json`        | Schema for cleanup verification results                        |
| `contract_registry.json`                  | Contract registry mapping contract ids to schemas and bindings |
| `contract_registry.schema.json`           | Schema for the contract registry file                          |
| `counters.schema.json`                    | Schema for run-level counters and gauges snapshots             |
| `criteria_entry.schema.json`              | Schema for a single validation criteria entry                  |
| `criteria_pack_manifest.schema.json`      | Schema for criteria pack identity and metadata                 |
| `criteria_result.schema.json`             | Schema for criteria evaluation results                         |
| `defense_outcomes.schema.json`            | Schema for defense outcomes (VECTR-style)                      |
| `detection_instance.schema.json`          | Schema for a single detection hit / finding                    |
| `duckdb_conformance_report.schema.json`   | Schema for DuckDB conformance harness reports                  |
| `ground_truth.schema.json`                | Schema for ground-truth execution evidence                     |
| `lab_inventory_snapshot.schema.json`      | Schema for deterministic lab inventory snapshots               |
| `manifest.schema.json`                    | Schema for the run manifest root object                        |
| `mapping_coverage.schema.json`            | Schema for mapping coverage summaries                          |
| `mapping_profile_input.schema.json`       | Schema for mapping profile input YAML files                    |
| `mapping_profile_snapshot.schema.json`    | Schema for mapping profile snapshots                           |
| `netflow_manifest.schema.json`            | Schema for NetFlow/flow artifacts (placeholder / optional)     |
| `ocsf_event_envelope.schema.json`         | Schema for normalized OCSF event envelope                      |
| `pcap_manifest.schema.json`               | Schema for pcap artifacts (placeholder / optional)             |
| `principal_context.schema.json`           | Schema for runner principal context evidence                   |
| `range_config.schema.json`                | Schema for range.yaml configuration inputs                     |
| `redaction_profile_set.schema.json`       | Schema for redaction profile sets (export/share)               |
| `report.schema.json`                      | Schema for consolidated run report outputs                     |
| `requirements_evaluation.schema.json`     | Schema for per-action requirements evaluation results          |
| `resolved_inputs_redacted.schema.json`    | Schema for redaction-safe resolved inputs evidence             |
| `runner_executor_evidence.schema.json`    | Schema for runner/executor evidence outputs                    |
| `side_effect_ledger.schema.json`          | Schema for per-action side-effect ledgers                      |
| `state_reconciliation_report.schema.json` | Schema for per-action state reconciliation reports             |
| `summary.schema.json`                     | Schema for run-level summary outputs                           |
| `telemetry_baseline_profile.schema.json`  | Schema for telemetry baseline profiles                         |
| `telemetry_validation.schema.json`        | Schema for telemetry validation outputs                        |
| `threat_intel_indicator.schema.json`      | Schema for normalized threat-intel indicator records           |
| `threat_intel_pack_manifest.schema.json`  | Schema for threat-intel pack manifest snapshots                |

## Update rule (required)

- Update this index (keep it one page).
- Do not include the agent, index or readme files.
- Ensure `docs/spec/025_data_contracts.md` remains the normative source for artifact semantics.
- Unless stated otherwise, lists and tables are sorted lexicographically by path.
