-- V6.0 transactional state schema
-- Applied by scripts/state_manager.py on first connect; idempotent.

PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA foreign_keys=ON;
PRAGMA busy_timeout=5000;

CREATE TABLE IF NOT EXISTS schema_version (
  version     INTEGER PRIMARY KEY,
  applied_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_state (
  agent           TEXT PRIMARY KEY,
  status          TEXT NOT NULL,
  current_focus   TEXT,
  last_heartbeat  TEXT NOT NULL,
  tick_count      INTEGER NOT NULL DEFAULT 0,
  health          TEXT NOT NULL DEFAULT 'green',
  payload_json    TEXT
);

CREATE TABLE IF NOT EXISTS session_log (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  ts              TEXT NOT NULL,
  agent           TEXT NOT NULL,
  session_id      TEXT NOT NULL,
  note            TEXT NOT NULL,
  artifacts_json  TEXT,
  UNIQUE (session_id, note)
);
CREATE INDEX IF NOT EXISTS idx_session_log_ts    ON session_log(ts DESC);
CREATE INDEX IF NOT EXISTS idx_session_log_agent ON session_log(agent, ts DESC);

CREATE TABLE IF NOT EXISTS active_task (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at      TEXT NOT NULL,
  updated_at      TEXT NOT NULL,
  bucket          TEXT NOT NULL,
  owner           TEXT NOT NULL,
  title           TEXT NOT NULL,
  status          TEXT NOT NULL DEFAULT 'open',
  priority        INTEGER NOT NULL DEFAULT 100,
  closed_at       TEXT
);
CREATE INDEX IF NOT EXISTS idx_active_task_status ON active_task(status, bucket, priority);

CREATE TABLE IF NOT EXISTS state_transaction (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  ts              TEXT NOT NULL,
  actor           TEXT NOT NULL,
  op              TEXT NOT NULL,
  table_name      TEXT NOT NULL,
  row_pk          TEXT,
  diff_json       TEXT,
  source_script   TEXT
);
CREATE INDEX IF NOT EXISTS idx_state_transaction_ts ON state_transaction(ts DESC);

INSERT OR IGNORE INTO schema_version(version, applied_at)
VALUES (1, strftime('%Y-%m-%dT%H:%M:%fZ','now'));
