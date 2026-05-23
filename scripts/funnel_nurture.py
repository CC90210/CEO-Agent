"""
Funnel Lead Nurture Engine
Sends automated follow-up emails to funnel leads at Day 2 and Day 5.
Called daily by scheduler.py. Notifies CC via Telegram with a digest.

Usage:
    python scripts/funnel_nurture.py run          # Execute nurture sequence
    python scripts/funnel_nurture.py stats         # Show lead stats
    python scripts/funnel_nurture.py --json run    # JSON output for agents
"""

from __future__ import annotations

import os
import sys
import json
from datetime import datetime, timezone
from pathlib import Path

# Load .env.agents
env_path = Path(__file__).resolve().parent.parent / ".env.agents"
if env_path.exists():
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

# Physical send + CASL + cooldown + daily cap + ledger logging all live in
# send_gateway (2026-04-20 rewire). This engine only owns the Day-2/Day-5
# timing logic + the HTML template bodies.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from name_utils import safe_first_name


def get_supabase():
    url = os.environ.get("BRAVO_SUPABASE_URL", "")
    key = os.environ.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        print("Missing BRAVO_SUPABASE_URL or BRAVO_SUPABASE_SERVICE_ROLE_KEY")
        sys.exit(1)
    try:
        from supabase import create_client
        return create_client(url, key)
    except ImportError:
        print("supabase package not installed: pip install supabase")
        sys.exit(1)


