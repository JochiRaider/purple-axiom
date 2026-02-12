---
title: Configuration reference
description: Defines the configuration surface, defaults, and validation expectations for runs.
status: draft
---

# Configuration reference

This document defines the configuration surface for Purple Axiom. Configuration is intended to be:

- local-first
- deterministic (config inputs are hashed and recorded in `manifest.json`)
- safe (secrets are referenced, not embedded)

Primary config file name used in examples: `inputs/range.yaml`.

## Configuration files and precedence

Recommended sources (lowest to highest precedence):

1. Built-in defaults (code)
1. `inputs/range.yaml` (range/lab and pipeline defaults)
1. `inputs/scenario.yaml` (optional, scenario-specific overrides)
1. CLI flags (optional, small overrides only)
1. Environment variables (optional, for paths and secrets references)

Precedence rule: later sources override earlier sources at the leaf key level.

Secrets rule:

- Do not place credentials, tokens, or private keys directly in `inputs/range.yaml`.
- Use references (file paths, OS keychain identifiers, or environment variable names).

## Workspace root and filesystem paths

Purple Axiom is workspace-rooted: all durable artifacts written by the toolchain live under a single
workspace root directory. See: [architecture](020_architecture.md) → "Workspace layout (v0.1+
normative)".

Path resolution rules (normative):

- Keys explicitly described as "relative directory under the run bundle root" are resolved relative
  to the active run bundle root (`runs/<run_id>/`).
- All other relative filesystem paths in configuration MUST be resolved relative to
  `<workspace_root>/`.
- v0.1 default `<workspace_root>`: the current working directory.

Workspace boundary rules (normative):

- Tooling MUST NOT write persistent artifacts outside `<workspace_root>/` except for OS-managed
  ephemeral temp files that are not required for correctness/resumability.
- Cross-run caches MUST live under `<workspace_root>/cache/` (reserved workspace directory).
- Derived exports produced outside the run bundle MUST live under `<workspace_root>/exports/`
  (reserved workspace directory).

## Top-level keys

### Lab (lab)

Defines the lab inventory and any range-scoped context required for orchestration and scoring.

Common keys:

- `provider` (optional, default: `manual`): `manual | ludus | terraform | vagrant | other`
- `assets` (required)
  - `asset_id` (required, stable)
  - `os` (required): `windows | linux | macos | bsd | appliance | other`
  - `role` (optional): `endpoint | server | domain_controller | network | sensor | other`
  - `hostname` (optional)
  - `ip` (optional)
  - `vars` (object, optional): allowlisted, non-secret connection hints. See the
    [lab providers specification](015_lab_providers.md) "Canonical intermediate model".
  - `tags` (optional): list of strings
- `inventory` (optional)
  - `path` (required when `provider != manual`): path to a provider-exported inventory artifact
  - `format` (optional): `ansible_yaml | ansible_ini | json` (default: `ansible_yaml`)
  - `refresh` (optional): `never | on_run_start` (default: `on_run_start`)
  - `snapshot_to_run_bundle` (optional, default: true): write resolved inventory snapshot under
    `logs/`
- `networks` (optional)
  - `cidrs`: list of CIDR ranges
  - `notes` (optional)

Inventory artifact formats (normative subset):

- `json`: Ansible inventory JSON static subset (RECOMMENDED). See the
  [lab providers specification](015_lab_providers.md) "Inventory artifact formats and adapter
  rules".
- `ansible_yaml`: static Ansible YAML inventory subset (no dynamic inventory plugins).
- `ansible_ini`: static Ansible INI inventory subset (no dynamic inventory scripts).

Determinism requirements:

- Implementations MUST convert the input inventory into `provider_inventory_canonical_v1` and MUST
  resolve `lab_inventory_snapshot.json` from that canonical model.
- Unsupported constructs MUST fail closed (do not attempt best-effort parsing that could change
  across versions).

Notes:

- `lab.assets` remains the canonical, contract-level shape used throughout the pipeline.
- When `provider != manual`, Purple Axiom resolves provider inventory into `lab.assets` at run start
  and records the snapshot and hash in the manifest.

### Runner (runner)

Controls scenario execution. The runner is responsible for producing ground truth events in
`ground_truth.jsonl`.

Common keys:

- `type` (required): `caldera | atomic | custom`

  - `type` selects the **execution adapter** backend (see `033_execution_adapters.md`).
    - v0.1: only `atomic` is required to be implemented; `caldera` and `custom` are reserved and
      MUST fail closed if selected.
    - The resolved execution adapter binding MUST be recorded in
      `manifest.extensions.adapter_provenance.entries[]` with `port_id="runner-execution-adapter"`
      and `adapter_id=<type>`.

- `identity` (optional)

  - `emit_principal_context` (default: `true`)
    - When `true`, the runner MUST emit `runner/principal_context.json` (schema-backed) exactly once
      per run.
      - `principal_context.json` MUST include `principals[]` and `action_principal_map[]`.
      - `action_principal_map[]` MUST include a mapping for every action recorded in
        `ground_truth.jsonl` (including actions mapped to `kind=unknown` with explicit
        `assertion_source`).
    - When `false`, the runner MUST NOT emit the artifact and MUST NOT populate
      `extensions.principal_id` in ground truth.
  - `probe_enabled` (default: `false`)
    - When `false`, the runner MUST NOT execute “identity probes” beyond what is already available
      without additional collection steps.
    - When `true`, the runner MAY probe to improve principal attribution, but MUST still obey
      redaction/disclosure constraints (no raw usernames/SIDs/creds).
      - Probes MUST be read-only and MUST NOT mutate target state.
      - Probes MUST be local-only by default (no network, no domain queries) unless explicitly
        enabled by a future config gate.
      - Implementations MUST bound probes (timeouts/attempt limits) and MUST record probe-attempt
        status deterministically in runner evidence.
      - Probes MUST NOT capture or store secrets (credentials, tokens, private keys, session
        material).
  - `probe_detail` (default: `summary`; enum: `summary | none`)
    - `summary`: populate the `principal_context.json` with `principals[]` +
      `action_principal_map[]` and MAY include `redacted_fingerprint` (hash-only / safe).
    - `none`: emit only the minimal typed mapping without fingerprints (still stable IDs and kinds).
      The runner MUST still record probe-attempt status deterministically in runner evidence.
  - `cache_policy` (default: `per_run_only`; enum: `disabled | per_run_only | cross_run_allowed`)
    - Mirrors the cache provenance policy enum already defined for `cache_provenance.json`.

