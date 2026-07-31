---
title: Bravo V6.0 — Enterprise-Grade Architecture
author: Bravo (acting as Principal Systems Architect)
status: DRAFT — pending CC review
date: 2026-04-22
supersedes: V5.7 (file-based LLM-OS)
tags: [architecture, v6, infrastructure, security, rag, event-driven, docker]
last_updated: 2026-07-20
---

# Bravo V6.0 — Principal Architect's Response

> Answering the four V6.0 questions posed in the upgrade brief. This is a **design document**, not an implementation plan. Implementation phasing appears at the end of each section.

---

## Preamble — What V5.7 got right, what it didn't

V5.7's bet on plain-text Markdown was correct for the bootstrap phase: zero framework lock-in, every file auditable by a human in 30 seconds, context portable across Claude / Gemini / Antigravity. That stays. V6.0 does **not** delete files. V6.0 adds an **indexing and eventing layer** on top of the existing file tree. The Markdown is the source of truth for humans; the index is the source of truth for agents.

**This is the inversion.** Today agents read files. In V6.0 agents query an index; the files become the derived, human-readable mirror of that index.

Three vulnerabilities to fix in order of severity:
1. **Pulse Protocol race condition** — concurrent JSON writes corrupt state. Highest *correctness* risk.
2. **Context collapse** — 15-25k tokens loaded at boot, lost-in-the-middle forgetting. Highest *cost* risk.
3. **IDE dependency** — Bravo only runs when a human opens a terminal. Highest *scale* risk.

---

## Q1 — Memory Migration (cut token burn, keep the Obsidian graph)

### Decision: **Supabase `pgvector` + BM25 hybrid retrieval. Markdown remains source of truth.**

We already pay for Supabase. We already have `agent_traces`, `session_logs`, and `memories` tables per migration 002. Adding `pgvector` is a single extension + one new table. We do **not** stand up Qdrant as a second DB — two memory systems is how we got fragmentation in V5.5.

### Design

**New table: `memory_chunks`**

```sql
create extension if not exists vector;
create extension if not exists pg_trgm;   -- lexical fallback

create table memory_chunks (
  id               bigserial primary key,
  source_file      text not null,         -- e.g. 'memory/SESSION_LOG.md'
  source_heading   text,                  -- nearest H2/H3 heading — provenance anchor
  chunk_index      int not null,          -- ordinal within file
  content          text not null,
  content_hash     text not null,         -- sha256 — detect unchanged chunks
  embedding        vector(1536),          -- OpenAI text-embedding-3-small or local nomic-embed
  metadata         jsonb not null default '{}',
  tags             text[] not null default '{}',
  freshness        timestamptz not null default now(),
  confidence       float not null default 1.0,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  unique (source_file, chunk_index)
);

create index on memory_chunks using ivfflat (embedding vector_cosine_ops) with (lists = 100);
create index on memory_chunks using gin (to_tsvector('english', content));
create index on memory_chunks using gin (tags);
create index on memory_chunks (source_file);
```

### The three new scripts

| Script | Role |
|---|---|
| `scripts/core/memory_chunker.py` | Parse MD by H2/H3 boundaries, max 1000 tokens/chunk, preserve frontmatter + wiki-link context per chunk |
| `scripts/core/memory_ingest.py` | Walk `brain/`, `memory/`, `knowledge/`, `APPS_CONTEXT/` → diff against `content_hash` → only re-embed changed chunks → upsert. Idempotent. Runs on file-save hook + nightly cron |
| `scripts/core/memory_query.py` | Takes a task string → embed → hybrid search (70% vector cosine + 30% BM25 trigram) → return top-k with freshness decay applied → emit markdown-formatted context block |

### Retrieval contract (how agents consume it)

```bash
python scripts/core/memory_query.py \
  --task "Alejandro retainer status" \
  --k 8 \
  --max-tokens 3000 \
  --always-include brain/STATE.md,brain/USER.md \
  --format markdown
```

