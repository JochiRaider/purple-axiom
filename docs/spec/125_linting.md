---
title: Linting and schema tooling
description: Defines a single linting engine and report contract, plus per-artifact rule packs for schema-backed authoring, deterministic CI validation, and Operator Interface reuse.
status: draft
category: spec
tags: [linting, schema, authoring, determinism, ci, tooling]
related:

  - 020_architecture.md
  - 025_data_contracts.md
  - 026_contract_spine.md
  - 030_scenarios.md
  - 031_plan_execution_model.md
  - 060_detection_sigma.md
  - 080_reporting.md
  - 100_test_strategy_ci.md
  - 105_ci_operational_readiness.md
  - 115_operator_interface.md
  - 120_config_reference.md
  - ADR-0001-project-naming-and-versioning.md
  - ADR-0003-redaction-policy.md
  - ADR-0005-stage-outcomes-and-failure-classification.md
---

# Linting and schema tooling

## Overview

Linting is a cross-cutting concern that spans configuration inputs, scenario/plan authoring, rule
content, and report artifacts. Without a single lint contract, teams tend to re-implement parsing,
schema validation, naming rules, and reference resolution independently, leading to drift and
inconsistent CI behavior.

This document defines:

- A **single lint engine** contract used by CLI, CI, and the Operator Interface.
- A **single lint report contract** (`lint.json`) for machine-readable output.
- A **rule pack model** that encapsulates artifact-specific checks and prevents cross-cutting
  sprawl.
- Determinism, safety, and offline constraints for parsing, schema resolution, and output ordering.

## Version scope

- v0.1

  - CLI-first linting (`pa lint`) with a minimal default profile.
  - Initial rule packs focus on the highest-friction authoring artifacts: YAML config and scenario
    inputs.
  - Deterministic machine output for CI integration.

- v0.2 and later

  - Operator Interface reuse of the same lint engine and the same report contract.
  - Additional rule packs (for example plan drafts, Sigma rules, report linting) and richer editor
    tooling.

## Goals

- Provide **fast, deterministic, local-first** validation for authoring inputs.

- Establish a **single lint report contract** so CI and UI can consume results without bespoke
  adapters.

- Prevent "lint sprawl" by forcing artifact-specific logic into **rule packs**, not ad hoc checks.

- Enable **schema-backed authoring** including editor validation, autocomplete, and structural
  guidance.

- Enforce safety policies during linting:

  - **No secret disclosure** in output.
  - **No network fetch** or remote schema resolution.
  - **Fail closed** on ambiguous references and unsafe YAML constructs.

## Non-goals

- Auto-fixing or rewriting source files is out of scope for v0.1.
- Linting does not replace publish-gate contract validation for run-bundle artifacts.
- Linting is not a generic static analysis framework for arbitrary languages; it targets
  project-owned artifacts and formats.
- Remote enrichment (MITRE technique lookup, threat intel fetch, schema fetch) is not allowed in
  v0.1.

## Normative language

The key words MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY are to be interpreted as described in RFC
2119\.

## Terminology

- **Lint target**: A concrete artifact instance to lint (file path plus a declared or inferred
  `target_kind`).
- **Target kind**: A stable identifier that selects which rule pack(s) apply (for example
  `scenario`, `range-config`).
- **Rule pack**: A versioned bundle of lint rules for a target kind, optionally exposing profiles.
- **Profile**: A named selection of rules and severity thresholds within a rule pack (for example
  `default`, `ci-strict`).
- **Finding**: One lint issue (schema, semantics, reference, safety) produced by a rule.
- **Lint report**: Machine-readable output emitted by the lint engine, conforming to this spec.

## Authority and precedence

- Parsing and schema-validation invariants in this spec are intended to align with existing
  determinism and safety constraints.
- If a conflict is discovered between this document and an ADR, implementations MUST follow the ADR
  and the conflict MUST be resolved by updating this document.
