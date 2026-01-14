---
title: R-06 Windows Security to OCSF Mapping Completeness
description: Mapping coverage matrix for Windows Security Event IDs against the current Windows Security → OCSF 1.7.0 mapping profile, including gap prioritization and verification hooks.
status: draft
---

# R-06 Windows Security to OCSF Mapping Completeness

This report evaluates Windows Security Event ID coverage in the current Windows Security to OCSF
1.7.0 mapping profile and highlights priority gaps for v0.1.

## Overview

This report answers:

- Which Windows Security Event IDs are **currently mapped** to OCSF classes by the project's Windows
  Security → OCSF 1.7.0 mapping profile.
- Which Event IDs are **unmapped** (coverage gaps), and a **P0/P1/P2** priority classification for
  closing those gaps.
- Which mapped Event IDs have **partial field coverage** that is likely to impact downstream
  detection content (Sigma).

**Key result:** The current profile routes approximately **17 Windows Security Event IDs** across
five event families (Authentication, Process Activity, Account Change, Group Management, Event Log
Activity) into OCSF classes. Many high-value Security channel events remain unmapped, including
object access, privilege use, scheduled task operations, and service installation events.

## Scope

This document covers:

- Project mapping profile: `windows-security_to_ocsf_1.7.0.md` (local file)
- Windows Security Event Log catalog (Microsoft documentation)
- Sigma logsource categories dependent on Windows Security events

This document does NOT cover:

- Implementing new mappings (this document identifies gaps and verification hooks only)
- Sysmon event coverage (see R-05 for Sysmon gaps)
- Non-Security channel Windows Event Logs (System, Application, etc.) except where noted

## Methodology

1. Extract "routed event families" and explicit Event ID coverage from
   `windows-security_to_ocsf_1.7.0.md`.
1. Compare against the Windows Security Event ID catalog for common detection-relevant events.
1. For each Event ID:
   - Mark as **Mapped** if present in the mapping profile's routed families.
   - If mapped, record the **OCSF class_uid** and **activity_id** described by the profile.
   - Assign a **gap priority** using the criteria below.

## Gap priority definitions (P0/P1/P2)

- **P0:** High-signal security telemetry that underpins common detection logic (e.g., persistence
  mechanisms, credential access indicators, defense evasion). Absence creates broad blind spots and
  blocks major Sigma logsource categories.
- **P1:** Valuable telemetry with meaningful detection value, but typically less universal, noisier,
  or more environment-dependent; recommended after P0 coverage.
- **P2:** Operability / niche / domain controller-specific events; recommended only after P0/P1 or
  when required for a specific scenario or product constraint.

Sigma rules' `logsource` selection is materially important (category/product/service mismatches can
make a rule ineffective), so missing telemetry families translate directly into missing Sigma
execution coverage.

## Event ID to OCSF mapping matrix

### Currently routed event families (v0.1)

| Event ID | Windows Security event              | Current OCSF mapping (from profile)  | Coverage | Gap priority |
| -------: | ----------------------------------- | ------------------------------------ | -------- | ------------ |
|     4624 | Successful logon                    | Authentication (3002) / Logon        | Strong   | OK           |
|     4625 | Failed logon                        | Authentication (3002) / Logon        | Strong   | OK           |
|     4634 | Logoff                              | Authentication (3002) / Logoff       | Strong   | OK           |
|     4647 | User initiated logoff               | Authentication (3002) / Logoff       | Strong   | OK           |
|     4688 | Process creation                    | Process Activity (1007) / Launch     | Strong   | OK           |
|     4689 | Process termination                 | Process Activity (1007) / Terminate  | Strong   | OK           |
|     4720 | User account created                | Account Change (3001) / Create       | Moderate | OK           |
|     4722 | User account enabled                | Account Change (3001) / Enable       | Moderate | OK           |
|     4725 | User account disabled               | Account Change (3001) / Disable      | Moderate | OK           |
|     4726 | User account deleted                | Account Change (3001) / Delete       | Moderate | OK           |
|     4740 | Account locked out                  | Account Change (3001) / Lock         | Moderate | OK           |
|     4728 | Member added to global group        | Group Management (3006) / AddUser    | Moderate | OK           |
|     4729 | Member removed from global group    | Group Management (3006) / RemoveUser | Moderate | OK           |
|     4732 | Member added to local group         | Group Management (3006) / AddUser    | Moderate | OK           |
|     4733 | Member removed from local group     | Group Management (3006) / RemoveUser | Moderate | OK           |
|     4756 | Member added to universal group     | Group Management (3006) / AddUser    | Moderate | OK           |
|     4757 | Member removed from universal group | Group Management (3006) / RemoveUser | Moderate | OK           |
|     1102 | Audit log cleared                   | Event Log Activity (1008) / Clear    | Strong   | OK           |

