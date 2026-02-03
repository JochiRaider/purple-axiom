from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from .model_view import as_int, build_entity_index
from .writer import write_md, write_text_md

# Existing diagram generators (reused as building blocks).
from .diagrams.publish_gate_contracts import gen_publish_gate_contracts_flow
from .diagrams.run_sequence import gen_sequence
from .diagrams.stage_flow import gen_stage_flow


def _workflow_display_name(wf: dict[str, Any]) -> str:
    """Best-effort human label for a workflow.

    We keep IDs stable and always include wf.id; name/title are optional.
    """

    wf_id = wf.get("id")
    wf_id_s = wf_id if isinstance(wf_id, str) else ""

    for key in ("name", "title", "purpose"):
        val = wf.get(key)
        if isinstance(val, str) and val.strip():
            name = val.strip()
            if wf_id_s and name != wf_id_s:
                return f"{name} ({wf_id_s})"
            return name

    return wf_id_s or "<unknown_workflow>"


def _stage_order_for_workflow(model: dict[str, Any], wf: dict[str, Any]) -> list[str]:
    """Return canonical stage order for a workflow.

    Mirrors the stage detection semantics used by the stage_flow and
    publish_gate_contracts diagrams: a step's `to` is a stage iff the referenced
    entity has kind == "stage".
    """

    entities = build_entity_index(model)
    steps = sorted(
        wf.get("steps", []) or [],
        key=lambda s: as_int(s.get("n")) if isinstance(s, dict) else 0,
    )

    stage_order: list[str] = []
    seen: set[str] = set()

    for step in steps:
        if not isinstance(step, dict):
            continue

        to_id = step.get("to")
        if not isinstance(to_id, str) or not to_id:
            continue

        ent = entities.get(to_id, {})
        if not (isinstance(ent, dict) and ent.get("kind") == "stage"):
            continue

        if to_id not in seen:
            stage_order.append(to_id)
            seen.add(to_id)

    return stage_order


def _require_workflows_list(model: dict[str, Any]) -> list[dict[str, Any]]:
    workflows = model.get("workflows", []) or []
    if workflows and not isinstance(workflows, list):
        raise TypeError("model.workflows must be a list")

    out: list[dict[str, Any]] = []
    for wf in workflows:
        if isinstance(wf, dict):
            out.append(wf)
    return out


def _workflow_id(wf: dict[str, Any]) -> Optional[str]:
    wf_id = wf.get("id")
    if isinstance(wf_id, str) and wf_id:
        return wf_id
    return None


def _preflight_suite(workflows: list[dict[str, Any]]) -> None:
    """Fail fast on conditions that would cause destructive overwrites."""

    seen: dict[str, int] = {}
    for i, wf in enumerate(workflows):
        wf_id = _workflow_id(wf)
        if not wf_id:
            # Validator should catch this as an error, but suite generation needs
            # IDs for directory paths.
            raise ValueError(f"workflow at index {i} is missing a string 'id'")

        if wf_id in seen:
            raise ValueError(
                f"duplicate workflow id {wf_id!r} (workflows[{seen[wf_id]}] and workflows[{i}])"
            )
        seen[wf_id] = i

        # Guard: workflow ids are used as directory names; disallow path
        # separators and path traversal segments.
        if "/" in wf_id or "\\" in wf_id or ".." in wf_id:
            raise ValueError(
                f"workflow id {wf_id!r} is not safe for use as a directory name"
            )


def _md_table_cell(text: str) -> str:
    """Escape a string for use in a Markdown table cell."""
    s = (text or "").replace("\r", " ").replace("\n", " ").strip()
    # Escape table separators.
    s = s.replace("|", "\\|")
    return s


def generate_workflow_suite(
    model: dict[str, Any],
    out_dir: Path,
    *,
    suite_dirname: str = "workflows",
    write_index: bool = True,
) -> None:
    """Generate per-workflow diagram outputs under out_dir/workflows/<id>/.

    Option A behavior (per your plan): callers typically run the existing global
    diagram registry first (top-level files), then call this to additionally
    emit per-workflow outputs.

    Outputs per workflow:
      - workflows/<workflow_id>/run_sequence.md
      - workflows/<workflow_id>/stage_flow.md (only when stages appear)
      - workflows/<workflow_id>/publish_gate_contracts.md (only when stages appear)

    Additionally (recommended): workflows/index.md listing links.
    """

    workflows = _require_workflows_list(model)
    _preflight_suite(workflows)

    # Deterministic ordering independent of YAML file order.
    workflows_sorted = sorted(workflows, key=lambda w: str(w.get("id") or ""))

    # Generate per-workflow outputs.
    per_wf_rows: list[tuple[str, str, bool]] = []  # (id, display_name, has_stages)

    for wf in workflows_sorted:
        wf_id = _workflow_id(wf)
        if not wf_id:
            continue  # preflight already guards, but keep mypy happy.

        wf_label = _workflow_display_name(wf)

        wf_dir = out_dir / suite_dirname / wf_id

        # Always: run sequence
        seq_code = gen_sequence(model, wf_id)
        write_md(
            wf_dir / "run_sequence.md",
            title=f"Run sequence — {wf_label}",
            diagram_code=seq_code,
        )

        # Conditional: stage views
        stage_order = _stage_order_for_workflow(model, wf)
        has_stages = bool(stage_order)

        if has_stages:
            stage_code = gen_stage_flow(model, wf_id)
            write_md(
                wf_dir / "stage_flow.md",
                title=f"Stage flow — {wf_label}",
                diagram_code=stage_code,
            )

            pg_code = gen_publish_gate_contracts_flow(model, wf_id)
            write_md(
                wf_dir / "publish_gate_contracts.md",
                title=f"Publish gate + contract seams — {wf_label}",
                diagram_code=pg_code,
            )

        per_wf_rows.append((wf_id, wf_label, has_stages))

    # Optional: workflows/index.md
    if write_index:
        index_path = out_dir / suite_dirname / "index.md"

        lines: list[str] = []
        lines.append(
            "This page lists workflow-scoped diagram outputs generated from the YAML model."
        )
        lines.append("")

        lines.append("| workflow_id | label | run sequence | stage flow | publish gate |")
        lines.append("|---|---|---|---|---|")

        for wf_id, wf_label, has_stages in per_wf_rows:
            run_seq_link = f"[{_md_table_cell('run_sequence')}]({wf_id}/run_sequence.md)"
            stage_link = (
                f"[{_md_table_cell('stage_flow')}]({wf_id}/stage_flow.md)"
                if has_stages
                else ""
            )
            pg_link = (
                f"[{_md_table_cell('publish_gate_contracts')}]({wf_id}/publish_gate_contracts.md)"
                if has_stages
                else ""
            )
            lines.append(
                "| "
                + " | ".join(
                    [
                        _md_table_cell(wf_id),
                        _md_table_cell(wf_label),
                        run_seq_link,
                        stage_link,
                        pg_link,
                    ]
                )
                + " |"
            )

        lines.append("")
        lines.append("Notes:")
        lines.append("- Stage flow + publish gate diagrams are emitted only when the workflow targets stage entities.")

        write_text_md(index_path, title="Workflows", body_md="\n".join(lines))
