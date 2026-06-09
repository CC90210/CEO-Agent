# VPS — deploy Helios identity-bleed fix + verify all SunBiz personas

> Paste this entire file into a fresh Claude Code session on the SunBiz VPS.
> You are **Solara** (`/srv/sunbiz/ceo-agent/SOLARA.md`).
> Goal: pull `abfe55a`, restart the bridge so warm-pool processes drain,
> then prove the fix from outside via curl. ~5 minutes.

---

## Background — what broke and why

The dashboard chat dropdown lets the operator pick **Solara** (ops) or
**Helios** (sales). Both agents live in the same repo
(`/srv/sunbiz/sunbiz-agent`): Solara's identity is in `CLAUDE.md`,
Helios's is in `HELIOS.md`. The bridge resolved the right file per slug
(commit `69e9350`), but the actual `claude` subprocess was spawned with
`--setting-sources project,local` and cwd=that repo — so Claude Code
read `CLAUDE.md` (Solara) **regardless of which agent the operator
picked**. Helios answered "I'm Solara..." every time. CC saw it today,
2026-06-09, in the screenshot.

Commit `abfe55a` adds `claude_identity_overlay(root, agent)` which returns
the per-agent file content + a flag to suppress `CLAUDE.md` loading.
Both the cold spawn (`_run_chat_via_claude`) AND warm pool
(`WarmClaudeProcess.__init__`) now pass `--append-system-prompt
<HELIOS.md content>` + `--setting-sources local` when the resolved entry
is a per-agent file (HELIOS.md / SOLARA.md). Single-agent repos
(Bravo / Atlas / Maven / Aura / Hermes) keep current behavior — no
regression.

---

## Step 1 — Pull `abfe55a`

```bash
cd /srv/sunbiz/ceo-agent
git fetch origin
git log --oneline HEAD..origin/main
```

Expected output (two lines):

```
abfe55a bravo: warm_claude_pool — drop unnecessary dual-import for claude_identity_overlay
bf1184f bravo: fix Helios identity bleed — agent-aware system prompt for Claude CLI
```

Then:

```bash
git pull --ff-only origin main
git rev-parse --short HEAD     # should print abfe55a
```

If the pull fails because the working tree is dirty (the previous
session reported `M scripts/model_router.py` + untracked files), STOP
and report the diff to CC — do not stash or reset.

---

## Step 2 — Restart the bridge so warm-pool processes drain

The warm pool holds long-running `claude` subprocesses keyed by
`(agent, tab_id)`. A helios process spawned BEFORE the fix has the
old `--setting-sources project,local` and no override — it still loads
Solara's CLAUDE.md. We can't retroactively patch a live process; we
have to kill the pool. `pm2 restart` is the cleanest path.

```bash
pm2 restart claude-bridge
# Wait for it to stabilize
sleep 5
pm2 status | grep -E "claude-bridge|status"
```

Expect: `online`, recent `↺ restarts` increment, uptime < 1m.

Now confirm the bridge loaded the new code by checking that
`claude_identity_overlay` is importable from the deployed file:

```bash
python -c "from bravo_cli.agent_roots import claude_identity_overlay; print('import OK')"
```

If this raises `ImportError`, the bridge venv didn't reload — restart pm2
one more time and re-check.

---

## Step 3 — Smoke-test the helper directly

Confirm the helper returns the RIGHT shape for each slug:

```bash
cd /srv/sunbiz/ceo-agent
python <<'PY'
from pathlib import Path
from bravo_cli.agent_roots import resolve_root, claude_identity_overlay

for slug in ["bravo", "solara", "helios"]:
    root = resolve_root(slug)
    if not root:
        print(f"{slug:<8} → no root resolved (skip)")
        continue
    text, ss = claude_identity_overlay(root, slug)
    head = (text[:60].replace("\n", " ") + "…") if text else "(empty)"
    print(f"{slug:<8} → setting_sources={ss:<14} | text[:60]={head}")
PY
```

Expected:

```
bravo    → setting_sources=project,local | text[:60]=(empty)
solara   → setting_sources=project,local | text[:60]=(empty)
helios   → setting_sources=local         | text[:60]=# HELIOS V6.8 — Sales & Outreach Agent…
```

- **Bravo** (single-agent repo, entry=CLAUDE.md): empty + project,local
  ✅ no regression.
