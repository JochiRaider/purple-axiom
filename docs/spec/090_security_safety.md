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

## Definitions

- **standard long-term artifact locations**: Default-exported run-bundle paths (Tier 1 evidence +
  Tier 2 analytics) plus deterministic evidence under `runs/<run_id>/logs/` (as defined by
  ADR-0009), excluding volatile logs, `.staging/**`, and the quarantine directory.
- **logs/\*.json evidence allowlist** (normative, v0.1): The subset of schema-backed artifacts under
  `runs/<run_id>/logs/` that MUST be treated as standard long-term artifacts (included in default
  export and in `security/checksums.txt` when signing is enabled; see `025_data_contracts.md`,
  "Long-term artifact selection for checksumming").
- **quarantine directory**: `runs/<run_id>/<security.redaction.unredacted_dir>` used only when
  unredacted evidence storage is explicitly permitted (default: `runs/<run_id>/unredacted/`).
- **volatile logs**: Operator-local diagnostics excluded from default export/checksums (for example
  process stdout/stderr and any `runs/<run_id>/logs/**` content not in the allowlist above).
- **redacted-safe**: Satisfies the effective redaction policy and post-checks (see
  [ADR-0003 Redaction policy](../adr/ADR-0003-redaction-policy.md)).
- **evidence-tier artifact**: Tier 1 evidence artifacts governed by redaction/withhold/quarantine
  rules (see [Storage formats](045_storage_formats.md)).

## Core principles

- Local-first, isolated lab by default.
- No outbound calls except explicitly allowed (provisioning-time package updates, required vendor
  endpoints).
  - v0.1: "package updates" refers only to lab provisioning-time OS/toolchain maintenance. The
    runner MUST NOT self-update or install/upgrade pipeline dependencies during a run.
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
- Any run-scoped environment configuration that mutates endpoint state (for example,
  `runner.environment_config` in apply mode) MUST be explicitly enabled (default off), scoped to an
  allowlist, and recorded deterministically in run evidence.
- Orchestration tools MUST NOT have access to production networks, identities, or secrets.
- Adapter implementations (including packaged / third-party adapters) execute inside the
  orchestrator trust boundary.
  - v0.1 safe default: only built-in adapters are permitted.
  - If third-party adapters are enabled, the orchestrator MUST enforce:
    - explicit selection (no ambient discovery),
    - immutable pinning (`adapter_version` + `source_digest`), and
    - signature verification when required by `security.adapters` policy.
  - Adapter provenance for every resolved binding MUST be recorded in the run manifest (see
    `020_architecture.md` "Adapter provenance recording (v0.1)").

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

### Evaluator boundary (criteria, detection)

Evaluators process untrusted rule content (Sigma, criteria packs). They MUST be sandboxed and MUST
NOT execute arbitrary code from rule packs.

Evaluator sandbox contract (minimal, testable; normative v0.1):

- Rule packs MUST be treated as data. Parsers MUST NOT execute embedded templates, macros, or code.
- The evaluator MUST NOT invoke a shell for rule processing. Any subprocess invocation (for example
  a Sigma compiler or query backend client) MUST use an argv array (no shell expansion) and MUST
  apply bounded timeouts and output size limits.
- Network egress MUST be denied by default for evaluator execution. If rule retrieval is required,
  it MUST occur in a separate, explicitly-enabled fetch step and the retrieved content MUST be
  pinned (versioned) and hashed before evaluation.
- File system access MUST be constrained:
  - read-only: the run bundle inputs required for evaluation and the pinned rule pack directory
  - write-only: evaluator outputs under the run bundle (for example `criteria/` or `detections/`)
- Sandbox violations MUST be treated as deterministic failures (fail closed).

Evaluators SHOULD not require network access. If network access is required for rule retrieval, it
MUST be explicitly enabled and logged, and rule content MUST be pinned and hashed.

## Safe defaults

