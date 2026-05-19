# Primary Retainer Revenue Shift — Full Handoff to Claude Code / Codex

> **Created:** 2026-05-18 2:33 PM ET by Antigravity (Claude Opus)
> **Priority:** P0 — Biggest revenue event since the empire launched.
> **Action required:** Verify file changes, update Agent Command Center dashboard, remove prior-client prominence from codebase.

---

## TL;DR

The primary retainer ($2,500/mo + ~$451 rev share = ~$2,951/mo) ended 2026-05-18. CC's confirmed MRR dropped from **~$3,322 to ~$371**. SunBiz salary is the pending replacement (~$2,500 range, NOT confirmed). $1,300 outstanding AR from the prior client — CC is handling collection. The Agent Command Center dashboard still shows the old numbers and needs updating.

---

## 1. What Happened

The prior retainer client (a Skool community CC was running) told CC the retainer was too high. He's brought on a different full-time coach with equity (percentage of the offer — that coach is building IP/platform for students). The prior client indicated he'd bring CC back as a smaller coach later — no terms, no timeline, no amount.

**The conversation (paraphrased for the record — name removed, content preserved):**

CC said:
> "What's up, brother? I know it's been chaotic on your end, and I've been giving grace with everything, but I'm still actively building, running calls, helping the community, posting, etc., and the people are genuinely loving it. I'm good to work with you through the rough month because I believe in what we're building, but I do need to get the outstanding stuff handled so we can keep everything flowing properly. Just let me know where you're at with it."

The client replied:
> "I got you. The retainer is a bit too high for me to be able to consistently pay it right now. I have a full-time coach now. I gave him a percentage of the offer because he's helping build this platform with a bunch of IP for all of our students to use. I still want you to be one of the main coaches, kind of like working with him. You'll be the first person we bring on, but I wouldn't be able to pay you as much. Your responsibilities would also be a bit less."

CC's response (being sent):
> "I trust you brother, and I completely understand — you're the visionary and you have to do what makes sense for the business. I'm down for something in the future, we'll do it right contractually. Things have been busy here too so no worries. I'm heading to Ireland soon to see my dad so I do need to get that $1,300 handled ASAP"

**Good news:** SunBiz is likely bringing CC on salary — CC expects ~$2,500/mo range. He's been building their software. Not signed yet.

---

## 2. Financial Impact

| Metric | Before | After | Delta |
|---|---|---|---|
| **Confirmed MRR** | ~$3,322/mo | ~$371/mo | **-$2,951 (-89%)** |
| **Primary retainer** | $2,500/mo | $0 | Gone |
| **Rev-share component** | ~$451/mo | $0 | Gone |
| **Stripe + base** | $371/mo | $371/mo | Unchanged |
| **Outstanding AR** | $0 | **$1,300** | CC is handling |
| **SunBiz salary** | $0 | **~$2,500 (PENDING)** | Do NOT count until signed |

---

## 3. Files Already Updated by Antigravity (VERIFY THESE)

Cross-reference each file to confirm the changes are correct:

| File | What Changed | Verify |
|---|---|---|
| `brain/STATE.md` | Revenue: ~$371 confirmed. Position: PIVOTING. Confidence: 0.65. Focus: REVENUE RECOVERY + SUNBIZ SALARY. North Star section rewritten with honest numbers. Active App Portfolio entry marked ENDING. | Verify |
| `memory/ACTIVE_TASKS.md` | Today section: Monday May 18. MRR target section rewritten. P0 priorities: #1 SunBiz salary, #2 Collect $1,300 AR. Prior-client deferred item updated. Strategy session at 4 PM. | Verify |
| `APPS_CONTEXT/SKOOL_COMMUNITY_CLAUDE.md` | Status: ENDING. Revenue structure marked ending. Full conversation documented. R-001 materialization. New coach's role. CC retains IP. Mitigation plan (SunBiz). | Verify |
| `brain/RISK_REGISTER.md` | R-001: MATERIALIZED (was LOW probability). Updated 2026-05-18. | Verify |
| `memory/SESSION_LOG.md` | State sync entry logged via state_sync.py. | Verify |

---

## 4. Agent Command Center — NEEDS UPDATING

The dashboard (screenshot from CC at 2:33 PM) still shows stale data:

### What's wrong on the dashboard right now:
- **NET MRR:** Shows **$3,322** — Should be **$371** (confirmed) or note SunBiz pending
- **GAP TO GOAL:** Shows **$1,678** — Should be **$4,629** (from confirmed), or ~$2,129 if SunBiz lands
- **GOAL COUNTDOWN:** Shows **66% of goal** — Should be **~7%** (from confirmed)
- **DAILY NEED:** Shows **$153** — Needs recalculation based on new gap
- **TOP CLIENT SHARE:** Shows **89% — [prior client]** — Prior client is no longer active. Remove or show "No dominant client" / SunBiz pending
- **MRR 30-DAY TRAJECTORY chart:** Will need updated data points

### What CC wants kept:
- **Goal Countdown widget** — CC likes it. Keep the $5K MRR by May 30 North Star for now. He said he sees himself changing it later (beyond just money) but for this stage of life it's right.
- **Days Left counter** — Keep it.

### Where the dashboard data likely comes from:
- Check `revenue_events` and `monthly_metrics` tables in Supabase (Bravo project). **Rule 8 applies — these are financial truth tables. Get CC's explicit approval before writing to them.**
- The MRR number may also come from `pulse_publish.py` or the CEO dashboard script
- Top Client Share likely queries `revenue_events` or has a hardcoded/cached reference to the prior client
- Run: `python scripts/supabase_tool.py select revenue_events --project bravo --limit 5` to see current data

---

## 5. Prior-Client References to Remove / Downgrade

CC's direction: the prior client is "obviously not important to that extent anymore." Remove the prominence across the codebase. He should exist only as historical context, not as a current operational reference.

### Likely places the prior client is referenced (beyond the 5 files already updated):
- `brain/OKRs.md` — Likely has prior-client / Skool MRR targets. **Check and update.**
- `brain/DASHBOARD.md` — May reference prior-client metrics. **Check and update.**
- `brain/CRM_STRATEGY.md` — May reference the prior client as primary. **Check and update.**
- `knowledge/` wiki pages — `revenue-model.md`, `client-playbook.md` may reference the prior client. **Check and update.**
- `data/pulse/ceo_pulse.json` — Likely has prior-client MRR baked in. **Refresh via pulse_publish.py.**
- Supabase `leads` table — Prior client may be in there. Don't delete, just update status.
- Agent Command Center code — grep the oasis-command-center repo for the prior client's name and company.
- `brain/GROWTH.md` — May reference prior-client revenue assumptions

---

## 6. Action Items for Codex / Bravo

| # | Action | Priority | Notes |
|---|---|---|---|
| 1 | **Verify all 5 Antigravity file changes** | P0 | Cross-reference section 3 above |
| 2 | **Update Agent Command Center MRR display** | P0 | Dashboard shows $3,322 — needs to show $371 confirmed. May require Supabase writes (Rule 8 — get CC approval). |
| 3 | **Remove prior-client prominence** from brain/, memory/, knowledge/, dashboard code | P0 | Downgrade to historical context only. |
| 4 | **Refresh CEO pulse** | P1 | `python scripts/pulse_publish.py cmd-refresh` with updated MRR numbers |
| 5 | **Strategy session prep (4 PM today)** | P1 | CC + Atlas + Bravo. Revenue restructure. SunBiz salary terms. North Star timeline reassessment. |
| 6 | **Update OKRs** | P1 | `brain/OKRs.md` likely has prior-era targets |
| 7 | **Skool daemon decision** | P2 | skool_watchdog + skool_engine archived 2026-05-18 (see `scripts/_archive/skool/`). Revive only for CC's own community. |
| 8 | **Contract note** | P2 | CC has a formal contract (Section 7 — Role Protection) but chose relationship over enforcement. Documented, not actionable. |

---

## 7. Key Context Notes

- CC is handling this well — already has SunBiz lined up as replacement revenue
- The relationship with the prior client ended amicably. CC chose grace over contract enforcement
- CC built the entire Skool curriculum and retains full IP ownership (contract Section 4)
- CC's North Star ($5K MRR by May 30) stays for now — he said he'll evolve it beyond just money later, but it's right for this stage
- The Goal Countdown widget on the dashboard should stay — CC likes it
- SunBiz salary is the lifeline but is NOT signed. Do not count it as confirmed MRR until it is.

---

*Handoff complete. Antigravity out. — 2026-05-18 2:33 PM ET*
*Name-scrub pass: 2026-05-18 evening — CC asked that the prior client's name not be so prevalent.*
