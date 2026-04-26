"""One-shot 2026-04-20 post-call update:
- Suppress CC's test accounts (goldstorm2003@gmail.com) in CASL list
- Delete the Contractorslm test lead from CRM
- Mark Basque Landscaping as QUALIFIED (warm lead, 1-week follow-up)
- Delete Wasaga Beach Brewing (permanently closed business)
- Mark Rooted Family Chiropractic as LOST (bad data — US-based, dead phone)
- Mark Anytime Fitness Collingwood as LOST (franchise, HQ handles automation)
- Log call interactions for Collingwood Charters, Peak Living, Tremont Cafe
"""
from __future__ import annotations
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from send_gateway import get_supabase
from casl_compliance import add_suppression

db = get_supabase()
now_iso = datetime.now(timezone.utc).isoformat()
today = now_iso[:10]

# 1. Suppress CC's test accounts — never email them again.
for e in ["goldstorm2003@gmail.com"]:
    add_suppression(e, reason="cc_test_account_do_not_email")
    print(f"[suppress] {e} added to CASL suppression list.")

# 2. Delete the Contractorslm test lead.
test_lead = db.table("leads").select("id,name,email").eq("email", "goldstorm2003@gmail.com").execute().data or []
for tl in test_lead:
    db.table("lead_interactions").delete().eq("lead_id", tl["id"]).execute()
    db.table("leads").delete().eq("id", tl["id"]).execute()
    print(f"[delete] test lead {tl['name']} ({tl['email']}) removed from CRM")

# 3. Basque Landscaping → QUALIFIED (THE warm win).
basque = db.table("leads").select("id,name,notes").eq("company", "Basque Landscaping").execute().data or []
if basque:
    lead_id = basque[0]["id"]
    follow_up = (datetime.now(timezone.utc) + timedelta(days=6)).date().isoformat()
    qual_notes = (basque[0].get("notes") or "").strip() + "\n\n" + (
        f"[{today}] CALL — WARM/QUALIFIED LEAD\n"
        "Called Jonathan Hutton, great conversation. He is interested in a custom "
        "software build for Basque Landscaping — similar model to Gritly (he owns "
        "the software, tailored to his use cases).\n"
        "Angle that landed: 15-year exit value — a custom software asset makes "
        "the business sell for significantly more.\n"
        "He is slammed for the next 3 weeks but open to a 15-min walkthrough. "
        "CC said we can compress into 15 min.\n"
        "Next step: ring back in ~1 week (not 3 — too long). Keep touching him, "
        "stay top of mind.\n"
        "Status bumped to QUALIFIED. Treat as high priority."
    )
    db.table("leads").update({
        "status": "qualified",
        "score": 75,
        "notes": qual_notes,
        "next_followup_at": follow_up,
        "last_contacted_at": now_iso,
        "updated_at": now_iso,
    }).eq("id", lead_id).execute()
    db.table("lead_interactions").insert({
        "lead_id": lead_id,
        "type": "call",
        "channel": "phone",
        "subject": "Discovery call — custom software build (warm)",
        "content": (
            "Interested in custom software (Gritly-style, owned asset). "
            "15-yr exit angle landed. 3-week busy window, CC to re-call "
            f"in ~1 week. Status -> qualified, score -> 75, "
            f"next_followup_at={follow_up}"
        ),
        "agent_source": "manual_cc",
        "metadata": {
            "outcome": "warm_qualified",
            "tags": ["custom_software", "exit_value_angle"],
            "follow_up_window": "1_week",
        },
        "created_at": now_iso,
    }).execute()
    print(f"[QUALIFIED] Basque Landscaping -> qualified, score=75, next_followup_at={follow_up}")

# 4. Delete Wasaga Beach Brewing (permanently closed).
wb = db.table("leads").select("id,name,company").eq("company", "Wasaga Beach Brewing Co.").execute().data or []
for l in wb:
    db.table("lead_interactions").delete().eq("lead_id", l["id"]).execute()
    db.table("leads").delete().eq("id", l["id"]).execute()
    print(f"[delete] {l['company']} — permanently closed, removed from CRM")

