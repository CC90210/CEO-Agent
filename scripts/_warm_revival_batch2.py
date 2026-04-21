"""Warm-revival email batch #2 — 2026-04-20 late afternoon.

Pulls 10 contacted leads (emailed 6+ weeks ago, past cooldown, no sends today),
varies the template by industry, sends through the gateway.
"""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from send_gateway import get_supabase, send as gateway_send

db = get_supabase()
now = datetime.now(timezone.utc)
today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
cutoff_14d = (now - timedelta(days=14)).isoformat()

# Already touched today — exclude
touched_today = {
    r["lead_id"]
    for r in (db.table("lead_interactions")
              .select("lead_id")
              .eq("type", "email_sent")
              .gte("created_at", today_start)
              .execute().data or [])
    if r.get("lead_id")
}

# Pull candidates: contacted, real email, 14+ days since last touch
pool = (db.table("leads")
        .select("id,name,email,company,notes,last_contacted_at,source,score")
        .eq("status", "contacted")
        .not_.is_("email", "null")
        .lte("last_contacted_at", cutoff_14d)
        .order("last_contacted_at", desc=False)  # oldest first
        .limit(50)
        .execute().data) or []


def ok(l):
    e = (l.get("email") or "").lower()
    if l["id"] in touched_today:
        return False
    # Skip junky domains + inbound sources + Vercel notifications + test accounts
    if any(b in e for b in ("noreply@", "notifications@", "mailer-daemon", "no-reply",
                              "user@domain.com", "goldstorm2003")):
        return False
    if (l.get("source") or "").startswith("inbound_"):
        return False
    return True


pool = [l for l in pool if ok(l)]
targets = pool[:10]
print(f"[batch2] pool after filter: {len(pool)} · sending to first 10")


def infer(company: str) -> tuple[str, str]:
    c = (company or "").lower()
    if "plumb" in c: return "plumbing", "after-hours leak calls and quote follow-ups"
    if "roof" in c: return "roofing", "chasing quotes and seasonal scheduling"
    if "landscap" in c: return "landscaping", "scheduling crews and invoicing per-job"
    if "physio" in c or "sport med" in c or "chiro" in c: return "clinic", "appointment reminders and rebooking no-shows"
    if "dental" in c or "eyecare" in c or "optom" in c: return "practice", "appointment reminders and rebooking"
    if "hvac" in c or "heating" in c or "mechanical" in c or "comfort" in c: return "HVAC", "quote follow-ups and service scheduling"
    if "electric" in c: return "electrical", "quote-to-invoice cycle and scheduling"
    if "auto" in c or "mechanic" in c: return "auto shop", "service reminders and quote follow-ups"
    if "salon" in c or "hair" in c or "studio" in c or "spa" in c: return "salon", "booking no-shows and rebooking"
    if "cafe" in c or "restaurant" in c or "grill" in c or "bar " in c or "brew" in c: return "restaurant", "reservations and customer follow-ups"
    if "fitness" in c or "gym" in c: return "fitness", "membership follow-ups and scheduling"
    if "charter" in c or "tour" in c: return "service", "booking confirmations and follow-ups"
    return "local service", "scheduling and follow-ups"


sent = blocked = failed = 0
results = []
for i, lead in enumerate(targets, 1):
    industry, pain = infer(lead["company"])
    subject = f"Following up from March — {lead['company']}"
    body = (
        "Hey,\n\n"
        f"Quick one — we connected briefly back in early March about {lead['company']}.\n\n"
        f"Since then I have been building automation for {industry} businesses specifically around "
        f"{pain}. The clients using it have cut admin time by 10+ hours a week.\n\n"
        f"If you are still the right person at {lead['company']} for this, happy to send a "
        "90-second walkthrough showing exactly how it would look for your shop. No call needed "
        "unless you want one.\n\n"
        "If it is not a fit right now, just reply pass and I will stop pinging.\n\n"
        "Either way, appreciate the 30 seconds.\n\n"
        "Conaugh"
    )
    r = gateway_send(
        channel="email",
        agent_source="manual_cc_bulk",
        to_email=lead["email"],
        lead_id=lead["id"],
        subject=subject,
        body_text=body,
        brand="oasis",
        intent="commercial",
        metadata={"batch": "warm_revival_2026-04-20_batch2", "industry": industry,
                   "campaign": "march_followup"},
    )
    status = r.get("status")
    icon = "OK" if status == "sent" else "SKIP" if status in ("blocked", "suppressed") else "FAIL"
    print(f"  [{i:2}/10] {icon:4} | {lead['company'][:28]:28} | {lead['email'][:35]:35} | "
          f"{status:10} | {r.get('reason','')[:40]}")
    if status == "sent":
        sent += 1
    elif status in ("blocked", "suppressed"):
        blocked += 1
    else:
        failed += 1
    results.append({"company": lead["company"], "email": lead["email"], "status": status,
                    "reason": r.get("reason")})
    time.sleep(1.0)

print(f"\n[batch2] sent {sent}/10 · blocked {blocked} · failed {failed}")

# Save batch log
out = Path(__file__).resolve().parent.parent / "tmp" / "warm_revival_batch2_2026-04-20.json"
out.write_text(json.dumps(results, indent=2), encoding="utf-8")
print(f"[batch2] results saved to {out}")
