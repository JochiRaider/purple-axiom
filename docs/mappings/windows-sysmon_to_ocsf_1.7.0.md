<!-- docs/mappings/windows-sysmon_to_ocsf_1.7.0.md -->

# Windows Sysmon → OCSF 1.7.0 Mapping Profile (v0.1)

## Status

Draft (v0.1 target)

## Purpose

This document defines the Windows Sysmon (Operational channel) mapping profile for Purple Axiom’s
OCSF v1.7.0 normalizer.

It is designed to be:

- implementable (rules are explicit and deterministic)
- reviewable (humans can validate class/field intent)
- testable (fixtures can assert routing, coverage, and semantics)

The machine-executable mapping rules referenced by this document live under:

- `mappings/normalizer/ocsf/1.7.0/windows-sysmon/**`

## Scope

In scope (v0.1):

- Windows Event Log: **Sysmon** (`Microsoft-Windows-Sysmon/Operational`)
- Sysmon event families required for v0.1 scenarios:
  - process creation / termination
  - network connection
  - file creation
  - DNS query (if Sysmon DNS logging is enabled)

Out of scope (v0.1):

- Image load (Sysmon Event ID 7)
- Registry events (12/13/14) and other Sysmon families not listed above
- Any behavior requiring inference (e.g., protocol-number derivation from protocol names)

## Mapping stance: OCSF-native fields plus Purple pivots

This profile uses a dual-fielding strategy:

1. **OCSF-native primary fields MUST be populated** when authoritative source values exist.
1. **Purple pivots MAY be populated** for correlation and cross-source consistency, but MUST NOT
   conflict with OCSF-native fields.

Requirements:

- The mapping MUST NOT infer values (no synthesis from unrelated fields).
- If a value is not authoritative, the field MUST be absent (not null, not empty string).
- If multiple possible inputs exist, the profile MUST define a stable precedence order.

### “Purple pivots” namespace

Purple pivots (when used) SHOULD be placed under:

- `extensions.purple.*`

Sysmon-specific raw fields that do not have an OCSF-native home in v0.1 SHOULD be placed under:

- `extensions.purple.sysmon.*`

## Inputs and prerequisites

### Expected raw input shape

The normalizer is expected to receive Windows Event Log records for Sysmon with:

- `provider` = `Microsoft-Windows-Sysmon`
- `channel` = `Microsoft-Windows-Sysmon/Operational`
- `event_id` (integer)
- `record_id` / `EventRecordID` (integer or string)
- `time_created` / `SystemTime` (UTC timestamp)
- `computer` (hostname)
- event payload key/value pairs (from `<EventData>`), e.g. `Image`, `CommandLine`, `ProcessId`, etc.

The mapping MUST NOT depend on localized renderings of the event message text.

### Canonicalization rules (determinism)

Canonicalization is applied prior to mapping.

Strings:

- MUST be trimmed of leading/trailing whitespace.
- MUST preserve original case unless explicitly normalized below.

Hostnames:

- `device.hostname` SHOULD be lowercased when populated from `computer`.

Users (`User` field in Sysmon EventData):

- If `User` matches `DOMAIN\NAME`, populate:
  - `actor.user.domain = DOMAIN`
  - `actor.user.name = NAME`
- Otherwise populate:
  - `actor.user.name = User`
- Placeholder values such as `-` or empty MUST be treated as “absent”.

PIDs:

- Sysmon `ProcessId`, `ParentProcessId`, and similar numeric fields MUST be parsed as base-10
  integers.
- If parsing fails, the target field MUST be absent and the raw value MAY be preserved under
  `extensions.purple.sysmon.parse_errors.*`.

GUIDs:

- Sysmon `ProcessGuid`, `ParentProcessGuid`, `LogonGuid` MUST be preserved exactly as emitted.

IP addresses and ports:

- IP strings MUST be emitted exactly as received after trimming.
- Port fields MUST be parsed as base-10 integers when possible; otherwise absent.

