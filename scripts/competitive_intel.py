#!/usr/bin/env python3
"""Competitive Intelligence Engine — CEO Dashboard Component

Tracks competitor profiles, generates battlecards, and produces
competitive landscape reports. Data stored in data/competitors.json.

All credentials loaded from .env.agents (never hardcoded).

Usage:
    python scripts/competitive_intel.py add "Lindy AI" --url "https://lindy.ai" --category "indirect"
    python scripts/competitive_intel.py list
    python scripts/competitive_intel.py list --category direct
    python scripts/competitive_intel.py view "Lindy AI"
    python scripts/competitive_intel.py update "Lindy AI" --notes "Raised Series A $10M"
    python scripts/competitive_intel.py update "Lindy AI" --pricing '{"starter": "$49/mo"}'
    python scripts/competitive_intel.py battlecard "Make.com"
    python scripts/competitive_intel.py report
    python scripts/competitive_intel.py matrix
    python scripts/competitive_intel.py delete "Lindy AI"
    python scripts/competitive_intel.py --json <any subcommand>
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
COMPETITORS_FILE = DATA_DIR / "competitors.json"


# ---------------------------------------------------------------------------
# Data layer
# ---------------------------------------------------------------------------

def load_competitors() -> list[dict]:
    if not COMPETITORS_FILE.exists():
        return []
    with open(COMPETITORS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


def save_competitors(competitors: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(COMPETITORS_FILE, "w", encoding="utf-8") as f:
        json.dump(competitors, f, indent=2, ensure_ascii=False)


def find_competitor(competitors: List[Dict], name: str) -> Optional[Dict]:
    name_lower = name.lower()
    for c in competitors:
        if c.get("name", "").lower() == name_lower:
            return c
    return None


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_add(args: argparse.Namespace) -> dict:
    competitors = load_competitors()
    name = args.name.strip()

    if find_competitor(competitors, name):
        return {"error": f"Competitor '{name}' already exists. Use 'update' to modify."}

    pricing: dict = {}
    if args.pricing:
        try:
            pricing = json.loads(args.pricing)
        except json.JSONDecodeError:
            return {"error": "Invalid JSON for --pricing. Use: '{\"starter\": \"$49/mo\"}'"}

    competitor = {
        "name": name,
        "url": args.url or "",
        "pricing_url": args.pricing_url or "",
        "category": args.category or "unknown",
        "founded": args.founded or "",
        "funding": args.funding or "",
        "target_market": args.target_market or "",
        "pricing": pricing,
        "strengths": [],
        "weaknesses": [],
        "features": [],
        "notes": [args.notes] if args.notes else [],
        "win_conditions": [],
        "loss_conditions": [],
        "review_themes": {"praise": "", "complaints": ""},
        "positioning": "",
        "our_counter_positioning": "",
        "created": now_iso(),
        "updated": now_iso(),
    }

    competitors.append(competitor)
    save_competitors(competitors)
    return {"status": "added", "competitor": competitor}


def cmd_list(args: argparse.Namespace) -> dict:
    competitors = load_competitors()
    if not competitors:
        return {"competitors": [], "count": 0}

    if args.category:
        competitors = [c for c in competitors if c.get("category", "").lower() == args.category.lower()]

    summary = []
    for c in competitors:
        summary.append({
            "name": c["name"],
            "url": c.get("url", ""),
            "category": c.get("category", ""),
            "updated": c.get("updated", ""),
            "notes_count": len(c.get("notes", [])),
        })

    return {"competitors": summary, "count": len(summary)}


def cmd_view(args: argparse.Namespace) -> dict:
    competitors = load_competitors()
    competitor = find_competitor(competitors, args.name)
    if not competitor:
        return {"error": f"Competitor '{args.name}' not found."}
    return {"competitor": competitor}


def cmd_update(args: argparse.Namespace) -> dict:
    competitors = load_competitors()
    competitor = find_competitor(competitors, args.name)
    if not competitor:
        return {"error": f"Competitor '{args.name}' not found. Use 'add' first."}

    if args.url:
        competitor["url"] = args.url
    if args.pricing_url:
        competitor["pricing_url"] = args.pricing_url
    if args.category:
        competitor["category"] = args.category
    if args.funding:
        competitor["funding"] = args.funding
    if args.target_market:
        competitor["target_market"] = args.target_market
    if args.positioning:
        competitor["positioning"] = args.positioning
    if args.counter_positioning:
        competitor["our_counter_positioning"] = args.counter_positioning
    if args.pricing:
        try:
            competitor["pricing"] = json.loads(args.pricing)
        except json.JSONDecodeError:
            return {"error": "Invalid JSON for --pricing"}
    if args.notes:
        existing_notes: list = competitor.setdefault("notes", [])
        existing_notes.append(f"[{now_iso()}] {args.notes}")
    if args.strength:
        competitor.setdefault("strengths", []).append(args.strength)
    if args.weakness:
        competitor.setdefault("weaknesses", []).append(args.weakness)
    if args.feature:
        competitor.setdefault("features", []).append(args.feature)
    if args.win:
        competitor.setdefault("win_conditions", []).append(args.win)
    if args.loss:
        competitor.setdefault("loss_conditions", []).append(args.loss)
    if args.praise:
        competitor.setdefault("review_themes", {})["praise"] = args.praise
    if args.complaints:
        competitor.setdefault("review_themes", {})["complaints"] = args.complaints

    competitor["updated"] = now_iso()
    save_competitors(competitors)
    return {"status": "updated", "name": competitor["name"], "updated": competitor["updated"]}


def cmd_delete(args: argparse.Namespace) -> dict:
    competitors = load_competitors()
    before = len(competitors)
    competitors = [c for c in competitors if c.get("name", "").lower() != args.name.lower()]
    if len(competitors) == before:
        return {"error": f"Competitor '{args.name}' not found."}
    save_competitors(competitors)
    return {"status": "deleted", "name": args.name}


def cmd_battlecard(args: argparse.Namespace) -> dict:
    competitors = load_competitors()
    competitor = find_competitor(competitors, args.name)
    if not competitor:
        return {"error": f"Competitor '{args.name}' not found."}

    name = competitor["name"]
    url = competitor.get("url", "N/A")
    category = competitor.get("category", "unknown")
    positioning = competitor.get("positioning") or "(not set - add with: competitive_intel.py update \"{}\" --positioning \"...\"".format(name)
    counter = competitor.get("our_counter_positioning") or "(not set - add with: --counter-positioning)"

    wins = competitor.get("win_conditions", [])
    losses = competitor.get("loss_conditions", [])
    praise = competitor.get("review_themes", {}).get("praise", "")
    complaints = competitor.get("review_themes", {}).get("complaints", "")
    notes = competitor.get("notes", [])

    pricing_lines = ""
    for plan, price in competitor.get("pricing", {}).items():
        pricing_lines += f"  {plan}: {price}\n"
    if not pricing_lines:
        pricing_lines = "  (not set)\n"

    wins_text = "\n".join(f"- {w}" for w in wins) if wins else "- (not set - add with: --win \"condition\")"
    losses_text = "\n".join(f"- {l}" for l in losses) if losses else "- (not set - add with: --loss \"condition\")"
    notes_text = "\n".join(f"- {n}" for n in notes[-5:]) if notes else "- (no notes)"
    praise_text = praise or "(not set)"
    complaints_text = complaints or "(not set)"

    battlecard = f"""## Battlecard: {name} vs OASIS AI Solutions

