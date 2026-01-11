<!-- docs/spec/032_atomic_red_team_executor_integration.md -->

# Atomic Red Team Executor Integration Contract (v0.1)

This document defines the normative integration contract between Purple Axiom and the
**Invoke-AtomicRedTeam** executor stack for `engine = "atomic"` actions.

It specifies:

- deterministic Atomic YAML parsing
- deterministic input resolution (defaults, overrides, template expansion)
- transcript capture and storage requirements (encoding, redaction, layout)
- cleanup invocation and cleanup verification workflow and artifacts

This contract is designed to make runs reproducible and cross-run comparable, while preserving
operator-debuggable evidence.

## Relationship to other specs

This document is additive and MUST be read alongside:

- `docs/spec/025_data_contracts.md` (hashing, `parameters.resolved_inputs_sha256`, run bundle
  layout, command integrity fields)
- `docs/spec/030_scenarios.md` (stable `action_key` basis, Atomic Test Plan scenarios)
- `docs/spec/035_validation_criteria.md` (cleanup verification semantics and reason codes)
- `docs/adr/ADR-0003-redaction-policy.md` (deterministic redaction requirements)

If this document conflicts with any of the above, the conflict MUST be resolved explicitly via a
spec patch (do not implement “best effort” divergence).

## Definitions

### Reference executor

For v0.1, the **reference executor** is the tuple:

- PowerShell runtime: **PowerShell 7.4.x** (pinned in `SUPPORTED_VERSIONS.md`)
- Invoke-AtomicRedTeam module: pinned exact version (pinned in `SUPPORTED_VERSIONS.md`)
- Atomic Red Team content: pinned reference (commit SHA, tag, or vendored content hash)

The runner MUST record these pins in run provenance (see “Runner evidence artifacts”).

### Atomic test identity

- `technique_id`: ATT&CK technique id (example: `T1059.001`)
- `engine_test_id`: Atomic test GUID (`auto_generated_guid`)

For v0.1 runner actions, `engine_test_id` MUST be present and MUST be used as the canonical Atomic
test identifier.

### Canonicalization token

`$ATOMICS_ROOT` is a literal token used only for **identity-bearing canonicalization**. It
represents environment-dependent Atomics payload roots and MUST NOT expand to a real path inside
identity-bearing materials.

## Contracted runner artifacts (filesystem layout)

Per-action evidence is stored under:

- `runs/<run_id>/runner/actions/<action_id>/`

The following files are RECOMMENDED by `docs/spec/045_storage_formats.md` and are REQUIRED by this
contract when the corresponding feature is enabled:

- `stdout.txt` (required when execution is attempted)
- `stderr.txt` (required when execution is attempted)
- `executor.json` (required for all attempted executions and cleanup runs)
- `attire.json` (required when Invoke-AtomicRedTeam structured logging is enabled, see below)
- `cleanup_stdout.txt` (required when cleanup is invoked)
- `cleanup_stderr.txt` (required when cleanup is invoked)
- `cleanup_verification.json` (required when cleanup verification is enabled)

The runner MUST also emit ground truth timeline entries as specified in
`docs/spec/025_data_contracts.md`.

## 1. Atomic YAML parsing (normative)

### 1.1 Technique discovery

Given a technique id `technique_id`, the runner MUST locate the Atomic YAML source as:

- `atomics/<technique_id>/<technique_id>.yaml`

If the file does not exist, the runner MUST fail closed for the action with reason code
`atomic_yaml_not_found`.

### 1.2 YAML parser requirements

The runner MUST parse Atomic YAML using a pinned implementation (as part of the reference executor).
Parsing MUST be deterministic for equivalent input bytes.

The parser MUST extract, at minimum, for each Atomic test:

- `technique_id` (from the technique selection context)
- `engine_test_id` = `auto_generated_guid`
- `name`
- `description` (if present)
- `supported_platforms` (if present)
- `executor.name` (executor type)
- `executor.command` (one or more command strings)
- `executor.cleanup_command` (optional, one or more command strings)
- `input_arguments` (optional object; keys and per-key `default` values when present)

