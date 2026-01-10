<!-- docs/spec/120_config_reference.md -->
# Configuration Reference

This document defines the configuration surface for Purple Axiom. Configuration is intended to be:
- local-first
- deterministic (config inputs are hashed and recorded in `manifest.json`)
- safe (secrets are referenced, not embedded)

Primary config file name used in examples: `range.yaml`.

## Configuration files and precedence

Recommended sources (lowest to highest precedence):

1. Built-in defaults (code)
2. `range.yaml` (range/lab and pipeline defaults)
3. `scenario.yaml` (optional, scenario-specific overrides)
4. CLI flags (optional, small overrides only)
5. Environment variables (optional, for paths and secrets references)

Precedence rule: later sources override earlier sources at the leaf key level.

Secrets rule:
- Do not place credentials, tokens, or private keys directly in `range.yaml`.
- Use references (file paths, OS keychain identifiers, or environment variable names).

## Top-level keys

### `lab`
Defines the lab inventory and any range-scoped context required for orchestration and scoring.

Common keys:
- `provider` (optional, default: `manual`): `manual | ludus | terraform | other`
- `assets` (required)
  - `asset_id` (required, stable)
  - `os` (required): `windows | linux | macos | bsd | appliance | other`
  - `role` (optional): `endpoint | server | domain_controller | network | sensor | other`
  - `hostname` (optional)
  - `ip` (optional)
  - `tags` (optional): list of strings
- `inventory` (optional)
  - `path` (required when `provider != manual`): path to a provider-exported inventory artifact
  - `format` (optional): `ansible_yaml | ansible_ini | json` (default: `ansible_yaml`)
  - `refresh` (optional): `never | on_run_start` (default: `on_run_start`)
  - `snapshot_to_run_bundle` (optional, default: true): write resolved inventory snapshot under `logs/`
- `networks` (optional)
  - `cidrs`: list of CIDR ranges
  - `notes` (optional)

Inventory artifact formats (normative subset):
- `json`: Ansible inventory JSON static subset (RECOMMENDED). See `015_lab_providers.md` "Inventory artifact formats and adapter rules".
- `ansible_yaml`: static Ansible YAML inventory subset (no dynamic inventory plugins).
- `ansible_ini`: static Ansible INI inventory subset (no dynamic inventory scripts).

Determinism requirements:
- Implementations MUST convert the input inventory into `provider_inventory_canonical_v1` and MUST resolve `lab_inventory_snapshot.json` from that canonical model.
- Unsupported constructs MUST fail closed (do not attempt best-effort parsing that could change across versions).

Notes:
- `lab.assets` remains the canonical, contract-level shape used throughout the pipeline.
- When `provider != manual`, Purple Axiom resolves provider inventory into `lab.assets` at run start and records the snapshot and hash in the manifest.

### `runner`
Controls scenario execution. The runner is responsible for producing ground truth events in `ground_truth.jsonl`.

Common keys:
- `type` (required): `caldera | atomic | custom`
  - v0.1: `pcap` and `netflow` are placeholder contracts only (collection/ingestion is not required). If enabled without an implementation, telemetry MUST fail closed with `reason_code=source_not_implemented`.
- `caldera` (optional, when `type: caldera`)
  - `endpoint` (required)
  - `api_token_ref` (required): reference only (example: `env:CALDERA_TOKEN`)
  - `operation` (optional): profile or operation template identifier
  - `agent_selector` (optional): tags or asset ids
