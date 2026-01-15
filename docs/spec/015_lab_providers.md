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

## Purpose

Define a pluggable interface for resolving lab assets without coupling Purple Axiom to any single
provisioning system.

Purple Axiom uses the resolved asset list (`lab.assets`) as the canonical shape for orchestration,
telemetry correlation, scoring, and reporting.

## Goals

- Support multiple lab providers:
  - manual (inline inventory)
  - Ludus (Proxmox-backed provisioning, consume exported inventory)
  - Terraform (cloud/local provisioning, consume exported outputs)
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

Recommended path:

- `runs/<run_id>/logs/lab_inventory_snapshot.json`

#### Inventory snapshot schema: `lab_inventory_snapshot_v1`

The inventory snapshot artifact (`lab_inventory_snapshot.json`) MUST be a JSON object with:

- `v` (int, required): MUST be `1`.
- `assets` (array, required): MUST contain at least one element.

Each `assets[]` element MUST conform to the canonical asset shape defined by this spec:

- `asset_id` (string, required)
- `os` (string, required)
- `role` (string, required)
- `hostname` (string, optional)
- `ip` (string, optional)
- `tags` (array of strings, optional)
- `provider_asset_ref` (string, optional)

Deterministic canonicalization (normative):

- `assets[]` MUST be sorted by `asset_id` using bytewise UTF-8 lexical ordering.
- If present, `tags[]` MUST be de-duplicated and sorted using bytewise UTF-8 lexical ordering.
- If present, `ip` MUST be a syntactically valid IP address and MUST be serialized in canonical
  textual form (IPv4 dotted-decimal; IPv6 lowercase compressed). Invalid IP strings MUST cause the
  provider stage to fail closed.

Hashing (normative):

- `inventory_snapshot_sha256` MUST be computed as `sha256(canonical_json_bytes(snapshot))` and
  recorded in the manifest.
- Canonical JSON bytes MUST use RFC 8785 (JCS) canonicalization.

Contract validation:

- The published `lab_inventory_snapshot.json` SHOULD be validated against a JSON Schema contract at
  `docs/contracts/lab_inventory_snapshot.schema.json` (TODO: define).
- Regardless of schema availability, implementations MUST validate the invariants above as a publish
  gate before atomically publishing the snapshot into the run bundle.

Retention semantics:

- The inventory snapshot is a reproducibility-critical, contract-backed run artifact. Even though
  the recommended path is under `runs/<run_id>/logs/`, it MUST be retained for the full retention
  period of the run bundle and MUST be referenced by the run manifest as the authoritative inventory
  input for downstream stages.

### Canonical asset shape

Regardless of provider, assets are normalized to:

- `asset_id` (stable, Purple Axiom logical ID)
- `os`
- `role`
- optional `hostname`
- optional `ip`
- optional `tags`
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
  - the operator defines `lab.assets` (with stable `asset_id`) in `range.yaml`, and the provider
    enriches those entries with `hostname`, `ip`, and `provider_asset_ref`, or
  - the provider maintains an explicit, persisted mapping from provider-native identifiers to stable
    `asset_id` values.
- If a provider cannot produce stable `asset_id` values for the resolved targets, it MUST fail
  closed at run start and MUST NOT emit `ground_truth.jsonl` because cross-run joins would be
  non-deterministic.

Reassignment semantics:

- If an operator reuses an existing `asset_id` to refer to a materially different host profile, this
  is treated as a range configuration change. The resulting `inventory_snapshot_sha256` SHOULD be
  expected to change, and downstream regression comparisons that join on `target_asset_id` will no
  longer be semantically comparable unless explicitly opted into by the operator (future config
  surface).

## Provider contract

At run start, a provider implementation MUST:

1. Resolve inventory into canonical `lab.assets`.
1. Write `lab_inventory_snapshot.json` into a staging location under the run bundle.
1. Validate the snapshot invariants and any available schema contract as a publish gate.
1. Atomically publish the snapshot to its final run bundle location.
1. Compute `inventory_snapshot_sha256` over the published snapshot.
1. Record provider identity, snapshot path, and the snapshot hash in the manifest.

Provider implementations MAY be:

- file-based (consume exported inventory)
- API-based (query provider)

All implementations MUST still write a deterministic snapshot for the run.

### Publish and validation gate

The lab provider stage MUST follow the staging and atomic publish semantics defined by
`ADR-0004-deployment-architecture-and-inter-component-communication.md` and the contract validation
requirements in `025_data_contracts.md`:

- Staging location MUST be under `runs/<run_id>/.staging/lab_provider/`.
- The stage MUST validate the snapshot (schema where applicable, plus invariants in this spec)
  before publishing.
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
- API provider query errors or timeouts MUST use `reason_code="provider_api_error"`.
- Non-deterministic resolved `asset_id` set across retries within a single run start MUST use
  `reason_code="unstable_asset_id_resolution"`.

