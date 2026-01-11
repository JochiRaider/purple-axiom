# OCSF Mapping Profile Authoring Guide

## Purpose

This document provides deterministic instructions for LLMs and automated agents to author YAML-based
OCSF mapping profiles for the Purple Axiom normalizer.

**Audience:** LLMs, code generation agents, and human implementers.

**Scope:** Creating and validating mapping profiles that transform raw telemetry into OCSF 1.7.0
normalized events.

## Status and authority (normative)

This document is **normative** for the on-disk structure and semantics of mapping packs under:

- `mappings/normalizer/ocsf/<ocsf_version>/<source_pack_id>/`

Conformance to this guide is REQUIRED for mapping packs that participate in:

- `normalized/mapping_profile_snapshot.json` emission and hashing
- mapping coverage computation (`normalized/mapping_coverage.json`)
- CI mapping conformance gates (see `docs/spec/100_test_strategy_ci.md`)

If this guide conflicts with:

- `docs/spec/050_normalization_ocsf.md`
- `docs/spec/025_data_contracts.md`
- `docs/adr/ADR-0002-event-identity-and-provenance.md`

…the spec and ADRs take precedence. This guide MUST be updated to restore consistency.

______________________________________________________________________

## 1. Directory Structure (Normative)

### Terminology (normative)

This guide uses three distinct identifiers. Implementations MUST NOT conflate them.

| Term                   | Meaning                                                                                | Example                                         |
| ---------------------- | -------------------------------------------------------------------------------------- | ----------------------------------------------- |
| `source_pack_id`       | The mapping pack directory identifier under `mappings/normalizer/ocsf/<ocsf_version>/` | `windows-security`, `windows-sysmon`, `osquery` |
| `event_source_type`    | The constant emitted into `metadata.source_type` for all events produced by this pack  | `osquery`                                       |
| `identity_source_type` | The constant used in the ADR-0002 identity basis as `identity_basis.source_type`       | `sysmon`, `windows_eventlog`                    |

Mapping packs MUST declare all three values (or explicitly declare `identity_source_type` is derived
from routing rules).

Mapping profiles MUST be organized under the following directory structure:

```
mappings/
  normalizer/
    ocsf/
      <ocsf_version>/           # e.g., "1.7.0"
        <source_type>/          # e.g., "windows-security", "osquery", "windows-sysmon"
          profile.yaml          # REQUIRED: top-level profile definition
          canonicalization.yaml # REQUIRED: transform definitions
          routing.yaml          # REQUIRED: event routing rules
          classes/              # REQUIRED: per-class mapping files
            <class_name>_<class_uid>.yaml
          helpers/              # OPTIONAL: reusable field mapping fragments
          maps/                 # OPTIONAL: lookup tables (enums, code mappings)
          transforms/           # OPTIONAL: source-specific transform extensions
```

### Mapping material boundary (normative)

The “mapping material” for a mapping pack is the complete set of files required to route and emit
events for that pack, including:

- `profile.yaml`
- `routing.yaml`
- `canonicalization.yaml`
- all files under `classes/` that are referenced by `routing.yaml`
- any additional files referenced transitively (for example via `includes`, `helpers`, `maps`, or
  `transforms`)

A mapping pack MUST be self-contained under its `<source_pack_id>/` directory. Mapping packs MUST
NOT reference files outside their pack directory.

This mapping material boundary is used for run provenance hashing in
`normalized/mapping_profile_snapshot.json` (see Section 2.1 and `docs/spec/025_data_contracts.md`).

### Naming Conventions

| Component             | Pattern                              | Example                                                  |
| --------------------- | ------------------------------------ | -------------------------------------------------------- |
| Source type directory | `<source_type>` (lowercase, hyphens) | `windows-security`, `windows-sysmon`, `osquery`          |
| Class map file        | `<class_name>_<class_uid>.yaml`      | `authentication_3002.yaml`, `process_activity_1007.yaml` |
| Profile file          | `profile.yaml`                       | Fixed name                                               |
| Routing file          | `routing.yaml`                       | Fixed name                                               |
| Canonicalization file | `canonicalization.yaml`              | Fixed name                                               |

______________________________________________________________________

## 2. File Schemas

## 2.0 Deterministic parsing requirements (normative)

### YAML version and parser behavior

Implementations MUST parse mapping YAML as YAML 1.2.

