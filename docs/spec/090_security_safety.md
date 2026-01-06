<!-- docs/spec/090_security_safety.md -->
# Security and safety

Purple Axiom intentionally runs adversary emulation. The project must be safe to run in a lab and must fail closed when controls are violated.

This document defines security boundaries, safe defaults, and non-negotiable constraints.

## Core principles

- Local-first, isolated lab by default.
- No outbound calls except explicitly allowed (package updates, required vendor endpoints).
- Least privilege and explicit trust boundaries between components.
- Deterministic and auditable behavior.

## Boundaries

### Lab provider boundary
- Lab providers may require privileged credentials (hypervisor APIs, cloud APIs). Treat these as secrets and reference them, do not embed them in configs or artifacts.
- Default posture: inventory resolution only. Provisioning, mutation, or teardown actions must be explicitly enabled and logged.
- Provider credentials must be scoped to the lab environment only (no production networks, no production identities).

### Orchestrator boundary

- Orchestration tools (Caldera, Atomic) are allowed to execute only on lab assets.
- They must not have access to production networks, identities, or secrets.

### Telemetry boundary (Collector)

The OpenTelemetry Collector is a privileged component on endpoints. Hardening requirements:

- Bind network listeners to `localhost` unless remote collection is explicitly required.
- Disable unused receivers/exporters; ship only what you need.
- Treat collector config as sensitive:
  - avoid embedding secrets directly in YAML when possible
  - enforce file permissions (readable only by the service account)
  - record config hashes in the run manifest for reproducibility
- Prefer authenticated, encrypted transport when exporting off-host.

Windows-specific:
- Reading the Security event log requires elevated privileges. If running the collector as a service, use a dedicated service account with the minimum rights required to read the configured channels.
- Do not treat rendered event messages as authoritative security evidence; prefer raw/unrendered payloads to avoid locale and manifest dependence.

### Normalizer boundary

- The normalizer must not perform network enrichment by default.
- Any enrichment must be explicitly enabled and recorded in provenance.

### Evaluator boundary

- Rule execution must not allow arbitrary code execution.
- Sigma translation and query execution must be sandboxed (read-only).

## Safe defaults

- Run in isolated network ranges.
- Default deny for outbound egress from lab assets.
- Strict file permissions on run bundles.
- Do not store secrets in run artifacts.

## Redaction

The pipeline must support a configurable redaction policy for:
- credentials and tokens
- PII fields commonly present in endpoint telemetry
- large payloads (example: script blocks) when policies require truncation

Normative definition:
- The redaction policy format and “redacted-safe” definition are specified in `docs/adr/ADR-0003-redaction-policy.md`.

Enablement (option, per run):
- Redaction application MUST be controlled by config `security.redaction.enabled`.
  - When `true`, artifacts promoted to long-term storage MUST be redacted-safe.
  - When `false`, the run MUST be explicitly labeled as unredacted in the run manifest and reports.

Disabled semantics (required when `security.redaction.enabled: false`):
- The pipeline MUST NOT silently store unredacted evidence in the standard long-term artifact locations.
- The pipeline MUST choose one of the following deterministic behaviors (config-controlled):
  - Withhold-from-long-term (default): write deterministic placeholders in standard locations.
  - Quarantine-unredacted: write unredacted evidence only to a quarantined location that is excluded from default packaging/export.

Redaction MUST be logged and surfaced in reports; hashes SHOULD be retained for integrity/dedupe when fields are truncated or withheld.

Runner transcripts:
- Executor stdout/stderr transcripts captured under `runner/` are evidence-tier artifacts and must be subject to the same redaction policy as raw telemetry.
- If transcripts cannot be safely redacted, they must be withheld (record a placeholder file and a hash of the withheld content in volatile logs).

## Failure modes

- If telemetry collection is misconfigured (missing raw/unrendered mode for Windows), treat this as a run validation failure.
- If a component attempts unexpected network egress, fail the run and surface the violation in the manifest.
