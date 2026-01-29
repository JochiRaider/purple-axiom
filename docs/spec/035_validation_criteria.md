---
title: Validation criteria packs
description: Defines criteria pack structure, drift detection, matching, and cleanup verification semantics.
status: draft
---

# Validation criteria packs

Purple Axiom externalizes expected telemetry and cleanup verification expectations into criteria
packs. This decouples execution definitions from validation logic while preserving determinism and
reproducibility.

## Overview

Criteria packs define expected signals for executed actions, are versioned independently, and are
snapshotted into the run bundle for reproducibility. The evaluator performs deterministic selection,
detects drift against upstream execution definitions, and records cleanup verification outcomes with
stable reason codes.

## Goals

- Keep Atomic YAML focused on execution mechanics.
- Make expected signals explicit, diffable, and versioned.
- Support environment-specific expectations without forking upstream Atomic tests.
- Provide a deterministic basis for classifying missing telemetry versus downstream mapping or rule
  gaps.
- Treat cleanup as a first-class stage and record verification results.

### Repository layout (source of truth)

Criteria packs live in-repo under a conventional folder layout:

- `criteria/packs/<criteria_pack_id>/<criteria_pack_version>/manifest.json`
- `criteria/packs/<criteria_pack_id>/<criteria_pack_version>/criteria.jsonl`

For avoidance of doubt: `<criteria_pack_id>` and `<criteria_pack_version>` MUST match the identity
recorded inside the pack manifest (`criteria_pack_id`, `criteria_pack_version`).

Optional (non-contractual):

- `criteria/packs/<criteria_pack_id>/<criteria_pack_version>/README.md`
- `criteria/packs/<criteria_pack_id>/<criteria_pack_version>/CHANGELOG.md`

## Pack control workflow (versioning and operational ownership)

This section defines how criteria packs are versioned, how a specific pack is selected for a run,
and how pack changes are managed so operational handoff is deterministic.

### Pack identity

This document uses:

- `criteria_pack_id` and `criteria_pack_version` as the canonical names (matching
  `manifest.versions` pins per ADR-0001).

Normative requirements:

- `criteria_pack_id` MUST be a stable identifier for a logical criteria pack (examples: `default`,
  `windows-enterprise`, `lab-small`).
  - `criteria_pack_id` MUST conform to `id_slug_v1` as defined by ADR-0001.
- `criteria_pack_version` MUST be a SemVer string and MUST be compared using SemVer precedence
  rules.
  - `criteria_pack_version` MUST conform to `semver_v1` as defined by ADR-0001.
- Pre-release identifiers MAY be used for development (for example `0.3.0-alpha.1`), but production
  CI SHOULD pin only stable versions.

### Immutability and change discipline

- A released pack version (a concrete `<criteria_pack_id>/<criteria_pack_version>/` directory) MUST
  be treated as immutable.
- Editing `criteria.jsonl` or `manifest.json` in-place for an already released version SHOULD NOT be
  done.
- Any change that affects evaluation semantics MUST produce a new `criteria_pack_version`.

Version bumps:

- PATCH: predicate or threshold tweaks, selector refinements, cleanup check tuning that preserves
  intent.
- MINOR: additive coverage (new entries or signals), broader selector support, new optional fields.
- MAJOR: breaking semantics (status meaning changes, operator set changes, required-field changes,
  widespread entry id changes).

### Selection and pinning

Ownership and responsibility:

- Criteria pack resolution and snapshotting is performed by the **validation stage** (the “criteria
  evaluator”), which is the first stage that consumes criteria packs.
- The runner MUST NOT resolve criteria packs (the runner only records execution-definition
  provenance used for drift detection).

Determinism requirement:

- For any run intended to be diffable across time and across environments (CI/regression), the
  effective criteria pack MUST be pinned by `(criteria_pack_id, criteria_pack_version)` and recorded
  in the run manifest under:
  - `manifest.versions.criteria_pack_id`
  - `manifest.versions.criteria_pack_version`

Resolution algorithm (normative):

1. Let `criteria_pack_id = validation.criteria_pack.criteria_pack_id`.
1. Let `criteria_pack_version = validation.criteria_pack.criteria_pack_version` (may be omitted;
   non-recommended).
1. Let `paths[] = validation.criteria_pack.paths[]` (search order is authoritative; earlier entries
   win ties when content is identical).

Case A — pinned version provided:

- If `criteria_pack_version` is provided:
  - The resolver MUST locate exactly `criteria/packs/<criteria_pack_id>/<criteria_pack_version>/`
    under the first search path where it exists.
  - If the directory does not exist in any search path, the resolver MUST fail closed for
    CI/regression runs.

Case B — version omitted (non-recommended):

- If `criteria_pack_version` is omitted:
  1. Enumerate candidate versions under each search path in `paths[]` for
     `criteria/packs/<criteria_pack_id>/`.
  1. Parse candidate directory names as SemVer and select the highest precedence version.
  1. The resolved `(criteria_pack_id, criteria_pack_version)` MUST be recorded in run provenance
     (manifest and report).

Duplicate `(id, version)` handling (normative):

- If the same `(criteria_pack_id, criteria_pack_version)` appears in multiple search paths, the
  resolver MUST fail closed **unless** the candidates are proven identical by:
  - matching `criteria.pack_sha256` (and, for debugging, matching `criteria_sha256` and
    `manifest_sha256`) in their manifests.
- When duplicates are proven identical, the resolver MUST select the candidate from the earliest
  matching search path in `paths[]` order.

Pack validation before snapshot (normative):

- Before snapshotting, the resolver MUST validate the selected pack directory:
  - Required files exist:
    - `criteria/manifest.json`
    - `criteria/criteria.jsonl`
  - `criteria/manifest.json` MUST validate against the criteria pack manifest schema.
  - `criteria/criteria.jsonl` MUST validate line-by-line against the criteria entry schema.
  - The resolver MUST recompute `criteria_sha256`, `manifest_sha256`, and `criteria.pack_sha256` and
    MUST fail closed if any recorded hash differs from the recomputed value.
  - The `criteria_pack_id` and `criteria_pack_version` values recorded inside `manifest.json` MUST
    exactly match the selected directory identity.

Note: `criteria_sha256`, `manifest_sha256`, and `criteria.pack_sha256` are content fingerprints and
MUST NOT be used as a substitute for the version pins (`manifest.versions.criteria_pack_id` and
`manifest.versions.criteria_pack_version`).

### Recommended source control practice (non-normative)

- The repo MAY tag pack releases (example tag pattern:
  `criteria/<criteria_pack_id>/<criteria_pack_version>`).
- CI SHOULD prevent changes to existing released pack version directories.

## Run bundle snapshot

The **validation stage** MUST snapshot the selected criteria pack into the run bundle so results
remain reproducible even if the repo changes. After publish, the snapshot MUST be treated as
read-only by all downstream stages.

Snapshot paths:

- `runs/<run_id>/criteria/manifest.json`
- `runs/<run_id>/criteria/criteria.jsonl`
- `runs/<run_id>/criteria/results.jsonl`

Normative rule:

- Criteria evaluation MUST use only the run-bundle snapshot (`runs/<run_id>/criteria/**`) and MUST
  NOT read criteria pack files directly from the repository after snapshotting.

Unless a `runs/<run_id>/` prefix is explicitly included, paths in this document are run-relative.

The run manifest MUST pin the criteria pack identity using version pins under `manifest.versions.*`:

- `manifest.versions.criteria_pack_id`
- `manifest.versions.criteria_pack_version`

### Snapshot schema validation (normative)

Snapshot schema validation:

- The snapshot `criteria/manifest.json` MUST validate against the criteria pack manifest contract:
  - Contract id: `criteria_pack_manifest`
  - Schema: `docs/contracts/criteria_pack_manifest.schema.json`
- The snapshot `criteria/criteria.jsonl` MUST validate line-by-line against the criteria entry
  contract:
  - Contract id: `criteria_entry`
  - Schema: `docs/contracts/criteria_entry.schema.json`
