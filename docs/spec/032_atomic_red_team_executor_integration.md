---
title: Atomic Red Team executor integration contract
description: Defines the integration contract between Purple Axiom and Invoke-AtomicRedTeam for atomic actions.
status: draft
---

# Atomic Red Team executor integration contract

This document defines the normative integration contract between Purple Axiom and the
Invoke-AtomicRedTeam executor stack for `engine = "atomic"` actions. It specifies the following and
is designed to make runs reproducible and cross-run comparable while preserving operator-debuggable
evidence.

- Deterministic Atomic YAML parsing
- Deterministic input resolution (defaults, overrides, template expansion)
- Prerequisites (dependencies) evaluation and optional fetch workflow and evidence artifacts
- Transcript capture and storage requirements (encoding, redaction, layout)
- Cleanup invocation and cleanup verification workflow and artifacts

## Overview

This spec defines how the runner discovers and parses Atomic YAML, resolves inputs, canonicalizes
identity-bearing materials, evaluates prerequisites, captures transcripts, and records cleanup
verification. It sets the deterministic behavior, evidence artifacts, and failure modes needed for
cross-run comparability.

## Relationship to other specs

This document is additive and MUST be read alongside:

- [Data contracts spec](025_data_contracts.md) for hashing, `parameters.resolved_inputs_sha256`, run
  bundle layout, and command integrity fields
- [Scenario model spec](030_scenarios.md) for stable `action_key` basis and Atomic Test Plan
  scenarios
- [Validation criteria spec](035_validation_criteria.md) for cleanup verification semantics and
  reason codes
- [Redaction policy ADR](../adr/ADR-0003-redaction-policy.md) for deterministic redaction
  requirements

If this document conflicts with any of the above, the conflict MUST be resolved explicitly via a
spec patch (do not implement "best effort" divergence).

## Lifecycle phase mapping

Purple Axiom's action lifecycle is defined in the scenario model. For `engine = "atomic"` actions,
the runner MUST map Atomic semantics to lifecycle phases as follows:

| Atomic semantic                                         | Lifecycle phase | Notes                                                                                      |
| ------------------------------------------------------- | --------------- | ------------------------------------------------------------------------------------------ |
| Dependency evaluation (`check_prereq_command`)          | `prepare`       | Warm-up checks are `prepare` even when no changes are made.                                |
| Dependency fetch (`get_prereq_command`)                 | `prepare`       | Any prerequisite materialization is recorded as `prepare`.                                 |
| Primary command invocation (`executor.command`)         | `execute`       | The detonation attempt.                                                                    |
| Cleanup command invocation (`executor.cleanup_command`) | `revert`        | Undo detonation side-effects to enable a safe re-run.                                      |
| Cleanup verification (`cleanup_verification.json`)      | `teardown`      | Post-run verification. Teardown MAY also remove runner-created prereq artifacts when safe. |

Revert vs teardown (normative):

- The runner MUST record `revert` separately from `teardown`. `revert` exists to undo execute
  side-effects; `teardown` exists to remove per-action prerequisites (when applicable) and to record
  cleanup verification outcomes.
  - The runner MUST NOT attempt to uninstall or remove system-wide prerequisites by default (risk:
    deleting prerequisites shared by other techniques). Any prerequisite removal behavior MUST be
    explicit, opt-in, and deterministic.

Idempotence (normative):

- Unless the scenario/action descriptor explicitly declares otherwise, Atomic actions MUST default
  `idempotence` to `unknown`.
  - When `idempotence` is `unknown`, the runner MUST treat the action as `non_idempotent` for safety
    (do not assume it is safe to re-run without a successful `revert`).

## Definitions

### Reference executor

For v0.1, the **reference executor** is the tuple:

- PowerShell runtime: **PowerShell 7.4.6**
- Invoke-AtomicRedTeam module: pinned exact version
- Atomic Red Team content: pinned reference (commit SHA, tag, or vendored content hash)

