-- oasis-platform master schema — transpiled from live Supabase
-- project ref: skgrbweyscysyetubemg  generated: 2026-08-06T23:29:59+00:00
-- tables: 17  indexes emitted: 79  views emitted: 1
--
-- NOT TRANSPILED (DAL responsibility — see scripts/lib/db_turso.py):
--   PL/pgSQL functions (13): auto_align_log_ownership, check_is_admin, ensure_log_visibility, get_portal_logs, handle_new_user, handle_updated_at, increment_promo_uses, update_automation_stats, update_automation_stats_no_definer, update_custom_agreements_timestamp, update_product_purchases_timestamp, update_updated_at, update_updated_at_column
--   Triggers (14): automation_logs.ensure_log_owner, automation_logs.ensure_log_visibility_trigger, automation_logs.on_automation_log_inserted, automation_logs.update_automation_stats_trigger, client_automations.update_automations_timestamp, client_automations.update_client_automations_updated_at, custom_agreements.custom_agreements_updated, custom_agreements.update_custom_agreements_updated_at, product_purchases.product_purchases_updated, product_purchases.update_product_purchases_updated_at...
--   RLS policies: replaced by mandatory tenant scoping in db_turso.py
--   cross-schema FKs dropped (1, e.g. auth.users): profiles(id) -> auth.users
--   FKs dropped as unenforceable in SQLite (0) — parent columns not unique in the emitted schema; enforce in the DAL
--   defaults dropped (8) and non-btree/expression indexes skipped (0): see turso_migrations/oasis__transpile_report.json
--
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS "custom_agreements" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "client_name" TEXT NOT NULL,
  "client_email" TEXT NOT NULL,
  "company_name" TEXT,
  "phone" TEXT,
  "agreement_reference" TEXT,
  "automation_type" TEXT NOT NULL,
  "upfront_cost_cents" INTEGER NOT NULL DEFAULT 0,
  "monthly_cost_cents" INTEGER NOT NULL DEFAULT 0,
  "nda_signed" INTEGER DEFAULT 0,
  "nda_signed_at" TEXT,
  "nda_signature_name" TEXT,
  "stripe_checkout_session_id" TEXT,
  "stripe_subscription_id" TEXT,
  "payment_status" TEXT DEFAULT 'pending',
  "paid_at" TEXT,
  "status" TEXT DEFAULT 'draft',
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "currency" TEXT DEFAULT 'usd',
  "tos_accepted" INTEGER DEFAULT 0,
  "tos_accepted_at" TEXT,
  "tos_version" TEXT,
  "privacy_accepted" INTEGER DEFAULT 0,
  "privacy_accepted_at" TEXT,
  "privacy_version" TEXT,
  "service_agreement_accepted" INTEGER DEFAULT 0,
  "service_agreement_accepted_at" TEXT,
  "service_agreement_signature" TEXT,
  "user_agent" TEXT,
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "invoices" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "user_id" TEXT,
  "user_email" TEXT NOT NULL,
  "stripe_invoice_id" TEXT,
  "stripe_customer_id" TEXT,
  "amount_cents" INTEGER NOT NULL,
  "currency" TEXT DEFAULT 'usd',
  "status" TEXT DEFAULT 'draft',
  "description" TEXT,
  "invoice_pdf_url" TEXT,
  "hosted_invoice_url" TEXT,
  "period_start" TEXT,
  "period_end" TEXT,
  "paid_at" TEXT,
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "legal_acceptances" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "client_name" TEXT NOT NULL,
  "client_email" TEXT NOT NULL,
  "company_name" TEXT,
  "document_type" TEXT NOT NULL,
  "document_version" TEXT NOT NULL,
  "acceptance_method" TEXT DEFAULT 'checkbox',
  "signature_name" TEXT,
  "related_purchase_type" TEXT,
  "user_agent" TEXT,
  "ip_address" TEXT,
  "accepted_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
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
  "upfront_cost_cents" INTEGER NOT NULL,
  "monthly_cost_cents" INTEGER NOT NULL,
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
  "stripe_session_id" TEXT,
  "stripe_customer_id" TEXT,
  "payment_status" TEXT DEFAULT 'unpaid',
  "user_agent" TEXT,
  "status" TEXT DEFAULT 'draft',
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "profiles" (
  "id" TEXT NOT NULL,
  "email" TEXT NOT NULL,
  "full_name" TEXT,
  "company_name" TEXT,
  "phone" TEXT,
  "avatar_url" TEXT,
  "role" TEXT DEFAULT 'client',
  "stripe_customer_id" TEXT,
  "is_active" INTEGER DEFAULT 1,
  "onboarding_completed" INTEGER DEFAULT 0,
  "timezone" TEXT DEFAULT 'America/Toronto',
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "last_login_at" TEXT,
  "onboarding_steps" TEXT,
  "is_owner" INTEGER DEFAULT 0,
  "is_admin" INTEGER DEFAULT 0,
  "billing_exempt" INTEGER DEFAULT 0,
  PRIMARY KEY ("id"),
  CONSTRAINT "profiles_role_check" CHECK ((role IN ('client', 'admin', 'super_admin')))
);

