<!-- docs/DOCS_INDEX.md -->

# Documentation Map

This file provides a high-level navigation aid for the `docs/` directory to help agents and humans
locate authoritative information.

## Primary Indexes (Start Here)

| Domain             | Index File                        | Purpose                                                                  |
| :----------------- | :-------------------------------- | :----------------------------------------------------------------------- |
| **Specifications** | `docs/spec/SPEC_INDEX.md`         | **Normative requirements**, architecture, data flows, and configuration. |
| **Decisions**      | `docs/adr/ADR_INDEX.md`           | **Context and history** of architectural choices (ADRs).                 |
| **Contracts**      | `docs/contracts/index.json`       | **JSON Schemas** for validation of artifacts (e.g., manifest, events).   |
| **Mappings**       | `docs/mappings/MAPPINGS_INDEX.md` | **Mapping specs** and coverage expectations per `source_type`.           |
| **Research**       | `docs/research/RESEARCH_INDEX.md` | **Exploratory reports** and conformance studies (non-normative).          |

## Directory Guide

- **`docs/spec/`**: The "source of truth" for system behavior.
  - *Read when:* Implementing features, fixing bugs, or verifying requirements.
- **`docs/adr/`**: Immutable records of decisions.
  - *Read when:* Understanding the "why" behind a design or proposing a fundamental change.
- **`docs/contracts/`**: CI-enforced data structures.
  - *Read when:* Modifying JSON outputs, validating data formats, or checking schema compatibility.
- **`docs/mappings/`**: Mapping references and completeness checklists.
  - *Read when:* Implementing or reviewing normalization mappings; adding CI coverage for “mapping
    completeness”.
- **`docs/research/`**: Transient or exploratory documents.
  - *Read when:* Investigating performance experiments or reliability studies.

## Writing and Style References

- **Markdown Style Guide**: `docs/MARKDOWN_STYLE_GUIDE.md`
- **Markdown Quick Reference**: `docs/MARKDOWN_QUICK_REFERENCE.md`

## Agent Guidelines Hierarchy

- **Global/Repo-wide**: `AGENTS.md` (Root)
- **Documentation**: `docs/AGENTS.md` (This directory)
  - **Specs**: `docs/spec/AGENTS.md`
  - **ADRs**: `docs/adr/AGENTS.md`
  - **Contracts**: `docs/contracts/AGENTS.md`
  - **Mappings**: `docs/mappings/AGENTS.md`