- Runs SHOULD use isolated network ranges.
- Lab assets SHOULD default to outbound egress deny.
- Run bundles MUST enforce strict file permissions.
- Secrets MUST NOT be stored in run artifacts.

### Noise and background activity generators

- Any workload/noise generator tooling (for example AD-Lab-Generator, ADTest.exe, GHOSTS) MUST
  operate on synthetic identities and synthetic credentials only. Operators MUST NOT import real
  production user data into lab noise profiles.
- Features that export plaintext credentials (for example password export options) MUST be disabled
  by default. If enabled for a controlled lab experiment, exported material MUST be treated as a
  secret and MUST NOT be included in publishable run artifacts.
- Noise generator server components (when required) SHOULD run as internal-only supporting services
  with outbound egress denied by default.

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

### Binary evidence retention

Binary artifacts (EVTX, PCAP, sidecar blobs, decoded payload extracts) are not redacted in-place by
the text redaction pipeline. When binary evidence is retained, implementations MUST follow
[ADR-0003 Redaction policy](../adr/ADR-0003-redaction-policy.md) "Binary retention requirements",
including explicit manifest labeling and export confirmation prompts.

### Enablement

Redaction application MUST be controlled by config `security.redaction.enabled`.

- When `true`, artifacts promoted to long-term storage MUST be redacted-safe.
- When `false`, the run MUST be explicitly labeled as unredacted in the run manifest and reports.

Config key map (normative):

| Key                                                    | Type    | Default                   | Meaning                                                                                                            |
| ------------------------------------------------------ | ------- | ------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| `security.redaction.enabled`                           | boolean | `true`                    | Global gate for applying redaction + redacted-safe promotion into standard long-term locations.                    |
| `security.redaction.disabled_behavior`                 | enum    | `withhold_from_long_term` | Determines handling when `security.redaction.enabled=false`: `withhold_from_long_term` or `quarantine_unredacted`. |
| `security.redaction.allow_unredacted_evidence_storage` | boolean | `false`                   | Explicit permission gate required to persist any unredacted evidence in the quarantine directory.                  |
| `security.redaction.unredacted_dir`                    | string  | `unredacted/`             | Quarantine directory relative to the run bundle root; MUST be excluded from default packaging/export.              |

### Disabled posture semantics

When `security.redaction.enabled: false`, the pipeline MUST NOT silently store unredacted evidence
in the standard long-term artifact locations.

The pipeline MUST apply one of the following deterministic behaviors, controlled by
`security.redaction.disabled_behavior`:

- `withhold_from_long_term` (default):
  - Unredacted evidence MUST NOT be persisted in the run bundle (except volatile logs as permitted
    by operability/debug policies).
  - The pipeline MUST write deterministic placeholders in standard artifact locations.
- `quarantine_unredacted`:
  - This behavior MUST be refused (fail closed) unless
    `security.redaction.allow_unredacted_evidence_storage: true`.
  - The pipeline MUST write deterministic placeholders in standard artifact locations.
  - Unredacted evidence MUST be written only under the quarantine directory
    `runs/<run_id>/<security.redaction.unredacted_dir>` (default: `runs/<run_id>/unredacted/`),
    which MUST be excluded from default packaging/export.

Redaction handling MUST be logged and surfaced in reports, including the affected artifact relative
path and handling (`withheld` or `quarantined`).

### Placeholder artifacts

When an artifact is withheld or quarantined under this spec, implementations MUST still emit a
placeholder at the standard artifact path so downstream tooling can rely on stable paths and
schemas.

Schema-aware placeholder pattern (normative):

- For contract-backed JSON artifacts (`*.json`):

  - The placeholder MUST be valid JSON and MUST validate against the artifact schema.
  - Schemas MUST allow an optional top-level `placeholder` object with the shape defined below.
  - When `placeholder` is present, the artifact MUST NOT include unredacted sensitive content
    elsewhere in the object; any required non-placeholder fields MUST use safe sentinel values only.

