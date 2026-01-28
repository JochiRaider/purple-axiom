---
title: 'OCSF field tiers: core vs extended'
description: Defines how Purple Axiom tiers OCSF fields for MVP normalization, validation gates, and safe raw retention.
status: draft
category: spec
tags: [ocsf, normalization, validation, scoring]
related:
  - 050_normalization_ocsf.md
  - 070_scoring_metrics.md
  - ../adr/ADR-0002-event-identity-and-provenance.md
---

# OCSF field tiers: core vs extended

This spec defines how Purple Axiom classifies OCSF fields into **Core** and **Extended** tiers, and
how unmapped or source-specific data is retained. The goal is to make the normalizer implementable
as an MVP, while ensuring outputs remain useful for detection scoring, investigation workflows, and
long-term storage.

This document is **normative** for Purple Axiom outputs. It does not attempt to restate the entire
OCSF specification.

## Overview

Purple Axiom tiers normalized event content to balance MVP feasibility with long-term fidelity. Tier
0 is contract-required for every normalized event. Tier 1 defines common pivots and adds a run-level
coverage gate. Tier 2 defines per-family minimums when a class is enabled. Tier 3 is enrichment that
MUST remain deterministic. Tier R defines redaction-safe raw retention.

Terminology note (normative):

- This document defines **field tiers** (FT0/FT1/FT2/FT3/FT-R) for normalization completeness and
  validation gating.
- `metadata.identity_tier` defines **identity tiers** (IT1/IT2/IT3) for event identity strength (see
  ADR-0002).
- Reports, gate names, and operator-facing text SHOULD qualify tier references as either "field
  tier" or "identity tier" (or use FT\*/IT\* shorthand). They SHOULD NOT use bare "Tier N" where
  ambiguity is possible.

## Goals

1. **Make MVP feasible**: define a small, stable Core set that every event should carry.
1. **Preserve fidelity**: never discard source information needed for future mapping or audits.
1. **Enable deterministic scoring**: ensure stable identity, provenance, and minimum pivot fields.
1. **Support incremental mapping**: allow Extended fields to grow without breaking historical runs.
1. **Make validation practical**: provide tiered validation expectations and coverage metrics.

## Non-goals

- Defining complete OCSF class schemas.
- Enforcing every OCSF-required field for every class in CI from day one.
- Mandating a specific storage layout (see storage spec), beyond field tier guidance.

## Definitions

### Core fields

Fields that Purple Axiom treats as the **minimum viable normalized event**. Core fields are split
into:

- **Core envelope**: required on every event (contract enforced).
- **Core common**: strongly recommended across all events when available.
- **Core class minimums**: recommended minimum objects/attributes for specific event families.

### Extended fields

Fields that materially improve analytics, correlation, triage, and reporting, but are not required
to produce a valid MVP. Extended mapping is expected to expand over time.

### Raw retention

Source-specific fields preserved to avoid data loss. These are retained under `raw` (and optionally
structured sub-objects), and are not required to be OCSF-conformant.

## Tier model

Purple Axiom uses the following tiers for implementation planning and validation gating.

| Tier | Name                | Description                                         | Expected timeline |
| ---: | ------------------- | --------------------------------------------------- | ----------------- |
|    0 | Core envelope       | Minimal contract required fields and provenance     | Day 1             |
|    1 | Core common         | Cross-cutting pivots and classification refinements | Early MVP         |
|    2 | Core class minimums | Minimum objects for each supported event family     | MVP to v1         |
|    3 | Extended            | Enrichment and completeness improvements            | Continuous        |
|    R | Raw retention       | Preserve unmapped source data safely                | Day 1             |

## Tier 0 core envelope

Every emitted normalized event MUST include the following fields.

### Required top-level fields

| Field       | Requirement | Notes                                                                                                                                                                       |
| ----------- | ----------: | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `time`      |        MUST | Event time in ms since epoch, UTC.                                                                                                                                          |
| `class_uid` |        MUST | The event class identifier (drives downstream routing and mapping coverage). If no OCSF class can be assigned deterministically, set `class_uid = 0` (reserved "unmapped"). |
| `metadata`  |        MUST | Provenance and stable identity.                                                                                                                                             |

### Required metadata fields

