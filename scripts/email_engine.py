"""
Email Engine - Free send and nurture sequence engine.
Zero paid services. Gmail SMTP (500/day free) + Supabase for tracking.
All credentials loaded from .env.agents (never hardcoded).

Usage:
  python scripts/email_engine.py send --to "person@email.com" --subject "Subject" --body "Body"
  python scripts/email_engine.py send --to "person@email.com" --subject "Subject" --body "Body" --html "<h1>Hi</h1>" --lead-id uuid
  python scripts/email_engine.py send-template --template-id uuid --to "person@email.com" --vars '{"first_name": "John"}'
  python scripts/email_engine.py templates list
  python scripts/email_engine.py templates create --name "Welcome" --subject "Welcome to OASIS" --body-html "<h1>Welcome {{first_name}}</h1>" --category welcome --vars '["first_name"]'
  python scripts/email_engine.py templates view <template_id>
  python scripts/email_engine.py sequence list
  python scripts/email_engine.py sequence create --name "New Lead Nurture" --trigger lead_created --steps '[{"delay_hours": 0, "template_name": "Welcome"}]'
  python scripts/email_engine.py sequence run <sequence_id> --lead-id <lead_id>
  python scripts/email_engine.py log [--status queued|sent|failed] [--limit 20]
  python scripts/email_engine.py stats
"""

import argparse
import email
import email.header
import imaplib
import json
import re
import smtplib
import sys
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from notify import notify
except ImportError:
    def notify(*a, **kw): return False


# -- Credentials -------------------------------------------


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


def get_supabase(env_vars):
    """Create Supabase client using Bravo project credentials."""
    try:
        from supabase import create_client
    except ImportError:
        print("ERROR: supabase package not installed. Run: pip install supabase", file=sys.stderr)
        sys.exit(1)

    url = env_vars.get("BRAVO_SUPABASE_URL")
    key = env_vars.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY")

    if not url or not key:
        print("ERROR: Missing Supabase credentials in .env.agents", file=sys.stderr)
        print("  Need: BRAVO_SUPABASE_URL and BRAVO_SUPABASE_SERVICE_ROLE_KEY", file=sys.stderr)
        sys.exit(1)

    return create_client(url, key)


def get_smtp_credentials(env_vars):
    """Return (gmail_address, app_password) or print setup instructions and exit."""
    address = env_vars.get("GMAIL_ADDRESS") or env_vars.get("GMAIL_USER")
    password = env_vars.get("GMAIL_APP_PASSWORD")

    if not address or not password:
        print("ERROR: Gmail SMTP credentials not configured in .env.agents", file=sys.stderr)
        print("", file=sys.stderr)
        print("  To set up free Gmail sending (500 emails/day):", file=sys.stderr)
        print("  1. Enable 2-Step Verification on your Google account", file=sys.stderr)
        print("  2. Go to: https://myaccount.google.com/apppasswords", file=sys.stderr)
        print("  3. Create an App Password for 'Mail'", file=sys.stderr)
        print("  4. Add to .env.agents:", file=sys.stderr)
        print("       GMAIL_ADDRESS=youraddress@gmail.com", file=sys.stderr)
        print("       GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx", file=sys.stderr)
        sys.exit(1)

    return address, password


# -- SMTP --------------------------------------------------


def send_email_smtp(gmail_address, app_password, to_email, subject, body_text, body_html=None):
    """
    Send an email via Gmail SMTP with STARTTLS.
    Returns (success: bool, error_message: str | None).
    """
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = gmail_address
        msg["To"] = to_email

        msg.attach(MIMEText(body_text, "plain"))
        if body_html:
            msg.attach(MIMEText(body_html, "html"))

        with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(gmail_address, app_password)
            server.sendmail(gmail_address, to_email, msg.as_string())

        return True, None

    except smtplib.SMTPAuthenticationError:
        return False, "SMTP authentication failed. Check GMAIL_APP_PASSWORD in .env.agents."
    except smtplib.SMTPRecipientsRefused:
        return False, f"Recipient address refused by server: {to_email}"
    except smtplib.SMTPException as e:
        return False, f"SMTP error: {str(e)}"
    except Exception as e:
        return False, f"Unexpected error: {str(e)}"


