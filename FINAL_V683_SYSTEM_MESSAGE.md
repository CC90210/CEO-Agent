# FINAL SYSTEM MESSAGE — V6.8.3 Production Hardening & Sync Correction

> **Target Agent:** Claude Code (Bravo) or OpenCode (Big-Pickle)
> **Mission:** Go above and beyond. This is the final pass. Close every gap. Fix every sync issue. Make this system perfect.
> **Constraint:** NO DEFERALS AND NO DISTRACTIONS. If a gap is identified, close it. Do NOT refactor adjacent code. Do NOT undertake "while I'm here" improvements. Touch ONLY what is required to fix these exact gaps.

---

## CURRENT STATE — TRUTH, NOT CLAIMS

You are operating on `C:\Users\User\Business-Empire-Agent` immediately after a "V6.8.3 production hardening complete" pass. But an independent deep diagnostic found these gaps:

### DEADLINE SYNC ISSUE — FOUND AND PARTIALLY FIXED

**The discrepancy CC saw:** "9 days left" in brief vs "28 days left" in command centre.

**Root cause:** Two files still had May 30 while all others had June 18:
- `memory/ACTIVE_TASKS.md:77` — was May 30 → now June 18 (OpenCode just fixed)
- `brain/USER.md:23` — was May 30 → now June 18 (OpenCode just fixed)

**YOUR JOB:** Verify all sources now agree. Use the `grep_search` or equivalent search tool to find any remaining `May 30` or `May.*30` in MRR/deadline contexts across the repo. Make it ZERO. Ensure all files reflect the true deadline: **June 18, 2026** ($5,000 USD Net MRR).

---

## CRITICAL GAPS THAT MUST BE CLOSED — NO DEFERALS

The prior pass claimed "V6.8.3 production hardening complete" but left these half-done:

### 1. @retry Decorator — 2/5 integration tools done

**Claimed:** "Applied to integration tools"
**Actual:** Only `n8n_tool.py` and `stripe_tool.py` have `@retry`.

**MISSING — ALL must get `@retry` + `@circuit_breaker`:**
- `scripts/integrations/supabase_tool.py` — 1500+ lines, makes HTTP calls
- `scripts/integrations/google_tool.py` — 1000+ lines, makes API calls
- `scripts/integrations/firecrawl_tool.py` — makes HTTP calls

**The pattern exists in `scripts/lib/retry.py`. APPLY IT. Do not create a new pattern — use the existing one.**

### 2. structured_log — 1/5 daemons done

**Claimed:** "Applied to critical daemons"
**Actual:** Only `scripts/lib/smtp_send.py` uses it.

**Count of print() statements still in critical daemons:**
- `scripts/integrations/send_gateway.py`
- `scripts/autonomous_agent.py`
- `scripts/core/event_router.py`
- `scripts/state/state_api.py`
- `scripts/hooks/webhook_listener.py`

**The pattern exists in `scripts/lib/structured_log.py`. APPLY IT. Start with `send_gateway.py` and `autonomous_agent.py`. Replace unstructured prints with `structured_log.info/error/warning`.**

### 3. docker-compose healthchecks — 1/3 done

**Claimed:** "Added docker healthchecks"
**Actual:**
- `infra/docker-compose.local.yml` — ✅ has healthchecks for webhook + state-api
- `infra/docker-compose.yml` (production VPS) — ❌ NO healthchecks for `state-api` (webhook was just added, verify and add state-api)
- `infra/docker-compose.cloud.yml` — ❌ only state-api has healthcheck; `webhook` missing

**YOUR JOB: Make ALL THREE compose files in `infra/` have healthchecks for ALL their FastAPI services.**

### 4. tests/ directory — excluded from test suite

**Claimed:** "183/185 tests passing"
**Actual:** `pyproject.toml:26` has `testpaths = ["scripts"]` ONLY. The `tests/` directory is completely excluded.

**Fix: Either**
- Add `"tests"` to `pyproject.toml` `testpaths` array, OR
- Move the tests from `tests/` into `scripts/` using the `test_*.py` convention.

