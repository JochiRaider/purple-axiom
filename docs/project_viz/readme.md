# Project Viz

Project Viz is the “system model → diagrams” workspace for the Purple Team CI Orchestrator
documentation. It standardizes a single, evidence-backed architecture model (`system_model.yaml`)
and generates a small set of consistent Mermaid diagrams.

This README lives in: `docs/project_viz/`

## What lives here

Primary inputs:

- `architecture/system_model.yaml`\
  YAML system model used to generate Mermaid diagrams. The model is **spec-derived** and should be
  **evidence-backed** (see “Evidence pointers”).

- `source/Mermaid.py`\
  Mermaid diagram generator for the YAML model. It validates the model for diagram safety and emits
  Markdown files containing Mermaid code blocks.

Generated outputs (do not hand-edit):

- `docs/diagrams/generated/`
  - `stage_flow.md`
  - `trust_boundaries.md`
  - `run_sequence.md`
  - `run_status_state.md`

## Quickstart

From the repo root:

```bash
python3 docs/project_viz/source/Mermaid.py
```

Common options:

```bash
# Render using a specific workflow id (default: exercise_run)
python3 docs/project_viz/source/Mermaid.py --workflow exercise_run

# Treat warnings as failures (recommended for CI)
python3 docs/project_viz/source/Mermaid.py --strict

# Override model path / output directory
python3 docs/project_viz/source/Mermaid.py \
  --model docs/project_viz/architecture/system_model.yaml \
  --out-dir docs/diagrams/generated
```

## System model format

`architecture/system_model.yaml` is a YAML mapping. The model can contain additional fields for
future tooling, but `Mermaid.py` currently consumes (and lightly validates) the following sections:

### Top-level keys commonly used

- `version` (integer; informational)
- `system` (informational metadata)
- `trust_zones` (diagram clustering + validation)
- `actors`, `containers`, `datastores`, `externals`, `buses` (entities referenced by diagrams)
- `relationships` (used by trust boundary view)
- `workflows` (used by stage flow + run sequence)
- `states` (currently unused by the generator; reserved for future explicit state machines)

### Trust zones

`trust_zones` is a list. Each trust zone should include:

- `id` (**required**; Mermaid-safe identifier)
- `name` (human label; used in diagrams)
- `description` (optional)
- `evidence` (recommended)

Trust zones are used to **cluster nodes** in the trust boundary diagram and to validate that
entities reference declared zones.

### Entities

Entities are defined across these sections:

- `actors`
- `containers`
- `datastores`
- `externals`
- `buses`

For diagram generation, each entity needs:

- `id` (**required**; unique across all entity sections)
- `name` (recommended; used as the displayed label)
- `trust_zone` (recommended; used for trust boundary clustering)

Additional fields are allowed (e.g., `kind`, `type`, `tech`, `responsibilities`, `tags`,
`description`, `evidence`, etc.).

#### Stages vs non-stages

The **Stage flow** diagram is derived from workflow steps, but it only includes `containers` where:

- `kind: stage`

If a workflow step targets a container that is not `kind: stage`, it will not appear in
`stage_flow.md`.

### Relationships

`relationships` is a list of directed edges, used by the trust boundary diagram.

The generator expects each relationship item to be a mapping and typically uses:

- `from` (entity id)
- `to` (entity id)
- `label` (optional; shown on the edge)

Other relationship fields (e.g., protocol, auth, evidence) are allowed and ignored by the generator
for now.

### Workflows

`workflows` is a list of named workflows. The generator uses one workflow (selected by `--workflow`,
defaulting to `exercise_run`) to build:

- `stage_flow.md`
- `run_sequence.md`

A workflow should contain:

- `id` (string; referenced by `--workflow`)
- `name` (optional)
- `steps` (list of workflow steps)

Each workflow step should contain:

- `n` (integer ordering key; used for sorting)
- `from` (entity id)
- `to` (entity id)
- `message` (human message used in the sequence diagram)

**Optional stage heuristic:** if a step’s `message` contains the literal substring `(optional)`, the
generator marks that stage as optional in `stage_flow.md` and renders the incoming edge as
“optional”.

## ID rules

To keep Mermaid output stable and parse-safe, trust zone IDs and entity IDs must be
**Mermaid-safe**:

- Must match: `^[A-Za-z_][A-Za-z0-9_]*$`
  - letters, digits, underscore
  - cannot start with a digit

Examples:

- ✅ `ci_environment`, `orchestrator_cli`, `run_bundle_store`
- ❌ `ci-environment` (hyphen), `123_stage` (starts with digit)

IDs must also be unique across all entity sections.

## Evidence pointers

