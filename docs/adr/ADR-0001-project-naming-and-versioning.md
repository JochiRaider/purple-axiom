<!-- docs/adr/ADR-0001-project-naming-and-versioning.md -->

# ADR-0001: Project naming and versioning

## Status

Proposed

## Context

We need stable identifiers for scenarios, rulesets, mappings, and pipeline configs to ensure
reproducible scoring.

## Decision (seed)

- Use semver for project releases.
- Use immutable run_id (UUID) for each run.
- Pin OCSF version and record in manifest.
- Version scenarios independently from the codebase (scenario_version).

## Consequences

- Easier regression tracking and reproducibility.
- Requires discipline around manifest completeness.
