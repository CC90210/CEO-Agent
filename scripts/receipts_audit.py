#!/usr/bin/env python3
"""Receipts audit — reconcile the mailbox against the financial pipeline.

Born 2026-08-23 from the Kimi gap: the UNSEEN-only sweep silently lost any
financial email CC read within the 5-minute window, and earlier eras had their
own leaks (the pre-2026-07-23 SKIP_SENDERS blanket drop destroyed no-reply
vendor receipts; Atlas-disabled windows queued nothing at all). This tool
answers the question none of the point fixes can: "across the WHOLE mailbox,
did every financial email actually get captured?"

Method — coverage by evidence, not by pipeline memory:
  scan   Read [Gmail]/All Mail headers (read-only, BODY.PEEK) since --since,
         cast a WIDE deterministic net for financial-looking mail (vendor
         billing senders, transaction phrases, money amounts, French forms —
         Montreal), and flag every candidate that carries NO Receipts/* Gmail
         label. The label is applied only by Atlas's consumer at booking time,
         so its absence is proof the pipeline never finished with the message.
  apply  Publish an email.financial_handoff event for each gap candidate
         (idempotency-keyed; Atlas's consumer fetches the real document by
         Message-ID, decides direction FROM THE DOCUMENT, labels and books).
         Candidates are clustered by (sender domain, reference/amount hint) so
         a vendor's separate invoice + receipt emails for one purchase hand
         off once, not twice.

Usage:
  python scripts/receipts_audit.py scan  [--since 2026-01-01] [--out tmp/receipts_audit.json]
  python scripts/receipts_audit.py apply [--limit 25] [--audit-file tmp/receipts_audit.json] [--dry-run]
"""
from __future__ import annotations

import argparse
import email
import email.header
import imaplib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = PROJECT_ROOT / "scripts"
for p in (str(SCRIPTS), str(SCRIPTS / "integrations")):
    if p not in sys.path:
        sys.path.insert(0, p)

CAPABILITY_META = {
    "category": "governance.finance",
    "lifecycle": "active",
    "risk": "external_write",
    "triggers": [
        "audit the mailbox for missed receipts",
        "reconcile financial emails against the receipts ledger",
        "backfill missed expense emails to atlas",
    ],
    "owner": "bravo",
    "project": "empire",
    "bridge": {"visible": True, "confirm": True},
}

DEFAULT_SINCE = "2026-01-01"
DEFAULT_OUT = PROJECT_ROOT / "tmp" / "receipts_audit.json"
FETCH_CHUNK = 400

# Reuse the production financial regexes — the audit net must never be weaker
# than the live classifier's.
from inbound_classifier import _MONEY_AMOUNT_RE, _TXN_PHRASE_RE  # noqa: E402

# Billing-shaped local parts on ANY domain.
_BILLING_LOCALS = {
    "billing", "invoice", "invoices", "invoicing", "receipt", "receipts",
    "payment", "payments", "pay", "statements", "statement", "accounting",
    "accounts", "ar", "payout", "payouts", "orders", "order",
}

# Vendor domains whose mail is financial-by-provenance (receipts, payouts,
# renewals). Wide on purpose: false positives cost one skipped candidate in
# review; false negatives are exactly the silent loss CC asked to end.
_VENDOR_DOMAINS = {
    "stripe.com", "paypal.com", "paypal.ca", "squareup.com", "square.com",
    "wise.com", "interac.ca", "payments.interac.ca",
    "godaddy.com", "namecheap.com", "cloudflare.com", "vercel.com",
    "netlify.com", "porkbun.com", "hover.com",
    "apple.com", "adobe.com", "google.com", "microsoft.com",
    "anthropic.com", "openai.com", "moonshot.ai", "moonshot.cn",
    "cursor.com", "cursor.sh", "github.com", "gitlab.com",
    "twilio.com", "kixie.com", "texttorrent.com",
    "canva.com", "figma.com", "notion.so", "linear.app",
    "shopify.com", "intuit.com", "quickbooks.com", "freshbooks.com",
    "waveapps.com", "xero.com", "plaid.com",
    "turso.tech", "supabase.com", "supabase.io", "sentry.io",
    "digitalocean.com", "hetzner.com", "hostinger.com", "ovh.com",
    "amazonaws.com", "amazon.com", "amazon.ca",
    "firecrawl.dev", "browserbase.com",
    "wispr.ai", "flow.wispr.ai", "elevenlabs.io",
    "x.ai", "perplexity.ai", "midjourney.com",
    # 2026-08-23 adversarial-verify additions: every one of these had REAL
    # unlabeled financial mail the first net missed.
    "kraken.com", "interactivebrokers.ca", "interactivebrokers.com",
    "paddle.com", "bestbuy.ca", "e.bestbuy.ca", "kie.ai",
}