| Field                         | Requirement | Notes                                                                                                                                                                                                                                        |
| ----------------------------- | ----------: | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `metadata.uid`                |        MUST | OCSF unique event identifier. MUST equal `metadata.event_id`. See [Event identity and provenance ADR](../adr/ADR-0002-event-identity-and-provenance.md).                                                                                     |
| `metadata.event_id`           |        MUST | Purple Axiom deterministic event identifier (idempotency key). MUST equal `metadata.uid` in OCSF outputs. Format: `pa:eid:v1:<32 lowercase hex>`. See [Event identity and provenance ADR](../adr/ADR-0002-event-identity-and-provenance.md). |
| `metadata.run_id`             |        MUST | Run identifier (ties to manifest, ground truth, detections). MUST be an RFC 4122 UUID string in canonical hyphenated form, lowercase hex. See [Project naming and versioning ADR](../adr/ADR-0001-project-naming-and-versioning.md).         |
| `metadata.scenario_id`        |        MUST | Scenario identifier (ties to ground truth). MUST conform to `id_slug_v1`. See [Project naming and versioning ADR](../adr/ADR-0001-project-naming-and-versioning.md).                                                                         |
| `metadata.collector_version`  |        MUST | Collector build/version.                                                                                                                                                                                                                     |
| `metadata.normalizer_version` |        MUST | Normalizer build/version.                                                                                                                                                                                                                    |
| `metadata.source_type`        |        MUST | Source discriminator (example: `windows-security`, `windows-sysmon`, `osquery`, `linux-auditd`).                                                                                                                                             |
| `metadata.source_event_id`    |        MUST | Source-native upstream ID when present; else `null`. MUST be a string when non-null. For `metadata.identity_tier = 3`, this MUST be `null`. See [Event identity and provenance ADR](../adr/ADR-0002-event-identity-and-provenance.md).       |
| `metadata.identity_tier`      |        MUST | Identity tier used to compute `metadata.event_id` (`1` \| `2` \| `3`). This is distinct from the FT0/FT1/FT2/FT3/FT-R field tier model. See [Event identity and provenance ADR](../adr/ADR-0002-event-identity-and-provenance.md).           |

#### Provisional network telemetry source types (v0.1)

Spec 010 reserves pcap and NetFlow ingestion as placeholder contracts, but operators MAY enable
custom network sources. When doing so, normalized Network Activity events MUST still satisfy the
Tier 0 envelope requirements, including deterministic `metadata.event_id` and `metadata.uid`.

For v0.1, the following `metadata.source_type` values are reserved for custom network sources:

- `netflow` (NetFlow v5/v9, IPFIX-derived flow records)
- `pcap_flow` (flows derived from pcap or similar sessionization)
- `zeek_conn` (Zeek `conn.log` derived flow/session records)
- `suricata_eve` (Suricata EVE flow/session records)

Event identity for these sources is defined in ADR-0002 under “Network flows (provisional)”,
including an `identity_tier = 3` fallback based on 5-tuple plus flow start time.

### Strong recommendations

These fields SHOULD be included when available, but are not contract-required.

| Field                      | Recommendation | Notes                                                                                   |
| -------------------------- | -------------: | --------------------------------------------------------------------------------------- |
| `metadata.ingest_time_utc` |         SHOULD | Ingest time as RFC3339 UTC string (for example, `2026-01-04T17:00:01Z`) when available. |
| `metadata.host`            |         SHOULD | Collector host identity if helpful for pipeline debugging.                              |
| `metadata.pipeline`        |         SHOULD | Pipeline identifier (config profile, mapping version tag, etc.).                        |

## Tier 1 core common

These fields SHOULD be populated across most events when the source provides them or they can be
derived safely. They significantly improve correlation and detection evaluation.

### Tier 1 coverage metric and run health gate

Tier 1 fields remain **SHOULD** per event. However, the pipeline MUST compute a run-level Tier 1
coverage metric and apply a run health gate. This resolves the tension between SHOULD fields and
scoring or UX assumptions that rely on their availability for pivots.

#### Scope

The Tier 1 coverage computation MUST operate over the set of **in-scope normalized OCSF events**:

1. Start with normalized OCSF events emitted for the run (for example, the contents of
   `normalized/ocsf_events/`).
1. Exclude events that fail OCSF schema validation (invalid events are not counted in the coverage
   denominator).
1. If an execution window can be derived from the executed actions (ground truth timeline), then the
   in-scope set SHOULD be restricted to events whose event timestamp falls within:
   - `[min(action.start_time) - padding, max(action.end_time) + padding]`
   - `padding` default: 30 seconds
1. If an execution window cannot be derived, all normalized OCSF events for the run are in-scope.

This scoping rule ensures the metric reflects executed techniques rather than ambient background
telemetry.

#### Presence semantics

For each Tier 1 field (or field group) and each in-scope event:

- A field is **present** if the JSON key exists, its value is not `null`, and it satisfies the
  type-specific rules below.
