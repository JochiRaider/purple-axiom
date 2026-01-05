# Normalization to OCSF

## Canonical model
- OCSF is the canonical normalized event model for all downstream evaluation and reporting.
- Normalization must be *loss-minimizing*: never discard source data that may be useful later.

## Versioning and profiles
- Pin a specific OCSF schema version per Purple Axiom release.
- Record the pinned OCSF version and enabled profiles/extensions in run provenance (manifest + normalized event metadata).
- Provide migration notes when updating the pinned OCSF version (field moves, enum changes, class reclassification).

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


## Run bundle artifacts (normalized/)

When normalization is enabled and produces an OCSF event store, the normalizer MUST emit:

- `normalized/ocsf_events.parquet` (or `normalized/ocsf_events.jsonl` for small fixtures)
- `normalized/mapping_profile_snapshot.json` (required)
- `normalized/mapping_coverage.json` (required)

### Mapping profile snapshot

Purpose:
- Pin the exact mapping inputs (configuration and transforms) used to normalize source telemetry into OCSF.

Requirements (normative):
- MUST validate against `mapping_profile_snapshot.schema.json`.
- MUST record the pinned `ocsf_version` and a `mapping_profile_sha256` (hash over mapping material).
- `mapping_profile_sha256` MUST be computed over stable mapping inputs and MUST NOT include run-specific fields.
- MUST include per-source-type mapping material hashes, so changes are detectable without parsing large raw datasets.

### Mapping coverage

Purpose:
- Provide machine-checkable coverage metrics for:
  - event class routing (`class_uid`)
  - missing core fields (per class)
  - unmapped or dropped events

Requirements (normative):
- MUST validate against `mapping_coverage.schema.json`.
- MUST reference the mapping profile via `mapping_profile_sha256` so coverage is attributable to mapping changes vs telemetry changes.


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
- Tier 3 (storage): enforce Parquet schema + partitioning + deterministic ordering for long-term storage.

## Observability and coverage
- Emit mapping coverage:
  - % events mapped by class_uid/source_type
  - unknown/unclassified event types
  - missing core fields rate per class
- Treat mapping regressions as first-class failures (reportable + trendable).

- Downstream evaluator alignment:
  - Track coverage for the Sigma-to-OCSF Bridge MVP field surface (see `065_sigma_to_ocsf_bridge.md`).
  - Report when normalizer changes increase `bridge_gap` risk (fields dropped/renamed, class routing changes).
  
## References
- Use the OCSF schema repo and example translations as guidance, not as a gold standard.
- Prefer production-shaped references (e.g., Security Lake transformation patterns) when designing mappings.