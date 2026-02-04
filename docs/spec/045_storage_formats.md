---
title: Storage formats
description: Defines storage tiers, formats, and schema evolution expectations for run artifacts.
status: draft
category: spec
tags: [storage, formats, artifacts, export, determinism, schema_evolution]
related:
  - 025_data_contracts.md
  - 040_telemetry_pipeline.md
  - 080_reporting.md
  - 086_detection_baseline_library.md
  - 090_security_safety.md
  - 110_operability.md
  - 120_config_reference.md
  - ../adr/ADR-0003-redaction-policy.md
  - ../adr/ADR-0005-stage-outcomes-and-failure-classification.md
  - ../adr/ADR-0009-run-export-policy-and-log-classification.md
---

# Storage formats

## Overview

This document defines how Purple Axiom writes run artifacts to disk, with a focus on long-term,
queryable storage. The default target for long-term event storage is Parquet.

The key principle is a two-tier model:

- Evidence tier: preserve source-native artifacts when they are valuable for fidelity and
  reprocessing.
- Analytics tier: store a structured, columnar representation (Parquet) for evaluation, scoring, and
  reporting.

Note: Tier 0 ("logs") is an operability surface and does not change the evidence vs analytics tier
model.

v0.1 policy (normative):

- The pipeline MUST NOT require native container exports. Pipeline correctness (normalization,
  detection evaluation, scoring, and reporting) MUST NOT depend on native container exports.
- Native container exports MAY be supported behind an explicit config gate, but docs SHOULD refer to
  them generically (or omit them entirely) until the capability is implemented.
- Any native container export feature MUST specify:
  - default-off behavior,
  - disk budget accounting semantics,
  - redaction and quarantine semantics, and
  - manifest and report disclosure requirements.

## Goals

- Use Parquet for long-term storage of event streams and large telemetry datasets.
- Keep artifacts queryable with Arrow-compatible tools (Python, DuckDB, Spark).
- Preserve enough fidelity to support reprocessing and debugging.
- Maintain deterministic outputs for diffability and regression testing.

## Non-goals

- Forcing every artifact type into Parquet. Small metadata artifacts remain JSON or JSONL by design.
- Treating debug logs as long-term storage. Debug logs are ephemeral.

## Storage tiers

Path notation (normative):

- In this document, `runs/<run_id>/...` is used as an illustrative on-disk prefix for run bundle
  locations.
- Any field that stores an artifact path (for example, `evidence_refs[].artifact_path`,
  `sidecar_ref`, `payload_overflow_ref`) MUST store a run-relative POSIX path (relative to the run
  bundle root) and MUST NOT include the `runs/<run_id>/` prefix.
  - Example run-relative paths: `manifest.json`, `inputs/baseline_run_ref.json`,
    `raw/evidence/blobs/wineventlog/<event_id_dir>/<field_path_hash>.xml`.

### No timestamped contracted filenames (normative)

- Contracted artifacts in Tier 1 and Tier 2 locations MUST have deterministic paths.
  - See the [data contracts specification](025_data_contracts.md) for the canonical "deterministic
    artifact path" rule.
- This rule applies equally to regression inputs and outputs (baseline references, delta reports).
- Timestamps belong inside artifact content, not in filenames.
- If an implementation generates timestamped scratch outputs, it MUST place them under a
  non-contracted, explicitly excluded directory, and MUST disclose the exclusion policy in
  operability docs or configuration.

### Publish-gate staging directories (normative; state machine integration hook)

- Stages that publish multi-file outputs MUST write those outputs under a stage-owned staging
  directory before publish:
  - `runs/<run_id>/.staging/<stage_id>/`
- `.staging/**` is non-contracted scratch space:
  - It MUST NOT be referenced by `evidence_refs[]` (or any other evidence pointer fields).
  - It MUST NOT be relied upon for pipeline correctness after publish.
- Stages MUST publish outputs using atomic replace semantics per final-path artifact
  (rename/replace), from `.staging/<stage_id>/` into the final contracted locations under
  `runs/<run_id>/` (see ADR-0004 and data contracts publish-gate rules). Atomicity is not required
  across multiple artifact paths.
- After a stage completes (success or failure), `.staging/<stage_id>/` SHOULD be absent or empty.
  Stages SHOULD remove the staging directory on exit (best-effort). CI MAY lint for any remaining
  `.staging/<stage_id>/**` entries as an incomplete publish-gate signal.

Note (non-normative): The existence (and eventual disappearance or emptiness) of
`.staging/<stage_id>/` provides a filesystem-observable integration point for lifecycle state
machines (ADR-0007).

### Regression baseline reference and outputs (v0.1; optional when enabled)

