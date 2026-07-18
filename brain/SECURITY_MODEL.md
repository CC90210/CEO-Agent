---
description: "Agent Command Center security model: multi-tenant RLS isolation, bearer+cookie auth, field encryption, bridge pairing — every claim mapped to migrations"
tags: [security, architecture, multi-tenant, encryption, hmac, rls, canonical]
purpose: Single canonical doc explaining how the Agent Command Center secures multi-tenant data, authenticates bridge daemons, and isolates per-client identity. The answer to "is this military-grade?" is in this file.
last_updated: 2026-06-09
freshness_threshold_days: 90
verified: 2026-06-09
---
# SECURITY MODEL — Agent Command Center

> Every claim below maps to a file path or migration. This doc rots if the
> code drifts; review it any time `/api/auth/`, `/api/bridge/`,
> `lib/field-encryption.ts`, or any `database/0XX_*.sql` touching
> `bridge_pairings` / `agent_model_config` / `tenants` changes.

---

## 1. Multi-tenant model

**One shared dashboard. One shared Supabase. N tenants. Tenant ID on every row that matters.**

- **Dashboard:** `agent-dashboard-cc90210.vercel.app` (Vercel-hosted Next.js).
  Same URL for CC and every paying client. Routes are tenant-aware via
  the auth-cookie / bridge-token resolution path.
- **Supabase:** project ref `phctllmtsogkovoilwos`. Single Postgres; isolation
  enforced via Postgres Row-Level Security (RLS) policies, not by
  separate databases.
- **Tenant identifier:** UUID in `public.tenants.id`. CC's tenant id is
  `ef8d389e-3f15-43f2-ae00-3660f69a1452`. Every tenant-scoped row carries
  `tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE`.
- **Resolution:** API routes get the caller's `tenant_id` either from
  - the auth cookie (browser users → `getSessionUser()` → `auth_user_id` →
    `user_profiles.tenant_id`), or
  - the bridge bearer token (daemons → `bridge_pairings.tenant_id` looked
    up by SHA-256 hash of the token).
  Never from request body. Tenant identity is server-derived, period.

### RLS coverage (verified 2026-05-09)

`grep -lE "ENABLE ROW LEVEL SECURITY" database/*.sql` returns 7 files spanning
every tenant-scoped table I checked. Per-table verification: see below.

| Table | Migration | RLS | Tenant-scope policy |
|---|---|---|---|
| `tenants` | 018 | YES | self-select via `auth_user_id` |
| `user_profiles` | 017 | YES | tenant + auth_user_id |
| `agent_model_config` | 020 | YES | tenant_id |
| `chat_sessions` | 020 | YES | tenant_id |
| `chat_messages` | 020 | YES | tenant_id |
| `bridge_pairings` | 020 | YES | tenant_id |
| `bridge_pair_codes` | 032 | YES | tenant_id |
| `mrr_snapshots` | 021 | YES | tenant_id |
| `agent_messages` | 028 | YES | tenant_id |
| `agent_state_snapshot` | 008 | YES | tenant_id |
| `agent_events` | 006 | YES | tenant_id |
| `integrations_health` | 017 | YES | profile_id (per-tenant) |
| `plans` / `plan_templates` | 017/018 | YES | tenant_id |
| `leads` / `lead_interactions` | (legacy) | YES | tenant_id |
| `email_log` / `outbound_log` | (legacy) | YES | tenant_id |

### What "service role" bypasses RLS

The Next.js API routes use the Supabase SERVICE_ROLE key
(`getServiceSupabase()`), which bypasses RLS by design — RLS would block
the routes from doing tenant-aware queries on behalf of users. The trade
is: every API route MUST manually filter by the resolved tenant_id (see
the resolution rules above). Bypassing tenant-id derivation in a route
is a security bug. Reviewers: grep new routes for `.from(...)` without
an `.eq('tenant_id', ...)` filter near it.

---

## 2. Encryption at rest — provider API keys

CC's clients paste their Anthropic / OpenAI / OpenRouter / etc. API keys
into the Settings UI. We store them encrypted, decrypt at agent-spawn time.

**Implementation:** `oasis-command-center:lib/field-encryption.ts`
- **Algorithm:** AES-256-GCM (authenticated encryption — tampering is
  detected via the GCM auth tag).