Hashes (`Hashes` field in Sysmon EventData, Event ID 1):

- If `Hashes` is present, it MUST be parsed as a list of `KEY=VALUE` pairs delimited by commas.
- Recognized `KEY` values MUST be mapped to OCSF `Fingerprint.algorithm_id`:
  - `MD5` → `1`
  - `SHA1` / `SHA-1` → `2`
  - `SHA256` / `SHA-256` → `3`
  - `SHA512` / `SHA-512` → `4`
  - Unrecognized keys → `99` with `algorithm` set to the original key
- Emitted `file.hashes[]` (or `process.file.hashes[]`) MUST be:
  - de-duplicated by `(algorithm_id, value)` and
  - sorted by `(algorithm_id ASC, value ASC)`.

## Classification and identifiers

### Class routing

Routing is based on `(provider, channel, event_id)`.

- The routing table is normative and versioned in:
  - `mappings/normalizer/ocsf/1.7.0/windows-sysmon/routing.yaml`

If an event_id is not routable in v0.1:

- The normalizer MUST emit a stage outcome indicating “unmapped_event_id” (warn-and-skip), OR emit
  an OCSF `base_event` with an explicit `unmapped` payload, depending on pipeline policy.

### OCSF classification fields

For every emitted event, the normalizer MUST set:

- `class_uid`
- `activity_id`
- `type_uid`
  - Example: Process Launch = `1007 * 100 + 1 = 100701`
  - Example: Network Open = `4001 * 100 + 1 = 400101`
- `category_uid` SHOULD be set when known for the class (see per-family sections below).
- `severity_id` MAY be set if an authoritative mapping exists; otherwise it MUST be absent.

Rules:

- `type_uid` MUST be computed as: `class_uid * 100 + activity_id`.

### Event identity

Event identity MUST be stable and must not depend on run-local values (run_id, host inventory IDs,
or ingestion time). This profile assumes a project-wide event identity decision exists; Sysmon
mapping MUST provide required basis fields (record_id, channel, provider, computer, event_id,
time_created).

### `metadata.uid` requirement

Per `055_ocsf_field_tiers.md` Tier 0 and ADR-0002:

- `metadata.uid` MUST be present on every emitted event.
- `metadata.uid` MUST equal `metadata.event_id`.

## Field mapping: shared (all routed Sysmon events)

### Device

- `device.name` MUST be populated from `computer` when present.
- `device.hostname` SHOULD be populated from `computer` when the value is a hostname.
  - `device.hostname` SHOULD be lowercased for cross-source join consistency (per canonicalization
    rules).

### Actor

Sysmon events in scope are emitted by an endpoint process and commonly include `User`, `Image`,
`ProcessId`, and `ProcessGuid`.

Rules:

- `actor.user.*` SHOULD be populated from `User` when present (per canonicalization rules).
- `actor.process.pid` SHOULD be populated from `ProcessId` when present and parseable.
- `actor.process.uid` SHOULD be populated from `ProcessGuid` when present.
- `actor.process.file.path` SHOULD be populated from `Image` when present.
- `actor.process.cmd_line` MAY be populated from `CommandLine` only when present and permitted by
  redaction policy.

### Metadata (source provenance)

At minimum:

- `metadata.product.name` SHOULD be `sysmon`.
- `metadata.log_provider` SHOULD be `Microsoft-Windows-Sysmon`.
- `metadata.log_name` SHOULD be `Microsoft-Windows-Sysmon/Operational`.
- `metadata.source_event_id` MUST be the raw record id when present.

## Routed event families (v0.1)

This section lists v0.1-required Sysmon event IDs and their OCSF mapping.

### 1) Process Activity (process creation/termination)

Class:

- Process Activity (`class_uid = 1007`)

Classification (normative):

- `category_uid` MUST be `1` (System Activity).
- `type_uid` MUST be computed as `class_uid * 100 + activity_id`.

#### Event IDs and activities