- The snapshot `criteria/results.jsonl` MUST validate line-by-line against the criteria entry
  contract:
  - Contract id: `criteria_result`
  - Schema: `docs/contracts/criteria_result.schema.json`
- The validation stage MUST fail closed if schema validation fails for runs intended for
  CI/regression.

Snapshot file-format invariants (normative):

- `criteria/manifest.json` MUST be UTF-8 encoded JSON text.
- `criteria/criteria.jsonl` MUST be UTF-8 encoded JSON Lines text:
  - Newlines MUST be `\n` (LF).
  - The file MUST end with a trailing `\n`.
  - The file MUST NOT contain blank lines.
- `criteria/results.jsonl` MUST be UTF-8 encoded JSON Lines text:
  - Newlines MUST be `\n` (LF).
  - The file MUST end with a trailing `\n`.
  - The file MUST NOT contain blank lines.

### Criteria pack content hash fields (normative)

The following hash fields MUST be present in the snapped pack manifest (`criteria/manifest.json`)
and MUST NOT be used as a substitute for the version pins:

- `manifest_sha256`
- `criteria_sha256`
- `criteria.pack_sha256` (i.e., the JSON path `criteria` → `pack_sha256`)

Definitions (normative):

- `criteria_sha256` MUST equal `sha256_hex(canonical_criteria_jsonl_bytes(criteria.jsonl))`, where
  `canonical_criteria_jsonl_bytes` is produced by:
  1. Parse `criteria/criteria.jsonl` as JSON Lines with no blank lines (each line is one JSON
     object).
  1. For each line object, serialize using `canonical_json_bytes` (RFC 8785 JCS; UTF-8 bytes).
  1. Join serialized objects with `\n` and append a trailing `\n`.
- `manifest_sha256` MUST equal `sha256_hex(canonical_json_bytes(manifest_basis))`, where
  `manifest_basis` is the manifest JSON object with the following fields removed before
  canonicalization:
  - `manifest_sha256`
  - `criteria_sha256`
  - `criteria.pack_sha256`
- `criteria.pack_sha256` MUST equal `sha256_hex(canonical_json_bytes(pack_basis_v1))`, where:
  - `pack_basis_v1.v = 1`
  - `pack_basis_v1.criteria_pack_id = <criteria_pack_id>`
  - `pack_basis_v1.criteria_pack_version = <criteria_pack_version>`
  - `pack_basis_v1.manifest_sha256 = <manifest_sha256>`
  - `pack_basis_v1.criteria_sha256 = <criteria_sha256>`

## Drift detection (execution definitions vs criteria expectations)

Criteria packs are intentionally decoupled from execution definitions (Atomic YAML, Caldera
abilities, and similar). That decoupling introduces a controlled failure mode: criteria drift.

### Definitions

**Execution definition**: the upstream content that defines what the runner executed for an
`(engine, technique_id, engine_test_id)`.

- Atomic: the Atomic YAML test definition associated with the Atomic GUID.
- Caldera: the ability definition or operation plan material associated with the ability ID.

**Criteria drift**: the execution definition changed, but the criteria pack entry used for
evaluation was not updated (or was updated against a different upstream revision).

### Required provenance fields for drift detection

To make drift detection implementable and testable without heuristic parsing:

1. Criteria pack manifest provenance (pack authoring time).

- `criteria/packs/<criteria_pack_id>/<criteria_pack_version>/manifest.json` MUST record, for each
  supported engine, an upstream provenance record:
  - `upstreams[]` array, each element:
    - `engine` (string: `atomic`, `caldera`, `custom`)
    - `source_ref` (string; a stable revision identifier)
    - `source_tree_sha256` (string; sha256 over a deterministic file list and file sha256 values)

Examples for `source_ref`:

- Atomic: git commit SHA of the Atomic Red Team repo checkout used to author the pack, or a
  content-addressed snapshot id.
- Caldera: git commit SHA of the Caldera content repo or abilities repo used to author the pack.

Deterministic tree hash basis (normative):

- `source_tree_sha256`: deterministic tree hash of the upstream execution-definition tree used when
  authoring the criteria pack. This MUST be computed using the deterministic algorithm below when
  feasible. If this field is missing (for example due to fail-open policy), drift detection MUST
  treat the drift status as `unknown`.
- `source_tree_sha256` MUST be computed as:
  - Build `tree_basis_v1` with:
    - `v: 1`
    - `engine`
    - `files[]`
  - `files[]` MUST include one record per included file, with:
    - `path`: repo-relative path (forward slashes)
    - `sha256`: lowercase hex SHA-256 of raw file bytes
  - Sort `files[]` by `path` ascending using bytewise lexicographic order (UTF-8).
  - Compute `sha256_hex(canonical_json_bytes(tree_basis_v1))`.

### Deterministic source tree hashing algorithm (v1)

This addendum defines deterministic enumeration rules for `tree_basis_v1.files[]`, including non-git
directories and tarball distributions. It is normative for all producers of `source_tree_sha256`,
including criteria pack authoring tools (pack-time provenance) and runners (run-time provenance).

#### Definitions

- **Source tree**: a filesystem directory tree or a tar archive representing upstream execution
  definitions (Atomic, Caldera abilities, or project-local custom definitions).
- **Hash root**: the top-level directory within the source tree from which repo-relative `path`
  values are computed.
- **Repo-relative path**: a normalized, portable path string derived from the hash root.

#### Canonical JSON and hashing primitive

`source_tree_sha256` MUST use the canonical JSON and hashing requirements defined in the
[data contracts spec](025_data_contracts.md) (Canonical JSON, normative).

#### Inputs

An implementation of v1 MUST accept the following inputs:

- `engine` (string: `atomic`, `caldera`, `custom`)
- `source_kind` (string: `directory`, `tar`)
- `hash_root`
  - For `directory`: an absolute or process-relative filesystem path to a directory.
  - For `tar`: an absolute or process-relative filesystem path to a `.tar`, `.tar.gz`, or `.tgz`.
- `exclude_patterns` (optional array of strings): path patterns applied to repo-relative paths.

If `hash_root` selection is ambiguous (example: multiple plausible Caldera plugin layouts), the
implementation MUST fail closed.

#### Default hash roots by engine

**Engine `atomic`**:

- If `<hash_root>/atomics/` exists, the effective hash root MUST be `<hash_root>/atomics/`.
- Otherwise, the effective hash root MUST be `<hash_root>/`.

Rationale: Atomic distributions are commonly either the repo root containing `atomics/`, or a
tarball containing only the `atomics/` subtree.

**Engine `caldera`**:

- include only files under any detected `plugins/<plugin_name>/data/abilities/**` subtree and
  `plugins/<plugin_name>/data/payloads/**` subtree.
- repo-relative `path` values MUST be computed from the effective hash root directory passed in
  provenance (`hash_root`) and therefore SHOULD include the plugin prefix (for example
  `plugins/stockpile/data/abilities/...`).
- if the source tree is a single-plugin checkout (no `plugins/` directory), implementations MAY use
  the plugin root as `hash_root` and include `data/abilities/**` and `data/payloads/**` relative to
  it.

Rationale: abilities and payloads are both execution-definition material. Hashing only YAML
frequently misses behavior changes introduced by payload updates.

**Engine `custom`**:

- The effective hash root MUST be explicitly provided by the caller (no discovery is performed).
- Pack-time and run-time producers MUST use the same custom hash root convention for a given custom
  upstream.

Guidance: if multiple custom source roots exist, the caller SHOULD embed a stable descriptor in
`source_ref` so `(engine, source_ref, source_tree_sha256)` comparisons do not silently conflate
different roots.

#### Path normalization (normative)

For every included file, the emitted `path` string MUST be produced as follows:

1. Compute `relpath` relative to the effective hash root (or subtree prefix for tar).
1. Normalize separators to `/`.
1. Remove any leading `./`.
1. Reject any resulting path that is empty, begins with `/`, contains a NUL byte, or contains a path
   segment equal to `..`.

Encoding and ordering:

- `path` MUST be representable as Unicode and UTF-8 encodable.
- Sorting MUST use bytewise UTF-8 lexical ordering over `path.encode("utf-8")`.

#### Inclusion rules (normative)

A source tree hash in v1 includes regular files only:

- A regular file is an on-disk file or a tar entry of type regular file.
- Directories are traversed but are not themselves hashed.

File content hashing:

- For each included file, `sha256` MUST be computed over the exact file bytes.
- Implementations SHOULD stream file content and MUST NOT depend on platform text decoding.

#### Exclusion rules (normative)

Exclusions are applied to repo-relative normalized paths.

Default exclude set (applied when `exclude_patterns` is omitted):

- `**/.git/**`
- `**/.hg/**`
- `**/.svn/**`
- `**/__MACOSX/**`
- `**/.DS_Store`
- `**/Thumbs.db`

Pattern matching requirements:

- Patterns MUST be matched against `/`-separated normalized paths.
- Matching semantics MUST be deterministic and documented by the implementation.
- If an implementation provides glob semantics, it MUST support `**` for any directories.

#### Symlinks and special files (normative)

To ensure cross-platform determinism, v1 is fail-closed on non-regular file types:

- If the enumerator encounters a symlink (filesystem) or a symlink tar entry, it MUST fail closed.
- If the enumerator encounters device nodes, FIFOs, sockets, or other non-regular file types, it
  MUST fail closed.

Rationale: symlink materialization and metadata differ across platforms and extraction tools.

#### Tarball handling (normative)

For `source_kind = "tar"`, the implementation MUST NOT compute `source_tree_sha256` by hashing the
raw tarball bytes. Instead, it MUST behave as if enumerating a directory tree composed of tar
entries:

- Enumerate tar entries and treat entry names as candidate paths.
- Apply the same path normalization and exclusion rules.
- Include only regular file entries and fail closed on symlinks or special entries.
- Compute `sha256` over the extracted entry content bytes.
- Apply the same sorting and `tree_basis_v1` construction rules.

This makes `source_tree_sha256` independent of tar metadata (mtime, uid, gid) and archive entry
order.

#### Failure behavior (normative)

If any of the following occur, the implementation MUST fail closed for `source_tree_sha256`
production:

- invalid or non-UTF-8 encodable paths after normalization
- detected path traversal (`..`) or absolute paths
- any symlink or special file type encountered
- inability to read file bytes deterministically (permission error or transient read failure)
- `engine = "caldera"` and no abilities subtree can be detected

When failing closed:

- Pack-time provenance emission MUST NOT emit a `source_tree_sha256` value.
- Run-time provenance emission MUST NOT emit a `source_tree_sha256` value.
- Consumers MUST treat the corresponding drift status as `unknown` due to missing required
  provenance.

#### Conformance tests and fixtures (normative)

A conforming implementation MUST be validated using fixture-driven tests that demonstrate:

1. Stable enumeration ordering. Given the same tree contents created in different filesystem orders,
   `files[]` and `source_tree_sha256` MUST be identical.
1. Cross-platform stability. For the same fixture content, `source_tree_sha256` MUST match across
   supported platforms.
1. Exclusion determinism. Adding only excluded files MUST NOT change `source_tree_sha256`.
1. Fail-closed behavior. Introducing a symlink in an otherwise valid fixture MUST cause hashing to
   fail closed.
1. Tarball equivalence. For a tarball fixture containing only regular files, hashing via tar
   enumeration MUST equal hashing the extracted directory tree using the same effective hash root.

#### Minimal normative example (basis and expected hash)

Example tree (effective hash root is the directory containing these files):

- `a.txt` with bytes `hello\n`
- `dir/b.txt` with bytes `world\n`

Per-file SHA-256:

- `a.txt` -> `5891b5b522d5df086d0ff0b110fbd9d21bb4fc7163af34d08286a2e846f6be03`
- `dir/b.txt` -> `e258d248fda94c63753607f7c4494ee0fcbe92f1a76bfdac795c9d84101eb317`

`tree_basis_v1` (logical form):

- `v: 1`
- `engine: "custom"`
- `files` (sorted by bytewise UTF-8 path):
  - `{ path: "a.txt", sha256: <a.txt sha256> }`
  - `{ path: "dir/b.txt", sha256: <dir/b.txt sha256> }`

Expected `source_tree_sha256` for this basis (using `canonical_json_bytes` as defined in the
[data contracts spec](025_data_contracts.md)):

- `11b328fb981fdcae6f56e7007cfbb84d09e7b324abaf2788f88693600113ea4e`

#### Runner provenance (run time)

The runner MUST record execution-definition provenance for each engine used by the run in the run
manifest under `extensions.runner.execution_definitions.upstreams[]`:

- `engine`: must match the pack manifest's upstream engine
- `source_ref`: exact git SHA/tag/version or artifact digest used
- `source_tree_sha256`: tree hash of the execution definitions used (MAY be omitted if unavailable)

If the runner cannot compute `source_tree_sha256`, it MUST omit `source_tree_sha256` from its
recorded provenance. The criteria evaluator MUST then apply `validation.evaluation.fail_mode` when
interpreting drift status (see below).

### Regression comparability requirement (normative)

For regression comparisons across runs:

- The criteria pack identity pins (`criteria_pack_id`, `criteria_pack_version`) MUST match.

- The criteria pack content fingerprints MUST match:

  - `manifest_sha256`
  - `criteria_sha256`
  - `criteria.pack_sha256`

- The upstream execution-definition provenance MUST match (per-engine `source_ref` and
  `source_tree_sha256`).

- If the criteria pack identity pins or snapshot hashes are missing from run outputs, consumers MUST
  treat criteria evaluation results as not comparable for regression deltas.

- By default, baseline/current runs with differing `manifest.versions.criteria_pack_version` MUST be
  treated as not comparable. If the reporting layer supports an explicit regression policy that
  allows criteria pack version drift, such drift MUST be explicitly enabled and recorded in the
  report; otherwise, comparison MUST NOT proceed.

Verification hooks (normative):

- Fixture: criteria pack version differs baseline/current (strict default):
  - Expected: regression comparability is not comparable (recorded as `baseline_incompatible`) and
    criteria-related regression deltas are not computed (or are marked indeterminate
    deterministically).
- Fixture: criteria pack version differs baseline/current (allow-drift mode, if supported):
  - Expected: mismatch is recorded as a warning, and regression deltas MAY be computed under the
    explicit allow-drift policy.

### Drift detection algorithm (normative)

Before evaluating any actions for a run, the criteria evaluator MUST compute a drift status **per
engine** present in ground truth:

1. Load the selected pack snapshot manifest from the run bundle.
1. For each engine `E` present in `ground_truth.jsonl` actions:
   1. Read the pack manifest provenance entry for engine `E` (from the criteria pack manifest
      snapshot file `criteria/manifest.json`, field `upstreams[]`)
   1. Read the runner-recorded provenance for engine `E` (from the run manifest runner extensions).
   1. Compare `(E, source_ref, source_tree_sha256)`:
      - If all match: `criteria_drift_status[E] = "none"`.
      - If `source_ref` differs or `source_tree_sha256` differs:
        `criteria_drift_status[E] = "detected"`.
      - If either side is missing required provenance: `criteria_drift_status[E] = "unknown"`.

Interpretation of `"unknown"` (normative):

- If `validation.evaluation.fail_mode = warn_and_skip`:
  - The evaluator SHOULD proceed, but MUST surface an explicit warning in run outputs.
- If `validation.evaluation.fail_mode = fail_closed`:
  - The evaluator MUST treat `"unknown"` as a hard drift gate failure for the affected engine and
    MUST mark affected actions as skipped deterministically (see “Required behavior on drift”).

