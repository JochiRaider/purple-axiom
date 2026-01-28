---
title: Markdown style guide
description: Defines markdown conventions for readability, consistency, and deterministic diffs.
status: stable
---

# Markdown style guide

Version 0.1. Applies to all markdown files in the Purple Axiom repository.

This guide defines conventions for markdown authoring that optimize for human readability, agent/LLM
comprehension, and diff stability. All contributors (human and automated) MUST follow these
guidelines.

## Guiding principles

1. **Consistency over preference**: Follow the guide even when alternatives seem reasonable.
1. **Searchability**: Use explicit, descriptive text that agents can locate and reference.
1. **Diff stability**: Prefer patterns that minimize spurious changes across edits.
1. **Context efficiency**: Structure content so agents can extract meaning without reading entire
   documents.

## Tooling constraints

This repository uses `mdformat` with the following enforced settings:

| Setting       | Value            | Effect                                  |
| ------------- | ---------------- | --------------------------------------- |
| `wrap`        | 100              | Lines reflow to 100 characters          |
| `number`      | false            | Ordered lists keep original numbers     |
| `end_of_line` | lf               | Unix line endings                       |
| `validate`    | true             | Malformed output rejected               |
| `extensions`  | gfm, frontmatter | GFM tables/tasklists + YAML frontmatter |

Do not fight the formatter. Write content that formats cleanly under these rules.

______________________________________________________________________

## Document structure

### File naming

Spec documents use numeric prefixes for ordering:

```text
NNN_descriptive_name.md
```

- `NNN`: Three-digit sequence number (000-999)
- Use underscores, not hyphens, in filenames
- Use lowercase throughout
- Name should be scannable and searchable

Examples:

- `050_normalization_ocsf.md` ✓
- `OCSF-Normalization.md` ✗
- `050-normalization-ocsf.md` ✗

ADRs use the pattern:

```text
ADR-NNNN-short-description.md
```

- `NNNN`: Four-digit sequence number
- Use hyphens in the description portion
- Keep descriptions under 50 characters

### Required frontmatter

Every markdown document MUST include YAML frontmatter with at minimum:

```yaml
---
title: "Human-readable document title"
description: "One-sentence summary of document purpose and scope"
status: draft | stable | deprecated
---
```

#### Full frontmatter schema

```yaml
---
# Required fields
title: "OCSF normalization specification"
description: "Defines mapping rules from raw telemetry to OCSF 1.7.0 envelopes"
status: draft | stable | deprecated

# Recommended fields
category: spec | adr | guide | reference
tags: [ocsf, normalization, telemetry]
related:
  - 055_ocsf_field_tiers.md
  - 040_telemetry_pipeline.md

# Optional fields
author: contributor-name
created: 2026-01-10
last_updated: 2026-01-12
spec_version: "0.1"
supersedes: ADR-0001-old-decision.md
superseded_by: null
---
```

#### Status definitions

| Status       | Meaning                                             |
| ------------ | --------------------------------------------------- |
| `draft`      | Under active development; may change without notice |
| `stable`     | Approved for implementation; changes require review |
| `deprecated` | Superseded; retained for historical reference only  |

### Document skeleton

Use this structure for spec documents:

```markdown
---
title: "Document title"
description: "One-sentence description"
status: stable
---

# Document title

Brief introductory paragraph (2-3 sentences) explaining what this document covers and why it
matters. No heading for this section.

## Overview

High-level summary suitable for someone skimming the document. Should answer: what problem does
this solve, what approach does it take, and what are the key constraints?

## [Primary content sections]

Main technical content organized by logical topic.

## Key decisions

Summary of important decisions made in this document, with rationale. Link to ADRs where
applicable.

## References

- [Related Document](path/to/doc.md)
- [External Resource](https://example.com)

## Changelog

| Date       | Change                          |
| ---------- | ------------------------------- |
| 2026-01-12 | Initial draft                   |
```

## Headings

### Hierarchy rules

1. **One H1 per document**: The H1 is the document title and MUST match the frontmatter `title`.
1. **No skipped levels**: Do not jump from H2 to H4.
1. **Maximum depth**: Prefer H2 and H3; use H4 sparingly; avoid H5 and H6.

```markdown
# Document title                    ← H1: exactly one per document

## Major section                    ← H2: primary divisions

### Subsection                      ← H3: secondary divisions

#### Detail (use sparingly)         ← H4: tertiary divisions

##### Avoid                         ← H5: restructure instead
```

### Heading text

- Use sentence case: "Event identity model" not "Event Identity Model"
- Be specific and searchable: "OCSF field mapping rules" not "Rules"
- Avoid articles at the start: "Configuration options" not "The configuration options"
- Do not end with punctuation
- Do not include inline code in headings when avoidable

