<!-- docs/mappings/coverage_matrix.md -->

# OCSF Field Mapping Completeness Matrix (v0.1 MVP)

This document defines a **mapping-profile conformance checklist** for the v0.1 normalizer.

It complements (and is referenced by) `docs/spec/055_ocsf_field_tiers.md`:

- `055` defines the **tier model** and run-level Tier 1 coverage metric.
- This file defines **which Tier 1 and Tier 2 field paths the mapping profiles MUST be able to
  populate**, per `source_type`, when authoritative input is present.

This matrix is intended to make normalizer implementation deterministic and to enable CI to verify
mapping completeness using fixtures.

______________________________________________________________________

## Scope

In scope `source_type` rows (v0.1 MVP):

- Windows Security (Windows Event Log: Security channel)
- Sysmon
- osquery
- auditd

Out of scope for this v0.1 matrix:

- Network sensor sources (Zeek, Suricata, firewall logs)
- EDR “findings” sources (alerts/notables), unless explicitly added as a v0.1 source

______________________________________________________________________

## Cell semantics (normative)

Each cell is one of: `R`, `O`, `N/A`.

- `R` (Required mapping target)

  - The mapping profile **MUST** populate the field **when an authoritative value exists** in:
    - the raw event payload, or
    - deterministic run context (example: host identity derived from inventory), or
    - deterministic local context snapshotted into the run (example: `/etc/passwd` snapshot if you
      choose to support UID→name).
  - The mapping profile **MUST NOT** infer or fabricate semantic values that are not present.
  - If the source provides an explicit “unknown” marker, the mapping profile **MAY** emit an
    explicit unknown convention, provided it is deterministic and tested.

- `O` (Optional mapping target)

  - Populate when present and low-cost; absence does not fail mapping completeness.

- `N/A`

  - The field is not applicable for that source, and **MUST remain absent**.

### “Authoritative value exists” (conformance rule)

A value is considered authoritative if it is:

- directly present in the raw record, or
- deterministically derived from run configuration or inventory that is snapshotted and versioned.

A value is not authoritative if it requires guesswork, heuristics with ambiguous outputs, external
network lookups, or locale-dependent parsing.

______________________________________________________________________

## Rationale codes

Rationale codes are included in `R` cells to keep the tables compact.

- `[C]` Classification needed for deterministic grouping/scoring (`category_uid`, `type_uid`,
  `severity_id`).
- `[H]` Host pivot required for joins across sources (`device.*`).
- `[U]` User pivot required for IAM detections and correlations (`actor.user.*`).
- `[P]` Process pivot required for endpoint behavior detections (`actor.process.*`).
- `[N]` Network pivot required for network-centric detections (`src_endpoint.*`, `dst_endpoint.*`).
- `[F]` File pivot required for file activity detections (`file.*`).

______________________________________________________________________

## Tier 1 matrix (Core Common)

### Relationship to Tier 0 (envelope contract)

This matrix covers Tier 1 (Core Common) fields only. Tier 0 (Core Envelope) fields are
contract-required per `055_ocsf_field_tiers.md` and are not repeated here. Key Tier 0 requirements:

- `metadata.uid` MUST equal `metadata.event_id` (ADR-0002).
- `metadata.run_id`, `metadata.scenario_id`, `metadata.source_type` MUST be present.
- See `055` for the complete Tier 0 field list.

Tier 1 is “core common” per `055`. This matrix makes Tier 1 **mapping-profile-checkable**.

Notes:

- Some Tier 1 fields are “conditionally applicable” for a given `source_type`. Where that is common,
  the cell is `O` and the Tier 2 family tables define the stricter requirements.
- For the device IP pivot, implementations vary between a scalar `device.ip` and an array
  `device.ips[]`. For conformance to this matrix:
  - The normalizer **SHOULD** emit `device.ips[]`.
  - If only a single IP is known, emitting `device.ip` alone is permitted, but CI conformance checks
    **SHOULD** treat `device.ip` as satisfying the IP pivot requirement.

