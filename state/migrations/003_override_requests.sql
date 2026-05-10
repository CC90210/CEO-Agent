-- V6 BUILD 4 — Operator-approval override flow
-- Applied by scripts/state_manager.py on next connect; idempotent.
--
-- The agent never holds a token. Every blocked command auto-creates a
-- `pending` override_request row; the operator approves the row by id;
-- the next attempt at the SAME command_hash within the TTL gets through
-- and the row is marked `consumed`. Single-use, command-hash-bound,
-- HMAC-signed at-rest.

PRAGMA journal_mode=WAL;
PRAGMA busy_timeout=5000;

CREATE TABLE IF NOT EXISTS override_request (
  id            TEXT PRIMARY KEY,                         -- 'req-' + 8 hex chars
  ts            TEXT NOT NULL,                            -- when the block fired
  expires_at    TEXT NOT NULL,                            -- ts + ttl
  command       TEXT NOT NULL,                            -- full command text (capped at 2000 chars in code)
  command_hash  TEXT NOT NULL,                            -- sha256(command), the approval-binding key
  layer         TEXT NOT NULL,                            -- which guard layer fired (hard-blocklist, sql-ast, ...)
  reason        TEXT,                                     -- agent-supplied or auto-derived
  caller_pid    INTEGER,                                  -- the process that hit the block
  status        TEXT NOT NULL DEFAULT 'pending',          -- pending | approved | denied | expired | consumed
  approved_at   TEXT,
  approved_by   TEXT,                                     -- 'cc' (only TTY-validated approver)
  approved_reason TEXT,
  consumed_at   TEXT,
  hmac_sig      TEXT                                      -- HMAC over id|command_hash|expires_at|status:approved (defense in depth)
);
CREATE INDEX IF NOT EXISTS idx_override_status ON override_request(status, expires_at);
CREATE INDEX IF NOT EXISTS idx_override_hash   ON override_request(command_hash, status, expires_at);
CREATE INDEX IF NOT EXISTS idx_override_ts     ON override_request(ts DESC);

INSERT OR IGNORE INTO schema_version(version, applied_at)
VALUES (3, strftime('%Y-%m-%dT%H:%M:%fZ','now'));
