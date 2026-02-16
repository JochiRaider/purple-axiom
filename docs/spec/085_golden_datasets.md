---
title: Golden dataset generation for ML training and evaluation
description: Deterministic dataset exports derived from run bundles with label-strippable views and reproducible splits for log analysis and attack detection training.
status: draft
category: spec
tags: [datasets, ml, export, provenance, determinism]
related:
  - 025_data_contracts.md
  - 030_scenarios.md
  - 035_validation_criteria.md
  - 045_storage_formats.md
  - 050_normalization_ocsf.md
  - 055_ocsf_field_tiers.md
  - 060_detection_sigma.md
  - 070_scoring_metrics.md
  - 080_reporting.md
  - 090_security_safety.md
  - 115_operator_interface.md
  - ../adr/ADR-0001-project-naming-and-versioning.md
  - ../adr/ADR-0002-event-identity-and-provenance.md
  - ../adr/ADR-0003-redaction-policy.md
  - ../adr/ADR-0004-deployment-architecture-and-inter-component-communication.md
  - ../adr/ADR-0005-stage-outcomes-and-failure-classification.md
  - ../adr/ADR-0007-state-machines.md
---

# Golden dataset generation for ML training and evaluation

## Overview

This document defines a deterministic, reproducible mechanism for generating "golden datasets" from
Purple Axiom run bundles for:

- model training (supervised / weakly supervised) on log analysis tasks (attack detection, technique
  classification, normalization assistance),
- model evaluation using label-stripped feature views and re-attachable labels,
- regression testing of dataset build determinism in CI.

**Golden** means: labels are derived from first-class ground truth and pipeline outcomes, not from
manual annotation; and labels can be removed from a "feature view" and re-applied deterministically
via stable join keys.

## Non-goals

- Defining new attack execution content or new annotation pipelines.
- Providing environment-specific "query generation" (Splunk/KQL) tasks in v0.1.
- Publishing requirements for a specific ML framework or trainer.
- Treating public dataset exports as authoritative run bundles (the authoritative source remains the
  original run bundles).

## Terminology

- **Run bundle**: the on-disk run artifact directory `runs/<run_id>/` containing contract-backed
  artifacts.
- **Dataset release**: an export product containing one or more runs, plus metadata describing
  views, splits, and provenance pins.
- **Dataset view**: a filtered projection of run artifacts intended for a specific consumer use case
  (features-only, labels-only, etc.).
- **Features**: artifacts intended as model inputs (e.g., normalized OCSF events).
- **Labels**: artifacts intended as training/evaluation targets (e.g., `technique_id`, detection
  matches).
- **Join keys**: stable keys used to re-attach labels to features.
  - **Run-level**: `run_id`.
  - **Event-level**: `(run_id, metadata.event_id)`.
  - (Reserved for v0.2+ / multi-action runs) **Action-level**: `(run_id, action_id)` (ground truth
    action instance id).
- **Release posture**:
  - `public`: redaction-safe only, suitable for broad distribution.
  - `gated`: access-controlled; still redaction-safe, but may include richer derived artifacts.
  - `internal`: may include non-public artifacts subject to explicit governance controls.

## v0.1 Scope

### Supported primary tasks (v0.1)

The dataset release MUST support the following tasks using mechanically derivable labels from
existing artifacts.

Note (v0.1): runs are expected to be single-action (one `ground_truth.jsonl` line per run), per the
v0.1 plan model. Multi-step attribution across multiple distinct actions per run is deferred (see
"Deferred tasks").

1. **Technique labeling (classification)**

   - Label target: `technique_id` (and `engine_test_id` when present) from `ground_truth.jsonl`.
   - Join: run-level (`run_id`). (For v0.1 single-action runs, this is equivalent to action-level.)

1. **Phase attribution (event window labeling)**

   - Label target: `prepare | execute | revert | teardown` per event, derived by joining:
     - `ground_truth.jsonl.lifecycle.phases[].{started_at_utc,ended_at_utc,phase}`, and
     - normalized event time `time` (ms since epoch UTC) from `normalized/ocsf_events/`.
   - Window semantics (deterministic):
     - A phase applies when `started_at_utc <= event_time_utc < ended_at_utc`.
     - Events not covered by any phase window MUST have `phase` omitted (or set to null) in any
       derived label table.

