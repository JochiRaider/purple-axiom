#!/usr/bin/env python3
"""Generate Mermaid diagrams from a YAML architecture model.

This script supports two input layouts:

1) **Split model directory** (current):
   `docs/project_viz/architecture/`
     - 00_system.yaml
     - 10_trust_zones.yaml
     - 20_entities.yaml
     - 30_relationships.yaml
     - 90_notes.yaml (optional; not used by diagrams)
     - workflows/*.yaml

2) **Monolithic YAML file** (legacy):
   `system_model.yaml` containing the same top-level keys.

Outputs:
    docs/diagrams/generated/
        - stage_flow.md
        - trust_boundaries.md
        - run_sequence.md
        - run_status_state.md

Script path:
    docs/project_viz/source/Mermaid.py
"""

from __future__ import annotations

from mermaid_gen.cli import main


if __name__ == "__main__":
    main()
