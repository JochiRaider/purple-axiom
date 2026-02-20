---
title: Test strategy and CI
description: Defines the unit, integration, and CI gating expectations for deterministic runs.
status: draft
tags: []
category: spec
related:
  - 020_architecture.md
  - 025_data_contracts.md
  - 026_contract_spine.md
  - 030_scenarios.md
  - 032_atomic_red_team_executor_integration.md
  - 035_validation_criteria.md
  - 040_telemetry_pipeline.md
  - 050_normalization_ocsf.md
  - 060_detection_sigma.md
  - 065_sigma_to_ocsf_bridge.md
  - 080_reporting.md
  - 105_ci_operational_readiness.md
  - 110_operability.md
  - SUPPORTED_VERSIONS.md
  - ADR-0005-stage-outcomes-and-failure-classification.md
  - ADR-0007-state-machines.md
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
  - For contract-backed artifacts, schema-owned `reason_domain` values MUST equal the artifact
    schema `contract_id`.
    - Exemption (placeholder namespace): `placeholder.reason_domain` MUST be `artifact_placeholder`
      and MUST NOT be subject to the "must equal contract_id" check.

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

- Contract Spine conformance gate (contract registry invariants, canonical serialization,
  publisher/reader conformance) (see `026_contract_spine.md`).
- Sigma ruleset determinism + uniqueness + required metadata (see `060_detection_sigma.md`).
- Mapping pack validation + router determinism (see `065_sigma_to_ocsf_bridge.md`).
- Sigma compilation to compiled plans (`bridge_compiled_plan`) for the selected backend (see
  `065_sigma_to_ocsf_bridge.md`).
