/**
 * sunbiz-default-sequences.ts — the 5 starter drip sequences for new
 * SunBiz tenants (Phase 4.5 of the SunBiz CRM build).
 *
 * These match the cadence Jordan + CC locked in at the 2026-05-15
 * meeting. They get inserted into drip_sequences when a SunBiz tenant
 * is provisioned via /api/onboarding/wizard or directly by Bravo. The
 * operator can edit / disable / delete any of them from /sequences.
 *
 * Why seed defaults instead of leaving the tenant empty:
 *   - SunBiz funding ops can't function without follow-up cadence.
 *     Forcing every new tenant to design their own drips from scratch
 *     means real leads ghost the pipeline while the operator figures
 *     out the JSON.
 *   - The seeded drips are tuned for the meeting-agreed lead.stage +
 *     offer.stage enums (Phase 2) so they fire end-to-end from day 1.
 *
 * Cadence and copy are deliberately conservative:
 *   - Cooldowns leave room for the operator to layer manual touches
 *   - "Solara" / "Helios" sender labels match SunBiz's agent personas
 *   - Plain text only; no HTML / images / links beyond simple URLs
 *   - All copy is meeting-tested wording from Text Torrent existing
 *     usage, not freshly-AI-generated cold-email-school filler
 */

import type { DripStep, DripTriggerFilter } from "./drips/types";

export type DefaultSequence = {
  name: string;
  description: string;
  trigger_event: string;
  trigger_filter: DripTriggerFilter;
  steps: DripStep[];
  one_per_lead: boolean;
};

