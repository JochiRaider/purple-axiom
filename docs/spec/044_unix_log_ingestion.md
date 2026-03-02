---
title: Unix log ingestion (telemetry and normalization)
description: Defines v0.1 Linux log ingestion for journald, syslog, and auditd sources.
status: draft
category: spec
tags: [telemetry, linux, journald, syslog, auditd]
related:
  - 040_telemetry_pipeline.md
  - ADR-0002-event-identity-and-provenance.md
  - 045_storage_formats.md
---

# Unix log ingestion (telemetry and normalization)

This document defines the v0.1 integration path for Linux log sources including journald, syslog
text files, and auditd.

It covers supported distribution families, OTel ingestion paths, checkpoint persistence, duplicate
avoidance, audit correlation requirements, and raw staging layout.

## Overview

Linux systems produce logs through multiple subsystems that often overlap. systemd-journald captures
structured logs from the kernel, early boot, daemon output, and forwarded syslog; rsyslog or
syslog-ng then writes filtered subsets to text files under `/var/log/`. The Linux audit subsystem
(auditd) produces security-relevant syscall and access logs that may flow through journald, audisp,
or directly to `/var/log/audit/audit.log`.

Purple Axiom v0.1 supports ingestion from these sources via OpenTelemetry Collector receivers, with
explicit rules for checkpoint persistence, duplication avoidance, and identity computation.

## Scope

This document covers:

- Debian/Ubuntu and RHEL-family Linux distributions
- journald (systemd journal) ingestion via the OTel `journald` receiver
- Syslog text file ingestion via the OTel `filelog` receiver
- Network syslog ingestion via the OTel `syslog` receiver (optional)
- Linux audit (auditd) ingestion via journald or direct file tailing
- Checkpoint and cursor persistence requirements
- Duplication avoidance when multiple paths capture the same events

This document does NOT cover:

- BSD or other Unix variants (explicitly out of scope for v0.1)
- macOS system logs (reserved for future specification)
- Application-specific log formats beyond standard syslog
- Windows Event Log (see the [telemetry pipeline specification](040_telemetry_pipeline.md))

## Standard log paths by distribution family

### Debian/Ubuntu (rsyslog defaults)

| Log file            | Content                          | Syslog facility/severity    |
| ------------------- | -------------------------------- | --------------------------- |
| `/var/log/syslog`   | General system messages          | Most facilities except auth |
| `/var/log/auth.log` | Authentication and authorization | auth, authpriv              |
| `/var/log/kern.log` | Kernel messages                  | kern                        |
| `/var/log/dpkg.log` | Package manager activity         | Application-specific        |

### RHEL-family (rsyslog defaults)

| Log file            | Content                     | Syslog facility/severity    |
| ------------------- | --------------------------- | --------------------------- |
| `/var/log/messages` | General system messages     | Most facilities except auth |
| `/var/log/secure`   | Authentication and security | auth, authpriv              |
| `/var/log/maillog`  | Mail subsystem              | mail                        |
| `/var/log/cron`     | Cron daemon                 | cron                        |
| `/var/log/boot.log` | Boot messages               | Local use                   |

### Audit log (both families)

| Log file                   | Content                      | Notes                        |
| -------------------------- | ---------------------------- | ---------------------------- |
| `/var/log/audit/audit.log` | Linux audit subsystem events | Requires root or audit group |

### journald storage locations

| Path                | Persistence | Notes                                                 |
| ------------------- | ----------- | ----------------------------------------------------- |
| `/run/log/journal/` | Volatile    | Default; cleared on reboot                            |
| `/var/log/journal/` | Persistent  | Requires explicit configuration or directory creation |

Operators must verify whether persistent journald storage is enabled on target assets. If only
volatile storage is configured, journal entries from prior boots are unavailable.

## Duplication avoidance (required)

On most modern Linux systems, systemd-journald collects logs from the kernel, early boot, daemon
stdout/stderr, and the syslog socket, then forwards a subset to rsyslog. rsyslog writes filtered
messages to text files under `/var/log/`.

**Critical constraint**: If the pipeline ingests both journald and rsyslog-written `/var/log/*`
files on the same host (syslog overlap), or ingests both journald audit transport and
`/var/log/audit/audit.log` on the same host (audit overlap), duplicate events are expected unless
explicitly prevented.

### Required policy (v0.1)

Operators must choose one of the following strategies per host:

1. **journald-only (preferred)**: Ingest via the `journald` receiver. Do not tail `/var/log/syslog`
   `/var/log/*` sources (for example `/var/log/syslog`, `/var/log/messages`, or
   `/var/log/audit/audit.log`) on the same host.

1. **File-only**: Tail `/var/log/*` files via `filelog`. Do not use the `journald` receiver for
   overlapping content.

1. **Explicit overlap dedupe (discouraged; implementation-defined)**: If both journald ingestion
   (`_TRANSPORT=syslog`) and syslog file tailing are enabled for overlapping syslog content, the
   dataset is expected to contain semantic duplicates. Implementations MUST NOT attempt to remove
   these duplicates by comparing `metadata.event_id` (Tier 1 cursor-based IDs and Tier 2
   artifact-cursor IDs will differ by design).

   If an implementation supports an overlap dedupe mode, it MUST be explicitly enabled via
   `telemetry.sources.unix.dedupe_strategy` and MUST be recorded in the run manifest at
   `manifest.telemetry.sources.unix.dedupe_strategy`. For v0.1, the only allowed overlap dedupe
   strategy token is `unix_syslog_fingerprint_v1`, defined as:

   - **Canonical syslog fields (required):** The `app`, `pid`, `facility`, `severity`, `message`,
     and `event_time_epoch_ms` values used below MUST be the canonical fields emitted by the formal
     syslog parser module `pa.syslog.v1` (`syslog_ast_v1`) after timestamp normalization (see
     "Syslog file ingestion / Formal syslog parser module (pa.syslog.v1)"). Implementations MUST NOT
     use receiver-specific parsing outputs unless they are byte-identical to `pa.syslog.v1` output
     for the same source line.

   - Compute `fingerprint_basis_v1`:

     ```json
     {
       "v": 1,
       "t": "<event_time_epoch_seconds>",
       "host": "<origin.host>",
       "app": "<app>",
       "pid": "<pid_or_null>",
       "facility": "<facility_or_null>",
       "severity": "<severity_or_null>",
       "message": "<message>"
     }
     ```

   - `event_time_epoch_seconds` MUST be computed as `floor(event_time_epoch_ms / 1000)` using
     `syslog_ast_v1.event_time_epoch_ms` emitted by `pa.syslog.v1` (including RFC3164 year inference
     and timezone assumption).

   - Serialize `fingerprint_basis_v1` using RFC 8785 canonical JSON (UTF-8 bytes).

   - Compute `fingerprint = sha256_hex(canonical_bytes)`.

   Dedupe rule (deterministic):

   - For events with the same `(host, fingerprint)` in a run, keep exactly one record:
     1. Prefer the record that has `origin.journald_cursor` present (journald-origin).
     1. Otherwise, prefer the record with the lexicographically smallest `stream.cursor` (bytewise
        UTF-8).
     1. Otherwise, prefer the record with the lexicographically smallest `metadata.event_id`.

   **Caveat**: This strategy can drop legitimate repeated messages that are byte-identical within
   the same second. It SHOULD remain disabled unless duplication materially harms the run’s
   usability.

