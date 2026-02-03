# Workflows

This page lists workflow-scoped diagram outputs generated from the YAML model.

| workflow_id | label | run sequence | stage flow | publish gate |
|---|---|---|---|---|
| adapter_binding_and_provenance | Adapter binding + provenance recording (adapter_binding_and_provenance) | [run_sequence](adapter_binding_and_provenance/run_sequence.md) |  |  |
| cache_provenance | Cross-run caching gate + cache provenance (cache_provenance) | [run_sequence](cache_provenance/run_sequence.md) |  |  |
| criteria_pack_resolution | Criteria pack resolution and snapshot (validation stage internals) (criteria_pack_resolution) | [run_sequence](criteria_pack_resolution/run_sequence.md) | [stage_flow](criteria_pack_resolution/stage_flow.md) | [publish_gate_contracts](criteria_pack_resolution/publish_gate_contracts.md) |
| detection_sigma_pipeline | Detection pipeline (Sigma) - deterministic load + bridge + detections (detection_sigma_pipeline) | [run_sequence](detection_sigma_pipeline/run_sequence.md) | [stage_flow](detection_sigma_pipeline/stage_flow.md) | [publish_gate_contracts](detection_sigma_pipeline/publish_gate_contracts.md) |
| event_identity_provenance | Event identity and provenance (deterministic join keys) (event_identity_provenance) | [run_sequence](event_identity_provenance/run_sequence.md) | [stage_flow](event_identity_provenance/stage_flow.md) | [publish_gate_contracts](event_identity_provenance/publish_gate_contracts.md) |
| exercise_run | Exercise run (happy path) (exercise_run) | [run_sequence](exercise_run/run_sequence.md) | [stage_flow](exercise_run/stage_flow.md) | [publish_gate_contracts](exercise_run/publish_gate_contracts.md) |
| provisioning | Provisioning and environment bring-up (provisioning) | [run_sequence](provisioning/run_sequence.md) | [stage_flow](provisioning/stage_flow.md) | [publish_gate_contracts](provisioning/publish_gate_contracts.md) |
| publish_gate | Publish gate (staging + contract validation + atomic publish) (publish_gate) | [run_sequence](publish_gate/run_sequence.md) |  |  |
| range_destroy | Destroy (range teardown) (range_destroy) | [run_sequence](range_destroy/run_sequence.md) |  |  |
| redaction_export_classification | Redaction + export classification (redact vs withhold/quarantine) (redaction_export_classification) | [run_sequence](redaction_export_classification/run_sequence.md) |  |  |
| reporting_regression_compare | Reporting regression compare (baseline vs candidate) (reporting_regression_compare) | [run_sequence](reporting_regression_compare/run_sequence.md) | [stage_flow](reporting_regression_compare/stage_flow.md) | [publish_gate_contracts](reporting_regression_compare/publish_gate_contracts.md) |
| run_export | Export (redaction-safe bundle) (run_export) | [run_sequence](run_export/run_sequence.md) |  |  |
| run_lifecycle_outcome_propagation | Run lifecycle and outcome propagation (state-machine oriented) (run_lifecycle_outcome_propagation) | [run_sequence](run_lifecycle_outcome_propagation/run_sequence.md) |  |  |
| run_replay | Replay (analysis-only) (run_replay) | [run_sequence](run_replay/run_sequence.md) | [stage_flow](run_replay/stage_flow.md) | [publish_gate_contracts](run_replay/publish_gate_contracts.md) |
| runner_action_lifecycle | Runner action lifecycle (prepare → execute → revert → teardown) (runner_action_lifecycle) | [run_sequence](runner_action_lifecycle/run_sequence.md) | [stage_flow](runner_action_lifecycle/stage_flow.md) | [publish_gate_contracts](runner_action_lifecycle/publish_gate_contracts.md) |
| scoring_reporting | Telemetry ingest to scoring and reporting (scoring_reporting) | [run_sequence](scoring_reporting/run_sequence.md) | [stage_flow](scoring_reporting/stage_flow.md) | [publish_gate_contracts](scoring_reporting/publish_gate_contracts.md) |
| teardown | Runner teardown and cleanup evidence (teardown) | [run_sequence](teardown/run_sequence.md) |  |  |
| telemetry_validation_canaries | Telemetry validation canaries (egress + checkpoint integrity) (telemetry_validation_canaries) | [run_sequence](telemetry_validation_canaries/run_sequence.md) | [stage_flow](telemetry_validation_canaries/stage_flow.md) | [publish_gate_contracts](telemetry_validation_canaries/publish_gate_contracts.md) |

Notes:
- Stage flow + publish gate diagrams are emitted only when the workflow targets stage entities.