### Required behavior on drift (normative)

When `criteria_drift_status = "detected"`:

- The evaluator MUST surface drift in run outputs (report and machine-readable provenance).
- Per-action criteria evaluation MUST NOT silently claim fail for missing signals when drift is
  detected. Instead, actions MUST be marked as `skipped` with a drift reason recorded in a
  deterministic field location.
- Drift-related skips MUST NOT be reported as `missing_telemetry`. The evaluator MUST set
  `reason_code = "criteria_misconfigured"` for drift-related skipped actions so downstream reporting
  and scoring can classify the gap under the scoring layer.

Recording drift in results (normative, minimal-impact):

When drift is detected for an action’s engine:

- Each affected `criteria/results.jsonl` line MUST include:
  - `status: "skipped"`
  - `reason_code: "criteria_misconfigured"`
  - `extensions.criteria.error.error_code: "drift_detected"`
  - an explanation under `extensions.criteria.drift`:
    - `status`: `detected`
    - `engine`
    - `expected_source_ref` and `expected_source_tree_sha256` (from pack manifest)
    - `actual_source_ref` and `actual_source_tree_sha256` (from runner provenance)

When drift status is unknown for an action’s engine:

- If `validation.evaluation.fail_mode = warn_and_skip`:
  - The evaluator SHOULD proceed, but MUST include:
    - `extensions.criteria.drift.status: "unknown"`
- If `validation.evaluation.fail_mode = fail_closed`:
  - The evaluator MUST mark the action as skipped and MUST include:
    - `status: "skipped"`
    - `reason_code: "criteria_misconfigured"`
    - `extensions.criteria.error.error_code: "drift_unknown"`
    - `extensions.criteria.drift.status: "unknown"`

When `criteria_drift_status = "unknown"`:

- The evaluator SHOULD proceed but MUST surface an explicit warning in run outputs.
- The evaluator MAY choose to treat this as detected when
  `validation.evaluation.fail_mode = fail_closed`.

Scoring integration (normative intent):

- Drift-related skips MUST classify as `criteria_misconfigured` (or an explicit criteria drift
  sub-reason) so missing telemetry is not incorrectly attributed when expectations were authored
  against different execution content.

## Matching model

Criteria entries are selected by stable engine identifiers recorded in ground truth.

Minimum join keys:

- `engine` (`atomic`, `caldera`, `custom`)
- `technique_id` (ATT&CK)
- `engine_test_id` (Atomic GUID, Caldera ability ID, or equivalent canonical ID)

Optional selectors allow more specific matching without changing join keys:

- `selectors.os`: OS family (`windows`, `linux`, `macos`)
- `selectors.roles`: array of environment role tokens (example: `["domain_controller"]`,
  `["endpoint"]`)
- `selectors.executor`: optional. If present, only matches when the run/action context
  `selectors.executor` equals this value.
  - For atomic runs, the recommended vocabulary is the configured atomic executor value (e.g.,
    `invoke_atomic_red_team`, `atomic_operator`, `other`).
  - For non-atomic runs, implementations MAY use the runner type (e.g., `caldera`, `custom`) unless
    a more specific executor identifier is available.

### Selector context

Selector context is per-run and per-action evaluation metadata that is not present in the join keys.
It MUST be derived deterministically from the run manifest and ground truth.

Precedence (normative):

1. If ground truth provides `resolved_target`, derive selector context from it.
1. Otherwise, fall back to `validation.criteria_pack.entry_selectors` (config-provided defaults).

Selector keys (normative):

- `selectors.os`: the resolved target OS family.
  - Source (preferred): `ground_truth.jsonl.resolved_target.os`
  - Allowed values SHOULD align with the lab/scenario OS enum:
    `windows | linux | macos | bsd | appliance | other`
- `selectors.roles`: array of resolved target roles.
  - Source (preferred): `ground_truth.jsonl.resolved_target.role` (single value) projected into a
    one-element array.
  - Allowed values SHOULD align with the lab/scenario role enum:
    `endpoint | server | domain_controller | network | sensor | other`
- `selectors.executor`: a stable execution backend identifier used to disambiguate criteria entries
  when the same `(engine, technique_id, engine_test_id)` can be produced by different executors.
  - Source (recommended): derived from the run configuration (e.g., `runner.type` and, for atomic
    runs, `runner.atomic.executor`).

Selector matching (normative):

- String comparisons for selector values MUST be performed on lowercased values.
- `selectors.os` is satisfied iff `selectors.os == context.os`.
- `selectors.executor` is satisfied iff `selectors.executor == context.executor`.
- `selectors.roles` is satisfied iff every role token listed in `selectors.roles` is present in
  `context.roles` (treat both arrays as sets; order does not matter; duplicates ignored).
- If a selector dimension is missing in context (for example roles unknown), then selector
  satisfaction MUST evaluate to "not satisfied" for entries requiring that dimension.
- If an entry's `selectors` object contains any key other than `os`, `roles`, or `executor`, that
  entry MUST be treated as not eligible by evaluators that do not recognize the key.

Selection algorithm (normative):

1. If ground truth includes pinned `criteria_ref.criteria_entry_id`:
   - Evaluator MUST select that exact criteria entry (by `entry_id`) from the selected pack.
   - Evaluator MUST verify that the entry join keys match the ground truth join keys.
   - If the entry is missing or join keys mismatch: mark action `skipped` with
     `reason_code=criteria_misconfigured` and set
     `extensions.criteria.error.error_code=criteria_ref_invalid`.
1. Else, compute the candidate set:
   - candidates = entries in pack where join keys exactly match.
   - eligible = candidates filtered by selector satisfaction (if selectors present).
1. If `eligible` is empty:
   - If `candidates` is empty: mark action `skipped` with `reason_code=criteria_unavailable`.
   - If `candidates` is non-empty but all candidates were excluded due to unsupported selector keys:
     mark action `skipped` with `reason_code=criteria_misconfigured` and set
     `extensions.criteria.error.error_code=unsupported_selector`.
1. If exactly one eligible candidate remains: select it.
1. If multiple eligible candidates remain, prefer the greatest selector specificity:
   - specificity = count of recognized selector keys present on the entry (from
     `{os, roles, executor}`).
1. If tie remains: select the candidate whose `entry_id` sorts first by the stable ordering rule
   below.

If no entry matches, criteria evaluation emits `criteria_unavailable` for the action.

No-match behavior (normative):

- The evaluator MUST emit a `criteria/results.jsonl` row for the action with:
  - `status: "skipped"`
  - `reason_code: "criteria_unavailable"`
- `criteria_ref` MUST include selected pack identity (`criteria_pack_id`, `criteria_pack_version`),
  and `criteria_entry_id` MUST be omitted or set to JSON `null`.
- `signals` MUST be an empty array.

### Tie-breaking order for entry_id (normative)

When multiple entries remain tied after steps 1 and 2, the evaluator MUST select the entry with the
smallest `entry_id` under the following bytewise lexical ordering:

1. Let `B(entry_id)` be the UTF-8 encoding of the JSON string value of `entry_id`.
1. Compare byte sequences `B(a)` and `B(b)` lexicographically by unsigned byte value (`0x00` to
   `0xFF`), left to right.
1. If one byte sequence is a strict prefix of the other, the shorter sequence sorts first.

Rationale: this yields cross-language deterministic ordering without locale dependence.

Pack authoring guidance (non-normative):

- `entry_id` SHOULD be restricted to ASCII (for example `[A-Za-z0-9._/-]`) to avoid visually
  confusable identifiers and normalization surprises.

### Required conformance tests (tie-breaking)

CI MUST include fixture cases for selection determinism:

- **Case sensitivity**: entries differ only in `entry_id` (`A` and `a`); expected selection is `A`.
- **No Unicode normalization**: entries differ only in `entry_id` (`e\u0301` and `\u00e9`); expected
  selection is `e\u0301`.

