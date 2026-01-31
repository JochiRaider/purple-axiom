# docs/project_viz/source/mermaid_gen/diagrams/run_sequence.py
from __future__ import annotations

from typing import Any

from ..mermaid_fmt import mm_text
from ..model_view import as_int, build_entity_index, get_workflow


def gen_sequence(model: dict[str, Any], workflow_id: str) -> str:
    """Generate a sequence diagram from the selected workflow's ordered steps."""
    entities = build_entity_index(model)
    workflow = get_workflow(model, workflow_id)

    def entity_label(entity_id: str) -> str:
        ent = entities.get(entity_id)
        if isinstance(ent, dict) and isinstance(ent.get("name"), str):
            return ent["name"]
        return entity_id

    steps = sorted(
        workflow.get("steps", []) or [],
        key=lambda s: as_int(s.get("n")) if isinstance(s, dict) else 0,
    )

    participants: list[str] = []
    seen: set[str] = set()

    def add(participant_id: Any) -> None:
        if isinstance(participant_id, str) and participant_id and participant_id not in seen:
            participants.append(participant_id)
            seen.add(participant_id)

    for step in steps:
        if not isinstance(step, dict):
            continue
        add(step.get("from"))
        add(step.get("to"))

    lines: list[str] = ["sequenceDiagram"]
    for pid in participants:
        lines.append(f'  participant {pid} as "{mm_text(entity_label(pid))}"')

    for step in steps:
        if not isinstance(step, dict):
            continue

        src, dst = step.get("from"), step.get("to")
        if not (isinstance(src, str) and isinstance(dst, str)):
            continue

        n_val = step.get("n")
        msg_val = step.get("message") or ""
        prefix = f"{n_val}. " if n_val is not None else ""
        lines.append(f"  {src}->>{dst}: {mm_text(prefix + str(msg_val))}")

    return "\n".join(lines)
