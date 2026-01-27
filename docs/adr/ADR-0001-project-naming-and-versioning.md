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

Purple Axiom uses distinct version domains. A version string MUST be interpreted only within its own
domain; identical version strings across domains MUST NOT be assumed to imply equivalence,
compatibility, or coupling unless this ADR (or the owning spec) explicitly defines such a linkage.

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
   - Threat intelligence packs: `threat_intel_pack_id` / `threat_intel_pack_version`
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

- `^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$` plus an additional check that `--` is not present.

Rationale:

- Safe for filesystem paths, JSON keys, and URLs.
- Avoids case-normalization ambiguity across operating systems and tools.

#### Version strings (`*_version`)

This ADR defines version-string requirements for *pinned version fields* that participate in run
comparability (for example: `manifest.versions.*` and pack-like artifact version pins).

This section does **not** constrain JSON Schema `contract_version` constants; contract identifiers
are defined and validated by their owning JSON Schema contracts.

Allowed pinned version formats:

- `semver_v1` — SemVer 2.0.0 string
- `version_token_v1` — opaque pinned token string (byte-for-byte comparable)

##### `semver_v1` (normative)

A `semver_v1` value:

- MUST be parseable as SemVer 2.0.0 (`MAJOR.MINOR.PATCH` with optional pre-release and build).
- MUST NOT include a leading `v` (for example, `1.2.3`, not `v1.2.3`).
- MUST be recorded exactly as the SemVer string (no additional prefixes or formatting).

The following pinned fields MUST be `semver_v1`:

- `project_version`
- `pipeline_version`
- `scenario_version`
- `criteria_pack_version` (when criteria evaluation is enabled)
- `mapping_pack_version` (when the Sigma-to-OCSF bridge is enabled)
- `mapping_profile_version` (when normalization mapping profiles are in use)

##### `version_token_v1` (normative)

A `version_token_v1` value:

- MUST be an ASCII string of length 1–128 characters.
- MUST NOT contain whitespace.
- MUST NOT contain `/` or `\` and MUST NOT contain control characters.
- MUST be treated as opaque: consumers MUST compare tokens using byte-for-byte equality with no
  normalization.
- MUST be recorded exactly as used for the run.

The following pinned fields MAY be `version_token_v1`:

- `ocsf_version` (when upstream OCSF does not publish SemVer, or when the implementation uses a
  pinned non-SemVer schema identifier)
- `rule_set_version` (when the implementation pins rule sets by snapshot id rather than SemVer)

Component/tool version keys (for example `runner_version`, `collector_version`) SHOULD be
`semver_v1` where practical, but MAY be `version_token_v1`.

Regex (informative):

- `^[A-Za-z0-9][A-Za-z0-9._:+-]{0,127}$`

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

- `project_version` (`semver_v1`; version of the Purple Axiom release)
- `pipeline_version` (`semver_v1`; version of the pipeline definition used to interpret configs and
  produce artifacts)
- `scenario_id` (id_slug_v1; stable scenario identifier)
- `scenario_version` (`semver_v1`; pinned scenario version)
- `ocsf_version` (`semver_v1` or `version_token_v1`; the implementation MUST record the exact pinned
  value)
- `rule_set_id` (id_slug_v1; stable rule set identifier)
- `rule_set_version` (`semver_v1` or `version_token_v1`; pinned rule set identifier for
  comparability)
- `contracts_version` (`semver_v1`; version of the JSON schema contract set used for validation)
- `schema_registry_version` (`semver_v1`; version of any external schema registry snapshot used, if
  applicable)
- `mapping_pack_id` (id_slug_v1), when the Sigma-to-OCSF bridge is enabled
- `mapping_pack_version` (SemVer), when the Sigma-to-OCSF bridge is enabled

Recommended additional keys (non-normative, strongly encouraged):

- `runner_version` (string)
- `collector_version` (string)
- `normalizer_version` (string)
- `evaluator_version` (string)
- `contracts_bundle_sha256`: deterministic content hash of the distributed contracts bundle
  corresponding to `contracts_version` (see `025_data_contracts.md`)

#### Backward compatibility with `manifest.extensions` (transitional)

If older consumers expect version values in `manifest.extensions`, producers MAY duplicate version
pins into `manifest.extensions` for compatibility.

Precedence rule (normative):

1. Consumers MUST prefer `manifest.versions.*` when present.
1. Consumers MAY fall back to a documented legacy location under `manifest.extensions` when the
   corresponding `manifest.versions.*` key is absent.
1. If both are present and disagree, consumers MUST fail closed for runs intended for regression or
   CI comparison, and MUST surface a deterministic error that includes both values.

#### Consistency with other manifest fields and snapshot artifacts (normative)

`manifest.versions` is the canonical source of pinned identifiers and versions used for regression
comparability and trending joins.

When other manifest sections or snapshot artifacts also carry copies of these values, producers and
consumers MUST enforce byte-for-byte equality (when both values are present):

- `manifest.versions.scenario_id` MUST equal `manifest.scenario.scenario_id`.
- `manifest.versions.scenario_version` MUST equal `manifest.scenario.scenario_version`, when
  `manifest.scenario.scenario_version` is present.
- `manifest.versions.ocsf_version` MUST equal `manifest.normalization.ocsf_version`, when
  `manifest.normalization.ocsf_version` is present.
- When `normalized/mapping_profile_snapshot.json` is present, its `ocsf_version` MUST equal
  `manifest.versions.ocsf_version`.
- When `bridge/mapping_pack_snapshot.json` is present, its `ocsf_version` MUST equal
  `manifest.versions.ocsf_version`.

If any required equality check fails, CI/regression mode implementations MUST fail closed. In
non-regression runs, implementations MAY continue only if configured to do so, but MUST record the
mismatch as a deterministic stage outcome (see ADR-0005).

#### Mapping from configuration inputs to `manifest.versions` pins (normative)

When the corresponding feature is enabled, orchestrators MUST project configuration-level selectors
into `manifest.versions` pins as follows (effective/resolved values):

- Criteria packs:
  - `validation.criteria_pack.pack_id` -> `manifest.versions.criteria_pack_id`
  - `validation.criteria_pack.pack_version` -> `manifest.versions.criteria_pack_version`
- Sigma rule evaluation:
  - `detection.sigma.rule_set_version` -> `manifest.versions.rule_set_version`
  - Because v0.1 configuration does not carry an explicit `rule_set_id`, implementations MUST set
    `manifest.versions.rule_set_id` deterministically when Sigma evaluation is enabled. Default:
    `rule_set_id = "sigma"` unless configured otherwise.
- Sigma-to-OCSF bridge:
  - `detection.sigma.bridge.mapping_pack` -> `manifest.versions.mapping_pack_id`
  - `detection.sigma.bridge.mapping_pack_version` -> `manifest.versions.mapping_pack_version`

### Deterministic resolution when version pins are omitted

Pinned versions are the default expectation for deterministic runs.

#### Requirements

- For any run intended to be diffable, regression-tested, or trended, the effective versions for all
  enabled pack-like artifacts MUST be pinned and recorded in `manifest.versions`.
- If an input omits a `*_version` (non-recommended), the implementation MUST resolve it
  deterministically using the algorithm below and MUST record the resolved version in
  `manifest.versions`.

#### Resolution algorithm (SemVer-based, normative):

Omission rules (normative):

- Omission is permitted only for pins whose version format is `semver_v1`.
- Pins that use `version_token_v1` MUST NOT be omitted; omission MUST fail closed.

Algorithm:

1. For the target artifact kind, enumerate candidate version directories across the configured
   search paths. The directory layout is artifact-kind-specific and defined by the owning
   spec/configuration. At minimum, each search path root MUST contain
   `<artifact_id>/<artifact_version>/` directories.
1. Parse each candidate `artifact_version` directory name as `semver_v1`. Ignore candidates that do
   not parse.
1. Select the highest SemVer version by SemVer precedence.
1. If no candidates parse as SemVer, fail closed.
1. If the same `(artifact_id, artifact_version)` is present in multiple search paths, fail closed
   unless the candidates are proven byte-identical by comparing the canonical content fingerprint
   for that artifact (see "Content hashes and immutability discipline"). If identical, select the
   first match in the configured search path order.
1. Record the resolved `artifact_version` into the appropriate pin field in `manifest.versions`.

### Content hashes and immutability discipline

#### Immutability rule (normative)

A released version directory for any pack-like artifact (a concrete `<id>/<version>/` directory)
MUST be treated as immutable.

- Editing content in-place for an already released version SHOULD NOT be done.
- Any semantic change MUST produce a new version.

#### Hash recording (normative)

For each selected pack-like artifact, the run bundle MUST contain a deterministic SHA-256 content
fingerprint for the effective content used by the run.

Minimum required canonical fingerprints (v0.1; normative when the corresponding feature is enabled):

- Criteria packs: `criteria/manifest.json` MUST include `criteria.pack_sha256`.
- Sigma-to-OCSF mapping packs: `bridge/mapping_pack_snapshot.json` MUST include
  `mapping_pack_sha256`.
- Normalization mapping profiles: `normalized/mapping_profile_snapshot.json` MUST include
  `mapping_profile_sha256`.

Producers MAY also mirror these canonical fingerprints into `manifest.versions` (for example as
`criteria_pack_content_sha256`, `mapping_pack_content_sha256`, `mapping_profile_content_sha256`) to
simplify operator inspection, but consumers MUST treat the snapshotted artifact metadata as the
source of truth.

For any artifact kind that lacks a spec-defined canonical fingerprint, implementations MUST compute
a deterministic SHA-256 fingerprint using the `hash_basis_v1` algorithm below and MUST record it in
a deterministic, contract-backed location for that artifact kind.

Hash computation basis for `hash_basis_v1` (normative):

- Implementations MUST compute the fingerprint using a deterministic file-list basis:

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

The project distinguishes between:

- **Diffable runs**: run bundles intended for CI, regression comparison, trending, or inclusion in a
  golden dataset / archival catalog.
- **Non-diffable runs**: ad-hoc/operator/debug runs not intended for long-term comparability.

For diffable runs (normative):

- When a run publishes contract-backed artifacts, the manifest MUST record the `contract_version`
  values for the contracts relevant to the run.
- When a run publishes Parquet datasets with required `_schema.json` snapshots, the manifest MUST
  record the dataset `schema_id` and `schema_version` values to support fast compatibility checks
  without scanning the filesystem.

For non-diffable runs (guidance):

- Producers SHOULD record the same information when feasible.

Manifest shapes (normative when the corresponding map is present):

- `versions.contracts` MUST be an object keyed by contract name to `contract_version`.
- `versions.datasets` MUST be an object keyed by `schema_id` to `schema_version`.

### Historical run bundle compatibility promise

Archived run bundles accumulate over time (CI fixtures, regression baselines, golden dataset
inputs). Downstream consumers (UI, reporting, dataset builder, regression runners) need a shared,
explicit contract to avoid re-implementing ad hoc migration logic.

Definitions:

- **Compatibility major**: the SemVer component that represents a breaking compatibility boundary.
  - For `MAJOR >= 1`: compatibility major = `MAJOR`.
  - For `MAJOR == 0`: compatibility major = `0.MINOR` (treat MINOR bumps as breaking).
- **Supported window**: `{current, previous}` compatibility majors for a given version pin, where
  `previous` refers to the immediately preceding compatibility major.
- **Out-of-window bundle**: a run bundle whose pinned versions fall outside the supported window for
  the consuming toolchain release.

Support window (normative):

- For a given consumer release, "current" for each pin is the value that the consumer would emit
  into `manifest.versions.*` when producing a new run bundle.
- A consumer release MUST be able to parse and contract-validate diffable run bundles whose:
  - `manifest.versions.pipeline_version` compatibility major is within the supported window, and
  - `manifest.versions.contracts_version` compatibility major is within the supported window, and
  - for each entry in `manifest.versions.datasets` (when present), the dataset `schema_version`
    compatibility major is within the supported window for that `schema_id`.

Behavior on mismatch (normative):

- In CI/regression contexts, consumers MUST fail closed when opening an out-of-window bundle.
- Outside CI/regression contexts, consumers MAY attempt a best-effort read of an out-of-window
  bundle, but MUST:
  - treat the bundle as **non-comparable** (MUST NOT compute regression deltas or include it in
    trending aggregates),
  - surface the incompatibility to the operator (for example, CLI stderr or a UI banner), and
  - if a machine-readable aggregate output is produced, mark the corresponding bundle contribution
    as non-comparable.

Upgrade strategy (policy decision; details deferred):

- The project adopts **write current, provide upgrader**:
  - Producers MUST write new run bundles using the current contracts and dataset schemas for their
    release.
  - A deterministic "bundle upgrade" utility MUST exist before any release that would otherwise drop
    support for an earlier compatibility major.
  - The upgrader MUST NOT mutate the input bundle in place.
  - When implemented, the upgrader MUST be deterministic (byte-identical outputs for identical
    inputs) and MUST record provenance linking the upgraded bundle to the source bundle.

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

### Lifecycle and state machine integration (normative)

Version pin validation, SemVer resolution (when permitted), and pack snapshotting are
input-preparation work that MUST complete before any stage that consumes those artifacts publishes
outputs.

Implementations that emit stage outcomes SHOULD record this work as the dedicated runner substage
`runner.environment_config` so that failures are visible and triageable via
`(stage, status, fail_mode, reason_code)` per ADR-0005.

In CI/regression mode, any version-pin validation/resolution failure MUST fail closed and MUST be
recorded deterministically as a stage outcome (see ADR-0005 for reason code constraints).

### Verification and CI requirements

Implementations MUST provide deterministic validation for this ADR, suitable for CI.

Minimum conformance checks (normative):

1. ID validation:
   - Every `*_id` recorded in `manifest.versions` MUST conform to `id_slug_v1`.
1. Version validation:
   - The following pins MUST be present and parseable as `semver_v1`:
     - `manifest.versions.project_version`
     - `manifest.versions.pipeline_version`
     - `manifest.versions.scenario_version`
     - `manifest.versions.contracts_version`
   - When enabled, the following pins MUST be present and parseable as `semver_v1`:
     - `manifest.versions.criteria_pack_version`
     - `manifest.versions.mapping_pack_version`
   - `manifest.versions.ocsf_version` MUST be present and MUST validate as either `semver_v1` or
     `version_token_v1` (byte-for-byte comparable).
   - `manifest.versions.rule_set_version` MUST be present when rule evaluation is enabled and MUST
     validate as either `semver_v1` or `version_token_v1` (byte-for-byte comparable).
   - `threat_intel_pack_version` (when `threat_intel.enabled=true`)
1. Run ID validation:
   - `run_id` MUST validate as an RFC 4122 UUID in canonical hyphenated form.
   - Runs that violate this MUST fail contract validation and MUST be rejected by CI fixtures.
1. Resolution determinism:
   - If any `*_version` is omitted in inputs, the resolved version MUST be recorded in
     `manifest.versions`.
   - If duplicate `(id, version)` candidates exist across search paths, the run MUST fail closed
     unless the content hash matches.
1. Cross-location consistency:
   - When both are present, `manifest.versions.scenario_id` MUST equal
     `manifest.scenario.scenario_id`.
   - When both are present, `manifest.versions.scenario_version` MUST equal
     `manifest.scenario.scenario_version`.
   - When present, `normalized/mapping_profile_snapshot.json.ocsf_version` MUST equal
     `manifest.versions.ocsf_version`.
   - When present, `bridge/mapping_pack_snapshot.json.ocsf_version` MUST equal
     `manifest.versions.ocsf_version`.
1. Snapshot reproducibility:
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
| 2026-01-18 | update                                                    |