Implementations MUST reject mapping files that contain:

- duplicate keys in any mapping object
- non-string YAML tags (custom type tags)
- YAML merge keys (`<<`)
- anchors and aliases

Rationale: these features commonly lead to non-obvious behavior and non-deterministic
materialization across parser implementations.

### Scalar typing constraints

Mapping files MUST use:

- integers only for numeric identifiers (for example `class_uid`, `activity_id`, `category_uid`)
- strings for raw field paths, OCSF field paths, and lookup keys
- explicit quotes for values that could be mis-typed by YAML (for example `"01"`, `"0x10"`)

If a value is semantically a string, it MUST be emitted as a YAML string.

### 2.1 `profile.yaml` (Required)

The profile file is the entry point for a mapping profile. It defines metadata, input expectations,
shared output rules, and identity computation.

```yaml
# mappings/normalizer/ocsf/<version>/<source_type>/profile.yaml
format_version: 1

profile:
  profile_id: <source_type>_to_ocsf_<version>   # MUST be unique
  profile_version: <semver>                      # e.g., "0.1.0"
  ocsf_version: "<ocsf_version>"                 # e.g., "1.7.0"

source:
  source_pack_id: <source_pack_id>               # MUST match directory name
  event_source_type: <event_source_type>         # Emitted to metadata.source_type for all events

  # Optional routing discriminators. MUST be present for Windows Event Log sources.
  provider: <provider_name>                      # e.g., "Microsoft-Windows-Security-Auditing"
  channel: <channel_name>                        # e.g., "Security"

  # Optional provenance labels (recommended)
  product_name: <string>                         # e.g., "windows_eventlog", "sysmon", "osquery"
  log_name: <string>                             # e.g., "Security"

inputs:
  raw_shape_version: <int>                       # Schema version for expected raw input
  required_fields:                               # Fields that MUST be present in raw input
    - <field_path>
    - ...

includes:
  canonicalization: canonicalization.yaml        # Relative path to transforms
  routing: routing.yaml                          # Relative path to routing rules

shared_emit:
  # Field mappings applied to ALL routed events before class-specific mappings.
  # Keys are OCSF field paths; values define the mapping rule.
  <ocsf_field_path>:
    from: <raw_field_path>                       # Source field
    transforms: [<transform_name>, ...]          # Optional transform chain
  <ocsf_field_path>:
    const: <literal_value>                       # Constant value

identity:
  algorithm: "pa:eid:v1"                         # Fixed. MUST match ADR-0002.
  identity_source_type: <identity_source_type>   # Optional if derived by routing rules
  basis:
    # Fields that form the identity basis (per ADR-0002)
    source_type_const: <value>
    origin.<field>_from: <raw_field_path>
    ...
  prehash_normalization:
    # Optional transforms applied to identity basis fields before hashing
    <basis_field>: [<transform>, ...]

outputs:
  set_uid_equal_event_id: true                   # MUST be true per Tier 0 contract
```

#### Profile Rules (Normative)

- `profile_id` MUST be globally unique and follow pattern `<source_type>_to_ocsf_<version>`.
- `ocsf_version` MUST match the directory path and the pinned version in
  `050_normalization_ocsf.md`.
- `source_type` MUST match the parent directory name.
- `set_uid_equal_event_id` MUST be `true` to satisfy `metadata.uid = metadata.event_id` contract.
- `source.source_pack_id` MUST equal the `<source_pack_id>` directory name.
- `source.event_source_type` MUST be the value emitted to `metadata.source_type` for all events
  produced by this pack.
- For Windows Event Log sources, `source.provider` and `source.channel` MUST be set and MUST match
  routing discriminators used in `routing.yaml`.
- For osquery-style sources, `source.provider` and `source.channel` MUST be omitted or set to null
  and MUST NOT participate in routing decisions.
- `identity.algorithm` MUST be `"pa:eid:v1"` and MUST conform to ADR-0002.
- If `identity.identity_source_type` is present, it MUST be the value used for
  `identity_basis.source_type` as defined by ADR-0002.
- If `identity.identity_source_type` is not present, the mapping pack MUST define deterministic
  rules to derive `identity_basis.source_type` from routing discriminators (example: Sysmon channel
  implies `sysmon`, otherwise `windows_eventlog`).
- For OCSF-conformant outputs, the normalizer MUST emit `metadata.uid` equal to `metadata.event_id`.
  This behavior is not configurable per profile.

