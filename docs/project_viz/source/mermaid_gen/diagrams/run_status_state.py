# docs/project_viz/source/mermaid_gen/diagrams/run_status_state.py
from __future__ import annotations

from typing import Any, Mapping


def gen_run_status_state(ctx: Mapping[str, Any]) -> str:
    """Generate a run-status state diagram (representational).
    Authoritative semantics for `manifest.status` and exit codes live in:
    - ADR-0005 (stage outcomes and failure classification)
    - 025_data_contracts (stage outcome contract + status derivation)

    Options (ctx):
    - include_exit_codes (bool, default True): annotate terminal statuses with exit codes.
    - include_authority_note (bool, default True): include a Mermaid note listing authority refs.
     """

    include_exit_codes = bool(ctx.get("include_exit_codes", True))
    include_authority_note = bool(ctx.get("include_authority_note", True))

    def _exit_suffix(code: int) -> str:
        return f" (exit {code})" if include_exit_codes else ""

    failed_label = (
        '  Running --> Failed: any enabled stage outcome has status="failed" '
        'and fail_mode="fail_closed" (dominates partial)'
    )
    partial_label = (
        '  Running --> Partial: else if any enabled stage outcome has status="failed" '
        'and fail_mode="warn_and_skip"'
    )
    success_label = (
        '  Running --> Success: else (all enabled stage outcomes have status="success")'
    )

    lines: list[str] = ["stateDiagram-v2", "  [*] --> Running"]

    if include_authority_note:
        lines.extend(
            [
                "  note right of Running",
                "    representational (non-normative)",
                "    authority: ADR-0005, 025_data_contracts",
                "  end note",
            ]
        )

    lines.extend(
        [
            failed_label + _exit_suffix(20),
            partial_label + _exit_suffix(10),
            success_label + _exit_suffix(0),
            "  Failed --> [*]",
            "  Partial --> [*]",
            "  Success --> [*]",
        ]
    )

    return "\n".join(lines) + "\n"
