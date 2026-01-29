#!/usr/bin/env python3
"""
Generate Mermaid diagrams from system_model.yaml (YAML model).

Outputs (same filenames as the prior JSON-based script):
  docs/diagrams/generated/
    - stage_flow.md
    - trust_boundaries.md
    - run_sequence.md
    - run_status_state.md
project script path: docs/project_viz/source/Mermaid.py      
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_VIZ_DIR = SCRIPT_DIR.parent
DOCS_DIR = PROJECT_VIZ_DIR.parent

OUT_DIR_DEFAULT = DOCS_DIR / "diagrams" / "generated"
MODEL_PATH_DEFAULT = PROJECT_VIZ_DIR / "architecture" / "system_model.yaml"
WORKFLOW_ID_DEFAULT = "exercise_run"

MERMAID_ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def mermaid_block(code: str) -> str:
    return "```mermaid\n" + code.rstrip() + "\n```\n"


def write_md(path: Path, title: str, diagram_code: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {title}\n\n{mermaid_block(diagram_code)}", encoding="utf-8")


def mm_text(s: str) -> str:
    """
    Escape text for Mermaid labels.

    Mermaid renders labels as HTML; unescaped `<run_id>` can disappear as an HTML tag.
    """
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', '\\"')
        .replace("|", "&#124;")
    )


def _sanitize_yaml_for_pyyaml(raw: str) -> str:
    """
    Some YAML parsers reject plain scalars containing ': ' (colon-space).
    In the current model, this appears in some evidence `excerpt:` lines.

    This sanitizer only quotes *unquoted* `excerpt:` values that contain ': '.
    It does not modify other fields.
    """
    out_lines: List[str] = []
    for line in raw.splitlines():
        m = re.match(r"^(\s*excerpt:\s*)(.+)$", line)
        if not m:
            out_lines.append(line)
            continue

        prefix, val = m.group(1), m.group(2)
        # already quoted or block scalar
        if val.startswith(("'", '"', "|", ">")):
            out_lines.append(line)
            continue

        if ": " in val:
            escaped = val.replace("\\", "\\\\").replace('"', '\\"')
            out_lines.append(f'{prefix}"{escaped}"')
        else:
            out_lines.append(line)

    return "\n".join(out_lines) + ("\n" if raw.endswith("\n") else "")


def load_model(path: Path) -> Dict[str, Any]:
    raw = path.read_text(encoding="utf-8")

    # First try strict parse.
    try:
        model = yaml.safe_load(raw)
        if not isinstance(model, dict):
            raise TypeError(f"Top-level YAML must be a mapping, got {type(model).__name__}")
        return model
    except Exception:
        # Retry with excerpt sanitization (keeps generator working with the current file).
        sanitized = _sanitize_yaml_for_pyyaml(raw)
        model = yaml.safe_load(sanitized)
        if not isinstance(model, dict):
            raise TypeError(f"Top-level YAML must be a mapping, got {type(model).__name__}")

        # Keep this as a warning so the underlying YAML can be fixed later.
        print(
            f"warning: parsed {path} after sanitizing unquoted `excerpt:` scalars; "
            f"consider quoting excerpt values containing ': '",
            file=sys.stderr,
        )
        return model

def _as_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def validate_model(model: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    """
    Lightweight structural validation to keep the YAML model diagram-safe.
    Returns (errors, warnings).
    """
    errors: List[str] = []
    warnings: List[str] = []

    trust_zones = model.get("trust_zones", []) or []
    if not isinstance(trust_zones, list):
        errors.append("model.trust_zones must be a list")
        trust_zones = []

    tz_ids: set[str] = set()
    for tz in trust_zones:
        if not isinstance(tz, dict):
            warnings.append("model.trust_zones contains a non-mapping item; skipping")
            continue
        tz_id = tz.get("id")
        if not isinstance(tz_id, str) or not tz_id:
            errors.append("model.trust_zones item missing string `id`")
            continue
        tz_ids.add(tz_id)
        if not MERMAID_ID_RE.match(tz_id):
            errors.append(f"trust_zone id {tz_id!r} is not Mermaid-safe (use [A-Za-z0-9_] and cannot start with a digit)")

    entity_sections = ("actors", "containers", "datastores", "externals", "buses")
    entity_ids: Dict[str, str] = {}

    for sec in entity_sections:
        items = model.get(sec, []) or []
        if not isinstance(items, list):
            errors.append(f"model.{sec} must be a list")
            continue
        for it in items:
            if not isinstance(it, dict):
                warnings.append(f"model.{sec} contains a non-mapping item; skipping")
                continue
            eid = it.get("id")
            if not isinstance(eid, str) or not eid:
                errors.append(f"model.{sec} item missing string `id`")
                continue
            if eid in entity_ids:
                errors.append(f"duplicate entity id {eid!r} in {sec} (also in {entity_ids[eid]})")
            else:
                entity_ids[eid] = sec
            if not MERMAID_ID_RE.match(eid):
                errors.append(f"entity id {eid!r} is not Mermaid-safe (use [A-Za-z0-9_] and cannot start with a digit)")
            tz = it.get("trust_zone")
            if tz is not None:
                if not isinstance(tz, str) or not tz:
                    errors.append(f"entity {eid!r} has non-string trust_zone")
                elif tz not in tz_ids:
                    warnings.append(f"entity {eid!r} references undeclared trust_zone {tz!r}")

    rels = model.get("relationships", []) or []
    if not isinstance(rels, list):
        errors.append("model.relationships must be a list")
    else:
        for r in rels:
            if not isinstance(r, dict):
                warnings.append("model.relationships contains a non-mapping item; skipping")
                continue
            a, b = r.get("from"), r.get("to")
            if isinstance(a, str) and a and a not in entity_ids:
                warnings.append(f"relationship.from references unknown entity id {a!r}")
            if isinstance(b, str) and b and b not in entity_ids:
                warnings.append(f"relationship.to references unknown entity id {b!r}")

    workflows = model.get("workflows", []) or []
    if workflows and not isinstance(workflows, list):
        errors.append("model.workflows must be a list")
    elif isinstance(workflows, list):
        for wf in workflows:
            if not isinstance(wf, dict):
                warnings.append("model.workflows contains a non-mapping item; skipping")
                continue
            steps = wf.get("steps", []) or []
            if not isinstance(steps, list):
                errors.append(f"workflow {wf.get('id')!r} steps must be a list")
                continue
            for st in steps:
                if not isinstance(st, dict):
                    warnings.append(f"workflow {wf.get('id')!r} contains a non-mapping step; skipping")
                    continue
                frm, to = st.get("from"), st.get("to")
                if isinstance(frm, str) and frm and frm not in entity_ids:
                    warnings.append(f"workflow {wf.get('id')!r} step.from references unknown entity id {frm!r}")
                if isinstance(to, str) and to and to not in entity_ids:
                    warnings.append(f"workflow {wf.get('id')!r} step.to references unknown entity id {to!r}")

    return errors, warnings

def build_entity_index(model: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Index entities by id across the model sections used by diagrams.
    """
    idx: Dict[str, Dict[str, Any]] = {}
    for section in ("actors", "containers", "datastores", "externals", "buses"):
        for item in model.get(section, []) or []:
            if not isinstance(item, dict):
                continue
            _id = item.get("id")
            if isinstance(_id, str) and _id:
                idx[_id] = item
    return idx


