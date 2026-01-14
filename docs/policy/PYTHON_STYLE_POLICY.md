---
title: Python style and quality policy
description: Defines Python coding, formatting, typing, testing, and determinism standards for Codex agents and human contributors.
status: draft
version: 2.1
last_updated: 2026-01-14
category: policy
related:
  - AGENTS_POLICY.md
  - SUPPORTED_VERSIONS.md
  - 100_test_strategy_ci.md
---

# Python style and quality policy

This policy defines Python coding, formatting, typing, testing, and determinism expectations for
contributors and local coding agents.

## Overview

**Summary**: This policy aligns Python implementation practices with CI gates and deterministic
artifact requirements. Tooling is authoritative where configured; conventions fill gaps only when
tooling does not enforce a behavior.

This document is optimized for local coding agents (Codex, GPT-5.2-Codex) and for deterministic CI
gating. Agents MUST treat this policy as authoritative for Python work in this repository.

## Purpose

This policy defines Python implementation standards for this repository.

Primary goals:

- **Tool-driven quality**: Formatting, linting, typing, and testing outcomes are determined by
  configured tooling, not manual judgment
- **Deterministic outputs**: Code that emits artifacts MUST produce stable, reproducible results
- **Agent compatibility**: Instructions are explicit and unambiguous to support Codex-style agents
- **CI parity**: Local development MUST match CI behavior

Tools are authoritative. Prose conventions exist only where tooling does not fully enforce the
desired behavior.

## Scope

This document covers:

- Python source code, scripts, and tooling in this repository
- Formatting, linting, typing, testing, and golden fixture generation
- Determinism and safety requirements for artifact-producing code paths

This document does NOT cover:

- Non-Python code style policies (Markdown is governed by the Markdown style guide)
- Deployment/runtime orchestration policies unless explicitly implemented in Python

## Integration with AGENTS.md

**Summary**: This policy is referenced from root `AGENTS.md` and provides Python-specific guidance
that extends repository-wide operating rules.

This policy is referenced from root `AGENTS.md` under "How to validate changes" and "Change
discipline". Agents SHOULD:

- Treat this document as authoritative for Python-specific guidance
- Follow root `AGENTS.md` for repository-wide operating rules
- When instructions conflict, prefer this policy for Python code and `AGENTS.md` for workflow

Scoped `AGENTS.md` files in Python-heavy directories (e.g., `src/`, `tools/`) MAY add local
constraints that extend this policy.

## Toolchain and CI pins (normative)

**Summary**: CI MUST run using pinned versions; local environments SHOULD match or MUST NOT bless
golden fixtures.

See [SUPPORTED_VERSIONS.md](SUPPORTED_VERSIONS.md) for the authoritative toolchain pins. The tables
below summarize the Python-relevant subset.

### Toolchain baseline (v0.1)

| Component | Pinned version | Enforcement                                             |
| --------- | -------------: | ------------------------------------------------------- |
| Python    |         3.12.3 | `.python-version`, `pyproject.toml` (`requires-python`) |
| uv        |         0.9.18 | CI MUST verify `uv --version` and fail on mismatch      |

### Dependencies

| Dependency         | Pinned version | Used by                    | Notes                         |
| ------------------ | -------------: | -------------------------- | ----------------------------- |
| pytest             |          9.0.2 | Unit + integration tests   | CI gate                       |
| pytest-regressions |          2.9.1 | Golden/regression fixtures | CI gate for "golden outputs"  |
| ruff               |        0.14.11 | Lint + format              | Lint + format gate            |
| pyright            |        1.1.408 | Type checking              | Type-check gate               |
| mdformat           |          1.0.0 | MD format checking         | MD format gate                |
| pre-commit         |          4.5.1 | Local + CI hook runner     | CI SHOULD enforce hook parity |

## Environment management (uv)

**Summary**: The project uses `uv` for deterministic environment management. All Python tooling MUST
be invoked via `uv run`.

- The project uses a `uv`-managed virtual environment for development and CI execution
- Contributors MUST run Python tooling via `uv run <tool>` to ensure the intended environment
- The repository standardizes the virtual environment location at `.venv/` (ignored by Git)
- CI MUST verify `uv --version` matches the pinned version before running any gates

### Why uv

Codex agents work best with explicit, deterministic environment management. `uv` provides:

- Fast, reproducible dependency resolution
- Single command for sync and run (`uv sync`, `uv run`)
- Lockfile-based reproducibility

Do NOT introduce pip venvs, Poetry, or `requirements.txt` unless explicitly required.

## Canonical quality gates

**Summary**: These gates define pass/fail criteria for CI. Agents MUST pass all gates before
finalizing changes.