### Unmapped event families (gaps)

#### Object access events

| Event ID | Windows Security event     | Current OCSF mapping | Coverage | Gap priority |
| -------: | -------------------------- | -------------------- | -------- | ------------ |
|     4656 | Handle to object requested | Unmapped (no route)  | None     | P1           |
|     4658 | Handle to object closed    | Unmapped (no route)  | None     | P2           |
|     4660 | Object deleted             | Unmapped (no route)  | None     | P1           |
|     4663 | Attempt to access object   | Unmapped (no route)  | None     | P0           |

#### Scheduled task events

| Event ID | Windows Security event  | Current OCSF mapping | Coverage | Gap priority |
| -------: | ----------------------- | -------------------- | -------- | ------------ |
|     4698 | Scheduled task created  | Unmapped (no route)  | None     | P0           |
|     4699 | Scheduled task deleted  | Unmapped (no route)  | None     | P1           |
|     4700 | Scheduled task enabled  | Unmapped (no route)  | None     | P1           |
|     4701 | Scheduled task disabled | Unmapped (no route)  | None     | P1           |
|     4702 | Scheduled task updated  | Unmapped (no route)  | None     | P1           |

#### Service events

| Event ID | Windows Security event | Current OCSF mapping | Coverage | Gap priority |
| -------: | ---------------------- | -------------------- | -------- | ------------ |
|     4697 | Service installed      | Unmapped (no route)  | None     | P0           |

#### Privilege use events

| Event ID | Windows Security event                   | Current OCSF mapping | Coverage | Gap priority |
| -------: | ---------------------------------------- | -------------------- | -------- | ------------ |
|     4672 | Special privileges assigned to new logon | Unmapped (no route)  | None     | P0           |
|     4673 | Privileged service called                | Unmapped (no route)  | None     | P1           |
|     4674 | Operation attempted on privileged object | Unmapped (no route)  | None     | P1           |

#### Additional authentication events

| Event ID | Windows Security event           | Current OCSF mapping | Coverage | Gap priority |
| -------: | -------------------------------- | -------------------- | -------- | ------------ |
|     4648 | Logon using explicit credentials | Unmapped (no route)  | None     | P0           |
|     4649 | Replay attack detected           | Unmapped (no route)  | None     | P1           |
|     4675 | SIDs filtered                    | Unmapped (no route)  | None     | P2           |

#### Domain controller authentication events (Account Logon)

| Event ID | Windows Security event             | Current OCSF mapping | Coverage | Gap priority |
| -------: | ---------------------------------- | -------------------- | -------- | ------------ |
|     4768 | Kerberos TGT requested             | Unmapped (no route)  | None     | P1           |
|     4769 | Kerberos service ticket requested  | Unmapped (no route)  | None     | P1           |
|     4770 | Kerberos service ticket renewed    | Unmapped (no route)  | None     | P2           |
|     4771 | Kerberos pre-authentication failed | Unmapped (no route)  | None     | P1           |
|     4776 | NTLM credential validation         | Unmapped (no route)  | None     | P1           |

#### Policy change events

| Event ID | Windows Security event      | Current OCSF mapping | Coverage | Gap priority |
| -------: | --------------------------- | -------------------- | -------- | ------------ |
|     4719 | System audit policy changed | Unmapped (no route)  | None     | P0           |
|     4739 | Domain policy changed       | Unmapped (no route)  | None     | P1           |
|     4713 | Kerberos policy changed     | Unmapped (no route)  | None     | P2           |

#### Security group enumeration events

| Event ID | Windows Security event                   | Current OCSF mapping | Coverage | Gap priority |
| -------: | ---------------------------------------- | -------------------- | -------- | ------------ |
|     4798 | User's local group membership enumerated | Unmapped (no route)  | None     | P1           |
|     4799 | Security-enabled local group enumerated  | Unmapped (no route)  | None     | P1           |

## Field coverage analysis

