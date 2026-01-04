# Normalization to OCSF

## Canonical model
- OCSF is the normalized event schema for all downstream evaluation.

## OCSF versioning
- Pin a specific OCSF schema version per release.
- Provide migration notes when updating.

## Mapping principles (seed)
- Preserve raw fields (as "observables" or vendor extensions) where needed.
- Minimal necessary mapping first; enrich incrementally.

## Required fields (seed)
- time
- actor / principal
- device / host
- event class + category
- metadata:
  - run_id
  - scenario_id
  - collector_version
  - normalizer_version
  - source_type

## Validation
- Validate output against OCSF schema artifacts as part of CI.
- Emit mapping coverage stats: % mapped by class, unknown event types.

## Reference examples
- Use the OCSF schema repo and example translations as guidance.
