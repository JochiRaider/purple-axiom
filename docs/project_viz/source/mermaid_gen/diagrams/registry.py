from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .run_sequence import gen_sequence
from .run_status_state import gen_run_status_state
from .stage_flow import gen_stage_flow
from .trust_boundaries import gen_trust_boundaries

Model = dict[str, Any]
RenderFn = Callable[[Model, "RenderConfig"], str]


@dataclass(frozen=True)
class RenderConfig:
    workflow_id: str
    trust_view: str


@dataclass(frozen=True)
class DiagramSpec:
    diagram_id: str
    title: str
    filename: str
    render: RenderFn


def _render_stage_flow(model: Model, cfg: RenderConfig) -> str:
    return gen_stage_flow(model, cfg.workflow_id)


def _render_trust_boundaries(model: Model, cfg: RenderConfig) -> str:
    return gen_trust_boundaries(model, view=cfg.trust_view)


def _render_run_sequence(model: Model, cfg: RenderConfig) -> str:
    return gen_sequence(model, cfg.workflow_id)


def _render_run_status_state(model: Model, _: RenderConfig) -> str:
    return gen_run_status_state(model)


DIAGRAMS: list[DiagramSpec] = [
    DiagramSpec(
        diagram_id="stage_flow",
        title="Stage flow",
        filename="stage_flow.md",
        render=_render_stage_flow,
    ),
    DiagramSpec(
        diagram_id="trust_boundaries",
        title="Trust boundaries",
        filename="trust_boundaries.md",
        render=_render_trust_boundaries,
    ),
    DiagramSpec(
        diagram_id="run_sequence",
        title="Canonical run sequence (v0.1)",
        filename="run_sequence.md",
        render=_render_run_sequence,
    ),
    DiagramSpec(
        diagram_id="run_status_state",
        title="Run status (success/partial/failed)",
        filename="run_status_state.md",
        render=_render_run_status_state,
    ),
]