If `auto_generated_guid` is missing or empty, the runner MUST fail closed with reason code
`missing_engine_test_id` unless the action is configured as `warn_and_skip` (in which case it MUST
emit `skipped` with reason code `missing_engine_test_id`).

### 1.3 Command list normalization

Atomic YAML may express commands as a scalar string or as a list. The runner MUST normalize both
`executor.command` and `executor.cleanup_command` into a list of strings:

- If scalar, normalize to a single-element list.
- If list, preserve list order exactly.
- Empty strings MUST be rejected (fail closed with reason code `empty_command`).

### 1.4 Supported platform gate

If `supported_platforms` is present, the runner MUST evaluate it against the target asset OS family.

- If the action’s target platform is not supported, the runner MUST emit `skipped` with reason code
  `unsupported_platform`.
- The runner MUST NOT attempt execution on unsupported platforms.

## 2. Input resolution (normative)

### 2.1 Precedence ladder

Input resolution MUST follow this precedence (highest to lowest):

1. Runner-supplied overrides (`-InputArgs` or an equivalent non-interactive injection mechanism)
1. YAML defaults (`input_arguments.<name>.default`)

Interactive prompting MUST NOT be used for unattended automation:

- The runner MUST NOT enable or rely on `-PromptForInputArgs`.
- If Invoke-AtomicRedTeam attempts to prompt due to missing required inputs, the runner MUST treat
  this as a failure and MUST fail closed with reason code `interactive_prompt_blocked`.

### 2.2 Required inputs (no defaults)

If an input argument key exists in YAML but has no `default` value:

- The runner MUST require an override value.
- If no override is provided, the runner MUST fail closed with reason code `missing_required_input`.

### 2.3 Template expansion rules

Template placeholders use the Atomic convention:

- Placeholder form: `#{<name>}`

The runner MUST perform placeholder substitution using the resolved input map:

- Substitution MUST be exact-match by placeholder name.

- Placeholder names MUST be treated as case-sensitive.

- The runner MUST validate that all placeholders used in `executor.command` and
  `executor.cleanup_command` reference keys present in the resolved input map.

  - If any placeholder cannot be resolved, the runner MUST fail closed with reason code
    `unresolved_placeholder`.

### 2.4 Resolved inputs fixed point

Resolved inputs MAY reference other inputs (example: a default value containing `#{other_arg}`).

To produce `resolved_inputs` deterministically, the runner MUST apply a fixed-point expansion:

1. Start from the precedence-merged input map (`merged_inputs`).

1. Iteratively substitute placeholders inside input values using the current map, until:

   - no value changes, or
   - `max_resolution_passes` is reached (v0.1 default: 8 passes)

1. If `max_resolution_passes` is reached and values are still changing, the runner MUST fail closed
   with reason code `input_resolution_cycle_or_growth`.

This algorithm MUST be deterministic for the same YAML bytes and the same override object.

### 2.5 Canonicalization of environment-dependent Atomics paths

Environment-dependent expansions MUST NOT participate in identity-bearing hashing.

For v0.1, the following expansions MUST be treated as evidence-only:

- `PathToAtomicsFolder`
- `$PathToPayloads` (and equivalent payload-root tokens used by Invoke-AtomicRedTeam)

When computing identity-bearing materials (including `parameters.resolved_inputs_sha256`), the
runner MUST canonicalize occurrences of these expansions by replacing them with the literal token:

- `$ATOMICS_ROOT`

This canonicalization applies to:

- resolved input values, and
- the canonical expanded command material (see Section 3)

The runner MUST record the actual expanded Atomics root path used for execution in `executor.json`
as evidence (see Section 4).

## 3. Identity-bearing hashes and command materials (normative)

### 3.1 `parameters.resolved_inputs_sha256` (required)

For `engine = "atomic"` actions, `parameters.resolved_inputs_sha256` MUST be computed as specified
in `docs/spec/025_data_contracts.md`:

- `sha256_hex( canonical_json_bytes(resolved_inputs_redacted_canonical) )`

Where `resolved_inputs_redacted_canonical` is:

- the resolved input map after:

  - precedence merge (Section 2.1)
  - fixed-point resolution (Section 2.4)
  - environment-dependent path canonicalization to `$ATOMICS_ROOT` (Section 2.5)
  - redaction (Section 3.2)

This hash MUST be computable without executing the Atomic test.

### 3.2 Redaction for hashing (required)

Before hashing `resolved_inputs`, the runner MUST apply deterministic redaction per
`docs/adr/ADR-0003-redaction-policy.md`:

- plaintext secrets MUST NOT be stored in run bundles

- secrets in `resolved_inputs` MUST be:

  - redacted deterministically, or
  - replaced with deterministic references (example: `secretref:<stable_id>`)

When redaction is enabled, the runner MUST record redaction provenance in ground truth extensions as
described in `docs/spec/025_data_contracts.md` and MUST ensure the run manifest includes:

- `redaction_policy_id`
- `redaction_policy_version`
- `redaction_policy_sha256`

### 3.3 Canonical expanded command boundary (required evidence)

To support operator debugging and cross-run comparability, the runner MUST compute and record a
**canonical expanded command** for both execution and cleanup:

- Boundary: command strings after placeholder substitution, but before executor-specific shell
  rewriting.

The runner MUST record:

- `command_post_merge` (list of strings, in order)
- `cleanup_command_post_merge` (list of strings, in order, if cleanup exists)

These command lists MUST apply `$ATOMICS_ROOT` canonicalization (Section 2.5).

These command lists MUST be recorded as evidence and MUST NOT be used as part of `action_key` unless
explicitly added to the action identity contract in `docs/spec/030_scenarios.md`.

### 3.4 Command integrity hash compatibility

`docs/spec/025_data_contracts.md` defines `extensions.command_sha256` as an OPTIONAL integrity hash
computed over a canonical `{executable, argv_redacted, ...}` object.

This document does not redefine that field.

If the runner emits an integrity hash for the canonical expanded command strings (Section 3.3), it
SHOULD use a separate field name to avoid conflicting semantics (example:
`extensions.command_post_merge_sha256`) and MUST document the basis object and redaction behavior.

## 4. Transcript capture and storage (normative)

### 4.1 Structured execution record (ATTiRe)

The runner MUST enable `Attire-ExecutionLogger` for Invoke-AtomicRedTeam executions and MUST capture
the structured output as an evidence artifact.

Storage requirement:

- The runner MUST store a per-action copy at:

  - `runs/<run_id>/runner/actions/<action_id>/attire.json`

Normalization requirement:

- The stored `attire.json` MUST be UTF-8 (no BOM) with LF newlines.
- If the upstream logger produces different newlines, the runner MUST normalize them
  deterministically when copying.

### 4.2 Stdout/stderr transcript files

For each attempted execution, the runner MUST store:

- `stdout.txt`
- `stderr.txt`

For each invoked cleanup, the runner MUST store:

- `cleanup_stdout.txt`
- `cleanup_stderr.txt`

Encoding and newline requirements (deterministic):

- Files MUST be UTF-8 without BOM.
- Newlines MUST be normalized to LF (`\n`) regardless of platform.
- The runner MUST NOT introduce an extra trailing newline that was not present in the captured
  content.

Capture semantics:

- The runner SHOULD capture process output as bytes and then apply deterministic decoding and
  normalization.
- Invalid UTF-8 sequences MUST be handled deterministically (example: decode with replacement using
  U+FFFD).

### 4.3 Redaction of transcripts

When `security.redaction.enabled: true` (or equivalent), the runner MUST apply the effective
redaction policy to transcripts before writing them.

- The run bundle MUST be redacted-safe by default.
- If redaction fails (example: cannot apply policy deterministically), the runner MUST fail closed
  for the affected action and MUST withhold the transcript artifacts (see ADR-0003 fail-closed
  behavior).

### 4.4 `executor.json` (required evidence)

For each attempted execution, the runner MUST write:

- `runs/<run_id>/runner/actions/<action_id>/executor.json`

Minimum required fields (v0.1):

