"""
Proposal Generator — OASIS AI Solutions
Generates markdown proposals from templates, saved to proposals/ directory.
Follows the structure defined in skills/proposal-generation/SKILL.md.

All credentials loaded from .env.agents (never hardcoded).

Usage:
    python scripts/proposal_generator.py create --client "Name" --type retainer --tier growth
    python scripts/proposal_generator.py create --client "Name" --type project --budget 5000
    python scripts/proposal_generator.py create --client "Name" --type discovery
    python scripts/proposal_generator.py list               # List generated proposals
    python scripts/proposal_generator.py templates          # Show available templates and tiers
    python scripts/proposal_generator.py --json <command>   # JSON output for agent consumption
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROPOSALS_DIR = Path(__file__).resolve().parent.parent / "proposals"

PROPOSAL_TYPES = ["discovery", "retainer", "project"]

RETAINER_TIERS: dict[str, dict] = {
    "starter": {
        "label":    "Starter",
        "range":    "$500–$1,500/mo",
        "default":  1000,
        "includes": [
            "1–2 automation workflows built and maintained",
            "Async support (response within 1 business day)",
            "Monthly performance report",
        ],
    },
    "growth": {
        "label":    "Growth",
        "range":    "$1,500–$3,000/mo",
        "default":  2000,
        "includes": [
            "3–5 automation workflows built and maintained",
            "Bi-weekly strategy calls",
            "Priority support",
            "Full reporting dashboard (Supabase-backed)",
            "Quarterly business review",
        ],
    },
    "scale": {
        "label":    "Scale",
        "range":    "$3,000–$5,000/mo",
        "default":  4000,
        "includes": [
            "Unlimited automations",
            "Weekly strategy calls",
            "Dedicated Slack channel",
            "Custom reporting and KPI dashboards",
            "On-demand change requests (same-week turnaround)",
            "Quarterly business review + annual strategy session",
        ],
    },
}

PROJECT_TIERS: dict[str, dict] = {
    "essential": {
        "label":    "Essential",
        "range":    "$2,000–$4,000",
        "includes": [
            "Core deliverables as scoped",
            "1 round of revisions",
            "Handoff documentation",
        ],
    },
    "complete": {
        "label":    "Complete",
        "range":    "$4,000–$8,000",
        "includes": [
            "Full scope of work",
            "2 rounds of revisions",
            "30-day post-launch support",
            "Handoff documentation + training session",
        ],
    },
    "premium": {
        "label":    "Premium",
        "range":    "$8,000–$15,000",
        "includes": [
            "Full scope of work",
            "Unlimited revisions during build",
            "90-day post-launch support",
            "Handoff documentation, training session, and recorded walkthrough",
            "Priority access for 90 days",
        ],
    },
}

DISCOVERY_FEE_RANGE = "$500–$1,500"

FOLLOW_UP_CADENCE = [
    ("Day 1",  "Text/Slack",  "Confirm receipt — keep it casual"),
    ("Day 3",  "Email",       "Share a relevant result or case study (no 'following up')"),
    ("Day 7",  "Phone call",  "Direct ask — offer to answer questions live"),
    ("Day 14", "Email",       "Proposal expires reminder — offer a brief extension"),
]


# ---------------------------------------------------------------------------
# Credential loading (same pattern as all other scripts)
# ---------------------------------------------------------------------------

def load_env() -> dict[str, str]:
    """Load .env.agents from project root. Exits on missing file."""
    env_path = Path(__file__).resolve().parent.parent / ".env.agents"
    if not env_path.exists():
        print(f"ERROR: {env_path} not found", file=sys.stderr)
        sys.exit(1)

    env_vars: dict[str, str] = {}
    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                env_vars[key.strip()] = value.strip()
    return env_vars


def get_supabase_client(env_vars: dict[str, str]):
    """Return a Supabase client for the bravo project. Returns None on failure."""
    try:
        from supabase import create_client
        url = env_vars.get("BRAVO_SUPABASE_URL")
        key = env_vars.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY")
        if url and key:
            return create_client(url, key)
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Client context lookup
# ---------------------------------------------------------------------------

def lookup_client(db_client, name: str) -> dict:
    """
    Fetch lead/client context from Supabase if available.
    Returns a dict with whatever context is found; caller handles missing fields.
    """
    if db_client is None:
        return {}
    try:
        result = db_client.table("leads") \
            .select("name,company,email,phone,industry,notes") \
            .ilike("name", f"%{name}%") \
            .limit(1) \
            .execute()
        if result.data:
            return result.data[0]
    except Exception:
        pass
    return {}


# ---------------------------------------------------------------------------
# Proposal template builders
# ---------------------------------------------------------------------------

def _section_divider(title: str) -> str:
    return f"\n---\n\n## {title}\n"


def _build_retainer_proposal(client: str, tier: str, budget: int | None, context: dict, today: str, expiry: str) -> str:
    tier_key    = tier.lower()
    tier_data   = RETAINER_TIERS.get(tier_key, RETAINER_TIERS["growth"])
    monthly_fee = budget if budget else tier_data["default"]
    company     = context.get("company") or client
    industry    = context.get("industry") or "your industry"
    notes       = context.get("notes") or ""

    includes_str = "\n".join(f"- {item}" for item in tier_data["includes"])

    # Build three-tier pricing table
    tiers_table_rows = ""
    for tk, td in RETAINER_TIERS.items():
        selected = "**← Selected**" if tk == tier_key else ""
        tiers_table_rows += f"| **{td['label']}** | {td['range']} | {'; '.join(td['includes'][:2])} | {selected} |\n"

    return f"""# Retainer Proposal — {company}

