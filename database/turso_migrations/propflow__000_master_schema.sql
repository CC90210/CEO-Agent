-- propflow master schema — transpiled from live Supabase
-- project ref: xusnasmzoxkaimyjqbie  generated: 2026-08-06T23:36:13+00:00
-- tables: 43  indexes emitted: 81  views emitted: 0
--
-- NOT TRANSPILED (DAL responsibility — see scripts/lib/db_turso.py):
--   PL/pgSQL functions (12): accept_invitation_manually, check_rate_limit, ensure_user_profile, ensure_user_profile_admin, generate_invoice_number, handle_new_user, increment_automation_counter, protect_company_entitlements, protect_profile_privileges, reap_stale_walkthrough_jobs, register_incoming_webhook_event, set_updated_at
--   Triggers (45): activity_log.set_activity_log_updated_at, agent_social_profiles.set_agent_social_profiles_updated_at, api_rate_limits.set_api_rate_limits_updated_at, application_documents.set_application_documents_updated_at, application_screening_reports.set_application_screening_reports_updated_at, applications.set_applications_updated_at, areas.set_areas_updated_at, audit_logs.set_audit_logs_updated_at, automation_configs.set_automation_configs_updated_at, automation_executions.set_automation_executions_updated_at...
--   RLS policies: replaced by mandatory tenant scoping in db_turso.py
--   cross-schema FKs dropped (10, e.g. auth.users): agent_social_profiles(user_id) -> auth.users; audit_logs(user_id) -> auth.users; gmail_oauth_tokens(user_id) -> auth.users; leases(tenant_id) -> auth.users; notifications(user_id) -> auth.users; platform_invitations(used_by) -> auth.users
--   FKs dropped as unenforceable in SQLite (0) — parent columns not unique in the emitted schema; enforce in the DAL
--   defaults dropped (13) and non-btree/expression indexes skipped (0): see turso_migrations/propflow__transpile_report.json
--
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS "agent_social_profiles" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "user_id" TEXT NOT NULL,
  "late_profile_id" TEXT NOT NULL,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "api_rate_limits" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "scope" TEXT NOT NULL,
  "window_start" TEXT NOT NULL,
  "count" INTEGER NOT NULL DEFAULT 0,
  "expires_at" TEXT NOT NULL,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "api_rate_limits_count_check" CHECK ((count >= 0))
);

CREATE TABLE IF NOT EXISTS "incoming_webhook_events" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "provider" TEXT NOT NULL,
  "event_id" TEXT NOT NULL,
  "payload_hash" TEXT,
  "processed_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "expires_at" TEXT NOT NULL,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "activity_log" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "company_id" TEXT NOT NULL,
  "user_id" TEXT,
  "action" TEXT NOT NULL,
  "entity_type" TEXT,
  "entity_id" TEXT,
  "description" TEXT,
  "details" TEXT NOT NULL DEFAULT '{}',
  "metadata" TEXT NOT NULL DEFAULT '{}',
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("company_id") REFERENCES "companies" ("id"),
  FOREIGN KEY ("user_id") REFERENCES "profiles" ("id")
);

CREATE TABLE IF NOT EXISTS "application_documents" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "application_id" TEXT NOT NULL,
  "company_id" TEXT NOT NULL,
  "file_name" TEXT NOT NULL,
  "file_url" TEXT NOT NULL,
  "file_type" TEXT NOT NULL DEFAULT 'other',
  "file_size" INTEGER,
  "document_label" TEXT,
  "mime_type" TEXT,
  "storage_path" TEXT,
  "uploaded_by" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("application_id") REFERENCES "applications" ("id"),
  FOREIGN KEY ("company_id") REFERENCES "companies" ("id"),
  FOREIGN KEY ("uploaded_by") REFERENCES "profiles" ("id")
);

CREATE TABLE IF NOT EXISTS "application_screening_reports" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "application_id" TEXT NOT NULL,
  "company_id" TEXT NOT NULL,
  "file_url" TEXT NOT NULL,
  "file_name" TEXT NOT NULL,
  "file_size" INTEGER,
  "report_type" TEXT NOT NULL DEFAULT 'singlekey',
  "extracted_credit_score" INTEGER,
  "extracted_income" TEXT,
  "extracted_criminal_clear" INTEGER,
  "extracted_public_records_clear" INTEGER,
  "extracted_bankruptcies" INTEGER,
  "extracted_collections" INTEGER,
  "extracted_legal_cases" INTEGER,
  "extracted_summary" TEXT,
  "extracted_risk_flags" TEXT,
  "raw_extracted_data" TEXT,
  "processing_status" TEXT NOT NULL DEFAULT 'pending',
  "processed_at" TEXT,
  "uploaded_by" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("application_id") REFERENCES "applications" ("id"),
  FOREIGN KEY ("company_id") REFERENCES "companies" ("id"),
  FOREIGN KEY ("uploaded_by") REFERENCES "profiles" ("id")
);