- For strings, the value MUST be non-empty after trimming whitespace.
- For objects, the value may be empty and still counts as present (existence is the pivot
  requirement).
- For arrays, the value MUST contain at least one element to count as present.
- Numeric zero and boolean `false` count as present.

#### Tier 1 field set (F)

The Tier 1 run coverage metric is computed over a fixed, ordered Tier 1 field set `F`. `F` MUST
match the Tier 1 matrix column set in the [Mapping coverage matrix](../mappings/coverage_matrix.md).

`F` (ordered):

1. `category_uid`
1. `type_uid`
1. `severity_id`
1. `device.hostname`
1. `device.uid`
1. `device.(ip|ips[])` (present if either `device.ip` or `device.ips[]` is present)
1. `actor.user.name`
1. `actor.user.uid`
1. `actor.process.name`
1. `actor.process.pid`
1. `message`
1. `observables[]`

Notes:

- Implementations SHOULD prefer emitting `device.ips[]` for the device IP pivot (even when only a
  single IP is known). However, for coverage computation, `device.ip` MUST be treated as satisfying
  `device.(ip|ips[])` when `device.ips[]` is absent.

#### Coverage computation

Let:

- `E` be the set of in-scope normalized events.
- `F` be the Tier 1 field set defined in this document.
- `present(e, f)` be 1 if field `f` is present in event `e` by the rules above, else 0.

Then:

`tier1_field_coverage_pct = ( Σ_{e in E} Σ_{f in F} present(e,f) ) / ( |E| * |F| )`

Notes:

- Unit: `tier1_field_coverage_pct` is a unitless fraction in `[0.0, 1.0]` (despite `_pct`, it is not
  `0-100`).
- When emitted in regression comparable artifacts (for example, `normalized/mapping_coverage.json`),
  `tier1_field_coverage_pct` MUST be rounded to 4 decimal places using round-half-up semantics.

If `|E| == 0`, the metric is **indeterminate** and `tier1_field_coverage_pct` MUST be recorded as
`null` with a reason code (for example, `indeterminate_no_events`).

#### Gate threshold

The default Tier 1 coverage gate threshold is:

- `tier1_field_coverage_threshold_pct = 0.80` (unitless fraction), derived from
  `scoring.thresholds.min_tier1_field_coverage` (default `0.80`).

The pipeline MUST compute `tier1_field_coverage_state` in
`{ ok, below_threshold, indeterminate_no_events }`:

- If `|E| == 0`: `indeterminate_no_events`.
- Else if `tier1_field_coverage_pct < tier1_field_coverage_threshold_pct`: `below_threshold`.
- Else: `ok`.

The run health classification rules are defined in [Scoring metrics](070_scoring_metrics.md). In
summary:

- If `tier1_field_coverage_state = indeterminate_no_events`, the run MUST be marked `partial`.
- If `tier1_field_coverage_state = below_threshold`, the run MUST be marked `partial`.

Invariant:

- `tier1_field_coverage_pct` MUST be `null` if and only if
  `tier1_field_coverage_state = indeterminate_no_events`.

This gate is intentionally a run-level quality signal. It does not convert Tier 1 event-level SHOULD
into MUST.

### Classification and severity

| Field          | Recommendation | Notes                                                                    |
| -------------- | -------------: | ------------------------------------------------------------------------ |
| `category_uid` |         SHOULD | Useful for routing and high-level grouping.                              |
| `type_uid`     |         SHOULD | Useful for deterministic subtyping when available in your mapping model. |
| `severity_id`  |         SHOULD | Normalize severity consistently across sources.                          |

### Device and actor pivots

Purple Axiom treats a small set of pivots as core common because they unlock most triage workflows.

| Object or field      | Recommendation | Notes                                                                                                                 |
| -------------------- | -------------: | --------------------------------------------------------------------------------------------------------------------- |
| `device.hostname`    |         SHOULD | Stable host identifier when available.                                                                                |
| `device.uid`         |         SHOULD | Stable host ID when available.                                                                                        |
| `device.(ip\|ips[])` |         SHOULD | Device IP pivot. Present if either `device.ip` or `device.ips[]` is present (see Tier 1 field set).                   |
| `actor.user.name`    |         SHOULD | Principal name in the Tier 2 standard user shape (see Tier 2: Standard actor identity shapes).                        |
| `actor.user.uid`     |         SHOULD | Principal stable identifier (SID/UID) in the Tier 2 standard user shape (see Tier 2: Standard actor identity shapes). |
| `actor.process.name` |         SHOULD | Process name in the Tier 2 standard process shape (see Tier 2: Standard actor identity shapes).                       |
| `actor.process.pid`  |         SHOULD | Process ID in the Tier 2 standard process shape (see Tier 2: Standard actor identity shapes).                         |

