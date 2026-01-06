<!-- docs/adr/ADR-0003-redaction-policy.md -->
# ADR-0003: Redaction policy (deterministic, contract-driven)

## Status
Proposed

## Context
Purple Axiom artifacts intentionally preserve high-fidelity telemetry and runner evidence for reproducibility and defensible debugging. Multiple specs reference “redaction” (runner transcripts, `command_summary`, raw retention), but the project does not define:

- what “redacted-safe” means,
- which patterns must be removed or transformed,
- deterministic truncation limits, or
- how to test the policy in CI.

This blocks implementable decisions for:
- runner transcript storage (Tier 1 evidence),
- raw payload retention (including large script blocks),
- optional EVTX retention, and
- ground truth `command_summary` determinism.

## Decision
Define a **deterministic redaction policy** that is:

1. **Configurable** via a policy file (`policy_ref`) but with a **normative minimum baseline**.
2. **Deterministic** across implementations (stable ordering, stable truncation).
3. **Fail-closed** when redaction cannot be safely applied or post-checks detect residual sensitive material.
4. **Tested** with fixture vectors in CI (byte-for-byte).

Enablement (option, per run):
- Components MUST implement this policy format (required capability).
- Whether the policy is applied for a run MUST be controlled by config `security.redaction.enabled`.
  - When enabled, artifacts promoted into standard long-term locations MUST be redacted-safe.
  - When disabled, the run MUST be labeled unredacted and standard long-term locations MUST NOT silently receive unredacted evidence.
- Disabled behavior MUST be deterministic and config-controlled:
  - withhold-from-long-term (default), or
  - quarantine-unredacted (explicit opt-in).

The policy applies to:
- runner stdout/stderr transcripts,
- `ground_truth.command_summary`,
- redacted input argument objects stored in artifacts,
- raw telemetry fields promoted into long-term storage (JSONL/Parquet),
- report rendering of any evidence-tier text.

## Definitions

### Redacted-safe
A string (or structured object containing strings) is **redacted-safe** if, after applying the configured redaction policy:

- It contains **no matches** for any `post_checks` patterns in the effective policy, and
- It respects all configured limits (max token length, max field length, max summary length), and
- It is valid UTF-8 (for text artifacts), and
- It contains **no secrets** or credential material per the normative minimum baseline below.

### Fail-closed
If redaction fails for any reason (parse error, unsupported regex engine, invalid encoding, post-check match), the pipeline MUST:

- Withhold the unsafe content from long-term artifacts, and
- Emit a deterministic placeholder instead, and
- Record the failure as a run-level policy violation (run becomes `partial` unless configured stricter).

## Policy model (pa.redaction_policy.v1)

### Effective policy resolution
Components MUST compute an **effective policy** for a run:

1. Load a policy file referenced by config (`policy_ref`) when provided.
2. Merge it over the **normative baseline** defaults (baseline applies when keys are absent).
3. Record the effective policy identity in run artifacts (see “Provenance”).

Merging rules (deterministic):
- Objects merge by key (policy file overrides baseline at leaf keys).
- Arrays are replaced as a whole (no deep merge).

### Regex engine constraint (determinism)
All regex patterns in the policy MUST be **RE2-compatible**.
- Rationale: RE2 is available across common stacks and avoids catastrophic backtracking.
- If the implementation regex engine is not RE2, the implementation MUST still reject patterns that are not RE2-compatible.

### Policy structure (normative keys)
Policy files SHOULD follow this shape (JSON; YAML MAY be supported but must be normalized to the JSON shape prior to hashing):

```json
{
  "policy_format": "pa.redaction_policy.v1",
  "policy_id": "pa-redaction",
  "policy_version": "1.0.0",
  "limits": {
    "max_token_chars": 128,
    "max_summary_chars": 512,
    "max_field_chars": 4096
  },
  "cli": {
    "secret_flags": ["--password", "--pass", "--token", "--api-key", "--apikey", "--client-secret", "--secret", "--key"],
    "secret_flag_prefixes": ["-password", "-pass", "-token", "-apikey", "-secret", "-key", "/password", "/pass", "/token"],
    "secret_bare_flags": ["-p"],
    "flag_value_separators": ["=", ":"]
  },
  "uri": {
    "redact_userinfo": true
  },
  "regex_redactions": [
    { "rule_id": "private_key_block", "pattern": "-----BEGIN ([A-Z ]+)?PRIVATE KEY-----[\\s\\S]*?-----END ([A-Z ]+)?PRIVATE KEY-----", "replacement": "<REDACTED:PRIVATE_KEY>" },
    { "rule_id": "jwt", "pattern": "eyJ[A-Za-z0-9_-]{10,}\\.[A-Za-z0-9_-]{10,}\\.[A-Za-z0-9_-]{10,}", "replacement": "<REDACTED:JWT>" },
    { "rule_id": "bearer_token", "pattern": "(?i)\\bBearer\\s+[A-Za-z0-9._=-]{20,}", "replacement": "Bearer <REDACTED:TOKEN>" },
    { "rule_id": "aws_access_key_id", "pattern": "\\b(AKIA|ASIA)[0-9A-Z]{16}\\b", "replacement": "<REDACTED:AWS_ACCESS_KEY_ID>" },
    { "rule_id": "hex_blob", "pattern": "\\b[0-9a-fA-F]{64,}\\b", "replacement": "<REDACTED:HEX_BLOB>" },
    { "rule_id": "base64_blob", "pattern": "\\b[A-Za-z0-9+/]{80,}={0,2}\\b", "replacement": "<REDACTED:BASE64_BLOB>" },
    { "rule_id": "kv_password", "pattern": "(?i)\\b(password|passwd|pwd|passphrase|secret|token|apikey|api_key|access[_-]?key|client[_-]?secret)\\b\\s*[:=]\\s*\\S+", "replacement": "$1=<REDACTED>" }
  ],
  "post_checks": [
    { "check_id": "no_private_key", "pattern": "-----BEGIN ([A-Z ]+)?PRIVATE KEY-----", "severity": "error" },
    { "check_id": "no_jwt", "pattern": "eyJ[A-Za-z0-9_-]{10,}\\.[A-Za-z0-9_-]{10,}\\.[A-Za-z0-9_-]{10,}", "severity": "error" }
  ]
}
```