| source_type      | category_uid | type_uid | severity_id | device.hostname | device.uid | device.(ip\|ips[]) | actor.user.name | actor.user.uid | actor.process.name | actor.process.pid | message | observables[] |
| ---------------- | ------------ | -------- | ----------- | --------------- | ---------- | ------------------ | --------------- | -------------- | ------------------ | ----------------- | ------- | ------------- |
| Windows Security | R[C]         | R[C]     | O[C]        | R[H]            | R[H]       | O[H]               | R[U]            | R[U]           | O[P]               | O[P]              | O       | O             |
| Sysmon           | R[C]         | R[C]     | O[C]        | R[H]            | R[H]       | O[H]               | O[U]            | O[U]           | R[P]               | R[P]              | O       | O             |
| osquery          | R[C]         | R[C]     | O[C]        | R[H]            | R[H]       | O[H]               | O[U]            | O[U]           | R[P]               | R[P]              | O       | O             |
| auditd           | R[C]         | R[C]     | O[C]        | R[H]            | R[H]       | O[H]               | O[U]            | R[U]           | O[P]               | R[P]              | O       | O             |

Tier 1 rationale notes (per row):

- **Windows Security**

  - `actor.user.*` is required because the Security channel is the v0.1 source of record for
    authentication and authorization outcomes.
  - `actor.process.*` is optional because many Security events do not include stable process
    attribution.

- **Sysmon**

  - `actor.process.*` is required because Sysmon is the v0.1 primary source for process creation and
    related process-context events.

- **osquery**

  - `actor.process.*` is required for the v0.1 routed tables `process_events` and `socket_events`.
    (See Tier 2 tables for per-family strictness.)

- **auditd**

  - `actor.user.uid` is required because auditd provides stable numeric principals (UID/AUID).
  - `actor.user.name` is optional because UID→name resolution requires an explicit deterministic
    context snapshot if you choose to support it.

______________________________________________________________________

## Tier 2 matrices (Core Class Minimums used in v0.1)

Tier 2 requirements apply **when the event is mapped into the corresponding family/class** (per
`055` Tier 2).

To keep CI implementable, Tier 2 is expressed as a small set of family-specific tables.

### Tier 2A: Authentication and authorization (Windows Security)

| source_type      | actor.user.name | actor.user.uid | status_id | src_endpoint.ip | src_endpoint.port | target.user.name | target.user.uid |
| ---------------- | --------------- | -------------- | --------: | --------------- | ----------------- | ---------------- | --------------- |
| Windows Security | R[U]            | R[U]           |      R[C] | O[N]            | O[N]              | O[U]             | O[U]            |
| Sysmon           | N/A             | N/A            |       N/A | N/A             | N/A               | N/A              | N/A             |
| osquery          | N/A             | N/A            |       N/A | N/A             | N/A               | N/A              | N/A             |
| auditd           | O[U]            | R[U]           |      O[C] | N/A             | N/A               | N/A              | N/A             |

Notes:

- `status_id` represents the success/failure (or equivalent) outcome representation referenced in
  `055` Tier 2B.
- `src_endpoint.*` is optional because only a subset of Windows Security auth events include a
  remote source address/port.
- `target.user.*` is optional because not all auth events have a distinct target principal beyond
  `actor.user`.

### Tier 2B: Process and execution activity (Windows Security, Sysmon, osquery, auditd)

| source_type      | activity_id | actor.process.name | actor.process.pid | actor.process.cmd_line | actor.process.parent_process.pid | actor.user.uid | actor.user.name |
| ---------------- | ----------- | ------------------ | ----------------- | ---------------------- | -------------------------------- | -------------- | --------------- |
| Windows Security | R[C]        | O[P]               | O[P]              | O[P]                   | O[P]                             | R[U]           | R[U]            |
| Sysmon           | R[C]        | R[P]               | R[P]              | R[P]                   | R[P]                             | O[U]           | O[U]            |
| osquery          | R[C]        | R[P]               | R[P]              | R[P]                   | O[P]                             | O[U]           | O[U]            |
| auditd           | R[C]        | O[P]               | R[P]              | O[P]                   | O[P]                             | R[U]           | O[U]            |

Notes:

- `activity_id` is required because it determines `type_uid` computation
  (`class_uid * 100 + activity_id`) and is needed for deterministic downstream routing and scoring.
- For Process Activity (`class_uid = 1007`), OCSF 1.7.0 uses: `1 = Launch`, `2 = Terminate`,
  `0 = Unknown`.
- Sysmon requires process pivots because it is the primary v0.1 source for endpoint behavior
  detections.
- auditd often provides executable path rather than a clean process name. Mapping profiles may
  choose to populate `actor.process.name` from the basename of an executable path only if this
  derivation is explicitly defined and tested.

