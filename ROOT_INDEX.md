# Purple Axiom navigator (repo root)

This file is the top-level map for agent navigation. It routes to domain-specific indexes so agents
can find authoritative entrypoints without scanning the entire repository.

## Entrypoints (open these first)

Sort key: recommended reading order for new contributors.

- `README.md` — project overview and quickstart
- `SPEC_INDEX.md` — architecture and specification navigator
- `CONTRACTS_INDEX.md` — JSON Schema contract navigator
- `MAPPINGS_INDEX.md` — OCSF mapping pack navigator

## Domain indexes

| Index file | Domain | Primary purpose |
| ---------- | ------ | --------------- |
| `ADR_INDEX.md` | Architecture decisions | Navigate ADRs for design rationale and constraints |
| `CONTRACTS_INDEX.md` | Data contracts | Navigate JSON Schema files for artifact validation |
| `DOCS_INDEX.md` | Documentation | Navigate general documentation (if distinct from specs) |
| `MAPPINGS_DOC_INDEX.md` | Mapping documentation | Navigate mapping guides and authoring references |
| `MAPPINGS_INDEX.md` | Mapping packs | Navigate OCSF mapping pack entrypoints |
| `OCSF_1_7_0_INDEX.md` | OCSF 1.7.0 | Navigate OCSF 1.7.0-specific mapping files |
| `RESEARCH_INDEX.md` | Research | Navigate exploratory and non-normative research docs |
| `SPEC_INDEX.md` | Specifications | Navigate normative specification files |

## Policy and style guides

| File | Purpose |
| ---- | ------- |
| `AGENTS_POLICY.md` | Policy for AGENTS.md authoring and agent guidance |
| `MARKDOWN_STYLE_GUIDE.md` | Markdown formatting conventions |
| `MARKDOWN_QUICK_REFERENCE.md` | Quick reference for common markdown patterns |
| `PYTHON_STYLE_POLICY.md` | Python code style and toolchain expectations |
| `REPO_INDEX_FILES_POLICY.md` | Policy for maintaining index files |
| `SUPPORTED_VERSIONS.md` | Supported versions and compatibility matrix |

## Common tasks (fast paths)

| Need | Start here | Then (if needed) |
| ---- | ---------- | ---------------- |
| "What is Purple Axiom?" | `README.md` | `SPEC_INDEX.md` → `000_charter.md` |
| "What specs exist?" | `SPEC_INDEX.md` | Individual spec files |
| "What ADRs exist?" | `ADR_INDEX.md` | Individual ADR files |
| "What schemas/contracts exist?" | `CONTRACTS_INDEX.md` | Individual schema files |
| "How do I map telemetry to OCSF?" | `MAPPINGS_INDEX.md` | `MAPPINGS_DOC_INDEX.md`, `ocsf_mapping_profile_authoring_guide.md` |
| "What mapping profiles exist for OCSF 1.7.0?" | `OCSF_1_7_0_INDEX.md` | Individual mapping profile docs |
| "What research has been done?" | `RESEARCH_INDEX.md` | Individual research docs |
| "How should I format markdown?" | `MARKDOWN_QUICK_REFERENCE.md` | `MARKDOWN_STYLE_GUIDE.md` |
| "How should I write Python?" | `PYTHON_STYLE_POLICY.md` | — |
| "How should I write AGENTS.md?" | `AGENTS_POLICY.md` | — |

## Key specification files (direct links)

For agents that need to jump directly to authoritative specs:

| Topic | File |
| ----- | ---- |
| Project charter and principles | `000_charter.md` |
| Scope boundaries | `010_scope.md` |
| System architecture | `020_architecture.md` |
| Data contracts and artifacts | `025_data_contracts.md` |
| Scenario model | `030_scenarios.md` |
| Telemetry pipeline | `040_telemetry_pipeline.md` |
| OCSF normalization | `050_normalization_ocsf.md` |
| Sigma detection | `060_detection_sigma.md` |
| Sigma-to-OCSF bridge | `065_sigma_to_ocsf_bridge.md` |
| Scoring metrics | `070_scoring_metrics.md` |
| Reporting | `080_reporting.md` |
| Configuration reference | `120_config_reference.md` |

## Key ADRs (direct links)

| Topic | File |
| ----- | ---- |
| Naming and versioning | `ADR-0001-project-naming-and-versioning.md` |
| Event identity and provenance | `ADR-0002-event-identity-and-provenance.md` |
| Redaction policy | `ADR-0003-redaction-policy.md` |
| Deployment architecture | `ADR-0004-deployment-architecture-and-inter-component-communication.md` |
| Stage outcomes and failures | `ADR-0005-stage-outcomes-and-failure-classification.md` |
| Plan execution model | `ADR-0006-plan-execution-model.md` |

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