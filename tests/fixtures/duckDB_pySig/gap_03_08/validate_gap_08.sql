-- tests/fixtures/duckDB_pySig/gap_03_08/validate_gap_08.sql
-- GAP-08: Timestamp typing and timezone normalization for time-part modifiers
-- Run after schema.sql and data.sql
-- Each query is independent; results documented in comments

--------------------------------------------------------------------------------
-- TEST 1: Verify raw epoch values
-- Confirm time column contains expected millisecond epoch values
--------------------------------------------------------------------------------
SELECT metadata.uid, time, time_dt
FROM ocsf_events
ORDER BY time;
-- Expected:
-- evt-001 | 1736344200000 | 2026-01-08T14:30:00Z
-- evt-002 | 1736347800000 | 2026-01-08T15:30:00Z
-- evt-003 | 1736351400000 | 2026-01-08T16:30:00Z
-- evt-004 | 1736355000000 | 2026-01-08T17:30:00Z
-- evt-005 | 1736358600000 | 2026-01-08T18:30:00Z

--------------------------------------------------------------------------------
-- TEST 2: Convert epoch ms to TIMESTAMP using epoch_ms()
-- This is the canonical conversion function for Purple Axiom
--------------------------------------------------------------------------------
SELECT 
  metadata.uid,
  time,
  epoch_ms(time) AS ts_from_epoch
FROM ocsf_events
ORDER BY time;
-- Expected: TIMESTAMP values matching time_dt

--------------------------------------------------------------------------------
-- TEST 3: Extract hour from epoch timestamp
-- Pattern for Sigma time|hour modifier
--------------------------------------------------------------------------------
SELECT 
  metadata.uid,
  date_part('hour', epoch_ms(time)) AS hour
FROM ocsf_events
ORDER BY time;
-- Expected hours: 14, 15, 16, 17, 18

--------------------------------------------------------------------------------
-- TEST 4: Extract all common date parts
-- Comprehensive time-part extraction
--------------------------------------------------------------------------------
SELECT 
  metadata.uid,
  date_part('year', epoch_ms(time)) AS year,
  date_part('month', epoch_ms(time)) AS month,
  date_part('day', epoch_ms(time)) AS day,
  date_part('hour', epoch_ms(time)) AS hour,
  date_part('minute', epoch_ms(time)) AS minute,
  date_part('second', epoch_ms(time)) AS second
FROM ocsf_events
ORDER BY time;
-- Expected for all: year=2026, month=1, day=8, minute=30, second=0
-- Hours vary: 14, 15, 16, 17, 18

--------------------------------------------------------------------------------
-- TEST 5: Week and day-of-week extraction
-- Additional time parts for complex rules
--------------------------------------------------------------------------------
SELECT 
  metadata.uid,
  date_part('week', epoch_ms(time)) AS week,
  date_part('dayofweek', epoch_ms(time)) AS dow,  -- 0=Sunday in DuckDB
  date_part('dayofyear', epoch_ms(time)) AS doy
FROM ocsf_events
ORDER BY time;
-- Expected: week=2, dow=3 (Wednesday), doy=8

--------------------------------------------------------------------------------
-- TEST 6: Filter by hour (Sigma: time|hour: 14)
--------------------------------------------------------------------------------
SELECT metadata.uid, time_dt
FROM ocsf_events
WHERE date_part('hour', epoch_ms(time)) = 14;
-- Expected rows: 1 (evt-001)

--------------------------------------------------------------------------------
-- TEST 7: Filter by hour range (business hours: 9-17)
--------------------------------------------------------------------------------
SELECT metadata.uid, time_dt
FROM ocsf_events
WHERE date_part('hour', epoch_ms(time)) >= 14
  AND date_part('hour', epoch_ms(time)) <= 17;
-- Expected rows: 4 (evt-001 through evt-004)

