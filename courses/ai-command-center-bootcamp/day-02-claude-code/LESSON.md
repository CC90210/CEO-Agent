# Day 2: Claude Code Deep Dive — Your AI Employee

> **Level:** Builder (Level 1)
> **Duration:** ~3 hours
> **Prerequisites:** Day 1 complete, Claude Code installed and working
> **Goal:** Master Claude Code as your primary AI tool. Know how to instruct it, extend it, and trust it.

---

## Module 1: Claude Code Architecture (20 min)

### How Claude Code Actually Works

```
You type a message
    ↓
Claude Code reads it + your CLAUDE.md + relevant files
    ↓
It decides what tools to use (Read, Edit, Write, Bash, etc.)
    ↓
Asks your permission (unless auto-accept)
    ↓
Executes the action
    ↓
Shows you the result
    ↓
Waits for your next instruction
```

### The Context Window

Claude Code can "see" about 200,000 tokens at once. That's roughly:
- 500 pages of text
- An entire medium codebase
- Every file it's read in the current conversation

**Important:** When the context fills up, older messages get compressed. This is normal. Claude Code handles it automatically.

### What Tools Does Claude Code Have?

| Tool | What It Does |
|------|-------------|
| **Read** | Read any file on your computer |
| **Write** | Create new files |
| **Edit** | Modify specific parts of existing files |
| **Bash** | Run terminal commands |
| **Glob** | Find files by name pattern (e.g., all .js files) |
| **Grep** | Search for text inside files |
| **Agent** | Spawn sub-agents for parallel work |
| **WebSearch** | Search the internet |
| **WebFetch** | Download a webpage |

---

## Module 2: Effective Prompting (30 min)

### The Prompting Framework: Context → Task → Constraints

**Bad:** "Make a website"
**Good:** "I'm building a dog grooming business website [CONTEXT]. Create a landing page with hero, services (3 cards), and contact form [TASK]. Use Tailwind CSS, dark theme, mobile-first [CONSTRAINTS]."

### Level 1: Simple Instructions
```
Create a Python script that converts Celsius to Fahrenheit
```

### Level 2: Contextual Instructions
```
I have a CSV file at data/customers.csv with columns: name, email, phone, city.
Create a Python script that reads this file and prints all customers in Toronto.
```

### Level 3: Multi-Step Instructions
```
I need to build a contact form for my business website.
1. Create an HTML form with fields: name, email, message
2. Add CSS styling (dark theme, centered, mobile responsive)
3. Add JavaScript validation (all fields required, valid email format)
4. Save everything in a "contact-form" folder
```

### Level 4: Role-Based Instructions
```
You are a senior TypeScript developer. Review the code in src/api/handler.ts.
Look for: security vulnerabilities, error handling gaps, performance issues.
Rate each finding as CRITICAL, HIGH, MEDIUM, or LOW.
Don't fix anything — just report.
```

### Pro Tips
- **Be specific** about file paths, names, and locations
- **State what you DON'T want** as clearly as what you do want
- **Break big tasks into steps** — Claude Code handles 3 clear steps better than 1 vague request
- **Iterate** — First result not perfect? Say "make the header bigger" or "change the color to blue"

---

## Module 3: CLAUDE.md — Teaching Your AI (20 min)

### What Is CLAUDE.md?

