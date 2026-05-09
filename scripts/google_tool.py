"""
Google Workspace CLI — Calendar, Gmail, Drive, Docs, Sheets
Wraps gws CLI with auto-token-refresh and fallback to direct API.
All credentials loaded from .env.agents (never hardcoded).

Usage (from any agent via terminal):
  python scripts/google_tool.py calendar list [--max 10]
  python scripts/google_tool.py calendar create --title "Meeting" --start "2026-04-01T16:00:00" --end "2026-04-01T16:45:00" [--attendees "a@b.com,c@d.com"] [--meet] [--description "..."] [--timezone "America/Toronto"]
  python scripts/google_tool.py calendar delete <event_id>
  python scripts/google_tool.py gmail send --to "a@b.com" --subject "Hi" --body "Hello"
  python scripts/google_tool.py gmail list [--max 10]
  python scripts/google_tool.py gmail read <message_id>
  python scripts/google_tool.py drive list [--max 10] [--query "name contains 'report'"]
  python scripts/google_tool.py drive upload --file "/path/to/file.pdf" [--name "Custom Name"] [--folder FOLDER_ID]
  python scripts/google_tool.py drive download <file_id> [--output "/path/to/save"]
  python scripts/google_tool.py drive delete <file_id>
  python scripts/google_tool.py drive info <file_id>
  python scripts/google_tool.py drive share <file_id> --email "user@example.com" [--role writer]
  python scripts/google_tool.py docs create --title "My Document" [--content "Plain text content"] [--html "/path/to/file.html"] [--folder FOLDER_ID]
  python scripts/google_tool.py docs read <doc_id>
  python scripts/google_tool.py docs append <doc_id> --text "Text to append"
  python scripts/google_tool.py docs export <doc_id> [--format pdf|docx|txt|html] [--output "/path/to/save"]
  python scripts/google_tool.py sheets create --title "My Sheet" [--sheets "Sheet1,Data,Summary"]
  python scripts/google_tool.py sheets read <spreadsheet_id> [--range "Sheet1!A1:Z"]
  python scripts/google_tool.py sheets write <spreadsheet_id> --range "Sheet1!A1" --values "Name,Email;John,j@t.com"
  python scripts/google_tool.py sheets append <spreadsheet_id> --values "NewRow1,NewRow2"
  python scripts/google_tool.py sheets info <spreadsheet_id>
  python scripts/google_tool.py slides create --title "My Deck"
  python scripts/google_tool.py slides read <presentation_id>
  python scripts/google_tool.py slides export <presentation_id> [--format pdf|pptx] [--output "/path/to/save"]
  python scripts/google_tool.py tasks list [--list-id LIST_ID]
  python scripts/google_tool.py tasks add --list-id LIST_ID --title "Do the thing" [--due 2026-04-15] [--notes "details"]
  python scripts/google_tool.py tasks complete --list-id LIST_ID --task-id TASK_ID
  python scripts/google_tool.py test

All commands support --json flag for agent consumption.
"""

import argparse
import json
import os
import smtplib
import subprocess
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path


# Ensure UTF-8 output on Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def load_env():
    """Load .env.agents from project root."""
    env_path = Path(__file__).parent.parent / ".env.agents"
    if not env_path.exists():
        print("ERROR: .env.agents not found", file=sys.stderr)
        sys.exit(1)
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())


GWS_PATH = os.environ.get("GWS_PATH", r"C:\Users\User\AppData\Roaming\npm\gws.cmd")


_PINGED_GWS_SERVICES: set[str] = set()


def _ping_gws_service(args_list: list, ok: bool) -> None:
    """Bump integrations_health for the GWS subsystem touched. Once-per-process
    per service to keep the trip cost negligible (the dashboard's green dot
    only needs ~one ping per session). Called from run_gws on every call.

    Maps the gws CLI's first arg to the integrations_health 'service'
    column: gmail → google_gmail, calendar → google_calendar, etc.
    """
    if not args_list:
        return
    first = str(args_list[0]).lower()
    service_map = {
        "gmail": "google_gmail",
        "calendar": "google_calendar",
        "drive": "google_drive",
        "docs": "google_docs",
        "sheets": "google_sheets",
        "slides": "google_slides",
        "tasks": "google_tasks",
    }
    service = service_map.get(first)
    if not service:
        return
    if ok and service in _PINGED_GWS_SERVICES:
        return
    try:
        from integration_health import ping  # type: ignore
        ping(service, status="healthy" if ok else "degraded")
        if ok:
            _PINGED_GWS_SERVICES.add(service)
    except Exception:
        pass  # best-effort — never break the caller


def run_gws(args_list, timeout=30):
    """Run a gws CLI command and return parsed JSON output."""
    cmd = [GWS_PATH] + args_list
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace"
        )
        # gws outputs to stdout, errors to stderr
        output = result.stdout.strip()
        if result.returncode != 0:
            error_text = result.stderr.strip() or output
            # Check for auth errors
            if "expired" in error_text.lower() or "401" in error_text:
                return None, "AUTH_EXPIRED"
            _ping_gws_service(args_list, ok=False)
            return None, error_text
        _ping_gws_service(args_list, ok=True)
        try:
            return json.loads(output), None
        except json.JSONDecodeError:
            return output, None
    except subprocess.TimeoutExpired:
        return None, "TIMEOUT"
    except FileNotFoundError:
        return None, "GWS_NOT_FOUND"


def refresh_gws_auth():
    """Attempt to refresh gws auth by re-logging in non-interactively.
    If this fails, fall back to direct API with SMTP for email."""
    print("WARNING: gws token expired. Attempting re-auth...", file=sys.stderr)
    # gws auth login requires browser interaction, so we can't auto-refresh
    # Instead, return False and let callers use fallback methods
    return False


