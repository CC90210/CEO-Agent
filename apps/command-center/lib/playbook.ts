/**
 * Cold Call Script V2 — multi-prospect, NEPQ-aligned, paired with the
 * 14-day free-pilot deal architecture.
 *
 * Four prospect tracks:
 *   1. service_trades   — HVAC, plumbing, landscaping, electrical
 *   2. professional     — accountants, lawyers, financial advisors, consultants
 *   3. real_estate      — agents, brokers, PM companies
 *   4. ecom             — Shopify stores, DTC brands
 *
 * Each track shares stages 1, 4, 5 (pattern interrupt + pivot + close) and
 * has its own Stage 2 (the reason) and Stage 3 (diagnose questions) tuned to
 * the prospect's actual day-to-day pain.
 */

export type ProspectTrack = "service_trades" | "professional" | "real_estate" | "ecom";

export const TRACK_LABELS: Record<ProspectTrack, string> = {
  service_trades: "Service Trades",
  professional: "Professional Services",
  real_estate: "Real Estate",
  ecom: "E-commerce / Retail",
};

export const TRACK_DESCRIPTIONS: Record<ProspectTrack, string> = {
  service_trades:
    "HVAC, plumbing, landscaping, electrical, roofing — owner-operators with field crews.",
  professional:
    "Accountants, lawyers, financial advisors, consultants — service businesses with billable-hour models.",
  real_estate:
    "Agents, brokers, property managers — high-volume lead-driven sales motion.",
  ecom:
    "Shopify stores, DTC brands, direct retail — high SKU count, customer service load, returns.",
};

// ─────────────────────────────────────────────────────────────────
// SHARED STAGES
// ─────────────────────────────────────────────────────────────────

export const STAGE_1_PATTERN_INTERRUPT = {
  num: "01",
  title: "Pattern Interrupt",
  duration: "~15 sec",
  purpose: "Disarm. Get permission.",
  line:
    "Hey [Name], it's Conaugh — we haven't spoken before, this is a cold call. You can hang up, or give me 30 seconds to tell you why I'm calling. Fair?",
  why:
    "Pattern interrupt. They expect a salesy opener; you give them honesty + control. ~80% say 'fair' out of curiosity. The 20% who hang up weren't going to buy anyway.",
};

export const STAGE_4_PIVOT = {
  num: "04",
  title: "The Pivot",
  duration: "~30 sec",
  purpose: "Drop the offer that makes saying no irrational.",
  line:
    "Here's what I do differently from anyone else you've probably talked to. I don't ask you to pay anything up front. We pick one process — the most painful one — we build the AI for it, and you run it for 14 days. If it saves you the time and money we projected, you pay implementation plus a small monthly to keep it running. If it doesn't, you owe me nothing and I walk. I'm that confident in the work. Worth a 15-minute walkthrough this week to see if it's a fit?",
  why:
    "Transfers risk onto OASIS. The 'no' gets very hard to say. There's literally no scenario where the prospect loses money.",
};

export const STAGE_5_CLOSE = {
  num: "05",
  title: "The Close",
  duration: "~15 sec",
  purpose: "Two options. Never open-ended.",
  line: "I've got Tuesday at 2pm or Thursday at 10am open. Which works?",
  why:
    "Never 'let me know what works.' Always two specific slots. Binary choice processes 4× faster than open-ended ask.",
};

// ─────────────────────────────────────────────────────────────────
// PER-TRACK STAGE 2 + STAGE 3
// ─────────────────────────────────────────────────────────────────

type TrackStages = {
  stage2_line: string;
  stage3_questions: string[];
};

