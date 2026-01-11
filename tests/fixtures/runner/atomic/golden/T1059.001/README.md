<!--tests/fixtures/runner/atomic/golden/T1059.001/README.md -->

# Atomic runner determinism fixture: T1059.001 (v0.1)

This fixture is a **unit-level determinism** vector for Purple Axiom’s Atomic runner integration
contract (`docs/spec/032_atomic_red_team_executor_integration.md`).

It validates, without executing Atomics:

- input precedence (YAML defaults + runner `-InputArgs` overrides)
- fixed-point placeholder substitution for `#{...}`
- `$ATOMICS_ROOT` canonicalization for `PathToAtomicsFolder` / `$PathToPayloads`-style path
  expansions
- `parameters.resolved_inputs_sha256` hashing determinism
- `action_key` basis hashing determinism (per `docs/spec/030_scenarios.md`)

Notes:

- `source/atomics/.../T1059.001.yaml` is a **minimal, synthetic** Atomic YAML shaped like upstream.
  It is intended for deterministic contract testing. Swap it with upstream content only if you also
  pin the upstream content ref and re-generate fixture outputs.

Regeneration:

- Update `extracted/atomic_test_extracted.json` (if YAML changes)
- Update `inputs/resolved_inputs.json` and `inputs/resolved_inputs_sha256.txt`
- Update `identity/action_key_basis_v1.json` and `identity/action_key.txt`
- Update `execution/command_post_merge.txt`
