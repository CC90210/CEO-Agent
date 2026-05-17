/**
 * Stage metadata for the SunBiz tenant — colors + display labels for the
 * Lead Pipeline and Opportunity Pipeline arrow-bar.
 *
 * Verbatim from Adon's 2026-05-16 Salesforce screenshots so the rebuilt
 * UI matches the colors his team already pattern-matches against. When
 * Adon changes a stage name on his side (which he won't until the
 * migration completes), update both this file and SUN_SEED's enum_values.
 *
 * Color choices map to the actual Salesforce Lightning hex codes where
 * possible; close approximations elsewhere. Background = solid fill on
 * the arrow chevron; text = readable foreground (white for dark fills,
 * dark navy for the yellow stages).
 */

export type StageMeta = {
  key: string;
  label: string;
  bg: string;   // arrow fill
  fg: string;   // arrow text color
};

export const LEAD_PIPELINE_STAGES: StageMeta[] = [
  { key: "imported",            label: "Imported",            bg: "#E96F2D", fg: "#FFFFFF" },
  { key: "not_interested",      label: "Not Interested",      bg: "#2C5F6E", fg: "#FFFFFF" },
  { key: "hot_lead",            label: "Hot Lead",            bg: "#FFB81C", fg: "#1A1A1A" },
  { key: "missing_info",        label: "Missing Info",        bg: "#0070D2", fg: "#FFFFFF" },
  { key: "declined",            label: "Declined",            bg: "#C23934", fg: "#FFFFFF" },
  { key: "follow_up",           label: "Follow Up",           bg: "#706E6B", fg: "#FFFFFF" },
  { key: "sent_application",    label: "Sent Application",    bg: "#E91A86", fg: "#FFFFFF" },
  { key: "viewed_application",  label: "Viewed Application",  bg: "#04844B", fg: "#FFFFFF" },
  { key: "signed_application",  label: "Signed Application",  bg: "#0099A8", fg: "#FFFFFF" },
  { key: "default",             label: "Default",             bg: "#7D7022", fg: "#FFFFFF" },
  { key: "submitted",           label: "Submitted",           bg: "#5C5121", fg: "#FFFFFF" },
  { key: "approved",            label: "Approved",            bg: "#3BA755", fg: "#FFFFFF" },
];

export const OPPORTUNITY_PIPELINE_STAGES: StageMeta[] = [
  { key: "submitted_to_underwriting", label: "Submitted To Underwriting", bg: "#54698D", fg: "#FFFFFF" },
  { key: "approved_open_offers",      label: "Approved Open Offers",      bg: "#04844B", fg: "#FFFFFF" },
  { key: "contracts_ordered",         label: "Contracts Ordered",         bg: "#794500", fg: "#FFFFFF" },
  { key: "funded",                    label: "Funded",                    bg: "#0070D2", fg: "#FFFFFF" },
  { key: "approved_never_funded",     label: "Approved Never Funded",     bg: "#E96F2D", fg: "#FFFFFF" },
  { key: "no_offers_available",       label: "No Offers Available",       bg: "#706E6B", fg: "#FFFFFF" },
  { key: "dead_file",                 label: "Dead File",                 bg: "#BA0517", fg: "#FFFFFF" },
];

export function getStageMeta(entityName: string): StageMeta[] {
  if (entityName === "lead") return LEAD_PIPELINE_STAGES;
  // application is the operator-facing Opportunity Pipeline (per
  // Salesforce vocabulary); offer is a per-lender term-sheet sub-detail
  // that happens to share the same stage labels. Both resolve to the
  // same StageMeta list.
  if (entityName === "application") return OPPORTUNITY_PIPELINE_STAGES;
  if (entityName === "offer") return OPPORTUNITY_PIPELINE_STAGES;
  return [];
}

export function findStage(entityName: string, key: string): StageMeta | undefined {
  return getStageMeta(entityName).find((s) => s.key === key);
}
