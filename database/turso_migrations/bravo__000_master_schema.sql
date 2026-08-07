-- bravo-empire master schema — transpiled from live Supabase
-- project ref: phctllmtsogkovoilwos  generated: 2026-08-07T02:40:48+00:00
-- tables: 161  indexes emitted: 545  views emitted: 2
--
-- NOT TRANSPILED (DAL responsibility — see scripts/lib/db_turso.py):
--   PL/pgSQL functions (60): ack_event, agents_touch_updated_at, approve_sunbiz_draft, bump_tenant_record_last_contact, calculate_activation_score, claim_events, claim_texttorrent_partition, client_signatures_append_only, consume_texttorrent_rate_token, conv_normalize_phone, conv_resolve_interaction_owner, conv_sync_lead_assignment, conv_thread_set_owner, conv_thread_upsert, decay_confidence_scores, exec_sql, fail_event, fail_texttorrent_inbound, finalize_texttorrent_inbound, find_similar_merchants...
--   Triggers (27): agent_events.trg_notify_agent_event, agent_model_config.trg_agent_model_config_updated_at, agents.agents_set_updated_at, application_lender_threads.trg_lender_threads_updated_at, bridge_pairings.trg_bridge_pairings_protect_owner, chat_sessions.trg_chat_sessions_updated_at, client_signatures.client_signatures_no_mutate, daily_plans.trg_daily_plans_updated_at, drip_sequences.trg_drip_sequences_updated_at, email_templates.email_templates_updated_at...
--   RLS policies: replaced by mandatory tenant scoping in db_turso.py
--   cross-schema FKs dropped (16, e.g. auth.users): agent_model_config(user_id) -> auth.users; agents(created_by) -> auth.users; bridge_pairings(user_id) -> auth.users; chat_attachments(auth_user_id) -> auth.users; chat_sessions(user_id) -> auth.users; drip_sequences(created_by) -> auth.users
--   FKs dropped as unenforceable in SQLite (0) — parent columns not unique in the emitted schema; enforce in the DAL
--   defaults dropped (11) and non-btree/expression indexes skipped (12): see turso_migrations/bravo__transpile_report.json
--
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS "_ddl_probe_tmp" (
  "id" INTEGER
);

CREATE TABLE IF NOT EXISTS "agent_activity" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "agent" TEXT NOT NULL,
  "status" TEXT NOT NULL,
  "task" TEXT NOT NULL,
  "files" TEXT,
  "branch" TEXT,
  "detail" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "agent_email_settings" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "user_id" TEXT NOT NULL,
  "mode" TEXT NOT NULL DEFAULT 'off',
  "work_enabled" INTEGER NOT NULL DEFAULT 1,
  "personal_enabled" INTEGER NOT NULL DEFAULT 0,
  "daily_send_cap" INTEGER NOT NULL DEFAULT 100,
  "last_processed_at" TEXT,
  "detail" TEXT NOT NULL DEFAULT '{}',
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "agent_email_settings_mode_check" CHECK ((mode IN ('off', 'monitor', 'draft', 'semi', 'full')))
);

CREATE TABLE IF NOT EXISTS "agent_email_snapshots" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "user_id" TEXT NOT NULL,
  "captured_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "emails_in" INTEGER NOT NULL DEFAULT 0,
  "emails_out" INTEGER NOT NULL DEFAULT 0,
  "median_response_sec" INTEGER,
  "awaiting_reply" INTEGER NOT NULL DEFAULT 0,
  "deals_with_email" INTEGER NOT NULL DEFAULT 0,
  "lender_declines" INTEGER NOT NULL DEFAULT 0,
  "detail" TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "agent_events" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "event_type" TEXT NOT NULL,
  "publisher_agent" TEXT NOT NULL,
  "target_agent" TEXT,
  "severity" TEXT NOT NULL DEFAULT 'info',
  "payload" TEXT NOT NULL DEFAULT '{}',
  "correlation_id" TEXT,
  "published_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "consumed_by" TEXT DEFAULT '[]',
  "expires_at" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "source_agent" TEXT NOT NULL DEFAULT 'unknown',
  "idempotency_key" TEXT,
  "status" TEXT NOT NULL DEFAULT 'pending',
  "processed_at" TEXT,
  "processed_by" TEXT,
  "retry_count" INTEGER NOT NULL DEFAULT 0,
  "last_error" TEXT,
  "visibility_until" TEXT,
  PRIMARY KEY ("id"),
  CONSTRAINT "agent_events_severity_check" CHECK ((severity IN ('info', 'warn', 'error', 'critical'))),
  CONSTRAINT "agent_events_status_check" CHECK ((status IN ('pending', 'processing', 'done', 'failed', 'dead')))
);

CREATE TABLE IF NOT EXISTS "agent_memory_notes" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "entity_type" TEXT NOT NULL,
  "entity_id" TEXT,
  "note_text" TEXT NOT NULL,
  "author_user_id" TEXT,
  "author_kind" TEXT NOT NULL DEFAULT 'operator',
  "tags" TEXT DEFAULT '[]',
  "pinned" INTEGER NOT NULL DEFAULT 0,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "agent_nurture_settings" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "user_id" TEXT NOT NULL,
  "mode" TEXT NOT NULL DEFAULT 'off',
  "notify_channel" TEXT DEFAULT 'telegram',
  "from_number" TEXT,
  "act_as_email" TEXT,
  "rep_name" TEXT,
  "rep_email" TEXT,
  "rep_phone" TEXT,
  "voice_seed" TEXT,
  "last_processed_at" TEXT,
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "voice_seed_version" INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "agent_nurture_voice_history" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "user_id" TEXT,
  "act_as_email" TEXT,
  "rep_name" TEXT,
  "voice_seed" TEXT,
  "prev_voice_seed" TEXT,
  "mode" TEXT,
  "summary" TEXT,
  "request_text" TEXT,
  "source" TEXT NOT NULL DEFAULT 'tune',
  "changed_by" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "agent_nurture_voice_history_source_check" CHECK ((source IN ('tune', 'rollback', 'reset', 'mode', 'drip')))
);

CREATE TABLE IF NOT EXISTS "agent_rep_identity" (
  "tenant_id" TEXT NOT NULL,
  "rep_user_id" TEXT NOT NULL,
  "rep_key" TEXT,
  "act_as_email" TEXT,
  "display_name" TEXT,
  "email_scan" TEXT NOT NULL DEFAULT 'none',
  "sms_scan" TEXT NOT NULL DEFAULT 'none',
  "notes" TEXT,
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("tenant_id", "rep_user_id"),
  CONSTRAINT "agent_rep_identity_email_scan_check" CHECK ((email_scan IN ('imap_apppassword', 'gmail_oauth', 'none'))),
  CONSTRAINT "agent_rep_identity_sms_scan_check" CHECK ((sms_scan IN ('texttorrent', 'none')))
);

CREATE TABLE IF NOT EXISTS "agent_state" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "confidence_level" TEXT DEFAULT 0.80,
  "focus_area" TEXT DEFAULT 'general',
  "energy_level" TEXT DEFAULT 'HIGH',
  "last_heartbeat" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "active_goals" TEXT DEFAULT '[]',
  "known_issues" TEXT DEFAULT '[]',
  "system_health" TEXT DEFAULT '{}',
  "updated_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "agent_state_confidence_level_check" CHECK (((confidence_level >= (0)) AND (confidence_level <= (1)))),
  CONSTRAINT "agent_state_energy_level_check" CHECK ((energy_level IN ('HIGH', 'MEDIUM', 'LOW', 'CRITICAL')))
);

CREATE TABLE IF NOT EXISTS "agent_state_snapshot" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "agent_name" TEXT NOT NULL,
  "tick_count" INTEGER DEFAULT 0,
  "last_tick_at" TEXT,
  "last_tick_id" TEXT,
  "working_memory" TEXT DEFAULT '{}',
  "pending_actions" TEXT DEFAULT '[]',
  "health_status" TEXT DEFAULT 'ok',
  "updated_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "agent_traces" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "trace_id" TEXT NOT NULL,
  "span_id" TEXT NOT NULL,
  "parent_span_id" TEXT,
  "timestamp" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "agent_interface" TEXT NOT NULL,
  "event_type" TEXT NOT NULL,
  "event_name" TEXT NOT NULL,
  "input_summary" TEXT,
  "output_summary" TEXT,
  "duration_ms" INTEGER,
  "confidence" TEXT,
  "status" TEXT NOT NULL DEFAULT 'success',
  "metadata" TEXT DEFAULT '{}',
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "agent_traces_agent_interface_check" CHECK ((agent_interface IN ('claude_code', 'anti_gravity', 'blackbox', 'telegram', 'n8n'))),
  CONSTRAINT "agent_traces_confidence_check" CHECK (((confidence >= (0)) AND (confidence <= (1)))),
  CONSTRAINT "agent_traces_event_type_check" CHECK ((event_type IN ('task_start', 'task_complete', 'task_fail', 'tool_call', 'decision', 'error', 'self_modify', 'memory_write', 'heartbeat', 'brain_loop_step'))),
  CONSTRAINT "agent_traces_status_check" CHECK ((status IN ('success', 'fail', 'partial', 'skipped')))
);

CREATE TABLE IF NOT EXISTS "agent_voice_profile_history" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "rep_user_id" TEXT NOT NULL,
  "channel" TEXT NOT NULL,
  "override_notes" TEXT,
  "prev_override_notes" TEXT,
  "summary" TEXT,
  "request_text" TEXT,
  "source" TEXT,
  "changed_by" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "agent_voice_profile_history_channel_check" CHECK ((channel IN ('sms', 'email')))
);

CREATE TABLE IF NOT EXISTS "agent_voice_profiles" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "rep_user_id" TEXT NOT NULL,
  "channel" TEXT NOT NULL,
  "style_descriptors" TEXT NOT NULL DEFAULT '{}',
  "compiled_prompt" TEXT,
  "example_snippets" TEXT NOT NULL DEFAULT '[]',
  "source_message_count" INTEGER NOT NULL DEFAULT 0,
  "confidence" TEXT NOT NULL DEFAULT 'low',
  "corpus_window_start" TEXT,
  "corpus_window_end" TEXT,
  "model_used" TEXT,
  "refreshed_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "override_notes" TEXT,
  "override_examples" TEXT NOT NULL DEFAULT '[]',
  "override_version" INTEGER NOT NULL DEFAULT 0,
  "override_locked" INTEGER NOT NULL DEFAULT 0,
  "override_updated_at" TEXT,
  "override_updated_by" TEXT,
  "override_source" TEXT,
  "approved" INTEGER NOT NULL DEFAULT 0,
  "approved_at" TEXT,
  "approved_by" TEXT,
  PRIMARY KEY ("id"),
  CONSTRAINT "agent_voice_profiles_channel_check" CHECK ((channel IN ('sms', 'email'))),
  CONSTRAINT "agent_voice_profiles_confidence_check" CHECK ((confidence IN ('low', 'med', 'high')))
);

CREATE TABLE IF NOT EXISTS "application_signing_requests" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "lead_id" TEXT NOT NULL,
  "application_id" TEXT,
  "status" TEXT NOT NULL DEFAULT 'sent',
  "token_sha256" TEXT NOT NULL,
  "created_by" TEXT NOT NULL,
  "sent_to_email" TEXT,
  "sent_to_phone" TEXT,
  "expires_at" TEXT NOT NULL,
  "signed_at" TEXT,
  "signed_ip" TEXT,
  "signed_user_agent" TEXT,
  "signer_name" TEXT,
  "signed_document_id" TEXT,
  "signed_document_sha256" TEXT,
  "consent_disclosure_version" TEXT,
  "otp_verified" INTEGER NOT NULL DEFAULT 0,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "application_underwriting" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "application_id" TEXT NOT NULL,
  "run_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "triggered_by" TEXT NOT NULL DEFAULT 'automatic',
  "triggered_by_user_id" TEXT,
  "status" TEXT NOT NULL DEFAULT 'pending',
  "parser_output" TEXT,
  "debt_analysis" TEXT,
  "sales_angle" TEXT,
  "avg_monthly_revenue" TEXT,
  "avg_daily_balance" TEXT,
  "nsf_count" INTEGER,
  "deposit_consistency_pct" TEXT,
  "debt_service_monthly" TEXT,
  "debt_to_revenue_ratio" TEXT,
  "lender_count" INTEGER,
  "risk_flags" TEXT DEFAULT '[]',
  "readiness_score" INTEGER,
  "error_message" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "booking_slots" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "slot_date" TEXT NOT NULL,
  "start_time" TEXT NOT NULL,
  "end_time" TEXT NOT NULL,
  "meeting_type" TEXT NOT NULL DEFAULT 'discovery',
  "is_available" INTEGER DEFAULT 1,
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "bridge_activity" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "agent" TEXT NOT NULL,
  "status" TEXT NOT NULL,
  "task" TEXT NOT NULL,
  "files" TEXT,
  "branch" TEXT,
  "detail" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "call_appointments" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "lead_id" TEXT NOT NULL,
  "entity_type" TEXT NOT NULL DEFAULT 'lead',
  "scheduled_for" TEXT NOT NULL,
  "assigned_to" TEXT,
  "status" TEXT NOT NULL DEFAULT 'scheduled',
  "pre_call_note" TEXT,
  "outcome_note" TEXT,
  "created_by" TEXT NOT NULL,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "completed_at" TEXT,
  PRIMARY KEY ("id"),
  CONSTRAINT "call_appointments_status_check" CHECK ((status IN ('scheduled', 'completed', 'no_answer', 'cancelled', 'rescheduled')))
);

CREATE TABLE IF NOT EXISTS "cold_lead_lists" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "name" TEXT NOT NULL,
  "source" TEXT,
  "description" TEXT,
  "row_count" INTEGER NOT NULL DEFAULT 0,
  "promoted_count" INTEGER NOT NULL DEFAULT 0,
  "created_by_user_id" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "archived_at" TEXT,
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "cold_sending_mailboxes" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "domain" TEXT NOT NULL,
  "address" TEXT NOT NULL,
  "provider" TEXT NOT NULL DEFAULT 'app_password',
  "app_password_enc" TEXT,
  "api_ref" TEXT,
  "daily_cap" INTEGER NOT NULL DEFAULT 30,
  "sends_today" INTEGER NOT NULL DEFAULT 0,
  "sends_date" TEXT,
  "last_send_at" TEXT,
  "warmup_status" TEXT NOT NULL DEFAULT 'warming',
  "active" INTEGER NOT NULL DEFAULT 1,
  "notes" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "cold_sending_mailboxes_warmup_status_check" CHECK ((warmup_status IN ('warming', 'ready', 'paused')))
);

CREATE TABLE IF NOT EXISTS "content_calendar" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "platform" TEXT NOT NULL,
  "content_type" TEXT NOT NULL DEFAULT 'post',
  "pillar" TEXT,
  "title" TEXT,
  "body" TEXT NOT NULL,
  "media_url" TEXT,
  "hashtags" TEXT DEFAULT '[]',
  "scheduled_for" TEXT,
  "posted_at" TEXT,
  "late_post_id" TEXT,
  "status" TEXT NOT NULL DEFAULT 'draft',
  "engagement" TEXT DEFAULT '{}',
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "content_templates" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "name" TEXT NOT NULL,
  "platform" TEXT NOT NULL,
  "pillar" TEXT,
  "template_body" TEXT NOT NULL,
  "variables" TEXT DEFAULT '[]',
  "example_output" TEXT,
  "times_used" INTEGER DEFAULT 0,
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "daily_logs" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "log_date" TEXT NOT NULL,
  "activities" TEXT DEFAULT '[]',
  "learnings" TEXT DEFAULT '[]',
  "emotional_state" TEXT DEFAULT '{"focus": "general", "energy": "HIGH", "confidence": 0.8}',
  "goals_progress" TEXT DEFAULT '{}',
  "sessions_count" INTEGER DEFAULT 0,
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "daily_plan_items" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "plan_date" TEXT NOT NULL,
  "assignee_user_id" TEXT,
  "lead_id" TEXT,
  "application_id" TEXT,
  "category" TEXT NOT NULL,
  "priority" INTEGER NOT NULL DEFAULT 50,
  "reason" TEXT NOT NULL,
  "metadata" TEXT DEFAULT '{}',
  "status" TEXT NOT NULL DEFAULT 'open',
  "completed_at" TEXT,
  "dismissed_at" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "document_extraction_jobs" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "lead_id" TEXT,
  "application_id" TEXT,
  "lead_document_id" TEXT,
  "storage_path" TEXT NOT NULL,
  "mime_type" TEXT NOT NULL,
  "source" TEXT NOT NULL,
  "assigned_to" TEXT,
  "uploaded_by" TEXT,
  "status" TEXT NOT NULL DEFAULT 'queued',
  "attempts" INTEGER NOT NULL DEFAULT 0,
  "used_fallback" INTEGER NOT NULL DEFAULT 0,
  "result_json" TEXT,
  "error" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "drift_alerts" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "metric_name" TEXT NOT NULL,
  "dimension_key" TEXT,
  "observed_value" TEXT,
  "baseline_mean" TEXT,
  "baseline_stddev" TEXT,
  "z_score" TEXT,
  "severity" TEXT,
  "acknowledged" INTEGER DEFAULT 0,
  "acknowledged_at" TEXT,
  "notes" TEXT,
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "drift_alerts_severity_check" CHECK ((severity IN ('warn', 'alert', 'critical')))
);

CREATE TABLE IF NOT EXISTS "drift_baselines" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "metric_name" TEXT NOT NULL,
  "dimension_key" TEXT,
  "baseline_mean" TEXT,
  "baseline_stddev" TEXT,
  "sample_window_days" INTEGER DEFAULT 28,
  "sample_count" INTEGER DEFAULT 0,
  "computed_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "drip_runs" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "lead_id" TEXT NOT NULL,
  "sequence_id" TEXT NOT NULL,
  "sequence_name" TEXT,
  "step_index" INTEGER NOT NULL DEFAULT 0,
  "channel" TEXT,
  "scheduled_for" TEXT NOT NULL,
  "status" TEXT NOT NULL DEFAULT 'scheduled',
  "attempts" INTEGER NOT NULL DEFAULT 0,
  "last_error" TEXT,
  "from_identity" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "sent_at" TEXT,
  "claimed_at" TEXT,
  "provider_message_id" TEXT,
  PRIMARY KEY ("id"),
  CONSTRAINT "drip_runs_channel_check" CHECK ((channel IN ('sms', 'email'))),
  CONSTRAINT "drip_runs_status_check" CHECK ((status IN ('scheduled', 'sending', 'sent', 'failed', 'cancelled', 'done')))
);

CREATE TABLE IF NOT EXISTS "email_templates" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "name" TEXT NOT NULL,
  "subject" TEXT NOT NULL,
  "body_html" TEXT NOT NULL,
  "body_text" TEXT,
  "category" TEXT NOT NULL DEFAULT 'nurture',
  "variables" TEXT DEFAULT '[]',
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "email_thread_monitors" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "monitor_kind" TEXT NOT NULL,
  "gmail_label" TEXT NOT NULL,
  "last_checked_at" TEXT,
  "last_message_id" TEXT,
  "next_check_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "status" TEXT NOT NULL DEFAULT 'active',
  "last_error" TEXT,
  "messages_seen" INTEGER NOT NULL DEFAULT 0,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "esign_envelopes" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "created_by" TEXT NOT NULL,
  "title" TEXT NOT NULL,
  "status" TEXT NOT NULL DEFAULT 'draft',
  "source_storage_key" TEXT,
  "source_document_id" TEXT,
  "source_pdf_sha256" TEXT,
  "signed_storage_key" TEXT,
  "signed_document_id" TEXT,
  "signed_pdf_sha256" TEXT,
  "lead_id" TEXT,
  "application_id" TEXT,
  "consent_disclosure_version" TEXT DEFAULT 'v1',
  "message" TEXT,
  "expires_at" TEXT,
  "completed_at" TEXT,
  "void_reason" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "follow_up_tasks" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "lead_id" TEXT,
  "application_id" TEXT,
  "assignee_user_id" TEXT,
  "reason" TEXT NOT NULL,
  "reason_detail" TEXT,
  "due_at" TEXT NOT NULL,
  "status" TEXT NOT NULL DEFAULT 'open',
  "attempt_count" INTEGER NOT NULL DEFAULT 0,
  "last_attempt_at" TEXT,
  "last_attempt_outcome" TEXT,
  "snoozed_until" TEXT,
  "completed_at" TEXT,
  "completed_note" TEXT,
  "source" TEXT NOT NULL DEFAULT 'auto',
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "funnel_leads" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "name" TEXT NOT NULL,
  "email" TEXT NOT NULL,
  "instagram_handle" TEXT,
  "interests" TEXT NOT NULL DEFAULT '[]',
  "business_name" TEXT,
  "business_type" TEXT,
  "biggest_pain" TEXT,
  "event_type" TEXT,
  "event_date" TEXT,
  "music_vibe" TEXT,
  "brand_goal" TEXT,
  "audience" TEXT,
  "current_following" TEXT,
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "follow_up_count" INTEGER DEFAULT 0,
  "last_follow_up" TEXT,
  "status" TEXT DEFAULT 'new',
  "phone" TEXT,
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "funnels" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "name" TEXT NOT NULL,
  "slug" TEXT NOT NULL,
  "description" TEXT,
  "stages" TEXT NOT NULL DEFAULT '["awareness", "interest", "consideration", "intent", "evaluation", "purchase"]',
  "is_active" INTEGER DEFAULT 1,
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "growth_log" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "category" TEXT NOT NULL,
  "description" TEXT NOT NULL,
  "evidence" TEXT,
  "confidence_score" TEXT DEFAULT 0.80,
  "impact" TEXT,
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "growth_log_category_check" CHECK ((category IN ('skill_acquired', 'pattern_learned', 'mistake_corrected', 'capability_expanded', 'sop_created', 'integration_added'))),
  CONSTRAINT "growth_log_confidence_score_check" CHECK (((confidence_score >= (0)) AND (confidence_score <= (1)))),
  CONSTRAINT "growth_log_impact_check" CHECK ((impact IN ('high', 'medium', 'low')))
);

