# Day 0: Foundation — What Is AI and Why It Matters

> **Level:** Explorer (Level 0)
> **Duration:** ~2 hours
> **Prerequisites:** None — absolute zero assumed
> **Goal:** Walk away understanding the vocabulary, the landscape, and why this matters for your career/business.

---

## Module 1: The AI Landscape (30 min)

### What Are LLMs?

Large Language Models are AI systems trained on massive amounts of text. They predict the next word — but that simple principle creates something that can write code, analyze data, draft emails, and solve complex problems.

**The Big Players:**
| Model | Company | Best For |
|-------|---------|----------|
| Claude | Anthropic | Coding, analysis, long documents |
| GPT-4 | OpenAI | General purpose, plugins |
| Gemini | Google | Multimodal (text + images), Google integration |
| Llama | Meta | Open source, self-hosting |

**What's real vs hype:**
- Real: AI writing code, automating data entry, summarizing documents, generating content
- Hype: "AI will replace all jobs" — it replaces tasks, not entire jobs
- The truth: People who use AI will replace people who don't

### Agents vs Chatbots

| | Chatbot | Agent |
|---|---|---|
| **What it does** | Answers questions | Takes actions |
| **Example** | "What's the weather?" | Checks weather, sends you an alert if it'll rain, adjusts your calendar |
| **Limitation** | One-turn conversations | Can run multi-step workflows |
| **Think of it as** | A search engine that talks | An employee that works |

An **Agent Command Center** is your dashboard for managing AI agents that work for your business.

---

## Module 2: How AI "Thinks" (20 min)

### Tokens
AI doesn't read words — it reads **tokens** (chunks of words).
- "Hello" = 1 token
- "Entrepreneurship" = 3 tokens
- Average: 1 token ≈ 0.75 words

Why it matters: AI has a **context window** — the maximum number of tokens it can process at once.
- Claude: ~200,000 tokens (~150,000 words — an entire book)
- GPT-4: ~128,000 tokens
- Bigger window = AI can see more of your project at once

### Prompts
A **prompt** is your instruction to the AI. Better prompts = better results.

**Bad prompt:** "Make me a website"
**Good prompt:** "Create a landing page for a dog grooming business in Collingwood, Ontario. Include a hero section with a headline, a services section with 3 cards (Bath, Haircut, Full Groom with prices $30, $45, $75), and a contact form. Use a warm color palette. Mobile responsive."

The difference? **Specificity.** AI isn't psychic — it needs context.

### Temperature
How "creative" vs "precise" the AI is:
- Temperature 0.0 = Deterministic (same input → same output every time)
- Temperature 1.0 = Creative (more variety, more randomness)
- For coding: low temperature (precision matters)
- For content: medium-high temperature (creativity matters)

---

## Module 3: The Tool Stack (20 min)

### The 4 Categories

Think of these as layers of a machine:

```
Layer 4: MCPs          (Connections — how AI plugs into tools)
Layer 3: APIs          (Communication — how software talks to software)
Layer 2: CLI           (Text interface — type commands, get results)
Layer 1: IDE           (Visual interface — where you write code)
```

**IDE (Integrated Development Environment)**
Your workspace. Like Microsoft Word, but for code.
- VS Code — Free, most popular, extensible
- Cursor — AI-first IDE (built on VS Code)
- Anti-Gravity — Claude-native IDE extension

**CLI (Command Line Interface)**
Text-based terminal. Looks like a hacker movie, but it's just typing commands.
- Claude Code — Anthropic's AI CLI (our primary tool)
- Gemini CLI — Google's AI CLI
- OpenCode — Open-source alternative

**API (Application Programming Interface)**
How software talks to other software. Like a restaurant menu:
- You (the app) send a request: "I want the weather for Toronto"
- The API responds: `{"temp": 22, "conditions": "sunny"}`

**MCP (Model Context Protocol)**
How AI connects to external tools automatically. Think of it as USB ports for AI:
- Plug in Playwright MCP → AI can browse the web
- Plug in Supabase MCP → AI can query your database
- Plug in Stripe MCP → AI can check your payments

---

## Module 4: Business Case Studies (30 min)

### Case Study 1: Local HVAC Company
**Before AI:** Owner manually responds to every inquiry email. Takes 2 hours/day.
**After AI:** n8n workflow catches new emails → Claude drafts response → owner approves with one click → auto-sends.
**Result:** 2 hours/day → 10 minutes/day. Owner focuses on jobs, not inbox.

### Case Study 2: Real Estate Agent
**Before AI:** Manually posting to 5 social media platforms. 1 hour/day.
**After AI:** Write one post → Late API cross-posts to X, LinkedIn, Instagram, Threads, TikTok. Scheduled for optimal times.
**Result:** 1 hour → 5 minutes. Consistent presence across all platforms.

### Case Study 3: E-Commerce Store
**Before AI:** Customer support via email. Responds next day. Loses sales.
**After AI:** AI agent handles common questions instantly (shipping, returns, sizing). Escalates complex issues to human.
**Result:** 90% of questions answered instantly. Sales conversion up 25%.

### The Pattern
1. Identify a repetitive task
2. Map the steps
3. Automate with AI tools
4. Human reviews/approves (keep the human in the loop)
5. Iterate and improve

---

## Module 5: Mindset (15 min)

### Why Most People Fail at AI Adoption

1. **Fear** — "AI is too complicated" → It's not. If you can Google, you can prompt AI.
2. **Perfectionism** — "I need to understand everything first" → Start messy. Learn by doing.
3. **Wrong tool** — Using ChatGPT for everything → Different tools for different jobs.
4. **No structure** — Random experiments → Need a system (that's what this bootcamp gives you).
5. **Giving up too early** — First prompt didn't work → Iteration is the game.

### The Mindset Shift
- Old: "I need to learn to code to use AI"
- New: "AI helps me code — I just need to learn to direct it"
- You're not becoming a developer. You're becoming an **AI operator**.

### The Hierarchy of AI Skills
```
Level 1: Use AI chatbots (ChatGPT, Claude.ai)        ← Most people stop here
Level 2: Use AI tools in your workflow (Cursor, Claude Code)
Level 3: Connect AI to external tools (MCPs, APIs)
Level 4: Build automated pipelines (n8n, cron, webhooks)
Level 5: Architect multi-agent systems (Agent Command Center)  ← Where we're going
```

---

## Exercise

**Write down 5 tasks in your business or life that are:**
1. Repetitive (you do them weekly or daily)
2. Rule-based (there's a clear process)
3. Time-consuming (they take >30 minutes each time)

Examples: Responding to emails, posting on social media, creating invoices, scheduling appointments, organizing files.

**These are your automation candidates.** By Day 10, at least 2 of them will be automated.

---

## Key Vocabulary Cheat Sheet

| Term | Plain English |
|------|---------------|
| LLM | AI brain trained on text |
| Token | A chunk of a word (AI's unit of reading) |
| Context Window | How much AI can "see" at once |
| Prompt | Your instruction to AI |
| Agent | AI that takes actions, not just chats |
| IDE | Code editor (like Word for code) |
| CLI | Text terminal (type commands) |
| API | How software talks to software |
| MCP | How AI connects to external tools |
| Webhook | "When X happens, do Y" trigger |
| Cron | "Run this at a specific time" scheduler |

---

**Next:** [Day 1 — Environment Setup](../day-01-environment-setup/LESSON.md)
