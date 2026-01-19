---
title: ADR-0001 Project naming and versioning
description: Defines stable naming and versioning conventions for runs, scenarios, packs, mappings, and schema pins to enable reproducible scoring.
status: draft
category: adr
tags: [versioning, naming, determinism, provenance]
related:
  - ../spec/025_data_contracts.md
  - ../spec/030_scenarios.md
  - ../spec/035_validation_criteria.md
  - ../spec/045_storage_formats.md
  - ../spec/080_reporting.md
  - ../spec/120_config_reference.md
  - ADR-0002-event-identity-and-provenance.md
---

# ADR-0001: Project naming and versioning

This ADR defines the naming and versioning conventions for Purple Axiom so runs remain comparable
over time and CI can detect drift deterministically. It establishes version domains, pinning
requirements, and validation checks that enforce reproducibility.

## Context

Purple Axiom needs stable identifiers and explicit version pins for scenarios, rules, mappings, and
pipeline components so that:

- runs are reproducible and comparable across time
- reporting and trending joins are stable and deterministic
- “same inputs” can be meaningfully asserted and tested in CI
- unpinned or ambiguous inputs fail closed instead of silently drifting

Several specs already assume the existence of pinned versions (for example: OCSF version pinning,
criteria pack selection, reporting trending keys, dataset schema version snapshots), but a single,
authoritative naming and versioning contract has not yet been consolidated.

## Decision

Purple Axiom MUST implement the naming, versioning, and pinning conventions below.

### Version domains

Purple Axiom uses distinct version domains. A version value MUST NOT be reused across domains unless
explicitly stated.

1. **Project release version**

   - `project_version` MUST be SemVer (SemVer 2.0.0).
   - `project_version` identifies the Purple Axiom release (codebase).

1. **Run identifier**

   - `run_id` MUST be an RFC 4122 UUID string in canonical hyphenated form, lowercase hex.
   - `run_id` MUST be globally unique and MUST NOT be reused.

1. **Scenario identity and version**

   - `scenario_id` MUST be a stable identifier for a logical scenario (independent of code release).
   - `scenario_version` MUST be SemVer and MUST be versioned independently from `project_version`.

1. **Pack-like artifacts** The following are “pack-like” artifacts: they are selected for a run,
   pinned, and treated as immutable per version.

   - criteria packs: `criteria_pack_id`, `criteria_pack_version`
   - rule sets (Sigma or other): `rule_set_id`, `rule_set_version`
   - mapping packs (Sigma-to-OCSF bridge): `mapping_pack_id`, `mapping_pack_version`
   - mapping profiles (telemetry source to OCSF mapping profile): `mapping_profile_id`,
     `mapping_profile_version` (when profiles are packaged and versioned)

1. **Schema and contract versions**

   - Each JSON Schema contract has a `contract_version` constant.
   - Parquet datasets have a logical `schema_version` (SemVer) recorded in `_schema.json`.

1. **Component and tool versions** Implementations SHOULD record versions for conformance-critical
   components (for example: runner, telemetry collector, normalizer, evaluator), so that drift is
   visible and explainable.

### Canonical identifier formats

#### ID strings (`*_id`)

All `*_id` fields defined by this ADR MUST conform to `id_slug_v1`.

`id_slug_v1` requirements (normative):

- MUST be ASCII lowercase.
- MUST contain only `a-z`, `0-9`, and `-`.
- MUST be 1 to 64 characters long.
- MUST start with `a-z` or `0-9`.
- MUST end with `a-z` or `0-9`.
- MUST NOT contain `--` (double hyphen).

Regex (informative, suitable for schema validation):

- `^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])$` plus an additional check that `--` is not present.

Rationale:

- Safe for filesystem paths, JSON keys, and URLs.
- Avoids case-normalization ambiguity across operating systems and tools.

#### Version strings (`*_version`)

All `*_version` fields defined by this ADR MUST conform to SemVer 2.0.0.

SemVer requirements (normative):

- MUST be parseable as SemVer 2.0.0 (`MAJOR.MINOR.PATCH` with optional pre-release and build).
- MUST NOT include a leading `v` (for example, `1.2.3`, not `v1.2.3`).
- When a version is recorded in artifacts, it MUST be recorded exactly as the SemVer string (no
  additional prefixes or formatting).

### Run bundle naming and path safety

- The run bundle directory name MUST be exactly the `run_id` string:
  - `runs/<run_id>/`
- Any human-readable labels (for example, “run name”, “run label”) MAY exist but MUST NOT be used as
  identifiers, join keys, or directory names.