### Required conformance tests (evaluation outcomes)

CI MUST include fixture cases that validate deterministic failure classification and stable field
locations in `criteria/results.jsonl`:

- **No matching entry**: when no criteria entry matches an executed action, the evaluator MUST emit
  `status = "skipped"`, `reason_code = "criteria_unavailable"`, `signals = []`, and MUST omit
  `criteria_ref.criteria_entry_id` or set it to JSON null.
- **Invalid predicate or unsupported operator**: when a selected criteria entry cannot be evaluated
  due to pack misconfiguration, the evaluator MUST emit `status = "skipped"` and
  `reason_domain="criteria_result"` and `reason_code = "criteria_misconfigured"` and MUST record a
  stable error token under `extensions.criteria.error.error_code`.
- These fixtures are distinct from criteria drift detection fixtures (drift detection is validated
  separately and MUST remain distinct from the above cases).

## Criteria entry model

Each line in `criteria/criteria.jsonl` is a complete criteria entry object that MUST validate
against the `criteria_entry.schema.json`.

Additional pack integrity requirements (normative):

- `entry_id` MUST be unique within a single criteria pack.
  - If duplicates are present, the evaluator MUST treat the pack as misconfigured and fail closed
    for CI/regression runs.
- Within a single criteria entry, each `expected_signals[].signal_id` MUST be unique.
  - If duplicates are present, the evaluator MUST treat the entry as misconfigured (skipped with
    `reason_code="criteria_misconfigured"` and `error_code="criteria_entry_invalid"`).

### Criteria entry (minimum fields)

- `entry_id` (string, stable within the pack)
- `engine` (string)
- `technique_id` (string)
- `engine_test_id` (string)
- `selectors` (optional object)
- `time_window` (optional object)
  - `before_seconds` (int, optional; defaults to `validation.evaluation.time_window_before_seconds`)
  - `after_seconds` (int, optional; defaults to `validation.evaluation.time_window_after_seconds`)
- `expected_signals` (required array)
- `cleanup_verification` (optional object)

### Expected signal model

Each expected signal defines a predicate over normalized OCSF events.

- `signal_id` (string)
- `description` (optional string)
- `predicate` (required object)
  - `class_uid` (required int)
  - `constraints` (optional array)
    - Each constraint is:
      - `field` (string; dotted path, for example `device.hostname` or `metadata.source_type`)
      - `op` (string: `equals`, `one_of`, `exists`, `contains`)
      - `value` (optional; required for `equals`, `one_of`, `contains`)
      - `case_sensitive` (optional bool, default true; applies to string comparisons only)
- `min_count` (optional int, default 1)
- `max_count` (optional int)
- `within_seconds` (int, optional): if present, overrides the effective `after_seconds` for this
  signal only; the effective after-window for the signal becomes `within_seconds`.

Notes:

- The predicate intentionally starts simple. The evaluator can evolve to support richer operators
  over time, but the MVP must be implementable without a full query language.
- Matching is performed against event-time (`time`) with respect to the ground truth action
  `timestamp_utc`.

#### Constraint matching semantics (normative)

Constraint matching is performed per event by evaluating all constraints in a predicate using
logical AND.

Field resolution:

- `field` MUST be resolved as a dotted path against the normalized event object.
- If the path cannot be resolved, the constraint MUST evaluate to false (including `op = exists`).

Operator semantics (minimum, normative):

- `exists`: true iff the resolved value is present and is not JSON null.
- `equals`: true iff the resolved value equals the expected `value`.
- `one_of`: true iff the resolved value equals at least one element of the expected `value` array.
- `contains`: true iff the resolved value (string) contains the expected `value` (string) as a
  substring.

Type rules (minimum, normative):

- `equals` and `one_of` MUST support comparison over JSON scalar types (string, number, boolean).
- If the resolved value is an array or object, `equals`, `one_of`, and `contains` MUST evaluate to
  false (no deep matching in v0.1). `exists` remains a presence check and is unaffected by this
  rule.
  - Implication: v0.1 defines neither list-logic nor set-logic for array-to-array comparisons. For
    example, expected `["A","B"]` MUST NOT match observed `["B","A"]` under any operator.
  - Implication: `one_of` MUST NOT treat an observed array as “any element is in expected”; it is
    strictly a scalar-to-array membership check.
- For `one_of`, the expected `value` MUST be an array of scalars; otherwise the operator MUST
  evaluate to false.
- For `equals`, the expected `value` SHOULD be a scalar. If the expected `value` is an array or
  object, the operator MUST evaluate to false.
- For `contains`, both the resolved value and expected `value` MUST be strings; otherwise the
  operator MUST evaluate to false.

#### Signal evaluation semantics (deterministic)

For evaluation, the evaluator MUST:

- Anchor all windows on the ground truth action timestamp (`timestamp_utc`) converted to epoch
  milliseconds.
- Evaluate candidate events against normalized OCSF event time (`time`, epoch milliseconds).

Effective windowing:

- Compute `before_seconds` from `entry.time_window.before_seconds` if present, else from config
  `validation.evaluation.time_window_before_seconds`.
- For each signal, compute the effective after-window:
  - If `signal.within_seconds` is present: use it.
  - Else use `entry.time_window.after_seconds` if present, else config
    `validation.evaluation.time_window_after_seconds`.

A normalized event is eligible for a signal only if:

- `event.class_uid == signal.predicate.class_uid`, and
- `event.time` is within `[t0 - before_ms, t0 + after_ms]` (inclusive), and
- all constraints evaluate to true.

Counts and verdicts:

- `matched_count` MUST be the total number of matching events for the signal.
- The signal `status` MUST be:
  - `pass` if `matched_count >= min_count` AND (if `max_count` is present)
    `matched_count <= max_count`
  - `fail` otherwise
- The action `status` MUST be:
  - `pass` if all signal statuses are `pass`
  - `fail` if any signal status is `fail`

Sampling:

- `sample_event_ids` MUST contain up to `validation.evaluation.max_sample_event_ids` event IDs from
  matching events.
  - Default: `20` (see config reference).
  - If an event lacks `metadata.event_id`, it MUST be excluded from `sample_event_ids` sampling, but
    it MUST still contribute to `matched_count` when it matches.
- The sample MUST be deterministic:
  - Collect `metadata.event_id` for all matching events where present.
  - De-duplicate event IDs (set semantics).
  - Sort event IDs ascending using bytewise lexicographic order (UTF-8).
  - Take the first N.

Case sensitivity:

- `case_sensitive` applies only when both operands are strings (for `equals`, each `one_of` element,
  and `contains`).
- If `case_sensitive` is omitted, it defaults to true.
- If `case_sensitive` is false, comparisons MUST apply Unicode default case folding
  (locale-independent) to both operands before evaluating equality or substring containment.
  Implementations MUST NOT apply Unicode normalization.

Pack authoring guidance (non-normative):

- For `selectors.os = windows`, packs SHOULD set `case_sensitive: false` when comparing Windows
  filesystem paths or registry key paths to reflect platform case-insensitivity.

Required conformance fixtures (constraint matching):

- `case_sensitive: false`: observed `c:\windows\system32\cmd.exe` MUST match expected
  `C:\Windows\System32\cmd.exe` under `op = equals`.
- `case_sensitive: true`: the same observed/expected pair MUST NOT match under `op = equals`.
- **Array resolved value**: if the resolved value is an array, `equals`, `one_of`, and `contains`
  MUST evaluate to false regardless of the expected `value`.
- **Array presence**: if the resolved value is an array and is not JSON null, `op = exists` MUST
  evaluate to true.

### Cleanup verification model

A criteria entry may optionally include a `cleanup_verification` object that declares how to verify
that cleanup reverted key side-effects.

- If `cleanup_verification.enabled=true`, the criteria entry declares cleanup verification checks
  for the runner to execute **if and only if** cleanup verification is enabled for the action by
  effective operator intent and policy/config gates.
  - `cleanup_verification.enabled=true` does **not** itself enable cleanup verification; it only
    declares what to check when verification is enabled elsewhere.