CREATE TABLE IF NOT EXISTS "heartbeat_tasks" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "task_name" TEXT NOT NULL,
  "description" TEXT,
  "schedule_interval" TEXT NOT NULL,
  "conditions" TEXT DEFAULT '{}',
  "action_template" TEXT NOT NULL,
  "priority" TEXT DEFAULT 'medium',
  "is_active" INTEGER DEFAULT 1,
  "last_run" TEXT,
  "next_run" TEXT,
  "run_count" INTEGER DEFAULT 0,
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "heartbeat_tasks_priority_check" CHECK ((priority IN ('critical', 'high', 'medium', 'low')))
);

CREATE TABLE IF NOT EXISTS "known_funding_companies" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "name" TEXT NOT NULL,
  "aliases" TEXT DEFAULT '[]',
  "website" TEXT,
  "industry_signal_keywords" TEXT DEFAULT '[]',
  "typical_term_days" INTEGER,
  "typical_buy_rate_min" TEXT,
  "typical_buy_rate_max" TEXT,
  "category" TEXT,
  "active" INTEGER NOT NULL DEFAULT 1,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "tier" INTEGER,
  "paper_grades_accepted" TEXT DEFAULT '[]',
  "contact_email" TEXT,
  "submission_notes" TEXT,
  PRIMARY KEY ("id"),
  CONSTRAINT "known_funding_companies_tier_check" CHECK (((tier >= 1) AND (tier <= 4)))
);

CREATE TABLE IF NOT EXISTS "lead_edges" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "from_lead_id" TEXT NOT NULL,
  "to_lead_id" TEXT NOT NULL,
  "edge_type" TEXT NOT NULL,
  "weight" TEXT DEFAULT 1.00,
  "bidirectional" INTEGER DEFAULT 0,
  "discovered_source" TEXT,
  "notes" TEXT,
  "metadata" TEXT DEFAULT '{}',
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "lead_edges_edge_type_check" CHECK ((edge_type IN ('referral', 'colleague', 'vendor', 'competitor', 'industry_peer', 'acquired_by', 'works_with', 'mentored_by', 'client_of'))),
  CONSTRAINT "lead_edges_weight_check" CHECK (((weight >= 0.00) AND (weight <= 1.00)))
);

CREATE TABLE IF NOT EXISTS "leads_outreach" (
  "email" TEXT NOT NULL,
  "name" TEXT,
  "business" TEXT,
  "type" TEXT,
  "status" TEXT,
  "outreach_date" TEXT,
  "hook" TEXT,
  PRIMARY KEY ("email")
);

CREATE TABLE IF NOT EXISTS "lender_feedback" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "lender_id" TEXT NOT NULL,
  "application_id" TEXT NOT NULL,
  "thread_id" TEXT,
  "outcome" TEXT NOT NULL,
  "industry" TEXT,
  "monthly_revenue" TEXT,
  "time_in_business_months" INTEGER,
  "fico" INTEGER,
  "requested_amount" TEXT,
  "funded_amount" TEXT,
  "funded_term_days" INTEGER,
  "funded_buy_rate" TEXT,
  "decline_reason" TEXT,
  "extracted_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "memories" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "category" TEXT NOT NULL,
  "content" TEXT NOT NULL,
  "confidence_score" TEXT DEFAULT 0.50,
  "source" TEXT DEFAULT 'observed',
  "tags" TEXT DEFAULT '[]',
  "is_active" INTEGER DEFAULT 1,
  "access_count" INTEGER DEFAULT 0,
  "last_accessed" TEXT,
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "memories_category_check" CHECK ((category IN ('decision', 'mistake', 'pattern', 'insight', 'fact', 'preference', 'capability'))),
  CONSTRAINT "memories_confidence_score_check" CHECK (((confidence_score >= (0)) AND (confidence_score <= (1)))),
  CONSTRAINT "memories_source_check" CHECK ((source IN ('observed', 'inferred', 'told', 'tested', 'assumed')))
);

CREATE TABLE IF NOT EXISTS "memories_episodic" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "content" TEXT NOT NULL,
  "context_type" TEXT,
  "related_lead_id" TEXT,
  "related_interaction_id" TEXT,
  "tags" TEXT DEFAULT '[]',
  "confidence" TEXT DEFAULT 0.85,
  "access_count" INTEGER DEFAULT 0,
  "last_accessed" TEXT,
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "expires_at" TEXT,
  "consolidated_into_id" TEXT,
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "memories_procedural" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "workflow_name" TEXT NOT NULL,
  "trigger_conditions" TEXT NOT NULL,
  "steps" TEXT NOT NULL,
  "success_count" INTEGER DEFAULT 0,
  "failure_count" INTEGER DEFAULT 0,
  "last_executed" TEXT,
  "last_success" TEXT,
  "last_failure" TEXT,
  "status" TEXT NOT NULL DEFAULT 'probationary',
  "promoted_at" TEXT,
  "demoted_at" TEXT,
  "demotion_reason" TEXT,
  "owner_agent" TEXT DEFAULT 'bravo',
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "memories_procedural_status_check" CHECK ((status IN ('probationary', 'validated', 'deprecated')))
);

CREATE TABLE IF NOT EXISTS "memories_semantic" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "pattern" TEXT NOT NULL,
  "domain" TEXT,
  "supporting_episodic_ids" TEXT DEFAULT '[]',
  "evidence_count" INTEGER DEFAULT 1,
  "counter_evidence_count" INTEGER DEFAULT 0,
  "confidence" TEXT DEFAULT 0.70,
  "tags" TEXT DEFAULT '[]',
  "access_count" INTEGER DEFAULT 0,
  "last_accessed" TEXT,
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "expires_at" TEXT,
  "promoted_to_procedural_id" TEXT,
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "monthly_metrics" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "month" TEXT NOT NULL,
  "mrr" TEXT NOT NULL DEFAULT 0,
  "new_clients" INTEGER DEFAULT 0,
  "churned_clients" INTEGER DEFAULT 0,
  "pipeline_value" TEXT DEFAULT 0,
  "total_leads" INTEGER DEFAULT 0,
  "conversion_rate" TEXT DEFAULT 0,
  "avg_deal_size" TEXT DEFAULT 0,
  "notes" TEXT,
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "nurture_sequences" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "name" TEXT NOT NULL,
  "description" TEXT,
  "trigger_event" TEXT NOT NULL,
  "steps" TEXT NOT NULL DEFAULT '[]',
  "is_active" INTEGER DEFAULT 1,
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "oasis_quests" (
  "id" TEXT NOT NULL,
  "bucket" TEXT NOT NULL,
  "title" TEXT NOT NULL,
  "owner" TEXT,
  "status" TEXT NOT NULL DEFAULT 'open',
  "source_file" TEXT NOT NULL DEFAULT 'memory/ACTIVE_TASKS.md',
  "source_line" INTEGER,
  "first_seen_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "completed_at" TEXT,
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "offer_sources" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "offer_record_id" TEXT NOT NULL,
  "source_type" TEXT NOT NULL,
  "source_email_id" TEXT,
  "source_portal_url" TEXT,
  "source_user_id" TEXT,
  "extracted_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "extraction_confidence" TEXT,
  "raw_extraction" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "pair_attempts" (
  "id" INTEGER PRIMARY KEY,
  "profile_id" TEXT NOT NULL,
  "outcome" TEXT NOT NULL,
  "attempted_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "ip" TEXT,
  CONSTRAINT "pair_attempts_outcome_check" CHECK ((outcome IN ('ok', 'invalid_hmac', 'invalid_bearer', 'rate_limited', 'missing_headers', 'code_invalid_shape', 'code_not_found', 'code_expired', 'code_consumed', 'code_redeem_failed')))
);

CREATE TABLE IF NOT EXISTS "performance_metrics" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "metric_date" TEXT NOT NULL,
  "agent_interface" TEXT NOT NULL,
  "tasks_attempted" INTEGER DEFAULT 0,
  "tasks_completed" INTEGER DEFAULT 0,
  "tasks_failed" INTEGER DEFAULT 0,
  "tool_calls_total" INTEGER DEFAULT 0,
  "tool_calls_failed" INTEGER DEFAULT 0,
  "avg_confidence" TEXT,
  "avg_task_duration_ms" INTEGER,
  "mistakes_logged" INTEGER DEFAULT 0,
  "patterns_logged" INTEGER DEFAULT 0,
  "sops_created" INTEGER DEFAULT 0,
  "self_modifications" INTEGER DEFAULT 0,
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "personalized_form_links" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "lead_id" TEXT NOT NULL,
  "form_id" TEXT NOT NULL,
  "form_step" INTEGER NOT NULL DEFAULT 1,
  "token" TEXT NOT NULL,
  "sent_via" TEXT,
  "sent_at" TEXT,
  "expires_at" TEXT NOT NULL,
  "first_opened_at" TEXT,
  "last_opened_at" TEXT,
  "open_count" INTEGER NOT NULL DEFAULT 0,
  "submitted_at" TEXT,
  "submission_id" TEXT,
  "revoked_at" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "revenue_events" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "type" TEXT NOT NULL,
  "amount_usd" TEXT NOT NULL DEFAULT 0,
  "source" TEXT NOT NULL DEFAULT 'stripe',
  "client_name" TEXT,
  "client_email" TEXT,
  "stripe_event_id" TEXT,
  "metadata" TEXT DEFAULT '{}',
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "scrub_candidates" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "status" TEXT NOT NULL DEFAULT 'pending_review',
  "tier" TEXT NOT NULL,
  "score" INTEGER NOT NULL DEFAULT 0,
  "reasons" TEXT NOT NULL DEFAULT '[]',
  "decline_reason" TEXT,
  "previously_submitted" INTEGER NOT NULL DEFAULT 0,
  "leverage_pct" TEXT,
  "monthly_revenue" TEXT,
  "lead_data" TEXT NOT NULL,
  "source_file" TEXT,
  "source_file_id" TEXT,
  "row_hash" TEXT NOT NULL,
  "scoring_config_version" TEXT,
  "scrubbed_at" TEXT,
  "reviewed_by" TEXT,
  "reviewed_at" TEXT,
  "review_note" TEXT,
  "created_lead_id" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "self_healing_log" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tier" INTEGER NOT NULL,
  "dimension" TEXT NOT NULL,
  "trigger_event" TEXT NOT NULL,
  "diagnosis" TEXT,
  "action_taken" TEXT,
  "outcome" TEXT NOT NULL,
  "duration_seconds" INTEGER,
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "self_healing_log_dimension_check" CHECK ((dimension IN ('memory', 'context', 'skill', 'infrastructure', 'relationship'))),
  CONSTRAINT "self_healing_log_outcome_check" CHECK ((outcome IN ('resolved', 'escalated', 'failed', 'deferred'))),
  CONSTRAINT "self_healing_log_tier_check" CHECK (((tier >= 1) AND (tier <= 4)))
);

CREATE TABLE IF NOT EXISTS "self_modification_log" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "file_path" TEXT NOT NULL,
  "section_modified" TEXT,
  "change_type" TEXT NOT NULL,
  "old_content_summary" TEXT,
  "new_content_summary" TEXT,
  "reason" TEXT NOT NULL,
  "evidence" TEXT,
  "confidence" TEXT DEFAULT 0.80,
  "governance_tier" TEXT NOT NULL,
  "approval_status" TEXT NOT NULL DEFAULT 'auto_approved',
  "rollback_commit" TEXT,
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "self_modification_log_approval_status_check" CHECK ((approval_status IN ('auto_approved', 'pending_approval', 'approved', 'rejected', 'rolled_back'))),
  CONSTRAINT "self_modification_log_change_type_check" CHECK ((change_type IN ('create', 'update', 'delete', 'propose'))),
  CONSTRAINT "self_modification_log_confidence_check" CHECK (((confidence >= (0)) AND (confidence <= (1)))),
  CONSTRAINT "self_modification_log_governance_tier_check" CHECK ((governance_tier IN ('immutable', 'semi_mutable', 'governed_mutable', 'freely_mutable', 'ephemeral')))
);

CREATE TABLE IF NOT EXISTS "session_logs" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "session_date" TEXT NOT NULL,
  "agent_interface" TEXT NOT NULL,
  "summary" TEXT NOT NULL,
  "tasks_completed" TEXT DEFAULT '[]',
  "tasks_failed" TEXT DEFAULT '[]',
  "tasks_blocked" TEXT DEFAULT '[]',
  "insights" TEXT DEFAULT '[]',
  "duration_minutes" INTEGER,
  "tool_calls_count" INTEGER DEFAULT 0,
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "session_logs_agent_interface_check" CHECK ((agent_interface IN ('claude_code', 'anti_gravity', 'blackbox', 'telegram', 'n8n')))
);

CREATE TABLE IF NOT EXISTS "shadow_decisions" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "agent_source" TEXT NOT NULL,
  "channel" TEXT NOT NULL,
  "lead_id" TEXT,
  "to_identity" TEXT,
  "subject" TEXT,
  "body_preview" TEXT,
  "would_have_status" TEXT NOT NULL,
  "block_reason" TEXT,
  "comparison_run_id" TEXT,
  "brand" TEXT,
  "intent" TEXT,
  "metadata" TEXT DEFAULT '{}',
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "shop_out_warnings" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "application_id" TEXT NOT NULL,
  "lender_id" TEXT NOT NULL,
  "severity" TEXT NOT NULL,
  "reason_code" TEXT NOT NULL,
  "reason_detail" TEXT NOT NULL,
  "detected_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "overridden" INTEGER NOT NULL DEFAULT 0,
  "override_note" TEXT,
  "overridden_by_user_id" TEXT,
  "overridden_at" TEXT,
  "thread_id" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "skill_activation" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "item_type" TEXT NOT NULL,
  "item_id" TEXT NOT NULL,
  "item_name" TEXT NOT NULL,
  "access_count" INTEGER DEFAULT 1,
  "last_accessed" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "first_accessed" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "activation_score" TEXT DEFAULT 0.5000,
  "status" TEXT DEFAULT 'active',
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "skill_activation_item_type_check" CHECK ((item_type IN ('memory', 'pattern', 'mistake', 'sop', 'skill', 'fact'))),
  CONSTRAINT "skill_activation_status_check" CHECK ((status IN ('active', 'probationary', 'validated', 'under_review', 'archived')))
);

CREATE TABLE IF NOT EXISTS "skills_registry" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "skill_name" TEXT NOT NULL,
  "skill_path" TEXT NOT NULL,
  "description" TEXT,
  "category" TEXT,
  "usage_count" INTEGER DEFAULT 0,
  "success_count" INTEGER DEFAULT 0,
  "last_used" TEXT,
  "dependencies" TEXT DEFAULT '[]',
  "is_active" INTEGER DEFAULT 1,
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "triggers" TEXT DEFAULT '[]',
  "tags" TEXT DEFAULT '[]',
  "tier" TEXT DEFAULT 'standard',
  "owner_agent" TEXT DEFAULT 'bravo',
  "when_to_use" TEXT DEFAULT '[]',
  "inputs" TEXT DEFAULT '{}',
  "outputs" TEXT DEFAULT '{}',
  "preconditions" TEXT DEFAULT '[]',
  "side_effects" TEXT DEFAULT '[]',
  "cli_entry" TEXT,
  "risk_level" TEXT DEFAULT 'normal',
  "requires_approval" INTEGER DEFAULT 0,
  "source_hash" TEXT,
  "frontmatter" TEXT DEFAULT '{}',
  "spec" TEXT DEFAULT '{}',
  "orchestration_notes" TEXT,
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "sops" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "sop_id" TEXT NOT NULL,
  "name" TEXT NOT NULL,
  "description" TEXT,
  "category" TEXT NOT NULL,
  "trigger_conditions" TEXT NOT NULL,
  "prerequisites" TEXT,
  "steps" TEXT NOT NULL DEFAULT '[]',
  "success_criteria" TEXT,
  "failure_handling" TEXT,
  "owner" TEXT DEFAULT 'bravo',
  "execution_count" INTEGER DEFAULT 0,
  "success_count" INTEGER DEFAULT 0,
  "last_executed" TEXT,
  "is_active" INTEGER DEFAULT 1,
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "sops_category_check" CHECK ((category IN ('content', 'code', 'deploy', 'research', 'automation', 'admin', 'client', 'finance')))
);

CREATE TABLE IF NOT EXISTS "template_performance" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "template_identity" TEXT NOT NULL,
  "vertical" TEXT,
  "relationship_stage" TEXT,
  "brand" TEXT,
  "sends_total" INTEGER DEFAULT 0,
  "replies_total" INTEGER DEFAULT 0,
  "positive_replies" INTEGER DEFAULT 0,
  "negative_replies" INTEGER DEFAULT 0,
  "meetings_booked" INTEGER DEFAULT 0,
  "deals_closed" INTEGER DEFAULT 0,
  "revenue_attributed_cents" INTEGER DEFAULT 0,
  "first_seen" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "last_seen" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "last_computed_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "score_30d" TEXT,
  "score_overall" TEXT,
  "metadata" TEXT DEFAULT '{}',
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "tenants" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "slug" TEXT NOT NULL,
  "name" TEXT NOT NULL,
  "plan_tier" TEXT NOT NULL DEFAULT 'starter',
  "purchase_status" TEXT NOT NULL DEFAULT 'pending',
  "stripe_customer_id" TEXT,
  "stripe_subscription_id" TEXT,
  "primary_brand_color" TEXT DEFAULT '#e8c547',
  "custom_fields" TEXT NOT NULL DEFAULT '{}',
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "logo_url" TEXT,
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "underwriting_ungrounded_backup_20260806" (
  "id" TEXT,
  "tenant_id" TEXT,
  "application_id" TEXT,
  "run_at" TEXT,
  "triggered_by" TEXT,
  "triggered_by_user_id" TEXT,
  "status" TEXT,
  "parser_output" TEXT,
  "debt_analysis" TEXT,
  "sales_angle" TEXT,
  "avg_monthly_revenue" TEXT,
  "avg_daily_balance" TEXT,
  "nsf_count" INTEGER,
  "deposit_consistency_pct" TEXT,
  "debt_service_monthly" TEXT,
  "debt_to_revenue_ratio" TEXT,
  "lender_count" INTEGER,
  "risk_flags" TEXT,
  "readiness_score" INTEGER,
  "error_message" TEXT,
  "created_at" TEXT
);

CREATE TABLE IF NOT EXISTS "user_context" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "key" TEXT NOT NULL,
  "value" TEXT NOT NULL,
  "category" TEXT NOT NULL,
  "confidence_score" TEXT DEFAULT 0.90,
  "updated_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "user_context_category_check" CHECK ((category IN ('identity', 'business', 'preference', 'weakness', 'strength', 'goal', 'content_pillar')))
);

CREATE TABLE IF NOT EXISTS "vertical_response_patterns" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "vertical" TEXT NOT NULL,
  "signal_type" TEXT NOT NULL,
  "signal_value" TEXT NOT NULL,
  "success_count" INTEGER DEFAULT 0,
  "failure_count" INTEGER DEFAULT 0,
  "sample_size" INTEGER DEFAULT 0,
  "confidence" TEXT,
  "last_updated" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "metadata" TEXT DEFAULT '{}',
  PRIMARY KEY ("id")
);

CREATE TABLE IF NOT EXISTS "agent_alerts" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "alert_type" TEXT NOT NULL,
  "severity" TEXT NOT NULL DEFAULT 'info',
  "subject_type" TEXT,
  "subject_id" TEXT,
  "title" TEXT NOT NULL,
  "body" TEXT,
  "payload" TEXT NOT NULL DEFAULT '{}',
  "dedup_key" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "resolved_at" TEXT,
  "resolved_by" TEXT,
  PRIMARY KEY ("id"),
  CONSTRAINT "agent_alerts_severity_check" CHECK ((severity IN ('info', 'warn', 'urgent'))),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "agent_decisions" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tick_id" TEXT NOT NULL,
  "agent_name" TEXT NOT NULL DEFAULT 'bravo',
  "phase" TEXT NOT NULL,
  "decision_type" TEXT NOT NULL,
  "target_lead_id" TEXT,
  "target_description" TEXT,
  "reasoning" TEXT,
  "confidence" TEXT,
  "chosen_action" TEXT,
  "alternatives_considered" TEXT,
  "executed" INTEGER DEFAULT 0,
  "execution_result" TEXT,
  "outcome_status" TEXT,
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "tenant_id" TEXT NOT NULL,
  PRIMARY KEY ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "agent_messages" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "message_id" TEXT NOT NULL,
  "tenant_id" TEXT NOT NULL,
  "from_agent" TEXT NOT NULL,
  "to_agent" TEXT NOT NULL,
  "subject" TEXT,
  "body" TEXT NOT NULL,
  "priority" TEXT NOT NULL DEFAULT 'normal',
  "requires_response" INTEGER NOT NULL DEFAULT 0,
  "in_reply_to" TEXT,
  "thread_id" TEXT,
  "read_at" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "agent_messages_priority_check" CHECK ((priority IN ('low', 'normal', 'high', 'urgent'))),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "agent_model_config" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "agent_key" TEXT NOT NULL,
  "provider" TEXT NOT NULL,
  "model" TEXT NOT NULL,
  "encrypted_api_key" TEXT,
  "system_prompt_override" TEXT,
  "enabled" INTEGER NOT NULL DEFAULT 1,
  "last_used_at" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "user_id" TEXT,
  "display_name_override" TEXT,
  PRIMARY KEY ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "agents" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "slug" TEXT NOT NULL,
  "name" TEXT NOT NULL,
  "category" TEXT NOT NULL,
  "short_description" TEXT NOT NULL,
  "description" TEXT,
  "base_prompt" TEXT NOT NULL,
  "required_tools" TEXT NOT NULL DEFAULT '[]',
  "suggested_model" TEXT,
  "pricing" TEXT NOT NULL DEFAULT '{"tier": "free"}',
  "is_public" INTEGER NOT NULL DEFAULT 1,
  "is_oasis_managed" INTEGER NOT NULL DEFAULT 0,
  "created_by" TEXT,
  "tenant_id" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "agents_category_check" CHECK ((category IN ('ceo', 'cfo', 'cmo', 'coo', 'operations', 'sales', 'support', 'research', 'content', 'engineering', 'finance', 'legal', 'industry_real_estate', 'industry_funding', 'industry_ecommerce', 'industry_agency', 'custom'))),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "application_lender_threads" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "application_id" TEXT NOT NULL,
  "lender_id" TEXT NOT NULL,
  "tenant_id" TEXT NOT NULL,
  "gmail_thread_id" TEXT,
  "subject" TEXT,
  "status" TEXT NOT NULL DEFAULT 'pending',
  "cc_emails" TEXT NOT NULL DEFAULT '[]',
  "last_response_at" TEXT,
  "last_response_summary" TEXT,
  "last_error" TEXT,
  "sent_at" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "body_template" TEXT,
  "attachments" TEXT NOT NULL DEFAULT '[]',
  "send_interaction_id" TEXT,
  "owner_phone" TEXT,
  "warnings_acknowledged" TEXT DEFAULT '[]',
  "last_message_id" TEXT,
  "message_id_history" TEXT NOT NULL DEFAULT '[]',
  "signer_name" TEXT,
  "signer_email" TEXT,
  "signer_phone" TEXT,
  "email_identity" TEXT NOT NULL DEFAULT 'sunbiz',
  PRIMARY KEY ("id"),
  CONSTRAINT "application_lender_threads_email_identity_check" CHECK ((email_identity IN ('sunbiz', 'funmate'))),
  CONSTRAINT "application_lender_threads_status_check" CHECK ((status IN ('pending', 'sending', 'sent', 'replied', 'offer_received', 'declined', 'error'))),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "application_signing_events" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "request_id" TEXT NOT NULL,
  "tenant_id" TEXT NOT NULL,
  "event" TEXT NOT NULL,
  "at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "ip" TEXT,
  "user_agent" TEXT,
  "meta" TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY ("id"),
  FOREIGN KEY ("request_id") REFERENCES "application_signing_requests" ("id")
);

