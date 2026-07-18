---
description: "Operational playbook for CC's client conversations, pitches, and meetings; positioning statements, security model, AI education, and sales plays"
tags: [client-facing, playbook, meeting, security, positioning, shareable]
last_updated: 2026-06-09
freshness_threshold_days: 30
verified: 2026-06-09
---
# 🎯 CLIENT PLAYBOOK — What CC Does, How He's Different, How to Run a Meeting

> Operational reference for CC in client/prospect conversations. Not social media content — this is what you actually say in a meeting, a pitch, or a discovery call. Shareable PDF/Gist when needed.
>
> **Companion docs:** [[memory/DISCOVERY_PLAYBOOK]] — NEPQ discovery questions for the Connect → Situation → Problem → Solution → Commitment phases.
>
> **Use cases:**
> - Pre-meeting prep: skim Section 4 (Meeting Play-by-Play)
> - Prospect asks "who are you?": Section 1 (CC's 30-Second Intro)
> - Prospect asks about security: Section 2 (Security Playbook) — your highest-leverage differentiator
> - Prospect is AI-curious or overwhelmed: Section 3 (AI Industry Map) — educate, don't sell
> - Prospect says "I'll think about it": Section 5 (The 10-Years-Ahead Frame)

---

## 1. CC's 30-Second Intro (memorize this)

**Short version (elevator):**
> "I'm Conaugh McKenna, founder of OASIS AI. I build AI automation for small businesses — the kind of systems a Fortune 500 has, scaled down to run on a laptop. Right now I run seven of them, including my own agency's back office. My edge is that I use AI to do the work most agencies hire three people to do — so I keep costs brutally low and move faster than anyone else in my lane."

**Authority version (for warmer conversations):**
> "I'm a builder. I've shipped 15+ AI-powered apps across real estate, DJ services, field services, compliance, finance, and my own agency. Every one of them runs on a stack I can explain in five minutes and rebuild in five days. The agencies selling you 'AI solutions' are reselling ChatGPT with a logo. I build actual systems."

**Origin story (for content / longer pitches):**
> "I dropped out of university, lived in Japan, Spain, Ireland, Norway. Started OASIS AI because every local business owner I met was being sold 'AI' that was just a chatbot on their website. I built real agents instead — systems that close loops, not flashy demos. Now I run three AI agents full-time: one as CEO (that's Bravo), one as CFO (Atlas), one as CMO (Maven). They run my business while I build."

**Who CC is NOT:**
- NOT a "prompt engineer"
- NOT a "ChatGPT consultant"
- NOT an agency reseller
- NOT selling courses
- NOT a generalist — specializes in **local service businesses + personal brands** monetizing AI automation

---

## 2. Security Playbook — CC's #1 Differentiator

**Why this matters:** Every prospect with real money will ask about security. Every client with real data will ask about insurance. This section is your trump card. Most agencies have no answer. You do.

### The 7-Layer Security Model (what OASIS does that others don't)

| Layer | What OASIS Enforces | What Most Agencies Do |
|-------|---------------------|------------------------|
| **1. Credentials** | Every secret lives in ONE gitignored file (`.env.agents`). Never hardcoded, never in code review, never in an AI prompt. Wrapper scripts inject at runtime. | Credentials pasted into ChatGPT, hardcoded in scripts, shared in Slack. |
| **2. Database access** | Supabase Row-Level Security (RLS) enforced on every table. AI agents have *read-only* access to production by default. | No RLS. Full admin keys in .env files committed to repos. |
| **3. Outbound communication** | Every email/DM routes through one "send gateway" with CASL compliance, cooldown windows, daily caps, and idempotency. No AI can double-send. | Each tool sends independently. Duplicate emails are common. CASL violations are routine. |
| **4. AI access control** | File-guard hooks BLOCK the AI from reading `.env*` files at all. I hit this earlier today — proven in production. | No hook layer. AI reads whatever it's asked to. |
| **5. Dependency scanning** | GitHub Dependabot active on every repo. Auto-PR for critical CVEs. Current CEO-Agent status: 34 vulnerabilities flagged, actioned in triage. | No dependency scanning. Security patches 12-18 months late. |
| **6. Secret rotation** | All API tokens logged with expiry. Supabase Management token rotates every 30 days. Single-file update propagates via wrapper scripts. | Tokens never rotate. When a contractor leaves, the keys stay live. |
| **7. Audit logging** | Every git/npm/Vercel command writes to `tmp/hook_audit.log`. Every send goes to `lead_interactions` table. Every state change goes to Supabase `agent_traces`. | No audit trail. When something breaks, no one knows when it started. |

### Client Security Checklist (give this to them)

Copy-paste this into a shared Google Doc at the start of every engagement:

```
OASIS AI — Client Security Checklist

[ ] Every API key/token has an owner and an expiry date
[ ] Production database has Row-Level Security enabled
[ ] No credentials in source code (I will run a secret scan)
[ ] All outbound email routes through a single logged system
[ ] Dependency vulnerabilities reviewed weekly
[ ] At least one backup exists off the primary cloud
[ ] Access logs for the last 90 days are retrievable
[ ] A "break glass" procedure exists for lost access
[ ] CASL/GDPR compliance verified for jurisdiction
[ ] Insurance policy covers AI-mediated actions (ask your broker)
```

If a prospect can't check 4 of these, they have a security problem. You can fix it.

### The Insurance Conversation

When a client asks "what if the AI screws up and costs me money?":

1. **Name the risk.** "Your business insurance almost certainly doesn't cover AI-mediated actions. That's real — I've had two clients verify it in writing from their brokers."
2. **Name the mitigations.** "That's why I enforce the 7 layers above. You can show any of those to your broker as evidence of commercially reasonable care — which is what insurance underwriters look for."
3. **Name the ceiling.** "No system is 100% secure. I design for contain-and-recover, not prevent-everything. If an agent misfires, we know within 5 minutes and can roll it back."
4. **Close.** "Want me to write a 1-page security memo you can attach to your insurance review?" That's a paid deliverable — $500-$1,500.

---

## 3. AI Industry Map — The Stack (educate prospects, don't sell)

**Framing:** "AI is not one thing. It's a seven-layer cake. Most people only see the frosting."

### Layer 1 — Hardware (the chips)

Where the math actually runs.

- **NVIDIA** — the default. H100/H200 (data center), RTX 5090 (consumer). ~80% market share in AI training.
- **AMD** — MI300X challenger. Cheaper per FLOP, less software maturity.
- **Apple Silicon** — M4 Max / M4 Ultra. Unified memory architecture means running 70B models on a laptop.
- **AI-specific chips** — Google TPU v6, Amazon Trainium 2, Groq LPUs, Cerebras wafer-scale.
- **What this means for clients:** The chip decides the ceiling. An OpenAI API call runs on H100s; your local Ollama runs on whatever you have. Quality of output tracks hardware.

### Layer 2 — Infrastructure (the cloud)

Where the chips live.

- **AWS / Azure / GCP** — the big three cloud providers. Your AI API calls hit their data centers.
- **Vercel / Cloudflare** — where the apps THAT USE AI live. Edge runtime matters for latency.
- **Supabase / Turso / Neon** — databases the AI reads and writes. Choosing one is a 3-year commitment.
- **What this means for clients:** You pay for AI twice — once for the model (Claude/GPT), once for the app that uses it (Vercel). Both matter.

### Layer 3 — Foundation Models (the brains)

What actually does the thinking.

- **Proprietary:** Claude 4.7 (Anthropic), GPT-5.4 (OpenAI), Gemini 3.1 Pro (Google), Grok 4 (xAI).
- **Open source:** Llama 4 (Meta), Mistral, Qwen 3 (Alibaba), DeepSeek.
- **Specialized:** Whisper (audio → text), FLUX / Stable Diffusion (image gen), ElevenLabs (voice synthesis), Suno (music).
- **What this means for clients:** Model choice is an ROI decision. Claude is best for writing + reasoning. GPT is best for code + tool use. Gemini is best for research + images. You match model to task — that's the expertise.

### Layer 4 — Orchestration (the conductors)

What strings models + tools together into agents.

- **Claude Code** (Anthropic's CLI) — what CC uses as primary agent runtime.
- **Cursor / Windsurf / Antigravity** — IDE-integrated agents.
- **Codex CLI** (OpenAI) — dual-AI delegation partner.
- **LangChain / LangGraph / CrewAI / AutoGen** — legacy Python frameworks (heavier, losing ground).
- **n8n / Zapier** — workflow automation (agent-agnostic).
- **What this means for clients:** Running one model is a tool. Orchestrating 4+ models + 10+ tools is an agent. That's where leverage compounds.

### Layer 5 — Memory + Context (the nervous system)

What lets agents remember.

- **Vector databases:** Pinecone, Weaviate, Qdrant, Supabase pgvector.
- **RAG frameworks:** LlamaIndex, Haystack, graph-RAG patterns.
- **Agent memory libraries:** mem0, Letta, claude-mem.
- **Knowledge graphs:** Obsidian (CC's second brain), Neo4j, RDF stores.
- **What this means for clients:** The difference between "smart chatbot" and "agent who knows your business" is memory. Agencies that don't talk about memory don't understand AI.

### Layer 6 — Tools + Integrations (the hands)

What agents can actually touch.

- **MCP (Model Context Protocol)** — Anthropic's open standard, adopted by OpenAI + others. Standardizes tool access.
- **APIs:** Stripe, Supabase, Twilio, Meta Ads, Google Workspace, etc. — each is a tool.
- **Browser automation:** Playwright, Selenium — lets agents use the web.
- **CLI wrappers:** the CLI-Anything methodology CC uses — turn any software into an agent-callable tool.
- **What this means for clients:** An agent with 5 tools can handle customer service. An agent with 50 tools can run your business.

### Layer 7 — Applications (the products)

What the business actually buys.

- **Enterprise:** Salesforce Einstein, HubSpot, Monday.com AI.
- **Vertical:** Industry-specific SaaS (HVAC → ServiceTitan, real estate → Follow Up Boss).
- **Horizontal:** General productivity (Notion AI, Linear, Superhuman).
- **Custom builds:** what CC ships. Owned by the client, not rented from a vendor.
- **What this means for clients:** Buying SaaS = renting. Building with CC = owning. Different cash flow, different leverage, different exit.

### The CC Pitch (tied to the layers)

> "Most agencies work in Layer 7 — they resell applications someone else built. I work in Layers 3, 4, 5, 6 — I pick the model, orchestrate it, give it memory, wire it to your tools. That's why my systems are cheaper, faster, and actually yours."

---

## 4. Meeting Play-by-Play

A 60-minute discovery/strategy call. Run this verbatim until you've done 20 and know when to deviate.

### Minute 0-3 — Rapport + reset the frame

> "Hey — thanks for grabbing time. Before I pitch anything, I want to understand what you actually need. I'm going to ask a lot of questions; some will feel off-topic. That's on purpose. Sound good?"

This sets YOU as the interviewer, not them.

### Minute 3-15 — Discovery (Jeremy Miner NEPQ framing)

Three pattern-interrupt questions, in order:

1. **"Walk me through what a typical day looks like for you right now — where does your time actually go?"** (Listen for: manual work, context switching, team gaps.)
2. **"Out of everything on your plate, what's the thing you keep pushing to next week?"** (The real pain.)
3. **"If you could wake up tomorrow and one of those things was just… handled… what changes in your business?"** (The stakes.)

**Do NOT pitch here.** Just listen. Take notes. Repeat back what you heard in their words.

### Minute 15-25 — Diagnose out loud

> "Okay, here's what I'm hearing. [Repeat their 3 pain points verbatim.] I want to check my understanding before I say anything about what I do."

Wait. Let them correct you. When they say "yeah, exactly" — you've earned the right to talk.

### Minute 25-40 — Show, don't sell

Open your laptop. Show ONE of these based on what they said:

- **If they complained about manual outreach:** Live-demo PULSE (ig-setter-pro).
- **If they complained about content:** Live-demo the video pipeline (Whisper + FFmpeg + Remotion).
- **If they complained about client management:** Live-demo client health scoring in Bravo.
- **If they complained about security/compliance:** Show Section 2 of this playbook. Walk them through the 7 layers.

**Key phrase:** "This isn't a prototype. I run this for my own business. Let me show you the dashboard."

### Minute 40-50 — Price the outcome, not the work

Don't lead with "$X/month." Lead with:

> "Most clients at your stage get to positive ROI in [timeframe] because [specific reason]. That works out to roughly [hourly savings × their rate] in time alone, not counting the deals you close faster. Pricing is $[800-3000]/mo depending on scope. Want me to walk you through what that covers?"

If they push back on price: handle it per `memory/feedback_objection_handling.md` — never defend margins, do the math for them, reframe as their win.

### Minute 50-55 — Close with a small ask

Either:
- "Want to try a 2-week pilot at $[number]? No contract. You cancel anytime."
- "Want me to send over a 1-page security memo + scope doc? Takes me 2 days. Then we decide together."

**Never leave without a next step on the calendar.**

### Minute 55-60 — Recap + schedule

> "Here's what I'm taking away. [Recap 3 pains.] I'm going to [next step] by [date]. You're going to [their commitment]. We'll meet again [specific date/time]."

Written follow-up in 2 hours via email. No exceptions.

---

## 5. The 10-Years-Ahead Frame (psychology)

This is why CC wins long-term and why prospects should work with him NOW.

**The frame:**
> "Most people are adjusting to AI the way my grandma adjusted to the internet in 2002. They'll get there, but they're going to lose a decade. I've been building on this for 2+ years. By the time it's 'normal,' I'll be 10 years ahead."

**Why prospects need to hear this:**
- They're scared of being left behind (accurate)
- They think "AI" is one thing they'll figure out later (wrong)
- They don't realize the compound advantage of early adoption

**How to frame it in a pitch:**
> "Every client I've onboarded this year will have a 3-year lead over their competitors by 2029. That's not hype — that's what happens when you build real systems while your competitors wait for certainty."

**The reverse close:**
> "If I'm wrong about AI, you spent $X/month and got a more efficient business. If I'm right, you have a 10-year advantage. That's an asymmetric bet."

---

## 6. Trend-Watching Discipline (how to stay ahead)

CC said: "We also predict small trends, but I want some material I can use."

**Sources to scan weekly (15 min each):**

- **[Hacker News](https://news.ycombinator.com)** — top 30 posts. What builders are actually using.
- **[Anthropic Blog](https://www.anthropic.com/news)** — Claude roadmap, new features.
- **[OpenAI Blog](https://openai.com/news)** — GPT/Codex updates.
- **[a16z AI portfolio](https://a16z.com/category/ai/)** — what VCs are funding = 2-year trend leader.
- **[Y Combinator Launches](https://www.ycombinator.com/launches)** — daily YC launches. Filter for AI.
- **[Latent Space podcast](https://www.latent.space)** — weekly, technical, signal-dense.
- **[Simon Willison's blog](https://simonwillison.net)** — best-in-class AI practitioner notes.

**Trend-capture protocol:**
1. When you see a signal (new tool, framework, pattern), save the link + 1-sentence why.
2. Drop it into `brain/TOOL_SHED.md` under the appropriate section.
3. If it's a repeat pattern (3+ sources), write 1 Skool post about it.
4. If it's a single source, save it and re-check in 30 days — is anyone else talking about it?

**This is how CC stays 10 years ahead:** not predicting the future, systematically noticing what's real.

---

## 7. Usage Guide

**Before a meeting:**
1. Re-read Section 1 (your intro) + Section 4 (play-by-play).
2. Based on prospect's LinkedIn/website, pick which live demo from Section 4 Min 25-40.
3. Have Section 2 (security) open in a tab in case they ask.

**During the meeting:**
- Phone on silent. Laptop ready. Notes app open.
- Don't reference this playbook in front of them — the point is you've internalized it.

**After the meeting:**
- Written follow-up within 2 hours (automated draft via Bravo).
- Log the meeting in `memory/client-meetings/[DATE]-[company].md`.
- Note which sections of this playbook worked / didn't.
- Update this file if you found a better answer than what's here.

**Sharing with prospects:**
- Sections 2 (Security), 3 (AI Industry Map), and 5 (10-Years-Ahead) are shareable.
- Section 1 and 4 are internal — these are YOUR tools.
- When you share, strip the internal-commentary parts (the italicized "Do NOT pitch here" lines etc.)

---

## 🔗 Obsidian Links
- [[brain/USER]] — your profile + mission
- [[brain/SOUL]] — identity + values
- [[brain/TOOL_SHED]] — repos + tools you can point clients to
- [[../CMO-Agent/brain/CONTENT_BIBLE]] (Maven canonical) — voice, hook bank, pacing rules
- [[memory/feedback_objection_handling]] — pricing pushback playbook
- [[memory/feedback_outreach_signature]] — email signature standard
- [[memory/feedback_power_dynamics]] — never defer to prospects on scheduling/framing

## Related

- [[brain/INDEX]]
- [[brain/AGENT_INDEX]]