1. **Detection and evaluation outcome labeling**

   - Labels derived from detection outputs (`detections/…`) and scoring summaries (`scoring/…`) to
     support tasks like "did rule X match any events" and "gap category".
   - Join expectations:
     - `detections/detections.jsonl` instances join to events via `matched_event_ids[]` which
       reference `metadata.event_id`.
     - run-level scoring summaries join via `run_id`.

1. **Normalization assistance (Tier 0 + Tier 1 only)**

   - Inputs: raw event stores (when present) plus normalized OCSF store.
   - Label target: Tier 0 + Tier 1 OCSF fields only (see `055_ocsf_field_tiers.md`).
   - Join requirement (v0.1):
     - Any raw records included for this task MUST carry the corresponding `metadata.event_id` so
       they can be joined to `normalized/ocsf_events/` without heuristic matching.

### Deferred tasks (v0.2+ / research mode)

- Multi-step attribution across multiple distinct actions per run (requires non-trivial multi-action
  plans).
- Free-form triage narrative generation over raw evidence.
- Open-ended query generation (Splunk/KQL).

## Dataset release model

### Identifiers and versioning

A dataset release MUST include the following identifiers:

- `dataset_id` (id_slug_v1, per ADR-0001).
- `dataset_version` (SemVer, per ADR-0001).
- `dataset_release_id` (content hash identifier) computed deterministically from the dataset
  manifest hash basis (see below).

### Release posture

- Dataset builds MUST declare a `release_posture` (`public | gated | internal`).
- For `public` posture:
  - The dataset build MUST fail closed if any included artifact is `quarantined` or requires
    `security.redaction.enabled=false` to exist.
- For `gated` posture:
  - The dataset build MAY include additional artifacts as long as they are redaction-safe and do not
    contain secrets.
- For `internal` posture:
  - The dataset build MAY include quarantined/unredacted artifacts only when explicitly enabled by
    operator intent gates (see `090_security_safety.md` and ADR-0003).
  - Internal releases MUST include a prominent "NOT FOR TRAINING WITHOUT GOVERNANCE REVIEW" notice
    in the dataset card.

## Source artifacts and prerequisites

### Run inclusion requirements (v0.1)

For a run to be eligible for inclusion in a dataset release, it MUST:

- have a readable `runs/<run_id>/manifest.json` that passes contract validation,
- NOT be actively written (the run MUST NOT have an active run lock file at
  `runs/.locks/<run_id>.lock`, per ADR-0004),
- pass run bundle contract validation for all artifacts that the dataset release claims to include,
- include `ground_truth.jsonl` (for technique/phase labels), and
- include a normalized OCSF event store (`normalized/ocsf_events/`) when any task uses normalized
  events as features.

If the dataset build is configured to include detection or scoring-derived labels, the run MUST also
include the corresponding contracted artifacts (`detections/…`, `scoring/…`) or the build MUST fail
closed unless explicitly configured to skip those runs.

The dataset build MUST record, per included run, which required artifacts were present vs
withheld/quarantined/absent.

### Canonical artifact paths

Dataset releases MUST treat the following run bundle artifact paths as canonical (non-exhaustive):

- Ground truth:
  - `runs/<run_id>/ground_truth.jsonl`
- Normalized OCSF store:
  - `runs/<run_id>/normalized/ocsf_events/` (Parquet dataset dir, includes `_schema.json`)
- Detection outputs:
  - `runs/<run_id>/detections/detections.jsonl` (and any additional detection artifacts defined by
    the detection spec)
- Scoring outputs:
  - `runs/<run_id>/scoring/summary.json` (and any additional scoring artifacts)
- Reporting outputs (optional for dataset builds; required only if the dataset claims to include
  reporting-derived labels):
  - `runs/<run_id>/report/report.json`, `runs/<run_id>/report/report.html`

