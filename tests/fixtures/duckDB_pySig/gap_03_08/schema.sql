-- tests/fixtures/duckDB_pySig/gap_03_08/schema.sql
-- Minimal OCSF-like schema for DuckDB backend testing
-- Purpose: Validate GAP-03 (nested fields) and GAP-08 (timestamp typing)

CREATE TABLE ocsf_events (
  -- Tier 0: Core envelope (contract-required)
  time BIGINT NOT NULL,                    -- ms since epoch, UTC
  time_dt VARCHAR NOT NULL,                -- ISO-8601/RFC3339 string
  class_uid INTEGER NOT NULL,              -- OCSF class identifier
  category_uid INTEGER,                    -- nullable
  type_uid INTEGER,                        -- nullable
  severity_id INTEGER,                     -- nullable
  
  -- Tier 0: Metadata (nested STRUCT, required)
  metadata STRUCT(
    uid VARCHAR,                           -- MUST equal event_id (ADR-0002)
    event_id VARCHAR,                      -- deterministic idempotency key
    run_id VARCHAR,                        -- UUID
    scenario_id VARCHAR,
    collector_version VARCHAR,
    normalizer_version VARCHAR,
    source_type VARCHAR,                   -- e.g., 'sysmon', 'wineventlog', 'osquery'
    source_event_id VARCHAR,               -- upstream native ID
    labels VARCHAR[]                       -- classification labels
  ) NOT NULL,
  
  -- Tier 1: Device (nullable nested STRUCT)
  device STRUCT(
    hostname VARCHAR,
    uid VARCHAR,
    ip VARCHAR,
    ips VARCHAR[]                          -- array of IPs
  ),
  
  -- Tier 1/2: Actor (nullable nested STRUCT with nested children)
  actor STRUCT(
    "user" STRUCT(                         -- quoted: 'user' is reserved
      name VARCHAR,
      uid VARCHAR
    ),
    process STRUCT(
      name VARCHAR,
      pid INTEGER,
      cmd_line VARCHAR
    )
  ),
  
  -- Tier R: Raw retention (nullable)
  raw STRUCT(
    provider VARCHAR,
    channel VARCHAR,
    event_id INTEGER
  )
);

-- Index recommendations (non-normative, for query optimization)
-- CREATE INDEX idx_class_uid ON ocsf_events(class_uid);
-- CREATE INDEX idx_time ON ocsf_events(time);
-- CREATE INDEX idx_source_type ON ocsf_events(metadata.source_type);