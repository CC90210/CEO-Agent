# LEARNED PATTERNS
> What works, what doesn't. Check this BEFORE starting a task type you've done before.
> **V5.5:** Patterns now have validation status. `[VALIDATED]` = proven across 3+ sessions. `[PROBATIONARY]` = promising but needs more evidence.

> [[brain/BRAIN_LOOP]] | [[memory/MISTAKES]] | [[memory/SOP_LIBRARY]]

## Effective Patterns

### Late API Posting Workflow `[VALIDATED]`
**Context:** When CC says "post this" or "schedule this" to any social platform
**Pattern:** 1) Validate char limits per platform → 2) Rewrite condensed versions for short platforms (X=280) → 3) Present all versions to CC → 4) Post via Late MCP → 5) Log to SESSION_LOG
**Why it works:** Prevents API rejections and ensures platform-optimized content
**Sessions validated:** 3 | **Last used:** 2026-02-27

### Multi-Agent Task Routing `[VALIDATED]`
**Context:** Any task that comes into the workspace
**Pattern:** Simple/isolated tasks → Gemini. Multi-file architecture → Claude Code. Research → Anti-Gravity (has Playwright). Content → Any (all read entry points + brain/)
**Why it works:** Cost-efficient — Gemini for grunt work, Opus for the heavy lifting
**Sessions validated:** 4 | **Last used:** 2026-03-01

### Outreach Name Separation `[VALIDATED]`
**Context:** When drafting any outbound emails, social DMs, or lead communications.
**Pattern:** For professional/B2B/business leads (e.g., OASIS AI), ALWAYS use the full name **Conaugh McKenna**. For DJing/entertainment-related outreach, you may use the nickname **CC**.
**Why it works:** Maintains a serious, professional image for high-ticket business prospects while keeping the recognized artist name for entertainment gigs.
**Sessions validated:** 1 | **Last used:** 2026-03-03

### High-Converting Sales Outreach `[PROBATIONARY]`
**Context:** Drafting outbound emails to new leads.
**Pattern:** 
1) **Pattern Interrupt:** Hook them with an immediate observation about their business or an unconventional opening.
2) **Sales Logic & Personable Tone:** Sound like a genuine person but back it up with hard ROI logic. Do not sound "salesy" or use hustle-culture buzzwords.
3) **Immediate Value:** Prove you can solve a specific problem off the first rip.
4) **Incentivize / Make a Promise:** Give them a tangible reason to reply (e.g., "I'll save you 10 hours a week" or an "automation audit").
5) **DJ connection:** If the lead is a DJ or entertainment company, explicitly mention that Conaugh (CC) is a DJ too to build instant rapport.
**Why it works:** Cuts through the noise of generic B2B spam, builds rapport instantly, and provides a clear, risk-free next step.
**Sessions validated:** 1 | **Last used:** 2026-03-03

### GitHub Remote Edit Strategy `[VALIDATED]`
**Context:** When deploying changes to client repos (PropFlow, Nostalgic Requests, OASIS)
**Pattern:** Use GitHub MCP to branch → edit files remotely → open PR → Vercel auto-deploys preview → CC visually confirms → merge
**Why it works:** Saves disk space (no local clones), instant Vercel previews, clean git history
**Sessions validated:** 3 | **Last used:** 2026-02-28

### MCP Error Recovery `[VALIDATED]`
**Context:** Any MCP server returns an error
**Pattern:** 1) Report exact error code + message → 2) Check if auth-related (401) or schema-related → 3) Suggest specific fix → 4) STOP. Never retry in a loop. Never create bypass scripts.
**Why it works:** Prevents junk file creation and infinite retry loops that waste context
**Sessions validated:** 5 | **Last used:** 2026-03-01

