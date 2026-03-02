---
title: Detection baseline library
description: Lightweight, durable baseline datasets derived from completed runs for detection regression and offline evaluation.
status: draft
category: spec
tags: [detection, baselines, storage, operator-interface]
related:
  - 045_storage_formats.md
  - 060_detection_sigma.md
  - 080_reporting.md
  - 090_security_safety.md
  - 115_operator_interface.md
  - 025_data_contracts.md
  - ADR-0001-project-naming-and-versioning.md
  - ADR-0003-redaction-policy.md
  - ADR-0009-run-export-policy-and-log-classification.md
---

# Detection baseline library

## Overview

A **Baseline Detection Package (BDP)** is a redaction-safe, lightweight subset of a *single*
completed run bundle that is intended to be retained long-term and reused to evaluate detection
content (for example, Sigma rules) against a known-good dataset.

BDPs exist to support:

- Detection regression testing (local and CI)
- Iterative detection development (repeatable offline evaluation)
- Durable retention of "known good" datasets without retaining full evidence-tier run artifacts

BDPs are stored outside of `runs/` under the workspace `exports/` tree.

- In v0.2+, BDPs are managed via the Operator Interface (UI + API).
- In v0.1, BDPs MAY be consumed as pinned CI artifacts without an operator-facing baseline catalog.

version scope: v0.1 (CI consumption subset) + post-OI (v0.2+)

## Non-goals

- Defining a new detection "replay run" execution model beyond the minimal CI replay harness
  requirements in this spec. (BDPs are inputs; how they are consumed by a general detection
  evaluation pipeline is reserved.)
- Providing a general-purpose archival format for complete run bundles (see run export policy /
  dataset releases).
- Defining a remote artifact store or synchronization protocol.

## CI usage (v0.1 subset)

Although the general "replay run" execution model is reserved, v0.1 CI relies on BDPs as a promoted,
versioned dataset artifact for deterministic detection evaluation without spinning up a lab
provider.

Run CI requirements (normative; v0.1):

- Run CI MUST be able to consume a pinned BDP identified by `(baseline_id, baseline_version)`.
- CI consumers MUST validate:
  - the BDP manifest (`baseline_package_manifest.json`) against the contract, and
  - integrity material (`security/checksums.txt`; signature when present) before using BDP contents
    for evaluation.
- Run CI MUST run detection evaluation deterministically over pinned fixture datasets (including at
  least one pinned BDP) and MUST enforce fixture-scoped expectations, failing closed on any
  mismatch:
  - `run.goodlog`: evaluate all enabled detections against fixtures declared `purpose=benign` and
    require zero non-allowlisted matches.
  - `run.regression`: evaluate detections against fixtures declared `purpose=malicious|mixed` and
    assert each fixture's declared `expected_outcomes[]`.
- Run CI MAY additionally compare full output artifacts to golden hashes/diffs, but this is OPTIONAL
  when fixture `expected_outcomes[]` coverage is sufficient.

Pinning requirement (verification hook):

- The repository MUST designate at least one pinned "CI baseline" `(baseline_id, baseline_version)`
  pair to be used by Run CI.
  - This pinning is a CI harness configuration input (for example for `ci-run`); it is not an
    orchestrator run configuration key.

## Fixture registry and allowlisting (v0.1 CI)

In addition to pinning at least one BDP for CI, v0.1 CI commonly needs a curated set of fixture
datasets for:

- **Good-log** validation (benign data; any match is suspicious).
- **Regression** validation (malicious or mixed data; expected matches are asserted).

To avoid ad hoc fixture selection and to prevent YAML seam drift across implementations, the project
defines a fixture registry authoring file and a deterministic canonical JSON materialization.

### Fixture registry authoring input (YAML)

- Path (repo-local): `fixtures/fixture_registry.v1.yaml`
- The YAML file is an authoring convenience only. It MUST NOT be treated as canonical.
- Tooling MUST parse this YAML deterministically:
  - Exactly one YAML document.
  - YAML 1.2 "JSON schema" data model.
  - Duplicate keys are forbidden (fail closed).
  - Anchors, aliases, and merge keys are forbidden (fail closed).

### Fixture registry canonical materialization (JSON)

- Path (workspace-root): `artifacts/fixtures/fixture_registry.v1.json`
- Contract: `fixture_registry` (workspace contract registry binding).
- Producers MUST emit canonical JSON bytes (RFC 8785 / JCS) with UTF-8 encoding and no BOM.

Deterministic ordering (normative):

- `fixtures[]` MUST be sorted ascending by:
  1. `fixture_id`
  1. `fixture_version`
- Within each fixture:
  - `formats[]` MUST be sorted ascending (UTF-8 byte order, no locale).
  - `paths[]` MUST be sorted ascending (UTF-8 byte order, no locale) when present.
  - `expected_outcomes[]` MUST be sorted ascending by `detection_id`.
  - `expected_outcomes[].assertions[]` MUST be sorted ascending by:
    1. `kind`
    1. `field` (missing sorts as empty string)
    1. `value` (missing sorts as `0`)
    1. `min` (missing sorts as `0`)
    1. `max` (missing sorts as `0`)
- Duplicate entries at any array level MUST be removed after sorting (keep the first entry after
  sort).

### Expected outcomes model (used by `run.regression`)

Each fixture MUST declare `expected_outcomes[]` entries used by `run.regression`.

- `detection_id` MUST equal the stable detection identifier.
  - For Sigma-based detections, `detection_id` MUST equal the Sigma `id` / Purple Axiom `rule_id`.

Assertions (closed set):

- `match_count_exact`: assert an exact integer match count for the detection over the fixture.
- `match_count_range`: assert an inclusive `[min,max]` match count range.
- `field_present`: assert at least one match where the named field exists in the emitted detection
  instance (useful when counts vary).
- `no_matches`: assert zero matches for the detection over the fixture.

### Negative baseline allowlist authoring input (YAML)

- Path (repo-local): `fixtures/baseline_allowlist.v1.yaml`
- The YAML file is an authoring convenience only. It MUST NOT be treated as canonical.
- Tooling MUST apply the same deterministic YAML constraints as the fixture registry YAML.

### Negative baseline allowlist canonical materialization (JSON)

- Path (workspace-root): `artifacts/fixtures/baseline_allowlist.v1.json`
- Contract: `baseline_allowlist` (workspace contract registry binding).
- Producers MUST emit canonical JSON bytes (RFC 8785 / JCS) with UTF-8 encoding and no BOM.