Non-fatal connectivity degradations MUST be recorded only as a substage
`stage="lab_provider.connectivity"` with `fail_mode="warn_and_skip"` and one of:

- `reason_code="partial_connectivity"`
- `reason_code="connectivity_check_error"`

Connectivity checks are optional for v0.1. When implemented, they MUST NOT affect
`inventory_snapshot_sha256` and MUST NOT modify the published inventory snapshot.

### API-based provider determinism requirements

API-based providers are permitted, but they MUST preserve run reproducibility:

- Providers MUST record a deterministic `inventory_source_ref` in the manifest (for example: API
  endpoint and query parameters), with all secrets redacted or omitted.
- Providers MUST use deterministic request parameters and ordering. Time-window dependent queries
  MUST be explicitly pinned by configuration; otherwise the provider MUST fail closed.
- If the provider performs retries, it MUST compare the resolved `asset_id` set across attempts. If
  the set differs, the provider MUST fail closed with `unstable_asset_id_resolution`.

## Configuration surface

Recommended minimal keys (see [Configuration reference](120_config_reference.md)):

- `lab.provider`
- `lab.inventory.path`
- `lab.inventory.format`
- `lab.inventory.refresh`
- `lab.inventory.snapshot_to_run_bundle`

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

- `name` (string, required): inventory host identifier.
- `ip` (string, optional): resolved management IP.
- `groups` (array of strings, optional): unique group names.
- `vars` (object, optional): allowlisted, non-secret connection metadata.

Allowlisted `vars` keys (all others MUST be ignored and MUST NOT affect resolution or hashing):

- `ansible_host`
- `ansible_port`
- `ansible_connection`
- `ansible_user`
- `ansible_shell_type`

Secret suppression:

- Any `vars` key matching `(?i)(pass|password|token|secret|private|key)` MUST be dropped.
- If the adapter cannot determine whether a value is secret, it MUST drop the key.

Canonicalization:

- `hosts[]` MUST be sorted by `name` using bytewise UTF-8 lexical ordering.
- For each host, `groups[]` MUST be de-duplicated and sorted using bytewise UTF-8 lexical ordering.
- `vars` MUST be reduced to the allowlist and then key-sorted for canonical JSON hashing.

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
   - `ip` MUST be set to `vars.ansible_host` when present.
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

### Deterministic resolution into `lab.assets`

When `lab.provider != manual`, resolution MUST:

1. Build a host lookup map keyed by `hosts[].name`.
   - Duplicate `name` values MUST cause a fail-closed error.
1. For each `lab.assets[]` entry, select an inventory host by match key:
   - If `lab.assets[].hostname` is present: match on that value.
   - Else: match on `lab.assets[].asset_id`.
1. Match key comparison MUST be an exact bytewise UTF-8 comparison.
   - Implementations MUST NOT apply locale-dependent casefolding.
   - Operators SHOULD normalize host identifiers to lowercase ASCII when using DNS hostnames.
1. The match MUST be exact and MUST yield exactly one host. Otherwise, fail closed.
1. Enrichment:
   - If `lab.assets[].ip` is unset and the matched inventory host has `ip`, the resolved snapshot
     MUST set `ip`.
   - Provider-native identifiers MAY be recorded in the snapshot as `provider_asset_ref`, but MUST
     NOT be required for deterministic joining.

### Minimum conformance fixtures

Implementations MUST include fixtures that demonstrate deterministic adapter behavior:

- One inventory fixture per supported format (`json`, `ansible_yaml`, `ansible_ini`) representing
  the same host set.
- A golden `lab_inventory_snapshot.json` produced from those fixtures.
- A golden `inventory_snapshot_sha256` computed over
  `canonical_json_bytes(lab_inventory_snapshot.json)`.

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

## Manual

- Inline `lab.assets` in `range.yaml`.
- No external dependencies.

## Security requirements

- Provider credentials are secrets and MUST be referenced, not embedded.
- Inventory snapshots MUST NOT contain secrets (no passwords, tokens, private keys).
- Provider operations that mutate infrastructure MUST be explicitly enabled and logged.

## References

- [Configuration reference](120_config_reference.md)
- [Data contracts](025_data_contracts.md)
- [ADR-0004: Deployment architecture and inter-component communication](ADR-0004-deployment-architecture-and-inter-component-communication.md)
- [ADR-0005: Stage outcomes and failure classification](ADR-0005-stage-outcomes-and-failure-classification.md)

## Changelog

| Date       | Change                                                        |
| ---------- | ------------------------------------------------------------- |
| 2026-01-14 | Align outcomes, publish gates, and snapshot determinism rules |
| 2026-01-12 | Formatting update                                             |