def gmail_send_smtp(to, subject, body, ics_content=None, *, branded=False, cta_label=None, cta_url=None):
    """Send email via SMTP as fallback when gws CLI auth fails.

    branded=True wraps `body` in the OASIS AI branded HTML shell from
    scripts/email_template.py and sends multipart/alternative (HTML +
    plaintext fallback). branded=False sends plaintext only — same
    behavior as before.

    cta_label + cta_url (only honored when branded=True) renders a
    primary-button CTA below the message body.
    """
    gmail_user = os.environ.get("GMAIL_USER", "conaugh@oasisai.work")
    gmail_pass = os.environ.get("GMAIL_APP_PASSWORD")
    if not gmail_pass:
        return None, "GMAIL_APP_PASSWORD not set in .env.agents"

    from_display = (
        os.environ.get("BRAVO_FROM_DISPLAY")
        or os.environ.get("USER_FULL_NAME")
        or "Conaugh McKenna"
    )

    if branded:
        # Lazy-import so the rest of google_tool.py keeps working when
        # email_template.py is missing (e.g., during a partial deploy).
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from email_template import render_branded_html, render_branded_plaintext
            html_body = render_branded_html(
                body, subject=subject, cta_label=cta_label, cta_url=cta_url,
                show_booking=True,
            )
            plain_body = render_branded_plaintext(body)
        except Exception as e:
            return None, f"branded_template_failed: {e}"

        # multipart/alternative — clients pick HTML if they support it,
        # plaintext otherwise. Wrap in mixed only if we're attaching an
        # ICS calendar invite below.
        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(plain_body, "plain", "utf-8"))
        alt.attach(MIMEText(html_body, "html", "utf-8"))
        if ics_content:
            msg = MIMEMultipart("mixed")
            msg.attach(alt)
            ics_part = MIMEBase("text", "calendar", method="REQUEST")
            ics_part.set_payload(ics_content)
            encoders.encode_base64(ics_part)
            ics_part.add_header("Content-Disposition", "attachment", filename="invite.ics")
            msg.attach(ics_part)
        else:
            msg = alt
    else:
        # Plain-text only — preserved for backwards compatibility.
        msg = MIMEMultipart("mixed")
        msg.attach(MIMEText(body, "plain"))
        if ics_content:
            ics_part = MIMEBase("text", "calendar", method="REQUEST")
            ics_part.set_payload(ics_content)
            encoders.encode_base64(ics_part)
            ics_part.add_header("Content-Disposition", "attachment", filename="invite.ics")
            msg.attach(ics_part)

    msg["From"] = f"{from_display} <{gmail_user}>"
    msg["To"] = to
    msg["Subject"] = subject

    try:
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(gmail_user, gmail_pass)
        server.sendmail(gmail_user, to, msg.as_string())
        server.quit()
        return {"status": "sent", "method": "smtp", "to": to, "branded": bool(branded)}, None
    except Exception as e:
        return None, str(e)


# ── Calendar Commands ──────────────────────────────────────────────

def calendar_list(args):
    """List upcoming calendar events."""
    max_results = args.max or 10
    params = {
        "calendarId": "primary",
        "maxResults": max_results,
        "singleEvents": True,
        "orderBy": "startTime",
        "timeMin": f"{_now_iso()}",
    }
    data, err = run_gws([
        "calendar", "events", "list",
        "--params", json.dumps(params)
    ])
    if err == "AUTH_EXPIRED":
        print("ERROR: gws auth expired. Run: gws auth login", file=sys.stderr)
        sys.exit(1)
    if err:
        print(f"ERROR: {err}", file=sys.stderr)
        sys.exit(1)

    events = data.get("items", [])
    if args.json_output:
        print(json.dumps(events, indent=2))
    else:
        if not events:
            print("No upcoming events.")
            return
        for e in events:
            start = e.get("start", {}).get("dateTime", e.get("start", {}).get("date", ""))
            print(f"  {start}  {e.get('summary', '(no title)')}")
            if e.get("hangoutLink"):
                print(f"    Meet: {e['hangoutLink']}")


def calendar_create(args):
    """Create a calendar event with optional attendees and Meet link."""
    tz = args.timezone or "America/Toronto"
    event = {
        "summary": args.title,
        "start": {"dateTime": args.start, "timeZone": tz},
        "end": {"dateTime": args.end, "timeZone": tz},
    }
    if args.description:
        event["description"] = args.description
    if args.attendees:
        event["attendees"] = [{"email": e.strip()} for e in args.attendees.split(",")]
    if args.meet:
        meet_link = os.environ.get("GOOGLE_MEET_LINK", "")
        if meet_link:
            event["conferenceData"] = {
                "entryPoints": [{
                    "entryPointType": "video",
                    "uri": meet_link,
                    "label": meet_link.replace("https://", "")
                }],
                "conferenceSolution": {
                    "key": {"type": "hangoutsMeet"},
                    "name": "Google Meet"
                },
                "conferenceId": meet_link.split("/")[-1]
            }

    params = {
        "calendarId": "primary",
        "conferenceDataVersion": 1,
        "sendUpdates": "all"
    }

    data, err = run_gws([
        "calendar", "events", "insert",
        "--params", json.dumps(params),
        "--json", json.dumps(event)
    ])

    if err == "AUTH_EXPIRED":
        print("ERROR: gws auth expired. Run: gws auth login", file=sys.stderr)
        sys.exit(1)
    if err:
        print(f"ERROR: {err}", file=sys.stderr)
        sys.exit(1)

    if args.json_output:
        print(json.dumps(data, indent=2))
    else:
        print(f"Event created: {data.get('summary')}")
        print(f"  When: {data.get('start', {}).get('dateTime')}")
        print(f"  Link: {data.get('htmlLink')}")
        if data.get("hangoutLink"):
            print(f"  Meet: {data['hangoutLink']}")
        attendees = data.get("attendees", [])
        if attendees:
            print(f"  Attendees: {', '.join(a['email'] for a in attendees)}")


def calendar_delete(args):
    """Delete a calendar event."""
    params = {"calendarId": "primary", "eventId": args.event_id, "sendUpdates": "all"}
    data, err = run_gws([
        "calendar", "events", "delete",
        "--params", json.dumps(params)
    ])
    if err:
        print(f"ERROR: {err}", file=sys.stderr)
        sys.exit(1)
    print(f"Event {args.event_id} deleted.")


# ── Gmail Commands ─────────────────────────────────────────────────

