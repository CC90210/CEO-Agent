/**
 * Shared display helpers for the SunBiz pipeline UI.
 *
 * Three pieces of logic that the chevron-bar pipeline pages all need
 * in the same shape, hoisted out of the route file so adding a column
 * or tweaking a formatter is one edit, not three:
 *
 *   PIPELINE_COLUMNS — per-entity display column list (Company, Phone,
 *     etc). The /leads page, /applications page, and the /pipeline
 *     superview all read from this map.
 *
 *   formatPipelineCell — value formatter: UUIDs short-hashed for
 *     readability, money columns rendered as $X, date columns rendered
 *     as "May 23, 2026". Used by every cell in the pipeline tables.
 *
 *   pipelineLinkBase — `/t/<slug>/leads` for entity=lead etc. The
 *     "click a row to drill in" links + "+ New" CTA both need it.
 *
 * Any future column additions (e.g. score column on leads, lender_name
 * on applications when we add the join) go here and propagate
 * automatically to every consumer.
 */

export type PipelineColumn = { key: string; label: string };

export const PIPELINE_COLUMNS: Record<string, PipelineColumn[]> = {
  lead: [
    { key: "business_name", label: "Company" },
    { key: "contact_name", label: "Contact" },
    { key: "phone", label: "Phone" },
    { key: "email", label: "Email" },
    { key: "monthly_revenue", label: "Monthly Rev" },
  ],
  application: [
    { key: "lead_id", label: "Lead" },
    { key: "lender_id", label: "Lender" },
    { key: "requested_amount", label: "Requested Amt" },
    { key: "submitted_at", label: "Submitted" },
  ],
  offer: [
    { key: "lender_id", label: "Lender" },
    { key: "amount", label: "Amount" },
    { key: "term_months", label: "Term" },
    { key: "factor_rate", label: "Factor" },
  ],
};

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const MONEY_KEYS = new Set(["amount", "requested_amount", "monthly_revenue"]);
const DATE_KEYS = new Set(["submitted_at", "funded_at"]);
const SHORT_UUID_KEYS = new Set(["lead_id", "lender_id"]);

/**
 * Format a JSONB value for display in the pipeline tables. The `key`
 * argument lets us decide how to format based on the column's
 * semantic role (money/date/uuid) rather than the value's runtime
 * type, which is more reliable than JS heuristics.
 */
export function formatPipelineCell(value: unknown, key: string): string {
  if (value == null || value === "") return "—";
  const s = String(value);
  if (SHORT_UUID_KEYS.has(key) && UUID_RE.test(s)) {
    return s.slice(0, 8);
  }
  if (MONEY_KEYS.has(key) && typeof value === "number") {
    return value.toLocaleString("en-US", {
      style: "currency",
      currency: "USD",
      maximumFractionDigits: 0,
    });
  }
  if (DATE_KEYS.has(key) && s.length >= 10) {
    const d = new Date(s);
    if (!Number.isNaN(d.getTime())) {
      return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
    }
  }
  return s;
}

const ENTITY_TO_PATH: Record<string, string> = {
  lead: "leads",
  application: "applications",
  offer: "offers",
};

export function pipelineLinkBase(slug: string, entityName: string): string {
  return `/t/${slug}/${ENTITY_TO_PATH[entityName] || entityName}`;
}
