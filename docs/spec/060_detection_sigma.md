# Detection Rules (Sigma)

## Why Sigma
- Portable, generic detection rule format; rules are YAML-based and designed to describe log events across platforms.

## Rule lifecycle
- rules/ directory is versioned and tagged.
- Each rule must declare:
  - title, id, status
  - logsource (mapped to OCSF class/category)
  - detection selectors (mapped fields)
  - tags (include ATT&CK technique tags when available)

## Execution model (seed)
- Sigma rules are compiled into a local query/evaluation plan targeting OCSF events.
- Evaluation modes:
  - streaming: evaluate as events arrive
  - batch: evaluate against event store after run

## Outputs
- detection_instance:
  - rule_id
  - run_id
  - first_seen, last_seen
  - matched_event_ids
  - mapped technique_id(s)

## References
- Sigma main repo and rule/spec docs.