def gmail_send(args):
    """Send an email. Uses gws CLI first, falls back to SMTP.

    `--branded` (default ON) wraps the body in the OASIS AI branded
    HTML shell from scripts/email_template.py. `--plain` opts out for
    the rare case the operator wants a stripped-down message (e.g.
    automated verification mails).
    """
    # When branded, the SMTP path renders HTML — gws CLI's `raw` field
    # would need to be MIME-encoded with the HTML body too. Easier:
    # always go SMTP for branded sends; gws CLI for plain.
    use_branded = getattr(args, "branded", True) and not getattr(args, "plain", False)
    cta_label = getattr(args, "cta_label", None)
    cta_url = getattr(args, "cta_url", None)

    if use_branded:
        data, smtp_err = gmail_send_smtp(
            args.to, args.subject, args.body,
            branded=True, cta_label=cta_label, cta_url=cta_url,
        )
        if smtp_err:
            print(f"ERROR: {smtp_err}", file=sys.stderr)
            sys.exit(1)
    else:
        # Plain-text path: try gws first (preserves From: identity from
        # the operator's OAuth grant), fall back to SMTP.
        message_body = {
            "raw": _encode_email(args.to, args.subject, args.body)
        }
        data, err = run_gws([
            "gmail", "users", "messages", "send",
            "--params", json.dumps({"userId": "me"}),
            "--json", json.dumps(message_body)
        ])
        if err == "AUTH_EXPIRED" or err:
            print("gws CLI unavailable, using SMTP fallback...", file=sys.stderr)
            data, smtp_err = gmail_send_smtp(args.to, args.subject, args.body)
            if smtp_err:
                print(f"ERROR: {smtp_err}", file=sys.stderr)
                sys.exit(1)

    if args.json_output:
        print(json.dumps(data, indent=2))
    else:
        suffix = " (branded)" if use_branded else ""
        print(f"Email sent to {args.to}{suffix}")


def gmail_list(args):
    """List recent emails."""
    max_results = args.max or 10
    params = {"userId": "me", "maxResults": max_results}
    data, err = run_gws([
        "gmail", "users", "messages", "list",
        "--params", json.dumps(params)
    ])
    if err == "AUTH_EXPIRED":
        print("ERROR: gws auth expired. Run: gws auth login", file=sys.stderr)
        sys.exit(1)
    if err:
        print(f"ERROR: {err}", file=sys.stderr)
        sys.exit(1)

    if args.json_output:
        print(json.dumps(data, indent=2))
    else:
        messages = data.get("messages", [])
        print(f"{len(messages)} messages (showing IDs — use 'gmail read <id>' for details)")
        for m in messages[:max_results]:
            print(f"  {m['id']}")


def gmail_read(args):
    """Read a specific email."""
    params = {"userId": "me", "id": args.message_id, "format": "full"}
    data, err = run_gws([
        "gmail", "users", "messages", "get",
        "--params", json.dumps(params)
    ])
    if err:
        print(f"ERROR: {err}", file=sys.stderr)
        sys.exit(1)

    if args.json_output:
        print(json.dumps(data, indent=2))
    else:
        headers = {h["name"]: h["value"] for h in data.get("payload", {}).get("headers", [])}
        print(f"From: {headers.get('From', 'unknown')}")
        print(f"Subject: {headers.get('Subject', '(no subject)')}")
        print(f"Date: {headers.get('Date', '')}")
        snippet = data.get("snippet", "")
        print(f"\n{snippet}")


# ── Drive Commands ────────────────────────────────────────────────

def drive_list(args):
    """List files in Google Drive."""
    max_results = args.max or 10
    params = {
        "pageSize": max_results,
        "fields": "files(id,name,mimeType,modifiedTime,size,webViewLink)",
        "orderBy": "modifiedTime desc",
    }
    if args.query:
        params["q"] = args.query

    data, err = run_gws([
        "drive", "files", "list",
        "--params", json.dumps(params)
    ])
    if err:
        _handle_error(err)

    files = data.get("files", []) if isinstance(data, dict) else []
    if args.json_output:
        print(json.dumps(files, indent=2))
    else:
        if not files:
            print("No files found.")
            return
        for f in files:
            size = f.get("size", "")
            size_str = f"  ({_human_size(int(size))})" if size else ""
            print(f"  {f['name']}{size_str}")
            print(f"    ID: {f['id']}  Type: {f.get('mimeType', '')}")
            if f.get("webViewLink"):
                print(f"    Link: {f['webViewLink']}")


