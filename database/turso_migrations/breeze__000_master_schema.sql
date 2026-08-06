-- breeze-portal master schema — transpiled from live Supabase
-- project ref: xugwrhvaoihyidtdgwkq  generated: 2026-08-06T22:40:15+00:00
-- tables: 46  indexes emitted: 171
--
-- NOT TRANSPILED (DAL responsibility — see scripts/lib/db_turso.py):
--   PL/pgSQL functions (12): accrue_iso_commission, approve_draw_request, assert_no_cross_role_binding, cancel_draw_request, claim_plaid_statement_link_token, compute_platform_fee, estimate_platform_fee, import_merchant_position, record_funded_draw, submit_draw_request, touch_updated_at, update_merchant_contact
--   Triggers (32): advances.advances_touch, bank_accounts.bank_accounts_touch, board_columns.board_columns_touch, board_groups.board_groups_touch, board_items.board_items_touch, board_views.board_views_touch, boards.boards_touch, chat_conversations.chat_conversations_touch, draw_requests.draw_requests_touch, draws.draws_accrue_iso_commission...
--   RLS policies: replaced by mandatory tenant scoping in db_turso.py
--   cross-schema FKs dropped (9, e.g. auth.users): documents(uploaded_by_user_id) -> auth.users; draw_requests(decided_by_user_id) -> auth.users; draw_requests(submitted_by_user_id) -> auth.users; merchant_users(auth_user_id) -> auth.users; merchant_users(invited_by) -> auth.users; plaid_statement_requests(requested_by_user_id) -> auth.users
--   FKs dropped as unenforceable in SQLite (0) — parent columns not unique in the emitted schema; enforce in the DAL
--   defaults dropped (2) and non-btree/expression indexes skipped (1): see turso_migrations/breeze__transpile_report.json
--
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS "tenants" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "slug" TEXT NOT NULL,
  "name" TEXT NOT NULL,
  "brand_logo_url" TEXT,
  "brand_primary_color" TEXT NOT NULL DEFAULT '#1e40af',
  "brand_secondary_color" TEXT,
  "support_email" TEXT,
  "crm_webhook_url" TEXT,
  "crm_webhook_secret" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "platform_fee_rate" TEXT NOT NULL DEFAULT 0.0000,
  "platform_fee_cap_cents" INTEGER,
  "platform_fee_label" TEXT,
  "platform_fee_payer" TEXT NOT NULL DEFAULT 'merchant',
  "epa_unaccrued_charge_pct" TEXT NOT NULL DEFAULT 0,
  "plaid_client_id" TEXT,
  "plaid_secret_enc" TEXT,
  "plaid_env" TEXT,
  "email_from_user" TEXT,
  "email_app_password_enc" TEXT,
  PRIMARY KEY ("id"),
  CONSTRAINT "tenants_epa_unaccrued_charge_pct_check" CHECK (((epa_unaccrued_charge_pct >= (0)) AND (epa_unaccrued_charge_pct <= (1)))),
  CONSTRAINT "tenants_plaid_env_check" CHECK (((plaid_env IS NULL) OR (plaid_env IN ('sandbox', 'development', 'production')))),
  CONSTRAINT "tenants_platform_fee_cap_cents_check" CHECK (((platform_fee_cap_cents IS NULL) OR (platform_fee_cap_cents > 0))),
  CONSTRAINT "tenants_platform_fee_payer_check" CHECK ((platform_fee_payer IN ('merchant', 'lender'))),
  CONSTRAINT "tenants_platform_fee_rate_check" CHECK (((platform_fee_rate >= (0)) AND (platform_fee_rate <= 0.5000)))
);

