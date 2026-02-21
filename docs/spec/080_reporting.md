---
title: Reporting
description: Defines reporting artifacts, required outputs, trending keys, and human-readable report structure for run evaluation.
status: draft
category: spec
tags: [reporting, scoring, ci, trending]
related:
  - 025_data_contracts.md
  - 026_contract_spine.md
  - 055_ocsf_field_tiers.md
  - 065_sigma_to_ocsf_bridge.md
  - 070_scoring_metrics.md
  - ADR-0005-stage-outcomes-and-failure-classification.md
---

# Reporting

## Stage contract header

### Stage ID

- `stage_id`: `reporting`

### Owned output roots (published paths)

- `report/`
- `inputs/baseline_run_ref.json` (when `reporting.regression.enabled=true`)
- `inputs/baseline/manifest.json` (optional; immutable snapshot when present; when
  `reporting.regression.enabled=true`)

### Inputs/Outputs

This section is the stage-local view of:

- the stage boundary table in
  [ADR-0004](../adr/ADR-0004-deployment-architecture-and-inter-component-communication.md), and
- the contract bindings in [contract_registry.json](../contracts/contract_registry.json).

#### Contract-backed outputs

| contract_id         | path/glob                       | Required?                                           |
| ------------------- | ------------------------------- | --------------------------------------------------- |
| `report.schema`     | `report/report.json`            | required (when `reporting.emit_json=true`)          |
| `thresholds.schema` | `report/thresholds.json`        | required                                            |
| `baseline_run_ref`  | `inputs/baseline_run_ref.json`  | required (when `reporting.regression.enabled=true`) |
| `manifest`          | `inputs/baseline/manifest.json` | optional (when `reporting.regression.enabled=true`) |

#### Required inputs

| contract_id    | Where found            | Required? |
| -------------- | ---------------------- | --------- |
| `range_config` | `inputs/range.yaml`    | required  |
| `manifest`     | `manifest.json`        | required  |
| `summary`      | `scoring/summary.json` | required  |

Notes:

- Reporting emits additional non-contract outputs in v0.1:
  - `report/report.html` when `reporting.emit_html=true`
  - `report/run_timeline.md` (required for reportable runs; deterministic operator-facing artifact;
    see "Run timeline artifact")
- `report/thresholds.json` is contract-backed (`thresholds.schema`) and MUST validate at the
  reporting publish gate.
- When `reporting.regression.enabled=true`, reporting also consumes a baseline reference (see
  `120_config_reference.md`, `reporting.regression.*`) and materializes deterministic baseline
  snapshots under `inputs/` per `045_storage_formats.md`.

### Config keys used

- `reporting.*` (emit flags, regression, rendering/detail toggles)
- `reporting.redaction.*` (report rendering redaction policy; distinct from `security.redaction.*`)

### Default fail mode and outcome reasons

- Default `fail_mode`: `fail_closed`
- Stage outcome reason codes:
  - reporting stage: see [ADR-0005](../adr/ADR-0005-stage-outcomes-and-failure-classification.md)
    "Reporting stage (`reporting`)"
  - regression substage: see ADR-0005 "Regression compare substage (`reporting.regression_compare`)"

### Isolation test fixture(s)

- `tests/fixtures/reporting/defense_outcomes/`
- `tests/fixtures/reporting/defense_outcomes/`
- `tests/fixtures/reporting/regression_compare/`
- `tests/fixtures/reporting/thresholds/`
- `tests/fixtures/reporting/report_render/`

