---
title: Lab providers and inventory resolution
description: Defines the pluggable lab provider interface, deterministic inventory snapshotting, and canonical asset resolution rules.
status: draft
category: spec
tags: [lab, inventory, providers, determinism]
related:
  - 025_data_contracts.md
  - ADR-0004-deployment-architecture-and-inter-component-communication.md
  - ADR-0005-stage-outcomes-and-failure-classification.md
  - 120_config_reference.md
---

# Lab providers and inventory resolution

## Stage contract header

### Stage ID

- `stage_id`: `lab_provider`

### Owned output roots (published paths)

- `logs/` (contracted: `logs/lab_inventory_snapshot.json`)

### Inputs/Outputs

This section is the stage-local view of:

- the stage boundary table in
  [ADR-0004](../adr/ADR-0004-deployment-architecture-and-inter-component-communication.md), and
- the contract bindings in [contract_registry.json](../contracts/contract_registry.json).

#### Contract-backed outputs

| contract_id              | path/glob                          | Required? |
| ------------------------ | ---------------------------------- | --------- |
| `lab_inventory_snapshot` | `logs/lab_inventory_snapshot.json` | required  |

#### Required inputs

| contract_id    | Where found         | Required? |
| -------------- | ------------------- | --------- |
| `range_config` | `inputs/range.yaml` | required  |

Notes:

- Provider-specific inventory sources MAY live outside the run bundle (`lab.inventory.path`,
  provider APIs, etc.). The resolved, canonical snapshot MUST be written to
  `logs/lab_inventory_snapshot.json`.

### Config keys used

- `lab.*` (especially `lab.provider`, `lab.assets`, `lab.inventory.*`)

### Default fail mode and outcome reasons

- Default `fail_mode`: `fail_closed`
- Stage outcome reason codes: see
  [ADR-0005](../adr/ADR-0005-stage-outcomes-and-failure-classification.md) "Lab provider stage
  (`lab_provider`)".

### Isolation test fixture(s)

- `tests/fixtures/lab_providers/`
- `tests/fixtures/scenario/target_selection/`

