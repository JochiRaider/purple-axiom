---
title: Operator Interface
description: Local-first web operator interface and control-plane API for plan authoring, run management, status monitoring, and safe artifact/report viewing (v0.2+).
status: draft
category: spec
tags: [operator-interface, ui, control-plane, web, security, v0.2]
related:
  - 020_architecture.md
  - 025_data_contracts.md
  - 031_plan_execution_model.md
  - 040_telemetry_pipeline.md
  - 080_reporting.md
  - 090_security_safety.md
  - 110_operability.md
  - 120_config_reference.md
  - ../adr/ADR-0003-redaction-policy.md
  - ../adr/ADR-0004-deployment-architecture-and-inter-component-communication.md
  - ../adr/ADR-0005-stage-outcomes-and-failure-classification.md
  - ../adr/ADR-0006-plan-execution-model.md
  - ../adr/ADR-0007-state-machines.md
---

# Operator Interface

## Version scope

This specification is **v0.2+ (normative)** unless explicitly marked as reserved or future work.

This spec defines an Operator Interface that is **web-based**, **local-first**, and
**contract-aligned** with the orchestrator’s existing verb and run-bundle semantics. The UI is
intentionally thin: it surfaces and drives the orchestrator’s canonical entry points rather than
re-implementing pipeline semantics. The run bundle remains the single source of truth for pipeline
state and outputs.

## Goals

The Operator Interface MUST provide:

1. A **web UI** suitable for:

   - interactive plan drafting (authoring)
   - plan compilation preview (graph view)
   - run creation and verb execution (build/simulate/replay/export/destroy)
   - run listing and monitoring (status, logs, progress)
   - report viewing and export (redaction-safe by default)
   - configuration editing for **UI-scoped settings** (not full platform configuration)

1. A **control-plane HTTP API** used by the UI, designed so that:

   - the API can later support non-browser clients (CLI, automation)
   - future RBAC/MFA/enterprise auth can be added without breaking API shape

1. A **secure-by-default LAN access posture** for a single-container appliance deployment.

## Non-goals

This spec explicitly does NOT define:

- pixel-level UX/UI layouts, menus, visual design, or component libraries
- multi-tenant behavior, organization constructs, or enterprise IAM integration (reserved)
- full RBAC/ABAC authorization models (reserved)
- internet-facing hosting guidance (the default posture assumes “not internet-facing”)
- multi-container orchestration (reserved for future version; v0.2 is single-container)

## Terms

- **Appliance**: A single Docker container packaging the orchestrator, Operator Interface web
  server, reverse proxy, and OTLP gateway.
- **Operator Interface (OI)**: The operator-facing web UI + the control-plane API service backing
  it.
- **Reverse proxy (RP)**: The in-container TLS terminator and request gatekeeper for the UI.
- **Verb**: A stable orchestrator entry point (for example: `build`, `simulate`, `replay`, `export`,
  `destroy`).
- **Run bundle**: `runs/<run_id>/` filesystem root containing all run artifacts, as defined
  elsewhere.
- **Workspace root**: A host directory (usually volume-mounted) containing `runs/`, UI state, UI
  audit logs, and UI workspace artifacts.
- **Quarantine path**: A run-bundle subpath excluded from default disclosure (notably
  `unredacted/`).
- **Control artifacts**: Durable, run-local files under `runs/<run_id>/control/` used for
  operator-driven run control (cancel/resume/retry) without introducing a database for pipeline
  correctness.

## Deployment model (v0.2 normative)

### Single-container appliance

In v0.2, the Operator Interface MUST be deployable as a **single container** that includes:

- Reverse proxy (RP) for UI ingress
- Operator Interface service (OI service: UI + API)
- Orchestrator (verbs) executable
- OTLP gateway (collector gateway tier)

Future multi-container decomposition is reserved, but this spec’s interfaces MUST NOT assume
co-location beyond localhost links between RP and OI service.

### Ports (v0.2 normative defaults)

The appliance MUST support the following defaults:

| Function        | Default port | Notes         |
| --------------- | -----------: | ------------- |
| UI ingress (RP) |          443 | HTTPS only    |
| OTLP gRPC       |         4317 | mTLS required |
| OTLP HTTP       |         4318 | mTLS required |

### Network profile: LAN UI via bundled reverse proxy

**requirements (normative):**

1. The reverse proxy MUST be the only process binding the external UI port (default 443).

1. The Operator Interface service MUST listen only on a loopback interface (localhost) or a Unix
   domain socket.

