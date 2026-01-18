# Purple Axiom

**Ground-truth detection engineering through continuous adversary emulation**

Purple Axiom is a **local-first** cyber range for **isolated lab environments**. It executes safe
adversary-emulation scenarios, captures telemetry from lab assets, normalizes events into **OCSF**,
evaluates detections using **Sigma**, and produces **reproducible run bundles** suitable for
regression testing and trend tracking.

## Why Purple Axiom

Most detection engineering loops still look like: run a test, eyeball logs, and call it "good
enough." Purple Axiom specifies a repeatable, defensible loop with explicit artifacts:

- **Ground truth**: what ran, when, where, and with what resolved inputs
- **Telemetry**: what was actually collected (and what was not)
- **Normalization**: how raw events mapped to a portable schema (OCSF), including mapping coverage
- **Detections**: what rules were executable and what fired (Sigma)
- **Scoring**: coverage, latency, and gap classification
- **Reporting**: a run bundle you can diff, gate in CI, and trend over time

## Core philosophy

Treat detections as the theorems you are trying to prove, and adversary emulation as the axioms
(ground truth) you build upon.

This project prioritizes measurable outcomes tied to specific techniques and behaviors, rather than
opaque "security scores."

## Scope and safety

Purple Axiom is designed for isolated lab environments and emphasizes detectability validation
rather than stealth, persistence, or destructive outcomes.

### Explicit non-goals

- Exploit development, weaponization, or destructive testing
- Production deployment guidance for hostile environments
- "Full SIEM replacement" (external ingestion is optional)
- A full-featured lab provisioning platform (Purple Axiom integrates with external lab providers; it
  does not replace them)
- Network telemetry capture and ingestion (pcap and NetFlow/IPFIX) as a required v0.1 capability
  (placeholder contracts are reserved)

### Safety constraints and secure defaults

- The range MUST be operated as an isolated lab, not a production environment.

- Cleanup is required, recorded, and surfaced in reporting.

- Lab assets SHOULD default to an outbound egress-deny posture.

  - Scenario-level network intent is expressed via `scenario.safety.allow_network`.
  - Effective outbound policy is the logical AND of `scenario.safety.allow_network` and
    `security.network.allow_outbound`.
  - Enforcement of outbound posture MUST occur at the lab boundary (provider / lab controls), not as
    a best-effort runner behavior.

- Long-term artifacts MUST avoid storing secrets.

  - Redaction is configurable and deterministic, and may be disabled only with explicit opt-in and
    quarantine handling for unredacted outputs.

- The detection subsystem MUST treat Sigma as non-executable content (no arbitrary code execution).

## Architecture overview

Purple Axiom v0.1 uses a single-host, local-first topology with a one-shot orchestrator and
file-based stage coordination. Each stage reads inputs from the run bundle and writes outputs back
to the run bundle. The filesystem is the inter-stage contract boundary.

The specified pipeline stages are:

1. **Lab provider** resolves target inventory and records a deterministic lab inventory snapshot.
1. **Runner** executes scenario actions and emits an append-only ground-truth timeline plus runner
   evidence artifacts.
1. **Telemetry pipeline** captures raw events (via an OpenTelemetry Collector topology) and runs
   required runtime canaries.
1. **Normalizer** converts raw telemetry into OCSF envelopes with required provenance and
   deterministic event identity.
1. **Validation** applies criteria packs and cleanup verification.
1. **Sigma-to-OCSF bridge** routes Sigma rules to applicable OCSF classes and snapshots mapping
   inputs for reproducibility.
1. **Detection engine** evaluates Sigma rules against normalized events (v0.1 default: DuckDB SQL
   over Parquet).
1. **Scoring** produces coverage, latency, and gap metrics (plus threshold gates where configured).
1. **Reporting** emits human-readable and machine-readable report outputs for diffing and trending.
1. **Signing** (optional) emits integrity artifacts for the run bundle.

