"""
Outreach Batch — Semi-Auto Lead Outreach Engine
Pulls uncontacted leads from CRM, drafts personalized cold emails via Claude Haiku,
sends each to CC in Telegram with Approve/Skip inline buttons.

Usage:
  python scripts/outreach_batch.py               # Run batch (up to 5 leads)
  python scripts/outreach_batch.py --limit 3     # Custom batch size
  python scripts/outreach_batch.py --send-draft <path>  # Send an approved draft
  python scripts/outreach_batch.py --skip-draft <path>  # Skip a draft

Called by: scheduler.py (daily 8am cron job), Telegram bridge (callback handler)
Requires: ANTHROPIC_API_KEY, BRAVO_SUPABASE_URL, BRAVO_SUPABASE_SERVICE_ROLE_KEY,
          TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_USERS, GMAIL_APP_PASSWORD in .env.agents
"""

import argparse
import json
import os
import re
import sys
import smtplib
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DRAFTS_DIR = PROJECT_ROOT / "tmp" / "outreach_drafts"
# Separate folder for drafts that have already been sent, so send_approved_draft
# can't silently double-send the same lead if the callback fires twice.
SENT_DIR = PROJECT_ROOT / "tmp" / "outreach_drafts_sent"

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
from casl_compliance import (  # noqa: E402
    should_suppress,
    build_casl_footer,
    add_list_unsubscribe_headers,
)


# ── Env loading ────────────────────────────────────────────────────────────────

def load_env():
    env_path = PROJECT_ROOT / ".env.agents"
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
    for k, v in env_vars.items():
        if k not in os.environ:
            os.environ[k] = v
    return env_vars


def get_supabase(env_vars):
    try:
        from supabase import create_client
    except ImportError:
        print("ERROR: supabase not installed. Run: pip install supabase", file=sys.stderr)
        sys.exit(1)
    url = env_vars.get("BRAVO_SUPABASE_URL")
    key = env_vars.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("ERROR: Missing BRAVO_SUPABASE_URL or BRAVO_SUPABASE_SERVICE_ROLE_KEY", file=sys.stderr)
        sys.exit(1)
    return create_client(url, key)


# ── Draft generation ───────────────────────────────────────────────────────────

def draft_email_claude(lead, env_vars):
    """Use Claude Haiku to draft a personalized cold email for a lead."""
    try:
        import anthropic
    except ImportError:
        print("ERROR: anthropic not installed. Run: pip install anthropic", file=sys.stderr)
        sys.exit(1)

    name = lead.get("name") or "there"
    company = lead.get("company") or "your business"
    notes = lead.get("notes") or ""
    source = lead.get("source") or ""

    # Infer business type from available fields. Previous version matched
    # substrings naively, so "spa" matched "space", "dent" matched "accident",
    # etc. Use word-boundary regex so only whole words match.
    haystack = f"{notes} {company} {source}".lower()
    biz_type = "local service business"
    for pattern, label in [
        (r"\bhvac\b", "HVAC company"),
        (r"\bplumb(er|ing|ers)?\b", "plumbing company"),
        (r"\broof(er|ing|ers)?\b", "roofing company"),
        (r"\bphysio(therapy)?\b", "physiotherapy clinic"),
        (r"\bchiro(practor|practic)?\b", "chiropractic clinic"),
        (r"\blandscap(er|ing|ers)?\b", "landscaping company"),
        (r"\b(med\s*spa|medspa)\b", "med spa"),
        (r"\belectric(ian|al|ians)?\b", "electrical company"),
        (r"\bauto\s*(repair|shop|body)\b", "auto repair shop"),
        (r"\b(dental|dentist|dentistry)\b", "dental clinic"),
        (r"\b(gym|fitness)\b", "fitness studio"),
        (r"\b(cleaning|cleaners|janitorial)\b", "cleaning service"),
    ]:
        if re.search(pattern, haystack):
            biz_type = label
            break

    client = anthropic.Anthropic(api_key=env_vars.get("ANTHROPIC_API_KEY"))

    prompt = f"""Write a short cold email from Conaugh McKenna, founder of OASIS AI Solutions.

Lead:
- Name: {name}
- Company: {company}
- Business type: {biz_type}
- Notes: {notes}

Rules:
- Max 120 words total
- No opener clichés ("hope this finds you", "I came across your profile", "quick question")
- First line: one specific pain point for a {biz_type} (scheduling chaos, chasing quotes, slow follow-ups)
- One concrete stat: clients save 10-15 hrs/week on admin
- CTA: "Worth a 15-min call?" with no link (CC will add it)
- Signature: Conaugh McKenna / OASIS AI Solutions
- Subject line on line 1 as "Subject: [subject]"
- Blank line, then body

Output ONLY the email. No explanation."""

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text.strip()


# ── Telegram messaging ─────────────────────────────────────────────────────────