- Producers MUST treat `run_id` as the only stable identifier for a specific execution.

### Canonical pin location in the run manifest

The run manifest is the authoritative location for the effective pins used by a run.

#### `manifest.versions` (normative)

The manifest MUST include a top-level `versions` object. `versions` MUST record the effective
resolved pins for a run (after any “latest” or omitted-version resolution is applied).

Minimum required keys in `manifest.versions` (v0.1 baseline, normative):

These keys are the canonical pin set for regression comparability and trending joins. Downstream
specifications that define regression comparability checks (for example, the reporting
specification) MUST treat this list as authoritative and MUST NOT redefine pin names or introduce
alternate pin locations for regression comparisons.

- `project_version` (SemVer)
- `pipeline_version` (SemVer)
  - Definition: the pipeline definition version used to interpret config and produce artifacts. This
    MAY equal `project_version`, but MUST be recorded explicitly for trending joins.
- `scenario_id` (id_slug_v1)
- `scenario_version` (SemVer)
- `ocsf_version` (SemVer or OCSF upstream version string if OCSF does not publish SemVer; the
  implementation MUST still record the exact pinned value)
- `criteria_pack_id` (id_slug_v1), when criteria evaluation is enabled
- `criteria_pack_version` (SemVer), when criteria evaluation is enabled
- `rule_set_id` (id_slug_v1), when Sigma or rule evaluation is enabled
- `rule_set_version` (SemVer or rule-set snapshot version), when Sigma or rule evaluation is enabled
- `mapping_pack_id` (id_slug_v1), when the Sigma-to-OCSF bridge is enabled
- `mapping_pack_version` (SemVer), when the Sigma-to-OCSF bridge is enabled

Recommended additional keys (non-normative, strongly encouraged):

- `runner_version` (string)
- `collector_version` (string)
- `normalizer_version` (string)
- `evaluator_version` (string)

#### Backward compatibility with `manifest.extensions` (transitional)

If older consumers expect version values in `manifest.extensions`, producers MAY duplicate version
pins into `manifest.extensions` for compatibility.

Precedence rule (normative):

1. Consumers MUST prefer `manifest.versions.*` when present.
1. Consumers MAY fall back to a documented legacy location under `manifest.extensions` when the
   corresponding `manifest.versions.*` key is absent.
1. If both are present and disagree, consumers MUST fail closed for runs intended for regression or
   CI comparison, and MUST surface a deterministic error that includes both values.

### Deterministic resolution when version pins are omitted

Pinned versions are the default expectation for deterministic runs.

#### Requirements

- For any run intended to be diffable, regression-tested, or trended, the effective versions for all
  enabled pack-like artifacts MUST be pinned and recorded in `manifest.versions`.
- If an input omits a `*_version` (non-recommended), the implementation MUST resolve it
  deterministically using the algorithm below and MUST record the resolved version in
  `manifest.versions`.

#### Resolution algorithm (SemVer-based, normative)

For a given `(artifact_kind, artifact_id)` where `artifact_kind` is one of: `criteria_pack`,
`rule_set`, `mapping_pack`, `mapping_profile`:

1. Enumerate candidate versions across the configured search paths, using the conventional layout:

   - `<root>/<artifact_kind>/<artifact_id>/<artifact_version>/`

1. Parse candidate directory names as SemVer.

1. Select the highest SemVer version.

1. If no candidates parse as SemVer, fail closed.

1. If the same `(artifact_id, artifact_version)` appears in multiple search paths, fail closed
   unless proven byte-identical by matching content hashes recorded at selection time.

Resolved-version recording (normative):

- The resolved `*_version` MUST be recorded in `manifest.versions`.
- The selected artifact content MUST be snapshotted into the run bundle (or otherwise made
  content-addressable) so the run remains reproducible if the repository changes.

### Content hashes and immutability discipline

#### Immutability rule (normative)

A released version directory for any pack-like artifact (a concrete `<id>/<version>/` directory)
MUST be treated as immutable.

- Editing content in-place for an already released version SHOULD NOT be done.
- Any semantic change MUST produce a new version.

#### Hash recording (normative)

For each selected pack-like artifact, the manifest MUST record a deterministic content hash for the
effective content used by the run.

Minimum required hash fields (normative):

- `*_content_sha256` (string, lowercase hex SHA-256)

Hash computation basis (normative):