**Category:** {category} | **URL:** {url} | **Updated:** {competitor.get('updated', 'N/A')}

### Their Pricing
{pricing_lines.rstrip()}

### How They Position Themselves
{positioning}

### How We Position Against Them
{counter}

### Where We Win
{wins_text}

### Where We Lose
{losses_text}

### Handle the "Why not {name}?" Objection
When a prospect mentions {name}:
  - Acknowledge: "They're a solid tool/company."
  - Pivot: "The difference is [our counter positioning]."
  - Ask: "What made you start looking in the first place?"

### Customer Review Themes
**What their customers love:** {praise_text}
**What their customers complain about:** {complaints_text}

### Recent Activity
{notes_text}
"""

    return {"battlecard": battlecard, "name": name}


def cmd_report(args: argparse.Namespace) -> dict:
    competitors = load_competitors()
    if not competitors:
        return {
            "report": "No competitors tracked yet. Add one: python scripts/competitive_intel.py add \"Competitor\" --url \"https://...\" --category direct",
            "count": 0,
        }

    direct = [c for c in competitors if c.get("category", "").lower() == "direct"]
    indirect = [c for c in competitors if c.get("category", "").lower() == "indirect"]
    other = [c for c in competitors if c.get("category", "").lower() not in ("direct", "indirect")]

    lines = [
        f"# Competitive Intelligence Report - {now_iso()}",
        f"\n**Total tracked:** {len(competitors)} ({len(direct)} direct, {len(indirect)} indirect, {len(other)} other)\n",
    ]

    if direct:
        lines.append("## Direct Competitors\n")
        for c in direct:
            lines.append(_competitor_summary_line(c))
        lines.append("")

    if indirect:
        lines.append("## Indirect Competitors\n")
        for c in indirect:
            lines.append(_competitor_summary_line(c))
        lines.append("")

    if other:
        lines.append("## Other\n")
        for c in other:
            lines.append(_competitor_summary_line(c))
        lines.append("")

    lines.append("## Action Items\n")
    stale = [c for c in competitors if _days_since(c.get("updated", "")) > 30]
    if stale:
        lines.append("**Stale profiles (not updated in 30+ days) - review these:**")
        for c in stale:
            lines.append(f"  - {c['name']} (last updated: {c.get('updated', 'unknown')})")
    else:
        lines.append("All competitor profiles updated within 30 days.")

    no_positioning = [c for c in competitors if not c.get("our_counter_positioning")]
    if no_positioning:
        lines.append("\n**Missing counter-positioning (add before next sales call):**")
        for c in no_positioning:
            lines.append(f"  - {c['name']}: competitive_intel.py update \"{c['name']}\" --counter-positioning \"...\"")

    report_text = "\n".join(lines)
    return {"report": report_text, "count": len(competitors)}


def cmd_matrix(args: argparse.Namespace) -> dict:
    competitors = load_competitors()
    if not competitors:
        return {"matrix": "No competitors tracked yet.", "count": 0}

    all_features: list[str] = []
    for c in competitors:
        for f in c.get("features", []):
            if f not in all_features:
                all_features.append(f)

    if not all_features:
        return {"matrix": "No features recorded yet. Add with: competitive_intel.py update \"Name\" --feature \"Feature name\"", "count": 0}

    header = "| Feature | " + " | ".join(c["name"] for c in competitors) + " |"
    separator = "|---------|" + "---------|" * len(competitors)
    rows = [header, separator]

    for feature in all_features:
        row = f"| {feature} |"
        for c in competitors:
            has_feature = feature in c.get("features", [])
            row += " YES |" if has_feature else " NO  |"
        rows.append(row)

    return {"matrix": "\n".join(rows), "features": all_features, "competitors": [c["name"] for c in competitors]}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _competitor_summary_line(c: dict) -> str:
    pricing_items = c.get("pricing", {})
    pricing_str = ", ".join(f"{k}: {v}" for k, v in list(pricing_items.items())[:2]) if pricing_items else "pricing unknown"
    notes_count = len(c.get("notes", []))
    return f"**{c['name']}** ({c.get('url', 'no URL')}) | {pricing_str} | {notes_count} notes | updated {c.get('updated', 'unknown')}"


def _days_since(date_str: str) -> int:
    if not date_str:
        return 999
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        return (datetime.now() - d).days
    except ValueError:
        return 999


def _print_result(result: dict, use_json: bool) -> None:
    if use_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    if "error" in result:
        print(f"ERROR: {result['error']}", file=sys.stderr)
        return

    # Human-readable formatting per command
    if "battlecard" in result:
        print(result["battlecard"])
    elif "report" in result:
        print(result["report"])
        print(f"\n({result.get('count', 0)} competitors tracked)")
    elif "matrix" in result:
        print(result["matrix"])
    elif "competitors" in result and isinstance(result["competitors"], list) and result["competitors"]:
        first = result["competitors"][0]
        if isinstance(first, dict) and "url" in first:
            # list command
            print(f"Competitors ({result['count']}):")
            for c in result["competitors"]:
                print(f"  [{c['category']}] {c['name']} | {c['url']} | updated {c['updated']}")
        else:
            # matrix command competitor names
            print(result["matrix"])
    elif "competitor" in result:
        c = result["competitor"]
        print(f"Name: {c['name']}")
        print(f"URL:  {c.get('url', 'N/A')}")
        print(f"Category: {c.get('category', 'N/A')}")
        print(f"Funding: {c.get('funding', 'N/A')}")
        print(f"Pricing: {json.dumps(c.get('pricing', {}))}")
        print(f"Strengths: {'; '.join(c.get('strengths', []))}")
        print(f"Weaknesses: {'; '.join(c.get('weaknesses', []))}")
        print(f"Win conditions: {'; '.join(c.get('win_conditions', []))}")
        print(f"Loss conditions: {'; '.join(c.get('loss_conditions', []))}")
        print(f"Notes: {len(c.get('notes', []))}")
        print(f"Updated: {c.get('updated', 'N/A')}")
    elif "status" in result:
        print(f"OK: {result.get('status', '')} {result.get('name', result.get('competitor', {}).get('name', ''))}")
    else:
        print(json.dumps(result, indent=2))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Competitive Intelligence Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    sub = parser.add_subparsers(dest="command")

    # add
    p_add = sub.add_parser("add", help="Add a new competitor")
    p_add.add_argument("name", help="Competitor name")
    p_add.add_argument("--url", help="Homepage URL")
    p_add.add_argument("--pricing-url", dest="pricing_url", help="Pricing page URL")
    p_add.add_argument("--category", choices=["direct", "indirect", "aspirational", "unknown"], default="unknown", help="Competitor category")
    p_add.add_argument("--founded", help="Year founded")
    p_add.add_argument("--funding", help="Funding status (e.g. 'Bootstrapped', 'Raised $5M Series A')")
    p_add.add_argument("--target-market", dest="target_market", help="Who they sell to")
    p_add.add_argument("--pricing", help="Pricing as JSON: '{\"starter\": \"$49/mo\"}'")
    p_add.add_argument("--notes", help="Initial notes")

    # list
    p_list = sub.add_parser("list", help="List tracked competitors")
    p_list.add_argument("--category", help="Filter by category")

    # view
    p_view = sub.add_parser("view", help="View full competitor profile")
    p_view.add_argument("name", help="Competitor name")

    # update
    p_update = sub.add_parser("update", help="Update competitor data")
    p_update.add_argument("name", help="Competitor name")
    p_update.add_argument("--url", help="Homepage URL")
    p_update.add_argument("--pricing-url", dest="pricing_url", help="Pricing page URL")
    p_update.add_argument("--category", choices=["direct", "indirect", "aspirational", "unknown"])
    p_update.add_argument("--funding", help="Funding status")
    p_update.add_argument("--target-market", dest="target_market", help="Who they sell to")
    p_update.add_argument("--pricing", help="Pricing as JSON")
    p_update.add_argument("--positioning", help="How they position themselves")
    p_update.add_argument("--counter-positioning", dest="counter_positioning", help="Our counter-positioning")
    p_update.add_argument("--notes", help="Add a timestamped note")
    p_update.add_argument("--strength", help="Add a strength")
    p_update.add_argument("--weakness", help="Add a weakness")
    p_update.add_argument("--feature", help="Add a feature they have")
    p_update.add_argument("--win", help="Add a win condition (when we beat them)")
    p_update.add_argument("--loss", help="Add a loss condition (when they beat us)")
    p_update.add_argument("--praise", help="Set review praise theme")
    p_update.add_argument("--complaints", help="Set review complaints theme")

    # battlecard
    p_battlecard = sub.add_parser("battlecard", help="Generate a battlecard")
    p_battlecard.add_argument("name", help="Competitor name")

    # report
    sub.add_parser("report", help="Generate full competitive landscape report")

    # matrix
    sub.add_parser("matrix", help="Feature comparison matrix across all competitors")

    # delete
    p_delete = sub.add_parser("delete", help="Remove a competitor")
    p_delete.add_argument("name", help="Competitor name")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    use_json = getattr(args, "json", False)

    command_map = {
        "add": cmd_add,
        "list": cmd_list,
        "view": cmd_view,
        "update": cmd_update,
        "delete": cmd_delete,
        "battlecard": cmd_battlecard,
        "report": cmd_report,
        "matrix": cmd_matrix,
    }

    if not args.command:
        parser.print_help()
        sys.exit(0)

    handler = command_map.get(args.command)
    if not handler:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        sys.exit(1)

    result = handler(args)
    _print_result(result, use_json)

    if "error" in result:
        sys.exit(1)


if __name__ == "__main__":
    main()
