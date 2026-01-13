---
title: Markdown quick reference
description: Condensed reference for the repository markdown style guide.
status: stable
---

# Markdown quick reference

Condensed reference for the [full style guide](MARKDOWN_STYLE_GUIDE.md).

## Frontmatter required

```yaml
---
title: "Document title"
description: "One-sentence summary"
status: draft | stable | deprecated
---
```

## Headings

```markdown
# Document title              ← One per document, matches frontmatter title
## Major section              ← Primary divisions
### Subsection                ← Secondary divisions (prefer stopping here)
#### Detail                   ← Use sparingly
```

- Sentence case: "Event identity model" not "Event Identity Model"
- No skipped levels (H2 → H4 without H3 is wrong)

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

## Links

```markdown
Internal (relative paths):
See [OCSF field tiers](055_ocsf_field_tiers.md) for requirements.

External:
See the [OCSF schema docs](https://schema.ocsf.io/).
```

Never: `[here](link)` or `[click here](link)`

## Tables

```markdown
| Field      | Type   | Required | Description          |
| ---------- | ------ | -------- | -------------------- |
| `run_id`   | string | Yes      | Execution identifier |
```

## Emphasis

```markdown
**Bold**: Key terms, summaries, warnings
*Italics*: New terms, titles, slight emphasis
`Code`: Field names, paths, commands, literals
```

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

## Section summary pattern

```markdown
## Complex section

**Summary**: One-sentence overview of what this section covers.

Detailed content follows...
```

## Pre-commit checklist

- [ ] Frontmatter: `title`, `description`, `status`
- [ ] Single H1 = frontmatter title
- [ ] No skipped heading levels
- [ ] All code blocks have language
- [ ] Links use relative paths + descriptive text
- [ ] Passes `mdformat --check`
