from __future__ import annotations

"""Per-workflow diagram output orchestrator.

This module is intentionally **not** a single-diagram renderer. It coordinates
existing diagram generators to emit a stable per-workflow file tree.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from .constants import WORKFLOW_ID_DEFAULT
from .diagrams.publish_gate_contracts import gen_publish_gate_contracts_flow
from .diagrams.run_sequence import gen_sequence
from .diagrams.run_status_state import gen_run_status_state
from .diagrams.stage_flow import gen_stage_flow
from .diagrams.trust_boundaries import gen_trust_boundaries
from .mermaid_fmt import MERMAID_ID_RE
from .model_view import as_int, build_entity_index
from .writer import write_doc_md, write_md


@dataclass(frozen=True)
class WorkflowSuiteConfig:
    """Configuration for workflow suite generation."""
    trust_view: str
    # If provided, only generate for these workflow IDs (in this order).
    workflow_ids: Optional[tuple[str, ...]] = None


def _iter_workflows(model: dict[str, Any]) -> list[dict[str, Any]]:
    workflows = model.get("workflows", []) or []
    if not isinstance(workflows, list):
        raise TypeError("model.workflows must be a list")

    out: list[dict[str, Any]] = []
    for wf in workflows:
        if not isinstance(wf, dict):
            continue
        wf_id = wf.get("id")
        if isinstance(wf_id, str) and wf_id:
            out.append(wf)
    return out


def _workflow_has_stages(model: dict[str, Any], wf: dict[str, Any]) -> bool:
    """True if workflow contains any step targeting an entity kind=stage."""
    entities = build_entity_index(model)
    steps = sorted(
        wf.get("steps", []) or [],
        key=lambda s: as_int(s.get("n")) if isinstance(s, dict) else 0,
    )

    for step in steps:
        if not isinstance(step, dict):
            continue
        to_id = step.get("to")
        if not isinstance(to_id, str) or not to_id:
            continue
        ent = entities.get(to_id, {})
        if isinstance(ent, dict) and ent.get("kind") == "stage":
            return True
    return False


def _workflow_display_name(wf: dict[str, Any]) -> str:
    wf_id = wf.get("id")
    name = wf.get("name")
    if isinstance(name, str) and name.strip() and name.strip() != wf_id:
        return f"{wf_id} — {name.strip()}"
    return str(wf_id)


def render_workflow_suite(
    model: dict[str, Any],
    out_dir: Path,
    *,
    cfg: WorkflowSuiteConfig,
) -> None:
    """Generate global diagrams + per-workflow diagrams.

    Output layout (under out_dir):
      trust_boundaries.md
      run_status_state.md
      workflows/index.md
      workflows/<workflow_id>/run_sequence.md
      workflows/<workflow_id>/stage_flow.md                 (only if stages appear)
      workflows/<workflow_id>/publish_gate_contracts.md     (only if stages appear)
    """

    # --- Global diagrams (not workflow-specific) ---
    write_md(
        out_dir / "trust_boundaries.md",
        "Trust boundaries",
        gen_trust_boundaries(model, view=cfg.trust_view),
    )
    write_md(
        out_dir / "run_status_state.md",
        "Run status (success/partial/failed)",
        gen_run_status_state(model),
    )

    # --- Per-workflow diagrams ---
    workflows = _iter_workflows(model)
    if cfg.workflow_ids is not None:
        by_id = {str(w.get("id")): w for w in workflows}
        workflows = []
        for wf_id in cfg.workflow_ids:
            if wf_id not in by_id:
                raise KeyError(f"Unknown workflow id: {wf_id!r}")
            workflows.append(by_id[wf_id])

    index_rows: list[tuple[str, str, str, str]] = []

    for wf in workflows:
        wf_id = str(wf.get("id"))
        if not MERMAID_ID_RE.match(wf_id):
            raise ValueError(
                f"workflow id {wf_id!r} is not Mermaid-safe (expected {MERMAID_ID_RE.pattern})"
            )

        wf_name = _workflow_display_name(wf)
        wf_scope = wf.get("scope") if isinstance(wf.get("scope"), str) else ""
        wf_dir = out_dir / "workflows" / wf_id

        # Always: sequence diagram
        write_md(
            wf_dir / "run_sequence.md",
            f"Workflow sequence — {wf_name}",
            gen_sequence(model, wf_id),
        )

        has_stages = _workflow_has_stages(model, wf)
        diagrams_cell_parts: list[str] = [f"[run_sequence](./{wf_id}/run_sequence.md)"]

        if has_stages:
            write_md(
                wf_dir / "stage_flow.md",
                f"Stage flow — {wf_name}",
                gen_stage_flow(model, wf_id),
            )
            write_md(
                wf_dir / "publish_gate_contracts.md",
                f"Publish gate + contract seams — {wf_name}",
                gen_publish_gate_contracts_flow(model, wf_id),
            )
            diagrams_cell_parts.append(f"[stage_flow](./{wf_id}/stage_flow.md)")
            diagrams_cell_parts.append(
                f"[publish_gate_contracts](./{wf_id}/publish_gate_contracts.md)"
            )

        index_rows.append((wf_id, wf_scope, wf_name, " ".join(diagrams_cell_parts)))

    # --- Index page for docs navigation ---
    lines: list[str] = []
    lines.append("Generated per-workflow diagrams.\n")
    lines.append("| workflow_id | scope | name | diagrams |")
    lines.append("|---|---|---|---|")
    for wf_id, wf_scope, wf_name, diagrams_cell in index_rows:
        lines.append(f"| {wf_id} | {wf_scope} | {wf_name} | {diagrams_cell} |")

    write_doc_md(out_dir / "workflows" / "index.md", "Workflows", "\n".join(lines) + "\n")