When regression comparison is enabled, the reporting stage MUST materialize a deterministic baseline
reference under the candidate run bundle and MUST compute regression results as part of reporting.
Baseline reference materialization and regression computation are owned by the reporting stage (see
the `reporting.regression_compare` health substage in ADR-0005). Other stages MUST treat any
pre-existing files under `inputs/**` as read-only; the baseline reference artifacts defined below
are write-once outputs of reporting and MUST NOT overwrite unrelated operator-provided inputs.

Timing (normative):

- Baseline reference materialization MUST occur during the reporting stage, in its staging area,
  before the reporting publish gate finalizes/publishes the run bundle. This ensures the baseline
  reference artifacts are atomically published with the run bundle and can be referenced by evidence
  pointers in `report/**`.

Baseline reference (v0.1; normative):

- Pointer form (REQUIRED when regression comparison is enabled):
  - `runs/<run_id>/inputs/baseline_run_ref.json`
    - A deterministic record of baseline selection and baseline manifest integrity (expected SHA-256
      digest string (`sha256:<lowercase_hex>`) for the baseline `manifest.json` bytes when
      readable).
- Snapshot form (RECOMMENDED when the baseline manifest bytes are readable; preferred for
  local-first portability):
  - `runs/<run_id>/inputs/baseline/manifest.json`
    - A byte-for-byte copy of the baseline run's `manifest.json` (no reformatting, no key
      reordering).

If both forms are present, they MUST be consistent (the referenced baseline manifest hash must match
the copied snapshot hash).

Regression comparison results MUST be recorded only in `runs/<run_id>/report/report.json` under the
`regression` object. Implementations MUST NOT produce standalone regression artifacts such as
`report/regression.json` or `report/regression_deltas.jsonl`.

Evidence references (normative):

- Any artifact field that carries an evidence pointer (for example `evidence_refs[].artifact_path`)
  MUST use a run-relative path that follows the deterministic layout rules in this document.
- Evidence paths MUST NOT be absolute paths and MUST NOT encode environment-specific prefixes.
- Regression-related evidence pointers SHOULD commonly reference:
  - `inputs/baseline_run_ref.json`
  - `inputs/baseline/manifest.json` (when present)
  - any missing or mismatched artifact paths that caused `baseline_incompatible` (for example, a
    required baseline or candidate artifact path referenced in the regression compare algorithm)

Verification hook (RECOMMENDED): CI SHOULD include a storage-format lint that fails if the
regression surface deviates from `report/report.json.regression` or uses timestamped filenames.

### Detection baseline packages (v0.1+; promoted CI artifact)

To support long-lived, lightweight “known-good” datasets for detection regression testing without
re-running labs, the system MUST support **Baseline Detection Packages (BDPs)** as a first-class
test artifact.

A BDP is a redaction-safe subset of a single completed run bundle containing only the artifacts
needed to evaluate detections (typically normalized OCSF events + ground truth), omitting heavy
evidence-tier artifacts (for example `raw/**`, `raw_parquet/**`, runner evidence). v0.1 CI
requirements (normative):

- A compliant implementation MUST make at least one pinned BDP available to Run CI as a replay
  substrate (see `105_ci_operational_readiness.md`).
- CI consumers MUST validate BDP integrity (manifest + checksums; signature when present) before
  using a BDP for evaluation.
- BDPs MUST be written under the reserved workspace exports root (for example
  `<workspace_root>/exports/baselines/<baseline_id>/<baseline_version>/`) and MUST NOT be placed
  under `runs/` because they are not run bundles.

See `086_detection_baseline_library.md` for the BDP format, lifecycle, and integrity rules. Operator
Interface expectations for managing baseline catalogs are v0.2+; v0.1 CI MAY consume BDPs from an
out-of-band artifact store as long as the on-disk format and integrity rules conform.

Recommended storage and formats (BDP profile `detection_eval_v1`):

- BDP manifest: JSON (canonical UTF-8) at `baseline_package_manifest.json`.
- Ground truth: JSONL at `run/ground_truth.jsonl` (same contract as run bundles).
- Normalized events: either Parquet dataset at `run/normalized/ocsf_events/` or JSONL at
  `run/normalized/ocsf_events.jsonl` (same logical artifact representation rules as run bundles).
- Integrity: `security/checksums.txt` (and optional Ed25519 signature/public key) following the
  standard checksums/signature rules used for shareable bundles.

### Tier 0: Operability logs (structured) and debug logs (ephemeral)

Location:

- `runs/<run_id>/logs/`

Format:

- Plain text (for example `run.log`)
- Structured JSON artifacts (for example health, validation summaries, and counters)

Retention:

- Debug text logs are short-lived and not used for scoring.
- Structured operability artifacts under `runs/<run_id>/logs/` that participate in CI gating or
  deterministic failure triage (for example `logs/health.json`, `logs/telemetry_validation.json`,
  and `logs/contract_validation/**` when present) SHOULD be retained with the run bundle for as long
  as the run bundle itself is retained.

Purpose:

- Operator visibility and deterministic failure triage.
- CI-facing evidence surfaces (stage outcomes, validation summaries), distinct from Tier 1 evidence
  and Tier 2 analytics datasets.

#### Tier 0 export classification: deterministic evidence vs volatile diagnostics (normative)

`runs/<run_id>/logs/` is intentionally a mixed directory. It contains:

- **Deterministic evidence**: small, structured artifacts required for reproducibility, CI gating,
  and deterministic failure triage. Deterministic evidence artifacts:
  - MUST be redaction-safe by construction (MUST NOT contain plaintext secrets).
  - MUST be included in default exports.
  - MUST be included in `security/checksums.txt` when signing is enabled (see the data contracts
    specification and ADR-0009).
- **Volatile diagnostics**: operator-local debug logs and runtime state (checkpoint databases,
  scratch files) that are not required for reproducibility and may contain environment-specific or
  sensitive information. Volatile diagnostics:
  - MUST be excluded from default exports.
  - MUST be excluded from `security/checksums.txt`.

Fail-closed rule (normative):

- Any artifact under `logs/` that is not explicitly classified as deterministic evidence below MUST
  be treated as volatile diagnostics.

Deterministic evidence under `logs/` (included in default export + checksums when present):

| Path (run-relative)                   | Format | Rationale                                                                                     |
| ------------------------------------- | ------ | --------------------------------------------------------------------------------------------- |
| `logs/health.json`                    | JSON   | Stage outcomes are the authoritative input to run status derivation and CI gating (ADR-0005). |
| `logs/telemetry_validation.json`      | JSON   | Deterministic telemetry validation summary and gap classification input (when enabled).       |
| `logs/counters.json`                  | JSON   | Run-scoped counters used for operability and deterministic triage (see operability spec).     |
| `logs/cache_provenance.json`          | JSON   | Cache usage provenance; required for reproducible cache-aware triage (when caching enabled).  |
| `logs/lab_inventory_snapshot.json`    | JSON   | Canonical lab inventory snapshot for reproducibility and diffability (lab provider output).   |
| `logs/lab_provider_connectivity.json` | JSON   | Provider connectivity canary evidence (optional when implemented; MUST NOT contain secrets).  |
| `logs/contract_validation/**`         | JSON   | Deterministic contract validation reports emitted on publish-gate failures.                   |

Volatile diagnostics under `logs/` (excluded from default export + checksums):

| Path (run-relative)             | Format | Rationale                                                                                                |
| ------------------------------- | ------ | -------------------------------------------------------------------------------------------------------- |
| `logs/run.log`                  | text   | Unstructured operator log; may contain environment-specific strings and MUST NOT be exported by default. |
| `logs/warnings.jsonl`           | JSONL  | Warning stream for operator visibility; not required for reproducibility.                                |
| `logs/eps_baseline.json`        | JSON   | Performance/resource baseline measurements; inherently environment-dependent and not used for scoring.   |
| `logs/telemetry_checkpoints/**` | files  | Receiver checkpoint state; runtime-only and restart-oriented.                                            |
| `logs/dedupe_index/**`          | files  | Normalization dedupe runtime index; runtime-only and restart-oriented.                                   |
| `logs/scratch/**`               | files  | Timestamped scratch outputs; explicitly non-contracted.                                                  |

Cross-reference (non-normative): ADR-0009 defines export and signing behavior for these classes.

### Tier 1: Evidence (source-native)

Location:

- `runs/<run_id>/raw/evidence/` (recommended convention)

Additional evidence location (runner artifacts):

- `runs/<run_id>/runner/`

Format:

- Source-native where it materially improves fidelity or reprocessing:
  - Windows Event Log raw payload captures (optional, see Windows section)
  - PCAP (if added later)
  - Tool-native output files
  - osquery results logs (NDJSON) preserved under `runs/<run_id>/raw/osquery/` (see the
    [osquery integration specification](042_osquery_integration.md))
  - Runner transcripts and executor metadata:
    - per-action stdout/stderr transcripts
    - terminal session recordings (asciinema `.cast`) (optional)
    - executor metadata (exit codes, durations, executor version)
    - cleanup verification results

Retention:

- Optional, policy-controlled (lab disk budgets vary).

Purpose:

- Max fidelity, reprocessing insurance, forensic traceability.

Runner evidence notes:

- Executor transcripts (stdout/stderr) and executor metadata are treated as Tier 1 evidence, not
  Tier 0 logs.
- Redaction is optional per run (see the [security and safety specification](090_security_safety.md)
  and [ADR-0003: Redaction policy](../adr/ADR-0003-redaction-policy.md)):
  - When `security.redaction.enabled: true`, transcripts MUST be redacted-safe prior to promotion
    into standard long-term artifacts.
  - When `security.redaction.enabled: false`, transcripts MUST be withheld from standard long-term
    artifacts unless explicitly written to a quarantined unredacted location.