def drive_upload(args):
    """Upload a file to Google Drive."""
    file_path = args.file
    if not os.path.exists(file_path):
        print(f"ERROR: File not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    name = args.name or os.path.basename(file_path)
    metadata = {"name": name}
    if args.folder:
        metadata["parents"] = [args.folder]

    # Detect mime type
    import mimetypes
    content_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"

    gws_args = [
        "drive", "files", "create",
        "--json", json.dumps(metadata),
        "--upload", file_path,
        "--upload-content-type", content_type,
    ]

    data, err = run_gws(gws_args, timeout=120)
    if err:
        _handle_error(err)

    if args.json_output:
        print(json.dumps(data, indent=2))
    else:
        print(f"Uploaded: {data.get('name')}")
        print(f"  ID: {data.get('id')}")
        print(f"  Link: https://drive.google.com/file/d/{data.get('id')}/view")


def drive_download(args):
    """Download a file from Google Drive."""
    file_id = args.file_id

    # First get file info to determine name and type
    info_data, err = run_gws([
        "drive", "files", "get",
        "--params", json.dumps({"fileId": file_id, "fields": "name,mimeType"})
    ])
    if err:
        _handle_error(err)

    file_name = info_data.get("name", "download") if isinstance(info_data, dict) else "download"
    mime = info_data.get("mimeType", "") if isinstance(info_data, dict) else ""

    output_path = args.output or file_name

    # Google Docs types need export, regular files use get with alt=media
    export_mimes = {
        "application/vnd.google-apps.document": ("application/pdf", ".pdf"),
        "application/vnd.google-apps.spreadsheet": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"),
        "application/vnd.google-apps.presentation": ("application/pdf", ".pdf"),
    }

    if mime in export_mimes:
        export_mime, ext = export_mimes[mime]
        if not output_path.endswith(ext):
            output_path += ext
        data, err = run_gws([
            "drive", "files", "export",
            "--params", json.dumps({"fileId": file_id, "mimeType": export_mime}),
            "--output", output_path
        ], timeout=60)
    else:
        data, err = run_gws([
            "drive", "files", "get",
            "--params", json.dumps({"fileId": file_id, "alt": "media"}),
            "--output", output_path
        ], timeout=60)

    if err:
        _handle_error(err)

    print(f"Downloaded: {output_path}")


def drive_delete(args):
    """Delete a file from Google Drive."""
    data, err = run_gws([
        "drive", "files", "delete",
        "--params", json.dumps({"fileId": args.file_id})
    ])
    if err:
        _handle_error(err)
    print(f"Deleted file: {args.file_id}")


def drive_info(args):
    """Get info about a Drive file."""
    data, err = run_gws([
        "drive", "files", "get",
        "--params", json.dumps({
            "fileId": args.file_id,
            "fields": "id,name,mimeType,size,createdTime,modifiedTime,webViewLink,owners,shared,permissions"
        })
    ])
    if err:
        _handle_error(err)

    if args.json_output:
        print(json.dumps(data, indent=2))
    else:
        print(f"Name: {data.get('name')}")
        print(f"ID: {data.get('id')}")
        print(f"Type: {data.get('mimeType')}")
        if data.get('size'):
            print(f"Size: {_human_size(int(data['size']))}")
        print(f"Modified: {data.get('modifiedTime', '')}")
        print(f"Link: {data.get('webViewLink', '')}")
        if data.get('shared'):
            print(f"Shared: Yes")


def drive_share(args):
    """Share a file with a user."""
    permission = {
        "type": "user",
        "role": args.role or "writer",
        "emailAddress": args.email,
    }
    data, err = run_gws([
        "drive", "permissions", "create",
        "--params", json.dumps({"fileId": args.file_id, "sendNotificationEmail": True}),
        "--json", json.dumps(permission)
    ])
    if err:
        _handle_error(err)

    if args.json_output:
        print(json.dumps(data, indent=2))
    else:
        print(f"Shared with {args.email} as {args.role or 'writer'}")


# ── Docs Commands ─────────────────────────────────────────────────

def docs_create(args):
    """Create a Google Doc. Supports plain text, HTML file upload, or blank."""
    if args.html:
        # Upload HTML file as Google Doc (auto-converts)
        if not os.path.exists(args.html):
            print(f"ERROR: HTML file not found: {args.html}", file=sys.stderr)
            sys.exit(1)

        metadata = {
            "name": args.title or os.path.splitext(os.path.basename(args.html))[0],
            "mimeType": "application/vnd.google-apps.document",
        }
        if args.folder:
            metadata["parents"] = [args.folder]

        data, err = run_gws([
            "drive", "files", "create",
            "--json", json.dumps(metadata),
            "--upload", args.html,
            "--upload-content-type", "text/html",
        ], timeout=60)
        if err:
            _handle_error(err)

    elif args.content:
        # Create blank doc then insert text
        metadata = {
            "name": args.title or "Untitled Document",
            "mimeType": "application/vnd.google-apps.document",
        }
        if args.folder:
            metadata["parents"] = [args.folder]

        # Write content as temp HTML for better formatting
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False, encoding="utf-8") as f:
            f.write(f"<html><body><p>{args.content}</p></body></html>")
            tmp_path = f.name

        try:
            data, err = run_gws([
                "drive", "files", "create",
                "--json", json.dumps(metadata),
                "--upload", tmp_path,
                "--upload-content-type", "text/html",
            ], timeout=60)
            if err:
                _handle_error(err)
        finally:
            os.unlink(tmp_path)

    else:
        # Create blank Google Doc
        metadata = {
            "name": args.title or "Untitled Document",
            "mimeType": "application/vnd.google-apps.document",
        }
        if args.folder:
            metadata["parents"] = [args.folder]

        data, err = run_gws([
            "drive", "files", "create",
            "--json", json.dumps(metadata),
        ])
        if err:
            _handle_error(err)

    doc_id = data.get("id", "") if isinstance(data, dict) else ""
    if args.json_output:
        print(json.dumps(data, indent=2))
    else:
        print(f"Created: {data.get('name')}")
        print(f"  ID: {doc_id}")
        print(f"  Link: https://docs.google.com/document/d/{doc_id}/edit")


def docs_read(args):
    """Read the text content of a Google Doc."""
    data, err = run_gws([
        "docs", "documents", "get",
        "--params", json.dumps({"documentId": args.doc_id})
    ])
    if err:
        _handle_error(err)

    if args.json_output:
        print(json.dumps(data, indent=2))
    else:
        # Extract plain text from document body
        text = _extract_doc_text(data)
        print(text)


def docs_append(args):
    """Append text to the end of a Google Doc."""
    # First get doc to find the end index
    data, err = run_gws([
        "docs", "documents", "get",
        "--params", json.dumps({"documentId": args.doc_id})
    ])
    if err:
        _handle_error(err)

    # Find end index
    body = data.get("body", {})
    content = body.get("content", [])
    end_index = 1
    if content:
        end_index = content[-1].get("endIndex", 1) - 1

    # Insert text at end
    batch_body = json.dumps({
        "requests": [{
            "insertText": {
                "location": {"index": end_index},
                "text": args.text
            }
        }]
    })

    # Use GWS — payload is small enough for command line
    update_data, err = run_gws([
        "docs", "documents", "batchUpdate",
        "--params", json.dumps({"documentId": args.doc_id}),
        "--json", batch_body
    ])
    if err:
        _handle_error(err)

    if args.json_output:
        print(json.dumps(update_data, indent=2))
    else:
        print(f"Appended {len(args.text)} characters to document.")


def docs_export(args):
    """Export a Google Doc as PDF, DOCX, TXT, or HTML."""
    format_map = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "txt": "text/plain",
        "html": "text/html",
    }
    fmt = args.format or "pdf"
    if fmt not in format_map:
        print(f"ERROR: Unsupported format '{fmt}'. Use: pdf, docx, txt, html", file=sys.stderr)
        sys.exit(1)

    export_mime = format_map[fmt]

    # Get doc name for default output filename
    if not args.output:
        info_data, err = run_gws([
            "drive", "files", "get",
            "--params", json.dumps({"fileId": args.doc_id, "fields": "name"})
        ])
        if err:
            _handle_error(err)
        name = info_data.get("name", "document") if isinstance(info_data, dict) else "document"
        output_path = f"{name}.{fmt}"
    else:
        output_path = args.output

    data, err = run_gws([
        "drive", "files", "export",
        "--params", json.dumps({"fileId": args.doc_id, "mimeType": export_mime}),
        "--output", output_path
    ], timeout=60)
    if err:
        _handle_error(err)

    print(f"Exported: {output_path}")


# ── Sheets Commands ───────────────────────────────────────────────

