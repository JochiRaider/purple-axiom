---
title: Dataset release generation for ML training and evaluation
description: Deterministic dataset releases derived from run bundles, with label-strippable views and reproducible splits for log analysis and attack detection training.
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

# Dataset release generation for ML training and evaluation

## Overview

This document defines a deterministic, reproducible mechanism for generating dataset releases from
Purple Axiom run bundles for:

- model training (supervised / weakly supervised) on log analysis tasks (attack detection, technique
  classification, normalization assistance),
- model evaluation using label-stripped feature views and re-attachable labels,
- regression testing of dataset build determinism in CI.

**Mechanically labeled** means: labels are derived from first-class ground truth and pipeline
outcomes, not from manual annotation; and labels can be removed from a features view and re-applied
deterministically via stable join keys.

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
  - **Event-level (v0.1, raw_ref-first)**:
    - Primary: `(run_id, metadata.extensions.purple_axiom.raw_ref)` when `raw_ref != null`.
    - Fallback (IT3 only): `(run_id, metadata.event_id)` when `raw_ref == null`.
  - (Reserved for v0.2+ / multi-action runs) **Action-level**: `(run_id, action_id)` (ground truth
    action instance id).
- **IT1 / IT2 / IT3**: identity tiers corresponding to `metadata.identity_tier` values `1 | 2 | 3`
  (ADR-0002).
- **FT0 / FT1 / FT2 / FT3 / FT-R**: OCSF field tiers per `055_ocsf_field_tiers.md`.
- **Tier terminology (dataset-doc-local; normative)**:
  - In this document, unqualified `"Tier N"` terminology is invalid and MUST NOT be used.
  - Identity tiers MUST be referenced as `IT1`, `IT2`, `IT3`.
  - OCSF field tiers MUST be referenced as `FT0`, `FT1`, `FT2`, `FT3`, `FT-R`.    
- **raw_ref**: canonical raw-origin pointer for an event, stored at
  `metadata.extensions.purple_axiom.raw_ref`.
  - Structured object (not a single string); see "Event join keys and join bridge (normative)".
  - Identity tier constraints:
    - IT1 and IT2: `raw_ref` is required (non-null).
    - IT3: `raw_ref` MUST be null.
- **Dataset release posture**:
  - `public`: redaction-safe only, suitable for broad distribution.
  - `gated`: access-controlled; still redaction-safe, but may include richer derived artifacts.
  - `internal`: may include non-public artifacts subject to explicit governance controls.
- **Dataset release card**: consumer-facing documentation shipped with a dataset release under
  `docs/README.md` (and optional `docs/DATASHEET.md`).
- **Golden dataset**: a governance-approved dataset entry in the golden dataset catalog, backed by
  repo governance artifacts (`golden_dataset_card`, `golden_dataset_approvals`,
  `golden_dataset_catalog`).
- **Golden catalog entry** (recommended): a single catalog item representing an approved dataset;
  may reference one or more dataset releases that implement the approved dataset.

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
     - `detections/detections.jsonl` instances identify matched events via `matched_event_ids[]`
       which reference `metadata.event_id`.
     - Dataset releases that include detection-derived labels MUST emit a deterministic join bridge
       under `views/labels/` that maps `(run_id, metadata.event_id) <-> (run_id, raw_ref)` so
       consumers can join detections through the raw_ref-first event join policy.
     - run-level scoring summaries join via `run_id`.

1. **Normalization assistance (FT0 + FT1 only)**

   - Inputs: raw event stores (when present) plus normalized OCSF store.
   - Label target: FT0 + FT1 OCSF fields only (see `055_ocsf_field_tiers.md`).
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
  - Variant disambiguation (v0.1, normative): when producing both feature variants, producers MUST
    encode the feature variant into `dataset_version` so outputs do not collide on disk (see
    "Variant-aware output layout").
  - Recommended encoding uses SemVer build metadata:
    - `+marker-assisted` for `marker_assisted`
    - `+marker-blind` for `marker_blind`
- `dataset_release_id` (content hash identifier) computed deterministically from the dataset
  manifest hash basis (see below).

### Dataset release posture

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
  - When included, quarantined/unredacted bytes MUST be written under the dedicated dataset-release
    subtree `unredacted/runs/<run_id>/...` and MUST NOT appear under any `views/**` subtree.
  - The `unredacted/**` subtree MUST be excluded from `security/checksums.txt` (and therefore from
    `security/signature.ed25519` when signing is enabled).    
  - Internal releases MUST include a prominent "NOT FOR TRAINING WITHOUT GOVERNANCE REVIEW" notice
    in the dataset release card (`docs/README.md`).

