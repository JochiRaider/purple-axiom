-- tests/fixtures/duckDB_pySig/gap_03_08/validate_gap_03.sql
-- GAP-03: Safe nested field access for OCSF projection
-- Run after schema.sql and data.sql
-- Each query is independent; results documented in comments

--------------------------------------------------------------------------------
-- TEST 1: Direct dot access on Tier 0 required fields
-- Expected: All 5 rows returned with non-NULL values
--------------------------------------------------------------------------------
SELECT 
  metadata.uid, 
  metadata.source_type,
  metadata.run_id
FROM ocsf_events;
-- Expected rows: 5
-- Expected: No NULL values in uid or source_type

--------------------------------------------------------------------------------
-- TEST 2: Nested STRUCT access with NULL parent (device)
-- Expected: NULL for record 3 where device is NULL
--------------------------------------------------------------------------------
SELECT 
  metadata.uid,
  device.hostname,
  device.ip
FROM ocsf_events
ORDER BY time;
-- Expected:
-- evt-001 | host-01 | 10.0.0.1
-- evt-002 | host-02 | 10.0.0.2
-- evt-003 | NULL    | NULL        <- device is NULL
-- evt-004 | dc-01   | 10.0.0.10
-- evt-005 | host-03 | NULL        <- device.ip is NULL, device is not

--------------------------------------------------------------------------------
-- TEST 3: Deep nested access with intermediate NULL
-- Expected: NULL for record 2 (user is NULL) and record 4 (process is NULL)
--------------------------------------------------------------------------------
SELECT 
  metadata.uid,
  actor."user".name AS user_name,
  actor.process.name AS process_name
FROM ocsf_events
ORDER BY time;
-- Expected:
-- evt-001 | alice  | powershell.exe
-- evt-002 | NULL   | cmd.exe         <- user is NULL
-- evt-003 | root   | bash
-- evt-004 | bob    | NULL            <- process is NULL
-- evt-005 | nobody | curl

--------------------------------------------------------------------------------
-- TEST 4: Existence check pattern (IS NOT NULL)
-- Filter events where actor.user.name exists
--------------------------------------------------------------------------------
SELECT metadata.uid, actor."user".name
FROM ocsf_events
WHERE actor."user".name IS NOT NULL
ORDER BY time;
-- Expected rows: 4 (evt-001, evt-003, evt-004, evt-005)
-- Excluded: evt-002 (user is NULL)

--------------------------------------------------------------------------------
-- TEST 5: Existence check for NULL parent struct
-- Filter events where device exists (is not NULL)
--------------------------------------------------------------------------------
SELECT metadata.uid, device.hostname
FROM ocsf_events
WHERE device IS NOT NULL
ORDER BY time;
-- Expected rows: 4 (evt-001, evt-002, evt-004, evt-005)
-- Excluded: evt-003 (device is NULL)

--------------------------------------------------------------------------------
-- TEST 6: LIST field membership - single value
-- Find events where device has IP 10.0.0.1
--------------------------------------------------------------------------------
SELECT metadata.uid, device.ips
FROM ocsf_events
WHERE list_contains(device.ips, '10.0.0.1');
-- Expected rows: 1 (evt-001)

--------------------------------------------------------------------------------
-- TEST 7: LIST field membership - any of multiple values
-- Find events where device has any of the specified IPs
--------------------------------------------------------------------------------
SELECT metadata.uid, device.ips
FROM ocsf_events
WHERE list_has_any(device.ips, ['10.0.0.2', '192.168.1.100']);
-- Expected rows: 2 (evt-001, evt-002)

--------------------------------------------------------------------------------
-- TEST 8: LIST field membership - all values present
-- Find events where device has ALL specified IPs
--------------------------------------------------------------------------------
SELECT metadata.uid, device.ips
FROM ocsf_events
WHERE list_has_all(device.ips, ['10.0.0.1', '192.168.1.100']);
-- Expected rows: 1 (evt-001)

--------------------------------------------------------------------------------
-- TEST 9: LIST field with pattern matching (requires unnest)
-- Find events where any IP starts with '10.'
--------------------------------------------------------------------------------
SELECT metadata.uid, device.ips
FROM ocsf_events
WHERE EXISTS (
  SELECT 1 FROM unnest(device.ips) AS t(ip)
  WHERE ip LIKE '10.%'
);
-- Expected rows: 4 (evt-001, evt-002, evt-004)
-- Note: evt-005 has empty ips[], evt-003 has NULL device

--------------------------------------------------------------------------------
-- TEST 10: Empty array vs NULL array distinction
-- Verify list functions handle empty arrays correctly
--------------------------------------------------------------------------------
SELECT 
  metadata.uid,
  metadata.labels,
  CASE 
    WHEN metadata.labels IS NULL THEN 'NULL'
    WHEN len(metadata.labels) = 0 THEN 'EMPTY'
    ELSE 'HAS_VALUES'
  END AS labels_state
FROM ocsf_events
ORDER BY time;
-- Expected:
-- evt-001 | ['test', 'process', 'atomic'] | HAS_VALUES
-- evt-002 | ['test', 'file']              | HAS_VALUES
-- evt-003 | NULL                          | NULL
-- evt-004 | ['auth', 'logon']             | HAS_VALUES
-- evt-005 | []                            | EMPTY

--------------------------------------------------------------------------------
-- TEST 11: LIST contains on empty array (edge case)
-- Should return false/no match, not error
--------------------------------------------------------------------------------
SELECT metadata.uid
FROM ocsf_events
WHERE list_contains(device.ips, '10.0.0.5');
-- Expected rows: 0

--------------------------------------------------------------------------------
-- TEST 12: LIST contains on NULL list (edge case)
-- Should return NULL/no match, not error
--------------------------------------------------------------------------------
SELECT metadata.uid
FROM ocsf_events
WHERE list_contains(metadata.labels, 'nonexistent');
-- Expected rows: 0
-- Note: evt-003 has NULL labels; NULL propagates through list_contains

--------------------------------------------------------------------------------
-- TEST 13: Combined nested + list access
-- Real-world pattern: find sysmon process events with specific label
--------------------------------------------------------------------------------
SELECT 
  metadata.uid,
  metadata.source_type,
  actor.process.name
FROM ocsf_events
WHERE metadata.source_type = 'sysmon'
  AND class_uid = 1007
  AND list_contains(metadata.labels, 'process');
-- Expected rows: 1 (evt-001)