# 5. Rooted Family Chiropractic → LOST (bad data).
rooted = db.table("leads").select("id,name,notes").eq("company", "Rooted Family Chiropractic").execute().data or []
for l in rooted:
    bad_notes = (l.get("notes") or "").strip() + (
        f"\n[{today}] LOST — BAD DATA: 3 US-based locations, 705 phone "
        "disconnected. Attempted call, failed. Source data not trustworthy."
    )
    db.table("leads").update({
        "status": "lost",
        "notes": bad_notes,
        "updated_at": now_iso,
    }).eq("id", l["id"]).execute()
    db.table("lead_interactions").insert({
        "lead_id": l["id"],
        "type": "call",
        "channel": "phone",
        "subject": "Call failed — phone disconnected",
        "content": (
            "Attempted call, phone number disconnected. Business is US-based "
            "(3 locations, none local). Bad lead data."
        ),
        "agent_source": "manual_cc",
        "metadata": {"outcome": "bad_data_phone_dead"},
        "created_at": now_iso,
    }).execute()
    print("[lost] Rooted Family Chiropractic -> bad data")

# 6. Anytime Fitness → LOST (franchise).
af = db.table("leads").select("id,name,notes").eq("company", "Anytime Fitness Collingwood").execute().data or []
for l in af:
    notes2 = (l.get("notes") or "").strip() + (
        f"\n[{today}] LOST — franchise. Edward confirmed HQ provides all "
        "automation; local franchisees cannot buy third-party. Structural "
        "mismatch, not CC."
    )
    db.table("leads").update({
        "status": "lost",
        "notes": notes2,
        "last_contacted_at": now_iso,
        "updated_at": now_iso,
    }).eq("id", l["id"]).execute()
    db.table("lead_interactions").insert({
        "lead_id": l["id"],
        "type": "call",
        "channel": "phone",
        "subject": "Franchise — no fit",
        "content": (
            "Spoke with Edward. Franchise model — HQ handles automation "
            "centrally. Local franchisees cannot buy third-party. Marking lost."
        ),
        "agent_source": "manual_cc",
        "metadata": {"outcome": "franchise_bad_fit"},
        "created_at": now_iso,
    }).execute()
    print("[lost] Anytime Fitness -> franchise, no fit")

# 7. Log VM / gatekept / no-answer calls.
vm_calls = [
    ("Collingwood Charters", "no_answer",
     "No pickup, did not leave voicemail this attempt. Retry next session."),
    ("Peak Living Inc.", "gatekept",
     "Spoke to Tom McCrae's assistant — asked to call back another time. "
     "Will retry to reach Tom directly."),
    ("The Tremont Cafe", "voicemail_left",
     "Went to voicemail, left message. Retry next call session."),
]
for company, outcome, content in vm_calls:
    leads = db.table("leads").select("id,name,notes").eq("company", company).execute().data or []
    for l in leads:
        note_line = f"\n[{today}] CALL — {outcome}. {content}"
        db.table("leads").update({
            "notes": (l.get("notes") or "").strip() + note_line,
            "last_contacted_at": now_iso,
            "updated_at": now_iso,
        }).eq("id", l["id"]).execute()
        db.table("lead_interactions").insert({
            "lead_id": l["id"],
            "type": "call",
            "channel": "phone",
            "subject": outcome,
            "content": content,
            "agent_source": "manual_cc",
            "metadata": {"outcome": outcome},
            "created_at": now_iso,
        }).execute()
        print(f"[call logged] {company} — {outcome}")

# Pipeline snapshot
r = db.rpc("exec_sql", {"sql_query": "SELECT status, count(*) FROM leads GROUP BY status ORDER BY status"}).execute()
rows = (r.data or {}).get("rows") if isinstance(r.data, dict) else None
print("\nPipeline after updates:", rows)
