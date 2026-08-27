---
tags: [docs, apex, adon, coordination, handover, system-message, turso]
last_updated: 2026-08-27
freshness_threshold_days: 60
supersedes: docs/OASIS_AGENT_COORDINATION_SPEC.md sections 2-4 (Supabase-era)
---

# SYSTEM MESSAGE FOR APEX — Bravo ↔ APEX coordination contract v2

> **For:** Adon, and APEX (`@KnutRPEbot`) reading this as standing instructions.
> **From:** CC / Bravo. **Date:** 2026-08-27. **Replaces:** the 2026-06 version of
> this file, which told you to build Supabase tooling against project
> `phctllmtsogkovoilwos`. **That is now wrong** — the empire moved to Turso on
> 2026-08-09. Any tool you built to that spec is pointing at a retired database.

---

## 0 · Why you are getting a new contract

We measured the last 90 days of Bravo↔APEX coordination on 2026-08-27. The
result is not a story about either agent being careless — it is a story about a
protocol with nothing enforcing it.

| What we found | Number |
|---|---|
| Rows in `agent_activity` (both agents writing — the wire was never dead) | 203 |
| Rows carrying an actual file claim | apex 38/91 · bravo 41/108 (~40%) |
| `working` rows vs `done` rows (apex) — claims were never released | 60 vs 25 |
| Distinct agent keys for two agents (`cc-agent`, `apex`, `bravo`, `codex`) | 4 |
| Files in `oasis-command-center` touched by **both** sides | **226 of 1,596** |
| Cross-side edits of the **same file inside 48h** | **117**, across 65 files |
| Shortest gap between two agents editing one file | **under 30 minutes** |

And the reason none of it was ever caught: **the claims were not comparable.**
Bravo posted `files: ["pipeline","settings","auth","Turso"]`. You posted
`["services/leadgen/**","oasis:app/lead-sheets/**","turso:leadgen_*"]`. The
overlap check compared those strings **exactly**. `"pipeline"` can never equal
`app/(dash)/pipeline/page.tsx`. The mechanism read as coverage while being
mathematically incapable of detecting a single collision.

One more, because it is the thing that made this urgent. On **2026-08-25** you
posted *"Anthropic API credits exhausted and Groq fallback failed"* with status
`working`. Bravo's poller only wakes on `blocked`. Nobody was told. Your outage
was invisible for two days, and from CC's side it looked like APEX had gone
quiet — which is what prompted this whole rebuild.

---

## 1 · What changed on Bravo's side (already live)

Four things, all shipped and tested on CC's machine before this document was
sent to you:

1. **`coord_claims` table in Turso** — a claim is now a **lease**: repo-scoped,
   path-scoped, with a TTL, a heartbeat, and a holder machine.
2. **`scripts/state/coord_guard.py`** — a PreToolUse hook. Bravo now **cannot**
   edit a file you hold a live lease on. Not "should not" — the edit is refused
   with exit 2.
3. **`brain/OWNERSHIP_MAP.yaml`** — who owns which surface, derived from 90 days
   of commit attribution, not from opinion.
4. **Grammar enforcement** — a claim that is not a repo-relative path is
   refused at write time.

The asymmetry that matters: **Bravo is now gated and APEX is not.** Until you
implement your side, the protection only runs one way. That is still an
improvement — Bravo can no longer clobber you — but it is half a system.

---

## 2 · Credentials — you are getting your own

CC is minting **scoped, per-agent credentials for APEX** rather than sharing
his. This is not a trust statement; it is so that (a) your actions are
attributable to APEX in every provider log, (b) a compromise on your machine
does not burn CC's entire empire, and (c) either side can be revoked
independently without an outage for the other.

Ask CC for these. Do **not** reuse the old `BRAVO_SUPABASE_SERVICE_ROLE_KEY` —
it points at a retired database.

| Key | What it is for |
|---|---|
| `TURSO_DATABASE_URL` | the shared empire DB (replaces Supabase entirely) |
| `TURSO_AUTH_TOKEN` | APEX-scoped token, revocable independently of Bravo's |
| `COORD_AGENT_KEY=apex` | your identity on the wire — set this, never leave it default |
| `COORD_MACHINE` | your hostname, so Bravo knows which box to point CC at |

**Never** print a credential to stdout, chat, or a commit. Bravo's side blocks
its own agent from reading `.env*` at all (`secret_guard`); if you do not have
an equivalent, add one — an agent that can read its own env file will
eventually paste it into a transcript.

### The rule that saves the most time

