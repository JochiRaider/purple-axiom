<!-- docs/spec/050_normalization_ocsf.md -->

# Normalization to OCSF

## Canonical model

- OCSF is the canonical normalized event model for all downstream evaluation and reporting.
- Normalization must be *loss-minimizing*: never discard source data that may be useful later.

## Versioning and profiles

- Pin a specific OCSF schema version per Purple Axiom release.
- Record the pinned OCSF version and enabled profiles/extensions in run provenance (manifest +
  normalized event metadata).
- Provide migration notes when updating the pinned OCSF version (field moves, enum changes, class
  reclassification).

## Pinned OCSF version (v0.1)

Purple Axiom v0.1 MUST pin the OCSF schema version to:

- `ocsf_version = "1.7.0"`

Conformance requirements (v0.1):

- Every run MUST record the effective `ocsf_version` used for normalization in run provenance.
  - Minimum: `normalized/mapping_profile_snapshot.json.ocsf_version`.
  - RECOMMENDED: also record in `manifest.json` (see `025_data_contracts.md` recommended manifest
    additions).
- When Sigma-to-OCSF Bridge artifacts are present, the bridge mapping pack MUST declare the same
  `ocsf_version` as the normalizer output for that run. A mismatch MUST be treated as an
  incompatible configuration (fail closed).

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
   - Router tables and field aliases MUST be evaluated for field moves/renames and enum changes.
1. Migration testing MUST be added/updated (see `docs/spec/100_test_strategy_ci.md`):
   - A fixed raw telemetry fixture set MUST be re-normalized under the new pinned version.
   - Expected outputs MUST be captured as “golden” artifacts, with diffs reviewed.

## Mapping strategy (industry-aligned)

- Preserve source fidelity:
  - retain original/raw payload (or a redacted-safe representation) for audit/forensics
  - route unmapped fields into an explicit `unmapped` / `raw` object so nothing is silently dropped
- “Core first” mapping:
  - define a small “core field set” per event class (mandatory + high-value entities)
  - map core fields deterministically; enrich incrementally over time
- Prefer declarative mappings where practical:
  - mapping tables/config per source_type and profile
  - minimal imperative code limited to parsing + derived fields + edge-case handling

## Required envelope (Purple Axiom contract)

- `time` (UTC)
- `class_uid`
- `metadata.event_id` (stable, deterministic)
- `metadata.run_id`
- `metadata.scenario_id`
- `metadata.collector_version`
- `metadata.normalizer_version`
- `metadata.source_type`

## osquery normalization (v0.1)

osquery is a query engine rather than a single semantic event stream. Normalization MUST therefore
be driven by the osquery scheduled query name:

- The normalizer MUST set `metadata.source_type = "osquery"` for all osquery-derived events.
- Routing MUST be based on the osquery `name` field (hereafter `query_name`) using a declarative
  routing table captured in `normalized/mapping_profile_snapshot.json`.
- v0.1 routing defaults (mapping profile MAY override explicitly):
  - `process_events` → Process Activity (`class_uid: 1007`)
  - `file_events` → File System Activity (`class_uid: 1001`)
  - `socket_events` → Network Activity (`class_uid: 4001`)

Unrouted behavior:

- The normalizer MUST NOT guess a `class_uid` for an unknown `query_name`.
- Unknown `query_name` rows MUST be preserved in `raw/` and MUST be counted in
  `normalized/mapping_coverage.json` as unrouted/unmapped.

Implementation details and conformance fixtures are specified in `042_osquery_integration.md`.

## Run bundle artifacts (normalized/)

When normalization is enabled and produces an OCSF event store, the normalizer MUST emit:

- `normalized/ocsf_events.parquet` (or `normalized/ocsf_events.jsonl` for small fixtures)
- `normalized/mapping_profile_snapshot.json` (required)
- `normalized/mapping_coverage.json` (required)

### Mapping profile snapshot

Purpose:

- Pin the exact mapping inputs (configuration and transforms) used to normalize source telemetry
  into OCSF.

Requirements (normative):

- MUST validate against `mapping_profile_snapshot.schema.json`.
- MUST record the pinned `ocsf_version` and a `mapping_profile_sha256` (hash over mapping material).
- `mapping_profile_sha256` MUST be computed over stable mapping inputs and MUST NOT include
  run-specific fields.
- MUST include per-source-type mapping material hashes, so changes are detectable without parsing
  large raw datasets.

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

## “Core entities” guidance (best practice)

- Ensure high-query entities are normalized consistently:
  - device/host identity
  - user/principal identity
  - application/service identity
  - (where applicable) src/dst network endpoints
- Apply data integrity checks for required/mapped core fields (nullability, type coercion policy).

## Normalization practicalities to handle explicitly

- Differing source column types → deterministic coercion rules
- Derived fields → explicit derivation functions with tests
- Missing/null fields → consistent defaults/null semantics
- Literal normalization → stable enumerations (“Success/Failure”, etc.)
- Schema evolution → backward-compatibility policy for stored artifacts
- Enrichment → well-defined join points (asset inventory, threat intel, scenario context)

## Validation strategy

- Tier 1 (CI gate): validate against Purple Axiom envelope contract + invariants.
- Tier 2 (deep validation): validate selected classes/sources against pinned OCSF schema artifacts.
- Tier 3 (storage): enforce Parquet schema + partitioning + deterministic ordering for long-term
  storage.

## Observability and coverage

- Emit mapping coverage:

  - % events mapped by class_uid/source_type
  - unknown/unclassified event types
  - missing core fields rate per class

- Treat mapping regressions as first-class failures (reportable + trendable).

- Downstream evaluator alignment:

  - Track coverage for the Sigma-to-OCSF Bridge MVP field surface (see
    `065_sigma_to_ocsf_bridge.md`).
  - Report when normalizer changes increase `bridge_gap` risk (fields dropped/renamed, class routing
    changes).

## References

- Use the OCSF schema repo and example translations as guidance, not as a gold standard.
- Prefer production-shaped references (e.g., Security Lake transformation patterns) when designing
  mappings.
