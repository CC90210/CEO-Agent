/**
 * Defensive parser for the AI editor's JSON envelope.
 *
 * The system prompt asks for STRICT JSON on its own, but models sometimes:
 *   - wrap the response in ```json ... ``` fences
 *   - prepend "Here's the change:" before the JSON
 *   - emit trailing prose after the closing brace
 *
 * This parser tolerates all three by extracting the first balanced JSON
 * object and parsing that. If the response can't be coerced into a valid
 * envelope we return an explicit error the route can surface to the UI
 * instead of crashing.
 */

import type { MutationArgs } from "./mutators";

export type AIEnvelope = {
  explanation: string;
  mutations: MutationArgs[];
};

export type EnvelopeResult =
  | { ok: true; envelope: AIEnvelope }
  | { ok: false; error: string; raw: string };

/** Extract the first balanced JSON object from a string. */
function extractFirstObject(s: string): string | null {
  // Strip a leading fenced block opener like ```json or ``` and trailing fence.
  const fenced = s.match(/```(?:json)?\s*([\s\S]*?)```/);
  if (fenced) return fenced[1].trim();
  const start = s.indexOf("{");
  if (start < 0) return null;
  let depth = 0;
  let inString = false;
  let escape = false;
  for (let i = start; i < s.length; i++) {
    const ch = s[i];
    if (escape) {
      escape = false;
      continue;
    }
    if (ch === "\\" && inString) {
      escape = true;
      continue;
    }
    if (ch === '"') {
      inString = !inString;
      continue;
    }
    if (inString) continue;
    if (ch === "{") depth++;
    else if (ch === "}") {
      depth--;
      if (depth === 0) {
        return s.slice(start, i + 1);
      }
    }
  }
  return null;
}

export function parseAIEnvelope(raw: string): EnvelopeResult {
  const candidate = extractFirstObject(raw);
  if (!candidate) return { ok: false, error: "no_json_object", raw };

  let parsed: unknown;
  try {
    parsed = JSON.parse(candidate);
  } catch (err) {
    return {
      ok: false,
      error: `json_parse:${err instanceof Error ? err.message : "unknown"}`,
      raw,
    };
  }

  if (!parsed || typeof parsed !== "object") {
    return { ok: false, error: "envelope_not_object", raw };
  }

  const obj = parsed as Record<string, unknown>;
  const explanation = obj.explanation;
  if (typeof explanation !== "string") {
    return { ok: false, error: "missing_explanation", raw };
  }
  if (!Array.isArray(obj.mutations)) {
    return { ok: false, error: "missing_mutations_array", raw };
  }

  // Shallow-validate each mutation has { name, args } — the mutator layer
  // does the full per-args validation when applied.
  for (let i = 0; i < obj.mutations.length; i++) {
    const m = obj.mutations[i];
    if (!m || typeof m !== "object") {
      return { ok: false, error: `mutation[${i}]_not_object`, raw };
    }
    const mm = m as Record<string, unknown>;
    if (typeof mm.name !== "string") {
      return { ok: false, error: `mutation[${i}]_missing_name`, raw };
    }
    if (!mm.args || typeof mm.args !== "object") {
      return { ok: false, error: `mutation[${i}]_missing_args`, raw };
    }
  }

  return {
    ok: true,
    envelope: {
      explanation,
      mutations: obj.mutations as MutationArgs[],
    },
  };
}
