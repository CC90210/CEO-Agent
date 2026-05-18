/**
 * Operator credential helpers — platform-default keys for the home tenant.
 *
 * The home tenant (OASIS — where CC operates from) can fall back to
 * platform-supplied API keys when no per-agent encrypted key is set in
 * agent_model_config. Client tenants always BYO key; the fallback is gated
 * by email-match against OPERATOR_EMAIL / ADMIN_EMAILS.
 *
 * Env vars (set on Vercel for the home tenant only — never client deploys):
 *   OPERATOR_EMAIL                              — CC's primary email
 *   ADMIN_EMAILS                                — comma-separated additional admins
 *   PLATFORM_DEFAULT_OPENROUTER_API_KEY         — preferred (covers all models)
 *   PLATFORM_DEFAULT_ANTHROPIC_API_KEY
 *   PLATFORM_DEFAULT_OPENAI_API_KEY
 *   PLATFORM_DEFAULT_GOOGLE_API_KEY
 *
 * Extracted from app/api/chat/route.ts after the manifest editor
 * (api/manifest/chat) needed the identical functions — keep this file
 * the single source of truth for "is this user the platform operator,
 * and what platform key should they fall back to."
 */

import type { Provider } from "./providers";

// Hardcoded fallback matches the same default lib/queries.ts uses — so if
// OPERATOR_EMAIL isn't set on Vercel, CC is still recognized as the empire
// operator. Without this, the /t/<slug> preview gate (2026-05-17 SunBiz
// hijack fix) would lock CC out of his own preview.
const DEFAULT_OPERATOR_EMAIL = "conaugh@oasisai.work";

export function isOperatorEmail(email: string | null | undefined): boolean {
  const e = (email || "").trim().toLowerCase();
  if (!e) return false;
  const operator = (
    process.env.OPERATOR_EMAIL || DEFAULT_OPERATOR_EMAIL
  )
    .trim()
    .toLowerCase();
  if (operator && e === operator) return true;
  const admins = (process.env.ADMIN_EMAILS || "")
    .split(",")
    .map((x) => x.trim().toLowerCase())
    .filter(Boolean);
  return admins.includes(e);
}

export type OperatorFallback = { provider: Provider; model: string; apiKey: string };

export function operatorPlatformFallback(): OperatorFallback | null {
  const or = process.env.PLATFORM_DEFAULT_OPENROUTER_API_KEY;
  if (or) return { provider: "openrouter", model: "anthropic/claude-sonnet-4", apiKey: or };
  const ant = process.env.PLATFORM_DEFAULT_ANTHROPIC_API_KEY;
  if (ant) return { provider: "anthropic", model: "claude-sonnet-4-6", apiKey: ant };
  const oai = process.env.PLATFORM_DEFAULT_OPENAI_API_KEY;
  if (oai) return { provider: "openai", model: "gpt-5.4", apiKey: oai };
  const goo = process.env.PLATFORM_DEFAULT_GOOGLE_API_KEY;
  if (goo) return { provider: "google", model: "gemini-2.5-pro", apiKey: goo };
  return null;
}