- `atomic` (optional, when `type: atomic`)
  - `atomic_root` (optional): path to Atomic Red Team definitions
  - `executor` (optional, default: `invoke_atomic_red_team`): `invoke_atomic_red_team | atomic_operator | other`
    - `invoke_atomic_red_team`: execute Atomics via the PowerShell Invoke-AtomicRedTeam module (canonical on Windows)
    - `atomic_operator`: execute Atomics via a cross-platform runner (Python), suitable for Linux/macOS targets
  - `timeout_seconds` (optional, default: 300): per-test execution timeout
  - `capture_transcripts` (optional, default: true): persist per-test stdout/stderr under `runner/` evidence
  - `capture_executor_metadata` (optional, default: true): persist per-test executor.json (exit code, duration, timestamps)
  - `cleanup` (optional)
    - `invoke` (optional, default: true): call the Atomic cleanup command when available
    - `verify` (optional, default: true): run cleanup verification checks and persist results under `runner/`
    - `verification_profile` (optional): named set of cleanup checks (implementation-defined)
  - `technique_allowlist` (optional): list of ATT&CK technique ids
  - `technique_denylist` (optional): list of ATT&CK technique ids
  - `executor_allowlist` (optional): list (example: `powershell`, `cmd`, `bash`)
- `custom` (optional, when `type: custom`)
  - `command` (required): local command or script path
  - `args` (optional): list
  - `env` (optional): key/value map (values should be refs when sensitive)

Determinism guidance:
- The runner should record its version and inputs in the manifest.
- Allowlists and denylists should be explicit and versioned.

### `telemetry`
Controls collection and staging of raw telemetry in `raw/`.

Common keys:
- `otel` (optional)
  - `enabled` (default: true)
  - `config_path` (required when enabled): path to OTel Collector config file
  - `channels` (optional): list of sources/channels to enable (implementation-defined)
    - v0.1 Windows baseline (normative): MUST include `application`, `security`, `system`, and `sysmon` (Microsoft-Windows-Sysmon/Operational).
  - `bookmarks` (optional): resume policy for sources that support cursoring
    - `mode` (default: `auto`): `auto | resume | reset`
      - `auto`: resume if a checkpoint exists, otherwise reset
      - `resume`: require checkpoint; if missing/corrupt, fall back to reset and mark checkpoint loss
      - `reset`: ignore checkpoints and start at run window start (plus skew tolerance)
    - `checkpoint_dir` (optional): defaults to `runs/<run_id>/logs/telemetry_checkpoints/`
    - `flush_interval_seconds` (default: 5)
- `sources` (optional)
  - Additional non-OTel sources (example: `osquery`, `pcap`, `netflow`)
  - v0.1: `pcap` and `netflow` are placeholder contracts only (collection/ingestion is not required). If enabled without an implementation, telemetry MUST fail closed with `reason_code=source_not_implemented`.
  - Each source should include:
    - `enabled`
    - `config_path` or equivalent
    - `output_path` under `raw/`

  - `osquery` (optional)
    - `enabled` (default: false)
    - `config_path` (optional): path to an osquery configuration file (deployment is runner/provider-defined). If present, the effective config SHOULD be snapshotted into the run bundle for provenance.
    - `results_log_path` (recommended): absolute path on the endpoint to the osquery results log (the NDJSON results file).
      - This SHOULD be explicit in lab configs to avoid OS/package default ambiguity.
    - `log_format` (default: `event_ndjson`): `event_ndjson | batch_json`
      - `event_ndjson` is the v0.1 canonical format (one JSON object per line).
      - `batch_json` is reserved; if used, ingestion requires multiline framing and MUST have explicit conformance tests.
    - `otel_ingest` (optional)
      - `enabled` (default: true): when true, the operator MUST configure the OTel Collector to tail `results_log_path` (typically via the `filelog` receiver) and tag records such that `metadata.source_type = "osquery"` can be set during normalization.
      - `receiver_id` (optional): logical receiver id in the OTel config (example: `filelog/osquery`) for traceability.
    - `output_path` (required): destination directory under the run bundle `raw/` where osquery raw logs are staged (example: `raw/osquery/`)

See `042_osquery_integration.md` for format requirements, OTel receiver examples, normalization routing, and fixtures.

Notes:
- OTel Collector configuration shape is owned by upstream OTel. Purple Axiom only references the path and hashes it.

