/**
 * drips/templates.ts — mustache-style variable substitution for drip
 * sequence messages.
 *
 * Phase 4 of the SunBiz CRM build (2026-05-15). Sequence definitions
 * carry SMS / email bodies like:
 *
 *   "Hi {{lead.first_name}}, your application to {{lender.name}} is
 *    in review — we'll be in touch by {{lender.eta}}."
 *
 * At fire time the runner builds a context object from the lead row +
 * the triggering event payload + (optionally) joined entities like the
 * lender. This function does the substitution.
 *
 * Design choices:
 *   - Mustache-style {{path}} only — no conditionals, no loops. Drip
 *     messages are short; complexity belongs in the sequence schema
 *     (more steps), not the template language.
 *   - Dot-pathed lookups: {{lead.first_name}} reads context.lead.first_name.
 *   - Missing values render as the operator-supplied default string
 *     (default "" — empty). Throwing on missing values would block
 *     sends over a typo; soft-fail is the right tradeoff here.
 *   - HTML / URL escaping is the CALLER's job. send_gateway handles
 *     plain-text SMS / multipart email. If a future template engine
 *     supports rich HTML, escape at that layer.
 *
 * PARITY ASSERTION — every case below MUST behave identically in
 * scripts/sequence_runner.py's render_template. The Python side has
 * the same sample cases in its docstring. When changing either side,
 * run through the list before shipping:
 *
 *   1. renderTemplate("Hi {{lead.first_name}}", { lead: { first_name: "Jordan" } })
 *        -> "Hi Jordan"
 *   2. renderTemplate("Hi {{lead.first_name}}", { lead: {} })
 *        -> "Hi "                                     (empty default)
 *   3. renderTemplate("Hi {{lead.first_name}}", { lead: {} }, { defaultValue: "there" })
 *        -> "Hi there"
 *   4. renderTemplate("Hi {{ lead.first_name }}", { lead: { first_name: "X" } })
 *        -> "Hi X"                                    (whitespace tolerated)
 *   5. renderTemplate("Bal: {{lead.monthly_revenue}}", { lead: { monthly_revenue: 25000 } })
 *        -> "Bal: 25000"                              (number coercion)
 *   6. renderTemplate("Toggle: {{lead.opted_in}}", { lead: { opted_in: false } })
 *        -> "Toggle: false"                           (boolean coercion)
 *   7. renderTemplate("Tags: {{lead.tags}}", { lead: { tags: ["vip"] } })
 *        -> 'Tags: ["vip"]'                            (JSON fallback)
 *   8. renderTemplate("Nope: {{unknown.path}}", {})
 *        -> "Nope: "                                  (missing intermediate)
 *
 * Case 6 intentional language divergence: TS String(false) -> "false",
 * Python str(False) -> "False". The case difference is on record;
 * don't "fix" it without coordinating with the Python side.
 */

const TOKEN_RE = /\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}/g;

export type TemplateContext = Record<string, unknown>;

export type RenderOptions = {
  /** What to substitute for a missing value. Default "". */
  defaultValue?: string;
};

/**
 * Resolve a dot-pathed key against the context. Returns undefined when
 * any segment is missing, so the caller can decide between
 * default-value and error semantics.
 */
function lookup(ctx: TemplateContext, path: string): unknown {
  const parts = path.split(".");
  let cur: unknown = ctx;
  for (const p of parts) {
    if (cur === null || cur === undefined) return undefined;
    if (typeof cur !== "object") return undefined;
    cur = (cur as Record<string, unknown>)[p];
  }
  return cur;
}

/**
 * Render a template body against the context. Tokens that resolve to
 * a value get stringified; missing tokens render as defaultValue.
 *
 * Examples:
 *   render("Hi {{lead.first_name}}", { lead: { first_name: "Jordan" } })
 *     -> "Hi Jordan"
 *   render("Hi {{lead.first_name}}", { lead: {} })
 *     -> "Hi "
 *   render("Hi {{lead.first_name}}", { lead: {} }, { defaultValue: "there" })
 *     -> "Hi there"
 */
export function renderTemplate(
  template: string,
  ctx: TemplateContext,
  opts: RenderOptions = {},
): string {
  const defaultValue = opts.defaultValue ?? "";
  return template.replace(TOKEN_RE, (_match, path: string) => {
    const v = lookup(ctx, path);
    if (v === null || v === undefined) return defaultValue;
    if (typeof v === "string") return v;
    if (typeof v === "number" || typeof v === "boolean") return String(v);
    // For objects / arrays — render JSON. Rarely useful for drip
    // bodies; mostly a safety hatch so a misconfigured template
    // doesn't crash. Operators see [object Object] in the result and
    // know to fix the path.
    try {
      return JSON.stringify(v);
    } catch {
      return defaultValue;
    }
  });
}

/**
 * Extract every {{path}} token from a template body. Used by the
 * sequence builder UI to show operators which variables their drip
 * references, plus by the validation layer to surface "you reference
 * {{lead.first_name}} but the lead schema doesn't have a first_name
 * field" hints.
 */
export function extractTokens(template: string): string[] {
  const set = new Set<string>();
  let m: RegExpExecArray | null;
  TOKEN_RE.lastIndex = 0;
  while ((m = TOKEN_RE.exec(template)) !== null) {
    set.add(m[1]);
  }
  return Array.from(set).sort();
}
