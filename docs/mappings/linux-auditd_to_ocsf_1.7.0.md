---
title: Linux auditd to OCSF 1.7.0 mapping profile v0.1
description: Defines the Linux auditd mapping profile for Purple Axiom's OCSF 1.7.0 normalizer.
status: draft
---

# Linux auditd to OCSF 1.7.0 mapping profile v0.1

## Overview

This mapping profile defines how aggregated Linux auditd events route to OCSF classes and which
fields must be populated for v0.1. It aligns auditd normalization with deterministic identity,
coverage, and provenance expectations used by the mapping packs.

This document defines the Linux auditd mapping profile for Purple Axiom's OCSF 1.7.0 normalizer. It
describes the routing and field mapping expectations for v0.1.

## Purpose

This document is designed to be:

- implementable (rules are explicit and deterministic)
- reviewable (humans can validate class and field intent)
- testable (fixtures can assert routing, semantics, and coverage)

The machine-executable mapping rules referenced by this document live under:

- `mappings/normalizer/ocsf/1.7.0/linux-auditd/**`

## Scope

This document covers:

- Linux audit subsystem events from `/var/log/audit/audit.log` or journald with `_TRANSPORT=audit`
- Aggregated audit events (multi-record correlation by `msg=audit(<timestamp>:<serial>)`)
- Debian/Ubuntu and RHEL-family distributions
- The v0.1 routed record types required by the coverage matrix fixture minimum:
  - EXECVE/SYSCALL (process activity)
  - PATH with file operations (file system activity)
  - SOCKADDR (network activity)
  - USER_LOGIN, USER_AUTH (authentication)

This document does NOT cover:

- Per-record normalization without aggregation (each audit line as separate event)
- BSD, macOS, or other Unix variants
- AVC (SELinux/AppArmor) policy denial events
- Audit configuration events (CONFIG_CHANGE, DAEMON\_\*)
- Full coverage of all audit record types

## Mapping stance for OCSF-core plus Purple pivots

This profile follows the project's "OCSF-core plus pivots" strategy:

1. **OCSF-native primary fields MUST be populated** when authoritative source values exist.
1. **Convenience pivots MAY be populated** to support cross-source joins, but MUST NOT conflict with
   OCSF-native values.

Constraints (normative):

- The mapping MUST NOT infer values (no synthesis from unrelated fields).
- If a value is not authoritative, the field MUST be absent (not null, not empty string).
- If multiple possible inputs exist, the profile MUST define a stable precedence order.

### UID-to-name resolution policy

Linux audit records provide numeric UIDs (uid, auid, euid, etc.) but not usernames. Resolving
UID-to-name requires access to `/etc/passwd` or equivalent identity stores.

Policy (normative for v0.1):

- `actor.user.uid` MUST be populated from the authoritative numeric UID when present.
- `actor.user.name` MAY be populated only when a deterministic, snapshotted context (e.g.,
  `/etc/passwd` captured at run start) is available and explicitly configured.
- UID-to-name resolution MUST NOT perform runtime lookups against live system files or external
  identity services.
- If UID-to-name resolution is not configured, `actor.user.name` MUST be absent.

This aligns with the coverage matrix designation of `actor.user.name` as `O[U]` (optional) for
auditd.

### Device IP representation

The v0.1 coverage matrix allows either `device.ip` or `device.ips[]` to satisfy the "device IP
pivot". This profile SHOULD prefer `device.ips[]` for consistency and multi-IP representation.

- If only one IP is authoritative, emitting `device.ip` alone is permitted, but implementations
  SHOULD also emit `device.ips[] = [device.ip]` when supported (sorted, de-duplicated).
- Device IP is typically derived from inventory context rather than audit records themselves.

## Inputs and prerequisites

This profile assumes the canonical Linux audit ingestion and staging defined in:

- [Unix log ingestion specification](../spec/044_unix_log_ingestion.md) (telemetry, multi-record
  correlation, identity basis)
- [OCSF normalization specification](../spec/050_normalization_ocsf.md) (pinned OCSF version,
  envelope requirements, coverage artifacts)
- [OCSF field tiers reference](../spec/055_ocsf_field_tiers.md) and
  [coverage matrix](coverage_matrix.md) (tier semantics and CI conformance)

