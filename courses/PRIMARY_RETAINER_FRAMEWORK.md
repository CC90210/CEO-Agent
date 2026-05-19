---
tags: [course, framework, onboarding]
---

# OASIS AI Solutions — Build Your Own AI Agency

> **What this is:** The exact system Conaugh McKenna used to build OASIS AI Solutions from zero to recurring revenue. Follow the modules in order — each builds on the last. By the end, you have a running AI agency with tools, clients, and monthly income.
>
> **How it works:** Self-paced modules + direct access to Conaugh for coaching calls. You do the work, you bring the questions, we figure it out together.
>
> **Your investment:** $97/month (price increases to $147 soon — you're locked in at the lower rate).

---

## MODULE 1: Foundation — Your AI Command Center (Week 1)

**Goal:** Set up the same AI-powered operating system that runs OASIS AI Solutions.

### 1.1 Install Your Tools
- [ ] **Anti-Gravity IDE** — Your primary AI coding environment ([download](https://www.antigravity.dev))
  - Why: Built-in AI chat, MCP server support, workspace-aware context
  - Setup: Install → open your project folder → enable MCP in settings
- [ ] **Claude Code CLI** — Terminal-based AI assistant
  - Install: `npm install -g @anthropic-ai/claude-code`
  - Auth: `claude` → `/login` → sign in with Claude Pro/Max account
  - Remote access from phone: `claude remote-control --name "My Agency"`
- [ ] **Git + GitHub** — Version control (non-negotiable)
  - Create a GitHub account if you don't have one
  - Install Git, configure SSH keys
  - Every project gets a repo. Every change gets a commit.
- [ ] **Node.js 20+** and **Python 3.11+** — Runtime environments

### 1.2 Create Your CLAUDE.md
This is the brain of your AI assistant. It tells Claude who you are, what you're building, and how to help you.

**Template to start with:**
```markdown
# MY AGENCY — Claude Code Instructions

## Identity
- **Agency Name:** [Your Agency Name]
- **Owner:** [Your Name]
- **Niche:** [Your target market — e.g., HVAC, dental, real estate]
- **Stack:** Next.js, Supabase, Vercel, Stripe, n8n

## Goal
[Your revenue target and timeline — e.g., "$3,000/month by Q3 2026"]

## Rules
1. Answer questions first, then work
2. Never hardcode API keys — use .env files
3. Verify work before shipping (run builds, check outputs)
4. Keep it simple — no over-engineering
```

**Why this matters:** Every time you open Claude Code in your project, it reads this file. It's your AI's operating manual. As you grow, this file grows with you.

### 1.3 Set Up Supabase (Your Free Database)
- [ ] Create account at [supabase.com](https://supabase.com) (free tier = 2 projects)
- [ ] Create your first project (this is your agency's backend)
- [ ] Save your project URL and anon key in `.env.local`
- [ ] Learn the basics: Tables, Row Level Security (RLS), SQL editor

### 1.4 Set Up Stripe (Your Payment Processor)
- [ ] Create Stripe account at [stripe.com](https://stripe.com)
- [ ] Complete identity verification (takes 1-2 days)
- [ ] Set up your first product: "AI Automation Retainer" → recurring monthly price
- [ ] Create a payment link (Dashboard → Payment Links → New)
- [ ] **Pro move:** Create links with setup fee + recurring (e.g., $500 setup + $300/month):
  - This requires the API — ask Conaugh and we'll walk you through it on a call
- [ ] Save your Stripe secret key in `.env.local` (NEVER commit this file)

**Stripe pricing psychology:**
- Always have a setup fee — it signals professionalism and covers your onboarding time
- Monthly retainers > one-time projects (recurring revenue is the goal)
- Offer 2 tiers: Basic ($297/mo) and Premium ($597/mo). Most pick the middle.

---

## MODULE 2: Your First Automation Stack (Week 2-3)

**Goal:** Build the core tools every AI agency needs — without paying for expensive SaaS.

### 2.1 n8n — Your Automation Engine
- [ ] Self-host n8n on a VPS (Hostinger, Railway, or DigitalOcean — ~$5-10/month)
  - Or use n8n Cloud free tier (limited but good for learning)
- [ ] Build your first workflow: **Inbound Lead Qualifier**
  - Trigger: Webhook (from your website contact form)
  - Step 1: Save lead to Supabase
  - Step 2: Send yourself a notification (email or Telegram)
  - Step 3: Auto-reply to the lead with a booking link
- [ ] Build your second workflow: **Content Scheduler**
  - Trigger: Cron (daily at 9am)
  - Step 1: Pull today's content from Supabase content_calendar table
  - Step 2: Post to social media via Late API or direct platform APIs

### 2.2 The Lead Engine Pattern
Every agency needs a way to track leads. Here's the schema:

```sql
-- Run this in your Supabase SQL editor
CREATE TABLE leads (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  name TEXT NOT NULL,
  email TEXT,
  phone TEXT,
  source TEXT DEFAULT 'manual',
  status TEXT DEFAULT 'new' CHECK (status IN ('new','contacted','qualified','proposal','won','lost')),
  score INTEGER DEFAULT 0,
  notes TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Enable Row Level Security (ALWAYS do this)
ALTER TABLE leads ENABLE ROW LEVEL SECURITY;
```

### 2.3 The Booking System
Stop going back and forth on scheduling. Set up:
- [ ] **Option A:** Cal.com (free tier, self-hostable)
- [ ] **Option B:** Build your own with Supabase (we provide the schema)
- [ ] Embed your booking link in every client communication

### 2.4 Email Automation (Zero Cost)
- [ ] Gmail SMTP — 500 emails/day for free
- [ ] Build email templates in Supabase (subject, body, variables)
- [ ] Create a 3-email nurture sequence:
  1. Welcome + what to expect (immediately)
  2. Case study or value demonstration (day 3)
  3. Call-to-action + booking link (day 7)

---

## MODULE 3: Finding Clients — Outreach That Actually Works (Week 3-4)

**Goal:** Get your first 3-5 discovery calls booked.

### 3.1 The NEPQ Sales Framework (Jeremy Miner)
**This is the only sales methodology you need.** Traditional sales = pitching. NEPQ = asking questions that make prospects sell themselves.

**The 6 stages:**
1. **Connecting** — Pattern interrupt. "I'm not sure if this is even relevant to you, but..."
2. **Situation** — Understand their world. "How are you currently handling [X]?"
3. **Problem Awareness** — Surface the pain. "What happens when [X] falls through the cracks?"
4. **Solution Awareness** — Let them imagine. "If you could automate [X], what would that free up?"
5. **Consequence** — Stakes. "What does it cost you every month to keep doing it manually?"
6. **Commitment** — Natural close. "Would it make sense to explore what this would look like for you?"

**Key rules:**
- NEVER lead with your product. Lead with THEIR problem.
- "I'm not sure if..." kills sales resistance instantly.
- Ask, don't tell. The prospect should talk 70% of the time.
- Your tone matters more than your words (curious > confident > confused > challenging).

### 3.2 Where to Find Leads
- [ ] **Google Maps scraping** — Search "[niche] + [city]", extract business info
- [ ] **LinkedIn** — Connect with business owners in your niche (personalized notes only)
- [ ] **Skool communities** — Engage genuinely, DM people who post about AI/automation
- [ ] **Local networking** — BNI groups, Chamber of Commerce, industry meetups
- [ ] **Cold email** — 50 personalized emails/week (not spam — real research per lead)

### 3.3 Cold Outreach Templates

**Cold Email (Pattern Interrupt Style):**
```
Subject: quick question about [their business name]

Hey [First Name],

I was looking at [their business] and honestly I'm not sure if this
would even be relevant to you — but I noticed [specific observation
about their business, e.g., "you're still using a contact form that
goes to a generic inbox"].

We've been helping [niche] businesses automate [specific process] and
it's been saving them about [X hours/week or $X/month].

Would it make sense to hop on a 15-min call to see if there's a fit?
Either way, no pressure.

— [Your Name]
[Your Agency]
```

**Why this works:** "I'm not sure if this would even be relevant" = zero pressure. Specific observation = you did your homework. Short = respect for their time.

### 3.4 Your Pricing Framework

| Tier | Monthly | Setup Fee | What They Get |
|------|---------|-----------|---------------|
| **Starter** | $297/mo | $500 | 1 automation workflow, basic CRM setup, email support |
| **Growth** | $597/mo | $1,000 | 3 workflows, CRM + lead scoring, weekly check-in call |
| **Scale** | $997/mo | $2,000 | Unlimited workflows, full automation audit, priority support, monthly strategy call |

**Rules:**
- Always charge a setup fee (covers your onboarding time + shows professionalism)
- Monthly retainers only — no hourly, no project-based (unless $5k+ one-time)
- Stripe payment links with setup fee + recurring (we set this up in Module 1)
- 3-month minimum commitment (protects your revenue)

---

## MODULE 4: Delivering Results — The Agency Playbook (Week 4-6)

**Goal:** Systematize client delivery so it takes minimal effort per client.

### 4.1 Client Onboarding SOP
When a new client pays:
1. [ ] Send welcome email (automated via n8n)
2. [ ] Schedule kickoff call (30 min — use your booking system)
3. [ ] Create their project in Supabase (separate schema or row-level isolation)
4. [ ] Set up their n8n workflows (fork from your templates)
5. [ ] Connect their accounts (Google, social media, CRM)
6. [ ] Deliver first automation within 7 days (speed = trust)

### 4.2 The Automation Menu
Pre-built workflows you can deploy for any client in under 2 hours:

| Automation | Time to Deploy | Client Value |
|-----------|---------------|--------------|
| **Inbound Lead Qualifier** | 30 min | Instant lead response + routing |
| **Appointment Reminder Sequence** | 45 min | 30% reduction in no-shows |
| **Review Request Automation** | 30 min | 5-star reviews on autopilot |
| **Social Media Scheduler** | 1 hour | Consistent posting without manual work |
| **Invoice + Payment Follow-up** | 45 min | Faster collections, less awkward chasing |
| **Client Reporting Dashboard** | 2 hours | Monthly reports generated automatically |
| **Chatbot / FAQ Responder** | 1 hour | 24/7 customer support on their website |

### 4.3 Monthly Client Maintenance
- [ ] Weekly: Check workflow execution logs (are automations running?)
- [ ] Monthly: Send performance report (leads generated, emails sent, time saved)
- [ ] Quarterly: Strategy call — identify new automation opportunities (upsell)

### 4.4 Scaling Beyond Yourself
When you hit 5+ clients:
- Use **Claude Code + CLAUDE.md** to automate your own operations
- Build internal dashboards to monitor all client workflows from one place
- Consider hiring a VA for client communication ($5-10/hr, train them on your SOPs)
- Every repeated task becomes an SOP → then an automation → then it runs itself

---

## MODULE 5: Building Your Platform — Apps That Generate Revenue (Week 6-8)

**Goal:** Go beyond services. Build products that earn while you sleep.

### 5.1 Your Agency Website
- [ ] **Stack:** Next.js 14 + Tailwind + Vercel (free hosting)
- [ ] **Pages:** Home, Services, About, Contact, Blog
- [ ] **Lead capture:** Contact form → Supabase → n8n → notification + auto-reply
- [ ] **Social proof:** Client logos, testimonials, case studies
- [ ] Deploy on Vercel (free tier handles most agency traffic)

### 5.2 SaaS Micro-Products
Once you've built 3+ automations for clients, you'll see patterns. Turn those into products:
- **Lead scoring tool** → charge $49/mo
- **Review management dashboard** → charge $29/mo
- **Appointment booking page** → charge $19/mo

**Stack for all of these:** Next.js + Supabase + Stripe + Vercel = $0 infrastructure cost.

### 5.3 OASIS GitHub Repos You Can Fork
These are real production apps built by Conaugh at OASIS AI. Study the code, fork them, adapt for your niche:

| Repo | What It Is | Learn From It |
|------|-----------|---------------|
| **CC Funnel** | Lead capture funnel (Next.js + Supabase) | How to build funnels |
| **TIKTIK** | Attendance tracker (Next.js + Supabase) | Full CRUD application pattern |
| **Nostalgic Requests** | Music request SaaS (Stripe Connect) | Marketplace/creator payments |
| **Grape Vine Cottage** | Marketing site (React + Shadcn/ui) | Modern design systems |

---

## MODULE 6: AI Agent Architecture — The Advanced Playbook (Week 8-12)

**Goal:** Build an AI system that runs your agency autonomously.

### 6.1 The Brain Loop (10-Step Reasoning)
This is how Bravo (CC's AI) processes every task:
1. **ORIENT** — Load context (who am I, who is the user, what's the current state)
2. **RECALL** — Check memory for relevant past experience
3. **ASSESS** — What do I know? What am I uncertain about?
4. **PLAN** — Generate 2-3 approaches, rank them
5. **VERIFY** — Cross-check against known patterns and mistakes
6. **EXECUTE** — Do the work, one step at a time
7. **REFLECT** — Did it work? What went wrong?
8. **STORE** — Save learnings to memory
9. **EVOLVE** — Should this become a reusable skill?
10. **HEAL** — Clean up, update state, check for broken references

### 6.2 Multi-Agent Orchestration
Instead of one AI doing everything, split work across specialists:
- **Architect** — System design decisions
- **Coder** — Implementation
- **Reviewer** — Quality checks before shipping
- **Researcher** — Market intel and documentation lookup
- **Content Creator** — Brand voice copywriting

### 6.3 Memory Systems
Your AI needs to remember across sessions:
- **State file** — What's happening right now (ephemeral)
- **Long-term memory** — Facts that persist (verified, scored by confidence)
- **Mistakes log** — What went wrong (prevents repeating errors)
- **Patterns log** — What works (promotes to SOPs after 3+ successes)

### 6.4 Self-Healing
Build AI that fixes itself:
- Memory consistency checks (no contradictions)
- Automatic junk file cleanup
- MCP server health monitoring
- Git state verification

---

## MODULE 7: Sales Mastery — Closing $297-$997/mo Retainers (Ongoing)

**Goal:** Never run out of clients.

### 7.1 The Discovery Call Framework
Every call follows this structure (30 min max):

1. **Pattern interrupt opener** (2 min)
   - "Before we dive in — I'm not even sure if what we do is a fit for you. Can I ask a few questions to find out?"

2. **Situation questions** (5 min)
   - "Walk me through how you currently handle [lead follow-up / scheduling / reviews]"
   - "How many [leads / appointments / reviews] are you getting per month?"

3. **Problem awareness** (8 min)
   - "What happens when a lead comes in at 10pm and nobody responds until morning?"
   - "How much time does your team spend on [manual process] per week?"

4. **Solution awareness** (5 min)
   - "What if every lead got a personalized response within 60 seconds, 24/7?"
   - "If you could get back [X hours/week], what would you do with that time?"

5. **Consequence + ROI** (5 min)
   - "What's the cost of losing even 2-3 leads per month to slow follow-up?"
   - "At your average deal size of $[X], that's $[Y] per month in lost revenue"

6. **Commitment** (5 min)
   - "Based on what you've told me, I think our [Growth/Scale] plan would be the right fit"
   - "The setup fee is $[X] and then $[Y]/month. Want me to send over the payment link?"

### 7.2 Objection Handling

| Objection | Response |
|-----------|----------|
| "I need to think about it" | "Totally fair. What specifically are you weighing? Sometimes I can help clarify." |
| "It's too expensive" | "I get it. Out of curiosity — what's it costing you right now to do this manually? Usually it's way more than $297/mo when you add up the hours." |
| "I'm not sure about AI" | "That's actually why most of our clients come to us — they don't want to figure out AI themselves. We handle everything. You just see the results." |
| "Can I see a demo?" | "Absolutely. I'll set up a quick demo specific to your business. But just so I build the right thing — what's the #1 process you'd want automated?" |
| "I already have someone for that" | "Nice, how's that going? What's working and what's not? Sometimes we complement what they're doing rather than replace it." |

### 7.3 Follow-Up Cadence
After a discovery call (if they didn't close):
- **Day 1:** Send recap email + payment link
- **Day 3:** "Hey [name], just checking in — any questions from our call?"
- **Day 7:** Share a relevant case study or result
- **Day 14:** "Last follow-up — the $97 setup discount expires this week"
- **Day 30:** Move to nurture list (monthly value emails)

---

## WEEKLY RHYTHM

| Day | Activity |
|-----|----------|
| **Monday** | Review pipeline, send 10 outreach messages, plan content |
| **Tuesday** | Client delivery work (build/optimize automations) |
| **Wednesday** | Content creation (1 post minimum), community engagement |
| **Thursday** | Discovery calls, follow-ups, proposals |
| **Friday** | Admin (invoicing, reporting), learning/skill building |
| **Weekend** | Optional: batch content, strategic thinking, rest |

---

## TOOLS CHECKLIST

### Free / Included with OASIS AI
- [x] Anti-Gravity IDE (free)
- [x] Claude Code CLI (needs Claude Pro $20/mo or Max $100/mo)
- [x] Supabase (free tier — 2 projects)
- [x] Vercel (free tier — 3 projects)
- [x] GitHub (free)
- [x] Gmail (free — 500 emails/day)
- [x] n8n (self-hosted ~$5/mo or cloud free tier)
- [x] Direct coaching from Conaugh (OASIS AI founder)

### Recommended (Pay As You Grow)
- [ ] Stripe ($0 until you process payments — 2.9% + $0.30 per transaction)
- [ ] Custom domain ($12/year)
- [ ] VPS for n8n ($5-10/month — Hostinger, Railway, or DigitalOcean)
- [ ] Claude Pro or Max ($20-100/month — for Claude Code + API access)
- [ ] Late.com ($0-19/month — social media scheduling)

**Total startup cost: $25-130/month** (vs. $500+/month for traditional SaaS stack)

---

## ACCOUNTABILITY SYSTEM

### Weekly Check-In (Post in Community)
Every Friday, send Conaugh a quick update:
1. **Wins this week:** What did you ship, close, or learn?
2. **Outreach numbers:** How many messages sent? Calls booked?
3. **Blockers:** What's stopping you? (We solve these on our next call)
4. **Next week's focus:** One specific goal

### Monthly Milestones

| Month | Target | Evidence |
|-------|--------|----------|
| **Month 1** | AI tools set up, first automation built, 20 outreach messages sent | Screenshot of working automation |
| **Month 2** | 3+ discovery calls, first proposal sent, website live | Link to website + Stripe account |
| **Month 3** | First paying client ($297+/mo retainer) | Stripe payment screenshot |
| **Month 4** | 2-3 clients, $500+/mo MRR | Stripe dashboard |
| **Month 5** | Refined delivery SOP, 3+ clients, $1,000+/mo | Client testimonial |
| **Month 6** | 5+ clients, $2,000+/mo, considering first hire/VA | Growth plan posted |

---

## FAQ

**Q: Do I need to know how to code?**
A: Not to start. Anti-Gravity IDE and Claude Code write the code for you. But you'll pick up the basics naturally as you build. By month 3, you'll understand enough to be dangerous.

**Q: What niche should I pick?**
A: Start with local service businesses (HVAC, dental, real estate, wellness). They have money, hate technology, and desperately need automation. Pick one niche and go deep.

**Q: How fast can I get my first client?**
A: If you follow the outreach framework and do 10+ messages per day, most people book their first discovery call within 2 weeks. First client within 30-60 days.

**Q: What if I get stuck?**
A: That's what the coaching calls with Conaugh are for. Send your question ahead of time so we can solve it on the call.

**Q: Can I really compete with established agencies?**
A: Yes, because you're faster and cheaper. Established agencies charge $3-10k/month with 2-week lead times. You charge $297-997/month and deliver in days, because AI does the heavy lifting. That's your unfair advantage.

---

*Built by Conaugh McKenna — OASIS AI Solutions*
*Only good things from now on.*

## Obsidian Links
- [[courses/INDEX]] | [[brain/CEO_OPERATING_SYSTEM]]


## Related (graph)

- [[courses/INDEX]]
- [[courses/SKOOL_IMAGE_AUDIT]]
