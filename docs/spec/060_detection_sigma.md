---
title: Detection Rules (Sigma)
description: Defines how Purple Axiom compiles and evaluates Sigma rules against normalized OCSF events.
status: draft
category: spec
tags: [sigma, detection, ocsf]
related:
  - 065_sigma_to_ocsf_bridge.md
  - 070_scoring_metrics.md
  - 080_reporting.md
  - 025_data_contracts.md
  - ADR-0005-stage-outcomes-and-failure-classification.md
  - ADR-0007-state-machines.md
---

# Detection Rules (Sigma)

## Stage contract header

### Stage ID

- `stage_id`: `detection`

### Owned output roots (published paths)

- `bridge/` (compiled evaluation plans + mapping pack snapshot + coverage)
- `detections/` (detection instances)

### Inputs/Outputs

This section is the stage-local view of:

- the stage boundary table in
  [ADR-0004](../adr/ADR-0004-deployment-architecture-and-inter-component-communication.md), and
- the contract bindings in [contract_registry.json](../contracts/contract_registry.json).

#### Contract-backed outputs

| contract_id            | path/glob                           | Required?                                      |
| ---------------------- | ----------------------------------- | ---------------------------------------------- |
| `bridge_compiled_plan` | `bridge/compiled_plans/*.plan.json` | required (when `detection.sigma.enabled=true`) |
| `bridge_coverage`      | `bridge/coverage.json`              | required (when `detection.sigma.enabled=true`) |
| `bridge_mapping_pack`  | `bridge/mapping_pack_snapshot.json` | required (when `detection.sigma.enabled=true`) |
| `bridge_router_table`  | `bridge/router_table.json`          | required (when `detection.sigma.enabled=true`) |
| `detection_instance`   | `detections/detections.jsonl`       | required (when `detection.sigma.enabled=true`) |

#### Required inputs

| contract_id           | Where found                    | Required?                            |
| --------------------- | ------------------------------ | ------------------------------------ |
| `range_config`        | `inputs/range.yaml`            | required                             |
| `manifest`            | `manifest.json`                | required (version pins + provenance) |
| `ocsf_event_envelope` | `normalized/ocsf_events.jsonl` | required                             |

Notes:

- Detection evaluation is defined over the normalized store. v0.1 binds the normalized stream as
  JSONL (`normalized/ocsf_events.jsonl`).
- Rule inputs (Sigma YAML) and mapping packs are pack-like **non-contract** inputs; the stage
  snapshots the effective mapping pack material to `bridge/mapping_pack_snapshot.json`.

### Config keys used

- `detection.*` (mode, join tolerance)
- `detection.sigma.*` (rule inputs)
- `detection.sigma.bridge.*` (mapping pack selection, backend selection, caching, fail mode)

### Default fail mode and outcome reasons

- Default `fail_mode`: `fail_closed`
- Stage outcome reason codes: see
  [ADR-0005](../adr/ADR-0005-stage-outcomes-and-failure-classification.md) § "Detection stage
  (`detection`)".

### Isolation test fixture(s)

- `tests/fixtures/sigma_rule_tests/<test_id>/`

