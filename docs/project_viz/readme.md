# Project Viz

Project Viz is the “system model → diagrams” workspace for the Purple Team CI Orchestrator documentation. It standardizes a single, validated system graph (`system_model.yaml`) and generates consistent Mermaid flowcharts from named views.

This README lives in: `docs/project_viz/`

## What lives here

Primary inputs:

* `architecture/system_model.yaml`
  Design-time system graph used to generate Mermaid flowcharts (topology, run sequence, IO boundary views). This file MUST conform to the `system_model_v1` schema (see below).

* `source/Mermaid.py`
  Mermaid diagram generator (parsing, linting, rendering). Unit tests map 1:1 to a lint checklist described in this README.

Related specs that define key invariants referenced by this project:

* ADR-0001: project naming/versioning (`id_slug_v1`, `version_token_v1`, SemVer rules)
* ADR-0004: deployment architecture + normative run sequence + minimum v0.1 I/O boundaries

## System model format

`architecture/system_model.yaml` is YAML, but it is restricted to a JSON-compatible subset and is validated after parse.

Schema token and identity:

* Schema version token: `system_model_v1`
* Schema `$id`: `urn:purple-axiom:schema:system_model_v1`

### JSON-compatible YAML subset (SM001)

The YAML parser MUST reject non-JSON YAML features. At minimum, these are not allowed:

* anchors / aliases (`&anchor`, `*alias`)
* YAML tags (`!!tag`)
* duplicate map keys

This is enforced as a hard error (generation fails).

### Root shape (required keys)

After YAML is parsed to JSON, the root object MUST contain:

* `v` (MUST equal `system_model_v1`)
* `system`
* `nodes`
* `edges`
* `views`

Optional:

* `groups` (for diagram grouping / subgraphs)

Additional root keys are not allowed (fail closed).

### `system`

`system` identifies the modeled system:

* `system.system_id`
  MUST be `id_slug_v1` as defined in ADR-0001 (lowercase letters/digits/hyphen; no leading/trailing hyphen; no consecutive hyphens).

* `system.system_version`
  MUST be `semver_v1` (SemVer 2.0.0, no leading `v`).

* `system.title`
  Human title for diagrams.

* `system.description` (optional)
  Human description.

### `groups` (optional)

`groups` define optional subgraph boundaries used for diagram grouping.

Key fields:

* `groups[].id` (lower_snake_case identifier; Mermaid-safe)
* `groups[].label` (Mermaid-safe label)
* `groups[].parent` (optional; must reference an existing group; must be acyclic)
* `groups[].order` (optional; integer sort key)
* `groups[].description` (optional)

### `nodes`

`nodes` are the diagram-addressable entities. Every node has:

* `nodes[].id`
  Lower snake case identifier (Mermaid-safe ID). Must be unique.

* `nodes[].kind`
  One of:

  * `core_stage`
  * `stage`
  * `orchestrator`
  * `run_bundle`
  * `endpoint`
  * `collector_agent`
  * `collector_gateway`
  * `datastore`
  * `external_service`
  * `note`

* `nodes[].label`
  Mermaid-safe label (constraints below).

Optional node fields:

* `group` (must reference an existing `groups[].id`)
* `order` (integer; used for stable sorting / deterministic output)
* `tags` (unique list of lower_snake_case tags)
* `description` (free text)

Core stages (v0.1):

* If a node has `kind: core_stage`, its `id` MUST be one of the stable v0.1 core stage identifiers:

  * `lab_provider`
  * `runner`
  * `telemetry`
  * `normalization`
  * `validation`
  * `detection`
  * `scoring`
  * `reporting`
  * `signing` (optional-by-config, but enumerated for reference)

### `edges`

`edges` are directed relationships between nodes. Every edge has:

* `edges[].id` (unique lower_snake_case identifier)
* `edges[].from` (must reference an existing `nodes[].id`)
* `edges[].to` (must reference an existing `nodes[].id`)
* `edges[].channel` (communication channel)

Allowed channels:

* `filesystem`
* `otlp_grpc`
* `otlp_http`
* `https`
* `ssh`
* `winrm`
* `in_process`
* `other`