def send_email(to_email: str, subject: str, html: str, lead_id: str | None = None) -> bool:
    """Nurture send (Day 2 / Day 5). REWIRED 2026-04-20 → send_gateway.

    Gateway handles CASL suppression, footer, List-Unsubscribe, cooldown,
    daily cap, lead_interactions, email_log mirror. Returns True on send,
    False on any block / error. The run_nurture loop still updates
    follow_up_count so downstream display state stays correct.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from send_gateway import send as gateway_send
    # Generate a text fallback from the HTML for clients that drop HTML.
    import re
    text_fallback = re.sub(r"<[^>]+>", " ", html)
    text_fallback = re.sub(r"\s+", " ", text_fallback).strip()[:4000]

    gw = gateway_send(
        channel="email",
        agent_source="funnel_nurture",
        to_email=to_email,
        lead_id=lead_id,
        subject=subject,
        body_text=text_fallback,
        body_html=html,
        brand="oasis",
        intent="commercial",
        metadata={"source": "funnel_nurture"},
    )
    if gw.get("status") != "sent":
        print(
            f"[funnel_nurture] send blocked/failed for {to_email}: "
            f"{gw.get('status')} — {gw.get('reason')}",
            file=sys.stderr,
        )
        return False
    return True


def send_telegram(message: str):
    """Unified Telegram via notify.py — uses the same path as every other engine.

    V2 2026-04-11: migrated from raw urllib.request to notify.notify() so
    category filtering, timeout, and error visibility are consistent across
    the codebase. Falls back to raw HTTP only if notify import fails.
    """
    try:
        # Local import to avoid a hard dependency when running in isolation
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from notify import notify as _notify
        _notify(message, category="email", force=True)  # force=True bypasses category block
        return
    except Exception:
        pass

    # Fallback: original raw HTTP path (kept as safety net)
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_ALLOWED_USERS", "").split(",")[0].strip()
    if not token or not chat_id:
        return

    import urllib.request
    data = json.dumps({
        "chat_id": chat_id,
        "text": message[:4096],
        "parse_mode": "HTML",
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=5)  # V2: 15s -> 5s
    except Exception as e:
        print(f"Telegram notify failed: {e}", file=sys.stderr)


# --- Email template helpers ---

GMAIL_USER = "conaugh@oasisai.work"

def _booking_link() -> str:
    """Return booking link from env, or fallback to mailto reply."""
    link = os.environ.get("BOOKING_LINK", "") or os.environ.get("BOOKING_MEET_LINK", "")
    if link:
        return link
    return f"mailto:{GMAIL_USER}?subject=Book%20My%20Free%20Strategy%20Call"


def _email_wrapper(content: str) -> str:
    """Wrap email content in branded OASIS AI HTML template."""
    return f"""
    <div style="background:#0a0a0a;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif">
      <!-- Header -->
      <div style="background:#111;padding:20px 24px;text-align:center;border-bottom:2px solid #e8c547">
        <span style="color:#faf9f5;font-size:20px;font-weight:700;letter-spacing:1px">OASIS</span>
        <span style="color:#e8c547;font-size:20px;font-weight:700;letter-spacing:1px"> AI</span>
        <p style="color:#666;font-size:11px;margin:4px 0 0;text-transform:uppercase;letter-spacing:2px">Automation That Works For You</p>
      </div>
      <!-- Body -->
      <div style="padding:32px 24px">
        <div style="max-width:520px;margin:0 auto">
          {content}
        </div>
      </div>
      <!-- Footer -->
      <div style="background:#111;padding:20px 24px;text-align:center;border-top:1px solid #222">
        <p style="color:#888;font-size:13px;margin:0 0 4px"><strong>Conaugh McKenna</strong> | Founder, OASIS AI Solutions</p>
        <p style="color:#555;font-size:11px;margin:0">Collingwood, ON &middot; <a href="https://www.instagram.com/konamakana" style="color:#e8c547;text-decoration:none">@konamakana</a></p>
      </div>
    </div>"""


def _cta_button(text: str, href: str = "") -> str:
    """Render a branded CTA button."""
    link = href or _booking_link()
    return f"""<p style="text-align:center;margin:28px 0">
              <a href="{link}" style="display:inline-block;background:#e8c547;color:#0a0a0a;padding:14px 28px;border-radius:8px;text-decoration:none;font-weight:700;font-size:15px">{text}</a>
            </p>"""


# --- Follow-up email templates ---

def day2_email(name: str, interests: list, data: dict) -> tuple[str, str]:
    first = safe_first_name(name.split(" ")[0] if name else "", fallback="there")

    if "ai" in interests:
        subject = f"{first}, your AI audit is ready"
        content = f"""
            <h2 style="color:#faf9f5;margin:0 0 16px">Hey {first},</h2>
            <p style="color:#ccc;line-height:1.7">I just finished reviewing <strong style="color:#faf9f5">{data.get('business_name', 'your business')}</strong>.</p>
            <p style="color:#ccc;line-height:1.7">Here's what I found: there are <strong style="color:#faf9f5">at least 3 workflows</strong> you're doing manually right now that could be fully automated — saving you an estimated 10-15 hours per week.</p>
            <p style="color:#ccc;line-height:1.7">I put together a quick breakdown. Want me to send it over? Just reply to this email{' or DM me on Instagram @' + data.get('instagram_handle', '') if data.get('instagram_handle') else ''}.</p>
            <p style="color:#ccc;line-height:1.7">Or if you're ready to talk, grab a free 15-min slot:</p>
            {_cta_button("Book Your Free Strategy Call")}
            <p style="color:#999;line-height:1.7;font-size:14px">No pressure, no pitch — just the analysis.</p>"""
    elif "music" in interests:
        subject = f"{first}, quick question about your event"
        content = f"""
            <h2 style="color:#faf9f5;margin:0 0 16px">Hey {first},</h2>
            <p style="color:#ccc;line-height:1.7">Just following up on your {data.get('event_type', 'event')} inquiry{' for ' + data.get('event_date', '') if data.get('event_date') else ''}.</p>
            <p style="color:#ccc;line-height:1.7">I've got some availability opening up and wanted to make sure I don't miss your date. What's the best way to chat — email, DM, or a quick call?</p>
            <p style="color:#ccc;line-height:1.7">I'll put together a vibe proposal based on what you told me{' (' + data.get('music_vibe', '') + ')' if data.get('music_vibe') else ''} so you can see exactly what the set would feel like.</p>
            <p style="color:#ccc;line-height:1.7"><strong style="color:#faf9f5">Just reply to this email</strong> and we'll get it locked in.</p>"""
    else:
        subject = f"{first}, let's book your strategy session"
        content = f"""
            <h2 style="color:#faf9f5;margin:0 0 16px">Hey {first},</h2>
            <p style="color:#ccc;line-height:1.7">I wanted to reach out about your free brand strategy session.</p>
            <p style="color:#ccc;line-height:1.7">You mentioned your goal is to <strong style="color:#faf9f5">{data.get('brand_goal', 'grow your brand')}</strong>{' targeting ' + data.get('audience', '') if data.get('audience') else ''} — I've got some specific ideas that could move the needle fast.</p>
            <p style="color:#ccc;line-height:1.7">Just reply with a time that works this week and I'll block 15 minutes for us. Completely free, no strings.</p>
            {_cta_button("Book Your Free Session")}"""

    return subject, _email_wrapper(content)


