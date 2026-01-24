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
  - 045_storage_formats.md
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

1. An **Operator API (HTTP)** used by the UI, designed so that:

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
- **Operator Interface (OI)**: The operator-facing web UI + the HTTP Operator API service backing it
  (called the “control-plane API” in this document). This is distinct from any reserved
  endpoint-management “control plane” functionality described elsewhere in the project.
- **Reverse proxy (RP)**: The in-container TLS terminator and request gatekeeper for the UI.
- **Verb**: A stable orchestrator entry point (for example: `build`, `simulate`, `replay`, `export`,
  `destroy`).
- **Run bundle**: `runs/<run_id>/` filesystem root containing all run artifacts, as defined
  elsewhere.
- **Workspace root**: The appliance’s durable data root (usually volume-mounted). It contains
  `runs/` (run bundles) and additional operator/control-plane directories such as `state/` (secrets
  \+ durable UI control-plane state), `logs/` (appliance logs), `plans/` (draft plans), and
  `exports/` (derived export outputs).
- **Quarantine path**: The run-bundle subpath excluded from default disclosure. The quarantine
  directory is `runs/<run_id>/<security.redaction.unredacted_dir>`, where
  `security.redaction.unredacted_dir` MUST be a **run-relative** directory name (no leading `/` or
  `\\`, no `..` segments, and no URL-encoded equivalents). Implementations MUST normalize the value
  by trimming leading/trailing separators and then treating it as `<dir>/` for containment checks.
  Default: `runs/<run_id>/unredacted/`.
- **Control artifacts**: Durable, run-local files under `runs/<run_id>/control/` used for
  operator-driven run control (cancel/resume/retry) without introducing a database for pipeline
  correctness.

## Workspace layout (v0.2 normative)

The workspace root is a filesystem trust boundary for durable appliance data. v0.2 implementations
MUST treat the following workspace-root children as **reserved** and MUST NOT place unrelated
content at these paths.

### Required directories (v0.2)

The appliance MUST ensure these directories exist (creating them if necessary) before serving the UI
or accepting Operator API calls:

| Path (workspace-root relative) | Purpose                                             | Sensitivity | Default perms |
| ------------------------------ | --------------------------------------------------- | ----------- | ------------- |
| `runs/`                        | Run bundles (pipeline outputs; authoritative)       | mixed       | 0750          |
| `state/`                       | Secrets + durable control-plane state               | high        | 0700          |
| `logs/`                        | Appliance-local logs (including `ui_audit.jsonl`)   | medium      | 0750          |
| `plans/`                       | Plan drafts + draft metadata (OI-authored)          | medium      | 0700          |
| `exports/`                     | Derived exports (archives + `export_manifest.json`) | high        | 0700          |

Notes:

- `runs/` is the only directory whose contents are treated as authoritative pipeline outputs.
- `state/` MUST NOT be served by the artifact-serving endpoints.
- `exports/` MUST NOT be served by the run artifact endpoints; exports are accessed only via
  explicit export download endpoints and policy gates.

### Permissions and fail-closed posture

- The appliance MUST fail closed (refuse to start UI ingress) if:

  - `<workspace_root>/state/` exists but is not owned by the appliance user, OR
  - `<workspace_root>/state/` permissions are more permissive than 0700, OR
  - any private key file under `<workspace_root>/state/` has permissions more permissive than 0600.

- The appliance SHOULD apply similar checks to `<workspace_root>/plans/` and
  `<workspace_root>/exports/`.

### Atomic writes (control-plane artifacts)

All control-plane writes under the workspace root MUST be crash-safe:

- Append-only logs (for example `logs/ui_audit.jsonl`) MUST use append + flush-to-durable storage
  semantics (`fsync()` or equivalent) for write-ahead audit records.
- Replacement-style JSON artifacts (for example `state/run_registry.json`) MUST be written via
  write-to-temp + atomic rename.
- When supported, implementations SHOULD `fsync()` the containing directory after atomic rename to
  reduce rename-loss risk on crash.

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
   - v0.2 minimum: rate-limit `POST /api/auth/login` at the reverse proxy boundary

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
- The CA private key MUST be stored only in the workspace root’s protected state directory (v0.2
  default: `<workspace_root>/state/`; directory permissions 0700; key file permissions 0600) and
  MUST NOT be written into any run bundle.

