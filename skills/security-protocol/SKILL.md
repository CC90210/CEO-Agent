---
name: security-protocol
description: Application security protocol. Credential handling plus the 20-Point Vibe-Security Matrix — the mechanical audit for the twenty defects that recur in AI-generated code (RLS off, IDOR, unverified webhooks, client-side authz, injection, XSS, unvalidated uploads). Use when handling any credential, or when auditing or hardening a codebase.
triggers: [secret, credential, API key, exposed, rotation, security, token, password, leak, gitguardian, security audit, vulnerability, vulnerabilities, audit codebase, harden, RLS, row level security, IDOR, XSS, CORS, SQL injection, webhook signature, rate limit, input validation, file upload, OWASP, pentest, vibe-code security]
tier: core
dependencies: []
tags: [skill, security-protocol]
last_updated: 2026-08-15
---

# SECRETS AND AUTHENTICATION MANAGEMENT

> **Purpose:** Ensures API keys, tokens, and database credentials are NEVER exposed in plain text files when different AI platforms interact with this workspace.

## Core Rules

1. **Never hardcode secrets.** No credentials of any kind belong in entry points (`CLAUDE.md`, `ANTIGRAVITY.md`, `GEMINI.md`) or any script. No `api_key = "sk-..."` lines anywhere.
2. **Single source of truth.** All agents must read tokens exclusively from the repo's `.env.agents` file. Never put them in code, never in commit messages.
3. **No new file types that hold raw secrets.** Files like `.long_lived_token.txt`, `credentials.json`, `service_account.json` should never exist inside a repo. If a tool needs such a file, put it outside the repo and reference it by path in `.env.agents`.
4. **MCP configs absorb from env.** When generating configuration files for new MCP servers, the server init process must read keys from `.env.agents` or local shell env vars — never paste tokens into JSON configs.
5. **`.env.agents` is gitignored everywhere.** The repo root `.gitignore` in every agent must include `.env` + `.env.*` with only `.env.agents.template` whitelisted.
6. **Untrusted spawns are text-only.** Any bridge/daemon that spawns a model in response to NON-operator input (a group peer, an inbound webhook, scraped content) MUST run that spawn with **no filesystem/exec/network tools** (`--disallowedTools` for Read/Grep/Glob/Bash/Edit/Write/WebFetch/…), a **secret-stripped env**, and a **sandboxed cwd** — not merely a read-only allowlist. A `Read`/`Grep` allowlist still reaches `.env.agents` by absolute path and exfiltrates it. Only operator-gated spawns (CC's Telegram id / an identity-gated `/chat`) get file tools. Reference: `coordination_agent.js` `UNTRUSTED_DENY_TOOLS`.

## The 20-Point Vibe-Security Matrix

> **What this is.** Twenty defects that recur in AI-generated and vibe-coded applications.
> Each row is a *mechanical* check — a grep, a query, a command — not a judgement call, so a
> fresh context with no memory of the incident can still run the audit and get the same answer.
>
> **Where it sits.** The seven **Production Defenses** (`prompts/_TEMPLATE_SYSTEM_PROMPT.md`
> § 3.1) are the *build-time* contract — what you must satisfy while writing the change. This
> matrix is the *audit-time* expansion — what you sweep for across code that already exists.
> The mapping between them is in the table at the end of this section. The seven-row
> **Anti-Slop Matrix** is a third, separate thing: process defects, not security holes. Don't
> merge them.
>
> Full audit protocol, including the portfolio-wide system message:
> [[prompts/20_POINT_SECURITY_AUDITOR_SYSTEM_PROMPT]]. Contract:
> [[docs/adr/0016-20-point-vibe-code-security-standard]].

| # | The hole | The mechanical check | The standing rule |
|---|---|---|---|
| 1 | **Secrets reachable through the repo** — committed, *or* sitting in `.git/config` | `python scripts/scan_secrets.py --history` — it now checks the working tree, all history, **and every remote URL**. A working-tree scan misses leaked-then-deleted; a history scan misses `.git/config`, which is never committed. Also `git ls-files \| grep -Ei 'env\|token\|credential\|\.pem\|id_rsa'` and `git remote -v`. | Credentials live in the agents env file only — gitignored, and unreadable by the model (`secret_guard`). Never `https://<token>@host/...` as a remote; let the credential helper answer. Any exposed secret is rotated at the provider **first** — stripping it locally does not un-expose it — and scrubbed second. **2026-08-16:** a live GitHub PAT sat in a remote URL and every file-based check missed it, because the row used to say "committed" and it never was. |
| 2 | **Real API key reachable from the frontend** | `grep -rn 'NEXT_PUBLIC_\|EXPO_PUBLIC_' app/ lib/ components/`, then check each name is a *publishable* credential; `grep -rln "'use client'" \| xargs grep -n 'process\.env\.'` | Only publishable keys cross to the client. A private key (`service_role`, `sk_live_`, `sbp_`, provider API keys) is used from a route handler that proxies the call — never shipped in the bundle. |
| 3 | **Row Level Security left off** | For every `CREATE TABLE` in `database/*.sql`, require a matching `ENABLE ROW LEVEL SECURITY` (and `FORCE` where users hold keys) plus at least one policy. `apply_migration.py --allow-rls` is required when a migration touches RLS. Verify live: `SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname='public';` | RLS on every user-key table, with an explicit `auth.uid()` or `tenant_id` policy — enabled without a policy denies everyone and is usually a misconfiguration, not a lock. On **service-role** paths RLS is bypassed by design — there the tenant filter (#14) is the entire boundary, and "we have RLS" is a false comfort. |
| 4 | **Permission checked in the frontend** | Enumerate `app/api/**/route.ts` + server actions; each privileged one must re-derive role and tenant server-side. Prompt text and hidden buttons gate nothing. | [[brain/EXECUTION_RULES]] § 14 — security boundaries are server-side. `lib/role-gates.ts` is the single source; a route that never calls it is not gated by it. |
| 5 | **No rate limiting — or a bypassable one** | Every public **mutation, login, signup and AI/inference** route needs an IP + user token bucket. Find them, then read the limiter's **key**. | Key on **client IP + authenticated user id**. A limiter keyed on caller-supplied data (a body `lead_id`, an email) is bypassed by minting a fresh value — a finding even though a limiter exists. |
| 6 | **SQL built by string concatenation** | `grep -rnE '(SELECT\|INSERT\|UPDATE\|DELETE).*(\{\|%s\|\+ *[a-z_]+\|\$\{)'` across `.py`/`.ts`; audit every `execute_sql` and raw libSQL call | Parameterized binds only. For *structural* work on SQL (tenant-scoping, rewriting), **parse it** — `sqlglot`, never a regex; see the *security boundary needs a parser* pattern ([[memory/PATTERNS]]). |
| 7 | **No server-side input validation** | Every `POST`/`PUT`/`PATCH` handler must parse the body through a schema. A TypeScript `as SomeType` cast validates **nothing** at runtime — it is the most common false positive here. | Zod (TS) / Pydantic (Python) at the boundary, and the handler consumes the **parse result**, never the original body object. |
| 8 | **User content rendered as raw HTML** | `grep -rn 'dangerouslySetInnerHTML\|innerHTML\|v-html'` — then trace each one's data source back to whether a stranger can reach it | Plain text by default. Where HTML is genuinely required (rendered email), sanitize explicitly with DOMPurify at render time. Inbound email bodies are the hottest source — see the Untrusted Content Discipline block in every entry point. |
| 9 | **Passwords stored in plaintext** | `grep -rniE 'bcrypt\|md5\|sha1\|hashlib.*password'` — the correct result is **zero** custom password code | Delegate entirely to Supabase Auth (Argon2id/bcrypt under the hood). Raw password handling anywhere in this fleet is a defect on sight, not a design to review — the acceptable number of hand-written hashing call sites is zero. |
| 10 | **Auth tokens in `localStorage`** | `grep -rn 'localStorage\|sessionStorage'` and confirm nothing token-shaped is stored; then check the session cookie flags | `httpOnly` + `Secure` + `SameSite=Strict` cookies. A token in `localStorage` is readable by any XSS on the page — that is what upgrades #8 from defacement to account takeover. |
| 11 | **Admin surface exposed, or leaking into a public page** | Diff `middleware.ts:PUBLIC_PATH_PREFIXES` against `app/layout.tsx:FULL_BLEED_PREFIXES` — a prefix in one and not the other is the bug | [[brain/EXECUTION_RULES]] § 13 — public routes need **two** layers. Missing the middleware layer 401s the share link; missing the layout layer renders the operator sidebar over a prospect's view. Verify in incognito against production, never a dev session. Debug and internal diagnostic routes must be stripped from the production build, not merely unlinked. |
| 12 | **CORS set to `*`** | `grep -rn 'Access-Control-Allow-Origin\|cors('` plus the `next.config.*` headers block | Explicit origin allowlist (`oasisai.work` and its subdomains, per-product domains). A wildcard on a credentialed endpoint is a finding regardless of what that endpoint returns. |
| 13 | **No email verification on signup** | Read the signup and invite flows; confirm a verified state gates privileged features | Unverified accounts may exist; they may not act. Verified email before anything writes or spends. |
| 14 | **Predictable id with no ownership check (IDOR)** | For every query keyed on a row id, require an adjacent `tenant_id`/`user_id` predicate. Then invert it: every module that **filters** on the partition key must **stamp** it on `.insert(` / `.upsert(` | [[brain/EXECUTION_RULES]] § 17 — write what you filter. A read filter with no matching write stamp hides rows; a read with no filter leaks them. Prove isolation by querying as anon **and** as an authed user of the wrong tenant. |
| 15 | **Raw request body saved on update** | `grep -rn '\.\.\.body\|\.\.\.req\.json()\|\.update(body)\|\*\*payload'` | Assignable fields are whitelisted through the schema parse result. Spreading a body lets a caller set `role`, `tenant_id`, or `is_admin` on a route that never meant to expose them. |
| 16 | **Webhook with no signature check** | Enumerate every inbound receiver (Stripe, Telegram, Late/Zernio, email provider, n8n). Verification must happen **before** the body is parsed or trusted | `stripe.webhooks.constructEvent` against the **raw** body; a secret token for Telegram; HMAC for generic providers. **An unset secret MUST fail closed** — `if SECRET and not compare_digest(...)` skips the check entirely wherever the variable was never set, which is exactly the defect found in `webhook_listener.py` on 2026-08-15 (fixed). Then dedup on the provider event id, scoped by tenant (the *tenant-scoped dedup* pattern ([[memory/PATTERNS]])). |
| 17 | **Stack trace surfaced to a user** | `grep -rn 'err\.stack\|traceback\.format_exc()\|String(err)\|JSON.stringify(error)'` and check each is **logged**, not **returned** | Log the full traceback (`agent_events`, `tmp/cron_failures/`) and return a generic error shape carrying a **correlation id** the operator can use to find that traceback. This is the exact inverse of Anti-Slop #2: swallow nothing internally, leak nothing externally. |
| 18 | **Dependencies never updated** | `npm audit` / `python -m pip_audit`; `gh api repos/<owner>/<repo>/dependabot/alerts --paginate`; confirm `.github/dependabot.yml` exists | [[brain/EXECUTION_RULES]] § 16 — bot review signal is input to the loop. An alert a bot already raised and you ignored is worse than one you never had. |
| 19 | **No password strength or breach check** | Read the auth provider's password policy configuration | Minimum 12 characters plus a breach check (HaveIBeenPwned, or Supabase's built-in). Length beats composition rules. |
| 20 | **File uploads with no validation** | Find every upload path; require a MIME/extension allowlist, a size cap, and a storage path anchored to the tenant prefix — enforced by a DB `CHECK`, not only in application code | SVG is executable in a browser: accepting it as an image is stored XSS. Store uploads outside the web root with no execution flags, and anchor `storage_path` to `tenant_id/` with a DB `CHECK` so an application bug cannot cross tenants. |

### Mapping to the seven Production Defenses

The defenses are the build-time contract; the points are what each decomposes into when you
audit code that already exists. A defense marked `N/A — <reason>` in a system prompt therefore
also declares its points out of scope — which is the only legitimate way to skip one.

| Defense (`_TEMPLATE_SYSTEM_PROMPT.md` § 3.1) | Points it expands into |
|---|---|
| 1 — Probe credentials first | 1, 2 |
| 2 — No UI-only security | 3, 4, 9, 10, 11, 12, 13, 19 |
| 3 — Tenant data isolation | 14, 15, 20 |
| 4 — Closed-loop error tracking | 17 |
| 5 — Verified restore point | *(no point — a recoverability defense, not a vulnerability class)* |
| 6 — Server-side payment math | 16 |
| 7 — Zero unrequested visual rewrites | *(no point — a scope defense)* |
| *(unowned — no single defense covers these)* | 5, 6, 7, 8, 18 |

That last row is the honest gap. The seven defenses were written for *building a feature* and
never covered untrusted-input handling or dependency hygiene as first-class concerns. It is why
this matrix is a superset rather than a restatement, and why an audit run against the defenses
alone would have missed five of the twenty.

## Detection — Run Before Every Push

Every agent ships with `scripts/scan_secrets.py`. Run it before shipping anything sensitive:

```bash
# Fast: scan the working tree (skips gitignored files)
python scripts/scan_secrets.py

# Thorough: scan every commit in every branch (catches leaked-once-then-deleted)
python scripts/scan_secrets.py --history

# Scan a sibling agent's repo
python scripts/scan_secrets.py --path ~/CMO-Agent
```

The scanner catches (non-exhaustive):
- Anthropic, OpenAI, Google AI keys (`sk-ant-`, `sk-`, `AIza`)
- GitHub PATs (`ghp_`, `gho_`, `github_pat_`)
- Supabase service role (`sbp_`)
- Stripe live/test secrets (`sk_live_`, `sk_test_`)
- AWS access keys (`AKIA`, `ASIA`)
- Slack, Discord, Telegram bot tokens
- Twilio SIDs
- **Facebook/Meta long-lived access tokens (`EAA...`)** ← the 2026-04-24 CMO-Agent leak pattern
- PGP / SSH / JWT material
- Suspicious filenames (`*_token.txt`, `credentials.json`, `id_rsa`, etc.)

## Incident Response — When A Leak Is Discovered

### 1. Rotate the credential at its provider BEFORE anything else
The leaked value is already public. Scrubbing git history on its own is insufficient — attackers may have already cloned. Revoke first.

- Anthropic: https://console.anthropic.com/settings/keys → Revoke
- OpenAI: https://platform.openai.com/api-keys → Delete
- Stripe: dashboard → Developers → API keys → Reveal & Roll
- GitHub: https://github.com/settings/tokens → Delete
- Facebook/Meta: https://developers.facebook.com/apps → Settings → Basic → **Reset App Secret** (this invalidates every token ever issued to the app)
- Supabase: project → Settings → API → generate new service_role
- Telegram bots: @BotFather → `/revoke`

### 2. Scrub git history
```bash
pip install git-filter-repo
git branch emergency-backup-before-scrub
git filter-repo --path <leaked-file> --invert-paths --force
git push origin --force --all
git push origin --force --tags
```

### 3. Prevent recurrence
Add the leaked file's pattern to `.gitignore`, then commit + push.

### 4. Notify
If the leak affected anything client-facing (Stripe, client tokens, client data), notify CC immediately. Write a Reflexion entry in `memory/MISTAKES.md` documenting the root cause.

## Known Leak Patterns (add to `.gitignore` of every new repo)

```gitignore
# Secrets
.env
.env.*
!.env.agents.template
!.env.example

# Token/credential files
*.token
*_token.txt
*_token.json
*token*.txt
.long_lived_token*
credentials.json
service_account.json

# SSH / TLS
id_rsa
id_ed25519
*.pem
*.key
*.p12
*.pfx

# MCP configs (often carry API keys)
.claude/mcp.json
.vscode/mcp.json
```

`templates/agent-scaffold/.gitignore` ships with all of this — every forged agent inherits it.

## Incidents Log

**2026-04-24 — CMO-Agent Facebook token leak**
- Root cause: `.long_lived_token.txt` (183-char Facebook long-lived User Access Token) was committed in Maven's initial commit `3e6e83e` on 2026-04-18. When CMO-Agent was flipped public later (to enable the cross-agent OASIS AI setup wizard clone flow), the token became world-readable. GitGuardian flagged it.
- Detection gap: `.env*` was gitignored but not `*.token` / `*token*.txt`. The filename didn't trip the narrow gitignore.
- Fix applied: `scripts/scan_secrets.py` + hardened `.gitignore` patterns + scanner in `bravo setup` workflow + this skill updated.
- Prevention: every forged agent now inherits the hardened `.gitignore` via `templates/agent-scaffold/`. Pre-push scans recommended before any public flip.
- **STILL OPEN — step 2 of Incident Response above was never performed (verified 2026-08-15).** The blob is deleted from the working tree and gitignored, which prevents a re-add and does nothing about history. Git metadata confirms it live: blob `96ae2fd` (193 bytes) introduced in `5a3649d`, removed in `50d4ed7`, and `git branch -r --contains 5a3649d` returns **10 remote branches including `origin/main`** — so GitHub still serves the object. Deletion is not rotation and it is not a scrub. What actually closes this is step 1 (Reset App Secret at Meta, which invalidates every token ever issued to the app); if that was done the blob is inert and the scrub is hygiene. **CC: confirm the reset happened.** This entry exists because an incident log that stops at "fix applied" reads as closed, and this one is not.

## Safe Handling in Subagents

When spawning subagents that need API access, pass secrets via environment variables or a shared `.env.agents` path reference — never paste the raw string into the prompt structure.


## Outbound Gate Compliance

> **All outbound communications** (emails, notifications, messages) referenced in this skill
> MUST be routed through `scripts/integrations/send_gateway.py`. Direct `smtplib` or raw
> SMTP calls are architecturally prohibited (V5.6 chokepoint rule). Use:
> ```bash
> python scripts/integrations/send_gateway.py send --channel email --to <email> --subject "..." --body "..." --lead-id <uuid>
> ```
> See [[skills/send-gateway/SKILL.md]] for the full contract.

## Obsidian Links
- [[skills/INDEX.md]] | [[brain/CAPABILITIES]] | [[memory/MISTAKES]]
- [[docs/adr/0016-20-point-vibe-code-security-standard]] (the contract) | [[prompts/20_POINT_SECURITY_AUDITOR_SYSTEM_PROMPT]] (the portable audit prompt)
- [[brain/EXECUTION_RULES]] § 21 (the incident behind each point) | [[CONTEXT]] (canonical terms)
- `scripts/scan_secrets.py` (the detection tool)
- `scripts/tests/test_20_point_security_contract.py` (the drift gate)
- `templates/agent-scaffold/.gitignore` (the baseline)
