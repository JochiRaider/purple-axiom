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

## Repository layout (source of truth)

Criteria packs live in-repo under a conventional folder:

- `criteria/packs/<pack_id>/<pack_version>/manifest.json`
- `criteria/packs/<pack_id>/<pack_version>/criteria.jsonl`

Optional (non-contractual):

- `criteria/packs/<pack_id>/<pack_version>/README.md`
- `criteria/packs/<pack_id>/<pack_version>/CHANGELOG.md`

## Pack control workflow (versioning and operational ownership)

This section defines how criteria packs are versioned, how a specific pack is selected for a run,
and how pack changes are managed so operational handoff is deterministic.

### Pack identity

- `pack_id` MUST be a stable identifier for a logical criteria pack (example: `default`,
  `windows-enterprise`, `lab-small`).
- `pack_version` MUST be a SemVer string (`MAJOR.MINOR.PATCH`).
- Pre-release identifiers MAY be used for development (`-alpha.1`), but production CI SHOULD pin
  only stable versions.

### Immutability and change discipline

- A released pack version (a concrete `<pack_id>/<pack_version>/` directory) MUST be treated as
  immutable.
- Editing `criteria.jsonl` or `manifest.json` in-place for an already released version SHOULD NOT be
  done.
- Any change that affects evaluation semantics MUST produce a new `pack_version`.

Version bumps:

- PATCH: predicate or threshold tweaks, selector refinements, cleanup check tuning that preserves
  intent.
- MINOR: additive coverage (new entries or signals), broader selector support, new optional fields.
- MAJOR: breaking semantics (status meaning changes, operator set changes, required-field changes,
  widespread entry id changes).

### Selection and pinning

Determinism requirement:

- For any run intended to be diffable or regression-tested, the effective criteria pack MUST be
  pinned by `pack_id` and a concrete `pack_version`.

If `pack_version` is not provided (non-recommended):

1. Enumerate available `<pack_id>/<pack_version>/` directories across the configured search paths.
1. Parse candidate versions as SemVer.
1. Select the highest SemVer version.
1. If no candidates parse as SemVer, fail closed (do not guess lexicographically).
1. If the same `(pack_id, pack_version)` appears in multiple search paths, fail closed unless they
   are byte-identical as proven by matching `criteria_sha256` and `manifest_sha256`.

The resolved `pack_version` MUST be recorded in run provenance (manifest and report).

### Recommended source control practice (non-normative)

- The repo MAY tag pack releases (example tag pattern: `criteria/<pack_id>/v<pack_version>`).
- CI SHOULD prevent changes to existing released pack version directories.

## Run bundle snapshot

Each run snapshots the selected criteria pack into the run bundle so results remain reproducible
even if the repo changes:

- `runs/<run_id>/criteria/manifest.json`
- `runs/<run_id>/criteria/criteria.jsonl`
- `runs/<run_id>/criteria/results.jsonl`

The run manifest pins the pack identity and hashes.

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

- `criteria/packs/<pack_id>/<pack_version>/manifest.json` MUST record, for each supported engine, an
  upstream provenance record:
  - `upstreams[]` array, each element:
    - `engine` (string: `atomic`, `caldera`, `custom`)
    - `source_ref` (string; a stable revision identifier)
    - `source_tree_sha256` (string; sha256 over a deterministic file list and file sha256 values)

Examples for `source_ref`:

- Atomic: git commit SHA of the Atomic Red Team repo checkout used to author the pack, or a
  content-addressed snapshot id.
- Caldera: git commit SHA of the Caldera content repo or abilities repo used to author the pack.

Deterministic tree hash basis (normative):

- `source_tree_sha256` MUST be computed as:
  - Build `tree_basis_v1` with `v`, `engine`, and `files[]`.
  - `files[]` is a sorted array of `{ path, sha256 }`.
  - `path` MUST be repo-relative and normalized to `/` separators.
  - `sha256` MUST be lowercase hex SHA-256 of the file bytes.
  - `files[]` MUST be sorted by `path` using bytewise UTF-8 lexical ordering.
  - `source_tree_sha256 = sha256_hex(canonical_json_bytes(tree_basis_v1))`.

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

- The effective hash scope MUST include all files under any detected `*/data/abilities/` subtree and
  all files under any detected `*/data/payloads/` subtree.
- Detection rules MUST identify directories or tar path prefixes that match
  `plugins/<plugin_name>/data/abilities/` and `plugins/<plugin_name>/data/payloads/`, or
  `data/abilities/` and `data/payloads/` for abilities-only distributions.
- If no `abilities` subtree is detected, the implementation MUST fail closed.

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

- The runner MUST record execution-definition provenance for the engine being used, using the same
  structure (`engine`, `source_ref`, `source_tree_sha256`) in run provenance (manifest `extensions`
  or equivalent run metadata).

Rationale: this allows drift detection without requiring the evaluator to locate and parse upstream
repos at evaluation time.

### Drift detection algorithm (normative)

Before evaluating any actions for a run, the criteria evaluator MUST compute
`criteria_drift_status`:

1. Load the selected pack snapshot manifest from the run bundle.
1. Read the run's runner-recorded provenance for the active engine.
1. Compare `(engine, source_ref, source_tree_sha256)`:
   - If all match: `criteria_drift_status = "none"`.
   - If `source_ref` differs or `source_tree_sha256` differs: `criteria_drift_status = "detected"`.
   - If either side is missing required provenance: `criteria_drift_status = "unknown"`.

### Required behavior on drift (normative)

When `criteria_drift_status = "detected"`:

