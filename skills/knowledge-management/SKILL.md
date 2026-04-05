---
name: knowledge-management
description: Use this skill whenever the user wants to capture, organize, retrieve, or maintain business intelligence. Covers PARA implementation, information capture protocols, progressive summarization, retrieval frameworks, freshness scoring, template library management, and weekly maintenance checklists.
triggers: [knowledge management, second brain, PARA, capture notes, organize information, template library, information retrieval, knowledge base, weekly maintenance]
tier: specialized
dependencies: [memory-management]
tags: [skill, knowledge, management]
---

# Knowledge Management Skill

Your brain is for thinking, not storing. Every insight, market data point, client interaction, and competitive signal must be captured somewhere reliable so you can retrieve it when it actually matters — not three weeks later when the opportunity is gone.

## Core Principle

Information that isn't captured is lost. Information that isn't organized can't be found. Information that isn't refreshed becomes a liability. This skill governs all three.

---

## PARA Implementation for Business Intelligence

PARA (Projects, Areas, Resources, Archives) is the organizing structure for all information in this system. Every document, note, and data point belongs in exactly one bucket.

### Projects — Active Engagements (maps to `memory/ACTIVE_TASKS.md`)

A project has a deadline and a finish line. When there is no finish line, it is an Area, not a Project.

**What belongs here:**
- Active client engagements (e.g., "OASIS AI — Bennett onboarding")
- Active product launches (e.g., "PropFlow — beta launch March 2026")
- Active campaigns (e.g., "Q1 outreach campaign — 50 prospects")
- Active proposals in progress

