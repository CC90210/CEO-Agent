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

const ANTHROPIC_VERSION = "2023-06-01";
const SCORING_MODEL = "claude-sonnet-4-6";
const MAX_TOKENS = 400;

export interface LeadScoreResult {
  score: number;
  reasoning: string;
  scored_at: string;
}

const SYSTEM_PROMPT = `You are an AI lead-quality scorer for OASIS AI, a custom AI agent build service. CC sells managed AI agents to small business owners, agencies, landlords, and operators — typically $2,500-$10,000 build fees + $500-$3,000/month retainers.

For each lead, you return a JSON object with two fields:
  score: integer 0-100, weighing (a) ICP fit, (b) likelihood of closing soon, (c) urgency / signal strength
  reasoning: 1-2 short sentences explaining the score. Cite the specific data point that drove it.

Scoring guide:
  90-100  Strong ICP fit + active intent + budget signal + named timeline
  70-89   ICP fit + warm signal (replied to outreach, attended a call, asked for pricing)
  50-69   Looks like ICP but cold — no engagement yet, or unclear budget
  30-49   Wrong ICP shape but possibly viable (size, industry, or budget mismatch)
  10-29   Weak fit, low engagement, no signal
  0-9     Not an OASIS customer (consumer, student, competitor, irrelevant)

Be honest. A score of 65 is more useful than an inflated 85. If the data is sparse, lean toward 40-50 and say "limited signal" in the reasoning.

Output ONLY a single JSON object on one line — no markdown, no prose, no code fence. Example:
{"score":78,"reasoning":"Mid-size agency owner who replied to cold email with a specific time-zone for a call. Strong ICP fit and active intent."}`;

export async function scoreLead(
  leadData: Record<string, unknown>,
): Promise<LeadScoreResult> {
  const apiKey = (process.env.BRAVO_ANTHROPIC_API_KEY || process.env.ANTHROPIC_API_KEY || "").trim();
  if (!apiKey) {
    throw new Error("anthropic_key_missing");
  }

  // Filter to the operator-facing fields Claude should weight — drop
  // internal bookkeeping like _legacy_id, ai_* fields (don't let prior
  // scores leak into a re-score), tenant metadata.
  const relevant: Record<string, unknown> = {};
  const INCLUDED = ["name", "company", "email", "phone", "source", "stage",
                    "score", "value_estimate", "last_contacted_at", "notes",
                    "title", "role"];
  for (const k of INCLUDED) {
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
      system: SYSTEM_PROMPT,
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