- For text artifacts (`*.txt`):

  - The placeholder MUST be UTF-8 text consisting only of the single-line record defined below
    (ending with `\n`).

- For asciinema cast artifacts (`*.cast`):

  - The placeholder MUST be a valid asciinema cast file (v2; JSON value per line).
  - The file MUST consist of exactly two lines (each ending with `\n`):
    1. Header: `{"version":2,"width":80,"height":24}`
    1. One output event: `[0.0,"o","<placeholder_line>\n"]`, where `<placeholder_line>` is the
       placeholder text line format defined below.

Required placeholder fields (normative):

- `reason_code` is REQUIRED and MUST be a stable `lower_snake_case` token.
- `reason_domain` is REQUIRED and MUST be a `artifact_placeholder`.
- `sha256` is REQUIRED when permitted by the effective redaction policy for the underlying content
  class; it MUST be omitted when not permitted.

Placeholder JSON object (normative, `pa.placeholder.v1`):

- `placeholder.placeholder_version` MUST be `pa.placeholder.v1`
- `placeholder.handling` MUST be `withheld` or `quarantined`
- `placeholder.reason_code` MUST be present
- `placeholder.reason_domain` MUST be present
- `placeholder.sha256` MAY be present only when permitted; format MUST be
  `sha256:<64 lowercase hex>`

Placeholder text line format (normative, `pa.placeholder.v1`):

`PA_PLACEHOLDER_V1 handling=<withheld|quarantined> reason_code=<lower_snake_case> [sha256=sha256:<64hex>]`

Hash inclusion rule (normative):

- `sha256` MUST be omitted when the effective redaction policy treats the underlying content as
  secret-containing or otherwise hash-sensitive (for example, post-check secret matches).
- `sha256` SHOULD be included when permitted to support integrity/deduplication.

Determinism requirements (normative):

- Placeholder serialization MUST be byte-for-byte deterministic given the same inputs.
- JSON placeholders MUST be serialized using RFC 8785 canonical JSON (UTF-8) to ensure stable bytes.
- Placeholders MUST NOT include timestamps, hostnames, absolute paths, or environment-specific
  values.

Quarantine mapping (normative):

- When `handling=quarantined`, the unredacted bytes MUST be written under
  `runs/<run_id>/<security.redaction.unredacted_dir>/` preserving the standard relative path (for
  example, `unredacted/runner/actions/<action_id>/requirements_evaluation.json`).

### Runner transcripts

- Executor stdout/stderr transcripts captured under `runner/` are evidence-tier artifacts and MUST
  be subject to the same redaction policy as raw telemetry.
- Terminal session recordings (for example, `runner/actions/<action_id>/terminal.cast`) are treated
  as transcript-like evidence-tier text and MUST follow the same redaction and placeholder rules.
- If transcripts or terminal recordings cannot be made redacted-safe deterministically, they MUST be
  handled as `withheld` or `quarantined` per the effective redaction posture. Implementations MUST
  write a placeholder file in the standard location conforming to "Placeholder artifacts" (including
  `reason_code`, and `sha256` only when allowed by policy).

### Requirements evaluation

Requirements evaluation may reveal tool paths, package versions, privilege context, and other
sensitive details.

Normative requirements:

- Requirements evaluation output MUST NOT include unredacted requirement details in run-scoped
  long-term artifacts. If redaction is disabled or cannot be applied deterministically, the runner
  MUST omit sensitive details or store them only in the configured quarantine directory.
- The redacted requirements evidence MUST be stored at
  `runner/actions/<action_id>/requirements_evaluation.json`.
- If the pipeline determines that `requirements_evaluation` content cannot be made redacted-safe
  deterministically (for example, non-redactable tool strings):
  - The pipeline MUST NOT store that content in the standard long-term artifact locations.
  - Implementations MAY write the unredacted content under the run's configured quarantine directory
    when quarantining is allowed by configuration (including the explicit unredacted-storage gate).
  - Otherwise, implementations MUST withhold the unredacted content (not persisted in the run
    bundle).
  - In both cases (quarantined or withheld), implementations MUST write a deterministic placeholder
    artifact at `runner/actions/<action_id>/requirements_evaluation.json` conforming to "Placeholder
    artifacts" (including required `reason_code`, and `sha256` when allowed).