**Then run the FULL suite: `python -m pytest scripts/ tests/ -q` and make them pass.**

### 5. 12+ scripts still bypass secret_loader.py

**Claimed:** "Documented pattern in secret_loader.py"
**Actual:** 12+ scripts still use `dotenv.load_dotenv()` directly (e.g., `scripts/smoke_n8n_inbound_rpc.py`, `scripts/core/agent_heartbeat.py`, etc).

**The pattern exists in `scripts/lib/secret_loader.py`. MIGRATE THESE. Do NOT leave this as a "backlog item".**

---

## URGENT: LEAD LIFECYCLE SYNC IS BROKEN

CC reported:
- Tom McCrae shows as both "Discovery" AND "touch first" simultaneously.
- Pressing "Discovery scheduled" life cycle action did nothing.
- Command centre and backend are out of sync.

### ROOT CAUSE FOUND

**THERE ARE TWO PARALLEL LEAD SYSTEMS:**
1. **Old (`scripts/lead_engine.py`)**: Uses table `leads`, field `status`.
2. **New (Command Centre)**: Uses table `tenant_records`, field `data->>'stage'`.

### YOUR MISSION: FIND AND FIX THE SYNC

1. **Verify the Sync Mechanism**: Check if `scripts/lead_engine.py update --status` updates BOTH tables or just `leads`.
2. **Fix the Dual-Write**: Modify `lead_engine.py` (or create a DB trigger) to ensure updating one table immediately updates the other based on the Migration 062 mapping (`new` -> `new_contact`, `contacted` -> `outreach`, etc).
3. **Verify with Data**: Pick a lead (e.g., Tom McCrae). Check BOTH tables via SQL. Ensure `status` and `data->>'stage'` match perfectly.
4. **Fix "Touch First"**: Determine where "touch first" is computed. Ensure it maps correctly to the `outreach` stage or a `last_contacted_at` check so a lead isn't stuck in dual states.

---

## AGENT DESCRIPTION IN COMMAND CENTRE — NEEDS SIMPLIFICATION

CC reported the agent descriptions are too complex ("workflow Workspace default first personal override").

**Your Task:**
Locate where this text is rendered (likely in the `oasis-command-center` repo, but check your local environment first for any API responses that feed it).
Simplify it to this clear logic:
1. **Local bridge:** Your machine runs Claude Code CLI.
2. **Cloud mode:** Uses API calls instead.
3. **Workspace vs personal:** Workspace defaults apply first; personal overrides override defaults per-user.

---

## FINAL VERIFICATION CHECKLIST — MUST ALL PASS

Before you state you are complete, you must verify EVERY item:

- [ ] `infra/docker-compose.yml`, `infra/docker-compose.local.yml`, and `infra/docker-compose.cloud.yml` all pass `docker-compose -f <file> config` and have full healthchecks.
- [ ] `@retry` is applied to supabase, stripe, google, n8n, and firecrawl tools.
- [ ] `structured_log` is actively used in the 5 critical daemons; rogue `print()` calls are near zero.
- [ ] `pytest scripts/ tests/ -q` runs and passes all tests (including the previously excluded ones).
- [ ] Direct `dotenv.load_dotenv()` usage is eliminated; everything uses `lib/secret_loader.py`.
- [ ] `leads.status` and `tenant_records.data->>'stage'` are strictly synchronized.
- [ ] Grep for `May 30` returns ZERO results in deadline contexts. All sources say June 18, 2026.

---

## EXECUTION & LOGGING

1. **Self-Execute:** Run the tests yourself. Run the DB queries yourself. Do not ask CC to verify things you can verify programmatically.
2. **Log Everything:**
   - Update `memory/SESSION_LOG.md` with a detailed, structured summary of exactly what files were touched and what gaps were closed.
   - Run `python scripts/state/state_sync.py --note "V6.8.3 Final — All gaps closed, lead sync fixed"`
3. **Report:** Provide a concise final report to CC confirming all boxes are checked.