1. The reverse proxy MUST enforce:

   - allowlist filtering (default deny)
   - TLS termination
   - request rate limiting for authentication endpoints (minimum viable brute-force protection)

1. The reverse proxy MUST forward authenticated traffic to the OI service over a local-only channel.

### Allowlist semantics (normative)

The allowlist is evaluated at the reverse proxy boundary.

- Allowlist entries MUST support:

  - CIDR ranges (IPv4 and IPv6)
  - explicit IP addresses

- Default policy MUST be **deny**.

- `localhost` MUST be **implicitly allowed** regardless of configured allowlist.

**Deterministic matching rules (normative):**

1. Determine `client_ip` as the TCP peer IP observed by the reverse proxy.
1. If `client_ip ∈ {127.0.0.1, ::1}`, ALLOW.
1. Else if `client_ip` is contained in any allowlist entry, ALLOW.
1. Else DENY with HTTP 403 (and do not disclose application behavior beyond a generic response).

**Forwarded header trust (normative):**

- The OI service MUST NOT trust `X-Forwarded-For` or similar headers from arbitrary clients.
- If the RP injects `X-Forwarded-For`, the OI service MAY use it only when the immediate peer is the
  RP on a loopback/unix-socket channel.

## TLS and certificates (v0.2 normative)

### UI TLS (reverse proxy termination)

**Default certificate story (normative):**

- On first appliance start, the appliance MUST generate a persistent **local CA** for UI TLS.
- On each appliance start (“server session”), the appliance MUST generate a new leaf certificate
  signed by that CA (leaf rotation per session).
- The CA private key MUST be stored only in the workspace root’s protected state directory and MUST
  NOT be written into any run bundle.

**Operator-provided TLS (reserved):**

- A future version MAY support operator-provided cert/key pairs. The config keys MUST be reserved
  now (see Configuration).

**Minimum TLS requirements (normative):**

- TLS 1.2+ MUST be supported.
- TLS 1.3 SHOULD be enabled when available.
- Insecure ciphers and TLS compression MUST be disabled.

### OTLP gateway exposure and mTLS (normative)

**Exposure:**

- The OTLP gateway MUST listen on ports 4317 and 4318 (configurable) and MUST be reachable by
  telemetry endpoints intended to export OTLP.

**mTLS:**

- OTLP ingress MUST require mTLS.
- The gateway MUST validate client certificates against an operator-controlled CA trust store.
- The default posture MUST be: “no valid client cert, no ingestion.”

**Certificate provisioning (v0.2):**

- v0.2 MAY use a locally generated OTLP CA (similar to UI CA) persisted under workspace state.
- v0.2 MUST document and implement a CLI workflow to issue client certificates for lab endpoints
  (exact lab distribution is environment-specific and is out of scope, but issuance MUST be
  deterministic and auditable).

## Control plane boundary and “thin UI” (v0.2 normative)

### Authoritative semantics

The orchestrator semantics remain authoritative for:

- stage execution order
- publish gates and contract validation
- run status derivation
- verb behavior (`build`, `simulate`, `replay`, `export`, `destroy`)

The Operator Interface MUST NOT re-implement these semantics in an alternate execution path.

### Execution model (v0.2 normative)

v0.2 MUST implement **Model 1**:

- The OI service spawns orchestrator verb processes (subprocess execution).
- The OI service streams logs/status by reading the run bundle artifacts and log files produced by
  the orchestrator process.

A future version MAY implement a long-running daemon/queue model, but only if it preserves run-lock,
publish-gate, and outcome-recording semantics and does not introduce a database as the authoritative
pipeline state store.

## Functional surfaces (v0.2 normative)

The web UI MUST expose, at minimum, the following capabilities:

1. **Landing / system status**

   - appliance version and build info
   - UI auth status (logged in user)
   - OTLP gateway status (up/down + mTLS enforced)

1. **Plan building**

   - create/edit plan drafts (YAML authoring surface)
   - compute and display deterministic plan hash
   - compile preview (expanded plan graph) without mutating the draft

1. **Run management**

   - start verbs: build/simulate/replay/export/destroy
   - list runs (stable ordering)
   - run detail view (manifest, stage outcomes, progress)
   - cancellation (graceful and force)
   - resume and retry (drift-gated decisions)

1. **Status monitoring**

   - live tail of run logs (while a verb process is active)
   - stage outcome view derived from `logs/health.json`
   - node-level status derived from ground truth + plan graph for v0.2 plans

