# Run sequence — Reporting regression compare (baseline vs candidate) (reporting_regression_compare)

```mermaid
sequenceDiagram
  participant orchestrator_cli as "Orchestrator CLI"
  participant reporting as "Reporting Stage"
  participant run_bundle_store as "Run Bundle Store"
  orchestrator_cli->>reporting: 1. invoke regression compare substage as part of reporting (only when reporting.regression.enabled=true)
  reporting->>run_bundle_store: 2. decision: baseline reference present + contract-valid? (inputs/baseline_run_ref.json). If missing/unreadable =#gt; warn_and_skip baseline_missing + indeterminate regression section
  reporting->>run_bundle_store: 3. baseline load: resolve baseline manifest via pointer form; if snapshot form present, verify sha256 integrity. Snapshot sha mismatch =#gt; fail_closed baseline_incompatible
  reporting->>reporting: 4. compatibility gate: compute canonical comparability checks over manifest.versions.* pins + policy (allow_mapping_pack_version_drift). Not comparable =#gt; warn_and_skip baseline_incompatible + no deltas
  reporting->>reporting: 5. delta computation: compute regression deltas (candidate - baseline) for comparable metric surface using deterministic rounding and ordering
  reporting->>reporting: 6. threshold evaluation: compare deltas to regression thresholds; set regression_alerted + alert_reasons; update report/thresholds.json.status_recommendation per alert_status_recommendation policy
  reporting->>run_bundle_store: 7. emit artifacts: write report/report.json regression block + report/thresholds.json; include required evidence_refs; keep indeterminate form on warn_and_skip / fail_closed paths
  orchestrator_cli->>run_bundle_store: 8. outcome mapping: record reporting.regression_compare substage outcome in logs/health.json (ok vs warn_and_skip vs fail_closed) with stable reason_code + deterministic precedence
```
