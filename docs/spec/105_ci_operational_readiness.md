---
title: CI and Operational Readiness
description: Stitches existing v0.1 CI gates, publish gates, and health signals into a single normative CI pipeline contract.
status: draft
category: spec
tags: [ci, devops, secdevops, sre, operability, gates]
related:
  - 000_charter.md
  - 025_data_contracts.md
  - 026_contract_spine.md
  - 070_scoring_metrics.md
  - 080_reporting.md
  - 090_security_safety.md
  - 100_test_strategy_ci.md
  - 110_operability.md
  - 120_config_reference.md
  - ADR-0001-project-naming-and-versioning.md
  - ADR-0003-redaction-policy.md
  - ADR-0004-deployment-architecture-and-inter-component-communication.md
  - ADR-0005-stage-outcomes-and-failure-classification.md
  - ADR-0007-state-machines.md
---

# CI + Operational Readiness

## Overview

This document defines the normative CI pipeline contract for Purple Axiom v0.1 implementations by
stitching together already-specified gates and evidence surfaces into a single, deterministic CI
verdict model.

This spec consolidates and operationalizes the existing requirements across:

- CI gates (100_test_strategy_ci.md)
- Publish-gate and artifact contracts (025_data_contracts.md)
- Run health and operational safeguards (110_operability.md)
- CI-facing reporting and exit code semantics (080_reporting.md)
- Failure classification (ADR-0005)
- Lifecycle state machines (ADR-0007)

## Scope

In-scope (v0.1):

- A deterministic CI verdict derived from contracted artifacts and existing exit-code semantics.
- A single "pipeline contract" view of the already-required CI gates.
- Explicit mapping from gates to evidence surfaces (schemas, reports, health files, and thresholds).
- A two-lane CI workflow (Content CI and Run CI) and the required CI entrypoints to run them.

Out-of-scope:

- Mandating a specific CI vendor or workflow engine.

## Normative sources

This spec primarily consolidates and operationalizes requirements already present in v0.1 documents
listed in the frontmatter.

In addition, this spec defines **CI lane structure** (Content CI vs Run CI) and the minimum CI
harness entrypoints required to exercise those lanes. These CI lane requirements are CI-only: they
MUST NOT change run bundle formats, stage boundaries, or contract schemas beyond what is already
defined elsewhere.

If a conflict is discovered between sources, the implementation MUST follow the more specific
contract document for the artifact in question (e.g., data contracts for run bundle paths) and MUST
raise an issue to reconcile the discrepancy.

## Definitions

- Run bundle: The contracted run directory rooted at `runs/<run_id>/`.
- Gate: A pass/fail rule evaluated by CI over contracted artifacts and v0.1 exit-code semantics.
- Content CI: A fast CI lane that validates content-like artifacts (rule sets, mapping packs,
  criteria packs, etc.) and their compilation outputs without requiring a lab provider.
- Run CI: A slower CI lane that executes integration checks by producing run bundles and/or
  evaluating detections against a pinned Baseline Detection Package (BDP).
- Content-like artifact: A repository input that can be validated deterministically without
  executing a scenario in a lab (for example Sigma rules, mapping packs, criteria packs, detection
  content bundles, and BDPs).
- Fail-closed gate: A gate where any failure MUST yield a `failed` run status.
- Threshold gate: A gate where violations degrade the run status to `partial` (or `failed` when the
  underlying contract requires hard failure) while keeping the run mechanically reportable.
- Run status: The canonical `(success | partial | failed)` value recorded in the run manifest file
  `runs/<run_id>/manifest.json` as `manifest.status` (derived from stage outcomes per ADR-0005).
- `Status recommendation`: The CI-facing status computed by the reporting stage; recorded in
  `runs/<run_id>/report/thresholds.json.status_recommendation` (authoritative) and mirrored in
  `runs/<run_id>/report/report.json.status` for reportable runs.
- Pipeline contract violation: A CI-detected nonconformance to required artifact presence, schema
  validity, or cross-artifact coupling (including unexpected exit codes). Pipeline contract
  violations are fail-closed and MUST force the CI verdict to `failed` (CI exit code `20`) even when
  other status signals indicate `success` or `partial`.
- CI verdict: The CI job’s final recommendation `(success | partial | failed)` plus an exit-code
  mapping `(0|10|20)` for the CI job step that enforces this contract.
- Reportable: A run with mechanically usable artifacts and the required reporting outputs for its
  enabled feature set (see reporting "required artifacts / required reporting outputs" and data
  contracts publish-gate requirements).

### Path notation (normative)

This document uses two equivalent notations for run-bundle paths:

- Run-bundle rooted: `runs/<run_id>/<path>`
- Run-relative: `<path>`

Translation rule (normative): when this document shows `runs/<run_id>/X`, the corresponding
run-relative path is `X`. Contract schemas, `artifact_path` fields, and
`evidence_refs[].artifact_path` values MUST use the run-relative form unless a field explicitly
states otherwise.

## CI lanes

Purple Axiom v0.1 CI MUST provide two explicit lanes:

- **Content CI** (fast, no lab required)
- **Run CI** (slow, integration)

This separation keeps feedback fast for content changes while preserving an integration signal for
the full pipeline.

### Content CI (fast, no lab required)

Content CI validates content-like artifacts and compilation outputs without invoking a lab provider.

Content CI MUST validate, at minimum:

1. `content.lint` gate: Contract Spine conformance (contract registry invariants, canonical
   serialization, publisher/reader conformance) plus repo-local lint rules (see
   `026_contract_spine.md` and `125_linting.md`).
   - Ordering (normative): `content.lint` MUST run before any other enforced Content CI gate.
1. Sigma ruleset determinism + uniqueness + required metadata (see `060_detection_sigma.md`).
1. Mapping pack resolution, router determinism, and mapping pack schema validation (see
   `065_sigma_to_ocsf_bridge.md`).
1. Sigma compilation to `bridge_compiled_plan` artifacts for the selected backend (see
   `065_sigma_to_ocsf_bridge.md`).
