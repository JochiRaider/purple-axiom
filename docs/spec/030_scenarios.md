<!-- docs/spec/030_scenarios.md -->
# Scenario Model

## Separation of concerns
- A scenario defines WHAT to execute and HOW to parameterize it.
- A lab provider defines WHERE it runs by resolving concrete target assets.
- Scenarios should target assets via stable selectors (asset_id, tags, roles), then the provider resolves those selectors to concrete hosts for the run.

## Scenario types
1) Caldera Operation
   - One or more adversary profiles / abilities
   - Agents + target groups
   - Stop conditions and safety toggles

2) Atomic Test Plan
   - Technique ID + test IDs (Atomic GUIDs)
   - Prereqs, input args, cleanup steps
   - Safe mode flags

3) Mixed Plan
   - A Caldera operation plus a set of Atomics
   - Used for “breadth + depth” runs

## Execution model (runner requirements)

Purple Axiom treats scenario execution as a staged lifecycle per action:

1. **Resolve** inputs (explicit, repeatable parameter resolution)
2. **Execute** (capture stdout/stderr + executor metadata)
3. **Cleanup** (invoke cleanup command when applicable)
4. **Cleanup verification** (verify post-conditions; “cleanup ran” is not sufficient)

The runner MUST persist:

- Ground truth timeline entries (contracted)
- Runner evidence artifacts (stdout/stderr transcripts, executor metadata, cleanup verification results)

## Stable action identity (join keys)

Each executed action MUST include two identifiers:

- `action_id` (unique within a run): used to correlate all per-run artifacts.
- `action_key` (stable across runs): used as the deterministic join key for regression comparisons.

`action_key` MUST be computed from a canonical JSON object with the following minimum fields:

- `engine` (atomic|caldera|custom)
- `technique_id`
- `engine_test_id` (Atomic test GUID / Caldera ability id / equivalent canonical id)
- `target_asset_id`
- `resolved_inputs_sha256` (hash of resolved inputs; not the raw inputs)

Then:

- `action_key = sha256(canonical_json_bytes)`

Notes:

- `action_key` MUST NOT incorporate `run_id` or timestamps.
- `action_key` SHOULD NOT embed secrets; use hashes for resolved inputs and store redacted inputs separately.

## Criteria linkage (expected telemetry)

Expected telemetry is externalized into criteria packs (see `035_validation_criteria.md`):

- Ground truth MAY include `expected_telemetry_hints` as coarse hints.
- Ground truth SHOULD include a `criteria_ref` when a criteria entry is selected.
- Scoring MUST prefer criteria evaluation outputs when present.

## Scenario identity
- scenario_id: stable identifier (human chosen)
- scenario_version: semver or date-based
- run_id: unique per execution

## Target selection (seed)
- target_selector:
  - asset_ids (optional): explicit list
  - tags (optional): match-any tags
  - roles (optional): match-any roles
  - os (optional): constrain to OS families
- The resolved targets for a run are written into the run manifest and an inventory snapshot artifact.

## Ground truth timeline schema (seed)
- timestamp_utc
- run_id, scenario_id, scenario_version
- target_asset_id
- resolved_target (seed)
  - hostname (optional)
  - ip (optional)
  - provider_asset_ref (optional): provider-native identifier
- action_type (caldera_ability | atomic_test | custom)
- technique_id (ATT&CK)
- command_summary (redacted-safe summary)
- parameters (seed)
  - input_args_redacted (optional)
  - input_args_sha256 (optional)
- expected_telemetry (channels / event types)
- cleanup_status

 ## Seed schema: Scenario Definition (v0.1)
 
 ```yaml
 scenario_id: "scn-2026-01-001"
 version: "0.1.0"
 name: "Atomic T1059.001 Powershell"
 description: "Basic PowerShell execution and related telemetry"
 safety:
   max_runtime_seconds: 600
   allow_network: false
   allow_persistence: false
 targets:
   - selector: { role: "endpoint", os: "windows" }
 plan:
    type: "atomic"
     technique_id: "T1059.001"
    engine_test_id: "d3c1...guid"
     input_args:
       command: "whoami"
     cleanup: true
````

## Ground truth timeline entry (v0.1)

Ground truth is emitted as JSONL, one action per line.

```json
{
  "timestamp_utc": "2026-01-03T12:00:00Z",
  "run_id": "run-2026-01-03-001",
  "scenario_id": "scn-2026-01-001",
  "scenario_version": "0.1.0",
  "action_id": "s1",
  "action_key": "sha256hex...",
  "engine": "atomic",
  "engine_test_id": "d3c1...guid",
  "technique_id": "T1059.001",
  "target_asset_id": "win11-test-01",
  "resolved_target": {
    "hostname": "WIN11-TEST-01",
    "ip": "192.0.2.10"
  },
  "command_summary": "powershell.exe -NoProfile ... (redacted)",
  "parameters": {
    "input_args_redacted": {
      "command": "whoami"
    },
    "input_args_sha256": "sha256hex...",
    "resolved_inputs_sha256": "sha256hex..."
  },
  "criteria_ref": {
    "criteria_pack_id": "default",
    "criteria_pack_version": "0.1.0",
    "criteria_entry_id": "atomic/T1059.001/d3c1...guid/windows"
  },
  "expected_telemetry_hints": {
    "ocsf_class_uids": [1001, 1005]
  },
  "cleanup": {
    "invoked": true,
    "status": "success",
    "verification": {
      "status": "success",
      "results_ref": "runner/actions/s1/cleanup_verification.json"
    }
  }
}
```
