# Agent instructions (docs/adr/)

## Scope and authority

- This file applies to **`docs/adr/*` only**.
- ADRs record architectural decisions: context, decision, and consequences.
- Avoid rewriting history; if a decision changes materially, prefer a new ADR or a clearly labeled
  amendment.

## Navigation entrypoint (required)

- Start with `docs/adr/ADR_INDEX.md` (one-page map + “Common tasks” router).

## ADR intent

- ADRs record: context, decision, and consequences.
- Avoid rewriting history; if a decision changes materially, prefer a new ADR or a clearly labeled
  amendment.

## Change protocol (do not rewrite history)

- Prefer **new ADR** when the decision changes materially or introduces incompatible consequences.
- Use an **amendment** only for:
  - clarifications that do not change the decision,
  - added operational detail that is consistent with the original decision,
  - editorial fixes (typos, formatting) that do not change meaning.
- If amending, make the amendment explicitly discoverable:
  - Add an "Amendments" section (or append an item under an existing one),
  - Include date and a short reason,
  - Preserve the original decision text and clearly separate new text.

## Index maintenance (required)

- Maintain `docs/adr/ADR_INDEX.md` as a **one-page map** that covers **all** ADRs in this directory.
- When you add a new ADR:
  - Add it to `docs/adr/ADR_INDEX.md`,
  - Keep the index pointer-style (no duplicated ADR content).
