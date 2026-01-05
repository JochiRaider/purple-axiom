# OCSF Field Tiers: Core vs Extended

This spec defines how Purple Axiom classifies OCSF fields into **Core** and **Extended** tiers, and how unmapped or source-specific data is retained. The goal is to make the normalizer implementable as an MVP, while ensuring outputs remain useful for detection scoring, investigation workflows, and long-term storage.

This document is **normative** for Purple Axiom outputs. It does not attempt to restate the entire OCSF specification.

---

## Goals

1. **Make MVP feasible:** define a small, stable Core set that every event should carry.
2. **Preserve fidelity:** never discard source information needed for future mapping or audits.
3. **Enable deterministic scoring:** ensure stable identity, provenance, and minimum pivot fields.
4. **Support incremental mapping:** allow Extended fields to grow without breaking historical runs.
5. **Make validation practical:** provide tiered validation expectations and coverage metrics.

## Non-goals

- Defining complete OCSF class schemas.
- Enforcing every OCSF-required field for every class in CI from day one.
- Mandating a specific storage layout (see storage spec), beyond field tier guidance.

---

## Definitions

### Core fields
Fields that Purple Axiom treats as the **minimum viable normalized event**. Core fields are split into:

- **Core Envelope:** required on every event (contract enforced).
- **Core Common:** strongly recommended across all events when available.
- **Core Class Minimums:** recommended minimum objects/attributes for specific event families.

### Extended fields
Fields that materially improve analytics, correlation, triage, and reporting, but are not required to produce a valid MVP. Extended mapping is expected to expand over time.

### Raw retention
Source-specific fields preserved to avoid data loss. These are retained under `raw` (and optionally structured sub-objects), and are not required to be OCSF-conformant.

---

## Tier model

Purple Axiom uses the following tiers for implementation planning and validation gating.

| Tier | Name | Description | Expected timeline |
|---:|---|---|---|
| 0 | Core Envelope | Minimal contract required fields and provenance | Day 1 |
| 1 | Core Common | Cross-cutting pivots and classification refinements | Early MVP |
| 2 | Core Class Minimums | Minimum objects for each supported event family | MVP to v1 |
| 3 | Extended | Enrichment and completeness improvements | Continuous |
| R | Raw retention | Preserve unmapped source data safely | Day 1 |

---

## Tier 0: Core Envelope (contract-required)

Every emitted normalized event MUST include the following fields.

### Required top-level fields

| Field | Requirement | Notes |
|---|---:|---|
| `time` | MUST | Event time in ms since epoch, UTC. |
| `class_uid` | MUST | The event class identifier (drives downstream routing and mapping coverage). |
| `metadata` | MUST | Provenance and stable identity. |

### Required `metadata` fields

| Field | Requirement | Notes |
|---|---:|---|
| `metadata.uid` | MUST | OCSF unique event identifier. MUST equal `metadata.event_id` (ADR-0002). |
| `metadata.event_id` | MUST | Purple Axiom deterministic event identifier (idempotency key). Mirrors `metadata.uid` in OCSF outputs (ADR-0002). |
| `metadata.run_id` | MUST | Run identifier (ties to manifest, ground truth, detections). |
| `metadata.scenario_id` | MUST | Scenario identifier (ties to ground truth). |
| `metadata.collector_version` | MUST | Collector build/version. |
| `metadata.normalizer_version` | MUST | Normalizer build/version. |
| `metadata.source_type` | MUST | Source discriminator (example: `wineventlog`, `sysmon`, `osquery`). |

### Strong recommendations (Tier 0.5)

These SHOULD be included when available, but are not contract-required.

| Field | Recommendation | Notes |
|---|---:|---|
| `metadata.source_event_id` | SHOULD | Native upstream ID when meaningful (example: Windows `EventRecordID`). |
| `metadata.identity_tier` | SHOULD | Identity tier used to compute `metadata.event_id` (1|2|3). |
| `metadata.ingest_time_utc` | SHOULD | Ingest time as RFC3339 or ISO8601 UTC string, when available. |
| `metadata.host` | SHOULD | Collector host identity if helpful for pipeline debugging. |
| `metadata.pipeline` | SHOULD | Pipeline identifier (config profile, mapping version tag, etc.). |

