---
title: Repository index files policy (agent navigation)
description: Defines a deterministic, low-churn policy for repo index files used by local coding agents (Codex / GPT-5.2-Codex).
status: draft
last_updated: 2026-01-14
---

# Repository index files policy (agent navigation)

This policy defines how the repository maintains index files used by local coding agents so they can
find authoritative entrypoints with minimal context and low churn.

## Purpose

This policy defines how the repository maintains index files (navigation aids) to help local coding
agents efficiently locate authoritative specs, contracts, mappings, and tooling entrypoints without
scanning large directory trees.

Primary goals:

- Fast navigation: agents find the correct file(s) quickly with minimal context load
- Determinism: index contents and ordering are stable and mechanically verifiable
- Low churn: index updates do not create noise in diffs or appear as functional drift
- Security: indexes do not become a vector for prompt injection, unsafe execution, or secret
  disclosure

## Scope

This document covers:

- Markdown index files (examples: `SPEC_INDEX.md`, `MAPPINGS_INDEX.md`, `ADR_INDEX.md`)
- Version-scoped and package-scoped sub-indexes (e.g., `.../ocsf/1.7.0/...`)
- Interaction between index files and agent instruction files (e.g., `AGENTS.md`)

This document does NOT cover:

- Runtime manifests, provenance snapshots, and machine-consumed mapping inputs (YAML/JSON)
- Human-facing docs like `README.md` (unless they link to index entrypoints)
- Behavioral instructions in `AGENTS.md` files (covered by a separate policy)

## Definitions

- **Agent instruction file**: `AGENTS.md` (or `AGENTS.override.md`) files that Codex reads and
  merges into an instruction chain prior to work. These provide *behavioral* guidance.
- **Index file**: A navigation-only document whose job is to point an agent to authoritative sources
  (entrypoints) with minimal reading. These provide *structural* guidance.
- **Entrypoint file**: A file that defines the contract or behavior for a subsystem (spec, ADR,
  mapping profile, tool reference). Index files route to entrypoints.
- **Enumerated inventory**: A full listing of many leaf files (e.g., every mapping class YAML).
  Inventories are permitted only in narrow, scoped indexes.

## Distinction: Index files vs. AGENTS.md

Index files and `AGENTS.md` serve complementary but distinct purposes:

| Aspect          | Index files                                             | AGENTS.md                        |
| --------------- | ------------------------------------------------------- | -------------------------------- |
| Purpose         | Navigation and discovery                                | Behavioral instructions          |
| Content         | File paths, brief descriptions                          | Commands, conventions, rules     |
| Read by         | Agents during exploration                               | Agents before any work           |
| Example entries | "See `docs/050_normalization_ocsf.md` for OCSF mapping" | "Run `make test` before commits" |

`AGENTS.md` SHOULD reference index files in a "Navigation" section to bootstrap agent discovery.

## Design constraints from Codex (normative)

These constraints reflect the GPT-5.2-Codex release (December 2025) and Codex CLI behavior.

1. **Layered instructions**: Codex discovers and concatenates instruction files from global scope
   (`~/.codex/`) and from repository root down to the working directory. Files closer to the working
   directory override earlier guidance.

1. **Instruction size cap**: Codex stops adding discovered instruction files once the combined size
   reaches `project_doc_max_bytes` (32 KiB by default, configurable up to 65536 bytes). Files are
   silently truncated when they exceed this limit. Guidance should be split across nested
   directories rather than bloating a single root file.

1. **Context is finite and may be compacted**: GPT-5.2-Codex supports native context compaction for
   long-horizon work, automatically summarizing the session as it approaches context window limits.
   Navigation docs must be concise and high-signal to survive compaction.

1. **Override precedence**: At each directory level, Codex checks in order:

   - `AGENTS.override.md` (highest precedence)
   - `AGENTS.md`
   - Fallback filenames from `project_doc_fallback_filenames` Only the first non-empty file per
     directory is included.

1. **Message injection format**: AGENTS.md contents are injected as user-role messages near the top
   of the conversation history in root-to-leaf order, formatted as:

   ```
   # AGENTS.md instructions for <directory>
   <INSTRUCTIONS>
   ...file contents...
   </INSTRUCTIONS>
   ```

## Policy

### Index hierarchy (must)

Indexes MUST be hierarchical to minimize load at the top level:

1. **Root index (router)**

   - Example: `MAPPINGS_INDEX.md`, `SPEC_INDEX.md`
   - MUST list *only*:
     - major subsystems / packs / domains
     - their authoritative entrypoint paths
     - and links to scoped sub-indexes
   - MUST NOT contain full leaf inventories
   - SHOULD fit within ~4 KiB to leave headroom for other instruction files

