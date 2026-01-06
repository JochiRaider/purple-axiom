<!-- docs/spec/080_reporting.md -->
# Reporting

## Artifact bundle (per run)
- manifest.json
- ground_truth.jsonl
- criteria/manifest.json
- criteria/criteria.jsonl
- criteria/results.jsonl
- runner/ (per-action transcripts + cleanup verification evidence)
- ocsf_events.jsonl (or parquet)
- bridge/ (mapping pack snapshot, compiled plans, bridge coverage)
- detections.jsonl
- report.html
- summary.json

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
  - baseline run_id and comparable keys
  - pass/fail status vs thresholds
  - deltas for coverage/latency/gap taxonomy

## Trend tracking (optional)
- Maintain a history table keyed by (scenario_id, rule_set_version, pipeline_version, bridge_mapping_pack_version).
  - Source: `manifest.extensions.bridge.mapping_pack_version` (or equivalent) when not present in `manifest.versions`.
- Emit regression alerts when coverage/latency deviates beyond thresholds.