(See deployment/pipeline artifact guidance in ADR-0004.)

## Dataset views and label separation

### View types (normative)

A dataset release MUST support the following views:

1. **features view**

   - Contains only feature artifacts intended as ML inputs.
   - MUST NOT include label-bearing artifacts (ground truth, detections, scoring summaries,
     reports).
   - MUST retain join keys needed to re-attach labels (at least `run_id` and `metadata.event_id` in
     event stores).

1. **labels view**

   - Contains label-bearing artifacts only.
   - MUST include at minimum:
     - `ground_truth.jsonl`
   - MAY include:
     - detection outputs (`detections/…`)
     - scoring outputs (`scoring/…`)
     - structured report outputs (if used as labels; see below)

1. **provenance view** (optional but recommended)

   - Contains run manifests and version pins used to support reproducibility auditing.
   - Producers SHOULD treat human-readable scenario names/descriptions as potentially label-leaking
     metadata for ML tasks and SHOULD place them here rather than in the features view.

### Strip and re-apply labels contract

- A consumer MUST be able to remove the `views/labels/` subtree from a dataset release and still
  load the `views/features/` view without errors.
- A consumer MUST be able to re-attach labels deterministically using:
  - `run_id` joins for run-level labels (v0.1 technique labels), and
  - `(run_id, metadata.event_id)` joins for event-level labels (detections and any derived
    event-window labels).
- Any label-bearing artifact included under `views/labels/` MUST either:
  - carry the appropriate join keys as fields (`run_id` and, when event-scoped,
    `metadata.event_id`), or
  - be accompanied by a deterministic join table under `views/labels/` that maps the artifact’s
    native identifiers to the join keys.

### Synthetic correlation marker leakage controls

The project’s synthetic correlation marker is valuable for attribution, but can trivialize learning
tasks if exposed as a feature.

Marker location (v0.1):

- Normalized OCSF events:
  - `metadata.extensions.purple_axiom.synthetic_correlation_marker` (string)
  - `metadata.extensions.purple_axiom.synthetic_correlation_marker_token` (string)
- Ground truth (when enabled):
  - `extensions.synthetic_correlation_marker` on each ground truth line
  - `extensions.synthetic_correlation_marker_token` on each ground truth line

Therefore dataset builds MUST support two feature variants (selected at build time per release):

1. **marker-assisted** (audit / debugging)

   - Marker fields MAY be present in feature artifacts.

1. **marker-blind** (default for ML)

   - Marker fields MUST be removed from all feature artifacts (both the canonical marker string and
     the derived token).
   - Removing marker fields MUST NOT change `metadata.event_id` values (marker fields are not part
     of event identity).
   - Marker fields MUST still be retained in labels/provenance artifacts when present in ground
     truth, so auditors can confirm end-to-end attribution.

Variant declaration and identity (normative):

- Each dataset release MUST declare the selected variant in `dataset_manifest.json` (see manifest
  schema).
- The selected variant MUST participate in `dataset_release_id` computation (see hash basis) so that
  marker-assisted and marker-blind exports cannot collide on the same `dataset_release_id`.

## Packaging and layout

### Output location

Dataset outputs MUST be written outside any run bundle directory under the reserved workspace
`exports/` root. (This mirrors export behavior for other secondary artifacts, see operator interface
guidance.)

Authoritative final output location (normative):

- `<workspace_root>/exports/datasets/<dataset_id>/<dataset_version>/`

Recommended staging location (crash-safe; reserved scratch):

- `<workspace_root>/exports/.staging/datasets/<dataset_id>/<dataset_version>/`

Dataset build tooling MUST treat all `runs/<run_id>/` inputs as read-only and MUST NOT create or
modify artifacts inside any run bundle directory.

#### Build staging and atomic publish (recommended)

To be crash-safe and to integrate cleanly with filesystem-derived state machines (ADR-0004,
ADR-0007), producers SHOULD:

