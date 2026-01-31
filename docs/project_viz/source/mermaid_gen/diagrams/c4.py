# docs/project_viz/source/mermaid_gen/diagrams/c4.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from ..mermaid_fmt import mm_text
from ..model_view import build_entity_index


def _q(text: object) -> str:
    """Quote + Mermaid-escape text for Mermaid C4 macros."""
    return f'"{mm_text(text)}"'


def _require_mapping(val: object, *, path: str) -> dict[str, Any]:
    if not isinstance(val, dict):
        raise TypeError(f"Expected mapping at {path}, got: {type(val).__name__}")
    # best-effort typing
    return val  # type: ignore[return-value]


def _require_str(val: object, *, path: str) -> str:
    if not isinstance(val, str) or not val:
        raise TypeError(f"Expected non-empty string at {path}, got: {val!r}")
    return val


def _section_ids(model: dict[str, Any], section: str) -> set[str]:
    out: set[str] = set()
    for item in model.get(section, []) or []:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            out.add(item["id"])
    return out


def _system_info(model: dict[str, Any]) -> tuple[str, str, str]:
    sys = _require_mapping(model.get("system"), path="model.system")
    sid = _require_str(sys.get("id"), path="model.system.id")
    name = _require_str(sys.get("name"), path="model.system.name")
    desc = sys.get("description")
    if not isinstance(desc, str):
        desc = ""
    return sid, name, desc


@dataclass(frozen=True)
class C4ViewDefaults:
    """Default IDs for the Purple Axiom C4 views.

    These defaults are intentionally conservative (small diagrams). If the model
    evolves, update these IDs rather than inferring new structure.
    """

    # Context view
    context_external_container_ids: tuple[str, ...] = ("matrix_runner",)

    # Container view
    container_actor_ids: tuple[str, ...] = ("operator",)
    container_external_system_ids: tuple[str, ...] = ("matrix_runner",)
    container_internal_container_ids: tuple[str, ...] = (
        "orchestrator_cli",
        "operator_interface",
        "audit_redactor",
    )
    container_internal_datastore_ids: tuple[str, ...] = (
        "run_bundle_store",
        "baseline_library",
        "audit_log_store",
    )

    # Component view
    component_root_container_id: str = "orchestrator_cli"
    component_aggregate_store_id: str = "run_bundle_store"
    component_max_artifact_samples: int = 2


def gen_c4_context(
    model: dict[str, Any],
    *,
    defaults: C4ViewDefaults = C4ViewDefaults(),
) -> str:
    """Generate a Mermaid C4 *Context* diagram from the YAML model.

    The system under analysis is model.system. Internal implementation details
    are collapsed: edges between internal containers and externals are rendered
    as external <-> system relationships.
    """

    system_id, system_name, system_desc = _system_info(model)
    entities = build_entity_index(model)

    actor_ids = _section_ids(model, "actors")
    external_ids = _section_ids(model, "externals")
    container_ids = _section_ids(model, "containers")
    datastore_ids = _section_ids(model, "datastores")

    external_container_ids = set(defaults.context_external_container_ids)
    internal_container_ids = set(container_ids) - external_container_ids
    internal_node_ids = internal_container_ids | datastore_ids
    external_node_ids = set(actor_ids) | set(external_ids) | external_container_ids

    # Collapse internal-boundary edges to the system boundary.
    ordered_external: list[str] = []
    seen_external: set[str] = set()
    ordered_rels: list[tuple[str, str, str, str]] = []
    seen_rels: set[tuple[str, str, str, str]] = set()

    def note_external(eid: str) -> None:
        if eid not in seen_external:
            seen_external.add(eid)
            ordered_external.append(eid)

    for rel in model.get("relationships", []) or []:
        if not isinstance(rel, dict):
            continue
        src, dst = rel.get("from"), rel.get("to")
        if not isinstance(src, str) or not isinstance(dst, str):
            continue

        label = rel.get("label")
        protocol = rel.get("protocol")
        if not isinstance(label, str):
            label = ""
        if not isinstance(protocol, str):
            protocol = ""

        if src in external_node_ids and dst in internal_node_ids:
            note_external(src)
            edge = (src, system_id, label, protocol)
        elif src in internal_node_ids and dst in external_node_ids:
            note_external(dst)
            edge = (system_id, dst, label, protocol)
        else:
            continue

        if edge not in seen_rels:
            seen_rels.add(edge)
            ordered_rels.append(edge)

    lines: list[str] = [
        "C4Context",
        f"title {_q(f'{system_name} — System Context (spec-derived)')}",
    ]

    for ext_id in ordered_external:
        ent = entities.get(ext_id, {})
        if not isinstance(ent, dict):
            ent = {}

        name = ent.get("name", ext_id)
        desc = ent.get("description", "")
        if not isinstance(name, str):
            name = ext_id
        if not isinstance(desc, str):
            desc = ""

        # Actor humans -> Person. Everything else -> System_Ext.
        if ext_id in actor_ids and ent.get("type") == "human":
            lines.append(f"Person({ext_id}, {_q(name)}, {_q(desc)})")
        else:
            lines.append(f"System_Ext({ext_id}, {_q(name)}, {_q(desc)})")

    # Keep context view legible: system description can be long.
    lines.append(
        f"System({system_id}, {_q(system_name)}, {_q(_truncate(system_desc, max_len=140))})"
    )

    for src, dst, label, protocol in ordered_rels:
        lines.append(f"Rel({src}, {dst}, {_q(label)}, {_q(protocol)})")

    return "\n".join(lines)