CREATE TABLE IF NOT EXISTS "bridge_pairings" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "user_id" TEXT,
  "label" TEXT NOT NULL,
  "pairing_code" TEXT,
  "pairing_code_expires_at" TEXT,
  "bridge_token_hash" TEXT,
  "machine_fingerprint" TEXT,
  "last_seen_at" TEXT,
  "last_seen_ip" TEXT,
  "revoked_at" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "tool_capabilities" TEXT NOT NULL DEFAULT '[]',
  PRIMARY KEY ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "campaign_metric_snapshots" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "tt_campaign_id" TEXT NOT NULL,
  "snapshot_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "total" INTEGER,
  "delivered" INTEGER,
  "failed" INTEGER,
  "reply_count" INTEGER,
  "reply_rate" TEXT,
  "conversion_count" INTEGER,
  "conversion_rate" TEXT,
  "credits_consumed" INTEGER,
  "status" TEXT,
  "opens" INTEGER,
  "unique_opens" INTEGER,
  "open_rate" TEXT,
  "clicks" INTEGER,
  "click_rate" TEXT,
  "bounces" INTEGER,
  "bounce_rate" TEXT,
  "optouts" INTEGER,
  "complaints" INTEGER,
  "unique_clicks" INTEGER,
  "complaint_rate" TEXT,
  PRIMARY KEY ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "campaign_number_health" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "send_from" TEXT NOT NULL,
  "window_key" TEXT NOT NULL DEFAULT 'global',
  "sent" INTEGER,
  "delivered" INTEGER,
  "failed" INTEGER,
  "replies" INTEGER,
  "failure_rate" TEXT,
  "reply_rate" TEXT,
  "health" TEXT,
  "last_alerted_at" TEXT,
  "last_alert_signature" TEXT,
  "last_computed_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "repeat_n" INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "campaign_recipients" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "tt_campaign_id" TEXT NOT NULL,
  "send_to" TEXT,
  "send_to_last10" TEXT,
  "send_from" TEXT,
  "send_status" TEXT,
  "received" INTEGER NOT NULL DEFAULT 0,
  "received_message" TEXT,
  "lead_id" TEXT,
  "conversion_stage" TEXT,
  "last_status_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "campaign_runs" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "tt_campaign_id" TEXT NOT NULL,
  "campaign_name" TEXT,
  "list_id" TEXT,
  "list_name" TEXT,
  "sender_numbers" TEXT,
  "message" TEXT,
  "launched_by" TEXT,
  "dry_run" INTEGER NOT NULL DEFAULT 0,
  "launched_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "channel" TEXT DEFAULT 'texttorrent',
  "provider_activity_id" TEXT,
  PRIMARY KEY ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "cc_email_templates" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "name" TEXT NOT NULL,
  "category" TEXT NOT NULL DEFAULT 'custom',
  "subject" TEXT NOT NULL DEFAULT '',
  "preheader" TEXT NOT NULL DEFAULT '',
  "html" TEXT NOT NULL DEFAULT '',
  "created_by" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "channel_accounts" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "provider" TEXT NOT NULL,
  "owner_user_id" TEXT,
  "display_name" TEXT,
  "from_email" TEXT,
  "from_phone" TEXT,
  "texttorrent_act_as_email" TEXT,
  "twilio_messaging_service_sid" TEXT,
  "twilio_phone_sid" TEXT,
  "capabilities" TEXT NOT NULL DEFAULT '{}',
  "credential_ref" TEXT,
  "is_active" INTEGER NOT NULL DEFAULT 1,
  "is_dry_run" INTEGER NOT NULL DEFAULT 0,
  "metadata" TEXT NOT NULL DEFAULT '{}',
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "chat_sessions" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "user_id" TEXT,
  "agent_key" TEXT NOT NULL,
  "title" TEXT,
  "provider" TEXT NOT NULL,
  "model" TEXT NOT NULL,
  "total_input_tokens" INTEGER NOT NULL DEFAULT 0,
  "total_output_tokens" INTEGER NOT NULL DEFAULT 0,
  "estimated_cost_usd" TEXT NOT NULL DEFAULT 0,
  "archived" INTEGER NOT NULL DEFAULT 0,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "cold_leads" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "list_id" TEXT NOT NULL,
  "business_name" TEXT,
  "contact_name" TEXT,
  "phone" TEXT,
  "email" TEXT,
  "raw" TEXT DEFAULT '{}',
  "stage" TEXT NOT NULL DEFAULT 'imported',
  "promoted_lead_id" TEXT,
  "last_contacted_at" TEXT,
  "attempt_count" INTEGER NOT NULL DEFAULT 0,
  "notes" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("list_id") REFERENCES "cold_lead_lists" ("id")
);

CREATE TABLE IF NOT EXISTS "cold_outreach_campaigns" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "name" TEXT NOT NULL,
  "channel" TEXT NOT NULL,
  "message_body" TEXT NOT NULL,
  "subject" TEXT,
  "cold_list_id" TEXT,
  "recipient_filter" TEXT DEFAULT '{}',
  "status" TEXT NOT NULL DEFAULT 'draft',
  "scheduled_for" TEXT,
  "started_at" TEXT,
  "completed_at" TEXT,
  "total_recipients" INTEGER NOT NULL DEFAULT 0,
  "sent_count" INTEGER NOT NULL DEFAULT 0,
  "failed_count" INTEGER NOT NULL DEFAULT 0,
  "daily_cap" INTEGER NOT NULL DEFAULT 500,
  "created_by_user_id" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "sender_user_id" TEXT,
  "sender_from_number" TEXT,
  "sender_act_as_email" TEXT,
  "sender_daily_limit" INTEGER,
  "last_error" TEXT,
  PRIMARY KEY ("id"),
  FOREIGN KEY ("cold_list_id") REFERENCES "cold_lead_lists" ("id")
);

CREATE TABLE IF NOT EXISTS "conversation_threads" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "thread_key" TEXT NOT NULL,
  "lead_id" TEXT,
  "contact_phone_e164" TEXT,
  "contact_email" TEXT,
  "contact_label" TEXT,
  "owner_agent_id" TEXT,
  "assigned_to" TEXT,
  "status" TEXT NOT NULL DEFAULT 'open',
  "priority" TEXT,
  "last_message_at" TEXT,
  "last_inbound_at" TEXT,
  "last_outbound_at" TEXT,
  "last_direction" TEXT,
  "last_preview" TEXT,
  "unread_count" INTEGER NOT NULL DEFAULT 0,
  "channel_summary" TEXT NOT NULL DEFAULT '{}',
  "sources" TEXT NOT NULL DEFAULT '[]',
  "tags" TEXT NOT NULL DEFAULT '[]',
  "snoozed_until" TEXT,
  "last_read_at" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "cron_jobs" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "name" TEXT NOT NULL,
  "description" TEXT,
  "schedule" TEXT NOT NULL,
  "action_type" TEXT NOT NULL,
  "action_config" TEXT NOT NULL DEFAULT '{}',
  "is_active" INTEGER DEFAULT 1,
  "last_run_at" TEXT,
  "next_run_at" TEXT,
  "run_count" INTEGER DEFAULT 0,
  "last_result" TEXT,
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "tenant_id" TEXT NOT NULL,
  "fail_count" INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "deal_paper_snapshot" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "application_id" TEXT NOT NULL,
  "shop_run_id" TEXT NOT NULL,
  "paper_grade" TEXT,
  "position_count" INTEGER,
  "total_mca_balance" TEXT,
  "leverage_ratio" TEXT,
  "monthly_revenue" TEXT,
  "nsf_count" TEXT,
  "avg_daily_balance" TEXT,
  "months_covered" INTEGER,
  "applicant_fico" INTEGER,
  "time_in_business_months" INTEGER,
  "industry" TEXT,
  "merchant_state" TEXT,
  "requested_amount" TEXT,
  "captured_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "drip_sequences" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "name" TEXT NOT NULL,
  "description" TEXT,
  "trigger_event" TEXT NOT NULL DEFAULT 'BRAVO_RECORD_STATUS_CHANGED',
  "trigger_filter" TEXT NOT NULL DEFAULT '{}',
  "steps" TEXT NOT NULL DEFAULT '[]',
  "enabled" INTEGER NOT NULL DEFAULT 1,
  "one_per_lead" INTEGER NOT NULL DEFAULT 1,
  "created_by" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "email_class" TEXT NOT NULL DEFAULT 'commercial',
  PRIMARY KEY ("id"),
  CONSTRAINT "drip_sequences_email_class_check" CHECK ((email_class IN ('transactional', 'commercial'))),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "drip_template_pool" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "brand" TEXT NOT NULL,
  "stage" TEXT NOT NULL,
  "role" TEXT NOT NULL,
  "subject" TEXT NOT NULL,
  "body_text" TEXT NOT NULL,
  "status" TEXT NOT NULL DEFAULT 'draft',
  "weight" INTEGER NOT NULL DEFAULT 1,
  "source" TEXT NOT NULL DEFAULT 'ui',
  "created_by" TEXT,
  "approved_by" TEXT,
  "approved_at" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "drip_template_pool_approval_audited" CHECK (((status <> 'approved') OR ((approved_by IS NOT NULL) AND (approved_at IS NOT NULL)))),
  CONSTRAINT "drip_template_pool_brand_check" CHECK ((brand IN ('sunbiz', 'bluerise'))),
  CONSTRAINT "drip_template_pool_role_check" CHECK ((role IN ('opener', 'nudge', 'value', 'question', 'last_call', 'revive'))),
  CONSTRAINT "drip_template_pool_source_check" CHECK ((source IN ('ui', 'seed', 'imported', 'generated'))),
  CONSTRAINT "drip_template_pool_status_check" CHECK ((status IN ('draft', 'approved', 'retired'))),
  CONSTRAINT "drip_template_pool_weight_check" CHECK (((weight >= 0) AND (weight <= 100))),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "email_click_events" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "outbound_message_id" TEXT NOT NULL,
  "lead_id" TEXT,
  "clicked_url" TEXT,
  "user_agent" TEXT,
  "ip_hash" TEXT,
  "clicked_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "email_open_events" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "outbound_message_id" TEXT NOT NULL,
  "lead_id" TEXT,
  "opened_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "user_agent" TEXT,
  "ip_hash" TEXT,
  "suspicious_prefetch" INTEGER NOT NULL DEFAULT 0,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "email_suppressions" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "email" TEXT NOT NULL,
  "tenant_id" TEXT NOT NULL,
  "brand" TEXT,
  "reason" TEXT NOT NULL DEFAULT 'unsubscribe',
  "source" TEXT NOT NULL DEFAULT 'web_form',
  "user_agent" TEXT,
  "ip_address" TEXT,
  "added_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "esign_events" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "envelope_id" TEXT NOT NULL,
  "signer_id" TEXT,
  "tenant_id" TEXT NOT NULL,
  "event" TEXT NOT NULL,
  "actor" TEXT,
  "at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "ip" TEXT,
  "user_agent" TEXT,
  "meta" TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY ("id"),
  FOREIGN KEY ("envelope_id") REFERENCES "esign_envelopes" ("id")
);

CREATE TABLE IF NOT EXISTS "esign_signers" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "envelope_id" TEXT NOT NULL,
  "tenant_id" TEXT NOT NULL,
  "email" TEXT NOT NULL,
  "name" TEXT,
  "sign_order" INTEGER NOT NULL DEFAULT 1,
  "status" TEXT NOT NULL DEFAULT 'pending',
  "token_sha256" TEXT NOT NULL,
  "expires_at" TEXT,
  "viewed_at" TEXT,
  "signed_at" TEXT,
  "signed_ip" TEXT,
  "signed_user_agent" TEXT,
  "consented" INTEGER NOT NULL DEFAULT 0,
  "decline_reason" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("envelope_id") REFERENCES "esign_envelopes" ("id")
);

CREATE TABLE IF NOT EXISTS "followup_drip_enrollments" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "lead_id" TEXT NOT NULL,
  "stage" TEXT NOT NULL,
  "cadence_key" TEXT NOT NULL,
  "sender_user_id" TEXT,
  "step_index" INTEGER NOT NULL DEFAULT 0,
  "scheduled_for" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "status" TEXT NOT NULL DEFAULT 'active',
  "last_sent_step" INTEGER,
  "last_sent_at" TEXT,
  "last_error" TEXT,
  "to_phone" TEXT,
  "to_email" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "followup_drip_enrollments_status_check" CHECK ((status IN ('active', 'done', 'stopped', 'error'))),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "forms" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "slug" TEXT NOT NULL,
  "name" TEXT NOT NULL,
  "description" TEXT,
  "branding" TEXT NOT NULL DEFAULT '{}',
  "steps" TEXT NOT NULL DEFAULT '[]',
  "on_complete_stage" TEXT,
  "step_outcomes" TEXT NOT NULL DEFAULT '{}',
  "enabled" INTEGER NOT NULL DEFAULT 1,
  "redirect_url" TEXT,
  "created_by" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "gmail_templates" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "name" TEXT NOT NULL,
  "stage" TEXT NOT NULL DEFAULT 'general',
  "subject" TEXT NOT NULL DEFAULT '',
  "body" TEXT NOT NULL DEFAULT '',
  "variants" TEXT NOT NULL DEFAULT '[]',
  "created_by" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "inference_jobs" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT,
  "source" TEXT NOT NULL,
  "system" TEXT,
  "prompt" TEXT NOT NULL,
  "model_tier" TEXT NOT NULL DEFAULT 'fast',
  "max_tokens" INTEGER NOT NULL DEFAULT 1024,
  "status" TEXT NOT NULL DEFAULT 'pending',
  "result_text" TEXT,
  "error_message" TEXT,
  "attempts" INTEGER NOT NULL DEFAULT 0,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "claimed_at" TEXT,
  "completed_at" TEXT,
  "metadata" TEXT NOT NULL DEFAULT '{}',
  "next_attempt_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "inference_jobs_max_tokens_check" CHECK (((max_tokens >= 1) AND (max_tokens <= 16000))),
  CONSTRAINT "inference_jobs_model_tier_check" CHECK ((model_tier IN ('fast', 'smart', 'max'))),
  CONSTRAINT "inference_jobs_status_check" CHECK ((status IN ('pending', 'running', 'complete', 'error'))),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "lead_documents" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "lead_id" TEXT NOT NULL,
  "filename" TEXT NOT NULL,
  "storage_path" TEXT NOT NULL,
  "mime_type" TEXT,
  "size_bytes" INTEGER,
  "doc_type" TEXT NOT NULL DEFAULT 'unclassified',
  "uploaded_by" TEXT,
  "uploaded_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "metadata" TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "lead_interactions" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "lead_id" TEXT,
  "type" TEXT NOT NULL,
  "channel" TEXT NOT NULL DEFAULT 'email',
  "subject" TEXT,
  "content" TEXT,
  "metadata" TEXT DEFAULT '{}',
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "cooldown_until" TEXT,
  "agent_source" TEXT,
  "tenant_id" TEXT,
  "direction" TEXT,
  "content_preview" TEXT,
  "to_email" TEXT,
  "to_phone" TEXT,
  "sent_at" TEXT,
  "actor_user_id" TEXT,
  "recording_url" TEXT,
  "transcript_url" TEXT,
  "disposition" TEXT,
  "call_outcome" TEXT,
  "call_duration_sec" INTEGER,
  "kixie_call_id" TEXT,
  "from_phone" TEXT,
  "provider" TEXT,
  "provider_message_id" TEXT,
  "from_email" TEXT,
  PRIMARY KEY ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "leads" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "name" TEXT NOT NULL,
  "email" TEXT,
  "phone" TEXT,
  "company" TEXT,
  "website" TEXT,
  "source" TEXT NOT NULL DEFAULT 'manual',
  "status" TEXT NOT NULL DEFAULT 'new',
  "score" INTEGER NOT NULL DEFAULT 0,
  "tags" TEXT DEFAULT '[]',
  "notes" TEXT,
  "last_contacted_at" TEXT,
  "next_followup_at" TEXT,
  "assigned_to" TEXT DEFAULT 'bravo',
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "tenant_id" TEXT,
  PRIMARY KEY ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "lender_reply_outcomes" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "application_id" TEXT NOT NULL,
  "lender_id" TEXT NOT NULL,
  "shop_run_id" TEXT,
  "outcome" TEXT NOT NULL,
  "decline_reason_code" TEXT,
  "decline_reason_detail" TEXT,
  "offer_amount" TEXT,
  "offer_term_months" INTEGER,
  "offer_factor" TEXT,
  "conditions" TEXT NOT NULL DEFAULT '[]',
  "confidence" TEXT,
  "reply_at" TEXT NOT NULL,
  "classified_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "list_intelligence" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "list_id" TEXT NOT NULL,
  "list_name" TEXT,
  "campaigns_count" INTEGER,
  "total_sent" INTEGER,
  "total_replies" INTEGER,
  "total_conversions" INTEGER,
  "reply_rate" TEXT,
  "conversion_rate" TEXT,
  "score" TEXT,
  "verdict" TEXT,
  "last_campaign_at" TEXT,
  "last_alerted_at" TEXT,
  "last_computed_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "marketing_asset" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "title" TEXT NOT NULL,
  "channel" TEXT NOT NULL,
  "track" TEXT GENERATED ALWAYS AS (CASE channel WHEN 'organic-instagram' THEN 'organic' WHEN 'organic-facebook' THEN 'organic' WHEN 'organic-tiktok' THEN 'organic' WHEN 'organic-youtube' THEN 'organic' WHEN 'paid-meta' THEN 'paid' WHEN 'paid-google' THEN 'paid' WHEN 'seo-article' THEN 'seo' WHEN 'seo-landing' THEN 'seo' WHEN 'email' THEN 'email' ELSE NULL END) STORED,
  "format" TEXT NOT NULL,
  "aspect" TEXT,
  "status" TEXT NOT NULL DEFAULT 'draft',
  "hook" TEXT,
  "body" TEXT,
  "cta" TEXT,
  "landing_url" TEXT,
  "campaign" TEXT,
  "duration_s" TEXT,
  "author_agent" TEXT NOT NULL DEFAULT 'human',
  "source" TEXT,
  "scheduled_for" TEXT,
  "published_at" TEXT,
  "external_id" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "meta" TEXT NOT NULL DEFAULT '{}',
  "brand_slug" TEXT NOT NULL DEFAULT 'oasis-ai',
  "brand_name" TEXT NOT NULL DEFAULT 'OASIS AI',
  PRIMARY KEY ("id"),
  CONSTRAINT "marketing_asset_channel_check" CHECK ((channel IN ('organic-instagram', 'organic-facebook', 'organic-tiktok', 'organic-youtube', 'paid-meta', 'paid-google', 'seo-article', 'seo-landing', 'email'))),
  CONSTRAINT "marketing_asset_format_check" CHECK ((format IN ('video', 'image', 'carousel', 'html', 'article', 'copy', 'audio'))),
  CONSTRAINT "marketing_asset_status_check" CHECK ((status IN ('draft', 'in_review', 'approved', 'scheduled', 'published', 'rejected', 'archived'))),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "merchant_background_checks" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "lead_id" TEXT,
  "application_id" TEXT,
  "business_name" TEXT,
  "dba" TEXT,
  "state" TEXT,
  "owner_name" TEXT,
  "partner_name" TEXT,
  "owner_email" TEXT,
  "owner_phone" TEXT,
  "owner_home_address" TEXT,
  "business_address" TEXT,
  "owner_dob" TEXT,
  "ein_last4" TEXT,
  "ssn_last4" TEXT,
  "status" TEXT NOT NULL DEFAULT 'pending',
  "risk_flag" TEXT NOT NULL DEFAULT 'none',
  "findings" TEXT,
  "findings_summary" TEXT,
  "sources_run" TEXT,
  "raw_results" TEXT,
  "error" TEXT,
  "checked_at" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "merchant_background_checks_risk_flag_check" CHECK ((risk_flag IN ('none', 'court_case', 'mca_default', 'ucc', 'lien', 'bankruptcy', 'unknown'))),
  CONSTRAINT "merchant_background_checks_status_check" CHECK ((status IN ('pending', 'running', 'completed', 'error', 'needs_assist'))),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "mrr_snapshots" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "snapshot_date" TEXT NOT NULL,
  "mrr_usd" TEXT NOT NULL DEFAULT 0,
  "target_usd" TEXT,
  "source" TEXT NOT NULL DEFAULT 'profile',
  "metadata" TEXT NOT NULL DEFAULT '{}',
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "ops_alert_state" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "alert_key" TEXT NOT NULL,
  "condition_signature" TEXT NOT NULL,
  "last_alerted_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "repeat_n" INTEGER NOT NULL DEFAULT 1,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "scheduled_calls" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "lead_id" TEXT,
  "thread_key" TEXT,
  "to_phone" TEXT,
  "contact_label" TEXT,
  "actor_user_id" TEXT NOT NULL,
  "scheduled_for" TEXT NOT NULL,
  "notes" TEXT,
  "status" TEXT NOT NULL DEFAULT 'pending',
  "reminded_at" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "scheduled_calls_status_check" CHECK ((status IN ('pending', 'done', 'cancelled', 'missed'))),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "scheduled_sends" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "lead_id" TEXT,
  "thread_key" TEXT NOT NULL,
  "channel" TEXT NOT NULL,
  "to_phone" TEXT,
  "to_email" TEXT,
  "subject" TEXT,
  "body" TEXT NOT NULL,
  "actor_user_id" TEXT NOT NULL,
  "from_identity" TEXT,
  "scheduled_for" TEXT NOT NULL,
  "status" TEXT NOT NULL DEFAULT 'pending',
  "attempts" INTEGER NOT NULL DEFAULT 0,
  "last_error" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "sent_at" TEXT,
  PRIMARY KEY ("id"),
  CONSTRAINT "scheduled_sends_channel_check" CHECK ((channel IN ('sms', 'email'))),
  CONSTRAINT "scheduled_sends_status_check" CHECK ((status IN ('pending', 'sending', 'sent', 'failed', 'cancelled'))),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "shop_out_runs" (
  "run_id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "application_id" TEXT NOT NULL,
  "merchant_name" TEXT NOT NULL,
  "initiated_by" TEXT NOT NULL,
  "signer_label" TEXT NOT NULL,
  "agent_ccs" TEXT NOT NULL DEFAULT '[]',
  "funders_targeted" TEXT NOT NULL,
  "results" TEXT NOT NULL DEFAULT '[]',
  "status" TEXT NOT NULL DEFAULT 'in_progress',
  "initiated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "completed_at" TEXT,
  PRIMARY KEY ("run_id"),
  CONSTRAINT "shop_out_runs_status_check" CHECK ((status IN ('in_progress', 'completed', 'failed'))),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "shopping_threads" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "lead_id" TEXT NOT NULL,
  "round_number" INTEGER NOT NULL,
  "root_message_id" TEXT NOT NULL,
  "agent_user_id" TEXT,
  "lenders" TEXT NOT NULL DEFAULT '[]',
  "status" TEXT NOT NULL DEFAULT 'pending',
  "subject" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "shopping_threads_status_check" CHECK ((status IN ('pending', 'sending', 'sent', 'error'))),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "signing_otp_codes" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "request_id" TEXT NOT NULL,
  "code_sha256" TEXT NOT NULL,
  "channel" TEXT NOT NULL,
  "destination" TEXT NOT NULL,
  "attempts" INTEGER NOT NULL DEFAULT 0,
  "expires_at" TEXT NOT NULL,
  "consumed_at" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("request_id") REFERENCES "application_signing_requests" ("id")
);

