---
title: R-07 osquery to OCSF Mapping Completeness
description: Mapping coverage matrix for osquery evented tables against the current osquery → OCSF 1.7.0 mapping profile, including gap prioritization and verification hooks.
status: draft
---

# R-07 osquery to OCSF Mapping Completeness

## Status

Draft (research report; mapping profile assessed as of 2026-01-14)

## Summary

This report answers:

- Which osquery evented tables are **currently mapped** to OCSF classes by the project's osquery →
  OCSF 1.7.0 mapping profile.
- Which tables are **unmapped** (coverage gaps), and a **P0/P1/P2** priority classification for
  closing those gaps.
- Which mapped tables have **partial field coverage** that is likely to impact downstream detection
  content.

**Key result:** The current profile routes **3 osquery query names** (`process_events`,
`socket_events`, `file_events`) into OCSF classes. Many high-value osquery evented tables remain
unmapped, including `user_events` (Linux authentication), eBPF-based tables, process-attributed file
events, and YARA scanning results.

## Inputs and scope

### In-scope artifacts

- Project mapping profile: `osquery_to_ocsf_1.7.0.md` (local file)
- osquery integration specification: `042_osquery_integration.md` (local file)
- osquery evented tables documentation

### Out of scope

- Implementing new mappings (this document identifies gaps and verification hooks only).
- Non-evented osquery tables (snapshot-only tables like `processes`, `users`, etc.).
- Windows Event Log sources collected via osquery (see R-06 for Windows Security coverage).

## Methodology

1. Extract "routed event families" and explicit `query_name` coverage from
   `osquery_to_ocsf_1.7.0.md`.

1. Compare against the osquery evented tables catalog across platforms.

1. For each table:

   - Mark as **Mapped** if present in the mapping profile's routed families.
   - If mapped, record the **OCSF class_uid** and documented field coverage.
   - Assign a **gap priority** using the criteria below.

## Gap priority definitions (P0/P1/P2)

- **P0:** High-signal endpoint telemetry that underpins common detection logic (e.g., authentication
  events, process-attributed file activity, malware scanning). Absence creates broad blind spots for
  cross-platform detection.
- **P1:** Valuable telemetry with meaningful detection value, but typically platform-specific,
  noisier, or requires additional configuration; recommended after P0 coverage.
- **P2:** Operability / niche / experimental tables; recommended only after P0/P1 or when required
  for a specific scenario.

## Query name to OCSF mapping matrix

### Currently routed query names (v0.1)

| Query name       | Platform          | OCSF target class        | `class_uid` | Coverage | Gap priority |
| ---------------- | ----------------- | ------------------------ | ----------: | -------- | ------------ |
| `process_events` | Linux, macOS      | Process Activity         |        1007 | Strong   | OK           |
| `socket_events`  | Linux, macOS      | Network Activity         |        4001 | Strong   | OK           |
| `file_events`    | Linux, macOS, Win | File System Activity     |        1001 | Partial  | OK (limited) |

### Unmapped evented tables (gaps)

#### Authentication and user activity

| Table name    | Platform     | Suggested OCSF class | Coverage | Gap priority |
| ------------- | ------------ | -------------------- | -------- | ------------ |
| `user_events` | Linux, macOS | Authentication       | None     | P0           |

#### Process activity alternatives

| Table name             | Platform | Suggested OCSF class | Coverage | Gap priority |
| ---------------------- | -------- | -------------------- | -------- | ------------ |
| `bpf_process_events`   | Linux    | Process Activity     | None     | P0           |
| `bpf_socket_events`    | Linux    | Network Activity     | None     | P0           |
| `process_etw_events`   | Windows  | Process Activity     | None     | P1           |
| `es_process_events`    | macOS    | Process Activity     | None     | P1           |

#### File activity with process attribution

| Table name               | Platform | Suggested OCSF class | Coverage | Gap priority |
| ------------------------ | -------- | -------------------- | -------- | ------------ |
| `process_file_events`    | Linux    | File System Activity | None     | P0           |
| `es_process_file_events` | macOS    | File System Activity | None     | P0           |
| `ntfs_journal_events`    | Windows  | File System Activity | None     | P1           |

#### Malware detection

| Table name    | Platform     | Suggested OCSF class | Coverage | Gap priority |
| ------------- | ------------ | -------------------- | -------- | ------------ |
| `yara_events` | Linux, macOS | Malware Finding      | None     | P0           |
| `yara`        | Linux, macOS | Malware Finding      | None     | P1           |

#### Security module events

| Table name        | Platform | Suggested OCSF class | Coverage | Gap priority |
| ----------------- | -------- | -------------------- | -------- | ------------ |
| `selinux_events`  | Linux    | Security Finding     | None     | P1           |
| `apparmor_events` | Linux    | Security Finding     | None     | P1           |

#### Hardware and system events