- Compiled plan semantic validation (see `065_sigma_to_ocsf_bridge.md`, "Compiled plan semantic
  validation policy").
- Contract/schema validation for any content-like artifacts under test (mapping packs, criteria
  packs, compiled plans, Baseline Detection Packages, etc.).
- Static semantic checks (see "Static semantic checks").
- Unit tests that do not require a lab provider (this section).
- Detection Content Release (detection content bundle) build + offline validation (see
  `025_data_contracts.md`, "Detection content bundle distribution and validation").

Content CI MUST fail closed when compilation or validation cannot be completed deterministically.

Verification hook (normative): CI workflow MUST fail a pull request that breaks compilation or
validation without spinning up a lab provider.

Content CI harness fixture suite (normative):

- CI MUST include at least one end-to-end fixture suite that executes the `ci-content` entrypoint
  against deterministic fixture workspaces without a lab provider.
- The fixture suite MUST assert expected exit codes deterministically for both a passing and a
  failing case.
- Canonical fixture root: `tests/fixtures/ci/content_ci_harness/` (see "Fixture index").
- Each fixture case under `tests/fixtures/ci/content_ci_harness/<case>/` MUST include:
  - `inputs/workspace/` as the workspace root to run `ci-content` against, and
  - `expected/expected_exit_code.txt` containing `0` or `20` (ASCII, trailing newline optional).
- The fixture runner MUST invoke `ci-content` with the working directory set to `inputs/workspace/`
  for the case.

### Run CI gate set (normative)

Run CI MUST include, at minimum:

- The evaluator conformance harness executed against at least one pinned Baseline Detection Package
  (BDP) or equivalent pinned event fixture set (see "Evaluator conformance harness").
- At least one end-to-end "golden run" bundle executed in a minimal lab profile when a lab provider
  is available (RECOMMENDED).

Run CI MAY be triggered less frequently than Content CI (for example on merge-to-main and/or on
release), but MUST be executed before release publication.

### Static semantic checks

Static semantic checks are deterministic validations that go beyond schema validation and
compilation success. They are intended to catch authoring errors early (in Content CI) instead of
surfacing later during integration (Run CI).

Content CI MUST run the static semantic checks defined in this section. Implementations MAY add
additional checks, but any added checks MUST preserve determinism (stable ordering, stable error
classification, no network fetch).

#### determinism-critical checks

These checks are determinism-critical and MUST be treated as **errors** in Content CI.

Minimum checks (normative):

- Sigma authoring invariants: enforce deterministic rule discovery, unique `id`, and required rule
  metadata per `060_detection_sigma.md`.
- Router determinism: for each Sigma rule `logsource`, routing via the selected mapping pack MUST
  yield a single deterministic route; ambiguous routing MUST fail closed.
- Mapping pack referential integrity: mapping pack references (classes, aliases, transforms) MUST
  resolve; dangling references MUST fail closed.
- Criteria pack integrity (when criteria packs are present in the change): pack manifests and
  entries MUST validate and integrity hashes MUST recompute successfully per
  `035_validation_criteria.md`.

#### quality/hygiene checks

These checks are deterministic quality/hygiene checks. They SHOULD run in Content CI and SHOULD be
surfaced in pull request feedback, but they MAY be treated as warnings by default.

Minimum checks (normative):

- ATT&CK tag hygiene: rules SHOULD include at least one valid `attack.t*` tag; missing tags SHOULD
  emit a warning (rules remain eligible for evaluation as defined in `060_detection_sigma.md`).
- Documentation hygiene: rules SHOULD include `references` when available; missing references SHOULD
  emit a warning.

Verification (normative): the Content CI harness fixture suite MUST include at least one failing
case that triggers a static semantic check and MUST assert exit code `20` for that case.

## Fixture index

This section defines the **canonical fixture roots** for each stage and cross-cutting component.

Stage specs MUST link to this section from their `### Isolation test fixture(s)` blocks rather than
duplicating fixture-root lists. When a stage spec needs a new fixture root, it MUST be added here
and referenced consistently.

Conventions (normative):

- A *fixture root* is a directory under `tests/fixtures/` that contains one or more *fixture cases*.
- A *fixture case* is a leaf directory that contains:
  - `inputs/` (minimum required inputs for the stage/feature under test), and
  - `expected/` (golden outputs or assertion maps used by test harnesses).
- Fixture cases MUST be named deterministically (no timestamps, no machine-specific paths).
- Unless stated otherwise by a contract, fixture suites MUST compare JSON artifacts using the
  contract-defined canonical JSON rules (not text diffs).

| Stage / area                                                             | Canonical fixture roots                                                                                                                                                               | Minimum fixture sets (normative)                                                                                                                        |
| ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Cross-cutting: glob matching (`glob_v1`)                                 | `tests/fixtures/glob_v1/vectors.json`                                                                                                                                                 | `glob_v1_vectors` (vectors file present and exercised)                                                                                                  |
| Cross-cutting: event identity (`event_id.v1`)                            | `tests/fixtures/event_id/v1/`                                                                                                                                                         | `tier1_smoke`, `tier2_smoke`, `tier3_collision`, `source_type_distinct`                                                                                 |
| Cross-cutting: redaction (`pa.redaction.v1`)                             | `tests/fixtures/redaction/v1/`                                                                                                                                                        | `allowlist_smoke`, `denylist_smoke`, `stable_hashes`                                                                                                    |
| Cross-cutting: integration credentials (`pa.integration_credentials.v1`) | `tests/fixtures/integration_credentials/v1/`                                                                                                                                          | `logs_redaction_smoke`, `artifact_absence_smoke`, `missing_fails_closed`, `invalid_fails_closed`, `leak_detected_fails_closed`                          |
| Cross-cutting: run results summary (`run_results`)                       | `tests/fixtures/run_results/`                                                                                                                                                         | `run_results_contract_and_hash`                                                                                                                         |
| Cross-cutting: detection content bundle (`detection_content_release_v1`) | `tests/fixtures/content_bundles/detection_content_release_v1/`                                                                                                                        | `content_bundle_offline_validation_smoke`, `run_plus_content_bundle_validation_smoke`                                                                   |
| `lab_provider`                                                           | `tests/fixtures/lab_providers/`                                                                                                                                                       | `provider_smoke`, `failure_mapping_smoke`                                                                                                               |
| `runner`                                                                 | `tests/fixtures/runner/lifecycle/`<br>`tests/fixtures/runner/state_reconciliation/`<br>`tests/fixtures/runner/noise_profile/`                                                         | `lifecycle_smoke`, `invalid_transition_blocked`, `state_reconciliation_smoke`, `noise_profile_snapshot_smoke`, `noise_profile_canonicalization_crlf_lf` |
| `telemetry`                                                              | `tests/fixtures/telemetry/synthetic_marker/`<br>`tests/fixtures/unix_logs/`<br>`tests/fixtures/osquery/`                                                                              | `synthetic_marker_smoke`, `unix_logs_smoke`, `osquery_smoke`                                                                                            |
| `normalization`                                                          | `tests/fixtures/normalization/`                                                                                                                                                       | `tier1_core_common_smoke`, `actor_identity_smoke`                                                                                                       |
| `validation` (criteria evaluation)                                       | `tests/fixtures/criteria/`                                                                                                                                                            | `criteria_time_window_smoke`, `criteria_eval_smoke`, `criteria_authoring_compile_smoke`, `criteria_pack_lint_smoke`                                     |
| `detection` (Sigma + Bridge)                                             | `tests/fixtures/sigma_rule_tests/<test_id>/`                                                                                                                                          | `rule_smoke`, `unsupported_feature_rejected`                                                                                                            |
| `scoring`                                                                | `tests/fixtures/scoring/`                                                                                                                                                             | `regression_comparables_smoke`                                                                                                                          |
| `reporting`                                                              | `tests/fixtures/reporting/defense_outcomes/`<br>`tests/fixtures/reporting/thresholds/`<br>`tests/fixtures/reporting/regression_compare/`<br>`tests/fixtures/reporting/report_render/` | `defense_outcomes_attribution_v1`, `thresholds_contract_and_ordering`, `regression_compare_smoke`, `report_render_smoke`                                |
| `signing` (when enabled)                                                 | `tests/fixtures/signing/`                                                                                                                                                             | `checksums_smoke`, `tamper_detected`                                                                                                                    |
| Content governance: golden datasets                                      | `tests/fixtures/golden_datasets/governance/`                                                                                                                                          | `valid_minimal_golden`, `missing_required_artifact_fails`                                                                                               |
| Dataset exports: dataset release artifacts (workspace validation)        | `tests/fixtures/golden_datasets/releases/`                                                                                                                                            | `dataset_release_smoke_valid`, `dataset_release_schema_invalid_fails`                                                                                   |
| CI harness: Content CI                                                   | `tests/fixtures/ci/content_ci_harness/`                                                                                                                                               | `smoke_pass`, `smoke_fail`                                                                                                                              |

## Unit tests

**Summary**: Unit tests validate individual components in isolation using deterministic fixtures.
Each test category targets a specific pipeline stage or cross-cutting concern.

### Run results summary (run_results.json)

The `runs/<run_id>/run_results.json` artifact is a compact, stable decision surface intended to
reduce CI "time-to-signal" and point to richer evidence artifacts.

The fixture set `run_results_contract_and_hash` MUST validate:

- Schema validation: `runs/<run_id>/run_results.json` MUST validate against
  `run_results.schema.json`.
- Cross-artifact coupling:
  - When `runs/<run_id>/manifest.json` is present and schema-valid, `run_results.run_id` MUST equal
    `manifest.run_id` and `run_results.status` MUST equal `manifest.status`.
  - When `runs/<run_id>/report/thresholds.json` is present and schema-valid, `run_results.status`
    MUST equal `report/thresholds.json.status_recommendation`.
- Stable bytes for fixtures: CI MUST assert a stable SHA-256 over the exact published bytes of
  `run_results.json` for fixed golden fixtures (no "parse and re-emit" allowed).

At minimum, `tests/fixtures/run_results/` MUST include:

- `happy_path_thresholds_source/` (thresholds present; status derived from thresholds; metrics
  copied from thresholds gates)
- `fallback_manifest_source/` (thresholds absent; manifest present; status derived from manifest)
- `schema_invalid/` (schema-invalid `run_results.json` fails closed)

### Event identity and canonicalization

Canonicalization tests validate RFC 8785 (JCS) vectors plus Purple Axiom hash-basis fixtures,
requiring byte-for-byte determinism.

Windows Event Log raw XML tests validate identity-field extraction without RenderingInfo, binary
field detection, and payload limit truncation with SHA-256 computation.

Linux event identity basis tests use auditd/journald/syslog fixture vectors covering Tier 1 and Tier
2 fields, plus Tier 3 collision fixtures under `tests/fixtures/event_id/v1/`.

Additional required vectors (normative):

- `metadata.source_type != identity_basis.source_type`:
  - The fixture set under `tests/fixtures/event_id/v1/` MUST include at least one case where the
    envelope `metadata.source_type` differs from `identity_basis.source_type`.
  - The differing values MUST be chosen so that substituting `metadata.source_type` for
    `identity_basis.source_type` in the hash basis would change the expected `metadata.event_id`
    (trap vector; ensures conflation bugs fail closed).
  - The test MUST assert that:
    - `metadata.event_id` is computed using `identity_basis.source_type` (not
      `metadata.source_type`), and
    - both fields are preserved (no forced equality, no rewriting).

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

### Integration credentials

Integration credentials are pipeline secrets used to authenticate to external systems (for example
Threatest, lab provider APIs, or other orchestrators). The test suite MUST prove that resolved
credential values:

1. are redacted/absent from logs, and
1. are absent from all contract-backed artifacts.
1. fail closed with `reason_code=integration_credentials_leaked` when a resolved credential value is
   detected in persisted output bytes (artifacts or logs).

Fixture root: `tests/fixtures/integration_credentials/v1/`

Required fixture cases (normative):

- `logs_redaction_smoke`

  - Inputs:
    - Minimal config enabling a test integration that declares at least one required credential
      (example: `api_token_ref`) via `security.integration_credentials`.
    - Secret reference uses the `env:` provider.
    - Test harness sets a sentinel secret value in the referenced environment variable (example:
      `PA_TEST_SECRET_SENTINEL="pa-secret-sentinel-DO-NOT-LOG"`).
  - Assertions:
    - No log output produced by the harness (stdout/stderr and any persisted logs) contains the
      sentinel secret value.
    - If the harness logs credential configuration, it MUST log only redacted placeholders and MUST
      preserve key presence so that "missing vs present" is observable without revealing the secret.

- `artifact_absence_smoke`

  - Inputs: same as `logs_redaction_smoke`.
  - Assertions:
    - Scan every contract-backed artifact emitted by the harness (use
      `docs/contracts/contract_registry.json` `bindings[].artifact_glob` to identify the set) and
      assert the sentinel secret value does not appear anywhere in the artifact bytes.

- `missing_fails_closed`

  - Inputs:
    - Config requires a credential via `security.integration_credentials`.
    - The referenced secret is unset/missing in the configured secret provider.
  - Assertions:
    - Run MUST fail closed.
    - `logs/health.json` (or `manifest.stage_outcomes[]`) MUST include a failed outcome for substage
      `runner.integration_credentials` with `reason_code=integration_credentials_missing`.

- `leak_detected_fails_closed`

  - Inputs:
    - Same as `logs_redaction_smoke`, but the test integration intentionally writes the resolved
      credential value into a persisted output stream (RECOMMENDED target: `logs/run.log`).
  - Assertions:
    - Run MUST fail closed.
    - `logs/health.json` (or `manifest.stage_outcomes[]`) MUST include a failed outcome for substage
      `runner.integration_credentials` with `reason_code=integration_credentials_leaked`.
    - Any CI/test harness diagnostics for this failure MUST NOT print the sentinel secret value.

- `invalid_fails_closed`

  - Inputs:
    - Config requires a credential via `security.integration_credentials`.
    - The referenced secret resolves successfully but fails integration validation (for example the
      test integration enforces a deterministic format check).
  - Assertions:
    - Run MUST fail closed.
    - `logs/health.json` (or `manifest.stage_outcomes[]`) MUST include a failed outcome for substage
      `runner.integration_credentials` with `reason_code=integration_credentials_invalid`.

Scanner requirement (normative):

- The fixture harness MUST implement a byte-scanning helper that searches for the sentinel secret
  byte sequence in:
  - all contract-backed artifacts (as defined by the contract registry bindings), and
  - all log outputs emitted by the harness.
- The scan MUST be performed on raw bytes (not parsed JSON) to avoid parser-normalization false
  negatives.
- The scanning helper MUST enumerate scanned files in deterministic order (run-relative path sort).
- The scanning helper MUST NOT print the sentinel secret value in any failure output.

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
"Normalization mapping profile snapshot").

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
  schema MUST be rejected deterministically with `reason_code="unmapped_field"` and an explanation
  beginning with `PA_BRIDGE_INVALID_OCSF_PATH:`.
