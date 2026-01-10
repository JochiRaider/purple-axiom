<!-- docs/spec/042_osquery_integration.md -->
# osquery integration (telemetry + normalization)

This document defines the v0.1 integration path for osquery as a telemetry source:
- Canonical continuous monitoring output format.
- OpenTelemetry Collector ingestion.
- Raw staging layout in the run bundle.
- Minimal, deterministic normalization to OCSF, including routing semantics.

## 1) Canonical osquery output format (continuous monitoring)

### 1.1 Required: filesystem logger in event format NDJSON

When osquery is enabled, collectors MUST ingest the osquery **scheduled query results log** emitted by `osqueryd` using the filesystem logger.

Canonical format (v0.1):
- One JSON object per line (NDJSON).
- Each line MUST include:
  - `name` (string): scheduled query name (query identifier for routing).
  - `hostIdentifier` (string): host identifier configured in osquery.
  - `unixTime` (string): epoch seconds as a string.
  - `action` (string): `added | removed | snapshot`.
- Each line MUST include exactly one of:
  - `columns` (object): differential event payload for `action: added|removed`.
  - `snapshot` (array of objects): snapshot payload for `action: snapshot`.

Non-canonical forms:
- Status logs (`INFO|WARNING|ERROR|FATAL`) are not part of the results stream and MUST NOT be mixed into the results log stream.
- “Batch” result formats MAY be supported later, but are out of scope for v0.1 unless explicitly enabled and covered by fixtures.

### 1.2 Timestamp handling

- The normalizer MUST interpret `unixTime` as integer epoch seconds and derive:
  - `time` (required envelope) as epoch milliseconds (`unixTime * 1000`).
- The normalizer MUST treat `calendarTime` as non-authoritative and MUST NOT use it for identity or ordering.

## 2) Raw staging in the run bundle

When `telemetry.sources.osquery.enabled=true`, the pipeline MUST stage the source-native results log under:

- `runs/<run_id>/raw/osquery/osqueryd.results.log`

Notes:
- This staged file is the canonical “evidence-tier” representation for osquery results.
- The pipeline MAY also stage adjacent files (example: `osqueryd.*.log`) under the same directory, but they MUST be clearly separated from the results log.

## 3) OpenTelemetry Collector ingestion

### 3.1 Collection model

The preferred ingestion model is:
- osquery writes NDJSON results to the local filesystem.
- The OTel Collector tails the results file via the `filelog` receiver.
- The collector parses JSON and exports logs via OTLP (local file/OTLP and optional gateway), consistent with the canonical topology in `040_telemetry_pipeline.md`.

### 3.2 Minimal `filelog` receiver example

This example is intentionally minimal and is designed to:
- Tail osquery results.
- Parse NDJSON into attributes.
- Preserve the original line for forensic/debug use.

```yaml
receivers:
  filelog/osquery:
    include:
      # Linux default (package dependent)
      - /var/log/osquery/osqueryd.results.log
      # Windows example (explicit is strongly preferred)
      - C:\\ProgramData\\osquery\\log\\osqueryd.results.log
    start_at: beginning
    include_file_path: true
    # Required for durable offset tracking across restarts; see 040_telemetry_pipeline.md "Checkpointing and replay semantics"
    storage: file_storage    
    operators:
      - type: json_parser
        parse_from: body
      - type: move
        from: attributes.name
        to: attributes.osquery.query_name
      - type: move
        from: attributes.hostIdentifier
        to: attributes.osquery.host_identifier
      - type: move
        from: attributes.unixTime
        to: attributes.osquery.unix_time
      - type: move
        from: attributes.action
        to: attributes.osquery.action
```
**Durable offset tracking note (required):** This receiver example assumes the collector enables a storage extension (v0.1 reference: `file_storage` / filestorage) and points it at a durable on-disk directory. Loss/corruption/reset of that directory MUST be treated as checkpoint loss per `040_telemetry_pipeline.md` (replay/duplication is expected; gaps must be recorded).

