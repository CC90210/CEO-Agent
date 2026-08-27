---
tags: [docs]
last_updated: 2026-08-27
superseded_by: docs/APEX_SYSTEM_MESSAGE.md
---

> ## ⚠️ SUPERSEDED 2026-08-27 — sections 2-4 describe a retired database
>
> This document was written 2026-06-19 against **Supabase project
> `phctllmtsogkovoilwos`**. The empire migrated to **Turso on 2026-08-09**, so
> the REST recipes, base URL, and `BRAVO_SUPABASE_SERVICE_ROLE_KEY` auth in §2-4
> now point at a database that is no longer the source of truth. An agent
> following them today is talking to the wrong system.
>
> **The current contract is [[docs/APEX_SYSTEM_MESSAGE]].**
>
> What §5-7 got RIGHT and is still true: two channels (Telegram = human↔agent,
> the table = agent↔agent), react only to the peer's rows, debounce, and prove
> the wire with a round-trip test rather than assuming it.
>
> What it got WRONG, and why the rebuild happened: it made claiming a
> *convention* (`files` as free text, compared by exact string) rather than a
> *mechanism*. Measured over the 90 days to 2026-08-27 that convention detected
> **zero** collisions while 226 of 1,596 files in oasis-command-center were
> touched by both sides, with 117 same-file cross-side edits inside 48h. Claims
> are now repo-scoped path leases with a TTL, enforced by a pre-edit hook —
> see `scripts/integrations/coord_claim.py` and `scripts/state/coord_guard.py`.

# OASIS Agent ↔ Agent Coordination Spec (Bravo ↔ APEX)

**For: Adon / APEX (KNUT).  From: CC / Bravo.  v1 — 2026-06-19.**

This is the contract for how **APEX** (Adon's agent) and **Bravo** (CC's agent)
coordinate **autonomously**. Hand this to APEX and implement the APEX side; the
Bravo side is already built to this exact shape.

---

## 0. The one thing that's missing right now

Bravo's side is live: it writes its status to the shared table and reads APEX's.
**APEX is currently posting only to the Telegram group, not to the shared
table** — so Bravo can't see APEX (Telegram blocks bots from seeing each other's
messages; that's a hard platform rule). The table is the ONLY machine-to-machine
channel. **APEX must read AND write the `agent_activity` table.** That's the work.

---

## 1. The two channels (and why)

| Channel | Direction | Mechanism |
|---|---|---|
| **Telegram group** `-5165125484` | human ↔ agent | CC + Adon talk; each agent **posts** status lines so the humans watch live. (Both bots can post; neither bot can *read* the other bot.) |
| **`agent_activity` table** | **agent ↔ agent** | The real coordination wire. Each agent INSERTs its status and SELECTs the other's. **This is the channel APEX must implement.** |

Rule of thumb: **post to Telegram for the humans; write to the table for the other agent.** Do both on every status change.

---

## 2. Credentials (APEX already has these — nothing new needed)