1. Compiled plan semantic validation (see `065_sigma_to_ocsf_bridge.md`, "Compiled plan semantic
   validation policy").
1. Detection Content Release (detection content bundle) build + offline validation (see
   `025_data_contracts.md`, "Detection content bundle distribution and validation").
1. Fixture registry + negative baseline allowlist validation + canonicalization (YAML → canonical
   JSON) (see `086_detection_baseline_library.md`, "Fixture registry and allowlisting (v0.1 CI)").
1. Contract/schema validation for any content-like artifacts under test (examples: criteria packs,
   detection content bundle manifests, BDP manifests).
1. Static semantic checks (P0.2 and P0.3) (see `100_test_strategy_ci.md`, "Static semantic checks").
1. Rule-level unit tests when fixtures are present (see `100_test_strategy_ci.md`, "Sigma rule unit
   tests").

#### Content CI wiring contract (v0.1)

This section is the **authoritative wiring contract** for Content CI gate execution order, required
gate IDs, and required findings artifacts. It is tool-agnostic (GitHub Actions, Buildkite, etc.).

Entrypoint (normative):

- Content CI MUST be invokable via the `ci-content` entrypoint (see `100_test_strategy_ci.md`,
  "Content CI harness fixture suite (normative)").

Required gate order (normative):

1. `content.lint`
1. `content.sigma.semantic`
1. `content.fixtures.validate`
1. `content.bundle.integrity`

Findings artifacts (normative):

- For every REQUIRED gate above, Content CI MUST emit exactly one findings artifact at:
  - `artifacts/findings/<gate_id>.findings.v1.json` (contract: `ci_gate_findings`)
- Missing or schema-invalid findings artifacts for any REQUIRED gate MUST fail Content CI (fail
  closed). (See also: "CI gate findings artifacts (required)".)

Workspace artifact publication rules (normative):

- Any contract-backed workspace artifact written under `artifacts/**` (including
  `artifacts/findings/**` and `artifacts/fixtures/**`) MUST be published using crash-safe atomic
  file replace semantics (write-to-temp in the same parent directory + atomic rename).
- Producers MUST validate contract-backed workspace artifacts against the workspace contract
  registry (`docs/contracts/workspace_contract_registry.json`) before the final rename.
- Producers SHOULD use `pa.publisher.workspace.v1` to implement these semantics consistently (see
  `025_data_contracts.md`).

Optional failure observability (normative; conditional):

- If a gate fails because it cannot emit a schema-valid findings artifact for its target path, it
  MUST also emit the workspace contract validation report for that target findings path at:
  - `logs/contract_validation/artifacts/findings/<gate_id>.findings.v1.json.contract_validation.json`.

Failure semantics (normative):

- `ci-content` MUST attempt to execute all REQUIRED gates in order and MUST emit findings artifacts
  for each gate before exiting.
- The overall Content CI exit code MUST be `0` when all REQUIRED gates succeed and `20` when any
  REQUIRED gate fails.

CI manifest binding (non-normative; recommended):

- Job name: `ci-content`
- Step names: use the gate ID as the step name (for example, step `content.lint` executes the
  `content.lint` gate).

#### `content.lint` gate (Contract Spine conformance + repo-local linting)

Gate ID (v0.1): `content.lint`

Purpose (normative):

- Execute all repo-local, deterministic checks that MUST run **before** other Content CI gates,
  including:
  - Contract Spine conformance checks (see `026_contract_spine.md`, "Verification and CI
    conformance"), including `parser_module_inventory_sync` (parser module inventory completeness).
  - Lint rule packs and lint report generation (see `125_linting.md`).
  - Contract registry linting (v0.1):
    - `docs/contracts/contract_registry.json` (target kind `contract-registry`), and
    - `docs/contracts/workspace_contract_registry.json` (target kind `workspace-contract-registry`).
    - This gate MUST fail closed when either registry violates the `pass_id` requirements
      introduced in `025_data_contracts.md` (grammar + `stage_owner` prefix) or when the run-bundle
      registry omits the required `logs/pass_manifest.json` binding.
      
Required outputs (workspace-root):

- `artifacts/findings/content.lint.findings.v1.json`

#### `content.fixtures.validate` gate (fixture registry canonicalization)

When fixture inputs are present, Content CI MUST execute a fixture validation and canonicalization
gate.

Inputs (v0.1; repo-local):

- `fixtures/fixture_registry.v1.yaml` (required when fixtures are used in CI)
- `fixtures/baseline_allowlist.v1.yaml` (optional)

Outputs (workspace-root; normative):

- `artifacts/fixtures/fixture_registry.v1.json` (contract-backed; canonical JSON)
- `artifacts/fixtures/baseline_allowlist.v1.json` (contract-backed; canonical JSON) when the YAML
  allowlist is present, otherwise the file MUST be omitted (treated as empty allowlist).
- `artifacts/findings/content.fixtures.validate.findings.v1.json`

Fail-closed policy (normative):

- YAML decode failures or schema validation failures MUST produce an `error` finding and MUST fail
  the gate.
- Missing fixture provenance or license metadata MUST produce an `error` finding and MUST fail the
  gate.
- Canonical JSON nondeterminism (byte mismatch across repeated canonicalization) MUST produce an
  `error` finding with `reason_code="fixture_registry_nondeterministic"` and MUST fail the gate.

#### `content.sigma.semantic` gate (Sigma semantic validators)

Gate ID (v0.1): `content.sigma.semantic`

Required outputs (workspace-root):

- `artifacts/findings/content.sigma.semantic.findings.v1.json`

Purpose (normative):

- Provide deterministic, offline Sigma rule semantic validation that catches authoring hazards early
  (before bridge compilation and Run CI execution).

Inputs (normative):

- The effective Sigma ruleset discovered from `detection.sigma.rule_paths[]` using the deterministic
  rule loading procedure defined in `060_detection_sigma.md` ("Deterministic rule loading
  requirements").

Minimum validator set (v0.1; normative):

1. Control characters (`rule_id="sigma.semantic.control_characters"`)

   - Severity: `error`
   - Emit when a Sigma YAML source file contains any disallowed ASCII control byte:
     - `0x00-0x08`, `0x0B`, `0x0C`, `0x0E-0x1F`, or `0x7F`
     - (Tab `0x09`, LF `0x0A`, and CR `0x0D` are permitted by this check.)
   - Emit exactly one finding per offending file.
   - Findings MUST use:
     - `category="semantic"`
     - `reason_domain="ci_gate_findings"`
     - `reason_code="control_characters"`
     - `subject.kind="sigma_rule_file"`
     - `subject.stable_id=<ruleset_path>` (as defined in `060_detection_sigma.md`)
     - `location.file_path=<ruleset_path>`

1. Invalid modifier combinations (`rule_id="sigma.semantic.invalid_modifier_combinations"`)

   - Severity: `error`
   - Applies to selector field-reference keys inside the Sigma `detection:` map (excluding
     `detection.condition`).
   - Define the modifier chain for a selector key `k` as:
     - `parts = split(k, "|")` (literal `|`, no escaping; preserves order)
     - `field_name = parts[0]`
     - `modifiers = parts[1..]` (may be empty)
   - Emit an error finding for any selector key where any of the following hold:
     - More than one "primary match modifier" is present in `modifiers`, where
       `primary_match_modifiers = {"contains","startswith","endswith","re"}`.
     - The modifier `all` is present and is not the last modifier.
     - Any modifier token is empty (`""`).
   - Emit exactly one finding per offending selector key per rule.
   - Findings MUST use:
     - `category="semantic"`
     - `reason_domain="ci_gate_findings"`
     - `reason_code="invalid_modifier_combinations"`
     - `subject.kind="sigma_rule"`
     - `subject.stable_id=<sigma_rule_id>` (Sigma `id`)
     - `location.file_path=<ruleset_path>` when available

1. Wildcards instead of modifiers (`rule_id="sigma.semantic.wildcards_instead_of_modifiers"`)

   - Severity: `warn`
   - Emit when a selector field-reference key has no explicit modifiers (does not contain `|`) but
     any associated scalar string value begins with `*` or ends with `*` (example: `*foo*`, `foo*`,
     `*foo`).
   - Emit at most one finding per selector key per rule (summarize multiple offending values in a
     deterministic way if desired).
   - Findings MUST use:
     - `category="semantic"`
     - `reason_domain="ci_gate_findings"`
     - `reason_code="wildcards_instead_of_modifiers"`
     - `subject.kind="sigma_rule"`
     - `subject.stable_id=<sigma_rule_id>` (Sigma `id`)
     - `location.file_path=<ruleset_path>` when available

Determinism requirements (normative):

- The gate MUST evaluate rule files in deterministic order:
  - ascending `ruleset_path` (Contract Spine bytewise UTF-8 lexical ordering).
- When iterating selector keys within a rule, keys MUST be processed in deterministic order:
  - ascending UTF-8 byte order of the exact key string.
- Emitted findings MUST satisfy the `ci_gate_findings` ordering and fingerprinting rules (see this
  document, "CI gate findings artifacts (required)").

Verification hooks (normative):

- Content CI fixtures MUST cover (at minimum) the three minimum validator cases declared in
  `100_test_strategy_ci.md` under `tests/fixtures/validators/sigma_semantic/`.

#### `content.bundle.integrity` gate (offline bundle validation)

Content CI MUST build at least one Detection Content Release (detection content bundle) and MUST
validate it offline.

Gate ID (v0.1): `content.bundle.integrity`

Required outputs:

- `artifacts/findings/content.bundle.integrity.findings.v1.json`

The findings artifact for this gate SHOULD use the integrity reason codes already defined by
`025_data_contracts.md` (for example: `checksums_parse_error`, `checksum_mismatch`,
`signature_invalid`) when reporting failures.

Verification hook (normative): Content CI MUST fail a pull request that breaks compilation or static
validation without spinning up a lab provider.

Content CI harness fixture suite (normative): CI MUST include an end-to-end fixture suite that
executes the `ci-content` entrypoint deterministically without a lab provider (see
`100_test_strategy_ci.md`, fixture root `tests/fixtures/ci/content_ci_harness/`).

### Run CI (slow, integration)

Run CI executes integration-level checks. A compliant CI pipeline MUST implement at least one of:

- **BDP replay**: evaluate detections against a pinned Baseline Detection Package (BDP) without
  running a lab provider.
- **Minimal lab run**: execute at least one scenario end-to-end on a minimal lab profile.

When BDP replay is used, Run CI MUST:

- Fetch a pinned `(baseline_id, baseline_version)` pair.
- Validate the BDP manifest and integrity material (checksums; signature when present).
- Run detection evaluation deterministically over the BDP normalized event store.
- Enforce configured detection performance budgets using deterministic metrics in
  `runs/<run_id>/logs/counters.json` and the `detection.performance_budgets` stage outcome (see
  `110_operability.md` and `ADR-0005-stage-outcomes-and-failure-classification.md`).
- Execute `run.goodlog` and `run.regression` fixture gates, failing closed on any expectation
  mismatch or any non-allowlisted match (see `086_detection_baseline_library.md`, "Fixture registry
  and allowlisting (v0.1 CI)").

#### `run.publish_gate` gate (publish-gate contract validation)

Objective: provide a single, canonical CI findings surface for publish-gate failures, including
contract validation errors emitted under `runs/<run_id>/logs/contract_validation/`.

Inputs (normative):

- `runs/<run_id>/manifest.json` and/or `runs/<run_id>/logs/health.json` (stage outcomes surface)
- Pass manifest:
  - `runs/<run_id>/logs/pass_manifest.json` (contract: `pass_manifest`)
- Any present contract validation reports:
  - `runs/<run_id>/logs/contract_validation/*.json` (contract: `contract_validation_report`)
- Contract registry for schema validation and pass attribution resolution:
  - `docs/contracts/contract_registry.json`

Behavior (normative):

1. The gate MUST emit exactly one findings artifact:

   - `artifacts/findings/run.publish_gate.findings.v1.json` (contract: `ci_gate_findings`)

1. Report presence and schema validity:

   - Each discovered `logs/contract_validation/*.json` report MUST be schema-validated against
     `contract_id="contract_validation_report"` using `docs/contracts/contract_registry.json`.
   - If any report is missing required fields or is schema-invalid, the gate MUST emit exactly one
     `fatal` finding per invalid report with:

     - `severity="fatal"`
     - `category="internal"`
     - `reason_domain="ci_gate_findings"`
     - `reason_code="publish_gate_report_invalid"`
     - `rule_id="publish_gate.contract_validation"`
     - `subject.kind="run_artifact"`
     - `subject.stable_id=<report_path>` (run-relative)
     - `location.file_path=<report_path>` (run-relative)
     - `message="Publish-gate contract validation report is schema-invalid or missing required fields"`
     - `evidence.details` MUST include:
       - `contract_validation_report_path` (run-relative; equals `<report_path>`)
       - `expected_contract_id="contract_validation_report"`
       - `expected_schema_version="pa:contract-validation-report:v1"`

1. Report requiredness cross-check:

   - If the stage outcome surface contains a failed stage whose `reason_code` indicates contract
     validation invalid (`contract_validation_failed` or a stage-scoped `*_invalid` code), CI MUST
     expect a corresponding report at `logs/contract_validation/<stage_id>.json`.
   - Any missing expected report MUST emit exactly one `error` finding per missing stage id with:

     - `severity="error"`
     - `category="internal"`
     - `reason_domain="ci_gate_findings"`
     - `reason_code="publish_gate_report_missing"`
     - `rule_id="publish_gate.contract_validation"`
     - `subject.kind="stage"`
     - `subject.stable_id=<stage_id>`
     - `location.file_path="logs/contract_validation/" + <stage_id> + ".json"`
     - `message="Publish-gate contract validation report missing for failed stage"`
     - `evidence.details` MUST include:
       - `contract_validation_stage_id` (string; equals `<stage_id>`)
       - `contract_validation_report_path` (run-relative;
         equals `"logs/contract_validation/" + <stage_id> + ".json"`)

1. Pass manifest presence and schema validity:

   - If `runs/<run_id>/manifest.json` is present (run bundle exists), the gate MUST require
     `runs/<run_id>/logs/pass_manifest.json` to be present.
     - On violation, emit an `error` finding with:
       - `reason_code="pass_manifest_missing"`
       - `rule_id="publish_gate.pass_manifest"`
       - `subject.kind="run_artifact"`
       - `subject.stable_id="logs/pass_manifest.json"`
       - `location.file_path="logs/pass_manifest.json"`

   - When present, `logs/pass_manifest.json` MUST be schema-validated against contract
     `pass_manifest`.
     - If schema-invalid, emit a `fatal` finding with:
       - `reason_code="pass_manifest_schema_invalid"`
       - `rule_id="publish_gate.pass_manifest"`
       - `subject.kind="run_artifact"`
       - `subject.stable_id="logs/pass_manifest.json"`
       - `location.file_path="logs/pass_manifest.json"`

1. Pass manifest consistency (normative):

   - `pass_manifest.run_id` MUST equal `manifest.run_id`.
     - On mismatch, emit an `error` finding with:
       - `reason_code="pass_manifest_run_id_mismatch"`
       - `rule_id="publish_gate.pass_manifest"`
       - `subject.kind="run_artifact"`
       - `subject.stable_id="logs/pass_manifest.json"`

   - The gate MUST validate that `pass_manifest.entries[]` is a complete and correct attribution
     index for contract-backed artifacts in the run bundle (see `026_contract_spine.md`,
     "Pass manifest", "Deterministic generation"):

     - For every contract-backed artifact present as a regular file in `runs/<run_id>/`
       (excluding `logs/pass_manifest.json`), `pass_manifest.entries[]` MUST contain exactly one
       entry with `artifact_path` equal to that run-relative path.
       - Missing entry MUST emit an `error` finding with:
         - `reason_code="pass_manifest_entry_missing"`
         - `rule_id="publish_gate.pass_manifest"`
         - `subject.kind="run_artifact"`
         - `subject.stable_id=<artifact_path>`

     - For every entry in `pass_manifest.entries[]`, the referenced `artifact_path` MUST exist as a
       regular file in the run bundle.
       - Orphan entry MUST emit an `error` finding with:
         - `reason_code="pass_manifest_entry_orphaned"`
         - `rule_id="publish_gate.pass_manifest"`
         - `subject.kind="run_artifact"`
         - `subject.stable_id=<artifact_path>`

     - For each entry, the tuple `(contract_id, stage_owner, pass_id, validation_mode when present)`
       MUST match the resolved binding metadata from `docs/contracts/contract_registry.json` using
       `glob_v1` rules.
       - On mismatch, emit an `error` finding with:
         - `reason_code="pass_manifest_binding_mismatch"`
         - `rule_id="publish_gate.pass_manifest"`
         - `subject.kind="run_artifact"`
         - `subject.stable_id=<artifact_path>`
         - `evidence.details.expected=<resolved_binding_subset>` (RECOMMENDED)
         - `evidence.details.observed=<manifest_entry_subset>` (RECOMMENDED)

     - `entries[]` MUST be sorted by `artifact_path` ascending.
       - On violation, emit an `error` finding with:
         - `reason_code="pass_manifest_ordering_invalid"`
         - `rule_id="publish_gate.pass_manifest"`
         - `subject.kind="run_artifact"`
         - `subject.stable_id="logs/pass_manifest.json"`

1. Findings mapping (preferred path):

   - For each schema-valid report that includes `diagnostics[]`, emit exactly one CI finding per
     diagnostic record.
   - Mapping MUST be lossless: the original diagnostic MUST be preserved under
     `finding.evidence.details.contract_validation_diagnostic` as a JSON object.

1. Findings mapping (fallback path):

   - If a schema-valid report omits `diagnostics[]`, CI MUST derive diagnostics deterministically
     from `artifacts[].errors[]` using the derivation algorithm in `025_data_contracts.md` ("Derived
     diagnostics surface"), and then map those derived diagnostics to CI findings.

1. For every mapped CI finding `g` (from either path above), producers MUST set:

   - `g.severity` and `g.category` copied from the diagnostic record

   - `g.reason_domain = "ci_gate_findings"`

   - `g.reason_code` (deterministic):

     - `"publish_gate_artifact_path_invalid"` when the diagnostic `reason_code` is
       `"timestamped_filename_disallowed"`
     - otherwise `"publish_gate_contract_invalid"`

   - `g.rule_id = "publish_gate.contract_validation"`

   - `g.subject` copied from the diagnostic record

   - `g.location` copied from the diagnostic record when present

   - `g.message` copied from the diagnostic record

   - `g.evidence.details` MUST include:

     - `contract_validation_report_path` (run-relative)
     - `contract_validation_stage_id` (string)
     - `contract_validation_diagnostic` (object; the diagnostic record)

Outputs (normative):

- `artifacts/findings/run.publish_gate.findings.v1.json`

#### `run.goodlog` gate (negative baseline)

Objective: detect false positives by asserting that benign fixtures produce zero non-allowlisted
matches.

Inputs (normative):

- `artifacts/fixtures/fixture_registry.v1.json`
- `artifacts/fixtures/baseline_allowlist.v1.json` (when present; otherwise treated as empty)
- A pinned backend profile / evaluator backend (implementation-defined)
- Fixture datasets referenced by the fixture registry

Behavior (normative):

- The gate MUST select fixtures with `purpose="benign"`.
- For each selected fixture, the gate MUST evaluate all enabled detections.
- Any emitted detection instance MUST be treated as a gate failure unless it matches an allowlist
  entry scoped to `(fixture_id, detection_id)` with a matching `match_fingerprint` (see
  `086_detection_baseline_library.md`).
- If zero benign fixtures are declared, the gate MUST fail closed with at least one `error` finding.

Outputs (normative):

- `artifacts/findings/run.goodlog.findings.v1.json`

#### `run.regression` gate (fixture expected outcomes)

Objective: assert that detections produce the expected results on malicious or mixed fixtures.

Inputs (normative):

- `artifacts/fixtures/fixture_registry.v1.json`
- A pinned backend profile / evaluator backend (implementation-defined)
- Fixture datasets referenced by the fixture registry

Behavior (normative):

- The gate MUST select fixtures with `purpose` of `malicious` or `mixed`.
- For each selected fixture, the gate MUST evaluate enabled detections and MUST verify every
  declared `expected_outcomes[]` entry for that fixture.
- Any failed assertion MUST emit an `error` finding and MUST fail the gate.
- If zero regression fixtures are declared, the gate MUST fail closed with at least one `error`
  finding.

Outputs (normative):

- `artifacts/findings/run.regression.findings.v1.json`

If Run CI is configured to qualify multiple batch evaluator backends (for example, `native_pcre2`
and a second backend that claims `pa_eval_v1` support), Run CI MUST also execute the evaluator
conformance harness in cross-backend matrix mode over the same pinned BDP fixture, failing closed on
any `cross_backend_*` mismatch (see `100_test_strategy_ci.md`, "Evaluator conformance harness").

### Merge and release blocking policy

- Merges to the default branch MUST be blocked unless Content CI passes.
- Releases MUST be blocked unless both Content CI and Run CI pass.

Clarification (normative): a "release" in this section includes any published production artifact
tagged as a Purple Axiom v0.1 release (for example: container images, binaries, or packages).

Release publication pipelines MUST execute Content CI and Run CI against the same commit and the
same pinned inputs used to build the production artifact being published.

Projects MAY enforce stricter policies but MUST NOT relax the minimum policy above.

### Required CI entrypoints

Implementations MUST expose stable entrypoints that a CI runner can invoke.

Minimum requirement (v0.1):

The repository MUST expose stable entrypoints named:

- `ci-content`
  - Runs Content CI validations.
  - MUST exit `0` on success and `20` on failure.
- `ci-run`
  - Runs Run CI (BDP replay and/or minimal lab run).
  - MUST exit `0|10|20` when producing run bundles, using the orchestrator exit code semantics.
  - When producing a run bundle, MUST emit `runs/<run_id>/run_results.json` (schema-valid).
  - For replay-only modes, MUST still exit `0|10|20`, matching the derived verdict mapping.

These entrypoints MAY be implemented as Makefile targets (`make ci-content` / `make ci-run`), CLI
subcommands (`<project_cli> ci content` / `<project_cli> ci run`), or standalone scripts.

## CI contract

### CI decision surface

CI MUST compute a single verdict for each `run_id` using only contracted artifacts and the exit-code
mapping defined by v0.1.

This section is a consolidation of existing requirements: reporting defines the CI-facing status
recommendation, data contracts define manifest status derivation, and operability/ADR-0005 define
exit-code and outcome semantics.

Unless otherwise stated, paths in this document are expressed in run-bundle rooted form
(`runs/<run_id>/...`). The corresponding run-relative form is defined in
[Path notation](#path-notation-normative).

#### CI run results surface (required)

For any run bundle produced by the Run CI lane (`ci-run`), CI MUST treat
`runs/<run_id>/run_results.json` as a REQUIRED artifact.

`runs/<run_id>/run_results.json` MUST be present and schema-valid. CI MUST use
`runs/<run_id>/run_results.json.status` as the authoritative CI verdict source.

If `runs/<run_id>/run_results.json` is missing or schema-invalid, CI MUST treat this as a
fail-closed pipeline contract violation and MUST force the CI verdict to `failed` (CI exit code
`20`), even when other artifacts suggest `success` or `partial`.

#### CI reporting mode (required)

For any run bundle produced by the Run CI lane (`ci-run`), the effective run configuration MUST set:

- `reporting.emit_json=true`

As a consequence, CI MUST treat the following reporting artifacts as REQUIRED for CI runs and MUST
enforce them as a coupled set:

- `runs/<run_id>/report/thresholds.json`
- `runs/<run_id>/report/report.json`
- `runs/<run_id>/report/run_timeline.md`

`runs/<run_id>/report/thresholds.json` and `runs/<run_id>/report/report.json` MUST be schema-valid.
`runs/<run_id>/report/run_timeline.md` MUST be contract-valid per `run_timeline.schema`
(timeline-conformant as defined in `080_reporting.md`).

If `runs/<run_id>/report/junit.xml` is present, it MUST NOT be treated as a substitute for the
coupled set above.

#### Evidence precedence

For a given `run_id`, CI MUST determine the verdict source in the following order. Any fail-closed
pipeline contract violation (for example, missing/invalid required evidence or mismatched coupled
signals) MUST override the selected verdict source and force the CI verdict to `failed`.

1. If `runs/<run_id>/run_results.json` exists and validates against its schema, CI MUST use
   `runs/<run_id>/run_results.json.status`.
1. Else, CI MUST treat the missing/invalid `run_results.json` as a fail-closed pipeline contract
   violation and MUST force the CI verdict to `failed`.

Crash-detection fallback (non-authoritative): when `runs/<run_id>/run_results.json` is missing or
schema-invalid, CI SHOULD still attempt to classify the failure by inspecting other artifacts, but
MUST NOT use these fallback signals to pass CI.

1. If `runs/<run_id>/report/thresholds.json` exists and validates against its schema, CI SHOULD
   record the observed status as `runs/<run_id>/report/thresholds.json.status_recommendation`.
1. Else, if `runs/<run_id>/manifest.json` exists and validates against its schema, CI SHOULD record
   the observed status as `manifest.status` from `runs/<run_id>/manifest.json`.
1. Else, if the run bundle root `runs/<run_id>/` exists, CI SHOULD derive an observed status from
   the orchestrator process exit code captured by CI:
   - `0 -> success`
   - `10 -> partial`
   - `20 -> failed`
   - Any other exit code MUST be treated as `failed` and MUST be recorded as a pipeline contract
     violation.
   - If the orchestrator process exit code is not available to CI in this scenario, CI MUST treat
     the run as `failed` and MUST record a pipeline contract violation.

Reporting output coupling (fail closed):

- For CI runs (see "CI reporting mode" above), CI MUST require the full coupled reporting set:
  - `runs/<run_id>/report/thresholds.json`
  - `runs/<run_id>/report/report.json`
  - `runs/<run_id>/report/run_timeline.md`
- If `runs/<run_id>/report/junit.xml` is present, CI MUST also require the coupled set above to be
  present (JUnit is not a substitute for the contracted JSON decision surface).
- `runs/<run_id>/report/thresholds.json` and `runs/<run_id>/report/report.json` MUST be
  schema-valid.
- `runs/<run_id>/report/run_timeline.md` MUST be contract-valid per `run_timeline.schema`.
- Any missing/invalid artifact or any mismatch MUST be treated as a fail-closed pipeline contract
  violation.

If the run bundle root `runs/<run_id>/` does not exist (for example, failure before run directory
creation), CI MUST treat the run as `failed`. When the orchestrator process exit code is available
to CI as a captured signal in this case, it MUST be `20`; any other exit code MUST be treated as a
pipeline contract violation and MUST fail closed.

#### Consistency checks (fail closed)

When the following artifacts are present, CI MUST fail closed if their status signals disagree:

- When `runs/<run_id>/report/thresholds.json` and `runs/<run_id>/report/report.json` are present,
  `runs/<run_id>/report/thresholds.json.status_recommendation` MUST equal
  `runs/<run_id>/report/report.json.status`.
- When `runs/<run_id>/run_results.json` and `runs/<run_id>/report/thresholds.json` are present,
  `runs/<run_id>/run_results.json.status` MUST equal
  `runs/<run_id>/report/thresholds.json.status_recommendation`.
- When `runs/<run_id>/run_results.json` and `runs/<run_id>/manifest.json` are present,
  `runs/<run_id>/run_results.json.run_id` MUST equal `manifest.run_id` and
  `runs/<run_id>/run_results.json.status` MUST equal `manifest.status`.
- When `runs/<run_id>/report/run_timeline.md` is present, it MUST be contract-valid per
  `run_timeline.schema` (timeline-conformant as defined in `080_reporting.md`).
- When `runs/<run_id>/manifest.json` and `runs/<run_id>/report/report.json` are present,
  `manifest.run_id` from `runs/<run_id>/manifest.json` MUST equal
  `runs/<run_id>/report/report.json.run_id`.
- `runs/<run_id>/report/report.json.status_reasons[]` MUST contain unique reason codes and MUST be
  emitted sorted ascending (UTF-8 byte order, no locale) when `runs/<run_id>/report/report.json` is
  present.
- `manifest.status` from `runs/<run_id>/manifest.json` MUST equal
  `runs/<run_id>/logs/health.json.status` when `operability.health.emit_health_files=true` and
  `runs/<run_id>/logs/health.json` is present.
- The CI job step that enforces this contract MUST exit with `(0|10|20)` matching the derived
  verdict.
- When the orchestrator process exit code is available to CI as a captured signal (for example, from
  a prior job step), it MUST match the derived verdict. Any mismatch MUST be treated as a
  fail-closed pipeline contract violation.

CI MUST also fail closed if any contract-backed evidence artifact is present but fails schema
validation.

#### Allowed absence of outcomes

v0.1 allows a narrow exception where stage outcomes cannot be recorded due to operational failures
(for example, `lock_acquisition_failed` or `storage_io_error`). In this case,
`runs/<run_id>/manifest.json` and/or `runs/<run_id>/logs/health.json` MAY be missing.

In this exception scenario, `runs/<run_id>/run_results.json` MAY also be missing.

When this exception occurs, CI MUST treat the run as `failed`. The captured orchestrator exit code
MUST be `20`; any other exit code MUST be treated as a pipeline contract violation and MUST fail
closed. CI MUST surface the absence of outcomes as an operational error requiring reconciliation.

### Required gate catalog

CI MUST enforce the required gate categories already defined by the test strategy:

| Gate category             | Required?                       | Primary evidence                                                     | Fail mode                                                                                                                             |
| ------------------------- | ------------------------------- | -------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| Schema validation         | REQUIRED                        | schema validation output / errors                                    | fail-closed                                                                                                                           |
| Version conformance       | REQUIRED                        | supported version pins + historical bundle fixtures                  | fail-closed                                                                                                                           |
| Determinism gates         | REQUIRED when enabled           | Evaluator conformance report + determinism fixtures                  | fail-closed for `result_hash_mismatch`; warn-only for `plan_hash_mismatch` unless explicitly enabled as a gate                        |
| Artifact validation       | REQUIRED                        | run bundle paths + contract reports                                  | fail-closed                                                                                                                           |
| Cross-artifact invariants | REQUIRED                        | manifest/run_id joins + referential checks                           | fail-closed                                                                                                                           |
| Operational readiness     | REQUIRED when enabled (default) | `logs/health.json`, `logs/telemetry_validation.json`, `logs/run.log` | fail-closed for required canaries; threshold-based (partial allowed) for configured budgets (including detection performance budgets) |
| Regression gates          | REQUIRED when enabled           | baseline compare outputs + thresholds                                | threshold-based (partial allowed)                                                                                                     |

This table is a consolidation view; details remain in the underlying specs.

### CI gate findings artifacts (required)

CI gates MUST have a single, canonical machine-readable output surface for CI evaluation and
annotations.

#### Artifact path and contract

- Path (workspace-root): `artifacts/findings/<gate_id>.findings.v1.json`
- Contract: `ci_gate_findings` (workspace contract registry binding)

#### Shared diagnostic record (`pa:diagnostic-record:v1`) (normative)

All `ci_gate_findings.findings[]` entries MUST conform to the canonical diagnostic record shape
`pa:diagnostic-record:v1` as defined by `025_data_contracts.md` ("Diagnostic record").

Additional constraints imposed by the `ci_gate_findings` contract (normative):

- `reason_domain` MUST equal `"ci_gate_findings"` for every finding (because `reason_domain` is
  schema-owned for contract-backed artifacts).
- The `ci_gate_findings` ordering, de-duplication, and fingerprint algorithm is the default ordering
  for any `pa:diagnostic-record:v1` list emitted as `diagnostics[]` elsewhere.

CI MUST treat findings artifacts as **required evidence** for any enforced REQUIRED gate:

- Each enforced gate MUST emit exactly one findings artifact at the path above, even when
  `findings=[]` (pass case).
- Missing findings artifacts for any REQUIRED gate MUST fail CI (fail closed).
- Findings artifacts MUST be contract-valid JSON. Schema-invalid artifacts MUST fail CI (fail
  closed).

#### Gate pass/fail semantics (normative)

Given a findings artifact that declares `gate.required=true`:

- The gate MUST be treated as **failed** when any finding has `severity` of `error` or `fatal`.
- The gate MUST be treated as **passed** when there are zero `error`/`fatal` findings (warnings and
  infos MAY be present).
- CI policy MAY escalate warnings to errors, but any escalation MUST be explicit and deterministic
  (out of scope for v0.1).

#### Deterministic ordering and fingerprinting (normative)

Findings artifacts are required to be deterministic to enable stable CI verdicts and stable
annotation surfaces.

Canonical bytes:

- Findings JSON MUST be emitted as canonical JSON bytes (RFC 8785 / `canonical_json_bytes` as
  defined by `026_contract_spine.md`).

Findings ordering:

- Reason domain pairing (normative):

  - Each finding MUST include `reason_domain` and `reason_code` as a sibling pair.
  - For `ci_gate_findings` artifacts, `reason_domain` MUST equal the contract id `ci_gate_findings`.
  - `reason_domain` MUST be present iff `reason_code` is present. (Since `reason_code` is required
    by this contract, `reason_domain` is required for all findings.)

- Before writing the artifact, producers MUST sort the `findings[]` array ascending by:

  1. `severity_rank` (`fatal=0`, `error=1`, `warn=2`, `info=3`)
  1. `reason_domain` (UTF-8 byte order, no locale)
  1. `reason_code` (UTF-8 byte order, no locale)
  1. `subject.kind`
  1. `subject.stable_id`
  1. `rule_id`
  1. `location.file_path` (missing sorts as empty string)
  1. `location.span.start_line` (missing sorts as `0`)
  1. `location.span.start_col` (missing sorts as `0`)
  1. `fingerprint`

- After sorting, producers MUST de-duplicate the `findings[]` array by `fingerprint` (keep the first
  entry after sort for each distinct fingerprint).

Fingerprint algorithm:

- Each finding MUST include `fingerprint` computed as:

```text
message_normalized =
  trim(message) with all runs of whitespace collapsed to a single ASCII space

fingerprint = SHA256_HEX(
  severity + "\n" +
  category + "\n" +
  reason_code + "\n" +
  rule_id + "\n" +
  subject.kind + "\n" +
  subject.stable_id + "\n" +
  (location.file_path || "") + "\n" +
  (location.span.start_line || 0) + ":" + (location.span.start_col || 0) + "\n" +
  message_normalized
)
```

#### Baseline gate IDs (v0.1)

To keep the CI surface stable across implementations, the following gate IDs are reserved for v0.1:

- `content.lint` (Content CI linting + Contract Spine conformance)
- `content.sigma.semantic` (Content CI Sigma semantic validators)
- `content.fixtures.validate` (Content CI fixture registry validation + canonicalization)
- `content.bundle.integrity` (Content CI offline bundle validation)
- `run.publish_gate` (Run CI publish-gate contract validation surface)

### Publish-gate enforcement

CI MUST verify publish-gate requirements by checking that:

- Stage outputs are written to staging then atomically published into contracted run bundle paths.
- Contract validation outputs (when emitted) are present under:
  - `runs/<run_id>/logs/contract_validation/<stage_id>.json` (per stage)
- Deterministic artifact path rules are enforced (no timestamps in contracted filenames).

CI SHOULD perform a post-run publish-gate sanity check by asserting that
`runs/<run_id>/.staging/<stage_id>/` does not remain populated after orchestrator completion. Any
leftover staged output indicates incomplete atomic publish and MUST be treated as a fail-closed
contract failure.

Note: v0.1 contract documents specify per-stage contract validation logs at
`runs/<run_id>/logs/contract_validation/<stage_id>.json`. If any CI fixtures reference a different
path, that discrepancy MUST be reconciled in the source documents; CI implementations MUST follow
the artifact contract path.

### Operational readiness evidence surfaces

Where enabled by v0.1 specs/config:

- `runs/<run_id>/logs/health.json` MUST exist and conform to schema when
  `operability.health.emit_health_files=true` (default).
- `runs/<run_id>/logs/telemetry_validation.json` MUST exist and conform when the telemetry stage is
  enabled (`telemetry.otel.enabled=true`; see stage enablement / required outputs matrix).
- `runs/<run_id>/logs/run.log` MUST exist (human-readable execution log; primary surface for
  warn-only diagnostics).
- `runs/<run_id>/logs/warnings.jsonl` is OPTIONAL; it may include warn-only entries for non-gating
  anomalies.

When `operability.health.emit_health_files=false`, `logs/health.json` MAY be absent. In this mode,
CI MUST NOT fail solely due to missing health file, but MUST still require `manifest.json` to
validate and to provide canonical `manifest.status`, unless the
[Allowed absence of outcomes](#allowed-absence-of-outcomes) exception applies.

CI MUST treat missing operational readiness files that are REQUIRED for the run’s enabled feature
set as contract failure (fail closed).

When `logs/health.json` is present, CI MUST validate ADR-0005 conformance properties that are
critical to determinism (violations are fail-closed):

- Stage and substage arrays are emitted in stable order.
- `reason_code` tokens are drawn from the known registry for the relevant stage context.

### Artifact retention (CI publication)

CI SHOULD retain (as build artifacts) the minimum evidence surface required for deterministic
debugging of gate failures:

- `runs/<run_id>/manifest.json`
- `runs/<run_id>/logs/run.log`
- `runs/<run_id>/logs/warnings.jsonl` (when present)
- `runs/<run_id>/report/thresholds.json` (when present)
- `runs/<run_id>/report/report.json` (when present)
- `runs/<run_id>/report/run_timeline.md` (when present)
- `runs/<run_id>/report/report.html` (when present)
- `runs/<run_id>/logs/health.json` (when present / when enabled)
- `runs/<run_id>/logs/telemetry_validation.json` (when present / when enabled)
- `runs/<run_id>/logs/cache_provenance.json` (when present)
- `runs/<run_id>/logs/contract_validation/` (when present)
- `artifacts/evaluator_conformance/**/report.json` (when determinism gate is enabled)
- `artifacts/findings/**` (required gate evidence)
- `artifacts/fixtures/**` (when fixture gates are enabled)
- `artifacts/connectors/**` (when connector gates are enabled)

Clarification (normative): CI artifact retention is a CI debugging mechanism. It MUST NOT be treated
as a substitute for the `export` verb, the default export profile, or signing/checksum scope. Export
and signing behavior is governed by the existing run export policy (ADR-0009) and signing contracts.

Security posture for CI artifacts:

- CI artifact publication MUST obey the security/redaction posture. Resolved secrets MUST NOT be
  written into CI artifacts.
- When unredacted evidence quarantine is used, `runs/<run_id>/unredacted/` (or the configured
  `security.redaction.unredacted_dir`) MUST be excluded from default CI artifact publication unless
  an operator explicitly intends to retain unredacted evidence.

### CI matrix contract

A "CI matrix" is a CI job strategy that executes multiple independent v0.1 runs (matrix cells) with
controlled variation across a declared set of input dimensions (matrix axes), then aggregates the
resulting artifacts to answer questions such as:

- Fixed tests, many detections: hold scenarios and telemetry constant while varying detection
  content (rule sets, and optionally mapping packs) to measure detection effectiveness deltas.
- Fixed detections, many tests: hold detections constant while varying scenarios/criteria to measure
  test suite coverage and stability.
- Regression: compare a candidate run to a baseline run under a pinned, comparable input set to
  detect drift in the regression-comparable metric surface.

v0.1 does not introduce a new "matrix execution" subsystem. A matrix runner is an external harness
(CI workflow, Make target, etc.) that invokes the orchestrator once per matrix cell and treats each
cell as a normal v0.1 run bundle (`runs/<run_id>/...`).

#### Terminology

- **Matrix runner**: external driver that launches one orchestrator run per cell, collects run
  bundles, and (optionally) performs cross-run aggregation.
- **Matrix cell**: exactly one v0.1 run bundle identified by a distinct `run_id`.
- **Matrix axis**: a single dimension the matrix runner varies across cells (for example,
  `rule_set_version`).
- **Regression cohort**: the set of runs that share a regression-comparable pin set (see below).
  Only runs within the same cohort are eligible for meaningful baseline-to-candidate regression
  deltas.

#### Allowed axes (what may vary)

A matrix runner MAY vary any of the following axes across cells. Each axis MUST be captured as an
effective value in a contracted run artifact so that aggregation is deterministic and explainable.

| Axis (concept)                                             | Authoritative recording location                                                                              | Regression deltas when this axis varies?                         |
| ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| Scenario (`scenario_id`/`scenario_version`)                | `runs/<run_id>/manifest.json`: `manifest.versions.scenario_*`                                                 | No. MUST be pinned for reporting regression.                     |
| Rule set (`rule_set_id`/`rule_set_version`)                | `runs/<run_id>/manifest.json`: `manifest.versions.rule_set_*`                                                 | No. MUST be pinned for reporting regression.                     |
| Mapping pack (`mapping_pack_id`/`mapping_pack_version`)    | `runs/<run_id>/manifest.json`: `manifest.versions.mapping_pack_*`                                             | Only if pinned, or if drift is explicitly allowed by policy.     |
| Criteria pack (`criteria_pack_id`/`criteria_pack_version`) | `runs/<run_id>/manifest.json`: `manifest.versions.criteria_pack_*`                                            | No. MUST be pinned for reporting regression.                     |
| OCSF version (`ocsf_version`)                              | `runs/<run_id>/manifest.json`: `manifest.versions.ocsf_version`                                               | No. MUST be pinned for reporting regression.                     |
| Pipeline version (`pipeline_version`)                      | `runs/<run_id>/manifest.json`: `manifest.versions.pipeline_version`                                           | No. MUST be pinned for reporting regression.                     |
| Range config hash (best-effort)                            | `runs/<run_id>/manifest.json`: `manifest.inputs.range_yaml_sha256` (optional)                                 | Yes, but SHOULD be pinned to reduce noise.                       |
| Gate thresholds / regression policy                        | `runs/<run_id>/report/thresholds.json` and `runs/<run_id>/report/report.json.regression.comparability.policy` | Metrics comparable; gate decisions not comparable unless pinned. |

Notes (normative):

- If an axis value is not recorded in the run bundle, the matrix runner MUST treat the run as
  ineligible for deterministic trending and reporting regression.
- Environment-derived values (hostnames, absolute paths, wall-clock timestamps) MUST NOT be treated
  as axes or join keys for reporting regression (see ADR-0001).

#### What MUST be pinned for meaningful reporting regression

A reporting regression comparison is the reporting-stage baseline-to-candidate comparison recorded
in `runs/<run_id>/report/report.json.regression` (see `080_reporting.md` and
`070_scoring_metrics.md`). A matrix runner MUST treat `report/report.json.regression.comparability`
as the authoritative statement of whether reporting regression deltas are meaningful.

To keep reporting regression meaningful (that is, to allow `comparability.status` to be `comparable`
or `warning` rather than `indeterminate`), the matrix runner MUST ensure that baseline and candidate
runs are in the same regression cohort:

- The reporting regression comparability key set in `080_reporting.md` MUST match byte-for-byte
  across baseline and candidate, with the only allowed exception being mapping pack version drift
  when the candidate explicitly enables
  `report/report.json.regression.comparability.policy.allow_mapping_pack_version_drift=true` and the
  resulting `comparability.status` is `warning`.
- `inputs.range_yaml_sha256` is OPTIONAL and non-fatal; when present in both runs it SHOULD match. A
  mismatch MUST be treated as a noise indicator and MUST surface as at least `warning`
  comparability.

If `comparability.status` is `indeterminate`, a matrix runner MUST NOT treat the absence of deltas
as "no change". It MUST treat the regression delta surface (`deltas[]`) as non-authoritative for
cross-run comparison in that case.

#### Benchmark comparisons (non-regression)

Matrix comparisons where one or more MUST-match reporting regression pins are intentionally varied
(for example, testing a new `rule_set_version` against a fixed scenario) are benchmarks, not
reporting regression.

A matrix runner MAY compute benchmark comparisons from per-run artifacts such as
`scoring/summary.json`, but MUST NOT present benchmark deltas as
`report/report.json.regression.deltas[]`, and MUST label such comparisons as non-regression (not
reporting regression comparable by definition).

#### Matrix runner artifact retention (cross-run analysis)

In addition to the minimum CI evidence surface listed above, a matrix runner that intends to perform
cross-run analysis (reporting regression or benchmark) MUST retain, for every matrix cell, the
contracted artifacts required to recompute comparable metrics and to attribute gaps
deterministically:

- `runs/<run_id>/scoring/summary.json`
- `runs/<run_id>/normalized/mapping_coverage.json`
- `runs/<run_id>/bridge/coverage.json` (when the Sigma-to-OCSF bridge is enabled)
- `runs/<run_id>/detections/detections.jsonl` (when Sigma evaluation is enabled)
- `runs/<run_id>/criteria/manifest.json` and `runs/<run_id>/criteria/results.jsonl` (when criteria
  evaluation is enabled)

When reporting regression is enabled for a cell, the matrix runner MUST also retain:

- `runs/<run_id>/inputs/baseline_run_ref.json`
- `runs/<run_id>/inputs/baseline/manifest.json` (when present)

Retention posture (normative):

- Retained matrix artifacts MUST obey the security/redaction posture described above and in
  ADR-0009. Quarantined/unredacted evidence directories MUST NOT be published by default.
- For large analytics datasets (`raw_parquet/**`, `normalized/**`), CI MAY omit the data from
  default retention to control artifact size, but SHOULD retain it for benchmark campaigns where
  deeper triage is expected.

## State machine representation (representational; non-normative)

This state machine is an illustrative CI orchestration view only. It is representational
(non-normative) and does not define new conformance requirements. Runtime stage behavior and
conformance are defined solely by the artifact contracts and status semantics in the preceding
sections.

Lifecycle authority references (per ADR-0007 representational requirements):

- Verdict derivation: [CI decision surface](#ci-decision-surface) and ADR-0005 exit-code semantics.
- Reporting coupling: `080_reporting.md` (thresholds status recommendation ↔ report status).
- Health/stage outcomes: `025_data_contracts.md` and ADR-0005 (`logs/health.json` semantics).
- Gate inventory: [Required gate catalog](#required-gate-catalog).

No-conflict statement (representational): if this representation conflicts with any lifecycle
authority reference above, the lifecycle authority reference is authoritative (this section MUST NOT
be treated as overriding semantics).

### State machine: CI gate lifecycle (v0.1) (representational; non-normative)

States (closed set):

- `pending`
- `executing`
- `validating`
- `publishing`
- `completed_success`
- `completed_partial`
- `completed_failed`

Events (closed set):

- `ci_job_started`
- `orchestrator_exited`
- `decision_surface_evaluated`
- `artifacts_published`

Transitions:

- `pending -> executing`: CI job starts (`ci_job_started`).
- `executing -> validating`: orchestrator exits (`orchestrator_exited`). CI begins decision-surface
  evaluation and gate enforcement.
- `validating -> publishing`: post-run gate evaluation completes (`decision_surface_evaluated`).
- `publishing -> completed_*`: artifacts retained/published and verdict recorded
  (`artifacts_published`).
- `executing -> completed_failed`: orchestrator exits (`orchestrator_exited`) without producing a
  conformant manifest/health surface due to an allowed outcome-recording exception; CI fails the run
  based on exit code.

Terminal mapping:

- `completed_success` iff verdict is `success` and exit code is `0`.
- `completed_partial` iff verdict is `partial` and exit code is `10`.
- `completed_failed` iff verdict is `failed` and exit code is `20`.

## Verification hooks

A CI pipeline is conformant iff:

- Required gate categories are executed and enforced with the specified fail modes.
- Historical run bundle compatibility matrix is enforced (current tooling can parse and validate the
  supported window of prior golden run bundles; see ADR-0001 and `100_test_strategy_ci.md`).
- CI verdict is derived deterministically from the decision surface.
- Exit code mapping matches the verdict mapping.
- Missing required artifacts are treated as fail-closed contract failures.
- Reporting output coupling is enforced when reporting artifacts are present (`report/report.json`,
  `report/thresholds.json`, and `report/run_timeline.md`).
- Status coupling checks are enforced when artifacts/signals are present
  (`thresholds.status_recommendation` \<-> `report.status`; `manifest.status` \<-> `health.status`;
  captured orchestrator exit code \<-> derived verdict).
- ADR-0005 CI conformance checks are enforced for stage outcome ordering and reason code validity.
- CI artifact publication obeys the security/redaction posture (no secrets; unredacted quarantine
  excluded by default).

### Conformance fixture matrix (v0.1)

This matrix defines minimal file-tree fixtures (present/missing/invalid) and the expected CI exit
code.

These fixtures exercise the same run-bundle artifacts and coupling rules that the contract tests in
`100_test_strategy_ci.md` gate, but the fixture IDs in this matrix are local to this section (they
do not imply a shared global fixture naming scheme).

Canonical fixture root: `tests/fixtures/ci/verdict_surface/` (see the fixture index in
`100_test_strategy_ci.md`). Expected exit codes follow the ADR-0005 `(0|10|20)` mapping.

Legend:

- `OK` = present and schema-valid
- `MISSING` = missing
- `INVALID` = present but schema-invalid
- `VIOLATION` = present and schema-valid, but violates a semantic invariant

Unless stated otherwise, fixtures assume `operability.health.emit_health_files=true` (so
`logs/health.json` is required when `runs/<run_id>/` exists).

| Fixture ID                                        | Gate / rule exercised                                              | Minimal fixture (paths relative to `runs/<run_id>/` unless noted)                                                                                                                                                                                                                                                                                                                   | Expected CI verdict | Expected CI exit code |
| ------------------------------------------------- | ------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------- | --------------------- |
| `happy_path_success`                              | End-to-end success (decision surface)                              | `run_results.json`: OK (`status=success`); `manifest.json`: OK (`status=success`); `logs/health.json`: OK (`status=success`); `report/thresholds.json`: OK (`status_recommendation=success`); `report/report.json`: OK (`status=success`); `report/run_timeline.md`: OK; `logs/run.log`: OK                                                                                         | `success`           | `0`                   |
| `happy_path_partial_threshold_degrade`            | Partial due to threshold failure (decision surface)                | `run_results.json`: OK (`status=partial`); `manifest.json`: OK (`status=partial`); `logs/health.json`: OK (`status=partial`); `report/thresholds.json`: OK (`status_recommendation=partial`); `report/report.json`: OK (`status=partial`); `report/run_timeline.md`: OK; `logs/run.log`: OK                                                                                         | `partial`           | `10`                  |
| `happy_path_failed_required_artifact_missing`     | Failed due to missing required artifact (fail closed)              | `run_results.json`: OK (`status=failed`); `manifest.json`: OK (`status=failed`); `logs/health.json`: OK (`status=failed`); `scoring/summary.json`: MISSING; `logs/run.log`: OK                                                                                                                                                                                                      | `failed`            | `20`                  |
| `schema_invalid_health`                           | Schema validation (fail closed)                                    | `manifest.json`: OK (`status=success`); `logs/health.json`: INVALID; `logs/run.log`: OK                                                                                                                                                                                                                                                                                             | `failed`            | `20`                  |
| `schema_invalid_run_results`                      | Schema validation (fail closed)                                    | `run_results.json`: INVALID; `manifest.json`: OK (`status=success`); `logs/run.log`: OK                                                                                                                                                                                                                                                                                             | `failed`            | `20`                  |
| `run_results_missing_when_required`               | Decision surface (`run_results` required for `ci-run`)             | `run_results.json`: MISSING; `manifest.json`: OK (`status=success`); `logs/health.json`: OK (`status=success`); `report/thresholds.json`: OK (`status_recommendation=success`); `report/report.json`: OK (`status=success`); `report/run_timeline.md`: OK; `logs/run.log`: OK                                                                                                       | `failed`            | `20`                  |
| `schema_invalid_thresholds`                       | Schema validation (fail closed)                                    | `report/thresholds.json`: INVALID; `report/report.json`: OK; `report/run_timeline.md`: OK; `logs/run.log`: OK                                                                                                                                                                                                                                                                       | `failed`            | `20`                  |
| `status_mismatch_report_thresholds`               | Status coupling (`thresholds` \<-> `report`)                       | `report/thresholds.json`: OK (`status_recommendation=success`); `report/report.json`: OK (`status=partial`); `report/run_timeline.md`: OK; `logs/run.log`: OK; invariant: `thresholds.status_recommendation != report.status` (VIOLATION)                                                                                                                                           | `failed`            | `20`                  |
| `status_mismatch_run_results_thresholds`          | Status coupling (`run_results` \<-> `thresholds`)                  | `run_results.json`: OK (`status=partial`); `manifest.json`: OK (`status=success`); `report/thresholds.json`: OK (`status_recommendation=success`); `report/report.json`: OK (`status=success`); `report/run_timeline.md`: OK; `logs/run.log`: OK; invariant(s): `run_results.status != thresholds.status_recommendation` and/or `run_results.status != manifest.status` (VIOLATION) | `failed`            | `20`                  |
| `report_timeline_missing_when_required`           | Reporting output coupling (timeline required)                      | `report/thresholds.json`: OK (`status_recommendation=success`); `report/report.json`: OK (`status=success`); `report/run_timeline.md`: MISSING; `logs/run.log`: OK                                                                                                                                                                                                                  | `failed`            | `20`                  |
| `orchestrator_exit_code_unknown`                  | Exit-code mapping (unknown => fail closed)                         | No run bundle required; captured orchestrator exit code: `2`                                                                                                                                                                                                                                                                                                                        | `failed`            | `20`                  |
| `artifact_path_timestamped_filename_blocked`      | Deterministic artifact path enforcement                            | `runner/actions/action_20260101T123000Z.json`: OK (timestamped filename in contracted dir); `logs/contract_validation/runner.json`: OK (includes stable error code `timestamped_filename_disallowed`); `logs/run.log`: OK                                                                                                                                                           | `failed`            | `20`                  |
| `publish_gate_incomplete_staging_dir`             | Publish-gate enforcement                                           | `.staging/{stage_id}/`: OK (left behind after run completion); `logs/run.log`: OK                                                                                                                                                                                                                                                                                                   | `failed`            | `20`                  |
| `determinism_report_result_hash_mismatch_fail`    | Determinism gates (fail closed)                                    | (workspace-root relative) `artifacts/evaluator_conformance/{case}/report.json`: OK (`result_hash_mismatch` present)                                                                                                                                                                                                                                                                 | `failed`            | `20`                  |
| `determinism_report_plan_hash_mismatch_warn_only` | Determinism gates (warn-only)                                      | Same as `happy_path_success`, plus: (workspace-root relative) `artifacts/evaluator_conformance/{case}/report.json`: OK (`plan_hash_mismatch` present)                                                                                                                                                                                                                               | `success`           | `0`                   |
| `version_pins_mismatch_fail`                      | Version conformance (fail closed)                                  | `manifest.json`: OK but `manifest.versions.*` violates supported pins (per `SUPPORTED_VERSIONS.md`) (VIOLATION); `logs/run.log`: OK                                                                                                                                                                                                                                                 | `failed`            | `20`                  |
| `cross_artifact_run_id_mismatch_fail`             | Cross-artifact invariants (fail closed)                            | `manifest.json`: OK (`run_id=A`); `report/thresholds.json`: OK (`status_recommendation=success`); `report/report.json`: OK (`run_id=B`, `status=success`); `report/run_timeline.md`: OK; `logs/run.log`: OK; invariant: `manifest.run_id != report.run_id` (VIOLATION)                                                                                                              | `failed`            | `20`                  |
| `telemetry_validation_missing_when_enabled`       | Operational readiness (telemetry validation required when enabled) | `manifest.json`: OK (`status=success`); `logs/health.json`: OK (`status=success`); `logs/telemetry_validation.json`: MISSING (telemetry validation enabled); `logs/run.log`: OK                                                                                                                                                                                                     | `failed`            | `20`                  |
| `run_log_missing`                                 | Operational readiness (required logging surface)                   | `manifest.json`: OK; `logs/run.log`: MISSING                                                                                                                                                                                                                                                                                                                                        | `failed`            | `20`                  |
| `report_status_reasons_unsorted_or_duplicate`     | Reporting determinism (fail closed)                                | `report/report.json`: OK but `status_reasons[]` unsorted and/or contains duplicates (VIOLATION); `report/thresholds.json`: OK; `report/run_timeline.md`: OK; `logs/run.log`: OK                                                                                                                                                                                                     | `failed`            | `20`                  |

## References

- [Test strategy and CI](100_test_strategy_ci.md)
- [Data contracts](025_data_contracts.md)
- [Operability](110_operability.md)
- [Reporting](080_reporting.md)
- [Security and safety](090_security_safety.md)
- [ADR-0001: Project naming and versioning](../adr/ADR-0001-project-naming-and-versioning.md)
- [ADR-0004: Deployment architecture and inter-component communication](../adr/ADR-0004-deployment-architecture-and-inter-component-communication.md)
- [ADR-0005: Stage outcomes and failure classification](../adr/ADR-0005-stage-outcomes-and-failure-classification.md)
- [ADR-0007: State machines for lifecycle semantics](../adr/ADR-0007-state-machines.md)

## Changelog

| Date       | Change |
| ---------- | ------ |
| 2026-01-26 | update |
| 2026-01-12 | draft  |