**Prepared by:** Conaugh McKenna, OASIS AI Solutions
**Date:** {today}
**Valid until:** {expiry}

{_section_divider("Executive Summary")}

{company} is a business in {industry} that relies on its team's time to keep operations running. Right now, manual processes are consuming hours that should be going toward growth. This proposal outlines how OASIS AI will design, build, and maintain the automation infrastructure that frees {company}'s team to focus on what only humans can do.

{_section_divider("Proposed Solution")}

We will build a custom automation stack integrated directly into the tools {company} already uses. Every workflow we build replaces a manual process — no new software to learn, no complexity added. The result is measurable time savings and fewer errors within the first 30 days.

**What {company} gets on day one:**
- A complete audit of current manual workflows
- Priority automations identified and ranked by ROI
- First live automation deployed within 14 days of onboarding

{_section_divider("Scope of Work")}

The following reflects the **{tier_data['label']} tier** at **${monthly_fee:,}/mo**:

{includes_str}

Ongoing scope is reviewed monthly and adjusted based on priority. Any automation in the queue can be substituted for another of equal complexity with 48 hours' notice.

{_section_divider("Timeline")}

```
Month 1: Onboarding + First Wins
  - Week 1: Account access, discovery session, automation audit
  - Week 2: Priority automation #1 built and live
  - Week 3-4: Priority automations #2–3 built and live
  - Milestone: Client confirms 3 workflows operating correctly

Month 2+: Steady State
  - Monthly: New automations added per queue
  - Bi-weekly: Strategy call (Growth/Scale tiers)
  - Monthly: Performance report delivered
```

{_section_divider("Investment")}

| Tier | Monthly Investment | What's Included | |
|------|-------------------|-----------------|---|
{tiers_table_rows}

**Selected tier: {tier_data['label']} — ${monthly_fee:,}/mo**

**Payment schedule:**
- First month invoiced upfront on contract signing
- Subsequent months billed on the 1st of each month
- Net 7 payment terms

{_section_divider("Terms")}

**Revisions:** Unlimited adjustments to existing automations are included. New automation requests are added to the queue (no extra charge within tier limits).

**Intellectual property:** All custom code and systems built for {company} are owned by {company} upon payment of invoices in full.

**Confidentiality:** All shared business information is kept strictly confidential. A mutual NDA is available on request.

**Termination:** Either party may cancel with 30 days' written notice. The final 30-day period is billed at the standard monthly rate.

**Response time:** All messages replied to within 1 business day. Urgent issues (automation down) within 4 hours.

{_section_divider("About OASIS AI")}

OASIS AI Solutions helps small and mid-sized businesses automate the work that's capping their growth. Founded by Conaugh McKenna, we build automation systems for service businesses — consistently cutting manual work and creating infrastructure that scales. We keep our client roster intentionally small so every engagement gets the attention it deserves.

{_section_divider("Next Steps")}

To move forward, reply with your preferred tier or any questions, and I'll send the contract and first invoice within 24 hours. If you'd like to talk through anything live, book a 20-minute call here: [your calendar link].

This proposal is valid until **{expiry}**.

---

