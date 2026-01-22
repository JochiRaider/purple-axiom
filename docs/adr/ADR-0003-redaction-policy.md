---
title: 'ADR-0003: Redaction policy'
description: Defines a deterministic, contract-driven redaction policy, including fail-closed semantics, provenance requirements, and CI test vectors.
status: draft
category: adr
tags: [redaction, security, determinism, contracts]
related:
  - ../spec/090_security_safety.md
  - ../spec/025_data_contracts.md
  - ../spec/040_telemetry_pipeline.md
  - ../spec/045_storage_formats.md
  - ../spec/032_atomic_red_team_executor_integration.md
---

# ADR-0003: Redaction policy

## Context

Purple Axiom artifacts intentionally preserve high-fidelity telemetry and runner evidence for
reproducibility and defensible debugging. Multiple specs reference "redaction" (runner transcripts,
`command_summary`, raw retention), but the project does not define:

- what "redacted-safe" means
- which patterns MUST be removed or transformed
- deterministic truncation limits
- how to test the policy in CI

This blocks implementable decisions for:

- runner transcript storage (Tier 1 evidence)
- raw payload retention (including large script blocks)
- optional EVTX retention
- ground truth `command_summary` determinism

## Decision

Purple Axiom MUST define a deterministic redaction policy that is:

1. Configurable via a policy file (`policy_ref`) but with a normative minimum baseline.
1. Deterministic across implementations (stable ordering, stable truncation).
1. Fail-closed when redaction cannot be safely applied or post-checks detect residual sensitive
   material.
1. Tested with fixture vectors in CI (byte-for-byte).

Enablement is optional per run:

- Components MUST implement this policy format (required capability).
- Whether the policy is applied for a run MUST be controlled by config `security.redaction.enabled`.
  - When enabled, artifacts promoted into standard long-term locations MUST be redacted-safe.
  - When disabled, the run MUST be labeled unredacted and standard long-term locations MUST NOT
    silently receive unredacted evidence.
- Disabled behavior MUST be deterministic and config-controlled:
  - withhold-from-long-term (default), or
  - quarantine-unredacted (explicit opt-in)

This policy applies to:

- runner stdout/stderr transcripts (`runner/actions/<action_id>/stdout.txt`, `stderr.txt`)
- runner prerequisite transcripts (`runner/actions/<action_id>/prereqs_stdout.txt`,
  `prereqs_stderr.txt`)
- terminal session recordings (`runner/actions/<action_id>/terminal.cast`) (when enabled)
- `ground_truth.command_summary` field
- redacted input argument objects stored in artifacts
  (`runner/actions/<action_id>/resolved_inputs_redacted.json`)
- raw telemetry fields promoted into long-term storage (JSONL/Parquet)
- report rendering of any evidence-tier text
- structured execution records when string fields contain command-like content (for example,
  `attire.json` command fields)

For structured artifacts (JSON), redaction MUST be applied to string-typed fields that may contain
sensitive content. Object structure MUST be preserved; only string values are transformed.

Cross-reference: Runner artifact requirements are defined in the
[Atomic Red Team executor integration spec](../spec/032_atomic_red_team_executor_integration.md).

## Definitions

### Redacted-safe

A string (or structured object containing strings) is redacted-safe if, after applying the
configured redaction policy:

- it contains no matches for any `post_checks` patterns in the effective policy
- it respects all configured limits (max token length, max field length, max summary length)
- it is valid UTF-8 (for text artifacts)
- it contains no secrets or credential material per the normative minimum baseline below

### Fail-closed

If redaction fails for any reason (parse error, unsupported regex engine, invalid encoding,
post-check match), the pipeline MUST:

- withhold the unsafe content from long-term artifacts
- emit a deterministic placeholder instead
- record the failure as a run-level policy violation (run becomes `partial` unless configured
  stricter)

## Policy model: pa.redaction_policy.v1

### Effective policy resolution

Components MUST compute an effective policy for a run:

1. Load a policy file referenced by config (`policy_ref`) when provided.
1. Merge it over the normative baseline defaults (baseline applies when keys are absent).
1. Record the effective policy identity in run artifacts (see "Provenance requirements").

