---
title: Scope and non-goals
description: Defines what is in scope for Purple Axiom v0.1 and what is explicitly out of scope.
status: draft
category: spec
tags: [scope]
---

# Scope and non-goals

This document defines the v0.1 scope boundaries for Purple Axiom and the explicit non-goals that
shape the initial release. It highlights what the pipeline must support, which contracts are
reserved for later, and the operating assumptions used throughout the spec set.

## Scope

This document covers:

- In-scope capabilities and contracts for v0.1 execution.
- Reserved or placeholder contracts explicitly deferred beyond v0.1.
- Explicit non-goals and operating assumptions that constrain implementation.

This document does NOT cover:

- Detailed stage responsibilities (see the [architecture specification](020_architecture.md)).
- Detailed artifact schemas and cross-artifact invariants (see the
  [data contracts specification](025_data_contracts.md)).
- Storage tier definitions and retention format rules (see the
  [storage formats specification](045_storage_formats.md)).
- Configuration surface area (see the [configuration reference](120_config_reference.md)).
- Safety, security, and operability requirements (see the
  [security and safety specification](090_security_safety.md) and
  [operability specification](110_operability.md)).

## In scope for v0.1

### Canonical v0.1 coordination and path conventions

This scope document assumes the canonical v0.1 run-bundle coordination and path conventions below
(see the architecture and data contracts specifications for full schemas and invariants):

- Run bundle root: `runs/<run_id>/`
- Exclusive run lock: `runs/.locks/<run_id>.lock`
- Publish-gate staging root: `runs/<run_id>/.staging/<stage_id>/`
- Contract validation failure reports (publish gate):
  `runs/<run_id>/logs/contract_validation/<stage_id>.json`

Regression baseline materialization, when enabled, is owned by the reporting stage and uses:

- `runs/<run_id>/inputs/baseline_run_ref.json`
- `runs/<run_id>/inputs/baseline/**`

Unless explicitly stated otherwise, file paths referenced in the spec set are run-relative (relative
to `runs/<run_id>/`).

`inputs/**` are pinned run inputs. Stages MUST treat any pre-existing operator-provided files under
`inputs/**` as read-only. The reporting stage MAY create `inputs/baseline_run_ref.json` and
`inputs/baseline/**` only when regression comparison is enabled.

- One-shot, local-first run execution on a single run host.
  - Core stages coordinate via filesystem artifacts in `runs/<run_id>/`.
  - Core stages do not require service-to-service RPC for coordination in v0.1.
  - Stage outputs are published via staging + validation + atomic publish (publish gates), and
    stages are not considered complete until their outcomes are recorded.
- A fixed, staged pipeline with stable stage identifiers and stage-scoped outputs:
  - `lab_provider`, `runner`, `telemetry`, `normalization`, `validation`, `detection`, `scoring`,
    `reporting`, and optional `signing`.
- Orchestrator entrypoints (range lifecycle verbs) are in scope as an interface surface when
  exposed:
  - `simulate` performs the canonical v0.1 stage sequence.
  - `build` semantics are REQUIRED for v0.1 compliance to ensure deterministic run initialization
    (input pinning and `manifest.json` creation). If `build` is not exposed as a separate operator
    command, the orchestrator MUST execute the `build` semantics implicitly as the first step of
    `simulate`.
  - `replay`, `export`, and `destroy` are permitted entrypoints (as defined in the architecture
    spec) but are not required to be implemented for v0.1 completeness. `destroy` is RECOMMENDED
    when lab providers provision or mutate lab resources.
- Contract-backed run bundles:
  - A manifest-driven run bundle layout, with deterministic hashing and provenance fields.
  - Publish-gate contract validation for contract-backed artifacts, with deterministic validation
    error ordering and deterministic contract-validation reports on failure.
  - Run-scoped session state and provenance (for example principal context and cache provenance)
    recorded under `runs/<run_id>/` (no global session DB required for correctness).
- Pluggable lab inventory resolution via a lab provider interface:
  - Manual lab definitions are supported.
  - Provider-derived inventory is supported via adapter parsing and deterministic canonicalization.
  - A deterministic `lab_inventory_snapshot.json` is recorded per run for reproducibility and
    diffability.
  - The snapshot is published at run-relative path `logs/lab_inventory_snapshot.json` and is treated
    as reproducibility-critical (it is not “debug-only” despite living under `logs/`).
  - v0.1 conformance requires `lab.inventory.snapshot_to_run_bundle = true`; configurations that set
    it to `false` MUST be rejected.