CREATE TABLE IF NOT EXISTS "audit_log" (
  "id" INTEGER PRIMARY KEY,
  "tenant_id" TEXT NOT NULL,
  "actor_id" TEXT,
  "actor_role" TEXT,
  "entity_type" TEXT NOT NULL,
  "entity_id" TEXT,
  "action" TEXT NOT NULL,
  "before_json" TEXT,
  "after_json" TEXT,
  "ip" TEXT,
  "ua" TEXT,
  "at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "boards" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "kind" TEXT NOT NULL DEFAULT 'custom',
  "name" TEXT NOT NULL,
  "description" TEXT,
  "archived" INTEGER NOT NULL DEFAULT 0,
  "created_by" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "boards_kind_check" CHECK ((kind IN ('custom', 'deals'))),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "crm_import_runs" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "source" TEXT NOT NULL DEFAULT 'monday',
  "mode" TEXT NOT NULL DEFAULT 'file',
  "status" TEXT NOT NULL DEFAULT 'running',
  "boards_imported" INTEGER NOT NULL DEFAULT 0,
  "items_imported" INTEGER NOT NULL DEFAULT 0,
  "error" TEXT,
  "started_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "finished_at" TEXT,
  PRIMARY KEY ("id"),
  CONSTRAINT "crm_import_runs_mode_check" CHECK ((mode IN ('file', 'api'))),
  CONSTRAINT "crm_import_runs_source_check" CHECK ((source IN ('monday', 'csv'))),
  CONSTRAINT "crm_import_runs_status_check" CHECK ((status IN ('running', 'succeeded', 'failed'))),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "email_suppressions" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "email" TEXT NOT NULL,
  "tenant_id" TEXT,
  "brand" TEXT,
  "suppressed_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "source" TEXT,
  "reason" TEXT,
  "ip" TEXT,
  "ua" TEXT,
  PRIMARY KEY ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "iso_partners" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "name" TEXT NOT NULL,
  "legal_name" TEXT,
  "contact_name" TEXT,
  "email" TEXT,
  "phone" TEXT,
  "states" TEXT NOT NULL DEFAULT '[]',
  "industries" TEXT NOT NULL DEFAULT '[]',
  "default_commission_pct" TEXT NOT NULL DEFAULT 0,
  "w9_status" TEXT NOT NULL DEFAULT 'none',
  "agreement_status" TEXT NOT NULL DEFAULT 'none',
  "clawback_days" INTEGER NOT NULL DEFAULT 0,
  "exclusivity_days" INTEGER NOT NULL DEFAULT 30,
  "status" TEXT NOT NULL DEFAULT 'active',
  "notes" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "iso_partners_agreement_status_check" CHECK ((agreement_status IN ('none', 'sent', 'signed', 'expired', 'terminated'))),
  CONSTRAINT "iso_partners_clawback_days_check" CHECK ((clawback_days >= 0)),
  CONSTRAINT "iso_partners_default_commission_pct_check" CHECK (((default_commission_pct >= (0)) AND (default_commission_pct <= 0.25))),
  CONSTRAINT "iso_partners_exclusivity_days_check" CHECK ((exclusivity_days >= 0)),
  CONSTRAINT "iso_partners_status_check" CHECK ((status IN ('active', 'paused', 'terminated'))),
  CONSTRAINT "iso_partners_w9_status_check" CHECK ((w9_status IN ('none', 'requested', 'received', 'verified'))),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "kb_documents" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "title" TEXT NOT NULL,
  "kind" TEXT NOT NULL DEFAULT 'other',
  "source_ref" TEXT,
  "status" TEXT NOT NULL DEFAULT 'active',
  "chunk_count" INTEGER NOT NULL DEFAULT 0,
  "created_by" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "kb_documents_kind_check" CHECK ((kind IN ('underwriting_guideline', 'investor_agreement', 'servicing_agreement', 'legal', 'collections_sop', 'reconciliation', 'pricing', 'training', 'other'))),
  CONSTRAINT "kb_documents_status_check" CHECK ((status IN ('active', 'archived', 'processing', 'failed'))),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "message_templates" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "key" TEXT NOT NULL,
  "name" TEXT NOT NULL,
  "channel" TEXT NOT NULL DEFAULT 'email',
  "subject" TEXT,
  "body" TEXT NOT NULL,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "message_templates_channel_check" CHECK ((channel IN ('email', 'sms'))),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "plaid_sync_state" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "plaid_item_id" TEXT NOT NULL,
  "cursor" TEXT,
  "last_synced_at" TEXT,
  "tx_count" INTEGER NOT NULL DEFAULT 0,
  "last_error" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "sequences" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "name" TEXT NOT NULL,
  "description" TEXT,
  "trigger" TEXT NOT NULL DEFAULT 'manual',
  "channel" TEXT NOT NULL DEFAULT 'email',
  "steps" TEXT NOT NULL DEFAULT '[]',
  "active" INTEGER NOT NULL DEFAULT 1,
  "created_by" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "mode" TEXT NOT NULL DEFAULT 'draft',
  "trigger_config" TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY ("id"),
  CONSTRAINT "sequences_channel_check" CHECK ((channel IN ('email', 'sms', 'both'))),
  CONSTRAINT "sequences_mode_check" CHECK ((mode IN ('draft', 'live'))),
  CONSTRAINT "sequences_trigger_check" CHECK ((trigger IN ('renewal', 'default', 'management', 'manual'))),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "tenant_draw_notifiers" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "email" TEXT NOT NULL,
  "label" TEXT,
  "active" INTEGER NOT NULL DEFAULT 1,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "tenant_users" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "auth_user_id" TEXT NOT NULL,
  "email" TEXT NOT NULL,
  "full_name" TEXT,
  "role" TEXT NOT NULL,
  "invited_by" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "tenant_users_role_check" CHECK ((role IN ('owner', 'admin', 'staff', 'viewer'))),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "webhook_events" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "direction" TEXT NOT NULL,
  "provider" TEXT NOT NULL,
  "event_type" TEXT NOT NULL,
  "payload_json" TEXT,
  "signature" TEXT,
  "target_url" TEXT,
  "response_status" INTEGER,
  "response_body" TEXT,
  "attempts" INTEGER NOT NULL DEFAULT 0,
  "last_attempt_at" TEXT,
  "status" TEXT NOT NULL DEFAULT 'pending',
  "external_id" TEXT,
  "related_entity_type" TEXT,
  "related_entity_id" TEXT,
  "error_message" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "webhook_events_direction_check" CHECK ((direction IN ('inbound', 'outbound'))),
  CONSTRAINT "webhook_events_status_check" CHECK ((status IN ('pending', 'sent', 'failed', 'received', 'processed', 'stub', 'duplicate'))),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "board_columns" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "board_id" TEXT NOT NULL,
  "name" TEXT NOT NULL,
  "type" TEXT NOT NULL,
  "settings" TEXT NOT NULL DEFAULT '{}',
  "is_locked" INTEGER NOT NULL DEFAULT 0,
  "position" TEXT NOT NULL DEFAULT 1000,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "board_columns_type_check" CHECK ((type IN ('text', 'long_text', 'number', 'status', 'people', 'date', 'checkbox', 'link', 'tags'))),
  FOREIGN KEY ("board_id") REFERENCES "boards" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "board_groups" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "board_id" TEXT NOT NULL,
  "name" TEXT NOT NULL,
  "color" TEXT,
  "position" TEXT NOT NULL DEFAULT 1000,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("board_id") REFERENCES "boards" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "board_views" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "board_id" TEXT NOT NULL,
  "name" TEXT NOT NULL,
  "kind" TEXT NOT NULL DEFAULT 'table',
  "settings" TEXT NOT NULL DEFAULT '{}',
  "position" TEXT NOT NULL DEFAULT 1000,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "board_views_kind_check" CHECK ((kind IN ('table', 'kanban'))),
  FOREIGN KEY ("board_id") REFERENCES "boards" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "kb_chunks" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "document_id" TEXT NOT NULL,
  "chunk_index" INTEGER NOT NULL,
  "content" TEXT NOT NULL,
  "embedding" F32_BLOB(1020),
  "token_count" INTEGER,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("document_id") REFERENCES "kb_documents" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "merchants" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "business_name" TEXT NOT NULL,
  "dba" TEXT,
  "ein_last4" TEXT,
  "primary_contact_name" TEXT,
  "primary_contact_email" TEXT,
  "primary_contact_phone" TEXT,
  "status" TEXT NOT NULL DEFAULT 'active',
  "street" TEXT,
  "city" TEXT,
  "state_region" TEXT,
  "postal_code" TEXT,
  "country" TEXT NOT NULL DEFAULT 'US',
  "industry" TEXT,
  "notes" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "sourcing_iso_partner_id" TEXT,
  PRIMARY KEY ("id"),
  CONSTRAINT "merchants_status_check" CHECK ((status IN ('active', 'suspended', 'defaulted', 'closed'))),
  FOREIGN KEY ("sourcing_iso_partner_id") REFERENCES "iso_partners" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "agent_runs" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "employee" TEXT NOT NULL,
  "trigger" TEXT NOT NULL DEFAULT 'cron',
  "status" TEXT NOT NULL DEFAULT 'running',
  "merchant_id" TEXT,
  "started_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "finished_at" TEXT,
  "summary" TEXT,
  "artifact_type" TEXT,
  "artifact_id" TEXT,
  "error" TEXT,
  "meta_json" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "agent_runs_status_check" CHECK ((status IN ('queued', 'running', 'succeeded', 'failed', 'skipped'))),
  FOREIGN KEY ("merchant_id") REFERENCES "merchants" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "bank_accounts" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "merchant_id" TEXT NOT NULL,
  "plaid_item_id" TEXT,
  "plaid_account_id" TEXT,
  "institution_name" TEXT,
  "institution_logo_url" TEXT,
  "mask" TEXT,
  "account_type" TEXT,
  "account_subtype" TEXT,
  "encrypted_access_token" TEXT,
  "manual_routing_last4" TEXT,
  "manual_account_last4" TEXT,
  "verified_at" TEXT,
  "status" TEXT NOT NULL DEFAULT 'active',
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "bank_accounts_status_check" CHECK ((status IN ('active', 'revoked', 'error', 'pending_verification'))),
  FOREIGN KEY ("merchant_id") REFERENCES "merchants" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "chat_conversations" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "owner_kind" TEXT NOT NULL,
  "merchant_id" TEXT,
  "tenant_user_id" TEXT,
  "title" TEXT NOT NULL DEFAULT 'New chat',
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "chat_conversations_owner_kind_check" CHECK ((owner_kind IN ('merchant', 'funder'))),
  FOREIGN KEY ("merchant_id") REFERENCES "merchants" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id"),
  FOREIGN KEY ("tenant_user_id") REFERENCES "tenant_users" ("id")
);

