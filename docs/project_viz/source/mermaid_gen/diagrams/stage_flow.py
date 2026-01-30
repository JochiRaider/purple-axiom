from __future__ import annotations

from typing import Any

from ..mermaid_fmt import mm_text
from ..model_view import as_int, build_entity_index, get_workflow


def gen_stage_flow(model: dict[str, Any], workflow_id: str) -> str:
    """Generate the stage flow diagram (flowchart LR) from a selected workflow."""
    entities = build_entity_index(model)
    workflow = get_workflow(model, workflow_id)

    steps = sorted(
        workflow.get("steps", []) or [],
        key=lambda s: as_int(s.get("n")) if isinstance(s, dict) else 0,
    )

    stage_order: list[str] = []
    stage_optional: set[str] = set()
    seen: set[str] = set()

    for step in steps:
        if not isinstance(step, dict):
            continue

        to_id = step.get("to")
        if not isinstance(to_id, str):
            continue

        ent = entities.get(to_id, {})
        if ent.get("kind") != "stage":
            continue

        if to_id not in seen:
            stage_order.append(to_id)
            seen.add(to_id)

        message = step.get("message")
        if isinstance(message, str) and "(optional)" in message:
            stage_optional.add(to_id)

    lines: list[str] = ["flowchart LR"]
    lines.append('  subgraph ci_environment["CI Environment (pipeline stages)"]')

    for stage_id in stage_order:
        stage_name = entities.get(stage_id, {}).get("name", stage_id)
        label = str(stage_name)
        if stage_id in stage_optional:
            label = f"{label} (optional)"
        lines.append(f'    {stage_id}["{mm_text(label)}"]')

    lines.append("  end")

    for src, dst in zip(stage_order, stage_order[1:]):
        if dst in stage_optional:
            lines.append(f'  {src} -. "optional" .-> {dst}')
        else:
            lines.append(f"  {src} --> {dst}")

    return "\n".join(lines)
