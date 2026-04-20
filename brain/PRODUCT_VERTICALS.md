---
tags: [product, verticals, lead-management, marketing-research, pricing]
---

# PRODUCT VERTICALS -- Business in a Box Research Reference

> Companion to [[PRODUCT_ARCHITECTURE]]. Research layer for the product: canonical agent knowledge, vertical pack contents, lead management best practice, marketing research methodology, and product pricing.
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



Document in each agent UPGRADE.md. For non-technical buyers, the GitHub Actions actions-template-sync marketplace action opens a PR automatically when upstream updates.

### Recommended Distribution Model

V1: Public template repo (GitHub) => buyer forks => buyer customizes personal/ => runs on their machine. Optional managed-setup upsell. See [[PRODUCT_ARCHITECTURE]] for full tier structure and clone flow.

---

## Section 2: Canonical Frameworks Every Agent Role Must Carry

### CEO Agent -- Framework Set

| Framework | Why It Is Non-Negotiable |
|-----------|-------------------------|
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
|-----------|-------------------------|
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
|-----------|-------------------------|
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


## Section 3: Vertical-Specific Extensions

Each vertical = a folder under skills/verticals/[vertical]/ installed on buyer opt-in.

