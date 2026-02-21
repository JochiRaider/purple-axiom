---
title: 'ADR-0009: Run export policy and log classification'
description: Clarifies deterministic evidence vs volatile diagnostics under runs/<run_id>/logs and defines default export + signing/checksum scope.
status: draft
category: adr
---

# ADR-0009: Run export policy and log classification

## Context

Multiple v0.1 specifications currently mix two different interpretations of `runs/<run_id>/logs/`:

- Some documents treat `logs/**` as **volatile** and therefore excluded from default exports and
  signing/checksums.
- Other documents require specific `logs/` artifacts (for example `logs/health.json`,
  `logs/telemetry_validation.json`, counters, cache provenance, and inventory snapshots) as
  **deterministic evidence** used for run status derivation, CI gating, and reproducible triage.

This inconsistency creates two concrete problems:

1. **Reproducibility and integrity gaps**: if `logs/**` is excluded wholesale, required run-critical
   evidence is not protected by signing/checksums and may be dropped from exports.
1. **Safety gaps**: if `logs/**` is exported wholesale, unstructured logs and runtime state may leak
   sensitive environment-specific strings or operational details.

We need a deterministic, testable policy that is both reproducible and safe-by-default.

## Decision

### 1. `logs/` is a mixed directory

`runs/<run_id>/logs/` is intentionally mixed and MUST be treated as two classes of artifacts:

- **Deterministic evidence logs**: small, structured artifacts that are required for
  reproducibility, CI gating, and deterministic failure triage.
- **Volatile diagnostics**: unstructured logs and runtime state that are not required for
  reproducibility and may be sensitive.

Classification is file-level and MUST NOT be inferred solely from the parent directory name.

### 2. Fail-closed default for unknown `logs/` artifacts

Fail-closed rule (normative):

- Any artifact under `runs/<run_id>/logs/` that is not explicitly classified as deterministic
  evidence in this ADR (or an updated Tier 0 taxonomy) MUST be treated as volatile diagnostics.

### 3. Deterministic evidence logs allowlist (normative)

The following run-relative paths are deterministic evidence logs:

- `logs/health.json`
- `logs/telemetry_validation.json` (when telemetry validation is enabled)
- `logs/counters.json`
- `logs/cache_provenance.json` (when caching is enabled)
- `logs/lab_inventory_snapshot.json`
- `logs/lab_provider_connectivity.json` (optional; when implemented)
- `logs/contract_validation/**` (publish-gate contract validation reports)

Deterministic evidence logs MUST satisfy:

- MUST be redaction-safe by construction (MUST NOT contain plaintext secrets).
- MUST be eligible for default export.
- MUST be eligible for signing/checksum scope.

### 4. Volatile diagnostics exclusions (normative)

The following run-relative paths are volatile diagnostics and MUST NOT be included in default export
or signing/checksum scope:

- `logs/run.log`
- `logs/warnings.jsonl`
- `logs/eps_baseline.json`
- `logs/telemetry_checkpoints/**`
- `logs/dedupe_index/**`
- `logs/scratch/**`
- any other `logs/**` path not on the deterministic evidence allowlist

### 5. Default export behavior (normative)

When an implementation produces an export bundle (for example via an operator export workflow), the
default export set MUST implement the "default export profile (v0.1)" defined in Section 6.

At minimum, the default export set MUST:

- include all deterministic evidence logs (Section 3) that exist for the run, and
- exclude all volatile diagnostics (Section 4),
- exclude `.staging/**`, and
- exclude the quarantine directory (unless explicitly requested and permitted).

### 6. Default export profile (v0.1) (normative)

For v0.1, the canonical default export profile is the "minimal reproducibility export" defined in
this section. All components that package runs for sharing or archival MUST treat this profile as
the default when the operator does not explicitly select a different profile.

The default export profile (v0.1) MUST include:

- all deterministic evidence logs (Section 3) that exist for the run, and
- the following non-log run-bundle paths (run-relative), when present:
  - `manifest.json`
  - `inputs/**`
  - `ground_truth.jsonl`
  - `runner/**`
  - `raw/**` (when raw preservation is enabled; `telemetry.raw_preservation.enabled=true`)
  - `normalized/**`
  - `criteria/**`
  - `bridge/**`
  - `detections/**`
  - `scoring/**`
  - `report/**`
  - `security/**` (when signing is enabled; at minimum `security/checksums.txt`,
    `security/signature.ed25519`, and `security/public_key.ed25519`)

The default export profile (v0.1) MUST NOT include:

- volatile diagnostics under `logs/` (Section 4),
- `.staging/**`,
- quarantine directory contents (`<security.redaction.unredacted_dir>/**`) unless explicitly
  requested and permitted, or
- `raw_parquet/**`.

`raw_parquet/**` is a non-long-term operational store used for pipeline operation (telemetry ->
normalization) and local debugging. It MUST be excluded from the v0.1 default export profile and
from signing/checksum scope.

### 7. Signing/checksum scope (normative)

When signing is enabled, `security/checksums.txt` scope MUST align to the default export profile
(v0.1) in Section 6:

- Deterministic evidence logs (Section 3) MUST be included.
- Volatile diagnostics (Section 4) MUST be excluded.
- `raw_parquet/**`, `.staging/**`, and `<security.redaction.unredacted_dir>/**` MUST be excluded.

Implementations MUST NOT implement this by excluding `runs/<run_id>/logs/**` wholesale; selection
MUST follow the file-level classification in this ADR.

## Consequences

- `logs/` is no longer treated as uniformly volatile. Some `logs/` artifacts are elevated to
  deterministic evidence and are covered by export and signing.
- Volatile diagnostics remain available for local debugging and via artifact reads, but are not
  bundled by default for safety.

## Verification (normative)

CI MUST include regression coverage that asserts:

- deterministic evidence log paths are present in exports/checksums,
- volatile diagnostics paths are absent from exports/checksums, and
- `raw_parquet/**` is absent from exports/checksums.

See: `100_test_strategy_ci.md` → `Export and checksums scope` and the required
`export_scope_logs_classification` fixture set.

| Date       | Change |
| ---------- | ------ |
| 2026-01-24 | new    |