Audit overlap note: if both journald audit transport (`_TRANSPORT=audit`) and audit log file tailing
(`telemetry.sources.unix.audit_log_files`) are enabled for the same host, overlap is detected. v0.1
does not define an audit-specific dedupe strategy; operators SHOULD avoid dual ingestion or accept
degraded data quality with explicit operator acknowledgment.

The pipeline MUST NOT silently ingest overlapping Unix sources without explicit operator
acknowledgment

When any Unix source under `telemetry.sources.unix.*` is enabled, the validator MUST evaluate
whether an overlapping configuration is active on the same host. At minimum, overlap MUST be
considered detected when:

- `telemetry.sources.unix.journald.enabled=true` **and** `telemetry.sources.unix.syslog_files` is
  non-empty.
- `telemetry.sources.unix.journald.enabled=true` **and** `telemetry.sources.unix.audit_log_files` is
  non-empty.

(Network syslog ingestion does not participate in this overlap check.)

The validator MUST emit a `health.json.stages[]` entry with `stage="telemetry.unix.source_overlap"`
(see ADR-0005) and SHOULD record overlap evidence in `runs/<run_id>/logs/telemetry_validation.json`
under `unix_source_overlap` (see `040_telemetry_pipeline.md`).

The validator MUST set `operator_acknowledged=true` iff `telemetry.sources.unix.dedupe_strategy` is
present (non-null).

Severity and `health.json` treatment (normative):

| Condition               | `overlap_detected` | `operator_acknowledged` | Substage `status` | `fail_mode`                           | `reason_code`                        |
| ----------------------- | ------------------ | ----------------------- | ----------------- | ------------------------------------- | ------------------------------------ |
| No unix sources enabled | N/A                | N/A                     | substage omitted  | —                                     | —                                    |
| No overlap              | `false`            | any                     | `success`         | `fail_closed`                         | *(omit)*                             |
| Overlap, no ack         | `true`             | `false`                 | `failed`          | `fail_closed` (default; configurable) | `unix_source_overlap_unacknowledged` |
| Overlap, ack'd          | `true`             | `true`                  | `failed`          | `warn_and_skip`                       | `unix_source_overlap_active`         |

The default `fail_mode` for unacknowledged overlap is `fail_closed` and MUST be configurable via
`telemetry.unix.source_overlap.fail_mode` (see `120_config_reference.md`). The acknowledged overlap
case MUST always use `warn_and_skip` so that the run records degraded data quality without blocking
downstream stages.

## journald ingestion

### OTel journald receiver

The OpenTelemetry Collector `journald` receiver parses journal entries by shelling out to
`journalctl`. It supports cursor-based checkpointing via a storage extension.

#### Prerequisites

- `journalctl` binary must be present in `$PATH` or configured via `journalctl_path`.
- The collector user must have read access to journal files (typically via `systemd-journal` group
  membership).
- For containerized collectors, the host journal directory must be mounted and a compatible
  `journalctl` binary must be available inside the container.

#### Cursor persistence (required)

The journald receiver tracks position using journal cursors. Without a storage extension, cursors
are held in memory only and restart causes position loss.

Normative requirements:

- For v0.1 validation runs, the `journald` receiver must be configured with a storage extension
  (v0.1 reference: `storage: file_storage`).
- The storage directory must be on durable disk and must not be an ephemeral temp directory.
- Loss, corruption, or reset of the storage directory must be treated as checkpoint loss per the
  [telemetry pipeline specification](040_telemetry_pipeline.md).

#### Cursor opacity (required)

The journald cursor format is explicitly described as private and subject to change. The pipeline
must treat cursors as opaque strings:

- Cursors must be persisted exactly as emitted by `journalctl --show-cursor`.
- Cursors must only be used as input to `--after-cursor`.
- Implementations must not parse, normalize, or interpret cursor contents.

#### Reference receiver configuration

```yaml
receivers:
  journald/system:
    directory: /var/log/journal
    # Or /run/log/journal for volatile-only systems
    start_at: end
    # Required for durable cursor tracking
    storage: file_storage
    # Optional: filter by unit, priority, or match
    # units:
    #   - sshd.service
    #   - nginx.service
    # priority: info

extensions:
  file_storage:
    directory: /var/lib/otelcol/journald-checkpoints
    fsync: true
```

#### Required tagging

The collector or downstream normalizer MUST set `metadata.source_type` based on the journal
`_TRANSPORT` value using the following mapping:

| Journal `_TRANSPORT` | `metadata.source_type` |
| -------------------- | ---------------------- |
| `syslog`             | `linux-syslog`         |
| `journal`            | `linux-journald`       |
| `stdout`             | `linux-journald`       |
| `kernel`             | `linux-journald`       |
| `audit`              | `linux-auditd`         |

This mapping MUST remain consistent with "Normalization to OCSF" → "Source type assignment".

Note: `linux-journald` is an explicitly supported v0.1 `metadata.source_type` value (supplemental
tier) for non-audit journal transports.

### Identity basis (Tier 1)

journald provides a stable per-entry cursor suitable for Tier 1 identity across all journal
transports. Per ADR-0002:

```json
{
  "source_type": "<metadata.source_type>",
  "origin.host": "<emitting_host>",
  "origin.journald_cursor": "<__CURSOR_value>"
}
```

Rules:

- `source_type` MUST equal the effective `metadata.source_type` assigned for the entry (see
  "Required tagging" above).
