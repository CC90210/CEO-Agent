# Lesson 4: Scaling Secure Agents for Clients

> **Course:** Secure OpenClaw Setup & Configuration
> **XP Reward: +400 XP** | Running Total: 1,300 XP
> **Level: Integrator (L2)** — Complete. You now run secure agents at the agency level.

---

## Multi-Tenant Security: The Foundation of Client Work

When you run one agent for yourself, security mistakes are painful. When you run agents for multiple clients, a security mistake in one client's system can cascade into another's. Multi-tenancy — isolating client data so no client can ever see another's — is the architectural requirement that makes agency AI work viable.

### The Tenant Isolation Model

Every client gets their own isolated environment:

```
Your Agency Infrastructure
  ├── Client A
  │   ├── Supabase project (dedicated)  ← Separate database, separate keys
  │   ├── API keys (scoped to Client A)
  │   ├── n8n workspace (separate)
  │   └── Stripe account (Client A's)
  │
  ├── Client B
  │   ├── Supabase project (dedicated)  ← Completely separate from Client A
  │   ├── API keys (scoped to Client B)
  │   ├── n8n workspace (separate)
  │   └── Stripe account (Client B's)
  │
  └── Your Agency
      ├── Business-Empire-Agent (your intelligence layer)
      ├── Your own Supabase project
      └── Your restricted keys for managing client deployments
```

**Never put two clients in the same database.** Even with perfect RLS, shared infrastructure creates cross-contamination risks through configuration errors, shared connection pools, and shared audit logs.

### Separate API Keys Per Client

Each client deployment gets its own set of keys:

| Key | Client A | Client B | Your Agency |
|-----|----------|----------|-------------|
| Supabase anon | `eyJh...clientA` | `eyJh...clientB` | `eyJh...agency` |
| Stripe restricted | `rk_live_clientA...` | `rk_live_clientB...` | `rk_live_agency...` |
| Anthropic | `sk-ant-clientA...` | `sk-ant-clientB...` | `sk-ant-agency...` |

When Client A's project has a security incident, you rotate Client A's keys. Client B is unaffected.

---

## The Agency Security Promise

Before you onboard a client, be explicit about what you're committing to. This is both a sales tool and a contractual obligation — don't promise what you can't deliver.

### What You Guarantee

```
OASIS AI Security Standards

✓ Dedicated database per client — your data is never shared infrastructure
✓ Encrypted credentials — all API keys stored in environment variables, never in code
✓ Row Level Security — database policies ensure users only access their own data
✓ Restricted API keys — agents have minimum necessary permissions
✓ Key rotation — credentials rotated on a fixed schedule
✓ Audit logging — all agent actions logged with timestamps
✓ Incident response — 24-hour containment SLA for security issues
✓ No third-party data sharing — your business data is not used to train AI models

✗ We do NOT guarantee against all possible breaches (no one can)
✗ We do NOT control security of your own third-party integrations
✗ We do NOT access your data outside of agreed automation workflows
```

Being explicit about both guarantees and limitations builds more trust than making promises you can't keep.

---

## Compliance Basics: GDPR for Agency Operators

If any of your clients serve customers in the European Union, GDPR applies — even if your agency is based in Canada or the US.

### The Three Things You Must Get Right

**1. Data minimization:** Only collect and store data you actually need.

```
Bad: Storing full conversation history indefinitely
Good: Storing conversation summaries with 90-day auto-expiry
```

**2. Right to deletion:** When a user asks to delete their data, you must be able to do it completely and quickly.

```sql
-- Make deletion fast and complete
CREATE OR REPLACE FUNCTION delete_user_data(target_user_id UUID)
RETURNS void AS $$
BEGIN
  DELETE FROM user_conversations WHERE user_id = target_user_id;
  DELETE FROM user_preferences WHERE user_id = target_user_id;
  DELETE FROM agent_traces WHERE metadata->>'user_id' = target_user_id::text;
  -- Add every table that stores user data
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
```

