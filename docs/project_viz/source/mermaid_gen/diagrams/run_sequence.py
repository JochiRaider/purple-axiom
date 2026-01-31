from __future__ import annotations

from typing import Any

from ..mermaid_fmt import assert_mm_id, mm_participant, mm_text
from ..model_view import as_int, build_entity_index, get_workflow


def gen_sequence(model: dict[str, Any], workflow_id: str) -> str:
    """Generate a sequence diagram from the selected workflow's ordered steps."""
    entities = build_entity_index(model)
    workflow = get_workflow(model, workflow_id)

    steps_raw = workflow.get("steps", []) or []
    if not isinstance(steps_raw, list):
        wf_id = workflow.get("id", workflow_id)
        raise TypeError(f"workflow {wf_id!r} steps must be a list")

    def entity_label(entity_id: str) -> str:
        ent = entities.get(entity_id)
        if isinstance(ent, dict):
            name = ent.get("name")
            if isinstance(name, str) and name:
                return name
        return entity_id

    # Keep only mapping steps; sort by integer `n`.
    # Treat missing/bad `n` as "go last" to avoid malformed steps floating to the top.
    steps: list[dict[str, Any]] = [s for s in steps_raw if isinstance(s, dict)]
    steps.sort(key=lambda s: as_int(s.get("n"), default=1_000_000_000))

    participants: list[str] = []
    seen: set[str] = set()

    def add(pid: Any) -> None:
        if not (isinstance(pid, str) and pid):
            return
        assert_mm_id(pid)
        if pid not in seen:
            participants.append(pid)
            seen.add(pid)

    for step in steps:
        add(step.get("from"))
        add(step.get("to"))

    lines: list[str] = ["sequenceDiagram"]
    for pid in participants:
        lines.append(mm_participant(pid, entity_label(pid)))

    for step in steps:
        src, dst = step.get("from"), step.get("to")
        if not (isinstance(src, str) and isinstance(dst, str)):
            continue

        # add() already validated IDs for declared participants, but keep this if you want
        # standalone safety even when participants collection logic changes later.
        assert_mm_id(src)
        assert_mm_id(dst)

        n_val = step.get("n")
        msg_val = step.get("message") or ""
        prefix = f"{n_val}. " if n_val is not None else ""
        lines.append(f"  {src}->>{dst}: {mm_text(prefix + str(msg_val))}")

    return "\n".join(lines)
