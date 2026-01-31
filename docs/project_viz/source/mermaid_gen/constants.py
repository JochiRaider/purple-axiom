# docs/project_viz/source/mermaid_gen/constants.py
from __future__ import annotations

ENTITY_SECTIONS: tuple[str, ...] = (
    "actors",
    "containers",
    "datastores",
    "externals",
    "buses",
)

# Split-model filenames (loaded in deterministic order).
MODEL_PART_FILES: tuple[str, ...] = (
    "00_system.yaml",
    "10_trust_zones.yaml",
    "20_entities.yaml",
    "30_relationships.yaml",
    # Workflows are discovered under workflows/*.yaml
    "90_notes.yaml",  # optional; not used by diagrams but kept for completeness
)

WORKFLOW_ID_DEFAULT = "exercise_run"
TRUST_VIEW_DEFAULT = "compact"