- Prohibited regex: a plan containing a regex that violates the configured regex safety limits MUST
  be rejected deterministically with `reason_code="unsupported_regex"` and an explanation beginning
  with `PA_BRIDGE_REGEX_POLICY_VIOLATION:`.
- Missing required scoping: a plan that is missing required `class_uid` scope MUST fail closed
  deterministically with `reason_code="backend_compile_error"` and an explanation beginning with
  `PA_BRIDGE_MISSING_SCOPE:` (treat as a compiler/validator bug)

### Sigma rule unit tests

Rule-level unit tests treat "expected matches" as executable assertions and are intended to run in
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

Execution adapter conformance suite (verification hook):

- Each execution adapter MUST have a fixture pack under `tests/fixtures/runner/<adapter_id>/`.
  - v0.1 baseline: `tests/fixtures/runner/atomic/` is required.
- A shared harness MUST execute the fixture pack(s) and assert:
  - required runner evidence header fields exist on all contract-backed JSON artifacts under
    `runner/` (`contract_version`, `run_id`, `action_id`, `action_key`, `generated_at_utc`)
  - deterministic ordering invariants declared by the owning specs (for example cleanup verification
    ordering in the Atomic executor integration spec)
  - stable `reason_domain`/`reason_code` mapping for common failures, using negative fixtures (for
    example `unsupported_executor`, `prereq_check_error`, `execution_failed` for Atomic)