See the [fixture index](100_test_strategy_ci.md#fixture-index) for the canonical fixture-root
mapping.

## Overview

Define a pluggable interface for resolving lab assets without coupling Purple Axiom to any single
provisioning system.

Purple Axiom uses the resolved asset list (`lab.assets`) as the canonical shape for orchestration,
telemetry correlation, scoring, and reporting.

## Goals

- Support multiple lab providers:
  - manual (inline inventory)
  - Ludus (Proxmox-backed provisioning, consume exported inventory)
  - Terraform (cloud/local provisioning, consume exported outputs)
  - Vagrant (local/dev ranges, consume exported inventory)
  - other (future)
- Ensure determinism by recording a run-scoped inventory snapshot and its hash.
- Keep secrets out of configs and artifacts (reference only).

## Non-goals

- Replacing lab provisioning tools.
- Standardizing every provider’s full state model.

## Key concepts

### Lab provider

A component that can resolve a concrete set of targets from an external inventory source.

### Inventory snapshot

A canonical JSON snapshot written into the run bundle so the run is reproducible even if the
provider state changes later.

Path notation (normative):

- In this document, `runs/<run_id>/...` is used as an illustrative on-disk prefix for run bundle
  locations.
- Any field that stores an artifact path (for example, a run-manifest pointer to the inventory
  snapshot) MUST store a run-relative POSIX path (relative to the run bundle root) and MUST NOT
  include the `runs/<run_id>/` prefix.
  - Example: `logs/lab_inventory_snapshot.json` (not
    `runs/<run_id>/logs/lab_inventory_snapshot.json`).

Recommended path:

- `logs/lab_inventory_snapshot.json`

#### Inventory snapshot schema: `lab_inventory_snapshot`

The inventory snapshot artifact (`lab_inventory_snapshot.json`) MUST be a JSON object with:

- `v` (int, required): MUST be `1`.
- `assets` (array, required): MUST contain at least one element.

Each `assets[]` element MUST conform to the canonical asset shape defined by this spec:

- `asset_id` (string, required): stable Purple Axiom logical asset id.
- `os` (string, required): MUST be one of `windows | linux | macos | bsd | appliance | other`.
  - Values MUST be lowercase ASCII.
- `role` (string, optional): when present, MUST be one of
  `endpoint | server | domain_controller | network | sensor | other`.
  - Values MUST be lowercase ASCII.
  - When omitted, downstream stages MUST treat the role as `other` for defaults and reporting.
- `hostname` (string, optional): inventory host identifier or DNS hostname.
- `ip` (string, optional): management IP address literal (no port).
- `tags` (array of strings, optional)
- `vars` (object, optional): allowlisted connection hints:
  - allowed keys: `ansible_host`, `ansible_port`, `ansible_connection`, `ansible_user`,
    `ansible_shell_type`
  - `ansible_port`, when present, MUST be an integer in the range `1..65535`
- `provider_asset_ref` (string, optional)

Deterministic canonicalization (normative):

- `assets[]` MUST be sorted by `asset_id` using bytewise UTF-8 lexical ordering.
- If present, `tags[]` MUST be de-duplicated and sorted using bytewise UTF-8 lexical ordering.
  - Each tag MUST be a non-empty string and MUST NOT contain leading or trailing ASCII whitespace.
- If present, `vars` MUST be reduced to the allowlist above and MUST NOT contain secrets (see
  "Canonical intermediate model").
- If present, `ip` MUST be a syntactically valid IP address literal and MUST be serialized in
  canonical textual form:
  - IPv4: dotted-decimal with no leading zeros.
  - IPv6: RFC 5952 canonical form (lowercase hex, shortest form, `::` compression).
  - Bracketed addresses (`[::1]`), zone identifiers (`fe80::1%eth0`), and `host:port` strings MUST
    be rejected.
  - Invalid `ip` strings MUST cause the provider stage to fail closed.

Hashing and encoding (normative):

- The published `lab_inventory_snapshot.json` bytes MUST equal `canonical_json_bytes(snapshot)` as
  defined in the data contracts specification (RFC 8785 / JCS; UTF-8; no BOM; no trailing newline).
- `lab.inventory_snapshot_sha256` MUST be computed as `sha256(file_bytes)` over the published
  snapshot bytes and recorded in the run manifest as the authoritative inventory hash for downstream
  stages.
  - The recorded value MUST use the canonical SHA-256 digest string form defined in
    `025_data_contracts.md`: `sha256:<lowercase_hex>` (regex `^sha256:[0-9a-f]{64}$`).
  - Implementations MUST NOT emit raw hex (no `sha256:` prefix) for this field. Consumers MUST treat
    any value that does not match the regex above as invalid.

Contract validation:

- The published snapshot MUST be validated at the publish gate using the local contract registry
  (`docs/contracts/contract_registry.json`) as defined in the data contracts specification.
- The published snapshot MUST validate against the `lab_inventory_snapshot` contract
  (`docs/contracts/lab_inventory_snapshot.schema.json`).
- In addition to schema validation, implementations MUST validate the invariants above as a publish
  gate before atomically publishing the snapshot into the run bundle.

Retention semantics:

- The inventory snapshot is a reproducibility-critical, contract-backed run artifact.
- Even though the snapshot is stored under `logs/`, implementations MUST retain it for the full
  retention period of the run bundle and MUST NOT treat it as prunable debug logging.
- The run manifest MUST reference the snapshot path and hash as the authoritative inventory input
  for downstream stages.

### Canonical asset shape

Regardless of provider, assets are normalized to:

- `asset_id` (stable, Purple Axiom logical ID)
- `os` (required; one of `windows | linux | macos | bsd | appliance | other`)
- `role` (optional; one of `endpoint | server | domain_controller | network | sensor | other`)
  - When omitted, downstream stages MUST treat the role as `other`.
- optional `hostname` (inventory/DNS host identifier)
- optional `ip` (management IP address literal)
- optional `tags` (set-like array; de-duplicated + sorted in snapshots)
- optional `vars` (allowlisted connection hints; see "Canonical intermediate model")
- optional `provider_asset_ref` (provider-native ID, when meaningful)

### Asset identity and reassignment

Purple Axiom distinguishes between:

- `asset_id`: a Purple Axiom logical identifier that MUST remain stable across runs for a given
  range configuration.
- `provider_asset_ref`: a provider-native identifier (optional) that MAY change as a consequence of
  provider behavior (re-provisioning, ephemeral instance IDs, inventory regeneration).

Normative requirements:

- `asset_id` MUST NOT be derived from an ephemeral provider identifier (for example: cloud instance
  IDs, incremental inventory indexes, or dynamically allocated VM IDs).
- A provider implementation MUST resolve all targets to a stable `asset_id` namespace. This
  typically means one of:
  - the operator defines `lab.assets` (with stable `asset_id`) in `inputs/range.yaml`, and the
    provider enriches those entries with `hostname`, `ip`, and `provider_asset_ref`, or
  - the provider maintains an explicit, persisted mapping from provider-native identifiers to stable
    `asset_id` values.
- If a provider cannot produce stable `asset_id` values for the resolved targets, it MUST fail
  closed at run start (stage `lab_provider`) so downstream stages do not execute under a
  non-deterministic target namespace.

Reassignment semantics:

- If an operator reuses an existing `asset_id` to refer to a materially different host profile, this
  is treated as a range configuration change. The resulting `lab.inventory_snapshot_sha256` SHOULD
  be expected to change, and downstream regression comparisons that join on `target_asset_id` will
  no longer be semantically comparable unless explicitly opted into by the operator (future config
  surface).

## Provider contract

At run start, a provider implementation MUST:

1. Resolve inventory into canonical `lab.assets` (including any provider enrichment fields allowed
   by this spec).
1. Materialize `lab_inventory_snapshot.json` as the canonical run-scoped inventory artifact.
1. Write the snapshot into a staging location under the run bundle.
1. Validate the snapshot invariants and any available schema contract as a publish gate.
1. Atomically publish the snapshot to its final run bundle location.
1. Compute `lab.inventory_snapshot_sha256` over the published snapshot bytes (recorded as a
   `sha256:<lowercase_hex>` digest string).
1. Record provider identity, `inventory_source_ref` (when applicable), snapshot path, and the
   snapshot hash in the manifest.

Provider implementations MAY be:

- file-based (consume exported inventory)

API-based providers are RESERVED for v0.3+ (see "Reserved: API-based provider determinism
requirements (v0.3+)"). All implementations (including `lab.provider: manual`) MUST still validate
inputs and publish a deterministic snapshot for the run.

### Publish and validation gate

The lab provider stage MUST follow the staging and atomic publish semantics defined by
`ADR-0004-deployment-architecture-and-inter-component-communication.md` and the contract validation
requirements in `025_data_contracts.md`:

- Staging location MUST be under `.staging/lab_provider/`.
- The stage MUST validate the snapshot (schema where available via the contract registry, plus
  invariants in this spec) before publishing.
  - On contract validation failure, the stage MUST emit a deterministic contract validation report
    at `logs/contract_validation/lab_provider.json`.
- The stage MUST publish by atomic rename into the final run bundle location.
- On any fail-closed error, the stage MUST NOT partially populate the final snapshot path.

### Stage outcomes and failure classification

The lab provider stage MUST emit stage outcomes and reason codes as defined by
`ADR-0005-stage-outcomes-and-failure-classification.md`.

Fail-closed (`stage="lab_provider"`, `fail_mode="fail_closed"`) mappings:

- Missing inventory file, parse error, adapter failure, or other resolution failure MUST use
  `reason_code="inventory_resolution_failed"`.
- Inventory artifact does not conform to the declared `lab.inventory.format` (including invalid IP
  strings) MUST use `reason_code="invalid_inventory_format"`.
- Duplicate `asset_id` in the resolved `lab.assets` set MUST use `reason_code="asset_id_collision"`.
- API provider query errors or timeouts MUST use `reason_code="provider_api_error"` (reserved for
  v0.3+).
- Non-deterministic resolved `asset_id` set across retries within a single run start MUST use
  `reason_code="unstable_asset_id_resolution"`.

Non-fatal connectivity degradations MUST be recorded only as a substage
`stage="lab_provider.connectivity"` with `fail_mode="warn_and_skip"` and one of:

- `reason_code="partial_connectivity"`
- `reason_code="connectivity_check_error"`

Connectivity checks are optional for v0.1. When implemented:

- They MUST execute after the inventory snapshot is published (read-only).
- They MUST NOT affect `lab.inventory_snapshot_sha256` and MUST NOT modify the published inventory
  snapshot.
- They MAY include an "addressability" canary that warns when a resolved asset is missing a usable
  connection address (runner dependency):
  - An asset is "addressable" when at least one of `ip` or `hostname` is present in the published
    snapshot.
  - If any assets are not addressable, the substage MUST record `status="failed"`,
    `fail_mode="warn_and_skip"`, and `reason_code="partial_connectivity"`.
  - If the addressability canary itself cannot be evaluated deterministically, the substage MUST
    record `status="failed"`, `fail_mode="warn_and_skip"`, and
    `reason_code="connectivity_check_error"`.
  - Implementations SHOULD emit deterministic evidence for this canary under
    `logs/lab_provider_connectivity.json` (implementation-defined JSON; MUST NOT contain secrets).

### Reserved: API-based provider determinism requirements (v0.3+)

API-based providers are RESERVED for v0.3+.

For v0.1-v0.2, implementations MUST NOT query provider APIs as part of `lab_provider`. Inventory
resolution MUST consume a static, on-disk inventory artifact (`lab.inventory.path`) and then publish
a deterministic `lab_inventory_snapshot.json` into the run bundle.

When API-based providers are enabled in v0.3+, they MUST preserve run reproducibility:

- Providers MUST record a deterministic `inventory_source_ref` in the manifest (for example: API
  endpoint and query parameters), with all secrets redacted or omitted.
- Providers MUST use deterministic request parameters and ordering. Time-window dependent queries
  MUST be explicitly pinned by configuration; otherwise the provider MUST fail closed.
- If the provider performs retries, it MUST compare the resolved `asset_id` set across attempts. If
  the set differs, the provider MUST fail closed with `unstable_asset_id_resolution`.

## Configuration surface

Recommended minimal keys (aligned with [Configuration reference](120_config_reference.md)):

- `lab.provider` (optional; default `manual`): `manual | ludus | terraform | vagrant | other`
- `lab.assets` (required): stable target list; provider resolution enriches these entries.
- `lab.inventory.path` (required when `lab.provider != manual`): provider-exported inventory
  artifact.
- `lab.inventory.format` (optional; default `ansible_yaml`): `ansible_yaml | ansible_ini | json`
- `lab.inventory.refresh` (optional; default `on_run_start`; enum `never | on_run_start`):
  - `on_run_start`: the provider MUST resolve and snapshot inventory at run start from the
    configured inventory artifact(s). (API-based refresh is reserved for v0.3+.)
  - `never`: the provider MUST NOT mutate or refresh inventory sources; it MUST use the existing
    artifact at `lab.inventory.path` and still snapshot deterministically.
- `lab.inventory.snapshot_to_run_bundle` (optional; default `true`):
  - v0.1: MUST be `true`. If set `false`, the configuration MUST be rejected during config
    validation because downstream stages require the snapshot artifact for correctness.

## Inventory artifact formats and adapter rules

Purple Axiom consumes provider-exported inventory artifacts (`lab.inventory.*`) and converts them
into a canonical intermediate model prior to resolving the run-scoped `lab_inventory_snapshot.json`.

This section defines the minimum deterministic subset required for v0.1. Provider adapters MAY
support richer provider-native constructs, but any unsupported constructs MUST fail closed.

### Canonical intermediate model: `provider_inventory_canonical_v1`

The inventory adapter output MUST be a JSON object with:

- `v` (int) MUST be `1`.
- `hosts` (array) MUST be present and MUST contain at least one element.

Each `hosts[]` element MUST be an object with:

- `name` (string, required): inventory host identifier (opaque string; case-sensitive).
- `ip` (string, optional): management IP address literal (no port).
- `groups` (array of strings, optional): unique group names.
- `vars` (object, optional): allowlisted, non-secret connection metadata.

Allowlisted `vars` keys (all others MUST be ignored and MUST NOT affect resolution, hashing, or the
published snapshot):

- `ansible_host` (string): connection host (IP literal or hostname).
- `ansible_port` (int): connection port in range 1..65535.
- `ansible_connection` (string)
- `ansible_user` (string)
- `ansible_shell_type` (string)

Type normalization (normative):

- If `ansible_port` is provided as a string of ASCII digits, the adapter MUST parse it and store it
  as an integer. Any non-integer or out-of-range value MUST fail closed with
  `reason_code="invalid_inventory_format"`.
- Adapters MUST NOT attempt DNS resolution to derive `ip`. If `ansible_host` is an IP literal, the
  adapter MAY copy it into `ip` (after canonicalization); otherwise `ip` MUST remain unset unless
  the source inventory provides an IP literal via an implementation-defined, contract-backed
  extension.

Secret suppression (normative):

- Any `vars` key matching `(?i)(pass|password|token|secret|private|key)` MUST be dropped.
- If the adapter cannot determine whether a value is secret, it MUST drop the key.
- Adapters MUST NOT log raw inventory `vars{}` values. Logs MUST be redacted/summarized (for
  example, by reporting only allowlisted key names and hashes).

Canonicalization (normative):

- `hosts[]` MUST be sorted by `name` using bytewise UTF-8 lexical ordering.
- For each host, `groups[]` MUST be de-duplicated and sorted using bytewise UTF-8 lexical ordering.
- If present, `ip` MUST be a syntactically valid IP literal and MUST be serialized in canonical form
  (IPv4 dotted-decimal; IPv6 RFC 5952). Invalid `ip` strings MUST cause a fail-closed error.
- `vars` MUST be reduced to the allowlist, normalized as above, and then key-sorted for canonical
  JSON hashing.

### Input format: `json`

The input MUST be a JSON object compatible with static Ansible inventory exports, using:

- group objects with optional `hosts[]`, `children[]`, and `vars{}`
- `_meta.hostvars{}`

#### Terraform `terraform output -json` wrapper handling (normative)

Terraform marks sensitivity in configuration (for example: `output ... { sensitive = true }`) and
includes a per-output `sensitive` flag when rendering outputs in `terraform output -json`. Terraform
does not redact sensitive output values in this mode, so adapters MUST treat wrapper files as
hazardous inputs and MUST NOT log wrapper values.

Wrapper detection:

- If the top-level JSON object values all have keys `value`, `type`, and `sensitive`, the adapter
  MUST treat the input as a Terraform output wrapper and MUST unwrap a single selected output prior
  to applying the JSON inventory extraction rules.

Output selection:

- If the wrapper has exactly one top-level key, the adapter MUST select that output.
- Else, if the wrapper contains an output named `pa_inventory`, the adapter MUST select
  `pa_inventory`.
- Else, the adapter MUST fail closed with `reason_code="invalid_inventory_format"`.

Selected output safety:

- If the selected output has `sensitive: true`, the adapter MUST fail closed with
  `reason_code="invalid_inventory_format"`.
- The adapter MUST treat the selected output's `value` as the inventory object and then apply the
  JSON inventory extraction rules to that object.
- Any non-selected outputs in the wrapper MUST be ignored and MUST NOT affect resolution, hashing,
  or output artifacts. Non-selected output values MUST NOT appear in logs.

Adapter extraction rules:

1. Enumerate all host names as the union of:
   - keys of `_meta.hostvars`
   - all hostnames referenced by any group `hosts[]`
1. For each host:
   - `vars` is derived from `_meta.hostvars[host]` (if present) reduced to the allowlist.
   - If `vars.ansible_host` is present and is an IP literal, the adapter MUST set `ip` to that value
     after canonical IP serialization.
   - If `vars.ansible_host` is present and is not an IP literal (for example, it is a DNS hostname),
     the adapter MUST NOT populate `ip` from it.
1. Group membership:
   - A host is a member of group `G` if it appears in `G.hosts[]` or is reachable through
     `G.children[]` traversal.
   - Cycles in the `children[]` graph MUST be detected. On any cycle, the adapter MUST fail closed.

### Input format: `ansible_yaml`

The input MUST be a static Ansible YAML inventory using only the following fields:

- `hosts` (map)
- `children` (map)
- `vars` (map)

Adapters MUST produce the same `provider_inventory_canonical_v1` host list and group membership
semantics as the `json` format.

### Input format: `ansible_ini`

The input MUST be a static INI inventory using only:

- group sections: `[group]`
- children sections: `[group:children]`
- vars sections: `[group:vars]` and `[all:vars]`

Host variable precedence:

- `all:vars` merged first, then group vars, then host vars.
- When multiple groups apply to one host, group vars MUST be applied in bytewise UTF-8 lexical order
  by group name.

### Deterministic resolution into lab.assets

When `lab.provider != manual`, resolution MUST:

1. Build a host lookup map keyed by `hosts[].name`.
   - Duplicate `name` values MUST cause a fail-closed error.
1. For each `lab.assets[]` entry, select an inventory host by match key (matched against
   `hosts[].name`):
   - If `lab.assets[].hostname` is present: match on that value.
   - Else if `lab.assets[].provider_asset_ref` is present: match on that value.
   - Else: match on `lab.assets[].asset_id`.
1. Match key comparison MUST be an exact bytewise UTF-8 comparison.
   - Implementations MUST NOT apply locale-dependent casefolding.
   - Operators SHOULD normalize host identifiers to lowercase ASCII when using DNS hostnames.
1. The match MUST be exact and MUST yield exactly one host. Otherwise, fail closed.
1. Enrichment (deterministic, non-destructive):
   - If `lab.assets[].hostname` is unset, the resolved snapshot MUST set `hostname` to the matched
     inventory host `name`.
   - If `lab.assets[].ip` is unset and the matched inventory host has `ip`, the resolved snapshot
     MUST set `ip`.
   - If `lab.assets[].vars` is unset, the resolved snapshot MUST set `vars` to the matched inventory
     host `vars` (after allowlist + normalization + secret suppression).
   - If `lab.assets[].vars` is set, the provider MUST merge only missing allowlisted keys from the
     matched inventory host `vars` and MUST NOT override keys already specified by the operator.
   - Provider-native identifiers MAY be recorded in the snapshot as `provider_asset_ref`. Downstream
     stages MUST NOT require `provider_asset_ref` for deterministic joining (joins are on
     `asset_id`).

### Minimum conformance fixtures

Implementations MUST include fixtures that demonstrate deterministic adapter behavior:

- One inventory fixture per supported format (`json`, `ansible_yaml`, `ansible_ini`) representing
  the same logical host set (including groups and allowlisted `vars`).
- The fixtures MUST include at least:
  - one host with `ansible_port` expressed as a string in INI and as an integer in YAML/JSON,
    proving type normalization,
  - one host with an IPv6 management IP, proving canonical IPv6 serialization.
- A golden `lab_inventory_snapshot.json` produced from those fixtures.
- A golden `lab.inventory_snapshot_sha256` computed over the published snapshot bytes
  (`canonical_json_bytes(lab_inventory_snapshot.json)`), encoded as `sha256:<lowercase_hex>`.

## Ludus

Recommended approach:

- Treat Ludus as an upstream system of record.
- Consume a Ludus-exported inventory artifact using one of the supported `lab.inventory.format`
  adapters.
  - For v0.1, `json` is RECOMMENDED for determinism (see “Inventory artifact formats and adapter
    rules”).
- Map inventory entries to canonical `lab.assets` records.

Purple Axiom SHOULD NOT require Ludus APIs at runtime for the initial implementation.

## Terraform

Recommended approach:

- Prefer a post-apply export step that produces a static inventory artifact in one of the supported
  `lab.inventory.format` values (for example `json` or `ansible_yaml`). This mirrors common practice
  in comparable lab projects where Terraform provisions and a generated inventory drives downstream
  automation.
- Consume a pre-exported artifact:
  - RECOMMENDED: a generated inventory file produced by Terraform in one of the supported
    `lab.inventory.format` values.
  - Alternative: `terraform output -json pa_inventory` saved to disk, where `pa_inventory` is a
    non-sensitive output containing only inventory data (no secrets).
    - `terraform output -json` and `terraform output -raw` display sensitive outputs in plain text.
    - The `sensitive = true` marker is declared in Terraform configuration, but it is not a
      guarantee that values are redacted in machine-readable output.
- If a Terraform output wrapper is used, the `json` adapter MUST unwrap the selected output as
  specified in “Input format: `json`”.
- Map the selected inventory export to the canonical `lab.assets` model.

## Vagrant

Vagrant is supported as an optional reference provider for local developer ranges.

Recommended approach (mirrors the Terraform/Ludus model):

- Treat Vagrant as an upstream provisioning tool (outside Purple Axiom).
- Export a static inventory artifact in one of the supported `lab.inventory.format` values and feed
  that artifact into the pipeline.
  - For v0.1, `json` is RECOMMENDED for determinism (see “Inventory artifact formats and adapter
    rules”).
- Map inventory entries to canonical `lab.assets` records.

Determinism and safety notes (normative where stated):

- The exported inventory artifact MUST NOT contain secrets (no passwords, tokens, private keys).
- To reduce inventory drift, management addressing SHOULD be stable (static IPs or stable DNS)
  rather than ephemeral NAT-forwarded ports.
- A RECOMMENDED joining strategy is:
  - Prefer joining on the stable Vagrant machine name via `provider_asset_ref`:
    - `lab.assets[].provider_asset_ref = <vagrant_machine_name>` (exact match to the exported
      inventory host identifier)
    - omit `lab.assets[].hostname` unless the exported inventory host identifier differs from the
      machine name (in which case set `hostname` explicitly)
    - `lab.assets[].asset_id = slugify(<vagrant_machine_name>)`, where `slugify(...)` MUST produce a
      valid `id_slug_v1` value as defined in
      [ADR-0001: Project naming and versioning](../adr/ADR-0001-project-naming-and-versioning.md).
  - Because deterministic resolution matches `hostname` → `provider_asset_ref` → `asset_id`, this
    makes `provider_asset_ref` operationally meaningful for Vagrant ranges while keeping `asset_id`
    stable and human-readable.

Reference implementation (optional):

- TODO: provide a small “vagrant inventory exporter” that emits the canonical JSON inventory format
  (including stable ordering) from a maintained machine map, so teams can stand up a range quickly.

## Manual

- Inline `lab.assets` in `inputs/range.yaml`.
- No external dependencies.

## Security requirements

- Provider credentials are secrets and MUST be referenced, not embedded.
- Inventory sources and snapshots MUST NOT contain secrets (no passwords, tokens, private keys).
  - Providers/adapters MUST apply allowlists and secret suppression to any propagated `vars` fields.
- Providers/adapters MUST treat inventory inputs as sensitive and MUST NOT log raw inventory content
  (including Terraform output wrappers). Logs MUST contain only redacted summaries and hashes.
- Default posture MUST be inventory resolution only. Provisioning, mutation, or teardown actions
  MUST be explicitly enabled and logged.
- Outbound egress posture enforcement:
  - The effective outbound policy is
    `scenario.safety.allow_network AND security.network.allow_outbound`.
  - When the effective outbound policy is deny, enforcement MUST be performed at the lab boundary by
    the lab provider or equivalent lab controls (the runner is not sufficient).

## References

- [Configuration reference](120_config_reference.md)
- [Data contracts](025_data_contracts.md)
- [ADR-0004: Deployment architecture and inter-component communication](ADR-0004-deployment-architecture-and-inter-component-communication.md)
- [ADR-0005: Stage outcomes and failure classification](ADR-0005-stage-outcomes-and-failure-classification.md)

## Changelog

| Date       | Change                                                                                                        |
| ---------- | ------------------------------------------------------------------------------------------------------------- |
| 2026-01-24 | Align match-key precedence; reserve API providers for v0.3+; align config defaults; add addressability canary |
| 2026-01-22 | Add optional Vagrant provider reference workflow                                                              |
| 2026-01-19 | Add `vars` to inventory snapshot; align enums + hashing/encoding; clarify publish + security                  |
