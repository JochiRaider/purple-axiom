---
title: 'Project charter: Continuous purple-team range'
description: Defines Purple Axiom’s mission, MVP outcomes, intended users, normative dependencies, and definition of done.
status: draft
category: spec
tags: [charter, scope]
---

# Project charter: Continuous purple-team range

## Summary

A local-first cyber range that continuously runs safe adversary-emulation scenarios, collects
telemetry, normalizes events into OCSF, evaluates detections (Sigma), and produces reproducible
scorecards.

## Motivation

- Replace ad-hoc “run a test, eyeball logs” workflows with repeatable ground-truth runs and
  measurable detection outcomes.
- Enable regression testing for detections, telemetry pipelines, and schema mappings.

## Primary outcomes

MVP outcomes:

- Deterministic scenario execution logs (ground truth timeline).
- Telemetry pipeline producing normalized OCSF events.
- Rule evaluation producing technique-level detection results.
- Human-readable report and a machine-readable JSON artifact.

## Users

- Detection engineers
- SOC analysts validating visibility and detections
- Purple teams and continuous security testing operators

## Key upstream dependencies

Normative:

- Atomic Red Team test library (optional but recommended).
- OpenTelemetry Collector pipeline for logs.
- OCSF schema as the canonical normalized event model.
- Sigma rules for detection portability.

## Definition of done

- One-click run: scenario → telemetry → normalize → score → report.
- A re-run MUST produce identical outputs given the same inputs, or MUST clearly document sources of
  nondeterminism.

## References

- TBD / Needs Confirmation.

## Changelog

| Date       | Change            |
| ---------- | ----------------- |
| 2026-01-12 | Formatting update |
