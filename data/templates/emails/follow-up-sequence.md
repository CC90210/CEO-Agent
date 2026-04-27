---
tags: [template, email, follow-up, sequence]
name: Follow-Up Sequence (5-touch)
type: email_sequence
use_case: Following up after cold outreach or discovery call
variables: [prospect_name, prospect_company, original_topic, value_add_link, case_study_link, calendar_link]
---

# Follow-Up Email Sequence — 5 Touches

## Rules Before Sending Any Follow-Up

1. Never apologize for following up. That framing telegraphs low status.
2. Each touch must deliver something — context, value, a question, or a clear close. Never send a "just checking in" email.
3. Vary the angle on every touch. If the first email was about pain, the second is about proof, the third is about urgency.
4. Track opens and replies in the lead tracker. If they opened 3 times but didn't reply, that is a buying signal — call them.
5. Stop the sequence the moment they reply. Resume a new sequence if they go cold again.

---

## Touch 1 — Day 3 (Soft Resurface)

**Trigger:** 3 days after initial cold outreach, no reply.

**Subject:** Re: [keep same subject line as original — creates thread continuity]

Hi {{prospect_name}},

Floating this back up in case it got buried.

If the timing isn't right, no problem — just let me know and I'll check back in a few months.

Best,
Conaugh

---

**Why this works:** Short, zero pressure, framed as a service to them not a persistence from you. Thread reply keeps it in the same conversation, which gets higher open rates than a fresh email.

---

## Touch 2 — Day 7 (Value Add)

**Trigger:** 7 days after initial outreach, no reply.

**Subject:** Thought this might be useful for {{prospect_company}}

Hi {{prospect_name}},

I came across something that's directly relevant to what I mentioned in my last note: {{value_add_link}}

Worth 3 minutes. Figured I'd share it regardless of whether we ever work together.

If it sparks any questions, I'm around.

Best,
Conaugh McKenna
OASIS AI Solutions

---

**Notes on the value add:** Link to a specific article, case study, tool, or insight that is genuinely relevant to their industry or the pain point you identified. Never link to your own content at this stage — it reads as a pitch in disguise. Use third-party credibility.

---

## Touch 3 — Day 14 (Proof)

**Trigger:** 14 days after initial outreach, no reply.

**Subject:** Case study from a {{prospect_company}} type business

Hi {{prospect_name}},

Wanted to share a quick result from a client in {{industry}}: {{case_study_link}}

Same situation you're likely dealing with — [specific pain point]. They saw [specific result] within [timeframe].

I'm not going to pretend every business gets identical results, but the approach is replicable. Happy to walk you through how it would look for {{prospect_company}} if you're curious.

15 minutes would be enough to know if there's a fit: {{calendar_link}}

Best,
Conaugh

---

**Notes on the proof:** Use a real client result with real numbers. If you cannot share names, use "a {{industry}} business in [city/region]" — the specificity of the outcome matters more than the name. Round numbers (save 10 hours/week) are weaker than precise numbers (saves 8.5 hours/week on average).

---

## Touch 4 — Day 21 (Direct Ask)

**Trigger:** 21 days after initial outreach, no reply.

**Subject:** Worth a 15-minute conversation?

Hi {{prospect_name}},

I've reached out a few times and want to be upfront: I don't want to spam you.

Here's the short version of what I do: I help {{industry}} businesses automate [specific process], which typically saves [X hours/week] and [Y revenue or cost impact].

If that's interesting right now, I'd love to show you in 15 minutes: {{calendar_link}}

If not — totally fine. Just let me know and I'll close your file.

Best,
Conaugh McKenna
OASIS AI Solutions

---

**Why this works:** The "close your file" phrase creates a soft deadline and elevates your positioning — you have files to manage, you're selective about your time. It also gives them a clear, zero-friction way to opt out, which paradoxically increases reply rates.

---

## Touch 5 — Day 30 (Breakup)

**Trigger:** 30 days after initial outreach, no reply to any touch.

**Subject:** Should I close your file?

Hi {{prospect_name}},

I've reached out a few times and haven't heard back — which usually means one of three things:

1. The timing isn't right and you'll circle back when it is
2. You've already solved this problem (genuinely great)
3. My emails are ending up in spam (less great, but it happens)

I'll assume it's option 1 or 2 and won't follow up again after this.

If anything changes, my door is always open — you know where to find me.

Wishing {{prospect_company}} a strong rest of the year.

Conaugh McKenna
Founder, OASIS AI Solutions

---

**Why this works:** The breakup email consistently has the highest reply rate of any touch in the sequence. The combination of "I'll stop" + the three-option list (which makes them feel understood rather than sold to) drives responses from prospects who were lurking but not ready to engage. Many re-engage after this email, sometimes months later.

---

## Post-Sequence: Lead Disposition

After Touch 5, update `memory/LEAD_TRACKER.csv`:

| Status | Condition |
|--------|-----------|
| `cold-dead` | No reply after full 5-touch sequence |
| `cold-snooze-90d` | They replied "not now" — re-queue in 90 days |
| `qualified` | Any positive reply — move to discovery call |
| `disqualified` | They explicitly opted out or are not a fit |

---

## Obsidian Links
- [[data/templates/emails/cold-outreach]] | `memory/LEAD_TRACKER.csv`
- [[brain/USER]] | [[brain/STATE]]