Allowlist matching key (normative):

- Each allowlist entry MUST be scoped to a fixture via `fixture_id`.
- Each allowlist entry MUST be scoped to a detection via `detection_id`.
- Each allowlist entry MUST identify a specific match instance via `match_fingerprint` (SHA-256
  hex).

`match_fingerprint` MUST be computed over the canonical projection:

```json
{
  "rule_id": "<rule_id>",
  "first_seen_utc": "<first_seen_utc>",
  "last_seen_utc": "<last_seen_utc>",
  "matched_event_ids": ["<event_id>", "..."]
}
```

Where the projection values are sourced from `detections/detections.jsonl` detection instances and
`matched_event_ids[]` is treated as already deterministically ordered by the detection stage.

## Relationship to reporting regression baselines

Reporting "regression baseline" inputs are baseline *runs*, not baseline packages. When regression
is enabled, the run bundle `inputs/` area is populated with baseline-run references/snapshots (see
`025_data_contracts.md` and `080_reporting.md`), including:

- `runs/<run_id>/inputs/baseline_run_ref.json`
- `runs/<run_id>/inputs/baseline/manifest.json`

BDPs are stored under `exports/baselines/` and MUST NOT overload the reserved
`runs/<run_id>/inputs/baseline/**` paths above.

Rules (normative):

- `runs/<run_id>/inputs/baseline_packages/**` is reserved for baseline package manifest snapshots
  and MUST NOT be used for other input types.
- The snapshot file MUST be byte-for-byte identical to the source BDP’s
  `baseline_package_manifest.json`.
- The `<baseline_id>` and `<baseline_version>` path segments MUST match the `baseline_id` and
  `baseline_version` fields inside the snapped manifest. If they do not match, consumers MUST treat
  the run inputs as invalid for reproducibility purposes.
- When present, the snapped `baseline_package_manifest.json` SHOULD be contract-validated at the run
  publish gate under the same posture as other `runs/<run_id>/inputs/**` contract-backed artifacts.

### Interaction with `replay` (normalized-input fast path)

BDPs are intended to support rapid, repeatable detection evaluation without re-running telemetry
collection or normalization.

When an evaluation workflow stages a BDP's normalized artifacts into a candidate run bundle and
invokes the orchestrator `replay` verb, the orchestrator MUST short-circuit to detection when a
compatible normalized event store is already present.

Requirements (v0.2+; normative when used):

- If `normalized/ocsf_events/` (Parquet dataset; MUST include `normalized/ocsf_events/_schema.json`)
  and `normalized/mapping_profile_snapshot.json` exist in the candidate run bundle, and the snapshot
  is compatible with the run's effective version control for normalization (at minimum:
  `ocsf_version` and `mapping_profile_sha256` match), `replay` MUST begin at `detection` (skipping
  `normalization` and `validation`).
  - Note: Legacy v0.1 bundles that only include `normalized/ocsf_events.jsonl` do not qualify for
    this fast path.
- If compatibility cannot be established (for example, `normalized/mapping_profile_snapshot.json` is
  missing), the orchestrator MUST NOT assume the normalized store is current. It MUST either:
  - execute `normalization` from `raw_parquet/**` (if present), or
  - fail closed with deterministic `reason_code="normalized_store_incompatible"` (see
    `ADR-0005-stage-outcomes-and-failure-classification.md`).

Observability (normative):

- The run manifest stage outcomes MUST record `normalization` and `validation` as `status="skipped"`
  with `reason_code="normalized_store_reused"` when the fast path is taken (see
  `ADR-0005-stage-outcomes-and-failure-classification.md`).

## Terminology

- **Run bundle**: The canonical per-run directory at `<workspace_root>/runs/<run_id>/` containing
  artifacts produced by the orchestrator.
- **BDP**: Baseline Detection Package. A directory-based package derived from one run bundle.
- **Baseline library**: The set of BDPs stored under `<workspace_root>/exports/baselines/`.
- **BDP profile**: A named selection of run artifacts included in a BDP (this spec defines
  `detection_eval_v1`).

## Storage location and addressing

### Workspace location

BDPs MUST be stored under the reserved exports root:

`<workspace_root>/exports/baselines/<baseline_id>/<baseline_version>/`

BDPs MUST NOT be stored under `runs/` because they are not run bundles.

### Identifiers

- `baseline_id` MUST be `id_slug_v1` (see ADR-0001).
- `baseline_version` MUST be `semver_v1` (SemVer 2.0.0).
- The tuple `(baseline_id, baseline_version)` MUST uniquely identify a BDP within a workspace.
- Implementations MAY also assign an internal `baseline_package_uuid` (UUIDv4) for UI convenience.

### Immutability and versioning

- A BDP’s **content selection** and **source run** are immutable once created.
- If the included content changes (different source run, different included artifacts, regenerated
  artifacts), a new `baseline_version` MUST be created.
- Mutable metadata (for example, `description`, `tags`) MAY be edited in place, but such edits MUST
  update integrity metadata (checksums and, if present, signature).

## Baseline Detection Package format

### Directory layout (profile `detection_eval_v1`)

A BDP directory MUST have the following structure:

```text
<baseline_root>/
  baseline_package_manifest.json
  security/
    checksums.txt
    signature.ed25519    # optional
    public_key.ed25519   # optional
  run/
    manifest.json
    ground_truth.jsonl
    normalized/
      ocsf_events/                    # OR: ocsf_events.jsonl (see representation rules)
        _schema.json                  # required when ocsf_events/ is present
      mapping_coverage.json           # optional
      mapping_profile_snapshot.json   # optional
    logs/
      telemetry_validation.json       # optional
    inputs/
      telemetry_baseline_profile.json # optional
    security/
      redaction_policy_snapshot.json  # optional
```

Where `<baseline_root>` is `<workspace_root>/exports/baselines/<baseline_id>/<baseline_version>/`.

Within a BDP, `run/` is an in-package mirror of the source run bundle root. Consumers that interpret
`run/manifest.json` MUST resolve run-relative paths (for example `normalized/**`) relative to the
`run/` directory (not the BDP root).

### Required artifacts

A BDP MUST include:

1. `baseline_package_manifest.json` (contract-backed; see below)
1. `run/manifest.json` (copied from the source run bundle)
1. `run/ground_truth.jsonl` (copied from the source run bundle)
1. Exactly one normalized events representation:
   - `run/normalized/ocsf_events/` (Parquet dataset directory; MUST include
     `run/normalized/ocsf_events/_schema.json`), OR
   - `run/normalized/ocsf_events.jsonl` (JSONL)

### Representation rules for normalized events

For profile `detection_eval_v1`:

- If the source run contains `normalized/ocsf_events/`, the BDP MUST include
  `run/normalized/ocsf_events/`.
  - The BDP MUST include `run/normalized/ocsf_events/_schema.json` copied byte-for-byte from the
    source run’s `normalized/ocsf_events/_schema.json`. If `_schema.json` is missing, BDP creation
    MUST fail.
- Else, if the source run contains `normalized/ocsf_events.jsonl`, the BDP MUST include
  `run/normalized/ocsf_events.jsonl`.
- If both representations exist in the source run, BDP creation MUST fail with an
  `artifact_representation_conflict`-class error.
- Implementations MUST NOT silently regenerate or transcode normalized events during BDP creation in
  `detection_eval_v1`. (A future profile may allow a deterministic transcode step.)

### Optional artifacts

If present in the source run bundle, the BDP SHOULD copy the following artifacts (they are typically
small and useful for debugging):

- `normalized/mapping_coverage.json` -> `run/normalized/mapping_coverage.json`
- `normalized/mapping_profile_snapshot.json` -> `run/normalized/mapping_profile_snapshot.json`
  - Strongly RECOMMENDED for `replay` fast-path compatibility checks.
  - The BDP builder MUST compute `replay_fast_path_eligible` in the BDP manifest as:
    - `true` iff `run/normalized/mapping_profile_snapshot.json` is present, is not a placeholder,
      and validates against the `mapping_profile_snapshot` contract.
    - otherwise `false`.
- `logs/telemetry_validation.json` -> `run/logs/telemetry_validation.json`
- `inputs/telemetry_baseline_profile.json` -> `run/inputs/telemetry_baseline_profile.json`
- `security/redaction_policy_snapshot.json` -> `run/security/redaction_policy_snapshot.json`

### Forbidden content (redaction-safe by default)

A BDP MUST NOT include evidence-tier or otherwise sensitive artifacts, including but not limited to:

- `run/raw/**`
- `run/raw_parquet/**`
- `run/runner/**`
- `run/unredacted/**`

Additionally, BDP creation MUST fail if any **required** artifact (`run/manifest.json`,
`run/ground_truth.jsonl`, or the chosen normalized events representation) is:

- missing, or
- present only as a redaction/export placeholder (that is, not the real underlying artifact).

For the purposes of this rule, a "placeholder" is any deterministic placeholder artifact written in
place of withheld/quarantined content per `090_security_safety.md` ("Placeholder artifacts").
Implementations SHOULD reuse the placeholder detection behavior described in `025_data_contracts.md`
("Evidence ref resolution and redaction handling") rather than implementing ad-hoc heuristics.

### File formats

Within a BDP:

- Artifacts copied from the source run bundle (everything under `run/`) MUST be copied
  byte-for-byte. Implementations MUST NOT reformat, reserialize, or normalize line endings for
  copied artifacts.
- `baseline_package_manifest.json` MUST be written as `canonical_json_bytes(obj)` (RFC 8785 JCS;
  UTF-8; no BOM; no trailing newline).
- JSONL artifacts MUST be UTF-8 line-delimited JSON objects (existing run-bundle JSONL artifacts are
  expected to already conform; they MUST still be copied byte-for-byte).
- Parquet datasets MUST follow the Parquet conventions used in run bundles (for example,
  `run/normalized/ocsf_events/` as a directory containing `.parquet` files and a required
  `run/normalized/ocsf_events/_schema.json` schema snapshot).

## Baseline package manifest contract

### Contract and location

- File path: `baseline_package_manifest.json`
- Contract ID: `baseline_detection_package_manifest`
- Contract version: `0.2.0`
- Format: JSON

### Required fields (normative summary)

The manifest MUST include, at minimum:

- `contract_version` (MUST be `0.2.0`)
- `schema_version` (MUST be `pa:baseline_detection_package_manifest:v1`)
- `baseline_id`, `baseline_version`
- `created_at` (UTC RFC3339 with `Z`)
- `profile` (MUST be `detection_eval_v1`)
- `replay_fast_path_eligible` (boolean; computed at BDP creation time; see below)
- `source_run` object:
  - `run_id` (UUID)
  - `run_manifest_sha256` (MUST be `sha256:<lowercase_hex>`; digest of the exact `run/manifest.json`
    bytes)
- `artifact_refs` object describing the normalized events representation and paths:
  - `ground_truth_path` (MUST be `run/ground_truth.jsonl`)
  - `ocsf_events_representation` (`parquet_dataset` or `jsonl`)
  - `ocsf_events_path` (MUST be `run/normalized/ocsf_events/` or `run/normalized/ocsf_events.jsonl`)
- `integrity` object:
  - `checksums_path` (MUST be `security/checksums.txt`)
  - `package_tree_sha256` (digest of the package file tree basis; see below)

`replay_fast_path_eligible` semantics (normative):

- The value MUST be:
  - `true` iff `run/normalized/mapping_profile_snapshot.json` is present in the package, is not a
    placeholder artifact, and validates against the `mapping_profile_snapshot` contract.
  - otherwise `false`.