- If transcripts cannot be made redacted-safe (fail-closed), they MUST be withheld and replaced with
  deterministic placeholders (policy provenance must still be recorded).
- Recommended per-action layout:
  - `runner/actions/<action_id>/stdout.txt`
  - `runner/actions/<action_id>/stderr.txt`
  - `runner/actions/<action_id>/terminal.cast` (optional; asciinema terminal session recording for
    human playback; MUST NOT be used for scoring)
  - `runner/actions/<action_id>/executor.json`
  - `runner/actions/<action_id>/resolved_inputs_redacted.json` (optional; redaction-safe resolved
    inputs basis used for `parameters.resolved_inputs_sha256`)
  - `runner/actions/<action_id>/side_effect_ledger.json`
  - `runner/actions/<action_id>/requirements_evaluation.json`
  - `runner/actions/<action_id>/state_reconciliation_report.json`
  - `runner/actions/<action_id>/attire.json` (optional; Atomic structured execution record)
  - `runner/actions/<action_id>/atomic_test_extracted.json` (optional; Atomic template snapshot)
  - `runner/actions/<action_id>/atomic_test_source.yaml` (optional; Atomic template snapshot)
  - `runner/actions/<action_id>/cleanup_verification.json`
- Executor-level evidence for defensible debugging when orchestration logs are incomplete.

Note (normative): The Tier 1 runner evidence paths listed above are contracted and MUST NOT be
timestamp-variant. Timestamped scratch outputs MUST NOT be written by inventing new filenames for
contracted artifacts. Note: see
[Atomic Red Team executor integration](032_atomic_red_team_executor_integration.md)

#### Side-effect ledger encoding and hashing (normative):

- `runner/actions/<action_id>/side_effect_ledger.json` is Tier 1 evidence and MUST be stored under
  the run bundle root (not under `logs/`).
- v0.1 defines the side-effect ledger at the per-action path above; no run-level rollup ledger path
  is contract-backed in v0.1.
- The ledger MUST be a valid JSON document after every write (crash-safe), and MUST use:
  - UTF-8 encoding
  - LF (`\n`) line endings
- Determinism requirements:
  - The ledger SHOULD be serialized using canonical JSON (RFC 8785 / JCS) to produce stable bytes.
  - The `entries[]` array order is authoritative and MUST follow the stable ordering rules defined
    in the data contracts spec (`seq` ascending with no gaps).
- Hash inventory requirements:
  - When signing is enabled, the ledger MUST be included in `security/checksums.txt` as a normal
    run-bundle file (see data contracts: long-term artifact selection for checksumming).
  - v0.1 does not require an additional `manifest.json` file-hash field for the ledger; integrity
    coverage is provided by `security/checksums.txt` when signing is enabled.

### Tier 2: Analytics (structured, long-term)

Location:

- `runs/<run_id>/raw_parquet/` and `runs/<run_id>/normalized/`

Format:

- Parquet for large datasets:
  - raw telemetry tables
  - normalized OCSF event store
  - joins and derived scoring tables (optional)

Retention:

- Long-term, used for evaluation, scoring, trending.

Purpose:

- Efficient queries, stable schemas, consistent downstream processing.

## Format selection by artifact type

### Always JSON (small, contract-driven)

- `manifest.json`
- `inputs/baseline_run_ref.json` (REQUIRED when regression comparison is enabled)
- `inputs/baseline/manifest.json` (optional; RECOMMENDED when baseline manifest bytes are readable)
- `inputs/telemetry_baseline_profile.json` (optional; telemetry baseline profile gate)
- `plan/expanded_graph.json` (v0.2+)
- `plan/expansion_manifest.json` (v0.2+)
- `plan/template_snapshot.json` (v0.2+; optional)
- `criteria/manifest.json`
- `scoring/summary.json`
- `normalized/mapping_profile_snapshot.json`
- `normalized/mapping_coverage.json`
- `bridge/coverage.json` (optional; when detection is enabled)
- `report/report.json`
- `report/thresholds.json`

Rationale:

- These are small, strongly typed, and designed to be human-readable and diffable.

### JSONL (small to medium, event-like but not huge)

- `ground_truth.jsonl`
- `plan/execution_log.jsonl` (v0.2+; optional)
- `criteria/criteria.jsonl`
- `criteria/results.jsonl`
- `detections/detections.jsonl`
- `scoring/joins.jsonl` (if used early)

Rationale:

- JSONL is simple, streamable, and contract-validated line-by-line.
- For large scale, these may also be promoted to Parquet, but JSONL remains the canonical
  interchange format.

### Parquet (long-term event streams)

Default:

- All log-like datasets intended for long-term storage are written as Parquet.

Examples:

- Raw telemetry emitted by collectors or ingestors (after minimal parsing):
  - Windows event data
  - Sysmon exports
  - Linux syslog or journald exports
  - osquery results (event format NDJSON; see the
    [osquery integration specification](042_osquery_integration.md))
