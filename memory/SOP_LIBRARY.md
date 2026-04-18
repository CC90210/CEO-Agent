---
tags: [sops, processes]
---
# SOP LIBRARY — Standard Operating Procedures (V5.5 Enhanced)

> SOPs are born from repeated patterns. When Bravo does the same thing 3+ times, it becomes an SOP.
> Each SOP has a success rate tracked over executions.
> **V5.5:** Probationary validation system, activation scoring, prerequisite tracking, Supabase sync.

> [[brain/BRAIN_LOOP]] | [[memory/PATTERNS]] | [[brain/DASHBOARD]]

## SOP Format

```
### SOP-[ID]: [Name]
**Category:** [content/code/deploy/research/automation/admin/finance]
**Status:** [PROBATIONARY] (< 3 successful sessions) | [VALIDATED] (3+ sessions) | [UNDER_REVIEW] (caused errors)
**Trigger:** [What activates this SOP]
**Prerequisites:** [What skills/context must be loaded first]
**Steps:**
1. [Step]
2. [Step]
3. [Step]
**Success Criteria:** [How to know it worked]
**Executions:** [count] | **Success Rate:** [percentage]
**Last Executed:** [date]
**Activation Score:** [0.0-1.0] (recency × 0.3 + frequency × 0.4 + confidence × 0.3)
```

## Active SOPs

### SOP-001: Social Media Content Creation & Publishing
**Category:** content
**Status:** `[PROBATIONARY]` — 2 executions, needs 1 more successful session
**Trigger:** CC says "Content:" or "Post:" or /content command
**Prerequisites:** CC's 5 content pillars (brain/USER.md), platform char limits (brain/SOUL.md)
**Steps:**
1. Map the request to one of CC's 5 content pillars
2. Write in CC's authentic voice (direct, no hustle-culture, transformation-focused)
3. Open with 2-second hook (pattern interrupt or bold statement)
4. Generate platform-specific versions:
   - X: Max 280 chars (including spaces, URLs, mentions)
   - LinkedIn: Max 3000 chars, professional but personal tone
   - Instagram: Max 2200 chars, visual-first messaging
   - TikTok: Max 4000 chars
   - Threads: Max 500 chars
5. Validate character count for EACH platform version
6. Present to CC for approval
7. Post via Zernio API (late_tool.py create or cross-post)
8. Log result in SESSION_LOG
**Success Criteria:** Post published, no character limit rejections, CC approves content
**Executions:** 2 | **Success Rate:** 50% (1st attempt failed on X char limit)
**Last Executed:** 2026-02-27

