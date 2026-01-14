---
title: Repository index files policy (agent navigation)
description: Defines a deterministic, low-churn policy for repo index files used by local coding agents (Codex / GPT-5.2-Codex).
status: draft
---

# Repository index files policy (agent navigation)

This policy defines how the repository maintains index files used by local coding agents so they can
find authoritative entrypoints with minimal context and low churn.

## Purpose

This policy defines how the repository maintains **index files** (navigation aids) to help **local
coding agents** efficiently locate authoritative specs, contracts, mappings, and tooling entrypoints
without scanning large directory trees.

Primary goals:

- **Fast navigation**: agents find the correct file(s) quickly with minimal context load
- **Determinism**: index contents and ordering are stable and mechanically verifiable
- **Low churn**: index updates do not create noise in diffs or appear as functional drift
- **Security**: indexes do not become a vector for prompt injection, unsafe execution, or secret
  disclosure

## Scope

This document covers:

- Markdown index files (examples: `SPEC_INDEX.md`, `MAPPINGS_INDEX.md`, `ADR_INDEX.md`)
- Version-scoped and package-scoped sub-indexes (e.g., `.../ocsf/1.7.0/...`)
- Interaction between index files and **agent instruction files** (e.g., `AGENTS.md`)

This document does NOT cover:

- Runtime manifests, provenance snapshots, and machine-consumed mapping inputs (YAML/JSON)
- Human-facing docs like `README.md` (unless they link to index entrypoints)

## Definitions

- **Agent instruction file**: `AGENTS.md` (or `AGENTS.override.md`) files that Codex reads and
  merges into an instruction chain prior to work.
- **Index file**: a navigation-only document whose job is to point an agent to authoritative sources
  (entrypoints) with minimal reading.
- **Entrypoint file**: a file that defines the contract or behavior for a subsystem (spec, ADR,
  mapping profile, tool reference). Index files route to entrypoints.
- **Enumerated inventory**: a full listing of many leaf files (e.g., every mapping class YAML).
  Inventories are permitted only in narrow, scoped indexes.

## Design constraints from Codex (normative)

1. **Layered instructions**: Codex discovers and concatenates instruction files from global scope
   and from repository root down to the working directory. Files closer to the working directory
   override earlier guidance.
1. **Instruction size cap**: Codex stops adding discovered instruction files once the combined size
   reaches `project_doc_max_bytes` (32 KiB by default). Guidance should be split across nested
   directories rather than bloating a single root file.
1. **Context is finite and may be compacted**: Codex monitors remaining context and may compact
   (summarize/discard) content over long threads. Navigation docs must therefore be concise and
   high-signal.

## Policy

### Index hierarchy (must)

Indexes MUST be hierarchical to minimize load at the top level:

1. **Root index** (router)

   - Example: `MAPPINGS_INDEX.md`, `SPEC_INDEX.md`
   - MUST list *only*:
     - major subsystems / packs / domains
     - their authoritative **entrypoint paths**
     - and links to scoped sub-indexes
   - MUST NOT contain full leaf inventories

1. **Scoped index** (bounded router + local conventions)

   - Example: `mappings/normalizer/ocsf/1.7.0/OCSF_1.7.0_INDEX.md`
   - SHOULD summarize the local layout and list pack entrypoints for that scope
   - MAY link to per-pack indexes

1. **Per-pack/per-module index** (inventory allowed)

   - Example: `.../<pack_id>/PACK_INDEX.md`
   - MAY enumerate leaf files (e.g., `classes/*.yaml`) if necessary for that pack
   - SHOULD begin with entrypoints and rules-of-thumb before inventories

Rationale: hierarchical navigation aligns with known agent limitations around context budget and
multi-file search and reduces the chance an agent “flies blind.”

### Naming to reduce ambiguity (should)

Because agents and editors commonly “open by name,” scoped indexes SHOULD have **unique basenames**
to avoid collisions.

Recommended:

- Root: `MAPPINGS_INDEX.md`
- Version: `OCSF_1.7.0_INDEX.md` (or `OCSF_1_7_0_INDEX.md`)
- Pack: `PACK_INDEX.md`

If a repo chooses repeated basenames (e.g., multiple `MAPPINGS_INDEX.md`), then all references MUST
be repo-relative and path-qualified (never “see MAPPINGS_INDEX.md”). (This is a policy choice to
avoid agents opening the wrong file.)

### Content model (must)

Every index file MUST have:

- **Scope statement**: what directory/subsystem it covers
- **Entrypoints section**: the smallest set of authoritative files an agent should open next
- **Stable, deterministic ordering**:
  - Tables and lists MUST be sorted lexicographically by path unless a different explicit sort key
    is declared in the file.
