"""
Lead Engine - OASIS AI CRM CLI
Zero-paid-service lead management backed by Supabase (project: bravo).
Replaces ManyChat, HubSpot, and every other CRM CC doesn't need to pay for.

All credentials loaded from .env.agents (never hardcoded).

Usage:
  python scripts/lead_engine.py list [--status new|contacted|qualified|proposal|won|lost] [--source instagram|...] [--limit 20]
  python scripts/lead_engine.py add "Name" --email x@y.com --phone 123 --company "Acme" --source cold_outreach --notes "Met at event"
  python scripts/lead_engine.py view <lead_id>
  python scripts/lead_engine.py update <lead_id> --status qualified --score 75 --notes "Had good call"
  python scripts/lead_engine.py score <lead_id>
  python scripts/lead_engine.py interact <lead_id> --type email_sent --channel email --subject "Follow-up" --content "Hey..."
  python scripts/lead_engine.py followups
  python scripts/lead_engine.py pipeline
  python scripts/lead_engine.py search "query"
  python scripts/lead_engine.py funnel <lead_id> <funnel_slug> [--stage awareness]
  python scripts/lead_engine.py --json <any command>
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


# -- Credential loading (identical pattern to supabase_tool.py) ----------------

def load_env():
    """Load .env.agents from project root."""
    env_path = Path(__file__).resolve().parent.parent / ".env.agents"
    if not env_path.exists():
        print(f"ERROR: {env_path} not found", file=sys.stderr)
        sys.exit(1)

    env_vars = {}
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                env_vars[key.strip()] = value.strip()
    return env_vars


def get_client(env_vars):
    """Create a Supabase client for the bravo project."""
    try:
        from supabase import create_client
    except ImportError:
        print("ERROR: supabase not installed. Run: pip install supabase", file=sys.stderr)
        sys.exit(1)

    url = env_vars.get("BRAVO_SUPABASE_URL")
    key = env_vars.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY")

    if not url or not key:
        print("ERROR: Missing BRAVO_SUPABASE_URL or BRAVO_SUPABASE_SERVICE_ROLE_KEY in .env.agents", file=sys.stderr)
        sys.exit(1)

    return create_client(url, key)


# -- Scoring -------------------------------------------------------------------

INTERACTION_SCORES = {
    "email_opened": 10,
    "email_clicked": 15,
    "meeting": 20,
    "dm_reply": 15,
}
INTERACTION_BASE = 5
INTERACTION_CAP = 30


def calculate_score(lead: dict, interactions: list) -> int:
    """
    Auto-calculate a lead score from 0-100 based on data completeness,
    interaction history, and recency.
    """
    score = 0

    # Data completeness
    if lead.get("email"):
        score += 10
    if lead.get("phone"):
        score += 10
    if lead.get("company"):
        score += 5

    # Interaction value (capped at 30)
    interaction_total = 0
    for ix in interactions:
        ix_type = ix.get("type", "")
        interaction_total += INTERACTION_SCORES.get(ix_type, INTERACTION_BASE)
    score += min(interaction_total, INTERACTION_CAP)

    # Recency bonus (based on most recent interaction)
    if interactions:
        now = datetime.now(timezone.utc)
        # created_at comes back as ISO string from Supabase
        latest_str = max(ix.get("created_at", "") for ix in interactions)
        if latest_str:
            try:
                latest = datetime.fromisoformat(latest_str.replace("Z", "+00:00"))
                days_ago = (now - latest).days
                if days_ago <= 7:
                    score += 10
                elif days_ago <= 30:
                    score += 5
            except (ValueError, TypeError):
                pass

    return min(score, 100)


# -- Formatting helpers --------------------------------------------------------

STATUS_LABELS = {
    "new": "NEW",
    "contacted": "CONTACTED",
    "qualified": "QUALIFIED",
    "proposal": "PROPOSAL",
    "won": "WON",
    "lost": "LOST",
}

SOURCE_LABELS = {
    "instagram": "Instagram",
    "website": "Website",
    "cold_outreach": "Cold Outreach",
    "referral": "Referral",
    "linkedin": "LinkedIn",
    "facebook": "Facebook",
    "event": "Event",
    "other": "Other",
}


def fmt_date(iso_str: str) -> str:
    """Format an ISO timestamp to a readable short date."""
    if not iso_str:
        return "-"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return iso_str[:10] if iso_str else "-"


def fmt_score(score) -> str:
    """Format score with a basic heat indicator."""
    if score is None:
        return "  -"
    s = int(score)
    if s >= 70:
        bar = "***"
    elif s >= 40:
        bar = "** "
    else:
        bar = "*  "
    return f"{s:3d} {bar}"


def truncate(text: str, max_len: int = 40) -> str:
    if not text:
        return ""
    return text[:max_len - 1] + "..." if len(text) > max_len else text


# -- Command handlers ----------------------------------------------------------

def cmd_list(client, args, output_json: bool):
    """List leads with optional filters."""
    query = client.table("leads").select("*")

    if args.status:
        query = query.eq("status", args.status)
    if args.source:
        query = query.eq("source", args.source)

    query = query.order("created_at", desc=True).limit(args.limit)
    result = query.execute()
    leads = result.data or []

    if output_json:
        print(json.dumps(leads, indent=2, default=str))
        return

    if not leads:
        print("No leads found.")
        return

    # Table header
    col_id     = 8
    col_name   = 22
    col_status = 11
    col_source = 14
    col_score  = 9
    col_date   = 11

    header = (
        f"{'ID':<{col_id}}  "
        f"{'NAME':<{col_name}}  "
        f"{'STATUS':<{col_status}}  "
        f"{'SOURCE':<{col_source}}  "
        f"{'SCORE':<{col_score}}  "
        f"{'CREATED':<{col_date}}"
    )
    sep = "-" * len(header)
    print(sep)
    print(header)
    print(sep)

    for lead in leads:
        lead_id = str(lead.get("id", ""))[:col_id]
        name = truncate(lead.get("name", "-"), col_name)
        status = STATUS_LABELS.get(lead.get("status", ""), lead.get("status", "-"))[:col_status]
        source = SOURCE_LABELS.get(lead.get("source", ""), lead.get("source", "-"))[:col_source]
        score = fmt_score(lead.get("score"))
        created = fmt_date(lead.get("created_at"))

        print(
            f"{lead_id:<{col_id}}  "
            f"{name:<{col_name}}  "
            f"{status:<{col_status}}  "
            f"{source:<{col_source}}  "
            f"{score:<{col_score}}  "
            f"{created:<{col_date}}"
        )

    print(sep)
    print(f"  {len(leads)} lead(s)")


def cmd_add(client, args, output_json: bool):
    """Add a new lead."""
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "name": args.name,
        "status": "new",
        "created_at": now,
        "updated_at": now,
    }
    if args.email:
        payload["email"] = args.email
    if args.phone:
        payload["phone"] = args.phone
    if args.company:
        payload["company"] = args.company
    if args.source:
        payload["source"] = args.source
    if args.notes:
        payload["notes"] = args.notes

    result = client.table("leads").insert(payload).execute()
    lead = result.data[0] if result.data else {}

    if output_json:
        print(json.dumps(lead, indent=2, default=str))
        return

    print(f"Lead created.")
    print(f"  ID:      {lead.get('id', '?')}")
    print(f"  Name:    {lead.get('name')}")
    print(f"  Email:   {lead.get('email', '-')}")
    print(f"  Phone:   {lead.get('phone', '-')}")
    print(f"  Company: {lead.get('company', '-')}")
    print(f"  Source:  {lead.get('source', '-')}")
    print(f"  Status:  new")


def cmd_view(client, args, output_json: bool):
    """Show a lead and all its interactions."""
    lead_result = client.table("leads").select("*").eq("id", args.lead_id).execute()
    if not lead_result.data:
        print(f"ERROR: Lead '{args.lead_id}' not found.", file=sys.stderr)
        sys.exit(1)
    lead = lead_result.data[0]

    ix_result = (
        client.table("lead_interactions")
        .select("*")
        .eq("lead_id", args.lead_id)
        .order("created_at", desc=False)
        .execute()
    )
    interactions = ix_result.data or []

    if output_json:
        print(json.dumps({"lead": lead, "interactions": interactions}, indent=2, default=str))
        return

    sep = "=" * 60
    print(sep)
    print(f"  {lead.get('name', '-')}")
    print(sep)
    print(f"  ID:          {lead.get('id')}")
    print(f"  Status:      {STATUS_LABELS.get(lead.get('status', ''), lead.get('status', '-'))}")
    print(f"  Score:       {lead.get('score', '-')}")
    print(f"  Email:       {lead.get('email', '-')}")
    print(f"  Phone:       {lead.get('phone', '-')}")
    print(f"  Company:     {lead.get('company', '-')}")
    print(f"  Website:     {lead.get('website', '-')}")
    print(f"  Source:      {SOURCE_LABELS.get(lead.get('source', ''), lead.get('source', '-'))}")
    print(f"  Assigned to: {lead.get('assigned_to', '-')}")
    print(f"  Tags:        {', '.join(lead.get('tags') or []) or '-'}")
    print(f"  Last contact:{fmt_date(lead.get('last_contacted_at'))}")
    print(f"  Next follow: {fmt_date(lead.get('next_followup_at'))}")
    print(f"  Created:     {fmt_date(lead.get('created_at'))}")
    if lead.get("notes"):
        print(f"\n  Notes:")
        for line in lead["notes"].splitlines():
            print(f"    {line}")

    if interactions:
        print(f"\n  Interactions ({len(interactions)}):")
        print("  " + "-" * 56)
        for ix in interactions:
            date = fmt_date(ix.get("created_at"))
            ix_type = ix.get("type", "?")
            channel = ix.get("channel", "")
            subject = ix.get("subject", "")
            label = f"[{ix_type}]" + (f" via {channel}" if channel else "")
            print(f"  {date}  {label}")
            if subject:
                print(f"           Subject: {subject}")
            if ix.get("content"):
                preview = truncate(ix["content"], 80)
                print(f"           {preview}")
    else:
        print("\n  No interactions yet.")

    print(sep)


def cmd_update(client, args, output_json: bool):
    """Update lead fields."""
    payload: dict = {"updated_at": datetime.now(timezone.utc).isoformat()}

    if args.status:
        payload["status"] = args.status
    if args.score is not None:
        payload["score"] = args.score
    if args.notes:
        # Append to existing notes rather than overwrite
        existing_result = client.table("leads").select("notes").eq("id", args.lead_id).execute()
        existing_notes = ""
        if existing_result.data:
            existing_notes = existing_result.data[0].get("notes") or ""
        datestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if existing_notes:
            payload["notes"] = f"{existing_notes}\n[{datestamp}] {args.notes}"
        else:
            payload["notes"] = f"[{datestamp}] {args.notes}"
    if args.email:
        payload["email"] = args.email
    if args.phone:
        payload["phone"] = args.phone
    if args.company:
        payload["company"] = args.company
    if args.next_followup:
        payload["next_followup_at"] = args.next_followup
    if args.assigned_to:
        payload["assigned_to"] = args.assigned_to

    if len(payload) == 1:
        print("ERROR: No fields to update. Specify at least one of --status, --score, --notes, etc.", file=sys.stderr)
        sys.exit(1)

    result = client.table("leads").update(payload).eq("id", args.lead_id).execute()
    lead = result.data[0] if result.data else {}

    if output_json:
        print(json.dumps(lead, indent=2, default=str))
        return

    print(f"Lead updated.")
    for k, v in payload.items():
        if k != "updated_at":
            print(f"  {k}: {v}")


def cmd_score(client, args, output_json: bool):
    """Auto-calculate and save a lead's score."""
    lead_result = client.table("leads").select("*").eq("id", args.lead_id).execute()
    if not lead_result.data:
        print(f"ERROR: Lead '{args.lead_id}' not found.", file=sys.stderr)
        sys.exit(1)
    lead = lead_result.data[0]

    ix_result = (
        client.table("lead_interactions")
        .select("*")
        .eq("lead_id", args.lead_id)
        .execute()
    )
    interactions = ix_result.data or []

    new_score = calculate_score(lead, interactions)

    client.table("leads").update({
        "score": new_score,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", args.lead_id).execute()

    if output_json:
        print(json.dumps({"lead_id": args.lead_id, "score": new_score}, indent=2))
        return

    print(f"Score calculated: {new_score}/100")
    print(f"  Has email:      {'yes (+10)' if lead.get('email') else 'no'}")
    print(f"  Has phone:      {'yes (+10)' if lead.get('phone') else 'no'}")
    print(f"  Has company:    {'yes (+5)' if lead.get('company') else 'no'}")
    print(f"  Interactions:   {len(interactions)} logged")
    print(f"  Score saved.")


def cmd_interact(client, args, output_json: bool):
    """Log an interaction against a lead."""
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "lead_id": args.lead_id,
        "type": args.type,
        "created_at": now,
    }
    if args.channel:
        payload["channel"] = args.channel
    if args.subject:
        payload["subject"] = args.subject
    if args.content:
        payload["content"] = args.content
    if args.metadata:
        try:
            payload["metadata"] = json.loads(args.metadata)
        except json.JSONDecodeError:
            print("ERROR: --metadata must be valid JSON.", file=sys.stderr)
            sys.exit(1)

    result = client.table("lead_interactions").insert(payload).execute()
    ix = result.data[0] if result.data else {}

    # Update last_contacted_at on the lead
    client.table("leads").update({
        "last_contacted_at": now,
        "updated_at": now,
    }).eq("id", args.lead_id).execute()

    if output_json:
        print(json.dumps(ix, indent=2, default=str))
        return

    print(f"Interaction logged.")
    print(f"  ID:      {ix.get('id', '?')}")
    print(f"  Lead:    {args.lead_id}")
    print(f"  Type:    {args.type}")
    print(f"  Channel: {args.channel or '-'}")
    if args.subject:
        print(f"  Subject: {args.subject}")


def cmd_followups(client, args, output_json: bool):
    """Show leads where next_followup_at is today or overdue."""
    today = datetime.now(timezone.utc).date().isoformat()
    result = (
        client.table("leads")
        .select("*")
        .lte("next_followup_at", today)
        .not_.is_("next_followup_at", "null")
        .order("next_followup_at", desc=False)
        .execute()
    )
    leads = result.data or []

    if output_json:
        print(json.dumps(leads, indent=2, default=str))
        return

    if not leads:
        print(f"No follow-ups due today or overdue.")
        return

    print(f"Follow-ups due (as of {today}):\n")
    for lead in leads:
        due = fmt_date(lead.get("next_followup_at"))
        name = lead.get("name", "-")
        status = STATUS_LABELS.get(lead.get("status", ""), "?")
        email = lead.get("email", "")
        overdue_marker = " [OVERDUE]" if due != "-" and due < today else ""
        print(f"  {due}{overdue_marker}  {name}  [{status}]")
        if email:
            print(f"           {email}")
    print(f"\n  {len(leads)} follow-up(s) pending.")


def cmd_pipeline(client, args, output_json: bool):
    """Show pipeline summary: count and avg score by status."""
    result = client.table("leads").select("status, score").execute()
    leads = result.data or []

    stages = ["new", "contacted", "qualified", "proposal", "won", "lost"]
    summary: dict[str, dict] = {s: {"count": 0, "scores": []} for s in stages}

    for lead in leads:
        status = lead.get("status", "new")
        if status not in summary:
            summary[status] = {"count": 0, "scores": []}
        summary[status]["count"] += 1
        if lead.get("score") is not None:
            summary[status]["scores"].append(lead["score"])

    if output_json:
        output = {}
        for stage in stages:
            d = summary.get(stage, {"count": 0, "scores": []})
            scores = d["scores"]
            output[stage] = {
                "count": d["count"],
                "avg_score": round(sum(scores) / len(scores), 1) if scores else None,
            }
        print(json.dumps(output, indent=2))
        return

    print("Pipeline Summary\n")
    print(f"  {'STAGE':<12}  {'COUNT':>6}  {'AVG SCORE':>10}")
    print("  " + "-" * 34)
    total = 0
    for stage in stages:
        d = summary.get(stage, {"count": 0, "scores": []})
        count = d["count"]
        scores = d["scores"]
        avg = f"{sum(scores)/len(scores):.0f}" if scores else "-"
        label = STATUS_LABELS.get(stage, stage.upper())
        print(f"  {label:<12}  {count:>6}  {avg:>10}")
        total += count
    print("  " + "-" * 34)
    print(f"  {'TOTAL':<12}  {total:>6}")
    print()


def cmd_search(client, args, output_json: bool):
    """Search leads by name, email, or company (case-insensitive substring)."""
    q = args.query.lower()

    # Supabase PostgREST ilike for substring matching
    # We query each field and merge - using or_ filter with ilike
    result = (
        client.table("leads")
        .select("*")
        .or_(f"name.ilike.%{q}%,email.ilike.%{q}%,company.ilike.%{q}%")
        .order("created_at", desc=True)
        .limit(50)
        .execute()
    )
    leads = result.data or []

    if output_json:
        print(json.dumps(leads, indent=2, default=str))
        return

    if not leads:
        print(f"No leads matching '{args.query}'.")
        return

    print(f"Search results for '{args.query}':\n")
    for lead in leads:
        name = lead.get("name", "-")
        email = lead.get("email", "")
        company = lead.get("company", "")
        status = STATUS_LABELS.get(lead.get("status", ""), "?")
        lead_id = str(lead.get("id", ""))[:8]
        parts = filter(None, [email, company])
        print(f"  [{lead_id}]  {name}  [{status}]  {' | '.join(parts)}")

    print(f"\n  {len(leads)} result(s).")


def cmd_funnel(client, args, output_json: bool):
    """Add a lead to a funnel by slug, optionally setting the entry stage."""
    # Resolve funnel by slug
    funnel_result = (
        client.table("funnels")
        .select("*")
        .eq("slug", args.funnel_slug)
        .limit(1)
        .execute()
    )
    if not funnel_result.data:
        print(f"ERROR: No funnel found with slug '{args.funnel_slug}'.", file=sys.stderr)
        sys.exit(1)
    funnel = funnel_result.data[0]

    # Check for existing entry
    existing = (
        client.table("funnel_entries")
        .select("*")
        .eq("funnel_id", funnel["id"])
        .eq("lead_id", args.lead_id)
        .limit(1)
        .execute()
    )

    now = datetime.now(timezone.utc).isoformat()

    if existing.data:
        # Update stage if provided
        if args.stage:
            client.table("funnel_entries").update({
                "current_stage": args.stage,
            }).eq("id", existing.data[0]["id"]).execute()
            entry = {**existing.data[0], "current_stage": args.stage}
            action = "updated"
        else:
            entry = existing.data[0]
            action = "already enrolled"
    else:
        payload = {
            "funnel_id": funnel["id"],
            "lead_id": args.lead_id,
            "entered_at": now,
            "current_stage": args.stage or None,
        }
        result = client.table("funnel_entries").insert(payload).execute()
        entry = result.data[0] if result.data else {}
        action = "enrolled"

    if output_json:
        print(json.dumps({"action": action, "entry": entry, "funnel": funnel}, indent=2, default=str))
        return

    print(f"Lead {action} in funnel '{funnel.get('name', funnel['slug'])}'.")
    print(f"  Funnel ID:     {funnel['id']}")
    print(f"  Lead ID:       {args.lead_id}")
    print(f"  Current stage: {entry.get('current_stage') or '-'}")
    print(f"  Entered:       {fmt_date(entry.get('entered_at'))}")


# -- Argument parser -----------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lead_engine.py",
        description="OASIS AI Lead Engine - CRM CLI backed by Supabase",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s list
  %(prog)s list --status qualified --limit 10
  %(prog)s add "Jane Smith" --email jane@acme.com --company "Acme" --source cold_outreach
  %(prog)s view <lead_id>
  %(prog)s update <lead_id> --status qualified --notes "Great call"
  %(prog)s score <lead_id>
  %(prog)s interact <lead_id> --type meeting --channel zoom --subject "Discovery call"
  %(prog)s followups
  %(prog)s pipeline
  %(prog)s search "acme"
  %(prog)s funnel <lead_id> onboarding --stage awareness
  %(prog)s --json pipeline
        """,
    )

    # Global --json flag - must come before subcommand
    parser.add_argument(
        "--json",
        dest="output_json",
        action="store_true",
        help="Output raw JSON for agent consumption",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # -- list ------------------------------------------------------------------
    p_list = subparsers.add_parser("list", help="List leads with optional filters")
    p_list.add_argument("--status", choices=["new", "contacted", "qualified", "proposal", "won", "lost"])
    p_list.add_argument("--source", choices=["instagram", "website", "cold_outreach", "referral", "linkedin", "facebook", "event", "other"])
    p_list.add_argument("--limit", "-l", type=int, default=20)

    # -- add -------------------------------------------------------------------
    p_add = subparsers.add_parser("add", help="Add a new lead")
    p_add.add_argument("name", help="Lead's full name")
    p_add.add_argument("--email")
    p_add.add_argument("--phone")
    p_add.add_argument("--company")
    p_add.add_argument("--source", choices=["instagram", "website", "cold_outreach", "referral", "linkedin", "facebook", "event", "other"])
    p_add.add_argument("--notes")

    # -- view ------------------------------------------------------------------
    p_view = subparsers.add_parser("view", help="View a lead and all interactions")
    p_view.add_argument("lead_id", help="Lead UUID")

    # -- update ----------------------------------------------------------------
    p_update = subparsers.add_parser("update", help="Update lead fields")
    p_update.add_argument("lead_id", help="Lead UUID")
    p_update.add_argument("--status", choices=["new", "contacted", "qualified", "proposal", "won", "lost"])
    p_update.add_argument("--score", type=int)
    p_update.add_argument("--notes", help="Appended to existing notes with datestamp")
    p_update.add_argument("--email")
    p_update.add_argument("--phone")
    p_update.add_argument("--company")
    p_update.add_argument("--next-followup", dest="next_followup", metavar="YYYY-MM-DD")
    p_update.add_argument("--assigned-to", dest="assigned_to")

    # -- score -----------------------------------------------------------------
    p_score = subparsers.add_parser("score", help="Auto-calculate and save lead score")
    p_score.add_argument("lead_id", help="Lead UUID")

    # -- interact --------------------------------------------------------------
    p_interact = subparsers.add_parser("interact", help="Log an interaction against a lead")
    p_interact.add_argument("lead_id", help="Lead UUID")
    p_interact.add_argument(
        "--type",
        required=True,
        choices=[
            "email_sent", "email_opened", "email_clicked",
            "dm_sent", "dm_reply",
            "call", "meeting",
            "proposal_sent", "contract_sent",
            "note",
        ],
        help="Interaction type",
    )
    p_interact.add_argument("--channel", choices=["email", "instagram", "linkedin", "facebook", "zoom", "phone", "in_person", "other"])
    p_interact.add_argument("--subject")
    p_interact.add_argument("--content")
    p_interact.add_argument("--metadata", help="JSON metadata (e.g. '{\"open_rate\": 0.5}')")

    # -- followups -------------------------------------------------------------
    subparsers.add_parser("followups", help="Show leads with next_followup_at <= today")

    # -- pipeline --------------------------------------------------------------
    subparsers.add_parser("pipeline", help="Pipeline summary by stage")

    # -- search ----------------------------------------------------------------
    p_search = subparsers.add_parser("search", help="Search by name, email, or company")
    p_search.add_argument("query", help="Search string")

    # -- funnel ----------------------------------------------------------------
    p_bulk = subparsers.add_parser("bulk-import", help="Bulk import leads from LEAD_TRACKER.csv")
    p_bulk.add_argument("--file", default="memory/LEAD_TRACKER.csv", help="Path to CSV (default: memory/LEAD_TRACKER.csv)")
    p_bulk.add_argument("--dry-run", action="store_true", help="Parse and validate without inserting")

    p_funnel = subparsers.add_parser("funnel", help="Enroll or update a lead in a funnel")
    p_funnel.add_argument("lead_id", help="Lead UUID")
    p_funnel.add_argument("funnel_slug", help="Funnel slug identifier")
    p_funnel.add_argument("--stage", help="Stage to set (e.g. awareness, nurture, close)")

    return parser


# -- Entry point ---------------------------------------------------------------

def cmd_bulk_import(client, args, output_json: bool):
    """Bulk import leads from LEAD_TRACKER.csv into Supabase."""
    import csv
    import re

    csv_path = args.file
    if not os.path.isabs(csv_path):
        csv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), csv_path)

    if not os.path.exists(csv_path):
        print(f"ERROR: File not found: {csv_path}", file=sys.stderr)
        sys.exit(1)

    # Load existing leads to dedupe by email + company
    existing = client.table("leads").select("email,company").execute().data or []
    existing_emails = {r.get("email", "").lower() for r in existing if r.get("email")}
    existing_companies = {r.get("company", "").lower() for r in existing if r.get("company")}

    email_re = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

    status_map = {
        "sent": "contacted",
        "called": "contacted",
        "called+emailed": "contacted",
        "meeting booked": "qualified",
        "warm": "qualified",
        "qualified": "qualified",
        "won": "won",
        "lost": "lost",
        "proposal": "proposal",
    }

    to_insert, skipped = [], []
    now = datetime.now(timezone.utc).isoformat()

    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = (row.get("Lead Name") or "").strip()
            company = (row.get("Business Name") or "").strip()
            category = (row.get("Category") or "").strip()
            contact = (row.get("Email/Contact") or "").strip()
            phone = (row.get("Phone") or "").strip() or None
            raw_status = (row.get("Status") or "sent").strip().lower()

            if not name and not company:
                continue

            email = None
            m = email_re.search(contact)
            if m:
                email = m.group(0).lower()

            # Dedupe
            if email and email in existing_emails:
                skipped.append(f"{name} ({company}) — email exists")
                continue
            if company and company.lower() in existing_companies:
                skipped.append(f"{name} ({company}) — company exists")
                continue

            # Map status
            mapped_status = "contacted"
            for key, val in status_map.items():
                if key in raw_status:
                    mapped_status = val
                    break

            payload = {
                "name": name or company,
                "status": mapped_status,
                "created_at": now,
                "updated_at": now,
                "source": "cold_outreach",
                "notes": f"Imported from LEAD_TRACKER.csv | Category: {category} | Original status: {row.get('Status', '')}",
            }
            if email:
                payload["email"] = email
                existing_emails.add(email)
            if phone:
                payload["phone"] = phone
            if company:
                payload["company"] = company
                existing_companies.add(company.lower())

            to_insert.append(payload)

    print(f"Parsed: {len(to_insert)} new leads | Skipped duplicates: {len(skipped)}")

    if args.dry_run:
        print("\n-- DRY RUN -- Sample (first 5):")
        for p in to_insert[:5]:
            print(f"  {p['name']:30} {p.get('email','-'):35} {p.get('company','-'):30} [{p['status']}]")
        return

    if not to_insert:
        print("Nothing to import.")
        return

    # Batch insert in chunks of 50
    inserted = 0
    for i in range(0, len(to_insert), 50):
        batch = to_insert[i:i+50]
        result = client.table("leads").insert(batch).execute()
        inserted += len(result.data or [])

    print(f"\n[OK] Imported {inserted} leads into Supabase.")
    if skipped:
        print(f"     Skipped {len(skipped)} duplicates.")


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    env_vars = load_env()
    client = get_client(env_vars)
    output_json: bool = getattr(args, "output_json", False)

    dispatch = {
        "list": cmd_list,
        "add": cmd_add,
        "view": cmd_view,
        "update": cmd_update,
        "score": cmd_score,
        "interact": cmd_interact,
        "followups": cmd_followups,
        "pipeline": cmd_pipeline,
        "search": cmd_search,
        "funnel": cmd_funnel,
        "bulk-import": cmd_bulk_import,
    }

    handler = dispatch.get(args.command)
    if handler:
        try:
            handler(client, args, output_json)
        except Exception as e:
            if output_json:
                print(json.dumps({"error": str(e)}, indent=2))
            else:
                print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