CREATE TABLE IF NOT EXISTS "promo_codes" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "code" TEXT NOT NULL,
  "discount_percent" INTEGER NOT NULL,
  "first_time_only" INTEGER DEFAULT 0,
  "max_uses" INTEGER,
  "current_uses" INTEGER DEFAULT 0,
  "is_active" INTEGER DEFAULT 1,
  "valid_from" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "valid_until" TEXT,
  "description" TEXT,
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "promo_codes_discount_percent_check" CHECK (((discount_percent > 0) AND (discount_percent <= 100)))
);

CREATE TABLE IF NOT EXISTS "api_keys" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "key_hash" TEXT NOT NULL,
  "key_prefix" TEXT NOT NULL,
  "name" TEXT NOT NULL,
  "description" TEXT,
  "permissions" TEXT DEFAULT '["log", "metric", "report"]',
  "is_active" INTEGER DEFAULT 1,
  "last_used_at" TEXT,
  "created_by" TEXT,
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "expires_at" TEXT,
  PRIMARY KEY ("id"),
  FOREIGN KEY ("created_by") REFERENCES "profiles" ("id")
);

CREATE TABLE IF NOT EXISTS "orders" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "user_id" TEXT,
  "pending_email" TEXT,
  "product_id" TEXT NOT NULL,
  "product_name" TEXT NOT NULL,
  "product_type" TEXT NOT NULL,
  "tier" TEXT,
  "setup_fee_cents" INTEGER NOT NULL,
  "monthly_fee_cents" INTEGER NOT NULL,
  "currency" TEXT DEFAULT 'usd',
  "discount_percent" INTEGER DEFAULT 0,
  "promo_code" TEXT,
  "stripe_checkout_session_id" TEXT,
  "stripe_subscription_id" TEXT,
  "payment_status" TEXT DEFAULT 'pending',
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "paid_at" TEXT,
  PRIMARY KEY ("id"),
  CONSTRAINT "orders_payment_status_check" CHECK ((payment_status IN ('pending', 'paid', 'failed', 'refunded'))),
  CONSTRAINT "orders_product_type_check" CHECK ((product_type IN ('automation', 'bundle'))),
  CONSTRAINT "orders_tier_check" CHECK ((tier IN ('starter', 'professional', 'business'))),
  FOREIGN KEY ("user_id") REFERENCES "profiles" ("id")
);

CREATE TABLE IF NOT EXISTS "pending_stripe_sessions" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "stripe_session_id" TEXT NOT NULL,
  "stripe_customer_id" TEXT,
  "customer_email" TEXT NOT NULL,
  "plan_type" TEXT,
  "product_name" TEXT,
  "tier" TEXT,
  "amount_total_cents" INTEGER,
  "currency" TEXT DEFAULT 'usd',
  "status" TEXT DEFAULT 'pending',
  "linked_user_id" TEXT,
  "linked_at" TEXT,
  "expires_at" TEXT,
  "created_at" TEXT NOT NULL,
  PRIMARY KEY ("id"),
  CONSTRAINT "pending_stripe_sessions_status_check" CHECK ((status IN ('pending', 'linked', 'expired'))),
  FOREIGN KEY ("linked_user_id") REFERENCES "profiles" ("id")
);