Merging rules (deterministic):

- Objects merge by key (policy file overrides baseline at leaf keys).
- Arrays are replaced as a whole (no deep merge).

### Regex engine constraint

All regex patterns in the policy MUST be RE2-compatible.

- Rationale: RE2 is available across common stacks and avoids catastrophic backtracking.
- If the implementation regex engine is not RE2, the implementation MUST still reject patterns that
  are not RE2-compatible.

### Policy structure

Policy files SHOULD follow this shape (JSON). YAML MAY be supported but MUST be normalized to the
JSON shape prior to hashing.

```json
{
  "policy_format": "pa.redaction_policy.v1",
  "policy_id": "pa-redaction",
  "policy_version": "1.1.0",
  "limits": {
    "max_token_chars": 128,
    "max_summary_chars": 512,
    "max_field_chars": 4096
  },
  "cli": {
    "secret_flags": [
      "--password",
      "--pass",
      "--token",
      "--api-key",
      "--apikey",
      "--client-secret",
      "--secret",
      "--key",
      "--credential"
    ],
    "secret_flag_prefixes": [
      "-password",
      "-pass",
      "-token",
      "-apikey",
      "-secret",
      "-key",
      "/password",
      "/pass",
      "/token"
    ],
    "secret_bare_flags": ["-p"],
    "flag_value_separators": ["=", ":"]
  },
  "uri": {
    "redact_userinfo": true
  },
  "pii": {
    "enabled": false,
    "redact_email": true,
    "redact_ipv4": false,
    "redact_ipv6": false,
    "redact_hostname": false,
    "custom_patterns": []
  },
  "structured": {
    "enabled": false,
    "recurse_json_strings": false,
    "target_paths": []
  },
  "regex_redactions": [
    {
      "rule_id": "aws_access_key_id",
      "pattern": "\\b(AKIA|ASIA)[0-9A-Z]{16}\\b",
      "replacement": "<REDACTED:AWS_ACCESS_KEY_ID>"
    },
    {
      "rule_id": "aws_secret_access_key",
      "pattern": "(?i)(aws[_-]?secret[_-]?access[_-]?key|secret[_-]?access[_-]?key)\\s*[:=]\\s*[A-Za-z0-9/+=]{40}",
      "replacement": "<REDACTED:AWS_SECRET_ACCESS_KEY>"
    },
    {
      "rule_id": "azure_sas_token",
      "pattern": "(?i)\\b(sv|sig|se|sp)=[^&\\s]{8,}(&(sv|sig|se|sp|sr|spr)=[^&\\s]+){2,}",
      "replacement": "<REDACTED:AZURE_SAS>"
    },
    {
      "rule_id": "base64_blob",
      "pattern": "\\b[A-Za-z0-9+/]{80,}={0,2}\\b",
      "replacement": "<REDACTED:BASE64_BLOB>"
    },
    {
      "rule_id": "bearer_token",
      "pattern": "(?i)\\bBearer\\s+[A-Za-z0-9._=-]{20,}",
      "replacement": "Bearer <REDACTED:TOKEN>"
    },
    {
      "rule_id": "connection_string_password",
      "pattern": "(?i)(connection\\s*string|server|data\\s*source|host|provider)\\s*=\\s*[^;]*;[^;]*(password|pwd|secret)\\s*=\\s*[^;]+",
      "replacement": "<REDACTED:CONNECTION_STRING>"
    },
    {
      "rule_id": "env_var_secret",
      "pattern": "(?i)\\b([A-Z_]*(?:SECRET|PASSWORD|TOKEN|API_KEY|APIKEY|CREDENTIAL|PRIVATE_KEY)[A-Z_]*)\\s*=\\s*[^\\s;]+",
      "replacement": "$1=<REDACTED>"
    },
    {
      "rule_id": "gcp_service_account_key",
      "pattern": "\"private_key\"\\s*:\\s*\"-----BEGIN [A-Z ]*PRIVATE KEY-----[^\"]+-----END [A-Z ]*PRIVATE KEY-----\"",
      "replacement": "\"private_key\": \"<REDACTED:GCP_PRIVATE_KEY>\""
    },
    {
      "rule_id": "hex_blob_32_labeled",
      "pattern": "(?i)(hash|checksum|md5|sha1|ntlm|lm)\\s*[:=]?\\s*[0-9a-f]{32}\\b",
      "replacement": "<REDACTED:HASH_32>"
    },
    {
      "rule_id": "hex_blob_64",
      "pattern": "\\b[0-9a-fA-F]{64}\\b",
      "replacement": "<REDACTED:HEX_BLOB_64>"
    },
    {
      "rule_id": "jdbc_url",
      "pattern": "(?i)jdbc:[a-z]+://[^:]+:[^@]+@[^\\s]+",
      "replacement": "<REDACTED:JDBC_URL>"
    },
    {
      "rule_id": "jwt",
      "pattern": "eyJ[A-Za-z0-9_-]{10,}\\.[A-Za-z0-9_-]{10,}\\.[A-Za-z0-9_-]{10,}",
      "replacement": "<REDACTED:JWT>"
    },
    {
      "rule_id": "kv_password",
      "pattern": "(?i)\\b(password|passwd|pwd|passphrase|secret|token|apikey|api_key|access[_-]?key|client[_-]?secret)\\b\\s*[:=]\\s*\\S+",
      "replacement": "$1=<REDACTED>"
    },
    {
      "rule_id": "mongodb_uri",
      "pattern": "(?i)mongodb(\\+srv)?://[^:]+:[^@]+@[^\\s]+",
      "replacement": "<REDACTED:MONGODB_URI>"
    },
    {
      "rule_id": "ntlm_hash",
      "pattern": "(?i)(lm|ntlm|nt)\\s*hash\\s*[:=]?\\s*[0-9a-f]{32}\\b",
      "replacement": "<REDACTED:NTLM_HASH>"
    },
    {
      "rule_id": "powershell_credential_param",
      "pattern": "(?i)-Credential\\s+(\\$[A-Za-z_][A-Za-z0-9_]*|\\([^)]+\\)|['\"][^'\"]+['\"])",
      "replacement": "-Credential <REDACTED:CREDENTIAL>"
    },
    {
      "rule_id": "powershell_password_param",
      "pattern": "(?i)-(Password|SecurePassword|AdminPassword)\\s+[^\\s|;]+",
      "replacement": "-$1 <REDACTED>"
    },
    {
      "rule_id": "powershell_secure_string",
      "pattern": "(?i)ConvertTo-SecureString\\s+-String\\s+['\"][^'\"]+['\"]",
      "replacement": "ConvertTo-SecureString -String '<REDACTED>'"
    },
    {
      "rule_id": "private_key_block",
      "pattern": "-----BEGIN ([A-Z ]+)?PRIVATE KEY-----[\\s\\S]*?-----END ([A-Z ]+)?PRIVATE KEY-----",
      "replacement": "<REDACTED:PRIVATE_KEY>"
    },
    {
      "rule_id": "windows_credential_target",
      "pattern": "(?i)(credential|cred)\\s*[:=]\\s*[^\\s;,]{8,}",
      "replacement": "<REDACTED:CREDENTIAL>"
    }
  ],
  "passthrough_patterns": [
    {
      "rule_id": "git_commit_sha",
      "pattern": "(?i)(commit|rev|sha)\\s*[:=]?\\s*[0-9a-f]{40}\\b",
      "note": "Git commit SHAs are safe"
    },
    {
      "rule_id": "sha256_checksum_labeled",
      "pattern": "(?i)(sha256|checksum|hash|digest)\\s*[:=]\\s*[0-9a-f]{64}\\b",
      "note": "Labeled checksums are safe"
    },
    {
      "rule_id": "uuid_v4",
      "pattern": "\\b[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\\b",
      "note": "UUIDv4 identifiers are safe"
    }
  ],
  "post_checks": [
    {
      "check_id": "no_aws_secret",
      "pattern": "(?i)aws[_-]?secret[_-]?access[_-]?key\\s*[:=]\\s*[A-Za-z0-9/+=]{40}",
      "severity": "error"
    },
    {
      "check_id": "no_jwt",
      "pattern": "eyJ[A-Za-z0-9_-]{10,}\\.[A-Za-z0-9_-]{10,}\\.[A-Za-z0-9_-]{10,}",
      "severity": "error"
    },
    {
      "check_id": "no_private_key",
      "pattern": "-----BEGIN ([A-Z ]+)?PRIVATE KEY-----",
      "severity": "error"
    }
  ]
}
```

