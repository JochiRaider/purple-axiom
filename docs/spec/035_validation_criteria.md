<!-- docs/spec/035_validation_criteria.md -->
# Validation Criteria Packs

Purple Axiom externalizes “expected telemetry” and cleanup verification expectations into **criteria packs**.

This follows the common harness pattern:

- Execution is handled by the runner (Atomic/Caldera/etc.).
- Telemetry is collected and normalized (OCSF).
- Validation criteria are evaluated against the normalized store.

Criteria packs are versioned and independently curatable so that expectation tuning does not require modifying Atomic YAML or scenario definitions.

## Goals

- Keep Atomic YAML focused on execution mechanics.
- Make expected signals explicit, diffable, and versioned.
- Support environment-specific expectations without forking upstream Atomic tests.
- Provide a deterministic basis for classifying “missing telemetry” versus downstream mapping/bridge/rule gaps.
- Treat cleanup as a first-class stage and record verification results.

## Repository layout (source of truth)

Criteria packs live in-repo under a conventional folder:

- `criteria/packs/<pack_id>/<pack_version>/manifest.json`
- `criteria/packs/<pack_id>/<pack_version>/criteria.jsonl`

Optional (non-contractual):

- `criteria/packs/<pack_id>/<pack_version>/README.md`
- `criteria/packs/<pack_id>/<pack_version>/CHANGELOG.md`

## Pack control workflow (versioning + operational ownership)

This section defines how criteria packs are **versioned**, how a specific pack is **selected** for a run,
and how pack changes are managed so operational handoff is deterministic.

### Pack identity

- `pack_id` MUST be a stable identifier for a logical criteria pack (example: `default`, `windows-enterprise`, `lab-small`).
- `pack_version` MUST be a **SemVer** string (`MAJOR.MINOR.PATCH`).
  - Pre-release identifiers MAY be used for development (`-alpha.1`), but production CI SHOULD pin only stable versions.

### Immutability and change discipline

- A released pack version (a concrete `<pack_id>/<pack_version>/` directory) MUST be treated as **immutable**:
  - Editing `criteria.jsonl` or `manifest.json` in-place for an already-released version SHOULD NOT be done.
  - Any change that affects evaluation semantics MUST produce a new `pack_version`.
- Version bumps:
  - PATCH: predicate/threshold tweaks, selector refinements, cleanup check tuning that preserves intent.
  - MINOR: additive coverage (new entries/signals), broader selector support, new optional fields.
  - MAJOR: breaking semantics (status meaning changes, operator set changes, required-field changes, widespread entry id changes).

### Selection and pinning

Determinism requirement:
- For any run that is intended to be diffable/regression-tested, the effective criteria pack MUST be pinned by:
  - `pack_id`, and
  - a concrete `pack_version`.

If `pack_version` is not provided (non-recommended):
- The implementation MUST resolve a version **deterministically** using SemVer ordering:
  1. Enumerate available `<pack_id>/<pack_version>/` directories across the configured search paths.
  2. Parse candidate versions as SemVer.
  3. Select the **highest** SemVer version.
  4. If no candidates parse as SemVer, fail closed (do not “guess” lexicographically).
  5. If the same `(pack_id, pack_version)` appears in multiple search paths, fail closed unless they are byte-identical
     (as proven by `criteria_sha256` and `manifest_sha256` matching).
- The resolved `pack_version` MUST be recorded in run provenance (manifest + report).

### Recommended source control practice (non-normative)

- The repo MAY tag pack releases (example tag pattern: `criteria/<pack_id>/v<pack_version>`).
- CI SHOULD prevent changes to existing released pack version directories.

## Run bundle snapshot

Each run snapshots the selected criteria pack into the run bundle so results remain reproducible even if the repo changes:

- `runs/<run_id>/criteria/manifest.json`
- `runs/<run_id>/criteria/criteria.jsonl`
- `runs/<run_id>/criteria/results.jsonl`

The run manifest pins the pack identity and hashes.

## Drift detection (execution definitions vs criteria expectations)

Criteria packs are intentionally decoupled from execution definitions (Atomic YAML, Caldera abilities, etc.).
That decoupling introduces a controlled failure mode: **criteria drift**.

### Definitions

- **Execution definition**: the upstream content that defines *what* the runner executed for an `(engine, technique_id, engine_test_id)`.
  - Atomic: the Atomic YAML test definition associated with the Atomic GUID.
  - Caldera: the ability definition (or operation plan material) associated with the ability ID.
