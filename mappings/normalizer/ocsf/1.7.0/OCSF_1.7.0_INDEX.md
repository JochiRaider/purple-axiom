# OCSF 1.7.0 mapping packs (normalizer)

Purpose: route the agent to OCSF 1.7.0 normalizer mapping pack entrypoints with minimal reading.

## Entrypoints (open these first)

Entrypoints are listed in recommended open order per pack: `profile.yaml`, then `routing.yaml`,
then `canonicalization.yaml`.

Ordering: packs are sorted lexicographically by `pack_id` (directory name).

| Pack (source_type) | Pack root                                          | Profile                                                            | Routing                                                            | Canonicalization                                                            |
| ------------------ | -------------------------------------------------- | ------------------------------------------------------------------ | ------------------------------------------------------------------ | --------------------------------------------------------------------------- |
| `osquery`          | `mappings/normalizer/ocsf/1.7.0/osquery/`          | `mappings/normalizer/ocsf/1.7.0/osquery/profile.yaml`              | `mappings/normalizer/ocsf/1.7.0/osquery/routing.yaml`              | `mappings/normalizer/ocsf/1.7.0/osquery/canonicalization.yaml`              |
| `windows-security` | `mappings/normalizer/ocsf/1.7.0/windows-security/` | `mappings/normalizer/ocsf/1.7.0/windows-security/profile.yaml`     | `mappings/normalizer/ocsf/1.7.0/windows-security/routing.yaml`     | `mappings/normalizer/ocsf/1.7.0/windows-security/canonicalization.yaml`     |
| `windows-sysmon`   | `mappings/normalizer/ocsf/1.7.0/windows-sysmon/`   | `mappings/normalizer/ocsf/1.7.0/windows-sysmon/profile.yaml`       | `mappings/normalizer/ocsf/1.7.0/windows-sysmon/routing.yaml`       | `mappings/normalizer/ocsf/1.7.0/windows-sysmon/canonicalization.yaml`       |

## Inventory (leaf mapping files)

This inventory is intentionally limited to leaf class mapping files.

Ordering: paths are sorted lexicographically by full repo-relative path.

| File path                                                                              | Primary purpose (authoritative for)                       |
| -------------------------------------------------------------------------------------- | --------------------------------------------------------- |
| `mappings/normalizer/ocsf/1.7.0/osquery/classes/file_system_activity_1001.yaml`        | File system activity class mapping rules (osquery)        |
| `mappings/normalizer/ocsf/1.7.0/osquery/classes/network_activity_4001.yaml`            | Network activity class mapping rules (osquery)            |
| `mappings/normalizer/ocsf/1.7.0/osquery/classes/process_activity_1007.yaml`            | Process activity class mapping rules (osquery)            |
| `mappings/normalizer/ocsf/1.7.0/windows-security/classes/authentication_3002.yaml`     | Authentication class mapping rules (Windows Security)     |
| `mappings/normalizer/ocsf/1.7.0/windows-security/classes/event_log_activity_1008.yaml` | Event log activity class mapping rules (Windows Security) |
| `mappings/normalizer/ocsf/1.7.0/windows-security/classes/process_activity_1007.yaml`   | Process activity class mapping rules (Windows Security)   |
| `mappings/normalizer/ocsf/1.7.0/windows-sysmon/classes/dns_activity_4003.yaml`         | DNS activity class mapping rules (Windows Sysmon)         |
| `mappings/normalizer/ocsf/1.7.0/windows-sysmon/classes/file_system_activity_1001.yaml` | File system activity class mapping rules (Windows Sysmon) |
| `mappings/normalizer/ocsf/1.7.0/windows-sysmon/classes/network_activity_4001.yaml`     | Network activity class mapping rules (Windows Sysmon)     |
| `mappings/normalizer/ocsf/1.7.0/windows-sysmon/classes/process_activity_1007.yaml`     | Process activity class mapping rules (Windows Sysmon)     |

## Related indexes

- `mappings/MAPPINGS_INDEX.md` (root router)

## Update rule (required)

- Update this index and keep it one page.
- Do not include the agent, or readme files.
- Prefer pointers to scoped indexes over duplicated prose.
- Unless stated otherwise, lists and tables are sorted lexicographically by path.
- The “Entrypoints” section above is intentionally sorted by recommended read order.