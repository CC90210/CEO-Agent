-- nostalgic-requests master schema — transpiled from live Supabase
-- project ref: jqybbrtzpvmefgzzdagz  generated: 2026-08-07T06:52:25+00:00
-- tables: 8  indexes emitted: 38  views emitted: 2
--
-- NOT TRANSPILED (DAL responsibility — see scripts/lib/db_turso.py):
--   PL/pgSQL functions (7): generate_unique_slug, handle_new_user, increment_lead_stats, update_custom_agreements_timestamp, update_dj_profile_updated_at, update_product_purchases_timestamp, update_updated_at_column
--   Triggers (4): custom_agreements.custom_agreements_updated, dj_profiles.update_dj_profiles_updated_at, events.update_events_updated_at, product_purchases.product_purchases_updated
--   RLS policies: replaced by mandatory tenant scoping in db_turso.py
--   cross-schema FKs dropped (3, e.g. auth.users): events(user_id) -> auth.users; leads(user_id) -> auth.users; profiles(id) -> auth.users
--   FKs dropped as unenforceable in SQLite (0) — parent columns not unique in the emitted schema; enforce in the DAL
--   defaults dropped (2) and non-btree/expression indexes skipped (0): see turso_migrations/nostalgic__transpile_report.json
--
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS "custom_agreements" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "client_name" TEXT NOT NULL,
  "client_email" TEXT NOT NULL,
  "company_name" TEXT,
  "phone" TEXT,
  "agreement_reference" TEXT,
  "service_type" TEXT,
  "upfront_cost_cents" INTEGER NOT NULL DEFAULT 0,
  "monthly_cost_cents" INTEGER NOT NULL DEFAULT 0,
  "currency" TEXT DEFAULT 'USD',
  "nda_signed" INTEGER DEFAULT 0,
  "nda_signed_at" TEXT,
  "nda_signature_name" TEXT,
  "tos_accepted" INTEGER DEFAULT 0,
  "tos_accepted_at" TEXT,
  "tos_version" TEXT,
  "privacy_accepted" INTEGER DEFAULT 0,
  "privacy_accepted_at" TEXT,
  "privacy_version" TEXT,
  "service_agreement_accepted" INTEGER DEFAULT 0,
  "service_agreement_accepted_at" TEXT,
  "service_agreement_signature" TEXT,
  "ip_address" TEXT,
  "user_agent" TEXT,
  "stripe_checkout_session_id" TEXT,
  "stripe_subscription_id" TEXT,
  "payment_status" TEXT DEFAULT 'pending',
  "paid_at" TEXT,
  "status" TEXT DEFAULT 'draft',
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "dj_profiles" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "user_id" TEXT,
  "email" TEXT NOT NULL,
  "dj_name" TEXT NOT NULL,
  "full_name" TEXT,
  "phone" TEXT,
  "bio" TEXT,
  "profile_image_url" TEXT,
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "username" TEXT,
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "leads" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "phone" TEXT NOT NULL,
  "name" TEXT,
  "email" TEXT,
  "total_spent" TEXT DEFAULT 0,
  "request_count" INTEGER DEFAULT 1,
  "first_seen_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "last_seen_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "user_id" TEXT,
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "legal_acceptances" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "client_name" TEXT NOT NULL,
  "client_email" TEXT NOT NULL,
  "company_name" TEXT,
  "document_type" TEXT NOT NULL,
  "document_version" TEXT NOT NULL,
  "acceptance_method" TEXT NOT NULL,
  "signature_name" TEXT,
  "ip_address" TEXT,
  "user_agent" TEXT,
  "accepted_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "related_agreement_id" TEXT,
  "related_purchase_type" TEXT,
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "product_purchases" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "client_name" TEXT NOT NULL,
  "client_email" TEXT NOT NULL,
  "company_name" TEXT,
  "phone" TEXT,
  "product_tier" TEXT NOT NULL,
  "product_name" TEXT NOT NULL,
  "upfront_cost_cents" INTEGER DEFAULT 0,
  "monthly_cost_cents" INTEGER DEFAULT 0,
  "currency" TEXT DEFAULT 'USD',
  "tos_accepted" INTEGER DEFAULT 0,
  "tos_accepted_at" TEXT,
  "tos_version" TEXT,
  "privacy_accepted" INTEGER DEFAULT 0,
  "privacy_accepted_at" TEXT,
  "privacy_version" TEXT,
  "service_agreement_accepted" INTEGER DEFAULT 0,
  "service_agreement_accepted_at" TEXT,
  "service_agreement_signature" TEXT,
  "ip_address" TEXT,
  "user_agent" TEXT,
  "stripe_checkout_session_id" TEXT,
  "stripe_subscription_id" TEXT,
  "payment_status" TEXT DEFAULT 'pending',
  "paid_at" TEXT,
  "status" TEXT DEFAULT 'pending',
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "profiles" (
  "id" TEXT NOT NULL,
  "email" TEXT,
  "full_name" TEXT,
  "avatar_url" TEXT,
  "updated_at" TEXT,
  "stripe_account_id" TEXT,
  "stripe_onboarding_complete" INTEGER DEFAULT 0,
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "events" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "name" TEXT NOT NULL,
  "venue_name" TEXT NOT NULL,
  "venue_address" TEXT,
  "start_time" TEXT NOT NULL,
  "end_time" TEXT NOT NULL,
  "event_type" TEXT NOT NULL DEFAULT 'other',
  "custom_message" TEXT,
  "base_price" TEXT DEFAULT 5.00,
  "status" TEXT DEFAULT 'draft',
  "unique_slug" TEXT NOT NULL,
  "qr_code_url" TEXT,
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "dj_id" TEXT,
  "price_single" TEXT DEFAULT 5.00,
  "price_double" TEXT DEFAULT 8.00,
  "price_party" TEXT DEFAULT 12.00,
  "price_priority" TEXT DEFAULT 10.00,
  "price_shoutout" TEXT DEFAULT 5.00,
  "price_guaranteed" TEXT DEFAULT 20.00,
  "user_id" TEXT NOT NULL,
  PRIMARY KEY ("id"),
  FOREIGN KEY ("dj_id") REFERENCES "dj_profiles" ("id")
);