1. Write the entire dataset release into a staging directory under the workspace exports staging
   root:
   - `<workspace_root>/exports/.staging/datasets/<dataset_id>/<dataset_version>/`
1. Validate the staged output (schemas, required files, determinism checks).
1. Atomically publish by renaming the staging directory to the final location:
   - `<workspace_root>/exports/datasets/<dataset_id>/<dataset_version>/`

If a build fails before publish, the final output directory MUST NOT be created or partially
populated. The staging directory MAY remain on failure for inspection and operator cleanup.

Representational state machine (non-normative; lifecycle authority: ADR-0004, ADR-0007):

- `absent` -> `staging` -> `published`
- `staging` -> `failed` (staging directory retained for inspection; operator cleanup required)

Authoritative observability signals:

- `published`: final directory exists and contains `dataset_manifest.json` and
  `security/checksums.txt`
- `staging`: staging directory exists under `exports/.staging/`

#### Export path helpers (recommended)

To avoid bespoke path logic across tooling and to keep workspace write-boundary enforcement
mechanical, implementations SHOULD centralize dataset release path resolution in a single helper.

Minimum helper contract:

- `resolve_dataset_release_dir(workspace_root, dataset_id, dataset_version) -> Path`
  - Returns: `<workspace_root>/exports/datasets/<dataset_id>/<dataset_version>/`
- `resolve_dataset_release_staging_dir(workspace_root, dataset_id, dataset_version) -> Path`
  - Returns: `<workspace_root>/exports/.staging/datasets/<dataset_id>/<dataset_version>/`

Validation (normative):

- The helper MUST validate `dataset_id` as `id_slug_v1` and `dataset_version` as `semver_v1`
  (ADR-0001) before any filesystem writes occur.
- The helper MUST reject values that would escape the intended directory (path separators, `..`, or
  URL-encoded equivalents).

Verification hook (RECOMMENDED):

- Unit tests SHOULD cover a table of invalid `(dataset_id, dataset_version)` pairs (including
  `../x`, `x/..`, and `x%2F..`) and assert deterministic failure.
- Unit tests SHOULD cover a valid pair and assert the helper returns an exactly normalized path.

### Canonical dataset release layout

A dataset release directory MUST have the following structure:

- `<workspace_root>/exports/datasets/<dataset_id>/<dataset_version>/`
  - `dataset_manifest.json`
  - `views/`
    - `features/`
      - `runs/<run_id>/...` (feature slice for each run)
    - `labels/`
      - `runs/<run_id>/...` (label slice for each run)
    - `provenance/` (optional)
      - `runs/<run_id>/manifest.json` (and other provenance artifacts)
  - `splits/`
    - `split_config.json`
    - `split_assignments.jsonl`
  - `docs/`
    - `README.md` (dataset card)
    - `DATASHEET.md` (dataset datasheet; see below)
    - `CHANGELOG.md` (optional)
  - `security/`
    - `checksums.txt`
    - `signature.ed25519` (optional)
    - `public_key.ed25519` (optional)

### Slice rules (normative)

For each included run:

- `views/features/runs/<run_id>/` MUST contain:

  - `normalized/ocsf_events/` (when normalized features are in scope),
  - and MAY contain raw stores (e.g., `raw_parquet/…`) only when the release posture permits it.

- `views/labels/runs/<run_id>/` MUST contain:

  - `ground_truth.jsonl`,
  - and MAY contain `detections/…`, `scoring/…`, `criteria/…`, `report/…` when the dataset build
    includes those tasks.

- `views/provenance/runs/<run_id>/` MAY contain:

  - `manifest.json`,
  - pinned pack manifests/snapshots if present in the run bundle,
  - but MUST NOT contain quarantined/unredacted artifacts in `public` posture.

## Dataset manifest

### Manifest file name

- The dataset release MUST include `dataset_manifest.json` at its root.

### Manifest schema (normative)

`dataset_manifest.json` MUST be a single JSON object with:

- `contract_version`: SemVer string (MUST be `0.1.0`)
- `schema_version`: `"pa:dataset_manifest:v1"`
- `dataset_id`: id_slug_v1
- `dataset_version`: SemVer
- `dataset_release_id`: string (see hash basis below)
- `release_posture`: `"public" | "gated" | "internal"`
- `created_at_utc`: RFC 3339 UTC timestamp
  - Determinism: implementations MUST support an explicit override for `created_at_utc` so CI can
    produce byte-identical dataset releases when required.
- `build`:
  - `tool_name`: string
  - `tool_version`: string
  - `config_hash_sha256`: string (digest string `sha256:<lowercase_hex>` of canonical JSON for the
    effective build config; see "Build config hash basis")
  - `tasks[]`: array of stable task ids, sorted ascending (bytewise UTF-8)
    - Allowed values (v0.1): `technique_labeling`, `phase_attribution`, `detection_outcomes`,
      `normalization_assistance`
  - `features_variant`: `"marker_blind" | "marker_assisted"`
- `inputs`:
  - `runs[]`: array of run input entries (see below), sorted by `run_id` ascending (bytewise UTF-8)
- `views_glob_version`: `"glob_v1"` (declares the glob grammar for `views[].includes[]` and
  `views[].excludes[]`)
- `splits`:
  - `split_config_path`: `"splits/split_config.json"`
  - `split_assignments_path`: `"splits/split_assignments.jsonl"`
- `security`:
  - `checksums_path`: `"security/checksums.txt"`
  - `signature_path`: optional
  - `public_key_path`: optional

#### Run input entry (normative)

Each element of `inputs.runs[]` MUST have:

- `run_id`: UUID string
- `run_manifest_sha256`: string
  - Digest string `sha256:<lowercase_hex>` of the exact source run’s `manifest.json` file bytes.
- `source_ref`: string
  - Either a filesystem path or URI identifying the source run bundle root/archival source.
- `included_views`:
  - object with boolean keys `features`, `labels`, `provenance`
- `artifact_handling`:
  - object describing handling for required artifacts using values:
    - `present | withheld | quarantined | absent`
  - At minimum, the following keys MUST be present:
    - `ground_truth`
    - `normalized_ocsf_events`
  - Keys MAY be extended (e.g., `detections`, `scoring_summary`, `report_json`).

#### View entry (normative)

Each element of `views[]` MUST have:

- `view_id`: `"features" | "labels" | "provenance"`
- `root_path`: string
  - Dataset-relative path to the view root (example: `"views/features"`).
- `includes[]`: array of strings
  - Sorted array of dataset-release-root relative POSIX paths or `glob_v1` patterns included in the
    view.
  - Each entry MUST be a valid `glob_v1` pattern over dataset-release-root relative candidate paths
    (fail closed on invalid patterns).
- `excludes[]`: array of strings (optional)
  - Sorted array of dataset-release-root relative POSIX paths or `glob_v1` patterns excluded from
    the view.
  - Each entry MUST be a valid `glob_v1` pattern over dataset-release-root relative candidate paths
    (fail closed on invalid patterns).

### Manifest canonicalization and hashing

Determinism requirements:

- `dataset_manifest.json` MUST be serialized using the canonical JSON requirements defined in
  `025_data_contracts.md` for hashing and CI comparisons.
- `dataset_release_id` MUST be reproducible across builds given the same inputs and the same
  effective build config. In particular, `created_at_utc` MUST NOT affect `dataset_release_id`.

#### Build config hash basis (normative)

`build.config_hash_sha256` MUST be computed as:

`"sha256:" + sha256_hex(canonical_json_bytes(build_config_basis))`

Where `build_config_basis` is a single JSON object with:

- `v`: `"pa.dataset_build_config_hash_basis:v1"`
- `release_posture`
- `tasks[]`
- `features_variant`
- `views_glob_version`
- `views[]`: for each view, the tuple `{ view_id, includes[], excludes[] }` (with arrays sorted as
  specified in the manifest schema)

`build_config_basis` MUST NOT include host- or time-specific fields such as output directories,
absolute paths, machine identifiers, or timestamps.

