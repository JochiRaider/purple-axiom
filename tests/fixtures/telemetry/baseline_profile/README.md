# Telemetry fixture pack: baseline_profile

Stage isolation fixtures for the telemetry validator’s **telemetry baseline profile** gate.

This suite asserts deterministic evidence in `logs/telemetry_validation.json.baseline_profile`.

## Cases

| Case | Intent | Expected behavior |
| --- | --- | --- |
| `baseline_profile_smoke_ok` | Baseline profile present and required signals observed | Pass; `profile_path` + `profile_sha256` present; per-asset `matched_profile_id` and per-signal `passed=true` |
| `baseline_profile_missing_fails_closed` | Gate enabled but profile missing/unreadable | Fail-closed (stage outcome `reason_code=baseline_profile_missing`); `profile_sha256` omitted |

## Notes

- These fixtures include an agent heartbeat metric set and a WinEventLog canary record so that other
  telemetry gates do not mask baseline-profile behavior.
- The baseline profile snapshot input file is `runs/<run_id>/inputs/telemetry_baseline_profile.json`
  (contract: `telemetry_baseline_profile`).