def sheets_create(args):
    """Create a new Google Spreadsheet."""
    body = {"properties": {"title": args.title or "Untitled Spreadsheet"}}
    if args.sheets:
        # Create multiple named sheets
        sheet_names = [s.strip() for s in args.sheets.split(",")]
        body["sheets"] = [{"properties": {"title": name}} for name in sheet_names]

    data, err = run_gws([
        "sheets", "spreadsheets", "create",
        "--json", json.dumps(body)
    ])
    if err:
        _handle_error(err)

    sid = data.get("spreadsheetId", "") if isinstance(data, dict) else ""
    if args.json_output:
        print(json.dumps(data, indent=2))
    else:
        print(f"Created: {data.get('properties', {}).get('title', '')}")
        print(f"  ID: {sid}")
        print(f"  Link: https://docs.google.com/spreadsheets/d/{sid}/edit")


def sheets_read(args):
    """Read values from a spreadsheet range."""
    params = {"spreadsheetId": args.spreadsheet_id, "range": args.range}
    data, err = run_gws([
        "sheets", "spreadsheets", "values", "get",
        "--params", json.dumps(params)
    ])
    if err:
        _handle_error(err)

    if args.json_output:
        print(json.dumps(data, indent=2))
    else:
        values = data.get("values", []) if isinstance(data, dict) else []
        if not values:
            print("No data found.")
            return
        for row in values:
            print("\t".join(str(cell) for cell in row))


def sheets_write(args):
    """Write values to a spreadsheet range."""
    # Parse values: comma-separated for columns, semicolons for rows
    # e.g. "Name,Email,Phone;John,john@test.com,555-1234"
    rows = []
    for row_str in args.values.split(";"):
        rows.append([cell.strip() for cell in row_str.split(",")])

    body = {"values": rows}
    params = {
        "spreadsheetId": args.spreadsheet_id,
        "range": args.range,
        "valueInputOption": "USER_ENTERED",
    }
    data, err = run_gws([
        "sheets", "spreadsheets", "values", "update",
        "--params", json.dumps(params),
        "--json", json.dumps(body)
    ])
    if err:
        _handle_error(err)

    if args.json_output:
        print(json.dumps(data, indent=2))
    else:
        updated = data.get("updatedCells", 0) if isinstance(data, dict) else 0
        print(f"Updated {updated} cells in {args.range}")


def sheets_append(args):
    """Append rows to a spreadsheet."""
    rows = []
    for row_str in args.values.split(";"):
        rows.append([cell.strip() for cell in row_str.split(",")])

    body = {"values": rows}
    params = {
        "spreadsheetId": args.spreadsheet_id,
        "range": args.range,
        "valueInputOption": "USER_ENTERED",
        "insertDataOption": "INSERT_ROWS",
    }
    data, err = run_gws([
        "sheets", "spreadsheets", "values", "append",
        "--params", json.dumps(params),
        "--json", json.dumps(body)
    ])
    if err:
        _handle_error(err)

    if args.json_output:
        print(json.dumps(data, indent=2))
    else:
        updated = data.get("updates", {}).get("updatedCells", 0) if isinstance(data, dict) else 0
        print(f"Appended {updated} cells")


def sheets_info(args):
    """Get spreadsheet metadata (sheets, titles, row counts)."""
    data, err = run_gws([
        "sheets", "spreadsheets", "get",
        "--params", json.dumps({"spreadsheetId": args.spreadsheet_id})
    ])
    if err:
        _handle_error(err)

    if args.json_output:
        print(json.dumps(data, indent=2))
    else:
        props = data.get("properties", {}) if isinstance(data, dict) else {}
        print(f"Title: {props.get('title', '')}")
        print(f"ID: {data.get('spreadsheetId', '')}")
        print(f"Link: https://docs.google.com/spreadsheets/d/{data.get('spreadsheetId', '')}/edit")
        sheets = data.get("sheets", [])
        print(f"Sheets ({len(sheets)}):")
        for s in sheets:
            sp = s.get("properties", {})
            grid = sp.get("gridProperties", {})
            print(f"  - {sp.get('title', '')} ({grid.get('rowCount', 0)} rows x {grid.get('columnCount', 0)} cols)")


# ── Slides Commands ───────────────────────────────────────────────

def slides_create(args):
    """Create a new Google Slides presentation."""
    body = {"title": args.title or "Untitled Presentation"}
    data, err = run_gws([
        "slides", "presentations", "create",
        "--json", json.dumps(body)
    ])
    if err:
        _handle_error(err)

    pid = data.get("presentationId", "") if isinstance(data, dict) else ""
    if args.json_output:
        print(json.dumps(data, indent=2))
    else:
        print(f"Created: {data.get('title', '')}")
        print(f"  ID: {pid}")
        print(f"  Link: https://docs.google.com/presentation/d/{pid}/edit")


def slides_read(args):
    """Read slide content from a presentation."""
    data, err = run_gws([
        "slides", "presentations", "get",
        "--params", json.dumps({"presentationId": args.presentation_id})
    ])
    if err:
        _handle_error(err)

    if args.json_output:
        print(json.dumps(data, indent=2))
    else:
        print(f"Title: {data.get('title', '')}")
        slides = data.get("slides", [])
        print(f"Slides: {len(slides)}")
        for i, slide in enumerate(slides, 1):
            texts = []
            for elem in slide.get("pageElements", []):
                shape = elem.get("shape", {})
                text_content = shape.get("text", {})
                for te in text_content.get("textElements", []):
                    tr = te.get("textRun", {})
                    if tr.get("content", "").strip():
                        texts.append(tr["content"].strip())
            content_preview = " | ".join(texts)[:100] if texts else "(empty slide)"
            print(f"  Slide {i}: {content_preview}")


def slides_export(args):
    """Export a presentation as PDF or PPTX."""
    format_map = {
        "pdf": "application/pdf",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    }
    fmt = args.format or "pdf"
    if fmt not in format_map:
        print(f"ERROR: Unsupported format '{fmt}'. Use: pdf, pptx", file=sys.stderr)
        sys.exit(1)

    if not args.output:
        info_data, err = run_gws([
            "drive", "files", "get",
            "--params", json.dumps({"fileId": args.presentation_id, "fields": "name"})
        ])
        name = info_data.get("name", "presentation") if isinstance(info_data, dict) and not err else "presentation"
        output_path = f"{name}.{fmt}"
    else:
        output_path = args.output

    data, err = run_gws([
        "drive", "files", "export",
        "--params", json.dumps({"fileId": args.presentation_id, "mimeType": format_map[fmt]}),
        "--output", output_path
    ], timeout=60)
    if err:
        _handle_error(err)

    print(f"Exported: {output_path}")


# ── Tasks Commands ────────────────────────────────────────────────

