---
title: ChatGPT Projects best practices for software development on Pro
description: A practical, source-grounded guide to configuring and operating ChatGPT Projects for software development, with emphasis on memory mode selection, project instructions, and file strategy.
status: stable
created: 2026-01-19
---

# ChatGPT Projects best practices for software development on Pro

## Overview

This report summarizes what **ChatGPT Projects** can do (per official OpenAI documentation) and
translates those capabilities and constraints into **operational best practices** tailored to:

- **Plan**: ChatGPT **Pro**
- **Primary use**: **Software development**
- **Memory modes**: both **default memory** and **project-only memory**
- **File strategy**: best mix of **code files** and **documentation** for reliable, low-friction
  work

Projects are described by OpenAI as "smart workspaces" that keep **chats + reference files + custom
(project) instructions** together for long-running efforts. ([OpenAI Help Center][1])

______________________________________________________________________

## Source baseline and scope

**Primary sources used**:

- "Projects in ChatGPT" (OpenAI Help Center) ([OpenAI Help Center][1])
- "File Uploads FAQ" (OpenAI Help Center) ([OpenAI Help Center][2])
- "Chat and File Retention Policies in ChatGPT" (OpenAI Help Center) ([OpenAI Help Center][3])
- "Visual Retrieval with PDFs FAQ" (OpenAI Help Center) ([OpenAI Help Center][4])
- "Prompt engineering best practices for ChatGPT" (OpenAI Help Center) ([OpenAI Help Center][5])
- "Key Guidelines for Writing Instructions for Custom GPTs" (OpenAI Help Center)
  ([OpenAI Help Center][6])
- "What is the canvas feature…" (OpenAI Help Center) ([OpenAI Help Center][7])

**Scope boundaries**:

- This report focuses on **Projects as a workflow container** (instructions + files + chats).
- It does **not** attempt to document every model/tool available on Pro; those change and are not
  fully enumerated in the Projects article. Instead, it focuses on **project mechanics** that are
  explicitly documented.

______________________________________________________________________

## Capability snapshot for Pro

### What Projects provide, operationally

- **Project instructions**: instructions set at the project level apply only within that project,
  and **override global custom instructions**. ([OpenAI Help Center][1])
- **Project memory**: Projects "remember" the chats and files within the project, enabling ongoing
  work without re-stating context. ([OpenAI Help Center][1])
- **Context prioritization**: for Plus/Pro, ChatGPT can reference previous chats in the same
  project, and it prioritizes project chats/files when answering inside a project.
  ([OpenAI Help Center][1])
- **Move chats into a project**: moved chats inherit the project’s instructions and file context.
  ([OpenAI Help Center][1])
- **Branching chats**: Projects support branching a chat to explore alternative directions while
  preserving the original. ([OpenAI Help Center][1])

### Pro-specific limits and constraints

| Area                     | Pro reality                                                                                                                                                                                           | Implication                                                                                           |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| Files per project        | Up to **40 files per project** on Pro. ([OpenAI Help Center][1])                                                                                                                                      | Plan your file set as a curated "context pack," not a full repo mirror.                               |
| Batch upload             | Only **10 files** can be uploaded at the same time. ([OpenAI Help Center][1])                                                                                                                         | Stage uploads; don’t rely on one big import step.                                                     |
| File size and quotas     | 512MB/file hard limit; 2M token cap for text/doc files; user/org storage caps; upload rate caps (e.g., 80 files / 3 hours). ([OpenAI Help Center][2])                                                 | Use smaller, targeted files; avoid frequent churn.                                                    |
| Apps in projects         | **Apps are currently not supported** in projects. ([OpenAI Help Center][1])                                                                                                                           | Don’t assume "connected apps/connectors" will work inside projects (e.g., GitHub connector patterns). |
| Custom GPTs in projects  | Custom GPTs **cannot** be used in projects. ([OpenAI Help Center][1])                                                                                                                                 | Encode dev workflow behavior in project instructions + project files (not a custom GPT).              |
| Temporary chats          | Temporary chats **cannot** be added to projects. ([OpenAI Help Center][1])                                                                                                                            | If something may become long-running, don’t start it as a temporary chat.                             |
| Visual retrieval in PDFs | Visual PDF understanding is **Enterprise-only** and not supported for Pro; plus PDFs added as **Project Files** are text-only retrieval even where visual retrieval exists. ([OpenAI Help Center][4]) | Put diagrams into text (ASCII, Mermaid, extracted text) if you need reliable reuse on Pro.            |
| Rate limits              | Project chats follow the same subscription-based rate limits as regular chats. ([OpenAI Help Center][1])                                                                                              | Projects won’t "increase quota"; optimize for fewer, higher-signal turns.                             |