- `environment_config` (optional)

  - `mode` (optional, default: `off`): `off | check_only | apply`

    - `off`: do not perform run-scoped environment configuration.
    - `check_only`: perform preflight checks only. MUST NOT mutate target state.
    - `apply`: MAY mutate target state to converge the configured baseline. This is a destructive
      capability and MUST be explicitly enabled.

  - `fail_mode` (optional, default: `fail_closed`): `fail_closed | warn_and_skip`

    - `fail_closed`: any failed check blocks scenario execution (preferred for v0.1).
    - `warn_and_skip`: record the failure deterministically but continue execution (use only for
      non-critical checks).

  - `transport` (optional, default: `ssh`): `ssh | winrm | other`

    - Transport used for remote environment configuration and checks.

  - `targets` (optional): allowlist of `lab.assets[].asset_id` eligible for environment
    configuration and checks.

    - When `mode=apply`, this list MUST be present and MUST be non-empty; otherwise config
      validation MUST fail closed with `reason_code=config_schema_invalid`.

  - `dsc_v3` (optional)

    - `enabled` (optional, default: `false`)
    - `config_path` (required when `enabled=true`): path to a DSC v3 configuration document (JSON or
      YAML).
    - `config_sha256` (required when `enabled=true`): SHA-256 of the canonical config bytes (UTF-8,
      strip UTF-8 BOM if present, normalize CRLF to LF).
    - `output_format` (optional, default: `json`): `json | pretty-json`
    - `what_if_before_apply` (optional, default: `true`)
      - When `true` and `mode=apply`, the runner MUST emit a WhatIf plan before applying.
    - `resource_type_allowlist` (optional)
      - When present and non-empty, the runner MUST reject any configuration document that contains
        resources outside the allowlist.

  - `noise_profile` (optional): configuration for deterministic benign background activity
    ("baseline noise").

    - `enabled` (optional, default: `false`): when `true`, the runner MUST execute the selected
      noise profile as part of environment configuration/background activity.
      - When `enabled=true`, `environment_config.mode` MUST equal `apply` (noise generation is
        state-mutating).
    - Terminology note (normative): this noise profile is a *workload/noise generator* input. It
      MUST NOT be conflated with the telemetry baseline profile gate (`telemetry.baseline_profile`).
    - `profile_id` (required when `enabled=true`): stable identifier for the noise profile.
    - `profile_version` (required when `enabled=true`): profile version string (SemVer recommended).
    - `profile_sha256` (required when `enabled=true`): SHA-256 of the canonical noise profile bytes
      (64 lowercase hex characters). In v0.1, the canonical bytes are exactly the bytes of the
      snapshotted profile file `runs/<run_id>/inputs/environment_noise_profile.json`, which MUST be
      emitted as canonical JSON bytes (`canonical_json_bytes(...)` as defined in
      `025_data_contracts.md`).
    - `profile_path` (optional): human-readable path to the profile definition source. Not used as
      an identity input; `profile_sha256` is authoritative.
    - When `enabled=true`, the implementation MUST snapshot the resolved noise profile bytes into
      `runs/<run_id>/inputs/environment_noise_profile.json` and MUST use the snapshotted bytes for
      hashing and execution.
    - `seed` (optional, default: `0`): deterministic seed for any stochastic elements. MUST be
      pinned and recorded in provenance (see `manifest.extensions.runner.environment_noise_profile`
      in `025_data_contracts.md`).
    - `targets` (optional): allowlist of `lab.assets[].asset_id` eligible for noise generation. When
      omitted, defaults to `environment_config.targets`. When present, MUST be a subset of
      `environment_config.targets`.

  Notes:

  - When `environment_config.mode != off`, the orchestrator records the substage outcome as
    `runner.environment_config` and emits deterministic evidence under `runs/<run_id>/logs/**` (see
    [architecture](020_architecture.md)).

  - Environment configuration is the recommended v0.1 integration point for generating benign
    background activity (“noise”) to improve dataset realism.

    - Examples:
      - Active Directory / domain controllers: AD-Lab-Generator (domain population) and ADTest.exe
        (directory/authentication workload).
      - Windows + Linux servers: scheduled tasks / cron jobs that emulate routine service behavior
        (periodic health checks, log rotation, internal HTTP requests, file reads/writes).
      - Cross-platform user activity: GHOSTS clients/agents pointing at an operator-managed GHOSTS
        server. In v0.1 the server SHOULD be treated as a supporting service (packaging-only) rather
        than bundled into the orchestrator image.

  - Noise tooling configuration MUST remain deterministic and reviewable.

    - All configuration inputs MUST be pinned by content hash (for example `dsc_v3.config_sha256`).
    - Noise tooling binaries/scripts SHOULD be treated as immutable inputs; runtime downloads MUST
      NOT be required for v0.1 correctness (aligns with dependency immutability and egress-deny
      defaults).
    - If randomized schedules are used, the effective seed MUST be recorded in deterministic
      evidence (implementation-defined) and SHOULD be included in the configuration document so the
      `config_sha256` changes when the seed changes.
    - For DSC v3, `resource_type_allowlist` SHOULD be used to constrain configurations to expected
      safe resources.

  - Tools/features that export plaintext credentials (for example AD-Lab-Generator
    `ExportPasswords`) MUST be disabled by default; if enabled for a lab experiment, the exported
    material MUST be treated as a secret and MUST NOT be included in publishable run artifacts (see
    [security and safety](090_security_safety.md)).

- `dependencies` (optional)

  - `allow_runtime_self_update` (default: `false`)
    - v0.1: MUST be `false`. Setting to `true` MUST be rejected by config validation (fail closed
      with `reason_code=config_schema_invalid`).
    - When `false`, any runner-managed self-update attempt MUST be blocked deterministically.
      - “Self-update” here should be defined narrowly as runner-managed dependency mutation (for
        example: updating the runner’s executor tooling, updating pinned modules the runner relies
        on, etc.), not the technique’s own intended side effects.
    - When blocked, the runner MUST surface the outcome deterministically via existing runner
      failure semantics (no new reason-code inventing in 120; keep it as a policy gate /
      configuration-invalid or “dependency missing” path per existing runner behavior).

- `caldera` (optional, when `type: caldera`)

  - `endpoint` (required)
  - `api_token_ref` (required): reference only (example: `env:CALDERA_TOKEN`)
    - Prefer configuring this token under `security.integration_credentials.caldera.api_token_ref`.
      If both are present, they MUST match exactly; otherwise config validation MUST fail closed
      with `reason_code=config_schema_invalid`.
  - `operation` (optional): profile or operation template identifier
  - `agent_selector` (optional): tags or asset ids

- `atomic` (optional, when `type: atomic`)

  - `atomic_root` (optional): path to Atomic Red Team definitions
  - `executor` (optional, default: `invoke_atomic_red_team`):
    `invoke_atomic_red_team | atomic_operator | other`
    - `invoke_atomic_red_team`: execute Atomics via the PowerShell Invoke-AtomicRedTeam module
      (reference executor for v0.1; MUST conform to
      [atomic red team executor integration specification](032_atomic_red_team_executor_integration.md))
    - `atomic_operator`: execute Atomics via a cross-platform runner (Python), suitable for
      Linux/macOS targets
  - `timeout_seconds` (optional, default: 300): per-test execution timeout
  - `prereqs` (optional)
    - `mode` (optional, default: `check_only`): `check_only | check_then_get | get_only`
      - `check_only`: the runner MUST NOT execute Atomic `get_prereq_command`.
      - `check_then_get`: the runner MAY execute `get_prereq_command` only when prerequisite checks
        fail. Any prerequisite get/install MUST be recorded as a side effect
        (`effect_type=prereq_install`) attributable to `prepare` (see
        `032_atomic_red_team_executor_integration.md`).
      - `get_only`: the runner MAY execute `get_prereq_command` unconditionally. Any prerequisite
        get/install MUST be recorded as a side effect (`effect_type=prereq_install`) attributable to
        `prepare` (see `032_atomic_red_team_executor_integration.md`).
  - `template_snapshot` (optional)
    - `mode` (optional, default: `off`; enum: `off | extracted | source`)
      - `off`: do not write template snapshot artifacts.
      - `extracted`: write `runner/actions/<action_id>/atomic_test_extracted.json`.
      - `source`: write both:
        - `runner/actions/<action_id>/atomic_test_extracted.json`
        - `runner/actions/<action_id>/atomic_test_source.yaml`
      - When mode is `extracted` or `source`, the runner MUST write `atomic_test_extracted.json`
        before attempting execution and before prerequisites evaluation.
      - When mode is `source`, the runner MUST also write `atomic_test_source.yaml` with newline
        normalization to LF.
      - Snapshot artifacts represent the Atomic template (no input placeholder substitution; no
        resolved/substituted commands).
      - See also: `032_atomic_red_team_executor_integration.md` ("Atomic template snapshot"); it
        defines `runner.atomic.template_snapshot.mode` semantics.
  - `capture_transcripts` (optional, default: true): persist per-test stdout/stderr under `runner/`
    evidence
  - `capture_terminal_recordings` (optional, default: false): persist per-test terminal session
    recordings (asciinema `.cast`) under `runner/actions/<action_id>/terminal.cast` for human
    debugging/docs (MUST NOT be used for scoring)
  - `capture_executor_metadata` (optional, default: true): persist per-test executor.json (exit
    code, duration, timestamps)
  - `cleanup` (optional)
    - `invoke` (optional, default: true): call the Atomic cleanup command when available
    - `verify` (optional, default: true): run cleanup verification checks and persist results under
      `runner/`
    - `verification_profile` (optional): named set of cleanup checks (implementation-defined)
  - `requirements` (optional)
    - `fail_mode` (default: `fail_closed`): `fail_closed | warn_and_skip`
      - `fail_closed`: if action requirements are `unsatisfied` or `unknown`, the runner MUST NOT
        attempt execution and MUST fail closed after writing deterministic evidence (ground truth +
        `requirements_evaluation.json`).
      - `warn_and_skip`: if action requirements are `unsatisfied` or `unknown`, the runner MUST mark
        the action non-executable (`prepare.phase_outcome=skipped`) with stable reason codes and MAY
        continue with other actions (v0.2+).
  - `synthetic_correlation_marker` (optional)
    - `enabled` (optional, default: `false`)
      - When `true`, the runner emits synthetic marker events for correlation (see
        `032_atomic_red_team_executor_integration.md`) and records the marker value in run
        artifacts.
        - Ground truth action records: `extensions.synthetic_correlation_marker` (see
          `025_data_contracts.md`).
        - Normalized OCSF events (when marker-bearing telemetry is ingested and normalized):
          `metadata.extensions.purple_axiom.synthetic_correlation_marker` (see
          `050_normalization_ocsf.md`).
    - `method` (optional, default: `auto`): `auto | windows_eventlog | linux_syslog | filelog`
      - `auto`: implementation selects an OS-appropriate method.
      - `filelog`: marker is appended to a local file that is tailed by the collector.
    - `filelog_path` (optional, required when `method=filelog`)
  - `state_reconciliation` (optional)
    - `enabled` (optional, default: `false`)
      - When `true`, the runner performs per-action state reconciliation (see
        `032_atomic_red_team_executor_integration.md`) and writes
        `runner/actions/<action_id>/state_reconciliation_report.json` (see `025_data_contracts.md`).
      - When `false`, the runner MUST NOT attempt reconciliation and MUST NOT produce
        `state_reconciliation_report.json`.
    - `allow_repair` (optional, default: `false`) (reserved)
      - When `true`, the runner MAY perform reconciliation-time repair only when:
        - the action's effective reconciliation policy requests repair, and
        - the repair operation is allowlisted (see below), and
        - the implementation supports repair for the selected effect types.
      - v0.1: MUST be `false`. Setting `allow_repair=true` MUST be rejected by config validation
        (fail closed with `reason_code=config_schema_invalid`).
    - `repair_allowlist_effect_types` (optional) (reserved)
      - List of allowlisted reconciliation effect types that may be repaired (implementation-defined
        tokens).
      - When `allow_repair=true`, this list MUST be present and MUST be non-empty; otherwise config
        validation MUST fail closed with `reason_code=config_schema_invalid`.
      - When `allow_repair=false`, the runner MUST treat any requested repair intent as blocked and
        MUST NOT mutate targets. Blocked repair MUST be accounted for in reconciliation outputs and
        operability counters (see `032_atomic_red_team_executor_integration.md` and
        `110_operability.md`).
  - `technique_allowlist` (optional): list of ATT&CK technique ids
  - `technique_denylist` (optional): list of ATT&CK technique ids
  - `executor_allowlist` (optional): list (example: `powershell`, `cmd`, `bash`)

