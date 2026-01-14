---
title: R-05 Sysmon-to-OCSF Mapping Completeness (Sysmon EventIDs 1–29, 255)
description: Mapping coverage matrix for Sysmon EventIDs against the current Windows Sysmon → OCSF 1.7.0 mapping profile, including gap prioritization and verification hooks.
status: draft
---

# R-05 Sysmon-to-OCSF Mapping Completeness (Sysmon EventIDs 1–29, 255)

## Status

Draft (research report; mapping profile assessed as of 2026-01-13)

## Summary

This report answers:

- Which Sysmon EventIDs are **currently mapped** to OCSF classes by the project’s Windows Sysmon →
  OCSF 1.7.0 mapping profile.
- Which EventIDs are **unmapped** (coverage gaps), and a **P0/P1/P2** priority classification for
  closing those gaps.
- Which mapped EventIDs have **partial field coverage** that is likely to impact downstream
  detection content (Sigma).

**Key result:** The current profile routes **5 Sysmon EventIDs** (1, 3, 5, 11, 22) into OCSF
classes. All other Sysmon EventIDs (2–29, 255) are currently unmapped and therefore absent from
OCSF-normalized outputs. (Sysmon EventID catalog reference: Microsoft Learn) ([Microsoft Learn][1])

## Inputs and scope

### In-scope artifacts

- Project mapping profile: `windows-sysmon_to_ocsf_1.7.0.md` (local file)
- Sysmon EventID catalog (Sysinternals / Microsoft Learn) ([Microsoft Learn][1])

### Out of scope

- Implementing new mappings (this document identifies gaps and verification hooks only).
- Non-Sysmon Windows Event Log sources (e.g., Security 4688), except where noted in Sigma impact.

## Methodology

1. Extract “routed event families” and explicit EventID coverage from
   `windows-sysmon_to_ocsf_1.7.0.md`.

1. Compare against the Sysmon EventID catalog (EventIDs 1–29 and 255). ([Microsoft Learn][1])

1. For each EventID:

   - Mark as **Mapped** if present in the mapping profile’s routed families.
   - If mapped, record the **OCSF class_uid** and **activity_name** described by the profile.
   - Assign a **gap priority** using the criteria below.

## Gap priority definitions (P0/P1/P2)

- **P0:** High-signal endpoint telemetry that underpins common detection logic (e.g., process
  injection, credential access, persistence, defense evasion). Absence creates broad blind spots and
  blocks major Sigma logsource categories.
- **P1:** Valuable telemetry with meaningful detection value, but typically less universal, noisier,
  or more environment-dependent; recommended after P0 coverage.
- **P2:** Operability / niche / meta events; recommended only after P0/P1 or when required for a
  specific scenario or product constraint.

Sigma rules’ `logsource` selection is materially important (category/product/service mismatches can
make a rule ineffective), so missing telemetry families translate directly into missing Sigma
execution coverage. ([sigmahq.io][2])

## EventID-to-OCSF mapping matrix

