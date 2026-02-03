# docs/project_viz/source/mermaid_gen/cli.py
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .constants import TRUST_VIEW_DEFAULT, WORKFLOW_ID_DEFAULT
from .diagrams.registry import DIAGRAMS, RenderConfig
from .io import load_model
from .validate import validate_model
from .writer import write_md
from .workflow_suite import WorkflowSuiteConfig, render_workflow_suite


def _default_paths() -> tuple[Path, Path]:
    """Compute default model and output paths based on this package location.

    Expected layout:
      docs/project_viz/source/mermaid_gen/cli.py
    """
    pkg_dir = Path(__file__).resolve().parent              # .../source/mermaid_gen
    source_dir = pkg_dir.parent                            # .../source
    project_viz_dir = source_dir.parent                    # .../project_viz
    docs_dir = project_viz_dir.parent                      # .../docs

    model_default = project_viz_dir / "architecture"
    out_default = docs_dir / "diagrams" / "generated"
    return model_default, out_default


def main() -> None:
    """CLI entrypoint."""
    model_default, out_default = _default_paths()

    parser = argparse.ArgumentParser(
        description="Generate Mermaid diagrams from a YAML architecture model."
    )
    parser.add_argument(
        "--model",
        type=Path,
        default=model_default,
        help=(
            "Path to split model directory (docs/project_viz/architecture/) or a "
            "legacy monolithic YAML file (system_model.yaml)."
        ),
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=out_default,
        help="Output directory for generated markdown",
    )
    parser.add_argument(
        "--trust-view",
        type=str,
        choices=("compact", "detailed"),
        default=TRUST_VIEW_DEFAULT,
        help="Trust boundaries diagram style (compact=Option A, detailed=legacy).",
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
    parser.add_argument(
        "--workflow-suite",
        action="store_true",
        help=(
            "Generate per-workflow outputs under workflows/<workflow_id>/ and a "
            "workflows/index.md page. In this mode, only global diagrams (trust "
            "boundaries, run status) are written to the out-dir root."
        ),
    )
    parser.add_argument(
        "--workflow-ids",
        type=str,
        default="",
        help=(
            "Comma-separated workflow ids to include in --workflow-suite mode "
            "(default: all workflows in the model)."
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
    cfg = RenderConfig(workflow_id=args.workflow, trust_view=args.trust_view)
    
    if args.workflow_suite:
        wf_ids = None
        if args.workflow_ids.strip():
            wf_ids = tuple(w.strip() for w in args.workflow_ids.split(",") if w.strip())
        render_workflow_suite(
            model,
            out_dir,
            cfg=WorkflowSuiteConfig(trust_view=args.trust_view, workflow_ids=wf_ids),
        )
        return
    
    for spec in DIAGRAMS:
        diagram_code = spec.render(model, cfg)
        write_md(out_dir / spec.filename, spec.title, diagram_code)