- `executor` (string, normalized executor name)
- `pwsh_version` (string, exact)
- `invoke_atomicredteam_version` (string, exact)
- `started_at_utc` (RFC 3339 timestamp)
- `ended_at_utc` (RFC 3339 timestamp)
- `duration_ms` (integer)
- `exit_code` (integer)
- `atomics_root_actual` (string, evidence-only actual path)
- `command_shell_specific` (string or list of strings, evidence-only actual invocation form)

This file is evidence, not identity.

## 5. Cleanup invocation and verification (normative)

### 5.1 Cleanup invocation strategy

When `runner.atomic.cleanup.invoke: true`:

- The runner MUST invoke cleanup via `Invoke-AtomicTest -Cleanup` (not by executing
  `cleanup_command` directly).
- The runner MUST use the same `-InputArgs` and the same Atomics root configuration used for
  execution.

Rationale (normative): direct execution would require re-implementing Invoke-AtomicRedTeam
substitution and executor semantics, which is not allowed for the v0.1 reference executor.

### 5.2 Cleanup transcript capture

Cleanup invocation MUST capture transcripts and store them per Section 4.2.

### 5.3 Cleanup verification checks

When cleanup verification is enabled (see `docs/spec/035_validation_criteria.md`):

- The runner MUST execute the configured cleanup verification checks after cleanup completes.

- The runner MUST write results to:

  - `runs/<run_id>/runner/actions/<action_id>/cleanup_verification.json`

Result requirements:

- The file MUST be deterministic:

  - stable ordering of results by `check_id` ascending
  - stable ordering of any nested arrays by stable key (if present)

- Each result MUST include:

  - `check_id`
  - `type`
  - `target`
  - `status` (`pass | fail | indeterminate | skipped`)
  - `reason_code` (required)
  - `attempts`
  - `elapsed_ms`

Reason code mapping:

- For `pass | fail | indeterminate`, the runner MUST use the reason code mapping defined in
  `docs/spec/035_validation_criteria.md`.

- For `skipped`, the runner MUST use a stable reason code (minimum recommended set):

  - `unsupported_platform`
  - `insufficient_privileges`
  - `exec_error`
  - `disabled_by_policy`

### 5.4 Ground truth cleanup fields

Ground truth timeline entries for the action MUST reflect cleanup execution and verification
outcomes as specified by the ground truth contract in `docs/spec/025_data_contracts.md`, including a
reference to `cleanup_verification.json` when produced.

## 6. Failure modes and stage outcomes (normative)

Failures in this contract MUST be observable in:

- per-action ground truth status fields (where applicable)
- runner evidence files (where applicable)
- stage outcomes recorded in the run manifest per
  `ADR-0005-stage-outcomes-and-failure-classification.md`

At minimum, the runner MUST emit stable reason codes for these failure classes:

- `atomic_yaml_not_found`
- `atomic_yaml_parse_error`
- `missing_engine_test_id`
- `missing_required_input`
- `interactive_prompt_blocked`
- `unresolved_placeholder`
- `input_resolution_cycle_or_growth`
- `redaction_failed`
- `executor_invoke_error`
- `cleanup_invoke_error`
- `cleanup_verification_error`

## 7. Verification hooks (normative)

Implementations MUST include fixture-backed tests that validate:

1. YAML parsing determinism: same YAML bytes yield identical extracted fields.
1. Input resolution determinism: same YAML bytes plus same override object yield identical
   `resolved_inputs_redacted_canonical` and identical `parameters.resolved_inputs_sha256`.
1. Canonicalization: `$ATOMICS_ROOT` replacement is applied to identity-bearing materials and does
   not vary with actual filesystem paths.
1. Transcript normalization: newline normalization and encoding rules produce byte-identical outputs
   for equivalent captured content.
1. Cleanup verification determinism: result ordering and reason code requirements are stable.

CI SHOULD include a golden fixture conformance test that runs a pinned Atomic test twice with
identical inputs and asserts:

- identical `parameters.resolved_inputs_sha256`
- identical `action_key` (per `docs/spec/030_scenarios.md`)
- stable emission of required runner evidence files

Fixture selection and gating (unit vs integration) are defined in
`docs/spec/100_test_strategy_ci.md`.