- **Key derivation:** Node's `scryptSync(passphrase, "oasis-bravo-v1", 32)`.
  Salt is fixed at the deploy level; rotating the salt orphans every
  stored ciphertext.
- **Master secret:** `BRAVO_FIELD_ENCRYPTION_KEY` env var (deployed in
  Vercel only, never committed). Minimum 16 chars; the lib refuses to
  start if missing or shorter.
- **On-disk format:** `base64(iv).base64(authTag).base64(ciphertext)` — three
  base64 chunks separated by literal periods. Stored in
  `agent_model_config.encrypted_api_key`.
- **Why not `pgcrypto`:** the supabase-js client round-trips Postgres
  `bytea` inconsistently across PostgREST versions (hex `\x...` vs
  base64 vs raw). Doing crypto in Node sidesteps that entirely.

**Rotation policy:** `BRAVO_FIELD_ENCRYPTION_KEY` is treated as a
deploy-wide master secret. Never rotate without a migration that
re-encrypts every row (no such migration exists today — flagged for
when CC chooses to rotate).

---

## 3. Bridge token lifecycle

The local bridge daemon (`bravo bridge serve`) authenticates to the
dashboard via a long-lived bearer token.

**Mint:** `POST /api/auth/pair` →
- generates `oab_<32-byte-hex>` (66-char ASCII)
- SHA-256 hashes it
- stores hash in `bridge_pairings.bridge_token_hash`
- returns the plaintext token to the daemon ONCE

**Storage on daemon:** `~/.oasis/bridge_token`. On Unix, chmod 600 (verified
in `bravo_cli/local_bridge.py` and the chat-server's `_self_pair_if_needed`).
On Windows, ACL inherits from the user profile (no tighter permission
applied).

**Verify:** `POST /api/bridge/ping` reads the `Authorization: Bearer <token>`
header, SHA-256 hashes the plaintext, looks up the row by hash. Returns
401 on no match, 403 on revoked.
- The lookup is by hash, not equality on a known-id+hash pair, so the
  attacker has no oracle for a timing attack on the hash itself. SQL
  `.eq()` is not constant-time at the SQL layer, but the design makes
  this immaterial in practice. (Tier C2 in the plan would change the
  wire format to send `pairing_id` alongside the token, enabling true
  constant-time compare in Node — deferred until there's a concrete
  reason; not shipping today.)

**Rotation:** the pair endpoint is now idempotent by `(tenant_id,
machine_fingerprint)` (migration 030 + commit d0e15e0). Calling pair
again from the same machine ROTATES the token — the row's
`bridge_token_hash` is updated, the daemon receives a fresh plaintext,
the prior token stops verifying immediately. Nothing to clean up.

**Revocation:** set `revoked_at` non-null on the `bridge_pairings` row.
`/api/bridge/ping` returns 403 once revoked. The dashboard `/operations`
page filters revoked rows from the visible list.

---

## 4. HMAC self-pair (bridge-side bootstrap)

Operators don't have `CLI_SIGNUP_SECRET` in their local env (that lives
on Vercel only). To let the bridge self-pair without operator interaction,
we use a per-profile HMAC secret.

**Issued by:** `python scripts/integrations/n8n_webhook_secret.py issue --save-env`
- generates a random 32-byte secret
- SHA-256 hashes it
- stores hash in `n8n_webhook_secrets.secret_hash` keyed by `profile_id`
- writes plaintext to operator's `.env.agents` as
  `OASIS_OUTBOUND_HMAC_SECRET`

**Verify:** `_hmacAuthEmail()` in `oasis-command-center:app/api/auth/pair/route.ts`
- reads `x-oasis-profile-id` + `x-oasis-secret` headers
- validates profile_id is a UUID (regex)
- SHA-256 hashes the secret
- looks up `n8n_webhook_secrets` by `(profile_id, secret_hash, revoked_at IS NULL)`
- returns the resolved email or null

**Constant-time-compare consideration:** as of Tier C1 (this PR), the
verification path pulls the row by `profile_id` first, then uses
`crypto.timingSafeEqual` to compare hashes. Eliminates the (theoretical)
timing side-channel from the DB indexer. Falls back to null on length
mismatch (timingSafeEqual requires equal-length buffers).

**Dual-use note:** the same HMAC secret also authenticates the outbound
write-through path used by n8n for inbound lead webhooks. One credential,
two purposes. Documented in the route's `_hmacAuthEmail` comment.

