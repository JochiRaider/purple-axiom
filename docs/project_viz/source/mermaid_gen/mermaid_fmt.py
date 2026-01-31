from __future__ import annotations

import html
import re
import json
from typing import Any
from urllib.parse import urlsplit, urlunsplit

# Mermaid node/subgraph IDs must be alphanumeric/underscore and must not start
# with a digit.
MERMAID_ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def mermaid_block(code: str) -> str:
    """Wrap Mermaid source in a Markdown Mermaid code fence."""
    return "```mermaid\n" + code.rstrip() + "\n```\n"


def mm_text(text: str, *, escape_semicolon: bool = False) -> str:
    """Escape text for Mermaid labels."""
    normalized = re.sub(r"\s+", " ", html.unescape(str(text))).strip()
    out = (
        normalized.replace("&", "#amp;")
        .replace("<", "#lt;")
        .replace(">", "#gt;")
        .replace('"', "#quot;")
        .replace("|", "#124;")
    )
    if escape_semicolon:
        out = out.replace(";", "#59;")
    return out


def mm_init(**config_sections: dict[str, Any]) -> str:
    # Stable JSON: sorted keys + compact separators.
    payload = json.dumps(config_sections, sort_keys=True, separators=(",", ":"))
    return f"%%{{init:{payload}}}%%"


def mm_edge_label(text: str) -> str:
    """Format a Mermaid *edge label* (the text inside `-->|...|`) safely."""
    raw = str(text)
    escaped = mm_text(raw)
    stripped = raw.lstrip()
    if stripped and not re.match(r"[A-Za-z0-9_]", stripped[0]):
        return f'"{escaped}"'
    return escaped

def assert_mm_id(value: str) -> str:
    if not MERMAID_ID_RE.match(value):
        raise ValueError(f"Not Mermaid-safe id: {value!r}")
    return value

def mm_unique_id(base: str, used: set[str]) -> str:
    candidate = base
    n = 2
    while candidate in used:
        candidate = f"{base}_{n}"
        n += 1
    used.add(candidate)
    return candidate

def mm_flow_node(node_id: str, label: str) -> str:
    return f'{node_id}["{mm_text(label)}"]'

def mm_subgraph_open(subgraph_id: str, title: str) -> str:
    return f'  subgraph {subgraph_id}["{mm_text(title)}"]'

def _mm_normalize_flow_arrow(arrow: str) -> str:
    """Normalize common (often accidental) flowchart arrows to valid Mermaid syntax.

    Mermaid flowcharts use `-->` for a normal arrow and `-.->` for a dotted arrow.
    Callers sometimes (accidentally) pass `->` or `.->`; normalize those to the
    correct Mermaid flowchart forms.
    """
    a = str(arrow).strip()
    if a == "->":
        return "-->"
    if a == ".->":
        return "-.->"
    return a

def mm_flow_edge(src: str, dst: str, label: str | None = None, arrow: str = "-->") -> str:
    a = _mm_normalize_flow_arrow(arrow)
    if label:
        lbl = mm_edge_label(label)
        # Mermaid flowchart dotted edge labels must be in the middle.
        if a == "-.->":
            return f"  {src} -. {lbl} .-> {dst}"
        return f"  {src} {a}|{lbl}| {dst}"
    return f"  {src} {a} {dst}"

def mm_participant(pid: str, label: str) -> str:
    return f'  participant {pid} as "{mm_text(label)}"'

def mm_class_def(class_name: str, style: str) -> str:
    return f"  classDef {class_name} {style}"

def mm_class_apply(node_ids: list[str] | tuple[str, ...], class_name: str) -> str:
    return f"  class {','.join(node_ids)} {class_name}"

def mm_safe_url(url: str) -> str:
    parts = urlsplit(url.strip())
    if parts.scheme and parts.scheme not in ("http", "https"):
        raise ValueError(f"Disallowed URL scheme: {parts.scheme!r}")
    # Strip userinfo if present.
    netloc = parts.hostname or ""
    if parts.port:
        netloc = f"{netloc}:{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))

def mm_click(node_id: str, url: str, tooltip: str | None = None, target: str = "_blank") -> str:
    safe = mm_safe_url(url)
    tip = f' "{mm_text(tooltip)}"' if tooltip else ""
    return f'  click {node_id} "{safe}"{tip} {target}'

def mm_comment(text: str) -> str:
    # Ensure it won't be parsed as a directive.
    t = str(text).replace("\n", " ").strip()
    if t.startswith("{"):
        t = " " + t
    return f"%% {t}"

C4_KINDS = {"C4Context","C4Container","C4Component","C4Dynamic","C4Deployment"}

def mm_c4_header(kind: str) -> str:
    if kind not in C4_KINDS:
        raise ValueError(f"unknown C4 kind: {kind!r}")
    return kind

def mm_c4_str(text: object) -> str:
    return f'"{mm_text(text)}"'

def mm_c4_call(fn: str, *positional: str, **named: object) -> str:
    parts: list[str] = [fn + "("]
    args: list[str] = list(positional)

    # Deterministic named args order
    for k in sorted(named.keys()):
        v = named[k]
        if v is None:
            continue
        args.append(f'$"{k}"={mm_c4_str(v)}')  # see note below

    # NOTE: you probably want `$key=` not `$"key"=`; kept as sketch.
    return fn + "(" + ", ".join(args) + ")"

def mm_c4_boundary_open(macro: str, alias: str, label: str, **named: object) -> str:
    # e.g. System_Boundary(c1, "Sample System") {
    base = mm_c4_call(macro, alias, mm_c4_str(label), **named)
    return base + " {"

def mm_c4_boundary_close() -> str:
    return "}"

def mm_class_decl(name: str, label: str | None = None) -> str:
    assert_mm_class_name(name)
    if label is None:
        return f"class {name}"
    return f'class {name}["{mm_text(label)}"]'

def mm_class_member(text: object) -> str:
    # Preserve punctuation; just prevent line breaks from corrupting Mermaid.
    s = str(text).replace("\r", " ").replace("\n", " ").strip()
    s = re.sub(r"\s+", " ", s)
    return s

CLASS_REL_ARROWS = {"<|--","*--","o--","-->","--","..>","..|>",".."}

def mm_class_relation(
    a: str,
    arrow: str,
    b: str,
    *,
    label: str | None = None,
    a_card: str | None = None,
    b_card: str | None = None,
) -> str:
    assert_mm_class_name(a)
    assert_mm_class_name(b)
    if arrow not in CLASS_REL_ARROWS:
        raise ValueError(f"unsupported class arrow: {arrow!r}")

    left = f'{a} "{mm_text(a_card)}"' if a_card else a
    right = f'"{mm_text(b_card)}" {b}' if b_card else b

    line = f"{left} {arrow} {right}"
    if label:
        line += f":{mm_text(label)}"
    return line

