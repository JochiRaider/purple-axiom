# docs/project_viz/source/mermaid_gen/io.py
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import yaml

from .constants import MODEL_PART_FILES


def _sanitize_yaml_for_pyyaml(raw: str) -> tuple[str, list[tuple[int, str, str]]]:
    """Return (sanitized_yaml, changes).

    Each change is (line_number_1_based, original_line, new_line).
    """
    changes: list[tuple[int, str, str]] = []
    out_lines: list[str] = []

    for i, line in enumerate(raw.splitlines(), start=1):
        match = re.match(
            r"^(\s*(?:-\s*)?(?:excerpt|definition|description|section_heading|message|name|purpose|title|label):\s*)(.+)$",
            line,
        )
        if not match:
            out_lines.append(line)
            continue

        prefix, value = match.group(1), match.group(2)

        # Already quoted or a block scalar.
        if value.startswith(("'", '"', "|", ">")):
            out_lines.append(line)
            continue

        # PyYAML rejects plain scalars containing ":" followed by whitespace or EOL
        # (e.g., "Network profile: LAN UI", "foo:", "foo:\tbar").
        # Preserve any trailing inline comment (space-# ...).
        body, comment = value, ""
        m = re.match(r"^(.*?)(\s+#.*)$", value)
        if m:
            body, comment = m.group(1), m.group(2)

        if re.search(r":(?=\s|$)", body):
            escaped = body.replace("\\", "\\\\").replace('"', '\\"')
            new_line = f'{prefix}"{escaped}"{comment}'
            out_lines.append(new_line)
            if new_line != line:
                changes.append((i, line, new_line))
        else:
            out_lines.append(line)

    sanitized = "\n".join(out_lines) + ("\n" if raw.endswith("\n") else "")
    return sanitized, changes


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")

    try:
        data = yaml.safe_load(raw)
    except Exception:
        sanitized, changes = _sanitize_yaml_for_pyyaml(raw)
        try:
            data = yaml.safe_load(sanitized)
        except Exception as e2:
            raise ValueError(f"Failed to parse YAML {path}: {e2}") from e2

        # Warn with specifics (cap to avoid spam)
        if changes:
            print(
                f"warning: parsed {path} after sanitizing {len(changes)} line(s); "
                "consider quoting values containing ':' followed by whitespace",
                file=sys.stderr,
            )
            for (ln, old, new) in changes[:10]:
                print(f"warning: {path}:{ln}: {old}", file=sys.stderr)
                print(f"warning: {path}:{ln}: {new}", file=sys.stderr)
            if len(changes) > 10:
                print(f"warning: (and {len(changes) - 10} more)", file=sys.stderr)

    if not isinstance(data, dict):
        raise TypeError(
            f"Top-level YAML must be a mapping in {path}, got {type(data).__name__}"
        )

    return data


def _deep_merge_model(
    dst: dict[str, Any], src: dict[str, Any], *, src_path: Path
) -> None:
    """Deep-merge `src` into `dst` with deterministic, safe semantics.

    Merge rules:
      - missing key -> copy
      - list + list -> concatenate (preserve file order)
      - dict + dict -> recursive merge
      - scalar conflicts -> error (unless equal)
    """
    for key, value in src.items():
        if key not in dst:
            dst[key] = value
            continue

        existing = dst[key]
        if isinstance(existing, list) and isinstance(value, list):
            dst[key] = existing + value
            continue

        if isinstance(existing, dict) and isinstance(value, dict):
            _deep_merge_model(existing, value, src_path=src_path)
            continue

        if existing == value:
            continue

        raise ValueError(
            f"Model merge conflict on key {key!r} from {src_path}: "
            f"existing type={type(existing).__name__}, new type={type(value).__name__}"
        )


def load_model(path: Path) -> dict[str, Any]:
    """Load the YAML system model (split directory or monolithic file)."""
    if not path.exists():
        raise FileNotFoundError(str(path))

    # Convenience: if a split-part file was provided, assume its parent directory
    # is the model root.
    if path.is_file() and path.name in set(MODEL_PART_FILES):
        path = path.parent

    if path.is_dir():
        model_dir = path
        merged: dict[str, Any] = {}

        # Deterministic merge order for the split model.
        for filename in MODEL_PART_FILES:
            part_path = model_dir / filename
            if not part_path.exists():
                # Only 90_notes.yaml is expected to be optional; others may be
                # present/absent depending on how the repo is evolving.
                continue
            part = _load_yaml_mapping(part_path)
            _deep_merge_model(merged, part, src_path=part_path)

        # workflows/*.yaml (each typically contains `workflows: [...]`).
        workflows_dir = model_dir / "workflows"
        if workflows_dir.exists() and workflows_dir.is_dir():
            for wf_path in sorted(workflows_dir.glob("*.yaml")):
                wf_doc = _load_yaml_mapping(wf_path)
                _deep_merge_model(merged, wf_doc, src_path=wf_path)

        return merged

    # Legacy monolithic file mode.
    return _load_yaml_mapping(path)
