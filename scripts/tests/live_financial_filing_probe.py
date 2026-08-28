"""LIVE end-to-end probe for financial email filing.

Sends one real email per class to the OASIS inbox, waits for the sweep to
process them, then asserts the Gmail label that actually landed on each.

This exists because unit tests cannot catch the failure that started this:
every layer was individually "correct" and the system still lost a receipt.
The only thing that proves filing works is a real message getting a real label
over real IMAP.

    python scripts/tests/live_financial_filing_probe.py send
    python scripts/tests/live_financial_filing_probe.py verify
    python scripts/tests/live_financial_filing_probe.py cleanup

`send` marks every probe with a unique tag in the subject so `verify` and
`cleanup` can find exactly these messages and nothing else.
"""

from __future__ import annotations

import argparse
import email as emod
import imaplib
import smtplib
import sys
import time
from email.message import EmailMessage
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
for p in (str(SCRIPTS_DIR), str(SCRIPTS_DIR / "integrations")):
    if p not in sys.path:
        sys.path.insert(0, p)

from email_engine import load_env, _decode_header_value  # noqa: E402
from lib.gmail_labels import read_labels  # noqa: E402

TAG = "OASIS-FILING-PROBE"

# A minimal but genuinely valid one-page PDF. The point of the attachment case
# is that the amount exists ONLY in the attachment - which is exactly how the
# Google Cloud invoice defeated the body-text rubric.
_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 100]>>endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF\n"
)

# (key, subject, body, attachment_filename|None, expected label leaf|None)
CASES = [
    ("gcp_invoice_no_amount",
     "Google Cloud Platform & APIs: Your invoice is available for 018D76-TEST",
     "Your invoice is available for your Google Cloud Platform & APIs account.\n"
     "Account ID: 018D76-TEST\nView and download it in the payments centre.",
     "invoice_018D76_TEST.pdf",
     "Business Expenses"),

    ("vendor_invoice_with_amount",
     "Invoice #TEST-4471 from Anthropic",
     "Thanks for your payment. Amount due: $120.00 USD for the Max plan.",
     None,
     "Business Expenses"),

    ("stripe_payout_income",
     "Your payout of $2,480.00 is on its way",
     "Your payout of $2,480.00 CAD has been sent to your bank account.",
     None,
     "Income & Invoices"),

    ("bank_statement_notice",
     "Your monthly statement is ready",
     "Your account statement for July is available to view in online banking.",
     None,
     "Statements & Notices"),

    ("marketing_blast_must_not_label",
     "We are cutting prices by 4x on average",
     "New pricing! Save 40% when you upgrade now. Compare plans and see the "
     "difference. Limited-time offer.",
     None,
     None),

    ("security_alert_must_not_label",
     "Security alert",
     "A new sign-in on Apple iPhone 14. If this was you, you don't need to do "
     "anything.",
     None,
     None),
]


def _creds():
    env = load_env()
    addr = env.get("GMAIL_ADDRESS") or env.get("GMAIL_USER")
    pw = env.get("GMAIL_APP_PASSWORD")
    if not addr or not pw:
        raise SystemExit("no Gmail credentials available")
    return addr, pw


def _imap(addr, pw):
    M = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    M.socket().settimeout(60)
    M.login(addr, pw)
    return M


def cmd_send(args):
    addr, pw = _creds()
    stamp = time.strftime("%H%M%S")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=60) as s:
        s.login(addr, pw)
        for key, subject, body, attach, _expect in CASES:
            m = EmailMessage()
            # The probe tag rides in the subject so verify/cleanup can scope
            # themselves to exactly these messages.
            m["Subject"] = f"{subject} [{TAG}-{stamp}-{key}]"
            m["From"] = addr
            m["To"] = addr
            m.set_content(body)
            if attach:
                m.add_attachment(_PDF, maintype="application",
                                 subtype="pdf", filename=attach)
            s.send_message(m)
            print(f"  sent  {key}")
    print(f"\nprobe id: {TAG}-{stamp}")
    print("now run the sweep, then: live_financial_filing_probe.py verify")


def cmd_verify(args):
    addr, pw = _creds()
    M = _imap(addr, pw)
    M.select("INBOX")
    ok = fail = 0
    for key, subject, _body, _attach, expect in CASES:
        st, data = M.uid("SEARCH", None, "SUBJECT", f'"{TAG}"', "SUBJECT", f'"{key}"')
        uids = data[0].split() if data and data[0] else []
        if not uids:
            print(f"  MISSING  {key}: no probe message found")
            fail += 1
            continue
        uid = uids[-1]
        labels = read_labels(M, uid, use_uid=True) or []
        receipts = [l for l in labels if l.startswith("Receipts/")]
        want = f"Receipts/2026/{expect}" if expect else None

        if want is None:
            good = not receipts
            detail = f"expected NO Receipts label, got {receipts}"
        else:
            good = want in receipts
            detail = f"expected {want!r}, got {receipts}"
        print(f"  {'PASS' if good else 'FAIL'}  {key}: {detail}")
        ok, fail = (ok + 1, fail) if good else (ok, fail + 1)
    M.close()
    M.logout()
    print(f"\n{ok} passed, {fail} failed")
    return 1 if fail else 0


def cmd_cleanup(args):
    """Remove the probe messages. Only ever touches subjects carrying TAG."""
    addr, pw = _creds()
    M = _imap(addr, pw)
    M.select("INBOX")
    st, data = M.uid("SEARCH", None, "SUBJECT", f'"{TAG}"')
    uids = data[0].split() if data and data[0] else []
    print(f"found {len(uids)} probe message(s)")
    for uid in uids:
        M.uid("STORE", uid, "+X-GM-LABELS", "\\Trash")
    M.expunge()
    M.close()
    M.logout()
    print(f"trashed {len(uids)} probe message(s)")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("send")
    sub.add_parser("verify")
    sub.add_parser("cleanup")
    args = ap.parse_args()
    return {"send": cmd_send, "verify": cmd_verify,
            "cleanup": cmd_cleanup}[args.cmd](args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