CREATE TABLE IF NOT EXISTS "promo_code_usage" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "promo_code_id" TEXT,
  "user_email" TEXT NOT NULL,
  "user_id" TEXT,
  "order_id" TEXT,
  "discount_amount_cents" INTEGER NOT NULL,
  "used_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("promo_code_id") REFERENCES "promo_codes" ("id")
);

CREATE TABLE IF NOT EXISTS "subscriptions" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "user_id" TEXT,
  "stripe_customer_id" TEXT,
  "stripe_subscription_id" TEXT,
  "stripe_price_id" TEXT,
  "product_name" TEXT NOT NULL,
  "tier" TEXT DEFAULT 'professional',
  "status" TEXT DEFAULT 'active',
  "amount_cents" INTEGER NOT NULL DEFAULT 0,
  "currency" TEXT DEFAULT 'usd',
  "billing_interval" TEXT DEFAULT 'month',
  "current_period_start" TEXT,
  "current_period_end" TEXT,
  "cancel_at_period_end" INTEGER DEFAULT 0,
  "canceled_at" TEXT,
  "metadata" TEXT DEFAULT '{}',
  "created_at" TEXT NOT NULL,
  "updated_at" TEXT NOT NULL,
  "is_custom_agreement" INTEGER DEFAULT 0,
  "custom_price" INTEGER,
  "custom_name" TEXT,
  "agreement_details" TEXT DEFAULT '{}',
  PRIMARY KEY ("id"),
  CONSTRAINT "subscriptions_billing_interval_check" CHECK ((billing_interval IN ('month', 'year'))),
  CONSTRAINT "subscriptions_status_check" CHECK ((status IN ('active', 'past_due', 'cancelled', 'paused', 'trialing', 'incomplete'))),
  FOREIGN KEY ("user_id") REFERENCES "profiles" ("id")
);

CREATE TABLE IF NOT EXISTS "billing_history" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "user_id" TEXT,
  "subscription_id" TEXT,
  "stripe_invoice_id" TEXT,
  "stripe_payment_intent_id" TEXT,
  "stripe_charge_id" TEXT,
  "description" TEXT NOT NULL,
  "amount_cents" INTEGER NOT NULL DEFAULT 0,
  "amount_paid_cents" INTEGER NOT NULL DEFAULT 0,
  "currency" TEXT DEFAULT 'usd',
  "status" TEXT DEFAULT 'pending',
  "invoice_date" TEXT NOT NULL,
  "due_date" TEXT,
  "paid_at" TEXT,
  "invoice_pdf_url" TEXT,
  "hosted_invoice_url" TEXT,
  "metadata" TEXT DEFAULT '{}',
  "created_at" TEXT NOT NULL,
  PRIMARY KEY ("id"),
  CONSTRAINT "billing_history_status_check" CHECK ((status IN ('draft', 'open', 'paid', 'void', 'uncollectible', 'pending', 'failed'))),
  FOREIGN KEY ("subscription_id") REFERENCES "subscriptions" ("id"),
  FOREIGN KEY ("user_id") REFERENCES "profiles" ("id")
);

CREATE TABLE IF NOT EXISTS "client_automations" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "user_id" TEXT NOT NULL,
  "order_id" TEXT,
  "subscription_id" TEXT,
  "automation_type" TEXT NOT NULL,
  "display_name" TEXT NOT NULL,
  "tier" TEXT NOT NULL,
  "status" TEXT DEFAULT 'pending_setup',
  "n8n_workflow_id" TEXT,
  "n8n_webhook_url" TEXT,
  "webhook_secret" TEXT,
  "config" TEXT DEFAULT '{}',
  "admin_notes" TEXT,
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "activated_at" TEXT,
  "last_run_at" TEXT,
  "stats" TEXT DEFAULT '{"total_runs": 0, "hours_saved": 0}',
  PRIMARY KEY ("id"),
  CONSTRAINT "client_automations_status_check" CHECK ((status IN ('pending_setup', 'in_progress', 'testing', 'active', 'paused', 'cancelled'))),
  CONSTRAINT "client_automations_tier_check" CHECK ((tier IN ('starter', 'professional', 'business'))),
  FOREIGN KEY ("order_id") REFERENCES "orders" ("id"),
  FOREIGN KEY ("user_id") REFERENCES "profiles" ("id")
);

