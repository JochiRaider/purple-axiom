# Normalized Sysmon fixtures (v0.1)

These fixtures are the expected normalized **OCSF event envelopes** for the corresponding raw Sysmon
fixtures.

## Pairing

For each raw fixture:

- `tests/fixtures/raw/windows_sysmon/<name>.json`

there is a matching golden output:

- `tests/fixtures/normalized/ocsf/1.7.0/windows_sysmon/<name>.json`

## Required envelope fields

Each golden output includes the minimum required envelope fields from
`docs/spec/025_data_contracts.md`:

- `time` (ms since epoch, UTC)
- `class_uid`
- `metadata.event_id` (deterministic)
- `metadata.run_id`
- `metadata.scenario_id`
- `metadata.collector_version`
- `metadata.normalizer_version`
- `metadata.source_type`
- `metadata.source_event_id`

## Fixture event_id algorithm (deterministic)

Until the project’s event identity ADR vectors are wired into this harness, these fixtures compute:

`metadata.event_id = sha256_hex(JCS({provider, channel, event_id, record_id, computer, time}))`

where `time` is the fixture’s `time_created` converted to epoch milliseconds and `JCS` is a stable,
sorted-key JSON serialization (RFC 8785-like).
