---
title: 'Project charter: continuous purple-team range'
description: Defines Purple Axiom's mission, MVP outcomes, intended users, normative dependencies, and definition of done.
status: draft
category: spec
tags: [charter, scope]
---

# Project charter: continuous purple-team range

This charter defines Purple Axiom's mission, MVP outcomes, intended users, and definition of done
for v0.1.

## Summary

Purple Axiom is a local-first cyber range that runs safe adversary-emulation scenarios, captures
telemetry, normalizes events into OCSF, evaluates detections, and produces reproducible run bundles
and scorecards.

In v0.1, the pipeline is specified as a one-shot orchestrator that executes a fixed stage sequence.
Each stage reads inputs from the run bundle and publishes outputs back into the run bundle (the
filesystem is the inter-stage contract boundary). Core stages MUST NOT require service-to-service
RPC in v0.1. The stable stage identifiers are:

- `lab_provider`
- `runner`
- `telemetry`
- `normalization`
- `validation`
- `detection`
- `scoring`
- `reporting`
- `signing` (when enabled)

See the
[deployment architecture ADR](../adr/ADR-0004-deployment-architecture-and-inter-component-communication.md)
for the normative run sequence, IO boundaries, and publish semantics.

## Motivation

- Replace ad-hoc "run a test, eyeball logs" workflows with repeatable ground-truth runs and
  measurable detection outcomes.
- Enable regression testing for detections, telemetry pipelines, schema mappings, and evaluation
  joins by capturing the full run bundle as a reproducible artifact set.

## Principles

### Determinism and reproducibility

- A run MUST be explainable and comparable across time by inspecting the run bundle and manifest,
  not by relying on external mutable state.
- Asset identity MUST be stable across runs (provider-native identifiers are treated as optional
  metadata, not the identity basis). See the [lab providers specification](015_lab_providers.md).

### Contract-driven, stage-scoped execution

- Each stage MUST be implementable as "read inputs from run bundle, write outputs to run bundle."
- For v0.1, stage ordering and the minimum published outputs are normative at the stage level (see
  the
  [deployment architecture ADR](../adr/ADR-0004-deployment-architecture-and-inter-component-communication.md)).

### Safety-by-default operation

Purple Axiom intentionally runs adversary emulation and MUST be safe to run in a lab. The platform
MUST default to an isolated, egress-deny posture and MUST fail closed when safety controls are
violated. Scenario-level network intent is expressed by `scenario.safety.allow_network`, but the
effective isolation posture is enforced at the lab boundary (the runner is not considered a
sufficient isolation mechanism). See the [security and safety specification](090_security_safety.md)
and the [scenarios specification](030_scenarios.md).

## Scope of the current v0.1 specification set

The current spec set defines a complete "run bundle" pipeline with deterministic artifacts and stage
outcomes, including:

- Pluggable lab provider inventory resolution and deterministic inventory snapshotting.
- Scenario execution producing a ground truth timeline with deterministic action identity and
  resolved targets.
- Telemetry collection over the run window, including validation canaries.
- Normalization into OCSF with mapping coverage outputs.
- Validation against criteria packs and cleanup verification outputs.
- Detection evaluation producing per-rule/per-technique outcomes.
- Scoring that joins ground truth, validation, and detections into a machine-readable summary.
- Reporting that renders human-readable artifacts derived from the machine-readable summary.
- Optional signing as a stage with explicit failure semantics.

This stage model and the minimum published output paths are specified in the
[deployment architecture ADR](../adr/ADR-0004-deployment-architecture-and-inter-component-communication.md).

## Primary outcomes

### MVP outcomes (v0.1)

The MVP outcome is a single "one-click" run that produces a reproducible run bundle containing, at
minimum:

- **Inventory snapshot**: a run-scoped snapshot that preserves the resolved target set even if the
  provider state changes later. See the [lab providers specification](015_lab_providers.md).
- **Ground truth timeline**: `ground_truth.jsonl`, one action per line, including deterministic
  action identity and resolved target metadata. See the [scenarios specification](030_scenarios.md).
- **Stage-scoped evidence**: runner evidence under `runner/**`, and telemetry validation evidence
  when enabled. See the
  [deployment architecture ADR](../adr/ADR-0004-deployment-architecture-and-inter-component-communication.md).
- **Normalized event store**: `normalized/**` as the canonical normalized dataset for downstream
  detection and scoring. See the
  [deployment architecture ADR](../adr/ADR-0004-deployment-architecture-and-inter-component-communication.md).
- **Detection outcomes**: `detections/detections.jsonl` produced from sigma evaluation via the
  detection stage. See the
  [deployment architecture ADR](../adr/ADR-0004-deployment-architecture-and-inter-component-communication.md).