**3. Data processing agreements:** If you process client data on behalf of a client who serves EU customers, you need a Data Processing Agreement (DPA) in place.

💡 **PRO TIP:** Keep it simple — use a standard DPA template from a legal service (Termly, Iubenda, or a lawyer). Have it ready to send during client onboarding. Most small business clients don't know they need this until you hand it to them, which demonstrates professionalism.

### Data Retention Policy

Define retention periods for every category of data you store:

| Data Type | Retention | Reason |
|-----------|-----------|--------|
| Agent session logs | 90 days | Debugging + compliance |
| Client records | Duration of contract + 30 days | Contract terms |
| Conversation history | 30 days | Performance optimization |
| Payment records | 7 years | Financial compliance |
| Security audit logs | 1 year | Incident investigation |

---

## Client Onboarding Security Checklist

Use this when setting up a new client's agent infrastructure.

```
PRE-ONBOARDING
  [ ] Create dedicated Supabase project for client
  [ ] Create restricted Stripe API key scoped to client's use case
  [ ] Generate Anthropic/OpenAI key (or confirm client uses their own)
  [ ] Set up client's n8n workspace or folder

INFRASTRUCTURE SETUP
  [ ] Configure .env.agents with client's credentials
  [ ] Enable RLS on every table in client's database
  [ ] Write RLS policies for all access patterns
  [ ] Create wrapper scripts for client's MCP connections
  [ ] Verify wrapper scripts work: run one test operation per integration

ACCESS SCOPING
  [ ] Define access control matrix (which agent accesses which service)
  [ ] Confirm service role key is only in server-side scripts
  [ ] Confirm anon key is only in client-facing code
  [ ] Test RLS: verify user A cannot read user B's records

DOCUMENTATION
  [ ] Create credentials-rotation-log.md for client project (gitignored)
  [ ] Set calendar reminders for 90-day and 30-day rotations
  [ ] Document the agent's capabilities and permissions in plain language
  [ ] Share security standards document with client

POST-ONBOARDING VERIFICATION
  [ ] Run pre-deployment security checklist from Lesson 3
  [ ] Verify audit logging is working (create a test trace entry)
  [ ] Send client the "what your agent can and cannot access" summary
```

---

## Incident Response Plan

A security incident is not a question of if — it's when. The agencies that handle incidents well are the ones who have a plan before the incident happens.

### Incident Severity Levels

| Level | Description | Response Time |
|-------|-------------|--------------|
| **P0 — Critical** | Exposed secret in public repo, active unauthorized access, data breach | Immediate — within 1 hour |
| **P1 — High** | Suspected unauthorized access, failed rotation, key expiry causing outages | Same day — within 4 hours |
| **P2 — Medium** | Security configuration drift, failed audit, unusual activity in logs | Within 24 hours |
| **P3 — Low** | Upcoming rotation, minor policy gaps, non-critical findings | Within 1 week |

### The P0 Response Sequence

```
P0 INCIDENT: Secret Exposed

Step 1 — DETECT (0-5 min)
  Confirm what was exposed
  Determine how long it was exposed
  Identify what the key could access

Step 2 — CONTAIN (5-30 min)
  Revoke the exposed key IMMEDIATELY
  If Supabase key: revoke in dashboard
  If Stripe key: revoke in Stripe dashboard
  If GitHub repo: make private, then address
  Document: time of detection, time of revocation

Step 3 — ROTATE (30-60 min)
  Generate new credentials
  Update .env.agents
  Deploy updated environment variables to Vercel/production
  Verify system is operational with new credentials

Step 4 — NOTIFY (within 2 hours)
  Notify affected client: what happened, what was exposed, what was done
  Be direct: "At [time], we detected that [key type] was exposed in [location].
  We revoked the key at [time] and rotated to a new credential at [time].
  No unauthorized access was detected in the [X]-hour exposure window.
  Here is what we are doing to prevent this from happening again."

Step 5 — POST-MORTEM (within 48 hours)
  Write a brief post-mortem
  Root cause: how did this happen?
  Contributing factors: what made this possible?
  Prevention: what process change prevents recurrence?
  Add to memory/MISTAKES.md
```

