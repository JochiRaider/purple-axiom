---
title: Normalization to OCSF
description: Defines OCSF normalization rules, versioning policy, and required artifacts.
status: draft
+category: spec
tags: [ocsf, normalization, mapping, versioning]
related:
  - 025_data_contracts.md
  - 040_telemetry_pipeline.md
  - 042_osquery_integration.md
  - 045_storage_formats.md
  - 055_ocsf_field_tiers.md
  - 065_sigma_to_ocsf_bridge.md
  - 070_scoring_metrics.md
  - 085_golden_datasets.md
  - 120_config_reference.md
  - ../adr/ADR-0001-project-naming-and-versioning.md
  - ../adr/ADR-0002-event-identity-and-provenance.md
  - ../adr/ADR-0003-redaction-policy.md
  - ../adr/ADR-0004-deployment-architecture-and-inter-component-communication.md
  - ../adr/ADR-0005-stage-outcomes-and-failure-classification.md
---

# Normalization to OCSF

## Stage contract header

### Stage ID

- `stage_id`: `normalization`

### Owned output roots (published paths)

- `normalized/` (analytics-tier normalized store + mapping coverage/provenance)

### Inputs/Outputs

This section is the stage-local view of:

- the stage boundary table in
  [ADR-0004](../adr/ADR-0004-deployment-architecture-and-inter-component-communication.md), and
- the contract bindings in [contract_registry.json](../contracts/contract_registry.json).

#### Contract-backed outputs

| contract_id                | path/glob                                  | Required? |
| -------------------------- | ------------------------------------------ | --------- |
| `ocsf_event_envelope`      | `normalized/ocsf_events.jsonl`             | required  |
| `mapping_coverage`         | `normalized/mapping_coverage.json`         | required  |
| `mapping_profile_snapshot` | `normalized/mapping_profile_snapshot.json` | required  |

#### Required inputs

| contract_id    | Where found         | Required?                            |
| -------------- | ------------------- | ------------------------------------ |
| `range_config` | `inputs/range.yaml` | required                             |
| `manifest`     | `manifest.json`     | required (version pins + provenance) |

Notes:

- This stage consumes **non-contract** inputs in v0.1, notably `raw_parquet/**` (telemetry
  analytics-tier store) and mapping profiles.
- If an implementation emits normalized events as Parquet under `normalized/ocsf_events/`, it MUST
  either:
  - also emit `normalized/ocsf_events.jsonl` for contract conformance, or
  - update the contract registry + schemas and treat the change as a contract version bump.

### Config keys used

- `normalization.*` (OCSF pinning, mapping profiles, dedupe, output format)

### Default fail mode and outcome reasons

- Default `fail_mode`: `fail_closed` when `normalization.strict_mode=true`; otherwise
  `warn_and_skip`
- Stage outcome reason codes: see
  [ADR-0005](../adr/ADR-0005-stage-outcomes-and-failure-classification.md) § "Normalization stage
  (`normalization`)".

### Isolation test fixture(s)

- `tests/fixtures/normalization/mapping_unit/`
- `tests/fixtures/normalization/mapping_pack_conformance/`