### SOP-002: Systematic Bug Investigation
**Category:** code
**Status:** `[VALIDATED]` — 3 executions, 100% success rate
**Trigger:** CC reports a bug, /debug command, error in logs
**Prerequisites:** Brain Loop (steps 1-8), relevant codebase context
**Steps:**
1. Read the error message/description carefully
2. Hypothesize the root cause (don't guess — reason from evidence)
3. Search codebase for relevant files (Grep/Glob)
4. Read the files, trace the logic
5. Identify the root cause with evidence
6. Apply minimal fix
7. Verify: build passes, no regressions
8. If fix fails after 3 attempts → STOP, report findings to CC
9. Log mistake + pattern to memory files
**Success Criteria:** Bug fixed, build passes, root cause documented
**Executions:** 3 | **Success Rate:** 100%
**Last Executed:** 2026-02-27

### SOP-003: Session Start Protocol (Heartbeat)
**Category:** admin
**Status:** `[VALIDATED]` — Core protocol, always executes
**Trigger:** Session begins
**Prerequisites:** brain/SOUL.md, brain/STATE.md, brain/HEARTBEAT.md, brain/INTERACTION_PROTOCOL.md
**Steps:**
1. Read brain/SOUL.md (identity check)
2. Read brain/STATE.md (current operational state)
3. Read memory/ACTIVE_TASKS.md (pending work)
4. Read memory/SESSION_LOG.md (last 3 entries)
5. Check git status
6. Report heartbeat status to CC
7. Await orders
**Success Criteria:** Bravo is oriented, CC knows system status
**Executions:** 0 | **Success Rate:** N/A (new SOP)
**Last Executed:** N/A

### SOP-004: Session End Protocol (Self-Heal + Sync)
**Category:** admin
**Status:** `[VALIDATED]` — Core protocol, always executes
**Trigger:** Session ending, /self-heal command
**Prerequisites:** brain/INTERACTION_PROTOCOL.md (Section 8)
**Steps:**
1. Scan for junk files in project root (*.js, *.txt, *.log, debug dumps)
2. Check for uncommitted changes (git status)
3. Update memory/ACTIVE_TASKS.md (mark completed, flag blocked)
4. Append to memory/SESSION_LOG.md
5. Extract new patterns → memory/PATTERNS.md (tag `[PROBATIONARY]` if new)
6. Extract new mistakes → memory/MISTAKES.md
7. Generate Reflexion entries for any failed tasks → memory/SELF_REFLECTIONS.md
8. Update brain/STATE.md with final state
9. Supabase sync: update agent_state, insert session_logs, flush agent_traces, insert new memories
10. Git commit: stage brain/ + memory/ → `bravo: sync — session YYYY-MM-DD`
11. Ask CC if ready to push to remote
12. Compress SESSION_LOG if > 200 lines
13. State to CC: "Memory synced. [X] files updated, [Y] traces logged, [Z] new learnings captured."
**Success Criteria:** Workspace clean, memory updated, state current, Supabase synced, git committed
**Executions:** 2 | **Success Rate:** 100%
**Last Executed:** 2026-02-28

### SOP-005: MCP Tool Routing (Query → Tool → Response)
**Category:** automation
**Status:** `[PROBATIONARY]` — New SOP, 2026-03-02
**Trigger:** ANY user query that can be answered by an MCP tool
**Prerequisites:** MCP servers running, credentials valid
**Steps:**
1. Parse user query — identify the TOPIC (n8n, social media, database, web, docs, memory)
2. Map topic to MCP server using this table:
   - n8n/workflows/automations → `n8n-mcp` → `search_workflows`, `get_workflow_details`, `execute_workflow`
   - Social media/posts/scheduling → `Late` → `posts_list`, `posts_create`, `accounts_list`, `posts_cross_post`
   - Database/SQL/tables → `Supabase` → `execute_sql`, `list_tables`, `apply_migration`
   - Web browsing/scraping → `Playwright` → `browser_navigate`, `browser_snapshot`
   - Library docs/code examples → `Context7` → `resolve-library-id`, `query-docs`
   - Knowledge/memory → `Memory` → `search_nodes`, `create_entities`
   - Payments/Stripe → `Stripe` → (see Stripe MCP tools)
3. Call the MCP tool IMMEDIATELY — do not describe what you would do
4. Return the REAL DATA from the tool response to the user
5. If the tool fails, report the error and suggest a fix — do NOT create workaround scripts
**Success Criteria:** User gets real data from the actual tool, not a description of what could be done
**Executions:** 0 | **Success Rate:** N/A
**Last Executed:** N/A

### SOP-006: N8N Workflow Management
**Category:** automation
**Status:** `[PROBATIONARY]` — New SOP, 2026-03-02
**Trigger:** CC asks to list, search, execute, or manage n8n workflows
**Prerequisites:** `skills/n8n-mcp-integration/SKILL.md`, N8N_API_KEY in .env.agents
**Steps:**
1. Call `search_workflows` to list/search (use `limit=200` for full list, `query="..."` for search)
2. For details: call `get_workflow_details(workflowId="...")` — ALWAYS before executing
3. For execution: call `execute_workflow(workflowId="...", inputs={...})` with proper input schema
4. For REST API fallback: use `curl -H "X-N8N-API-KEY: $N8N_API_KEY" https://n8n.srv993801.hstgr.cloud/api/v1/...`
5. Report results clearly — workflow name, status, node count, trigger type
**Success Criteria:** Workflows listed/executed correctly, real data returned
**Executions:** 0 | **Success Rate:** N/A
**Last Executed:** N/A

### SOP-007: Weekly Revenue Review (CEO)
**Category:** finance
**Status:** `[PROBATIONARY]` — New SOP, 2026-03-26
**Trigger:** Monday morning, /briefing command, CC asks about revenue
**Prerequisites:** Stripe CLI tool, revenue_engine.py, ACTIVE_TASKS.md
**Steps:**
1. Pull current MRR: `python scripts/revenue_engine.py mrr --json`
2. Compare against $5,000 USD target — calculate gap and pace
3. Check revenue concentration (% from top client)
4. Flag if concentration >80% (CRITICAL) or >60% (HIGH risk)
5. Review pipeline: how many leads at each stage?
6. Calculate: at current close rate, when do we hit target?
7. Report to CC in 5 lines or less — MRR, gap, pace, risk, #1 action
**Success Criteria:** CC knows exact MRR, gap to target, and what to do next
**Executions:** 0 | **Success Rate:** N/A
**Last Executed:** N/A

### SOP-008: Client Health Check (CEO)
**Category:** client
**Status:** `[PROBATIONARY]` — New SOP, 2026-03-26
**Trigger:** Weekly (part of /briefing), or when CC asks about a client
**Prerequisites:** Supabase leads table, lead_interactions, revenue_events
**Steps:**
1. List all clients with status=client in CRM
2. For each client, check:
   - Last interaction date (flag if >14 days)
   - Revenue contribution (flag if >50% of total MRR)
   - Deliverable status (on-time, overdue, upcoming)
   - Any negative signals (complaints, slow responses, scope changes)
3. Score each client: HEALTHY (all good), AT-RISK (1+ flag), CRITICAL (2+ flags or revenue >70%)
4. For AT-RISK/CRITICAL: generate specific action (e.g., "Send check-in email to Bennett")
5. Report to CC: client list with scores and recommended actions
**Success Criteria:** No client goes unmonitored for more than 7 days
**Executions:** 0 | **Success Rate:** N/A
**Last Executed:** N/A

### SOP-009: Pipeline Review & Follow-Up (CEO)
**Category:** client
**Status:** `[PROBATIONARY]` — New SOP, 2026-03-26
**Trigger:** Monday + Thursday, or CC asks about leads/pipeline
**Prerequisites:** lead_engine.py, email_engine.py, booking_engine.py
**Steps:**
1. Pull full pipeline: `python scripts/lead_engine.py pipeline --json`
2. Identify leads with no interaction in 7+ days → generate follow-up actions
3. Identify warm leads (score >60) → prioritize for outreach today
4. Check if any booked calls are coming up this week: `python scripts/booking_engine.py slots list --json`
5. For each warm lead, draft a follow-up action (email, call, or DM)
6. Report: total leads, warm count, overdue follow-ups, booked calls, recommended actions
7. If CC approves follow-ups, execute via email_engine.py or suggest manual action
**Success Criteria:** No warm lead goes cold without a follow-up attempt
**Executions:** 0 | **Success Rate:** N/A
**Last Executed:** N/A

### SOP-010: Weekly Revenue Review
**Category:** finance
**Status:** `[PROBATIONARY]` — New SOP, 2026-03-28
**Trigger:** Every Monday morning (part of /briefing)
**Prerequisites:** Stripe access, Supabase access
**Steps:**
1. Run `python scripts/stripe_tool.py balance` — check current balance
2. Run `python scripts/revenue_engine.py dashboard` — pull MRR breakdown
3. Compare current MRR vs target ($5,000 USD by May 15, 2026)
4. Calculate gap and required weekly growth rate
5. Check pipeline: how many leads in proposal/negotiation stage?
6. IF gap > $1,000: flag as CRITICAL, recommend specific outreach actions
7. IF gap < $500: flag as ON TRACK, recommend optimization actions
8. Log revenue snapshot to memory/SESSION_LOG.md
**Success Criteria:** Weekly revenue visibility, gap clearly quantified, action plan generated
**Failure Handling:** If Stripe unavailable, use last known MRR from STATE.md + manual update prompt
**Executions:** 0 | **Success Rate:** N/A
**Last Executed:** N/A
**Owner:** Bravo

### SOP-011: Client Onboarding (New Client)
**Category:** client
**Status:** `[PROBATIONARY]` — New SOP, 2026-03-28
**Trigger:** New client signs contract or pays first invoice
**Prerequisites:** Signed contract, payment received, client contact info
**Steps:**
1. Create client record in Supabase `leads` table with status='client'
2. Send welcome email using `data/templates/emails/client-checkin.md` (adapted for onboarding)
3. Schedule kickoff call (within 5 business days)
4. Generate project brief using `data/templates/documents/project-brief.md`
5. Set up access: create Slack channel or communication thread
6. Run discovery session: document requirements, pain points, success criteria
7. Create project plan with milestones using `skills/project-management/SKILL.md`
8. Set up recurring check-ins (bi-weekly or monthly)
9. Add client to health monitoring (`scripts/client_health.py`)
10. Log onboarding to memory/SESSION_LOG.md
**Success Criteria:** Client fully onboarded within 5 business days, kickoff completed, project plan approved
**Failure Handling:** If client unresponsive > 3 days, escalate with phone call
**Executions:** 0 | **Success Rate:** N/A
**Last Executed:** N/A
**Owner:** CC + Bravo

### SOP-012: Quarterly Business Review (QBR)
**Category:** admin
**Status:** `[PROBATIONARY]` — New SOP, 2026-03-28
**Trigger:** Last week of each quarter (March, June, September, December)
**Prerequisites:** 90 days of data in Stripe, Supabase, memory files
**Steps:**
1. Run `python scripts/financial_model.py unit-economics` — calculate CAC, LTV, payback
2. Run `python scripts/financial_model.py concentration` — check Herfindahl index
3. Run `python scripts/competitive_intel.py report` — competitive landscape update
4. Run `python scripts/client_health.py report` — full client health snapshot
5. Grade previous quarter's OKRs (0.0-1.0 scale per key result)
6. Identify top 3 wins and top 3 misses
7. Run scenario modeling: bull/base/bear for next quarter
8. Draft next quarter's OKRs (max 3 objectives, 3-5 KRs each)
9. Compile into QBR report using `skills/strategic-planning/SKILL.md` template
10. Present to CC for review and approval
11. Log approved OKRs to brain/STATE.md
**Success Criteria:** Complete QBR report with graded OKRs, new OKRs approved, strategic adjustments documented
**Failure Handling:** If data gaps exist, note them in report and use best available estimates
**Executions:** 0 | **Success Rate:** N/A
**Last Executed:** N/A
**Owner:** Bravo

### SOP-013: Proposal-to-Close Pipeline
**Category:** client
**Status:** `[PROBATIONARY]` — New SOP, 2026-03-28
**Trigger:** Lead reaches "discovery" stage in pipeline
**Prerequisites:** Discovery call completed, pain points identified, budget range known
**Steps:**
1. Generate proposal: `python scripts/proposal_generator.py create --client "Name" --type retainer --tier growth`
2. Review proposal against `skills/proposal-generation/SKILL.md` checklist
3. Send proposal with cover email (personalized, reference specific pain points from discovery)
4. Day 1: Confirm receipt, answer questions
5. Day 3: Soft follow-up if no response
6. Day 7: Value-add follow-up (share relevant case study or insight)
7. Day 14: Direct ask — "Ready to move forward or any concerns?"
8. IF accepted: Trigger SOP-011 (Client Onboarding)
9. IF rejected: Log reason in win/loss tracker, move to nurture sequence
10. IF no response after 30 days: Breakup email, move to cold nurture
**Success Criteria:** Proposal sent within 48 hours of discovery, follow-up cadence executed, outcome logged
**Failure Handling:** If proposal rejected, analyze reason and update pricing/positioning if pattern emerges
**Executions:** 0 | **Success Rate:** N/A
**Last Executed:** N/A
**Owner:** CC (sends) + Bravo (generates, tracks)

### SOP-014: Monthly Competitive Intelligence Update
**Category:** research
**Status:** `[PROBATIONARY]` — New SOP, 2026-03-28
**Trigger:** First Monday of each month
**Prerequisites:** `data/competitors.json` populated with at least 3 competitors
**Steps:**
1. Load competitor list from `data/competitors.json`
2. For each competitor: check pricing page via Playwright, note changes
3. Check G2/Capterra for new reviews mentioning competitors
4. Check LinkedIn/X for competitor content and positioning changes
5. Check job postings (signals growth areas or pivots)
6. Update `data/competitors.json` with findings
7. Regenerate battlecards for any competitor with significant changes
8. Generate monthly competitive summary
9. IF competitor made a major move (price drop, new feature, funding): alert CC immediately
10. Log to memory/SESSION_LOG.md
**Success Criteria:** All tracked competitors reviewed, changes documented, battlecards current
**Failure Handling:** If Playwright can't access a site, note as "BLOCKED" and try alternative data sources
**Executions:** 0 | **Success Rate:** N/A
**Last Executed:** N/A
**Owner:** Bravo (researcher agent)

### SOP-015: Meeting Prep & Follow-Up
**Category:** admin
**Status:** `[PROBATIONARY]` — New SOP, 2026-03-28
**Trigger:** Any scheduled meeting on CC's calendar
**Prerequisites:** Calendar access (Google Workspace), meeting details (who, what, when)
**Steps:**
1. Scan calendar for meetings in next 24 hours
2. For each meeting: search memory/knowledge graph for relationship history
3. Check lead tracker for pipeline stage and last interaction
4. Pull recent email threads with the contact
5. Generate pre-meeting brief using `skills/meeting-automation/SKILL.md` template
6. Present brief to CC before the meeting
7. After meeting: prompt CC for key decisions and action items
8. Draft follow-up email within 2 hours
9. Update CRM/lead tracker with interaction notes
10. Schedule next touchpoint
**Success Criteria:** Brief delivered before every meeting, follow-up sent within 2 hours, CRM updated
**Failure Handling:** If no prior history found, generate brief from company research only
**Executions:** 0 | **Success Rate:** N/A
**Last Executed:** N/A
**Owner:** Bravo (chief of staff agent)

### SOP-016: Content Publishing Cadence
**Category:** content
**Status:** `[PROBATIONARY]` — New SOP, 2026-03-28
**Trigger:** Daily (part of morning routine)
**Prerequisites:** Content Bible loaded, Late/Zernio accounts connected
**Steps:**
1. Check content calendar: what's scheduled for today?
2. IF nothing scheduled: generate content using daily pillar rotation (Sobriety Log / Quote Drop / CEO Log)
3. Draft content using `../Marketing-Agent/skills/content-engine/SKILL.md` and platform-specific templates from `data/templates/content/`
4. Validate character limits: X=280, Threads=500, IG=2200, LinkedIn=3000, TikTok=4000
5. Present draft to CC for approval (or auto-publish if CC has pre-approved the pillar)
6. Publish via `python scripts/late_tool.py create --text "..." --account <id>`
7. Cross-post to relevant platforms using profile-based publishing
8. Log published content to memory/SESSION_LOG.md
9. Check engagement after 24 hours: note top-performing posts
**Success Criteria:** Minimum 1 post/day across at least 2 platforms
**Failure Handling:** If Late API fails, draft content and save for manual posting
**Executions:** 0 | **Success Rate:** N/A
**Last Executed:** N/A
**Owner:** Bravo (social publisher agent)

### SOP-017: Weekly Knowledge Maintenance
**Category:** admin
**Status:** `[PROBATIONARY]` — New SOP, 2026-03-28
**Trigger:** Every Sunday (part of /knowledge-maintenance workflow)
**Prerequisites:** Access to all memory files
**Steps:**
1. Check SESSION_LOG.md line count — compress if >200 lines (archive to ARCHIVES/)
2. Review ACTIVE_TASKS.md — remove completed tasks older than 7 days
3. Scan PATTERNS.md for [PROBATIONARY] entries with 3+ successful uses → promote to [VALIDATED]
4. Check MISTAKES.md for recurring themes → create prevention SOPs if pattern found
5. Verify data/competitors.json freshness — flag entries older than 30 days
6. Run confidence decay on LONG_TERM.md facts (>30 days: -0.1, >90 days: -0.3)
7. Verify all ``wiki-links`` in brain/ and memory/ files resolve correctly
8. Update brain/STATE.md with current operational snapshot
9. Log maintenance summary to SESSION_LOG.md
**Success Criteria:** All memory files within size limits, no stale data, all links valid
**Failure Handling:** If a file is corrupted, restore from last git commit
**Executions:** 0 | **Success Rate:** N/A
**Last Executed:** N/A
**Owner:** Bravo

---

## SOP Promotion Pipeline

*Patterns are promoted to SOPs after 3+ executions with consistent steps.*
*SOPs start as `[PROBATIONARY]` → promoted to `[VALIDATED]` after 3 successful sessions → `[UNDER_REVIEW]` if errors occur.*

| Candidate Pattern | Observations | Status | Next Action |
|-------------------|-------------|--------|-------------|
| Playwright research → brief synthesis | 0 | Watching | Need 3 observations |
| Git branch → PR → Vercel preview | 1 | Watching | Need 2 more observations |
| Client onboarding flow | 0 | Template exists | Needs first execution |
| n8n workflow creation | 0 | Template exists | Needs first execution |
| Self-evolution file update cycle | 1 | Watching | Research → Apply to files → DB sync → Git |

## Automatic SOP Detection Rules

When the heartbeat (Step 6: Growth Check) detects:
- 3+ task completions with similar steps → auto-create `[PROBATIONARY]` SOP stub
- A `[PROBATIONARY]` SOP used successfully in 3+ sessions → promote to `[VALIDATED]`
- A SOP that causes errors → demote to `[UNDER_REVIEW]`, flag for CC
- A SOP not used in 30+ days → flag for archival consideration

## Retired SOPs

*SOPs that are no longer relevant. Kept for reference.*

(None yet)
