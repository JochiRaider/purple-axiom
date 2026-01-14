---
title: Research index
description: One-page map of exploratory and transient research documents in docs/research.
status: draft
---

# Research index

This file provides a single-page map of the research documents under `docs/research/` to keep
working sets small. Research documents are exploratory and non-normative unless explicitly promoted
in specs or ADRs.

## Overview

The research documents in this directory capture experiments, conformance reports, and mapping
coverage studies that inform v0.1 decisions. Use this index to locate the relevant report without
opening every document.

## File map (covers all docs/research files)

| Research doc file                                                   | Primary purpose (authoritative for)                                                  |
| ------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| `R-01_otel_filelog_checkpoint_reliability.md`                       | OTel filelog checkpoint reliability harness and acceptance criteria for NDJSON       |
| `R-02_DuckDB_Conformance_Report_and_Harness_Requirements_v1.4.3.md` | DuckDB plan and result stability conformance harness and report contract             |
| `R-03_DuckDB_Backend_Plugin_for_pySigma.md`                         | pySigma DuckDB backend capability surface, SQL patterns, and policy decisions        |
| `R-04_EPS_baseline_quantification.md`                               | EPS baselines for Windows telemetry and v0.1 resource budget guidance                |
| `R-05_Sysmon-to-OCSF_mapping.md`                                    | Sysmon EventID mapping coverage and gap prioritization against OCSF 1.7.0            |
| `R-06_Windows_Security_to_OCSF_Mapping.md`                          | Windows Security Event ID mapping coverage and gap prioritization against OCSF 1.7.0 |
| `R-07_osquery_to_OCSF_Mapping.md`                                   | osquery evented table mapping coverage and gap prioritization against OCSF 1.7.0     |
| `RESEARCH_INDEX.md`                                                 | This index                                                                           |

## Common tasks (fast paths)

| Need                                                | Read first                                                          |
| --------------------------------------------------- | ------------------------------------------------------------------- |
| “Where is the OTel filelog checkpoint report?”      | `R-01_otel_filelog_checkpoint_reliability.md`                       |
| “Where is the DuckDB conformance report?”           | `R-02_DuckDB_Conformance_Report_and_Harness_Requirements_v1.4.3.md` |
| “Where is the pySigma DuckDB backend policy doc?”   | `R-03_DuckDB_Backend_Plugin_for_pySigma.md`                         |
| “Where are EPS baselines for v0.1 sizing?”          | `R-04_EPS_baseline_quantification.md`                               |
| “Where is the Sysmon mapping completeness report?”  | `R-05_Sysmon-to-OCSF_mapping.md`                                    |
| “Where is the Windows Security mapping report?”     | `R-06_Windows_Security_to_OCSF_Mapping.md`                          |
| “Where is the osquery mapping completeness report?” | `R-07_osquery_to_OCSF_Mapping.md`                                   |

## Update rule (required)

When you add, rename, or remove a file in `docs/research/`:

- Update this index to point to the authoritative research document (keep it one page).
- Prefer pointers to existing documents over duplicated prose.
