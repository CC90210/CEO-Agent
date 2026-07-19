"""
Email Engine - Free send and nurture sequence engine.
Zero paid services. Gmail SMTP (500/day free) + Supabase for tracking.
All credentials loaded from .env.agents (never hardcoded).

Usage:
  python scripts/integrations/email_engine.py send --to "person@email.com" --subject "Subject" --body "Body"
  python scripts/integrations/email_engine.py send --to "person@email.com" --subject "Subject" --body "Body" --html "<h1>Hi</h1>" --lead-id uuid
  python scripts/integrations/email_engine.py send-template --template-id uuid --to "person@email.com" --vars '{"first_name": "John"}'
  python scripts/integrations/email_engine.py templates list
  python scripts/integrations/email_engine.py templates create --name "Welcome" --subject "Welcome to OASIS" --body-html "<h1>Welcome {{first_name}}</h1>" --category welcome --vars '["first_name"]'
  python scripts/integrations/email_engine.py templates view <template_id>
  python scripts/integrations/email_engine.py sequence list
  python scripts/integrations/email_engine.py sequence create --name "New Lead Nurture" --trigger lead_created --steps '[{"delay_hours": 0, "template_name": "Welcome"}]'
  python scripts/integrations/email_engine.py sequence run <sequence_id> --lead-id <lead_id>
  python scripts/integrations/email_engine.py log [--status queued|sent|failed] [--limit 20]
  python scripts/integrations/email_engine.py stats
"""

import argparse
import email
import email.header
import imaplib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPTS_DIR))

try:
    from notify import notify
except ImportError:
    def notify(*a, **kw): return False

from name_utils import sanitize_template_vars as _sanitize_template_vars

# Physical send + CASL enforcement now lives inside send_gateway.py
# (V5.6 chokepoint). cmd_send / cmd_send_template / cmd_sequence_run
# all route through it. The legacy send_email_smtp() below is a
# hard-fail deprecation shim — calling it raises RuntimeError.


# -- Credentials -------------------------------------------


def load_env():
    """Load .env.agents from project root."""
    env_path = Path(__file__).resolve().parent.parent.parent / ".env.agents"
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


# -- HTML detection helpers ---------------------------------
#
# 2026-05-19 incident: an agent invocation passed HTML content to --body
# (a plain-text slot) AND then passed --html "true" to satisfy argparse
# after the previous attempt errored with "--html expects a value". Result:
# body_text correctly held the HTML (which is what email_log.body_preview
# recorded), but body_html="true" won at SMTP-render time, so the brand
# template wrapped the literal string "true" and shipped it. Recipient saw
# a useless email; the actual Meet link never left send_gateway.
#
# Two defenses below — both apply at the CLI boundary so every caller of
# email_engine.py is protected, not just the bridge chat session:
#   1. _looks_like_html() — quick heuristic for "this string contains HTML markup"
#   2. cmd_send rewires: auto-detect HTML in --body, reject non-HTML in --html


_HTML_TAG_RE = re.compile(r"<[A-Za-z][A-Za-z0-9]*(?:\s[^>]*)?/?>")


def _looks_like_html(s: Optional[str]) -> bool:
    """True if the string contains at least one well-formed HTML opener.

    Conservative on purpose — we want false-negatives (treat as plain text)
    over false-positives (treat literal '<5' as HTML). A real HTML body
    will always contain at least one tag like <p>, <a>, <div>, etc.
    """
    if not s or len(s) < 4:
        return False
    return bool(_HTML_TAG_RE.search(s))


# -- SMTP --------------------------------------------------


def send_email_smtp(
    gmail_address,
    app_password,
    to_email,
    subject,
    body_text,
    body_html=None,
    casl_mode="commercial",
):
    """DEPRECATED 2026-04-20 — use scripts/send_gateway.send() instead.

    Every outbound email in this codebase now routes through the V5.6
    chokepoint (send_gateway.py). This function is kept only so
    well-meaning future imports fail loudly rather than silently
    bypassing CASL, cooldown, daily-cap, and the unified ledger.

    The CASL-aware smtplib code that used to live here now lives inside
    send_gateway._send_email_smtp() and is enforced there — you cannot
    accidentally skip it from a business engine.

    Returns: raises RuntimeError. Do not call.
    """
    raise RuntimeError(
        "email_engine.send_email_smtp() is deprecated. Use "
        "send_gateway.send(channel='email', agent_source=..., to_email=..., "
        "subject=..., body_text=..., intent='commercial'|'transactional'). "
        "See skills/send-gateway/SKILL.md for the full contract."
    )


