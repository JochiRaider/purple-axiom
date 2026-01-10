<!-- docs/research/R-01_otel_filelog_checkpoint_reliability.md -->

# R-01 Validation report: OTel `filelog` checkpoint reliability for rotated NDJSON

## 1) Scope

This report defines a repeatable validation harness and acceptance criteria for the OpenTelemetry
Collector `filelog` receiver when ingesting NDJSON sources that may rotate (example:
`osqueryd.results.log`).

The objective is to determine whether `filelog` persists offsets reliably across:

- file rotation (rename-and-create, copy-truncate, optional gzip)
- ungraceful process termination (SIGKILL / taskkill) and host reboot equivalents

The required semantics for Purple Axiom are at-least-once delivery with downstream dedupe:

- **Loss is unacceptable** for the validated matrix (must be detected as a failure)
- **Duplication is acceptable**, but MUST be measurable and SHOULD remain bounded

Non-goals:

- Proving durability of downstream exporters/queues (separate concern)
- Proving correctness for arbitrary third-party log writers that violate NDJSON (partial lines,
  non-UTF8)

## 2) Upstream behavior relied upon (documented)

The `filelog` receiver can persist per-file read offsets when configured with a storage extension
via the `storage` setting. The receiver stores (at least) the number of tracked files and, per file,
the file fingerprint (first bytes), the current byte offset, and selected file attributes.
Serialization depends on the selected storage backend.

The `file_storage` (filestorage) extension is a common implementation of a storage backend. If its
underlying database is detected as corrupt and automatic recovery is triggered, the extension can
start with a fresh database; this can cause duplication or loss of component state.

When ingesting compressed rotated logs, `filelog` supports `compression: gzip`. Compressed files are
expected to be appended to; recompressing and overwriting the full file content is not assumed to be
safe.

## 3) Reliability model (what can go wrong)

Even with storage-backed offsets, the following failure modes matter for rotated NDJSON:

1. **Rotation retention gap**

   - If rotated segments are deleted before the collector catches up after a crash/outage, loss can
     occur.

1. **File identity ambiguity**

   - `filelog` uses a fingerprint of initial bytes as part of file identity. Rotation modes that
     reuse initial bytes (example: copy-truncate) can increase the chance of confusing “new file” vs
     “old file,” resulting in replay duplication or gaps.

1. **Checkpoint reset / corruption recovery**

   - Any reset of the offset database (manual deletion, corruption recovery) is logically equivalent
     to checkpoint loss and can trigger replay and/or gaps.

1. **Writer buffering vs crash point**

   - If the log writer does not flush/fsync frequently, the “expected” source stream may not be
     durable at the crash boundary. The harness therefore controls writer flush semantics to
     separate collector behavior from writer behavior.

## 4) Validation harness design (reproducible)

### 4.1 Components

- **NDJSON writer**: emits one JSON object per line with a monotonic `seq` field and a stable
  `source_id`.
- **Rotator**: applies a chosen rotation strategy at deterministic boundaries.
- **Collector under test**: `otelcol-contrib` with `filelog` receiver configured with
  `storage: file_storage`.
- **Sink**: local, append-only output that captures the receiver-emitted stream for analysis
  (example: file exporter).
- **Crash injector**: terminates the collector ungracefully at deterministic times.
- **Analyzer**: computes loss/dup metrics from the sink output and compares to expected `seq`
  ranges.

### 4.2 Control points (recorded for determinism)

The harness MUST record all parameters in its run report (exact values, not “defaults”):

- OS + filesystem type (best effort)
- `poll_interval`, `max_concurrent_files`, `fingerprint_size`, `start_at`, `include`/`exclude` globs
- storage backend configuration (`file_storage.directory`)
- rotation mode + boundary (lines/bytes/time)
- retention window for rotated segments
- writer flush cadence (`flush_every_n_lines`, `fsync_every_n_lines`)
- crash injection timing (by seq number or elapsed time)

### 4.3 Deterministic expected stream

The writer MUST emit an expected manifest:

- `expected_seq_start`
- `expected_seq_end`
- `expected_total = expected_seq_end - expected_seq_start + 1`

## 5) Test matrix (minimum)

The harness MUST execute, at minimum, the matrix below.

| Axis          | Values (minimum)                                                                |
| ------------- | ------------------------------------------------------------------------------- |
| OS            | Windows, Linux                                                                  |
| Rotation mode | rename-and-create, copy-truncate                                                |
| Crash point   | no crash (control), crash during steady write, crash immediately after rotation |
| Restart       | immediate restart (same config), restart with new process id                    |

Optional (recommended) extensions to the matrix:

- gzip-rotated segments (rename-and-create + gzip)
- symlinked “current” file patterns

## 6) Metrics (computed per matrix cell)

All metrics are computed over the captured sink output.

- `observed_total`: total records observed
- `unique_total`: number of unique `seq` values observed
- `dup_total = observed_total - unique_total`
- `loss_total = expected_total - unique_total`
- `dup_pct = dup_total / expected_total * 100`
- `loss_pct = loss_total / expected_total * 100`
- `parse_error_total`: lines that failed NDJSON parse at the receiver
- `reorder_total`: count of observed inversions where `seq[i] < seq[i-1]` (diagnostic only)

## 7) Acceptance criteria (pass/fail/indeterminate)

### 7.1 Pass

A matrix cell MUST be marked PASS when all of the following hold:

- `loss_total == 0`
- `parse_error_total == 0` (for this harness, the writer emits valid JSON)

Duplication is allowed. The report MUST still record `dup_total` and `dup_pct`.

### 7.2 Fail

A matrix cell MUST be marked FAIL when any of the following hold:

- `loss_total > 0`
- the collector restarts with an empty offset database (checkpoint reset) without being explicitly
  commanded by the harness

### 7.3 Indeterminate

A matrix cell MUST be marked INDETERMINATE when the harness cannot establish a durable expected
stream at the crash boundary (example: writer configured with `fsync_every_n_lines = 0` and crash
occurs before OS flush). The harness MUST surface the cause and MUST NOT count indeterminate results
as passes.

## 8) Output artifacts (required)

Each harness run MUST produce:

- The collector config used (resolved, post-templating)
- The checkpoint directory snapshot from before and after restart
- Collector logs for the run window
- Source NDJSON files (including rotated segments)
- Sink output file(s)
- A machine-readable summary report (`json`, deterministic field ordering recommended)

## 9) Spec impact

The following spec changes are implied by this report:

- Make `filelog` storage-backed offsets a hard requirement for file-tailed sources.
- Treat any storage corruption recovery / state reset as checkpoint loss.
- Require rotation retention windows sufficient to cover worst-case restart/outage.
- Add an explicit CI/integration test case that executes the minimum matrix and asserts
  `loss_total == 0`.
