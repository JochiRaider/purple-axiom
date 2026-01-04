# Reporting

## Artifact bundle (per run)
- manifest.json
- ground_truth.jsonl
- ocsf_events.jsonl (or parquet)
- detections.jsonl
- report.html
- summary.json

## Report sections (seed)
- Run summary (scenario, targets, duration)
- Technique coverage table
- Latency distributions
- Top failures:
  - missing telemetry
  - mapping gaps
  - rule gaps
- Change log vs previous run (if comparable)

## Trend tracking (optional)
- Maintain a history table keyed by (scenario_id, rule_set_version, pipeline_version).
- Emit regression alerts when coverage/latency deviates beyond thresholds.