---

## Tier 1: Core Common (cross-cutting pivots)

These fields SHOULD be populated across most events when the source provides them or they can be derived safely. They significantly improve correlation and detection evaluation.

### Classification and severity

| Field | Recommendation | Notes |
|---|---:|---|
| `category_uid` | SHOULD | Useful for routing and high-level grouping. |
| `type_uid` | SHOULD | Useful for deterministic subtyping when available in your mapping model. |
| `severity_id` | SHOULD | Normalize severity consistently across sources. |

### Device and actor pivots

Purple Axiom treats a small set of pivots as “core common” because they unlock most triage workflows.

| Object / Field | Recommendation | Notes |
|---|---:|---|
| `device.hostname` | SHOULD | Stable host identifier when available. |
| `device.uid` | SHOULD | Stable host ID when available. |
| `device.ip` / `device.ips[]` | SHOULD | Prefer `ips[]` when multiple. |
| `actor.user` | SHOULD | Normalize principal identity into a stable user shape. |
| `actor.process` | SHOULD | Normalize process identity where applicable. |

### Message and observables

| Field | Recommendation | Notes |
|---|---:|---|
| `message` | SHOULD | Short, redaction-safe human summary. |
| `observables[]` | SHOULD | Extract canonical pivots (IPs, domains, hashes, usernames, URLs). Use when available in your OCSF version/profile. |

---

## Tier 2: Core Class Minimums (per event family)

Tier 2 defines the minimum “primary objects” Purple Axiom expects for each supported event family. These are not universal requirements. They apply when an event is mapped to the corresponding family/class set.

This section is intentionally framed by **event families** rather than exact class lists, because class_uids and shapes vary by pinned OCSF version. The normalizer should implement these as mapping profiles per source_type.

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

---

## Tier 3: Extended fields (enrichment and completeness)

Extended fields are “everything beyond Tier 2” that improves outcomes, but should not block shipping the MVP.

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
2. Extended fields SHOULD be gated behind mapping profiles so you can test and measure them.
3. When Extended fields require derived logic, the derivation MUST be deterministic and tested.

---

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
- If a raw value is high risk (secrets, tokens, PII), it MUST be removed or transformed prior to writing long-term artifacts.

---

## Validation and coverage expectations

### Tiered validation gates

| Gate | Enforced in CI | Description |
|---|---:|---|
| Tier 0 | YES | Contract schema validation and invariants (run_id, scenario_id, event_id uniqueness). |
| Tier 1 | YES (recommended) | Presence checks for common pivots and classification completeness where applicable. |
| Tier 2 | YES (as classes are enabled) | Class-family minimums for enabled mappings (profile-specific). |
| Tier 3 | NO | Extended fields validated opportunistically and via sampling. |
| Tier R | YES | Redaction policy checks; raw present when configured; raw never contains restricted data. |

### Coverage metrics

The normalizer SHOULD emit mapping coverage metrics that support incremental improvement:

- % events meeting Tier 0, Tier 1, Tier 2 per source_type and class_uid
- Unknown/unclassified rate (events that cannot be assigned a class_uid deterministically)
- Top missing pivots (hostname, user, process, endpoints) by source_type
- Raw retention rate and top raw field keys (for mapping backlog triage)

---

## Implementation guidance

### Mapping order

1. Implement Tier 0 for every source_type.
2. Add Tier 1 pivots for the same sources.
3. Enable Tier 2 class minimums for the event families produced by your scenarios.
4. Expand Tier 3 continuously, driven by scoring gaps and analyst workflows.

### Null and unknown policy

- If a field is present but unknown, prefer explicit unknown conventions over omission when it materially improves downstream stability.
- Avoid inventing values. Derive only from trustworthy source evidence.

### Determinism

- Core and Extended derivations MUST be deterministic given the same inputs and mapping profile.
- Output field ordering for JSONL SHOULD be deterministic for diffability (implementation detail, but treated as an invariant by CI).

---

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

---

## Open items

* Define a standard shape for `actor.user` and `actor.process` for the pinned OCSF version/profile.
* Define per-source redaction profiles and automated tests for raw retention.
* Enumerate the initial enabled event families for v0.1 (driven by scenario set).

