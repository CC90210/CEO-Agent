-- bravo__013 — coordination claims become LEASES on repo-relative paths.
--
-- WHY THIS EXISTS
-- ---------------
-- The `agent_activity.files` column has carried "claims" since 2026-06. Measured
-- over the 90 days to 2026-08-27 it has never been able to prevent a collision,
-- for three independent reasons:
--
-- 1. NO GRAMMAR. Bravo wrote files=["pipeline","settings","auth","Turso"];
--    APEX wrote ["services/leadgen/**","oasis:app/lead-sheets/**","turso:leadgen_*"].
--    agent_activity.claims() keys a dict on those raw strings and compares by
--    exact match. "pipeline" can never equal "app/(dash)/pipeline/page.tsx", so
--    the overlap check was structurally incapable of firing even when both
--    agents dutifully posted claims.
--
-- 2. NO RELEASE. apex posted 60 `working` rows against 25 `done`. A claim was
--    only ever dropped by falling out of a 6h read window — an accidental TTL
--    with no owner, no heartbeat, and no way to tell "still working" from
--    "crashed three hours ago".
--
-- 3. NO REPO. A bare path is ambiguous across the ~26 repos under ~/APPS. Two
--    agents editing lib/nav-config.ts in different repos is fine; in the same
--    repo it is one agent silently reverting the other.
--
-- Measured cost of those three holes in oasis-command-center alone: 226 of 1,596
-- files touched by both sides, and 117 cross-side edits of the SAME file inside
-- 48h across 65 files — several under 30 minutes apart.
--
-- WHAT CHANGES
-- ------------
-- A claim becomes a lease with the semantics scripts/bridge_lock.py already
-- proved for Telegram bridge arbitration — acquire / heartbeat / release, an
-- explicit TTL, stale reclaim, and the holder's host recorded so a human knows
-- which machine to go look at. The difference is that bridge_lock is a local
-- file (one machine) and this is Turso (both machines, both orgs).
--
-- agent_activity is NOT replaced. It stays the human-readable narrative channel
-- and keeps its 90 days of history. This table is the machine-checkable half,
-- and it is what scripts/state/coord_guard.py reads on every Edit/Write.

CREATE TABLE IF NOT EXISTS coord_claims (
  id            TEXT PRIMARY KEY,
  agent         TEXT NOT NULL,      -- canonical key only: 'bravo' | 'apex'
  machine       TEXT NOT NULL,      -- hostname of the holder; who to go page
  repo          TEXT NOT NULL,      -- canonical slug, e.g. 'oasis-command-center'
  path_glob     TEXT NOT NULL,      -- repo-relative POSIX path or fnmatch glob
  task          TEXT NOT NULL,      -- groups the paths of one unit of work
  branch        TEXT,
  session_id    TEXT,               -- lets SessionEnd release exactly its own leases
  status        TEXT NOT NULL DEFAULT 'held',   -- held | released
  acquired_at   TEXT NOT NULL,
  heartbeat_at  TEXT NOT NULL,
  expires_at    TEXT NOT NULL,      -- absolute ISO-8601; refreshed by heartbeat
  released_at   TEXT
);

-- The hot path is coord_guard on every single Edit/Write: "is there a live
-- lease in THIS repo covering THIS path". Filtering on (repo, status,
-- expires_at) is that query.
CREATE INDEX IF NOT EXISTS idx_coord_claims_live
  ON coord_claims(repo, status, expires_at);

-- release --task and release --session are the two release paths; both need to
-- find a holder's open leases without scanning history.
CREATE INDEX IF NOT EXISTS idx_coord_claims_holder
  ON coord_claims(agent, status, task);