Project policy: **Evidence or it doesn’t exist.**

Model elements should be backed by evidence pointers in the shape:

- `file` (spec filename)
- `section_heading` (nearest heading)
- `excerpt` (short quote; keep it brief)

The generator does not currently enforce “evidence required”, but the model is intended to be
auditable and maintainable, so treat evidence as mandatory for new additions.

## YAML pitfalls and quoting

Some YAML parsers reject _plain scalars_ that contain `:` (colon-space). In the current model this
most commonly appears in evidence `excerpt:` lines.

Guidance:

- If an `excerpt:` contains `:` , quote it:
  - `excerpt: "Atomic Red Team tests: pinned exact version."`
- Prefer short, single-line excerpts.

`Mermaid.py` includes a narrow fallback sanitizer that auto-quotes **unquoted** `excerpt:` values
containing `:` , and prints a warning so the YAML can be fixed properly later.

## Diagram set produced by Mermaid.py

### 1) Stage flow (`stage_flow.md`)

A Mermaid **flowchart** that represents the ordered stage pipeline for the selected workflow:

- Derived from `workflows[].steps` sorted by `n`
- Extracts `to:` endpoints that are `containers` with `kind: stage`
- Preserves first-seen order
- Marks a stage optional if any step message includes `(optional)`

This view is meant to stay small and legible: it shows the stage pipeline, not every internal
dependency.

### 2) Trust boundaries (`trust_boundaries.md`)

A Mermaid **flowchart** clustered by `trust_zones`:

- Nodes are grouped into subgraphs by each entity’s `trust_zone`
- Edge selection is intentionally bounded:
  - includes all **cross-trust-zone** relationships
  - plus any `orchestrator_cli -> *` relationship with `label: invoke stage`
- Nodes without a `trust_zone` appear under an `unmodeled` subgraph

### 3) Canonical run sequence (`run_sequence.md`)

A Mermaid **sequenceDiagram** generated directly from workflow steps:

- Participants are collected in first-seen order across `from`/`to`
- Each step becomes a message `from ->> to: n. message`

### 4) Run status state (`run_status_state.md`)

A Mermaid **stateDiagram-v2** that currently renders a stable, spec-level summary:

- Running → Failed (fail_closed)
- Running → Partial (warn_and_skip)
- Running → Success (otherwise)

The generator currently does not build this from `states` (the model currently has `states: []`), so
treat this as a placeholder until an explicit state machine is modeled.

## Validation behavior (errors vs warnings)

The generator performs lightweight structural validation before rendering:

Errors (generation fails):

- `trust_zones` / entity sections are not lists
- missing string `id` for trust zones or entities
- duplicate entity IDs across all entity sections
- IDs that are not Mermaid-safe
- workflow `steps` is not a list

Warnings (generation continues by default):

- entities reference an undeclared `trust_zone`
- relationships reference unknown entity IDs
- workflow steps reference unknown entity IDs
- non-mapping items in lists (skipped)

In CI, prefer `--strict` so warnings fail the build.

## Editing checklist

When you edit `architecture/system_model.yaml`:

- Keep IDs Mermaid-safe and stable (rename only when strictly necessary).
- Ensure entity IDs are globally unique across `actors/containers/datastores/externals/buses`.
- Ensure `trust_zone` references point to declared `trust_zones[].id` values.
- Keep workflow step `n` values as integers and unique within the workflow.
- If a stage is optional-by-config and you want that reflected in `stage_flow.md`, include
  `(optional)` in the step’s `message`.
- Quote `excerpt:` strings containing `:` .
- Re-run the generator locally and resolve warnings (or run with `--strict`).

## Troubleshooting generation failures

Common failure modes:

- **YAML parse errors**\
  Usually caused by unquoted `excerpt:` values containing `:` . Quote the excerpt (preferred) or
  confirm the sanitizer warning appears and then fix the YAML.
- **“not Mermaid-safe” id errors**\
  Rename the offending `id` to match `^[A-Za-z_][A-Za-z0-9_]*$`.
- **Warnings about unknown ids**\
  Fix typos in `relationships[].from/to` and `workflows[].steps[].from/to`, or add the missing
  entity definition in the appropriate section.
- **Trust boundaries diagram looks empty**\
  Check that relationships include cross-zone edges, or that `orchestrator_cli -> *` edges use
  `label: invoke stage`.

## Security and safety hygiene

- Do not put secrets (tokens/keys/passwords) in labels, descriptions, or evidence excerpts.
- Prefer placeholders like `<run_id>` / `<workspace_root>` over environment-specific internal paths.
- Keep text single-line where possible to avoid Mermaid parsing quirks.
