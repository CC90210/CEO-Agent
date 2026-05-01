/**
 * Canonical list of integrations the OASIS Command Center cares about.
 *
 * Sourced from the actual codebase: scripts/*_tool.py, .claude/mcp.json,
 * .vscode/mcp.json, brain/CAPABILITIES.md. Only includes integrations where
 * real code in this repo touches them. Don't fabricate.
 *
 * The Integrations page reads this list, fetches the latest ping from
 * integrations_health, and shows a green/amber/red dot per service.
 *
 * If you add a new integration, add a row here AND make sure something
 * pings it (script via integration_health.ping or direct RPC).
 */

export type IntegrationCategory = "core" | "comms" | "finance" | "content" | "social" | "data" | "ai" | "infra";

export type IntegrationDef = {
  service: string;            // matches integrations_health.service value
  label: string;
  category: IntegrationCategory;
  description: string;
};

export const KNOWN_INTEGRATIONS: IntegrationDef[] = [
  // ── Core infra ─────────────────────────────────────────────────
  { service: "supabase",        label: "Supabase",         category: "core",    description: "Bravo Postgres + auth + RLS" },
  { service: "vercel",          label: "Vercel",           category: "core",    description: "Dashboard + n8n bridge hosting" },
  { service: "cloudflare",      label: "Cloudflare",       category: "core",    description: "DNS + edge caching for oasisai.work" },
  { service: "hostinger",       label: "Hostinger",        category: "core",    description: "n8n workflow host (24/7)" },

  // ── Comms ──────────────────────────────────────────────────────
  { service: "gmail",           label: "Gmail SMTP",       category: "comms",   description: "Outbound + inbox polling" },
  { service: "telegram",        label: "Telegram Bridge",  category: "comms",   description: "Mobile control + agent notifications" },
  { service: "skool",           label: "Skool",            category: "comms",   description: "Bennett community engine + post replies" },

  // ── Finance ────────────────────────────────────────────────────
  { service: "stripe",          label: "Stripe",           category: "finance", description: "OASIS + PropFlow + Nostalgic accounts" },

  // ── Content / video ────────────────────────────────────────────
  { service: "late",            label: "Late (Zernio)",    category: "content", description: "Multi-platform social scheduler" },
  { service: "remotion",        label: "Remotion",         category: "content", description: "Programmatic video pipeline" },
  { service: "ffmpeg",          label: "FFmpeg",           category: "content", description: "Video edit pipeline + captions" },
  { service: "elevenlabs",      label: "ElevenLabs",       category: "content", description: "Voiceover generation" },
  { service: "whisper",         label: "Whisper",          category: "content", description: "Audio → caption transcription" },

  // ── Social platforms (via Late) ────────────────────────────────
  { service: "linkedin",        label: "LinkedIn",         category: "social",  description: "Personal brand publishing via Late" },
  { service: "instagram",       label: "Instagram",        category: "social",  description: "Reels + posts via Late" },
  { service: "tiktok",          label: "TikTok",           category: "social",  description: "Vertical video via Late" },
  { service: "youtube",         label: "YouTube",          category: "social",  description: "Long-form + shorts via Late" },
  { service: "twitter",         label: "X / Twitter",      category: "social",  description: "Threads + posts via Late" },
  { service: "reddit",          label: "Reddit",           category: "social",  description: "Cross-posting via Late" },

  // ── Data / automation ──────────────────────────────────────────
  { service: "n8n_inbound",     label: "n8n Inbound",      category: "data",    description: "OASIS Inbound Qualifier — classified email pipeline" },
  { service: "firecrawl",       label: "Firecrawl",        category: "data",    description: "Web scrape + structured extraction" },
  { service: "playwright",      label: "Playwright",       category: "data",    description: "Browser automation for forms + flows" },
  { service: "browser_harness", label: "Browser Harness",  category: "data",    description: "Logged-in Chrome via CDP (port 9222)" },
  { service: "knowledge_graph", label: "Knowledge Graph",  category: "data",    description: "MCP — 2117 nodes / 3725 edges Obsidian vault" },
  { service: "mem0",            label: "mem0",             category: "data",    description: "Semantic memory store (Qdrant + Haiku)" },

  // ── AI providers ───────────────────────────────────────────────
  { service: "anthropic",       label: "Anthropic Claude", category: "ai",      description: "Reasoning + drafting (Opus + Sonnet + Haiku)" },
  { service: "openai_codex",    label: "Codex (OpenAI)",   category: "ai",      description: "Backend / debug delegation" },

  // ── Google Workspace ───────────────────────────────────────────
  { service: "google_drive",    label: "Google Drive",     category: "infra",   description: "Docs + assets" },
  { service: "google_calendar", label: "Google Calendar",  category: "infra",   description: "Booking link + meeting prep" },
  { service: "google_docs",     label: "Google Docs",      category: "infra",   description: "Coaching prep + proposals" },

  // ── Auxiliary ──────────────────────────────────────────────────
  { service: "context7",        label: "Context7",         category: "ai",      description: "MCP — current library docs (Claude API + SDKs)" },
  { service: "supabase_mcp",    label: "Supabase MCP",     category: "data",    description: "Direct SQL + migrations from Claude Code" },
];

export const INTEGRATION_CATEGORIES: { key: IntegrationCategory; label: string }[] = [
  { key: "core",    label: "Core" },
  { key: "comms",   label: "Comms" },
  { key: "finance", label: "Finance" },
  { key: "content", label: "Content" },
  { key: "social",  label: "Social" },
  { key: "data",    label: "Data + Automation" },
  { key: "ai",      label: "AI" },
  { key: "infra",   label: "Infra" },
];

export function categorize(integration: { service: string }): IntegrationDef | null {
  return KNOWN_INTEGRATIONS.find((i) => i.service === integration.service) || null;
}
