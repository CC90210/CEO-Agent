# Lesson 2: API Key Rotation & Access Controls

> **Course:** Secure OpenClaw Setup & Configuration
> **XP Reward: +300 XP** | Running Total: 550 XP
> **Level: Integrator (L2)** — You're managing real credentials now. Treat them like cash.

---

## API Key Types: Not All Keys Are Equal

Before you can manage keys properly, you need to understand what you're managing. Handing an agent a full admin key is like giving a contractor a master key to every floor of your building — including the server room and the executive offices. You give contractors exactly the key they need for the job.

### The Four Key Categories

| Type | Access Level | Use Case |
|------|-------------|----------|
| **Public (anon)** | Read-only, governed by security policies | Client-facing apps, frontend code |
| **Private (secret)** | Full access, bypasses all security policies | Server-side only, never in frontend |
| **Restricted (scoped)** | Custom permissions, defined by you | Agents, automations — this is what you want |
| **Management (admin)** | Platform-level config, token refresh | Provisioning infrastructure, key rotation |

The goal for every agent and automation you build: **use restricted keys with the minimum scope required.**

---

## Supabase Keys: A Case Study in Getting It Right

Supabase ships with two keys that look similar but behave very differently. Getting this wrong exposes your entire database.

### The Anon Key

```
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...  (starts with eyJ)
```

- **Safe for:** Frontend apps, public-facing code, mobile apps
- **How it works:** Respects all Row Level Security (RLS) policies you've defined
- **What it can do:** Only what your RLS policies explicitly allow — nothing more
- **What it cannot do:** Read rows the current user doesn't own, bypass auth, access other users' data

The anon key is designed to be exposed. It appears in Next.js environment variables prefixed with `NEXT_PUBLIC_`, which means it ships to the browser. That's fine — as long as your RLS policies are correctly configured.

### The Service Role Key

```
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...  (also starts with eyJ, different token)
```

- **Safe for:** Server-side only — API routes, server actions, trusted backend scripts
- **How it works:** **Bypasses all RLS policies completely**
- **What it can do:** Read and write every row in every table, regardless of ownership
- **What it cannot do:** Be used safely in frontend code — ever

💀 **COMMON MISTAKE:** Using the service role key in a Next.js component or anywhere prefixed with `NEXT_PUBLIC_`. This exposes your entire database to any user who opens browser devtools. This mistake is irreversible without a full key rotation.

### The Management API Token

```
sbp_7430...
```

- **Purpose:** Platform management — creating projects, configuring settings, generating types
- **Not for:** Runtime database operations
- **Expiry:** 30 days — must be rotated on schedule

### RLS: The Lock That Makes the Anon Key Safe

Row Level Security is a PostgreSQL feature that Supabase uses to enforce access at the database level — not the application level. Even if your API code has a bug, RLS prevents unauthorized data access.

```sql
-- Enable RLS on a table (MANDATORY for every table)
ALTER TABLE client_records ENABLE ROW LEVEL SECURITY;

-- Policy: users can only see their own records
CREATE POLICY "Users see own records"
ON client_records
FOR SELECT
USING (auth.uid() = user_id);

-- Policy: users can only insert records for themselves
CREATE POLICY "Users insert own records"
ON client_records
FOR INSERT
WITH CHECK (auth.uid() = user_id);

-- Policy: users can only update their own records
CREATE POLICY "Users update own records"
ON client_records
FOR UPDATE
USING (auth.uid() = user_id);
```

⚡ **QUICK WIN:** Go to your Supabase dashboard right now. Open Table Editor. Look at the "RLS" column for every table. Any table showing "Disabled" is a live security risk — enable RLS and write policies before going to production.

---

## Stripe Keys: Use Restricted Keys for Agents

Stripe provides three key types relevant to agencies:

| Key | Prefix | Use |
|-----|--------|-----|
| Publishable | `pk_live_` | Frontend only — identifies your account |
| Secret | `sk_live_` | Server-side only — full account access |
| Restricted | `rk_live_` | Server-side only — scoped to specific permissions |

### Always Use Restricted Keys for Agents