See the [fixture index](100_test_strategy_ci.md#fixture-index) for the canonical fixture-root
mapping.

## Overview

This specification defines how Purple Axiom compiles and evaluates Sigma rules against normalized
OCSF events using the Sigma-to-OCSF Bridge. Sigma rules are the default, portable detection language
for Purple Axiom. Rules are evaluated against **normalized OCSF events** (not raw logs) using the
**Sigma-to-OCSF Bridge**.

See the [Sigma-to-OCSF Bridge specification][sigma-bridge].

## Why Sigma

- Portable, generic detection rule format (YAML) with broad community content
- Separates detection logic from any specific SIEM or query language

## Rule selection and filtering

### Supported rule metadata

In addition to the required fields, Purple Axiom recognizes the following Sigma metadata for
filtering and reporting:

| Field            | Purpose                                                         | Default behavior                              |
| ---------------- | --------------------------------------------------------------- | --------------------------------------------- |
| `status`         | Rule maturity (`experimental`, `test`, `stable`)                | All statuses evaluated unless filtered        |
| `level`          | Severity (`informational`, `low`, `medium`, `high`, `critical`) | All levels evaluated unless filtered          |
| `falsepositives` | Known false positive contexts                                   | Recorded in compiled plan for operator review |
| `author`         | Rule authorship                                                 | Recorded for provenance                       |
| `references`     | External references (URLs)                                      | Recorded for provenance                       |

### Configuration-driven filtering

Rule selection MAY be constrained via configuration (see the
[configuration reference](120_config_reference.md)).

v0.1 supported selection inputs:

- `detection.sigma.rule_paths`: directories/files containing Sigma YAML.
- `detection.sigma.rule_set_version`: pinned rule set version for reporting/regression joins.
- `detection.sigma.limits.max_rules`: optional hard cap on the number of rules loaded.

Deterministic rule loading requirements (normative):

- Implementations MUST discover rule files deterministically:
  - Treat `detection.sigma.rule_paths[]` as an ordered list.
  - For a directory entry at index `i`, recursively include files ending in `.yml` or `.yaml`.
  - For a file entry at index `i`, include only that file.
  - For each included file, define `ruleset_path` deterministically:
    - directory entry: the file path relative to the directory root
    - file entry: the basename of the file
    - in both cases: separators MUST be normalized to `/`
  - Before parsing/loading, the discovered file list MUST be sorted by the stable key tuple:
    1. `i` ascending
    1. `ruleset_path` ascending (UTF-8 bytewise lexical ordering, no locale)
- Each loaded rule MUST have a non-empty `id`.
- Rule IDs MUST be unique within the effective loaded ruleset. If duplicate `id` values are
  detected, the detection stage MUST fail closed with stage-level reason code
  `sigma_ruleset_load_failed` ([ADR-0005: Stage outcomes and failure classification][adr-0005]).

Reserved (v0.2+; requires config schema + reference update before use):

- Filtering by ATT&CK technique id (allow/deny lists).
- Filtering by Sigma `status` and/or `level`.

When selection constraints are applied, the run manifest MUST record the effective selection inputs,
and excluded rules MUST NOT appear in coverage metrics.

## ATT&CK technique mapping

### Tag extraction

Sigma rules encode ATT&CK mappings in the `tags` array using the `attack.tXXXX` convention.

The detection engine MUST:

- Extract technique IDs from tags matching the pattern `attack\.t\d{4}(?:\.\d{3})?`
  (case-insensitive).
- Normalize extracted IDs to uppercase (example: `attack.t1059.001` → `T1059.001`).
- Populate `technique_ids` in detection instances as a deduplicated array sorted ascending using
  bytewise UTF-8 lexical ordering (no locale).

### Sub-technique handling

When a rule tags both a technique and its sub-technique (example: `attack.t1059`,
`attack.t1059.001`):

- The detection instance MUST include both.
- Coverage metrics MUST credit the most specific match (sub-technique) for scoring joins.

### Unmapped rules

Rules without valid ATT&CK tags:

- Are still evaluated and may produce detection instances.
- Are excluded from technique coverage metrics.
- SHOULD be surfaced in reporting for operator review (at minimum as a count; MAY include a list of
  `rule_id`s).

## Rule lifecycle

- The `rules/` directory is versioned and tagged.
- Each rule MUST declare:
  - `title`, `id`, `status`
  - `logsource` (used for routing via the Sigma-to-OCSF Bridge)
  - `detection` selectors and conditions
  - `tags` (include ATT&CK technique tags when available)

## Execution model

Sigma evaluation is a two-stage process.

1. **Compile (bridge-aware)**
   - Select a bridge mapping pack (router + field aliases) per
     `detection.sigma.bridge.mapping_pack_id` and `detection.sigma.bridge.mapping_pack_version`.
   - Route the rule: `logsource` to an OCSF class filter (and optional producer/source predicates
     via `filters[]` OCSF filter objects).
   - Rewrite Sigma field references to OCSF JSONPaths (or backend-native column expressions).
     - If a rule requires `raw.*`, behavior is governed by
       `detection.sigma.bridge.raw_fallback_enabled` and MAY render the rule non-executable with
       reason code `raw_fallback_disabled` and reason domain `bridge_compiled_plan`.
   - Produce a backend-neutral compiled-plan IR (bridge IR):
     - The bridge IR is `pa_eval_v1` and is persisted in `bridge/compiled_plans/<rule_id>.plan.json`
       under `backend.plan_kind="pa_eval_v1"` and `backend.plan` (see `065_sigma_to_ocsf_bridge.md`,
       "Plan IR format (pa_eval_v1)").
   - Select a backend executor to run the IR:
     - Batch: `native_pcre2` MUST be the v0.1 default when `detection.sigma.bridge.backend` is
       omitted.
     - Other batch backends MAY lower deterministically from the IR while preserving semantics.
     - Streaming: optional (v0.2+; backend-defined).
1. **Evaluate**
   - Execute the plan over the run's OCSF event store.
   - Emit `detection_instance` rows for each match group.
   - For event rules, each match group MUST correspond to exactly one matched event id. The
     evaluator MUST emit one detection instance per matched event with:
     - `matched_event_ids = [<event_id>]`
     - `first_seen_utc == last_seen_utc` (event time)
   - For correlation rules, each match group MUST correspond to exactly one correlation window and
     group key. The evaluator MUST emit one detection instance per satisfied group with:
     - `matched_event_ids = [<event_id>, ...]`
     - `first_seen_utc = min(event time)` over contributing events
     - `last_seen_utc = max(event time)` over contributing events

Note (backend pluralism and determinism): the bridge IR (`pa_eval_v1`) is backend-neutral. Any batch
backend that claims `pa_eval_v1` support MUST preserve IR semantics and MUST be qualified via the
cross-backend conformance harness on the same BDP fixture (see `100_test_strategy_ci.md`, "Evaluator
conformance harness").

## State machine integration

The detection stage lifecycle is a candidate for explicit state machine modeling per
[ADR-0007: State machines for lifecycle semantics][adr-0007] to improve determinism, observability,
and testability.

This section is **representational (non-normative)**. Lifecycle authority remains:

- [ADR-0005: Stage outcomes and failure classification][adr-0005] (stage outcomes and reason codes)
- [Data contracts specification][data-contracts] (required artifacts when detection is enabled)
- [Sigma-to-OCSF Bridge specification][sigma-bridge] (per-rule compiled plans and non-executable
  reasons)

Representational stage lifecycle (v0.1):

- `pending` → `running` → `published` (success path)
- `pending` → `running` → `failed` (fatal stage failure)
- `pending` → `skipped` (stage disabled)

Representational per-rule lifecycle (v0.1; within the stage):

- `loaded` → `compiled(executable=true)` → `evaluated`
- `loaded` → `compiled(executable=true)` → `evaluated(error)` (recorded as non-executable with
  `non_executable_reason.reason_code: "backend_eval_error"`)
- `loaded` → `compiled(executable=false)` (non-executable; recorded in `bridge/compiled_plans/`)

Observable anchors (run bundle):

- Stage outcome: `manifest.json` / `logs/health.json` entry for stage `detection` (status +
  reason_code).
- Publish gate artifacts when enabled: `detections/detections.jsonl` and `bridge/**`.
- Per-rule compiled plan files: `bridge/compiled_plans/<rule_id>.plan.json` (executable flag and
  `non_executable_reason`).

## Non-executable rules

A rule is classified as **non-executable** when the bridge cannot (a) compile it into a valid
backend plan, or (b) execute the compiled plan to completion for the current run. Non-executable
rules are recorded in `bridge/compiled_plans/<rule_id>.plan.json` with `executable: false` and a
stable `non_executable_reason.reason_code` and `non_executable_reason.reason_domain` MUST equal
`bridge_compiled_plan`. (including runtime evaluation failures such as `backend_eval_error`).

The `non_executable_reason` object MUST also include a human-readable explanation.

### Reason codes (normative)

| Reason code               | Category      | Description                                                                                                      |
| ------------------------- | ------------- | ---------------------------------------------------------------------------------------------------------------- |
| `unroutable_logsource`    | Routing       | Sigma `logsource` matches no router entry                                                                        |
| `unmapped_field`          | Field alias   | Sigma field has no alias mapping                                                                                 |
| `raw_fallback_disabled`   | Field alias   | Rule requires `raw.*` but fallback is disabled                                                                   |
| `ambiguous_field_alias`   | Field alias   | Alias resolution is ambiguous for the routed scope                                                               |
| `unsupported_modifier`    | Sigma feature | Modifier cannot be expressed in the backend                                                                      |
| `unsupported_operator`    | Sigma feature | Operator not in supported subset                                                                                 |
| `unsupported_regex`       | Sigma feature | Regex pattern uses constructs rejected by backend policy (v0.1 default: PCRE2 with bounded execution for `\|re`) |
| `unsupported_value_type`  | Sigma feature | Value type incompatible with operator                                                                            |
| `unsupported_correlation` | Sigma feature | Correlation rule uses unsupported correlation type or semantics for the selected backend                         |
| `unsupported_aggregation` | Sigma feature | Aggregation semantics are out of scope for v0.1 outside Sigma correlations (default backend: `native_pcre2`)     |
| `backend_compile_error`   | Backend       | Backend compilation failed                                                                                       |
| `backend_eval_error`      | Backend       | Backend evaluation failed at runtime                                                                             |

Non-executable rules do not produce detection instances but are included in bridge coverage
reporting and contribute to gap classification.

See [ADR-0005: Stage outcomes and failure classification][adr-0005] for stage-level failure
semantics.

#### Gap category mapping for non-executable rules (normative):

When a rule is marked non-executable, the detection or scoring pipeline MUST classify downstream
gaps using the scoring taxonomy. The minimum required mapping (from compiled plan
`non_executable_reason.reason_code`) is:

| Reason code group                                                                                                                                   | Gap category         |
| --------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------- |
| `unroutable_logsource`, `unmapped_field`, `raw_fallback_disabled`, `ambiguous_field_alias`                                                          | `bridge_gap_mapping` |
| `unsupported_modifier`, `unsupported_operator`, `unsupported_regex`, `unsupported_value_type`, `unsupported_correlation`, `unsupported_aggregation` | `bridge_gap_feature` |
| `backend_compile_error`, `backend_eval_error`                                                                                                       | `bridge_gap_other`   |

### Fail-closed behavior

If a rule cannot be routed (unknown `logsource`) or references unmapped fields, it MUST be reported
as **non-executable** for that run, with reasons recorded in the run report.

## Outputs

- Output file: `detections/detections.jsonl` (one JSONL line per detection instance)

Each detection instance includes:

- `rule_id`, `rule_title`, `rule_source = "sigma"`
- `run_id`, optional `scenario_id`
- `first_seen_utc`, `last_seen_utc`
- `matched_event_ids` (references `metadata.event_id` in the OCSF store)
- `technique_ids` when available
- Recommended: `extensions.bridge` provenance (`mapping_pack_id`, `mapping_pack_version`, `backend`,
  `compiled_at_utc`, and `fallback_used` when any `raw.*` fallback is required)

### Regression comparable detection metric inputs (normative):

- Detection-stage comparable surfaces for regression analysis MUST be derived from deterministic run
  bundle artifacts and MUST NOT depend on host-specific paths or non-deterministic iteration order.
- For v0.1, the comparable detection metric inputs are:
  - Bridge compilation and routing health derived from `bridge/coverage.json`, including
    non-executable reason distributions (used by the reporting "Sigma-to-OCSF bridge health"
    section).
  - Detection instances from `detections/detections.jsonl` (used for coverage and attribution joins,
    and for auditability of "detections exist" vs "no detections produced").

### Regression comparability keys (normative):

- Regression comparability decisions MUST use pinned values recorded under `manifest.versions.*` as
  the authoritative source of join dimensions (ADR-0001). Implementations MUST NOT use environment-
  derived identifiers (for example, hostnames, absolute paths, local usernames, ephemeral
  timestamps) as comparability keys.

- For runs intended for regression comparison, the run manifest MUST record pinned versions for the
  ADR-0001 minimum join dimensions:

  - `manifest.versions.scenario_id` and `manifest.versions.scenario_version`
  - `manifest.versions.pipeline_version`
  - `manifest.versions.ocsf_version`

- In addition, the run manifest MUST record pinned versions for enabled pack-like artifacts:

  - `manifest.versions.rule_set_id` and `manifest.versions.rule_set_version` when Sigma evaluation
    is enabled.
  - `manifest.versions.mapping_pack_id` and `manifest.versions.mapping_pack_version` when the
    Sigma-to-OCSF bridge is enabled.
  - `manifest.versions.criteria_pack_id` and `manifest.versions.criteria_pack_version` when criteria
    evaluation is enabled (even though the detection stage does not consume criteria directly, the
    regression comparability posture is run-level and MUST be coherent across reporting outputs).

- Drift gate semantics (normative):

  - By default, `manifest.versions.mapping_pack_version` drift between baseline and current runs
    MUST be treated as not comparable.
  - The only exception is an explicit regression policy (recorded in the run report) that allows
    mapping pack version drift (for example,
    `report/report.json.regression.comparability.policy.allow_mapping_pack_version_drift=true`).
  - When drift is disallowed and a mismatch is observed, the reporting regression-compare substage
    MUST record `baseline_incompatible`, and regression deltas MUST NOT be computed (or MUST be
    marked indeterminate) for detection-stage comparable surfaces.

### Deterministic emission

- When Sigma evaluation is enabled, implementations MUST emit `detections/detections.jsonl` even
  when there are zero matches (empty file). Consumers MUST treat a missing file as a contract
  failure.
- Timestamp normalization (normative):
  - `first_seen_utc` and `last_seen_utc` MUST be serialized as UTC RFC 3339 strings in the fixed
    form `YYYY-MM-DDTHH:MM:SS.mmmZ` (exactly 3 fractional digits).
  - Timestamp values MUST be derived from matched event-time, not ingest-time.
- Each detection instance MUST sort `matched_event_ids` using bytewise UTF-8 lexical ordering
  (case-sensitive, no locale).
- If present, each detection instance MUST sort `technique_ids` using bytewise UTF-8 lexical
  ordering (case-sensitive, no locale).
- The file MUST be ordered deterministically by the following stable key tuple (bytewise UTF-8
  lexical ordering for all string comparisons):
  1. `rule_id` ascending
  1. `first_seen_utc` ascending
  1. `last_seen_utc` ascending
  1. `matched_event_ids` ascending by lexicographic comparison of the (already-sorted) string array
- Each JSONL line MUST be encoded as UTF-8 and MUST end with a single LF (`\n`).
- Implementations SHOULD serialize each object without insignificant whitespace and with a
  deterministic key ordering to maximize byte-level stability across runtimes.

### Required conformance tests (regression comparability)

CI MUST include fixtures that validate regression comparability behavior and evidence satisfiability
for detection-stage gaps.

#### Fixture A: Strict mode (default) - mapping pack version drift is NOT comparable

- Setup:

  - Constant telemetry + normalization inputs, but `manifest.versions.mapping_pack_version` differs
    between baseline and current runs.
  - No explicit “allow drift” policy is enabled.

- Expected:

  - The regression comparability decision MUST be recorded deterministically as not comparable:
    - `report/report.json.regression.comparability.status` is `indeterminate`
    - `report/report.json.regression.comparability.reason_code` is `baseline_incompatible`
  - `report/report.json.regression.comparability_checks[]` MUST include an entry for the mapping
    pack version key indicating a policy-disallowed drift condition (for example, reason code
    `drift_disallowed_by_policy`), and the run MUST NOT emit computed regression deltas for the
    detection-stage comparable surfaces (deltas MUST be empty or marked indeterminate
    deterministically).
  - Evidence references MUST be satisfiable and MUST include run-relative pointers to:
    - `manifest.json` (current run)
    - `inputs/baseline_run_ref.json` and/or `inputs/baseline/manifest.json` (when present)

#### Fixture B: Allow-drift mode - mapping pack version drift is explicitly allowed

- Setup:

  - Constant telemetry + normalization inputs, but `manifest.versions.mapping_pack_version` differs
    between baseline and current runs.
  - An explicit regression policy allowing mapping pack version drift is enabled and recorded in the
    run report (for example,
    `report/report.json.regression.comparability.policy.allow_mapping_pack_version_drift=true`).

- Expected:

  - The mismatch MUST be recorded in `comparability_checks[]`, and the overall regression
    `comparability.status` MUST be at least `warning` (comparison MAY proceed).
  - Detection-stage regression deltas MUST be computed and MUST remain attributable to the
    `detection` measurement layer.
  - For a scenario intentionally constructed to surface mapping drift, `bridge_gap_mapping`
    rates/counts SHOULD increase between baseline and current while telemetry and normalization are
    held constant.
  - Evidence references MUST be satisfiable and include `bridge/coverage.json` and (when present)
    `detections/detections.jsonl`.

## Joining detections to ground truth

The scoring stage joins detection instances to ground truth actions to compute coverage and latency
metrics.

### Join semantics

A detection instance is **attributed** to a ground truth action when all of the following hold:

1. The detection's `technique_ids` intersect with the action's `technique_id`.
1. The detection's `first_seen_utc` falls within the configured time window relative to the action's
   `timestamp_utc`:
   - Window start: `action.timestamp_utc - detection.join.clock_skew_tolerance_seconds`
   - Window end: `action.timestamp_utc + scoring.thresholds.max_allowed_latency_seconds`
1. The detection's matched events originate from the action's `target_asset_id` (when asset
   attribution is available).

Note (v0.1):

- Since correlation/aggregation rules are out of scope, each detection instance MUST represent
  exactly one matched event (`matched_event_ids` length 1). This ensures `first_seen_utc`
  corresponds to the matched event time deterministically for join and latency metrics.

### Unattributed detections

Detections that match events but cannot be attributed to a ground truth action:

- Are recorded in `detections/detections.jsonl`.
- Are excluded from technique coverage metrics.
- MAY indicate:
  - Legitimate background activity (true positives unrelated to the scenario).
  - Rule logic issues (overly broad detection).
  - Time window misalignment.

The report SHOULD surface unattributed detection counts for operator review.

## Detection instance schema

Detection instances MUST validate against
[`detection_instance.schema.json`](../contracts/detection_instance.schema.json).

### Required fields

| Field               | Type   | Description                                                                            |
| ------------------- | ------ | -------------------------------------------------------------------------------------- |
| `rule_id`           | string | Sigma rule identifier (typically a UUID)                                               |
| `rule_title`        | string | Sigma rule title                                                                       |
| `rule_source`       | string | Always `"sigma"` for Sigma-originated detections                                       |
| `run_id`            | string | Run identifier                                                                         |
| `first_seen_utc`    | string | RFC 3339 UTC timestamp in fixed form `YYYY-MM-DDTHH:MM:SS.mmmZ` (event-time)           |
| `last_seen_utc`     | string | RFC 3339 UTC timestamp in fixed form `YYYY-MM-DDTHH:MM:SS.mmmZ` (event-time)           |
| `matched_event_ids` | array  | Sorted array of `metadata.event_id` references (v0.1: exactly 1 event id per instance) |

### Recommended fields

| Field               | Type   | Description                                          |
| ------------------- | ------ | ---------------------------------------------------- |
| `scenario_id`       | string | Scenario identifier (when available)                 |
| `technique_ids`     | array  | Extracted ATT&CK technique IDs                       |
| `extensions.bridge` | object | Bridge provenance (mapping pack, backend, fallback)  |
| `extensions.sigma`  | object | Original Sigma metadata (`logsource`, `level`, etc.) |

## Rule provenance

### Detection instances SHOULD include rule provenance in `extensions.sigma`:

| Field             | Type   | Description                                       |
| ----------------- | ------ | ------------------------------------------------- |
| `logsource`       | object | Original Sigma `logsource` (verbatim)             |
| `level`           | string | Sigma severity level                              |
| `status`          | string | Sigma maturity status                             |
| `rule_sha256`     | string | SHA-256 of canonical rule content                 |
| `rule_source_ref` | string | Origin reference (example: `sigmahq/sigma@v0.22`) |

### Canonical rule hashing (normative)

To make rule drift detection deterministic across platforms, `extensions.sigma.rule_sha256` MUST be
computed as:

1. Read the rule file bytes as stored in the selected ruleset (`detection.sigma.rule_paths`).
1. If the content begins with a UTF-8 BOM, remove the BOM.
1. Normalize line endings by converting CRLF (`\r\n`) and CR (`\r`) to LF (`\n`).
1. Compute SHA-256 over the resulting byte sequence.
1. Serialize as `sha256:<lowercase_hex>` (64 hex chars, lowercase).

### Rule provenance enables:

- Attribution of community vs custom rules in reporting.
- Regression detection when rule content changes.
- Filtering by rule maturity in downstream dashboards.

### Regression comparability requirements (normative):

- For runs intended to be diffable, regression-tested, or trended:
  - Detection outputs SHOULD include `extensions.sigma.rule_sha256` and
    `extensions.sigma.rule_source_ref` so rule drift is explainable in reports.
  - Detection outputs SHOULD include sufficient `extensions.bridge` provenance to explain
    compilation differences (example: mapping pack version and fallback usage).
- Consumers MUST treat runs as not comparable for regression deltas when required version pins for
  the rule set or mapping pack are missing from `manifest.versions`.

## Gap classification

When a ground truth action lacks a matching detection, the scoring stage classifies the gap using
the normative taxonomy defined in [Scoring metrics](070_scoring_metrics.md).

### Detection-related gap categories:

| Category             | Description                                                                |
| -------------------- | -------------------------------------------------------------------------- |
| `bridge_gap_mapping` | OCSF fields exist but bridge lacks aliases or router entries               |
| `bridge_gap_feature` | Rule requires unsupported Sigma features (correlation, aggregation, regex) |
| `bridge_gap_other`   | Bridge failure not otherwise classified                                    |
| `rule_logic_gap`     | Fields present, rule executable, but rule did not fire                     |

### Evidence pointer requirements (normative intent):

- Detection-layer gap conclusions in reporting/scoring MUST be backed by deterministic evidence
  references.
- Minimum evidence refs for detection-layer gaps:
  - MUST include `bridge/coverage.json`.
  - SHOULD include `detections/detections.jsonl`.
- When detection is enabled, this specification requires these artifacts to exist so evidence
  references are always satisfiable.

### Gap classification enables prioritized remediation:

- `bridge_gap_mapping`: addressable via mapping pack work
- `bridge_gap_feature`: addressable via backend enhancement
- `rule_logic_gap`: addressable via rule tuning

## Scope limitations (v0.1)

### Correlation rules

Sigma correlation rules (multi-event sequences, temporal conditions, aggregations with thresholds)
are **out of scope for v0.1**.

Rules containing `correlation` blocks MUST be marked non-executable with
`non_executable_reason.reason_code: "unsupported_correlation"`.

### Aggregation functions

Sigma aggregation keywords (`count`, `sum`, `avg`, `min`, `max`, `near`) are **out of scope for
v0.1** unless the backend explicitly supports them.

The default backend (`native_pcre2`) supports Sigma correlation rules, but does not necessarily
support arbitrary Sigma aggregation keywords inside event-rule `condition` expressions in v0.1.
Rules requiring aggregation MUST be marked non-executable with
`non_executable_reason.reason_code: "unsupported_aggregation"`.

### Timeframe modifiers

The `timeframe` modifier is **out of scope for v0.1**.

- Rules specifying `timeframe` SHOULD be evaluated without the temporal constraint.
- When `timeframe` is ignored, the evaluator MUST record this deterministically by appending
  `"timeframe"` to `extensions.bridge.ignored_modifiers` (sorted by UTF-8 byte order).
- Ignoring `timeframe` MUST NOT be treated as an `unsupported_modifier` non-executable condition in
  v0.1; it is an explicit best-effort downgrade.

## References

- [Sigma-to-OCSF Bridge specification][sigma-bridge]
- [Scoring metrics specification][scoring-spec]
- [Reporting specification][reporting-spec]
- [Data contracts specification][data-contracts]
- [Configuration reference][config-ref]
- [ADR-0005: Stage outcomes and failure classification][adr-0005]
- [ADR-0007: State machines for lifecycle semantics][adr-0007]
- [Sigma detection format documentation](https://sigmahq.io/docs/)
- [Sigma rule repository (SigmaHQ/sigma)](https://github.com/SigmaHQ/sigma)
- [Sigma specification repository (SigmaHQ/sigma-specification)](https://github.com/SigmaHQ/sigma-specification)
- [pySigma library (SigmaHQ/pySigma)](https://github.com/SigmaHQ/pySigma)

## Changelog

| Date       | Change            |
| ---------- | ----------------- |
| 2026-01-22 | update            |
| 2026-01-12 | Formatting update |

[adr-0005]: ../adr/ADR-0005-stage-outcomes-and-failure-classification.md
[adr-0007]: ../adr/ADR-0007-state-machines.md
[config-ref]: 120_config_reference.md
[data-contracts]: 025_data_contracts.md
[reporting-spec]: 080_reporting.md
[scoring-spec]: 070_scoring_metrics.md
[sigma-bridge]: 065_sigma_to_ocsf_bridge.md