- `custom` (optional, when `type: custom`)

  - `command` (required): local command or script path
  - `args` (optional): list
  - `env` (optional): key/value map (values should be refs when sensitive)

- If `runner.identity.cache_policy=cross_run_allowed`, config validation MUST fail closed unless:

  - `cache.cross_run_allowed=true`, and
  - `cache.emit_cache_provenance=true`.

- If `emit_principal_context=true`, `principal_context.json` MUST follow the deterministic ordering
  rules (sorted principals and action map).

- If a self-update is required to proceed and `allow_runtime_self_update=false`, the runner MUST
  fail closed rather than silently updating.

Determinism guidance:

- The runner should record its version and inputs in the manifest.
- Allowlists and denylists should be explicit and versioned.

Plan execution defaults (reserved for v0.2+):

- `plan` (optional): defaults and safety caps applied when compiling multi-action plans.
  - `model_version` (optional, default: `0.2.0`): requested plan execution model version.
  - `max_nodes` (optional, default: 100): hard cap on expanded plan node count; if exceeded, fail
    closed with `reason_code=plan_expansion_limit`.
  - `max_concurrency` (optional, default: 1): upper bound on concurrent action execution; per-plan
    requested concurrency MUST be clamped to this value.
  - `fail_fast` (optional, default: false): if true, halt scheduling of remaining nodes after the
    first failure.

### Cache (optional, cache)

Controls explicit enablement and provenance requirements for caches that may affect determinism.

Definitions (normative):

- A cache is considered **cross-run** if it can be read by a different run than the one that created
  it.
- Implementations MUST treat any on-disk cache directory outside `runs/<run_id>/` as cross-run.
- "Derived state" refers to deterministic, recomputable materializations (for example compiled
  plans, parsed schemas, and intermediate indexes). If derived state is persisted outside
  `runs/<run_id>/` and reused across runs, it is treated as a cross-run cache under this section.

Common keys:

- `cross_run_allowed` (default: `false`)
  - Global gate: when `false`, any configuration that would enable cross-run caching MUST be
    rejected by config validation (fail closed).
- `emit_cache_provenance` (default: `true`)
  - When `true`, the pipeline MUST write `logs/cache_provenance.json` and MUST record cache usage
    deterministically.
  - When `false`, cross-run caches MUST NOT be used.
  - When `false`, the pipeline MAY use strictly per-run caches under `runs/<run_id>/`.

Normative requirements:

- Any cross-run cache usage MUST be recorded in `logs/cache_provenance.json` with stable ordering
  `(component, cache_name, key)` and the policy enum values already defined.
- If `cross_run_allowed=true`, then `emit_cache_provenance` MUST be `true`. Otherwise, config
  validation MUST fail closed.
- If cross-run cache usage is detected at runtime while `cross_run_allowed=false`, the pipeline MUST
  fail closed.

Implementation guidance (non-normative):

- Backing a cross-run cache with a local database (for example SQLite) is permitted. The database
  file is considered part of the cache directory and is therefore subject to the same gating and
  provenance requirements.
- When helpful for debugging, implementations MAY include a stable backend marker in
  `entries[].notes` (for example `backend=sqlite; store_format=v1`), subject to the redaction rules
  in `090_security_safety.md`.

### Control plane (optional, control_plane)

Reserved for a future optional RPC-based endpoint management layer (for example, agent configuration
injection).

Common keys:

- `enabled` (optional, default: false)
  - v0.1: MUST be `false`. Setting to `true` MUST be rejected by schema validation (fail closed with
    `reason_code=config_schema_invalid`).
- `transport` (optional): `ssh | winrm | grpc | other` (reserved; ignored when disabled)
- `targets` (optional): allowlist of `lab.assets[].asset_id` to which control-plane actions may
  apply
- `auth` (optional): transport-specific authentication; values MUST be secret references (`*_ref`)
  - `username_ref` (optional)
  - `password_ref` (optional)
  - `private_key_ref` (optional)
  - `token_ref` (optional)
- `audit` (optional)
  - `enabled` (optional, default: true): when enabled, implementations MUST record a deterministic
    audit transcript into the run bundle at `runs/<run_id>/control/audit.jsonl`.
    - The audit file MUST be JSONL (one UTF-8 JSON object per line, terminated by `\n`).
    - Each line MUST validate against the `audit_event` contract
      (`docs/contracts/audit_event.schema.json`, `contract_version=0.2.0`).
    - Implementations MUST append and flush the audit event to durable storage before performing any
      security-sensitive control-plane action and before returning a successful response. See
      [ADR-0004: Deployment architecture and inter-component communication](../adr/ADR-0004-deployment-architecture-and-inter-component-communication.md).

Notes:

- Implication: v0.1 does not remotely modify agent collector configs; required invariants (for
  example Windows `raw: true`) are enforced by pre-provisioned configuration plus telemetry
  validation canaries.
- Control-plane functionality is out of scope for v0.1. The v0.1 pipeline MUST NOT require remote
  management credentials and MUST NOT depend on control-plane actions for correctness.

### Telemetry (telemetry)

Controls collection and staging of raw telemetry (analytics-tier Parquet under `raw_parquet/`;
evidence-tier raw preservation under `raw/` when enabled).

