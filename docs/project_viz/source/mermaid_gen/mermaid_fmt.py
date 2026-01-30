from __future__ import annotations

import html
import re

# Mermaid node/subgraph IDs must be alphanumeric/underscore and must not start
# with a digit.
MERMAID_ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def mermaid_block(code: str) -> str:
    """Wrap Mermaid source in a Markdown Mermaid code fence."""
    return "```mermaid\n" + code.rstrip() + "\n```\n"


def mm_text(text: str) -> str:
    """Escape text for Mermaid labels."""
    normalized = re.sub(r"\s+", " ", html.unescape(str(text))).strip()
    return (
        normalized.replace("&", "#amp;")
        .replace("<", "#lt;")
        .replace(">", "#gt;")
        .replace('"', "#quot;")
        .replace("|", "#124;")
    )


def mm_edge_label(text: str) -> str:
    """Format a Mermaid *edge label* (the text inside `-->|...|`) safely."""
    raw = str(text)
    escaped = mm_text(raw)
    stripped = raw.lstrip()
    if stripped and not re.match(r"[A-Za-z0-9_]", stripped[0]):
        return f'"{escaped}"'
    return escaped