- Normalized OCSF events
- Derived tables used in scoring (optional)

Rationale:

- Columnar compression and predicate pushdown make large-scale evaluation feasible on a single
  workstation.
- Parquet is broadly supported across the ecosystem.

## Parquet conventions

### Dataset naming

Within a run bundle, store Parquet datasets as directories with one or more Parquet files:

- `runs/<run_id>/raw_parquet/windows_eventlog/`
- `runs/<run_id>/raw_parquet/linux_syslog/`
- `runs/<run_id>/raw_parquet/osquery/`
- `runs/<run_id>/raw_parquet/pcap/` (reserved; capture/ingestion is not required for v0.1; any
  emission MUST be behind an explicit config gate)
- `runs/<run_id>/raw_parquet/netflow/` (reserved; capture/ingestion is not required for v0.1; any
  emission MUST be behind an explicit config gate)
- `runs/<run_id>/normalized/ocsf_events/`
- `runs/<run_id>/scoring/joins/` (optional)

### Partitioning strategy

Default (local-first, minimal complexity):

- Partition by `run_id` at the directory level (already implied by run bundle path).
- Within a run, avoid over-partitioning. Prefer fewer files with reasonable row group sizes.

Optional (when runs are large or you want faster filtering):

- Partition normalized OCSF events by:
  - `class_uid` (common filter in detection evaluation)
  - and optionally `date` (derived from event time, UTC)

Example:

- `normalized/ocsf_events/class_uid=1001/date=2026-01-04/part-0000.parquet`

### Compression

Default:

- Snappy (best compatibility, sufficient performance)

Optional:

- Zstd (better compression, good performance, verify tooling compatibility in your environment)

### Row group sizing

Guideline:

- Target row groups that are large enough for scan efficiency but not so large that local memory
  becomes a bottleneck.
- A practical starting point is row groups in the tens to low hundreds of MB range.

### Deterministic writing

To support reproducible diffs and regression tests:

- For any Parquet dataset that includes both `time` and `metadata.event_id` columns (notably
  `normalized/ocsf_events/`), writers MUST sort rows deterministically before write by:
  1. `time` ascending
  1. `metadata.event_id` ascending
- For Parquet datasets that do not include this tuple, writers SHOULD define an equivalent
  dataset-specific stable sort key (time-like column first, then a stable record identity column).
- Within any contracted Parquet dataset directory, writers MUST use deterministic, non-timestamped,
  non-random output filenames.
  - Filenames MUST NOT include UUIDs, timestamps, random salts, or process-derived IDs.
  - Recommended pattern: `part-0000.parquet`, `part-0001.parquet`, ... (zero-padded, monotonically
    increasing).
  - If partitioning is used (for example `class_uid=.../date=.../`), the deterministic filename rule
    applies within each leaf partition directory.

Notes:

- Deterministic ordering is an implementation requirement. Parquet itself does not guarantee row
  order semantics, but stable ordering improves repeatability and debugging.

## Sidecar blob store (payload overflow and binary extraction)

Purple Axiom uses a sidecar blob convention for payloads that are too large or unsuitable to inline
into Parquet (oversized XML, decoded binary fields).

When enabled:

- Sidecar payloads live under Tier 1 evidence:
  - `raw/evidence/blobs/wineventlog/`
- Sidecar objects MUST be addressed deterministically by:
  - `event_id_dir` (directory; filesystem-safe stable identifier derived from `metadata.event_id`)
  - `field_path_hash` (filename stem)

`event_id_dir` definition (normative):

- `metadata.event_id` values are not guaranteed to be filesystem-safe (for example, `:` is not a
  valid path character on Windows).
- Implementations MUST derive `event_id_dir` deterministically as the suffix of `metadata.event_id`
  after the final `:` character.
  - Example: `pa:eid:v1:0123456789abcdef0123456789abcdef` -> `0123456789abcdef0123456789abcdef`
- In v0.1, `event_id_dir` MUST be lowercase hex.

`field_path_hash` definition (normative):

- Let `field_path` be the canonical field path string that identifies the logical payload field (for
  example: `event_xml`, `raw.event_data.script_block_text`).
- `field_path` MUST be encoded as UTF-8 with no normalization.
- `field_path_hash = sha256_hex(UTF8(field_path))` as lowercase hex.
- Because `field_path_hash` is a filename stem, it MUST use `<lowercase_hex>` only (no `sha256:`
  prefix).

File extensions (normative):

- Writers SHOULD use a deterministic extension based on the payload encoding:
  - `.xml` for XML
  - `.json` for JSON
  - `.bin` for all other binary payloads

Examples:

- `raw/evidence/blobs/wineventlog/<event_id_dir>/<field_path_hash>.bin`
- `raw/evidence/blobs/wineventlog/<event_id_dir>/<field_path_hash>.xml`