- When `requirements_evaluation` content is quarantined or withheld, the run manifest and reports
  MUST disclose the affected artifact relative path and the applied handling (`withheld` or
  `quarantined`).

### Resolved inputs evidence

Resolved inputs evidence may include sensitive command fragments, paths, or environment-derived
values. This artifact is intended as evidence-tier support, not user-facing detail.

Normative requirements:

- Resolved inputs evidence MUST be written at
  `runner/actions/<action_id>/resolved_inputs_redacted.json`.

- It MUST be redacted-safe before promotion to standard long-term artifact locations.

- If the pipeline determines that `resolved_inputs_redacted` content cannot be made redacted-safe
  deterministically:

  - The pipeline MUST NOT store that content in the standard long-term artifact locations.
  - Implementations MAY write the unredacted content under the run's configured quarantine directory
    when quarantining is allowed by configuration (including the explicit unredacted-storage gate).
  - Otherwise, implementations MUST withhold the unredacted content (not persisted in the run
    bundle).
  - In both cases (quarantined or withheld), implementations MUST write a deterministic placeholder
    artifact at `runner/actions/<action_id>/resolved_inputs_redacted.json` conforming to
    "Placeholder artifacts" (including required `reason_code`, and `sha256` when allowed).

- When resolved inputs evidence content is quarantined or withheld, the run manifest and reports
  MUST disclose the affected artifact relative path and the applied handling (`withheld` or
  `quarantined`).

- Report rendering (default-safe): reports MUST NOT render resolved input values from
  `resolved_inputs_redacted.json` unless a future explicit debug-only gate is added. Reports MAY
  render `parameters.resolved_inputs_sha256` and an evidence reference for operator triage.

### Principal context

Principal identity evidence is sensitive and must avoid leaking usernames/SIDs/session identifiers
unless explicitly allowed and redacted-safe.

Normative requirements:

- The principal context output MUST be stored at `runner/principal_context.json`.
- Raw principal identifiers (usernames, SIDs, tokens) MUST NOT appear in long-term artifacts unless
  explicitly allowed by the redaction policy.
- The artifact MAY include:
  - Stable typed identifiers (for example, `kind: "user"` and a stable `principal_id` that is a hash
    or synthetic identifier)
  - An `action_principal_map[]` keyed by `action_id` and stable ids
  - A `redacted_fingerprint` field that is explicitly designated as safe by the redaction policy.
- If the pipeline determines the principal context cannot be made redacted-safe:
  - The pipeline MUST NOT store that content in the standard long-term artifact locations.
  - Implementations MAY write the unredacted content under the run's configured quarantine directory
    when quarantining is allowed by configuration (including the explicit unredacted-storage gate).
  - Otherwise, implementations MUST withhold the unredacted content (not persisted in the run
    bundle).
  - In both cases (quarantined or withheld), implementations MUST write a deterministic placeholder
    artifact at `runner/principal_context.json` conforming to "Placeholder artifacts" (including
    required `reason_code`, and `sha256` when allowed).
- When principal context is quarantined or withheld, the run manifest and reports MUST disclose the
  affected artifact relative path and the applied handling (`withheld` or `quarantined`).

### Side-effect ledger

Side-effect tracking may include filesystem paths, environment-derived details, or cleanup
operations that contain sensitive artifacts.

Normative requirements:

- The side-effect ledger MUST be stored at `runner/actions/<action_id>/side_effect_ledger.json`.
- Side-effect entries MUST avoid storing raw secrets. If a side-effect involves secret material, the
  entry MUST record `reason_domain="side_effect_ledger"` and `reason_code` only, and MAY include a
  redacted-safe `sha256` only when allowed by the effective redaction policy.
