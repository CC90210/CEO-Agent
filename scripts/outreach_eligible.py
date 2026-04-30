"""Pick leads eligible for the next outreach send.

Encodes CC's pacing rule: max 2-3 sends per week per lead, escalating
backoff after each unanswered touch, auto-dormant after 3 silent
attempts so we never spam someone who isn't going to reply.

Cadence (per lead, email channel):
  attempt 1 → next allowed in  3 days
  attempt 2 → next allowed in  7 days  (1 week)
  attempt 3 → next allowed in 14 days  (2 weeks, last try)
  attempt 4 → status auto-flipped to 'dormant', stops sending

Inbound reply at any point resets the counter.

Usage:
  python scripts/outreach_eligible.py --json --limit 20
  python scripts/outreach_eligible.py --mark-dormant   # writes back

Output JSON shape:
  {"eligible": [{lead_id, first_name, company, email, region, attempt_n,
                 next_template_recommended, last_send_iso}, ...],
   "stats": {total_leads, eligible, on_cooldown, dormant_marked,
             never_contacted_no_email}}
"""
from __future__ import annotations
import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from supabase_tool import get_client, load_env  # noqa: E402
from region_inference import infer_region  # noqa: E402
from name_utils import PLACEHOLDER_FIRST_NAMES, strip_honorifics  # noqa: E402

# Days between sends, indexed by attempt-count BEFORE this send.
CADENCE_DAYS: dict[int, int] = {
    0: 0,    # first touch — eligible if never contacted
    1: 3,    # 2nd send: 3 days after 1st
    2: 7,    # 3rd send: 1 week after 2nd
    3: 14,   # 4th send blocked → auto-dormant
}
MAX_ATTEMPTS = 3
DORMANT_AFTER = MAX_ATTEMPTS  # 3 unanswered touches → dormant

TEMPLATE_BY_ATTEMPT = {
    0: "OASIS Welcome",      # first touch
    1: "OASIS Value Add",    # follow-up
    2: "OASIS CTA",          # final ask
}


def _is_real_first_name(name: str) -> bool:
    if not name:
        return False
    cleaned = strip_honorifics(name.strip())
    first = cleaned.split()[0] if cleaned else ""
    return bool(first) and first.lower() not in PLACEHOLDER_FIRST_NAMES


def _has_email(lead: dict) -> bool:
    e = (lead.get("email") or "").strip()
    return "@" in e and "." in e.split("@")[-1]


def _outbound_count_30d(db, lead_id: str) -> tuple[int, str | None]:
    """Return (count of outbound emails in last 30d, ISO ts of last send)."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    rows = (db.table("lead_interactions")
            .select("created_at,type,channel")
            .eq("lead_id", lead_id)
            .eq("channel", "email")
            .eq("type", "email_sent")
            .gte("created_at", cutoff)
            .order("created_at", desc=True)
            .execute()).data or []
    last = rows[0]["created_at"] if rows else None
    return len(rows), last


def _has_inbound_reply_30d(db, lead_id: str) -> bool:
    """True if the lead has replied (inbound) in the last 30 days."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    rows = (db.table("lead_interactions")
            .select("id")
            .eq("lead_id", lead_id)
            .eq("channel", "email")
            .eq("type", "email_received")
            .gte("created_at", cutoff)
            .limit(1)
            .execute()).data or []
    return len(rows) > 0


def evaluate(limit: int = 50, mark_dormant: bool = False) -> dict:
    db = get_client(load_env())
    leads = (db.table("leads")
             .select("id,name,company,email,phone,notes,status,last_contacted_at")
             .in_("status", ["new", "contacted", "qualified"])
             .limit(2000)
             .execute()).data or []

    eligible: list[dict] = []
    on_cooldown: list[dict] = []
    dormant_marked: list[str] = []
    no_email_or_name: int = 0

    now = datetime.now(timezone.utc)

    for L in leads:
        if not _has_email(L) or not L.get("company") or not _is_real_first_name(L.get("name") or ""):
            no_email_or_name += 1
            continue

        attempt_n, last_send_iso = _outbound_count_30d(db, L["id"])

        # Auto-dormant after MAX_ATTEMPTS with no reply
        if attempt_n >= DORMANT_AFTER and not _has_inbound_reply_30d(db, L["id"]):
            if mark_dormant:
                try:
                    db.table("leads").update({
                        "status": "dormant",
                        "updated_at": now.isoformat(),
                        "notes": (L.get("notes") or "") + (
                            f"\n[{now.date()}] Auto-flipped to dormant after "
                            f"{attempt_n} unanswered email touches."
                        ),
                    }).eq("id", L["id"]).execute()
                    dormant_marked.append(L["id"])
                except Exception as exc:  # noqa: BLE001
                    print(f"[outreach_eligible] dormant flip failed for {L['id']}: {exc}",
                          file=sys.stderr)
            continue

        # Cooldown check: days since last send must exceed CADENCE_DAYS[attempt_n]
        required_days = CADENCE_DAYS.get(attempt_n, CADENCE_DAYS[max(CADENCE_DAYS)])
        if last_send_iso:
            last_send_dt = datetime.fromisoformat(last_send_iso.replace("Z", "+00:00"))
            days_since = (now - last_send_dt).total_seconds() / 86400.0
            if days_since < required_days:
                on_cooldown.append({
                    "lead_id": L["id"],
                    "company": L.get("company"),
                    "attempt_n": attempt_n,
                    "days_since": round(days_since, 1),
                    "required_days": required_days,
                })
                continue

        first = strip_honorifics((L.get("name") or "").strip()).split()[0]
        eligible.append({
            "lead_id": L["id"],
            "first_name": first,
            "company": L["company"],
            "email": L["email"],
            "region": infer_region(L),
            "attempt_n": attempt_n,
            "next_template_recommended": TEMPLATE_BY_ATTEMPT.get(attempt_n, "OASIS CTA"),
            "last_send_iso": last_send_iso,
        })

    eligible.sort(key=lambda r: (r["attempt_n"], r["last_send_iso"] or ""))
    return {
        "eligible": eligible[:limit],
        "stats": {
            "total_leads_screened": len(leads),
            "eligible": len(eligible),
            "on_cooldown": len(on_cooldown),
            "dormant_marked": len(dormant_marked),
            "no_email_or_name": no_email_or_name,
        },
        "cadence_days": CADENCE_DAYS,
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--json", action="store_true", help="Output JSON")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--mark-dormant", action="store_true",
                   help="Auto-flip status='dormant' for leads past MAX_ATTEMPTS")
    args = p.parse_args()
    result = evaluate(limit=args.limit, mark_dormant=args.mark_dormant)
    if args.json:
        print(json.dumps(result, indent=2, default=str))
        return
    print(f"=== OUTREACH ELIGIBILITY ===")
    s = result["stats"]
    print(f"Screened: {s['total_leads_screened']} leads (status in new/contacted/qualified)")
    print(f"  Eligible now:        {s['eligible']}")
    print(f"  On cooldown:         {s['on_cooldown']}")
    print(f"  Auto-dormant:        {s['dormant_marked']}")
    print(f"  No email / no name:  {s['no_email_or_name']}")
    print()
    print(f"Cadence: {CADENCE_DAYS}")
    print()
    print(f"Top {min(args.limit, len(result['eligible']))} eligible:")
    for e in result["eligible"][:args.limit]:
        print(f"  attempt {e['attempt_n']} | {e['first_name'][:15]:15} | "
              f"{e['company'][:30]:30} | {e['region']:25} | "
              f"-> {e['next_template_recommended']}")


if __name__ == "__main__":
    main()