______________________________________________________________________

### 2.2 `canonicalization.yaml` (Required)

Defines reusable transforms for deterministic field processing.

```yaml
# mappings/normalizer/ocsf/<version>/<source_type>/canonicalization.yaml
format_version: 1

constants:
  <constant_set_name>:
    - <value>
    - ...

transforms:
  <transform_name>:
    kind: <transform_kind>                       # string | scalar | time | presence | network | identity
    op: <operation_name>                         # Operation to perform
    args:                                        # Optional arguments
      <arg_name>: <arg_value>
```

#### Standard Transform Kinds

| Kind       | Purpose                     | Common Operations                                                           |
| ---------- | --------------------------- | --------------------------------------------------------------------------- |
| `string`   | String manipulation         | `trim_ascii_whitespace`, `lowercase_ascii`, `uppercase_ascii`               |
| `scalar`   | Type conversion             | `to_string`, `parse_int`, `parse_hex_or_dec_int`                            |
| `time`     | Timestamp parsing           | `parse_rfc3339_to_epoch_ms`, `parse_epoch_s_to_epoch_ms`                    |
| `presence` | Null/placeholder handling   | `absent_if_in_set`, `absent_if_null`                                        |
| `network`  | Network value normalization | `normalize_ip_text`                                                         |
| `identity` | Identity basis computation  | `build_identity_basis_*`, `jcs_canonical_json_bytes`, `sha256_trunc128_hex` |

#### Required Transforms (All Profiles)

Every canonicalization file SHOULD define at minimum:

```yaml
transforms:
  trim_ascii:
    kind: string
    op: trim_ascii_whitespace

  lowercase_ascii:
    kind: string
    op: lowercase_ascii

  to_string:
    kind: scalar
    op: to_string

  parse_int:
    kind: scalar
    op: parse_int
    args:
      base: 10

  absent_if_placeholder:
    kind: presence
    op: absent_if_in_set
    args:
      set_ref: constants.placeholder_values

constants:
  placeholder_values:
    - ""
    - "-"
    - "NULL"
    - "null"
    - "(null)"
    - "N/A"
```

______________________________________________________________________

### 2.3 `routing.yaml` (Required)

Defines how raw events are routed to class-specific mapping files.

```yaml
# mappings/normalizer/ocsf/<version>/<source_type>/routing.yaml
format_version: 1

routing:
  provider: <provider_name>                      # Must match profile.yaml
  channel: <channel_name>                        # Must match profile.yaml

routes:
  - route_id: <unique_route_id>                  # Descriptive identifier
    match:
      event_ids: [<id>, <id>, ...]               # Raw event IDs that match this route
      # OR for osquery-style routing:
      query_names: [<name>, ...]                 # Query names that match this route
    class_map: classes/<class_name>_<class_uid>.yaml  # Relative path to class map
```

#### Routing Rules (Normative)

- Each `route_id` MUST be unique within the file.
- `match` criteria MUST be mutually exclusive across routes (no event ID appears in multiple
  routes).
- Unmatched events MUST NOT be silently dropped.
- For each unmatched event, the normalizer MUST:
  - increment `unmapped` counters in mapping coverage (`normalized/mapping_coverage.json`), and
  - emit a stage outcome reason code indicating an unmapped event (see ADR-0005).
- The raw event payload SHOULD be retained per Tier R guidance (see
  `docs/spec/055_ocsf_field_tiers.md`).
- `class_map` paths MUST be relative to the source type directory.
- Route evaluation order MUST be the order of entries in `routes[]`.
- Each `match.event_ids` list MUST be strictly ascending numeric order.
- Each `match.query_names` list MUST be strictly ascending lexicographic order.
- Implementations MUST validate at load time that match criteria are mutually exclusive across
  routes. If overlap exists, the mapping pack MUST be rejected (fail closed).

______________________________________________________________________

### 2.4 Class Map Files (Required per routed class)

Each OCSF class that the profile can emit MUST have a dedicated class map file.

