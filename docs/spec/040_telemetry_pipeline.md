<!-- docs/spec/040_telemetry_pipeline.md -->
# Telemetry pipeline

Purple Axiom treats telemetry as an input dataset that must be (a) reproducible and (b) analyzable without vendor lock-in. The telemetry stage is therefore optimized for:

- **High-fidelity capture** (preserve the original event semantics).
- **Determinism** (stable fields across restarts, replays, and locale differences).
- **Resilience** (at-least-once delivery is expected; downstream dedupe is required).
- **Low operational surprise** (bounded resource usage; explicit backpressure behavior).

## 1) Canonical topology

**Endpoint agents (preferred):**
- Run an OpenTelemetry Collector (or a distro such as Splunk OTel Collector / Bindplane Agent) on each endpoint.
- Export logs to a local-first sink (file/OTLP) plus an optional central aggregator.

**Collector tiers:**
- **Agent**: reads OS/native sources (Windows Event Log, syslog, file logs), adds minimal provenance, ships upstream.
- **Gateway (optional)**: applies buffering, batching, auth, and fan-out to storage backends.

Purple Axiom assumes the agent tier exists even if a gateway is later added.

## 2) Windows Event Log collection (OTel Collector)

### Required invariant: collect raw, unrendered events

For Windows Event Log, prefer **raw/unrendered** collection. Rendering (human-readable message formatting) depends on provider manifests, OS language packs, and local system state; it is not a stable basis for identity or normalization.

Policy:
- For every `windowseventlog` receiver instance, set `raw: true`.
- Treat the raw XML as the canonical payload for later parsing and determinism.

### Receiver instance model

Create one receiver instance per channel (or per channel group), using stable names:

- `windowseventlog/application`
- `windowseventlog/security`
- `windowseventlog/system`
- `windowseventlog/sysmon`
- `windowseventlog/forwarded`

This mirrors how downstream storage partitions are organized (by `channel`).

### Output shape and assumptions

The `windowseventlog` receiver emits **OTel LogRecords**. The LogRecord body (`body`) may be either:

- a string (commonly raw XML when `raw: true`), or
- a structured map (when not in raw mode, or when the receiver populates parsed fields).

Purple Axiom treats the LogRecord as the transport envelope and does not assume a single fixed body shape. Normalization converts the LogRecord plus raw payload into OCSF.

### Large and binary event data

Windows Event Data may contain:
- large strings (example: PowerShell script blocks),
- nested XML,
- binary blobs (often represented as hex/base64 in XML).

Policy:
- Preserve raw payloads in the raw store, but enforce **size hygiene** in the pipeline:
  - define a configurable max payload length for promotion into long-term stores,
  - store a hash (SHA-256) for oversized fields to support dedupe and integrity,
  - optionally store large payloads in a sidecar blob store keyed by `(run_id, event_id, field_path)`.

### Performance and footprint controls (agent)

The agent configuration SHOULD include:
- a memory limiter (hard cap),
- a batch processor (reduce export overhead),
- a bounded sending queue with retry (avoid drops on transient backpressure),
- internal telemetry enabled (Prometheus endpoint for the agent itself).

Purple Axiom does not prescribe exact values. Instead, the repo includes a validation harness (see below) that measures events/sec, CPU, and memory for your lab scale.

## 3) Injecting `run_id` / `scenario_id`

There are two supported strategies.

### A) Processing-time enrichment (recommended)

Collectors run continuously; the Purple Axiom pipeline assigns `run_id` / `scenario_id` during processing/normalization using:
- manifest start/end bounds,
- scenario ground-truth timestamps,
- asset identity.

This avoids per-run restarts/reconfiguration of collectors and is stable under at-least-once delivery.

### B) Collection-time enrichment (optional)

If you are comfortable restarting or hot-reloading collector configs per run, you MAY inject `run_id` / `scenario_id` at the collector via an attributes/resource processor, sourcing values from environment variables.

Constraints:
- Environment substitution is applied to scalar values at config parse time; dynamic per-event enrichment without external correlation is not assumed.
- Collection-time enrichment is best for small lab runs where collector restart is acceptable.

## 4) Practical validation harness (required)

Before the telemetry stage is treated as "green", validate each Windows endpoint with a repeatable checklist:

1. **Correctness**
   - Generate known events (Security 4624/4625, Sysmon 1/3, PowerShell 4104, etc.).
   - Verify they arrive in the raw store with `raw: true` payloads intact.
2. **Determinism**
   - Restart the collector mid-stream; confirm no schema changes and that downstream `event_id` generation remains stable.
3. **Backpressure**
   - Throttle the exporter/disk; confirm bounded queue behavior (drops are explicit and counted).
4. **Footprint**
   - Measure CPU/RAM at idle and at target EPS (events per second) for 10 minutes.
5. **Large payloads**
   - Emit a large script block and confirm max-length and sidecar policies behave as expected.

The results of these validations should be recorded as part of a run bundle under `logs/telemetry_validation.json`.