Reference fields (normative):

- Parquet rows that externalize a payload to a sidecar object MUST carry enough reference metadata
  to retrieve and integrity-check the sidecar payload.
- Implementations MAY use either:
  - generic reference fields:
    - `sidecar_ref` (string; run-relative path under the run bundle root)
    - `sidecar_sha256` (string; `sha256:<lowercase_hex>` digest of the sidecar payload bytes), or
  - dataset-specific reference fields with identical semantics (for example `payload_overflow_ref` /
    `payload_overflow_sha256` in the raw Windows Event Log dataset).

If redaction is disabled (`security.redaction.enabled=false`), sidecar payload retention MUST follow
the same withhold/quarantine rules as other evidence-tier artifacts.

### Schema evolution

This section defines how Parquet-backed datasets evolve over time as:

- new OCSF fields are populated (additional columns),
- mapping profiles expand,
- field naming is corrected (rename-like changes), or
- types need to change.

#### Definitions

- **Dataset**: a Parquet dataset directory such as `normalized/ocsf_events/` or
  `raw_parquet/windows_eventlog/`.
- **Physical schema**: the column names and types stored in each Parquet file’s metadata.
- **Logical schema**: the query-facing expectation for a dataset (required columns plus optional
  columns).
- **Schema version**: a SemVer identifier for a dataset’s logical schema (not the Parquet format
  version).

#### Writer requirements (normative)

1. **Single-schema per dataset per run**

- Within a single run bundle, all Parquet files under a dataset directory MUST share the same
  physical schema.
  - Rationale: avoids per-run “schema merge” behavior that can be non-deterministic and expensive at
    read time.

2. **Additive evolution is the default**

- Adding columns is the preferred evolution mechanism.
- Newly introduced columns MUST be **nullable**.
- Writers MUST NOT rely on “column presence” to communicate meaning. Absence is treated as `NULL` on
  read.

3. **No in-place semantic changes**

- Writers MUST NOT change the meaning of an existing column name within the same schema MAJOR
  version.
- If semantics must change, the writer MUST introduce a new column name and deprecate the old one
  (see below).

4. **Type stability**

- Writers MUST NOT change the physical type of an existing column within the same schema MAJOR
  version.
- If a type change is necessary:
  - Preferred: **widening** changes (for example, `int32 -> int64`) while preserving meaning.
  - Otherwise: write to a new column name and deprecate the old one.

#### Rename policy (how to handle “field renamed” in practice)

Parquet itself is not a table format with first-class rename semantics. Purple Axiom therefore
treats “rename” as a compatibility pattern, not an in-place operation:

- A “rename” MUST be implemented as:
  1. add the new column name (nullable),
  1. mark the old column name as deprecated,
  1. provide an explicit alias mapping for readers (required; see `_schema.json` below).

During the deprecation window, writers SHOULD populate both:

- the new column, and
- the deprecated column (same value), unless doing so causes unacceptable storage overhead. If
  writers do not populate both, the alias mapping becomes mandatory for correctness of cross-run
  queries.

#### Required dataset schema snapshot (`_schema.json`)

To make historical runs queryable without guesswork, each Tier 2 Parquet dataset directory MUST
include a schema snapshot:

- Path: `runs/<run_id>/<dataset_dir>/_schema.json`
  - Example: `runs/<run_id>/normalized/ocsf_events/_schema.json`

The snapshot MUST be deterministic and MUST NOT include volatile fields (timestamps, hostnames,
random IDs).

Minimum fields (normative):

- `schema_id` (string)
  - Recommended: `pa.parquet.<dataset_kind>` (example: `pa.parquet.normalized.ocsf_events`)
- `schema_version` (string; SemVer)
- `columns` (array), each:
  - `name` (string; canonical dotted path, for example `metadata.event_id`)
  - `type` (string; Arrow-style scalar, for example `int64`, `string`, `timestamp_ms_utc`)
  - `nullable` (bool)
- `aliases` (object; optional but REQUIRED when any column has been deprecated/renamed)
  - Keys are canonical column names.
  - Values are ordered arrays of acceptable physical column names, most-preferred first.
  - Example:
    - `"actor.user.name": ["actor.user.name", "user.name"]`

Deterministic ordering (normative):

- `columns[]` MUST be sorted by `name` using bytewise UTF-8 lexical ordering (no locale,
  case-sensitive).
- Each `aliases[<key>]` list MUST be in deterministic preference order.

#### Querying historical runs (union + projection)

Consumers of run bundles SHOULD assume that older runs may:

- lack newly added columns (treat as `NULL`), and
- contain deprecated column names (resolve via aliases).

Requirements (normative for built-in query tooling):

- When scanning multiple Parquet files or multiple run bundles with potentially different schemas,
  the reader MUST use “union by name” semantics so missing columns become `NULL` instead of failing
  the scan.
- Readers SHOULD rely on column projection to only load the columns needed for the query.