1. **Scoped index (bounded router + local conventions)**

   - Example: `mappings/normalizer/ocsf/1.7.0/OCSF_1.7.0_INDEX.md`
   - SHOULD summarize the local layout and list pack entrypoints for that scope
   - MAY link to per-pack indexes

1. **Per-pack/per-module index (inventory allowed)**

   - Example: `.../<pack_id>/PACK_INDEX.md`
   - MAY enumerate leaf files (e.g., `classes/*.yaml`) if necessary for that pack
   - SHOULD begin with entrypoints and rules-of-thumb before inventories

Rationale: hierarchical navigation aligns with known agent limitations around context budget and
multi-file search and reduces the chance an agent "flies blind."

### Naming to reduce ambiguity (should)

Because agents and editors commonly "open by name," scoped indexes SHOULD have unique basenames to
avoid collisions.

Recommended:

- Root: `MAPPINGS_INDEX.md`
- Version: `OCSF_1.7.0_INDEX.md` (or `OCSF_1_7_0_INDEX.md`)
- Pack: `PACK_INDEX.md`

If a repo chooses repeated basenames (e.g., multiple `MAPPINGS_INDEX.md`), then all references MUST
be repo-relative and path-qualified (never "see MAPPINGS_INDEX.md"). (This is a policy choice to
avoid agents opening the wrong file.)

### Content model (must)

Every index file MUST have:

- **Scope statement**: what directory/subsystem it covers
- **Entrypoints section**: the smallest set of authoritative files an agent should open next
- **Stable, deterministic ordering**:
  - Tables and lists MUST be sorted lexicographically by path unless a different explicit sort key
    is declared in the file.

Indexes MUST NOT include:

- secrets, tokens, credentials, or "copy/paste" sensitive values
- instructions to fetch and follow arbitrary web content
- executable shell commands that are not safe-by-default for local execution
- themselves or AGENTS.md files in the listing

### Size budgets (should)

To keep agent load low and avoid silent truncation:

| Index type         | Recommended max         | Hard ceiling |
| ------------------ | ----------------------- | ------------ |
| Root index         | ≤ 150 lines (~4 KiB)    | 200 lines    |
| Scoped index       | ≤ 250 lines (~8 KiB)    | 300 lines    |
| Per-pack inventory | ≤ 100 lines per section | 150 lines    |

These are operational budgets; the intent is to keep indexes "high-signal first screen" and leave
room within the 32 KiB default `project_doc_max_bytes` for actual AGENTS.md instructions.

### Indexes are navigation-only (must)

Index files MUST be treated as documentation-only artifacts:

- They MUST NOT be used as runtime inputs or sources of truth for compilation, normalization,
  routing, or scoring.
- If the system produces a "mapping material hash" or provenance snapshot, it SHOULD exclude
  navigation-only markdown (including index files), so index edits do not appear as functional
  drift.

### Maintenance and verification (must)

Index accuracy MUST be mechanically verifiable.

Minimum required checks:

1. **Reachability check**

   - Every path referenced in an index MUST exist in the repo.

1. **Entrypoint completeness check**

   - For each declared "pack root," required entrypoints MUST exist (example: `profile.yaml`,
     `routing.yaml`, `canonicalization.yaml` if your pack design uses those).

1. **Deterministic ordering check**

   - Tables/lists MUST be in the declared canonical order.

1. **Size budget check**

   - Indexes SHOULD warn if they exceed recommended size budgets.

Recommended implementation approach:

- Provide a generator script (e.g., `tools/gen_indexes.py`) that emits indexes deterministically
- CI SHOULD fail if regenerating indexes produces a diff (index drift gate)

Rationale: empirical evidence suggests agent context files evolve like configuration code and drift
without disciplined maintenance.

## Integration with AGENTS.md (Codex / GPT-5.2-Codex)

### Required "Navigation" stanza (should)

Repository root `AGENTS.md` SHOULD include an early section that points agents to the root indexes,
because Codex performs best when it can follow explicit file-path guidance.

Example:

```markdown
## Navigation

Start by reading these index files to locate authoritative sources:

- `docs/SPEC_INDEX.md` — architecture and specification entrypoints
- `mappings/MAPPINGS_INDEX.md` — mapping pack entrypoints
- `docs/ADR_INDEX.md` — architecture decision records

Use the `@` file picker or explicit paths rather than scanning directories.
```

### Directory overrides (may)

Where a directory requires special rules, add a nested `AGENTS.md` or `AGENTS.override.md` near that
work to override broader guidance (Codex applies later files as overrides).

Use `AGENTS.override.md` for temporary constraints (e.g., release hardening windows, incident
response) that should take precedence over standard `AGENTS.md` files. Remove override files when
the temporary condition ends.

