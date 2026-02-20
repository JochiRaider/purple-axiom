---
title: OCSF mapping profile authoring guide
description: Deterministic authoring rules for YAML-based OCSF mapping profiles used by the Purple Axiom normalizer.
status: draft
---

# OCSF mapping profile authoring guide

This guide defines deterministic instructions for authoring YAML-based OCSF mapping packs for the
Purple Axiom normalizer.

## Purpose

**Audience:** LLMs, code generation agents, and human implementers.

**Scope:** Creating and validating mapping packs that transform raw telemetry into OCSF 1.7.0
normalized events.

## Status and authority (normative)

This document is **normative** for the on-disk structure and semantics of mapping packs under:

- `mappings/normalizer/ocsf/<ocsf_version>/<source_pack_id>/`

Conformance to this guide is REQUIRED for mapping packs that participate in:

- `normalized/mapping_profile_snapshot.json` emission and hashing
- mapping coverage computation (`normalized/mapping_coverage.json`)
- CI mapping conformance gates (see [mapping CI strategy](../spec/100_test_strategy_ci.md))

If this guide conflicts with:

- [OCSF normalization specification](../spec/050_normalization_ocsf.md)
- [Data contracts specification](../spec/025_data_contracts.md)
- [ADR-0002 Event identity and provenance](../adr/ADR-0002-event-identity-and-provenance.md)

then the spec and ADRs take precedence. This guide MUST be updated to restore consistency.

______________________________________________________________________

## Directory structure (normative)

### Terminology (normative)

This guide uses distinct identifiers. Implementations MUST NOT conflate them, even when the chosen
string values happen to be equal.

| Term                   | Meaning                                                                                | Example                                         |
| ---------------------- | -------------------------------------------------------------------------------------- | ----------------------------------------------- |
| `source_pack_id`       | The mapping pack directory identifier under `mappings/normalizer/ocsf/<ocsf_version>/` | `windows-security`, `windows-sysmon`, `osquery` |
| `event_source_type`    | The constant emitted into `metadata.source_type` for all events produced by this pack  | `windows-sysmon`, `osquery`                     |
| `identity_source_type` | The constant used in the ADR-0002 identity basis as `identity_basis.source_type`       | `sysmon`, `windows_eventlog`                    |

Additionally, this guide uses:

- **Routing key**: the per-record discriminator used to select `class_map.event_id_map[...]`.
  - For `routing.match.event_ids`, the routing key is the matched numeric event id.
  - For `routing.match.query_names`, the routing key is the matched query name string.

Mapping packs MUST declare `source_pack_id` and `event_source_type`. Mapping packs MUST declare
`identity_source_type` or explicitly define deterministic derivation rules for it from routing
discriminators (see `profile.yaml` identity rules).

### Directory structure (normative)

Mapping packs MUST be organized under the following structure:

```text
mappings/
  normalizer/
    ocsf/
      <ocsf_version>/                 # e.g., "1.7.0"
        <source_pack_id>/             # e.g., "windows-security", "windows-sysmon", "osquery"
          profile.yaml                # REQUIRED: top-level profile definition
          canonicalization.yaml       # REQUIRED: transform definitions
          routing.yaml                # REQUIRED: event routing rules
          classes/                    # REQUIRED: per-class mapping files
            <class_name>_<class_uid>.yaml
          helpers/                    # OPTIONAL: reusable field mapping fragments
          maps/                       # OPTIONAL: lookup tables (enums, code mappings)
          transforms/                 # OPTIONAL: source-specific transform extensions
```

### Mapping material boundary (normative)

The "mapping material" for a mapping pack is the complete set of files required to route and emit
events for that pack.

At minimum it includes:

- `profile.yaml`
- `routing.yaml`
- `canonicalization.yaml`
- all files under `classes/` referenced by `routing.yaml`