- Scenario execution (runner):
  - Optional run-scoped environment configuration (`runner.environment_config`) is in scope when
    enabled, including baseline readiness checks and benign background activity/noise generation
    used to improve dataset realism.
  - v0.1 supports **Atomic Test Plan** scenarios.
  - The runner emits a deterministic ground truth timeline and per-action evidence artifacts.
  - For `engine = "atomic"`, the runner conforms to the Atomic execution integration contract,
    including deterministic YAML parsing, resolved input determinism, transcript capture, cleanup
    invocation, and cleanup verification.
  - Runner-evidence artifacts required for deterministic joins and safe disclosure are in scope,
    including (non-exhaustive): `runner/actions/<action_id>/resolved_inputs_redacted.json`,
    `runner/actions/<action_id>/requirements_evaluation.json`, and
    `runner/actions/<action_id>/side_effect_ledger.json`.
  - Runner requirements evaluation is in scope:
    - Deterministic pre-execution requirement checks (platform, privilege, tool availability).
    - Deterministic action `skipped` outcomes and reason codes when requirements are not satisfied.
  - Runner prerequisites behavior is in scope via a deterministic prerequisites policy (including
    explicit enablement for any prerequisite-fetch behavior).
  - Runner runtime dependency immutability is in scope as a determinism and safety requirement:
    - Runtime self-update behavior is disallowed; missing/incompatible dependencies fail closed.
  - Optional runner enrichments are in scope when enabled:
    - Run-level principal context capture (`runner/principal_context.json`) with redaction-safe
      reporting behavior.
    - Principal context capture is controlled by `runner.identity.emit_principal_context` (default:
      `true`). When disabled, the runner omits `runner/principal_context.json` and MUST NOT populate
      ground truth `principal_id` / `principal_kind` fields.
    - When emitted, `runner/principal_context.json` is evidence-tier and MUST follow the effective
      redaction posture. If the content cannot be made redaction-safe deterministically, the runner
      MUST withhold or quarantine the unredacted bytes and write a deterministic placeholder
      artifact at `runner/principal_context.json`.
    - Synthetic correlation marker emission and observability reporting, when enabled.
    - State reconciliation reporting (detect-and-report drift); repair/mutation is reserved.
- Telemetry collection from lab assets (endpoint-first):
  - OpenTelemetry Collector-based capture is the normative path for endpoint telemetry.
  - Supported endpoint telemetry sources include:
    - Windows Event Log (required raw/unrendered fidelity in v0.1, validated by a runtime canary),
    - Sysmon and Windows Security logs,
    - Linux auditd and Unix syslog ingestion (when enabled),
    - osquery as an optional endpoint telemetry source with a defined input format and routing
      expectations.
  - Telemetry stage outputs are in scope as:
    - analytics-tier telemetry datasets under `raw_parquet/**`, and
    - evidence-tier source-native payloads under `raw/**` when raw preservation is enabled.
  - Telemetry validation includes required runtime canaries and fail modes (for example agent
    liveness heartbeats for dead-on-arrival detection in push-only OTLP, raw Windows Event Log
    capture, checkpointing integrity, resource budgets).
  - When enabled, telemetry validation is published as a contract-backed summary artifact at
    `logs/telemetry_validation.json` and is referenced by scoring/reporting for mechanical gap
    attribution.
- Normalization into OCSF:
  - Normalized events satisfy the required envelope and provenance rules.
  - Deterministic event identity and provenance rules are applied during normalization.
  - The pipeline records mapping coverage and supports tiered expectations (Core vs Extended) for
    field presence and reporting, including coverage gates that can degrade run status.
  - Tier model note (v0.1): Tier 0 (required envelope + core identifiers) and Tier 1 (Core Common)
    fields are the primary coverage gating surface; Tier 2 (class minimums) and Tier 3 (Extended)
    fields are measured and reported but are not required for v0.1 completeness unless explicitly
    gated by configuration.
- Validation against expected telemetry (criteria packs) and cleanup verification:
  - Criteria pack snapshotting and deterministic selection (when enabled).
  - Criteria evaluation emits per-action results, including deterministic `skipped` reasons when an
    action cannot be evaluated under configured policy.
  - Cleanup verification outputs are first-class, contract-backed artifacts produced by the runner
    and consumed for validation/scoring/reporting.
