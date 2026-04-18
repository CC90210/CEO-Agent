---
tags: [content-studio, courses, scripts, bennett]
---

# Course Overview Scripts — Bennett's Agency Accelerator
## Skool Module Walkthrough Videos (CC On Camera + Screen Share)

---

# COURSE 3: ENVIRONMENT SETUP
### "Zero to Ready" — Module Overview Video (~7-9 min)

---

**[SCREEN: Skool course page — Course 3: Environment Setup, all lessons visible]**

**[INTRO — 30 sec]**

Alright, what's up — welcome to Course 3. This is the environment setup module and honestly, it's the one most people sleep on. They skip to the fun stuff and then wonder why nothing works.

So — before you write a single line of code, before you run your first Claude session, you need your machine actually set up to do it. That's what this whole module is. By the end of these four lessons, you should be able to open a terminal, type `claude`, hit enter, and have a full AI coding session running. That's the goal. Let's go through what's in here.

---

**[LESSON 1 — Terminal Basics]**

**[SCREEN: Click into Lesson 1 — "Welcome to the Terminal"]**

First lesson is called "Welcome to the Terminal" — and if you've never touched a terminal before, this is where it clicks.

The terminal looks scary. It's just a black screen with a blinking cursor. But once you get it, you realize it's just a faster way to talk to your computer. Instead of clicking through menus, you type what you want. That's it.

In this lesson I walk you through what the terminal actually is, how to open it on your machine — whether you're on Mac, Windows, Linux — and I go through the commands you'll actually use. `cd` to navigate folders, `ls` to list files, how to create directories, how to move around. Nothing crazy. Just the foundation.

Why does this matter? Because Claude Code lives in the terminal. Everything you're going to do in this course — running scripts, installing packages, starting sessions — it all happens in the terminal. You need to be comfortable here. This lesson gets you there.

---

**[LESSON 2 — Node.js, Git & GitHub]**

**[SCREEN: Click into Lesson 2 — "Git — Your Code Time Machine"]**

Lesson two is called "Git — Your Code Time Machine" and I love that title because that's exactly what it is.

So there are two things happening in this lesson. First, Node.js — Node is a JavaScript runtime that Claude Code needs to run. You'll install it, verify it's working, that's it. Takes five minutes.

The bigger piece is Git and GitHub. Git is version control — every time you save a meaningful state of your project, Git remembers it. You can go back. You can branch off and try something, and if it breaks, you revert. It's genuinely one of the most important tools in development and most non-technical people just never touch it.

GitHub is where your code lives in the cloud. It's like Google Drive for code. When Claude Code is working on your project, it can push changes, track what was modified, and you always have a backup.

I walk you through installing Git, setting up a GitHub account if you don't have one, and doing your first commit. By the end you'll understand what `git init`, `git commit`, and `git push` actually do — not just copy-paste them blindly.

---

**[LESSON 3 — Installing Claude Code]**

**[SCREEN: Click into Lesson 3 — "Installing Claude Code"]**

Lesson three is the one you've been waiting for — installing Claude Code.

Claude Code is Anthropic's official CLI — command line interface — for Claude. It's not the chat window. It's not Claude.ai. This is Claude living inside your terminal, with access to your files, your codebase, your entire project. That's a fundamentally different thing.

In this lesson I go through the exact install steps. You'll use Node's package manager — npm — to install it globally on your machine. Takes one command. Then you authenticate with your Anthropic API key, and you're live.

I also talk about what Claude Code actually does differently from the chat UI. When you're in a session, it can read your files, edit them, run commands, search your codebase. It's operating in your environment. That's the power shift. You'll understand why that matters by the end of this one.

---

**[LESSON 4 — IDEs]**

**[SCREEN: Click into Lesson 4 — "IDEs (Anti-Gravity IDE + VS Code)"]**

Last lesson in this module is about IDEs — your code editor. An IDE is basically where you read and write code. Think of it like Microsoft Word, but for developers.

I cover two options here. VS Code is the one everyone knows — free, open source, massive extension library, solid choice. Anti-Gravity IDE is what I personally use. It's built specifically for AI-assisted development, has Claude Code integration baked in natively, and the experience is cleaner when you're working with AI agents all day.

I'm not here to tell you which one to use — both work. I show you how to set up both, how to open your project folder, and how Claude Code connects to whichever editor you're in.