### Multi-record aggregation prerequisite (critical)

Linux audit events frequently consist of multiple record lines sharing a common
`msg=audit(<epoch>.<fractional>:<serial>)` identifier. A single semantic event (e.g., a process
execution) may produce SYSCALL, EXECVE, PATH, CWD, PROCTITLE, and EOE records.

**Normative requirement**: The normalizer MUST receive pre-aggregated audit events where all records
sharing the same `msg=audit(...)` identifier have been correlated into a single input object. This
aggregation MUST occur before OCSF mapping.

Acceptable aggregation points:

1. journald (may pre-correlate related records into a single journal entry)
1. OTel transform processor (buffer and aggregate by audit message ID)
1. Normalizer pre-processing stage (aggregate raw lines before routing)

The mapping profile assumes aggregated input and does not define per-line routing behavior.

### Expected raw input shape

The normalizer is expected to receive aggregated audit events containing:

- `audit_msg_id` (string): The literal `msg=audit(<epoch>.<fractional>:<serial>)` substring,
  preserved exactly as emitted
- `hostname` (string): The originating host identifier
- `node` (string, optional): The audit node value if present in the record
- `record_type` (string): Primary record type for routing (SYSCALL, USER_LOGIN, etc.)
- `syscall` (string or integer, optional): Syscall number for SYSCALL records
- `fields` (object): Merged key-value pairs from all correlated records, including:
  - `uid`, `auid`, `euid`, `suid`, `fsuid` (numeric strings)
  - `gid`, `egid`, `sgid`, `fsgid` (numeric strings)
  - `pid`, `ppid` (numeric strings)
  - `comm`, `exe` (strings)
  - `cwd` (string, from CWD record)
  - `proctitle` (string, from PROCTITLE record, may be hex-encoded)
  - `path`, `name`, `nametype` (from PATH records, may be multiple)
  - `saddr` (hex-encoded socket address, from SOCKADDR record)
  - `success` (string: "yes" or "no")
  - `exit` (string: syscall return value)

The mapping MUST NOT depend on:

- Locale-specific field representations
- Parsed floating-point timestamp values (use the literal `audit_msg_id` string)
- Fields that require external resolution (DNS, LDAP, etc.)

## Canonicalization rules for determinism

Canonicalization is applied prior to mapping and hashing.

### Strings

- MUST be trimmed of leading/trailing ASCII whitespace.
- MUST preserve original case unless a field is explicitly case-normalized below.

### Hostnames

- `device.hostname` SHOULD be lowercased when populated from `hostname`.

### Numeric UIDs and GIDs

Audit records represent UIDs and GIDs as decimal integer strings.

- Numeric strings MUST be parsed as base-10 integers.
- `actor.user.uid` MUST be emitted as a string (per Tier 2 standard user shape), representing the
  base-10 UID with no leading zeros (except UID `0` represented as `"0"`).
- Unresolvable values (e.g., `4294967295` for "unset") SHOULD be treated as absent unless the
  project defines an explicit "unset" convention.

### PIDs

- `pid`, `ppid`, and related fields MUST be parsed as base-10 integers.
- If parsing fails, the target field MUST be absent.

### Hex-encoded fields

Several audit fields may be hex-encoded:

- `proctitle`: Hex-encoded command line (each byte as two hex digits)
- `saddr`: Hex-encoded socket address structure
- `name` in PATH records: May be hex-encoded if it contains special characters

Rules:

- Hex-encoded `proctitle` MUST be decoded to UTF-8 (or the system locale encoding) before mapping to
  `process.cmd_line`. Invalid byte sequences SHOULD be replaced with a placeholder or cause the
  field to be absent.
- Hex-encoded `saddr` MUST be parsed according to the socket address family (AF_INET, AF_INET6,
  AF_UNIX) to extract IP addresses and ports.
- Hex-encoded `name` fields MUST be decoded before mapping to file paths.
- If hex decoding fails, the target field MUST be absent and the raw hex value MAY be preserved
  under `unmapped.auditd.*`.

### Paths

- Linux paths use `/` as the separator.
- When deriving `file.name` from a path, the basename algorithm MUST:
  - treat `/` as the separator
  - ignore trailing separators
  - return the final non-empty segment