______________________________________________________________________

## Memory modes: default vs project-only

### What the modes mean (as documented)

**Project-only memory** (set at project creation):

- Saved memories are **not referenced**
- Chats can reference other conversations **within the same project**
- Chats **cannot** reference conversations **outside** the project (general ChatGPT or other
  projects) ([OpenAI Help Center][1])

**Default memory** (project creation option; existing projects remain on default):

- Saved memories are referenced, and chats can draw on other conversations within the project
- For non-enterprise subscriptions (which includes Pro), chats can also reference non-project
  conversations, and project chats can be referenced outside the project as well
  ([OpenAI Help Center][1])

**Important mechanics**:

- You must choose whether a project is project-only or default at creation time; existing projects
  stay on default, and project-only memory can only be set when starting a new project.
  ([OpenAI Help Center][1])
- No global toggle exists to force all projects to project-only; it’s per project.
  ([OpenAI Help Center][1])
- Sharing a project forces project-only memory and it cannot be reverted to default.
  ([OpenAI Help Center][1])

### When to use which mode for software development

#### Default memory projects

Use **default memory** when you want **continuity across your account**, such as:

- Consistent personal dev preferences you’ve saved as memories (language style, code-review tone,
  "always include tests," etc.)
- Cross-project patterns (e.g., you maintain several similar repos and want shared conventions to
  carry through)
- You value speed over strict isolation, and you can tolerate occasional "context bleed" risks

This is especially relevant because, for non-enterprise plans, default-memory project chats can
reference non-project conversations and vice versa. ([OpenAI Help Center][1])

**Default memory risks** (and mitigation):

- Risk: The assistant may pull in assumptions from other projects or saved memories.
- Mitigation: In project instructions, explicitly require "cite the file/chat source" for
  repo-specific claims, and require clarification where the source is absent.

#### Project-only memory projects

Use **project-only memory** when you want **strong isolation and reproducibility**, such as:

- Security-sensitive work (private code, proprietary architecture, pre-release behavior)
- Projects that share names/terms with other repos (avoid "wrong repo" errors)
- When you anticipate sharing later (sharing forces project-only memory anyway)
  ([OpenAI Help Center][1])
- When you want "clean-room" reasoning anchored strictly to the project’s files and chats

**Project-only tradeoffs**:

- Your saved memories won’t apply, so you must restate key preferences in project instructions.
  ([OpenAI Help Center][1])

### Practical decision matrix

| Criterion                          | Prefer default memory         | Prefer project-only memory                                             |
| ---------------------------------- | ----------------------------- | ---------------------------------------------------------------------- |
| Need cross-project personalization | Yes ([OpenAI Help Center][1]) | No ([OpenAI Help Center][1])                                           |
| Need strict repo isolation         | No                            | Yes ([OpenAI Help Center][1])                                          |
| Might share project later          | OK, but sharing flips it      | Yes (pre-align with eventual forced setting) ([OpenAI Help Center][1]) |
| Risk tolerance for "context bleed" | Higher                        | Lower                                                                  |
| Need your saved preferences        | Yes ([OpenAI Help Center][1]) | No ([OpenAI Help Center][1])                                           |

______________________________________________________________________

## Best practices for project instructions (software development)

### Ground rules from OpenAI documentation

- Project instructions apply only in that project and **override global custom instructions**.
  ([OpenAI Help Center][1])
- OpenAI’s prompt guidance emphasizes being **clear and specific** and using **iterative
  refinement**. ([OpenAI Help Center][5])
- OpenAI’s instruction-writing guidance (for GPTs, but directly applicable to projects) recommends:
  breaking complex instructions into smaller steps and using **trigger/instruction pairs** with
  delimiters to improve reliability. ([OpenAI Help Center][6])

### Design principles for effective project instructions

#### 1) Keep them stable, compact, and "constitutional"

Your project instructions should be a stable, low-churn "constitution" for how work is done in that
project. Put volatile, fast-changing details into project files.

- **Project instructions**: stable behavior and output contract
- **Project files**: source-of-truth facts that change over time (design, constraints, APIs,
  roadmap)
- **Chat prompts**: per-task specifics (the "ticket")

This approach is consistent with OpenAI’s emphasis on clarity and iterative prompting without
overloading a single instruction blob. ([OpenAI Help Center][5])

#### 2) Be explicit about evidence and provenance

For software dev, the most common failure mode is confident output that is correct "in general" but
wrong "for your repo."