# CC's own products — their operational mail (draw requests, demo/stress-test
# notifications) is never a vendor expense. Billing-shaped locals still pass:
# accounting@breezeadvance.com sending a real inter-entity invoice is mail the
# net must keep.
_OWN_APP_DOMAINS = {
    "breezeadvance.credit", "breezeadvance.com", "propflow.app",
    "revline.app", "credport.app",
}

# Senders whose money-shaped subjects are never financial documents (proven
# false-positive classes from the 2026-08-23 verification: job alerts and AI
# newsletters quoting dollar figures, CI bots quoting PR titles that contain
# "subscription"/"receipt"/"paid").
_NOISE_SENDERS = {
    "jobalerts-noreply@linkedin.com", "newsletters-noreply@linkedin.com",
    "news@alphasignal.ai", "notifications@github.com",
}

# Forward sources: CC forwards vendor receipts in from his personal accounts
# (per standing rule, goldstorm inbound forwards are real receipts). Subjects
# are human-typed — misspellings like "Recipt" included — so the wide hint
# regex qualifies these alone.
_FORWARD_SOURCES = {"konamak@icloud.com", "goldstorm2003@gmail.com"}

# Subject-side signals beyond the production regexes. French included — CC
# operates from Montreal and Québec vendors invoice in French.
_SUBJECT_HINT_RE = re.compile(
    r"\b(?:"
    r"rec(?:ei|ie|i)pt|invoice|payment|billing|bill|statement"  # recipt: human-typed forwards
    r"|subscription|renewal|renew"
    r"|charged|charge|refund|payout|purchase|order\s+confirmation"
    r"|e-?transfer|deposit|withdrawal|balance\s+due|past\s+due|overdue"
    r"|facture|reçu|paiement|relevé|virement|remboursement"
    r"|abonnement|commande|solde"
    r")\b",
    re.IGNORECASE,
)

# Document NOUNS — subject words that name a financial document rather than a
# lifestyle ("subscription"/"renewal" can headline pure marketing; "statement"
# / "facture" essentially cannot). Gates the unattended auto-apply tier.
_DOC_NOUN_RE = re.compile(
    r"\b(?:"
    r"statement|invoice|rec(?:ei|ie|i)pt|payout|e-?transfer|refund"
    r"|\bbill\b|facture|reçu|relevé|virement|remboursement"
    r")\b",
    re.IGNORECASE,
)

# Marketing noise that matches the wide net but is never a transaction record.
_NOISE_SUBJECT_RE = re.compile(
    r"\b(?:"
    r"webinar|newsletter|sale\s+ends|% ?off|discount\s+code|black\s+friday"
    r"|cyber\s+monday|free\s+trial\s+(?:tips|guide)|product\s+update"
    r"|what'?s\s+new|roadmap|changelog|community|meetup|survey"
    r")\b",
    re.IGNORECASE,
)

_OWNER_ADDRS = {"konamak@icloud.com"}
_OWNER_HINTS = ("oasisai.work",)

_REF_RE = re.compile(r"#\s?([A-Z0-9][A-Z0-9-]{3,})", re.IGNORECASE)


def _decode(value: str) -> str:
    try:
        parts = email.header.decode_header(value or "")
        return "".join(
            p.decode(enc or "utf-8", errors="replace") if isinstance(p, bytes) else p
            for p, enc in parts
        )
    except Exception:  # noqa: BLE001
        return value or ""


def _addr_of(from_header: str) -> str:
    m = re.search(r"<([^>]+)>", from_header or "")
    addr = (m.group(1) if m else (from_header or "")).strip().lower()
    return addr


def _domain_of(addr: str) -> str:
    return addr.rsplit("@", 1)[-1] if "@" in addr else ""


def _base_domain(domain: str) -> str:
    parts = domain.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else domain