- When splitting `file.parent_folder` and `file.name`, the split MUST:
  - be deterministic
  - set `file.name` to basename, and `file.parent_folder` to the remaining prefix (if any)

### Audit message ID preservation

The `audit_msg_id` field (`msg=audit(<epoch>.<fractional>:<serial>)`) is critical for identity.

Rules (normative):

- The `audit_msg_id` MUST be captured and preserved exactly as it appears in the raw record.
- Implementations MUST NOT parse the timestamp component into a floating-point number.
- Implementations MUST NOT normalize the fractional precision.
- The literal string is used for identity hashing.

## Classification and identifiers

### OCSF version pinning

- This profile targets `ocsf_version = "1.7.0"` and expects the run to record that pin in
  provenance.

### Class routing

Routing is based on the primary `record_type` of the aggregated audit event.

The routing table is normative and versioned in:

- `mappings/normalizer/ocsf/1.7.0/linux-auditd/routing.yaml`

v0.1 required routes:

| Primary record type | OCSF target class    | `class_uid` | `category_uid` |
| ------------------- | -------------------- | ----------: | -------------: |
| SYSCALL (execve)    | Process Activity     |        1007 |              1 |
| SYSCALL (file ops)  | File System Activity |        1001 |              1 |
| SYSCALL (network)   | Network Activity     |        4001 |              4 |
| USER_LOGIN          | Authentication       |        3002 |              3 |
| USER_AUTH           | Authentication       |        3002 |              3 |

Category UID values (OCSF 1.7.0):

- `1` = System Activity
- `3` = Identity & Access Management
- `4` = Network Activity

**Routing disambiguation for SYSCALL records**:

SYSCALL records require secondary discrimination based on the `syscall` number to determine the
appropriate OCSF class:

| Syscall family | Example syscalls                      | OCSF class           |
| -------------- | ------------------------------------- | -------------------- |
| exec           | execve (59), execveat (322)           | Process Activity     |
| file           | open, openat, unlink, rename, chmod   | File System Activity |
| network        | connect, accept, bind, socket, sendto | Network Activity     |

The routing configuration MUST define explicit syscall-to-class mappings. Unrecognized syscalls MUST
NOT be silently dropped; they MUST be counted as unrouted in `mapping_coverage.json`.

**Unrouted behavior (normative)**:

- The normalizer MUST NOT guess a `class_uid` for an unrecognized record type or syscall.
- Unrouted events MUST be preserved in `raw/` and MUST be counted as unrouted/unmapped in
  `normalized/mapping_coverage.json`.

### OCSF classification fields

For every emitted event, the normalizer MUST set:

- `class_uid`
- `activity_id`
- `type_uid`

Rules:

- `type_uid` MUST be computed as: `class_uid * 100 + activity_id`.
- `category_uid` SHOULD be set when known for the class.
- `severity_id` MAY be set if an authoritative mapping exists; otherwise it MUST be absent.

### Event identity and metadata uid

Linux auditd with aggregated events provides Tier 1 identity per
[ADR-0002 Event identity and provenance](../adr/ADR-0002-event-identity-and-provenance.md).

Identity basis (normative):

```json
{
  "source_type": "linux_auditd",
  "origin.host": "<hostname>",
  "origin.audit_node": "<node_if_present>",
  "origin.audit_msg_id": "audit(<epoch>.<fractional>:<serial>)"
}
```

Rules (normative):

- `origin.audit_msg_id` MUST be the literal substring from the raw record, captured exactly.
- Implementations MUST NOT parse the timestamp into floating point.
- Implementations MUST NOT normalize fractional precision.
- `origin.audit_node` is included only when the `node=` field is present in the raw record.

Normative requirements (per ADR-0002 and the OCSF field tiers reference Tier 0):

- `metadata.uid` MUST be present and MUST equal `metadata.event_id`.
- `metadata.event_id` MUST be computed from the identity basis above using RFC 8785 (JCS)
  canonicalization and SHA-256 hashing per the project standard.

### Source event ID mapping

Because the audit message ID is a compound value (timestamp + serial), implementations SHOULD set:

- `metadata.source_event_id = <audit_msg_id_literal>`

This preserves the native audit identifier for forensic traceability.

## Field mapping for all routed auditd events

This section defines baseline field population rules that apply to all routed audit records.

### Metadata for source provenance