CREATE TABLE IF NOT EXISTS "automation_logs" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "automation_id" TEXT NOT NULL,
  "user_id" TEXT NOT NULL,
  "event_type" TEXT NOT NULL,
  "event_name" TEXT NOT NULL,
  "description" TEXT,
  "metadata" TEXT DEFAULT '{}',
  "status" TEXT DEFAULT 'success',
  "error_message" TEXT,
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "automation_logs_status_check" CHECK ((status IN ('success', 'error', 'warning', 'info'))),
  FOREIGN KEY ("automation_id") REFERENCES "client_automations" ("id"),
  FOREIGN KEY ("user_id") REFERENCES "profiles" ("id")
);

CREATE TABLE IF NOT EXISTS "automation_metrics" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "automation_id" TEXT NOT NULL,
  "user_id" TEXT NOT NULL,
  "metric_name" TEXT NOT NULL,
  "metric_category" TEXT,
  "value_numeric" TEXT,
  "value_text" TEXT,
  "value_json" TEXT,
  "period_start" TEXT,
  "period_end" TEXT,
  "recorded_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "source" TEXT DEFAULT 'n8n',
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("automation_id") REFERENCES "client_automations" ("id"),
  FOREIGN KEY ("user_id") REFERENCES "profiles" ("id")
);

CREATE TABLE IF NOT EXISTS "monthly_reports" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "user_id" TEXT NOT NULL,
  "automation_id" TEXT,
  "title" TEXT NOT NULL,
  "description" TEXT,
  "report_month" TEXT NOT NULL,
  "file_url" TEXT,
  "file_name" TEXT,
  "file_type" TEXT,
  "file_size_bytes" INTEGER,
  "summary" TEXT DEFAULT '{}',
  "hours_saved" TEXT,
  "tasks_automated" INTEGER,
  "estimated_value_cents" INTEGER,
  "roi_percentage" TEXT,
  "status" TEXT DEFAULT 'draft',
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "published_at" TEXT,
  "viewed_at" TEXT,
  PRIMARY KEY ("id"),
  CONSTRAINT "monthly_reports_status_check" CHECK ((status IN ('draft', 'published', 'archived'))),
  FOREIGN KEY ("automation_id") REFERENCES "client_automations" ("id"),
  FOREIGN KEY ("user_id") REFERENCES "profiles" ("id")
);

CREATE TABLE IF NOT EXISTS "support_tickets" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "user_id" TEXT NOT NULL,
  "automation_id" TEXT,
  "subject" TEXT NOT NULL,
  "description" TEXT,
  "priority" TEXT DEFAULT 'medium',
  "status" TEXT DEFAULT 'open',
  "assigned_to" TEXT,
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "resolved_at" TEXT,
  PRIMARY KEY ("id"),
  CONSTRAINT "support_tickets_priority_check" CHECK ((priority IN ('low', 'medium', 'high', 'urgent'))),
  CONSTRAINT "support_tickets_status_check" CHECK ((status IN ('open', 'in_progress', 'waiting_on_client', 'resolved', 'closed'))),
  FOREIGN KEY ("assigned_to") REFERENCES "profiles" ("id"),
  FOREIGN KEY ("automation_id") REFERENCES "client_automations" ("id"),
  FOREIGN KEY ("user_id") REFERENCES "profiles" ("id")
);

