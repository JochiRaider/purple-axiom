# Run sequence — Runner action lifecycle (prepare → execute → revert → teardown) (runner_action_lifecycle)

```mermaid
sequenceDiagram
  participant orchestrator_cli as "Orchestrator CLI"
  participant runner as "Runner Stage"
  participant run_bundle_store as "Run Bundle Store"
  participant target_asset as "target_asset"
  orchestrator_cli->>runner: 1. select target asset and action template; allocate action_id/action_key for this run
  runner->>run_bundle_store: 2. materialize per-action evidence scaffolding and structured execution record
  runner->>target_asset: 3. prepare (evaluate prerequisites and satisfy them when applicable)
  runner->>run_bundle_store: 4. record prepare phase outcome in ground_truth.jsonl (including requirements evaluation attachment when present)
  runner->>target_asset: 5. execute (invoke technique payload)
  runner->>run_bundle_store: 6. record execute phase outcome in ground_truth.jsonl and attach executor/stdout/stderr evidence refs
  runner->>target_asset: 7. revert (invoke cleanup command when plan.cleanup=true and execute was attempted)
  runner->>run_bundle_store: 8. record revert phase outcome in ground_truth.jsonl and attach cleanup transcript evidence refs
  runner->>target_asset: 9. teardown (remove per-action prerequisites when safe; run verification probes when enabled)
  runner->>run_bundle_store: 10. write per-action cleanup verification evidence (when enabled)
  runner->>run_bundle_store: 11. write per-action state reconciliation report (when enabled)
  runner->>run_bundle_store: 12. record teardown phase outcome in ground_truth.jsonl and attach verification/reconciliation evidence refs (when present)
  orchestrator_cli->>run_bundle_store: 13. record runner stage outcome in manifest and health log
```