At minimum:

- `metadata.product.name` SHOULD be `auditd`.
- `metadata.source_type` MUST be `linux_auditd`.
- `metadata.source_event_id` SHOULD be set to the `audit_msg_id` literal.
- `metadata.log_name` SHOULD be `audit.log` or `journald:audit` depending on ingestion path.

### Device

Device identity for auditd MUST be deterministic and SHOULD be consistent with other sources.

Rules:

- `device.name` MUST be populated from `hostname` when present.
- `device.hostname` SHOULD be populated from `hostname` when the value is a hostname-like string.
  - `device.hostname` SHOULD be lowercased for cross-source join consistency.
- `device.uid` MUST be populated from deterministic run context when available (recommended:
  resolved `asset_id` from the inventory snapshot). If `device.uid` cannot be resolved
  deterministically, it MUST be absent rather than guessed.
- `device.ip` / `device.ips[]` MAY be populated only when an authoritative device IP exists in
  deterministic run context. Audit records themselves rarely contain device IP.

### Actor user

Linux audit records provide rich numeric principal information.

Rules:

- `actor.user.uid` MUST be populated from the authoritative UID field. Precedence order when
  multiple UID fields are present:
  1. `auid` (audit UID / login UID) — preferred for tracking the original login identity
  1. `uid` (effective UID at syscall time)
  1. `euid` (effective UID)
- The selected UID MUST be emitted as a base-10 string with no leading zeros.
- `actor.user.name` MAY be populated only from a deterministic, snapshotted context (see
  "UID-to-name resolution policy").
- `actor.user.domain` is `N/A` for Linux audit sources and MUST remain absent.

### Actor process

When process context is available (typically from SYSCALL records):

- `actor.process.pid` SHOULD be populated from `pid` when present and parseable.
- `actor.process.parent_process.pid` SHOULD be populated from `ppid` when present and parseable.
- `actor.process.file.path` SHOULD be populated from `exe` when present.
- `actor.process.name` MUST be derived from `exe` using the deterministic basename algorithm when
  `exe` is present. If `exe` is absent but `comm` is present, `actor.process.name` MAY be populated
  from `comm`.
- `actor.process.cmd_line` MAY be populated from decoded `proctitle` only when present and permitted
  by redaction policy.

### Raw retention and unmapped preservation

For every routed audit record, the normalizer MUST preserve source-specific fields under the
`unmapped` namespace:

- `unmapped.auditd.audit_msg_id`
- `unmapped.auditd.record_type`
- `unmapped.auditd.syscall` (when applicable)
- `unmapped.auditd.success`
- `unmapped.auditd.exit`

Namespace rationale:

- This profile uses `unmapped.<source_type>.*` to clearly indicate fields not mapped to OCSF-native
  fields.
- The `unmapped` namespace aligns with the OCSF normalization specification guidance.

## Routed event families for v0.1

This section defines the v0.1 required audit routes and their minimal field mapping obligations.

### Process activity for execve syscalls

Class:

- Process Activity (`class_uid = 1007`)

Classification (normative):

- `category_uid` MUST be `1` (System Activity).
- `type_uid` MUST be computed as `class_uid * 100 + activity_id`.

#### Syscalls and activities

| Syscall  | Syscall number (x86_64) | activity_id |
| -------- | ----------------------: | ----------: |
| execve   |                      59 |  1 (Launch) |
| execveat |                     322 |  1 (Launch) |

Note: Syscall numbers are architecture-dependent. The mapping pack SHOULD support configurable
syscall number tables or use symbolic names when the aggregator provides them.

#### Field mapping rules for execve

Authoritative inputs from aggregated audit event:

- `exe` (executable path)
- `pid`, `ppid`
- `uid`, `auid`, `euid`
- `comm` (command name, 16-char max)
- `proctitle` (full command line, may be hex-encoded)
- `cwd` (current working directory, from CWD record)
- `success`, `exit`

Rules:

- `process.pid` MUST be populated from `pid` when present and parseable.
- `process.file.path` MUST be populated from `exe` when present.
- `process.name` MUST be derived from `exe` using the deterministic basename algorithm.
- `process.cmd_line` MAY be populated from decoded `proctitle` only when present and permitted by
  redaction policy.