---

**[OUTRO — 30 sec]**

**[SCREEN: Back to full Course 3 module view, all 4 lessons visible]**

That's the whole module — four lessons, zero to ready. Terminal, Node, Git, Claude Code installed, IDE set up. Do all four in order, don't skip anything. The members who skip the terminal lesson are always the ones DMing me later saying something won't run.

Get your environment right once, and everything else in this course just works. See you in Course 4.

Only good things from now on.

---
---

# COURSE 4: CLAUDE CODE MASTERY
### "From User to Builder" — Module Overview Video (~7-9 min)

---

**[SCREEN: Skool course page — Course 4: Claude Code Mastery, all lessons visible]**

**[INTRO — 30 sec]**

Okay, Course 4. This is the big one. This is the module where you stop being someone who uses Claude Code and start being someone who builds with it.

There are six lessons in here and they build on each other. We go from understanding how Claude Code actually works under the hood, to prompting it properly, to giving it a memory, to building your own custom tools, to running multi-agent workflows. The arc of this module is: you start as a user, you end as an architect. Let me walk you through what's in each lesson.

---

**[LESSON 1 — How Claude Code Works]**

**[SCREEN: Click into Lesson 1 — "Claude Code Architecture"]**

First lesson is called "Claude Code Architecture" — inputs, outputs, how the model reads your project.

Most people just start typing at Claude Code and hope for the best. This lesson explains what's actually happening. When you start a session, Claude Code doesn't just see your current message — it reads your project. It looks at your files, your folder structure, any configuration you've set up. It builds context before it responds.

Understanding this changes how you work with it. You stop treating it like a chatbot and start treating it like a collaborator that has actually read your codebase. I explain the input/output model — what goes in, what comes back, how it decides what to do. This is the mental model you need before anything else in this module makes sense.

---

**[LESSON 2 — Effective Prompting]**

**[SCREEN: Click into Lesson 2 — "The 4 Levels of Prompting"]**

Lesson two is "The 4 Levels of Prompting" and this one genuinely changes how people interact with AI tools.

Level one is basic — you type a question, you get an answer. Most people live here. Level two is structured — you give context, a goal, and constraints. Way better results. Level three is system-level — you're setting up rules and behaviors that persist across the whole session, not just one message. Level four is architect-level — you're not prompting for an answer, you're prompting for a plan, and then delegating execution.

The jump from level two to four is what separates people who save 20 minutes a day from people who replace entire workflows. I give you real examples of each level so you can see the difference. By the end of this lesson you'll know exactly why some prompts hit and some fall flat.

---

**[LESSON 3 — CLAUDE.md & Project Config]**

**[SCREEN: Click into Lesson 3 — "CLAUDE.md & Project Config"]**

Lesson three is about CLAUDE.md — and this might be the most important concept in the entire course.

CLAUDE.md is a file you put in your project that Claude Code reads every single session. It's your project's memory. You put in your tech stack, your rules, your preferences, what files matter, what patterns to follow. Claude Code loads it at boot and now it knows your project without you having to explain it every time.

I walk you through what actually belongs in a CLAUDE.md — your stack, your constraints, your routing rules, your security requirements. I show you the difference between a project with a good CLAUDE.md and one without. Without it, you're re-explaining yourself every session. With it, Claude Code already knows the context and just executes.

This is the thing that makes AI actually feel like a team member rather than a search engine you have to prompt correctly every time.

---

**[LESSON 4 — File Operations & Subagents]**

**[SCREEN: Click into Lesson 4 — "File Operations & Subagents"]**

Lesson four gets into file operations and subagents.

File operations are exactly what they sound like — reading files, editing files, creating files, searching across your codebase. Claude Code can do all of this natively inside a session. You say "read this file and refactor the auth logic" and it actually does it — reads the file, makes the changes, shows you the diff. I go through the tools it uses and how to get precise results.

Subagents are where it gets really interesting. Claude Code can spin up other agents to handle parts of a task in parallel. You're working on one thing, a subagent handles something else in the background. This is how you start moving from "doing tasks" to "orchestrating systems." I cover how to delegate cleanly and how to verify the subagent actually did what you asked.

---

**[LESSON 5 — Building Custom Skills]**

**[SCREEN: Click into Lesson 5 — "Building Custom Skills"]**