---

## 5. Cross-tenant attack surface

What a malicious authenticated user CAN'T do:
- Read another tenant's chat messages, agents, leads, MRR, or any other
  tenant-scoped row → blocked by RLS.
- Pair a bridge to another tenant → would require a stolen
  `OASIS_PROFILE_ID` + `OASIS_OUTBOUND_HMAC_SECRET` pair (both server-
  verified before any DB mutation).
- Replay another tenant's bridge token → token is bound to a specific
  `tenant_id` in `bridge_pairings`; the ping endpoint resolves tenant
  from the token row, not the request body.
- Bypass RLS via the API → API routes use the service role, but EVERY
  tenant-scoped query manually filters by the resolved tenant_id (this
  is the contract reviewers must enforce on new routes).

What a malicious actor with HOST access to the operator's machine CAN do
(and we don't defend against — host compromise is out of scope):
- Read `~/.oasis/bridge_token` → impersonate that bridge until revoked.
- Read `.env.agents` → exfiltrate the operator's API keys (Anthropic /
  Stripe / Supabase service role / etc.).
- Modify the wizard / bravo_cli code → MITM future operator commands.

Mitigations against host compromise (operator's responsibility, not
the platform's):
- Disk encryption (FileVault / BitLocker / LUKS).
- OS-level user account password — file-mode 600 on `~/.oasis/bridge_token`
  prevents same-host other-user reads.
- `.env.agents` is gitignored; never commit it.

---

## 6. Audit trail + rate limiting

- **`pair_attempts` table** (migration 031, shipped) — every call to
  `/api/auth/pair` writes a row with `(profile_id, outcome, attempted_at,
  ip)`. Outcome vocabulary: `ok | invalid_hmac | invalid_bearer |
  rate_limited | missing_headers`. Service-role only; not exposed to
  tenant users. Used both for the rate-limit gate (below) and as a
  forensic trail for "who tried to pair when from where."
- **Rate limit on `/api/auth/pair`** — if a `profile_id` accumulates ≥10
  failed attempts in any 60-second window (counting only `invalid_hmac`,
  `invalid_bearer`, `missing_headers` — successes don't push toward the
  limit), the route returns `429 rate_limited` and records the
  outcome. Window is intentionally short so a typo doesn't lock out a
  legitimate operator for long; threshold is intentionally low because
  the only legitimate caller (the bridge daemon) hits the endpoint once
  per re-pair.
- **`audit_log` table** — broader cross-route audit logging is on the
  roadmap. For now, security-sensitive events that don't touch the pair
  endpoint write to: bridge_pairings (revoked_at on revoke), agent_events
  (every cron fire / agent reasoning loop / outbound send — tenant-scoped
  via RLS, visible at /operations Activity Tape).
- **Bridge log:** `~/.oasis/bridge.log` (operator's machine). Captures
  every heartbeat result, every chat-server start/stop, every pair
  attempt. Local only — never transmitted.

---

## 7. What's NOT in the threat model (intentional)

- **Self-hosted Supabase:** clients use the shared `phctllmtsogkovoilwos`
  Supabase project. RLS isolates them at the row level. A client who
  needs strict data residency / their own Postgres has Tier B (cloud-
  only mode) or Tier D self-hosting on their roadmap — not shipped.
- **Hardware security modules (HSM) for key management:** AES-256-GCM
  with a strong scrypt-derived key from an env-var passphrase is the
  current standard. HSM integration is a future hardening pass; not
  blocking ship.
- **Penetration testing / formal certification:** SOC 2 / ISO 27001
  paperwork is not in scope for V6. Code is open to read; CC's clients
  can audit independently if their compliance regime requires it.

---

## 8. Verification commands

Run these to spot-check the claims above:

```bash
# RLS enabled on all tenant-scoped tables (should print all listed in §1)
grep -lE "ENABLE ROW LEVEL SECURITY" database/*.sql | xargs grep -hE "ENABLE ROW LEVEL SECURITY" | sort -u

# Plaintext live secrets in MCP configs (should be ZERO)
python scripts/audit_mcp_secrets.py

# Bridge tokens never returned from any API except the mint endpoint
grep -rn "bridge_token" oasis-command-center:app/api --include="*.ts" | grep -v "pair/route.ts"
# (only matches in pair/route.ts are expected)

# Constant-time HMAC compare wired in pair route (Tier C1)
grep -n "timingSafeEqual" oasis-command-center:app/api/auth/pair/route.ts

# Migration 030 applied (idempotent pair)
python scripts/integrations/supabase_tool.py select bridge_pairings --columns "machine_fingerprint" --limit 5
# Then attempt a duplicate insert via the Python client — should fail with code 23505
```

---

## 9. Agent-side execution guards (V6 PreToolUse hooks)

Three Python hooks gate every tool call an AI makes in this repo. They are
wired in `.claude/settings.local.json` under `PreToolUse` and read their mode
from `EMPIRE_HOOK_*` env vars (`enforce` | `report` | `off`) via
`scripts/lib/hook_runtime.mode_from_env`. Audit trails: `state/<guard>.log` (JSONL).

| Guard | File | Blocks | **Mode (2026-06-09)** |
|---|---|---|---|
| **secret_guard** | `scripts/state/secret_guard.py` | Read/Edit/Write on `.env*`, `*.pem`, `*.key`, `*.p12/.pfx`, `credentials.json`, `secrets/`; Bash that cat/grep/cp/exfils them | **enforce** |
| **exec_guard** | `scripts/state/exec_guard.py` | `DROP/TRUNCATE`, `DELETE` w/o `WHERE`, `ALTER … DROP`, `rm -rf /`, `git push --force` to main, `git reset --hard <ref>`, `git clean -fdx`, fork bombs, `dd` to disks (hard blocklist + sqlglot AST) | **enforce** |
| **state_guard** | `scripts/state/state_guard.py` | Edits / shell-redirects to auto-generated mirrors (`memory/SESSION_LOG.md`) | **report** |

**Mode rationale (audit Phase 3, 2026-06-09):**
- `secret_guard` → **enforce**: secret access should always be gated. This is the
  agent-layer mitigation for the §5 "read `.env.agents`" risk — the LLM itself
  can no longer read or copy secret files; it must go through a CLI wrapper that
  loads the secret in-process and returns sanitized JSON. (Host compromise by a
  human with shell access remains out of scope per §5.)
- `exec_guard` → **enforce**: the 14-day would-block count was 0 (no false
  positives in the soak window — last guard activity 2026-05-22), so enforce ships
  with no known legitimate command being blocked.
- `state_guard` → **report** (up from `off`): logs would-be clobbers of the
  auto-generated SESSION_LOG mirror without blocking yet; promote to `enforce`
  after a soak once `EMPIRE_V6_MODE=on` is the steady state.

**Where modes live:** authoritative for the Claude Code runtime in
`.claude/settings.local.json` (`env` block). Other runtimes (VPS daemons,
`bridge_chat_server`) read the same `EMPIRE_HOOK_*` keys from `.env.agents`
(operator-maintained — the LLM can't write `.env*`, by design of secret_guard).

**The block IS the protection** — there is no override/approval-queue path
(deleted 2026-05-22 per CC). A blocked agent picks a different approach; it does
not get to request a human to approve the dangerous command.

## 10. Outbound email compliance is enforced at every send surface (Phase 2)

CASL suppression + footer + List-Unsubscribe headers are applied by
`scripts/integrations/send_gateway.py` (the canonical chokepoint) AND, as of
2026-06-09, by `scripts/dashboard_email_consumer.py` (the drawer-queue daemon,
which sends via `lib.smtp_send` directly, bypassing the gateway). Both now gate
commercial sends on `casl_compliance.should_suppress` and stamp the CASL footer
for non-internal intents. `scripts/email_doctor.py` check #5 structurally fails
the build if any new file under `scripts/` imports `smtplib`/`lib.smtp_send`
without being on its allowlist — so a future send path can't silently skip
compliance again.

---

## Obsidian Links
- [[brain/CROSS_MACHINE_SYNC]] (the operating rules)
- [[docs/deploy/MULTI_MACHINE_PAIRING_PROMPT]] (the canonical pairing playbook)
- [[brain/CAPABILITIES]] (what tools the agent has — what it CAN do)
- [[memory/MISTAKES]] (what we learned the hard way — including the
  2026-05-06 plaintext Stripe key leak that drove the MCP-shim
  hardening pass)
