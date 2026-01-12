---
title: 'ADR-0001: Project naming and versioning'
description: Defines stable naming and versioning conventions for runs, scenarios, mappings, and schema pins to enable reproducible scoring.
status: proposed
category: adr
tags: [versioning, naming, determinism]
---

# ADR-0001: Project naming and versioning

## Context

Purple Axiom needs stable identifiers for scenarios, rulesets, mappings, and pipeline configurations
to ensure reproducible scoring.

## Decision

- The project release versioning MUST use SemVer.
- Each run MUST use an immutable `run_id` (UUID).
- The pinned OCSF version MUST be recorded in the run manifest.
- Scenarios MUST be versioned independently from the codebase via `scenario_version`.

`TODO: Add explicit naming/versioning rules for rule packs and mapping profiles if they are defined elsewhere (for example: `ruleset_id`, `ruleset_version`, `mapping_profile_id`, `mapping_profile_version`) and cross-link the authoritative spec or contract.`

## Consequences

- Improves regression tracking and reproducibility across runs.
- Requires discipline around manifest completeness and version pin hygiene.
