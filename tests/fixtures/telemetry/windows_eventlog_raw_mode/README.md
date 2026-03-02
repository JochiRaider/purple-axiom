# Telemetry fixture pack: windows_eventlog_raw_mode

This fixture pack is a **stage isolation** suite for the `telemetry` stage.

It exercises two deterministic, fixture-assertable gates:

1. **Windows Event Log raw-mode canary** evidence in `logs/telemetry_validation.json.windows_eventlog_raw_mode`.
2. **Windows raw XML availability** evidence and counters in `logs/telemetry_validation.json.windows_eventlog_raw_xml`.

## Case matrix

| Case | Intent | Expected stage behavior |
| --- | --- | --- |
| `winlog_raw_mode_smoke_ok` | Canary present, raw XML available | Pass; `windows_eventlog_raw_mode.observed=true`; raw XML counters present and zeroed |
| `winlog_raw_mode_missing_canary_fails_closed` | No canary event present | Fail-closed (stage outcome `reason_code=winlog_raw_missing`); `canary_observed_at` omitted |
| `winlog_raw_mode_rendering_detected_fails_closed` | Canary present but contains `<RenderingInfo>` | Fail-closed (`reason_code=winlog_rendering_detected`); `observed=false`; `canary_observed_at` present |
| `winlog_raw_xml_unavailable_fail_closed` | Missing `log.record.original` | Fail-closed; `windows_eventlog_raw_xml.reason_code=raw_xml_unavailable` when fail mode is `fail_closed` |
| `winlog_raw_xml_unavailable_warn_and_skip` | Missing `log.record.original` but warn/skip policy | Not fatal; `windows_eventlog_raw_xml.reason_code` omitted when fail mode is `warn_and_skip` |

## Fixture structure

Each case directory contains:

- `runs/<run_id>/...` — a **pruned run bundle** containing only the telemetry stage’s required inputs.
- `expected_outputs.json` — stage isolation expected outputs manifest.
- `telemetry_validation.assertions.v1.yaml` — semantic assertions against `logs/telemetry_validation.json`.

## Canary identity (deterministic)

These fixtures model the raw-mode canary as the **synthetic correlation marker token** embedded
inside the raw Windows Event XML payload.

Marker canonical string (v1):

- `pa:synth:v1:<run_id>:<action_id>:execute`

See `025_data_contracts.md` (`extensions.synthetic_correlation_marker`).

In these fixtures:

- `ground_truth.jsonl` includes `extensions.synthetic_correlation_marker` for the action, and
- the Windows Event XML corpus line embeds the same marker string inside an `<Event>` payload.

## Notes / TODOs

- The concrete ingestion wiring for `inputs/telemetry_fixture/*.jsonl` is implementation-defined.
  This pack includes a suggested JSONL representation that is easy to generate deterministically.
- If the config key controlling raw-XML fail behavior differs from the placeholder used here,
  adjust `inputs/range.yaml` accordingly.
