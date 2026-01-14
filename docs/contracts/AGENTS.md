# Agent instructions (docs/contracts/)

+## Scope and authority

- This file applies to **`docs/contracts/*` only**.
- `docs/contracts/*` defines **machine-validated schema contracts** (CI-enforced).

## Navigation entrypoint (required)

- Start with `docs/contracts/index.json` (authoritative contract registry).

## Registry sync (required)

- If any `*.schema.json` is added/removed/renamed:
  - update `docs/contracts/index.json`, and
  - update the contract registry list in `docs/spec/025_data_contracts.md`.

## Compatibility rules

- Preserve forward-compatibility patterns:
  - keep schemas strict where intended (e.g., `additionalProperties: false`) and use `extensions`
    for forward additions,
  - do not introduce breaking contract changes without explicit versioning/migration notes.

## Schema testability hooks

- For materially changed contracts, add/refresh:
  - minimal valid example payloads (as fixtures or embedded examples), and
  - fixture-driven validation expectations aligned to `docs/spec/100_test_strategy_ci.md`.
