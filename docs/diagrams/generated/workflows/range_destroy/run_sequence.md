# Run sequence — Destroy (range teardown) (range_destroy)

```mermaid
sequenceDiagram
  participant operator as "Operator"
  participant orchestrator_cli as "Orchestrator CLI"
  participant run_lock as "run_lock"
  participant destroy_policy_gate as "destroy_policy_gate"
  participant operability_log as "operability_log"
  participant run_local_resources as "run_local_resources"
  participant lab_provider_adapter as "lab_provider_adapter"
  operator->>orchestrator_cli: 1. invoke destroy for run_id (clean up run-local resources; lab/provider teardown requires explicit enablement)
  orchestrator_cli->>run_lock: 2. acquire run lock (runs/.locks/#lt;run_id#gt;.lock) before mutating any run-bundle artifacts (including operability logs)
  orchestrator_cli->>destroy_policy_gate: 3. decision: provider mutation enabled? (explicit enablement required; default is no provider mutation)
  orchestrator_cli->>operability_log: 4. record deterministic operability log entry (destroy invoked; provider_mutation_enabled; planned cleanup scope)
  orchestrator_cli->>run_local_resources: 5. clean up run-local resources
  orchestrator_cli->>lab_provider_adapter: 6. if provider_mutation_enabled, tear down lab resources (provider mutation); otherwise skip
  orchestrator_cli->>operability_log: 7. record deterministic operability log entry (destroy completed; provider teardown attempted/skipped; outcomes)
  orchestrator_cli->>run_lock: 8. release run lock
```
