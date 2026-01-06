<!-- README.md -->
# Purple Axiom

**Ground-truth detection engineering through continuous adversary emulation**

Purple Axiom is a local-first cyber range that continuously runs safe adversary-emulation scenarios, collects telemetry from lab assets, normalizes events into **OCSF**, evaluates detections using **Sigma**, and produces **reproducible run bundles** (HTML + JSON artifacts) suitable for regression testing and trend tracking. 

## Why Purple Axiom

Most detection engineering workflows still look like: run a test, eyeball logs, and call it “good enough.”
Purple Axiom turns that into a repeatable, defensible loop:

- **Ground truth**: what ran, when, where, and what should have been observable
- **Telemetry**: what was actually collected
- **Normalization**: how raw events mapped to a portable schema (OCSF)
- **Detections**: what rules fired (Sigma)
- **Scoring**: coverage, latency, and gap classification
- **Reporting**: a run bundle you can diff, gate in CI, and trend over time 

## Core philosophy

Treat detections as the theorems you are trying to prove, and adversary emulation as the axioms (ground truth) you build upon.

This project prioritizes **measurable outcomes tied to specific techniques and behaviors**, rather than opaque “security scores.” 

## Scope and safety

Purple Axiom is designed for **isolated lab environments** and emphasizes detectability validation, not stealth, persistence, or destructive outcomes.

**Explicit non-goals (initially):**
- Exploit development, weaponization, or destructive testing
- Production deployment guidance for hostile environments
- “Full SIEM replacement” (external ingestion is optional) 

**Hard safety constraints (MVP):**
- Isolated lab only
- No destructive payloads, no persistence, no lateral movement
- Cleanup is required, recorded, and surfaced in reporting
- No secrets written to long-term artifacts (redaction and hashing where needed) 

## Architecture

```

┌─────────────────────────┐
│ Scenario Runner         │  ← Caldera operations and/or Atomic test plans
└────────────┬────────────┘
│ ground-truth timeline (append-only)
▼
┌─────────────────────────┐
│ Telemetry Collectors    │  ← Windows Event Log, osquery, optional sensors
└────────────┬────────────┘
│ raw events
▼
┌─────────────────────────┐
│ OTel Collector Pipeline │  ← ingest, enrich (run_id/scenario_id), export
└────────────┬────────────┘
│ collected telemetry
▼
┌─────────────────────────┐
│ Normalizer → OCSF       │  ← canonical event model + provenance + event_id
└────────────┬────────────┘
│ normalized event store
▼
┌─────────────────────────┐
│ Detection Engine (Sigma)│  ← compile rules → evaluate (streaming or batch)
└────────────┬────────────┘
│ detections
▼
┌─────────────────────────┐
│ Scoring + Reporting     │  ← coverage, latency, gaps → HTML + JSON bundle
└─────────────────────────┘

```

## Key concepts

- **Scenario**: a planned set of actions/tests (Caldera operation or Atomic plan)
- **Run**: a single execution instance with a unique `run_id` (UUID)
- **Ground truth**: append-only timeline of what executed, with expected telemetry hints
- **Normalized events**: OCSF events with required provenance fields and stable `event_id`
- **Detection instance**: a Sigma rule hit referencing matched `event_id` values
- **Scoring**: technique coverage, latency, and pipeline gap classification 

## Run bundles (artifacts)

Each run produces a **run bundle** at `runs/<run_id>/`. The **manifest** is the authoritative index of what exists and which versions/config hashes were used.

```text
runs/<run_id>/
manifest.json
ground_truth.jsonl
raw/
normalized/
ocsf_events.jsonl        (or Parquet in later phases)
mapping_coverage.json    (optional)
detections/
detections.jsonl
scoring/
summary.json
report/
report.html
summary.json
logs/                    (volatile; not long-term storage)

```

### Determinism and provenance (what makes outputs “diffable”)

- `run_id` is immutable per execution
- `scenario_id` and `scenario_version` identify what ran
- OCSF events include required provenance fields on every record
- `metadata.event_id` is deterministic when source event + normalization inputs match
- JSONL outputs are written in deterministic order for diffability 

For the normative configuration keys and an example `range.yaml`, see `docs/spec/120_config_reference.md`. 

## Configuration (range.yaml skeleton)

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
  ocsf_version: "1.3.0"
  mapping_profiles: ["default"]

detection:
  sigma:
    rule_paths: ["rules/sigma"]
  evaluation_mode: "batch"   # or "streaming"

reporting:
  output_dir: "runs/"
  emit_html: true
```

## CI and validation

Purple Axiom is intended to fail closed on contract violations:

* Schema validation for each artifact (including per-line JSONL)
* Cross-artifact invariant checks (run_id/scenario_id consistency, referential integrity)
* “Golden run” end-to-end fixtures for regression testing
* Report generation sanity checks

## Extensibility

Designed extension points include:

* New runners beyond Caldera/Atomic
* New lab providers (manual, Ludus, Terraform, other)
* New telemetry sources (endpoint, network, EDR exports)
* New mapping profiles or OCSF versions
* New rule engines beyond Sigma

## Documentation (specs)

* Charter: `docs/spec/000_charter.md` 
* Scope and non-goals: `docs/spec/010_scope.md` 
* Lab providers: `docs/spec/015_lab_providers.md`
* Architecture: `docs/spec/020_architecture.md` 
* Scenario model: `docs/spec/030_scenarios.md` 
* Telemetry pipeline: `docs/spec/040_telemetry_pipeline.md` 
* OCSF normalization: `docs/spec/050_normalization_ocsf.md` 
* Sigma detection model: `docs/spec/060_detection_sigma.md` 
* Scoring and metrics: `docs/spec/070_scoring_metrics.md` 
* Reporting: `docs/spec/080_reporting.md` 
* Security and safety: `docs/spec/090_security_safety.md` 
* Test strategy and CI: `docs/spec/100_test_strategy_ci.md` 
* Operability: `docs/spec/110_operability.md` 
* Configuration reference: `docs/spec/120_config_reference.md` 
* ADRs:

  * `ADR-0001-project-naming-and-versioning.md` 
  * `ADR-0002-event-identity-and-provenance.md` 
* Data contracts: `docs/spec/025_data_contracts.md` 

## Requirements

* Docker and Docker Compose (single-node lab deployment)
* Python 3.10+
* Isolated lab environment (required)

## License

MIT License. See `LICENSE`.

## Contributing

See `CONTRIBUTING.md`. Contributions should preserve:

* deterministic outputs
* contract-first artifacts
* safe-by-default scenario execution
* clear provenance and reproducibility metadata