export const TRACK_STAGES: Record<ProspectTrack, TrackStages> = {
  service_trades: {
    stage2_line:
      "I work with [their niche — HVAC/plumbing/landscaping] businesses around [region], and a lot of them are losing 8 to 15 hours a week on the same kind of stuff — booking jobs, chasing follow-ups, managing leads when they're already on a job site. I'm not sure if that's something you've thought about, but I figured you'd be the right person to ask.",
    stage3_questions: [
      "Walk me through how your team currently handles inbound calls or new job requests when you're in the field.",
      "What does follow-up look like with quotes that didn't close — do those just go cold?",
      "How long does it usually take, week to week, to chase paperwork and quotes? Ballpark.",
      "If that just… happened in the background and you got those hours back — what would you actually do with the time?",
      "And if nothing changes — same setup 12 months from now — what does that look like for the business?",
    ],
  },
  professional: {
    stage2_line:
      "I work with [accountants/lawyers/advisors] across Ontario, and the pattern I keep seeing is they're losing 10+ hours a week on intake — onboarding new clients, gathering documents, scheduling, repetitive client questions that don't need their actual expertise. I'm not sure if that's true for you, but I figured you'd be the right person to ask.",
    stage3_questions: [
      "Walk me through your current client intake — from first inquiry to first billable meeting.",
      "How much time per week is spent on questions clients ask that don't really need your expertise — just clarification, status updates, document gathering?",
      "What's the current process for chasing missing documents or signatures?",
      "If your billable hours went up 15% without you working more, what would that change?",
      "And if nothing changes for the next year, where does that leave the practice?",
    ],
  },
  real_estate: {
    stage2_line:
      "I work with agents and brokerages across Ontario, and the pattern I keep seeing is they're losing leads at the speed-to-lead step — someone fills out a form at 9pm and gets called back the next afternoon. By then half are gone. I'm not sure if that's something you've run into, but I figured you'd be the right person to ask.",
    stage3_questions: [
      "When a lead comes in off Zillow / your site / Facebook — walk me through what happens between the form fill and the first conversation.",
      "How fast are you actually responding, average? Honest answer.",
      "What's the conversion rate from lead to first appointment? And from first appointment to listing/sale?",
      "If your speed-to-lead dropped to under a minute and follow-up was automatic for the dead ones, how many more deals does that mean per quarter?",
      "And if nothing changes for the next 12 months, what does the pipeline look like?",
    ],
  },
  ecom: {
    stage2_line:
      "I work with Shopify and DTC brands, and the pattern I keep seeing is the customer service load eats 15-20 hours a week answering the same 30 questions — where's my order, refund, sizing, how does this work. I'm not sure if that's true for your business, but I figured you'd be the right person to ask.",
    stage3_questions: [
      "Walk me through what your team does for support tickets right now — volume per day, who handles what.",
      "What percentage of tickets are 'where's my order' or repeat questions someone has answered 50 times?",
      "How does the customer experience differ when a ticket comes in at 9am vs. 11pm?",
      "If a smart agent handled all the repeat tickets in seconds and only escalated edge cases to your team, what would your team be free to do instead?",
      "And if nothing changes for the next year, what does scaling support look like — more hires, longer waits, both?",
    ],
  },
};

// ─────────────────────────────────────────────────────────────────
// OBJECTION HANDLERS — universal
// ─────────────────────────────────────────────────────────────────

export const OBJECTIONS = [
  {
    trigger: "Send me info.",
    response:
      "Yeah I can do that — but the info I send only makes sense after 5 minutes on the phone, otherwise it's just noise. What's the actual concern, that we're not legit, or that AI feels too early for you?",
  },
  {
    trigger: "Too expensive / no budget.",
    response:
      "I haven't quoted you anything yet. So is it that you're worried it won't be worth what we charge, or that you can't justify any new spend right now no matter what?",
  },
  {
    trigger: "We have someone.",
    response:
      "Smart, that's a sign you're growth-oriented. Out of curiosity — are they doing AI specifically, or running ads/marketing? Different categories. I just want to make sure I'm not stepping on toes.",
  },
  {
    trigger: "Not interested.",
    response:
      "Totally fair. Out of curiosity though — is it that AI feels too early for the business, or you've tried something before and it didn't deliver? I'm trying to figure out what people actually need.",
  },
  {
    trigger: "It's a bad time.",
    response:
      "Got it. When's a better time — a week, a month, never? Just being real with you — I'd rather know now than chase you for nothing.",
  },
  {
    trigger: "I'll think about it.",
    response:
      "Of course. What's the part you actually want to think about — the technology, the cost, the timing, or whether we're the right people?",
  },
  {
    trigger: "Sounds too good to be true.",
    response:
      "I get that a lot — that's exactly why I do it free for 14 days. There's literally no scenario where you lose money. If the work doesn't deliver, I eat the build cost. The risk is on me, not you.",
  },
  {
    trigger: "How does it actually work?",
    response:
      "Quick: we pick one process, build the AI to run it, hand it over, you use it for 14 days. We measure the impact together on day 14. If it saved you what we promised, you pay implementation plus monthly. If not, walk. That simple.",
  },
  {
    trigger: "We're too small for AI.",
    response:
      "That's actually backwards from what I see — small teams benefit most because every hour back is a bigger percentage of capacity. What's the real concern there, complexity or cost?",
  },
  {
    trigger: "Can you put it in writing first?",
    response:
      "Absolutely, I'll send a one-page scope after our 15-min call. Way easier to write something useful once I understand your specific process. When works for you?",
  },
];

export const TRACKS: ProspectTrack[] = [
  "service_trades",
  "professional",
  "real_estate",
  "ecom",
];
