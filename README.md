# Purple Axiom

**Ground-truth detection engineering through continuous adversary emulation**

Purple Axiom is a **local-first** cyber range for **isolated lab environments** that runs safe
adversary-emulation scenarios, captures telemetry from lab assets, normalizes events into **OCSF**,
evaluates detections using **Sigma**, and produces **reproducible run bundles** (artifact bundles
suitable for regression testing and trend tracking).

## Why Purple Axiom

Most detection engineering loops still look like: run a test, eyeball logs, and call it "good
enough." Purple Axiom specifies a repeatable, defensible loop:

- **Ground truth**: what ran, when, where, and what should have been observable
- **Telemetry**: what was actually collected
- **Normalization**: how raw events mapped to a portable schema (OCSF)
- **Detections**: what rules fired (Sigma)
- **Scoring**: coverage, latency, and gap classification
- **Reporting**: a run bundle you can diff, gate in CI, and trend over time

## Core philosophy

Treat detections as the theorems you are trying to prove, and adversary emulation as the axioms
(ground truth) you build upon.

This project prioritizes **measurable outcomes tied to specific techniques and behaviors**, rather
than opaque "security scores."

## Scope and safety

Purple Axiom is designed for **isolated lab environments** and emphasizes detectability validation
rather than stealth, persistence, or destructive outcomes.

### Explicit non-goals

- Exploit development, weaponization, or destructive testing
- Production deployment guidance for hostile environments
- "Full SIEM replacement" (external ingestion is optional)
- A full-featured lab provisioning platform (Purple Axiom integrates with external lab providers; it
  does not replace them)

### Safety constraints and secure defaults

- The range MUST be operated as an isolated lab, not a production environment.
- Cleanup is required, recorded, and surfaced in reporting.
- Long-term artifacts MUST avoid storing secrets; redaction is configurable and can be tuned or
  disabled (with explicit handling for unredacted outputs).
- The detection subsystem MUST treat Sigma as non-executable content (no arbitrary code execution).

## Architecture (high-level)

Purple Axiom's specified pipeline stages are:

1. **Runner** executes scenario actions and emits an append-only ground-truth timeline.
1. **Telemetry pipeline** captures raw events (via OpenTelemetry Collector topology) and preserves
   original semantics.
1. **Normalizer** converts raw events to OCSF envelopes with required provenance and deterministic
   identity.
1. **Validation** applies criteria packs and cleanup verification.
1. **Detection** evaluates Sigma rules against normalized events (via the Sigma-to-OCSF bridge).
1. **Scoring** produces coverage/latency/gap metrics.
1. **Reporting** emits an HTML + JSON report bundle for diffing and trending.

```text
┌─────────────────────────┐
│ Scenario Runner         │  ← runner engines (e.g., Atomic, Caldera)
└────────────┬────────────┘
             │ ground truth (append-only)
             ▼
┌─────────────────────────┐
│ Telemetry Pipeline      │  ← OTel Collector topology (agent/gateway)
└────────────┬────────────┘
             │ raw events
             ▼
┌─────────────────────────┐
│ Normalizer → OCSF       │  ← OCSF envelopes + provenance + event identity
└────────────┬────────────┘
             │ normalized event store
             ▼
┌─────────────────────────┐
│ Validation (Criteria)   │  ← criteria packs + cleanup verification
└────────────┬────────────┘
             │ validated observations
             ▼
┌─────────────────────────┐
│ Sigma Detection         │  ← Sigma→OCSF bridge + evaluation
└────────────┬────────────┘
             │ detections
             ▼
┌─────────────────────────┐
│ Scoring + Reporting     │  ← metrics + HTML/JSON run bundle
└─────────────────────────┘
```

## Key concepts

- **Scenario**: a planned set of actions/tests executed by the runner.
- **Run**: a single execution instance with a unique `run_id`.
- **Ground truth**: append-only timeline of what executed, with hashed summaries and "expected
  telemetry" hints.
- **Normalized events**: OCSF event envelopes with required provenance fields and deterministic
  `metadata.event_id`.
- **Criteria pack**: validation rules that evaluate expected vs observed telemetry and cleanup
  state.
- **Sigma-to-OCSF bridge**: mapping/router layer that makes Sigma evaluation over OCSF mechanically
  testable.
- **Run bundle**: the on-disk artifact bundle rooted at `runs/<run_id>/`, indexed by
  `manifest.json`.

## Run bundles

Each run produces a **run bundle** at `runs/<run_id>/`. The **manifest** is the authoritative index
of what exists and which versions/config hashes were used.

### Typical layout