```yaml
# mappings/normalizer/ocsf/<version>/<source_type>/classes/<class_name>_<class_uid>.yaml
format_version: 1

class_map:
  class_uid: <int>                               # OCSF class UID (e.g., 3002)
  class_name: <string>                           # Human-readable name (e.g., "Authentication")
  category_uid: <int>                            # OCSF category UID (e.g., 3)

  event_id_map:
    # Per-event classification values
    <raw_event_id>:
      activity_id: <int>
      status_id: <int>                           # Optional
    ...

emit:
  # Classification fields (REQUIRED)
  class_uid:
    const_from_class: true                       # Emit class_uid from class_map.class_uid

  activity_id:
    from_event_id_map: activity_id               # Look up from event_id_map

  status_id:
    from_event_id_map: status_id                 # Optional

  type_uid:
    op: compute_type_uid                         # type_uid = class_uid * 100 + activity_id
    args:
      class_uid_from_class: true
      activity_id_from_event_id_map: true

  # Entity field mappings
  <ocsf_field_path>:
    from: <raw_field_path>                       # e.g., "event_data.TargetUserSid"
    transforms: [<transform>, ...]               # Transform chain from canonicalization.yaml

  <ocsf_field_path>:
    when:                                        # Conditional mapping
      event_id_in: [<id>, ...]                   # Only apply for these event IDs
    from: <raw_field_path>
    transforms: [...]

no_inference:
  forbidden_derivations:                         # Explicit guardrails
    - <derivation_description>
    - ...
```

Note: Implementations MUST treat `no_inference.forbidden_derivations[]` as documentation only unless
an explicit enforcement mechanism is implemented. If enforcement is implemented, it MUST be
deterministic and MUST fail closed in CI when violated.

#### Class Map Rules (Normative)

- `class_uid` MUST match the OCSF 1.7.0 schema.
- `category_uid` MUST be set correctly for the class family:
  - `1` = System Activity (Process, File, Event Log)
  - `3` = Identity & Access Management (Authentication, Account Change, Group Management)
  - `4` = Network Activity (Network, DNS)
- `event_id_map` MUST include entries for ALL event IDs routed to this class.
- `activity_id` MUST follow OCSF 1.7.0 enum values for the class.
- `type_uid` MUST be computed as `class_uid * 100 + activity_id`.
- `event_id_map` MUST include an entry for every event identifier routed to this class.
- `event_id_map` keys MUST be represented as strings in the in-memory mapping model, even if YAML
  parses them as integers. This prevents ambiguity across sources where identifiers may be numeric
  (Windows) or symbolic (osquery snapshots).
- `emit` MUST NOT populate any Tier 1 or Tier 2 field by inference. If an authoritative raw value is
  absent, the output field MUST be absent.

#### Field Mapping Syntax

```yaml
emit:
  # Direct field mapping with transforms
  <ocsf_path>:
    from: <raw_path>
    transforms: [trim_ascii, absent_if_placeholder]

  # Constant value
  <ocsf_path>:
    const: <value>

  # Conditional mapping (only for specific event IDs)
  <ocsf_path>:
    when:
      event_id_in: [4688]
    from: <raw_path>
    transforms: [...]

  # Computed value
  <ocsf_path>:
    op: <operation>
    args:
      <arg>: <value>

  # Reference to class_map value
  <ocsf_path>:
    const_from_class: true                       # Uses class_map.class_uid
    from_event_id_map: <key>                     # Uses class_map.event_id_map[event_id][key]
```

______________________________________________________________________

## 3. Authoring Workflow

### Step 1: Gather Requirements

Before creating a mapping profile, collect:

1. **Source documentation**: Raw event schema, field definitions, event ID catalog.
1. **Coverage matrix requirements**: Which Tier 1/2 fields are `R` (required) for this source.
1. **Spec document references**: The human-readable mapping profile doc (e.g.,
   `windows-security_to_ocsf_1.7.0.md`).
1. **OCSF schema reference**: Class definitions, activity IDs, field types for OCSF 1.7.0.

### Step 2: Create Directory Structure

```bash
mkdir -p mappings/normalizer/ocsf/1.7.0/<source_type>/classes
touch mappings/normalizer/ocsf/1.7.0/<source_type>/profile.yaml
touch mappings/normalizer/ocsf/1.7.0/<source_type>/canonicalization.yaml
touch mappings/normalizer/ocsf/1.7.0/<source_type>/routing.yaml
```

### Step 3: Author `canonicalization.yaml`

1. Start with the standard transforms template (see Section 2.2).
1. Add source-specific transforms as needed.
1. Define placeholder constants for the source.

### Step 4: Author `profile.yaml`