Lesson five is building custom skills — and this is when Claude Code becomes yours.

A skill is a reusable instruction set. You write it once, and then you can trigger it by name in any session. The anatomy of a skill file is simple: YAML frontmatter at the top — name, description, what it does — and then the actual instructions. I go through a real skill file and explain every section.

Examples of skills I use myself: a skill for code review, a skill for writing content in my voice, a skill for database migrations. Instead of typing out all those instructions every time, I just say "run the code-review skill" and it knows exactly what to do.

This is how you systematize your own workflows. Anything you find yourself explaining to Claude Code more than twice — turn it into a skill.

---

**[LESSON 6 — Advanced Skills & Automation]**

**[SCREEN: Click into Lesson 6 — "Advanced Skills & Automation"]**

Last lesson — advanced skills and automation. This is the ceiling of what Claude Code can do.

Skill chaining is running multiple skills in sequence — one skill's output feeds into the next. I show you how to set that up so you can build multi-step pipelines that run automatically. Multi-agent orchestration is the next level — you have a primary agent coordinating multiple subagents, each handling a different part of a complex task simultaneously.

Headless mode is something most people don't even know exists. You can run Claude Code without an interactive session — fully automated, triggered by a script or a scheduler. This is how you build things that run while you sleep. I show you what that looks like and when you'd use it.

By the end of this lesson, you can build something that would take a traditional developer weeks — in an afternoon.

---

**[OUTRO — 30 sec]**

**[SCREEN: Back to full Course 4 module view, all 6 lessons visible]**

Six lessons. That's the whole module. Architecture, prompting, project memory, file ops, custom skills, full automation. Do them in order — each one builds on the last.

If you take nothing else from this community, take this module seriously. This is the stuff that actually changes how you work. See you in Course 5.

Only good things from now on.

---
---

# COURSE 5: MCPs & INTEGRATIONS
### "Claude Code Gets Superpowers" — Module Overview Video (~7-9 min)

---

**[SCREEN: Skool course page — Course 5: MCPs & Integrations, all lessons visible]**

**[INTRO — 30 sec]**

Course 5 — MCPs and integrations. This is where Claude Code stops being a code assistant and becomes a full operations center.

By the end of this module, your Claude Code setup will be able to browse the web, read and write to a database in plain English, automate multi-step workflows, and pull live documentation on any tool as you're building. Six lessons. Let me break them down.

---

**[LESSON 1 — What Is an API?]**

**[SCREEN: Click into Lesson 1 — "The Restaurant Analogy"]**

First lesson is called "The Restaurant Analogy" — and I start here because honestly, a lot of people in this community come from a non-technical background and the word API gets thrown around like everyone just knows what it means. Most people don't.

So here's the analogy. You're at a restaurant. You're the client — the customer. The kitchen is where the data lives — the database, the service, whatever system you want to talk to. The waiter is the API. You don't walk into the kitchen and grab food yourself. You tell the waiter what you want, the waiter goes to the kitchen, the kitchen prepares it, and the waiter brings it back to you.

That's it. An API is a messenger between you and a system. It defines what you can ask for and what format you'll get it back in. Every integration in this module runs on APIs. Once you understand this, everything else in Course 5 makes sense. I go deeper in the lesson — real examples, real use cases — but that's the core.

---

**[LESSON 2 — What Are MCPs?]**

**[SCREEN: Click into Lesson 2 — "What Are MCPs?"]**

Lesson two — Model Context Protocol. MCP.

Here's the simplest way I can put it. Claude Code, by default, can read and edit files and run commands. That's powerful on its own. But MCPs are plugins that extend what Claude Code can connect to. With an MCP, Claude Code can browse the web, query your database, trigger automation workflows, pull live documentation — things it literally cannot do out of the box.

The Model Context Protocol is an open standard Anthropic released so that any tool can build a native integration with Claude. So instead of you writing code to connect Claude to your database, someone already built a Supabase MCP. You install it, configure it, and now Claude Code can talk to your database in plain English. Done.

I explain how MCPs work technically — at a high level, not a deep dive — and I show you how to install and configure them. The rest of the module is us activating specific MCPs one by one. Think of this lesson as the unlock.

---

**[LESSON 3 — Playwright & Web Automation]**