Add an explicit requirement such as:

- “If a repo-specific claim is not grounded in the project files/chats, ask a clarifying question or
  label it as an assumption.”

This pairs well with the general guidance to be clear and specific. ([OpenAI Help Center][5])

#### 3) Use trigger/instruction pairs for repeatable workflows

For example, debugging, refactoring, and feature implementation have predictable phases. Use
trigger/instruction pairs to keep the assistant from skipping steps. ([OpenAI Help Center][6])

### Recommended project-instruction template for a dev project

Use this as your default "project instructions" text.

```text
ROLE
- Act as a senior software engineer pair-programmer for this repository.

DEFAULT OUTPUT CONTRACT
- Prefer: short sections + bullet points.
- For code changes: propose a plan, then provide a minimal patch (or a focused snippet) and list
  verification steps (tests, lint, run).
- Always state assumptions and ask clarifying questions if repo-specific facts are missing.

EVIDENCE RULES
- Treat project files and project chats as the source of truth for this repo.
- If a claim is not grounded in project files/chats, label it as an assumption or ask.

CHANGE DISCIPLINE
- Optimize for minimal diffs.
- Avoid refactors unless requested or necessary for correctness.

DEBUGGING PLAYBOOK (trigger/instruction pairs)
Trigger: User reports a bug or error log
Instruction: Ask for reproduction steps, environment, and the smallest relevant code + logs.

Trigger: Repro steps and code provided
Instruction: Identify likely root causes, propose 1–3 hypotheses, and suggest targeted checks.

Trigger: Hypothesis confirmed
Instruction: Provide a patch and list verification steps.
```

This structure is aligned with OpenAI’s guidance on decomposing instructions and using
trigger/instruction pairs. ([OpenAI Help Center][6])

______________________________________________________________________

## Project file strategy for software development

### What "project files" are best for

Projects exist to keep **files, chats, and instructions in one place** to stay on-topic.
([OpenAI Help Center][1]) On Pro, you have up to **40 files per project**, so you should treat the
file list as a curated "context pack," not a dumping ground. ([OpenAI Help Center][1])

### File handling constraints you should design around

- Project file limit: **40** (Pro). ([OpenAI Help Center][1])
- Only **10 files** can be uploaded at once. ([OpenAI Help Center][1])
- File size and usage constraints apply (512MB, 2M tokens for text/docs, etc.).
  ([OpenAI Help Center][2])
- For non-Enterprise plans, file understanding is effectively text-based for documents (and visual
  PDF retrieval is Enterprise-only, not Pro). ([OpenAI Help Center][2])

### Best mix: code files vs documentation

There is no universal ratio, but for Pro + software dev the most reliable approach is:

- **Documentation-heavy baseline** (stable, high-level truth)
- **Code-slice overlays** (targeted, working-set code for the current workstream)

A practical starting point for a Pro project:

- **~12–18 documentation/config files**
- **~10–20 code/test files**
- **Keep 5–10 slots free** for short-term "investigation artifacts" (logs, stack traces, exported
  canvases, temporary specs)

This balances:

- the assistant’s need for stable context (docs)
- the need for exactness (code and tests)
- the constraints of 40 files and practical churn limits ([OpenAI Help Center][1])

### Recommended "context pack" (docs/config first)

These files tend to pay off repeatedly:

1. `README.md` (or equivalent)
1. `ARCHITECTURE.md` (high-level system view)
1. `SETUP.md` or `DEVELOPMENT.md` (how to run, env vars, dev workflow)
1. `CONTRIBUTING.md` (how changes are made)
1. `STYLEGUIDE.md` (lint rules, formatting, naming)
1. `TESTING.md` (how to run tests, test philosophy)
1. `API.md` / `openapi.yaml` / contracts (public interfaces)
1. `DECISIONS.md` (or ADR-style decisions)
1. `ROADMAP.md` / `BACKLOG.md` (what matters now)
1. "Repo map" file (see below)

**Why this works**: It creates a stable, shared "language" for the assistant and reduces repeated
re-explanation turn-by-turn, which matters because projects inherit the same tools/rate limits as
normal chats. ([OpenAI Help Center][1])

### Recommended "repo map" file (high leverage)

Create and maintain a single, small, frequently updated file such as `REPO_MAP.md`:

- Directory tree (top 2–3 levels)
- "What lives where" descriptions
- Key entrypoints (main, CLI, server start)
- Where configs live
- Where tests live
- Where the "core domain logic" lives

Because apps/connectors are not supported in projects, a repo map becomes a substitute for “browse
the repo on demand inside the project.” ([OpenAI Help Center][1])

