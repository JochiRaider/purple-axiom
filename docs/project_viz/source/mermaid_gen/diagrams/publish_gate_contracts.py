# docs/project_viz/source/mermaid_gen/diagrams/publish_gate_contracts.py
from __future__ import annotations

import re
from typing import Any, Optional

from ..mermaid_fmt import mm_edge_label, mm_text
from ..model_view import as_int, build_entity_index, get_workflow


def _find_workflow(model: dict[str, Any], workflow_id: str) -> Optional[dict[str, Any]]:
    """Return a workflow by ID without falling back to the first workflow."""
    workflows = model.get("workflows", []) or []
    if not isinstance(workflows, list):
        return None
    for wf in workflows:
        if isinstance(wf, dict) and wf.get("id") == workflow_id:
            return wf
    return None


def _is_path_like(value: str) -> bool:
    """Heuristic: treat values as artifact paths if they look like filesystem entries."""
    if "/" in value or "**" in value:
        return True
    return bool(re.search(r"\.[A-Za-z0-9]{1,5}$", value))


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item not in seen:
            out.append(item)
            seen.add(item)
    return out


def gen_publish_gate_contracts_flow(model: dict[str, Any], workflow_id: str) -> str:
    """Generate the publish-gate + stage contract seams diagram (flowchart LR).

    This view combines:
      - canonical stage order (from the selected workflow)
      - publish discipline edges (staging -> validate -> atomic publish)
      - per-stage run-bundle write ownership (from relationships)
    """
    entities = build_entity_index(model)
    workflow = get_workflow(model, workflow_id)

    steps = sorted(
        workflow.get("steps", []) or [],
        key=lambda s: as_int(s.get("n")) if isinstance(s, dict) else 0,
    )

    def entity_label(entity_id: str) -> str:
        ent = entities.get(entity_id)
        if isinstance(ent, dict) and isinstance(ent.get("name"), str):
            return ent["name"]
        return entity_id

    def entity_kind(entity_id: str) -> str:
        ent = entities.get(entity_id)
        if isinstance(ent, dict) and isinstance(ent.get("kind"), str):
            return ent["kind"]
        return ""

    # --- canonical stage order (same logic as stage_flow) ---
    stage_order: list[str] = []
    stage_optional: set[str] = set()
    seen: set[str] = set()

    for step in steps:
        if not isinstance(step, dict):
            continue
        to_id = step.get("to")
        if not isinstance(to_id, str) or not to_id:
            continue
        if entity_kind(to_id) != "stage":
            continue

        if to_id not in seen:
            stage_order.append(to_id)
            seen.add(to_id)

        msg = step.get("message")
        if isinstance(msg, str) and "(optional)" in msg:
            stage_optional.add(to_id)

    # --- publish-gate labels (best-effort from publish_gate workflow) ---
    publish_gate_wf = _find_workflow(model, "publish_gate")
    validate_label = ""
    publish_label = ""

    if publish_gate_wf:
        pg_steps = sorted(
            publish_gate_wf.get("steps", []) or [],
            key=lambda s: as_int(s.get("n")) if isinstance(s, dict) else 0,
        )
        if len(pg_steps) >= 2 and isinstance(pg_steps[1], dict):
            validate_label = str(pg_steps[1].get("message") or "")
        if len(pg_steps) >= 3 and isinstance(pg_steps[2], dict):
            publish_label = str(pg_steps[2].get("message") or "")

    # --- gather per-stage published artifact paths (relationships -> local filesystem datastores) ---
    datastore_ids: set[str] = set()
    for ds in model.get("datastores", []) or []:
        if isinstance(ds, dict) and isinstance(ds.get("id"), str):
            datastore_ids.add(ds["id"])

    stage_outputs: dict[str, list[str]] = {sid: [] for sid in stage_order}

    for rel in model.get("relationships", []) or []:
        if not isinstance(rel, dict):
            continue
        src, dst = rel.get("from"), rel.get("to")
        if not (isinstance(src, str) and isinstance(dst, str)):
            continue
        if src not in stage_outputs:
            continue
        if dst not in datastore_ids:
            continue
        if rel.get("interaction") != "file_drop":
            continue
        if str(rel.get("protocol") or "") != "filesystem":
            continue

        for item in rel.get("data", []) or []:
            if isinstance(item, str) and item and _is_path_like(item):
                stage_outputs[src].append(item)

    stage_outputs = {k: _dedupe_preserve_order(v) for k, v in stage_outputs.items()}

    # --- orchestrator publish discipline edges (relationships) ---
    rels: list[dict[str, Any]] = [
        r for r in (model.get("relationships", []) or []) if isinstance(r, dict)
    ]

    def find_rel(
        src: str,
        dst: str,
        label_substr: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        candidates = [r for r in rels if r.get("from") == src and r.get("to") == dst]
        if not candidates:
            return None
        if label_substr:
            for r in candidates:
                if label_substr.lower() in str(r.get("label") or "").lower():
                    return r
        return candidates[0]

    rel_stage_to_staging = find_rel(
        "orchestrator_cli", "staging_area", label_substr="stage outputs"
    )
    rel_publish = find_rel("orchestrator_cli", "run_bundle_store", label_substr="publish")
    rel_contract_fail = find_rel("orchestrator_cli", "run_logs_store", label_substr="contract")

    # Prefer to show a path glob on the stage->staging edge when available.
    stage_to_staging_edge_label = ""
    if rel_stage_to_staging:
        data = rel_stage_to_staging.get("data", []) or []
        if data and isinstance(data[0], str):
            stage_to_staging_edge_label = data[0]
        else:
            stage_to_staging_edge_label = str(rel_stage_to_staging.get("label") or "")

    publish_edge_label = ""
    if publish_label:
        publish_edge_label = publish_label
    elif rel_publish:
        publish_edge_label = str(rel_publish.get("label") or "")

    contract_fail_edge_label = ""
    if rel_contract_fail:
        rel_label = str(rel_contract_fail.get("label") or "")
        data = [d for d in (rel_contract_fail.get("data", []) or []) if isinstance(d, str)]
        if rel_label and data:
            contract_fail_edge_label = rel_label + ": " + ", ".join(data)
        elif rel_label:
            contract_fail_edge_label = rel_label
        elif data:
            contract_fail_edge_label = ", ".join(data)

    # --- node labels (path-forward for local filesystem) ---
    staging_node_label = ".staging/<stage_id>/"
    if stage_to_staging_edge_label and "/**" in stage_to_staging_edge_label:
        staging_node_label = stage_to_staging_edge_label.replace("/**", "/")

    run_bundle_node_label = "runs/<run_id>/ (run bundle)"
    run_logs_node_label = "runs/<run_id>/logs/"

    publish_gate_node_label = (
        entity_label("publish_gate") if "publish_gate" in entities else "Publish Gate"
    )

    # --- render ---
    lines: list[str] = ["flowchart LR"]
    lines.append("  %% --- execution context ---")
    lines.append('  subgraph ci_environment["CI Environment (pipeline stages)"]')
    lines.append(f'    orchestrator_cli["{mm_text(entity_label("orchestrator_cli"))}"]')
    lines.append(f'    publish_gate["{mm_text(publish_gate_node_label)}"]')
    for stage_id in stage_order:
        lines.append(f'    {stage_id}["{mm_text(entity_label(stage_id))}"]')
    lines.append("  end")
    lines.append("")
    lines.append('  subgraph local_filesystem["Local Filesystem (runs/<run_id>/)"]')
    lines.append(f'    staging_area["{mm_text(staging_node_label)}"]')
    lines.append(f'    run_bundle_store["{mm_text(run_bundle_node_label)}"]')
    lines.append(f'    run_logs_store["{mm_text(run_logs_node_label)}"]')
    lines.append("  end")
    lines.append("")
    lines.append("  %% --- canonical stage order ---")
    for src, dst in zip(stage_order, stage_order[1:]):
        if dst in stage_optional:
            lines.append(f'  {src} -. "optional" .-> {dst}')
        else:
            lines.append(f"  {src} --> {dst}")
    lines.append("")
    lines.append("  %% --- publish discipline (stage writes -> validate -> atomic promote) ---")
    lines.append("  orchestrator_cli --> publish_gate")
    if stage_to_staging_edge_label:
        lines.append(
            f"  orchestrator_cli -->|{mm_edge_label(stage_to_staging_edge_label)}| staging_area"
        )
    else:
        lines.append("  orchestrator_cli --> staging_area")
    if validate_label:
        lines.append(f"  publish_gate -->|{mm_edge_label(validate_label)}| staging_area")
    else:
        lines.append("  publish_gate --> staging_area")
    if publish_edge_label:
        lines.append(f"  publish_gate -->|{mm_edge_label(publish_edge_label)}| run_bundle_store")
    else:
        lines.append("  publish_gate --> run_bundle_store")
    if contract_fail_edge_label:
        lines.append(
            f"  publish_gate -.->|{mm_edge_label(contract_fail_edge_label)}| run_logs_store"
        )
    else:
        lines.append("  publish_gate -.-> run_logs_store")
    lines.append("")
    lines.append("  %% --- contract seams: each stage owns a run-bundle write subtree ---")
    for stage_id in stage_order:
        outs = stage_outputs.get(stage_id, []) or []
        if not outs:
            continue
        label = ", ".join(outs)
        lines.append(f"  {stage_id} -->|{mm_edge_label(label)}| run_bundle_store")

    return "\n".join(lines)