### Limits scope clarification

The `limits` object in `pa.redaction_policy.v1` applies to redaction-time processing of text
artifacts. These limits are distinct from telemetry payload limits defined in the
[telemetry pipeline specification](../spec/040_telemetry_pipeline.md):

| Limit                 | Redaction Policy (this ADR) | Telemetry Pipeline          |
| --------------------- | --------------------------- | --------------------------- |
| Purpose               | Bound redacted output size  | Bound raw payload ingestion |
| `max_token_chars`     | 128 (default)               | N/A                         |
| `max_summary_chars`   | 512 (default)               | N/A                         |
| `max_field_chars`     | 4,096 (default)             | 262,144 (`max_field_chars`) |
| `max_event_xml_bytes` | N/A                         | 1,048,576                   |

When both limits apply (for example, a telemetry field that is later rendered in a report):

1. Telemetry limits are applied at ingestion time (raw Parquet writing).
1. Redaction limits are applied at artifact promotion time (long-term storage, report rendering).
1. If telemetry truncation already reduced a field below `limits.max_field_chars`, no additional
   redaction truncation is applied to that field.

The telemetry pipeline's `max_field_chars` is intentionally larger to preserve fidelity for
detection evaluation. The redaction policy's `max_field_chars` is smaller because it governs
human-readable and shareable artifacts where brevity matters.

