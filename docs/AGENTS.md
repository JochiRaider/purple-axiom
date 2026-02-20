# Agent instructions (docs/)

## Scope

- If a docs change *requires* updating non-doc files for consistency, call it out explicitly in the
  PR/diff rationale.

## Primary objective: keep the working set small (performance)

- DO NOT brute-force read all docs.
- Use a navigation-first workflow:
  1. Start from the relevant index (below) to choose the correct authority file.
  1. Use repo search (ripgrep or equivalent) to jump to the exact section/header.
  1. Only open the minimum section(s) required to answer/edit.
- When quoting context into prompts/PRs, keep excerpts tight (prefer ≤ 80 lines).

## Navigation entrypoints (authoritative indexes)

- **Global Docs Map**: `docs/DOCS_INDEX.md`
- **Markdown Style Guide**: `docs/MARKDOWN_STYLE_GUIDE.md`
- **Markdown Quick Reference**: `docs/MARKDOWN_QUICK_REFERENCE.md`
- ADR navigation (decisions, consequences): `docs/adr/ADR_INDEX.md`
- Spec navigation (normative requirements): `docs/spec/SPEC_INDEX.md`
- Contract registry (schema catalog): `docs/contracts/index.json`
- Mapping navigation (per `source_type`): `docs/mappings/MAPPINGS_INDEX.md`

## Evidence-gated edits

- If you cannot verify a fact in-repo/specs, mark it "TBD / Needs Confirmation" rather than
  hallucinating it.
- If you update an existing doc, keep the diff localized and reference the exact section heading
  being changed.

## Normative language discipline

- Use RFC-style modals consistently: MUST / MUST NOT / SHOULD / SHOULD NOT / MAY.
- Every new MUST/MUST NOT MUST include:
  - scope (what files/components it applies to),
  - observable behavior (what changes in output or validation),
  - how to verify (fixture, golden output, CI assertion, or acceptance criteria).

## Determinism first

- Prefer deterministic identifiers, canonicalization rules, explicit ordering, and stable
  serialization.
- Where hashing/IDs are involved, follow the project’s canonical JSON requirements (RFC 8785 / JCS)
  and identity rules.
- Avoid ambiguous "best effort" rules without an explicit tie-breaker.
- Prefer explicit omission rules: when a value is not authoritative, fields MUST be absent rather
  than inferred.

## Cross-doc boundaries (avoid duplication)

- `docs/spec/*` is the normative source for system behavior and stage-level invariants.
- `docs/adr/*` records architectural decisions and rationale.
- `docs/contracts/*` defines CI-enforced schemas and data-shape contracts.
- `docs/mappings/*` documents mapping intent, field-level rules, and mapping completeness
  expectations.
- `docs/research/*` is exploratory and non-normative unless explicitly promoted elsewhere.
- When a doc needs an invariant owned by another domain, prefer linking to the authoritative file
  and section rather than duplicating prose.

## Index maintenance (required)

- If you add/rename/move a document in `docs/spec/`, update `docs/spec/SPEC_INDEX.md`.
- If you add/rename/move a document in `docs/adr/`, update `docs/adr/ADR_INDEX.md`.
- If you add/rename/remove a contract schema in `docs/contracts/`, update
  `docs/contracts/index.json`.
- If you add/rename/move a document in `docs/mappings/`, update `docs/mappings/MAPPINGS_INDEX.md`.
- If you create a new documentation category or index entrypoint, update `docs/DOCS_INDEX.md`.

## Documentation hygiene

- Preserve existing structure unless a change is necessary for correctness.
- Prefer concrete references (file + section heading) over ambiguous language.
- Do not include secrets (tokens/keys) in examples; use placeholders.