def _escape_md(s: str) -> str:
    """Escape Telegram legacy Markdown parse_mode metacharacters.

    The legacy parse_mode='Markdown' (what we use here) treats `_*` `*` `` ` ``
    and `[` as active. If the lead's company name or email contains any of
    those, Telegram returns 400 and the draft never reaches CC.
    """
    if not s:
        return ""
    out = []
    for ch in s:
        if ch in "_*`[":
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out)


def send_telegram_approval(lead, email_draft, env_vars):
    """Send draft to CC in Telegram with Approve/Skip inline keyboard."""
    token = env_vars.get("TELEGRAM_BOT_TOKEN")
    allowed = env_vars.get("TELEGRAM_ALLOWED_USERS", "")
    chat_id = allowed.split(",")[0].strip() if allowed else None

    if not token or not chat_id:
        print("ERROR: TELEGRAM_BOT_TOKEN or TELEGRAM_ALLOWED_USERS not set", file=sys.stderr)
        return False

    lead_id = str(lead.get("id", "unknown"))
    name = _escape_md(lead.get("name") or "Unknown")
    company = _escape_md(lead.get("company") or "Unknown")
    email = _escape_md(lead.get("email") or "")
    score = lead.get("score") or 0

    # Telegram message max is 4096 chars. Headers + fence + tail ~200 chars,
    # so 3800 is a safe body cap. 700 (old value) was truncating most drafts.
    display = email_draft[:3800] + ("…" if len(email_draft) > 3800 else "")
    # Escape backtick fence collisions inside the draft
    display = display.replace("```", "ʼʼʼ")

    text = (
        f"\U0001f4e7 *Outreach Draft — {name}*\n"
        f"\U0001f3e2 {company} | \U0001f4ec {email}\n"
        f"\U0001f4ca Score: {score}/100\n\n"
        f"```\n{display}\n```\n\n"
        f"_Approve to send. Skip to pass._"
    )

    keyboard = {"inline_keyboard": [[
        {"text": "\u2705 Send Email", "callback_data": f"outreach_send_{lead_id}"},
        {"text": "\u23ed\ufe0f Skip", "callback_data": f"outreach_skip_{lead_id}"},
    ]]}

    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": json.dumps(keyboard),
    }

    data = urllib.parse.urlencode(payload).encode("utf-8")
    url = f"https://api.telegram.org/bot{token}/sendMessage"

    try:
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            return result.get("ok", False)
    except Exception as e:
        print(f"ERROR sending Telegram: {e}", file=sys.stderr)
        return False


# ── Core actions ───────────────────────────────────────────────────────────────

