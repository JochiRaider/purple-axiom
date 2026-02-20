---
title: Contract Spine
description: Consolidated, implementable seam for contract registry resolution, publish-gate validation, deterministic serialization, reader semantics, and CI conformance.
status: draft
category: spec
tags: [contracts, publish-gate, contract-validator, reader, determinism, ci]
related:

  - 020_architecture.md
  - 025_data_contracts.md
  - 045_storage_formats.md
  - 080_reporting.md
  - 100_test_strategy_ci.md
  - 105_ci_operational_readiness.md
  - ADR-0004-deployment-architecture-and-inter-component-communication.md
  - ADR-0005-stage-outcomes-and-failure-classification.md
  - ADR-0009-run-export-policy-and-log-classification.md
---

# Contract Spine

This document defines the Contract Spine: the canonical, cross-cutting seam that prevents contract
drift across producers (stages + orchestrator) and consumers (CI, reporting, exporters). It
consolidates the mechanically-actionable requirements for:

- Contract registry resolution and glob matching
- Expected outputs construction (including requiredness)
- Publish-gate staging, validation, and atomic promotion
- Contract validation report emission
- Deterministic serialization rules for contract-backed artifacts
- Reader discovery, classification, and stable error codes
- Observability surfaces and CI conformance gates

The Contract Spine exists to ensure multiple implementations do not "re-interpret" the same contract
rules.

## Scope

This document is authoritative for:

- Interface signatures and required behavior for:

  - `ContractRegistry`
  - `PublishGate` and `StagePublishSession`
  - `ContractValidator`
  - `ArtifactReader` (reference reader semantics surface)

- Determinism and canonicalization requirements at the contract seam:

  - stable ordering (paths, errors, outputs)
  - canonical JSON / JSONL byte representation
  - validation dispatch via `validation_mode`

- Failure taxonomy and observability:

  - where error codes appear

  - how failures surface in:

    - `runs/<run_id>/logs/contract_validation/<stage_id>.json`
    - `runs/<run_id>/logs/health.json`
    - CI output and exit codes

- Verification hooks:

  - a Contract Spine conformance gate within Content CI that gates contract conformance
  - the Contract Spine gate MUST run before other Content CI checks

Out of scope:

- The full set of domain contracts and schemas themselves (those live under `docs/contracts/`)
- Stage-specific business logic and scoring semantics
- Non-contract operational logging beyond classification rules

### Authority and precedence

- This document is the canonical consolidation for the Contract Spine seam (publish/validate/read)
  and defines the Contract Spine gate within Content CI.
  - Where this document restates requirements defined in existing specs (notably
    `020_architecture.md`, `025_data_contracts.md`, and `045_storage_formats.md`), it MUST NOT
    drift. If a conflict is discovered, implementations MUST follow the existing spec and the
    conflict MUST be resolved by updating this document (treat as a spec bug).
- ADRs remain authoritative for architecture/decision intent. If this document conflicts with an
  ADR, implementations MUST follow the ADR and the conflict MUST be resolved by updating this
  document (treat as a spec bug).
- For contract schemas and contract registry instance files under `docs/contracts/**`,
  `025_data_contracts.md` and the schema files remain authoritative. Where this document restates
  those rules, it does so for consolidation and MUST NOT drift.

## Normative language

The key words MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY are to be interpreted as described in RFC
2119\.

## Terminology

- Run bundle: the directory `runs/<run_id>/` and its contents (see `025_data_contracts.md` layout).
- Run bundle root: the directory that contains `manifest.json` for a specific run.
- Run-relative path / `artifact_path`: a POSIX path (separator `/`) relative to the run bundle root
  (for example `scoring/summary.json`). It is not an absolute path.
- Contract-backed artifact: a run-bundle artifact whose `artifact_path` matches a binding in the
  contract registry and is therefore schema-validated by publish-gate rules.
- Non-contract artifact: an artifact that does not match a registry binding, or is explicitly
  declared with `contract_id=null` in `ExpectedOutput`.
- Deterministic evidence log (Tier 0): a log file that is allowlisted for exports and for inclusion
  in integrity material (checksums/signing) per ADR-0009 and storage format classification rules.
- CI lane: one of the two explicit CI lanes: Content CI or Run CI (see
  `105_ci_operational_readiness.md`).
- CI gate: a pass/fail rule evaluated by CI within a lane (see `105_ci_operational_readiness.md`).
- Contract Spine gate: the Content CI gate defined by this document (see “Verification and CI
  conformance”).

## Canonical ordering

Unless a section explicitly specifies a different ordering, all "sorted" / "stable ordering"
requirements in this document MUST use the canonical ordering defined here.

### Bytewise UTF-8 lexical ordering

Given two strings `a` and `b`:

1. Encode `a` and `b` as UTF-8 byte sequences (no Unicode normalization; no locale collation).
1. Compare the two byte sequences lexicographically by unsigned byte value (`0x00`..`0xFF`).
1. If one byte sequence is a strict prefix of the other, the shorter sequence sorts first.

This ordering MUST be used for deterministic sorts of:

- `artifact_path` values
- `stage_id` values
- `error_code` values
- any other string fields included in sort keys

## Contract Spine components and ownership

### Ownership and single-authority requirements

- The orchestrator (composition root) MUST be the single authority that:

  - holds the run lock while mutating the run bundle
  - records stage outcomes into `manifest.json` and, when enabled, `logs/health.json`
  - selects and provides the contracts bundle for consumer-side validation workflows
    (historical/offline)

- Stage cores MUST NOT write contract-backed artifacts directly to their final run-bundle paths.
  They MUST publish contract-backed artifacts only via the `PublishGate` instance provided by the
  reference publisher SDK.

### Components

- `ContractRegistry`: resolves contract metadata and ownership for artifact paths using the selected
  registry instance (`docs/contracts/contract_registry.json` or
  `docs/contracts/workspace_contract_registry.json`).
- `ContractValidator`: validates artifact bytes against a resolved schema with deterministic
  dispatch and deterministic error ordering/truncation.
