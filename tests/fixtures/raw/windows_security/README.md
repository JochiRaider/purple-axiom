# Windows Security raw fixtures (shape v1)

These fixtures represent the minimum raw input shape expected by the Windows Security mapping
profile:

Top-level:

- provider (string)
- channel (string)
- event_id (int)
- record_id (int)
- time_created (RFC3339 string, UTC)
- computer (string)
- event_data (object: string -> string)

Notes:

- Placeholder values such as "-" MUST be treated as absent.
- These fixtures are intended for deterministic mapping + golden output tests.