### Code files: how to choose what to upload

Because you cannot (and should not) upload an entire repo in most real-world cases, choose **code
slices** based on the task.

#### Always include (if applicable)

- Build/tooling: `pyproject.toml`, `package.json`, `tsconfig.json`, `Makefile`, CI config
- The entrypoint: `main`, server bootstrap, CLI runner
- Core domain modules (not helpers)
- Representative tests for the core modules

#### Upload per workstream

- The files directly touched by the feature/bug
- The tests that should validate the change
- Any config files that influence behavior in the relevant path

#### Avoid uploading

- Vendored dependencies
- Generated artifacts
- Large logs beyond what you’re actively debugging (prefer minimal repro snippets)

### Managing file churn and "stale truth"

A project’s answers will be influenced by its files and chats, and project files persist until you
delete the project. ([OpenAI Help Center][3]) Therefore, stale files are a real risk.

Recommended hygiene:

- Keep a `FILE_MANIFEST.md` listing:

  - file name
  - purpose
  - "source of truth" vs "snapshot"
  - last updated date
  - commit hash (if relevant)

- When you upload a new version of a file, delete the old version (or clearly mark it "deprecated")
  to reduce contradictory context.

- Use a simple naming convention:

  - `NN_` prefix for ordering (e.g., `00_README.md`, `10_REPO_MAP.md`, `20_ARCHITECTURE.md`)
  - Optional suffix: `@<commit>` or `@YYYY-MM-DD` for snapshots

______________________________________________________________________

## Workflow patterns that work well in Projects for dev

### Recommended chat taxonomy inside a project

Create a small number of stable chats and reuse them:

- "0 - Project hub": goals, definition of done, links to key chats/files
- "1 - Architecture and decisions": design discussions; branch when exploring alternatives
  ([OpenAI Help Center][1])
- "2 - Implementation log": task-by-task work; link to PRs/commits (manually)
- "3 - Debugging and incidents": logs, errors, root cause analysis
- "4 - Testing strategy": test plan and coverage gaps

Projects support branching chats; use it aggressively to explore alternatives without overwriting
the main thread. ([OpenAI Help Center][1])

### Using Canvas inside Projects (when available)

The Projects article explicitly lists Canvas as a tool usable in projects. ([OpenAI Help Center][1])
Canvas is described as an interface for writing/coding work with editing and revision support.
([OpenAI Help Center][7])

Best practice:

- Use Canvas for artifacts that you want to iterate on (design docs, long code blocks, refactors).
- Export Canvas outputs (e.g., markdown or code files) and upload them back into the project as
  stable references when they become "source of truth." ([OpenAI Help Center][7])

> **Important**: The Canvas article notes that Canvas is not available with **GPT-5 Pro**. If you
> don’t see Canvas, check whether the currently selected model is compatible.
> ([OpenAI Help Center][7])

______________________________________________________________________

## Data handling, retention, and privacy considerations

### Retention: what persists, and for how long

- Chats persist until you delete them; deleting schedules permanent deletion within 30 days (subject
  to exceptions). ([OpenAI Help Center][3])
- Files uploaded to a **project** are retained until the project is deleted; once deleted, removal
  occurs within ~30 days (subject to exceptions). ([OpenAI Help Center][3])

### Model training controls (relevant for Pro)

For Free/Plus/Pro users, OpenAI may use information accessed from projects to train models **if**
your "Improve the model for everyone" setting is on. ([OpenAI Help Center][1]) For shared projects,
OpenAI states training occurs only if **every** contributor/owner has that toggle enabled.
([OpenAI Help Center][1])

Operational best practice for dev:

- If you handle proprietary code, decide explicitly whether you want that toggle enabled before
  uploading sensitive material.
- Prefer project-only memory for sensitive repositories to reduce accidental context mixing, even
  aside from training considerations. ([OpenAI Help Center][1])

______________________________________________________________________

## Known limitations and "gotchas" that matter in dev workflows

1. **Apps are not supported in projects** Plan for a workflow that does not rely on connected
   apps/connectors inside the project. ([OpenAI Help Center][1])

1. **Custom GPTs cannot be used in projects** Put reusable behavior in project instructions and
   project files, not in a custom GPT. ([OpenAI Help Center][1])

1. **Temporary chats can’t be moved into projects** If you might want the work to live in a project,
   don’t start it as a temporary chat. ([OpenAI Help Center][1])

1. **Project-only memory is "set at creation"** You cannot convert an existing default-memory
   project to project-only; make a new project and move conversations if needed.
   ([OpenAI Help Center][1])

