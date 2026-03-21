---
tags: [codebase, architecture, patterns]
---

# Codebase Architectural Patterns (2026-03-21)

## Key Findings from Code Analysis

### 1. Instagram DM Auto-Reply Engine

#### Intent Detection System (6 classes)
- **BOOKING**: Only explicit phrases ("book a call", "schedule meeting"). NOT vague signals.
- **PAYMENT**: Person mentions payment OR non-Stripe methods (Venmo, wire, e-transfer, etc.)
- **PRICING**: Cost/rate inquiries
- **INFO**: "What do you do?", "How does X work?"
- **GREETING**: Short "hey/hi/hello" with no other content
- **CONVO**: Everything else (default) — genuine conversation response
- **UNKNOWN**: <2 chars — no reply

#### Claude API Integration
- **Model**: claude-sonnet-4-6, max_tokens=150
- **System Prompt**: 45 lines of voice rules embedded in code
- **Voice Rules**: 2am conversation style, lowercase, no emojis/marketing, match energy, NEVER pitch
- **Payment Constraint**: ALL via Stripe only. Token: [GENERATE_PAYMENT_LINK:cents:label]
- **Context**: Last 1000 chars of conversation passed to Claude
- **Fallback**: Simple templates if API fails

#### Multi-Stage Auto-Reply Flow
1. Check DMs (unread only)
2. Extract last incoming message
3. If BOOKING + awaiting_time state → Parse datetime, create Calendar event, send Meet link
4. Else → Detect intent, build reply via Claude, send DM
5. Log to dm_replied.json (24h cooldown), Supabase (history)
6. Notify CC on Telegram ONLY for BOOKING intents

#### State Files
- `dm_replied.json`: username → {replied_at, intent} (24h cooldown)
- `dm_booking_state.json`: username → {stage, date, time, meet_link, event_id}
- `dm_notified.json`: Tracks which previews already Telegram-notified (no spam)

#### Browser Setup
- Persistent context: `tmp/ig-browser/`
- Headless: True
- Viewport: 1280x900
- Session continuity across cron runs

---

### 2. Scheduling/Cron System

#### Architecture
- **Source of Truth**: Supabase table `cron_jobs`
- **Not a runner**: n8n schedules. This is the registry.
- **10 Seed Jobs** defined (morning/afternoon/evening posts, lead follow-up, booking reminders, Stripe sync, reports)
- **Cron Format**: Standard expressions ("0 9 * * *")

#### Job Structure
{
  "name": "string",
  "schedule": "0 9 * * *",
  "action_type": "content_post|lead_followup|booking_reminder|stripe_sync|...",
  "action_config": {...}
  "is_active": bool
}

#### Commands
- list, add, toggle, run, due, seed, --json output

#### Credential Loading
All from `.env.agents` (BRAVO_SUPABASE_URL, BRAVO_SUPABASE_SERVICE_ROLE_KEY)

---

### 3. Skool Community Automation

#### No Official API
Uses Playwright MCP browser automation exclusively

#### Operations
1. **Edit Lesson**: Navigate → Click Edit → Find Tiptap editor → innerHTML injection → dispatch input (bubbles=true CRITICAL) → Save via JS → Wait 2s
2. **Batch Push**: Load HTML files from courses/ → For each: navigate directly → edit → save → wait → continue → report results
3. **About Page**: Same pattern, hard 1000-char limit

#### Content Format (Tiptap-compatible)
- h2, h3, p, strong, em, ul, ol, li, blockquote, code, a href
- NO: div, span, table, img, CSS styles

#### Callout Patterns
⚡ QUICK WIN, 💡 PRO TIP, 💀 COMMON MISTAKE, 🧠 KEY TAKEAWAY, 🔥 CHALLENGE, 🏆 BOSS LEVEL, ⚠️ WARNING, ✅ CHECKPOINT

#### Workflows
- `/skool-edit <target>`: Single lesson/about page
- `/skool-push <scope>`: Batch push all/course/lessons
- Both in `.agents/workflows/skool-*.md`

---

## Cross-Cutting Patterns

### CLI Design
- All scripts support `--json` for programmatic output (n8n compatible)
- Commands: check, list, run, send, add, toggle, etc.

### State Management
- **Local (fast)**: JSON files in tmp/
- **Persistent (history)**: Supabase tables
- **Dual write**: Important actions → both locations

### Playwright Pattern
- Persistent context with saved profile
- Headless mode
- Explicit waits (time.sleep)
- Session continuity

### Intent + State Machine
- Classify input → Semantic intent
- Intent → Action (not regex template rules)
- Multi-turn flows use state machines (not single-pass)

### Notification Control
- Only notify on actionable states (not routine execution)
- Track notified items to prevent spam
- Different thresholds per intent type

---

## Integration Map

Instagram DMs → Claude (replies) + Google Calendar (booking) + Telegram (notify) + Supabase (log)
Cron Jobs → n8n (scheduler) + Supabase (registry) + individual scripts
Skool Push → Playwright MCP + courses/SKOOL_REGISTRY.md

---

## Design Principles for New Development

1. Always support --json for agent/CLI consumption
2. Use state machines for multi-turn flows
3. Gate notifications (avoid spam)
4. Playwright > API when API missing
5. Dual persistence (file + DB)
6. Intent detection > regex patterns
7. Graceful degradation (fallback when API down)