Additional Purple Axiom staging policy (applies during raw Parquet writing and optional sidecar extraction):
- `payload_limits` (optional)
  - `max_event_xml_bytes` (optional, default: 1048576)
  - `max_field_chars` (optional, default: 262144)
  - `max_binary_bytes` (optional, default: 262144)
  - `sidecar` (optional)
    - `enabled` (optional, default: true)
    - `dir` (optional, default: `raw/evidence/blobs/wineventlog/`)

### `normalization`
Controls raw-to-OCSF transformation and the normalized store written under `normalized/`.

Common keys:
- `ocsf_version` (required): pinned OCSF version string (example: `1.3.0`)
- `mapping_profiles` (optional): list of profile identifiers (example: `windows`, `linux`, `dns`)
- `source_type_mapping` (optional): map of raw source identifiers to `metadata.source_type`
- `dedupe` (optional)
  - `enabled` (default: true)
  - `scope` (default: `per_run`): `per_run` (v0.1 only)
  - `index_dir` (optional): defaults to `runs/<run_id>/logs/dedupe_index/`
  - `conflict_policy` (default: `warn`): `warn | fail_closed`

Notes (v0.1):
- Purple Axiom v0.1 pins `ocsf_version = "1.3.0"`. OCSF schema update/migration policy is defined in `050_normalization_ocsf.md`.
- `strict_mode` (default: true)
  - When true, normalization failures produce a run-level failure unless explicitly allowlisted.
- `raw_preservation` (optional)
  - `enabled` (default: true)
  - `policy`: `none | minimal | full` (implementation-defined)
- `output` (optional)
  - `format`: `jsonl | parquet` (recommended: `parquet` for long-term)
  - `parquet` (optional)
    - `compression`: `zstd | snappy | none` (default: `zstd`)
    - `row_group_size` (optional)
    - `partitioning` (optional): list (example: `["class_uid"]`)

### `validation`
Controls criteria-pack evaluation (expected telemetry) and cleanup verification reporting.

Common keys:
- `enabled` (default: true)
- `criteria_pack` (optional)
  - `pack_id` (required when enabled): identifier for the criteria pack
  - `pack_version` (optional, recommended): pinned version for reproducibility
    - Determinism requirement:
      - For CI/regression runs, `pack_version` SHOULD be set explicitly.
    - If `pack_version` is omitted:
      - The implementation MUST resolve a version deterministically using SemVer ordering:
        1. Enumerate available `<pack_id>/<pack_version>/` directories across `paths`.
        2. Parse candidate versions as SemVer.
        3. Select the highest SemVer version.
        4. If no candidates parse as SemVer, fail closed.
      - The resolved `pack_version` MUST be recorded in run provenance (manifest + report).
  - `paths` (optional): one or more search paths (directories) that contain criteria packs
  - `entry_selectors` (optional): constraints to pick the most specific entry when multiple match
    - `os`
    - `roles`
    - `executor`
- `evaluation` (optional)
  - `time_window_before_seconds` (optional, default: 5)
  - `time_window_after_seconds` (optional, default: 120)
  - `max_sample_event_ids` (optional, default: 20)
  - `fail_mode` (optional, default: `warn_and_skip`): `fail_closed | warn_and_skip`
    - `fail_closed`: criteria-stage errors that prevent producing a complete `criteria/results.jsonl` MUST cause the criteria stage outcome to be `failed`.
    - `warn_and_skip`: evaluator MUST still emit `criteria/results.jsonl` rows for all selected actions; actions that cannot be evaluated MUST be marked `status: "skipped"` with a stable `reason_code`.

Notes:
- Criteria evaluation SHOULD operate on the normalized OCSF store (not raw events).
- When `fail_mode: fail_closed`, criteria evaluation errors MUST produce a criteria stage outcome of `failed`, and `manifest.status` MUST be derived per `025_data_contracts.md` (“Status derivation”).

### `detection`
Controls evaluation over normalized OCSF events and outputs to `detections/`.