The secret key (`sk_live_`) can do anything to your Stripe account — create charges, issue refunds, delete customers, modify subscription plans. An agent doesn't need all of that.

Create restricted keys in Stripe Dashboard → Developers → API Keys → Restricted Keys:

```
Agent: Payment Processing
  ✓ Charges: Read + Write
  ✓ Customers: Read + Write
  ✓ Payment Intents: Read + Write
  ✗ Refunds: None
  ✗ Subscriptions: None
  ✗ Plans: None

Agent: Reporting Only
  ✓ Charges: Read
  ✓ Customers: Read
  ✗ Everything else: None
```

If the payment processing agent is compromised, it cannot issue refunds or cancel subscriptions. Blast radius contained.

💡 **PRO TIP:** Name your restricted keys descriptively in Stripe: `bravo-agent-payments-prod`, `n8n-reporting-prod`. When you rotate them, you know exactly which systems to update. Generic names like `key1` are a debugging nightmare six months later.

---

## Key Rotation Workflow

Rotating a key without breaking your system is a process. Do it in this order — skipping steps causes outages.

### Phase 1: Generate the New Key

1. Log into the provider dashboard (Stripe, Supabase, Anthropic, etc.)
2. Create a new key with identical permissions to the one you're replacing
3. Copy the new key — you won't see it again after leaving the page
4. Do NOT revoke the old key yet

### Phase 2: Update and Verify

```bash
# Update .env.agents with the new key
# OLD: STRIPE_RESTRICTED_KEY=rk_live_oldkeyABC
# NEW: STRIPE_RESTRICTED_KEY=rk_live_newkeyXYZ

# Test that the system still works
python scripts/stripe_tool.py balance
# Expected: Returns current balance without error
```

Run one real operation with the new key before revoking the old one.

### Phase 3: Propagate to All Environments

Keys often need updating in multiple places:

```
Locations to update:
  [ ] .env.agents (local development)
  [ ] Vercel environment variables (production)
  [ ] Any CI/CD secrets (GitHub Actions, etc.)
  [ ] Other developers' .env files (notify them)
  [ ] Any deployed n8n workflows that use this key
```

### Phase 4: Revoke the Old Key

Only after confirming the new key works in all environments:

1. Go back to the provider dashboard
2. Find the old key
3. Revoke/delete it
4. Verify the system still works (the new key was already confirmed, so this is just peace of mind)

### Phase 5: Log the Rotation

```markdown
# credentials-rotation-log.md (gitignored)

## STRIPE_RESTRICTED_KEY
- Rotated: 2026-03-18
- Next rotation due: 2026-06-18
- Rotated by: Conaugh McKenna

## SUPABASE_SERVICE_ROLE_KEY
- Rotated: 2026-03-01
- Next rotation due: 2026-04-01
- Rotated by: Bravo (automated)
```

---

## Wrapper Script Pattern

MCP configuration files are often shared, synced to version control, or edited by multiple people. Credentials cannot live in those files. The wrapper script pattern solves this cleanly.

### The Problem

```json
// .claude/mcp.json — BAD: credential in config file
{
  "mcpServers": {
    "supabase": {
      "command": "npx",
      "args": ["-y", "@supabase/mcp-server-supabase@latest", "--access-token", "sbp_ACTUAL_TOKEN_HERE"]
    }
  }
}
```

If this file gets committed, the token is in git history forever.

### The Solution

```json
// .claude/mcp.json — GOOD: wrapper reads credentials at runtime
{
  "mcpServers": {
    "supabase": {
      "command": "cmd",
      "args": ["/c", "scripts/supabase-mcp-wrapper.cmd"]
    }
  }
}
```

```batch
:: scripts/supabase-mcp-wrapper.cmd
@echo off
for /f "tokens=1,* delims==" %%a in ('findstr "SUPABASE_ACCESS_TOKEN" .env.agents') do set %%a=%%b
npx -y @supabase/mcp-server-supabase@latest --access-token=%SUPABASE_ACCESS_TOKEN%
```

When the Supabase token rotates, you update one line in `.env.agents`. The wrapper, the config file, and the git history stay clean.