- **Machine-readable scorecard**: `scoring/summary.json` as the required machine-readable run
  summary output. See the
  [deployment architecture ADR](../adr/ADR-0004-deployment-architecture-and-inter-component-communication.md)
  and the [stage outcomes ADR](../adr/ADR-0005-stage-outcomes-and-failure-classification.md).
- **Human-readable report**: `report/**` as presentation outputs derived from scoring and other run
  artifacts. See the
  [deployment architecture ADR](../adr/ADR-0004-deployment-architecture-and-inter-component-communication.md)
  and the [stage outcomes ADR](../adr/ADR-0005-stage-outcomes-and-failure-classification.md).

### Operational safety outcomes (v0.1)

- **Egress deny enforcement**: when the effective outbound policy is denied, the validator MUST run
  a TCP connect canary and MUST fail the run if it observes reachability (evidence is recorded
  deterministically). See the [operability specification](110_operability.md).
- **Fail-closed behavior**: safety control violations are run-fatal by default and must be
  observable in deterministic stage outcomes and reason codes. See the
  [security and safety specification](090_security_safety.md) and the
  [deployment architecture ADR](../adr/ADR-0004-deployment-architecture-and-inter-component-communication.md).

## Intended users

- Detection engineers validating visibility and detection logic.
- SOC analysts validating investigative pivots and alert quality.
- Purple teams and continuous security testing operators running unattended lab workflows.

## Key upstream dependencies

Normative dependencies are those relied upon by the v0.1 pipeline contracts. Pinned versions live in
[SUPPORTED_VERSIONS.md](../../SUPPORTED_VERSIONS.md).

- **Atomic Red Team** as the primary v0.1 scenario plan type (other plan types are reserved). See
  the [scenarios specification](030_scenarios.md).
- **OpenTelemetry Collector Contrib** as the default telemetry collection mechanism (privileged,
  hardened, and minimized per the security boundary requirements). See the
  [security and safety specification](090_security_safety.md).
- **OCSF schema** as the canonical normalized event model (the `normalized/**` store is the input to
  detection and scoring stages). See the
  [deployment architecture ADR](../adr/ADR-0004-deployment-architecture-and-inter-component-communication.md).
- **Sigma toolchain (pySigma + pySigma-pipeline-ocsf)** as the detection portability layer and
  Sigma-to-OCSF bridge (evaluated in the detection stage). See the
  [deployment architecture ADR](../adr/ADR-0004-deployment-architecture-and-inter-component-communication.md).
- **DuckDB** as the batch evaluator backend.
- **pyarrow** as the Parquet scanning and schema inspection backend.
- **jsonschema** as the contract validation engine.
- **osquery** as the endpoint telemetry source (osqueryd).
- **PowerShell** as the Atomic executor runner.

## Definition of done

Purple Axiom v0.1 is considered "done" when:

- A single command (or equivalent one-shot orchestration) can execute the canonical stage sequence
  and publish the required run bundle artifacts. See the
  [deployment architecture ADR](../adr/ADR-0004-deployment-architecture-and-inter-component-communication.md).
- The run produces deterministic stage outcomes with stable stage identifiers and reason codes such
  that failures can be triaged mechanically using `(stage, status, fail_mode, reason_code)`. See the
  [stage outcomes ADR](../adr/ADR-0005-stage-outcomes-and-failure-classification.md).
- Re-running with the same inputs MUST produce identical outputs, or MUST explicitly record and
  surface the sources of nondeterminism in the run bundle and stage outcomes (fail-closed is the
  default posture for safety and contract violations). See the
  [security and safety specification](090_security_safety.md) and
  [lab providers specification](015_lab_providers.md).

## References

Normative or orienting references for v0.1:

- [Lab providers specification](015_lab_providers.md) (inventory snapshotting, asset identity)
- [Scenarios specification](030_scenarios.md) (scenario seed schema, ground truth timeline)
- [Security and safety specification](090_security_safety.md) (safety posture, boundaries,
  redaction, secrets)
- [Operability specification](110_operability.md) (health signals, canaries, resource safeguards)
- [Configuration reference](120_config_reference.md) (configuration determinism and secret reference
  rules)
- [Deployment architecture ADR](../adr/ADR-0004-deployment-architecture-and-inter-component-communication.md)
  (stage model, run sequence, IO boundaries, publish semantics)
- [Stage outcomes ADR](../adr/ADR-0005-stage-outcomes-and-failure-classification.md) (stage outcomes
  taxonomy and CI gating implications)

## Changelog

| Date       | Change                                                                  |
| ---------- | ----------------------------------------------------------------------- |
| 2026-01-13 | Expand charter to reflect current v0.1 stage model, safety, operability |
| 2026-01-12 | Formatting update                                                       |