💀 **COMMON MISTAKE:** Delaying client notification while you investigate to avoid looking bad. Clients react far worse to late disclosure than to prompt, honest communication. Notify as soon as the incident is contained, even if you don't have all the answers yet.

---

## Security as a Selling Point

Most agency operators treat security as a cost center — something they have to do, not something they get to promote. That's a competitive mistake.

### The Security Pitch

Your prospective clients are currently worried about:
- "What if this AI agent reads my client data?"
- "What happens if you get hacked?"
- "Can you guarantee our data stays private?"

Most of your competitors cannot answer these questions. You can.

**During a sales call:**

> "One thing we take seriously is how your data is handled. Every client gets a dedicated database — your data is never on shared infrastructure with another client. We use restricted API keys with the exact permissions your automation needs, nothing more. And we maintain a rotation schedule for every credential so nothing sits long enough to become a liability. We can walk you through our security standards document if you'd like."

This converts objections into proof points and positions you as the professional in the room.

### Security in Your Proposals

Add a "Security & Data Handling" section to every proposal:

```
Security & Data Handling

Infrastructure: Dedicated Supabase database — your data is not shared
Credentials: API keys stored in encrypted environment variables, never in code
Access: Agent permissions scoped to minimum required for each automation
Rotation: All credentials on 30-90 day rotation schedule
Logging: Complete audit trail of agent actions
Incidents: 24-hour response SLA with immediate containment and notification
Compliance: GDPR-compliant data minimization and deletion procedures
```

---

## Automated Security Monitoring

Don't rely on manual checks. Build n8n workflows that catch issues automatically.

### Monitor 1: Daily Key Expiry Check

```
Schedule: Every day at 9am
Action:
  1. Read credentials-rotation-log.md
  2. Find any credentials with next_rotation_date within 14 days
  3. If found: send Telegram message "⚠️ Key rotation due in X days: [KEY_NAME]"
```

### Monitor 2: Supabase RLS Status Check

```
Schedule: Weekly
Action:
  1. Query Supabase management API for all tables
  2. Filter for tables with RLS disabled
  3. If any found: send alert "🚨 RLS disabled on tables: [table_names]"
```

### Monitor 3: Unusual Activity Detection

```
Schedule: Every 4 hours
Action:
  1. Query agent_traces table for last 4 hours
  2. Count operations by category
  3. If any category > 3x the 7-day average: send alert
```

---

## 🔥 EXERCISE: Client Security Onboarding Template + Incident Response Playbook

**Part 1: Client Security Onboarding Template**

Create a document called `docs/client-security-onboarding.md` in your agency project. Include:

1. The complete client onboarding security checklist (from this lesson, personalized for your stack)
2. The security standards document you send to clients after onboarding
3. The "what your agent can and cannot access" summary template

**Part 2: Incident Response Playbook**

Create `docs/incident-response-playbook.md`. Include:

1. Severity level definitions for your agency
2. The full P0 response sequence with time targets
3. A client notification email template for each severity level
4. A post-mortem template

**Deliverable:** Two completed documents ready to use with your first or next client. These should be specific to your stack (Supabase + Stripe + n8n + Claude Code), not generic security boilerplate.

---

## 🧠 KEY TAKEAWAY

Security at agency scale means three things: total tenant isolation (dedicated infrastructure per client), a clear security promise you can actually deliver on, and an incident response plan that lets you act in minutes instead of hours when something goes wrong. Clients don't expect perfection — they expect transparency, speed, and professionalism when problems arise. The agencies that build security into their delivery standard — not as an afterthought — are the ones that keep clients for years and justify premium pricing.

---

**Course Complete: Secure OpenClaw Setup & Configuration**

You've covered the full security stack: architecture principles, key rotation, production hardening, and client-scale deployment. Apply these standards to every project from this point forward.