- The harness MUST also validate contract compliance for all required artifacts in each fixture run
  (contract registry binding).
- See `033_execution_adapters.md` for the shared conformance requirements.

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

  - Input:
    - `runner.dependencies.allow_runtime_self_update=false` (explicit).
  - Simulate an attempt by the runner (or any invoked component, including noise engines) to
    self-update or mutate runtime dependencies during a run.
  - Assert deterministic enforcement handling:
    - The run MUST record a stable reason code for the block: `disallowed_runtime_self_update`.
  - Assert counters:
    - `runner_dependency_mutation_blocked_total == 1`

- `disallowed_runtime_self_update_config_rejected`

  - Input:
    - `runner.dependencies.allow_runtime_self_update=true`.
  - Assert deterministic config validation failure:
    - The run MUST fail closed before any action `prepare` begins.
    - The run MUST record a stable stage outcome reason code: `disallowed_runtime_self_update`.

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
deterministic marker computation, deterministic marker_token derivation, and attempted emission
bookkeeping.

The fixture set MUST include at least:

- `marker_emitted`:
  - Input: runner config enables synthetic correlation marker emission.
  - Expected:
    - Ground truth includes both:
      - `extensions.synthetic_correlation_marker`, and
      - `extensions.synthetic_correlation_marker_token`, for the action where `execute` is
        attempted.
    - The side-effect ledger includes an `execute`-phase entry describing the marker emission
      attempt (success or failure), consistent with runner contracts.
    - The marker values conform to the v1 formats defined in data contracts, and
      `extensions.synthetic_correlation_marker_token` MUST equal the deterministic derivation from
      `extensions.synthetic_correlation_marker`.

Deterministic token test vector (required):

- For `marker_canonical = "pa:synth:v1:00000000-0000-0000-0000-000000000000:s1:execute"`, the
  expected `marker_token` MUST equal `-rqyVmMhNi0Dq9suJO8hb8` (N=22; base64url(SHA-256) prefix).

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

#### Criteria authoring compiler

Fixture root (normative): `tests/fixtures/criteria/authoring_compile/`

The fixture suite MUST validate the deterministic compiler defined in `035_validation_criteria.md`
("Authoring format and deterministic compilation"):

- Input: `criteria_authoring.csv` or `criteria_authoring.yaml`
- Authoritative output: `criteria.jsonl`
- Diagnostic output: `authoring_compile_report.json`

Minimum required fixture cases (normative):

- `criteria_authoring_compile_smoke`
  - Includes at least one example row for each authoring operator (`equals`, `contains`, `regex`,
    and one numeric compare operator).
  - Includes at least one `ARG` row (argument environment + placeholder substitution).
  - Includes at least one `FYI` row (ignored for compilation).
  - Includes at least one skipped row using the `!!!` marker with a non-empty skip reason.
  - Asserts byte-identical outputs for:
    - compiled `criteria.jsonl` (including canonical ordering), and
    - `authoring_compile_report.json` (canonical JSON), including `stable_signal_id` values.

#### Criteria pack linter

Fixture root (normative): `tests/fixtures/criteria/lint/`

The fixture suite MUST validate the `criteria-pack` lint target kind described in `125_linting.md`.

Minimum required fixture cases (normative):

- `criteria_pack_lint_smoke`
  - `missing_required_columns_rejected`:
    - `criteria_authoring.csv` omits at least one required column for the row model.
    - Expected: lint fails closed with rule_id `lint-criteria-pack-missing-required-columns`.
  - `ambiguous_operator_rejected`:
    - An authoring row uses an unknown operator token OR applies a numeric operator to a non-numeric
      value OR uses a non-RE2-parseable regex.
    - Expected: lint fails closed with rule_id `lint-criteria-pack-ambiguous-operator`.
  - `canonical_ordering_enforced`:
    - `criteria.jsonl` violates canonical ordering requirements (file ordering and/or
      `expected_signals[]` ordering and/or `predicate.constraints[]` ordering).
    - Expected: lint fails closed with rule_id `lint-criteria-pack-canonical-ordering` and includes
      a stable remediation hint (minimum: the expected sort key).