1. Set profile metadata (`profile_id`, `profile_version`, `ocsf_version`).
1. Define source discriminators (`source_type`, `provider`, `channel`).
1. List required input fields.
1. Define `shared_emit` rules for fields common to ALL events:
   - `time` (REQUIRED)
   - `device.name`, `device.hostname` (REQUIRED for Tier 1)
   - `metadata.source_type` (REQUIRED)
   - `metadata.source_event_id` (REQUIRED)
   - `metadata.log_provider`, `metadata.log_name`, `metadata.product.name` (RECOMMENDED)
1. Define identity basis per ADR-0002.

### Step 5: Author `routing.yaml`

1. List all event IDs/query names to be routed.
1. Group related events into routes (e.g., all auth events → one route).
1. Reference class map files (create placeholders if needed).

### Step 6: Author Class Map Files

For each routed class:

1. Create `classes/<class_name>_<class_uid>.yaml`.
1. Set `class_uid`, `class_name`, `category_uid`.
1. Define `event_id_map` with `activity_id` and `status_id` per event.
1. Map REQUIRED fields per coverage matrix:
   - Actor user fields (`actor.user.uid`, `actor.user.name`, `actor.user.domain`)
   - Process fields (`process.pid`, `process.file.path`, `actor.process.*`)
   - Network fields (`src_endpoint.*`, `dst_endpoint.*`)
   - File fields (`file.path`, `file.name`, `file.parent_folder`)
1. Add `no_inference` guardrails for forbidden derivations.

### Step 7: Validate

1. **Schema validation**: Each YAML file MUST be valid YAML.
1. **Reference integrity**: All `class_map` paths in routing MUST exist.
1. **Transform references**: All transforms in `emit` rules MUST be defined in
   `canonicalization.yaml`.
1. **Coverage matrix alignment**: All `R` fields for the source MUST have mappings.
1. **OCSF compliance**: `class_uid`, `activity_id`, `category_uid` MUST match OCSF 1.7.0.

______________________________________________________________________

## 4. OCSF Class Reference (v1.7.0)

**Non-normative reference:** This section is a convenience index. Implementations MUST treat the
pinned OCSF schema as the source of truth for class UIDs, category UIDs, and activity enums.

### Common Classes and Activity IDs

| Class                | `class_uid` | `category_uid` | Activity IDs                                                                                 |
| -------------------- | ----------- | -------------- | -------------------------------------------------------------------------------------------- |
| File System Activity | 1001        | 1              | 1=Create, 2=Read, 3=Update, 4=Delete, 5=Rename, 6=SetAttributes                              |
| Process Activity     | 1007        | 1              | 1=Launch, 2=Terminate, 3=Open, 4=Inject, 5=SetUserContext                                    |
| Event Log Activity   | 1008        | 1              | 1=Clear, 2=Read, 3=Modify, 4=Create, 5=Delete                                                |
| Account Change       | 3001        | 3              | 1=Create, 2=Enable, 3=Disable, 4=Delete, 5=PasswordChange, 6=PasswordReset, 7=Lock, 8=Unlock |
| Authentication       | 3002        | 3              | 1=Logon, 2=Logoff, 3=AuthTicket, 4=ServiceTicket                                             |
| Group Management     | 3006        | 3              | 1=AssignPrivileges, 2=RevokePrivileges, 3=AddUser, 4=RemoveUser                              |
| Network Activity     | 4001        | 4              | 1=Open, 2=Close, 3=Reset, 4=Fail, 5=Refuse, 6=Traffic                                        |
| DNS Activity         | 4003        | 4              | 1=Query, 2=Response                                                                          |

### Status IDs (Common)

| `status_id` | Meaning |
| ----------- | ------- |
| 0           | Unknown |
| 1           | Success |
| 2           | Failure |
| 99          | Other   |

______________________________________________________________________

## 5. Transform Reference

### String Transforms

| Transform               | Input       | Output     | Notes                                     |
| ----------------------- | ----------- | ---------- | ----------------------------------------- |
| `trim_ascii_whitespace` | `"  foo  "` | `"foo"`    | Removes leading/trailing ASCII whitespace |
| `lowercase_ascii`       | `"FooBar"`  | `"foobar"` | ASCII lowercase only                      |
| `uppercase_ascii`       | `"FooBar"`  | `"FOOBAR"` | ASCII uppercase only                      |

