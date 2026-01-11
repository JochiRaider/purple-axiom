<!-- docs/mappings/AGENTS.md -->

# Agent instructions (docs/mappings/*)

## Scope

This file governs work in **`docs/mappings/*` only**:

- Human-readable mapping profile specifications (per `source_type`, per OCSF version)
- Mapping conformance documentation (coverage expectations, fixture expectations)
- Mapping authoring guidance for machine-executable mapping packs

This file does **not** govern changes to the machine-executable mapping packs under `mappings/**`.
A separate agent file will cover that directory.

## Primary objective: keep the working set small (performance)

- DO NOT brute-force read every mapping doc.
- Use a navigation-first workflow:
  1. Read `docs/mappings/MAPPINGS_INDEX.md` (one-page map) to choose the correct document.
  2. Use repo search (ripgrep or equivalent) to jump to the exact section/header.
  3. Only open the minimum section(s) required to answer/edit.

## Mappings-only navigation fast paths (docs/mappings/*)

- “What coverage is required for mapping completeness?” → `coverage_matrix.md`
- “How do I author deterministic, machine-executable mapping packs?” → `ocsf_mapping_profile_authoring_guide.md`
- “Where are Windows Security mapping rules documented?” → `windows-security_to_ocsf_1.7.0.md`
- “Where are Sysmon mapping rules documented?” → `windows-sysmon_to_ocsf_1.7.0.md`
- “Where are osquery mapping rules documented?” → `osquery_to_ocsf_1.7.0.md`

## Cross-doc boundaries (avoid duplication)

- `docs/mappings/*` documents SHOULD describe mapping intent, field-level rules, and testable expectations.
- Stage-level invariants (pipeline boundaries, run bundle artifacts, CI gates, identity rules) MUST remain authoritative in:
  - `docs/spec/*` and relevant ADRs
- When a mapping doc needs a stage invariant, prefer a link to the authoritative spec/ADR section rather than duplicating prose.

## Evidence-gated edits

- If you cannot verify a fact in-repo/specs, mark it “TBD / Needs Confirmation” rather than inventing it.
- If you update an existing mapping doc, keep the diff localized and reference the exact section heading being changed.

## Normative language discipline

- Use RFC-style modals consistently: MUST / MUST NOT / SHOULD / SHOULD NOT / MAY.
- Every new MUST/MUST NOT MUST include:
  - scope (which `source_type`, which event family/class, which file),
  - observable behavior (what changes in output),
  - how to verify (fixture, golden output, or CI assertion).

## Determinism first (mapping-doc-specific)

When specifying or editing mapping behavior, prefer deterministic rules:

- Stable routing keys and stable precedence rules (no ambiguous “best effort” selection without a tie-breaker).
- Explicit canonicalization and normalization steps, written as ordered requirements.
- Explicit omission rules (when a value is not authoritative, fields MUST be absent rather than inferred).
- Stable ordering requirements for any emitted arrays or map keys if they affect hashing, comparisons, or golden fixtures.

## Fixtures and conformance coupling (docs/mappings/*)

When a change affects mapping outputs or coverage expectations:

- Update `coverage_matrix.md` if the required/optional/N/A expectations change.
- Add or update fixture and golden-output guidance in the relevant mapping doc, or link to the authoritative CI/spec section that defines fixture requirements.
- Avoid describing ad hoc test workflows. Prefer referencing the project’s CI/test strategy spec for gates and harness behavior.

## Index maintenance (required)

- Maintain `docs/mappings/MAPPINGS_INDEX.md` as a one-page map covering all files in this directory.
- When you add, rename, or delete a file in `docs/mappings/*`:
  - Update `docs/mappings/MAPPINGS_INDEX.md`.
  - If project-level doc indexes exist and are affected, call that out explicitly in the change rationale.

## Working-set discipline (authoring checklist)

Before writing or editing mapping docs:

1. Identify the `source_type` and OCSF version in scope.
2. Identify the authoritative doc in `docs/mappings/` for that `source_type`.
3. Identify the relevant `coverage_matrix.md` sections that constrain the change.
4. Define the verification hook (fixtures and golden outputs) before adding new MUST/MUST NOT language.