1. **Report building and viewing**

   - view `report/report.json`
   - view `report/report.html` (served safely; see Artifact Serving)
   - trigger exports (zip/archive) with explicit inclusion toggles

1. **UI-scoped configuration**

   - network allowlist management
   - session timeouts
   - quarantine access policy (default OFF)
   - export inclusion policies (default safe)

## Authentication (v0.2 normative)

### Local-only accounts

v0.2 MUST support local user accounts with local authentication.

- Roles/RBAC/ABAC are explicitly reserved for future versions.
- In v0.2, any authenticated user is a full operator.

### Bootstrap mechanism (v0.2 normative)

The system MUST provide a CLI bootstrap workflow (exact binary name is implementation-defined; the
verbs are normative):

- `user create <username>`: creates a local account
- `user reset-password <username>`: resets password (see recovery)
- `user disable <username>`: disables account (optional but recommended)

The UI MUST NOT provide “create the first user” workflows in v0.2. Bootstrap is CLI-only.

### Password hashing (v0.2 normative)

- Passwords MUST be stored only as salted password hashes.

- Argon2id MUST be used via a maintained library where feasible.

  - Parameters (v0.2 baseline): memory 19 MiB, iterations 2, parallelism 1.

- bcrypt is an acceptable fallback if Argon2id dependencies are impractical for the appliance.

### Sessions (v0.2 normative)

- Sessions MUST be server-side revocable (so logout and admin resets take effect immediately).

- Default idle timeout MUST be 20 minutes.

- Sessions MUST terminate on explicit logout.

- Session cookies MUST be configured:

  - `HttpOnly`: required
  - `SameSite=Strict`: required by default (MAY relax to Lax only with explicit config)
  - `Secure`: required when TLS is enabled

- Cookie name: `pa_session` (v0.2 default).

### Account recovery (v0.2 normative)

Account recovery is CLI-only:

- `user reset-password <username>` MUST either:

  - set a new password directly (operator-entered), OR
  - generate a time-limited reset token

If token-based:

- token expiry MUST be 1 hour
- no email/SMS delivery is provided in v0.2

## Audit logging (v0.2 normative)

### Scope

Audit logging MUST be enabled by default and MUST be global (appliance-wide), not per-run only.

Audit logs MUST:

- be append-only JSONL
- exclude secrets (passwords, tokens, private keys, raw cert material)
- be written with a write-ahead posture for security-sensitive actions

### Location (v0.2 normative)

The global UI audit log MUST be written under the workspace root at:

- `logs/ui_audit.jsonl`

This is distinct from run-local logs at `runs/<run_id>/logs/**`.

### Minimum required audit event set (v0.2)

The audit stream MUST include events for:

- authentication: login success/failure, logout, session expiry
- account admin: create/reset/disable (CLI actions SHOULD also be audited to same log)
- run verbs: start (verb name), completion (exit code + derived status), cancellation requests,
  resume/retry decisions
- quarantine access toggles
- artifact reads/downloads (path + allow/deny)
- export creation (include flags + allow/deny)

### UI audit event schema (v0.2)

Each JSONL row MUST contain at minimum:

- `ts`: RFC3339 timestamp

- `event_id`: UUID

- `actor`: object

  - `username` (string)
  - `auth_provider` (string; `local` for v0.2)

- `session_id`: string (or null for CLI-originated events)

- `client_ip`: string (best-effort; null allowed for CLI events)

- `action`: string (for example `auth.login`, `runs.start`, `runs.cancel`, `artifact.read`,
  `export.create`)

- `target`: object (action-dependent; MAY include `run_id`, `path`, `verb`, `export_id`)

- `outcome`: enum `allowed | denied | succeeded | failed`

- `reason_code`: string (UI-level reason codes; separate from ADR-0005 stage reason codes)

**Determinism requirement:** For a fixed sequence of API calls in a conformance fixture, the audit
log MUST be identical aside from timestamps and generated IDs (where permitted). If deterministic
IDs are required for CI fixtures, the implementation MUST support a “test mode” that seeds or
injects deterministic IDs.

## Artifact serving and redaction-safe viewing (v0.2 normative)

The Operator Interface serves artifacts for operator viewing and download. This is a major
disclosure boundary and MUST be explicitly constrained.

### Path allowlist (normative)

The UI MUST implement a **path allowlist** rooted at `runs/<run_id>/`.

Allowed (browseable + retrievable):

