---
title: ADR-0008 Threat intelligence integration model
description: Defines a v0.2+ model for integrating external threat intelligence (including MISP) without bundling a full TI platform, preserving local-first determinism via versioned intel packs and run-bundle snapshots.
status: draft
category: adr
tags: [threat-intel, misp, integration, determinism, provenance, observability, conformance]
related:
  - ADR-0001-project-naming-and-versioning.md
  - ADR-0004-deployment-architecture-and-inter-component-communication.md
  - ADR-0003-redaction-policy.md
  - ADR-0005-stage-outcomes-and-failure-classification.md
  - ADR-0007-state-machines.md
  - ../spec/010_scope.md
  - ../spec/020_architecture.md
  - ../spec/025_data_contracts.md
  - ../spec/035_validation_criteria.md
  - ../spec/070_scoring_metrics.md
  - ../spec/080_reporting.md
  - ../spec/090_security_safety.md
  - ../spec/115_operator_interface.md
  - ../spec/120_config_reference.md
---

# ADR-0008: Threat intelligence integration model

This ADR defines how Purple Axiom integrates threat intelligence in a way that is compatible with
the project’s local-first, deterministic, run-bundle-centric architecture.

In particular, it makes an explicit v0.2+ decision to **not** bundle a full threat intelligence
platform (such as a complete MISP server stack) into the orchestrator/appliance, and instead defines
a pack-and-snapshot model that allows threat intel to be consumed reproducibly.

## Context

Operators often want to incorporate threat intelligence (TI) into evaluation and reporting
workflows:

- indicator of compromise (IoC) lists for enrichment and correlation
- tags/attribution metadata associated with known threats
- external context attached to detections (for example, “this domain is tagged with X”)

However, Purple Axiom’s architecture and safety posture emphasize:

- reproducibility and deterministic run results derived from pinned inputs and contracted artifacts
- a one-shot orchestrator model driven by filesystem publish-gates and stage outcomes (not daemon
  databases)
- default-off network side effects and explicit, observable configuration for any egress

Bundling a full TI platform server (web app, database, workers, background jobs) inside the
orchestrator Docker bundle would:

- introduce persistent state and long-running lifecycle concerns that do not match the one-shot run
  model
- expand the attack surface and operational complexity of the “single container” appliance approach
  planned for v0.2+
- create drift risk (mutable TI state) that undermines deterministic comparability unless
  snapshotted

Accordingly, TI integration should be modeled as a **pinned input** that is snapshotted into the run
bundle in the same spirit as other pack-like artifacts.

## Decision

### Version scope

- This ADR is **normative starting in v0.2**.
- v0.1 implementations MUST NOT be required to implement the artifacts or configuration described in
  this ADR.

### Deployment and packaging decision (no bundled MISP server)

1. The orchestrator Docker bundle / v0.2+ “single container” appliance MUST NOT include a full MISP
   server stack as a required component.
1. Threat intelligence platforms (including MISP) are treated as **external operator-managed
   dependencies** (if used at all) and are integrated via export/sync into versioned inputs.
1. Any optional “installation convenience” packaging (for example, a sample Docker Compose file)
   MUST NOT change conformance semantics: the authoritative TI inputs for a run MUST still be the
   run-bundle snapshots defined below.

### Threat intel as a pack-like artifact (Threat Intel Packs)

This ADR introduces a new pack-like artifact type:

- **Threat Intel Pack (TIP)**: a versioned, immutable bundle of indicators plus minimal provenance
  metadata, designed for deterministic consumption by pipeline stages.

This ADR extends ADR-0001 by defining the following version pins:

- `threat_intel_pack_id` (MUST conform to `id_slug_v1`)
- `threat_intel_pack_version` (MUST be SemVer)

Pinning rules (normative):

1. If TI is enabled for a run, the implementation MUST record the resolved `threat_intel_pack_id`
   and `threat_intel_pack_version` in `manifest.versions`.
1. A TI pack version MUST be treated as immutable. If duplicate `(id, version)` candidates exist,
   selection MUST follow ADR-0001 ambiguity rules (prefer fail-closed unless hashes match).