def tasks_list(args):
    """List task lists or tasks within a list."""
    if args.list_id:
        # List tasks in a specific list
        params = {"tasklist": args.list_id, "maxResults": args.max or 20, "showCompleted": True}
        data, err = run_gws(["tasks", "tasks", "list", "--params", json.dumps(params)])
        if err:
            _handle_error(err)
        items = data.get("items", []) if isinstance(data, dict) else []
        if args.json_output:
            print(json.dumps(items, indent=2))
        else:
            for t in items:
                status = "done" if t.get("status") == "completed" else "    "
                print(f"  [{status}] {t.get('title', '')}  (id: {t.get('id', '')[:12]}...)")
    else:
        # List all task lists
        data, err = run_gws(["tasks", "tasklists", "list", "--params", json.dumps({"maxResults": 20})])
        if err:
            _handle_error(err)
        items = data.get("items", []) if isinstance(data, dict) else []
        if args.json_output:
            print(json.dumps(items, indent=2))
        else:
            for tl in items:
                print(f"  {tl.get('title', '')}  (id: {tl.get('id', '')})")


def tasks_add(args):
    """Add a task to a task list."""
    body = {"title": args.title}
    if args.notes:
        body["notes"] = args.notes
    if args.due:
        body["due"] = args.due + "T00:00:00.000Z" if "T" not in args.due else args.due

    data, err = run_gws([
        "tasks", "tasks", "insert",
        "--params", json.dumps({"tasklist": args.list_id}),
        "--json", json.dumps(body)
    ])
    if err:
        _handle_error(err)

    if args.json_output:
        print(json.dumps(data, indent=2))
    else:
        print(f"Added: {data.get('title', '')}")


def tasks_complete(args):
    """Mark a task as completed."""
    data, err = run_gws([
        "tasks", "tasks", "patch",
        "--params", json.dumps({"tasklist": args.list_id, "task": args.task_id}),
        "--json", json.dumps({"status": "completed"})
    ])
    if err:
        _handle_error(err)
    print(f"Completed: {data.get('title', '')}" if isinstance(data, dict) else "Task completed.")


# ── Test Command ───────────────────────────────────────────────────

def test_connection(args):
    """Test all Google integrations."""
    print("Testing Google Workspace integration...\n")

    # Test 1: gws auth
    print("1. gws CLI auth status...")
    data, err = run_gws(["auth", "status"])
    if err:
        print(f"   FAIL: {err}")
    else:
        token_valid = data.get("token_valid", False) if isinstance(data, dict) else False
        user = data.get("user", "unknown") if isinstance(data, dict) else "unknown"
        status = "PASS" if token_valid else "FAIL (token expired)"
        print(f"   {status} — {user}")

    # Test 2: Calendar read
    print("2. Calendar access...")
    data, err = run_gws([
        "calendar", "events", "list",
        "--params", json.dumps({
            "calendarId": "primary",
            "maxResults": 1,
            "singleEvents": True,
            "orderBy": "startTime",
            "timeMin": _now_iso()
        })
    ])
    if err:
        print(f"   FAIL: {err}")
    else:
        print(f"   PASS — calendar readable")

    # Test 3: Gmail read
    print("3. Gmail access...")
    data, err = run_gws([
        "gmail", "users", "getProfile",
        "--params", json.dumps({"userId": "me"})
    ])
    if err:
        print(f"   FAIL: {err}")
    else:
        email = data.get("emailAddress", "unknown") if isinstance(data, dict) else "unknown"
        print(f"   PASS — {email}")

    # Test 4: SMTP fallback
    print("4. SMTP fallback...")
    gmail_pass = os.environ.get("GMAIL_APP_PASSWORD")
    if gmail_pass:
        print(f"   PASS — GMAIL_APP_PASSWORD configured")
    else:
        print(f"   FAIL — GMAIL_APP_PASSWORD not in .env.agents")

    # Test 5: Drive access
    print("5. Drive access...")
    data, err = run_gws([
        "drive", "files", "list",
        "--params", json.dumps({"pageSize": 1})
    ])
    if err:
        print(f"   FAIL: {err}")
    else:
        print(f"   PASS — drive readable")

    # Test 6: Docs access
    print("6. Docs access...")
    # Just verify the endpoint responds (list recent docs)
    data, err = run_gws([
        "drive", "files", "list",
        "--params", json.dumps({"pageSize": 1, "q": "mimeType='application/vnd.google-apps.document'"})
    ])
    if err:
        print(f"   FAIL: {err}")
    else:
        files = data.get("files", []) if isinstance(data, dict) else []
        print(f"   PASS — {len(files)} recent doc(s) found")

    # Test 7: Sheets access
    print("7. Sheets access...")
    data, err = run_gws([
        "sheets", "spreadsheets", "create",
        "--dry-run",
        "--json", json.dumps({"properties": {"title": "test"}})
    ])
    # dry-run may not be supported for all endpoints, so just check drive for sheets files
    data, err = run_gws([
        "drive", "files", "list",
        "--params", json.dumps({"pageSize": 1, "q": "mimeType='application/vnd.google-apps.spreadsheet'"})
    ])
    if err:
        print(f"   FAIL: {err}")
    else:
        print(f"   PASS — sheets accessible")

    # Test 8: Slides access
    print("8. Slides access...")
    data, err = run_gws([
        "drive", "files", "list",
        "--params", json.dumps({"pageSize": 1, "q": "mimeType='application/vnd.google-apps.presentation'"})
    ])
    if err:
        print(f"   FAIL: {err}")
    else:
        print(f"   PASS — slides accessible")

    # Test 9: Tasks access
    print("9. Tasks access...")
    data, err = run_gws([
        "tasks", "tasklists", "list",
        "--params", json.dumps({"maxResults": 1})
    ])
    if err:
        print(f"   FAIL: {err}")
    else:
        print(f"   PASS — tasks accessible")

    # Test 10: Meet link
    print("10. Google Meet link...")
    meet = os.environ.get("GOOGLE_MEET_LINK")
    if meet:
        print(f"   PASS — {meet}")
    else:
        print(f"   WARN — no static GOOGLE_MEET_LINK in .env.agents")

    print("\nDone.")


# ── Helpers ────────────────────────────────────────────────────────

def _handle_error(err):
    """Print error and exit."""
    if err == "AUTH_EXPIRED":
        print("ERROR: gws auth expired. Run: gws auth login", file=sys.stderr)
    else:
        print(f"ERROR: {err}", file=sys.stderr)
    sys.exit(1)


