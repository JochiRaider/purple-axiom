# Purple Axiom

**Ground-truth detection engineering through continuous adversary emulation**

Purple Axiom is a local-first cyber range that continuously runs safe adversary-emulation scenarios, collects telemetry, normalizes it to open standards, and scores your detections with reproducible reports.

## Core Philosophy

Treat detections as the theorems you're trying to prove, and adversary emulation as the axioms (ground truth) you build upon.

## Architecture

```
┌─────────────────┐
│  Orchestrator   │  ← Caldera + Atomic Red Team
└────────┬────────┘
         │ ground-truth timeline
         ▼
┌─────────────────┐
│   Telemetry     │  ← OTel Collector + osquery
└────────┬────────┘
         │ raw events
         ▼
┌─────────────────┐
│   Normalizer    │  ← Transform to OCSF
└────────┬────────┘
         │ normalized events
         ▼
┌─────────────────┐
│   Evaluator     │  ← Sigma rules → scoring
└────────┬────────┘
         │ detection results
         ▼
┌─────────────────┐
│    Reporter     │  ← HTML/JSON artifacts
└─────────────────┘
```

## Quick Start

```bash
# Installation
./scripts/setup.sh

# Run a scenario
./scripts/run-scenario.sh --technique T1059.001

# Evaluate detections
./scripts/evaluate.sh --scenario last

# Generate report
./scripts/report.sh --output ./reports/$(date +%Y%m%d)
```

## Components

- **Orchestrator**: Scenario selection and execution via Caldera/Atomic
- **Telemetry Pipeline**: OTel + osquery ingestion
- **Normalizer**: Raw events → OCSF schema
- **Evaluator**: Sigma rule execution and scoring
- **Reporter**: Coverage, latency, and failure analysis

## Requirements

- Docker & Docker Compose
- Python 3.10+
- Isolated lab environment

## Documentation

- [Architecture Overview](docs/architecture/overview.md)
- [Setup Guide](docs/setup/installation.md)
- [Usage Examples](docs/usage/scenarios.md)

## License

MIT License - See LICENSE file

## Contributing

See CONTRIBUTING.md for guidelines.