def gen_c4_container(
    model: dict[str, Any],
    *,
    defaults: C4ViewDefaults = C4ViewDefaults(),
) -> str:
    """Generate a Mermaid C4 *Container* diagram from the YAML model."""

    system_id, system_name, _ = _system_info(model)
    entities = build_entity_index(model)

    declared_ids: set[str] = set()
    lines: list[str] = [
        "C4Container",
        f"title {_q(f'{system_name} — Containers (run host + optional UI)')}",
    ]

    # External people/systems
    for actor_id in defaults.container_actor_ids:
        ent = entities.get(actor_id)
        if not isinstance(ent, dict):
            raise KeyError(f"Missing actor entity: {actor_id}")

        # Default list is "actors", but keep this robust if a system actor appears.
        if ent.get("type") == "human":
            lines.append(
                f"Person({actor_id}, {_q(ent.get('name', actor_id))}, {_q(ent.get('description', ''))})"
            )
        else:
            lines.append(
                f"System_Ext({actor_id}, {_q(ent.get('name', actor_id))}, {_q(ent.get('description', ''))})"
            )
        declared_ids.add(actor_id)

    for sys_id in defaults.container_external_system_ids:
        ent = entities.get(sys_id)
        if not isinstance(ent, dict):
            raise KeyError(f"Missing external system entity: {sys_id}")
        lines.append(
            f"System_Ext({sys_id}, {_q(ent.get('name', sys_id))}, {_q(ent.get('description', ''))})"
        )
        declared_ids.add(sys_id)

    # System boundary
    lines.append(f"System_Boundary({system_id}, {_q(system_name)}) {{")
    declared_ids.add(system_id)

    # Internal containers
    for cid in defaults.container_internal_container_ids:
        ent = entities.get(cid)
        if not isinstance(ent, dict):
            raise KeyError(f"Missing container entity: {cid}")
        lines.append(
            "  "
            + f"Container({cid}, {_q(ent.get('name', cid))}, {_q(ent.get('kind', ''))}, {_q(ent.get('description', ''))})"
        )
        declared_ids.add(cid)

    # Internal datastores (shown as ContainerDb)
    for did in defaults.container_internal_datastore_ids:
        ent = entities.get(did)
        if not isinstance(ent, dict):
            raise KeyError(f"Missing datastore entity: {did}")
        lines.append(
            "  "
            + f"ContainerDb({did}, {_q(ent.get('name', did))}, {_q(ent.get('tech', ''))}, {_q(ent.get('description', ''))})"
        )
        declared_ids.add(did)

    lines.append("}")

    # Relationships (only those between declared nodes), deduped.
    for rel in model.get("relationships", []) or []:
        if not isinstance(rel, dict):
            continue
        src, dst = rel.get("from"), rel.get("to")
        if not isinstance(src, str) or not isinstance(dst, str):
            continue
        if src not in declared_ids or dst not in declared_ids:
            continue
        label = rel.get("label")
        protocol = rel.get("protocol")
        if not isinstance(label, str):
            label = ""
        if not isinstance(protocol, str):
            protocol = ""
        lines.append(f"Rel({src}, {dst}, {_q(label)}, {_q(protocol)})")

    return "\n".join(lines)


