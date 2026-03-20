"""
Funnel Lead Nurture Engine
Sends automated follow-up emails to funnel leads at Day 2 and Day 5.
Called daily by scheduler.py. Notifies CC via Telegram with a digest.

Usage:
    python scripts/funnel_nurture.py run          # Execute nurture sequence
    python scripts/funnel_nurture.py stats         # Show lead stats
    python scripts/funnel_nurture.py --json run    # JSON output for agents
"""

import os
import sys
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Load .env.agents
env_path = Path(__file__).resolve().parent.parent / ".env.agents"
if env_path.exists():
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k, v)


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


def send_email(to_email: str, subject: str, html: str) -> bool:
    gmail_user = os.environ.get("GMAIL_USER", "")
    gmail_pass = os.environ.get("GMAIL_APP_PASSWORD", "")
    if not gmail_user or not gmail_pass:
        return False

    msg = MIMEMultipart("alternative")
    msg["From"] = f'"Conaugh McKenna" <{gmail_user}>'
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_user, gmail_pass)
            server.sendmail(gmail_user, to_email, msg.as_string())
        return True
    except Exception as e:
        print(f"Email send failed to {to_email}: {e}")
        return False


def send_telegram(message: str):
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
        urllib.request.urlopen(req)
    except Exception as e:
        print(f"Telegram notify failed: {e}")


# --- Follow-up email templates ---

def day2_email(name: str, interests: list, data: dict) -> tuple[str, str]:
    first = name.split(" ")[0]

    if "ai" in interests:
        subject = f"{first}, your AI audit is ready"
        body = f"""
        <div style="background:#0a0a0a;padding:40px 20px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif">
          <div style="max-width:520px;margin:0 auto">
            <h2 style="color:#faf9f5;margin:0 0 16px">Hey {first},</h2>
            <p style="color:#ccc;line-height:1.6">I just finished reviewing <strong>{data.get('business_name', 'your business')}</strong>.</p>
            <p style="color:#ccc;line-height:1.6">Here's what I found: there are <strong>at least 3 workflows</strong> you're doing manually right now that could be fully automated — saving you an estimated 10-15 hours per week.</p>
            <p style="color:#ccc;line-height:1.6">I put together a quick breakdown. Want me to send it over? Just reply to this email or DM me on Instagram{' @' + data.get('instagram_handle', '') if data.get('instagram_handle') else ''}.</p>
            <p style="color:#ccc;line-height:1.6">No pressure, no pitch — just the analysis.</p>
            <div style="margin-top:32px;border-top:1px solid #2a2a2a;padding-top:16px">
              <p style="color:#888;font-size:14px;margin:0">— CC McKenna</p>
              <p style="color:#666;font-size:12px;margin:4px 0 0">Founder, OASIS AI Solutions</p>
            </div>
          </div>
        </div>"""
    elif "music" in interests:
        subject = f"{first}, quick question about your event"
        body = f"""
        <div style="background:#0a0a0a;padding:40px 20px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif">
          <div style="max-width:520px;margin:0 auto">
            <h2 style="color:#faf9f5;margin:0 0 16px">Hey {first},</h2>
            <p style="color:#ccc;line-height:1.6">Just following up on your {data.get('event_type', 'event')} inquiry{' for ' + data.get('event_date', '') if data.get('event_date') else ''}.</p>
            <p style="color:#ccc;line-height:1.6">I've got some availability opening up and wanted to make sure I don't miss your date. What's the best way to chat — email, DM, or a quick call?</p>
            <p style="color:#ccc;line-height:1.6">I'll put together a vibe proposal based on what you told me{' (' + data.get('music_vibe', '') + ')' if data.get('music_vibe') else ''} so you can see exactly what the set would feel like.</p>
            <div style="margin-top:32px;border-top:1px solid #2a2a2a;padding-top:16px">
              <p style="color:#888;font-size:14px;margin:0">— CC</p>
            </div>
          </div>
        </div>"""
    else:
        subject = f"{first}, let's book your strategy session"
        body = f"""
        <div style="background:#0a0a0a;padding:40px 20px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif">
          <div style="max-width:520px;margin:0 auto">
            <h2 style="color:#faf9f5;margin:0 0 16px">Hey {first},</h2>
            <p style="color:#ccc;line-height:1.6">I wanted to reach out about your free brand strategy session.</p>
            <p style="color:#ccc;line-height:1.6">You mentioned your goal is to <strong>{data.get('brand_goal', 'grow your brand')}</strong>{' targeting ' + data.get('audience', '') if data.get('audience') else ''} — I've got some specific ideas that could move the needle fast.</p>
            <p style="color:#ccc;line-height:1.6">Just reply with a time that works this week and I'll block 15 minutes for us. Completely free, no strings.</p>
            <div style="margin-top:32px;border-top:1px solid #2a2a2a;padding-top:16px">
              <p style="color:#888;font-size:14px;margin:0">— CC McKenna</p>
            </div>
          </div>
        </div>"""

    return subject, body