Common keys:

- `otel` (optional)
  - `enabled` (default: true)
  - `config_path` (required when enabled): path to OTel Collector config file
  - `channels` (optional): list of sources/channels to enable (implementation-defined)
    - v0.1 Windows baseline (normative): MUST include `application`, `security`, `system`, and
      `sysmon` (Microsoft-Windows-Sysmon/Operational).
  - `bookmarks` (optional): resume policy for sources that support cursoring
    - `mode` (default: `auto`): `auto | resume | reset`
      - `auto`: resume if a checkpoint exists, otherwise reset
      - `resume`: require checkpoint; if missing/corrupt, fall back to reset and mark checkpoint
        loss
      - `reset`: ignore checkpoints and start at run window start (plus skew tolerance)
    - `checkpoint_dir` (optional): defaults to a platform-local directory on the collector host
      (implementation-defined; MUST be writable). A run-bundle snapshot MAY be copied into
      `runs/<run_id>/logs/telemetry_checkpoints/` for diagnostics.
    - `flush_interval_seconds` (default: 5)
  - `checkpoint_corruption` (optional): policy for checkpoint store corruption events (validation
    and operability)
    - `mode` (default: `fail_closed`): `fail_closed | recreate_fresh`
      - `fail_closed`: treat checkpoint store corruption as fatal for telemetry; the collector MUST
        NOT automatically recreate checkpoint state.
      - `recreate_fresh`: allow storage backends that recreate state on corruption. This MUST be
        treated as checkpoint loss and replay start mode MUST be recorded as `reset_corrupt`.
    - `require_fsync` (default: true): when the checkpoint backend supports an fsync option
      (example: OTel `file_storage.fsync`), validation MUST require that it is enabled unless the
      operator explicitly disables this check.
  - `agent_liveness`
    - `startup_grace_seconds` (default: `30`)
      - Startup grace period for observing the agent heartbeat derived from collector
        self-telemetry.
    - `required_metric_names` (default:
      `["otelcol_process_memory_rss", "otelcol_process_cpu_seconds"]`)
      - Ordered allowlist of metric names that qualify as a heartbeat. If none are observed for an
        expected asset within the startup grace, telemetry validation MUST fail closed with
        `reason_code=agent_heartbeat_missing` (see operability and stage outcome specifications).
- `baseline_profile` (optional)
  - `enabled` (optional, default: false)
    - When `true`, telemetry validation MUST enforce the telemetry baseline profile gate (see
      `040_telemetry_pipeline.md`) and MUST emit a health stage outcome
      `stage="telemetry.baseline_profile"`.
  - `profile_path` (required when enabled): path to a telemetry baseline profile JSON file.
    - If the profile is missing or unreadable, telemetry MUST fail closed with
      `reason_code=baseline_profile_missing`.
    - If contract validation fails, telemetry MUST fail closed with
      `reason_code=baseline_profile_invalid`.
    - The implementation MUST snapshot the effective profile bytes into
      `runs/<run_id>/inputs/telemetry_baseline_profile.json` and use the snapshotted bytes for
      evaluation and hashing.
    - Terminology note (normative): this telemetry baseline profile is a *telemetry validation*
      input. It MUST NOT be used as a benign noise/workload generator. Benign background activity is
      configured separately via `runner.environment_config.noise_profile`.
- `sources` (optional)
  - Additional sources (example: `unix`, `osquery`, `pcap`, `netflow`)
  - v0.1: `pcap` and `netflow` are placeholder contracts only (collection/ingestion is not
    required). If enabled without an implementation, telemetry MUST fail closed with
    `reason_code=source_not_implemented`.
  - Each source should include (when applicable):
    - `enabled`
    - `config_path` or equivalent
    - `output_path` under `raw/`
  - v0.1 reserved output paths (normative when implemented):
    - `pcap.output_path` MUST be `raw/pcap/` (manifest: `raw/pcap/manifest.json`)
    - `netflow.output_path` MUST be `raw/netflow/` (manifest: `raw/netflow/manifest.json`)
  - `unix` (optional)
    - Unix log ingestion declarations used for duplication avoidance validation and provenance (see
      `044_unix_log_ingestion.md`).
    - `journald` (optional)
      - `enabled` (default: false)
    - `syslog_files` (optional): list of absolute paths to syslog text files expected to be tailed.
      - Example values: `/var/log/syslog`, `/var/log/messages`, `/var/log/auth.log`.
    - `dedupe_strategy` (optional): overlap dedupe strategy token (discouraged;
      implementation-defined; see `044_unix_log_ingestion.md`).
      - v0.1 allowed token: `unix_syslog_fingerprint_v1`.
      - When set, the pipeline MUST record the effective value in the run manifest at
        `manifest.telemetry.sources.unix.dedupe_strategy`.
  - `osquery` (optional)
    - `enabled` (default: false)
    - `config_path` (optional): path to an osquery configuration file (deployment is
      runner/provider-defined). If present, the effective config SHOULD be snapshotted into the run
      bundle for provenance.
    - `results_log_path` (recommended): absolute path on the endpoint to the osquery results log
      (the NDJSON results file).
      - This SHOULD be explicit in lab configs to avoid OS/package default ambiguity.
    - `log_format` (default: `event_ndjson`): `event_ndjson | batch_json`
      - `event_ndjson` is the v0.1 canonical format (one JSON object per line).
      - `batch_json` is reserved; if used, ingestion requires multiline framing and MUST have
        explicit conformance tests.
    - `otel_ingest` (optional)
      - `enabled` (default: true): when true, the operator MUST configure the OTel Collector to tail
        `results_log_path` (typically via the `filelog` receiver) and tag records such that
        `metadata.source_type = "osquery"` can be set during normalization.
      - `receiver_id` (optional): logical receiver id in the OTel config (example:
        `filelog/osquery`) for traceability.
    - `output_path` (required): destination directory under the run bundle `raw/` where osquery raw
      logs are staged (example: `raw/osquery/`)

See the [osquery integration specification](042_osquery_integration.md) for format requirements,
OTel receiver examples, normalization routing, and fixtures.

Notes:

- For Windows Event Log sources, the referenced OTel Collector config MUST set `raw: true` for every
  enabled `windowseventlog/*` receiver.
- Collector self-telemetry MUST be exported upstream (for example Prometheus self-scrape plus OTLP
  export) to support resource budgets and agent liveness (dead-on-arrival detection).
- For v0.1, the config SHOULD also set `suppress_rendering_info: true` and a persistent `storage`
  extension for bookmarks (see the [telemetry pipeline specification](040_telemetry_pipeline.md)
  §2).
- OTel Collector configuration shape is owned by upstream OTel. Purple Axiom only references the
  path and hashes it.
- `telemetry.otel.checkpoint_corruption` does not generate collector configuration. It is a policy
  input for telemetry validation and operability reporting: the validator SHOULD inspect the
  effective collector config and logs to determine whether checkpoint corruption recovery was
  allowed and/or observed.

Additional Purple Axiom staging policy (applies during raw Parquet writing and optional sidecar
extraction):

- `payload_limits` (optional)
  - Staging-time size limits applied during raw Parquet writing and optional sidecar extraction (see
    `040_telemetry_pipeline.md` and `045_storage_formats.md`).
  - `max_event_xml_bytes` (optional, default: 1048576)
    - Maximum UTF-8 byte length for inlining Windows Event Log `event_xml` in
      `raw_parquet/windows_eventlog/`.
    - When the payload exceeds this limit, the writer MUST truncate deterministically and MUST write
      the full payload to a deterministically addressed sidecar blob when sidecar retention is
      enabled (see `045_storage_formats.md` “Raw payload sizing and sidecars” and “Sidecar blob
      store”).
  - `max_field_chars` (optional, default: 262144)
    - Maximum character length for any single promoted string field at staging time (deterministic
      truncation bound).
  - `max_binary_bytes` (optional, default: 262144)
    - Maximum decoded byte length for extracted binary payloads written to sidecar (oversize decoded
      payloads must not be externalized; record a deterministic summary instead).
  - `sidecar` (optional)
    - `enabled` (optional, default: true)
      - When `true`, oversize payloads MUST be externalized using the deterministic sidecar
        addressing scheme defined by `045_storage_formats.md` (event-specific directory +
        `field_path_hash`).
      - When `false`, implementations MUST NOT emit a truncated payload representation that violates
        the raw Windows Event Log overflow constraints in `045_storage_formats.md`. Concretely:
        implementations MUST either (a) avoid truncation by configuration, or (b) fail closed on
        overflow.
    - `dir` (optional, default: `raw/evidence/blobs/wineventlog/`)
      - Relative directory under the run bundle root used as the sidecar prefix.
      - Sidecar objects MUST be addressed deterministically beneath this prefix using:
        - `event_id_dir` (filesystem-safe directory derived from `metadata.event_id`), and
        - `field_path_hash` (filename stem), as defined by `045_storage_formats.md` “Sidecar blob
          store”.