| Sysmon Event ID | Sysmon name        |   activity_id |
| --------------: | ------------------ | ------------: |
|               1 | Process creation   |    1 (Launch) |
|               5 | Process terminated | 2 (Terminate) |

Note: OCSF 1.7.0 Process Activity uses `activity_id = 2` for Terminate, aligning with Windows
Security event 4689 mapping.

#### Field mapping rules (Event ID 1: Process creation)

Authoritative inputs commonly include:

- `ProcessGuid`, `ProcessId`, `Image`, `CommandLine` (may be absent)
- `ParentProcessGuid`, `ParentProcessId`, `ParentImage`, `ParentCommandLine` (may be absent)
- `Hashes` (may be absent)
- `User`

Rules:

- `process.pid` MUST be populated from `ProcessId` when present and parseable.
- `process.uid` SHOULD be populated from `ProcessGuid` when present.
- `process.file.path` MUST be populated from `Image` when present.
- `process.cmd_line` MAY be populated from `CommandLine` only when present and permitted by
  redaction policy.

Parent process (initiator context):

- `actor.process.pid` SHOULD be populated from `ParentProcessId` when present and parseable.
- `actor.process.uid` SHOULD be populated from `ParentProcessGuid` when present.
- `actor.process.file.path` SHOULD be populated from `ParentImage` when present.
- `actor.process.cmd_line` MAY be populated from `ParentCommandLine` only when present and permitted
  by redaction policy.

Hashes:

- If `Hashes` is present, the normalizer SHOULD populate `process.file.hashes[]` using the parsing
  and ordering rules defined in “Canonicalization rules”.
- If `Hashes` parsing fails, `process.file.hashes[]` MUST be absent and the raw value MAY be
  preserved under `extensions.purple.sysmon.hashes_raw`.

No inference:

- The normalizer MUST NOT attempt to infer signer, integrity, or reputation metadata from the
  presence or absence of hash values.

#### Field mapping rules (Event ID 5: Process terminated)

Authoritative inputs commonly include:

- `ProcessGuid`, `ProcessId`, `Image`
- `User`

Rules:

- `process.pid` MUST be populated from `ProcessId` when present and parseable.
- `process.uid` SHOULD be populated from `ProcessGuid` when present.
- `process.file.path` MUST be populated from `Image` when present.

### 2) Network Activity (network connection)

Class:

- Network Activity (`class_uid = 4001`)

Classification (normative):

- `category_uid` MUST be `4` (Network Activity).
- `type_uid` MUST be computed as `class_uid * 100 + activity_id`.

#### Event IDs and activities

| Sysmon Event ID | Sysmon name        | activity_id |
| --------------: | ------------------ | ----------: |
|               3 | Network connection |    1 (Open) |

#### Field mapping rules (Event ID 3)

Authoritative inputs commonly include:

- `Image`, `ProcessId`, `ProcessGuid`, `User`
- `SourceIp`, `SourcePort`
- `DestinationIp`, `DestinationPort`
- `DestinationHostname` (may be absent)
- `Protocol` (e.g., `tcp`, `udp`)

Rules:

- `src_endpoint.ip` MUST be populated from `SourceIp` when present.

- `src_endpoint.port` SHOULD be populated from `SourcePort` when present and parseable.

- `dst_endpoint.ip` MUST be populated from `DestinationIp` when present.

- `dst_endpoint.port` SHOULD be populated from `DestinationPort` when present and parseable.

- `dst_endpoint.hostname` MAY be populated from `DestinationHostname` when present.

Protocol:

- `Protocol` MUST NOT be converted to a protocol number (inference).
- `Protocol` MAY be preserved under `extensions.purple.sysmon.protocol` for v0.1.

### 3) File System Activity (file create)

Class:

- File System Activity (`class_uid = 1001`)

Classification (normative):

- `category_uid` MUST be `1` (System Activity).
- `type_uid` MUST be computed as `class_uid * 100 + activity_id`.