- `process.parent_process.pid` SHOULD be populated from `ppid` when present and parseable.
- `process.cwd` SHOULD be populated from `cwd` when present.

Actor (initiating context):

- For execve, `actor.process.*` represents the parent process context. Populate from `ppid` and any
  available parent process fields.
- `actor.user.uid` MUST be populated per the actor user rules above.

Status mapping:

- `status_id` SHOULD be derived from `success`:
  - `success = "yes"` → `status_id = 1` (Success)
  - `success = "no"` → `status_id = 2` (Failure)
  - absent or unparseable → `status_id` absent

### File system activity for file operation syscalls

Class:

- File System Activity (`class_uid = 1001`)

Classification (normative):

- `category_uid` MUST be `1` (System Activity).
- `type_uid` MUST be computed as `class_uid * 100 + activity_id`.

#### Syscalls and activities

| Syscall family | Example syscalls (x86_64)     | activity_id      |
| -------------- | ----------------------------- | ---------------- |
| open/create    | open (2), openat (257), creat | 1 (Create)       |
| read           | read (0), pread64             | 2 (Read)         |
| write          | write (1), pwrite64           | 3 (Update)       |
| delete         | unlink (87), unlinkat (263)   | 4 (Delete)       |
| rename         | rename (82), renameat (264)   | 5 (Rename)       |
| chmod/chown    | chmod, fchmod, chown, fchown  | 7 (Set Security) |

Note: Activity ID mapping depends on the specific syscall. The mapping pack MUST define explicit
syscall-to-activity mappings.

#### Field mapping rules for file operations

Authoritative inputs from aggregated audit event:

- `name` (from PATH record — target file path or name)
- `nametype` (from PATH record — indicates CREATE, DELETE, NORMAL, etc.)
- `cwd` (from CWD record)
- `pid`, `ppid`, `exe`
- `uid`, `auid`
- `success`, `exit`

Rules:

- `file.path` MUST be populated by combining `cwd` and `name` when `name` is relative, or from
  `name` directly when absolute.
- `file.name` MUST be derived from the resolved path using the deterministic basename algorithm.
- `file.parent_folder` MUST be derived from the resolved path using the deterministic split rule.
- `actor.process.pid` SHOULD be populated from `pid` when present and parseable.
- `actor.process.file.path` SHOULD be populated from `exe` when present.
- `actor.user.uid` MUST be populated per the actor user rules above.

PATH record handling:

- Aggregated audit events may contain multiple PATH records (e.g., source and destination for rename
  operations).
- The mapping MUST define a deterministic rule for selecting the primary file target.
- For rename operations, the mapping SHOULD populate both source and destination fields if the OCSF
  class supports them.

### Network activity for network syscalls

Class:

- Network Activity (`class_uid = 4001`)

Classification (normative):

- `category_uid` MUST be `4` (Network Activity).
- `type_uid` MUST be computed as `class_uid * 100 + activity_id`.

#### Syscalls and activities

| Syscall  | Syscall number (x86_64) | activity_id |
| -------- | ----------------------: | ----------- |
| connect  |                      42 | 1 (Open)    |
| accept   |                      43 | 1 (Open)    |
| bind     |                      49 | 4 (Bind)    |
| listen   |                      50 | 5 (Listen)  |
| sendto   |                      44 | 6 (Send)    |
| recvfrom |                      45 | 7 (Receive) |

#### Field mapping rules for network operations

Authoritative inputs from aggregated audit event:

- `saddr` (SOCKADDR record — hex-encoded socket address structure)
- `pid`, `ppid`, `exe`
- `uid`, `auid`
- `success`, `exit`

SOCKADDR parsing (normative):

The `saddr` field is a hex-encoded socket address structure. The first two bytes indicate the
address family:

- `0200` = AF_INET (IPv4)
- `0A00` = AF_INET6 (IPv6)
- `0100` = AF_UNIX (local socket)

For AF_INET (`saddr` structure):

- Bytes 0-1: Address family (0x0002)
- Bytes 2-3: Port (network byte order)
- Bytes 4-7: IPv4 address (network byte order)

For AF_INET6 (`saddr` structure):

- Bytes 0-1: Address family (0x000A)
- Bytes 2-3: Port (network byte order)
- Bytes 4-7: Flow info
- Bytes 8-23: IPv6 address
- Bytes 24-27: Scope ID

