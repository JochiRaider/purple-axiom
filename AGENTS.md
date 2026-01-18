# AGENTS (repo root)

## Operating rules

- Do not invent repository behavior, APIs, file paths, or conventions — verify in-repo first
- Keep changes small and local; avoid drive-by refactors
- Evidence-gated changes: cite authoritative source (spec, ADR, test) before modifying behavior
- Deterministic, reviewable outputs: preserve stable ordering in lists and tables

## How to validate changes

### Fast checks (run before finalizing)

```bash
# Python formatting and linting (if Python tooling exists)
uv run ruff check .
uv run ruff format --check .

# Type checking
uv run mypy .
```

### Full checks (CI-equivalent)

```bash
# Full test suite
uv run pytest

# Schema validation (if applicable)
uv run python -m tools.validate_schemas
```

### Notes

- Formatting/linting/typing/testing MUST be tool-driven — do not hand-format beyond what the
  formatter produces
- When Python tooling exists in-repo, commands SHOULD be executed via `uv run <tool>` to ensure
  the intended environment is used
- If a change affects specs/docs, ensure formatting and link/path references remain correct

## Repository navigation

Start by reading these index files to locate authoritative sources:

- **Root index**: `ROOT_INDEX.md` — top-level navigator across all domains
- **Specs**: `SPEC_INDEX.md` — architecture and specification entrypoints
- **ADRs**: `ADR_INDEX.md` — architecture decision records
- **Contracts**: `CONTRACTS_INDEX.md` — JSON Schema contracts
- **Mappings**: `MAPPINGS_INDEX.md` — OCSF mapping pack entrypoints
- **Mapping docs**: `MAPPINGS_DOC_INDEX.md` — mapping documentation and guides
- **Research**: `RESEARCH_INDEX.md` — research and exploratory documents

## Change discipline

- Make minimal diffs; avoid cosmetic changes outside the scope of the request
- Preserve deterministic ordering — lists and tables are sorted lexicographically by path unless
  explicitly stated otherwise
- Cite authoritative sources before changing behavior; if missing, add a TODO and bound the change
- Do not modify `*_INDEX.md` files directly unless the change adds/removes/renames indexed content

## Escalation

- **When instructions conflict**: prefer the most specific (closest to working directory)
- **When context is missing**: open the authoritative spec or ADR before proceeding
- **When unsure**: minimize assumptions, keep changes bounded, and note uncertainty in output
- **When a change is ambiguous**: prefer read-only analysis over speculative edits