CREATE TABLE IF NOT EXISTS "applications" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "company_id" TEXT NOT NULL,
  "property_id" TEXT NOT NULL,
  "agent_id" TEXT,
  "submitted_by" TEXT,
  "applicant_name" TEXT NOT NULL,
  "applicant_email" TEXT NOT NULL,
  "applicant_phone" TEXT NOT NULL DEFAULT '',
  "current_address" TEXT,
  "employer" TEXT,
  "monthly_income" TEXT,
  "move_in_date" TEXT,
  "num_occupants" INTEGER NOT NULL DEFAULT 1,
  "has_pets" INTEGER NOT NULL DEFAULT 0,
  "pet_details" TEXT,
  "additional_notes" TEXT,
  "combined_household_income" TEXT,
  "employment_status" TEXT,
  "employment_duration" TEXT,
  "previous_addresses" TEXT,
  "current_rent" TEXT,
  "current_landlord_name" TEXT,
  "current_landlord_phone" TEXT,
  "total_debt" TEXT,
  "num_vehicles" INTEGER,
  "is_smoker" INTEGER NOT NULL DEFAULT 0,
  "government_id_verified" INTEGER,
  "screening_status" TEXT NOT NULL DEFAULT 'pending',
  "credit_score" INTEGER,
  "background_check_passed" INTEGER,
  "criminal_check_passed" INTEGER,
  "public_records_clear" INTEGER,
  "income_verified" INTEGER,
  "screening_url" TEXT,
  "screening_report_url" TEXT,
  "singlekey_report_url" TEXT,
  "screening_completed_at" TEXT,
  "income_to_rent_ratio" TEXT,
  "yearly_rent_cost" TEXT,
  "dti_ratio" TEXT,
  "status" TEXT NOT NULL DEFAULT 'new',
  "denial_reason" TEXT,
  "reviewed_at" TEXT,
  "reviewed_by" TEXT,
  "webhook_sent" INTEGER NOT NULL DEFAULT 0,
  "webhook_sent_at" TEXT,
  "automation_status" TEXT,
  "automation_error" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("company_id") REFERENCES "companies" ("id"),
  FOREIGN KEY ("property_id") REFERENCES "properties" ("id"),
  FOREIGN KEY ("agent_id") REFERENCES "profiles" ("id"),
  FOREIGN KEY ("submitted_by") REFERENCES "profiles" ("id"),
  FOREIGN KEY ("reviewed_by") REFERENCES "profiles" ("id")
);

CREATE TABLE IF NOT EXISTS "areas" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "company_id" TEXT NOT NULL,
  "name" TEXT NOT NULL,
  "description" TEXT,
  "image_url" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("company_id") REFERENCES "companies" ("id")
);

CREATE TABLE IF NOT EXISTS "audit_logs" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "company_id" TEXT,
  "user_id" TEXT,
  "action" TEXT NOT NULL,
  "resource_type" TEXT,
  "resource_id" TEXT,
  "metadata" TEXT NOT NULL DEFAULT '{}',
  "ip_address" TEXT,
  "user_agent" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("company_id") REFERENCES "companies" ("id")
);

CREATE TABLE IF NOT EXISTS "automation_configs" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "company_id" TEXT NOT NULL,
  "type" TEXT NOT NULL,
  "name" TEXT,
  "status" TEXT NOT NULL DEFAULT 'inactive',
  "purchased_at" TEXT,
  "implementation_fee_paid" INTEGER NOT NULL DEFAULT 0,
  "config" TEXT NOT NULL DEFAULT '{}',
  "total_executions" INTEGER NOT NULL DEFAULT 0,
  "successful_executions" INTEGER NOT NULL DEFAULT 0,
  "last_execution_at" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("company_id") REFERENCES "companies" ("id")
);

CREATE TABLE IF NOT EXISTS "automation_executions" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "automation_id" TEXT NOT NULL,
  "status" TEXT NOT NULL DEFAULT 'pending',
  "started_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "completed_at" TEXT,
  "duration_ms" INTEGER,
  "error_message" TEXT,
  "input_payload" TEXT NOT NULL DEFAULT '{}',
  "output_payload" TEXT NOT NULL DEFAULT '{}',
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("automation_id") REFERENCES "automation_configs" ("id")
);

CREATE TABLE IF NOT EXISTS "automation_logs" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "company_id" TEXT NOT NULL,
  "user_id" TEXT,
  "action_type" TEXT NOT NULL,
  "entity_type" TEXT,
  "entity_id" TEXT,
  "payload" TEXT NOT NULL DEFAULT '{}',
  "status" TEXT NOT NULL DEFAULT 'pending',
  "result" TEXT,
  "error_message" TEXT,
  "triggered_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "completed_at" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("company_id") REFERENCES "companies" ("id"),
  FOREIGN KEY ("user_id") REFERENCES "profiles" ("id")
);

CREATE TABLE IF NOT EXISTS "automation_settings" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "company_id" TEXT NOT NULL,
  "email_provider" TEXT,
  "smtp_host" TEXT,
  "smtp_port" INTEGER,
  "smtp_user" TEXT,
  "smtp_password" TEXT,
  "from_name" TEXT,
  "from_email" TEXT,
  "singlekey_api_key" TEXT,
  "document_email_enabled" INTEGER NOT NULL DEFAULT 0,
  "document_email_recipients" TEXT NOT NULL,
  "document_email_template" TEXT,
  "invoice_email_enabled" INTEGER NOT NULL DEFAULT 0,
  "invoice_email_recipients" TEXT NOT NULL,
  "invoice_email_template" TEXT,
  "webhook_url" TEXT,
  "webhook_secret" TEXT NOT NULL,
  "webhook_events" TEXT NOT NULL,
  "platform_credentials" TEXT,
  "listing_platforms" TEXT NOT NULL DEFAULT '[]',
  "updated_by" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("company_id") REFERENCES "companies" ("id"),
  FOREIGN KEY ("updated_by") REFERENCES "profiles" ("id")
);

