# Docs index

This file is a high-level navigation aid for the `docs/` directory to help agents and humans locate
authoritative information without loading the full tree.

## Entrypoints (open these first, if needed)

- `docs/spec/SPEC_INDEX.md` (normative requirements)
- `docs/contracts/CONTRACTS_INDEX.md` (schemas and contract registry)
- `docs/mappings/MAPPINGS_DOC_INDEX.md` (human mapping specs)
- `docs/adr/ADR_INDEX.md` (architectural decisions)
- `docs/research/RESEARCH_INDEX.md` (non-normative research)

## Sub-index map

| Index file                            | Domain         | Purpose                                                             |
| ------------------------------------- | -------------- | ------------------------------------------------------------------- |
| `docs/adr/ADR_INDEX.md`               | Decisions      | Context and history of architectural choices (ADRs)                 |
| `docs/contracts/CONTRACTS_INDEX.md`   | Contracts      | JSON Schemas and contract registry for validation of artifacts      |
| `docs/mappings/MAPPINGS_DOC_INDEX.md` | Mappings       | Mapping specs and coverage expectations per `source_type`           |
| `docs/research/RESEARCH_INDEX.md`     | Research       | Exploratory reports and conformance studies (non-normative)         |
| `docs/spec/SPEC_INDEX.md`             | Specifications | Normative requirements, architecture, data flows, and configuration |

## Directory Guide

- `docs/spec/`: The "source of truth" for system behavior.
  - Implementing features, fixing bugs, or verifying requirements.
- `docs/adr/`: Immutable records of decisions.
  - Understanding the "why" behind a design or proposing a fundamental change.
- `docs/contracts/`: CI-enforced data structures.
  - Modifying JSON outputs, validating data formats, or checking schema compatibility.
- `docs/mappings/`: Mapping references and completeness checklists.
  - Implementing or reviewing normalization mappings; adding CI coverage for "mapping completeness".
- `docs/research/`: Transient or exploratory documents.
  - Investigating performance experiments or reliability studies.

## Writing and Style References

- Markdown Style Guide: `docs/MARKDOWN_STYLE_GUIDE.md`
- Markdown Quick Reference: `docs/MARKDOWN_QUICK_REFERENCE.md`

## Update rule (required)

- Update this index and keep it one page.
- Do not include the agent, index or readme files.
- Prefer pointers to scoped indexes over duplicated prose.
- Unless stated otherwise, lists and tables are sorted lexicographically by path.
- The “Entrypoints” section above is intentionally sorted by recommended read order.