**Certificate identity and distribution (normative):**

- The appliance MUST persist the UI CA certificate (public) at `<workspace_root>/state/ui_ca.pem` so
  operators can trust the appliance UI in their browser.
- The per-session leaf certificate MUST include Subject Alternative Names (SANs) sufficient for LAN
  access:
  - MUST include: `localhost`, `127.0.0.1`, and `::1`
  - SHOULD include: all non-loopback interface IP addresses present at startup, and any configured
    DNS name used for UI access
- The per-session leaf private key MUST be generated fresh on each appliance start and SHOULD NOT be
  persisted to the workspace root unless required by the reverse proxy implementation.

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

- v0.2 MAY use a locally generated OTLP CA (similar to UI CA) persisted under the workspace root’s
  protected state directory (v0.2 default: `<workspace_root>/state/`).
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

v0.2 MUST implement:

- The OI service spawns orchestrator verb processes (subprocess execution).
- The OI service streams logs/status by reading the run bundle artifacts and log files produced by
  the orchestrator process.

#### Concurrency control (v0.2 normative)

- The OI service MUST enforce `ui.limits.max_concurrent_runs` across concurrently active
  orchestrator verb processes started via the Operator API (where “active” means the child process
  has been spawned and has not yet exited).

- In addition, the OI service MUST enforce **per-run mutual exclusion**:

  - For a given `run_id`, the OI service MUST NOT spawn more than one verb process at a time.
  - If a verb-start request arrives for a `run_id` that already has an active verb process, the
    request MUST be rejected with HTTP 409 and MUST emit a `runs.start` audit event with
    `outcome=denied` and `reason_code=run_busy`.

- The OI service MUST treat orchestrator run locks as authoritative for safe start:

  - Before spawning any verb process that mutates or reads run-bundle state, the OI service MUST
    check for the presence of the run lock at `runs/.locks/<run_id>.lock` (see ADR-0004).
  - If a lock is present and the OI service does not own the corresponding process, the request MUST
    be rejected with HTTP 409 and MUST emit a `runs.start` audit event with `outcome=denied` and
    `reason_code=run_lock_held`.

- When `ui.limits.max_concurrent_runs` is reached, additional verb-start requests MUST be rejected
  without spawning a new verb process, and a `runs.start` audit event with `outcome=denied` and
  `reason_code=concurrency_limit` MUST be emitted.

A future version MAY implement a long-running daemon/queue model, but only if it preserves run-lock,
publish-gate, and outcome-recording semantics and does not introduce a database as the authoritative
pipeline state store.

## Operator API (HTTP) (v0.2 normative)

The Operator API is the programmatic interface used by the web UI. It is designed so that
non-browser clients (CLI, automation) can be added later without breaking API shape.

### API conventions (normative)

- Base path: `/api` (v0.2 default). All Operator API endpoints MUST be rooted under this prefix.
- Request and response bodies MUST be UTF-8 JSON (`application/json; charset=utf-8`) unless
  explicitly noted (artifact/export download endpoints).
- The API MUST set `Cache-Control: no-store` on all authenticated responses.
- The API SHOULD set `X-Request-ID` on every response.

### Authentication and authorization (normative)

