<!-- docs/mappings/windows-security_to_ocsf_1.7.0.md -->

# Windows Security → OCSF 1.7.0 Mapping Profile (v0.1)

## Status

Draft (v0.1 target)

## Purpose

This document defines the Windows Event Log **Security channel** mapping profile for Purple Axiom’s
OCSF v1.7.0 normalizer.

It is designed to be:

- implementable (rules are explicit and deterministic)
- reviewable (humans can validate class/field intent)
- testable (fixtures can assert coverage and semantics)

The machine-executable mapping rules referenced by this document live under:

- `mappings/normalizer/ocsf/1.7.0/windows-security/**`

## Scope

In scope:

- Windows Event Log: **Security** channel (`Microsoft-Windows-Security-Auditing`)
- The event families required for v0.1 detection and validation scenarios:
  - authentication (logon/logoff)
  - process creation/termination
  - account lifecycle and group membership changes
  - audit-log tampering (clear/disable)

Out of scope (v0.1):

- Full Windows Security catalog coverage
- Domain Controller-specific “Account Logon” events unless explicitly enabled and routed

## Mapping stance: OCSF-native fields plus Purple pivots

This profile uses a dual-fielding strategy:

1. **OCSF-native primary fields MUST be populated** when authoritative source values exist.
1. **Purple pivots MAY be populated** for correlation and cross-source consistency, but MUST NOT
   conflict with OCSF-native fields.

Requirements:

- The mapping MUST NOT infer values (no synthesis from unrelated fields).
- If a value is not authoritative, the field MUST be absent (not null, not empty string).
- If multiple possible inputs exist, the profile MUST define a stable precedence order.

### “Purple pivots”

Purple pivots are optional convenience fields used for cross-event joins. If used, they SHOULD be
placed under a stable extension namespace (recommended: `extensions.purple.*`) unless the project
has already standardized on top-level pivots.

Examples:

- Device IPs:
  - OCSF-native: `device.ip` (single value)
  - Purple pivot (optional): `extensions.purple.device.ips[]` (set of all authoritative IPs)

## Inputs and prerequisites

### Expected raw input shape

The normalizer is expected to receive Windows Event Log records with:

- `provider` (e.g., `Microsoft-Windows-Security-Auditing`)
- `channel` = `Security`
- `event_id` (integer)
- `record_id` / `EventRecordID` (integer or string)
- `time_created` / `SystemTime` (UTC timestamp)
- `computer` (hostname)
- event payload key/value pairs (from `<EventData>`)

The mapping MUST NOT depend on localized renderings of the event message text.

### Canonicalization rules (determinism)

All canonicalization is applied prior to mapping:

- Strings:
  - MUST be trimmed of leading/trailing whitespace.
  - MUST preserve original case unless a field is explicitly case-normalized below.
- Hostnames:
  - `device.hostname` SHOULD be lowercased.
- SIDs:
  - MUST be preserved exactly as emitted (e.g., `S-1-5-21-...`).
- IP addresses:
  - MUST be emitted in normalized textual form.
  - Placeholder values such as `-` MUST be treated as “absent”.

## Classification and identifiers

### Class routing

Routing is based on `(provider, channel, event_id)`.

- The routing table is normative and versioned in:
  - `mappings/normalizer/ocsf/1.7.0/windows-security/routing.yaml`

If an event_id is not routable in v0.1:

- The normalizer MUST emit a stage outcome indicating “unmapped_event_id” (warn-and-skip), OR emit
  an OCSF `base_event` with an explicit `unmapped` payload, depending on pipeline policy.

### OCSF classification fields

For every emitted event, the normalizer MUST set:

- `class_uid`
- `activity_id`
- `type_uid`

Rules:

- `type_uid` MUST be computed as: `class_uid * 100 + activity_id`.
  - Example: Authentication Logon = `3002 * 100 + 1 = 300201`
  - Example: Process Launch = `1007 * 100 + 1 = 100701`
- `category_uid` SHOULD be set when known for the class.
- `severity_id` MAY be set if an authoritative mapping exists; otherwise it MUST be absent.

### Event identity

Event identity MUST be stable and must not depend on run-local values (run_id, host inventory IDs,
or ingestion time). This profile assumes a project-wide event identity decision exists; if it does,
the Windows Security mapping MUST provide the required basis fields (record_id, channel, provider,
computer, event_id, time_created).

### `metadata.uid` requirement

Per `055_ocsf_field_tiers.md` Tier 0 and ADR-0002:

- `metadata.uid` MUST be present on every emitted event.
- `metadata.uid` MUST equal `metadata.event_id`.

