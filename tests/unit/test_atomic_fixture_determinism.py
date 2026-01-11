import hashlib
import json
from pathlib import Path

import pytest


FIXTURE_DIR = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "runner"
    / "atomic"
    / "golden"
    / "T1059.001"
)


def canonical_json_bytes_jcs_subset(obj: object) -> bytes:
    """
    Test-only canonical JSON for JCS-safe subset (strings/ints/bools/null/objects/arrays).
    This is sufficient for the current fixtures, which avoid floats and other tricky cases.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonicalize_atomics_root(value: str) -> str:
    # v0.1 canonicalization tokens per docs/spec/032: evidence-only expansions become $ATOMICS_ROOT.
    # Keep this as simple string replacement (deterministic).
    value = value.replace("PathToAtomicsFolder", "$ATOMICS_ROOT")
    value = value.replace("$PathToPayloads", "$ATOMICS_ROOT")
    value = value.replace("PathToPayloads", "$ATOMICS_ROOT")
    return value


def substitute_placeholders(template: str, resolved_inputs: dict[str, str]) -> str:
    out = template
    for k, v in resolved_inputs.items():
        out = out.replace(f"#{{{k}}}", v)
    return out


def resolve_inputs(extracted: dict, overrides: dict[str, str], max_passes: int = 8) -> dict[str, str]:
    defaults = {k: v.get("default") for k, v in extracted.get("input_arguments", {}).items()}
    merged = dict(defaults)
    merged.update(overrides)

    # Validate required inputs (no default and no override)
    for k, default in defaults.items():
        if default is None and (k not in overrides or overrides[k] in (None, "")):
            raise ValueError(f"missing_required_input:{k}")

    # Fixed-point substitution inside input values
    current = {k: ("" if v is None else str(v)) for k, v in merged.items()}

    for _ in range(max_passes):
        changed = False
        next_map: dict[str, str] = {}
        for k, v in current.items():
            nv = substitute_placeholders(v, current)
            next_map[k] = nv
            changed |= (nv != v)
        current = next_map
        if not changed:
            break
    else:
        raise ValueError("input_resolution_cycle_or_growth")

    # Canonicalize environment-dependent expansions for identity-bearing materials
    current = {k: canonicalize_atomics_root(v) for k, v in current.items()}
    return current


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_atomic_fixture_resolved_inputs_sha256_and_action_key():
    extracted = load_json(FIXTURE_DIR / "extracted" / "atomic_test_extracted.json")
    overrides = load_json(FIXTURE_DIR / "inputs" / "input_args_override.json")
    expected_resolved_inputs = load_json(FIXTURE_DIR / "inputs" / "resolved_inputs.json")
    expected_resolved_sha = load_text(FIXTURE_DIR / "inputs" / "resolved_inputs_sha256.txt")
    expected_action_key = load_text(FIXTURE_DIR / "identity" / "action_key.txt")

    resolved_inputs = resolve_inputs(extracted, overrides)
    assert resolved_inputs == expected_resolved_inputs

    resolved_sha = sha256_hex(canonical_json_bytes_jcs_subset(resolved_inputs))
    assert resolved_sha == expected_resolved_sha

    action_key_basis = load_json(FIXTURE_DIR / "identity" / "action_key_basis_v1.json")
    # Guard: fixture basis must match the expected resolved_inputs_sha256.
    assert action_key_basis["parameters"]["resolved_inputs_sha256"] == resolved_sha

    action_key = sha256_hex(canonical_json_bytes_jcs_subset(action_key_basis))
    assert action_key == expected_action_key


def test_atomic_fixture_command_post_merge():
    extracted = load_json(FIXTURE_DIR / "extracted" / "atomic_test_extracted.json")
    overrides = load_json(FIXTURE_DIR / "inputs" / "input_args_override.json")
    expected_command_post_merge = load_text(FIXTURE_DIR / "execution" / "command_post_merge.txt")

    resolved_inputs = resolve_inputs(extracted, overrides)

    cmd_templates = extracted["executor"]["command"]
    assert isinstance(cmd_templates, list) and len(cmd_templates) == 1

    cmd = substitute_placeholders(cmd_templates[0], resolved_inputs)
    cmd = canonicalize_atomics_root(cmd)

    assert cmd == expected_command_post_merge