### Keep instruction chains under the size cap (must)

When `AGENTS.md` content grows, split it across nested directories rather than bloating root.

Configuration knobs in `~/.codex/config.toml`:

```toml
# Adjust these if needed (defaults shown)
project_doc_max_bytes = 32768        # 32 KiB default; max 65536 recommended
project_doc_fallback_filenames = []  # e.g., ["TEAM_GUIDE.md", ".agents.md"]
```

### Long-running changes (should)

For complex multi-hour tasks, the repo MAY adopt an explicit "plan doc" pattern (e.g., `PLANS.md`)
and instruct agents in `AGENTS.md` when to use it. GPT-5.2-Codex's native compaction makes this less
critical than before, but plan docs still help with auditability.

### Cross-agent compatibility (informative)

`AGENTS.md` is now an open standard under the Linux Foundation's Agentic AI Foundation, supported by
multiple coding agents including:

- OpenAI Codex (CLI, IDE Extension, Cloud)
- Cursor
- Google Jules
- Amp
- Factory

When authoring `AGENTS.md`, prefer standard markdown without agent-specific syntax to maximize
compatibility.

## Security and safety requirements

1. **Prompt injection awareness (MUST)**

   - When enabling network access or web search in Codex, operators MUST treat fetched content as
     untrusted, because prompt injection can cause an agent to follow malicious instructions.
   - Index files MUST NOT contain URLs to external content that agents might fetch and follow.
   - Be aware that `AGENTS.md` files in cloned repositories could contain malicious instructions.
     Codex injects these as high-privilege policy, not just context.

1. **Approval/sandbox posture (SHOULD)**

   - Prefer sandboxed, approval-gated modes for editing/running commands, especially in repos that
     are not version-controlled.
   - Use `approval_policy = "on-request"` and `sandbox_mode = "workspace-write"` as conservative
     defaults.
   - Disable network access (`network_access = false`) unless explicitly needed.

1. **Boundaries and "never touch" lists (SHOULD)**

   - Agent instruction files are most effective when they declare explicit boundaries and required
     commands/tests early.
   - Consider listing directories or patterns that agents should never modify.

1. **Review cloned repositories (SHOULD)**

   - Before enabling Codex on a newly cloned repository, review any `AGENTS.md` or
     `AGENTS.override.md` files for suspicious instructions (e.g., data exfiltration, unusual
     network requests, disabling safety checks).

## Acceptance criteria

This policy is satisfied when:

- Root indexes route to the correct authoritative entrypoints without requiring directory scans.
- Scoped indexes exist for high-churn / high-leaf-count areas (e.g., mappings per OCSF version).
- Combined index + AGENTS.md content fits comfortably within `project_doc_max_bytes`.
- CI (or a local script) validates:
  - referenced paths exist
  - required entrypoints exist per pack
  - ordering is canonical
  - indexes can be regenerated deterministically with no diff

## Appendix A: Minimal root index template

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

## Appendix B: Minimal per-pack index template

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

## Appendix C: Recommended AGENTS.md navigation stanza

```markdown
## Navigation

This repository uses hierarchical index files to guide agent navigation.

**Start here:**
- `docs/SPEC_INDEX.md` — architecture and specification entrypoints
- `mappings/MAPPINGS_INDEX.md` — mapping pack entrypoints
- `docs/ADR_INDEX.md` — architecture decision records

**Conventions:**
- Use `@` file picker or explicit repo-relative paths
- Check the appropriate index before scanning directories
- Scoped indexes exist in version/pack directories

**Do not modify:**
- Any `*_INDEX.md` files directly; regenerate via `tools/gen_indexes.py`
```

## Appendix D: Configuration reference

Key `~/.codex/config.toml` settings affecting instruction discovery:

```toml
# Maximum bytes read from each AGENTS.md file (default: 32768)
project_doc_max_bytes = 32768

# Additional filenames to treat as instruction files (default: [])
project_doc_fallback_filenames = ["TEAM_GUIDE.md", ".agents.md"]

# Approval policy: untrusted | on-failure | on-request | never
approval_policy = "on-request"

# Sandbox mode: read-only | workspace-write | danger-full-access
sandbox_mode = "workspace-write"

# Network access (default: false)
[sandbox_workspace_write]
network_access = false
```

## Changelog

| Version | Date       | Changes                                                                                                |
| ------- | ---------- | ------------------------------------------------------------------------------------------------------ |
| 2.0     | 2026-01-14 | Updated for GPT-5.2-Codex; added AGENTS.override.md; expanded security section; added config reference |
| 1.0     | —          | Initial policy                                                                                         |