Rules:

- `dst_endpoint.ip` MUST be populated from parsed `saddr` for connect/sendto syscalls.
- `dst_endpoint.port` SHOULD be populated from parsed `saddr` when present.
- `src_endpoint.ip` SHOULD be populated from parsed `saddr` for bind/accept syscalls when
  applicable.
- `actor.process.pid` SHOULD be populated from `pid` when present and parseable.
- `actor.user.uid` MUST be populated per the actor user rules above.

AF_UNIX handling:

- For AF_UNIX sockets, IP and port fields are `N/A`.
- The socket path MAY be preserved under `unmapped.auditd.unix_socket_path`.
- The mapping SHOULD still emit a Network Activity event with available process context.

### Authentication for USER_LOGIN and USER_AUTH

Class:

- Authentication (`class_uid = 3002`)

Classification (normative):

- `category_uid` MUST be `3` (Identity & Access Management).
- `type_uid` MUST be computed as `class_uid * 100 + activity_id`.

#### Record types and activities

| Record type | activity_id |
| ----------- | ----------- |
| USER_LOGIN  | 1 (Logon)   |
| USER_AUTH   | 1 (Logon)   |
| USER_LOGOUT | 2 (Logoff)  |

Note: USER_AUTH typically represents PAM authentication attempts. Both USER_LOGIN and USER_AUTH map
to the Logon activity as they represent authentication events.

#### Field mapping rules for authentication

Authoritative inputs from audit record:

- `auid` (audit/login UID)
- `uid` (effective UID)
- `acct` (account name, when present)
- `hostname` (remote host for network logins)
- `addr` (remote IP address, when present)
- `terminal` (tty or pts)
- `res` (result: "success" or "failed")

Rules:

- `actor.user.uid` MUST be populated from `auid` when present; fall back to `uid`.
- `actor.user.name` MAY be populated from `acct` when present (this is authoritative, not a lookup).
- `src_endpoint.ip` SHOULD be populated from `addr` when present and valid.
- `src_endpoint.hostname` MAY be populated from `hostname` when present.
- `status_id` MUST be derived from `res`:
  - `res = "success"` → `status_id = 1` (Success)
  - `res = "failed"` → `status_id = 2` (Failure)
  - absent or unparseable → `status_id` absent

Terminal/session context:

- `unmapped.auditd.terminal` SHOULD preserve the `terminal` field for forensic context.
- Session ID (`ses`) MAY be preserved under `unmapped.auditd.session_id`.

## Applicability and coverage

This profile is designed to work with the applicability-aware coverage model defined by:

- [Coverage matrix](coverage_matrix.md)

Normative conformance requirements:

- Fields are only required when authoritative values exist.
- Fields marked `N/A` for auditd (example: `actor.user.domain`) MUST remain absent.
- UID-to-name resolution is optional; `actor.user.name` is `O[U]` in the coverage matrix.

Coverage matrix alignment for auditd (Tier 1):

| Field                | Requirement | Notes                                         |
| -------------------- | ----------: | --------------------------------------------- |
| `category_uid`       |        R[C] | Always determinable from routing              |
| `type_uid`           |        R[C] | Computed from class_uid + activity_id         |
| `severity_id`        |        O[C] | May be derived from success/failure           |
| `device.hostname`    |        R[H] | From aggregator hostname field                |
| `device.uid`         |        R[H] | From inventory context                        |
| `device.(ip\|ips)`   |        O[H] | From inventory context                        |
| `actor.user.name`    |        O[U] | Optional; requires UID-to-name snapshot       |
| `actor.user.uid`     |        R[U] | Always present in audit records               |
| `actor.process.name` |        O[P] | Derived from exe when present                 |
| `actor.process.pid`  |        R[P] | Present in SYSCALL records                    |
| `message`            |           O | Optional human-readable summary               |
| `observables[]`      |           O | Optional; extract IPs, users, paths as pivots |

## Verification hooks for CI

Minimum conformance tests for this profile:

1. Routing tests:

   - Given raw fixtures for each v0.1 record type/syscall combination, the normalizer MUST select
     the expected `class_uid`.

1. Determinism tests:

   - Re-running normalization on the same raw fixture MUST produce byte-identical normalized JSON
     after canonicalization and stable ordering.