- `origin.journald_cursor` MUST be the exact cursor string from the journal entry.
- The cursor MUST NOT be parsed or modified.
- Cursor/state persistence MUST be implemented via the receiver `storage` extension (see "Cursor
  persistence (required)"); implementations MUST NOT invent a separate cursor store.

## Syslog file ingestion

### OTel filelog receiver

For systems where journald is unavailable or where operators prefer file-based collection, the
`filelog` receiver tails syslog text files.

#### Standard include patterns

Debian/Ubuntu:

```yaml
receivers:
  filelog/syslog_debian:
    include:
      - /var/log/syslog
      - /var/log/auth.log
    start_at: end
    storage: file_storage
    include_file_path: true
```

RHEL-family:

```yaml
receivers:
  filelog/syslog_rhel:
    include:
      - /var/log/messages
      - /var/log/secure
    start_at: end
    storage: file_storage
    include_file_path: true
```

#### Offset persistence (required)

The `filelog` receiver must be configured with a storage extension for durable offset tracking. Per
the [telemetry pipeline specification](040_telemetry_pipeline.md):

- `storage: file_storage` (or equivalent) must be set.
- The storage directory must be durable and explicitly configured.
- Offset checkpoint loss must be treated as checkpoint loss and recorded accordingly.

#### Log rotation tolerance (required)

Linux systems rotate logs via `logrotate`, producing files with numeric suffixes (for example,
`syslog.1`, `messages.1.gz`). The `filelog` receiver must tolerate rotation:

- The `include` pattern should cover both the active file and recent rotated segments when catch-up
  after restart is required.
- If gzip-compressed rotated segments are ingested, they SHOULD be handled by a separate `filelog`
  receiver instance configured with `compression: gzip` and `include` globs matching `*.gz`
  (compression is configured per receiver; mixed plain + gzip patterns in one receiver are not
  portable).
- Recompress-overwrite rotation modes are NOT supported; compressed files must be append-only or
  created atomically.
- If rotated segments age out before being read, this must be recorded as a telemetry gap.

#### Syslog parsing operators

The receiver may use parsing operators to extract structured fields from syslog messages, but the
normative parsing definition for v0.1 is the formal syslog parser module `pa.syslog.v1` (see below).
Any operator-chain implementation MUST be behaviorally equivalent to `pa.syslog.v1` for all accepted
inputs and MUST emit the same `syslog_ast_v1` values.

Example operator chain for RFC 3164:

```yaml
operators:
  - type: regex_parser
    regex: '^(?P<timestamp>\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+(?P<host>\S+)\s+(?P<app>[^\[:]+)(?:\[(?P<pid>\d+)\])?:\s*(?P<message>.*)$'
    timestamp:
      parse_from: attributes.timestamp
      layout: '%b %d %H:%M:%S'
      location: Local
  - type: move
    from: attributes.host
    to: resource["host.name"]
```

RFC 3164 timestamp determinism requirements:

- RFC 3164 timestamps omit year and timezone. Implementations MUST apply a deterministic year
  inference rule and a deterministic timezone assumption (do not rely on collector process-local
  defaults when the collector is containerized or runs off-host).
- v0.1 recommended year inference rule (deterministic): interpret the parsed month/day/time in the
  emitting host’s assumed timezone; choose the year such that the resulting timestamp is the closest
  timestamp at or before the run window end time (prevents year-rollover misparses).
- The chosen timezone + year inference rules MUST be documented in implementation notes and SHOULD
  be recorded in normalization provenance for debuggability.

##### Formal syslog parser module (pa.syslog.v1)

`pa.syslog.v1` is the normative syslog parsing contract for v0.1. It replaces regex-fragile syslog
parsing across all Unix syslog ingestion paths (journald syslog transport, syslog file tailing, and
network syslog ingestion).

**Module identity (normative):**

- `module_token`: `pa.syslog.v1`
- `module_id`: `syslog`
- `module_version`: `v1`
- `input_kind`: `utf8_text`

**Preprocessing and input envelope (normative):**

- UTF-8 BOM MAY be accepted but MUST be stripped before parsing.
- Newlines MUST be normalized (`\r\n` -> `\n`, `\r` -> `\n`) before parsing.
- Max input size: the canonical parse input MUST be `<= 65536` UTF-8 bytes.
  - If exceeded, parsing MUST fail closed with `line_too_long`.

The canonical parse input MUST be treated as a sequence of lines separated by `\n`:

- The first line (`line0`) is the syslog line to parse.
- Subsequent lines (if any) are syslog parse context directives of the form `@<key>=<value>`.
- A trailing empty final line (caused by an ending newline) MUST be ignored.

**Syslog parse context directives (v1; normative):**

These directives exist solely to make RFC3164 year inference deterministic and testable.

- `@assumed_timezone=<tz>` (REQUIRED for RFC3164-like inputs)
  - `<tz>` MUST be either:
    - an IANA time zone identifier (example: `America/New_York`), or
    - the literal `UTC`.
- `@run_end_time_utc=<rfc3339>` (REQUIRED for RFC3164-like inputs)
  - `<rfc3339>` MUST be an RFC 3339 timestamp with a `Z` suffix (UTC).

Directive rules (normative):

- Directive keys are case-sensitive.
- Duplicate directive keys MUST fail closed.
- Unknown directive keys MUST fail closed in v1 (`invalid_context_key`).
- For RFC3164-like inputs, missing a required directive key MUST fail closed with
  `missing_context_value`.

**Supported syslog formats (v1; normative):**

`pa.syslog.v1` MUST accept at minimum:

- **RFC3164-like** lines:

  - MAY include an initial PRI (`<0..191>`). If PRI is present, `facility` and `severity` MUST be
    derived from PRI; otherwise both MUST be `null`.
  - MUST include a timestamp of the form `Mmm dd hh:mm:ss` immediately after any PRI.
  - MUST include `<hostname> <tag>:` header fields, where:
    - `<hostname>` is a single non-space token,
    - `<tag>` is the application/program name, and
    - an optional PID MAY appear as `<tag>[<pid>]`.

- **RFC5424-like** lines:

  - MUST include PRI.
  - MUST include a version integer immediately after PRI; version MUST equal `1` in v1.
  - MUST include a full RFC 3339 timestamp with timezone information (or `Z`).
  - Hostname and app-name MUST NOT be NILVALUE (`-`) in v1.
  - Structured data MUST be either `-` or a syntactically valid RFC5424 structured-data sequence.
    - v1 validation MUST fail closed with `bad_structured_data` on invalid structured data.
    - v1 does not expose structured data in the AST (future versions may).

If an input line does not match either supported format, parsing MUST fail closed with
`unknown_format`.

**Timestamp parsing and normalization (normative):**

- For RFC5424-like inputs, `event_time_epoch_ms` MUST be derived from the RFC 3339 timestamp using
  integer arithmetic (no float parsing).
- For RFC3164-like inputs, `event_time_epoch_ms` MUST be derived by applying the deterministic year
  inference algorithm below using:
  - `@run_end_time_utc` as the reference instant, and
  - `@assumed_timezone` as the emitting host’s assumed timezone.

RFC3164 year inference algorithm (v1; normative):

1. Parse `month`, `day`, and `time` from the RFC3164 timestamp.
   - Month abbreviations are English and case-insensitive: `Jan`..`Dec`.
1. Convert `run_end_time_utc` into `assumed_timezone` to obtain `run_end_local`.
1. Candidate years are `run_end_local.year` and `run_end_local.year - 1`.
1. For each candidate year, construct a local datetime `candidate_local` with the parsed
   month/day/time:
   - If the local datetime is invalid for that year (for example Feb 29 in a non-leap year), skip
     the candidate.
   - If the local datetime is non-existent due to a DST forward jump, parsing MUST fail closed with
     `invalid_timestamp`.
   - If the local datetime is ambiguous due to a DST fallback, evaluate both possibilities and
     select the one whose UTC instant is the greatest instant `<= run_end_time_utc`. If both are
     `> run_end_time_utc`, select the smaller UTC instant (deterministic tie-break).
1. Select the candidate year whose UTC instant is the greatest instant `<= run_end_time_utc`.
   - If no candidate qualifies, parsing MUST fail closed with `invalid_timestamp`.
1. Set `event_time_epoch_ms` from the selected UTC instant.

**Equivalence requirement (normative):**

For any syslog line accepted by `pa.syslog.v1`, the derived fields used by:

- the Syslog Parquet schema (see "Syslog Parquet schema"), and
- `unix_syslog_fingerprint_v1` (overlap dedupe),

MUST be byte-identical for semantically identical inputs across:

- syslog file ingestion, and
- network syslog ingestion.

##### syslog_ast_v1 (minimal AST)

On success, `pa.syslog.v1` MUST return `syslog_ast_v1` with the following shape:

```json
{
  "syslog_version": "pa.syslog.v1",
  "format": "rfc3164",
  "event_time_epoch_ms": 0,
  "host": "debian",
  "app": "sudo",
  "pid": 123,
  "facility": "4",
  "severity": "2",
  "message": "example message"
}
```

Field rules (normative):

- `syslog_version` MUST equal `pa.syslog.v1`.
- `format` MUST be one of: `rfc3164`, `rfc5424`.
- `event_time_epoch_ms` MUST be an integer milliseconds-since-epoch UTC timestamp.
- `host` MUST be the hostname parsed from the syslog header (no case folding).
- `app` MUST be the application/program name parsed from the syslog header (no case folding).
- `pid` MUST be an integer when present; otherwise it MUST be `null`.
- `facility` and `severity` MUST be base-10 strings when PRI is present; otherwise `null`.
- `message` MUST be the message portion after header parsing (may be empty but MUST be present).

##### Deterministic parse errors (syslog\_\*)

On failure, `pa.syslog.v1` MUST return one or more parser-module errors conforming to
`026_contract_spine.md` "Parser modules".

Required error codes (v1; normative minimum):

- `line_too_long`
- `invalid_utf8`
- `unknown_format`
- `invalid_pri`
- `invalid_version`
- `missing_timestamp`
- `invalid_timestamp`
- `invalid_hostname`
- `invalid_app`
- `invalid_pid`
- `bad_structured_data`
- `invalid_context_key`
- `missing_context_value`

Location rules (normative):

- `location.byte_offset` MUST point at the first byte of the offending token in the canonical parse
  input (line 0 for syslog syntax errors, directive lines for context errors).

### Identity basis (Tier 2)

Syslog text logs lack a source-native unique identifier. Repeated byte-identical messages in the
same timestamp bucket are common. Per ADR-0002, use Tier 2 when a stable cursor exists:

```json
{
  "source_type": "linux-syslog",
  "origin.host": "<emitting_host>",
  "stream.name": "<source_file>",
  "stream.cursor": "li:<line_index>"
}
```

Rules:

- `stream.name` MUST be a stable identifier for the stored artifact and MUST correspond to the
  staged syslog file name under `raw/syslog/` (for example, `syslog`, `messages`, `auth.log`).
- `stream.cursor` MUST be stable under reprocessing and MUST be `li:<u64>`, where `<u64>` is the
  0-based line index within that stored artifact (base-10 ASCII digits).
- Together, (`stream.name`, `stream.cursor`) form the canonical row locator for syslog provenance.
- Byte offsets MAY be used for collection checkpointing, but v0.1 uses `line_index` as the canonical
  row locator because syslog is line-oriented and the `li:<u64>` cursor is human-readable.
- Ephemeral collector offsets MUST NOT be used unless persisted with the stored artifact.

When neither Tier 1 nor Tier 2 inputs exist, fall back to Tier 3 fingerprinting per ADR-0002. Tier 3
identity should be treated as lower confidence in coverage reporting.

## Network syslog ingestion (optional)

### OTel syslog receiver

For environments that forward syslog over the network, the `syslog` receiver accepts UDP and TCP
connections.

#### Protocol support

| Protocol | RFC        | Notes                                       |
| -------- | ---------- | ------------------------------------------- |
| RFC 3164 | BSD syslog | Legacy format; timestamp precision varies   |
| RFC 5424 | Structured | Preferred; includes structured data support |

#### TCP framing (RFC 6587)

For TCP connections, message framing is required. The receiver supports:

- **Newline framing (default)**: Messages terminated by LF, CR, CRLF, or NUL.
- **Octet counting**: Each message prefixed with its byte length (RFC 6587).

Normative requirements:

- `enable_octet_counting` defaults to `false`. Operators must explicitly enable it when remote
  senders use octet-prefixed framing.
- `max_octets` defaults to **8192 bytes**. Operators should increase this value if senders emit
  messages exceeding this limit.
- `enable_octet_counting` and `non_transparent_framing_trailer` are mutually exclusive.

#### Reference configuration

```yaml
receivers:
  syslog/network:
    protocol: rfc5424
    tcp:
      listen_address: "0.0.0.0:1514"
    # For RFC 6587 octet counting (if senders require it):
    # enable_octet_counting: true
    # max_octets: 65536
```

#### Identity basis

Network syslog records inherit the same identity constraints as file-tailed syslog. Prefer Tier 2
(with stored artifact cursor) when records are staged to the run bundle. For stream-only ingestion
without staging, Tier 3 fingerprinting applies.

## Linux audit (auditd) ingestion

### Audit subsystem overview

The Linux audit subsystem logs security-relevant syscalls, file accesses, and authentication events.
A single semantic audit event frequently produces multiple records that share a timestamp and serial
number in the format `msg=audit(<epoch>.<fractional>:<serial>)`.

Record types within a single audit event commonly include:

- `SYSCALL`: syscall metadata (syscall number, arguments, return value)
- `EXECVE`: executed command arguments
- `PATH`: file path information (may appear multiple times)
- `CWD`: current working directory
- `PROCTITLE`: process title / command line
- `EOE`: end-of-event marker (when enabled)

**Critical requirement**: Implementations must correlate records by their shared
`msg=audit(<timestamp>:<serial>)` identifier before mapping to a single OCSF event. Treating each
audit record line as an independent event produces incorrect, fragmented output.

### Ingestion paths

#### Path 1: journald with audit transport (preferred)

When audit events are forwarded to journald (common on modern systemd systems), ingest via the
`journald` receiver with an audit transport filter:

```yaml
receivers:
  journald/audit:
    directory: /var/log/journal
    start_at: end
    storage: file_storage
    matches:
      - _TRANSPORT: audit
```

Advantages:

- Tier 1 cursor-based identity for each raw audit record via journald cursor.
- Unified checkpoint model with other journald sources.

**Correlation requirement (still required)**: Even when ingesting audit records via journald,
implementations MUST correlate multiple records that share the same
`msg=audit(<epoch>.<fractional>:<serial>)` identifier into a single logical audit event before OCSF
mapping (see "Audit subsystem overview").

#### Path 2: Direct audit.log tailing (advanced)

When audit events are not forwarded to journald, tail `/var/log/audit/audit.log` directly:

```yaml
receivers:
  filelog/audit:
    include:
      - /var/log/audit/audit.log
    start_at: end
    storage: file_storage
    include_file_path: true
```

**Operator declaration (normative):** When audit log file tailing is enabled under Purple Axiom
orchestration, the same paths MUST be declared in `telemetry.sources.unix.audit_log_files` so the
Unix overlap validator can detect and gate dual-ingestion with journald.

**Multi-record correlation requirement**: The `filelog` receiver emits one log record per line. The
normalizer or an intermediate processor must aggregate lines by their shared
`msg=audit(<timestamp>:<serial>)` before OCSF mapping. This aggregation is NOT performed by the
receiver itself.

Recommended approaches:

1. **Transform processor**: Use OTel `transform` or `groupbyattrs` processors to buffer and
   aggregate records by audit message ID before export.

1. **Normalizer aggregation**: Stage raw audit lines to Parquet, then aggregate by message ID during
   normalization.

1. **audisp plugin**: Use the `audisp-remote` plugin or a custom audisp plugin to pre-aggregate
   events before forwarding to the collector.

v0.1 recommendation: Use journald-based ingestion (Path 1) when available. Direct audit.log tailing
(Path 2) is supported but must document the chosen aggregation strategy.

#### Path 3: audisp plugin to syslog or network receiver

The audit dispatcher (`audispd`) can forward events to external systems via plugins. The `af_unix`
or `syslog` plugins can route events to the OTel `syslog` receiver or a custom socket.

This path is implementation-defined and out of scope for detailed v0.1 specification.

### Formal parsing and correlation (normative)

This section replaces regex/key-fragile audit parsing and correlation with formal parser modules and
a deterministic correlation algorithm.

#### Formal audit record grammar (pa.auditd_record_kv.v1)

`pa.auditd_record_kv.v1` is the normative grammar for a single Linux audit record line.

**Module identity (normative):**

- `module_token`: `pa.auditd_record_kv.v1`
- `module_id`: `auditd_record_kv`
- `module_version`: `v1`
- `input_kind`: `utf8_text`

**Input preprocessing (normative):**

- UTF-8 BOM MAY be accepted but MUST be stripped before parsing.
- Newlines MUST be normalized (`\r\n` -> `\n`, `\r` -> `\n`) before parsing.
- A single trailing `\n` (common for file line reads) MUST be ignored.
- Max input size: the canonical parse input MUST be `<= 65536` UTF-8 bytes.
  - If exceeded, parsing MUST fail closed with `line_too_long`.

**Tokenization and key/value grammar (v1; normative):**

- An audit record line MUST be parsed as a sequence of tokens separated by one or more ASCII spaces.
- Each token MUST be of the form `<key>=<value>` where:
  - `<key>` matches `^[A-Za-z0-9_]+$`.
  - `<value>` is either:
    - an unquoted token: a non-empty sequence of non-space characters, or
    - a quoted token: `"` `<chars>` `"` where:
      - `\"` represents a literal `"` and `\\` represents a literal `\`,
      - all other backslash escapes MUST be preserved literally (no interpretation) in v1.

Required fields (v1; normative):

- The record MUST contain `type=<record_type>` and `msg=<msg_value>` tokens.
- `type` and `msg` MUST each appear exactly once.
  - If either is missing, parsing MUST fail closed (`missing_required_field`).
  - If either repeats, parsing MUST fail closed (`duplicate_required_field`).

Repeated keys (v1; normative):

- Keys other than `type` and `msg` MAY repeat.
- The AST representation MUST preserve repeats deterministically:
  - The first occurrence is represented as a string value.
  - On the second occurrence, the value MUST become an array of strings in encounter order.

`msg` value handling (v1; normative):

- `msg` MUST contain a correlation key substring of the form `audit(<sec>.<fraction>:<serial>)`.
- The correlation key substring MUST be extracted and preserved exactly as `audit_msg_id` in the
  AST.
- A trailing colon immediately after the closing `)` (common in `msg=audit(...):`) MUST be ignored
  for the purposes of `audit_msg_id` extraction.

Hex decoding policy (v1; normative):

- v1 MUST NOT perform automatic hex decoding of any values (including `proctitle=`). Values are
  preserved as raw strings. Any decoded representation is reserved for a future module version.

**Output AST: audit_record_ast_v1 (v1; normative):**

On success, the module MUST return:

```json
{
  "audit_record_version": "pa.auditd_record_kv.v1",
  "record_type": "SYSCALL",
  "audit_msg_id": "audit(1700000000.123:456)",
  "node": "ip-10-0-0-1",
  "kv": {
    "arch": "c000003e",
    "syscall": "59",
    "exe": "/usr/bin/sudo"
  }
}
```

Field rules (normative):

- `audit_record_version` MUST equal `pa.auditd_record_kv.v1`.
- `record_type` MUST equal the parsed `type=` value.
- `audit_msg_id` MUST equal the extracted `audit(<sec>.<fraction>:<serial>)` substring exactly.
- `node` MUST be:
  - the parsed `node=` value if present, otherwise `null`.
- `kv` MUST contain all parsed key/value pairs excluding `type`, `msg`, and `node`.
  - Values are either strings or arrays of strings per "Repeated keys".

**Deterministic parse errors (auditd_record_kv\_\*) (normative minimum):**

On failure, `pa.auditd_record_kv.v1` MUST return one or more parser-module errors conforming to
`026_contract_spine.md` "Parser modules".

Required error codes (v1; normative minimum):

- `line_too_long`
- `invalid_utf8`
- `invalid_token`
- `unterminated_quote`
- `missing_required_field`
- `duplicate_required_field`
- `missing_correlation_key`

Location rules (normative):

- `location.byte_offset` MUST point at the first byte of the offending token in the canonical parse
  input.

#### Formal audit correlation-key parser (pa.audit_event_key.v1)

`pa.audit_event_key.v1` is the normative grammar for parsing the audit correlation key substring
`audit(<sec>.<fraction>:<serial>)` used as `origin.audit_msg_id`.

**Module identity (normative):**

- `module_token`: `pa.audit_event_key.v1`
- `module_id`: `audit_event_key`
- `module_version`: `v1`
- `input_kind`: `utf8_text`

**Grammar (v1; normative):**

The canonical parse input MUST match:

- `audit(` + `<sec>` + `.` + `<fraction>` + `:` + `<serial>` + `)`

Where:

- `<sec>` is a non-empty sequence of ASCII digits (`0-9`).
- `<fraction>` is a non-empty sequence of ASCII digits (`0-9`) of length 1 to 9.
- `<serial>` is a non-empty sequence of ASCII digits (`0-9`).

**Output AST: audit_event_key_ast_v1 (v1; normative):**

On success, the module MUST return:

```json
{
  "audit_event_key_version": "pa.audit_event_key.v1",
  "audit_msg_id": "audit(1700000000.123:456)",
  "epoch_seconds": 1700000000,
  "fraction_digits": "123",
  "serial": 456
}
```

Rules (normative):

- `audit_msg_id` MUST equal the canonical parse input exactly (no normalization).
- Numeric fields MUST be parsed using integer arithmetic (no float parsing).
- If any numeric value overflows unsigned 64-bit integer range, parsing MUST fail closed.

**Deterministic parse errors (audit_event_key\_\*) (normative minimum):**

Required error codes (v1; normative minimum):

- `line_too_long`
- `invalid_utf8`
- `invalid_format`
- `invalid_number`

#### Correlation algorithm (audit_correlation_v1)

`audit_correlation_v1` defines how multiple audit record lines are grouped into a single audit
event.

**Inputs (normative):**

- A finite set of raw audit record lines within a run window (for example from `audit.log` or the
  journald audit transport).
- Each line MUST be parsed by `pa.auditd_record_kv.v1`. Correlation keys MUST be parsed by
  `pa.audit_event_key.v1`.

**Correlation key (normative):**

- `correlation_key = origin.audit_msg_id = audit_record_ast_v1.audit_msg_id`
- `origin.audit_msg_id` MUST preserve the literal `audit(<sec>.<fraction>:<serial>)` substring
  exactly (no precision normalization).

**Grouping rule (normative):**

- All audit records with the same `correlation_key` MUST be correlated into a single audit event.

**Event time (normative):**

- `event_time_epoch_ms` for the correlated event MUST be derived from `correlation_key` using the
  parsed `epoch_seconds` and `fraction_digits` from `pa.audit_event_key.v1`:
  - Let `ms_digits = fraction_digits` right-padded with `0` to at least 3 digits.
  - Let `ms = int(ms_digits[0:3])` (truncate toward zero).
  - `event_time_epoch_ms = epoch_seconds * 1000 + ms`
- This computation MUST NOT use floating point.

**Deterministic `records_json` ordering (normative):**

The correlated event MUST include an ordered `records_json` array. Ordering MUST be deterministic
and independent of ingestion order:

1. For each `audit_record_ast_v1`, compute `k = canonical_json_bytes(record_ast)` (RFC 8785 / JCS).
1. Sort records by `k` using bytewise UTF-8 lexical ordering.
1. Emit `records_json` as the RFC 8785 canonical JSON bytes of the resulting array of
   `audit_record_ast_v1` objects.

**Primary record type (event_type) (normative):**

- If any record in the event has `record_type="SYSCALL"`, `event_type` MUST be `SYSCALL`.
- Otherwise, `event_type` MUST be the lexicographically smallest `record_type` present (bytewise
  UTF-8).

**Failure and error taxonomy (normative):**

`audit_correlation_v1` is fail closed at the event boundary:

- If an audit record fails `pa.auditd_record_kv.v1` parsing, it MUST NOT contribute to any
  correlated event, and a deterministic correlation error `audit_record_parse_error` MUST be
  recorded.
- If an audit record is missing a correlation key, it MUST NOT contribute to any correlated event,
  and a deterministic correlation error `audit_missing_correlation_key` MUST be recorded.
- If a correlated group contains inconsistent `node` values (non-null and unequal), the entire group
  MUST be dropped and `audit_event_inconsistent_node` MUST be recorded.

Implementations MAY apply explicit buffering limits for streaming correlation, but:

- Any buffering limit MUST be deterministic and MUST be documented.
- If a buffering limit is exceeded, the affected group MUST be dropped with
  `audit_event_buffer_overflow`.

Required correlation error codes (v1; normative minimum):

- `audit_record_parse_error`
- `audit_missing_correlation_key`
- `audit_event_inconsistent_node`
- `audit_event_buffer_overflow`

### Identity basis

#### Tier 1 (aggregated audit events)

When audit records are aggregated into a single logical event before normalization:

```json
{
  "source_type": "linux-auditd",
  "origin.host": "<emitting_host>",
  "origin.audit_node": "<node_value_if_present>",
  "origin.audit_msg_id": "audit(<epoch>.<fractional>:<serial>)"
}
```

Rules:

- `origin.audit_msg_id` MUST be the literal substring from the raw record, captured exactly, and
  MUST equal `audit_event_key_ast_v1.audit_msg_id` from `pa.audit_event_key.v1`.
- Implementations MUST NOT parse the timestamp into floating point.
- Implementations MUST NOT normalize fractional precision.

#### Tier 2 (per-record without aggregation)

If each audit record line is normalized independently (not recommended), use Tier 2 with a stable
artifact cursor to avoid identity collisions across records within the same event:

```json
{
  "source_type": "linux-auditd",
  "origin.host": "<emitting_host>",
  "stream.name": "audit.log",
  "stream.cursor": "<line_index_or_byte_offset>"
}
```

### Permissions

Audit log files are typically readable only by root or members of the `audit` group. The collector
process must have sufficient permissions:

- Run as root, OR
- Add the collector user to the `audit` group, OR
- Configure appropriate ACLs on `/var/log/audit/`.

## Raw staging in the run bundle

When Unix log ingestion is enabled, the pipeline must stage source-native logs under
`runs/<run_id>/raw/`.

### Recommended layout

```text
runs/<run_id>/raw/
├── journald/
│   └── journal_export.jsonl      # Exported journal entries (JSONL); each line MUST include __CURSOR and _TRANSPORT
├── syslog/
│   ├── syslog                    # Staged from /var/log/syslog (Debian; placeholder if withheld)
│   ├── messages                  # Staged from /var/log/messages (RHEL; placeholder if withheld)
│   └── auth.log                  # Staged from /var/log/auth.log (placeholder if withheld)
└── audit/
    └── audit.log                 # Staged from /var/log/audit/audit.log (placeholder if withheld)