CREATE TABLE IF NOT EXISTS "automation_subscriptions" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "company_id" TEXT NOT NULL,
  "is_active" INTEGER NOT NULL DEFAULT 0,
  "tier" TEXT NOT NULL DEFAULT 'none',
  "features" TEXT NOT NULL DEFAULT '{}',
  "webhook_endpoints" TEXT NOT NULL DEFAULT '{}',
  "enabled_at" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("company_id") REFERENCES "companies" ("id")
);

CREATE TABLE IF NOT EXISTS "buildings" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "company_id" TEXT NOT NULL,
  "area_id" TEXT,
  "name" TEXT NOT NULL,
  "address" TEXT NOT NULL,
  "city" TEXT,
  "postal_code" TEXT,
  "total_units" INTEGER,
  "year_built" INTEGER,
  "amenities" TEXT NOT NULL DEFAULT '[]',
  "image_url" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("company_id") REFERENCES "companies" ("id"),
  FOREIGN KEY ("area_id") REFERENCES "areas" ("id")
);

CREATE TABLE IF NOT EXISTS "commissions" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "company_id" TEXT NOT NULL,
  "agent_id" TEXT NOT NULL,
  "property_id" TEXT,
  "application_id" TEXT,
  "lease_id" TEXT,
  "type" TEXT NOT NULL DEFAULT 'lease_signing',
  "amount" TEXT NOT NULL,
  "percentage" TEXT,
  "status" TEXT NOT NULL DEFAULT 'pending',
  "description" TEXT,
  "earned_date" TEXT NOT NULL,
  "paid_date" TEXT,
  "paid_at" TEXT,
  "notes" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("company_id") REFERENCES "companies" ("id"),
  FOREIGN KEY ("agent_id") REFERENCES "profiles" ("id"),
  FOREIGN KEY ("property_id") REFERENCES "properties" ("id"),
  FOREIGN KEY ("application_id") REFERENCES "applications" ("id"),
  FOREIGN KEY ("lease_id") REFERENCES "leases" ("id")
);

CREATE TABLE IF NOT EXISTS "companies" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "name" TEXT NOT NULL,
  "slug" TEXT,
  "email" TEXT,
  "phone" TEXT,
  "address" TEXT,
  "logo_url" TEXT,
  "tagline" TEXT,
  "primary_color" TEXT NOT NULL DEFAULT '#2563eb',
  "email_footer_text" TEXT,
  "subscription_plan" TEXT NOT NULL DEFAULT 'professional',
  "subscription_status" TEXT NOT NULL DEFAULT 'active',
  "subscription_tier" TEXT NOT NULL DEFAULT 'tier_2',
  "is_lifetime_access" INTEGER NOT NULL DEFAULT 0,
  "automation_enabled" INTEGER NOT NULL DEFAULT 0,
  "feature_flags" TEXT NOT NULL DEFAULT '{}',
  "stripe_customer_id" TEXT,
  "stripe_subscription_id" TEXT,
  "subscription_current_period_end" TEXT,
  "stripe_connect_id" TEXT,
  "stripe_connect_enabled" INTEGER NOT NULL DEFAULT 0,
  "late_profile_id" TEXT,
  "plan_override" TEXT,
  "plan_override_reason" TEXT,
  "plan_override_by" TEXT,
  "plan_override_at" TEXT,
  "property_count" INTEGER NOT NULL DEFAULT 0,
  "team_member_count" INTEGER NOT NULL DEFAULT 0,
  "social_account_count" INTEGER NOT NULL DEFAULT 0,
  "next_invoice_number" INTEGER NOT NULL DEFAULT 1,
  "invoice_prefix" TEXT NOT NULL DEFAULT 'INV-',
  "currency" TEXT NOT NULL DEFAULT 'CAD',
  "subscription_started_at" TEXT,
  "subscription_ends_at" TEXT,
  "trial_ends_at" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("plan_override_by") REFERENCES "profiles" ("id")
);

CREATE TABLE IF NOT EXISTS "contacts" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "company_id" TEXT NOT NULL,
  "name" TEXT NOT NULL,
  "email" TEXT,
  "phone" TEXT,
  "type" TEXT NOT NULL DEFAULT 'prospect',
  "company_name" TEXT,
  "address" TEXT,
  "notes" TEXT,
  "tags" TEXT NOT NULL DEFAULT '[]',
  "property_id" TEXT,
  "last_contacted_at" TEXT,
  "created_by" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("company_id") REFERENCES "companies" ("id"),
  FOREIGN KEY ("property_id") REFERENCES "properties" ("id"),
  FOREIGN KEY ("created_by") REFERENCES "profiles" ("id")
);

