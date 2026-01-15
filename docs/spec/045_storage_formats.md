---
title: Storage formats
description: Defines storage tiers, formats, and schema evolution expectations for run artifacts.
status: draft
---

# Storage formats

This document defines how Purple Axiom writes run artifacts to disk, with a focus on long-term,
queryable storage. The default target for long-term event storage is Parquet.

The key principle is a two-tier model:

- Evidence tier: preserve source-native artifacts when they are valuable for fidelity and
  reprocessing.
- Analytics tier: store a structured, columnar representation (Parquet) for evaluation, scoring, and
  reporting.

## Goals

- Use Parquet for long-term storage of event streams and large telemetry datasets.
- Keep artifacts queryable with Arrow-compatible tools (Python, DuckDB, Spark).
- Preserve enough fidelity to support reprocessing and debugging.
- Maintain deterministic outputs for diffability and regression testing.

## Non-goals

- Forcing every artifact type into Parquet. Small metadata artifacts remain JSON or JSONL by design.
- Treating debug logs as long-term storage. Debug logs are ephemeral.

## Storage tiers

### Tier 0: Ephemeral operational logs

Location:

- `runs/<run_id>/logs/`

Format:

- Plain text (or structured JSON logs if preferred)

Retention:

- Short-lived. Not used for scoring, not considered authoritative evidence.

Purpose:

- Human debugging and operator visibility.

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
  - `runner/actions/<action_id>/executor.json`
  - `runner/actions/<action_id>/cleanup_verification.json`
- Executor-level evidence for defensible debugging when orchestration logs are incomplete.

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
- `criteria/manifest.json`
- `scoring/summary.json`
- `normalized/mapping_coverage.json`

Rationale:

- These are small, strongly typed, and designed to be human-readable and diffable.

### JSONL (small to medium, event-like but not huge)

- `ground_truth.jsonl`
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
- `runs/<run_id>/raw_parquet/syslog/`
- `runs/<run_id>/raw_parquet/osquery/`
- `runs/<run_id>/raw_parquet/pcap/` (placeholder contract; capture/ingestion is not required for
  v0.1)
- `runs/<run_id>/raw_parquet/netflow/` (placeholder contract; capture/ingestion is not required for
  v0.1)
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

- When writing Parquet within a run, sort rows deterministically before write:
  1. `time` ascending
  1. `metadata.event_id` ascending

Notes:

- Deterministic ordering is an implementation requirement. Parquet itself does not guarantee row
  order semantics, but stable ordering improves repeatability and debugging.

## Sidecar blob store (payload overflow and binary extraction)

Purple Axiom uses a sidecar blob convention for payloads that are too large or unsuitable to inline
into Parquet (oversized XML, decoded binary fields).

When enabled:

- Sidecar payloads live under Tier 1 evidence:
  - `runs/<run_id>/raw/evidence/blobs/wineventlog/`
- Sidecar objects MUST be addressed deterministically by:
  - `metadata.event_id` (directory)
  - `field_path_hash` (filename stem, SHA-256 of UTF-8 field path)

Example:

- `runs/<run_id>/raw/evidence/blobs/wineventlog/<metadata.event_id>/<field_path_hash>.bin`
- `runs/<run_id>/raw/evidence/blobs/wineventlog/<metadata.event_id>/<field_path_hash>.xml`

Parquet rows MUST carry enough reference metadata to retrieve the sidecar payload:

- `sidecar_ref` (string, relative path under the run bundle root)
- `sidecar_sha256` (string)

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

- `metadata.event_id` (string)
- `metadata.run_id` (string, UUID)
  - `metadata.run_id` MUST validate as an RFC 4122 UUID (canonical hyphenated form).
- `metadata.scenario_id` (string)
- `metadata.collector_version` (string)
- `metadata.normalizer_version` (string)
- `metadata.source_type` (string)
- `metadata.source_event_id` (string, nullable)
- `metadata.ingest_time_utc` (timestamp or string, nullable)

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
- `event_xml_sha256` (string, required)
- `event_xml_truncated` (bool, required)
- `payload_overflow_ref` (string, nullable; relative sidecar path when overflow is written)
- `payload_overflow_sha256` (string, nullable)

Rendered message strings are non-authoritative:

- `rendered_message` MAY be stored as a nullable convenience column.
- Missing rendered messages (provider metadata/manifests unavailable) MUST NOT block ingestion or
  normalization.

### Raw payload sizing and sidecars (normative)

If the raw XML payload exceeds a configured maximum payload size:

- The writer MUST truncate `event_xml`.
- The writer MUST set `event_xml_truncated = true`.
- The writer MUST write the full payload to a content-addressed sidecar blob and set
  `payload_overflow_ref` and `payload_overflow_sha256`.

### Optional: native container export (non-default)

If an implementation supports exporting Windows Event Log binary container files as additional
evidence:

- Export MUST be explicitly enabled by the operator (config-driven).
- Export MUST NOT be enabled by default, including for CI and "daily" runs.
- Exported containers MUST be treated as sensitive evidence (baseline redaction does not apply
  in-place).
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
- If native container exports are retained, they are additional insurance, not a replacement for the structured raw tables.

The manifest should record:

- which datasets exist
- their hashes (or the hash of a checksums file)
- versions used to generate them

## Decision matrix: native container exports vs Parquet

Use this table as the default decision logic:

- If your primary need is evaluation, scoring, and trending:

  - Parquet is required.
  - Native container exports is optional.

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

| Date       | Change            |
| ---------- | ----------------- |
| 2026-01-12 | Formatting update |
