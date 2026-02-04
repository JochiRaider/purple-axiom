# Purple Axiom navigator (repo root)

This file is the top-level map for agent navigation. It routes to domain-specific indexes so agents
can find authoritative entrypoints without scanning the entire repository.

## Entrypoints (open these first)

Sort key: recommended reading order for new contributors.

- `README.md` — project overview and quickstart
- `docs/spec/SPEC_INDEX.md` — architecture and specification navigator
- `docs/contracts/CONTRACTS_INDEX.md` — JSON Schema contract navigator
- `mappings/MAPPINGS_INDEX.md` — OCSF mapping pack navigator

## Documentation indexes

| Index file                            | Domain                 | Primary purpose                                         |
| ------------------------------------- | ---------------------- | ------------------------------------------------------- |
| `docs/DOCS_INDEX.md`                  | Documentation          | Navigate general documentation (if distinct from specs) |
| `docs/adr/ADR_INDEX.md`               | Architecture decisions | Navigate ADRs for design rationale and constraints      |
| `docs/contracts/CONTRACTS_INDEX.md`   | Data contracts         | Navigate JSON Schema files for artifact validation      |
| `docs/mappings/MAPPINGS_DOC_INDEX.md` | Mapping documentation  | Navigate mapping guides and authoring references        |
| `docs/research/RESEARCH_INDEX.md`     | Research               | Navigate exploratory and non-normative research docs    |
| `docs/spec/SPEC_INDEX.md`             | Specifications         | Navigate normative specification files                  |

## Policy and style guides

| File                                     | Purpose                                           |
| ---------------------------------------- | ------------------------------------------------- |
| `docs/policy/AGENTS_POLICY.md`           | Policy for AGENTS.md authoring and agent guidance |
| `docs/MARKDOWN_STYLE_GUIDE.md`           | Markdown formatting conventions                   |
| `docs/MARKDOWN_QUICK_REFERENCE.md`       | Quick reference for common markdown patterns      |
| `docs/policy/PYTHON_STYLE_POLICY.md`     | Python code style and toolchain expectations      |
| `docs/policy/REPO_INDEX_FILES_POLICY.md` | Policy for maintaining index files                |
| `SUPPORTED_VERSIONS.md`                  | Supported versions and compatibility matrix       |

## Tests and fixtures

| File                               | Purpose       |
| ---------------------------------- | ------------- |
| `tests/fixtures/FIXTURES_INDEX.md` | Test Fixtures |

## Common tasks (fast paths)

| Need                                          | Start here                                           | Then (if needed)                                                                               |
| --------------------------------------------- | ---------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| "What is Purple Axiom?"                       | `README.md`                                          | `docs/spec/SPEC_INDEX.md` → `docs/spec/000_charter.md`                                         |
| "What specs exist?"                           | `docs/spec/SPEC_INDEX.md`                            | Individual spec files                                                                          |
| "What ADRs exist?"                            | `docs/adr/ADR_INDEX.md`                              | Individual ADR files                                                                           |
| "What schemas/contracts exist?"               | `docs/contracts/CONTRACTS_INDEX.md`                  | Individual schema files                                                                        |
| "How do I map telemetry to OCSF?"             | `mappings/MAPPINGS_INDEX.md`                         | `docs/mappings/MAPPINGS_DOC_INDEX.md`, `docs/mappings/ocsf_mapping_profile_authoring_guide.md` |
| "What mapping profiles exist for OCSF 1.7.0?" | `mappings/normalizer/ocsf/1.7.0/OCSF_1.7.0_INDEX.md` | Individual mapping profile docs                                                                |
| "What research has been done?"                | `docs/research/RESEARCH_INDEX.md`                    | Individual research docs                                                                       |
| "How should I format markdown?"               | `docs/MARKDOWN_QUICK_REFERENCE.md`                   | `docs/MARKDOWN_STYLE_GUIDE.md`                                                                 |
| "How should I write Python?"                  | `docs/policy/PYTHON_STYLE_POLICY.md`                 | —                                                                                              |
| "How should I write AGENTS.md?"               | `docs/policy/AGENTS_POLICY.md`                       | —                                                                                              |

## Key specification files (direct links)

For agents that need to jump directly to authoritative specs:

| Topic                          | File                                    |
| ------------------------------ | --------------------------------------- |
| Project charter and principles | `docs/spec/000_charter.md`              |
| Scope boundaries               | `docs/spec/010_scope.md`                |
| System architecture            | `docs/spec/020_architecture.md`         |
| Data contracts and artifacts   | `docs/spec/025_data_contracts.md`       |
| Scenario model                 | `docs/spec/030_scenarios.md`            |
| Telemetry pipeline             | `docs/spec/040_telemetry_pipeline.md`   |
| OCSF normalization             | `docs/spec/050_normalization_ocsf.md`   |
| Sigma detection                | `docs/spec/060_detection_sigma.md`      |
| Sigma-to-OCSF bridge           | `docs/spec/065_sigma_to_ocsf_bridge.md` |
| Scoring metrics                | `docs/spec/070_scoring_metrics.md`      |
| Reporting                      | `docs/spec/080_reporting.md`            |
| Configuration reference        | `docs/spec/120_config_reference.md`     |

## Key ADRs (direct links)

| Topic                         | File                                                                             |
| ----------------------------- | -------------------------------------------------------------------------------- |
| Naming and versioning         | `docs/adr/ADR-0001-project-naming-and-versioning.md`                             |
| Event identity and provenance | `docs/adr/ADR-0002-event-identity-and-provenance.md`                             |
| Redaction policy              | `docs/adr/ADR-0003-redaction-policy.md`                                          |
| Deployment architecture       | `docs/adr/ADR-0004-deployment-architecture-and-inter-component-communication.md` |
| Stage outcomes and failures   | `docs/adr/ADR-0005-stage-outcomes-and-failure-classification.md`                 |
| Plan execution model          | `docs/adr/ADR-0006-plan-execution-model.md`                                      |

## Non-goals

- This index does not enumerate leaf files (individual schemas, mapping YAMLs, etc.)
- For leaf file listings, see the domain-specific indexes
- This index does not contain behavioral instructions — see `AGENTS.md` for agent guidance

## Update rule (required)

- Update this index when adding new domain indexes or major entrypoints
- Keep this file under 200 lines
- Do not include leaf file inventories — delegate to sub-indexes
- Prefer pointers to authoritative indexes over duplicated content
- Unless stated otherwise, tables are sorted lexicographically by the first column