Common keys:
- `mode` (default: `batch`): `batch | streaming`
- `sigma` (optional)
  - `enabled` (default: true)
  - `rule_paths` (required when enabled): list of directories/files containing Sigma YAML
  - `rule_set_version` (optional): pinned identifier for reporting and trending
  - `bridge` (optional, recommended)
    - `mapping_pack` (required): identifier for the Sigma-to-OCSF mapping pack (router + field aliases)
    - `mapping_pack_version` (optional, recommended): pin for reproducibility
    - `backend` (default: `duckdb_sql`): `duckdb_sql | tenzir | other`
    - `fail_mode` (default: `fail_closed`): `fail_closed | warn_and_skip`
      - `fail_closed`: bridge/backend errors that prevent evaluating enabled rules (routing, compilation, backend execution) MUST cause the detection stage outcome to be `failed`.
      - `warn_and_skip`: such errors MUST be recorded; affected rules MUST be marked non-executable with a stable `reason_code`. The detection stage outcome SHOULD be `success` unless the stage cannot produce outputs at all.
     - `raw_fallback_enabled` (default: true)
      - Controls whether rules may reference `raw.*` per `065_sigma_to_ocsf_bridge.md` (“Fallback policy (`raw.*`)”).
      - When `false`, any rule requiring `raw.*` MUST be marked non-executable with `reason_code: "raw_fallback_disabled"`.
      - When `true`, any fallback use MUST be accounted for via `extensions.bridge.fallback_used=true` in detection outputs.
    - `compile_cache_dir` (optional): path for cached compiled plans keyed by (rule hash, mapping pack version, backend version)
  - `limits` (optional)
    - `max_rules` (optional)
    - `max_compile_errors` (optional)
- `join` (optional)
  - `clock_skew_tolerance_seconds` (default: 30)

Notes:
- The Sigma-to-OCSF Bridge is specified in `065_sigma_to_ocsf_bridge.md`. This config selects the mapping pack and backend behavior.
- `fail_closed` is the recommended default so rules that cannot be routed or mapped are reported as non-executable rather than silently producing “no matches”.

### `scoring`
Controls the scoring model and classification taxonomy written under `scoring/`.

Common keys:
- `enabled` (default: true)
- `gap_taxonomy` (default)
  - `missing_telemetry`
  - `criteria_unavailable`
  - `criteria_misconfigured`
  - `normalization_gap`
  - `bridge_gap`
  - `rule_logic_gap`
  - `cleanup_verification_failed`
- `thresholds` (optional): allow CI to fail if below expected quality.
  - v0.1 defaults (normative) if omitted: `min_technique_coverage=0.75`, `max_allowed_latency_seconds=300`, `min_tier1_field_coverage=0.80`, `max_missing_telemetry_rate=0.10`, `max_normalization_gap_rate=0.05`, `max_bridge_gap_rate=0.15`.
  - Keys:
    - `min_technique_coverage`: percent of executed techniques that must have ≥1 detection.
    - `max_allowed_latency_seconds`: maximum time delta between a ground truth action and first detection hit.
    - `min_tier1_field_coverage`: minimum Tier 1 field coverage ratio (0.0-1.0).
    - `max_missing_telemetry_rate`: maximum fraction of executed techniques classified as `missing_telemetry` (0.0-1.0).
    - `max_normalization_gap_rate`: maximum fraction of executed techniques classified as `normalization_gap` (0.0-1.0).
    - `max_bridge_gap_rate`: maximum fraction of executed techniques classified as `bridge_gap` (0.0-1.0).
- `weights` (optional): allow scores to emphasize certain categories.
  - v0.1 defaults (normative) if omitted: `coverage_weight=0.60`, `latency_weight=0.25`, `fidelity_weight=0.15`.
  - Keys:
    - `coverage_weight`: factor for technique coverage.
    - `latency_weight`: factor for time-to-detection.
    - `fidelity_weight`: factor for match quality (exact vs partial vs weak).

### `reporting`
Controls report generation and output locations.

