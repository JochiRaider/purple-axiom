from __future__ import annotations

from typing import Any


def gen_run_status_state(_: dict[str, Any]) -> str:
    """Generate a run-status state diagram.

    The model currently defines no explicit state machine, so this returns a
    stable, spec-level summary.
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
