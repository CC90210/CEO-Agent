/**
 * Universal row-matcher for the SunBiz CRM list surfaces.
 *
 * Every list page (Lead Pipeline, Opportunity Pipeline, Offers,
 * Funded Deals, Renewals, Commissions, Lenders) supports a free-text
 * search input that writes its value to the URL `?q=` param. The
 * server-side filter runs through `rowMatchesQuery` so the matching
 * rules are consistent across every surface: case-insensitive
 * substring across every stringifiable value in the row's data blob,
 * plus a phone-digits-only twin so typing "5551234" matches phones
 * stored as "(555) 123-4567".
 *
 * Why a shared module: this matcher used to live inline in three
 * places (ManifestKanban, ManifestTable, PipelineSearchableTable).
 * Fixing a bug in one would silently leave the other two wrong.
 */

type RowLike = { id: string; data?: Record<string, unknown> | null };

export function rowMatchesQuery(row: RowLike, query: string): boolean {
  const q = (query || "").trim().toLowerCase();
  if (!q) return true;
  const qDigits = q.replace(/\D/g, "");
  const parts: string[] = [row.id];
  const data = row.data || {};
  for (const v of Object.values(data)) {
    if (v == null) continue;
    parts.push(String(v));
  }
  const phone = (data as Record<string, unknown>).phone;
  if (typeof phone === "string") parts.push(phone.replace(/\D/g, ""));
  const hay = parts.join(" ").toLowerCase();
  if (hay.includes(q)) return true;
  if (qDigits.length >= 4 && hay.includes(qDigits)) return true;
  return false;
}

/**
 * Convenience: filter an array of rows by query. Returns the original
 * array reference when the query is empty so callers can skip the
 * filter-allocation cost on the common "nothing typed" path.
 */
export function filterRowsByQuery<T extends RowLike>(rows: T[], query: string | null | undefined): T[] {
  const q = (query || "").trim();
  if (!q) return rows;
  return rows.filter((r) => rowMatchesQuery(r, q));
}