- If the pipeline determines the side-effect ledger cannot be made redacted-safe:
  - The pipeline MUST NOT store that content in the standard long-term artifact locations.
  - Implementations MAY write the unredacted content under the run's configured quarantine directory
    when quarantining is allowed by configuration (including the explicit unredacted-storage gate).
  - Otherwise, implementations MUST withhold the unredacted content (not persisted in the run
    bundle).
  - In both cases (quarantined or withheld), implementations MUST write a deterministic placeholder
    artifact at `runner/actions/<action_id>/side_effect_ledger.json` conforming to "Placeholder
    artifacts" (including required `reason_code`, and `sha256` when allowed).
- If the ledger contains raw credential material, it MUST be withheld or quarantined (never stored
  in standard long-term artifact locations).
- When side-effect ledger is quarantined or withheld, the run manifest and reports MUST disclose the
  affected artifact relative path and the applied handling (`withheld` or `quarantined`).

### State reconciliation

State reconciliation compares recorded action effects (side-effect ledger and cleanup verification)
against observed environment state to detect drift.

Guardrails:

- Default posture MUST be observe-only:
  - Observe-only mode MAY check for leftover artifacts and compare to expected cleanup actions.
  - Observe-only mode MUST NOT delete or mutate artifacts on the system.
- Destructive reconciliation (“repair”) MUST be disabled by default.
- v0.1: repair is out of scope. Implementations MUST NOT attempt destructive repair actions as part
  of reconciliation.
- If the scenario requests reconciliation policy of `repair`:
  - v0.1 behavior MUST be observe-only (checks still execute).
  - The runner MUST NOT "skip everything" solely due to the request; instead, any per-check repair
    intent MUST be blocked and recorded deterministically as `status: "skipped"` with
    `reason_code: "repair_blocked"` in the reconciliation report for that check.
  - The overall `runner.state_reconciliation` outcome SHOULD reflect the observe-only execution
    result (for example `success` if checks ran; `warn`/`failed` only for actual observe-only
    failures or safety violations).
- Any allowed repair mode (v0.2+ only) MUST:
  - Be constrained to a strict allowlist of safe operations (delete known temp files, stop known
    services).
  - Produce a deterministic plan before executing.
  - Record a before/after evidence set.
  - Fail closed if the plan cannot be proven safe.

Failure handling:

- If reconciliation observes unexpected residue, it MUST report it deterministically and SHOULD set
  the `runner.state_reconciliation` outcome to `warn` unless the residue implies safety violation.
- If a repair mode is enabled (v0.2+) and repair cannot be performed deterministically, the runner
  MUST NOT attempt repair and MUST fail closed with `reason_code=reconcile_failed`.

### Cache provenance

The run-level cache provenance artifact (`logs/cache_provenance.json`) is expected to be safe by
default, but it MUST be constrained to prevent accidental disclosure.

Normative requirements:

- Cache provenance MUST NOT contain secrets (credentials, tokens, private keys, session material).
- Cache keys MUST be non-secret opaque identifiers. Implementations SHOULD use stable hashes for
  keys rather than embedding raw inputs.
- `entries[].notes`, when present, MUST be redaction-processed under the effective redaction policy
  before writing to standard run bundle locations.
  - If `security.redaction.enabled: false`, implementations MUST either omit `entries[].notes` or
    replace them with a deterministic placeholder string rather than emitting unredacted identity-
    or path-bearing notes.
- Notes SHOULD avoid identity-bearing or environment-specific strings (example: tool paths,
  usernames) unless strictly necessary for diagnosis. Prefer stable tokens over raw paths/usernames.

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

| Date       | Change                                                                                                                |
| ---------- | --------------------------------------------------------------------------------------------------------------------- |
| 2026-01-24 | Clarify that `logs/` contains both deterministic evidence (exported/checksummed) and volatile diagnostics (excluded). |
| 2026-01-12 | Formatting update                                                                                                     |