*Questions? Reply to this message or reach out directly: conaugh@oasisai.io*
"""


def _build_project_proposal(client: str, tier: str, budget: int | None, context: dict, today: str, expiry: str) -> str:
    tier_key  = tier.lower() if tier else "complete"
    tier_data = PROJECT_TIERS.get(tier_key, PROJECT_TIERS["complete"])
    company   = context.get("company") or client
    industry  = context.get("industry") or "your industry"

    fee_display = f"${budget:,}" if budget else tier_data["range"]

    includes_str = "\n".join(f"- {item}" for item in tier_data["includes"])

    tiers_table_rows = ""
    for tk, td in PROJECT_TIERS.items():
        selected = "**← Selected**" if tk == tier_key else ""
        tiers_table_rows += f"| **{td['label']}** | {td['range']} | {'; '.join(td['includes'][:2])} | {selected} |\n"

    return f"""# Project Proposal — {company}

**Prepared by:** Conaugh McKenna, OASIS AI Solutions
**Date:** {today}
**Valid until:** {expiry}

{_section_divider("Executive Summary")}

{company} has a specific challenge that requires a defined solution with a clear delivery date. This proposal outlines the scope, timeline, and investment for a one-time project engagement with OASIS AI Solutions. Unlike a retainer, this engagement has a defined start, defined deliverables, and a defined end — with optional ongoing support afterward.

{_section_divider("Proposed Solution")}

We will build [describe the specific system here] integrated with [tools/platforms]. This replaces the manual process of [current manual workflow] and delivers [measurable outcome].

**What {company} receives:**
- [Core deliverable 1]
- [Core deliverable 2]
- [Core deliverable 3]

{_section_divider("Scope of Work")}

