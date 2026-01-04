# Architecture

## High-level flow
[Scenario Runner] -> [Ground Truth Timeline]
                     |
                     v
               [Telemetry Collectors]
                     |
                     v
             [OTel Collector Pipeline]
                     |
                     v
          [Normalizer -> OCSF Event Store]
                     |
                     v
     [Detection Engine (Sigma rules) -> Results]
                     |
                     v
     [Report Generator -> HTML + JSON + Artifacts]

## Components
### Scenario Runner
- Executes test plans (Caldera operations and/or Atomic tests).
- Emits a signed, append-only timeline: what ran, when, where, parameters, expected signals.

### Telemetry Collectors
- Endpoint logs (Windows Event Log receiver for OTel contrib; Linux journald/syslog options later).
- Optional: osquery, Sysmon, EDR exports, network sensors (phase 2).

### Normalizer
- Maps raw telemetry to OCSF categories/classes.
- Attaches provenance fields: source, host, tool version, scenario_id, run_id.

### Detection Engine
- Loads Sigma rules and evaluates against normalized OCSF events.
- Produces detection instances, technique coverage, and latency measures.

### Reporting
- Generates report bundle: HTML scorecard + JSON results + run manifest.

## Extension points
- New runners (beyond Caldera/Atomic)
- New telemetry sources
- New schema mappings (OCSF profiles/versions)
- New rule languages (beyond Sigma)
