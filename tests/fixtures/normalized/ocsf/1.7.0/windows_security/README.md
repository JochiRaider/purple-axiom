# Windows Security normalized golden fixtures (OCSF 1.7.0)

These JSON files are the expected OCSF outputs for the corresponding raw fixtures.

Notes:

- `time` is epoch milliseconds.
- `metadata.event_id` is computed per ADR-0002 (pa:eid:v1 + sha256(JCS(identity_basis)) truncated to
  128 bits).
- `metadata.uid` MUST equal `metadata.event_id`.
- Fields with non-authoritative inputs MUST be absent (not null).
