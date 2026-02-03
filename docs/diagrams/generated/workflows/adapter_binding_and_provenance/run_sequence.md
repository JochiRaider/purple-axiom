# Run sequence — Adapter binding + provenance recording (adapter_binding_and_provenance)

```mermaid
sequenceDiagram
  participant orchestrator_cli as "Orchestrator CLI"
  participant adapter_registry as "adapter_registry"
  participant adapter_source as "adapter_source"
  participant signature_verifier as "signature_verifier"
  participant run_bundle_store as "Run Bundle Store"
  orchestrator_cli->>adapter_registry: 1. resolve adapter per port_id (deterministic binding via registry; reject unknown/disallowed adapters)
  orchestrator_cli->>adapter_source: 2. compute/verify adapter source_ref + source_digest (digest-pinned refs; hash_basis_v1 for local_path)
  orchestrator_cli->>signature_verifier: 3. (optional) verify adapter signature when required by policy snapshot
  orchestrator_cli->>run_bundle_store: 4. record manifest.extensions.adapter_provenance.entries[] deterministically (sanitize; optional config_sha256; stable sort)
  orchestrator_cli->>run_bundle_store: 5. on nondeterministic provenance, fail closed and record a deterministic stage/substage outcome
```