- If a conflict is discovered between this document and an existing v0.1 spec that defines the
  relevant contract surface (for example `026_contract_spine.md` for `pa.yaml_decode.v1` or
  `080_reporting.md` for report HTML asset policy), implementations MUST follow the existing spec
  and the conflict MUST be resolved by updating this document.

## Lint engine contract

### Core responsibilities

The lint engine MUST:

1. Load targets (bytes) from disk under a workspace root.

1. Parse and normalize content using a deterministic, safe decoding profile.

1. Apply schema validation where schemas exist for the target kind.

1. Apply rule-pack semantic and reference checks.

1. Emit:

   - human-readable output suitable for terminal use, and
   - a machine-readable lint report (`lint.json`) conforming to the lint report contract.

The lint engine MUST NOT:

- Fetch remote resources (network calls).
- Resolve remote `$ref` in JSON Schema.
- Emit secrets into outputs.

### Lint target shape

A lint target MUST minimally include:

- `target_kind`: stable identifier, `id_slug_v1`
- `path`: workspace-relative POSIX path to a file

A lint target MAY include:

- `profile`: profile identifier (default is pack-defined)
- `options`: target-kind-specific configuration used only for linting (for example search roots)

### Rule pack model

Each rule pack MUST declare:

- `target_kind`: the kind it owns.

- `pack_id`: stable identifier (`id_slug_v1`).

- `pack_version`: SemVer (`semver_v1`).

- `profiles`: named profiles with:

  - enabled rule list, and
  - default severity mapping or thresholds.

Each rule MUST declare:

- `rule_id`: stable identifier (`id_slug_v1`).
- `description`: human-readable description.
- `default_severity`: `info | warning | error`.
- `determinism_contract`: statement of any required stable ordering or normalization inputs.

Rule IDs MUST be stable over time:

- A rule ID MUST NOT be re-used for a different check.
- If a rule is retired, it SHOULD remain recognized for backwards compatibility in report consumers.

### Pack registry

Implementations MUST provide a deterministic pack registry:

- The set of built-in rule packs MUST be versioned with the tool release.
- Rule pack discovery MUST be deterministic and MUST NOT depend on environment ordering (filesystem
  iteration order, locale, etc.).
- If user-configurable pack loading is introduced later, it MUST fail closed on ambiguity (multiple
  packs with the same `pack_id` and `pack_version`), unless the packs are byte-identical by hash. If
  byte-identical duplicates exist, the registry MUST select the first pack in deterministic
  discovery order.

## Determinism and safety invariants

### Offline operation

Linting MUST be local-first and MUST NOT require network access:

- Any lint rule that would normally consult an external registry MUST use a local snapshot artifact
  or MUST be disabled in v0.1.

### Path normalization

All file paths emitted in lint output MUST be:

- workspace-relative (never absolute host paths),
- POSIX-style with `/` separators (normalize `\` to `/`),
- normalized by:
  - removing any leading `./`,
  - removing `.` segments, and
  - rejecting any path that is empty, begins with `/`, contains a NUL byte, or contains a path
    segment equal to `..`.

Paths MUST be representable as Unicode and UTF-8 encodable.

If a target path is outside the workspace root (after normalization), linting MUST fail closed.

The lint engine MUST fail closed if a target path resolves to a symlink or any non-regular file
(directory, device node, FIFO, socket).

### Canonical ordering

Unless a rule explicitly specifies otherwise, the lint engine MUST sort:

- targets,
- findings,
- any lists within the machine report,

using **bytewise UTF-8 lexical ordering** (no locale).

### YAML decoding profile

For YAML targets, decoding MUST follow a single shared profile, `pa.yaml_decode.v1`, with these
invariants:

For YAML targets, decoding MUST implement the shared profile `pa.yaml_decode.v1` as defined in the
Contract Spine (`026_contract_spine.md`).

Invariants (normative):

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

- After parsing, the value MUST be representable using only JSON-native types:
  - object with string keys only
  - array
  - string
  - number (finite only; NaN/±Inf invalid)
  - boolean
  - null

If any invariant is violated, linting MUST fail closed and MUST emit a finding (see "Parse and tool
errors").

### JSON Schema validation profile

When schema validation is performed:

- Validation MUST use JSON Schema Draft 2020-12.
- `$ref` MUST be local-only:
  - Implementations MUST NOT resolve remote references.
  - Implementations MUST fail closed if `$ref` attempts to escape the schema bundle root or
    otherwise violates the local-only policy.

### Secrets and redaction safety

Lint output MUST be safe to store as CI artifacts and to render in UI:

- Findings MUST NOT include raw secret material.

- Any `details` emitted MUST be JSON-serializable and MUST NOT include secrets.

- If a rule detects sensitive content, it MUST report:

  - location and rule ID, and
  - a redaction-safe summary (for example "looks like an API key pattern"),
  - without including the matched value.

## CLI contract

### Command

The CLI entrypoint MUST be:

- `pa lint`

### Inputs

`pa lint` MUST accept:

- one or more file paths, and
- an optional explicit target kind.

Recommended CLI shape:

- `pa lint <path> [<path> ...]`
- `--target <target_kind>` optional; if omitted, the tool MAY infer target kind deterministically
  from path patterns.
- `--backend <backend_id>` optional; if provided, selects the backend profile used for
  backend-specific validation checks when linting `sigma-rule` targets. If omitted, the linter MUST
  use `detection.sigma.bridge.backend` from the provided config.

Inference MUST be deterministic and MUST fail closed if ambiguous:

- If multiple target kinds match a given file, `--target` MUST be required.

### Output behavior

The CLI MUST provide:

- Human-readable output to stdout or stderr.
- A machine-readable report:
  - default output path: `lint.json` in the current working directory, or
  - `--out <path>` to override.

The machine-readable report MUST be emitted even when lint fails, unless output cannot be written
(in which case the CLI MUST print a clear error and exit with code `20`).

### Exit codes

`pa lint` MUST use stable exit codes:

- `0`: no findings at or above the configured fail threshold
- `20`: at least one finding at or above the fail threshold, or tool failure that prevents
  successful lint completion

A configurable fail threshold MUST exist:

- `--fail-on {error,warning,info}`
- Default SHOULD be `error`.

## Lint report contract

### File name and format

The machine report MUST be RFC 8785 canonical JSON bytes (JCS), encoded as UTF-8 with no BOM and no
trailing newline.

The file is referred to as `lint.json` in this spec.

### Top-level fields

A lint report MUST be a JSON object with:

- `schema_version`: stable identifier for the lint report schema (MUST be `pa:lint-report:v1`)
- `tool`:
  - `name` (string)
  - `version` (string)
- `root`: workspace root used for path normalization (MUST be `"."` in v0.1)
- `targets`: array of lint targets (sorted by `target_kind`, then `path`, then `profile`)
- `summary`:
  - `status`: `pass | fail | tool_error`
  - `fail_on`: `error | warning | info`
  - `counts`: object with integer counts for each severity (`error`, `warning`, `info`)
- `findings`: array of findings (sorted)

`targets[].path` MUST be unique within a lint report.

Targets MUST be sorted by the tuple (`target_kind`, `path`, `profile`) using UTF-8 bytewise lexical
ordering (no locale). Missing `profile` is treated as empty string.

The report MUST NOT include volatile fields such as timestamps, random IDs, hostnames, or absolute
paths.

### Finding fields

Each finding MUST be a JSON object with:

- `file`: normalized workspace-relative POSIX path
- `instance_path`: JSON Pointer string to the relevant location
  - Use `""` for document root when the pointer is not available.
- `rule_id`: stable identifier (`id_slug_v1`)
- `severity`: `error | warning | info`
- `message`: human-readable summary, deterministic for equivalent inputs
- `details`: optional JSON object for structured metadata
  - MUST be redaction-safe
  - MUST NOT include secrets
- `help`: optional human guidance string

A finding MAY include:

- `location`:
  - `line` (1-indexed)
  - `column` (1-indexed)
  - These fields are informational and MUST NOT be required for stable ordering.

### Deterministic finding ordering

Findings MUST be sorted by the tuple:

1. `file`
1. `instance_path`
1. `rule_id`
1. `severity`
1. `message`

Comparison MUST be UTF-8 bytewise lexical ordering (no locale). Missing fields are treated as empty
string.

### Parse and tool errors

The lint engine MUST represent parse failures and tool failures without crashing:

- A YAML/JSON parse failure MUST emit a finding with:

  - `rule_id` set to a stable core rule (RECOMMENDED: `lint-core-parse-error`)
  - `severity="error"`
  - `instance_path=""`

- A tool-level failure that prevents lint completion MUST set:

  - `summary.status="tool_error"`
  - and MUST exit with code `20`

## Human output contract

Human output MUST be:

- deterministic in ordering,
- stable in formatting for a given tool version and input,
- free of secrets and absolute host paths.

Recommended minimum content:

- per-file header
- per-finding line with: severity, rule_id, instance path, message
- summary line with counts and exit condition

Color MAY be used when stdout is a TTY, but MUST be disableable via `--no-color`.

## Required target kinds and initial rule packs

This spec defines the mechanism; the concrete rule packs can be introduced incrementally. The
following target kinds are RECOMMENDED as the initial baseline:

### Target kind `range-config`

Intended for `inputs/range.yaml` and any config YAML that contributes to the effective run
configuration.

Minimum rule requirements:

- Safe YAML parsing per `pa.yaml_decode.v1`.
- Schema validation against the canonical config schema (range config schema).
- Prohibit direct secret material; enforce secrets-by-reference conventions.

### Target kind `scenario`

Intended for `inputs/scenario.yaml` and other scenario selection or scenario definition inputs.

Minimum rule requirements:

- Safe YAML parsing per `pa.yaml_decode.v1`.

- Structural validation against the scenario schema for the supported scenario model version.

- Semantic checks including:

  - identifiers and versions conform to project naming conventions,
  - plan selection is coherent with scenario type,
  - technique IDs match the expected format,
  - action identifiers are unique where required,
  - `principal_alias` is non-secret and stable.

Reference checks SHOULD be included when resolution rules are available:

- existence checks for referenced plans, rule packs, mappings, or supporting assets.

### Target kind `criteria-pack`

Intended for criteria pack authoring directories (repository packs under `criteria/packs/**` and run
snapshots under `criteria/`).

Minimum rule requirements:

- Detect missing required pack files:
  - `manifest.json`
  - `criteria.jsonl`
- If an authoring input is present (`criteria_authoring.yaml` or `criteria_authoring.csv`):
  - Reject ambiguous operator usage (unknown operator tokens; missing operator/value; numeric
    compare operators applied to non-numeric values; regex patterns that are not RE2-parseable).
  - Detect missing required columns/fields for the row model (see `035_validation_criteria.md`,
    "Authoring format and deterministic compilation").
  - Enforce the deterministic precedence rule: both authoring files MUST NOT be present at the same
    time.
- Enforce canonical ordering of the compiled criteria output:
  - `criteria.jsonl` line ordering,
  - `expected_signals[]` ordering,
  - `predicate.constraints[]` ordering, as defined in `035_validation_criteria.md`, "Canonical
    ordering for criteria.jsonl".

Required rule IDs (normative):

- `lint-criteria-pack-missing-required-files`
- `lint-criteria-pack-missing-required-columns`
- `lint-criteria-pack-ambiguous-operator`
- `lint-criteria-pack-canonical-ordering`
- `lint-criteria-pack-multiple-authoring-sources`

### Target kind `plan-draft`

Intended for `inputs/plan_draft.yaml` in v0.2+.

Minimum rule requirements:

- Safe YAML parsing per `pa.yaml_decode.v1`.
- Schema validation against the plan draft schema.
- Semantic checks:
  - stable action IDs,
  - required fields for plan intent and provenance,
  - reference existence checks for any referenced assets.

### Target kind `sigma-rule`

Intended for Sigma YAML rules.

Minimum rule requirements:

- Safe YAML parsing per `pa.yaml_decode.v1`.
- Sigma structural validity per the pinned Sigma tooling assumptions (at minimum, `id` and `title`).
- Deterministic rule discovery and hashing semantics aligned with the Sigma stage (canonical rule
  hashing per `060_detection_sigma.md`, "Canonical rule hashing").

Sigma parsing and resolution requirements (normative):

- The linter MUST classify each rule as an event rule (`SigmaRule`) or a correlation rule
  (`SigmaCorrelationRule`) and MUST parse it using the canonical parsing model defined in
  `060_detection_sigma.md` (TODO: add a stable section anchor, e.g. "Parsing model").

- The linter MUST parse to the canonical AST form (`sigma_ast_v1`) (TODO: defined in
  `060_detection_sigma.md`) for:

  - `SigmaRule.detection.condition` (including `x of`, pipe aggregation, and `near`).
  - `SigmaCorrelationRule.correlation` (including correlation type normalization and required-field
    presence checks).

- The linter MUST perform deterministic reference resolution checks:

  - `ref` identifiers MUST exist in the rule’s `detection` selector identifier set.
  - `x of <pattern>` expansions MUST be deterministic and MUST NOT be empty.
  - Correlation `rules` references MUST resolve within the lint input set (or configured pack
    scope). Missing or ambiguous references MUST be reported.

- If a backend profile is selected (for example via resolved config
  `detection.sigma.bridge.backend`), the linter MUST run backend-profile validation against the
  parsed `sigma_ast_v1` using configured backend restrictions (when present). Findings SHOULD map to
  the same non-executable `reason_code` values used by bridge compilation (see
  `065_sigma_to_ocsf_bridge.md`, "Non-executable classification mapping").

### Target kind `report-html`

Intended for generated HTML reports or report templates.

Minimum rule requirements:

- "No remote assets" rule: report HTML MUST comply with the Reporting spec's self-contained,
  local-only asset policy (`080_reporting.md`, "Self-contained, local-only asset policy").
  - The rendered HTML MUST NOT contain absolute `http://` or `https://` URLs in any attribute value.
  - The rendered HTML MUST NOT contain `<script` tags with a `src=` attribute or `<link` tags with
    an `href=` attribute.
  - The rendered HTML MUST NOT contain `<base` tags or `<meta http-equiv="refresh"`
    (case-insensitive).

## Schema publishing and editor integration

### Schema file location

Schemas used for linting SHOULD live alongside other project schemas under a single root
(RECOMMENDED: `docs/contracts/`), even if the artifact is not part of the run-bundle contract
registry.

### Schema identifiers

Each published JSON Schema file MUST:

- declare JSON Schema Draft 2020-12 meta-schema, and
- declare a stable `$id` identifier.

Recommended `$id` shape:

- `pa:schema:<name>:v<major>`

### Editor setup

The project SHOULD provide examples for editor integration, including:

- VS Code YAML schema mapping for `inputs/*.yaml` patterns.
- A mechanism for local-only schema paths (no network fetch).

See Appendix C.

## Operator Interface integration

When the Operator Interface is present:

- The UI MUST reuse the same lint engine and rule packs.
- The UI MUST consume the same `lint.json` schema shape, whether lint is invoked:
  - on-demand, or
  - on file save, or
  - as a pre-run validation step.

The UI MAY present additional UX affordances (grouping, filtering), but MUST NOT invent new rule IDs
or severities.

## Verification hooks

Implementations MUST provide tests that assert:

- Deterministic ordering of findings for a fixed input corpus.
- Stable exit codes for pass and fail cases.
- No network access is required (and preferably is actively blocked) during lint runs.
- YAML parsing rejects:
  - duplicate keys,
  - anchors/aliases,
  - merge keys,
  - multi-document YAML,
  - custom tags,
  - non-JSON-native scalar types.
- Criteria pack linting fixtures cover:
  - ambiguous operator usage,
  - canonical ordering violations, and
  - missing required columns/fields in authoring inputs.
- Machine report schema conformance:
  - `lint.json` validates against the lint report schema.
  - golden fixtures ignore no fields because the report MUST avoid volatile metadata by design.

Snapshot testing guidance:

- Maintain a small fixture corpus per target kind.
- Compare the emitted `lint.json` bytes directly (the report is canonical JSON bytes).

## Open items

- Define the canonical set of v0.1 rule packs shipped by default and their `pack_id` values.
- Decide whether lint report schemas are added to the contract registry or remain "tool output
  schemas".
- Specify reference resolution rules for scenario and plan assets once content pack layout is
  finalized.

## Appendix A: Example lint report

The JSON below is formatted for readability; emitted `lint.json` MUST be canonical JSON bytes as
specified above.

```json
{
  "schema_version": "pa:lint-report:v1",
  "tool": { "name": "pa", "version": "0.1.0" },
  "root": ".",
  "targets": [{ "target_kind": "scenario", "path": "inputs/scenario.yaml" }],
  "summary": {
    "status": "fail",
    "fail_on": "error",
    "counts": { "error": 2, "warning": 1, "info": 0 }
  },
  "findings": [
    {
      "file": "inputs/scenario.yaml",
      "instance_path": "/plan/technique_id",
      "rule_id": "lint-scenario-technique-id-format",
      "severity": "error",
      "message": "technique_id must match expected ATT&CK technique format (for example T1059 or T1059.001)",
      "details": { "observed": "1059" },
      "help": "Use the canonical technique ID format with the leading 'T'."
    }
  ]
}
```

## Appendix B: Rule ID conventions

Rule IDs MUST be `id_slug_v1`.

Recommended convention:

- `lint-<target_kind>-<short-name>`

Examples:

- `lint-core-parse-error`
- `lint-scenario-technique-id-format`
- `lint-range-config-schema-invalid`
- `lint-report-html-no-remote-assets`

## Appendix C: Editor configuration example

VS Code example mapping YAML schemas by file glob:

```json
{
  "yaml.schemas": {
    "./docs/contracts/range_config.schema.json": "inputs/range.yaml",
    "./docs/contracts/plan_draft.schema.json": "inputs/plan_draft.yaml",
    "./docs/contracts/scenario.schema.json": "inputs/scenario.yaml"
  }
}
```

## References

- [Architecture](020_architecture.md)
- [Data contracts](025_data_contracts.md)
- [Contract Spine](026_contract_spine.md)
- [Scenarios](030_scenarios.md)
- [Plan execution model](031_plan_execution_model.md)
- [Detection Sigma](060_detection_sigma.md)
- [Reporting](080_reporting.md)
- [Validation criteria packs](035_validation_criteria.md)
- [Test strategy and CI](100_test_strategy_ci.md)
- [CI operational readiness](105_ci_operational_readiness.md)
- [Operator Interface](115_operator_interface.md)
- [Configuration reference](120_config_reference.md)
- [ADR-0001: Project naming and versioning](../adr/ADR-0001-project-naming-and-versioning.md)
- [ADR-0003: Redaction policy](../adr/ADR-0003-redaction-policy.md)
- [ADR-0005: Stage outcomes and failure classification](../adr/ADR-0005-stage-outcomes-and-failure-classification.md)

## Changelog

| Date       | Change                                                                                                                                          |
| ---------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| 2026-02-11 | Refined draft: aligned to house style, added lint report contract, clarified determinism and safety invariants, added references and changelog. |
