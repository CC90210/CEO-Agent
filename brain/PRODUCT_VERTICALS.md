---
description: "Reference defining product vertical packs, canonical-vs-personal architecture (shipped frameworks vs buyer credentials), and update flow for additions"
tags: [product, verticals, lead-management, marketing-research, pricing]
last_updated: 2026-07-22
freshness_threshold_days: 30
verified: 2026-06-09
---
# PRODUCT VERTICALS -- Business in a Box Research Reference

> Companion to [[brain/PRODUCT_ARCHITECTURE]]. Research layer for the product: canonical agent knowledge, vertical pack contents, lead management best practice, marketing research methodology, and product pricing.
> Last updated: 2026-04-18 | Confidence: HIGH (triangulated 3+ sources per claim)

---

## Section 1: Template vs Personalization Architecture

### The Core Pattern

The WordPress analogy holds: theme = core layer (same for every buyer), content = personal layer (per-buyer). Production-grade template repos use this separation (verified: GitHub open-gitagent spec, AndrewAltimit template-repo, Vercel knowledge-agent-template).

**Core layer** -- git-tracked, shipped, universal:
- skills/ -- all playbooks, frameworks, sub-agent specs
- brain/ -- SOUL.md (template structure, buyer fills), BRAIN_LOOP, INTERACTION_PROTOCOL, CANONICAL_ROLES
- scripts/ -- all CLI engines (.env.agents.template documents required keys, no hardcoded values)
- agents/ -- sub-agent definitions
- skills/verticals/[vertical]/ -- pluggable vertical packs (buyer opts into one at install)
- .env.agents.template -- scaffold of required keys with placeholder values

