# event_id fixtures (v1)

This folder contains fixture vectors and representative raw inputs for verifying deterministic
`metadata.event_id` generation.

## Files

- `linux_identity_vectors.jsonl`
  - Golden vectors: `identity_basis` (v1) + expected `event_id` for Linux sources (auditd, journald, syslog).
- `linux_identity_collision.jsonl`
  - Intentional collision vectors (Tier 3) used to validate collision accounting and de-duplication behavior.
- `linux_auditd.audit.log`, `linux_journald.jsonl`, `linux_syslog.messages`
  - Representative raw inputs intended for extractor unit tests.

## Expected test behavior (normative)

1. For each line in `linux_identity_vectors.jsonl`:
   - Serialize `identity_basis` using RFC 8785 (JCS) canonical JSON.
   - Compute `sha256_hex(canonical_bytes)` and set `event_id = "pa:eid:v1:" + sha256_hex[:32]`.
   - Assert exact match to the vector's `event_id`.

2. For `linux_identity_collision.jsonl`:
   - Verify that the vectors produce identical `event_id` values.
   - Verify that the pipeline surfaces collisions deterministically (metric, warning, or explicit counter).