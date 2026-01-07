<!-- docs/contracts/AGENTS.md -->
# Agent instructions (docs/contracts/*)

## Contract registries (keep in sync)
- If any `*.schema.json` is added/removed/renamed:
  - update `docs/contracts/index.json`, and
  - update the contract registry list in `docs/spec/025_data_contracts.md`.

## Compatibility rules
- Preserve forward-compatibility patterns:
  - keep schemas strict where intended (e.g., `additionalProperties: false`) and use `extensions` for forward additions,
  - do not introduce breaking contract changes without explicit versioning/migration notes.

## Determinism and testability
- Define stable ordering rules where arrays/maps affect hashing, identity, or diffability.
- For materially changed contracts, add/refresh minimal valid example payloads and fixture-driven validation expectations
  aligned to `docs/spec/100_test_strategy_ci.md`.