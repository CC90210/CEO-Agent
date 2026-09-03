"""
Email Engine - Free send and nurture sequence engine.
Zero paid services. Gmail SMTP (500/day free) + Turso for tracking.
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
import os
import re
import socket
import time
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPTS_DIR))

# Windows CA-bundle fix (2026-07-28) — see lib/tls_trust.py. The inbox sweep
# reads IMAP (unaffected) but then writes lead_interactions to Turso over
# HTTPS, which is where the AV TLS-scanner root broke it: the sweep printed
# emails fine and then exited 1 on the DB write.
from lib.tls_trust import ensure_os_trust  # noqa: E402

ensure_os_trust()

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


# --- transient-network retry (2026-08-15) ------------------------------------
# The inbox sweep's two failure modes in tmp/cron_failures/ are both transport,
# not logic: `ConnectionResetError [WinError 10054]` on the Gmail TLS handshake,
# and `ValueError: Hrana: ... tcp connect error ... (os error 10060)` when the
# Turso connect in get_supabase() cannot reach the host. Each one exits 1, which
# pages CC. Retrying in-process turns a 2-second network blip into a no-op.
CONNECT_ATTEMPTS = 3
CONNECT_RETRY_SLEEP = 2

# WHY NOT lib/retry.py: that module already exists, is used by 8 integration
# tools, and is the right home for this — but its RetryConfig selects retries by
# EXCEPTION TYPE (`retryable_exceptions`) and exposes only a decorator. Neither
# fits here. The libSQL driver reports transport failures as a plain ValueError
# whose text starts "Hrana:", so a type-based policy would have to list
# ValueError — and that swallows lib/db_turso.quote_ident's guard, which raises
# ValueError for an unsafe SQL identifier. Retrying THAT would burn three
# attempts and then surface a security defect as a network complaint.
#
# So this matches on transport MARKERS, not on type. The clean consolidation is
# an optional predicate on RetryConfig (`retryable_predicate`) with all three
# call sites — here, breeze_live_watch.check_health, and the integration tools —
# routed through it. That edits shared substrate and needs CC's go-ahead first.
# Do NOT "simplify" this by adding ValueError to a type-based retry list.
_TRANSIENT_MARKERS = (
    "hrana", "tcp connect", "connection reset", "forcibly closed", "timed out",
    "timeout", "temporarily unavailable", "os error 10054", "os error 10060",
    "connection aborted", "broken pipe", "eof occurred",
)


def _is_transient(exc: BaseException) -> bool:
    if isinstance(exc, (ConnectionResetError, ConnectionAbortedError,
                        ConnectionRefusedError, TimeoutError, socket.timeout)):
        return True
    if isinstance(exc, OSError):
        return True
    return any(m in str(exc).lower() for m in _TRANSIENT_MARKERS)


def _retry_transient(label: str, fn, attempts: int = CONNECT_ATTEMPTS,
                     sleep_s: int = CONNECT_RETRY_SLEEP):
    """Call fn(), retrying only faults that look like the network dropped.

    A non-transient exception is re-raised on the FIRST attempt — this must not
    become a blanket except that turns a real bug into a slow one.
    """
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - re-raised unless transient
            if attempt == attempts or not _is_transient(exc):
                raise
            print(f"[email_engine] {label}: transient "
                  f"{type(exc).__name__}: {exc} — retry {attempt}/{attempts - 1}",
                  file=sys.stderr)
            time.sleep(sleep_s)


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
    """Create DB client using Bravo project credentials."""
    try:
        from supabase import create_client
    except ImportError:
        print("ERROR: supabase package not installed. Run: pip install supabase", file=sys.stderr)
        sys.exit(1)

    url = env_vars.get("BRAVO_SUPABASE_URL") or "https://turso.compat"
    key = env_vars.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY") or "dummy-turso-key"

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


# -- Turso logging ---------------------------------------


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

# SKIP_SENDERS was removed 2026-07-23. It matched these prefixes on the From
# header and DROPPED the message before classification, which silently destroyed
# every no-reply vendor receipt (Stripe / Google Cloud / Vercel / Apple) — i.e.
# CC's deductible expenses. Sender handling now lives in email_playbook
# .classify_sender(), which treats no-reply as a SIGNAL (never reply) rather
# than a reason to delete. Do not reintroduce a blanket drop here.
IMAP_MAX_EMAILS = 20

# Seconds of wall-clock this sweep will spend on the message loop before
# stopping cleanly. MUST stay comfortably below the scheduler's per-job kill at
# scheduler.py:1116 (300s) — the gap absorbs one in-flight classification plus
# the backfill pass and IMAP teardown. Note the timeout is NOT settable from
# cron_engine for this job: the override at scheduler.py:859-862 applies only to
# action_type "script_run", and this job is "email_inbox_check". So the budget
# has to live here, on this side of the wall.
#
# 210 -> 170 (2026-08-29). 210 + the backfill's 90s reserve is exactly 300 —
# the wall itself, with nothing left for the IMAP teardown and ledger flush that
# follow. Measured that day: backfill_done at 285.8s, process killed at 301.6s,
# so teardown costs ~15s. The budget is now sized so the LAST thing the run can
# legally start still finishes inside the wall with margin:
#   170 budget + 90 worst message + 15 teardown = 275s, under the 300s kill.
SWEEP_BUDGET_SEC = int(os.environ.get("EMPIRE_SWEEP_BUDGET_SEC", "170"))

# Budget a single message must have available before the loop will START it.
# Sized from the measured worst case: claude_cli timeout (90s) + one OpenCode
# fallback (120s). A message admitted with less than this can push the run past
# scheduler.py's 300s kill. Checked as a RESERVE rather than a deadline because
# a deadline alone only says when the last message may begin, not when the run
# will end — the distinction Codex's adversarial review caught.
MESSAGE_RESERVE_SEC = int(os.environ.get("EMPIRE_MESSAGE_RESERVE_SEC", "60"))

# The SAME reserve, for the backfill pass — which had a deadline but no reserve,
# and that gap is what still blew the wall on 2026-08-29 (measured, not
# inferred: the duration instrumentation added the same day recorded the sweep
# at 301.6s against a 300s kill, and the breadcrumbs put 278.5s of it inside the
# backfill). `if now > deadline: break` only decides when the last message may
# BEGIN. One admitted at 209s ran to 285.8s — a classify plus a label plus a
# handoff — and 285.8 + IMAP teardown + ledger flush is 301.
#
# 90s, not 60s: the same worst case the main loop sizes against (claude_cli 90s
# + one OpenCode fallback 120s) applies here, and the one observed overrun cost
# ~76s. Above the measured value, not at it.
BACKFILL_RESERVE_SEC = int(os.environ.get("EMPIRE_BACKFILL_RESERVE_SEC", "90"))

# Post-mortem breadcrumb trail for the sweep.
#
# WHY (2026-08-28): this job has been dying with exit 3221225480 and EMPTY
# stdout AND stderr — six recorded failures across three days with not one line
# of evidence between them, because the captured pipes are lost when the run is
# killed. Six failures that could not be diagnosed at all is the actual defect;
# the crash is secondary. Every stage below appends one flushed JSON line to
# state/email_sweep.log, so the NEXT failure says exactly where it stopped, how
# long it had been running, and on which message. Rotated by the existing
# hooks/rotate_logs.py sweep over state/*.log.
SWEEP_PROGRESS_LOG = (Path(__file__).resolve().parent.parent.parent
                      / "state" / "email_sweep.log")


def _log_sweep_progress(stage: str, started: float | None = None, **fields) -> None:
    """One flushed line per stage. Never raises, never blocks the sweep."""
    try:
        # pid, because this log is shared and two overlapping sweeps interleave
        # into it indistinguishably. On 2026-08-29 two `start` records landed
        # 0.9s apart and there was no way to tell one process running the sweep
        # twice from two processes running it once — which are different bugs
        # with different fixes. One field makes that answerable forever.
        rec = {"ts": datetime.now(timezone.utc).isoformat(),
               "pid": os.getpid(), "stage": stage}
        if started is not None:
            rec["elapsed_s"] = round(time.monotonic() - started, 1)
        rec.update(fields)
        SWEEP_PROGRESS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(SWEEP_PROGRESS_LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, default=str) + "\n")
            fh.flush()
            os.fsync(fh.fileno())  # a kill must not take the evidence with it
    except Exception:  # noqa: BLE001
        pass

# V2.1 2026-04-11: Poison UID tracking. If an IMAP fetch fails repeatedly
# on the same UID (e.g., corrupt message, encoding error), quarantine it
# by marking it \Seen after 3 failed attempts. This prevents a bad message
# at the head of the UNSEEN queue from blocking newer messages forever.
POISON_UID_PATH = Path(__file__).resolve().parent.parent.parent / "tmp" / "imap_poison_uids.json"
POISON_MAX_ATTEMPTS = 3

# Idempotency ledger — keyed by the STABLE RFC Message-ID (not the IMAP
# sequence number, which changes every session). This is what stops the
# reprocessing loop: draft_hold and handoff_atlas deliberately leave mail
# UNREAD as CC's / Atlas's queue, but the 5-minute UNSEEN sweep re-picks
# unread mail, so without this every held email was re-classified, re-drafted,
# re-handed-off and re-ledgered on every tick (runaway LLM cost + duplicate
# rows + Telegram spam). Same on-disk-JSON idiom as POISON_UID_PATH above.
PROCESSED_MSGIDS_PATH = (Path(__file__).resolve().parent.parent.parent
                         / "tmp" / "inbound_processed_msgids.json")
PROCESSED_MSGIDS_MAX = 5000  # ring-buffer cap so the file can't grow unbounded


def _load_processed_msgids() -> dict:
    try:
        if PROCESSED_MSGIDS_PATH.exists():
            data = json.loads(PROCESSED_MSGIDS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:  # noqa: BLE001
        pass
    return {}


def _save_processed_msgids(seen: dict) -> None:
    try:
        # Keep only the most-recent N by stored timestamp so this never grows
        # without bound on a busy mailbox.
        if len(seen) > PROCESSED_MSGIDS_MAX:
            newest = sorted(seen.items(), key=lambda kv: kv[1], reverse=True)[:PROCESSED_MSGIDS_MAX]
            seen = dict(newest)
        PROCESSED_MSGIDS_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = PROCESSED_MSGIDS_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(seen), encoding="utf-8")
        os.replace(tmp, PROCESSED_MSGIDS_PATH)
    except Exception as exc:  # noqa: BLE001
        print(f"[email_inbox] could not persist processed-msgid ledger: {exc}", file=sys.stderr)


# READ-BEFORE-SWEEP BACKFILL (2026-08-23) — closes the gap that lost the Kimi
# receipt. The sweep searches UNSEEN only, so any message CC reads within the
# 5-minute window between ticks becomes SEEN before the sweep ever fetches it
# and escapes classification FOREVER: no ledger row, no financial hand-off, no
# Gmail label, no booking. That is exactly what happened to the NOVASCENT/Kimi
# Stripe receipt on 2026-08-23 — it sat read-and-unlabeled until backfilled by
# hand.
#
# The fix sweeps SEEN mail too, but FINANCIAL-ONLY: a message CC already read
# is a message a human is already handling, so replies/drafts/archives/Telegram
# pings would be noise — the ONE thing that must still happen automatically is
# the Atlas hand-off (label + booking), because reading a receipt is not the
# same as booking it. Everything non-financial is just recorded in the msgid
# ledger and left alone.
#
# Cost control: a persisted IMAP UID high-water mark means each tick examines
# only messages that BECAME candidates since the last tick (usually zero), not
# the whole mailbox. First run seeds from the last SEEN_BACKFILL_INIT_DAYS
# days. All fetches are BODY.PEEK so read-state is never altered.
SEEN_BACKFILL_STATE_PATH = (Path(__file__).resolve().parent.parent.parent
                            / "tmp" / "seen_backfill_state.json")
SEEN_BACKFILL_INIT_DAYS = 2
SEEN_BACKFILL_MAX_PER_TICK = 40  # bound tick duration; leftovers roll to next tick


def read_mail_financial_decision(cls: dict, fin_threshold: float = 0.65) -> str:
    """Pure decision for a message CC already read: 'handoff' | 'notify' | 'skip'.

    Same confidence gate as the UNSEEN path (decide_action): a low-confidence
    financial read must NOT reach Atlas — the consumer would file a
    non-financial legal notice under Receipts/, which is the mislabeling this
    pipeline exists to prevent. Proven live 2026-08-23: a building quiet-hours
    notice at conf 0.45 was handed off before this gate existed (event
    cancelled same day). Degraded (keyword-fallback) financial reads notify
    quietly — never auto-book from a guess, never be silent about money.
    Unit-tested like stop_signal_decision; keep it pure."""
    if cls.get("category") != "financial_legal":
        return "skip"
    if cls.get("fallback"):
        return "notify"
    confidence = float(cls.get("confidence", 0.0) or 0.0)
    return "handoff" if confidence > fin_threshold else "skip"


def _backfill_read_before_sweep(imap, db, processed_msgids: dict,
                                deadline: float | None = None) -> int:
    """Classify recently-SEEN mail the UNSEEN sweep never saw; hand financial
    mail to Atlas. Returns the number of messages newly examined. Never raises
    — a backfill failure must not take down the main sweep."""
    handed = examined = labelled = 0
    try:
        state = {}
        try:
            if SEEN_BACKFILL_STATE_PATH.exists():
                state = json.loads(SEEN_BACKFILL_STATE_PATH.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            state = {}
        last_uid = int(state.get("last_uid") or 0)

        if last_uid:
            status, data = imap.uid("SEARCH", None, f"(SEEN UID {last_uid + 1}:*)")
        else:
            since = (datetime.now(timezone.utc)
                     - timedelta(days=SEEN_BACKFILL_INIT_DAYS)).strftime("%d-%b-%Y")
            status, data = imap.uid("SEARCH", None, f"(SEEN SINCE {since})")
        if status != "OK":
            return 0
        # Gmail quirk: "N:*" always matches the highest-UID message even when
        # its UID < N, so filter client-side rather than trusting the range.
        uids = sorted(
            u for u in (int(x) for x in (data[0].split() if data and data[0] else []))
            if u > last_uid
        )[:SEEN_BACKFILL_MAX_PER_TICK]

        for uid_int in uids:
            # The backfill runs AFTER the main loop and classifies up to
            # SEEN_BACKFILL_MAX_PER_TICK messages, so before this it could blow
            # the scheduler's 300s wall entirely on its own — the main loop's
            # budget did not reach here. Both failures on 2026-08-28 (03:20:53
            # and 04:05:42) were kills at exactly 300s after their tick started.
            # Stopping here is free: last_uid is only advanced for messages
            # actually examined, so the next tick resumes at the same place.
            # RESERVE, not deadline (fixed 2026-08-29). `> deadline` admitted a
            # message with one second left and then ran it to completion; the
            # completion is what overruns, not the admission. See
            # BACKFILL_RESERVE_SEC for the measurement.
            remaining = None if deadline is None else deadline - time.monotonic()
            if remaining is not None and remaining < BACKFILL_RESERVE_SEC:
                print(f"[seen_backfill] {remaining:.0f}s left, need "
                      f"{BACKFILL_RESERVE_SEC}s to start a message — deferring "
                      f"{len(uids) - uids.index(uid_int)} message(s) to the next tick",
                      file=sys.stderr)
                _log_sweep_progress("backfill_budget_reached",
                                    remaining_s=round(remaining, 1),
                                    deferred=len(uids) - uids.index(uid_int))
                break
            uid = str(uid_int)
            # Cheap header peek first: most candidates are mail the UNSEEN sweep
            # already processed (held mail CC later read), and the ledger skips
            # them for the price of one header round-trip instead of a full body.
            h_status, h_data = imap.uid(
                "FETCH", uid, "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])")
            if h_status != "OK" or not h_data or h_data[0] is None:
                # Do NOT advance the mark past a failed fetch — retry next tick.
                break
            raw_hdr = h_data[0][1] if isinstance(h_data[0], tuple) else b""
            hdr_msg = email.message_from_bytes(raw_hdr if isinstance(raw_hdr, bytes) else b"")
            rfc_message_id = (hdr_msg.get("Message-ID") or "").strip() or f"uid:{uid}"
            examined += 1

            if rfc_message_id in processed_msgids:
                last_uid = uid_int
                continue

            f_status, f_data = imap.uid("FETCH", uid, "(BODY.PEEK[])")
            if f_status != "OK" or not f_data or f_data[0] is None \
                    or not isinstance(f_data[0], tuple):
                break
            msg = email.message_from_bytes(f_data[0][1])
            from_addr = _decode_header_value(msg.get("From", ""))
            subject = _decode_header_value(msg.get("Subject", "(no subject)"))
            body_full = extract_body_full(msg)

            try:
                from inbound_classifier import classify_category
                cls = classify_category(
                    content=(body_full or "")[:6000],
                    subject=subject,
                    from_identity=_extract_email_address(from_addr),
                    is_bulk=bool(msg.get("List-Unsubscribe")),
                )
            except Exception as cls_err:  # noqa: BLE001
                print(f"[seen_backfill] classifier failed on {rfc_message_id}: "
                      f"{cls_err} — will retry next tick", file=sys.stderr)
                break  # don't advance the mark; don't ledger it

            confidence = float(cls.get("confidence", 0.0) or 0.0)
            try:
                from email_brain import _resolve_config
                fin_threshold = float(_resolve_config(None)["financial_threshold"])
            except Exception:  # noqa: BLE001
                fin_threshold = 0.65  # DEFAULT_FINANCIAL_THRESHOLD
            # File it BEFORE deciding whether it can be booked. This path
            # handles mail CC opened on his phone before the 5-minute sweep saw
            # it — which is exactly what a forwarded receipt looks like — and it
            # previously skipped anything the model called low_priority, so a
            # forwarded invoice read on a phone was never labelled at all.
            fin_label = None
            try:
                from lib.financial_labels import assess
                from lib.gmail_labels import apply_label as _apply_gmail_label
                _fin = assess({
                    "from": from_addr,
                    "subject": subject,
                    "body": body_full,
                    "attachments": _extract_attachment_meta(msg),
                    "date": msg.get("Date"),
                }, prefilter_route=cls.get("route_target"))
                if _fin.get("is_financial") and _fin.get("label"):
                    # UID addressing: this loop fetches with imap.uid(...).
                    _apply_gmail_label(imap, uid, _fin["label"], use_uid=True)
                    fin_label = _fin["label"]
                    labelled += 1
            except Exception as label_err:  # noqa: BLE001
                print(f"[seen_backfill] LABEL FAILED on {rfc_message_id}: "
                      f"{label_err}", file=sys.stderr)
                try:
                    notify(f"⚠️ FINANCIAL LABEL FAILED (read-before-sweep)\n"
                           f"From: {from_addr}\nSubject: {subject}\n"
                           f"Error: {label_err}", category="email")
                except Exception:  # noqa: BLE001
                    pass

            if fin_label:
                # Logged OUTSIDE the labelling try on purpose. This stream is
                # cp1252 on Windows and real subjects carry non-ASCII (the
                # Kraken statement subjects use a smart apostrophe), so a print
                # inside that block could raise AFTER a successful STORE and
                # report a filed receipt as LABEL FAILED — an inverted signal,
                # which is the class of bug this whole change exists to remove.
                _safe_subj = (subject or "")[:60].encode("ascii", "replace").decode()
                print(f"[seen_backfill] filed -> {fin_label}: {_safe_subj}",
                      file=sys.stderr)

            decision = read_mail_financial_decision(cls, fin_threshold)
            if decision == "handoff":
                from email_brain import handoff_to_atlas
                ok = handoff_to_atlas({
                    "from": from_addr,
                    "from_identity": _extract_email_address(from_addr),
                    "subject": subject,
                    "body": body_full,
                    "rfc_message_id": rfc_message_id,
                    "attachments": _extract_attachment_meta(msg),
                    # Already filed by Bravo above; Atlas should reuse this
                    # label rather than deriving a different one.
                    "gmail_label": fin_label,
                }, db=db)
                if ok:
                    handed += 1
                    print(f"[seen_backfill] read-before-sweep financial mail handed "
                          f"to Atlas: {subject[:70]} (conf {confidence:.2f})",
                          file=sys.stderr)
                else:
                    # Refused hand-offs (no stable Message-ID / no sender) can
                    # never be booked automatically — say so once, quietly.
                    print(f"[seen_backfill] financial mail REFUSED hand-off "
                          f"(unresolvable payload): {subject[:70]}", file=sys.stderr)
            elif decision == "notify":
                # Degraded (keyword-fallback) financial read on already-seen
                # mail: never auto-book from a guess, but never be silent about
                # money either. Low-confidence NON-degraded reads are skipped
                # entirely — CC already read the mail, and the model itself
                # judged it probably-not-financial.
                try:
                    notify(
                        f"Possible financial email you read before the sweep — "
                        f"NOT auto-booked (degraded classifier).\n"
                        f"From: {from_addr}\nSubject: {subject}",
                        category="email",
                    )
                except Exception:  # noqa: BLE001
                    pass

            processed_msgids[rfc_message_id] = datetime.now(timezone.utc).isoformat()
            # Checkpoint per message: this pass runs AFTER the main loop, so on a
            # 300s kill it was the most likely work to be discarded entirely.
            _save_processed_msgids(processed_msgids)
            last_uid = uid_int

        state["last_uid"] = last_uid
        SEEN_BACKFILL_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = SEEN_BACKFILL_STATE_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state), encoding="utf-8")
        os.replace(tmp, SEEN_BACKFILL_STATE_PATH)

        if examined:
            print(f"[seen_backfill] examined {examined} read message(s), "
                  f"{labelled} filed by label, {handed} handed to Atlas",
                  file=sys.stderr)
    except Exception as exc:  # noqa: BLE001
        print(f"[seen_backfill] backfill error (main sweep unaffected): {exc}",
              file=sys.stderr)
    return examined


REVIEW_QUEUE_PATH = (Path(__file__).resolve().parent.parent.parent
                     / "tmp" / "review_harvest_queue.json")


def _enqueue_review_harvest(ping: dict, rfc_message_id: str) -> None:
    """Queue a (repo, pr) for the review-harvest cron. Best-effort, never raises.

    A queue rather than an inline harvest: the inbox sweep must stay fast and
    must not block on gh + a fix run. The 'Review Harvest' cron drains this.
    Keyed by repo#pr so ten CodeRabbit emails on one PR enqueue one job.
    """
    try:
        queue = {}
        if REVIEW_QUEUE_PATH.exists():
            try:
                loaded = json.loads(REVIEW_QUEUE_PATH.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    queue = loaded
            except Exception:  # noqa: BLE001
                queue = {}

        # A workflow-failure mail has no PR number, so it keys on repo+branch.
        # review_loop resolves that branch to a PR via `gh pr list --head`; an
        # entry with neither a PR nor a branch can never become actionable, so
        # the loop drops it rather than letting it accumulate forever.
        if ping.get("pr"):
            key = f"{ping['repo']}#{ping['pr']}"
        elif ping.get("branch"):
            key = f"{ping['repo']}@{ping['branch']}"
        else:
            key = ping["repo"]
        entry = queue.get(key) or {"repo": ping["repo"], "pr": ping.get("pr"),
                                   "branch": ping.get("branch"),
                                   "kinds": [], "message_ids": [], "count": 0}
        if ping.get("branch") and not entry.get("branch"):
            entry["branch"] = ping["branch"]
        if ping["kind"] not in entry["kinds"]:
            entry["kinds"].append(ping["kind"])
        if rfc_message_id not in entry["message_ids"]:
            entry["message_ids"] = (entry["message_ids"] + [rfc_message_id])[-10:]
        entry["count"] = int(entry.get("count", 0)) + 1
        entry["last_seen"] = datetime.now(timezone.utc).isoformat()
        queue[key] = entry

        REVIEW_QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = REVIEW_QUEUE_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(queue, indent=2), encoding="utf-8")
        os.replace(tmp, REVIEW_QUEUE_PATH)
        print(f"[email_inbox] review queued: {key} ({ping['kind']})", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001
        print(f"[email_inbox] could not queue review harvest: {exc}", file=sys.stderr)


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


def _strip_html(html: str) -> str:
    """Turn an HTML email part into readable text.

    Drops <style>/<script>/<head> wholesale (otherwise CSS dominates the first
    few hundred characters of a vendor receipt), converts block tags to
    newlines so line structure survives, strips remaining tags, and unescapes
    entities.
    """
    if not html:
        return ""
    s = re.sub(r"(?is)<(script|style|head)[^>]*>.*?</\1>", " ", html)
    s = re.sub(r"(?i)<br\s*/?>", "\n", s)
    s = re.sub(r"(?i)</(p|div|tr|li|h[1-6]|table)>", "\n", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    try:
        import html as _htmlmod
        s = _htmlmod.unescape(s)
    except Exception:  # noqa: BLE001
        pass
    # Collapse runs of spaces/tabs but KEEP newlines (forward-header parsing and
    # salutation matching are line-anchored).
    s = re.sub(r"[ \t\xa0]+", " ", s)
    s = re.sub(r"\n\s*\n\s*\n+", "\n\n", s)
    return s.strip()


def _decode_part(part) -> str:
    payload = part.get_payload(decode=True)
    if not payload:
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except (LookupError, UnicodeDecodeError):
        return payload.decode("utf-8", errors="replace")


def extract_body_full(msg) -> str:
    """Full readable body text of a message. UTF-8 preserved, newlines kept.

    2026-07-23 — three defects this replaces, all of which degraded EVERY
    downstream decision:
      * text/plain ONLY: an HTML-only message (the norm for Stripe / bank /
        SaaS billing mail) produced an EMPTY body, so the classifier saw just
        the subject and sender. Now falls back to the HTML part, cleaned.
      * 200-char cap on the only body artifact: the classifier, the drafter,
        the ledger and the hand-off all shared one 200-char string. Callers now
        slice what they need from the full text.
      * ASCII coercion: every accent, curly quote and emoji became '?'. That
        matters for French mail now that CC operates from Montreal.
    """
    text_parts: list[str] = []
    html_parts: list[str] = []
    try:
        if msg.is_multipart():
            for part in msg.walk():
                if part.is_multipart():
                    continue
                disp = str(part.get("Content-Disposition") or "").lower()
                if "attachment" in disp:
                    continue
                ctype = part.get_content_type()
                if ctype == "text/plain":
                    text_parts.append(_decode_part(part))
                elif ctype == "text/html":
                    html_parts.append(_decode_part(part))
        else:
            raw = _decode_part(msg)
            if msg.get_content_type() == "text/html":
                html_parts.append(raw)
            else:
                text_parts.append(raw)
    except Exception as exc:  # noqa: BLE001
        print(f"[email_inbox] body extract warning: {exc}", file=sys.stderr)

    body = "\n".join(p for p in text_parts if p and p.strip()).strip()
    if not body:
        body = _strip_html("\n".join(html_parts)).strip()
    # Normalise line endings; keep the text itself intact (UTF-8, accents, case).
    return body.replace("\r\n", "\n").replace("\r", "\n")


def _extract_text_preview(msg, max_chars=200):
    """Short single-line preview for logs//email_log. Built from the full body
    so an HTML-only message no longer previews as empty. ASCII-coerced because
    legacy log/notify surfaces on Windows expect it — use extract_body_full()
    for anything that feeds a decision."""
    preview = " ".join(extract_body_full(msg).split())
    preview = preview.encode("ascii", errors="replace").decode("ascii")
    return preview[:max_chars]


def stop_signal_decision(classification, preview, subject):
    """CASL auto-suppress decision for an inbound reply.

    Returns (is_stop_signal, needs_manual_review):
      is_stop_signal      — irreversibly suppress (CASL list) + mark lead lost.
      needs_manual_review — the DEGRADED keyword classifier (model outage,
                            fallback=True) said unsubscribe but there is no
                            literal STOP/UNSUBSCRIBE line-opener; ping CC
                            instead of auto-killing what may be a hot lead
                            ("nothing will stop me from signing" matches the
                            fallback's substring test). CASL's 10-business-day
                            window is met either way: literal openers still
                            suppress instantly, ambiguous ones go to review.

    Pure function — unit-tested directly (scripts/tests, CASL-critical).
    """
    intent = (classification or {}).get("intent", "")
    preview_upper = (preview or "").strip().upper()
    subject_upper = (subject or "").strip().upper()
    literal_stop = (
        preview_upper.startswith(("STOP", "UNSUBSCRIBE", "REMOVE ME"))
        or subject_upper.startswith(("STOP", "UNSUBSCRIBE", "REMOVE ME"))
    )
    classifier_stop = (
        intent == "unsubscribe"
        and not (classification or {}).get("fallback")
    )
    is_stop_signal = classifier_stop or literal_stop
    needs_manual_review = intent == "unsubscribe" and not is_stop_signal
    return is_stop_signal, needs_manual_review


def _email_brain_enabled(env_vars) -> bool:
    """EMAIL_BRAIN_ENABLED gates the native multi-brain router (the n8n "OASIS
    Inbound Qualifier" replacement). OFF by default so the inbox loop behaves
    exactly as before until it's switched on.

    Reads .env.agents first, then falls back to the process environment — so the
    flag can live in .env.agents OR be injected by PM2 (ecosystem.config.js env
    block, which is how bravo-scheduler sets it and how it reaches this script
    as an inherited subprocess env). Same precedence email_brain._env_flag uses.
    """
    v = ""
    try:
        v = env_vars.get("EMAIL_BRAIN_ENABLED", "") or ""
    except Exception:
        v = ""
    if not str(v).strip():
        v = os.environ.get("EMAIL_BRAIN_ENABLED", "")
    return str(v).strip().lower() in ("1", "true", "yes", "on")


_KNOWN_CLIENT_STATUSES = ("client", "active", "active_client", "won", "customer")

# Which agent owns each brain. Financial & Legal is Atlas's (CFO); everything
# else stays with Bravo. Mirrors the agent_label the n8n routing contract set.
_AGENT_LABEL_BY_CATEGORY = {
    "financial_legal": "atlas",
    "technical_support": "bravo",
    "business_opportunity": "bravo",
    "low_priority": "bravo",
}


def _routing_contract(outcome: dict, classification: dict) -> dict:
    """Build the routing contract the Command Center renders for an inbound mail.

    This is the native form of the `<oasis-routing>` JSON each n8n agent emitted
    and the "Parse routing (…)" nodes POSTed to /api/inbound/n8n. Same fields —
    intent / agent_action / priority / agent_label / summary — so the dashboard
    shows which brain handled the mail and what it actually did, rather than a
    bare intent with no outcome.
    """
    category = outcome.get("category") or "low_priority"
    return {
        "intent": category,
        "legacy_intent": classification.get("intent"),
        "agent_action": outcome.get("action"),
        "priority": classification.get("priority") or "cold",
        "agent_label": _AGENT_LABEL_BY_CATEGORY.get(category, "bravo"),
        "summary": (outcome.get("reason") or "")[:500],
        "confidence": outcome.get("confidence"),
        "sent": bool(outcome.get("sent")),
        "drafted": bool(outcome.get("drafted")),
        "archived": bool(outcome.get("archived")),
        "handed_off": bool(outcome.get("handed_off")),
        "notified": bool(outcome.get("notified")),
        # Where this email was actually FILED, so the Command Center shows the
        # outcome rather than the intent. `gmail_label: null` on a row whose
        # financial_document is true is the signal that filing failed — the
        # thing that was previously invisible.
        "gmail_label": outcome.get("label"),
        "financial_document": bool(outcome.get("financial_document")),
        "label_error": outcome.get("label_error"),
        "routing_extracted": True,
        "source": "email_brain",
    }


def _extract_attachment_meta(msg) -> list:
    """Lightweight attachment metadata (filename, content_type, size) for the
    Atlas financial hand-off — NOT the raw bytes (Atlas's consumer fetches those
    from Gmail via rfc_message_id when it processes the hand-off). Best-effort;
    returns [] on any error."""
    out: list = []
    try:
        if not msg.is_multipart():
            return out
        for part in msg.walk():
            if part.is_multipart():
                continue
            disp = str(part.get("Content-Disposition") or "").lower()
            filename = part.get_filename()
            if "attachment" not in disp and not filename:
                continue
            try:
                payload = part.get_payload(decode=True)
                size = len(payload) if payload else 0
            except Exception:
                size = 0
            out.append({
                "filename": filename or "(unnamed)",
                "content_type": part.get_content_type(),
                "size": size,
            })
    except Exception:
        return []
    return out


def _is_known_client(db, email_addr) -> bool:
    """True if the sender is an existing OASIS client (not a cold lead). Gates
    Technical-Support auto-replies. Best-effort; False on any error (fail-safe:
    the brain then drafts-and-holds instead of auto-sending)."""
    if not email_addr:
        return False
    try:
        rows = (db.table("leads").select("status")
                .eq("email", email_addr.strip().lower()).limit(1).execute().data) or []
        return bool(rows) and (rows[0].get("status") or "").strip().lower() in _KNOWN_CLIENT_STATUSES
    except Exception:
        return False


def cmd_check_inbox(env_vars, args, output_json=False):
    """
    Connect to Gmail IMAP, fetch UNSEEN emails, log them to Turso,
    notify via Telegram, then mark them as SEEN.

    When EMAIL_BRAIN_ENABLED is set, each non-STOP email is routed through
    email_brain.process_email (the native n8n classifier replacement): it
    drafts/sends replies via send_gateway, hands Financial & Legal to Atlas,
    archives low-priority, and controls its own read-state. Off by default.
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

    # First breadcrumb, before ANY network call. Six failures on this job have
    # produced empty stdout AND stderr, so the open question was whether the run
    # even reached application code. From now on it says so.
    _run_started = time.monotonic()
    _log_sweep_progress("start")

    # Both of these are network connects and both have failed transiently in
    # production (tmp/cron_failures/): the Turso connect with os error 10060,
    # the Gmail TLS handshake with WinError 10054.
    db = _retry_transient("turso connect", lambda: get_supabase(env_vars))
    _log_sweep_progress("db_connected", _run_started)
    imap = None
    found_emails = []

    try:
        imap = _retry_transient(
            "imap connect", lambda: imaplib.IMAP4_SSL("imap.gmail.com", 993))
        imap.socket().settimeout(30)
        imap.login(address, password)
        imap.select("INBOX")
        _log_sweep_progress("imap_ready", _run_started)

        status, data = imap.search(None, "UNSEEN")
        if status != "OK":
            raise RuntimeError(f"IMAP search failed: {status}")
        _log_sweep_progress("searched", _run_started,
                            unseen=len(data[0].split()) if data and data[0] else 0)

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

        # 2026-07-24: processed-message idempotency ledger (see the guard below).
        processed_msgids = _load_processed_msgids()

        # WALL-CLOCK BUDGET (2026-08-28). scheduler.py:1116 kills this job at
        # 300s, and that kill is a SIGKILL-equivalent: no cleanup, no summary,
        # no IMAP logout. On quota-degraded days a single classification cost
        # 172.5s, so the sweep reliably died part-way through the mailbox and
        # the operator's only evidence was a truncated log in tmp/cron_failures.
        #
        # Stopping ourselves a minute early turns that into an ordinary partial
        # run: remaining mail stays UNSEEN and the next 5-minute tick picks it
        # up. This bounds the run WITHOUT capping how much mail we will ever
        # process, which a smaller IMAP_MAX_EMAILS would have done.
        sweep_started = time.monotonic()
        # DEADLINE IS ANCHORED TO PROCESS START, NOT TO THIS POINT (2026-08-28).
        # The first version anchored it here — after the Turso connect, the IMAP
        # login and the UNSEEN search — so the budget silently excluded the
        # startup it was meant to protect against. The breadcrumbs measured that
        # startup at 38.5s on this machine (process spawn is AV-slowed to ~4s and
        # the DB connect dominates the rest), so a 210s budget was really
        # 39 + 210 + one in-flight message, and the job was still killed at the
        # 300s wall — 21:18:57 start, FAILED (timeout) recorded at 21:22:58.
        #
        # Anchoring to _run_started makes SWEEP_BUDGET_SEC mean what it says:
        # the whole run, startup included, leaving the remaining ~90s of the
        # wall as headroom for the one message already in flight.
        sweep_deadline = _run_started + SWEEP_BUDGET_SEC
        _log_sweep_progress("budget_anchored", _run_started,
                            budget_s=SWEEP_BUDGET_SEC,
                            startup_cost_s=round(sweep_started - _run_started, 1))
        deferred = 0
        _log_sweep_progress("loop_start", _run_started,
                            queued=len(message_ids), budget_s=SWEEP_BUDGET_SEC)

        for uid in message_ids:
            # ADMISSION RESERVE, not just a deadline. Codex's adversarial review
            # caught that checking `now > deadline` alone lets a message start
            # with one second left and then run for the full model timeout plus
            # fallback (~210s worst case) — so SWEEP_BUDGET_SEC was never a bound
            # on the run, only on when the LAST message may BEGIN. Requiring a
            # per-message reserve is what actually keeps the run inside the
            # scheduler's 300s kill window.
            #
            # This is best-effort, and deliberately so: with per-message ledger
            # checkpointing above, an overrun that does get killed no longer
            # loses mail — it wastes one partial message. Bounding the frequency
            # is worth doing; claiming a hard guarantee would not be true.
            remaining = sweep_deadline - time.monotonic()
            if remaining < MESSAGE_RESERVE_SEC:
                deferred = len(message_ids) - message_ids.index(uid)
                print(f"[email_inbox] only {remaining:.0f}s of the {SWEEP_BUDGET_SEC}s "
                      f"budget left (need {MESSAGE_RESERVE_SEC}s to start a message) — "
                      f"stopping cleanly with {deferred} message(s) left UNSEEN for the "
                      f"next tick", file=sys.stderr)
                _log_sweep_progress("budget_reached", _run_started,
                                    deferred=deferred, remaining_s=round(remaining, 1))
                break
            _log_sweep_progress("message_start", _run_started,
                                idx=message_ids.index(uid) + 1, of=len(message_ids))
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

            # IDEMPOTENCY GUARD (2026-07-24) — the stable RFC Message-ID, NOT the
            # IMAP sequence number. If we've already processed this message,
            # skip ALL work (classification, LLM, ledger, brain, hand-off) and
            # move on WITHOUT marking it read — held/handed-off mail is left
            # unread on purpose as CC's / Atlas's review queue, and this is what
            # keeps the UNSEEN sweep from redoing that work every 5 minutes.
            rfc_message_id = (msg.get("Message-ID") or "").strip() or f"uid:{uid_str}"
            if rfc_message_id in processed_msgids:
                continue

            # SENDER TRIAGE (2026-07-23) — replaces a blanket drop.
            #
            # This used to be: `if any(skip in from_lower for skip in
            # SKIP_SENDERS): mark \Seen; continue` — i.e. every message from a
            # no-reply address was marked read and discarded BEFORE
            # classification, the ledger, the brain and the Atlas hand-off.
            # Stripe, Google Cloud, Vercel, Apple and Adobe all send receipts
            # from no-reply addresses, so that quietly destroyed CC's
            # deductible expense records. The n8n workflow never dropped these
            # — it treated "no-reply" as a SIGNAL and let the classifier route
            # them (they are overwhelmingly Financial & Legal).
            #
            # So: classify everything, reply to almost nothing. The playbook
            # decides who may receive a generated reply.
            body_full = extract_body_full(msg)

            # FORWARD PARSING (2026-07-24) — wire the built-but-dead helpers.
            # When CC forwards a vendor invoice or a lead thread INTO the inbox,
            # the envelope From is CC. Without this, native classifies it as mail
            # FROM CC and both the ledger and the sender triage are wrong. If the
            # message is a forward and the original sender is recoverable, we
            # classify/route on THAT address instead (the reply address, however,
            # is intentionally left to CC — we never auto-reply to a forward).
            forwarded_from = None
            unresolved_forward = False
            try:
                from email_playbook import (is_forwarded, extract_forwarded_sender,
                                            UNKNOWN_FORWARD_SENDER)
                if is_forwarded(subject, body_full):
                    # Body first, then the envelope From, then a sentinel — never
                    # None/'?'. If it resolves to the sentinel, the original
                    # sender is unrecoverable, so this must go to plain human
                    # review and NOT drive any automated/financial routing.
                    forwarded_from = extract_forwarded_sender(body_full, header_from=from_addr)
                    if forwarded_from == UNKNOWN_FORWARD_SENDER:
                        unresolved_forward = True
            except Exception as fwd_err:  # noqa: BLE001
                print(f"[email_inbox] forward-parse warning: {fwd_err}", file=sys.stderr)
            # The identity used for classification + triage + ledger. Falls back
            # to the envelope From when this isn't a recoverable forward.
            effective_from = forwarded_from or from_addr

            # RFC-2369 bulk-mail header. Marketing blasts are legally obliged to
            # set it; invoices, receipts and password resets essentially never
            # do. Best single machine-readable "this is marketing, not a
            # transaction" signal we have — and it's why a Lindy price-cut
            # announcement should never have looked like an expense.
            list_unsubscribe = (msg.get("List-Unsubscribe") or "").strip()

            try:
                from email_playbook import classify_sender as _triage
                sender_triage = _triage(effective_from, subject, body_full,
                                        list_unsubscribe=list_unsubscribe)
                # A forwarded message is CC handing us something to process, not
                # a stranger writing in — never auto-reply to the forwarded party.
                if forwarded_from:
                    sender_triage["may_reply"] = False
                    sender_triage["forwarded_from"] = forwarded_from
            except Exception as tri_err:  # noqa: BLE001
                print(f"[email_inbox] triage warning: {tri_err}", file=sys.stderr)
                sender_triage = {"kind": "human", "is_automated": False,
                                 "may_reply": False,
                                 "is_bulk": bool(list_unsubscribe),
                                 "reason": "triage failed"}

            # AUTOMATED-REVIEW NOTIFICATION (2026-07-29) — the closed loop.
            #
            # CodeRabbit / Vercel / GitHub Actions mail is a NOTIFICATION, not
            # content to classify. Detecting it here, deterministically and
            # before any model call, buys three things: no LLM spend on machine
            # mail, no chance of a PR title like "Inbound financial consumer"
            # being read as an expense (which is exactly what happened), and a
            # concrete (repo, pr) to hand to review_harvest — which then reads
            # the LIVE thread state rather than this email's stale snapshot.
            review_ping = None
            try:
                from email_playbook import detect_review_notification
                review_ping = detect_review_notification(from_addr, subject)
            except Exception as rev_err:  # noqa: BLE001
                print(f"[email_inbox] review-detect warning: {rev_err}", file=sys.stderr)

            email_entry = {
                "from": from_addr,
                "subject": subject,
                "date": date_str,
                "preview": preview,
            }
            found_emails.append(email_entry)

            if review_ping:
                _enqueue_review_harvest(review_ping, rfc_message_id)
                # TERMINAL for machine mail. The comment above has promised
                # "no LLM spend on machine mail" since 2026-07-29, but the code
                # only ever enqueued and then fell through — every CI email
                # still ran the classifier AND email_brain, and the brain
                # Telegrams whatever it cannot auto-handle.
                #
                # So a red pipeline became a notification loop: on 2026-08-08
                # CC had 53 CI/deploy emails in two days across five repos,
                # each one an LLM call and a phone buzz about his own build.
                # Fixing the builds stops today's flood; this stops the NEXT
                # one, because a red pipeline is a normal state a tool should
                # absorb rather than escalate.
                #
                # Suppressed here means "not classified and not Telegrammed",
                # not "dropped": the queue entry above is the durable record,
                # and the Review Harvest cron reports on it once per drain
                # instead of once per email. Marking \\Seen + recording the
                # Message-ID mirrors the other terminal paths so the next
                # UNSEEN sweep does not reprocess it.
                #
                # Deliberately NOT suppressed: Vercel deployment-failure mail.
                # It carries no repo, so it cannot be queued or harvested, and
                # a broken production deploy is exactly the thing CC must still
                # hear about. notify.py's 1h dedup keeps that to one ping.
                print(f"[email_inbox] review notification suppressed "
                      f"({review_ping['kind']} {review_ping['repo']}): {subject[:70]}",
                      file=sys.stderr)
                # Record "processed" ONLY if IMAP actually accepted the flag.
                #
                # Every other terminal path lets a store() failure propagate and
                # abort the sweep. Catching it here (so one bad UID cannot kill a
                # whole batch of suppressed mail) introduced a failure mode none
                # of them have: the message stays UNSEEN in Gmail while the local
                # ledger claims it is done, so the next UNSEEN sweep skips it and
                # it is never retried — unread forever, silently.
                #
                # Leaving it unrecorded makes the path self-healing instead: the
                # next sweep retries it, and re-enqueueing is free because
                # _enqueue_review_harvest keys on repo#pr and de-dupes
                # message_ids, so a retry updates a counter rather than creating
                # work. If IMAP is broken badly enough for this to loop, that is
                # an outage the hourly cron health check surfaces on its own.
                #
                # Caught in Codex's adversarial audit of this change.
                try:
                    imap.store(uid, "+FLAGS", "\\Seen")
                except Exception as seen_err:  # noqa: BLE001
                    print(f"[email_inbox] could not mark review mail read, will retry "
                          f"next sweep: {seen_err}", file=sys.stderr)
                else:
                    processed_msgids[rfc_message_id] = datetime.now(timezone.utc).isoformat()
                    # Checkpoint here too — this branch `continue`s, so it never
                    # reached the end-of-run flush even before the 300s kill.
                    _save_processed_msgids(processed_msgids)
                continue

            # Log to Turso email_log (legacy SMTP-layer visibility)
            try:
                db.table("email_log").insert({
                    "to_email": address,
                    "subject": subject,
                    "body_preview": preview,
                    "status": "received",
                    "sent_at": datetime.now(timezone.utc).isoformat(),
                }).execute()
            except Exception as db_err:
                print(f"Warning: could not log inbound email to Turso: {db_err}", file=sys.stderr)

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
                    # Full body, not the 200-char preview: an HTML-only vendor
                    # receipt previews as (almost) nothing, and every signal
                    # past ~200 chars was invisible to the classifier.
                    content=body_full[:6000] or preview,
                    channel="email",
                    subject=subject,
                    # effective_from = the ORIGINAL sender on a forward, else the
                    # envelope From. This is what makes a forwarded vendor invoice
                    # classify as the vendor's mail, not as CC's.
                    from_identity=_extract_email_address(effective_from),
                )
            except Exception as cls_err:
                print(f"[email_inbox] classifier warning: {cls_err}", file=sys.stderr)
                classification = {"sentiment": "unknown", "intent": "other",
                                  "priority": "cold", "confidence": 0.0,
                                  "fallback": True}

            # Effective sender: the ORIGINAL sender when this is a forward CC
            # sent in, else the envelope From. Everything that attributes the
            # mail to a person — the ledger, is_known_client, the brain — keys
            # off this, so a forwarded vendor invoice is booked against the
            # vendor rather than against CC.
            sender_addr = _extract_email_address(effective_from)
            sender_name = ("" if forwarded_from
                           else _extract_display_name(from_addr))

            def _write_inbound_ledger(routing: dict | None = None) -> bool:
                """Write the unified inbound ledger row the Command Center reads.

                Returns True on success, False if the row could not be written.
                The caller MUST NOT mark a message \\Seen or record it as
                processed when this returns False — see the except clause below.

                DEFERRED until after the brain runs so the row carries the
                brain's routing decision. The retired n8n workflow achieved this
                by POSTing an <oasis-routing> contract to /api/inbound/n8n with a
                plaintext shared secret in the workflow; Bravo holds the
                service-role client directly, so it writes the same contract
                straight through the RPC — no HTTP hop and no secret to leak.

                2026-07-23: the DB carries TWO overloads of this function — a
                6-arg (…, p_message_id) and an 8-arg (…, p_thread_id,
                p_message_id, p_received_at). Passing only the 6 shared args made
                PostgREST fail every call with PGRST203, silently dropping EVERY
                message. The full 8-arg set resolves the overload.
                """
                # FLAT merge, not nested. The dashboard reads
                # metadata.classification.intent / .agent_action / .summary at the
                # TOP level (app/page.tsx renders `cls.intent`, `cls.agent_action`,
                # `cls.summary`) — exactly the shape n8n POSTed. Nesting these
                # under a "routing" key writes the data but renders nothing, so the
                # routing intent deliberately overrides the legacy keyword intent
                # (the legacy value is preserved as legacy_intent).
                payload = dict(classification or {})
                if routing:
                    payload.update(routing)
                try:
                    db.rpc("record_inbound_from_n8n", {
                        "p_from_email": sender_addr,
                        "p_from_name": sender_name,
                        "p_subject": subject,
                        "p_content": preview,
                        "p_classification": payload,
                        "p_thread_id": (msg.get("References") or "").strip() or None,
                        # Stable RFC Message-ID, not the volatile IMAP sequence
                        # number — this is the ledger's real dedup key and the
                        # same id Atlas books receipts under.
                        "p_message_id": rfc_message_id,
                        "p_received_at": datetime.now(timezone.utc).isoformat(),
                    }).execute()
                    return True
                except Exception as rpc_err:
                    # DO NOT swallow into a success. Codex's adversarial review
                    # caught that this used to print a warning and return None,
                    # after which the caller marked the message \Seen and wrote
                    # it to the processed-msgid ledger anyway. Under a DB/RPC
                    # outage that reproduces the EXACT failure this commit set
                    # out to remove — mail vanishes from the UNSEEN sweep, is
                    # skipped by every future run, and no Command Center row was
                    # ever created — just through the swallowed-RPC path instead
                    # of the end-of-run-flush path.
                    #
                    # Returning False makes the caller leave the message UNSEEN
                    # and unrecorded, so the next tick retries it. A retry costs
                    # a re-classification; a silent drop costs the lead.
                    print(f"[email_inbox] LEDGER WRITE FAILED: {rpc_err} — leaving "
                          f"message UNSEEN for retry", file=sys.stderr)
                    return False

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
            # Decision logic lives in stop_signal_decision() (pure, unit-tested
            # — CASL-critical, see its docstring for the degraded-mode guard).
            is_stop_signal, needs_manual_review = stop_signal_decision(
                classification, preview, subject
            )
            if needs_manual_review and sender_addr:
                # A raw <...> in the subject would make Telegram reject the
                # alert, silently losing the one surface this opt-out gets
                # (Codex P2). notify() now escapes for every caller (2026-08-04);
                # escaping here too would double-encode the subject.
                notify(
                    f"POSSIBLE opt-out from {sender_addr} — flagged by the "
                    "degraded keyword classifier (model outage), no literal "
                    f"STOP/UNSUBSCRIBE opener.\nSubject: {subject or ''}\n"
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
                    # Loud Telegram ping so CC knows someone opted out.
                    # Escaping is notify()'s job as of 2026-08-04 — doing it
                    # here as well would double-encode the subject.
                    notify(
                        f"STOP received from {sender_addr}\n"
                        f"Subject: {subject or ''}\n"
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
            # --- Native multi-brain routing (n8n replacement) OR legacy path ---
            # When the brain is enabled and this isn't a STOP signal (already
            # handled above), route the email through email_brain: it drafts/
            # sends/hands-off/archives and controls read-state (holds stay
            # UNREAD for review). Any failure degrades to the legacy notify+mark.
            if _email_brain_enabled(env_vars) and not is_stop_signal:
                try:
                    from email_brain import process_email, build_default_deps

                    def _mark_read(_e, _u=uid):
                        imap.store(_u, "+FLAGS", "\\Seen")

                    def _apply_label(_e, _label, _u=uid):
                        # Raises gmail_labels.LabelError on anything that is not
                        # an OK STORE. process_email relies on that: a returned
                        # False would be indistinguishable from success at the
                        # call site, which is how 42 statement notices were lost
                        # before the '&' encoding fix on 2026-08-24.
                        from lib.gmail_labels import apply_label
                        return apply_label(imap, _u, _label)

                    deps = build_default_deps(mark_read=_mark_read, db=db,
                                              apply_label=_apply_label)
                    brain_email = {
                        "from": from_addr,
                        "from_identity": sender_addr,
                        "subject": subject,
                        # Full body — the drafter's "open with a SPECIFIC
                        # reference to what they wrote" rule is unsatisfiable
                        # from a 200-char ASCII-mangled preview.
                        "body": body_full or preview,
                        "rfc_message_id": msg.get("Message-ID"),
                        "references": msg.get("References"),
                        "is_known_client": _is_known_client(db, sender_addr),
                        "attachments": _extract_attachment_meta(msg),
                        "tenant_id": None,
                        # Deterministic triage: who sent this, and are they even
                        # eligible for a generated reply.
                        "sender_kind": sender_triage.get("kind"),
                        "may_reply": bool(sender_triage.get("may_reply")),
                        # RFC-2369 List-Unsubscribe present => bulk/marketing.
                        # Weighs against a Financial & Legal read in both the
                        # model prompt and the keyword fallback.
                        "is_bulk": bool(sender_triage.get("is_bulk")),
                        # An unresolvable forward goes straight to human review:
                        # no auto-reply, no archive, no financial hand-off.
                        "force_review": unresolved_forward,
                    }
                    outcome = process_email(brain_email, deps=deps)
                    print(f"[email_inbox] brain: {outcome.get('action')} "
                          f"({outcome.get('category')}) conf={outcome.get('confidence')}",
                          file=sys.stderr)
                    # The <oasis-routing> contract the n8n workflow used to POST
                    # to the dashboard, now written straight into the ledger row
                    # so the Command Center shows WHICH brain handled the mail
                    # and WHAT it did — not just a bare intent.
                    ledger_ok = _write_inbound_ledger(
                        _routing_contract(outcome, classification))
                    # auto_reply/archive already marked read by the brain. Financial
                    # hand-offs and holds/reviews stay UNREAD so CC still sees them:
                    # Atlas's consumer marks a financial email read only after it
                    # actually processes it (until that consumer exists, the email
                    # stays in the inbox rather than vanishing into a void).
                except Exception as brain_err:
                    print(f"[email_inbox] email_brain failed, legacy fallback: {brain_err}",
                          file=sys.stderr)
                    ledger_ok = _write_inbound_ledger()
                    notify(notify_msg)
                    if ledger_ok:
                        imap.store(uid, "+FLAGS", "\\Seen")
            else:
                ledger_ok = _write_inbound_ledger()
                notify(notify_msg)
                if ledger_ok:
                    # Mark as read
                    imap.store(uid, "+FLAGS", "\\Seen")

            # A message whose ledger row was never written must stay UNSEEN and
            # unrecorded, so the next tick retries it. Recording it here would
            # make the UNSEEN sweep skip it forever with no Command Center row —
            # the precise silent-loss shape this run was meant to remove.
            if not ledger_ok:
                _log_sweep_progress("ledger_failed_message_deferred", _run_started)
                print("[email_inbox] not marking processed — ledger row missing",
                      file=sys.stderr)
                continue

            # Record this Message-ID as processed so the next UNSEEN sweep
            # skips it (the guard at the top of the loop). Runs for every
            # terminal path — brain, legacy, and the brain-failure fallback.
            processed_msgids[rfc_message_id] = datetime.now(timezone.utc).isoformat()
            # CHECKPOINT PER MESSAGE (2026-08-28). This used to be an in-memory
            # mutation flushed once at the end of the run. The sweep is killed at
            # scheduler.py's 300s wall on quota-degraded days, and the kill never
            # reaches that flush — so every message already marked \Seen above
            # was absent from the ledger, the next UNSEEN search skipped it, and
            # non-financial mail was dropped silently and permanently. (Only
            # _backfill_read_before_sweep would catch it, and that is
            # financial-routing only.) The write is atomic (tmp + os.replace),
            # so a kill mid-write cannot corrupt the ledger either.
            #
            # RESIDUAL WINDOW, stated rather than papered over: a kill BETWEEN
            # the \Seen store above and this line still loses that ONE message.
            # Closing it fully needs the ledger written before \Seen, but that
            # inverts the failure into "ledgered, still unread, skipped by the
            # guard forever" — an equally silent loss. Fixing that properly means
            # making the guard UNSEEN-aware, which is a larger change than this
            # one. One message at risk instead of a whole run is the win here.
            _save_processed_msgids(processed_msgids)

        # READ-BEFORE-SWEEP BACKFILL — catch mail CC read before this tick
        # (financial-only routing; see _backfill_read_before_sweep). Shares
        # this run's ledger dict so its entries persist in the save below.
        _log_sweep_progress("loop_done", _run_started,
                            processed=len(message_ids) - deferred, deferred=deferred)
        _backfill_read_before_sweep(imap, db, processed_msgids,
                                    deadline=sweep_deadline)
        _log_sweep_progress("backfill_done", _run_started)

        # V2.1: Persist poison UID tracker so failure counts survive across runs
        try:
            POISON_UID_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(POISON_UID_PATH, "w", encoding="utf-8") as pf:
                json.dump(poison_state, pf, indent=2)
        except Exception as save_err:
            print(f"[email_inbox] Could not save poison UID state: {save_err}", file=sys.stderr)

        # Persist the processed-Message-ID idempotency ledger.
        _save_processed_msgids(processed_msgids)

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
        description="Email Engine - Free Gmail SMTP sending + Turso tracking",
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