## Source artifacts and prerequisites

### Run inclusion requirements (v0.1)

For a run to be eligible for inclusion in a dataset release, it MUST:

- have a readable `runs/<run_id>/manifest.json` that passes contract validation,
- NOT be actively written (the run MUST NOT have an active run lock file at
  `runs/.locks/<run_id>.lock`, per ADR-0004),
- pass run bundle contract validation for all artifacts that the dataset release claims to include,
- include `ground_truth.jsonl` (for technique/phase labels), and
- include a normalized OCSF event store when any task uses normalized events as features:
  - `normalized/ocsf_events/` (Parquet dataset dir, includes `_schema.json`), or
  - `normalized/ocsf_events.jsonl` (JSONL envelope; used as transcode input when Parquet is absent)

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
  - `runs/<run_id>/normalized/ocsf_events.jsonl` (JSONL envelope; used as transcode input when
    Parquet is absent)
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
   - MUST NOT include label-bearing artifacts (ground truth, detections, scoring summaries).
   - MUST NOT include provenance-only descriptive context (see below).
   - MUST contain only `present` artifacts (no placeholders).
   - MUST retain join keys needed to re-attach labels:
     - `run_id`,
     - `metadata.event_id` (required for determinism and detection joins),
     - `metadata.extensions.purple_axiom.raw_ref` (required For IT1 and IT2 events; MUST be
       null for Tier 3 events).

1. **labels view**

   - Contains label-bearing artifacts only.
   - MUST contain only `present` artifacts (no placeholders).
   - MUST include at minimum:
     - `ground_truth.jsonl`
   - MUST include the event join bridge when any included label source is keyed by
     `metadata.event_id` (for example, detections).
   - MAY include:
     - detection outputs (`detections/…`)
     - scoring outputs (`scoring/…`)
     - derived, structured label tables that carry only machine labels plus join keys (no
       descriptive context).

1. **provenance view** (optional but recommended)

   - Contains run manifests and version pins used to support reproducibility auditing.
   - MAY include provenance-only descriptive context (scenario names, descriptions, narrative text,
     rich reports, operator notes).
   - MUST be the only view that contains provenance-only descriptive context for dataset releases
     intended for ML tasks.

### Provenance-only descriptive context boundary (normative)

Provenance-only descriptive context is any human-readable scenario metadata or narrative material
that can leak labels or make ML tasks trivial. Examples include:

- scenario name/title, scenario description, narrative text, operator notes
- rich report narrative, HTML reports, Markdown narratives
- human-readable command summaries or transcripts intended for operator review

Rules:

- `views/features/` MUST NOT contain provenance-only descriptive context.
- `views/labels/` MUST NOT contain provenance-only descriptive context.
- `views/provenance/` MAY contain provenance-only descriptive context.

Enforcement (dataset builder):

- View manifests MUST exclude provenance-only artifacts from `views/features/` and `views/labels/`
  via `includes[]` and `excludes[]` patterns (fail closed on misconfiguration).
- Derived label tables written under `views/labels/` MUST be schema-limited to join keys and machine
  labels, and MUST NOT include scenario names, descriptions, narratives, or free-form text.
- The dataset build MUST validate the staged output and fail closed if any prohibited descriptive
  artifacts are present under `views/features/` or `views/labels/`.

### Artifact handling boundary (normative)

Dataset releases MUST treat non-`present` artifact handling as an audit-only concern. Handling
values (`present | withheld | quarantined | absent`) MUST be recorded in `dataset_manifest.json` for
each input run.

Rules:

- `views/features/**` MUST contain only artifacts whose effective handling is `present`.
- `views/labels/**` MUST contain only artifacts whose effective handling is `present`.
- `views/provenance/**` MAY contain deterministic placeholder artifacts (for `withheld` or `absent`)
  for auditability.
- `views/provenance/**` MUST NOT contain quarantined/unredacted byte copies.
- Quarantined/unredacted byte copies MAY be included only when `release_posture="internal"` and the
  corresponding operator intent gates permit it, and then only under:
  - `unredacted/runs/<run_id>/...` (dataset-release-root relative).
- For `release_posture != "internal"`, the dataset release MUST NOT contain any `unredacted/**`
  subtree content (fail closed).
- If a selected task would require including any non-`present` artifact under `views/features/**` or
  `views/labels/**`, the builder MUST either:
  - skip that run (only when explicitly configured to allow skipping), or
  - fail closed.

### Strip and re-apply labels contract

