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
- Run CI MUST run detection evaluation deterministically over the BDP normalized event store and
  MUST compare outputs to a golden expected output (hash- or diff-based), failing closed on
  mismatch.
  - The exact golden output surface is owned by the CI harness (see `100_test_strategy_ci.md`).

Pinning requirement (verification hook):

- The repository MUST designate at least one pinned "CI baseline" `(baseline_id, baseline_version)`
  pair to be used by Run CI.

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

- If `normalized/ocsf_events/` (or `normalized/ocsf_events.jsonl`) and
  `normalized/mapping_profile_snapshot.json` exist in the candidate run bundle, and the snapshot is
  compatible with the run's effective version control for normalization (at minimum: `ocsf_version`
  and `mapping_profile_sha256` match), `replay` MUST begin at `detection` (skipping `normalization`
  and `validation`).
- If compatibility cannot be established (for example, `normalized/mapping_profile_snapshot.json` is
  missing), the orchestrator MUST NOT assume the normalized store is current. It MUST either:
  - execute `normalization` from `raw_parquet/**` (if present), or
  - fail closed with a deterministic `reason_code` (see `020_architecture.md`).

Observability (normative):

- The run manifest stage outcomes MUST record `normalization` and `validation` as `status="skipped"`
  with a stable `reason_code` when the fast path is taken.

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
  - Strongly RECOMMENDED for `replay` fast-path compatibility checks. If absent, consumers MUST
    treat the normalized store as lacking version-control provenance for short-circuiting.
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

#### Authoritative state representation

This state machine is derived from the filesystem (no separate state store required).

Authoritative paths:

- Published root: `<workspace_root>/exports/baselines/<baseline_id>/<baseline_version>/`
- Staging root: `<workspace_root>/exports/baselines/<baseline_id>/.staging/<baseline_version>/`
- Trash root (optional if implemented):
  `<workspace_root>/exports/baselines/.trash/<baseline_id>/<baseline_version>/`

Derivation rule (normative, ordered):

1. If the published root exists:
   - If `baseline_package_manifest.json` exists, parses, and passes manifest/path consistency checks
     (see [Listing](#listing)), state is `published`.
   - Else, state is `invalid`.
1. Else if the staging root exists, state is `staging`.
1. Else if the trash root exists (when implemented), state is `trashed`.
1. Else, state is `absent`.

#### States

| State       | Kind                | Description                                                                | Invariants (normative)                                                           | Observable signals                                        |
| ----------- | ------------------- | -------------------------------------------------------------------------- | -------------------------------------------------------------------------------- | --------------------------------------------------------- |
| `absent`    | initial             | No staged or published BDP exists for the key.                             | Neither published root nor staging root exists.                                  | Listing excludes.                                         |
| `staging`   | intermediate        | Creation is in progress or an earlier create attempt left staged contents. | Published root does not exist; staging root exists.                              | Create returns `baseline_create_in_progress` on conflict. |
| `published` | intermediate        | A complete, readable BDP exists and is eligible for listing and download.  | Published root exists and contains a manifest that is valid and path-consistent. | Listed by OI.                                             |
| `invalid`   | intermediate        | A directory exists at the published root but is not a valid BDP.           | Published root exists but manifest is missing/unreadable/invalid/inconsistent.   | SHOULD surface as `baseline_manifest_invalid`.            |
| `trashed`   | terminal (optional) | A deleted BDP retained in an internal trash location.                      | Trash root exists and published root does not exist.                             | Not listed.                                               |

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
   `<workspace_root>/exports/baselines/<baseline_id>/.staging/<baseline_version>/`
   - The staging directory MUST be empty.
     - If the staging directory exists and is non-empty, creation MUST fail (RECOMMENDED error:
       `baseline_create_in_progress`). Implementations MUST NOT delete or reuse non-empty staging
       directories automatically.
   - Creation MUST fail if the final `<baseline_root>` already exists (conflict).
1. Copy required artifacts into the staging directory under `run/`, preserving relative paths and
   bytes.
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

### Metadata updates

Implementations MAY support updating the following manifest fields in place:

- `description`
- `tags`
- `blessing`/curation fields (if implemented)

Updates MUST:

- preserve immutable identity fields (`baseline_id`, `baseline_version`, `source_run`, `profile`,
  `artifact_refs`)
- rewrite `baseline_package_manifest.json` as canonical JSON bytes
- recompute `security/checksums.txt`
- update signature if present (or remove signature if signing is not configured)
- recompute `integrity.package_tree_sha256` only if any file included in the *tree-basis selection*
  changes (see [Integrity and signing](#integrity-and-signing)). Pure metadata edits MUST NOT change
  `integrity.package_tree_sha256`.

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

## Changelog

| Date       | Change    |
| ---------- | --------- |
| 2026-01-28 | Init spec |