#### Pack resolution and validation (normative)

This section defines how an implementation resolves and validates the effective Threat Intel Pack
directory prior to snapshotting it into the run bundle.

Resolution inputs (reserved config keys; see Follow-ups):

- `threat_intel.enabled` (boolean)
- `threat_intel.pack.pack_id` (string; required when enabled)
- `threat_intel.pack.pack_version` (string; optional but RECOMMENDED for diffable/regression runs)
- `threat_intel.pack.paths` (array[string]; optional)

Search path semantics (normative):

1. Each entry in `threat_intel.pack.paths[]` MUST be a directory that contains TI packs under:
   - `<path>/<threat_intel_pack_id>/<threat_intel_pack_version>/`
1. If `threat_intel.pack.paths[]` is omitted, the implementation MUST use the single default search
   path:
   - `threat_intel/packs/`

Resolution algorithm (normative):

1. Let `requested_pack_id = threat_intel.pack.pack_id`.
1. Let `requested_pack_version = threat_intel.pack.pack_version` (may be absent).
1. Enumerate candidate pack directories across search paths:
   - For each search path `P`, candidates live under:
     - `P/<requested_pack_id>/<candidate_pack_version>/`
1. If `requested_pack_version` is provided:
   1. Candidates MUST be restricted to directories whose name equals `requested_pack_version`.
   1. If no such directory exists in any search path, resolution MUST fail closed.
1. If `requested_pack_version` is absent (non-recommended):
   1. Enumerate all candidate version directory names across all search paths.
   1. Parse candidate directory names as SemVer (using SemVer precedence rules).
   1. Select the highest SemVer version.
   1. If no candidates parse as SemVer, resolution MUST fail closed (do not guess
      lexicographically).
   1. The resolved `threat_intel_pack_version` MUST be recorded in run provenance (manifest +
      report), consistent with version pinning rules.
1. Duplicate `(threat_intel_pack_id, threat_intel_pack_version)` candidates across multiple search
   paths:
   1. If the selected `(id, version)` appears in multiple search paths, resolution MUST fail closed
      unless the packs are identical as proven by matching, in each candidate manifest:
      - `threat_intel.pack_sha256`, and
      - `manifest_sha256` and `indicators_sha256`.
   1. If the candidates are identical by the above definition, the implementation MUST select the
      candidate from the earliest search path in `threat_intel.pack.paths[]` order.

Validation requirements (normative; performed after selecting a candidate directory and before
snapshotting):

1. The pack `manifest.json` MUST include the required identity and hash fields:
   - `threat_intel_pack_id`
   - `threat_intel_pack_version`
   - `manifest_sha256`
   - `indicators_sha256`
   - `threat_intel.pack_sha256`
1. `threat_intel_pack_id` and `threat_intel_pack_version` MUST match the resolved
   `(pack_id, pack_version)` directory selection.