```text
┌──────────────────────────────┐
│         Lab Provider         │ ← Inventory resolution (Manual, Ludus, Terraform)
└──────────────┬───────────────┘
               │ Inventory snapshot (deterministic)
               ▼
┌──────────────────────────────┐
│       Scenario Runner        │ ← Execution engine (Atomic Red Team v0.1)
└──────────────┬───────────────┘
               │ Ground truth + Evidence (transcripts)
               ▼
┌──────────────────────────────┐
│      Telemetry Pipeline      │ ← OTel Collector topology + Canaries
└──────────────┬───────────────┘
               │ Raw datasets + Evidence pointers
               ▼
┌──────────────────────────────┐
│     Normalization (OCSF)     │ ← Schema envelopes + Provenance + Identity
└──────────────┬───────────────┘
               │ Normalized event store (Parquet)
               ▼
┌──────────────────────────────┐
│      Criteria Evaluator      │ ← Validation packs + Cleanup verification
└──────────────┬───────────────┘
               │ Validated observations
               ▼
┌──────────────────────────────┐
│     Sigma-to-OCSF Bridge     │ ← Routing + Field mapping + Rule compilation
└──────────────┬───────────────┘
               │ Executable plans (SQL) + Classification
               ▼
┌──────────────────────────────┐
│       Detection Engine       │ ← Evaluation backend (DuckDB)
└──────────────┬───────────────┘
               │ Detection instances
               ▼
┌──────────────────────────────┐
│     Scoring & Reporting      │ ← Metrics aggregation + HTML/JSON generation
└──────────────┬───────────────┘
               │ Integrity metadata
               ▼
┌──────────────────────────────┐
│      Signing (Optional)      │ ← Artifact checksums + Digital signatures
└──────────────────────────────┘
```

## Key concepts

- **Scenario**: a planned set of actions/tests executed by the runner.
- **Run**: a single execution instance with a unique `run_id` (UUID, canonical hyphenated form).
- **Lab inventory snapshot**: the resolved target inventory used for the run, recorded for
  reproducibility and diffability.
- **Ground truth**: append-only timeline of what executed, with hashed summaries and
  expected-observability hints.
- **Normalized events**: OCSF event envelopes with required provenance fields and deterministic
  `metadata.event_id`.
- **Criteria pack**: validation rules that evaluate expected vs observed telemetry and cleanup
  state.
- **Sigma-to-OCSF bridge**: mapping/router layer that makes Sigma evaluation over OCSF mechanically
  testable.
- **Stage outcomes**: deterministic per-stage outcomes (`success | failed | skipped`) with stable
  reason codes that drive `manifest.status` and process exit codes.
- **Run bundle**: the on-disk artifact bundle rooted at `runs/<run_id>/`, indexed by
  `manifest.json`.

## Run bundles

Each run produces a run bundle at `runs/<run_id>/`. The **manifest** is the authoritative index of
what exists, which versions/config hashes were used, and the overall run status.

### Typical layout

The run bundle layout is contract-driven. At a high level, you should expect:

```text
runs/<run_id>/
  manifest.json
  ground_truth.jsonl

  criteria/                # criteria pack snapshot + criteria evaluation outputs
  runner/                  # runner evidence: transcripts, executor metadata, cleanup verification

  raw/                     # evidence tier: source-native telemetry and supporting evidence (policy-controlled)
  raw_parquet/             # analytics tier: structured raw telemetry tables (Parquet)

  normalized/              # analytics tier: normalized OCSF event store + mapping coverage

  bridge/                  # Sigma→OCSF bridge artifacts: mapping pack snapshot, compiled plans, coverage
  detections/              # detection outputs (Sigma evaluation results)
  scoring/                 # summary metrics, joins/derivations (optional)

  report/                  # HTML and JSON report outputs (presentation derived from scoring and run metadata)

  logs/                    # structured operability summaries and debug logs (not long-term storage)
  security/                # optional integrity and redaction metadata (checksums/signatures, policy manifests)
  unredacted/              # optional quarantine for unredacted evidence (explicit opt-in; excluded from exports)
```

### Storage formats and determinism

Purple Axiom uses a two-tier storage model:

- **Evidence tier** preserves source-native artifacts when they are valuable for fidelity and
  reprocessing (under `raw/`).
