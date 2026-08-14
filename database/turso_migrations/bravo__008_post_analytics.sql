-- ============================================================================
-- bravo__008 — post_analytics: what the work actually did
--
-- The Performance tab has been a greyed-out chip since the portal shipped
-- ("No metrics connected yet. Phase 5."). The metrics exist and always have —
-- Zernio has been collecting them and nothing here ever read them.
--
-- MEASURED BEFORE BUILDING (2026-08-14): GET /api/v1/analytics returns
-- hasAnalyticsAccess: true and 42 of 50 posts carry non-zero metrics.
--
-- THE COLUMNS ARE ZERNIO'S, NOT A WISH LIST
-- The task specified `views, likes, comments, shares, retention_rate FLOAT`.
-- Zernio does not return a retention rate; it returns igReelsAvgWatchTime and
-- videoDurationSeconds, and retention is those two divided — a derived number
-- that must not be stored as if it were measured, because the day Zernio changes
-- either input a stored ratio silently becomes a lie. So the inputs are stored
-- and the ratio is computed at read time.
--
-- Everything else here is a field the API actually emits, verified against a
-- live response rather than assumed: impressions, likes, comments, shares,
-- saves, clicks, views, follows, engagementRate.
--
-- ---------------------------------------------------------------------------
-- TRANSLATION NOTES
--   PRIMARY KEY   (tenant_id, platform_post_id). One row per post PER PLATFORM,
--                 because the same asset published to six networks has six
--                 different sets of numbers and averaging them answers nothing.
--   asset_id      Nullable FK-by-convention to marketing_asset. Zernio knows
--                 about posts we did not create here, and dropping those would
--                 make the Performance tab disagree with the Zernio dashboard.
--   REAL          SQLite has no FLOAT; REAL is the same thing under its real name.
--   NOT NULL      Every counter defaults to 0 — "nobody watched" and "we have not
--                 synced yet" are different facts, and last_synced_at is what
--                 tells them apart.
-- ============================================================================

create table if not exists post_analytics (
  id               TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  tenant_id        TEXT NOT NULL,

  -- Zernio's own ids. `zernio_post_id` groups the platforms of one post;
  -- `platform_post_id` is the network's id and is what makes a row unique.
  zernio_post_id   TEXT NOT NULL,
  platform_post_id TEXT NOT NULL,
  platform         TEXT NOT NULL,
  account_username TEXT,

  -- Ours, when we can match it. Null for anything published outside the Library.
  asset_id         TEXT,

  impressions      INTEGER NOT NULL DEFAULT 0,
  views            INTEGER NOT NULL DEFAULT 0,
  likes            INTEGER NOT NULL DEFAULT 0,
  comments         INTEGER NOT NULL DEFAULT 0,
  shares           INTEGER NOT NULL DEFAULT 0,
  saves            INTEGER NOT NULL DEFAULT 0,
  clicks           INTEGER NOT NULL DEFAULT 0,
  follows          INTEGER NOT NULL DEFAULT 0,
  engagement_rate  REAL    NOT NULL DEFAULT 0,

  -- Retention INPUTS, not a stored ratio. See the note above.
  avg_watch_s      REAL,
  duration_s       REAL,

  content_excerpt  TEXT,
  published_at     TEXT,
  last_synced_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),

  PRIMARY KEY (id)
);

-- One row per post per platform. Re-syncing must update, never duplicate.
create unique index if not exists post_analytics_platform_post_unique
  on post_analytics (tenant_id, platform_post_id);

-- "top by retention over the last 7 days", the Performance tab's main question.
create index if not exists idx_post_analytics_published
  on post_analytics (tenant_id, published_at desc);

-- Join back to the Library when the post is one of ours.
create index if not exists idx_post_analytics_asset
  on post_analytics (tenant_id, asset_id);