## Normative processing rules

### Tokenization boundary

For any command-like artifact (command summaries, executor argv, transcripts when they contain
command echo):

- The runner SHOULD provide a tokenized representation (`executable` plus `argv[]`) when available.
- Redaction MUST operate on tokens when tokenization exists.
- When tokenization does not exist (free-form text), redaction MUST operate on the full string.

### Structured artifact redaction

For JSON-structured artifacts (for example, `attire.json`, `executor.json`, normalized OCSF events):

1. Redaction MUST traverse the object tree and apply to all string-typed leaf values.
1. Object structure (keys, nesting, arrays) MUST be preserved.
1. Non-string values (numbers, booleans, null) MUST NOT be modified.
1. String values that are valid JSON MUST be parsed and redacted recursively if
   `structured.recurse_json_strings: true` (default: false).

Target fields for structured redaction:

- Fields matching `*command*`, `*cmd*`, `*script*`, `*password*`, `*secret*`, `*token*`, `*key*`
  (case-insensitive) SHOULD be prioritized for redaction.
- Fields explicitly listed in `structured.target_paths[]` (JSONPath notation) MUST be redacted.

Example policy extension:

```json
{
  "structured": {
    "enabled": true,
    "recurse_json_strings": false,
    "target_paths": [
      "$.command",
      "$.command_line",
      "$.process.cmd_line",
      "$.actor.user.credential_uid"
    ]
  }
}
```

When `structured.enabled: false` (default), structured artifacts are serialized to string and
redacted as plain text. This may produce valid but semantically degraded JSON (for example, partial
replacement within a quoted string).

Recommendation: Enable structured redaction for artifacts that will be queried or joined downstream.

### CLI argument redaction

Given an argv token stream, apply in this order:

1. Flag-value pairs as separate tokens:

   - If token `t[i]` matches any `cli.secret_flags` or `cli.secret_flag_prefixes`, then if `t[i+1]`
     exists and is not another flag, replace `t[i+1]` with `<REDACTED>`.

1. Inline flag-value:

   - If a token matches `(--flag)(=|:)(value)` where `--flag` is secret, replace `value` with
     `<REDACTED>`.

1. Bare secret flags:

   - If token matches `cli.secret_bare_flags` (example: `-p`) and `t[i+1]` exists, redact `t[i+1]`.

The redaction MUST preserve token order and original token boundaries.

### URI userinfo redaction