CREATE TABLE IF NOT EXISTS "documents" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "company_id" TEXT NOT NULL,
  "created_by" TEXT,
  "type" TEXT NOT NULL,
  "title" TEXT,
  "content" TEXT NOT NULL DEFAULT '{}',
  "pdf_url" TEXT,
  "property_id" TEXT,
  "application_id" TEXT,
  "related_property_id" TEXT,
  "related_landlord_id" TEXT,
  "status" TEXT NOT NULL DEFAULT 'completed',
  "currency" TEXT NOT NULL DEFAULT 'CAD',
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("company_id") REFERENCES "companies" ("id"),
  FOREIGN KEY ("created_by") REFERENCES "profiles" ("id"),
  FOREIGN KEY ("property_id") REFERENCES "properties" ("id"),
  FOREIGN KEY ("application_id") REFERENCES "applications" ("id"),
  FOREIGN KEY ("related_property_id") REFERENCES "properties" ("id"),
  FOREIGN KEY ("related_landlord_id") REFERENCES "landlords" ("id")
);

CREATE TABLE IF NOT EXISTS "gmail_oauth_tokens" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "company_id" TEXT NOT NULL,
  "user_id" TEXT NOT NULL,
  "email" TEXT NOT NULL,
  "access_token" TEXT NOT NULL,
  "refresh_token" TEXT,
  "token_expiry" TEXT,
  "scopes" TEXT NOT NULL DEFAULT '[]',
  "is_primary" INTEGER NOT NULL DEFAULT 0,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("company_id") REFERENCES "companies" ("id")
);

CREATE TABLE IF NOT EXISTS "inspection_items" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "inspection_id" TEXT NOT NULL,
  "label" TEXT NOT NULL,
  "category" TEXT NOT NULL,
  "status" TEXT NOT NULL DEFAULT 'not_checked',
  "notes" TEXT,
  "photo_urls" TEXT NOT NULL DEFAULT '[]',
  "maintenance_request_id" TEXT,
  "landlord_override" INTEGER NOT NULL DEFAULT 0,
  "landlord_override_at" TEXT,
  "landlord_override_reason" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("inspection_id") REFERENCES "inspections" ("id"),
  FOREIGN KEY ("maintenance_request_id") REFERENCES "maintenance_requests" ("id")
);

CREATE TABLE IF NOT EXISTS "inspections" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "company_id" TEXT NOT NULL,
  "property_id" TEXT NOT NULL,
  "template_id" TEXT,
  "inspected_by" TEXT NOT NULL,
  "inspected_by_name" TEXT NOT NULL,
  "status" TEXT NOT NULL DEFAULT 'in_progress',
  "notes" TEXT,
  "signed_at" TEXT,
  "landlord_notified_at" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("company_id") REFERENCES "companies" ("id"),
  FOREIGN KEY ("property_id") REFERENCES "properties" ("id"),
  FOREIGN KEY ("inspected_by") REFERENCES "profiles" ("id")
);

CREATE TABLE IF NOT EXISTS "invoice_items" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "invoice_id" TEXT NOT NULL,
  "description" TEXT,
  "reference" TEXT,
  "quantity" TEXT NOT NULL DEFAULT 1,
  "rate" TEXT NOT NULL DEFAULT 0,
  "amount" TEXT NOT NULL DEFAULT 0,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("invoice_id") REFERENCES "invoices" ("id")
);

CREATE TABLE IF NOT EXISTS "invoices" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "company_id" TEXT NOT NULL,
  "created_by" TEXT,
  "invoice_number" TEXT NOT NULL,
  "recipient_name" TEXT NOT NULL,
  "recipient_email" TEXT,
  "property_id" TEXT,
  "issue_date" TEXT NOT NULL,
  "due_date" TEXT,
  "items" TEXT NOT NULL DEFAULT '[]',
  "subtotal" TEXT NOT NULL DEFAULT 0,
  "tax_amount" TEXT NOT NULL DEFAULT 0,
  "total" TEXT NOT NULL DEFAULT 0,
  "status" TEXT NOT NULL DEFAULT 'draft',
  "notes" TEXT,
  "pdf_url" TEXT,
  "pdf_generated_at" TEXT,
  "currency" TEXT NOT NULL DEFAULT 'CAD',
  "paid_at" TEXT,
  "paid_date" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("company_id") REFERENCES "companies" ("id"),
  FOREIGN KEY ("created_by") REFERENCES "profiles" ("id"),
  FOREIGN KEY ("property_id") REFERENCES "properties" ("id")
);

CREATE TABLE IF NOT EXISTS "landlord_properties" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "landlord_id" TEXT NOT NULL,
  "property_id" TEXT NOT NULL,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("landlord_id") REFERENCES "landlords" ("id"),
  FOREIGN KEY ("property_id") REFERENCES "properties" ("id")
);

CREATE TABLE IF NOT EXISTS "landlords" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "company_id" TEXT NOT NULL,
  "name" TEXT NOT NULL,
  "email" TEXT,
  "phone" TEXT,
  "company_name" TEXT,
  "address" TEXT,
  "notes" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("company_id") REFERENCES "companies" ("id")
);

