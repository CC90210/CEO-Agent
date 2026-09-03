"""
Wire OASIS outreach templates in the Bravo Turso project.

This replaces the scratch one-off template patcher that used non-canonical
environment names. Canonical Bravo tools use:

  BRAVO_SUPABASE_URL
  BRAVO_SUPABASE_SERVICE_ROLE_KEY

(These legacy-named vars route to the Turso bravo DB via the supabase-compat
shim; the underlying engine is Turso/libSQL.)

This replaces the scratch one-off template patcher that used non-canonical
environment names. Canonical Bravo tools use:

  BRAVO_SUPABASE_URL
  BRAVO_SUPABASE_SERVICE_ROLE_KEY

No credentials are printed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BOOKING_LINK = "https://calendar.app.google/tpfvJYBGircnGu8G8"
DEFAULT_WEBSITE_LINK = "https://oasisai.work"
CTA_LABEL = "Book the 15-minute AI audit"
TEMPLATE_NAMES = ("OASIS Welcome", "OASIS Value Add", "OASIS CTA")


def load_env() -> dict[str, str]:
    env_path = PROJECT_ROOT / ".env.agents"
    if not env_path.exists():
        raise RuntimeError(f"{env_path} not found")

    env: dict[str, str] = {}
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                env[key.strip()] = value.strip()

    for key, value in env.items():
        os.environ.setdefault(key, value)
    return env


def get_supabase(env: dict[str, str]):
    try:
        from supabase import create_client
    except ImportError as exc:
        raise RuntimeError("supabase package not installed. Run: pip install supabase") from exc

    url = (
        env.get("BRAVO_SUPABASE_URL")
        or os.environ.get("BRAVO_SUPABASE_URL") or "https://bravo.turso.compat"
    )
    key = (
        env.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY") or "turso-compat-key"
    )
    if not url or not key:
        raise RuntimeError(
            "Missing Bravo Supabase credentials. Need "
            "BRAVO_SUPABASE_URL + BRAVO_SUPABASE_SERVICE_ROLE_KEY in .env.agents."
        )
    return create_client(url, key)


def button_html(link: str) -> str:
    return (
        f'<a href="{link}" '
        'style="display:inline-block;background:#111827;color:#ffffff;'
        'text-decoration:none;padding:10px 14px;border-radius:6px;'
        'font-weight:600;">'
        f"{CTA_LABEL}</a>"
    )


def templates(booking_link: str, website_link: str) -> dict[str, dict[str, Any]]:
    button = button_html(booking_link)
    return {
        "OASIS Welcome": {
            "subject": "Quick thought for {{company}}",
            "body_text": f"""Hi {{{{first_name}}}},

I'm Conaugh McKenna, founder of OASIS AI Solutions in Collingwood.

For a service business like {{{{company}}}}, the hidden leak is usually not talent. It is the admin between the lead coming in, the quote going out, and the follow-up actually happening.

Would it be useful to spend 15 minutes mapping where AI could remove that bottleneck in your current workflow?

{CTA_LABEL}: {booking_link}

No prep needed. If there is no fit, you still leave with the map.

Only good things from now on,
Conaugh McKenna
OASIS AI Solutions
{website_link}""",
            "body_html": f"""<p>Hi {{{{first_name}}}},</p>
<p>I'm Conaugh McKenna, founder of OASIS AI Solutions in Collingwood.</p>
<p>For a service business like {{{{company}}}}, the hidden leak is usually not talent. It is the admin between the lead coming in, the quote going out, and the follow-up actually happening.</p>
<p>Would it be useful to spend 15 minutes mapping where AI could remove that bottleneck in your current workflow?</p>
<p>{button}</p>
<p>No prep needed. If there is no fit, you still leave with the map.</p>
<p>Only good things from now on,<br>Conaugh McKenna<br>OASIS AI Solutions<br><a href="{website_link}">{website_link}</a></p>""",
            "category": "welcome",
            "variables": ["first_name", "company"],
        },
        "OASIS Value Add": {
            "subject": "Where follow-up leaks at {{company}}",
            "body_text": f"""Hi {{{{first_name}}}},

Following up with something more concrete.

Most local service businesses do not lose work because the team is bad. They lose it in the handoff: the missed inquiry, the quote that waits a day too long, the reminder nobody had time to send.

For {{{{company}}}}, the first useful AI system may be as simple as:
- instant lead response
- automatic booking confirmations and reminders
- review requests after completed work
- a weekly inbox report showing what slipped

Worth 15 minutes to map that against your current workflow?

{CTA_LABEL}: {booking_link}

Only good things from now on,
Conaugh McKenna
OASIS AI Solutions
{website_link}""",
            "body_html": f"""<p>Hi {{{{first_name}}}},</p>
