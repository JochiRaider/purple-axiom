# docs/project_viz/source/mermaid_gen/validate.py
from __future__ import annotations

from typing import Any, Optional, Tuple, Literal
from dataclasses import dataclass, field

from .constants import ENTITY_SECTIONS
from .mermaid_fmt import MERMAID_ID_RE

Severity = Literal["error", "warning"]


@dataclass(frozen=True)
class ValidationIssue:
    """Structured validation issue for callers that want more than strings."""

    severity: Severity
    code: str
    message: str
    path: str = ""
    hint: Optional[str] = None


@dataclass(frozen=True)
class ValidateConfig:
    """Validation configuration.

    NOTE: The CLI currently uses the legacy `validate_model()` wrapper, which
    returns `(errors, warnings)` as lists of strings. This config is exposed for
    richer callers (e.g., CI annotations) via `validate_model_issues()`.
    """

    # Rule controls
    ignore: set[str] = field(default_factory=set)
    escalate: set[str] = field(default_factory=set)

    # Mermaid-breaker guards
    check_mermaid_safe_trust_zone_refs: bool = True
    check_mermaid_safe_workflow_step_ids: bool = True


def validate_model_issues(
    model: dict[str, Any], cfg: Optional[ValidateConfig] = None
) -> list[ValidationIssue]:
    """Return structured validation issues.

    This is the canonical validator. `validate_model()` is a backwards-
    compatible wrapper for the CLI.
    """

    cfg = cfg or ValidateConfig()
    issues: list[ValidationIssue] = []

    def emit(
        severity: Severity,
        code: str,
        message: str,
        path: str = "",
        hint: Optional[str] = None,
    ) -> None:
        if code in cfg.ignore:
            return
        final_severity: Severity = (
            "error" if (severity == "warning" and code in cfg.escalate) else severity
        )
        issues.append(
            ValidationIssue(
                severity=final_severity,
                code=code,
                message=message,
                path=path,
                hint=hint,
            )
        )

    trust_zones = model.get("trust_zones", []) or []
    if not isinstance(trust_zones, list):
        emit("error", "E_TRUST_ZONES_NOT_LIST", "model.trust_zones must be a list")
        trust_zones = []

    tz_ids: set[str] = set()
    for i, tz in enumerate(trust_zones):
        if not isinstance(tz, dict):
            emit(
                "warning",
                "W_TRUST_ZONES_ITEM_NOT_MAPPING",
                "model.trust_zones contains a non-mapping item; skipping",
                path=f"/trust_zones/{i}",
            )
            continue

        tz_id = tz.get("id")
        if not isinstance(tz_id, str) or not tz_id:
            emit(
                "error",
                "E_TRUST_ZONE_MISSING_ID",
                "model.trust_zones item missing string `id`",
                path=f"/trust_zones/{i}/id",
            )
            continue

        tz_ids.add(tz_id)
        if not MERMAID_ID_RE.match(tz_id):
            emit(
                "error",
                "E_TRUST_ZONE_ID_NOT_MERMAID_SAFE",
                "trust_zone id "
                f"{tz_id!r} is not Mermaid-safe (use [A-Za-z0-9_] and cannot "
                "start with a digit)",
                path=f"/trust_zones/{i}/id",
            )

    entity_ids: dict[str, str] = {}
    for section in ENTITY_SECTIONS:
        items = model.get(section, []) or []
        if not isinstance(items, list):
            emit(
                "error",
                "E_SECTION_NOT_LIST",
                f"model.{section} must be a list",
                path=f"/{section}",
            )
            continue

        for j, item in enumerate(items):
            if not isinstance(item, dict):
                emit(
                    "warning",
                    "W_SECTION_ITEM_NOT_MAPPING",
                    f"model.{section} contains a non-mapping item; skipping",
                    path=f"/{section}/{j}",
                )
                continue

            entity_id = item.get("id")
            if not isinstance(entity_id, str) or not entity_id:
                emit(
                    "error",
                    "E_ENTITY_MISSING_ID",
                    f"model.{section} item missing string `id`",
                    path=f"/{section}/{j}/id",
                )
                continue

            if entity_id in entity_ids:
                emit(
                    "error",
                    "E_ENTITY_DUPLICATE_ID",
                    f"duplicate entity id {entity_id!r} in {section} "
                    f"(also in {entity_ids[entity_id]})",
                    path=f"/{section}/{j}/id",
                )
            else:
                entity_ids[entity_id] = section

            if not MERMAID_ID_RE.match(entity_id):
                emit(
                    "error",
                    "E_ENTITY_ID_NOT_MERMAID_SAFE",
                    "entity id "
                    f"{entity_id!r} is not Mermaid-safe (use [A-Za-z0-9_] and "
                    "cannot start with a digit)",
                    path=f"/{section}/{j}/id",
                )

            tz = item.get("trust_zone")
            if tz is not None:
                if not isinstance(tz, str) or not tz:
                    emit(
                        "error",
                        "E_ENTITY_TRUST_ZONE_NOT_STRING",
                        f"entity {entity_id!r} has non-string trust_zone",
                        path=f"/{section}/{j}/trust_zone",
                    )
                    emit(
                        "error",
                        "E_ENTITY_TRUST_ZONE_NOT_STRING",
                        f"entity {entity_id!r} has non-string trust_zone",
                        path=f"/{section}/{j}/trust_zone",
                    )
                else:
                    # Mermaid-breaker: trust boundaries renders trust zones as
                    # Mermaid subgraph IDs.
                    if (
                        cfg.check_mermaid_safe_trust_zone_refs
                        and tz not in tz_ids
                        and not MERMAID_ID_RE.match(tz)
                    ):
                        emit(
                            "error",
                            "E_ENTITY_TRUST_ZONE_NOT_MERMAID_SAFE",
                            f"entity {entity_id!r} references trust_zone {tz!r} "
                            "that is not Mermaid-safe (use [A-Za-z0-9_] and cannot "
                            "start with a digit)",
                            path=f"/{section}/{j}/trust_zone",
                        )
                    elif tz not in tz_ids:
                        emit(
                            "warning",
                            "W_ENTITY_TRUST_ZONE_UNDECLARED",
                            f"entity {entity_id!r} references undeclared trust_zone {tz!r}",
                            path=f"/{section}/{j}/trust_zone",
                        )
    rels = model.get("relationships", []) or []
    if not isinstance(rels, list):
        emit("error", "E_RELATIONSHIPS_NOT_LIST", "model.relationships must be a list")
    else:
        for i, rel in enumerate(rels):
            if not isinstance(rel, dict):
                emit(
                    "warning",
                    "W_RELATIONSHIPS_ITEM_NOT_MAPPING",
                    "model.relationships contains a non-mapping item; skipping",
                    path=f"/relationships/{i}",
                )
                continue

            src, dst = rel.get("from"), rel.get("to")
            if isinstance(src, str) and src and src not in entity_ids:
                emit(
                    "warning",
                    "W_REL_FROM_UNKNOWN_ENTITY",
                    f"relationship.from references unknown entity id {src!r}",
                    path=f"/relationships/{i}/from",
                )
            if isinstance(dst, str) and dst and dst not in entity_ids:
                emit(
                    "warning",
                    "W_REL_TO_UNKNOWN_ENTITY",
                    f"relationship.to references unknown entity id {dst!r}",
                    path=f"/relationships/{i}/to",
                )

    workflows = model.get("workflows", []) or []
    if workflows and not isinstance(workflows, list):
        emit("error", "E_WORKFLOWS_NOT_LIST", "model.workflows must be a list")
    elif isinstance(workflows, list):
        wf_ids_seen: dict[str, int] = {}
        for wf_i, wf in enumerate(workflows):
            if not isinstance(wf, dict):
                emit(
                    "warning",
                    "W_WORKFLOWS_ITEM_NOT_MAPPING",
                    "model.workflows contains a non-mapping item; skipping",
                    path=f"/workflows/{wf_i}",
                )
                continue

            wf_id = wf.get("id")
            if not isinstance(wf_id, str) or not wf_id:
                emit(
                    "error",
                    "E_WORKFLOW_MISSING_ID",
                    "workflow is missing string `id`",
                    path=f"/workflows/{wf_i}/id",
                )
            else:
                if wf_id in wf_ids_seen:
                    emit(
                        "error",
                        "E_WORKFLOW_DUPLICATE_ID",
                        f"duplicate workflow id {wf_id!r} (also in workflows[{wf_ids_seen[wf_id]}])",
                        path=f"/workflows/{wf_i}/id",
                    )
                else:
                    wf_ids_seen[wf_id] = wf_i

                if not MERMAID_ID_RE.match(wf_id):
                    emit(
                        "warning",
                        "W_WORKFLOW_ID_NOT_MERMAID_SAFE",
                        "workflow id "
                        f"{wf_id!r} is not Mermaid-safe (use [A-Za-z0-9_] and cannot "
                        "start with a digit)",
                        path=f"/workflows/{wf_i}/id",
                        hint="Use snake_case (A-Za-z0-9_); do not start with a digit",
                    )

            steps = wf.get("steps", []) or []
            if not isinstance(steps, list):
                emit(
                    "error",
                    "E_WORKFLOW_STEPS_NOT_LIST",
                    f"workflow {wf_id!r} steps must be a list",
                    path=f"/workflows/{wf_i}/steps",
                )
                continue

            for step_i, step in enumerate(steps):
                if not isinstance(step, dict):
                    emit(
                        "warning",
                        "W_WORKFLOW_STEP_NOT_MAPPING",
                        f"workflow {wf_id!r} contains a non-mapping step; skipping",
                        path=f"/workflows/{wf_i}/steps/{step_i}",
                     )
                    continue

                msg = step.get("message")
                if isinstance(msg, str) and ("\n" in msg or "\r" in msg):
                    emit(
                        "warning",
                        "W_WORKFLOW_STEP_MESSAGE_NEWLINE",
                        f"workflow {wf_id!r} step n={step.get('n')!r} message contains a newline; "
                        "this can break Mermaid rendering (consider folding to one line)",
                        path=f"/workflows/{wf_i}/steps/{step_i}/message",
                    )

                src, dst = step.get("from"), step.get("to")
                # Mermaid-breaker: sequence diagrams render step.from/step.to as
                # Mermaid participant IDs.
                if isinstance(src, str) and src:
                    if cfg.check_mermaid_safe_workflow_step_ids and not MERMAID_ID_RE.match(
                        src
                    ):
                        emit(
                            "error",
                            "E_WORKFLOW_STEP_FROM_NOT_MERMAID_SAFE",
                            f"workflow {wf_id!r} step.from value {src!r} is not Mermaid-safe "
                            "(use [A-Za-z0-9_] and cannot start with a digit)",
                            path=f"/workflows/{wf_i}/steps/{step_i}/from",
                        )
                    elif src not in entity_ids:
                        emit(
                            "warning",
                            "W_WORKFLOW_STEP_FROM_UNKNOWN_ENTITY",
                            f"workflow {wf_id!r} step.from references unknown entity id {src!r}",
                            path=f"/workflows/{wf_i}/steps/{step_i}/from",
                        )

                if isinstance(dst, str) and dst:
                    if cfg.check_mermaid_safe_workflow_step_ids and not MERMAID_ID_RE.match(
                        dst
                    ):
                        emit(
                            "error",
                            "E_WORKFLOW_STEP_TO_NOT_MERMAID_SAFE",
                            f"workflow {wf_id!r} step.to value {dst!r} is not Mermaid-safe "
                            "(use [A-Za-z0-9_] and cannot start with a digit)",
                            path=f"/workflows/{wf_i}/steps/{step_i}/to",
                        )
                    elif dst not in entity_ids:
                        emit(
                            "warning",
                            "W_WORKFLOW_STEP_TO_UNKNOWN_ENTITY",
                            f"workflow {wf_id!r} step.to references unknown entity id {dst!r}",
                            path=f"/workflows/{wf_i}/steps/{step_i}/to",
                        )

    return issues


def validate_model(model: dict[str, Any]) -> Tuple[list[str], list[str]]:
    """Perform lightweight structural validation to keep the model diagram-safe."""
    issues = validate_model_issues(model)
    errors = [iss.message for iss in issues if iss.severity == "error"]
    warnings = [iss.message for iss in issues if iss.severity == "warning"]
    return errors, warnings