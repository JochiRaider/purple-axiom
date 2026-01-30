from __future__ import annotations

from typing import Any

from .constants import ENTITY_SECTIONS


def as_int(value: Any, default: int = 0) -> int:
    """Convert a value to int, falling back to a default."""
    try:
        return int(value)
    except Exception:
        return default


def build_entity_index(model: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Index entities by ID across sections used by diagrams."""
    index: dict[str, dict[str, Any]] = {}
    for section in ENTITY_SECTIONS:
        for item in model.get(section, []) or []:
            if not isinstance(item, dict):
                continue

            entity_id = item.get("id")
            if isinstance(entity_id, str) and entity_id:
                index[entity_id] = item

    return index


def get_workflow(model: dict[str, Any], workflow_id: str) -> dict[str, Any]:
    """Get a workflow by ID, or deterministically fall back to the first workflow."""
    workflows = model.get("workflows", []) or []
    if not isinstance(workflows, list):
        raise TypeError("model.workflows must be a list")

    for wf in workflows:
        if isinstance(wf, dict) and wf.get("id") == workflow_id:
            return wf

    # Deterministic fallback: first workflow, if present.
    if workflows and isinstance(workflows[0], dict):
        return workflows[0]

    raise KeyError(f"No workflows found (requested workflow_id={workflow_id!r})")
