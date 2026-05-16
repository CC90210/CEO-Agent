/**
 * Shared value formatter for manifest UI surfaces (Kanban cards,
 * table cells, future detail-page summary blocks).
 *
 * Why a dedicated module: every CRM surface needs to render the same
 * raw `data` jsonb values with consistent currency / months / date
 * units. Inline duplication in ManifestKanban + ManifestTable diverged
 * once already (different em-dash handling) — this module is the
 * single source of truth.
 *
 * Unit inference is name-based because the manifest field type
 * ("number") doesn't carry domain semantics. For SunBiz the field
 * names are stable, so heuristics like `name.includes("amount")` are
 * safe. Future tenants with non-standard naming can override by
 * adding their entity to a future per-tenant formatter overlay.
 */

import { formatFieldValue } from "./data";
import type { ManifestEntityField } from "./schema";

/**
 * Render a single field value with operator-natural units.
 *
 * Examples:
 *   formatCardField("amount", 3435435)        → "$3,435,435"
 *   formatCardField("term_months", 12)        → "12 mo"
 *   formatCardField("factor_rate", 1.35)      → "1.35"
 *   formatCardField("fico", 650)              → "650"
 *   formatCardField("funded_at", "2026-05-16") → "May 16, 2026"
 *   formatCardField("notes", "  ")            → "—"
 */
export function formatCardField(
  name: string,
  value: unknown,
  fieldDef?: ManifestEntityField,
): string {
  if (value === undefined || value === null || value === "") return "—";
  const n = name.toLowerCase();

  // Currency — operator-facing monetary fields. Names checked
  // case-insensitively against substring matches because manifests
  // use a mix ("amount", "amount_funded", "max_funded_amount",
  // "min_monthly_revenue", "monthly_revenue", "estimated_commission").
  if (
    typeof value === "number" &&
    (n.includes("amount") ||
      n.includes("revenue") ||
      n.includes("funded") ||
      n === "price" ||
      n.includes("commission") ||
      n === "fee" ||
      n === "cost")
  ) {
    return "$" + value.toLocaleString("en-US", { maximumFractionDigits: 0 });
  }

  // Term in months — appends "mo" so a `term_months: 12` renders as
  // "12 mo" instead of "12" (which the operator might read as days).
  if (typeof value === "number" && n.includes("months")) {
    return `${value} mo`;
  }

  // FICO + score — integer string, no decimals, no commas.
  if (
    typeof value === "number" &&
    (n === "fico" || n.endsWith("_fico") || n === "score" || n.includes("fico_floor"))
  ) {
    return value.toString();
  }

  // Factor rate — 2-decimal display so 1.35 doesn't read as "1.3500000001".
  if (typeof value === "number" && (n === "factor_rate" || n === "rate")) {
    return value.toFixed(2);
  }

  // Date / datetime — manifest type wins, falls back to field-name
  // heuristic so a legacy `funded_at` string field without a type
  // declaration still gets the friendly format.
  if (
    fieldDef?.type === "date" ||
    fieldDef?.type === "datetime" ||
    n.endsWith("_at") ||
    n.endsWith("_date")
  ) {
    if (typeof value === "string" && value) {
      const d = new Date(value);
      if (!Number.isNaN(d.getTime())) {
        return d.toLocaleDateString("en-US", {
          month: "short",
          day: "numeric",
          year: "numeric",
        });
      }
    }
  }

  return formatFieldValue(value);
}

/**
 * Per-entity title field priorities. First match wins. For domain
 * entities the "best" title isn't the manifest's fields[0] — it's a
 * domain-specific header (amount for offer; business_name for
 * application; etc.). Unlisted entities fall through to the generic
 * heuristic in the caller.
 *
 * Kept here instead of co-located with ManifestKanban so a future
 * record-detail page or summary widget can pick the same headline
 * field without re-deriving it.
 */
export const ENTITY_TITLE_PRIORITY: Record<string, string[]> = {
  lead: ["name", "contact_name", "business_name", "first_name", "email", "phone"],
  application: ["business_name", "company", "name", "contact_name", "lead_id"],
  offer: ["amount", "lender_id", "lead_id"],
  funded_deal: ["amount_funded", "lender_id", "lead_id"],
  renewal: ["funded_deal_id", "due_date"],
  lender: ["name", "company"],
  commission: ["amount", "name"],
  task: ["title", "name"],
};
