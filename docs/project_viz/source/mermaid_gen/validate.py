from __future__ import annotations

from typing import Any, Optional, Tuple

from .constants import ENTITY_SECTIONS
from .mermaid_fmt import MERMAID_ID_RE


def validate_model(model: dict[str, Any]) -> Tuple[list[str], list[str]]:
    """Perform lightweight structural validation to keep the model diagram-safe."""
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

                msg = step.get("message")
                if isinstance(msg, str) and ("\n" in msg or "\r" in msg):
                    warnings.append(
                        f"workflow {wf_id!r} step n={step.get('n')!r} message contains a newline; "
                        "this can break Mermaid rendering (consider folding to one line)"
                    )

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
