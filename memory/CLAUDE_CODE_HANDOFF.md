---
tags: [handoff, delegation, critical]
---

# CLAUDE CODE HANDOFF — Sentient Autonomy Buildout

> **From:** Bravo via Antigravity (2026-04-20)
> **To:** Claude Code (next session)
> **Priority:** P0 — This is the foundational infrastructure CC needs to make autonomous agents stop miscalculating.
> **Context:** CC ran a deep intelligence audit. Read the full report FIRST before doing any work.

## STEP 0: READ THE AUDIT FIRST

**Read this file before anything else:**
```
Antigravity artifact: bravo_intelligence_audit.md
```
The artifact lives in Antigravity's brain directory. The key findings are also summarized in `memory/SESSION_LOG.md` (top entry, 2026-04-20).

**Also read:**
- `memory/ACTIVE_TASKS.md` → "Sentient Autonomy Buildout" section at the bottom
- `brain/STATE.md` → updated header with intelligence level assessment

## WHAT ANTIGRAVITY ALREADY DID

1. **Full file structure audit** — read 15+ critical files, mapped all 60 scripts, 152 skills, 17 agents, 35 workflows
2. **Identified 8 critical gaps** preventing autonomous agent intelligence (see audit artifact)
3. **Updated state files** — brain/STATE.md, memory/ACTIVE_TASKS.md, memory/SESSION_LOG.md
4. **Created 3-phase roadmap** — Action Awareness → Interaction Intelligence → Autonomous Reasoning
5. **Corrected architecture understanding** — CC's inbound email agent is the N8N workflow `OASIS Inbound Qualifier (Bravo Aware)` (ID: 1cGIN32alM8sf8OV), a 68-node N8N workflow with 5-category classifier, NOT a Gmail script

## WHAT CLAUDE CODE NEEDS TO BUILD

### WORKLOAD 1: Phase 1 — Action Awareness (THE FIX for duplicate emails)

This is the #1 problem CC described: agents don't check what they've already done before acting.

#### 1A. Create `agent_actions` Supabase table

```sql
CREATE TABLE agent_actions (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  entity_type TEXT NOT NULL,          -- 'lead', 'client', 'contact', 'prospect'
  entity_id TEXT NOT NULL,            -- UUID or email of the entity
  entity_name TEXT,                   -- Human-readable name
  action_type TEXT NOT NULL,          -- 'email_sent', 'dm_sent', 'call_scheduled', 'follow_up', 'meeting_booked'
  channel TEXT NOT NULL,              -- 'email', 'instagram', 'telegram', 'phone', 'skool', 'linkedin'
  content_summary TEXT,               -- What was communicated (first 200 chars)
  agent_source TEXT NOT NULL,         -- Which script/agent performed this: 'outreach_engine', 'email_engine', 'funnel_nurture', 'n8n_inbound', 'manual'
  cooldown_until TIMESTAMPTZ,         -- When the next action on this entity+channel is allowed
  metadata JSONB DEFAULT '{}'::jsonb,  -- Extra context (email subject, template used, etc.)
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes for fast pre-action lookups
CREATE INDEX idx_agent_actions_entity ON agent_actions(entity_id, channel, created_at DESC);
CREATE INDEX idx_agent_actions_cooldown ON agent_actions(entity_id, cooldown_until);
CREATE INDEX idx_agent_actions_type ON agent_actions(action_type, created_at DESC);
CREATE INDEX idx_agent_actions_source ON agent_actions(agent_source, created_at DESC);

-- Daily cap tracking
CREATE INDEX idx_agent_actions_daily ON agent_actions(channel, created_at);
```

Run this via: `python scripts/supabase_tool.py sql "<the SQL>" --project bravo`

#### 1B. Create `scripts/action_guard.py`

This is the core library. Every outbound engine must call it BEFORE acting.

**Required functions:**

