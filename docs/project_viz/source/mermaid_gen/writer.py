from __future__ import annotations

from pathlib import Path

from .mermaid_fmt import mermaid_block


def write_md(path: Path, title: str, diagram_code: str) -> None:
    """Write a titled Markdown file containing a Mermaid diagram block."""
    path.parent.mkdir(parents=True, exist_ok=True)
    content = f"# {title}\n\n{mermaid_block(diagram_code)}"
    path.write_text(content, encoding="utf-8")
