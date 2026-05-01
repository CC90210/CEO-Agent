"""One-shot CRM reconciliation: pull every outbound address from Gmail's
Sent folder over the last N days, match against `leads` where status='new',
flip matched rows to 'contacted', and backfill `lead_interactions` rows so
V5.6's cooldown + send_gateway have accurate history.

Why this exists: CC sent hundreds of cold emails before the V5.6 ledger
existed, and email_log never got the write pattern wired up historically.
The CRM shows 178 leads as 'new' that are actually 'contacted'. Without
this reconciliation, the send_gateway has zero cooldown memory and could
double-send to someone you emailed 2 months ago.

Run:
  python scripts/_reconcile_gmail_sent.py --days 180 --dry-run  # preview
  python scripts/_reconcile_gmail_sent.py --days 180            # apply
  python scripts/_reconcile_gmail_sent.py --days 365 --json

This script is idempotent — re-running does nothing new once the CRM is in
sync.
"""

from __future__ import annotations

import argparse
import email
import email.utils
import imaplib
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def load_env() -> dict[str, str]:
    env_path = PROJECT_ROOT / ".env.agents"
    env_vars: dict[str, str] = {}
    if not env_path.exists():
        return env_vars
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            env_vars[k.strip()] = v.strip()
    for k, v in env_vars.items():
        os.environ.setdefault(k, v)
    return env_vars


def get_supabase():
    from send_gateway import get_supabase as _g
    return _g()


# ---- Gmail IMAP scan -------------------------------------------------------

def imap_scan_sent(env: dict[str, str], days: int, max_messages: int = 3000) -> list[dict]:
    """Connect to Gmail IMAP, scan [Gmail]/Sent Mail for the last N days,
    return a list of {to, subject, date_iso, message_id} dicts.

    Gmail's `ALL` + `SINCE` search is fast even at 3000+ messages."""
    address = env.get("GMAIL_ADDRESS") or env.get("GMAIL_USER")
    password = env.get("GMAIL_APP_PASSWORD")
    if not address or not password:
        raise RuntimeError("GMAIL_ADDRESS/GMAIL_USER + GMAIL_APP_PASSWORD required in .env.agents")

    imap = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    imap.login(address, password)

    # Gmail uses the localized "[Gmail]/Sent Mail" on most accounts, but
    # some clients see "[Gmail]/Sent" or custom labels. Try common names.
    for folder in ('"[Gmail]/Sent Mail"', '"[Gmail]/Sent"', "Sent"):
        status, _ = imap.select(folder, readonly=True)
        if status == "OK":
            selected = folder
            break
    else:
        imap.logout()
        raise RuntimeError("Could not find Gmail Sent folder")

    print(f"  Connected to IMAP, selected {selected}", file=sys.stderr)

    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%d-%b-%Y")
    status, data = imap.search(None, f'(SINCE {since})')
    if status != "OK":
        imap.logout()
        raise RuntimeError(f"IMAP search failed: {status}")

    uids = (data[0] or b"").split()
    total = len(uids)
    print(f"  Found {total} sent messages since {since}", file=sys.stderr)
    uids = uids[-max_messages:]  # most recent N

    sends: list[dict] = []
    for i, uid in enumerate(uids):
        # Fetch only the headers, not the body — faster.
        status, msg_data = imap.fetch(uid, "(BODY.PEEK[HEADER.FIELDS (TO SUBJECT DATE MESSAGE-ID)])")
        if status != "OK" or not msg_data or msg_data[0] is None:
            continue
        raw = msg_data[0][1]
        if not isinstance(raw, bytes):
            continue
        msg = email.message_from_bytes(raw)

        to_raw = msg.get("To", "") or ""
        subject = (msg.get("Subject") or "").strip()[:300]
        date_raw = msg.get("Date", "")
        mid = (msg.get("Message-ID") or "").strip("<>").strip()

        # Multiple To: addresses split on comma
        for addr in email.utils.getaddresses([to_raw]):
            name, email_addr = addr
            email_addr = (email_addr or "").strip().lower()
            if not email_addr or "@" not in email_addr:
                continue
            try:
                dt = email.utils.parsedate_to_datetime(date_raw)
                date_iso = dt.astimezone(timezone.utc).isoformat()
            except Exception:  # noqa: BLE001
                date_iso = None
            sends.append({
                "to": email_addr,
                "to_name": (name or "").strip(),
                "subject": subject,
                "date_iso": date_iso,
                "message_id": mid,
            })
        if (i + 1) % 250 == 0:
            print(f"    parsed {i + 1}/{len(uids)}", file=sys.stderr)

    imap.close()
    imap.logout()
    return sends


# ---- Reconciliation --------------------------------------------------------

def dedupe_most_recent(sends: list[dict]) -> dict[str, dict]:
    """Return dict keyed on to-email, value = most-recent send record."""
    by_email: dict[str, dict] = {}
    for s in sends:
        key = s["to"]
        cur = by_email.get(key)
        if not cur or (s.get("date_iso") or "") > (cur.get("date_iso") or ""):
            by_email[key] = s
    return by_email