<p>Following up with something more concrete.</p>
<p>Most local service businesses do not lose work because the team is bad. They lose it in the handoff: the missed inquiry, the quote that waits a day too long, the reminder nobody had time to send.</p>
<p>For {{{{company}}}}, the first useful AI system may be as simple as:</p>
<ul>
  <li>instant lead response</li>
  <li>automatic booking confirmations and reminders</li>
  <li>review requests after completed work</li>
  <li>a weekly inbox report showing what slipped</li>
</ul>
<p>Worth 15 minutes to map that against your current workflow?</p>
<p>{button}</p>
<p>Only good things from now on,<br>Conaugh McKenna<br>OASIS AI Solutions<br><a href="{website_link}">{website_link}</a></p>""",
            "category": "nurture",
            "variables": ["first_name", "company"],
        },
        "OASIS CTA": {
            "subject": "Worth a 15-minute AI audit for {{company}}?",
            "body_text": f"""Hi {{{{first_name}}}},

I do not want to keep filling your inbox, so I will make this useful.

I am offering a free 15-minute AI audit for local service businesses this month. We can look at where follow-up slows down, what can be automated first, and whether there is a practical first system for {{{{company}}}}.

Worth 15 minutes to audit that together?

{CTA_LABEL}: {booking_link}

No pressure either way. If there is no fit, you still leave with a clearer next step.

Only good things from now on,
Conaugh McKenna
OASIS AI Solutions
{website_link}""",
            "body_html": f"""<p>Hi {{{{first_name}}}},</p>