See the [fixture index](100_test_strategy_ci.md#fixture-index) for the canonical fixture-root
mapping.

This document defines the reporting artifacts, required outputs, and trending keys for Purple Axiom
runs. It specifies both machine-readable JSON outputs for CI integration and human-readable report
structures for operator review.

## Scope

This document covers:

- Run artifact bundle structure and required outputs
- Machine-readable JSON report contracts
- Human-readable report sections and content requirements
- Trending keys for historical comparison
- Regression analysis semantics

This document does NOT cover:

- Scoring computation logic (see [Scoring metrics](070_scoring_metrics.md))
- Gap taxonomy definitions (see [Scoring metrics](070_scoring_metrics.md))
- Stage outcome semantics (see
  [ADR-0005](../adr/ADR-0005-stage-outcomes-and-failure-classification.md))

## Conventions

This specification follows the metric naming and rounding conventions defined in
[Scoring metrics](070_scoring_metrics.md) (Metric surface, normative).

Units (normative):

- Values suffixed `_pct` or `_rate` in machine-readable outputs are unitless fractions in the range
  `[0.0, 1.0]`. Human-readable percent displays MUST be rendered as `value * 100`.
- Values suffixed `_seconds` are measured in seconds.
- Values suffixed `_ms` are measured in milliseconds.

Determinism defaults (normative):

- Unless otherwise specified, arrays in reporting outputs MUST be emitted in a deterministic order
  and MUST NOT depend on input iteration order.
- String ordering MUST use UTF-8 byte order with no locale collation.

## Run artifact bundle

Each run produces a deterministic artifact bundle under `runs/<run_id>/`. The reporting stage
consumes upstream artifacts and emits outputs to `report/`.

Consumer tooling semantics (normative):

- The reporting stage MUST use the reference reader semantics defined in `025_data_contracts.md`
  ("Consumer tooling: reference reader semantics (pa.reader.v1)") for run bundle discovery, artifact
  discovery, `manifest.versions` interpretation, evidence ref handling (withheld/quarantined
  defaults), and integrity artifact parsing (`security/checksums.txt` and signatures when enabled).
- The reporting stage MUST NOT implement ad-hoc fallbacks that diverge from those semantics; any new
  fallback MUST be specified in the reader semantics section and covered by conformance fixtures.

### Required artifacts (v0.1)

The following artifacts MUST be present for a run to be considered reportable:

| Path                               | Source stage  | Purpose                                        |
| ---------------------------------- | ------------- | ---------------------------------------------- |
| `manifest.json`                    | orchestrator  | Run-level provenance, status, and version pins |
| `ground_truth.jsonl`               | runner        | Executed actions timeline                      |
| `logs/telemetry_validation.json`   | telemetry     | Telemetry validation outcomes (when enabled)   |
| `scoring/summary.json`             | scoring       | Primary metrics rollup for CI and trending     |
| `normalized/mapping_coverage.json` | normalization | OCSF field coverage by class                   |
| `bridge/coverage.json`             | detection     | Sigma-to-OCSF bridge quality metrics           |
| `criteria/manifest.json`           | validation    | Criteria pack snapshot metadata (when enabled) |
| `criteria/criteria.jsonl`          | validation    | Criteria pack snapshot contents (when enabled) |
| `criteria/results.jsonl`           | validation    | Per-action criteria outcomes (when enabled)    |
| `detections/detections.jsonl`      | detection     | Rule hits with matched event references        |
| `logs/health.json`                 | orchestrator  | Stage/substage outcomes mirror (when enabled)  |

Notes (health files and outcome sources):

- `manifest.json` is the authoritative source of stage outcomes and `manifest.status` derivation
  (see ADR-0005).
- `logs/health.json` is an operator-ergonomics mirror of those outcomes.
  - When health files are enabled (default; `operability.health.emit_health_files=true`),
    `logs/health.json` MUST be present and MUST match `manifest.json` status.
  - When health files are disabled (`operability.health.emit_health_files=false`),
    `logs/health.json` MAY be absent. In this mode, reporting MUST derive run status and stage
    outcomes from `manifest.json` and MUST NOT fail a run solely because `logs/health.json` is
    absent.

### Optional artifacts

Selected optional report inputs are *not* guaranteed to exist.

- For `manifest.versions.contracts_version >= 0.2.0`, normalized events are Parquet-only at
  `normalized/ocsf_events/**` (with the required schema snapshot at
  `normalized/ocsf_events/_schema.json`). `normalized/ocsf_events.jsonl` is legacy v0.1.x only
  and MUST NOT be used for v0.2+ runs.

| Path                                                        | Source stage  | Purpose                                                            |
| ----------------------------------------------------------- | ------------- | ------------------------------------------------------------------ |
| `runner/`                                                   | runner        | Per-action transcripts and cleanup evidence                        |
| `runner/principal_context.json`                             | runner        | Redaction-safe principal context summary                           |
| `inputs/baseline_run_ref.json`                              | reporting     | Resolved regression baseline reference (when enabled)              |
| `inputs/baseline/manifest.json`                             | reporting     | Baseline manifest snapshot (when enabled)                          |
| `logs/cache_provenance.json`                                | orchestrator  | Cache hit/miss provenance (when enabled)                           |
| `plan/expanded_graph.json`                                  | runner        | Compiled plan graph (v0.2+)                                        |
| `plan/expansion_manifest.json`                              | runner        | Matrix expansion manifest (v0.2+)                                  |
| `normalized/ocsf_events/` (includes `normalized/ocsf_events/_schema.json`) | normalization | Full normalized event store (Parquet dataset; v0.2+ canonical)     |
| `bridge/mapping_pack_snapshot.json`                         | detection     | Bridge inputs snapshot for reproducibility                         |
| `bridge/compiled_plans/`                                    | detection     | Per-rule compilation outputs                                       |
| `normalized/mapping_profile_snapshot.json`                  | normalization | Mapping profile snapshot for drift detection                       |
| `security/checksums.txt`                                    | signing       | SHA-256 checksums for long-term artifacts                          |
| `security/signature.ed25519`                                | signing       | Ed25519 signature over checksums                                   |
| `report/junit.xml`                                          | reporting     | CI-native JUnit test report (one testcase per action or scenario). |

## Required reporting outputs (v0.1)

The reporting stage MUST produce the following outputs:

| File                     | Purpose                                                                   | Schema reference                                         |
| ------------------------ | ------------------------------------------------------------------------- | -------------------------------------------------------- |
| `report/report.json`     | Consolidated report for external tooling                                  | [report schema](../contracts/report.schema.json)         |
| `report/thresholds.json` | Threshold evaluation results for CI gating                                | [thresholds schema](../contracts/thresholds.schema.json) |
| `report/report.html`     | Human-readable report for operator review (when enabled)                  | [HTML structure](#html-report-structure)                 |
| `report/run_timeline.md` | Deterministic, human-readable run timeline in UTC (operator UI + exports) | - (see "Run timeline artifact")                          |

Notes:

- When `reporting.emit_html=false`, `report/report.html` MUST NOT be emitted.
- When `reporting.emit_html=true`, `report/report.html` MUST be self-contained and local-only: it
  MUST NOT reference remote assets (no `http://` / `https://` URLs) and MUST NOT rely on external
  `.css` / `.js` files. See
  [Self-contained, local-only asset policy](#self-contained-local-only-asset-policy).
- `report/report.json` is a contract-backed required artifact for v0.1 reportable runs (when
  `reporting.emit_json=true`).
- `report/thresholds.json` is a contract-backed required artifact (`thresholds.schema`) for v0.1
  reportable runs and MUST validate at the reporting publish gate.
- If an implementation supports `reporting.emit_json`, it MUST be `true` for any run intended to be
  reportable.
- `report/run_timeline.md` is a required deterministic operator-facing artifact for v0.1 reportable
  runs.

The reporting stage MUST NOT modify upstream artifacts. It reads from `scoring/summary.json`,
`bridge/coverage.json`, `normalized/mapping_coverage.json`, and other inputs, then emits derived
outputs to `report/`.

### Run timeline artifact

The reporting stage MUST emit a deterministic, human-readable run timeline artifact at:

- `report/run_timeline.md`

Intended uses:

- Operator Interface: primary per-run chronology and drill-down starting point.
- Exported bundles: a single file that summarizes what happened without requiring a report renderer.

Source of truth (normative):

- The timeline MUST be derived from:
  - `ground_truth.jsonl` (canonical action lifecycle timeline), and
  - `manifest.json` (run id, scenario metadata when available, and overall run status).
- The timeline MUST NOT be derived by parsing unstructured logs.

Format (normative):

- The file MUST be UTF-8 (no BOM) and MUST use LF (`\n`) newlines.
- All timestamps rendered in the file MUST be UTC and MUST be RFC3339 with a `Z` suffix.
- Missing values MUST be rendered as `-` (single hyphen).

Required structure (normative):

The document MUST include, in this order:

1. A top-level heading `# Run timeline`
1. A "Run summary" section containing a Markdown table with the following keys (exact spellings):
   - `run_id`
   - `scenario_id`
   - `scenario_name` (MAY be `-` when unknown)
   - `status`
   - `started_at_utc`
   - `ended_at_utc`
1. An "Action timeline" section containing a Markdown table with one row per `action_id` in
   `ground_truth.jsonl`.

Action timeline table columns (normative; exact spellings):

- `order` (1-based integer)
- `action_id`
- `action_key`
- `technique_id` (MAY be `-` when unknown)
- `target_asset_id` (MAY be `-` when unknown)
- `start_utc`
- `end_utc`
- `duration_ms`
- `prepare`
- `execute`
- `revert`
- `teardown`
- `evidence`

Computation rules (normative):

- `start_utc` MUST equal the `prepare` phase `started_at_utc` when present; otherwise it MUST equal
  the earliest `lifecycle.phases[].started_at_utc`.
- `end_utc` MUST equal the final `teardown` phase `ended_at_utc` when present; otherwise it MUST
  equal the latest `lifecycle.phases[].ended_at_utc`.
- `duration_ms` MUST be computed as the integer milliseconds between `start_utc` and `end_utc` when
  both are present; otherwise it MUST be `-`.
- Phase outcome cells MUST be rendered from the ground truth `phase_outcome` values.
  - If retries exist for `execute` and/or `revert`, the cell MUST list attempt outcomes in ascending
    `attempt_ordinal` order using the syntax `<phase>[<n>]=<outcome>`, joined by `; `.
- `order` MUST be derived by sorting rows by a deterministic key and then assigning 1..N in that
  order.
  - Primary sort key: `start_utc` ascending.
  - Secondary sort key (tie-breaker when `start_utc` is identical):
    - When `plan/expanded_graph.json` is present and a `node_ordinal` can be resolved for every
      `action_id` in the table (by joining on `action_id`), rows MUST be sorted by `node_ordinal`
      ascending (numeric).
    - Otherwise, rows MUST be sorted by `action_id` ascending (UTF-8 byte order, no locale).
  - Final tie-breaker: `action_id` ascending (UTF-8 byte order, no locale).

Evidence links (normative):

- The `evidence` cell MUST contain zero or more Markdown links to run-relative evidence artifacts,
  in the following stable order when present:
  1. `requirements_evaluation_ref`
  1. `executor_ref`
  1. `stdout_ref`
  1. `stderr_ref`
  1. `terminal_recording_ref` (link label MUST be `terminal recording`)
  1. `cleanup_stdout_ref`
  1. `cleanup_stderr_ref`
  1. `cleanup_verification_ref`
  1. `state_reconciliation_report_ref`
- Evidence references MUST use the run-relative paths from `ground_truth.jsonl` `evidence.*_ref`
  fields.
- The timeline MUST NOT inline raw transcript content (stdout/stderr/terminal bytes); it MUST link
  to evidence artifacts only.

Evidence handling (normative):

- When the reporting stage knows that an evidence artifact is `withheld` or `quarantined`, the
  corresponding link label MUST include the handling value (example:
  `terminal recording (withheld)`).
- Handling vocabulary MUST match the report schema: `present | withheld | quarantined | absent`.

Verification hooks:

- A run is "timeline-conformant" iff `report/run_timeline.md` exists, is UTF-8, and matches the
  required section ordering and column set.
- CI SHOULD include a golden-fixture test that renders `report/run_timeline.md` from a fixed
  `ground_truth.jsonl` and compares it byte-for-byte.

### JUnit output artifact (optional)

The reporting stage MAY emit a JUnit XML file to integrate with common CI test result UIs without
custom tooling.

Path:

- `report/junit.xml`

Format (normative when present):

- UTF-8 XML.
- A single `<testsuite>` element containing `<testcase>` elements.
- Testcases MUST be deterministically ordered (RECOMMENDED: ascending `action_id`).

Test case mapping (normative when present):

- Default mapping: one `<testcase>` per action instance in `ground_truth.jsonl`.
- `<testcase name>` MUST be the action instance `action_id`.
- `<testcase classname>` SHOULD be the `scenario_id` (or a stable fallback such as `run_id` if
  `scenario_id` is not available to the reporter).

Outcome mapping (normative when present):

- The test result MUST be derived from the final `execute` phase outcome for the action:
  - `success` → pass (no `<failure>` or `<skipped>` element)
  - `failed` → `<failure>` element
  - `skipped` → `<skipped>` element

Failures and skips (normative when present):

- `<failure>` / `<skipped>` MUST include the Purple Axiom `reason_domain` and `reason_code` from the
  action's final `execute` phase record (see `ground_truth.jsonl` lifecycle phase schema).
- When the ground truth `execute` phase record also contains an `error` object, the reporter SHOULD
  include `error.type` (and a short message) in the failure payload.

Evidence pointers (normative when present):

- Each `<testcase>` SHOULD include pointers to evidence artifacts, either as `<system-out>` text or
  as `<property>` values, using run-relative paths.
- When available, the reporter SHOULD include the `stdout_ref`, `stderr_ref`, and `executor_ref`
  evidence references from the ground truth action record.

Verification hooks:

- Fixture-based tests SHOULD assert deterministic ordering and stable, parseable XML for fixed
  fixtures.
- Fixture-based tests SHOULD assert that failures include `reason_domain` + `reason_code` and at
  least one evidence pointer when evidence references are present in `ground_truth.jsonl`.

### Upstream artifacts (consumed, not produced)

These artifacts are produced by upstream stages and referenced in the report:

| File                               | Purpose                                       | Schema reference                                                                 |
| ---------------------------------- | --------------------------------------------- | -------------------------------------------------------------------------------- |
| `manifest.json`                    | Run-level provenance and outcomes             | [manifest schema](../contracts/manifest.schema.json)                             |
| `ground_truth.jsonl`               | Executed actions timeline                     | [Scenarios](030_scenarios.md)                                                    |
| `logs/telemetry_validation.json`   | Telemetry validation outcomes                 | [Telemetry pipeline](040_telemetry_pipeline.md)                                  |
| `scoring/summary.json`             | Operator-facing metrics rollup                | [summary schema](../contracts/summary.schema.json)                               |
| `bridge/coverage.json`             | Sigma-to-OCSF bridge quality                  | [bridge coverage schema](../contracts/bridge_coverage.schema.json)               |
| `normalized/mapping_coverage.json` | OCSF normalization coverage                   | [mapping coverage schema](../contracts/mapping_coverage.schema.json)             |
| `criteria/manifest.json`           | Criteria pack snapshot metadata               | [criteria pack manifest schema](../contracts/criteria_pack_manifest.schema.json) |
| `criteria/criteria.jsonl`          | Criteria pack snapshot contents               | [Validation criteria](035_validation_criteria.md)                                |
| `criteria/results.jsonl`           | Per-action criteria outcomes                  | [Validation criteria](035_validation_criteria.md)                                |
| `detections/detections.jsonl`      | Rule hits with matched event references       | [Detection (Sigma)](060_detection_sigma.md)                                      |
| `logs/health.json`                 | Stage/substage outcomes mirror (when enabled) | [ADR-0005](../adr/ADR-0005-stage-outcomes-and-failure-classification.md)         |

## Run status summary

The report MUST prominently display run status and the reasons for any degradation. Run status is
derived from stage outcomes per
[ADR-0005](../adr/ADR-0005-stage-outcomes-and-failure-classification.md), plus any configured
quality gates evaluated by the reporting stage (thresholds and regression).

Stage outcomes are read from `manifest.json` (authoritative); `logs/health.json` is an optional
mirror when enabled.

Normative coupling:

- `report/thresholds.json.status_recommendation` is the authoritative CI-facing status.
- `report/report.json.status` MUST equal `report/thresholds.json.status_recommendation`.
- `report/report.json.status_reasons[]` MUST include the stable degradation reason codes that
  explain why the final status is not `success`.

### Status definitions

| Status    | Meaning                                                                        | Exit code |
| --------- | ------------------------------------------------------------------------------ | --------- |
| `success` | All stages completed; all quality gates passed                                 | `0`       |
| `partial` | Artifacts usable but one or more quality gates failed or were indeterminate    | `10`      |
| `failed`  | Run not mechanically usable; required artifacts missing or stage failed closed | `20`      |

### Status degradation reasons

When status is `partial` or `failed`, the report MUST enumerate the contributing factors.

Normative JSON detail (report schema):

- `report/report.json.status_reason_details[]` entries MUST include:
  - `reason_domain` (string; MUST equal `report.schema`)
  - `reason_code` (string)

Common degradation reasons include:

| Reason code                          | Gate type     | Description                                                                                        |
| ------------------------------------ | ------------- | -------------------------------------------------------------------------------------------------- |
| `stage_failed_closed`                | Stage outcome | A required stage failed with `fail_mode=fail_closed`                                               |
| `artifact_missing`                   | Orchestrator  | One or more required artifacts absent                                                              |
| `technique_coverage_below_threshold` | Quality gate  | Technique coverage < configured threshold                                                          |
| `tier1_coverage_below_threshold`     | Quality gate  | Tier 1 field coverage < configured threshold (default 80%)                                         |
| `tier1_coverage_indeterminate`       | Quality gate  | No in-scope events to compute coverage                                                             |
| `latency_above_threshold`            | Quality gate  | Detection latency p95 > configured threshold (default 300s)                                        |
| `gap_rate_exceeded`                  | Quality gate  | Gap category rate exceeds thresholds                                                               |
| `regression_alert`                   | Quality gate  | Significant regression detected vs baseline                                                        |
| `baseline_missing`                   | Quality gate  | Regression enabled but baseline run could not be resolved/read                                     |
| `baseline_incompatible`              | Quality gate  | Regression baseline and candidate not comparable (for example: environment noise profile mismatch) |
| `regression_compare_failed`          | Quality gate  | Regression comparison errored; results indeterminate                                               |
| `cleanup_verification_failed`        | Validation    | Cleanup verification failures above threshold (future gate)                                        |
| `criteria_misconfigured_rate`        | Validation    | Criteria misconfigured rate above threshold (optional gate)                                        |

Clarification (normative):

- `report/report.json.status_reasons[]` and `report/report.json.status_reason_details[]` use
  `reason_domain="report.schema"` and are scoped to the report schema (not the ADR-0005 stage
  outcome reason code catalog).
- Stage/substage outcome `reason_code` values in `manifest.stage_outcomes[]` and `logs/health.json`
  remain governed by ADR-0005.

Determinism (normative):

- `report/report.json.status_reasons[]` MUST contain unique reason codes and MUST be emitted sorted
  ascending (UTF-8 byte order, no locale).

### Gate catalog

This catalog is a coherence aid only. It introduces no new v0.1 behavior; it summarizes how the
existing Tier 1 normalization coverage gate and Sigma-to-OCSF bridge gap budgets are surfaced in the
CI-facing and report-facing outputs.

| Gate axis                                             | Threshold gate (`report/thresholds.json.gates[].gate_id`) | Threshold config key                             | Source metric(s) (`scoring/summary.json`)                | Degradation reason code(s)                                       | Primary evidence artifacts                                        |
| ----------------------------------------------------- | --------------------------------------------------------- | ------------------------------------------------ | -------------------------------------------------------- | ---------------------------------------------------------------- | ----------------------------------------------------------------- |
| Tier 1 normalization coverage                         | `min_tier1_field_coverage`                                | `scoring.thresholds.min_tier1_field_coverage`    | `tier1_field_coverage_pct`, `tier1_field_coverage_state` | `tier1_coverage_below_threshold`, `tier1_coverage_indeterminate` | `normalized/mapping_coverage.json`, `scoring/summary.json`        |
| Bridge gap budget (mapping pack addressable)          | `max_bridge_gap_mapping_rate`                             | `scoring.thresholds.max_bridge_gap_mapping_rate` | `bridge_gap_mapping_rate`                                | `gap_rate_exceeded`                                              | `bridge/coverage.json` (optionally `detections/detections.jsonl`) |
| Bridge gap budget (expected feature scope)            | `max_bridge_gap_feature_rate`                             | `scoring.thresholds.max_bridge_gap_feature_rate` | `bridge_gap_feature_rate`                                | `gap_rate_exceeded`                                              | `bridge/coverage.json` (optionally `detections/detections.jsonl`) |
| Bridge gap budget (unexpected / bridge bug indicator) | `max_bridge_gap_other_rate`                               | `scoring.thresholds.max_bridge_gap_other_rate`   | `bridge_gap_other_rate`                                  | `gap_rate_exceeded`                                              | `bridge/coverage.json` (optionally `detections/detections.jsonl`) |

Notes:

- CI reads `report/thresholds.json.status_recommendation` as the primary verdict input when present
  (see `105_ci_operational_readiness.md`).
- For bridge gap budgets, the shared reason code `gap_rate_exceeded` is disambiguated by the failing
  `gate_id` plus its `threshold` and `actual` values in `report/thresholds.json.gates[]`.

## Human-readable report sections

The HTML report MUST include the following sections. JSON equivalents SHOULD be emitted in
`report/report.json` for programmatic consumption.

### Executive summary

The report MUST include:

- Run name, timestamp, and overall status
- Scenario posture (`baseline` vs `assumed_compromise`)
- Top-line technique coverage (`coverage_pct` rendered as a percentage)
- EPS (events/sec), total events
- Total actions executed, succeeded, failed
- Criteria summary: unmet, met, misconfigured, unavailable counts
- Synthetic correlation marker summary (if enabled)
- Regression summary (if enabled)
- Link to raw artifacts (if published)

### Execution context

Principal context summary:

- Evidence reference: `runner/principal_context.json`.
- The report MUST treat principal context as sensitive and MUST render only redaction-safe summary
  fields (no raw usernames, SIDs, emails, access key IDs, or other secret-like identifiers).
- The report MUST disclose principal context handling as one of:
  - `present`
  - `withheld`
  - `quarantined`
  - `absent` (not produced)
- Count of principals by `kind` (from `principal_context.principals[]`).
- Count of actions with `kind=unknown` attribution (from `principal_context.action_principal_map[]`,
  counting rows whose referenced principal resolves to `kind=unknown`).
- Principals table (stable ordering, required when `handling != absent`):
  - Columns: `principal_id`, `kind`
  - Sort rows by `principal_id` ascending (UTF-8 byte order, no locale).

Cache provenance summary (when present):

- Evidence reference: `logs/cache_provenance.json` (when produced).
- Counts of cache results grouped by `(component, cache_name)`:
  - `hits` (entries with `result=hit`)
  - `misses` (entries with `result=miss`)
  - `bypassed` (entries with `result=bypassed`, when present in the contract)
- Cache summary table (stable ordering, required when the artifact is present):
  - Columns: `component`, `cache_name`, `hits`, `misses`, `bypassed` (optional), `total`
  - Sort rows by `(component, cache_name)` ascending (UTF-8 byte order, no locale).
- The report MUST NOT disclose per-entry cache `key` values unless a future explicit debug-only
  configuration gate allows it.

Deterministic ordering (normative):

- Principals MUST be sorted by `principal_id` as specified above.
- If the report renders any per-entry cache provenance rows (debug-only), it MUST follow the cache
  provenance contract ordering (entries sorted by `(component, cache_name, key)`).

JSON equivalent (recommended):

- The report JSON SHOULD mirror this section under
  `report/report.json.extensions.execution_context`, including `principals[]` sorted by
  `principal_id` and cache summaries sorted by `(component, cache_name)`.

### Action lifecycle outcomes

The report MUST include::

- Idempotence distribution over executed actions:
  - counts for `idempotent | non_idempotent | unknown`
- Per-phase outcome counts aggregated over actions:
  - `prepare`, `execute`, `revert`, `teardown` each with counts for `success | failed | skipped`
- A table (or list) of actions with non-success lifecycle phases (limit 25), including:
  - `action_id`, technique ID, target asset id
  - `idempotence` (`idempotent | non_idempotent | unknown`) for the action
  - non-success phase(s) and per-phase `phase_outcome`
    - When multiple non-success phases exist, phases MUST be listed in lifecycle order: `prepare`,
      `execute`, `revert`, `teardown`.
    - When retries are present in ground truth, the report MUST render attempt ordinals
      deterministically (example: `execute[0]`, `execute[1]`) and MUST preserve lifecycle order.
  - evidence references (paths under `runner/actions/<action_id>/`), including requirements
    evaluation, resolved inputs evidence, and cleanup verification references when present
    - When `runner/actions/<action_id>/resolved_inputs_redacted.json` is present, the report MUST
      treat it as sensitive and MUST NOT render resolved input values; the report SHOULD render only
      the evidence reference (artifact path) and handling.
    - When `runner/actions/<action_id>/terminal.cast` (or the ground truth
      `evidence.terminal_recording_ref`) is present, the report SHOULD render an evidence link
      labeled "terminal recording". The report MAY provide inline playback in the Operator
      Interface, but MUST treat the recording as supplemental (MUST NOT affect scoring or pass/fail
      evaluation) and MUST surface the evidence handling. When handling is `withheld` or
      `quarantined`, the report MUST NOT attempt to render unredacted bytes; it MAY link only to the
      placeholder artifact.
    - The report SHOULD prefer rendering evidence links that are referenced by the ground truth
      lifecycle phase `evidence` pointers (when present), and otherwise fall back to the
      conventional runner paths.

Deterministic ordering (normative):

- The non-success lifecycle actions table MUST be sorted deterministically by the tuple:
  1. `primary_phase` order: `prepare` < `execute` < `revert` < `teardown`, where `primary_phase` is
     the earliest lifecycle phase that is not `success` for the action (considering retries).
  1. `primary_outcome` order: `failed` < `skipped`.
  1. `action_id` ascending (UTF-8 byte order, no locale).
- If multiple actions share identical tuple values (rare), implementations MAY add additional stable
  tie-breakers, but MUST NOT depend on input iteration order.

### Synthetic correlation marker

Required content (when marker emission is enabled):

- Marker status: `enabled | disabled`.
- The marker values used for the run:
  - canonical marker string (`extensions.synthetic_correlation_marker`)
  - deterministic derived token (`extensions.synthetic_correlation_marker_token`)
- Per-action marker observability table (stable ordering, required):
  - Sort rows by `action_id` ascending.
  - Columns:
    - `action_id` (and action name when available)
    - `marker_canonical`
    - `marker_token`
    - `observed` (`yes | no`) (yes when either canonical marker or token is observed in normalized
      telemetry for the action)
    - `observed_form` (`canonical | token | both | none`)
    - `gap_category` (when `observed_form=none`, MUST be `missing_telemetry`)
- Narrative and gap integration (normative):
  - When `observed_form=none` for any action, the report MUST surface those actions under the
    existing `missing_telemetry` gap category in [Gap analysis](#gap-analysis) and MUST include a
    concise remediation hint that points to telemetry pipeline filtering/sampling misconfiguration
    as a primary suspect.

JSON equivalent (recommended):

- The report JSON SHOULD mirror this section under `report/report.json.extensions`, for example
  `extensions.synthetic_correlation_marker`, including aggregate counts and a `per_action[]` list
  sorted by `action_id` ascending.

### Coverage metrics

The report MUST include:

- Total executed techniques (`techniques_executed`)
- Total covered techniques (`techniques_covered`)
- Coverage fraction (`coverage_pct`: `techniques_covered / techniques_executed`, unitless in
  `[0.0, 1.0]`)
- Per-technique breakdown table (technique_id, detection count, first detection latency (seconds))

### Defense outcomes

Required content:

- Outcome precedence rendered verbatim: `blocked > alerted > logged > none > not_applicable > tbd`
- Per-technique outcome table (stable ordering, required):
  - Sort rows by `technique_id` ascending.
  - Columns:
    - `technique_id`
    - `outcome_best`
    - `outcome_counts` (at least: alerted/logged/none/not_applicable/tbd; blocked MAY be present)
    - `actions_total` (count of action instances with this technique_id in ground truth)
- Per-action outcome table (stable ordering, recommended when the run has ≤ 500 actions):
  - Sort rows by `action_id` ascending.
  - Columns:
    - `action_id` (and action name when available)
    - `technique_id`
    - `derived_outcome`
    - `tool_outcomes[]` (tool_kind, tool_id, outcome, reason_domain, reason_code)
      - `reason_domain` MUST equal `defense_outcomes` when `reason_code` is present.
    - evidence references (criteria result row and/or marker result row; detection evidence when
      alerted)

JSON equivalent (required):

- The report JSON MUST include `extensions.defense_outcomes` containing:
  - `taxonomy_version`
  - `outcome_precedence[]`
  - `summary`
  - `by_technique[]`
  - `by_action[]` (MAY be omitted only when a configured size guard is exceeded; if omitted, the
    report MUST set `summary.by_action_omitted=true` and record the omission reason)

### Latency distribution

The report MUST include:

- Percentile distribution: p50, p90, p95, max (in milliseconds)
- Histogram or distribution visualization (HTML only)
- Techniques with latency exceeding threshold (flagged)

### Detection fidelity

The report MUST include:

- Fidelity tier counts from `scoring/summary.json`:
  - `exact`: detection matched expected event with high confidence
  - `partial`: detection matched with reduced confidence (time window, field subset)
  - `weak`: detection present but match quality uncertain
- Fidelity breakdown by technique (when available)

### Gap analysis

The report MUST classify failures using the categories defined in
[Scoring metrics](070_scoring_metrics.md) (Pipeline health, v0.1). Gap categories are mutually
exclusive and collectively exhaustive for reported pipeline-health gaps. Implementations MUST NOT
emit additional gap category tokens.

#### Gap taxonomy (normative)

| Category                      | Description                                               | Addressability                |
| ----------------------------- | --------------------------------------------------------- | ----------------------------- |
| `missing_telemetry`           | Expected signals absent for executed action               | Collector/endpoint config     |
| `criteria_unavailable`        | No matching criteria entry in pinned pack                 | Criteria pack authoring       |
| `criteria_misconfigured`      | Criteria entry exists but cannot be evaluated             | Criteria pack fix             |
| `normalization_gap`           | Events exist but required OCSF fields missing             | Mapping profile work          |
| `bridge_gap_mapping`          | OCSF fields exist but bridge lacks aliases/router entries | Mapping pack work             |
| `bridge_gap_feature`          | Rule requires unsupported Sigma features                  | Backend enhancement           |
| `bridge_gap_other`            | Bridge failure not otherwise classified                   | Investigation required        |
| `rule_logic_gap`              | Fields present, rule executable, but rule did not fire    | Rule tuning                   |
| `cleanup_verification_failed` | Cleanup invoked but verification checks failed            | Runner/scenario investigation |

Terminology note (normative):

- `missing_telemetry` describes missing expected telemetry signals for an executed action.
- It MUST NOT be used to describe missing artifact files (for example missing Parquet partitions or
  missing JSON artifacts). Missing artifacts are surfaced via stage outcomes (for example
  `input_missing`, `baseline_missing`, `baseline_incompatible`) or reader errors
  (`error_code="artifact_missing"`), not via the gap taxonomy.

Required content:

- Aggregate counts per gap category
- Top failures by category (limit 10 per category) with:
  - Gap category (`gap_category`; MUST be one of the taxonomy tokens above)
  - Technique ID
  - Measurement layer
  - Evidence references (`evidence_refs[]`; run-relative artifact paths; see
    `025_data_contracts.md`)
  - Actionable remediation hint
- Gap rate percentages relative to executed actions

#### Measurement contract for conclusions (normative)

Every reported gap MUST be attributable to exactly one measurement layer. This enables deterministic
triage by answering "which layer is broken" and "which artifacts prove it" for every conclusion.

Measurement layers (closed set):

- `telemetry`
- `normalization`
- `detection`
- `scoring`

Note (stage vs layer, normative):

- The pipeline includes a `validation` stage (criteria evaluation and cleanup verification)
  configured via `validation.*` (see `120_config_reference.md`).
- Validation is not a separate `measurement_layer` token. Validation-originated gap categories
  (`criteria_unavailable`, `criteria_misconfigured`, `cleanup_verification_failed`) MUST use
  `measurement_layer="scoring"` per the mapping in `070_scoring_metrics.md`.

Note: Artifact namespaces such as `bridge/`, `criteria/`, and `runner/` are evidence surfaces and
report subsections. They MUST NOT be used as `measurement_layer` values.

Normative requirements:

- Gap category identifiers used in the report JSON (for example `gaps.by_category` keys and any
  `top_failures[].gap_category`) MUST be canonical pipeline-health gap taxonomy tokens defined in
  [Scoring metrics](070_scoring_metrics.md) (Pipeline health, v0.1). Implementations MUST NOT emit
  additional gap category tokens.
- Each per-category aggregate under `gaps.by_category` MUST include `measurement_layer`.
- Each gap instance in any `top_failures[]` array MUST include:
  - `gap_category`
  - `measurement_layer`
  - `evidence_refs[]` (at least one entry)
- For `gaps.by_category["<gap_category>"].top_failures[]`, each entry's `gap_category` MUST equal
  the parent category key.
- `measurement_layer` MUST match the mapping in [Scoring metrics](070_scoring_metrics.md) (Gap
  category to measurement layer mapping, normative).
- `evidence_refs[]` MUST conform to the evidence ref shape, selector grammar, and deterministic
  ordering rules defined in `025_data_contracts.md` (Evidence references (shared shape)).
- Evidence refs MUST be run-relative artifact paths. Selectors are optional.
- Evidence refs MUST NOT embed secrets or raw sensitive identifiers.

Minimum evidence refs by measurement layer (normative):

- telemetry:
  - MUST include `manifest.json`.
  - MUST include `logs/health.json` when present.
  - SHOULD include `logs/telemetry_validation.json` when present.
- normalization:
  - MUST include `normalized/mapping_coverage.json`.
- detection:
  - MUST include `bridge/coverage.json`.
  - SHOULD include `detections/detections.jsonl`.
- scoring:
  - MUST include `scoring/summary.json`

Conditional minimums:

- `criteria_unavailable`, `criteria_misconfigured`:

  - When criteria validation is enabled, MUST include `criteria/manifest.json` and
    `criteria/results.jsonl`.
  - SHOULD include `criteria/criteria.jsonl`.

- `cleanup_verification_failed`:

  - MUST include `runner/actions/<action_id>/cleanup_verification.json` for the relevant action.

Deterministic ordering (normative):

- Any `top_failures[]` array MUST be sorted by:
  1. `gap_category` ascending (UTF-8 byte order, no locale)
  1. `technique_id` ascending (UTF-8 byte order, no locale)
  1. `action_id` ascending (UTF-8 byte order, no locale), when present
- Within any `evidence_refs[]` array, entries MUST be sorted by `artifact_path` ascending.

### Tier 1 normalization coverage

This section surfaces the Tier 1 coverage gate defined in
[OCSF field tiers](055_ocsf_field_tiers.md).

Required content:

- `tier1_field_coverage_pct`: aggregate coverage percentage
- `tier1_field_coverage_state`: `ok`, `below_threshold`, or `indeterminate_no_events`
- `tier1_field_coverage_threshold_pct`: configured threshold (default 80%)
- Gate outcome: pass/fail with explanation
- Per-field breakdown table (SHOULD include):
  - Field path (e.g., `device.hostname`, `actor.user.name`)
  - Presence count
  - Presence percentage
  - Fields below 50% presence (flagged)

### Per-source breakdown

Detection engineering requires understanding which sources contribute to coverage and gaps.

Required content (per `source_type`):

- Event count
- Tier 1 field coverage percentage
- Detection count
- Gap breakdown (counts per category)
- Top unmapped fields (when `normalization_gap` present)

Source types MUST align with `metadata.source_type` values in normalized events (e.g.,
`windows-security`, `windows-sysmon`, `osquery`, `linux-auditd`).

Terminology note (normative): `metadata.source_type` uses the event_source_type namespace
(hyphenated `id_slug_v1` literals). It MUST NOT be confused with `identity_basis.source_type`
(identity_source_type; typically lower_snake_case such as `windows_eventlog`, `linux_auditd`) used
for deterministic `metadata.event_id` computation (ADR-0002).

### Sigma-to-OCSF bridge health

Required content (from `bridge/coverage.json`):

- `total_rules`: rules attempted
- `routed_rules`: rules with valid logsource routing
- `executable_rules`: rules that compiled successfully
- `non_executable_rules`: rules that failed compilation
- `fallback_used_rules`: rules requiring `raw.*` fallback

Breakdown tables:

- By `logsource.category`: routed vs unrouted counts
- Top unrouted categories (limit 20)
- Top unmapped Sigma fields (limit 20) with occurrence counts
- Non-executable reason distribution (from `non_executable_reasons`)

### Criteria evaluation

Required content:

- Criteria pack ID and version (from `criteria/manifest.json`)
- Aggregate rates:
  - `criteria_pass_rate`
  - `criteria_fail_rate`
  - `criteria_skipped_rate`
- Per-technique criteria outcomes
- Criteria signal latency (p50, p90) when measurable
- Skipped reasons breakdown (no matching criteria, evaluation disabled, action failed)

### Requirements & environment gates

Required content:

- Aggregate unmet requirement counts by `(reason_domain, reason_code)`:
  - `requirements_evaluation` + `unsupported_platform`
  - `requirements_evaluation` + `insufficient_privileges`
  - `requirements_evaluation` + `missing_tool`
- Affected actions table (limit 50) including:
  - `action_id` and technique ID (and action name when available)
  - primary unmet `reason_domain` and `reason_code` (one of the above, domain MUST be
    `requirements_evaluation`)
  - Evidence reference: link to `runner/actions/<action_id>/requirements_evaluation.json`
  - Evidence handling note: `present | withheld | quarantined`
- Narrative integration (normative):
  - When any unmet requirements exist, the report MUST include the corresponding reason codes in
    [Status degradation reasons](#status-degradation-reasons) and MUST surface a concise explanation
    in the executive summary "why did it fail?" narrative.

Disclosure minimization (normative):

- Unless explicitly configured otherwise, this section MUST NOT render over-specific probe details
  (example: exact tool paths, full version strings); it MUST prefer reason codes and run-relative
  evidence references.

### Cleanup verification

Required content:

- Cleanup invocation count vs skipped count
- Verification outcomes: pass/fail counts
- Failed verifications with evidence references (links to `runner/` artifacts)
- Cleanup policy applied (from scenario or range config)

### State reconciliation

Required content:

- Reconciliation coverage:
  - Actions reconciled count vs not-enabled/skipped count
- Action-level status distribution (from per-action reconciliation reports):
  - `clean`
  - `drift_detected`
  - `unknown`
  - `skipped`
- Aggregate item counts (sum of `summary` fields across actions):
  - `items_total`
  - `drift_detected`
  - `unknown`
  - `skipped`
- Remediation disposition summary:
  - `repaired` vs `requires_review`
  - For v0.1, repair is out of scope; the report MUST render `repaired=0` and MUST treat every drift
    item as `requires_review`.
- Drift details table (limit 50):
  - `action_id` and `action_key`
  - `source` (`cleanup_verification | side_effect_ledger`)
  - `check_id` (when `source=cleanup_verification`) or `ledger_seq` (when
    `source=side_effect_ledger`)
  - `status` (`match | mismatch | unknown | skipped`)
  - `reason_domain`
  - `reason_code`
  - Evidence reference: link to `runner/actions/<action_id>/state_reconciliation_report.json`

### Event volume metrics

Required content:

- Total events captured (raw)
- Total events normalized
- Events per second (EPS) during execution window:
  - Peak EPS
  - Average EPS
- Events by `source_type`
- Events by `class_uid`

### Version inventory

The report MUST include a version inventory section with:

Required content (from `manifest.versions`):

- `project_version` (Purple Axiom core release)
- `pipeline_version` (pipeline definition version)
- `scenario_id`, `scenario_version`, `rule_set_id`, `rule_set_version`
- `ocsf_version`
- `mapping_pack_id`, `mapping_pack_version` (when the Sigma-to-OCSF bridge is enabled)
- `criteria_pack_id`, `criteria_pack_version` (when criteria evaluation is enabled)
- `threat_intel_pack_id` (when threat intelligence is enabled)
- `threat_intel_pack_version` (when threat intelligence is enabled)

Conditional pins (from `manifest.versions`, when enabled):

- `mapping_pack_id`
- `mapping_pack_version`
- `criteria_pack_id`
- `criteria_pack_version`

Runner environment noise profile pins (from `manifest.extensions.runner.environment_noise_profile`,
when enabled):

- `manifest.extensions.runner.environment_noise_profile.profile_id`
- `manifest.extensions.runner.environment_noise_profile.profile_version`
- `manifest.extensions.runner.environment_noise_profile.profile_sha256`
- `manifest.extensions.runner.environment_noise_profile.seed`

Additional provenance (when present):

- Mapping pack ref (from `bridge/coverage.json` → `mapping_pack_ref`)
- Criteria pack manifest (from `criteria/manifest.json`)
- Range config sha (from `manifest.inputs.range_yaml_sha256`; `sha256:<lowercase_hex>` form when
  present)

## Regression analysis

Regression analysis is controlled by configuration (`reporting.regression.enabled`; see
`120_config_reference.md`). When disabled, the report MUST NOT include
`report/report.json.regression`. When enabled, the reporting stage MUST attempt a deterministic
comparison against the configured baseline and MUST emit `report/report.json.regression` as
described below.

If regression is enabled but the baseline cannot be located/read, is incompatible, or the comparison
fails unexpectedly, the reporting stage MUST still emit the `reporting.regression_compare` health
substage outcome with the appropriate reason code (see ADR-0005). In these cases, the report MUST
emit `report/report.json.regression` in an indeterminate form with an empty `deltas[]` array.

### Regression JSON contract (normative)

`report/report.json.regression` is the authoritative machine-readable regression surface for CI and
downstream tools.

Presence rules (normative):

- If `reporting.regression.enabled=false`, `report/report.json.regression` MUST be absent.
- If `reporting.regression.enabled=true` and the baseline is resolved and compared, the report JSON
  MUST include `report/report.json.regression` populated per this contract.
- If `reporting.regression.enabled=true` but baseline resolution or comparison fails, the report
  JSON MUST still include `report/report.json.regression` in an indeterminate form:
  - `comparability.status` MUST be `indeterminate`.
  - `comparability.reason_domain` MUST equal `report.schema`.
  - `comparability.reason_code` MUST be one of
    `baseline_missing | baseline_incompatible | regression_compare_failed`.
  - `deltas[]` MUST be an empty array (`[]`).
  - `regression_alerted` MUST be `false`.
  - `alert_reasons[]` MUST be an empty array (`[]`).
  - The reporting stage MUST emit the `reporting.regression_compare` health substage outcome with
    the same `reason_code` (see ADR-0005).

Required fields:

- `baseline`:
  - `run_id` (string; baseline run id; may be `null` when unavailable)
  - `generated_at_utc` (string; baseline report generation timestamp; may be `null` when
    unavailable)
  - `manifest_ref` (string; run-relative artifact path or content-addressed reference; may be `null`
    when unavailable)
- `comparability`:
  - `status` (string): `comparable | warning | indeterminate`
  - `reason_domain` (string; required when `status=indeterminate`; MUST equal `report.schema`)
  - `reason_code` (string; required when `status=indeterminate`):
    `baseline_missing | baseline_incompatible | regression_compare_failed`
  - `policy` (object; REQUIRED when `report/report.json.regression` is present):
    - Purpose: record the resolved comparability policy that was applied, so comparisons remain
      explainable and reproducible.
    - `allow_mapping_pack_version_drift` (boolean; default: `false`)
      - If `false`, mismatches on `versions.mapping_pack_version` MUST be treated as not comparable
        (`baseline_incompatible`) unless the key is not applicable to both runs.
      - If `true`, mismatches on `versions.mapping_pack_version` MUST be treated as warnings
        (comparison MAY proceed), and the mismatch MUST still be recorded in
        `comparability_checks[]`.
    - `allow_noise_profile_mismatch` (boolean; default: `false`)
      - If `false`, mismatches on `extensions.runner.environment_noise_profile.*` MUST be treated as
        not comparable (`baseline_incompatible`) unless the key is not applicable to both runs.
      - If `true`, mismatches on `extensions.runner.environment_noise_profile.*` MUST be treated as
        warnings (comparison MAY proceed), and the mismatches MUST still be recorded in
        `comparability_checks[]`.
  - `evidence_refs[]`:
    - Each entry MUST follow the `evidence_refs[]` shape and selector grammar defined in
      `025_data_contracts.md`.
    - `evidence_refs[]` MUST include entries with:
      - `artifact_path="manifest.json"` (current run)
      - `artifact_path="inputs/baseline_run_ref.json"`
    - When `inputs/baseline/manifest.json` is present, `evidence_refs[]` SHOULD include it.
    - Entries MUST be sorted by `artifact_path` ascending (UTF-8 byte order, no locale).
- `comparability_checks[]`:
  - Each entry MUST include:
    - `key` (string)
    - `baseline_value` (string; may be `null` when unavailable)
    - `current_value` (string; may be `null` when unavailable)
    - `match` (boolean; MUST be false when `baseline_value` or `current_value` is null)
    - `status` (string): `pass | fail | skipped`
    - `reason_code` (string; REQUIRED when `status != pass`):
      `missing_baseline_pin | missing_current_pin | pin_mismatch | drift_disallowed_by_policy | not_applicable`
    - `evidence_refs[]` (array; REQUIRED when `status=fail`):
      - Each entry MUST follow the `evidence_refs[]` shape and selector grammar defined in
        `025_data_contracts.md`.
      - Entries MUST be sorted by `artifact_path` ascending (UTF-8 byte order, no locale).
  - `comparability_checks[]` MUST include all keys listed in
    [Regression comparability keys](#regression-comparability-keys).
  - `comparability_checks[]` MUST be sorted by `key` ascending (UTF-8 byte order, no locale).
- `metric_surface_ref`:
  - A string reference to the comparable metric surface defined in
    [Scoring metrics](070_scoring_metrics.md) (Regression comparable metric surface, normative).
- `deltas[]`:
  - Each entry MUST include:
    - `metric_id` (string)
    - `kind` (string)
    - `unit` (string)
    - `baseline_value` (number or integer; may be `null`)
    - `candidate_value` (number or integer; may be `null`)
    - `delta` (number or integer; may be `null`)
    - `tolerance` (number or integer)
    - `status` (string): `computed | indeterminate`
    - `indeterminate_reason` (string; REQUIRED when `status=indeterminate`):
      `not_applicable | excluded_by_config | taxonomy_mismatch`
    - `within_tolerance` (boolean; MUST be false when `status=indeterminate` or `delta` is `null`)
    - `regression_flag` (boolean; MUST be false when `status=indeterminate`)
    - `evidence_refs[]` (array; REQUIRED when `status=indeterminate` and
      `indeterminate_reason=taxonomy_mismatch`):
      - Each entry MUST follow the `evidence_refs[]` shape and selector grammar defined in
        `025_data_contracts.md`.
      - `evidence_refs[]` MUST include entries pointing to the baseline and candidate effective
        taxonomy sources (for example, the `meta.effective_gap_taxonomy` field in the scoring
        summary, or a config snapshot referenced by the manifest/report).
      - Entries MUST be sorted by `artifact_path` ascending (UTF-8 byte order, no locale).
  - Deterministic indeterminate handling (normative):
    - If `status=indeterminate`, then `delta` MUST be `null`, and `within_tolerance` MUST be
      `false`.
    - Indeterminate delta entries MUST NOT be evaluated against thresholds and MUST NOT contribute
      to `regression_alerted` or `alert_reasons[]`.
  - Deterministic excluded-category handling (normative):
    - If a metric is excluded in both baseline and candidate (for example, both values are `null`
      due to `excluded_by_config`), then `status` MUST be `indeterminate` with
      `indeterminate_reason="excluded_by_config"`.
    - If a metric is excluded in exactly one of baseline or candidate, then `status` MUST be
      `indeterminate` with `indeterminate_reason="taxonomy_mismatch"` (do not compute a delta from a
      `null`).
    - If a metric’s definition depends on the effective included set (for example, aggregates
      computed over an effective taxonomy) and the baseline and candidate effective taxonomies are
      not identical, then `status` MUST be `indeterminate` with
      `indeterminate_reason="taxonomy_mismatch"`.
  - `deltas[]` MUST be sorted by `metric_id` ascending (UTF-8 byte order, no locale).
  - Delta rounding, tolerance semantics, and indeterminate handling MUST follow
    [Scoring metrics](070_scoring_metrics.md) (Deterministic comparison semantics, normative).
- `computed_metrics_total` (integer):
  - Count of `deltas[]` entries with `status=computed`.
- `indeterminate_metrics_total` (integer):
  - Count of `deltas[]` entries with `status=indeterminate`.
- `indeterminate_reasons_breakdown` (object; OPTIONAL):
  - Map of `indeterminate_reason` token → count across `deltas[]` where `status=indeterminate`.
  - Keys MUST be sorted ascending (UTF-8 byte order, no locale).
- `regression_alerted` (boolean)
- `alert_reasons[]`:
  - Stable list of tokens describing which thresholds were exceeded.
  - MUST be sorted ascending (UTF-8 byte order, no locale).
  - MUST NOT include reasons derived from indeterminate delta entries.

Baseline field derivation (normative):

- If `inputs/baseline/manifest.json` exists:

  - `inputs/baseline_run_ref.json` MUST exist.
  - `inputs/baseline_run_ref.json.baseline_manifest_sha256` MUST be present.
  - Reporting MUST compute `sha256(file_bytes)` of `inputs/baseline/manifest.json` and MUST verify
    it `baseline.manifest_ref` MUST equal that `baseline_manifest_sha256` value.
  - On mismatch, `comparability.status` MUST be `indeterminate` with
    `comparability.reason_code="baseline_incompatible"`, `deltas[]` MUST be empty, and the reporting
    stage MUST emit `reporting.regression_compare` with `reason_code=baseline_incompatible`
    (ADR-0005).

- `baseline.manifest_ref` derivation:

  - If `inputs/baseline/manifest.json` exists, `baseline.manifest_ref` MUST be
    `inputs/baseline/manifest.json`.
  - Otherwise, if `inputs/baseline_run_ref.json` records `baseline_manifest_sha256`, then
    `baseline.manifest_ref` SHOULD equal that `baseline_manifest_sha256` value.
  - Otherwise (baseline not readable), `baseline.manifest_ref` MUST be `null`.

- `baseline.generated_at_utc` derivation:

  - If `baseline.run_id` is known and the baseline report exists at
    `runs/<baseline_run_id>/report/report.json`, then `baseline.generated_at_utc` MUST equal the
    baseline report’s top-level `generated_at_utc`.
  - Otherwise, `baseline.generated_at_utc` MUST be `null` (implementations MUST NOT invent a
    timestamp).

Interaction with status recommendation (normative):

- If `regression_alerted=true`, then:
  - `report/thresholds.json.status_recommendation` MUST be set according to the configured policy:
    - If `reporting.regression.alert_status_recommendation=failed`, it MUST be `failed`.
    - Otherwise, it MUST be downgraded to at least `partial`.
  - `report/report.json.status_reasons[]` MUST include `regression_alert`.
- The effective regression alert policy MUST be explicitly configured via
  `reporting.regression.alert_status_recommendation` (see `120_config_reference.md`) and MUST be
  recorded in `report/thresholds.json` under `regression.alert_status_recommendation`.

### Regression comparability keys

Regression analysis assumes that the baseline and current runs were produced with the same effective
pins. For regression comparability decisions, the authoritative pin source is `manifest.versions.*`
(per ADR-0001). Exporters and reporting tools MUST treat the `versions.*` keys below as stable join
dimensions for regression comparisons (ADR-0001). Keys outside these pins (for example, hostnames,
timestamps, absolute paths, or other environment-specific fields) MUST NOT be used to decide
comparability.

#### Comparable pins (normative)

The canonical key set for regression comparability is the ADR-0001 minimum required pin set recorded
under `manifest.versions` for diffable/regression-tested/trended runs, plus an optional
pipeline/config hash key until a canonical `manifest.versions.*` config-hash field is standardized.

The table order is canonical. `report/report.json.regression.comparability_checks[]` MUST be sorted
by `key` ascending (UTF-8 byte order, no locale) and MUST include exactly one entry per key below.

| Key                                                           | Source (baseline & current)                                            | Applicability (deterministic)                    | Requirement                             |
| ------------------------------------------------------------- | ---------------------------------------------------------------------- | ------------------------------------------------ | --------------------------------------- |
| `inputs.range_yaml_sha256`                                    | `manifest.inputs.range_yaml_sha256`                                    | OPTIONAL: compare only when present in both runs | SHOULD match (non-fatal)                |
| `extensions.runner.environment_noise_profile.profile_id`      | `manifest.extensions.runner.environment_noise_profile.profile_id`      | Applicable when present in either run            | MUST match (unless policy allows drift) |
| `extensions.runner.environment_noise_profile.profile_version` | `manifest.extensions.runner.environment_noise_profile.profile_version` | Applicable when present in either run            | MUST match (unless policy allows drift) |
| `extensions.runner.environment_noise_profile.profile_sha256`  | `manifest.extensions.runner.environment_noise_profile.profile_sha256`  | Applicable when present in either run            | MUST match (unless policy allows drift) |
| `versions.criteria_pack_id`                                   | `manifest.versions.criteria_pack_id`                                   | Applicable when present in either run            | MUST match                              |
| `versions.criteria_pack_version`                              | `manifest.versions.criteria_pack_version`                              | Applicable when present in either run            | MUST match                              |
| `versions.mapping_pack_id`                                    | `manifest.versions.mapping_pack_id`                                    | Applicable when present in either run            | MUST match                              |
| `versions.mapping_pack_version`                               | `manifest.versions.mapping_pack_version`                               | Applicable when present in either run            | MUST match (unless policy allows drift) |
| `versions.ocsf_version`                                       | `manifest.versions.ocsf_version`                                       | Always applicable                                | MUST match                              |
| `versions.pipeline_version`                                   | `manifest.versions.pipeline_version`                                   | Always applicable                                | MUST match                              |
| `versions.rule_set_id`                                        | `manifest.versions.rule_set_id`                                        | Applicable when present in either run            | MUST match                              |
| `versions.rule_set_version`                                   | `manifest.versions.rule_set_version`                                   | Applicable when present in either run            | MUST match                              |
| `versions.scenario_id`                                        | `manifest.versions.scenario_id`                                        | Always applicable                                | MUST match                              |
| `versions.scenario_version`                                   | `manifest.versions.scenario_version`                                   | Always applicable                                | MUST match                              |

Notes:

- The `versions.*` key names above correspond to the `manifest.versions` minimum required keys
  defined by ADR-0001 (including scenario, pipeline, OCSF, and pack pins). The reporting spec MUST
  not use `manifest.scenario.*` as the primary comparability pin source for regression runs.

- `inputs.range_yaml_sha256` is an OPTIONAL best-effort pipeline/config hash until a canonical
  `manifest.versions.*` configuration-hash field is standardized. When present, it MUST be a SHA-256
  digest string in `sha256:<lowercase_hex>` form (`^sha256:[0-9a-f]{64}$`). It MUST NOT fail
  comparability by default because it may include environment-dependent configuration.

#### Deterministic check generation (normative)

For each key in the table above, the reporting stage MUST emit exactly one entry in
`comparability_checks[]` with the following deterministic semantics:

- Value extraction:
  - If `key` starts with `versions.`, extract the value from `manifest.versions` using the suffix
    after `versions.` (example: `versions.pipeline_version` maps to
    `manifest.versions.pipeline_version`).
  - If `key` starts with `inputs.`, extract the value from `manifest.inputs` using the suffix after
    `inputs.`.
  - If `key` starts with `extensions.`, extract the value from `manifest.extensions` using the
    suffix after `extensions.` as a dot-delimited path. Example:
    `extensions.runner.environment_noise_profile.profile_id` maps to
    `manifest.extensions.runner.environment_noise_profile.profile_id`.
- `baseline_value` MUST be extracted from the baseline run’s `manifest.json` content that was read
  during baseline resolution. When `inputs/baseline/manifest.json` is present, implementations
  SHOULD use that snapshot as the baseline source.
- `current_value` MUST be extracted from the current run `manifest.json`.
- `match` MUST be computed as byte-for-byte equality of the two string values, with no additional
  normalization. If either value is `null`, `match` MUST be `false`.
- `status` computation:
  - For REQUIRED/MUST-match keys:
    - If `baseline_value` is `null` **and** `current_value` is `null`, and the key is marked
      "Applicable when present in either run": `status=skipped`, `reason_code=not_applicable`.
    - If `baseline_value` is `null`: `status=fail`, `reason_code=missing_baseline_pin` (except where
      a drift policy explicitly allows mismatch; see below).
    - If `current_value` is `null`: `status=fail`, `reason_code=missing_current_pin` (except where a
      drift policy explicitly allows mismatch; see below).
    - If both are present and differ: `status=fail`, `reason_code=pin_mismatch` (except drift-policy
      keys; see below).
    - If both are present and equal: `status=pass`

#### Drift policy (normative)

By default, drift is DISALLOWED for the following pinned keys:

- `versions.mapping_pack_version`
- `extensions.runner.environment_noise_profile.profile_id`
- `extensions.runner.environment_noise_profile.profile_version`
- `extensions.runner.environment_noise_profile.profile_sha256`

If any of the above keys differs between baseline and current run, and the corresponding allow flag
is `false`, the corresponding check MUST be:

- `status=fail`
- `reason_code=drift_disallowed_by_policy`

The allow flags (reporting MUST record these under `comparability.policy`):

- `comparability.policy.allow_mapping_pack_version_drift` (default `false`)
- `comparability.policy.allow_noise_profile_mismatch` (default `false`)

If drift is allowed for a key (allow flag `true`), the mismatch MUST still be recorded in
`comparability_checks[]` (`match=false`), but MUST NOT be surfaced as a failed check. In this case
the corresponding check MUST be `status=pass` and the overall `comparability.status` MUST be at
least `warning`.

For the noise-profile keys, `allow_noise_profile_mismatch=true` applies to all mismatch modes
(including baseline-present/current-missing and baseline-missing/current-present).

#### Evidence pointers (normative)

Every `comparability_checks[]` entry with `status=fail` MUST include `evidence_refs[]` with
run-relative `artifact_path` pointers. At minimum:

- `artifact_path="manifest.json"` (current run)
- `artifact_path="inputs/baseline/manifest.json"` when present; otherwise
  `artifact_path="inputs/baseline_run_ref.json"`

Within each such `evidence_refs[]`, entries MUST be sorted by `artifact_path` ascending.

#### Impact on regression deltas (normative)

If any MUST-match key results in `status=fail`:

- `comparability.status` MUST be `indeterminate`
- `comparability.reason_code` MUST be `baseline_incompatible`
- `deltas[]` MUST be an empty array (`[]`)
- The reporting stage MUST emit `reporting.regression_compare` with
  `reason_code=baseline_incompatible` (ADR-0005)

#### Verification hooks (normative)

- Fixture: changing only `manifest.versions.mapping_pack_version` MUST produce
  `baseline_incompatible` by default, with `comparability_checks[]` including a failed entry whose
  `reason_code` is `drift_disallowed_by_policy`.
- Fixture: changing any runner environment noise profile pin (for example:
  `manifest.extensions.runner.environment_noise_profile.profile_sha256`) MUST produce
  `baseline_incompatible` by default, with `comparability_checks[]` including a failed entry whose
  `reason_code` is `drift_disallowed_by_policy`.
- Fixture: runs with identical `manifest.versions.*` pins but differing environment fields
  (hostnames, timestamps, absolute paths) MUST remain comparable; comparability MUST NOT depend on
  ephemeral fields.
- Fixture: when `inputs/baseline/manifest.json` is present, but
  `inputs/baseline_run_ref.json.baseline_manifest_sha256` is missing or does not match the snapshot
  bytes, regression MUST be indeterminate with `comparability.reason_code="baseline_incompatible"`
  and `deltas[]=[]`.

### Regression deltas

The report MUST compute deltas for comparable metrics as defined in
[Scoring metrics](070_scoring_metrics.md) (Regression comparable metric surface, normative).

At minimum, the report MUST compute regression deltas for:

| Metric                          | Delta computation      | Regression threshold |
| ------------------------------- | ---------------------- | -------------------- |
| `technique_coverage_rate`       | `candidate - baseline` | < -0.0500            |
| `detection_latency_p95_seconds` | `candidate - baseline` | > +60.000            |
| `tier1_field_coverage_pct`      | `candidate - baseline` | < -0.0500            |
| `missing_telemetry_count`       | `candidate - baseline` | > +2                 |
| `bridge_gap_mapping_count`      | `candidate - baseline` | > +5                 |

A regression is flagged when any computed delta exceeds the configured threshold. Indeterminate
delta entries (for example, `excluded_by_config` or `taxonomy_mismatch`) MUST NOT be evaluated
against thresholds and MUST NOT contribute to `regression_alerted` or `alert_reasons[]`.

### Regression summary content

- Baseline `run_id` and timestamp
- Comparable keys status (match/mismatch warnings)
- Delta table with: metric id, baseline value, candidate value, delta, status, indeterminate reason,
  regression flag
- `computed_metrics_total` and `indeterminate_metrics_total`
- (optional) `indeterminate_reasons_breakdown`
- New failures not present in baseline (technique ID + gap category)
- Resolved failures present in baseline but not current

Deterministic ordering (normative):

- The delta table MUST be sorted by `metric_id` ascending (UTF-8 byte order, no locale).
- The "new failures" list and "resolved failures" list MUST be sorted by:
  1. `gap_category` ascending (UTF-8 byte order, no locale)
  1. `technique_id` ascending (UTF-8 byte order, no locale)
  1. `action_id` ascending (UTF-8 byte order, no locale), when present

## Trend tracking

Trending enables longitudinal analysis across runs. Downstream dashboards and exporters MUST use the
stable trending dimensions defined here.

#### Trending keys (normative)

Trending join dimensions MUST be sourced from `manifest.versions` only, per ADR-0001.

Producers MUST NOT derive or "fallback" pins from other artifacts (for example
`manifest.scenario.*`, `bridge/coverage.json`, or snapshot manifests). If required pins are absent,
the run MUST be treated as non-trendable/non-comparable for the affected join surfaces.

See "Trend tracking" for the authoritative set of trend keys and their selectors.

### Non-trending keys

- `run_id`: unique per execution; MUST NOT be used as a trending key
- `started_at_utc`, `ended_at_utc`: timestamps for ordering, not grouping

### Trend history table

Implementations MAY maintain a history table for trend queries. Recommended schema:

```sql
CREATE TABLE run_trends (
  scenario_id TEXT NOT NULL,
  scenario_version TEXT,
  rule_set_id TEXT NOT NULL,
  rule_set_version TEXT NOT NULL,
  pipeline_version TEXT NOT NULL,
  mapping_pack_id TEXT,
  mapping_pack_version TEXT,
  ocsf_version TEXT,
  criteria_pack_id TEXT,
  criteria_pack_version TEXT,
  run_id TEXT NOT NULL,
  started_at_utc TIMESTAMP NOT NULL,
  technique_coverage_rate REAL,
  detection_latency_p95_seconds REAL,
  tier1_field_coverage_pct REAL,
  status TEXT,
  PRIMARY KEY (run_id)
);
```

### Regression alerts

Exporters SHOULD emit alerts when:

- Technique coverage drops > 0.05 (5 percentage points) vs trailing 5-run average
- Detection latency p95 increases > 50% vs trailing 5-run average
- New gap categories appear that were not present in prior runs

## Threshold evaluation output

The reporting stage MUST emit `report/thresholds.json` for CI integration.

Determinism and units (normative):

- `gates[]` MUST be sorted by `gate_id` (UTF-8 byte order, no locale).
- Gate thresholds and actuals are interpreted by `gate_id`:
  - All `*_rate` and `*_coverage` gates use unitless fractions in `[0.0, 1.0]`.
  - `max_allowed_latency_seconds` uses seconds.
- `status_recommendation` MUST be one of `success`, `partial`, or `failed`.

### Thresholds JSON schema

`report/thresholds.json` MUST validate against the contract schema
[`thresholds.schema`](../contracts/thresholds.schema.json) as registered in the contract registry.

The JSON object below is a non-normative example.

Determinism requirements (v0.1):

- The `gates[]` array MUST be sorted by `gate_id` ascending (UTF-8 byte order, no locale).
- `gate_id` values MUST be unique within `gates[]`.

```json
{
  "contract_version": "0.1.0",
  "run_id": "<uuid>",
  "evaluated_at_utc": "<ISO8601>",
  "overall_pass": true,
  "regression": {
    "alert_status_recommendation": "partial"
  },  
  "gates": [
    {
      "gate_id": "min_technique_coverage",
      "threshold": 0.75,
      "actual": 0.82,
      "pass": true
    },
    {
      "gate_id": "min_tier1_field_coverage",
      "threshold": 0.80,
      "actual": 0.78,
      "pass": false,
      "degradation_reason": "tier1_coverage_below_threshold"
    }
  ],
  "status_recommendation": "partial"
}
```

Required gates (v0.1):

- `min_technique_coverage` (default: 0.75)
- `max_allowed_latency_seconds` (default: 300)
- `min_tier1_field_coverage` (default: 0.80)
- `max_missing_telemetry_rate` (default: 0.10)
- `max_normalization_gap_rate` (default: 0.05)
- `max_bridge_gap_mapping_rate` (default: 0.10)
- `max_bridge_gap_feature_rate` (default: 0.40)
- `max_bridge_gap_other_rate` (default: 0.02)

Regression gates (required only when a baseline is provided):

- `regression_alert`:
  - The gate MUST fail when `report/report.json.regression.regression_alerted=true`.
  - When the gate fails, `degradation_reason` MUST be `regression_alert`.
  - The reporting stage MUST apply the "Interaction with status recommendation" rules in
    [Regression JSON contract](#regression-json-contract-normative).

## Report JSON schema

The `report/report.json` output MUST conform to the following structure:

```json
{
  "contract_version": "0.1.0",
  "run_id": "<uuid>",
  "generated_at_utc": "<ISO8601>",
  "status": "success | partial | failed",
  "status_reasons": ["<reason_code>"],
  "status_reason_details": [
    {
      "reason_code": "<reason_code>",
      "measurement_layer": "telemetry | normalization | detection | scoring",
      "evidence_refs": [
        {
          "artifact_path": "<run-relative path>",
          "selector": "<optional selector>",
          "handling": "present | withheld | quarantined | absent"
        }
      ]
    }
  ],
  "executive_summary": {
    "scenario_id": "<string>",
    "scenario_version": "<string>",
    "scenario_posture": {
      "mode": "baseline | assumed_compromise"
    },    
    "techniques_executed": 10,
    "techniques_covered": 8,
    "coverage_pct": 0.80,
    "duration_seconds": 300,
    "target_count": 2
  },
  "plan": {
    "model_version": "<semver>",
    "plan_type": "<string>",
    "node_count": 10,
    "group_count": 1,
    "templates_executed": 10
  },  
  "coverage": { },
  "latency": { },
  "fidelity": { },
  "gaps": {
    "by_category": {
      "<gap_category>": {
        "measurement_layer": "telemetry | normalization | detection | scoring",
        "count": 0,
        "rate": 0.0,
        "top_failures": [
          {
            "gap_category": "<gap_category>",
            "measurement_layer": "telemetry | normalization | detection | scoring",
            "technique_id": "<string>",
            "action_id": "<string>",
            "evidence_refs": [
              {
                "artifact_path": "<run-relative path>",
                "selector": "<optional selector>",
                "handling": "present | withheld | quarantined | absent"
              }
            ],
            "remediation_hint": "<string>"
          }
        ]
      }
    },
    "top_failures": [
      {
        "gap_category": "<gap_category>",
        "measurement_layer": "telemetry | normalization | detection | scoring",
        "technique_id": "<string>",
        "action_id": "<string>",
        "evidence_refs": [
          {
            "artifact_path": "<run-relative path>",
            "selector": "<optional selector>",
            "handling": "present | withheld | quarantined | absent"
          }
        ],
        "remediation_hint": "<string>"
      }
    ]
  },
  "tier1_coverage": { },
  "per_source": [ ],
  "bridge_health": { },
  "criteria_evaluation": { },
  "cleanup_verification": { },
  "event_volume": { },
  "versions": { },
  "regression": {
    "baseline": {
      "run_id": "<uuid|null>",
      "generated_at_utc": "<ISO8601|null>",
      "manifest_ref": "<string|null>"
    },
    "comparability": {
      "status": "comparable | warning | indeterminate",
      "reason_code": "<string|null>",
      "policy": {
        "allow_mapping_pack_version_drift": false
      },
      "evidence_refs": [
        {
          "artifact_path": "inputs/baseline/manifest.json",
          "selector": "json_pointer:/versions",
          "handling": "present | withheld | quarantined | absent"
        },
        {
          "artifact_path": "inputs/baseline_run_ref.json",
          "selector": "json_pointer:",
          "handling": "present | withheld | quarantined | absent"
        },
        {
          "artifact_path": "manifest.json",
          "selector": "json_pointer:/versions",
          "handling": "present | withheld | quarantined | absent"
        }
      ]
    },
    "comparability_checks": [
      {
        "key": "versions.pipeline_version",
        "baseline_value": "<string|null>",
        "current_value": "<string|null>",
        "match": true,
        "status": "pass | fail | skipped",
        "reason_code": "<string|null>",
        "evidence_refs": [
          {
            "artifact_path": "inputs/baseline/manifest.json",
            "selector": "json_pointer:/versions/pipeline_version",
            "handling": "present | withheld | quarantined | absent"
          },
          {
            "artifact_path": "manifest.json",
            "selector": "json_pointer:/versions/pipeline_version",
            "handling": "present | withheld | quarantined | absent"
          }
        ]
      }
    ],
    "metric_surface_ref": "070_scoring_metrics.md#regression-comparable-metric-surface-normative",
    "deltas": [
      {
        "metric_id": "<string>",
        "kind": "<string>",
        "unit": "<string>",
        "baseline_value": 0,
        "candidate_value": 0,
        "delta": 0,
        "tolerance": 0,
        "status": "computed | indeterminate",
        "indeterminate_reason": "<string|null>",
        "within_tolerance": true,
        "regression_flag": false,
        "evidence_refs": [ ]
      }
    ],
    "computed_metrics_total": 0,
    "indeterminate_metrics_total": 0,
    "indeterminate_reasons_breakdown": { },
    "regression_alerted": false,
    "alert_reasons": [ ]
  },
  "extensions": {
    "execution_context": {
      "principal_context": {
        "artifact_path": "runner/principal_context.json",
        "handling": "present | withheld | quarantined | absent",
        "counts_by_kind": { },
        "unknown_kind_actions": 0,
        "principals": [ ]
      },
      "cache_provenance": {
        "artifact_path": "logs/cache_provenance.json",
        "present": false,
        "by_cache": [ ]
      }
    }
  }
}
```

Full schema definition: `report.schema.json` see `docs/contracts/report.schema.json`.

## HTML report structure

The HTML report SHOULD follow this layout:

1. Header: Run ID, status badge, scenario name, execution timestamp
1. Executive summary card: Key metrics at a glance
1. Navigation: Jump links to each section
1. Sections: Each section from [Human-readable report sections](#human-readable-report-sections)
1. Footer: Version inventory, generation timestamp, links to raw artifacts

### Styling guidance

- Use semantic HTML5 elements
- Status indicators: green (success), yellow (partial), red (failed)
- Tables SHOULD be sortable where appropriate
- Threshold violations SHOULD be visually flagged
- Include collapsible detail sections for large tables

### Self-contained, local-only asset policy

To align with the Operator Interface static file serving model (see `115_operator_interface.md`) and
to keep the report in a "Metta-style" minimal footprint, the HTML report is intentionally
self-contained.

Normative requirements:

- The HTML report MUST NOT reference remote assets.
  - The rendered HTML MUST NOT contain absolute `http://` or `https://` URLs in any attribute value
    (`href`, `src`, `action`, etc.).
- The HTML report MUST NOT rely on external `.css` or `.js` files.
  - The Operator Interface serves `.html` under a strict extension allowlist; external `.css` /
    `.js` files are not a supported dependency.
- All styling MUST be embedded via a `<style>` element in the document `<head>`.
- If collapsible/interactive behavior is needed, the report SHOULD prefer native HTML elements (for
  example, `<details>` / `<summary>`) and SHOULD avoid JavaScript entirely.
- If JavaScript is used in a future revision, it MUST be optional (the report remains readable with
  scripts disabled) and MUST NOT fetch remote resources.
- Any dynamic string content rendered from run artifacts MUST be HTML-escaped.

Observability:

- A "no remote assets" lint can be implemented by scanning the rendered `report/report.html` for:
  - `http://` or `https://`
  - `<script` tags with a `src=` attribute
  - `<link` tags with an `href=` attribute
  - `<base` tags
  - `<meta http-equiv="refresh"` (case-insensitive)

Verification hooks:

- Fixture: generate `report/report.html` from a deterministic `report/report.json` fixture and
  assert it passes the lint above.

## CI integration

### Exit codes

The reporting stage MUST set exit codes aligned with
[ADR-0005](../adr/ADR-0005-stage-outcomes-and-failure-classification.md):

| Exit code | Meaning                                                 |
| --------- | ------------------------------------------------------- |
| `0`       | Run status `success`; all gates passed                  |
| `10`      | Run status `partial`; artifacts usable but gates failed |
| `20`      | Run status `failed`; artifacts not usable               |

### CI workflow integration

```yaml
# Example GitHub Actions step
- name: Evaluate thresholds
  run: |
    STATUS=$(jq -r '.status_recommendation' report/thresholds.json)
    if [ "$STATUS" = "failed" ]; then exit 20; fi
    if [ "$STATUS" = "partial" ]; then exit 10; fi
    exit 0
```

## References

- [Manifest schema](../contracts/manifest.schema.json)
- [Summary schema](../contracts/summary.schema.json)
- [Bridge coverage schema](../contracts/bridge_coverage.schema.json)
- [Mapping coverage schema](../contracts/mapping_coverage.schema.json)
- [Criteria pack manifest schema](../contracts/criteria_pack_manifest.schema.json)
- [report schema](../contracts/report.schema.json)
- [Scoring metrics specification](070_scoring_metrics.md)
- [OCSF field tiers specification](055_ocsf_field_tiers.md)
- [Sigma-to-OCSF bridge specification](065_sigma_to_ocsf_bridge.md)
- [ADR-0005: Stage outcomes and failure classification](../adr/ADR-0005-stage-outcomes-and-failure-classification.md)

## Changelog

| Date       | Change                                                                           |
| ---------- | -------------------------------------------------------------------------------- |
| 2026-01-24 | update                                                                           |
| 2026-01-22 | Specify self-contained, local-only HTML report constraints (Metta-style minimal) |
| 2026-01-18 | Codify regression JSON contract and measurement-layer evidence pointers for gaps |
