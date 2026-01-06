<!-- docs/contracts/README.md -->
# Purple Axiom Contracts (JSON Schemas)

Contract version: `0.1.0`

These schemas define the **minimum** structure required for deterministic, CI-validated artifacts in the Purple Axiom run bundle.

## Intended usage

- `ground_truth.jsonl`, `normalized/ocsf_events.jsonl`, and `detections.jsonl` are **JSON Lines** files:
  - validate **each line** against the corresponding schema.
- `manifest.json`, `scoring/summary.json`, and `normalized/mapping_coverage.json` are single JSON objects.

## Design notes

- Strict schemas (manifest, ground truth, detections, summary) use `additionalProperties: false` for high signal-to-noise.
- Forward-compatible extension point: `extensions` object.
- OCSF event validation is intentionally *minimal*:
  - It enforces provenance (`metadata.run_id`, `metadata.scenario_id`, versions, `metadata.source_type`) and a stable `metadata.event_id`.
  - It does not attempt to fully validate the entire OCSF spec payload.

## Files

See `index.json` for the schema list.