This section focuses on Event IDs that are currently routed. Unrouted Event IDs have **no** field
coverage because events are not present in normalized outputs.

### Pivot coverage for routed Event IDs

| Event ID | OCSF class         | Actor user | Target user | Device | Process | Network endpoint |
| -------- | ------------------ | ---------- | ----------- | ------ | ------- | ---------------- |
| 4624     | Authentication     | Yes        | No          | Yes    | No      | Partial          |
| 4625     | Authentication     | Yes        | No          | Yes    | No      | Partial          |
| 4634     | Authentication     | Yes        | No          | Yes    | No      | No               |
| 4647     | Authentication     | Yes        | No          | Yes    | No      | No               |
| 4688     | Process Activity   | Yes        | No          | Yes    | Yes     | No               |
| 4689     | Process Activity   | Yes        | No          | Yes    | Yes     | No               |
| 4720     | Account Change     | Partial    | Yes         | Yes    | No      | No               |
| 1102     | Event Log Activity | Partial    | No          | Yes    | No      | No               |

### Notable partial coverage (current routed set)

- **Event ID 4624/4625 (Logon/Failed Logon):** routed to **Authentication (3002)** with strong field
  coverage, but `src_endpoint.ip` and `src_endpoint.port` are only populated when the raw event
  provides them (often placeholder values like `-` for local logons). This is documented in the
  profile's known limitations.

- **Event ID 4688 (Process Creation):** routed to **Process Activity (1007)** with strong field
  coverage. `process.cmd_line` is conditional on redaction policy and audit policy configuration
  (command line auditing must be enabled). Without command line data, many detection rules become
  less effective.

- **Account Change events (4720–4740):** routed to **Account Change (3001)** but field coverage is
  marked as "MAY include" in the profile, indicating these routes may not be fully implemented in
  v0.1.

## P0/P1/P2 gap breakdown

### P0 gaps (recommended next)

These Event IDs commonly underpin high-value detection content:

- **4663 (Object access)** — file and registry access telemetry for data exfiltration and defense
  evasion detection
- **4672 (Special privileges)** — privilege escalation and lateral movement indicators
- **4697 (Service installed)** — persistence mechanism detection (T1543.003)
- **4698 (Scheduled task created)** — persistence mechanism detection (T1053.005)
- **4648 (Explicit credential logon)** — credential theft and lateral movement indicators
- **4719 (Audit policy changed)** — defense evasion via audit tampering detection

### P1 gaps (recommended after P0)

- **4656/4660 (Handle request/Object deleted)** — file system audit correlation
- **4673/4674 (Privilege use)** — sensitive privilege exercise monitoring
- **4699–4702 (Scheduled task lifecycle)** — complete task monitoring
- **4768/4769/4771/4776 (DC authentication)** — Kerberos/NTLM attack detection on domain controllers
- **4798/4799 (Group enumeration)** — reconnaissance detection

### P2 gaps (defer unless scenario-driven)

- **4658 (Handle closed)** — correlation support only
- **4649/4675 (Replay/SID filter)** — niche security events
- **4770 (Kerberos renewal)** — low detection value
- **4713/4739 (Policy changes)** — domain controller specific

## Verification hooks for closing gaps

For each Event ID promoted to "routed" (especially P0/P1):

1. **Golden input fixtures**

   - Provide representative Windows Security event payloads (XML/EVTX extract or JSON projection)
     for the Event ID.
   - Include edge cases (placeholder IPs, missing optional fields, SID vs username, various logon
     types).

1. **Golden normalized output**

   - Expected OCSF JSON events (canonical form) with stable `class_uid`, `activity_id`, and stable
     identity/provenance fields.

1. **CI gates**

   - A test MUST fail if a routed Event ID is missing from output when its input fixture is present.
   - A test MUST fail if required pivots for the Event ID are absent (per the acceptance list
     below).

### Minimum acceptance criteria per routed Event ID

When adding a new Windows Security Event ID route, the normalizer MUST:

- Emit the correct `class_uid` and `activity_id` for every fixture input.
- Populate `device.*` identity and `metadata.*` provenance fields per ADR-0002 (event identity and
  provenance).
- Populate the event-family pivots needed for Sigma evaluation (see Appendix A).

## Appendix A: Expected Sigma rule impact by gap

This appendix describes how each gap is expected to affect Sigma rule execution and coverage, based
on common Sigma logsource categories and representative Sigma rules.

### Why this matters for Sigma