def is_financial_candidate(from_addr: str, subject: str) -> tuple[bool, str]:
    """Wide-recall header-only net. Returns (is_candidate, reason)."""
    addr = _addr_of(from_addr)
    domain = _domain_of(addr)
    local = addr.split("@", 1)[0] if "@" in addr else ""
    # GCP dunning mail wraps its subject mid-word across a newline, which
    # defeated every regex in the first net — normalize before matching.
    subj = re.sub(r"\s+", " ", subject or "").strip()

    # Forwards from CC's personal accounts ARE real receipts (standing rule);
    # checked BEFORE the owner exclusion so it can't shadow them.
    if addr in _FORWARD_SOURCES and _SUBJECT_HINT_RE.search(subj):
        return True, f"forward:{local}"
    if addr in _OWNER_ADDRS or any(h in addr for h in _OWNER_HINTS):
        return False, "owner-sent"
    if addr in _NOISE_SENDERS:
        return False, "noise-sender"
    if _base_domain(domain) in _OWN_APP_DOMAINS and \
            local.split("+", 1)[0] not in _BILLING_LOCALS:
        return False, "own-app"

    vendorish = (_base_domain(domain) in _VENDOR_DOMAINS
                 or domain in _VENDOR_DOMAINS)
    billing_local = local.split("+", 1)[0] in _BILLING_LOCALS
    # Two strengths of subject evidence (adversarial review 2026-08-24, P2):
    # STRONG = the production transaction regexes, a money amount, or a
    # document noun (statement/invoice/facture/…) — words that name a
    # financial DOCUMENT. WEAK = lifestyle words ("subscription", "renewal",
    # "purchase") that vendor marketing uses freely: "Your Canva subscription
    # is about to get even better" is not a document. Weak evidence still
    # makes a scan candidate, but cmd_reconcile only auto-hands STRONG ones.
    strong_subject = bool(_TXN_PHRASE_RE.search(subj)
                          or _MONEY_AMOUNT_RE.search(subj)
                          or _DOC_NOUN_RE.search(subj))
    txn_subject = strong_subject or bool(_SUBJECT_HINT_RE.search(subj))

    if _NOISE_SUBJECT_RE.search(subj) and not _MONEY_AMOUNT_RE.search(subj):
        return False, "marketing-noise"
    if billing_local:
        return True, f"billing-local:{local}"
    if vendorish and strong_subject:
        return True, f"vendor+txn:{_base_domain(domain)}"
    if vendorish and txn_subject:
        return True, f"vendor+hint:{_base_domain(domain)}"
    if txn_subject and (_TXN_PHRASE_RE.search(subj) or _MONEY_AMOUNT_RE.search(subj)):
        return True, "txn-subject"
    return False, "no-signal"


def _parse_fetch_response(data) -> list[dict]:
    """Parse imaplib's uid-fetch response pairs into dicts."""
    out = []
    for item in data:
        if not isinstance(item, tuple) or len(item) < 2:
            continue
        meta = item[0].decode("utf-8", errors="replace") if isinstance(item[0], bytes) else str(item[0])
        hdr = email.message_from_bytes(item[1] if isinstance(item[1], bytes) else b"")
        # Quoted label names may themselves contain parens — "Clients/Acme
        # (Old)" — so the capture must treat quoted strings as opaque instead
        # of stopping at the first ')' (adversarial review 2026-08-24, P2:
        # truncating there could hide a later Receipts/* label and report a
        # covered message as a false gap).
        labels_m = re.search(r'X-GM-LABELS \(((?:[^()"]|"[^"]*")*)\)', meta)
        labels_raw = labels_m.group(1) if labels_m else ""
        labels = re.findall(r'"((?:[^"\\]|\\.)*)"|(\S+)', labels_raw)
        label_list = [a or b for a, b in labels]
        uid_m = re.search(r"UID (\d+)", meta)
        gmid_m = re.search(r"X-GM-MSGID (\d+)", meta)
        out.append({
            "uid": uid_m.group(1) if uid_m else None,
            "gm_msgid": gmid_m.group(1) if gmid_m else None,
            "labels": label_list,
            "from": _decode(hdr.get("From", "")),
            "subject": _decode(hdr.get("Subject", "")),
            "date": hdr.get("Date", ""),
            "message_id": (hdr.get("Message-ID") or "").strip(),
            "list_unsubscribe": bool(hdr.get("List-Unsubscribe")),
        })
    return out