- Criteria entries MAY include a `cleanup_verification` object:
  - `enabled` (bool; declares that checks are defined for this entry)
  - `checks[]` (array of check definitions)
- When cleanup verification is enabled by operator intent and policy/config gates, the runner MUST
  write a per-action artifact at:
  - `runner/actions/<action_id>/cleanup_verification.json`
- Criteria results MUST reference this artifact by `cleanup.results_ref`.

Aggregation mapping into criteria results (normative):

- If `runner/actions/<action_id>/cleanup_verification.json` exists:
  - `cleanup.invoked = true`
  - `cleanup.results_ref = "runner/actions/<action_id>/cleanup_verification.json"`
  - `cleanup.verification_status` MUST be:
    - `success` if all check results are `pass`
    - `failed` if any check result is `fail`
    - `indeterminate` if no fails exist and at least one check result is `indeterminate`
    - `skipped` if all check results are `skipped`
- If `runner/actions/<action_id>/cleanup_verification.json` does not exist:
  - `cleanup.invoked = false`
  - `cleanup.results_ref` MUST be omitted
  - `cleanup.verification_status` MUST be:
    - `not_applicable` when the matched criteria entry has no `cleanup_verification` (or
      `enabled=false`)
    - `skipped` when the matched criteria entry declares `cleanup_verification.enabled=true` but
      verification was disabled by effective gates

#### Check type: file_absent (minimum semantics)

`file_absent` verifies that a filesystem path has no resolvable directory entry on the target system
at verification time. This mirrors common cleanup commands (`rm -f <path>`, `Remove-Item <path>`) by
treating the path itself as the artifact to remove, not the dereferenced target of a link.

Target (type-specific, required):

- `target.path` (string)
- MUST be interpreted as a literal path.
- Implementations MUST NOT perform glob expansion, environment-variable expansion, or `~` expansion.

Non-goals (normative):

- `file_absent` MUST NOT check timestamps, contents, or ACL correctness.
- `file_absent` MUST NOT attempt to prove that an unlinked POSIX file is no longer held open by a
  process. It only asserts that the directory entry at `target.path` is absent.

Per-check status (normative):

- `pass`: the path is absent (no directory entry exists at `target.path`).
- `fail`: the path is present (a directory entry exists at `target.path`, including symlinks or
  reparse points).
- `indeterminate`: the verifier cannot determine presence versus absence due to permissions, invalid
  path syntax, or other non-presence-related errors.

POSIX and Linux evaluation (normative):

- The verifier MUST evaluate existence using `lstat`-equivalent semantics (the link object counts as
  present).
- If the `lstat(target.path)`-equivalent call succeeds: `status = fail`.
- If the call fails with `ENOENT` or `ENOTDIR`: `status = pass`.
- If the call fails with `EACCES` or `EPERM`: `status = indeterminate`.
- Any other error: `status = indeterminate`.

Windows evaluation (normative):

- The verifier MUST evaluate existence using a path attribute query that observes the path entry
  itself when the path is a symbolic link, junction, or other reparse point.
- If the attribute query succeeds: `status = fail`.
- If the query fails with not found (`ERROR_FILE_NOT_FOUND` or `ERROR_PATH_NOT_FOUND`):
  `status = pass`.
- If the query fails with `ERROR_ACCESS_DENIED` (or equivalent): `status = indeterminate`.
- If the query fails due to invalid path syntax (`ERROR_INVALID_NAME`, `ERROR_BAD_PATHNAME`, or
  equivalent): `status = indeterminate`.
- Any other error: `status = indeterminate`.

Deterministic stabilization window (optional, recommended):

- `target.settle_timeout_ms` (optional int, default 0).
- If `settle_timeout_ms > 0`, the verifier SHOULD repeat the existence check on a fixed interval
  until pass or timeout.
- `target.settle_interval_ms` (optional int, default 250).
- If `settle_timeout_ms > 0`, the verifier MUST use a fixed interval and MUST report the attempt
  count deterministically: `attempts = 1 + floor(settle_timeout_ms / settle_interval_ms)`.

Required evidence recording (normative):

- If cleanup verification is executed, the runner MUST write a per-action
  `runner/actions/<action_id>/cleanup_verification.json` that includes, per check:
  - `check_id`, `type`, `target` (echoed), `status` (`pass`, `fail`, `indeterminate`, `skipped`)
  - `reason_code` (string; required for all statuses)
  - `reason_domain` (string; required when status != `passed`; MUST equal `cleanup_verification`)
  - `attempts` (int), `elapsed_ms` (int)
  - `observed_error` (string or int) when `status = indeterminate` (OS-native error code or errno)
  - `observed_kind` (optional string) when `status = fail` (implementation-defined, but stable)
- If cleanup verification is disabled by policy/config, the runner MUST NOT write this file.

When the file is written, it MUST include the check list, per-check results, timestamps, and any
captured outputs necessary to debug failures. It MUST be stable for audit and MUST be referenced by
`cleanup.results_ref` in the criteria results.

Minimum conformance fixtures (normative intent):

- Linux: a dangling symlink at `target.path` MUST yield `status = fail` (because the link entry
  exists).
- Linux: a deleted regular file at `target.path` MUST yield `status = pass`.
- Windows: an existing file at `target.path` MUST yield `status = fail`.
- Windows: an access-denied probe (directory ACL prevents attribute query) MUST yield
  `status = indeterminate`.

MVP guidance:

- Prefer `command` checks for early implementation because they are portable across Windows and
  Linux if the runner is already remote-executing commands.
- Runner MUST record check execution results and evidence references (stdout or stderr hashes, exit
  codes).

## Evaluation outputs

Minimum fields for `criteria/results.jsonl` (v0.1; one JSON object per action):

- `run_id`
- `scenario_id` (optional, if scenario is present)
- `action_id` (required)
- `template_id` (optional; v0.2+ only; stable procedure identity of action template)
- `action_key` (required; stable action join key)
- `criteria_ref` object (required; selection provenance)
- `status` (`pass` | `fail` | `skipped`)
- `reason_code` (required when `status = "skipped"`):
  - a stable, machine-readable token.
  - minimum required set is:
    - `criteria_unavailable` (no matching entry)
    - `criteria_misconfigured` (entry exists but cannot be evaluated deterministically)
  - recommended additional values (non-breaking; strongly encouraged for reporting/scoring
    fidelity):
    - `criteria_disabled` (criteria evaluation disabled by config/policy for this run or action)
    - `action_not_executed` (runner did not attempt execute; criteria evaluation not applicable)
    - `action_failed_before_evaluation` (runner attempted execute but failed before a valid
      evaluation anchor/window could be established)
- `signals[]` array:
  - MUST be an empty array (`[]`) when `status=skipped`.
  - Otherwise: one element per expected signal with `signal_id`, `status`, `matched_count`,
    `sample_event_ids[]`.
  - `signals[]` MUST be ordered by `signal_id` ascending (bytewise lexicographic order, UTF-8).
  - `sample_event_ids[]` MUST be ordered ascending (bytewise lexicographic order, UTF-8).
- `time_window` object (resolved window applied):
  - `start_time_utc`, `end_time_utc`, `before_seconds`, `after_seconds`
- `cleanup` object (optional; surfaced from runner evidence and/or ground truth):
  - `invoked` (`true`/`false`)
  - `verification_status` (`success`|`failed`|`indeterminate`|`skipped`|`not_applicable`)
  - `results_ref` (optional run-relative artifact pointer; when present, SHOULD reference
    `runner/actions/<action_id>/cleanup_verification.json`)

Optional extensions:

- `extensions.criteria`:
  - `engine`
  - `join_keys` (echoed for audit)
  - `error`: { `error_code`, `message` }
  - `drift`: { ... }
  - `selection`: { ... } (optional; helpful debugging context)