--------------------------------------------------------------------------------
-- TEST 8: Filter by day of week (weekday only)
--------------------------------------------------------------------------------
SELECT metadata.uid, time_dt
FROM ocsf_events
WHERE date_part('dayofweek', epoch_ms(time)) BETWEEN 1 AND 5;
-- Expected: All 5 rows (2026-01-08 is a Thursday, dow=4)

--------------------------------------------------------------------------------
-- TEST 9: Verify time_dt string parses to same timestamp
-- Contract: time_dt MUST be deterministic rendering of time
--------------------------------------------------------------------------------
SELECT 
  metadata.uid,
  epoch_ms(time) AS from_epoch,
  CAST(time_dt AS TIMESTAMP) AS from_string,
  epoch_ms(time) = CAST(time_dt AS TIMESTAMP) AS timestamps_match
FROM ocsf_events
ORDER BY time;
-- Expected: timestamps_match = true for ALL rows

--------------------------------------------------------------------------------
-- TEST 10: Time range query using epoch directly
-- Pattern for time-bounded detection windows
--------------------------------------------------------------------------------
SELECT metadata.uid, time_dt
FROM ocsf_events
WHERE time >= 1736347800000  -- >= 15:30
  AND time < 1736355000000;  -- < 17:30
-- Expected rows: 2 (evt-002, evt-003)

--------------------------------------------------------------------------------
-- TEST 11: Time range using TIMESTAMP comparison
-- Alternative pattern using human-readable bounds
--------------------------------------------------------------------------------
SELECT metadata.uid, time_dt
FROM ocsf_events
WHERE epoch_ms(time) >= TIMESTAMP '2026-01-08 15:30:00'
  AND epoch_ms(time) < TIMESTAMP '2026-01-08 17:30:00';
-- Expected rows: 2 (evt-002, evt-003)

--------------------------------------------------------------------------------
-- TEST 12: Extract milliseconds (sub-second precision)
-- Verify no precision loss in epoch storage
--------------------------------------------------------------------------------
SELECT 
  metadata.uid,
  time,
  time % 1000 AS milliseconds,
  date_part('millisecond', epoch_ms(time)) AS ms_from_timestamp
FROM ocsf_events
ORDER BY time;
-- Expected: milliseconds = 0 for all test data (on-the-minute times)

--------------------------------------------------------------------------------
-- TEST 13: Timestamp arithmetic (detection window lookback)
-- Pattern: "events within 1 hour of reference event"
--------------------------------------------------------------------------------
WITH reference AS (
  SELECT time AS ref_time FROM ocsf_events WHERE metadata.uid = 'evt-003'
)
SELECT e.metadata.uid, e.time_dt
FROM ocsf_events e, reference r
WHERE e.time >= r.ref_time - 3600000  -- 1 hour before
  AND e.time <= r.ref_time + 3600000; -- 1 hour after
-- Expected rows: 3 (evt-002, evt-003, evt-004)
-- evt-003 is at 16:30, window is 15:30-17:30

--------------------------------------------------------------------------------
-- TEST 14: Combined time + field filter
-- Real-world pattern: specific event type in time window
--------------------------------------------------------------------------------
SELECT metadata.uid, metadata.source_type, time_dt
FROM ocsf_events
WHERE date_part('hour', epoch_ms(time)) >= 15
  AND date_part('hour', epoch_ms(time)) <= 17
  AND metadata.source_type = 'sysmon';
-- Expected rows: 1 (evt-002)

--------------------------------------------------------------------------------
-- TEST 15: Verify UTC assumption (no timezone offset applied)
-- DuckDB TIMESTAMP is timezone-naive; should match UTC string exactly
--------------------------------------------------------------------------------
SELECT 
  metadata.uid,
  time_dt,
  strftime(epoch_ms(time), '%Y-%m-%dT%H:%M:%SZ') AS formatted_utc,
  time_dt = strftime(epoch_ms(time), '%Y-%m-%dT%H:%M:%SZ') AS format_matches
FROM ocsf_events
ORDER BY time;
-- Expected: format_matches = true for ALL rows
-- This confirms no timezone conversion is happening