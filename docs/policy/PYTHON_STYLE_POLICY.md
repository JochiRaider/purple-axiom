---
title: Python style and quality policy
description: Defines Python coding, formatting, typing, testing, and determinism standards for Codex agents and human contributors.
status: draft
---

# Python style and quality policy

## Purpose

This policy defines Python implementation standards for this repository. It is optimized for local
coding agents (Codex, GPT-5.2-Codex) and for deterministic CI gating.

Tools are authoritative. Prose conventions exist only where tooling does not fully enforce the
desired behavior.

## Scope

In scope:

- Python source code, scripts, and tooling in this repository.
- Formatting, linting, typing, testing, and golden fixture generation.
- Determinism and safety requirements for artifact-producing code paths.

Out of scope:

- Non-Python code style policies (Markdown is governed by the Markdown policy/tooling).
- Deployment/runtime orchestration policies unless explicitly implemented in Python.

## Toolchain and CI pins (normative for CI and guidance for local)

CI MUST run using the pinned toolchain versions below. Local developer environments SHOULD match
these pins. If local versions differ, they MUST NOT be used to generate or bless golden fixtures.

Toolchain baseline (v0.1):

- Python: **3.12.3**
  - Enforcement hooks: `.python-version` and `pyproject.toml` (`requires-python`) SHOULD be set to
    prevent drift.
- uv: **0.9.18**
  - Enforcement hooks: CI SHOULD run `uv --version` and MUST fail if it differs from the pinned
    value.

| Dependency         | Pinned version | Used by                    | Notes                         |
| ------------------ | -------------: | -------------------------- | ----------------------------- |
| pytest             |          9.0.2 | Unit + integration tests   | CI gate                       |
| pytest-regressions |          2.9.1 | Golden/regression fixtures | CI gate for "golden outputs"  |
| ruff               |        0.14.11 | Lint + format              | Lint + format gate            |
| pyright            |        1.1.408 | Type checking              | Type-check gate               |
| mdformat           |          1.0.0 | MD format checking         | MD format gate                |
| pre-commit         |          4.5.1 | Local + CI hook runner     | CI SHOULD enforce hook parity |

## Environment management (uv)

- The project uses a `uv`-managed virtual environment for development and CI execution.
- Contributors MUST run Python tooling via `uv run <tool>` (for example, `uv run pytest`) to ensure
  the intended environment is used.
- The repository SHOULD standardize the virtual environment location (recommended: `.venv/`) and
  ensure it is ignored by Git.
- CI MUST verify `uv --version` matches the pinned version before running any gates.

## Canonical quality gates

Implementations MUST pass these gates in CI:

- Format: ruff format
- Lint: ruff check
- Types: pyright
- Tests: pytest

The repository MUST provide canonical commands (or wrappers) for these gates.

TODO: record the exact commands once `pyproject.toml`, task runners, and CI workflows exist.

## Baseline style references (PEP 8 / PEP 257)

- Code style SHOULD follow PEP 8 by default. Formatting and lint outcomes produced by ruff are
  authoritative when there is any discrepancy.
- Docstrings SHOULD follow PEP 257 guidance where docstrings are required. The repository MAY adopt
  additional docstring conventions (Google/Numpy) only if enforced by tooling and documented here.

## Formatting and linting (ruff)

- Ruff is the single source of truth for formatting and lint rules.
- Contributors MUST NOT manually “style format” code beyond what ruff produces.
- Lint suppressions MUST be local and justified with a short comment.
- New and modified files MUST be formatted and lint-clean before review unless a staged migration
  is explicitly declared.

TODO: record the selected ruff rule sets and any project-specific exceptions once the
`pyproject.toml` config is created.

## Typing policy (pyright)

- New and modified code MUST include type hints at function boundaries:
  - public functions/classes,
  - module entrypoints,
  - artifact-producing code paths.
- Internal helper functions SHOULD be typed when non-trivial.
- Prefer `pathlib.Path` over raw strings for filesystem paths.
- Avoid `Any` unless explicitly justified; if used, constrain it as close to the boundary as
  possible.

TODO: define pyright strictness mode (recommended: start at standard, tighten per module as
interfaces stabilize).

## Docstrings

- Docstrings MUST be present for:
  - public modules that define stable interfaces (schemas, contracts, canonicalization),
  - public functions/classes exported as part of a library surface,
  - CLI entrypoints and subcommands.
- Docstrings SHOULD be present for other non-trivial functions.
- Docstrings MUST NOT contain secrets or unredacted sensitive material.

## Determinism requirements

Because this project depends on reproducibility:

- Code that emits artifacts MUST produce stable output given the same inputs.
- Ordering MUST be explicit when it affects serialization:
  - Sort keys MUST be documented.
  - Never rely on filesystem iteration order.
- Randomness MUST be seeded and the seed MUST be recorded in the run bundle if applicable.
- Timestamps MUST be timezone-explicit; avoid implicit local-time behavior.

## Error handling

- Use exceptions for programmer errors and unrecoverable stage failures.
- For expected operational failures (missing file, missing mapping, missing required input),
  raise a domain-specific exception type and ensure the caller can classify it.
- Error messages MUST be actionable and MUST avoid leaking secrets or sensitive data.

TODO: define the repository error taxonomy once stage outcome classification is implemented.

## Logging and redaction

- Logging MUST NOT emit secrets. Use placeholder values and reference IDs.
- When logging structured data, avoid dumping entire events unless the redaction policy permits it.
- Any “debug dump” feature MUST be opt-in and MUST be compatible with the redaction policy.

TODO: link to the redaction policy ADR once its path is finalized.

## Testing and fixtures (pytest, pytest-regressions)

- New behavior MUST include tests.
- Regression tests MUST be deterministic and stable across OS and filesystem differences.
- Golden fixtures MUST be generated only under pinned toolchain versions.
- Test data MUST NOT include secrets; use synthetic or redacted values.

## Dependency management (uv)

- Dependencies MUST be added intentionally and recorded in the repo’s lockfile workflow.
- New dependencies SHOULD be pinned or constrained in a way compatible with the repo’s version-pin
  policy (top-level pins in CI, transitives via lockfile).
- Avoid large transitive dependency trees unless justified.

TODO: define the exact workflow for adding dependencies once `uv.lock` and `pyproject.toml` are in
place.

## File layout conventions (initial)

- Production code SHOULD live under a single import root (recommended: `src/` layout).
- Tooling and scripts SHOULD live under a separate directory (recommended: `tools/`).
- Tests SHOULD mirror package layout (recommended: `tests/`).

TODO: finalize the layout once implementation begins.

## Acceptance criteria

This policy is satisfied when:

- The repository exposes canonical commands for format, lint, type-check, and test.
- CI enforces the pinned toolchain and fails on mismatches.
- Golden fixtures are never blessed from unpinned local toolchains.
- Determinism constraints are explicitly enforced where artifacts are emitted.