The runner MUST record these pins in run provenance (see
[runner evidence artifacts](#contracted-runner-artifacts)).

### Atomic test identity

- `technique_id`: ATT&CK technique id (example: `T1059.001`)
- `engine_test_id`: Atomic test GUID (`auto_generated_guid`)

For v0.1 runner actions, `engine_test_id` MUST be present and MUST be used as the canonical Atomic
test identifier.

In v0.2+ plan compilation, the runner MUST compute a stable `template_id` for each Atomic action as:
`atomic/<technique_id>/<engine_test_id>`.

### Canonicalization token

`$ATOMICS_ROOT` is a literal token used only for **identity-bearing canonicalization**. It
represents environment-dependent Atomics payload roots and MUST NOT expand to a real path inside
identity-bearing materials.

## Contracted runner artifacts

Per-action evidence is stored under:

Action id semantics (normative):

- v0.1: `action_id` MUST be the legacy ordinal identifier `s<positive_integer>` (example: `s1`).

- v0.2+: `action_id` MUST be the deterministic action instance id defined in the
  [data contracts spec](025_data_contracts.md) and MUST match `pa_aid_v1_<32hex>`.

- `runs/<run_id>/runner/actions/<action_id>/`

The following files are RECOMMENDED by the [storage formats spec](045_storage_formats.md) and are
REQUIRED by this contract when the corresponding feature is enabled:

- `stdout.txt` (required when execution is attempted)
- `stderr.txt` (required when execution is attempted)
- `executor.json` (required for all attempted executions and cleanup runs)
- `prereqs_stdout.txt` (required when prerequisites are evaluated)
- `prereqs_stderr.txt` (required when prerequisites are evaluated)
- `attire.json` (required when Invoke-AtomicRedTeam structured logging is enabled, see below)
- `atomic_test_extracted.json` (required when Atomic template snapshotting is enabled, see
  [Atomic template snapshot](#atomic-template-snapshot))
- `atomic_test_source.yaml` (optional; see [Atomic template snapshot](#atomic-template-snapshot))
- `cleanup_stdout.txt` (required when cleanup is invoked)
- `cleanup_stderr.txt` (required when cleanup is invoked)
- `cleanup_verification.json` (required when cleanup verification is enabled)

The runner MUST also emit ground truth timeline entries as specified in the
[data contracts spec](025_data_contracts.md).

## Atomic YAML parsing

### Technique discovery

Given a technique id `technique_id`, the runner MUST locate the Atomic YAML source as:

- `atomics/<technique_id>/<technique_id>.yaml`

If the file does not exist, the runner MUST fail closed for the action with reason code
`atomic_yaml_not_found`.

### YAML parser requirements

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

### Atomic template snapshot

The runner MAY snapshot the Atomic test template material used for an action into the run bundle so
run review does not require a local checkout of the Atomic Red Team repository.

Config gate (normative):

- `runner.atomic.template_snapshot.mode` (string enum; v0.1 default: `off`)

Allowed values:

- `off`: do not write template snapshot artifacts.
- `extracted`: write `atomic_test_extracted.json` only.
- `source`: write both `atomic_test_extracted.json` and `atomic_test_source.yaml`.

Requirements (normative):

- When `runner.atomic.template_snapshot.mode` is `extracted` or `source`, the runner MUST write
  `atomic_test_extracted.json` for the selected Atomic test before attempting execution or
  prerequisites evaluation.
- When `runner.atomic.template_snapshot.mode` is `source`, the runner MUST also write
  `atomic_test_source.yaml` containing the YAML bytes for the selected Atomic test after newline
  normalization to LF.

Snapshot artifact paths:

- `runs/<run_id>/runner/actions/<action_id>/atomic_test_extracted.json`
- `runs/<run_id>/runner/actions/<action_id>/atomic_test_source.yaml` (mode=`source`)

`atomic_test_extracted.json` contents (minimum):

- `technique_id`
- `engine_test_id`
- `source_relpath` (example: `atomics/T1059.001/T1059.001.yaml`)
- `source_sha256` (sha256 of the exact bytes written to `atomic_test_source.yaml` when present;
  otherwise sha256 of the YAML bytes after deterministic newline normalization to LF)
- `name`
- `description` (if present)
- `supported_platforms` (if present)
- `executor` object:
  - `name`
  - `command` (list of strings; normalized per
    [Command list normalization](#command-list-normalization))
  - `cleanup_command` (optional list of strings; normalized per
    [Command list normalization](#command-list-normalization))
- `input_arguments` (optional object; keys and per-key `default` values when present)
- `dependencies` (optional array in YAML order), each with:
  - `description` (string or null)
  - `prereq_command` (list of strings; normalized per
    [Command list normalization](#command-list-normalization))
  - `get_prereq_command` (list of strings; normalized per
    [Command list normalization](#command-list-normalization))

Template snapshot scope:

- The runner MUST NOT perform input placeholder substitution when writing the snapshot artifacts.
  Snapshot artifacts represent the Atomic template, not the resolved command material.

Determinism requirements:

- Arrays MUST preserve YAML order.
- `atomic_test_extracted.json` MUST be serialized as RFC 8785 canonical JSON (JCS) bytes (UTF-8, no
  BOM, no trailing newline).
- `atomic_test_source.yaml` MUST be UTF-8 (no BOM) with LF newlines.

### Command list normalization

Atomic YAML may express commands as a scalar string or as a list. The runner MUST normalize both
`executor.command` and `executor.cleanup_command` into a list of strings. If `dependencies` are
present, the runner MUST also normalize `dependencies[].prereq_command` and
`dependencies[].get_prereq_command` into lists of strings using the same rules.

Normalized command-bearing fields (when present) MUST preserve list order exactly:

- If scalar, normalize to a single-element list.
- If list, preserve list order exactly.
- Empty strings MUST be rejected (fail closed with reason code `empty_command`).

### Supported platform gate

If `supported_platforms` is present, the runner MUST evaluate it against the target asset OS family
as resolved from the run-scoped inventory snapshot (see
[Inventory snapshot consumption](#inventory-snapshot-consumption)).

- If the action's target platform is not supported, the runner MUST emit `skipped` with reason code
  `unsupported_platform`.
- The runner MUST NOT attempt execution on unsupported platforms.

## Target resolution and remote execution

This section defines how the runner turns `target_asset_id` into a concrete connection address for
`engine = "atomic"` actions.

### Inventory snapshot consumption

For any `engine = "atomic"` action, the runner MUST resolve `target_asset_id` using the run-scoped
inventory snapshot produced by the lab provider stage (see the
[lab providers spec](015_lab_providers.md)).

Source of truth (v0.1):

- `runs/<run_id>/logs/lab_inventory_snapshot.json`

Resolution rules (normative):

1. Parse `lab_inventory_snapshot.json` as JSON.
1. Locate the target asset in `lab.assets[]` where `asset_id == target_asset_id`.
   - If no match exists, the runner MUST fail closed with reason code `target_asset_not_found`.
   - If multiple matches exist, the runner MUST fail closed with reason code
     `target_asset_id_not_unique`.
1. Determine `connection_address`:
   - If `ip` is present and non-empty, use `ip`.
   - Else if `hostname` is present and non-empty, use `hostname`.
   - Else the runner MUST fail closed with reason code `target_connection_address_missing`.

Determinism requirements:

- The `connection_address` selection MUST follow the fixed precedence above.
- The runner MUST NOT consult environment variables or provider APIs to resolve `connection_address`
  at execution time.
- `connection_address` is evidence-only and MUST NOT contribute to `action_key` or identity-bearing
  hashes.

Ground truth enrichment:

- The runner SHOULD populate `resolved_target.hostname`, `resolved_target.ip`, and
  `resolved_target.provider_asset_ref` in `ground_truth.jsonl` from the inventory snapshot per the
  [scenario model spec](030_scenarios.md).

### Invoke-AtomicRedTeam remote mapping

For remote Windows execution, the runner MUST translate `connection_address` into a PowerShell
remoting session and then execute `Invoke-AtomicTest` within that session:

- `connection_address` MUST map to `New-PSSession -ComputerName <connection_address>`.
- The created PSSession MUST be passed to `Invoke-AtomicTest` via `-Session <PSSession>`.

If a remoting session cannot be created, the runner MUST fail closed with reason code
`executor_invoke_error` (and SHOULD include error details in `stderr.txt` and `executor.json`).

## Input resolution

### Input resolution precedence

Input resolution MUST follow this precedence (highest to lowest):

1. Runner-supplied overrides (`-InputArgs` or an equivalent non-interactive injection mechanism)
1. YAML defaults (`input_arguments.<name>.default`)

Interactive prompting MUST NOT be used for unattended automation:

- The runner MUST NOT enable or rely on `-PromptForInputArgs`.
- If Invoke-AtomicRedTeam attempts to prompt due to missing required inputs, the runner MUST treat
  this as a failure and MUST fail closed with reason code `interactive_prompt_blocked`.

### Required inputs without defaults

If an input argument key exists in YAML but has no `default` value:

- The runner MUST require an override value.
- If no override is provided, the runner MUST fail closed with reason code `missing_required_input`.

### Template expansion rules

Template placeholders use the Atomic convention:

- Placeholder form: `#{<name>}`

The runner MUST perform placeholder substitution using the resolved input map:

- Substitution MUST be exact-match by placeholder name.
- Placeholder names MUST be treated as case-sensitive.
- The runner MUST validate that all placeholders used in `executor.command` and
  `executor.cleanup_command` (and, when present, `dependencies[].prereq_command` and
  `dependencies[].get_prereq_command`) reference keys present in the resolved input map.
  - If any placeholder cannot be resolved, the runner MUST fail closed with reason code
    `unresolved_placeholder`.

### Resolved input fixed point

Resolved inputs MAY reference other inputs (example: a default value containing `#{other_arg}`).

To produce `resolved_inputs` deterministically, the runner MUST apply a fixed-point expansion:

1. Start from the precedence-merged input map (`merged_inputs`).
1. Iteratively substitute placeholders inside input values using the current map, until:
   - no value changes, or
   - `max_resolution_passes` is reached (v0.1 default: 8 passes)
1. If `max_resolution_passes` is reached and values are still changing, the runner MUST fail closed
   with reason code `input_resolution_cycle_or_growth`.

This algorithm MUST be deterministic for the same YAML bytes and the same override object.

### Canonicalization of environment-dependent Atomics paths

Environment-dependent expansions MUST NOT participate in identity-bearing hashing.

For v0.1, the following expansions MUST be treated as evidence-only:

- `PathToAtomicsFolder`
- `$PathToPayloads` (and equivalent payload-root tokens used by Invoke-AtomicRedTeam)

When computing identity-bearing materials (including `parameters.resolved_inputs_sha256`), the
runner MUST canonicalize occurrences of these expansions by replacing them with the literal token:

- `$ATOMICS_ROOT`

This canonicalization applies to:

- resolved input values, and
- the canonical expanded command material (see
  [Canonical expanded command boundary](#canonical-expanded-command-boundary))

The runner MUST record the actual expanded Atomics root path used for execution in `executor.json`
as evidence (see [Executor evidence file](#executor-evidence-file)).

## Identity-bearing hashes and command materials

### Resolved inputs hash

For `engine = "atomic"` actions, `parameters.resolved_inputs_sha256` MUST be computed as specified
in the [data contracts spec](025_data_contracts.md):

- `sha256_hex(canonical_json_bytes(resolved_inputs_redacted_canonical))`

Where `resolved_inputs_redacted_canonical` is the resolved input map after:

- precedence merge (see [Input resolution precedence](#input-resolution-precedence))
- fixed-point resolution (see [Resolved input fixed point](#resolved-input-fixed-point))
- environment-dependent path canonicalization to `$ATOMICS_ROOT` (see
  [Canonicalization of environment-dependent Atomics paths](#canonicalization-of-environment-dependent-atomics-paths))
- redaction (see [Redaction for hashing](#redaction-for-hashing))

This hash MUST be computable without executing the Atomic test.

### Redaction for hashing

Before hashing `resolved_inputs`, the runner MUST apply deterministic redaction per the
[redaction policy ADR](../adr/ADR-0003-redaction-policy.md):

- plaintext secrets MUST NOT be stored in run bundles
- secrets in `resolved_inputs` MUST be:
  - redacted deterministically, or
  - replaced with deterministic references (example: `secretref:<stable_id>`)

When redaction is enabled, the runner MUST record redaction provenance in ground truth extensions as
described in the [data contracts spec](025_data_contracts.md) and MUST ensure the run manifest
includes:

- `redaction_policy_id`
- `redaction_policy_version`
- `redaction_policy_sha256`

### Canonical expanded command boundary

To support operator debugging and cross-run comparability, the runner MUST compute and record a
**canonical expanded command** for both execution and cleanup:

- Boundary: command strings after placeholder substitution, but before executor-specific shell
  rewriting.

The runner MUST record:

- `command_post_merge` (list of strings, in order)
- `cleanup_command_post_merge` (list of strings, in order, if cleanup exists)

These command lists MUST apply `$ATOMICS_ROOT` canonicalization, as described in
[Canonicalization of environment-dependent Atomics paths](#canonicalization-of-environment-dependent-atomics-paths).

These command lists MUST be recorded as evidence and MUST NOT be used as part of `action_key` unless
explicitly added to the action identity contract in the [scenario model spec](030_scenarios.md).

### Command integrity hash compatibility

The [data contracts spec](025_data_contracts.md) defines `extensions.command_sha256` as an OPTIONAL
integrity hash computed over a canonical `{executable, argv_redacted, ...}` object.

This document does not redefine that field.

If the runner emits an integrity hash for the canonical expanded command strings (see
[Canonical expanded command boundary](#canonical-expanded-command-boundary)), it SHOULD use a
separate field name to avoid conflicting semantics (example: `extensions.command_post_merge_sha256`)
and MUST document the basis object and redaction behavior.

## Prerequisites and dependencies

Atomic tests MAY declare prerequisites via a `dependencies` block. Each dependency commonly
includes:

- `prereq_command`: a command that checks whether a prerequisite is satisfied
- `get_prereq_command`: a command that attempts to satisfy the prerequisite (often by downloading or
  creating payloads)

### Responsibility model (normative)

- The runner MUST be capable of executing Atomic prerequisites for the selected test when
  `dependencies` are present.
- Lab Providers MAY pre-bake prerequisites into images, but the integration contract MUST NOT rely
  on pre-baking as the only mechanism.
- If prerequisites are not satisfied (and cannot be satisfied per policy), the runner MUST NOT
  attempt the Atomic execution and MUST fail closed for the action with a stable prereq reason code
  (see below).

### Prerequisites policy

The runner MUST expose a deterministic prerequisites policy. For v0.1, the policy is defined by:

- `runner.atomic.prereqs.mode` (string enum)

Allowed values:

- `skip`: do not check or fetch prerequisites; proceed directly to execution
- `check_only`: check prerequisites; if missing, do not execute
- `check_then_get`: check prerequisites; if missing, attempt `get_prereq_command` then re-check
- `get_only`: attempt `get_prereq_command` then check

Default (v0.1): `check_then_get`

Determinism requirements:

- The effective mode MUST be recorded in `executor.json`.
- Dependency processing order MUST match the YAML `dependencies[]` order exactly.
- Command normalization, input placeholder substitution, and `$ATOMICS_ROOT` canonicalization MUST
  be applied consistently to prerequisite commands using the same rules as for execution and cleanup
  commands.

### Prerequisites execution algorithm (normative)

When `dependencies` are present and `runner.atomic.prereqs.mode != skip`, the runner MUST perform:

1. For each dependency `d` in `dependencies[]` (in order):
   1. Execute the normalized `d.prereq_command` after placeholder substitution.
   1. If the prereq command indicates success (exit code `0`), mark the dependency `met` and
      continue.
   1. If the prereq command indicates failure (non-zero exit code):
      - If the effective mode does not include `get`, mark dependency `missing` and continue.
      - If the effective mode includes `get`:
        1. If `d.get_prereq_command` is missing or empty, the runner MUST fail closed with reason
           code `prereq_get_command_missing`.
        1. Execute the normalized `d.get_prereq_command` after placeholder substitution.
        1. Re-execute `d.prereq_command` (same rules as above).
        1. If re-check succeeds, mark dependency `met_after_get`; otherwise mark `missing`.
1. If any dependency is `missing`, the runner MUST NOT attempt the Atomic execution and MUST fail
   closed for the action with reason code `prereq_unsatisfied`.

Failure classification (normative):

- If a prereq check command cannot be executed (transport failure, timeout, runner internal error),
  the runner MUST fail closed with reason code `prereq_check_failed`.
- If a get prereq command cannot be executed (transport failure, timeout, runner internal error),
  the runner MUST fail closed with reason code `prereq_get_failed`.

### Prerequisites logs and evidence artifacts

When prerequisites are evaluated (`dependencies` present and `runner.atomic.prereqs.mode != skip`),
the runner MUST write:

- `runs/<run_id>/runner/actions/<action_id>/prereqs_stdout.txt`
- `runs/<run_id>/runner/actions/<action_id>/prereqs_stderr.txt`

These files MUST follow the same encoding/newline and redaction rules as other transcripts (see
[Stdout and stderr transcript files](#stdout-and-stderr-transcript-files) and
[Redaction of transcripts](#redaction-of-transcripts)).

To keep prereq logs machine-checkable and deterministic, the runner SHOULD prefix each prerequisite
command attempt with a delimiter line appended to `prereqs_stdout.txt`:

- `==> prereq[<i>/<n>] <phase>: <description>`

Where:

- `<i>` is 1-based index into `dependencies[]`
- `<n>` is total count of dependencies
- `<phase>` is one of `check`, `get`, `recheck`
- `<description>` is the dependency `description` after placeholder substitution (or a stable
  placeholder if absent)

### Executor evidence requirements (prereqs)

When prerequisites are evaluated, `executor.json` MUST include a `prereqs` object with, at minimum:

- `mode` (string; effective mode)
- `dependencies_count` (integer)
- `status` (`skipped | satisfied | unsatisfied | error`)
- `dependencies` (array in YAML order), each with:
  - `index` (1-based integer)
  - `description` (string; substituted)
  - `check_exit_code` (integer)
  - `get_attempted` (boolean)
  - `get_exit_code` (integer or null)
  - `recheck_exit_code` (integer or null)
  - `status` (`met | met_after_get | missing | error`)

## Transcript capture and storage

### Structured execution record (ATTiRe)

The runner MUST enable `Attire-ExecutionLogger` for Invoke-AtomicRedTeam executions and MUST capture
the structured output as an evidence artifact.

Storage requirement:

- The runner MUST store a per-action copy at:
  - `runs/<run_id>/runner/actions/<action_id>/attire.json`

Normalization requirement:

- The stored `attire.json` MUST be UTF-8 (no BOM) with LF newlines.
- If the upstream logger produces different newlines, the runner MUST normalize them
  deterministically when copying.

### Stdout and stderr transcript files

For each attempted execution, the runner MUST store:

- `stdout.txt`
- `stderr.txt`

For each invoked cleanup, the runner MUST store:

- `cleanup_stdout.txt`
- `cleanup_stderr.txt`

For each prerequisites evaluation (see
[Prerequisites and dependencies](#prerequisites-and-dependencies)), the runner MUST store:

- `prereqs_stdout.txt`
- `prereqs_stderr.txt`

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

### Redaction of transcripts

When `security.redaction.enabled: true` (or equivalent), the runner MUST apply the effective
redaction policy to transcripts before writing them.

- The run bundle MUST be redacted-safe by default.
- If redaction fails (example: cannot apply policy deterministically), the runner MUST fail closed
  for the affected action and MUST withhold the transcript artifacts (see the
  [redaction policy ADR](../adr/ADR-0003-redaction-policy.md) for fail-closed behavior).

### Executor evidence file

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
- `prereqs` (object, required when prerequisites are evaluated; see
  [Prerequisites and dependencies](#prerequisites-and-dependencies))

This file is evidence, not identity.

## Cleanup invocation and verification

### Cleanup invocation strategy

When `runner.atomic.cleanup.invoke: true`:

- The runner MUST invoke cleanup via `Invoke-AtomicTest -Cleanup` (not by executing
  `cleanup_command` directly).
- The runner MUST use the same `-InputArgs` and the same Atomics root configuration used for
  execution.

Rationale (normative): direct execution would require re-implementing Invoke-AtomicRedTeam
substitution and executor semantics, which is not allowed for the v0.1 reference executor.

### Cleanup transcript capture

Cleanup invocation MUST capture transcripts and store them per
[Stdout and stderr transcript files](#stdout-and-stderr-transcript-files).

### Cleanup verification checks

When cleanup verification is enabled (see the
[validation criteria spec](035_validation_criteria.md)):

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

- For `pass | fail | indeterminate`, the runner MUST use the reason code mapping defined in the
  [validation criteria spec](035_validation_criteria.md).
- For `skipped`, the runner MUST use a stable reason code (minimum recommended set):
  - `unsupported_platform`
  - `insufficient_privileges`
  - `exec_error`
  - `disabled_by_policy`

### Ground truth cleanup fields

Ground truth timeline entries for the action MUST reflect cleanup execution and verification
outcomes as specified by the ground truth contract in the
[data contracts spec](025_data_contracts.md), including a reference to `cleanup_verification.json`
when produced.

## Appendix: ATTiRe import mode (optional)

Some environments may execute Atomic tests outside Purple Axiom (for example, via a separate runner
wrapper) while still producing structured ATTiRe execution logs.

Implementations MAY support an "ATTiRe import" mode that ingests external structured execution
records and emits a run bundle that is contract-compatible with downstream stages.

If ATTiRe import mode is implemented (normative requirements):

- The runner MUST write a normalized per-action ATTiRe record to:
  - `runs/<run_id>/runner/actions/<action_id>/attire.json`
- The runner MUST derive `ground_truth.jsonl` entries from the imported `attire.json` using the same
  mapping rules as the execution path (timestamps, action identity fields, and executor status
  fields).
- The runner MUST NOT attempt to execute `Invoke-AtomicTest` when operating in import mode.
- `executor.json` MUST record that the action was imported (example field: `import_mode=true`) and
  MUST include a SHA-256 of the imported ATTiRe bytes after newline normalization (example field:
  `attire_sha256`).
- If the imported record is missing required fields, the runner MUST fail closed for the action with
  `reason_code=attire_import_error` and MUST preserve the raw import file only in a quarantined
  location (if configured).

This appendix does not require import mode for v0.1. When not enabled, `attire.json` is produced
only by the reference executor as specified in
[Structured execution record (ATTiRe)](#structured-execution-record-attire).

## Failure modes and stage outcomes

Failures in this contract MUST be observable in:

- per-action ground truth status fields (where applicable)
- runner evidence files (where applicable)
- stage outcomes recorded in the run manifest per the
  [stage outcomes ADR](../adr/ADR-0005-stage-outcomes-and-failure-classification.md)

At minimum, the runner MUST emit stable reason codes for these failure classes:

- `atomic_yaml_not_found`
- `atomic_yaml_parse_error`
- `attire_import_error` (only when ATTiRe import mode is enabled)
- `missing_engine_test_id`
- `missing_required_input`
- `interactive_prompt_blocked`
- `unresolved_placeholder`
- `input_resolution_cycle_or_growth`
- `prereq_check_failed`
- `prereq_get_failed`
- `prereq_get_command_missing`
- `prereq_unsatisfied`
- `redaction_failed`
- `executor_invoke_error`
- `cleanup_invoke_error`
- `cleanup_verification_error`
- `target_asset_not_found`
- `target_asset_id_not_unique`
- `target_connection_address_missing`

## Verification hooks

Implementations MUST include fixture-backed tests that validate:

1. YAML parsing determinism: same YAML bytes yield identical extracted fields.
1. Template snapshot determinism: when enabled, `atomic_test_extracted.json` and (if present)
   `atomic_test_source.yaml` are byte-stable for identical YAML bytes and the same pinned parser and
   normalizer versions.
1. Input resolution determinism: same YAML bytes plus same override object yield identical
   `resolved_inputs_redacted_canonical` and identical `parameters.resolved_inputs_sha256`.
1. Canonicalization: `$ATOMICS_ROOT` replacement is applied to identity-bearing materials and does
   not vary with actual filesystem paths.
1. Transcript normalization: newline normalization and encoding rules produce byte-identical outputs
   for equivalent captured content.
1. Prerequisites determinism: dependency order, logging artifacts, and prereq outcomes are stable
   for identical inputs.
1. Cleanup verification determinism: result ordering and reason code requirements are stable.

CI SHOULD include a golden fixture conformance test that runs a pinned Atomic test twice with
identical inputs and asserts:

- identical `parameters.resolved_inputs_sha256`
- identical `action_key` (per the [scenario model spec](030_scenarios.md))
- stable emission of required runner evidence files

Fixture selection and gating (unit vs integration) are defined in the
[test strategy and CI spec](100_test_strategy_ci.md).

## Key decisions

- Atomic YAML parsing, input resolution, and transcript handling are deterministic and
  evidence-backed for cross-run comparability.
- The runner canonicalizes environment-dependent Atomics paths to `$ATOMICS_ROOT` for
  identity-bearing materials.
- The runner is responsible for prerequisite evaluation and optional fetch, producing explicit
  prereq artifacts and structured prereq outcomes to avoid relying on lab image pre-baking
- Cleanup uses Invoke-AtomicTest semantics and records verification artifacts for post-run
  validation.
- Failure modes emit stable reason codes tied to ground truth and stage outcomes.

## References

- [Data contracts spec](025_data_contracts.md)
- [Scenario model spec](030_scenarios.md)
- [Validation criteria spec](035_validation_criteria.md)
- [Storage formats spec](045_storage_formats.md)
- [Test strategy and CI spec](100_test_strategy_ci.md)
- [Redaction policy ADR](../adr/ADR-0003-redaction-policy.md)
- [Stage outcomes ADR](../adr/ADR-0005-stage-outcomes-and-failure-classification.md)
- [Supported versions](../../SUPPORTED_VERSIONS.md)

## Changelog

| Date | Change                                       |
| ---- | -------------------------------------------- |
| TBD  | Style guide migration (no technical changes) |
