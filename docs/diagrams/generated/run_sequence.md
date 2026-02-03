# Canonical run sequence (v0.1)

```mermaid
sequenceDiagram
  participant operator as "Operator"
  participant orchestrator_cli as "Orchestrator CLI"
  participant run_lock_dir as "Run lock directory (runs/.locks/)"
  participant run_bundle_store as "Run Bundle Store"
  participant lab_provider as "Lab Provider Stage"
  participant runner as "Runner Stage"
  participant telemetry as "Telemetry Stage"
  participant normalization as "Normalization Stage"
  participant validation as "Validation Stage"
  participant detection as "Detection Stage"
  participant scoring as "Scoring Stage"
  participant reporting as "Reporting Stage"
  participant signing as "Signing Stage"
  operator->>orchestrator_cli: 1. invoke simulate (full pipeline)
  orchestrator_cli->>run_lock_dir: 2. acquire exclusive run lock
  orchestrator_cli->>run_bundle_store: 3. write manifest skeleton and pin inputs into runs/#lt;run_id#gt;/inputs/
  orchestrator_cli->>lab_provider: 4. run lab_provider and record stage outcome
  orchestrator_cli->>runner: 5. (optional) run environment configuration and record `runner.environment_config` substage outcome
  orchestrator_cli->>runner: 6. run runner to execute scenario actions
  orchestrator_cli->>telemetry: 7. run telemetry post-run harvest/validation/publish to materialize raw_parquet/** (and raw/** when enabled)
  orchestrator_cli->>normalization: 8. normalize raw_parquet/** into normalized/** and publish mapping coverage + profile snapshot
  orchestrator_cli->>validation: 9. evaluate criteria and publish criteria/manifest.json + criteria/criteria.jsonl + criteria/results.jsonl
  orchestrator_cli->>detection: 10. evaluate Sigma and publish detections/detections.jsonl
  orchestrator_cli->>scoring: 11. compute scoring/summary.json
  orchestrator_cli->>reporting: 12. generate report/report.json, report/thresholds.json, and report/run_timeline.md
  orchestrator_cli->>signing: 13. (optional) sign run artifacts and publish security/**
```
