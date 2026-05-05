/**
 * Canonical list of integrations the OASIS Command Center cares about.
 *
 * Sourced from the actual codebase: scripts/*_tool.py, .claude/mcp.json,
 * .vscode/mcp.json, brain/CAPABILITIES.md. Only includes integrations where
 * real code in this repo touches them. Don't fabricate.
 *
 * The Integrations page reads this list, fetches the latest ping from
 * integrations_health, and renders an actionable card per service:
 *   - signup_url:  where the user creates an account
 *   - api_key_url: where they retrieve / manage their key once signed up
 *   - setup_doc_url: optional walk-through link
 *   - setup_complexity: how much elbow-grease the setup needs
 *
 * If you add a new integration, populate ALL fields — the Connect CTA
 * directly links the user to their signup or API page.
 */

export type IntegrationCategory = "core" | "comms" | "finance" | "content" | "social" | "data" | "ai" | "infra";
export type SetupComplexity = "trivial" | "simple" | "moderate" | "advanced";

export type IntegrationDef = {
  service: string;            // matches integrations_health.service value
  label: string;
  category: IntegrationCategory;
  description: string;
  signup_url: string;         // where to create an account
  api_key_url: string;        // where to manage credentials post-signup
  setup_doc_url?: string;     // optional first-run walkthrough
  setup_complexity: SetupComplexity;
};