- The evaluator MUST surface drift in run outputs (report and machine-readable provenance).
- Per-action criteria evaluation MUST NOT silently claim fail for missing signals when drift is
  detected. Instead, actions MUST be marked as `skipped` with a drift reason recorded in a
  deterministic field location.

Recording drift in results (normative, minimal-impact):

- Each affected `criteria/results.jsonl` line MUST include:
  - `status: "skipped"`
  - an explanation under `extensions.criteria.drift`:
    - `status`: `detected`
    - `engine`
    - `expected_source_ref` and `expected_source_tree_sha256` (from pack manifest)
    - `actual_source_ref` and `actual_source_tree_sha256` (from runner provenance)

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

Optional selectors refine specificity:

- `selectors.os` (`windows`, `linux`, `macos`, `bsd`, `other`)
- `selectors.roles` (match-any)
- `selectors.executor` (`powershell`, `cmd`, `bash`, and similar)

Deterministic selection:

1. Filter entries that match (engine, technique_id, engine_test_id).
1. Among matches, prefer entries with the greatest selector specificity (most selector keys present
   and satisfied).
1. Break ties by `entry_id` lexical sort (normative order defined below).

If no entry matches, criteria evaluation emits `criteria_unavailable` for the action.

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

## Criteria entry model

`criteria.jsonl` is JSON Lines; each line is one criteria entry.

### Criteria entry (minimum fields)

- `entry_id` (string, stable within the pack)
- `engine` (string)
- `technique_id` (string)
- `engine_test_id` (string)
- `selectors` (optional object)
- `time_window` (optional object)
  - `before_seconds` (optional, default 5)
  - `after_seconds` (optional, default 120)
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
- `within_seconds` (optional int; defaults to the entry time window)

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

Cleanup verification defines post-conditions that must hold after cleanup runs.

- `enabled` (optional bool, default true)
- `checks` (required array when enabled)

Each check:

- `check_id` (string)
- `type` (string: `command`, `file_absent`, `process_absent`, `registry_absent`, `service_state`)
- `target` (optional object; type-specific)
- `severity` (optional string; `info`, `warn`, `error`, default `error`)

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

- The runner MUST write a per-action `runner/actions/<action_id>/cleanup_verification.json` that
  includes, per check:
  - `check_id`, `type`, `target` (echoed), `status` (`pass`, `fail`, `indeterminate`, `skipped`)
  - `reason_code` (string; required for all statuses)
  - `attempts` (int), `elapsed_ms` (int)
  - `observed_error` (string or int) when `status = indeterminate` (OS-native error code or errno)
  - `observed_kind` (optional string) when `status = fail` (implementation-defined, but stable)

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

`criteria/results.jsonl` is JSON Lines; each line represents the evaluation for one executed action.

Minimum fields:

- `run_id`
- `scenario_id`
- `action_id` (format is versioned; see data contracts)
- `template_id` (v0.2+; stable procedure identity of the action template)
- `action_key`
- `criteria_ref` (pack id, pack version, and entry_id)
- `status` (`pass`, `fail`, `skipped`)
- `signals` (array)
  - `signal_id`
  - `status` (`pass`, `fail`, `skipped`)
  - `matched_count` (int)
  - `sample_event_ids` (optional array of `metadata.event_id`)
- `cleanup` (object)
  - `invoked` (bool)
  - `verification_status` (`pass`, `fail`, `indeterminate`, `skipped`, `not_applicable`)
  - `results_ref` (optional path under `runner/`)

## Design constraints

- Criteria evaluation MUST operate on the normalized OCSF store (not raw telemetry).
- Criteria results MUST be sufficient to power missing telemetry classification without referencing
  Atomic YAML content.
- Criteria evaluation MUST be deterministic:
  - stable tie-breaking for entry selection
  - stable ordering of result arrays (`signals`, `checks`) by id
  - stable sampling (if sampling is used)

## Cleanup verification checks: deterministic semantics (v0.1)

Cleanup verification checks MUST evaluate to a tri-state verdict: `pass`, `fail`, or
`indeterminate`. Implementations MAY additionally emit `skipped` when a check is not executed (for
example, not applicable on the platform or the verifier is disabled by policy). `skipped` is an
execution outcome, not an evaluated verdict.

### Common evaluation contract

**Verdicts**:

- `pass`: the check predicate is satisfied.
- `fail`: the predicate is violated.
- `indeterminate`: the predicate could not be evaluated with confidence (unsupported OS, missing
  permissions, missing tooling, timeout, probe error, or parse error).

**Indeterminate is not success**:

- Cleanup verification gating MUST treat `indeterminate` as a gate-fail by default.
- The tri-state verdict is still recorded to support diagnostics and deterministic reporting.

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

**Skipped requires reason_code**: If a check result status is `skipped`, it MUST include
`reason_code`, and `reason_code` MUST be one of `unsupported_platform`, `insufficient_privileges`,
or `exec_error`.

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

## Key decisions

- Criteria packs are versioned independently and snapshotted into the run bundle.
- Drift detection relies on deterministic provenance and source tree hashing.
- Matching is deterministic with bytewise lexical tie-breaking.
- Cleanup verification records explicit reason codes and stable probe transcripts.

## References

- [Data contracts spec](025_data_contracts.md)
- [ADR-0002 "Event Identity and Provenance"](../adr/ADR-0002-event-identity-and-provenance.md)
- [Telemetry pipeline spec](040_telemetry_pipeline.md)

## Changelog

| Date | Change                                       |
| ---- | -------------------------------------------- |
| TBD  | Style guide migration (no technical changes) |