def get_workflow(model: Dict[str, Any], workflow_id: str) -> Dict[str, Any]:
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


def gen_stage_flow(model: Dict[str, Any], workflow_id: str) -> str:
    """
    Stage flow is derived from the selected workflow, extracting `to:` endpoints
    that are containers with kind == "stage", preserving step order.
    """
    entities = build_entity_index(model)
    wf = get_workflow(model, workflow_id)

    steps = sorted(wf.get("steps", []) or [], key=lambda s: _as_int(s.get("n")))
    stage_order: List[str] = []
    stage_optional: set[str] = set()
    seen: set[str] = set()

    for st in steps:
        to_id = st.get("to")
        if not isinstance(to_id, str):
            continue
        ent = entities.get(to_id, {})
        if ent.get("kind") != "stage":
            continue

        if to_id not in seen:
            stage_order.append(to_id)
            seen.add(to_id)

        if "(optional)" in (st.get("message") or ""):
            stage_optional.add(to_id)

    lines: List[str] = ["flowchart LR"]
    lines.append('  subgraph ci_environment["CI Environment (pipeline stages)"]')
    for sid in stage_order:
        label = entities.get(sid, {}).get("name", sid)
        if sid in stage_optional:
            label = f"{label} (optional)"
        lines.append(f'    {sid}["{mm_text(label)}"]')
    lines.append("  end")

    for a, b in zip(stage_order, stage_order[1:]):
        if b in stage_optional:
            lines.append(f'  {a} -. "optional" .-> {b}')
        else:
            lines.append(f"  {a} --> {b}")

    return "\n".join(lines)


