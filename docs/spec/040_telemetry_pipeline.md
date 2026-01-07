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

### osquery results (optional telemetry source)

osquery is supported as an optional telemetry source by ingesting **osqueryd scheduled query results** from the local filesystem logger:

- The canonical continuous monitoring output format MUST be **event format NDJSON** (one JSON object per line).
  - Differential rows use `action: "added" | "removed"` with a `columns` object.
  - Snapshot rows use `action: "snapshot"` with a `snapshot` array.
- Collection SHOULD be performed via the OTel Collector `filelog` receiver + JSON parsing operator.
- When enabled, collectors MUST label records such that the normalizer can set `metadata.source_type = "osquery"`.

Implementation details and conformance fixtures are specified in `042_osquery_integration.md`.

## 2) Windows Event Log collection (OTel Collector)

### Required invariant: collect raw, unrendered events

For Windows Event Log, prefer **raw/unrendered** collection. Rendering (human-readable message formatting) depends on provider manifests, OS language packs, and local system state; it is not a stable basis for identity or normalization.

Policy:
- For every `windowseventlog` receiver instance, set `raw: true`.
- Treat the raw XML as the canonical payload for later parsing and determinism.

### Manifest independence and publisher metadata failures

Windows Event Log “rendering” (human-readable message strings) depends on provider metadata and OS state and can fail when publisher metadata cannot be opened or message resources are unavailable. Purple Axiom MUST NOT treat rendered strings as required inputs for parsing, identity, or normalization.

Normative requirements:
- The normalizer MUST be able to parse required identity fields from raw event XML alone:
  - provider name (and GUID when present)
  - channel
  - EventID
  - EventRecordID
  - Computer
  - TimeCreated
- The pipeline MUST NOT require the presence of `RenderingInfo` or any formatted `Message` field.
- A collector MAY attempt to attach rendered message strings for operator convenience, but these strings:
  - MUST be treated as non-authoritative,
  - MUST be nullable,
  - MUST NOT participate in `metadata.event_id` generation or any stable hashing.

Failure classification (telemetry stage):
- If the receiver cannot open publisher metadata (example: “Failed to open publisher handle”), the event MUST still be captured if raw XML is available.
- If raw XML is not available for a Windows Event Log record, telemetry validation for that asset MUST fail closed (see §4).

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

Purple Axiom does not prescribe a single set of “correct” values for all labs. However, to support MVP deployments and to make “bounded queue behavior” mechanically testable, Purple Axiom DOES provide baseline starter values and a deterministic tuning methodology.

#### Baseline starter values (reference config; MVP)

The following values are RECOMMENDED as a starting point for a typical Windows endpoint agent collecting Windows Event Log + Sysmon and exporting off-host.

- Memory limiter:
  - `limit_mib: 512`
  - `spike_limit_mib: 128`
  - `check_interval: 1s`
- Batch processor:
  - `send_batch_size: 1024` (≈ “1000 events”)
  - `timeout: 10s`
- Exporter sending queue + retry (per exporter):
  - `sending_queue.enabled: true`
  - `sending_queue.queue_size: 4096`
  - `sending_queue.num_consumers: 2`
  - `retry_on_failure.enabled: true`
  - `retry_on_failure.initial_interval: 1s`
  - `retry_on_failure.max_interval: 30s`
  - `retry_on_failure.max_elapsed_time: 300s`

Notes:
- These values are intentionally conservative for operator UX (low surprise) and determinism (explicit backpressure behavior).
- If the endpoint is memory-constrained, operators SHOULD reduce `limit_mib` (example: 256) before increasing queue sizes.

#### Reference snippet (illustrative; not a full collector config)

```yaml
processors:
  memory_limiter:
    check_interval: 1s
    limit_mib: 512
    spike_limit_mib: 128
  batch:
    send_batch_size: 1024
    timeout: 10s

exporters:
  otlp:
    endpoint: "${env:OTLP_ENDPOINT}"
    sending_queue:
      enabled: true
      queue_size: 4096
      num_consumers: 2
    retry_on_failure:
      enabled: true
      initial_interval: 1s
      max_interval: 30s
      max_elapsed_time: 300s

service:
  pipelines:
    logs:
      processors: [memory_limiter, batch]
      exporters: [otlp]
```

#### Tuning methodology (operator playbook; deterministic)

When tuning, change one dimension at a time, in this order, and record the resulting config hash in run provenance:

1) **Set the memory ceiling first (fail-closed for runaway growth)**
   - Choose `limit_mib` such that the collector remains stable under sustained target EPS for 10 minutes.
   - Acceptance target: memory limiter activation events may occur under stress, but the process MUST NOT exhibit unbounded growth.

2) **Size the sending queue to a bounded “outage budget”**
   - Decide the maximum export stall you want to tolerate without drops (example: 30–120 seconds).
   - Choose `queue_size ≈ target_eps * tolerated_stall_seconds`.
   - Requirement: the queue MUST be bounded; when full, drops MUST be explicit and counted (no silent unbounded buffering).

3) **Tune batching to your EPS**
   - Pick `send_batch_size` so that a batch represents roughly 0.5–2.0 seconds of traffic at target EPS.
   - Keep `timeout` small enough to bound latency (10s is a reasonable starting point for MVP).

4) **Validate under backpressure and restarts**
   - Re-run the validation harness backpressure and restart tests (§4) after each tuning change.
   - Operators SHOULD treat any tuning change that increases drops at steady-state EPS as a regression unless justified by tighter resource budgets.

### Checkpointing and replay semantics (required)

At-least-once delivery implies duplicates and replay. This is expected and MUST be handled without breaking determinism goals.