#### Event IDs and activities

| Sysmon Event ID | Sysmon name | activity_id |
| --------------: | ----------- | ----------: |
|              11 | File create |  1 (Create) |

#### Field mapping rules (Event ID 11)

Authoritative inputs commonly include:

- `Image`, `ProcessId`, `ProcessGuid`, `User`
- `TargetFilename`

Rules:

- `file.path` MUST be populated from `TargetFilename` when present.
- `file.name` MUST be derived from `TargetFilename` using the deterministic basename algorithm:
  - Treat both `\` and `/` as path separators.
  - Ignore trailing separators.
  - Return the final non-empty segment.
- `file.parent_folder` MUST be derived from `TargetFilename` using the deterministic split rule:
  - Split at the last path separator (treating both `\` and `/` as separators).
  - Set `file.parent_folder` to the prefix before the final separator.
  - If no separator exists, `file.parent_folder` MUST be absent.
- `actor.process.*` SHOULD be populated using the shared actor mapping rules.

No inference:

- The normalizer MUST NOT infer file hashes or file owner metadata from this event family.

### 4) DNS Activity (DNS query)

Class:

- DNS Activity (`class_uid = 4003`)

Classification (normative):

- `category_uid` MUST be `4` (Network Activity).
- `type_uid` MUST be computed as `class_uid * 100 + activity_id`.

#### Event IDs and activities

| Sysmon Event ID | Sysmon name | activity_id |
| --------------: | ----------- | ----------: |
|              22 | DNS query   |   1 (Query) |

#### Field mapping rules (Event ID 22)

Authoritative inputs commonly include:

- `Image`, `ProcessId`, `ProcessGuid`, `User`
- `QueryName`
- `QueryStatus` (Windows status code; not a DNS rcode)
- `QueryResults` (may be absent)

Rules:

- `query.hostname` MUST be populated from `QueryName` when present.
- `QueryStatus` MUST NOT be mapped to DNS `rcode` (not authoritative as DNS server rcode); it MAY be
  preserved under `extensions.purple.sysmon.query_status`.
- `QueryResults` MAY be preserved under `extensions.purple.sysmon.query_results` in v0.1.
- DNS `rcode` (response code) is `N/A` for Sysmon Event ID 22:
  - Sysmon `QueryStatus` is a Windows NTSTATUS code indicating whether the DNS client API call
    succeeded, not the DNS protocol response code from the server.
  - Mapping profiles MUST NOT infer or populate `rcode` from `QueryStatus`.
  
## Applicability and coverage

This profile is designed to work with an applicability-aware coverage model:

- Fields are only “required” when authoritative values exist.
- Fields that cannot exist for an event family MUST remain absent.

The canonical field applicability expectations for v0.1 are maintained in:

- `docs/mappings/coverage_matrix.md`

## Known limitations (v0.1)

- Sysmon coverage depends on the deployed Sysmon configuration (event IDs may not be enabled).
- DNS query visibility (Event ID 22) is environment- and config-dependent.
- Command line fields may contain secrets; any redaction policy MUST be applied before emitting
  normalized fields and before writing report artifacts.

## Verification hooks (CI)

Minimum conformance tests for this profile:

1. Routing tests:

   - Given raw fixtures for each v0.1 Sysmon event_id, the normalizer MUST select the expected
     `(class_uid, activity_id)`.

1. Determinism tests:

   - Re-running normalization on the same raw fixture MUST produce byte-identical normalized JSON
     (after canonicalization).

1. Coverage tests:

   - Coverage computation MUST treat non-authoritative fields as “not applicable” and MUST NOT count
     them as missing.

Artifacts and fixtures (recommended layout):

- Raw fixtures: `tests/fixtures/raw/windows_sysmon/**`
- Golden normalized outputs: `tests/fixtures/normalized/ocsf/1.7.0/windows_sysmon/**`
- Coverage reports (ephemeral CI outputs) compared against checked-in baselines.