-- indexes
CREATE UNIQUE INDEX IF NOT EXISTS "billing_history_pkey" ON "billing_history" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "billing_history_stripe_invoice_id_key" ON "billing_history" (stripe_invoice_id);
CREATE INDEX IF NOT EXISTS "idx_billing_history_user_id" ON "billing_history" (user_id);
CREATE INDEX IF NOT EXISTS "idx_billing_history_subscription" ON "billing_history" (subscription_id);
CREATE INDEX IF NOT EXISTS "idx_billing_history_stripe_invoice" ON "billing_history" (stripe_invoice_id);
CREATE UNIQUE INDEX IF NOT EXISTS "subscriptions_pkey" ON "subscriptions" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "subscriptions_stripe_subscription_id_key" ON "subscriptions" (stripe_subscription_id);
CREATE INDEX IF NOT EXISTS "idx_subscriptions_user_id" ON "subscriptions" (user_id);
CREATE INDEX IF NOT EXISTS "idx_subscriptions_stripe_customer" ON "subscriptions" (stripe_customer_id);
CREATE INDEX IF NOT EXISTS "idx_subscriptions_status" ON "subscriptions" (status);
CREATE UNIQUE INDEX IF NOT EXISTS "pending_stripe_sessions_pkey" ON "pending_stripe_sessions" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "pending_stripe_sessions_stripe_session_id_key" ON "pending_stripe_sessions" (stripe_session_id);
CREATE INDEX IF NOT EXISTS "idx_pending_sessions_email" ON "pending_stripe_sessions" (customer_email);
CREATE INDEX IF NOT EXISTS "idx_pending_sessions_stripe_id" ON "pending_stripe_sessions" (stripe_session_id);
CREATE INDEX IF NOT EXISTS "idx_pending_stripe_sessions_linked_user_id" ON "pending_stripe_sessions" (linked_user_id);
CREATE UNIQUE INDEX IF NOT EXISTS "promo_codes_pkey" ON "promo_codes" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "promo_codes_code_key" ON "promo_codes" (code);
CREATE INDEX IF NOT EXISTS "idx_promo_codes_code" ON "promo_codes" (code);
CREATE INDEX IF NOT EXISTS "idx_profiles_email" ON "profiles" (email);
CREATE INDEX IF NOT EXISTS "idx_profiles_role" ON "profiles" (role);
CREATE UNIQUE INDEX IF NOT EXISTS "profiles_pkey" ON "profiles" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "profiles_email_key" ON "profiles" (email);
CREATE UNIQUE INDEX IF NOT EXISTS "profiles_stripe_customer_id_key" ON "profiles" (stripe_customer_id);
CREATE INDEX IF NOT EXISTS "idx_profiles_stripe" ON "profiles" (stripe_customer_id);
CREATE UNIQUE INDEX IF NOT EXISTS "api_keys_pkey" ON "api_keys" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "api_keys_key_hash_key" ON "api_keys" (key_hash);
CREATE INDEX IF NOT EXISTS "idx_api_keys_created_by" ON "api_keys" (created_by);
CREATE UNIQUE INDEX IF NOT EXISTS "support_tickets_pkey" ON "support_tickets" (id);
CREATE INDEX IF NOT EXISTS "idx_support_tickets_user" ON "support_tickets" (user_id);
CREATE INDEX IF NOT EXISTS "idx_support_tickets_status" ON "support_tickets" (status);
CREATE INDEX IF NOT EXISTS "idx_support_tickets_priority" ON "support_tickets" (priority);
CREATE INDEX IF NOT EXISTS "idx_support_tickets_assigned_to" ON "support_tickets" (assigned_to);
CREATE INDEX IF NOT EXISTS "idx_support_tickets_automation_id" ON "support_tickets" (automation_id);
CREATE INDEX IF NOT EXISTS "idx_metrics_automation_id" ON "automation_metrics" (automation_id);
CREATE INDEX IF NOT EXISTS "idx_metrics_recorded_at" ON "automation_metrics" (recorded_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "automation_metrics_pkey" ON "automation_metrics" (id);
CREATE INDEX IF NOT EXISTS "idx_automation_metrics_user_id" ON "automation_metrics" (user_id);
CREATE INDEX IF NOT EXISTS "idx_reports_user_id" ON "monthly_reports" (user_id);
CREATE UNIQUE INDEX IF NOT EXISTS "monthly_reports_pkey" ON "monthly_reports" (id);
CREATE INDEX IF NOT EXISTS "idx_monthly_reports_automation_id" ON "monthly_reports" (automation_id);
CREATE INDEX IF NOT EXISTS "idx_orders_user_id" ON "orders" (user_id);
CREATE INDEX IF NOT EXISTS "idx_orders_pending_email" ON "orders" (pending_email);
CREATE UNIQUE INDEX IF NOT EXISTS "orders_pkey" ON "orders" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "orders_stripe_checkout_session_id_key" ON "orders" (stripe_checkout_session_id);
CREATE INDEX IF NOT EXISTS "idx_automations_user_id" ON "client_automations" (user_id);
CREATE INDEX IF NOT EXISTS "idx_automations_status" ON "client_automations" (status);
CREATE UNIQUE INDEX IF NOT EXISTS "client_automations_pkey" ON "client_automations" (id);
CREATE INDEX IF NOT EXISTS "idx_client_automations_order_id" ON "client_automations" (order_id);
CREATE UNIQUE INDEX IF NOT EXISTS "legal_acceptances_pkey" ON "legal_acceptances" (id);
CREATE INDEX IF NOT EXISTS "idx_legal_acceptances_email" ON "legal_acceptances" (client_email);
CREATE INDEX IF NOT EXISTS "idx_legal_acceptances_document" ON "legal_acceptances" (document_type, document_version);
CREATE INDEX IF NOT EXISTS "idx_legal_acceptances_date" ON "legal_acceptances" (accepted_at);
CREATE UNIQUE INDEX IF NOT EXISTS "product_purchases_pkey" ON "product_purchases" (id);
CREATE INDEX IF NOT EXISTS "idx_product_purchases_email" ON "product_purchases" (client_email);
CREATE INDEX IF NOT EXISTS "idx_product_purchases_status" ON "product_purchases" (status);
CREATE INDEX IF NOT EXISTS "idx_product_purchases_tier" ON "product_purchases" (product_tier);
CREATE INDEX IF NOT EXISTS "idx_product_purchases_payment" ON "product_purchases" (payment_status);
CREATE INDEX IF NOT EXISTS "idx_logs_automation_id" ON "automation_logs" (automation_id);
CREATE INDEX IF NOT EXISTS "idx_logs_created_at" ON "automation_logs" (created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "automation_logs_pkey" ON "automation_logs" (id);
CREATE INDEX IF NOT EXISTS "idx_automation_logs_automation" ON "automation_logs" (automation_id);
CREATE INDEX IF NOT EXISTS "idx_automation_logs_user" ON "automation_logs" (user_id);
CREATE INDEX IF NOT EXISTS "idx_automation_logs_date" ON "automation_logs" (created_at DESC);
CREATE INDEX IF NOT EXISTS "idx_automation_logs_type" ON "automation_logs" (event_type);
CREATE INDEX IF NOT EXISTS "idx_automation_logs_user_id" ON "automation_logs" (user_id);
CREATE INDEX IF NOT EXISTS "idx_automation_logs_automation_id" ON "automation_logs" (automation_id);
CREATE INDEX IF NOT EXISTS "idx_automation_logs_created_at" ON "automation_logs" (created_at);
CREATE UNIQUE INDEX IF NOT EXISTS "promo_code_usage_pkey" ON "promo_code_usage" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "promo_code_usage_promo_code_id_user_email_key" ON "promo_code_usage" (promo_code_id, user_email);
CREATE INDEX IF NOT EXISTS "idx_promo_usage_email" ON "promo_code_usage" (user_email);
CREATE UNIQUE INDEX IF NOT EXISTS "custom_agreements_pkey" ON "custom_agreements" (id);
CREATE INDEX IF NOT EXISTS "idx_custom_agreements_email" ON "custom_agreements" (client_email);
CREATE INDEX IF NOT EXISTS "idx_custom_agreements_status" ON "custom_agreements" (status);
CREATE INDEX IF NOT EXISTS "idx_custom_agreements_payment" ON "custom_agreements" (payment_status);
CREATE UNIQUE INDEX IF NOT EXISTS "invoices_pkey" ON "invoices" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "invoices_stripe_invoice_id_key" ON "invoices" (stripe_invoice_id);
CREATE INDEX IF NOT EXISTS "idx_invoices_user" ON "invoices" (user_id);
CREATE INDEX IF NOT EXISTS "idx_invoices_email" ON "invoices" (user_email);
CREATE INDEX IF NOT EXISTS "idx_invoices_stripe" ON "invoices" (stripe_invoice_id);

-- views
CREATE VIEW IF NOT EXISTS "automations" AS
SELECT id,
    user_id,
    order_id,
    subscription_id,
    automation_type,
    display_name,
    tier,
    status,
    n8n_workflow_id,
    n8n_webhook_url,
    webhook_secret,
    config,
    admin_notes,
    created_at,
    updated_at,
    activated_at,
    last_run_at,
    stats
   FROM client_automations;