- `PublishGate`: enforces transaction-like publication for stage outputs (stage writes are staged,
  validated, and then atomically promoted).
- `ArtifactReader`: provides canonical consumer semantics for discovering a run bundle, classifying
  artifacts, and reporting stable error codes.

## Contract Registry

### Registry file and location

- Implementations MUST support two contract registry instances inside the selected contracts bundle
  root:

  - Run-bundle registry: `docs/contracts/contract_registry.json` (run-relative bindings).
  - Workspace-root registry: `docs/contracts/workspace_contract_registry.json`
    (workspace-root-relative bindings; relative to `<workspace_root>/`).

- Producers and consumers MUST treat registry selection as an explicit configuration input required
  for contract-backed artifact interpretation. Tooling MUST NOT interpret run-relative bindings as
  workspace-root-relative bindings (or vice versa).

### Registry schema essentials

The registry MUST contain:

- `registry_version` (SemVer; independent of contract versions)
- `contracts[]`, containing at minimum:
  - `contract_id` (stable identifier)
  - `schema_path` (repo-relative path under `docs/contracts/`)
  - `contract_version` (SemVer string; MUST match the schema constant)
- `bindings[]`, containing at minimum:
  - `artifact_glob` (POSIX glob; `glob_v1`; registry-relative)
  - `contract_id` (must exist in `contracts[]`)
  - `validation_mode` (authoritative parse/validation dispatch key)
  - `stage_owner` (owning stage ID, or `orchestrator`)

### Path requirements

All paths consumed or produced by Contract Spine components MUST obey POSIX-relative constraints
(registry-relative):

- For the run-bundle registry, paths are run-relative (relative to the run bundle root).
- For the workspace-root registry, paths are workspace-root-relative (relative to
  `<workspace_root>/`).

Constraints:

- Separator MUST be `/` (backslash `\` is forbidden).
- Paths MUST NOT start with `/`.
- Paths MUST NOT contain a drive prefix (for example `C:`).
- Paths MUST NOT contain a NUL byte.
- Paths MUST NOT contain any `..` segment.
- Paths MUST NOT contain empty segments (`//` is forbidden).
- Paths MUST NOT end with `/`.

### Glob semantics

- All components that interpret `bindings[].artifact_glob` MUST implement `glob_v1` semantics
  exactly (see `025_data_contracts.md`, "Glob semantics (glob_v1)").
- Fail-closed requirement:
  - If any `artifact_glob` is invalid per `glob_v1`, the registry MUST be treated as invalid
    configuration.
  - Consumers MUST surface this as `error_code="contract_registry_parse_error"`.
  - Producers MUST treat publish-gate configuration as invalid and MUST NOT publish outputs.

Registry version compatibility (normative):

- Contract Spine implementations MUST declare a supported `registry_version` range.
- If `registry_version` is outside the supported range, the registry MUST be treated as invalid
  configuration (fail closed) and MUST surface as:
  - consumer (reader / offline validation): `error_code="schema_registry_version_incompatible"`
  - producer (publish gate): publish-gate configuration failure (no publishing)

### Binding uniqueness and ambiguity

To prevent divergent interpretations:

- For any registry-relative `artifact_path`, at most one binding MUST match.
- If multiple bindings match the same `artifact_path`, the registry MUST be treated as invalid
  configuration and tooling MUST fail closed.
  - Consumer surface: `error_code="contract_registry_parse_error"` with `details` identifying the
    ambiguous bindings.
  - Producer surface: publish-gate MUST refuse to validate/publish and MUST surface a configuration
    failure (see "Failure taxonomy and observability").

Note: This is stricter than "first match wins". No implementation is allowed to pick an arbitrary
winner.

### Validation mode as the only dispatch key

- `validation_mode` MUST be treated as the only authoritative switch for validation behavior.
- Implementations MUST NOT select validation behavior based on file extension (for example `.json`,
  `.jsonl`, `.yaml`) or inferred schema metadata.
- Supported modes (v0.1):
  - `json_document`
  - `jsonl_lines`
  - `yaml_document`
- If an implementation does not support a registry `validation_mode`, validation MUST fail closed
  with a configuration error.

### YAML validation mode policy (ingress-only; v0.1)

`validation_mode="yaml_document"` is reserved for **ingress/control-plane YAML** in v0.1.

Registry invariants (normative):

- Any binding with `validation_mode="yaml_document"` MUST have `stage_owner == "orchestrator"`.
- Any binding with `validation_mode="yaml_document"` MUST bind under `inputs/` in v0.1.
  - Concretely: `bindings[].artifact_glob` MUST start with the literal prefix `inputs/`.
  - If future versions introduce additional orchestrator-owned control-plane roots (for example
    `control/`), those MUST be added by an explicit spec update (do not silently broaden).
- Stage-owned contract-backed outputs MUST NOT use `validation_mode="yaml_document"`.
  - Contract-backed interstage seams remain JSON/JSONL only (canonicalized) in v0.1.

Fail-closed enforcement (normative):

- `ContractRegistry.load(...)` MUST fail closed if any binding violates the invariants above.
- The Contract Spine gate MUST fail closed if any binding violates the invariants above.

Rationale (non-normative):

- YAML is accepted for operator/orchestrator-provided inputs, but deterministic interstage seams
  remain JSON/JSONL to avoid cross-language YAML emission drift.

### Contract version constant

Each schema MUST include a `contract_version` constant (SemVer string, expressed via JSON Schema
`const`). If a schema’s `contract_version` disagrees with the registry
`contracts[].contract_version` for the same `contract_id`, validation tooling MUST fail closed
(misconfiguration).

### Universal placeholder support for contract-backed JSON artifacts (v0.1)

Contract-backed artifacts are required to maintain stable paths even when evidence is withheld,
quarantined, or absent due to the effective redaction/safety posture.

Normative requirements:

- For every contract with `validation_mode="json_document"` (contract-backed JSON artifacts), the
  schema MUST allow an optional top-level `placeholder` object with the shape `pa.placeholder.v1` as
  defined in `090_security_safety.md` ("Placeholder artifacts").
- Presence of `placeholder` MUST NOT make an otherwise-invalid artifact instance "schema-valid".
  Unless an artifact contract explicitly states otherwise, all other invariants and constraints
  continue to apply.
  - If an artifact contract has schema-required non-placeholder fields, placeholder instances MUST
    satisfy those requirements using redacted-safe sentinel values as defined in
    `090_security_safety.md`.
- Contract authors SHOULD factor the `pa.placeholder.v1` definition into shared `$defs` to avoid
  drift, but schema factoring choices are implementation-defined.

Verification hook (normative):

- Content CI MUST include a lint rule that fails if any `validation_mode="json_document"` schema is
  missing the `placeholder` property.

## Interfaces

This section defines the Contract Spine interfaces. Names are normative; language bindings MAY vary
but MUST preserve signatures and semantics.

### `ContractRegistry`

Purpose: resolve contract metadata from registry-relative paths and provide stage-scoped binding
views.

Required interface:

```
ContractRegistry.load(contracts_root: Path) -> ContractRegistry
  - Loads the run-bundle registry instance at `docs/contracts/contract_registry.json`

ContractRegistry.load_workspace(contracts_root: Path) -> ContractRegistry
  - Loads the workspace-root registry instance at `docs/contracts/workspace_contract_registry.json`.
  
ContractRegistry.resolve(artifact_path: str) -> ResolvedContract | None
  - Returns None if no binding matches artifact_path.
  - Returns ResolvedContract if exactly one binding matches.

ContractRegistry.bindings_for_stage(stage_id: str) -> list[Binding]
  - Returns all bindings with stage_owner == stage_id.

ContractRegistry.contract_entry(contract_id: str) -> ContractEntry
  - MUST fail closed if contract_id is unknown.
```

Resolved contract shape (normative):

```
ResolvedContract:
  contract_id: str
  contract_version: str
  schema_path: str
  validation_mode: str
  stage_owner: str
  artifact_glob: str
```

Error handling (normative):

- `ContractRegistry.load(...)` MUST fail closed if:

  - the registry file is missing
  - the registry file is invalid JSON
  - the registry file is schema-invalid
  - any `artifact_glob` is invalid
  - any binding references an unknown `contract_id`
  - any `(contract_id, contract_version, schema_path)` inconsistencies exist
  - any `yaml_document` binding violates the YAML ingress-only invariants (see “YAML validation mode
    policy (ingress-only; v0.1)”)

### `PublishGate` and `StagePublishSession`

Purpose: provide transaction-like artifact publication: stage writes are staged, validated, and then
atomically promoted.

Required interface (minimum):

```
PublishGate.begin_stage(stage_id: str) -> StagePublishSession

StagePublishSession.write_bytes(artifact_path: str, data: bytes) -> None

StagePublishSession.write_json(artifact_path: str, obj: Any, canonical: bool = true) -> None

StagePublishSession.write_jsonl(artifact_path: str, rows_iterable: Iterable[Any]) -> None

StagePublishSession.finalize(
  expected_outputs: list[ExpectedOutput],
  unexpected_outputs_policy: str = "lenient"
) -> PublishResult

StagePublishSession.abort() -> None
```

ExpectedOutput shape (normative):

```
ExpectedOutput:
  artifact_path: str
  contract_id: str | null
  required: bool   # MUST be explicitly set; MUST NOT rely on defaults
```

ExpectedOutput ↔ registry consistency (normative):

- If `ContractRegistry.resolve(artifact_path)` returns a binding, then:
  - `ExpectedOutput.contract_id` MUST be non-null, and
  - it MUST equal the binding’s `contract_id`.
- If `ContractRegistry.resolve(artifact_path)` returns `None`, then `ExpectedOutput.contract_id`
  MUST be `null`.
- `finalize()` MUST fail closed (no promotion) if these invariants are violated.

PublishResult shape (normative minimum):

```
PublishResult:
  unexpected_outputs: list[str]        # run-relative; sorted
  missing_required_outputs: list[str]  # run-relative; sorted
  # Implementation MAY include additional fields (for example published_paths).
```

Publish-gate staging layout (normative):

- Stage outputs MUST be written under:

  - `runs/<run_id>/.staging/<stage_id>/...`

- `.staging/` is a reserved, non-contracted scratch area:

  - `.staging/` MUST NOT be referenced by contracted evidence pointers (`evidence_refs[]`).
  - `.staging/` MUST be excluded from signing/checksumming inputs.

Output-root guardrail (normative):

- A stage MUST NOT write or promote any run-bundle output outside its declared output roots (see
  `020_architecture.md`, "Stage IO boundaries").
- Violations MUST fail closed and MUST NOT promote any staged outputs.

Deterministic stage → contract-backed outputs (normative):

- `bindings[].stage_owner` is the source of truth for which stage owns contract-backed artifacts.

- The stage wrapper / orchestrator MUST construct the binding-derived `expected_outputs[]` list for
  `finalize()` as follows:

  1. Filter `bindings[]` to entries where `stage_owner == stage_id`.
  1. For each binding, compute the concrete `artifact_path` set:
     - If `artifact_glob` contains no glob metacharacters, the set is the single literal path
       `artifact_glob` (even if no staged file exists yet).
     - Otherwise, expand `artifact_glob` over the stage’s staged file set under
       `runs/<run_id>/.staging/<stage_id>/` using `glob_v1` semantics.
       - Expansion candidates are **regular files only**; directories are traversed but MUST NOT be
         returned as matches.
  1. For each concrete `artifact_path`, emit an `ExpectedOutput` with:
     - `artifact_path = <concrete artifact_path>`
     - `contract_id = <binding.contract_id>`
     - `required = output_required(stage_id, binding.contract_id, cfg)`
  1. Sort the resulting list by `artifact_path` ascending using the **Canonical ordering** defined
     in this document.
  1. De-duplicate:
     - If the same `artifact_path` appears more than once in the binding-derived list, tooling MUST
       fail closed (treat as an ambiguous registry configuration).

- Stages MAY append additional non-contract outputs by including `ExpectedOutput` entries with
  `contract_id=null`, but only for paths that do not match any registry binding.

Ownership invariant (normative):

- A stage MUST NOT publish any contract-backed output whose registry binding has
  `stage_owner != stage_id` (fail closed).

Finalize semantics (normative):

- `finalize()` MUST validate all contract-backed expected outputs (`contract_id != null`) using
  `ContractValidator` before any atomic promotion.
- If any required expected output (`required=true`) is missing, `finalize()` MUST fail closed and
  MUST NOT promote any staged outputs.
- Optional expected outputs (`required=false`) that are missing MUST NOT cause failure and MUST NOT
  be contract-validated.
- Staged file type constraints (fail closed):
  - Before validation and promotion, the publish gate MUST enumerate the staged output set under
    `runs/<run_id>/.staging/<stage_id>/`.
  - If any staged entry is not a regular file (for example a symlink, socket, FIFO, or device node),
    `finalize()` MUST fail closed and MUST NOT promote any staged outputs.
- Contract-backed artifacts MUST NOT be treated as "unexpected non-contract outputs":
  - Define `unexpected_outputs[]` as staged regular files that are not declared in
    `expected_outputs[]`.
  - If any unexpected staged file matches a registry binding (i.e., is contract-backed),
    `finalize()` MUST fail closed regardless of `unexpected_outputs_policy`.
- Deterministic promotion ordering:
  - When promotion occurs (both expected outputs and any lenient unexpected non-contract outputs),
    the publish gate MUST promote paths in ascending `artifact_path` order using the **Canonical
    ordering** defined in this document.
- Unexpected staged outputs MUST be handled according to `unexpected_outputs_policy`:
  - Define `unexpected_outputs[]` as staged regular files not declared in `expected_outputs[]`.
  - If `strict`: any unexpected output MUST fail closed (no promotion).
  - If `lenient`: unexpected outputs MUST be promoted (subject to output-root guardrail) and MUST be
    recorded in `PublishResult.unexpected_outputs`.
  - Unexpected outputs are treated as non-contract (no schema validation).
- Failure reporting:
  - When `finalize()` fails, the orchestrator MUST record a failed stage outcome (see ADR-0005) with
    a stable `reason_code`.
  - Publish-gate failure MUST be fail-closed with respect to artifact promotion: no final-path
    promotion may occur when validation fails.
  - Stage outcome `fail_mode` handling MUST follow the orchestrator’s configured `fail_mode` policy
    for that stage (see ADR-0005). The term "fail closed" in this document refers to publication
    behavior unless explicitly stated otherwise.

Atomicity scope (normative; v0.1):

- Atomicity MUST be defined per destination path (per run-relative artifact path).
- Atomicity is not required across multiple artifact paths.
- Stage-level durability is outcome-driven:
  - Contract-backed outputs MUST be treated as durable/published only when the terminal stage
    outcome has been recorded for that stage.
  - If a restart observes output/outcome mismatch, deterministic reconciliation rules apply (see
    ADR-0004).

Cleanup and hygiene (normative):

- After successful `finalize()`, the publish gate MUST delete (or leave empty)
  `runs/<run_id>/.staging/<stage_id>/` before returning.
- Once the run is terminal (success/partial/failed), `runs/<run_id>/.staging/` MUST be absent or
  empty.

### `ContractValidator`

Purpose: deterministic schema/contract validation for run-bundle artifacts.

Required interface (minimum):

```
ContractValidator.validate_artifact(
  artifact_path: str,
  contract_id: str,
  *,
  contracts_root: Path,
  run_bundle_root: Path
) -> ValidationResult

ContractValidator.validate_many(
  expected_outputs: list[ExpectedOutput],
  *,
  contracts_root: Path,
  run_bundle_root: Path
) -> ContractValidationReport
  - MUST ignore entries with contract_id == null.

ContractValidator.validate_file(
  bytes_or_path: bytes | Path,
  *,
  contract_id: str,
  validation_mode: str,
  schema_path: str,
  contracts_root: Path
) -> ValidationResult
```

ValidationResult (normative minimum):

```
ValidationResult:
  status: "valid" | "invalid"
  errors_truncated: bool
  errors: list[ContractValidationError]
```

ContractValidationError (normative):

- `artifact_path`: run-relative POSIX path

- `contract_id`: contract identifier

- `error_code`: OPTIONAL stable machine-readable token (`lower_snake_case`)

  - When the deterministic artifact path rule is violated, `error_code` MUST be
    `timestamped_filename_disallowed`.

- `instance_path`: JSON Pointer to failing instance location (`""` for document root)

- `schema_path`: JSON Pointer to failing schema location (`""` if unavailable, for example parse
  failure)

- `keyword`: OPTIONAL JSON Schema keyword that triggered the failure (example `required`, `type`)

- `message`: human-readable error message

- `line_number`: REQUIRED for JSONL validation errors and JSONL parse errors (1-indexed); omitted
  otherwise

Schema dialect and `$ref` constraints (normative):

- Validation MUST use JSON Schema Draft 2020-12.

- `$ref` MUST be local-only:

  - Implementations MUST NOT resolve remote references.
  - Implementations MUST fail closed if `$ref` attempts to escape the schema bundle root or
    otherwise violates the local-only policy.

Validation dispatch (normative):

- The validator MUST dispatch parsing/validation using the registry binding’s `validation_mode`.

JSONL parse failures (normative):

- If a JSONL line cannot be parsed as JSON, the validator MUST emit one error with:

  - `line_number` set to the failing line (1-indexed)
  - `instance_path=""`
  - `schema_path=""`
  - `keyword` omitted
  - `message` describing the parse error

Deterministic error ordering (normative):

- Errors MUST be sorted by this tuple using UTF-8 byte order (no locale):

  1. `artifact_path`
  1. `line_number` (treat missing as `0`)
  1. `instance_path`
  1. `schema_path`
  1. `keyword` (treat missing as empty string)
  1. `message`

Error caps (normative):

- A maximum error cap per artifact (`max_errors_per_artifact`) MUST be applied.
- Default cap MUST be `50` when not configured.
- The validator MUST compute the deterministic sort key for every encountered error (see
  "Deterministic error ordering") and MUST return the **first** `max_errors_per_artifact` errors in
  that sorted order.
- `errors_truncated` MUST be:
  - `false` if the total number of errors for the artifact is `<= max_errors_per_artifact`
  - `true` if the total number of errors for the artifact is `> max_errors_per_artifact`
- To ensure the "first N by sort order" selection is deterministic across validation engines and
  discovery orders, implementations SHOULD use an order-independent selection strategy, such as:
  - collect all errors, sort, then truncate; or
  - maintain a bounded heap of the smallest `N` errors by sort key, marking `errors_truncated=true`
    if any additional error would be excluded by the cap.

## Requiredness and expected output computation

### Requiredness function

Publish-gate requiredness MUST be computed mechanically from the effective run config:

- `stage_enabled(stage_id, cfg) -> bool`
- `output_required(stage_id, contract_id, cfg) -> bool`

Rules:

- If `stage_enabled(stage_id, cfg)` is `false`, `output_required(...)` MUST return `false`.

- Otherwise, `output_required(...)` MUST be derived from the stage’s required/optional/conditional
  sets:

  - `true` if contract_id is in `required_contract_ids_when_enabled`
  - `false` if in `optional_contract_ids_when_enabled`
  - `eval(required_if)` if in `conditional_required_contracts`

- If `contract_id` is not covered by any list for that stage, implementations MUST fail closed
  (spec/registry mismatch).

### Stage enablement matrix

- The canonical stage enablement matrix and `expr_v1` expression language are defined in
  `025_data_contracts.md`, "Stage enablement and required contract outputs (v0.1)".
- Contract Spine implementers MUST treat that matrix as the source of truth.

TODO: Optionally migrate the matrix into this document to eliminate duplication across specs once
downstream references are updated.

## Contract validation report

### When it is emitted

- When publish-gate contract validation fails, the system MUST persist a structured validation
  report.

### Location

- `runs/<run_id>/logs/contract_validation/<stage_id>.json`

### Minimum fields

ContractValidationReport MUST include:

- `run_id`

- `stage_id`

- `generated_at_utc`

- `max_errors_per_artifact`

- `artifacts[]`, where each entry includes:

  - `artifact_path`
  - `contract_id`
  - `contract_version`
  - `status` (`valid | invalid`)
  - `errors_truncated` (boolean)
  - `errors[]` (the deterministic, capped, sorted error list)

Canonical bytes (normative):

- The persisted report file MUST be serialized as Canonical JSON bytes (RFC 8785 / JCS):
  `canonical_json_bytes(ContractValidationReport)` (UTF-8, no BOM, no trailing newline).
- Canonical serialization makes the on-disk bytes deterministic **given a chosen report object** and
  ensures stable ordering across implementations.
- The report includes intentionally non-stable metadata fields (for example `generated_at_utc`);
  therefore, two executions are not required to produce byte-identical report files even when they
  detect the same validation failures.
- Semantic comparisons (CI fixtures, report diff tooling) MUST ignore `generated_at_utc`.
- Integrity artifacts (checksums/signing) MUST cover the report bytes exactly as persisted
  (including `generated_at_utc` when present).

Deterministic ordering (normative):

- `artifacts[]` MUST be sorted by `artifact_path` ascending using UTF-8 byte order (no locale).
- Each `errors[]` list MUST be sorted per "Deterministic error ordering".

Tier classification (normative):

- This report is a deterministic evidence log (Tier 0).

- When present, it MUST be included in:

  - default exports, and
  - `runs/<run_id>/security/checksums.txt` when signing is enabled

- `.staging/` MUST be excluded from default exports and from checksums/signing inputs.

## Deterministic artifact path rule

- All contracted artifacts under `runs/<run_id>/` MUST use stable, spec-defined paths and MUST NOT
  include timestamps in filenames.

- On violation, the contract validation report MUST include at least one error entry with:

  - `error_code="timestamped_filename_disallowed"`
  - `artifact_path` set to the offending run-relative path
  - `instance_path=""`, `schema_path=""`, `keyword` omitted

Timestamped exports (normative):

- If timestamped exports are needed for ad-hoc operator workflows, they MUST:

  - be written only under an explicitly non-contracted scratch area (RECOMMENDED:
    `runs/<run_id>/logs/scratch/`)
  - MUST NOT be referenced by contracted artifact lists or evidence refs
  - MUST NOT participate in hashing/signing/trending inputs

## Canonical serialization

### Canonical JSON

For contract-backed JSON artifacts:

- Canonical JSON bytes MUST follow RFC 8785 (JCS).

- `canonical_json_bytes(obj)` MUST output:

  - UTF-8 bytes
  - no BOM
  - no trailing newline

### JSONL physical format invariants

For contract-backed JSONL artifacts:

- Each line MUST be a single JSON object serialized as canonical JSON bytes (JCS).

- Lines MUST be joined with LF (`\n`) only. CRLF and CR MUST NOT be emitted.

- UTF-8 bytes MUST be used with no BOM.

- Blank lines MUST NOT be emitted.

- End-of-file newline rule:

  - if at least one row is written, the file MUST end with a trailing LF
  - if zero rows are written, the file MUST be zero bytes

### PublishGate writer restrictions (normative)

- For contract-backed JSON artifacts, `StagePublishSession.write_json(..., canonical=true)` MUST
  write exactly `canonical_json_bytes(obj)`.

- For contract-backed JSONL artifacts, `StagePublishSession.write_jsonl(rows_iterable)` MUST emit
  bytes obeying the JSONL invariants above.

- Stage cores MUST NOT use `write_bytes(...)` to publish contract-backed JSON or JSONL artifacts.

  - `write_bytes(...)` MAY be used for explicitly non-contracted artifacts under non-contracted
    locations such as `logs/scratch/`.

### YAML artifacts (ingress-only; v0.1)

YAML is permitted as an operator-/orchestrator-owned **ingress format** in v0.1.

Contract Spine rules (normative):

- `validation_mode="yaml_document"` defines validation parsing as YAML decoded into a JSON-shaped
  in-memory representation (`pa.yaml_decode.v1`) before JSON Schema validation.
- Canonical YAML byte emission is intentionally **unspecified** in v0.1.
  - Contract-backed YAML is restricted to orchestrator-owned ingress artifacts (see “YAML validation
    mode policy (ingress-only; v0.1)”).
  - Stages MUST NOT publish contract-backed outputs using `validation_mode="yaml_document"`.

Non-contract YAML artifacts (clarification):

- This policy does not prohibit `.yaml` files that are **not** contract-backed (for example byte
  snapshots of pinned upstream content).
- Any stage that emits YAML bytes MUST treat those artifacts as **opaque bytes**, not as a
  structured interstage seam. If an emitted YAML artifact is required to be deterministic and/or
  included in checksums/signing scope, its owning stage spec MUST define the byte-level determinism
  constraints (encoding, newline normalization, source basis). The Contract Spine does not define a
  global YAML emitter in v0.1.

#### YAML decode profile: `pa.yaml_decode.v1` (normative)

Purpose: ensure two conforming implementations decode the same YAML ingress bytes to the same
JSON-shaped value.

Parsing (normative):

- Input MUST be interpreted as UTF-8 text.
  - Implementations MAY accept a UTF-8 BOM but MUST strip it before parsing.
  - Invalid UTF-8 MUST fail closed.
- The parser MUST implement YAML 1.2.
- The parser MUST accept exactly one document; multiple documents MUST fail closed.
- The parser MUST use a safe loader (no arbitrary object construction).
- The parser MUST reject:
  - duplicate mapping keys (at any nesting level),
  - anchors and aliases,
  - merge keys (`<<`),
  - explicit tags other than the YAML 1.2 core JSON tags (`!!str`, `!!int`, `!!float`, `!!bool`,
    `!!null`).

Type resolution (normative):

- To avoid YAML 1.1 vs 1.2 drift, decoding MUST use YAML 1.2 JSON-schema-style resolution.
  - Example: `yes/no/on/off` MUST be interpreted as strings (unless explicitly tagged, and explicit
    non-JSON-native tags are rejected).

Normalization to JSON shape (normative):

After parsing, the decoded value MUST be representable using only JSON-native types:

- object/map with string keys only
- array
- string
- number (finite; NaN and ±Inf MUST fail closed)
- boolean
- null

If any node cannot be represented in this JSON shape, decoding MUST fail closed.

#### YAML semantic hash: `yaml_semantic_sha256_v1` (normative)

Where the pipeline records a semantic hash for a YAML ingress artifact (for example
`manifest.inputs.range_yaml_sha256`), it MUST compute:

```
yaml_semantic_sha256_v1(yaml_bytes):
  v = pa.yaml_decode.v1(yaml_bytes)          # JSON-shaped value (see above)
  b = canonical_json_bytes(v)                # RFC 8785 / JCS (see Canonical JSON)
  return sha256_hex(b)                       # lowercase hex
```

Notes:

- The semantic hash MUST be recorded in canonical digest string form: `sha256:<lowercase_hex>` (see
  `025_data_contracts.md`, "Canonical SHA-256 digest strings").
- Raw YAML bytes MAY still be preserved in the run bundle for auditability. The semantic hash is the
  deterministic basis for comparisons/trending that should ignore YAML formatting differences.

## Artifact Reader

This section defines the consumer-facing Contract Spine surface. It is aligned with `pa.reader.v1`
in `025_data_contracts.md`.

### `ReaderError`

`ReaderError` is the minimal, language-agnostic error envelope returned by `ArtifactReader` APIs. It
is intentionally a thin wrapper; the full stable error code vocabulary is defined by `pa.reader` in
`025_data_contracts.md`.

Normative minimum shape:

```
ReaderError:
  error_code: str
  message: str
  artifact_path: str | omitted
  details: object | omitted
  errors: list[ReaderError] | omitted
```

Rules (normative):

- `error_code` MUST be a stable machine-readable token (`lower_snake_case`).
- `message` MUST be human-readable and SHOULD be deterministic for equivalent inputs (avoid
  embedding absolute paths, hostnames, or timestamps).
- If `artifact_path` is present, it MUST be a run-relative POSIX path and MUST satisfy “Path
  requirements” / "Path normalization and reserved locations" in this document.
- If `details` is present, it MUST be JSON-serializable and MUST NOT include secrets. It SHOULD NOT
  include volatile values (timestamps, random IDs) unless explicitly marked as diagnostic-only.
- If `errors` is present:
  - it MUST be non-empty,
  - each entry MUST itself conform to this `ReaderError` shape, and
  - entries MUST be sorted per "Error ordering (normative)".

### Required interface

Purpose: discover a run bundle, classify artifacts, enforce reserved locations, and provide stable
error codes.

Required interface (minimum):

```
ArtifactReader.discover(input_path: Path) -> RunBundleHandle | ReaderError

ArtifactReader.inventory_json_bytes(run: RunBundleHandle) -> bytes | ReaderError
  - Returns the derived inventory view (`pa.inventory.v1`) as canonical JSON bytes.

ArtifactReader.open_validated(
  run: RunBundleHandle,
  artifact_path: str,
  *,
  required: bool = true,
  allow_quarantine: bool = false
) -> bytes | ReaderError
```

- `inventory_json_bytes` MUST implement the derived inventory semantics ("pa.inventory.v1") and MUST
  return byte-identical `canonical_json_bytes(...)` output for the same run bundle contents across
  conforming consumer implementations.

Notes:

- `open_validated` in v0.1 validates:

  - path normalization and reserved locations
  - evidence handling rules where applicable
  - optional integrity verification (checksums/signature) if the caller requests verification

- `open_validated` does not imply re-validating every artifact against its schema at read time;
  schema validation is a publish-gate responsibility and is surfaced via `logs/contract_validation/`
  reports.

### Canonical discovery

The discovery algorithm MUST follow `025_data_contracts.md` ("Canonical run bundle discovery").

Key requirements (normative):

- If input path contains `manifest.json`, it is the run bundle root.
- If input path contains `ground_truth.jsonl` but not `manifest.json`, discovery fails with
  `error_code="manifest_missing"`.
- If input path contains `runs/`, enumerate run candidates by UUID directory names and require
  `manifest.json` presence.
- Discovered run list MUST be sorted by `run_id` ascending using UTF-8 byte order (no locale).

### Path normalization and reserved locations

Path normalization (normative):

- The reader MUST reject any path that is absolute, contains backslashes, contains NUL, or contains
  any `..` segment after normalization.
- On violation, return `error_code="artifact_path_invalid"`.

Reserved scratch and quarantine (normative):

- `.staging/`:

  - MUST be excluded from inventory/hash sets
  - MUST return `error_code="artifact_in_staging"` if asked to open via an evidence ref

- Quarantine directory (`runs/<run_id>/<security.redaction.unredacted_dir>`, default `unredacted/`):

  - By default, the reader MUST deny reads and return `error_code="quarantine_access_denied"`.
  - Reads MAY be allowed only when caller explicitly opts in.

### Deterministic evidence vs volatile logs

- `runs/<run_id>/logs/` classification MUST follow ADR-0009 allowlist rules.
- Any `logs/` path not allowlisted as deterministic evidence MUST be treated as volatile
  diagnostics.

### Stable reader error codes

- Reader errors MUST follow `pa.reader` stable error code rules in `025_data_contracts.md`.

Required error codes (v1) include (non-exhaustive; see `025_data_contracts.md` for the full
normative list):

- `run_bundle_root_not_found`
- `manifest_missing`
- `manifest_parse_error`
- `manifest_schema_invalid`
- `contract_registry_missing`
- `contract_registry_parse_error`
- `artifact_path_invalid`
- `artifact_missing`
- `artifact_in_staging`
- `artifact_representation_conflict`
- `quarantine_access_denied`
- `version_pin_conflict`
- `contracts_version_incompatible`
- `schema_registry_version_incompatible`
- `checksums_parse_error`
- `checksum_mismatch`
- `signature_invalid`

Error ordering (normative):

- When multiple reader errors are returned, they MUST be sorted by:

  1. `error_code`
  1. `artifact_path` (missing as empty string)
  1. `message` using UTF-8 byte order (no locale)

## Failure taxonomy and observability

### Contract validation failures

Contract validation failures MUST be observable in all of the following:

1. Structured report:

   - `runs/<run_id>/logs/contract_validation/<stage_id>.json`

1. Stage outcome:

   - orchestrator MUST record a failed stage outcome (ADR-0005) for the publishing stage with a
     stable `reason_code`
   - `manifest.json` MUST reflect this in its stage outcomes
   - `logs/health.json` MUST mirror the stage outcomes when health emission is enabled

1. CI:

   - The Contract Spine gate MUST surface the failing stage id(s) and the report path(s)
   - The gate MUST fail deterministically (see "CI output requirements")

### Missing required outputs

- Missing required outputs MUST be treated as publish-gate validation failures:

  - `PublishResult.missing_required_outputs` MUST list missing run-relative paths (sorted).
  - No promotion may occur when missing required outputs exist.
  - The orchestrator MUST record the stage outcome as failed with a stable reason code (ADR-0005).

### Registry and configuration failures

Registry failures are configuration failures and MUST fail closed:

- Consumer surface:

  - `contract_registry_missing` or `contract_registry_parse_error` (`pa.reader`)

- Producer surface:

  - publish-gate MUST refuse to validate/publish
  - orchestrator MUST record a failed stage outcome using an appropriate ADR-0005 reason code
    (RECOMMENDED: `config_schema_invalid` when the failure is attributable to registry/schema
    misconfiguration)

### Recommended reason_code mapping

This table is non-authoritative guidance to reduce drift between Contract Spine implementations.
ADR-0005 remains the single authority for the `reason_code` registry and severity semantics;
implementations MUST NOT emit `reason_code` values that are not defined for the relevant stage in
ADR-0005.

| Contract Spine failure class | Trigger (examples)                                                                 | RECOMMENDED stage-outcome `reason_code`                                        | Notes                                                                                                |
| ---------------------------- | ---------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------- |
| Registry invalid             | Registry missing/parse error; `glob_v1` invalid; overlapping bindings; unknown ids | `config_schema_invalid`                                                        | Configuration failure; publish gate must refuse to validate/publish.                                 |
| Contract validation invalid  | Contract-backed artifact fails schema validation or parse                          | Stage-scoped contract-invalid reason code (example: `scoring_summary_invalid`) | TODO: align across stages in ADR-0005 (suggested cross-cutting: `contract_validation_failed`).       |
| Unexpected contracted output | Staged file matches a binding but is not declared in `expected_outputs[]`          | Same as "Contract validation invalid"                                          | Treat as a contract validation failure category (fail closed).                                       |
| Output-root violation        | Stage attempts to write/promote outside its declared output roots                  | `storage_io_error`                                                             | TODO: consider a dedicated policy-violation reason code in ADR-0005 (e.g., `output_root_violation`). |
| Non-regular file in staging  | Symlink/FIFO/socket/device node present under `.staging/<stage_id>/`               | `storage_io_error`                                                             | Fail closed; promote nothing.                                                                        |

### CI output requirements

Contract Spine gate output MUST be deterministic and MUST include:

- run id
- stage id (when applicable)
- the path to any contract validation report emitted
- a stable error summary ordered deterministically (use the error ordering rules above)

Exit codes:

- In Content CI, the Contract Spine gate MUST exit:
  - `0` on success
  - `20` on failure
- When Contract Spine conformance is enforced as part of run-bundle validation in Run CI, the
  overall CI verdict and exit-code mapping MUST follow ADR-0005 `(0|10|20)` (see
  `105_ci_operational_readiness.md`).

## Verification and CI conformance

### Contract Spine gate (Content CI)

The Contract Spine conformance check is a **gate within Content CI** (not a third CI lane).

Content CI MUST include the Contract Spine gate, and it MUST run before other Content CI checks.

Properties (normative):

- MUST be runnable without a lab provider (Content CI)

- MUST validate:

  - contract registry invariants
  - publish-gate and validator determinism rules
  - canonical serialization rules (JSON/JSONL)
  - contract validation report location and ordering
  - reader stable error codes and ordering
  - logs classification rules relevant to deterministic evidence (Tier 0 allowlist)

Recommended gate identifier: `contract_spine`. If a different identifier is used, it MUST be
documented in CI docs and referenced from here.

### Required conformance tests (minimum set)

The Contract Spine gate MUST include tests that cover at minimum:

- Contract registry invariants:
  - `stage_owner` present and within allowed set
  - `validation_mode` within allowed set
  - `artifact_glob` validity (`glob_v1`)
  - no ambiguous overlapping bindings
  - schema `contract_version` matches registry `contract_version`
  - YAML ingress-only invariants (v0.1):
    - any `yaml_document` binding MUST have `stage_owner == "orchestrator"`
    - any `yaml_document` binding MUST bind under `inputs/`
- Expected outputs determinism:
  - expansion is over staged regular files
  - stable sort by `artifact_path` (UTF-8 byte order)
  - requiredness function coverage fails closed if a stage omits a contract_id mapping
  - singleton glob behavior:
    - a binding with an `artifact_glob` containing no glob metacharacters is included in
      `expected_outputs[]` even when the file is missing in staging, and a missing `required=true`
      output fails closed (no promotion)
- Publish gate behavior:
  - validate-before-publish (no final-path writes on failure)
  - missing required outputs block promotion
  - strict vs lenient unexpected output policy semantics
  - `.staging/<stage_id>/` cleanup after success
  - staged file type constraints:
    - presence of a symlink (or other non-regular file) in `.staging/<stage_id>/` fails closed and
      promotes nothing
  - deterministic promotion order:
    - when multiple outputs are promoted, promotion occurs in canonical `artifact_path` order (allow
      deterministic crash/restart fixtures)
- Contract validation report:
  - written at `logs/contract_validation/<stage_id>.json` on validation failure
  - `artifacts[]` sorted by `artifact_path`
  - errors sorted by the specified tuple
  - per-artifact truncation is deterministic and reflected in `errors_truncated`
  - `generated_at_utc` is treated as volatile metadata and MUST be ignored by semantic comparisons
    (CI fixtures, report diff tooling)
  - deterministic artifact path rule yields `timestamped_filename_disallowed`
- Serialization:
  - canonical JSON bytes: UTF-8, no BOM, no trailing newline, JCS
  - JSONL invariants (line endings, trailing newline rule, no blank lines, JCS per line)
  - YAML ingress decoding (when `yaml_document` exists in the registry):
    - `pa.yaml_decode.v1` fixture vectors:
      - duplicate keys fail closed
      - anchors/aliases fail closed
      - merge keys (`<<`) fail closed
      - non-JSON-native tags/types fail closed
      - YAML 1.1 ambiguity vectors (`yes/no/on/off`) decode deterministically as strings
    - `yaml_semantic_sha256_v1` stability fixture:
      - two YAML inputs with identical semantics but different formatting/comments/newlines yield
        the same semantic hash
- Reader semantics:
  - run bundle discovery behavior and fallbacks
  - stable error code emission for required codes
  - `.staging/` access returns `artifact_in_staging`
  - quarantine default deny (`quarantine_access_denied`)
  - contract registry missing/parse errors surface as the correct error codes
  - derived inventory view:
    - `ArtifactReader.inventory_json_bytes` returns canonical JSON bytes and is byte-identical
      across conforming consumer implementations for the same run bundle

TODO: Align test identifiers and fixture paths with `100_test_strategy_ci.md` and ensure this gate
is explicitly referenced there.

## Security, export, and evidence classification

- `logs/contract_validation/` is Tier 0 deterministic evidence and MUST be included in default
  exports and checksums when signing is enabled.
- `logs/health.json` classification MUST follow ADR-0009 allowlist rules.
- Any `logs/` path not explicitly allowlisted as deterministic evidence MUST be treated as volatile
  diagnostics.
- `.staging/` MUST be excluded from:
  - evidence refs
  - signing/checksum inputs
  - default exports

## Versioning and compatibility

- Publisher semantics version: `pa.publisher.v1` (see `025_data_contracts.md`).
- Reader semantics version: `pa.reader.v1` (see `025_data_contracts.md`).
- Any change that can cause two conforming producers (or two conforming consumers) to disagree MUST
  bump the corresponding semantics version and MUST include explicit compatibility notes.

Contracts bundle distribution (historical validation) MUST follow `025_data_contracts.md`
("Contracts bundle distribution and retrieval for historical validation").

## Open items

- TODO: Decide whether to migrate `glob_v1` and the stage enablement matrix into this document (and
  update other docs to reference here) to eliminate duplication.
- TODO: If deterministic **contract-backed** YAML outputs become a real requirement, define a
  restricted canonical YAML emission profile (for example `pa.yaml_emit.v1`) and bump
  publisher/reader semantics as needed. Until then, `yaml_document` remains ingress-only in v0.1
  (orchestrator-owned `inputs/` bindings only).
- TODO: Define the exact CI gate wiring (job/step name) and ordering inside Content CI in
  `105_ci_operational_readiness.md` once CI manifests exist.

## Changelog

| Date      | Change                                                 |
| --------- | ------------------------------------------------------ |
| 2/10/2026 | Define ingress-only YAML policy + `pa.yaml_decode.v1`. |
| 2/09/2026 | Proposed                                               |
