<!-- docs/spec/060_detection_sigma.md -->
# Detection Rules (Sigma)

## Purpose
Sigma rules are the default, portable detection language for Purple Axiom. Rules are evaluated against **normalized OCSF events** (not raw logs) using an explicit **Sigma-to-OCSF Bridge**.

See: `065_sigma_to_ocsf_bridge.md`.

## Why Sigma
- Portable, generic detection rule format (YAML) with broad community content.
- Separates detection logic from any specific SIEM or query language.

## Rule lifecycle
- - `rules/` is versioned and tagged.
- Each rule must declare:
  - `title`, `id`, `status`
  - `logsource` (used for routing via the Sigma-to-OCSF Bridge)
  - `detection` selectors and conditions
  - `tags` (include ATT&CK technique tags when available)

## Execution model
Sigma evaluation is a two-stage process:

1) **Compile (bridge-aware)**
   - Select a bridge mapping pack (router + field aliases).
   - Route the rule: `sigma.logsource` -> OCSF class filter (and optional producer/source predicates via `filters[]` OCSF filter objects; see `065_sigma_to_ocsf_bridge.md`).
   - Rewrite Sigma field references to OCSF JSONPaths (or SQL column expressions).
   - Produce a backend plan:
     - batch: SQL over Parquet (DuckDB recommended)
     - streaming: expression plan over in-memory/stream processors

2) **Evaluate**
   - Execute the plan over the run’s OCSF event store.
   - Emit `detection_instance` rows for each match group.

Fail-closed behavior:
- If a rule cannot be routed (unknown `logsource`) or references unmapped fields, it is reported as **non-executable** for that run, with reasons recorded in the run report.

## Outputs
- `detections/detections.jsonl` (one JSONL line per detection instance)
- Each detection instance includes:
  - `rule_id`, `rule_title`, `rule_source = "sigma"`
  - `run_id`, optional `scenario_id`
  - `first_seen_utc`, `last_seen_utc`
  - `matched_event_ids` (references `metadata.event_id` in the OCSF store)
  - `technique_ids` when available
  - Recommended: `extensions.bridge` metadata (mapping pack id/version, backend, fallback usage)

## References
- Sigma rule specification and the pySigma ecosystem.
