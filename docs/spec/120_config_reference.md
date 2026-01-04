# Configuration Reference

## Top-level keys (seed)
- lab:
  - assets (hostnames, roles, OS)
  - network ranges
- runner:
  - type: caldera | atomic | custom
  - endpoint, credentials (refs only)
- telemetry:
  - otel_collector_config_path
  - channels/sources
- normalization:
  - ocsf_version
  - mapping_profiles
- detection:
  - sigma_rule_paths
  - evaluation_mode: streaming|batch
- reporting:
  - output_dir
  - emit_html: true|false

## Example range.yaml
```yaml
lab:
  assets:
    - asset_id: win11-test-01
      os: windows
      role: endpoint
runner:
  type: atomic
  atomic:
    technique_allowlist: ["T1059.001"]
telemetry:
  otel:
    config_path: configs/otel-collector.yaml
normalization:
  ocsf_version: "1.x.x"
detection:
  sigma:
    rule_paths: ["rules/sigma"]
reporting:
  output_dir: "runs/"
  emit_html: true

```yaml
(OTel config structure reference :contentReference[oaicite:13]{index=13}.)

---

## docs/spec/appendix_glossary.md

```md
# Glossary

- ATT&CK: MITRE ATT&CK technique taxonomy
- Scenario: a planned set of actions/tests
- Run: a single execution instance of a scenario
- Ground truth: authoritative record of actions executed
- OCSF: normalized security event schema
- Sigma: portable detection rule format
- Pipeline gap taxonomy:
  - missing telemetry
  - mapping gap
  - rule logic gap
```