This field is a first-class manifest signal for whether a BDP contains sufficient normalization
provenance to be considered for the orchestrator `replay` normalized-input fast path (subject to the
orchestrator's compatibility checks on `ocsf_version` and `mapping_profile_sha256`).

The manifest MAY include user-facing metadata such as `description`, `tags`, and `blessing`.

If `summary` is present, it MUST be internally consistent with the package contents:

- `summary.ground_truth_row_count` (if present) MUST equal the number of lines in
  `run/ground_truth.jsonl`.
- `summary.ocsf_event_count` (if present) MUST equal the number of normalized event rows:
  - For `ocsf_events_representation=jsonl`: number of lines in `run/normalized/ocsf_events.jsonl`.
  - For `ocsf_events_representation=parquet_dataset`: sum of row counts across all `.parquet` files
    recursively under `run/normalized/ocsf_events/` (including nested partition directories).
- `summary.technique_ids` (if present) MUST be de-duplicated and sorted ascending by technique id
  (UTF-8 byte order, no locale).

### Example manifest

```json
{
  "contract_version": "0.2.0",
  "schema_version": "pa:baseline_detection_package_manifest:v1",
  "baseline_id": "win-proc-create-t1059",
  "baseline_version": "1.0.0",
  "baseline_package_uuid": "2d6a9a7a-6ce5-4cb5-b2c8-4c2fb4f0793a",
  "created_at": "2026-01-28T00:00:00Z",
  "profile": "detection_eval_v1",
  "replay_fast_path_eligible": true,
  "description": "Known-good Windows process telemetry covering T1059.",
  "tags": ["windows", "process", "t1059"],
  "source_run": {
    "run_id": "0f2b7f0d-8f5e-4a7f-9dd2-5c5d1a3c9a12",
    "run_manifest_sha256": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  },
  "artifact_refs": {
    "ground_truth_path": "run/ground_truth.jsonl",
    "ocsf_events_representation": "parquet_dataset",
    "ocsf_events_path": "run/normalized/ocsf_events/"
  },
  "summary": {
    "technique_ids": ["T1059"],
    "ocsf_event_count": 12456,
    "ground_truth_row_count": 6
  },
  "integrity": {
    "checksums_path": "security/checksums.txt",
    "package_tree_sha256": "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
  }
}
```

## Integrity and signing

BDPs reuse the standard checksums/signing rules used for shareable bundles (see
`025_data_contracts.md`):

- `security/checksums.txt` MUST exist and MUST enumerate file digests one per line using the
  format:\
  `sha256:<lowercase_hex><space><relative_path><LF>` (single space), sorted by `relative_path`
  ascending using UTF-8 byte order (no locale).
- `<relative_path>` MUST be BDP-root-relative (POSIX separators), MUST NOT start with `/`, and MUST
  NOT contain `..` path segments.
- The checksums enumerator MUST only process regular files. If a symlink (or platform-equivalent
  reparse point) or other non-regular file type (block/char device, FIFO, socket) is encountered
  anywhere under the BDP root, integrity computation MUST fail closed (RECOMMENDED error:
  `baseline_package_unsafe`).
- The checksums selection MUST include every file under the BDP root except:
  - `.staging/**` (if present)
  - `security/checksums.txt`
  - `security/signature.ed25519` (if present)
- If signing is enabled, the BDP MAY include:
  - `security/signature.ed25519`
  - `security/public_key.ed25519`\
    and MUST follow the same signature semantics as for run bundles (signature over the exact bytes
    of `security/checksums.txt`; files contain base64 + `\n`).

The manifest field `integrity.package_tree_sha256` MUST be computed as:

`"sha256:" + sha256_hex(canonical_json_bytes(tree_basis_v1))`

Where:

- `canonical_json_bytes(x)` is RFC 8785 JCS canonical JSON encoded as UTF-8 bytes (no BOM; no
  trailing newline).
- `sha256_hex(bytes)` is lowercase hex SHA-256 of the exact byte sequence.

`tree_basis_v1` is the canonical JSON object:

- `v`: `1`
- `engine`: `baseline_package`
- `files`: an array of
  `{ "path": "<relative_path>", "sha256": "<lowercase_hex>", "size_bytes": <int> }` for all files in
  the tree-basis selection.

Tree-basis selection (normative):

- The tree-basis selection MUST be derived from the checksums selection, but MUST additionally
  exclude `baseline_package_manifest.json` to avoid self-referential hashing cycles.

`files` MUST be sorted by `path` ascending using UTF-8 byte order (no locale).

## Library manager behavior

### State machine: baseline-package-lifecycle

#### Purpose

- **What it represents**: The on-disk lifecycle of a Baseline Detection Package (BDP) instance keyed
  by `(baseline_id, baseline_version)`, including crash-safe staging and atomic publish behavior.
- **Scope**: baseline package instance within a single workspace.
- **Machine ID**: `baseline-package-lifecycle` (id_slug_v1)
- **Version**: `1.0.0`

This state machine definition is **normative**: conforming implementations MUST derive lifecycle
state and MUST enforce lifecycle transitions exactly as specified in this section.

#### Lifecycle authority references

This state machine is an overlay on authoritative lifecycle semantics defined elsewhere. When
sources conflict, the referenced lifecycle authority is authoritative unless this section explicitly
overrides it:

- Baseline package addressing and identity:
  [Storage location and addressing](#storage-location-and-addressing) and
  [Identifiers](#identifiers)
- Package shape and schema: [Baseline Detection Package format](#baseline-detection-package-format)
  and [Baseline package manifest contract](#baseline-package-manifest-contract)
- Integrity policy: [Integrity and signing](#integrity-and-signing) and
  [Data contracts and reader semantics](025_data_contracts.md)
- Library manager behaviors: [Listing](#listing), [Creation](#creation),
  [Metadata updates](#metadata-updates), [Deletion](#deletion), and
  [Download / export](#download--export)
- CI/validation consumers: [CI usage (v0.1 subset)](#ci-usage-v01-subset),
  [Verification hooks](#verification-hooks), and [Test strategy CI](100_test_strategy_ci.md)

Note: This machine is intended to meet the ADR-0007 state machine contract bar (closed event set,
deterministic reconciliation, explicit illegal-transition policy, and fixture-driven conformance
tests).

#### Entities and identifiers

- **Machine instance key (correlation key)**: `(baseline_id, baseline_version)`.
  - `baseline_id` MUST be `id_slug_v1`; `baseline_version` MUST be `semver_v1` (SemVer 2.0.0). See
    [Identifiers](#identifiers).
  - The instance key is encoded in the published-root path segments and MUST exactly match the two
    fields in `baseline_package_manifest.json`.
- **Content identity** (immutability support):
  - `integrity.package_tree_sha256` is the stable content identity for the "tree basis" (excludes
    `baseline_package_manifest.json`) and is expected to remain stable across metadata-only updates.
- **Auxiliary identifiers** (non-authoritative, optional):
  - `baseline_package_uuid` (UI convenience)
  - `source_run.run_id` and `source_run.run_manifest_sha256` (provenance join)

Path mapping (authoritative):

- Published root: `<workspace_root>/exports/baselines/<baseline_id>/<baseline_version>/`
- Staging root: `<workspace_root>/exports/.staging/baselines/<baseline_id>/<baseline_version>/`
- Trash root (optional if implemented):
  `<workspace_root>/exports/baselines/.trash/<baseline_id>/<baseline_version>/`

#### Authoritative state representation

This state machine is derived from the filesystem (no separate state store required).

Persistence requirement (normative):

- MUST persist: `no`
- Implementations MAY maintain an equivalent cache/index, but it MUST be rebuildable by a
  deterministic scan of the authoritative paths below.

Authoritative paths:

- Published root: `<workspace_root>/exports/baselines/<baseline_id>/<baseline_version>/`
- Staging root: `<workspace_root>/exports/.staging/baselines/<baseline_id>/<baseline_version>/`
- Trash root (optional if implemented):
  `<workspace_root>/exports/baselines/.trash/<baseline_id>/<baseline_version>/`

Derivation rule (normative, ordered):

1. If the published root exists:
   - If `baseline_package_manifest.json` exists, parses, and passes manifest/path consistency checks
     (see [Listing](#listing)), AND required integrity material is present (at minimum:
     `security/checksums.txt`), AND the manifest-referenced required artifact paths exist, state is
     `published`.
   - Else, state is `invalid`.
1. Else if the staging root exists, state is `staging`.
1. Else if the trash root exists (when implemented), state is `trashed`.
1. Else, state is `absent`.

Note: If both published root and staging root exist, the published-root branch above takes
precedence; the staging root is treated as stale scratch and MUST NOT affect listing.

#### Inconsistent artifact state handling

Implementations MUST apply the following reconciliation rules deterministically when on-disk
artifacts are partial or contradictory.

Published-root inconsistencies (normative):

- If `baseline_package_manifest.json` is missing, unreadable, schema-invalid, or fails manifest/path
  consistency checks, derived state MUST be `invalid`.
- If `security/checksums.txt` is missing or unreadable, derived state MUST be `invalid`.
- If any manifest-referenced required artifact path is missing (for example `ground_truth_path`,
  `ocsf_events_path`, or `_schema.json` when `ocsf_events_representation=parquet_dataset`), derived
  state MUST be `invalid`.
- If signing artifacts are partially present:
  - If `security/signature.ed25519` is present but `security/checksums.txt` is missing/unreadable,
    derived state MUST be `invalid`.
  - If `security/signature.ed25519` is present but `security/public_key.ed25519` is absent, the
    package MAY still be treated as `published` (public key may be provided out-of-band). If an
    implementation requires `security/public_key.ed25519` by policy, it MUST treat this as `invalid`
    and fail closed for listing and export (RECOMMENDED error: `baseline_package_unsafe`).

Stale or contradictory roots (normative):

- If both published root and staging root exist, state derivation MUST ignore the staging root and
  MUST derive state exclusively from the published root (`published` or `invalid`).
  - The staging root MUST NOT be reused or deleted automatically.
- If the staging root exists and published root does not, derived state MUST be `staging` regardless
  of which intermediate creation step was reached.
- If the trash root exists concurrently with a published root, the published root takes precedence
  for state derivation, but this condition SHOULD be surfaced as `artifact_representation_conflict`
  during create/delete operations.

Multiple candidate manifests (normative):

- Only the canonical BDP-root `baseline_package_manifest.json` path is authoritative for discovery
  and state derivation. Other manifest-like filenames MUST be ignored for state derivation and MUST
  NOT affect listing eligibility.

#### Events / triggers vocabulary

Closed event set for this machine (normative):

- `event.create_requested`: A caller requests creation of a BDP for the instance key from a given
  source run bundle (see [Creation](#creation)).
- `event.publish_succeeded`: The create operation has completed staging and is ready to atomically
  publish (rename staging root to published root).
- `event.create_failed`: The create operation failed while in `staging` and MUST NOT partially
  publish. The staging root MAY be left for inspection.
- `event.metadata_update_requested`: A caller requests a metadata-only update to an existing
  published BDP (see [Metadata updates](#metadata-updates)).
- `event.delete_requested`: A caller requests deletion (or trash) of a published/invalid BDP (see
  [Deletion](#deletion)).

Event ordering / precedence (normative):

- If multiple *request* events are presented for the same instance within a single reconciliation
  pass, implementations MUST process at most one event and MUST apply the following precedence:
  `event.delete_requested` > `event.metadata_update_requested` > `event.create_requested`.
- After applying any event that mutates the filesystem, implementations MUST re-derive state from
  the filesystem before processing any subsequent event for the same instance key.
- `event.publish_succeeded` and `event.create_failed` are internal outcomes of a single create
  attempt and MUST NOT be synthesized by passive filesystem reconciliation.

#### States

| State       | Kind                | Description                                                                | Invariants (normative)                                                                                                          | Observable signals                                        |
| ----------- | ------------------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------- |
| `absent`    | initial             | No staged or published BDP exists for the key.                             | Neither published root nor staging root exists.                                                                                 | Listing excludes.                                         |
| `staging`   | intermediate        | Creation is in progress or an earlier create attempt left staged contents. | Published root does not exist; staging root exists.                                                                             | Create returns `baseline_create_in_progress` on conflict. |
| `published` | intermediate        | A complete, readable BDP exists and is eligible for listing and download.  | Published root exists and contains a manifest that is valid, path-consistent, and has required integrity material present.      | Listed by OI.                                             |
| `invalid`   | intermediate        | A directory exists at the published root but is not a valid BDP.           | Published root exists but required package material is missing/unreadable/invalid (manifest, checksums, or required artifacts). | SHOULD surface as `baseline_manifest_invalid`.            |
| `trashed`   | terminal (optional) | A deleted BDP retained in an internal trash location.                      | Trash root exists and published root does not exist.                                                                            | Not listed.                                               |

Notes:

- Listing MUST treat `published` as the only eligible state for normal baseline listing.
- Implementations MAY implement a trash facility. If trash is not implemented, deletion transitions
  directly to `absent`.

#### Transition rules (normative)

| From state  | Event                             | Guard (deterministic)                                                                     | To state              | Actions (entry/exit)                                                                                      | Failure mapping (recommended)                                                                                    |
| ----------- | --------------------------------- | ----------------------------------------------------------------------------------------- | --------------------- | --------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `absent`    | `event.create_requested`          | Published root does not exist AND staging root is empty/absent per [Creation](#creation). | `staging`             | Create staging directory; copy required artifacts; compute integrity; write manifest/checksums/signature. | `baseline_already_exists`, `baseline_create_in_progress`, `artifact_missing`, `artifact_representation_conflict` |
| `staging`   | `event.publish_succeeded`         | All required staged outputs exist; integrity artifacts computed; ready to publish.        | `published`           | Publish atomically by renaming staging dir to published root (as specified in [Creation](#creation)).     | `baseline_package_unsafe`                                                                                        |
| `staging`   | `event.create_failed`             | Any failure during staging (artifact missing, placeholder detected, conflict, unsafe).    | `staging`             | MUST NOT partially publish. Staging contents MAY be left for operator inspection; no listing impact.      | Error codes per [Error guidance](#error-guidance-non-exhaustive)                                                 |
| `published` | `event.metadata_update_requested` | Update touches only mutable metadata fields.                                              | `published`           | Atomically rewrite manifest/checksums/signature per [Metadata updates](#metadata-updates).                | `baseline_manifest_invalid`, `baseline_package_unsafe`                                                           |
| `published` | `event.delete_requested`          | None.                                                                                     | `absent` or `trashed` | Atomically remove published root or atomically move it to trash (no partial listing state).               | `baseline_not_found`                                                                                             |
| `invalid`   | `event.delete_requested`          | None.                                                                                     | `absent` or `trashed` | Same as delete above; delete is the primary remediation for invalid BDP roots.                            | `baseline_not_found`                                                                                             |

#### Entry actions and exit actions

This machine’s conformance-critical side effects are the filesystem mutations described in the
linked authority sections ([Creation](#creation), [Metadata updates](#metadata-updates),
[Deletion](#deletion), [Download / export](#download--export)).

Entry action summaries (normative):

- Enter `staging` (via `event.create_requested`): create/verify an empty staging directory; copy
  required artifacts; compute integrity; write manifest/checksums/(optional) signature.
- Enter `published` (via `event.publish_succeeded`): publish atomically by renaming the staging
  directory to the published root.
- Remain `published` (via `event.metadata_update_requested`): atomically rewrite
  `baseline_package_manifest.json`, `security/checksums.txt`, and (if present)
  `security/signature.ed25519`.
- Enter `absent` or `trashed` (via `event.delete_requested`): atomically remove the published root
  or atomically move it to trash.

Exit action summaries (normative):

- No additional required exit actions beyond the atomic filesystem operations above.

#### Illegal transitions

Policy (normative):

- Type: `fail_closed`
- Behavior: reject the event, do not mutate any on-disk artifacts, and surface a deterministic error
  to the caller.

Requirements (normative):

- For any `(state,event)` pair not present in the [Transition rules](#transition-rules-normative)
  table, the implementation MUST treat the event as an illegal transition and MUST fail closed.
- For any guard failure in the transition table, the implementation MUST fail closed (no coercion).
- Forbidden regression: an implementation MUST NOT attempt to transition from `published` to
  `staging` for the same `(baseline_id, baseline_version)` key. Rebuilds MUST use a new
  `baseline_version`.

Outcome classification and observability (normative):

- If invoked through the Operator Interface, illegal transitions and guard failures MUST:
  - return an error response using the stable error codes in
    [Error guidance](#error-guidance-non-exhaustive), and
  - emit an `audit_event` row to `logs/ui_audit.jsonl` for the attempted action (success or failure)
    per [Operator Interface integration](#operator-interface-integration).
- If invoked outside the Operator Interface, illegal transitions and guard failures MUST surface a
  deterministic error (exception / error code) and MUST NOT mutate artifacts.

Contract validation failure observability (normative):

- If a create or metadata update operation fails because contract-backed baseline package metadata
  is schema-invalid (for example the baseline package manifest fails the
  `baseline_detection_package_manifest` contract), the implementation MUST:
  - fail closed with no mutation of the published root, and
  - emit the workspace contract validation report for the baseline target root at
    `logs/contract_validation/exports/baselines/<baseline_id>/<baseline_version>.contract_validation.json`.

Recommended `(state,event)` failure mappings (non-exhaustive):

- `published` + `event.create_requested` -> `baseline_already_exists`
- `invalid` + `event.create_requested` -> `baseline_already_exists` (delete is primary remediation)
- `staging` + `event.create_requested` -> `baseline_create_in_progress`
- `absent` + `event.delete_requested` -> `baseline_not_found`
- `staging` + `event.delete_requested` -> `artifact_representation_conflict` (no cancel event in
  v1.0.0)
- `invalid` + `event.metadata_update_requested` -> `baseline_manifest_invalid`

#### Observability

Authoritative state representation (normative):

- The authoritative state is the derived state from
  [Authoritative state representation](#authoritative-state-representation).
- Implementations MUST NOT introduce a separate authoritative "state file" for this machine in
  v1.0.0.

State evidence surfaces (normative):

- `published`: published root exists and satisfies the derivation rule (manifest + checksums +
  required referenced artifacts).
- `invalid`: published root exists but fails the derivation rule.
- `staging`: staging root exists and published root does not.
- `trashed`: trash root exists and published root does not.
- `absent`: none of the above roots exist.

Transition evidence surfaces (normative):

- `absent` -> `staging`: existence of the staging root directory.
- `staging` -> `published`: atomic rename results in published root existing and staging root
  absent.
- `published` -> `published` (metadata update): `baseline_package_manifest.json` and
  `security/checksums.txt` bytes change, while `integrity.package_tree_sha256` SHOULD remain
  unchanged.
- `published`/`invalid` -> `absent`/`trashed`: published root absent, and (when trash is
  implemented) trash root present.

Failure evidence surfaces (normative):

- Invalid packages MUST be observable as `invalid` via the derivation rule and MUST be excluded from
  normal listings (see [States](#states)).
- Illegal transitions and guard failures MUST be observable via:
  - the API error response (when using the Operator Interface), and
  - the emitted `audit_event` row (see
    [Operator Interface integration](#operator-interface-integration)).

#### Conformance tests

Fixture-driven conformance tests are REQUIRED for any implementation that claims conformance with
this state machine.

Fixture root (normative):

- RECOMMENDED canonical fixture root: `tests/fixtures/baselines/lifecycle/`

Minimum fixture suite (normative):

1. **Happy path end-to-end**: `build -> validate -> publish`
   - Create a BDP from a minimal, valid source run bundle fixture.
   - Assert derived state transitions: `absent` -> `staging` -> `published`.
   - Assert published-root invariants: manifest schema-valid + path-consistent, checksums present
     and correct, `integrity.package_tree_sha256` matches recomputation.
1. **Idempotent re-runs**
   - Re-run `event.create_requested` for the same instance key and assert failure with
     `baseline_already_exists` and no on-disk mutation.
   - Re-run `event.metadata_update_requested` with no effective changes and assert byte-for-byte
     identical outputs (no-op is allowed).
1. **Crash / partial publish recovery**
   - Simulate a crash leaving a non-empty staging root with partial outputs.
   - Assert derived state is `staging` and subsequent create requests fail with
     `baseline_create_in_progress` (no silent cleanup).
1. **Illegal transitions**
   - Exercise at least: unknown `(state,event)` pair, guard failure, and forbidden regression.
   - Assert fail-closed behavior (no mutation) and stable error code surfaced.
1. **Determinism**
   - Listing determinism: stable ordering by `baseline_id` ascending and `baseline_version`
     descending (SemVer precedence with required tie-break).
   - Hash determinism: repeated creation from identical inputs produces identical
     `security/checksums.txt` and identical `integrity.package_tree_sha256`.
   - Export determinism: two exports of the same `<baseline_root>` are byte-for-byte identical.

### Listing

The baseline library is defined as the set of on-disk BDP roots under:

`<workspace_root>/exports/baselines/<baseline_id>/<baseline_version>/`

Discovery (normative):

- The library manager MUST enumerate direct children of `<workspace_root>/exports/baselines/`.
- A child directory is a `baseline_id` candidate only if its name is a valid `id_slug_v1` (see
  ADR-0001). Reserved directories (for example `.staging`, `.trash`) MUST be ignored.
- For each `baseline_id` directory, the manager MUST enumerate direct children and treat each child
  as a `baseline_version` candidate only if its name is a valid `semver_v1` (SemVer 2.0.0).
- A `(baseline_id, baseline_version)` candidate is a BDP only if it contains
  `baseline_package_manifest.json`.

Manifest/path consistency (normative):

- For each discovered BDP, the manager MUST parse `baseline_package_manifest.json`.
- `baseline_id` and `baseline_version` in the manifest MUST exactly match the two path segments used
  to discover the BDP. On mismatch, the BDP MUST be excluded from listings and SHOULD be surfaced as
  `baseline_manifest_invalid`.

The Operator Interface MUST list baselines by reading manifests from disk (or an equivalent cache).
Listings MUST be deterministic:

- `baseline_id` ascending (UTF-8 byte order, no locale)
- `baseline_version` descending by SemVer precedence
  - If two versions compare equal by SemVer precedence, ties MUST be broken by `baseline_version`
    string ascending (UTF-8 byte order, no locale).

### Creation

To create a BDP, the builder MUST:

1. Validate the source run exists, is readable, and is a run bundle root (contains `manifest.json`).
1. Validate required source artifacts exist and are not placeholders.
1. Select the normalized events representation per the rules in this spec (fail closed on conflict).
1. Create a staging directory at:
   `<workspace_root>/exports/.staging/baselines/<baseline_id>/<baseline_version>/`
   - The staging directory MUST be empty.
     - If the staging directory exists and is non-empty, creation MUST fail (RECOMMENDED error:
       `baseline_create_in_progress`). Implementations MUST NOT delete or reuse non-empty staging
       directories automatically.
   - Creation MUST fail if the final `<baseline_root>` already exists (conflict).
1. Copy required artifacts into the staging directory under `run/`, preserving relative paths and
   bytes.
1. Compute `replay_fast_path_eligible` for the package:
   - `true` iff `run/normalized/mapping_profile_snapshot.json` is present in staging, is not a
     placeholder artifact, and validates against the `mapping_profile_snapshot` contract.
   - otherwise `false`.
1. If signing is enabled, write `security/public_key.ed25519` into the staging directory before
   computing `integrity.package_tree_sha256`.
1. Compute `integrity.package_tree_sha256` from the staged file tree basis (as defined in
   [Integrity and signing](#integrity-and-signing)).
1. Write `baseline_package_manifest.json` (canonical JSON) into the staging directory.
1. Write `security/checksums.txt` for the staged package (as defined in
   [Integrity and signing](#integrity-and-signing)).
1. If signing is enabled, write `security/signature.ed25519` for the staged package.
1. Publish atomically by renaming the staging directory to `<baseline_root>`.

Creation MUST fail if `<baseline_root>` already exists (conflict).

Publish-gate integration (normative):

- The publish step for baseline packages MUST follow `pa.publisher.workspace.v1` semantics (see
  `025_data_contracts.md`, "Producer tooling: workspace publisher semantics (pa.publisher.workspace.v1)").
- Before the final rename into `exports/baselines/**`, the implementation MUST validate the staged
  baseline package manifest (and any other contract-backed baseline package metadata) against the
  workspace contract registry (`docs/contracts/workspace_contract_registry.json`).
- On contract validation failure, the implementation MUST fail closed:
  - the final published root under `exports/baselines/**` MUST NOT be created or modified, and
  - the workspace contract validation report MUST be written at
    `logs/contract_validation/exports/baselines/<baseline_id>/<baseline_version>.contract_validation.json`.

### Metadata updates

Implementations MAY support updating the following manifest fields in place:

- `description`
- `tags`
- `blessing`/curation fields (if implemented)

Updates MUST:

- preserve immutable identity fields (`baseline_id`, `baseline_version`, `source_run`, `profile`,
  `artifact_refs`, `replay_fast_path_eligible`)
- rewrite `baseline_package_manifest.json` as canonical JSON bytes
- `replay_fast_path_eligible` matches recomputation from package contents (presence +
  non-placeholder + schema validity of `run/normalized/mapping_profile_snapshot.json`).
- recompute `security/checksums.txt`
- update signature if present (or remove signature if signing is not configured)
- recompute `integrity.package_tree_sha256` only if any file included in the *tree-basis selection*
  changes (see [Integrity and signing](#integrity-and-signing)). Pure metadata edits MUST NOT change
  `integrity.package_tree_sha256`.

Contract validation (metadata updates; normative):

- Any updated `baseline_package_manifest.json` MUST validate against the workspace contract registry
  before the update is applied.
- On contract validation failure, the implementation MUST fail closed (no mutation to the published
  root) and MUST emit the workspace contract validation report at
  `logs/contract_validation/exports/baselines/<baseline_id>/<baseline_version>.contract_validation.json`.

### Deletion

Deletion MUST remove the full `<baseline_root>` directory (or move it to an internal trash location)
and MUST be atomic with respect to listing (no partial state).

### Download / export

The Operator Interface MAY expose a download of a BDP as an archive. If so:

Determinism (normative):

- For a fixed `<baseline_root>` and a fixed requested archive format (e.g., `tar` or `zip`), two
  downloads/exports produced by the same implementation MUST be byte-for-byte identical.
- The archive MUST be derived solely from the on-disk `<baseline_root>` contents (no embedded build
  timestamps, randomized ordering, or host-specific metadata).

Archive root and paths (normative):

- The archive root MUST be the BDP root directory contents (not wrapped in extra top-level folders).
- All archived entry paths MUST be BDP-root-relative (POSIX separators), MUST NOT start with `/`,
  and MUST NOT contain `..` path segments.
- Implementations MUST NOT prefix archived paths with `./`.

File type safety (normative):

- The archive generator MUST only include regular files.
- The archive generator MUST NOT follow symlinks (or platform-equivalent reparse points).
- If any symlink or other non-regular file type (block/char device, FIFO, socket) is encountered
  anywhere under `<baseline_root>`, archive generation MUST fail closed (RECOMMENDED error:
  `baseline_package_unsafe`).

Supported formats (normative when implemented):

- The implementation MUST support at least one deterministic archive format:
  - **Tar** (`.tar`) and MAY additionally support **gzip-compressed tar** (`.tar.gz`), and/or
  - **Zip** (`.zip`).
- If multiple formats are supported, each format MUST independently satisfy the determinism rules
  above.

Deterministic entry ordering (normative):

- Archive entries MUST be emitted in ascending `relative_path` order (UTF-8 byte order, no locale).
- Implementations MAY omit explicit directory entries (directories implied by file paths). If
  directory entries are emitted, they MUST be emitted deterministically and MUST appear before any
  file entries they contain.

Metadata normalization (normative):

- For **tar** outputs:

  - Each regular file entry MUST normalize header fields as follows:
    - `mtime = 0`
    - `uid = 0`, `gid = 0`
    - `uname = ""`, `gname = ""`
    - mode normalized to `0644` for regular files (and `0755` for directory entries, if emitted)
  - The writer MUST NOT emit symlink entries, hardlink entries, device entries, FIFOs, or sockets.
  - If the implementation uses PAX extended headers (e.g., for long paths), it MUST emit them
    deterministically and MUST NOT include time-varying keys (`mtime`, `atime`, `ctime`) or other
    host-specific metadata.

- For **gzip-compressed tar** (`.tar.gz`) outputs:

  - The gzip header MUST set `mtime = 0` and MUST NOT embed an original filename.
  - Compression settings MUST be fixed and deterministic for the implementation (for example, a
    fixed compression level and strategy).

- For **zip** outputs:

  - Each entry MUST use a fixed timestamp. RECOMMENDED: `1980-01-01T00:00:00Z` (zip epoch).
  - The archive MUST NOT include per-entry comments or a global archive comment.
  - The archive MUST NOT include variable extra fields (for example, extended timestamp fields).
  - Entry-name encoding MUST be deterministic (RECOMMENDED: UTF-8 with the UTF-8 flag set
    consistently).
  - If compression is enabled, the compressor settings MUST be fixed and deterministic for the
    implementation. RECOMMENDED: `stored` (no compression) unless size constraints require deflate.

## Operator Interface integration

- The Operator Interface MUST expose baseline library operations only through explicit baseline
  endpoints (see `115_operator_interface.md`) and MUST NOT treat baselines as run artifacts.
- All baseline library mutations MUST emit `audit_event` rows to the workspace-global audit log
  `logs/ui_audit.jsonl` (see `115_operator_interface.md`).
  - RECOMMENDED `action` values: `baseline.create`, `baseline.update`, `baseline.delete`,
    `baseline.download`.

## Error guidance (non-exhaustive)

Recommended API error codes (using the standard Operator Interface error envelope):

- `baseline_not_found` (404)
- `baseline_already_exists` (409)
- `baseline_create_in_progress` (409)
- `baseline_source_run_not_found` (404)
- `baseline_source_run_ineligible` (409)
- `artifact_missing` (422)
- `baseline_manifest_invalid` (422)
- `baseline_package_unsafe` (422)
- `artifact_representation_conflict` (409)

## Verification hooks

A conforming implementation SHOULD include automated checks that:

- A created BDP contains all required files and none of the forbidden prefixes.
- `baseline_package_manifest.json` validates against `baseline_detection_package_manifest` schema.
- `security/checksums.txt` is correctly formatted and sorted, and every included file digest
  matches.
- `integrity.package_tree_sha256` matches recomputation from the file tree basis.
- Listing order is deterministic and stable (including SemVer precedence tie-breaks).
- For `ocsf_events_representation=parquet_dataset`, BDP creation fails if
  `run/normalized/ocsf_events/_schema.json` is missing.
- BDP creation and export fail closed if any symlink (or platform-equivalent reparse point) or other
  non-regular file type is present anywhere under the staged package tree.
- Two downloads/exports of the same `<baseline_root>` produce deterministic archives (byte-for-byte
  identical).
- A fixture-driven conformance suite exists (RECOMMENDED root:
  `tests/fixtures/baselines/lifecycle/`) and covers: happy path build/publish, idempotent re-runs,
  crash recovery (staging left behind), illegal transitions, and determinism (stable ordering and
  stable hashes). See [Conformance tests](#conformance-tests).

A minimal fixture should include a small completed run bundle with:

- `manifest.json`
- `ground_truth.jsonl`
- one normalized events representation (including `_schema.json` when using the Parquet dataset
  form)
- at least one optional small log artifact.

## References

- [OCSF normalization specification](050_normalization_ocsf.md)
- [Data contracts and reader semantics](025_data_contracts.md)
- [Operator Interface](115_operator_interface.md)
- [Scoring metrics](070_scoring_metrics.md)
- [Project naming and versioning ADR](../adr/ADR-0001-project-naming-and-versioning.md)
- [Event identity and provenance ADR](../adr/ADR-0002-event-identity-and-provenance.md)
- [Mapping coverage matrix](../mappings/coverage_matrix.md)
- [State machines ADR](../adr/ADR-0007-state-machines.md)
- [Storage formats](045_storage_formats.md)
- [Test strategy CI](100_test_strategy_ci.md)

## Changelog

| Date       | Change                |
| ---------- | --------------------- |
| 2026-02-26 | State machines update |
| 2026-01-28 | Init spec             |
