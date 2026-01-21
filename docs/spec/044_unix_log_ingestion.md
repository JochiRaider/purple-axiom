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
files on the same host, duplicate events are expected unless explicitly prevented.

### Required policy (v0.1)

Operators must choose one of the following strategies per host:

1. **journald-only (preferred)**: Ingest via the `journald` receiver. Do not tail `/var/log/syslog`
   or `/var/log/messages` for the same event stream.

1. **File-only**: Tail `/var/log/*` files via `filelog`. Do not use the `journald` receiver for
   overlapping content.

1. **Explicit overlap dedupe (discouraged; implementation-defined)**: If both journald ingestion
   (`_TRANSPORT=syslog`) and syslog file tailing are enabled for overlapping syslog content, the
   dataset is expected to contain semantic duplicates. Implementations MUST NOT attempt to remove
   these duplicates by comparing `metadata.event_id` (Tier 1 cursor-based IDs and Tier 2
   artifact-cursor IDs will differ by design).

   If an implementation supports an overlap dedupe mode, it MUST be explicitly enabled and MUST be
   recorded in the run manifest as `telemetry.unix.dedupe_strategy`. For v0.1, the only allowed
   overlap dedupe strategy token is `unix_syslog_fingerprint_v1`, defined as:

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

   - `event_time_epoch_seconds` MUST be computed as `floor(event_time_epoch_ms / 1000)` using the
     event timestamp after syslog parsing and time normalization.

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

The pipeline must not silently ingest both sources without explicit operator acknowledgment.

### Configuration enforcement

When `telemetry.sources.unix.journald.enabled=true` and `telemetry.sources.unix.syslog_files`
includes paths that overlap with journald-forwarded content, the validator should emit a warning and
must record the overlap in `runs/<run_id>/logs/telemetry_validation.json`.

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
| `syslog`             | `linux_syslog`         |
| `journal`            | `linux_journald`       |
| `stdout`             | `linux_journald`       |
| `kernel`             | `linux_journald`       |
| `audit`              | `linux_auditd`         |

This mapping MUST remain consistent with "Normalization to OCSF" → "Source type assignment".

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

The receiver should include parsing operators to extract structured fields from syslog messages. At
minimum, extract timestamp, host, app, pid (when present), facility, severity, and message.

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

### Identity basis (Tier 2)

Syslog text logs lack a source-native unique identifier. Repeated byte-identical messages in the
same timestamp bucket are common. Per ADR-0002, use Tier 2 when a stable cursor exists:

```json
{
  "source_type": "linux_syslog",
  "origin.host": "<emitting_host>",
  "stream.name": "<log_file_name>",
  "stream.cursor": "<line_index_or_byte_offset>"
}
```

Rules:

- `stream.name` must be a stable identifier for the stored artifact (for example, `syslog`,
  `messages`, `auth`).
- `stream.cursor` must be stable under reprocessing (for example, `li:12345` for line index or
  `bo:98765` for byte offset).
- Ephemeral collector offsets must not be used unless persisted with the stored artifact.

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

### Identity basis

#### Tier 1 (aggregated audit events)

When audit records are aggregated into a single logical event before normalization:

```json
{
  "source_type": "linux_auditd",
  "origin.host": "<emitting_host>",
  "origin.audit_node": "<node_value_if_present>",
  "origin.audit_msg_id": "audit(<epoch>.<fractional>:<serial>)"
}
```

Rules:

- `origin.audit_msg_id` must be the literal substring from the raw record, captured exactly.
- Implementations must not parse the timestamp into floating point.
- Implementations must not normalize fractional precision.

#### Tier 2 (per-record without aggregation)

If each audit record line is normalized independently (not recommended), use Tier 2 with a stable
artifact cursor to avoid identity collisions across records within the same event:

```json
{
  "source_type": "linux_auditd",
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
│   ├── syslog                    # Copied /var/log/syslog (Debian)
│   ├── messages                  # Copied /var/log/messages (RHEL)
│   └── auth.log                  # Copied /var/log/auth.log
└── audit/
    └── audit.log                 # Copied /var/log/audit/audit.log
```

Notes:

- Staged files are evidence-tier representations for reproducibility and MUST follow the effective
  redaction posture (redacted-safe, withheld, or quarantined) under the project redaction policy.
- The pipeline may convert staged text to Parquet under `raw_parquet/`.
- Rotation and truncation during the run window should be handled by staging complete files or by
  recording the byte range captured.

## Derived raw Parquet (optional but recommended)

### Syslog Parquet schema

When converting syslog text to Parquet, include at minimum:

| Column     | Type   | Notes                                    |
| ---------- | ------ | ---------------------------------------- |
| `time`     | int64  | Epoch ms (derived from syslog timestamp) |
| `host`     | string | Hostname from syslog header              |
| `app`      | string | Application name                         |
| `pid`      | int32  | Process ID (nullable)                    |
| `facility` | string | Syslog facility (nullable)               |
| `severity` | string | Syslog severity (nullable)               |
| `message`  | string | Message body                             |
| `raw`      | string | Original line (nullable)                 |

### Audit Parquet schema

When converting audit.log to Parquet, aggregate by message ID first, then include:

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
| journald (syslog transport)      | `linux_syslog`         |
| journald (journal/stdout/kernel) | `linux_journald`       |
| journald (audit transport)       | `linux_auditd`         |
| filelog on syslog files          | `linux_syslog`         |
| filelog on audit.log             | `linux_auditd`         |
| syslog receiver (network)        | `linux_syslog`         |

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

Add fixtures under `tests/fixtures/unix_logs/` (recommended convention):

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
- **Audit correlation**: Multi-record audit events with the same message ID produce a single
  normalized OCSF event (not multiple fragmented events).
- **Identity determinism**: Re-normalizing the same fixture produces byte-identical
  `metadata.event_id` values.
- **Duplication warning**: Enabling both journald and overlapping syslog file ingestion produces a
  validation warning.

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
