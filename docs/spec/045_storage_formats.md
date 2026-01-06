<!-- docs/spec/045_storage_formats.md -->
# Storage formats

This document defines how Purple Axiom writes run artifacts to disk, with a focus on long-term, queryable storage. The default target for long-term event storage is Parquet.

The key principle is a two-tier model:
- Evidence tier: preserve source-native artifacts when they are valuable for fidelity and reprocessing.
- Analytics tier: store a structured, columnar representation (Parquet) for evaluation, scoring, and reporting.

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
  - Windows EVTX (optional, see Windows section)
  - PCAP (if added later)
  - Tool-native output files
  - Runner transcripts and executor metadata:
    - per-action stdout/stderr transcripts
    - executor metadata (exit codes, durations, executor version)
    - cleanup verification results
    
Retention:
- Optional, policy-controlled (lab disk budgets vary).

Purpose:
- Max fidelity, reprocessing insurance, forensic traceability.

Runner evidence notes:
- Executor transcripts (stdout/stderr) and executor metadata are treated as Tier 1 evidence, not Tier 0 logs.
- Redaction is optional per run (see `090_security_safety.md` and `docs/adr/ADR-0003-redaction-policy.md`):
  - When `security.redaction.enabled: true`, transcripts MUST be redacted-safe prior to promotion into standard long-term artifacts.
  - When `security.redaction.enabled: false`, transcripts MUST be withheld from standard long-term artifacts unless explicitly written to a quarantined unredacted location.
- If transcripts cannot be made redacted-safe (fail-closed), they MUST be withheld and replaced with deterministic placeholders (policy provenance must still be recorded).
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
- `report/report.json`

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
- For large scale, these may also be promoted to Parquet, but JSONL remains the canonical interchange format.

### Parquet (long-term event streams)
Default:
- All log-like datasets intended for long-term storage are written as Parquet.

Examples:
- Raw telemetry emitted by collectors or ingestors (after minimal parsing):
  - Windows event data
  - Sysmon exports
  - Linux syslog or journald exports
  - osquery results
- Normalized OCSF events
- Derived tables used in scoring (optional)

Rationale:
- Columnar compression and predicate pushdown make large-scale evaluation feasible on a single workstation.
- Parquet is broadly supported across the ecosystem.

## Parquet conventions

### Dataset naming

Within a run bundle, store Parquet datasets as directories with one or more Parquet files:

- `runs/<run_id>/raw_parquet/windows_eventlog/`
- `runs/<run_id>/raw_parquet/syslog/`
- `runs/<run_id>/raw_parquet/osquery/`
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
- Target row groups that are large enough for scan efficiency but not so large that local memory becomes a bottleneck.
- A practical starting point is row groups in the tens to low hundreds of MB range.

### Deterministic writing

To support reproducible diffs and regression tests:
- When writing Parquet within a run, sort rows deterministically before write:
  1. `time` ascending
  2. `metadata.event_id` ascending

Notes:
- Deterministic ordering is an implementation requirement. Parquet itself does not guarantee row order semantics, but stable ordering improves repeatability and debugging.

### Schema evolution

- Additive changes are preferred (new nullable columns).
- Avoid changing the meaning or type of existing columns.
- For normalized OCSF events, required provenance columns must not change types across versions.

## Normalized OCSF Parquet schema (minimum required columns)

Even when the normalized store is Parquet, the same contract intent applies as the JSON schema envelope.

Minimum required columns:
- `time` (int64, ms since epoch)
- `time_dt` (timestamp or string ISO-8601; choose one and standardize)
- `class_uid` (int32)
- `category_uid` (int32, nullable)
- `type_uid` (int32, nullable)
- `severity_id` (int32, nullable)

Provenance (required):
- `metadata.event_id` (string)
- `metadata.run_id` (string, UUID)
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
- If a source produces highly variable nested structures, store a `raw_json` (string) column as a fallback, but prefer typed columns for fields used by detections.

## Windows Event Log storage decision

You are split on EVTX. The recommended approach is to treat EVTX as evidence-tier optional, and Parquet as analytics-tier required.

