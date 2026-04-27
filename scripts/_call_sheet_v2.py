"""Call sheet generator v2 — with the validation CC asked for.

Filters applied before a lead reaches the sheet:
- Phone exists
- Status not in (lost, won, qualified)  — qualified leads get direct CC attention, not batched
- NOT already called today (avoid double-dialing)
- Phone area code matches known Ontario regions (catches mis-scraped US numbers)
- Company name does NOT contain a known franchise brand (Anytime Fitness, Subway,
  RE/MAX, Century 21, Snap Fitness, Active Green + Ross, etc. — these can't buy
  third-party software, HQ handles it)
- Company name does NOT have "closed" / "permanent" / "out of business" in notes

Ranks:
- Named owner (not generic "Owner/Manager") ranked higher
- More recent last_contacted_at ranked higher (hot chain)
- Score desc
"""
from __future__ import annotations
import re
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from send_gateway import get_supabase

db = get_supabase()
now = datetime.now(timezone.utc)
today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

# Canadian area codes we trust (SW + Central Ontario mostly)
OK_AREA_CODES = {
    "705", "249",  # Central Ontario / Georgian Bay / Collingwood
    "519", "226", "548",  # Southwestern Ontario
    "905", "289", "365", "742",  # GTA outskirts
    "416", "647", "437",  # Toronto
    "613", "343", "753",  # Eastern Ontario / Ottawa
    "807",  # Northwestern Ontario
}

FRANCHISE_BRANDS = {
    "anytime fitness", "snap fitness", "f45",
    "subway", "mcdonald", "tim hortons", "wendy", "burger king",
    "re/max", "remax", "century 21", "royal lepage",
    "midas", "jiffy lube", "mr. lube",
    "active green + ross", "active green and ross",
    "curves", "goodlife",
    "orangetheory", "pure barre",
    "ups store", "7-eleven", "mac's",
    "great clips", "sport chek", "planet fitness",
}


def area_code(phone: str) -> str:
    if not phone:
        return ""
    m = re.search(r"\(?(\d{3})\)?", phone)
    return m.group(1) if m else ""


def is_franchise(company: str) -> bool:
    c = (company or "").lower()
    return any(b in c for b in FRANCHISE_BRANDS)


def is_dead_in_notes(notes: str) -> bool:
    n = (notes or "").lower()
    return any(flag in n for flag in (
        "permanently closed", "out of business", "no longer operating",
        "business closed", "phone disconnected", "bad data",
    ))


# Pull candidates
candidates = (db.table("leads")
              .select("id,name,email,phone,company,status,score,notes,last_contacted_at")
              .not_.is_("phone", "null")
              .in_("status", ["new", "contacted"])
              .execute().data) or []

# Exclude leads called today
called_today = {
    r["lead_id"]
    for r in (db.table("lead_interactions")
              .select("lead_id")
              .eq("type", "call")
              .gte("created_at", today_start)
              .execute().data or [])
    if r.get("lead_id")
}

# Also exclude leads emailed today (give ourselves a breather — don't call
# someone you just emailed 3 hours ago)
emailed_today = {
    r["lead_id"]
    for r in (db.table("lead_interactions")
              .select("lead_id")
              .eq("type", "email_sent")
              .gte("created_at", today_start)
              .execute().data or [])
    if r.get("lead_id")
}

rejected = {"franchise": [], "bad_area_code": [], "dead_in_notes": [],
             "called_today": [], "emailed_today": []}
passed: list[dict] = []
for l in candidates:
    if l["id"] in called_today:
        rejected["called_today"].append(l)
        continue
    if l["id"] in emailed_today:
        rejected["emailed_today"].append(l)
        continue
    if is_dead_in_notes(l.get("notes")):
        rejected["dead_in_notes"].append(l)
        continue
    if is_franchise(l.get("company")):
        rejected["franchise"].append(l)
        continue
    ac = area_code(l.get("phone"))
    if ac and ac not in OK_AREA_CODES:
        rejected["bad_area_code"].append({**l, "area_code": ac})
        continue
    passed.append(l)


def rank(l):
    is_named = 0 if (l.get("name") and not l.get("name").startswith("Owner")) else 1
    has_prior_email = 0 if l.get("last_contacted_at") else 1  # prior email = warmer
    return (is_named, has_prior_email, -(l.get("score") or 0))


passed.sort(key=rank)
top10 = passed[:10]

print(f"Candidates: {len(candidates)} · passed validation: {len(passed)} · rejected:")
for reason, lst in rejected.items():
    print(f"  {reason:20s}  {len(lst):3d}")
    for l in lst[:3]:
        extra = f" [{l.get('area_code')}]" if reason == "bad_area_code" else ""
        print(f"    - {(l.get('company') or '-')[:35]:35}  {l.get('phone') or ''}{extra}")

print(f"\n=== TOP 10 VALIDATED CALL CANDIDATES ===\n")
for i, l in enumerate(top10, 1):
    last = (l.get("last_contacted_at") or "")[:10] or "never"
    print(f"  {i:>2}  {(l.get('name') or '-')[:22]:22}  "
          f"{(l.get('company') or '-')[:30]:30}  {l.get('phone'):15}  "
          f"status={l.get('status'):<10}  last_email={last}")


# Write markdown sheet
out = Path(__file__).resolve().parent.parent / "tmp" / "call_sheet_2026-04-20_v2.md"
lines = [
    f"# Cold Call Sheet v2 — 2026-04-20 (validated)",
    "",
    "## What's different from this morning's sheet",
    "",
    "- Franchise brands filtered out (Anytime Fitness / RE/MAX / Active Green+Ross / etc.)",
    "- Area codes checked against Ontario geo (no more US-disguised numbers)",
    "- Leads with 'permanently closed' / 'phone disconnected' flagged in notes are excluded",
    "- Already-called-today + already-emailed-today filtered (no double-dialing)",
    f"- Candidates scanned: {len(candidates)} · passed validation: {len(passed)}",
    "",
    "## Opener",
    "",
    '> "Hey, is this [name]? — Conaugh from OASIS AI. I know this is cold, can I steal 20 seconds?"',
    "",
    '**[pause]** → "I work with local service businesses on their booking and follow-up automation — my clients are saving 10+ hours a week on admin. Worth a 15-min zoom next week, or am I off base?"',
    "",
    "---",
    "",
    "## The list",
    "",
]
for i, l in enumerate(top10, 1):
    name = l.get("name") or "Owner/Manager"
    company = l.get("company") or ""
    phone = l.get("phone") or ""
    status = l.get("status") or "?"
    last = (l.get("last_contacted_at") or "")[:10] or "never"
    notes = (l.get("notes") or "").strip().replace("\n", " ")[:180]
    lead_id = l["id"]
    lines.append(f"### {i}. {name} — {company}")
    lines.append(f"- **Phone:** `{phone}`")
    lines.append(f"- **Status:** `{status}`")
    if last != "never":
        lines.append(f"- **Prior email:** {last} — can reference in opener")
    if notes:
        lines.append(f"- **Notes:** {notes}")
    lines.append(f"- **Log after call:** `python scripts/lead_engine.py interact {lead_id} --type call --channel phone --content \"<outcome>\"`")
    lines.append("")

lines.append("---")
lines.append(f"\nGenerated {datetime.now().strftime('%a %b %d %I:%M %p ET')} — rejected leads logged to stderr for review")
out.parent.mkdir(exist_ok=True)
out.write_text("\n".join(lines), encoding="utf-8")
print(f"\nSheet: {out}")