def _human_size(num_bytes):
    """Convert bytes to human-readable size."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num_bytes) < 1024:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} PB"


def _extract_doc_text(doc_data):
    """Extract plain text from a Google Docs API document response."""
    body = doc_data.get("body", {})
    content = body.get("content", [])
    text_parts = []
    for block in content:
        paragraph = block.get("paragraph")
        if paragraph:
            for element in paragraph.get("elements", []):
                text_run = element.get("textRun")
                if text_run:
                    text_parts.append(text_run.get("content", ""))
    return "".join(text_parts)


def _now_iso():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _encode_email(to, subject, body):
    """Create base64url encoded email for Gmail API."""
    import base64
    gmail_user = os.environ.get("GMAIL_USER", "conaugh@oasisai.work")
    message = MIMEText(body)
    message["to"] = to
    message["from"] = f"Conaugh McKenna <{gmail_user}>"
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return raw


# ── CLI Parser ─────────────────────────────────────────────────────

def main():
    load_env()

    parser = argparse.ArgumentParser(description="Google Workspace CLI Tool")
    parser.add_argument("--json", dest="json_output", action="store_true", help="Output JSON")
    subparsers = parser.add_subparsers(dest="service")

    # Calendar
    cal_parser = subparsers.add_parser("calendar", help="Google Calendar operations")
    cal_sub = cal_parser.add_subparsers(dest="action")

    cal_list = cal_sub.add_parser("list", help="List upcoming events")
    cal_list.add_argument("--max", type=int, default=10)
    cal_list.add_argument("--json", dest="json_output", action="store_true")

    cal_create = cal_sub.add_parser("create", help="Create event")
    cal_create.add_argument("--title", required=True)
    cal_create.add_argument("--start", required=True, help="ISO datetime")
    cal_create.add_argument("--end", required=True, help="ISO datetime")
    cal_create.add_argument("--attendees", help="Comma-separated emails")
    cal_create.add_argument("--meet", action="store_true", help="Attach Google Meet link")
    cal_create.add_argument("--description", help="Event description")
    cal_create.add_argument("--timezone", default="America/Toronto")
    cal_create.add_argument("--json", dest="json_output", action="store_true")

    cal_delete = cal_sub.add_parser("delete", help="Delete event")
    cal_delete.add_argument("event_id")
    cal_delete.add_argument("--json", dest="json_output", action="store_true")

    # Gmail
    gmail_parser = subparsers.add_parser("gmail", help="Gmail operations")
    gmail_sub = gmail_parser.add_subparsers(dest="action")

    gmail_s = gmail_sub.add_parser("send", help="Send email")
    gmail_s.add_argument("--to", required=True)
    gmail_s.add_argument("--subject", required=True)
    gmail_s.add_argument("--body", required=True)
    gmail_s.add_argument("--json", dest="json_output", action="store_true")
    # Branded HTML shell (OASIS AI template) is the default — agents send
    # client-facing email under the operator's identity, so the brand should
    # be there automatically. --plain opts out for the rare case the operator
    # wants a stripped-down send (verification mails, internal-only relays).
    gmail_s.add_argument("--branded", action="store_true", default=True,
                         help="Wrap body in OASIS AI branded HTML shell (default)")
    gmail_s.add_argument("--plain", action="store_true",
                         help="Send plain-text only (overrides --branded)")
    gmail_s.add_argument("--cta-label", dest="cta_label", default=None,
                         help="Optional CTA button text (requires --cta-url)")
    gmail_s.add_argument("--cta-url", dest="cta_url", default=None,
                         help="Optional CTA button URL (requires --cta-label)")

    gmail_l = gmail_sub.add_parser("list", help="List messages")
    gmail_l.add_argument("--max", type=int, default=10)
    gmail_l.add_argument("--json", dest="json_output", action="store_true")

    gmail_r = gmail_sub.add_parser("read", help="Read message")
    gmail_r.add_argument("message_id")
    gmail_r.add_argument("--json", dest="json_output", action="store_true")

    # Drive
    drive_parser = subparsers.add_parser("drive", help="Google Drive operations")
    drive_sub = drive_parser.add_subparsers(dest="action")

    drv_list = drive_sub.add_parser("list", help="List files")
    drv_list.add_argument("--max", type=int, default=10)
    drv_list.add_argument("--query", help="Drive search query (e.g. \"name contains 'report'\")")
    drv_list.add_argument("--json", dest="json_output", action="store_true")

    drv_upload = drive_sub.add_parser("upload", help="Upload file")
    drv_upload.add_argument("--file", required=True, help="Local file path")
    drv_upload.add_argument("--name", help="Custom name (default: filename)")
    drv_upload.add_argument("--folder", help="Parent folder ID")
    drv_upload.add_argument("--json", dest="json_output", action="store_true")

    drv_download = drive_sub.add_parser("download", help="Download file")
    drv_download.add_argument("file_id")
    drv_download.add_argument("--output", help="Output path")
    drv_download.add_argument("--json", dest="json_output", action="store_true")

    drv_delete = drive_sub.add_parser("delete", help="Delete file")
    drv_delete.add_argument("file_id")
    drv_delete.add_argument("--json", dest="json_output", action="store_true")

    drv_info = drive_sub.add_parser("info", help="Get file info")
    drv_info.add_argument("file_id")
    drv_info.add_argument("--json", dest="json_output", action="store_true")

    drv_share = drive_sub.add_parser("share", help="Share file")
    drv_share.add_argument("file_id")
    drv_share.add_argument("--email", required=True, help="Email to share with")
    drv_share.add_argument("--role", default="writer", help="Permission role (reader/writer/commenter)")
    drv_share.add_argument("--json", dest="json_output", action="store_true")

    # Docs
    docs_parser = subparsers.add_parser("docs", help="Google Docs operations")
    docs_sub = docs_parser.add_subparsers(dest="action")

    doc_create = docs_sub.add_parser("create", help="Create a Google Doc")
    doc_create.add_argument("--title", help="Document title")
    doc_create.add_argument("--content", help="Plain text content")
    doc_create.add_argument("--html", help="Path to HTML file to import")
    doc_create.add_argument("--folder", help="Parent folder ID")
    doc_create.add_argument("--json", dest="json_output", action="store_true")

    doc_read = docs_sub.add_parser("read", help="Read a Google Doc")
    doc_read.add_argument("doc_id")
    doc_read.add_argument("--json", dest="json_output", action="store_true")

    doc_append = docs_sub.add_parser("append", help="Append text to a doc")
    doc_append.add_argument("doc_id")
    doc_append.add_argument("--text", required=True, help="Text to append")
    doc_append.add_argument("--json", dest="json_output", action="store_true")

    doc_export = docs_sub.add_parser("export", help="Export doc as PDF/DOCX/TXT/HTML")
    doc_export.add_argument("doc_id")
    doc_export.add_argument("--format", default="pdf", help="Export format: pdf, docx, txt, html")
    doc_export.add_argument("--output", help="Output path")
    doc_export.add_argument("--json", dest="json_output", action="store_true")

    # Sheets
    sheets_parser = subparsers.add_parser("sheets", help="Google Sheets operations")
    sheets_sub = sheets_parser.add_subparsers(dest="action")

    sh_create = sheets_sub.add_parser("create", help="Create a spreadsheet")
    sh_create.add_argument("--title", help="Spreadsheet title")
    sh_create.add_argument("--sheets", help="Comma-separated sheet names (e.g. 'Sheet1,Summary,Data')")
    sh_create.add_argument("--json", dest="json_output", action="store_true")

    sh_read = sheets_sub.add_parser("read", help="Read values from a range")
    sh_read.add_argument("spreadsheet_id")
    sh_read.add_argument("--range", default="Sheet1", help="Range (e.g. 'Sheet1!A1:Z')")
    sh_read.add_argument("--json", dest="json_output", action="store_true")

    sh_write = sheets_sub.add_parser("write", help="Write values to a range")
    sh_write.add_argument("spreadsheet_id")
    sh_write.add_argument("--range", required=True, help="Target range (e.g. 'Sheet1!A1')")
    sh_write.add_argument("--values", required=True, help="Values: comma=cols, semicolon=rows (e.g. 'Name,Email;John,j@t.com')")
    sh_write.add_argument("--json", dest="json_output", action="store_true")

    sh_append = sheets_sub.add_parser("append", help="Append rows")
    sh_append.add_argument("spreadsheet_id")
    sh_append.add_argument("--range", default="Sheet1", help="Target sheet/range")
    sh_append.add_argument("--values", required=True, help="Values: comma=cols, semicolon=rows")
    sh_append.add_argument("--json", dest="json_output", action="store_true")

    sh_info = sheets_sub.add_parser("info", help="Get spreadsheet metadata")
    sh_info.add_argument("spreadsheet_id")
    sh_info.add_argument("--json", dest="json_output", action="store_true")

    # Slides
    slides_parser = subparsers.add_parser("slides", help="Google Slides operations")
    slides_sub = slides_parser.add_subparsers(dest="action")

    sl_create = slides_sub.add_parser("create", help="Create a presentation")
    sl_create.add_argument("--title", help="Presentation title")
    sl_create.add_argument("--json", dest="json_output", action="store_true")

    sl_read = slides_sub.add_parser("read", help="Read slide content")
    sl_read.add_argument("presentation_id")
    sl_read.add_argument("--json", dest="json_output", action="store_true")

    sl_export = slides_sub.add_parser("export", help="Export as PDF or PPTX")
    sl_export.add_argument("presentation_id")
    sl_export.add_argument("--format", default="pdf", help="Export format: pdf, pptx")
    sl_export.add_argument("--output", help="Output path")
    sl_export.add_argument("--json", dest="json_output", action="store_true")

    # Tasks
    tasks_parser = subparsers.add_parser("tasks", help="Google Tasks operations")
    tasks_sub = tasks_parser.add_subparsers(dest="action")

    tk_list = tasks_sub.add_parser("list", help="List task lists or tasks")
    tk_list.add_argument("--list-id", help="Task list ID (omit to list all task lists)")
    tk_list.add_argument("--max", type=int, default=20)
    tk_list.add_argument("--json", dest="json_output", action="store_true")

    tk_add = tasks_sub.add_parser("add", help="Add a task")
    tk_add.add_argument("--list-id", required=True, help="Task list ID")
    tk_add.add_argument("--title", required=True)
    tk_add.add_argument("--notes", help="Task notes/description")
    tk_add.add_argument("--due", help="Due date (YYYY-MM-DD)")
    tk_add.add_argument("--json", dest="json_output", action="store_true")

    tk_complete = tasks_sub.add_parser("complete", help="Mark task as done")
    tk_complete.add_argument("--list-id", required=True)
    tk_complete.add_argument("--task-id", required=True)
    tk_complete.add_argument("--json", dest="json_output", action="store_true")

    # Test
    subparsers.add_parser("test", help="Test all integrations")

    args = parser.parse_args()

    if args.service == "calendar":
        if args.action == "list":
            calendar_list(args)
        elif args.action == "create":
            calendar_create(args)
        elif args.action == "delete":
            calendar_delete(args)
        else:
            cal_parser.print_help()
    elif args.service == "gmail":
        if args.action == "send":
            gmail_send(args)
        elif args.action == "list":
            gmail_list(args)
        elif args.action == "read":
            gmail_read(args)
        else:
            gmail_parser.print_help()
    elif args.service == "drive":
        if args.action == "list":
            drive_list(args)
        elif args.action == "upload":
            drive_upload(args)
        elif args.action == "download":
            drive_download(args)
        elif args.action == "delete":
            drive_delete(args)
        elif args.action == "info":
            drive_info(args)
        elif args.action == "share":
            drive_share(args)
        else:
            drive_parser.print_help()
    elif args.service == "docs":
        if args.action == "create":
            docs_create(args)
        elif args.action == "read":
            docs_read(args)
        elif args.action == "append":
            docs_append(args)
        elif args.action == "export":
            docs_export(args)
        else:
            docs_parser.print_help()
    elif args.service == "sheets":
        if args.action == "create":
            sheets_create(args)
        elif args.action == "read":
            sheets_read(args)
        elif args.action == "write":
            sheets_write(args)
        elif args.action == "append":
            sheets_append(args)
        elif args.action == "info":
            sheets_info(args)
        else:
            sheets_parser.print_help()
    elif args.service == "slides":
        if args.action == "create":
            slides_create(args)
        elif args.action == "read":
            slides_read(args)
        elif args.action == "export":
            slides_export(args)
        else:
            slides_parser.print_help()
    elif args.service == "tasks":
        if args.action == "list":
            tasks_list(args)
        elif args.action == "add":
            tasks_add(args)
        elif args.action == "complete":
            tasks_complete(args)
        else:
            tasks_parser.print_help()
    elif args.service == "test":
        test_connection(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