- **Criteria drift**: the execution definition changed, but the criteria pack entry used for evaluation was not updated
  (or was updated against a different upstream revision).

### Required provenance fields for drift detection

To make drift detection implementable and testable without heuristic parsing:

1) Criteria pack manifest provenance (pack authoring time)
- `criteria/packs/<pack_id>/<pack_version>/manifest.json` MUST record, for each supported engine, an upstream provenance record:
  - `upstreams[]` (array), each element:
    - `engine` (string; `atomic | caldera | custom`)
    - `source_ref` (string; a stable revision identifier)
      - Examples:
        - Atomic: git commit SHA of the Atomic Red Team repo checkout used to author the pack, or a content-addressed snapshot id.
        - Caldera: git commit SHA of the Caldera content repo / abilities repo used to author the pack.
    - `source_tree_sha256` (string; sha256 over a deterministic file list + file sha256 values; see below)

Deterministic tree hash basis (normative):
- `source_tree_sha256` MUST be computed as:
  - Build `tree_basis_v1`:
    - `v: 1`
    - `engine`
    - `files[]`: sorted array of `{ path, sha256 }`
      - `path` MUST be repo-relative, normalized to `/` separators.
      - `sha256` MUST be lower-hex SHA-256 of the file bytes.
      - The `files[]` array MUST be sorted by `path` using bytewise UTF-8 lexical ordering (same ordering rules as `entry_id`).
  - `source_tree_sha256 = sha256_hex( canonical_json_bytes(tree_basis_v1) )`

2) Runner provenance (run time)
- The runner MUST record the execution-definition provenance for the engine being used, using the same structure
  (`engine`, `source_ref`, `source_tree_sha256`) in run provenance (manifest `extensions` or equivalent run metadata).

Rationale: this allows drift detection without requiring the evaluator to locate and parse upstream repos at evaluation time.

### Drift detection algorithm (normative)

Before evaluating any actions for a run, the criteria evaluator MUST compute `criteria_drift_status`:

1. Load the selected pack snapshot manifest from the run bundle.
2. Read the run’s runner-recorded provenance for the active engine.
3. Compare `(engine, source_ref, source_tree_sha256)`:
   - If all match: `criteria_drift_status = "none"`.
   - If `source_ref` differs OR `source_tree_sha256` differs: `criteria_drift_status = "detected"`.
   - If either side is missing required provenance: `criteria_drift_status = "unknown"`.

### Required behavior on drift (normative)

When `criteria_drift_status = "detected"`:
- The evaluator MUST surface drift in run outputs (report + machine-readable provenance).
- Per-action criteria evaluation MUST NOT silently claim “fail” for missing signals when drift is detected.
  Instead, actions MUST be marked as `skipped` with a drift reason recorded in a deterministic field location.

Recording drift in results (normative, minimal-impact):
- Each affected `criteria/results.jsonl` line MUST include:
  - `status: "skipped"`
  - an explanation under a deterministic extension location:
    - `extensions.criteria.drift`:
      - `status`: `"detected"`
      - `engine`
      - `expected_source_ref` / `expected_source_tree_sha256` (from pack manifest)
      - `actual_source_ref` / `actual_source_tree_sha256` (from runner provenance)

When `criteria_drift_status = "unknown"`:
- The evaluator SHOULD proceed, but MUST surface an explicit warning in run outputs.
- The evaluator MAY choose to treat this as `detected` when `validation.evaluation.fail_mode = fail_closed`.

Scoring integration (normative intent):
- Drift-related skips MUST classify as `criteria_misconfigured` (or an equivalent explicit “criteria drift” sub-reason)
  so “missing telemetry” is not incorrectly attributed when expectations were authored against different execution content.

## Matching model

Criteria entries are selected by **stable engine identifiers** recorded in ground truth.

Minimum join keys:

- `engine` (atomic | caldera | custom)
- `technique_id` (ATT&CK)
- `engine_test_id` (Atomic GUID, Caldera ability ID, or equivalent canonical ID)

Optional selectors refine specificity:

- `selectors.os` (windows | linux | macos | bsd | other)
- `selectors.roles` (match-any)
- `selectors.executor` (powershell | cmd | bash | …)

Deterministic selection:

1. Filter entries that match (engine, technique_id, engine_test_id).
2. Among matches, prefer entries with the greatest selector specificity (most selector keys present and satisfied).
3. Break ties by `entry_id` lexical sort (normative order defined below).

If no entry matches, criteria evaluation emits `criteria_unavailable` for the action.

### Tie-breaking order for `entry_id` (normative)

