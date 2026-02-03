# Run sequence — Redaction + export classification (redact vs withhold/quarantine) (redaction_export_classification)

```mermaid
sequenceDiagram
  participant orchestrator_cli as "Orchestrator CLI"
  participant run_bundle_store as "Run Bundle Store"
  participant stage_wrapper as "stage_wrapper"
  participant staging_area as "Stage Staging Area (runs/#lt;run_id#gt;/.staging/#lt;stage_id#gt;/)"
  participant audit_redactor as "Audit Redaction Pipeline"
  participant publish_gate as "publish_gate"
  participant operator as "Operator"
  participant export_packager as "export_packager"
  participant signing as "Signing Stage"
  orchestrator_cli->>run_bundle_store: 1. snapshot effective redaction policy into the run bundle
  stage_wrapper->>staging_area: 2. write candidate outputs to .staging (may contain sensitive data prior to handling decision)
  orchestrator_cli->>orchestrator_cli: 3. decide per-artifact handling {redact #124; withhold #124; quarantine_only} based on redaction.enabled, disabled_behavior, and determinism constraints
  orchestrator_cli->>audit_redactor: 4. if handling=redact, apply redaction pipeline to staged artifacts and write redacted versions back to staging
  orchestrator_cli->>run_bundle_store: 5. if handling=withhold or quarantine_only, publish a deterministic placeholder at the standard contracted path and (if permitted) place unredacted originals under runs/#lt;run_id#gt;/#lt;unredacted_dir#gt;/
  orchestrator_cli->>run_bundle_store: 6. record evidence_refs.handling (present/withheld/quarantined) in manifest/report metadata for any affected artifacts
  orchestrator_cli->>publish_gate: 7. validate contracted outputs and atomically publish from .staging to final run-bundle paths
  operator->>orchestrator_cli: 8. invoke export; select default export set (Tier 0 deterministic evidence) and exclude .staging, volatile diagnostics, and unredacted/quarantine by default
  orchestrator_cli->>audit_redactor: 9. run operator-facing export through the redaction pipeline (fail closed if not redaction-safe)
  orchestrator_cli->>export_packager: 10. write export bundle outside the run bundle; include quarantine/unredacted only via explicit operator request + policy permission
  signing->>run_bundle_store: 11. when signing is enabled, exclude unredacted/quarantine directory from checksumming scope but include placeholder artifacts
```
