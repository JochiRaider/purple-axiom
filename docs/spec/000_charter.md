<!-- docs/spec/000_charter.md -->

# Project Charter: Continuous Purple-Team Range

## Summary

A local-first cyber range that continuously runs safe adversary-emulation scenarios, collects
telemetry, normalizes events into OCSF, evaluates detections (Sigma), and produces reproducible
scorecards.

## Motivation

- Replace ad-hoc “run a test, eyeball logs” workflows with repeatable ground-truth runs and
  measurable detection outcomes.
- Enable regression testing for detections, telemetry pipelines, and schema mappings.

## Primary outcomes (MVP)

- Deterministic scenario execution logs (ground truth timeline).
- Telemetry pipeline producing normalized OCSF events.
- Rule evaluation producing technique-level detection results.
- Human-readable report + machine-readable JSON artifact.

## Users

- Detection engineers
- SOC analysts validating visibility/detections
- Purple teams / continuous security testing operators

## Key upstream dependencies (normative)

- Caldera for automated emulation (or pluggable runner) (ref: Caldera docs).
- Atomic Red Team test library (optional but recommended).
- OpenTelemetry Collector pipeline for logs.
- OCSF schema as the canonical normalized event model.
- Sigma rules for detection portability.

## Definitions of done

- One-click run: scenario → telemetry → normalize → score → report.
- Re-run produces identical outputs given same inputs (or clearly documented sources of
  nondeterminism).