def _dedupe_preserve_order(items: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for s in items:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _truncate(text: str, *, max_len: int) -> str:
    """Deterministically truncate text for diagram legibility."""

    text = (text or "").strip()
    if len(text) <= max_len:
        return text
    # Use a single Unicode ellipsis for compactness.
    return text[: max(0, max_len - 1)].rstrip() + "…"


def _summarize_artifacts(
    artifacts: list[str],
    *,
    max_samples: int,
) -> str:
    """Summarize a list of artifact paths into a compact label fragment."""

    artifacts = _dedupe_preserve_order([a for a in artifacts if isinstance(a, str) and a])
    if not artifacts:
        return "artifacts"

    # Group by first path segment (e.g., logs/, report/, security/). Keep first
    # occurrence for each group, preserving original order.
    by_prefix: dict[str, str] = {}
    ordered_prefixes: list[str] = []
    for p in artifacts:
        prefix = p.split("/", 1)[0]
        if prefix not in by_prefix:
            by_prefix[prefix] = p
            ordered_prefixes.append(prefix)

    # Always include the first prefix. Prefer including logs/* if present.
    chosen: list[str] = []
    if ordered_prefixes:
        chosen.append(by_prefix[ordered_prefixes[0]])

    if "logs" in by_prefix and by_prefix["logs"] not in chosen and len(chosen) < max_samples:
        chosen.append(by_prefix["logs"])

    for pref in ordered_prefixes[1:]:
        if len(chosen) >= max_samples:
            break
        candidate = by_prefix[pref]
        if candidate not in chosen:
            chosen.append(candidate)

    remaining = max(0, len(ordered_prefixes) - len({c.split('/', 1)[0] for c in chosen}))
    if remaining:
        return "; ".join(chosen) + f"; +{remaining} more"
    return "; ".join(chosen)


def gen_c4_component_orchestrator_internals(
    model: dict[str, Any],
    *,
    defaults: C4ViewDefaults = C4ViewDefaults(),
) -> str:
    """Generate a Mermaid C4 *Component* diagram for orchestrator internals.

    View intent:
    - Show stage components executing inside the orchestrator trust boundary.
    - Show key external dependencies.
    - Collapse run-bundle subdirectories into a single Run Bundle Store node.
    """

    _, system_name, _ = _system_info(model)
    entities = build_entity_index(model)

    root_container_id = defaults.component_root_container_id
    agg_store_id = defaults.component_aggregate_store_id

    container_items = [c for c in (model.get("containers", []) or []) if isinstance(c, dict)]
    container_ids = _section_ids(model, "containers")
    datastore_ids = _section_ids(model, "datastores")
    external_ids = _section_ids(model, "externals")

    # Components: all stages + in-process helpers used by stages.
    stage_ids: set[str] = {c["id"] for c in container_items if c.get("kind") == "stage" and isinstance(c.get("id"), str)}

    helper_ids: set[str] = set()
    for rel in model.get("relationships", []) or []:
        if not isinstance(rel, dict):
            continue
        if rel.get("protocol") != "in_process":
            continue
        src, dst = rel.get("from"), rel.get("to")
        if not isinstance(src, str) or not isinstance(dst, str):
            continue
        if src in stage_ids and dst in container_ids and dst != root_container_id:
            helper_ids.add(dst)
        if dst in stage_ids and src in container_ids and src != root_container_id:
            helper_ids.add(src)

    component_ids: set[str] = stage_ids | helper_ids

    # Preserve model order for component declarations.
    ordered_components: list[str] = []
    for c in container_items:
        cid = c.get("id")
        if isinstance(cid, str) and cid in component_ids and cid != root_container_id:
            ordered_components.append(cid)

    # External dependencies used by these components (preserve relationship order).
    ordered_externals: list[str] = []
    seen_ext: set[str] = set()

    def note_ext(eid: str) -> None:
        if eid not in seen_ext:
            seen_ext.add(eid)
            ordered_externals.append(eid)

    # Track stage outputs for aggregation to the run-bundle store.
    stage_artifacts: dict[str, list[str]] = {sid: [] for sid in stage_ids}

    # Relationship lines in-order, deduped.
    rel_lines: list[tuple[str, str, str, str]] = []
    seen_rels: set[tuple[str, str, str, str]] = set()

    for rel in model.get("relationships", []) or []:
        if not isinstance(rel, dict):
            continue
        src, dst = rel.get("from"), rel.get("to")
        if not isinstance(src, str) or not isinstance(dst, str):
            continue

        # Skip orchestrator -> stage invocation edges (not part of this view).
        if src == root_container_id or dst == root_container_id:
            continue

        label = rel.get("label")
        protocol = rel.get("protocol")
        if not isinstance(label, str):
            label = ""
        if not isinstance(protocol, str):
            protocol = ""

        edge = (src, dst, label, protocol)
        if edge in seen_rels:
            continue
        seen_rels.add(edge)

        # Collect external dependencies.
        if src in component_ids and dst in external_ids:
            note_ext(dst)
        if dst in component_ids and src in external_ids:
            note_ext(src)

        # Collect stage outputs to local filesystem datastores for aggregation.
        if (
            src in stage_ids
            and dst in datastore_ids
            and protocol == "filesystem"
            and rel.get("interaction") == "file_drop"
        ):
            data = rel.get("data")
            if isinstance(data, list):
                stage_artifacts[src].extend([d for d in data if isinstance(d, str)])
            continue  # aggregated later

        # Keep component-to-component and component-to-external edges.
        if (src in component_ids and dst in component_ids) or (
            src in component_ids and dst in external_ids
        ) or (src in external_ids and dst in component_ids):
            edge = (src, dst, label, protocol)
            if edge not in seen_rels:
                seen_rels.add(edge)
                rel_lines.append(edge)

    # Add aggregated stage output edges.
    for stage_id in [c for c in ordered_components if c in stage_ids]:
        artifacts = stage_artifacts.get(stage_id, [])
        summary = _summarize_artifacts(artifacts, max_samples=defaults.component_max_artifact_samples)
        edge = (stage_id, agg_store_id, f"write {summary}", "filesystem")
        if edge not in seen_rels:
            seen_rels.add(edge)
            rel_lines.append(edge)

    # Render
    lines: list[str] = [
        "C4Component",
        f"title {_q(f'{system_name} — Orchestrator internals (stages + key deps)')}",
    ]

    for ext_id in ordered_externals:
        ent = entities.get(ext_id)
        if not isinstance(ent, dict):
            continue
        lines.append(f"System_Ext({ext_id}, {_q(ent.get('name', ext_id))}, {_q(ent.get('description', ''))})")

    # Aggregate store (run bundle)
    store_ent = entities.get(agg_store_id)
    if not isinstance(store_ent, dict):
        raise KeyError(f"Missing datastore entity for component view: {agg_store_id}")
    lines.append(
        f"ContainerDb({agg_store_id}, {_q(store_ent.get('name', agg_store_id))}, {_q(store_ent.get('tech', ''))}, {_q(store_ent.get('description', ''))})"
    )

    # Orchestrator boundary containing stage components
    root_ent = entities.get(root_container_id)
    if not isinstance(root_ent, dict):
        raise KeyError(f"Missing root container entity for component view: {root_container_id}")
    lines.append(f"Container_Boundary({root_container_id}, {_q(root_ent.get('name', root_container_id))}) {{")

    for cid in ordered_components:
        ent = entities.get(cid)
        if not isinstance(ent, dict):
            continue
        lines.append(
            "  "
            + f"Component({cid}, {_q(ent.get('name', cid))}, {_q(ent.get('kind', ''))}, {_q(ent.get('description', ''))})"
        )

    lines.append("}")

    for src, dst, label, protocol in rel_lines:
        lines.append(f"Rel({src}, {dst}, {_q(label)}, {_q(protocol)})")

    return "\n".join(lines)
