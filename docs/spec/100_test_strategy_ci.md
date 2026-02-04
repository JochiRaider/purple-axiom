---
title: Test strategy and CI
description: Defines the unit, integration, and CI gating expectations for deterministic runs.
status: draft
tags: []
category: spec
related:
  - 020_architecture.md
  - 025_data_contracts.md
  - 030_scenarios.md
  - 032_atomic_red_team_executor_integration.md
  - 035_validation_criteria.md
  - 040_telemetry_pipeline.md
  - 050_normalization_ocsf.md
  - 065_sigma_to_ocsf_bridge.md
  - 080_reporting.md
  - 110_operability.md
  - ../../SUPPORTED_VERSIONS.md
  - ../adr/ADR-0005-stage-outcomes-and-failure-classification.md
  - ../adr/ADR-0007-state-machines.md
---

# Test strategy and CI

This document defines the required unit tests, integration fixtures, and CI gates for Purple Axiom
runs. It establishes the testing approach that ensures deterministic outputs, pinned-version
conformance, and regression protection across all pipeline stages.

## Overview

**Summary**: Purple Axiom requires deterministic, reproducible pipeline outputs. This spec defines
the testing layers (unit, integration, CI gates) that enforce determinism, detect drift, and protect
against regressions.

The testing strategy addresses three core concerns. First, determinism verification ensures that
identical inputs produce byte-identical outputs across runs, platforms, and time. Second, version
conformance validates that all pipeline stages use pinned dependency versions and produce outputs
conforming to pinned schemas. Third, regression protection detects coverage drops, performance
degradation, and semantic drift before they reach production.

### Determinism primitives (normative for tests)

- `canonical_json_bytes(x)`: RFC 8785 JSON Canonicalization Scheme (JCS), UTF-8 bytes.
- `sha256_hex(bytes)`: lowercase hex SHA-256 digest of `bytes`.
- Any `*_jcs_sha256` value in this spec MUST mean: `sha256_hex(canonical_json_bytes(<json value>))`.
- For criteria JSONL hashing, `canonical_criteria_jsonl_bytes(...)` MUST follow the validation
  criteria spec (JCS per-line, join with `\n`, trailing `\n`).

### Reason code scope (normative)

- Stage/substage outcomes (`runs/<run_id>/logs/health.json`): `reason_code` values MUST be drawn
  from ADR-0005 (unknown codes MUST NOT be emitted without updating ADR-0005).
- Artifact-level reason codes (for example inside `ground_truth.jsonl`,
  `requirements_evaluation.json`, `state_reconciliation_report.json`) are governed by their contract
  schemas and may include additional stable tokens.
  - Any artifact-level `reason_code` field MUST be paired with `reason_domain`.
  - For contract-backed artifacts, `reason_domain` MUST equal the artifact schema `contract_id`.

## Scope

This document covers:

- Unit test requirements for each pipeline component
- Integration test fixtures and harnesses
- CI gate definitions and failure semantics
- Recommended CI workflow patterns
- Conformance tests for lifecycle/state-machine semantics defined elsewhere (runner action
  lifecycle, telemetry checkpointing/rotation, reporting regression-compare substages)

This document does NOT cover:

- Implementation details of specific test frameworks
- Manual QA procedures
- Performance benchmarking beyond latency regression gates
- Authoritative definitions of lifecycle/state machines (see ADR-0007 and the owning stage specs)

## CI lanes (Content CI vs Run CI)

Purple Axiom CI is intentionally split into two lanes (see `105_ci_operational_readiness.md`):

- **Content CI**: fast, no lab required. Runs static validation, compilation, and fixture-backed
  unit tests over content-like artifacts.
- **Run CI**: slow, integration. Runs evaluator replay against a pinned baseline dataset and/or
  executes at least one end-to-end run in a minimal lab profile.

This spec defines which test categories MUST be runnable in each lane.

### Content CI gate set (normative)

Content CI MUST be runnable without a lab provider and MUST include, at minimum:

- Unit tests that do not require a lab provider (this section).
- Contract/schema validation for content-like artifacts under test (criteria packs, mapping pack
  snapshots, compiled plans, etc.).
- Sigma compilation + semantic validation (see "Sigma compilation (bridge)").
- Rule-level unit tests when fixtures are present (see "Sigma rule unit tests").

Content CI MUST fail closed when compilation or validation cannot be completed deterministically.

### Run CI gate set (normative)

Run CI MUST include, at minimum:

- The evaluator conformance harness executed against at least one pinned Baseline Detection Package
  (BDP) or equivalent pinned event fixture set (see "Evaluator conformance harness").
- At least one end-to-end “golden run” bundle when a lab provider is available (RECOMMENDED).

Run CI MAY be triggered less frequently than Content CI (for example on merge-to-main and/or on
release), but MUST be executed before release publication.

## Unit tests

**Summary**: Unit tests validate individual components in isolation using deterministic fixtures.
Each test category targets a specific pipeline stage or cross-cutting concern.

### Event identity and canonicalization

Canonicalization tests validate RFC 8785 (JCS) vectors plus Purple Axiom hash-basis fixtures,
requiring byte-for-byte determinism.

Windows Event Log raw XML tests validate identity-field extraction without RenderingInfo, binary
field detection, and payload limit truncation with SHA-256 computation.

Linux event identity basis tests use auditd/journald/syslog fixture vectors covering Tier 1 and Tier
2 fields, plus Tier 3 collision fixtures under `tests/fixtures/event_id/v1/`.

### Glob matching (glob_v1)

