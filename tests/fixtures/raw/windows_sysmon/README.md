# Raw Sysmon fixtures (v0.1)

These fixtures are minimal, deterministic inputs for unit tests of the **windows-sysmon → OCSF
1.7.0** mapping profile.

## File naming

- `eid_XXXX_<description>.json` where `XXXX` is the Sysmon `event_id` zero-padded to 4 digits.

## Input shape (normative for fixtures)

Each fixture is a single JSON object with:

- `provider` (string)
- `channel` (string)
- `event_id` (int)
- `record_id` (int)
- `time_created` (RFC3339 UTC string)
- `computer` (string)
- `event_data` (object): Sysmon EventData key/value pairs
- `_fixture` (object): test harness context (run/scenario/version identifiers)

The normalizer MUST treat `event_data` as the authoritative Sysmon payload for these fixtures.
