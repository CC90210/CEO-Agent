---
tags: [template, email, win-back, retention]
name: Win-Back Email
type: email
use_case: Re-engaging churned or paused clients (30–180 days since last engagement)
variables: [client_name, client_company, time_since_churn, churn_reason_hypothesis, new_capability, specific_improvement, special_offer]
---

# Win-Back Email

## When to Use

Send to former clients who:
- Cancelled a retainer or paused a project (30+ days ago)
- Went quiet after a proposal or discovery call (60+ days ago)
- Completed a one-time project with no follow-on work (90+ days ago)

Do not send this until you have something genuinely new to say. A win-back email that says "I'm just checking in" is a follow-up in disguise — it signals that nothing has changed and reminds them why they left. Wait until you have a real reason: a new capability, a relevant case study, or a meaningful improvement to the service.

---

## Pre-Send Checklist

Before writing the email, identify:
- [ ] What was the likely reason they churned? (price, timing, scope creep, unmet expectation, external change in their business)
- [ ] What is genuinely different now that would address that reason?
- [ ] Do you have a relevant new result from another client that maps to their situation?
- [ ] Is there a real offer (discount, free audit, reduced scope) or is this a soft re-engagement?

---

## Template A — New Capability (Most Common)

**Trigger:** You have built something new that is directly relevant to their business.

**Subject:** We built something that would have solved [specific issue] for you

Hi {{client_name}},

It has been {{time_since_churn}} since we worked together, and I wanted to reach out because of something specific.

We recently built [new capability / automation / system] for a {{client_company}}-type business in [their industry]. It solved [specific problem that also applies to them].

I think about {{client_company}} when I see these results because [specific reason it maps to their situation]. Here's what it looked like in practice: [one concrete outcome — a number, a before/after, a time saved].

If you are open to it, I would be happy to show you a 15-minute demo — no sales process, just showing you what it does. If it is not relevant, I will not bring it up again.

{{calendar_link}}

Best,
Conaugh McKenna
OASIS AI Solutions

---

## Template B — Acknowledge the Gap (For Clients Who Left Due to Service Issues)

**Trigger:** Client churned because of a service failure — late delivery, misaligned expectations, or a specific unresolved issue.

**Subject:** I owe you an honest update

Hi {{client_name}},

I have been thinking about our work together and wanted to be straightforward with you.

When we wrapped up, [acknowledge what happened without over-explaining or being defensive — one sentence]. I know that was not the experience you were expecting, and I take responsibility for it.

Since then, I have [specific improvement — process, tooling, communication cadence, pricing structure]. It is a real change, not just a talking point.

I am not asking you to come back based on that alone. But if you are dealing with [relevant challenge] and would be open to a conversation, I think it would go differently this time.

No pressure either way. Wanted to reach out directly rather than pretend it did not happen.

Best,
Conaugh McKenna
Founder, OASIS AI Solutions

---

## Template C — Seasonal / Business-Change Trigger

**Trigger:** Something changed in their business (new funding, new hire, scaling, rebranding, seasonal push) that makes now a good time to re-engage.

**Subject:** Congrats on [specific thing you noticed] — quick question

Hi {{client_name}},

I saw that {{client_company}} [specific business development — funding round, expansion, new location, rebrand, product launch]. Congrats — that is a real milestone.

Businesses going through that kind of growth usually hit [specific operational friction point] around this stage. It is one of the most common things I help with, and the timing is usually right when [signal that applies to them].

I am not going to pretend this is not a sales email — it clearly is. But I think the fit is actually better now than when we worked together before because of [specific reason].

Worth a 15-minute conversation to see if there is something useful here? {{calendar_link}}

Best,
Conaugh

---

## Special Offer Guidelines

If you include a special offer ({{special_offer}}):

**Do use:**
- A free audit or discovery sprint (30–60 min of focused work, no charge)
- A reduced first-month rate to lower re-entry friction
- A specific deliverable ("I'll build you one automation for free to show you what's changed")

**Do not use:**
- Percentage discounts without a reason ("20% off" with no context devalues the retainer)
- Urgency that is manufactured ("this offer expires Friday")
- Guarantees you cannot actually honor

The offer should feel like a gesture of confidence in the work, not a discount to close a deal.

---

## After the Win-Back Email

If they reply positively:
1. Book the call within 48 hours
2. Before the call, review their prior project files and identify 2-3 specific things you know about their business
3. Start the call by acknowledging the gap and what is different — do not pretend the churn did not happen
4. Treat it as a discovery call, not a resume of the prior relationship

If no reply after 14 days:
- Send one soft follow-up using Touch 2 from the follow-up sequence
- If still no reply, mark as `cold-dead` in the lead tracker and move on

---

## Obsidian Links
- [[data/templates/emails/follow-up-sequence]] | [[data/templates/emails/client-checkin]]
- [[memory/LEAD_TRACKER]] | [[brain/USER]]