## Normative processing rules

### A) Tokenization boundary
For any “command-like” artifact (command summaries, executor argv, transcripts when they contain command echo):
- The runner SHOULD provide a tokenized representation (`executable` + `argv[]`) when available.
- Redaction MUST operate on tokens when tokenization exists.
- When tokenization does not exist (free-form text), redaction operates on the full string.

### B) CLI argument redaction (token-based)
Given an argv token stream, apply in this order:

1. **Flag-value pairs as separate tokens**
   - If token `t[i]` matches any `cli.secret_flags` or `cli.secret_flag_prefixes`, then:
     - If `t[i+1]` exists and is not another flag, replace `t[i+1]` with `<REDACTED>`.
2. **Inline flag-value**
   - If a token matches `(--flag)(=|:)(value)` where `--flag` is secret, replace `(value)` with `<REDACTED>`.
3. **Bare secret flags**
   - If token matches `cli.secret_bare_flags` (example: `-p`) and `t[i+1]` exists, redact `t[i+1]`.

The redaction MUST preserve token order and the original token boundaries.

### C) URI userinfo redaction
If `uri.redact_userinfo: true`, redact userinfo credentials in URIs:
- Match: `scheme://user:pass@host/...`
- Replace only the password portion: `scheme://user:<REDACTED>@host/...`

### D) Regex redaction (string scan)
Apply `regex_redactions[]` to any remaining string content:
- Ordering MUST be lexicographic by `rule_id` unless an explicit `order` field is added in a future version.
- Replacements MUST be exact string substitutions (no environment-dependent behavior).

### E) Deterministic truncation (limits)
Truncation applies after redaction.

1. **Token truncation**
   - If any token length exceeds `limits.max_token_chars`, it MUST be replaced with:
     - prefix: first 32 characters of the token, then
     - suffix: `<TRUNCATED len=<N>>`
   - If (and only if) the token did not match any secret redaction rule, the suffix MAY also include a SHA-256 of the original token:
     - `<TRUNCATED len=<N> sha256=<64hex>>`
2. **Field truncation**
   - If a single field (free-form string) exceeds `limits.max_field_chars`, apply the same truncation rule (prefix + `<TRUNCATED ...>`).
3. **Command summary truncation**
   - If the final `command_summary` exceeds `limits.max_summary_chars`, truncate to that limit and append `<TRUNCATED_SUMMARY>`.

### F) Post-checks (redacted-safe verification)
After all redactions/truncations:
- Run every `post_checks[]` pattern against the output.
- If any `severity: error` check matches, the content MUST be withheld from long-term artifacts.

## Withholding behavior (evidence handling)
When content is withheld (fail-closed):
- Write a deterministic placeholder file or value:
  - Text placeholder: `<WITHHELD_BY_REDACTION_POLICY policy_id=... policy_version=...>`
- Record a failure reason (machine-readable) in Tier 0 logs.
- The run manifest SHOULD record that withholding occurred and which artifacts were affected.

## Provenance requirements (pinning the policy)
Every run MUST record:
- `redaction_policy_id`
- `redaction_policy_version`
- `redaction_policy_sha256` (SHA-256 over canonical JSON of the **effective policy**)
- The effective limits used (`max_token_chars`, `max_summary_chars`, `max_field_chars`)

Recommended run-bundle snapshot path:
- `runs/<run_id>/security/redaction_policy_snapshot.json`

The snapshot MUST be identical to the effective policy used to process artifacts.

## Test vectors (required)
CI MUST include fixture-based tests that validate:
- regex redactions,
- CLI flag-value redactions,
- URI userinfo redaction,
- truncation determinism,
- post-check fail-closed behavior.

Recommended fixture layout:
- `tests/fixtures/redaction/v1/`
  - `cases.jsonl` (input + expected output + notes)
  - `effective_policy.json` (the policy used for the fixture)

Each case SHOULD be shaped as:
```json
{
  "case_id": "jwt_basic",
  "input": "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.aaaa.bbbb",
  "expected": "Authorization: Bearer <REDACTED:TOKEN>",
  "mode": "text"
}
```

Minimum required cases (baseline):
- private key PEM block removal
- JWT removal
- `Bearer <token>` removal
- `--password <value>` redaction (tokenized argv)
- `--token=<value>` redaction (inline)
- URI `user:pass@` sanitization
- long base64 blob redaction
- truncation of a long non-secret token to deterministic placeholder

## Consequences
- “Redacted-safe” becomes testable and deterministic.
- Runner transcripts can be stored as evidence-tier artifacts without leaking secrets by default.
- EVTX retention remains possible but requires explicit operator intent (binary artifacts are not redacted in-place and must be governed separately in storage policy).