CREATE TABLE IF NOT EXISTS "requests" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "event_id" TEXT,
  "song_title" TEXT NOT NULL,
  "song_artist" TEXT NOT NULL,
  "song_album" TEXT,
  "song_artwork_url" TEXT,
  "song_preview_url" TEXT,
  "song_itunes_url" TEXT,
  "song_itunes_id" TEXT,
  "requester_name" TEXT,
  "requester_phone" TEXT NOT NULL,
  "requester_email" TEXT,
  "amount_paid" TEXT NOT NULL,
  "stripe_payment_id" TEXT,
  "stripe_session_id" TEXT,
  "song_count" INTEGER DEFAULT 1,
  "has_priority" INTEGER DEFAULT 0,
  "has_shoutout" INTEGER DEFAULT 0,
  "has_guaranteed_next" INTEGER DEFAULT 0,
  "status" TEXT DEFAULT 'pending',
  "sms_sent" INTEGER DEFAULT 0,
  "sms_sent_at" TEXT,
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "played_at" TEXT,
  "is_paid" INTEGER DEFAULT 0,
  PRIMARY KEY ("id"),
  FOREIGN KEY ("event_id") REFERENCES "events" ("id")
);

-- indexes
CREATE UNIQUE INDEX IF NOT EXISTS "profiles_pkey" ON "profiles" (id);
CREATE INDEX IF NOT EXISTS "idx_profiles_stripe_id" ON "profiles" (stripe_account_id);
CREATE UNIQUE INDEX IF NOT EXISTS "requests_pkey" ON "requests" (id);
CREATE INDEX IF NOT EXISTS "idx_requests_event_id" ON "requests" (event_id);
CREATE INDEX IF NOT EXISTS "idx_requests_status" ON "requests" (status);
CREATE INDEX IF NOT EXISTS "idx_requests_created_at" ON "requests" (created_at);
CREATE INDEX IF NOT EXISTS "idx_requests_is_paid" ON "requests" (is_paid);
CREATE INDEX IF NOT EXISTS "idx_requests_event" ON "requests" (event_id);
CREATE UNIQUE INDEX IF NOT EXISTS "dj_profiles_pkey" ON "dj_profiles" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "dj_profiles_user_id_key" ON "dj_profiles" (user_id);
CREATE INDEX IF NOT EXISTS "idx_dj_profiles_user_id" ON "dj_profiles" (user_id);
CREATE INDEX IF NOT EXISTS "idx_dj_profiles_email" ON "dj_profiles" (email);
CREATE UNIQUE INDEX IF NOT EXISTS "custom_agreements_pkey" ON "custom_agreements" (id);
CREATE INDEX IF NOT EXISTS "idx_custom_agreements_email" ON "custom_agreements" (client_email);
CREATE INDEX IF NOT EXISTS "idx_custom_agreements_status" ON "custom_agreements" (status);
CREATE UNIQUE INDEX IF NOT EXISTS "legal_acceptances_pkey" ON "legal_acceptances" (id);
CREATE INDEX IF NOT EXISTS "idx_legal_acceptances_email" ON "legal_acceptances" (client_email);
CREATE INDEX IF NOT EXISTS "idx_legal_acceptances_document" ON "legal_acceptances" (document_type, document_version);
CREATE INDEX IF NOT EXISTS "idx_legal_acceptances_date" ON "legal_acceptances" (accepted_at);
CREATE UNIQUE INDEX IF NOT EXISTS "product_purchases_pkey" ON "product_purchases" (id);
CREATE INDEX IF NOT EXISTS "idx_product_purchases_email" ON "product_purchases" (client_email);
CREATE INDEX IF NOT EXISTS "idx_product_purchases_status" ON "product_purchases" (status);
CREATE INDEX IF NOT EXISTS "idx_product_purchases_tier" ON "product_purchases" (product_tier);
CREATE UNIQUE INDEX IF NOT EXISTS "events_pkey" ON "events" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "events_unique_slug_key" ON "events" (unique_slug);
CREATE INDEX IF NOT EXISTS "idx_events_status" ON "events" (status);
CREATE INDEX IF NOT EXISTS "idx_events_slug" ON "events" (unique_slug);
CREATE INDEX IF NOT EXISTS "idx_events_start_time" ON "events" (start_time);
CREATE INDEX IF NOT EXISTS "idx_events_dj_id" ON "events" (dj_id);
CREATE INDEX IF NOT EXISTS "idx_events_user_id" ON "events" (user_id);
CREATE INDEX IF NOT EXISTS "idx_events_user" ON "events" (user_id);
CREATE INDEX IF NOT EXISTS "idx_events_created" ON "events" (created_at DESC);
CREATE INDEX IF NOT EXISTS "idx_events_created_at" ON "events" (created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "leads_pkey" ON "leads" (id);
CREATE INDEX IF NOT EXISTS "idx_leads_phone" ON "leads" (phone);
CREATE UNIQUE INDEX IF NOT EXISTS "leads_dj_phone_idx" ON "leads" (user_id, phone);
CREATE INDEX IF NOT EXISTS "idx_leads_user_id" ON "leads" (user_id);
CREATE INDEX IF NOT EXISTS "idx_leads_user" ON "leads" (user_id);

-- views
CREATE VIEW IF NOT EXISTS "dashboard_overview" AS
SELECT count(DISTINCT e.id) AS total_events,
    count(r.id) AS total_requests,
    COALESCE(sum(r.amount_paid), 0) AS total_revenue,
    count(DISTINCT r.requester_phone) AS unique_customers,
    COALESCE(avg(r.amount_paid), 0) AS avg_request_value,
    count(DISTINCT l.id) AS total_leads
   FROM events e
     LEFT JOIN requests r ON e.id = r.event_id
     LEFT JOIN leads l ON true;

CREATE VIEW IF NOT EXISTS "event_stats" AS
SELECT e.id AS event_id,
    e.name AS event_name,
    e.venue_name,
    e.status,
    e.start_time,
    e.end_time,
    count(r.id) AS total_requests,
    COALESCE(sum(r.amount_paid), 0) AS total_revenue,
    count(
        CASE
            WHEN r.status = 'pending' THEN 1
            ELSE NULL
        END) AS pending_requests,
    count(
        CASE
            WHEN r.status = 'played' THEN 1
            ELSE NULL
        END) AS played_requests,
    count(
        CASE
            WHEN r.has_priority THEN 1
            ELSE NULL
        END) AS priority_requests,
    count(
        CASE
            WHEN r.has_shoutout THEN 1
            ELSE NULL
        END) AS shoutout_requests,
    count(
        CASE
            WHEN r.has_guaranteed_next THEN 1
            ELSE NULL
        END) AS guaranteed_next_requests
   FROM events e
     LEFT JOIN requests r ON e.id = r.event_id
  GROUP BY e.id, e.name, e.venue_name, e.status, e.start_time, e.end_time;
