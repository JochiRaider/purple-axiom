<!-- docs/AGENTS.md -->
# Agent instructions (docs/*)

## Scope
- If a docs change *requires* updating non-doc files for consistency, call it out explicitly in the PR/diff rationale.

## Working set discipline (performance)
- DO NOT brute-force read all docs. Use a navigation-first workflow:
  1) Start from the relevant index (below).
  2) Use repo search (ripgrep or equivalent) to jump to the exact section/header.
  3) Open only the minimum sections required to perform the change.
- When quoting context into prompts/PRs, keep excerpts tight (prefer ≤ 80 lines).

## Navigation entrypoints (authoritative indexes)
- ADR navigation (decisions, consequences): `docs/adr/ADR_INDEX.md`
- Spec navigation (normative requirements): `docs/spec/SPEC_INDEX.md`
- Contract registry (schema catalog): `docs/contracts/index.json`

## Index maintenance (required)
- If you add/rename/move a document in `docs/spec/`, update `docs/spec/SPEC_INDEX.md`.
- If you add a new ADR in `docs/adr/`, update `docs/adr/ADR_INDEX.md`.
- If you add/rename/remove a contract schema in `docs/contracts/`, update `docs/contracts/index.json`.

## Documentation hygiene
- Preserve existing structure unless a change is necessary for correctness.
- Prefer concrete references (file + section heading) over ambiguous language.