#### Dataset release id hash basis (normative)

Hash basis object:

- `v`: `"pa.dataset_release_hash_basis:v1"`
- `dataset_id`
- `dataset_version`
- `release_posture`
- `build_config_sha256` (equals `build.config_hash_sha256`)
- `runs[]`: sorted array of `{ run_id, run_manifest_sha256 }`
  - `run_manifest_sha256` is the digest string `sha256:<lowercase_hex>` of the exact source run’s
    `manifest.json` bytes.
- `split_config_sha256`: digest string `sha256:<lowercase_hex>` of the exact
  `splits/split_config.json` file bytes

`dataset_release_id = "pa:dsrel:v1:" + sha256_hex(canonical_json_bytes(hash_basis))`.

## Splits

### Split configuration (`splits/split_config.json`)

The dataset release MUST include a split config that declares:

- `contract_version`: SemVer string (MUST be `0.1.0`)
- `schema_version`: `"pa:dataset_splits_config:v1"`
- `policy`:
  - `split_names`: array (default: `["train","val","test"]`)
  - `split_fractions`: object (default: `{ "train": 0.8, "val": 0.1, "test": 0.1 }`)
  - `seed`: string (default: `"pa:v1"`)
  - `group_key`: enum (default: `"engine_technique_engine_test"`)
- `group_key_definition`:
  - explicit statement of which fields form the group key (see below)
- `hash`:
  - `algorithm`: `"sha256"`
  - `encoding`: `"hex_lower"`
  - `basis_version`: `"pa.split_hash_basis:v1"`

### Default grouping key (v0.1)

To reduce cross-split leakage, the default split grouping key MUST keep identical procedures
together:

- `group_key = (engine, technique_id, engine_test_id)` (with null-safe normalization)

The dataset build MUST treat all runs that share the same group key as inseparable: they MUST all be
assigned to the same split.

### Split assignment algorithm (normative)

Validation (fail closed):

- `policy.split_names[]` MUST be non-empty, MUST contain unique values, and ordering MUST be treated
  as authoritative.
- `policy.split_fractions` MUST contain exactly the keys listed in `policy.split_names[]`.
- All fraction values MUST be finite numbers in `(0, 1]`.
- The sum of fractions across `policy.split_names[]` MUST equal `1.0` within an absolute tolerance
  of `1e-9`.

For each run:

1. Compute its group key string using a canonical encoding:
   - `engine` empty -> `"-"`
   - `technique_id` empty -> `"-"`
   - `engine_test_id` empty -> `"-"`
   - Concatenate as: `engine + "|" + technique_id + "|" + engine_test_id`
   - v0.1 constraint: if a run contains more than one distinct
     `(engine, technique_id, engine_test_id)` tuple in `ground_truth.jsonl`, the dataset build MUST
     fail closed unless an explicit multi-action grouping policy is configured.
1. Compute `h_hex = sha256_hex(UTF8(seed + "|" + group_key_string))`.
1. Interpret the first 8 hex characters of `h_hex` as an unsigned 32-bit integer `u` (big-endian
   hex), then compute `r = u / 2^32` as a real number in `[0,1)`.
1. Assign a split deterministically by walking `policy.split_names[]` in order and selecting the
   first split whose cumulative fraction threshold exceeds `r` (the final split MUST be treated as
   the catch-all remainder).

The dataset build MUST emit:

- `splits/split_assignments.jsonl` with one JSON object per run:
  - `contract_version`: SemVer string (MUST be `0.1.0`)
  - `schema_version`: `"pa:dataset_split_assignment:v1"`
  - `run_id`
  - `split`
  - `group_key_string`
  - `group_key_hash_sha256` (MUST equal `"sha256:" + h_hex`)

File ordering MUST be deterministic by sorting lines by `run_id` ascending (bytewise UTF-8).

## Hugging Face projection (optional)

Purple Axiom dataset releases are filesystem-native. However, producers MAY generate a derived
Hugging Face projection for convenience.

If a Hugging Face projection is generated, it MUST:

- be derived from `views/features` and (optionally) `views/labels`,
- never include quarantined/unredacted artifacts,
- include a dataset card (`docs/README.md`) with:
  - clear licensing,
  - composition and provenance notes,
  - leakage caveats (marker, scenario metadata),
  - intended tasks and limitations.

(Reference: Hugging Face dataset cards and metadata conventions.)

## Dataset documentation requirements

A dataset release MUST include:

1. `docs/README.md` (dataset card)

   - Audience: dataset consumers.
   - Must include: intended tasks, how to load, how to use views, and leakage cautions.

1. `docs/DATASHEET.md` (dataset datasheet)

   - Audience: governance, reviewers, and downstream deployers.
   - Must include: motivation, composition, collection process (derived from run bundles),
     privacy/redaction posture, labeling process (ground truth + deterministic derivations), known
     limitations.

## Integrity

`security/checksums.txt` format and coverage MUST follow the same conventions as run bundle signing
(see `025_data_contracts.md`), adapted to the dataset release root.

Normative requirements:

- Dataset releases MUST include `security/checksums.txt`.
- `security/checksums.txt` MUST be UTF-8 with LF (`\n`) newlines and contain one record per line in
  the format: `sha256:<lowercase_hex><space><relative_path><newline>`.
  - `sha256:<lowercase_hex>` MUST match `^sha256:[0-9a-f]{64}$` and MUST equal `sha256(file_bytes)`
    serialized in the canonical digest string form.
  - `relative_path` MUST be dataset-release-root relative, use POSIX separators (`/`), and be
    compared and sorted using UTF-8 byte order (no locale).
- `security/checksums.txt` MUST include every file under the dataset release directory except:
  - `.staging/**` (unexpected under a published release; treated as transient scratch when present),
  - `security/checksums.txt` and `security/signature.ed25519` (to avoid self-reference).

Signing (optional):

- Producers MAY sign `security/checksums.txt`.
- If signing is enabled:
  - signature algorithm MUST be Ed25519,
  - `security/signature.ed25519` MUST be computed over the exact bytes of `security/checksums.txt`,
  - `security/public_key.ed25519` MUST contain the public key as base64 of the 32 raw bytes,
    followed by a single LF,
  - signature and public key files MUST be verifiable offline.

## Verification and CI

Implementations MUST provide deterministic conformance tests suitable for CI:

### Fixture requirements (minimum)

CI MUST include a fixture dataset build that:

- takes a fixed set of small run bundles as input (stored as test fixtures),
- emits a dataset release under `<workspace_root>/exports/datasets/<dataset_id>/<dataset_version>/`
  (within a temporary workspace root created for the fixture),
- does not create or modify any files under the input run bundles (`runs/<run_id>/` is treated as
  read-only input; validate via a before/after tree snapshot or hashes),
- writes only within the reserved export namespaces used by dataset builds:
  - `exports/datasets/**` (final output)
  - `exports/.staging/datasets/**` (staging; when enabled),
- validates:
  1. workspace contract validation (registry-driven):
     - `dataset_manifest.json` (validation_mode `json_document`)
     - `splits/split_config.json` (validation_mode `json_document`)
     - `splits/split_assignments.jsonl` (validation_mode `jsonl_lines`)
  1. `dataset_manifest.json` and `splits/split_config.json` deterministic ordering,
  1. `dataset_release_id` reproducibility,
  1. `splits/split_assignments.jsonl` reproducibility,
  1. label stripping:
     - deleting `views/labels/` still allows loading features,
     - join keys exist in features and labels to re-attach labels,
  1. marker-blind behavior:
     - marker absent from features in marker-blind mode,
     - `metadata.event_id` values unchanged vs marker-assisted mode,
  1. integrity artifacts:
     - `security/checksums.txt` exists and matches the required line format and ordering,
     - `security/checksums.txt` does not include itself or `security/signature.ed25519`,
  1. (when staging is enabled) publish-gate hygiene:
     - final output does not contain `.staging/` content.

### Failure modes (normative)

Dataset build MUST fail closed (non-zero exit) for:

- missing required artifacts for declared tasks (unless explicitly configured to skip),
- presence of quarantined/unredacted artifacts in `public` posture,
- non-deterministic outputs detected by self-checks (e.g., manifest reorder instability),
- schema validation failures for included contract-backed artifacts.

## Release posture definitions

We classify each dataset in the golden catalog into one of:

- **Public**: Approved for broad redistribution. We may publish an internal snapshot and/or an
  external artifact, consistent with license obligations (e.g., attribution, notice retention).
- **Gated**: Approved for use, but access is controlled (ACL + acknowledgement). Typically used for
  share-alike licenses (e.g., CC BY-SA) and/or elevated IP/content risk. Default stance: **do not
  publicly re-host**; instead, provide a reproducible build script and a manifest that pulls from
  the authoritative upstream.
- **Internal**: Restricted to employees/approved contractors only. Used for proprietary,
  user-derived, or otherwise sensitive datasets; also used when license terms prevent broader
  distribution.

### Default decision rules (v0.1)

- **Share-alike (CC BY-SA / similar)** ⇒ **Gated** (to avoid accidental license propagation into
  broader artifacts).
- **Provenance unclear / underlying rights ambiguous** ⇒ **Gated** until Legal review clears
  posture.
- **PII plausible (privacy class P2+)** ⇒ **Internal** until scan + mitigations complete; may later
  move to **Gated** or **Public** depending on results and policy.
- **Code-execution evals** (e.g., HumanEval, MBPP) ⇒ allowed, but require a sandboxed evaluation
  harness (security control, not licensing).

## v0.1 Golden dataset catalog (initial)

## Evidence required to mark a dataset “Golden”

A dataset is not “golden” until the following evidence artifacts exist and are linked from the
catalog entry:

1. **Dataset card** (human-readable)

   - License and obligations (attribution, share-alike, notice retention)
   - Provenance summary + upstream links
   - Sensitivity classification (privacy + content + IP risk)
   - Release posture (public/internal/gated) + rationale
   - Owners (data steward + technical owner)

1. **Reproducible build manifest** (machine-executable, immutable)

   - Upstream locator (repo/dataset + revision/tag/commit)
   - Retrieval timestamp
   - Hashes for raw + normalized artifacts
   - Deterministic transformations (canonical schema, normalization steps)
   - Split membership fingerprints (hash per split)

1. **Approvals record**

   - Legal license/provenance signoff (explicitly approves posture)
   - Privacy signoff (scan evidence, mitigation plan if needed)
   - Security signoff where relevant (code execution / sandboxing)
   - Data governance signoff (completeness of artifacts)

## Intake and validation workflow (v0.1)

1. **Candidate intake**

   - Identify candidate dataset and intended regression coverage.
   - Capture upstream canonical reference (HF dataset page or GitHub repo).

1. **License + provenance validation**

   - Record license identifier and obligations.
   - Capture upstream provenance statements (dataset card / paper / repo statement).

1. **Sensitivity classification**

   - Run PII scan + document results (especially for “naturally occurring” query datasets).
   - Tag content-risk categories relevant to distribution policy.

1. **Deterministic build**

   - Convert to canonical schema and freeze artifact hashes.
   - Store split hashes and schema fingerprint.

1. **Approvals + publication**

   - Collect signoffs; store approvals record.
   - Publish to catalog with the approved posture (public/internal/gated) and enforce access
     controls.

## TODO

- [ ] Define and implement the **dataset card + build manifest + approvals record schema**
  (validator + CI checks).
- [ ] Implement/standardize **gating controls** (ACL groups, acknowledgement/click-through, audit
  logging) for “Gated” datasets.

## Future extensions (non-normative)

- Add optional "structured triage narrative" tasks derived only from redaction-safe report fields.
- Add tactic labeling by pinning an explicit ATT&CK mapping table version as an input.
- Add multi-step attribution once multi-action plans are standard.

| Date       | Change        |
| ---------- | ------------- |
| 2026-01-23 | Initial draft |