- The API MUST use the same session mechanism described in [Sessions](#sessions-v02-normative).
- Unless explicitly stated otherwise, all Operator API endpoints MUST require an authenticated
  session cookie.
- In v0.2, any authenticated user is a full operator; therefore authorization is binary:
  authenticated vs unauthenticated.
- The API MUST reject unauthenticated requests with HTTP 401.
- The API MUST reject authenticated-but-disallowed requests (future RBAC) with HTTP 403.

CSRF / origin protection (v0.2 minimum):

- For any state-changing request (POST/PUT/PATCH/DELETE) authenticated via cookie, the API MUST
  validate the `Origin` header (when present) against the request host and MUST reject mismatches
  with HTTP 403 (`reason_code=origin_mismatch`).

### Error response schema (v0.2 normative)

When returning an error status (4xx/5xx), the API MUST return a JSON body of the form:

```json
{
  "error": {
    "http_status": 403,
    "reason_code": "artifact_path_denied",
    "message": "Access denied.",
    "details": {}
  }
}
```

- `reason_code` MUST be `lower_snake_case` and is UI-level (separate from ADR-0005 stage reason
  codes).
- `message` MUST be safe for operator display and MUST NOT disclose quarantined path contents or
  other\
  sensitive information.

### Required endpoints (v0.2 normative minimum set)

#### System / status

- `GET /api/status`
  - Returns appliance build/version info and component status.
  - MUST include:
    - appliance version/build info
    - UI auth status (current user, or unauthenticated)
    - OTLP gateway status (`enabled`, `up`, `mtls_required`)

#### Authentication

- `POST /api/auth/login`
  - Body: `{ "username": "<string>", "password": "<string>" }`
  - On success: MUST establish a session cookie and return `{ "username": "<string>" }`.
  - On failure: MUST return HTTP 401 with `reason_code=auth_invalid_credentials` (do not disclose\
    whether the username exists).
- `POST /api/auth/logout`
  - Terminates the current session (server-side) and clears the session cookie.
  - Returns HTTP 204 on success.
- `GET /api/auth/session`
  - Returns the current session summary or HTTP 401 if not authenticated.
  - MUST include:
    - `username`
    - `auth_provider`
    - `session_id`
    - `expires_at` (RFC3339)
    - `quarantine_access_enabled` (boolean; per-session toggle; default false)
- `POST /api/session/quarantine-access`
  - Body: `{ "enabled": true|false }`
  - Enables/disables the per-session quarantine access toggle (only if the global config gate
    allows).
  - MUST emit an audit event `quarantine.toggle`.

#### Plan drafts (workspace artifacts)

- `GET /api/plans/drafts`
- `POST /api/plans/drafts`
- `GET /api/plans/drafts/{draft_id}`
- `PUT /api/plans/drafts/{draft_id}`
- `POST /api/plans/drafts/{draft_id}/compile`

The compile preview endpoint MUST NOT mutate the draft; it returns the compiled plan graph and any\
validation errors.

#### Runs

- `GET /api/runs`
  - Returns the run list using the stable ordering defined in Stable ordering.
- `GET /api/runs/{run_id}`
  - Returns at minimum:
    - `run_id`
    - `manifest` (the parsed `manifest.json`)
    - `health` (parsed `logs/health.json` when present; null otherwise)
- `POST /api/runs`
  - Creates a run and (optionally) starts a verb.

  - v0.2 minimum request shape:

    ```json
    {
      "draft_id": "<uuid>",
      "verb": "simulate"
    }
    ```

  - The API MAY support an optional client-supplied `run_id`, but if absent the OI service MUST\
    generate a UUID.

  - On success it MUST return HTTP 201 with `{ "run_id": "<uuid>" }`.
- `POST /api/runs/{run_id}/verbs/{verb}`
  - Starts an orchestrator verb process (`build`, `simulate`, `replay`, `export`, `destroy`)
  - MUST enforce the concurrency constraints in Execution model.
  - Returns HTTP 202 on successful spawn.

#### Run control

- `POST /api/runs/{run_id}/cancel`
- `POST /api/runs/{run_id}/resume`
- `POST /api/runs/{run_id}/retry`

These endpoints MUST create and/or update the corresponding `runs/<run_id>/control/**` artifacts as\
defined in Cancellation, resume, retry.

#### Artifact browsing and retrieval

- `GET /api/runs/{run_id}/artifacts`
- `GET /api/runs/{run_id}/artifacts/{path}`

These endpoints MUST enforce Artifact serving and redaction-safe viewing.\
`GET /api/runs/{run_id}/artifacts/{path}` SHOULD support HTTP Range requests for efficient log
tailing.

#### Exports

- `POST /api/runs/{run_id}/exports`
- `GET /api/exports/{export_id}`
- `GET /api/exports/{export_id}/download`

Export endpoints MUST enforce the export gates in Export behavior and\
MUST NOT treat exports as ordinary run artifacts.

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
   - `logs/run.log` viewing (stable human-readable diagnostic log)
   - stage outcome view derived from `logs/health.json` when present; otherwise indicate that health
     output is unavailable and fall back to run-level status from `manifest.json`
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
- be written with a write-ahead posture for security-sensitive actions (append the audit row and
  flush to durable storage before attempting the gated action)

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

- `ts`: RFC3339 timestamp (UTC, with `Z` suffix)
- `event_id`: UUID
- `actor`: object
  - `username` (string)
  - `auth_provider` (string; `local` for v0.2)
- `session_id`: string (or null for CLI-originated events)
- `client_ip`: string (best-effort; null allowed for CLI events)
- `action`: string
  - MUST be dot-separated segments
  - each segment MUST be `lower_snake_case`
  - examples: `auth.login`, `runs.start`, `runs.cancel_requested`, `artifact.read`, `export.create`
- `target`: object (action-dependent; MAY include `run_id`, `path`, `verb`, `export_id`,
  `request_id`)
- `outcome`: enum `allowed | denied | succeeded | failed`
- `reason_code`: string
  - required when `outcome ∈ {denied, failed}`
  - optional otherwise
  - UI-level reason codes are separate from ADR-0005 stage reason codes.

Outcome semantics (normative):

- `allowed | denied` represent an authorization or policy gate decision taken before attempting the
  action.
- `succeeded | failed` represent completion of an action that was attempted.

Serialization and determinism (normative):

- Each audit row MUST be serialized as UTF-8 JSON followed by a single `\n`.
- Implementations MUST use a deterministic JSON serializer for audit rows.
  - RECOMMENDED: RFC 8785 JCS canonical JSON for the JSON object prior to appending `\n`.
- For a fixed sequence of API calls in a conformance fixture, the audit log MUST be identical aside
  from timestamps and generated IDs (where permitted). If deterministic IDs are required for CI
  fixtures, the implementation MUST support a “test mode” that seeds or injects deterministic IDs.

Minimum v0.2 `reason_code` registry (normative closed set):

- `auth_invalid_credentials`
- `auth_account_disabled`
- `session_expired`
- `allowlist_denied`
- `origin_mismatch`
- `concurrency_limit`
- `run_busy`
- `run_lock_held`
- `run_not_found`
- `run_already_terminal`
- `artifact_path_denied`
- `artifact_extension_denied`
- `artifact_path_traversal`
- `quarantine_access_disabled`
- `export_policy_denied`
- `config_validation_failed`

## Artifact serving and redaction-safe viewing (v0.2 normative)

The Operator Interface serves artifacts for operator viewing and download. This is a major
disclosure boundary and MUST be explicitly constrained.

### Path allowlist (normative)

The UI MUST implement a **path allowlist** rooted at `runs/<run_id>/`.

Allowed (browseable + retrievable):

- `manifest.json`
- `ground_truth.jsonl`
- `inputs/`
- `plan/`
- `control/`
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
- `unredacted/` (quarantined; see below; default name — implementations MUST also quarantine
  `security.redaction.unredacted_dir`)

Directory listing requirements (normative):

- Directory listings MUST be deterministic.
- Listing order MUST be run-relative POSIX path ascending (UTF-8 byte order; no locale).
- Denied and quarantined paths MUST NOT appear in listings.

### Quarantine handling (normative)

Default:

- Requests for the quarantine directory (run-relative `unredacted/**` by default, or the configured
  `security.redaction.unredacted_dir/**`) MUST return HTTP 403.
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

- `.json`, `.jsonl`, `.parquet`, `.txt`, `.log`, `.html`, `.md`, `.csv`, `.cast`, `.yaml`, `.yml`

Denied by default:

- `.evtx`, `.pcap`, `.exe`, `.dll`, and all other extensions not in the allowlist

Additional requirements:

- Extension matching MUST be case-insensitive (normalize to lowercase).
- Responses MUST include `X-Content-Type-Options: nosniff`.
- For `.html` responses, the UI SHOULD apply a restrictive Content Security Policy suitable for
  locally generated reports (no remote fetches).
- For `.log`, `.txt`, `.json`, `.jsonl`, `.md`, `.csv`, `.yaml`, `.yml`, and `.cast` responses, the
  UI SHOULD support HTTP Range requests (byte ranges) to enable efficient tailing and paging.
- For `.cast` responses, the UI MUST treat them as `application/json`.
  - The UI MUST provide an inline asciinema playback viewer using locally bundled player assets (no
    remote fetches).
  - A plain-text view MUST remain available as a fallback.
  - The viewer MUST be able to render deterministic placeholder `.cast` artifacts produced under the
    redaction posture (placeholders are valid asciinema v2 cast files).
  - The viewer SHOULD expose at least play/pause and seek controls; it MAY expose speed controls
    when supported by the chosen player library.

### Path traversal defense (normative)

All artifact serving endpoints MUST:

- reject any path containing `..`, absolute paths, or URL-encoded equivalents
- normalize separators and enforce run-root containment
- allow only run-relative paths under the allowlisted roots above

### Export behavior (normative)

Exports MUST follow the orchestrator `export` verb semantics:

- default exclusions: the quarantine directory (`unredacted/` by default;
  `security.redaction.unredacted_dir` when configured), `.staging/`, and binary evidence
- quarantine inclusion requires explicit `include_quarantine: true` plus confirmation prompt plus
  audit event
- binary evidence inclusion requires explicit `include_binary_evidence: true` plus confirmation
  prompt plus audit event

**Export output location (normative):**

- Export outputs MUST be written outside the run bundle, under the workspace root:
  - `<workspace_root>/exports/<run_id>/<export_id>/`
- `export_id` MUST be a UUID.
- Export filenames MUST NOT include timestamps.

**Export manifest (normative):**

Every export MUST include an `export_manifest.json` written adjacent to the produced export output,
and included in the root of the archive when the output is an archive format. The manifest MUST
record:

- run_id
- export_id
- included paths (run-relative POSIX paths; sorted lexicographically)
- excluded paths (run-relative POSIX paths; sorted lexicographically) + exclusion reasons
- checksums for included files (at minimum sha256, lowercase hex)

Audit (normative):

- Export creation MUST emit an audit event `export.create` with inclusion flags and outcome.
- Export download MUST emit an audit event `export.download` with `export_id` and outcome.

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

**Draft storage (v0.2 normative):**

- Drafts MUST be stored under `<workspace_root>/plans/drafts/`.
- Each draft MUST be represented by a directory named by `draft_id` (UUID), containing:
  - `plan.yaml` (the draft YAML, exactly as last saved)
  - `draft.json` (metadata)
- `draft.json` MUST include at minimum:
  - `draft_id` (UUID)
  - `plan_sha256` (string; lowercase hex; computed as specified above for the current `plan.yaml`)
  - `created_at_utc` (RFC3339)
  - `updated_at_utc` (RFC3339)
- Writes to `plan.yaml` and `draft.json` MUST use write-to-temp + atomic rename.

### Run association and immutability

When a plan draft is assigned to a run (for example, when starting `simulate`):

- the exact draft YAML content MUST be copied into the run bundle at:
  - `runs/<run_id>/inputs/plan_draft.yaml`
- the plan hash (`plan_sha256`) MUST be recorded in the run manifest under:
  - `manifest.extensions.operator_interface.plan_draft_sha256`
- the run manifest MUST also record the run-relative plan snapshot path under:
  - `manifest.extensions.operator_interface.plan_draft_path` (v0.2 value: `inputs/plan_draft.yaml`)
- the recorded hash MUST match the copied draft (computed as specified in
  [Draft plans](#draft-plans))

Once copied into `runs/<run_id>/inputs/plan_draft.yaml`, the plan snapshot MUST be treated as
immutable for the lifetime of the run.

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
- v0.2 default location: `<workspace_root>/state/run_registry.json` (single JSON object; written via
  write-to-temp + atomic rename).
- A run MUST be considered present if and only if `runs/<run_id>/manifest.json` exists and validates
  against the manifest contract.
- The registry MUST be rebuildable by scanning `runs/<run_id>/manifest.json` surfaces.
  - The scan MUST ignore non-run directories under `runs/` (for example `.locks/`).
  - The scan order MUST be deterministic: enumerate candidate run directories and sort by `run_id`
    ascending (UTF-8 byte order) before reading manifests.

v0.2 registry schema (normative):

```json
{
  "schema_version": 1,
  "runs": [
    { "run_id": "<uuid>", "started_at_utc": "<rfc3339>" }
  ]
}
```

- `runs[]` MUST be stored in the stable ordering defined in Stable ordering.

### Stable ordering

The run list default ordering MUST be stable and MUST be defined in terms of manifest fields:

1. primary sort: `manifest.started_at_utc` (descending; most recent first)
1. secondary sort: `manifest.run_id` UTF-8 byte order (ascending; no locale)

### Status derivation

Run status shown by the UI MUST be derived from the canonical run decision surfaces and MUST NOT be
inferred from UI process state:

- `manifest.json` is authoritative for overall run status (`manifest.status`) and stage outcomes.
- When `logs/health.json` is present, the UI MUST use it to display per-stage (and dotted substage)
  outcomes.
- When `logs/health.json` is absent (for example, when
  `operability.health.emit_health_files=false`), the UI MUST still display run-level status from
  `manifest.json` and MUST indicate that health output is disabled/unavailable (do not guess
  per-stage state).

### Run timeline surface (v0.2 normative)

When a run contains `report/run_timeline.md`, the UI MUST surface it as a first-class run detail
view suitable for human triage.

Requirements:

- The UI MUST render `report/run_timeline.md` via the standard artifact viewer.
  - If the UI renders Markdown, it MUST do so with safe rendering (raw HTML disabled/sanitized by
    default).
- The UI MUST preserve timestamps exactly as written (UTC, RFC3339 with `Z`) and MUST NOT silently
  localize or reformat them.
- If the rendered timeline contains links to evidence artifacts (including `.cast` terminal
  recordings), activating those links MUST open the evidence using the corresponding safe viewer
  (including the inline asciinema playback viewer for `.cast`).
- If `report/run_timeline.md` is absent, the UI MUST indicate that the timeline is not available
  (for example, reporting not completed) rather than synthesizing or guessing a timeline.

Verification hooks:

- UI integration test: given a run bundle containing `report/run_timeline.md` and a referenced
  `runner/actions/<action_id>/terminal.cast`, verify:
  - the timeline view is present,
  - `.cast` opens the inline player,
  - no remote assets are fetched.

## Cancellation, resume, retry

This section defines **normative state machines** using ADR-0007’s template. These state machines
are scoped to Operator Interface behavior and required control artifacts. The orchestrator remains
responsible for correct stage outcomes and publish gates.

### Control artifacts (normative)

A run that is controlled via the Operator Interface MUST use run-local control artifacts under:

- `runs/<run_id>/control/`

Minimum required control artifacts:

- `runs/<run_id>/control/cancel.json` (durable cancellation request; atomic write)
- `runs/<run_id>/control/resume_request.json` (durable resume request; atomic write)
- `runs/<run_id>/control/resume_decision.json` (resume decision output)
- `runs/<run_id>/control/retry_request.json` (durable retry request; atomic write)
- `runs/<run_id>/control/retry_decision.json` (retry decision output)

#### `cancel.json` (v0.2 contract)

`cancel.json` MUST include:

- `request_id`: UUID (generated on the first cancellation request; MUST NOT change on escalation)
- `requested_at`: RFC3339 timestamp (time of the first request; MUST NOT change on escalation)
- `requested_by`: username (or a stable CLI actor string; example: `cli`)
- `mode`: `graceful | force` (current requested mode; MAY be escalated from graceful→force)
- `scope`: `run | stage | action` (v0.2 MUST support `scope="run"`; other scopes are reserved but
  MAY be supported)
- `target`: object (scope-dependent)
  - when `scope="run"`, `target` MUST be `{}` or omitted
  - when `scope="stage"`, `target.stage` MUST be a stable stage identifier (example: `telemetry`)
  - when `scope="action"`, `target.action_id` MUST be an `action_id` from `ground_truth.jsonl`
- `reason`: optional free text (MUST be redacted-safe)
- `escalated_at`: RFC3339 timestamp (optional; present only when mode changes from `graceful` to
  `force`)
- `escalated_by`: username (optional; present only when mode changes from `graceful` to `force`)

Atomic write requirement:

- The control plane MUST write `cancel.json` via write-to-temp + atomic rename.

Durability requirement:

- The control plane MUST write `cancel.json` even if it also sends OS signals (signals are not
  durable).

#### `resume_request.json` / `retry_request.json` (v0.2 contract)

Each request file MUST be a single JSON object written to its corresponding path under
`runs/<run_id>/control/` and MUST be written via write-to-temp + atomic rename.

Each request object MUST include:

- `request_id`: UUID
- `requested_at`: RFC3339 timestamp
- `requested_by`: username (or a stable CLI actor string; example: `cli`)
- `scope`: `run | stage | action` (v0.2 MUST support `scope="run"`; other scopes are reserved but
  MAY be supported)
- `target`: object (scope-dependent; same rules as `cancel.json`)
- `override_drift`: boolean (default false; when true, explicitly requests resume/retry despite
  drift)
- `reason`: optional free text (MUST be redacted-safe)

If a new resume/retry request is issued for the same `run_id`, the corresponding request file MUST
be overwritten atomically (the latest request is authoritative; prior requests are discoverable via
the audit log).

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
- `run_terminal` (observed via orchestrator completion: manifest written, run lock released;
  `logs/health.json` MAY be written when enabled)
- `run_missing` (run_id does not exist or manifest invalid)

#### State derivation (observability)

- `no_request` iff `control/cancel.json` does not exist
- `requested_graceful` iff `control/cancel.json` exists and `mode=graceful`
- `requested_force` iff `control/cancel.json` exists and `mode=force`
- `terminal_observed` iff run is terminal AND `control/cancel.json` exists

#### Transitions (normative)

- `no_request -> requested_graceful` on `cancel_request(graceful, …)`
  - Guard: if the run is already terminal, the request MUST be denied (do not write `cancel.json`)
  - Actions:
    - atomically write `control/cancel.json`
    - emit write-ahead audit event `runs.cancel_requested`
    - send OS signal to verb process (best-effort)
- `no_request -> requested_force` on `cancel_request(force, …)`
  - Guard: if the run is already terminal, the request MUST be denied (do not write `cancel.json`)
  - Actions as above, mode=force
- `requested_graceful -> requested_force` on `cancel_request(force, …)`
  - Guard: the existing request MAY be escalated; downgrade is forbidden
  - Actions:
    - update `control/cancel.json` atomically with mode=force and set `escalated_at` /
      `escalated_by` (preserve `request_id`, `requested_at`, and `requested_by`)
    - emit audit event `runs.cancel_escalated`
    - send stronger OS signal (best-effort)
- `requested_- -> terminal_observed` on `run_terminal`
- `* -> *` on `cancel_request(*, …)` when `run_terminal` is already true
  - Actions:
    - MUST respond as denied (HTTP 409 in the Operator API)
    - emit audit event `runs.cancel_requested` with `outcome=denied` and
      `reason_code=run_already_terminal`
    - MUST NOT write or modify `control/cancel.json`
- `* -> *` on `run_missing` (observed during cancel request handling)
  - Actions:
    - MUST respond as denied (HTTP 404 in the Operator API)
    - emit audit event `runs.cancel_requested` with `outcome=denied` and `reason_code=run_not_found`
    - MUST NOT write or modify `control/cancel.json`

Illegal transitions:

- `requested_force -> requested_graceful` MUST NOT occur.

#### Required observability outputs

- `control/cancel.json` exists after any cancel request.
- `logs/ui_audit.jsonl` contains:
  - `runs.cancel_requested` (and possibly `runs.cancel_escalated`) before the system attempts to
    stop the run.
- Cancellation MUST be observable via:
  - presence of `control/cancel.json`
  - terminal status of the run derived from `manifest.json` (and `logs/health.json` when present)

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
  - `run_id`: chosen run_id (existing or new) when `decision ∈ {same_run, continuation_run}`; null
    when `decision=denied`
  - `baseline_run_id`: prior `run_id` when `decision=continuation_run`; null otherwise
  - `reason_code`: machine-readable reason

Policy controls MUST allow explicit operator opt-in to resume-despite-drift, but the default MUST be
conservative (deny or require continuation run unless explicitly allowed).

#### Artifact anchors (normative)

Resume/retry MUST treat the following as authoritative anchors (do not mutate compiled plan
artifacts):

- Run-level: run lock presence + manifest stage outcomes
- Node-level: the `ground_truth.jsonl` row for `action_id` (terminal by definition) + presence of
  `runner/actions/<action_id>/`
- Stage-level: stage outcome entries + IO boundary artifacts

Node status MUST be derived from ground truth `outcome`, not by mutating plan artifacts.

### State machine: Resume/retry decision lifecycle (normative)

**Name:** `oi.resume_retry.decision_lifecycle` **Scope:** per `(run_id, decision_type)`
**Authority:** Operator Interface spec (v0.2)

#### States (closed set)

- `idle`
- `evaluating_drift`
- `decided_same_run`
- `decided_continuation_run`
- `decided_denied`

#### Inputs / triggers (closed set)

- `resume_request(scope, target, override_drift)` from UI/API
- `retry_request(scope, target, override_drift)` from UI/API

#### State derivation (observability; normative)

Let `request_file` be:

- `control/resume_request.json` when `decision_type="resume"`
- `control/retry_request.json` when `decision_type="retry"`

Let `decision_file` be:

- `control/resume_decision.json` when `decision_type="resume"`
- `control/retry_decision.json` when `decision_type="retry"`

Derive state deterministically:

- `idle` iff `request_file` does not exist
- `evaluating_drift` iff `request_file` exists AND `decision_file` does not exist
- `decided_same_run` iff `decision_file` exists AND `decision.decision="same_run"`
- `decided_continuation_run` iff `decision_file` exists AND `decision.decision="continuation_run"`
- `decided_denied` iff `decision_file` exists AND `decision.decision="denied"`

#### Transitions (normative)

- `idle -> evaluating_drift` on `resume_request` or `retry_request`
  - Guards:
    - The run MUST exist (`runs/<run_id>/manifest.json` validates), else deny the request.
    - The run MUST NOT be actively running (run lock present or active verb process), else deny the
      request.
  - Actions:
    - atomically write `request_file`
    - read prior `lab.inventory_snapshot_sha256`
    - compute current inventory snapshot hash deterministically (using the same snapshot + hashing
      method as the `lab_provider` stage)
    - emit audit event `runs.resume_retry_requested` (write-ahead; `outcome=allowed|denied`)
- `evaluating_drift -> decided_same_run` when drift policy allows same-run continuation
  - Output:
    - write `decision_file` atomically
- `evaluating_drift -> decided_continuation_run` when drift policy requires a new run
  - Output includes new run_id and baseline reference.
  - write `decision_file` atomically
- `evaluating_drift -> decided_denied` when policy denies the request
  - Output includes reason_code.
  - write `decision_file` atomically

#### Illegal transition handling (normative)

- `decided_* -> evaluating_drift` MUST NOT occur without a new request overwriting `request_file`.
- If `decision_file` exists but is invalid/unreadable, the UI MUST fail closed for resume/retry UI
  actions and MUST surface the condition to the operator as an error (do not guess state).

#### Required conformance tests (minimum)

1. No drift: decision is `same_run` when policy allows; both request and decision artifacts exist.
1. Drift detected: decision is `continuation_run` (or `denied`, depending on configured policy).
1. Override path: drift detected + operator override enabled → allowed decision + audit event.
1. Busy guard: when run is active (lock/process), request is denied with deterministic reason_code.
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
    allowed_extensions: [".json", ".jsonl", ".parquet", ".txt", ".log", ".html", ".md", ".csv", ".cast", ".yaml", ".yml"]

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
  - `runs/<run_id>/control/resume_request.json`
  - `runs/<run_id>/control/resume_decision.json`
  - `runs/<run_id>/control/retry_request.json`
  - `runs/<run_id>/control/retry_decision.json`
  - `runs/<run_id>/inputs/plan_draft.yaml`
  - `logs/ui_audit.jsonl`
  - `state/run_registry.json` (run registry output)
  - `export_manifest.json` (export output)
- run manifest extension fields:
  - `manifest.extensions.operator_interface.plan_draft_sha256`
  - `manifest.extensions.operator_interface.plan_draft_path`

1. **ADR-0005 reason code registry**

   - If cancellation/resume/retry introduce new stage-level reason codes, ADR-0005 MUST be updated
     accordingly (per ADR-0007 requirements).

1. **Config reference**

   - Add `ui.*`, `auth.*` (UI scope), and `otel_gateway.*` keys and schema constraints.

1. **Terminal recording playback (asciinema)**

   - Decide whether `.cast` artifacts (for example `runner/actions/<action_id>/terminal.cast`) are
     rendered inline (player) or link-only in v0.2.

## References

## Changelog

| Date       | Change                                                                                                                                                                                                                                                                                                      |
| ---------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2026-01-22 | Added explicit workspace layout, introduced a minimal Operator API section, fixed artifact extension allowlist to include `.log` and YAML, expanded artifact allowlist to include `plan/` and `control/`, and made resume/retry request/decision lifecycle fully observable with durable request artifacts. |
| 2026-01-21 | Initial draft defining web Operator Interface, LAN reverse-proxy profile, local auth, audit logging, artifact serving constraints, and explicit cancellation/resume/retry state machines.                                                                                                                   |