export const SUNBIZ_DEFAULT_SEQUENCES: DefaultSequence[] = [
  // ─────────────────────────────────────────────────────────────────
  // 1. Cold -> follow_up : 3-touch follow-up cadence
  // ─────────────────────────────────────────────────────────────────
  {
    name: "Follow-up sequence (cold leads)",
    description:
      "Fires when a lead moves cold → follow_up. 3-touch SMS+email cadence to get them on a call.",
    trigger_event: "BRAVO_RECORD_STATUS_CHANGED",
    trigger_filter: { entity: "lead", field: "stage", to: "follow_up" },
    one_per_lead: true,
    steps: [
      {
        channel: "sms",
        delay_minutes: 10,
        from_label: "Solara",
        body:
          "Hi {{lead.contact_name}} — this is Solara at SunBiz Funding. Saw your business {{lead.business_name}} and wanted to see if you're looking at funding options for growth or working capital this quarter. Reply YES if you'd like options.",
      },
      {
        channel: "email",
        delay_minutes: 60 * 24, // 24h
        from_label: "Solara",
        subject: "Quick funding options for {{lead.business_name}}",
        body:
          "Hi {{lead.contact_name}},\n\nFollowing up on yesterday's note — we work with operators like you to surface 3-5 lender offers in under 48h, no commitment to take any of them.\n\nWhat does your monthly revenue look like right now? If it's in the {{lead.monthly_revenue}} range we can almost certainly get you offers worth reviewing.\n\nReply with a good time today or tomorrow.\n\n— Solara, SunBiz Funding",
      },
      {
        channel: "sms",
        delay_minutes: 60 * 24 * 3, // +3 days
        from_label: "Solara",
        body:
          "{{lead.contact_name}} — last note from me on funding. Send a 1-line reply (yes / not now / never) and I'll match the cadence. Otherwise I'll close out the thread on my end.",
      },
    ],
  },

  // ─────────────────────────────────────────────────────────────────
  // 2. Viewed application -> nudge : 2-touch
  // ─────────────────────────────────────────────────────────────────
  {
    name: "Viewed application nudge",
    description:
      "Fires when a lead opens their personalized application link. Nudges them through the form.",
    trigger_event: "BRAVO_RECORD_STATUS_CHANGED",
    trigger_filter: { entity: "lead", field: "stage", to: "viewed_application" },
    one_per_lead: true,
    steps: [
      {
        channel: "sms",
        delay_minutes: 30,
        from_label: "Solara",
        body:
          "Hi {{lead.contact_name}} — saw you opened the application. Anything I can clarify? It's 3 quick steps — basic info, the app itself, then 3 months of bank statements at the end.",
      },
      {
        channel: "email",
        delay_minutes: 60 * 24, // 24h
        from_label: "Solara",
        subject: "Heads up on the application for {{lead.business_name}}",
        body:
          "Hi {{lead.contact_name}},\n\nWanted to follow up — when you finish the application, the lenders we work with usually return 3-5 offers within 24-48h. The bank statements at step 3 are the gating piece; without them no underwriting can fire.\n\nIf anything's holding you up, reply here and I'll help.\n\n— Solara, SunBiz Funding",
      },
    ],
  },

  // ─────────────────────────────────────────────────────────────────
  // 3. Submitted -> underwriting holding pattern
  // ─────────────────────────────────────────────────────────────────
  {
    name: "Submitted — underwriting wait",
    description:
      "Fires when a lead's application is fully submitted. Sets expectations + asks them to stay reachable.",
    trigger_event: "BRAVO_RECORD_STATUS_CHANGED",
    trigger_filter: { entity: "lead", field: "stage", to: "submitted" },
    one_per_lead: true,
    steps: [
      {
        channel: "sms",
        delay_minutes: 15,
        from_label: "Solara",
        body:
          "{{lead.contact_name}} — your file is in to underwriting. Keep your phone on for the next 24h; lenders often call to verify details. I'll be the one bringing the offers back to you.",
      },
    ],
  },

  // ─────────────────────────────────────────────────────────────────
  // 4. Declined -> 1-month revival
  // ─────────────────────────────────────────────────────────────────
  {
    name: "Declined — 1-month check-back",
    description:
      "Professional 1-month re-engagement for leads declined after bank-statement review. Doesn't burn the bridge.",
    trigger_event: "BRAVO_RECORD_STATUS_CHANGED",
    trigger_filter: { entity: "lead", field: "stage", to: "declined" },
    one_per_lead: true,
    steps: [
      {
        channel: "email",
        delay_minutes: 60 * 24 * 30, // 30 days
        from_label: "Solara",
        subject: "Checking in on {{lead.business_name}}",
        body:
          "Hi {{lead.contact_name}},\n\nIt's been about a month since we last talked. Funding markets shift — what didn't fit last month sometimes does this month, especially if revenue's trending up or you've added new business.\n\nIf you're open to another look, send me an updated month of bank statements and I'll re-shop the file. No pressure — just want to keep the door open.\n\n— Solara, SunBiz Funding",
      },
    ],
  },

  // ─────────────────────────────────────────────────────────────────
  // 5. Approved-never-funded -> monthly bank-statement refresh
  // ─────────────────────────────────────────────────────────────────
  {
    name: "No offers / approved-not-funded — monthly bank statement refresh",
    description:
      "Fires when an offer rolls to no_offer status. Asks the operator for updated bank statements monthly so we can re-shop.",
    trigger_event: "BRAVO_RECORD_STATUS_CHANGED",
    trigger_filter: { entity: "offer", field: "stage", to: "no_offer" },
    // Multi-fire-allowed (one_per_lead=false). The monthly cadence is
    // the whole point — same lead, new month, new statements.
    one_per_lead: false,
    steps: [
      {
        channel: "email",
        delay_minutes: 60 * 24 * 30, // 30 days
        from_label: "Solara",
        subject: "Quick re-shop for {{lead.business_name}}?",
        body:
          "Hi {{lead.contact_name}},\n\nIt's been a month since we last shopped your file. If you can send the latest month of bank statements, I'll re-run it through our lender network and see what's changed.\n\nFast turnaround — usually 24-48h to bring offers back.\n\n— Solara, SunBiz Funding",
      },
    ],
  },
];

/**
 * Build rows ready for `db.from("drip_sequences").insert(...)` for a
 * given tenant. Caller fills in tenant_id + created_by.
 */
export function buildSunbizSequenceRows(
  tenantId: string,
  createdBy: string | null,
): Array<{
  tenant_id: string;
  name: string;
  description: string;
  trigger_event: string;
  trigger_filter: DripTriggerFilter;
  steps: DripStep[];
  enabled: boolean;
  one_per_lead: boolean;
  created_by: string | null;
}> {
  return SUNBIZ_DEFAULT_SEQUENCES.map((s) => ({
    tenant_id: tenantId,
    name: s.name,
    description: s.description,
    trigger_event: s.trigger_event,
    trigger_filter: s.trigger_filter,
    steps: s.steps,
    enabled: true,
    one_per_lead: s.one_per_lead,
    created_by: createdBy,
  }));
}