Optional edge fields:

* `label` (Mermaid-safe label)
* `optional` (boolean; default false)
* `artifacts` (unique list of run-relative artifact paths or globs)

Artifact path / glob constraints:

* Must be run-relative POSIX-style (no leading `/`)
* No backslashes
* No `..` path segments
* Allows `*` and `<placeholder>` tokens

### Mermaid-safe labels

Labels used in nodes, groups, and edges are restricted to avoid Mermaid parse hazards.

At minimum:

* no newlines
* no tabs
* no `[` or `]`
* no `|`
* no double quotes (`"`)

If a label violates Mermaid-safe constraints, generation MUST fail closed (or sanitize deterministically, if the generator explicitly supports a safe sanitizer).

### `views`

`views` are named Mermaid render targets. The generator renders exactly one Mermaid flowchart per view.

Each view has:

* `views[].id` (unique lower_snake_case identifier)
* `views[].title` (human title)
* `views[].kind` (MUST be `flowchart`)
* `views[].direction` (one of `TB`, `TD`, `BT`, `LR`, `RL`)
* `views[].nodes` (unique list of node IDs included in the view)
* `views[].edges` (unique list of edge IDs included in the view)

Optional view fields:

* `profile` (conformance profile; see below)
* `include_groups` (optional list of group IDs to include)
* `notes` (free text notes attached to the view)

## View profiles (v0.1 conformance)

A view may set `views[].profile` to enable additional conformance lints. Profiles are:

* `none` (default)
* `v0_1_run_sequence`
* `v0_1_io_boundaries`
* `v0_1_deployment_topology`

Notes on expectations:

* `v0_1_run_sequence` reflects ADR-0004’s normative stage ordering and responsibilities.
* `v0_1_io_boundaries` reflects ADR-0004’s “Minimum v0.1 IO boundaries” table.
* Stage coordination is filesystem-based (the run-bundle is the coordination plane). OTLP is part of the telemetry plane and is not required for stage-to-stage coordination.

## Mermaid generator contract and lints

The generator is tested as a lint-and-render pipeline with the following assumed contract:

* `parse_system_model_yaml(path) -> model_json`
* `lint_system_model(model_json) -> findings[]`
* `render_mermaid(model_json, view_id) -> mermaid_text`

Findings contract:

* Each finding has at least:

  * `code`
  * `message`
  * `json_pointer`

Severity:

* All checklist items below are treated as errors (any finding fails generation).

## Lint checklist (maps 1:1 to unit tests)

Model / parse / schema lints:

* SM001 (`test_SM001_reject_non_json_yaml_features`)
  Reject anchors/aliases, tags, and duplicate keys (JSON-subset only).

* SM002 (`test_SM002_schema_validation_errors_reported`)
  Parsed JSON MUST validate against `system_model_v1`; schema failures must surface as lint findings.

* SM003 (`test_SM003_version_token_must_match`)
  `v` MUST equal `system_model_v1` (fail closed for unknown versions).

ID uniqueness and reference integrity lints:

* SM010 (`test_SM010_group_ids_unique`)
  `groups[].id` MUST be unique.

* SM011 (`test_SM011_group_parent_must_exist`)
  If `groups[].parent` is set, it MUST reference an existing `groups[].id`.

* SM012 (`test_SM012_group_parent_must_be_acyclic`)
  Group parent chains MUST be acyclic.

* SM020 (`test_SM020_node_ids_unique`)
  `nodes[].id` MUST be unique.

* SM021 (`test_SM021_node_group_must_exist`)
  If `nodes[].group` is set, it MUST reference an existing `groups[].id`.

* SM030 (`test_SM030_edge_ids_unique`)
  `edges[].id` MUST be unique.

* SM031 (`test_SM031_edge_endpoints_must_exist`)
  `edges[].from` and `edges[].to` MUST reference existing `nodes[].id`.

* SM032 (`test_SM032_no_self_edges`)
  `edges[].from` MUST NOT equal `edges[].to`.