### Message and observables

| Field           | Recommendation | Notes                                                                                                                 |
| --------------- | -------------: | --------------------------------------------------------------------------------------------------------------------- |
| `message`       |         SHOULD | Short, redaction-safe human summary.                                                                                  |
| `observables[]` |         SHOULD | Extract canonical pivots (IPs, domains, hashes, usernames, URLs). Use when available in your OCSF version or profile. |

### Field mapping completeness matrix

For v0.1, Purple Axiom defines a source-type-specific checklist for Tier 1 (core common) and the
Tier 2 families used by the v0.1 MVP normalizer. The authoritative checklist is defined in the
[Mapping coverage matrix](../mappings/coverage_matrix.md).

The matrix:

- Uses rows = `source_type` (for example, Windows Security, Sysmon, osquery, auditd).
- Uses columns = OCSF field paths (Tier 1 plus the v0.1 enabled event families defined in "Enabled
  event families (v0.1 baseline)").
- Uses cells = `R` / `O` / `N/A` with the following semantics:
  - `R` (required mapping target): the mapping MUST populate the field when an authoritative value
    is present in the raw input or when it is deterministically derived from run context (for
    example, `device.uid` from inventory). The mapping MUST NOT infer or fabricate semantic values
    that are not present.
  - `O` (optional mapping target): populate when present; absence does not fail mapping
    completeness.
  - `N/A`: the field is not applicable for that `source_type` (or defined sub-scope) and MUST remain
    absent.

The completeness matrix is a mapping-profile conformance tool. It is intentionally distinct from the
run-level Tier 1 coverage metric: a run may have low Tier 1 coverage due to collection gaps even
when the mapping profiles are complete.

## Tier 2 core class minimums

Tier 2 defines the minimum primary objects Purple Axiom expects for each supported event family.
These are not universal requirements. They apply when an event is mapped to the corresponding family
or class set.

This section is intentionally framed by **event families** rather than exact class lists, because
`class_uid` values and shapes vary by pinned OCSF version. The normalizer should implement these as
mapping profiles per `source_type`.

### Enabled event families (v0.1 baseline)

This section defines the minimal, representative set of **enabled event families** for Purple Axiom
v0.1. This baseline exists to prevent cross-lab incomparability by fixing the minimum scope for:

- mapping effort (which Tier 2 family minimums are expected),
- telemetry configuration (which families must be collectable in the lab), and
- what “coverage” means for scoring and detection evaluation.

#### Baseline set (normative)

For Purple Axiom **v0.1**, the following event families **MUST** be treated as enabled:

1. **Process execution**
1. **Network connections**
1. **DNS queries**
1. **Authentication/logon**
1. **File writes (selectively)**

Implementations **MAY** additionally enable other families (for example, registry, image/module
load, EDR “findings”), but those families are **out of scope** for v0.1 baseline comparability
unless:

1. this section is updated, and
1. the Mapping coverage matrix column set is updated accordingly, and
1. CI baselines / golden fixtures are refreshed to reflect the new scope.

#### Mapping and evaluation semantics (normative)

- When events in an enabled family are emitted, mapping profiles **MUST** attempt to populate the
  Tier 2 minimum objects/fields defined in the corresponding family subsections of this document,
  subject to authoritative availability in raw input.
- Mappings **MUST NOT** fabricate Tier 2 fields to satisfy this baseline. If authoritative values
  are absent, the field **MUST** be absent and the gap **MUST** remain observable via mapping
  coverage outputs (for example, coverage segmented by `source_type` and `class_uid`).
- v0.1 scoring and Sigma-based detection evaluation **SHOULD** treat these families as the minimum
  input surface for “meaningful” evaluation. Runs that do not collect/normalize one or more baseline
  families will be difficult to compare across labs and will commonly manifest as
  `missing_telemetry` / `normalization_gap`-shaped outcomes downstream.

#### Telemetry sources (planning guidance; non-normative)

The baseline families are intentionally achievable using common endpoint telemetry (no mandatory
network sensors).

| Enabled family (v0.1)     | Typical sources / `metadata.source_type`                    | Notes                                                                          |
| ------------------------- | ----------------------------------------------------------- | ------------------------------------------------------------------------------ |
| Process execution         | `windows-sysmon`, `osquery`, `linux-auditd`                 | Primary pivot for most endpoint detections and correlations.                   |
| Network connections       | `windows-sysmon`, host firewall logs, optional flow sensors | Prefer endpoint connection events in v0.1; pcap/NetFlow are optional/reserved. |
| DNS queries               | `dns` (DNS client logs / resolver logs), optional `zeek_*`  | Treated as its own family to support domain-based detections and correlation.  |
| Authentication/logon      | `windows-security`, POSIX auth logs, IdP audit logs         | Focus on success/failure + principal identity pivots.                          |
| File writes (selectively) | `windows-sysmon`, `linux-auditd`, `osquery`                 | High-volume and high-variance unless bounded (see selection policy below).     |

#### File write selection policy (recommended; v0.1)

“File writes (selectively)” is enabled because dropped payloads, staging, and persistence often
leave file-system evidence, but unconstrained file telemetry can dominate volume and cost.

To bound telemetry volume (and reduce privacy risk), file system collection **SHOULD** be limited
to:

- create/modify operations (not read),
- user-writable and common staging locations (for example: Downloads, Temp, Startup, ProgramData),
  and
- high-signal extensions (executables and scripts), for example:
  - `.exe`, `.dll`, `.ps1`, `.bat`, `.cmd`, `.js`, `.vbs`, `.hta`, `.msi`, `.lnk`
  - archives such as `.zip`, `.7z`, `.rar` when feasible

If a lab applies materially different selection criteria, it **SHOULD** be reflected in the lab’s
telemetry baseline profile and treated as a comparability-relevant configuration difference.

#### Rationale (coverage; non-normative)

This v0.1 baseline aligns with the Sigma-to-OCSF bridge MVP scope recommendation (process execution,
network connections, DNS queries, authentication/logon, selective file writes), chosen to cover a
significant fraction of high-value detection content without exploding scope.

Collectively, these families cover the most common “evidence surfaces” produced by safe technique
execution scenarios, including execution pivots, download / remote communications, and identity
pivots.

#### Cost estimates (planning; v0.1)

The table below is intended for planning and tradeoff discussions; actual costs MUST be validated
using run reporting volume metrics (events by `source_type` / `class_uid`, EPS, and byte rates).

| Family                    | Telemetry volume (relative) | Mapping complexity (relative) | Primary cost drivers / notes                                                                |
| ------------------------- | --------------------------- | ----------------------------- | ------------------------------------------------------------------------------------------- |
| Process execution         | Medium                      | Medium                        | Steady baseline volume; requires consistent actor + process pivots.                         |
| Network connections       | High                        | Medium                        | Can dominate EPS on active endpoints; consider excluding loopback/noise only if documented. |
| DNS queries               | Medium                      | Low                           | Generally structured; critical for domain-based detections.                                 |
| Authentication/logon      | Low–Medium                  | Medium                        | Volume spikes on shared systems; requires consistent outcome semantics.                     |
| File writes (selectively) | Medium–High                 | High                          | Highly sensitive to selection policy; hashing increases CPU/bytes.                          |

### Standard actor identity shapes

This section defines a **Tier 2 identity profile** for `actor.user` and `actor.process`. Its purpose
is to prevent cross-source drift (example: one source populates `actor.user.name` only while another
populates `actor.user.uid` only) by defining:

- the preferred stable identifiers,
- platform-specific semantics, and
- canonicalization rules that are deterministic across implementations.

Normative requirements:

- Mapping profiles MUST follow these shapes whenever they emit `actor.user` and/or `actor.process`.
- Mappings MUST NOT infer or fabricate semantic values that are not present in authoritative raw
  input (or deterministically derived from run context).
- Mappings MUST NOT perform environment-dependent lookups (example: resolving username from UID or
  SID) to populate these fields.
- Empty-string values (after trimming) MUST be treated as absent (field omitted).

#### `actor.user` (Tier 2 standard user shape)

| Field                     | Requirement | Canonicalization and semantics                                                                                                                                                                                                                                                                                                                               |
| ------------------------- | ----------: | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `actor.user.uid`          |      SHOULD | Stable principal identifier. MUST be a string across platforms to avoid type drift in long-term storage. Windows: MUST be the SID string in canonical `S-1-...` form (no surrounding whitespace). POSIX (Linux/macOS): MUST be the base-10 string representation of the numeric UID, with no leading zeros (except UID `0` represented as `"0"`).            |
| `actor.user.name`         |      SHOULD | Username (no domain prefix/suffix) when present in authoritative raw input. MUST NOT be rendered as `DOMAIN\user` or `user@domain`. Mappings MUST NOT synthesize usernames via directory services or local account lookup. If the authoritative raw input provides only a combined name string, mappings SHOULD apply the deterministic parsing rules below. |
| `actor.user.domain`       |      SHOULD | Domain / realm / scope when present as a separate authoritative field (preferred) or safely parsed from a combined name string. Windows: typically the `*DomainName` field. POSIX: rarely available; omit unless explicitly present (example: `user@realm`). MUST NOT be derived via environment-dependent lookups (LDAP, `/etc/passwd`, etc.).              |
| `actor.user.display_name` |         MAY | Presentation-only principal string when the authoritative raw input provides a combined form (example: `DOMAIN\user` or `user@domain`). SHOULD equal the exact raw combined string after trimming. When `actor.user.domain` is derived by parsing a combined name string, mappings SHOULD preserve the original combined form here.                          |

Deterministic parsing rules for combined principal strings (recommended):

- If authoritative raw input provides separate domain and username fields, mappings SHOULD:
  - set `actor.user.domain` and `actor.user.name` from those fields, and
  - MAY set `actor.user.display_name` to `DOMAIN\user` (Windows) or `user@domain` (UPN-style) as a
    presentation helper.
- If authoritative raw input provides a single combined string and no separate domain field,
  mappings SHOULD parse only when the format is unambiguous:
  - `DOMAIN\user` form: if the string matches `^[^\\]+\\[^\\]+$`, split on the first backslash.
  - `user@domain` form: if the string matches `^[^@\s]+@[^@\s]+$`, split on the first `@`.
  - Otherwise, set `actor.user.name` to the full trimmed string, omit `actor.user.domain`, and MAY
    set `actor.user.display_name` to the same string.

Canonical validity checks (recommended, deterministic):

- If `actor.user.uid` is populated on Windows, it SHOULD match `^S-1-\d+(-\d+)+$`. If it does not,
  the mapping SHOULD omit `actor.user.uid` and preserve the original value in an unmapped/raw area.
- If `actor.user.uid` is populated on POSIX, it SHOULD match `^(0|[1-9]\d*)$`. If it does not, the
  mapping SHOULD omit `actor.user.uid` and preserve the original value in an unmapped/raw area.

#### `actor.process` (Tier 2 standard process shape)

| Field                    | Requirement | Canonicalization and semantics                                                                                                                                                                                                                                                                                      |
| ------------------------ | ----------: | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `actor.process.pid`      |      SHOULD | Process identifier as an integer when present. If the authoritative raw input provides a base-10 numeric string, the mapping SHOULD parse it deterministically. Values MUST be non-negative. If parsing fails, the mapping SHOULD omit `actor.process.pid` and preserve the original value in an unmapped/raw area. |
| `actor.process.name`     |      SHOULD | Process image name (basename only). If the authoritative raw input provides a full path but no name field, the mapping SHOULD derive `actor.process.name` deterministically as the final path segment. The mapping MUST NOT perform filesystem lookups to resolve name from PID or path.                            |
| `actor.process.path`     |         MAY | Full executable path when present in authoritative raw input. The mapping MUST NOT expand environment variables, resolve symlinks, or otherwise perform filesystem-dependent normalization.                                                                                                                         |
| `actor.process.cmd_line` |         MAY | Command line when present in authoritative raw input. Redaction (if enabled) is governed elsewhere; this section only defines field intent and shape.                                                                                                                                                               |

Applicability and absence:

- When a source does not provide initiating process identifiers (example: osquery
  `ntfs_journal_events` on Windows), `actor.process` MUST be absent for those events and MUST NOT be
  backfilled from other telemetry sources.
- When a source does not provide user attribution for those events, `actor.user` MUST be absent and
  MUST NOT be backfilled from other telemetry sources.

#### Verification hooks (actor identity) (normative)

Implementations MUST maintain fixture-backed tests that validate Tier 2 actor identity extraction
and canonicalization across at least the following telemetry sources:

- Windows Event Log (`metadata.source_type` variants such as `windows-security` or `windows-sysmon`)
- osquery (`metadata.source_type = "osquery"`)
- Unix logs (`metadata.source_type = "linux-auditd"` and/or `linux-syslog`)

Each fixture MUST include (1) a representative raw source record (or minimally sufficient parsed
representation) and (2) the expected normalized OCSF event. The test suite MUST assert:

- `actor.user.name` is username-only; domain/realm is represented in `actor.user.domain` when
  available or safely parsed.
- `actor.user.uid` uses Windows SID (Windows) or base-10 UID string (POSIX) and is not populated via
  environment-dependent lookup.
- When a combined principal string is parsed, the original combined string is preserved in
  `actor.user.display_name`.

Suggested fixture location: `tests/fixtures/normalization/actor_identity/` (new).

### Process and execution activity

Example sources: Sysmon, auditd, osquery.

Minimum recommended fields:

- `actor.process`: process identity (name, pid, path if available)
- `actor.user`: user identity (uid or sid, name)
- `device`: host identity
- Optional but high value:
  - Parent process identity (if available)
  - Command line (subject to redaction-safe policy)

### Authentication and authorization

Example sources: Windows Security, auth logs.

Minimum recommended fields:

- `actor.user`: principal attempting auth
- `device`: host identity
- `status_id` or equivalent outcome representation (success or failure)
- Optional but high value:
  - Source network endpoint (IP, hostname)
  - Target account or resource identifiers

### Network and connection activity

Example sources: Zeek, Suricata, firewall logs.

Minimum recommended fields:

- `device`: sensor host or originating host identity (depending on source semantics)
- Source endpoint (IP, port) and destination endpoint (IP, port)
- Transport or protocol indicator
- Optional but high value:
  - Directionality (inbound, outbound)
  - Bytes or packets counters

### DNS activity

Example sources: Zeek DNS, resolver logs.

Minimum recommended fields:

- Query name
- Query type
- Response codes or outcome representation
- Source endpoint identity (client host or resolver identity, depending on source semantics)
- Optional but high value:
  - Resolved IPs
  - Upstream resolver identity

### File system activity

Example sources: Sysmon, auditd.

Minimum recommended fields:

- File identity (path, name)
- Actor identity (user, process)
- Device identity (host)
- Optional but high value:
  - Hashes (sha256 preferred)
  - Operation semantics (create, modify, delete)

### Findings and detections

Example sources: EDR alerts, SIEM notable events.

Minimum recommended fields:

- Finding identifier (rule name, signature ID, or vendor alert ID)
- Severity and status
- Primary affected entity pivots (host, user, process, file, network)
- Optional but high value:
  - Confidence or score
  - Evidence references (event IDs, observable list)

## Tier 3 extended fields

Extended fields are everything beyond Tier 2 that improves outcomes, but should not block shipping
the MVP.

Extended mapping commonly includes:

- Full actor attribution:
  - Session identity, MFA indicators, privilege context
- Asset and environment context:
  - Business unit tags, host role, environment (prod, dev)
- Process detail:
  - Full ancestry chain, integrity level, signer, module loads
- Network detail:
  - JA3 or JA4, SNI, HTTP method, URI, TLS version, cipher
- File detail:
  - Signed-by, entropy, file owner, creation and modify times
- Rich vendor finding detail:
  - Tactic or technique tags, kill chain stage, remediation state

### Rules for adding extended fields

1. Extended fields MUST NOT change the semantics of core fields.
1. Extended fields SHOULD be gated behind mapping profiles so you can test and measure them.
1. When extended fields require derived logic, the derivation MUST be deterministic and tested.

## Tier R raw retention

### Purpose

Raw retention ensures:

- No loss of forensic fidelity when mappings are incomplete.
- Faster iteration on mappings (you can backfill new fields from preserved raw).
- Debuggability for pipeline issues.

### Rules

- Use `raw` to retain source-specific or unmapped content.
- `raw` MUST be redaction-safe for long-term storage.
- `raw` SHOULD be structured where possible:
  - `raw.source` (source system identifiers)
  - `raw.event` (selected normalized-safe raw fields)
  - `raw.payload` (optional raw payload snapshot, redaction-safe)

### Guidance

- Prefer keeping raw values in their original types when safe.
- If a raw value is high risk (secrets, tokens, PII), it MUST be removed or transformed prior to
  writing long-term artifacts.

## Validation and coverage expectations

### Tiered validation gates

| Gate   |               Enforced in CI | Description                                                                               |
| ------ | ---------------------------: | ----------------------------------------------------------------------------------------- |
| Tier 0 |                          YES | Contract schema validation and invariants (run_id, scenario_id, event_id uniqueness).     |
| Tier 1 |            YES (recommended) | Presence checks for common pivots and classification completeness where applicable.       |
| Tier 2 | YES (as classes are enabled) | Class-family minimums for enabled mappings (profile-specific).                            |
| Tier 3 |                           NO | Extended fields validated opportunistically and via sampling.                             |
| Tier R |                          YES | Redaction policy checks; raw present when configured; raw never contains restricted data. |

### Coverage metrics

The normalizer SHOULD emit mapping coverage metrics that support incremental improvement:

- Percent of events meeting Tier 0, Tier 1, Tier 2 per `source_type` and `class_uid`
- Unknown or unclassified rate (events that cannot be assigned a `class_uid` deterministically)
- Top missing pivots (hostname, user, process, endpoints) by `source_type`
- Raw retention rate and top raw field keys (for mapping backlog triage)

## Implementation guidance

### Mapping order

1. Implement Tier 0 for every `source_type`.
1. Add Tier 1 pivots for the same sources.
1. Enable Tier 2 class minimums for the event families produced by your scenarios.
1. Expand Tier 3 continuously, driven by scoring gaps and analyst workflows.

### Null and unknown policy

- If a field is present but unknown, prefer explicit unknown conventions over omission when it
  materially improves downstream stability.
- Avoid inventing values. Derive only from trustworthy source evidence.

### Determinism

- Core and extended derivations MUST be deterministic given the same inputs and mapping profile.
- Output field ordering for JSONL SHOULD be deterministic for diffability (implementation detail,
  but treated as an invariant by CI).

## Examples

### Tier 0 only example

```json
{
  "time": 1736035200123,
  "class_uid": 1001,
  "metadata": {
    "uid": "pa:eid:v1:4b2d3f3f6b7b2a1c9a1d2c3b4a5f6e7d",
    "event_id": "pa:eid:v1:4b2d3f3f6b7b2a1c9a1d2c3b4a5f6e7d",
    "run_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "scenario_id": "atomic-t1059",
    "collector_version": "collector@0.1.0",
    "normalizer_version": "normalizer@0.1.0",
    "source_type": "sysmon",
    "source_event_id": "record:123456",
    "identity_tier": 1
  },
  "raw": {
    "provider": "Microsoft-Windows-Sysmon",
    "event_id": 1
  }
}
```

### Tier 0 and Tier 1 pivots example

```json
{
  "time": 1736035200123,
  "class_uid": 1001,
  "category_uid": 1,
  "severity_id": 2,
  "metadata": {
    "uid": "pa:eid:v1:4b2d3f3f6b7b2a1c9a1d2c3b4a5f6e7d",
    "event_id": "pa:eid:v1:4b2d3f3f6b7b2a1c9a1d2c3b4a5f6e7d",
    "run_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "scenario_id": "atomic-t1059",
    "collector_version": "collector@0.1.0",
    "normalizer_version": "normalizer@0.1.0",
    "source_type": "sysmon",
    "source_event_id": "record:123456",
    "identity_tier": 1,
    "ingest_time_utc": "2026-01-04T17:00:01Z",
    "pipeline": "profile.sysmon.v1"
  },
  "device": {
    "hostname": "host-01",
    "uid": "host-01-guid",
    "ips": ["10.0.0.10"]
  },
  "actor": {
    "user": { "name": "alice", "uid": "S-1-5-21-1111111111-2222222222-3333333333-1001" },
    "process": { "name": "powershell.exe", "pid": 4242 }
  },
  "raw": {
    "provider": "Microsoft-Windows-Sysmon",
    "event_id": 1,
    "image": "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe"
  }
}
```

## Open items

- Add fixture-backed actor identity vectors (Windows Event Log, osquery, Unix logs) that pin the
  parsing/canonicalization rules for `actor.user.{name,domain,uid,display_name}` and
  `actor.process.{pid,name,path,cmd_line}`.
- Define per-source redaction profiles and automated tests for raw retention.

## Key decisions

- Tier 0 is contract-required for every normalized event; Tier R requires redaction-safe raw
  retention.
- Tier 1 pivots remain event-level SHOULD, but MUST be measured with a run-level coverage metric and
  gate.
- Tier 1 gate default is `tier1_field_coverage_threshold_pct = 0.80` (derived from
  `scoring.thresholds.min_tier1_field_coverage`), with run health outcomes defined in
  [Scoring metrics](070_scoring_metrics.md).
- Tier 2 minimums are defined by event family and apply only when that family is enabled by mappings
  and scenarios.
- Tier 3 enrichment MUST remain deterministic and MUST NOT change core semantics.

## References

- [OCSF normalization specification](050_normalization_ocsf.md)
- [Scoring metrics](070_scoring_metrics.md)
- [Project naming and versioning ADR](../adr/ADR-0001-project-naming-and-versioning.md)
- [Event identity and provenance ADR](../adr/ADR-0002-event-identity-and-provenance.md)
- [Mapping coverage matrix](../mappings/coverage_matrix.md)

## Changelog

| Date       | Change                                                                  |
| ---------- | ----------------------------------------------------------------------- |
| 2026-01-24 | update                                                                  |
| 2026-01-12 | Migrated to repository Markdown style guide (structure and formatting). |