- **Non-goals**: what the index intentionally does not list (to set agent expectations)

Indexes MUST NOT include:

- secrets, tokens, credentials, or “copy/paste” sensitive values
- instructions to fetch and follow arbitrary web content
- executable shell commands that are not safe-by-default for local execution

### Size budgets (should)

To keep agent load low:

- Root indexes SHOULD be ≤ 200 lines
- Scoped indexes SHOULD be ≤ 300 lines
- Inventories SHOULD be moved to per-pack indexes once they exceed ~150 lines

These are operational budgets, not hard caps; the intent is to keep indexes “high-signal first
screen.”

### Indexes are navigation-only (must)

Index files MUST be treated as **documentation-only** artifacts:

- They MUST NOT be used as runtime inputs or sources of truth for compilation, normalization,
  routing, or scoring.
- If the system produces a “mapping material hash” or provenance snapshot, it SHOULD exclude
  navigation-only markdown (including index files), so index edits do not appear as functional
  drift.

### Maintenance and verification (must)

Index accuracy MUST be mechanically verifiable.

Minimum required checks:

1. **Reachability check**

   - Every path referenced in an index MUST exist in the repo.

1. **Entrypoint completeness check**

   - For each declared “pack root,” required entrypoints MUST exist (example: `profile.yaml`,
     `routing.yaml`, `canonicalization.yaml` if your pack design uses those).

1. **Deterministic ordering check**

   - Tables/lists MUST be in the declared canonical order.

Recommended implementation approach:

- Provide a generator script (e.g., `tools/gen_indexes.py`) that emits indexes deterministically
- CI SHOULD fail if regenerating indexes produces a diff (index drift gate)

Rationale: empirical evidence suggests agent context files evolve like configuration code and drift
without disciplined maintenance.

## Integration with AGENTS.md (Codex / GPT-5.2-Codex)

### Required “Navigation” stanza (should)

Repository root `AGENTS.md` SHOULD include an early section that points agents to the root indexes,
because Codex performs best when it can follow explicit file-path guidance.

Example:

- “Start with `docs/SPEC_INDEX.md` for architecture/spec entrypoints”
- “Start with `mappings/MAPPINGS_INDEX.md` for mapping packs”

### Directory overrides (may)

Where a directory requires special rules, add a nested `AGENTS.md` or `AGENTS.override.md` near that
work to override broader guidance (Codex applies later files as overrides).

### Keep instruction chains under the size cap (must)

When `AGENTS.md` content grows, split it across nested directories rather than bloating root, since
Codex truncates/limits discovered instruction content by `project_doc_max_bytes` (32 KiB default).

### Long-running changes (should)

For complex multi-hour tasks, the repo MAY adopt an explicit “plan doc” pattern (e.g., `PLANS.md`)
and instruct agents in `AGENTS.md` when to use it.

## Security and safety requirements

1. **Prompt injection awareness (MUST)**

   - When enabling network access or web search in Codex, operators MUST treat fetched content as
     untrusted, because prompt injection can cause an agent to follow malicious instructions.

1. **Approval/sandbox posture (SHOULD)**

   - Prefer sandboxed, approval-gated modes for editing/running commands, especially in repos that
     are not version-controlled.

1. **Boundaries and “never touch” lists (SHOULD)**

   - Agent instruction files are most effective when they declare explicit boundaries and required
     commands/tests early.

## Acceptance criteria

This policy is satisfied when:

- Root indexes route to the correct authoritative entrypoints without requiring directory scans.
- Scoped indexes exist for high-churn / high-leaf-count areas (e.g., mappings per OCSF version).
- CI (or a local script) validates:
  - referenced paths exist
  - required entrypoints exist per pack
  - ordering is canonical
  - indexes can be regenerated deterministically with no diff

## Appendix A: minimal root index template

```markdown
# <Domain> navigator

Purpose: route the agent to entrypoints with minimal reading.

## Pack / subsystem map

| Name | Path | Entrypoints | Notes |
| ---- | ---- | ----------- | ----- |

## Sub-indexes

- <path-to-scoped-index>

## Non-goals

- Does not enumerate leaf files; see scoped/per-pack indexes
```

## Appendix B: minimal per-pack index template

```markdown
# Pack: <pack_id> (<scope>)

## Entrypoints (open these first)

- profile: <path>
- routing: <path>
- canonicalization: <path>

## Conventions

- <short bullets>

## Inventory (optional)

- classes:
  - <path>
  - <path>
```
