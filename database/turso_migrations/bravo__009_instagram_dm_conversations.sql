-- ============================================================================
-- bravo__009 — instagram_dm_conversations: the DM closer's memory
--
-- One row per Instagram conversation. Everything the automation needs to answer
-- a DM the way a human would — what stage the relationship is at, what the
-- prospect has actually told us, how many times we have replied today, whether
-- a human has taken over, and whether a meeting has been booked.
--
-- WHY A TABLE AND NOT `data.dm` ON THE LEAD. Six mechanical reasons, none of
-- them stylistic:
--
--   1. State is needed on TURN 1. The CRM lead does not exist until after a
--      successful send, so there is nowhere to put "we have seen this message"
--      before the first reply goes out.
--   2. The identity keys disagree. State is per provider_conversation_id, which
--      is stable. The lead is keyed per HANDLE, which is mutable and already
--      duplicated twice for ccmckennaa; tenant_records has no unique index
--      beyond id.
--   3. SQLite's json_patch is RFC-7386 RECURSIVE, while the Postgres source
--      (database/099) is a top-level `||` merge. A nested data.dm blob leaves
--      the tested parity envelope: nested nulls DELETE keys and arrays are
--      replaced wholesale. Flat columns dodge all of it.
--   4. The compat layer's .table().update({"data": ...}) rewrites the WHOLE
--      column — the lost-update race that database/099_tenant_records_atomic_
--      patch.sql exists to kill.
--   5. "Which conversations are waiting on a human?" becomes an indexed
--      predicate instead of a json_extract scan over 31,032 leads. That scan is
--      the exact shape of the capped-page bug that shipped on 2026-08-20 and
--      created a duplicate lead on every poll.
--   6. sunbiz_conversation_state is the right SHAPE but carries
--      CHECK (provider='texttorrent'), and SQLite cannot ALTER a CHECK. Copy
--      the shape, not the table.
--
-- NO CHECK CONSTRAINT ON `stage`, DELIBERATELY. The enum is enforced in Python
-- (ig_dm_state.set_stage -> ig_conversation_brain.is_legal_transition, one copy
-- of the machine). ig-setter-pro migration 006 is the receipt for what a stage
-- CHECK costs in SQLite: a full table rebuild to add one value.
--
-- ---------------------------------------------------------------------------
-- TRANSLATION NOTES
--   TEXT timestamps  ISO-8601 UTC strings, as everywhere else in this database.
--                    SQLite has no timestamptz; a string that sorts correctly is
--                    the whole requirement.
--   INTEGER flags    automation_paused / handoff_pending are 0|1. SQLite has no
--                    boolean, so the DAO returns Python ints and callers must
--                    compare to 0, never rely on truthiness of a str.
--   tenant_id        Present, therefore db_turso auto-registers this table as
--                    tenant-scoped (db_turso.py:379-391) and EVERY statement
--                    against it needs a tenant_id predicate or it raises
--                    UnscopedQueryError. That is the intended safety property.
--   NO FKs           lead_id and booking_lead_id point at two different tables
--                    (tenant_records and the legacy `leads`). Neither is
--                    enforced: the conversation must survive its lead being
--                    deleted, because the DM thread still exists on Instagram.
-- ============================================================================

create table if not exists instagram_dm_conversations (
  id                              TEXT NOT NULL PRIMARY KEY,   -- uuid4, ours
  tenant_id                       TEXT NOT NULL,
  provider                        TEXT NOT NULL DEFAULT 'instagram',
  provider_conversation_id        TEXT NOT NULL,               -- Zernio conversation id
  participant_id                  TEXT NOT NULL,               -- Zernio participantId (stable)
  participant_handle              TEXT,                        -- NULL for 7/50 live convos
  participant_name                TEXT,
  account_id                      TEXT NOT NULL,               -- Zernio ObjectId

  -- Two different lead tables, on purpose. `lead_id` is the CRM projection in
  -- tenant_records; `booking_lead_id` is the legacy `leads` bridge row that
  -- book_discovery_call.load_lead() can actually read.
  lead_id                         TEXT,
  booking_lead_id                 TEXT,

  stage                           TEXT NOT NULL DEFAULT 'new', -- NO CHECK, on purpose
  stage_entered_at                TEXT,
  automation_paused               INTEGER NOT NULL DEFAULT 0,

  last_inbound_at                 TEXT,
  last_outbound_at                TEXT,
  last_processed_message_id       TEXT,
  inbound_message_count           INTEGER NOT NULL DEFAULT 0,
  reply_count_total               INTEGER NOT NULL DEFAULT 0,
  replies_today                   INTEGER NOT NULL DEFAULT 0,
  replies_today_date              TEXT,                        -- 'YYYY-MM-DD' UTC

  -- Only facts the prospect stated. Never inferred, never completed by the
  -- model. extracted_email is FIRST-WRITE-WINS and carries the id of the
  -- message it came from, so a booked meeting can be traced to the DM that
  -- authorised it.
  extracted_name                  TEXT,
  extracted_email                 TEXT,
  extracted_phone                 TEXT,
  extracted_business              TEXT,
  extracted_need                  TEXT,
  extracted_timeline              TEXT,
  extracted_email_source_msg_id   TEXT,

  handoff_pending                 INTEGER NOT NULL DEFAULT 0,
  handoff_reason                  TEXT,

  -- booking_status is the idempotency marker: none -> claimed -> booked|failed.
  -- 'failed' NEVER decays back to 'none' on its own; only an operator reset
  -- moves it. That is what makes double-booking impossible after a partial
  -- success, where the calendar event exists but a later step died.
  booking_status                  TEXT NOT NULL DEFAULT 'none',
  booking_claim_token             TEXT,
  booking_claimed_at              TEXT,
  booked_start                    TEXT,
  booked_end                      TEXT,
  booked_meet_link                TEXT,
  booking_email_status            TEXT,
  booking_error                   TEXT,

  consecutive_model_failures      INTEGER NOT NULL DEFAULT 0,
  consecutive_guardrail_rejects   INTEGER NOT NULL DEFAULT 0,
  last_error                      TEXT,
  last_decision_json              TEXT,

  created_at                      TEXT NOT NULL,
  updated_at                      TEXT NOT NULL
);

-- The identity of a conversation. INSERT OR IGNORE against this index is what
-- makes get_or_create() safe when two polls race: the loser's insert is ignored
-- and it reads back the winner's row instead of creating a second one.
create unique index if not exists idx_ig_dm_conv_unique
  on instagram_dm_conversations (tenant_id, provider, provider_conversation_id);

-- "What is in flight, newest first" — the operator CLI's list view.
create index if not exists idx_ig_dm_conv_stage
  on instagram_dm_conversations (tenant_id, stage, updated_at desc);

-- Partial index: only rows actually waiting on a human are in it, so
-- `list --handoffs` stays a small index scan no matter how big the table gets.
create index if not exists idx_ig_dm_conv_handoff
  on instagram_dm_conversations (tenant_id, handoff_pending) where handoff_pending = 1;