| Deliverable | Description | Acceptance Criterion | Timeline |
|-------------|-------------|---------------------|----------|
| [Name] | [What it is] | [How we both know it's done] | Week X |
| [Name] | [What it is] | [How we both know it's done] | Week X |

**Not included in this scope:**
- Ongoing maintenance after delivery (available as add-on retainer)
- Changes outside the defined deliverables above (handled via change order)

{_section_divider("Timeline")}

```
Phase 1: Discovery & Setup (Week 1)
  - Onboarding call, access setup, requirements confirmation
  - Milestone: All credentials received and requirements signed off

Phase 2: Build (Weeks 2–4)
  - Core system built in staging environment
  - Milestone: Client reviews and approves staging version

Phase 3: Launch & Handoff (Week 5–6)
  - Live deployment, testing, client training
  - Milestone: Client confirms system is operating correctly
```

{_section_divider("Investment")}

| Tier | Investment | Includes | |
|------|-----------|----------|---|
{tiers_table_rows}

**Selected tier: {tier_data['label']} — {fee_display}**

{includes_str}

**Payment schedule:**
- 50% due on contract signing: {f"${budget // 2:,}" if budget else "50% upfront"}
- 50% due on final delivery and sign-off: {f"${budget - budget // 2:,}" if budget else "50% on delivery"}

For projects over $5,000: 33% upfront / 33% at midpoint milestone / 33% on delivery.

{_section_divider("Terms")}

**Revisions:** {tier_data['includes'][1] if len(tier_data['includes']) > 1 else "Included as per tier"}.

**Change orders:** Any work outside this scope requires a written change order before it begins. Change orders are billed at $150/hr or as a fixed add-on, agreed in advance.

**Intellectual property:** All deliverables become {company}'s property upon final payment.

**Confidentiality:** All shared business information is kept confidential. A mutual NDA is available on request.

{_section_divider("About OASIS AI")}

OASIS AI Solutions builds automation systems for service businesses — consistently cutting manual work and creating infrastructure that scales. Founded by Conaugh McKenna, we keep our client roster intentionally small so every project gets the focus it deserves.

{_section_divider("Next Steps")}

To move forward, reply confirming the scope and preferred tier. I'll send the contract and first invoice within 24 hours.

This proposal is valid until **{expiry}**.

---

*Questions? Reply here or book a call: [calendar link]*
"""


def _build_discovery_proposal(client: str, context: dict, today: str, expiry: str) -> str:
    company  = context.get("company") or client
    industry = context.get("industry") or "your industry"

    return f"""# Discovery Engagement — {company}

**Prepared by:** Conaugh McKenna, OASIS AI Solutions
**Date:** {today}
**Valid until:** {expiry}

{_section_divider("What This Is")}

Before committing to a retainer or project, this engagement gives {company} a clear picture of what can be automated, what the ROI looks like, and what a realistic roadmap looks like. It de-risks the decision for both sides.

This is a paid engagement — it's not a free consultation. The output is a written deliverable {company} can act on, with or without OASIS AI.

{_section_divider("What You Get")}

- A 60-minute discovery session (recorded with your permission)
- A written automation audit: current processes mapped, automation potential scored
- A prioritised roadmap: top 3–5 automations ranked by time saved and implementation effort
- An investment estimate: what each automation would cost to build as a retainer or project

**Deliverable format:** PDF report, delivered within 5 business days of the discovery session.

{_section_divider("Investment")}

**Flat fee: {DISCOVERY_FEE_RANGE}** (based on business complexity — confirmed before booking)

**This fee applies toward your first retainer or project** if you proceed within 30 days.

Payment due on booking. Net 0 terms (pay to confirm the session).

{_section_divider("Timeline")}

```
Day 1:   Invoice paid — session booked
Day 2-7: 60-minute discovery session
Day 7-12: Audit and roadmap prepared
Day 12:   Written deliverable delivered
```

{_section_divider("Terms")}

**Cancellation:** Full refund if cancelled 48+ hours before the session. 50% refund within 48 hours. No refund for no-shows.

**Confidentiality:** Everything shared in the session is confidential.

{_section_divider("About OASIS AI")}

OASIS AI Solutions helps service businesses automate the manual work that's eating their time. Founded by Conaugh McKenna, our audits consistently surface 10–20 hours/week of automatable work in businesses that thought they "weren't ready for AI."

{_section_divider("Next Steps")}

Reply to confirm interest and I'll send the invoice. The session is booked once payment clears.

This offer is valid until **{expiry}**.

---

*Questions? Reach out: conaugh@oasisai.io*
"""


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def cmd_create(env_vars: dict[str, str], args: argparse.Namespace) -> int:
    if not args.client:
        print("ERROR: --client is required. Example: --client \"Acme HVAC\"", file=sys.stderr)
        return 1

    proposal_type = (args.type or "retainer").lower()
    if proposal_type not in PROPOSAL_TYPES:
        print(f"ERROR: --type must be one of: {', '.join(PROPOSAL_TYPES)}", file=sys.stderr)
        return 1

    tier = (args.tier or "growth").lower()

    db_client = get_supabase_client(env_vars)
    context   = lookup_client(db_client, args.client)

    today  = datetime.now().strftime("%Y-%m-%d")
    expiry_dt = datetime.now()
    # 14-day expiry
    from datetime import timedelta
    expiry = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")

    builders = {
        "retainer":  _build_retainer_proposal,
        "project":   _build_project_proposal,
        "discovery": lambda *a, **kw: _build_discovery_proposal(*a, **kw),
    }

    if proposal_type == "discovery":
        content = _build_discovery_proposal(args.client, context, today, expiry)
    elif proposal_type == "retainer":
        content = _build_retainer_proposal(args.client, tier, args.budget, context, today, expiry)
    else:
        content = _build_project_proposal(args.client, tier, args.budget, context, today, expiry)

    # Save to proposals/
    PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = args.client.lower().replace(" ", "-").replace("/", "-")[:40]
    filename  = f"{today}-{proposal_type}-{safe_name}.md"
    out_path  = PROPOSALS_DIR / filename

    out_path.write_text(content, encoding="utf-8")

    result = {
        "status":        "created",
        "file":          str(out_path),
        "client":        args.client,
        "type":          proposal_type,
        "tier":          tier,
        "expiry":        expiry,
        "context_found": bool(context),
    }

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Proposal created: {out_path}")
        print(f"  Client:  {args.client}")
        print(f"  Type:    {proposal_type}")
        print(f"  Tier:    {tier}")
        print(f"  Expires: {expiry}")
        if not context:
            print("  NOTE: No client record found in Supabase — proposal uses generic context.")
            print("        Add client notes with: python scripts/lead_engine.py add ...")

    # Update Supabase lead record if client is found
    if context and db_client and context.get("id"):
        try:
            db_client.table("leads").update({
                "proposal_sent_date": today,
                "proposal_type":      proposal_type,
                "proposal_tier":      tier,
                "status":             "proposal",
            }).eq("id", context["id"]).execute()
            if not args.json:
                print("  Supabase: Lead status updated to 'proposal'.")
        except Exception as exc:
            if not args.json:
                print(f"  NOTE: Could not update Supabase lead record: {exc}")

    return 0


def cmd_list(env_vars: dict[str, str], args: argparse.Namespace) -> int:
    if not PROPOSALS_DIR.exists():
        msg = "No proposals directory found. Run 'create' to generate the first proposal."
        if args.json:
            print(json.dumps({"proposals": [], "message": msg}, indent=2))
        else:
            print(msg)
        return 0

    files = sorted(PROPOSALS_DIR.glob("*.md"), reverse=True)
    if not files:
        msg = "No proposals found in proposals/ directory."
        if args.json:
            print(json.dumps({"proposals": [], "message": msg}, indent=2))
        else:
            print(msg)
        return 0

    proposals = []
    for f in files:
        # Parse filename: YYYY-MM-DD-type-client.md
        parts = f.stem.split("-", 3)
        proposals.append({
            "filename": f.name,
            "path":     str(f),
            "date":     "-".join(parts[:3]) if len(parts) >= 3 else "unknown",
            "type":     parts[3].split("-")[0] if len(parts) == 4 else "unknown",
        })

    if args.json:
        print(json.dumps({"proposals": proposals}, indent=2))
    else:
        print(f"{'DATE':<12} {'TYPE':<12} {'FILENAME'}")
        print("-" * 70)
        for p in proposals:
            print(f"{p['date']:<12} {p['type']:<12} {p['filename']}")

    return 0


def cmd_templates(env_vars: dict[str, str], args: argparse.Namespace) -> int:
    data = {
        "proposal_types": PROPOSAL_TYPES,
        "retainer_tiers": {
            k: {
                "label":   v["label"],
                "range":   v["range"],
                "default": v["default"],
            }
            for k, v in RETAINER_TIERS.items()
        },
        "project_tiers": {
            k: {
                "label": v["label"],
                "range": v["range"],
            }
            for k, v in PROJECT_TIERS.items()
        },
        "discovery_fee_range":  DISCOVERY_FEE_RANGE,
        "follow_up_cadence": [
            {"day": d, "channel": ch, "tone": t}
            for d, ch, t in FOLLOW_UP_CADENCE
        ],
    }

    if args.json:
        print(json.dumps(data, indent=2))
        return 0

    print("Available Templates\n")
    print("Proposal Types:", ", ".join(PROPOSAL_TYPES))
    print()
    print("Retainer Tiers:")
    for k, v in RETAINER_TIERS.items():
        print(f"  {k:<12} {v['label']:<12} {v['range']}")
    print()
    print("Project Tiers:")
    for k, v in PROJECT_TIERS.items():
        print(f"  {k:<12} {v['label']:<12} {v['range']}")
    print()
    print("Discovery:", DISCOVERY_FEE_RANGE)
    print()
    print("Follow-Up Cadence After Sending:")
    for day, channel, tone in FOLLOW_UP_CADENCE:
        print(f"  {day:<8} via {channel:<15} — {tone}")

    return 0


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="proposal_generator.py",
        description="Proposal Generator — OASIS AI Solutions",
    )
    parser.add_argument("--json", action="store_true", help="Output JSON for agent consumption")

    sub = parser.add_subparsers(dest="command")

    create_p = sub.add_parser("create", help="Generate a new proposal")
    create_p.add_argument("--client",  required=False, help="Client name (searched in Supabase)")
    create_p.add_argument(
        "--type",
        choices=PROPOSAL_TYPES,
        default="retainer",
        help="Proposal type (default: retainer)",
    )
    create_p.add_argument(
        "--tier",
        choices=list(RETAINER_TIERS) + list(PROJECT_TIERS),
        default="growth",
        help="Pricing tier (default: growth)",
    )
    create_p.add_argument(
        "--budget",
        type=int,
        default=None,
        help="Override the default fee with a specific amount (no $ symbol)",
    )

    sub.add_parser("list",      help="List all generated proposals")
    sub.add_parser("templates", help="Show available proposal types and pricing tiers")

    return parser


def main() -> int:
    parser = build_parser()
    args   = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    env_vars = load_env()

    commands = {
        "create":    cmd_create,
        "list":      cmd_list,
        "templates": cmd_templates,
    }

    handler = commands.get(args.command)
    if not handler:
        print(f"ERROR: Unknown command '{args.command}'", file=sys.stderr)
        return 1

    return handler(env_vars, args)


if __name__ == "__main__":
    sys.exit(main())
