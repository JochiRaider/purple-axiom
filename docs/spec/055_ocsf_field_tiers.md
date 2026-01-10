<!-- docs/spec/055_ocsf_field_tiers.md -->

# OCSF Field Tiers: Core vs Extended

This spec defines how Purple Axiom classifies OCSF fields into **Core** and **Extended** tiers, and
how unmapped or source-specific data is retained. The goal is to make the normalizer implementable
as an MVP, while ensuring outputs remain useful for detection scoring, investigation workflows, and
long-term storage.

This document is **normative** for Purple Axiom outputs. It does not attempt to restate the entire
OCSF specification.

______________________________________________________________________

## Goals

1. **Make MVP feasible:** define a small, stable Core set that every event should carry.
1. **Preserve fidelity:** never discard source information needed for future mapping or audits.
1. **Enable deterministic scoring:** ensure stable identity, provenance, and minimum pivot fields.
1. **Support incremental mapping:** allow Extended fields to grow without breaking historical runs.
1. **Make validation practical:** provide tiered validation expectations and coverage metrics.

## Non-goals

- Defining complete OCSF class schemas.
- Enforcing every OCSF-required field for every class in CI from day one.
- Mandating a specific storage layout (see storage spec), beyond field tier guidance.

______________________________________________________________________

## Definitions

### Core fields

Fields that Purple Axiom treats as the **minimum viable normalized event**. Core fields are split
into:

- **Core Envelope:** required on every event (contract enforced).
- **Core Common:** strongly recommended across all events when available.
- **Core Class Minimums:** recommended minimum objects/attributes for specific event families.

### Extended fields

Fields that materially improve analytics, correlation, triage, and reporting, but are not required
to produce a valid MVP. Extended mapping is expected to expand over time.

### Raw retention

Source-specific fields preserved to avoid data loss. These are retained under `raw` (and optionally
structured sub-objects), and are not required to be OCSF-conformant.

______________________________________________________________________

## Tier model

Purple Axiom uses the following tiers for implementation planning and validation gating.

| Tier | Name                | Description                                         | Expected timeline |
| ---: | ------------------- | --------------------------------------------------- | ----------------- |
|    0 | Core Envelope       | Minimal contract required fields and provenance     | Day 1             |
|    1 | Core Common         | Cross-cutting pivots and classification refinements | Early MVP         |
|    2 | Core Class Minimums | Minimum objects for each supported event family     | MVP to v1         |
|    3 | Extended            | Enrichment and completeness improvements            | Continuous        |
|    R | Raw retention       | Preserve unmapped source data safely                | Day 1             |

______________________________________________________________________

## Tier 0: Core Envelope (contract-required)

Every emitted normalized event MUST include the following fields.

### Required top-level fields

| Field       | Requirement | Notes                                                                        |
| ----------- | ----------: | ---------------------------------------------------------------------------- |
| `time`      |        MUST | Event time in ms since epoch, UTC.                                           |
| `class_uid` |        MUST | The event class identifier (drives downstream routing and mapping coverage). |
| `metadata`  |        MUST | Provenance and stable identity.                                              |

### Required `metadata` fields

| Field                         | Requirement | Notes                                                                                                             |
| ----------------------------- | ----------: | ----------------------------------------------------------------------------------------------------------------- |
| `metadata.uid`                |        MUST | OCSF unique event identifier. MUST equal `metadata.event_id` (ADR-0002).                                          |
| `metadata.event_id`           |        MUST | Purple Axiom deterministic event identifier (idempotency key). Mirrors `metadata.uid` in OCSF outputs (ADR-0002). |
| `metadata.run_id`             |        MUST | Run identifier (ties to manifest, ground truth, detections).                                                      |
| `metadata.scenario_id`        |        MUST | Scenario identifier (ties to ground truth).                                                                       |
| `metadata.collector_version`  |        MUST | Collector build/version.                                                                                          |
| `metadata.normalizer_version` |        MUST | Normalizer build/version.                                                                                         |
| `metadata.source_type`        |        MUST | Source discriminator (example: `wineventlog`, `sysmon`, `osquery`).                                               |

### Strong recommendations (Tier 0.5)

These SHOULD be included when available, but are not contract-required.

