# HANDOFF → Fable — Audit Remediation V1 complete (Business-Empire-Agent / Bravo)
**Date:** 2026-06-09 · **Ships as:** V6.9.0 · **Branch:** `main` (pushed) · **Author:** Bravo (Opus 4.8)

> **TL;DR for Fable:** Bravo's harness (the CEO-Agent / Business-Empire-Agent repo) got a
> 10-phase security + structural hardening pass. The work is **done and on `main`**. The
> point was **harness reliability** — wiring that makes *any* model (Opus, Sonnet, or a
> lower-tier OpenCode/Gemini) behave more accurately. These patterns are now proven on
> Bravo and **ready to replicate to Maven (CMO), Atlas (CFO), and the SunBiz agents** next
> round. This doc tells you exactly what's done, what CC must click, and what you direct next.

---

## 1. Why this matters (the thesis)

We didn't "fix bugs." We upgraded the **substrate every model reads**. A weaker model fails
when the harness lets it: stale docs it trusts, dangling links it follows, version drift it
repeats, guards that only watch, a test suite that won't run. Every phase below removes one of
those failure modes **structurally** — enforced by a test or a generator, not by hoping the
model behaves. That's what makes the harness portable across model tiers and across agents.

The durable centerpiece is the **LOCKSTEP `tool_discipline` block** now byte-identical in all
five entry points (CLAUDE/GEMINI/ANTIGRAVITY/AGENTS/OPENCODE.md): evidence-before-claims,
read-before-edit + verify-after, visible todo tracking, tool-failure fallback, the four-line
report, plain-English-to-CC. That block is *the* behavior contract — it's what made even this
session disciplined, and it's the first thing to copy to the siblings.

---

## 2. What's done (10 phases, all on `main`)

| # | Phase | What it gives the harness | Enforced by |
|---|---|---|---|
| 0 | Preflight | Full bundle + local backup before any destructive op | — |
| 1 | **PII purge** | 11 real third-party lead emails + 5 lead files gone from all git history | `git log -S` = 0 (branches+tags) |
| 2 | **Email compliance** | Drawer-queue daemon can't email an unsubscriber or skip CASL | `test_dashboard_email_consumer_compliance.py` + `email_doctor` check #5 |
| 3 | **Guards enforce** | secret+exec guards now *block*, not just log | smoke-tested; `SECURITY_MODEL.md` §9–10 |
| 4 | **Migration ledger** | No migration silently re-runs (checksum guard) | `apply_migration.py --status` |
| 5 | **Version single-source** | Version lives in ONE place; entry points can't drift | `test_entrypoint_parity.py` |
| 6 | **Generated routing docs** | Skill/brain/memory indexes derive from the graph | `test_generated_docs_fresh.py` |
| 7 | **Wiki-link integrity** | 125 dangling links → 0; brain loads whole in a fresh clone | `test_wiki_links.py` |
| 8 | **Hygiene + LOCKSTEP** | Deploy prompts → `docs/deploy/`; the discipline block ×5 | parity test |
| 9 | **Brain freshness** | Every brain doc is dated; staleness is visible | `check_brain_freshness.py` |
| F | **Ship 6.9.0** | `pytest -q` runs from root again (was 100% broken) | `--import-mode=importlib` |

**New tests that make drift impossible going forward:** `test_entrypoint_parity`,
`test_generated_docs_fresh`, `test_wiki_links`, `test_dashboard_email_consumer_compliance`.
**New tools:** `build_capability_graph.py --emit-docs`, `check_brain_freshness.py`,
`apply_migration.py --status/--backfill-ledger`.

**Verification snapshot (this session):** `pytest -q` 422 passed / 5 failed (all pre-existing,
documented below); `scan_secrets` clean (1422 files); `email_doctor --skip-network` 8/8;
brain freshness 0 stale; generated docs fresh (no diff).

---

## 3. What CC must personally do (nothing here is blocking; all are clicks/commands)

