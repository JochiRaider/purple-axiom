# Run sequence — Publish gate (staging + contract validation + atomic publish) (publish_gate)

```mermaid
sequenceDiagram
  participant orchestrator_cli as "Orchestrator CLI"
  participant staging_area as "Stage Staging Area (runs/#lt;run_id#gt;/.staging/#lt;stage_id#gt;/)"
  participant run_bundle_store as "Run Bundle Store"
  orchestrator_cli->>staging_area: 1. write stage outputs under runs/#lt;run_id#gt;/.staging/#lt;stage_id#gt;/ prior to publish
  orchestrator_cli->>run_bundle_store: 2. validate required schema contracts before publish (on failure: emit contract validation report, do not publish final paths; see teardown.yaml for .staging cleanup)
  orchestrator_cli->>run_bundle_store: 3. if validation succeeds, publish via atomic rename into final run-bundle paths
  orchestrator_cli->>staging_area: 4. after successful publish, cleanup `runs/#lt;run_id#gt;/.staging/#lt;stage_id#gt;/` (delete or leave empty); teardown ensures `runs/#lt;run_id#gt;/.staging/**` is absent on terminal run
```
