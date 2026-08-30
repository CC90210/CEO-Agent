"""Backfill Gmail labels onto financial mail that was never filed.

WHY
---
The filing automation dropped receipts for an unknown stretch of 2026 (the
`email.financial_handoff` bus shows a four-day publish drought before the fix,
and the underlying misroute - a vendor invoice read as `low_priority` and
archived silently - is not time-bounded). A label is only useful at tax time if
it is COMPLETE, so the going-forward fix has to be paired with a sweep over
what was already missed.

SAFETY
------
  * Dry run by DEFAULT. `--apply` is required to write anything.
  * ADD-ONLY. Labels are added with +X-GM-LABELS; nothing is ever removed,
    no message is deleted, moved, or marked read. Every effect is reversible by
    removing the label.
  * IDEMPOTENT. A message that already carries the target label is skipped, so
    re-running costs nothing and cannot double-apply.
  * Reads All Mail, not just the inbox, because archived receipts are exactly
    the ones that went missing.

USAGE
-----
    python scripts/backfill_financial_labels.py --year 2026
    python scripts/backfill_financial_labels.py --year 2026 --csv report.csv
    python scripts/backfill_financial_labels.py --year 2026 --apply
"""

from __future__ import annotations

import argparse
import csv
import email as emod
import imaplib
import re
import sys
from collections import Counter
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
for _p in (str(SCRIPTS_DIR), str(SCRIPTS_DIR / "integrations")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from email_engine import (  # noqa: E402
    _decode_header_value,
    _extract_attachment_meta,
    extract_body_full,
    load_env,
)
from lib.financial_labels import assess  # noqa: E402
from lib.gmail_labels import LabelError, apply_label  # noqa: E402

ALL_MAIL = '"[Gmail]/All Mail"'

# Cheap subject-level prefilter so we do not pull the full body of several
# thousand messages. Deliberately WIDER than the real gate: anything this lets
# through is then judged properly by `assess`, and anything with an attachment
# is fetched regardless of subject.
_SUBJECT_HINT = (
    "invoice", "receipt", "payment", "payout", "billing", "bill",
    "statement", "charged", "charge", "subscription", "renewal", "refund",
    "remittance", "tax", "cra", "gst", "hst", "qst", "order confirmation",
    "purchase", "paid", "transaction", "deposit", "credit note", "facture",
)


def _connect():
    env = load_env()
    addr = env.get("GMAIL_ADDRESS") or env.get("GMAIL_USER")
    pw = env.get("GMAIL_APP_PASSWORD")
    if not addr or not pw:
        raise SystemExit("no Gmail credentials available (GMAIL_ADDRESS / "
                         "GMAIL_APP_PASSWORD)")
    M = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    M.socket().settimeout(90)
    M.login(addr, pw)
    return M, addr


def _search_year(M, year: int) -> list:
    status, data = M.uid("SEARCH", None,
                         "SINCE", f"1-Jan-{year}",
                         "BEFORE", f"1-Jan-{year + 1}")
    if status != "OK":
        raise SystemExit(f"IMAP SEARCH failed: {status}")
    return data[0].split() if data and data[0] else []


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--apply", action="store_true",
                    help="actually add labels (default: dry run)")
    ap.add_argument("--limit", type=int, default=0,
                    help="stop after N candidates (0 = no limit)")
    ap.add_argument("--csv", help="write the full report to this CSV")
    args = ap.parse_args()

    M, addr = _connect()
    # readonly for a dry run: the server itself refuses a write we did not ask
    # for, rather than trusting this script's own branching.
    M.select(ALL_MAIL, readonly=not args.apply)
    print(f"mailbox : {addr}")
    print(f"scope   : [Gmail]/All Mail, {args.year}")
    print(f"mode    : {'APPLY (writes labels)' if args.apply else 'DRY RUN (no writes)'}\n")

    uids = _search_year(M, args.year)
    print(f"{len(uids)} message(s) in {args.year}; screening...\n")

    rows, counts = [], Counter()
    scanned = 0

    for batch in _chunks(uids, 200):
        ids = b",".join(batch).decode()
        status, data = M.uid("FETCH", ids,
                             "(X-GM-LABELS BODY.PEEK[HEADER.FIELDS "
                             "(SUBJECT FROM DATE)] BODYSTRUCTURE)")
        if status != "OK":
            continue
        # Response items interleave; walk tuples and recover the uid from the
        # envelope prefix of each.
        for item in data:
            if not isinstance(item, tuple):
                continue
            prefix = item[0].decode("utf-8", "replace")
            hdr = emod.message_from_bytes(item[1])
            subject = _decode_header_value(hdr.get("Subject", "") or "")
            sender = _decode_header_value(hdr.get("From", "") or "")
            datehdr = hdr.get("Date")

            m = re.search(r"UID (\d+)", prefix)
            if not m:
                continue
            uid = m.group(1)
            scanned += 1

            existing = []
            lm = re.search(r"X-GM-LABELS \(([^)]*)\)", prefix)
            if lm:
                existing = [x.strip('"').replace("&-", "&")
                            for x in re.findall(r'"[^"]*"|\S+', lm.group(1))]

            # Skip CC's OWN outbound mail. All Mail includes \Sent, and the
            # first dry run proposed filing five copies of an outbound "OASIS
            # AI Solutions - Onboarding & Service Agreement" as a Business
            # EXPENSE. Money CC receives is already captured by the inbound
            # Stripe/customer payment notifications, so dropping \Sent costs no
            # income coverage and removes a whole class of wrong-direction rows.
            if any(l == "\\Sent" for l in existing):
                counts["skipped_sent"] += 1
                continue

            has_attach = "attachment" in prefix.lower()
            subj_hit = any(h in subject.lower() for h in _SUBJECT_HINT)
            if not (subj_hit or has_attach):
                continue

            # Worth a full read: fetch the body and judge properly.
            st2, fd = M.uid("FETCH", uid, "(BODY.PEEK[])")
            if st2 != "OK" or not fd or not isinstance(fd[0], tuple):
                continue
            msg = emod.message_from_bytes(fd[0][1])
            fin = assess({
                "from": sender,
                "subject": subject,
                "body": extract_body_full(msg),
                "attachments": _extract_attachment_meta(msg),
                "date": datehdr,
            })
            if not fin.get("is_financial"):
                continue

            target = fin["label"]
            already = target in existing
            counts["candidates"] += 1
            if already:
                counts["already_filed"] += 1
                status_txt = "already filed"
            else:
                counts[fin["subtype"]] += 1
                status_txt = "WOULD ADD" if not args.apply else "added"
                if args.apply:
                    try:
                        apply_label(M, uid, target, use_uid=True)
                    except LabelError as exc:
                        status_txt = f"FAILED: {exc}"
                        counts["failed"] += 1

            rows.append({
                "date": (datehdr or "")[:31],
                "from": sender[:48],
                "subject": subject[:72],
                "proposed_label": target,
                "existing_labels": ";".join(l for l in existing
                                            if not l.startswith("\\")),
                "status": status_txt,
            })
            if args.limit and counts["candidates"] >= args.limit:
                break
        if args.limit and counts["candidates"] >= args.limit:
            break

    # --- report ---------------------------------------------------------
    to_change = [r for r in rows if r["status"] in ("WOULD ADD", "added")]
    print(f"screened {scanned} message(s)")
    if counts["skipped_sent"]:
        print(f"  skipped (CC's own Sent mail)  : {counts['skipped_sent']}")
    print(f"financial documents found : {counts['candidates']}")
    print(f"  already correctly filed : {counts['already_filed']}")
    print(f"  needing a label         : {len(to_change)}")
    for k in ("expense", "income", "statement"):
        if counts[k]:
            print(f"      {k:10} -> {counts[k]}")
    if counts["failed"]:
        print(f"  FAILED                  : {counts['failed']}")

    if to_change:
        print("\n" + "-" * 100)
        for r in to_change[:60]:
            print(f"{r['date'][:16]:17} {r['from'][:28]:29} "
                  f"{r['subject'][:40]:41} -> {r['proposed_label']}")
        if len(to_change) > 60:
            print(f"... and {len(to_change) - 60} more")
        print("-" * 100)

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else
                               ["date", "from", "subject", "proposed_label",
                                "existing_labels", "status"])
            w.writeheader()
            w.writerows(rows)
        print(f"\nfull report written to {args.csv}")

    if not args.apply and to_change:
        print(f"\nDRY RUN - nothing was written. Re-run with --apply to add "
              f"{len(to_change)} label(s).")

    M.close()
    M.logout()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
