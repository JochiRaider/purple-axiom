<!-- mappings/MAPPINGS_INDEX.md -->

# Mappings navigator (mappings only)

This file is a one-page map over the machine-executable mapping packs in `mappings/` so agents do
not need to load every mapping file to find the relevant pack or rule.

## Pack map (by OCSF version / source_type)

| Pack (source_type) | Path                                               | Notes                                  |
| ------------------ | -------------------------------------------------- | -------------------------------------- |
| `osquery`          | `mappings/normalizer/ocsf/1.7.0/osquery/`           | Pack entrypoint, routing, helpers, maps |
| `windows-security`| `mappings/normalizer/ocsf/1.7.0/windows-security/`  | Pack profile, routing, canonicalization, classes |
| `windows-sysmon`   | `mappings/normalizer/ocsf/1.7.0/windows-sysmon/`    | Pack profile, routing, canonicalization, maps, transforms |

## File map (covers all mapping files)

| File path | Primary purpose (authoritative for) |
| --------- | ----------------------------------- |
| `mappings/normalizer/ocsf/1.7.0/osquery/_pack.yaml` | Pack entrypoint for osquery mappings |
| `mappings/normalizer/ocsf/1.7.0/osquery/routing.yaml` | Routing rules for osquery mappings |
| `mappings/normalizer/ocsf/1.7.0/osquery/helpers/canonicalization.yaml` | Canonicalization helpers for osquery mappings |
| `mappings/normalizer/ocsf/1.7.0/osquery/helpers/identity.yaml` | Identity helpers for osquery mappings |
| `mappings/normalizer/ocsf/1.7.0/osquery/maps/file_system_activity.yaml` | File system activity mapping rules (osquery) |
| `mappings/normalizer/ocsf/1.7.0/osquery/maps/network_activity.yaml` | Network activity mapping rules (osquery) |
| `mappings/normalizer/ocsf/1.7.0/osquery/maps/process_activity.yaml` | Process activity mapping rules (osquery) |
| `mappings/normalizer/ocsf/1.7.0/windows-security/profile.yaml` | Pack profile for Windows Security mappings |
| `mappings/normalizer/ocsf/1.7.0/windows-security/routing.yaml` | Routing rules for Windows Security mappings |
| `mappings/normalizer/ocsf/1.7.0/windows-security/canonicalization.yaml` | Canonicalization rules for Windows Security mappings |
| `mappings/normalizer/ocsf/1.7.0/windows-security/classes/authentication_3002.yaml` | Authentication class mapping rules (Windows Security) |
| `mappings/normalizer/ocsf/1.7.0/windows-security/classes/event_log_activity_1008.yaml` | Event log activity class mapping rules (Windows Security) |
| `mappings/normalizer/ocsf/1.7.0/windows-security/classes/process_activity_1007.yaml` | Process activity class mapping rules (Windows Security) |
| `mappings/normalizer/ocsf/1.7.0/windows-sysmon/profile.yaml` | Pack profile for Windows Sysmon mappings |
| `mappings/normalizer/ocsf/1.7.0/windows-sysmon/routing.yaml` | Routing rules for Windows Sysmon mappings |
| `mappings/normalizer/ocsf/1.7.0/windows-sysmon/canonicalization.yaml` | Canonicalization rules for Windows Sysmon mappings |
| `mappings/normalizer/ocsf/1.7.0/windows-sysmon/maps/dns_activity.yaml` | DNS activity mapping rules (Windows Sysmon) |
| `mappings/normalizer/ocsf/1.7.0/windows-sysmon/maps/file_system_activity.yaml` | File system activity mapping rules (Windows Sysmon) |
| `mappings/normalizer/ocsf/1.7.0/windows-sysmon/maps/network_activity.yaml` | Network activity mapping rules (Windows Sysmon) |
| `mappings/normalizer/ocsf/1.7.0/windows-sysmon/maps/process_activity.yaml` | Process activity mapping rules (Windows Sysmon) |
| `mappings/normalizer/ocsf/1.7.0/windows-sysmon/transforms/hostname_lower.yaml` | Hostname transform (Windows Sysmon) |
| `mappings/normalizer/ocsf/1.7.0/windows-sysmon/transforms/parse_domain_user.yaml` | Domain\\user parsing transform (Windows Sysmon) |
| `mappings/normalizer/ocsf/1.7.0/windows-sysmon/transforms/parse_int.yaml` | Integer parsing transform (Windows Sysmon) |
| `mappings/normalizer/ocsf/1.7.0/windows-sysmon/transforms/parse_sysmon_hashes.yaml` | Sysmon hashes parsing transform (Windows Sysmon) |
| `mappings/normalizer/ocsf/1.7.0/windows-sysmon/transforms/trim.yaml` | String trim transform (Windows Sysmon) |

## Other files in mappings

- `mappings/AGENTS.md` (agent instructions for `mappings/*`)
- `mappings/MAPPINGS_INDEX.md` (this index)
