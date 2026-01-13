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

## Overview

Purple Axiom v0.1 focuses on deterministic, local-first execution with a fixed stage pipeline and
contract-backed artifacts. The scope centers on Atomic Red Team-based scenario execution,
endpoint-first telemetry capture, OCSF normalization, validation, detection, scoring, and reporting.
Capabilities that require distributed control planes, mandatory network sensors, or multi-scenario
orchestration are intentionally out of scope.

## Scope

This document covers:

- In-scope capabilities and contracts for v0.1 execution.
- Reserved or placeholder contracts explicitly deferred beyond v0.1.
- Explicit non-goals and operating assumptions that constrain implementation.

This document does NOT cover:

- Detailed stage responsibilities (see the
  [system architecture specification](020_architecture.md)).
- Configuration surface area (see the [configuration reference](120_config_reference.md)).
- Safety, security, and operability requirements (see the
  [security and safety specification](090_security_safety.md)).

## In scope for v0.1

- One-shot, local-first run execution on a single run host.
  - Core stages coordinate via filesystem artifacts in `runs/<run_id>/`.
  - Core stages do not require service-to-service RPC for coordination in v0.1.
- A fixed, staged pipeline with stable stage identifiers and stage-scoped outputs:
  - `lab_provider`, `runner`, `telemetry`, `normalization`, `validation`, `detection`, `scoring`,
    `reporting`, and optional `signing`.
- Contract-backed run bundles:
  - A manifest-driven run bundle layout, with deterministic hashing and provenance fields.
  - Publish-gate contract validation for contract-backed artifacts, with deterministic validation
    error ordering.
- Pluggable lab inventory resolution via a lab provider interface:
  - Manual lab definitions are supported.
  - Provider-derived inventory is supported via adapter parsing and deterministic canonicalization.
  - A deterministic `lab_inventory_snapshot.json` is recorded per run for reproducibility and
    diffability.
- Scenario execution (runner):
  - v0.1 supports **Atomic Test Plan** scenarios.
  - The runner emits a deterministic ground truth timeline and per-action evidence artifacts.
  - For `engine = "atomic"`, the runner conforms to the Atomic execution integration contract,
    including deterministic YAML parsing, resolved input determinism, transcript capture, cleanup
    invocation, and cleanup verification.
- Telemetry collection from lab assets (endpoint-first):
  - OpenTelemetry Collector-based capture is the normative path for endpoint telemetry.
  - Windows Event Log collection in raw, unrendered mode is a v0.1 fidelity requirement, validated
    by a runtime canary.
  - osquery is supported as an optional endpoint telemetry source with a defined input format and
    routing expectations.
  - Telemetry validation includes required runtime canaries and records deterministic evidence
    pointers into run logs.
- Normalization into OCSF:
  - Normalized events satisfy the required envelope and provenance rules.
  - Deterministic event identity and provenance rules are applied during normalization.
  - The pipeline records mapping coverage and supports tiered expectations (Core vs Extended) for
    field presence and reporting.
- Validation against expected telemetry (criteria packs) and cleanup verification:
  - Criteria pack snapshotting and deterministic selection (when enabled).
  - Criteria evaluation emits per-action results, including deterministic `skipped` reasons when an
    action cannot be evaluated under configured policy.
  - Cleanup verification outputs are first-class, contract-backed artifacts.
- Detection evaluation and scoring:
  - Sigma-based detection evaluation is in scope via a Sigma-to-OCSF bridge and deterministic
    executability classification.
  - Scoring joins ground truth, validation outputs, and detection outputs into a machine-readable
    run summary.
  - Quality gates that downgrade a run (for example normalization coverage gates) are expressed as
    deterministic stage outcomes and reason codes.
- Reporting:
  - Human-readable reporting derived from machine-readable artifacts (for example the scoring
    summary), plus machine-readable report artifacts intended for downstream automation.
- Security, safety, and operability guardrails that make unattended continuous runs viable:
  - Redaction posture and deterministic redaction policy application for evidence artifacts.
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
- Multi-scenario runs:
  - v0.1 is single-scenario per run bundle. Multi-scenario manifests and multi-scenario plan
    execution are reserved for a future release.

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
- Full SIEM replacement or enterprise ingestion defaults:
  - Purple Axiom produces run bundles and evaluation artifacts.
  - External SIEM ingestion is optional and out of scope as a required capability.
- Production deployment guidance for hostile or multi-tenant environments.
- Exploit development, weaponization, destructive testing, or persistence-focused operations.
- Network or threat intelligence enrichment that requires outbound network access by default.
- A comprehensive UI or SaaS service. Optional packaging (for example Docker Compose) is permitted
  as an installation convenience, but must not change stage semantics or determinism guarantees.

## Operating assumptions

- Runs occur in an isolated lab environment, local-first by default.
- Scenario payloads emphasize detectability validation, not stealth or permanence.
- Enforcement of outbound egress posture is performed at the lab boundary by the lab provider or
  equivalent lab controls. Runner-side controls may be defense-in-depth only.
- When outbound egress is denied by effective policy, telemetry validation performs a deterministic
  egress canary check and treats an observed violation as run-fatal under default policy.
- Configurations, schema references, and contract validation are local-only and deterministic:
  - Schema `$ref` resolution does not fetch remote references during validation.
  - A run is reproducible by inspecting the run bundle and pinned inputs, not by consulting mutable
    external state.

## Key decisions

- v0.1 focuses on single-host, one-shot execution with filesystem-coordinated stages.
- Atomic Red Team scenarios are the only supported plan type for v0.1.
- Endpoint telemetry capture and OCSF normalization are the normative ingestion path for v0.1.

## References

- [Charter specification](000_charter.md)
- [Data contracts specification](025_data_contracts.md)
- [Scenarios specification](030_scenarios.md)
- [Atomic Red Team executor integration specification](032_atomic_red_team_executor_integration.md)
- [Telemetry pipeline specification](040_telemetry_pipeline.md)
- [OCSF field tiers specification](055_ocsf_field_tiers.md)
- [Scoring metrics specification](070_scoring_metrics.md)
- [Security and safety specification](090_security_safety.md)
- [Test strategy and CI specification](100_test_strategy_ci.md)
- [Operability specification](110_operability.md)
- [Configuration reference](120_config_reference.md)
- [ADR-0002 "Event identity and provenance"](../adr/ADR-0002-event-identity-and-provenance.md)
- [ADR-0003 "Redaction policy"](../adr/ADR-0003-redaction-policy.md)
- [ADR-0004 "Deployment architecture and inter-component communication"](../adr/ADR-0004-deployment-architecture-and-inter-component-communication.md)
- [ADR-0005 "Stage outcomes and failure classification"](../adr/ADR-0005-stage-outcomes-and-failure-classification.md)

## Changelog

| Date       | Change                                      |
| ---------- | ------------------------------------------- |
| 2026-01-12 | Formatting update                           |
| 2026-01-13 | Update scope to match current v0.1 spec set |
