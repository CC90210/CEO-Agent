---
name: funnel-management
description: Track leads through conversion funnels, measure stage-to-stage conversion rates, and identify where prospects are dropping off using lead_engine.py and direct Supabase queries.
triggers: [funnel, conversion, drop-off, stage, pipeline metrics, awareness, consideration]
tier: standard
dependencies: [lead-management, email-marketing]
---

# Funnel Management — Conversion Tracking

## Overview

A funnel is a named path a lead takes from first touch to close. `lead_engine.py` assigns leads to funnels and tracks their stage. Direct Supabase queries via `supabase_tool.py` handle aggregate reporting. The goal is knowing exactly where prospects stall — not guessing.

---

## Funnel Stages

These map to OASIS AI's actual buyer journey. Every stage has a single exit condition — either they advance or they stall.

| Stage | Definition | Exit Condition |
|-------|-----------|----------------|
| `awareness` | Saw content, ad, or DM — no reply yet | They engage with any message |
| `interest` | Replied or clicked — signal of curiosity | They ask a question or book a call |
| `consideration` | Actively evaluating — asking pricing, scope questions | Proposal sent |
| `intent` | Proposal reviewed, asking for changes or timeline | Negotiation begins |
| `evaluation` | Comparing options, stalling on decision | They confirm or go silent |
| `purchase` | Signed and paying | Revenue logged in revenue_engine |

---

## Tool Routing

### Assigning a Lead to a Funnel

```
python scripts/lead_engine.py funnel <lead_id> <funnel_slug> --stage awareness
```

Example:
```
python scripts/lead_engine.py funnel abc-123 oasis-cold-outreach --stage awareness
```

### Updating Funnel Stage

```
python scripts/lead_engine.py funnel <lead_id> oasis-cold-outreach --stage consideration
```

### Pipeline Overview (All Leads by Status)

```
python scripts/lead_engine.py pipeline
```

This shows counts per pipeline status. For funnel-specific stage counts, query Supabase directly.

### Funnel Stage Counts (Supabase Direct Query)

```
python scripts/supabase_tool.py query \
  "SELECT funnel_stage, COUNT(*) FROM lead_funnels WHERE funnel_slug = 'oasis-cold-outreach' GROUP BY funnel_stage ORDER BY funnel_stage" \
  --project bravo
```

### Full Lead List in a Funnel

```
python scripts/supabase_tool.py query \
  "SELECT l.name, l.email, l.score, lf.funnel_stage, lf.entered_at FROM lead_funnels lf JOIN leads l ON l.id = lf.lead_id WHERE lf.funnel_slug = 'oasis-cold-outreach' ORDER BY lf.entered_at DESC" \
  --project bravo
```

---

## Funnel Metrics

Track these numbers monthly. Improvement in any single conversion rate compounds into meaningful pipeline growth.

| Metric | What It Measures | How to Calculate |
|--------|----------------|------------------|
| Entry rate | New leads added per week | COUNT where status = `new`, last 7 days |
| Awareness → Interest | Cold outreach response rate | Leads at `interest` / Leads at `awareness` |
| Interest → Consideration | Qualification rate | Leads at `consideration` / Leads at `interest` |
| Consideration → Intent | Proposal acceptance rate | Leads at `intent` / Leads at `consideration` |
| Intent → Purchase | Close rate | Leads at `purchase` / Leads at `intent` |
| Overall conversion | End-to-end | Leads at `purchase` / Total leads entered funnel |
| Average days to close | Sales cycle length | AVG(purchase_date - created_at) for won leads |

A 10% cold-to-interest rate is industry standard. Below 5% means the opening message needs rewriting. Above 20% means the targeting is excellent.

---

## Drop-Off Analysis

When a stage has a conversion rate below 20% (except awareness), investigate before sending more leads in.

Run this query to find leads stuck in a stage for 7+ days:

```
python scripts/supabase_tool.py query \
  "SELECT l.name, l.email, lf.funnel_stage, lf.entered_at FROM lead_funnels lf JOIN leads l ON l.id = lf.lead_id WHERE lf.funnel_slug = 'oasis-cold-outreach' AND lf.funnel_stage = 'consideration' AND lf.entered_at < NOW() - INTERVAL '7 days'" \
  --project bravo
```

Leads stalled at `consideration` for 7+ days without a proposal: send the proposal today or move to `lost`.
Leads stalled at `intent` for 5+ days: follow up directly — not with email, with a phone call or DM.

---

## Integration Points

- **lead_engine.py** — source of lead records; use `funnel` subcommand for all stage assignments
- **email_engine.py** — nurture sequences are the primary mechanism for moving leads through `awareness` → `interest`
- **content_engine.py** — top-of-funnel content (posts, reels) drives new leads into `awareness`
- **booking_engine.py** — the `interest` → `consideration` transition often happens on a discovery call; book it then
- **revenue_engine.py** — `purchase` stage exits are logged manually as revenue events

## Obsidian Links
- [[skills/INDEX]] | [[brain/CAPABILITIES]]