# -- Template rendering -------------------------------------


def render_template(template_str, variables):
    """Replace {{variable}} placeholders with values from the variables dict."""
    def replacer(match):
        key = match.group(1).strip()
        return str(variables.get(key, match.group(0)))

    return re.sub(r"\{\{([^}]+)\}\}", replacer, template_str)


# -- Supabase logging ---------------------------------------


def log_email(db, to_email, subject, body_preview, status, lead_id=None,
              template_id=None, sequence_id=None, error_message=None):
    """Write a row to the email_log table. Returns the created row id or None."""
    row = {
        "to_email": to_email,
        "subject": subject,
        "body_preview": body_preview[:200] if body_preview else None,
        "status": status,
        "sent_at": datetime.now(timezone.utc).isoformat() if status == "sent" else None,
        "error_message": error_message,
    }
    if lead_id:
        row["lead_id"] = lead_id
    if template_id:
        row["template_id"] = template_id
    if sequence_id:
        row["sequence_id"] = sequence_id

    try:
        result = db.table("email_log").insert(row).execute()
        if result.data:
            return result.data[0].get("id")
    except Exception as e:
        # Log failure is non-fatal - print to stderr and continue
        print(f"Warning: could not write to email_log: {e}", file=sys.stderr)
    return None


# -- Commands ----------------------------------------------


def cmd_send(env_vars, args, output_json=False):
    """Send a one-off email directly."""
    db = get_supabase(env_vars)
    gmail_address, app_password = get_smtp_credentials(env_vars)

    body_text = args.body
    body_html = getattr(args, "html", None)
    lead_id = getattr(args, "lead_id", None)

    success, error = send_email_smtp(
        gmail_address, app_password,
        args.to, args.subject, body_text, body_html,
    )

    status = "sent" if success else "failed"
    log_id = log_email(
        db,
        to_email=args.to,
        subject=args.subject,
        body_preview=body_html or body_text,
        status=status,
        lead_id=lead_id,
        error_message=error,
    )

    result = {
        "status": status,
        "to": args.to,
        "subject": args.subject,
        "log_id": log_id,
        "error": error,
    }

    if output_json:
        print(json.dumps(result, indent=2))
        return

    if success:
        print(f"Sent to {args.to} - subject: {args.subject}")
        if log_id:
            print(f"  Logged (id: {log_id})")
    else:
        print(f"ERROR: Failed to send to {args.to}", file=sys.stderr)
        print(f"  {error}", file=sys.stderr)
        sys.exit(1)


def cmd_send_template(env_vars, args, output_json=False):
    """Send a stored template to an address, rendering {{variables}}."""
    db = get_supabase(env_vars)
    gmail_address, app_password = get_smtp_credentials(env_vars)

    # Fetch template
    try:
        result = db.table("email_templates").select("*").eq("id", args.template_id).execute()
    except Exception as e:
        print(f"ERROR: Could not fetch template: {e}", file=sys.stderr)
        sys.exit(1)

    if not result.data:
        print(f"ERROR: Template not found: {args.template_id}", file=sys.stderr)
        sys.exit(1)

    tmpl = result.data[0]
    variables = json.loads(args.vars) if args.vars else {}

    subject = render_template(tmpl["subject"], variables)
    body_html = render_template(tmpl.get("body_html") or "", variables) or None
    # Generate plain-text fallback by stripping HTML tags
    body_text = re.sub(r"<[^>]+>", "", body_html or "") if body_html else subject

    lead_id = getattr(args, "lead_id", None)

    success, error = send_email_smtp(
        gmail_address, app_password,
        args.to, subject, body_text, body_html,
    )

    status = "sent" if success else "failed"
    log_id = log_email(
        db,
        to_email=args.to,
        subject=subject,
        body_preview=body_html or body_text,
        status=status,
        lead_id=lead_id,
        template_id=args.template_id,
        error_message=error,
    )

    result_dict = {
        "status": status,
        "to": args.to,
        "subject": subject,
        "template_id": args.template_id,
        "template_name": tmpl.get("name"),
        "log_id": log_id,
        "error": error,
    }

    if output_json:
        print(json.dumps(result_dict, indent=2))
        return

    if success:
        print(f"Sent template '{tmpl.get('name')}' to {args.to}")
        if log_id:
            print(f"  Logged (id: {log_id})")
    else:
        print(f"ERROR: Failed to send to {args.to}", file=sys.stderr)
        print(f"  {error}", file=sys.stderr)
        sys.exit(1)


