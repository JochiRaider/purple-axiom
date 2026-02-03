# Run sequence — Replay (analysis-only) (run_replay)

```mermaid
sequenceDiagram
  participant operator as "Operator"
  participant orchestrator_cli as "Orchestrator CLI"
  participant run_lock as "run_lock"
  participant run_bundle as "run_bundle"
  participant normalization as "Normalization Stage"
  participant validation as "Validation Stage"
  participant detection as "Detection Stage"
  participant scoring as "Scoring Stage"
  participant reporting as "Reporting Stage"
  participant signing as "Signing Stage"
  operator->>orchestrator_cli: 1. invoke replay to rerun downstream analysis stages (analysis-only; no runner/telemetry)
  orchestrator_cli->>run_lock: 2. acquire exclusive run lock for target run bundle (single-writer invariant)
  orchestrator_cli->>run_bundle: 3. materialize/verify pinned operator inputs under inputs/ (read-only; MUST NOT rewrite)
  orchestrator_cli->>run_bundle: 4. deterministically reconcile run state; enforce replay constraints (analysis-only); (re)run stages via publish gate and record stage outcomes
  orchestrator_cli->>normalization: 5. invoke normalization (replay)
  orchestrator_cli->>validation: 6. invoke validation (replay)
  orchestrator_cli->>detection: 7. invoke detection (replay)
  orchestrator_cli->>scoring: 8. invoke scoring (replay)
  orchestrator_cli->>reporting: 9. invoke reporting (replay)
  orchestrator_cli->>signing: 10. (optional) invoke signing (replay)
  orchestrator_cli->>run_lock: 11. release run lock
```
