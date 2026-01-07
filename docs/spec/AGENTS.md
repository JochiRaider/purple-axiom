<!-- docs/spec/AGENTS.md -->
# Agent instructions (docs/spec/*)

## Primary objective: keep the working set small (performance)
- DO NOT brute-force read every spec file. Use a navigation-first workflow:
  1) Read `docs/spec/SPEC_INDEX.md` (one-page map) to choose the right spec file.
  2) Use repo search (ripgrep or equivalent) to jump to the exact section/header.
  3) Only open the minimum section(s) required to answer/edit.

## Spec-only navigation fast paths (docs/spec/*)
- Project mission, vocabulary, non-goals → `000_charter.md`, `010_scope.md`
- End-to-end pipeline boundaries / stage responsibilities → `020_architecture.md`
- Run bundle artifacts + invariants across artifacts → `025_data_contracts.md`
- Scenario authoring + stable action identity expectations → `030_scenarios.md`
- Criteria evaluation + cleanup verification model → `035_validation_criteria.md`
- Telemetry collection invariants → `040_telemetry_pipeline.md`, `042_osquery_integration.md`
- Storage layout + schema evolution expectations → `045_storage_formats.md`
- OCSF normalization rules + field mapping expectations → `050_normalization_ocsf.md`, `055_ocsf_field_tiers.md`
- Detection representation + Sigma semantics → `060_detection_sigma.md`
- Sigma→OCSF bridge behavior + outputs → `065_sigma_to_ocsf_bridge.md`
- Scoring + coverage metrics and gates → `070_scoring_metrics.md`
- Reporting artifacts + operator-facing outputs → `080_reporting.md`
- Security/safety posture and redaction-related requirements (spec-level) → `090_security_safety.md`
- CI strategy + fixtures + conformance gates → `100_test_strategy_ci.md`
- Operability / run-time concerns / knobs → `110_operability.md`
- Configuration keys, defaults, and config surface → `120_config_reference.md`

## Navigation scaffold (required)
- Maintain `docs/spec/SPEC_INDEX.md` as a **one-page map** covering **all** spec files in this directory.
- When you add a new MUST/MUST NOT or introduce a new concept:
  - Update `docs/spec/SPEC_INDEX.md` to point to the authoritative spec file.
  - Use linking to an existing section rather than duplicating prose in the index.

## Primary objective: keep the working set small (performance)
- Treat `docs/spec/` as the normative source, but DO NOT brute-force read every spec file.
- Use a **navigation-first** workflow:
  1) Read `docs/spec/SPEC_INDEX.md` (one-page map) to choose the correct authority file.
  2) Use repo search (ripgrep or equivalent) to jump to the exact section/header.
  3) Only open the minimum section(s) required to answer/edit.

## Spec navigation fast paths (read the minimum authoritative doc)
- Pipeline overview / stage boundaries → `020_architecture.md`
- Run bundle layout, artifact purposes, cross-artifact invariants → `025_data_contracts.md`
- Telemetry collection invariants (OTel, raw Windows event collection) → `040_telemetry_pipeline.md` (details/fixtures may live in `042_osquery_integration.md`)
- Criteria semantics + cleanup verification model → `035_validation_criteria.md`
- Sigma detection model + bridge backend requirements → `060_detection_sigma.md` + `065_sigma_to_ocsf_bridge.md`
- CI gates, fixture expectations, “golden run” requirements → `100_test_strategy_ci.md`
- Operator-facing outputs and bundle/report expectations → `080_reporting.md`

## Evidence-gated edits
- If you cannot verify a fact in-repo/specs, mark it “TBD / Needs Confirmation” rather than hallucinating it.

## Normative language discipline
- Use RFC-style modals consistently: MUST / MUST NOT / SHOULD / SHOULD NOT / MAY.
- Every new MUST/MUST NOT must include:
  - scope,
  - observable behavior,
  - how to verify (fixture/test/acceptance criteria).

## Determinism first
- Prefer deterministic identifiers, canonicalization rules, explicit ordering, and stable serialization.
- Where hashing/IDs are involved, follow the project’s canonical JSON requirements (RFC 8785 / JCS) and identity rules.

## Cross-spec consistency (docs-only)
- You MAY update other docs (including README) when required to keep the spec set internally consistent.