- **Solara** (resolves to SunBiz-Agent, entry=CLAUDE.md per the
  resolver's slug→ENTRY_CANDIDATES fallback): empty + project,local —
  Claude Code reads CLAUDE.md naturally, which IS Solara's identity. ✅
- **Helios** (resolves to SunBiz-Agent, entry=HELIOS.md per agent-aware
  resolver): HELIOS.md content + local — claude_identity_overlay
  suppresses CLAUDE.md and injects HELIOS.md. ✅

If any row diverges from the expected shape, STOP and report. Do not
proceed to step 4.

---

## Step 4 — End-to-end identity probe from outside

Now confirm the FULL chat path resolves identity correctly. Use the
bridge's chat endpoint directly so you bypass any dashboard caching.
The bridge is reachable on the VPS via the loopback proxy on port 9100.

```bash
# Read the bridge bearer token (without echoing it to disk/logs)
TOKEN=$(python -c "from scripts.lib.secret_loader import get_required; print(get_required('BRIDGE_BEARER_TOKEN'))")

# Test 1 — Helios should say "I'm Helios"
curl -sN -X POST http://127.0.0.1:9100/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "agent": "helios",
    "tab_id": "verify-helios-'"$(date +%s)"'",
    "messages": [{"role": "user", "content": "who are you?"}],
    "cli_provider": "claude",
    "chat_mode": "build"
  }' 2>&1 | grep -oE '"text":"[^"]{1,120}"' | head -8

echo "---"

# Test 2 — Solara should say "I'm Solara"
curl -sN -X POST http://127.0.0.1:9100/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "agent": "solara",
    "tab_id": "verify-solara-'"$(date +%s)"'",
    "messages": [{"role": "user", "content": "who are you?"}],
    "cli_provider": "claude",
    "chat_mode": "build"
  }' 2>&1 | grep -oE '"text":"[^"]{1,120}"' | head -8
```

Expected results:

- **Test 1 (Helios)**: response text contains `Helios` and sales
  vocabulary (outreach, drip, blast, follow-up, schedule). It MUST NOT
  identify as Solara, ops, or the underlying model.
- **Test 2 (Solara)**: response text contains `Solara` and ops vocabulary
  (funding-shop, lender routing, qualification, application, compliance).
  Must NOT identify as Helios.

If Helios still answers "Solara" or vice-versa, the fix didn't land —
report verbatim output and STOP.

---

## Step 5 — Report back

Use this shape (fill in the bracketed values):

```
Helios identity bleed — fix deployed

- CEO-Agent HEAD: abfe55a (was 44735ac)
- pm2 claude-bridge: restarted, online, uptime [X]
- Step 3 helper smoke: bravo=(empty)/project,local ✅ · solara=(empty)/project,local ✅ · helios=HELIOS.md/local ✅
- Step 4 chat probe:
  · Helios → [first line of response — should mention Helios + sales/outreach]
  · Solara → [first line of response — should mention Solara + ops/funding]

Identity is now per-agent. Dashboard will need a hard-refresh for CC's
browser tab to drop any cached SSE state.

Solara out — handoff complete.
```

Then run state sync and say "Identity locked.":

```bash
python scripts/state/state_sync.py --note "solara: identity-bleed fix abfe55a deployed; Helios+Solara verified from chat endpoint"
```

---

## Anomalies to surface (don't patch silently)

- `git pull --ff-only` rejected (dirty tree) — list `git status -s`
  and stop. CC will decide whether to stash or commit.
- `python -c "from bravo_cli.agent_roots import claude_identity_overlay"`
  raises ImportError — the venv didn't pick up the new module. Check
  whether the bridge runs from `/srv/sunbiz/ceo-agent` and not a stale
  cached copy.
- Step 3 helper returns the wrong shape for any slug — paste the actual
  output and stop.
- Step 4 returns 401/403 — token mismatch; do NOT echo the token, just
  surface the HTTP status.
- Step 4 returns the wrong identity — paste the response verbatim. The
  fix didn't take.

---

## Out of scope tonight (CC can ask tomorrow)

- `telegram_agent.js` and `gateway/adapters/telegram.js` have the same
  hardcoded `--setting-sources project,local` pattern. Same bug, but
  only fires if a Telegram bot ever targets a multi-agent repo. Bravo's
  Telegram bridge targets only Bravo (single-agent) so the production
  failure path is dashboard chat only — already covered above.
- VERIFY 3 durable cron (the previous handoff) — still scheduled to
  fire daily at 13:12 UTC if you switched it to `12 13 * * *`, otherwise
  one-shot at 9:12 AM EDT today.