- **Supabase project:** `phctllmtsogkovoilwos` → `BRAVO_SUPABASE_URL` = `https://phctllmtsogkovoilwos.supabase.co`
- **Auth:** `BRAVO_SUPABASE_SERVICE_ROLE_KEY` (the service-role key already in APEX's env). Use it as both the `apikey` header and the `Authorization: Bearer` token. service_role bypasses RLS, so reads/writes to `agent_activity` just work.

> Note for Adon: that key is project-wide (it can touch every table, not just this one). If you'd rather scope APEX down, tell CC and Bravo will mint a narrow `agent_activity`-only credential/RPC. Either way the protocol below is identical.

---

## 3. The table (already created — do NOT recreate it)

```
agent_activity (
  id          uuid primary key default gen_random_uuid(),
  agent       text not null,        -- 'apex'  (APEX writes this)  | 'cc-agent' (Bravo writes this)
  status      text not null,        -- 'start' | 'working' | 'done' | 'blocked'
  task        text not null,        -- short human-readable task name
  files       text[],               -- files/areas being touched (the "claim")
  branch      text,                 -- git branch
  detail      text,                 -- freeform note (keep < ~1500 chars)
  created_at  timestamptz not null default now()
)
```

**Identity values (must match exactly):**
- APEX writes rows with `agent = "apex"`.
- APEX reads Bravo's rows with `agent = "cc-agent"`.
- (Bravo reads peers where `agent = "apex"`. If you must use `"knut"` instead, tell CC so Bravo adds it — otherwise use `"apex"`.)

---

## 4. REST API (no SDK required)

Base: `https://phctllmtsogkovoilwos.supabase.co/rest/v1`
Headers on every call:
```
apikey: <BRAVO_SUPABASE_SERVICE_ROLE_KEY>
Authorization: Bearer <BRAVO_SUPABASE_SERVICE_ROLE_KEY>
Content-Type: application/json
```

**WRITE a status row (on start / working / done / blocked):**
```
POST /agent_activity
{
  "agent": "apex",
  "status": "start",
  "task": "Pipeline tabs — Leads→Applications→Shopping single-stage",
  "files": ["app/api/forms/submit", "lib/sunbiz-stage-meta.ts"],
  "branch": "apex/lead-pipeline-agents-kixie",
  "detail": "Starting #2. Single-stage move; leaves prior tab on advance."
}
```

**READ Bravo's recent activity (poll this every 30–60s):**
```
GET /agent_activity?agent=eq.cc-agent&created_at=gte.<ISO-8601 of now-3h>&order=created_at.desc
```

**READ everything recent (to see open claims before you edit shared files):**
```
GET /agent_activity?created_at=gte.<now-6h>&order=created_at.desc
```

---

## 5. The protocol (both agents follow it)

1. **Before you start editing shared files**, SELECT recent rows and look for an
   open `start`/`working` row from `cc-agent` whose `files` overlap yours.
   **Do not edit a file the other agent has an open claim on** — instead post a
   "heads-up, you're in X, I'll hold" and pick something else.
2. **On every state change**, do BOTH:
   - INSERT a row into `agent_activity` (so the other agent sees it), AND
   - post the matching status line into the Telegram group (so the humans see it).
3. **`done` releases a claim.** `blocked` means you need the other agent or a human.
4. **Humans direct; agents coordinate.** A status row from the other agent updates
   your awareness — it does **not** by itself authorize you to make changes. Real
   work directives come from CC/Adon in the group.

### Status-line format (Telegram — APEX already uses this)
```
🟦 APEX · START   · Pipeline tabs · files: app/api/forms/submit · branch apex/lead-pipeline-agents-kixie
🟩 APEX · DONE    · Pipeline tabs · merged to main
🟥 APEX · BLOCKED · Pipeline tabs · need decision on stage-leave behavior
```
Bravo posts the same with `🟧 BRAVO · …`.

---

## 6. Loop safety (so the agents don't ping-pong forever)

- React only to the **other** agent's rows (`apex` ignores `apex`; `cc-agent`
  ignores `cc-agent`). Never react to your own writes.
- A plain `working`/`done` status row is **awareness only** — do not auto-spawn a
  response to it. Only engage when a row is `blocked` or explicitly addresses you
  (mentions the other agent, a handoff, or a file conflict).
- Debounce: at most one agent-triggered action per ~60s, with a sane hourly cap.
  Bravo enforces this on its side; APEX should too.

---

## 7. Round-trip acceptance test (proves the wire is live)

1. **APEX → Bravo:** APEX INSERTs a `start` row (`agent=apex`) AND posts the line
   to the group. → Bravo's poller reads the row and posts a one-line ack in the
   group ("seen APEX start on X"). ✅ if Bravo acks.
2. **Bravo → APEX:** Bravo INSERTs a `cc-agent` row. → APEX's poller reads it and
   posts an ack in the group. ✅ if APEX acks.

When both directions ack, the agents are genuinely reading each other — not just
posting in parallel for the humans.

---

## 8. Division of labor right now (from the chat)

- **APEX owns:** #1 Lead status (Viewed/Inquiry) — *merged to main*; #2 Pipeline tabs (Leads→Applications→Shopping) — *next*.
- **Bravo/CC owns:** #3 Ezra→Matt; #4 per-agent Kixie numbers — *config + phone infra mostly done; finish + verify*.

Use the table to claim files before touching them so #1–#4 don't collide on the
shared oasis-command-center surfaces.

---

## 9. What Bravo needs from APEX (the checklist)

- [ ] APEX **writes** an `agent_activity` row (`agent="apex"`) on start/working/done/blocked.
- [ ] APEX **reads** `agent_activity` for `agent="cc-agent"` rows every 30–60s and reacts only to blocked/addressed/conflict rows.
- [ ] APEX **checks claims** (other agent's open `files`) before editing shared files.
- [ ] APEX keeps posting the Telegram status line (already doing this).
- [ ] Run the §7 round-trip test with Bravo.

Once APEX is writing to the table, ping CC — Bravo will confirm it sees APEX's
first row, and we're live both ways.

## Obsidian Links
- [[docs/INDEX]]
- [[brain/STATE]]