If `uri.redact_userinfo: true`, redact userinfo credentials in URIs:

- Match: `scheme://user:pass@host/...`
- Replace only the password portion: `scheme://user:<REDACTED>@host/...`

### PII redaction (optional)

PII redaction is disabled by default (`pii.enabled: false`) because Purple Axiom operates in
isolated lab environments where network topology and test account identifiers are not sensitive.
Operators MAY enable PII redaction when artifacts will be shared outside the lab context.

When `pii.enabled: true`:

1. If `pii.redact_email: true`, apply:

   - Pattern: `[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}`
   - Replacement: `<REDACTED:EMAIL>`

1. If `pii.redact_ipv4: true`, apply:

   - Pattern:
     `\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b`
   - Replacement: `<REDACTED:IPV4>`
   - Exception: loopback addresses (`127.x.x.x`) and link-local (`169.254.x.x`) SHOULD be preserved
     unless `pii.redact_ipv4_strict: true`.

1. If `pii.redact_ipv6: true`, apply:

   - Pattern: `(?i)(?:[0-9a-f]{1,4}:){7}[0-9a-f]{1,4}|(?:[0-9a-f]{1,4}:){1,7}:|...` (full IPv6
     pattern per RFC 5952)
   - Replacement: `<REDACTED:IPV6>`
   - Exception: loopback (`::1`) SHOULD be preserved unless `pii.redact_ipv6_strict: true`.

1. If `pii.redact_hostname: true`, apply custom hostname patterns from `pii.custom_patterns[]`.

PII redaction MUST be applied after credential redaction and before truncation.

Rationale for default-off:

- Lab IP addresses and hostnames are required for telemetry correlation and debugging.
- Test user accounts (example: `atomic_test_user@lab.local`) are not real PII.
- Enabling PII redaction may interfere with detection rule evaluation that depends on network
  context fields.

When sharing artifacts externally, operators SHOULD enable PII redaction or apply a separate
sanitization pass.

### Passthrough patterns (allowlist)

Before applying `regex_redactions[]`, implementations MUST check each candidate match region against
`passthrough_patterns[]`. If a region matches any passthrough pattern, it MUST NOT be redacted by
subsequent rules.

Processing order:

1. Identify all candidate match regions from `regex_redactions[]` patterns.
1. For each candidate, check if the matched text also matches any `passthrough_patterns[]` entry.
1. If a passthrough matches, skip redaction for that region.
1. Apply redaction to remaining candidates.

Passthrough patterns reduce false positives for:

- UUIDs that look like hex blobs
- Labeled checksums that look like credential hashes
- Git commit SHAs
- Test fixture identifiers

Passthrough patterns MUST NOT be used to bypass security-critical redactions. Post-checks still
apply to final output regardless of passthrough matches.

### Regex redaction

Apply `regex_redactions[]` to any remaining string content.

- Ordering MUST be lexicographic by `rule_id` unless an explicit `order` field is added in a future
  version.
- Replacements MUST be exact string substitutions (no environment-dependent behavior).

### Rule severity (optional)

Each rule in `regex_redactions[]` MAY include a `severity` field:

```json
{
  "rule_id": "jwt",
  "pattern": "...",
  "replacement": "...",
  "severity": "redact"
}
```

Supported values:

- `redact` (default): Apply the replacement.
- `audit`: Log the match but do not apply replacement. Useful for testing new patterns before
  enabling redaction.
- `block`: Treat any match as a post-check failure (withhold content).

When `severity: audit`:

- The match MUST be logged with `rule_id`, match offset, and a truncated sample (first 32 chars of
  match).
- The original content MUST be preserved (no replacement applied).
- The run manifest SHOULD record `redaction.audit_matches_observed: true` if any audit-mode matches
  occurred.

Audit mode is intended for:

- Validating new patterns against production-like telemetry before enforcing redaction.
- Detecting potential secrets in historical data without modifying artifacts.

### Deterministic truncation

Truncation MUST be applied after redaction.