def cmd_templates_list(env_vars, args, output_json=False):
    """List all stored email templates."""
    db = get_supabase(env_vars)

    try:
        result = db.table("email_templates").select("id, name, subject, category, variables").order("name").execute()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if output_json:
        print(json.dumps(result.data, indent=2, default=str))
        return

    templates = result.data
    if not templates:
        print("No templates found.")
        return

    print(f"Email Templates ({len(templates)}):\n")
    for t in templates:
        category = t.get("category") or "uncategorized"
        variables = t.get("variables") or []
        vars_str = ", ".join(variables) if variables else "none"
        print(f"  [{t['id'][:8]}...] {t['name']} [{category}]")
        print(f"    Subject: {t['subject']}")
        print(f"    Variables: {vars_str}")
        print()


def cmd_templates_create(env_vars, args, output_json=False):
    """Create a new email template."""
    db = get_supabase(env_vars)

    variables = json.loads(args.vars) if args.vars else []
    if not isinstance(variables, list):
        print("ERROR: --vars must be a JSON array, e.g. '[\"first_name\", \"company\"]'", file=sys.stderr)
        sys.exit(1)

    # Generate plain-text version by stripping HTML
    body_text = re.sub(r"<[^>]+>", "", args.body_html) if args.body_html else None

    row = {
        "name": args.name,
        "subject": args.subject,
        "body_html": args.body_html,
        "body_text": body_text,
        "category": args.category,
        "variables": variables,
    }

    try:
        result = db.table("email_templates").insert(row).execute()
    except Exception as e:
        print(f"ERROR: Could not create template: {e}", file=sys.stderr)
        sys.exit(1)

    created = result.data[0] if result.data else row

    if output_json:
        print(json.dumps(created, indent=2, default=str))
        return

    print(f"Template created: {created.get('name')}")
    print(f"  ID:       {created.get('id', 'N/A')}")
    print(f"  Category: {created.get('category', 'N/A')}")
    print(f"  Variables: {', '.join(variables) or 'none'}")


def cmd_templates_view(env_vars, args, output_json=False):
    """View a single template by ID."""
    db = get_supabase(env_vars)

    try:
        result = db.table("email_templates").select("*").eq("id", args.template_id).execute()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if not result.data:
        print(f"ERROR: Template not found: {args.template_id}", file=sys.stderr)
        sys.exit(1)

    tmpl = result.data[0]

    if output_json:
        print(json.dumps(tmpl, indent=2, default=str))
        return

    print(f"Template: {tmpl['name']}")
    print(f"  ID:        {tmpl['id']}")
    print(f"  Category:  {tmpl.get('category', 'N/A')}")
    print(f"  Subject:   {tmpl['subject']}")
    print(f"  Variables: {', '.join(tmpl.get('variables') or []) or 'none'}")
    print()
    print("--- HTML Body ---")
    print(tmpl.get("body_html") or "(none)")


def cmd_sequence_list(env_vars, args, output_json=False):
    """List all nurture sequences."""
    db = get_supabase(env_vars)

    try:
        result = db.table("nurture_sequences").select("id, name, trigger_event, is_active, steps").order("name").execute()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if output_json:
        print(json.dumps(result.data, indent=2, default=str))
        return

    sequences = result.data
    if not sequences:
        print("No sequences found.")
        return

    print(f"Nurture Sequences ({len(sequences)}):\n")
    for s in sequences:
        active = "ACTIVE" if s.get("is_active") else "inactive"
        steps = s.get("steps") or []
        step_count = len(steps) if isinstance(steps, list) else "?"
        print(f"  [{s['id'][:8]}...] {s['name']} [{active}]")
        print(f"    Trigger: {s.get('trigger_event', 'N/A')}")
        print(f"    Steps:   {step_count}")
        print()


