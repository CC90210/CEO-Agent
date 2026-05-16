/**
 * AI smart next-action — Claude reads a lead's full data + recent
 * interactions and returns the single highest-value next move.
 *
 * Phase 5b of the OASIS HQ redesign. Operator-triggered today via
 * POST /api/leads/[id]/next-action (suggestion card on /pipeline/[id]);
 * surfaced inline as "Bravo recommends: ..." so CC doesn't have to
 * decide what to do next on each lead — Claude already weighed the
 * history and picked.
 *
 * Different from scoring (lib/ai-lead-scoring.ts) in two ways:
 *   1. Output is a single short action string + a one-line rationale,
 *      not a 0-100 number. Designed for the operator to read and
 *      either execute or override in <5 seconds.
 *   2. Takes interaction history as context — recent outbound + inbound
 *      tied to the lead — so Claude knows what's already been tried
 *      and doesn't suggest "send a cold intro email" to a lead that
 *      already got three of them.
 *
 * Output shape:
 *   { action: string, rationale: string, generated_at: ISO timestamp }
 *
 * Action style guide (encoded in the system prompt):
 *   - Imperative verb first ("Send", "Call", "Book", "Pause", "Drop")
 *   - One concrete next step, not a list
 *   - Specific enough to act on without thinking ("Send the Funded
 *     Deals case study", not "Send relevant material")
 */

const ANTHROPIC_VERSION = "2023-06-01";
const NEXT_ACTION_MODEL = "claude-sonnet-4-6";
const MAX_TOKENS = 350;

export interface InteractionSnapshot {
  direction: "outbound" | "inbound";
  channel: string;
  subject?: string | null;
  body_preview?: string | null;
  at: string;
}

export interface NextActionResult {
  action: string;
  rationale: string;
  generated_at: string;
}

const SYSTEM_PROMPT = `You are Bravo, OASIS AI's lead architect. CC sells custom AI agent builds + retainers to SMBs, agencies, landlords, and operators ($2,500-$10,000 builds + $500-$3,000/month retainers).

For each lead you're shown, you return a JSON object with two fields:
  action: a single imperative next step. Start with a verb (Send, Call, Book, Pause, Drop, Reply, Wait, Score). One concrete move, not a list.
  rationale: one sentence explaining why this is the right next move, citing the specific data point.

Action style examples:
  "Send the SunBiz case study (funding CRM, 3-week build, replaced Salesforce)."
  "Book a 20-min scope call. Reply with two specific times this week."
  "Pause the drip. They asked for radio silence in their last reply."
  "Drop. They told us they hired a competitor."
  "Wait 4 days. The proposal just landed; nudging now is too eager."

Honesty over hustle. If the right move is "wait" or "drop", say so. CC's bottleneck is his time, not his outbound volume — a clean "drop" frees an hour better than a half-hearted "follow up again".

Output ONLY a single JSON object on one line — no markdown, no code fence, no extra prose. Example:
{"action":"Send the SunBiz case study and ask for a 20-min scope call.","rationale":"Score 82 + replied to last touch with a specific question about agency clients — they're ready for a credibility piece and a clear next step."}`;

export async function recommendNextAction(
  leadData: Record<string, unknown>,
  interactions: InteractionSnapshot[],
): Promise<NextActionResult> {
  const apiKey = (process.env.BRAVO_ANTHROPIC_API_KEY || process.env.ANTHROPIC_API_KEY || "").trim();
  if (!apiKey) {
    throw new Error("anthropic_key_missing");
  }

  // Same field filter as the scorer — operator-facing only, drop bookkeeping.
  const INCLUDED = ["name", "company", "email", "phone", "source", "stage",
                    "score", "value_estimate", "last_contacted_at", "notes",
                    "ai_score", "ai_reasoning", "title", "role"];
  const relevant: Record<string, unknown> = {};
  for (const k of INCLUDED) {
    if (leadData[k] !== undefined && leadData[k] !== null && leadData[k] !== "") {
      relevant[k] = leadData[k];
    }
  }

  // Cap interactions at 10 most recent — Claude doesn't need a year of
  // history to recommend the next move, and prompt cost scales with body.
  const recentInteractions = interactions.slice(0, 10).map((i) => ({
    direction: i.direction,
    channel: i.channel,
    subject: (i.subject || "").slice(0, 120),
    body_preview: (i.body_preview || "").slice(0, 200),
    at: i.at,
  }));

  const userPrompt =
    `Lead data:\n${JSON.stringify(relevant, null, 2)}\n\n` +
    `Recent interactions (newest first, up to 10):\n${
      recentInteractions.length === 0
        ? "(none yet)"
        : JSON.stringify(recentInteractions, null, 2)
    }\n\nWhat is the single highest-value next move?`;

  const res = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-api-key": apiKey,
      "anthropic-version": ANTHROPIC_VERSION,
    },
    body: JSON.stringify({
      model: NEXT_ACTION_MODEL,
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

  let cleaned = text;
  if (cleaned.startsWith("```")) {
    cleaned = cleaned.replace(/^```(?:json)?\s*/i, "").replace(/```\s*$/i, "").trim();
  }

  let parsed: { action?: unknown; rationale?: unknown };
  try {
    parsed = JSON.parse(cleaned);
  } catch {
    throw new Error(`next_action_parse_failed: ${text.slice(0, 300)}`);
  }

  const action = typeof parsed.action === "string" ? parsed.action.trim() : "";
  const rationale = typeof parsed.rationale === "string" ? parsed.rationale.trim() : "";
  if (!action || !rationale) {
    throw new Error(`next_action_parse_failed: ${text.slice(0, 300)}`);
  }

  return {
    action,
    rationale,
    generated_at: new Date().toISOString(),
  };
}