1. Token truncation:

   - If any token length exceeds `limits.max_token_chars`, it MUST be replaced with:

     - prefix: first 32 characters of the token (UTF-8 code points, not bytes), then
     - suffix: `<TRUNCATED len=<N>>` where `<N>` is the original character count

   - If (and only if) the token did not match any secret redaction rule, the suffix MAY also include
     a SHA-256 of the original token: `<TRUNCATED len=<N> sha256=<64hex>>`.

   - Hash basis for truncated tokens (normative):

     - The hash MUST be computed over the UTF-8 byte sequence of the original token value, before
       any redaction or normalization.
     - The hash MUST be lowercase hexadecimal (64 characters).
     - If the token contained a secret (matched any redaction rule), the hash MUST NOT be included
       to prevent hash-based secret recovery attacks.

   - This hash basis is consistent with `command_hash_basis: "command_material_v1_redacted"` used in
     ground truth extensions (see the [data contracts spec](../spec/025_data_contracts.md)).

1. Field truncation:

   - If a single field (free-form string) exceeds `limits.max_field_chars`, apply the same
     truncation rule (prefix plus `<TRUNCATED ...>`).

1. Command summary truncation:

   - If the final `command_summary` exceeds `limits.max_summary_chars`, truncate to that limit and
     append `<TRUNCATED_SUMMARY>`.

### Post-checks

After all redactions and truncations:

- Implementations MUST run every `post_checks[]` pattern against the output.
- If any `severity: error` check matches, the content MUST be withheld from long-term artifacts.

### Post-check design rationale

Post-checks are independent validation, not redundant with redaction rules. They serve as
defense-in-depth for cases where:

- A redaction pattern has an edge-case bug (regex backtracking, unexpected input encoding).
- Content bypasses redaction due to an implementation error.
- A new secret format appears that is not yet covered by `regex_redactions[]`.

If a redaction rule produces output that still matches a post-check pattern, this indicates:

- The redaction pattern is malformed or incomplete, OR
- The replacement text itself matches the post-check (implementation bug).

When a post-check matches after redaction:

1. The content MUST be withheld (fail-closed).
1. The failure record MUST include `reason_code: post_check_match_after_redaction`.
1. The failure record MUST include the `check_id` that matched and a truncated sample (first 64
   chars) of the matching region.

Implementations SHOULD log a warning when a post-check pattern exactly duplicates a redaction
pattern, as this may indicate unnecessary redundancy or a copy-paste error.

## Withholding behavior

When content is withheld (fail-closed), the pipeline MUST:

- write a deterministic placeholder file or value
  - Text placeholder: the single-line `pa.placeholder.v1` record (see
    [Placeholder artifacts](../spec/090_security_safety.md#placeholder-artifacts)).
- record a failure reason (machine-readable) in Tier 0 logs
- record that withholding occurred and which artifacts were affected
  - The run manifest SHOULD include this information

## Provenance requirements

Every run MUST record:

- `redaction_policy_id`
- `redaction_policy_version`
- `redaction_policy_sha256` (SHA-256 over canonical JSON of the effective policy)
- the effective limits used (`max_token_chars`, `max_summary_chars`, `max_field_chars`)

Recommended run-bundle snapshot path:

- `runs/<run_id>/security/redaction_policy_snapshot.json`

The snapshot MUST be identical to the effective policy used to process artifacts.

Canonical JSON (normative):

- The policy snapshot hash (`redaction_policy_sha256`) MUST be computed using the canonical JSON
  requirements defined in the [data contracts specification](../spec/025_data_contracts.md),
  specifically:
  - `canonical_json_bytes(policy)` = the exact UTF-8 byte sequence produced by JSON Canonicalization
    Scheme (RFC 8785, JCS).
  - `redaction_policy_sha256 = sha256_hex(canonical_json_bytes(effective_policy))`
- The effective policy object MUST satisfy RFC 8785 constraints (I-JSON subset) before
  canonicalization.

## Test vectors

CI MUST include fixture-based tests that validate:

- regex redactions
- CLI flag-value redactions
- URI userinfo redaction
- truncation determinism
- post-check fail-closed behavior
- passthrough pattern precedence
- structured artifact redaction
- asciinema cast redaction (v2 `.cast`; JSON value per line)

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

Credential patterns:

- private key PEM block removal
- JWT removal
- `Bearer <token>` removal
- AWS access key ID redaction
- AWS secret access key redaction (labeled key-value)
- Azure SAS token redaction
- NTLM hash redaction (labeled)
- Connection string password redaction

CLI argument handling:

- `--password <value>` redaction (tokenized argv)
- `--token=<value>` redaction (inline)
- `-p <value>` bare flag redaction
- PowerShell `-Credential` parameter redaction

URI and structured data:

- URI `user:pass@` sanitization
- MongoDB/JDBC connection URI redaction

Blob and truncation:

- long base64 blob redaction (80+ chars)
- long hex blob redaction (64 chars)
- truncation of a long non-secret token to deterministic placeholder with hash
- truncation of a long secret-containing token to deterministic placeholder without hash

Post-check validation:

- post-check match triggers withholding
- post-check match after partial redaction triggers withholding with correct reason code

Passthrough validation:

- UUID passthrough prevents hex blob redaction
- labeled checksum passthrough prevents hash redaction

Environment and context:

- environment variable secret pattern (`SECRET_KEY=value`)
- mixed content with multiple pattern types in single input

## Binary artifact handling

Binary artifacts (EVTX, PCAP, memory dumps, and similar) are not redacted in-place by this policy.
Binary handling is governed by storage policy and operator intent.

### Scope exclusion (normative)

The following artifact types are explicitly out of scope for text-based redaction:

- Windows EVTX files (`raw/evidence/*.evtx`)
- PCAP and flow captures (`raw/pcap/`, `raw/netflow/`)
- Binary blobs extracted to sidecar storage (`raw/evidence/blobs/`)
- Compiled executables and DLLs captured as evidence

### Binary retention requirements

When binary evidence is retained:

1. The run manifest MUST include `security.binary_evidence_retained: true`.
1. Binary artifacts MUST be stored only in explicitly designated evidence locations (not promoted to
   standard long-term artifact paths).
1. The run report MUST surface a warning indicating unredacted binary evidence exists.
1. Export and packaging tools MUST prompt for confirmation before including binary evidence in
   shareable bundles.

### Future extension point

A future policy version MAY add:

- `binary.evtx.retention: none | quarantine | evidence_tier`
- `binary.pcap.retention: none | quarantine | evidence_tier`
- `binary.sidecar.redact_on_extract: true | false`

These fields are reserved but not normative in `pa.redaction_policy.v1`.

Cross-reference:

- EVTX storage guidance: [Storage formats specification](../spec/045_storage_formats.md)
- Sidecar blob policy: [Telemetry pipeline specification](../spec/040_telemetry_pipeline.md)

## Consequences

- "Redacted-safe" becomes testable and deterministic.
- Runner transcripts can be stored as evidence-tier artifacts without leaking secrets by default.
- EVTX retention remains possible but requires explicit operator intent. Binary artifacts are not
  redacted in-place and MUST be governed separately in storage policy.
- Cloud credential patterns (AWS, Azure, GCP) and database connection strings are covered by
  default.
- PowerShell-specific patterns support Atomic Red Team execution scenarios.
- Passthrough patterns reduce false positives for legitimate hex values and checksums.
- Audit mode enables pattern validation before enforcement.

## References

- [Security and safety specification](../spec/090_security_safety.md)
- [Data contracts specification](../spec/025_data_contracts.md) (canonical JSON, action identity)
- [Telemetry pipeline specification](../spec/040_telemetry_pipeline.md) (payload limits, sidecar)
- [Storage formats specification](../spec/045_storage_formats.md) (EVTX retention, evidence tiers)
- [Atomic Red Team executor integration](../spec/032_atomic_red_team_executor_integration.md)
  (transcript capture, redaction scope)
- [Configuration reference](../spec/120_config_reference.md) (`security.redaction.*` keys)

## Changelog

| Date       | Change                                                                                                |
| ---------- | ----------------------------------------------------------------------------------------------------- |
| 2026-01-13 | v1.1.0: Add cloud credentials, PowerShell, connection strings, PII, passthrough, structured redaction |
| 2026-01-12 | Formatting update                                                                                     |
