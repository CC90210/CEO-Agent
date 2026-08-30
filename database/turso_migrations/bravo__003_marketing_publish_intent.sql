-- ============================================================================
-- bravo__003 — marketing_publish_intent, ported to SQLite/libSQL
--
-- Postgres source of truth:
--   oasis-command-center/database/140_marketing_publish_intent.sql
--
-- WHAT THE TABLE IS FOR
-- CC, 2026-08-14: "I should be able to click on one of these videos and then
-- manually post it to all the social media channels via our API key that we have
-- connected."
--
-- The Command Center runs on Vercel. The only sanctioned publisher is
-- CMO-Agent/scripts/publishers/base.publish() — Python, runs send_gateway first
-- (killswitch, daily caps, audit trail), needs credentials on the operator's
-- machine. A Vercel function cannot call it, and calling Zernio's HTTP API
-- directly instead would skip the killswitch, the caps and the audit row while
-- forking per-platform knowledge that took real failures to learn (Instagram
-- video must declare contentType: reel; YouTube needs a <=95-char title).
--
-- So the app records INTENT here and scripts/marketing_publish_drain.py, which
-- runs where the gateway runs, performs it.
--
-- ---------------------------------------------------------------------------
-- TRANSLATION NOTES (what could not be carried over literally)
--
--   gen_random_uuid()   No SQLite equivalent. Same randomblob() expression the
--                       rest of this database already uses for uuid defaults —
--                       see tenant_invites.id in the live schema.
--   timestamptz         TEXT, ISO-8601 UTC, matching every other ported table.
--                       now() becomes strftime('%Y-%m-%dT%H:%M:%fZ','now').
--   jsonb               TEXT holding JSON. The readers already JSON.parse it:
--                       lib/founders/marketing-queries.ts getLatestPublishIntent
--                       accepts either an array or a JSON string for exactly this
--                       reason.
--   RLS / policies       SQLite has no RLS. Isolation comes from db_turso's
--                       scoping guard plus the explicit .eq("tenant_id", …) that
--                       every reader and the API route already pass. tenant_id is
--                       NOT NULL so those filters always bite.
--   NOT NULL + DEFAULT   Every non-null column here carries its own default or is
--                       supplied by the writer. Learned today from
--                       tenant_invites.expires_at, whose Postgres default did not
--                       survive its port and silently broke every invite for
--                       months.
-- ============================================================================

create table if not exists marketing_publish_intent (
  id            TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  tenant_id     TEXT NOT NULL,
  asset_id      TEXT NOT NULL,

  -- JSON array of platform keys: ["instagram","tiktok",...]. Validated by the
  -- API route against what is connected, and again by the drainer against
  -- CMO-Agent schedule_posts.ACCOUNTS, which is the only place that truly knows.
  platforms     TEXT NOT NULL,

  -- queued -> running -> done | failed. `running` exists so a slow publish (a
  -- 10 MB reel to five networks takes over a minute) cannot be claimed twice by
  -- an overlapping drain and posted twice. There is no unsending.
  state         TEXT NOT NULL DEFAULT 'queued'
                  CHECK (state IN ('queued','running','done','failed')),

  requested_by  TEXT NOT NULL,
  note          TEXT,

  -- Per-platform outcome once the drainer has been:
  -- {"instagram":{"ok":true,"post_id":"..."}}. Keeps a partial success legible
  -- instead of collapsing five channels into one boolean.
  result        TEXT NOT NULL DEFAULT '{}',
  error         TEXT,

  attempts      INTEGER NOT NULL DEFAULT 0,
  created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  started_at    TEXT,
  finished_at   TEXT,

  PRIMARY KEY (id),
  FOREIGN KEY (tenant_id, asset_id) REFERENCES marketing_asset (tenant_id, id) ON DELETE CASCADE
);

-- The drainer's only query: oldest queued first.
create index if not exists idx_marketing_publish_intent_queued
  on marketing_publish_intent (state, created_at);

-- "has this already been sent anywhere", for the detail page.
create index if not exists idx_marketing_publish_intent_asset
  on marketing_publish_intent (tenant_id, asset_id, created_at desc);
