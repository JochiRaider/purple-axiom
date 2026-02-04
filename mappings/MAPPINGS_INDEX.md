# Mappings navigator

Purpose: route the agent to mapping pack entrypoints with minimal reading.

## Entrypoints (open these first)

- `mappings/normalizer/ocsf/1.7.0/OCSF_1.7.0_INDEX.md` (OCSF 1.7.0 normalizer mapping packs)

## Pack / subsystem map

| Name                                  | Path                              | Entrypoints           | Notes                                             |
| ------------------------------------- | --------------------------------- | --------------------- | ------------------------------------------------- |
| OCSF normalizer mappings (OCSF 1.7.0) | `mappings/normalizer/ocsf/1.7.0/` | `OCSF_1.7.0_INDEX.md` | Pack profiles, routing, canonicalization, classes |

## Pack map (OCSF 1.7.0 normalizer packs)

Ordering: rows are sorted lexicographically by `Pack (source_type)`.

| Pack (source_type) | Path                                               | Notes                                            |
| ------------------ | -------------------------------------------------- | ------------------------------------------------ |
| `osquery`          | `mappings/normalizer/ocsf/1.7.0/osquery/`          | Pack profile, routing, canonicalization, classes |
| `windows-security` | `mappings/normalizer/ocsf/1.7.0/windows-security/` | Pack profile, routing, canonicalization, classes |
| `windows-sysmon`   | `mappings/normalizer/ocsf/1.7.0/windows-sysmon/`   | Pack profile, routing, canonicalization, classes |

## Sub-indexes

- `mappings/normalizer/ocsf/1.7.0/OCSF_1.7.0_INDEX.md`

## Update rule (required)

- Update this index and keep it one page.
- Do not include the agent, or readme files.
- Prefer pointers to scoped indexes over duplicated prose.
- Unless stated otherwise, lists and tables are sorted lexicographically by path.
- The “Entrypoints” section above is intentionally sorted by recommended read order.
