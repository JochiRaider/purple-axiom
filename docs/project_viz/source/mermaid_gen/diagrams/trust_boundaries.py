from __future__ import annotations

import re
from collections import Counter
from typing import Any, Optional

from ..constants import TRUST_VIEW_DEFAULT
from ..mermaid_fmt import mm_edge_label, mm_text
from ..model_view import build_entity_index


def gen_trust_boundaries(model: dict[str, Any], view: str = TRUST_VIEW_DEFAULT) -> str:
    """Generate the trust boundaries view (flowchart TB)."""
    if view == "detailed":
        return gen_trust_boundaries_detailed(model)
    return gen_trust_boundaries_compact(model)


def gen_trust_boundaries_compact(model: dict[str, Any]) -> str:
    """Generate a compact trust boundaries view (Option A)."""
    entities = build_entity_index(model)

    trust_zones = model.get("trust_zones", []) or []
    tz_name: dict[str, Any] = {
        tz.get("id"): tz.get("name", tz.get("id"))
        for tz in trust_zones
        if isinstance(tz, dict)
    }  # type: ignore

    def entity_zone(entity_id: str) -> Optional[str]:
        ent = entities.get(entity_id)
        return ent.get("trust_zone") if isinstance(ent, dict) else None

    def entity_label(entity_id: str) -> str:
        ent = entities.get(entity_id)
        if isinstance(ent, dict) and isinstance(ent.get("name"), str):
            return ent["name"]
        return entity_id

    def is_stage(entity_id: str) -> bool:
        ent = entities.get(entity_id)
        return bool(isinstance(ent, dict) and ent.get("kind") == "stage")

    # Infer the "stage trust zone" (typically CI environment) from the model.
    stage_zone_counts: Counter[str] = Counter()
    for ent_id, ent in entities.items():
        if not (isinstance(ent, dict) and ent.get("kind") == "stage"):
            continue
        tz = ent.get("trust_zone")
        if isinstance(tz, str) and tz:
            stage_zone_counts[tz] += 1
    pipeline_zone: str = (
        stage_zone_counts.most_common(1)[0][0] if stage_zone_counts else "ci_environment"
    )

    # Infer the "local filesystem trust zone" from datastores (most common).
    datastore_zone_counts: Counter[str] = Counter()
    for item in model.get("datastores", []) or []:
        if not isinstance(item, dict):
            continue
        tz = item.get("trust_zone")
        if isinstance(tz, str) and tz:
            datastore_zone_counts[tz] += 1
    workspace_zone: str = (
        datastore_zone_counts.most_common(1)[0][0]
        if datastore_zone_counts
        else "local_filesystem"
    )

    # Avoid collisions with real entity IDs.
    synthetic_ids: set[str] = set()

    def unique_synthetic_id(base: str) -> str:
        candidate = base
        n = 2
        while candidate in entities or candidate in synthetic_ids:
            candidate = f"{base}_{n}"
            n += 1
        synthetic_ids.add(candidate)
        return candidate

    agg_pipeline_id = unique_synthetic_id("agg_ci_pipeline")
    agg_workspace_id = unique_synthetic_id("agg_ci_workspace")

    agg_labels: dict[str, str] = {
        agg_pipeline_id: "CI Pipeline (all stages)",
        agg_workspace_id: "CI Workspace (run bundles + artifact stores)",
    }

    stage_ids: set[str] = {eid for eid in entities.keys() if is_stage(eid)}

    def bucket(entity_id: str) -> str:
        # Collapse stage containers into a single pipeline node (only when in the inferred zone).
        if entity_id in stage_ids and (entity_zone(entity_id) == pipeline_zone):
            return agg_pipeline_id
        # Collapse local filesystem entities into a single workspace node.
        if entity_zone(entity_id) == workspace_zone:
            return agg_workspace_id
        return entity_id

    # Select the underlying edges (same selection rule as legacy),
    # then bucket + summarize.
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

    # Bucket edges and accumulate labels to allow summarization.
    bucketed: dict[tuple[str, str], list[str]] = {}
    for rel in selected_edges:
        src = rel.get("from")
        dst = rel.get("to")
        if not (isinstance(src, str) and isinstance(dst, str)):
            continue

        src_b, dst_b = bucket(src), bucket(dst)
        if src_b == dst_b:
            continue

        raw_label = rel.get("label") or ""
        label = str(raw_label) if raw_label is not None else ""
        bucketed.setdefault((src_b, dst_b), []).append(label)

    def summarize_labels(src: str, dst: str, labels: list[str]) -> str:
        distinct = sorted({l for l in labels if l})
        if not distinct:
            return ""

        # Special case: pipeline <-> workspace is the main hairball; summarize aggressively.
        if src == agg_pipeline_id and dst == agg_workspace_id:
            has_read = any(re.search(r"\bread\b", l, re.IGNORECASE) for l in distinct)
            has_write = any(
                re.search(
                    r"\b(write|publish|append|create|mutate|materialize|preserve)\b",
                    l,
                    re.IGNORECASE,
                )
                for l in distinct
            )
            if has_read and has_write:
                return "read/write artifacts"
            if has_read:
                return "read artifacts"
            if has_write:
                return "write/publish artifacts"
            return "artifacts"

        if len(distinct) == 1:
            return distinct[0]

        max_show = 2
        if len(distinct) <= max_show:
            return "; ".join(distinct)
        return "; ".join(distinct[:max_show]) + f"; +{len(distinct) - max_show} more"

    node_ids: set[str] = set()
    for (src_b, dst_b) in bucketed.keys():
        node_ids.add(src_b)
        node_ids.add(dst_b)

    def bucket_zone(node_id: str) -> str:
        if node_id == agg_pipeline_id:
            return pipeline_zone
        if node_id == agg_workspace_id:
            return workspace_zone
        return entity_zone(node_id) or "unmodeled"

    def bucket_label(node_id: str) -> str:
        if node_id in agg_labels:
            return agg_labels[node_id]
        return entity_label(node_id)

    nodes_by_zone: dict[str, list[str]] = {}
    for node_id in sorted(node_ids):
        nodes_by_zone.setdefault(bucket_zone(node_id), []).append(node_id)

    declared_order: list[str] = [
        tz.get("id")
        for tz in trust_zones
        if isinstance(tz, dict) and isinstance(tz.get("id"), str)
    ]  # pyright: ignore[reportAssignmentType]
    zone_order: list[str] = (
        [z for z in declared_order if z in nodes_by_zone]
        + [z for z in sorted(nodes_by_zone.keys()) if z not in declared_order]
    )

    lines: list[str] = [
        '%%{init: {"flowchart": {"curve":"linear", "useMaxWidth": false}} }%%',
        "flowchart TB",
    ]

    for zone_id in zone_order:
        zone_title = str(tz_name.get(zone_id, zone_id))
        lines.append(f'  subgraph {zone_id}["{mm_text(zone_title)}"]')
        lines.append("    direction TB")
        for node_id in nodes_by_zone[zone_id]:
            lines.append(f'    {node_id}["{mm_text(bucket_label(node_id))}"]')
        lines.append("  end")

    for (src_b, dst_b) in sorted(bucketed.keys()):
        label = summarize_labels(src_b, dst_b, bucketed[(src_b, dst_b)])
        if label:
            lines.append(f"  {src_b} -->|{mm_edge_label(label)}| {dst_b}")
        else:
            lines.append(f"  {src_b} --> {dst_b}")

    lines.append("  classDef aggregate stroke-dasharray: 6 3")
    lines.append(f"  class {agg_pipeline_id},{agg_workspace_id} aggregate")

    return "\n".join(lines)


def gen_trust_boundaries_detailed(model: dict[str, Any]) -> str:
    """Generate the detailed trust boundaries view (legacy, edge-level)."""
    entities = build_entity_index(model)

    trust_zones = model.get("trust_zones", []) or []
    tz_name: dict[str, Any] = {
        tz.get("id"): tz.get("name", tz.get("id"))
        for tz in trust_zones
        if isinstance(tz, dict)
    }  # type: ignore

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
    ]  # pyright: ignore[reportAssignmentType]
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
            edge_label = mm_edge_label(str(label))
            lines.append(f"  {src} -->|{edge_label}| {dst}")
        else:
            lines.append(f"  {src} --> {dst}")

    return "\n".join(lines)
