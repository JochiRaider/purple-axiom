# Scope and Non-Goals

## In-scope
- Scenario execution orchestration (Caldera and/or Atomic runner).
- Telemetry collection from lab assets (endpoint + optional network sensors).
- Normalization to OCSF.
- Rule evaluation and scoring.
- Reporting and trend tracking.
- Pluggable lab inventory resolution via a Lab Provider interface (manual first, Ludus next, Terraform later).
- Capturing a deterministic “lab inventory snapshot” per run for reproducibility and diffability.

## Explicit non-goals (initially)
- Exploit development, weaponization, or destructive testing.
- Production deployment guidance for hostile environments.
- “Full SIEM replacement.” The range produces artifacts; external SIEM ingestion is optional.
- A full-featured lab provisioning platform. Purple Axiom integrates with external lab providers; it does not replace them.
- Coupling the project to a single lab provider or a single inventory format.

## Operating assumptions
- Runs occur in an isolated lab environment.
- Tests emphasize detectability validation, not stealth/permanence.
- All components are run with least privilege.
- Lab assets may be provisioned out-of-band (Ludus, Terraform, manual), but Purple Axiom records the resolved inventory used for each run.