# -- Template rendering -------------------------------------


TEMPLATE_PLACEHOLDER_RE = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")


class TemplateRenderError(ValueError):
    """Raised when a stored email template cannot be rendered safely."""


def normalize_template_vars(variables):
    """Normalize caller-provided template variables before rendering.

    `company_name` is a common CRM/agent spelling; templates use `company`.
    Normalize it here so good data does not fail just because one caller used
    the alternate key. Missing or blank canonical variables still fail closed.
    """
    if not isinstance(variables, dict):
        return {}
    normalized = dict(variables)
    company = normalized.get("company")
    company_name = normalized.get("company_name")
    if (
        (company is None or str(company).strip() == "")
        and company_name is not None
        and str(company_name).strip()
    ):
        normalized["company"] = company_name
    return normalized


def missing_template_variables(template_str, variables) -> list[str]:
    """Return placeholder names that are missing or blank in `variables`."""
    normalized = normalize_template_vars(variables)
    missing: list[str] = []
    for raw_key in TEMPLATE_PLACEHOLDER_RE.findall(template_str or ""):
        key = raw_key.strip()
        value = normalized.get(key)
        if value is None or str(value).strip() == "":
            if key not in missing:
                missing.append(key)
    return missing


def unresolved_template_placeholders(*fields) -> list[str]:
    """Return unresolved `{{...}}` tokens still present in rendered output."""
    tokens: list[str] = []
    for field in fields:
        for token in TEMPLATE_PLACEHOLDER_RE.findall(field or ""):
            name = token.strip()
            if name not in tokens:
                tokens.append(name)
    return tokens


def render_template(template_str, variables, *, strict: bool = True, label: str = "template"):
    """Replace {{variable}} placeholders with values from the variables dict.

    Strict mode is the production default. It rejects missing or blank values
    instead of leaving raw `{{company}}` tokens in an email.
    """
    normalized = normalize_template_vars(variables)
    missing = missing_template_variables(template_str, normalized)
    if strict and missing:
        raise TemplateRenderError(
            f"{label} missing required template variable(s): {', '.join(missing)}"
        )

    def replacer(match):
        key = match.group(1).strip()
        value = normalized.get(key)
        return str(value) if value is not None else match.group(0)

    rendered = TEMPLATE_PLACEHOLDER_RE.sub(replacer, template_str or "")
    if strict:
        leftovers = unresolved_template_placeholders(rendered)
        if leftovers:
            raise TemplateRenderError(
                f"{label} rendered with unresolved placeholder(s): {', '.join(leftovers)}"
            )
    return rendered


