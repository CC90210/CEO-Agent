/**
 * AI lead scoring — Claude rates a lead 0-100 on fit + close-likelihood
 * + urgency, with a 1-2 sentence rationale.
 *
 * Phase 5a of the OASIS HQ redesign. Operator-triggered today via
 * POST /api/leads/[id]/score (Re-score button on /pipeline/[id]); a
 * future daily cron will batch-score new leads automatically.
 *
 * Why a focused scorer instead of "throw the whole context at Claude":
 *   - Deterministic shape — the route writes `ai_score` + `ai_reasoning`
 *     to a structured location on the lead row, surfaced as kanban-card
 *     fields. A free-form chat reply would force the operator to copy/
 *     paste the score back into the data.
 *   - Cheaper — one ~600-token call per lead, no streaming overhead.
 *   - Auditable — same prompt across leads, so score deltas track lead
 *     quality drift, not prompt drift.
 *
 * Inputs are the lead's data dict (whatever the operator captured —
 * name, company, email, source, notes, etc.). We pass the full thing
 * to Claude and let it reason over whatever's present.
 *
 * Output shape:
 *   { score: 0-100, reasoning: string, scored_at: ISO timestamp }
 *
 * Failure modes:
 *   - Missing BRAVO_ANTHROPIC_API_KEY → throws "anthropic_key_missing"
 *   - Anthropic non-2xx → throws the upstream status code + body slice
 *   - Claude returns malformed JSON → throws "score_parse_failed" with
 *     the raw text so the caller can fall back gracefully
 */

import {
  OASIS_LEAD_SCORING_PROMPT,
  LEAD_SCORING_INCLUDED_FIELDS,
} from "./prompts";

const ANTHROPIC_VERSION = "2023-06-01";
const SCORING_MODEL = "claude-sonnet-4-6";
const MAX_TOKENS = 400;

export interface LeadScoreResult {
  score: number;
  reasoning: string;
  scored_at: string;
}

export async function scoreLead(
  leadData: Record<string, unknown>,
): Promise<LeadScoreResult> {
  const apiKey = (process.env.BRAVO_ANTHROPIC_API_KEY || process.env.ANTHROPIC_API_KEY || "").trim();
  if (!apiKey) {
    throw new Error("anthropic_key_missing");
  }

  // Filter to the operator-facing fields Claude should weight — drop
  // internal bookkeeping like _legacy_id, ai_* fields (don't let prior
  // scores leak into a re-score), tenant metadata. The allowlist lives
  // in lib/prompts/index.ts so the Python cron path shares it.
  const relevant: Record<string, unknown> = {};
  for (const k of LEAD_SCORING_INCLUDED_FIELDS) {
    if (leadData[k] !== undefined && leadData[k] !== null && leadData[k] !== "") {
      relevant[k] = leadData[k];
    }
  }

  const userPrompt = `Score this lead:\n\n${JSON.stringify(relevant, null, 2)}`;

  const res = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-api-key": apiKey,
      "anthropic-version": ANTHROPIC_VERSION,
    },
    body: JSON.stringify({
      model: SCORING_MODEL,
      max_tokens: MAX_TOKENS,
      system: OASIS_LEAD_SCORING_PROMPT,
      messages: [{ role: "user", content: userPrompt }],
    }),
  });

  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`anthropic_${res.status}: ${detail.slice(0, 300)}`);
  }

  const body = (await res.json()) as {
    content?: Array<{ type: string; text?: string }>;
  };
  const text = (body.content || [])
    .filter((b) => b.type === "text")
    .map((b) => b.text || "")
    .join("")
    .trim();

  // Strip markdown code fences if Claude added them despite the prompt.
  let cleaned = text;
  if (cleaned.startsWith("```")) {
    cleaned = cleaned.replace(/^```(?:json)?\s*/i, "").replace(/```\s*$/i, "").trim();
  }

  let parsed: { score?: unknown; reasoning?: unknown };
  try {
    parsed = JSON.parse(cleaned);
  } catch {
    throw new Error(`score_parse_failed: ${text.slice(0, 300)}`);
  }

  const score = typeof parsed.score === "number" ? Math.round(parsed.score) : NaN;
  const reasoning = typeof parsed.reasoning === "string" ? parsed.reasoning.trim() : "";
  if (Number.isNaN(score) || score < 0 || score > 100 || !reasoning) {
    throw new Error(`score_parse_failed: ${text.slice(0, 300)}`);
  }

  return {
    score,
    reasoning,
    scored_at: new Date().toISOString(),
  };
}
