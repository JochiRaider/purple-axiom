# ADR navigator (docs/adr only)

This file exists to keep agent working sets small. It is a one-page map over ADR markdown files in
`docs/adr/` so agents do not need to load every document to find the relevant decision record.

## Entrypoints (open these first)

- `ADR-0002-event-identity-and-provenance.md` (event identity basis and provenance requirements)
- `ADR-0004-deployment-architecture-and-inter-component-communication.md` (deployment boundaries)
- `ADR-0005-stage-outcomes-and-failure-classification.md` (stage outcomes and failure taxonomy)

## File map (covers all ADRs)

| ADR file                                                                | Primary purpose (authoritative for)                              |
| ----------------------------------------------------------------------- | ---------------------------------------------------------------- |
| `ADR-0001-project-naming-and-versioning.md`                             | Project-wide naming, versioning, and pinning conventions         |
| `ADR-0002-event-identity-and-provenance.md`                             | Event identity and provenance rules                              |
| `ADR-0003-redaction-policy.md`                                          | Redaction policy and safe defaults                               |
| `ADR-0004-deployment-architecture-and-inter-component-communication.md` | Component boundaries and communication expectations              |
| `ADR-0005-stage-outcomes-and-failure-classification.md`                 | Stage outcomes, failure classification, and run status semantics |
| `ADR-0006-plan-execution-model.md`                                      | Plan execution model and reserved multi-target semantics         |

## Common tasks (fast paths)

| Need                                                   | Read first                                                              |
| ------------------------------------------------------ | ----------------------------------------------------------------------- |
| “Where are event identity / provenance rules defined?” | `ADR-0002-event-identity-and-provenance.md`                             |
| “How are sensitive values redacted?”                   | `ADR-0003-redaction-policy.md`                                          |
| “What is the run status / failure taxonomy?”           | `ADR-0005-stage-outcomes-and-failure-classification.md`                 |
| “What are the deployment / component boundaries?”      | `ADR-0004-deployment-architecture-and-inter-component-communication.md` |
| “How do matrix/multi-target plans work?”               | `ADR-0006-plan-execution-model.md`                                      |

## Update rule (required)

When you add a new ADR:

- Add it to this index and keep this file one page.
- Do not include the agent, index or readme files.
- Prefer pointers over duplicated prose.
- Unless stated otherwise, lists and tables are sorted lexicographically by path.
- The “Entrypoints” section above is intentionally sorted by recommended read order.