* SM033 (`test_SM033_no_duplicate_semantic_edges`)
  No two edges may share the same semantic key `(from, to, channel, label)`.

View integrity lints:

* SM040 (`test_SM040_view_node_refs_exist`)
  Every `views[].nodes[]` entry MUST reference an existing `nodes[].id`.

* SM041 (`test_SM041_view_edge_refs_exist`)
  Every `views[].edges[]` entry MUST reference an existing `edges[].id`.

* SM042 (`test_SM042_view_edges_must_connect_included_nodes`)
  For each edge referenced by a view, both endpoints MUST be included in `views[].nodes[]`.

v0.1 profile lints (only apply when `views[].profile` is set):

* SM100 (`test_SM100_profile_run_sequence_requires_core_stages`)
  For `profile=v0_1_run_sequence`, the view MUST include all stable core stage IDs. `signing` MAY be omitted.

* SM101 (`test_SM101_profile_run_sequence_stage_order`)
  For `profile=v0_1_run_sequence`, the view MUST include the canonical stage order from ADR-0004:
  `lab_provider → runner → telemetry → normalization → validation → detection → scoring → reporting`
  If `signing` is present, it MUST be last.

* SM102 (`test_SM102_profile_run_sequence_no_otlp_between_stages`)
  For `profile=v0_1_run_sequence`, edges connecting two core stages MUST NOT use OTLP channels.

* SM110 (`test_SM110_profile_io_boundaries_minimum_artifacts_present`)
  For `profile=v0_1_io_boundaries`, the view MUST include edges whose `artifacts[]` cover the minimum v0.1 IO boundaries defined in ADR-0004. Examples (non-exhaustive):

  * runner emits `ground_truth.jsonl`
  * telemetry emits `raw_parquet/**`
  * normalization emits `normalized/**`

Mermaid render determinism and formatting lints (generator behavior):

* MG001 (`test_MG001_render_is_order_independent`)
  Rendering MUST be deterministic regardless of input ordering.

* MG002 (`test_MG002_render_uses_stable_sort_keys`)
  Generator MUST sort emitted Mermaid statements by stable keys. Recommended sort keys:

  * groups by `(order, id)`
  * nodes by `(order, id)`
  * edges by `(from, to, channel, label, id)`

* MG003 (`test_MG003_render_rejects_or_sanitizes_unsafe_labels`)
  If labels violate Mermaid-safe constraints, generator MUST fail closed (or sanitize deterministically, if supported).

* MG010 (`test_MG010_golden_mermaid_for_v0_1_run_sequence`)
  For a canonical `system_model.v0_1.yaml` fixture, rendered Mermaid MUST match a checked-in golden `.mmd` file byte-for-byte.

## Editing checklist (practical)

When you edit `architecture/system_model.yaml`:

* Ensure it stays within the JSON-compatible YAML subset (SM001).
* Ensure `v: system_model_v1` (SM003).
* Ensure all IDs are unique and references resolve (SM010–SM042).
* Prefer stable IDs; renames should be avoided unless explicitly required.
* Keep labels Mermaid-safe (schema + MG003).
* For profile views:

  * `v0_1_run_sequence`: include all core stages and preserve canonical ordering; avoid OTLP between core stages.
  * `v0_1_io_boundaries`: ensure required artifact boundary edges are present (per ADR-0004).

## Troubleshooting generation failures

If diagram generation fails, start with the lint findings:

* Use `code` to identify the category (schema vs reference vs profile vs render).
* Use `json_pointer` to jump directly to the failing location in `system_model.yaml` (after parse-to-JSON).
* Fix the first/earliest schema or reference error before debugging profile-related errors (later lints often cascade from missing nodes/edges).

## Security and safety hygiene

* Do not embed secrets, credentials, tokens, or internal URLs with embedded credentials in labels, descriptions, or artifact paths.
* Keep labels conservative: Mermaid parsing failures should result in clean lint errors, not “almost renders” output.
* If you need to capture uncertainties or TODOs inside the model, use `kind: note` nodes and keep them out of conformance-profile views unless they are explicitly intended to appear in a diagram.