CREATE TABLE IF NOT EXISTS "sunbiz_agent_accounts" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "user_id" TEXT NOT NULL,
  "provider" TEXT NOT NULL DEFAULT 'texttorrent',
  "display_name" TEXT NOT NULL,
  "act_as_email" TEXT NOT NULL,
  "from_number" TEXT NOT NULL,
  "application_url" TEXT NOT NULL,
  "handoff_user_id" TEXT,
  "timezone" TEXT NOT NULL DEFAULT 'America/New_York',
  "mode" TEXT NOT NULL DEFAULT 'semi',
  "daily_cap" INTEGER NOT NULL DEFAULT 250,
  "voice_profile_id" TEXT,
  "knowledge_version" TEXT NOT NULL,
  "enabled" INTEGER NOT NULL DEFAULT 1,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "sunbiz_agent_accounts_daily_cap_check" CHECK (((daily_cap >= 0) AND (daily_cap <= 5000))),
  CONSTRAINT "sunbiz_agent_accounts_mode_check" CHECK ((mode IN ('off', 'shadow', 'semi', 'full', 'paused'))),
  CONSTRAINT "sunbiz_agent_accounts_provider_check" CHECK ((provider = 'texttorrent')),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "sunbiz_phone_suppressions" (
  "tenant_id" TEXT NOT NULL,
  "phone_last10" TEXT NOT NULL,
  "reason" TEXT NOT NULL,
  "source" TEXT NOT NULL,
  "source_work_id" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("tenant_id", "phone_last10"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "sunbiz_processing_leases" (
  "tenant_id" TEXT NOT NULL,
  "partition_key" TEXT NOT NULL,
  "owner_id" TEXT NOT NULL,
  "acquired_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "expires_at" TEXT NOT NULL,
  "heartbeat_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("tenant_id", "partition_key"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "sunbiz_provider_rate_state" (
  "bucket" TEXT NOT NULL,
  "tenant_id" TEXT NOT NULL,
  "provider" TEXT NOT NULL,
  "window_started_at" TEXT NOT NULL,
  "request_count" INTEGER NOT NULL DEFAULT 0,
  "blocked_until" TEXT,
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("bucket"),
  CONSTRAINT "sunbiz_provider_rate_state_provider_check" CHECK ((provider = 'texttorrent')),
  CONSTRAINT "sunbiz_provider_rate_state_request_count_check" CHECK ((request_count >= 0)),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "tenant_audit_log" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "actor_user_id" TEXT,
  "actor_email" TEXT,
  "action_type" TEXT NOT NULL,
  "target_table" TEXT,
  "target_id" TEXT,
  "before" TEXT,
  "after" TEXT,
  "ip_hash" TEXT,
  "user_agent" TEXT,
  "metadata" TEXT NOT NULL DEFAULT '{}',
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "tenant_cron_jobs" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "agent_key" TEXT NOT NULL DEFAULT 'bravo',
  "name" TEXT NOT NULL,
  "description" TEXT,
  "schedule" TEXT NOT NULL,
  "action_type" TEXT NOT NULL,
  "action_payload" TEXT NOT NULL DEFAULT '{}',
  "enabled" INTEGER NOT NULL DEFAULT 1,
  "last_run_at" TEXT,
  "last_run_status" TEXT,
  "last_run_output" TEXT,
  "last_run_error" TEXT,
  "run_count" INTEGER NOT NULL DEFAULT 0,
  "created_by" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "tenant_cron_jobs_last_run_status_check" CHECK (((last_run_status IN ('success', 'error', NULL)) OR (last_run_status IS NULL))),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "tenant_invites" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "email" TEXT,
  "team_role" TEXT NOT NULL DEFAULT 'member',
  "token_hash" TEXT NOT NULL,
  "created_by" TEXT NOT NULL,
  "expires_at" TEXT NOT NULL,
  "redeemed_at" TEXT,
  "redeemed_by" TEXT,
  "revoked_at" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "tenant_invites_team_role_check" CHECK ((team_role IN ('admin', 'loan_officer', 'processor', 'read_only', 'member'))),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "tenant_manifests" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT,
  "slug" TEXT NOT NULL,
  "manifest" TEXT NOT NULL,
  "version" INTEGER NOT NULL DEFAULT 1,
  "schema_version" INTEGER NOT NULL DEFAULT 1,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "tenant_records" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "entity_type" TEXT NOT NULL,
  "data" TEXT NOT NULL DEFAULT '{}',
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "user_integration_credentials" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "user_id" TEXT NOT NULL,
  "service" TEXT NOT NULL,
  "field_key" TEXT NOT NULL,
  "encrypted_value" TEXT NOT NULL,
  "last_tested_at" TEXT,
  "last_test_ok" INTEGER,
  "last_test_error" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "user_profiles" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "auth_user_id" TEXT,
  "email" TEXT NOT NULL,
  "full_name" TEXT NOT NULL,
  "display_name" TEXT,
  "brand" TEXT NOT NULL DEFAULT 'OASIS AI',
  "role" TEXT NOT NULL DEFAULT 'operator',
  "mrr_target_usd" TEXT NOT NULL DEFAULT 5000.00,
  "mrr_current_usd" TEXT NOT NULL DEFAULT 0.00,
  "mrr_target_date" TEXT,
  "agents_enabled" TEXT NOT NULL,
  "primary_agent" TEXT NOT NULL DEFAULT 'bravo',
  "manifesto" TEXT,
  "primary_script_version" TEXT NOT NULL DEFAULT 'cold_call_v1',
  "deal_architecture_version" TEXT NOT NULL DEFAULT 'v1',
  "custom_fields" TEXT NOT NULL DEFAULT '{}',
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "tenant_id" TEXT,
  "preferred_language" TEXT NOT NULL DEFAULT 'en',
  "prospect_focus" TEXT NOT NULL,
  "onboarding_completed_at" TEXT,
  "team_role" TEXT NOT NULL DEFAULT 'member',
  "is_owner" INTEGER NOT NULL DEFAULT 0,
  "invited_by" TEXT,
  "joined_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "personal_phone" TEXT,
  "admin_access" INTEGER NOT NULL DEFAULT 0,
  "admin_access_granted_by" TEXT,
  "admin_access_granted_at" TEXT,
  PRIMARY KEY ("id"),
  CONSTRAINT "user_profiles_team_role_check" CHECK ((team_role IN ('owner', 'admin', 'loan_officer', 'processor', 'read_only', 'member'))),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "bookings" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "lead_id" TEXT,
  "slot_id" TEXT,
  "name" TEXT NOT NULL,
  "email" TEXT NOT NULL,
  "phone" TEXT,
  "meeting_type" TEXT NOT NULL DEFAULT 'discovery',
  "notes" TEXT,
  "status" TEXT NOT NULL DEFAULT 'confirmed',
  "meeting_link" TEXT,
  "reminder_sent" INTEGER DEFAULT 0,
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("lead_id") REFERENCES "leads" ("id"),
  FOREIGN KEY ("slot_id") REFERENCES "booking_slots" ("id")
);

CREATE TABLE IF NOT EXISTS "bridge_pair_codes" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "code" TEXT NOT NULL,
  "tenant_id" TEXT NOT NULL,
  "auth_user_id" TEXT NOT NULL,
  "email" TEXT NOT NULL,
  "expires_at" TEXT NOT NULL,
  "consumed_at" TEXT,
  "consumed_by_pairing_id" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("consumed_by_pairing_id") REFERENCES "bridge_pairings" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "chat_attachments" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "auth_user_id" TEXT NOT NULL,
  "session_id" TEXT,
  "agent_key" TEXT,
  "filename" TEXT NOT NULL,
  "storage_bucket" TEXT NOT NULL DEFAULT 'chat-attachments',
  "storage_path" TEXT NOT NULL,
  "mime_type" TEXT,
  "size_bytes" INTEGER NOT NULL DEFAULT 0,
  "parser" TEXT NOT NULL DEFAULT 'metadata_only',
  "text_excerpt" TEXT,
  "metadata" TEXT NOT NULL DEFAULT '{}',
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("session_id") REFERENCES "chat_sessions" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "chat_messages" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "session_id" TEXT NOT NULL,
  "tenant_id" TEXT NOT NULL,
  "role" TEXT NOT NULL,
  "content" TEXT NOT NULL,
  "input_tokens" INTEGER,
  "output_tokens" INTEGER,
  "latency_ms" INTEGER,
  "error" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("session_id") REFERENCES "chat_sessions" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "clair_reports" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "lead_id" TEXT NOT NULL,
  "application_id" TEXT,
  "query_name" TEXT,
  "query_address" TEXT,
  "query_city" TEXT,
  "query_state" TEXT,
  "query_zip" TEXT,
  "query_dob" TEXT,
  "permissible_dppa" TEXT,
  "permissible_glb" TEXT,
  "permissible_voter" TEXT,
  "clear_environment" TEXT,
  "status" TEXT NOT NULL DEFAULT 'pending',
  "error_message" TEXT,
  "http_status" INTEGER,
  "result_count" INTEGER,
  "people" TEXT,
  "phones" TEXT,
  "raw_report" TEXT,
  "raw_format" TEXT,
  "requested_by" TEXT,
  "requested_by_email" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "completed_at" TEXT,
  "report_type" TEXT NOT NULL DEFAULT 'person_search',
  "entity_id" TEXT,
  PRIMARY KEY ("id"),
  CONSTRAINT "clair_reports_status_check" CHECK ((status IN ('pending', 'completed', 'no_results', 'error'))),
  FOREIGN KEY ("lead_id") REFERENCES "tenant_records" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "cold_outreach_recipients" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "campaign_id" TEXT NOT NULL,
  "cold_lead_id" TEXT,
  "lead_id" TEXT,
  "contact_address" TEXT NOT NULL,
  "status" TEXT NOT NULL DEFAULT 'pending',
  "sent_at" TEXT,
  "delivery_status_at" TEXT,
  "last_error" TEXT,
  "interaction_id" TEXT,
  "response_at" TEXT,
  "response_summary" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("campaign_id") REFERENCES "cold_outreach_campaigns" ("id"),
  FOREIGN KEY ("cold_lead_id") REFERENCES "cold_leads" ("id")
);

CREATE TABLE IF NOT EXISTS "contracts" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "lead_id" TEXT,
  "client_name" TEXT NOT NULL,
  "client_email" TEXT NOT NULL,
  "contract_type" TEXT NOT NULL,
  "terms_body" TEXT NOT NULL,
  "variables" TEXT NOT NULL DEFAULT '{}',
  "status" TEXT NOT NULL DEFAULT 'draft',
  "sign_token" TEXT NOT NULL,
  "expires_at" TEXT,
  "sent_at" TEXT,
  "first_viewed_at" TEXT,
  "signed_at" TEXT,
  "created_by" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "contracts_status_check" CHECK ((status IN ('draft', 'sent', 'viewed', 'signed', 'expired', 'void'))),
  FOREIGN KEY ("lead_id") REFERENCES "leads" ("id")
);

CREATE TABLE IF NOT EXISTS "conversation_events" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "thread_id" TEXT,
  "lead_id" TEXT,
  "event_type" TEXT NOT NULL,
  "actor_user_id" TEXT,
  "metadata" TEXT NOT NULL DEFAULT '{}',
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id"),
  FOREIGN KEY ("thread_id") REFERENCES "conversation_threads" ("id")
);

CREATE TABLE IF NOT EXISTS "daily_plans" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "profile_id" TEXT NOT NULL,
  "plan_date" TEXT NOT NULL,
  "mission" TEXT,
  "primary_lead_id" TEXT,
  "primary_lead_play" TEXT,
  "target_calls" INTEGER NOT NULL DEFAULT 0,
  "target_emails" INTEGER NOT NULL DEFAULT 0,
  "target_bookings" INTEGER NOT NULL DEFAULT 1,
  "schedule" TEXT NOT NULL DEFAULT '[]',
  "actual_calls" INTEGER,
  "actual_bookings" INTEGER,
  "retro_notes" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "tenant_id" TEXT,
  "finalized_at" TEXT,
  PRIMARY KEY ("id"),
  FOREIGN KEY ("primary_lead_id") REFERENCES "leads" ("id"),
  FOREIGN KEY ("profile_id") REFERENCES "user_profiles" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "drip_email_events" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "merchant_id" TEXT NOT NULL,
  "sequence_id" TEXT NOT NULL,
  "drip_run_id" TEXT,
  "step_index" INTEGER NOT NULL,
  "recipient_email" TEXT NOT NULL,
  "subject_line" TEXT NOT NULL,
  "payload_text" TEXT NOT NULL,
  "payload_html" TEXT NOT NULL,
  "provider_message_id" TEXT,
  "sent_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("drip_run_id") REFERENCES "drip_runs" ("id"),
  FOREIGN KEY ("sequence_id") REFERENCES "drip_sequences" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "drip_sequence_versions" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "sequence_id" TEXT NOT NULL,
  "name" TEXT NOT NULL,
  "steps" TEXT NOT NULL,
  "edited_by" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("sequence_id") REFERENCES "drip_sequences" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "email_log" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "lead_id" TEXT,
  "template_id" TEXT,
  "sequence_id" TEXT,
  "to_email" TEXT NOT NULL,
  "subject" TEXT NOT NULL,
  "body_preview" TEXT,
  "status" TEXT NOT NULL DEFAULT 'queued',
  "sent_at" TEXT,
  "opened_at" TEXT,
  "clicked_at" TEXT,
  "error_message" TEXT,
  "created_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("lead_id") REFERENCES "leads" ("id"),
  FOREIGN KEY ("sequence_id") REFERENCES "nurture_sequences" ("id"),
  FOREIGN KEY ("template_id") REFERENCES "email_templates" ("id")
);

CREATE TABLE IF NOT EXISTS "esign_fields" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "envelope_id" TEXT NOT NULL,
  "signer_id" TEXT NOT NULL,
  "tenant_id" TEXT NOT NULL,
  "type" TEXT NOT NULL,
  "page" INTEGER NOT NULL DEFAULT 0,
  "x" TEXT NOT NULL,
  "y" TEXT NOT NULL,
  "w" TEXT NOT NULL DEFAULT 160,
  "h" TEXT NOT NULL DEFAULT 44,
  "required" INTEGER NOT NULL DEFAULT 1,
  "value" TEXT,
  "placeholder" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("envelope_id") REFERENCES "esign_envelopes" ("id"),
  FOREIGN KEY ("signer_id") REFERENCES "esign_signers" ("id")
);

CREATE TABLE IF NOT EXISTS "exec_overrides" (
  "request_id" TEXT NOT NULL,
  "ts" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "expires_at" TEXT NOT NULL,
  "command" TEXT NOT NULL,
  "command_hash" TEXT NOT NULL,
  "layer" TEXT NOT NULL,
  "reason" TEXT,
  "caller_pid" INTEGER,
  "status" TEXT NOT NULL DEFAULT 'pending',
  "approved_at" TEXT,
  "approved_by" TEXT,
  "consumed_at" TEXT,
  "hmac_sig" TEXT,
  "dashboard_decision" TEXT,
  "dashboard_decided_at" TEXT,
  "dashboard_decided_by" TEXT,
  "dashboard_reason" TEXT,
  "consumer_synced_at" TEXT,
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "cwd_path" TEXT,
  "workspace_label" TEXT NOT NULL DEFAULT 'unknown',
  PRIMARY KEY ("request_id"),
  FOREIGN KEY ("dashboard_decided_by") REFERENCES "user_profiles" ("id")
);

CREATE TABLE IF NOT EXISTS "followup_drip_sends" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "enrollment_id" TEXT NOT NULL,
  "tenant_id" TEXT NOT NULL,
  "step_index" INTEGER NOT NULL,
  "channel" TEXT NOT NULL,
  "status" TEXT NOT NULL DEFAULT 'claimed',
  "provider_ref" TEXT,
  "error" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "followup_drip_sends_channel_check" CHECK ((channel IN ('sms', 'email'))),
  CONSTRAINT "followup_drip_sends_status_check" CHECK ((status IN ('claimed', 'sent', 'failed', 'skipped'))),
  FOREIGN KEY ("enrollment_id") REFERENCES "followup_drip_enrollments" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "form_submissions" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "form_id" TEXT NOT NULL,
  "tenant_id" TEXT NOT NULL,
  "lead_id" TEXT NOT NULL,
  "step_index" INTEGER NOT NULL DEFAULT 0,
  "payload" TEXT NOT NULL DEFAULT '{}',
  "file_attachments" TEXT NOT NULL DEFAULT '[]',
  "ip_address" TEXT,
  "user_agent" TEXT,
  "submitted_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("form_id") REFERENCES "forms" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "form_views" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "form_id" TEXT NOT NULL,
  "tenant_id" TEXT NOT NULL,
  "lead_id" TEXT NOT NULL,
  "ip_address" TEXT,
  "user_agent" TEXT,
  "viewed_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("form_id") REFERENCES "forms" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "funded_deals" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "merchant_name" TEXT NOT NULL,
  "contact_name" TEXT,
  "lender_name" TEXT,
  "lead_id" TEXT,
  "application_id" TEXT,
  "funded_amount_usd" TEXT NOT NULL,
  "factor_rate" TEXT,
  "term_months" INTEGER,
  "points_pct" TEXT,
  "funded_at" TEXT NOT NULL,
  "next_renewal_date" TEXT,
  "est_commission_usd" TEXT,
  "notes" TEXT,
  "source" TEXT NOT NULL DEFAULT 'manual_entry',
  "created_by" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "dedupe_key" TEXT,
  "lender_id" TEXT,
  "term_value" INTEGER,
  "term_unit" TEXT,
  PRIMARY KEY ("id"),
  CONSTRAINT "funded_deals_factor_rate_check" CHECK (((factor_rate IS NULL) OR ((factor_rate >= 1.0) AND (factor_rate <= 2.0)))),
  CONSTRAINT "funded_deals_funded_amount_usd_check" CHECK ((funded_amount_usd > (0))),
  CONSTRAINT "funded_deals_points_pct_check" CHECK (((points_pct IS NULL) OR ((points_pct >= (0)) AND (points_pct <= (100))))),
  CONSTRAINT "funded_deals_term_months_check" CHECK (((term_months IS NULL) OR ((term_months >= 1) AND (term_months <= 60)))),
  CONSTRAINT "funded_deals_term_unit_check" CHECK ((((term_value IS NULL) AND (term_unit IS NULL)) OR ((term_unit = 'months') AND ((term_value >= 1) AND (term_value <= 60))) OR ((term_unit = 'weeks') AND ((term_value >= 1) AND (term_value <= 260))) OR ((term_unit = 'days') AND ((term_value >= 1) AND (term_value <= 1825))))),
  FOREIGN KEY ("lender_id") REFERENCES "tenant_records" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "funnel_entries" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "funnel_id" TEXT,
  "lead_id" TEXT,
  "current_stage" TEXT NOT NULL DEFAULT 'awareness',
  "entered_at" TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "converted_at" TEXT,
  "dropped_at" TEXT,
  "metadata" TEXT DEFAULT '{}',
  PRIMARY KEY ("id"),
  FOREIGN KEY ("funnel_id") REFERENCES "funnels" ("id"),
  FOREIGN KEY ("lead_id") REFERENCES "leads" ("id")
);