| Table name        | Platform          | Suggested OCSF class   | Coverage | Gap priority |
| ----------------- | ----------------- | ---------------------- | -------- | ------------ |
| `hardware_events` | Linux, macOS      | Device Config State    | None     | P1           |
| `disk_events`     | macOS             | Device Config State    | None     | P2           |
| `syslog_events`   | Linux             | Event Log Activity     | None     | P2           |

## Field coverage analysis

This section focuses on query names that are currently routed. Unrouted tables have **no** field
coverage because events are not present in normalized outputs.

### Pivot coverage for routed query names

| Query name       | OCSF class           | Actor process | Actor user | Target file | Network endpoints |
| ---------------- | -------------------- | ------------- | ---------- | ----------- | ----------------- |
| `process_events` | Process Activity     | Yes           | Partial    | No          | No                |
| `socket_events`  | Network Activity     | Yes           | Partial    | No          | Yes               |
| `file_events`    | File System Activity | **N/A**       | Partial    | Yes         | No                |

### Notable partial coverage and limitations (current routed set)

- **`file_events` (File System Activity):** routed to **File System Activity (1001)** but
  `actor.process.*` is explicitly **N/A** because `file_events` does not provide initiating process
  attribution. This is a fundamental limitation of the osquery FIM table. Detections requiring
  process context for file writes MUST use `process_file_events` (Linux) or `es_process_file_events`
  (macOS) instead.

- **`socket_events` (Network Activity):** routed to **Network Activity (4001)** with strong
  endpoint coverage. Direction inference is best-effort based on action (`connect`, `accept`,
  `bind`). This table is **not available on Windows**.

- **`process_events` (Process Activity):** routed to **Process Activity (1007)** with strong
  coverage. User attribution depends on audit configuration; `actor.user.uid` is populated when
  available but username resolution requires additional context.

- **Snapshot rows (`action=snapshot`):** All routed tables emit snapshot rows with
  `activity_id = 99` (Other) because snapshot rows represent point-in-time state observations rather
  than discrete activity events.

## P0/P1/P2 gap breakdown

### P0 gaps (recommended next)

These tables commonly underpin high-value cross-platform detection content:

- **`user_events` (Linux authentication)** — Linux companion to `process_events` that provides
  authentication-based events including failed logins, sudo usage, and user session changes. This is
  a critical gap for Linux authentication monitoring.

- **`bpf_process_events` / `bpf_socket_events` (eBPF-based)** — Modern Linux alternative to
  audit-based tables with better container visibility, lower overhead potential, and no conflict
  with auditd. Requires kernel >= 4.18.

- **`process_file_events` (Linux) / `es_process_file_events` (macOS)** — File activity tables WITH
  process attribution. Essential for detections that require knowing which process created/modified
  a file. Without these, `file_events` provides limited detection value.

- **`yara_events`** — Real-time YARA-based malware detection triggered by file changes. This enables
  automated malware scanning and indicator matching without external tooling.

### P1 gaps (recommended after P0)

- **`process_etw_events` (Windows)** — ETW-backed Windows process execution telemetry. Reliability
  is build-dependent but provides Windows process coverage when Sysmon is not deployed.
- **`es_process_events` (macOS)** — EndpointSecurity-based process events, intended to replace
  deprecated OpenBSM.
- **`ntfs_journal_events` (Windows)** — NTFS USN journal-based file integrity monitoring. Does not
  include process attribution but provides Windows FIM capability.
- **`selinux_events` / `apparmor_events` (Linux)** — Security module policy violation events.
  Valuable for detecting privilege escalation and policy bypass attempts.
- **`yara` (on-demand table)** — On-demand YARA scanning table for forensic investigation.
- **`hardware_events`** — Hardware change events useful for detecting unauthorized device
  connections (USB, etc.).

### P2 gaps (defer unless scenario-driven)

- **`disk_events` (macOS)** — Disk mount/unmount events; niche use case.
- **`syslog_events` (Linux)** — System log events; typically better sourced from dedicated syslog
  collection.

## Platform coverage summary

The current mapping profile has significant platform coverage gaps:

| Platform | Process events | Network events | File events | Auth events |
| -------- | -------------- | -------------- | ----------- | ----------- |
| Linux    | ✓ (Strong)     | ✓ (Strong)     | Partial     | **Gap**     |
| macOS    | ✓ (Strong)     | ✓ (Strong)     | Partial     | **Gap**     |
| Windows  | **Gap**        | **Gap**        | Partial     | N/A         |

**Windows gaps are particularly notable:**

- `socket_events` is not available on Windows (macOS/Linux only).
- `process_events` requires either `process_etw_events` (ETW-based, reliability varies) or external
  sources like Sysmon.
- Windows network connection normalization MUST be sourced from a non-osquery telemetry provider or
  treated as out of scope.

## Verification hooks for closing gaps

For each table promoted to "routed" (especially P0/P1):

1. **Golden input fixtures**

   - Provide representative osquery NDJSON payloads for the table.
   - Include edge cases: `action` variants (`added`, `removed`, `snapshot`), missing optional
     fields, platform-specific field availability.