If `helpers/`, `maps/`, or `transforms/` are used, the mapping material boundary additionally
includes the deterministic closure of referenced files defined in
[Reusable components and deterministic composition](#reusable-components-and-deterministic-composition-normative).

A mapping pack MUST be self-contained under its `<source_pack_id>/` directory. Mapping packs MUST
NOT reference files outside their pack directory.

This mapping material boundary is used for run provenance hashing in
`normalized/mapping_profile_snapshot.json` (see the
[data contracts specification](../spec/025_data_contracts.md)).

### Naming conventions (normative)

| Component                         | Pattern                                         | Example                                                  |
| --------------------------------- | ----------------------------------------------- | -------------------------------------------------------- |
| `source_pack_id` directory        | lowercase, digits, hyphens                      | `windows-security`, `windows-sysmon`, `osquery`          |
| `event_source_type`               | lowercase, digits, hyphens                      | `windows-sysmon`, `osquery`                              |
| `identity_source_type`            | lowercase, digits, hyphens, underscores allowed | `windows_eventlog`, `sysmon`                             |
| Class map file                    | `<class_name>_<class_uid>.yaml`                 | `authentication_3002.yaml`, `process_activity_1007.yaml` |
| Profile file                      | `profile.yaml`                                  | fixed name                                               |
| Routing file                      | `routing.yaml`                                  | fixed name                                               |
| Canonicalization file             | `canonicalization.yaml`                         | fixed name                                               |
| Profile id (`profile.profile_id`) | `<source_pack_id>_to_ocsf_<ocsf_version>`       | `windows-security_to_ocsf_1.7.0`                         |

______________________________________________________________________

## File schemas

### Deterministic parsing requirements (normative)

#### YAML version and parser behavior

Implementations MUST parse mapping YAML as YAML 1.2.

Each mapping YAML file MUST contain exactly one YAML document. Multi-document YAML MUST be rejected.

Implementations MUST reject mapping files that contain:

- duplicate keys in any mapping object
- non-string YAML tags (custom type tags)
- YAML merge keys (`<<`)
- anchors and aliases

Rationale: these features commonly lead to non-obvious behavior and non-deterministic
materialization across parser implementations.

#### Encoding and line ending constraints (normative)

To ensure cross-platform reproducibility, mapping YAML files MUST:

- be UTF-8 encoded
- NOT include a UTF-8 BOM
- use LF (`\n`) line endings

Implementations MUST reject mapping files that violate these constraints.

#### Scalar typing constraints (normative)

Mapping files MUST use:

- integers only for numeric identifiers (for example `class_uid`, `activity_id`, `category_uid`)
- strings for raw field paths, OCSF field paths, transform names, and lookup keys
- explicit quotes for values that could be mis-typed by YAML (for example `"01"`, `"0x10"`)

Routing keys may be numeric (Windows event ids) or string (osquery query names). In the in-memory
mapping model, routing keys MUST be represented as strings to avoid ambiguity across sources.

If a value is semantically a string, it MUST be emitted as a YAML string.

#### Unknown keys (normative)

For every YAML file schema defined in this guide, implementations MUST reject unknown keys at the
top-level and at any schema-defined object level (fail closed). This is required for deterministic
interpretation across implementations.

______________________________________________________________________

### Reusable components and deterministic composition (normative)

This section defines the only supported composition mechanism for optional reusable mapping material
under `helpers/`, `maps/`, and `transforms/`. It is the deterministic alternative to YAML merge
keys, anchors, and aliases, which are forbidden.

#### Pack path references (normative)

A **pack path** is a string that identifies a file within a single mapping pack.

Pack path requirements:

A pack path MUST:

- be relative to the mapping pack root directory (the directory that contains `profile.yaml`)
- use POSIX separators (`/`) only
- NOT begin with `/`
- NOT begin with `./`
- NOT contain any path segment equal to `..`
- refer to a regular file that exists in the repository checkout

Implementations MUST fail closed if a pack path violates any requirement above.

Symlinks and special files:

To preserve cross-platform determinism, implementations MUST fail closed if any referenced file is a
symlink or a non-regular file (device node, FIFO, socket).

#### Include list ordering (normative)

All include lists defined by this guide MUST:

- be strictly sorted in ascending **UTF-8 bytewise lexical order**
- contain no duplicate entries

Failure MUST be fail closed (reject the mapping pack).

#### Helper fragments (normative)

Helper fragments are YAML files under `helpers/` that provide reusable `emit` mappings.

Helpers file schema:

```yaml
format_version: 1

emit:
  <ocsf_field_path>:
    <mapping_rule>
```

Rules:

- Helper files MUST define only `format_version` and `emit`.
- Helper files MUST NOT define `profile`, `source`, `inputs`, `identity`, `routing`, or `class_map`.

Helper inclusion in `profile.yaml`:

`profile.yaml` MAY include helper fragments merged into `shared_emit` via:

```yaml
includes:
  helpers:
    - helpers/<name>.yaml
    - helpers/<name>.yaml
```

Helper inclusion in class map files:

A class map file MAY include helper fragments merged into its `emit` via:

```yaml
includes:
  helpers:
    - helpers/<name>.yaml
    - helpers/<name>.yaml
```

Helper merge semantics (normative):

- The effective mapping map is computed by:

  1. merging included helper `emit` maps in include-list order
  1. merging the local map (`shared_emit` for profile, `emit` for class map)

- Any duplicate OCSF field key across the merge inputs MUST cause the mapping pack to be rejected
  (fail closed). Collisions are not resolved by precedence.

#### Transform extension files (normative)

Transform extension files are YAML files under `transforms/` that contribute additional `constants`
and `transforms` definitions to the effective canonicalization model.

Transforms extension file schema:

```yaml
format_version: 1

constants:
  <constant_set_name>:
    - <value>
    - <value>

transforms:
  <transform_name>:
    kind: <transform_kind>
    op: <operation_name>
    args:
      <arg_name>: <arg_value>
```

Rules:

- `constants` MAY be omitted.
- `transforms` MAY be omitted.
- Transform extension files MUST NOT declare `includes` (no nested transform includes in v0.1).

Including transform extensions in `canonicalization.yaml`:

`canonicalization.yaml` MAY include transform extension files via:

```yaml
includes:
  transforms:
    - transforms/<name>.yaml
    - transforms/<name>.yaml
```

Transform merge semantics (normative):

- The effective canonicalization model is computed by merging, in order:

  1. `constants` and `transforms` from each included transform extension file
  1. `constants` and `transforms` from `canonicalization.yaml`

- Any collision in `constants` set name (same key defined more than once) MUST fail closed.

- Any collision in `transform` name (same key defined more than once) MUST fail closed.

#### Lookup maps (normative)

Lookup maps are YAML files under `maps/` used by deterministic lookup operations.

Map file schema:

```yaml
format_version: 1

map:
  "<key_string>": <value>
```

Rules:

- `map` keys MUST be YAML strings.

  - Numeric-looking keys MUST be explicitly quoted (example: `"6"`, `"0x10"`).

- `map` values MUST be one of:

  - YAML string
  - YAML integer
  - YAML null (meaning "emit absent")

Map files MUST NOT declare `includes`.

##### Standard lookup operation (normative)

Transform op: `map_lookup`

A transform with `op: map_lookup` MUST behave as follows:

- Input:

  - If the input is absent or null, the output is absent.
  - If the input is a string, the lookup key is the input string as-is.
  - If the input is an integer, the lookup key is the base-10 string representation of that integer.
  - Any other input type MUST cause the transform to fail closed.

- Args:

  - `map_ref` (required): pack path to a `maps/*.yaml` file
  - `default` (optional): a scalar or null used when the key is not found

- Behavior:

  - Load `map_ref` and look up the derived key by exact match.

  - If key is present:

    - if the mapped value is null, output is absent
    - else output is the mapped value

  - If key is absent:

    - if `default` is present and null, output is absent
    - if `default` is present and non-null, output is `default`
    - else output is absent

Any `maps/*.yaml` file referenced by `map_ref` affects emission and MUST be included in the mapping
material boundary.

#### Mapping material closure (normative)

For mapping pack conformance validation and `normalized/mapping_profile_snapshot.json` enumeration,
a file under `helpers/`, `maps/`, or `transforms/` affects emission if and only if it is reachable
from `profile.yaml` by the following reference graph:

1. `profile.yaml`
1. `profile.yaml includes.canonicalization`
1. `profile.yaml includes.routing`
1. `profile.yaml includes.helpers[]` (optional)
1. `routing.yaml routes[].class_map`
1. each class map file `includes.helpers[]` (optional)
1. `canonicalization.yaml includes.transforms[]` (optional)
1. any `maps/*.yaml` referenced by any effective transform with `op: map_lookup` via `args.map_ref`

No other cross-file reference mechanisms are supported by this guide. Any unrecognized attempt to
reference external files MUST cause pack rejection (fail closed).

#### CI conformance validations (normative)

CI mapping pack conformance tooling MUST implement the following validations in addition to existing
parse, routing, and coverage checks:

Reference validity and containment:

- Every pack path reference MUST satisfy pack path requirements.
- Every referenced file MUST exist, be a regular file, and be inside the mapping pack root
  directory.
- Any symlink encountered among referenced files MUST fail closed.

Include list determinism:

- All include lists MUST be strictly sorted ascending by UTF-8 bytewise lexical order.
- Include lists MUST NOT contain duplicates.

Merge correctness:

- Helper merge MUST be collision-free:

  - duplicate OCSF field keys across merged helper emits or between helper emits and local emits
    MUST fail closed.

- Canonicalization merge MUST be collision-free:

  - duplicate `constants` set names MUST fail closed.
  - duplicate `transform` names MUST fail closed.

Lookup map correctness:

- For every transform using `op: map_lookup`:

  - `args.map_ref` MUST be present and MUST be a pack path under `maps/`.
  - the referenced map file MUST parse and satisfy the map file schema.

Snapshot completeness and ordering:

When the normalizer emits `normalized/mapping_profile_snapshot.json` using `mapping_files[]`:

- `mapping_files[]` MUST include exactly one `{path, sha256}` entry for each file in the mapping
  material closure defined in this section.
- `mapping_files[]` MUST be sorted in ascending UTF-8 bytewise lexical order by `path`.
- Each `sha256` MUST be computed over the exact file bytes in the repository checkout.

Required conformance fixtures:

CI MUST include fixtures that assert deterministic failure for:

1. A helper include that introduces a duplicate OCSF field key.
1. A transform extension include that introduces a duplicate transform name.
1. An include path containing `..`, beginning with `/`, or beginning with `./`.
1. A `map_lookup` transform referencing a missing `maps/*.yaml`.
1. An unsorted include list for any include list defined by this guide.

______________________________________________________________________

### Mapping rule object (normative)

Mapping rules are used in `profile.shared_emit`, helper fragment `emit`, and class map `emit`.

A mapping rule MUST be a YAML mapping object and MUST use exactly one of the following primary
forms:

1. **Direct field mapping**

   - Required: `from` (string raw field path)
   - Optional: `transforms` (list of transform names)

1. **Constant**

   - Required: `const` (scalar)

1. **Computed value**

   - Required: `op` (string operation name)
   - Optional: `args` (object)

1. **Reference to class map static fields**

   - Required: `const_from_class: true`

1. **Reference to per-routing-key classification**

   - Required: `from_event_id_map` (string key name within `class_map.event_id_map[routing_key]`)

Conditional application:

A mapping rule MAY include a `when` object to make the rule conditional. `when` applies to the whole
rule.

Supported `when` predicates (v0.1):

- `event_id_in`: list of routing keys (numeric event ids or query name strings)

If `when` evaluates to false, the field MUST be absent (not null) in the emitted output.

Validation:

- A mapping rule MUST NOT specify more than one primary form at the same time.
- Unknown keys in a mapping rule MUST be rejected (fail closed).
- If `transforms` is present, it MUST be a list of strings. Each referenced transform MUST exist in
  the effective canonicalization model.

______________________________________________________________________

### profile.yaml (required)

The profile file is the entry point for a mapping pack. It defines metadata, input expectations,
shared output rules, and identity computation.

```yaml
# mappings/normalizer/ocsf/<ocsf_version>/<source_pack_id>/profile.yaml
format_version: 1

profile:
  profile_id: <source_pack_id>_to_ocsf_<ocsf_version>  # MUST be globally unique
  profile_version: <semver>                             # e.g., "0.1.0"
  ocsf_version: "<ocsf_version>"                        # e.g., "1.7.0"

source:
  source_pack_id: <source_pack_id>                      # MUST match directory name
  event_source_type: <event_source_type>                # Emitted to metadata.source_type for all events

  # Optional routing discriminators (Windows Event Log sources).
  provider: <provider_name>                             # e.g., "Microsoft-Windows-Security-Auditing"
  channel: <channel_name>                               # e.g., "Security"

  # Optional provenance labels (recommended)
  product_name: <string>                                # e.g., "windows_eventlog", "sysmon", "osquery"
  log_name: <string>                                    # e.g., "Security"

inputs:
  raw_shape_version: <int>                              # Schema version for expected raw input
  required_fields:                                      # Fields that MUST be present in raw input
    - <raw_field_path_1>
    - <raw_field_path_2>

includes:
  canonicalization: canonicalization.yaml               # REQUIRED: relative pack path
  routing: routing.yaml                                 # REQUIRED: relative pack path
  helpers:                                               # OPTIONAL: helper fragments for shared_emit
    - helpers/<name>.yaml

shared_emit:
  # Field mappings applied to ALL routed events before class-specific mappings.
  time:
    from: <raw_time_field_path>
    transforms: [parse_epoch_s_to_epoch_ms]

  metadata.source_type:
    const: <event_source_type>

  metadata.source_event_id:
    from: <raw_source_event_id_path>
    transforms: [to_string]

identity:
  algorithm: "pa:eid:v1"                                # Fixed. MUST match ADR-0002.
  identity_source_type: <identity_source_type>          # Optional if derived by routing rules
  basis:
    source_type_const: <value>
    origin.<basis_field_1>_from: <raw_field_path_1>
    origin.<basis_field_2>_from: <raw_field_path_2>
  prehash_normalization:
    origin.<basis_field_1>: [trim_ascii]

outputs:
  set_uid_equal_event_id: true                          # MUST be true per Tier 0 contract
```

#### Profile rules (normative)

- `format_version` MUST be `1`. Unknown versions MUST fail closed.

- `profile.profile_id` MUST be globally unique and follow pattern
  `<source_pack_id>_to_ocsf_<ocsf_version>`.

- `profile.ocsf_version` MUST match:

  - the directory `<ocsf_version>`, and
  - the pinned version in the [OCSF normalization specification](../spec/050_normalization_ocsf.md).

- `source.source_pack_id` MUST equal the `<source_pack_id>` directory name.

- `source.event_source_type` MUST be emitted to `metadata.source_type` for all events produced by
  this pack.

- For Windows Event Log sources, `source.provider` and `source.channel` MUST be set and MUST match
  the corresponding values in `routing.yaml`.

- For osquery-style sources, `source.provider` and `source.channel` MUST be omitted or null and MUST
  NOT participate in routing decisions.

- `includes.canonicalization` MUST be `canonicalization.yaml`.

- `includes.routing` MUST be `routing.yaml`.

- If `includes.helpers[]` is present, it MUST obey include list ordering rules.

- `identity.algorithm` MUST be `"pa:eid:v1"` and MUST conform to ADR-0002.

- If `identity.identity_source_type` is present, it MUST be the value used for
  `identity_basis.source_type` as defined by ADR-0002.

- If `identity.identity_source_type` is not present, the mapping pack MUST define deterministic
  rules to derive `identity_basis.source_type` from routing discriminators.

- `outputs.set_uid_equal_event_id` MUST be `true` to satisfy `metadata.uid = metadata.event_id`
  contract. This behavior is not configurable per profile.

______________________________________________________________________

### canonicalization.yaml (required)

Defines reusable transforms for deterministic field processing.

```yaml
# mappings/normalizer/ocsf/<ocsf_version>/<source_pack_id>/canonicalization.yaml
format_version: 1

includes:
  transforms:
    - transforms/<name>.yaml

constants:
  placeholder_values:
    - ""
    - "-"
    - "NULL"
    - "null"
    - "(null)"
    - "N/A"

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
```

#### Canonicalization rules (normative)

- `format_version` MUST be `1`. Unknown versions MUST fail closed.
- `includes.transforms[]` is OPTIONAL. If present, it MUST obey include list ordering rules.
- The effective canonicalization model MUST be merged as defined in
  [Transform extension files](#transform-extension-files-normative).
- All transforms referenced by mapping rules MUST exist in the effective canonicalization model.
- Transforms MUST be deterministic and MUST NOT depend on external environment state (time, host,
  network, filesystem, or random source), except where explicitly defined by the normalizer as
  deterministic pure functions.

______________________________________________________________________

### routing.yaml (required)

Defines how raw events are routed to class-specific mapping files.

```yaml
# mappings/normalizer/ocsf/<ocsf_version>/<source_pack_id>/routing.yaml
format_version: 1

routing:
  # For Windows Event Log sources, these MUST match profile.yaml source.provider/source.channel.
  provider: <provider_name>
  channel: <channel_name>

routes:
  - route_id: <unique_route_id>
    match:
      event_ids: [4624, 4625]
    class_map: classes/authentication_3002.yaml
```

For osquery-style routing, `match.query_names` MUST be used instead of `match.event_ids`:

```yaml
routes:
  - route_id: osq_process_events
    match:
      query_names: ["processes", "process_open_sockets"]
    class_map: classes/process_activity_1007.yaml
```

#### Routing rules (normative)

- `format_version` MUST be `1`. Unknown versions MUST fail closed.

- Each `route_id` MUST be unique within the file.

- Each `routes[].class_map` MUST be a pack path and MUST be under `classes/`.

- `match` MUST specify exactly one of:

  - `event_ids`, or
  - `query_names`

- `match.event_ids`:

  - MUST contain only integers
  - MUST be strictly ascending numeric order
  - MUST contain no duplicates

- `match.query_names`:

  - MUST contain only strings
  - MUST be strictly ascending UTF-8 bytewise lexical order
  - MUST contain no duplicates

- Match criteria MUST be mutually exclusive across routes:

  - no event id may appear in more than one route
  - no query name may appear in more than one route

- Route evaluation order MUST be the order of entries in `routes[]`.

- Unmatched events MUST NOT be silently dropped. For each unmatched event, the normalizer MUST:

  - increment `unmapped` counters in mapping coverage (`normalized/mapping_coverage.json`), and
  - emit a stage outcome reason code indicating an unmapped event (see
    [ADR-0005 Stage outcomes and failure classification](../adr/ADR-0005-stage-outcomes-and-failure-classification.md)).

- The raw event payload SHOULD be retained per Tier R guidance (see
  [OCSF field tiers reference](../spec/055_ocsf_field_tiers.md)).

- Implementations MUST validate at load time that match criteria are mutually exclusive across
  routes. If overlap exists, the mapping pack MUST be rejected (fail closed).

______________________________________________________________________

### Class map files (required per routed class)

Each OCSF class that the mapping pack can emit MUST have a dedicated class map file.

```yaml
# mappings/normalizer/ocsf/<ocsf_version>/<source_pack_id>/classes/<class_name>_<class_uid>.yaml
format_version: 1

includes:
  helpers:
    - helpers/<name>.yaml

class_map:
  class_uid: 3002
  class_name: "Authentication"
  category_uid: 3

  event_id_map:
    "4624":
      activity_id: 1
      status_id: 1
    "4625":
      activity_id: 1
      status_id: 2

emit:
  class_uid:
    const_from_class: true

  activity_id:
    from_event_id_map: activity_id

  status_id:
    from_event_id_map: status_id

  type_uid:
    op: compute_type_uid
    args:
      class_uid_from_class: true
      activity_id_from_event_id_map: true

  actor.user.uid:
    from: <raw_actor_user_id_path>
    transforms: [to_string, absent_if_placeholder]

  metadata.product.name:
    const: <string>

no_inference:
  forbidden_derivations:
    - "actor.process.pid derived from non-authoritative heuristic"
```

> Note: Implementations MUST treat `no_inference.forbidden_derivations[]` as documentation only
> unless an explicit enforcement mechanism is implemented. If enforcement is implemented, it MUST be
> deterministic and MUST fail closed in CI when violated.

#### Class map rules (normative)

- `format_version` MUST be `1`. Unknown versions MUST fail closed.

- `class_map.class_uid` MUST match the pinned OCSF 1.7.0 schema.

- `class_map.category_uid` MUST be set correctly for the class family:

  - `1` = System Activity (Process, File, Event Log)
  - `3` = Identity & Access Management (Authentication, Account Change, Group Management)
  - `4` = Network Activity (Network, DNS)

- `includes.helpers[]` is OPTIONAL. If present, it MUST obey include list ordering rules.

- `class_map.event_id_map` MUST include an entry for every routing key routed to this class via
  `routing.yaml`. The routing key is:

  - the matched event id for `match.event_ids`, or
  - the matched query name for `match.query_names`

- `activity_id` MUST follow OCSF 1.7.0 enum values for the class.

- `type_uid` MUST be computed as `class_uid - 100 + activity_id`.

- In the in-memory mapping model, `event_id_map` keys MUST be represented as strings, even if YAML
  provides integers. This prevents ambiguity across sources where identifiers may be numeric
  (Windows) or symbolic (osquery query names).

- `emit` MUST NOT populate any Tier 1 or Tier 2 field by inventing values not present in raw input.
  Deterministic transforms of authoritative raw values are allowed. If an authoritative raw value is
  absent, the output field MUST be absent.

#### Field mapping syntax (non-exhaustive)

```yaml
emit:
  <ocsf_path>:
    from: <raw_path>
    transforms: [trim_ascii, absent_if_placeholder]

  <ocsf_path>:
    const: <value>

  <ocsf_path>:
    when:
      event_id_in: ["4624"]
    from: <raw_path>
    transforms: [to_string]

  <ocsf_path>:
    op: <operation>
    args:
      <arg>: <value>

  <ocsf_path>:
    const_from_class: true

  <ocsf_path>:
    from_event_id_map: <key>
```

______________________________________________________________________

## Authoring workflow

### Step 1: Gather requirements

Before creating a mapping pack, collect:

1. **Source documentation**: raw event schema, field definitions, event catalog (event ids or query
   names).
1. **Coverage matrix requirements**: which Tier 1/2 fields are `R` (required) for this source.
1. **Spec document references**: the human-readable mapping profile doc (example:
   `windows-security_to_ocsf_1.7.0.md`).
1. **OCSF schema reference**: class definitions, activity ids, field types for OCSF 1.7.0.

### Step 2: Create directory structure

```bash
mkdir -p mappings/normalizer/ocsf/1.7.0/<source_pack_id>/classes
touch mappings/normalizer/ocsf/1.7.0/<source_pack_id>/profile.yaml
touch mappings/normalizer/ocsf/1.7.0/<source_pack_id>/canonicalization.yaml
touch mappings/normalizer/ocsf/1.7.0/<source_pack_id>/routing.yaml
```

### Step 3: Author canonicalization.yaml

1. Start with the standard transforms template (see `canonicalization.yaml` requirements).
1. Add source-specific transforms as needed (either directly or under `transforms/` using includes).
1. Define placeholder constants for the source.

### Step 4: Author profile.yaml

1. Set profile metadata (`profile_id`, `profile_version`, `ocsf_version`).

1. Set source identifiers:

   - `source_pack_id` (directory name)
   - `event_source_type` (emitted to `metadata.source_type`)
   - `identity_source_type` (explicit or derived per deterministic rules)

1. Define source discriminators as applicable:

   - Windows Event Log: `provider`, `channel`
   - osquery: omit or null

1. List required input fields.

1. Define `shared_emit` rules for fields common to all events:

   - `time` (REQUIRED)
   - `metadata.source_type` (REQUIRED)
   - `metadata.source_event_id` (REQUIRED)
   - `device.name`, `device.hostname` (REQUIRED for Tier 1 where applicable)
   - `metadata.log_provider`, `metadata.log_name`, `metadata.product.name` (RECOMMENDED)

1. Define identity basis per ADR-0002.

### Step 5: Author routing.yaml

1. List all routing keys to be routed:

   - Windows Event Log: event ids
   - osquery: query names

1. Group related items into routes (example: auth events in one route).

1. Reference class map files (create placeholders if needed).

### Step 6: Author class map files

For each routed class:

1. Create `classes/<class_name>_<class_uid>.yaml`.
1. Set `class_uid`, `class_name`, `category_uid`.
1. Define `event_id_map` with `activity_id` and (optionally) `status_id` per routing key.
1. Map required fields per coverage matrix.
1. Add `no_inference` guardrails describing forbidden derivations.

### Step 7: Validate

1. **Schema validation**: each YAML file MUST be valid YAML and conform to this guide’s schemas.
1. **Reference integrity**: all referenced pack paths MUST exist and be contained in the pack.
1. **Transform references**: all transforms in mapping rules MUST exist in the effective
   canonicalization model.
1. **Coverage matrix alignment**: all `R` fields for the source MUST have mappings.
1. **OCSF compliance**: `class_uid`, `activity_id`, `category_uid` MUST match OCSF 1.7.0.

______________________________________________________________________

## OCSF class reference (v1.7.0)

Note: This section is a convenience index. Implementations MUST treat the pinned OCSF schema as the
source of truth for class UIDs, category UIDs, and activity enums.

### Common classes and activity IDs

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

### Status IDs (common)

| `status_id` | Meaning |
| ----------- | ------- |
| 0           | Unknown |
| 1           | Success |
| 2           | Failure |
| 99          | Other   |

______________________________________________________________________

## Transform reference (non-exhaustive)

### String transforms

| Transform               | Input       | Output     | Notes                                     |
| ----------------------- | ----------- | ---------- | ----------------------------------------- |
| `trim_ascii_whitespace` | `"  foo  "` | `"foo"`    | Removes leading/trailing ASCII whitespace |
| `lowercase_ascii`       | `"FooBar"`  | `"foobar"` | ASCII lowercase only                      |
| `uppercase_ascii`       | `"FooBar"`  | `"FOOBAR"` | ASCII uppercase only                      |

### Scalar transforms

| Transform              | Input              | Output  | Notes                            |
| ---------------------- | ------------------ | ------- | -------------------------------- |
| `to_string`            | `123`              | `"123"` | Convert to string representation |
| `parse_int`            | `"123"`            | `123`   | Parse base-10 integer            |
| `parse_hex_or_dec_int` | `"0x1A"` or `"26"` | `26`    | Parse hex (0x prefix) or decimal |

### Time transforms

| Transform                   | Input                    | Output          | Notes                         |
| --------------------------- | ------------------------ | --------------- | ----------------------------- |
| `parse_rfc3339_to_epoch_ms` | `"2026-01-11T12:00:00Z"` | `1768161600000` | RFC3339 to epoch milliseconds |
| `parse_epoch_s_to_epoch_ms` | `1768161600`             | `1768161600000` | Multiply by 1000              |

### Presence transforms

| Transform          | Args                                    | Behavior                         |
| ------------------ | --------------------------------------- | -------------------------------- |
| `absent_if_in_set` | `set_ref: constants.placeholder_values` | Return absent if value is in set |
| `absent_if_null`   | none                                    | Return absent if value is null   |

### Network transforms

| Transform           | Input           | Output          | Notes                              |
| ------------------- | --------------- | --------------- | ---------------------------------- |
| `normalize_ip_text` | `"192.168.1.1"` | `"192.168.1.1"` | Normalize IP; MUST NOT resolve DNS |

______________________________________________________________________

## Field path conventions

### Raw input paths

Raw field paths use dot notation to navigate nested structures:

```yaml
from: event_data.TargetUserSid
from: columns.pid
from: hostIdentifier
```

### OCSF output paths

OCSF field paths follow the OCSF schema structure:

```yaml
actor.user.uid
actor.user.name
actor.process.pid
process.pid
src_endpoint.ip
dst_endpoint.port
file.path
file.name
file.parent_folder
metadata.source_event_id
```

______________________________________________________________________

## Validation checklist

### Run provenance and hashing (normative)

#### Relationship to normalized/mapping_profile_snapshot.json

For every run that performs normalization, the orchestrator/normalizer MUST emit
`normalized/mapping_profile_snapshot.json` as Tier 0 provenance per the
[data contracts specification](../spec/025_data_contracts.md).

The mapping pack authored by this guide MUST be fully represented in the snapshot using one of:

1. `mapping_material` (embedded canonical representation), or
1. `mapping_files[]` (preferred for YAML-based packs)

#### mapping_files[] requirements (preferred)

When using `mapping_files[]`, the snapshot MUST include SHA-256 entries for:

- `profile.yaml`
- `routing.yaml`
- `canonicalization.yaml`
- all routed `classes/*.yaml`
- the deterministic closure of referenced files under `helpers/`, `maps/`, and `transforms/` as
  defined by [Mapping material closure](#mapping-material-closure-normative)

Each `mapping_files[].path` MUST be:

- repository-relative
- normalized to POSIX separators (`/`)
- stable across operating systems
- sorted ascending by UTF-8 bytewise lexical order

Each `mapping_files[].sha256` MUST be computed over the exact file bytes as stored in the repository
checkout.

Before submitting a mapping pack, verify:

### Structure

- [ ] Directory structure matches the directory structure section
- [ ] All required files exist (`profile.yaml`, `canonicalization.yaml`, `routing.yaml`)
- [ ] Class map files exist for all routed classes

### Profile

- [ ] `profile.profile_id` is unique and follows naming convention
- [ ] `profile.ocsf_version` matches directory path
- [ ] `source.source_pack_id` matches directory name
- [ ] `outputs.set_uid_equal_event_id: true` is set

### Routing

- [ ] Every route uses exactly one of `event_ids` or `query_names`
- [ ] No overlapping matches across routes
- [ ] All `class_map` paths resolve to existing files under `classes/`
- [ ] `event_ids` and `query_names` lists are sorted and contain no duplicates

### Class maps

- [ ] `class_uid` matches OCSF 1.7.0 schema
- [ ] `category_uid` is correct for the class family
- [ ] `event_id_map` covers all routing keys routed to this class
- [ ] `activity_id` values match OCSF 1.7.0 enum
- [ ] `type_uid` computation is defined and deterministic

### Coverage matrix alignment

- [ ] All `R` (Required) fields from coverage matrix have mappings
- [ ] `N/A` fields are not mapped
- [ ] No invented values for Tier 1 or Tier 2 fields

### Composition and transforms

- [ ] All referenced transforms exist in the effective canonicalization model
- [ ] `includes.helpers[]` and `includes.transforms[]` lists are sorted and have no duplicates
- [ ] Helper merges are collision-free (no duplicate OCSF field keys)
- [ ] Transform merges are collision-free (no duplicate constant set names or transform names)
- [ ] `map_lookup` references resolve to valid `maps/*.yaml` files

### Provenance (Tier 0)

- [ ] `normalized/mapping_profile_snapshot.json` includes this mapping pack as `mapping_files[]` or
  embedded `mapping_material`
- [ ] The file set included in the snapshot matches the mapping material boundary and closure rules
- [ ] No mapping files are referenced outside the mapping pack directory

______________________________________________________________________

## Examples

### Example: Adding a new event id to an existing class (Windows Security)

To add Windows Security event 4672 (Special Privileges Assigned) to the Authentication class:

1. Update `routing.yaml`:

```yaml
routes:
  - route_id: winsec_authentication
    match:
      event_ids: [4624, 4625, 4634, 4647, 4672]
    class_map: classes/authentication_3002.yaml
```

2. Update `classes/authentication_3002.yaml`:

```yaml
class_map:
  event_id_map:
    "4624": {activity_id: 1, status_id: 1}
    "4625": {activity_id: 1, status_id: 2}
    "4634": {activity_id: 2, status_id: 1}
    "4647": {activity_id: 2, status_id: 1}
    "4672": {activity_id: 99, status_id: 1}
```

### Example: Creating a new class map using helper fragments and transform extensions

Helper fragment:

```yaml
# helpers/common_metadata.yaml
format_version: 1

emit:
  metadata.log_name:
    const: "Security"
```

Transform extension:

```yaml
# transforms/path_extract.yaml
format_version: 1

transforms:
  extract_basename:
    kind: string
    op: extract_basename

  extract_parent_folder:
    kind: string
    op: extract_parent_folder
```

Canonicalization include:

```yaml
# canonicalization.yaml
format_version: 1

includes:
  transforms:
    - transforms/path_extract.yaml

transforms:
  trim_ascii:
    kind: string
    op: trim_ascii_whitespace
```

Class map:

```yaml
# classes/file_system_activity_1001.yaml
format_version: 1

includes:
  helpers:
    - helpers/common_metadata.yaml

class_map:
  class_uid: 1001
  class_name: "File System Activity"
  category_uid: 1

  event_id_map:
    "CREATE_FILE": {activity_id: 1, status_id: 1}
    "DELETE_FILE": {activity_id: 4, status_id: 1}
    "MODIFY_FILE": {activity_id: 3, status_id: 1}

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
```

______________________________________________________________________

## Appendix: Source-specific notes

### Windows Event Log sources

- Raw field paths commonly use `event_data.<FieldName>` for EventData elements.
- Placeholder values: `"-"`, `"NULL"`, `"(null)"` are common.
- PIDs may be hex (0x prefix) or decimal; use `parse_hex_or_dec_int`.
- SIDs MUST be preserved exactly (no normalization).

### osquery sources

- Routing key: query name (from the `name` field in results).
- Raw field paths commonly use `columns.<column_name>` for differential rows.
- Numeric fields are often string-typed; use `parse_int` as needed.
- Snapshot rows: `activity_id` SHOULD be `99` (Other) unless the OCSF class enum requires a specific
  value.

### Sysmon sources

- Raw field paths commonly use `event_data.<FieldName>`.
- Hash field: parse `KEY=VALUE,KEY=VALUE` format.
- Protocol field: preserve as string; do NOT convert to number.
- GUIDs: preserve exactly as emitted.

______________________________________________________________________

## References

- [OCSF normalization specification](../spec/050_normalization_ocsf.md): OCSF version pinning,
  envelope requirements
- [OCSF field tiers reference](../spec/055_ocsf_field_tiers.md): Tier model, coverage metrics
- [Coverage matrix](coverage_matrix.md): Per-source field requirements (R/O/N/A)
- [ADR-0002 Event identity and provenance](../adr/ADR-0002-event-identity-and-provenance.md): event
  identity and provenance
- [ADR-0003 Redaction policy](../adr/ADR-0003-redaction-policy.md): redaction policy
- [Mappings index](MAPPINGS_INDEX.md): index of `<source>_to_ocsf_1.7.0.md` mapping docs