CREATE TABLE IF NOT EXISTS "historical_deals" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "import_batch" TEXT,
  "source" TEXT NOT NULL DEFAULT 'sheet',
  "business_name" TEXT NOT NULL,
  "industry" TEXT,
  "state_region" TEXT,
  "iso_name" TEXT,
  "funded_on" TEXT,
  "advance_amount_cents" INTEGER,
  "factor_rate" TEXT,
  "term_days" INTEGER,
  "payment_frequency" TEXT,
  "outcome" TEXT NOT NULL DEFAULT 'unknown',
  "defaulted_on" TEXT,
  "renewal_count" INTEGER,
  "total_repaid_cents" INTEGER,
  "recovered_cents" INTEGER,
  "avg_daily_balance_cents" INTEGER,
  "ending_balance_cents" INTEGER,
  "nsf_count_90d" INTEGER,
  "negative_days_90d" INTEGER,
  "deposits_monthly_cents" INTEGER,
  "deposit_count_monthly" INTEGER,
  "position_count" INTEGER,
  "notes" TEXT,
  "raw_json" TEXT,
  "merchant_id" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "iso_partner_id" TEXT,
  PRIMARY KEY ("id"),
  CONSTRAINT "historical_deals_advance_amount_cents_check" CHECK (((advance_amount_cents IS NULL) OR (advance_amount_cents > 0))),
  CONSTRAINT "historical_deals_factor_rate_check" CHECK (((factor_rate IS NULL) OR ((factor_rate >= 1.000) AND (factor_rate <= 1.999)))),
  CONSTRAINT "historical_deals_outcome_check" CHECK ((outcome IN ('active', 'paid_off', 'renewed', 'defaulted', 'settled', 'written_off', 'unknown'))),
  CONSTRAINT "historical_deals_payment_frequency_check" CHECK (((payment_frequency IS NULL) OR (payment_frequency IN ('daily', 'weekly', 'biweekly', 'monthly')))),
  CONSTRAINT "historical_deals_recovered_cents_check" CHECK (((recovered_cents IS NULL) OR (recovered_cents >= 0))),
  CONSTRAINT "historical_deals_renewal_count_check" CHECK (((renewal_count IS NULL) OR (renewal_count >= 0))),
  CONSTRAINT "historical_deals_term_days_check" CHECK (((term_days IS NULL) OR ((term_days >= 1) AND (term_days <= 1080)))),
  CONSTRAINT "historical_deals_total_repaid_cents_check" CHECK (((total_repaid_cents IS NULL) OR (total_repaid_cents >= 0))),
  FOREIGN KEY ("iso_partner_id") REFERENCES "iso_partners" ("id"),
  FOREIGN KEY ("merchant_id") REFERENCES "merchants" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "merchant_users" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "merchant_id" TEXT NOT NULL,
  "auth_user_id" TEXT NOT NULL,
  "email" TEXT NOT NULL,
  "full_name" TEXT,
  "role" TEXT NOT NULL,
  "invited_by" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "merchant_users_role_check" CHECK ((role IN ('owner', 'staff'))),
  FOREIGN KEY ("merchant_id") REFERENCES "merchants" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "plaid_items" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "merchant_id" TEXT NOT NULL,
  "attempt_id" TEXT NOT NULL,
  "plaid_item_id" TEXT NOT NULL,
  "encrypted_access_token" TEXT NOT NULL,
  "institution_id" TEXT,
  "institution_name" TEXT,
  "status" TEXT NOT NULL DEFAULT 'pending',
  "retry_count" INTEGER NOT NULL DEFAULT 0,
  "last_attempt_at" TEXT,
  "last_error" TEXT,
  "completed_at" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "plaid_items_retry_count_check" CHECK ((retry_count >= 0)),
  CONSTRAINT "plaid_items_status_check" CHECK ((status IN ('pending', 'active', 'error', 'revoked'))),
  FOREIGN KEY ("merchant_id") REFERENCES "merchants" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "plaid_link_events" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "merchant_id" TEXT NOT NULL,
  "event" TEXT NOT NULL,
  "institution_id" TEXT,
  "institution_name" TEXT,
  "request_id" TEXT,
  "error_code" TEXT,
  "error_type" TEXT,
  "error_message" TEXT,
  "link_session_id" TEXT,
  "view_name" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("merchant_id") REFERENCES "merchants" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "plaid_statement_requests" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "merchant_id" TEXT NOT NULL,
  "plaid_item_id" TEXT NOT NULL,
  "requested_by_user_id" TEXT,
  "start_date" TEXT NOT NULL,
  "end_date" TEXT NOT NULL,
  "status" TEXT NOT NULL DEFAULT 'pending_consent',
  "plaid_request_id" TEXT,
  "statement_count" INTEGER NOT NULL DEFAULT 0,
  "last_error" TEXT,
  "completed_at" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "attempt_count" INTEGER NOT NULL DEFAULT 0,
  "next_attempt_at" TEXT,
  PRIMARY KEY ("id"),
  CONSTRAINT "plaid_statement_requests_attempt_count_check" CHECK ((attempt_count >= 0)),
  CONSTRAINT "plaid_statement_requests_check" CHECK ((start_date <= end_date)),
  CONSTRAINT "plaid_statement_requests_statement_count_check" CHECK ((statement_count >= 0)),
  CONSTRAINT "plaid_statement_requests_status_check" CHECK ((status IN ('pending_consent', 'starting_refresh', 'refreshing', 'callback_missing', 'ready', 'processing', 'completed', 'error'))),
  FOREIGN KEY ("merchant_id") REFERENCES "merchants" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "position_summaries" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "merchant_id" TEXT NOT NULL,
  "avg_monthly_revenue_cents" INTEGER,
  "total_monthly_pull_cents" INTEGER,
  "leverage_pct" TEXT,
  "position_count" INTEGER NOT NULL DEFAULT 0,
  "next_deposit_label" TEXT,
  "next_deposit_approx_cents" INTEGER,
  "pricing_note" TEXT,
  "as_of" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("merchant_id") REFERENCES "merchants" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "sequence_state" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "sequence_id" TEXT NOT NULL,
  "merchant_id" TEXT NOT NULL,
  "current_step" INTEGER NOT NULL DEFAULT 0,
  "status" TEXT NOT NULL DEFAULT 'active',
  "enrolled_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "next_run_at" TEXT,
  "last_step_at" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "meta_json" TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY ("id"),
  CONSTRAINT "sequence_state_status_check" CHECK ((status IN ('active', 'paused', 'completed', 'cancelled'))),
  FOREIGN KEY ("merchant_id") REFERENCES "merchants" ("id"),
  FOREIGN KEY ("sequence_id") REFERENCES "sequences" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "advances" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "merchant_id" TEXT NOT NULL,
  "advance_amount_cents" INTEGER NOT NULL,
  "factor_rate" TEXT NOT NULL,
  "term_days" INTEGER NOT NULL,
  "daily_holdback_pct" TEXT NOT NULL,
  "funded_at" TEXT,
  "source_bank_account_id" TEXT,
  "repayment_status" TEXT NOT NULL DEFAULT 'pending',
  "lender_ref_id" TEXT,
  "notes" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "origination_fee_pct" TEXT NOT NULL DEFAULT 0,
  "monthly_rate_pct" TEXT NOT NULL DEFAULT 0,
  "term_months" INTEGER NOT NULL DEFAULT 0,
  "uw_revenue_min_cents" INTEGER,
  "uw_revenue_max_cents" INTEGER,
  "uw_daily_balance_min_cents" INTEGER,
  "uw_max_positions" INTEGER,
  "uw_max_negative_days" INTEGER,
  "requires_monthly_ar" INTEGER NOT NULL DEFAULT 0,
  "defaulted_at" TEXT,
  "charged_off_at" TEXT,
  "settled_at" TEXT,
  "settled_amount_cents" INTEGER,
  "recovered_cents" INTEGER NOT NULL DEFAULT 0,
  "renewal_of_advance_id" TEXT,
  "collection_status" TEXT NOT NULL DEFAULT 'none',
  "iso_partner_id" TEXT,
  "iso_commission_pct" TEXT,
  "iso_attributed_at" TEXT,
  "client_key" TEXT,
  PRIMARY KEY ("id"),
  CONSTRAINT "advances_advance_amount_cents_check" CHECK ((advance_amount_cents > 0)),
  CONSTRAINT "advances_collection_status_check" CHECK ((collection_status IN ('none', 'in_house', 'agency', 'legal', 'settled', 'written_off'))),
  CONSTRAINT "advances_daily_holdback_pct_check" CHECK (((daily_holdback_pct >= (0)) AND (daily_holdback_pct <= 0.50))),
  CONSTRAINT "advances_factor_rate_check" CHECK (((factor_rate >= 1.000) AND (factor_rate <= 4.000))),
  CONSTRAINT "advances_iso_commission_pct_check" CHECK (((iso_commission_pct IS NULL) OR ((iso_commission_pct >= (0)) AND (iso_commission_pct <= 0.25)))),
  CONSTRAINT "advances_monthly_rate_pct_check" CHECK (((monthly_rate_pct >= (0)) AND (monthly_rate_pct <= 0.20))),
  CONSTRAINT "advances_origination_fee_pct_check" CHECK (((origination_fee_pct >= (0)) AND (origination_fee_pct <= 0.20))),
  CONSTRAINT "advances_recovered_cents_check" CHECK ((recovered_cents >= 0)),
  CONSTRAINT "advances_repayment_status_check" CHECK ((repayment_status IN ('pending', 'active', 'completed', 'default', 'closed'))),
  CONSTRAINT "advances_settled_amount_cents_check" CHECK (((settled_amount_cents IS NULL) OR (settled_amount_cents >= 0))),
  CONSTRAINT "advances_term_days_check" CHECK (((term_days >= 30) AND (term_days <= 1110))),
  CONSTRAINT "advances_term_months_check" CHECK (((term_months >= 0) AND (term_months <= 36))),
  FOREIGN KEY ("iso_partner_id") REFERENCES "iso_partners" ("id"),
  FOREIGN KEY ("merchant_id") REFERENCES "merchants" ("id"),
  FOREIGN KEY ("renewal_of_advance_id") REFERENCES "advances" ("id"),
  FOREIGN KEY ("source_bank_account_id") REFERENCES "bank_accounts" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "chat_messages" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "conversation_id" TEXT NOT NULL,
  "tenant_id" TEXT NOT NULL,
  "role" TEXT NOT NULL,
  "content" TEXT NOT NULL DEFAULT '',
  "tool_calls" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "chat_messages_role_check" CHECK ((role IN ('user', 'assistant'))),
  FOREIGN KEY ("conversation_id") REFERENCES "chat_conversations" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "interactions" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "merchant_id" TEXT,
  "channel" TEXT NOT NULL,
  "direction" TEXT NOT NULL DEFAULT 'outbound',
  "to_address" TEXT,
  "subject" TEXT,
  "body_preview" TEXT,
  "status" TEXT NOT NULL DEFAULT 'queued',
  "sequence_id" TEXT,
  "agent_run_id" TEXT,
  "external_id" TEXT,
  "error" TEXT,
  "sent_at" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "interactions_channel_check" CHECK ((channel IN ('email', 'sms'))),
  CONSTRAINT "interactions_direction_check" CHECK ((direction IN ('outbound', 'inbound'))),
  CONSTRAINT "interactions_status_check" CHECK ((status IN ('queued', 'sent', 'delivered', 'failed', 'suppressed', 'bounced'))),
  FOREIGN KEY ("agent_run_id") REFERENCES "agent_runs" ("id"),
  FOREIGN KEY ("merchant_id") REFERENCES "merchants" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "plaid_statement_link_tokens" (
  "request_id" TEXT NOT NULL,
  "encrypted_link_token" TEXT,
  "expires_at" TEXT,
  "lease_id" TEXT,
  "lease_at" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("request_id"),
  CONSTRAINT "plaid_statement_link_tokens_check" CHECK (((lease_id IS NULL) = (lease_at IS NULL))),
  FOREIGN KEY ("request_id") REFERENCES "plaid_statement_requests" ("id")
);