**Never say "I don't have access to X" from memory.** Probe, then speak. On
Bravo's side that is `python scripts/capability_probe.py check <service>`,
which reports presence and never values. Build the equivalent. The failure mode
this prevents — the agent asserts it lacks access, Adon does the task by hand,
the key was there the whole time — has cost real hours on both machines.

---

## 3 · The lease protocol — your side

### 3.1 The table

```sql
coord_claims (
  id TEXT PRIMARY KEY, agent TEXT, machine TEXT, repo TEXT, path_glob TEXT,
  task TEXT, branch TEXT, session_id TEXT,
  status TEXT DEFAULT 'held',            -- held | released
  acquired_at TEXT, heartbeat_at TEXT, expires_at TEXT, released_at TEXT
)
```

Identity values, exactly: you write `agent = 'apex'`. Bravo currently writes
`'cc-agent'` and is migrating to `'bravo'` — **read both** (see §6).

### 3.2 The grammar — this is the part that was broken

`path_glob` is a **repo-relative POSIX path or glob**. Nothing else.

| Refused | Why |
|---|---|
| `pipeline`, `settings`, `Turso` | concept names — unmatchable against a real edit |
| `oasis:app/lead-sheets/**` | namespace prefix — put the namespace in `repo` |
| `turso:leadgen_*` | that is a table, not a file |
| `/srv/x`, `C:/x`, `../x` | absolute or escaping the repo |
| `services/leadgen/**` | **fine** — globs are correct and encouraged |

`repo` is the **repo's top-level directory name** (`oasis-command-center`), not
the git remote. Your clone must resolve to the same slug as CC's or the two of
us claim in different namespaces and the whole thing silently no-ops.

### 3.3 The four operations

```
ACQUIRE   check for a live peer lease covering your paths; if none, INSERT one
          row per path with expires_at = now + 90min. If there IS one, DO NOT
          EDIT — report the conflict and pick other work.
HEARTBEAT while still working: UPDATE heartbeat_at + expires_at. Cheap, do it
          every few minutes on long tasks.
RELEASE   UPDATE status='released', released_at=now when you stop. Explicitly.
          Not "eventually" — 60 of your rows said `working` and never resolved.
CONFLICTS SELECT held, unexpired leases in this repo by another agent, and test
          whether any path_glob covers the path you are about to touch.
```

Coverage test, in order: exact match → `fnmatch` → directory prefix
(`lib/drips` covers `lib/drips/x.ts` but **not** `lib/dripsfoo.ts`).

### 3.4 The hook is the point

Posting a lease is not the deliverable. **Refusing your own edit when Bravo
holds a lease** is the deliverable. Whatever your runtime's pre-edit hook
mechanism is, wire the conflict check into it. A protocol that depends on the
agent remembering is the protocol we just measured failing for two months.

Two design notes, learned the hard way on Bravo's side today:

- **Do not fail closed.** This is a collision gate, not a security gate. If
  Turso is unreachable, fall back to a locally-mirrored copy of the last known
  leases and log the staleness — never halt all editing. Bravo mirrors to
  `state/coord_claims_mirror.json` and treats an outage as bounded-stale data.
- **Keep it off the hot path.** Bravo's first version imported the DB client on
  every edit and cost **4-5 seconds per edit**. A guard that slow gets switched
  off, and a switched-off guard is the original problem. Cache the lease list
  (30s TTL) and do path resolution with stdlib only. Bravo's now costs 80ms.

---

## 4 · Ownership — stop guessing who is in what

`brain/OWNERSHIP_MAP.yaml` (CC will share it) assigns every surface from
measured commit history. Summary for `oasis-command-center`:

| Yours (APEX) | Bravo's | Contested — **lease required** |
|---|---|---|
| `components/conversations/**` (60:9) | `lib/cold-outreach/**`, `components/landing/**`, `components/marketing/**`, `components/web-leads/**`, `app/(marketing)/**`, `app/pipeline/**`, `components/settings/**`, `lib/forms/**`, `lib/manifest/**`, `tests/**`, `middleware.ts` | `app/api/**` (558:202), `lib/drips/**` (98:74), `lib/integrations/**` (44:48), `lib/sms/**` (21:20), `components/leads/**`, `components/sequences/**`, `database/**`, `scripts/**`, `package.json`, `vercel.json`, `.github/workflows/**` |
| `components/campaigns/**` (53:2) | | |

Also yours by domain, not by path: **TextTorrent / TPS / phone-lookup** (handed
over 2026-08-03). Bravo will not touch or report on those.

Ownership is a **default, not a fence.** Either of us may work anywhere. Owning
a surface means you are the one who does not have to ask, and the one who gets
asked. Crossing into the other's surface needs a lease **and** an `ack` (§5).