Returns: 8 most relevant chunks across all memory, each prefixed with provenance (`### from memory/project_<client_slug>.md § Retainer Pitch`), with always-included files appended verbatim. Total output bounded by `--max-tokens`.

### What still loads at boot (unchanged)

- `CLAUDE.md` (120 lines — rules)
- `brain/SOUL.md` (identity — immutable)
- `brain/STATE.md` (ephemeral — operational state)
- `brain/USER.md` (CC's profile — critical links)

That's the floor: ~5k tokens, always on. Everything else is retrieved on demand.

### Realistic token reduction

Honest numbers, not the 90% in the brief:

| Context | V5.7 boot | V6.0 boot |
|---|---|---|
| CLAUDE.md + SOUL + STATE + USER | 5k | 5k |
| CAPABILITIES, AGENTS, ORCHESTRATION | 8k | 0k (retrieved) |
| SESSION_LOG, ACTIVE_TASKS tail | 6k | 1-2k (retrieved top-k) |
| MEMORY.md index + leaf memories | 4-6k | 2k (retrieved top-k) |
| **Total boot context** | **23-25k** | **8-10k** |

**~60-65% reduction at boot.** The "90%" only holds for specific narrow-task turns where a single retrieval covers the whole prompt. Claim the real number to CC and to clients — marketing language breaks trust when clients benchmark.

### The Obsidian question

Obsidian graph **stays**. It's CC's thinking environment and provides structural metadata (wiki-links) that a vector index can't replicate. The ingest pipeline parses `[[wiki-links]]` into a `link_graph` column so retrieval can expand: "pull this chunk AND the chunks it links to, one hop out." That's hybrid graph+vector retrieval, and it's strictly better than either alone.

### Migration phases

1. **Week 1** — migration 014: add `pgvector` + `memory_chunks` table. Ship `memory_chunker.py` + `memory_ingest.py`. One-time backfill ingest of current tree.
2. **Week 2** — Ship `memory_query.py`. Add `--use-rag` flag to `scripts/core/context_builder.py`. Dual-run: retrieve via RAG, also load old files, diff the outputs, log deltas.
3. **Week 3** — Flip default. CAPABILITIES and AGENTS files move to "retrieved-only" — remove from CLAUDE.md `@imports`.
4. **Week 4** — Measure: token cost per session before/after, answer quality via Validator subagent. Keep dual-run as fallback for one month.

---

## Q2 — Event-Driven Messaging (kill the JSON pulse race condition)

### Decision: **Postgres `LISTEN`/`NOTIFY` + `agent_events` table. No Redis. No MQTT.**

Every argument for Redis dissolves when you already run Postgres. Postgres gives us:
- **Durability** — an offline Atlas still sees the event on reconnect (Redis Pub/Sub is fire-and-forget; offline = missed).
- **Atomicity** — the event insert and the state update can be one transaction.
- **Zero new infrastructure** — Supabase is already the spine.
- **Free audit log** — `agent_events` IS the history.

Redis Pub/Sub wins only on raw throughput (millions/sec). We will not hit that for years. If we ever do, we bolt Redis Streams in behind the same API — the agents never know.

### The `agent_events` table already exists (per migration 002)

Verify and extend:

```sql
alter table agent_events
  add column if not exists source_agent    text not null default 'unknown',
  add column if not exists target_agent    text,                    -- null = broadcast
  add column if not exists correlation_id  uuid not null default gen_random_uuid(),
  add column if not exists idempotency_key text unique,             -- replay protection
  add column if not exists processed_at    timestamptz,
  add column if not exists processed_by    text,
  add column if not exists status          text not null default 'pending'
    check (status in ('pending','processing','done','failed','dead'));

create index if not exists idx_events_target_pending
  on agent_events (target_agent, status) where status = 'pending';

create or replace function notify_agent_event() returns trigger as $$
begin
  perform pg_notify(
    coalesce(new.target_agent, 'broadcast'),
    json_build_object('id', new.id, 'type', new.event_type)::text
  );
  return new;
end;
$$ language plpgsql;

drop trigger if exists trg_notify_agent_event on agent_events;
create trigger trg_notify_agent_event
  after insert on agent_events
  for each row execute function notify_agent_event();
```

### Standard event envelope

```json
{
  "v": 1,
  "id": "01HY...",
  "source": "bravo",
  "target": "maven",
  "type": "lead.classified",
  "correlation_id": "abc-123",
  "idempotency_key": "lead-uuid:classified",
  "payload": { "lead_id": "...", "intent": "hot" },
  "timestamp": "2026-04-22T12:00:00Z"
}
```

### Publisher pattern (replaces all `*_pulse.json` writes)

```python
# scripts/core/event_bus.py
def publish(event_type: str, payload: dict, target: str | None = None,
            source: str = "bravo", correlation_id: str | None = None) -> str:
    """Durable pub/sub. Returns event id. Idempotent on idempotency_key collisions."""
```

Atlas, Maven, Aura each import this and call `publish(...)` instead of writing JSON.

### Subscriber pattern (long-lived daemons)

```python
# scripts/event_subscriber.py
async def subscribe(agent_name: str, handlers: dict[str, Callable]):
    """LISTEN on own channel + 'broadcast'. Claim pending rows via SELECT ... FOR UPDATE SKIP LOCKED.
       Process handler. Mark done. Retry with exponential backoff on failure. Move to 'dead' after N."""
```

`FOR UPDATE SKIP LOCKED` is the pattern that makes this concurrent-safe across multiple subscriber workers of the same agent — standard Postgres job-queue idiom.

### What this kills

- `data/pulse/cfo_pulse.json` — gone
- `data/pulse/cmo_pulse.json` — gone
- All file-watch polling for cross-agent state — gone
- All "did Bravo write this yet?" race conditions — gone

### Failure semantics (the honest caveats)

- **Handler crash mid-processing:** row stays `processing`, reclaimed after visibility-timeout (30s default).
- **Poison message:** after 3 retries → `status=dead`, alert Telegram, human decides.
- **Supabase down:** publisher falls back to writing a JSONL file at `tmp/events_offline.jsonl`, drained to DB on reconnect by `scripts/event_drain.py`. Durability preserved even during outages.

### Migration phases

1. **Day 1** — migration 015: columns + trigger above. Ship `event_bus.publish()`.
2. **Day 2-3** — Update `autonomous_agent.py`, Atlas, Maven to dual-write (JSON file + event publish). Zero breaking change.
3. **Week 2** — Ship subscriber harness. Atlas + Maven daemons consume events. JSON files become read-only legacy mirror.
4. **Week 3** — Delete pulse JSON writers. Archive the files. One PR.

---

## Q3 — Headless Autonomy (Dockerized VPS deployment)

### Decision: **Hetzner CX32 VPS (Falkenstein, EU). Docker Compose. Tailscale for access. Deploy via GitHub Actions → SSH.**

Hostinger is fine; Hetzner is half the price at equal spec (€6.90/mo for 4 vCPU / 8 GB RAM / 80 GB SSD as of 2026). Frankfurt region gets us GDPR-friendly hosting — matters for the Q4 client-security answer. If CC prefers a Canadian company, **OVHcloud Beauharnois** is the equivalent pick.

Claude API calls still originate from the VPS — we do not self-host an LLM. Model quality > hosting ideology.

### The Docker Compose stack

```yaml
# docker-compose.yml (canonical, lives in infra/)
services:

  bravo-core:              # the reasoning loop daemon
    build: ./bravo
    command: python -m scripts.autonomous_agent daemon
    env_file: .env.agents
    restart: unless-stopped
    depends_on: [postgres-pooler]
    healthcheck:
      test: ["CMD", "python", "-m", "scripts.self_audit", "--health-only"]
      interval: 60s
      timeout: 10s
      retries: 3

  bravo-scheduler:         # cron runner — replaces PM2 bravo-scheduler
    build: ./bravo
    command: python scheduler.py
    env_file: .env.agents
    restart: unless-stopped

  bravo-webhook:           # FastAPI — receives N8N + Telegram + Stripe webhooks
    build: ./bravo
    command: uvicorn scripts.webhook_listener:app --host 0.0.0.0 --port 8000
    env_file: .env.agents
    expose: ["8000"]
    restart: unless-stopped

  bravo-inbox:             # Gmail poller — replaces local email_engine check-inbox
    build: ./bravo
    command: python scripts/integrations/email_engine.py check-inbox --daemon --interval 300
    env_file: .env.agents
    restart: unless-stopped

  caddy:                   # reverse proxy with automatic Let's Encrypt TLS
    image: caddy:2-alpine
    ports: ["80:80", "443:443"]
    volumes:
      - ./infra/Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
    restart: unless-stopped

  postgres-pooler:         # PgBouncer — keeps Supabase connections tight across daemons
    image: edoburu/pgbouncer:latest
    env_file: .env.agents
    restart: unless-stopped

volumes:
  caddy_data:
```

### VPS hardening checklist (non-negotiable before first deploy)

1. Disable root SSH, password auth. Key-only. `fail2ban` on port 22.
2. UFW firewall: allow 80/443 public, 22 via **Tailscale only**. Public SSH closed.
3. Automatic security updates: `unattended-upgrades`.
4. Docker daemon socket NOT exposed over TCP.
5. Full disk encryption (LUKS) at provision time — Hetzner supports it.
6. Secrets: `.env.agents` injected via `docker-compose.yml` `env_file:`, file mode 600, owned by a non-root user.
7. Log shipping: container stdout → journald → ship to Supabase `agent_logs` table via `scripts/log_shipper.py`.

### Deployment path

- **GitHub Actions** workflow on push to `main` → run tests → SSH to VPS → `git pull && docker compose up -d --build` → smoke test → post to Telegram `#deploys`.
- **Rollback:** `docker compose up -d --build` with previous git SHA; 30 seconds.
- **Observability:** lightweight Uptime Kuma on a sibling VPS or a $5 DigitalOcean droplet — checks the webhook endpoint + the autonomous_agent health endpoint every 60s. Pages Telegram on failure.

### What changes for CC day-to-day

| Before V6 | After V6 |
|---|---|
| Open laptop → `cd` into repo → `python autonomous_agent.py daemon` | Agent is already running |
| Close laptop → agent sleeps | Agent runs 24/7 |
| Scheduler cron dies when Mac sleeps | Scheduler in container — never sleeps |
| Email inbox polled only when local script runs | Polled every 5 min by `bravo-inbox` service |
| Webhooks (N8N, Stripe) point at local tunnel / miss events | Webhooks point at `https://ops.oasisai.work` directly |

Local machine becomes **dev-only**: CC edits code, runs tests, pushes. Production lives on the VPS.

### Migration phases

1. **Week 1** — Write `Dockerfile` for `scripts/` directory (Python 3.12-slim base). Verify local `docker compose up` runs the full stack on CC's Windows box.
2. **Week 2** — Provision Hetzner. Harden. Tailscale enroll. Deploy stack. Run in shadow mode: receives webhooks but does not send outbound.
3. **Week 3** — Point DNS `ops.oasisai.work` at VPS. Cutover: outbound traffic moves to VPS. Local scheduler stopped. Telegram bot re-homed.
4. **Week 4** — Add Uptime Kuma, log shipping, Grafana dashboards for `send_gateway` stats + `agent_events` throughput.

Total cost: **~€8/mo VPS + €0 Tailscale (free tier) + €0 Caddy + existing Supabase.** Call it **$10 USD/mo** to host the entire C-suite headlessly.

---

## Q4 — Client Data Security (the high-ticket client answer)

### The sales answer (what CC says verbatim)

> "Your data never enters any LLM training pipeline — that's contractual with Anthropic's API. It lives in a dedicated Postgres database with row-level isolation, hosted on a hardened EU VPS under our name, TLS in transit and AES-256 at rest. Every agent action is logged to an immutable audit trail you can inspect. We'll sign a DPA. For highly regulated verticals we offer a fully self-hosted LLM deployment — your data and the model both live on infrastructure you control."

That's one paragraph. It lands. Now the architecture that makes it true.

### Defense-in-depth layers

| Layer | V6.0 control | What a client can verify |
|---|---|---|
| **1. LLM training leakage** | Anthropic API — zero training on customer data by default. For HIPAA/SOC2 clients: upgrade to **Claude for Work** ZDR (zero data retention) endpoint. | Point client at [Anthropic's data usage policy](https://anthropic.com/legal/privacy). Include in DPA. |
| **2. Prompt injection & data exfiltration** | Input sanitizer at gateway: strips prompt-injection patterns, enforces max-token caps on client-authored input. Output scanner: regex + Claude Haiku classifier flags any response containing another client's name, API key shape, or PII leakage before it leaves the server. | Show the sanitizer + scanner code. Offer pen-test results. |
| **3. Tenant isolation** | Per-client Supabase **schema** with RLS enforced by service-role JWT claims. `tenant_id` on every row. Cross-tenant query = 0 rows, guaranteed by policy. For large clients: dedicated Supabase project. | Live demo: log in as Client A, try to query Client B's data → 0 rows returned. |
| **4. Transport security** | TLS 1.3 everywhere. Caddy auto-renews Let's Encrypt certs. Internal service-to-service over Tailscale WireGuard. | SSL Labs A+ on all endpoints. Tailscale ACL export. |
| **5. At-rest encryption** | LUKS on VPS disk. Supabase pgcrypto on sensitive columns (SSN, financial data). Backups encrypted with client-specific KMS key. | Show `cryptsetup status`. Show pgcrypto column definitions. |
| **6. Secret management** | Secrets never in Git. `.env.agents` mode 600 on disk. Production uses **Doppler** (free tier, $6/mo paid) or **Infisical** self-hosted for per-client secret scoping. Quarterly rotation with audit log. | Doppler audit log export. `git log -p` on repo showing zero secrets. |
| **7. PII handling** | `scripts/pii_scrubber.py` runs before any client data enters a Claude API call. Strips/tokenizes names, emails, phones, SSN patterns using Microsoft Presidio. Original PII never leaves the tenant's DB. | Show unit tests with sample PII in, tokens out. |
| **8. Audit trail** | Every agent action → `agent_traces` row with `tenant_id`, `actor`, `tool`, `input_hash`, `output_hash`, `timestamp`. Immutable (Postgres RLS forbids UPDATE/DELETE on `agent_traces`). 7-year retention for financial-advisory clients. | Live audit query demo. Export to CSV for client's auditor. |
| **9. Access control** | VPS: SSH key + Tailscale + MFA. Supabase: service-role key only in VPS env. CC's dashboard: Vercel SSO (already on — caught correctly in STATE.md). Per-client dashboard: magic-link email auth. | Demonstrate locked-out access attempts in logs. |
| **10. Incident response** | Documented runbook: detect → isolate → notify client within 72 hours (GDPR) / per DPA. Automated: `scripts/incident_response.py` kills all outbound sends for tenant, rotates tenant secrets, exports forensic snapshot. | Share the runbook. Tabletop exercise with client. |
| **11. Self-hosted LLM option** | For health / finance / legal clients: Ollama on a dedicated GPU VPS (Hetzner GEX44, €189/mo) running Llama 3.3 70B or Qwen 2.5 72B. Private endpoint, no external API call. Quality is 85-90% of Claude Sonnet 4.6 for most agency tasks. | Offer side-by-side evaluation run. Show network diagram: zero egress from tenant boundary. |
| **12. Compliance posture** | Start: documented Trust Center page on oasisai.work listing all of the above. Offer DPA template (GDPR + PIPEDA). 12-month roadmap: SOC 2 Type I via Vanta or Drata (~$15k/yr — only if a $50k+/yr client requires it). | Trust Center URL. DPA PDF. Vanta dashboard link when applicable. |

### Client data flow (V6.0 end-to-end)

```
[Client system] ──TLS──> [VPS Caddy]
                             │
                             ▼
                     [bravo-webhook] ──validates signature──┐
                             │                              │
                             ▼                              │
                    [PII scrubber] ──────────────┐          │
                             │                    ▼          │
                             ▼            [Claude API — ZDR]│
                       [tenant DB]               │           │
                       (RLS-isolated)            ▼           │
                             │            [response scrubber]│
                             │                    │          │
                             └────audit_trace─────┴──────────┘
                                      │
                                      ▼
                              [agent_traces — immutable]
```

### Non-negotiable rules (write these into CLAUDE.md v6)

1. No client production data on CC's laptop. Ever. If we need it for debugging, we sanitize first.
2. No multi-tenant table without `tenant_id` + RLS policy.
3. No outbound LLM call without passing through `pii_scrubber.py` for regulated tenants.
4. No secret in the repo. Pre-commit hook blocks.
5. Every new client gets: a schema, a service key scoped to that schema, a DPA signature, and a row in `clients_registry` before the first agent action runs on their behalf.

### Migration phases

1. **Week 1-2** — Trust Center page on oasisai.work. DPA template drafted (template from iubenda or Termly).
2. **Week 3** — `scripts/pii_scrubber.py` ships + tested. Wired into `send_gateway.py` for regulated-tenant rows.
3. **Week 4** — Per-tenant schema migration pattern documented. First new client onboarded on V6.0 pattern.
4. **Month 3+** — Evaluate self-hosted LLM deployment for first health/finance client. Only build when a real deal demands it.

---

## Sequencing — which of the four first?

Not all four at once. Prioritize by revenue leverage × risk reduction:

1. **Q2 Event bus** — **Week 1**. Fastest, smallest surface, unlocks everything else. Kills race conditions today.
2. **Q3 Headless VPS** — **Weeks 2-3**. True 24/7 autonomy is the single biggest quality-of-life and client-facing credibility jump. Directly enables Q4.
3. **Q1 RAG migration** — **Weeks 3-4**, overlaps with Q3. Cuts Anthropic API bill ~60% — pays for itself in the first month at current usage.
4. **Q4 Client security hardening** — **Weeks 3-5**, overlaps all. Mostly documentation + Trust Center. Wire PII scrubber and RLS patterns when the first $1000+/mo OASIS client demands it. Don't over-build before demand.

**Full V6.0 target: operational by end of May 2026** — the same week CC should hit the $5k MRR north star. Infrastructure and revenue milestones aligned deliberately.

---

## Open questions for CC

1. **VPS region** — Hetzner Germany (cheapest, GDPR-ready) or OVH Canada (data sovereignty)? My recommendation: **Hetzner Germany** unless a Canadian client contractually requires in-country hosting.
2. **Dedicated GPU VPS for self-hosted LLM** — build speculatively, or only when first health/finance client signs? My recommendation: **on-demand only**. €190/mo is a lot of burn for a feature no one has paid for yet.
3. **SOC 2** — timeline and budget. My recommendation: defer until a single deal north of $30k/yr makes it ROI-positive. Likely end of 2026 at current pace.
4. **Obsidian vault** — does CC keep editing MD files locally and sync to the VPS, or flip to editing via the VPS? My recommendation: **keep local + sync**. Obsidian is a thinking tool; decoupling it from the agent runtime is a feature, not a bug.

---

## Obsidian Links
- [[brain/STATE]] | [[brain/USER]] | [[brain/ORCHESTRATION]]
- [[brain/CAPABILITIES]] | [[brain/CHANGELOG]]
- [[memory/SESSION_LOG]] | [[memory/DECISIONS]]
