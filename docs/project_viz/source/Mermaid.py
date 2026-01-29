#!/usr/bin/env python3
"""Generate Mermaid diagrams from `system_model.yaml` (YAML model).

This script reads a YAML system model and generates Markdown files that embed
Mermaid diagrams. Output filenames match the prior JSON-based generator.

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

import argparse
import re
import sys
from pathlib import Path
from typing import Any, Optional, Tuple

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_VIZ_DIR = SCRIPT_DIR.parent
DOCS_DIR = PROJECT_VIZ_DIR.parent

OUT_DIR_DEFAULT = DOCS_DIR / "diagrams" / "generated"
MODEL_PATH_DEFAULT = PROJECT_VIZ_DIR / "architecture" / "system_model.yaml"
WORKFLOW_ID_DEFAULT = "exercise_run"

# Mermaid node/subgraph IDs must be alphanumeric/underscore and must not start
# with a digit.
MERMAID_ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

ENTITY_SECTIONS: tuple[str, ...] = (
    "actors",
    "containers",
    "datastores",
    "externals",
    "buses",
)


def mermaid_block(code: str) -> str:
    """Wrap Mermaid source in a Markdown Mermaid code fence.

    Args:
        code: Mermaid diagram source.

    Returns:
        Markdown string containing a Mermaid code block.
    """
    return "```mermaid\n" + code.rstrip() + "\n```\n"


def write_md(path: Path, title: str, diagram_code: str) -> None:
    """Write a titled Markdown file containing a Mermaid diagram block.

    Args:
        path: Output Markdown path.
        title: H1 title for the Markdown file.
        diagram_code: Mermaid source code.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    content = f"# {title}\n\n{mermaid_block(diagram_code)}"
    path.write_text(content, encoding="utf-8")


def mm_text(text: str) -> str:
    """Escape text for Mermaid labels.

    Mermaid renders labels as HTML; unescaped `<run_id>` can be interpreted as an
    HTML tag and may disappear.

    Args:
        text: Raw label text.

    Returns:
        Escaped label text safe for Mermaid.
    """
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', '\\"')
        .replace("|", "&#124;")
    )


def _sanitize_yaml_for_pyyaml(raw: str) -> str:
    """Sanitize YAML to improve compatibility with PyYAML parsing.

    Some YAML parsers reject plain scalars containing ': ' (colon-space). In the
    current model, this appears in some evidence `excerpt:` lines.

    This sanitizer only quotes *unquoted* `excerpt:` values that contain ': '.
    It does not modify other fields.

    Args:
        raw: Raw YAML content.

    Returns:
        YAML content with only the relevant `excerpt:` scalars quoted.
    """
    out_lines: list[str] = []
    for line in raw.splitlines():
        match = re.match(r"^(\s*excerpt:\s*)(.+)$", line)
        if not match:
            out_lines.append(line)
            continue

        prefix, value = match.group(1), match.group(2)

        # Already quoted or a block scalar.
        if value.startswith(("'", '"', "|", ">")):
            out_lines.append(line)
            continue

        if ": " in value:
            escaped = value.replace("\\", "\\\\").replace('"', '\\"')
            out_lines.append(f'{prefix}"{escaped}"')
        else:
            out_lines.append(line)

    return "\n".join(out_lines) + ("\n" if raw.endswith("\n") else "")


def load_model(path: Path) -> dict[str, Any]:
    """Load the YAML system model.

    Tries strict parsing first. If parsing fails, retries after sanitizing
    unquoted `excerpt:` scalars that contain ': '.

    Args:
        path: Path to `system_model.yaml`.

    Returns:
        Parsed YAML mapping.

    Raises:
        FileNotFoundError: If `path` does not exist.
        TypeError: If the top-level YAML object is not a mapping.
        yaml.YAMLError: If parsing fails even after sanitization.
    """
    raw = path.read_text(encoding="utf-8")

    try:
        model = yaml.safe_load(raw)
    except Exception:
        sanitized = _sanitize_yaml_for_pyyaml(raw)
        model = yaml.safe_load(sanitized)

        print(
            (
                f"warning: parsed {path} after sanitizing unquoted `excerpt:` "
                "scalars; consider quoting excerpt values containing ': '"
            ),
            file=sys.stderr,
        )

    if not isinstance(model, dict):
        raise TypeError(
            "Top-level YAML must be a mapping, got "
            f"{type(model).__name__}"
        )

    return model