def html_to_text(html):
    """Convert simple stored-template HTML to readable plain text."""
    if not html:
        return ""
    import html as html_lib

    text = re.sub(r"(?i)<br\s*/?>", "\n", html)
    text = re.sub(r"(?i)</p\s*>", "\n\n", text)
    text = re.sub(r"(?i)</li\s*>", "\n", text)
    text = re.sub(r"(?i)<li\s*>", "- ", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html_lib.unescape(text)
    lines = [line.rstrip() for line in text.splitlines()]
    return "\n".join(lines).strip()


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
    """Send a one-off email. REWIRED 2026-04-20 → send_gateway.

    Gateway handles: CASL suppression, CASL footer, List-Unsubscribe,
    cooldown, daily cap, lead_interactions ledger, email_log mirror,
    leads.last_contacted_at bump. --transactional flips intent so
    suppressed recipients still receive booking/reminder-style mail.
    """
    from send_gateway import send as gateway_send

    body_text = args.body
    body_html = getattr(args, "html", None)

    # Auto-detect: if --body looks like HTML and --html was not provided,
    # promote --body to the HTML slot and synthesize a plain-text version.
    # Agents reaching for `python scripts/integrations/email_engine.py send` from a chat
    # session routinely write HTML into --body (it's the obvious slot when
    # you have one body to send); this routes correctly without forcing
    # them to learn the --html/--body distinction.
    if body_html is None and _looks_like_html(body_text):
        body_html = body_text
        body_text = re.sub(r"<[^>]+>", "", body_html).strip()

    # Validation: if --html was passed, it MUST contain HTML markup. The
    # 2026-05-19 incident was a non-HTML literal ("true") landing in the
    # HTML slot and winning at SMTP-render time; reject loudly so the next
    # caller iterates instead of shipping garbage.
    if body_html is not None and not _looks_like_html(body_html):
        msg = (
            f"--html must contain actual HTML markup; got "
            f"{body_html[:60]!r}. If you meant plain text, omit --html."
        )
        if output_json:
            print(json.dumps({"status": "failed", "error": msg}, indent=2))
        else:
            print(f"ERROR: {msg}", file=sys.stderr)
        sys.exit(1)

    intent = "transactional" if getattr(args, "transactional", False) else "commercial"
    gw = gateway_send(
        channel="email",
        agent_source="email_engine",
        to_email=args.to,
        lead_id=getattr(args, "lead_id", None),
        subject=args.subject,
        body_text=body_text,
        body_html=body_html,
        brand=getattr(args, "brand", "oasis"),
        intent=intent,
        dry_run=getattr(args, "dry_run", False),
    )

    # Preserve the legacy return shape for any script that parses this output.
    # dry_run is a successful no-op — treat it as success for exit-code purposes.
    success = gw.get("status") in {"sent", "dry_run"}
    status = gw.get("status") if success else "failed"
    result = {
        "status": status,
        "to": args.to,
        "subject": args.subject,
        "log_id": gw.get("interaction_id"),
        "gateway_status": gw.get("status"),
        "error": gw.get("reason") if not success else None,
    }

    if output_json:
        print(json.dumps(result, indent=2))
        return

    if success:
        print(f"Sent to {args.to} - subject: {args.subject}")
        if result["log_id"]:
            print(f"  Logged (id: {result['log_id']})")
    else:
        print(f"ERROR: send failed ({gw.get('status')}): {gw.get('reason')}",
              file=sys.stderr)
        sys.exit(1)


def cmd_send_template(env_vars, args, output_json=False):
    """Render a stored template and send via send_gateway.

    REWIRED 2026-04-20. Template fetch + variable rendering stays here
    (template engine is email_engine's job); physical send + CASL +
    cooldown + logging delegated to send_gateway.
    """
    from send_gateway import send as gateway_send
    db = get_supabase(env_vars)

    try:
        result = db.table("email_templates").select("*").eq("id", args.template_id).execute()
    except Exception as e:
        print(f"ERROR: Could not fetch template: {e}", file=sys.stderr)
        sys.exit(1)
    if not result.data:
        print(f"ERROR: Template not found: {args.template_id}", file=sys.stderr)
        sys.exit(1)

    tmpl = result.data[0]
    variables = normalize_template_vars(json.loads(args.vars) if args.vars else {})
    # Defensive sanitization — 2026-04-25 incident:
    # CSV-imported leads had name="Contact" / "Owner" / "Info" / "there"
    # as placeholder text. Earlier staging code did name.split()[0],
    # which faithfully passed "Contact" into {{first_name}}. Templates
    # rendered "Hi Contact," to 9 real prospects before CC noticed.
    # Template + send paths worked exactly as designed; the data was
    # garbage. The CRM has been scrubbed (placeholder names → empty),
    # but we ALSO defend at render time so a future bad import or
    # caller passing junk first_name can't repeat the failure.
    variables = normalize_template_vars(_sanitize_template_vars(variables))
    # 2026-04-27: auto-inject {{region}} from the lead row if the caller
    # didn't pass one. Templates use this to say "as a fellow local
    # business owner in {{region}}" — geo-rapport without the AI having
    # to think about it. Caller can still override by passing region in
    # --vars; auto-inject only fills the gap.
    if "region" not in variables and getattr(args, "lead_id", None):
        try:
            from region_inference import infer_region
            lead_row = (db.table("leads")
                        .select("company,name,notes,phone")
                        .eq("id", args.lead_id)
                        .execute())
            if lead_row.data:
                variables["region"] = infer_region(lead_row.data[0])
        except Exception as exc:  # noqa: BLE001
            print(f"[email_engine] region auto-inject failed (using "
                  f"'your area'): {exc}", file=sys.stderr)
    variables.setdefault("region", "your area")
    try:
        subject = render_template(tmpl["subject"], variables, label="subject")
        body_html = render_template(tmpl.get("body_html") or "", variables, label="body_html") or None
        body_text_template = tmpl.get("body_text") or ""
        body_text = (
            render_template(body_text_template, variables, label="body_text")
            if body_text_template
            else (html_to_text(body_html) if body_html else subject)
        )
    except TemplateRenderError as exc:
        if output_json:
            print(json.dumps({
                "status": "failed",
                "to": args.to,
                "template_id": args.template_id,
                "template_name": tmpl.get("name"),
                "error": f"template render failed: {exc}",
            }, indent=2))
        else:
            print(f"ERROR: template render failed: {exc}", file=sys.stderr)
        sys.exit(1)

    intent = "transactional" if getattr(args, "transactional", False) else "commercial"
    gw = gateway_send(
        channel="email",
        agent_source="email_engine",
        to_email=args.to,
        lead_id=getattr(args, "lead_id", None),
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        brand=getattr(args, "brand", "oasis"),
        intent=intent,
        metadata={
            "template_id": args.template_id,
            "template_name": tmpl.get("name"),
        },
        dry_run=getattr(args, "dry_run", False),
    )

    success = gw.get("status") in {"sent", "dry_run"}
    result_dict = {
        "status": gw.get("status") if success else "failed",
        "to": args.to,
        "subject": subject,
        "template_id": args.template_id,
        "template_name": tmpl.get("name"),
        "log_id": gw.get("interaction_id"),
        "gateway_status": gw.get("status"),
        "error": gw.get("reason") if not success else None,
    }

    if output_json:
        print(json.dumps(result_dict, indent=2))
        return

    if success:
        print(f"Sent template '{tmpl.get('name')}' to {args.to}")
        if result_dict["log_id"]:
            print(f"  Logged (id: {result_dict['log_id']})")
    else:
        print(f"ERROR: send failed ({gw.get('status')}): {gw.get('reason')}",
              file=sys.stderr)
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
        step_vars = normalize_template_vars({**lead_vars, **step.get("variables", {})})
        # Same defensive sanitization as cmd_send_template — sequence
        # runs pull lead vars from the leads table, where placeholder
        # names ("Contact" / "Owner" / etc) historically slipped in via
        # CSV bulk-import. Junk first_name -> "team" before render.
        step_vars = normalize_template_vars(_sanitize_template_vars(step_vars))
        # 2026-04-27: auto-inject {{region}} from lead data for geo-rapport.
        if "region" not in step_vars and "lead" in dir():
            try:
                from region_inference import infer_region
                step_vars["region"] = infer_region(lead)  # type: ignore[name-defined]
            except Exception:  # noqa: BLE001
                pass
        step_vars.setdefault("region", "your area")

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
        try:
            subject = render_template(tmpl["subject"], step_vars, label="subject")
            body_html = render_template(tmpl.get("body_html") or "", step_vars, label="body_html") or None
            body_text_template = tmpl.get("body_text") or ""
            body_text = (
                render_template(body_text_template, step_vars, label="body_text")
                if body_text_template
                else (html_to_text(body_html) if body_html else subject)
            )
        except TemplateRenderError as exc:
            results.append({"step": i + 1, "template": template_name, "status": "error",
                            "error": f"template render failed: {exc}"})
            continue

        # Step 0 sends immediately via send_gateway; future steps log as queued.
        # Gateway handles CASL, cooldown, daily cap, lead_interactions + email_log.
        if delay_hours == 0:
            from send_gateway import send as gateway_send
            gw = gateway_send(
                channel="email",
                agent_source="email_engine",
                to_email=lead_email,
                lead_id=args.lead_id,
                subject=subject,
                body_text=body_text,
                body_html=body_html,
                brand="oasis",
                intent="commercial",
                metadata={
                    "template_id": tmpl["id"],
                    "sequence_id": args.sequence_id,
                    "step": i + 1,
                },
                dry_run=getattr(args, "dry_run", False),
            )
            success = gw.get("status") == "sent"
            error = None if success else gw.get("reason")
            status = "sent" if success else ("queued" if gw.get("status") == "blocked" else "failed")
        else:
            # Delayed step — log as queued in email_log for visibility; a
            # future scheduler can pick these up and re-enter the sequence.
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

# V2.1 2026-04-11: Poison UID tracking. If an IMAP fetch fails repeatedly
# on the same UID (e.g., corrupt message, encoding error), quarantine it
# by marking it \Seen after 3 failed attempts. This prevents a bad message
# at the head of the UNSEEN queue from blocking newer messages forever.
POISON_UID_PATH = Path(__file__).resolve().parent.parent.parent / "tmp" / "imap_poison_uids.json"
POISON_MAX_ATTEMPTS = 3


def _extract_email_address(from_header: str) -> str:
    """Given a From: header string like '"Jane Doe" <jane@acme.com>', return
    just the lowercased email address. Returns empty string on parse failure."""
    import email.utils
    try:
        _, addr = email.utils.parseaddr(from_header or "")
        return (addr or "").strip().lower()
    except Exception:  # noqa: BLE001
        return ""


def _extract_display_name(from_header: str) -> str:
    """Given a From: header, return just the display name portion (without
    quotes) or empty string. Example: '"Jane Doe" <jane@acme.com>' -> 'Jane Doe'."""
    import email.utils
    try:
        name, _ = email.utils.parseaddr(from_header or "")
        return (name or "").strip()
    except Exception:  # noqa: BLE001
        return ""


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

        # V2.1 2026-04-11: Load poison UID tracker
        poison_state = {}
        try:
            if POISON_UID_PATH.exists():
                with open(POISON_UID_PATH, "r", encoding="utf-8") as pf:
                    poison_state = json.load(pf)
        except Exception:
            poison_state = {}

        for uid in message_ids:
            uid_str = uid.decode() if isinstance(uid, bytes) else str(uid)
            fetch_status, fetch_data = imap.fetch(uid, "(RFC822)")

            # V2.1: Handle fetch failures explicitly. Track failed UIDs and
            # quarantine them by marking \Seen after POISON_MAX_ATTEMPTS
            # failures, so a corrupt message at the head of the queue can't
            # block newer messages forever.
            if fetch_status != "OK" or not fetch_data or fetch_data[0] is None:
                attempts = poison_state.get(uid_str, 0) + 1
                poison_state[uid_str] = attempts
                if attempts >= POISON_MAX_ATTEMPTS:
                    print(
                        f"[email_inbox] Poison UID {uid_str}: quarantining after "
                        f"{attempts} failed fetches — marking \\Seen",
                        file=sys.stderr,
                    )
                    try:
                        imap.store(uid, "+FLAGS", "\\Seen")
                        poison_state.pop(uid_str, None)
                    except Exception as pq_err:
                        print(f"[email_inbox] Quarantine failed: {pq_err}", file=sys.stderr)
                else:
                    print(
                        f"[email_inbox] UID {uid_str}: fetch failed "
                        f"(attempt {attempts}/{POISON_MAX_ATTEMPTS})",
                        file=sys.stderr,
                    )
                continue

            raw_bytes = fetch_data[0][1]
            if not isinstance(raw_bytes, bytes):
                attempts = poison_state.get(uid_str, 0) + 1
                poison_state[uid_str] = attempts
                if attempts >= POISON_MAX_ATTEMPTS:
                    print(
                        f"[email_inbox] Poison UID {uid_str}: non-bytes payload, "
                        f"quarantining after {attempts} attempts",
                        file=sys.stderr,
                    )
                    try:
                        imap.store(uid, "+FLAGS", "\\Seen")
                        poison_state.pop(uid_str, None)
                    except Exception as pq_err:
                        print(f"[email_inbox] Quarantine failed: {pq_err}", file=sys.stderr)
                continue

            # Successfully fetched — clear any poison tracking for this UID
            poison_state.pop(uid_str, None)

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

            # Log to Supabase email_log (legacy SMTP-layer visibility)
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

            # V5.6 — route through inbound_classifier + record_inbound_from_n8n
            # RPC so the unified ledger gets every classified inbound. This
            # is the Python-side replacement for the N8N Supabase node (we
            # leave the 68-node OASIS Inbound Qualifier untouched; it keeps
            # doing auto-reply logic). Fail-closed: if classifier or RPC
            # fails, the email is still marked read and the legacy email_log
            # row is preserved.
            classification: dict = {}
            try:
                from inbound_classifier import classify as _classify_inbound
                classification = _classify_inbound(
                    content=preview,
                    channel="email",
                    subject=subject,
                    from_identity=_extract_email_address(from_addr),
                )
            except Exception as cls_err:
                print(f"[email_inbox] classifier warning: {cls_err}", file=sys.stderr)
                classification = {"sentiment": "unknown", "intent": "other",
                                  "priority": "cold", "confidence": 0.0,
                                  "fallback": True}

            try:
                sender_addr = _extract_email_address(from_addr)
                rpc_params = {
                    "p_from_email": sender_addr,
                    "p_from_name": _extract_display_name(from_addr),
                    "p_subject": subject,
                    "p_content": preview,
                    "p_classification": classification,
                    "p_message_id": uid_str,
                }
                db.rpc("record_inbound_from_n8n", rpc_params).execute()
            except Exception as rpc_err:
                # Don't block the inbox flow on ledger errors — email_log still captures.
                print(f"[email_inbox] ledger write warning: {rpc_err}", file=sys.stderr)

            # V1.0 — bump the OASIS Command Center integrations_health row so
            # the dashboard's green dot lights up. Best-effort.
            try:
                from integration_health import ping as _ping_integration
                _ping_integration("n8n_inbound", client=db, metadata={"source": "email_engine.check_inbox"})
            except Exception as ping_err:
                print(f"[email_inbox] integration health ping warning: {ping_err}", file=sys.stderr)

            # ---- AUTO-SUPPRESS on "STOP" / unsubscribe intent -------------------
            # When the classifier flags intent=unsubscribe OR the subject/body
            # starts with a bare STOP/UNSUBSCRIBE, auto-add the sender to the
            # CASL suppression list. Reply-STOP is now the primary opt-out path
            # (the https://oasisai.work/unsubscribe link was removed from the
            # footer 2026-04-20 since that page didn't exist). This handler is
            # what makes reply-STOP actually legally compliant — CASL requires
            # opt-outs to be processed within 10 business days; this does it
            # within 5 minutes (next scheduler tick).
            intent = (classification or {}).get("intent", "")
            preview_upper = (preview or "").strip().upper()
            subject_upper = (subject or "").strip().upper()
            literal_stop = (
                preview_upper.startswith(("STOP", "UNSUBSCRIBE", "REMOVE ME"))
                or subject_upper.startswith(("STOP", "UNSUBSCRIBE", "REMOVE ME"))
            )
            # Degraded-mode guard (2026-07-18): when the classifier ran in
            # keyword-fallback mode (model/CLI outage, fallback=True), its
            # intent is a coarse substring match — "nothing will stop me from
            # signing" classifies as unsubscribe. An IRREVERSIBLE CASL
            # suppression + lead lost-overwrite must never ride on that. In
            # fallback mode only the literal STOP/UNSUBSCRIBE line-opener
            # counts; ambiguous fallback opt-outs go to CC for manual review
            # below (CASL's 10-business-day window is met either way).
            classifier_stop = (
                intent == "unsubscribe"
                and not (classification or {}).get("fallback")
            )
            is_stop_signal = classifier_stop or literal_stop
            if intent == "unsubscribe" and not is_stop_signal and sender_addr:
                notify(
                    f"POSSIBLE opt-out from {sender_addr} — flagged by the "
                    "degraded keyword classifier (model outage), no literal "
                    f"STOP/UNSUBSCRIBE opener.\nSubject: {subject}\n"
                    "NOT auto-suppressed — review and suppress manually if genuine.",
                    category="email",
                    force=True,
                )
            if is_stop_signal and sender_addr:
                try:
                    sys.path.insert(0, str(Path(__file__).resolve().parent))
                    from casl_compliance import add_suppression
                    add_suppression(sender_addr, reason="auto_reply_stop_2026_04_20")
                    # Mark any matching lead as 'lost' + note
                    try:
                        r = db.table("leads").select("id,notes").eq("email", sender_addr).execute().data or []
                        for lead in r:
                            db.table("leads").update({
                                "status": "lost",
                                "notes": (lead.get("notes") or "").strip() + (
                                    f"\n[{datetime.now(timezone.utc).date().isoformat()}] "
                                    "AUTO-SUPPRESSED — inbound STOP/unsubscribe reply detected. "
                                    "Added to CASL suppression list; gateway will block all "
                                    "future sends."
                                ),
                                "updated_at": datetime.now(timezone.utc).isoformat(),
                            }).eq("id", lead["id"]).execute()
                            # V6.8.3 dual-write — mirror status='lost' into
                            # tenant_records so the dashboard shows the lost
                            # state too. Best-effort, never raises.
                            try:
                                import sys as _esys
                                _esys.path.insert(0, str(Path(__file__).resolve().parent.parent))
                                from lib.lead_sync import sync_lead_status_to_tenant_records  # type: ignore  # noqa: E402
                                sync_lead_status_to_tenant_records(db, lead["id"], "lost")
                            except ImportError:
                                pass
                    except Exception as lead_err:
                        print(f"[email_inbox] lead update on STOP failed: {lead_err}", file=sys.stderr)
                    # Loud Telegram ping so CC knows someone opted out
                    notify(
                        f"STOP received from {sender_addr}\n"
                        f"Subject: {subject}\n"
                        f"Auto-suppressed — they will not receive further emails.",
                        category="email",
                        force=True,
                    )
                    print(f"[email_inbox] AUTO-SUPPRESSED {sender_addr} (reply-STOP intent)",
                          file=sys.stderr)
                except Exception as sup_err:
                    # If suppression fails, surface loudly — this is a compliance risk
                    print(f"[email_inbox] CRITICAL: STOP auto-suppress FAILED for "
                          f"{sender_addr}: {sup_err}", file=sys.stderr)
                    notify(
                        f"CRITICAL: STOP received from {sender_addr} but auto-suppress "
                        f"FAILED: {sup_err}. Add them to suppression list MANUALLY now.",
                        category="email",
                        force=True,
                    )

            # Telegram notification — enriched with classifier intent/priority.
            priority_emoji = {"hot": "🔥", "warm": "♨️", "cold": "❄️", "low": "📥"}.get(
                classification.get("priority"), "📧"
            )
            notify_msg = (
                f"{priority_emoji} {classification.get('intent','email')} "
                f"({classification.get('priority','—')}): {from_addr}\n"
                f"Subject: {subject}\n"
                f"Preview: {preview[:120]}"
            )
            notify(notify_msg)

            # Mark as read
            imap.store(uid, "+FLAGS", "\\Seen")

        # V2.1: Persist poison UID tracker so failure counts survive across runs
        try:
            POISON_UID_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(POISON_UID_PATH, "w", encoding="utf-8") as pf:
                json.dump(poison_state, pf, indent=2)
        except Exception as save_err:
            print(f"[email_inbox] Could not save poison UID state: {save_err}", file=sys.stderr)

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
    p_send.add_argument("--brand", default="oasis",
                        choices=["oasis", "conaugh_mckenna", "nostalgic"],
                        help="Brand identity (drives CASL footer sender + address)")
    p_send.add_argument("--transactional", action="store_true",
                        help="Transactional intent — skip suppression list check "
                             "(CASL s.10(9) exemption). Use for confirmations only.")
    p_send.add_argument("--dry-run", dest="dry_run", action="store_true",
                        help="Validate inputs + run gates but DO NOT send. "
                             "Returns gateway status='dry_run'. Multi-AI safety: "
                             "set BRAVO_FORCE_DRY_RUN=1 to force this for all "
                             "send paths, even from sub-callers that don't pass it.")

    # send-template
    p_st = subparsers.add_parser("send-template", help="Send a stored template")
    p_st.add_argument("--template-id", dest="template_id", required=True, help="Template UUID")
    p_st.add_argument("--to", required=True, help="Recipient email address")
    p_st.add_argument("--vars", default=None, help='Variable substitution JSON: \'{"first_name": "John"}\'')
    p_st.add_argument("--lead-id", dest="lead_id", default=None, help="Lead UUID for log association")
    p_st.add_argument("--brand", default="oasis",
                      choices=["oasis", "conaugh_mckenna", "nostalgic"])
    p_st.add_argument("--transactional", action="store_true",
                      help="Transactional intent (welcome / confirmation / reminder).")
    p_st.add_argument("--dry-run", dest="dry_run", action="store_true",
                      help="Validate template + render + run gates but DO NOT "
                           "send. Multi-AI safety: BRAVO_FORCE_DRY_RUN=1 forces "
                           "this for all send paths.")

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
    p_sr.add_argument("--dry-run", dest="dry_run", action="store_true",
                      help="Run the sequence without actually sending step 0. "
                           "Multi-AI safety: BRAVO_FORCE_DRY_RUN=1 forces this.")

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
