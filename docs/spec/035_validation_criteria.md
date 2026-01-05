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
3. Break ties by `entry_id` lexical sort.

If no entry matches, criteria evaluation emits `criteria_unavailable` for the action.

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