### Windows MCP Env Variable Fix `[VALIDATED]`
**Context:** MCP server needs an environment variable (e.g., LATE_API_KEY, N8N_API_URL) but the `env` field in JSON config doesn't pass through on Windows
**Pattern:** Create a dedicated `.cmd` wrapper script in `scripts/` that `set`s all required env vars, then launches the MCP server. Point the JSON config to `"command": "cmd", "args": ["/c", "path/to/wrapper.cmd"]`. Example: `scripts/late-mcp-wrapper.cmd` sets `LATE_API_KEY` then runs `uvx --from "late-sdk[mcp]" late-mcp`.
**Why it works:** Windows MCP hosts (Antigravity IDE, Gemini CLI) don't reliably forward `env` field to subprocesses. The wrapper script injects vars into the shell before the process starts.
**Wrapper scripts:** `scripts/n8n-mcp-wrapper.cmd`, `scripts/late-mcp-wrapper.cmd`
**Sessions validated:** 4 | **Last used:** 2026-03-02

### Multi-Hypothesis Approach `[PROBATIONARY]`
**Context:** Any MODERATE+ complexity task
**Pattern:** 1) Generate 2-3 candidate approaches → 2) Rank by feasibility/risk/effort → 3) Execute best option → 4) On failure, switch to next ranked alternative → 5) After 3 total attempts across all approaches, STOP
**Why it works:** Prevents retrying the same broken approach. Inspired by LATS (Language Agent Tree Search)
**Sessions validated:** 1 | **Last used:** 2026-03-01

### Reflexion on Failure `[PROBATIONARY]`
**Context:** After any failed task
**Pattern:** 1) What was attempted? → 2) What went wrong? → 3) Why? (root cause) → 4) What to do differently? → 5) Confidence in reflection (0.0-1.0) → Store in SELF_REFLECTIONS.md
**Why it works:** Structured reflections retrieved by Step 2 (RECALL) prevent repeat failures. Inspired by Reflexion (Shinn et al., 2023)
**Sessions validated:** 0 | **Last used:** N/A (new pattern)

### Query-First MCP Routing `[VALIDATED]`
**Context:** User asks a question that can be answered by an MCP tool (n8n, Late, Supabase, etc.)
**Pattern:** 1) Parse query → identify topic → 2) Map to MCP server using routing table → 3) Call the tool IMMEDIATELY → 4) Return real data → 5) Never describe what you would do, actually DO it
**Why it works:** Prevents agents from dumping boot sequences or internal state when the user asked a direct question.
**Applied to:** GEMINI.md, ANTIGRAVITY.md, telegram_agent.js (all 3 agent entry points)
**Sessions validated:** 3 | **Last used:** 2026-03-02

### Anti-Bloat / File Structure Protocol `[VALIDATED]`
**Context:** When asked to create documentation, tracking files, or SOPs.
**Pattern:** Do not create new markdown files unless strictly required for a new tool or distinct architectural domain (like a new CLI command). Always UPDATE existing files (`PATTERNS.md`, `ACTIVE_TASKS.md`, `STATE.md`, `CAPABILITIES.md`).
**Why it works:** Prevents knowledge fragmentation and confusion across the 12 sub-agents. A lean, consolidated brain is faster and more accurate to query.
**Sessions validated:** 1 | **Last used:** 2026-03-03

### Cross-File Sync on Structure Changes `[VALIDATED]`
**Context:** Any change to file structure, MCP configs, agent entry points, or capabilities
**Pattern:** When changing ANY config or structure file, identify and update ALL files that reference it. Key sync points:
- MCP configs: `.claude/mcp.json`, `.vscode/mcp.json`, `~/.gemini/settings.json`, `.env.agents`
- Agent entry points: `GEMINI.md`, `ANTIGRAVITY.md`, `telegram_agent.js`, `CLAUDE.md`
- Documentation: `brain/CAPABILITIES.md`, `brain/AGENTS.md`, `skills/mcp-operations/SKILL.md`
- Memory: `memory/ACTIVE_TASKS.md`, `brain/STATE.md`
**Critical addition:** After ANY file delete/rename, run `grep -rn "filename" --include="*.md"` to find ALL stale references. Fix every one before committing.
**Why it works:** Session 12 discovered 15+ broken cross-references from deleting 2 files without scanning. This pattern prevents that.
**Sessions validated:** 2 | **Last used:** 2026-03-03

