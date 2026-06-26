---
tags: [parity, bootstrap, multi-machine, mac, autonomy, setup]
purpose: The canonical runbook for bringing ANY machine (Mac/Windows/Linux) to full agentic parity after a git pull — hooks (the autonomous loop), deps, Codex, plugins, daemons. Supersedes the env-only MAC_SYNC_PROMPT.
owner: CC (Conaugh McKenna)
last_updated: 2026-06-26
---

# Machine Parity Bootstrap — make a new machine fully agentic

> **Why this exists.** `git pull` syncs *files*. It does NOT make the agent *agentic*. The
> autonomous loop is the Claude Code **hooks** (memory injection on every prompt, the
> secret/exec/anti-pattern guards, post-edit memory index, SessionStart state load, pre-compact
> soul, sub-agent validator, Stop self-review). Those live in `.claude/settings.local.json`,
> which is **gitignored and machine-specific** (interpreter + absolute repo path differ per OS).
> So a fresh clone is a "dumb" Claude Code. This runbook + `scripts/machine_parity.py` close that
> gap reproducibly. See also: `brain/CROSS_MACHINE_SYNC.md` (daemon ownership),
> `docs/deploy/CAPABILITY_MANIFEST.md` (plugins/Codex/bins).

## The one command

```bash
python3 scripts/machine_parity.py --fix
```

It renders the committed, OS-portable hook template (`.claude/settings.hooks.template.json`) into
this machine's `.claude/settings.local.json` with the correct interpreter + paths, **self-tests
that every hook script runs** (catches OS-specific import bugs), then checks deps / Codex / plugins
/ global config / `.env.agents` (by KEY NAME only) and prints exactly what still needs a manual
step. **Then RESTART Claude Code so the hooks load**, and run `--check` to confirm GREEN.

The three modes:
| Command | When | What |
|---|---|---|
| `--export-template` | source machine, after editing the hook set | capture live hooks → committed portable template |
| `--fix` | new machine (or after a hook-set change) | install hooks for this OS + self-test + heal deps + report |
| `--check [--quiet] [--fast]` | anytime | read-only parity report. `--fast` = hooks + global config only (used by the SessionStart hook) |

## Full bootstrap sequence (new machine)

1. **Clone / pull.** `git pull --ff-only` (the repo, plus sibling repos per the session handover).
2. **Environment.**
   ```bash
   python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
   npm install
   # macOS bins: brew install python@3.12 node@20 ffmpeg gh && npm install -g pm2
   ```
3. **`.env.agents`** — create it on this machine (CC keeps this manual; it is never committed).
4. **Parity doctor:** `python3 scripts/machine_parity.py --fix` → do its manual-steps list →
   **restart Claude Code** → `python3 scripts/machine_parity.py --check` until GREEN.
5. **Codex** (Rule 8 dual-AI review): `node ~/.claude/codex-plugin/scripts/codex-companion.mjs status`
   — if unauthed, run the OpenAI login it prints.
6. **Plugins:** run the `/plugin marketplace add` + `/plugin install` lines in `docs/deploy/CAPABILITY_MANIFEST.md`.
7. **Global config:** if `~/.claude/CLAUDE.md` is missing, `cp docs/deploy/global-CLAUDE.md ~/.claude/CLAUDE.md`.

After step 4, parity stays self-policing: the **SessionStart hook runs `--check --fast`** every boot
and injects a one-line warning if the machine ever drifts out of parity (e.g. a new hook is added
upstream). You won't have to remember this again.

## Daemon takeover (only when the usual daemon host is OFF)

`brain/CROSS_MACHINE_SYNC.md` is law: exactly ONE machine runs the state-mutating daemons
(single Telegram poll token; one scheduler vs the shared Supabase `cron_jobs` table). Normally
that's the Windows box. **A second machine may take over only while the primary is OFF** (e.g. CC
travelling, PC powered down) — there is no concurrency then.

1. **On the primary, before it goes offline:** `pm2 stop all && pm2 save` (so a sleep/wake can't
   resurrect a colliding bridge).
2. **On the takeover machine** (after the doctor installs deps): confirm **no `bravo-*` in
   `pm2 list`**, then:
   ```bash
   pm2 start ecosystem.config.js --only bravo-coord,bravo-telegram,dashboard-email-consumer,scheduler
   pm2 save
   caffeinate -dimsu &      # macOS: a sleeping laptop pauses every daemon
   ```
3. **Verify FUNCTION, not just "online"** — exercise each bridge's real handler once; confirm no
   `ImportError`/token error before trusting `pm2 status`. ("online" has masked a per-request crash
   for 9 days before.)
4. **Hand back on return:** `pm2 stop all` on the takeover machine → start the primary → `pm2 save`.

> **Caveat:** a travelling laptop is a weak daemon host (sleep / wifi / lid-close pause everything).
> If coordination needs to be rock-solid while away, the robust answer is moving these daemons to
> the always-on VPS (`srv1723601`), not the laptop. The SunBiz client portal on the VPS stays up
> regardless.

## What the doctor does NOT do
- It never reads or prints secret values (`.env.agents` is audited by KEY NAME only).
- It does not start daemons (that needs the single-instance safety gate above — done by hand).
- It does not install marketplace plugins or auth Codex (manual, but it tells you exactly what to run).