def day5_email(name: str, interests: list, data: dict) -> tuple[str, str]:
    first = safe_first_name(name.split(" ")[0] if name else "", fallback="there")

    if "ai" in interests:
        subject = f"Last call, {first} — your AI audit expires soon"
        content = f"""
            <h2 style="color:#faf9f5;margin:0 0 16px">{first},</h2>
            <p style="color:#ccc;line-height:1.7">Quick heads up — I did the full audit for <strong style="color:#faf9f5">{data.get('business_name', 'your business')}</strong> and it's sitting in my drafts waiting for you.</p>
            <p style="color:#ccc;line-height:1.7">I can only keep these personalized for so long before I move on to the next batch.</p>
            {_cta_button("Book Your Free Audit Call")}
            <p style="color:#999;line-height:1.7;font-size:14px">Either way, no hard feelings. Just didn't want you to miss something that could genuinely save you hours every week.</p>"""
    elif "music" in interests:
        subject = f"{first} — still looking for a DJ?"
        content = f"""
            <h2 style="color:#faf9f5;margin:0 0 16px">Hey {first},</h2>
            <p style="color:#ccc;line-height:1.7">Just checking in — my calendar is filling up and I want to make sure your event doesn't slip through the cracks.</p>
            <p style="color:#ccc;line-height:1.7">If you've already found someone, no worries at all. But if you're still looking, let me know and I'll lock your date in before it's gone.</p>
            {_cta_button("Book a Quick Call")}"""
    else:
        subject = f"{first}, your free session is still available"
        content = f"""
            <h2 style="color:#faf9f5;margin:0 0 16px">{first},</h2>
            <p style="color:#ccc;line-height:1.7">Your free brand strategy session is still on the table. I only do a few of these a week, so I wanted to make sure you didn't forget.</p>
            <p style="color:#ccc;line-height:1.7">15 minutes, zero pitch, and you'll walk away with at least one thing you can implement immediately.</p>
            {_cta_button("Book Your Free Session")}"""

    return subject, _email_wrapper(content)


