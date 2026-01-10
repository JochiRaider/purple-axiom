<!-- docs/spec/015_lab_providers.md -->

# Lab Providers and Inventory Resolution

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

### Lab Provider

A component that can resolve a concrete set of targets from an external inventory source.

### Inventory snapshot

A canonical JSON snapshot written into the run bundle so the run is reproducible even if the
provider state changes later.

Recommended path:

- `runs/<run_id>/logs/lab_inventory_snapshot.json`

### Canonical asset shape

Regardless of provider, assets are normalized to:

- `asset_id` (stable, Purple Axiom logical ID)
- `os`, `role`
- optional `hostname`, `ip`, `tags`
- optional `provider_asset_ref` (provider-native ID, when meaningful)

### Asset identity and reassignment (determinism requirements)

Purple Axiom distinguishes between:

- `asset_id`: a **Purple Axiom logical identifier** that MUST remain stable across runs for a given
  range configuration.
- `provider_asset_ref`: a **provider-native identifier** (optional) that MAY change as a consequence
  of provider behavior (re-provisioning, ephemeral instance IDs, inventory regeneration).

Normative requirements:

- `asset_id` MUST NOT be derived from an ephemeral provider identifier (for example: cloud instance
  IDs, incremental inventory indexes, or dynamically allocated VM IDs).
- A provider implementation MUST resolve all targets to a stable `asset_id` namespace. This
  typically means one of:
  - the operator defines `lab.assets` (with stable `asset_id`) in `range.yaml`, and the provider
    enriches those entries with `hostname`/`ip`/`provider_asset_ref`, or
  - the provider maintains an explicit, persisted mapping from provider-native identifiers to stable
    `asset_id`s.
- If a provider cannot produce stable `asset_id`s for the resolved targets, it MUST fail closed at
  run start and MUST NOT emit `ground_truth.jsonl` (because cross-run joins would be
  non-deterministic).

Reassignment semantics (important for regression):

- If an operator reuses an existing `asset_id` to refer to a materially different host profile, this
  is treated as a **range configuration change**. The resulting `inventory_snapshot_sha256` SHOULD
  be expected to change, and downstream regression comparisons that join on `target_asset_id` will
  no longer be semantically comparable unless explicitly opted into by the operator (future config
  surface).

## Provider contract (conceptual)

At run start:

1. Resolve inventory into canonical `lab.assets`
1. Write `lab_inventory_snapshot.json`
1. Compute `inventory_snapshot_sha256`
1. Record provider identity and snapshot hash in the manifest

Provider implementations may be:

- file-based (consume exported inventory)
- API-based (query provider), but must still write a deterministic snapshot for the run

## Configuration surface

Recommended minimal keys (see `120_config_reference.md`):

- `lab.provider`
- `lab.inventory.path`
- `lab.inventory.format`
- `lab.inventory.refresh`
- `lab.inventory.snapshot_to_run_bundle`

## Inventory artifact formats and adapter rules (normative)

Purple Axiom consumes provider-exported inventory artifacts (`lab.inventory.*`) and converts them
into a canonical intermediate model prior to resolving the run-scoped `lab_inventory_snapshot.json`.

This section defines the *minimum*, deterministic subset required for v0.1. Provider adapters MAY
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

Canonicalization (normative):

- `hosts[]` MUST be sorted by `name` using bytewise UTF-8 lexical ordering.
- For each host, `groups[]` MUST be de-duplicated and sorted using bytewise UTF-8 lexical ordering.
- `vars` MUST be reduced to the allowlist and then key-sorted for canonical JSON hashing.

### Input format: `json` (Ansible inventory JSON, static subset)

The input MUST be a JSON object compatible with static Ansible inventory exports, using:

- group objects with optional `hosts[]`, `children[]`, and `vars{}`
- `_meta.hostvars{}`

Adapter extraction rules (normative):

1. Enumerate all host names as the union of:
   - keys of `_meta.hostvars`, and
   - all hostnames referenced by any group `hosts[]`.
1. For each host:
   - `vars` is derived from `_meta.hostvars[host]` (if present) reduced to the allowlist.
   - `ip` MUST be set to `vars.ansible_host` when present.
1. Group membership:
   - A host is a member of group `G` if it appears in `G.hosts[]` OR is reachable through
     `G.children[]` traversal.
   - Cycles in the `children[]` graph MUST be detected; on any cycle, the adapter MUST fail closed.

### Input format: `ansible_yaml` (static subset)

The input MUST be a static Ansible YAML inventory using only the following fields:

- `hosts` (map)
- `children` (map)
- `vars` (map)

Adapters MUST produce the same `provider_inventory_canonical_v1` host list and group membership
semantics as the `json` format.

### Input format: `ansible_ini` (static subset)

The input MUST be a static INI inventory using only:

- group sections: `[group]`
- children sections: `[group:children]`
- vars sections: `[group:vars]` and `[all:vars]`

Host variable precedence (normative):

- `all:vars` merged first, then group vars, then host vars.
- When multiple groups apply to one host, group vars MUST be applied in bytewise UTF-8 lexical order
  by group name.

### Deterministic resolution into `lab.assets` (minimum requirements)

When `lab.provider != manual`, resolution MUST:

1. Build a host lookup map keyed by `hosts[].name`.
   - Duplicate `name` values MUST cause a fail-closed error.
1. For each `lab.assets[]` entry, select an inventory host by match key:
   - If `lab.assets[].hostname` is present: match on that value.
   - Else: match on `lab.assets[].asset_id`.
   - The match MUST be exact and MUST yield exactly one host; otherwise, fail closed.
1. Enrichment:
   - If `lab.assets[].ip` is unset and the matched inventory host has `ip`, the resolved snapshot
     MUST set `ip`.
   - Provider-native identifiers MAY be recorded in the snapshot as `provider_asset_ref`, but MUST
     NOT be required for deterministic joining.

### Minimum conformance fixtures (normative intent)

Implementations MUST include fixtures that demonstrate deterministic adapter behavior:

- One inventory fixture per supported format (`json`, `ansible_yaml`, `ansible_ini`) representing
  the same host set.
- A golden `lab_inventory_snapshot.json` produced from those fixtures.
- A golden `inventory_snapshot_sha256` computed over
  `canonical_json_bytes(lab_inventory_snapshot.json)`.

## Ludus (first implementation)

Recommended approach:

- Treat Ludus as an upstream system of record.
- Consume a Ludus-exported inventory artifact using one of the supported `lab.inventory.format`
  adapters.
  - For v0.1, `json` is RECOMMENDED for determinism (see "Inventory artifact formats and adapter
    rules").
- Map inventory entries to canonical `lab.assets` records.

Purple Axiom should not require Ludus APIs at runtime for the initial implementation.

## Terraform (future implementation)

Recommended approach:

- Consume a pre-exported artifact:
  - `terraform output -json` saved to disk, or
  - a generated inventory file produced by Terraform
- Map outputs to canonical `lab.assets`.

## Manual (fallback)

- Inline `lab.assets` in `range.yaml`.
- No external dependencies.

## Security requirements

- Provider credentials are secrets and must be referenced, not embedded.
- Inventory snapshots must not contain secrets (no passwords, tokens, private keys).
- Provider operations that mutate infrastructure must be explicitly enabled and logged.
