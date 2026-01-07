<!-- docs/spec/015_lab_providers.md -->
# Lab Providers and Inventory Resolution

## Purpose
Define a pluggable interface for resolving lab assets without coupling Purple Axiom to any single provisioning system.

Purple Axiom uses the resolved asset list (`lab.assets`) as the canonical shape for orchestration, telemetry correlation, scoring, and reporting.

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
A canonical JSON snapshot written into the run bundle so the run is reproducible even if the provider state changes later.

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

- `asset_id`: a **Purple Axiom logical identifier** that MUST remain stable across runs for a given range configuration.
- `provider_asset_ref`: a **provider-native identifier** (optional) that MAY change as a consequence of provider behavior
  (re-provisioning, ephemeral instance IDs, inventory regeneration).

Normative requirements:

- `asset_id` MUST NOT be derived from an ephemeral provider identifier (for example: cloud instance IDs, incremental
  inventory indexes, or dynamically allocated VM IDs).
- A provider implementation MUST resolve all targets to a stable `asset_id` namespace. This typically means one of:
  - the operator defines `lab.assets` (with stable `asset_id`) in `range.yaml`, and the provider enriches those entries
    with `hostname`/`ip`/`provider_asset_ref`, or
  - the provider maintains an explicit, persisted mapping from provider-native identifiers to stable `asset_id`s.
- If a provider cannot produce stable `asset_id`s for the resolved targets, it MUST fail closed at run start and MUST
  NOT emit `ground_truth.jsonl` (because cross-run joins would be non-deterministic).

Reassignment semantics (important for regression):

- If an operator reuses an existing `asset_id` to refer to a materially different host profile, this is treated as a
  **range configuration change**. The resulting `inventory_snapshot_sha256` SHOULD be expected to change, and downstream
  regression comparisons that join on `target_asset_id` will no longer be semantically comparable unless explicitly
  opted into by the operator (future config surface).

## Provider contract (conceptual)
At run start:
1. Resolve inventory into canonical `lab.assets`
2. Write `lab_inventory_snapshot.json`
3. Compute `inventory_snapshot_sha256`
4. Record provider identity and snapshot hash in the manifest

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

## Ludus (first implementation)
Recommended approach:
- Treat Ludus as an upstream system of record.
- Consume Ludus-exported inventory artifacts (for example, an Ansible inventory file).
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