export const KNOWN_INTEGRATIONS: IntegrationDef[] = [
  // ── Core infra ─────────────────────────────────────────────────
  {
    service: "supabase", label: "Supabase", category: "core",
    description: "Postgres + auth + RLS for tenant data",
    signup_url: "https://supabase.com/dashboard/sign-up",
    api_key_url: "https://supabase.com/dashboard/account/tokens",
    setup_doc_url: "https://supabase.com/docs/guides/getting-started",
    setup_complexity: "moderate",
  },
  {
    service: "vercel", label: "Vercel", category: "core",
    description: "Dashboard hosting + n8n bridge",
    signup_url: "https://vercel.com/signup",
    api_key_url: "https://vercel.com/account/tokens",
    setup_complexity: "trivial",
  },
  {
    service: "cloudflare", label: "Cloudflare", category: "core",
    description: "DNS + edge caching",
    signup_url: "https://dash.cloudflare.com/sign-up",
    api_key_url: "https://dash.cloudflare.com/profile/api-tokens",
    setup_complexity: "moderate",
  },
  {
    service: "hostinger", label: "Hostinger", category: "core",
    description: "n8n workflow host (24/7)",
    signup_url: "https://www.hostinger.com/",
    api_key_url: "https://hpanel.hostinger.com/profile/api",
    setup_complexity: "moderate",
  },

  // ── Comms ──────────────────────────────────────────────────────
  {
    service: "gmail", label: "Gmail SMTP", category: "comms",
    description: "Outbound email + inbox polling",
    signup_url: "https://accounts.google.com/signup",
    api_key_url: "https://myaccount.google.com/apppasswords",
    setup_doc_url: "https://support.google.com/mail/answer/185833",
    setup_complexity: "simple",
  },
  {
    service: "telegram", label: "Telegram Bridge", category: "comms",
    description: "Mobile control + notifications via BotFather",
    signup_url: "https://telegram.org/",
    api_key_url: "https://t.me/BotFather",
    setup_doc_url: "https://core.telegram.org/bots/tutorial",
    setup_complexity: "simple",
  },
  {
    service: "skool", label: "Skool", category: "comms",
    description: "Community engine + post replies",
    signup_url: "https://www.skool.com/",
    api_key_url: "https://www.skool.com/settings",
    setup_complexity: "simple",
  },

  // ── Finance ────────────────────────────────────────────────────
  {
    service: "stripe", label: "Stripe", category: "finance",
    description: "Payments, invoices, subscriptions",
    signup_url: "https://dashboard.stripe.com/register",
    api_key_url: "https://dashboard.stripe.com/apikeys",
    setup_doc_url: "https://stripe.com/docs/keys",
    setup_complexity: "simple",
  },

  // ── Content / video ────────────────────────────────────────────
  {
    service: "late", label: "Late (Zernio)", category: "content",
    description: "Multi-platform social scheduler",
    signup_url: "https://zernio.com/signup",
    api_key_url: "https://zernio.com/dashboard/api",
    setup_complexity: "simple",
  },
  {
    service: "remotion", label: "Remotion", category: "content",
    description: "Programmatic video pipeline",
    signup_url: "https://www.remotion.dev/",
    api_key_url: "https://www.remotion.dev/license",
    setup_complexity: "advanced",
  },
  {
    service: "ffmpeg", label: "FFmpeg", category: "content",
    description: "Video edit pipeline + captions (no account needed)",
    signup_url: "https://ffmpeg.org/download.html",
    api_key_url: "https://ffmpeg.org/download.html",
    setup_complexity: "moderate",
  },
  {
    service: "elevenlabs", label: "ElevenLabs", category: "content",
    description: "Voiceover generation",
    signup_url: "https://elevenlabs.io/sign-up",
    api_key_url: "https://elevenlabs.io/app/settings/api-keys",
    setup_complexity: "trivial",
  },
  {
    service: "whisper", label: "Whisper", category: "content",
    description: "Audio → caption transcription (uses OpenAI key)",
    signup_url: "https://platform.openai.com/signup",
    api_key_url: "https://platform.openai.com/api-keys",
    setup_complexity: "trivial",
  },

  // ── Social platforms (via Late) ────────────────────────────────
  {
    service: "linkedin", label: "LinkedIn", category: "social",
    description: "Brand publishing via Late",
    signup_url: "https://www.linkedin.com/signup",
    api_key_url: "https://www.linkedin.com/developers/apps",
    setup_complexity: "moderate",
  },
  {
    service: "instagram", label: "Instagram", category: "social",
    description: "Reels + posts via Late",
    signup_url: "https://www.instagram.com/accounts/emailsignup/",
    api_key_url: "https://developers.facebook.com/apps/",
    setup_complexity: "moderate",
  },
  {
    service: "tiktok", label: "TikTok", category: "social",
    description: "Vertical video via Late",
    signup_url: "https://www.tiktok.com/signup",
    api_key_url: "https://developers.tiktok.com/apps",
    setup_complexity: "moderate",
  },
  {
    service: "youtube", label: "YouTube", category: "social",
    description: "Long-form + shorts via Late",
    signup_url: "https://accounts.google.com/signup",
    api_key_url: "https://console.cloud.google.com/apis/credentials",
    setup_complexity: "moderate",
  },
  {
    service: "twitter", label: "X / Twitter", category: "social",
    description: "Threads + posts via Late",
    signup_url: "https://twitter.com/signup",
    api_key_url: "https://developer.twitter.com/en/portal/dashboard",
    setup_complexity: "moderate",
  },
  {
    service: "reddit", label: "Reddit", category: "social",
    description: "Cross-posting via Late",
    signup_url: "https://www.reddit.com/register/",
    api_key_url: "https://www.reddit.com/prefs/apps",
    setup_complexity: "moderate",
  },

  // ── Data / automation ──────────────────────────────────────────
  {
    service: "n8n_inbound", label: "n8n Inbound", category: "data",
    description: "Email classifier pipeline",
    signup_url: "https://n8n.io/cloud/",
    api_key_url: "https://docs.n8n.io/api/authentication/",
    setup_complexity: "advanced",
  },
  {
    service: "firecrawl", label: "Firecrawl", category: "data",
    description: "Web scrape + structured extraction",
    signup_url: "https://www.firecrawl.dev/signup",
    api_key_url: "https://www.firecrawl.dev/app/api-keys",
    setup_complexity: "trivial",
  },
  {
    service: "playwright", label: "Playwright", category: "data",
    description: "Browser automation (no account needed)",
    signup_url: "https://playwright.dev/",
    api_key_url: "https://playwright.dev/docs/intro",
    setup_complexity: "moderate",
  },
  {
    service: "browser_harness", label: "Browser Harness", category: "data",
    description: "Logged-in Chrome via CDP",
    signup_url: "https://www.google.com/chrome/",
    api_key_url: "https://www.google.com/chrome/",
    setup_complexity: "advanced",
  },
  {
    service: "knowledge_graph", label: "Knowledge Graph", category: "data",
    description: "MCP — Obsidian vault graph queries",
    signup_url: "https://obsidian.md/",
    api_key_url: "https://obsidian.md/",
    setup_complexity: "advanced",
  },
  {
    service: "mem0", label: "mem0", category: "data",
    description: "Semantic memory store",
    signup_url: "https://mem0.ai/sign-up",
    api_key_url: "https://app.mem0.ai/dashboard/api-keys",
    setup_complexity: "simple",
  },

  // ── AI providers ───────────────────────────────────────────────
  {
    service: "openrouter", label: "OpenRouter", category: "ai",
    description: "★ One key, every model — recommended for chat",
    signup_url: "https://openrouter.ai/sign-up",
    api_key_url: "https://openrouter.ai/keys",
    setup_doc_url: "https://openrouter.ai/docs/quick-start",
    setup_complexity: "trivial",
  },
  {
    service: "anthropic", label: "Anthropic Claude", category: "ai",
    description: "Reasoning + drafting (Opus / Sonnet / Haiku)",
    signup_url: "https://console.anthropic.com/signup",
    api_key_url: "https://console.anthropic.com/settings/keys",
    setup_doc_url: "https://docs.anthropic.com/en/api/getting-started",
    setup_complexity: "trivial",
  },
  {
    service: "openai_codex", label: "OpenAI", category: "ai",
    description: "GPT-5.x + Codex models",
    signup_url: "https://platform.openai.com/signup",
    api_key_url: "https://platform.openai.com/api-keys",
    setup_doc_url: "https://platform.openai.com/docs/quickstart",
    setup_complexity: "trivial",
  },
  {
    service: "google_ai", label: "Google Gemini", category: "ai",
    description: "Gemini 2.5 Pro / Flash via AI Studio",
    signup_url: "https://aistudio.google.com/",
    api_key_url: "https://aistudio.google.com/apikey",
    setup_complexity: "trivial",
  },

  // ── Google Workspace ───────────────────────────────────────────
  {
    service: "google_drive", label: "Google Drive", category: "infra",
    description: "Docs + assets storage",
    signup_url: "https://workspace.google.com/signup",
    api_key_url: "https://console.cloud.google.com/apis/credentials",
    setup_complexity: "moderate",
  },
  {
    service: "google_calendar", label: "Google Calendar", category: "infra",
    description: "Booking + meeting prep",
    signup_url: "https://workspace.google.com/signup",
    api_key_url: "https://console.cloud.google.com/apis/credentials",
    setup_complexity: "moderate",
  },
  {
    service: "google_docs", label: "Google Docs", category: "infra",
    description: "Coaching prep + proposals",
    signup_url: "https://workspace.google.com/signup",
    api_key_url: "https://console.cloud.google.com/apis/credentials",
    setup_complexity: "moderate",
  },

  // ── Auxiliary ──────────────────────────────────────────────────
  {
    service: "context7", label: "Context7", category: "ai",
    description: "MCP — current library docs",
    signup_url: "https://context7.com/",
    api_key_url: "https://context7.com/dashboard",
    setup_complexity: "simple",
  },
  {
    service: "supabase_mcp", label: "Supabase MCP", category: "data",
    description: "Direct SQL + migrations from Claude Code",
    signup_url: "https://supabase.com/dashboard/sign-up",
    api_key_url: "https://supabase.com/dashboard/account/tokens",
    setup_complexity: "moderate",
  },
];

export const INTEGRATION_CATEGORIES: { key: IntegrationCategory; label: string }[] = [
  { key: "ai",      label: "AI Providers" },
  { key: "core",    label: "Core" },
  { key: "comms",   label: "Comms" },
  { key: "finance", label: "Finance" },
  { key: "content", label: "Content" },
  { key: "social",  label: "Social" },
  { key: "data",    label: "Data + Automation" },
  { key: "infra",   label: "Infra" },
];

export function categorize(integration: { service: string }): IntegrationDef | null {
  return KNOWN_INTEGRATIONS.find((i) => i.service === integration.service) || null;
}

export function getIntegration(service: string): IntegrationDef | null {
  return KNOWN_INTEGRATIONS.find((i) => i.service === service) || null;
}
