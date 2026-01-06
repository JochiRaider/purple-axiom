<!-- docs/spec/065_sigma_to_ocsf_bridge.md -->
# Sigma-to-OCSF Bridge

## Problem statement
Sigma rules typically assume a **producer-specific log schema** (Windows Security, Sysmon, auditd, Zeek, etc.) expressed through:
- `logsource` (routing signal)
- field names referenced in `detection` selectors

Purple Axiom normalizes telemetry into **OCSF** before evaluation. The Sigma-to-OCSF Bridge provides a contract-driven compatibility layer that makes Sigma rules executable against OCSF events without abandoning OCSF as the canonical store.

## Goals
- Make Sigma evaluation **first-class** in an OCSF-first pipeline.
- Keep the bridge deterministic, versioned, and auditable.
- Attribute misses to one of: missing telemetry, normalization gap, bridge gap, rule logic gap.

## Non-goals
- “Run every Sigma rule unmodified” as a hard guarantee.
- Perfect semantic equivalence between producer-specific event types and OCSF classes for all sources.
- Correlation / multi-event sequence semantics beyond what the chosen evaluator backend supports in MVP.

## Core concept
The bridge is a composition of three artifacts:

1) **Logsource router**
2) **Field alias map**
3) **Evaluator backend adapter**

Together, these compile Sigma rules into an executable plan over OCSF events.

## 1) Logsource router

### Inputs
Sigma `logsource` fields:
- `category` (primary)
- `product`, `service` (secondary, optional)

### Output
An OCSF query scope:
- required: one or more OCSF class filters (preferred: `class_uid` or class name)
- optional: producer predicates (examples: `metadata.source_type`, `metadata.product.name`, `raw.channel`, `raw.provider`)

### Rules
- Route primarily on `logsource.category`.
- Use `product/service` only to **narrow** when necessary.
- If routing cannot be determined, the rule is **non-executable** (fail-closed).

### Mapping packs
Adopt SigmaHQ’s OCSF routing where possible, then constrain to your pinned OCSF version and enabled profiles.

The mapping pack is versioned independently of:
- the Sigma ruleset version
- the Purple Axiom pipeline version

## 2) Field alias map

### Purpose
Translate Sigma field references into OCSF JSONPaths (or evaluator-specific column expressions).

### Structure
Field aliases SHOULD be scoped by router result (at minimum by `logsource.category`), because field meaning varies by event family.

Recommended structure (conceptual):
- `aliases[logsource.category][sigma_field] -> ocsf_path_or_expr`
- `normalizers[sigma_field] -> value transforms` (case folding, path normalization, enum harmonization)

### Fallback policy (`raw.*`)
A controlled escape hatch is permitted for MVP:
- If an event attribute cannot be mapped yet, allow evaluation to reference `raw.*` when:
  - the event is still within the correct OCSF class scope, and
  - provenance clearly identifies the producer/source
- If fallback is used, it MUST be recorded (see “Bridge provenance in detections”).

Over time, the target is to reduce fallback rate by expanding normalized fields.

### Unsupported fields or modifiers
- If a rule references an unmapped field and fallback is disabled, the rule is **non-executable**.
- If a Sigma modifier cannot be expressed in the backend (example: complex regex semantics), the rule is **non-executable**.
- Non-executable rules are reported with reasons and counts.

## 3) Evaluator backend adapter

### Batch backend (recommended default)
- Compile Sigma -> SQL (after routing + aliasing)
- Execute over OCSF Parquet using DuckDB
- Return:
  - matched event ids (`metadata.event_id`)
  - first/last seen timestamps

### Streaming backend (optional)
- Compile Sigma -> expression plan
- Evaluate over a stream processor (example: Tenzir)
- Emit matches in near real time

### Backend contract
Regardless of backend, the evaluator MUST produce `detection_instance` rows in `detections/detections.jsonl` and MUST be able to explain non-executable rules.

## Bridge artifacts in the run bundle

When Sigma evaluation is enabled, the bridge SHOULD emit a small, contract-validated set of artifacts under `runs/<run_id>/bridge/` so routing, compilation, and coverage are mechanically testable:

- `router_table.json` (required)
  - Snapshot of `logsource` routing (Sigma category to OCSF scope).
  - Schema: `bridge_router_table.schema.json`.

- `mapping_pack_snapshot.json` (required)
  - Snapshot of the full bridge inputs (router + alias map + fallback policy).
  - Schema: `bridge_mapping_pack.schema.json`.
  - `mapping_pack_sha256` MUST be computed over stable mapping inputs and MUST NOT include run-specific fields.

- `compiled_plans/`
  - `compiled_plans/<rule_id>.plan.json` (required for each evaluated rule)
  - Deterministic compilation output for the chosen backend (SQL or IR), including non-executable reasons.
  - Schema: `bridge_compiled_plan.schema.json` per file.

- `coverage.json` (required)
  - Summary metrics and top failure modes (unrouted categories, unmapped fields, fallback usage).
  - Schema: `bridge_coverage.schema.json`.

These artifacts are intentionally small and diffable, and they enable CI to distinguish:
- telemetry gaps (no events)
- normalization gaps (missing required/core fields)
- bridge gaps (unrouted categories, unmapped fields, unsupported modifiers)
- rule logic gaps (compiled and executed but did not match expected activity)

## Bridge provenance in detections

Detection instances SHOULD include bridge metadata in `extensions.bridge`:
- `mapping_pack_id`
- `mapping_pack_version`
- `backend`
- `compiled_at_utc`
- `fallback_used`
- `unmapped_sigma_fields` (when applicable)
- `non_executable_reason` (when applicable)

Also store the original Sigma logsource under `extensions.sigma.logsource` (verbatim) when available.

## Determinism and reproducibility requirements
- Compilation is deterministic given:
  - rule content
  - mapping pack id/version
  - backend id/version
- Ordering:
  - `detections.jsonl` written in a deterministic order (see storage requirements)
- Fail-closed:
  - unknown logsource, unmapped fields (without fallback), or unsupported modifiers MUST not silently degrade into “no matches”

## Testing guidance (MVP)
- Golden tests:
  - For a small curated Sigma ruleset, compile to plans and assert stable outputs (diffable).
- Router tests:
  - For each supported `logsource.category`, assert the expected OCSF class scope.
- Alias tests:
  - For each supported category, assert that required Sigma fields map to existing OCSF fields in representative events.
- Backend tests:
  - Run the compiled plan against a fixed Parquet fixture and assert match sets and timestamps.

## MVP scope recommendation
Start with the event families that cover the majority of safe adversary emulation scenarios:
- process execution
- network connections
- DNS queries
- authentication/logon
- file writes (selectively)

Expand iteratively, using bridge coverage metrics to guide where mapping work has the highest scoring impact.