## Field mapping: shared (all Windows Security events)

This section defines the baseline field population rules that apply to all routed events.

### Device

- `device.name` MUST be populated from `computer` when present. This field represents the
  NetBIOS/hostname as reported by the event source.
- `device.hostname` SHOULD be populated from `computer` when the value is a hostname.
  - `device.hostname` SHOULD be lowercased for cross-source join consistency.
  - When `device.name` and `device.hostname` are both populated from `computer`, they MAY differ
    only in case normalization (`device.name` preserves original case; `device.hostname` is
    lowercased).
- `device.ip` MUST be populated only when an authoritative device IP exists in the raw event.
- If multiple authoritative IPs exist, `device.ip` SHOULD be the stable “primary” IP and the full
  set MAY be emitted to `extensions.purple.device.ips[]` (sorted, de-duplicated).

### Actor user (Subject vs Target)

Windows Security frequently provides both “Subject” and “Target/New Logon” fields.

This profile defines:

- `actor.user` = the **principal whose activity the event represents** (the user being logged on,
  the user creating the process, etc.).
- `target.user` = the **object user** when the event’s semantics describe an action on a distinct
  user account.

Per-event sections below define which raw fields populate `actor.user` vs `target.user`.

### Metadata (source provenance)

At minimum:

- `metadata.product.name` SHOULD be `windows_eventlog`.
- `metadata.log_provider` SHOULD be the event provider.
- `metadata.log_name` SHOULD be `Security`.
- `metadata.source_event_id` MUST be the raw record id when present.

If the project uses additional provenance fields (receiver_id, pipeline_id), this mapping SHOULD
populate them, but they MUST NOT participate in event identity hashing.

## Routed event families (v0.1)

This section lists v0.1-required Windows Security event IDs and their OCSF mapping.

### 1) Authentication (logon/logoff)

Class:

- Authentication (`class_uid = 3002`)

Classification (normative):

- `category_uid` MUST be `3` (Identity & Access Management).
- `type_uid` MUST be computed as `class_uid * 100 + activity_id`.
  - Example: Logon (4624/4625) = `300201`; Logoff (4634/4647) = `300202`

#### Event IDs and activities

| Windows Event ID | Meaning (Windows)                    | activity_id |   status_id |
| ---------------: | ------------------------------------ | ----------: | ----------: |
|             4624 | Successful logon                     |   1 (Logon) | 1 (Success) |
|             4625 | Failed logon                         |   1 (Logon) | 2 (Failure) |
|             4634 | Logoff                               |  2 (Logoff) | 1 (Success) |
|             4647 | User initiated logoff (if collected) |  2 (Logoff) | 1 (Success) |

#### Field mapping rules (4624/4625)

Authoritative inputs commonly include:

- `TargetUserSid`, `TargetUserName`, `TargetDomainName`
- `LogonType`
- `IpAddress`, `IpPort` (may be `-` or empty)
- For failures: `Status`, `SubStatus`, `FailureReason`

Rules:

- `actor.user.uid` MUST be `TargetUserSid` when present and not placeholder.

- `actor.user.name` MUST be `TargetUserName` when present.

- `actor.user.domain` MUST be `TargetDomainName` when present.

- `logon_type_id` SHOULD be set from `LogonType` when present and numeric.

- `src_endpoint.ip` SHOULD be set from `IpAddress` when present and not placeholder.

- `src_endpoint.port` SHOULD be set from `IpPort` when present and numeric.

- `status_id` MUST be set as specified in the table above.

- For failed logons (4625):

  - `status_code` SHOULD be populated from `Status` when present.
  - `status_detail` SHOULD be populated from `SubStatus` and/or `FailureReason` when present.

No inference:

- The normalizer MUST NOT derive IP from `WorkstationName`.
- The normalizer MUST NOT synthesize a domain when `TargetDomainName` is absent.

### 2) Process Activity (process creation/termination)

Class:

- Process Activity (`class_uid = 1007`)

Classification (normative):

- `category_uid` MUST be `1` (System Activity).
- `type_uid` MUST be computed as `class_uid * 100 + activity_id`.
  - Example: Launch (4688) = `100701`; Terminate (4689) = `100702`

#### Event IDs and activities

| Windows Event ID | Meaning (Windows)   |   activity_id |   status_id |
| ---------------: | ------------------- | ------------: | ----------: |
|             4688 | Process creation    |    1 (Launch) | 1 (Success) |
|             4689 | Process termination | 2 (Terminate) | 1 (Success) |

#### Field mapping rules (4688)

Authoritative inputs commonly include:

- Subject:
  - `SubjectUserSid`, `SubjectUserName`, `SubjectDomainName`
- Creator:
  - `ProcessId`, `ProcessName` (creator)
- New process:
  - `NewProcessId`, `NewProcessName`, `CommandLine` (may be absent), `TokenElevationType` (optional)

Rules:

- `actor.user.*` MUST be populated from `Subject*` when present.

- `process.pid` MUST be populated from `NewProcessId` when present and parseable.

- `process.file.path` MUST be populated from `NewProcessName` when present.

- `process.cmd_line` MAY be populated from `CommandLine` only when present and permitted by
  redaction policy.

- `actor.process.pid` SHOULD be populated from `ProcessId` when present.

- `actor.process.file.path` SHOULD be populated from `ProcessName` when present.

No inference:

- The normalizer MUST NOT infer `process.hash` or `process.integrity` from unrelated fields.

### 3) Account Change (user lifecycle)

Class:

- Account Change (`class_uid = 3001`)

Classification (normative):

- `category_uid` MUST be `3` (Identity & Access Management).
- `activity_id` MUST be derived from the specific event ID (create/enable/disable/delete/lockout).

v0.1 routing MAY include:

- 4720 (user created)
- 4722 (user enabled)
- 4725 (user disabled)
- 4726 (user deleted)
- 4740 (account locked out)

Rules:

- `target.user.*` SHOULD describe the account being modified (the user lifecycle object).
- `actor.user.*` SHOULD describe the initiator (commonly the Subject fields), when present.

### 4) Group Management (membership changes)

Class:

- Group Management (`class_uid = 3006`)

Classification (normative):

- `category_uid` MUST be `3` (Identity & Access Management).

v0.1 routing MAY include:

- 4728/4729 (member added/removed from a security-enabled global group)
- 4732/4733 (member added/removed from a security-enabled local group)
- 4756/4757 (member added/removed from a universal group)

Rules:

- `group.*` SHOULD identify the group object when authoritative group identifiers exist.
- `target.user.*` SHOULD be the member affected when authoritative identifiers exist.
- `actor.user.*` SHOULD be the initiator when present.

### 5) Event Log Activity (audit log tampering)

Class:

- Event Log Activity (`class_uid = 1008`)

Classification (normative):

- `category_uid` MUST be `1` (System Activity).

v0.1 routing SHOULD include:

- 1102 (audit log cleared)

Rules (1102):

- `activity_id` MUST be 1 (Clear) when the event indicates clearing the Security log.
- `log_name` SHOULD be `Security`.
- `log_provider` SHOULD be `Microsoft-Windows-Eventlog` or the authoritative provider from the
  event.

## Applicability and coverage

This profile is designed to work with an applicability-aware coverage model:

- Fields are only “required” when authoritative values exist.
- Fields that cannot exist for an event family MUST remain absent.

The canonical field applicability expectations for v0.1 are maintained in:

- `docs/mappings/coverage_matrix.md`

This profile SHOULD publish a machine-readable “applicability manifest” (follow-on work) that
states, per `(event_id, class_uid)`, which Tier 1 and Tier 2 fields are expected to be present when
authoritative.

## Known limitations (v0.1)

- Authentication events:
  - Some Windows event IDs provide incomplete network context (IpAddress placeholders, missing
    port).
  - Domain controller “Account Logon” events are not covered unless explicitly enabled.
- File and registry activity:
  - Security channel events can represent access checks and do not always cleanly map to a single
    file/registry action without inference. v0.1 SHOULD prefer `activity_id = 0` (Unknown) over
    guessing.
- Command line and sensitive fields:
  - Any redaction policy MUST be applied before emitting normalized fields, and before writing
    report artifacts.

## Verification hooks (CI)

Minimum conformance tests for this profile:

1. Routing tests:

   - Given raw fixtures for each v0.1 event_id, the normalizer MUST select the expected
     `(class_uid, activity_id)`.

1. Determinism tests:

   - Re-running normalization on the same raw fixture MUST produce byte-identical normalized JSON
     (after canonicalization).

1. Coverage tests:

   - Coverage computation MUST treat non-authoritative fields as “not applicable” and MUST NOT count
     them as missing.
   - Baselines MUST be derived from a representative Windows Security fixture corpus.

Artifacts and fixtures:

- Raw fixtures: `tests/fixtures/raw/windows_security/**`
- Golden normalized outputs: `tests/fixtures/normalized/ocsf/1.7.0/windows_security/**`
- Coverage reports (ephemeral CI outputs) compared against checked-in baselines.