```python
def can_act(entity_id: str, action_type: str, channel: str, cooldown_hours: int = 72) -> dict:
    """
    Check if an action is allowed on this entity.
    Returns: {"allowed": bool, "reason": str, "last_action": dict|None, "daily_count": int}
    
    Checks:
    1. Was this entity+channel contacted within cooldown_hours? If yes → blocked
    2. Has the daily cap for this channel been hit? If yes → blocked
    3. Is this entity on the CASL suppression list? If yes → blocked
    """

def log_action(entity_id: str, entity_name: str, entity_type: str, 
               action_type: str, channel: str, content_summary: str,
               agent_source: str, cooldown_hours: int = 72, metadata: dict = None) -> str:
    """
    Log an action to the agent_actions table and set cooldown_until.
    Returns: action UUID
    """

def get_entity_history(entity_id: str, limit: int = 20) -> list:
    """
    Get the full action history for an entity across all channels.
    Returns: list of action dicts, newest first
    """

def get_daily_stats(channel: str = None) -> dict:
    """
    Get today's action counts by channel.
    Returns: {"email": 5, "instagram": 2, "total": 7}
    """

# Default cooldowns (configurable)
DEFAULT_COOLDOWNS = {
    "email": 72,       # 3 days between emails to same lead
    "instagram": 48,   # 2 days between DMs
    "phone": 168,      # 7 days between calls  
    "linkedin": 72,    # 3 days
    "skool": 24,       # 1 day (community is higher frequency)
}

# Daily caps
DAILY_CAPS = {
    "email": 50,       # Max 50 outbound emails per day
    "instagram": 30,   # Max 30 DMs per day
    "linkedin": 20,    # Max 20 connection requests/messages
}
```

**Pattern:** Same as all other scripts — reads `.env.agents`, uses `BRAVO_SUPABASE_URL` + `BRAVO_SUPABASE_SERVICE_ROLE_KEY`, argparse CLI with `--json` flag. Should also be importable as a library.

**CLI interface:**
```
python scripts/action_guard.py check --entity-id <id> --channel email
python scripts/action_guard.py history --entity-id <id>
python scripts/action_guard.py stats
python scripts/action_guard.py stats --json
```

#### 1C. Wire action_guard into existing engines

**`scripts/outreach_engine.py` — `cmd_send()` function (line ~286):**
BEFORE the `send_outreach()` call, add:
```python
from action_guard import can_act, log_action

check = can_act(args.lead_id, "email_sent", "email")
if not check["allowed"]:
    print(f"BLOCKED: {check['reason']}", file=sys.stderr)
    if output_json:
        print(json.dumps({"status": "blocked", "reason": check["reason"]}))
    return
```
AFTER successful send, add:
```python
log_action(args.lead_id, lead_name, "lead", "email_sent", "email",
           subject[:200], "outreach_engine")
```

**`scripts/email_engine.py` — wherever emails are sent:**
Same pattern. Import action_guard, check before sending, log after sending.

**`scripts/funnel_nurture.py` — `run_nurture()` function (line ~215):**
Before sending Day 2 or Day 5 email, add the `can_act()` check. This SUPPLEMENTS the existing `follow_up_count` guard — the action_guard catches emails sent by OTHER engines.

**`scripts/outreach_batch.py` — the batch loop:**
Before each lead in the batch, check `can_act()`. Skip if blocked.

#### 1D. Register in routing docs

After building, update:
- `brain/QUICK_REFERENCE.md` — add action_guard to CLI tools table
- `brain/CAPABILITIES.md` — add to business ops engines section
- `brain/ORCHESTRATION.md` — add to routing ambiguity table ("Check action history" → action_guard.py)

---

### WORKLOAD 2: Full File Structure Upgrade

CC said "not just that specific problem — the whole file structure needs best practices." Here's what needs attention:

#### 2A. Brain Loop Enhancement

**File:** `brain/BRAIN_LOOP.md`

Add a new step between ASSESS (Step 3) and PLAN (Step 4):

```markdown
### Step 3.5: ACTION HISTORY CHECK (New — Sentient Guard)
> Before planning any outbound action, check the action ledger.

- Query `agent_actions` for the target entity
- If action was taken within cooldown period → SKIP or ADAPT
- If approaching daily cap → THROTTLE
- Log the check result for audit trail
```

#### 2B. Heartbeat Enhancement

**File:** `brain/HEARTBEAT.md`

Add a new session-start check:

```markdown
### 7. Action Ledger Health (Priority: HIGH)
CHECK: Are autonomous actions staying within bounds?
- Query agent_actions for last 24h → count by channel
- Any channel over 80% of daily cap? → WARN
- Any entity contacted more than once within cooldown? → ERROR (idempotency breach)
- Stale cooldowns (cooldown_until in the past by >7 days)? → CLEAN
ACTION: Report action health. Flag any idempotency breaches.
```

#### 2C. Architecture Doc Update

**File:** `ARCHITECTURE.md`

Add a new section documenting the Action Awareness layer:

```markdown
## Action Awareness Layer (V5.6)

Every autonomous outbound action passes through the Action Guard:

1. **Pre-check**: `action_guard.can_act()` queries agent_actions table
2. **Execute**: Engine sends the email/DM/call
3. **Log**: `action_guard.log_action()` records the action with cooldown
4. **Audit**: Heartbeat monitors for idempotency breaches

Tables: agent_actions (Supabase)
Script: scripts/action_guard.py
Wired into: outreach_engine, email_engine, funnel_nurture, outreach_batch
```

