-- ============================================================================
-- bravo__006 — training_corpus: what Maven learns from
--
-- The Train Maven tab has a drop-zone that has said "Ingestion lands in Phase 2"
-- since it shipped: you can paste forty links into it and nothing anywhere
-- records that you did. This is the table those links land in.
--
-- CC's framing, from the page itself: "Drop in what good looks like, and what
-- bad looks like. She learns from both." The `never_do` category is the half
-- people skip and the more valuable one — an exemplar teaches form, a rejection
-- teaches the boundary, and only the boundary can be crossed by accident.
--
-- ---------------------------------------------------------------------------
-- TRANSLATION NOTES
--   uuid / timestamptz   TEXT, as everywhere else on this backend.
--   CHECK on category    Kept. Unlike marketing_asset.asset_type this vocabulary
--   and status           is closed by design — three verdicts and four states,
--                        and if either ever grows it is a product decision worth
--                        a deliberate migration rather than a silent new value.
--   style_analysis       TEXT holding JSON: the extracted hook / pacing / tone.
--                        Nullable because it does not exist until the worker has
--                        run, and "not analysed yet" is a real state.
--   submitted_by         NOT NULL, no default. Two people use this tab and an
--                        exemplar with no author cannot be argued with later.
--                        Deliberately unlike author_email on marketing_asset,
--                        where a default was needed to describe rows that
--                        predate the column.
-- ============================================================================

create table if not exists training_corpus (
  id            TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  tenant_id     TEXT NOT NULL,

  url           TEXT NOT NULL,

  -- What the operator meant by dropping it in.
  --   do_more  — a model to work toward
  --   never_do — the boundary. Worth more than an exemplar.
  --   context  — background; neither a target nor a warning.
  category      TEXT NOT NULL
                  CHECK (category IN ('do_more','never_do','context')),

  -- pending -> processing -> ingested | failed. `processing` exists so an
  -- overlapping worker cannot fetch the same URL twice, the same reason
  -- marketing_publish_intent has `running`.
  status        TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending','processing','ingested','failed')),

  extracted_transcript TEXT,
  style_analysis       TEXT,

  -- Where the exemplar was written, so the row and the file can find each other.
  exemplar_path TEXT,
  title         TEXT,
  note          TEXT,

  submitted_by  TEXT NOT NULL,
  error         TEXT,
  attempts      INTEGER NOT NULL DEFAULT 0,

  created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  started_at    TEXT,
  ingested_at   TEXT,

  PRIMARY KEY (id),
  FOREIGN KEY (tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
);

-- The worker's only query: oldest pending first.
create index if not exists idx_training_corpus_pending
  on training_corpus (status, created_at);

-- The Train tab lists newest first, per tenant.
create index if not exists idx_training_corpus_tenant_created
  on training_corpus (tenant_id, created_at desc);

-- The same link dropped twice is one lesson, not two. Partial so a retry after
-- a failure can re-insert rather than being blocked by its own dead row.
create unique index if not exists training_corpus_tenant_url_unique
  on training_corpus (tenant_id, url)
  where status <> 'failed';