- **Analytics tier** stores structured, queryable datasets for evaluation and trending (Parquet
  under `raw_parquet/` and `normalized/`).

Format expectations:

- Small, contract-driven artifacts are JSON (for example `manifest.json`, `scoring/summary.json`,
  and `report/report.json`).
- Event-like streams are JSONL when line-addressable diffs/fixtures are required (for example
  `ground_truth.jsonl`).
- Long-term event streams and large datasets are Parquet by default (for example the normalized OCSF
  event store).

Outputs intended to be diffed and hashed MUST follow deterministic ordering and canonicalization
rules defined in the storage and contracts specs.

## Determinism, provenance, and CI posture

Purple Axiom is specified to fail closed on contract violations. Key properties include:

- `run_id` is immutable per execution and is carried across artifacts via required provenance
  fields.
- `metadata.event_id` is deterministic when the source event and normalization inputs match.
- Hashes that participate in identity MUST use canonical JSON rules.
- Mapping packs and bridge inputs are snapshotted so evaluations are reproducible across time.
- Multi-scenario runs are reserved in v0.1. Implementations MUST fail closed if more than one
  distinct `scenario_id` is observed.
- Validators MUST use local-only JSON Schema `$ref` resolution (no network fetches) and
  deterministic error ordering.
- Stage outcomes and deterministic exit codes are used for CI gating.

## Configuration

Purple Axiom is configured via `range.yaml` (see the normative configuration reference).
Configuration and contract validation are a first-class part of the runtime and CI model.

- Canonical keys, defaults, and examples: `docs/spec/120_config_reference.md`
- Operational limits and safety toggles (including redaction, network posture, and signing):
  `docs/spec/090_security_safety.md` and `docs/adr/ADR-0003-redaction-policy.md`

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
| Plan execution model        | `docs/spec/031_plan_execution_model.md`                 |
| Atomic executor integration | `docs/spec/032_atomic_red_team_executor_integration.md` |
| Validation criteria         | `docs/spec/035_validation_criteria.md`                  |
| Telemetry pipeline          | `docs/spec/040_telemetry_pipeline.md`                   |
| osquery integration         | `docs/spec/042_osquery_integration.md`                  |
| Unix log ingestion          | `docs/spec/044_unix_log_ingestion.md`                   |
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

| ADR                                                                              | Decision area                                             |
| -------------------------------------------------------------------------------- | --------------------------------------------------------- |
| `docs/adr/ADR-0001-project-naming-and-versioning.md`                             | Project naming rules and versioning policy                |
| `docs/adr/ADR-0002-event-identity-and-provenance.md`                             | Event identity, provenance model, and determinism rules   |
| `docs/adr/ADR-0003-redaction-policy.md`                                          | Redaction policy posture and consequences                 |
| `docs/adr/ADR-0004-deployment-architecture-and-inter-component-communication.md` | Deployment architecture and inter-component communication |
| `docs/adr/ADR-0005-stage-outcomes-and-failure-classification.md`                 | Stage outcomes and failure classification rules           |
| `docs/adr/ADR-0006-plan-execution-model.md`                                      | Plan execution model and reserved multi-target semantics  |

## Requirements

- Isolated lab environment (required)
- Python 3.12.3 (pinned; see `SUPPORTED_VERSIONS.md` for toolchain details)
- Pinned runtime dependencies as specified in `SUPPORTED_VERSIONS.md`:
  - OpenTelemetry Collector Contrib 0.143.1
  - pySigma 1.1.0
  - pySigma-pipeline-ocsf 0.1.1
  - DuckDB 1.4.3
  - pyarrow 22.0.0
  - jsonschema 4.26.0
  - osquery 5.14.1 (for lab endpoints)
  - OCSF schema 1.7.0 (normalization target)
  - PowerShell 7.4.6 (for Atomic executor)
- Optional packaging: Docker Compose MAY be provided for installation convenience, but it is not a
  normative requirement for v0.1

## License

MIT License. See `LICENSE`.

## Contributing

See `CONTRIBUTING.md`. Contributions should preserve:

- deterministic outputs
- contract-first artifacts
- safe-by-default scenario execution
- clear provenance and reproducibility metadata