- `manifest.json`
- `ground_truth.jsonl`
- `inputs/`
- `lab/`
- `runner/`
- `raw_parquet/`
- `raw/`
- `normalized/`
- `criteria/`
- `bridge/`
- `detections/`
- `scoring/`
- `report/`
- `logs/`
- `security/`

Denied:

- `.staging/` (never served; never listed)
- `unredacted/` (quarantined; see below)

### Quarantine handling (normative)

Default:

- Requests for `unredacted/**` MUST return HTTP 403.
- Quarantine paths MUST NOT appear in directory listings.

Override (v0.2):

- Quarantine access requires BOTH:

  1. config `ui.security.allow_quarantine_access: true`
  1. a per-session runtime toggle enabled by the operator (default OFF; MUST NOT persist across
     sessions)

Audit:

- Every access to a quarantined path MUST emit a write-ahead audit event to `logs/ui_audit.jsonl`
  with:

  - actor identity
  - path
  - access type (list/read/download)
  - outcome (allowed/denied)

### MIME / extension policy (normative)

The UI MUST enforce **extension-based allowlisting** (no content sniffing).

Allowed extensions:

- `.json`, `.jsonl`, `.parquet`, `.txt`, `.html`, `.md`, `.csv`

Denied by default:

- `.evtx`, `.pcap`, `.exe`, `.dll`, and all other extensions not in the allowlist

Additional requirements:

- Extension matching MUST be case-insensitive (normalize to lowercase).
- Responses MUST include `X-Content-Type-Options: nosniff`.
- For `.html` responses, the UI SHOULD apply a restrictive Content Security Policy suitable for
  locally generated reports (no remote fetches).

### Path traversal defense (normative)

All artifact serving endpoints MUST:

- reject any path containing `..`, absolute paths, or URL-encoded equivalents
- normalize separators and enforce run-root containment
- allow only run-relative paths under the allowlisted roots above

### Export behavior (normative)

Exports MUST follow the orchestrator `export` verb semantics:

- default exclusions: `unredacted/`, `.staging/`, and binary evidence
- quarantine inclusion requires explicit `include_quarantine: true` plus confirmation prompt plus
  audit event
- binary evidence inclusion requires explicit `include_binary_evidence: true` plus confirmation
  prompt plus audit event

Every export MUST include an `export_manifest.json` that records:

- run_id
- export_id
- included paths (sorted lexicographically)
- excluded paths (sorted lexicographically) + exclusion reasons
- checksums for included files (at minimum sha256)

## Plan building (v0.2 normative)

### Draft plans

Draft plans MUST live in a workspace area outside the run bundle and MUST be explicitly referenced
when used for a run.

- Draft authoring format: YAML.
- Hash basis: canonical JSON derived from YAML, canonicalized using RFC 8785 JCS, then SHA-256.

**YAML restrictions (normative):**

- Draft YAML MUST be restricted to the JSON-compatible YAML subset:

  - no anchors/aliases
  - no duplicate keys
  - no non-JSON scalar types (timestamps, binary tags, etc.)

### Run association and immutability

When a plan draft is assigned to a run (for example, when starting `simulate`):

- the exact draft content MUST be copied into the run bundle (run-relative location is
  implementation-defined but MUST be deterministic and contract-backed)
- the plan hash MUST be recorded in the run manifest (or a manifest extension) and MUST match the
  copied draft

### Compiled plan artifacts

For v0.2 plan execution, compiled plan artifacts MUST be written under:

- `runs/<run_id>/plan/**`

Compiled artifacts MUST be treated as immutable once published. Runtime progress MUST be represented
via ground truth and per-action evidence, not by mutating the compiled plan graph.

## Run listing and monitoring (v0.2 normative)

### Run discovery mechanism

The Operator Interface MUST implement a run registry to define “what exists” (instead of relying
purely on nondeterministic directory enumeration).

- The registry is a control-plane artifact (global, not per-run).
- The registry MUST be rebuildable by scanning `runs/<run_id>/manifest.json` surfaces.

### Stable ordering

The run list default ordering MUST be stable:

1. primary sort: run start time (from manifest or registry record)
1. secondary sort: `run_id` lexical ordering

### Status derivation

Run status shown by the UI MUST be derived from the canonical run decision surfaces (manifest +
health) and MUST NOT be inferred from UI process state.

## Cancellation, resume, retry

This section defines **normative state machines** using ADR-0007’s template. These state machines
are scoped to Operator Interface behavior and required control artifacts. The orchestrator remains
responsible for correct stage outcomes and publish gates.

### Control artifacts (normative)