1. **Re-sync the other machines** (Mac + VPS) — Phase 1 rewrote history:
   ```
   git fetch origin && git reset --hard origin/main
   ```
   (Local secrets/state survive — they're gitignored and untracked.)
2. **GitHub PR-ref PII (recommended):** the 11 old lead emails still live in GitHub's internal
   `refs/pull/*` (PRs #1–22) — git can't rewrite those. Either email **GitHub Support** to purge
   unreachable commits, or flip the repo **private**. Normal clones are already clean.
3. **Append guard modes to `.env.agents` (+ `.env.agents.template`) on each machine** — the
   secret guard correctly blocks AI from writing `.env*`, so this is yours:
   ```
   EMPIRE_HOOK_SECRET_GUARD=enforce
   EMPIRE_HOOK_EXEC_GUARD=enforce
   EMPIRE_HOOK_STATE_GUARD=report
   ```
   (Tracked `.claude/settings.json` already covers Claude Code; these cover VPS daemons.)
4. **Seed the migration ledger on prod** — ONLY after confirming prod has every migration applied:
   ```
   python scripts/apply_migration.py database/100_schema_migrations_ledger.sql --allow-rls
   python scripts/apply_migration.py --backfill-ledger
   python scripts/apply_migration.py --status     # expect: 89 applied, 0 pending
   ```

---

## 4. Deliberately deferred (the deep-work queue — direct these next)

- **Phase 10 — `send_gateway.py` (163KB) decomposition.** The brief itself says do this in a
  *fresh* session a day after the rest is stable — refactoring the money path alongside 9 other
  changes is how outages happen. **Plan:** baseline `python -m pytest scripts/tests/test_send_gateway.py -q`
  (record pass count), convert to a `send_gateway/` package (`gates.py`/`transports.py`/`policy.py`/`cli.py`)
  with `__init__.py` re-exporting the identical public API, move-only (zero behavior change),
  gate on identical test pass count + `email_doctor` green.
- **`bridge_chat_server.py` windowless-flags bug** (pre-existing, newly *visible*): 4
  `subprocess.run` calls (lines ~110/2299/2567/2590) miss `creationflags=WINDOWLESS_FLAGS` → pop
  cmd.exe windows on Windows. `tests/test_bridge_heartbeat_silence.py` red. Fix in a session that
  can verify the live bridge still starts.
- **4 `test_send_gateway` failures** (pre-existing): depend on Supabase RPC `reserve_send_slot`
  unavailable offline. Need a live-DB or better-mocked fixture.
- **~6 scripts use bare `from send_gateway import`** (work in prod via path setup; should be
  `from integrations.send_gateway import` for robustness).

---

## 5. Replication playbook — Fable → Maven (CMO), Atlas (CFO), SunBiz agents

**The patterns are universal; the content is per-agent.** For each sibling repo, port these in
roughly this order (each is independently shippable + test-gated):

1. **LOCKSTEP `tool_discipline` block** — copy the exact block from any Bravo entry point into
   that agent's entry point(s), wrapped in the same `<!-- LOCKSTEP:tool_discipline -->` markers.
   This is the single highest-leverage import — it disciplines weaker models immediately.
2. **Version single-sourcing + parity test** — one `architecture_version` in that agent's
   `STATE.md`; de-version the entry-point titles; drop in `test_entrypoint_parity.py` (retarget
   the entry-point list). Drift becomes a build failure.
3. **`--import-mode=importlib` in `pyproject.toml`** — check each sibling for the same
   dual-`tests`-package collision; this one-liner often makes their `pytest -q` runnable.
4. **Guard enforce-modes** — set `EMPIRE_HOOK_*` in their tracked settings + `.env.agents`;
   confirm their guard logic exists (it's shared substrate). Document modes in their SECURITY doc.
5. **Generated routing docs** — if the sibling has a capability graph, add `--emit-docs` +
   `test_generated_docs_fresh`. If not, that's the prerequisite to build first.
6. **Wiki-link + brain-freshness checkers** — `test_wiki_links.py` + `check_brain_freshness.py`
   port almost verbatim (adjust the local-only-store prefixes per agent).
7. **Email/outbound compliance audit** — for any sibling that sends (Maven especially): grep for
   `smtplib`/`smtp_send` importers NOT routed through their gateway; apply suppression+footer at
   each send surface (Bravo's `email_doctor` check #5 is the template).
8. **PII history sweep** — run a content sweep (not just path-based) for real third-party data
   before assuming a repo is clean; **ask the operator** which strings are real vs test data
   (the `goldstorm` lesson — the audit's own canary was CC's test address).

**Sequencing for Fable:** do LOCKSTEP + parity + importlib first on all three siblings (cheap,
high-leverage, low-risk), then the per-agent security passes (Maven email compliance, Atlas
financial-data guards, SunBiz tenant isolation), then the generated-docs tier where each has a graph.

---

## 6. Codex independent audit

_See the `### Codex independent audit` section appended below once the background review returns.
If Codex was unavailable in this environment, that is noted there and Bravo's self-review (the
per-phase records in `plans/MISSION_2026-06-09_PROGRESS.md`) stands as the review of record._

---

## Pointers
- Full per-phase record + proofs: `plans/MISSION_2026-06-09_PROGRESS.md`
- Original brief: `plans/MISSION_2026-06-09_AUDIT_REMEDIATION.md`
- Retrospective + lessons: `memory/RETROSPECTIVE_2026-06-09_audit_remediation.md`
- Security model (guards + send-surface compliance): `brain/SECURITY_MODEL.md` §9–10