```text
runs/<run_id>/
  manifest.json
  ground_truth.jsonl

  runner/                 # runner-emitted execution events
  raw/                    # raw telemetry capture (format depends on source)
  normalized/             # normalized OCSF event store + coverage artifacts
  criteria/               # criteria pack inputs/outputs + cleanup verification artifacts
  bridge/                 # Sigma→OCSF bridge artifacts (router + mapping snapshots)
  detections/             # detection results (Sigma evaluation outputs)
  scoring/                # scoring summaries and per-technique metrics
  report/                 # human + machine-readable report bundle (HTML/JSON)
  logs/                   # volatile logs (not long-term storage)
  security/               # optional security metadata (e.g., signatures, redaction manifests)
```

### Storage formats and determinism

- Normalized event storage MAY be JSONL or Parquet depending on the contract and use case; Parquet
  is the default for long-term analytics storage, while JSONL is used where line-addressable diffs
  and fixtures are required.
- Outputs that are intended to be diffed (JSON/JSONL) MUST use deterministic ordering rules as
  specified in the storage/contracts documentation.

## Determinism and provenance

- `run_id` is immutable per execution and is carried across artifacts via required provenance
  fields.
- `metadata.event_id` is deterministic when the source event and normalization inputs match (see
  event identity ADR).
- Hashes that participate in identity MUST use canonical JSON rules (see contracts/ADR).
- Mapping profiles and bridge inputs are snapshotted to make evaluations reproducible across time.

## Configuration

Purple Axiom is configured via a `range.yaml` (see the normative configuration reference).

- Canonical keys, defaults, and examples: `docs/spec/120_config_reference.md`
- Operational limits and safety toggles (including redaction and signing):
  `docs/spec/120_config_reference.md` + `docs/spec/090_security_safety.md` +
  `ADR-0003-redaction-policy.md`

## CI and validation

Purple Axiom is specified to fail closed on contract violations:

- Schema validation for each artifact (including per-line JSONL validation where applicable)
- Cross-artifact invariant checks (e.g., `run_id` consistency, referential integrity across event
  IDs)
- Golden run end-to-end fixtures for regression testing
- Report generation sanity checks

## Documentation

### Primary specs

| Spec                        | File                                                    |
| --------------------------- | ------------------------------------------------------- |
| Charter                     | `docs/spec/000_charter.md`                              |
| Scope and non-goals         | `docs/spec/010_scope.md`                                |
| Lab providers               | `docs/spec/015_lab_providers.md`                        |
| Architecture                | `docs/spec/020_architecture.md`                         |
| Data contracts              | `docs/spec/025_data_contracts.md`                       |
| Scenario model              | `docs/spec/030_scenarios.md`                            |
| Atomic executor integration | `docs/spec/032_atomic_red_team_executor_integration.md` |
| Validation criteria         | `docs/spec/035_validation_criteria.md`                  |
| Telemetry pipeline          | `docs/spec/040_telemetry_pipeline.md`                   |
| Osquery integration         | `docs/spec/042_osquery_integration.md`                  |
| Storage formats             | `docs/spec/045_storage_formats.md`                      |
| OCSF normalization          | `docs/spec/050_normalization_ocsf.md`                   |
| OCSF field tiers            | `docs/spec/055_ocsf_field_tiers.md`                     |
| Sigma detection model       | `docs/spec/060_detection_sigma.md`                      |
| Sigma-to-OCSF bridge        | `docs/spec/065_sigma_to_ocsf_bridge.md`                 |
| Scoring and metrics         | `docs/spec/070_scoring_metrics.md`                      |
| Reporting                   | `docs/spec/080_reporting.md`                            |
| Security and safety         | `docs/spec/090_security_safety.md`                      |
| Test strategy and CI        | `docs/spec/100_test_strategy_ci.md`                     |
| Operability                 | `docs/spec/110_operability.md`                          |
| Configuration reference     | `docs/spec/120_config_reference.md`                     |

### ADRs

| ADR                                                                     | Decision area                                             |
| ----------------------------------------------------------------------- | --------------------------------------------------------- |
| `ADR-0001-project-naming-and-versioning.md`                             | Project naming rules and versioning policy                |
| `ADR-0002-event-identity-and-provenance.md`                             | Event identity, provenance model, and determinism rules   |
| `ADR-0003-redaction-policy.md`                                          | Redaction policy posture and consequences                 |
| `ADR-0004-deployment-architecture-and-inter-component-communication.md` | Deployment architecture and inter-component communication |
| `ADR-0005-stage-outcomes-and-failure-classification.md`                 | Stage outcomes and failure classification rules           |

## Requirements

- Docker and Docker Compose (single-node lab deployment)
- Python 3.12.3 (pinned; see `SUPPORTED_VERSIONS.md` for toolchain details)
- Isolated lab environment (required)

## License

MIT License. See `LICENSE`.

## Contributing

See `CONTRIBUTING.md`. Contributions should preserve:

- deterministic outputs
- contract-first artifacts
- safe-by-default scenario execution
- clear provenance and reproducibility metadata
