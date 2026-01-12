<!-- mappings/MAPPINGS_INDEX.md -->

# Mappings navigator (mappings only)

This file is a one-page map over the machine-executable mapping packs in `mappings/` so agents do
not need to load every mapping file to find the relevant pack or rule.

## Pack map (by OCSF version / source_type)

| Pack (source_type) | Path                                               | Notes                                            |
| ------------------ | -------------------------------------------------- | ------------------------------------------------ |
| `osquery`          | `mappings/normalizer/ocsf/1.7.0/osquery/`          | Pack profile, routing, canonicalization, classes |
| `windows-security` | `mappings/normalizer/ocsf/1.7.0/windows-security/` | Pack profile, routing, canonicalization, classes |
| `windows-sysmon`   | `mappings/normalizer/ocsf/1.7.0/windows-sysmon/`   | Pack profile, routing, canonicalization, classes |

## File map (covers all mapping files)

| File path                                                                              | Primary purpose (authoritative for)                       |
| -------------------------------------------------------------------------------------- | --------------------------------------------------------- |
| `mappings/normalizer/ocsf/1.7.0/osquery/profile.yaml`                                  | Pack profile for osquery mappings                         |
| `mappings/normalizer/ocsf/1.7.0/osquery/canonicalization.yaml`                         | Canonicalization rules for osquery mappings               |
| `mappings/normalizer/ocsf/1.7.0/osquery/routing.yaml`                                  | Routing rules for osquery mappings                        |
| `mappings/normalizer/ocsf/1.7.0/osquery/classes/file_system_activity_1001.yaml`        | File system activity class mapping rules (osquery)        |
| `mappings/normalizer/ocsf/1.7.0/osquery/classes/network_activity_4001.yaml`            | Network activity class mapping rules (osquery)            |
| `mappings/normalizer/ocsf/1.7.0/osquery/classes/process_activity_1007.yaml`            | Process activity class mapping rules (osquery)            |
| `mappings/normalizer/ocsf/1.7.0/windows-security/profile.yaml`                         | Pack profile for Windows Security mappings                |
| `mappings/normalizer/ocsf/1.7.0/windows-security/routing.yaml`                         | Routing rules for Windows Security mappings               |
| `mappings/normalizer/ocsf/1.7.0/windows-security/canonicalization.yaml`                | Canonicalization rules for Windows Security mappings      |
| `mappings/normalizer/ocsf/1.7.0/windows-security/classes/authentication_3002.yaml`     | Authentication class mapping rules (Windows Security)     |
| `mappings/normalizer/ocsf/1.7.0/windows-security/classes/event_log_activity_1008.yaml` | Event log activity class mapping rules (Windows Security) |
| `mappings/normalizer/ocsf/1.7.0/windows-security/classes/process_activity_1007.yaml`   | Process activity class mapping rules (Windows Security)   |
| `mappings/normalizer/ocsf/1.7.0/windows-sysmon/profile.yaml`                           | Pack profile for Windows Sysmon mappings                  |
| `mappings/normalizer/ocsf/1.7.0/windows-sysmon/routing.yaml`                           | Routing rules for Windows Sysmon mappings                 |
| `mappings/normalizer/ocsf/1.7.0/windows-sysmon/canonicalization.yaml`                  | Canonicalization rules for Windows Sysmon mappings        |
| `mappings/normalizer/ocsf/1.7.0/windows-sysmon/classes/dns_activity_4003.yaml`         | DNS activity class mapping rules (Windows Sysmon)         |
| `mappings/normalizer/ocsf/1.7.0/windows-sysmon/classes/file_system_activity_1001.yaml` | File system activity class mapping rules (Windows Sysmon) |
| `mappings/normalizer/ocsf/1.7.0/windows-sysmon/classes/network_activity_4001.yaml`     | Network activity class mapping rules (Windows Sysmon)     |
| `mappings/normalizer/ocsf/1.7.0/windows-sysmon/classes/process_activity_1007.yaml`     | Process activity class mapping rules (Windows Sysmon)     |

## Other files in mappings

- `mappings/AGENTS.md` (agent instructions for `mappings/*`)
- `mappings/MAPPINGS_INDEX.md` (this index)