#### Definitions

- **Collector checkpoint**: persisted receiver cursor/state used to resume ingestion after restart (example: Windows `EventRecordID`-based bookmarks).
- **Checkpoint loss**: missing, corrupt, or reset checkpoint state that causes the collector to re-emit previously exported events.

#### Required behavior

1) Durable checkpoint persistence (collector)
- For sources that support stable cursors (example: Windows Event Log), the collector configuration MUST enable durable state storage for checkpoints.
- The checkpoint storage directory MUST be explicitly configured to a stable location on durable disk (not an ephemeral temp directory).
- If the collector is deployed in a container, the checkpoint directory MUST be mounted to a persistent volume.

2) Loss and replay handling (pipeline)
- If a collector checkpoint is lost, the collector MAY replay historical events.
- The pipeline MUST accept replays and MUST rely on downstream dedupe keyed by `metadata.event_id` to prevent duplicate normalized events.
- The pipeline MUST record checkpoint-loss and replay indicators in run-scoped logs (see §4).

3) Restart policy (operator-visible)
- Restarting collectors and gateways MUST be treated as a normal operational action.
- A restart MUST NOT require manual cleanup of raw stores or normalized stores to recover correctness.

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
   - Simulate checkpoint loss (delete or move the collector checkpoint directory); restart the collector; confirm that:
     - events may replay into the raw store, and
     - downstream dedupe prevents duplicate normalized events (uniqueness by `metadata.event_id` is preserved).
3. **Backpressure**
   - Throttle the exporter/disk; confirm bounded queue behavior (drops are explicit and counted).
4. **Footprint**
   - Measure CPU/RAM at idle and at target EPS (events per second) for 10 minutes.
5. **Large payloads**
   - Emit a large script block and confirm max-length and sidecar policies behave as expected.

The results of these validations should be recorded as part of a run bundle under `logs/telemetry_validation.json`.

Minimum required fields for `logs/telemetry_validation.json`:
- `asset_id` (string)
- `collector_restart_test` (object)
  - `passed` (bool)
- `checkpoint_loss_test` (object)
  - `passed` (bool)
  - `checkpoint_loss_observed` (bool)
  - `replay_observed` (bool)
  - `dedupe_preserved_uniqueness` (bool)
 
 Recommended additional fields (operator UX and regression tracking):
 - `performance_controls` (object)
   - `memory_limiter` (object): `limit_mib`, `spike_limit_mib`, `check_interval`
   - `batch` (object): `send_batch_size`, `timeout`
   - `sending_queue` (object): `queue_size`, `num_consumers`
 - `observed` (object)
   - `memory_limiter_activated` (bool)
   - `exporter_queue_drops_observed` (bool)
   - `exporter_send_failures_observed` (bool)
   
## 5) Payload limits and binary handling (Windows Event Log)

### Definitions

- **Raw event XML**: the canonical event payload captured in raw/unrendered mode.
- **Binary event data**: event payload elements that represent binary blobs (for example `<Binary>` / BinaryEventData in the event schema) and large encoded payload fields embedded in XML. This commonly appears as hex strings (sometimes base64) in the XML view.

### Configuration surface

These limits are Purple Axiom staging policy (not upstream OTel config) and MUST be applied during raw Parquet writing and any optional sidecar extraction:

- `telemetry.payload_limits.max_event_xml_bytes` (default: 1_048_576)
- `telemetry.payload_limits.max_field_chars` (default: 262_144)
- `telemetry.payload_limits.max_binary_bytes` (default: 262_144)
- `telemetry.payload_limits.sidecar.enabled` (default: true)
- `telemetry.payload_limits.sidecar.dir` (default: `raw/evidence/blobs/wineventlog/`)

### Required behavior

1) Raw event XML promotion rules (analytics tier)
- The raw Windows Event Log Parquet dataset MUST include:
  - `event_xml` (string, MAY be truncated)
  - `event_xml_sha256` (string, SHA-256 of the full UTF-8 byte sequence of the pre-truncation XML payload)
  - `event_xml_truncated` (bool)
- If `event_xml` exceeds `max_event_xml_bytes`, the pipeline MUST:
  - set `event_xml_truncated=true`,
  - inline only the first `max_event_xml_bytes` bytes (UTF-8) as `event_xml`,
  - compute and store `event_xml_sha256` from the full pre-truncation payload,
  - optionally write the full payload to sidecar (see below).

2) Binary extraction rules (optional but mechanically testable)
- If the raw XML contains a binary-like field value (hex or base64) and its decoded length is <= `max_binary_bytes`, the pipeline MAY:
  - decode it to bytes,
  - write the decoded bytes to sidecar,
  - record `binary_ref` and `binary_sha256` (SHA-256 of decoded bytes) in the raw Parquet row.
- If the decoded length would exceed `max_binary_bytes`, the pipeline MUST:
  - NOT write decoded bytes to sidecar,
  - record a deterministic summary instead (at minimum `binary_present=true` and `binary_oversize=true`).

3) Sidecar blob store (when enabled)
- When `sidecar.enabled=true`, sidecar payloads MUST be keyed deterministically by `(run_id, metadata.event_id, field_path)`:
  - `runs/<run_id>/<sidecar.dir>/<metadata.event_id>/<field_path_hash>.<ext>`
- `field_path_hash` MUST be SHA-256 of the UTF-8 bytes of `field_path` and encoded as lowercase hex.
- Sidecar writes MUST respect redaction posture:
  - When `security.redaction.enabled=false`, sidecar payloads MUST follow the same withhold/quarantine rules as other evidence-tier artifacts (see `090_security_safety.md`).