A special file that Claude Code reads automatically at the start of every conversation. It contains:
- Project rules (coding style, conventions)
- Context about the project (what it does, how it's structured)
- Behavior instructions (what to do and what NOT to do)

### Where It Lives

```
your-project/
├── CLAUDE.md          ← Project root (loaded always)
├── src/
│   ├── CLAUDE.md      ← Only loaded when working in src/
│   └── components/
│       └── CLAUDE.md  ← Only loaded when working in components/
└── tests/
    └── CLAUDE.md      ← Only loaded when working in tests/
```

### Your First CLAUDE.md

```markdown
# My Project

## What This Is
A personal portfolio website built with HTML, CSS, and JavaScript.

## Rules
- Use dark theme (background: #1a1a2e, text: #e0e0e0)
- Mobile-first design (min-width media queries)
- No frameworks — vanilla HTML/CSS/JS only
- All images go in /assets/images/
- Use semantic HTML (header, main, section, footer)

## Don't
- Don't use inline styles
- Don't add jQuery or any libraries
- Don't create files outside the project directory
```

### Why This Matters

Without CLAUDE.md, you repeat the same instructions every conversation. With it, Claude Code already knows your preferences. It's like training an employee once instead of every morning.

---

## Module 4: Skills & Slash Commands (30 min)

### Built-In Commands

| Command | What It Does |
|---------|-------------|
| `/help` | Show help |
| `/clear` | Clear conversation |
| `/compact` | Compress context (saves tokens) |
| `/cost` | Show usage and cost |
| `/model` | Switch AI model |
| `/memory` | Manage project memory |

### What Are Skills?

Skills are pre-written prompt templates that extend Claude Code. Think of them as "macros" — one command triggers a complex workflow.

### Example Skill: Smart Commit

Instead of manually writing git commits:
```
/commit
```
This skill automatically:
1. Reads all your changes
2. Writes a clear commit message
3. Commits with conventional format

### Creating Custom Skills

Skills live in your project's `CLAUDE.md` or in `~/.claude/commands/`.

**Example: Create a /review skill**
Create file: `~/.claude/commands/review.md`
```markdown
Review the code changes I've made (use git diff). For each change:
1. Rate quality (1-5)
2. Flag any security issues
3. Suggest improvements
Keep it concise — bullet points only.
```

Now when you type `/review` in Claude Code, it runs this prompt.

### Community Skills

There's a growing ecosystem of community-built skills. Ask Claude Code:
```
What community skills are available?
```

---

## Module 5: Working with Files (30 min)

### Reading Files
```
Read the file at src/index.js
```
or
```
What's in my package.json?
```

### Creating Files
```
Create a new file called utils/helpers.js with a function that formats dates
```

### Editing Files
```
In src/app.js, change the port from 3000 to 8080
```

Claude Code uses precise text replacement — it finds the exact code to change and swaps it.

### Finding Files
```
Find all TypeScript files in the src directory
```
```
Search for any file that contains "API_KEY"
```

### Real-World Example: Refactoring

```
I have a function called "processData" in src/utils.js that's 200 lines long.
Break it into smaller functions (each <50 lines).
Keep the same behavior — don't change what it does, just how it's organized.
Make sure all imports still work.
```

Claude Code will:
1. Read the file
2. Understand the logic
3. Break it into smaller functions
4. Update all references
5. Show you what changed

---

## Module 6: Multi-File Operations & Subagents (20 min)

### Working Across Multiple Files

Claude Code can modify multiple files in one task:
```
Rename the "UserProfile" component to "AccountProfile" everywhere in the codebase.
Update all imports, references, and file names.
```

It searches every file, finds all references, and updates them all.

### Subagents

For complex tasks, Claude Code can spawn **sub-agents** — separate AI workers that handle specific parts in parallel.

```
Search the codebase for all API endpoints and document them in a table.
```

Under the hood, Claude Code might spawn a sub-agent to search files while the main agent organizes results. You don't need to manage this — it happens automatically.

### When to Use Multi-Step Prompts

If your task involves:
- Changing >5 files → Let Claude Code handle it, but review the plan first
- Adding a new feature → Describe the feature fully, then let Claude Code plan the approach
- Debugging → Describe the error, paste the error message, let Claude Code investigate

---

## Module 7: Settings & Configuration (15 min)

### The .claude Directory

```
~/.claude/                  ← Global settings (applies to all projects)
├── settings.json           ← Permissions, preferences
├── commands/               ← Custom slash commands
└── projects/               ← Per-project memory
    └── your-project/
        └── memory/         ← What Claude Code remembers about this project
```

### Permission Settings

In `settings.json`, you can configure what Claude Code can do without asking:

```json
{
  "permissions": {
    "allow": ["Read", "Glob", "Grep"],
    "deny": ["Bash(rm *)"]
  }
}
```

- **Allow:** These tools run without asking permission
- **Deny:** These patterns are always blocked

### Model Selection

Claude Code defaults to the best available model. You can switch:
```
/model sonnet      ← Faster, cheaper, good for simple tasks
/model opus        ← Smartest, more expensive, for complex work
/model haiku       ← Fastest, cheapest, for quick lookups
```

**Rule of thumb:**
- Routine tasks → Sonnet (fast, cheap)
- Complex coding → Opus (smart, thorough)
- Quick questions → Haiku (instant, minimal cost)

---

## Exercise: Build a Productivity Dashboard

**Step 1:** Create a new project
```bash
mkdir ~/ai-bootcamp/day-02-dashboard
cd ~/ai-bootcamp/day-02-dashboard
```

**Step 2:** Create your CLAUDE.md
```bash
claude
```
Then tell Claude:
```
Create a CLAUDE.md file with these rules:
- This is a personal productivity dashboard
- Use HTML, CSS, and vanilla JavaScript only
- Dark theme (bg: #0d1117, text: #c9d1d9, accent: #58a6ff)
- Mobile responsive
- All code must be well-commented
```

**Step 3:** Build the dashboard
```
Create a productivity dashboard with:
1. A header showing current date and time (updates every second)
2. A to-do list (add, complete, delete tasks — stored in localStorage)
3. A daily goals section (3 goal slots with progress bars)
4. A motivational quote section (hardcode 10 quotes, show random one)
Layout: 2-column grid on desktop, single column on mobile
```

**Step 4:** Review the code
```
/review
```
(If you created the skill from Module 4)

**Step 5:** Push to GitHub
```bash
git add .
git commit -m "day 2: productivity dashboard"
git push
```

---

## Checklist Before Moving On

- [ ] Understand Claude Code's architecture (tools, context, permissions)
- [ ] Can write effective prompts (context → task → constraints)
- [ ] Created a CLAUDE.md with project-specific rules
- [ ] Understand skills and slash commands
- [ ] Can direct Claude Code to read, write, edit, and find files
- [ ] Understand multi-file operations
- [ ] Know the difference between Opus, Sonnet, and Haiku models
- [ ] Built the productivity dashboard exercise

**All boxes checked?** You're a confident Claude Code operator.

---

**Next:** [Day 3 — MCPs & Integrations](../day-03-mcps-and-integrations/LESSON.md)