#### 2D. N8N Inbound Qualifier Awareness

**CRITICAL CONTEXT for Claude Code:**

CC's inbound email agent is NOT a Python script — it's the N8N workflow `OASIS Inbound Qualifier (Bravo Aware)` (ID: `1cGIN32alM8sf8OV`). This is a 68-node workflow that:

- Polls Gmail every 5 minutes for unread emails
- Classifies into 5 categories via `textClassifier` node
- Routes to specialized agents: Oasis Chat Agent, Business Opportunities Agent, Internal & Operations Agent, Oasis Email Agent, SENTINEL
- Has Google Calendar availability check
- Can auto-reply via Gmail
- Sends Telegram notifications to CC
- Has a Telegram trigger for manual interaction
- Uses OpenAI Chat Models (not Claude) + Google Gemini for some agents
- Has memory buffer windows for conversation context

**The N8N workflow is OUTSIDE the Bravo file structure** — it lives in N8N's cloud/self-hosted instance. Bravo can query it via `python scripts/n8n_tool.py get 1cGIN32alM8sf8OV` but cannot directly edit its nodes.

**What Bravo CAN do:** The action_guard system should also work for N8N. When the N8N inbound qualifier sends an email reply, it should log to `agent_actions` with `agent_source = 'n8n_inbound'`. This can be done by:
1. Adding an HTTP Request node in N8N that POSTs to a Supabase webhook/function
2. OR creating a lightweight webhook endpoint that action_guard.py exposes
3. OR having the N8N workflow write directly to the `agent_actions` Supabase table (simplest — N8N already has Supabase integration)

Document this integration path but don't implement N8N changes — CC manages N8N directly.

#### 2E. Scheduler Integration

**File:** `scripts/scheduler.py`

The scheduler should log a daily action summary to Telegram at end of day. Add to the scheduler's daily reporting:

```python
# In the daily summary handler:
from action_guard import get_daily_stats
stats = get_daily_stats()
# Include in Telegram digest: "Actions today: 5 emails, 2 DMs, 0 calls"
```

#### 2F. CASL Compliance Integration

**File:** `scripts/casl_compliance.py`

The action_guard should call `should_suppress()` as part of `can_act()` for email channel. This centralizes ALL pre-send checks into one call.

---

### WORKLOAD 3: Documentation & Governance

#### 3A. Create `skills/action-awareness/SKILL.md`

New skill documenting the action guard system:
- When to use (before ANY outbound communication)
- API reference (can_act, log_action, get_entity_history, get_daily_stats)
- Default cooldowns and caps
- How to override for urgent CC-approved actions
- Integration with CASL compliance
- How N8N workflows should log actions

#### 3B. Update `brain/AGENTS.md`

Add action awareness to every agent that does outbound communication:
- revenue-hunter → must check action_guard before any outreach
- chief-of-staff → must check before client follow-ups
- social-publisher → must check before DMs

#### 3C. Update entry points

If action_guard changes any routing rules, update all 3 entry points:
- CLAUDE.md
- GEMINI.md  
- ANTIGRAVITY.md

---

## EXECUTION ORDER

1. Read the audit artifact first
2. Create Supabase table (1A)
3. Build action_guard.py (1B) 
4. Wire into outreach_engine.py (1C)
5. Wire into email_engine.py (1C)
6. Wire into funnel_nurture.py (1C)
7. Wire into outreach_batch.py (1C)
8. Update brain/BRAIN_LOOP.md (2A)
9. Update brain/HEARTBEAT.md (2B)
10. Update ARCHITECTURE.md (2C)
11. Create skill file (3A)
12. Update routing docs (1D + 3B + 3C)
13. Test: `python scripts/action_guard.py stats --json`
14. Test: `python scripts/action_guard.py check --entity-id test --channel email`
15. Sync: STATE.md, ACTIVE_TASKS.md, SESSION_LOG.md

## WHAT NOT TO DO

- Do NOT edit N8N workflows — CC manages those directly
- Do NOT create ad-hoc scripts in tmp/ — use scripts/ directory
- Do NOT refactor unrelated code — surgical changes only (GEMINI.md Rule: Surgical Changes)
- Do NOT hardcode API keys — everything reads from .env.agents
- Do NOT touch SOUL.md — immutable, CC only

## VERIFICATION

After building, run:
```bash
python scripts/action_guard.py --help
python scripts/action_guard.py stats --json
python scripts/action_guard.py check --entity-id test-lead-123 --channel email --json
python scripts/supabase_tool.py sql "SELECT count(*) FROM agent_actions" --project bravo
```

All must pass. Then update memory files and say "Memory synced."