### 3.3 Rotation and compression constraints (required)

- The `filelog` receiver MUST be able to read every rotated segment necessary to cover the
  worst-case catch-up window (see `040_telemetry_pipeline.md` “Checkpointing and replay semantics”).
- osquery filesystem logger rotation MAY produce Zstandard-compressed rotated files (`*.zst`).
  The v0.1 pipeline MUST NOT assume that the `filelog` receiver can read `*.zst` segments.
- Operators MUST ensure the osquery results rotation policy yields rotated history that is readable
  by `filelog` for the full catch-up window. Acceptable strategies include:
  - keep rotated segments uncompressed until after the catch-up window expires, or
  - use gzip (`*.gz`) for rotated segments and configure `filelog` `compression: gzip`
    (append-only; MUST NOT recompress-overwrite existing files).
- If unreadable rotated segments lead to missing results, the validator MUST record the gap as a
  telemetry failure (not silently ignored).

Required exporter tagging:
- The collector (or downstream normalizer) MUST be able to set `metadata.source_type = "osquery"` for records originating from this receiver.

Failure handling (v0.1):
- If a line fails JSON parsing, the collector SHOULD emit it as an unstructured log record (retain the raw line) and the normalizer MUST account for it as an ingest/parse error (see §6).

## 4) Derived raw Parquet (optional but recommended)

The pipeline MAY convert staged NDJSON lines into a Parquet dataset under:

- `runs/<run_id>/raw_parquet/osquery/`

When emitted, the dataset MUST include (at minimum) the following columns:

| Column | Type | Notes |
|---|---|---|
| `time` | int64 | Epoch ms derived from `unixTime` |
| `query_name` | string | From `name` |
| `host_identifier` | string | From `hostIdentifier` |
| `action` | string | `added|removed|snapshot` |
| `columns_json` | string (JSON) | Present for `added|removed`, else null |
| `snapshot_json` | string (JSON) | Present for `snapshot`, else null |
| `raw_json` | string (JSON) | The full original JSON object (canonical raw) |
| `log.file.path` | string | If provided by the collector; else null |

Determinism requirements:
- `raw_json` MUST be the original parsed JSON object re-serialized via RFC 8785 (JCS) prior to hashing or stable joins (see ADR-0002).

## 5) Normalization to OCSF

### 5.1 Source type

- The normalizer MUST set `metadata.source_type = "osquery"` for osquery-derived events.

### 5.2 Routing by `query_name`

Normalization MUST be routed by osquery `query_name` (the `name` field in the results log). The routing table MUST be captured in the mapping profile snapshot (`normalized/mapping_profile_snapshot.json`).

v0.1 default routing:

| `query_name` | OCSF target class | `class_uid` |
|---|---|---:|
| `process_events` | Process Activity | 1007 |
| `file_events` | File System Activity | 1001 |
| `socket_events` | Network Activity | 4002 |

Rules:
- The normalizer MUST NOT guess a `class_uid` for unknown `query_name` values.
- Unknown `query_name` rows MUST be counted as unrouted/unmapped in `normalized/mapping_coverage.json`.
- Implementations MAY provide an explicit allowlist of additional `query_name` routes via mapping profile material.

### 5.3 Minimal mapping obligations (v0.1)

For routed rows, the normalizer MUST:
- Emit a valid OCSF envelope as defined in `docs/spec/050_normalization_ocsf.md` and `docs/spec/055_ocsf_field_tiers.md`.
- Preserve the full source payload under an explicit `unmapped.osquery` object when fields cannot be mapped deterministically.

Minimum `unmapped.osquery` contents:
- `query_name`
- `action`
- `columns` (object) or `snapshot` (array), whichever was present
- `raw_json` (the original object, or a redacted-safe representation)

### 5.4 Event identity (required)

`metadata.event_id` MUST be computed per ADR-0002 using an osquery identity basis with deterministic inputs.