Reference patterns (non-normative examples):

- DuckDB: `read_parquet(..., union_by_name=true)`
- Spark: enable schema merging when reading mutually compatible Parquet schemas.
- Arrow: unify fragment schemas into a dataset schema when needed.

#### Compatibility expectations for normalized OCSF datasets

- The “minimum required columns” listed below are **contract-critical** and MUST remain present and
  type-stable across all schema versions for `normalized/ocsf_events/`.
- New OCSF fields added over time MUST be introduced as additional nullable columns.

## Normalized OCSF Parquet schema (minimum required columns)

Even when the normalized store is Parquet, the same contract intent applies as the JSON schema
envelope.

Minimum required columns:

- `time` (int64, ms since epoch)
- `time_dt` (string, ISO-8601/RFC3339 UTC, e.g. `2026-01-08T14:30:00Z`)
  - `time_dt` MUST be a deterministic rendering of `time` (no locale; UTC only).
- `class_uid` (int32)
- `category_uid` (int32, nullable)
- `type_uid` (int32, nullable)
- `severity_id` (int32, nullable)

Provenance (required):

- `metadata.uid` (string)
  - `metadata.uid` MUST equal `metadata.event_id`.
- `metadata.event_id` (string)
- `metadata.identity_tier` (int32)
  - Allowed values: `1 | 2 | 3` (see ADR-0002).
- `metadata.run_id` (string, UUID)
  - `metadata.run_id` MUST validate as an RFC 4122 UUID (canonical hyphenated form).
- `metadata.scenario_id` (string)
- `metadata.collector_version` (string)
- `metadata.normalizer_version` (string)
- `metadata.source_type` (string)
- `metadata.source_event_id` (string, nullable)
- `metadata.ingest_time_utc` (timestamp_ms_utc, nullable)
  - When present, `metadata.ingest_time_utc` MUST be UTC.

Recommended convenience columns for evaluation:

- `device.hostname` (string, nullable)
- `actor.user.name` or equivalent (nullable)
- `actor.process.name` and `actor.process.pid` (nullable)

Permissive payload:

- Keep additional OCSF and vendor fields as additional Parquet columns where feasible.
- If a source produces highly variable nested structures, store a `raw_json` (string) column as a
  fallback, but prefer typed columns for fields used by detections.

## Windows Event Log storage (raw payload + Parquet)

Purple Axiom v0.1 treats OpenTelemetry LogRecords as the canonical transport for Windows Event Log
data. The pipeline MUST NOT assume that Windows-native binary event log container files are created
or retained.

### Default representation (normative)

Implementations MUST write a structured raw Windows Event Log Parquet table derived from the
collector output (example: the OpenTelemetry `windowseventlog` receiver).

The raw table SHOULD use stable columns. Recommended columns include:

- `time` (int64, ms since epoch, UTC)
- `channel` (string)
- `provider` (string)
- `event_id` (int32)
- `record_id` (int64)
- `computer` (string)
- `level` (int32, nullable)
- `keywords` (string, nullable)
- `task` (int32, nullable)
- `opcode` (int32, nullable)

Canonical raw payload (required):

- `event_xml` (string, nullable)
  - When present, `event_xml` MUST contain the (possibly truncated) Windows Event XML payload.
- `event_xml_sha256` (string, required)
  - SHA-256 digest string in `sha256:<lowercase_hex>` form computed over the full (untruncated)
    canonical XML payload bytes (UTF-8; CRLF normalized to LF).
- `event_xml_truncated` (bool, required)
- `payload_overflow_ref` (string, nullable; run-relative sidecar path when overflow is written)
- `payload_overflow_sha256` (string, nullable; `sha256:<lowercase_hex>` digest of the sidecar
  payload bytes)

Overflow constraints (normative):

- If `event_xml_truncated = true`, then `payload_overflow_ref` and `payload_overflow_sha256` MUST be
  present.
- If `event_xml_truncated = false`, then `payload_overflow_ref` and `payload_overflow_sha256` MUST
  be absent.
- When present, `payload_overflow_sha256` MUST equal `event_xml_sha256`.

Rendered message strings are non-authoritative:

- `rendered_message` MAY be stored as a nullable convenience column.
- Missing rendered messages (provider metadata/manifests unavailable) MUST NOT block ingestion or
  normalization.

### Raw payload sizing and sidecars (normative)

If the raw XML payload exceeds a configured maximum payload size:

- The writer MUST truncate `event_xml` (but MUST still compute `event_xml_sha256` over the full,
  untruncated canonical payload bytes).
