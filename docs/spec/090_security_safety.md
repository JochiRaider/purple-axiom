---
title: Security and safety
description: Defines security boundaries, safe defaults, redaction posture, and fail-closed constraints for Purple Axiom.
status: draft
category: spec
tags: [security, safety, redaction]
related:
  - 040_telemetry_pipeline.md
  - 025_data_contracts.md
  - 120_config_reference.md
  - ../adr/ADR-0003-redaction-policy.md
---

# Security and safety

Purple Axiom intentionally runs adversary emulation. The project MUST be safe to run in a lab and
MUST fail closed when controls are violated.

This document defines security boundaries, safe defaults, and non-negotiable constraints.

## Overview

**Summary**: Purple Axiom MUST enforce explicit trust boundaries between components, default to
isolation and egress-deny posture, and apply deterministic redaction and artifact-handling rules
that prevent accidental long-term storage of unredacted evidence.

Key constraints:

- Purple Axiom MUST be local-first and lab-isolated by default.
- Purple Axiom MUST deny unexpected network egress by default and treat violations as run-fatal.
- Privileged components (for example, the OpenTelemetry Collector on endpoints) MUST be hardened and
  minimized.
- Evidence artifacts (telemetry and transcripts) MUST follow the configured redaction posture, with
  deterministic withheld/quarantine semantics when redaction is disabled.

Scenario safety interaction (normative):

- Scenario-level network intent is expressed by `scenario.safety.allow_network` (see the
  [scenario model](030_scenarios.md)).
- Enforcement of outbound egress posture MUST be performed at the lab boundary by the lab provider
  or equivalent lab controls. The runner MUST NOT be treated as a sufficient isolation mechanism.
- The effective outbound policy is the logical AND of `scenario.safety.allow_network` and
  `security.network.allow_outbound` (see the [configuration reference](120_config_reference.md)).

## Core principles

- Local-first, isolated lab by default.
- No outbound calls except explicitly allowed (package updates, required vendor endpoints).
- Least privilege and explicit trust boundaries between components.
- Deterministic and auditable behavior.

## Boundaries

### Lab provider boundary

- Lab providers MAY require privileged credentials (hypervisor APIs, cloud APIs). Implementations
  MUST treat these as secrets and MUST reference them. Implementations MUST NOT embed secrets in
  configs or artifacts.
- Default posture MUST be inventory resolution only. Provisioning, mutation, or teardown actions
  MUST be explicitly enabled and logged.
- Provider credentials MUST be scoped to the lab environment only (no production networks, no
  production identities).

### Orchestrator boundary

- Orchestration tools (Caldera, Atomic) MUST be allowed to execute only on lab assets.
- Orchestration tools MUST NOT have access to production networks, identities, or secrets.

### Telemetry boundary (collector)

The OpenTelemetry Collector is a privileged component on endpoints. Implementations MUST satisfy
these hardening requirements:

- Network listeners MUST bind to `localhost` unless remote collection is explicitly required.
- Unused receivers/exporters MUST be disabled. Deployments MUST ship only what is needed.
- Collector configuration MUST be treated as sensitive:
  - Secrets SHOULD be avoided in YAML when possible.
  - File permissions MUST be enforced so the config is readable only by the service account.
  - Config hashes MUST be recorded in the run manifest for reproducibility.
- Off-host export SHOULD use authenticated, encrypted transport.

Windows-specific requirements:

- Reading the Security event log requires elevated privileges. If running the collector as a
  service, deployments MUST use a dedicated service account with the minimum rights required to read
  the configured channels.
- Rendered event messages MUST NOT be treated as authoritative security evidence. Implementations
  SHOULD prefer raw, unrendered payloads to avoid locale and manifest dependence.

### Normalizer boundary

- The normalizer MUST NOT perform network enrichment by default.
- Any enrichment MUST be explicitly enabled and MUST be recorded in provenance.

### Evaluator boundary

- Rule execution MUST NOT allow arbitrary code execution.
- Sigma translation and query execution MUST be sandboxed and read-only.

## Safe defaults

- Runs SHOULD use isolated network ranges.
- Lab assets SHOULD default to outbound egress deny.
- Run bundles MUST enforce strict file permissions.
- Secrets MUST NOT be stored in run artifacts.

## Secrets

Purple Axiom configuration MUST reference secrets rather than embedding them.

Normative requirements:

- Config keys ending in `_ref` MUST use a secret reference string as defined in
  [configuration reference](120_config_reference.md) under "Secret reference strings".
- Implementations MUST resolve secrets at runtime and MUST NOT write resolved secret values into run
  bundles, logs, or reports.
- If `security.secrets.provider: custom` is used, implementations MUST enforce the custom provider
  execution requirements:
  - execute the provider directly (no shell),
  - enforce a bounded timeout and bounded stdout size, and
  - treat provider stdout/stderr as sensitive.
- If secret resolution fails for any required secret, the pipeline MUST fail closed.

## Redaction

The pipeline MUST support a configurable redaction policy for:

- credentials and tokens
- PII fields commonly present in endpoint telemetry
- large payloads (example: script blocks) when policies require truncation

### Policy definition

The redaction policy format and the definition of “redacted-safe” are specified in
[ADR-0003 Redaction policy](../adr/ADR-0003-redaction-policy.md).

### Enablement

Redaction application MUST be controlled by config `security.redaction.enabled`.

- When `true`, artifacts promoted to long-term storage MUST be redacted-safe.
- When `false`, the run MUST be explicitly labeled as unredacted in the run manifest and reports.

### Disabled posture semantics

When `security.redaction.enabled: false`, the pipeline MUST NOT silently store unredacted evidence
in the standard long-term artifact locations.

The pipeline MUST choose one of the following deterministic behaviors (config-controlled):

- Withhold-from-long-term (default): write deterministic placeholders in standard locations.
- Quarantine-unredacted: write unredacted evidence only to a quarantined location that is excluded
  from default packaging/export.

Redaction MUST be logged and surfaced in reports. Hashes SHOULD be retained for integrity and
deduplication when fields are truncated or withheld.

### Runner transcripts

Executor stdout/stderr transcripts captured under `runner/` are evidence-tier artifacts and MUST be
subject to the same redaction policy as raw telemetry.

If transcripts cannot be safely redacted, they MUST be withheld. Implementations MUST record a
placeholder file and a hash of the withheld content in volatile logs.

## Failure modes

- If telemetry collection is misconfigured (example: missing raw/unrendered mode for Windows), the
  pipeline MUST treat this as a run validation failure.
- If a component attempts unexpected network egress, the pipeline MUST fail the run and MUST surface
  the violation in the run manifest.

## References

- [Telemetry pipeline specification](040_telemetry_pipeline.md)
- [Data contracts specification](025_data_contracts.md)
- [Configuration reference](120_config_reference.md)
- [Redaction policy ADR](../adr/ADR-0003-redaction-policy.md)

## Changelog

| Date       | Change            |
| ---------- | ----------------- |
| 2026-01-12 | Formatting update |