CREATE TABLE IF NOT EXISTS "integrations_health" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "profile_id" TEXT,
  "service" TEXT NOT NULL,
  "status" TEXT NOT NULL,
  "last_ping_at" TEXT,
  "last_error" TEXT,
  "metadata" TEXT NOT NULL DEFAULT '{}',
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "tenant_id" TEXT,
  PRIMARY KEY ("id"),
  FOREIGN KEY ("profile_id") REFERENCES "user_profiles" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "manifest_audit_log" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "manifest_id" TEXT,
  "tenant_id" TEXT,
  "actor_type" TEXT NOT NULL,
  "actor_id" TEXT,
  "diff" TEXT NOT NULL,
  "message" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "manifest_audit_log_actor_type_check" CHECK ((actor_type IN ('user', 'ai', 'system', 'seed'))),
  FOREIGN KEY ("manifest_id") REFERENCES "tenant_manifests" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "marketing_asset_media" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "asset_id" TEXT NOT NULL,
  "kind" TEXT NOT NULL,
  "storage_bucket" TEXT NOT NULL DEFAULT 'marketing-media',
  "storage_path" TEXT NOT NULL,
  "mime" TEXT,
  "bytes" INTEGER,
  "width" INTEGER,
  "height" INTEGER,
  "label" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "marketing_asset_media_kind_check" CHECK ((kind IN ('video', 'poster', 'preview', 'thumb', 'audio', 'html', 'source', 'caption'))),
  FOREIGN KEY ("tenant_id", "asset_id") REFERENCES "marketing_asset" ("tenant_id", "id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "marketing_corpus" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "kind" TEXT NOT NULL,
  "label" TEXT NOT NULL DEFAULT 'exemplar',
  "title" TEXT,
  "source_url" TEXT,
  "storage_bucket" TEXT,
  "storage_path" TEXT,
  "asset_id" TEXT,
  "transcript" TEXT,
  "extraction" TEXT NOT NULL DEFAULT '{}',
  "search_text" TEXT,
  "state" TEXT NOT NULL DEFAULT 'queued',
  "attempts" INTEGER NOT NULL DEFAULT 0,
  "last_error" TEXT,
  "contributed_by" TEXT NOT NULL DEFAULT 'adon',
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "indexed_at" TEXT,
  PRIMARY KEY ("id"),
  CONSTRAINT "marketing_corpus_kind_check" CHECK ((kind IN ('media', 'link', 'metrics', 'lesson', 'verdict'))),
  CONSTRAINT "marketing_corpus_label_check" CHECK ((label IN ('exemplar', 'counter_example', 'neutral'))),
  CONSTRAINT "marketing_corpus_state_check" CHECK ((state IN ('queued', 'extracting', 'indexed', 'failed', 'skipped'))),
  FOREIGN KEY ("tenant_id", "asset_id") REFERENCES "marketing_asset" ("tenant_id", "id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "marketing_event" (
  "id" INTEGER PRIMARY KEY,
  "tenant_id" TEXT NOT NULL,
  "at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "actor" TEXT NOT NULL,
  "verb" TEXT NOT NULL,
  "asset_id" TEXT,
  "detail" TEXT,
  FOREIGN KEY ("tenant_id", "asset_id") REFERENCES "marketing_asset" ("tenant_id", "id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "marketing_metric_daily" (
  "tenant_id" TEXT NOT NULL,
  "asset_id" TEXT NOT NULL,
  "date" TEXT NOT NULL,
  "impressions" INTEGER,
  "reach" INTEGER,
  "views" INTEGER,
  "clicks" INTEGER,
  "saves" INTEGER,
  "shares" INTEGER,
  "comments" INTEGER,
  "likes" INTEGER,
  "spend" TEXT,
  "conversions" INTEGER,
  "revenue" TEXT,
  "source" TEXT NOT NULL,
  "captured_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("tenant_id", "asset_id", "date", "source"),
  FOREIGN KEY ("tenant_id", "asset_id") REFERENCES "marketing_asset" ("tenant_id", "id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "marketing_request" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "kind" TEXT NOT NULL,
  "title" TEXT NOT NULL,
  "detail" TEXT,
  "channel" TEXT,
  "asset_id" TEXT,
  "priority" INTEGER NOT NULL DEFAULT 50,
  "status" TEXT NOT NULL DEFAULT 'open',
  "requester" TEXT NOT NULL DEFAULT 'adon',
  "claimed_by" TEXT,
  "response" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "claimed_at" TEXT,
  "done_at" TEXT,
  PRIMARY KEY ("id"),
  CONSTRAINT "marketing_request_kind_check" CHECK ((kind IN ('generate', 'variant', 'revise', 'research', 'question'))),
  CONSTRAINT "marketing_request_status_check" CHECK ((status IN ('open', 'claimed', 'done', 'dropped'))),
  FOREIGN KEY ("tenant_id", "asset_id") REFERENCES "marketing_asset" ("tenant_id", "id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "marketing_review" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "asset_id" TEXT NOT NULL,
  "decision" TEXT NOT NULL,
  "note" TEXT,
  "reviewer" TEXT NOT NULL DEFAULT 'adon',
  "reviewer_agent" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "acted_on_at" TEXT,
  PRIMARY KEY ("id"),
  CONSTRAINT "marketing_review_decision_check" CHECK ((decision IN ('approve', 'approve_with_changes', 'request_changes', 'reject', 'comment'))),
  CONSTRAINT "marketing_review_reason_required" CHECK (((decision IN ('approve', 'comment')) OR (COALESCE(trim(note), '') <> ''))),
  FOREIGN KEY ("tenant_id", "asset_id") REFERENCES "marketing_asset" ("tenant_id", "id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "n8n_webhook_secrets" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "profile_id" TEXT NOT NULL,
  "secret_hash" TEXT NOT NULL,
  "label" TEXT,
  "last_used_at" TEXT,
  "use_count" INTEGER NOT NULL DEFAULT 0,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "revoked_at" TEXT,
  "tenant_id" TEXT,
  PRIMARY KEY ("id"),
  FOREIGN KEY ("profile_id") REFERENCES "user_profiles" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "phone_lookup_jobs" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "lead_id" TEXT NOT NULL,
  "query_first_name" TEXT,
  "query_last_name" TEXT,
  "query_city" TEXT,
  "query_state" TEXT,
  "query_age" INTEGER,
  "status" TEXT NOT NULL DEFAULT 'pending',
  "error_message" TEXT,
  "phones" TEXT,
  "emails" TEXT,
  "matched_name" TEXT,
  "matched_age" INTEGER,
  "matched_city" TEXT,
  "matched_state" TEXT,
  "confidence" INTEGER,
  "source" TEXT,
  "detail_url" TEXT,
  "attempts" INTEGER NOT NULL DEFAULT 0,
  "requested_by" TEXT,
  "requested_by_email" TEXT,
  "trigger_source" TEXT NOT NULL DEFAULT 'manual',
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "claimed_at" TEXT,
  "completed_at" TEXT,
  PRIMARY KEY ("id"),
  CONSTRAINT "phone_lookup_jobs_status_check" CHECK ((status IN ('pending', 'running', 'completed', 'no_results', 'blocked', 'error'))),
  FOREIGN KEY ("lead_id") REFERENCES "tenant_records" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "plan_templates" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "profile_id" TEXT,
  "kind" TEXT NOT NULL,
  "mission" TEXT,
  "target_calls" INTEGER NOT NULL DEFAULT 0,
  "target_emails" INTEGER NOT NULL DEFAULT 0,
  "target_bookings" INTEGER NOT NULL DEFAULT 1,
  "schedule" TEXT NOT NULL DEFAULT '[]',
  "enabled" INTEGER NOT NULL DEFAULT 1,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("profile_id") REFERENCES "user_profiles" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "sequence_state" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "sequence_id" TEXT NOT NULL,
  "tenant_id" TEXT NOT NULL,
  "lead_id" TEXT NOT NULL,
  "step_index" INTEGER NOT NULL,
  "scheduled_for" TEXT NOT NULL,
  "status" TEXT NOT NULL DEFAULT 'scheduled',
  "attempt_count" INTEGER NOT NULL DEFAULT 0,
  "last_attempt_at" TEXT,
  "last_error" TEXT,
  "context_snapshot" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "claimed_at" TEXT,
  "claimed_by" TEXT,
  PRIMARY KEY ("id"),
  CONSTRAINT "sequence_state_status_check" CHECK ((status IN ('scheduled', 'sent', 'failed', 'cancelled', 'skipped'))),
  FOREIGN KEY ("sequence_id") REFERENCES "drip_sequences" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "sunbiz_conversation_state" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "provider" TEXT NOT NULL,
  "provider_conversation_id" TEXT NOT NULL,
  "lead_id" TEXT,
  "agent_account_id" TEXT,
  "qualification_state" TEXT NOT NULL DEFAULT '{}',
  "last_intent" TEXT,
  "last_action" TEXT,
  "automation_paused" INTEGER NOT NULL DEFAULT 0,
  "human_owner_id" TEXT,
  "knowledge_version" TEXT NOT NULL,
  "provider_cursor" TEXT,
  "retry_count" INTEGER NOT NULL DEFAULT 0,
  "last_error" TEXT,
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "sunbiz_conversation_state_provider_check" CHECK ((provider = 'texttorrent')),
  FOREIGN KEY ("agent_account_id") REFERENCES "sunbiz_agent_accounts" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "tenant_integration_credentials" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "service" TEXT NOT NULL,
  "field_key" TEXT NOT NULL,
  "encrypted_value" TEXT NOT NULL,
  "last_tested_at" TEXT,
  "last_test_ok" INTEGER,
  "last_test_error" TEXT,
  "created_by" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  FOREIGN KEY ("created_by") REFERENCES "user_profiles" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "texttorrent_inbound_work" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "account_id" TEXT NOT NULL,
  "provider_message_id" TEXT NOT NULL,
  "provider_conversation_id" TEXT,
  "source_interaction_id" TEXT,
  "inbound_message" TEXT NOT NULL,
  "conversation" TEXT NOT NULL DEFAULT '{}',
  "merchant_context" TEXT NOT NULL DEFAULT '{}',
  "voice_profile" TEXT NOT NULL DEFAULT '{}',
  "decision" TEXT,
  "priority" INTEGER NOT NULL DEFAULT 100,
  "status" TEXT NOT NULL DEFAULT 'pending',
  "attempts" INTEGER NOT NULL DEFAULT 0,
  "next_attempt_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "lease_owner" TEXT,
  "claimed_at" TEXT,
  "lease_expires_at" TEXT,
  "last_error" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "completed_at" TEXT,
  PRIMARY KEY ("id"),
  CONSTRAINT "texttorrent_inbound_work_status_check" CHECK ((status IN ('pending', 'running', 'drafted', 'escalated', 'suppressed', 'dead_letter'))),
  FOREIGN KEY ("account_id") REFERENCES "sunbiz_agent_accounts" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "client_signatures" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "contract_id" TEXT NOT NULL,
  "signer_name" TEXT NOT NULL,
  "signer_email" TEXT NOT NULL,
  "signature_png" TEXT,
  "signature_typed" TEXT,
  "signature_kind" TEXT NOT NULL DEFAULT 'drawn',
  "ip_address" TEXT,
  "user_agent" TEXT,
  "terms_sha256" TEXT,
  "signed_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "client_signatures_signature_kind_check" CHECK ((signature_kind IN ('drawn', 'typed'))),
  FOREIGN KEY ("contract_id") REFERENCES "contracts" ("id")
);

CREATE TABLE IF NOT EXISTS "renewal_outreach_events" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "funded_deal_id" TEXT NOT NULL,
  "lead_id" TEXT,
  "lender_id" TEXT,
  "assigned_agent_id" TEXT,
  "event_kind" TEXT NOT NULL DEFAULT '50_percent',
  "threshold_date" TEXT NOT NULL,
  "status" TEXT NOT NULL,
  "scheduled_send_id" TEXT,
  "internal_email_at" TEXT,
  "telegram_at" TEXT,
  "sent_at" TEXT,
  "attempts" INTEGER NOT NULL DEFAULT 0,
  "last_error" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "renewal_outreach_events_event_kind_check" CHECK ((event_kind = '50_percent')),
  CONSTRAINT "renewal_outreach_events_status_check" CHECK ((status IN ('review_required', 'pending', 'queued', 'sent', 'blocked', 'failed', 'cancelled'))),
  FOREIGN KEY ("funded_deal_id") REFERENCES "funded_deals" ("id"),
  FOREIGN KEY ("lender_id") REFERENCES "tenant_records" ("id"),
  FOREIGN KEY ("scheduled_send_id") REFERENCES "scheduled_sends" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "sunbiz_reply_drafts" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "conversation_state_id" TEXT NOT NULL,
  "agent_account_id" TEXT NOT NULL,
  "lead_id" TEXT,
  "thread_key" TEXT NOT NULL,
  "to_phone" TEXT NOT NULL,
  "original_text" TEXT NOT NULL,
  "final_text" TEXT,
  "status" TEXT NOT NULL DEFAULT 'pending',
  "intent" TEXT NOT NULL,
  "confidence" TEXT,
  "model_id" TEXT,
  "model_version" TEXT,
  "knowledge_version" TEXT NOT NULL,
  "source_interaction_id" TEXT,
  "provider_message_id" TEXT,
  "approved_by" TEXT,
  "approved_at" TEXT,
  "rejected_by" TEXT,
  "rejected_at" TEXT,
  "handoff_user_id" TEXT,
  "handoff_at" TEXT,
  "scheduled_send_id" TEXT,
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "updated_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  PRIMARY KEY ("id"),
  CONSTRAINT "sunbiz_reply_drafts_final_text_check" CHECK (((final_text IS NULL) OR ((length(final_text) >= 1) AND (length(final_text) <= 1600)))),
  CONSTRAINT "sunbiz_reply_drafts_original_text_check" CHECK (((length(original_text) >= 1) AND (length(original_text) <= 1600))),
  CONSTRAINT "sunbiz_reply_drafts_status_check" CHECK ((status IN ('pending', 'approved', 'rejected', 'cancelled', 'sent', 'failed'))),
  FOREIGN KEY ("agent_account_id") REFERENCES "sunbiz_agent_accounts" ("id"),
  FOREIGN KEY ("conversation_state_id") REFERENCES "sunbiz_conversation_state" ("id"),
  FOREIGN KEY ("scheduled_send_id") REFERENCES "scheduled_sends" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

CREATE TABLE IF NOT EXISTS "texttorrent_dead_letters" (
  "id" TEXT NOT NULL DEFAULT (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' || substr(lower(hex(randomblob(2))),2) || '-' || substr('89ab',abs(random())%4+1,1) || substr(lower(hex(randomblob(2))),2) || '-' || lower(hex(randomblob(6)))),
  "tenant_id" TEXT NOT NULL,
  "inbound_work_id" TEXT,
  "account_id" TEXT NOT NULL,
  "failure_code" TEXT NOT NULL,
  "attempts" INTEGER NOT NULL,
  "sanitized_metadata" TEXT NOT NULL DEFAULT '{}',
  "created_at" TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  "resolved_at" TEXT,
  PRIMARY KEY ("id"),
  FOREIGN KEY ("account_id") REFERENCES "sunbiz_agent_accounts" ("id"),
  FOREIGN KEY ("inbound_work_id") REFERENCES "texttorrent_inbound_work" ("id"),
  FOREIGN KEY ("tenant_id") REFERENCES "tenants" ("id")
);

-- indexes
CREATE UNIQUE INDEX IF NOT EXISTS "funnels_pkey" ON "funnels" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "funnels_slug_key" ON "funnels" (slug);
CREATE UNIQUE INDEX IF NOT EXISTS "funnel_entries_pkey" ON "funnel_entries" (id);
CREATE INDEX IF NOT EXISTS "idx_funnel_entries_funnel" ON "funnel_entries" (funnel_id);
CREATE INDEX IF NOT EXISTS "idx_funnel_entries_lead" ON "funnel_entries" (lead_id);
CREATE UNIQUE INDEX IF NOT EXISTS "conversation_threads_pkey" ON "conversation_threads" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "conversation_threads_tenant_id_thread_key_key" ON "conversation_threads" (tenant_id, thread_key);
CREATE INDEX IF NOT EXISTS "idx_conv_threads_status" ON "conversation_threads" (tenant_id, status, last_message_at DESC);
CREATE INDEX IF NOT EXISTS "idx_conv_threads_assigned" ON "conversation_threads" (tenant_id, assigned_to, last_message_at DESC);
CREATE INDEX IF NOT EXISTS "idx_conv_threads_lead" ON "conversation_threads" (tenant_id, lead_id);
CREATE INDEX IF NOT EXISTS "idx_conv_threads_recent" ON "conversation_threads" (tenant_id, last_message_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "agent_state_pkey" ON "agent_state" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "memories_pkey" ON "memories" (id);
CREATE INDEX IF NOT EXISTS "idx_memories_category" ON "memories" (category);
CREATE INDEX IF NOT EXISTS "idx_memories_confidence" ON "memories" (confidence_score DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "session_logs_pkey" ON "session_logs" (id);
CREATE INDEX IF NOT EXISTS "idx_session_logs_date" ON "session_logs" (session_date DESC);
CREATE INDEX IF NOT EXISTS "idx_session_logs_interface" ON "session_logs" (agent_interface);
CREATE UNIQUE INDEX IF NOT EXISTS "daily_logs_pkey" ON "daily_logs" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "daily_logs_log_date_key" ON "daily_logs" (log_date);
CREATE INDEX IF NOT EXISTS "idx_daily_logs_date" ON "daily_logs" (log_date DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "sops_pkey" ON "sops" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "sops_sop_id_key" ON "sops" (sop_id);
CREATE INDEX IF NOT EXISTS "idx_sops_category" ON "sops" (category);
CREATE INDEX IF NOT EXISTS "idx_sops_active" ON "sops" (is_active);
CREATE UNIQUE INDEX IF NOT EXISTS "self_healing_log_pkey" ON "self_healing_log" (id);
CREATE INDEX IF NOT EXISTS "idx_healing_tier" ON "self_healing_log" (tier);
CREATE INDEX IF NOT EXISTS "idx_healing_dimension" ON "self_healing_log" (dimension);
CREATE INDEX IF NOT EXISTS "idx_healing_date" ON "self_healing_log" (created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "growth_log_pkey" ON "growth_log" (id);
CREATE INDEX IF NOT EXISTS "idx_growth_category" ON "growth_log" (category);
CREATE INDEX IF NOT EXISTS "idx_growth_date" ON "growth_log" (created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "heartbeat_tasks_pkey" ON "heartbeat_tasks" (id);
CREATE INDEX IF NOT EXISTS "idx_heartbeat_active" ON "heartbeat_tasks" (is_active);
CREATE INDEX IF NOT EXISTS "idx_heartbeat_next" ON "heartbeat_tasks" (next_run);
CREATE UNIQUE INDEX IF NOT EXISTS "user_context_pkey" ON "user_context" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "user_context_key_category_key" ON "user_context" (key, category);
CREATE INDEX IF NOT EXISTS "idx_user_context_category" ON "user_context" (category);
CREATE UNIQUE INDEX IF NOT EXISTS "scheduled_calls_pkey" ON "scheduled_calls" (id);
CREATE INDEX IF NOT EXISTS "idx_scheduled_calls_due" ON "scheduled_calls" (status, scheduled_for);
CREATE INDEX IF NOT EXISTS "idx_scheduled_calls_tenant" ON "scheduled_calls" (tenant_id, status, scheduled_for);
CREATE UNIQUE INDEX IF NOT EXISTS "email_templates_pkey" ON "email_templates" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "nurture_sequences_pkey" ON "nurture_sequences" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "email_log_pkey" ON "email_log" (id);
CREATE INDEX IF NOT EXISTS "idx_email_log_lead" ON "email_log" (lead_id);
CREATE INDEX IF NOT EXISTS "idx_email_log_status" ON "email_log" (status);
CREATE UNIQUE INDEX IF NOT EXISTS "booking_slots_pkey" ON "booking_slots" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "booking_slots_slot_date_start_time_meeting_type_key" ON "booking_slots" (slot_date, start_time, meeting_type);
CREATE UNIQUE INDEX IF NOT EXISTS "bookings_pkey" ON "bookings" (id);
CREATE INDEX IF NOT EXISTS "idx_bookings_lead" ON "bookings" (lead_id);
CREATE INDEX IF NOT EXISTS "idx_bookings_status" ON "bookings" (status);
CREATE UNIQUE INDEX IF NOT EXISTS "inference_jobs_pkey" ON "inference_jobs" (id);
CREATE INDEX IF NOT EXISTS "idx_inference_jobs_due" ON "inference_jobs" (status, created_at);
CREATE INDEX IF NOT EXISTS "idx_inference_jobs_retry_due" ON "inference_jobs" (status, next_attempt_at, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS "agent_traces_pkey" ON "agent_traces" (id);
CREATE INDEX IF NOT EXISTS "idx_traces_trace_id" ON "agent_traces" (trace_id);
CREATE INDEX IF NOT EXISTS "idx_traces_timestamp" ON "agent_traces" ("timestamp" DESC);
CREATE INDEX IF NOT EXISTS "idx_traces_event_type" ON "agent_traces" (event_type);
CREATE INDEX IF NOT EXISTS "idx_traces_interface" ON "agent_traces" (agent_interface);
CREATE INDEX IF NOT EXISTS "idx_traces_status" ON "agent_traces" (status);
CREATE UNIQUE INDEX IF NOT EXISTS "revenue_events_pkey" ON "revenue_events" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "revenue_events_stripe_event_id_key" ON "revenue_events" (stripe_event_id);
CREATE INDEX IF NOT EXISTS "idx_revenue_events_type" ON "revenue_events" (type);
CREATE INDEX IF NOT EXISTS "idx_revenue_events_created" ON "revenue_events" (created_at);
CREATE UNIQUE INDEX IF NOT EXISTS "monthly_metrics_pkey" ON "monthly_metrics" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "monthly_metrics_month_key" ON "monthly_metrics" (month);
CREATE UNIQUE INDEX IF NOT EXISTS "content_calendar_pkey" ON "content_calendar" (id);
CREATE INDEX IF NOT EXISTS "idx_content_calendar_status" ON "content_calendar" (status);
CREATE INDEX IF NOT EXISTS "idx_content_calendar_scheduled" ON "content_calendar" (scheduled_for);
CREATE UNIQUE INDEX IF NOT EXISTS "self_modification_log_pkey" ON "self_modification_log" (id);
CREATE INDEX IF NOT EXISTS "idx_selfmod_file" ON "self_modification_log" (file_path);
CREATE INDEX IF NOT EXISTS "idx_selfmod_type" ON "self_modification_log" (change_type);
CREATE INDEX IF NOT EXISTS "idx_selfmod_date" ON "self_modification_log" (created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "content_templates_pkey" ON "content_templates" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "agent_email_settings_pkey" ON "agent_email_settings" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "agent_email_settings_tenant_id_user_id_key" ON "agent_email_settings" (tenant_id, user_id);
CREATE INDEX IF NOT EXISTS "agent_email_settings_active_idx" ON "agent_email_settings" (last_processed_at) WHERE (mode <> 'off');
CREATE UNIQUE INDEX IF NOT EXISTS "funnel_leads_pkey" ON "funnel_leads" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "memories_episodic_pkey" ON "memories_episodic" (id);
CREATE INDEX IF NOT EXISTS "idx_mem_ep_lead" ON "memories_episodic" (related_lead_id);
CREATE INDEX IF NOT EXISTS "idx_mem_ep_expires" ON "memories_episodic" (expires_at);
CREATE UNIQUE INDEX IF NOT EXISTS "memories_semantic_pkey" ON "memories_semantic" (id);
CREATE INDEX IF NOT EXISTS "idx_mem_sem_domain" ON "memories_semantic" (domain);
CREATE INDEX IF NOT EXISTS "idx_mem_sem_confidence" ON "memories_semantic" (confidence DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "performance_metrics_pkey" ON "performance_metrics" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "performance_metrics_metric_date_agent_interface_key" ON "performance_metrics" (metric_date, agent_interface);
CREATE INDEX IF NOT EXISTS "idx_metrics_date" ON "performance_metrics" (metric_date DESC);
CREATE INDEX IF NOT EXISTS "agent_email_snapshots_lookup_idx" ON "agent_email_snapshots" (tenant_id, user_id, captured_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "agent_email_snapshots_pkey" ON "agent_email_snapshots" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "skill_activation_pkey" ON "skill_activation" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "skill_activation_item_type_item_id_key" ON "skill_activation" (item_type, item_id);
CREATE INDEX IF NOT EXISTS "idx_activation_score" ON "skill_activation" (activation_score DESC);
CREATE INDEX IF NOT EXISTS "idx_activation_status" ON "skill_activation" (status);
CREATE UNIQUE INDEX IF NOT EXISTS "campaign_metric_snapshots_pkey" ON "campaign_metric_snapshots" (id);
CREATE INDEX IF NOT EXISTS "idx_camp_snap" ON "campaign_metric_snapshots" (tt_campaign_id, snapshot_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "agent_voice_profiles_pkey" ON "agent_voice_profiles" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "agent_voice_profiles_tenant_id_rep_user_id_channel_key" ON "agent_voice_profiles" (tenant_id, rep_user_id, channel);
CREATE INDEX IF NOT EXISTS "idx_voice_profiles_rep" ON "agent_voice_profiles" (tenant_id, rep_user_id);
CREATE UNIQUE INDEX IF NOT EXISTS "agent_decisions_pkey" ON "agent_decisions" (id);
CREATE INDEX IF NOT EXISTS "idx_agent_decisions_tick" ON "agent_decisions" (tick_id, created_at);
CREATE INDEX IF NOT EXISTS "idx_agent_decisions_lead" ON "agent_decisions" (target_lead_id, created_at DESC) WHERE (target_lead_id IS NOT NULL);
CREATE INDEX IF NOT EXISTS "idx_agent_decisions_created" ON "agent_decisions" (created_at DESC);
CREATE INDEX IF NOT EXISTS "agent_decisions_tenant_id_idx" ON "agent_decisions" (tenant_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "memories_procedural_pkey" ON "memories_procedural" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "memories_procedural_workflow_name_key" ON "memories_procedural" (workflow_name);
CREATE INDEX IF NOT EXISTS "idx_mem_proc_status" ON "memories_procedural" (status);
CREATE INDEX IF NOT EXISTS "idx_mem_proc_name" ON "memories_procedural" (workflow_name);
CREATE UNIQUE INDEX IF NOT EXISTS "shadow_decisions_pkey" ON "shadow_decisions" (id);
CREATE INDEX IF NOT EXISTS "idx_shadow_decisions_run" ON "shadow_decisions" (comparison_run_id, created_at);
CREATE INDEX IF NOT EXISTS "idx_shadow_decisions_agent_source" ON "shadow_decisions" (agent_source, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "agent_state_snapshot_pkey" ON "agent_state_snapshot" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "agent_state_snapshot_agent_name_key" ON "agent_state_snapshot" (agent_name);
CREATE INDEX IF NOT EXISTS "idx_agent_state_snapshot_agent" ON "agent_state_snapshot" (agent_name);
CREATE UNIQUE INDEX IF NOT EXISTS "drift_alerts_pkey" ON "drift_alerts" (id);
CREATE INDEX IF NOT EXISTS "idx_drift_alerts_severity" ON "drift_alerts" (severity, acknowledged, created_at DESC);
CREATE INDEX IF NOT EXISTS "idx_drift_alerts_metric" ON "drift_alerts" (metric_name, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "drift_baselines_pkey" ON "drift_baselines" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "drift_baselines_metric_name_dimension_key_key" ON "drift_baselines" (metric_name, dimension_key);
CREATE INDEX IF NOT EXISTS "idx_drift_baselines_metric" ON "drift_baselines" (metric_name, dimension_key);
CREATE UNIQUE INDEX IF NOT EXISTS "lead_edges_pkey" ON "lead_edges" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "lead_edges_from_lead_id_to_lead_id_edge_type_key" ON "lead_edges" (from_lead_id, to_lead_id, edge_type);
CREATE INDEX IF NOT EXISTS "idx_lead_edges_from" ON "lead_edges" (from_lead_id, edge_type);
CREATE INDEX IF NOT EXISTS "idx_lead_edges_to" ON "lead_edges" (to_lead_id, edge_type);
CREATE INDEX IF NOT EXISTS "idx_lead_edges_type_weight" ON "lead_edges" (edge_type, weight DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "skills_registry_pkey" ON "skills_registry" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "skills_registry_skill_name_key" ON "skills_registry" (skill_name);
CREATE INDEX IF NOT EXISTS "idx_skills_name" ON "skills_registry" (skill_name);
CREATE INDEX IF NOT EXISTS "idx_skills_registry_category" ON "skills_registry" (category);
CREATE INDEX IF NOT EXISTS "idx_skills_registry_tier" ON "skills_registry" (tier);
CREATE INDEX IF NOT EXISTS "idx_skills_registry_owner_agent" ON "skills_registry" (owner_agent);
CREATE INDEX IF NOT EXISTS "idx_skills_registry_risk_level" ON "skills_registry" (risk_level);
CREATE UNIQUE INDEX IF NOT EXISTS "daily_plans_pkey" ON "daily_plans" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "daily_plans_profile_id_plan_date_key" ON "daily_plans" (profile_id, plan_date);
CREATE INDEX IF NOT EXISTS "idx_daily_plans_profile_date" ON "daily_plans" (profile_id, plan_date DESC);
CREATE INDEX IF NOT EXISTS "idx_daily_plans_tenant" ON "daily_plans" (tenant_id);
CREATE UNIQUE INDEX IF NOT EXISTS "user_profiles_pkey" ON "user_profiles" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "user_profiles_auth_user_id_key" ON "user_profiles" (auth_user_id);
CREATE UNIQUE INDEX IF NOT EXISTS "user_profiles_email_key" ON "user_profiles" (email);
CREATE INDEX IF NOT EXISTS "idx_user_profiles_email" ON "user_profiles" (email);
CREATE INDEX IF NOT EXISTS "idx_user_profiles_auth_user_id" ON "user_profiles" (auth_user_id);
CREATE INDEX IF NOT EXISTS "idx_user_profiles_tenant" ON "user_profiles" (tenant_id);
CREATE UNIQUE INDEX IF NOT EXISTS "user_profiles_one_owner_per_tenant" ON "user_profiles" (tenant_id) WHERE (is_owner = true);
CREATE UNIQUE INDEX IF NOT EXISTS "n8n_webhook_secrets_pkey" ON "n8n_webhook_secrets" (id);
CREATE INDEX IF NOT EXISTS "idx_n8n_secrets_profile" ON "n8n_webhook_secrets" (profile_id);
CREATE INDEX IF NOT EXISTS "idx_n8n_secrets_hash" ON "n8n_webhook_secrets" (secret_hash);
CREATE UNIQUE INDEX IF NOT EXISTS "leads_pkey" ON "leads" (id);
CREATE INDEX IF NOT EXISTS "idx_leads_tenant" ON "leads" (tenant_id);
CREATE UNIQUE INDEX IF NOT EXISTS "integrations_health_pkey" ON "integrations_health" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "integrations_health_profile_id_service_key" ON "integrations_health" (profile_id, service);
CREATE INDEX IF NOT EXISTS "idx_integrations_profile_service" ON "integrations_health" (profile_id, service);
CREATE INDEX IF NOT EXISTS "idx_integrations_health_tenant" ON "integrations_health" (tenant_id);
CREATE UNIQUE INDEX IF NOT EXISTS "integrations_health_profile_service_uniq" ON "integrations_health" (profile_id, service);
CREATE UNIQUE INDEX IF NOT EXISTS "plan_templates_pkey" ON "plan_templates" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "plan_templates_profile_id_kind_key" ON "plan_templates" (profile_id, kind);
CREATE INDEX IF NOT EXISTS "idx_plan_templates_tenant" ON "plan_templates" (tenant_id);
CREATE INDEX IF NOT EXISTS "idx_plan_templates_profile_kind" ON "plan_templates" (profile_id, kind);
CREATE UNIQUE INDEX IF NOT EXISTS "tenants_pkey" ON "tenants" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "tenants_slug_key" ON "tenants" (slug);
CREATE INDEX IF NOT EXISTS "idx_tenants_slug" ON "tenants" (slug);
CREATE INDEX IF NOT EXISTS "idx_tenants_purchase_status" ON "tenants" (purchase_status);
CREATE UNIQUE INDEX IF NOT EXISTS "agent_model_config_pkey" ON "agent_model_config" (id);
CREATE INDEX IF NOT EXISTS "idx_agent_model_config_tenant" ON "agent_model_config" (tenant_id);
CREATE INDEX IF NOT EXISTS "idx_agent_model_config_user" ON "agent_model_config" (tenant_id, user_id, agent_key) WHERE (user_id IS NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS "idx_agent_model_config_default_per_agent" ON "agent_model_config" (tenant_id, agent_key) WHERE (user_id IS NULL);
CREATE UNIQUE INDEX IF NOT EXISTS "idx_agent_model_config_override_per_user" ON "agent_model_config" (tenant_id, user_id, agent_key) WHERE (user_id IS NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS "chat_sessions_pkey" ON "chat_sessions" (id);
CREATE INDEX IF NOT EXISTS "idx_chat_sessions_tenant" ON "chat_sessions" (tenant_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS "idx_chat_sessions_agent" ON "chat_sessions" (tenant_id, agent_key, updated_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "chat_messages_pkey" ON "chat_messages" (id);
CREATE INDEX IF NOT EXISTS "idx_chat_messages_session" ON "chat_messages" (session_id, created_at);
CREATE INDEX IF NOT EXISTS "idx_chat_messages_tenant" ON "chat_messages" (tenant_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "mrr_snapshots_pkey" ON "mrr_snapshots" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "mrr_snapshots_tenant_id_snapshot_date_key" ON "mrr_snapshots" (tenant_id, snapshot_date);
CREATE INDEX IF NOT EXISTS "idx_mrr_snapshots_tenant_date" ON "mrr_snapshots" (tenant_id, snapshot_date DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "agent_messages_pkey" ON "agent_messages" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "agent_messages_tenant_id_message_id_key" ON "agent_messages" (tenant_id, message_id);
CREATE INDEX IF NOT EXISTS "agent_messages_tenant_to_unread_idx" ON "agent_messages" (tenant_id, to_agent, priority, created_at DESC) WHERE (read_at IS NULL);
CREATE INDEX IF NOT EXISTS "agent_messages_tenant_to_read_idx" ON "agent_messages" (tenant_id, to_agent, created_at DESC) WHERE (read_at IS NOT NULL);
CREATE INDEX IF NOT EXISTS "agent_messages_thread_idx" ON "agent_messages" (tenant_id, thread_id);
CREATE UNIQUE INDEX IF NOT EXISTS "bridge_pair_codes_pkey" ON "bridge_pair_codes" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "bridge_pair_codes_code_key" ON "bridge_pair_codes" (code);
CREATE INDEX IF NOT EXISTS "idx_bridge_pair_codes_code_active" ON "bridge_pair_codes" (code) WHERE (consumed_at IS NULL);
CREATE INDEX IF NOT EXISTS "idx_bridge_pair_codes_tenant" ON "bridge_pair_codes" (tenant_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "bridge_pairings_pkey" ON "bridge_pairings" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "bridge_pairings_pairing_code_key" ON "bridge_pairings" (pairing_code);
CREATE INDEX IF NOT EXISTS "idx_bridge_pairings_tenant" ON "bridge_pairings" (tenant_id) WHERE (revoked_at IS NULL);
CREATE INDEX IF NOT EXISTS "idx_bridge_pairings_pairing_code" ON "bridge_pairings" (pairing_code) WHERE (pairing_code IS NOT NULL);
CREATE INDEX IF NOT EXISTS "idx_bridge_pairings_token_hash" ON "bridge_pairings" (bridge_token_hash) WHERE (bridge_token_hash IS NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS "idx_bridge_pairings_unique_live_machine" ON "bridge_pairings" (tenant_id, machine_fingerprint) WHERE ((revoked_at IS NULL) AND (machine_fingerprint IS NOT NULL));
CREATE UNIQUE INDEX IF NOT EXISTS "pair_attempts_pkey" ON "pair_attempts" (id);
CREATE INDEX IF NOT EXISTS "idx_pair_attempts_profile_recent" ON "pair_attempts" (profile_id, attempted_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "oasis_quests_pkey" ON "oasis_quests" (id);
CREATE INDEX IF NOT EXISTS "idx_oasis_quests_status" ON "oasis_quests" (status, bucket);
CREATE INDEX IF NOT EXISTS "idx_oasis_quests_updated" ON "oasis_quests" (updated_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "agent_events_pkey" ON "agent_events" (id);
CREATE INDEX IF NOT EXISTS "idx_agent_events_type" ON "agent_events" (event_type, published_at DESC);
CREATE INDEX IF NOT EXISTS "idx_agent_events_target" ON "agent_events" (target_agent, published_at DESC) WHERE (target_agent IS NOT NULL);
CREATE INDEX IF NOT EXISTS "idx_agent_events_correlation" ON "agent_events" (correlation_id) WHERE (correlation_id IS NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS "idx_agent_events_idem" ON "agent_events" (idempotency_key) WHERE (idempotency_key IS NOT NULL);
CREATE INDEX IF NOT EXISTS "idx_agent_events_target_pending" ON "agent_events" (target_agent, status, published_at) WHERE (status = 'pending');
CREATE INDEX IF NOT EXISTS "idx_agent_events_broadcast_pending" ON "agent_events" (status, published_at) WHERE ((status = 'pending') AND (target_agent IS NULL));
CREATE INDEX IF NOT EXISTS "idx_cold_mb_tenant_ready" ON "cold_sending_mailboxes" (tenant_id, active, warmup_status, last_send_at);
CREATE UNIQUE INDEX IF NOT EXISTS "cold_sending_mailboxes_pkey" ON "cold_sending_mailboxes" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "cold_sending_mailboxes_tenant_id_address_key" ON "cold_sending_mailboxes" (tenant_id, address);
CREATE UNIQUE INDEX IF NOT EXISTS "tenant_invites_pkey" ON "tenant_invites" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "tenant_invites_token_hash_key" ON "tenant_invites" (token_hash);
CREATE INDEX IF NOT EXISTS "idx_tenant_invites_active" ON "tenant_invites" (tenant_id) WHERE ((redeemed_at IS NULL) AND (revoked_at IS NULL));
CREATE INDEX IF NOT EXISTS "idx_tenant_invites_token_hash" ON "tenant_invites" (token_hash) WHERE ((redeemed_at IS NULL) AND (revoked_at IS NULL));
CREATE UNIQUE INDEX IF NOT EXISTS "exec_overrides_pkey" ON "exec_overrides" (request_id);
CREATE INDEX IF NOT EXISTS "idx_exec_overrides_status" ON "exec_overrides" (status, expires_at DESC);
CREATE INDEX IF NOT EXISTS "idx_exec_overrides_pending_intent" ON "exec_overrides" (dashboard_decided_at) WHERE ((dashboard_decision IS NOT NULL) AND (consumer_synced_at IS NULL));
CREATE INDEX IF NOT EXISTS "idx_exec_overrides_workspace" ON "exec_overrides" (workspace_label, ts DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "tenant_manifests_pkey" ON "tenant_manifests" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "tenant_manifests_slug_key" ON "tenant_manifests" (slug);
CREATE INDEX IF NOT EXISTS "idx_tenant_manifests_tenant_id" ON "tenant_manifests" (tenant_id);
CREATE UNIQUE INDEX IF NOT EXISTS "tenant_manifests_tenant_id_key" ON "tenant_manifests" (tenant_id);
CREATE UNIQUE INDEX IF NOT EXISTS "manifest_audit_log_pkey" ON "manifest_audit_log" (id);
CREATE INDEX IF NOT EXISTS "idx_manifest_audit_manifest" ON "manifest_audit_log" (manifest_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "tenant_records_pkey" ON "tenant_records" (id);
CREATE INDEX IF NOT EXISTS "idx_tenant_records_tenant_entity" ON "tenant_records" (tenant_id, entity_type, updated_at DESC);
CREATE INDEX IF NOT EXISTS "idx_tenant_records_sunbiz_merchant_stage" ON "tenant_records" (tenant_id, ((data ->> 'merchant_stage'))) WHERE (entity_type = 'lead');
CREATE INDEX IF NOT EXISTS "idx_tenant_records_sunbiz_deal_stage" ON "tenant_records" (tenant_id, ((data ->> 'deal_stage'))) WHERE (entity_type = 'application');
CREATE INDEX IF NOT EXISTS "idx_tenant_records_application_lead_id" ON "tenant_records" (((data ->> 'lead_id'))) WHERE (entity_type = 'application');
CREATE INDEX IF NOT EXISTS "idx_tenant_records_assigned_to" ON "tenant_records" (tenant_id, ((data ->> 'assigned_to'))) WHERE ((entity_type IN ('lead', 'application', 'funded_deal', 'renewal')) AND ((data ->> 'assigned_to') IS NOT NULL));
CREATE INDEX IF NOT EXISTS "idx_tenant_records_tenant_entity_for_match" ON "tenant_records" (tenant_id, entity_type);
CREATE INDEX IF NOT EXISTS "idx_tenant_records_email_lower" ON "tenant_records" (tenant_id, lower((data ->> 'email'))) WHERE (entity_type = 'lead');
CREATE UNIQUE INDEX IF NOT EXISTS "agents_pkey" ON "agents" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "agents_slug_key" ON "agents" (slug);
CREATE INDEX IF NOT EXISTS "idx_agents_category" ON "agents" (category);
CREATE INDEX IF NOT EXISTS "idx_agents_public" ON "agents" (is_public) WHERE (is_public = true);
CREATE INDEX IF NOT EXISTS "idx_agents_tenant" ON "agents" (tenant_id) WHERE (tenant_id IS NOT NULL);
CREATE INDEX IF NOT EXISTS "idx_cc_templates_tenant" ON "cc_email_templates" (tenant_id, updated_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "cc_email_templates_pkey" ON "cc_email_templates" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "forms_pkey" ON "forms" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "forms_tenant_id_slug_key" ON "forms" (tenant_id, slug);
CREATE INDEX IF NOT EXISTS "idx_forms_tenant_enabled" ON "forms" (tenant_id, enabled) WHERE (enabled = true);
CREATE UNIQUE INDEX IF NOT EXISTS "form_submissions_pkey" ON "form_submissions" (id);
CREATE INDEX IF NOT EXISTS "idx_form_submissions_form" ON "form_submissions" (form_id, submitted_at DESC);
CREATE INDEX IF NOT EXISTS "idx_form_submissions_lead" ON "form_submissions" (tenant_id, lead_id, submitted_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "form_views_pkey" ON "form_views" (id);
CREATE INDEX IF NOT EXISTS "idx_form_views_lead_recent" ON "form_views" (tenant_id, lead_id, viewed_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "sequence_state_pkey" ON "sequence_state" (id);
CREATE INDEX IF NOT EXISTS "idx_sequence_state_due" ON "sequence_state" (scheduled_for) WHERE (status = 'scheduled');
CREATE INDEX IF NOT EXISTS "idx_sequence_state_tenant_lead" ON "sequence_state" (tenant_id, lead_id, created_at DESC);
CREATE INDEX IF NOT EXISTS "idx_sequence_state_lead_seq_active" ON "sequence_state" (sequence_id, lead_id) WHERE (status IN ('scheduled', 'failed'));
CREATE UNIQUE INDEX IF NOT EXISTS "idx_sequence_state_one_active_per_lead" ON "sequence_state" (sequence_id, lead_id) WHERE (status IN ('scheduled', 'failed'));
CREATE INDEX IF NOT EXISTS "idx_sequence_state_claimable" ON "sequence_state" (scheduled_for) WHERE ((status = 'scheduled') AND (claimed_at IS NULL));
CREATE UNIQUE INDEX IF NOT EXISTS "tenant_cron_jobs_pkey" ON "tenant_cron_jobs" (id);
CREATE INDEX IF NOT EXISTS "idx_tenant_cron_jobs_tenant_enabled" ON "tenant_cron_jobs" (tenant_id, enabled) WHERE (enabled = true);
CREATE INDEX IF NOT EXISTS "idx_tenant_cron_jobs_agent" ON "tenant_cron_jobs" (tenant_id, agent_key);
CREATE UNIQUE INDEX IF NOT EXISTS "application_lender_threads_pkey" ON "application_lender_threads" (id);
CREATE INDEX IF NOT EXISTS "idx_lender_threads_tenant_status" ON "application_lender_threads" (tenant_id, status, last_response_at DESC);
CREATE INDEX IF NOT EXISTS "idx_lender_threads_application" ON "application_lender_threads" (application_id);
CREATE INDEX IF NOT EXISTS "idx_lender_threads_gmail" ON "application_lender_threads" (tenant_id, gmail_thread_id) WHERE (gmail_thread_id IS NOT NULL);
CREATE INDEX IF NOT EXISTS "idx_application_lender_threads_send_interaction_id" ON "application_lender_threads" (send_interaction_id) WHERE (send_interaction_id IS NOT NULL);
CREATE INDEX IF NOT EXISTS "idx_lender_threads_application_lender" ON "application_lender_threads" (application_id, lender_id, created_at DESC);
CREATE INDEX IF NOT EXISTS "idx_application_lender_threads_email_identity" ON "application_lender_threads" (tenant_id, email_identity, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "followup_drip_enrollments_pkey" ON "followup_drip_enrollments" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "followup_drip_enrollments_tenant_id_lead_id_cadence_key_key" ON "followup_drip_enrollments" (tenant_id, lead_id, cadence_key);
CREATE INDEX IF NOT EXISTS "idx_fde_due" ON "followup_drip_enrollments" (status, scheduled_for);
CREATE INDEX IF NOT EXISTS "idx_fde_lead" ON "followup_drip_enrollments" (lead_id, created_at DESC);
CREATE INDEX IF NOT EXISTS "idx_fde_tenant" ON "followup_drip_enrollments" (tenant_id, updated_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "drip_sequences_pkey" ON "drip_sequences" (id);
CREATE INDEX IF NOT EXISTS "idx_drip_sequences_tenant_enabled" ON "drip_sequences" (tenant_id, enabled) WHERE (enabled = true);
CREATE INDEX IF NOT EXISTS "idx_drip_sequences_tenant_event" ON "drip_sequences" (tenant_id, trigger_event) WHERE (enabled = true);
CREATE UNIQUE INDEX IF NOT EXISTS "email_open_events_pkey" ON "email_open_events" (id);
CREATE INDEX IF NOT EXISTS "idx_email_open_events_tenant_lead" ON "email_open_events" (tenant_id, lead_id, opened_at DESC);
CREATE INDEX IF NOT EXISTS "idx_email_open_events_message" ON "email_open_events" (outbound_message_id);
CREATE UNIQUE INDEX IF NOT EXISTS "idx_email_open_events_dedup" ON "email_open_events" (outbound_message_id, ip_hash);
CREATE UNIQUE INDEX IF NOT EXISTS "tenant_audit_log_pkey" ON "tenant_audit_log" (id);
CREATE INDEX IF NOT EXISTS "idx_tenant_audit_log_tenant_time" ON "tenant_audit_log" (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS "idx_tenant_audit_log_actor" ON "tenant_audit_log" (tenant_id, actor_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS "idx_tenant_audit_log_action" ON "tenant_audit_log" (tenant_id, action_type, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "agent_alerts_pkey" ON "agent_alerts" (id);
CREATE INDEX IF NOT EXISTS "idx_agent_alerts_open" ON "agent_alerts" (tenant_id, severity, created_at DESC) WHERE (resolved_at IS NULL);
CREATE INDEX IF NOT EXISTS "idx_agent_alerts_subject" ON "agent_alerts" (tenant_id, subject_type, subject_id);
CREATE UNIQUE INDEX IF NOT EXISTS "idx_agent_alerts_dedup" ON "agent_alerts" (tenant_id, dedup_key) WHERE ((dedup_key IS NOT NULL) AND (resolved_at IS NULL));
CREATE UNIQUE INDEX IF NOT EXISTS "lead_documents_pkey" ON "lead_documents" (id);
CREATE INDEX IF NOT EXISTS "idx_lead_documents_tenant_lead" ON "lead_documents" (tenant_id, lead_id, uploaded_at DESC);
CREATE INDEX IF NOT EXISTS "idx_lead_documents_doc_type" ON "lead_documents" (tenant_id, doc_type) WHERE (doc_type <> 'unclassified');
CREATE UNIQUE INDEX IF NOT EXISTS "drip_template_pool_pkey" ON "drip_template_pool" (id);
CREATE INDEX IF NOT EXISTS "idx_drip_pool_lookup" ON "drip_template_pool" (tenant_id, brand, stage, role, status);
CREATE UNIQUE INDEX IF NOT EXISTS "tenant_integration_credentials_pkey" ON "tenant_integration_credentials" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "tenant_integration_credentials_tenant_id_service_field_key_key" ON "tenant_integration_credentials" (tenant_id, service, field_key);
CREATE INDEX IF NOT EXISTS "idx_tenant_integration_credentials_tenant" ON "tenant_integration_credentials" (tenant_id, service);
CREATE INDEX IF NOT EXISTS "idx_tenant_integration_credentials_service" ON "tenant_integration_credentials" (tenant_id, service, field_key);
CREATE UNIQUE INDEX IF NOT EXISTS "chat_attachments_pkey" ON "chat_attachments" (id);
CREATE INDEX IF NOT EXISTS "idx_chat_attachments_tenant_user_created" ON "chat_attachments" (tenant_id, auth_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS "idx_chat_attachments_session" ON "chat_attachments" (tenant_id, session_id, created_at DESC) WHERE (session_id IS NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS "application_underwriting_pkey" ON "application_underwriting" (id);
CREATE INDEX IF NOT EXISTS "idx_app_underwriting_tenant_app" ON "application_underwriting" (tenant_id, application_id, run_at DESC);
CREATE INDEX IF NOT EXISTS "idx_app_underwriting_status" ON "application_underwriting" (tenant_id, status) WHERE (status IN ('pending', 'parsing'));
CREATE UNIQUE INDEX IF NOT EXISTS "follow_up_tasks_pkey" ON "follow_up_tasks" (id);
CREATE INDEX IF NOT EXISTS "idx_follow_up_tenant_status_due" ON "follow_up_tasks" (tenant_id, status, due_at) WHERE (status IN ('open', 'in_progress'));
CREATE INDEX IF NOT EXISTS "idx_follow_up_lead" ON "follow_up_tasks" (tenant_id, lead_id, created_at DESC) WHERE (lead_id IS NOT NULL);
CREATE INDEX IF NOT EXISTS "idx_follow_up_application" ON "follow_up_tasks" (tenant_id, application_id, created_at DESC) WHERE (application_id IS NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS "daily_plan_items_pkey" ON "daily_plan_items" (id);
CREATE INDEX IF NOT EXISTS "idx_daily_plan_tenant_date" ON "daily_plan_items" (tenant_id, plan_date, priority DESC, category);
CREATE INDEX IF NOT EXISTS "idx_daily_plan_assignee" ON "daily_plan_items" (tenant_id, assignee_user_id, plan_date, status) WHERE (assignee_user_id IS NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS "daily_plan_items_tenant_date_lead_category_uniq" ON "daily_plan_items" (tenant_id, plan_date, lead_id, category);
CREATE UNIQUE INDEX IF NOT EXISTS "cold_lead_lists_pkey" ON "cold_lead_lists" (id);
CREATE INDEX IF NOT EXISTS "idx_cold_lists_tenant" ON "cold_lead_lists" (tenant_id, created_at DESC) WHERE (archived_at IS NULL);
CREATE UNIQUE INDEX IF NOT EXISTS "cold_leads_pkey" ON "cold_leads" (id);
CREATE INDEX IF NOT EXISTS "idx_cold_leads_tenant_list_stage" ON "cold_leads" (tenant_id, list_id, stage);
CREATE INDEX IF NOT EXISTS "idx_cold_leads_promoted" ON "cold_leads" (tenant_id, promoted_lead_id) WHERE (promoted_lead_id IS NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS "idx_cold_leads_dedup" ON "cold_leads" (tenant_id, list_id, COALESCE(lower(email), ''), COALESCE(phone, ''));
CREATE UNIQUE INDEX IF NOT EXISTS "cold_outreach_campaigns_pkey" ON "cold_outreach_campaigns" (id);
CREATE INDEX IF NOT EXISTS "idx_outreach_campaigns_tenant_status" ON "cold_outreach_campaigns" (tenant_id, status, scheduled_for) WHERE (status IN ('queued', 'sending'));
CREATE UNIQUE INDEX IF NOT EXISTS "known_funding_companies_pkey" ON "known_funding_companies" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "known_funding_companies_name_key" ON "known_funding_companies" (name);
CREATE INDEX IF NOT EXISTS "idx_known_funding_active" ON "known_funding_companies" (active, name) WHERE (active = true);
CREATE INDEX IF NOT EXISTS "idx_known_funding_tier" ON "known_funding_companies" (tier, active) WHERE ((active = true) AND (tier IS NOT NULL));
CREATE UNIQUE INDEX IF NOT EXISTS "cold_outreach_recipients_pkey" ON "cold_outreach_recipients" (id);
CREATE INDEX IF NOT EXISTS "idx_outreach_recipients_campaign_status" ON "cold_outreach_recipients" (campaign_id, status, sent_at);
CREATE INDEX IF NOT EXISTS "idx_outreach_recipients_tenant_pending" ON "cold_outreach_recipients" (tenant_id, status) WHERE (status = 'pending');
CREATE UNIQUE INDEX IF NOT EXISTS "shop_out_warnings_pkey" ON "shop_out_warnings" (id);
CREATE INDEX IF NOT EXISTS "idx_shop_warnings_tenant_app" ON "shop_out_warnings" (tenant_id, application_id, detected_at DESC);
CREATE INDEX IF NOT EXISTS "idx_shop_warnings_overridden" ON "shop_out_warnings" (tenant_id, overridden, severity) WHERE (overridden = true);
CREATE UNIQUE INDEX IF NOT EXISTS "offer_sources_pkey" ON "offer_sources" (id);
CREATE INDEX IF NOT EXISTS "idx_offer_sources_tenant_offer" ON "offer_sources" (tenant_id, offer_record_id);
CREATE INDEX IF NOT EXISTS "idx_offer_sources_email" ON "offer_sources" (source_email_id) WHERE (source_email_id IS NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS "email_thread_monitors_pkey" ON "email_thread_monitors" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "idx_email_monitors_tenant_kind" ON "email_thread_monitors" (tenant_id, monitor_kind);
CREATE INDEX IF NOT EXISTS "idx_email_monitors_due" ON "email_thread_monitors" (status, next_check_at) WHERE (status = 'active');
CREATE UNIQUE INDEX IF NOT EXISTS "lender_feedback_pkey" ON "lender_feedback" (id);
CREATE INDEX IF NOT EXISTS "idx_lender_feedback_tenant_lender_outcome" ON "lender_feedback" (tenant_id, lender_id, outcome, extracted_at DESC);
CREATE INDEX IF NOT EXISTS "idx_lender_feedback_industry" ON "lender_feedback" (tenant_id, industry, outcome) WHERE (industry IS NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS "personalized_form_links_pkey" ON "personalized_form_links" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "personalized_form_links_token_key" ON "personalized_form_links" (token);
CREATE INDEX IF NOT EXISTS "idx_form_links_lead" ON "personalized_form_links" (tenant_id, lead_id, form_id, form_step, created_at DESC);
CREATE INDEX IF NOT EXISTS "idx_form_links_unsubmitted" ON "personalized_form_links" (tenant_id, expires_at) WHERE ((submitted_at IS NULL) AND (revoked_at IS NULL));
CREATE UNIQUE INDEX IF NOT EXISTS "agent_memory_notes_pkey" ON "agent_memory_notes" (id);
CREATE INDEX IF NOT EXISTS "idx_memory_notes_tenant_entity" ON "agent_memory_notes" (tenant_id, entity_type, entity_id, created_at DESC) WHERE (entity_id IS NOT NULL);
CREATE INDEX IF NOT EXISTS "idx_memory_notes_pinned" ON "agent_memory_notes" (tenant_id, pinned, created_at DESC) WHERE (pinned = true);
CREATE UNIQUE INDEX IF NOT EXISTS "shopping_threads_pkey" ON "shopping_threads" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "shopping_threads_tenant_id_lead_id_round_number_key" ON "shopping_threads" (tenant_id, lead_id, round_number);
CREATE INDEX IF NOT EXISTS "idx_shopping_threads_lead" ON "shopping_threads" (tenant_id, lead_id, round_number DESC);
CREATE INDEX IF NOT EXISTS "idx_shopping_threads_agent" ON "shopping_threads" (tenant_id, agent_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS "idx_shopping_threads_status" ON "shopping_threads" (tenant_id, status, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "user_integration_credentials_pkey" ON "user_integration_credentials" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "user_integration_credentials_tenant_id_user_id_service_fiel_key" ON "user_integration_credentials" (tenant_id, user_id, service, field_key);
CREATE INDEX IF NOT EXISTS "idx_user_integration_credentials_user" ON "user_integration_credentials" (tenant_id, user_id, service);
CREATE UNIQUE INDEX IF NOT EXISTS "leads_outreach_pkey" ON "leads_outreach" (email);
CREATE UNIQUE INDEX IF NOT EXISTS "template_performance_pkey" ON "template_performance" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "template_performance_template_identity_vertical_relationshi_key" ON "template_performance" (template_identity, vertical, relationship_stage, brand);
CREATE INDEX IF NOT EXISTS "idx_template_perf_template" ON "template_performance" (template_identity);
CREATE INDEX IF NOT EXISTS "idx_template_perf_score" ON "template_performance" (vertical, relationship_stage, score_30d DESC);
CREATE INDEX IF NOT EXISTS "idx_template_perf_last_seen" ON "template_performance" (last_seen DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "vertical_response_patterns_pkey" ON "vertical_response_patterns" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "vertical_response_patterns_vertical_signal_type_signal_valu_key" ON "vertical_response_patterns" (vertical, signal_type, signal_value);
CREATE INDEX IF NOT EXISTS "idx_vpat_vertical" ON "vertical_response_patterns" (vertical, signal_type);
CREATE INDEX IF NOT EXISTS "idx_vpat_confidence" ON "vertical_response_patterns" (vertical, confidence DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "email_suppressions_pkey" ON "email_suppressions" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "email_suppressions_unique" ON "email_suppressions" (COALESCE(email, '\u001f__null__'), COALESCE(tenant_id, '\u001f__null__'), COALESCE(brand, '\u001f__null__'));
CREATE INDEX IF NOT EXISTS "idx_email_suppressions_email_lower" ON "email_suppressions" (lower(email));
CREATE INDEX IF NOT EXISTS "idx_email_suppressions_tenant" ON "email_suppressions" (tenant_id);
CREATE UNIQUE INDEX IF NOT EXISTS "cron_jobs_pkey" ON "cron_jobs" (id);
CREATE INDEX IF NOT EXISTS "cron_jobs_tenant_id_idx" ON "cron_jobs" (tenant_id, is_active);
CREATE INDEX IF NOT EXISTS "cron_jobs_failing_idx" ON "cron_jobs" (fail_count) WHERE (fail_count > 0);
CREATE UNIQUE INDEX IF NOT EXISTS "shop_out_runs_pkey" ON "shop_out_runs" (run_id);
CREATE INDEX IF NOT EXISTS "idx_shop_out_runs_application" ON "shop_out_runs" (application_id, initiated_at DESC);
CREATE INDEX IF NOT EXISTS "idx_shop_out_runs_tenant" ON "shop_out_runs" (tenant_id, initiated_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "bridge_activity_pkey" ON "bridge_activity" (id);
CREATE INDEX IF NOT EXISTS "bridge_activity_created_idx" ON "bridge_activity" (created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "agent_activity_pkey" ON "agent_activity" (id);
CREATE INDEX IF NOT EXISTS "agent_activity_created_idx" ON "agent_activity" (created_at DESC);
CREATE INDEX IF NOT EXISTS "agent_activity_agent_created_idx" ON "agent_activity" (agent, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "followup_drip_sends_pkey" ON "followup_drip_sends" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "followup_drip_sends_enrollment_id_step_index_key" ON "followup_drip_sends" (enrollment_id, step_index);
CREATE INDEX IF NOT EXISTS "idx_fds_enrollment" ON "followup_drip_sends" (enrollment_id, step_index);
CREATE INDEX IF NOT EXISTS "idx_fds_tenant" ON "followup_drip_sends" (tenant_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "conversation_events_pkey" ON "conversation_events" (id);
CREATE INDEX IF NOT EXISTS "idx_conv_events_thread" ON "conversation_events" (thread_id, created_at DESC);
CREATE INDEX IF NOT EXISTS "idx_conv_events_tenant" ON "conversation_events" (tenant_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "channel_accounts_pkey" ON "channel_accounts" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "ux_channel_accounts_email" ON "channel_accounts" (tenant_id, provider, lower(from_email)) WHERE (from_email IS NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS "ux_channel_accounts_phone" ON "channel_accounts" (tenant_id, provider, from_phone) WHERE (from_phone IS NOT NULL);
CREATE INDEX IF NOT EXISTS "idx_channel_accounts_owner" ON "channel_accounts" (tenant_id, owner_user_id);
CREATE INDEX IF NOT EXISTS "idx_campaign_runs_channel" ON "campaign_runs" (tenant_id, channel, launched_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "campaign_runs_pkey" ON "campaign_runs" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "campaign_runs_tenant_id_tt_campaign_id_key" ON "campaign_runs" (tenant_id, tt_campaign_id);
CREATE UNIQUE INDEX IF NOT EXISTS "scheduled_sends_pkey" ON "scheduled_sends" (id);
CREATE INDEX IF NOT EXISTS "idx_scheduled_sends_due" ON "scheduled_sends" (status, scheduled_for);
CREATE INDEX IF NOT EXISTS "idx_scheduled_sends_tenant" ON "scheduled_sends" (tenant_id, status);
CREATE UNIQUE INDEX IF NOT EXISTS "campaign_recipients_pkey" ON "campaign_recipients" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "campaign_recipients_tt_campaign_id_send_to_last10_key" ON "campaign_recipients" (tt_campaign_id, send_to_last10);
CREATE INDEX IF NOT EXISTS "idx_camp_recip_from" ON "campaign_recipients" (send_from);
CREATE INDEX IF NOT EXISTS "idx_camp_recip_last10" ON "campaign_recipients" (send_to_last10);
CREATE INDEX IF NOT EXISTS "idx_camp_recip_camp" ON "campaign_recipients" (tt_campaign_id);
CREATE UNIQUE INDEX IF NOT EXISTS "application_signing_requests_pkey" ON "application_signing_requests" (id);
CREATE INDEX IF NOT EXISTS "asr_tenant_lead_idx" ON "application_signing_requests" (tenant_id, lead_id);
CREATE UNIQUE INDEX IF NOT EXISTS "asr_token_idx" ON "application_signing_requests" (token_sha256);
CREATE UNIQUE INDEX IF NOT EXISTS "application_signing_events_pkey" ON "application_signing_events" (id);
CREATE INDEX IF NOT EXISTS "ase_request_idx" ON "application_signing_events" (request_id, at);
CREATE UNIQUE INDEX IF NOT EXISTS "signing_otp_codes_pkey" ON "signing_otp_codes" (id);
CREATE INDEX IF NOT EXISTS "otp_request_idx" ON "signing_otp_codes" (request_id, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS "drip_runs_pkey" ON "drip_runs" (id);
CREATE INDEX IF NOT EXISTS "idx_drip_runs_due" ON "drip_runs" (status, scheduled_for);
CREATE INDEX IF NOT EXISTS "idx_drip_runs_lead" ON "drip_runs" (tenant_id, lead_id, sequence_id);
CREATE UNIQUE INDEX IF NOT EXISTS "ux_drip_runs_active" ON "drip_runs" (tenant_id, lead_id, sequence_id) WHERE (status IN ('scheduled', 'sending'));
CREATE INDEX IF NOT EXISTS "idx_drip_runs_sending_claimed" ON "drip_runs" (claimed_at) WHERE (status = 'sending');
CREATE INDEX IF NOT EXISTS "idx_drip_runs_provider_message_id" ON "drip_runs" (provider_message_id) WHERE (provider_message_id IS NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS "document_extraction_jobs_pkey" ON "document_extraction_jobs" (id);
CREATE INDEX IF NOT EXISTS "dej_status_idx" ON "document_extraction_jobs" (status, created_at) WHERE (status IN ('queued', 'processing'));
CREATE INDEX IF NOT EXISTS "dej_tenant_lead_idx" ON "document_extraction_jobs" (tenant_id, lead_id);
CREATE UNIQUE INDEX IF NOT EXISTS "agent_nurture_settings_pkey" ON "agent_nurture_settings" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "agent_nurture_settings_tenant_id_user_id_key" ON "agent_nurture_settings" (tenant_id, user_id);
CREATE UNIQUE INDEX IF NOT EXISTS "list_intelligence_pkey" ON "list_intelligence" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "list_intelligence_tenant_id_list_id_key" ON "list_intelligence" (tenant_id, list_id);
CREATE UNIQUE INDEX IF NOT EXISTS "scrub_candidates_pkey" ON "scrub_candidates" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "scrub_candidates_tenant_rowhash_uniq" ON "scrub_candidates" (tenant_id, row_hash);
CREATE INDEX IF NOT EXISTS "scrub_candidates_tenant_status_idx" ON "scrub_candidates" (tenant_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS "scrub_candidates_created_lead_idx" ON "scrub_candidates" (tenant_id, created_lead_id) WHERE (created_lead_id IS NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS "campaign_number_health_pkey" ON "campaign_number_health" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "campaign_number_health_tenant_id_send_from_window_key_key" ON "campaign_number_health" (tenant_id, send_from, window_key);
CREATE UNIQUE INDEX IF NOT EXISTS "agent_nurture_voice_history_pkey" ON "agent_nurture_voice_history" (id);
CREATE INDEX IF NOT EXISTS "idx_anvh_lookup" ON "agent_nurture_voice_history" (tenant_id, act_as_email, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "merchant_background_checks_pkey" ON "merchant_background_checks" (id);
CREATE INDEX IF NOT EXISTS "idx_mbc_queue" ON "merchant_background_checks" (status, created_at);
CREATE INDEX IF NOT EXISTS "idx_mbc_lead" ON "merchant_background_checks" (lead_id, created_at DESC);
CREATE INDEX IF NOT EXISTS "idx_mbc_tenant" ON "merchant_background_checks" (tenant_id, checked_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "lead_interactions_pkey" ON "lead_interactions" (id);
CREATE INDEX IF NOT EXISTS "idx_lead_interactions_lead" ON "lead_interactions" (lead_id);
CREATE INDEX IF NOT EXISTS "idx_lead_interactions_type" ON "lead_interactions" (type);
CREATE INDEX IF NOT EXISTS "idx_lead_interactions_entity_channel" ON "lead_interactions" (lead_id, channel, created_at DESC);
CREATE INDEX IF NOT EXISTS "idx_lead_interactions_cooldown" ON "lead_interactions" (lead_id, cooldown_until) WHERE (cooldown_until IS NOT NULL);
CREATE INDEX IF NOT EXISTS "idx_lead_interactions_channel_created" ON "lead_interactions" (channel, created_at DESC);
CREATE INDEX IF NOT EXISTS "idx_lead_interactions_agent_source" ON "lead_interactions" (agent_source, created_at DESC) WHERE (agent_source IS NOT NULL);
CREATE INDEX IF NOT EXISTS "idx_lead_interactions_tenant" ON "lead_interactions" (tenant_id);
CREATE INDEX IF NOT EXISTS "idx_lead_interactions_outbound_queued" ON "lead_interactions" (tenant_id, channel, direction, created_at DESC) WHERE (direction = 'outbound');
CREATE INDEX IF NOT EXISTS "idx_lead_interactions_notes" ON "lead_interactions" (tenant_id, lead_id, created_at DESC) WHERE (channel = 'note');
CREATE INDEX IF NOT EXISTS "lead_interactions_actor_user_id_idx" ON "lead_interactions" (tenant_id, actor_user_id, created_at DESC) WHERE (actor_user_id IS NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS "idx_lead_interactions_kixie_call_id_unique" ON "lead_interactions" (kixie_call_id) WHERE (kixie_call_id IS NOT NULL);
CREATE INDEX IF NOT EXISTS "idx_lead_interactions_phone_by_tenant" ON "lead_interactions" (tenant_id, channel, created_at DESC) WHERE (channel = 'phone');
CREATE INDEX IF NOT EXISTS "idx_lead_interactions_from_phone" ON "lead_interactions" (from_phone);
CREATE UNIQUE INDEX IF NOT EXISTS "ux_lead_interactions_provider_msg" ON "lead_interactions" (provider, provider_message_id);
CREATE UNIQUE INDEX IF NOT EXISTS "ux_lead_interactions_kixie_call_id" ON "lead_interactions" (kixie_call_id);
CREATE UNIQUE INDEX IF NOT EXISTS "esign_envelopes_pkey" ON "esign_envelopes" (id);
CREATE INDEX IF NOT EXISTS "esign_env_tenant_idx" ON "esign_envelopes" (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS "esign_env_status_idx" ON "esign_envelopes" (tenant_id, status);
CREATE UNIQUE INDEX IF NOT EXISTS "esign_signers_pkey" ON "esign_signers" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "esign_signer_token_idx" ON "esign_signers" (token_sha256);
CREATE INDEX IF NOT EXISTS "esign_signer_env_idx" ON "esign_signers" (envelope_id, sign_order);
CREATE UNIQUE INDEX IF NOT EXISTS "esign_fields_pkey" ON "esign_fields" (id);
CREATE INDEX IF NOT EXISTS "esign_field_env_idx" ON "esign_fields" (envelope_id, signer_id);
CREATE UNIQUE INDEX IF NOT EXISTS "esign_events_pkey" ON "esign_events" (id);
CREATE INDEX IF NOT EXISTS "esign_event_env_idx" ON "esign_events" (envelope_id, at);
CREATE UNIQUE INDEX IF NOT EXISTS "call_appointments_pkey" ON "call_appointments" (id);
CREATE INDEX IF NOT EXISTS "idx_call_appt_when" ON "call_appointments" (tenant_id, scheduled_for);
CREATE INDEX IF NOT EXISTS "idx_call_appt_assignee" ON "call_appointments" (tenant_id, assigned_to, status);
CREATE INDEX IF NOT EXISTS "idx_call_appt_lead" ON "call_appointments" (tenant_id, lead_id);
CREATE UNIQUE INDEX IF NOT EXISTS "email_click_events_pkey" ON "email_click_events" (id);
CREATE INDEX IF NOT EXISTS "idx_email_click_events_tenant_lead" ON "email_click_events" (tenant_id, lead_id, clicked_at DESC);
CREATE INDEX IF NOT EXISTS "idx_email_click_events_message" ON "email_click_events" (outbound_message_id);
CREATE UNIQUE INDEX IF NOT EXISTS "idx_email_click_events_dedup" ON "email_click_events" (outbound_message_id, ip_hash);
CREATE UNIQUE INDEX IF NOT EXISTS "marketing_request_pkey" ON "marketing_request" (id);
CREATE INDEX IF NOT EXISTS "idx_marketing_request_open" ON "marketing_request" (tenant_id, status, priority DESC, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS "agent_voice_profile_history_pkey" ON "agent_voice_profile_history" (id);
CREATE INDEX IF NOT EXISTS "idx_avp_history_rep_chan" ON "agent_voice_profile_history" (tenant_id, rep_user_id, channel, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "agent_rep_identity_pkey" ON "agent_rep_identity" (tenant_id, rep_user_id);
CREATE UNIQUE INDEX IF NOT EXISTS "drip_sequence_versions_pkey" ON "drip_sequence_versions" (id);
CREATE INDEX IF NOT EXISTS "idx_drip_seq_versions_seq" ON "drip_sequence_versions" (tenant_id, sequence_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "deal_paper_snapshot_pkey" ON "deal_paper_snapshot" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "deal_paper_snapshot_tenant_id_shop_run_id_key" ON "deal_paper_snapshot" (tenant_id, shop_run_id);
CREATE INDEX IF NOT EXISTS "deal_paper_snapshot_app_idx" ON "deal_paper_snapshot" (tenant_id, application_id, captured_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "renewal_outreach_events_pkey" ON "renewal_outreach_events" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "renewal_outreach_events_funded_deal_id_event_kind_key" ON "renewal_outreach_events" (funded_deal_id, event_kind);
CREATE INDEX IF NOT EXISTS "idx_renewal_outreach_tenant_status" ON "renewal_outreach_events" (tenant_id, status, threshold_date);
CREATE UNIQUE INDEX IF NOT EXISTS "clair_reports_pkey" ON "clair_reports" (id);
CREATE INDEX IF NOT EXISTS "clair_reports_lead_idx" ON "clair_reports" (lead_id, created_at DESC);
CREATE INDEX IF NOT EXISTS "clair_reports_tenant_idx" ON "clair_reports" (tenant_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "gmail_templates_pkey" ON "gmail_templates" (id);
CREATE INDEX IF NOT EXISTS "idx_gmail_templates_tenant" ON "gmail_templates" (tenant_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS "idx_gmail_templates_stage" ON "gmail_templates" (tenant_id, stage);
CREATE UNIQUE INDEX IF NOT EXISTS "phone_lookup_jobs_pkey" ON "phone_lookup_jobs" (id);
CREATE INDEX IF NOT EXISTS "phone_lookup_jobs_pending_idx" ON "phone_lookup_jobs" (status, created_at) WHERE (status = 'pending');
CREATE INDEX IF NOT EXISTS "phone_lookup_jobs_lead_idx" ON "phone_lookup_jobs" (lead_id, created_at DESC);
CREATE INDEX IF NOT EXISTS "phone_lookup_jobs_tenant_idx" ON "phone_lookup_jobs" (tenant_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "phone_lookup_jobs_one_in_flight_idx" ON "phone_lookup_jobs" (lead_id) WHERE (status IN ('pending', 'running'));
CREATE UNIQUE INDEX IF NOT EXISTS "drip_email_events_pkey" ON "drip_email_events" (id);
CREATE INDEX IF NOT EXISTS "idx_drip_email_events_tenant_sent" ON "drip_email_events" (tenant_id, sent_at DESC);
CREATE INDEX IF NOT EXISTS "idx_drip_email_events_merchant" ON "drip_email_events" (tenant_id, merchant_id, sent_at DESC);
CREATE INDEX IF NOT EXISTS "idx_drip_email_events_sequence" ON "drip_email_events" (tenant_id, sequence_id, sent_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "ux_drip_email_events_run" ON "drip_email_events" (tenant_id, drip_run_id);
CREATE UNIQUE INDEX IF NOT EXISTS "sunbiz_agent_accounts_pkey" ON "sunbiz_agent_accounts" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "sunbiz_agent_accounts_tenant_id_user_id_provider_key" ON "sunbiz_agent_accounts" (tenant_id, user_id, provider);
CREATE UNIQUE INDEX IF NOT EXISTS "sunbiz_agent_accounts_tenant_id_provider_from_number_key" ON "sunbiz_agent_accounts" (tenant_id, provider, from_number);
CREATE UNIQUE INDEX IF NOT EXISTS "sunbiz_conversation_state_pkey" ON "sunbiz_conversation_state" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "sunbiz_conversation_state_tenant_id_provider_provider_conve_key" ON "sunbiz_conversation_state" (tenant_id, provider, provider_conversation_id);
CREATE INDEX IF NOT EXISTS "idx_sunbiz_state_agent" ON "sunbiz_conversation_state" (tenant_id, agent_account_id, updated_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "sunbiz_reply_drafts_pkey" ON "sunbiz_reply_drafts" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "sunbiz_reply_drafts_tenant_id_source_interaction_id_key" ON "sunbiz_reply_drafts" (tenant_id, source_interaction_id);
CREATE INDEX IF NOT EXISTS "idx_sunbiz_drafts_queue" ON "sunbiz_reply_drafts" (tenant_id, status, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS "sunbiz_processing_leases_pkey" ON "sunbiz_processing_leases" (tenant_id, partition_key);
CREATE INDEX IF NOT EXISTS "idx_sunbiz_leases_expiry" ON "sunbiz_processing_leases" (expires_at);
CREATE UNIQUE INDEX IF NOT EXISTS "sunbiz_provider_rate_state_pkey" ON "sunbiz_provider_rate_state" (bucket);
CREATE UNIQUE INDEX IF NOT EXISTS "sunbiz_phone_suppressions_pkey" ON "sunbiz_phone_suppressions" (tenant_id, phone_last10);
CREATE UNIQUE INDEX IF NOT EXISTS "texttorrent_inbound_work_pkey" ON "texttorrent_inbound_work" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "texttorrent_inbound_work_tenant_id_provider_message_id_key" ON "texttorrent_inbound_work" (tenant_id, provider_message_id);
CREATE INDEX IF NOT EXISTS "idx_tt_inbound_due" ON "texttorrent_inbound_work" (status, priority, next_attempt_at);
CREATE INDEX IF NOT EXISTS "idx_tt_inbound_account_due" ON "texttorrent_inbound_work" (account_id, status, next_attempt_at, priority, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS "texttorrent_dead_letters_pkey" ON "texttorrent_dead_letters" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "texttorrent_dead_letters_inbound_work_id_key" ON "texttorrent_dead_letters" (inbound_work_id);
CREATE UNIQUE INDEX IF NOT EXISTS "lender_reply_outcomes_pkey" ON "lender_reply_outcomes" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "lender_reply_outcomes_tenant_id_application_id_lender_id_re_key" ON "lender_reply_outcomes" (tenant_id, application_id, lender_id, reply_at);
CREATE INDEX IF NOT EXISTS "lender_reply_outcomes_lender_idx" ON "lender_reply_outcomes" (tenant_id, lender_id, reply_at DESC);
CREATE INDEX IF NOT EXISTS "lender_reply_outcomes_app_idx" ON "lender_reply_outcomes" (tenant_id, application_id);
CREATE UNIQUE INDEX IF NOT EXISTS "funded_deals_pkey" ON "funded_deals" (id);
CREATE INDEX IF NOT EXISTS "idx_funded_deals_tenant_renewal" ON "funded_deals" (tenant_id, next_renewal_date);
CREATE INDEX IF NOT EXISTS "idx_funded_deals_tenant_merchant" ON "funded_deals" (tenant_id, lower(merchant_name), funded_at);
CREATE UNIQUE INDEX IF NOT EXISTS "uq_funded_deals_dedupe" ON "funded_deals" (tenant_id, dedupe_key) WHERE (dedupe_key IS NOT NULL);
CREATE INDEX IF NOT EXISTS "idx_funded_deals_tenant_lender" ON "funded_deals" (tenant_id, lender_id);
CREATE UNIQUE INDEX IF NOT EXISTS "contracts_pkey" ON "contracts" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "contracts_sign_token_key" ON "contracts" (sign_token);
CREATE INDEX IF NOT EXISTS "contracts_tenant_idx" ON "contracts" (tenant_id);
CREATE INDEX IF NOT EXISTS "contracts_lead_idx" ON "contracts" (lead_id);
CREATE INDEX IF NOT EXISTS "contracts_status_idx" ON "contracts" (status);
CREATE UNIQUE INDEX IF NOT EXISTS "contracts_sign_token_idx" ON "contracts" (sign_token);
CREATE UNIQUE INDEX IF NOT EXISTS "client_signatures_pkey" ON "client_signatures" (id);
CREATE INDEX IF NOT EXISTS "client_signatures_contract_idx" ON "client_signatures" (contract_id);
CREATE UNIQUE INDEX IF NOT EXISTS "ops_alert_state_pkey" ON "ops_alert_state" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "ops_alert_state_tenant_id_alert_key_key" ON "ops_alert_state" (tenant_id, alert_key);
CREATE INDEX IF NOT EXISTS "idx_ops_alert_state_tenant_key" ON "ops_alert_state" (tenant_id, alert_key);
CREATE UNIQUE INDEX IF NOT EXISTS "marketing_review_pkey" ON "marketing_review" (id);
CREATE INDEX IF NOT EXISTS "idx_marketing_review_open" ON "marketing_review" (tenant_id, acted_on_at, created_at) WHERE (acted_on_at IS NULL);
CREATE INDEX IF NOT EXISTS "idx_marketing_review_asset" ON "marketing_review" (asset_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "marketing_asset_media_pkey" ON "marketing_asset_media" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "marketing_asset_media_tenant_id_storage_bucket_storage_path_key" ON "marketing_asset_media" (tenant_id, storage_bucket, storage_path);
CREATE INDEX IF NOT EXISTS "idx_marketing_media_asset" ON "marketing_asset_media" (asset_id, kind);
CREATE UNIQUE INDEX IF NOT EXISTS "marketing_asset_pkey" ON "marketing_asset" (id);
CREATE UNIQUE INDEX IF NOT EXISTS "marketing_asset_tenant_id_key" ON "marketing_asset" (tenant_id, id);
CREATE INDEX IF NOT EXISTS "idx_marketing_asset_tenant_track" ON "marketing_asset" (tenant_id, track, status, created_at DESC);
CREATE INDEX IF NOT EXISTS "idx_marketing_asset_tenant_created" ON "marketing_asset" (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS "idx_marketing_asset_scheduled" ON "marketing_asset" (tenant_id, scheduled_for) WHERE (scheduled_for IS NOT NULL);
CREATE INDEX IF NOT EXISTS "idx_marketing_asset_tenant_brand_created" ON "marketing_asset" (tenant_id, brand_slug, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "marketing_asset_tenant_source_unique_idx" ON "marketing_asset" (tenant_id, source) WHERE (source IS NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS "marketing_event_pkey" ON "marketing_event" (id);
CREATE INDEX IF NOT EXISTS "idx_marketing_event_at" ON "marketing_event" (tenant_id, at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "marketing_corpus_pkey" ON "marketing_corpus" (id);
CREATE INDEX IF NOT EXISTS "idx_marketing_corpus_due" ON "marketing_corpus" (state, created_at) WHERE (state IN ('queued', 'extracting'));
CREATE INDEX IF NOT EXISTS "idx_marketing_corpus_tenant" ON "marketing_corpus" (tenant_id, label, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS "marketing_corpus_one_in_flight_url_idx" ON "marketing_corpus" (tenant_id, source_url) WHERE ((source_url IS NOT NULL) AND (state IN ('queued', 'extracting')));
CREATE UNIQUE INDEX IF NOT EXISTS "marketing_corpus_one_in_flight_path_idx" ON "marketing_corpus" (tenant_id, storage_path) WHERE ((storage_path IS NOT NULL) AND (state IN ('queued', 'extracting')));
CREATE UNIQUE INDEX IF NOT EXISTS "marketing_metric_daily_pkey" ON "marketing_metric_daily" (tenant_id, asset_id, date, source);
CREATE INDEX IF NOT EXISTS "idx_marketing_metric_date" ON "marketing_metric_daily" (tenant_id, date DESC);

-- views
CREATE VIEW IF NOT EXISTS "agent_model_resolved" AS
WITH per_user AS (
         SELECT agent_model_config.tenant_id,
            agent_model_config.user_id,
            agent_model_config.agent_key,
            agent_model_config.provider,
            agent_model_config.model,
            agent_model_config.encrypted_api_key,
            agent_model_config.system_prompt_override,
            agent_model_config.enabled,
            'user' AS scope
           FROM agent_model_config
          WHERE agent_model_config.user_id IS NOT NULL
        ), per_tenant AS (
         SELECT agent_model_config.tenant_id,
            NULL AS user_id,
            agent_model_config.agent_key,
            agent_model_config.provider,
            agent_model_config.model,
            agent_model_config.encrypted_api_key,
            agent_model_config.system_prompt_override,
            agent_model_config.enabled,
            'tenant' AS scope
           FROM agent_model_config
          WHERE agent_model_config.user_id IS NULL
        )
 SELECT per_user.tenant_id,
    per_user.user_id,
    per_user.agent_key,
    per_user.provider,
    per_user.model,
    per_user.encrypted_api_key,
    per_user.system_prompt_override,
    per_user.enabled,
    per_user.scope
   FROM per_user
UNION ALL
 SELECT per_tenant.tenant_id,
    per_tenant.user_id,
    per_tenant.agent_key,
    per_tenant.provider,
    per_tenant.model,
    per_tenant.encrypted_api_key,
    per_tenant.system_prompt_override,
    per_tenant.enabled,
    per_tenant.scope
   FROM per_tenant;

CREATE VIEW IF NOT EXISTS "lead_interactions_unreplied_outbound" AS
SELECT id AS outbound_id,
    lead_id,
    channel,
    created_at AS sent_at,
    subject,
    agent_source,
    metadata,
    ((julianday('now') - julianday(created_at)) * 86400.0) / 3600.0 AS hours_since_send
   FROM lead_interactions o
  WHERE (type IN ('email_sent', 'dm_sent', 'linkedin_sent')) AND NOT (EXISTS ( SELECT 1
           FROM lead_interactions r
          WHERE r.lead_id = o.lead_id AND r.channel = o.channel AND r.created_at > o.created_at AND (r.type LIKE '%_received' OR r.type LIKE '%_reply')));

-- hand-ported triggers (invariants; see PORTED_TRIGGERS)
CREATE TRIGGER IF NOT EXISTS "client_signatures_no_mutate_update" BEFORE UPDATE ON "client_signatures" FOR EACH ROW BEGIN SELECT RAISE(ABORT, 'client_signatures is append-only (attempted UPDATE). Void the contract and reissue instead.'); END;
CREATE TRIGGER IF NOT EXISTS "client_signatures_no_mutate_delete" BEFORE DELETE ON "client_signatures" FOR EACH ROW BEGIN SELECT RAISE(ABORT, 'client_signatures is append-only (attempted DELETE). Void the contract and reissue instead.'); END;
CREATE TRIGGER IF NOT EXISTS "trg_shop_out_runs_results_append_only" BEFORE UPDATE ON "shop_out_runs" FOR EACH ROW WHEN OLD.status IN ('completed','failed') AND OLD.results IS NOT NEW.results BEGIN SELECT RAISE(ABORT, 'shop_out_runs.results is append-only after terminal status'); END;
