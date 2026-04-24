"""Post-call updates 2026-04-20 (late afternoon):
- URGENT: send personable follow-up to Emon at Tremont Cafe
- Tremont Cafe → qualified (called back, engaged conversation)
- [REDACTED] Wellness + Garden Holistics → log no-answer calls
- Iron Skillet → fix the Wasaga/Collingwood data mix-up
"""
from __future__ import annotations
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from send_gateway import get_supabase, send as gateway_send

db = get_supabase()
now_iso = datetime.now(timezone.utc).isoformat()
today = now_iso[:10]

# ============================================================
# 1. TREMONT CAFE — Emon email + qualify
# ============================================================
tremont = db.table("leads").select("id,name,email,notes").eq("company", "The Tremont Cafe").execute().data or []
if not tremont:
    print("[ERROR] Tremont Cafe lead missing — aborting Tremont block")
else:
    t = tremont[0]
    follow_up = (datetime.now(timezone.utc) + timedelta(days=6)).date().isoformat()

    subject = "Great chat, Emon — quick recap from our call"
    body = (
        "Hey Emon,\n\n"
        "Really appreciate you calling back — genuinely the best kind of "
        "conversation to have on a Monday afternoon.\n\n"
        "Quick recap so nothing falls through the cracks:\n\n"
        "- You're open to exploring how AI automation could fit Tremont's "
        "day-to-day — reservations, ordering, customer follow-ups, whichever "
        "bits feel most broken right now\n"
        "- I'm going to put together a short tailored walkthrough for a "
        "cafe / restaurant operation specifically, so you can see what "
        "\"done\" looks like before we spend more of your time\n"
        "- I'll ring you back in about a week to talk through it and see if "
        "there's one specific workflow worth piloting\n\n"
        "No pressure in the meantime — if anything shifts on your end "
        "(you want to push it out, pull it in, change direction), just "
        "reply and we'll adjust.\n\n"
        "Looking forward to it.\n\n"
        "Conaugh\n"
        "OASIS AI Solutions\n"
        "oasisai.work"
    )
    r = gateway_send(
        channel="email",
        agent_source="manual_cc",
        to_email=t["email"],
        lead_id=t["id"],
        subject=subject,
        body_text=body,
        brand="oasis",
        intent="commercial",
        metadata={
            "campaign": "tremont_post_call_followup",
            "contact_name": "Emon",
            "call_context": "inbound_callback_from_earlier_voicemail",
        },
    )
    print(f"[TREMONT email] status={r.get('status')} reason={r.get('reason')}")

    # Qualify the lead
    new_notes = (t.get("notes") or "").strip() + (
        f"\n\n[{today}] INBOUND CALLBACK — Emon called back after our earlier VM. "
        "Great conversation. Open to exploring AI automation for the cafe "
        "(reservations / ordering / customer follow-ups). CC to send tailored "
        "5-min walkthrough, then ring back in ~1 week to pick a specific workflow "
        f"to pilot. next_followup_at={follow_up}. "
        "Contact: Emon (not Bev Drexler as originally listed)."
    )
    db.table("leads").update({
        "status": "qualified",
        "score": 70,
        "notes": new_notes,
        "next_followup_at": follow_up,
        "last_contacted_at": now_iso,
        "updated_at": now_iso,
    }).eq("id", t["id"]).execute()

    db.table("lead_interactions").insert({
        "lead_id": t["id"],
        "type": "call",
        "channel": "phone",
        "subject": "Inbound callback — Emon — warm qualify",
        "content": (
            "Emon called back after our earlier VM attempt. Engaged conversation "
            "about AI automation fit for Tremont Cafe. Agreed to receive a tailored "
            f"5-min walkthrough + follow-up call in ~1 week ({follow_up}). "
            "Status -> qualified, score -> 70."
        ),
        "agent_source": "manual_cc",
        "metadata": {
            "outcome": "inbound_callback_qualified",
            "contact_name": "Emon",
            "direction": "inbound",
        },
        "created_at": now_iso,
    }).execute()
    print(f"[TREMONT updated] -> qualified, score=70, next_followup={follow_up}, contact=Emon")