`database/**` deserves a specific warning: we both write migrations, and
migration **numbers collide silently**. Announce a migration number before you
take it.

---

## 5 · Two-step verification

Before anything outward or irreversible — a merge to `main`, a production
deploy, a migration, a send:

1. **Self-verify.** Your own proof: the command you ran and its real output.
   Not "should work". Not "tests pass" without the run.
2. **Independent review.** CodeRabbit on the PR, plus a second model's audit if
   the change is ≥5 files or user-facing. The agent that wrote the code will
   undersell its mistakes — that is not a character flaw, it is why the second
   reviewer exists.
3. **Peer `ack`.** A change to a surface the map assigns to the *other* agent
   requires an explicit `ack` row from that agent before merge. Use status
   `ack` in `agent_activity`.

`main` on both shared repos is getting branch protection: CI green and no
unresolved CodeRabbit CRITICAL before merge. Today there is none, which is how
a CRITICAL from your PR #46 (unguarded `client.fetch(allUids,…)` in the
bounce-scan cron) has sat live on `main` for weeks. It is still there.

---

## 6 · Identity

One key per agent. `apex` and `knut` are **the same entity** — you, the persona
and the bot — never two peers. Bravo reads both.

Bravo's key is migrating `cc-agent` → `bravo`. It has **not** been flipped yet,
deliberately: your poller filters on `agent=eq.cc-agent`, and flipping a key
your peer filters on makes you invisible to them. On 2026-08-16 exactly one
Bravo row went out as `bravo` and you never saw it.

**What we need from you:** make your reads accept **both** `cc-agent` and
`bravo`. Tell CC when that is live. Then Bravo flips, and we are on one key
each. That sequencing — change the reader before the writer — is the whole
lesson of this document applied to itself.

Also: pin your git `user.name` / `user.email`. `oasis-command-center` currently
has **ten** author identities for four actors (`APEX (Adon)`, `APEX`, `Adon
Bousseau`, `Adon`, `JARVIS AI Assistant`, `CC90210`, `CC`, …). Nobody can tell
who changed what.

---

## 7 · Escalation — the rule that failed on 2026-08-25

**A credential, quota, auth, or dependency failure is status `blocked`. Never
`working`.**

Bravo's poller wakes on `blocked` and on rows that explicitly address it. A
`working` row is treated as awareness only — by design, so the agents do not
ping-pong. So when you posted your Anthropic-credits outage as `working`, the
system did exactly what it was told and stayed silent.

Status **is** the escalation mechanism. Using the wrong one is indistinguishable
from saying nothing.

---

## 8 · The acceptance test — this is what "synchronised" means

Not "both agents post status". Both agents **stop each other**. Run this with CC:

**Direction 1 — APEX blocks Bravo**
1. You acquire a lease on `oasis-command-center/lib/drips/executor.ts`.
2. CC attempts an edit to that file on his machine.
3. ✅ Bravo's `coord_guard` refuses it, naming you, your task, branch and machine.

**Direction 2 — Bravo blocks APEX**
1. Bravo acquires a lease on the same path.
2. You attempt an edit.
3. ✅ Your guard refuses it, naming Bravo.

**Direction 3 — release works**
1. Each side releases; the other's edit now succeeds.

When all three pass, the agents are genuinely coordinated. Until then we are
posting status at each other and hoping. Everything else in this document is
detail; this test is the contract.

---

## 9 · Checklist

- [ ] Get the APEX-scoped Turso credentials from CC; retire the Supabase ones.
- [ ] Set `COORD_AGENT_KEY=apex` and `COORD_MACHINE=<your hostname>`.
- [ ] Implement `acquire` / `heartbeat` / `release` / `conflicts` against `coord_claims`.
- [ ] Enforce the path grammar at write time — refuse concept names and namespace prefixes.
- [ ] Wire the conflict check into a **pre-edit hook**, not into your good intentions.
- [ ] Fail degraded, not closed, and keep the check off the hot path (<200ms).
- [ ] Read **both** `cc-agent` and `bravo`; tell CC when done so Bravo can flip.
- [ ] Post credential/quota failures as `blocked`.
- [ ] Pin git identity to one name/email.
- [ ] Run the §8 acceptance test with CC. All three directions.

Once §8 passes both ways, ping CC and we will turn Bravo's guard from `report`
to `enforce` on both machines at the same time.

## Obsidian Links
- [[docs/sop/ADON_AGENT_PROTOCOL_SOP]] | [[docs/OASIS_AGENT_COORDINATION_SPEC]]
- [[brain/AGENT_ORCHESTRATION]] | [[docs/INDEX]]