def gen_trust_boundaries(model: Dict[str, Any]) -> str:
    """
    Trust boundaries view derived from:
      - trust_zones (for clustering)
      - relationships (for edges)

    Selection rule to keep the diagram bounded:
      - include all cross-trust-zone relationships (both endpoints have zones and differ)
      - include orchestrator_cli -> * edges labelled "invoke stage"
    """
    entities = build_entity_index(model)

    trust_zones = model.get("trust_zones", []) or []
    tz_name = {
        tz.get("id"): tz.get("name", tz.get("id"))
        for tz in trust_zones
        if isinstance(tz, dict)
    }

    def zone(eid: str) -> Optional[str]:
        ent = entities.get(eid)
        return ent.get("trust_zone") if isinstance(ent, dict) else None

    def label(eid: str) -> str:
        ent = entities.get(eid)
        if isinstance(ent, dict) and isinstance(ent.get("name"), str):
            return ent["name"]
        return eid

    selected_edges: List[Dict[str, Any]] = []
    for rel in model.get("relationships", []) or []:
        if not isinstance(rel, dict):
            continue
        a, b = rel.get("from"), rel.get("to")
        if not (isinstance(a, str) and isinstance(b, str)):
            continue

        za, zb = zone(a), zone(b)

        if za and zb and za != zb:
            selected_edges.append(rel)
            continue

        if a == "orchestrator_cli" and rel.get("label") == "invoke stage":
            selected_edges.append(rel)

    node_ids: set[str] = set()
    for rel in selected_edges:
        node_ids.add(rel["from"])
        node_ids.add(rel["to"])

    nodes_by_zone: Dict[str, List[str]] = {}
    for nid in sorted(node_ids):
        z = zone(nid) or "unmodeled"
        nodes_by_zone.setdefault(z, []).append(nid)

    lines: List[str] = ["flowchart TB"]

    declared_order = [
        tz.get("id")
        for tz in trust_zones
        if isinstance(tz, dict) and isinstance(tz.get("id"), str)
    ]
    zone_order = [z for z in declared_order if z in nodes_by_zone] + [
        z for z in sorted(nodes_by_zone.keys()) if z not in declared_order
    ]

    for z in zone_order:
        lines.append(f'  subgraph {z}["{mm_text(tz_name.get(z, z))}"]') # type: ignore
        for nid in nodes_by_zone[z]:
            lines.append(f'    {nid}["{mm_text(label(nid))}"]')
        lines.append("  end")

    def edge_sort_key(r: Dict[str, Any]) -> Tuple[str, str, str]:
        return (str(r.get("from", "")), str(r.get("to", "")), str(r.get("label", "")))

    for rel in sorted(selected_edges, key=edge_sort_key):
        a, b = rel["from"], rel["to"]
        lbl = rel.get("label") or ""
        if lbl:
            lines.append(f"  {a} -->|{mm_text(str(lbl))}| {b}")
        else:
            lines.append(f"  {a} --> {b}")

    return "\n".join(lines)


def gen_sequence(model: Dict[str, Any], workflow_id: str) -> str:
    """
    Sequence diagram is generated directly from workflows[*].steps (ordered by n).
    """
    entities = build_entity_index(model)
    wf = get_workflow(model, workflow_id)

    def label(eid: str) -> str:
        ent = entities.get(eid)
        if isinstance(ent, dict) and isinstance(ent.get("name"), str):
            return ent["name"]
        return eid

    steps = sorted(wf.get("steps", []) or [], key=lambda s: _as_int(s.get("n")))

    participants: List[str] = []
    seen: set[str] = set()

    def add(pid: Any) -> None:
        if isinstance(pid, str) and pid and pid not in seen:
            participants.append(pid)
            seen.add(pid)

    for st in steps:
        add(st.get("from"))
        add(st.get("to"))

    lines: List[str] = ["sequenceDiagram"]
    for pid in participants:
        lines.append(f'  participant {pid} as "{mm_text(label(pid))}"')

    for st in steps:
        frm, to = st.get("from"), st.get("to")
        if not (isinstance(frm, str) and isinstance(to, str)):
            continue
        n = st.get("n")
        msg = st.get("message") or ""
        prefix = f"{n}. " if n is not None else ""
        lines.append(f"  {frm}->>{to}: {mm_text(prefix + str(msg))}")

    return "\n".join(lines)


def gen_run_status_state(model: Dict[str, Any]) -> str:
    # system_model.yaml currently defines `states: []` (no explicit state machine),
    # so keep this as a stable, spec-level summary.
    return "\n".join(
        [
            "stateDiagram-v2",
            "  [*] --> Running",
            "  Running --> Failed: any enabled stage fails (fail_closed)",
            "  Running --> Partial: any enabled stage fails (warn_and_skip)",
            "  Running --> Success: otherwise",
            "  Failed --> [*]",
            "  Partial --> [*]",
            "  Success --> [*]",
        ]
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", type=Path, default=MODEL_PATH_DEFAULT, help="Path to system_model.yaml")
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR_DEFAULT, help="Output directory for generated markdown")
    ap.add_argument(
        "--workflow",
        type=str,
        default=WORKFLOW_ID_DEFAULT,
        help="Workflow id to use for stage flow + run sequence diagrams",
    )
    ap.add_argument(
        "--strict",
        action="store_true",
        help="Fail generation on validation warnings (unknown ids, undeclared trust zones, non-Mermaid-safe ids).",
    )
    args = ap.parse_args()

    model = load_model(args.model)
    errors, warnings = validate_model(model)
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    if errors or (args.strict and warnings):
        for e in errors:
            print(f"error: {e}", file=sys.stderr)
        raise SystemExit(2)    
    out_dir: Path = args.out_dir

    write_md(out_dir / "stage_flow.md", "Stage flow", gen_stage_flow(model, args.workflow))
    write_md(out_dir / "trust_boundaries.md", "Trust boundaries", gen_trust_boundaries(model))
    write_md(out_dir / "run_sequence.md", "Canonical run sequence (v0.1)", gen_sequence(model, args.workflow))
    write_md(out_dir / "run_status_state.md", "Run status (success/partial/failed)", gen_run_status_state(model))


if __name__ == "__main__":
    main()