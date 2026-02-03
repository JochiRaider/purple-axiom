from __future__ import annotations

from pathlib import Path

from .mermaid_fmt import mermaid_block


def write_md(path: Path, title: str, diagram_code: str) -> None:
    """Write a titled Markdown file containing a Mermaid diagram block."""
    path.parent.mkdir(parents=True, exist_ok=True)
    content = f"# {title}\n\n{mermaid_block(diagram_code)}"
    path.write_text(content, encoding="utf-8")


def write_text_md(path: Path, title: str, body_md: str) -> None:
    """Write a titled Markdown file containing arbitrary Markdown body.

    This is intentionally separate from write_md(), which always wraps the body
    as a Mermaid diagram block.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    body = (body_md or "").rstrip() + "\n"
    content = f"# {title}\n\n{body}"
    path.write_text(content, encoding="utf-8")