| EventID | Sysmon event                                          | Current OCSF mapping (from profile)  | Coverage | Gap priority |
| ------: | ----------------------------------------------------- | ------------------------------------ | -------- | ------------ |
|       1 | Process creation                                      | Process Activity (1007) / Launch     | Strong   | OK           |
|       2 | A process changed a file creation time                | Unmapped (no route)                  | None     | P2           |
|       3 | Network connection                                    | Network Activity (4001) / Open       | Strong   | OK           |
|       4 | Sysmon service state changed                          | Unmapped (no route)                  | None     | P2           |
|       5 | Process terminated                                    | Process Activity (1007) / Terminate  | Strong   | OK           |
|       6 | Driver loaded                                         | Unmapped (no route)                  | None     | P1           |
|       7 | Image loaded                                          | Unmapped (no route)                  | None     | P0           |
|       8 | CreateRemoteThread                                    | Unmapped (no route)                  | None     | P0           |
|       9 | RawAccessRead                                         | Unmapped (no route)                  | None     | P1           |
|      10 | ProcessAccess                                         | Unmapped (no route)                  | None     | P0           |
|      11 | FileCreate                                            | File System Activity (1001) / Create | Strong   | OK           |
|      12 | RegistryEvent (Object create and delete)              | Unmapped (no route)                  | None     | P0           |
|      13 | RegistryEvent (Value Set)                             | Unmapped (no route)                  | None     | P0           |
|      14 | RegistryEvent (Key and Value Rename)                  | Unmapped (no route)                  | None     | P0           |
|      15 | FileCreateStreamHash                                  | Unmapped (no route)                  | None     | P1           |
|      16 | ServiceConfigurationChange                            | Unmapped (no route)                  | None     | P2           |
|      17 | PipeEvent (Pipe Created)                              | Unmapped (no route)                  | None     | P0           |
|      18 | PipeEvent (Pipe Connected)                            | Unmapped (no route)                  | None     | P0           |
|      19 | WmiEvent (WmiEventFilter activity detected)           | Unmapped (no route)                  | None     | P0           |
|      20 | WmiEvent (WmiEventConsumer activity detected)         | Unmapped (no route)                  | None     | P0           |
|      21 | WmiEvent (WmiEventConsumerToFilter activity detected) | Unmapped (no route)                  | None     | P0           |
|      22 | DNSEvent (DNS query)                                  | DNS Activity (4003) / Query          | Moderate | P1 (partial) |
|      23 | FileDelete (File Delete archived)                     | Unmapped (no route)                  | None     | P1           |
|      24 | ClipboardChange (New content in the clipboard)        | Unmapped (no route)                  | None     | P2           |
|      25 | ProcessTampering (Process image change)               | Unmapped (no route)                  | None     | P1           |
|      26 | FileDeleteDetected (File Delete logged)               | Unmapped (no route)                  | None     | P1           |
|      27 | FileBlockExecutable                                   | Unmapped (no route)                  | None     | P1           |
|      28 | FileBlockShredding                                    | Unmapped (no route)                  | None     | P1           |
|      29 | FileExecutableDetected                                | Unmapped (no route)                  | None     | P1           |
|     255 | Error                                                 | Unmapped (no route)                  | None     | P2           |

(Sysmon EventID names are taken from the Sysmon documentation catalog.) ([Microsoft Learn][1])

## Field coverage analysis

This section focuses on EventIDs that are currently routed. Unrouted EventIDs have **no** field
coverage because events are not present in normalized outputs.

### Pivot coverage for routed EventIDs

| EventID | OCSF class           | Actor process | Actor user | Target file | Network endpoints | DNS query |
| ------- | -------------------- | ------------- | ---------- | ----------- | ----------------- | --------- |
| 1       | Process Activity     | Yes           | Yes        | No          | No                | No        |
| 3       | Network Activity     | Yes           | Yes        | No          | Yes               | No        |
| 5       | Process Activity     | Yes           | Yes        | No          | No                | No        |
| 11      | File System Activity | Yes           | Yes        | Yes         | No                | No        |
| 22      | DNS Activity         | Yes           | Yes        | No          | No                | Yes       |

### Notable partial coverage (current routed set)

- **EventID 22 (DNS query):** routed to **DNS Activity (4003)** but the profile currently maps the
  query and basic metadata; answer material (e.g., resolved IPs, response codes) is not represented
  as core pivots in the current mapping profile. This is treated as **P1 (partial)** to reflect
  detection content that relies on response details.

## P0/P1/P2 gap breakdown

### P0 gaps (recommended next)

These EventIDs commonly underpin high-value endpoint detection content:

- **7 (Image loaded)** — DLL/module load telemetry ([Microsoft Learn][1])
- **8 (CreateRemoteThread)** — process injection primitives ([Microsoft Learn][1])
- **10 (ProcessAccess)** — access to sensitive processes (e.g., LSASS) ([Microsoft Learn][1])
- **12/13/14 (Registry events)** — persistence and defense evasion via registry manipulation
  ([Microsoft Learn][1])
- **17/18 (Named pipe events)** — C2 and lateral movement indicators (requires Sysmon config
  enablement) ([Microsoft Learn][1])
