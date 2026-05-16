/**
 * Shared `humanize()` for the manifest layer.
 *
 * Used by every manifest UI primitive (ManifestRecordForm,
 * ManifestKanban, the catch-all router subtitle) to turn entity / field
 * names like "lead", "funded_deal", "monthly_revenue" into operator-
 * readable "Lead", "Funded Deal", "Monthly Revenue".
 *
 * Lives here (instead of inline in each component) because the rule
 * was already duplicated three places — extracting once-and-for-all
 * before a fourth caller copies it again.
 */
export function humanize(name: string): string {
  if (!name) return "";
  return name
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}