When multiple entries remain tied after steps (1) and (2), the evaluator MUST select the entry
with the smallest `entry_id` under the following **bytewise lexical ordering**:

1. Let `B(entry_id)` be the **UTF-8** encoding of the JSON string value of `entry_id`:
   - UTF-8 only (no BOM).
   - **Case-sensitive** (no case folding).
   - **No locale** or collation rules.
   - **No Unicode normalization** is applied (no NFC/NFD/NFKC/NFKD). The exact codepoint
     sequence in the JSON string is what is compared.
2. Compare byte sequences `B(a)` and `B(b)` lexicographically by **unsigned byte value**
   (`0x00`..`0xFF`), left to right.
3. If one byte sequence is a strict prefix of the other, the shorter sequence sorts first.

Rationale: this yields cross-language deterministic ordering without locale dependence.

Pack authoring guidance (non-normative):
- `entry_id` SHOULD be restricted to ASCII (for example `[A-Za-z0-9._/-]`) to avoid visually
  confusable identifiers and normalization surprises.

### Required conformance tests (tie-breaking)

CI MUST include at least the following fixture cases for selection determinism:

1. **Case sensitivity**
   - Two criteria entries are identical in (engine, technique_id, engine_test_id) and selector specificity,
     differing only in `entry_id`:
     - `entry_id = "A"`
     - `entry_id = "a"`
   - Expected selection: `"A"` (because `0x41 < 0x61` in UTF-8).

2. **No Unicode normalization**
   - Two criteria entries are identical in (engine, technique_id, engine_test_id) and selector specificity,
     differing only in `entry_id`:
     - `entry_id = "e\u0301"` (LATIN SMALL LETTER E + COMBINING ACUTE ACCENT)
     - `entry_id = "\u00e9"` (LATIN SMALL LETTER E WITH ACUTE)
   - Expected selection: `"e\u0301"` (because UTF-8 bytes begin with `0x65 ...` vs `0xC3 ...`).

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

Each expected signal defines a predicate over **normalized OCSF events**.

- `signal_id` (string)
- `description` (optional string)
- `predicate` (required object)
  - `class_uid` (required int)
  - `constraints` (optional array)
    - Each constraint is:
      - `field` (string; dotted path, e.g. `device.hostname` or `metadata.source_type`)
      - `op` (string; `equals | one_of | exists | contains`)
      - `value` (optional; required for `equals`, `one_of`, `contains`)
- `min_count` (optional int, default 1)
- `max_count` (optional int)
- `within_seconds` (optional int; defaults to the entry time window)

Notes:

- The predicate intentionally starts simple. The evaluator can evolve to support richer operators over time, but the MVP must be implementable without a full query language.
- Matching is performed against event-time (`time`) with respect to the ground truth action `timestamp_utc`.

### Cleanup verification model

Cleanup verification defines post-conditions that must hold after cleanup runs.

- `enabled` (optional bool, default true)
- `checks` (required array when enabled)

Each check:

- `check_id` (string)
- `type` (string)
  - `command`
  - `file_absent`
  - `process_absent`
  - `registry_absent`
  - `service_state`
- `target` (optional object; type-specific)
- `severity` (optional string; `info | warn | error`, default `error`)

MVP guidance:

- Prefer `command` checks for early implementation, because they are portable across Windows/Linux if the runner is already remote-executing commands.
- Runner MUST record check execution results and evidence references (stdout/stderr hashes, exit codes).

## Evaluation outputs

`criteria/results.jsonl` is JSON Lines; each line represents the evaluation for one executed action.

Minimum fields:

- `run_id`
- `scenario_id`
- `action_id`
- `action_key`
- `criteria_ref` (pack id/version + entry_id)
- `status` (`pass | fail | skipped`)
- `signals` (array)
  - `signal_id`
  - `status` (`pass | fail | skipped`)
  - `matched_count` (int)
  - `sample_event_ids` (optional array of `metadata.event_id`)
- `cleanup` (object)
  - `invoked` (bool)
  - `verification_status` (`pass | fail | skipped | not_applicable`)
  - `results_ref` (optional path under `runner/`)

## Design constraints

- Criteria evaluation MUST operate on the normalized OCSF store (not raw telemetry).
- Criteria results MUST be sufficient to power the “missing telemetry” classification without referencing Atomic YAML content.
- Criteria evaluation MUST be deterministic:
  - stable tie-breaking for entry selection
  - stable ordering of result arrays (`signals`, `checks`) by id
  - stable sampling (if sampling is used)