### Scalar Transforms

| Transform              | Input              | Output  | Notes                            |
| ---------------------- | ------------------ | ------- | -------------------------------- |
| `to_string`            | `123`              | `"123"` | Convert to string representation |
| `parse_int`            | `"123"`            | `123`   | Parse base-10 integer            |
| `parse_hex_or_dec_int` | `"0x1A"` or `"26"` | `26`    | Parse hex (0x prefix) or decimal |

### Time Transforms

| Transform                   | Input                    | Output          | Notes                         |
| --------------------------- | ------------------------ | --------------- | ----------------------------- |
| `parse_rfc3339_to_epoch_ms` | `"2026-01-11T12:00:00Z"` | `1768161600000` | RFC3339 to epoch milliseconds |
| `parse_epoch_s_to_epoch_ms` | `1768161600`             | `1768161600000` | Multiply by 1000              |

### Presence Transforms

| Transform          | Args                                    | Behavior                         |
| ------------------ | --------------------------------------- | -------------------------------- |
| `absent_if_in_set` | `set_ref: constants.placeholder_values` | Return absent if value is in set |
| `absent_if_null`   | -                                       | Return absent if value is null   |

### Network Transforms

| Transform           | Input           | Output          | Notes                              |
| ------------------- | --------------- | --------------- | ---------------------------------- |
| `normalize_ip_text` | `"192.168.1.1"` | `"192.168.1.1"` | Normalize IP; MUST NOT resolve DNS |

______________________________________________________________________

## 6. Field Path Conventions

### Raw Input Paths

Raw field paths use dot notation to navigate nested structures:

```yaml
from: event_data.TargetUserSid        # Windows Event Log EventData
from: columns.pid                      # osquery columns object
from: hostIdentifier                   # Top-level osquery field
```

### OCSF Output Paths

OCSF field paths follow the OCSF schema structure:

```yaml
actor.user.uid                         # Actor user identifier
actor.user.name                        # Actor user name
actor.process.pid                      # Actor process ID
process.pid                            # Primary process ID (for Process Activity)
src_endpoint.ip                        # Source endpoint IP
dst_endpoint.port                      # Destination endpoint port
file.path                              # Full file path
file.name                              # File basename
file.parent_folder                     # Parent directory
metadata.source_event_id               # Source-native event ID
```

______________________________________________________________________

## 7. Validation Checklist

## Run provenance and hashing (normative)

### Relationship to `normalized/mapping_profile_snapshot.json`

For every run that performs normalization, the orchestrator/normalizer MUST emit
`normalized/mapping_profile_snapshot.json` as Tier 0 provenance per
`docs/spec/025_data_contracts.md`.

The mapping pack authored by this guide MUST be fully represented in the snapshot using one of:

1. `mapping_material` (embedded canonical representation), or
1. `mapping_files[]` (preferred for YAML-based packs)

### `mapping_files[]` requirements (preferred)

When using `mapping_files[]`, the snapshot MUST include, at minimum, SHA-256 entries for:

- `profile.yaml`
- `routing.yaml`
- `canonicalization.yaml`
- all routed `classes/*.yaml`
- all transitively referenced files under `helpers/`, `maps/`, or `transforms/` that affect emission

Each `mapping_files[].path` MUST be:

- repository-relative
- normalized to POSIX separators (`/`)
- stable across operating systems

Each `mapping_files[].sha256` MUST be computed over the exact file bytes as stored in the
repository.

Before submitting a mapping profile, verify:

### Structure

- [ ] Directory structure matches Section 1
- [ ] All required files exist (`profile.yaml`, `canonicalization.yaml`, `routing.yaml`)
- [ ] Class map files exist for all routed classes

### Profile

- [ ] `profile_id` is unique and follows naming convention
- [ ] `ocsf_version` matches directory path
- [ ] `source_type` matches directory name
- [ ] `set_uid_equal_event_id: true` is set

### Routing

- [ ] All event IDs are covered (no gaps)
- [ ] No overlapping matches across routes
- [ ] All `class_map` paths resolve to existing files

### Class Maps

- [ ] `class_uid` matches OCSF 1.7.0 schema
- [ ] `category_uid` is correct for the class family
- [ ] `event_id_map` covers all routed event IDs
- [ ] `activity_id` values match OCSF 1.7.0 enum
- [ ] `type_uid` computation is defined