CREATE TABLE IF NOT EXISTS "leases" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "company_id" TEXT NOT NULL,
  "property_id" TEXT NOT NULL,
  "tenant_id" TEXT,
  "tenant_name" TEXT NOT NULL,
  "tenant_email" TEXT NOT NULL,
  "tenant_phone" TEXT,
  "start_date" TEXT NOT NULL,
  "end_date" TEXT NOT NULL,
  "rent_amount" TEXT NOT NULL,
  "deposit_amount" TEXT NOT NULL DEFAULT 0,
  "payment_day" INTEGER NOT NULL DEFAULT 1,
  "status" TEXT NOT NULL DEFAULT 'draft',
  "auto_renew" INTEGER NOT NULL DEFAULT 0,
  "renewal_notice_days" INTEGER NOT NULL DEFAULT 60,
  "rent_escalation_pct" TEXT NOT NULL DEFAULT 0,
  "lease_document_url" TEXT,
  "signed_at" TEXT,
  "notes" TEXT,
  "created_by" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "leases_payment_day_check" CHECK (((payment_day >= 1) AND (payment_day <= 28))),
  FOREIGN KEY ("company_id") REFERENCES "companies" ("id"),
  FOREIGN KEY ("property_id") REFERENCES "properties" ("id"),
  FOREIGN KEY ("created_by") REFERENCES "profiles" ("id")
);

CREATE TABLE IF NOT EXISTS "maintenance_requests" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "company_id" TEXT NOT NULL,
  "property_id" TEXT NOT NULL,
  "submitted_by" TEXT,
  "assigned_to" TEXT,
  "title" TEXT NOT NULL,
  "description" TEXT NOT NULL,
  "category" TEXT NOT NULL DEFAULT 'general',
  "priority" TEXT NOT NULL DEFAULT 'medium',
  "status" TEXT NOT NULL DEFAULT 'open',
  "photos" TEXT NOT NULL DEFAULT '[]',
  "estimated_cost" TEXT,
  "actual_cost" TEXT,
  "scheduled_date" TEXT,
  "resolved_at" TEXT,
  "resolution_notes" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("company_id") REFERENCES "companies" ("id"),
  FOREIGN KEY ("property_id") REFERENCES "properties" ("id"),
  FOREIGN KEY ("submitted_by") REFERENCES "profiles" ("id"),
  FOREIGN KEY ("assigned_to") REFERENCES "profiles" ("id")
);

CREATE TABLE IF NOT EXISTS "notifications" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "user_id" TEXT NOT NULL,
  "company_id" TEXT,
  "title" TEXT NOT NULL,
  "message" TEXT NOT NULL,
  "type" TEXT NOT NULL DEFAULT 'info',
  "category" TEXT NOT NULL DEFAULT 'system',
  "read" INTEGER NOT NULL DEFAULT 0,
  "read_at" TEXT,
  "action_url" TEXT,
  "action_label" TEXT,
  "email_sent" INTEGER NOT NULL DEFAULT 0,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("company_id") REFERENCES "companies" ("id")
);

CREATE TABLE IF NOT EXISTS "platform_invitations" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "token" TEXT NOT NULL,
  "label" TEXT NOT NULL,
  "company_name" TEXT,
  "assigned_plan" TEXT NOT NULL DEFAULT 'agent_pro',
  "is_enterprise" INTEGER NOT NULL DEFAULT 0,
  "status" TEXT NOT NULL DEFAULT 'active',
  "max_uses" INTEGER NOT NULL DEFAULT 1,
  "use_count" INTEGER NOT NULL DEFAULT 0,
  "created_by" TEXT,
  "used_by" TEXT,
  "used_at" TEXT,
  "company_created_id" TEXT,
  "expires_at" TEXT NOT NULL,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "platform_invitations_max_uses_check" CHECK ((max_uses > 0)),
  CONSTRAINT "platform_invitations_status_check" CHECK ((status IN ('active', 'used', 'revoked', 'expired'))),
  CONSTRAINT "platform_invitations_use_count_check" CHECK ((use_count >= 0)),
  FOREIGN KEY ("created_by") REFERENCES "profiles" ("id"),
  FOREIGN KEY ("company_created_id") REFERENCES "companies" ("id")
);

CREATE TABLE IF NOT EXISTS "profiles" (
  "id" TEXT NOT NULL,
  "company_id" TEXT,
  "email" TEXT NOT NULL,
  "full_name" TEXT NOT NULL DEFAULT 'New User',
  "avatar_url" TEXT,
  "phone" TEXT,
  "job_title" TEXT,
  "role" TEXT NOT NULL DEFAULT 'agent',
  "is_super_admin" INTEGER NOT NULL DEFAULT 0,
  "is_partner" INTEGER NOT NULL DEFAULT 0,
  "partner_type" TEXT,
  "is_active" INTEGER NOT NULL DEFAULT 1,
  "stripe_customer_id" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "profiles_role_check" CHECK ((role IN ('admin', 'agent', 'landlord', 'tenant'))),
  FOREIGN KEY ("company_id") REFERENCES "companies" ("id")
);

