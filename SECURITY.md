---
tags: [root]
last_updated: 2026-05-21
---

# Security Policy — Bravo (CEO Agent)

Security is a first-class concern for every OASIS AI agent. Bravo is the
orchestrator of the C-Suite — it reads revenue data, sends outbound emails
and messages, routes tasks to sibling agents, and holds the keys to
production business systems. This document describes how we handle
credentials, what we promise, and how to report a vulnerability.

## Reporting a Vulnerability

**Do not open a public GitHub issue for a security vulnerability.**

Please email **security@oasisai.work** (preferred) or
**conaugh@oasisai.work** (fallback) with:

- A description of the issue
- Steps to reproduce (or a proof-of-concept)
- The affected version or commit SHA
- Your assessment of impact

**Response SLA**

| Stage | Target |
|-------|--------|
| Initial acknowledgement | within 48 hours |
| Severity triage | within 5 business days |
| Fix in `main` for critical/high | within 14 days |
| Coordinated public disclosure | 90 days from report, or sooner if a fix ships |

We will credit you in the fix commit and changelog unless you ask to stay
anonymous.

## Supported Versions

Only the latest commit on `main` is actively maintained. Forks and older
tags are not patched. If you are running a pinned commit older than 30
days, pull `main` before reporting — the issue may already be fixed.

## Security Posture

### Credential handling

- All secrets live in a single `.env.agents` file per install — never
  in source, never in git history, never in CI logs.
- `.env.agents` is in `.gitignore` and `.git/info/exclude`; the setup
  wizard refuses to write to any `.env*` path that is tracked by git.
- On POSIX the file is `chmod 0600` (owner read/write only). On Windows,
  NTFS ACLs inherit from the user home directory.
- The setup wizard writes values via `os.replace()` (atomic) with prior
  values redacted from stdout.

### Secret scanning

- `scripts/scan_secrets.py` runs over the working tree + git history.
  Detects 18+ credential shapes: Anthropic `sk-ant-`, OpenAI `sk-`,
  Google `AIza`, GitHub `ghp_` / `gho_`, Stripe `sk_live_`, Facebook
  long-lived tokens `EAA…`, JWT, PGP / SSH / TLS private keys, plus
  suspicious filenames (`*.token`, `credentials.json`, `*.pfx`, etc.).
- A hardened `.gitignore` blocks `*.env*`, `*_token.txt`, `credentials.json`,
  `service_account.json`, `*.pem`, `*.key`, `id_rsa`, `id_ed25519`, and
  MCP config files that contain API keys.
- If a secret is ever committed by accident, we rotate the credential
  first and rewrite history second (`git filter-repo`) — never in the
  other order.

### Outbound communication

- Every email, Telegram, LinkedIn, and Instagram message routes through
  one chokepoint: `scripts/integrations/send_gateway.py`. No business engine calls
  SMTP directly.
- The gateway enforces: CASL compliance footer, per-channel cooldown
  (email 72h, IG 48h, LinkedIn 72h, phone 168h), daily cap (email 50,
  IG 30, LinkedIn 20, phone 15), hourly caps, per-domain caps, bounce
  circuit breaker, DNS/SPF reputation check, idempotency via the
  unified `lead_interactions` ledger, and a pre-send AI critic that
  can hard-block a draft.
- 50 unit tests guard this contract (`scripts/test_send_gateway.py`).

### MCP server policy

- All enabled MCP servers are **stateless** — Playwright, Context7,
  Memory, Sequential Thinking, Knowledge Graph. No MCP server stores
  credentials in its config file.
- Credential-sensitive capabilities (Gmail, Calendar, Supabase, Stripe)
  are never routed through MCP connectors. They use CLI tools in
  `scripts/` that read `.env.agents` at runtime.
- Anyone adding a new MCP server must follow
  `skills/mcp-operations/SKILL.md` and never hardcode credentials in a
  shipped config file; a `.claude/mcp.json.template` with `${VAR}`
  placeholders is provided.

### Database access

- Supabase Row Level Security (RLS) is enabled on every table. The
  agent connects with a service-role key only when server-side; the
  dashboard uses anonymous-key + RLS for reads.
- Migrations are additive where possible (`database/*.sql`). Any
  destructive migration requires explicit human approval.

### PII and privacy

- `scripts/pii_scrubber.py` removes emails, phone numbers, SIN/SSN, and
  credit-card-shaped numbers from content before it is embedded into
  long-term memory or sent to third-party LLMs.
- User messages and lead content are stored in a customer-owned Supabase
  project. Nothing is sent to Anthropic or OpenAI beyond the specific
  prompt for a given action, and only under the `ANTHROPIC_API_KEY` /
  `OPENAI_API_KEY` the user supplies.

### Safety hooks

- `.claude/settings.local.json` registers hooks that block destructive
  shell commands (`rm -rf /`, `DROP TABLE`, force-push to `main`) and
  block any edit that would touch a `.env*` file.
- All shell commands and git operations are audit-logged to
  `tmp/hook_audit.log`.

### Known dependency exceptions

- `node-telegram-bot-api` currently pulls an unpatched transitive
  `request` dependency. Dependabot tracks this as a moderate SSRF risk.
  The repo does not pass arbitrary user-supplied URLs into that library;
  it is used only for Telegram Bot API calls with the configured bot
  token. Downgrading swaps the vulnerable chain rather than removing it.
  Remediation path: replace `node-telegram-bot-api` with a minimal
  first-party Telegram HTTP client or a maintained library before
  exposing any user-controlled Telegram fetch/proxy behavior.

## Scope for this Agent (Bravo / CEO)

Bravo has the broadest permissions of any agent in the C-Suite. By design
it can:

- Read and write the unified `lead_interactions` ledger (every outbound)
- Enqueue and approve outreach through `send_gateway`
- Invoke sibling agents (Atlas, Maven, Aura, Hermes) via cross-agent
  inbox messages
- Read the Stripe MRR stream (read-only) for revenue reporting
- Read Google Workspace (Gmail, Calendar, Drive) through `google_tool.py`
  under the installed OAuth scopes

Bravo **cannot**, by policy:

- Place live financial trades (Atlas owns that, with per-trade approval)
- Spend ad budget (Maven owns that, with spend caps)
- Trigger physical devices like door locks or cameras (Aura requires
  explicit per-action approval)
- Write to client commerce systems (Hermes operates on its own isolated
  client deployment)

## Out of Scope

This policy covers Bravo's own code and its install path. It does **not**
cover:

- Third-party SaaS misconfigurations on the customer's side (Supabase
  RLS policies the customer disables, Stripe keys the customer shares
  publicly, etc.)
- The user's own machine hygiene (disk encryption, OS patches, password
  managers)
- Vulnerabilities in upstream dependencies — those are tracked via
  GitHub Dependabot and patched in regular releases

## Coordinated Disclosure

Please give us a reasonable window to fix before public disclosure.
90 days is the default; we will ship a fix faster if we can and will
request an extension only for genuinely complex issues with clear
communication.

Thank you for helping keep our agents safe for the businesses that
depend on them.

## Related
- [[CLAUDE]]
- [[brain/INDEX]]
- [[brain/CAPABILITIES]]