A run that is controlled via the Operator Interface MUST use run-local control artifacts under:

- `runs/<run_id>/control/`

Minimum required control artifacts:

- `runs/<run_id>/control/cancel.json` (durable cancellation request; atomic write)
- `runs/<run_id>/control/resume_decision.json` (resume decision output)
- `runs/<run_id>/control/retry_decision.json` (retry decision output)

#### `cancel.json` (v0.2 contract)

`cancel.json` MUST include:

- `request_id`: UUID
- `requested_at`: RFC3339 timestamp
- `requested_by`: username
- `mode`: `graceful | force`
- `scope`: `run | stage | action`
- `target`: object (scope-dependent; MUST include identifiers where applicable)
- `reason`: optional free text (MUST be redacted-safe)

Atomic write requirement:

- The control plane MUST write `cancel.json` via write-to-temp + atomic rename.

Durability requirement:

- The control plane MUST write `cancel.json` even if it also sends OS signals (signals are not
  durable).

### State machine: Cancellation request lifecycle (normative)

**Name:** `oi.cancel.request_lifecycle` **Scope:** per `(run_id)` **Authority:** Operator Interface
spec (v0.2) **Objective:** Make cancellation durable, idempotent, and observable while preserving
run-bundle decision surfaces.

#### States (closed set)

- `no_request`
- `requested_graceful`
- `requested_force`
- `terminal_observed`

#### Inputs / triggers

- `cancel_request(mode, scope, target)` from UI/API
- `run_terminal` (observed via orchestrator completion: manifest/health written, lock released)

#### State derivation (observability)

- `no_request` iff `control/cancel.json` does not exist
- `requested_graceful` iff `control/cancel.json` exists and `mode=graceful`
- `requested_force` iff `control/cancel.json` exists and `mode=force`
- `terminal_observed` iff run is terminal AND `control/cancel.json` exists

#### Transitions (normative)

- `no_request -> requested_graceful` on `cancel_request(graceful, …)`

  - Actions:

    - atomically write `control/cancel.json`
    - emit write-ahead audit event `runs.cancel_requested`
    - send OS signal to verb process (best-effort)

- `no_request -> requested_force` on `cancel_request(force, …)`

  - Actions as above, mode=force

- `requested_graceful -> requested_force` on `cancel_request(force, …)`

  - Guard: the existing request MAY be escalated; downgrade is forbidden

  - Actions:

    - update `control/cancel.json` atomically with mode=force (retain original request_id in an
      `escalates` field OR emit an audit event indicating escalation)
    - emit audit event `runs.cancel_escalated`
    - send stronger OS signal (best-effort)

- `requested_- -> terminal_observed` on `run_terminal`

Illegal transitions:

- `requested_force -> requested_graceful` MUST NOT occur.

#### Required observability outputs

- `control/cancel.json` exists after any cancel request.

- `logs/ui_audit.jsonl` contains:

  - `runs.cancel_requested` (and possibly `runs.cancel_escalated`) before the system attempts to
    stop the run.

- The run’s `logs/health.json` MUST still be emitted per orchestrator semantics; cancellation MUST
  be observable via:

  - presence of `control/cancel.json`
  - terminal status of the run

#### Conformance tests (minimum)

1. Happy path: start run → cancel graceful → run terminates → `terminal_observed` derived.
1. Escalation: cancel graceful → cancel force → verify mode escalation and single durable cancel
   artifact.
1. Idempotency: submit same cancel request twice → no duplicated side effects beyond audit entries;
   cancel.json remains valid.
1. Determinism: repeat fixture twice → artifacts identical except timestamps/UUIDs (or deterministic
   IDs in test mode).

### Resume and retry (v0.2 normative)

#### Drift gate (authoritative signal)

The authoritative drift signal for resume/retry decisions is:

- Compare prior run manifest’s `lab.inventory_snapshot_sha256` to the current lab’s inventory
  snapshot hash.
- Inventory snapshot hashing MUST use RFC 8785 JCS canonicalization + SHA-256, consistent with the
  project’s canonical JSON posture.

Reserved future drift inputs (non-blocking extension points):

- config hash signals
- criteria pack hash signals
- mapping pack/profile hash signals
- plan hash signals

#### Decision function (normative)

A resume/retry request MUST produce a decision object with:

- **Inputs:**

  - prior manifest
  - current lab hash
  - drift report
  - requested scope (run/stage/action)
  - policy flags (including operator override)