- Implementations MUST compute `*_content_sha256` using a deterministic file-list basis:

  - Build an object containing:
    - `v` (string, fixed value identifying the hash basis version)
    - `artifact_kind` (string)
    - `artifact_id` (string)
    - `artifact_version` (string)
    - `files[]` (sorted array of `{ path, sha256 }`)
  - `path` MUST be normalized to `/` separators and MUST be relative to the artifact version root.
  - `files[]` MUST be sorted by `path` using bytewise UTF-8 lexical ordering.
  - The object MUST be serialized using the canonical JSON requirements defined in the data
    contracts specification.
  - The hash MUST be `sha256_hex(canonical_json_bytes(hash_basis))`.

Note:

- If the project already defines an equivalent deterministic tree hash primitive for upstream source
  trees, implementations SHOULD reuse that primitive, provided it meets the requirements above.

### Schema and contract pinning requirements

- When a run publishes contract-backed artifacts, the manifest SHOULD record the `contract_version`
  values for the contracts relevant to the run.
- When a run publishes Parquet datasets with required `_schema.json` snapshots, the manifest SHOULD
  record the dataset `schema_id` and `schema_version` values to support fast compatibility checks
  without scanning the filesystem.

If recorded in the manifest, the following shapes are RECOMMENDED:

- `versions.contracts` as an object keyed by contract name to `contract_version`
- `versions.datasets` as an object keyed by `schema_id` to `schema_version`

### Trending keys and join dimensions

Exporters and reporting tools MUST treat the following as stable join dimensions for trending and
regression comparisons. Reporting-level regression comparability checks MUST be computed using these
pins (and other `manifest.versions.*` keys as applicable) and MUST NOT depend on environment-derived
fields (for example, hostnames, absolute paths, timestamps).

- `versions.scenario_id`
- `versions.scenario_version` (SHOULD be present for trending)
- `versions.pipeline_version`
- `versions.rule_set_version` (when rule evaluation is enabled)
- `versions.mapping_pack_version` (when the Sigma-to-OCSF bridge is enabled)
- `versions.ocsf_version`
- `versions.criteria_pack_version` (when criteria evaluation is enabled)

Non-goal (normative):

- `run_id` is unique per execution and MUST NOT be used as a trending key.

### Verification and CI requirements

Implementations MUST provide deterministic validation for this ADR, suitable for CI.

Minimum conformance checks (normative):

1. **ID validation**

   - Every `*_id` recorded in `manifest.versions` MUST conform to `id_slug_v1`.

1. **Version validation**

   - Every `*_version` recorded in `manifest.versions` that claims SemVer MUST parse as SemVer.
   - If a version is unparseable, the run MUST fail closed for regression or CI modes.

1. **Run ID validation**

   - `run_id` MUST validate as an RFC 4122 UUID in canonical hyphenated form.
   - Runs that violate this MUST fail contract validation and MUST be rejected by CI fixtures.

1. **Resolution determinism**

   - If any `*_version` is omitted in inputs, the resolved version MUST be recorded in
     `manifest.versions`.
   - If duplicate `(id, version)` candidates exist across search paths, the run MUST fail closed
     unless the content hash matches.

1. **Snapshot reproducibility**

   - For each selected pack-like artifact, the run bundle MUST contain enough material to reproduce
     the selection (snapshot or content-addressable reference), and the recorded hash MUST match the
     snapshotted content.

## Consequences

- Improves reproducibility, diffability, and trending stability across runs.
- Requires explicit pins and hash recording discipline in the manifest.
- Introduces deterministic failure modes for ambiguous or unpinned inputs, which may require
  operator action to resolve (pin versions, remove duplicates, or fix layout).

## Follow-ups

- Update any examples that use non-UUID `run_id` strings to conform to the UUID requirement.
- Ensure all specs that reference legacy `manifest.extensions.*` version locations either:
  - migrate to `manifest.versions.*`, or
  - explicitly describe transitional behavior consistent with this ADR.

## References

- [Data contracts specification](../spec/025_data_contracts.md)
- [Scenarios specification](../spec/030_scenarios.md)
- [Validation criteria packs specification](../spec/035_validation_criteria.md)
- [Storage formats specification](../spec/045_storage_formats.md)
- [Reporting specification](../spec/080_reporting.md)
- [Configuration reference](../spec/120_config_reference.md)
- [ADR-0002 "Event identity and provenance"](ADR-0002-event-identity-and-provenance.md)

## Changelog

| Date       | Change                                                    |
| ---------- | --------------------------------------------------------- |
| 2026-01-12 | Formatting update                                         |
| 2026-01-13 | Expand ADR into a complete naming and versioning contract |
| 2026-01-18 | update |