See the [fixture index](100_test_strategy_ci.md#fixture-index) for the canonical fixture-root
mapping.

## Overview

This spec establishes OCSF as the canonical normalized event model, defines how versions and
profiles are pinned, and outlines the required artifacts and coverage outputs. It also describes
v0.1 osquery routing rules and the migration policy for OCSF version updates.

## Canonical model

- OCSF is the canonical normalized event model for all downstream evaluation and reporting.
- Normalization must be loss-minimizing: never discard source data that may be useful later.

## Versioning and profiles

- Pin a specific OCSF schema version per Purple Axiom release.
- Record the pinned OCSF version and enabled profiles or extensions in run provenance (manifest and
  normalized event metadata).
- Provide migration notes when updating the pinned OCSF version (field moves, enum changes, class
  reclassification).
- Mapping packs under `mappings/normalizer/ocsf/<ocsf_version>/<source_pack_id>/` MUST conform to
  `docs/mappings/ocsf_mapping_profile_authoring_guide.md` (directory structure, routing semantics,
  and deterministic parsing constraints).

## Pinned OCSF version (v0.1)

Purple Axiom v0.1 MUST pin the OCSF schema version to:

- `ocsf_version = "1.7.0"`

Conformance requirements (v0.1):

- `manifest.versions.ocsf_version` MUST be the authoritative OCSF version pin for the run.
- Every run MUST record the effective `ocsf_version` used for normalization in
  `manifest.versions.ocsf_version`.
- Producers MAY also record `manifest.normalization.ocsf_version` for compatibility, but consumers
  MUST treat `manifest.versions.ocsf_version` as authoritative.
  - If both are present, `manifest.normalization.ocsf_version` MUST equal
    `manifest.versions.ocsf_version` byte-for-byte.
- `normalized/mapping_profile_snapshot.json.ocsf_version` MUST be present when
  `normalized/mapping_profile_snapshot.json` is emitted and MUST equal
  `manifest.versions.ocsf_version` byte-for-byte.
- When Sigma-to-OCSF Bridge artifacts are present, the bridge mapping pack MUST declare the same
  `ocsf_version` as `manifest.versions.ocsf_version`. A mismatch MUST be treated as an incompatible
  configuration (fail closed).

## OCSF schema update and migration policy

Cadence (project policy):

- The pinned OCSF version SHOULD be reviewed quarterly.
- The pinned OCSF version MUST NOT change silently. A version bump MUST be an explicit, reviewed
  change (PR that updates specs, fixtures, and CI gates).

Required steps for changing the pinned OCSF version (normative):

1. Update the pinned `ocsf_version` in:
   - `docs/spec/050_normalization_ocsf.md` (this section)
   - `docs/spec/120_config_reference.md` (examples and any stated defaults)
   - `README.md` (examples)
1. Update normalization mapping material so produced events remain valid against the new pinned
   version:
   - Update mapping profile(s) and refresh `normalized/mapping_profile_snapshot.json` semantics as
     needed.
1. Update bridge mapping packs as needed:
   - Router tables and field aliases MUST be evaluated for field moves, renames, and enum changes.
1. Migration testing MUST be added or updated (see the
   [test strategy and CI spec](100_test_strategy_ci.md)):
   - A fixed raw telemetry fixture set MUST be re-normalized under the new pinned version.
   - Expected outputs MUST be captured as golden artifacts, with diffs reviewed.

## Mapping strategy (industry-aligned)

- Preserve source fidelity:
  - retain original or raw payload (or a redacted-safe representation / reference) for audit and
    forensics, subject to `normalization.raw_preservation` and the
    [redaction policy ADR](../adr/ADR-0003-redaction-policy.md)
  - route unmapped fields into an explicit `raw` object so nothing is silently dropped
    - `raw` is a Purple Axiom extension (Tier R) and is not required to be OCSF-conformant
    - values placed under `raw` MUST be redaction-safe for standard long-term artifact locations
    - `unmapped` MAY be used for derived fields that could not be mapped after routing, but `raw` is
      the canonical location for retaining the source payload
- Preserve synthetic correlation markers in the normalized envelope even when the base event is
  unmapped:
  - if the source record carries:
    - `metadata.extensions.purple_axiom.synthetic_correlation_marker`, and/or
    - `metadata.extensions.purple_axiom.synthetic_correlation_marker_token`, (the same values are
      also recorded in ground truth action records as `extensions.synthetic_correlation_marker` and
      `extensions.synthetic_correlation_marker_token`; see `025_data_contracts.md`), the normalizer
      MUST preserve them verbatim at the same paths on the emitted envelope
  - the synthetic correlation marker fields MUST NOT be used as part of `metadata.event_id`
    computation
  - if the record is otherwise unrouted/unmapped, the normalizer MUST still emit a minimal OCSF
    envelope record (see "Required envelope (Purple Axiom contract)") and retain the payload per the
    source-fidelity rules above (marker-bearing records MUST NOT be dropped as "unmapped noise")
  - for marker-bearing records where no OCSF `class_uid` can be assigned from routing/mapping, the
    normalizer MUST NOT guess a `class_uid`; it MUST set `class_uid = 0` (reserved "unmapped") and
    MUST count the record as unmapped in `normalized/mapping_coverage.json`
- Core-first mapping:
  - define a small core field set per event class (mandatory + high-value entities)
  - map core fields deterministically; enrich incrementally over time
- Prefer declarative mappings where practical:
  - mapping tables or config per `source_type` and profile
  - minimal imperative code limited to parsing, derived fields, and edge-case handling

## Required envelope (Purple Axiom contract)

The minimum envelope requirements for normalized events are defined in the
[data contracts spec](025_data_contracts.md) and the Tier 0 core field tier definition in the
[OCSF field tiers spec](055_ocsf_field_tiers.md). The following fields MUST be present on every
normalized event (keys MAY be null only where explicitly noted).

- `time` (ms since epoch, UTC)
- `class_uid`
- `metadata.uid` (MUST equal `metadata.event_id`)
- `metadata.event_id` (stable, deterministic)
- `metadata.run_id`
- `metadata.scenario_id`
- `metadata.collector_version`
- `metadata.normalizer_version`
- `metadata.source_type`
- `metadata.source_event_id` (source-native upstream ID when meaningful; else null)
- `metadata.identity_tier` (1 | 2 | 3; see the
  [event identity ADR](../adr/ADR-0002-event-identity-and-provenance.md))
- `metadata.extensions.purple_axiom.raw_ref` (stable raw provenance pointer; required for identity
  tiers 1 and 2; MUST be `null` for identity tier 3; see
  [ADR-0002](../adr/ADR-0002-event-identity-and-provenance.md))

Terminology note (normative):

- `metadata.source_type` is the **event_source_type** discriminator. It MAY differ from the
  **identity_source_type** used for event-id hashing (`identity_basis.source_type`; see
  [ADR-0002](../adr/ADR-0002-event-identity-and-provenance.md)).
- Implementations MUST NOT assume these values are equal and MUST NOT rewrite either value to force
  equality.

Optional envelope extensions (v0.1):

- `metadata.extensions.purple_axiom.synthetic_correlation_marker` (string)
- `metadata.extensions.purple_axiom.synthetic_correlation_marker_token` (string)
- `metadata.extensions.purple_axiom.raw_refs` (array of `raw_ref` objects; MAY be present when an
  emitted normalized event is derived from multiple raw records; see
  [ADR-0002](../adr/ADR-0002-event-identity-and-provenance.md))

Vendor-field rule (normative):

- New project-owned envelope extension fields MUST be added under `metadata.extensions.purple_axiom`
  (not as new `metadata.*` siblings).

### Raw provenance linkage (required)

Normalization MUST preserve a stable raw provenance pointer from upstream telemetry ingestion:

- For every emitted normalized event with `metadata.identity_tier ∈ {1,2}`,
  `metadata.extensions.purple_axiom.raw_ref` MUST be present and MUST conform to
  `ADR-0002-event-identity-and-provenance.md`.
- If the normalizer emits multiple normalized events from a single raw/source record, all derived
  events MUST share the same `raw_ref`.
- If the normalizer emits an aggregated event derived from multiple raw/source records, it MUST:
  - set `raw_ref` to the canonical origin per ADR-0002, and
  - SHOULD emit `raw_refs` containing all known origins.
- `raw_ref` and `raw_refs` MUST NOT influence `metadata.event_id` computation.

## Osquery normalization (v0.1)

Osquery is a query engine rather than a single semantic event stream. Normalization MUST therefore
be driven by the osquery scheduled query name:

- The normalizer MUST set `metadata.source_type = "osquery"` for all osquery-derived events.
- Routing MUST be based on the osquery `name` field (hereafter `query_name`) using a declarative
  routing table captured in `normalized/mapping_profile_snapshot.json`.
- v0.1 routing defaults (mapping profile MAY override explicitly):
  - `process_events` -> Process Activity (`class_uid: 1007`)
  - `file_events` -> File System Activity (`class_uid: 1001`)
  - `socket_events` -> Network Activity (`class_uid: 4001`)
- v0.1 routing defaults (mapping profile MAY override explicitly):
  - `process_events` -> Process Activity (`class_uid: 1007`)
  - `process_etw_events` -> Process Activity (`class_uid: 1007`)
  - `file_events` -> File System Activity (`class_uid: 1001`)
  - `ntfs_journal_events` -> File System Activity (`class_uid: 1001`)
  - `socket_events` -> Network Activity (`class_uid: 4001`)

Unrouted behavior:

- The normalizer MUST NOT guess a `class_uid` for an unknown `query_name`.
- Unknown `query_name` rows MUST be preserved in `raw/` and MUST be counted in
  `normalized/mapping_coverage.json` as unrouted or unmapped.
- If an unknown `query_name` row carries either
  `metadata.extensions.purple_axiom.synthetic_correlation_marker` or
  `metadata.extensions.purple_axiom.synthetic_correlation_marker_token`, the normalizer MUST still
  emit a minimal normalized event record with `class_uid = 0`, preserve whichever marker fields are
  present, and include the required envelope fields per "Required envelope (Purple Axiom contract)".

Implementation details and conformance fixtures are specified in the
[osquery integration spec](042_osquery_integration.md).

## Run bundle artifacts

When normalization is enabled, the normalizer MUST emit:

- `normalized/mapping_profile_snapshot.json` (required)
- `normalized/mapping_coverage.json` (required; MUST be emitted even when zero events are
  normalized)

Note (normative): `normalized/mapping_profile_snapshot.json` is the normalization mapping provenance
snapshot. It is distinct from `bridge/mapping_pack_snapshot.json` (Sigma-to-OCSF bridge provenance)
which is emitted by the detection stage when Sigma bridge evaluation is enabled.

When normalization produces an OCSF event store, the normalizer MUST emit the contract-backed JSONL
envelope:

- `normalized/ocsf_events.jsonl`

Implementations MAY also emit a Parquet dataset directory for long-term storage and evaluation:

- `normalized/ocsf_events/` (Parquet dataset directory; MUST include
  `normalized/ocsf_events/_schema.json`)

If both representations are present, they MUST be derived from the same logical normalized event
stream for the run (no divergence in `metadata.event_id`).

### Deduplication and replay

Normalization and storage MUST be idempotent with respect to `metadata.event_id` (dedupe key).

Normative requirements (v0.1):

- Deduplication MUST be enforced for the normalized event store within a single run bundle.
- Deduplication MUST be based on `metadata.event_id`.
- When `normalization.dedupe.enabled=true`, the normalizer MUST persist a durable dedupe index under
  `logs/dedupe_index/` (run-relative; configurable via `normalization.dedupe.index_dir`).
- On restart for the same `run_id`, if the dedupe index is missing or corrupt but the normalized
  store already contains rows, the normalizer MUST rebuild the dedupe index by scanning
  `metadata.event_id` from the existing normalized store before appending any new rows.
- Dedupe conflict handling MUST be deterministic. If two non-identical instances share the same
  `metadata.event_id`, the normalizer MUST treat this as a data-quality signal and MUST select the
  canonical instance deterministically (see the
  [event identity ADR](../adr/ADR-0002-event-identity-and-provenance.md) for the canonical selection
  rule).

Regression comparable normalization metric inputs (normative):

- Any normalization-stage metric that participates in regression comparisons MUST be computable from
  deterministic artifacts in the run bundle.
- For v0.1, the comparable normalization surface MUST be derived from:
  - `normalized/mapping_coverage.json` (aggregate and per-source coverage inputs), and
  - `normalized/mapping_profile_snapshot.json` (pins mapping inputs via hashes).
- Comparable normalization surfaces MUST NOT incorporate environment-dependent timestamps. Timestamp
  fields MAY be recorded as informational only (for example `generated_at_utc`) and MUST NOT
  participate in regression deltas or gating.

#### Durable dedupe index contract (normative, v0.1)

The requirements below are restatements of the
[event identity ADR](../adr/ADR-0002-event-identity-and-provenance.md) to make the dedupe + replay
contract mechanically implementable and testable.

- **Window:** Deduplication MUST consider the full run window (unbounded within the run), i.e.
  dedupe MUST consider all previously-emitted normalized events for the run, not only “recent”
  events.
- **Non-goal:** The project does not require `metadata.event_id` to be globally unique across run
  bundles. Replays across different runs MAY intentionally produce the same `metadata.event_id`.
- **On-disk durability:** The dedupe index MUST be persisted to disk inside the run bundle under
  `runs/<run_id>/logs/` (example: `runs/<run_id>/logs/dedupe_index/ocsf_events.*`) and MUST survive
  process restarts for the same `run_id`.
  - All files that comprise the dedupe index (including engine sidecars such as journals/WAL/lock
    files) MUST be contained under `logs/dedupe_index/` so they remain classified as volatile
    diagnostics.
- **Duplicate equivalence (volatile-field removal):**
  - Define `instance_without_volatile_fields` as the normalized event with the following fields
    removed when present:
    - `metadata.ingest_time_utc`
    - `metadata.observed_time`
    - `metadata.extensions.purple_axiom.ingest_id`
  - Define `instance_canonical_bytes = canonical_json_bytes(instance_without_volatile_fields)`.
  - Define `conflict_key = sha256_hex(instance_canonical_bytes)`.
    - `canonical_json_bytes` and `sha256_hex` MUST follow the canonical JSON + hashing rules in
      `025_data_contracts.md` (RFC 8785 JCS; UTF-8 bytes; lowercase hex digest).
- **Exact duplicates:** When an incoming normalized event is suppressed as an exact duplicate
  (equivalent after volatile-field removal) because its `metadata.event_id` is already present in
  the dedupe index, the normalizer MUST increment `dedupe_duplicates_dropped_total` (see
  `110_operability.md`).
- **Non-identical duplicates:** If two instances share the same `metadata.event_id` but have
  different `instance_canonical_bytes`:
  - The normalizer MUST treat this as a **dedupe conflict** (a data-quality signal).
  - The canonical instance retained for a given `metadata.event_id` MUST be the instance with the
    lexicographically smallest `conflict_key` across all observed instances for that
    `metadata.event_id`, independent of ingestion order.
  - The normalizer MUST increment `dedupe_conflicts_total` each time a non-equivalent instance is
    observed for an existing `metadata.event_id` (see `110_operability.md`).
  - The normalizer MUST record minimal conflict evidence under `runs/<run_id>/logs/` (without
    writing sensitive payloads into long-term artifacts). Minimal evidence SHOULD include:
    - `metadata.event_id`
    - `metadata.source_type`
    - `identity_source_type` (the value used for `identity_basis.source_type`)
    - `metadata.source_event_id`
    - `metadata.identity_tier`
    - `conflict_key` of the incoming instance and the retained canonical instance
- **Export + signing classification:** `logs/dedupe_index/**` is volatile diagnostics (see
  `025_data_contracts.md` and
  [ADR-0009](../adr/ADR-0009-run-export-policy-and-log-classification.md)) and MUST NOT be included
  in default export bundles or signing/checksum scope.

#### Storage engine note (non-normative)

The spec does not mandate the storage engine for the dedupe index, only the behavioral contract
above. A file-backed embedded DB is a natural fit (example: `logs/dedupe_index/ocsf_events.sqlite`),
because it can enforce uniqueness on `metadata.event_id` and support transactional updates when
selecting the canonical instance on conflicts.

### Mapping profile snapshot

Purpose:

- Pin the exact mapping inputs (configuration and transforms) used to normalize source telemetry
  into OCSF.

Requirements (normative):

- MUST validate against `mapping_profile_snapshot.schema.json`.
- MUST record the pinned `ocsf_version`.
  - When `manifest.json` is present, `normalized/mapping_profile_snapshot.json.ocsf_version` MUST
    equal `manifest.versions.ocsf_version` byte-for-byte.
- MUST include `mapping_profile_id`, `mapping_profile_version`, and `mapping_profile_sha256`.
- MUST include per-source mapping material hashes as `source_profiles[].mapping_material_sha256`.

Hashing (normative):

- All JSON serialized for hashing in this section MUST use the canonical JSON requirements defined
  in the [data contracts spec](025_data_contracts.md) (RFC 8785, JCS).
- `mapping_material_sha256` MUST be computed as
  `sha256_hex(canonical_json_bytes(mapping_material_basis))`, where:
  - If `mapping_material` is embedded, `mapping_material_basis` is exactly that JSON object.
  - If only `mapping_files[]` are provided, `mapping_material_basis` is a JSON array of
    `{path,sha256}` entries sorted by `path` ascending (UTF-8 byte order, no locale) prior to
    serialization.
- `mapping_profile_sha256` MUST be computed as
  `sha256_hex(canonical_json_bytes(mapping_profile_basis))`, where `mapping_profile_basis` is a JSON
  object containing only stable inputs:
  - `ocsf_version`
  - `mapping_profile_id`
  - `mapping_profile_version`
  - `source_profiles[]` projected to `{source_type, profile, mapping_material_sha256}`
- The hash basis MUST NOT include run-specific fields (`run_id`, `scenario_id`, `generated_at_utc`).
- `source_profiles[]` MUST be deterministically ordered (sort by `source_type` ascending, UTF-8 byte
  order, no locale).

### Mapping coverage

Purpose:

- Provide machine-checkable coverage metrics for:
  - event class routing (`class_uid`)
  - missing core fields (per class)
  - unmapped or dropped events

Requirements (normative):

- MUST validate against `mapping_coverage.schema.json`.
- MUST reference the mapping profile via `mapping_profile_sha256` so coverage is attributable to
  mapping changes vs telemetry changes.
- `normalized/mapping_coverage.json` is the canonical evidence artifact for normalization-layer gap
  classification (example: `normalization_gap`) and MUST be suitable for direct inclusion in
  `evidence_refs[].artifact_path` as `normalized/mapping_coverage.json` (run-relative path, POSIX
  separators, deterministic content).

Deterministic computation rules (normative):

- Any per-source arrays or maps emitted by `normalized/mapping_coverage.json` that are used for
  regression comparisons MUST be deterministically ordered:
  - Sort by `source_type` ascending (UTF-8 byte order, no locale).
- Any rates, ratios, or `_pct` metrics emitted in comparable metric surfaces MUST be rounded to 4
  decimal places using round-half-up semantics.

Regression comparable normalization metrics (normative):

At minimum, normalization MUST expose the following comparable metrics for regression analysis:

- `tier1_field_coverage_pct` (overall; unitless fraction in `[0.0, 1.0]`), derived from
  `normalized/mapping_coverage.json` and computed over the in-scope normalized events as defined in
  the OCSF field tiers spec.
- Per-source `tier1_field_coverage_pct` (same units), keyed by `metadata.source_type` values and
  derived from `normalized/mapping_coverage.json`.

These comparable metrics MUST be attributable to a specific mapping profile via
`mapping_profile_sha256` so mapping drift can be distinguished from telemetry drift
deterministically.

## Core entities guidance (best practice)

- Ensure high-query entities are normalized consistently:
  - device or host identity
  - user or principal identity
  - application or service identity
  - (where applicable) src or dst network endpoints
- Apply data integrity checks for required or mapped core fields (nullability, type coercion
  policy).

## Normalization practicalities to handle explicitly

- Differing source column types -> deterministic coercion rules
- Derived fields -> explicit derivation functions with tests
- Missing or null fields -> consistent defaults or null semantics
- Literal normalization -> stable enumerations ("Success" and "Failure", and so on)
- Schema evolution -> backward-compatibility policy for stored artifacts
- Enrichment -> well-defined join points (asset inventory, threat intel, scenario context)

## Validation strategy

- Tier 0 (CI gate): validate normalized events against the Purple Axiom envelope contract
  (`ocsf_event_envelope.schema.json`) and required invariants (stable identity, required fields, and
  deterministic time representation).
- Tier 1 (CI gate): compute Tier 1 field coverage from `normalized/mapping_coverage.json` per the
  OCSF field tiers spec and enforce configured regression gates.
- Tier 2 (deep validation): validate selected classes or sources against pinned OCSF schema
  artifacts.
- Tier 3 (storage): enforce Parquet schema + partitioning + deterministic ordering for long-term
  storage.
- Tier R (CI gate): enforce redaction-safe raw retention policy for any material placed under
  `raw.*` in normalized events.
- Regression fixture (normative):
  - Add a fixture where normalized events exist but Tier 1 field coverage declines.
  - Expected: classification is normalization layer, with `evidence_refs[]` including
    `normalized/mapping_coverage.json`.
  - Fixture design MUST drive a deterministic change in Tier 1 coverage by adjusting normalized
    envelope field presence (Tier 1 pivots are explicitly measured and gated).

## Observability and coverage

- Emit mapping coverage:
  - % events mapped by class_uid or source_type
  - unknown or unclassified event types
  - missing core fields rate per class
- Treat mapping regressions as first-class failures (reportable + trendable).
- Downstream evaluator alignment:
  - Track coverage for the Sigma-to-OCSF bridge MVP field surface (see the
    [Sigma to OCSF bridge spec](065_sigma_to_ocsf_bridge.md)).
  - Report when normalizer changes increase `bridge_gap` risk (fields dropped or renamed, class
    routing changes).

## Key decisions

- OCSF is the canonical normalized event model and is pinned per release.
- Normalization artifacts must include mapping snapshots and coverage metrics for determinism.
- Osquery routing is based on scheduled query names with explicit unrouted handling.

## References

- [Data contracts spec](025_data_contracts.md)
- [Telemetry pipeline spec](040_telemetry_pipeline.md)
- [Osquery integration spec](042_osquery_integration.md)
- [Storage formats spec](045_storage_formats.md)
- [OCSF field tiers spec](055_ocsf_field_tiers.md)
- [Sigma to OCSF bridge spec](065_sigma_to_ocsf_bridge.md)
- [Test strategy and CI spec](100_test_strategy_ci.md)
- [Config reference](120_config_reference.md)
- [OCSF schema documentation](https://schema.ocsf.io/)

## Changelog

| Date      | Change                                       |
| --------- | -------------------------------------------- |
| 1/20/2026 | feature updates                              |
| TBD       | Style guide migration (no technical changes) |
