<!-- docs/spec/AGENTS.md -->

# Agent instructions (docs/spec/)

## Scope and authority

- This file applies to **`docs/spec/*` only**.
- `docs/spec/*` is the **normative source** for system behavior, stage boundaries, and spec-level
  MUST/MUST NOT requirements.
- Use `docs/spec/SPEC_INDEX.md` to select the correct authoritative spec file and section before
  editing.

## Navigation entrypoint (required)

- Start with `docs/spec/SPEC_INDEX.md` (one-page map + “Common tasks” router).

## Spec-only fast paths (minimal pointers)

- Mission, vocabulary, non-goals → `000_charter.md`, `010_scope.md`
- Stage boundaries and responsibilities → `020_architecture.md`
- Run bundle artifacts and invariants → `025_data_contracts.md`
- CI gates and fixture expectations → `100_test_strategy_ci.md`
- Configuration surface and defaults → `120_config_reference.md`

## Index maintenance (required)

- Maintain `docs/spec/SPEC_INDEX.md` as a **one-page map** covering **all** spec files in this
  directory.
- When you add a new spec file, introduce a new concept, or add a new MUST/MUST NOT:
  - Update `docs/spec/SPEC_INDEX.md` to point to the authoritative spec file.
  - Prefer pointers to existing sections over duplicated prose.