**Rules:**
- Every project has a single owner (CC or Bravo)
- Every project has a target completion date
- Completed projects move to Archives immediately (don't let dead projects clog active memory)
- Maximum 10 active projects at any time — above 10, something must be paused or killed

### Areas — Ongoing Responsibilities (maps to `brain/` files)

An area has a standard to maintain, not a finish line. You never "finish" finance or marketing.

| Area | Maintained In | Standard to Maintain |
|------|--------------|---------------------|
| Finance | `brain/STATE.md` + Atlas CFO | MRR tracked, expenses <$500/mo, runway >3 months |
| Marketing | Content strategy files + `memory/PATTERNS.md` | 1 post/day, engagement trending up |
| Operations | `memory/SOP_LIBRARY.md` | All recurring tasks have SOPs |
| Client Success | `memory/ACTIVE_TASKS.md` + `data/` | All clients receive weekly value touchpoint |
| Legal | `data/` (contracts, agreements) | All contracts signed and filed |
| Product | App repos (see APP_REGISTRY.md) | Build velocity, no critical bugs open |

### Resources — Reference Material (maps to `data/` and `docs/`)

Reference material you might need someday but are not actively working on.

**What belongs here:**
- Market research reports
- Competitive analysis snapshots
- Industry trend data
- Proposal and email templates
- Case studies and testimonials
- Course materials and training content
- Technical documentation

**File locations:**
- Market intelligence: `data/market_research/`
- Competitor data: `data/competitors.json`
- Templates: `data/templates/`
- Industry trends: `data/market_research/trends/`

### Archives — Completed or Inactive Work (maps to `memory/ARCHIVES/`)

Everything that is no longer active but may be referenced in the future.

**What belongs here:**
- Completed client projects and final deliverables
- Past proposals (won and lost — both are valuable)
- Old session logs (compressed >14 days, archived >30 days)
- Retired SOPs
- Past experiments and their outcomes

**Rule:** Archive aggressively. The cost of archiving something you later need is 2 minutes of search time. The cost of leaving dead material in active folders is constant cognitive overhead.

---

## Information Capture Protocol

The moment between "this is useful" and "I captured this" is where most business intelligence dies. These protocols eliminate that gap.

### Meeting Insights
1. During the meeting: take raw notes anywhere (phone, paper, voice memo — medium doesn't matter)
2. Within 4 hours: extract the 1-3 most important things from those notes
3. Log to `memory/SESSION_LOG.md` with the date, who was involved, and the insight
4. If the insight changes how Bravo should behave: update the relevant `brain/` file
5. If a client was involved: update their entry in the lead tracker or client health score

### Market Data
1. Source the data (Playwright for web, Context7 for library docs, manual research)
2. Note the source URL and date retrieved
3. File to `data/market_research/verticals/[industry].md` or `data/market_research/trends/[topic].md`
4. Add a freshness flag: `last_updated: YYYY-MM-DD`
5. If the data contradicts an existing belief: update `memory/LONG_TERM.md` with the correction

### Competitor Updates
1. Any new information about a competitor goes to `data/competitors.json`
2. Update the `last_checked` field and add to the `notes` array
3. If the competitor moved in a direction that changes our positioning: flag for a strategic review
4. Set a reminder to re-check within 30 days

### Client Feedback
1. Log the feedback verbatim or summarized in `memory/SESSION_LOG.md`
2. Update the client's health score (positive or negative signal)
3. If the feedback reveals a product gap: log to `memory/ACTIVE_TASKS.md` as a potential feature
4. If the feedback is praise: save as a potential testimonial in `data/testimonials/`

### Industry Trends
1. File to `data/market_research/trends/[topic].md`
2. Note the implication for each brand (OASIS AI, PropFlow, Nostalgic Requests)
3. If it changes the competitive landscape: update competitor analysis
4. If it creates a new opportunity: log to `memory/ACTIVE_TASKS.md` for strategic review

### Personal Learnings
1. Pattern (something that worked): → `memory/PATTERNS.md` tagged `[PROBATIONARY]`
2. Mistake (something that failed): → `memory/MISTAKES.md` with root cause and prevention
3. Decision (a significant choice made): → `memory/DECISIONS.md` with rationale and alternatives
4. Reflection (a lesson from failure): → `memory/SELF_REFLECTIONS.md` with Reflexion format

---

## Progressive Summarization

Raw information is too dense to retrieve quickly. Progressive Summarization (Forte method) creates four layers of density for every important piece of content.

### The Four Layers

**Layer 1 — Full Capture**
The complete source: article, transcript, meeting notes, research report. Keep this in the archive. Never delete raw captures — you will want context later.

**Layer 2 — Bold**
Read through the full capture and bold the most important passages (roughly 10-20% of the text). Do this in a single pass without overthinking. You are not summarizing — you are highlighting what struck you as important.

**Layer 3 — Highlight**
Read only the bolded passages from Layer 2. Highlight the subset that are truly critical (roughly 20-30% of the bolded text). These are the passages you would quote in a presentation or use in a decision.

**Layer 4 — Executive Summary**
Write 1-2 sentences that capture the single most important insight from the entire piece. This is what goes into `memory/LONG_TERM.md` or `memory/PATTERNS.md`.

### When to Apply Each Layer

| Content Type | Layers Used | Location |
|-------------|-------------|----------|
| Market research report | 1 → 4 | `data/market_research/` + LONG_TERM.md |
| Meeting notes | 1 → 3 | SESSION_LOG.md |
| Long article or thread | 2 → 4 | PATTERNS.md or LONG_TERM.md |
| Quick competitor update | 4 only | `data/competitors.json` notes field |
| Client conversation | 3 → 4 | SESSION_LOG.md + health score update |

**Time investment:** Layer 1 = free (capture in real time). Layer 2 = 5 minutes per document. Layer 3 = 2 minutes. Layer 4 = 30 seconds. Total for a full research report: ~10 minutes. Skip this and you will never find the insight again.

---

## Retrieval Framework

Captured knowledge that can't be retrieved is worthless. Use the right retrieval path for each type of query.

### By Topic (Semantic)
Use Memory MCP (`search_nodes`) for broad thematic queries.
```
search_nodes query="HVAC market pricing Canada"
search_nodes query="cold outreach frameworks that worked"
search_nodes query="PropFlow competitive positioning"
```
Best for: finding patterns, cross-domain connections, anything where the exact keyword is unknown.

### By Time (Chronological)
Use `memory/SESSION_LOG.md` for "what happened around [date]" queries.
- Read the log entries for the relevant date range
- Use Grep for keyword search within the log: `Grep pattern="client name" path="memory/SESSION_LOG.md"`
Best for: reconstructing a decision timeline, finding what was discussed with a specific person, understanding what was happening in a specific month.

### By Person (Relational)
Use the lead tracker CSV (`memory/LEAD_TRACKER.csv`) and SESSION_LOG.md.
- Search by company name or person name
- Look at the last touchpoint date and status
- Review any notes in the tracker
Best for: preparing for a sales call, following up with a prospect, reviewing a client relationship history.

### By Project (Task-linked)
Use `memory/ACTIVE_TASKS.md` for current work and `memory/ARCHIVES/` for completed work.
- Every task in ACTIVE_TASKS has a task ID — search by ID across files
- Completed projects are archived with a summary in the relevant monthly archive
Best for: understanding what stage a project is at, finding all work done for a specific client or product.

### By Pattern (Behavioral)
Use `memory/PATTERNS.md` and `memory/MISTAKES.md` for recurring situations.
- Patterns answer: "what approach works for this type of situation?"
- Mistakes answer: "what have we done that failed in this type of situation?"
Best for: preparing for a negotiation, debugging a recurring problem, choosing an approach for a known challenge type.

---

## Knowledge Freshness Scoring

Stale information is worse than no information — it creates false confidence.

### Freshness Thresholds by Data Type

| Data Type | Flag After | Action |
|-----------|-----------|--------|
| Market sizing data | 90 days | Re-research the key numbers |
| Competitor pricing or features | 30 days | Check their website, changelog, pricing page |
| Competitor funding status | 60 days | Check Crunchbase, LinkedIn |
| Client health score | 7 days | Log a fresh touchpoint or update score |
| Lead status (active pipeline) | 14 days | Follow up or mark stale |
| Industry trend data | 60 days | Scan relevant newsletters, X, LinkedIn |
| Technology assumptions (APIs, tools) | 30 days | Check changelogs for breaking changes |
| Personal learnings (patterns/mistakes) | No expiry | Wisdom compounds — never expires |

### How to Run a Freshness Check
1. Read `data/competitors.json` — check every `last_checked` field
2. Scan `data/market_research/` — look at `last_updated` frontmatter
3. Review `memory/LONG_TERM.md` — any confidence scores that have decayed below 0.5?
4. Check `memory/LEAD_TRACKER.csv` — any leads with no touchpoint in 14+ days?

Freshness checks run automatically as part of the weekly knowledge maintenance workflow.

---

## Template Library

Templates eliminate the blank page problem. Every recurring document type should have a template in `data/templates/`.

### Email Templates

**Cold Outreach (NEPQ-style)**
Subject: Quick question about [specific pain you noticed]
Opening: Pattern interrupt that shows research, not template
Body: Problem framing using their language, not yours
CTA: Single low-friction ask (call, reply, resource)

**Follow-Up (after no response, Day 7)**
Subject: Re: [original subject]
Body: One new value-add (article, insight, result from a similar client), restate the ask

**Proposal Cover Email**
Subject: [Company name] — [Service] Proposal
Body: 3 sentences: context of conversation, what's attached, single next step

**Invoice Reminder (overdue by 7 days)**
Subject: Invoice [#] — [Company] — 7 days overdue
Body: Friendly, specific amount, payment link, no guilt-tripping

**Client Check-In (monthly)**
Subject: [Month] check-in — [Company name]
Body: One value observation + one question about their business + offer of specific help

**Win-Back (churned client, 90 days later)**
Subject: Checking in — [Company name]
Body: What changed since they left + what's new + low-pressure re-engagement offer

### Document Templates

**Client Proposal**
- Problem statement (using their words from discovery)
- Proposed solution (scoped, not open-ended)
- Deliverables (explicit list, not "ongoing support")
- Timeline (phases with milestones)
- Investment (monthly retainer or project fee)
- What success looks like (measurable outcomes)
- Next steps (sign, pay, kickoff date)

**Statement of Work (SOW)**
- Parties, effective date
- Scope of services (detailed)
- Out of scope (explicit)
- Deliverables with acceptance criteria
- Timeline and milestones
- Fees and payment schedule
- Intellectual property ownership
- Confidentiality
- Termination (notice period, what's owed)

**NDA (Non-Disclosure Agreement)**
Use the standard Canadian bilateral NDA template. Do not draft from scratch — use a vetted template from a legal resource and have it reviewed by a lawyer for deals over $10K.

**Project Brief**
- Background (why this project exists)
- Objective (what success looks like, quantified)
- Scope (what's in and out)
- Stakeholders and roles
- Timeline
- Budget
- Constraints or risks

**Status Report**
- Period covered
- Completed this period (bulleted, specific)
- In progress (status, % complete, blockers)
- Next period plan
- Issues requiring decision
- Metrics snapshot

**Quarterly Business Review (QBR)**
- Metrics review (vs. targets set last quarter)
- What worked and why
- What didn't work and why
- Client goals for next quarter
- Proposals for next quarter's work
- Investment request (if scope is increasing)

### Content Templates

**LinkedIn Post (thought leadership)**
- Hook (one bold claim or counterintuitive observation)
- Proof (2-3 data points or specific examples)
- Lesson (what this means for the reader)
- CTA (question, follow, DM)
- No emojis as decoration. Use line breaks aggressively.

**X Thread**
- Tweet 1: Claim or story hook (must stand alone)
- Tweets 2-7: Proof, lessons, examples (one idea per tweet)
- Last tweet: Summary + follow CTA
- Length: 280 chars per tweet, 7-12 tweets per thread

**Instagram Caption**
- First line visible in feed: strongest hook (no "Hey everyone!")
- Body: story or value, conversational tone
- CTA: one action
- Hashtags: 5-10 specific, not generic
- Max 2200 chars

**Blog Outline**
- Title: [Number] ways to [achieve outcome] without [common obstacle]
- Intro: State the problem and why existing solutions fail
- Sections: Each one answer to a specific sub-question
- Conclusion: What to do next (actionable)
- Internal links: 2-3 to related content

**Case Study**
- Client (anonymized or named with permission)
- Situation before (metrics, pain)
- What we did (high level, no proprietary detail)
- Results (quantified: revenue, time saved, leads generated)
- Quote (verbatim, with permission)

---

## Weekly Knowledge Maintenance Checklist

Run every Sunday as part of the `/knowledge-maintenance` workflow.

```
[ ] SESSION_LOG.md — compress entries older than 14 days if file is over 200 lines
[ ] PATTERNS.md — any [PROBATIONARY] entries with 3+ verified uses? Promote to [VALIDATED]
[ ] PATTERNS.md — any patterns not referenced in 60+ days? Archive them
[ ] MISTAKES.md — any recurring mistakes (same root cause 2+ times)? Create a prevention SOP
[ ] data/competitors.json — check all last_checked dates. Flag anything older than 30 days
[ ] data/market_research/ — check last_updated dates. Flag anything older than 90 days
[ ] LONG_TERM.md — any facts with confidence below 0.5? Mark for re-verification
[ ] ACTIVE_TASKS.md — remove completed tasks older than 7 days. Any tasks stale for 14+ days?
[ ] Template library — any templates used this week? Update them if gaps appeared in use
[ ] brain/STATE.md — does this reflect current operational reality? Update any stale fields
[ ] Wiki-links integrity — any broken [[wiki-links]] in modified files this week?
[ ] New insights from this week — extracted and filed correctly? (patterns, mistakes, decisions)
```

---

## Obsidian Links
- [[skills/memory-management/SKILL]] | [[skills/sop-breakdown/SKILL]] | [[brain/CAPABILITIES]]
- [[memory/PATTERNS]] | [[memory/MISTAKES]] | [[memory/LONG_TERM]]
- [[memory/SESSION_LOG]] | [[brain/STATE]] | [[data/competitors]]