| Field                      | Recommendation | Notes                                                                  |
| -------------------------- | -------------: | ---------------------------------------------------------------------- |
| `metadata.source_event_id` |         SHOULD | Native upstream ID when meaningful (example: Windows `EventRecordID`). |
| `metadata.identity_tier`   |         SHOULD | Identity tier used to compute `metadata.event_id` (1                   |
| `metadata.ingest_time_utc` |         SHOULD | Ingest time as RFC3339 or ISO8601 UTC string, when available.          |
| `metadata.host`            |         SHOULD | Collector host identity if helpful for pipeline debugging.             |
| `metadata.pipeline`        |         SHOULD | Pipeline identifier (config profile, mapping version tag, etc.).       |

______________________________________________________________________

## Tier 1: Core Common (cross-cutting pivots)

These fields SHOULD be populated across most events when the source provides them or they can be
derived safely. They significantly improve correlation and detection evaluation.

### Tier 1 coverage metric and run health gate

Tier 1 fields remain **SHOULD** per event. However, the pipeline **MUST** compute a run-level Tier 1
coverage metric and apply a run health gate. This resolves the tension between "SHOULD" fields and
scoring/UX assumptions that rely on their availability for pivots.

#### Scope (what events are counted)

The Tier 1 coverage computation **MUST** operate over the set of **in-scope normalized OCSF
events**:

1. Start with normalized OCSF events emitted for the run (for example, the contents of
   `normalized/ocsf_events.*`).
1. Exclude events that fail OCSF schema validation (invalid events are not counted in the coverage
   denominator).
1. If an execution window can be derived from the executed actions (ground truth timeline), then the
   in-scope set **SHOULD** be restricted to events whose event timestamp falls within:
   - `[min(action.start_time) - padding, max(action.end_time) + padding]`
   - `padding` default: 30 seconds
1. If an execution window cannot be derived, all normalized OCSF events for the run are in-scope.

This scoping rule ensures the metric reflects executed techniques rather than ambient background
telemetry.

#### Presence semantics (what "present" means)

For each Tier 1 field path and each in-scope event:

- A field is **present** if the JSON key exists and its value is not `null`.
- For strings, the value **MUST** be non-empty after trimming whitespace.
- For arrays and objects, the value may be empty and still counts as present (existence is the pivot
  requirement).
- Numeric zero and boolean `false` count as present.

#### Coverage computation

Let:

- `E` be the set of in-scope normalized events
- `F` be the Tier 1 field set defined in this document
- `present(e, f)` be 1 if field `f` is present in event `e` by the rules above, else 0

Then:

`tier1_field_coverage_pct = ( Σ_{e in E} Σ_{f in F} present(e,f) ) / ( |E| * |F| )`

If `|E| == 0`, the metric is **indeterminate** and `tier1_field_coverage_pct` **MUST** be recorded
as `null` with a reason code (for example, `indeterminate_no_events`).

#### Gate threshold

The default Tier 1 coverage gate threshold is:

- `min_tier1_field_coverage_pct = 0.80`

The run health classification rules are defined in `070_scoring_metrics.md`. In summary:

- If `tier1_field_coverage_pct < 0.80`, the run **MUST** be marked `partial`.
- If indeterminate due to `|E| == 0`, the run **MUST** be marked `partial`.

This gate is intentionally a run-level quality signal. It does not convert Tier 1 event-level SHOULD
into MUST.

### Classification and severity

| Field          | Recommendation | Notes                                                                    |
| -------------- | -------------: | ------------------------------------------------------------------------ |
| `category_uid` |         SHOULD | Useful for routing and high-level grouping.                              |
| `type_uid`     |         SHOULD | Useful for deterministic subtyping when available in your mapping model. |
| `severity_id`  |         SHOULD | Normalize severity consistently across sources.                          |

### Device and actor pivots

Purple Axiom treats a small set of pivots as “core common” because they unlock most triage
workflows.

| Object / Field               | Recommendation | Notes                                                  |
| ---------------------------- | -------------: | ------------------------------------------------------ |
| `device.hostname`            |         SHOULD | Stable host identifier when available.                 |
| `device.uid`                 |         SHOULD | Stable host ID when available.                         |
| `device.ip` / `device.ips[]` |         SHOULD | Prefer `ips[]` when multiple.                          |
| `actor.user`                 |         SHOULD | Normalize principal identity into a stable user shape. |
| `actor.process`              |         SHOULD | Normalize process identity where applicable.           |

### Message and observables

| Field           | Recommendation | Notes                                                                                                              |
| --------------- | -------------: | ------------------------------------------------------------------------------------------------------------------ |
| `message`       |         SHOULD | Short, redaction-safe human summary.                                                                               |
| `observables[]` |         SHOULD | Extract canonical pivots (IPs, domains, hashes, usernames, URLs). Use when available in your OCSF version/profile. |

### Field mapping completeness matrix (v0.1 MVP)

For v0.1, Purple Axiom defines a source-type-specific checklist for Tier 1 (Core Common) and the
Tier 2 families used by the v0.1 MVP normalizer. The authoritative checklist is defined in
`docs/mappings/coverage_matrix.md`.

The matrix:

- Uses rows = `source_type` (for example, Windows Security, Sysmon, osquery, auditd).
- Uses columns = OCSF field paths (Tier 1 plus selected Tier 2 families: process, network, file,
  user).
- Uses cells = `R` / `O` / `N/A` with the following semantics:
  - `R` (required mapping target): the mapping **MUST** populate the field when an authoritative
    value is present in the raw input or when it is deterministically derived from run context (for
    example, `device.uid` from inventory). The mapping **MUST NOT** infer or fabricate semantic
    values that are not present.
  - `O` (optional mapping target): populate when present; absence does not fail mapping
    completeness.
  - `N/A`: the field is not applicable for that `source_type` (or defined sub-scope) and **MUST**
    remain absent.

The completeness matrix is a mapping-profile conformance tool. It is intentionally distinct from the
run-level Tier 1 coverage metric: a run may have low Tier 1 coverage due to collection gaps even
when the mapping profiles are complete.

______________________________________________________________________

## Tier 2: Core Class Minimums (per event family)

Tier 2 defines the minimum “primary objects” Purple Axiom expects for each supported event family.
These are not universal requirements. They apply when an event is mapped to the corresponding
family/class set.

This section is intentionally framed by **event families** rather than exact class lists, because
class_uids and shapes vary by pinned OCSF version. The normalizer should implement these as mapping
profiles per source_type.

### A) Process and execution activity (example sources: Sysmon, auditd, osquery)

Minimum recommended fields:

- `actor.process`: process identity (name, pid, path if available)
- `actor.user`: user identity (uid/sid, name)
- `device`: host identity
- Optional but high value:
  - parent process identity (if available)
  - command line (redacted-safe policy)

### B) Authentication and authorization (example sources: Windows Security, auth logs)

Minimum recommended fields:

- `actor.user`: principal attempting auth
- `device`: host identity
- `status_id` or equivalent outcome representation (success/failure)
- Optional but high value:
  - source network endpoint (IP, hostname)
  - target account/resource identifiers

### C) Network and connection activity (example sources: Zeek, Suricata, firewall logs)

Minimum recommended fields:

- `device`: sensor host or originating host identity (depending on source semantics)
- Source endpoint (IP, port) and destination endpoint (IP, port)
- Transport/protocol indicator
- Optional but high value:
  - directionality (inbound/outbound)
  - bytes/packets counters

### D) DNS activity (example sources: Zeek DNS, resolver logs)

Minimum recommended fields:

- Query name
- Query type
- Response codes or outcome representation
- Source endpoint identity (client host or resolver identity, depending on source semantics)
- Optional but high value:
  - resolved IPs
  - upstream resolver identity

### E) File system activity (example sources: Sysmon, auditd)

Minimum recommended fields:

- File identity (path, name)
- Actor identity (user, process)
- Device identity (host)
- Optional but high value:
  - hashes (sha256 preferred)
  - operation semantics (create, modify, delete)

### F) Findings and detections (example sources: EDR alerts, SIEM notable events)

Minimum recommended fields:

- Finding identifier (rule name, signature ID, or vendor alert ID)
- Severity and status
- Primary affected entity pivots (host, user, process, file, network)
- Optional but high value:
  - confidence/score
  - evidence references (event IDs, observable list)

______________________________________________________________________

## Tier 3: Extended fields (enrichment and completeness)

Extended fields are “everything beyond Tier 2” that improves outcomes, but should not block shipping
the MVP.

Extended mapping commonly includes:

- Full actor attribution:
  - session identity, MFA indicators, privilege context
- Asset and environment context:
  - business unit tags, host role, environment (prod/dev)
- Process detail:
  - full ancestry chain, integrity level, signer, module loads
- Network detail:
  - JA3/JA4, SNI, HTTP method/uri, TLS version/cipher
- File detail:
  - signed-by, entropy, file owner, creation/modify times
- Rich vendor finding detail:
  - tactic/technique tags, kill chain stage, remediation state

### Rules for adding Extended fields

1. Extended fields MUST NOT change the semantics of Core fields.
1. Extended fields SHOULD be gated behind mapping profiles so you can test and measure them.
1. When Extended fields require derived logic, the derivation MUST be deterministic and tested.

______________________________________________________________________

## Tier R: Raw retention and unmapped data

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
  - `raw.payload` (optional raw payload snapshot, redacted-safe)

### Guidance

- Prefer keeping raw values in their original types when safe.
- If a raw value is high risk (secrets, tokens, PII), it MUST be removed or transformed prior to
  writing long-term artifacts.

______________________________________________________________________

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

- % events meeting Tier 0, Tier 1, Tier 2 per source_type and class_uid
- Unknown/unclassified rate (events that cannot be assigned a class_uid deterministically)
- Top missing pivots (hostname, user, process, endpoints) by source_type
- Raw retention rate and top raw field keys (for mapping backlog triage)

______________________________________________________________________

## Implementation guidance

### Mapping order

1. Implement Tier 0 for every source_type.
1. Add Tier 1 pivots for the same sources.
1. Enable Tier 2 class minimums for the event families produced by your scenarios.
1. Expand Tier 3 continuously, driven by scoring gaps and analyst workflows.

### Null and unknown policy

- If a field is present but unknown, prefer explicit unknown conventions over omission when it
  materially improves downstream stability.
- Avoid inventing values. Derive only from trustworthy source evidence.

### Determinism

- Core and Extended derivations MUST be deterministic given the same inputs and mapping profile.
- Output field ordering for JSONL SHOULD be deterministic for diffability (implementation detail,
  but treated as an invariant by CI).

______________________________________________________________________

## Examples

### Example: Tier 0 only (envelope)

```json
{
  "time": 1736035200123,
  "class_uid": 1001,
  "metadata": {
    "event_id": "4b2d3f3f6b7b2a1c",
    "run_id": "run_2026-01-04T17-00-00Z",
    "scenario_id": "scenario.atomic.t1059",
    "collector_version": "collector@0.1.0",
    "normalizer_version": "normalizer@0.1.0",
    "source_type": "sysmon",
    "source_event_id": "record:123456"
  },
  "raw": {
    "provider": "Microsoft-Windows-Sysmon",
    "event_id": 1
  }
}
```

### Example: Tier 0 + Tier 1 pivots

```json
{
  "time": 1736035200123,
  "class_uid": 1001,
  "category_uid": 1,
  "severity_id": 2,
  "metadata": {
    "event_id": "4b2d3f3f6b7b2a1c",
    "run_id": "run_2026-01-04T17-00-00Z",
    "scenario_id": "scenario.atomic.t1059",
    "collector_version": "collector@0.1.0",
    "normalizer_version": "normalizer@0.1.0",
    "source_type": "sysmon",
    "source_event_id": "record:123456",
    "ingest_time_utc": "2026-01-04T17:00:01Z",
    "pipeline": "profile.sysmon.v1"
  },
  "device": {
    "hostname": "host-01",
    "uid": "host-01-guid",
    "ips": ["10.0.0.10"]
  },
  "actor": {
    "user": { "name": "alice", "uid": "S-1-5-21-..." },
    "process": { "name": "powershell.exe", "pid": 4242 }
  },
  "raw": {
    "provider": "Microsoft-Windows-Sysmon",
    "event_id": 1,
    "image": "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe"
  }
}
```

______________________________________________________________________

## Open items

- Define a standard shape for `actor.user` and `actor.process` for the pinned OCSF version/profile.
- Define per-source redaction profiles and automated tests for raw retention.
- Enumerate the initial enabled event families for v0.1 (driven by scenario set).