CREATE TABLE IF NOT EXISTS "plaid_transactions" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "merchant_id" TEXT NOT NULL,
  "bank_account_id" TEXT,
  "plaid_item_id" TEXT NOT NULL,
  "plaid_account_id" TEXT NOT NULL,
  "plaid_transaction_id" TEXT NOT NULL,
  "amount_cents" INTEGER NOT NULL,
  "posted_on" TEXT NOT NULL,
  "name" TEXT,
  "merchant_name" TEXT,
  "pfc_primary" TEXT,
  "pfc_detailed" TEXT,
  "pending" INTEGER NOT NULL DEFAULT 0,
  "raw_json" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("bank_account_id") REFERENCES "bank_accounts" ("id"),
  FOREIGN KEY ("merchant_id") REFERENCES "merchants" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "position_account_months" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "merchant_id" TEXT NOT NULL,
  "bank_account_id" TEXT,
  "account_label" TEXT NOT NULL,
  "month" TEXT NOT NULL,
  "revenue_cents" INTEGER NOT NULL DEFAULT 0,
  "avg_balance_cents" INTEGER,
  "negative_days" INTEGER,
  "is_mtd" INTEGER NOT NULL DEFAULT 0,
  "no_additional_activity" INTEGER NOT NULL DEFAULT 0,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("bank_account_id") REFERENCES "bank_accounts" ("id"),
  FOREIGN KEY ("merchant_id") REFERENCES "merchants" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "board_items" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "board_id" TEXT NOT NULL,
  "group_id" TEXT,
  "name" TEXT NOT NULL,
  "position" TEXT NOT NULL DEFAULT 1000,
  "merchant_id" TEXT,
  "advance_id" TEXT,
  "external_ref" TEXT,
  "archived" INTEGER NOT NULL DEFAULT 0,
  "created_by" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("advance_id") REFERENCES "advances" ("id"),
  FOREIGN KEY ("board_id") REFERENCES "boards" ("id"),
  FOREIGN KEY ("group_id") REFERENCES "board_groups" ("id"),
  FOREIGN KEY ("merchant_id") REFERENCES "merchants" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "draw_requests" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "advance_id" TEXT NOT NULL,
  "merchant_id" TEXT NOT NULL,
  "requested_cents" INTEGER NOT NULL,
  "approved_cents" INTEGER,
  "status" TEXT NOT NULL DEFAULT 'pending',
  "submitted_by_user_id" TEXT,
  "submitted_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "decided_at" TEXT,
  "decided_by_user_id" TEXT,
  "decision_note" TEXT,
  "purpose" TEXT,
  "merchant_note" TEXT,
  "bank_account_id" TEXT,
  "idempotency_key" TEXT NOT NULL,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "estimated_fee_cents" INTEGER,
  PRIMARY KEY ("id"),
  CONSTRAINT "draw_requests_approved_cents_check" CHECK (((approved_cents IS NULL) OR (approved_cents > 0))),
  CONSTRAINT "draw_requests_estimated_fee_cents_check" CHECK (((estimated_fee_cents IS NULL) OR (estimated_fee_cents >= 0))),
  CONSTRAINT "draw_requests_requested_cents_check" CHECK ((requested_cents > 0)),
  CONSTRAINT "draw_requests_status_check" CHECK ((status IN ('pending', 'approved', 'awaiting_signature', 'denied', 'funded', 'cancelled'))),
  FOREIGN KEY ("advance_id") REFERENCES "advances" ("id"),
  FOREIGN KEY ("bank_account_id") REFERENCES "bank_accounts" ("id"),
  FOREIGN KEY ("merchant_id") REFERENCES "merchants" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "mca_positions" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "merchant_id" TEXT NOT NULL,
  "advance_id" TEXT,
  "funder" TEXT NOT NULL,
  "amount_cents" INTEGER,
  "payment_cents" INTEGER,
  "frequency" TEXT,
  "term_label" TEXT,
  "is_new" INTEGER NOT NULL DEFAULT 0,
  "is_renewal" INTEGER NOT NULL DEFAULT 0,
  "pulls_pending" INTEGER NOT NULL DEFAULT 0,
  "note" TEXT,
  "note_severity" TEXT NOT NULL DEFAULT 'info',
  "detected_from" TEXT NOT NULL DEFAULT 'manual',
  "observed_on" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "mca_positions_detected_from_check" CHECK ((detected_from IN ('plaid', 'manual', 'moneythumb', 'email'))),
  CONSTRAINT "mca_positions_frequency_check" CHECK ((frequency IN ('daily', 'weekly', 'biweekly', 'monthly'))),
  CONSTRAINT "mca_positions_note_severity_check" CHECK ((note_severity IN ('info', 'risk'))),
  FOREIGN KEY ("advance_id") REFERENCES "advances" ("id"),
  FOREIGN KEY ("merchant_id") REFERENCES "merchants" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "draws" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "draw_request_id" TEXT NOT NULL,
  "advance_id" TEXT NOT NULL,
  "merchant_id" TEXT NOT NULL,
  "funded_cents" INTEGER NOT NULL,
  "funded_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "bank_account_id" TEXT,
  "lender_ref_id" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "platform_fee_cents" INTEGER NOT NULL DEFAULT 0,
  "net_deposit_cents" INTEGER,
  "origination_fee_pct" TEXT NOT NULL DEFAULT 0,
  "monthly_rate_pct" TEXT NOT NULL DEFAULT 0,
  "term_months" INTEGER NOT NULL DEFAULT 0,
  "total_repayment_cents" INTEGER NOT NULL DEFAULT 0,
  "disbursement_status" TEXT NOT NULL DEFAULT 'pending',
  "disbursed_at" TEXT,
  "disbursed_by_user_id" TEXT,
  "disbursement_reference" TEXT,
  "disbursement_note" TEXT,
  "disbursement_notified_at" TEXT,
  PRIMARY KEY ("id"),
  CONSTRAINT "draws_disbursement_status_check" CHECK ((disbursement_status IN ('pending', 'disbursed'))),
  CONSTRAINT "draws_fee_within_funded" CHECK ((platform_fee_cents <= funded_cents)),
  CONSTRAINT "draws_funded_cents_check" CHECK ((funded_cents > 0)),
  CONSTRAINT "draws_platform_fee_cents_check" CHECK ((platform_fee_cents >= 0)),
  CONSTRAINT "draws_total_repayment_cents_check" CHECK ((total_repayment_cents >= 0)),
  FOREIGN KEY ("advance_id") REFERENCES "advances" ("id"),
  FOREIGN KEY ("bank_account_id") REFERENCES "bank_accounts" ("id"),
  FOREIGN KEY ("draw_request_id") REFERENCES "draw_requests" ("id"),
  FOREIGN KEY ("merchant_id") REFERENCES "merchants" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "item_column_values" (
  "item_id" TEXT NOT NULL,
  "column_id" TEXT NOT NULL,
  "tenant_id" TEXT NOT NULL,
  "value" TEXT NOT NULL DEFAULT '{}',
  "text_value" TEXT,
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("item_id", "column_id"),
  FOREIGN KEY ("column_id") REFERENCES "board_columns" ("id"),
  FOREIGN KEY ("item_id") REFERENCES "board_items" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "underwriting_snapshots" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "merchant_id" TEXT NOT NULL,
  "draw_request_id" TEXT,
  "configured" INTEGER NOT NULL DEFAULT 1,
  "pending" INTEGER NOT NULL DEFAULT 0,
  "current_balance_cents" INTEGER NOT NULL DEFAULT 0,
  "est_monthly_revenue_cents" INTEGER NOT NULL DEFAULT 0,
  "deposit_count_90d" INTEGER NOT NULL DEFAULT 0,
  "account_count" INTEGER NOT NULL DEFAULT 0,
  "error" TEXT,
  "verdict" TEXT,
  "indicators_json" TEXT,
  "as_of" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "underwriting_snapshots_verdict_check" CHECK ((verdict IN ('pass', 'review', 'unavailable'))),
  FOREIGN KEY ("draw_request_id") REFERENCES "draw_requests" ("id"),
  FOREIGN KEY ("merchant_id") REFERENCES "merchants" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "agreements" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "merchant_id" TEXT NOT NULL,
  "draw_request_id" TEXT NOT NULL,
  "advance_id" TEXT NOT NULL,
  "draw_id" TEXT,
  "status" TEXT NOT NULL DEFAULT 'pending_signature',
  "funded_cents" INTEGER NOT NULL,
  "origination_fee_cents" INTEGER NOT NULL DEFAULT 0,
  "net_funded_cents" INTEGER NOT NULL DEFAULT 0,
  "total_repayment_cents" INTEGER NOT NULL DEFAULT 0,
  "monthly_rate_pct" TEXT NOT NULL DEFAULT 0,
  "term_months" INTEGER NOT NULL DEFAULT 0,
  "contract_html" TEXT NOT NULL,
  "content_hash" TEXT NOT NULL,
  "storage_path" TEXT,
  "signer_name" TEXT,
  "signer_email" TEXT,
  "signed_at" TEXT,
  "signer_ip" TEXT,
  "signer_ua" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "signed_content_hash" TEXT,
  PRIMARY KEY ("id"),
  CONSTRAINT "agreements_status_check" CHECK ((status IN ('pending_signature', 'signed', 'voided'))),
  FOREIGN KEY ("advance_id") REFERENCES "advances" ("id"),
  FOREIGN KEY ("draw_id") REFERENCES "draws" ("id"),
  FOREIGN KEY ("draw_request_id") REFERENCES "draw_requests" ("id"),
  FOREIGN KEY ("merchant_id") REFERENCES "merchants" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "deal_memos" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "merchant_id" TEXT NOT NULL,
  "draw_request_id" TEXT,
  "advance_id" TEXT,
  "snapshot_id" TEXT,
  "grade" TEXT NOT NULL,
  "recommendation" TEXT NOT NULL,
  "memo_json" TEXT NOT NULL,
  "model" TEXT NOT NULL,
  "created_by" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "deal_memos_grade_check" CHECK ((grade IN ('A+', 'A', 'A-', 'B+', 'B', 'B-', 'C+', 'C', 'C-', 'D', 'F'))),
  CONSTRAINT "deal_memos_recommendation_check" CHECK ((recommendation IN ('approve', 'approve_with_conditions', 'decline', 'needs_info'))),
  FOREIGN KEY ("advance_id") REFERENCES "advances" ("id"),
  FOREIGN KEY ("draw_request_id") REFERENCES "draw_requests" ("id"),
  FOREIGN KEY ("merchant_id") REFERENCES "merchants" ("id"),
  FOREIGN KEY ("snapshot_id") REFERENCES "underwriting_snapshots" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "documents" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "merchant_id" TEXT NOT NULL,
  "advance_id" TEXT,
  "draw_id" TEXT,
  "kind" TEXT NOT NULL,
  "storage_path" TEXT NOT NULL,
  "file_name" TEXT NOT NULL,
  "mime_type" TEXT,
  "size_bytes" INTEGER,
  "period_label" TEXT,
  "uploaded_by_user_id" TEXT,
  "uploaded_by_role" TEXT NOT NULL DEFAULT 'merchant',
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "source" TEXT NOT NULL DEFAULT 'upload',
  "provider_document_id" TEXT,
  "plaid_item_id" TEXT,
  "period_start" TEXT,
  "period_end" TEXT,
  PRIMARY KEY ("id"),
  CONSTRAINT "documents_kind_check" CHECK ((kind IN ('bank_statement', 'ar', 'application', 'agreement', 'other'))),
  CONSTRAINT "documents_source_check" CHECK ((source IN ('upload', 'plaid_statements', 'plaid_asset_report'))),
  CONSTRAINT "documents_uploaded_by_role_check" CHECK ((uploaded_by_role IN ('merchant', 'lender_staff', 'system'))),
  FOREIGN KEY ("advance_id") REFERENCES "advances" ("id"),
  FOREIGN KEY ("draw_id") REFERENCES "draws" ("id"),
  FOREIGN KEY ("merchant_id") REFERENCES "merchants" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "iso_commissions" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "iso_partner_id" TEXT NOT NULL,
  "advance_id" TEXT NOT NULL,
  "draw_id" TEXT,
  "entry_type" TEXT NOT NULL DEFAULT 'commission',
  "basis_cents" INTEGER NOT NULL,
  "commission_pct" TEXT NOT NULL,
  "amount_cents" INTEGER NOT NULL,
  "status" TEXT NOT NULL DEFAULT 'accrued',
  "paid_at" TEXT,
  "note" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "iso_commissions_entry_type_check" CHECK ((entry_type IN ('commission', 'clawback', 'adjustment'))),
  CONSTRAINT "iso_commissions_status_check" CHECK ((status IN ('accrued', 'approved', 'paid', 'voided'))),
  FOREIGN KEY ("advance_id") REFERENCES "advances" ("id"),
  FOREIGN KEY ("draw_id") REFERENCES "draws" ("id"),
  FOREIGN KEY ("iso_partner_id") REFERENCES "iso_partners" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "platform_fee_ledger" (
  "id" INTEGER PRIMARY KEY,
  "tenant_id" TEXT NOT NULL,
  "draw_id" TEXT NOT NULL,
  "draw_request_id" TEXT NOT NULL,
  "advance_id" TEXT NOT NULL,
  "merchant_id" TEXT NOT NULL,
  "funded_cents" INTEGER NOT NULL,
  "fee_rate" TEXT NOT NULL,
  "fee_cap_cents" INTEGER,
  "fee_cents" INTEGER NOT NULL,
  "fee_label" TEXT,
  "recorded_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  CONSTRAINT "platform_fee_ledger_fee_cap_cents_check" CHECK (((fee_cap_cents IS NULL) OR (fee_cap_cents > 0))),
  CONSTRAINT "platform_fee_ledger_fee_cents_check" CHECK ((fee_cents >= 0)),
  CONSTRAINT "platform_fee_ledger_fee_rate_check" CHECK (((fee_rate >= (0)) AND (fee_rate <= 0.5000))),
  CONSTRAINT "platform_fee_ledger_funded_cents_check" CHECK ((funded_cents > 0)),
  FOREIGN KEY ("advance_id") REFERENCES "advances" ("id"),
  FOREIGN KEY ("draw_id") REFERENCES "draws" ("id"),
  FOREIGN KEY ("draw_request_id") REFERENCES "draw_requests" ("id"),
  FOREIGN KEY ("merchant_id") REFERENCES "merchants" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "repayments" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "advance_id" TEXT NOT NULL,
  "merchant_id" TEXT NOT NULL,
  "amount_cents" INTEGER NOT NULL,
  "recorded_at" TEXT NOT NULL,
  "source" TEXT NOT NULL,
  "external_id" TEXT,
  "note" TEXT,
  "recorded_by_user_id" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "draw_id" TEXT,
  PRIMARY KEY ("id"),
  CONSTRAINT "repayments_amount_cents_check" CHECK ((amount_cents <> 0)),
  CONSTRAINT "repayments_source_check" CHECK ((source IN ('ach', 'manual', 'adjustment', 'wire'))),
  FOREIGN KEY ("advance_id") REFERENCES "advances" ("id"),
  FOREIGN KEY ("draw_id") REFERENCES "draws" ("id"),
  FOREIGN KEY ("merchant_id") REFERENCES "merchants" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

-- indexes
CREATE UNIQUE INDEX IF NOT EXISTS "repayments_pkey" ON "repayments" (id);
CREATE INDEX IF NOT EXISTS "repayments_tenant_idx" ON "repayments" (tenant_id);
CREATE INDEX IF NOT EXISTS "repayments_advance_idx" ON "repayments" (advance_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS "repayments_merchant_idx" ON "repayments" (merchant_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS "repayments_recorded_day_idx" ON "repayments" (advance_id, (((recorded_at AT TIME ZONE 'UTC'))));
CREATE UNIQUE INDEX IF NOT EXISTS "repayments_external_id_idx" ON "repayments" (advance_id, external_id) WHERE (external_id IS NOT NULL);
CREATE INDEX IF NOT EXISTS "repayments_draw_idx" ON "repayments" (draw_id, recorded_at DESC) WHERE (draw_id IS NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS "bank_accounts_pkey" ON "bank_accounts" (id);
CREATE INDEX IF NOT EXISTS "bank_accounts_tenant_idx" ON "bank_accounts" (tenant_id);
CREATE INDEX IF NOT EXISTS "bank_accounts_merchant_idx" ON "bank_accounts" (merchant_id);
CREATE UNIQUE INDEX IF NOT EXISTS "bank_accounts_plaid_unique" ON "bank_accounts" (merchant_id, plaid_account_id) WHERE (plaid_account_id IS NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS "bank_accounts_merchant_plaid_account_uidx" ON "bank_accounts" (merchant_id, plaid_account_id);
CREATE UNIQUE INDEX IF NOT EXISTS "tenant_draw_notifiers_pkey" ON "tenant_draw_notifiers" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "tenant_draw_notifiers_tenant_email_uidx" ON "tenant_draw_notifiers" (tenant_id, lower(trim(email)));
CREATE INDEX IF NOT EXISTS "tenant_draw_notifiers_active_idx" ON "tenant_draw_notifiers" (tenant_id) WHERE active;
CREATE UNIQUE INDEX IF NOT EXISTS "audit_log_pkey" ON "audit_log" (id);
CREATE INDEX IF NOT EXISTS "audit_log_tenant_entity_idx" ON "audit_log" (tenant_id, entity_type, entity_id);
CREATE INDEX IF NOT EXISTS "audit_log_tenant_at_idx" ON "audit_log" (tenant_id, at DESC);
CREATE INDEX IF NOT EXISTS "audit_log_actor_idx" ON "audit_log" (actor_id, at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "email_suppressions_pkey" ON "email_suppressions" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "email_suppressions_email_tenant_id_brand_key" ON "email_suppressions" (COALESCE(email, '\u001f__null__'), COALESCE(tenant_id, '\u001f__null__'), COALESCE(brand, '\u001f__null__'));
CREATE INDEX IF NOT EXISTS "email_suppressions_email_idx" ON "email_suppressions" (lower(email));
CREATE INDEX IF NOT EXISTS "email_suppressions_tenant_idx" ON "email_suppressions" (tenant_id);
CREATE UNIQUE INDEX IF NOT EXISTS "webhook_events_pkey" ON "webhook_events" (id);
CREATE INDEX IF NOT EXISTS "webhook_events_tenant_idx" ON "webhook_events" (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS "webhook_events_status_idx" ON "webhook_events" (tenant_id, status, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "webhook_events_external_id_idx" ON "webhook_events" (tenant_id, provider, external_id) WHERE ((external_id IS NOT NULL) AND (direction = 'inbound'));
CREATE UNIQUE INDEX IF NOT EXISTS "documents_pkey" ON "documents" (id);
CREATE INDEX IF NOT EXISTS "documents_tenant_idx" ON "documents" (tenant_id);
CREATE INDEX IF NOT EXISTS "documents_merchant_idx" ON "documents" (merchant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS "documents_kind_idx" ON "documents" (merchant_id, kind, period_label);
CREATE INDEX IF NOT EXISTS "documents_draw_idx" ON "documents" (draw_id) WHERE (draw_id IS NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS "documents_provider_uidx" ON "documents" (tenant_id, source, provider_document_id);
CREATE UNIQUE INDEX IF NOT EXISTS "advances_pkey" ON "advances" (id);
CREATE INDEX IF NOT EXISTS "advances_tenant_idx" ON "advances" (tenant_id);
CREATE INDEX IF NOT EXISTS "advances_merchant_idx" ON "advances" (merchant_id);
CREATE INDEX IF NOT EXISTS "advances_status_idx" ON "advances" (tenant_id, repayment_status);
CREATE UNIQUE INDEX IF NOT EXISTS "advances_lender_ref_idx" ON "advances" (tenant_id, lender_ref_id) WHERE (lender_ref_id IS NOT NULL);
CREATE INDEX IF NOT EXISTS "advances_renewal_of_idx" ON "advances" (renewal_of_advance_id) WHERE (renewal_of_advance_id IS NOT NULL);
CREATE INDEX IF NOT EXISTS "advances_collections_idx" ON "advances" (tenant_id, collection_status) WHERE (collection_status <> 'none');
CREATE INDEX IF NOT EXISTS "advances_defaulted_at_idx" ON "advances" (tenant_id, defaulted_at) WHERE (defaulted_at IS NOT NULL);
CREATE INDEX IF NOT EXISTS "advances_iso_idx" ON "advances" (iso_partner_id) WHERE (iso_partner_id IS NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS "advances_tenant_client_key_uk" ON "advances" (tenant_id, client_key) WHERE (client_key IS NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS "agreements_pkey" ON "agreements" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "agreements_draw_request_id_key" ON "agreements" (draw_request_id);
CREATE INDEX IF NOT EXISTS "agreements_tenant_idx" ON "agreements" (tenant_id);
CREATE INDEX IF NOT EXISTS "agreements_merchant_idx" ON "agreements" (merchant_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "merchants_pkey" ON "merchants" (id);
CREATE INDEX IF NOT EXISTS "merchants_tenant_idx" ON "merchants" (tenant_id);
CREATE INDEX IF NOT EXISTS "merchants_status_idx" ON "merchants" (tenant_id, status);
CREATE INDEX IF NOT EXISTS "merchants_business_idx" ON "merchants" (tenant_id, business_name);
CREATE UNIQUE INDEX IF NOT EXISTS "merchants_tenant_email_lower_uidx" ON "merchants" (tenant_id, lower(trim(primary_contact_email))) WHERE (primary_contact_email IS NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS "merchants_tenant_name_lower_uidx" ON "merchants" (tenant_id, lower(trim(business_name)));
CREATE UNIQUE INDEX IF NOT EXISTS "underwriting_snapshots_pkey" ON "underwriting_snapshots" (id);
CREATE INDEX IF NOT EXISTS "uw_snapshots_merchant_idx" ON "underwriting_snapshots" (merchant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS "uw_snapshots_tenant_idx" ON "underwriting_snapshots" (tenant_id);
CREATE INDEX IF NOT EXISTS "uw_snapshots_draw_idx" ON "underwriting_snapshots" (draw_request_id) WHERE (draw_request_id IS NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS "tenants_pkey" ON "tenants" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "tenants_slug_key" ON "tenants" (slug);
CREATE INDEX IF NOT EXISTS "tenants_slug_idx" ON "tenants" (slug);
CREATE UNIQUE INDEX IF NOT EXISTS "platform_fee_ledger_pkey" ON "platform_fee_ledger" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "platform_fee_ledger_draw_id_key" ON "platform_fee_ledger" (draw_id);
CREATE INDEX IF NOT EXISTS "platform_fee_ledger_tenant_recorded_idx" ON "platform_fee_ledger" (tenant_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS "platform_fee_ledger_advance_idx" ON "platform_fee_ledger" (advance_id);
CREATE INDEX IF NOT EXISTS "platform_fee_ledger_merchant_idx" ON "platform_fee_ledger" (merchant_id);
CREATE UNIQUE INDEX IF NOT EXISTS "tenant_users_pkey" ON "tenant_users" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "tenant_users_tenant_id_auth_user_id_key" ON "tenant_users" (tenant_id, auth_user_id);
CREATE INDEX IF NOT EXISTS "tenant_users_tenant_idx" ON "tenant_users" (tenant_id);
CREATE INDEX IF NOT EXISTS "tenant_users_auth_idx" ON "tenant_users" (auth_user_id);
CREATE UNIQUE INDEX IF NOT EXISTS "merchant_users_pkey" ON "merchant_users" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "merchant_users_merchant_id_auth_user_id_key" ON "merchant_users" (merchant_id, auth_user_id);
CREATE INDEX IF NOT EXISTS "merchant_users_tenant_idx" ON "merchant_users" (tenant_id);
CREATE INDEX IF NOT EXISTS "merchant_users_merchant_idx" ON "merchant_users" (merchant_id);
CREATE INDEX IF NOT EXISTS "merchant_users_auth_idx" ON "merchant_users" (auth_user_id);
CREATE UNIQUE INDEX IF NOT EXISTS "chat_conversations_pkey" ON "chat_conversations" (id);
CREATE INDEX IF NOT EXISTS "chat_conversations_merchant_idx" ON "chat_conversations" (merchant_id, updated_at DESC) WHERE (merchant_id IS NOT NULL);
CREATE INDEX IF NOT EXISTS "chat_conversations_funder_idx" ON "chat_conversations" (tenant_id, tenant_user_id, updated_at DESC) WHERE (owner_kind = 'funder');
CREATE UNIQUE INDEX IF NOT EXISTS "chat_messages_pkey" ON "chat_messages" (id);
CREATE INDEX IF NOT EXISTS "chat_messages_conversation_idx" ON "chat_messages" (conversation_id, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS "draws_pkey" ON "draws" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "draws_draw_request_id_key" ON "draws" (draw_request_id);
CREATE INDEX IF NOT EXISTS "draws_tenant_idx" ON "draws" (tenant_id);
CREATE INDEX IF NOT EXISTS "draws_advance_idx" ON "draws" (advance_id);
CREATE INDEX IF NOT EXISTS "draws_merchant_idx" ON "draws" (merchant_id);
CREATE INDEX IF NOT EXISTS "draws_funded_idx" ON "draws" (tenant_id, funded_at DESC);
CREATE INDEX IF NOT EXISTS "draws_pending_disbursement_idx" ON "draws" (tenant_id, disbursement_status) WHERE (disbursement_status = 'pending');
CREATE UNIQUE INDEX IF NOT EXISTS "draw_requests_pkey" ON "draw_requests" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "draw_requests_tenant_id_idempotency_key_key" ON "draw_requests" (tenant_id, idempotency_key);
CREATE INDEX IF NOT EXISTS "draw_requests_tenant_idx" ON "draw_requests" (tenant_id);
CREATE INDEX IF NOT EXISTS "draw_requests_advance_idx" ON "draw_requests" (advance_id);
CREATE INDEX IF NOT EXISTS "draw_requests_merchant_idx" ON "draw_requests" (merchant_id);
CREATE INDEX IF NOT EXISTS "draw_requests_status_idx" ON "draw_requests" (tenant_id, status, submitted_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "plaid_link_events_pkey" ON "plaid_link_events" (id);
CREATE INDEX IF NOT EXISTS "plaid_link_events_merchant_idx" ON "plaid_link_events" (tenant_id, merchant_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "mca_positions_pkey" ON "mca_positions" (id);
CREATE INDEX IF NOT EXISTS "mca_positions_merchant_idx" ON "mca_positions" (merchant_id, observed_on DESC);
CREATE INDEX IF NOT EXISTS "mca_positions_advance_idx" ON "mca_positions" (advance_id);
CREATE UNIQUE INDEX IF NOT EXISTS "position_account_months_pkey" ON "position_account_months" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "position_account_months_by_account" ON "position_account_months" (tenant_id, bank_account_id, month) WHERE (bank_account_id IS NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS "position_account_months_by_label" ON "position_account_months" (tenant_id, merchant_id, account_label, month) WHERE (bank_account_id IS NULL);
CREATE UNIQUE INDEX IF NOT EXISTS "position_summaries_pkey" ON "position_summaries" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "position_summaries_merchant_unique" ON "position_summaries" (tenant_id, merchant_id);
CREATE UNIQUE INDEX IF NOT EXISTS "historical_deals_pkey" ON "historical_deals" (id);
CREATE INDEX IF NOT EXISTS "historical_deals_tenant_outcome_idx" ON "historical_deals" (tenant_id, outcome);
CREATE INDEX IF NOT EXISTS "historical_deals_industry_idx" ON "historical_deals" (tenant_id, industry);
CREATE INDEX IF NOT EXISTS "historical_deals_batch_idx" ON "historical_deals" (tenant_id, import_batch);
CREATE INDEX IF NOT EXISTS "historical_deals_iso_idx" ON "historical_deals" (iso_partner_id) WHERE (iso_partner_id IS NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS "plaid_transactions_pkey" ON "plaid_transactions" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "plaid_tx_unique" ON "plaid_transactions" (tenant_id, plaid_transaction_id);
CREATE INDEX IF NOT EXISTS "plaid_tx_merchant_date_idx" ON "plaid_transactions" (merchant_id, posted_on DESC);
CREATE INDEX IF NOT EXISTS "plaid_tx_item_idx" ON "plaid_transactions" (plaid_item_id);
CREATE UNIQUE INDEX IF NOT EXISTS "plaid_sync_state_pkey" ON "plaid_sync_state" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "plaid_sync_state_item_unique" ON "plaid_sync_state" (tenant_id, plaid_item_id);
CREATE UNIQUE INDEX IF NOT EXISTS "kb_chunks_pkey" ON "kb_chunks" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "kb_chunks_doc_idx" ON "kb_chunks" (document_id, chunk_index);
CREATE INDEX IF NOT EXISTS "kb_chunks_tenant_idx" ON "kb_chunks" (tenant_id);
CREATE UNIQUE INDEX IF NOT EXISTS "deal_memos_pkey" ON "deal_memos" (id);
CREATE INDEX IF NOT EXISTS "deal_memos_tenant_idx" ON "deal_memos" (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS "deal_memos_draw_idx" ON "deal_memos" (draw_request_id) WHERE (draw_request_id IS NOT NULL);
CREATE INDEX IF NOT EXISTS "deal_memos_merchant_idx" ON "deal_memos" (merchant_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "kb_documents_pkey" ON "kb_documents" (id);
CREATE INDEX IF NOT EXISTS "kb_documents_tenant_idx" ON "kb_documents" (tenant_id, status);
CREATE UNIQUE INDEX IF NOT EXISTS "iso_commissions_pkey" ON "iso_commissions" (id);
CREATE INDEX IF NOT EXISTS "iso_commissions_partner_idx" ON "iso_commissions" (iso_partner_id, created_at DESC);
CREATE INDEX IF NOT EXISTS "iso_commissions_tenant_idx" ON "iso_commissions" (tenant_id, status, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "iso_commissions_draw_accrual_unique" ON "iso_commissions" (draw_id) WHERE ((entry_type = 'commission') AND (draw_id IS NOT NULL));
CREATE UNIQUE INDEX IF NOT EXISTS "iso_commissions_draw_clawback_unique" ON "iso_commissions" (draw_id) WHERE ((entry_type = 'clawback') AND (draw_id IS NOT NULL));
CREATE UNIQUE INDEX IF NOT EXISTS "interactions_pkey" ON "interactions" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "interactions_tenant_id_external_id_key" ON "interactions" (tenant_id, external_id);
CREATE INDEX IF NOT EXISTS "interactions_tenant_idx" ON "interactions" (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS "interactions_merchant_idx" ON "interactions" (merchant_id, created_at DESC) WHERE (merchant_id IS NOT NULL);
CREATE INDEX IF NOT EXISTS "interactions_sequence_idx" ON "interactions" (sequence_id, created_at DESC) WHERE (sequence_id IS NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS "agent_runs_pkey" ON "agent_runs" (id);
CREATE INDEX IF NOT EXISTS "agent_runs_tenant_idx" ON "agent_runs" (tenant_id, started_at DESC);
CREATE INDEX IF NOT EXISTS "agent_runs_employee_idx" ON "agent_runs" (tenant_id, employee, started_at DESC);
CREATE INDEX IF NOT EXISTS "agent_runs_status_idx" ON "agent_runs" (tenant_id, status) WHERE (status IN ('queued', 'running', 'failed'));
CREATE INDEX IF NOT EXISTS "agent_runs_merchant_idx" ON "agent_runs" (merchant_id, started_at DESC) WHERE (merchant_id IS NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS "sequences_pkey" ON "sequences" (id);
CREATE INDEX IF NOT EXISTS "sequences_tenant_idx" ON "sequences" (tenant_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "iso_partners_pkey" ON "iso_partners" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "iso_partners_name_unique" ON "iso_partners" (tenant_id, lower(name));
CREATE UNIQUE INDEX IF NOT EXISTS "message_templates_pkey" ON "message_templates" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "message_templates_key_unique" ON "message_templates" (tenant_id, key);
CREATE UNIQUE INDEX IF NOT EXISTS "sequence_state_pkey" ON "sequence_state" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "sequence_state_sequence_id_merchant_id_key" ON "sequence_state" (sequence_id, merchant_id);
CREATE INDEX IF NOT EXISTS "sequence_state_due_idx" ON "sequence_state" (tenant_id, next_run_at) WHERE (status = 'active');
CREATE INDEX IF NOT EXISTS "sequence_state_merchant_idx" ON "sequence_state" (merchant_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "plaid_items_pkey" ON "plaid_items" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "plaid_items_tenant_item_uidx" ON "plaid_items" (tenant_id, plaid_item_id);
CREATE UNIQUE INDEX IF NOT EXISTS "plaid_items_tenant_attempt_uidx" ON "plaid_items" (tenant_id, merchant_id, attempt_id);
CREATE INDEX IF NOT EXISTS "plaid_items_recovery_idx" ON "plaid_items" (status, retry_count, updated_at) WHERE (status IN ('pending', 'error'));
CREATE INDEX IF NOT EXISTS "plaid_items_merchant_idx" ON "plaid_items" (tenant_id, merchant_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "item_column_values_pkey" ON "item_column_values" (item_id, column_id);
CREATE INDEX IF NOT EXISTS "item_column_values_column_idx" ON "item_column_values" (column_id);
CREATE UNIQUE INDEX IF NOT EXISTS "board_views_pkey" ON "board_views" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "crm_import_runs_pkey" ON "crm_import_runs" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "boards_pkey" ON "boards" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "boards_deals_singleton" ON "boards" (tenant_id) WHERE (kind = 'deals');
CREATE UNIQUE INDEX IF NOT EXISTS "board_groups_pkey" ON "board_groups" (id);
CREATE INDEX IF NOT EXISTS "board_groups_board_idx" ON "board_groups" (board_id, "position");
CREATE UNIQUE INDEX IF NOT EXISTS "board_columns_pkey" ON "board_columns" (id);
CREATE INDEX IF NOT EXISTS "board_columns_board_idx" ON "board_columns" (board_id, "position");
CREATE UNIQUE INDEX IF NOT EXISTS "board_columns_locked_stage_singleton" ON "board_columns" (board_id) WHERE (is_locked AND (type = 'status'));
CREATE UNIQUE INDEX IF NOT EXISTS "board_items_pkey" ON "board_items" (id);
CREATE INDEX IF NOT EXISTS "board_items_board_idx" ON "board_items" (board_id, group_id, "position");
CREATE UNIQUE INDEX IF NOT EXISTS "board_items_external_ref_unique" ON "board_items" (tenant_id, external_ref) WHERE (external_ref IS NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS "plaid_statement_requests_pkey" ON "plaid_statement_requests" (id);
CREATE INDEX IF NOT EXISTS "plaid_statement_requests_merchant_idx" ON "plaid_statement_requests" (tenant_id, merchant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS "plaid_statement_requests_work_idx" ON "plaid_statement_requests" (status, next_attempt_at, updated_at) WHERE (status IN ('starting_refresh', 'refreshing', 'callback_missing', 'ready', 'processing'));
CREATE UNIQUE INDEX IF NOT EXISTS "plaid_statement_requests_active_item_uidx" ON "plaid_statement_requests" (tenant_id, merchant_id, plaid_item_id) WHERE (status IN ('pending_consent', 'starting_refresh', 'refreshing', 'callback_missing', 'ready', 'processing'));
CREATE UNIQUE INDEX IF NOT EXISTS "plaid_statement_link_tokens_pkey" ON "plaid_statement_link_tokens" (request_id);
