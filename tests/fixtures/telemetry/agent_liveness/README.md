# Telemetry fixture pack: agent_liveness

Stage isolation fixtures for the telemetry validator’s **agent heartbeat / liveness** gate.

This suite asserts deterministic evidence in `logs/telemetry_validation.json.agent_liveness`.

## Cases

| Case | Intent | Expected behavior |
| --- | --- | --- |
| `agent_liveness_smoke_ok` | Required heartbeat metric names observed during startup grace | Pass; per-asset `observed=true` and timestamps present |
| `agent_liveness_missing_fails_closed` | Heartbeat metric names not observed for an expected asset | Fail-closed (stage outcome `reason_code=agent_heartbeat_missing`); per-asset `observed=false` and `first_seen/last_seen` omitted |

## Notes

- These fixtures include a WinEventLog canary record so that other telemetry gates (raw-mode canary)
  do not mask liveness failures.
- The telemetry fixture ingestion inputs under `inputs/telemetry_fixture/` are a suggested deterministic
  representation; the concrete wiring is implementation-defined.
