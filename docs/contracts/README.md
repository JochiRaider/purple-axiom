<!-- docs/contracts/README.md -->
# Purple Axiom Contracts (JSON Schemas)

Contract version: `0.1.0`

These schemas define the **minimum** structure required for deterministic, CI-validated artifacts in the Purple Axiom run bundle.

## Intended usage

- `ground_truth.jsonl`, `normalized/ocsf_events.jsonl`, `detections/detections.jsonl`, `criteria/criteria.jsonl`,
  and `criteria/results.jsonl` are **JSON Lines** files:
  - validate **each line** against the corresponding schema.
- The following are single JSON objects:
  - `manifest.json`
  - `criteria/manifest.json`
  - `scoring/summary.json`
  - `normalized/mapping_profile_snapshot.json`
  - `normalized/mapping_coverage.json`
  - `bridge/router_table.json`
  - `bridge/mapping_pack_snapshot.json`
  - `bridge/coverage.json`
  - `bridge/compiled_plans/<rule_id>.plan.json` (one object per file)

## Design notes

- Strict schemas (manifest, ground truth, detections, summary) use `additionalProperties: false` for high signal-to-noise.
- Forward-compatible extension point: `extensions` object.
- OCSF event validation is intentionally *minimal*:
  - It enforces provenance (`metadata.run_id`, `metadata.scenario_id`, versions, `metadata.source_type`) and a stable `metadata.event_id`.
  - It does not attempt to fully validate the entire OCSF spec payload.

## Files

See `index.json` for the authoritative registry. Current schemas:

- `manifest.schema.json`
- `ground_truth.schema.json`
- `criteria_pack_manifest.schema.json`
- `criteria_entry.schema.json`
- `criteria_result.schema.json`
- `ocsf_event_envelope.schema.json`
- `detection_instance.schema.json`
- `summary.schema.json`
- `mapping_profile_snapshot.schema.json`
- `mapping_coverage.schema.json`
- `bridge_router_table.schema.json`
- `bridge_mapping_pack.schema.json`
- `bridge_compiled_plan.schema.json`
- `bridge_coverage.schema.json`
- `pcap_manifest.schema.json`
- `netflow_manifest.schema.json`