Note: pack snapshot hashes (for example `manifest_sha256` and `criteria_sha256`) are not version
pins. They MUST be recorded separately (for example in `criteria/manifest.json`) and referenced as
evidence where needed; they MUST NOT replace the version pins.

Failure classification and reason codes (normative):

- When `status = "skipped"`, the evaluator MUST set `reason_domain` and `reason_code` to a stable
  token. The minimum required set is:
  - `reason_domain` MUST equal `criteria_result`.
  - `criteria_unavailable`: no criteria entry matched the action join keys.
  - `criteria_misconfigured`: criteria evaluation cannot be trusted (example: drift detected,
    invalid predicate, unsupported operator, schema invalid).
- When `reason_code = "criteria_misconfigured"`, the evaluator SHOULD emit a stable error token at
  `extensions.criteria.error.error_code` to enable deterministic triage without exposing sensitive
  details.
  - `extensions.criteria.error.error_code` MUST be one of:
    - `unsupported_operator`
    - `invalid_predicate`
    - `schema_invalid`
    - `drift_detected`
    - `drift_unknown`
    - `criteria_ref_invalid`
- When criteria drift is detected or treated as detected (fail-closed), the evaluator MUST set
  `reason_code = "criteria_misconfigured"` and MUST record drift details under
  `extensions.criteria.drift` as specified above.

Evidence pointers for reporting (normative intent):

- Reporting/scoring conclusions that classify gaps as scoring-layer criteria issues SHOULD include
  evidence references to `criteria/manifest.json` and `criteria/results.jsonl`.
- For `criteria/results.jsonl`, report evidence references SHOULD use a selector that follows the
  evidence ref selector grammar in `025_data_contracts.md`. When referencing rows directly, prefer
  `jsonl_line:<n>` with the deterministic ordering below rather than ad-hoc row-key selectors.

Deterministic ordering (normative):

- The evaluator MUST emit `criteria/results.jsonl` rows in a deterministic order, sorted by:
  1. `scenario_id` ascending (UTF-8 byte order), treating a missing `scenario_id` as the empty
     string (`""`, which sorts before any non-empty value).
  1. `action_id` ascending (UTF-8 byte order, no locale)

## Design constraints

- Criteria evaluation MUST operate on the normalized OCSF store (not raw telemetry).
- Criteria results MUST be sufficient to power missing telemetry classification without referencing
  Atomic YAML content.
- Criteria evaluation MUST be deterministic:
  - stable tie-breaking for entry selection
  - stable row ordering for `criteria/results.jsonl` (as specified above)
  - stable ordering of result arrays (`signals`, `checks`) by id
  - stable sampling (if sampling is used)

## Cleanup verification checks: deterministic semantics (v0.1)

Cleanup verification checks MUST evaluate to a tri-state verdict: `pass`, `fail`, or
`indeterminate`. Implementations MAY additionally emit `skipped` when a check is not executed (for
example, not applicable on the platform or the verifier is disabled by policy). `skipped` is an
execution outcome, not an evaluated verdict.

### Common evaluation contract

**Verdicts**:

- Implementations MUST evaluate checks to a tri-state verdict: `pass`, `fail`, or `indeterminate`.
- Implementations MAY additionally emit `skipped` when an individual check is not executed under an
  effective policy gate (for example, a per-check allowlist/denylist decision) while cleanup
  verification overall is enabled and `cleanup_verification.json` is produced for the action.

**Indeterminate is not success**:

- Cleanup verification gating MUST treat `indeterminate` as a gate-fail by default.
- The four-state verdict is still recorded to support diagnostics and deterministic reporting.

**Reason codes**: Each check result MUST include a stable `reason_code` (even for pass) from the
following minimal set:

- `ok` (pass)
- `present` (fail; thing exists or is running)
- `absent` (pass for absence checks)
- `state_mismatch` (fail for state checks)
- `unsupported_platform` (indeterminate)
- `insufficient_privileges` (indeterminate)
- `not_found` (indeterminate; required tool or target not found)
- `timeout` (indeterminate)
- `exec_error` (indeterminate; command could not be executed or probe crashed)
- `parse_error` (indeterminate; output not interpretable deterministically)
- `ambiguous_match` (indeterminate; multiple targets match but check expects exactly one)
- `unstable_observation` (indeterminate; observation flaps across probes)
- `disabled_by_policy` (skipped; check not run by policy)

Note: This `reason_code` vocabulary is scoped to cleanup verification check results and is not a
stage outcome reason code (ADR-0005).

**Skipped requires reason_code**: If a check result status is `skipped`, it MUST include
`reason_code`, and `reason_code` MUST be one of `unsupported_platform`, `insufficient_privileges`,
`disabled_by_policy`, or `exec_error`.

Unless a check type defines a more specific mapping, absence checks MUST use `absent` (pass) and
`present` (fail). State checks MUST use `ok` (pass) and `state_mismatch` (fail).

**Deterministic stability window**: Checks that query live system state (`process_absent`,
`service_state`) MUST apply a stabilization protocol:

- `probes = 3` (fixed default)
- `probe_delays_ms = [0, 250, 1000]` (fixed default)
- Observation is collected at each probe.
- Pass is allowed only when all probes agree on pass.
- Fail is allowed only when all probes agree on fail.
- Mixed observations across probes MUST yield indeterminate with
  `reason_code = unstable_observation`.

Parsing requirement: implementations SHOULD prefer structured system APIs over localized CLI output.
When CLI output is used, it MUST be restricted to stable key-value outputs or structured output (for
example, `systemctl show`).

**Probe transcript**: Each sample MUST record a probe transcript:

- `tool` (example: `psutil`, `powershell`, `systemctl`)
- `args` (array)
- `exit_code` (if applicable)
- `stdout`, `stderr` (newlines normalized to `\n`)
- `duration_ms`
- `error` (string, if applicable)

Probe normalization rules are deterministic:

- Decode bytes as UTF-8 with replacement on decode errors.
- Normalize newlines to `\n`.
- Limit captured `stdout` and `stderr` to `max_output_bytes` (default 8192) and set
  `truncated: true` or `false`.

### process_absent

`process_absent` verifies that no running process matches a selector.

Selector (minimum). The selector is an AND across any provided fields:

- `pid` (integer, optional)
- `exe_path` (string, optional)
- `name` (string, optional)

Matching rules are deterministic:

- `name` comparison is case-insensitive on Windows and case-sensitive on Linux or macOS.
- `exe_path` MUST be path-normalized (separator normalization). Comparison is case-insensitive on
  Windows and case-sensitive on Linux or macOS.

Verdict rules per probe:

- `present` if any running process matches the selector.
- `absent` if no running process matches the selector.

Verdict and reason_code mapping using the stabilization protocol:

- Pass only if all probes observe `absent` (`reason_code = absent`).
- Fail only if all probes observe `present` (`reason_code = present`).
- Mixed observations across probes: indeterminate (`reason_code = unstable_observation`).
- If any probe cannot enumerate due to permissions: indeterminate
  (`reason_code = insufficient_privileges`).
- If required tooling is missing: indeterminate (`reason_code = not_found`).
- Any other execution failure: indeterminate (`reason_code = exec_error`).

Windows guidance (normative for determinism):

- Prefer CIM or WMI `Win32_Process` for `CommandLine` and `ExecutablePath` matching because it
  exposes these as structured properties.
- `Get-Process` alone is insufficient for deterministic command line matching because it does not
  directly expose `CommandLine`.

### registry_absent (Windows only)

`registry_absent` verifies that a registry key (and optionally a value) does not exist.

Applicability:

- On non-Windows OS, the check MUST return indeterminate (`reason_code = unsupported_platform`).

Selector:

- `hive`: `HKLM`, `HKCU`, `HKCR`, `HKU`, `HKCC`
- `key_path`: string
- `value_name`: string (optional)

Verdict rules (Windows):