### Reporting and scoring (defense outcomes + attribution)

Reporting derives per-action defense outcomes. For v0.1, defense outcome derivation depends on
deterministic attribution of detection hits to executed actions (`pa.attribution.v1`) and the
associated `match_quality` token defined in `070_scoring_metrics.md`.

#### Defense outcomes derivation

Fixture root (normative): `tests/fixtures/reporting/defense_outcomes/`

The fixture suite MUST lock `pa.attribution.v1` join precedence and tie-break behavior, and MUST
lock `match_quality` semantics.

Minimum required fixture cases (normative):

- `attribution_marker_only_exact`

  - Setup: A ground-truth executed action includes `extensions.synthetic_correlation_marker`, and at
    least one matched normalized event includes the same marker in
    `metadata.extensions.purple_axiom.synthetic_correlation_marker`.
  - Expected:
    - the hit is attributed to that action, and
    - `match_quality = "exact"`.

- `attribution_marker_token_only_exact`

  - Setup: A ground-truth executed action includes `extensions.synthetic_correlation_marker_token`,
    and at least one matched normalized event includes the same token in
    `metadata.extensions.purple_axiom.synthetic_correlation_marker_token` (with the canonical marker
    absent on the matched event).
  - Expected:
    - the hit is attributed to that action, and
    - `match_quality = "exact"`.

- `attribution_criteria_window_partial`

  - Setup: Marker evidence is absent. `criteria/results.jsonl` contains a `time_window` for an
    executed action, and the detection `first_seen_utc` falls within the inclusive interval.
  - Expected:
    - the hit is attributed to that action, and
    - `match_quality = "partial"`.

- `attribution_pivot_fallback_weak_signal`

  - Setup: Neither marker nor criteria-window evidence is available, but the detection
    `first_seen_utc` is within the pivot fallback window around `ground_truth.action.timestamp_utc`
    as defined by `pa.attribution.v1`.
  - Expected:
    - the hit is attributed to that action, and
    - `match_quality = "weak_signal"`.

- `attribution_tie_break_deterministic`

  - Setup: Two or more candidate actions match within the same precedence tier (for example,
    overlapping criteria windows or overlapping pivot fallback windows) for the same `technique_id`.
  - Expected:
    - A single `primary_action_id` is selected deterministically by the `pa.attribution.v1` total
      ordering.
    - If an implementation emits `attributed_action_ids[]` for debugging, it MUST be ordered by the
      same ordering with `primary_action_id` first.

Fixture structure (normative):

- Each fixture case MUST include `inputs/` sufficient to run the scoring+reporting attribution logic
  (minimum: `ground_truth.jsonl`, `detections/detections.jsonl`, and the normalized event envelope
  when testing marker join; `criteria/results.jsonl` is REQUIRED for criteria-window cases).
- Each fixture case MUST include an expected attribution assertion map under `expected/` (format MAY
  be JSON or YAML) that maps each detection hit to:
  - the expected `primary_action_id`, and
  - the expected `match_quality` token.

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
  - `bridge_ir_hash` (backend-neutral; required when `backend.plan_kind="pa_eval_v1"`):
    - For each executable compiled plan, SHA256 of canonical JSON (JCS) for `backend.plan` only.
    - The harness MUST also record an aggregate hash computed by sorting `(rule_id, bridge_ir_hash)`
      by `rule_id` and hashing the resulting canonical JSON array.
  - `semantic_detections_hash` (backend-neutral):
    - SHA256 of canonical JSON (JCS) for the ordered contents of a backend-neutral projection of
      `detections/detections.jsonl` (see "Cross-backend conformance").

#### Cross-backend conformance (verification hook)

When Run CI is configured to qualify more than one batch backend that claims `pa_eval_v1` support,
the harness MUST execute a backend matrix over the same BDP fixture and ruleset and verify semantic
equivalence.

Matrix inputs (normative):

- `backends[]`: ordered list of backend ids to test.
  - The list MUST be sorted lexicographically (bytewise UTF-8) to ensure deterministic report
    ordering.
- `fixture`: the same pinned Baseline Detection Package (BDP) version for all backends.
- `ruleset`: the same pinned evaluator conformance rule set for all backends.

Equivalence rules (normative):

- IR equivalence: for each rule that is `executable=true` across the matrix, the `bridge_ir_hash`
  MUST be identical across backends.
- Result equivalence: for those rules, the `semantic_detections_hash` MUST be identical across
  backends.

Backend-neutral projection for `semantic_detections_hash` (normative):

To avoid false mismatches due to backend provenance, the harness MUST compute semantic equivalence
over a projection that excludes backend-specific fields.

For each JSONL row in `detections/detections.jsonl`, construct an object with only:

- `rule_id`
- `first_seen_utc`
- `last_seen_utc`
- `matched_event_ids`
- `technique_ids` (if present)

The projection MUST exclude `run_id`, `scenario_id`, and all `extensions.*` fields.

The harness MUST then:

1. Canonicalize each projected object with RFC 8785 (JCS).
1. Sort rows deterministically by the stable key tuple:
   - `rule_id`, then
   - `first_seen_utc`, then
   - `last_seen_utc`, then
   - `matched_event_ids` (lexicographic compare of the already-sorted array)
