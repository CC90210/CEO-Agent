/**
 * Per-agent operational catalog: cron jobs, backend processes, workflows
 * each agent owns. Static for v1 — every client deploy gets the same
 * catalog. Phase 2: bridge daemon ships per-tenant overrides.
 *
 * The Agents page renders one card per enabled agent so the operator sees
 * exactly what's running for them, not a generic "AI agents page."
 *
 * Display rule: an entry is shown EVEN IF its host machine is offline.
 * The catalog says what the agent CAN run; the worker-tick badges on
 * /operations say what's actually firing right now.
 */

export type CatalogEntry = {
  name: string;
  /** "cron" / "process" / "workflow" / "skill-bundle" */
  kind: "cron" | "process" | "workflow" | "skill-bundle";
  description: string;
  /** Where the entry runs. */
  location: "vercel" | "local" | "n8n" | "supabase" | "browser";
  /** Cron-style schedule when applicable. */
  schedule?: string;
};

export type AgentCatalog = {
  crons: CatalogEntry[];
  processes: CatalogEntry[];
  workflows: CatalogEntry[];
};

const EMPTY: AgentCatalog = { crons: [], processes: [], workflows: [] };

export const AGENT_CATALOG: Record<string, AgentCatalog> = {
  bravo: {
    crons: [
      {
        name: "materialize-plans",
        kind: "cron",
        description: "Builds tomorrow's daily_plan from the weekday/weekend templates.",
        location: "vercel",
        schedule: "0 3 * * *",
      },
      {
        name: "snapshot-mrr",
        kind: "cron",
        description: "Writes today's MRR row to mrr_snapshots so the trajectory chart is real.",
        location: "vercel",
        schedule: "0 4 * * *",
      },
    ],
    processes: [
      { name: "lead_engine", kind: "process", description: "CRM, scoring, pipeline, follow-ups.", location: "local" },
      { name: "outreach_engine", kind: "process", description: "Cold outreach + reply handling.", location: "local" },
      { name: "send_gateway", kind: "process", description: "Email chokepoint with 8-gate safety pipeline.", location: "local" },
      { name: "client_health", kind: "process", description: "Client-health scoring + churn alerts.", location: "local" },
      { name: "ceo_dashboard", kind: "process", description: "Daily KPI rollup + briefing.", location: "local" },
      { name: "telegram bridge", kind: "process", description: "Mobile control surface; routes back to chat.", location: "local" },
    ],
    workflows: [
      { name: "n8n inbound qualifier", kind: "workflow", description: "Classifies inbound email + posts to /api/inbound/n8n.", location: "n8n" },
      { name: "agent inbox", kind: "workflow", description: "Cross-agent async messages (Codex/Atlas/Maven post here).", location: "supabase" },
    ],
  },

  atlas: {
    crons: [
      { name: "trade_loop", kind: "cron", description: "Strategy evaluation across 12+ rule sets.", location: "local", schedule: "*/15 * * * *" },
      { name: "tax_recompute", kind: "cron", description: "Re-runs CRA-accurate tax projection on transaction changes.", location: "local", schedule: "0 5 * * *" },
      { name: "spend_gate_refresh", kind: "cron", description: "Updates cfo_pulse.json with current spend ceilings for Maven.", location: "local", schedule: "*/30 * * * *" },
    ],
    processes: [
      { name: "trade_engine", kind: "process", description: "12+ strategies, conviction scoring, stop-loss enforcement.", location: "local" },
      { name: "tax_calculator", kind: "process", description: "CRA / cross-jurisdiction tax engine.", location: "local" },
      { name: "financial_advisor", kind: "process", description: "FIRE projections, wealth tracker, budget enforcement.", location: "local" },
      { name: "wealth_tracker", kind: "process", description: "Net-worth + liquidity dashboard.", location: "local" },
    ],
    workflows: [
      { name: "broker reconcile", kind: "workflow", description: "Pulls Kraken / Wise / IBKR balances daily.", location: "local" },
      { name: "spend_gate", kind: "workflow", description: "Pre-spend checkpoint Maven hits before any ad-budget commit.", location: "supabase" },
    ],
  },

  maven: {
    crons: [
      { name: "content_pipeline", kind: "cron", description: "End-to-end content production: research → draft → edit → schedule.", location: "local", schedule: "0 9 * * *" },
      { name: "ad_optimizer", kind: "cron", description: "ROAS check + ad-set rebalance for active Meta/Google campaigns.", location: "local", schedule: "0 */4 * * *" },
      { name: "social_publisher", kind: "cron", description: "Pushes scheduled posts via Zernio.", location: "local", schedule: "*/15 * * * *" },
    ],
    processes: [
      { name: "content_pipeline", kind: "process", description: "Video pipeline (Remotion + FFmpeg + Whisper + ElevenLabs).", location: "local" },
      { name: "ad_engine", kind: "process", description: "Meta + Google paid ads orchestration.", location: "local" },
      { name: "competitive_intel", kind: "process", description: "Tracks competitor ads + content + battlecards.", location: "local" },
      { name: "lead_scraper", kind: "process", description: "Firecrawl-driven prospect research.", location: "local" },
    ],
    workflows: [
      { name: "brand_voice_check", kind: "workflow", description: "Pre-publish gate against brand-voice corpus.", location: "local" },
      { name: "captions_pipeline", kind: "workflow", description: "Whisper word-level → SRT → cinematic captions.", location: "local" },
    ],
  },

  aura: {
    crons: [
      { name: "habit_streak_compute", kind: "cron", description: "Recomputes streaks + small-wins surface.", location: "local", schedule: "0 6 * * *" },
      { name: "sleep_sync", kind: "cron", description: "Pulls sleep data, surfaces tomorrow's recovery target.", location: "local", schedule: "30 6 * * *" },
    ],
    processes: [
      { name: "home_assistant_bridge", kind: "process", description: "ESP32 + Pi 5 hub, scenes, automations.", location: "local" },
      { name: "voice_agent", kind: "process", description: "Local-first voice loop, no cloud audio leave-the-device.", location: "local" },
      { name: "habits_log", kind: "process", description: "Append-only habit + workout journal.", location: "local" },
    ],
    workflows: [
      { name: "morning_scene", kind: "workflow", description: "Wake routine: lights + climate + briefing.", location: "local" },
      { name: "wind_down", kind: "workflow", description: "Evening routine: dim, lock, prep tomorrow.", location: "local" },
    ],
  },

  hermes: {
    crons: [
      { name: "po_inbox_scan", kind: "cron", description: "Scans Emmanuel's PO inbox for new files; parses + queues.", location: "local", schedule: "*/10 * * * *" },
      { name: "chargeback_watch", kind: "cron", description: "Pre-emptive compliance check across active orders.", location: "local", schedule: "0 */2 * * *" },
    ],
    processes: [
      { name: "a2000_takeover", kind: "process", description: "pywinauto-driven order entry into the A2000 desktop ERP.", location: "local" },
      { name: "edi_processor", kind: "process", description: "EDI 856/810/940/820 round-trip handling.", location: "local" },
      { name: "label_printer", kind: "process", description: "GS1-128 + UCC-128 SSCC label generation.", location: "local" },
      { name: "audit_log", kind: "process", description: "Append-only log of every order action.", location: "local" },
    ],
    workflows: [
      { name: "po_to_pos_to_invoice", kind: "workflow", description: "End-to-end commerce ops happy path.", location: "local" },
      { name: "chargeback_dispute", kind: "workflow", description: "Auto-builds dispute packet from audit log.", location: "local" },
    ],
  },
  "life-preservation": {
    crons: [],
    processes: [
      { name: "interview_coach", kind: "process", description: "Suggests questions that surface the meaningful, not the obvious.", location: "local" },
      { name: "voice_capture", kind: "process", description: "Coaches the family on what to record, when, in what conditions.", location: "local" },
      { name: "memory_organizer", kind: "process", description: "Turns hours of audio + scattered notes into a coherent narrative.", location: "local" },
    ],
    workflows: [
      { name: "persona_session", kind: "workflow", description: "Private conversational access for surviving loved ones — family-gated.", location: "local" },
    ],
  },
};

export function catalogFor(agentKey: string): AgentCatalog {
  return AGENT_CATALOG[agentKey] || EMPTY;
}
