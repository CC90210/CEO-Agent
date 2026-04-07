---
tags: [knowledge, wiki, clients, sales, retention, onboarding]
sources: [brain/USER.md, brain/STATE.md, skills/client-success/SKILL.md, skills/sales-methodology/SKILL.md]
last_updated: 2026-04-06
confidence: 0.90
---

# Client Playbook — How to Win and Retain OASIS AI Clients

> From first contact to long-term retention — the complete client lifecycle for OASIS AI.
> [[knowledge/index]] | [[knowledge/wiki/ai-automation-agency]] | [[knowledge/wiki/revenue-model]]

## The Client Lifecycle

```
Prospect → Discovery Call → Proposal → Close → Onboarding → Active → Retained → Expand
```

Each stage has a specific playbook. The goal is to move people through quickly while building
genuine trust. Speed and quality are not in conflict when the system is right.

## Stage 1 — Lead Generation

**Primary source (priority 1):** Inbound via CC content and CC Funnel.
- CC creates video/content on personal brand (Kona Makana)
- Content drives to CC Funnel (`cc-funnel.vercel.app`)
- Funnel captures lead → Supabase → Telegram notification to CC → booking CTA

**Secondary source (priority 2):** Cold outreach via NEPQ framework.
- Identify prospect via Google Maps scraper (`scripts/scrape_maps_emails.py`)
- Research their business for 5 minutes before reaching out
- Open with pattern interrupt — never with a pitch
- Use LinkedIn CLI (`scripts/linkedin_cli.py`) for connection + message

**Key principle:** The goal of outreach is to start a conversation, not to close a sale.
Any message that sounds like a pitch kills the conversation.

## Stage 2 — Discovery (NEPQ Framework)

The discovery call is the most important part of the sale. Do not skip it or rush it.

**NEPQ approach:**
1. Open with curiosity: "I'm not sure if this is even a fit — can I ask you a few questions first?"
2. Situation questions: "Walk me through how you currently handle follow-up with new leads"
3. Problem questions: "What happens when a lead calls after hours and no one picks up?"
4. Implication questions: "How much business do you think you're losing from slow follow-up?"
5. Need-payoff: "If you could get that time back and never miss a lead — what would that be worth?"
6. Let them sell themselves. Your job is to ask questions, not to pitch.

**What to capture during discovery:**
- Their single biggest pain point (in their exact words — use this language in the proposal)
- Current monthly revenue (to size the retainer appropriately)
- How many leads per month (to size the impact of automation)
- What they've tried before and why it didn't work
- Decision timeline and who else is involved in the decision

## Stage 3 — Proposal

Send within 24 hours of the discovery call. Delay kills momentum.

**Proposal structure:**
1. Problem statement — use their exact words from discovery
2. Proposed solution — scoped specifically to their pain (not a generic menu)
3. Deliverables — explicit list of what gets built and deployed
4. Timeline — phases with milestone dates (2–4 week deployment)
5. Investment — monthly retainer amount
6. What success looks like — 1–3 measurable outcomes
7. Next steps — "Sign here, pay first month, we schedule kickoff call"

**Pricing positioning:** Never apologize for the price. Frame the investment against the cost
of inaction (leads lost per month × average deal size).

Use `scripts/proposal_generator.py generate` to produce the initial draft.

## Stage 4 — Onboarding (First 30 Days)

The first 30 days determine 90% of long-term retention. Deliver early wins fast.

**Week 1 — Foundation:**
- Kickoff call (30 min): confirm pain points, set expectations, collect access
- Deploy core automation (lead capture + first follow-up sequence)
- Set up reporting dashboard so client can see activity

**Week 2 — First Results:**
- First automation goes live and processes real leads
- Send the client a "here's what happened this week" summary
- Identify 1 quick win to ship before end of month

**Week 3-4 — Expansion:**
- Add second automation layer (booking, content, or reporting)
- Weekly check-in call (15 min) — what's working, what to improve
- Document everything in their client file

**Onboarding command:** `/client-onboard` workflow in `.agents/workflows/`

## Stage 5 — Retention and Health Scoring

Every active client gets a health score (0–100) calculated weekly.

**Health score components:**

| Factor | Weight | Positive Signal | Negative Signal |
|--------|--------|-----------------|-----------------|
| Last touchpoint | 25% | Within 7 days | 14+ days ago |
| Payment status | 25% | Current | Overdue |
| Results delivered | 25% | Measurable improvement | No visible impact |
| Communication quality | 15% | Responds quickly, engaged | Slow/absent |
| Expansion signals | 10% | Asked about more services | No expansion mentions |

**Score thresholds:**
- 80–100: Healthy — maintain and look for expansion opportunity
- 60–79: Watch — schedule a check-in call this week
- 40–59: At risk — book an urgent meeting, identify what's wrong
- Below 40: Churn risk — escalate immediately, CC handles directly

**Tool:** `python scripts/client_health.py score <client>` and `python scripts/client_health.py alerts`

## Stage 6 — Retention Actions by Risk Level

**Healthy clients:**
- Monthly value recap email (what was automated, what it saved them)
- Proactively suggest one additional automation per quarter
- Share relevant industry data or tools that help their business

**At-risk clients (score 40–59):**
- Schedule call within 48 hours
- Ask directly: "Is there anything we're not delivering on that we should talk about?"
- Identify the gap and either fix it or set honest expectations
- Consider offering a free add-on to restore confidence

**Churn imminent (score below 40):**
- CC handles the call personally — this is not a delegation scenario
- Win-back offer: free month or reduced rate for a 3-month commitment
- If they're leaving regardless: get a testimonial and ask for a referral on the way out

## Common Objections and Responses

**"I need to think about it."**
"Totally fair — what specifically is unclear? I want to make sure you have everything you need
to decide either way."

**"It's too expensive."**
"What's the cost of losing [X leads per month × their deal size]? The automation pays for
itself if we capture just [N] additional leads a month. Does that math work for you?"

**"We tried software before and it didn't work."**
"That makes sense — most software requires you to set it up and maintain it yourself.
What we're doing is completely different: we build it, we run it, you just see the results."

**"I don't know enough about AI."**
"That's exactly why we exist. You don't need to know anything — that's our job.
You focus on your customers; we handle the technology."

## Sources
- `brain/USER.md` — CC's role, sales approach, client management philosophy
- `brain/STATE.md` — current client status and health
- `skills/client-success/SKILL.md` — full health scoring protocol
- `skills/sales-methodology/SKILL.md` — NEPQ framework details

## Obsidian Links
- [[knowledge/index]] | [[knowledge/wiki/ai-automation-agency]] | [[knowledge/wiki/revenue-model]]
- [[brain/USER]] | [[brain/STATE]]
- [[skills/client-success/SKILL]] | [[skills/proposal-generation/SKILL]] | [[skills/sales-methodology/SKILL]]
- [[.agents/workflows/client-onboard]] | [[.agents/workflows/client-health-report]]