def run_batch(limit, env_vars):
    """Pull leads → draft emails → send approval requests to Telegram."""
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)

    db = get_supabase(env_vars)

    # IDs already queued in pending drafts
    existing = {f.stem for f in DRAFTS_DIR.glob("*.json")}

    resp = (
        db.table("leads")
        .select("*")
        .eq("status", "new")
        .not_.is_("email", "null")
        .order("score", desc=True)
        .limit(limit * 4)
        .execute()
    )

    leads = resp.data or []
    # Filter out already-drafted leads, low-score leads, and CASL-suppressed
    # addresses. Suppressed leads should never even reach the draft stage —
    # draft generation burns Claude Haiku tokens and the result is unsendable.
    leads = [l for l in leads if str(l.get("id", "")) not in existing]
    leads = [l for l in leads if (l.get("score") or 0) >= 40]
    leads = [l for l in leads if not should_suppress(l.get("email") or "")]
    leads = leads[:limit]

    if not leads:
        print(json.dumps({
            "ok": True,
            "output": "No new leads to draft. Run scrape_maps_emails.py to find more or lower score threshold.",
            "drafted": 0
        }))
        return

    drafted = 0
    errors = 0
    for lead in leads:
        lead_id = str(lead.get("id", ""))
        try:
            email_draft = draft_email_claude(lead, env_vars)

            draft_data = {
                "lead_id": lead_id,
                "lead_name": lead.get("name") or "",
                "lead_email": lead.get("email") or "",
                "company": lead.get("company") or "",
                "score": lead.get("score") or 0,
                "email_draft": email_draft,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            draft_path = DRAFTS_DIR / f"{lead_id}.json"
            draft_path.write_text(json.dumps(draft_data, indent=2))

            sent = send_telegram_approval(lead, email_draft, env_vars)
            status = "sent to Telegram" if sent else "saved (Telegram send failed)"
            print(f"[{drafted+1}] {lead.get('name')} ({lead.get('email')}) — {status}", flush=True)
            drafted += 1

        except Exception as e:
            print(f"ERROR drafting {lead.get('name', lead_id)}: {e}", file=sys.stderr)
            errors += 1

    msg = f"Drafted {drafted} lead(s) and sent to Telegram for approval."
    if errors:
        msg += f" ({errors} failed.)"
    print(json.dumps({"ok": True, "output": msg, "drafted": drafted, "errors": errors}))


def send_approved_draft(draft_path_str, env_vars):
    """Send an approved email draft. Called by Telegram bridge callback handler.

    Double-send guard: the Telegram callback button can fire twice if CC
    double-taps or the network retries. Before sending, atomically rename
    the draft file into tmp/outreach_drafts_sent/. If rename fails because
    the source is gone, we know another invocation already claimed it.
    """
    draft_path = Path(draft_path_str)
    if not draft_path.exists():
        print(json.dumps({"ok": False, "error": f"Draft file not found (already sent?): {draft_path_str}"}))
        sys.exit(1)

    # Claim the draft atomically. If rename fails (race with a sibling
    # callback), the other process owns the send and we exit cleanly.
    SENT_DIR.mkdir(parents=True, exist_ok=True)
    claimed_path = SENT_DIR / draft_path.name
    try:
        draft_path.rename(claimed_path)
    except FileNotFoundError:
        print(json.dumps({"ok": False, "error": "Draft already claimed by another callback."}))
        sys.exit(1)
    except OSError as e:
        print(json.dumps({"ok": False, "error": f"Draft claim failed: {e}"}))
        sys.exit(1)

    draft = json.loads(claimed_path.read_text())
    email_draft = draft["email_draft"]
    lead_email = draft["lead_email"]
    lead_name = draft["lead_name"]
    company = draft.get("company") or lead_name
    lead_id = draft["lead_id"]

    # Final CASL check at send-time. Lead may have been added to the
    # suppression list between draft creation and approval.
    if should_suppress(lead_email):
        print(json.dumps({
            "ok": False,
            "error": f"Lead {lead_email} is on CASL suppression list — send aborted.",
        }))
        sys.exit(1)

    # Parse subject from first line
    lines = email_draft.strip().split("\n")
    subject = f"{company} — AI Automation Intro | OASIS AI"
    body_start = 0
    if lines and lines[0].lower().startswith("subject:"):
        subject = lines[0].split(":", 1)[1].strip()
        body_start = 2 if len(lines) > 2 and lines[1].strip() == "" else 1
    body = "\n".join(lines[body_start:]).strip()
    # CASL footer — sender, address, unsubscribe link. Mandatory.
    body = body + build_casl_footer(lead_email)

    gmail_user = env_vars.get("GMAIL_USER", "conaugh@oasisai.work")
    gmail_app_password = env_vars.get("GMAIL_APP_PASSWORD")
    if not gmail_app_password:
        print(json.dumps({"ok": False, "error": "GMAIL_APP_PASSWORD not set in .env.agents"}))
        sys.exit(1)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"Conaugh McKenna — OASIS AI <{gmail_user}>"
    msg["To"] = lead_email
    # RFC 2369/8058 List-Unsubscribe — native Gmail/Outlook unsubscribe button.
    add_list_unsubscribe_headers(msg, lead_email)
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(gmail_user, gmail_app_password)
            smtp.send_message(msg)

        # Update lead status + log interaction
        db = get_supabase(env_vars)
        db.table("leads").update({
            "status": "contacted",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", lead_id).execute()

        db.table("lead_interactions").insert({
            "lead_id": lead_id,
            "type": "email_sent",
            "channel": "email",
            "subject": subject,
            "content": body[:500],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()

        print(json.dumps({
            "ok": True,
            "output": f"Email sent to {lead_name} ({lead_email}). Lead marked as contacted.",
            "lead_id": lead_id,
            "to": lead_email,
        }))

    except Exception as e:
        # Send failed — move the draft back so CC can retry.
        try:
            claimed_path.rename(draft_path)
        except OSError:
            pass
        print(json.dumps({"ok": False, "error": str(e)}))
        sys.exit(1)


def skip_draft(draft_path_str, env_vars):
    """Skip a draft — delete file, add note to lead in CRM."""
    draft_path = Path(draft_path_str)
    if not draft_path.exists():
        print(json.dumps({"ok": True, "output": "Draft already removed."}))
        return

    draft = json.loads(draft_path.read_text())
    lead_id = draft["lead_id"]

    try:
        db = get_supabase(env_vars)
        existing = db.table("leads").select("notes").eq("id", lead_id).execute()
        existing_notes = (existing.data[0].get("notes") or "") if existing.data else ""
        db.table("leads").update({
            "notes": (existing_notes + " [skipped outreach batch]").strip(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", lead_id).execute()
    except Exception:
        pass

    draft_path.unlink(missing_ok=True)
    print(json.dumps({"ok": True, "output": f"Lead {lead_id} skipped. Draft removed."}))


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Semi-auto outreach batch — drafts + Telegram approve flow")
    parser.add_argument("--limit", type=int, default=5, help="Max leads per batch (default: 5)")
    parser.add_argument("--send-draft", metavar="PATH", help="Send an approved draft email")
    parser.add_argument("--skip-draft", metavar="PATH", help="Skip a draft")
    args = parser.parse_args()

    env_vars = load_env()

    if args.send_draft:
        send_approved_draft(args.send_draft, env_vars)
    elif args.skip_draft:
        skip_draft(args.skip_draft, env_vars)
    else:
        run_batch(args.limit, env_vars)


if __name__ == "__main__":
    main()
