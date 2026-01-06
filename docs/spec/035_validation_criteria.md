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

## Run bundle snapshot

Each run snapshots the selected criteria pack into the run bundle so results remain reproducible even if the repo changes:

- `runs/<run_id>/criteria/manifest.json`
- `runs/<run_id>/criteria/criteria.jsonl`
- `runs/<run_id>/criteria/results.jsonl`

The run manifest pins the pack identity and hashes.

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