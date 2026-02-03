# Run sequence — Criteria pack resolution and snapshot (validation stage internals) (criteria_pack_resolution)

```mermaid
sequenceDiagram
  participant orchestrator_cli as "Orchestrator CLI"
  participant validation as "Validation Stage"
  participant criteria_pack_sources as "criteria_pack_sources"
  participant staging_area as "Stage Staging Area (runs/#lt;run_id#gt;/.staging/#lt;stage_id#gt;/)"
  participant run_bundle_store as "Run Bundle Store"
  orchestrator_cli->>validation: 1. invoke validation with criteria-pack selection config + required inputs
  validation->>criteria_pack_sources: 2. resolve criteria pack deterministically (paths[] order, SemVer, duplicate handling)
  validation->>criteria_pack_sources: 3. validate selected pack before snapshot (schemas + recomputed hashes + id/version match)
  validation->>staging_area: 4. snapshot manifest + criteria into `.staging/validation/criteria/` for run-scoped reproducibility
  validation->>staging_area: 5. evaluate criteria using the snapshot only; write staged `criteria/results.jsonl`
  validation->>run_bundle_store: 6. validate snapshot contracts + invariants, then publish by atomic rename to `criteria/`
  orchestrator_cli->>run_bundle_store: 7. record resolved criteria-pack pins + validation stage outcome (single-writer manifest policy)
```
