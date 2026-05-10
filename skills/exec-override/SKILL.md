---
name: exec-override
description: V6 BUILD 4 operator-approval flow for the exec_guard sandbox. When a legitimate command false-positives on the regex/AST layers, the agent gets a request_id; the operator approves it from their terminal; the next attempt of the SAME command is allowed exactly once. Use when exec_guard blocks a command CC actually wants to run.
triggers: [exec_guard, override, approve, blocked command, false positive, sandbox bypass, override request, req-, single-use approval]
tier: core
dependencies: [security-protocol]
---

# EXEC OVERRIDE — Operator-Approval Flow

> **The agent never holds a token.** Every blocked command auto-creates a pending `override_request` row in `state/empire_state.db`. The operator approves the row by id; the agent's next attempt at the SAME command is allowed exactly once and the row is sealed.

## When to use this

`exec_guard.py` blocks a command CC actually intended to run. Examples that genuinely should pass:

- `git push --force origin staging` — staging branch reset, intentional.
- `psql -c "DROP TABLE _scratch_2026_05;"` — staging-table cleanup.
- `git reset --hard origin/main` — discarding local junk on a personal-only branch.

The `secret_guard` and `state_guard` are NEVER overridable. Credentials stay LLM-unreadable, period; DB-mirror writes stay blocked. Override applies to `exec_guard` only.

## The flow

### 1. Agent attempts the command

```bash
git push --force origin staging
```

`exec_guard` matches `hard-blocklist:git-force-main` (false positive — the regex only knows about `main`/`master`/`production` but the command IS allowed for `staging`). Hook returns exit 2 with stderr:

```
BLOCKED by exec_guard (hard-blocklist): matches hard blocklist pattern 'git-force-main'
  Command: git push --force origin staging
  Override request: req-7fed684e (TTL 5 min, single-use)
  To approve from your terminal:
    python scripts/exec_override.py approve req-7fed684e
  Do NOT bypass with eval, base64, or --no-verify.
  Bypass attempts are logged.
```

The agent surfaces the request_id to CC. It does NOT auto-retry, does NOT try to bypass, does NOT mint anything itself.

### 2. CC reviews and approves

From CC's interactive terminal (NOT inside the agent's chat):

```bash
python scripts/exec_override.py approve req-7fed684e --reason "staging cleanup, intended"
```

Output:

```
APPROVED  req-7fed684e
  command:  git push --force origin staging
  expires:  2026-05-10T08:14:40+00:00
  hmac:     10d44d1858e9173b...
  reason:   staging cleanup, intended

  The agent's next attempt at the EXACT same command will be allowed,
  marked consumed, and the row sealed (single-use).
```

### 3. Agent retries the same command

`exec_guard` looks up the command's sha256, finds an unconsumed approved row with valid HMAC, allows the call, and atomically marks the row `consumed`.

```
[exec_guard] allowed via approved override req-7fed684e (single-use, consumed).
```

A second attempt at the same command would block again — single-use is the contract. If CC wants to re-run, they approve a fresh request.

## Test-only bypass: `EMPIRE_OVERRIDE_FORCE_TTY=1`

There is one env-var bypass that disables the non-TTY refusal: `EMPIRE_OVERRIDE_FORCE_TTY=1`.

**Purpose:** the regression suite (`tests/test_exec_override.py`) needs to invoke `approve` from a subprocess that does not have a real TTY. Without the bypass, every test that exercises the operator path would fail. The bypass lets CI run the lifecycle tests headlessly.

**Production rule:** **NEVER set this in `.env.agents`, `.env.agents.*`, the wizard, the docker-compose env block, or any production shell.** If the var is set in production, the entire non-TTY refusal layer collapses — an LLM in a Bash tool call could approve its own request. The variable should only exist transiently in the env of a known-headless test harness.

**Audit:** `state/exec_guard.log` shows the `decision: "allowed-via-override"` rows. If you see these without a corresponding interactive `approve` invocation in your terminal history, the bypass was set somewhere it shouldn't have been. Hunt and remove.

## Hard rules (built into the validator, not just policy)

1. **Single-use.** First match consumes; subsequent matches block.
2. **Hash-bound.** Approval is keyed to `sha256(command)`. Approving `rm -rf staging/` does NOT also approve `rm -rf /` — different hashes.
3. **Time-limited.** Default TTL: 5 minutes. Maximum: 1 hour. Operator-tunable per call.
4. **HMAC-signed at rest.** Even if the agent somehow got DB write access (the guards already prevent this), it couldn't forge a valid approval row without `EMPIRE_OVERRIDE_HMAC_KEY`.
5. **Non-TTY refused.** `approve`/`deny` REFUSE if the parent process is not an interactive terminal AND `EMPIRE_OVERRIDE_FORCE_TTY=1` is not set. An LLM running in a Bash tool call cannot approve its own request.
6. **secret_guard / state_guard exempt.** Approvals never apply to credential reads or auto-generated state writes.
7. **Idempotent.** Two blocks on the same command within the TTL share the same request_id (no spam).

## Operator commands

```bash
# List recent requests (default: last 24h)
python scripts/exec_override.py list

# Only pending approval — what's CC waiting on?
python scripts/exec_override.py list --pending

# Approve a request
python scripts/exec_override.py approve req-7fed684e [--reason "..."]

# Deny a request (closes it; subsequent retries block)
python scripts/exec_override.py deny req-7fed684e [--reason "..."]

# Inspect one request as JSON
python scripts/exec_override.py status req-7fed684e

# Purge old rows (>7 days) — runnable from cron
python scripts/exec_override.py cleanup [--days 7]
```

## Where the data lives

| Surface | Location | Purpose |
|---------|----------|---------|
| Schema | `state/migrations/003_override_requests.sql` | `override_request` table |
| State | `state/empire_state.db` (table `override_request`) | The approval rows |
| HMAC key | `.env.agents` (`EMPIRE_OVERRIDE_HMAC_KEY`) | Generated lazily on first use; never logged |
| Audit | `state/exec_guard.log` (jsonl) | `decision: "blocked"` rows include `override_request_id`; `decision: "allowed-via-override"` rows record successful approvals |
| Helpers | `scripts/state_manager.py` (create/approve/deny/find/consume/list/cleanup) | Single source of truth for state reads |
| Crypto | `scripts/lib/override_crypto.py` (HMAC, hash, request-id mint, TTY detection) | Shared between exec_guard + exec_override |
| Tests | `tests/test_exec_override.py` (12 lifecycle tests) | Locked behavior |

## What this does NOT do (Phase 2 deferred)

- **Dashboard approval flow.** Phase 2 will add a `/system-health` panel listing pending requests with [Approve]/[Deny] buttons. Phase 1 is CLI only.
- **Multi-machine sync.** The override row lives in the local SQLite DB — approving on Machine A does NOT carry to Machine B. Same scope as the rest of V6.0 single-machine state.
- **Auto-pattern-learning.** Repeated approvals of similar commands could in principle teach the regex. We're not doing that — false-positive learning is a footgun. The operator approves each occurrence explicitly.

## Related skills

- `security-protocol` — credentials never LLM-readable; this skill complements that contract.
- `systematic-debugging` — when `exec_guard` blocks, debug the BLOCK first (is it a real false positive, or did the LLM misunderstand the task?). Reach for override only after the false-positive is confirmed.

## Obsidian
- [[skills/security-protocol/SKILL]] | [[brain/CAPABILITIES]] | [[ARCHITECTURE]]
