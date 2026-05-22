# V6.8.3 Production Hardening — Cross-Repo Parity Sync

> **Paste this into any sibling agent's IDE terminal** (Maven, Atlas, Hermes,
> Aura, future client agents). The agent will execute the 5-phase audit against
> its own repo and bring its substrate to the Bravo V6.8.3 standard.
>
> **Target Agent:** Whoever's CLI you paste this into (Claude Code, OpenCode,
> Gemini CLI, Antigravity, Codex, etc.)
> **Reference:** Bravo at `C:\Users\User\Business-Empire-Agent` is already
> V6.8.3-compliant. Read its `scripts/lib/{retry,structured_log,secret_loader}.py`
> as the canonical pattern.

---

## CONTEXT

The empire's primary agent (Bravo) completed a V6.8.3 production hardening
pass: bloat purged, secret loading centralized, retry + circuit-breaker on
every external integration, structured logging in every daemon, docker
healthchecks across every FastAPI service, and the test suite green at
394/394. Your job is to apply those same architectural standards to **this**
repo so the empire operates on one substrate.

The 5 phases below describe *what* to do, not *how*. Adapt the
implementation to this repo's integrations — Maven hits Late.com /
Stripe / social APIs, Atlas hits Plaid / IBKR / tax APIs, a future
client agent will hit whatever its vertical needs. The phases stay
identical; the file list per phase is yours to discover.

---

## HARD CONSTRAINTS — NO EXCEPTIONS

1. **`cd` into THIS repo's root before any operation.** Never edit Bravo
   from here — Bravo is the source-of-truth and is already done.
2. **Do not touch persona / voice files.** `brain/SOUL.md`, brand-voice
   docs, content-style canon (Maven), professional-advisory voice (Atlas),
   tax/legal templates — all sacred. The audit is structural only.
3. **Do not push.** Commit locally; CC reviews and pushes manually.
4. **Do not delete `docker-compose*.yml` files.** Edit them in place.
5. **Skip business-logic changes.** If a fix would alter content
   generation, scheduling rules, financial computations, advisory logic,
   or any vertical's actual product behavior — SKIP and note it in your
   report. This pass is structural hardening only.
6. **Keep load-bearing `tmp/` files.** `.db`, active offline-buffer
   `.jsonl`, current state files all stay. Only purge obvious scratch
   (`commit-msg-*.txt`, `send_batch_*.py` one-offs, dead JSON payload dumps,
   abandoned worktree artifacts).
7. **Do not touch `archive/` directories.** That's intentionally archived
   code (e.g., Atlas's `archive/trading-automation/`), not live.

---

## EXECUTION — 5 PHASES, SEQUENTIAL

### Phase 1: Bloat Purge

- `tmp/`: delete scratch scripts, `commit-msg-*.txt`, manual `send_batch*.py`,
  orphaned JSON dumps. Keep `.db` + active offline buffers.
- `.playwright-mcp/` if present: delete all `console-*.log` and `page-*.yml`.
- `docs/` + `brain/`: find dated point-in-time audit reports
  (`*2026-04-*`, `*2026-05-1[0-9]*`, `HANDOFF_*`, `*_AUDIT_*` with stale
  dates). If they're not actively linked in an `INDEX.md`, delete them.
  Then sweep for resulting dead `[[wiki-links]]` and strip those lines.

### Phase 2: Secret Substrate

- `grep -r "load_dotenv\|from dotenv" scripts/` — every hit except
  `scripts/lib/secret_loader.py` itself is a violation.
- Replace each violation by importing
  `from lib.secret_loader import load_env`.
- If `scripts/lib/secret_loader.py` doesn't exist in this repo, copy it from
  `C:\Users\User\Business-Empire-Agent\scripts\lib\secret_loader.py`.

### Phase 3: Resilience (Retry + Logging)

- **Integrations:** for every script that hits an external API, wrap HTTP
  calls with `@retry` and `@circuit_breaker` from `scripts/lib/retry.py`.
  If `lib/retry.py` doesn't exist here, copy from Bravo first. Reference
  pattern: Bravo's `scripts/integrations/n8n_tool.py`.
- **Daemons:** for every long-running script (loops, webhook listeners,
  poll workers), replace `print(...)` calls in ERROR paths with
  `from lib.structured_log import structured_log; structured_log.error(...)`.
  If `lib/structured_log.py` doesn't exist here, copy from Bravo first.
  **Do NOT replace user-facing CLI prints** — only internal daemon logging.

### Phase 4: Infrastructure + Tests

- `pyproject.toml`: ensure
  `[tool.pytest.ini_options] testpaths = ["scripts", "tests"]`. Add
  `"tests"` if missing.
- Run `python -m pytest scripts/ tests/ -q --ignore=scripts/_archive
  --ignore=archive`. Fix any real test bugs. If a test fails due to
  environment (missing credentials, missing sibling repo state),
  gate it with `pytest.skip(...)` rather than deleting it.
- `infra/docker-compose*.yml` if present: every FastAPI service must
  have a `healthcheck:` block. Pattern:
  ```yaml
  healthcheck:
    test: ["CMD-SHELL", "python -c \"import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:<PORT>/health', timeout=5).status==200 else 1)\""]
    interval: 60s
    timeout: 5s
    retries: 3
    start_period: 20s
  ```

### Phase 5: Entry-Point Alignment

- `CLAUDE.md`, `GEMINI.md`, `AGENTS.md`, `ANTIGRAVITY.md` (whichever
  this repo has): each Rules section must explicitly mention:
  - **V6 Coherence Gate** — "verify inherited claims via live
    diagnostic before acting" (Bravo's CLAUDE.md Rule 10 is the
    canonical phrasing).
  - **Secret-loader requirement** — secrets MUST load via
    `lib.secret_loader.load_env()`, never directly via `dotenv`.
- If equivalent language already exists, don't duplicate.

---

## CLOSING THE LOOP

1. **Self-execute.** Do not ask CC to run tests, do searches, or verify
   healthchecks. Run them yourself.
2. **Update `memory/SESSION_LOG.md`** with one structured entry
   describing exactly which files you touched per phase.
3. **Run this repo's state-sync script** (typically
   `python scripts/state/state_sync.py --note "V6.8.3 parity sync complete"`).
   If the path differs in this agent, find it and run it.
4. **Commit locally** with message:
   `chore(v6.8.3): cross-repo parity sync to Bravo standard`
   plus a body listing the phases executed and the file count touched.
   Default branch differs per agent (Bravo + Maven = `main`,
   Atlas = `master`).
5. **Report to CC** in 5 short sections — one per phase — with: what
   you found, what you changed, what you skipped and why. Include the
   final test count (`N passed, M failed, K skipped`). Under 800 words,
   bullet-shaped, no prose padding.

---

## VERIFICATION CHECKLIST (must all be ✓ before reporting "complete")

- [ ] `grep -r "load_dotenv" scripts/` returns only `scripts/lib/secret_loader.py`
- [ ] Every external-API integration file has `@retry` somewhere
- [ ] Every daemon imports `structured_log` for ERROR paths
- [ ] `pyproject.toml` testpaths includes `tests`
- [ ] `pytest scripts/ tests/ -q` exits 0 (passes or skips, no failures)
- [ ] Every FastAPI service in every compose file has a `healthcheck:` block
- [ ] All four sibling entry-point files reference V6 Coherence Gate + secret_loader
- [ ] No dead `[[wiki-links]]` to deleted files (grep returns clean)
- [ ] `memory/SESSION_LOG.md` updated
- [ ] State-sync script ran successfully (heartbeat ✅ if applicable)
- [ ] Local commit landed; no `git push`