def run_nurture(as_json: bool = False):
    sb = get_supabase()
    now = datetime.now(timezone.utc)
    results = {"day2_sent": [], "day5_sent": [], "errors": []}

    # Get leads that need follow-up
    leads = sb.table("funnel_leads").select("*").in_(
        "status", ["new", "nurturing"]
    ).execute().data

    for lead in leads:
        created = datetime.fromisoformat(lead["created_at"].replace("Z", "+00:00"))
        age_days = (now - created).days
        follow_up_count = lead.get("follow_up_count", 0) or 0
        interests = lead.get("interests", [])
        name = lead["name"]
        email = lead["email"]

        # Day 2 follow-up (send between 1.5 and 3.5 days after signup)
        # V2 2026-04-11: widened upper bound from 3 -> 3.5 to catch leads
        # that landed at exactly 3 days old (previously fell through the gap
        # between 3.0 and 4.5 which was a dead zone).
        if follow_up_count == 0 and 1.5 <= age_days <= 3.5:
            subject, html = day2_email(name, interests, lead)
            if send_email(email, subject, html, lead_id=lead.get("id")):
                sb.table("funnel_leads").update({
                    "follow_up_count": 1,
                    "last_follow_up": now.isoformat(),
                    "status": "nurturing",
                }).eq("id", lead["id"]).execute()
                results["day2_sent"].append(f"{name} ({email})")
            else:
                results["errors"].append(f"Day 2 email failed: {email}")

        # Day 5 follow-up (send between 3.5 and 7 days after signup)
        # V2 2026-04-11: lowered floor from 4.5 -> 3.5 to close the dead zone
        # with Day 2's new upper bound. Overlap is fine because follow_up_count
        # gate ensures a lead doesn't receive both on the same run.
        elif follow_up_count == 1 and 3.5 <= age_days <= 7:
            subject, html = day5_email(name, interests, lead)
            if send_email(email, subject, html, lead_id=lead.get("id")):
                sb.table("funnel_leads").update({
                    "follow_up_count": 2,
                    "last_follow_up": now.isoformat(),
                    "status": "nurtured",
                }).eq("id", lead["id"]).execute()
                results["day5_sent"].append(f"{name} ({email})")
            else:
                results["errors"].append(f"Day 5 email failed: {email}")

        # After Day 7 with no response — mark as cold
        elif follow_up_count >= 2 and age_days > 7:
            sb.table("funnel_leads").update({
                "status": "cold",
            }).eq("id", lead["id"]).execute()

    # Send digest to CC via Telegram
    total_actions = len(results["day2_sent"]) + len(results["day5_sent"])
    if total_actions > 0:
        digest_parts = ["📋 <b>Funnel Nurture Digest</b>\n"]
        if results["day2_sent"]:
            digest_parts.append(f"<b>Day 2 follow-up sent ({len(results['day2_sent'])}):</b>")
            for lead_name in results["day2_sent"]:
                digest_parts.append(f"  • {lead_name}")
        if results["day5_sent"]:
            digest_parts.append(f"\n<b>Day 5 follow-up sent ({len(results['day5_sent'])}):</b>")
            for lead_name in results["day5_sent"]:
                digest_parts.append(f"  • {lead_name}")
        if results["errors"]:
            digest_parts.append(f"\n⚠️ Errors: {len(results['errors'])}")
        send_telegram("\n".join(digest_parts))

    if as_json:
        print(json.dumps(results, indent=2))
    else:
        print(f"Nurture run complete: {len(results['day2_sent'])} Day-2, {len(results['day5_sent'])} Day-5, {len(results['errors'])} errors")


def show_stats(as_json: bool = False):
    sb = get_supabase()
    leads = sb.table("funnel_leads").select("*").order("created_at", desc=True).execute().data

    stats = {"total": len(leads), "new": 0, "nurturing": 0, "nurtured": 0, "cold": 0}
    for lead in leads:
        status = lead.get("status", "new") or "new"
        stats[status] = stats.get(status, 0) + 1

    if as_json:
        print(json.dumps({"stats": stats, "leads": leads}, indent=2, default=str))
    else:
        print(f"Funnel Leads: {stats['total']} total")
        print(f"  New: {stats['new']} | Nurturing: {stats['nurturing']} | Nurtured: {stats['nurtured']} | Cold: {stats['cold']}")
        print()
        for lead in leads[:10]:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(lead["created_at"].replace("Z", "+00:00"))).days
            print(f"  {lead['name']} ({lead['email']}) — {lead.get('status','new')} — {age}d ago — {lead.get('follow_up_count',0)} follow-ups")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Funnel Lead Nurture Engine")
    parser.add_argument("command", choices=["run", "stats"], help="Command to execute")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    if args.command == "run":
        run_nurture(args.json)
    elif args.command == "stats":
        show_stats(args.json)