- Detection evaluation and scoring:
  - Sigma-based detection evaluation is in scope via a Sigma-to-OCSF bridge and deterministic
    executability classification.
    - Sigma features that are not supported for execution in v0.1 are classified deterministically
      (rather than “best-effort” execution).
  - Scoring joins ground truth, validation outputs, and detection outputs into a machine-readable
    run summary.
  - Quality gates that downgrade a run (for example normalization or coverage gates) are expressed
    as deterministic stage outcomes and reason codes.
- Reporting:
  - Human-readable reporting derived from machine-readable artifacts (for example the scoring
    summary), plus machine-readable report artifacts intended for downstream automation and CI.
  - CI gate surface is in scope:
    - `report/thresholds.json` supports deterministic threshold evaluation and status
      recommendation.
    - Reporting exit codes align with run status for mechanical gating.
  - Regression comparison is in scope when enabled:
    - The reporting stage materializes a deterministic baseline reference under `inputs/**` and
      computes regression deltas as part of reporting outputs.
    - Baseline artifacts are run-relative `inputs/baseline_run_ref.json` and `inputs/baseline/**`.
    - Only the reporting stage writes baseline artifacts under `inputs/**`; other stages MUST treat
      `inputs/**` as read-only pinned inputs.
    - Regression results are embedded in `report/report.json` (no separate regression output tree).
- Security, safety, and operability guardrails that make unattended continuous runs viable:
  - Redaction posture and deterministic redaction policy application for evidence artifacts.
  - Deterministic withheld/quarantine semantics for sensitive evidence when redaction is disabled.
  - Secrets-by-reference configuration rules (no resolved secrets in artifacts).
  - Resource budgeting and operational health artifacts, including deterministic stage outcomes and
    exit codes.
  - Default isolated lab posture and required egress enforcement verification when outbound egress
    is denied by policy.

## Reserved and placeholder contracts

The following items are reserved for future expansion and are intentionally specified only as
placeholder contracts or reserved types in v0.1.

- Network telemetry capture and ingestion (pcap and NetFlow/IPFIX):
  - Placeholder artifact contracts may exist, but capture and ingestion are not required v0.1
    capabilities.
  - Operators may integrate custom network sources, but any resulting normalized events must still
    follow deterministic event identity rules and required envelope fields.
- Additional scenario and plan types:
  - Caldera operations are reserved (not supported in v0.1).
  - Mixed plans and matrix plans are reserved (not supported in v0.1).
  - `plan/**` compiled plan graph artifacts are reserved for v0.2+.
- Multi-scenario runs:
  - v0.1 is single-scenario per run bundle. Multi-scenario manifests and multi-scenario plan
    execution are reserved for a future release.
- Control plane:
  - A future RPC-based endpoint management/control-plane layer is reserved.
  - v0.1 requires control plane to be disabled (not implemented as a required capability).
- State reconciliation repair/mutation:
  - Drift detection and reporting is in scope when enabled.
  - Any automatic repair intent or mutation of targets based on reconciliation is reserved (default
    is observe-only; repair is blocked by policy).
- Native container exports (for example EVTX export, PCAP retention):
  - Pipeline correctness MUST NOT depend on native container exports in v0.1.
  - Any such exports (if introduced later) require explicit config gates and explicit budget and
    disclosure semantics.
- Threat intelligence pack inputs and enrichment:
  - The threat intelligence integration model (local snapshot packs and enrichment inputs) is v0.2+
    and is reserved. v0.1 MUST NOT require threat intelligence artifacts as a correctness
    dependency.
  - Any future threat intelligence integration MUST remain local-only by default (no outbound fetch
    during a run) and MUST preserve determinism via snapshotting + hashing.

## Explicit non-goals for v0.1

The following are explicit non-goals for initial releases, including v0.1.

- Required network sensor capture and ingestion as a baseline platform capability (pcap, NetFlow,
  Zeek, Suricata). Placeholder contracts do not imply required implementation.
- A required long-running daemon, distributed control plane, or scheduler. External scheduling is
  allowed, but the v0.1 orchestrator is a one-shot process per run.
- Service-to-service RPC as a required mechanism for coordination between core stages. The run
  bundle filesystem is the v0.1 coordination boundary.
- A full lab provisioning platform:
  - Purple Axiom integrates with external lab providers and inventories.
  - Provisioning, mutation, or teardown is not a required v0.1 capability unless explicitly enabled
    by a lab provider implementation.
- Automatic endpoint management (agent installation, config injection, credential rotation) as a
  required v0.1 platform feature (control plane is reserved and disabled).
