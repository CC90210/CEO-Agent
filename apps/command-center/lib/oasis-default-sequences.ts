/**
 * oasis-default-sequences.ts — the starter drip sequences for the
 * OASIS HQ tenant (Phase 4.4 of the empire redesign).
 *
 * Cadence parallels the SunBiz pattern (lib/sunbiz-default-sequences.ts)
 * but the copy + funnel shape is OASIS-side: selling AI agent builds +
 * retainers to landlords, business owners, and agencies.
 *
 * Trigger events:
 *   BRAVO_RECORD_STATUS_CHANGED  — entity=lead, field=stage, to=<target>
 *
 * Channels:
 *   email — through send_gateway → Gmail. Respects CASL + 72h cooldown.
 *   sms   — disabled by default for OASIS today (no TT/Twilio number on
 *           the OASIS lane). When CC wires a number, flip enabled_on_seed
 *           on the SMS variants.
 */

import type { DripStep, DripTriggerFilter } from "./drips/types";

export type DefaultSequence = {
  name: string;
  description: string;
  trigger_event: string;
  trigger_filter: DripTriggerFilter;
  steps: DripStep[];
  one_per_lead: boolean;
  enabled_on_seed?: boolean;
};

export const OASIS_DEFAULT_SEQUENCES: DefaultSequence[] = [
  // ─────────────────────────────────────────────────────────────────
  // 1. new → contacted : automatic first-touch (DISABLED on seed —
  //    CC reviews every cold-outreach before turning on)
  // ─────────────────────────────────────────────────────────────────
  {
    name: "Cold first touch (review before enabling)",
    description:
      "Fires when a lead moves new → contacted. Sends a single hand-crafted intro email. Disabled on seed; CC reviews wording before flipping on.",
    trigger_event: "BRAVO_RECORD_STATUS_CHANGED",
    trigger_filter: { entity: "lead", field: "stage", to: "contacted" },
    one_per_lead: true,
    enabled_on_seed: false,
    steps: [
      {
        channel: "email",
        delay_minutes: 15,
        from_label: "CC",
        subject: "AI agents for {{lead.company}}",
        body:
          "Hi {{lead.name}},\n\nI run OASIS AI — we build custom AI agents that handle the repetitive backend of small businesses (lead follow-up, inbox triage, content publishing, financial ops).\n\nFor {{lead.company}}, the biggest wins usually come from the work you don't want to hire a person for but is still eating hours. Would love to hear what those look like for you.\n\nWorth a 15-min look?\n\n— CC, OASIS AI",
      },
    ],
  },

  // ─────────────────────────────────────────────────────────────────
  // 2. contacted → qualified : warm follow-up cadence
  // ─────────────────────────────────────────────────────────────────
  {
    name: "Qualified lead nurture",
    description:
      "Fires when a lead moves contacted → qualified. Sends a case-study email then a check-in 4 days later if no reply.",
    trigger_event: "BRAVO_RECORD_STATUS_CHANGED",
    trigger_filter: { entity: "lead", field: "stage", to: "qualified" },
    one_per_lead: true,
    steps: [
      {
        channel: "email",
        delay_minutes: 60, // 1h after stage flip
        from_label: "CC",
        subject: "Quick look at what we'd build for {{lead.company}}",
        body:
          "Hi {{lead.name}},\n\nThanks for the reply — picking up from where we left off.\n\nFor context, our most recent build was a funding-shop CRM (SunBiz) that replaced their Salesforce + JotForm + a manual underwriting workflow in 3 weeks. The agent now handles lead follow-up, application intake, lender shop-out, and AI-powered underwriting end-to-end.\n\nFor {{lead.company}} the equivalent depends on what's eating your time. Want to grab 20 min this week to scope it?\n\n— CC, OASIS AI",
      },
      {
        channel: "email",
        delay_minutes: 60 * 24 * 4, // +4 days
        from_label: "CC",
        subject: "Re: {{lead.company}}",
        body:
          "Hi {{lead.name}},\n\nNudging the thread — totally fine if the timing's wrong, just want to make sure I didn't lose this in your inbox.\n\nIf a 20-min call doesn't fit, I can send a quick written scope instead — what would help more?\n\n— CC",
      },
    ],
  },

  // ─────────────────────────────────────────────────────────────────
  // 3. proposal sent → drip : 2-touch nudge over 7 days
  // ─────────────────────────────────────────────────────────────────
  {
    name: "Proposal follow-up",
    description:
      "Fires when a lead moves qualified → proposal. Nudges the prospect at 2 days and 7 days if they haven't signed.",
    trigger_event: "BRAVO_RECORD_STATUS_CHANGED",
    trigger_filter: { entity: "lead", field: "stage", to: "proposal" },
    one_per_lead: true,
    steps: [
      {
        channel: "email",
        delay_minutes: 60 * 24 * 2, // +2 days
        from_label: "CC",
        subject: "Proposal for {{lead.company}} — any questions?",
        body:
          "Hi {{lead.name}},\n\nFollowing up on the proposal I sent — happy to walk through any of the line items or scope tradeoffs on a quick call.\n\nWhat would be most useful — answers in email, or 15 min on the phone?\n\n— CC",
      },
      {
        channel: "email",
        delay_minutes: 60 * 24 * 7, // +7 days
        from_label: "CC",
        subject: "Closing the loop on {{lead.company}}",
        body:
          "Hi {{lead.name}},\n\nLast nudge from me — if the proposal's a 'not right now', that's totally fine, I'll close the thread on my end and we can pick it back up when it's the right time.\n\nIf you'd like to move forward, just reply with a kickoff date that works.\n\n— CC",
      },
    ],
  },

  // ─────────────────────────────────────────────────────────────────
  // 4. won → onboarding kickoff
  // ─────────────────────────────────────────────────────────────────
  {
    name: "Won — onboarding kickoff",
    description:
      "Fires when a lead moves to won. Confirms next steps and sets the kickoff call.",
    trigger_event: "BRAVO_RECORD_STATUS_CHANGED",
    trigger_filter: { entity: "lead", field: "stage", to: "won" },
    one_per_lead: true,
    steps: [
      {
        channel: "email",
        delay_minutes: 30,
        from_label: "CC",
        subject: "Welcome to OASIS — kickoff for {{lead.company}}",
        body:
          "Hi {{lead.name}},\n\nLocked in — excited to build with you.\n\nNext steps:\n  1. I'll send a kickoff call invite for this week. Block 60 min.\n  2. Before that call, I'll send a short questionnaire so we capture the existing-system context.\n  3. Build sprint kicks off the Monday after kickoff. You'll see weekly Friday demos.\n\nQuestions any time.\n\n— CC, OASIS AI",
      },
    ],
  },

  // ─────────────────────────────────────────────────────────────────
  // 5. lost → 60-day soft re-engagement (DISABLED on seed)
  // ─────────────────────────────────────────────────────────────────
  {
    name: "Lost — 60-day re-engagement (review before enabling)",
    description:
      "Fires when a lead moves to lost. Single check-in 60 days later. Disabled on seed; CC enables once a sane wording is locked in.",
    trigger_event: "BRAVO_RECORD_STATUS_CHANGED",
    trigger_filter: { entity: "lead", field: "stage", to: "lost" },
    one_per_lead: true,
    enabled_on_seed: false,
    steps: [
      {
        channel: "email",
        delay_minutes: 60 * 24 * 60, // 60 days
        from_label: "CC",
        subject: "Quick check-in on {{lead.company}}",
        body:
          "Hi {{lead.name}},\n\nNo agenda — circling back two months on. The AI side moves fast and what wasn't right then often is now. If you want a no-pressure 15 min to revisit, I'm in.\n\nOtherwise no action needed, hope the work's going well.\n\n— CC",
      },
    ],
  },
];