Implementations MUST pass these gates in CI. Agents SHOULD run these before finalizing changes.

### Commands

```bash
# Format check (does not modify files)
uv run ruff format --check .

# Lint check
uv run ruff check .

# Type check
uv run pyright

# Test suite
uv run pytest
```

### Gate behavior

| Gate   | Tool          | Failure behavior                                      |
| ------ | ------------- | ----------------------------------------------------- |
| Format | `ruff format` | CI fails; agent MUST run `ruff format` to fix         |
| Lint   | `ruff check`  | CI fails; agent MUST fix or add justified suppression |
| Types  | `pyright`     | CI fails; agent MUST add type hints or fix errors     |
| Tests  | `pytest`      | CI fails; agent MUST fix failing tests                |

Agents SHOULD run format and lint gates before committing changes. The model is trained to run all
tests mentioned in AGENTS.md, so these commands will be executed.

## Baseline style references (PEP 8 / PEP 257)

- Code style SHOULD follow PEP 8 by default
- Formatting and lint outcomes produced by ruff are authoritative when there is any discrepancy
- Docstrings SHOULD follow PEP 257 guidance where docstrings are required
- The repository MAY adopt additional docstring conventions (Google/NumPy) only if enforced by
  tooling and documented here

## Formatting and linting (ruff)

**Summary**: Ruff is the single source of truth for formatting and lint rules. Do not hand-format
beyond what ruff produces.

- Ruff is the single source of truth for formatting and lint rules

- Contributors MUST NOT manually "style format" code beyond what ruff produces

- Lint suppressions MUST be local and justified with a short comment:

  ```python
  # ruff: noqa: E501 - URL exceeds line length, cannot be wrapped
  LONG_URL = "https://..."
  ```

- New and modified files MUST be formatted and lint-clean before review unless a staged migration is
  explicitly declared

### Agent instructions

When modifying Python code:

1. Make the functional change
1. Run `uv run ruff format <file>` on modified files
1. Run `uv run ruff check <file>` and fix any errors
1. Do NOT hand-format beyond what ruff produces

## Typing policy (pyright)

**Summary**: Strong typing improves agent comprehension and reduces hallucinated behavior. New code
MUST include type hints at function boundaries.

### Requirements

- New and modified code MUST include type hints at function boundaries:
  - Public functions and classes
  - Module entrypoints
  - Artifact-producing code paths
- Internal helper functions SHOULD be typed when non-trivial
- Prefer `pathlib.Path` over raw strings for filesystem paths
- Avoid `Any` unless explicitly justified; if used, constrain it as close to the boundary as
  possible

### Type hint patterns for agents

Explicit types help agents understand intent:

```python
# Good: explicit types, agent understands the contract
def process_events(
    events: list[dict[str, Any]],
    output_path: Path,
    *,
    sort_key: str = "timestamp",
) -> int:
    """Process events and write to output. Returns count of processed events."""
    ...

# Avoid: loose types, agent may hallucinate structure
def process_events(events, output_path, sort_key="timestamp"):
    ...
```

### Prefer explicit models over loose dicts

```python
# Good: explicit model, agent understands fields
@dataclass
class EventRecord:
    event_id: str
    timestamp: datetime
    payload: dict[str, Any]

# Avoid: loose dict, agent may invent fields
event: dict[str, Any] = {...}
```

## Docstrings

**Summary**: Docstrings document intent and contracts for public interfaces. They MUST be present
for public modules, functions, classes, and CLI entrypoints.

### Requirements

Docstrings MUST be present for:

- Public modules that define stable interfaces (schemas, contracts, canonicalization)
- Public functions/classes exported as part of a library surface
- CLI entrypoints and subcommands

Docstrings SHOULD be present for other non-trivial functions.

Docstrings MUST NOT contain secrets or unredacted sensitive material.

### Format

Use imperative mood and be explicit about inputs, outputs, and side effects:

```python
def normalize_event(raw: dict[str, Any], schema_version: str) -> OCSFEvent:
    """Normalize a raw event dict into an OCSF event.

    Args:
        raw: Raw event dictionary from telemetry source.
        schema_version: Target OCSF schema version (e.g., "1.7.0").

    Returns:
        Normalized OCSF event with required fields populated.

    Raises:
        NormalizationError: If required fields are missing or malformed.
    """
```

## Determinism requirements

**Summary**: Artifact-producing code MUST produce stable, reproducible output given identical
inputs. This section defines the constraints that ensure determinism.

Because this project depends on reproducibility, code that emits artifacts MUST produce stable
output given the same inputs.

### Determinism checklist for artifact code

Before committing code that produces run bundle artifacts:

- [ ] All iterations use explicit sort keys (documented in code)
- [ ] Timestamps use `datetime.now(timezone.utc)`, never `datetime.now()`
- [ ] Random operations use seeded `random.Random(seed)` instances
- [ ] Filesystem paths use `pathlib.Path`, normalized before serialization
- [ ] Dict serialization uses `sort_keys=True` or equivalent
- [ ] No reliance on `set` iteration order for outputs

### Ordering

- Ordering MUST be explicit when it affects serialization
- Sort keys MUST be documented in code comments or docstrings
- Never rely on filesystem iteration order or dict insertion order for output stability

```python
# Good: explicit sort for deterministic output
events = sorted(events, key=lambda e: (e["timestamp"], e["event_id"]))

# Bad: relies on implicit ordering
for event in events:  # order depends on source
    ...
```

### Randomness

- Randomness MUST be seeded
- The seed MUST be recorded in the run bundle if applicable
- Use `random.Random(seed)` instances, not module-level `random.*` functions

```python
# Good: seeded, reproducible
rng = random.Random(seed=42)
sample = rng.sample(population, k=10)

# Bad: unseeded, non-deterministic
sample = random.sample(population, k=10)
```

### Timestamps

- Timestamps MUST be timezone-explicit
- Avoid implicit local-time behavior
- Prefer ISO 8601 format with explicit UTC offset

```python
# Good: explicit UTC
from datetime import datetime, timezone
now = datetime.now(timezone.utc)

# Bad: implicit local time
now = datetime.now()
```

### Filesystem paths

- Use `pathlib.Path` for all filesystem operations
- Normalize paths before comparison or serialization
- Never assume path separator (use `Path`, not string concatenation)

```python
# Good: pathlib with normalization
output_path = Path(base_dir) / "events" / "normalized.parquet"
canonical = output_path.resolve()

# Bad: string concatenation, platform-dependent
output_path = base_dir + "/events/normalized.parquet"
```

## Error handling

**Summary**: Use domain-specific exceptions for operational failures. Error messages MUST be
actionable and MUST NOT leak sensitive data.

### Principles

- Use exceptions for programmer errors and unrecoverable stage failures
- For expected operational failures (missing file, missing mapping), raise a domain-specific
  exception type
- Error messages MUST be actionable and MUST NOT leak secrets or sensitive data

### Exception pattern for agents

```python
class NormalizationError(Exception):
    """Raised when event normalization fails."""
    pass

class MissingMappingError(NormalizationError):
    """Raised when no mapping exists for an event type."""
    def __init__(self, event_type: str, source: str):
        super().__init__(f"No mapping for event_type={event_type} from source={source}")
        self.event_type = event_type
        self.source = source
```

### Error message patterns

Error messages MUST be actionable but MUST NOT leak sensitive data:

```python
# Good: actionable, redacted
raise MissingMappingError(
    f"No mapping for event_type={event_type} from source={source}"
)

# Bad: leaks raw event content
raise ValueError(f"Cannot process event: {raw_event}")

# Bad: not actionable
raise ValueError("Mapping error")
```

See [ADR-0003-redaction-policy.md](ADR-0003-redaction-policy.md) for the authoritative redaction
rules.

## Logging and redaction

**Summary**: Logging MUST NOT emit secrets or unredacted sensitive material. Use placeholder values
and reference IDs instead of raw data.

- Logging MUST NOT emit secrets
- Use placeholder values and reference IDs instead of raw sensitive data
- When logging structured data, avoid dumping entire events unless the redaction policy permits
- Any "debug dump" feature MUST be opt-in and MUST be compatible with the redaction policy

```python
# Good: reference ID, no sensitive data
logger.info("Processing event", extra={"event_id": event.event_id, "source": source})

# Bad: dumps entire event, may contain secrets
logger.debug(f"Processing event: {event}")
```

See [ADR-0003-redaction-policy.md](ADR-0003-redaction-policy.md) for the authoritative redaction
rules.

## Testing and fixtures (pytest, pytest-regressions)

**Summary**: Tests validate behavior deterministically. Golden fixtures MUST be generated only under
pinned toolchain versions.

### Requirements

- New behavior MUST include tests
- Regression tests MUST be deterministic and stable across OS and filesystem differences
- Golden fixtures MUST be generated only under pinned toolchain versions
- Test data MUST NOT include secrets; use synthetic or redacted values

### Test naming convention

```python
def test_<function>_<scenario>():
    """Test description."""
    ...

# Examples:
def test_normalize_event_happy_path():
def test_normalize_event_missing_required_field():
def test_normalize_event_invalid_timestamp():
```

### Agent instructions for testing

When adding or modifying functionality:

1. Write or update tests that cover the change
1. Run `uv run pytest <test_file>` to verify tests pass
1. For new test files, follow the naming convention `test_<module>.py`
1. Prefer explicit assertions over broad `assert result` statements

```python
# Good: explicit assertion, clear failure message
assert event.event_id == "expected-id", f"Expected 'expected-id', got {event.event_id}"

# Avoid: unclear failure
assert event
```

### Golden fixture workflow

1. Ensure you are using the pinned toolchain (`uv --version`, `python --version`)
1. Run `uv run pytest --regtest-reset` to regenerate fixtures
1. Review the diff to ensure changes are intentional
1. Commit the updated fixtures with a clear message

## Dependency management (uv)

**Summary**: Dependencies MUST be added intentionally and recorded in the lockfile.

- Dependencies MUST be added intentionally and recorded in the lockfile
- New dependencies SHOULD be pinned or constrained in a way compatible with the version-pin policy
- Avoid large transitive dependency trees unless justified

### Adding a dependency

```bash
# Add a runtime dependency
uv add <package>

# Add a development dependency
uv add --dev <package>

# Sync environment after changes
uv sync
```

## File layout conventions

```text
.
├── src/                    # Production code (single import root)
│   └── purple_axiom/       # Package root
├── tests/                  # Test files (mirrors src/ layout)
│   └── test_*.py
├── mappings/               # Field mapping packs
├── tools/                  # Tooling and scripts
├── docs/                   # Documentation
├── pyproject.toml          # Project configuration
└── uv.lock                 # Dependency lockfile
```

- Production code lives under `src/` (src layout)
- Tests live under `tests/` and mirror the package structure
- Tooling and scripts live under `tools/`

## Agent-specific guidance

**Summary**: These instructions are normative for Codex agents operating on Python code in this
repository.

### Pre-flight checklist (before any Python edit)

1. Identify the files that will be modified
1. Read existing code patterns in those files
1. Check if a related test file exists in `tests/`
1. Note any domain-specific exception types in use

### Post-edit checklist (before finalizing)

1. Run `uv run ruff format <modified_files>`
1. Run `uv run ruff check <modified_files>` — fix errors or add justified suppressions
1. Run `uv run pyright <modified_files>` — add type hints if missing
1. Run `uv run pytest <relevant_test_files>` — all tests MUST pass
1. Verify no unrelated files were modified

### Scope constraints

When implementing Python code, agents MUST:

- Implement EXACTLY and ONLY what is requested
- Not add extra features, utilities, or "nice to have" code
- Not refactor unrelated code unless explicitly asked
- Follow existing patterns in the codebase

### When uncertain

- Check existing code for patterns before inventing new ones
- Prefer the simpler interpretation when requirements are ambiguous
- Note uncertainty in comments rather than making assumptions
- Minimize the scope of changes when context is incomplete

## Acceptance criteria

This policy is satisfied when:

- The repository exposes canonical commands for format, lint, type-check, and test
- CI enforces the pinned toolchain and fails on mismatches
- Golden fixtures are never blessed from unpinned local toolchains
- Determinism constraints are explicitly enforced where artifacts are emitted
- Agents can follow this policy to produce code that passes CI without human intervention

## Key decisions

- Tool-driven quality over manual judgment reduces ambiguity for agents
- Determinism checklist makes reproducibility requirements actionable
- Pre-flight and post-edit checklists provide explicit agent workflows
- Cross-references to SUPPORTED_VERSIONS.md and AGENTS_POLICY.md establish authoritative sources
- Error message patterns enforce redaction compliance without blocking actionable diagnostics

## References

- [SUPPORTED_VERSIONS.md](SUPPORTED_VERSIONS.md) — authoritative toolchain pins
- [AGENTS_POLICY.md](AGENTS_POLICY.md) — agent instruction file policy
- [ADR-0003-redaction-policy.md](ADR-0003-redaction-policy.md) — redaction rules
- [100_test_strategy_ci.md](100_test_strategy_ci.md) — test strategy and CI gates
- [MARKDOWN_STYLE_GUIDE.md](MARKDOWN_STYLE_GUIDE.md) — markdown conventions

## Changelog

| Date       | Version | Changes                                                                                                                                                                                                                                                                      |
| ---------- | ------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2026-01-14 | 2.1     | Added AGENTS.md integration section; added determinism checklist; added pre-flight/post-edit checklists; added error message patterns; added Key decisions and References sections; cross-referenced SUPPORTED_VERSIONS.md; restructured for markdown style guide compliance |
| 2026-01-14 | 2.0     | Added agent-specific guidance; expanded type hint and testing sections; added explicit commands; restructured for Codex compatibility                                                                                                                                        |
| —          | 1.0     | Initial policy                                                                                                                                                                                                                                                               |