v0.1 identity basis (Tier 3, because osquery does not provide a stable record id):
```json
{
  "source_type": "osquery",
  "host_identifier": "<hostIdentifier>",
  "query_name": "<name>",
  "action": "<action>",
  "unix_time": <unixTime_int>,
  "payload": <columns_or_snapshot_canonical_json>
}
```

Rules:
- `payload` MUST be the canonical JSON object/array for `columns` or `snapshot` using RFC 8785 (JCS).
- `calendarTime` MUST NOT be included.
- For OCSF-conformant outputs, `metadata.uid` MUST equal `metadata.event_id` (see `025_data_contracts.md`).

## 5.5 Known Mapping Limitations (v0.1)

The v0.1 osquery mappings have the following documented limitations. These are driven by what the underlying osquery event tables can provide and, in some cases, by platform-specific collection backends.

### macOS and Linux

#### `file_events` (FIM)

- Initiating process attribution is not available from `file_events`. The table reports file change metadata (including file owner `uid/gid`) and an `action`, but it does not include a process identifier or executable path for the initiating actor. As a result, `actor.process` MUST be absent for `file_events` normalized events.
- If process context is required for detection content, it MUST be sourced from a process-context file auditing table rather than inferred from `file_events`. Feasible options include:
  - Linux: `process_file_events` (audit-based file activity with process context). This includes process identifiers and user identifiers such as `pid`, `ppid`, `uid/euid`, `auid`, and `executable`.
    - Operational constraints apply: `process_file_events` requires audit control (it will not work if `auditd` is running), and it only reports events for directories that exist before the agent starts.
  - macOS: `es_process_file_events` (EndpointSecurity-based file activity with process context), which includes `pid`, parent process context, and executed `path`.
- `activity_id` mapping is best-effort. `file_events.action` does not fully disambiguate content writes versus metadata-only changes. For example, osquery can emit actions like `ATTRIBUTES_MODIFIED`, which indicates a metadata change.

#### `socket_events` (process and socket auditing)

- `socket_events` does provide process linkage, including `pid` and executed `path`, so `actor.process.pid` can be populated directly when present.
- `socket_events` provides an audit user identifier (`auid`). v0.1 normalization SHOULD map this to a numeric user identifier (for example, `actor.user.uid`) when present. Username resolution is out of scope for v0.1 unless explicitly supported via additional identity correlation logic.
- Direction inference is best-effort and derived from the observed action set (`bind`, `connect`, `accept`). `connect` is treated as outbound intent, `accept` as inbound acceptance, and `bind` is ambiguous without additional context.

#### `action=snapshot` (scheduled query snapshot logging)

- Snapshot rows represent bulk table state at a point in time, not discrete per-entity events.
- When snapshot rows are emitted as event-like rows (for example, via snapshot event logging), they MUST be normalized as state observations rather than activity. v0.1 routes these to the standard class but with `activity_id=99` (Other), and includes an explanation in `unmapped.osquery.notes`.

### Windows

#### Filesystem activity (`ntfs_journal_events`)

- On Windows, osquery file integrity monitoring is sourced from `ntfs_journal_events` (NTFS USN journal), not `file_events`.
- `ntfs_journal_events` does not include initiating process identifiers or executable path. Therefore, for file activity normalized from `ntfs_journal_events`, `actor.process` MUST be absent.
- User attribution is not provided directly by `ntfs_journal_events`. Any `actor.user` attribution requires a different telemetry source.
- `activity_id` mapping remains best-effort because `action` values reflect USN journal semantics (for example, write, delete, rename) and do not always cleanly distinguish content writes from metadata-only changes.

#### Network socket activity

- The osquery `socket_events` table is not available on Windows (it is macOS/Linux only).
- Therefore, v0.1 does not normalize Windows network connection activity from osquery. Any Windows network connection normalization MUST be sourced from a non-osquery telemetry provider (or treated as out of scope for v0.1).
- Scheduled snapshot diffs of socket state are intentionally not treated as event-equivalent in v0.1 (race-prone and non-deterministic under load).