```markdown
## Event identity computation       ✓ Sentence case, specific
## Event Identity Computation       ✗ Title case
## The Event Identity               ✗ Leading article
## How events get their IDs         ✗ Vague
## `metadata.event_id` generation   ✗ Inline code in heading (avoid)
```

### Heading anchors

GitHub and most renderers auto-generate anchors from heading text. To ensure stable cross-document
links:

- Keep heading text stable once documents are published
- If you must rename a heading, update all internal references

## Paragraphs and prose

### Line wrapping

Let mdformat handle wrapping at 100 characters. Write naturally without manual line breaks within
paragraphs.

```markdown
<!-- Good: let the formatter wrap -->
This is a paragraph that explains a concept. The formatter will wrap it appropriately at the
configured line length, keeping the source readable and diffs clean.

<!-- Bad: manual mid-sentence breaks -->
This is a paragraph that explains
a concept. Manual breaks create
unnecessary diff noise.
```

### Paragraph length

- Aim for 3-6 sentences per paragraph
- Break up walls of text with headings or lists
- Lead with the most important information

### Section summaries

For complex sections, include a bold summary line immediately after the heading:

```markdown
## Provenance model

**Summary**: Every normalized event carries provenance fields tracing its origin through the
pipeline, enabling deterministic identity computation and audit trails.

The provenance model consists of three components...
```

This pattern helps agents extract key information without parsing entire sections.

## Lists

### When to use lists

Use lists for:

- Enumerated requirements or steps
- Feature comparisons
- Option sets with brief descriptions

Do NOT use lists for:

- Content that flows better as prose
- Single-item "lists"
- Deeply nested structures (restructure as sections instead)

### Unordered lists

Use hyphens (`-`) for unordered lists, not asterisks or plus signs:

```markdown
- First item
- Second item
- Third item
```

### Ordered lists

Use `1.` for all items. The formatter preserves source numbers, and renderers auto-increment:

```markdown
1. First step
1. Second step
1. Third step
```

This keeps diffs clean when reordering items.

### List item length

- Short items (single line): No trailing punctuation unless they're complete sentences
- Long items (multiple sentences): Use full punctuation

```markdown
<!-- Short items: no trailing punctuation -->
Required fields:
- `run_id`
- `event_id`
- `timestamp`

<!-- Long items: full sentences with punctuation -->
Configuration steps:
- Clone the repository and navigate to the project root. Ensure you have the required Python
  version installed.
- Run `uv sync` to install dependencies. This creates a virtual environment automatically.
- Copy `range.example.yaml` to `range.yaml` and edit as needed.
```

### Nested lists

Limit nesting to two levels. If you need more, restructure as subsections:

```markdown
<!-- Acceptable: two levels -->
- Category A
  - Item A1
  - Item A2
- Category B
  - Item B1

<!-- Avoid: three+ levels -->
- Category A
  - Subcategory A1
    - Item A1a      ← restructure instead
```

### Definition-style lists

For term definitions, use bold terms followed by a colon:

```markdown
**Ground truth**: The append-only timeline of executed actions, serving as the authoritative
record of what occurred during a scenario run.

**Run bundle**: The complete artifact set produced by a single execution, rooted at
`runs/<run_id>/`.
```

## Code

### Inline code

Use backticks for:

- File paths: `runs/<run_id>/manifest.json`
- Field names: `metadata.event_id`
- Command names: `uv sync`
- Literal values: `true`, `null`, `1.7.0`
- Environment variables: `$OCSF_SCHEMA_VERSION`

Do NOT use backticks for:

- Emphasis (use bold or italics)
- Product names: Purple Axiom, not `Purple Axiom`
- General technical terms: OCSF, Sigma, JSON (unless referring to literal strings)

### Code blocks

Always specify the language identifier:

````markdown
```yaml
schema_version: 1.7.0
````

```python
def compute_event_id(event: dict) -> str:
    ...
```

```bash
uv sync --frozen
```

````

Common language identifiers used in this project:
- `yaml` - Configuration files, OCSF examples
- `json` - Data structures, API responses
- `jsonl` - Line-delimited JSON examples
- `python` - Python code
- `bash` - Shell commands
- `sql` - DuckDB queries
- `text` - Plain text, directory trees
- `toml` - Configuration files
- `markdown` - Markdown examples

### Command examples

For shell commands, use `bash` and include the prompt only when showing interactive sessions:

```markdown
<!-- Single command: no prompt -->
```bash
uv sync --frozen
````

<!-- Interactive session: include prompts -->

```bash
$ uv run pytest tests/
===== 42 passed in 1.23s =====
$ echo $?
0
```

````

### File content examples

When showing file contents, include a comment indicating the filename:

```yaml
# range.yaml
schema_version: 1.7.0
lab:
  provider: local
````

### Directory trees

Use `text` language identifier for directory structures:

```text
runs/<run_id>/
├── manifest.json
├── ground_truth.jsonl
├── normalized/
│   ├── events.parquet
│   └── coverage.json
└── report/
    └── index.html
```

## Tables

### When to use tables

Tables work well for:

- Structured reference data (field definitions, version pins)
- Comparisons with consistent attributes
- Status/feature matrices

Avoid tables for:

- Prose content
- Deeply nested or variable structures
- Content with very long cell values

### Table formatting

- Include header row with column names
- Use alignment appropriate to content (default left, numbers right)
- Keep cell content concise; link to details if needed

```markdown
| Field          | Type   | Required | Description                    |
| -------------- | ------ | -------- | ------------------------------ |
| `run_id`       | string | Yes      | Immutable execution identifier |
| `event_id`     | string | Yes      | Deterministic event identity   |
| `timestamp`    | string | Yes      | ISO 8601 timestamp             |
```

### Wide tables

If a table exceeds 100 characters, consider:

1. Abbreviating column headers
1. Moving detailed descriptions to footnotes or a following list
1. Splitting into multiple tables
1. Using a definition list instead

## Links and references

### Internal links

Use relative paths for links within the repository:

```markdown
See [OCSF field tiers](055_ocsf_field_tiers.md) for mapping requirements.
```

For links within the same directory, use the filename only:

```markdown
See [field tiers](055_ocsf_field_tiers.md).
```

For links to other directories, use relative paths from the current file:

```markdown
See [ADR-0002](../adrs/ADR-0002-event-identity-and-provenance.md).
```

### Link text

Use descriptive link text that makes sense out of context:

```markdown
<!-- Good: descriptive -->
See [OCSF field tier requirements](055_ocsf_field_tiers.md) for mapping priorities.

<!-- Bad: vague -->
See [here](055_ocsf_field_tiers.md) for more info.

<!-- Bad: URL as text -->
See [055_ocsf_field_tiers.md](055_ocsf_field_tiers.md).
```

### External links

For external resources, include enough context that the link destination is clear:

```markdown
See the [OCSF schema documentation](https://schema.ocsf.io/) for field definitions.
```

### Reference-style links

For documents with many links to the same targets, use reference-style links at the bottom:

```markdown
The [normalization spec][norm-spec] defines how events map to [OCSF 1.7.0][ocsf].

[norm-spec]: 050_normalization_ocsf.md
[ocsf]: https://schema.ocsf.io/1.7.0/
```

## Emphasis

### Bold

Use bold (`**text**`) for:

- Key terms on first use
- Summary lines at the start of sections
- Critical warnings or requirements

```markdown
**Ground truth** is the append-only timeline of executed actions.

**Summary**: Every event carries provenance fields for traceability.

**Warning**: This operation is irreversible.
```

### Italics

Use italics (`*text*`) for:

- Introducing new terms (alternative to bold)
- Titles of external works
- Slight emphasis within a sentence

```markdown
The *run bundle* contains all artifacts from a single execution.

See *Designing Data-Intensive Applications* for background on event sourcing.
```

### Avoid

- ALL CAPS for emphasis (use bold instead)
- Underlining (not standard markdown)
- Combining bold and italics (`***text***`)
- Excessive emphasis (if everything is bold, nothing is)

## Special sections

### Admonitions

Use blockquotes with bold labels for callouts:

```markdown
> **Note**: This applies only to OCSF 1.7.0 and later.

> **Warning**: Changing this field invalidates existing event identities.

> **Important**: This is a breaking change from v0.0.x.
```

Standard labels: Note, Warning, Important, Tip, Example

### Examples

Label examples explicitly and use code blocks:

````markdown
**Example**: Computing event identity from raw input

```python
event_id = compute_identity(raw_event, mapping_profile)
````

````

### Changelogs

Use tables for inline changelogs:

```markdown
## Changelog

| Date       | Change                                    |
| ---------- | ----------------------------------------- |
| 2026-01-12 | Added provenance field requirements       |
| 2026-01-10 | Initial draft                             |
````

## Agent-specific patterns

These patterns specifically improve comprehension by LLMs and automated agents.

### Explicit scope statements

Start documents with clear scope boundaries:

```markdown
## Scope

This document covers:
- Event identity computation rules
- Provenance field requirements
- Determinism guarantees

This document does NOT cover:
- Raw event collection (see [telemetry pipeline](040_telemetry_pipeline.md))
- Detection rule evaluation (see [Sigma detection](060_detection_sigma.md))
```

### Normative language

Use RFC 2119 keywords consistently for requirements:

| Keyword    | Meaning                                   |
| ---------- | ----------------------------------------- |
| MUST       | Absolute requirement                      |
| MUST NOT   | Absolute prohibition                      |
| SHOULD     | Recommended unless good reason to deviate |
| SHOULD NOT | Discouraged unless good reason to use     |
| MAY        | Optional                                  |