- Full SIEM replacement or enterprise ingestion defaults:
  - Purple Axiom produces run bundles and evaluation artifacts.
  - External SIEM ingestion is optional and out of scope as a required capability.
- Production deployment guidance for hostile or multi-tenant environments.
- Network or threat intelligence enrichment that requires outbound network access by default.
- Runtime self-update or “fetch dependencies at execution time” behavior as a supported runner
  mechanism.
- A comprehensive UI or SaaS service.
  - Optional packaging (for example Docker Compose) is permitted as an installation convenience, but
    must not change stage semantics or determinism guarantees.

## Operating assumptions

- Runs occur in an isolated lab environment, local-first by default.
- Scenario payloads emphasize detectability validation, not stealth or permanence.
- Enforcement of outbound egress posture is performed at the lab boundary by the lab provider or
  equivalent lab controls. Runner-side controls may be defense-in-depth only.
- When outbound egress is denied by effective policy, telemetry validation performs a deterministic
  egress canary check and treats an observed violation as run-fatal under default policy.
- Publish gates and stage completion semantics enforce determinism:
  - Stages publish outputs atomically after validation, and do not partially populate final paths.
  - Stage outcomes and reason codes are recorded deterministically for mechanical triage.
- Configurations, schema references, and contract validation are local-only and deterministic:
  - Schema `$ref` resolution does not fetch remote references during validation.
  - A run is reproducible by inspecting the run bundle and pinned inputs, not by consulting mutable
    external state.
- Cross-run caches (if any) are treated as optional optimizations and are explicitly gated:
  - Cross-run caching is disallowed by default and requires deterministic cache provenance recording
    when enabled.

## Key decisions

- v0.1 focuses on single-host, one-shot execution with filesystem-coordinated stages.
- Atomic Red Team scenarios are the only supported plan type for v0.1.
- Endpoint telemetry capture and OCSF normalization are the normative ingestion path for v0.1.
- Deterministic publish-gate validation and deterministic stage outcomes are required for
  unattended, repeatable operation.
- Regression comparison, when enabled, is owned by the reporting stage and is expressed in report
  artifacts rather than as separate pipelines.

## References

- [Charter specification](000_charter.md)
- [Lab providers specification](015_lab_providers.md)
- [Architecture specification](020_architecture.md)
- [Data contracts specification](025_data_contracts.md)
- [Storage formats specification](045_storage_formats.md)
- [Scenarios specification](030_scenarios.md)
- [Plan execution model specification](031_plan_execution_model.md)
- [Atomic Red Team executor integration specification](032_atomic_red_team_executor_integration.md)
- [Telemetry pipeline specification](040_telemetry_pipeline.md)
- [Unix log ingestion specification](044_unix_log_ingestion.md)
- [osquery integration specification](042_osquery_integration.md)
- [Normalization specification](050_normalization_ocsf.md)
- [OCSF field tiers specification](055_ocsf_field_tiers.md)
- [Detection specification](060_detection_sigma.md)
- [Sigma-to-OCSF bridge specification](065_sigma_to_ocsf_bridge.md)
- [Scoring metrics specification](070_scoring_metrics.md)
- [Reporting specification](080_reporting.md)
- [Golden datasets specification](085_golden_datasets.md)
- [Security and safety specification](090_security_safety.md)
- [Test strategy and CI specification](100_test_strategy_ci.md)
- [Operability specification](110_operability.md)
- [Configuration reference](120_config_reference.md)
- [ADR-0002 "Event identity and provenance"](../adr/ADR-0002-event-identity-and-provenance.md)
- [ADR-0003 "Redaction policy"](../adr/ADR-0003-redaction-policy.md)
- [ADR-0004 "Deployment architecture and inter-component communication"](../adr/ADR-0004-deployment-architecture-and-inter-component-communication.md)
- [ADR-0005 "Stage outcomes and failure classification"](../adr/ADR-0005-stage-outcomes-and-failure-classification.md)
- [ADR-0006 "Plan execution model"](../adr/ADR-0006-plan-execution-model.md)
- [ADR-0008 "Threat intelligence integration model"](../adr/ADR-0008-Threat-intelligence-integration-model.md)

## Changelog

| Date       | Change                                                                                 |
| ---------- | -------------------------------------------------------------------------------------- |
| 2026-01-24 | update                                                                                 |
| 2026-01-19 | Align scope with publish-gate validation, regression inputs/outputs, caches, and verbs |
| 2026-01-12 | Formatting update                                                                      |
| 2026-01-13 | Update scope to match current v0.1 spec set                                            |
