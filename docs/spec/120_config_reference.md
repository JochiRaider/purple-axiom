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

Notes:
- `lab.assets` remains the canonical, contract-level shape used throughout the pipeline.
- When `provider != manual`, Purple Axiom resolves provider inventory into `lab.assets` at run start and records the snapshot and hash in the manifest.

### `runner`
Controls scenario execution. The runner is responsible for producing ground truth events in `ground_truth.jsonl`.

Common keys:
- `type` (required): `caldera | atomic | custom`
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
  - `bookmarks` (optional): reset or resume policy (implementation-defined)
- `sources` (optional)
  - Additional non-OTel sources (example: `osquery`, `pcap`, `netflow`)
  - Each source should include:
    - `enabled`
    - `config_path` or equivalent
    - `output_path` under `raw/`

Notes:
- OTel Collector configuration shape is owned by upstream OTel. Purple Axiom only references the path and hashes it.

### `normalization`
Controls raw-to-OCSF transformation and the normalized store written under `normalized/`.

Common keys:
- `ocsf_version` (required): pinned OCSF version string (example: `1.3.0`)
- `mapping_profiles` (optional): list of profile identifiers (example: `windows`, `linux`, `dns`)
- `source_type_mapping` (optional): map of raw source identifiers to `metadata.source_type`
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

Notes:
- Criteria evaluation SHOULD operate on the normalized OCSF store (not raw events).
- When `fail_mode: fail_closed`, criteria evaluation errors cause the run to be marked `partial` or `failed`.

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
    - `raw_fallback_enabled` (default: true)
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
- `thresholds` (optional)
  - `min_technique_coverage` (optional)
  - `max_allowed_latency_seconds` (optional)
- `weights` (optional)
  - `coverage_weight`
  - `latency_weight`
  - `fidelity_weight`

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

### `operability` (optional)
Controls operational safety and runtime behavior (see also `110_operability.md`).

Common keys:
- `logging`
  - `level` (default: `info`): `debug | info | warn | error`
  - `json` (default: true)
- `run_limits`
  - `max_run_minutes` (optional)
  - `max_disk_gb` (optional)
- `health`
  - `emit_health_files` (default: true)

### `security` (optional)
Controls security boundaries and hardening (see also `090_security_safety.md`).

Common keys:
- `secrets`
  - `provider` (optional): `env | file | keychain | custom`
  - `refs` (optional): map of named secret refs
- `network`
  - `allow_outbound` (default: false)
  - `allowlist` (optional): list of CIDRs/domains when outbound is enabled
- `signing` (optional)
  - `enabled` (default: false)
  - `key_ref` (required when enabled): reference only

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