# ============================================================
# 2. CEDARWOOD WELLNESS — log no-answer
# ============================================================
cw = db.table("leads").select("id,notes").eq("company", "[REDACTED]").execute().data or []
for l in cw:
    n = (l.get("notes") or "").strip() + f"\n[{today}] CALL — no answer. Retry next session."
    db.table("leads").update({
        "notes": n,
        "last_contacted_at": now_iso,
        "updated_at": now_iso,
    }).eq("id", l["id"]).execute()
    db.table("lead_interactions").insert({
        "lead_id": l["id"],
        "type": "call",
        "channel": "phone",
        "subject": "No answer",
        "content": "Attempted call, no pickup. Did not leave VM this attempt.",
        "agent_source": "manual_cc",
        "metadata": {"outcome": "no_answer"},
        "created_at": now_iso,
    }).execute()
    print("[call logged] [REDACTED] Wellness — no answer")

# ============================================================
# 3. GARDEN HOLISTICS — log no-answer
# ============================================================
gh = db.table("leads").select("id,notes").eq("company", "Garden Holistics").execute().data or []
for l in gh:
    n = (l.get("notes") or "").strip() + f"\n[{today}] CALL — no answer. Retry next session."
    db.table("leads").update({
        "notes": n,
        "last_contacted_at": now_iso,
        "updated_at": now_iso,
    }).eq("id", l["id"]).execute()
    db.table("lead_interactions").insert({
        "lead_id": l["id"],
        "type": "call",
        "channel": "phone",
        "subject": "No answer",
        "content": "Attempted call, no pickup.",
        "agent_source": "manual_cc",
        "metadata": {"outcome": "no_answer"},
        "created_at": now_iso,
    }).execute()
    print("[call logged] Garden Holistics — no answer")

# ============================================================
# 4. IRON SKILLET — fix the Wasaga/Collingwood data mix-up
# ============================================================
skillet = db.table("leads").select("id,name,email,notes").eq("company", "The Iron Skillet").execute().data or []
for l in skillet:
    fixed_notes = (l.get("notes") or "").strip() + (
        f"\n[{today}] DATA CORRECTION — This lead is for The Iron Skillet COLLINGWOOD. "
        "Phone (705) 429-1144 is correct for the Collingwood location. HOWEVER the "
        "email on file ([redacted-lead-email]) belongs to the WASAGA "
        "location — they used to be franchised together but are NOW SEPARATE "
        "businesses. The Collingwood email needs to be re-sourced before any "
        f"send. Status: email marked as WASAGA_WRONG_LOC pending verification. "
        f"\n[{today}] CALL — a girl (likely front-of-house) answered, owner not "
        "reachable at that moment. Not much to go on."
    )
    db.table("leads").update({
        "email": None,  # null it out to prevent accidental send to the wrong location
        "notes": fixed_notes,
        "last_contacted_at": now_iso,
        "updated_at": now_iso,
    }).eq("id", l["id"]).execute()
    db.table("lead_interactions").insert({
        "lead_id": l["id"],
        "type": "note",
        "channel": "email",
        "subject": "Data correction — Wasaga/Collingwood mix-up",
        "content": (
            "Email on file ([redacted-lead-email]) belongs to the "
            "WASAGA location. Collingwood Iron Skillet is a separate business. "
            "Email nulled out pending correct Collingwood address source. Phone "
            "(705) 429-1144 is correct for Collingwood."
        ),
        "agent_source": "manual_cc",
        "metadata": {"outcome": "data_correction", "reason": "email_wrong_location"},
        "created_at": now_iso,
    }).execute()
    db.table("lead_interactions").insert({
        "lead_id": l["id"],
        "type": "call",
        "channel": "phone",
        "subject": "Reached front-of-house",
        "content": "A girl answered, likely front-of-house. Owner not available; not much to act on.",
        "agent_source": "manual_cc",
        "metadata": {"outcome": "reached_gatekeeper"},
        "created_at": now_iso,
    }).execute()
    print("[iron skillet] email nulled (wrong location), notes updated, call logged")

# Final pipeline
r = db.rpc("exec_sql", {"sql_query": "SELECT status, count(*) FROM leads GROUP BY status ORDER BY status"}).execute()
rows = (r.data or {}).get("rows") if isinstance(r.data, dict) else None
print(f"\nPipeline: {rows}")
