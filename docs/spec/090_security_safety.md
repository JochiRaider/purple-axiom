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

### Synthetic correlation marker

Synthetic correlation markers are explicitly non-secret identifiers emitted to correlate synthetic
runner activity end-to-end. They are intended to be safe to display in reports.

Normative requirements:

- Marker values MUST NOT contain secrets, credentials, or token-like material.
- Marker values MUST be constrained to a safe, bounded character set:
  - Marker values MUST match regex `^[a-z0-9:._-]{1,256}$` (ASCII only).
  - Marker values MUST NOT contain whitespace or control characters.
- Marker values MUST be bounded in length:
  - Marker values MUST be at most 256 characters.
- Implementations MUST validate marker values against these constraints before emission. Invalid
  marker values MUST NOT be emitted.

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

### Requirements evaluation

The per-action requirements evaluation artifact
(`runner/actions/<action_id>/requirements_evaluation.json`) is an evidence-tier artifact and MUST be
treated as sensitive by default.

Rationale: requirements evaluation may reveal over-specific environment details (example: exact tool
versions, binary paths, OS build strings, installed capability inventory) that are not necessary for
most reports and may increase sharing risk.

Normative requirements:

- The pipeline MUST apply the effective redaction policy to requirements evaluation contents before
  writing the artifact to standard run bundle locations.
- The artifact MUST redact secrets (tokens, passwords, private keys, bearer credentials) and other
  redaction policy matches deterministically.
- If the pipeline determines that the requirements evaluation content cannot be made redacted-safe
  deterministically (example: it contains over-specific environment details that must be withheld),
  it MUST NOT store that content in standard long-term artifact locations.
  - Implementations MAY quarantine the unredacted content under the run's configured quarantine
    directory (default: `runs/<run_id>/unredacted/`) when quarantining is allowed by configuration.
  - Otherwise, implementations MUST withhold the unredacted content and write a deterministic
    placeholder at `runner/actions/<action_id>/requirements_evaluation.json`.
- When requirements evaluation content is quarantined or withheld, the run manifest and reports MUST
  disclose the affected artifact relative path and the applied handling (withheld or quarantined).

### Side-effect ledger

The per-action side-effect ledger (`runner/actions/<action_id>/side_effect_ledger.json`) is an
evidence-tier artifact and MUST be treated as potentially sensitive.

Normative requirements:

- The pipeline MUST apply the effective redaction policy to ledger contents before writing the
  ledger to standard run bundle locations.
- The ledger MUST redact secrets (tokens, passwords, private keys, bearer credentials) and other
  redaction policy matches deterministically.
- If the pipeline determines that the ledger contains raw credential material that cannot be made
  redacted-safe deterministically, it MUST NOT store that ledger content in standard long-term
  artifact locations.
  - Implementations MAY quarantine the unredacted ledger content under the run's configured
    quarantine directory (default: `runs/<run_id>/unredacted/`) when quarantining is allowed by
    configuration.
  - Otherwise, implementations MUST withhold the unredacted content and write a deterministic
    placeholder at `runner/actions/<action_id>/side_effect_ledger.json`.
- When ledger content is quarantined or withheld, the run manifest and reports MUST disclose the
  affected artifact relative path and the applied handling (withheld or quarantined).

### State reconciliation

State reconciliation compares recorded action effects (side-effect ledger and cleanup verification)
against observed environment state to detect drift.

Guardrails (normative):

- Default posture MUST be observe-only. Reconciliation probes MUST be read-only and MUST NOT mutate
  target assets.
- Destructive reconciliation (repair) MUST be disabled by default.
  - v0.1: repair is out of scope; implementations MUST NOT attempt destructive repair actions as
    part of reconciliation.
- If a scenario requests a reconciliation policy of `repair` (see the scenario model), the runner
  MUST refuse to run reconciliation in repair mode unless an explicit global configuration gate is
  enabled. The gate MUST be defined in the configuration reference before repair is supported.
- Allowlist constraints (for any future repair-capable mode):
  - A repair attempt MUST be limited to an explicit allowlist of reconciliation items derived from
    the run bundle (for example by `check_id` and/or `ledger_seq`).
  - Repair MUST NOT discover or enumerate targets beyond what is explicitly recorded in the
    side-effect ledger and/or cleanup verification results for that action.
  - Repair MUST be scoped to the action's resolved `target_asset_id` (cross-asset mutation is
    prohibited).
- Fail-closed semantics:
  - If the runner cannot prove a deterministic, bounded, and allowlisted repair plan for an item, it
    MUST NOT attempt repair and MUST fail closed for reconciliation (record
    `runner.state_reconciliation` as failed with `reason_code=reconcile_failed`).
  - When reconciliation fails closed, the runner MUST still write a reconciliation report with
    `status=unknown` or `status=skipped` items, and MUST include a stable `reason_code` per item
    explaining the refusal.

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
