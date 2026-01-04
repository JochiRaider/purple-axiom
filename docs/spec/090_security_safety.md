# Security and Safety

## Hard constraints
- Must run in isolated lab environments only.
- No persistence, lateral movement, or destructive payloads in MVP.
- All tests include cleanup, and cleanup status is recorded.

## Secrets and credentials
- Separate “range credentials” from developer credentials.
- No secrets stored in artifacts; redact or hash sensitive command parameters.

## Safe defaults
- Disabled-by-default high-risk tests.
- Explicit allowlist for enabled techniques/tests.

## Auditability
- Append-only run logs
- Run manifests include tool versions and configs used