def cmd_scan(args) -> int:
    from lib.secret_loader import load_env
    env = load_env()
    address = env.get("GMAIL_ADDRESS") or env.get("GMAIL_USER")
    password = env.get("GMAIL_APP_PASSWORD")
    if not address or not password:
        print("ERROR: GMAIL_ADDRESS / GMAIL_APP_PASSWORD missing", file=sys.stderr)
        return 1

    since_dt = datetime.strptime(args.since, "%Y-%m-%d")
    since_imap = since_dt.strftime("%d-%b-%Y")

    imap = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    imap.socket().settimeout(60)
    imap.login(address, password)
    # readonly — an audit must never mutate read-state or labels.
    imap.select('"[Gmail]/All Mail"', readonly=True)

    status, data = imap.uid("SEARCH", None, f"(SINCE {since_imap})")
    if status != "OK":
        print(f"ERROR: IMAP search failed: {status}", file=sys.stderr)
        return 1
    uids = [u.decode() for u in (data[0].split() if data and data[0] else [])]
    print(f"[scan] {len(uids)} messages in All Mail since {args.since}")

    rows: list[dict] = []
    for i in range(0, len(uids), FETCH_CHUNK):
        chunk = uids[i:i + FETCH_CHUNK]
        status, data = imap.uid(
            "FETCH", ",".join(chunk),
            "(X-GM-MSGID X-GM-LABELS BODY.PEEK[HEADER.FIELDS "
            "(FROM SUBJECT MESSAGE-ID DATE LIST-UNSUBSCRIBE)])")
        if status != "OK":
            print(f"[scan] WARNING: chunk fetch failed at {i}", file=sys.stderr)
            continue
        rows.extend(_parse_fetch_response(data))
        print(f"[scan] fetched {min(i + FETCH_CHUNK, len(uids))}/{len(uids)}",
              file=sys.stderr)
    imap.logout()

    candidates, gaps, covered = [], [], []
    for r in rows:
        ok, reason = is_financial_candidate(r["from"], r["subject"])
        if not ok:
            continue
        r["net_reason"] = reason
        candidates.append(r)
        has_receipt_label = any(l.startswith("Receipts/") for l in r["labels"])
        (covered if has_receipt_label else gaps).append(r)

    by_domain: dict[str, int] = {}
    for g in gaps:
        d = _base_domain(_domain_of(_addr_of(g["from"])))
        by_domain[d] = by_domain.get(d, 0) + 1

    report = {
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "since": args.since,
        "total_messages": len(rows),
        "candidates": len(candidates),
        "covered": len(covered),
        "gaps": len(gaps),
        "gaps_by_domain": dict(sorted(by_domain.items(), key=lambda kv: -kv[1])),
        "gap_list": [
            {k: g[k] for k in ("message_id", "gm_msgid", "date", "from",
                               "subject", "labels", "net_reason")}
            for g in gaps
        ],
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    # Full header inventory alongside the report, so a reviewer (human or
    # agent) can hunt for candidates the net MISSED — the audit's own audit.
    inv_path = out_path.with_name(out_path.stem + "_inventory.json")
    inv_path.write_text(json.dumps(
        [{k: r[k] for k in ("message_id", "date", "from", "subject", "labels")}
         for r in rows],
        indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"[scan] inventory (all {len(rows)} headers): {inv_path}")

    print(f"[scan] candidates: {len(candidates)}  covered (Receipts/*): "
          f"{len(covered)}  GAPS: {len(gaps)}")
    for d, n in list(report["gaps_by_domain"].items())[:15]:
        print(f"  gap domain: {d:30s} {n}")
    print(f"[scan] full report: {out_path}")
    return 0


def _month_of(date_header: str) -> str:
    """'YYYY-MM' from an RFC-2822 Date header, '' if unparseable."""
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(date_header or "")
        return f"{dt.year:04d}-{dt.month:02d}" if dt else ""
    except Exception:  # noqa: BLE001
        return ""


def _cluster_key(gap: dict) -> str:
    """One handoff per transaction: cluster by (domain, reference-or-subject).

    Atlas's consumer dedupes by Message-ID only, so a vendor's separate
    invoice + receipt emails for the SAME purchase would book twice. A shared
    reference number (#2671-3082) or identical normalized subject on the same
    domain IN THE SAME MONTH marks them as one transaction — hand off the
    newest only. The month component is load-bearing (adversarial review
    2026-08-24, P1): without it, a monthly SaaS receipt with no reference
    number ("Your receipt from Notion") collapsed across every month in the
    scan window, and distinct real transactions were silently dropped as
    "duplicates"."""
    domain = _base_domain(_domain_of(_addr_of(gap["from"])))
    ref = _REF_RE.search(gap["subject"] or "")
    if ref:
        return f"{domain}|ref:{ref.group(1).lower()}"
    norm = re.sub(r"\s+", " ", (gap["subject"] or "").lower())
    norm = re.sub(r"\b(?:your|receipt|invoice|from|for)\b", "", norm).strip()
    return f"{domain}|{_month_of(gap.get('date', ''))}|subj:{norm[:60]}"


def _cluster_newest(gaps: list[dict]) -> list[dict]:
    """One representative (newest by date) per transaction cluster."""
    clusters: dict[str, dict] = {}
    for g in gaps:
        key = _cluster_key(g)
        held = clusters.get(key)
        if held is None or (g.get("date") or "") > (held.get("date") or ""):
            clusters[key] = g
    return list(clusters.values())


def _gap_handoff(g: dict, tag: str) -> bool:
    """Publish one gap to Atlas via the production handoff (idempotency-keyed
    there). Shared by apply and reconcile so the payload shape can't drift."""
    from email_brain import handoff_to_atlas
    return handoff_to_atlas({
        "from": g["from"],
        "from_identity": _addr_of(g["from"]),
        "subject": g["subject"],
        "body": f"[{tag} {datetime.now(timezone.utc).date()}] "
                f"net={g.get('net_reason')}",
        "rfc_message_id": g["message_id"],
        "attachments": [],
    })


def cmd_apply(args) -> int:
    audit_path = Path(args.audit_file)
    if not audit_path.exists():
        print(f"ERROR: audit file not found: {audit_path} — run scan first",
              file=sys.stderr)
        return 1
    report = json.loads(audit_path.read_text(encoding="utf-8"))
    gaps = report.get("gap_list", [])
    if not gaps:
        print("[apply] no gaps in audit file — nothing to do")
        return 0

    clustered = _cluster_newest(gaps)
    picked = clustered[:args.limit]
    skipped_dupes = len(gaps) - len(clustered)
    print(f"[apply] {len(gaps)} gap messages → {len(clustered)} transaction "
          f"clusters ({skipped_dupes} sibling emails of the same transaction — "
          f"same reference, or same vendor+subject within one month — held "
          f"back); handing off {len(picked)} this run")

    if args.dry_run:
        for g in picked:
            print(f"  DRY-RUN would hand off: {g['from'][:40]:40s} | "
                  f"{g['subject'][:60]}")
        return 0

    handed = failed = 0
    for g in picked:
        if _gap_handoff(g, "receipts_audit backfill"):
            handed += 1
        else:
            failed += 1
            print(f"[apply] REFUSED: {g['subject'][:70]}", file=sys.stderr)
    print(f"[apply] handed off {handed}, refused {failed}. Atlas's consumer "
          f"books/labels on its next pass (or run it now with --limit).")
    return 0


# Precision tiers for unattended (cron) auto-apply. billing-local and forward
# are sender-identity proofs; vendor+txn additionally requires STRONG subject
# evidence (transaction regex, money amount, or a document noun) — vendor mail
# with only lifestyle words ("your subscription is about to get even better")
# is vendor+hint and lands in the review list instead (adversarial review
# 2026-08-24: a Canva marketing subject reached the auto tier under the old
# vendor+subject rule). A newsletter quoting "$2,000" still can't auto-apply:
# txn-subject is not an auto tier at all.
_AUTO_APPLY_PREFIXES = ("billing-local:", "vendor+txn:", "forward:")

# Bound the unattended fan-out per run; leftovers roll to the next monthly
# tick (or a manual `apply`). Never silent: the summary reports the deferral.
_RECONCILE_MAX_HANDOFFS = 40


def cmd_reconcile(args) -> int:
    """Recurring safety net: rolling scan -> tiered auto-apply -> one Telegram.

    Exit contract mirrors weekly_truth_digest (2026-08-23): 0 iff the summary
    was DELIVERED — findings are content, not reporter failure. The cron
    watchdog should page only when this reconciliation itself cannot run."""
    from datetime import timedelta
    since = (datetime.now(timezone.utc)
             - timedelta(days=args.window_days)).strftime("%Y-%m-%d")
    scan_ns = argparse.Namespace(since=since, out=args.out)
    rc = cmd_scan(scan_ns)
    if rc != 0:
        return rc

    report = json.loads(Path(args.out).read_text(encoding="utf-8"))
    gaps = report.get("gap_list", [])
    auto = [g for g in gaps
            if str(g.get("net_reason", "")).startswith(_AUTO_APPLY_PREFIXES)]
    auto_ids = {g["message_id"] for g in auto}
    # Cluster the review tier too, so an invoice+receipt pair with only weak
    # evidence shows once in CC's Telegram list, not twice.
    review_clusters: dict[str, dict] = {}
    for g in gaps:
        if g["message_id"] in auto_ids:
            continue
        review_clusters.setdefault(_cluster_key(g), g)
    review = list(review_clusters.values())

    handed = failed = deferred = 0
    if auto and not args.dry_run:
        picked = _cluster_newest(auto)
        deferred = max(0, len(picked) - _RECONCILE_MAX_HANDOFFS)
        for g in picked[:_RECONCILE_MAX_HANDOFFS]:
            if _gap_handoff(g, "receipts_reconcile"):
                handed += 1
            else:
                failed += 1
                print(f"[reconcile] hand-off REFUSED/FAILED: "
                      f"{g['subject'][:70]}", file=sys.stderr)

    lines = [f"Receipts reconciliation — last {args.window_days}d: "
             f"{report['candidates']} financial candidates, "
             f"{report['covered']} already filed, {len(gaps)} gaps."]
    if handed:
        lines.append(f"Auto-handed {handed} to Atlas (books/labels within 15 min).")
    if failed:
        # A hand-off outage must never read like "no gaps this run"
        # (adversarial review 2026-08-24, P1 — the zero-vs-failed-query class).
        lines.append(f"⚠️ {failed} hand-off(s) FAILED — the agent_events insert "
                     f"is broken; gaps remain unfiled.")
    if deferred:
        lines.append(f"{deferred} deferred to the next run (per-run cap "
                     f"{_RECONCILE_MAX_HANDOFFS}).")
    if review:
        lines.append(f"{len(review)} held for review (weak signal):")
        lines.extend(f"  • {g['from'][:40]}: {g['subject'][:60]}"
                     for g in review[:8])
    message = "\n".join(lines)
    print(message)

    if args.dry_run:
        return 0
    import notify as notify_mod
    sent = notify_mod.notify(
        message, category="system", silent=True, force=bool(gaps),
        dedup_key=f"receipts-reconcile-{datetime.now(timezone.utc):%Y-%m}",
        agent="bravo")
    delivered = sent or bool(getattr(notify_mod, "LAST_SUPPRESSED", False))
    if not delivered:
        print("reconcile: summary notification failed", file=sys.stderr)
    # Total hand-off outage = the reconciler is broken (its one job is moving
    # gaps to Atlas); partial failure is reported in the message but exits 0.
    if auto and not args.dry_run and handed == 0 and failed > 0:
        return 1
    return 0 if delivered else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_scan = sub.add_parser("scan", help="read-only mailbox reconciliation")
    p_scan.add_argument("--since", default=DEFAULT_SINCE)
    p_scan.add_argument("--out", default=str(DEFAULT_OUT))
    p_apply = sub.add_parser("apply", help="hand gap candidates to Atlas")
    p_apply.add_argument("--audit-file", default=str(DEFAULT_OUT))
    p_apply.add_argument("--limit", type=int, default=25)
    p_apply.add_argument("--dry-run", action="store_true")
    p_rec = sub.add_parser("reconcile",
                           help="rolling scan + tiered auto-apply + Telegram summary")
    p_rec.add_argument("--window-days", type=int, default=45)
    p_rec.add_argument("--out", default=str(DEFAULT_OUT))
    p_rec.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass
    if args.cmd == "scan":
        return cmd_scan(args)
    if args.cmd == "apply":
        return cmd_apply(args)
    return cmd_reconcile(args)


if __name__ == "__main__":
    raise SystemExit(main())