1. Join the canonicalized rows with `\n` and a trailing `\n`.
1. Compute SHA-256 over the resulting bytes.

Non-executable handling (normative):

- If a rule is `executable=false` for any backend in the matrix, the harness MUST record this as a
  cross-backend conformance failure unless the rule is explicitly excluded from the matrix rule set.

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
- `cross_backend_ir_mismatch` (backend matrix mode only)
- `cross_backend_result_mismatch` (backend matrix mode only)
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

Schema validation of operator control-plane artifacts (v0.2+) validates contract-backed operator
intent artifacts when present.

- Fixture run bundles that include any `control/*.json` or `inputs/plan_draft.yaml` MUST validate
  against the new contracts via the contract validator (fail closed on mismatch).

The fixture set MUST include at least:

- `range_config_gap_taxonomy_invalid_token_rejected` (fail closed)
  - Provide a `inputs/range.yaml` fixture that includes a non-canonical `scoring.gap_taxonomy[]`
    token.
  - Assert schema validation fails closed.
  - Assert the failure output identifies the invalid token location deterministically (for example,
    a JSON pointer or dotted path to the array element).
- `range_config_noise_profile_missing_pin_rejected` (fail closed):
  - Feed `inputs/range.yaml` with `runner.environment_config.noise_profile.enabled=true` but omit
    `profile_sha256` (or `profile_id` / `profile_version`).
  - Expected: config validation fails closed with `reason_code=config_schema_invalid`.
- `control_plane_cancel_valid` (v0.2+)
  - Fixture root: `tests/fixtures/orchestrator/control_plane/cancel_valid/`
  - Provide a minimal run bundle that includes a valid `control/cancel.json`.
  - Assert contract validation succeeds for the operator control-plane artifacts present.
- `control_plane_cancel_invalid_rejected` (v0.2+; fail closed)
  - Fixture root: `tests/fixtures/orchestrator/control_plane/cancel_invalid_rejected/`
  - Provide a run bundle that includes a schema-invalid `control/cancel.json`.
  - Assert contract validation fails closed.
  - Assert the failure output identifies the invalid location deterministically (for example, JSON
    pointer or dotted path).
- `control_plane_resume_request_decision_valid` (v0.2+)
  - Fixture root: `tests/fixtures/orchestrator/control_plane/resume_request_decision_valid/`
  - Provide a run bundle that includes:
    - `control/resume_request.json`, and
    - `control/operator_decisions.json` (with a decision for the request).
  - Assert all present operator control-plane artifacts validate successfully.
- `control_plane_retry_request_decision_valid` (v0.2+)
  - Fixture root: `tests/fixtures/orchestrator/control_plane/retry_request_decision_valid/`
  - Provide a run bundle that includes:
    - `control/retry_request.json`, and
    - `control/operator_decisions.json` (with a decision for the request).
  - Assert all present operator control-plane artifacts validate successfully.
- `plan_draft_valid` (v0.2+)
  - Fixture root: `tests/fixtures/orchestrator/plan_draft/valid/`
  - Provide a run bundle that includes a valid `inputs/plan_draft.yaml`.
  - Assert contract validation succeeds for the plan draft artifact.
- `plan_draft_invalid_rejected` (v0.2+; fail closed)
  - Fixture root: `tests/fixtures/orchestrator/plan_draft/invalid_rejected/`
  - Provide a run bundle that includes an invalid `inputs/plan_draft.yaml` (syntactically invalid OR
    schema-invalid).
  - Assert contract validation fails closed and emits a deterministic error location.

### Content governance: golden datasets (fail-closed)

Golden datasets are a governed corpus: the "golden" designation MUST NOT be granted unless required
governance artifacts are present and valid (see `085_golden_datasets.md`).

CI requirements (normative):

- Content CI MUST validate the golden dataset governance artifacts as a fail-closed gate.
- If any dataset is designated "golden" (via the catalog mechanism defined in
  `085_golden_datasets.md`) and any required governance artifact is missing or schema-invalid, CI
  MUST fail.

Minimum checks (normative; repository layout is defined by `085_golden_datasets.md`):

- Golden dataset catalog exists at `golden_datasets/catalog.json` and validates against its contract
  (`docs/contracts/golden_dataset_catalog.schema.json`).
- For each catalog entry designated "golden" (`dataset_id = X`):
  - `golden_datasets/cards/X.json` MUST exist and validate against its contract
    (`docs/contracts/golden_dataset_card.schema.json`).
  - `golden_datasets/approvals/X.json` MUST exist and validate against its contract
    (`docs/contracts/golden_dataset_approvals.schema.json`).
- Catalog → card → approvals joins MUST be deterministic (stable key: `dataset_id`).

Conformance fixtures (normative):

- Fixture root: `tests/fixtures/golden_datasets/governance/`
- Minimum fixture cases:
  - `valid_minimal_golden`: minimal conforming golden dataset designation passes.
  - `missing_required_artifact_fails`: missing catalog/card/approvals fails closed with a stable
    error code that identifies the missing artifact class.

### Dataset exports: dataset release artifacts (workspace-root contract validation)

Dataset release artifacts are workspace-root exports (not run-relative). CI MUST validate the
contract-backed dataset JSON artifacts using the workspace contract registry
(`docs/contracts/workspace_contract_registry.json`), reusing `validation_mode` dispatch:

- `json_document`:
  - `exports/datasets/<dataset_id>/<dataset_version>/dataset_manifest.json`
  - `exports/datasets/<dataset_id>/<dataset_version>/splits/split_config.json`