Common keys:
- `output_dir` (required): base directory for run bundles (example: `runs/`)
- `emit_html` (default: true)
- `emit_json` (default: true)
- `include_debug_sections` (default: false)
- `redaction` (optional)
  - `enabled` (default: true)
  - `policy_ref` (optional): reference to a redaction policy file
  - Notes:
    - `reporting.redaction` controls report rendering. It MUST NOT be interpreted as the pipeline redaction enablement switch.
    - Pipeline redaction enablement is controlled by `security.redaction.enabled`.

### `operability` (optional)
Controls operational safety and runtime behavior (see also `110_operability.md`).

Common keys:
- `logging`
  - `level` (default: `info`): `debug | info | warn | error`
  - `json` (default: true)
- `run_limits`
  - `max_run_minutes` (optional): hard upper bound for runtime.
  - `max_disk_gb` (optional): maximum disk usage for run artifacts.
  - `disk_limit_behavior` (optional): `partial` | `hard_fail` (default: `partial`).
  - `max_memory_mb` (optional): maximum resident memory usage.
- `health`
  - `emit_health_files` (default: true)
    - When `true`, the pipeline MUST write `runs/<run_id>/logs/health.json` (minimum schema in `110_operability.md`, “Health files (normative, v0.1)”).
    - When `false`, the pipeline MUST still compute `manifest.status` per `025_data_contracts.md` (“Status derivation”).

### `security` (optional)
Controls security boundaries and hardening (see also `090_security_safety.md`).

Common keys:
- `redaction` (optional)
  - `enabled` (default: true)
    - When `true`, the pipeline applies the effective redaction policy and promotes only redacted-safe artifacts into standard long-term locations.
    - When `false`, the run is explicitly unredacted and the pipeline MUST withhold sensitive evidence from standard long-term locations unless quarantined.
  - `policy_ref` (optional): reference to a redaction policy file (format defined in `docs/adr/ADR-0003-redaction-policy.md`)
  - `limits` (optional)
    - `max_token_chars` (optional)
    - `max_summary_chars` (optional)
    - `max_field_chars` (optional)
  - `disabled_behavior` (optional, default: `withhold_from_long_term`): `withhold_from_long_term | quarantine_unredacted`
    - `withhold_from_long_term`: write deterministic placeholders in standard artifact locations
    - `quarantine_unredacted`: write unredacted evidence to `runs/<run_id>/unredacted/`.
    - `runs/<run_id>/unredacted/` MUST be excluded from default exports/packaging.
  - `allow_unredacted_evidence_storage` (optional, default: false)
    - When `true` and `disabled_behavior: quarantine_unredacted`, the pipeline MAY persist unredacted evidence to the quarantine path.
  - `unredacted_dir` (optional, default: `unredacted/`): relative directory under the run bundle root for quarantined evidence
- `secrets`
  - `provider` (optional): `env | file | keychain | custom`
  - `refs` (optional): map of named secret refs
- `network`
  - `allow_outbound` (default: false)
  - `allowlist` (optional): list of CIDRs/domains when outbound is enabled
- `signing` (optional)
  - `enabled` (default: false)
  - `key_ref` (required when enabled): reference to signing private key material (never inline)
    - v0.1 posture:
      - Disabled by default for MVP.
      - Strongly RECOMMENDED for compliance/audit/export workflows.
    - When `enabled: true`, the pipeline MUST emit bundle integrity artifacts as specified in `025_data_contracts.md` ("Run bundle signing").
    - If signing is enabled but cannot be completed (missing key material, invalid key format, signing I/O error), the pipeline MUST fail closed.
  - `key_ref` (required when enabled): reference to signing private key material (never inline)
  - `algorithm` (optional, default: `ed25519`)
    - v0.1 supports `ed25519` only.
  - `key_format` (optional, default: `ed25519_seed_base64`)
    - `ed25519_seed_base64`: secret value is base64 for a 32-byte Ed25519 seed.
    - Implementations MAY support additional formats (example: OpenSSH private key) but MUST still emit Ed25519 signatures.
  - `trusted_key_ids` (optional): list of allowed `key_id` values for verification/export gating
    - `key_id` is defined as `sha256(public_key_bytes)` encoded as 64 lowercase hex characters.
    