- The writer MUST set `event_xml_truncated = true`.
- The writer MUST write the full payload to a deterministically addressed sidecar blob (see "Sidecar
  blob store") and set `payload_overflow_ref` and `payload_overflow_sha256`.
  - For Windows Event Log XML overflow, the canonical `field_path` for `field_path_hash` MUST be
    `event_xml`, and the sidecar file extension SHOULD be `.xml`.

### Optional: native container export (non-default)

If an implementation supports exporting Windows Event Log binary container files as additional
evidence:

- Export MUST be explicitly enabled by the operator (config-driven).
- Export MUST NOT be enabled by default, including for CI and "daily" runs.
- Export MUST be included in disk budget accounting:
  - Exported containers MUST count toward run-scoped raw storage budgets (for example:
    `max_raw_bytes_per_run`) and MUST be subject to the same fail-closed enforcement semantics as
    other raw artifacts.
- Exported containers MUST be treated as sensitive evidence (baseline redaction does not apply
  in-place).
- Export MUST define redaction and quarantine semantics:
  - If exported containers are not redaction-safe under the configured policy, they MUST be withheld
    from standard long-term artifact locations and MUST be written only to a quarantined unredacted
    location when explicitly allowed.
- The run manifest and report SHOULD indicate that unredacted binary evidence exists and where it is
  stored.

### Practical implementation options

Option A (default, using an OpenTelemetry receiver):

- Collect LogRecords from the receiver.
- Write the raw Windows Event Log Parquet table.
- Preserve canonical raw payloads (XML) inline or via sidecars per the sizing policy above.

Option B (optional, when binary containers are exported separately):

- Export binary containers as evidence-tier artifacts.
- Parse the exported containers into the same structured raw table and write Parquet.
- Do not treat rendered message plain text as canonical; the raw XML/system fields remain canonical.

## Linux and Unix log storage

Linux, Unix, and BSD logs are well-suited to Parquet, but only after minimal parsing into a
structured schema.

Suggested raw syslog Parquet columns:

- `time` (int64 ms)
- `host` (string)
- `app` (string)
- `pid` (int32, nullable)
- `facility` (string, nullable)
- `severity` (string, nullable)
- `message` (string)
- `raw` (string, nullable, for full original line)

For journald, prefer extracting structured fields into columns rather than storing only rendered
message text.

## When to keep raw text logs

Keep raw text logs only as:

- ephemeral debug output under `runs/<run_id>/logs/`
- or as evidence-tier when the source is inherently plain text (example: a tool only emits text)

If a plain text log is intended for long-term storage and repeated queries, parse it into a table
and store it as Parquet. You can retain the original line in a `raw` column if you want.

## Compaction and file counts

Local-first systems often generate many small Parquet files. This can slow down queries.

Recommendation:

- Write fewer, larger Parquet files per dataset per run when possible.
- Optionally implement a compaction step:
  - merge per-source shards into one file per dataset
  - preserve deterministic ordering
  - record compaction metadata in the manifest

## Reprocessing and provenance

To enable reprocessing:

- Preserve sufficient raw structured Parquet tables to re-run normalization and detection evaluation
  without re-running scenarios.
- If native container exports are retained, they are additional insurance, not a replacement for the
  structured raw tables.

The manifest should record:

- which datasets exist
- their hashes (or the hash of a checksums file)
- versions used to generate them

Signing and integrity provenance (normative if present):

- When `security.signing.enabled: true`, implementations SHOULD record the hash
  (`sha256:<lowercase_hex>`) of `security/checksums.txt` and signing metadata in `manifest.json`
  under `extensions.security.signing` (see `025_data_contracts.md`, "Recommended signing provenance
  in manifest.json").
- If any `extensions.security.signing.*` fields are recorded, they MUST match the emitted
  `security/checksums.txt`, `security/signature.ed25519`, and `security/public_key.ed25519` files.

Integrity recording note (v0.1):

- When signing is enabled, implementations SHOULD prefer recording the hash
  (`sha256:<lowercase_hex>`) of `security/checksums.txt` (and optional signature metadata) in
  `manifest.json` under an extensions namespace, consistent with the data contracts guidance.

## Decision matrix: native container exports vs Parquet

Use this table as the default decision logic:

- If your primary need is evaluation, scoring, and trending:

  - Parquet is required.
  - Native container exports are optional.

- If your primary need is maximal Windows-native fidelity and reprocessing:

  - Keep native container exports as evidence-tier.
  - Still write Parquet for analytics.

- If disk budget is tight:

  - Keep Parquet only.
  - Retain native container exports only for explicitly flagged runs.

This yields consistency across the storage system without losing the ability to preserve
high-fidelity Windows artifacts when needed.

## References

- [OSquery integration specification](042_osquery_integration.md)
- [Security and safety specification](090_security_safety.md)
- [Redaction policy ADR](../adr/ADR-0003-redaction-policy.md)

## Changelog

| Date       | Change                                                                                  |
| ---------- | --------------------------------------------------------------------------------------- |
| 2026-01-24 | Clarify `logs/` export classification (deterministic evidence vs volatile diagnostics). |
| 2026-01-21 | update                                                                                  |