- `jsonl_lines`:
  - `exports/datasets/<dataset_id>/<dataset_version>/splits/split_assignments.jsonl`

CI MUST fail closed on any schema validation failure (do not "best-effort" validate).

In addition to JSON Schema validation, CI MUST fail closed on dataset release invariants required by
`085_golden_datasets.md`, even when the dataset release JSON artifacts are schema-valid. At minimum,
CI MUST enforce:

- Any field name ending in `_sha256` MUST match `^sha256:[0-9a-f]{64}$`.
- `dataset_manifest.json.views_glob_version` MUST equal `"glob_v1"`. All view patterns
  (`views[].includes[]`, `views[].excludes[]`) MUST parse under `glob_v1` and MUST pass
  dataset-relative path safety checks (no leading `/`, no `..`, no `//`, no `\`).
- Feature variant disambiguation MUST be enforced:
  - `dataset_manifest.json.dataset_version` MUST encode the selected feature variant using SemVer
    build metadata as specified by `085_golden_datasets.md`:
    - `build.features_variant = "marker_assisted"` -> `dataset_version` ends with `+marker-assisted`
    - `build.features_variant = "marker_blind"` -> `dataset_version` ends with `+marker-blind`
  - `dataset_version` MUST match the on-disk `<dataset_version>/` directory name byte-for-byte.
- Deterministic ordering and set semantics MUST be enforced:
  - `inputs.runs[]` sorted by `run_id` (bytewise UTF-8),
  - `views[]` sorted by `view_id`,
  - `views[].includes[]` and `views[].excludes[]` sorted and de-duplicated (bytewise UTF-8),
  - `splits/split_assignments.jsonl` lines sorted by `run_id` (bytewise UTF-8).
- Event identity tier invariants for `raw_ref`:
  - Identity Tier 1 and Tier 2 events: `metadata.extensions.purple_axiom.raw_ref` MUST be non-null.
  - Identity Tier 3 events: `metadata.extensions.purple_axiom.raw_ref` MUST be null.
- When `views/labels/` includes detection-derived labels keyed by `metadata.event_id`, the dataset
  release MUST include the deterministic event join bridge required by `085_golden_datasets.md`, and
  CI MUST validate its presence and determinism.
- Provenance-only descriptive context boundary: prohibited descriptive artifacts MUST NOT appear
  under `views/features/` or `views/labels/`.

Conformance fixtures (normative):

- Fixture root: `tests/fixtures/golden_datasets/releases/`
- Minimum fixture cases:
  - `dataset_release_smoke_valid`: build or provide a minimal dataset release directory and assert
    workspace validation succeeds for the three required artifacts.
  - `dataset_release_schema_invalid_fails`: provide a dataset release with at least one
    schema-invalid artifact (document or JSONL line) and assert the workspace validator fails closed
    with a deterministic error location.
  - `dataset_release_join_bridge_valid`: provide a dataset release that includes detection outputs
    under `views/labels/` and the join bridge under
    `views/labels/runs/<run_id>/joins/event_id_raw_ref_bridge/`. Assert:
    - bridge is present for each included run,
    - bridge rows are deterministically ordered (stable sort),
    - joins are possible from `matched_event_ids[]` to raw_ref-first feature events.
  - `dataset_release_join_bridge_missing_fails`: provide a dataset release that includes detections
    under `views/labels/` but omits the join bridge. Assert CI fails closed with a stable error that
    identifies the missing bridge class.
  - `dataset_release_raw_ref_tier_violation_fails`: provide a dataset release whose feature events
    violate raw_ref tier invariants (Tier 1/2 raw_ref null or Tier 3 raw_ref non-null). Assert CI
    fails closed with a stable error classification.
  - `dataset_release_leakage_boundary_fails`: provide a dataset release that places provenance-only
    descriptive context under `views/features/` or `views/labels/` (for example, a report narrative
    file or scenario description material). Assert CI fails closed with a stable error that
    identifies a leakage boundary violation.

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

When `runner.environment_config.noise_profile` enables a specific engine, the run MUST satisfy
`SUPPORTED_VERSIONS` pins for that engine (and the UI MUST satisfy pins for any bundled playback
assets), otherwise version conformance fails.

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

### Detection performance budget gates

Run CI MUST include fixtures that exercise the deterministic detection performance budget gate
(`detection.performance_budgets`) defined in `110_operability.md`.

Required fixtures:

- **Pass fixture**: budgets configured to comfortably exceed the fixture's cost; expected:

  - `detection.performance_budgets` stage outcome `success`
  - `manifest.status == "success"` (assuming no other warnings)

- **Fail fixture (deterministic)**: budgets configured to be intentionally too small (for example,
  `max_predicate_ast_nodes_total: 0` and/or `max_eval_cost_units_total: 0`); expected:

  - `detection.performance_budgets` stage outcome `failed` with
    `reason_code="detection_budget_exceeded"` and `fail_mode="warn_and_skip"`
  - `manifest.status == "partial"`
  - `logs/counters.json` includes the required `detection_sigma_*` budget metrics and non-zero
    `detection_sigma_budget_violation_total`

The fixtures MUST validate the gate using `logs/counters.json` as the source of truth for metrics.
Wall-clock timers MUST NOT be used for gating in CI.

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
- `offline_content_bundle_validation_with_contracts_bundle`: Provide a valid detection content
  bundle fixture and a matching contracts bundle fixture (directory or tarball) and assert that
  content bundle offline validation succeeds with (a) network access disabled and (b) no repository
  checkout available (only the two bundles on disk).
  - The fixture MUST exercise, at minimum:
    - `detection_content_bundle_manifest.json` schema validation via the resolved contracts bundle
    - `security/checksums.txt` format validation and per-file SHA-256 recomputation
    - Ed25519 signature verification when signature artifacts are present
- `offline_run_validation_with_content_bundle_and_contracts_bundle`: Provide a valid run bundle
  fixture, a matching detection content bundle fixture, and a matching contracts bundle fixture and
  assert that run + content provenance validation succeeds with (a) network access disabled and (b)
  no repository checkout available (only the three bundles on disk).
  - The fixture MUST exercise, at minimum:
    - Version pin compatibility between `runs/<run_id>/manifest.json` and
      `detection_content_bundle_manifest.json` (ruleset, mapping pack, and criteria pack when
      pinned)
    - Bridge compatibility via `bridge/mapping_pack_snapshot.json.mapping_pack_sha256`
    - Per-rule provenance: the run’s `bridge/compiled_plans/<rule_id>.plan.json.rule_sha256` must
      match the recomputed canonical rule hash of the corresponding ruleset file inside the content
      bundle
  - The fixture suite MUST include at least one negative (fail-closed) case (for example a
    mismatched `mapping_pack_sha256` or missing referenced `rules/<rule_id>.yaml`).
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

Thresholds artifact conformance (contract + deterministic ordering) (normative):

- The artifact validation fixture suite MUST include conformance coverage for
  `report/thresholds.json` as a contract-backed output (see `080_reporting.md`).
- Fixture root: `tests/fixtures/reporting/thresholds/`
- Minimum fixture case(s):
  - `thresholds_contract_and_ordering`:
    - Provide a minimal run bundle where reporting emits `report/thresholds.json`.
    - Assert `report/thresholds.json` validates against the `thresholds.schema` contract.
    - Assert `gates[]` is deterministically ordered by `gate_id` ascending (UTF-8 byte order) and
      contains unique `gate_id` values.

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

### Controlled noise profile conformance

Controlled benign noise is a first-class test variable used to detect false positive regressions.
When enabled, it MUST be pinned and observable in provenance (see
`runner.environment_config.noise_profile` in `120_config_reference.md` and
`manifest.extensions.runner.environment_noise_profile` in `025_data_contracts.md`).

The fixture set MUST include at least:

- `noise_profile_provenance_pinned` (fail closed):

  - Input: `inputs/range.yaml` enables `runner.environment_config.noise_profile` with explicit
    `profile_id`, `profile_version`, `profile_sha256`, and `seed`.
  - Expected:
    - `manifest.extensions.runner.environment_noise_profile` exists and matches the effective
      config.
    - The profile pin is stable across repeated runs with identical inputs (no timestamps, stable
      ordering).

- `noise_profile_snapshot_exists_and_hash_matches` (fail closed; contract-backed):

  - Input: a noise-enabled run (`runner.environment_config.noise_profile` set) with an explicit
    `profile_id`, `profile_version`, `profile_sha256`, and `seed`.
  - Expected:
    - `inputs/environment_noise_profile.json` exists in the run bundle (run-relative path).
    - The snapshot validates against the `environment_noise_profile` contract.
    - The SHA-256 of the canonical snapshot bytes equals
      `manifest.extensions.runner.environment_noise_profile.profile_sha256`.

- `noise_profile_snapshot_deterministic_bytes` (determinism hook):

  - Input: repeat the same scenario suite twice with identical seeds and pinned versions.
  - Expected:
    - `inputs/environment_noise_profile.json` is byte-identical across runs.

- `noise_profile_canonicalization_crlf_lf_equivalence` (canonicalization vector):

  - Input: two noise profiles with identical semantic content but different line endings (LF vs
    CRLF).
  - Expected:
    - computed `profile_sha256` is identical, and the emitted snapshot bytes are identical.

- `noise_profile_toggle_event_id_stability` (determinism hook; recommended):

  - Input: execute the same scenario suite twice with identical seeds and pinned versions:
    1. noise profile disabled, 2) noise profile enabled.
  - Expected:
    - For all normalized events that carry
      `metadata.extensions.purple_axiom.synthetic_correlation_marker` and/or
      `metadata.extensions.purple_axiom.synthetic_correlation_marker_token` values observed in
      ground truth for executed actions, the multiset of `metadata.event_id` values MUST be
      identical between the two runs.
    - Noise-profile metadata fields (when present) MUST NOT participate in `metadata.event_id`
      computation.

- `noise_profile_false_positive_budget` (CI gate; configurable):

  - Input: a noise-enabled run with detections enabled.
  - Expected:
    - Scoring emits `false_positive_detection_count` and `false_positive_detection_rate` in the
      comparable metrics surface.
    - If `scoring.thresholds.max_false_positive_detection_rate` and/or
      `scoring.thresholds.max_false_positive_detection_count` is configured, the run MUST be marked
      `partial` when the budget is exceeded.

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

These thresholds are defined in `080_reporting.md` ("Regression deltas") and MAY be overridden via
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
    baseline incompatible (including `manifest.extensions.runner.environment_noise_profile.*`
    mismatch).

When adding a new stateful lifecycle that needs deterministic conformance, document the state
machine using the ADR-0007 template and add fixture-driven conformance tests here.

- Operator control-plane lifecycle (v0.2+):
  - Authority: `115_operator_interface.md` cancel/resume/retry semantics + ADR-0007 state
    machine(s).
  - Conformance fixtures: `tests/fixtures/orchestrator/control_plane/` (cancel/resume/retry request
    \+ decision cases).

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