Glob expansion and matching is used by both producers (publish-gate `expected_outputs[]` discovery)
and consumers (contract-backed artifact discovery). To ensure multi-language implementations match,
tests MUST lock glob semantics to `glob_v1` as defined in `025_data_contracts.md` ("Glob semantics
(glob_v1)").

Fixture set (normative):

- `glob_v1_vectors` (semantic lock)

  - Provide `tests/fixtures/glob_v1/vectors.json` as canonical JSON with:
    - `glob_version` (string; MUST equal `glob_v1`)
    - `cases[]`: array of objects, each containing:
      - `pattern` (string; run-relative POSIX glob)
      - `candidates[]` (array of run-relative POSIX paths)
      - `matches[]` (array of expected matches)
        - `matches[]` MUST equal the subset of `candidates[]` that match `pattern` under `glob_v1`.
        - `matches[]` MUST be sorted by UTF-8 byte order ascending (no locale).
  - The case set MUST include, at minimum:
    - Each distinct wildcard form currently present in `docs/contracts/contract_registry.json`
      `bindings[].artifact_glob` (for example `bridge/compiled_plans/*.plan.json` and
      `runner/actions/*/executor.json`).
    - At least one recursive `**` case (for example `runner/**/executor.json`).
    - At least one `?` case and at least one `[...]` case.
  - Each case's `candidates[]` MUST include both positive and negative examples that enforce:
    - `*` does not match `/`,
    - matching is case-sensitive (example: `Executor.json` MUST NOT match `executor.json`), and
    - `**` matches zero or more path segments.
  - Verification (normative):
    - The reference reader SDK (`pa.reader.v1`) and reference publisher SDK (`pa.publisher.v1`) test
      suites MUST include this fixture and MUST fail if any case does not match.
    - Any other first-party implementation of `glob_v1` MUST also include this fixture in CI.

### Redaction

- Redaction policy test vectors validate deterministic truncation, placeholder emission, and
  post-check secret detection.
- Disabled redaction posture fixtures validate deterministic handling:
  - `withhold_from_long_term`: standard locations contain deterministic placeholders; unredacted
    evidence is not persisted in the run bundle (except volatile logs as permitted by
    operability/debug policies); manifest/report labeled unredacted.
  - `quarantine_unredacted`: placeholders remain in standard locations and unredacted evidence is
    persisted only under the configured quarantine directory; quarantine outputs are excluded from
    default packaging/export; manifest/report labeled unredacted.
- Placeholder determinism fixtures (required):
  - Golden fixtures for both JSON and text placeholders that assert byte-for-byte stable
    serialization (JSON uses RFC 8785 canonical JSON), and required field emission (`reason_code`
    always present; `reason_domain` MUST equal `artifact_placeholder`;`sha256` present only when
    allowed).
  - Vectors that explicitly validate `sha256` omission for secret-containing / post-check matches,
    and inclusion when the effective redaction policy permits it.
- Required: byte-for-byte determinism of placeholders and truncation output.

### Normalization and mapping

Mapping unit tests validate raw input to expected OCSF output transformations.

Mapping pack conformance tests validate that mapping YAML MUST parse deterministically (no duplicate
keys, no anchors/aliases/merge keys), routing MUST be overlap-free, and
`normalized/mapping_profile_snapshot.json` MUST include hashes for the complete mapping material
boundary defined by the
[OCSF mapping profile authoring guide](../mappings/ocsf_mapping_profile_authoring_guide.md).
`normalized/mapping_profile_snapshot.json` MUST validate against
`mapping_profile_snapshot.schema.json` and MUST include, at minimum: `mapping_profile_id`,
`mapping_profile_version`, `mapping_profile_sha256`, and `ocsf_version` (see data contracts:
“Normalization mapping profile snapshot”).

OCSF schema regression tests validate that representative normalized fixtures MUST validate against
the pinned OCSF version used by v0.1.

### Runner contracts (ground truth lifecycle)

Ground truth schema tests MUST validate representative fixtures against the pinned
`ground_truth.schema.json`, including lifecycle and idempotence fields:

- Fixtures MUST include `idempotence` and a `lifecycle.phases[]` array containing all four phases in
  order: `prepare`, `execute`, `revert`, `teardown`.
- Each phase record MUST include:
  - `phase` (`prepare|execute|revert|teardown`)
  - `phase_outcome` (`success|failed|skipped`)
  - `started_at_utc`, `ended_at_utc`
  - `reason_code` (required when `phase_outcome` is not `success`)
- Phases that are not attempted MUST be represented explicitly as `phase_outcome=skipped` with a
  stable `reason_domain="ground_truth"` and `reason_code` (example: `cleanup_suppressed` when
  `plan.cleanup=false`).
- The fixture suite MUST include at least one failure case where `revert` or `teardown` is `failed`
  and is surfaced deterministically in runner-stage outcomes and reporting inputs.

### Schema evolution

Parquet schema evolution tests for the normalized store cover two scenarios.

For additive columns: given two Parquet fixtures for `normalized/ocsf_events/` where fixture B adds
one new nullable column relative to fixture A, readers MUST be able to scan both together using
union-by-name semantics, and the missing column MUST read as NULL for fixture A rows.

For alias resolution: given a deprecated column name and an `_schema.json` alias mapping, the query
layer MUST resolve the canonical column name deterministically (prefer first alias, fall through to
next, then NULL if none exist).

The same fixture MUST assert lifecycle conformance:

- Ground truth MUST include `idempotence` and `lifecycle.phases[]`.
- `lifecycle.phases[]` MUST be in lifecycle order and MUST include all four phases: `prepare`,
  `execute`, `revert`, `teardown`.
  - Phases that are not attempted MUST be recorded as `phase_outcome=skipped` with a stable
    `reason_code`.
- When cleanup verification is enabled and the artifact exists, the `teardown` phase evidence MUST
  include a stable pointer to `runner/actions/<action_id>/cleanup_verification.json` consistent with
  the ground-truth phase evidence attachment rules.

### Sigma compilation (bridge)

Rule compilation tests validate Sigma to evaluation plan compilation for the authoritative supported
subset and non-executable classification defined in
[Sigma-to-OCSF bridge: backend adapter contract](065_sigma_to_ocsf_bridge.md#backend-adapter-contract-normative-v01).

Fixtures for `native_pcre2` compilation patterns MUST cover:

- Case-insensitive equality and inequality semantics (including list-typed field semantics).
- Literal substring semantics for `contains`, `startswith`, and `endswith`.
- Regex acceptance for PCRE2-compatible patterns (including lookaround) and bounded-execution
  rejection (match limits, depth limits) with `unsupported_regex` and a stable `PA_SIGMA_...` code
  in the explanation.
- LIST-typed field semantics (any/all) selection based on schema type.
- Correlation rule compilation for each supported correlation type (`event_count`, `value_count`,
  `temporal`, `ordered_temporal`), including `group-by` and `aliases`.

Bridge router multi-class routing tests validate that given a `logsource.category` routed to
multiple `class_uid` values, compilation MUST scope evaluation to the union (`IN (...)` / OR
semantics) and the routed `class_uid` set MUST be emitted in ascending numeric order for
deterministic output.

#### Compiled plan semantic validation policy (required)

In addition to syntactic compilation, v0.1 implementations MUST apply a semantic validation phase to
each compiled plan (see `065_sigma_to_ocsf_bridge.md`, "Compiled plan semantic validation policy").

Unit tests MUST include fixtures that demonstrate deterministic rejection / classification for:

- Invalid field reference: a plan referencing an OCSF path that does not exist in the pinned OCSF
  schema MUST be rejected deterministically.
- Prohibited regex: a plan containing a regex that violates the configured regex safety limits MUST
  be rejected deterministically with `reason_code="unsupported_regex"` and a stable
  `PA_BRIDGE_REGEX_POLICY_VIOLATION` code in the explanation.
- Missing required scoping: a plan that is missing required `class_uid` scope MUST fail closed with
  a stable, machine-classifiable error (treat as a compiler/validator bug).

### Sigma rule unit tests

Rule-level unit tests treat “expected matches” as executable assertions and are intended to run in
Content CI (fast, no lab required).

Rule unit test fixtures tie together:

- A Sigma rule (by `rule_id` / `id`),
- A small slice of normalized OCSF events,
- Expected match semantics (matched event ids and/or counts), and
- Expected non-executable classification when applicable.

#### Fixture format (v0.1, minimal)

A rule unit test case MUST be representable as a directory:

- `tests/fixtures/sigma_rule_tests/<test_id>/`
  - `rule.yaml`: Sigma rule under test (MUST include `id`; treated as `rule_id`).
  - `events.jsonl`: newline-delimited normalized OCSF event envelopes.
    - Each row MUST validate against the `ocsf_event_envelope` contract.
    - Each row MUST include `metadata.event_id` (used as the match join key).
  - `expect.json`: expected result (schema defined below).

`expect.json` MUST follow this shape (future-proofed with an explicit version string):

- `schema_version` (required): `"pa:sigma_rule_test:v1"`
- `rule_id` (required): string; MUST equal the Sigma `id`.
- `expect` (required):
  - `executable` (required): boolean
  - When `executable: true`:
    - `matched_event_ids` (required): array of `metadata.event_id` strings expected to match.
      - MUST be unique and sorted ascending.
    - `match_count` (optional): integer; when present MUST equal `len(matched_event_ids)`.
  - When `executable: false`:
    - `non_executable_reason` (required):
      - `reason_domain` MUST be `"bridge_compiled_plan"`.
      - `reason_code` MUST be a stable token from the bridge reason code registry.

#### Execution semantics (normative)

Given a test case:

1. The harness MUST compile `rule.yaml` using the same mapping pack + backend configuration as
   Content CI.
1. If compilation yields `executable=false`, the harness MUST compare the emitted
   `non_executable_reason` to `expect.non_executable_reason` and MUST NOT attempt evaluation.
1. If compilation yields `executable=true`, the harness MUST evaluate the plan over `events.jsonl`
   and compute the set of matched `metadata.event_id` values.
1. The harness MUST fail the test if the matched event id set differs from
   `expect.matched_event_ids` (set equality; ordering is canonicalized before comparison).

#### Required golden rule test pack (verification hook)

The repository MUST include a golden rule test pack that runs in Content CI and contains at least:

- One rule that should match (non-empty `matched_event_ids`).
- One rule that should not match (`matched_event_ids: []`).
- One rule that should be non-executable for a known `reason_code` (for example
  `reason_code="unroutable_logsource"`).

### Runner and execution

Lab provider parser tests validate provider inventory export to canonical `lab.assets` list
transformation.

Scenario selection tests validate target selectors to resolved target set conversion using a fixed
inventory snapshot fixture.

Atomic runner determinism fixtures under `tests/fixtures/runner/atomic/` validate that extracted
Atomic test to resolved inputs to `$ATOMICS_ROOT` canonicalization produces stable
`resolved_inputs_sha256` and `action_key`.

When a fixture includes `runner/actions/<action_id>/resolved_inputs_redacted.json`, tests MUST also
validate that:

- the artifact validates against `resolved_inputs_redacted.schema.json`, and
- `runner/actions/<action_id>/resolved_inputs_redacted.json.resolved_inputs_sha256` equals the
  corresponding ground truth `parameters.resolved_inputs_sha256` value, and
- that value equals `"sha256:" + sha256_hex(canonical_json_bytes(resolved_inputs_redacted))`.

Requirements gating fixtures under `tests/fixtures/runner/requirements/` validate deterministic
evaluation and deterministic skip semantics when declared requirements are unmet.

The fixture set MUST include at least:

- `unmet_admin_privilege`:
  - Input: scenario declares `plan.requirements.privilege=admin`.
  - Probe snapshot: target privilege probe indicates the runner context is not admin.
  - Expected: action is skipped with deterministic `reason_domain="ground_truth"` and
    `reason_code=insufficient_privileges` and
    `runner/actions/<action_id>/requirements_evaluation.json` is emitted.
- `wrong_os`:
  - Input: scenario declares `plan.requirements.platform.os=["windows"]`.
  - Probe snapshot: target OS family probe indicates `linux`.
  - Expected: action is skipped with deterministic `reason_domain="ground_truth"` and
    `reason_code=unsupported_platform` and `runner/actions/<action_id>/requirements_evaluation.json`
    is emitted.
- `missing_tool`:
  - Input: scenario declares `plan.requirements.tools=["powershell"]`.
  - Probe snapshot: tool/capability probe indicates `powershell` is unavailable.
  - Expected: action is skipped with deterministic `reason_domain="ground_truth"` and
    `reason_code=missing_tool` and `runner/actions/<action_id>/requirements_evaluation.json` is
    emitted.
- `multiple_requirements_mixed_order`:
  - Input: scenario declares multiple requirements in a non-sorted declaration order (example:
    privilege=admin, platform.os=["windows"], tools=["powershell"]).
  - Probe snapshot: multiple requirements evaluate to unmet (example: OS family indicates `linux`,
    privilege probe indicates not admin, and tool probe indicates `powershell` unavailable).
  - Expected (normative):
    - The action is skipped and `runner/actions/<action_id>/requirements_evaluation.json` is
      emitted.
    - The requirement result list MUST include an item for each evaluated requirement and MUST be
      ordered deterministically by the stable sort key `(kind, key)`.
    - The action-level `reason_code` MUST be selected deterministically from the first unmet
      requirement result after applying the same stable sort key. The mapping MUST be:
      - `platform` -> `unsupported_platform`
      - `privilege` -> `insufficient_privileges`
      - `tool` -> `missing_tool` (Example: if the first unmet result has `kind=platform`, then
        `reason_code` MUST be `unsupported_platform`.)

For each fixture, the runner requirements implementation MUST:

- Emit `runner/actions/<action_id>/requirements_evaluation.json` with deterministic ordering of
  requirement result items.
  - Requirement result arrays MUST be ordered by a stable sort key: `(kind, key)` where `kind` is
    one of `platform | privilege | tool` and `key` is the stable evaluated token (OS family,
    privilege level, or tool token).
- In the test harness, compute a stable hash over the evaluation content (RECOMMENDED:
  `requirements_eval_jcs_sha256` over RFC 8785 JCS canonicalized JSON) and assert the hash is
  identical across repeated runs with identical inputs and probe snapshots.

Principal context fixtures under `tests/fixtures/runner/principal_context/` validate deterministic
principal capture and schema conformance for `runs/<run_id>/runner/principal_context.json`.

The fixture set MUST include at least:

- `single_principal_known`

  - Assert `runs/<run_id>/runner/principal_context.json` exists and validates against
    `docs/contracts/principal_context.schema.json`.
  - Assert deterministic ordering:
    - `principals[]` MUST be sorted lexicographically by `principal_id`.
    - `action_principal_map[]` MUST be sorted lexicographically by `action_id`.
  - Assert stable, deterministic counters:
    - `runner_principal_context_total == 1`
    - `runner_principal_context_known_total == 1`
    - `runner_principal_context_unknown_total == 0`

- `principal_unknown`

  - Fixture setup MUST simulate probe-unavailable or probe-blocked behavior (for example: probe
    disabled by configuration or blocked by environment constraints) while still producing
    `principal_context.json`.
  - Assert at least one principal is recorded with `kind = "unknown"` (and no secret-bearing
    identity material).
  - Assert deterministic ordering as above.
  - Assert stable, deterministic counters:
    - `runner_principal_context_total == 1`
    - `runner_principal_context_known_total == 0`
    - `runner_principal_context_unknown_total == 1`

Cache provenance fixtures under `tests/fixtures/cache_provenance/` validate deterministic cache
provenance recording for `runs/<run_id>/logs/cache_provenance.json` when caching is enabled.

The fixture set MUST include at least:

- `cache_hit_recorded`

  - Assert `runs/<run_id>/logs/cache_provenance.json` exists and validates against
    `docs/contracts/cache_provenance.schema.json`.
  - Assert deterministic ordering: `entries[]` MUST be sorted lexicographically by
    `(component, cache_name, key)`.
  - Assert hit/miss status reflects a hit for the recorded entry.
  - Assert stable, deterministic counters:
    - `cache_provenance_hit_total == 1`
    - `cache_provenance_miss_total == 0`

- `cache_miss_recorded`

  - Same assertions as `cache_hit_recorded`, but hit/miss status MUST reflect a miss.
  - Assert stable, deterministic counters:
    - `cache_provenance_hit_total == 0`
    - `cache_provenance_miss_total == 1`

State reconciliation fixtures under `tests/fixtures/runner/state_reconciliation/` validate
deterministic environment drift reporting (distinct from baseline drift in evaluator and conformance
harnesses).

- Any reconciliation item with `status="unknown"` or `status="skipped"` MUST include
  `reason_domain="state_reconciliation_report"` and `reason_code`.

Idempotence and lifecycle enforcement fixtures under `tests/fixtures/runner/lifecycle/` validate
deterministic re-run safety behavior and lifecycle phase transition guards.

The fixture set MUST include at least:

- `dependency_mutation_blocked`

  - Simulate an attempt by the runner (or an invoked action) to self-update or mutate runtime
    dependencies during a run.
  - Assert deterministic enforcement handling:
    - The run MUST record a stable reason code for the block: `disallowed_runtime_self_update`.
  - Assert counters:
    - `runner_dependency_mutation_blocked_total == 1`

- `unsafe_rerun_blocked_cleanup_suppressed`:

  - Input:
    - Scenario includes two action instances targeting the same `target_asset_id` and resolving to
      the same `action_key`.
    - The action's `idempotence` is `non_idempotent` (or `unknown` treated as `non_idempotent`).
    - The first action instance suppresses cleanup (`plan.cleanup=false`) and therefore does not
      attempt `revert`/`teardown`.
  - Expected:
    - First action instance:
      - `execute.phase_outcome=success`.
      - `revert.phase_outcome=skipped` and `teardown.phase_outcome=skipped` when
        `plan.cleanup=false` (cleanup suppressed).
      - `runner/actions/<action_id>/cleanup_verification.json` MUST NOT be emitted when cleanup is
        suppressed.
    - Second action instance:
      - The runner MUST refuse to attempt `execute` and MUST record `execute.phase_outcome=skipped`
        with deterministic `reason_code=unsafe_rerun_blocked`.
      - `revert` and `teardown` MUST be `skipped`.
    - Observability (normative):
      - `runs/<run_id>/logs/health.json` MUST include a `health.json.stages[]` entry with:
        - `stage="runner.lifecycle_enforcement"`
        - `status="failed"`
        - `reason_code="unsafe_rerun_blocked"`
      - Stable counters MUST reflect the enforcement event:
        - `runner_unsafe_rerun_blocked_total == 1`
        - `runner_invalid_lifecycle_transition_total == 0`
    - In the test harness, compute a stable hash over the two action lifecycle records (RECOMMENDED:
      `lifecycle_jcs_sha256` over RFC 8785 JCS canonicalized ground truth lifecycle objects) and
      assert the hash is identical across repeated runs with identical inputs.

- `unsafe_rerun_blocked_revert_failed`:

  - Input:
    - Scenario includes two action instances targeting the same `target_asset_id` and resolving to
      the same `action_key`.
    - The action's `idempotence` is `non_idempotent` (or `unknown` treated as `non_idempotent`).
    - The first action instance attempts cleanup (`plan.cleanup=true`) and attempts `revert`, but
      the `revert` phase does not complete successfully (`revert.phase_outcome=failed`).
  - Expected:
    - First action instance:
      - `execute.phase_outcome=success`.
      - `revert.phase_outcome=failed`.
    - Second action instance:
      - The runner MUST refuse to attempt `execute` and MUST record `execute.phase_outcome=skipped`
        with deterministic `reason_code=unsafe_rerun_blocked`.
      - `revert` and `teardown` MUST be `skipped`.
    - Observability (normative):
      - `runs/<run_id>/logs/health.json` MUST include a `health.json.stages[]` entry with:
        - `stage="runner.lifecycle_enforcement"`
        - `status="failed"`
        - `reason_code="unsafe_rerun_blocked"`
      - Stable counters MUST reflect the enforcement event:
        - `runner_unsafe_rerun_blocked_total == 1`
        - `runner_invalid_lifecycle_transition_total == 0`
    - In the test harness, compute a stable hash over the two action lifecycle records (RECOMMENDED:
      `lifecycle_jcs_sha256` over RFC 8785 JCS canonicalized ground truth lifecycle objects) and
      assert the hash is identical across repeated runs with identical inputs.

- `execute_not_attempted_without_prepare_success`:

  - Input:
    - requirements evaluation (or other deterministic gating) causes `prepare` to be skipped or
      failed, and
    - `execute` would otherwise be attempted for the action.
  - Expected:
    - The runner MUST block the invalid transition deterministically:
      - `execute.phase_outcome=skipped` with deterministic
        `reason_code=invalid_lifecycle_transition`.
    - `revert.phase_outcome=skipped` and `teardown.phase_outcome=skipped`.
    - Observability (normative):
      - `runs/<run_id>/logs/health.json` MUST include a `health.json.stages[]` entry with:
        - `stage="runner.lifecycle_enforcement"`
        - `status="failed"`
        - `reason_code="invalid_lifecycle_transition"`
      - Stable counters MUST reflect the enforcement event:
        - `runner_invalid_lifecycle_transition_total == 1`
        - `runner_unsafe_rerun_blocked_total == 0`
    - If `side_effect_ledger.json` exists for the action, it MUST NOT contain any `execute`-phase
      entry representing command invocation.

- `revert_not_attempted_without_execute`:

  - Input:
    - requirements evaluation (or other deterministic gating) causes `execute` to be skipped, and
    - cleanup invocation would otherwise be attempted (example: `plan.cleanup=true` for the action).
  - Expected:
    - The runner MUST block the invalid transition deterministically:
      - `revert.phase_outcome=skipped` with deterministic
        `reason_code=invalid_lifecycle_transition`.
    - `teardown.phase_outcome=skipped`.
    - Observability (normative):
      - `runs/<run_id>/logs/health.json` MUST include a `health.json.stages[]` entry with:
        - `stage="runner.lifecycle_enforcement"`
        - `status="failed"`
        - `reason_code="invalid_lifecycle_transition"`
      - Stable counters MUST reflect the enforcement event:
        - `runner_invalid_lifecycle_transition_total == 1`
        - `runner_unsafe_rerun_blocked_total == 0`
    - Cleanup invocation evidence MUST be absent for the action:
      - `runner/actions/<action_id>/cleanup_stdout.txt` and
        `runner/actions/<action_id>/cleanup_stderr.txt` MUST NOT exist.
      - If `side_effect_ledger.json` exists for the action, it MUST NOT contain any `revert`-phase
        entry representing cleanup invocation.

Synthetic correlation marker fixtures under `tests/fixtures/runner/synthetic_marker/` validate
deterministic marker computation and attempted emission bookkeeping.

The fixture set MUST include at least:

- `marker_emitted`:
  - Input: runner config enables synthetic correlation marker emission.
  - Expected:
    - Ground truth includes `extensions.synthetic_correlation_marker` for the action where `execute`
      is attempted.
    - The side-effect ledger includes an `execute`-phase entry describing the marker emission
      attempt (success or failure), consistent with runner contracts.
    - The marker value conforms to the v0.1 format defined in data contracts.

For this fixture, the harness SHOULD compute
`marker_value_sha256 = sha256_hex(UTF-8 bytes of marker_value)` and assert it is identical across
repeated runs with identical inputs.

#### State reconciliation fixtures (required)

The fixture set MUST include at least:

- `record_present_reality_absent`:

  - Input: a `side_effect_ledger.json` entry indicating a resource is present/created.
  - Probe snapshot: observed state indicates the resource is absent.
  - Expected: `state_reconciliation_report.status=drift_detected` with a deterministic
    `reason_code`.
    - Stable counters MUST reflect that repair was not attempted:
      - `runner_state_reconciliation_repairs_attempted_total == 0`
      - `runner_state_reconciliation_repairs_succeeded_total == 0`
      - `runner_state_reconciliation_repairs_failed_total == 0`
      - `runner_state_reconciliation_repair_blocked_total == 0`
    - `runs/<run_id>/logs/health.json` MUST include `stage="runner.state_reconciliation"` with
      `status="success"` and MUST omit `reason_code`.

- `record_absent_reality_present`:

  - Input: a `side_effect_ledger.json` entry indicating a resource is absent/deleted.
  - Probe snapshot: observed state indicates the resource is present.
  - Expected: `state_reconciliation_report.status=drift_detected` with a deterministic
    `reason_code`.
    - Stable counters MUST reflect that repair was not attempted:
      - `runner_state_reconciliation_repairs_attempted_total == 0`
      - `runner_state_reconciliation_repairs_succeeded_total == 0`
      - `runner_state_reconciliation_repairs_failed_total == 0`
      - `runner_state_reconciliation_repair_blocked_total == 0`
    - `runs/<run_id>/logs/health.json` MUST include `stage="runner.state_reconciliation"` with
      `status="failed"` and `reason_code="drift_detected"`.

- `observe_only_drift_detected`:

  - Input:
    - action requests reconciliation policy `observe_only` (scenario-side policy), and
    - runner config enables reconciliation.
  - Probe snapshot: observed state indicates drift (example: record present but reality absent).
  - Expected (normative):
    - `state_reconciliation_report.status=drift_detected` with a deterministic `reason_code`.
    - The report MUST record at least one drift item (stable ordering as specified in data
      contracts).
    - Stable counters MUST reflect that repair was not attempted and was not blocked:
      - `runner_state_reconciliation_repairs_attempted_total == 0`
      - `runner_state_reconciliation_repairs_succeeded_total == 0`
      - `runner_state_reconciliation_repairs_failed_total == 0`
      - `runner_state_reconciliation_repair_blocked_total == 0`
    - `runs/<run_id>/logs/health.json` MUST include `stage="runner.state_reconciliation"` with
      `status="success"` and MUST omit `reason_code`.

- `clean_match`:

  - Input: a `side_effect_ledger.json` entry indicating a resource is present/created.
  - Probe snapshot: observed state indicates the resource is present.
  - Expected: `state_reconciliation_report.status=clean`.
    - Stable counters MUST reflect that no repair was required:
      - `runner_state_reconciliation_repairs_attempted_total == 0`
      - `runner_state_reconciliation_repairs_succeeded_total == 0`
      - `runner_state_reconciliation_repairs_failed_total == 0`
      - `runner_state_reconciliation_repair_blocked_total == 0`
    - `runs/<run_id>/logs/health.json` MUST include `stage="runner.state_reconciliation"` with
      `status="success"` MUST omit `reason_code`.

- `repair_requested_but_blocked`:

  - Input:
    - action requests reconciliation policy `repair` (scenario-side policy), and
    - runner config enables reconciliation but does not permit repair (v0.1 default; example:
      `runner.atomic.state_reconciliation.enabled=true` and
      `runner.atomic.state_reconciliation.allow_repair=false`).
  - Probe snapshot: observed state indicates drift that would require repair to resolve (example:
    record present but reality absent).
  - Expected (normative):
    - `state_reconciliation_report.status=drift_detected` with a deterministic `reason_code`.
    - The report MUST record that repair was requested but blocked in a deterministic way (minimum
      requirement: at least one affected reconciliation item includes `reason_code=repair_blocked`).
    - Stable counters MUST reflect that repair was not attempted and was blocked:
      - `runner_state_reconciliation_repairs_attempted_total == 0`
      - `runner_state_reconciliation_repairs_succeeded_total == 0`
      - `runner_state_reconciliation_repairs_failed_total == 0`
      - `runner_state_reconciliation_repair_blocked_total >= 1`
    - `runs/<run_id>/logs/health.json` MUST include `stage="runner.state_reconciliation"` with
      `status="failed"` and `reason_code="drift_detected"`.

For each fixture, the runner reconciliation implementation MUST:

- Emit `runs/<run_id>/logs/health.json` with a deterministic `health.json.stages[]` entry for
  reconciliation:
  - `stage="runner.state_reconciliation"` MUST be present for every fixture run where reconciliation
    is enabled.
  - When `state_reconciliation_report.status=drift_detected`, `health` MUST record `status="failed"`
    and `reason_code="drift_detected"`.
  - When `state_reconciliation_report.status=clean`, `health` MUST record `status="success"` and
    MUST omit `reason_code`.
- Emit stable reconciliation counters for determinism and operability (required set):
  - `runner_state_reconciliation_items_total`
  - `runner_state_reconciliation_drift_detected_total`
  - `runner_state_reconciliation_skipped_total`
  - `runner_state_reconciliation_unknown_total`
  - `runner_state_reconciliation_probe_error_total`
  - `runner_state_reconciliation_repairs_attempted_total`
  - `runner_state_reconciliation_repairs_succeeded_total`
  - `runner_state_reconciliation_repairs_failed_total`
  - `runner_state_reconciliation_repair_blocked_total`
- In the test harness, compute a stable hash over the report content (RECOMMENDED:
  `report_jcs_sha256` over RFC 8785 JCS canonicalized JSON) and assert the hash is identical across
  repeated runs with identical inputs and probe snapshots.

### Criteria evaluation

Criteria pack versioning tests validate that the criteria pack manifest file
`criteria/packs/<criteria_pack_id>/<criteria_pack_version>/manifest.json` has:

- field `criteria_pack_id` that MUST match `<criteria_pack_id>`, and
- field `criteria_pack_version` that MUST match `<criteria_pack_version>`.

If multiple search paths contain the same `(criteria_pack_id, criteria_pack_version)`, CI MUST fail
unless the pack snapshots are byte-identical (manifest plus criteria content hashes match).

Criteria drift detection tests validate that given a criteria pack manifest upstream with
`(engine, source_ref, source_tree_sha256)` and a runner provenance that differs, the evaluator MUST
set criteria drift to detected and MUST mark affected actions `status=skipped` with a deterministic
drift reason field.

## Integration tests

**Summary**: Integration tests validate cross-component behavior using realistic fixtures and
harnesses. They cover end-to-end scenarios, platform-specific behaviors, and recovery from failure
conditions.

### Evaluator conformance harness

The evaluator conformance harness qualifies the configured batch evaluator backend against the
determinism and compatibility requirements of this repository.

Goals:

- Detect cross-platform and cross-version drift in match sets (regressions and behavior changes).
- Provide concrete artifacts that allow reviewers to triage changes introduced by:
  - backend upgrades,
  - regex engine upgrades,
  - OCSF mapping pack changes,
  - schema snapshot changes.

#### Inputs

- A pinned Baseline Detection Package (BDP) (preferred for Run CI replay), OR an unpacked fixture
  event set (JSONL and/or Parquet) under `tests/fixtures/evaluator_conformance/`.
  - When a BDP is used, the harness MUST read normalized events from the BDP normalized event store
    (see `086_detection_baseline_library.md`).
  - Run CI MUST execute this harness against at least one pinned BDP version.
- A pinned rule set under `tests/fixtures/evaluator_conformance/rules/`, including:
  - event rules (single-event),
  - correlation rules (all supported correlation types),
  - regex-heavy rules (PCRE2 constructs).

#### Execution

- The harness MUST run the evaluator end-to-end:

  1. compile rules to `bridge/compiled_plans/`
  1. execute compiled plans over the fixture event set
  1. write detections to `detections/detections.jsonl`

- The harness MUST compute and record the following per backend + fixture version:

  - `compiled_plan_hash`:
    - SHA256 of canonical JSON (JCS) for each `bridge/compiled_plans/<rule_id>.plan.json`
  - `detections_hash`:
    - SHA256 of canonical JSON (JCS) for the ordered contents of `detections/detections.jsonl`

#### Output artifacts

- The harness MUST emit a conformance report:

  - JSON: `artifacts/evaluator_conformance/<report_id>/report.json`
  - Markdown summary (optional): `artifacts/evaluator_conformance/<report_id>/summary.md`

- The JSON report MUST conform to the evaluator conformance report schema:

  - `../contracts/evaluator_conformance_report.schema.json`

#### Failure classification

The harness MUST classify mismatches with stable categories:

- `plan_hash_mismatch`
- `result_hash_mismatch`
- `backend_error` (compile or evaluation failure)

Where possible, the harness SHOULD include a human-readable diff summary (for example, a small
sample of added/removed matched event ids).

## CI gates

**Summary**: CI gates define pass/fail criteria for pipeline runs. Gates are categorized as
fail-closed (blocking) or configurable (threshold-based).

### Schema validation

Schema validation of produced OCSF events ensures all normalized events conform to the pinned OCSF
schema.

Schema validation of effective configuration validates `inputs/range.yaml` against
`docs/contracts/range_config.schema.json`.

The fixture set MUST include at least:

- `range_config_gap_taxonomy_invalid_token_rejected` (fail closed)
  - Provide a `inputs/range.yaml` fixture that includes a non-canonical `scoring.gap_taxonomy[]`
    token.
  - Assert schema validation fails closed.
  - Assert the failure output identifies the invalid token location deterministically (for example,
    a JSON pointer or dotted path to the array element).

### Version conformance

Pinned-version consistency checks (fail closed) validate that canonical pins under
`manifest.versions.*` match any mirrored pin fields in produced artifacts (when present). For
example, the pinned OCSF version MUST be consistent across:

- `manifest.versions.ocsf_version` (canonical)
- `normalized/mapping_profile_snapshot.json.ocsf_version`
- bridge mapping pack snapshot `ocsf_version` (when present)

External dependency version matrix (fail closed; v0.1) requires CI MUST run the integration and
"golden run" fixtures using the pinned dependency versions in the
[supported versions reference](../../SUPPORTED_VERSIONS.md). CI MUST fail if any enabled runtime
dependency version differs from the pins.

Selected determinism-critical pins for v0.1 (excerpt; the supported versions reference is
authoritative):

| Dependency                      | Version |
| ------------------------------- | ------- |
| OpenTelemetry Collector Contrib | 0.143.1 |
| pySigma                         | 1.1.0   |
| pySigma-pipeline-ocsf           | 0.1.1   |
| PCRE2 (libpcre2-8)              | 10.46   |
| pyarrow                         | 22.0.0  |
| jsonschema                      | 4.26.0  |
| osquery                         | 5.14.1  |
| OCSF schema                     | 1.7.0   |
| PowerShell                      | 7.4.6   |
| DSC                             | 3.1.2   |
| asciinema                       | 2.4.0   |

CI SHOULD also enforce the pinned toolchain versions listed in the supported versions reference
(Python, uv, pytest, ruff, pyright) to reduce non-deterministic test behavior.

#### Historical run bundle compatibility matrix (compatibility promise)

To prevent consumer-side reimplementation of ad hoc migration logic, CI MUST assert the project's
historical run bundle compatibility promise (ADR-0001) by validating a fixed set of archived
("golden") run bundles from prior releases.

Minimum requirement (v0.1):

- CI MUST include fixtures for at least `N=1` prior compatibility major within the supported window
  (current + previous) for each of:
  - `manifest.versions.pipeline_version`
  - `manifest.versions.contracts_version`
  - Parquet dataset `schema_version` values recorded under `manifest.versions.datasets` (when
    applicable)
- CI MUST run the current run-bundle validator against each historical fixture bundle and MUST
  assert:
  - `manifest.json` parses and validates against `manifest.schema.json`.
  - Contract-backed artifacts required for reporting and scoring validate against their contracts
    (or are explicitly marked absent by feature flags for that fixture).
  - Any Parquet dataset included as a fixture has a valid `_schema.json` snapshot and is readable
    with union-by-name semantics (see `045_storage_formats.md`).
- Any failure to parse, locate required artifacts, or validate contracts in this matrix MUST fail CI
  (fail closed). The failure output MUST identify the fixture bundle deterministically (for example,
  by `run_id` and pinned versions).

Notes:

- For SemVer `0.y.z`, treat `0.y` as the compatibility-major boundary (ADR-0001).
- The fixture set SHOULD be small (smoke-level) but MUST include at least one bundle that exercises
  reporting outputs (`report/report.json` + `report/thresholds.json` + `report/run_timeline.md`).

### Determinism gates

The evaluator conformance gate (toolchain determinism; configurable) enforces deterministic
evaluation results for the configured evaluator backend. Default CI behavior (RECOMMENDED):
`result_hash_mismatch` MUST fail CI (fail closed) and `plan_hash_mismatch` SHOULD warn but MUST NOT
fail CI unless explicitly enabled as a gate.

CI SHOULD retain the conformance report as a build artifact to support fixture refresh review on
backend and regex engine upgrades, platform qualification (OS/arch) changes, and drift triage when
golden fixtures regress.

### Artifact validation

Linting and validation for Sigma rules ensures syntactic and semantic correctness.

Contract validation MUST also enforce deterministic artifact path rules for contracted directories.
Fixtures MUST include a negative (fail-closed) case that introduces a prohibited timestamped
filename in a contracted directory.

The fixture set MUST include at least:

- `artifact_path_timestamped_filename_blocked` (CI lint-style)
  - Provide a minimal run bundle containing a file with a timestamped filename located inside a
    contracted directory (for example, under `runs/<run_id>/runner/` or another contracted subtree).
  - Assert contract validation fails closed and emits
    `runs/<run_id>/logs/contract_validation/runner.json`.
  - Assert the contract validation report contains an error with:
    - `artifact_path` matching the offending path (run-relative; POSIX separators)
    - `error_code = "timestamped_filename_disallowed"` (stable error code for this class of
      violation)
- `offline_contract_validation_with_schema_bundle`: Provide a valid run bundle fixture and a
  matching contracts bundle fixture (directory or tarball) and assert that contract validation
  succeeds with (a) network access disabled and (b) no repository checkout available (only the two
  bundles on disk).
- `stage_isolation_fixture_per_stage` (per-stage seam fixtures; independent stage build)
  - Normative rule: Each stage MUST have at least one stage-isolation fixture that contains the
    minimum upstream artifacts required to run that stage and produces contract-valid outputs for
    that stage.
  - Scope (normative):
    - "Stage" means each v0.1 `stage_id` defined in ADR-0005 ("Stage identifiers").
    - The `signing` stage is in-scope only when signing is enabled/implemented.
  - Fixture contents (normative):
    - The stage-isolation fixture input bundle MUST be a pruned run bundle rooted at
      `runs/<run_id>/` containing only the upstream artifacts required by the stage under test for
      the fixture's enabled feature set.
    - The input bundle MUST NOT include artifacts produced by the stage under test or any later
      stage(s) (prevents hidden coupling on downstream outputs).
    - The fixture MUST include an expected outputs manifest for the stage under test, used to make
      "artifact manifest completeness" checks deterministic and to support offline stage
      development.
      - RECOMMENDED location: `expected_outputs.json` adjacent to the fixture input bundle.
      - Manifest format (normative): JSON array of objects, each containing:
        - `artifact_path` (string; run-relative; POSIX separators)
        - `contract_id` (string; resolvable via the contracts bundle)
        - `required` (boolean)
      - The array MUST be sorted by `artifact_path` ascending (bytewise lexicographic).
  - Verification (normative; fail closed):
    - CI MUST execute the stage under test using only the fixture input bundle (no upstream stages
      executed).
    - CI MUST validate produced outputs offline against the pinned contracts bundle (network
      disabled; no repository checkout), consistent with
      `offline_contract_validation_with_schema_bundle`.
    - CI MUST assert:
      - every `required=true` expected output exists at its declared `artifact_path`,
      - each produced expected output validates against its contract, and
      - deterministic artifact path rules hold for produced contracted directories (timestamped
        filenames blocked).

Report generation sanity checks validate that reports render without errors.

Artifact manifest completeness check ensures all expected artifacts are present.

### Cross-artifact invariants

Cross-artifact invariants enforce consistency across pipeline outputs:

- `run_id` and `scenario_id` consistency across all artifacts
- Referential integrity (detections reference existing `event_id` values)
- Inventory snapshot hash matches manifest input hash
- When `operability.health.emit_health_files=true`, `runs/<run_id>/logs/health.json` MUST exist and
  MUST satisfy the minimum schema in the [operability specification](110_operability.md) ("Health
  files (normative, v0.1)")
- Health outcome registry conformance (fail closed):
  - Each `health.json.stages[].stage` value MUST be a valid stage or substage identifier (dotted
    substages allowed) consistent with the architecture specification.
  - Each `health.json.stages[].reason_code` value (when present) MUST be drawn from ADR-0005 for the
    corresponding stage/substage; unknown reason codes MUST fail CI.

### Consumer tooling conformance (reference reader semantics)

Run bundles are consumed by multiple tools (CI validator, report generator, dataset builder, future
UI, exporters). CI MUST enforce that first-party consumers share a single reader semantics surface
(`pa.reader.v1`) defined in `025_data_contracts.md` ("Consumer tooling: reference reader
semantics").

For CI enforcement, each first-party consumer MUST expose an inventory-derivation entrypoint that
can be invoked by tests (either as a library call or as a CLI mode) which emits `pa.inventory.v1` as
canonical JSON bytes (`canonical_json_bytes(...)`).

Fixture set (normative):

- `consumer_reader_inventory_view_consistency` (cross-consumer semantic lock)

  - Provide a minimal run bundle fixture that includes, at minimum:
    - `manifest.json` with a non-empty `versions` object and at least two `stage_outcomes` entries
    - `ground_truth.jsonl`
    - one deterministic evidence log under `logs/` (example: `logs/counters.json`)
    - one volatile diagnostics log under `logs/` (example: `logs/run.log`)
    - one withheld placeholder artifact (to ensure placeholder-handling does not break discovery)
    - one quarantined artifact under `unredacted/` (to validate default deny and exclusion rules)
  - Test harness MUST invoke at least two independent consumer entrypoints (at minimum: report
    generator and CI validator) against the same fixture and capture their derived inventory view
    (`pa.inventory.v1`) as canonical JSON bytes.
  - Assertions (normative):
    - byte-for-byte equality between consumer outputs, and
    - equality against the reference reader SDK output for the same fixture.

- `consumer_reader_error_codes_stability` (deterministic gating surface)

  - Provide a small suite of invalid run bundle fixtures that each exercise one primary reader error
    code defined in `025_data_contracts.md` (minimum examples):
    - `manifest_parse_error` (invalid JSON)
    - `contract_registry_missing` (registry absent)
    - `artifact_representation_conflict` (both OCSF store representations present)
    - `quarantine_access_denied` (attempted read under `unredacted/` without opt-in)
    - `version_pin_conflict` (scenario id/version mismatch between authoritative locations)
  - For each fixture, invoke the same consumer entrypoints as above and assert:
    - identical `error_domain` and `error_code`, and
    - deterministic error ordering when multiple errors are emitted.

### Producer tooling conformance (reference publisher semantics)

Run bundles are produced by multiple entrypoints (the orchestrator and any per-stage CLIs/wrappers).
CI MUST enforce that first-party producers share a single publisher semantics surface
(`pa.publisher.v1`) defined in `025_data_contracts.md` ("Producer tooling: reference publisher
semantics").

For CI enforcement, any first-party producer entrypoint that can publish contract-backed artifacts
MUST either:

- use the reference publisher SDK directly, or
- demonstrate semantic conformance via CI fixtures that compare publish behavior and emitted
  validation reports against the reference publisher output.

Fixture set (normative):

- `publisher_publish_gate_no_partial_promotion` (validation failure does not publish)

  - Provide a minimal run bundle fixture and a deliberately invalid contract-backed artifact written
    via `PublishGate` staging.
  - Assertions (normative):
    - `finalize()` reports failure,
    - no final-path contracted output is present (all stage outputs remain unpublished),
    - the contract validation report exists at
      `runs/<run_id>/logs/contract_validation/<stage_id>.json`, and
    - errors in the report follow the deterministic ordering + truncation rules in
      `025_data_contracts.md` ("Deterministic error ordering and error caps").

- `publisher_publish_gate_success_atomic_promotion` (success publishes and cleans staging)

  - Provide a minimal run bundle fixture and a valid contract-backed artifact.
  - Assertions (normative):
    - `finalize()` reports success,
    - the final-path artifact exists and matches the canonical serialization rules required by
      `pa.publisher.v1`, and
    - `runs/<run_id>/.staging/<stage_id>/` is absent (or empty) after publish.

- `publisher_crash_mid_promotion_reconciliation` (crash mid-promotion is reconciled
  deterministically)

  - Provide a minimal run bundle fixture with a stage that has at least two REQUIRED
    `expected_outputs[]` entries under different run-relative prefixes (for example,
    `criteria/manifest.json` and `logs/counters.json`) staged under
    `runs/<run_id>/.staging/<stage_id>/`.
  - Simulate a crash after promoting at least one expected output into its final path but before
    promoting all REQUIRED outputs and before recording the terminal stage outcome.
    - The harness MAY use a test-only failpoint, signal, or injected kill; the mechanism is
      implementation-defined.
  - Assertions (normative):
    - On restart, the orchestrator reconciliation pass MUST re-run publish-gate contract validation
      over the final-path outputs for the stage (per ADR-0004).
    - Because at least one REQUIRED output is missing, validation MUST fail and the orchestrator
      MUST record a fail-closed stage outcome.
    - The failure MUST use a stable `reason_code` across repeated restarts (RECOMMENDED:
      `storage_io_error` for partial publish).
    - Downstream stages MUST be marked `skipped` (blocked by upstream failure), and repeated
      restarts MUST be idempotent (no additional mutation beyond idempotent outcome recording and
      `.staging/**` cleanup).

- `publisher_canonical_json_and_jsonl_bytes` (serialization lock)

  - Using the reference publisher SDK:
    - publish one JSON artifact via `write_json(..., canonical=true)`, and
    - publish one JSONL artifact via `write_jsonl(rows_iterable)`.
  - Assertions (normative):
    - JSON bytes equal `canonical_json_bytes(...)`,
    - JSONL uses LF, no BOM, no blank lines, and the end-of-file newline rule from
      `025_data_contracts.md` ("Producer tooling: reference publisher semantics").

- `publisher_contract_validator_yaml_document` (YAML document validation)

  - Provide a minimal contracted YAML artifact fixture (for example `inputs/range.yaml` bound to
    `range_config` with `bindings[].validation_mode = "yaml_document"` in the registry).
  - Assertions (normative):
    - The reference `ContractValidator` validates YAML documents when
      `validation_mode=yaml_document`.
    - A syntactically invalid YAML document OR a schema-invalid YAML document MUST fail validation
      deterministically, and MUST emit a contract validation report that follows the deterministic
      ordering + truncation rules in `025_data_contracts.md` ("Deterministic error ordering and
      error caps").

### Export and checksums scope

The run bundle `logs/` directory is intentionally mixed: it contains both deterministic evidence and
volatile diagnostics. Default export and signing/checksum scope MUST follow the Tier 0 taxonomy
defined by the storage formats spec and ADR-0009.

CI MUST enforce, at minimum:

- Deterministic evidence under `logs/` is included in:
  - default export manifests (when export is implemented), and
  - `security/checksums.txt` (when signing is enabled).
- Volatile diagnostics under `logs/` are excluded from both.

Fixture set (normative):

- `export_scope_logs_classification` (signing + export allowlist)
  - Provide a minimal run bundle tree containing both deterministic evidence logs and volatile
    diagnostics logs:
    - deterministic evidence:
      - `logs/health.json`
      - `logs/counters.json`
      - `logs/telemetry_validation.json`
      - `logs/cache_provenance.json`
      - `logs/lab_inventory_snapshot.json`
      - `logs/contract_validation/runner.json`
    - volatile diagnostics:
      - `logs/run.log`
      - `logs/warnings.jsonl`
      - `logs/eps_baseline.json`
      - `logs/telemetry_checkpoints/**`
      - `logs/dedupe_index/ocsf_events.jsonl`
      - `logs/scratch/tmp.txt`
    - quarantine example:
      - `unredacted/runner/actions/s1/stdout.txt`
    - publish-gate scratch example:
      - `.staging/tmp.bin`

Assertions (normative):

- Signing scope (when signing is enabled):

  - Generate `security/checksums.txt` per `025_data_contracts.md`.
  - Assert `security/checksums.txt` includes all deterministic evidence files under `logs/` above.
  - Assert `security/checksums.txt` excludes all volatile diagnostics paths above.
  - Assert `security/checksums.txt` excludes the quarantine directory and `.staging/`.

- Export scope (when export is implemented):

  - Export with default flags (no quarantine, no binary evidence, no volatile diagnostics).
  - Assert the resulting `export_manifest.json` includes deterministic evidence under `logs/`.
  - Assert the resulting `export_manifest.json` excludes volatile diagnostics under `logs/`, the
    quarantine directory, and `.staging/`.

Suggested failure messages (non-normative):

- `FAIL export_scope: volatile diagnostics leaked into export: <path>`
- `FAIL signing_scope: deterministic evidence missing from checksums: <path>`

### Regression gates

Regression gates (configurable thresholds) protect against coverage and performance degradation:

- `technique_coverage_rate` delta (`candidate - baseline`) must not be < -0.0500
- `detection_latency_p95_seconds` delta (`candidate - baseline`) must not be > +60.000
- `tier1_field_coverage_pct` delta (`candidate - baseline`) must not be < -0.0500
- `missing_telemetry_count` delta (`candidate - baseline`) must not be > +2
- `bridge_gap_mapping_count` delta (`candidate - baseline`) must not be > +5

These thresholds are defined in `080_reporting.md` (“Regression deltas”) and MAY be overridden via
`reporting.regression.thresholds` (see `120_config_reference.md`).

Regression comparison precondition failures (for example, missing or incompatible baselines) MUST be
represented as a `warn_and_skip` stage outcome under the reporting regression compare substage
(`stage="reporting.regression_compare"`), consistent with stage outcomes being the sole input to run
status derivation (see ADR-0005).

## CI workflow pattern

The recommended CI workflow proceeds through six stages:

1. Resolve lab inventory (provider or fixture)
1. Execute scenario suite (runner)
1. Collect telemetry (OTel) and validate telemetry health gates
1. Normalize telemetry to OCSF (normalization)
1. Evaluate criteria (validation), evaluate detections (Sigma), and score gaps (scoring)
1. Produce report plus machine-readable summary, then compare to baseline and fail when thresholds
   are violated (reporting + reporting.regression_compare)

## State machine integration notes (v0.1)

This spec’s fixtures act as conformance tests for lifecycle/state machines whose authoritative
definitions live outside this document:

- Runner action lifecycle state machine:
  - Authority: scenario model + runner/executor integration + runner lifecycle guard semantics.
  - Conformance fixtures: `tests/fixtures/runner/lifecycle/`, requirements gating, unsafe rerun
    blocking, invalid transition blocking.
- Runner reconciliation lifecycle:
  - Authority: data contracts (state reconciliation report ordering) + operability (health +
    counters).
  - Conformance fixtures: `tests/fixtures/runner/state_reconciliation/`.
- Reporting regression compare lifecycle:
  - Authority: reporting spec regression semantics + ADR-0005 substage outcomes.
  - Conformance fixtures: baseline present/identical, baseline intentional change, baseline missing,
    baseline incompatible.

When adding a new stateful lifecycle that needs deterministic conformance, document the state
machine using the ADR-0007 template and add fixture-driven conformance tests here.

## Key decisions

- Unit tests are organized by pipeline stage to enable targeted validation and clear ownership.
- The evaluator conformance harness provides toolchain qualification across the version × OS × arch
  matrix.
- CI gates use fail-closed semantics for version conformance and configurable thresholds for
  regression protection.
- Fixtures cover both happy-path determinism and failure-mode recovery scenarios.

## References

- [OCSF mapping profile authoring guide](../mappings/ocsf_mapping_profile_authoring_guide.md)
- [Sigma-to-OCSF bridge specification](065_sigma_to_ocsf_bridge.md)
- [Operability specification](110_operability.md)
- [Telemetry pipeline specification](040_telemetry_pipeline.md)
- [Normalization to OCSF specification](050_normalization_ocsf.md)
- [Data contracts specification](025_data_contracts.md)
- [Evaluator conformance report schema](../contracts/evaluator_conformance_report.schema.json)
- [Supported versions reference](../../SUPPORTED_VERSIONS.md)

## Changelog

| Date       | Change                                                                                                      |
| ---------- | ----------------------------------------------------------------------------------------------------------- |
| 2026-01-24 | Add regression tests for export/checksum scope of `logs/` (deterministic evidence vs volatile diagnostics). |
| 2026-01-13 | Style guide conformance reformat                                                                            |
| 2026-01-12 | Formatting update                                                                                           |