- A consumer MUST be able to remove the `views/labels/` subtree from a dataset release and still
  load the `views/features/` view without errors.
- A consumer MUST be able to re-attach labels deterministically using:
  - `run_id` joins for run-level labels (v0.1 technique labels), and
  - event-level joins under the dataset release event join policy (v0.1 default: `dual_key_v1`):
    - Primary: `(run_id, metadata.extensions.purple_axiom.raw_ref)` when `raw_ref != null` (IT1
      and IT2 events).
    - Fallback (IT3 only): `(run_id, metadata.event_id)` when `raw_ref == null
- Any label-bearing artifact included under `views/labels/` MUST either:
  - carry the required join keys as fields (`run_id` and either `raw_ref` or `metadata.event_id`
    depending on scope), or
  - be accompanied by the deterministic event join bridge specified below, which maps
    `(run_id, metadata.event_id) <-> (run_id, raw_ref)` for consumer joins.
- Dataset builds that include detection-derived labels (from `detections/…`) MUST emit the event
  join bridge, because detections reference `matched_event_ids[]` (`metadata.event_id`) rather than
  `raw_ref`.

### Event join keys and join bridge (normative)

Event identity fields:

- `metadata.event_id`: stable event identifier (string).
- `metadata.extensions.purple_axiom.raw_ref`: canonical raw-origin pointer (object or null).
  - IT1 and IT2 events: `raw_ref` MUST be non-null.
  - IT3 events: `raw_ref` MUST be null.

Event join policy (v0.1 default):

- `event_joins.policy = "dual_key_v1"`:
  - Primary join: `(run_id, raw_ref)` when `raw_ref != null`.
  - Fallback join (IT3 only): `(run_id, metadata.event_id)` when `raw_ref == null`.

raw_ref canonicalization for joins:

- Dataset releases MUST define a canonical digest for raw_ref:
  - `raw_ref_sha256 = "sha256:" + sha256_hex(canonical_json_bytes(raw_ref_norm))`
- `raw_ref_norm` is the raw_ref object with:
  - required keys: `kind`, `path`
  - optional keys included only when non-null: `cursor`, `row_locator`
- `canonical_json_bytes(...)` MUST follow the canonical JSON rules in `025_data_contracts.md`.
- Consumers SHOULD join on `(run_id, raw_ref_sha256)` rather than engine-specific struct equality.

Detections join bridge (required when `detections/…` are included):

- Motivation: detection instances reference `matched_event_ids[]` (`metadata.event_id`), but dataset
  releases prefer raw_ref for event-level joins.
- For each included run, the dataset release MUST emit:
  - Path: `views/labels/runs/<run_id>/joins/event_id_raw_ref_bridge/`
  - Files:
    - `_schema.json`
    - Parquet dataset files (v0.1: a single `part-0000.parquet`)
- Join bridge schema (v0.1):
  - `run_id` (string, required)
  - `event_id` (string, required; equals `metadata.event_id`)
  - `identity_tier` (int, required; 1|2|3)
  - `raw_ref_sha256` (string, nullable; digest string)
  - `raw_ref_jcs` (string, nullable; canonical JSON string of `raw_ref_norm`)
- Derivation:
  - One row per normalized event in the features event store for that run.
  - For IT1 and IT2:
    - `raw_ref_sha256` and `raw_ref_jcs` MUST be non-null.
  - For IT3:
    - `raw_ref_sha256` and `raw_ref_jcs` MUST be null.
- Deterministic ordering:
  - Before writing Parquet, rows MUST be sorted by:
    1. `run_id` ascending (bytewise UTF-8)
    1. `raw_ref_sha256` ascending with nulls last
    1. `event_id` ascending
- Parquet writer constraints (normative):
  - The join bridge Parquet dataset MUST be written using the deterministic Parquet writer rules in
    `045_storage_formats.md`.
- Uniqueness (fail closed):
  - For IT1 and IT2 events: `(run_id, raw_ref_sha256)` MUST be unique.
  - For IT3 events under `dual_key_v1`: `(run_id, event_id)` MUST be unique.
- Consumer join guidance:
  - event_id to raw_ref:
    - Join detections on `(run_id, event_id)` to the bridge, then join features on
      `(run_id, raw_ref_sha256)` when present, otherwise fall back to `(run_id, event_id)` (Tier 3).
  - raw_ref to event_id:
    - Consumers MAY join on `(run_id, raw_ref_sha256)` to recover `event_id` when needed.

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

Therefore dataset build tooling MUST produce two feature-variant dataset releases for each build
invocation:

1. **marker-assisted** (audit / debugging)

   - Marker fields MAY be present in feature artifacts.

1. **marker-blind** (default for ML)

   - Marker fields MUST be removed from all feature artifacts (both the canonical marker string and
     the derived token).
   - For Parquet feature stores, marker-blind MUST be implemented by rewriting Parquet datasets,
     dropping the marker columns, and (when a `raw_json` column is present) rewriting `raw_json` so
     marker fields are stripped before canonical JSON serialization (see "Normalized OCSF feature
     store materialization").
   - Removing marker fields MUST NOT change `metadata.extensions.purple_axiom.raw_ref` values
     (raw_ref participates in event joins For IT1 and IT2 events).
   - Marker fields MUST still be retained in labels/provenance artifacts when present in ground
     truth, so auditors can confirm end-to-end attribution.

Variant declaration and identity (normative):

- Each dataset release MUST declare the selected variant in `dataset_manifest.json` (see manifest
  schema).
- For paired builds, the two releases MUST use variant-disambiguated `dataset_version` values (see
  "Variant-aware output layout") so marker-assisted and marker-blind outputs do not collide on disk.
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

#### Variant-aware `dataset_version` encoding (normative; v0.1)

Dataset build tooling MUST avoid filesystem output collisions between `marker_assisted` and
`marker_blind` releases produced from the same inputs and build configuration.

For v0.1, builders MUST disambiguate feature variants by encoding the selected variant into
`dataset_version` using SemVer build metadata (ADR-0001 SemVer rules apply).

Normative requirements:

- Builders MUST derive the on-disk `<dataset_version>` directory name by appending exactly one
  variant build-metadata suffix to a base SemVer version `V`:
  - `build.features_variant = "marker_assisted"` MUST map to
    `dataset_version = V + "+marker-assisted"`.
  - `build.features_variant = "marker_blind"` MUST map to `dataset_version = V + "+marker-blind"`.
- The `<dataset_version>` string above MUST be used verbatim in all output locations, including:
  - `<workspace_root>/exports/datasets/<dataset_id>/<dataset_version>/`
  - `<workspace_root>/exports/.staging/datasets/<dataset_id>/<dataset_version>/`
- `dataset_manifest.json.dataset_version` MUST equal the exact `<dataset_version>` directory name
  (byte-for-byte).
- If `build.features_variant` is present but the computed `dataset_version` does not match the
  required mapping above, the builder MUST fail closed (do not publish any output).

Example paired outputs for base version `1.2.3`:

- `exports/datasets/<dataset_id>/1.2.3+marker-assisted/`
- `exports/datasets/<dataset_id>/1.2.3+marker-blind/`

Consumer note (normative):

- Because SemVer build metadata does not affect precedence ordering, consumers MUST treat
  `<dataset_version>` directory names as exact identifiers. Consumers MUST NOT use SemVer precedence
  rules to order or "pick the latest" across different feature variants.

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
    - `README.md` (dataset release card)
    - `DATASHEET.md` (dataset datasheet; see below)
    - `CHANGELOG.md` (optional)
  - `security/`
    - `checksums.txt`
    - `signature.ed25519` (optional)
    - `public_key.ed25519` (optional)
  - `unredacted/` (optional; internal posture only; excluded from checksums/signing)
    - `runs/<run_id>/...` (quarantined/unredacted byte copies)
    
### Slice rules (normative)

#### Transform policy (normative)

Builders MUST copy included source artifacts byte-for-byte unless a transform is explicitly mandated
by this spec.

Mandated transforms (v0.1):

- JSONL -> Parquet transcode for normalized OCSF events when the source run lacks a Parquet dataset.
- marker-blind Parquet rewrite for normalized OCSF events to drop synthetic correlation marker
  fields (including rewriting `raw_json` when present so marker fields are removed prior to
  serialization).

Builders MUST NOT apply any other transformation (including JSON reserialization, Parquet
recompression, partition reshaping, or file renaming) unless this spec is updated to require it.

For each included run:

- `views/features/runs/<run_id>/` MUST contain:

  - `normalized/ocsf_events/` (Parquet dataset directory) when normalized features are in scope.
    - The dataset release MUST NOT contain JSONL normalized event stores under `views/features/`.
    - The builder MUST materialize this dataset per "Normalized OCSF feature store materialization"
      below:
      - byte-for-byte copy when the source run provides Parquet, otherwise deterministic JSONL ->
        Parquet transcode, and
      - (marker-blind) deterministic Parquet rewrite to drop marker fields.
  - and MAY contain raw stores (e.g., `raw_parquet/…`) only when the release posture permits it.

- `views/labels/runs/<run_id>/` MUST contain:

  - `ground_truth.jsonl`,
  - `joins/event_id_raw_ref_bridge/` when any included label source is keyed by `metadata.event_id`
    (for example, detections),
  - and MAY contain `detections/…`, `scoring/…`, `criteria/…` when the dataset build includes those
    tasks.

- `views/provenance/runs/<run_id>/` MAY contain:

  - `manifest.json`,
  - pinned pack manifests/snapshots if present in the run bundle,
  - reporting artifacts and other human-readable descriptive context used for auditing (for example,
    `report/…` and scenario metadata snapshots),
  - but MUST NOT contain quarantined/unredacted byte copies (those MAY appear only under
    `unredacted/**` when `release_posture="internal"` and operator intent gates permit it).

#### Normalized OCSF feature store materialization (normative)

This section defines how the builder produces the Parquet feature event store under:

- `views/features/runs/<run_id>/normalized/ocsf_events/`

##### Source representation resolution (per run; normative)

The builder MUST resolve the normalized OCSF source representation in this order:

1. If `runs/<run_id>/normalized/ocsf_events/` exists and contains one or more `*.parquet` files, the
   builder MUST treat it as the preferred source representation.
1. Else if `runs/<run_id>/normalized/ocsf_events.jsonl` exists, the builder MUST treat it as the
   transcode source representation.
1. Else the build MUST fail closed.

If both Parquet and JSONL representations are present in the source run, the builder MUST prefer
Parquet to avoid unnecessary transforms and to preserve source bytes. JSONL MAY be used for optional
consistency checks but MUST NOT override the Parquet selection.

##### JSONL -> Parquet transcode (required when Parquet is absent; normative)

Input:

- `runs/<run_id>/normalized/ocsf_events.jsonl`

Output:

- `views/features/runs/<run_id>/normalized/ocsf_events/` (Parquet dataset directory)
  - MUST contain one or more deterministic `part-*.parquet` files
  - MUST contain `_schema.json`

Validation (fail closed):

- Each JSONL line MUST parse as a JSON object.
- Each object MUST include `time` and `metadata.event_id`.
- `metadata.event_id` MUST be unique within the transcode input for the run.

Row ordering (normative):

- Rows MUST be sorted by `time` ascending, then `metadata.event_id` ascending (bytewise UTF-8) prior
  to write (see `045_storage_formats.md` deterministic writing requirements).

Schema projection (v0.1 minimum; normative):

- The output Parquet dataset MUST include at minimum the required columns defined in
  `045_storage_formats.md` for `normalized/ocsf_events/`.
- The builder MUST include `raw_json` (string) containing the canonical JSON serialization of the
  full event object after applying any feature-variant field stripping required by this spec (in
  particular: marker-blind stripping of the synthetic correlation marker fields), per
  `025_data_contracts.md` canonical JSON requirements, to preserve payload without requiring full
  columnization.
- Additional columns are OPTIONAL. If present, they MUST use canonical dotted paths, MUST be
  nullable-by-default when newly introduced, and MUST have type stability within the dataset for the
  run.

Writer constraints (normative):

- Transcode outputs MUST conform to the deterministic Parquet writer rules in
  `045_storage_formats.md`, including stable sort order and deterministic filenames.

Schema snapshot (normative):

- `_schema.json` MUST be generated deterministically from the output columns and MUST follow the
  ordering and content constraints in `045_storage_formats.md`.

##### marker-blind Parquet rewrite (required; normative)

marker-blind MUST be produced by rewriting the marker-assisted-equivalent Parquet dataset for the
run and dropping the marker columns:

- `metadata.extensions.purple_axiom.synthetic_correlation_marker`
- `metadata.extensions.purple_axiom.synthetic_correlation_marker_token`

Requirements (normative):

- Marker columns MUST be absent from the output schema (not present with null values).
- If a `raw_json` (string) column is present in the source dataset, the rewrite MUST also rewrite
  `raw_json` such that marker fields are removed from the serialized JSON:
  - Each `raw_json` value MUST parse as a JSON object (fail closed if parsing fails).
  - The rewrite MUST remove (when present) the following keys from the parsed object:
    - `metadata.extensions.purple_axiom.synthetic_correlation_marker`
    - `metadata.extensions.purple_axiom.synthetic_correlation_marker_token`
  - The rewritten `raw_json` value MUST equal the UTF-8 string rendering of
    `canonical_json_bytes(marker_stripped_object)` (per `025_data_contracts.md`). 
- The rewrite MUST NOT change `metadata.event_id` values.
- The rewrite MUST preserve deterministic ordering and deterministic filenames per
  `045_storage_formats.md`.
- `_schema.json` MUST be updated deterministically to reflect the dropped columns.

## Dataset manifest

### Manifest file name

- The dataset release MUST include `dataset_manifest.json` at its root.

Contract binding (normative):

- `dataset_manifest.json` MUST be validated as a contract-backed workspace export artifact with
  `contract_id = "dataset_manifest"` (schema_version `"pa:dataset_manifest:v1"`).
- Tooling MUST validate `dataset_manifest.json` using the workspace contract registry in
  `json_document` mode (fail closed on validation errors).

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
- `event_joins`:
  - `policy`: `"dual_key_v1" | "restrictive_v1"` (v0.1 default: `"dual_key_v1"`)
  - `raw_ref_c14n_version`: `"pa:raw_ref_c14n:v1"`
  - `event_id_raw_ref_bridge_path_suffix`: `"joins/event_id_raw_ref_bridge/"`
  - `event_id_raw_ref_bridge_schema_version`: `"pa:event_id_raw_ref_bridge:v1"`
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
- `views[]`: array of view entries (see "View entry" below), sorted by `view_id` ascending (bytewise
  UTF-8)
- `splits`:
  - `split_config_path`: `"splits/split_config.json"`
  - `split_assignments_path`: `"splits/split_assignments.jsonl"`
- `security`:
  - `checksums_path`: `"security/checksums.txt"`
  - `signature_path`: optional
  - `public_key_path`: optional

Digest fields (normative):

- Any field name ending in `_sha256` MUST use the canonical digest string form
  `sha256:<lowercase_hex>` and MUST match `^sha256:[0-9a-f]{64}$`.
- Unless a field explicitly states a different basis, `*_sha256` values MUST be computed over exact
  file bytes (`sha256(file_bytes)`) and then serialized in canonical form.
- If a field’s basis is canonical JSON bytes (for example `build.config_hash_sha256`), the field
  definition MUST say so explicitly.

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
  - Path constraints (normative):
    - MUST be dataset-release-root relative (MUST NOT start with `/`).
    - MUST use POSIX separators (`/`) and MUST NOT contain backslashes (`\`).
    - MUST NOT contain `..` segments.
    - MUST NOT contain empty segments (`//`).
- `includes[]`: array of strings
  - Sorted and de-duplicated array of dataset-release-root relative POSIX paths or `glob_v1`
    patterns included in the view.
  - Each entry MUST be a valid `glob_v1` pattern over dataset-release-root relative candidate paths
    (fail closed on invalid patterns).
  - Each entry MUST obey the same path constraints as `root_path` (no leading `/`, no `..`, no `//`,
    no `\`).
- `excludes[]`: array of strings (optional)
  - Sorted and de-duplicated array of dataset-release-root relative POSIX paths or `glob_v1`
    patterns excluded from the view.
  - Each entry MUST be a valid `glob_v1` pattern over dataset-release-root relative candidate paths
    (fail closed on invalid patterns).
  - Each entry MUST obey the same path constraints as `root_path` (no leading `/`, no `..`, no `//`,
    no `\`).

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
- `event_joins`:
  - `policy`
  - `raw_ref_c14n_version`
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

Contract binding (normative):

- `splits/split_config.json` MUST be validated as a contract-backed workspace export artifact with
  `contract_id = "dataset_splits_config"` (schema_version `"pa:dataset_splits_config:v1"`).
- Tooling MUST validate `splits/split_config.json` using the workspace contract registry in
  `json_document` mode (fail closed on validation errors).

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

Contract binding (normative):

- `splits/split_assignments.jsonl` MUST be validated as a contract-backed workspace export artifact
  with `contract_id = "dataset_split_assignment"` (schema_version
  `"pa:dataset_split_assignment:v1"`).
- Tooling MUST validate `splits/split_assignments.jsonl` using the workspace contract registry in
  `jsonl_lines` mode (fail closed on validation errors).

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
- never include any `unredacted/**` subtree content (quarantined/unredacted artifacts),
- include the dataset release card (`docs/README.md`) with:
  - clear licensing,
  - composition and provenance notes,
  - leakage caveats (marker, scenario metadata),
  - intended tasks and limitations.

(Reference: Hugging Face dataset cards and metadata conventions.)

## Dataset release documentation requirements

A dataset release MUST include:

1. `docs/README.md` (dataset release card)

   - Audience: dataset consumers.
   - Must include: intended tasks, how to load, how to use views, and leakage cautions.

1. `docs/DATASHEET.md` (dataset release datasheet)

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

- takes a fixed set of small run bundles as input (stored as test fixtures), including at minimum:
  - one JSONL-only normalized-store run (no `normalized/ocsf_events/`, has
    `normalized/ocsf_events.jsonl`) to force JSONL -> Parquet transcode,
  - one Parquet normalized-store run (has `normalized/ocsf_events/` and `_schema.json`) to exercise
    byte-for-byte copy (marker-assisted) and deterministic rewrite (marker-blind),
  - one run that contains both Parquet and JSONL representations to assert the "prefer Parquet"
    selection rule,
- emits paired dataset releases under
  `<workspace_root>/exports/datasets/<dataset_id>/<dataset_version>/` (within a temporary workspace
  root created for the fixture):
  - marker-assisted: `<dataset_version> = V + "+marker-assisted"`
  - marker-blind: `<dataset_version> = V + "+marker-blind"`
- does not create or modify any files under the input run bundles (`runs/<run_id>/` is treated as
  read-only input; validate via a before/after tree snapshot or hashes),
- writes only within the reserved export namespaces used by dataset builds:
  - `exports/datasets/**` (final output)
  - `exports/.staging/datasets/**` (staging; when enabled),
- validates:
  1. workspace contract validation (registry-driven) for each produced dataset release directory:

     - `dataset_manifest.json` (validation_mode `json_document`)
     - `splits/split_config.json` (validation_mode `json_document`)
     - `splits/split_assignments.jsonl` (validation_mode `jsonl_lines`)

  1. `dataset_manifest.json` and `splits/split_config.json` deterministic ordering,

  1. `dataset_release_id` reproducibility,

  1. `splits/split_assignments.jsonl` reproducibility,

  1. label stripping and re-attachment:

     - deleting `views/labels/` still allows loading features,
     - join keys exist in features and labels:
       - `run_id`
       - `metadata.event_id`
       - `metadata.extensions.purple_axiom.raw_ref` present For IT1 and IT2 events and null
         for Tier 3,
     - event-level re-attachment works under the declared `event_joins.policy`:
       - Tier 1 and Tier 2 join on `(run_id, raw_ref)`,
       - Tier 3 behavior matches the policy (v0.1 default: fallback join on
         `(run_id, metadata.event_id)`),
     - detection-derived labels can be joined deterministically via the event join bridge under
       `views/labels/`,

  1. provenance-only leakage boundary:

     - prohibited descriptive artifacts are not present under `views/features/` or `views/labels/`,
     - descriptive scenario metadata (when present) appears only under `views/provenance/`,

  1. marker-blind behavior:

     - marker absent from features in marker-blind mode,
     - `metadata.event_id` values unchanged vs marker-assisted mode,
     - `metadata.extensions.purple_axiom.raw_ref` values unchanged vs marker-assisted mode,

  1. integrity artifacts:

     - `security/checksums.txt` exists and matches the required line format and ordering,
     - `security/checksums.txt` does not include any `unredacted/**` subtree paths,

  1. (when staging is enabled) publish-gate hygiene:

     - final output does not contain `.staging/` content.

### Failure modes (normative)

Dataset build MUST fail closed (non-zero exit) for:

- missing required artifacts for declared tasks (unless explicitly configured to skip),
- presence of any `unredacted/**` subtree content when `release_posture != "internal"`,
- output collisions or unsafe publish conditions, including:
  - the final output directory already exists under `exports/datasets/`,
  - both feature variants would resolve to the same `<dataset_id>/<dataset_version>/` path,
  - staged output cannot be atomically promoted without overwriting existing files,
- non-deterministic outputs detected by self-checks (e.g., manifest reorder instability),
- normalized OCSF feature store materialization failures, including:
  - neither `normalized/ocsf_events/` nor `normalized/ocsf_events.jsonl` exists for a required run,
  - selected Parquet source is missing `_schema.json` or has no Parquet part files,
  - JSONL parse failures or missing required fields (`time`, `metadata.event_id`) during transcode,
  - duplicate `metadata.event_id` detected during transcode,
  - marker-blind rewrite leaves marker columns present, leaves marker fields present in `raw_json`
    (when the `raw_json` column exists), or changes any `metadata.event_id`,
- non-deterministic outputs detected by self-checks (for example unstable Parquet filenames or
  ordering, or manifest reorder instability),
- schema validation failures for included contract-backed artifacts,
- feature variant encoding violations:
  - `dataset_version` does not encode the selected `build.features_variant` per "Variant-aware
    `dataset_version` encoding (normative; v0.1)",
  - `dataset_manifest.json.build.features_variant` and `dataset_manifest.json.dataset_version` are
    inconsistent,
- event join policy violations:
  - IT1 or IT2 events with `metadata.extensions.purple_axiom.raw_ref == null`,
  - IT3 events with `metadata.extensions.purple_axiom.raw_ref != null`,
  - missing required join bridge output when `detections/…` are included,
  - join bridge ordering or uniqueness violations (as specified in "Event join keys and join
    bridge"),
- artifact handling boundary violations:
  - any `withheld | quarantined | absent` placeholder artifact present under `views/features/**` or
    `views/labels/**`,
  - any quarantined/unredacted byte copies present outside `unredacted/**` (for example under
    `views/**`),    
- provenance-only leakage boundary violations:
  - any provenance-only descriptive artifacts present under `views/features/` or `views/labels/`,
  - any derived label table under `views/labels/` that includes scenario names, descriptions,
    narratives, or free-form text.

## Governance: Golden dataset catalog

This section defines governance for what is allowed to be called "golden". It is intentionally
separate from the dataset release artifact format defined above.

Governance artifacts are repository inputs (not run-derived exports) and are contract-backed in the
contract registry:

- `golden_dataset_card`
- `golden_dataset_approvals`
- `golden_dataset_catalog`

### Repository layout (normative; v0.1)

Governance artifacts MUST live under the repository root using this canonical layout:

- Catalog: `golden_datasets/catalog.json` (contract_id `golden_dataset_catalog`)
- Cards: `golden_datasets/cards/<dataset_id>.json` (contract_id `golden_dataset_card`)
- Approvals: `golden_datasets/approvals/<dataset_id>.json` (contract_id `golden_dataset_approvals`)

Where `<dataset_id>` MUST be `id_slug_v1` (ADR-0001).

Validation and join rules (normative):

- Catalog, card, and approvals records MUST agree on `dataset_id` byte-for-byte.
- Tooling MUST fail closed if any catalog-designated dataset is missing its corresponding card or
  approvals file, or if any of the three artifacts is schema-invalid.

### Governance posture definitions

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

#### Default decision rules (v0.1)

- **Share-alike (CC BY-SA / similar)** ⇒ **Gated** (to avoid accidental license propagation into
  broader artifacts).
- **Provenance unclear / underlying rights ambiguous** ⇒ **Gated** until Legal review clears
  posture.
- **PII plausible (privacy class P2+)** ⇒ **Internal** until scan + mitigations complete; may later
  move to **Gated** or **Public** depending on results and policy.
- **Code-execution evals** (e.g., HumanEval, MBPP) ⇒ allowed, but require a sandboxed evaluation
  harness (security control, not licensing).

### v0.1 catalog seed (initial)

This catalog is a governance index of approved datasets. Catalog entries are intended to reference
one or more dataset releases (export artifacts) that implement the approved dataset.

### Evidence required to mark a dataset "Golden"

A dataset is not "golden" until the following evidence artifacts exist and are linked from the
catalog entry:

1. **Golden card record** (governance artifact)

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

### Intake and validation workflow (v0.1)

1. **Candidate intake**

   - Identify candidate dataset and intended regression coverage.
   - Capture upstream canonical reference (HF dataset page or GitHub repo).

1. **License + provenance validation**

   - Record license identifier and obligations.
   - Capture upstream provenance statements (dataset card / paper / repo statement).

1. **Sensitivity classification**

   - Run PII scan + document results (especially for "naturally occurring" query datasets).
   - Tag content-risk categories relevant to distribution policy.

1. **Deterministic build**

   - Convert to canonical schema and freeze artifact hashes.
   - Store split hashes and schema fingerprint.

1. **Approvals + publication**

   - Collect signoffs; store approvals record.
   - Publish to catalog with the approved posture (public/internal/gated) and enforce access
     controls.

### TODO

- [ ] Implement authoring and CI fixture coverage for the `golden_dataset_*` governance artifacts
  (`golden_dataset_card`, `golden_dataset_approvals`, `golden_dataset_catalog`) (schema validation +
  cross-artifact invariants).
- [ ] Implement/standardize **gating controls** (ACL groups, acknowledgement/click-through, audit
  logging) for "Gated" datasets.

### Future extensions (non-normative)

- Add optional "structured triage narrative" tasks derived only from redaction-safe report fields.
- Add tactic labeling by pinning an explicit ATT&CK mapping table version as an input.
- Add multi-step attribution once multi-action plans are standard.

| Date       | Change        |
| ---------- | ------------- |
| 2026-01-23 | Initial draft |