1. Coverage tests:

   - Coverage computation MUST treat non-authoritative fields as "not applicable" and MUST NOT count
     them as missing.
   - Tests MUST assert that `N/A` fields (e.g., `actor.user.domain`) remain absent.

1. Identity tests:

   - The `metadata.event_id` for the same `audit_msg_id` MUST be identical across runs.
   - Identity MUST NOT change based on ingestion path (journald vs file tailing).

Minimum fixture set (aligned to the coverage matrix CI requirements):

- Raw fixtures: `tests/fixtures/raw/linux-auditd/**`
- Required raw fixture coverage:
  - 1 execve SYSCALL event (aggregated with EXECVE, PATH, CWD, PROCTITLE records)
  - 1 file operation SYSCALL event (e.g., openat with PATH record)
  - 1 network SYSCALL event (e.g., connect with SOCKADDR record) — optional per coverage matrix
  - 1 USER_LOGIN or USER_AUTH event
- Golden normalized outputs: `tests/fixtures/normalized/ocsf/1.7.0/linux-auditd/**`

## Known limitations for v0.1

- **Multi-record aggregation dependency**: This profile assumes pre-aggregated input.
  Implementations that receive raw audit lines MUST aggregate before invoking the normalizer.
- **Syscall number portability**: Syscall numbers are architecture-dependent (x86_64, aarch64,
  etc.). The mapping pack SHOULD support configurable syscall tables or symbolic name resolution.
- **UID-to-name resolution**: Not implemented by default. Operators who require username population
  MUST configure and snapshot a local identity context.
- **Hex decoding complexity**: `proctitle` and `saddr` parsing requires careful hex decoding.
  Invalid or truncated hex values should result in absent fields rather than corrupt data.
- **PATH record ambiguity**: Some audit events produce multiple PATH records. The mapping must
  define deterministic selection rules, which may not capture all semantic nuance.
- **Network activity coverage**: Socket-level audit events depend on audit rule configuration.
  Detection coverage for network activity may be limited if appropriate audit rules are not
  deployed.

## Future expansion (out of scope for v0.1)

This profile covers auditd as the primary Linux security telemetry source for v0.1. The following
sources are explicitly reserved for future mapping profiles within the `linux-*` family:

| Source   | Target pack ID   | Identity tier | Blocking dependencies                    |
| -------- | ---------------- | ------------- | ---------------------------------------- |
| journald | `linux-journald` | Tier 1        | OTel journald receiver cursor semantics  |
| syslog   | `linux-syslog`   | Tier 2/3      | Tier 2/3 identity collision analysis     |
| eBPF/BCC | `linux-ebpf`     | TBD           | Schema stabilization in upstream tooling |

Design decisions in this profile (naming conventions, identity basis structure, class routing
patterns) are intended to be consistent with future sibling profiles:

- `source_pack_id` uses the `linux-<subsystem>` naming pattern.
- `event_source_type` uses the `linux_<subsystem>` pattern (underscore for programmatic use).
- Identity basis fields are prefixed with `origin.` for consistency across the family.

When adding future Linux source profiles, implementers SHOULD:

1. Review this profile for structural patterns and naming conventions.
1. Ensure class routing decisions are consistent (same syscalls route to same classes).
1. Coordinate Tier 1 field coverage to enable cross-source correlation.

## References

- [Unix log ingestion specification](../spec/044_unix_log_ingestion.md)
- [OCSF normalization specification](../spec/050_normalization_ocsf.md)
- [OCSF field tiers reference](../spec/055_ocsf_field_tiers.md)
- [Coverage matrix](coverage_matrix.md)
- [ADR-0002 Event identity and provenance](../adr/ADR-0002-event-identity-and-provenance.md)
- [OCSF mapping profile authoring guide](ocsf_mapping_profile_authoring_guide.md)
- [Red Hat: Understanding audit log files](https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/7/html/security_guide/sec-understanding_audit_log_files)
- [Linux Audit Documentation](https://github.com/linux-audit/audit-documentation)
- [ausearch(8) man page](https://man7.org/linux/man-pages/man8/ausearch.8.html)

## Changelog

| Date       | Change        |
| ---------- | ------------- |
| 2026-01-14 | Initial draft |