**Personal layer** -- gitignored or in buyer private fork, NEVER shipped:
- personal/USER.md -- owner name, business context, goals, values
- personal/brands/ -- brand voice, ICP, competitor list
- personal/ledger/ -- financial accounts, actuals
- personal/goals/ -- OKRs, quarterly targets (buyer-filled)
- .env.agents -- credentials (always gitignored)
- data/pulse/*.json -- live operational state
- memory/ -- SESSION_LOG, MISTAKES, PATTERNS (per-buyer learning)

### What MUST Be Canonical

- All framework skills (OKRs, 13-week cashflow, NEPQ, funnel math, cohort analysis)
- Sub-agent role definitions (writer, researcher, debugger, analyst)
- The cross-agent pulse protocol schema
- Setup scripts, CLI engine interfaces, MCP integration wrappers
- SOUL.md template structure (identity shell -- buyer fills name/values/mission)
- .env.agents.template (documents what keys are needed)

### What MUST Be Personal

- Actual owner identity, history, values (USER.md filled)
- All client and brand names, competitive intelligence about their specific market
- Financial account details, real MRR figures, Stripe keys
- Session memory -- mistakes and patterns are per-buyer learning, not universal
- Credentials -- every key in .env.agents

### Update Flow When Core Gets New Skills

The proven pattern (GitHub actions-template-sync, Atlassian upstream docs, GitHub community discussion #23528 confirm this):

Buyer runs: git remote add upstream, git fetch upstream, git merge upstream/main. Conflicts resolved by .gitattributes merge strategy: skills/ always takes upstream, personal/ always takes ours (buyer), brain/SOUL.md is a manual 3-way merge.

Document in each agent UPGRADE.md. For non-technical buyers, the GitHub Actions actions-template-sync marketplace action opens a PR automatically when upstream updates.

### Recommended Distribution Model

V1: Public template repo (GitHub) => buyer forks => buyer customizes personal/ => runs on their machine. Optional managed-setup upsell. See [[brain/PRODUCT_ARCHITECTURE]] for full tier structure and clone flow.

---

## Section 2: Canonical Frameworks Every Agent Role Must Carry

### CEO Agent -- Framework Set

| Framework | Why It Is Non-Negotiable |
|-----------|--------------------------|
| OKRs (Objectives and Key Results) | Universal goal-setting; 40% top-down + 60% bottom-up (OKR International 2025) |
| Ideal Customer Profile (ICP) scoring | Every revenue decision traces back to who the buyer actually serves |
| Jobs-to-Be-Done (JTBD) | Clayton Christensen -- underlying motivation, not product features, drives purchase |
| Porter Five Forces | Competitive dynamics framing for any business |
| The Flywheel (Jim Collins) | Momentum-based growth vs event-driven thinking |
| SWOT + TOWS matrix | Strategic situation assessment |
| Risk register + scenario planning | Irreversible decisions need downside framing |
| Eisenhower Matrix | Task prioritization for solo founders drowning in urgent |
| The One Metric That Matters (OMTM) | Focus filter for stage-appropriate KPI selection |
| SPARC methodology | Structured problem decomposition for multi-hypothesis decisions |

**Seminal books to seed CEO knowledge library:**
1. Good to Great -- Jim Collins (flywheel, hedgehog concept)
2. The Hard Thing About Hard Things -- Ben Horowitz (real-world CEO decisions)
3. Zero to One -- Peter Thiel (competition, monopoly thinking)
4. Traction -- Gino Wickman (EOS operating system for small business)
5. The E-Myth Revisited -- Michael Gerber (founder vs operator trap)

**Key public data sources:**
- Harvard Business Review (hbr.org)
- First Round Review (review.firstround.com)
- YC Essay archive (paulgraham.com, ycombinator.com/library)
- CB Insights / Crunchbase (competitive and market intelligence)

---

### CFO Agent -- Framework Set

| Framework | Why It Is Non-Negotiable |
|-----------|--------------------------|
| 13-week rolling cashflow | Survival instrument; week-by-week cash in/out. Prevents surprise insolvency. |
| Unit economics (LTV, CAC, payback period, gross margin) | Every growth decision needs these inputs |
| Net Revenue Retention (NRR) | Expansion vs churn balance; single best SaaS health signal |
| Rule of 40 (growth rate + profit margin >= 40%) | SaaS viability benchmark |
| EBITDA margin analysis | Agency/services profitability benchmark (target: 20-30%) |
| Break-even analysis | Stage-gate for every major cost decision |
| Scenario modeling (base / bull / bear) | Irreversible spend decisions need three futures |
| MRR decomposition (new + expansion + contraction + churn) | Shape of growth, not just the number |
| CRA/IRS tax framework | Canada: T2125, HST/GST; US: Schedule C, SE tax. Every solo founder overpays or underpays. |
| Debt vs equity capital decision matrix | Knowing when to use credit vs raise |

**Seminal books to seed CFO knowledge library:**
1. Profit First -- Mike Michalowicz (cash allocation system for small business owners)
2. Simple Numbers, Straight Talk, Big Profits -- Greg Crabtree (gross margin as primary metric)
3. Financial Intelligence -- Karen Berman and Joe Knight (financial literacy for non-finance founders)
4. The Intelligent Investor -- Benjamin Graham (long-term capital allocation thinking)
5. Venture Deals -- Brad Feld and Jason Mendelson (cap tables, term sheets if raising)

**Key public data sources:**
- CRA (canada.ca/cra) -- T2125, HST, business deductions
- IRS.gov -- Schedule C, SE tax
- Stripe Revenue Recognition docs (MRR accounting)
- Baremetrics / ChartMogul (SaaS industry medians)
- FRED (macroeconomic data for planning assumptions)

---

### CMO Agent -- Framework Set

| Framework | Why It Is Non-Negotiable |
|-----------|--------------------------|
| Funnel math (awareness to conversion to retention to advocacy) | Every marketing decision should trace to a stage |
| Jobs-to-Be-Done (JTBD) | Positioning and messaging hinge on this |
| April Dunford Positioning Framework | 5 components: competitive alternatives, unique attributes, value, target characteristics, market category |
| Hook and Lead magnet architecture (Hormozi) | Attention capture is the first constraint in every funnel |
| Content velocity framework | Platform-native cadence, format, hook structure |
| Multi-touch attribution | Knowing which channels actually close |
| Customer journey mapping | Pre/during/post purchase touchpoints |
| Byron Sharp Reach principle (How Brands Grow) | Mental availability + physical availability; distinctiveness over differentiation |
| Mark Ritson market orientation model | Research => strategy => tactics; reverse engineered from customer |
| AEO (Answer Engine Optimization) | 2025 shift: AI search citations over SEO clicks |

**Seminal books to seed CMO knowledge library:**
1. Obviously Awesome -- April Dunford (positioning -- mandatory for any CMO agent)
2. 100M Leads -- Alex Hormozi (lead magnets, warm/cold outreach, give-ask cycle)
3. How Brands Grow -- Byron Sharp (reach, mental availability, distinctiveness)
4. This Is Marketing -- Seth Godin (smallest viable audience, permission marketing)
5. The Mom Test -- Rob Fitzpatrick (customer discovery, avoiding vanity feedback)

**Key public data sources:**
- Google Search Console + Google Trends (free demand data)
- Ahrefs / Semrush (keyword difficulty, traffic estimates, backlink data)
- SimilarWeb (competitor traffic analysis)
- Reddit (niche forums reveal real customer language)
- SparkToro (audience research -- where your ICP spends time online)
- Exploding Topics (early trend detection)

---

## Section 3: Vertical-Specific Extensions (Pluggable Modules)

Each vertical = a folder under skills/verticals/[vertical]/ installed on buyer opt-in. CC instance ships with Agency + Creator packs activated.

### 1. Agency (consulting, dev shops, marketing agencies)

**Revenue model:** Project fees + monthly retainers. Gross margins: specialists 25-40%, generalists 15-20% EBITDA (Parakeeto / tmetric 2025 benchmarks). Retainer MRR is the north star.

**Lead generation channels that work:**
- Warm network (referrals from past clients) -- lowest CAC by a factor of 10
- Content / thought leadership (LinkedIn, newsletters) -- builds inbound over 6-12 months
- Outbound cold email (personalized, NEPQ framework) -- works for 5K-25K deals

**Pricing conventions:**
- Discovery call => SOW => project fee or monthly retainer
- Retainer range: 1,500-10,000/mo for solo/small agency
- Value-based pricing: 10-30% of the result delivered

**Agency-specific frameworks:**
- Utilization math: target 65-75% billable utilization. Below 65% = leaving money on the table. Above 85% = burnout + quality drop (tmetric 2025 benchmark confirms 81% median).
- Scope creep guard: every change request => SOW amendment => approval. Non-negotiable operational discipline.

**Top experts:** Jason Swenk (Agency Mastery), David C. Baker (The Business of Expertise), Blair Enns (Win Without Pitching)

---

### 2. SaaS (B2B tools, micro-SaaS)

**Revenue model:** MRR/ARR subscriptions. Gross margins: 70-90% for pure software. Top-quartile micro-SaaS: 85%+ gross margin.

**Lead generation channels that work:**
- SEO (content + product-led) -- 3.3x better unit economics than social ads (rockingweb.com 2025 analysis of 1,000 micro-SaaS)
- Product-led growth (free tier, trial, in-product upgrade prompt)
- Community-led (build in public, niche forum presence)

**Pricing conventions:**
- Freemium to paid conversion target: 2-5% of free users
- Tiered pricing: Starter / Growth / Scale (seat-based or usage-based)
- Annual discount: 15-20% to convert monthly to annual

**SaaS-specific frameworks:**
- MRR cohort analysis: track revenue per signup cohort monthly. Identifies whether retention is improving.
- LTV:CAC ratio: minimum 3:1; target 4:1+ for B2B. Median 3.6:1 (Benchmarkit 2024). Below 3:1 = fix retention before scaling acquisition.
- Net Revenue Retention (NRR): target >100%. Best-in-class SaaS runs 120-130% NRR.

**Top experts:** Jason Lemkin (SaaStr), Patrick Campbell (ProfitWell/Paddle), Lenny Rachitsky (Lenny Newsletter)

---

### 3. E-commerce / DTC (Shopify, physical products)

**Revenue model:** Product margin on units sold. Gross margins: 30-60% DTC physical, 60-80% digital. AOV and repeat purchase rate are primary levers after initial acquisition.

**Lead generation channels that work:**
- Meta (Facebook/Instagram) paid ads -- highest volume for physical goods
- Influencer/UGC partnerships -- lower CPM, higher trust signal
- Email list (owned channel) -- highest LTV-per-impression after initial list build

**Pricing conventions:**
- AOV optimization: bundle offers, upsells, post-purchase sequences
- Subscription/replenishment model adds predictable MRR layer to lumpy revenue
- Abandoned cart recovery: 3-email sequence -- industry standard 15-20% recovery rate

**E-commerce-specific frameworks:**
- Shopify abandoned cart flow: trigger at cart abandonment => email 1 (0hr, reminder) => email 2 (1hr, social proof + urgency) => email 3 (24hr, final offer). Klaviyo is the standard tool.
- COGS per SKU analysis: know your landed cost before running any paid acquisition. CPM-based ROAS without COGS is meaningless.

**Top experts:** Ezra Firestone (Smart Marketer), Andrew Youderian (eCommerceFuel), Chase Dimond (DTC email)

---

### 4. Coaching / Info-products (courses, group programs)

**Revenue model:** High-ticket 1:1 (3K-25K+), group program (1K-5K), course (97-997). Margins: 70-90% after platform fees. No COGS on digital delivery.

**Lead generation channels that work:**
- Organic social (short-form video => long-form authority => DMs)
- Webinar / workshop funnel -- highest close rate for 1K+ offers
- Podcast guesting + email list -- builds trust over time

**Pricing conventions:**
- Application funnel (not buy now) -- adds perceived selectivity and qualifies buyers
- Payment plans: 3-6 month installments at 20-30% premium vs one-time
- Cohort model reduces support burden vs 1:1 while maintaining premium pricing

**Coaching-specific frameworks:**
- Webinar funnel: traffic => opt-in => email sequence (3-5 days) => live or evergreen webinar => offer => close sequence. Teach-pitch ratio: 70/30.
- Ascension ladder: free content => low-ticket tripwire (47-197) => core offer (997-5K) => high-ticket (10K+). Most coaches skip the middle and leave money on the table.

**Top experts:** Alex Hormozi (Acquisition.com), Amy Porterfield (online course launches), Dan Martell (SaaS + coaching)

---

### 5. Creator / Personal Brand (DJ, podcaster, newsletter)

**Revenue model:** Sponsorships (25-50 CPM for podcast mid-rolls; direct sponsorships command 30-50% premium over network rates per Castos/Acast 2025 data), digital products, community memberships, affiliate income, brand deals. Income is lumpy until multiple streams layer.

**Lead generation channels that work:**
- Platform-native growth (TikTok, Instagram Reels, YouTube Shorts for top-of-funnel)
- Newsletter (owned audience -- highest monetization ceiling; Beehiiv, Kit)
- Collab with adjacent creators (cross-pollination beats ads at early stage)

**Pricing conventions:**
- Sponsorship CPM baseline: 25-40/episode (host-read). 1,000 downloads/episode minimum threshold most brands require.
- Brand deals: 500-5K per post depending on audience size and engagement rate
- Membership/Patreon: 5-25/mo tiers; target 1-3% of free audience

**Creator-specific frameworks:**
- Content repurposing chain: one long-form piece (podcast/YT video) => 5-10 short clips => email newsletter => social posts. Multiplies reach without multiplying effort.
- Creator tax management (T2125 Canada / Schedule C US): track every business expense. Most creators overpay tax in year 1 by failing to track deductions.

**Top experts:** Pat Flynn (Smart Passive Income), Justin Moore (Creator Wizard), Jenna Kutcher (Goal Digger)

---

### 6. Local Service (HVAC, wellness, real estate, home services)

**Revenue model:** Job-based revenue, often seasonal. Gross margins: 30-50% before overhead. Target 15-25% net profit margin. Recurring contracts (maintenance plans, memberships) transform lumpy revenue into predictable MRR.

**Lead generation channels that work:**
- Google Local Services Ads (LSAs) -- pay-per-lead; Google Screened badge builds trust. 2025 update: AI-driven ranking, responsiveness and review strength are primary signals.
- Google Business Profile optimization + local SEO -- high-intent free traffic
- Referral programs -- highest-quality leads, lowest CAC
- Combining LSAs + SEO yields 40% lower overall CAC than either alone (ServiceTitan 2025)

**Pricing conventions:**
- Flat-rate pricing (vs hourly) increases AOV and customer trust
- Maintenance plan / membership (29-99/mo) converts one-time buyers to recurring revenue
- Review acquisition: ask within 24 hours of job completion while experience is fresh

**Local service-specific frameworks:**
- Job-costing: track labor + materials + overhead per job. Know actual margin per service line before scaling. Many local operators grow revenue while margin compresses because job-costing is absent.
- Reputation management: 4.8+ Google rating is the threshold for LSA premium ranking. Build a systematic ask-review-respond process into every job completion workflow.

**Top experts:** Tommy Mello (A1 Garage Door), Mike Michalowicz (Profit First applied to trades), Ken Goodrich (HVAC operations)

---

## Section 4: Lead Management Framework

### 4.1 Lead Capture

**Inbound:**
- Lead magnet: offer a high-value artifact (audit, calculator, template, mini-course) in exchange for contact info. Hormozi rule: the lead magnet should be so good the prospect feels foolish saying no.
- Contact form: reduce fields to name + email + one qualifying question. Every additional field reduces conversion.
- Webinar / workshop opt-in: highest commitment signal; converts better to paid than passive downloads.
- Referral program: structured ask at peak satisfaction moment (post-win, post-delivery).

**Outbound:**
- Cold email (Predictable Revenue -- Aaron Ross): Spear outreach. 3-step sequence: pattern-interrupt => permission ask => resource share. Target 20% reply rate from warm; 3-5% from cold.
- LinkedIn DMs: personalized; reference specific content they published.
- Cold calling: still works for local service and high-ticket B2B; use NEPQ framework (Jeremy Miner).

**Lead magnet quality test:** Would your ideal client pay a meaningful amount for this if it were not free? If no, rebuild it.

### 4.2 Lead Qualification

Use the right framework for your deal size:

| Framework | Best For | Core Criteria |
|-----------|----------|---------------|
| BANT | Sub-25K, single decision-maker, fast cycle (<30 days) | Budget, Authority, Need, Timeline |
| CHAMP | Consultative mid-market (10-50K) | Challenges first, then Authority, Money, Prioritization |
| MEDDIC | Enterprise / complex multi-stakeholder (50K+) | Metrics, Economic Buyer, Decision Criteria, Decision Process, Identify Pain, Champion |

**For solo founders at OASIS AI stage (500-2K/mo retainers):** CHAMP is the practical default. Lead with their Challenge, confirm they are the decision-maker, then confirm budget and priority. Avoids the awkward budget-first opener that kills rapport (leadsatscale.com, syncgtm.com 2025 confirm this pattern).

**ICP fit scoring (build into lead_engine.py):** Score 0-10 across: industry match, company size, decision-maker access, urgency signal, budget signal, geographic fit. Threshold: 7+ = MQL, 9+ = priority.

**Intent signals to weight:** opened email 3+ times, visited pricing page, booked a meeting, asked a specific technical question.

### 4.3 Lead Nurture

**The give-ask cycle (Hormozi):** Consistently deliver value before asking for the sale. Goodwill compounds.

**Sequence architecture:**
- Day 0: Deliver lead magnet + welcome message (personal, not template-feeling)
- Day 2: Quick win content (how to apply one thing from the magnet)
- Day 4: Social proof (case study or outcome story -- specific, not vague)
- Day 7: Address the number-one objection your ICP has (name it, answer it directly)
- Day 10: Soft CTA (invitation to conversation, low-pressure)
- Day 14: Re-engagement or breakup email (Is this still relevant for you?)

**Dean Jackson 9-word email** (validated by Hormozi): Are you still looking to [4-word desire]? -- highest open and reply rate of any nurture email. Use at day 21+ for stale leads.

**Content velocity:** Frequency beats perfection. One email per week is the minimum to maintain mental availability.

### 4.4 Lead Handoff (MQL to SQL)

| Stage | Definition | SLA |
|-------|-----------|-----|
| MQL (Marketing Qualified Lead) | ICP fit >= 7, engaged with 2+ pieces of content | Contacted within 24 hours |
| SQL (Sales Qualified Lead) | MQL + CHAMP criteria confirmed | Discovery call booked within 48 hours |
| Opportunity | Discovery call completed, proposal sent | Follow-up within 24 hours of proposal send |
| Closed-Won | Contract signed / deposit received | Onboarding kickoff within 72 hours |
| Closed-Lost | Dead after 3 follow-ups or explicit no | Re-engage in 90 days or long-term nurture |

### 4.5 CRM Architecture for Solo Founders

| Option | Price | Best For | Limitation |
|--------|-------|----------|-----------|
| HubSpot Free | 0 (1,000 contacts) | Getting started | 1K contact cap; aggressive upsell |
| Attio | 0 up to 3 users / 34/user/mo paid | Technical founders; API-first pipeline | No native email sequencing |
| Pipedrive | 14/seat/mo | Clean pipeline focus | Less automation at starter tier |
| Custom Supabase | Supabase instance cost | Full control; integrates with existing stack | Build time; ongoing maintenance |
| Notion | 8-16/mo | Personal tracking only | Not scalable; no automation |

**Recommendation:** Start with HubSpot Free. When leads exceed 1K or automation needs outgrow free tier, migrate to Attio (API-first -- best for agent integration). Buyers already running Supabase: lead_engine.py pattern is highest-leverage. (forecastio.ai, stacksync.com 2025 comparison confirms these tradeoffs.)

### 4.6 Automation Rules

- Routing: New lead => ICP score (automated) => if score >= 7, assign Priority tag + Telegram notify => if score < 7, enter long-term nurture sequence
- Re-engagement: Stale lead after 30 days => 9-word email => if no reply in 7 days => cold list => 90-day re-engagement cadence
- Stale-lead handling: Never delete. Mark as Long-Term Nurture. Monthly one-touch value drop (no CTA). They often convert 6-18 months later.
- Booking confirmation: Auto-send calendar invite + prep questions + 24-hour reminder + 1-hour reminder. No-show rate drops approximately 40% with this sequence.

### 4.7 Key Lead Metrics

| Metric | Formula | Target (Agency/Consulting stage) |
|--------|---------|----------------------------------|
| CPL (Cost Per Lead) | Spend / Leads | <50 organic; <200 paid |
| CPQL (Cost Per Qualified Lead) | Spend / Qualified Leads | <500 |
| CAC | Total sales+marketing spend / New customers | <3-month LTV |
| Show rate | Booked calls that actually show | >70% (industry: 60-80%) |
| Close rate | Proposals sent => won | 25-40% warm; 10-20% cold |
| Time-to-close | First contact => signed | 7-21 days for 1-5K; 30-90 days for 10K+ |
| LTV by source | Revenue per customer by acquisition channel | Track quarterly; kill channels with LTV<3x CAC |

### 4.8 Authoritative Sources for Lead Management

1. Aaron Ross -- Predictable Revenue (outbound specialization model; Seeds/Nets/Spears lead types; still canonical in 2025)
2. Chet Holmes -- The Ultimate Sales Machine (Dream 100 prospect strategy; stadium pitch; nurtured pipeline as company asset)
3. Alex Hormozi -- 100M Leads (warm outreach benchmarks; give-ask cycle; lead magnet construction; 9-word email)
4. David Sandler -- Sandler Selling System (pain discovery methodology; no is OK qualification; prevents chasing unqualified leads)
5. Jason Lemkin -- SaaStr (pipeline rules for B2B SaaS; never let a deal go dark; ARR-stage hiring triggers)

---

---

## Section 5: Marketing Research Framework

**Purpose:** Know the market before building. Every agent vertical pack ships with audience intelligence baked in. This section defines the research stack that informs CMO agent playbooks, ICP definitions, content strategy, and keyword targeting.

### Audience Discovery

Primary method: ethnographic listening before any quantitative work.

**Reddit ethnography** â€” Search subreddits where your target vertical complains (r/smallbusiness, r/HVAC, r/ecommerce, r/freelance). Mine thread titles for exact-match language. The words people use to describe their own pain are the words your copy must use. Tool: Reddit search + Exploding Topics for trending threads.

**Mom Test (Rob Fitzpatrick, 2013)** â€” The canonical framework for customer interviews that do not produce bias. Three rules: talk about their life (not your idea), ask about specifics in the past (not hypotheticals), shut up and listen. Mandatory reading for every vertical pack build. ICP profiles in personal/brands/ must be validated against at least 3 real conversations before launch.

**SparkToro** â€” Audience intelligence tool. Given an ICP keyword, returns: what they read, who they follow, which podcasts they listen to, which sites they visit. Paid tier at 50/mo unlocks demographic overlays. Free tier gives 5 searches/mo. Use for CMO agent audience_profiles.

**SimilarWeb** â€” Competitive traffic intelligence. Enter a competitor domain, get: monthly visits, traffic sources (organic, paid, direct, referral, social), top keywords, audience geography. Free tier: 5 lookups/mo, 3 months history. Use for competitor_teardown reports in competitive-intelligence skill.

**Wayback Machine teardown methodology** â€” Pull snapshots of competitor landing pages at 6-month intervals. Compare: headline evolution, offer changes, CTA shifts, pricing page revisions. Reveals what is working (they keep it) and what failed (they changed it). Zero cost. Apply to top 3 competitors per vertical.

### Keyword Research Stack

**Free tools:**
- Google Keyword Planner â€” volume + CPC estimates, intent inference from ad group clustering
- Google Search Console â€” actual impressions/clicks for existing content, unsampled
- Ubersuggest (free tier) â€” keyword ideas, difficulty scores, SERP preview
- AlsoAsked â€” question-format keywords from People Also Ask boxes; maps to FAQ and AEO content

**Paid tools (recommended at scale):**
- Ahrefs (99/mo Lite) â€” backlink analysis, keyword difficulty, content gap vs competitors, rank tracker
- Semrush (129/mo Pro) â€” broader keyword database, on-page SEO audit, social listening add-on

**For each vertical pack:** CMO agent ships with a pre-seeded keyword cluster covering: primary commercial intent terms, 10-15 long-tail FAQ terms, 5 AEO-formatted questions (Who/What/When/Where/Why/How format).

### AEO and LLM Visibility

Answer Engine Optimization is no longer optional. As of 2025:
- 1 in 10 US internet users now search AI-first (ChatGPT, Perplexity, Claude) before using Google (Statista, 2025)
- 16.4% of Google desktop queries now show AI Overviews in the SERP (SparkToro/Datos, Q1 2025)
- AEO-optimized content shows 40% higher AI citation rate vs standard SEO content (Tryprofound, Conductor, Amsive research, 2025)

**AEO implementation for CMO agent:**
- Every pillar article includes a dedicated FAQ section with question-format H2 headers
- Answers are self-contained: 40-60 words, factually verifiable, no jargon
- Schema markup: FAQPage, HowTo, Article structured data on every content page
- Topical authority clusters: 1 pillar page + 8-12 supporting cluster articles per core topic
- Citation bait: original data, proprietary frameworks, named methodologies (LLMs cite named frameworks disproportionately)

**LLM visibility monitoring:** Track brand mentions in ChatGPT/Perplexity responses monthly. Prompt: "What are the best tools for [target keyword]?" If the product does not appear, identify which citations do appear and reverse-engineer their content format.

### Trend Monitoring

- **Exploding Topics** â€” emerging trend detection before mainstream adoption; free tier, 5 searches/mo
- **Google Trends** â€” relative search volume over time, geographic breakdowns, related queries; free
- **Feedly** â€” RSS aggregation for industry publications; curate by vertical; 8/mo Pro removes limits
- **Twitter/X Lists** â€” follow 20-30 vertical-specific practitioners; surface emerging conversations before they become search volume
- **Product Hunt** â€” new tool launches in adjacent categories; signals what buyers are shopping for

CMO agent heartbeat: weekly trend scan surfaces 3 trend signals â†’ CEO agent evaluates for strategic relevance â†’ logged to pulse.

### Authoritative Sources

1. **April Dunford** â€” Positioning framework (Obviously Awesome, 2019). The standard for competitive differentiation. Positioning canvas: competitive alternatives, unique attributes, value for target, characteristics of best-fit buyers. Every vertical pack ICP must be run through this framework.

2. **Rob Fitzpatrick** â€” Customer discovery (The Mom Test, 2013). Prevents building for a market that does not exist. Required for new vertical pack validation.

3. **Byron Sharp** â€” Evidence-based marketing (How Brands Grow, 2010). Core finding: penetration beats loyalty; mental and physical availability drive share. Informs CMO agent reach-vs-retention balance in content calendar.

4. **Mark Ritson** â€” Marketing effectiveness research; Mini MBA in Marketing. Distinguishes brand-building (long, 60%) from activation (short, 40%). Informs CMO agent budget allocation playbooks.

5. **Rand Fishkin** (SparkToro) â€” Modern audience research methodology; debunks SEO myths; AEO transition insights. Substack and SparkToro blog are primary sources for search behavior data cited above.


---

## Section 6: Pricing the Product Itself

**Purpose:** Anchor price against real market comparables. Every buyer mentally compares this product to something they already know. That comparison must be controlled.

### Market Comparables

| Comparison | Monthly Cost | What You Get |
|---|---|---|
| Fractional CFO (human) | 3,000 - 15,000 | 1-2 days/week, no institutional memory, turnover risk |
| Fractional CMO (human) | 5,000 - 20,000 | Strategy only, no execution, no content production |
| Fractional CEO advisor | 2,000 - 10,000 | Calls only, no operating system, no automation |
| Knolli AI agent platform | 39/mo | Pre-built agents, no customization, no vertical depth |
| Gumloop automation platform | 49 - 199/mo | Workflow automation only, no agent intelligence |
| n8n self-hosted | 20 - 50/mo | Workflow engine only, no reasoning, no memory |
| HubSpot CRM | 15+/user/mo | CRM only, no executive function, no strategy |
| Attio CRM | 34+/user/mo | CRM only, no content, no finance |
| Notion workspace | 8 - 16/mo | Documentation only, no execution |
| Agency AI retainer | 800 - 3,000/mo | Deliverables only, no institutional learning |

**The anchor:** A human fractional C-Suite (CFO + CMO + CEO advisor) costs 10,000 - 45,000/mo. Business in a Box delivers equivalent strategic function at 497 one-time (Starter tier) or 497/mo (Fractional tier) â€” a 95%+ cost reduction with sovereign ownership and no turnover.

### Validated Pricing Structure

| Tier | Price | What Is Included | Completeness Score |
|---|---|---|---|
| Starter | 497 one-time | 3 core agents (CEO, CFO, CMO), 1 vertical pack, install guide, community support | 7/10 |
| Pro | 1,497 one-time | Starter + Aura life agent, 2 additional vertical packs, 1-hour onboarding call, priority support | 9/10 |
| Managed Install | 3,997 one-time | Pro + CC installs on your machine, configures env, runs first week with you | 10/10 |
| Fractional | 497/mo recurring | Managed Install + monthly 1-hour strategy call + priority skill requests | 10/10 ongoing |

**Rationale for Starter at 497:**
- Below the psychological pain threshold for a solo founder who has never paid more than 99/mo for a tool
- Priced as a one-time tool purchase, not a subscription â€” reduces objection surface
- One vertical pack limits scope, creates a natural upgrade path to Pro
- Validated: info-product pricing research (Hormozi, Kern) shows 297-997 is the highest-converting range for digital products targeting operators

**Rationale for Fractional at 497/mo:**
- Anchored against the cheapest fractional human option (typically 3,000/mo minimum)
- Positions as a 6:1 value vs the next cheapest alternative
- Monthly recurring creates compounding revenue without ongoing delivery overhead beyond 1 call

### Value Anchoring Script (CMO Agent Uses This)

"You are currently spending [X] per month on [HubSpot / agency / consultant]. Business in a Box delivers CEO-level strategic planning, CFO-level cashflow modeling, and CMO-level campaign execution â€” permanently, on your machine, with no monthly seat fees â€” for a single 497 payment. If it saves you 3 hours this week, it paid for itself."

Hormozi give-ask cycle: deliver one concrete insight before anchoring price. Dean Jackson 9-word email reactivation: "Are you still looking for help with [specific pain]?" Aaron Ross Nets model: content-driven inbound â†’ warm leads who already believe, making price anchoring frictionless.

### What Would Make This Look Amateur (Anti-Checklist)

- Pricing with no comparison to alternatives â€” buyer invents their own (usually wrong) anchor
- Tier names that do not communicate the transformation (avoid: Basic, Standard, Premium)
- Missing a one-time option â€” subscription-only triggers cancellation anxiety before purchase
- No social proof at checkout â€” testimonial, case study, or CC usage stats must be visible
- Vague deliverables â€” every tier must list exactly what files, agents, and support are included
- No upgrade path shown â€” Starter buyer must see Pro is available so the initial purchase feels safe
- Support described as "community" without defining what that means â€” specify: Discord, async Q+A, response time

### Pricing Validation Criteria (Before Launch)

Before setting final prices, validate:
1. 5 target buyers interviewed â€” what did they last spend on a business tool? What would they pay for a full AI exec team?
2. Comparable products surveyed â€” is Starter undercutting the market in a way that signals low quality?
3. Managed Install scoped â€” what is CC time cost per install? Price must cover that at target margin.
4. Fractional modeled â€” how many Fractional clients is sustainable before delivery quality degrades?

First 5 beta buyers: offer at 50% discount in exchange for a detailed case study and permission to use their results in marketing. This generates both proof and pricing validation data simultaneously.


---

## Obsidian Links

[[brain/PRODUCT_ARCHITECTURE]] | [[brain/CANONICAL_ROLES]] | [[brain/C_SUITE_ARCHITECTURE]]
[[skills/self-improvement-protocol/SKILL]] | [[brain/CROSS_AGENT_AWARENESS]] | [[brain/SHARED_DB]]