Sigma rules identify their target telemetry using a `logsource` consisting of `category`, `product`,
and optional `service`; mismatches can render a rule ineffective even if "similar" data exists
elsewhere. Pipelines/backends often use `logsource` to scope queries and apply field mappings.

The Sigma main repository contains more than 3000 detection rules overall, so even "one category"
gaps can have non-trivial downstream impact.

### P0 gaps and expected Sigma impact

#### Event ID 4697 (Service installed) → Sigma `windows/builtin/security`

**Representative rule fields** commonly include:

- `ServiceName` (service display name)
- `ServiceFileName` (executable path)
- `ServiceType`, `ServiceStartType`
- Subject user fields

**Expected impact if unmapped:**

- Service installation persistence detections (including malicious service creation patterns) will
  not execute against OCSF-normalized data.

#### Event ID 4698 (Scheduled task created) → Sigma `windows/builtin/security`

**Representative rule fields** commonly include:

- `TaskName` (scheduled task name)
- `TaskContent` (XML definition including command/arguments)
- Subject user fields

**Expected impact if unmapped:**

- Scheduled task persistence detections (T1053.005) will not match. This is a commonly observed
  persistence mechanism in real-world attacks.

#### Event ID 4672 (Special privileges) → Sigma `windows/builtin/security`

**Representative rule fields** commonly include:

- `PrivilegeList` (privileges assigned)
- Subject user fields
- Logon ID for correlation

**Expected impact if unmapped:**

- Privilege escalation detections that monitor for sensitive privilege assignment will not execute.

#### Event ID 4663 (Object access) → Sigma `file_access` and custom rules

**Representative rule fields** commonly include:

- `ObjectName` (file/registry path)
- `ObjectType` (File, Key, etc.)
- `AccessMask` or `Accesses` (read/write/delete)
- `ProcessName`, `ProcessId`

**Expected impact if unmapped:**

- File access monitoring for sensitive files (SAM, NTDS.dit, etc.) will not execute.
- Registry access detections for persistence and defense evasion will be absent.

#### Event ID 4648 (Explicit credentials) → Sigma `windows/builtin/security`

**Representative rule fields** commonly include:

- Subject user fields (user performing the action)
- Target user fields (credentials being used)
- Target server name
- Process information

**Expected impact if unmapped:**

- Pass-the-hash and credential reuse detections will not match.
- Lateral movement patterns using explicit credentials will be missed.

#### Event ID 4719 (Audit policy changed) → Sigma `windows/builtin/security`

**Representative rule fields** commonly include:

- `SubcategoryGuid` or `CategoryId`
- `AuditPolicyChanges` (success/failure enabled/disabled)
- Subject user fields

**Expected impact if unmapped:**

- Defense evasion detections for audit tampering will not execute.

### P1/P2 gaps: expected Sigma impact (summary)

- **Object access lifecycle (4656/4660):** impacts file system audit correlation; required for
  complete object access story but less frequently used in standalone rules.
- **Privilege use (4673/4674):** impacts sensitive privilege exercise monitoring; high volume but
  valuable for specific investigations.
- **DC authentication (4768/4769/4771/4776):** impacts Kerberos attack detection (Golden Ticket,
  Kerberoasting, AS-REP roasting); DC-specific but high-value when applicable.
- **Group enumeration (4798/4799):** impacts reconnaissance detection; relatively new events with
  growing rule coverage.

## Known limitations in the current profile

The mapping profile documents several known limitations for v0.1:

1. **Authentication events:** Some Windows Security Event IDs provide incomplete network context
   (IpAddress placeholders, missing port). Domain controller "Account Logon" events are explicitly
   out of scope unless enabled.

1. **File and registry activity:** Security channel events represent access checks and do not always
   cleanly map to a single file/registry action without inference. The profile recommends
   `activity_id = 0` (Unknown) when action cannot be determined.

1. **Command line and sensitive fields:** Redaction policy must be applied before emitting
   normalized fields.

## References

- Microsoft Learn: Windows Security Event documentation (TBD / Needs confirmation)
- Microsoft Learn: Appendix L - Events to Monitor (TBD / Needs confirmation)
- Ultimate Windows Security: Event ID encyclopedia (TBD / Needs confirmation)
- SigmaHQ logsource documentation (TBD / Needs confirmation)
- SigmaHQ rule repository (size/scale) (TBD / Needs confirmation)