## Example `range.yaml`

```yaml
lab:
  provider: ludus
  inventory:
    path: ".ludus/inventory.yml"
    format: ansible_yaml
    refresh: on_run_start
    snapshot_to_run_bundle: true
  assets:  # optional overlays (stable asset_id + tags); provider supplies hostname/ip  
    - asset_id: win11-test-01
      os: windows
      role: endpoint
      hostname: win11-test-01.local
      tags: ["win11", "test"]
    - asset_id: ubuntu-test-01
      os: linux
      role: server
      hostname: ubuntu-test-01.local
      tags: ["linux", "test"]
  networks:
    cidrs: ["10.10.0.0/16"]

runner:
  type: atomic
  atomic:
    executor: invoke_atomic_red_team
    timeout_seconds: 300
    capture_transcripts: true
    cleanup:
      invoke: true
      verify: true
      verification_profile: "default"
    technique_allowlist: ["T1059.001"]
    executor_allowlist: ["powershell", "cmd"]

telemetry:
  otel:
    enabled: true
    config_path: configs/otel-collector.yaml
    channels: ["windows_security", "sysmon", "dns"]
  sources:
    osquery:
      enabled: false
      config_path: configs/osquery.conf
      # Absolute path on the endpoint. Keep explicit to avoid OS/package default ambiguity.
      results_log_path: "/var/log/osquery/osqueryd.results.log"
      log_format: event_ndjson
      otel_ingest:
        enabled: true
        receiver_id: filelog/osquery      
      output_path: raw/osquery/

normalization:
  ocsf_version: "1.3.0"
  mapping_profiles: ["windows", "dns"]
  strict_mode: true
  raw_preservation:
    enabled: true
    policy: minimal
  output:
    format: parquet
    parquet:
      compression: zstd
      partitioning: ["class_uid"]

validation:
  enabled: true
  criteria_pack:
    pack_id: "default"
    pack_version: "0.1.0"
    paths: ["criteria/packs"]
  evaluation:
    time_window_before_seconds: 5
    time_window_after_seconds: 120
    max_sample_event_ids: 20
    fail_mode: warn_and_skip

detection:
  mode: batch
  sigma:
    enabled: true
    rule_paths: ["rules/sigma"]
    rule_set_version: "sigma-hq-snapshot-2026-01"
    bridge:
      mapping_pack: "sigmahq-ocsf"
      mapping_pack_version: "0.1.0"
      backend: duckdb_sql
      fail_mode: fail_closed
      raw_fallback_enabled: true
      compile_cache_dir: ".cache/sigma-compiled"
    limits:
      max_rules: 5000

scoring:
  enabled: true
  gap_taxonomy:
    - missing_telemetry
    - criteria_unavailable
    - criteria_misconfigured    
    - normalization_gap
    - bridge_gap
    - rule_logic_gap
    - cleanup_verification_failed
  thresholds:
    min_technique_coverage: 0.75

reporting:
  output_dir: "runs/"
  emit_html: true
  emit_json: true
  include_debug_sections: false

operability:
  logging:
    level: info
    json: true
  run_limits:
    max_run_minutes: 60

security:
  network:
    allow_outbound: false
  signing:
    enabled: false
```

## OTel Collector config reference

Purple Axiom does not redefine the OpenTelemetry Collector configuration schema. The collector config is referenced by path (`telemetry.otel.config_path`) and is hashed into the run manifest for reproducibility.

Recommended practice:

* Version the collector config file in-repo.
* Treat collector config changes as pipeline changes that can affect determinism and coverage.

## Validation expectations

Minimum validation (MVP):

* YAML parses successfully.
* Required keys are present for enabled components (example: `telemetry.otel.config_path` when `telemetry.otel.enabled: true`).
* Config inputs are hashed and recorded in `manifest.json`.

Recommended next step:

* Introduce a JSON Schema for `range.yaml` and enforce it in CI.