### N8N Community MCP over Native Endpoint `[PROBATIONARY]`
**Context:** Accessing n8n workflows via MCP
**Pattern:** Use `n8n-mcp` npm package (community, REST API) instead of `supergateway` → native `/mcp-server/http` endpoint. The native endpoint only shows workflows with MCP Server trigger nodes. The community package uses the REST API and shows ALL workflows.
**Why it works:** Gives full access to all 44 workflows instead of 0. Requires N8N_API_KEY (from n8n Settings > API) set via env var.
**Sessions validated:** 1 | **Last used:** 2026-03-02

## Anti-Patterns (NEVER Do These)

### Creating Bypass Scripts When MCP Fails (VIOLATION RECORDED 2026-02-27)
**What it looks like:** MCP call fails → agent writes a direct_post.js or similar file to call the API directly and bypasses the connector.
**Why it fails:** Creates junk files, exposes raw API keys to process memory/storage, clutters workspace, and wastes context on HTTP protocol handling instead of utilizing the defined MCP schema.
**Do this instead:** Report the error, suggest the fix, STOP. Rely ONLY on the configured server tools for integrations, *especially* if the server handles authentication directly.

### Powershell Standard Output Pipe `>` Interop
**What it looks like:** Running `node script.js > output.json` or `curl url > data.json` and trying to read the file in another language environment.
**Why it fails:** Windows PowerShell `>` defaults to `UTF-16LE` encoding, which breaks standard JSON parsers (`SyntaxError: Unexpected token ...`) in Node.js or Python expecting `UTF-8`.
**Do this instead:** Avoid pipe-redirections entirely. Use specific filesystem tools like `write_to_file` and `view_file` instead of bash-like file manipulation. Or use explicit `-Encoding utf8`.

### Posting Identical Content Across Platforms
**What it looks like:** Same exact text sent to X, LinkedIn, Instagram
**Why it fails:** Each platform has different char limits, audience, and tone expectations
**Do this instead:** Rewrite per platform. Same core message, different delivery.

### Guessing Library APIs Without Context7
**What it looks like:** Agent writes code using method names from training data
**Why it fails:** Libraries change. Training data is stale.
**Do this instead:** Always call Context7 to verify current API before writing code

### Deleting Files Without Scanning References
**What it looks like:** Remove or rename a file, but don't scan the project for files that reference it
**Why it fails:** Creates 10-20+ broken cross-references. Agents try to read non-existent files and lose context.
**Do this instead:** After ANY delete/rename: `grep -rn "filename" --include="*.md"` → fix every hit → verify with a second grep.

### Hardcoding Counts in Documentation
**What it looks like:** Writing "Sub-Agents (12)" or "Skills (40)" in CAPABILITIES.md or README.md
**Why it fails:** The actual count drifts as files are added/removed. Documentation becomes permanently stale.
**Do this instead:** During /sync or /commit, verify: `dir agents/*.md | measure | select Count` matches the documented number.

### Evolving Architecture Without Deprecating Old Files
**What it looks like:** Creating new entry points (CLAUDE.md, ANTIGRAVITY.md) but leaving the old monolithic file (AGENT_CORE_DIRECTIVES.md) in place
**Why it fails:** Multiple sources of truth. Edits go to the new files, old file rots, agents get confused about which to follow.
**Do this instead:** When a file is superseded: 1) Delete immediately, 2) Grep for refs, 3) Fix all refs, 4) Log in CHANGELOG.md.

### Calling Google Meet Link a "Calendar" or "Booking" Link `[VALIDATED]`
**What it looks like:** "Here's my calendar link" or "Book a call" with the Google Meet URL `https://meet.google.com/oqd-xpoq-fgw`
**Why it fails:** The Google Meet link is a **universal drop-in meeting room** — it does NOT let people pick a time slot, book an appointment, or interact with any calendar. Calling it a "calendar" is misleading and unprofessional.
**Do this instead:** Use language like: "Here's a quick meeting link — hop on whenever works" or "Here's a meeting link, no scheduling needed." Never say "calendar", "booking", "grab a time slot", or "schedule here" when referring to this link.
**CC corrected this:** 2026-03-04 | **Severity:** HIGH — affects all outbound communications.