- **Outputs:**

  - `decision`: `same_run | continuation_run | denied`
  - `run_id`: chosen run_id (existing or new)
  - `baseline_run_ref`: reference to prior run when `continuation_run`
  - `reason_code`: machine-readable reason

Policy controls MUST allow explicit operator opt-in to resume-despite-drift, but the default MUST be
conservative (deny or require continuation run unless explicitly allowed).

#### Artifact anchors (normative)

Resume/retry MUST treat the following as authoritative anchors (do not mutate compiled plan
artifacts):

- Run-level: run lock presence + manifest stage outcomes
- Node-level: terminal rows in `ground_truth.jsonl` + presence of `runner/actions/<action_id>/`
- Stage-level: stage outcome entries + IO boundary artifacts

Node status MUST be derived from ground truth `outcome`, not by mutating plan artifacts.

### State machine: Resume/retry decision lifecycle (normative)

**Name:** `oi.resume_retry.decision_lifecycle` **Scope:** per `(request_id)` **Authority:** Operator
Interface spec (v0.2)

#### States (closed set)

- `idle`
- `evaluating_drift`
- `decided_same_run`
- `decided_continuation_run`
- `decided_denied`

#### Transitions (normative)

- `idle -> evaluating_drift` on `resume_request` or `retry_request`

  - Actions:

    - read prior `lab.inventory_snapshot_sha256`
    - compute current inventory snapshot hash deterministically
    - emit audit event `runs.resume_retry_requested` (write-ahead)

- `evaluating_drift -> decided_same_run` when drift policy allows same-run continuation

  - Output:

    - write `control/resume_decision.json` or `control/retry_decision.json`

- `evaluating_drift -> decided_continuation_run` when drift policy requires new run

  - Output includes new run_id and baseline reference.

- `evaluating_drift -> decided_denied` when policy denies the request

  - Output includes reason_code.

#### Required conformance tests (minimum)

1. No drift: decision is `same_run` when policy allows.
1. Drift detected: decision is `continuation_run` (or `denied`, depending on configured policy).
1. Override path: drift detected + operator override enabled → allowed decision + audit event.
1. Determinism: repeat drift fixture twice → decision output identical aside from timestamps/UUIDs
   (or deterministic IDs in test mode).

## Configuration surface (v0.2)

This spec introduces a UI namespace. These keys MUST be added to the configuration reference in the
same implementation change set (TODO for this draft).

```yaml
ui:
  enabled: true

  network:
    profile: lan_reverse_proxy   # v0.2 target
    port: 443
    allowlist:
      # CIDRs and/or IPs
      - 192.168.0.0/16
      - 10.0.0.0/8
    default_deny: true

  tls:
    mode: self_signed_ca         # default
    rotate_leaf_on_start: true
    # reserved (future):
    cert_path: null
    key_path: null
    ca_path: null

  security:
    allow_quarantine_access: false
    allowed_extensions: [".json", ".jsonl", ".parquet", ".txt", ".html", ".md", ".csv"]

  sessions:
    idle_timeout_seconds: 1200

  limits:
    max_concurrent_runs: 1

auth:
  provider: local                # reserved: ldap, oidc
  mfa:
    enabled: false               # reserved
    method: null                 # reserved: totp, webauthn

otel_gateway:
  enabled: true
  ports:
    grpc: 4317
    http: 4318
  mtls:
    required: true
    # v0.2 may generate these in workspace state by default
    ca_path: null
    server_cert_path: null
    server_key_path: null
```

## Open items and required follow-ups for implementation

This document is a v0.2 draft. The following MUST be addressed in the implementation change set(s)
that adopt it:

1. **Data contracts**

   - Register new contract-backed artifacts for:

     - `runs/<run_id>/control/cancel.json`
     - `runs/<run_id>/control/resume_decision.json`
     - `runs/<run_id>/control/retry_decision.json`
     - `logs/ui_audit.jsonl`
     - `export_manifest.json` (export output)

1. **ADR-0005 reason code registry**

   - If cancellation/resume/retry introduce new stage-level reason codes, ADR-0005 MUST be updated
     accordingly (per ADR-0007 requirements).

1. **Config reference**

   - Add `ui.*`, `auth.*` (UI scope), and `otel_gateway.*` keys and schema constraints.

## References

## Changelog

| Date       | Change                                                                                                                                                                                    |
| ---------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2026-01-21 | Initial draft defining web Operator Interface, LAN reverse-proxy profile, local auth, audit logging, artifact serving constraints, and explicit cancellation/resume/retry state machines. |
