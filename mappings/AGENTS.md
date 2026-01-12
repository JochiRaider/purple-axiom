<!-- mappings/AGENTS.md -->

# Agent instructions (mappings/)

## Scope

- This file applies to **`mappings/*` only** (machine-executable mapping packs and helpers).
- Human-readable mapping specifications live under **`docs/mappings/*`** and are governed by
  `docs/mappings/AGENTS.md`.

## Navigation entrypoints (required)

- Start with `mappings/MAPPINGS_INDEX.md` to find the correct pack and file to edit.
- For pack structure, semantics, and determinism requirements, follow:
  - `docs/mappings/ocsf_mapping_profile_authoring_guide.md`

## What is authoritative for what

- On-disk pack structure, allowed YAML features, deterministic parsing rules, routing semantics, and
  “mapping material boundary” → `docs/mappings/ocsf_mapping_profile_authoring_guide.md`
- Where mapping files live and what each file is for (per pack) → `mappings/MAPPINGS_INDEX.md`
- Mapping intent and field-level mapping rationale (per source) → `docs/mappings/*_to_ocsf_*.md`
- Required vs optional mapping completeness expectations → `docs/mappings/coverage_matrix.md`
- Identity/provenance requirements that the mappings must satisfy → relevant ADRs/specs referenced
  by the authoring guide (do not duplicate them into mapping YAML)

## Change protocol (keep changes local and verifiable)

- Prefer edits that stay within a single pack directory under
  `mappings/normalizer/ocsf/<version>/<source_pack_id>/`.
- Do not introduce new YAML constructs or “helper conventions” unless they are defined in the
  authoring guide.
- When adding a new pack, new route, or new class map:
  - Update `mappings/MAPPINGS_INDEX.md` (one-page map).
  - Ensure the pack remains self-contained per the authoring guide’s mapping material boundary.
  - Ensure the change is testable via the project’s existing fixture/golden harness (see CI/test
    strategy spec).

## Index maintenance (required)

- When you add/rename/move/delete mapping packs or mapping files under `mappings/*`, update
  `mappings/MAPPINGS_INDEX.md` (keep it one page and pointer-style).
