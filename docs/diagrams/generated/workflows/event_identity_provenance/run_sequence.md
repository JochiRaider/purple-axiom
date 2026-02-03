# Run sequence — Event identity and provenance (deterministic join keys) (event_identity_provenance)

```mermaid
sequenceDiagram
  participant telemetry as "Telemetry Stage"
  participant normalization as "Normalization Stage"
  participant run_bundle_store as "Run Bundle Store"
  telemetry->>normalization: 1. hand off raw_parquet records to the normalizer; if an ingest_id is present, treat it as a volatile, debug-only ingestion-attempt identifier (never used for joins)
  normalization->>normalization: 2. determine metadata.identity_tier and construct identity_basis (identity-family discriminator + tier-specific stable fields); set metadata.source_event_id (null for tier 3)
  normalization->>normalization: 3. compute metadata.event_id deterministically from identity_basis using RFC 8785 canonical JSON and SHA-256 (v1); set metadata.uid = metadata.event_id
  normalization->>run_bundle_store: 4. publish normalized/** with event provenance surfaces (event_id, uid, identity_tier, source_event_id) and embedded identity_basis (and identity_source_type); include ingest_id only if explicitly enabled
  normalization->>run_bundle_store: 5. enforce within-run deduplication of normalized events keyed by metadata.event_id; persist durable dedupe index; detect non-identical duplicates after volatile field removal and record minimal conflict evidence
  normalization->>normalization: 6. ensure reproducibility across marker-blind modes by excluding rendered strings from metadata.event_id computation
```
