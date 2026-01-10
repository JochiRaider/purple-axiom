<!-- docs/adr/ADR_INDEX.md -->

# ADR navigator (docs/adr only)

This file is a one-page map over ADR markdown files in `docs/adr/`. It exists to keep agent working
sets small and prevent “read the entire ADR set” behavior.

## File map (covers all ADRs)

| ADR file                                    | Decision area (authoritative for)                           |
| ------------------------------------------- | ----------------------------------------------------------- |
| `ADR-0001-project-naming-and-versioning.md` | Project naming rules and versioning policy                  |
| `ADR-0002-event-identity-and-provenance.md` | Event identity, provenance model, and determinism rules     |
| `ADR-0003-redaction-policy.md`              | Redaction policy posture and redaction-related consequences |

## Common tasks (fast paths)

| Need                                                 | Read first                                  |
| ---------------------------------------------------- | ------------------------------------------- |
| “What naming/versioning rules are in force?”         | `ADR-0001-project-naming-and-versioning.md` |
| “How is event identity/provenance defined?”          | `ADR-0002-event-identity-and-provenance.md` |
| “What is the redaction policy and its implications?” | `ADR-0003-redaction-policy.md`              |

## Update rule (required)

When you add a new ADR:

- Add it to this index and keep this file one page.
- Prefer pointers over duplicated prose.
