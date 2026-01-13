---
title: Reporting
description: Defines reporting artifacts, required outputs, and trending keys for run evaluation.
status: draft
---

# Reporting

This document defines the reporting artifacts, sections, and required outputs for Purple Axiom runs.
It also specifies the stable keys used for trending across historical runs.

## Artifact bundle (per run)

- `manifest.json`
- `ground_truth.jsonl`
- `criteria/manifest.json`
- `criteria/criteria.jsonl`
- `criteria/results.jsonl`
- `runner/` (per-action transcripts + cleanup verification evidence)
- `ocsf_events.jsonl` (or Parquet)
- `bridge/` (mapping pack snapshot, compiled plans, bridge coverage)
- `detections.jsonl`
- `report.html`
- `scoring/summary.json`

## Report sections (seed)

- Run summary (scenario, targets, duration)

- Lab inventory summary (provider type, asset counts, key tags/roles)

- Technique coverage table

- Latency distributions

- Top failures:

  - missing telemetry
  - criteria gaps (missing/unmatched criteria)
  - normalization gaps (OCSF fields missing)
  - bridge gaps (Sigma-to-OCSF routing/alias gaps)
  - rule gaps (logic/expression)

- Criteria evaluation:

  - criteria pack id/version (pinned)
  - criteria pass/fail/skipped rates
  - per-technique and per-test criteria outcomes

- Cleanup verification:

  - cleanup invoked vs skipped
  - cleanup verification pass/fail (with links to evidence refs)

- Sigma-to-OCSF bridge health:

  - rules routed vs unrouted (by `logsource.category`)
  - most common unmapped Sigma fields
  - fallback usage (`raw.*`) rate and which fields drove it

- Change log vs previous run (if comparable)

- Regression summary (when baseline provided)

  - baseline `run_id` and comparable keys
  - pass/fail status vs thresholds
  - deltas for coverage/latency/gap taxonomy

## Trend tracking (optional)

- Maintain a history table keyed by (`scenario_id`, `rule_set_version`, `pipeline_version`,
  `bridge_mapping_pack_version`).
  - Source: `manifest.extensions.bridge.mapping_pack_version` (or equivalent) when not present in
    `manifest.versions`.
- Emit regression alerts when coverage/latency deviates beyond thresholds.

## Required JSON outputs (v0.1)

The following JSON outputs MUST be produced for v0.1 runs (unless the corresponding stage is
explicitly disabled):

| File                               | Purpose                                                    | Primary contract                                                                 |
| ---------------------------------- | ---------------------------------------------------------- | -------------------------------------------------------------------------------- |
| `manifest.json`                    | Run-level provenance and outcomes                          | [manifest schema](../contracts/manifest.schema.json)                             |
| `scoring/summary.json`             | Operator-facing rollup (coverage, latency, fidelity, gaps) | [summary schema](../contracts/summary.schema.json)                               |
| `bridge/coverage.json`             | Sigma-to-OCSF bridge quality and coverage                  | [bridge coverage schema](../contracts/bridge_coverage.schema.json)               |
| `normalized/mapping_coverage.json` | OCSF normalization coverage and missing core fields        | [mapping coverage schema](../contracts/mapping_coverage.schema.json)             |
| `criteria/manifest.json`           | Criteria pack snapshot metadata                            | [criteria pack manifest schema](../contracts/criteria_pack_manifest.schema.json) |

## Trending keys (normative)

Exporters and downstream dashboards MUST treat the following fields as the stable trending
dimensions for joining historical runs:

- `scenario_id` (REQUIRED)
- `scenario_version` (SHOULD be present for trending)
- `rule_set_version` (REQUIRED for Sigma regression tracking)
- `pipeline_version` (REQUIRED for pipeline drift detection)
- `extensions.bridge.mapping_pack_version` (RECOMMENDED)
- `versions.ocsf_version` (RECOMMENDED)
- `extensions.criteria.criteria_pack_version` (RECOMMENDED)

Non-goal:

- `run_id` is unique per execution and MUST NOT be used as a trending key.