---

## Access Control Matrix

Map every agent and service to its exact permissions. This becomes your reference document during security audits and incident response.

| Agent / Service | Supabase | Stripe | Anthropic | n8n | File System |
|----------------|----------|--------|-----------|-----|------------|
| Claude Code (Bravo) | anon key (RLS) + service role (server scripts only) | Restricted (read + write payments) | Full | Management API | Read/write project dir |
| n8n workflows | anon key (specific tables only via RLS) | Restricted (read only for reporting) | None | — | None |
| Frontend app | anon key (RLS only) | Publishable key | None | None | None |
| Telegram bridge | anon key (RLS) | None | Full | None | Read agent files |

Create this matrix for your own stack before your first client deployment.

---

## Row Level Security: Writing Real Policies

Theory is easy. Here are RLS policies you'll actually use.

### Multi-Tenant Client Isolation

If you're building a system where multiple clients store data, they must never see each other's records.

```sql
-- Table: client_automations
-- Each row belongs to a specific organization

ALTER TABLE client_automations ENABLE ROW LEVEL SECURITY;

-- Users can only see automations for their organization
CREATE POLICY "org_isolation"
ON client_automations
FOR ALL
USING (
  organization_id = (
    SELECT organization_id
    FROM user_profiles
    WHERE user_id = auth.uid()
  )
);
```

### Owner-Only Writes

```sql
-- Users can read all records but only write their own
CREATE POLICY "read_all_write_own"
ON public_profiles
FOR SELECT USING (true);  -- Anyone can read

CREATE POLICY "write_own_only"
ON public_profiles
FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "update_own_only"
ON public_profiles
FOR UPDATE USING (auth.uid() = user_id);
```

### Service Role Bypass (Intentional)

Sometimes your backend scripts legitimately need to bypass RLS — for example, a cron job that aggregates data across all users for reporting. Use the service role key only in trusted server-side code:

```typescript
// server/reporting.ts — server-side only, never in a component
import { createClient } from '@supabase/supabase-js'

const adminClient = createClient(
  process.env.SUPABASE_URL!,
  process.env.SUPABASE_SERVICE_ROLE_KEY!  // bypasses RLS — use intentionally only
)

// This query sees ALL rows, regardless of user ownership
const { data } = await adminClient.from('orders').select('*')
```

The key rule: **service role operations live only in API routes, server actions, and trusted scripts — never in components, hooks, or anything that runs in the browser.**

---

## 🔥 EXERCISE: Key Rotation Checklist + RLS Policies

**Part 1: Create your key rotation checklist.**

Open a new file called `credentials-rotation-log.md` in your project root (add it to `.gitignore`). Document every credential your project uses:

```markdown
# Credentials Rotation Log

## [SERVICE_NAME]
- Key type: [restricted/secret/management]
- Current rotation date: [DATE]
- Next rotation due: [DATE + 90 days or 30 days]
- Permissions granted: [list them]
- Locations used: [.env.agents, Vercel, CI/CD]
```

**Part 2: Write RLS policies for a sample table.**

Create a Supabase table called `agency_clients` with these columns: `id`, `user_id`, `name`, `monthly_value`, `status`, `created_at`.

Write three policies:
1. Users can only read clients they own
2. Users can only insert clients for themselves
3. Users can only update and delete their own clients

Test each policy by querying the table as both the owner and a different user. Verify you cannot read another user's clients.

**Deliverable:** Rotation log populated for all your credentials + RLS policies verified working on your sample table.

---

## 🧠 KEY TAKEAWAY

Not all keys are equal — use restricted, scoped keys for agents, never full admin keys. Supabase's anon key is safe for clients because RLS enforces access at the database level, but the service role key bypasses everything and belongs only in server-side code. Rotate every key on a fixed schedule and use wrapper scripts so credentials never touch your configuration files or git history. The access control matrix is your security contract — map every agent to its exact permissions before your first client deployment.

---

**Next:** [Lesson 3 — Production Hardening & Deployment Safety](../lesson-03-production-hardening/LESSON.md)