<p>I do not want to keep filling your inbox, so I will make this useful.</p>
<p>I am offering a free 15-minute AI audit for local service businesses this month. We can look at where follow-up slows down, what can be automated first, and whether there is a practical first system for {{{{company}}}}.</p>
<p>Worth 15 minutes to audit that together?</p>
<p>{button}</p>
<p>No pressure either way. If there is no fit, you still leave with a clearer next step.</p>
<p>Only good things from now on,<br>Conaugh McKenna<br>OASIS AI Solutions<br><a href="{website_link}">{website_link}</a></p>""",
            "category": "cta",
            "variables": ["first_name", "company"],
        },
    }


def verify_template(row: dict[str, Any], booking_link: str, website_link: str) -> list[str]:
    problems: list[str] = []
    body_text = row.get("body_text") or ""
    body_html = row.get("body_html") or ""
    if booking_link not in body_text:
        problems.append("plain text body missing booking link")
    if body_text.count(booking_link) != 1:
        problems.append(f"plain text body must contain exactly one booking link, found {body_text.count(booking_link)}")
    if f'href="{booking_link}"' not in body_html:
        problems.append("HTML body missing linked booking CTA")
    booking_href_count = body_html.count(f'href="{booking_link}"')
    if booking_href_count != 1:
        problems.append(
            f"HTML body must contain exactly one booking CTA href, "
            f"found {booking_href_count}"
        )
    if website_link not in body_text:
        problems.append("plain text body missing website link")
    if f'href="{website_link}"' not in body_html:
        problems.append("HTML body missing linked website")
    if f">{booking_link}</a>" in body_html and CTA_LABEL not in body_html:
        problems.append("HTML CTA uses raw URL instead of action label")
    if CTA_LABEL not in body_text or CTA_LABEL not in body_html:
        problems.append("CTA label missing")
    for placeholder in ("{{first_name}}", "{{company}}"):
        if placeholder not in body_text:
            problems.append(f"plain text body missing {placeholder}")
        if placeholder not in body_html:
            problems.append(f"HTML body missing {placeholder}")
    return problems


def update_templates(db: Any, wanted: dict[str, dict[str, Any]], dry_run: bool) -> list[dict[str, Any]]:
    results = []
    for name, payload in wanted.items():
        existing = db.table("email_templates").select("id,name").eq("name", name).execute().data or []
        if not existing:
            results.append({"name": name, "status": "missing"})
            continue
        if dry_run:
            results.append({"name": name, "status": "dry_run", "id": existing[0]["id"]})
            continue
        updated = db.table("email_templates").update(payload).eq("name", name).execute().data or []
        results.append({
            "name": name,
            "status": "updated" if updated else "no_rows_updated",
            "id": existing[0]["id"],
        })
    return results


SAMPLE_RENDER_VARS = {
    "first_name": "Alex",
    "company": "Northern HVAC",
    "region": "the Collingwood area",
}


def render_audit(
    db: Any, booking_link: str, website_link: str, sample_vars: dict[str, str] | None = None
) -> list[dict[str, Any]]:
    """Render stored templates through the production render path and audit output.

    Separate from verify_template (which checks the stored strings): this
    catches regressions that only appear post-substitution — e.g. a variable
    missing from sample_vars leaves a leftover `{{...}}`, or a templating
    helper doubles a link at render time.
    """
    import re as _re

    try:
        from email_engine import render_template  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "render_audit requires scripts/ on sys.path; "
            "email_engine.render_template not importable"
        ) from exc

    sample_vars = sample_vars or SAMPLE_RENDER_VARS
    rows = (
        db.table("email_templates")
        .select("name,subject,body_text,body_html")
        .in_("name", list(TEMPLATE_NAMES))
        .execute()
        .data
        or []
    )
    by_name = {r["name"]: r for r in rows}

    results: list[dict[str, Any]] = []
    for name in TEMPLATE_NAMES:
        row = by_name.get(name)
        if not row:
            results.append({"name": name, "ok": False, "problems": ["template missing"]})
            continue

        problems: list[str] = []
        rendered_text = render_template(row.get("body_text") or "", sample_vars)
        rendered_html = render_template(row.get("body_html") or "", sample_vars)
        rendered_subject = render_template(row.get("subject") or "", sample_vars)

        if rendered_text.count(booking_link) != 1:
            problems.append(
                f"rendered text: booking link count={rendered_text.count(booking_link)} (want 1)"
            )
        if rendered_text.count(website_link) != 1:
            problems.append(
                f"rendered text: website link count={rendered_text.count(website_link)} (want 1)"
            )

        href_booking = f'href="{booking_link}"'
        href_website = f'href="{website_link}"'
        if rendered_html.count(href_booking) != 1:
            problems.append(
                f"rendered html: booking href count={rendered_html.count(href_booking)} (want 1)"
            )
        if rendered_html.count(href_website) != 1:
            problems.append(
                f"rendered html: website href count={rendered_html.count(href_website)} (want 1)"
            )

        for field, rendered in (
            ("subject", rendered_subject),
            ("body_text", rendered_text),
            ("body_html", rendered_html),
        ):
            leftovers = _re.findall(r"\{\{[^}]+\}\}", rendered)
            if leftovers:
                problems.append(f"rendered {field}: unsubstituted placeholders {leftovers}")

        results.append({"name": name, "ok": not problems, "problems": problems})
    return results


def verify_templates(db: Any, booking_link: str, website_link: str) -> list[dict[str, Any]]:
    rows = (
        db.table("email_templates")
        .select("id,name,subject,body_text,body_html")
        .in_("name", list(TEMPLATE_NAMES))
        .execute()
        .data
        or []
    )
    by_name = {row.get("name"): row for row in rows}
    results = []
    for name in TEMPLATE_NAMES:
        row = by_name.get(name)
        if not row:
            results.append({"name": name, "ok": False, "problems": ["template missing"]})
            continue
        problems = verify_template(row, booking_link, website_link)
        results.append({
            "name": name,
            "ok": not problems,
            "subject": row.get("subject"),
            "problems": problems,
        })
    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Wire and verify OASIS email templates in Bravo Turso."
    )
    parser.add_argument("--dry-run", action="store_true", help="Show intended updates without writing")
    parser.add_argument("--verify-only", action="store_true", help="Only verify stored templates")
    parser.add_argument("--render-check", action="store_true",
                        help="Also render each template with sample vars and audit the rendered output")
    parser.add_argument("--json", dest="output_json", action="store_true", help="Print JSON output")
    args = parser.parse_args()

    env = load_env()
    booking_link = env.get("BOOKING_LINK") or os.environ.get("BOOKING_LINK") or DEFAULT_BOOKING_LINK
    website_link = env.get("WEBSITE_LINK") or os.environ.get("WEBSITE_LINK") or DEFAULT_WEBSITE_LINK
    if "calendar.app.google" not in booking_link:
        raise RuntimeError(f"BOOKING_LINK must be the Google Calendar link, got: {booking_link}")
    if "oasisai.work" not in website_link:
        raise RuntimeError(f"WEBSITE_LINK must be the OASIS website link, got: {website_link}")

    db = get_supabase(env)
    updates: list[dict[str, Any]] = []
    if not args.verify_only:
        updates = update_templates(db, templates(booking_link, website_link), dry_run=args.dry_run)
    verification = verify_templates(db, booking_link, website_link)
    render_results: list[dict[str, Any]] = []
    if args.render_check:
        render_results = render_audit(db, booking_link, website_link)

    ok = (
        all(item["ok"] for item in verification)
        and all(item["status"] not in {"missing", "no_rows_updated"} for item in updates)
        and all(item["ok"] for item in render_results)
    )

    result = {
        "ok": ok if args.verify_only else (args.dry_run or ok),
        "booking_link": booking_link,
        "website_link": website_link,
        "updates": updates,
        "verification": verification,
        "render_check": render_results,
    }
    if args.output_json:
        print(json.dumps(result, indent=2, default=str))
    else:
        if updates:
            for item in updates:
                print(f"{item['name']}: {item['status']}")
        for item in verification:
            status = "OK" if item["ok"] else "NEEDS FIX"
            print(f"{item['name']}: {status}")
            for problem in item.get("problems") or []:
                print(f"  - {problem}")
        if render_results:
            print("\n-- render check --")
            for item in render_results:
                status = "OK" if item["ok"] else "NEEDS FIX"
                print(f"{item['name']} (rendered): {status}")
                for problem in item.get("problems") or []:
                    print(f"  - {problem}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