- `native_container_exports` (optional)
  - v0.1 policy (normative):
    - The pipeline MUST NOT require native container exports. Pipeline correctness MUST NOT depend
      on native container exports.
    - Native container exports MAY be supported behind an explicit config gate, but docs SHOULD
      refer to them generically (or omit them entirely) until the capability is implemented.
  - `enabled` (optional, default: false)
    - When `true`, the implementation MAY export source-native container artifacts as additional
      evidence-tier material.
  - `dir` (optional, default: `raw/evidence/`): relative directory under the run bundle root for
    exported native containers (subpaths are implementation-defined).
  - Requirements when `enabled: true` (normative):
    - Exported containers MUST count toward run-scoped disk usage limits (see
      `operability.run_limits`).
    - Exported containers MUST follow `security.redaction` behavior (withhold or quarantine when
      unredacted).
    - The run manifest and report SHOULD disclose that native containers were exported and their
      relative paths.

### Normalization (normalization)

Controls raw-to-OCSF transformation and the normalized store written under `normalized/`.

Common keys:

- `ocsf_version` (required): pinned OCSF version string (example: `1.7.0`)
- `mapping_profiles` (optional): list of profile identifiers (example: `windows`, `linux`, `dns`)
- `source_type_mapping` (optional): map of raw source identifiers to `metadata.source_type`
  - Note: `metadata.source_type` is an event/source-pack discriminator. It MUST NOT be conflated
    with `identity_basis.source_type` (identity_source_type) used for `metadata.event_id` hashing
    (see ADR-0002-event-identity-and-provenance.md).
- `dedupe` (optional)
  - `enabled` (default: true)
  - `scope` (default: `per_run`): `per_run` (v0.1 only)
  - `index_dir` (optional; run-relative directory under the run bundle root)
    - Default: `logs/dedupe_index/`
    - Path constraints (normative):
      - MUST be a run-relative POSIX path (no leading `/`, no drive letters, no `..` segments).
      - MUST normalize to `logs/dedupe_index/` or a subdirectory under `logs/dedupe_index/`.
      - Any value that would resolve outside `runs/<run_id>/logs/dedupe_index/` MUST be rejected by
        config validation (fail closed with `reason_code=config_schema_invalid`).
    - Rationale (non-normative): the dedupe index is volatile diagnostics and remains excluded from
      default export bundles and `security/checksums.txt` when it stays under `logs/` (see
      `050_normalization_ocsf.md`, `025_data_contracts.md`, and ADR-0009).
  - `conflict_policy` (default: `warn`): `warn | fail_closed`

Notes (v0.1):

- Purple Axiom v0.1 pins `ocsf_version = "1.7.0"`. OCSF schema update/migration policy is defined in
  the [normalization specification](050_normalization_ocsf.md).
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

### Validation (validation)

Controls criteria-pack evaluation (expected telemetry) and cleanup verification reporting.

Common keys:

- `enabled` (default: true)
- `criteria_pack` (optional)
  - `criteria_pack_id` (required when enabled): identifier for the criteria pack
  - `criteria_pack_version` (optional, recommended): pinned version for reproducibility
    - Determinism requirement:
      - For CI/regression runs, `criteria_pack_version` SHOULD be set explicitly.
    - If `criteria_pack_version` is omitted:
      - The implementation MUST resolve a version deterministically using SemVer ordering:
        1. Enumerate available `<criteria_pack_id>/<criteria_pack_version>/` directories across
           `paths`.
        1. Parse candidate versions as SemVer.
        1. Select the highest SemVer version.
        1. If no candidates parse as SemVer, fail closed.
      - The resolved `criteria_pack_version` MUST be recorded in run provenance (manifest + report).
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
    - `fail_closed`: criteria evaluation errors that prevent producing a complete
      `criteria/results.jsonl` MUST cause the criteria stage outcome to be `failed`.
    - `warn_and_skip`: evaluator MUST still emit `criteria/results.jsonl` rows for all selected
      actions; actions that cannot be evaluated MUST be marked `status: "skipped"` with a stable
      `reason_domain="criteria_result"` and `reason_code`.

Notes:

- Criteria evaluation SHOULD operate on the normalized OCSF store (not raw events).
- When `fail_mode: fail_closed`, criteria evaluation errors MUST produce a validation stage outcome
  of `failed`, and `manifest.status` MUST be derived per the
  [data contracts specification](025_data_contracts.md) ("Status derivation").
- Reporting/triage note (normative): Validation is a pipeline stage but the reporting measurement
  layer taxonomy is coarser. Validation-originated gap categories (`criteria_unavailable`,
  `criteria_misconfigured`, `cleanup_verification_failed`) MUST be attributed to
  `measurement_layer="scoring"` (see `070_scoring_metrics.md` and `080_reporting.md`).

### Detection (detection)

Controls evaluation over normalized OCSF events and outputs to `detections/`.

Common keys:

- `mode` (default: `batch`): `batch | streaming`
- `sigma` (optional)
  - `enabled` (default: true)
  - `rule_paths` (required when enabled): list of directories/files containing Sigma YAML
  - `rule_set_version` (optional): pinned identifier for reporting and trending
  - `bridge` (optional, recommended)
    - `mapping_pack_id` (required): identifier for the Sigma-to-OCSF mapping pack (router + field
      aliases)
    - `mapping_pack_version` (optional, recommended): pin for reproducibility
    - `backend` (default: `native_pcre2`): `native_pcre2 | tenzir | other`
    - `backend_options` (object, optional)
      - Passed through to the selected backend adapter at initialization.
      - For `native_pcre2`, the following keys are supported:
        - `threads` (integer, default: `1`): evaluator worker threads. v0.1 MUST use `1` for
          deterministic correlation evaluation.
        - `timezone` (string, default: `UTC`): timezone for interpreting OCSF `time`. v0.1 MUST use
          `UTC`.
        - `max_matched_event_ids` (integer, optional): maximum number of event ids to attach to a
          single correlation detection instance. If exceeded, the evaluator MUST truncate
          deterministically.
        - `regex` (object, optional)
          - `max_pattern_length` (integer, optional)
          - `match_limit` (integer, optional)
          - `depth_limit` (integer, optional)
      - For `tenzir`, supported keys are backend-defined.
    - `fail_mode` (default: `fail_closed`): `fail_closed | warn_and_skip`
      - `fail_closed`: bridge/backend errors that prevent evaluating enabled rules (routing,
        compilation, backend execution) MUST cause the detection stage outcome to be `failed`.
      - `warn_and_skip`: such errors MUST be recorded; affected rules MUST be marked non-executable
        with a stable `reason_domain="bridge_compiled_plan"` and `reason_code`. The detection stage
        outcome SHOULD be `success` unless the stage cannot produce outputs at all.
    - `raw_fallback_enabled` (default: true)
    - Controls whether rules may reference `raw.*` per the
      [Sigma-to-OCSF bridge specification](065_sigma_to_ocsf_bridge.md) ("Fallback policy
      (raw.\*)").
    - When `false`, any rule requiring `raw.*` MUST be marked non-executable with
      `reason_domain="bridge_compiled_plan"` and `reason_code: "raw_fallback_disabled"`.
    - When `true`, any fallback use MUST be accounted for via `extensions.bridge.fallback_used=true`
      in detection outputs.
    - `compile_cache_dir` (optional): workspace-root relative path under `<workspace_root>/cache/`
      for cached compiled plans keyed by (rule hash, mapping pack version, backend version)
      - `compile_cache_dir` MUST NOT be an absolute path and MUST resolve under
        `<workspace_root>/cache/` (see "Workspace root and filesystem paths").
      - If `compile_cache_dir` points to a location reused across runs, it is a cross-run cache and
        therefore:
        - requires `cache.cross_run_allowed=true`, and
        - MUST record an entry in `logs/cache_provenance.json` (component=`detection`,
          cache_name=`sigma_compile_cache`, policy/result/key per contract).
  - `limits` (optional)
    - `max_rules` (optional)
    - `max_compile_errors` (optional)
- `join` (optional)
  - `clock_skew_tolerance_seconds` (default: 30)

Notes:

- The Sigma-to-OCSF bridge is specified in the
  [Sigma-to-OCSF bridge specification](065_sigma_to_ocsf_bridge.md). This config selects the mapping
  pack and backend behavior.
- `fail_closed` is the recommended default so rules that cannot be routed or mapped are reported as
  non-executable rather than silently producing “no matches”.

### Scoring (scoring)

Controls the scoring model and classification taxonomy written under `scoring/`.

Common keys:

- `enabled` (default: true)
- `gap_taxonomy` (default)
  - `missing_telemetry`
  - `criteria_unavailable`
  - `criteria_misconfigured`
  - `normalization_gap`
  - `bridge_gap_mapping`
  - `bridge_gap_feature`
  - `bridge_gap_other`
  - `rule_logic_gap`
  - `cleanup_verification_failed`
- `thresholds` (optional): allow CI to fail if below expected quality.
  - v0.1 defaults (normative) if omitted: `min_technique_coverage=0.75`,
    `max_allowed_latency_seconds=300`, `min_tier1_field_coverage=0.80`,
    `max_missing_telemetry_rate=0.10`, `max_normalization_gap_rate=0.05`,
    `max_bridge_gap_mapping_rate=0.10`, `max_bridge_gap_feature_rate=0.40`,
    `max_bridge_gap_other_rate=0.02`.
  - Keys:
    - `min_technique_coverage`: percent of executed techniques that must have ≥1 detection.
    - `max_allowed_latency_seconds`: maximum time delta between a ground truth action and first
      detection hit.
    - `min_tier1_field_coverage`: minimum Tier 1 field coverage ratio (0.0-1.0).
    - `max_missing_telemetry_rate`: maximum fraction of executed techniques classified as
      `missing_telemetry` (0.0-1.0).
    - `max_normalization_gap_rate`: maximum fraction of executed techniques classified as
      `normalization_gap` (0.0-1.0).
    - `max_bridge_gap_mapping_rate`: maximum fraction of executed techniques classified as
      `bridge_gap_mapping` (0.0-1.0). Default: 0.10.
    - `max_bridge_gap_feature_rate`: maximum fraction of executed techniques classified as
      `bridge_gap_feature` (0.0-1.0). Default: 0.40.
    - `max_bridge_gap_other_rate`: maximum fraction of executed techniques classified as
      `bridge_gap_other` (0.0-1.0). Default: 0.02.
    - `max_false_positive_detection_rate` (optional): float in `[0,1]` (maximum false positive
      detection rate; see `false_positive_detection_rate` in `070_scoring_metrics.md`). Only
      evaluated when the detections stage is enabled and `detections_total > 0`.
    - `max_false_positive_detection_count` (optional): integer >= 0 (maximum false positive
      detections; see `false_positive_detection_count` in `070_scoring_metrics.md`). Only evaluated
      when the detections stage is enabled.
- `weights` (optional): allow scores to emphasize certain categories.
  - v0.1 defaults (normative) if omitted: `coverage_weight=0.60`, `latency_weight=0.25`,
    `fidelity_weight=0.15`.
  - Keys:
    - `coverage_weight`: factor for technique coverage.
    - `latency_weight`: factor for time-to-detection.
    - `fidelity_weight`: factor for match quality (exact vs partial vs weak).

Notes:

- `gap_taxonomy` is a selection/filter for evaluation, budgeting, and CI gating. It MUST NOT change
  the schema shape of scoring outputs or the regression comparable metric surface.
- Excluded categories MUST still appear in scoring outputs as indeterminate to preserve a stable row
  set for regression diffs:
  - For per-category tables (for example, "gap rate by category"), excluded categories MUST be
    present with `value: null` and `indeterminate_reason: "excluded_by_config"`.
  - For per-category comparable metrics (for example, `criteria_misconfigured_rate`), excluded
    categories MUST be present with `value: null` and `indeterminate_reason: "excluded_by_config"`.
  - Implementations MUST NOT omit per-category rows or per-category metric identifiers due to
    `gap_taxonomy` exclusions.
- Regression guidance: baseline and candidate runs SHOULD use identical effective `gap_taxonomy`
  selections to avoid indeterminate deltas. If the effective selections differ, regression deltas
  for affected metrics MUST be indeterminate with `indeterminate_reason: "taxonomy_mismatch"` (see
  `070_scoring_metrics.md`).
- The `gap_taxonomy` list MUST be a subset of the canonical pipeline-health gap taxonomy tokens
  defined in `070_scoring_metrics.md` (Pipeline health, v0.1). Configuration validation MUST reject
  unknown `gap_taxonomy` entries (fail closed).
- Gap category to measurement layer mapping is defined in `070_scoring_metrics.md` and is normative.
  Configuration MUST NOT redefine or remap categories into different layers.

Example (non-normative): excluding a category without changing the stable row set

Config excerpt (YAML):

```yaml
scoring:
  enabled: true
  gap_taxonomy:
    - missing_telemetry
    - criteria_unavailable
    # criteria_misconfigured intentionally excluded
    - normalization_gap
    - bridge_gap_mapping
    - bridge_gap_feature
    - bridge_gap_other
    - rule_logic_gap
    - cleanup_verification_failed
```

Expected scoring output excerpt (JSON; illustrative; the full output includes a row/value for every
canonical `gap_category`):

```json
{
  "pipeline_health_by_gap_category": [
    {
      "gap_category": "missing_telemetry",
      "value": 0.0312,
      "indeterminate_reason": null
    },
    {
      "gap_category": "criteria_misconfigured",
      "value": null,
      "indeterminate_reason": "excluded_by_config"
    }
  ]
}
```

### Reporting (reporting)

Controls report generation and output locations.

Common keys:

- `output_dir` (required): base directory for run bundles (example: `runs/`)
- `emit_html` (default: true)
  - When `true`, reporting MUST emit `report/report.html` per `080_reporting.md`.
  - The HTML report MUST be self-contained and local-only: it MUST NOT reference remote assets and
    MUST NOT rely on external `.css` or `.js` files.
- `emit_json` (default: true)
- `include_debug_sections` (default: false)
- Failure semantics (v0.1 baseline):
  - Reporting is `fail_closed` when enabled (see ADR-0005).
  - `html_render_error` severity is policy-dependent:
    - when HTML is required (`emit_html=true`) it is treated as FATAL under fail-closed semantics
    - when HTML is best-effort (`emit_html=false`) it is recorded as NON-FATAL warning-only
- `regression` (optional)
  - `enabled` (default: false)
    - When `true`, reporting MUST attempt a deterministic comparison against a baseline run and MUST
      record regression results only in `report/report.json` under the `regression` object.
      - Implementations MUST NOT emit standalone regression artifacts (for example
        `report/regression.json`); see `045_storage_formats.md`.
  - Baseline selection (exactly one when `enabled: true`):
    - `baseline_run_id` (string, UUID): baseline run identifier
    - `baseline_manifest_path` (string): relative path to a baseline `manifest.json`
      - `baseline_manifest_path` MUST be relative to `reporting.output_dir`. Absolute paths MUST NOT
        be used for baseline selection.
  - Baseline reference materialization (normative when `enabled: true`):
    - Reporting MUST record baseline selection inputs in
      `runs/<run_id>/inputs/baseline_run_ref.json` (schema-backed; see `025_data_contracts.md`).
    - When baseline resolution succeeds, reporting SHOULD snapshot the baseline manifest bytes to
      `runs/<run_id>/inputs/baseline/manifest.json` (preferred for portability).
    - If both snapshot and pointer forms are present, they MUST be consistent (the baseline manifest
      SHA-256 must match) per `045_storage_formats.md`.
  - `thresholds` (optional): allowlist of comparable metrics and tolerances used to classify deltas
    - Entries are used to populate `report/report.json.regression.deltas[].tolerance` and determine
      `within_tolerance` and `regression_flag` (see `080_reporting.md`).
    - Comparable metric identifiers and rounding/tolerance semantics are defined in
      `070_scoring_metrics.md`.
  - `alert_status_recommendation` (optional, default: `partial`; enum: `partial | failed`)
    - Controls how regression alerts (`report/report.json.regression.regression_alerted=true`)
      affect `report/thresholds.json.status_recommendation` (see `080_reporting.md`).
    - When `partial` (default), regression alerts MUST downgrade status recommendation to at least
      `partial`.
    - When `failed`, regression alerts MUST set status recommendation to `failed`.
    - The effective value MUST be recorded in `report/thresholds.json` (schema in
      `080_reporting.md`).
  - Notes (recommended for CI/regression runs):
    - Pack-like inputs that affect comparability SHOULD be explicitly pinned (see
      `criteria_pack.pack_version`, `detection.sigma.rule_set_version`, and
      `detection.sigma.bridge.mapping_pack_version`).
    - Baseline and candidate runs SHOULD use identical effective `scoring.gap_taxonomy` selections
      to avoid indeterminate regression deltas for gap-category-derived metrics. When effective
      taxonomy selections differ, affected deltas MUST be indeterminate with
      `indeterminate_reason: "taxonomy_mismatch"` (see `070_scoring_metrics.md`).
- `requirements` (optional)
  - `detail_level` (default: `reason_codes_only`): `reason_codes_only | include_sensitive_details`
    - `reason_codes_only`: reports MUST include only stable `(reason_domain, reason_code)` tokens
      and aggregate counts for unmet requirements. Reports MUST NOT include detailed tool strings,
      dependency command fragments, or privilege descriptors beyond coarse enums.
    - `include_sensitive_details`: reports MAY include the `requirements.results[]` `key` values and
      related detail fields from `runner/actions/*/requirements_evaluation.json`, subject to the
      report redaction policy and the pipeline redaction/quarantine rules.
- `redaction` (optional)
  - `enabled` (default: true)
  - `policy_ref` (optional): reference to a redaction policy file Notes:
    - `reporting.redaction` controls report rendering. It MUST NOT be interpreted as the pipeline
      redaction enablement switch.
    - Pipeline redaction enablement is controlled by `security.redaction.enabled`.

### Operability (optional, operability)

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
    - When `true`, the pipeline MUST write `runs/<run_id>/logs/health.json` (minimum schema in the
      [operability specification](110_operability.md), "Health files (normative, v0.1)").
    - When `false`, the pipeline MUST still compute `manifest.status` per the
      [data contracts specification](025_data_contracts.md) ("Status derivation").

### Security (optional, security)

Controls security boundaries and hardening (see also `090_security_safety.md`).

Common keys:

- `redaction` (optional)
  - `enabled` (default: true)
    - When `true`, the pipeline applies the effective redaction policy and promotes only
      redacted-safe artifacts into standard long-term locations.
    - When `false`, the run is explicitly unredacted and the pipeline MUST withhold sensitive
      evidence from standard long-term locations unless quarantined.
  - `policy_ref` (optional): reference to a redaction policy file (format defined in
    [ADR-0003: Redaction policy](../adr/ADR-0003-redaction-policy.md))
  - `limits` (optional)
    - `max_token_chars` (optional)
    - `max_summary_chars` (optional)
    - `max_field_chars` (optional)
    - `max_predicate_ast_nodes_per_rule` (optional)
    - `max_predicate_ast_nodes_total` (optional)
    - `max_compile_cost_units_per_rule` (optional)
    - `max_eval_cost_units_per_rule` (optional)
    - `max_eval_cost_units_total` (optional)
  - `disabled_behavior` (optional, default: `withhold_from_long_term`):
    `withhold_from_long_term | quarantine_unredacted`
    - `withhold_from_long_term`: write deterministic placeholders in standard artifact locations
    - `quarantine_unredacted`: write unredacted evidence to `runs/<run_id>/unredacted/`.
    - `runs/<run_id>/unredacted/` MUST be excluded from default exports/packaging.
  - `allow_unredacted_evidence_storage` (optional, default: false)
    - When `true` and `disabled_behavior: quarantine_unredacted`, the pipeline MAY persist
      unredacted evidence to the quarantine path.
  - `unredacted_dir` (optional, default: `unredacted/`): relative directory under the run bundle
    root for quarantined evidence
- `secrets`
  - `provider` (optional): `env | file | keychain | custom` (default: `env`)
  - `refs` (optional): map of named secret refs
    - Each value MUST be a secret reference string (see below).
  - `custom` (optional, required when `provider: custom`)
    - `executable` (required): absolute path to the custom secret provider CLI
    - `timeout_seconds` (optional, default: 5): per lookup execution timeout
    - `max_stdout_bytes` (optional, default: 65536): maximum stdout bytes accepted
- `integration_credentials` (optional)
  - Dedicated configuration block for **external integration credentials** (API tokens, client
    secrets, private keys) used by adapters and supporting tools.
  - The `integration_credentials` block is the canonical place to declare which integrations have
    credentials and to ensure secret-bearing fields are handled consistently across stages.
  - Shape: map of `<integration_id>` → `<credential_map>`
    - `<integration_id>` (id_slug_v1; REQUIRED): stable identifier of the integration.
      - RECOMMENDED: match an adapter id or provider id (examples: `caldera`, `ludus`).
    - `<credential_map>` (object; REQUIRED): map of credential fields to secret references.
      - Keys MUST end with `_ref` (example: `api_token_ref`, `client_secret_ref`,
        `private_key_ref`).
      - Values MUST be secret reference strings (see "Secret reference strings" below).
  - Persistence and redaction requirements (normative):
    - The pipeline MUST resolve integration credentials at runtime and MUST NOT write resolved
      credential values into run bundles, logs, or reports.
    - Any contract-backed artifact that records an integration’s effective configuration MUST record
      only secret references or redacted placeholders, never resolved credential values.
    - When emitting debug logs or "effective config" snapshots, implementations MUST omit credential
      values or replace them with a stable placeholder string (for example `"<REDACTED>"`) while
      preserving key presence.
  - Preflight requirement (normative):
    - If any enabled integration requires credentials, the owning stage MUST preflight credential
      resolution/validation and fail closed on missing/invalid credentials (see
      [ADR-0005](../adr/ADR-0005-stage-outcomes-and-failure-classification.md)).
- `network`
  - `allow_outbound` (default: false)
  - `allowlist` (optional): list of CIDRs/domains when outbound is enabled
  - Outbound gating (normative):
    - `security.network.allow_outbound` is a global gate for outbound egress.
    - A run MUST treat outbound egress as permitted only when:
      - `security.network.allow_outbound: true`, and
      - `scenario.safety.allow_network: true` for the selected scenario.
    - If either is `false`, outbound egress MUST be treated as denied for the run.
    - `security.network.allowlist` applies only when outbound egress is permitted.
  - `egress_canary` (optional): provider-controlled sentinel used to validate outbound isolation
    enforcement when outbound egress is denied
    - `address` (required when enabled): literal IP address (no DNS)
    - `port` (required): TCP port to probe
    - `timeout_ms` (optional, default: 2000): bounded connect timeout
    - `required_on_deny` (optional, default: true)
      - When `true`, and effective outbound policy is denied for the run, telemetry validation MUST
        fail closed if the canary is missing or incomplete.
      - When `false`, implementations MAY treat the egress canary as best-effort and record a
        `skipped` outcome with deterministic reasons.
- `adapters` (optional)
  - Controls whether non-builtin (packaged / third-party) adapters are permitted and how they are
    verified (see `020_architecture.md` "Adapter provenance recording (v0.1)").
  - `allow_third_party` (optional, default: false)
    - When `false`, the pipeline MUST fail closed if any selected adapter has
      `source_kind != "builtin"`.
  - `require_signatures` (optional, default: true)
    - When `true`, every selected adapter with `source_kind != "builtin"` MUST include a valid
      `signature` object in adapter provenance and MUST verify successfully before stage execution.
  - `trusted_key_ids` (optional): list of allowed `key_id` values for adapter signature verification
    - REQUIRED when `require_signatures: true` and third-party adapters are allowed.
    - `key_id` is defined as `sha256(public_key_bytes)` encoded as 64 lowercase hex characters.
- `signing` (optional)
  - `enabled` (default: false)
  - `key_ref` (required when enabled): reference to signing private key material (never inline)
    - v0.1 posture:
      - Disabled by default for MVP.
      - Strongly RECOMMENDED for compliance/audit/export workflows.
    - When `enabled: true`, the pipeline MUST emit bundle integrity artifacts as specified in
      [data contracts specification](025_data_contracts.md) ("Run bundle signing").
    - If signing is enabled but cannot be completed (missing key material, invalid key format,
      signing I/O error), the pipeline MUST fail closed.
  - `key_ref` (required when enabled): reference to signing private key material (never inline)
  - `algorithm` (optional, default: `ed25519`)
    - v0.1 supports `ed25519` only.
  - `key_format` (optional, default: `ed25519_seed_base64`)
    - `ed25519_seed_base64`: secret value is base64 for a 32-byte Ed25519 seed.
    - Implementations MAY support additional formats (example: OpenSSH private key) but MUST still
      emit Ed25519 signatures.
  - `trusted_key_ids` (optional): list of allowed `key_id` values for verification/export gating
    - `key_id` is defined as `sha256(public_key_bytes)` encoded as 64 lowercase hex characters.

#### Secret reference strings

A **secret reference string** identifies secret material without embedding the secret value in
configuration files.

Secret reference strings MUST use the form `<provider>:<selector>`.

Supported providers (v0.1):

- `env:<VAR_NAME>`
  - Reads the secret value from an environment variable.
- `file:<PATH>`
  - Reads the secret value from a local file.
- `keychain:<SELECTOR>`
  - Reads the secret value from an OS keychain entry.
  - The `SELECTOR` syntax is implementation-defined.
- `custom:<REF_KEY>`
  - Resolves the secret value by calling the custom secret provider CLI.

Validation rules (normative):

- Config keys that end with `_ref` MUST be secret reference strings.
- When `security.secrets.provider` is set, the implementation MUST reject secret references using a
  different provider.
- Implementations MUST treat all resolved secret values as sensitive and MUST NOT write them into
  run bundles, logs, or reports.

#### Custom secret provider CLI contract

When `security.secrets.provider: custom` is enabled, Purple Axiom resolves secret references of the
form `custom:<REF_KEY>` using an operator-supplied executable.

Configuration:

- The executable path MUST be provided as `security.secrets.custom.executable`.
- The executable path MUST be absolute.

Invocation (normative):

- The implementation MUST execute the provider directly (no shell).
- For each lookup, the implementation MUST invoke:
  - argv[0] = `security.secrets.custom.executable`
  - argv[1] = `get`
  - argv[2] = `<REF_KEY>`
- The implementation MUST enforce `timeout_seconds`.
- The implementation MUST enforce `max_stdout_bytes`.

Stdout format (normative):

- On success (exit code 0), stdout MUST contain the resolved secret value encoded as UTF-8.
- If stdout ends with exactly one line terminator (`\n` or `\r\n`), the implementation MUST strip
  that terminator.
- The implementation MUST treat all remaining stdout bytes as the secret value.

Failure behavior (normative):

- Any non-zero exit code MUST be treated as lookup failure.
- On lookup failure, the pipeline MUST fail closed when the secret is required to proceed.

Operability guidance (non-normative):

- Implementations SHOULD avoid logging provider stderr by default; if recorded for debugging, it
  SHOULD be subject to redaction.
- Implementations MAY cache resolved secrets in memory for the duration of a run, but MUST NOT
  persist them.

## Example inputs/range.yaml

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
    prereqs:
      mode: check_only    
    capture_transcripts: true
    synthetic_correlation_marker:
      enabled: false
      method: auto    
    cleanup:
      invoke: true
      verify: true
      verification_profile: "default"
    technique_allowlist: ["T1059.001"]
    executor_allowlist: ["powershell", "cmd"]

cache:
  cross_run_allowed: true
  emit_cache_provenance: true

telemetry:
  otel:
    enabled: true
    config_path: configs/otel-collector.yaml
    channels: ["windows-security", "windows-sysmon", "dns"]
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
  ocsf_version: "1.7.0"
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
    criteria_pack_id: "default"
    criteria_pack_version: "0.1.0"
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
      mapping_pack_id: "sigmahq-ocsf"
      mapping_pack_version: "0.1.0"
      backend: native_pcre2
      fail_mode: fail_closed
      raw_fallback_enabled: true
      compile_cache_dir: "cache/sigma-compiled"
    limits:
      max_rules: 5000

scoring:
  enabled: true
  gap_taxonomy:
    - missing_telemetry
    - criteria_unavailable
    - criteria_misconfigured
    - normalization_gap
    - bridge_gap_mapping
    - bridge_gap_feature
    - bridge_gap_other
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

## OTel collector config reference

Purple Axiom does not redefine the OpenTelemetry Collector configuration schema. The collector
config is referenced by path (`telemetry.otel.config_path`) and is hashed into the run manifest for
reproducibility.

Recommended practice:

- Version the collector config file in-repo.
- Treat collector config changes as pipeline changes that can affect determinism and coverage.

## Validation expectations

Minimum validation (v0.1, normative):

- YAML MUST parse successfully using a safe YAML 1.2 loader.
- Duplicate YAML mapping keys MUST be rejected (fail closed) for all configuration inputs (including
  `inputs/range.yaml` and `inputs/scenario.yaml`).
- The effective configuration (after applying precedence and overrides) MUST validate against
  `docs/contracts/range_config.schema.json` (JSON Schema draft 2020-12).
- Unknown keys MUST be rejected by schema validation at every object boundary. The only exception is
  `extensions`, which is reserved for forward-compatible, implementation-defined keys.
- On schema validation failure, the pipeline MUST fail closed before executing any stage and MUST
  report `reason_code=config_schema_invalid` (see
  [ADR-0005: Stage outcomes and failure classification](../adr/ADR-0005-stage-outcomes-and-failure-classification.md)).

Deterministic error reporting (v0.1):

- Implementations MUST emit a stable, machine-readable list of schema violations.
- Violations MUST be sorted lexicographically by `(instance_location, schema_location, message)`
  before output (to avoid library-dependent ordering).
- Each violation entry MUST include:
  - `instance_location`: JSON Pointer into the effective config (RFC 6901)
  - `schema_location`: JSON Pointer into the schema
  - `message`: human-readable summary

CI requirements (v0.1):

- CI MUST validate all committed example configs and the configuration example embedded in this
  document against `docs/contracts/range_config.schema.json`.

## References

- [Lab providers specification](015_lab_providers.md)
- [Atomic Red Team executor integration specification](032_atomic_red_team_executor_integration.md)
- [Telemetry pipeline specification](040_telemetry_pipeline.md)
- [OSquery integration specification](042_osquery_integration.md)
- [Normalization specification](050_normalization_ocsf.md)
- [Data contracts specification](025_data_contracts.md)
- [Sigma to OCSF bridge specification](065_sigma_to_ocsf_bridge.md)
- [Scoring and metrics specification](070_scoring_metrics.md)
- [Operability specification](110_operability.md)
- [Security and safety specification](090_security_safety.md)
- [Redaction policy ADR](../adr/ADR-0003-redaction-policy.md)

## Changelog

| Date       | Change                                                                  |
| ---------- | ----------------------------------------------------------------------- |
| 2026-01-22 | Add `vagrant` lab.provider; document local-only HTML report constraints |
| 2026-01-13 | Define security.network.egress_canary for outbound isolation validation |
| 2026-01-12 | Formatting update                                                       |