- If access is denied for the key or value: indeterminate (`reason_code = insufficient_privileges`).
- If the key does not exist: pass (`reason_code = absent`).
- If `value_name` is omitted and the key exists: fail (`reason_code = present`).
- If `value_name` is provided and the key exists: value missing yields pass
  (`reason_code = absent`); value present yields fail (`reason_code = present`).

Implementation note:

- `Get-ItemProperty` is provider-agnostic and works with the Registry provider; use it (or an API
  equivalent) rather than parsing `reg.exe` output.

### service_state

`service_state` verifies runtime state and optional enablement for a service.

Expected state:

- `runtime`: `running` or `stopped` (required)
- `enabled`: `enabled` or `disabled` (optional)

Observed state model:

- `runtime`: `running`, `stopped`, `unknown`
- `enabled`: `enabled`, `disabled`, `unknown`

Verdict rules:

- If the service manager query fails due to permissions: indeterminate
  (`reason_code = insufficient_privileges`).
- If the service cannot be found: indeterminate (`reason_code = not_found`) and probe evidence MUST
  set `service_not_found: true`.
- If `expected.enabled` is not set: pass if observed runtime equals expected runtime; otherwise
  fail.
- If `expected.enabled` is set: pass only if both runtime and enabled match expectations; otherwise
  fail.

Backend selection:

- Windows: query Service Control Manager via `Get-Service` or .NET service APIs.
- Linux with systemd available: query via `systemctl show` properties (stable `Key=Value` output).
- If the platform service manager cannot be queried deterministically, return indeterminate with
  `unsupported_platform`.

State mapping rules (minimal, stable):

- Windows: `running` means `Running`; `stopped` means `Stopped`. Pending states MUST be treated as
  indeterminate `unstable_observation` unless they stabilize across probes.
- systemd: parse `ActiveState` (and optionally `SubState`). `running` means `ActiveState=active`;
  `stopped` means `ActiveState=inactive`. `failed` or unexpected values count as `state_mismatch`
  unless explicitly allowed.
- If `systemctl` reports unit not found, this MUST be treated as indeterminate
  (`reason_code = not_found`) with `service_not_found: true`.
- Stabilization protocol is REQUIRED for `service_state` (services transition asynchronously).

### command

`command` executes a command and evaluates deterministic predicates over exit code and optional
stdout matching.

Execution constraints:

- Commands MUST be executed as an argv array (no string parsing) with `shell=false` by default.
- Each execution MUST apply `timeout_ms` (default 10000) and record the effective working directory.
- Captured stdout and stderr MUST be normalized per the probe transcript rules.

Predicate (minimum):

- `argv`: list of tokens (not a shell string)
- `timeout_ms` (default 10000)
- `expect_exit_codes`: array of integers, default `[0]`
- Optional output assertions that do not require parsing localized text:
  - `stdout_contains` or `stderr_contains` (substring over normalized captured text)
  - `stdout_sha256` or `stderr_sha256` (exact match; computed over normalized captured text encoded
    as UTF-8)
  - `stdout_regex` only if regex is anchored (`^...$`) and the regex dialect is pinned by the
    implementation

Verdict rules:

- If the command cannot be executed because it is not found: indeterminate
  (`reason_code = not_found`).
- If the command times out: indeterminate (`reason_code = timeout`).
- If the exit code is not in `expect_exit_codes`: fail (`reason_code = present`).
- If exit code matches but any specified output assertion is not satisfied:
  - If the relevant stream is truncated and the assertion requires full output (`*_sha256`):
    indeterminate (`reason_code = parse_error`).
  - If the relevant stream is truncated and the assertion is `*_contains` or `stdout_regex`: pass
    only if the match is found within captured output; otherwise indeterminate
    (`reason_code = parse_error`).
  - Otherwise: fail (`reason_code = present`).
- Otherwise: pass (`reason_code = ok`).

## Appendix: Criteria pack and evaluation state machines (representational)

This appendix is representational (non-normative). Normative semantics are defined elsewhere in this
spec (selection, hashing, evaluation, and drift sections). This representation follows the guidance
for representational state machines in ADR-0007.

Authority references (normative semantics live in):

- “Selection and pinning”
- “Run bundle snapshot”
- “Signal evaluation semantics”
- “Drift detection”
- ADR-0005 (stage outcomes)
- ADR-0007 (state machine representation guidance)

### State machine: Criteria pack resolution (run-level)

States:

- `disabled`: validation criteria evaluation is disabled (`validation.enabled=false`).
- `resolving`: resolver is selecting `(criteria_pack_id, criteria_pack_version)` from configured
  inputs.
- `validating`: resolver is validating schema + hashes for the selected pack directory.
- `snapshotted`: `runs/<run_id>/criteria/{manifest.json,criteria.jsonl}` published successfully.
- `ready`: snapshot exists and is the sole input used for criteria evaluation.
- `failed`: resolution/validation/snapshot publish failed (fail_closed) or was skipped
  (warn_and_skip).

Transitions (high level):

- `disabled` → `resolving` when `validation.enabled=true`.
- `resolving` → `validating` when a candidate pack directory is selected.
- `validating` → `snapshotted` when schema + hash validation succeed.
- `snapshotted` → `ready` when snapshot publish gate completes.
- Any state → `failed` on deterministic failure (recorded as a validation stage outcome per
  ADR-0005).

### State machine: Criteria evaluation (per action)

States:

- `pending`: action exists in ground truth; criteria evaluation not yet computed.
- `selected`: a criteria entry has been selected (or selection failed deterministically).
- `evaluated_pass`: evaluation completed with `status="pass"`.
- `evaluated_fail`: evaluation completed with `status="fail"`.
- `skipped`: evaluation not performed (no matching entry, misconfiguration, drift gate, etc.).
- `recorded`: a `criteria/results.jsonl` row was emitted.

Transitions:

- `pending` → `selected` on criteria entry selection.
- `selected` → `evaluated_pass | evaluated_fail` when evaluation executes.
- `selected` → `skipped` when selection/evaluation is blocked deterministically.
- `evaluated_pass | evaluated_fail | skipped` → `recorded` when the output row is emitted.

### State machine: Cleanup verification consumption (per action)

States:

- `not_applicable`: no cleanup verification declared for the selected criteria entry.
- `disabled`: cleanup verification declared but disabled by effective gates; runner artifact absent.
- `executed_success`: runner artifact exists; all checks pass.
- `executed_failed`: runner artifact exists; at least one check fails.
- `executed_indeterminate`: runner artifact exists; no fails but at least one indeterminate.
- `executed_skipped`: runner artifact exists; all checks skipped.

Mapping to `criteria/results.jsonl.cleanup.verification_status` is defined in “Cleanup verification
structure”.

## Key decisions

- Criteria packs are versioned independently and snapshotted into the run bundle.
- Drift detection relies on deterministic provenance and source tree hashing.
- Matching is deterministic with bytewise lexical tie-breaking.
- Cleanup verification records explicit reason codes and stable probe transcripts.

## References

- [Data contracts](025_data_contracts.md)
- [ADR-0001: Project naming and versioning](../adr/ADR-0001-project-naming-and-versioning.md)
- [ADR-0002: Event identity and provenance](../adr/ADR-0002-event-identity-and-provenance.md)
- [ADR-0005: Stage outcomes and failure classification](../adr/ADR-0005-stage-outcomes-and-failure-classification.md)
- [ADR-0007: State machines](../adr/ADR-0007-state-machines.md)
- [ADR-0008: Threat intel packs](../adr/ADR-0008-threat-intel-packs.md)
- [Atomic Red Team executor integration](032_atomic_red_team_executor_integration.md)
- [Telemetry pipeline](040_telemetry_pipeline.md)
- [Configuration reference](120_config_reference.md)

## Changelog

| Date      | Change                                       |
| --------- | -------------------------------------------- |
| 1/25/2026 | update                                       |
| TBD       | Style guide migration (no technical changes) |
