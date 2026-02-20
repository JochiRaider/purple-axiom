# Agent instructions (docs/mappings/)

## Scope and exclusions

- This file applies to **`docs/mappings/*` only**.
- `docs/mappings/*` contains human-readable mapping specifications and mapping conformance
  expectations.
- This file does **not** govern changes to machine-executable mapping packs under `mappings/**`
  (those are owned by a separate agent file for `mappings/*`).

## Navigation entrypoint (required)

- Start with `docs/mappings/MAPPINGS_INDEX.md` (one-page map + "Common tasks" router).

## Mappings-only fast paths (minimal pointers)

- Mapping completeness expectations → `coverage_matrix.md`
- Mapping pack structure and authoring rules → `ocsf_mapping_profile_authoring_guide.md`
- Windows Security → OCSF 1.7.0 → `windows-security_to_ocsf_1.7.0.md`
- Sysmon → OCSF 1.7.0 → `windows-sysmon_to_ocsf_1.7.0.md`
- osquery → OCSF 1.7.0 → `osquery_to_ocsf_1.7.0.md`

## Index maintenance (required)

- Maintain `docs/mappings/MAPPINGS_INDEX.md` as a **one-page map** covering all files in this
  directory.
- When you add/rename/move/delete a file in `docs/mappings/*`, update
  `docs/mappings/MAPPINGS_INDEX.md`.