1. **Sharing changes memory behavior permanently** Sharing forces project-only memory and it cannot
   revert to default. ([OpenAI Help Center][1])

1. **PDF diagrams won’t be interpreted visually on Pro** Visual PDF retrieval is Enterprise-only; on
   Pro, plan to extract diagrams into text or separate image files and describe them.
   ([OpenAI Help Center][4])

1. **Only 10 files at a time** Plan staged uploads and keep a "manifest" so you don’t lose track.
   ([OpenAI Help Center][1])

______________________________________________________________________

## Practical checklists

### New dev project setup checklist (Pro)

- [ ] Choose memory mode (default vs project-only) based on isolation needs.
  ([OpenAI Help Center][1])
- [ ] Add project instructions (use the dev template; keep it stable). ([OpenAI Help Center][1])
- [ ] Upload the documentation baseline ("context pack"). ([OpenAI Help Center][1])
- [ ] Add `REPO_MAP.md` and `FILE_MANIFEST.md`.
- [ ] Create core chats ("hub", "architecture", "implementation log", "debugging").

### Per-task execution checklist

- [ ] State the goal and definition of done.
- [ ] Provide the smallest relevant code slice and relevant tests.
- [ ] Request: plan → patch/snippet → verification steps.
- [ ] If outputs rely on assumptions, require the assistant to label them clearly.
  ([OpenAI Help Center][5])

### Monthly hygiene checklist

- [ ] Delete stale or superseded snapshots to reduce contradictory context.
  ([OpenAI Help Center][3])
- [ ] Refresh `REPO_MAP.md` after major refactors.
- [ ] Review whether the project should be migrated to project-only memory (new project + move
  chats) if scope or sensitivity changes. ([OpenAI Help Center][1])

______________________________________________________________________

## Appendix A: official reference URLs

> **Note**: ChatGPT citations above are clickable inside ChatGPT. If you’re saving this as a local
> markdown file, the URLs below are the portable version.

```text
Projects in ChatGPT
https://help.openai.com/en/articles/10169521-projects-in-chatgpt
https://help.openai.com/en/articles/10169521-using-projects-in-chatgpt

File Uploads FAQ
https://help.openai.com/en/articles/8555545-file-uploads-faq

Chat and File Retention Policies in ChatGPT
https://help.openai.com/en/articles/8983778-chat-and-file-retention-policies-in-chatgpt

Visual Retrieval with PDFs FAQ
https://help.openai.com/en/articles/10416312-visual-retrieval-with-pdfs-faq

Prompt engineering best practices for ChatGPT
https://help.openai.com/en/articles/10032626-prompt-engineering-best-practices-for-chatgpt

Key Guidelines for Writing Instructions for Custom GPTs
https://help.openai.com/en/articles/9358033-key-guidelines-for-writing-instructions-for-custom-gpts

Canvas feature guide
https://help.openai.com/en/articles/9930697-what-is-the-canvas-feature-in-chatgpt-and-how-do-i-use-it
```

______________________________________________________________________

## Appendix B: local markdown and agent-authoring references used for formatting

These files were provided in the current workspace and can be used as supporting authoring
conventions for your local notes and playbooks.

- Markdown quick reference
- Markdown style guide
- AGENTS.md policy (agent instruction layering concepts can be adapted to “project instructions vs
  project files”)

[1]: https://help.openai.com/en/articles/10169521-projects-in-chatgpt "Projects in ChatGPT | OpenAI Help Center"
[2]: https://help.openai.com/en/articles/8555545-file-uploads-faq "File Uploads FAQ | OpenAI Help Center"
[3]: https://help.openai.com/en/articles/8983778-chat-and-file-retention-policies-in-chatgpt "Chat and File Retention Policies in ChatGPT | OpenAI Help Center"
[4]: https://help.openai.com/en/articles/10416312-visual-retrieval-with-pdfs-faq "Visual Retrieval with PDFs FAQ | OpenAI Help Center"
[5]: https://help.openai.com/en/articles/10032626-prompt-engineering-best-practices-for-chatgpt "Prompt engineering best practices for ChatGPT | OpenAI Help Center"
[6]: https://help.openai.com/en/articles/9358033-key-guidelines-for-writing-instructions-for-custom-gpts "Key Guidelines for Writing Instructions for Custom GPTs | OpenAI Help Center"
[7]: https://help.openai.com/en/articles/9930697-what-is-the-canvas-feature-in-chatgpt-and-how-do-i-use-it "What is the canvas feature in ChatGPT and how do I use it? | OpenAI Help Center"
