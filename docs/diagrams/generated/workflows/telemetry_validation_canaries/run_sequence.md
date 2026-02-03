# Run sequence — Telemetry validation canaries (egress + checkpoint integrity) (telemetry_validation_canaries)

```mermaid
sequenceDiagram
  participant orchestrator_cli as "Orchestrator CLI"
  participant telemetry as "Telemetry Stage"
  participant telemetry_validator as "telemetry_validator"
  participant egress_sentinel as "egress_sentinel"
  participant target_asset as "target_asset"
  participant run_bundle_store as "Run Bundle Store"
  participant telemetry_collector as "telemetry_collector"
  participant checkpoint_store as "checkpoint_store"
  orchestrator_cli->>telemetry: 1. run telemetry with required runtime canaries enabled for this run
  telemetry->>telemetry_validator: 2. initialize telemetry validation evidence (contract-backed) and canary plan
  telemetry_validator->>egress_sentinel: 3. (when outbound egress is denied) configure / select an egress-canary probe endpoint (fail_closed if missing: reason_code=egress_canary_missing)
  target_asset->>egress_sentinel: 4. attempt outbound egress probe (expected blocked under deny-by-default policy)
  telemetry_validator->>run_bundle_store: 5. record egress-canary outcome in telemetry_validation and emit substage outcome telemetry.network.egress_policy (fail_closed on unexpected reachability: reason_code=egress_violation)
  telemetry_validator->>run_bundle_store: 6. run agent liveness (dead-on-arrival) canary and emit substage outcome telemetry.agent.liveness (fail_closed if no heartbeat: reason_code=agent_heartbeat_missing)
  telemetry_validator->>run_bundle_store: 7. (optional; Windows Event Log) run raw-mode canary and emit substage outcome telemetry.windows_eventlog.raw_mode (fail_closed: reason_code=winlog_raw_missing#124;winlog_rendering_detected)
  telemetry_collector->>checkpoint_store: 8. persist receiver bookmarks via stable storage extension and compute checkpoint store fingerprint
  telemetry_validator->>run_bundle_store: 9. validate checkpoint store integrity and emit substage outcome telemetry.checkpointing.storage_integrity (fail_closed if unwritable/corrupt: reason_code=checkpoint_store_corrupt)
  telemetry_validator->>run_bundle_store: 10. detect checkpoint loss/reset and record deterministic NON_FATAL warning (reason_code=checkpoint_loss) with replay_start_mode + counters
  telemetry->>run_bundle_store: 11. on success, publish raw_parquet/** (and raw/** when enabled) plus logs/telemetry_validation.json
  orchestrator_cli->>run_bundle_store: 12. record telemetry stage outcome (and dotted substages) in manifest + health; on fail_closed, do not publish final-path telemetry outputs (egress_canary_missing#124;egress_violation#124;agent_heartbeat_missing#124;winlog_raw_missing#124;winlog_rendering_detected#124;checkpoint_store_corrupt)
```