def _as_int(value: Any, default: int = 0) -> int:
    """Convert a value to int, falling back to a default.

    Args:
        value: Value to convert.
        default: Value to return if conversion fails.

    Returns:
        Integer conversion result or `default`.
    """
    try:
        return int(value)
    except Exception:
        return default


def validate_model(model: dict[str, Any]) -> Tuple[list[str], list[str]]:
    """Perform lightweight structural validation to keep the model diagram-safe.

    The validation is intentionally shallow and oriented toward avoiding Mermaid
    generation issues.

    Args:
        model: Parsed system model mapping.

    Returns:
        A tuple of (errors, warnings), each as a list of strings.
    """
    errors: list[str] = []
    warnings: list[str] = []

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
            errors.append(
                "trust_zone id "
                f"{tz_id!r} is not Mermaid-safe (use [A-Za-z0-9_] and cannot "
                "start with a digit)"
            )

    entity_ids: dict[str, str] = {}
    for section in ENTITY_SECTIONS:
        items = model.get(section, []) or []
        if not isinstance(items, list):
            errors.append(f"model.{section} must be a list")
            continue

        for item in items:
            if not isinstance(item, dict):
                warnings.append(f"model.{section} contains a non-mapping item; skipping")
                continue

            entity_id = item.get("id")
            if not isinstance(entity_id, str) or not entity_id:
                errors.append(f"model.{section} item missing string `id`")
                continue

            if entity_id in entity_ids:
                errors.append(
                    f"duplicate entity id {entity_id!r} in {section} "
                    f"(also in {entity_ids[entity_id]})"
                )
            else:
                entity_ids[entity_id] = section

            if not MERMAID_ID_RE.match(entity_id):
                errors.append(
                    "entity id "
                    f"{entity_id!r} is not Mermaid-safe (use [A-Za-z0-9_] and "
                    "cannot start with a digit)"
                )

            tz = item.get("trust_zone")
            if tz is not None:
                if not isinstance(tz, str) or not tz:
                    errors.append(f"entity {entity_id!r} has non-string trust_zone")
                elif tz not in tz_ids:
                    warnings.append(
                        f"entity {entity_id!r} references undeclared trust_zone {tz!r}"
                    )

    rels = model.get("relationships", []) or []
    if not isinstance(rels, list):
        errors.append("model.relationships must be a list")
    else:
        for rel in rels:
            if not isinstance(rel, dict):
                warnings.append("model.relationships contains a non-mapping item; skipping")
                continue

            src, dst = rel.get("from"), rel.get("to")
            if isinstance(src, str) and src and src not in entity_ids:
                warnings.append(f"relationship.from references unknown entity id {src!r}")
            if isinstance(dst, str) and dst and dst not in entity_ids:
                warnings.append(f"relationship.to references unknown entity id {dst!r}")

    workflows = model.get("workflows", []) or []
    if workflows and not isinstance(workflows, list):
        errors.append("model.workflows must be a list")
    elif isinstance(workflows, list):
        for wf in workflows:
            if not isinstance(wf, dict):
                warnings.append("model.workflows contains a non-mapping item; skipping")
                continue

            steps = wf.get("steps", []) or []
            wf_id = wf.get("id")
            if not isinstance(steps, list):
                errors.append(f"workflow {wf_id!r} steps must be a list")
                continue

            for step in steps:
                if not isinstance(step, dict):
                    warnings.append(
                        f"workflow {wf_id!r} contains a non-mapping step; skipping"
                    )
                    continue

                src, dst = step.get("from"), step.get("to")
                if isinstance(src, str) and src and src not in entity_ids:
                    warnings.append(
                        f"workflow {wf_id!r} step.from references unknown entity id {src!r}"
                    )
                if isinstance(dst, str) and dst and dst not in entity_ids:
                    warnings.append(
                        f"workflow {wf_id!r} step.to references unknown entity id {dst!r}"
                    )

    return errors, warnings