1. `manifest_sha256` MUST match a recomputation over `manifest.json` using the canonicalization
   rules in [Hash calculation rules](#hash-calculation-rules-normative).
1. `indicators_sha256` MUST match a recomputation over the canonical indicators JSONL bytes.
1. `threat_intel.pack_sha256` MUST match a recomputation using
   [Hash calculation rules](#hash-calculation-rules-normative).
1. `inputs/threat_intel/manifest.json` MUST validate against
   `threat_intel_pack_manifest.schema.json`.
1. Each line of `inputs/threat_intel/indicators.jsonl` MUST validate against
   `threat_intel_indicator.schema.json`.
1. The implementation MUST recompute and verify these hash fields per "Canonicalization and hashing
   (normative)".
1. When the contract schemas exist (see Follow-ups), the implementation MUST validate:
   - `manifest.json` against `threat_intel_pack_manifest.schema.json`, and
   - each `indicators.jsonl` line against `threat_intel_indicator.schema.json`.
1. If TI is enabled and resolution or validation fails:
   - the owning stage MUST fail closed by default, and
   - the failure MUST be recorded in stage outcomes per ADR-0005.

Interaction with run-bundle snapshots (normative):

1. If `inputs/threat_intel/manifest.json` and `inputs/threat_intel/indicators.jsonl` already exist
   at the time the owning stage begins:
   - the implementation MUST treat them as read-only snapshots,
   - MUST validate them using the same rules above, and
   - MUST NOT overwrite them in place.
1. If the snapshots do not exist, the owning stage MUST materialize them under
   `inputs/threat_intel/` using an atomic publish pattern (write to a temporary path, then rename),
   consistent with publish-gate intent.
1. If both a resolved pack directory and a pre-existing `inputs/threat_intel/` snapshot are present,
   they MUST be consistent (fail closed otherwise):
   - pinned `(id, version)` MUST match, and
   - hash fields MUST match.

### Threat Intel Pack layout (normative)

Threat Intel Packs MUST use a deterministic directory layout analogous to other pack-like artifacts.

Repository layout (normative):

- `threat_intel/packs/<threat_intel_pack_id>/<threat_intel_pack_version>/`

Within that directory, the following artifacts MUST exist:

| Path               | Required | Description                                              |
| ------------------ | -------- | -------------------------------------------------------- |
| `manifest.json`    | yes      | Pack manifest and provenance summary                     |
| `indicators.jsonl` | yes      | Normalized indicator set (one indicator record per line) |
| `upstream/`        | no       | Optional upstream exports (for example MISP JSON export) |
| `README.md`        | no       | Human notes (non-normative; MUST NOT affect hashing)     |

#### `indicators.jsonl` format invariants (normative)

`indicators.jsonl` is a JSON Lines (JSONL) artifact with deterministic parsing and hashing
semantics.

Physical format invariants (normative):

1. Encoding: MUST be UTF-8. A UTF-8 BOM MUST NOT be present.
1. Line delimiter: MUST use LF (`\n`) as the line separator.
   - CRLF (`\r\n`) and CR (`\r`) MUST NOT appear in the file.
1. Blank lines: MUST NOT contain blank/empty lines.
   - Each non-empty line MUST be exactly one JSON object.
1. End-of-file newline:
   - If the indicator set is non-empty, the file MUST end with a trailing LF (`\n`).
   - If the indicator set is empty, the file MUST be zero bytes (no trailing newline).
1. Deterministic ordering:
   - The file MUST be ordered canonically as defined in "Duplicate indicators and canonical ordering
     (normative)".

Parsing invariant (normative):

- Consumers MUST parse `indicators.jsonl` as JSON Lines with no blank lines (each line is one JSON
  object), and MUST treat any parse failure as pack validation failure when TI is enabled.

### Run-bundle snapshot model (normative)

When a run uses TI (enabled + resolved pack selection), the implementation MUST snapshot the TI pack
into the run bundle under `runs/<run_id>/inputs/threat_intel/`.

Run-bundle layout (normative):

| Path                                   | Required when TI enabled | Description                                              |
| -------------------------------------- | ------------------------ | -------------------------------------------------------- |
| `inputs/threat_intel/manifest.json`    | yes                      | Copy of selected pack `manifest.json`                    |
| `inputs/threat_intel/indicators.jsonl` | yes                      | Copy of selected pack `indicators.jsonl`                 |
| `inputs/threat_intel/upstream/`        | no                       | Optional copies of upstream exports (if present in pack) |

Snapshot rules (normative):

1. Snapshotting MUST be byte-for-byte reproducible for a given selected pack version.
1. The run MUST contain enough material to reproduce the selection (at minimum: the snapshotted
   manifest and indicator list), consistent with ADR-0001 snapshot reproducibility rules.
1. The stage that first consumes TI (for example detection or reporting) MUST be responsible for
   materializing these snapshots, and MUST treat the snapshot as read-only thereafter.

Note: Placing TI snapshots under `inputs/` ensures the Operator Interface artifact-serving model can
expose the files without adding new allowlisted top-level directories.

### Canonicalization and hashing (normative)

Threat Intel Packs MUST be deterministically hashable so “same pack version implies same content” is
testable.

This ADR reserves the following hash fields for the TI pack manifest and run snapshot:

- `manifest_sha256`
- `indicators_sha256`
- `threat_intel.pack_sha256`

Hash calculation rules (normative):

1. `indicators_sha256`

   - Let `L[]` be the sequence of JSON objects parsed from `indicators.jsonl` (one per line).
   - For each object `L[i]`, compute canonical JSON bytes `canonical_json_bytes(L[i])`.
   - Join these with `\n` (LF) and append a trailing `\n` (LF) at end of file.
   - `indicators_sha256 = sha256_hex(joined_bytes)`.
   - Empty indicator sets MUST be represented as a zero-line file with length 0 bytes (no trailing
     newline). The hash MUST be the SHA-256 of the empty byte string.

1. `manifest_sha256`

   - Compute canonical JSON bytes for `manifest.json` with these fields removed before hashing:
     - `manifest_sha256`
     - `indicators_sha256`
     - `threat_intel.pack_sha256`
   - `manifest_sha256 = sha256_hex(canonical_json_bytes(manifest_without_hash_fields))`.

1. `threat_intel.pack_sha256`

   - Compute canonical JSON bytes of:
     ```json
     {
       "threat_intel_pack_id": "...",
       "threat_intel_pack_version": "...",
       "manifest_sha256": "...",
       "indicators_sha256": "..."
     }
     ```
   - `threat_intel.pack_sha256 = sha256_hex(canonical_json_bytes(pack_basis_v1))`, where:
     - `pack_basis_v1.v = 1`
     - `pack_basis_v1.threat_intel_pack_id = <threat_intel_pack_id>`
     - `pack_basis_v1.threat_intel_pack_version = <threat_intel_pack_version>`
     - `pack_basis_v1.manifest_sha256 = <manifest_sha256>`
     - `pack_basis_v1.indicators_sha256 = <indicators_sha256>`

Hashing notes (normative):

- Hashes MUST NOT substitute for `(id, version)` pins. Hashes are evidence and validation aids; pins
  are the semantic identity, consistent with ADR-0001.
- If a TI pack includes `upstream/` exports, those artifacts MAY be hashed and recorded under a
  manifest `upstreams[]` section, but they MUST NOT change the normative meaning of
  `threat_intel.pack_sha256` unless explicitly specified in a future revision.

### Indicator record model (normative minimum)

Each line in `indicators.jsonl` MUST be a single JSON object conforming to a contract to be added
under `docs/contracts/` (see Follow-ups).

This ADR defines a minimal required field set for v0.2+:

| Field              | Type                | Required | Notes                                                 |
| ------------------ | ------------------- | -------- | ----------------------------------------------------- |
| `indicator_id`     | string              | yes      | Stable, deterministic ID (see below)                  |
| `type`             | string (enum)       | yes      | Indicator type vocabulary (see below)                 |
| `value`            | string              | yes      | Original value (trimmed)                              |
| `value_normalized` | string              | yes      | Deterministic normalized value used for matching      |
| `confidence`       | number or null      | no       | 0.0–1.0 recommended; null if unknown                  |
| `tags`             | array[string]       | no       | MUST be sorted by UTF-8 byte order when present       |
| `valid_from_utc`   | RFC3339 string/null | no       | Optional validity window                              |
| `valid_until_utc`  | RFC3339 string/null | no       | Optional validity window                              |
| `sources`          | array[object]       | no       | Provenance pointers; MUST be sorted deterministically |
| `extensions`       | object              | no       | Non-normative extensibility bucket                    |

Indicator type vocabulary (v0.2+ baseline):

- `ipv4`
- `ipv6`
- `domain`
- `url`
- `md5`
- `sha1`
- `sha256`
- `sha512`

Additional types MAY be added later, but MUST be added in a backward-compatible way (new enum
values) and MUST have deterministic normalization rules.

Normalization rules (normative baseline):

1. `value` MUST be the input value with leading/trailing ASCII whitespace removed.
1. `value_normalized` MUST be computed deterministically from `value` as follows:
   - `ipv4` / `ipv6`: MUST parse as an IP address; emit canonical textual form. For IPv6, canonical
     form MUST use RFC 5952-style compression.
   - `domain`: MUST be lowercased; MUST strip a single trailing dot if present.
   - `md5` / `sha1` / `sha256` / `sha512`: MUST be lowercased hex; MUST reject non-hex characters.
   - `url`: MUST be left as `value` for v0.2 (no structural URL normalization). (Reserved: future
     URL normalization contract.)

Stable indicator identity (normative):

`indicator_id` MUST be computed as:

```
indicator_id =
  "pa.ti.indicator.v1:" +
  sha256_hex(
    utf8_bytes("pa.ti.indicator_id.v1\0" + type + "\0" + value_normalized)
  )
```

#### Duplicate indicators and canonical ordering (normative)

Indicator-set intent:

- `indicators.jsonl` is semantically a *set* of indicators for matching/enrichment purposes.
- The on-disk JSONL is an ordered representation purely for deterministic hashing, diffs, and stable
  evidence selection.

Duplicate definition (normative):

- Two indicator records are duplicates if they have the same `indicator_id`.
- Because `indicator_id` is derived from `(type, value_normalized)`, duplicates also imply duplicate
  `(type, value_normalized)` pairs.

Uniqueness requirement (normative):

1. Within a single Threat Intel Pack, `indicator_id` MUST be unique across all lines in
   `indicators.jsonl`.
1. If duplicates are present after normalization, the pack is invalid:
   - When TI is enabled, the owning stage MUST fail closed by default.

Canonical ordering requirement (normative):

1. `indicators.jsonl` MUST be sorted by `indicator_id` ascending (UTF-8 byte order, no locale).
1. Pack producers MUST emit the file in this canonical order.
1. Consumers MUST treat out-of-order files as pack validation failure when TI is enabled.

Deterministic dedupe/merge rule (normative; for pack producers):

When constructing a pack from upstream sources, producers MUST collapse duplicates into a single
canonical record per `indicator_id` using the following deterministic merge semantics.

Let `G` be the group of records that share the same `(type, value_normalized)` (therefore the same
`indicator_id`). The merged record MUST be:

- `indicator_id`: computed per this ADR’s stable identity rule (and MUST match all group members).
- `type`: the shared `type` value (group key).
- `value_normalized`: the shared `value_normalized` value (group key).
- `value`: the minimum of the group’s `value` strings using UTF-8 byte order (no locale).
- `confidence`:
  - if any group member has a numeric `confidence`, set to the maximum numeric confidence value;
  - otherwise omit or set to `null`.
- `tags`:
  - MUST be the set-union of all tag strings across the group,
  - MUST be unique,
  - MUST be sorted ascending by UTF-8 byte order (no locale).
- `sources` (when present):
  - MUST be the set-union of all `sources[]` entries across the group,
  - duplicates MUST be removed by comparing `canonical_json_bytes(source_obj)` equality,
  - the resulting array MUST be sorted ascending by `canonical_json_bytes(source_obj)` (UTF-8 byte
    order, no locale).
- `valid_from_utc`:
  - if any member has `valid_from_utc`, set to the minimum RFC3339 timestamp among non-null values;
  - otherwise omit or set to `null`.
- `valid_until_utc`:
  - if any member has `valid_until_utc`, set to the maximum RFC3339 timestamp among non-null values;
  - otherwise omit or set to `null`.
- `extensions`:
  - For v0.2 baseline determinism, `extensions` MUST either be omitted, or MUST be byte-for-byte
    identical (by `canonical_json_bytes`) across all group members. If not identical, producers MUST
    omit `extensions` in the merged record.

Note: These merge semantics are intentionally conservative and deterministic. Future revisions may
introduce richer merge policy controls, but any such policy MUST preserve determinism and
testability.

### Consumption model (v0.2+)

Threat intel integration is intentionally separated into two layers:

1. **Input layer (normative in this ADR)**: versioned TI packs and deterministic run snapshots.
1. **Consumption layer (optional; stage-owned)**: how specific stages use TI snapshots for
   enrichment.

Consumption rules (normative):

1. Stages MAY read `inputs/threat_intel/*` when TI is enabled.
1. TI consumption MUST NOT introduce network access requirements at run time.
1. Unless explicitly specified by the scoring and reporting specifications, TI-derived enrichments
   MUST be treated as **supplemental** and MUST NOT change the regression comparable metric surface.

Reserved (non-normative) consumption examples:

- A reporting enrichment that lists observed indicators that match TI.
- An optional IoC matcher that emits detection-like artifacts under `detections/` with a distinct
  `rule_source` value. (If added, it MUST be contract-backed and deterministic.)

### Security and safety requirements (normative)

1. TI packs MUST NOT contain secrets (API keys, tokens, private keys). Any free-text note fields
   included in `extensions` MUST be treated as potentially sensitive and SHOULD either be omitted or
   redaction-processed under the effective redaction policy before being written to standard run
   bundle locations.
1. Implementations MUST NOT perform network fetches from TI platforms (including MISP) as an
   implicit side effect of enabling TI pack consumption.
1. If a future implementation adds an explicit “TI sync” capability, it MUST be:
   - default-off,
   - explicitly configured in `threat_intel.*` config keys (reserved),
   - fully observable (inputs, endpoints, timestamps, hashes),
   - and compliant with the project’s network egress safety posture (fail-closed on unexpected
     egress).

### Observability and failure semantics (v0.2+ requirements)

1. When TI is enabled and a pack is selected, the run MUST surface:
   - the selected `threat_intel_pack_id` and `threat_intel_pack_version` pins, and
   - the presence of the TI snapshot artifacts under `inputs/threat_intel/`.
1. If TI is enabled but the pack cannot be resolved or validated:
   - the owning stage MUST fail closed by default, and
   - the failure MUST be recorded in stage outcomes per ADR-0005.

Note: This ADR does not add ADR-0005 reason codes. The reason code registry update is a follow-up.

### State machine integration (representational; non-normative)

This section is an illustrative lifecycle view only. It does not define or constrain runtime stage
behavior; conformance is defined by the normative artifact contracts, publish semantics, and stage
outcome semantics in the preceding sections.

Lifecycle authority references (per ADR-0007 representational requirements):

- Pack resolution and validation: "Pack resolution and validation (normative)" in this ADR.
- Snapshot semantics: "Run-bundle snapshot model (normative)" in this ADR.
- Stage outcomes and run status derivation: ADR-0005 (stage outcomes and `manifest.status`
  derivation).
- Publish-gate intent: ADR-0004 and the architecture specification (staging + validation + atomic
  publish).

#### State machine: Threat Intel availability within a run (representational)

States (closed set):

- `ti_disabled`
- `ti_requested`
- `ti_resolving`
- `ti_resolved`
- `ti_validating`
- `ti_snapshotted`
- `ti_available`
- `ti_failed`

Transitions:

- `ti_disabled`:
  - Entered when TI is not enabled for the run.
- `ti_disabled -> ti_requested`:
  - Trigger: `threat_intel.enabled=true` and the owning stage begins.
- `ti_requested -> ti_resolving`:
  - Trigger: owning stage starts pack resolution (search paths + optional SemVer selection).
- `ti_resolving -> ti_resolved`:
  - Trigger: a concrete `(threat_intel_pack_id, threat_intel_pack_version)` and candidate directory
    (or pre-snapshotted `inputs/threat_intel/`) is selected.
- `ti_resolved -> ti_validating`:
  - Trigger: owning stage begins schema + hash validation of `manifest.json` and `indicators.jsonl`.
- `ti_validating -> ti_snapshotted`:
  - Trigger: pack validates and `inputs/threat_intel/` did not previously exist; owning stage
    performs snapshot materialization and atomic publish.
- `ti_validating -> ti_available`:
  - Trigger: pack validates and a read-only `inputs/threat_intel/` snapshot is already present.
- `ti_snapshotted -> ti_available`:
  - Trigger: snapshot publish completes successfully.
- `* -> ti_failed`:
  - Trigger: any resolution, validation, or snapshot I/O error while TI is enabled.

Observable signals (informative mapping):

- `ti_available` MUST correspond to the presence of:
  - `inputs/threat_intel/manifest.json`
  - `inputs/threat_intel/indicators.jsonl` and to the run provenance pins
    (`manifest.versions.threat_intel_pack_id` and `manifest.versions.threat_intel_pack_version`).
- `ti_failed` MUST correspond to an owning-stage failure recorded per ADR-0005.

Optional substage outcome mapping (non-normative):

- Implementations MAY emit additive substages under the owning stage to surface TI lifecycle steps
  (example: `<owning_stage>.threat_intel_resolve`, `<owning_stage>.threat_intel_validate`,
  `<owning_stage>.threat_intel_snapshot`).
- If emitted, substages MUST follow ADR-0005 ordering rules and reason-code registry rules.

## Consequences

### Positive

- Enables threat intel integration without undermining local determinism and reproducibility.
- Avoids introducing a full TI server stack (database + web app + background jobs) into the
  appliance.
- Makes TI use auditable: a run bundle contains the exact TI inputs that influenced enrichment.
- Keeps CI/regression comparability stable by default (TI is supplemental unless explicitly
  incorporated into scoring contracts).

### Trade-offs

- Operators who want MISP must run it separately and export/sync TI into versioned packs.
- A pack-and-snapshot workflow is less “live” than querying TI at runtime, but is intentionally
  safer and more reproducible.

## Alternatives considered

1. **Bundle a full MISP server in the orchestrator Docker bundle**

   - Rejected due to lifecycle mismatch (daemon + persistent DB), increased attack surface, and
     determinism drift risk unless aggressively snapshotted.

1. **Query MISP (or TAXII) live at run time**

   - Rejected for v0.2 due to reproducibility risk and the project’s default-off network side
     effects.
   - Could be revisited only with explicit, fully observable sync semantics and immutable snapshots.

1. **Treat TI as “just another rule set”**

   - Not chosen because TI indicator sets are semantically distinct from detection rule semantics
     and benefit from their own provenance and normalization contract.

## Follow-ups

This ADR requires follow-up changes before implementation can be considered complete:

1. **Contracts**

   - Add JSON Schemas under `docs/contracts/` for:
     - `threat_intel_pack_manifest.schema.json`
     - `threat_intel_indicator.schema.json`

1. **Config reference**

   - Reserve and document `threat_intel.*` configuration keys in `120_config_reference.md`:
     - enabling/disabling TI
     - selecting a TI pack `(id, version)`
     - (future) explicit sync controls, if ever added

1. **ADR-0005 reason code registry**

   - If TI pack validation introduces new stage-level `reason_code` values, ADR-0005 MUST be updated
     in the same change set (per ADR-0007 requirements).

1. **Reporting integration**

   - If reporting surfaces TI enrichments, update `080_reporting.md` with:
     - where TI summary appears
     - whether it is supplemental-only or impacts comparability

1. **Test strategy**

   - Add fixtures:
     - a minimal TI pack with deterministic hashes
     - a pack derived from a small upstream export (for example a MISP JSON export) proving stable
       normalization and stable `indicator_id` generation

## References

- [Scope specification](../spec/010_scope.md)
- [Architecture specification](../spec/020_architecture.md)
- [Data contracts specification](../spec/025_data_contracts.md)
- [Validation criteria packs specification](../spec/035_validation_criteria.md)
- [Scoring metrics specification](../spec/070_scoring_metrics.md)
- [Reporting specification](../spec/080_reporting.md)
- [Security and safety specification](../spec/090_security_safety.md)
- [Operator Interface specification](../spec/115_operator_interface.md)
- [Configuration reference](../spec/120_config_reference.md)
- [ADR-0001: Project naming and versioning](ADR-0001-project-naming-and-versioning.md)
- [ADR-0004: Deployment architecture and inter-component communication](ADR-0004-deployment-architecture-and-inter-component-communication.md)
- [ADR-0005: Stage outcomes and failure classification](ADR-0005-stage-outcomes-and-failure-classification.md)
- [ADR-0007: State machines for lifecycle semantics](ADR-0007-state-machines.md)

## Changelog

| Date       | Change                |
| ---------- | --------------------- |
| 2026-01-23 | Initial draft (v0.2+) |