CREATE TABLE IF NOT EXISTS "properties" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "company_id" TEXT NOT NULL,
  "area_id" TEXT,
  "building_id" TEXT,
  "landlord_id" TEXT,
  "owner_id" TEXT,
  "unit_number" TEXT,
  "address" TEXT NOT NULL,
  "city" TEXT NOT NULL DEFAULT '',
  "neighborhood" TEXT,
  "postal_code" TEXT,
  "rent" TEXT NOT NULL DEFAULT 0,
  "deposit" TEXT NOT NULL DEFAULT 0,
  "bedrooms" TEXT NOT NULL DEFAULT 0,
  "bathrooms" TEXT NOT NULL DEFAULT 0,
  "square_feet" INTEGER,
  "description" TEXT,
  "amenities" TEXT NOT NULL DEFAULT '[]',
  "lockbox_code" TEXT,
  "photos" TEXT NOT NULL DEFAULT '[]',
  "status" TEXT NOT NULL DEFAULT 'available',
  "available_date" TEXT,
  "pet_policy" TEXT,
  "parking_included" INTEGER NOT NULL DEFAULT 0,
  "utilities_included" TEXT NOT NULL DEFAULT '[]',
  "video_walkthrough_url" TEXT,
  "workflow_phase" TEXT NOT NULL DEFAULT 'onboarding',
  "inspection_status" TEXT NOT NULL DEFAULT 'not_started',
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("company_id") REFERENCES "companies" ("id"),
  FOREIGN KEY ("area_id") REFERENCES "areas" ("id"),
  FOREIGN KEY ("building_id") REFERENCES "buildings" ("id"),
  FOREIGN KEY ("landlord_id") REFERENCES "landlords" ("id"),
  FOREIGN KEY ("owner_id") REFERENCES "profiles" ("id")
);

CREATE TABLE IF NOT EXISTS "property_photos" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "property_id" TEXT NOT NULL,
  "url" TEXT NOT NULL,
  "is_primary" INTEGER NOT NULL DEFAULT 0,
  "caption" TEXT,
  "order_index" INTEGER NOT NULL DEFAULT 0,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("property_id") REFERENCES "properties" ("id")
);

CREATE TABLE IF NOT EXISTS "showings" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "company_id" TEXT NOT NULL,
  "property_id" TEXT NOT NULL,
  "landlord_id" TEXT,
  "agent_id" TEXT,
  "prospect_name" TEXT,
  "prospect_email" TEXT,
  "prospect_phone" TEXT,
  "scheduled_date" TEXT NOT NULL,
  "scheduled_time" TEXT,
  "status" TEXT NOT NULL DEFAULT 'scheduled',
  "notes" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("company_id") REFERENCES "companies" ("id"),
  FOREIGN KEY ("property_id") REFERENCES "properties" ("id"),
  FOREIGN KEY ("landlord_id") REFERENCES "landlords" ("id"),
  FOREIGN KEY ("agent_id") REFERENCES "profiles" ("id")
);

CREATE TABLE IF NOT EXISTS "signing_audit_log" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "signing_request_id" TEXT NOT NULL,
  "action" TEXT NOT NULL,
  "actor_email" TEXT,
  "ip_address" TEXT,
  "user_agent" TEXT,
  "metadata" TEXT NOT NULL DEFAULT '{}',
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("signing_request_id") REFERENCES "signing_requests" ("id")
);

CREATE TABLE IF NOT EXISTS "signing_requests" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "company_id" TEXT NOT NULL,
  "document_id" TEXT,
  "title" TEXT NOT NULL,
  "status" TEXT NOT NULL DEFAULT 'pending',
  "sender_id" TEXT NOT NULL,
  "recipient_email" TEXT NOT NULL,
  "recipient_name" TEXT,
  "message" TEXT,
  "document_url" TEXT,
  "signing_token" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "signed_at" TEXT,
  "signature_data" TEXT,
  "signed_document_url" TEXT,
  "expires_at" TEXT NOT NULL,
  "viewed_at" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("company_id") REFERENCES "companies" ("id"),
  FOREIGN KEY ("document_id") REFERENCES "documents" ("id")
);

CREATE TABLE IF NOT EXISTS "social_accounts" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "company_id" TEXT NOT NULL,
  "late_account_id" TEXT NOT NULL,
  "platform" TEXT NOT NULL,
  "account_name" TEXT NOT NULL DEFAULT '',
  "account_avatar" TEXT,
  "status" TEXT NOT NULL DEFAULT 'active',
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("company_id") REFERENCES "companies" ("id")
);

CREATE TABLE IF NOT EXISTS "social_posts" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "company_id" TEXT NOT NULL,
  "created_by" TEXT,
  "late_post_id" TEXT,
  "content" TEXT NOT NULL DEFAULT '',
  "media_urls" TEXT NOT NULL DEFAULT '[]',
  "hashtags" TEXT NOT NULL DEFAULT '[]',
  "platforms" TEXT NOT NULL DEFAULT '[]',
  "status" TEXT NOT NULL DEFAULT 'draft',
  "scheduled_for" TEXT,
  "published_at" TEXT,
  "error_message" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("company_id") REFERENCES "companies" ("id")
);

CREATE TABLE IF NOT EXISTS "stripe_connect_accounts" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "company_id" TEXT NOT NULL,
  "stripe_account_id" TEXT NOT NULL,
  "onboarding_complete" INTEGER NOT NULL DEFAULT 0,
  "charges_enabled" INTEGER NOT NULL DEFAULT 0,
  "payouts_enabled" INTEGER NOT NULL DEFAULT 0,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("company_id") REFERENCES "companies" ("id")
);