```markdown
The `run_id` field MUST be present in all normalized events.
Implementations SHOULD use deterministic ordering for JSON serialization.
The `description` field MAY be omitted if no meaningful value exists.
```

### Explicit cross-references

When referring to other documents, include the document type and title:

```markdown
See ADR-0002 "Event Identity and Provenance" for the rationale behind deterministic identity
computation.

The configuration reference (docs/spec/120_config_reference.md) defines all valid keys.
```

### Glossary references

For key terms used across documents, reference the canonical definition:

```markdown
The **ground truth** (see [Key Concepts](#key-concepts)) timeline records...
```

Or link to a central glossary:

```markdown
Each **run bundle** ([glossary](glossary.md#run-bundle)) contains...
```

## Greppability conventions (agent + tooling)

This repo is routinely navigated using line-oriented search tools (`rg`, `grep`). Authoring MUST
assume searches are **single-line** by default (no multiline matching).

### Search tokens (required)

A **search token** is a string an agent/operator is expected to locate mechanically, including:

- artifact paths (example: `runs/<run_id>/manifest.json`)
- contract IDs (example: `mapping_profile_snapshot`)
- schema paths (example: `docs/contracts/manifest.schema.json`)
- config keys (example: `telemetry.otel.enabled`)
- stage IDs (example: `telemetry.windows_eventlog.raw_mode`)
- reason codes (example: `winlog_rendering_detected`)
- enum values (example: `fail_closed`)

Rules:

1. Search tokens MUST appear in backticks as a single uninterrupted token (no spaces).
1. When a section introduces multiple search tokens, they MUST be presented as one-per-line list
   items or table rows (do not bury tokens only in wrapped prose).
1. Do not rely on multi-word phrase searches across wrapped lines. If a term must be searchable,
   give it a heading and/or a labeled line.

### Standard label lines (required)

To support consistent regex search, use these labels at the start of a line (column 1):

- `Contract id:`
- `Schema:`
- `Artifact path:`
- `Config key:`
- `Stage id:`
- `Reason code:`
- `Enum:`

Each labeled line MUST use the form:

`Label: \`value\`\`

Example:

Contract id: `manifest` Schema: `docs/contracts/manifest.schema.json` Artifact path:
`runs/<run_id>/manifest.json` Config key: `telemetry.otel.enabled` Stage id:
`telemetry.windows_eventlog.raw_mode` Reason code: `winlog_raw_missing`

### Quick reference block (recommended for specs)

Specs with multiple artifacts/config keys SHOULD include a `## Quick reference` section near the top
containing the key search tokens as one-per-line bullets:

- Artifacts (paths)
- Contracts (contract id + schema path)
- Config keys
- Reason codes / enums (when relevant)

## Common mistakes

### Inconsistent code formatting

```markdown
<!-- Bad: mixing styles -->
The `run_id` field and the event_id field must match.

<!-- Good: consistent -->
The `run_id` field and the `event_id` field must match.
```

### Orphaned links

```markdown
<!-- Bad: link destination unclear -->
See [this document](050_normalization_ocsf.md) for details.

<!-- Good: context provided -->
See the [OCSF normalization specification](050_normalization_ocsf.md) for field mapping rules.
```

### Over-nesting

```markdown
<!-- Bad: too deep -->
- Level 1
  - Level 2
    - Level 3
      - Level 4

<!-- Good: restructure -->
## Level 1

### Level 2

- Level 3 item A
- Level 3 item B
```

### Ambiguous pronouns

```markdown
<!-- Bad: unclear referent -->
The normalizer processes events and sends them to storage. It validates them first.

<!-- Good: explicit -->
The normalizer processes events and sends them to storage. The normalizer validates each event
before forwarding.
```

______________________________________________________________________

## Checklist for new documents

Before committing a new markdown document, verify:

- [ ] Frontmatter includes required fields (`title`, `description`, `status`)
- [ ] Single H1 matching frontmatter title
- [ ] No skipped heading levels
- [ ] All code blocks have language identifiers
- [ ] Internal links use relative paths
- [ ] Link text is descriptive
- [ ] Lists are appropriately formatted (hyphens for unordered, `1.` for ordered)
- [ ] Tables have header rows
- [ ] Key terms are defined on first use
- [ ] Scope section clarifies what is/isn't covered
- [ ] Document passes `mdformat --check`

______________________________________________________________________

## References

- [CommonMark Specification](https://spec.commonmark.org/)
- [GitHub Flavored Markdown Spec](https://github.github.com/gfm/)
- [mdformat Documentation](https://mdformat.readthedocs.io/)
- [RFC 2119: Key Words](https://www.rfc-editor.org/rfc/rfc2119)