**[SCREEN: Click into Lesson 3 — "The 5-Step Workflow"]**

Lesson three is Playwright — web automation. And this one is genuinely wild when you see it for the first time.

Playwright is a browser automation tool. With the Playwright MCP, Claude Code can open a real browser, navigate to a URL, interact with the page — click buttons, fill out forms, extract data — and report back what happened. All from a single instruction.

I teach a 5-step workflow: navigate, snapshot, interact, re-snapshot, verify. You navigate to a page, take a snapshot so Claude can see what's on screen, interact with an element, take another snapshot to confirm the change happened, then verify the result matches what you expected. That loop is the foundation of every web automation you'll build.

Use cases in this community — scraping competitor data, automating form submissions, testing your own web apps, pulling lead information. It's one of the most immediately useful tools in this entire course.

---

**[LESSON 4 — Memory, Context7 & Thinking]**

**[SCREEN: Click into Lesson 4 — "The Intelligence Stack"]**

Lesson four is called "The Intelligence Stack" — and this is about making Claude Code smarter, not just more connected.

Three tools here. Sequential Thinking MCP gives Claude Code the ability to reason through complex problems step by step before acting. Instead of just responding immediately, it slows down, generates hypotheses, evaluates them, picks the best approach. For anything non-trivial, this produces dramatically better results.

Context7 MCP solves a real problem — Claude's training data has a cutoff. If you're building with a library that released a new version recently, Claude might give you outdated syntax. Context7 pulls live, current documentation for any tool in real time during your session. So Claude's always working with accurate information.

Memory MCP is persistent storage across sessions. By default, Claude Code forgets everything when a session ends. Memory MCP lets it store notes, decisions, project context — and load them back in the next session. It's how you give Claude Code a long-term memory.

Together, these three make Claude Code genuinely intelligent rather than just responsive.

---

**[LESSON 5 — Supabase MCP]**

**[SCREEN: Click into Lesson 5 — "Supabase MCP"]**

Lesson five — Supabase. This is the database integration.

Supabase is a Postgres database with an API layer, auth, storage — it's the backend most of us are building on in this community. The Supabase MCP lets Claude Code query, insert, update, and manage your database using plain English.

You literally say "show me all the users who signed up in the last 7 days and haven't completed onboarding" and Claude Code writes and runs the SQL query and returns the results. You don't need to know SQL. You don't need to open a database GUI. You just ask.

I walk through how to connect it to your Supabase project, how to set it up securely — because you're connecting real data here, so credentials need to be handled correctly — and I show real queries so you can see what's possible. This one alone saves hours every week once you're using it.

---

**[LESSON 6 — n8n Integration]**

**[SCREEN: Click into Lesson 6 — "n8n Integration"]**

Last lesson — n8n. This is the automation workflow layer.

n8n is a workflow automation tool — think Zapier but self-hosted and far more powerful. You build workflows visually — triggers, conditions, actions — and n8n runs them automatically. The n8n MCP integration means Claude Code can trigger and interact with those workflows directly from a session.

So imagine this: you're in a Claude Code session, you say "kick off the lead enrichment workflow for this contact" and Claude Code fires the n8n workflow, which then hits an API, updates your CRM, and sends a follow-up email. One instruction, full chain of automation.

I go through how to connect them, how to structure workflows so Claude can trigger them cleanly, and I show a real example end to end. This is the piece that turns Claude Code from a single tool into the center of your whole operations stack.

---

**[OUTRO — 30 sec]**

**[SCREEN: Back to full Course 5 module view, all 6 lessons visible]**

Six lessons — APIs, MCPs, web automation, the intelligence stack, database access, automation workflows. At this point in the course you have a fully operational AI system. Not just a code helper. An operations center.

That's everything in Course 5. If you've made it this far through all three modules — environment set up, Claude Code mastered, integrations live — you're genuinely ahead of 99% of agency owners in this space.

Go build something. Only good things from now on.

---

*Scripts written for Bennett's Agency Accelerator — Skool Course 3, 4, and 5 module overview videos.*
*CC on camera + screen share. Estimated runtime per video: 7-9 minutes.*

## Obsidian Links
- [[content-studio/INDEX]] | [[brain/USER]] | [[courses/INDEX]]
- [[../CMO-Agent/skills/content-engine/SKILL]] | [[agents/content-creator]]