### Tier 2C: Network and connection activity (Sysmon, osquery)

| source_type      | src_endpoint.ip | src_endpoint.port | dst_endpoint.ip | dst_endpoint.port |
| ---------------- | --------------- | ----------------- | --------------- | ----------------- |
| Windows Security | N/A             | N/A               | N/A             | N/A               |
| Sysmon           | R[N]            | R[N]              | R[N]            | R[N]              |
| osquery          | R[N]            | O[N]              | R[N]            | O[N]              |
| auditd           | O[N]            | O[N]              | O[N]            | O[N]              |

Notes:

- Ports are required for Sysmon network events because Sysmon commonly provides them; they
  materially improve detection matching.
- For osquery `socket_events`, port availability depends on the table/back-end; treat as optional
  unless the raw provides them.

### Tier 2D: File system activity (Sysmon, osquery, auditd)

| source_type      | file.name | file.parent_folder | file.path | actor.process.pid | actor.process.name | actor.user.uid |
| ---------------- | --------: | -----------------: | --------: | ----------------: | -----------------: | -------------: |
| Windows Security |      O[F] |               O[F] |      O[F] |              O[P] |               O[P] |           O[U] |
| Sysmon           |      R[F] |               R[F] |      R[F] |              R[P] |               R[P] |           O[U] |
| osquery          |      R[F] |               R[F] |      O[F] |               N/A |                N/A |           O[U] |
| auditd           |      R[F] |               O[F] |      O[F] |              R[P] |               O[P] |           R[U] |

Notes:

- For **osquery `file_events`**, initiating process attribution is not available in v0.1. Therefore
  `actor.process.*` is `N/A` and **MUST NOT be inferred**. (This matches the “known mapping
  limitations” approach in `042_osquery_integration.md`.)
- `file.path` and `file.name`/`file.parent_folder` relationship:
  - When a source provides a full path (example: Sysmon `TargetFilename`), mapping profiles MUST
    populate `file.path` directly from the source.
  - Mapping profiles MUST also derive `file.name` (basename) and `file.parent_folder` (directory)
    using a deterministic split algorithm. The split MUST treat both `\` and `/` as path separators.
  - When only `file.name` or only `file.parent_folder` is authoritative (no full path), populate
    only the authoritative field(s).
  - `file.path` is marked `O[F]` for sources that do not always provide a full path (osquery
    `file_events` may have partial paths depending on configuration).
- For auditd file activity, `file.parent_folder` is optional because audit records may provide only
  a full path or inode-derived context depending on configuration. If only a full path is available,
  mapping profiles should deterministically split it into `parent_folder` and `name`.

______________________________________________________________________

## CI conformance requirements (how to verify this matrix)

To make this matrix mechanically checkable, v0.1 CI SHOULD include a fixture-backed conformance
suite.

### Fixture requirements (minimum set)

For each `source_type`, maintain a small raw fixture corpus that includes at least:

- Windows Security:
  - 1 successful auth event
  - 1 failed auth event
- Sysmon:
  - 1 process creation event
  - 1 network connection event
  - 1 file activity event
- osquery:
  - 1 `process_events` row
  - 1 `socket_events` row
  - 1 `file_events` row
- auditd:
  - 1 exec/process event
  - 1 network/socket event (optional; validates Tier 2C `O[N]` handling)
  - 1 file activity event

### Conformance assertions

For each fixture, the conformance test MUST assert:

- All `R` fields for the applicable Tier 1 row are present when the raw fixture provides an
  authoritative value.
- All `R` fields for the applicable Tier 2 family table are present.
- All `N/A` fields are absent (this is a determinism requirement, not merely a completeness rule).

Presence semantics should match `055` Tier 1 “Presence semantics”.

### Failure reporting (recommended)

When a conformance assertion fails, CI output SHOULD report:

- `source_type`
- fixture id
- expected field path
- whether the failure is `missing_required` or `present_but_na`
- a pointer to the normalized output event id(s) to reproduce

______________________________________________________________________

## Change control

This matrix is normative for v0.1 mapping completeness. Any change that modifies an `R`/`O`/`N/A`
cell SHOULD be treated as a compatibility-impacting change and MUST be accompanied by:

- updated fixtures (if required), and
- updated golden normalized outputs.