CREATE TABLE IF NOT EXISTS "team_invitations" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "company_id" TEXT NOT NULL,
  "email" TEXT NOT NULL,
  "role" TEXT NOT NULL,
  "token" TEXT NOT NULL,
  "status" TEXT NOT NULL DEFAULT 'pending',
  "invited_by" TEXT,
  "accepted_by" TEXT,
  "accepted_at" TEXT,
  "expires_at" TEXT NOT NULL,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "team_invitations_role_check" CHECK ((role IN ('admin', 'agent', 'landlord', 'tenant'))),
  CONSTRAINT "team_invitations_status_check" CHECK ((status IN ('pending', 'accepted', 'expired', 'revoked'))),
  FOREIGN KEY ("company_id") REFERENCES "companies" ("id"),
  FOREIGN KEY ("invited_by") REFERENCES "profiles" ("id"),
  FOREIGN KEY ("accepted_by") REFERENCES "profiles" ("id")
);

CREATE TABLE IF NOT EXISTS "tenant_payments" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "company_id" TEXT NOT NULL,
  "property_id" TEXT,
  "tenant_name" TEXT NOT NULL,
  "tenant_email" TEXT,
  "amount" TEXT NOT NULL,
  "description" TEXT,
  "status" TEXT NOT NULL DEFAULT 'pending',
  "stripe_payment_intent_id" TEXT,
  "stripe_checkout_session_id" TEXT,
  "paid_at" TEXT,
  "created_by" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("company_id") REFERENCES "companies" ("id"),
  FOREIGN KEY ("property_id") REFERENCES "properties" ("id"),
  FOREIGN KEY ("created_by") REFERENCES "profiles" ("id")
);

CREATE TABLE IF NOT EXISTS "walkthrough_jobs" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "company_id" TEXT NOT NULL,
  "property_id" TEXT NOT NULL,
  "created_by" TEXT,
  "status" TEXT NOT NULL DEFAULT 'pending',
  "photo_count" INTEGER NOT NULL DEFAULT 0,
  "runpod_job_id" TEXT,
  "error_message" TEXT,
  "progress_pct" INTEGER NOT NULL DEFAULT 0,
  "share_token" TEXT NOT NULL,
  "splat_r2_key" TEXT,
  "preview_r2_key" TEXT,
  "splat_size_bytes" INTEGER,
  "started_at" TEXT,
  "completed_at" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "walkthrough_jobs_photo_count_check" CHECK (((photo_count >= 0) AND (photo_count <= 500))),
  CONSTRAINT "walkthrough_jobs_progress_pct_check" CHECK (((progress_pct >= 0) AND (progress_pct <= 100))),
  FOREIGN KEY ("company_id") REFERENCES "companies" ("id"),
  FOREIGN KEY ("property_id") REFERENCES "properties" ("id")
);

CREATE TABLE IF NOT EXISTS "webhook_events" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "company_id" TEXT NOT NULL,
  "event_type" TEXT NOT NULL,
  "payload" TEXT NOT NULL,
  "status" TEXT NOT NULL DEFAULT 'pending',
  "attempts" INTEGER NOT NULL DEFAULT 0,
  "last_attempt_at" TEXT,
  "error_message" TEXT,
  "response_code" INTEGER,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("company_id") REFERENCES "companies" ("id")
);