def reconcile(days: int, dry_run: bool, output_json: bool) -> int:
    env = load_env()
    print(f"[reconcile] scanning Gmail Sent folder over last {days} days...",
          file=sys.stderr)
    sends = imap_scan_sent(env, days=days)
    by_email = dedupe_most_recent(sends)
    print(f"[reconcile] Gmail Sent: {len(sends)} messages -> "
          f"{len(by_email)} unique recipient emails",
          file=sys.stderr)

    db = get_supabase()
    # Pull every lead with an email (not just status='new'), so we also
    # detect leads marked 'new' but actually emailed, AND leads missing
    # from email_log/lead_interactions entirely.
    leads = (db.table("leads")
             .select("id,name,email,status,source,last_contacted_at")
             .not_.is_("email", "null")
             .execute().data) or []
    leads_by_email = {(l.get("email") or "").lower().strip(): l for l in leads if l.get("email")}
    print(f"[reconcile] CRM leads with email: {len(leads_by_email)}", file=sys.stderr)

    # Classification
    to_flip_new_to_contacted: list[tuple[dict, dict]] = []  # (lead, send)
    already_contacted_in_gmail: list[tuple[dict, dict]] = []
    emailed_no_crm_record: list[dict] = []

    for email_addr, send in by_email.items():
        lead = leads_by_email.get(email_addr)
        if not lead:
            emailed_no_crm_record.append(send)
            continue
        if lead.get("status") == "new":
            to_flip_new_to_contacted.append((lead, send))
        else:
            already_contacted_in_gmail.append((lead, send))

    print(f"\n[reconcile] CLASSIFICATION:")
    print(f"  leads with status='new' but Gmail shows sent: {len(to_flip_new_to_contacted)}")
    print(f"  leads already status!=new and matched in Gmail: {len(already_contacted_in_gmail)}")
    print(f"  Gmail recipients with NO CRM record at all:    {len(emailed_no_crm_record)}")

    # Build the backfill interactions (only for matched leads)
    backfill_rows: list[dict] = []
    for lead, send in to_flip_new_to_contacted + already_contacted_in_gmail:
        if not send.get("date_iso"):
            continue
        backfill_rows.append({
            "lead_id": lead["id"],
            "type": "email_sent",
            "channel": "email",
            "subject": send.get("subject") or None,
            "agent_source": "gmail_historical_backfill",
            "metadata": {
                "message_id": send.get("message_id"),
                "to_name": send.get("to_name"),
                "backfilled_at": datetime.now(timezone.utc).isoformat(),
                "source": "reconcile_gmail_sent.py",
            },
            "created_at": send["date_iso"],
        })

    if dry_run:
        print("\n[reconcile] --dry-run: printing first 10 flips + first 10 orphans")
        for lead, send in to_flip_new_to_contacted[:10]:
            print(f"  FLIP {lead.get('name') or '-':25} {lead.get('email'):40} "
                  f"→ contacted (last send: {send.get('date_iso', '?')[:10]})")
        for s in emailed_no_crm_record[:10]:
            print(f"  ORPHAN (emailed, no CRM): {s['to']:40s} "
                  f"subject={(s.get('subject') or '')[:60]}")
        result = {
            "mode": "dry_run",
            "gmail_sent_count": len(sends),
            "unique_recipients": len(by_email),
            "crm_leads_with_email": len(leads_by_email),
            "would_flip_new_to_contacted": len(to_flip_new_to_contacted),
            "already_contacted_and_matched": len(already_contacted_in_gmail),
            "gmail_recipients_not_in_crm": len(emailed_no_crm_record),
            "backfill_interaction_rows_queued": len(backfill_rows),
        }
        if output_json:
            print(json.dumps(result, indent=2, default=str))
        return 0

    # Apply changes
    flipped = 0
    for lead, send in to_flip_new_to_contacted:
        try:
            db.table("leads").update({
                "status": "contacted",
                "last_contacted_at": send.get("date_iso") or datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "notes": (lead.get("notes") or "").strip() + (
                    ("\n" if lead.get("notes") else "")
                    + f"[reconcile {datetime.now(timezone.utc).date().isoformat()}] "
                    + f"Historical Gmail send detected — flipped new→contacted."
                ),
            }).eq("id", lead["id"]).execute()
            flipped += 1
        except Exception as exc:  # noqa: BLE001
            print(f"  flip failed for {lead.get('email')}: {exc}", file=sys.stderr)

    # Backfill lead_interactions in batches of 100
    backfilled = 0
    for i in range(0, len(backfill_rows), 100):
        batch = backfill_rows[i:i + 100]
        try:
            db.table("lead_interactions").insert(batch).execute()
            backfilled += len(batch)
        except Exception as exc:  # noqa: BLE001
            print(f"  backfill batch failed at offset {i}: {exc}", file=sys.stderr)

    result = {
        "mode": "applied",
        "gmail_sent_count": len(sends),
        "unique_recipients": len(by_email),
        "flipped_new_to_contacted": flipped,
        "backfilled_lead_interactions": backfilled,
        "orphan_recipients_not_in_crm": len(emailed_no_crm_record),
    }
    if output_json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(f"\n[reconcile] DONE")
        print(f"  flipped new -> contacted:  {flipped}")
        print(f"  backfilled interactions:  {backfilled}")
        print(f"  orphan recipients (not in CRM, for manual review): {len(emailed_no_crm_record)}")
    return 0


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=180, help="How far back to scan (default 180)")
    p.add_argument("--dry-run", dest="dry_run", action="store_true")
    p.add_argument("--json", dest="output_json", action="store_true")
    args = p.parse_args()
    sys.exit(reconcile(args.days, args.dry_run, args.output_json))


if __name__ == "__main__":
    main()
