---
title: "Specification Title"
description: "One-sentence summary of what this specification defines"
status: draft
category: spec
tags: []
related: []
---

# Specification Title

Brief introductory paragraph (2-3 sentences) explaining what this document covers and why it
matters. State the key problem or need this specification addresses.

## Overview

High-level summary for readers who need to understand the specification quickly. Answer:

- What problem does this solve?
- What approach does it take?
- What are the key constraints or boundaries?

This section should be self-contained enough that someone can decide whether to read further.

## Scope

This document covers:

- First in-scope item
- Second in-scope item
- Third in-scope item

This document does NOT cover:

- First out-of-scope item (see [related doc](path/to/doc.md))
- Second out-of-scope item

## Requirements

### Normative requirements

The following requirements use RFC 2119 keywords (MUST, SHOULD, MAY).

1. Implementations MUST do the first required thing.
1. Implementations MUST do the second required thing.
1. Implementations SHOULD do the recommended thing unless there is a documented reason not to.
1. Implementations MAY do the optional thing.

### Constraints

**Constraint name**: Description of the constraint and why it exists.

**Another constraint**: Description of this constraint.

## [Primary Content Section]

**Summary**: One-sentence overview of what this section covers.

Main technical content goes here. Use subsections (H3) to organize complex topics.

### Subsection

Detailed content for this subsection.

**Example**: Demonstrating a key concept

```yaml
# example.yaml
key: value
nested:
  field: data
```

### Another subsection

More detailed content.

## [Secondary Content Section]

Additional technical content organized by topic.

## Key decisions

| Decision                        | Rationale                              | ADR             |
| ------------------------------- | -------------------------------------- | --------------- |
| Decision description            | Brief rationale                        | [ADR-NNNN](link) |
| Another decision                | Brief rationale                        | N/A             |

## References

- [Related internal doc](path/to/doc.md) - Brief description of relationship
- [External resource](https://example.com) - Brief description

## Changelog

| Date       | Change                                    |
| ---------- | ----------------------------------------- |
| YYYY-MM-DD | Initial draft                             |