def build_entity_index(model: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Index entities by ID across sections used by diagrams.

    Args:
        model: Parsed system model mapping.

    Returns:
        Mapping of entity ID -> entity definition mapping.
    """
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
    """Get a workflow by ID, or deterministically fall back to the first workflow.

    Args:
        model: Parsed system model mapping.
        workflow_id: Workflow ID to select.

    Returns:
        The workflow mapping.

    Raises:
        TypeError: If `model["workflows"]` is not a list.
        KeyError: If no workflows exist in the model.
    """
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


def gen_stage_flow(model: dict[str, Any], workflow_id: str) -> str:
    """Generate the stage flow diagram (flowchart LR) from a selected workflow.

    Stage flow is derived from the selected workflow by extracting `to:` endpoints
    that are containers with `kind == "stage"`, preserving step order.

    Args:
        model: Parsed system model mapping.
        workflow_id: Workflow ID to select.

    Returns:
        Mermaid diagram source for the stage flow.
    """
    entities = build_entity_index(model)
    workflow = get_workflow(model, workflow_id)

    steps = sorted(
        workflow.get("steps", []) or [],
        key=lambda s: _as_int(s.get("n")) if isinstance(s, dict) else 0,
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


def gen_trust_boundaries(model: dict[str, Any]) -> str:
    """Generate the trust boundaries view (flowchart TB).

    Derived from:
      - `trust_zones` (for clustering)
      - `relationships` (for edges)

    Selection rule (to keep the diagram bounded):
      - include all cross-trust-zone relationships (both endpoints have zones and differ)
      - include `orchestrator_cli -> *` edges labeled `"invoke stage"`

    Args:
        model: Parsed system model mapping.

    Returns:
        Mermaid diagram source for trust boundaries.
    """
    entities = build_entity_index(model)

    trust_zones = model.get("trust_zones", []) or []
    tz_name: dict[str, Any] = {
        tz.get("id"): tz.get("name", tz.get("id"))
        for tz in trust_zones
        if isinstance(tz, dict)
    } # type: ignore

    def entity_zone(entity_id: str) -> Optional[str]:
        ent = entities.get(entity_id)
        return ent.get("trust_zone") if isinstance(ent, dict) else None

    def entity_label(entity_id: str) -> str:
        ent = entities.get(entity_id)
        if isinstance(ent, dict) and isinstance(ent.get("name"), str):
            return ent["name"]
        return entity_id

    selected_edges: list[dict[str, Any]] = []
    for rel in model.get("relationships", []) or []:
        if not isinstance(rel, dict):
            continue

        src, dst = rel.get("from"), rel.get("to")
        if not (isinstance(src, str) and isinstance(dst, str)):
            continue

        src_zone, dst_zone = entity_zone(src), entity_zone(dst)
        if src_zone and dst_zone and src_zone != dst_zone:
            selected_edges.append(rel)
            continue

        if src == "orchestrator_cli" and rel.get("label") == "invoke stage":
            selected_edges.append(rel)

    node_ids: set[str] = set()
    for rel in selected_edges:
        src = rel.get("from")
        dst = rel.get("to")
        if isinstance(src, str):
            node_ids.add(src)
        if isinstance(dst, str):
            node_ids.add(dst)

    nodes_by_zone: dict[str, list[str]] = {}
    for node_id in sorted(node_ids):
        zone_id = entity_zone(node_id) or "unmodeled"
        nodes_by_zone.setdefault(zone_id, []).append(node_id)

    lines: list[str] = ["flowchart TB"]

    declared_order: list[str] = [
        tz.get("id")
        for tz in trust_zones
        if isinstance(tz, dict) and isinstance(tz.get("id"), str)
    ] # pyright: ignore[reportAssignmentType]
    zone_order: list[str] = (
        [z for z in declared_order if z in nodes_by_zone]
        + [z for z in sorted(nodes_by_zone.keys()) if z not in declared_order]
    )

    for zone_id in zone_order:
        zone_title = str(tz_name.get(zone_id, zone_id))
        lines.append(f'  subgraph {zone_id}["{mm_text(zone_title)}"]')
        for node_id in nodes_by_zone[zone_id]:
            lines.append(f'    {node_id}["{mm_text(entity_label(node_id))}"]')
        lines.append("  end")

    def edge_sort_key(rel: dict[str, Any]) -> tuple[str, str, str]:
        return (
            str(rel.get("from", "")),
            str(rel.get("to", "")),
            str(rel.get("label", "")),
        )

    for rel in sorted(selected_edges, key=edge_sort_key):
        src = rel["from"]
        dst = rel["to"]
        label = rel.get("label") or ""
        if label:
            lines.append(f"  {src} -->|{mm_text(str(label))}| {dst}")
        else:
            lines.append(f"  {src} --> {dst}")

    return "\n".join(lines)


def gen_sequence(model: dict[str, Any], workflow_id: str) -> str:
    """Generate a sequence diagram from the selected workflow's ordered steps.

    Args:
        model: Parsed system model mapping.
        workflow_id: Workflow ID to select.

    Returns:
        Mermaid diagram source for a `sequenceDiagram`.
    """
    entities = build_entity_index(model)
    workflow = get_workflow(model, workflow_id)

    def entity_label(entity_id: str) -> str:
        ent = entities.get(entity_id)
        if isinstance(ent, dict) and isinstance(ent.get("name"), str):
            return ent["name"]
        return entity_id

    steps = sorted(
        workflow.get("steps", []) or [],
        key=lambda s: _as_int(s.get("n")) if isinstance(s, dict) else 0,
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


def gen_run_status_state(_: dict[str, Any]) -> str:
    """Generate a run-status state diagram.

    Notes:
        `system_model.yaml` currently defines `states: []` (no explicit state
        machine), so this returns a stable, spec-level summary.

    Args:
        _: Parsed system model mapping (currently unused).

    Returns:
        Mermaid diagram source for a `stateDiagram-v2`.
    """
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
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Generate Mermaid diagrams from a YAML system model."
    )
    parser.add_argument(
        "--model",
        type=Path,
        default=MODEL_PATH_DEFAULT,
        help="Path to system_model.yaml",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=OUT_DIR_DEFAULT,
        help="Output directory for generated markdown",
    )
    parser.add_argument(
        "--workflow",
        type=str,
        default=WORKFLOW_ID_DEFAULT,
        help="Workflow id to use for stage flow + run sequence diagrams",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Fail generation on validation warnings (e.g., unknown ids, undeclared "
            "trust zones). Errors always fail."
        ),
    )
    args = parser.parse_args()

    model = load_model(args.model)

    errors, warnings = validate_model(model)
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)

    if errors or (args.strict and warnings):
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)

    out_dir: Path = args.out_dir
    write_md(out_dir / "stage_flow.md", "Stage flow", gen_stage_flow(model, args.workflow))
    write_md(
        out_dir / "trust_boundaries.md",
        "Trust boundaries",
        gen_trust_boundaries(model),
    )
    write_md(
        out_dir / "run_sequence.md",
        "Canonical run sequence (v0.1)",
        gen_sequence(model, args.workflow),
    )
    write_md(
        out_dir / "run_status_state.md",
        "Run status (success/partial/failed)",
        gen_run_status_state(model),
    )


if __name__ == "__main__":
    main()