---
title: Markdown quick reference
description: Condensed reference for the repository markdown style guide.
status: stable
---

# Markdown quick reference

Condensed reference for the [full style guide](MARKDOWN_STYLE_GUIDE.md).

## Grep-friendly writing

- Use **canonical terms** consistently (don’t rename the same concept across docs).
- Put exact tokens in inline code: `metadata.event_id`, `manifest.versions.ocsf_version`,
  `stage="telemetry.windows_eventlog.raw_mode"`, `reason_code=winlog_raw_missing`.
- Prefer **full dotted paths** (not shorthand) the first time you mention a field/key.
- When listing keys/IDs/enums, use **one token per list item** (one per line) for clean `rg` hits.
- When referencing another document, include the **document ID + title** in text (not just a link):
  `ADR-0002 "Event identity and provenance"`.
- Avoid ambiguous pronouns ("it", "this", "that") when a repeated noun makes the sentence
  searchable.

## Frontmatter required

```yaml
---
title: "Document title"
description: "One-sentence summary"
status: draft | stable | deprecated
---
```

- Keep `title` stable after publish (changing it breaks search + links).

## Headings

```markdown
# Document title              ← One per document, matches frontmatter title
## Major section              ← Primary divisions
### Subsection                ← Secondary divisions (prefer stopping here)
#### Detail                   ← Use sparingly
```

- Sentence case: "Event identity model" not "Event Identity Model"
- No skipped levels (H2 → H4 without H3 is wrong)
- Make headings **keyword-bearing** (prefer nouns agents will search for; avoid generic "Notes" /
  "Misc" headings)

## Lists

```markdown
Unordered (use hyphens):
- Item one
- Item two

Ordered (use 1. for all):
1. First step
1. Second step

Definition style:
**Term**: Definition text here.
```

- Max two nesting levels
- Short items: no trailing punctuation
- Long items (full sentences): use punctuation
- For "search targets" (keys, IDs, enums), prefer **one-per-line** list items

## Code

````markdown
Inline: `field_name`, `path/to/file`, `command`

Blocks (always specify language):
```yaml
key: value
```

```python
def example():
    pass
```

```bash
uv sync --frozen
```
````

Common languages: `yaml`, `json`, `jsonl`, `python`, `bash`, `sql`, `text`, `toml`, `markdown`

- When documenting stable strings, show them exactly (prefer `key=value` forms for greppable tokens:
  `reason_code=...`, `contract_id=...`, `stage="..."`).

## Links

```markdown
Internal (relative paths):
See [OCSF field tiers](055_ocsf_field_tiers.md) for requirements.

External:
See the [OCSF schema docs](https://schema.ocsf.io/).
```

Never: `[here](link)` or `[click here](link)`

- Cross-doc references should include **type + id + title**:
  `ADR-0002 "Event identity and provenance"`.

## Tables

```markdown
| Field      | Type   | Required | Description          |
| ---------- | ------ | -------- | -------------------- |
| `run_id`   | string | Yes      | Execution identifier |
```

- Prefer tables for stable reference data (fields, enums, thresholds).
- Keep key names in backticks (so `rg` finds exact strings).

## Emphasis

```markdown
**Bold**: Key terms, summaries, warnings
*Italics*: New terms, titles, slight emphasis
`Code`: Field names, paths, commands, literals
```

- Prefer backticks for exact strings you expect people/agents to search for.

## Admonitions

```markdown
> **Note**: Informational callout.

> **Warning**: Important caution.

> **Important**: Critical information.
```

## Normative keywords

| Keyword    | Meaning              |
| ---------- | -------------------- |
| MUST       | Absolute requirement |
| MUST NOT   | Absolute prohibition |
| SHOULD     | Recommended          |
| SHOULD NOT | Discouraged          |
| MAY        | Optional             |

- Put the normative keyword near the start of the sentence so it’s easy to scan and grep.

## Section summary pattern

```markdown
## Complex section

**Summary**: One-sentence overview of what this section covers.

Detailed content follows...
```