def day5_email(name: str, interests: list, data: dict) -> tuple[str, str]:
    first = name.split(" ")[0]

    if "ai" in interests:
        subject = f"Last call, {first} — your AI audit expires soon"
        body = f"""
        <div style="background:#0a0a0a;padding:40px 20px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif">
          <div style="max-width:520px;margin:0 auto">
            <h2 style="color:#faf9f5;margin:0 0 16px">{first},</h2>
            <p style="color:#ccc;line-height:1.6">Quick heads up — I did the full audit for <strong>{data.get('business_name', 'your business')}</strong> and it's sitting in my drafts waiting for you.</p>
            <p style="color:#ccc;line-height:1.6">I can only keep these personalized for so long before I move on to the next batch, so if you want it, just reply "send it" and I'll fire it over.</p>
            <p style="color:#ccc;line-height:1.6">Either way, no hard feelings. Just didn't want you to miss something that could genuinely save you hours every week.</p>
            <div style="margin-top:32px;border-top:1px solid #2a2a2a;padding-top:16px">
              <p style="color:#888;font-size:14px;margin:0">— CC</p>
            </div>
          </div>
        </div>"""
    elif "music" in interests:
        subject = f"{first} — still looking for a DJ?"
        body = f"""
        <div style="background:#0a0a0a;padding:40px 20px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif">
          <div style="max-width:520px;margin:0 auto">
            <h2 style="color:#faf9f5;margin:0 0 16px">Hey {first},</h2>
            <p style="color:#ccc;line-height:1.6">Just checking in — my calendar is filling up and I want to make sure your event doesn't slip through the cracks.</p>
            <p style="color:#ccc;line-height:1.6">If you've already found someone, no worries at all. But if you're still looking, let me know and I'll lock your date in before it's gone.</p>
            <div style="margin-top:32px;border-top:1px solid #2a2a2a;padding-top:16px">
              <p style="color:#888;font-size:14px;margin:0">— CC</p>
            </div>
          </div>
        </div>"""
    else:
        subject = f"{first}, your free session is still available"
        body = f"""
        <div style="background:#0a0a0a;padding:40px 20px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif">
          <div style="max-width:520px;margin:0 auto">
            <h2 style="color:#faf9f5;margin:0 0 16px">{first},</h2>
            <p style="color:#ccc;line-height:1.6">Your free brand strategy session is still on the table. I only do a few of these a week, so I wanted to make sure you didn't forget.</p>
            <p style="color:#ccc;line-height:1.6">15 minutes, zero pitch, and you'll walk away with at least one thing you can implement immediately.</p>
            <p style="color:#ccc;line-height:1.6">Reply with "I'm in" and I'll send a calendar link.</p>
            <div style="margin-top:32px;border-top:1px solid #2a2a2a;padding-top:16px">
              <p style="color:#888;font-size:14px;margin:0">— CC McKenna</p>
            </div>
          </div>
        </div>"""

    return subject, body


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

        # Day 2 follow-up (send between 1.5 and 3 days after signup)
        if follow_up_count == 0 and 1.5 <= age_days <= 3:
            subject, html = day2_email(name, interests, lead)
            if send_email(email, subject, html):
                sb.table("funnel_leads").update({
                    "follow_up_count": 1,
                    "last_follow_up": now.isoformat(),
                    "status": "nurturing",
                }).eq("id", lead["id"]).execute()
                results["day2_sent"].append(f"{name} ({email})")
            else:
                results["errors"].append(f"Day 2 email failed: {email}")

        # Day 5 follow-up (send between 4.5 and 7 days after signup)
        elif follow_up_count == 1 and 4.5 <= age_days <= 7:
            subject, html = day5_email(name, interests, lead)
            if send_email(email, subject, html):
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