-- indexes
CREATE UNIQUE INDEX IF NOT EXISTS "companies_pkey" ON "companies" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "companies_slug_key" ON "companies" (slug);
CREATE UNIQUE INDEX IF NOT EXISTS "profiles_pkey" ON "profiles" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "profiles_email_lower_idx" ON "profiles" (lower(email));
CREATE INDEX IF NOT EXISTS "profiles_company_id_idx" ON "profiles" (company_id);
CREATE UNIQUE INDEX IF NOT EXISTS "areas_pkey" ON "areas" (id);
CREATE INDEX IF NOT EXISTS "areas_company_idx" ON "areas" (company_id);
CREATE UNIQUE INDEX IF NOT EXISTS "buildings_pkey" ON "buildings" (id);
CREATE INDEX IF NOT EXISTS "buildings_company_idx" ON "buildings" (company_id);
CREATE UNIQUE INDEX IF NOT EXISTS "landlords_pkey" ON "landlords" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "properties_pkey" ON "properties" (id);
CREATE INDEX IF NOT EXISTS "properties_company_idx" ON "properties" (company_id);
CREATE INDEX IF NOT EXISTS "properties_status_idx" ON "properties" (company_id, status);
CREATE UNIQUE INDEX IF NOT EXISTS "property_photos_pkey" ON "property_photos" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "applications_pkey" ON "applications" (id);
CREATE INDEX IF NOT EXISTS "applications_company_idx" ON "applications" (company_id);
CREATE INDEX IF NOT EXISTS "applications_status_idx" ON "applications" (company_id, status);
CREATE UNIQUE INDEX IF NOT EXISTS "application_documents_pkey" ON "application_documents" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "application_screening_reports_pkey" ON "application_screening_reports" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "activity_log_pkey" ON "activity_log" (id);
CREATE INDEX IF NOT EXISTS "activity_log_company_created_idx" ON "activity_log" (company_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "audit_logs_pkey" ON "audit_logs" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "documents_pkey" ON "documents" (id);
CREATE INDEX IF NOT EXISTS "documents_company_idx" ON "documents" (company_id);
CREATE UNIQUE INDEX IF NOT EXISTS "invoices_pkey" ON "invoices" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "invoices_company_id_invoice_number_key" ON "invoices" (company_id, invoice_number);
CREATE INDEX IF NOT EXISTS "invoices_company_idx" ON "invoices" (company_id);
CREATE UNIQUE INDEX IF NOT EXISTS "invoice_items_pkey" ON "invoice_items" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "showings_pkey" ON "showings" (id);
CREATE INDEX IF NOT EXISTS "showings_company_date_idx" ON "showings" (company_id, scheduled_date);
CREATE UNIQUE INDEX IF NOT EXISTS "leases_pkey" ON "leases" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "maintenance_requests_pkey" ON "maintenance_requests" (id);
CREATE INDEX IF NOT EXISTS "maintenance_company_status_idx" ON "maintenance_requests" (company_id, status);
CREATE UNIQUE INDEX IF NOT EXISTS "notifications_pkey" ON "notifications" (id);
CREATE INDEX IF NOT EXISTS "notifications_user_created_idx" ON "notifications" (user_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "contacts_pkey" ON "contacts" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "commissions_pkey" ON "commissions" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "inspections_pkey" ON "inspections" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "inspection_items_pkey" ON "inspection_items" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "team_invitations_pkey" ON "team_invitations" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "team_invitations_token_key" ON "team_invitations" (token);
CREATE UNIQUE INDEX IF NOT EXISTS "team_invitations_company_id_email_key" ON "team_invitations" (company_id, email);
CREATE UNIQUE INDEX IF NOT EXISTS "automation_subscriptions_pkey" ON "automation_subscriptions" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "automation_subscriptions_company_id_key" ON "automation_subscriptions" (company_id);
CREATE UNIQUE INDEX IF NOT EXISTS "automation_settings_pkey" ON "automation_settings" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "automation_settings_company_id_key" ON "automation_settings" (company_id);
CREATE UNIQUE INDEX IF NOT EXISTS "automation_logs_pkey" ON "automation_logs" (id);
CREATE INDEX IF NOT EXISTS "automation_logs_company_idx" ON "automation_logs" (company_id, triggered_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "automation_configs_pkey" ON "automation_configs" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "automation_configs_company_id_type_key" ON "automation_configs" (company_id, type);
CREATE UNIQUE INDEX IF NOT EXISTS "automation_executions_pkey" ON "automation_executions" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "webhook_events_pkey" ON "webhook_events" (id);
CREATE INDEX IF NOT EXISTS "webhook_events_pending_idx" ON "webhook_events" (status, created_at) WHERE (status IN ('pending', 'retrying'));
CREATE UNIQUE INDEX IF NOT EXISTS "gmail_oauth_tokens_pkey" ON "gmail_oauth_tokens" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "gmail_oauth_tokens_company_id_email_key" ON "gmail_oauth_tokens" (company_id, email);
CREATE UNIQUE INDEX IF NOT EXISTS "tenant_payments_pkey" ON "tenant_payments" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "stripe_connect_accounts_pkey" ON "stripe_connect_accounts" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "stripe_connect_accounts_company_id_key" ON "stripe_connect_accounts" (company_id);
CREATE UNIQUE INDEX IF NOT EXISTS "stripe_connect_accounts_stripe_account_id_key" ON "stripe_connect_accounts" (stripe_account_id);
CREATE UNIQUE INDEX IF NOT EXISTS "landlord_properties_pkey" ON "landlord_properties" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "landlord_properties_landlord_id_property_id_key" ON "landlord_properties" (landlord_id, property_id);
CREATE UNIQUE INDEX IF NOT EXISTS "agent_social_profiles_pkey" ON "agent_social_profiles" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "agent_social_profiles_user_id_key" ON "agent_social_profiles" (user_id);
CREATE UNIQUE INDEX IF NOT EXISTS "social_accounts_pkey" ON "social_accounts" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "social_accounts_company_id_late_account_id_key" ON "social_accounts" (company_id, late_account_id);
CREATE UNIQUE INDEX IF NOT EXISTS "social_posts_pkey" ON "social_posts" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "signing_requests_pkey" ON "signing_requests" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "signing_requests_signing_token_key" ON "signing_requests" (signing_token);
CREATE INDEX IF NOT EXISTS "signing_requests_company_idx" ON "signing_requests" (company_id);
CREATE UNIQUE INDEX IF NOT EXISTS "signing_audit_log_pkey" ON "signing_audit_log" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "walkthrough_jobs_pkey" ON "walkthrough_jobs" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "walkthrough_jobs_share_token_key" ON "walkthrough_jobs" (share_token);
CREATE INDEX IF NOT EXISTS "walkthrough_jobs_company_idx" ON "walkthrough_jobs" (company_id);
CREATE UNIQUE INDEX IF NOT EXISTS "platform_invitations_pkey" ON "platform_invitations" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "platform_invitations_token_key" ON "platform_invitations" (token);
CREATE UNIQUE INDEX IF NOT EXISTS "incoming_webhook_events_pkey" ON "incoming_webhook_events" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "incoming_webhook_events_provider_event_id_key" ON "incoming_webhook_events" (provider, event_id);
CREATE INDEX IF NOT EXISTS "incoming_webhook_events_expires_idx" ON "incoming_webhook_events" (expires_at);
CREATE UNIQUE INDEX IF NOT EXISTS "api_rate_limits_pkey" ON "api_rate_limits" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "api_rate_limits_scope_window_start_key" ON "api_rate_limits" (scope, window_start);
CREATE INDEX IF NOT EXISTS "api_rate_limits_expires_idx" ON "api_rate_limits" (expires_at);
