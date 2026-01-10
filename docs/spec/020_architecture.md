<!-- docs/spec/020_architecture.md -->
# Architecture

## High-level flow
[Lab Provider] -> [Resolved Lab Inventory Snapshot]
                    |
                    v
  [Scenario Runner] -> [Ground Truth Timeline + Runner Artifacts]
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
      [Criteria Evaluator (sidecar pack) -> Criteria Results]
                       |
                       v                       
        [Sigma-to-OCSF Bridge (router + field aliases)]
                       |
                       v
        [Detection Engine (Sigma) -> Results]
                       |
                       v
        [Report Generator -> HTML + JSON + Artifacts]

## Components
### Lab Provider (inventory resolution)
- Resolves a concrete list of target assets and connection metadata from an external source.
- Implementations may be:
  - manual (inline `lab.assets`)
  - Ludus (consume generated inventory export)
  - Terraform (consume `terraform output -json` or an exported inventory file)
- Produces a run-scoped “lab inventory snapshot” recorded in the run bundle and referenced by the manifest.
  - This snapshot is treated as an input for determinism (hashable, diffable).

### Scenario Runner
- Executes test plans (Atomic tests for v0.1; Caldera operations are a future candidate).
- Emits a signed, append-only timeline: what ran, when, where, and with what *resolved* inputs.
- MUST record resolved target identifiers (asset_id plus resolved host identity) so that ground truth remains valid even if the provider inventory changes later.

Runner artifacts (evidence tier):
- Captures executor transcripts (stdout/stderr) and execution metadata (exit codes, durations).
- Treats cleanup as a staged lifecycle (invoke -> verify) and records verification results.

### Telemetry Collectors
- Endpoint logs (Windows Event Log receiver for OTel contrib; includes Sysmon Operational channel on Windows; Linux journald/syslog options later).
- Optional: osquery, EDR exports. Network sensors (pcap/netflow) are phase 2 for collection, but v0.1 reserves placeholder contracts.

### Normalizer
- Maps raw telemetry to OCSF categories/classes.
- Attaches provenance fields: source, host, tool version, scenario_id, run_id.

### Criteria Evaluator
Evaluates an externalized, versioned criteria pack against the normalized OCSF store.

Responsibilities:
- Load a criteria pack snapshot pinned in the run manifest.
- For each executed action (ground truth), match the appropriate criteria entry and evaluate expected signals within configured time windows.
- Emit `criteria_results.jsonl` for scoring and reporting.
- Emit cleanup verification results (either as part of criteria results or as runner-side evidence referenced by them).

### Sigma-to-OCSF Bridge
- Contract-driven compatibility layer that allows Sigma rules (logsource + fields) to be evaluated against OCSF-normalized events.
- Artifacts:
  - Logsource router: `sigma.logsource` -> OCSF class filter (and optional producer/source predicates)
  - Field alias map: Sigma field names -> OCSF JSONPaths (or SQL column expressions)
  - Backend adapters: compile to a batch plan (SQL over Parquet) or stream plan (in-memory)

### Detection Engine
- Loads Sigma rules and evaluates them against normalized OCSF events via the Sigma-to-OCSF Bridge.
- Produces detection instances, technique coverage, and latency measures.
- Fail-closed behavior: if the bridge cannot route a rule (unknown `logsource`) or map a referenced field, the rule is reported as non-executable for that run.

### Reporting
- Generates report bundle: HTML scorecard + JSON results + run manifest.

## Extension points
- New lab providers (manual, Ludus, Terraform, other)
- New runners (beyond Caldera/Atomic)
- New telemetry sources
- New schema mappings (OCSF profiles/versions)
- New rule languages (beyond Sigma, like yara or suricata)
- New Sigma bridge mapping packs (logsource router + field aliases)
- New evaluator backends (DuckDB/SQL, Tenzir, other engines)