- **19/20/21 (WMI events)** — WMI persistence and execution ([Microsoft Learn][1])

### P1 gaps (recommended after P0)

- **6 (Driver loaded)** ([Microsoft Learn][1])
- **9 (RawAccessRead)** ([Microsoft Learn][1])
- **15 (FileCreateStreamHash)** ([Microsoft Learn][1])
- **23/26 (File delete variants)** ([Microsoft Learn][1])
- **25 (Process tampering)** ([Microsoft Learn][1])
- **27/28/29 (File block / executable detection family)** ([Microsoft Learn][1])

### P2 gaps (defer unless scenario-driven)

- **2 (File creation time changed)** ([Microsoft Learn][1])
- **4 (Sysmon service state changed)** ([Microsoft Learn][1])
- **16 (Service configuration change)** ([Microsoft Learn][1])
- **24 (Clipboard change)** ([Microsoft Learn][1])
- **255 (Error)** ([Microsoft Learn][1])

## Verification hooks for closing gaps

For each EventID promoted to “routed” (especially P0/P1):

1. **Golden input fixtures**

   - Provide representative Sysmon event payloads (XML/EVTX extract or JSON projection) for the
     EventID.
   - Include edge cases (missing optional fields, path casing, SID vs username, null hashes).

1. **Golden normalized output**

   - Expected OCSF JSON events (canonical form) with stable `class_uid`, `activity_name`, and stable
     identity/provenance fields.

1. **CI gates**

   - A test MUST fail if a routed EventID is missing from output when its input fixture is present.
   - A test MUST fail if required pivots for the EventID are absent (per the acceptance list below).

### Minimum acceptance criteria per routed EventID

When adding a new Sysmon EventID route, the normalizer MUST:

- Emit the correct `class_uid` and `activity_name` for every fixture input.
- Populate `device.*` identity and `metadata.*` provenance fields per ADR-0002 (event identity and
  provenance).
- Populate the event-family pivots needed for Sigma evaluation (see Appendix A).

## Appendix A: Expected Sigma rule impact by gap

This appendix describes how each gap is expected to affect Sigma rule execution and coverage, based
on common Sigma logsource categories and representative Sigma rules.

### Why this matters for Sigma

Sigma rules identify their target telemetry using a `logsource` consisting of `category`, `product`,
and optional `service`; mismatches can render a rule ineffective even if “similar” data exists
elsewhere. Pipelines/backends often use `logsource` to scope queries and apply field mappings.
([sigmahq.io][2])

Also note the Sigma main repository contains **more than 3000** detection rules overall, so even
“one category” gaps can have non-trivial downstream impact. ([GitHub][3])

### P0 gaps and expected Sigma impact

#### EventID 10 (ProcessAccess) → Sigma `process_access`

**Representative rule fields** commonly include:

- `TargetImage` (sensitive target process, e.g., `\lsass.exe`)
- `GrantedAccess` and/or `CallTrace`
- `SourceImage` ([Detection][4])

**Expected impact if unmapped:**

- Rules in the `process_access` logsource category will not match, and detections for credential
  access / LSASS access behavior will be absent. ([Detection][4])

#### EventID 8 (CreateRemoteThread) → Sigma `create_remote_thread`

**Representative rule fields** commonly include:

- `TargetImage` (often `\lsass.exe`)
- `StartModule` / start address module context (varies by rule/backend support) ([Detection][5])

**Expected impact if unmapped:**

- Process injection / remote thread detections (including credential dumping patterns) will not
  execute. ([Detection][5])

#### EventID 7 (Image loaded) → Sigma `image_load`

**Representative rule fields** commonly include:

- `ImageLoaded` (loaded module path)
- Optional signature metadata (`Signed`, `Company`, `Product`, `Description`) ([Detection][6])

**Expected impact if unmapped:**

- DLL sideloading / hijacking detections that depend on module load telemetry will be absent.
  ([Detection][6])

#### EventIDs 12/13/14 (Registry events) → Sigma `registry_set` and `registry_event`

**Representative rule fields** commonly include:

- `TargetObject` (registry path)
- `Details` (value data) for `registry_set` ([Detection][7])
- `EventType`, `NewName` (create/rename flows) for `registry_event` ([Detection][8])

**Expected impact if unmapped:**

- Many persistence and defense-evasion detections that hinge on registry manipulation (ETW tamper,
  disabling event logging, Run key persistence, etc.) will not execute. ([Detection][7])

#### EventIDs 19/20/21 (WMI events) → Sigma `wmi_event`

**Representative rule fields** commonly include:

- `EventID` in `{19, 20, 21}` (and often accompanying object details depending on rule)
  ([Detection][9])

**Expected impact if unmapped:**

- WMI subscription persistence detections will be absent. ([Detection][9])

#### EventIDs 17/18 (Pipe events) → Sigma `pipe_created`

**Representative rule fields** commonly include:

- `PipeName` (pattern matching is common)
- Optional `Image`/process context depending on backend ([Detection][10])

**Expected impact if unmapped:**

- Named pipe based detections (including C2 patterns) will be absent. Sigma rules in this family may
  also include `definition` guidance indicating Sysmon Named Pipe events must be enabled in Sysmon
  configuration (i.e., they are not always present by default). ([Detection][10])

### P1/P2 gaps: expected Sigma impact (summary)

- **Driver loaded (6):** impacts kernel driver / rootkit-related rules where present; typically
  fewer rules than process/registry families but still high-signal when used. ([Microsoft Learn][1])
- **RawAccessRead (9):** can support credential dumping or disk forensics detection; niche and
  environment-dependent. ([Microsoft Learn][1])
- **Process tampering (25):** can support defense evasion; emerging rule content likely to grow.
  ([Microsoft Learn][1])
- **File delete & block families (23/26/27/28/29):** may support anti-forensics and
  controlled-execution detections; depends heavily on Sysmon config and environment.
  ([Microsoft Learn][1])

## References (descriptive)

- Microsoft Learn: Sysmon EventID catalog ([Microsoft Learn][1])
- SigmaHQ: Logsource documentation ([sigmahq.io][2])
- SigmaHQ rule repository (size/scale) ([GitHub][3])
- Representative Sigma rules (mirrored via detection.fyi) ([Detection][4])

[1]: https://learn.microsoft.com/en-us/sysinternals/downloads/sysmon "Sysmon - Sysinternals | Microsoft Learn"
[2]: https://sigmahq.io/docs/basics/log-sources.html "Logsources | Sigma Detection Format"
[3]: https://github.com/SigmaHQ/sigma "GitHub - SigmaHQ/sigma: Main Sigma Rule Repository"
[4]: https://detection.fyi/sigmahq/sigma/windows/process_access/proc_access_win_lsass_susp_access_flag/ "Potentially Suspicious GrantedAccess Flags On LSASS | Detection.FYI"
[5]: https://detection.fyi/sigmahq/sigma/windows/create_remote_thread/create_remote_thread_win_susp_password_dumper_lsass/ "Password Dumper Remote Thread in LSASS | Detection.FYI"
[6]: https://detection.fyi/sigmahq/sigma/windows/image_load/image_load_side_load_python/ "Potential Python DLL SideLoading | Detection.FYI"
[7]: https://detection.fyi/sigmahq/sigma/windows/registry/registry_set/registry_set_services_etw_tamper/ "ETW Logging Disabled For SCM | Detection.FYI"
[8]: https://detection.fyi/sigmahq/sigma/windows/registry/registry_event/registry_event_disable_security_events_logging_adding_reg_key_minint/ "Disable Security Events Logging Adding Reg Key MiniNt | Detection.FYI"
[9]: https://detection.fyi/sigmahq/sigma/windows/wmi_event/sysmon_wmi_event_subscription/ "WMI Event Subscription | Detection.FYI"
[10]: https://detection.fyi/sigmahq/sigma/windows/pipe_created/pipe_created_hktl_cobaltstrike_susp_pipe_patterns/ "CobaltStrike Named Pipe Patterns | Detection.FYI"
