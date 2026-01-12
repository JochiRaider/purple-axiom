-- tests/fixtures/duckDB_pySig/gap_03_08/data.sql
-- Sample data covering edge cases for GAP-03 and GAP-08 validation
-- Run after schema.sql

INSERT INTO ocsf_events VALUES
  -- Record 1: Full population (all fields present)
  (
    1736344200000,                          -- 2026-01-08T14:30:00Z (ms epoch)
    '2026-01-08T14:30:00Z',
    1007,                                   -- Process Activity
    1,                                      -- System Activity category
    100701,                                 -- type_uid = class_uid * 100 + activity_id(1)
    2,                                      -- Informational severity
    {
      uid: 'evt-001',
      event_id: 'evt-001',
      run_id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
      scenario_id: 'scenario.atomic.t1059',
      collector_version: 'collector@0.1.0',
      normalizer_version: 'normalizer@0.1.0',
      source_type: 'sysmon',
      source_event_id: 'record:12345',
      labels: ['test', 'process', 'atomic']
    },
    {
      hostname: 'host-01',
      uid: 'host-01-guid',
      ip: '10.0.0.1',
      ips: ['10.0.0.1', '192.168.1.100']
    },
    {
      "user": { name: 'alice', uid: 'S-1-5-21-123456789-1' },
      process: { name: 'powershell.exe', pid: 4242, cmd_line: 'powershell.exe -ep bypass' }
    },
    { provider: 'Microsoft-Windows-Sysmon', channel: 'Microsoft-Windows-Sysmon/Operational', event_id: 1 }
  ),
  
  -- Record 2: Sparse actor (user is NULL, process present)
  (
    1736347800000,                          -- 2026-01-08T15:30:00Z
    '2026-01-08T15:30:00Z',
    1001,                                   -- File System Activity
    1,
    100101,
    3,                                      -- Low severity
    {
      uid: 'evt-002',
      event_id: 'evt-002',
      run_id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
      scenario_id: 'scenario.atomic.t1059',
      collector_version: 'collector@0.1.0',
      normalizer_version: 'normalizer@0.1.0',
      source_type: 'sysmon',
      source_event_id: 'record:12346',
      labels: ['test', 'file']
    },
    {
      hostname: 'host-02',
      uid: NULL,
      ip: '10.0.0.2',
      ips: ['10.0.0.2']
    },
    {
      "user": NULL,                         -- No user context in this event
      process: { name: 'cmd.exe', pid: 1234, cmd_line: 'cmd.exe /c dir' }
    },
    { provider: 'Microsoft-Windows-Sysmon', channel: 'Microsoft-Windows-Sysmon/Operational', event_id: 11 }
  ),
  
  -- Record 3: NULL device (osquery scenario - device context not available)
  (
    1736351400000,                          -- 2026-01-08T16:30:00Z
    '2026-01-08T16:30:00Z',
    1007,
    1,
    100799,                                 -- activity_id=99 (Other) for snapshot
    NULL,                                   -- No severity
    {
      uid: 'evt-003',
      event_id: 'evt-003',
      run_id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
      scenario_id: 'scenario.osquery.processes',
      collector_version: 'collector@0.1.0',
      normalizer_version: 'normalizer@0.1.0',
      source_type: 'osquery',
      source_event_id: 'osquery:evt-003',
      labels: NULL                          -- No labels for this event
    },
    NULL,                                   -- No device context
    {
      "user": { name: 'root', uid: '0' },
      process: { name: 'bash', pid: 5678, cmd_line: '/bin/bash' }
    },
    NULL                                    -- No raw retention needed
  ),
  
  -- Record 4: Windows Security event (different source type)
  (
    1736355000000,                          -- 2026-01-08T17:30:00Z
    '2026-01-08T17:30:00Z',
    3001,                                   -- Authentication class
    3,                                      -- Identity & Access category
    300101,
    1,                                      -- Informational
    {
      uid: 'evt-004',
      event_id: 'evt-004',
      run_id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
      scenario_id: 'scenario.atomic.t1078',
      collector_version: 'collector@0.1.0',
      normalizer_version: 'normalizer@0.1.0',
      source_type: 'wineventlog',
      source_event_id: 'record:99999',
      labels: ['auth', 'logon']
    },
    {
      hostname: 'dc-01',
      uid: 'dc-01-guid',
      ip: '10.0.0.10',
      ips: ['10.0.0.10', '10.0.0.11']
    },
    {
      "user": { name: 'bob', uid: 'S-1-5-21-123456789-2' },
      process: NULL                         -- No process in auth event
    },
    { provider: 'Microsoft-Windows-Security-Auditing', channel: 'Security', event_id: 4624 }
  ),
  
  -- Record 5: Edge case - empty arrays
  (
    1736358600000,                          -- 2026-01-08T18:30:00Z
    '2026-01-08T18:30:00Z',
    4001,                                   -- Network Activity
    4,
    400101,
    2,
    {
      uid: 'evt-005',
      event_id: 'evt-005',
      run_id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
      scenario_id: 'scenario.network.conn',
      collector_version: 'collector@0.1.0',
      normalizer_version: 'normalizer@0.1.0',
      source_type: 'osquery',
      source_event_id: 'osquery:evt-005',
      labels: []                            -- Empty array (not NULL)
    },
    {
      hostname: 'host-03',
      uid: 'host-03-guid',
      ip: NULL,                             -- No single IP
      ips: []                               -- Empty array (not NULL)
    },
    {
      "user": { name: 'nobody', uid: '65534' },
      process: { name: 'curl', pid: 9999, cmd_line: NULL }
    },
    NULL
  );