1. **Golden normalized output**

   - Expected OCSF JSON events (canonical form) with stable `class_uid`, `activity_id`, and stable
     identity/provenance fields.

1. **CI gates**

   - A test MUST fail if a routed `query_name` is missing from output when its input fixture is
     present.
   - A test MUST fail if required pivots for the table are absent (per the acceptance list below).

### Minimum acceptance criteria per routed query name

When adding a new osquery table route, the normalizer MUST:

- Emit the correct `class_uid` and `activity_id` for every fixture input.
- Populate `device.*` identity and `metadata.*` provenance fields per ADR-0002 (event identity and
  provenance).
- Handle `action=snapshot` rows with `activity_id = 99` (Other).
- Preserve raw payload under `unmapped.osquery.*` namespace.

## Appendix A: Expected detection impact by gap

This appendix describes how each gap is expected to affect detection content.

### Why osquery table coverage matters

osquery provides cross-platform endpoint telemetry that enables unified detection logic across
Linux, macOS, and (partially) Windows. Missing table coverage translates directly into platform
blind spots.

Unlike Sigma rules (which target specific log sources), osquery-based detections typically query
osquery tables directly or through scheduled query results. Missing table mappings mean those events
cannot be normalized into OCSF and evaluated against detection rules.

### P0 gaps and expected detection impact

#### `user_events` (Linux authentication)

**Available fields** commonly include:

- `type` (authentication event type)
- `uid`, `auid` (user IDs)
- `pid` (associated process)
- `message` (event details)
- `time` (event timestamp)

**Expected impact if unmapped:**

- Linux authentication monitoring will be absent from normalized OCSF outputs.
- Failed login detection, sudo abuse detection, and user session tracking will not be available.
- This is the primary authentication telemetry source for osquery on Linux.

#### `bpf_process_events` / `bpf_socket_events` (eBPF-based)

**Available fields** commonly include:

- Full process context: `pid`, `ppid`, `uid`, `gid`, `cgroup_id`
- Execution details: `path`, `cmdline`, `cwd`
- Container-aware fields: better namespace visibility than audit-based tables
- Duration and timing information

**Expected impact if unmapped:**

- Modern Linux deployments using eBPF instead of audit cannot normalize process/socket events.
- Container workloads with limited audit visibility will have reduced telemetry coverage.
- Organizations avoiding auditd conflicts cannot use osquery process telemetry.

#### `process_file_events` / `es_process_file_events` (process-attributed file events)

**Available fields** commonly include:

- File details: `target_path`, `action`, `md5`, `sha256`
- **Process attribution**: `pid`, `ppid`, `uid`, `gid`, `path` (of the process)
- Timing: `time`, `uptime`

**Expected impact if unmapped:**

- File-based detections requiring process context will not function.
- Malware persistence detection (file drops by suspicious processes) will be unavailable.
- This addresses the fundamental limitation of `file_events` lacking actor process context.

#### `yara_events` (YARA-based malware detection)

**Available fields** commonly include:

- `target_path` (scanned file)
- `matches` (matched YARA rules)
- `strings` (matched strings if enabled)
- `count` (match count)
- `category` (file category)

**Expected impact if unmapped:**

- Real-time malware indicator matching will not be normalized.
- YARA-based threat hunting workflows will require separate tooling.
- Automated IOC matching against file changes will be absent.

### P1/P2 gaps: expected detection impact (summary)

- **`process_etw_events` (Windows):** impacts Windows process visibility when Sysmon is not
  deployed; reliability is build-dependent.
- **`selinux_events` / `apparmor_events` (Linux):** impacts security policy violation detection;
  valuable for detecting privilege escalation and policy bypass.
- **`hardware_events`:** impacts unauthorized device detection (USB monitoring, etc.).
- **`ntfs_journal_events` (Windows):** impacts Windows FIM but lacks process attribution.

## Known limitations in the current profile

The mapping profile documents several known limitations for v0.1:

1. **`file_events` lacks process attribution:** Initiating process attribution is not available.
   `actor.process.*` is explicitly N/A and MUST NOT be inferred. Use `process_file_events` or
   `es_process_file_events` for process-attributed file activity.

1. **`socket_events` not available on Windows:** Windows network connection normalization MUST be
   sourced from a non-osquery telemetry provider.

1. **Snapshot rows are state observations:** Snapshot rows represent bulk table state at a point in
   time, not discrete per-entity events. They are normalized with `activity_id = 99` (Other).

1. **Identity is Tier 3:** osquery does not provide a stable record ID. Event identity is computed
   from canonicalized payload hashing, which may increase computational cost for large snapshots.

1. **Platform-specific backend differences:** eBPF tables require kernel >= 4.18. Audit-based tables
   conflict with auditd. EndpointSecurity tables require Full Disk Access on macOS.

## References (descriptive)

- osquery documentation: Process Auditing
- osquery documentation: File Integrity Monitoring
- osquery documentation: YARA Scanning
- Fleet documentation: osquery evented tables overview
- osquery GitHub: evented table specifications