### Coverage Matrix Alignment

- [ ] All `R` (Required) fields from coverage matrix have mappings
- [ ] `N/A` fields are not mapped
- [ ] No inference of values not present in raw data

### Transforms

- [ ] All referenced transforms exist in `canonicalization.yaml`
- [ ] Placeholder handling is consistent with source conventions
- [ ] Numeric parsing handles source-specific formats (hex, decimal)

### Provenance (Tier 0)

- [ ] `normalized/mapping_profile_snapshot.json` includes this mapping pack as `mapping_files[]` or
  embedded `mapping_material`
- [ ] The file set included in the snapshot matches the mapping material boundary in Section 1
- [ ] No mapping files are referenced outside the mapping pack directory

______________________________________________________________________

## 8. Examples

### Example: Adding a New Event ID to Existing Class

To add Windows Security event 4672 (Special Privileges Assigned) to the Authentication class:

1. **Update `routing.yaml`**:

```yaml
routes:
  - route_id: winsec_authentication
    match:
      event_ids: [4624, 4625, 4634, 4647, 4672]  # Added 4672
    class_map: classes/authentication_3002.yaml
```

2. **Update `authentication_3002.yaml`**:

```yaml
class_map:
  event_id_map:
    4624: {activity_id: 1, status_id: 1}
    4625: {activity_id: 1, status_id: 2}
    4634: {activity_id: 2, status_id: 1}
    4647: {activity_id: 2, status_id: 1}
    4672: {activity_id: 99, status_id: 1}  # Added: Other activity
```

### Example: Creating a New Class Map

To add File System Activity (1001) for a new source:

```yaml
# classes/file_system_activity_1001.yaml
format_version: 1

class_map:
  class_uid: 1001
  class_name: File System Activity
  category_uid: 1

  event_id_map:
    # Map source event IDs to OCSF activities
    CREATE_FILE: {activity_id: 1, status_id: 1}
    DELETE_FILE: {activity_id: 4, status_id: 1}
    MODIFY_FILE: {activity_id: 3, status_id: 1}

emit:
  class_uid:
    const_from_class: true

  activity_id:
    from_event_id_map: activity_id

  type_uid:
    op: compute_type_uid
    args:
      class_uid_from_class: true
      activity_id_from_event_id_map: true

  file.path:
    from: target_path
    transforms: [trim_ascii, absent_if_placeholder]

  file.name:
    from: target_path
    transforms: [trim_ascii, absent_if_placeholder, extract_basename]

  file.parent_folder:
    from: target_path
    transforms: [trim_ascii, absent_if_placeholder, extract_parent_folder]

  actor.user.uid:
    from: uid
    transforms: [to_string]

no_inference:
  forbidden_derivations:
    - actor.process.pid_from_file_owner
```

______________________________________________________________________

## 9. Appendix: Source-Specific Notes

### Windows Event Log Sources

- Raw field paths: `event_data.<FieldName>` for EventData elements.
- Placeholder values: `"-"`, `"NULL"`, `"(null)"` are common.
- PIDs may be hex (0x prefix) or decimal; use `parse_hex_or_dec_int`.
- SIDs MUST be preserved exactly (no normalization).

### osquery Sources

- Routing key: `query_name` (from `name` field in results).
- Raw field paths: `columns.<column_name>` for differential rows.
- Numeric fields are often string-typed; always use `parse_int`.
- Snapshot rows: `activity_id` MUST be `99` (Other).

### Sysmon Sources

- Raw field paths: `event_data.<FieldName>`.
- Hash field: parse `KEY=VALUE,KEY=VALUE` format.
- Protocol field: preserve as string; do NOT convert to number.
- GUIDs: preserve exactly as emitted.

______________________________________________________________________

## 10. References

| Document                    | Purpose                                         |
| --------------------------- | ----------------------------------------------- |
| `050_normalization_ocsf.md` | OCSF version pinning, envelope requirements     |
| `055_ocsf_field_tiers.md`   | Tier model, coverage metrics                    |
| `coverage_matrix.md`        | Per-source field requirements (R/O/N/A)         |
| `ADR-0002`                  | Event identity and provenance                   |
| `ADR-0003`                  | Redaction policy                                |
| Human mapping profile docs  | `<source>_to_ocsf_1.7.0.md` in `docs/mappings/` |
