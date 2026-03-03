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

Scope note (non-normative): This specification defines optional v0.2+ workspace and control-plane
behavior and is not required for the default build profile. See `000_charter.md` ("Target contract
surface and scope profile (normative)") for the authoritative baseline and seam scope map.

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
   - Baseline detection package library management for detection regression workflows (v0.2+
     optional): create from completed "known good" runs, list/search, view metadata, download, and
     delete baseline packages.

1. An **Operator API (HTTP)** used by the UI, designed so that:

   - the API can later support non-browser clients (CLI, automation)
   - future RBAC/MFA/enterprise auth can be added without breaking API shape

1. A **secure-by-default LAN access posture** for a single-container appliance deployment.

## Non-goals

This spec explicitly does NOT define:

- pixel-level UX/UI layouts, menus, visual design, or component libraries
- multi-tenant behavior, organization constructs, or enterprise IAM integration (reserved)
- full RBAC/ABAC authorization models (reserved)
- internet-facing hosting guidance (the default posture assumes "not internet-facing")
- multi-container orchestration (reserved for future version; v0.2 is single-container)

## Terms

- **Appliance**: A single Docker container packaging the orchestrator, Operator Interface web
  server, reverse proxy, and OTLP gateway.
- **Operator Interface (OI)**: The operator-facing web UI + the HTTP Operator API service backing it
  (called the "control-plane API" in this document). This is distinct from any reserved
  endpoint-management "control plane" functionality described elsewhere in the project.
- **Reverse proxy (RP)**: The in-container TLS terminator and request gatekeeper for the UI.
- **Verb**: A stable orchestrator entry point (for example: `build`, `simulate`, `replay`, `export`,
  `destroy`).
- **Run bundle**: `runs/<run_id>/` filesystem root containing all run artifacts, as defined
  elsewhere.
- **Workspace root**: The appliance’s durable data root (usually volume-mounted). It contains
  `runs/` (run bundles) and additional operator/control-plane directories such as `state/` (secrets
  and durable UI control-plane state), `logs/` (appliance logs), `plans/` (draft plans), `exports/`
  (derived export outputs), and `artifacts/` (CI/workspace artifacts and connector outputs).
- **Quarantine path**: The run-bundle subpath excluded from default disclosure. The quarantine
  directory is `runs/<run_id>/<security.redaction.unredacted_dir>` (default:
  `runs/<run_id>/unredacted/`). Validation and canonicalization rules for
  `security.redaction.unredacted_dir` are defined in `120_config_reference.md`; implementations MUST
  apply the canonicalization rules before containment checks.
- **Control artifacts**: Durable, run-local files under `runs/<run_id>/control/` used for
  operator-driven run control (cancel/resume/retry) without introducing a database for pipeline
  correctness.

## Workspace layout (v0.1+ normative)

The workspace root is a filesystem trust boundary for durable appliance data. Implementations
(v0.1+) MUST treat the following workspace-root children as **reserved** and MUST NOT place
unrelated content at these paths.

### Required directories (v0.2)

The appliance MUST ensure these directories exist (creating them if necessary) before serving the UI
or accepting Operator API calls:

Note (v0.1): the one-shot CLI MUST treat these directory names as reserved; only `runs/` is required
to exist in v0.1.

| Path (workspace-root relative) | Purpose                                                | Sensitivity | Default perms |
| ------------------------------ | ------------------------------------------------------ | ----------- | ------------- |
| `runs/`                        | Run bundles (pipeline outputs; authoritative)          | mixed       | 0750          |
| `state/`                       | Secrets + durable control-plane state                  | high        | 0700          |
| `logs/`                        | Appliance-local logs (including `ui_audit.jsonl`)      | medium      | 0750          |
| `artifacts/`                   | CI/workspace artifacts (findings/fixtures, connectors) | medium      | 0750          |
| `plans/`                       | Plan drafts + draft metadata (OI-authored)             | medium      | 0700          |
| `exports/`                     | Derived exports (archives + `export_manifest.json`)    | high        | 0700          |
| `cache/`                       | Cross-run caches and derived state (explicitly gated)  | medium      | 0700          |

Notes:

- `runs/` is the only directory whose contents are treated as authoritative pipeline outputs.
- `state/` MUST NOT be served by the artifact-serving endpoints.
- `exports/` MUST NOT be served by the run artifact endpoints; exports are accessed only via
  explicit export download endpoints and policy gates.
- `artifacts/` MUST NOT be served by the run artifact endpoints; it MAY be served only via explicit
  findings/CI endpoints with their own policy gates.
- `exports/datasets/` is a reserved export namespace for dataset releases (see
  `085_golden_datasets.md`) and MUST NOT be served by the run artifact endpoints.
- `cache/` MUST NOT be served by the artifact-serving endpoints.

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

Contract validation before publish (normative):

- Before appending an event to `logs/ui_audit.jsonl`, the implementation MUST validate the event
  instance against the `audit_event` contract as bound in the workspace contract registry.
- Before publishing `state/run_registry.json`, the implementation MUST validate the document
  instance against the `run_registry` contract as bound in the workspace contract registry.
- On validation failure, the implementation MUST fail closed and MUST NOT modify the final artifact.
  For contract-backed control-plane writes, implementations SHOULD emit the workspace contract
  validation report defined in `025_data_contracts.md` ("Workspace contract validation report
  artifact (normative)").

Implementation note (non-normative): The reference mechanism for these semantics is
`pa.publisher.workspace.v1` (see `025_data_contracts.md`).

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
- On each appliance start ("server session"), the appliance MUST generate a new leaf certificate
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
- The default posture MUST be: "no valid client cert, no ingestion."

**Certificate provisioning (v0.2):**

- v0.2 MAY use a locally generated OTLP CA (similar to UI CA) persisted under the workspace root’s
  protected state directory (v0.2 default: `<workspace_root>/state/`).
- v0.2 MUST document and implement a CLI workflow to issue client certificates for lab endpoints
  (exact lab distribution is environment-specific and is out of scope, but issuance MUST be
  deterministic and auditable).

## Control plane boundary and "thin UI" (v0.2 normative)

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
- The OI service streams run status by reading the run bundle artifacts and log files produced by
  the orchestrator process.

#### Concurrency control (v0.2 normative)

- The OI service MUST enforce `ui.limits.max_concurrent_runs` across concurrently active
  orchestrator verb processes started via the Operator API (where "active" means the child process
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
- The API MUST set `X-Request-ID` on every response.
  - The effective request id MUST be a UUID in canonical lowercase hyphenated form.
  - If an inbound `X-Request-ID` is present and is a valid UUID, the API MAY adopt it; otherwise it
    MUST generate a new UUID.
  - The effective request id MUST be used as `target.request_id` for all audit events emitted while
    servicing the request.
  - For endpoints that create or overwrite a durable control request artifact under
    `runs/<run_id>/control/` (cancel/resume/retry), the artifact `request_id` MUST equal
    `target.request_id` for the corresponding audit events.

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
- `reason_domain` (string): MUST equal `operator_interface`.
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

### Optional endpoints (v0.2+; normative when implemented)

#### Baseline detection packages (baseline library)

This optional endpoint set supports the Baseline Detection Package (BDP) library described in
`086_detection_baseline_library.md`. BDPs are stored outside `runs/` (under
`<workspace_root>/exports/baselines/...`) and are accessed via this resource rather than via run
artifact browsing.

Endpoints:

- `GET /api/baselines`
  - Returns a list of available baseline packages (summary view).
  - Sorting MUST be deterministic: `baseline_id` ascending, then `baseline_version` descending by
    SemVer precedence. If two versions compare equal by SemVer precedence, ties MUST be broken by
    `baseline_version` string ascending (UTF-8 byte order, no locale).
- `GET /api/baselines/{baseline_id}/{baseline_version}`
  - Returns the baseline package manifest (`baseline_detection_package_manifest`).
- `POST /api/baselines`
  - Creates a new baseline package from a completed run bundle.
  - Request body (minimum):
    - `baseline_id` (id_slug_v1)
    - `baseline_version` (semver_v1)
    - `source_run_id` (run_id UUID)
    - optional `description`, `tags`
  - Response: `201 Created` with the baseline package manifest.
  - Implementations MAY return `202 Accepted` if creation is long-running, but MUST make progress
    observable (for example, via audit events and/or server logs).
- `PATCH /api/baselines/{baseline_id}/{baseline_version}`
  - Updates mutable metadata fields (for example, `description`, `tags`, `blessing`) without
    changing immutable identity/content fields.
- `DELETE /api/baselines/{baseline_id}/{baseline_version}`
  - Deletes the baseline package.
- `GET /api/baselines/{baseline_id}/{baseline_version}/download`
  - Downloads the baseline package as a deterministic archive (zip/tar).
  - MUST enforce path traversal defenses equivalent to run artifact serving.

Error handling:

- MUST use the standard Operator API error envelope and domain (`operator_interface`).
- Recommended error codes:
  - `baseline_not_found` (404)
  - `baseline_already_exists` (409)
  - `baseline_create_in_progress` (409)
  - `baseline_source_run_not_found` (404)
  - `baseline_source_run_ineligible` (409)
  - `artifact_missing` (422)
  - `baseline_manifest_invalid` (422)
  - `baseline_package_unsafe` (422)
  - `artifact_representation_conflict` (409)

Audit logging:

- All baseline library mutations (create/update/delete/download) MUST emit `audit_event` rows into
  `logs/ui_audit.jsonl`.
- The `action` field SHOULD use distinct strings (for example, `baseline.create`, `baseline.update`,
  `baseline.delete`, `baseline.download`).

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

1. **Optional functional surfaces** (v0.2+; normative when implemented)

   If the Baseline Detection Package (BDP) library feature is enabled (see
   `086_detection_baseline_library.md`), the Operator Interface SHOULD provide:

   - Baseline library manager: list/search baseline packages, view details and manifest, create from
     completed runs, update metadata (tags/description/blessing), delete, and download baseline
     packages.
   - (Optional) A "Trial detections" affordance that launches a detection-only evaluation using one
     or more selected baseline packages as inputs. (Execution semantics are reserved; this bullet
     only defines the UX surface.)

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

The UI MUST NOT provide "create the first user" workflows in v0.2. Bootstrap is CLI-only.

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

This is distinct from run-local logs at `runs/<run_id>/logs/`.

### Minimum required audit event set (v0.2)

The audit stream MUST include events for:

- authentication: login success/failure, logout, session expiry
- account admin: create/reset/disable (CLI actions SHOULD also be audited to same log)
- run verbs: start (verb name; `action="runs.start"`), completion (`action="runs.complete"`; exit
  code + derived status), cancellation requests, resume/retry decisions
- quarantine access toggles
- artifact reads/downloads (path + allow/deny)
- export creation (include flags + allow/deny)

### UI audit event schema (v0.2)

Each JSONL row MUST validate against `docs/contracts/audit_event.schema.json` (contract_id:
`audit_event`).

Each JSONL row MUST contain at minimum:

- `ts`: RFC3339 timestamp (UTC, with `Z` suffix)
- `contract_version`: semver string; MUST be `0.2.0`
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
- `target`: object (action-dependent; MUST include `request_id`; MAY also include `run_id`, `path`,
  `verb`, `export_id`)
  - `request_id`: UUID correlation id for the triggering operator action.
    - For API-originated events, MUST be non-null and MUST match the `X-Request-ID` response header
      for the triggering request.
    - For CLI-originated events, MAY be null.
- `outcome`: enum `allowed | denied | succeeded | failed`
- `reason_domain` (string; required when `reason_code` is present; MUST equal `audit_event`)
- `reason_code`: string
  - required when `outcome ∈ {denied, failed}`
  - optional otherwise
  - UI-level reason codes are separate from ADR-0005 stage reason codes.
- `extensions`: object (optional; reserved for forward-compatible additions)

Audit rows MUST validate against the `audit_event` contract
(`docs/contracts/audit_event.schema.json`, `contract_version=0.2.0`).

Outcome semantics (normative):

- `allowed | denied` represent an authorization or policy gate decision taken before attempting the
  action.
- `succeeded | failed` represent completion of an action that was attempted.

Correlation semantics (v0.2 normative):

- Every audit row emitted as part of servicing an Operator API call MUST include the same
  `target.request_id` as the `X-Request-ID` response header for that call.
- If an operator action produces both:
  - a gate decision audit row (`outcome ∈ {allowed, denied}`), and
  - a completion audit row (`outcome ∈ {succeeded, failed}`), then both audit rows MUST share the
    same `target.request_id`.
- For `runs.start`, implementations MUST emit:
  - a gate decision row (`action="runs.start"`) with `outcome ∈ {allowed, denied}`, and
  - a completion row (`action="runs.complete"`) with `outcome ∈ {succeeded, failed}`.
  - Both rows MUST include the same `target.request_id`, and MUST also include `target.run_id` and
    `target.verb`.

Serialization and determinism (normative):

- Each audit row MUST be serialized as UTF-8 JSON followed by a single `\n`.
- Implementations MUST use a deterministic JSON serializer for audit rows.
  - RECOMMENDED: RFC 8785 JCS canonical JSON for the JSON object prior to appending `\n`.
- For a fixed sequence of API calls in a conformance fixture, the audit log MUST be identical aside
  from timestamps and generated IDs (where permitted). If deterministic IDs are required for CI
  fixtures, the implementation MUST support a "test mode" that seeds or injects deterministic IDs.

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

Request path validation (normative):

- Any user-supplied artifact-path string MUST be validated by parsing with `pa.run_relpath.v1`
  before allowlist evaluation.
- If `pa.run_relpath.v1` parsing fails, the API MUST deny the request with
  `reason_code="artifact_path_traversal"`.
- If parsing succeeds but the path is not allowed by policy/allowlist, the API MUST deny the request
  with `reason_code="artifact_path_denied"`.

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
  `security.redaction.unredacted_dir` when configured), `.staging/`, volatile diagnostics under
  `runs/<run_id>/logs/` (see ADR-0009), and binary evidence
- quarantine inclusion requires explicit `include_quarantine: true` plus confirmation prompt plus
  audit event
- volatile diagnostics inclusion (if implemented) requires explicit
  `include_volatile_diagnostics: true` plus confirmation prompt plus audit event
- binary evidence inclusion requires explicit `include_binary_evidence: true` plus confirmation
  prompt plus audit event

**Export output location (normative):**

- Export outputs MUST be written outside the run bundle, under the workspace root:
  - `<workspace_root>/exports/<run_id>/<export_id>/`
- Other export products MAY use other reserved export namespaces under `exports/` (for example
  dataset releases under `<workspace_root>/exports/datasets/<dataset_id>/<dataset_version>/`). These
  products MUST NOT be exposed via run artifact endpoints.
- `export_id` MUST be a UUID.
- Export filenames MUST NOT include timestamps.

**Crash-safe staging + publish (normative):**

- Export outputs under `exports/**` MUST be staged under `<workspace_root>/exports/.staging/**` and
  published by atomic directory rename into the final export location (see `045_storage_formats.md`,
  "Workspace-global export staging directories").
- Implementations MUST NOT use per-product staging directories under the final export namespaces
  (for example `exports/datasets/.staging/**`).
- Publication MUST conform to `pa.publisher.workspace.v1` semantics for this publish step (see
  `025_data_contracts.md`, "Producer tooling: workspace publisher semantics
  (pa.publisher.workspace.v1)"). Implementations SHOULD use the repository-provided reference
  workspace publisher implementation unless they demonstrate byte-for-byte conformance via the
  Contract Spine fixture suite for `pa.publisher.workspace.v1` (executed under `content.lint`).

**Contract validation + failure observability (normative):**

- `export_manifest.json` MUST validate against the `export_manifest` contract as bound in the
  workspace contract registry before publish.
- On contract validation failure, the final export output at `exports/<run_id>/<export_id>/` MUST
  NOT be created or modified, and the implementation MUST write the workspace contract validation
  report at `logs/contract_validation/exports/<run_id>/<export_id>.contract_validation.json`.

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
  (This hash basis corresponds to `yaml_semantic_sha256_v1` in `026_contract_spine.md`.)

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
  - `plan_sha256` (string; lowercase hex; computed as specified above for the current `plan.yaml`;
    corresponds to `yaml_semantic_sha256_v1(plan.yaml_bytes)` in `026_contract_spine.md`)
  - `created_at_utc` (RFC3339)
  - `updated_at_utc` (RFC3339)
- Writes to `plan.yaml` and `draft.json` MUST use write-to-temp + atomic rename.

### Run association and immutability

When a plan draft is assigned to a run (for example, when starting `simulate`):

- the exact draft YAML content MUST be copied into the run bundle at:
  - `runs/<run_id>/inputs/plan_draft.yaml`
- the plan semantic hash MUST be recorded in the run manifest under:
  - `manifest.extensions.operator_interface.plan_draft_sha256` (canonical digest string form:
    `sha256:<lowercase_hex>`; value MUST equal the string `sha256:` concatenated with
    `draft.json.plan_sha256`)
- the run manifest MUST also record the run-relative plan snapshot path under:
  - `manifest.extensions.operator_interface.plan_draft_path` (v0.2 value: `inputs/plan_draft.yaml`)
- the recorded hash MUST match the copied draft (computed as specified in
  [Draft plans](#draft-plans))

Contract surface note (normative): The field shapes, requiredness conditions, and cross-artifact
invariants for `manifest.extensions.operator_interface.*` are defined in `025_data_contracts.md`
under "Extensions and vendor fields". This document defines the operator workflow and semantic
intent.

Once copied into `runs/<run_id>/inputs/plan_draft.yaml`, the plan snapshot MUST be treated as
immutable for the lifetime of the run.

### Compiled plan artifacts

For v0.2 plan execution, compiled plan artifacts MUST be written under:

- `runs/<run_id>/plan/**`

Compiled artifacts MUST be treated as immutable once published. Runtime progress MUST be represented
via ground truth and per-action evidence, not by mutating the compiled plan graph.

## Run listing and monitoring (v0.2 normative)

### Run discovery mechanism

The Operator Interface MUST implement a run registry to define "what exists" (instead of relying
purely on nondeterministic directory enumeration).

- The registry is a control-plane artifact (global, not per-run).
- Default location: `<workspace_root>/state/run_registry.json` (single JSON object; written via
  write-to-temp + atomic rename; reserved in v0.1, written by v0.2+ control plane).
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
  - This value MUST equal `target.request_id` in the corresponding `runs.cancel_requested` audit
    rows.
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
  - This value MUST equal `target.request_id` in the corresponding `runs.resume_retry_requested`
    audit rows.
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

#### Purpose

- **What it represents**: A durable operator-issued cancellation request for a run, including
  escalation from `graceful` to `force`, with state derived from contracted control artifacts and
  run terminal status.
- **Scope**: `run` (per `run_id`)
- **Machine ID**: `oi-cancel-request-lifecycle`
- **Version**: `0.2.0`
- **Display name (non-authoritative)**: `oi.cancel.request_lifecycle` (legacy identifier; MUST NOT
  be used as the Machine ID)

#### Lifecycle authority references

- `115_operator_interface.md`:
  - `## Cancellation, resume, retry` (control artifacts + `cancel.json` contract)
  - `## Operator API (HTTP)` (API conventions + standard error envelope)
  - `## Audit logging (v0.2 normative)` (`audit_event` schema + `runs.cancel_*` audit actions)
- ADR-0007 (state machine template and requirements)
- ADR-0001 (identifier format: `id_slug_v1`)

If this state machine definition conflicts with other linked lifecycle authority, this state machine
is authoritative for Operator Interface cancellation behavior in v0.2.

#### Entities and identifiers

- **Machine instance key**: `run_id` (UUID; canonical lowercase hyphenated form)
- **Correlation identifiers**:
  - `runs/<run_id>/control/cancel.json.request_id` (UUID; durable cancellation correlation id)
  - `logs/ui_audit.jsonl[].target.request_id` (UUID; Operator API request correlation id)

#### Authoritative state representation

- **Source of truth**:
  - `runs/<run_id>/control/cancel.json` (presence + `mode`)
  - Run terminal status derived from `runs/<run_id>/manifest.json` (and
    `runs/<run_id>/logs/health.json` when present)
- **Derivation rule** (deterministic precedence):
  1. If `control/cancel.json` does not exist → `no_request`
  1. Else if the run is terminal → `terminal_observed`
  1. Else if `cancel.json.mode="graceful"` → `requested_graceful`
  1. Else if `cancel.json.mode="force"` → `requested_force`
  1. Else (invalid/unknown mode) → illegal state representation (fail closed; see Illegal
     transitions)
- **Persistence requirement**:
  - MUST persist: yes
  - MUST be persisted in: `runs/<run_id>/control/cancel.json` (write-to-temp + atomic rename)

#### Events / triggers

- `event.cancel_request_graceful`: A `POST /api/runs/{run_id}/cancel` request with
  `mode="graceful"`.
- `event.cancel_request_force`: A `POST /api/runs/{run_id}/cancel` request with `mode="force"`.
- `event.run_terminal_observed`: The run becomes terminal (verb exits, manifest written, run lock
  released).

Event requirements (normative):

- Events MUST be named with ASCII `lower_snake_case` after the `event.` prefix.
- For a given `run_id`, the Operator Interface control plane MUST process events serially.

#### States

State requirements (normative):

- States MUST be named as ASCII `lower_snake_case`.
- States MUST be stable within the declared version.
- Terminal states MUST be explicitly identified.

| State                | Kind           | Description                                   | Invariants                                          | Observable signals                                                |
| -------------------- | -------------- | --------------------------------------------- | --------------------------------------------------- | ----------------------------------------------------------------- |
| `no_request`         | `initial`      | No cancellation has been requested.           | `control/cancel.json` does not exist.               | Absence of `control/cancel.json`.                                 |
| `requested_graceful` | `intermediate` | Graceful cancellation requested and durable.  | `cancel.json.mode="graceful"` and run not terminal. | `control/cancel.json` validates; `mode="graceful"`.               |
| `requested_force`    | `intermediate` | Force cancellation requested and durable.     | `cancel.json.mode="force"` and run not terminal.    | `control/cancel.json` validates; `mode="force"`.                  |
| `terminal_observed`  | `terminal`     | Run is terminal and cancellation is recorded. | Run terminal AND `control/cancel.json` exists.      | Run terminal in `manifest.json` AND `control/cancel.json` exists. |

#### Transition rules

Transition requirements (normative):

- Each transition MUST specify: from_state, event, guard conditions, to_state, actions, failure
  mapping, and observable evidence.
- Guards MUST be explicit and deterministic.

| From state           | Event                           | Guard (deterministic)           | To state             | Actions (entry/exit)                                                                                                                                                                                                              | Outcome mapping                                                                                                                                                                                                                                                                                                | Observable transition evidence                                                                                                                |
| -------------------- | ------------------------------- | ------------------------------- | -------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| `no_request`         | `event.cancel_request_graceful` | run exists AND run not terminal | `requested_graceful` | Atomically write `control/cancel.json` (mode=graceful); emit write-ahead audit event `runs.cancel_requested`; MAY send OS signal best-effort                                                                                      | Success: Operator API accepts the request. Guard fail (run missing): deny (HTTP 404, `reason_code=run_not_found`), emit audit event with `outcome=denied`, do not write. Guard fail (run terminal): deny (HTTP 409, `reason_code=run_already_terminal`), emit audit event with `outcome=denied`, do not write. | `control/cancel.json` exists and validates; `logs/ui_audit.jsonl` contains `runs.cancel_requested`.                                           |
| `no_request`         | `event.cancel_request_force`    | run exists AND run not terminal | `requested_force`    | Atomically write `control/cancel.json` (mode=force); emit write-ahead audit event `runs.cancel_requested`; MAY send OS signal best-effort                                                                                         | Same as above (404/409 on guard failure).                                                                                                                                                                                                                                                                      | `control/cancel.json` exists and validates; `logs/ui_audit.jsonl` contains `runs.cancel_requested`.                                           |
| `requested_graceful` | `event.cancel_request_force`    | run not terminal                | `requested_force`    | Atomically update `control/cancel.json` (mode=force; set `escalated_at`/`escalated_by`; preserve `request_id`, `requested_at`, `requested_by`); emit audit event `runs.cancel_escalated`; MAY send stronger OS signal best-effort | Success: Operator API accepts escalation. Guard fail (run terminal): deny (HTTP 409, `reason_code=run_already_terminal`), emit denied audit event, do not modify.                                                                                                                                              | `control/cancel.json.mode="force"` and escalation fields present; `logs/ui_audit.jsonl` contains `runs.cancel_escalated`.                     |
| `requested_graceful` | `event.cancel_request_graceful` | run not terminal                | `requested_graceful` | Idempotent replay: MUST NOT change durable fields in `control/cancel.json`; MAY re-emit `runs.cancel_requested`; MAY re-signal OS best-effort                                                                                     | Success: Operator API accepts replay (no state change). Guard fail (run terminal): deny (HTTP 409, `reason_code=run_already_terminal`), emit denied audit event, no modification.                                                                                                                              | `control/cancel.json` unchanged (aside from explicitly non-deterministic fields, if any); audit row appended.                                 |
| `requested_force`    | `event.cancel_request_force`    | run not terminal                | `requested_force`    | Idempotent replay: MUST NOT change durable fields in `control/cancel.json`; MAY re-emit `runs.cancel_requested`; MAY re-signal OS best-effort                                                                                     | Success: Operator API accepts replay (no state change). Guard fail (run terminal): deny (HTTP 409, `reason_code=run_already_terminal`), emit denied audit event, no modification.                                                                                                                              | `control/cancel.json` unchanged; audit row appended.                                                                                          |
| `requested_force`    | `event.cancel_request_graceful` | always (downgrade attempt)      | `requested_force`    | MUST NOT modify `control/cancel.json`; MUST emit audit event `runs.cancel_requested` with `outcome=denied` and `reason_code=cancel_downgrade_forbidden`                                                                           | Operator API MUST deny (HTTP 409, `reason_code=cancel_downgrade_forbidden`). Response and evidence MUST be deterministic across repeated identical downgrade attempts.                                                                                                                                         | `control/cancel.json` unchanged; `logs/ui_audit.jsonl` contains denied `runs.cancel_requested` with `reason_code=cancel_downgrade_forbidden`. |
| `requested_graceful` | `event.run_terminal_observed`   | run becomes terminal            | `terminal_observed`  | No additional actions required (state derived from artifacts).                                                                                                                                                                    | Not an Operator API surface; used for derivation/observation.                                                                                                                                                                                                                                                  | `manifest.json` indicates terminal and `control/cancel.json` exists.                                                                          |
| `requested_force`    | `event.run_terminal_observed`   | run becomes terminal            | `terminal_observed`  | No additional actions required (state derived from artifacts).                                                                                                                                                                    | Not an Operator API surface; used for derivation/observation.                                                                                                                                                                                                                                                  | `manifest.json` indicates terminal and `control/cancel.json` exists.                                                                          |

#### Entry actions and exit actions

- **Entry actions**:

  - `requested_graceful`:
    - write `control/cancel.json` atomically (mode=graceful)
    - emit write-ahead `runs.cancel_requested` audit row
    - MAY send OS cancellation signal (best-effort; non-authoritative)
  - `requested_force`:
    - write/update `control/cancel.json` atomically (mode=force; include escalation fields when
      applicable)
    - emit `runs.cancel_requested` (initial force) and/or `runs.cancel_escalated` (escalation) audit
      row
    - MAY send OS cancellation signal (best-effort; non-authoritative)

- **Exit actions**: none.

Requirements (normative):

- Artifact writes that define or advance state MUST be atomic or fail closed.
- Entry/exit actions MUST be idempotent with respect to the authoritative state representation.

#### Illegal transitions

- **Policy**: `fail_closed`
- **Classification**: Operator API 4xx with the standard error envelope
  (`reason_domain=operator_interface`)
- **Observable evidence**: denied `audit_event` row in `logs/ui_audit.jsonl` plus an unchanged
  authoritative state representation (`control/cancel.json`)

Requirements (normative):

- Illegal transitions MUST NOT silently mutate state.
- Illegal transitions MUST be observable.

Any `(state, event)` combination not listed in Transition rules is illegal and MUST be handled per
this fail-closed policy.

This machine defines the following explicit illegal transition:

- Downgrade prevention: `requested_force` on `event.cancel_request_graceful` is illegal and MUST be
  rejected deterministically (see Transition rules).

In addition, the following are illegal:

- Any unrecognized `event.*` token.
- Any schema-invalid or unreadable `control/cancel.json` (fail closed; treat as illegal state
  representation and surface an operator-visible error).

#### Observability

- **Required artifacts**:
  - `runs/<run_id>/control/cancel.json`
  - `runs/<run_id>/manifest.json`
- **Structured logs**:
  - `logs/ui_audit.jsonl` (`audit_event` rows; includes `runs.cancel_requested` and
    `runs.cancel_escalated`)
- **Human-readable logs**:
  - `runs/<run_id>/logs/run.log` (diagnostic; not conformance-critical)

Requirements (normative):

- Observability signals MUST be deterministic for equivalent inputs.

#### Conformance tests

Minimum conformance suite (normative):

1. **Happy path**: `no_request` → graceful cancel request accepted → run terminates →
   `terminal_observed` derived.
1. **Escalation**: `requested_graceful` → force cancel request accepted → `requested_force` derived
   and escalation fields present.
1. **Illegal transition handling**: attempt a forbidden downgrade and verify deterministic rejection
   and evidence.
1. **Idempotency**: repeat a cancel request and verify no duplicated durable side effects and stable
   state derivation.
1. **Determinism**: run the same fixture twice and assert identical state-related artifacts
   (excluding explicitly non-deterministic fields permitted by contract).

Conformance test matrix (normative minimum):

| Test ID     | Initial state                                      | Event sequence                                                            | Expected final state | Required evidence                                                                                                         |
| ----------- | -------------------------------------------------- | ------------------------------------------------------------------------- | -------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `cancel-01` | `no_request`                                       | `event.cancel_request_graceful` then `event.run_terminal_observed`        | `terminal_observed`  | `control/cancel.json` (mode=graceful) exists; audit has `runs.cancel_requested` before termination.                       |
| `cancel-02` | `requested_graceful`                               | `event.cancel_request_force`                                              | `requested_force`    | `control/cancel.json.mode="force"` and escalation fields set; audit has `runs.cancel_escalated`.                          |
| `cancel-03` | `requested_graceful`                               | `event.cancel_request_graceful` (replay)                                  | `requested_graceful` | `control/cancel.json` unchanged; additional audit row emitted.                                                            |
| `cancel-04` | `requested_force`                                  | `event.cancel_request_graceful` (downgrade)                               | `requested_force`    | Operator API rejects with HTTP 409 `cancel_downgrade_forbidden`; denied audit row; `control/cancel.json` unchanged.       |
| `cancel-05` | `terminal_observed` or terminal run with no cancel | `event.cancel_request_force`                                              | unchanged            | Operator API rejects with HTTP 409 `run_already_terminal`; denied audit row; MUST NOT write/modify `control/cancel.json`. |
| `cancel-06` | n/a (missing run)                                  | `event.cancel_request_graceful`                                           | n/a                  | Operator API rejects with HTTP 404 `run_not_found`; denied audit row; MUST NOT write `control/cancel.json`.               |
| `cancel-07` | any                                                | derive from artifacts where run terminal AND `control/cancel.json` exists | `terminal_observed`  | State derivation precedence is deterministic (terminal overrides requested mode).                                         |

### Resume and retry (v0.2 normative)

#### Drift gate (authoritative signal)

The authoritative drift signal for resume/retry decisions is:

- Compare prior run manifest’s `manifest.lab.inventory_snapshot_sha256` to the current lab’s
  inventory snapshot hash.
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

#### Purpose

- **What it represents**: A durable operator-issued request to resume or retry a run plus a durable
  decision output, gated by deterministic drift evaluation.
- **Scope**: `run` (per `(run_id, decision_type)`)
- **Machine ID**: `oi-resume-retry-decision-lifecycle`
- **Version**: `0.2.0`
- **Display name (non-authoritative)**: `oi.resume_retry.decision_lifecycle` (legacy identifier;
  MUST NOT be used as the Machine ID)

#### Lifecycle authority references

- `115_operator_interface.md`:
  - `## Cancellation, resume, retry` (control artifacts + request file contract)
  - `### Resume and retry (v0.2 normative)` (drift gate definition)
  - `## Operator API (HTTP)` (API conventions + standard error envelope)
  - `## Audit logging (v0.2 normative)` (`audit_event` schema + `runs.resume_retry_requested` audit
    action)
- ADR-0007 (state machine template and requirements)
- ADR-0001 (identifier format: `id_slug_v1`)

If this state machine definition conflicts with other linked lifecycle authority, this state machine
is authoritative for Operator Interface resume/retry behavior in v0.2.

#### Entities and identifiers

- **Machine instance key**: `(run_id, decision_type)`
  - `run_id`: UUID (canonical lowercase hyphenated form)
  - `decision_type`: `resume | retry`
- **Correlation identifiers**:
  - `request_file.request_id` (UUID; latest request correlation id)
  - `logs/ui_audit.jsonl[].target.request_id` (UUID; Operator API request correlation id)

#### Authoritative state representation

Let `request_file` be:

- `control/resume_request.json` when `decision_type="resume"`
- `control/retry_request.json` when `decision_type="retry"`

Let `decision_file` be:

- `control/resume_decision.json` when `decision_type="resume"`

- `control/retry_decision.json` when `decision_type="retry"`

- **Source of truth**: `request_file` + `decision_file` (presence + validated JSON content)

- **Derivation rule** (deterministic precedence):

  1. If `request_file` does not exist → `idle`
  1. Else if `decision_file` does not exist → `evaluating_drift`
  1. Else if `decision_file` is present and validates:
     - `decision.decision="same_run"` → `decided_same_run`
     - `decision.decision="continuation_run"` → `decided_continuation_run`
     - `decision.decision="denied"` → `decided_denied`
  1. Else (schema invalid/unreadable) → illegal state representation (fail closed; see Illegal
     transitions)

- **Persistence requirement**:

  - MUST persist: yes
  - MUST be persisted in: `request_file` and `decision_file` (write-to-temp + atomic rename)

#### Events / triggers

- `event.resume_requested`: A `POST /api/runs/{run_id}/resume` request.
- `event.retry_requested`: A `POST /api/runs/{run_id}/retry` request.
- `event.drift_evaluated`: Drift evaluation completed for the latest request and a decision is ready
  to be written to `decision_file`.

Event requirements (normative):

- Events MUST be named with ASCII `lower_snake_case` after the `event.` prefix.
- For a given `(run_id, decision_type)`, the Operator Interface control plane MUST process events
  serially.

#### States

State requirements (normative):

- States MUST be named as ASCII `lower_snake_case`.
- States MUST be stable within the declared version.

Terminal states:

- None. Any decided state MAY transition back to `evaluating_drift` when a new request is accepted
  (latest request is authoritative).

| State                      | Kind           | Description                                      | Invariants                                                         | Observable signals                                         |
| -------------------------- | -------------- | ------------------------------------------------ | ------------------------------------------------------------------ | ---------------------------------------------------------- |
| `idle`                     | `initial`      | No request is present.                           | `request_file` does not exist.                                     | Absence of `request_file`.                                 |
| `evaluating_drift`         | `intermediate` | Request is present and drift is being evaluated. | `request_file` exists AND `decision_file` does not exist.          | Presence of `request_file` and absence of `decision_file`. |
| `decided_same_run`         | `intermediate` | Decision written: continue in same run.          | `decision_file` exists AND `decision.decision="same_run"`.         | `decision_file` validates; `decision="same_run"`.          |
| `decided_continuation_run` | `intermediate` | Decision written: create a new continuation run. | `decision_file` exists AND `decision.decision="continuation_run"`. | `decision_file` validates; `decision="continuation_run"`.  |
| `decided_denied`           | `intermediate` | Decision written: request denied by policy.      | `decision_file` exists AND `decision.decision="denied"`.           | `decision_file` validates; `decision="denied"`.            |

#### Transition rules

| From state                                                         | Event                                              | Guard (deterministic)                                            | To state                                                           | Actions (entry/exit)                                                                                                                                                                                                     | Outcome mapping                                                                                                                                                                                                                                                                              | Observable transition evidence                                                                               |
| ------------------------------------------------------------------ | -------------------------------------------------- | ---------------------------------------------------------------- | ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| `idle`                                                             | `event.resume_requested` / `event.retry_requested` | decision_type matches endpoint AND run exists AND run not active | `evaluating_drift`                                                 | Atomically write/overwrite `request_file`; MUST delete `decision_file` if it exists; compute drift deterministically; emit write-ahead audit event `runs.resume_retry_requested` (`outcome=allowed` or `outcome=denied`) | Success: Operator API accepts request and evaluation begins. Guard fail (run missing/invalid): deny (HTTP 404, `reason_code=run_not_found`), emit denied audit event, do not write. Guard fail (run active): deny (HTTP 409, `reason_code=run_busy`), emit denied audit event, do not write. | `request_file` exists; `decision_file` absent; audit row emitted.                                            |
| `evaluating_drift`                                                 | `event.resume_requested` / `event.retry_requested` | decision_type matches endpoint AND run exists AND run not active | `evaluating_drift`                                                 | Superseding request: atomically overwrite `request_file`; MUST ensure `decision_file` is absent; emit `runs.resume_retry_requested` audit row; restart evaluation against latest request (implementation-defined)        | Success: latest request becomes authoritative. Guard failures map as above.                                                                                                                                                                                                                  | `request_file` content changes (or remains identical for replay); `decision_file` absent; audit row emitted. |
| `decided_same_run` / `decided_continuation_run` / `decided_denied` | `event.resume_requested` / `event.retry_requested` | decision_type matches endpoint AND run exists AND run not active | `evaluating_drift`                                                 | New request: atomically overwrite `request_file`; MUST delete `decision_file` (invalidate prior decision); emit `runs.resume_retry_requested` audit row; begin new evaluation                                            | Success: latest request becomes authoritative and prior decision is invalidated deterministically. Guard failures map as above.                                                                                                                                                              | `decision_file` removed; `request_file` overwritten; audit row emitted.                                      |
| `evaluating_drift`                                                 | `event.drift_evaluated`                            | `request_file` exists AND `decision_file` absent                 | `decided_same_run` / `decided_continuation_run` / `decided_denied` | Atomically write `decision_file` for the current request                                                                                                                                                                 | Not an Operator API surface; decision output MUST be produced deterministically from drift gate inputs and configured policy.                                                                                                                                                                | `decision_file` exists and validates; derived decided state matches `decision.decision`.                     |

#### Entry actions and exit actions

- **Entry actions**:

  - `evaluating_drift`:
    - write/overwrite `request_file` atomically
    - MUST delete `decision_file` if it exists (invalidate stale decisions deterministically)
    - compute current inventory snapshot hash deterministically (same snapshot + hashing method as
      `lab_provider`)
    - emit write-ahead audit event `runs.resume_retry_requested` (`outcome=allowed` or
      `outcome=denied`)
  - `decided_*`:
    - write `decision_file` atomically

- **Exit actions**: none.

Requirements (normative):

- Artifact writes that define or advance state MUST be atomic or fail closed.
- Entry/exit actions MUST be idempotent with respect to the authoritative state representation.

#### Illegal transitions

- **Policy**: `fail_closed`
- **Classification**:
  - Operator API 4xx with the standard error envelope (`reason_domain=operator_interface`) when the
    illegal transition is requested via `POST /resume` or `POST /retry`.
  - Operator UI MUST fail closed (surface operator-visible error) when the illegal transition is
    observed via artifact inspection.
- **Observable evidence**:
  - denied `audit_event` row in `logs/ui_audit.jsonl` (for Operator API-originated illegals)
  - unchanged authoritative artifacts (`request_file` / `decision_file`) for API-originated illegals

Any `(state, event)` combination not listed in Transition rules is illegal and MUST fail closed.

This machine treats the following as illegal (non-exhaustive; all MUST fail closed):

- Any unrecognized `event.*` token.
- Any schema-invalid or unreadable `request_file` or `decision_file`.
- Any attempt to write a decision when `request_file` is absent (illegal state representation).

#### Observability

- **Required artifacts**:
  - `request_file` (`control/resume_request.json` or `control/retry_request.json`)
  - `decision_file` (`control/resume_decision.json` or `control/retry_decision.json`)
  - `runs/<run_id>/manifest.json` (source for prior `inventory_snapshot_sha256`)
- **Structured logs**:
  - `logs/ui_audit.jsonl` (`audit_event` rows; includes `runs.resume_retry_requested`)
- **Human-readable logs**:
  - `runs/<run_id>/logs/run.log` (diagnostic; not conformance-critical)

Requirements (normative):

- Observability signals MUST be deterministic for equivalent inputs.

#### Conformance tests

Minimum conformance suite (normative):

1. **Happy path**: request accepted → drift evaluated → decision written (one fixture each for
   `same_run`, `continuation_run`, and `denied` depending on policy configuration).
1. **Illegal transition handling**: attempt an invalid request sequence and verify fail-closed
   policy and evidence.
1. **Idempotency**: replay the same request and verify stable artifacts and decision outputs (aside
   from additional audit rows).
1. **Determinism**: repeat drift fixture twice → decision output identical aside from explicitly
   non-deterministic fields permitted by contract.

Conformance test matrix (normative minimum):

| Test ID | decision_type       | Initial state | Event sequence                                                         | Expected final state                           | Required evidence                                                                                             |
| ------- | ------------------- | ------------- | ---------------------------------------------------------------------- | ---------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| `rr-01` | `resume`            | `idle`        | `event.resume_requested` then `event.drift_evaluated` (no drift)       | `decided_same_run`                             | request and decision artifacts exist; audit row `runs.resume_retry_requested` emitted with `outcome=allowed`. |
| `rr-02` | `resume`            | `idle`        | `event.resume_requested` then `event.drift_evaluated` (drift detected) | `decided_continuation_run` or `decided_denied` | decision matches configured policy; decision artifact validates.                                              |
| `rr-03` | `retry`             | `idle`        | `event.retry_requested` then `event.drift_evaluated` (override path)   | decided (policy-specific)                      | audit row reflects override intent; decision artifact present.                                                |
| `rr-04` | `resume` or `retry` | `idle`        | request event while run active                                         | unchanged (`idle`)                             | Operator API rejects with HTTP 409 `run_busy`; denied audit row; MUST NOT write `request_file`.               |
| `rr-05` | `resume` or `retry` | `idle`        | request event for missing run                                          | unchanged (`idle`)                             | Operator API rejects with HTTP 404 `run_not_found`; denied audit row; MUST NOT write `request_file`.          |
| `rr-06` | `resume` or `retry` | `decided_*`   | new request event                                                      | `evaluating_drift`                             | prior `decision_file` removed; new `request_file` written; evaluation restarts deterministically.             |
| `rr-07` | `resume` or `retry` | any           | corrupt/unreadable `decision_file` observed                            | n/a (fail closed)                              | UI/API surfaces operator-visible error; no guessed state; authoritative artifacts unchanged.                  |

## Configuration surface (v0.2)

This spec introduces top-level Operator Interface configuration keys.

Source of truth (normative):

- These keys live in `inputs/range.yaml` (contract: `range_config`).
- `120_config_reference.md` is authoritative for defaults / types / validation rules; this document
  defines Operator Interface semantics and behavioral requirements.

```yaml
ui:
  enabled: true                # opt-in; default: false

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
  enabled: true                # opt-in; default: false
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

1. **Contracts + bindings (registry + validation hooks)**

   The implementation MUST register contract-backed artifacts for the operator interface
   control-plane and supporting workspace state, with **concrete contract IDs** and schema file
   paths.

   **Run-bundle artifacts (run-relative bindings).**

   Notes (normative):

   - `bindings[].artifact_glob` values in `contract_registry.json` are run-relative (do not include
     the `runs/<run_id>/` prefix).
   - Control-plane artifacts under `control/` MUST be bound with `stage_owner="orchestrator"`.
   - Validation modes MUST use the existing registry vocabulary: `json_document`, `yaml_document`,
     `jsonl_lines`, `parquet_dataset_v1`.

   | Run artifact (location)                      | Registry `artifact_glob`       | `contract_id`             | `schema_path`                                        | `stage_owner`  | `validation_mode` |
   | -------------------------------------------- | ------------------------------ | ------------------------- | ---------------------------------------------------- | -------------- | ----------------- |
   | `runs/<run_id>/control/cancel.json`          | `control/cancel.json`          | `control_cancel_request`  | `docs/contracts/control_cancel_request.schema.json`  | `orchestrator` | `json_document`   |
   | `runs/<run_id>/control/resume_request.json`  | `control/resume_request.json`  | `control_resume_request`  | `docs/contracts/control_resume_request.schema.json`  | `orchestrator` | `json_document`   |
   | `runs/<run_id>/control/resume_decision.json` | `control/resume_decision.json` | `control_resume_decision` | `docs/contracts/control_resume_decision.schema.json` | `orchestrator` | `json_document`   |
   | `runs/<run_id>/control/retry_request.json`   | `control/retry_request.json`   | `control_retry_request`   | `docs/contracts/control_retry_request.schema.json`   | `orchestrator` | `json_document`   |
   | `runs/<run_id>/control/retry_decision.json`  | `control/retry_decision.json`  | `control_retry_decision`  | `docs/contracts/control_retry_decision.schema.json`  | `orchestrator` | `json_document`   |
   | `runs/<run_id>/inputs/plan_draft.yaml`       | `inputs/plan_draft.yaml`       | `plan_draft`              | `docs/contracts/plan_draft.schema.json`              | `orchestrator` | `yaml_document`   |

   **Manifest extension fields (schema evolution).**

   - The existing `manifest` contract (`docs/contracts/manifest.schema.json`) validates the
     structural shape of `manifest.extensions.operator_interface`, including:
     - `manifest.extensions.operator_interface.plan_draft_sha256`
     - `manifest.extensions.operator_interface.plan_draft_path`
   - Schema source of truth (normative): the field definitions, requiredness conditions, and hash
     basis are defined in `spec/025_data_contracts.md` under
     "Operator Interface namespace: plan draft provenance (v0.2+)". This document is a consumer and
     MUST NOT restate those constraints in a divergent way.
     
   **Workspace-global artifacts (workspace-root validation required).**

   The following are workspace-root artifacts (not run-relative). They MUST NOT be silently made
   run-relative without updating the rest of the operator model:

   | Artifact                    | Workspace location (normative)                                    | `contract_id`                          | `schema_path`                                                     | `validation_mode` |
   | --------------------------- | ----------------------------------------------------------------- | -------------------------------------- | ----------------------------------------------------------------- | ----------------- |
   | Global UI audit log         | `logs/ui_audit.jsonl`                                             | `audit_event` (reuse)                  | `docs/contracts/audit_event.schema.json`                          | `jsonl_lines`     |
   | Run registry                | `state/run_registry.json`                                         | `run_registry`                         | `docs/contracts/run_registry.schema.json`                         | `json_document`   |
   | Export manifest             | `exports/<run_id>/<export_id>/export_manifest.json`               | `export_manifest`                      | `docs/contracts/export_manifest.schema.json`                      | `json_document`   |
   | Workspace validation report | `logs/contract_validation/<target_path>.contract_validation.json` | `workspace_contract_validation_report` | `docs/contracts/workspace_contract_validation_report.schema.json` | `json_document`   |

   **Test hooks (CI).**

   - CI MUST include fixtures that validate the run-bundle artifacts above using the normal
     publish-gate `ContractValidator`.
   - CI MUST validate the workspace-global artifacts above using the workspace contract registry
     (`docs/contracts/workspace_contract_registry.json`) and the Contract Spine conformance fixtures
     for `pa.publisher.workspace.v1` (executed under the `content.lint` gate).

1. **Schema source of truth (payload definitions are already in this spec)**

   The schema files introduced above MUST reflect the normative payload requirements already
   specified in this document:

   - `cancel.json`: `### Control artifacts (normative)` → `#### cancel.json (v0.2 contract)`
   - `resume_request.json` / `resume_decision.json`: corresponding subsections under
     `### Control artifacts (normative)`
   - `retry_request.json` / `retry_decision.json`: corresponding subsections under
     `### Control artifacts (normative)`
   - plan draft snapshot + hashing:
     - Operator workflow + semantics: `## Plan building (v0.2 normative)` → `### Draft plans` and
       `### Run association and immutability`
     - Manifest extension field contract (names, invariants, requiredness, hash basis):
       `spec/025_data_contracts.md` → "Operator Interface namespace: plan draft provenance (v0.2+)"
   - export manifest: `### Export behavior (normative)` → **Export manifest (normative)**

1. **Workspace-global artifacts (workspace-root validation; resolved)**

`logs/ui_audit.jsonl`, `state/run_registry.json`, `artifacts/**`, and `exports/**` outputs are
workspace-root artifacts (not run-relative).

Resolution (normative):

- Contract-backed workspace artifacts MUST be validated against the workspace contract registry
  (`docs/contracts/workspace_contract_registry.json`, `registry_kind="workspace"`).
- Publication MUST follow `pa.publisher.workspace.v1` semantics, including:
  - directory staging + rename for `exports/**` via `exports/.staging/**`,
  - atomic replace for single-file artifacts under `state/**` and `artifacts/**`, and
  - append + `fsync()` for `logs/ui_audit.jsonl`.
- On contract validation failure, the implementation MUST fail closed and MUST emit the workspace
  contract validation report defined in `025_data_contracts.md`.

Constraint (normative):

- Run-bundle publish-gate behavior (`pa.publisher.v1`) remains unchanged.

1. **Asciinema playback (required; locally bundled assets + fallback)**

   - Implement the required inline asciinema playback viewer for `.cast` artifacts (for example
     `runner/actions/<action_id>/terminal.cast`) using locally bundled player assets (no remote
     fetches), with a plain-text fallback view.
   - The chosen player library/assets MUST be version-pinned and recorded per
     `SUPPORTED_VERSIONS.md` (add a UI pin category if needed).

1. **Audit logging contract (validation scope is workspace-global)**

   - The global UI audit log at `logs/ui_audit.jsonl` MUST reuse the existing `audit_event` contract
     (`docs/contracts/audit_event.schema.json`).
   - CI validation MUST treat `logs/ui_audit.jsonl` as a workspace-global log (not per-run), even
     though run bundles may also emit run-local audit trails (for example `control/audit.jsonl`).

1. **ADR-0005 reason code registry**

   - If cancellation/resume/retry introduce new stage-level reason codes, ADR-0005 MUST be updated
     accordingly (per ADR-0007 requirements).

1. **Range config schema constraints**

   - Ensure `docs/contracts/range_config.schema.json` accepts and validates the top-level `ui`,
     `auth`, and `otel_gateway` keys documented in `120_config_reference.md` (unknown-key rejection
     makes this fail closed until the schema is updated).

## References

## Changelog

| Date       | Change                                                                                                                                                                                                                                                                                                      |
| ---------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2026-01-24 | Exclude volatile diagnostics under `runs/<run_id>/logs/` from default exports; align with ADR-0009.                                                                                                                                                                                                         |
| 2026-01-22 | Added explicit workspace layout, introduced a minimal Operator API section, fixed artifact extension allowlist to include `.log` and YAML, expanded artifact allowlist to include `plan/` and `control/`, and made resume/retry request/decision lifecycle fully observable with durable request artifacts. |
| 2026-01-21 | Initial draft defining web Operator Interface, LAN reverse-proxy profile, local auth, audit logging, artifact serving constraints, and explicit cancellation/resume/retry state machines.                                                                                                                   |