```

Notes:

- Staged files are evidence-tier representations for reproducibility and MUST follow the effective
  redaction posture (redacted-safe, withheld, or quarantined) under the project redaction policy.

  - When withheld or quarantined, the standard artifact path MUST contain a placeholder artifact per
    `090_security_safety.md` rather than silently omitting the file.

- **Unix flat-text withholding (v0.1 default):** Unix flat-text artifacts (`raw/syslog/**`,
  `raw/audit/**`) are withheld by default in v0.1. In-place redaction is not attempted on flat-text
  sources due to the absence of a stable field schema. The placeholder MUST use:
  `PA_PLACEHOLDER_V1 handling=withheld reason_code=unix_text_redaction_unsupported`.

- **Structured JSONL artifacts:** Structured JSONL artifacts (journald export) MAY attempt
  field-level redaction but MUST fall back to withheld (placeholder) on any post-check match.

- **Raw provenance pointers (`raw_ref` / `raw_refs`):** Raw provenance pointers MUST follow
  ADR-0002's placeholder-aware selection rule: implementations MUST NOT emit `file_cursor_v1`
  pointing at a placeholder-only raw file. When `raw/**` is placeholder-only, `raw_ref` MUST use
  `dataset_row_v1` pointing into `raw_parquet/**`. Consequently, `raw_parquet/**` for a Unix source
  MUST NOT be pruned if it is the only remaining valid IT1/IT2 provenance anchor. If
  `raw_parquet/**` is also unavailable, the event MUST downgrade to IT3 with `raw_ref=null`.

- The pipeline MAY convert staged text to Parquet under `raw_parquet/`.

- Rotation and truncation during the run window SHOULD be handled by staging complete files or by
  recording the byte range captured.

### Raw provenance pointers (ADR-0002 instantiation)

ADR-0002 defines the generic `raw_ref` fallback rule:

> If raw preservation is enabled and the source supports stable cursors: emit `file_cursor_v1`
> pointing into `raw/`. Otherwise: emit `dataset_row_v1` pointing into `raw_parquet/`.

This spec instantiates that rule per Unix ingestion path as follows:

| Ingestion path           | Identity tier                                 | `raw_ref.kind` when `telemetry.raw_preservation.enabled=true`                                                  | `raw_ref.kind` when `telemetry.raw_preservation.enabled=false` (or raw withheld/quarantined/placeholder-only) |
| ------------------------ | --------------------------------------------- | -------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| journald (any transport) | IT1                                           | `file_cursor_v1` -> `raw/journald/journal_export.jsonl`, `cursor: li:<line_index>`                             | `dataset_row_v1` -> `raw_parquet/unix/journald/`                                                              |
| syslog file              | IT2                                           | `file_cursor_v1` -> `raw/syslog/<source_file>`, `cursor: li:<line_index>`                                      | `dataset_row_v1` -> `raw_parquet/unix/syslog/`                                                                |
| auditd via journald      | IT1 (multi-record group -> single OCSF event) | `file_cursor_v1` -> `raw/journald/journal_export.jsonl`, `cursor: li:<canonical_record_line_index>`            | `dataset_row_v1` -> `raw_parquet/unix/audit/`                                                                 |
| auditd via file tail     | IT1 (aggregated) / IT2 (per-record)           | `file_cursor_v1` -> `raw/audit/audit.log`, `cursor: bo:<byte_offset>` (or canonical offset for grouped events) | `dataset_row_v1` -> `raw_parquet/unix/audit/`                                                                 |

Additional rules (normative):

- Multi-record audit correlation and `raw_ref` canonicalization: when multiple raw records
  contribute to a single normalized audit event, the event's `raw_ref` MUST follow ADR-0002
  canonical selection rule (smallest `path`, then smallest numeric cursor). The full set of
  contributing records SHOULD be recorded in `raw_refs[]`.

- Placeholder-only artifacts: `file_cursor_v1` MUST NOT target placeholder-only files (see
  ADR-0002). In v0.1, Unix flat-text artifacts are placeholder-only by default, so the effective
  provenance pointer is `dataset_row_v1` into `raw_parquet/**` unless an implementation provides a
  redaction-safe representation of the raw text.

Dataset-row locators (recommended defaults):

- `raw_parquet/unix/journald/`: `{ "journald_cursor": "<__CURSOR>" }`
- `raw_parquet/unix/syslog/`: `{ "source_file": "<source_file>", "line_index": <u64> }`
- `raw_parquet/unix/audit/`:
  `{ "host": "<emitting_host>", "audit_msg_id": "audit(<epoch>.<fractional>:<serial>)" }`

## Derived raw Parquet (optional but recommended)

Derived raw Parquet is optional as a performance optimization, but it becomes REQUIRED whenever any
normalized event emits `raw_ref.kind="dataset_row_v1"` (including when
`telemetry.raw_preservation.enabled=false` or when a `raw/**` artifact is placeholder-only).

When emitted, Unix Parquet datasets MUST be stored under:

- `runs/<run_id>/raw_parquet/unix/journald/`
- `runs/<run_id>/raw_parquet/unix/syslog/`
- `runs/<run_id>/raw_parquet/unix/audit/`

Each Parquet dataset directory under `raw_parquet/**` MUST include a schema snapshot file named
`_schema.json` as specified in `045_storage_formats.md`.

### Journald Parquet schema

When converting journald export to Parquet, include at minimum:

| Column            | Type   | Notes                                       |
| ----------------- | ------ | ------------------------------------------- |
| `time`            | int64  | Epoch ms (derived from journal timestamp)   |
| `host`            | string | Hostname                                    |
| `journald_cursor` | string | `__CURSOR` (stable unique cursor per entry) |
| `transport`       | string | `_TRANSPORT` (journal, syslog, audit, etc.) |
| `message`         | string | `MESSAGE` (nullable)                        |
| `fields_json`     | string | Original fields as JSON (nullable)          |

### Syslog Parquet schema

When converting syslog text to Parquet, implementations MUST first parse each syslog line using
`pa.syslog.v1` and then include at minimum:

| Column        | Type   | Notes                                    |
| ------------- | ------ | ---------------------------------------- |
| `time`        | int64  | Epoch ms (derived from syslog timestamp) |
| `host`        | string | Hostname from syslog header              |
| `source_file` | string | Staged file name (for example `syslog`)  |
| `line_index`  | int64  | 0-based line index within `source_file`  |
| `app`         | string | Application name                         |
| `pid`         | int32  | Process ID (nullable)                    |
| `facility`    | string | Syslog facility (nullable)               |
| `severity`    | string | Syslog severity (nullable)               |
| `message`     | string | Message body (nullable)                  |
| `raw`         | string | Original line (nullable)                 |

### Audit Parquet schema

When converting audit.log to Parquet, implementations MUST aggregate by message ID first using
`audit_correlation_v1` (see "Formal parsing and correlation"), then include:

Determinism requirements (normative):

- `records_json` MUST be the RFC 8785 canonical JSON serialization of the ordered array of
  `audit_record_ast_v1` objects emitted by `audit_correlation_v1`.
- The order of elements in `records_json` MUST follow the deterministic ordering rule in
  `audit_correlation_v1` (independent of ingestion order).
- `raw_lines` MUST concatenate the original raw record lines in the same order as `records_json`,
  separated by `\n`.

| Column         | Type          | Notes                                        |
| -------------- | ------------- | -------------------------------------------- |
| `time`         | int64         | Epoch ms from audit timestamp                |
| `audit_msg_id` | string        | `audit(<timestamp>:<serial>)` identifier     |
| `host`         | string        | Hostname or node value                       |
| `event_type`   | string        | Primary record type (SYSCALL, USER\_\*, etc) |
| `records_json` | string (JSON) | Array of all records in the event            |
| `raw_lines`    | string        | Concatenated original lines (nullable)       |

## Normalization to OCSF

### Source type assignment

The normalizer must set `metadata.source_type` based on the ingestion path:

| Ingestion path                   | `metadata.source_type` |
| -------------------------------- | ---------------------- |
| journald (syslog transport)      | `linux-syslog`         |
| journald (journal/stdout/kernel) | `linux-journald`       |
| journald (audit transport)       | `linux-auditd`         |
| filelog on syslog files          | `linux-syslog`         |
| filelog on audit.log             | `linux-auditd`         |
| syslog receiver (network)        | `linux-syslog`         |

### OCSF class routing (v0.1 seed)

Routing to OCSF classes is content-dependent and requires mapping profiles per source. The following
are seed recommendations:

| Source content             | OCSF class            | `class_uid` |
| -------------------------- | --------------------- | ----------- |
| Authentication events      | Authentication        | 3002        |
| Process execution (audit)  | Process Activity      | 1007        |
| File access (audit)        | File System Activity  | 1001        |
| Network connection (audit) | Network Activity      | 4001        |
| General syslog             | Base Event (unmapped) | 0           |

Detailed mapping profiles for Linux sources are reserved for the mappings specification.

## Permissions and deployment guidance

### journald access

By default, journal files are readable by the `systemd-journal` group. To grant collector access
without running as root:

```bash
# Add collector user to systemd-journal group
sudo usermod -a -G systemd-journal otelcol-contrib

# Verify access
sudo -u otelcol-contrib journalctl --lines 5
```

### Audit log access

Audit logs require root or `audit` group membership:

```bash
# Add collector user to audit group (if group exists)
sudo usermod -a -G audit otelcol-contrib

# Or configure ACL
sudo setfacl -m u:otelcol-contrib:r /var/log/audit/audit.log
```

### Containerized collectors

For collectors running in containers:

- Mount the journal directory: `-v /var/log/journal:/var/log/journal:ro`
- Provide `journalctl` binary inside the container (not included in official otelcol images).
- Mount syslog directories as needed: `-v /var/log:/var/log:ro`
- Run as privileged or with appropriate capabilities for audit access.

## Conformance fixtures and tests

### Required fixtures

Add fixtures under `tests/fixtures/unix_logs/` (integration logs; recommended convention), plus
parser-module vectors under `tests/fixtures/parser_modules/` (unit-level):

- `journald_export.jsonl`: Exported journal entries including:

  - At least 2 entries with `_TRANSPORT=syslog`
  - At least 1 entry with `_TRANSPORT=audit`
  - Entries spanning authentication, daemon, and kernel sources

- `syslog_debian.log`: Sample Debian `/var/log/syslog` content including:

  - RFC 3164 formatted lines
  - At least 1 line with PID, at least 1 without
  - Repeated identical messages (to test identity stability)

- `audit.log`: Sample audit log including:

  - At least 1 complete multi-record audit event (SYSCALL + PATH + CWD + PROCTITLE + EOE)
  - Records with the same `msg=audit(...)` identifier

- `syslog_invalid.log`: Sample syslog content containing a small number of malformed lines for
  negative-path assertions (invalid PRI, invalid timestamp, and unknown format).

- `audit_incomplete.log`: Sample audit log segment containing records that cannot be correlated
  (missing or malformed `msg=audit(...)` key) for negative-path assertions.

Add parser-module vector fixtures under `tests/fixtures/parser_modules/`:

- `syslog_v1/vectors.json` (module `pa.syslog.v1`)
- `audit_event_key_v1/vectors.json` (module `pa.audit_event_key.v1`)
- `auditd_record_kv_v1/vectors.json` (module `pa.auditd_record_kv.v1`)

### Required assertions

CI must assert:

- **Cursor persistence**: journald receiver resumes using persisted checkpoint state after restart
  (no reset to the beginning). At-least-once replay is permitted; any duplicate records MUST be
  removed deterministically downstream (typically by `metadata.event_id` equality when the same
  cursor is re-read).

- **Offset persistence**: filelog receiver resumes using persisted offsets after restart (no reset
  to the beginning). At-least-once replay is permitted; any duplicate records MUST be removed
  deterministically downstream (typically by `metadata.event_id` equality when the same cursor is
  re-read).

- **Syslog parsing (pa.syslog.v1)**: All syslog-derived fields used for `raw_parquet/unix/syslog/**`
  and `unix_syslog_fingerprint_v1` MUST be derived from the canonical `syslog_ast_v1` output of
  `pa.syslog.v1`.

- **Parser module vectors**: CI MUST execute parser-module vector suites for:

  - `pa.syslog.v1`
  - `pa.audit_event_key.v1`
  - `pa.auditd_record_kv.v1`

  and MUST assert `expected_ast` / `expected_errors` exactly, including deterministic `error_code`,
  `message_prefix`, and `location` fields.

- **Negative-path determinism**: Ingesting `syslog_invalid.log` and `audit_incomplete.log` MUST NOT
  silently mutate run outputs. Invalid records MUST be rejected deterministically (validated by the
  parser-module vectors) and MUST NOT appear as successfully parsed syslog/audit normalized events.

- **Audit correlation (audit_correlation_v1)**: Multi-record audit events with the same message ID
  MUST be correlated per `audit_correlation_v1` into a single normalized OCSF event (not multiple
  fragmented events).

- **Identity determinism**: Re-normalizing the same fixture produces byte-identical
  `metadata.event_id` values.

- **Unix source overlap gate**: When Unix sources are enabled, `logs/health.json` MUST include a
  `telemetry.unix.source_overlap` substage outcome. If overlap is detected without operator
  acknowledgment, the substage MUST be failed with `reason_code=unix_source_overlap_unacknowledged`
  and default `fail_mode=fail_closed`. If overlap is detected with operator acknowledgment, the
  substage MUST be failed with `reason_code=unix_source_overlap_active` and
  `fail_mode=warn_and_skip`.

- **Schema snapshots**: Each emitted `raw_parquet/unix/**` dataset directory MUST include
  `_schema.json` per `045_storage_formats.md`.

- **Unix flat-text withholding**: In v0.1, `raw/syslog/**` and `raw/audit/**` MUST be
  placeholder-only by default with `reason_code=unix_text_redaction_unsupported`, and normalized
  events MUST use `raw_ref.kind="dataset_row_v1"` pointing into `raw_parquet/**` (not
  `file_cursor_v1` pointing at a placeholder).

## Key decisions

- journald is the preferred ingestion path for modern Linux systems due to Tier 1 cursor-based
  identity.
- Syslog file tailing is supported for systems without journald or when explicit file evidence is
  required.
- Auditd multi-record correlation must be performed before OCSF mapping.
- Operators must choose a single source per event stream to avoid duplication.
- BSD and other Unix variants are explicitly out of scope for v0.1.

## References

- [Telemetry pipeline specification](040_telemetry_pipeline.md)
- [ADR-0002 "Event Identity and Provenance"](../adr/ADR-0002-event-identity-and-provenance.md)
- [Storage formats specification](045_storage_formats.md)
- [OCSF normalization specification](050_normalization_ocsf.md)
- [OTel journald receiver](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/receiver/journaldreceiver)
- [OTel filelog receiver](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/receiver/filelogreceiver)
- [OTel syslog receiver](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/receiver/syslogreceiver)
- [Red Hat: Troubleshooting with log files](https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/8/html/configuring_basic_system_settings/assembly_troubleshooting-problems-using-log-files_configuring-basic-system-settings)
- [Ubuntu: Viewing and monitoring log files](https://ubuntu.com/tutorials/viewing-and-monitoring-log-files)
- [journalctl(1) man page](https://man7.org/linux/man-pages/man1/journalctl.1.html)
- [Red Hat: Understanding audit log files](https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/7/html/security_guide/sec-understanding_audit_log_files)

## Changelog

| Date       | Change        |
| ---------- | ------------- |
| 2026-01-14 | Initial draft |
