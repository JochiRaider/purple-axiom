# Scope and Non-Goals

## In-scope
- Scenario execution orchestration (Caldera and/or Atomic runner).
- Telemetry collection from lab assets (endpoint + optional network sensors).
- Normalization to OCSF.
- Rule evaluation and scoring.
- Reporting and trend tracking.

## Explicit non-goals (initially)
- Exploit development, weaponization, or destructive testing.
- Production deployment guidance for hostile environments.
- “Full SIEM replacement.” The range produces artifacts; external SIEM ingestion is optional.

## Operating assumptions
- Runs occur in an isolated lab environment.
- Tests emphasize detectability validation, not stealth/permanence.
- All components are run with least privilege.