#### Process execution context (`process_etw_events`)

- Windows process execution telemetry MAY be sourced from `process_etw_events` (ETW-backed), which can provide `pid`, `ppid`, `path`, `cmdline`, and `username` when available.
- `process_etw_events` reliability is build-dependent. v0.1 treats this source as best-effort and requires fixture validation on the supported Windows build matrix (including validation that ProcessStart events are emitted as expected).

#### `action=snapshot`

- Snapshot rows remain bulk table state, not discrete events. Snapshot-derived rows continue to be routed to the standard class with `activity_id=99` (Other), with rationale recorded in `unmapped.osquery.notes`.

These limitations do not prevent normalization but may affect Tier 1 field coverage metrics (see `055_ocsf_field_tiers.md`).

## 6) Conformance fixtures and tests

A conformant implementation MUST include fixture-driven tests with deterministic golden outputs.

### 6.1 Required fixtures

Add the following fixtures under `tests/fixtures/osquery/` (recommended convention):

- `osqueryd.results.log` (NDJSON):
  - At least 2 differential rows (`added`, `removed`) for `process_events`
  - At least 1 snapshot row (`snapshot`) for `file_events`
  - At least 1 row for an unknown `query_name` (to validate unrouted behavior)
  - At least 1 invalid JSON line (to validate parse-error accounting)

### 6.2 Required assertions

At minimum, CI MUST assert:

- **Parsing:**
  - Valid JSON lines are ingested and available to normalization.
  - Invalid JSON lines are counted as ingest/parse errors and do not produce normalized events.

- **Routing:**
  - Known `query_name` values map to the expected `class_uid`.
  - Unknown `query_name` values do not produce normalized events and are recorded as unrouted/unmapped.

- **Identity determinism:**
  - Re-normalizing the same fixture input produces byte-identical `metadata.event_id` values (and `metadata.uid` when present).

- **Raw preservation:**
  - The staged `runs/<run_id>/raw/osquery/osqueryd.results.log` is present when osquery is enabled.
  - Routed normalized events contain `unmapped.osquery.raw_json` (or an explicitly redacted-safe representation when redaction is enabled).

## 7) Sample inputs and outputs (non-normative)

### 7.1 Example osquery NDJSON lines

```json
{"name":"process_events","hostIdentifier":"win11-test-01","unixTime":"1736204345","action":"added","columns":{"pid":"4321","path":"C:\\\\Windows\\\\System32\\\\cmd.exe","cmdline":"cmd.exe /c whoami"}}
{"name":"file_events","hostIdentifier":"win11-test-01","unixTime":"1736204347","action":"snapshot","snapshot":[{"target_path":"C:\\\\Temp\\\\example.txt","action":"CREATED"}]}
{"name":"unknown_query","hostIdentifier":"win11-test-01","unixTime":"1736204349","action":"added","columns":{"foo":"bar"}}
```

### 7.2 Example normalized OCSF envelope (Process Activity)

```json
{
  "time": 1736204345000,
  "class_uid": 1007,
  "metadata": {
    "event_id": "2f5a0f4b2c1b4bd38c0d9b6f7e9a1c2d",
    "uid": "2f5a0f4b2c1b4bd38c0d9b6f7e9a1c2d",
    "run_id": "RUN_ID",
    "scenario_id": "SCENARIO_ID",
    "collector_version": "otelcol-contrib",
    "normalizer_version": "purple-axiom-normalizer",
    "source_type": "osquery"
  },
  "unmapped": {
    "osquery": {
      "query_name": "process_events",
      "action": "added",
      "columns": {
        "pid": "4321",
        "path": "C:\\\\Windows\\\\System32\\\\cmd.exe",
        "cmdline": "cmd.exe /c whoami"
      }
    }
  }
}
```