### Recommendation

Redaction interaction (normative):
- EVTX is a binary evidence format and is not redacted in-place by the baseline policy.
- Therefore, EVTX MUST NOT be retained by default. Retention MUST require explicit operator intent (config-driven) and MUST be treated as sensitive evidence.
- When EVTX is retained, the run report and manifest SHOULD clearly indicate that an unredacted binary evidence artifact exists and where it is stored.

1. Always store a structured representation of Windows Event Logs as Parquet for consistency and analytics.
2. Optionally retain EVTX in `raw/evidence/` when you need:
   - maximal fidelity for reprocessing
   - compatibility with Windows-native tooling
   - investigation workflows that rely on EVTX semantics

Do not convert EVTX to plain text as the primary path. Plain text loses structure, complicates parsing, and tends to be less stable for deterministic pipelines. If you need human-readable views, generate them as derived, ephemeral artifacts.

### Why Parquet for Windows event data is worth it

- Consistent downstream evaluation: the evaluator consumes Parquet across OSes.
- Easier joins: correlate Windows telemetry with ground truth, osquery, and normalized OCSF events.
- Faster iteration: mapping fixes and Sigma tuning become query-driven.

### Why keeping EVTX can still be valuable

- Fidelity insurance: EVTX preserves full record structure and provenance.
- Reprocessing: if your mapping evolves, EVTX allows you to regenerate raw tables without re-running scenarios.
- Tool compatibility: many Windows IR utilities and workflows expect EVTX.

### Default policy (suggested)

- MVP and daily CI runs:
  - Do not retain EVTX by default.
  - Store Parquet extracted from Windows Event Log receiver output (or equivalent structured export).

- Investigation-quality runs (explicit flag):
  - Retain EVTX as evidence-tier artifacts.
  - Also store the corresponding Parquet extraction for analytics.

### Practical implementation options

Option A (preferred when using OTel Windows Event Log receiver):
- Collect structured events from the receiver.
- Write them into a raw Windows event Parquet table with stable columns:
  - channel, provider, event_id, record_id, computer, level, keywords, task, opcode, message (optional), xml (optional), and any structured data fields.
- Preserve raw XML only if needed. It can be large.

Option B (when you explicitly export EVTX):
- Export EVTX as evidence-tier.
- Parse EVTX into a structured raw table and write Parquet.
- Avoid plain text as an intermediate. Use XML or JSON structures if needed during parsing.

## Linux and Unix log storage

Linux, Unix, and BSD logs are well-suited to Parquet, but only after minimal parsing into a structured schema.

Suggested raw syslog Parquet columns:
- `time` (int64 ms)
- `host` (string)
- `app` (string)
- `pid` (int32, nullable)
- `facility` (string, nullable)
- `severity` (string, nullable)
- `message` (string)
- `raw` (string, nullable, for full original line)

For journald, prefer extracting structured fields into columns rather than storing only rendered message text.

## When to keep raw text logs

Keep raw text logs only as:
- ephemeral debug output under `runs/<run_id>/logs/`
- or as evidence-tier when the source is inherently plain text (example: a tool only emits text)

If a plain text log is intended for long-term storage and repeated queries, parse it into a table and store it as Parquet. You can retain the original line in a `raw` column if you want.

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
- Preserve sufficient raw structured Parquet tables to re-run normalization and detection evaluation without re-running scenarios.
- If EVTX is retained, it is additional insurance, not a replacement for the structured raw tables.

The manifest should record:
- which datasets exist
- their hashes (or the hash of a checksums file)
- versions used to generate them

## Decision matrix: EVTX vs Parquet

Use this table as the default decision logic:

- If your primary need is evaluation, scoring, and trending:
  - Parquet is required.
  - EVTX is optional.

- If your primary need is maximal Windows-native fidelity and reprocessing:
  - Keep EVTX as evidence-tier.
  - Still write Parquet for analytics.

- If disk budget is tight:
  - Keep Parquet only.
  - Retain EVTX only for explicitly flagged runs.

This yields consistency across the storage system without losing the ability to preserve high-fidelity Windows artifacts when needed.