def cmd_sequence_create(env_vars, args, output_json=False):
    """Create a nurture sequence with ordered steps."""
    db = get_supabase(env_vars)

    try:
        steps = json.loads(args.steps)
    except json.JSONDecodeError as e:
        print(f"ERROR: --steps is not valid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(steps, list):
        print("ERROR: --steps must be a JSON array of step objects", file=sys.stderr)
        sys.exit(1)

    # Validate each step has at minimum delay_hours and template_name
    for i, step in enumerate(steps):
        if "delay_hours" not in step:
            print(f"ERROR: Step {i} is missing 'delay_hours'", file=sys.stderr)
            sys.exit(1)
        if "template_name" not in step:
            print(f"ERROR: Step {i} is missing 'template_name'", file=sys.stderr)
            sys.exit(1)

    row = {
        "name": args.name,
        "trigger_event": args.trigger,
        "steps": steps,
        "is_active": True,
    }

    try:
        result = db.table("nurture_sequences").insert(row).execute()
    except Exception as e:
        print(f"ERROR: Could not create sequence: {e}", file=sys.stderr)
        sys.exit(1)

    created = result.data[0] if result.data else row

    if output_json:
        print(json.dumps(created, indent=2, default=str))
        return

    print(f"Sequence created: {created.get('name')}")
    print(f"  ID:      {created.get('id', 'N/A')}")
    print(f"  Trigger: {created.get('trigger_event', 'N/A')}")
    print(f"  Steps:   {len(steps)}")
    for i, step in enumerate(steps):
        print(f"    [{i + 1}] delay: {step['delay_hours']}h - template: {step['template_name']}")


def cmd_sequence_run(env_vars, args, output_json=False):
    """
    Execute a sequence for a lead - sends all steps immediately.

    In production you would schedule delayed sends via a job queue (e.g., n8n,
    pg_cron, or a Lambda cron). This command executes each step NOW, which is
    useful for testing and for sequences where delay_hours is meaningful only
    relative to a trigger you manage externally.

    Each step without a 'delay_hours' of 0 will be logged as 'queued' rather
    than actually sent, so the caller can process them on schedule.
    """
    db = get_supabase(env_vars)
    gmail_address, app_password = get_smtp_credentials(env_vars)

    # Fetch sequence
    try:
        seq_result = db.table("nurture_sequences").select("*").eq("id", args.sequence_id).execute()
    except Exception as e:
        print(f"ERROR: Could not fetch sequence: {e}", file=sys.stderr)
        sys.exit(1)

    if not seq_result.data:
        print(f"ERROR: Sequence not found: {args.sequence_id}", file=sys.stderr)
        sys.exit(1)

    sequence = seq_result.data[0]
    steps = sequence.get("steps") or []

    if not steps:
        print("ERROR: Sequence has no steps.", file=sys.stderr)
        sys.exit(1)

    # Fetch lead email from lead_id (expects a leads or contacts table with email column)
    lead_email = getattr(args, "lead_email", None)
    if not lead_email:
        try:
            lead_result = db.table("leads").select("email, first_name, last_name, company").eq("id", args.lead_id).execute()
            if lead_result.data:
                lead = lead_result.data[0]
                lead_email = lead.get("email")
            else:
                print(f"ERROR: Lead not found: {args.lead_id}", file=sys.stderr)
                print("  Tip: pass --lead-email if your leads table has a different schema.", file=sys.stderr)
                sys.exit(1)
        except Exception as e:
            print(f"ERROR: Could not fetch lead: {e}", file=sys.stderr)
            print("  Tip: pass --lead-email to bypass the leads table lookup.", file=sys.stderr)
            sys.exit(1)

    lead_vars = {}
    if "lead" in dir():
        # Populate template variables from lead fields
        lead_vars = {k: v for k, v in lead.items() if v is not None}  # type: ignore[name-defined]

    results = []

    for i, step in enumerate(steps):
        template_name = step.get("template_name")
        delay_hours = step.get("delay_hours", 0)
        step_vars = {**lead_vars, **step.get("variables", {})}

        # Fetch template by name
        try:
            tmpl_result = db.table("email_templates").select("*").eq("name", template_name).execute()
        except Exception as e:
            results.append({"step": i + 1, "template": template_name, "status": "error", "error": str(e)})
            continue

        if not tmpl_result.data:
            results.append({"step": i + 1, "template": template_name, "status": "error",
                            "error": f"Template '{template_name}' not found"})
            continue

        tmpl = tmpl_result.data[0]
        subject = render_template(tmpl["subject"], step_vars)
        body_html = render_template(tmpl.get("body_html") or "", step_vars) or None
        body_text = re.sub(r"<[^>]+>", "", body_html or "") if body_html else subject

        # Step 0 is sent immediately; future steps are logged as queued
        if delay_hours == 0:
            success, error = send_email_smtp(
                gmail_address, app_password,
                lead_email, subject, body_text, body_html,
            )
            status = "sent" if success else "failed"
        else:
            success, error = True, None
            status = "queued"

        log_email(
            db,
            to_email=lead_email,
            subject=subject,
            body_preview=body_html or body_text,
            status=status,
            lead_id=args.lead_id,
            template_id=tmpl["id"],
            sequence_id=args.sequence_id,
            error_message=error,
        )

        results.append({
            "step": i + 1,
            "template": template_name,
            "delay_hours": delay_hours,
            "status": status,
            "error": error,
        })

    if output_json:
        print(json.dumps({"sequence": sequence["name"], "lead_id": args.lead_id, "steps": results}, indent=2))
        return

    print(f"Sequence '{sequence['name']}' for lead {args.lead_id}:\n")
    for r in results:
        delay_label = f" (delay: {r['delay_hours']}h)" if r.get("delay_hours") else ""
        print(f"  Step {r['step']}: {r['template']}{delay_label} - {r['status']}")
        if r.get("error"):
            print(f"    Error: {r['error']}")

    sent = sum(1 for r in results if r["status"] == "sent")
    queued = sum(1 for r in results if r["status"] == "queued")
    failed = sum(1 for r in results if r["status"] == "failed")
    print(f"\n--- {sent} sent, {queued} queued for future delivery, {failed} failed ---")


def cmd_log(env_vars, args, output_json=False):
    """Show the email send log."""
    db = get_supabase(env_vars)

    limit = getattr(args, "limit", 20)
    status_filter = getattr(args, "status", None)

    try:
        query = db.table("email_log").select(
            "id, to_email, subject, status, sent_at, error_message, lead_id, template_id, sequence_id"
        )

        if status_filter:
            query = query.eq("status", status_filter)

        query = query.order("sent_at", desc=True).limit(limit)
        result = query.execute()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if output_json:
        print(json.dumps(result.data, indent=2, default=str))
        return

    rows = result.data
    if not rows:
        print("No email log entries found.")
        return

    label = f" (status={status_filter})" if status_filter else ""
    print(f"Email Log{label} - {len(rows)} entries:\n")
    for row in rows:
        sent_at = row.get("sent_at") or "-"
        if sent_at and sent_at != "-":
            sent_at = sent_at[:19].replace("T", " ")
        status = row.get("status", "?").upper()
        subject = (row.get("subject") or "")[:50]
        print(f"  [{status}] {sent_at}  {row['to_email']}")
        print(f"    Subject: {subject}")
        if row.get("error_message"):
            print(f"    Error: {row['error_message']}")
        if row.get("lead_id"):
            print(f"    Lead: {row['lead_id']}")
        print()


def cmd_stats(env_vars, args, output_json=False):
    """Show aggregate send statistics."""
    db = get_supabase(env_vars)

    try:
        all_rows = db.table("email_log").select("status").execute()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    rows = all_rows.data
    total = len(rows)
    sent = sum(1 for r in rows if r.get("status") == "sent")
    failed = sum(1 for r in rows if r.get("status") == "failed")
    queued = sum(1 for r in rows if r.get("status") == "queued")
    opened = 0  # opened_at/clicked_at columns not yet implemented
    clicked = 0

    open_rate = (opened / sent * 100) if sent else 0
    click_rate = (clicked / sent * 100) if sent else 0

    stats = {
        "total": total,
        "sent": sent,
        "queued": queued,
        "failed": failed,
        "opened": opened,
        "clicked": clicked,
        "open_rate_pct": round(open_rate, 1),
        "click_rate_pct": round(click_rate, 1),
    }

    if output_json:
        print(json.dumps(stats, indent=2))
        return

    print("Email Statistics:\n")
    print(f"  Total logged:  {total}")
    print(f"  Sent:          {sent}")
    print(f"  Queued:        {queued}")
    print(f"  Failed:        {failed}")
    print(f"  Opened:        {opened}  ({open_rate:.1f}% open rate)")
    print(f"  Clicked:       {clicked}  ({click_rate:.1f}% click rate)")


# -- IMAP inbox check --------------------------------------

SKIP_SENDERS = ("noreply@", "no-reply@", "mailer-daemon@", "postmaster@")
IMAP_MAX_EMAILS = 20


def _decode_header_value(raw_value):
    """Decode an email header value to a plain ASCII-safe string."""
    if raw_value is None:
        return ""
    parts = email.header.decode_header(raw_value)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            try:
                decoded.append(part.decode(charset or "utf-8", errors="replace"))
            except (LookupError, UnicodeDecodeError):
                decoded.append(part.decode("utf-8", errors="replace"))
        else:
            decoded.append(str(part))
    result = "".join(decoded)
    # Strip non-ASCII for Windows cp1252 safety
    return result.encode("ascii", errors="replace").decode("ascii")


def _extract_text_preview(msg, max_chars=200):
    """Pull the first max_chars of plain-text body from an email.Message object."""
    preview = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        preview = payload.decode(charset, errors="replace")
                    except (LookupError, UnicodeDecodeError):
                        preview = payload.decode("utf-8", errors="replace")
                    break
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            try:
                preview = payload.decode(charset, errors="replace")
            except (LookupError, UnicodeDecodeError):
                preview = payload.decode("utf-8", errors="replace")

    # Collapse whitespace and trim
    preview = " ".join(preview.split())
    preview = preview.encode("ascii", errors="replace").decode("ascii")
    return preview[:max_chars]


def cmd_check_inbox(env_vars, args, output_json=False):
    """
    Connect to Gmail IMAP, fetch UNSEEN emails, log them to Supabase,
    notify via Telegram, then mark them as SEEN.
    """
    address = env_vars.get("GMAIL_ADDRESS") or env_vars.get("GMAIL_USER")
    password = env_vars.get("GMAIL_APP_PASSWORD")

    if not address or not password:
        msg = "ERROR: GMAIL_ADDRESS and GMAIL_APP_PASSWORD required in .env.agents"
        if output_json:
            print(json.dumps({"status": "error", "message": msg}))
        else:
            print(msg, file=sys.stderr)
        sys.exit(1)

    db = get_supabase(env_vars)
    imap = None
    found_emails = []

    try:
        imap = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        imap.socket().settimeout(30)
        imap.login(address, password)
        imap.select("INBOX")

        status, data = imap.search(None, "UNSEEN")
        if status != "OK":
            raise RuntimeError(f"IMAP search failed: {status}")

        message_ids = data[0].split() if data[0] else []
        # Cap to avoid long runs
        message_ids = message_ids[:IMAP_MAX_EMAILS]

        for uid in message_ids:
            fetch_status, fetch_data = imap.fetch(uid, "(RFC822)")
            if fetch_status != "OK" or not fetch_data or fetch_data[0] is None:
                continue

            raw_bytes = fetch_data[0][1]
            if not isinstance(raw_bytes, bytes):
                continue

            msg = email.message_from_bytes(raw_bytes)
            from_addr = _decode_header_value(msg.get("From", ""))
            subject = _decode_header_value(msg.get("Subject", "(no subject)"))
            date_str = _decode_header_value(msg.get("Date", ""))
            preview = _extract_text_preview(msg)

            # Skip system/noreply senders
            from_lower = from_addr.lower()
            if any(skip in from_lower for skip in SKIP_SENDERS):
                # Still mark as seen so it doesn't keep surfacing
                imap.store(uid, "+FLAGS", "\\Seen")
                continue

            email_entry = {
                "from": from_addr,
                "subject": subject,
                "date": date_str,
                "preview": preview,
            }
            found_emails.append(email_entry)

            # Log to Supabase email_log
            try:
                db.table("email_log").insert({
                    "to_email": address,
                    "subject": subject,
                    "body_preview": preview,
                    "status": "received",
                    "sent_at": datetime.now(timezone.utc).isoformat(),
                }).execute()
            except Exception as db_err:
                print(f"Warning: could not log inbound email to Supabase: {db_err}", file=sys.stderr)

            # Telegram notification
            notify_msg = (
                f"[Email Inbox] New email from: {from_addr}\n"
                f"Subject: {subject}\n"
                f"Preview: {preview[:120]}"
            )
            notify(notify_msg)

            # Mark as read
            imap.store(uid, "+FLAGS", "\\Seen")

    finally:
        if imap:
            try:
                imap.close()
                imap.logout()
            except Exception:
                pass

    if not found_emails:
        result = {"status": "checked", "unread_count": 0, "message": "No unread emails"}
    else:
        result = {
            "status": "checked",
            "unread_count": len(found_emails),
            "emails": found_emails,
        }

    if output_json:
        print(json.dumps(result, indent=2))
        return

    if not found_emails:
        print("Inbox checked - no unread emails.")
        return

    print(f"Inbox checked - {len(found_emails)} unread email(s):\n")
    for e in found_emails:
        subject_display = e["subject"][:60]
        from_display = e["from"][:60]
        print(f"  From:    {from_display}")
        print(f"  Subject: {subject_display}")
        print(f"  Date:    {e['date']}")
        if e["preview"]:
            print(f"  Preview: {e['preview'][:100]}")
        print()


# -- Argument parsing ---------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Email Engine - Free Gmail SMTP sending + Supabase tracking",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s send --to "lead@example.com" --subject "Quick question" --body "Hi there..."
  %(prog)s send-template --template-id <uuid> --to "lead@example.com" --vars '{"first_name": "John"}'
  %(prog)s templates list
  %(prog)s templates create --name "Welcome" --subject "Welcome {{first_name}}" --body-html "<h1>Hi {{first_name}}</h1>" --category welcome --vars '["first_name"]'
  %(prog)s templates view <uuid>
  %(prog)s sequence list
  %(prog)s sequence create --name "New Lead" --trigger lead_created --steps '[{"delay_hours":0,"template_name":"Welcome"},{"delay_hours":72,"template_name":"Value Add"}]'
  %(prog)s sequence run <seq_uuid> --lead-id <lead_uuid>
  %(prog)s log --status sent --limit 10
  %(prog)s stats
        """
    )

    parser.add_argument("--json", dest="output_json", action="store_true",
                        help="Output JSON for agent consumption")

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # send
    p_send = subparsers.add_parser("send", help="Send a one-off email")
    p_send.add_argument("--to", required=True, help="Recipient email address")
    p_send.add_argument("--subject", required=True)
    p_send.add_argument("--body", required=True, help="Plain text body")
    p_send.add_argument("--html", dest="html", default=None, help="HTML body (optional)")
    p_send.add_argument("--lead-id", dest="lead_id", default=None, help="Lead UUID for log association")

    # send-template
    p_st = subparsers.add_parser("send-template", help="Send a stored template")
    p_st.add_argument("--template-id", dest="template_id", required=True, help="Template UUID")
    p_st.add_argument("--to", required=True, help="Recipient email address")
    p_st.add_argument("--vars", default=None, help='Variable substitution JSON: \'{"first_name": "John"}\'')
    p_st.add_argument("--lead-id", dest="lead_id", default=None, help="Lead UUID for log association")

    # templates (sub-group)
    p_tmpl = subparsers.add_parser("templates", help="Manage email templates")
    tmpl_sub = p_tmpl.add_subparsers(dest="tmpl_command", help="Template operation")

    tmpl_sub.add_parser("list", help="List all templates")

    p_tc = tmpl_sub.add_parser("create", help="Create a template")
    p_tc.add_argument("--name", required=True)
    p_tc.add_argument("--subject", required=True)
    p_tc.add_argument("--body-html", dest="body_html", required=True, help="HTML body with {{variable}} placeholders")
    p_tc.add_argument("--category", default="general",
                      choices=["welcome", "nurture", "followup", "cta", "general"])
    p_tc.add_argument("--vars", default=None, help='Variable names as JSON array: \'["first_name", "company"]\'')

    p_tv = tmpl_sub.add_parser("view", help="View a template by ID")
    p_tv.add_argument("template_id", help="Template UUID")

    # sequence (sub-group)
    p_seq = subparsers.add_parser("sequence", help="Manage nurture sequences")
    seq_sub = p_seq.add_subparsers(dest="seq_command", help="Sequence operation")

    seq_sub.add_parser("list", help="List all sequences")

    p_sc = seq_sub.add_parser("create", help="Create a nurture sequence")
    p_sc.add_argument("--name", required=True)
    p_sc.add_argument("--trigger", required=True,
                      help="Trigger event name (e.g. lead_created, demo_booked)")
    p_sc.add_argument("--steps", required=True,
                      help='JSON array of steps: \'[{"delay_hours":0,"template_name":"Welcome"}]\'')

    p_sr = seq_sub.add_parser("run", help="Run a sequence for a lead")
    p_sr.add_argument("sequence_id", help="Sequence UUID")
    p_sr.add_argument("--lead-id", dest="lead_id", required=True, help="Lead UUID")
    p_sr.add_argument("--lead-email", dest="lead_email", default=None,
                      help="Lead email (bypasses leads table lookup)")

    # log
    p_log = subparsers.add_parser("log", help="View email send log")
    p_log.add_argument("--status", choices=["queued", "sent", "failed"], default=None)
    p_log.add_argument("--limit", "-l", type=int, default=20)

    # stats
    subparsers.add_parser("stats", help="Show aggregate email statistics")

    # check-inbox
    subparsers.add_parser("check-inbox", help="Fetch unread Gmail messages via IMAP and mark them as read")

    args = parser.parse_args()
    output_json = args.output_json

    if not args.command:
        parser.print_help()
        sys.exit(1)

    env_vars = load_env()

    # Dispatch
    if args.command == "send":
        cmd_send(env_vars, args, output_json)

    elif args.command == "send-template":
        cmd_send_template(env_vars, args, output_json)

    elif args.command == "templates":
        if not args.tmpl_command:
            p_tmpl.print_help()
            sys.exit(1)
        if args.tmpl_command == "list":
            cmd_templates_list(env_vars, args, output_json)
        elif args.tmpl_command == "create":
            cmd_templates_create(env_vars, args, output_json)
        elif args.tmpl_command == "view":
            cmd_templates_view(env_vars, args, output_json)
        else:
            p_tmpl.print_help()

    elif args.command == "sequence":
        if not args.seq_command:
            p_seq.print_help()
            sys.exit(1)
        if args.seq_command == "list":
            cmd_sequence_list(env_vars, args, output_json)
        elif args.seq_command == "create":
            cmd_sequence_create(env_vars, args, output_json)
        elif args.seq_command == "run":
            cmd_sequence_run(env_vars, args, output_json)
        else:
            p_seq.print_help()

    elif args.command == "log":
        cmd_log(env_vars, args, output_json)

    elif args.command == "stats":
        cmd_stats(env_vars, args, output_json)

    elif args.command == "check-inbox":
        cmd_check_inbox(env_vars, args, output_json)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
