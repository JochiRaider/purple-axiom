# Scenario Model

## Scenario types
1) Caldera Operation
- One or more adversary profiles / abilities
- Agents + target groups
- Stop conditions and safety toggles

2) Atomic Test Plan
- Technique ID + test IDs
- Prereqs, input args, cleanup steps
- Safe mode flags

## Scenario identity
- scenario_id: stable identifier (human chosen)
- scenario_version: semver or date-based
- run_id: unique per execution

## Ground truth timeline schema (seed)
- timestamp_utc
- run_id, scenario_id, scenario_version
- target_asset_id
- action_type (caldera_ability | atomic_test | custom)
- technique_id (ATT&CK)
- command_summary (redacted-safe summary)
- expected_telemetry (channels / event types)
- cleanup_status
