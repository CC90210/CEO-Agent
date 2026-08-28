"""Financial-document detection and Gmail label selection.

WHY THIS EXISTS (2026-08-28)
----------------------------
Labelling an email for tax season and booking a ledger row are two different
questions with OPPOSITE error costs, and the pipeline used to answer both with
one decision:

  * booking a ledger row   -> a false positive puts a fake expense in the
    operator's books. Bias: PRECISION. Owned by `_has_transaction_evidence()`.
  * applying a Gmail label -> a false negative loses a deductible expense at
    tax time; a false positive costs ~5 seconds of dragging. Bias: RECALL.
    Owned by THIS module.

Welding them together meant the (correctly) conservative booking rubric
silently suppressed labelling. A real Google Cloud invoice
("Your invoice is available for 018D76-BA5673-D713C1" - the amount lives in the
attached PDF, not the body) was classified `low_priority` at 0.95 confidence
and archived silently, while a Telegram message said "Route: financial".

The operator's own mailbox proves which bias is right: he keeps a
"Statements & Notices" label - a bucket for exactly the mail the booking rubric
throws away.

This module is PURE: no I/O, no model calls, no IMAP. That makes the recall
gate deterministic and unit-testable, and keeps model variance out of whether a
receipt gets filed at all.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

# The three buckets that exist in the live mailbox under `Receipts/<year>/`.
SUBTYPE_EXPENSE = "expense"
SUBTYPE_INCOME = "income"
SUBTYPE_STATEMENT = "statement"

LABEL_LEAF = {
    SUBTYPE_EXPENSE: "Business Expenses",
    SUBTYPE_INCOME: "Income & Invoices",
    SUBTYPE_STATEMENT: "Statements & Notices",
}

LABEL_ROOT = "Receipts"


# --- Signals ----------------------------------------------------------------
#
# Anchored on document nouns and transaction verbs. Deliberately broad: this
# gate decides FILING, not booking.

# NOTE ON TIGHTNESS (2026-08-28, after the first backfill dry run):
# these were originally bare topic words - `tax`, `payment`, `charge`, `bill`.
# That is too loose for a mailbox that also receives industry news: a LinkedIn
# digest headlined "The $175 Billion Question: What the Supreme Court..." was
# proposed as a Business Expense, because its body discusses tax and `bill`
# matches inside "Billion". Recall-biased does not mean signal-free - every
# alternative below names a DOCUMENT or a COMPLETED TRANSACTION, not a topic.
_DOC_RE = re.compile(
    r"("
    r"\binvoice[sd]?\b|\breceipt\b|"
    r"\bpayment\s+(?:of|received|confirmation|successful|failed|due)\b|"
    r"\byour\s+payment\b|\bpayout\b|\bremittance\b|\brefund(?:ed)?\b|"
    r"\bcredit\s+note\b|"
    r"\b(?:account|monthly|annual|quarterly|bank|card|billing)\s+statement\b|"
    r"\bstatement\s+(?:is\s+)?(?:available|ready|attached)\b|"
    r"\byou\s+(?:were|have\s+been)\s+charged\b|\bwe\s+charged\b|"
    r"\bcharge\s+of\s+[$€£]|"
    r"\bsubscription\s+(?:renew\w*|charge\w*)\b|\brenewal\s+confirm\w*\b|"
    r"\border\s+confirmation\b|\bpurchase\s+confirmation\b|"
    r"\b(?:amount|total|balance)\s+(?:due|paid|charged)\b|"
    r"\btax\s+(?:invoice|receipt|slip|document|statement)\b|"
    r"\bnotice\s+of\s+assessment\b|\bt4a\b|\bt5\b|\bt2125\b|"
    r"\b(?:gst|hst|qst)\s+(?:return|remittance|filing)\b|"
    r"\bremittance\s+advice\b"
    r")",
    re.IGNORECASE,
)

# Senders whose mail is never a financial document, however much money it
# discusses. Social and publishing platforms send digests ABOUT money.
_NEVER_FILE_SENDER_RE = re.compile(
    r"@(?:[\w.-]*\.)?("
    r"linkedin\.com|medium\.com|substack\.com|twitter\.com|x\.com|"
    r"facebookmail\.com|meta\.com|reddit\.com|quora\.com|"
    r"news\.|newsletter\.|alphasignal\.|indeed\.com|glassdoor\.com|"
    # CI / code-review bots. Their mail quotes diffs that routinely contain
    # billing code, and the 2026 backfill dry run proposed filing three
    # coderabbitai PR comments and a vercel[bot] comment as Business Expenses.
    r"github\.com|githubusercontent\.com|gitlab\.com"
    r")",
    re.IGNORECASE,
)

# Bot display names / local-parts that are never a counterparty.
_BOT_SENDER_RE = re.compile(
    r"(coderabbit|\[bot\]|dependabot|renovate|noreply\+bot)", re.IGNORECASE)

# Machine senders - the addresses vendors actually send receipts from. Used to
# decide how much signal a message needs: an automated sender gets the benefit
# of the doubt, a human has to name a document explicitly.
_AUTOMATED_SENDER_RE = re.compile(
    r"("
    r"no-?reply|do-?not-?reply|notifications?@|billing@|invoice|receipts?@|"
    r"payments?[-.@]|accounts?@|statements?@|support@|team@|hello@|"
    r"@(?:stripe|paypal|square|intuit|quickbooks|xero|wave|freshbooks)\."
    r")",
    re.IGNORECASE,
)

# Money has NOT moved yet: reminders, dunning nudges, and card-on-file prompts.
# The vendor is asking for action, not confirming a transaction, so there is no
# document here for CC to keep. Checked as a veto, before the doc signals.
_NOT_YET_RE = re.compile(
    r"("
    r"\bwill\s+renew\b|\brenews?\s+(?:on|in)\b|\brenewal\s+reminder\b|"
    r"\badd\s+(?:a\s+)?payment\s+(?:details|method)\b|"
    r"\bupdate\s+your\s+payment\b|\bpayment\s+method\s+(?:is\s+)?expir\w*|"
    r"\bcard\s+(?:is\s+)?expir\w*|"
    r"\bupcoming\s+invoice\b|\binvoice\s+is\s+coming\b"
    r")",
    re.IGNORECASE,
)

# A vendor CONFIRMING that CC paid them. This is money OUT, and it must be
# tested BEFORE the income phrases: "We've received your payment" contains
# "received your payment", which reads as income to a naive direction rule and
# filed a Google Workspace charge under Income & Invoices in the dry run.
_EXPENSE_DIRECTION_RE = re.compile(
    r"("
    r"we(?:'ve|’ve| have)?\s+received\s+your\s+payment|"
    r"received\s+your\s+payment|"
    r"thank\s+you\s+for\s+your\s+(?:payment|purchase|order|business)|"
    r"your\s+payment\s+to\b|\bpayment\s+to\s+[A-Z]|"
    r"your\s+(?:receipt|invoice)\s+from\b|"
    r"\binvoice\s*\S*\s+from\s+[A-Z]|"
    # "Payment received for Supabase Pte. Ltd" - the VENDOR received it, so
    # this is money out. Without this the dry run filed it as income.
    r"payment\s+received\s+for\s+\w|"
    r"\bpurchase\s+confirmed\b"
    r")",
    re.IGNORECASE,
)

# CC's BUSINESS identities - the addresses that ISSUE invoices to clients. An
# invoice sent by one of these is income, never an expense: the dry run
# proposed filing his own outbound "Software and AI Automation Invoice" as a
# Business Expense.
#
# DELIBERATELY EXCLUDES goldstorm2003@gmail.com and konamak@icloud.com. CC signs
# up to vendors with those and FORWARDS the receipts here to be categorised, so
# mail bearing them is inbound vendor spend, not something he issued - the
# Google Cloud invoice that started this whole repair arrived from GOLD STORM.
# Treating them as issuing identities would invert the direction on every
# forwarded receipt CC files.
_OWN_ISSUER_RE = re.compile(
    r"(@oasisai\.work|oasisaisolutions@gmail\.com)",
    re.IGNORECASE,
)

# A vendor announcing pricing is not a document, no matter how much money it
# names. This VETOES the doc signal unless a strong document token is present.
_MARKETING_RE = re.compile(
    r"\b("
    r"new\s+pricing|price\s+(?:drop|cut|increase)|cutting\s+prices|"
    r"upgrade\s+(?:now|today)|save\s+\d+%|"
    r"limited[-\s]time|black\s+friday|special\s+offer|promo(?:tion)?\s+code|"
    r"introducing|announcing|"
    r"compare\s+plans|plan\s+comparison|webinar|newsletter"
    r")\b",
    re.IGNORECASE,
)

# Tokens strong enough to survive the marketing veto: these name a SPECIFIC
# document that exists for this account.
_STRONG_DOC_RE = re.compile(
    r"("
    r"\byour\s+(?:invoice|receipt|statement|bill)\b|"
    # An identifier must actually FOLLOW, otherwise the prose "chasing the
    # invoice numbers on these" reads as a document and files a colleague's
    # ops email as a receipt.
    # A DIGIT must follow, not any alphanumeric: with IGNORECASE, [A-Z0-9]
    # matched the trailing "s" of "invoice numbers" and turned a colleague's
    # prose into a document reference.
    r"\binvoice\s*(?:#\s*|no\.?\s+|number\s*[:#]?\s*)\d|"
    r"\binvoice\s+(?:is\s+)?(?:available|ready|attached)\b|"
    # A real invoice identifier: uppercase/digits, containing at least one
    # digit. `(?-i:...)` turns OFF this pattern's IGNORECASE locally - with it
    # on, [A-Z0-9] also matches lowercase and "invoice numbers" parsed as
    # "invoice" + the identifier "numbe".
    r"\binvoice\s+(?-i:(?=[A-Z0-9-]*\d)[A-Z0-9][A-Z0-9-]{3,})\b|"
    r"\breceipt\s+(?:for|from|#)|"
    r"\bpayment\s+(?:received|confirmation|successful|failed)\b|"
    r"\bpayout\b|\bremittance\b|"
    r"\bnotice\s+of\s+assessment\b|\bt4a\b|\bt2125\b"
    r")",
    re.IGNORECASE,
)

# Money actually named in the text. Not required for filing (the amount is
# routinely inside the PDF) but a strong positive when present.
_MONEY_RE = re.compile(
    r"(?:[$€£]\s?\d[\d,]*(?:\.\d{2})?)|"
    r"(?:\b\d[\d,]*\.\d{2}\s?(?:CAD|USD|EUR|GBP)\b)",
    re.IGNORECASE,
)

# Attachment filenames that are self-evidently financial documents.
_DOC_FILENAME_RE = re.compile(
    r"(invoice|receipt|statement|bill|remittance|payout|facture|"
    r"t4a|t5\b|assessment)",
    re.IGNORECASE,
)

# --- Direction --------------------------------------------------------------
#
# A prior incident mis-booked 8 rows as INCOME with a direction-blind
# classifier. Direction is decided by explicit phrases, never by the mere
# presence of the word "invoice" (which is direction-ambiguous on its own).

_INCOME_RE = re.compile(
    r"("
    r"\bpayout\b|\bpaid\s+out\b|"
    r"you(?:’ve|'ve| have)\s+been\s+paid|"
    r"payment\s+received|received\s+a\s+payment|"
    r"you\s+received\s+(?:a\s+)?(?:payment|transfer|deposit)|"
    r"\bfunds?\s+(?:deposited|received|transferred\s+to\s+you)\b|"
    r"\bdeposit\s+(?:of|to)\b|"
    r"\bremittance\s+advice\b|"
    r"(?:customer|client)\s+(?:paid|payment)|"
    r"invoice\s+(?:has\s+been\s+)?paid|"
    r"\bnew\s+(?:sale|order)\b|"
    r"your\s+payout|payout\s+(?:is|was|of)"
    r")",
    re.IGNORECASE,
)

# Statement/notice language: a document exists on a portal, or an authority is
# notifying. Deliberately does NOT include "invoice" - a vendor invoice is an
# expense even when phrased as "your invoice is available".
_STATEMENT_RE = re.compile(
    r"("
    r"\b(?:account|monthly|annual|quarterly|bank|card)\s+statement\b|"
    r"\bstatement\s+(?:is\s+)?(?:available|ready|attached|for)\b|"
    r"\byour\s+statement\b|"
    r"\bnotice\s+of\s+assessment\b|"
    r"\bcra\b|\brevenu\s+qu[eé]bec\b|\bt4a\b|\bt5\b|"
    r"\btax\s+(?:slip|document|receipt)\b|"
    r"\bgst\b|\bhst\b|\bqst\b|"
    r"\blegal\s+notice\b|\bcompliance\s+notice\b"
    r")",
    re.IGNORECASE,
)

# Unambiguous expense phrasing - a vendor charging CC.
_EXPENSE_RE = re.compile(
    r"("
    r"\byour\s+invoice\b|\binvoice\s+is\s+(?:available|ready|attached)\b|"
    r"\breceipt\s+(?:for|from)\b|\byour\s+receipt\b|"
    r"\bsubscription\s+(?:renew\w*|charge\w*)\b|\brenewal\s+confirm\w*\b|"
    r"\byou\s+(?:were|have\s+been)\s+charged\b|\bwe\s+charged\b|"
    r"\bpayment\s+(?:to|for)\b|"
    r"\bthanks?\s+for\s+your\s+(?:payment|purchase|order)\b|"
    r"\border\s+confirmation\b|\bpurchase\s+confirmation\b"
    r")",
    re.IGNORECASE,
)


def _text_of(subject: Optional[str], body: Optional[str]) -> str:
    return ((subject or "") + "\n" + (body or ""))


def _attachment_names(attachments: Optional[Iterable[Any]]) -> list:
    """Accept the several shapes callers use: str, {"filename": ...}, {"name": ...}."""
    names = []
    for att in attachments or []:
        if isinstance(att, str):
            names.append(att)
        elif isinstance(att, dict):
            n = att.get("filename") or att.get("name") or att.get("file_name")
            if n:
                names.append(str(n))
    return names


def has_document_attachment(attachments: Optional[Iterable[Any]]) -> bool:
    """A PDF named like an invoice/receipt is a financial document on its own.

    This is the signal the body-text rubric cannot see: the Google Cloud
    invoice that started this carried its amount only inside `5655806289.pdf`.
    """
    for name in _attachment_names(attachments):
        if _DOC_FILENAME_RE.search(name):
            return True
    return False


def is_financial_document(
    subject: Optional[str] = None,
    body: Optional[str] = None,
    from_identity: Optional[str] = None,
    attachments: Optional[Iterable[Any]] = None,
    prefilter_route: Optional[str] = None,
) -> bool:
    """HIGH-RECALL gate: should this email be FILED under Receipts/<year>/?

    Says nothing about whether it may be booked to the ledger - that stays with
    `inbound_classifier._has_transaction_evidence()`.
    """
    text = _text_of(subject, body)

    # Hard veto by sender: a LinkedIn or Substack digest is never a receipt,
    # and these platforms publish about money constantly. Checked first so no
    # amount of document vocabulary in the body can override it.
    if from_identity and (_NEVER_FILE_SENDER_RE.search(from_identity)
                          or _BOT_SENDER_RE.search(from_identity)):
        return False

    # Nothing has been transacted yet - a renewal reminder or a "add your card"
    # nudge is not a document to keep. Vetoed before the doc signals, since
    # those messages are full of billing vocabulary by design.
    if _NOT_YET_RE.search(text) and not _MONEY_RE.search(text):
        return False

    strong = bool(_STRONG_DOC_RE.search(text))
    doc = bool(_DOC_RE.search(text))
    marketing = bool(_MARKETING_RE.search(text))
    attach = has_document_attachment(attachments)

    # The platform prefilter already resolves known billing senders correctly -
    # it got the Google Cloud invoice right when everything downstream did not.
    # Trust it, but still let a pure marketing blast from a billing sender out.
    if (prefilter_route or "").strip().lower() == "financial":
        if marketing and not (strong or attach):
            return False
        return True

    if strong or attach:
        return True

    # A PERSON writing to CC needs a strong signal, not merely billing
    # vocabulary. Vendors send receipts from automated addresses
    # (noreply@, billing@, invoice+...@, notifications@); colleagues send prose
    # that happens to discuss money. The 2026 dry run proposed filing four of
    # Jordan's SunBiz ops emails ("Underwriting SOP", "Fwd: Leads to get
    # numbers") and a personal apartment application as Business Expenses,
    # all on the loose signal alone.
    if from_identity and not _AUTOMATED_SENDER_RE.search(from_identity):
        return False

    if doc and not marketing:
        return True
    return False


def financial_subtype(
    subject: Optional[str] = None,
    body: Optional[str] = None,
    from_identity: Optional[str] = None,
    attachments: Optional[Iterable[Any]] = None,
) -> str:
    """Which of the three buckets. Deterministic; direction is never guessed
    from the bare word "invoice"."""
    text = _text_of(subject, body)

    # Direction is resolved OUT-first, because the phrases that mean "you paid
    # us" and "we paid you" share most of their words. "We've received your
    # payment" and "Payment received for Supabase Pte. Ltd" both contain
    # "received ... payment" and both mean money LEFT CC's account; the dry run
    # filed two Google Workspace charges as Income before this branch existed.
    if _EXPENSE_DIRECTION_RE.search(text):
        return SUBTYPE_EXPENSE

    # Income: an explicit "you have been paid" outranks generic doc words.
    if _INCOME_RE.search(text):
        return SUBTYPE_INCOME
    # Then an unambiguous vendor charge - this must beat the statement rule so
    # that "Your invoice is available" files as an expense, not a notice.
    if _EXPENSE_RE.search(text):
        return SUBTYPE_EXPENSE

    # An invoice issued BY one of CC's business addresses is money coming in.
    #
    # Checked AFTER the vendor-charge phrases on purpose: CC also FORWARDS
    # vendor receipts from his own oasisai.work address, and an earlier
    # ordering flipped "Your invoice is available" (a Google Cloud charge he
    # forwarded to himself) into Income. Being the sender is the weakest
    # possible direction signal - it loses to anything the document says.
    if from_identity and _OWN_ISSUER_RE.search(from_identity) \
            and re.search(r"\binvoice\b", text, re.IGNORECASE):
        return SUBTYPE_INCOME
    if _STATEMENT_RE.search(text):
        return SUBTYPE_STATEMENT
    # A financial document that named no direction is still a vendor document
    # far more often than not; expense is the safe default for filing (it is a
    # label, not a ledger entry).
    return SUBTYPE_EXPENSE


def _year_of(email_date: Any) -> int:
    """The year the email is FROM, never `today`.

    Backfilling 2026 mail in 2027 must not file it under Receipts/2027, and a
    receipt that arrives on 1 January belongs to the year it was sent.
    """
    if email_date is None:
        return datetime.now(timezone.utc).year
    if isinstance(email_date, datetime):
        return email_date.year
    if isinstance(email_date, int):
        return email_date
    s = str(email_date).strip()
    if not s:
        return datetime.now(timezone.utc).year
    # RFC 2822 Date header is the common case.
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(s)
        if dt is not None:
            return dt.year
    except Exception:  # noqa: BLE001 - fall through to the ISO/regex attempts
        pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).year
    except ValueError:
        pass
    m = re.search(r"\b(20\d{2})\b", s)
    if m:
        return int(m.group(1))
    return datetime.now(timezone.utc).year


def label_for(subtype: str, email_date: Any = None) -> str:
    """`Receipts/<year>/<leaf>` - the exact strings that exist in the mailbox."""
    leaf = LABEL_LEAF.get(subtype)
    if leaf is None:
        raise ValueError(f"unknown financial subtype: {subtype!r}")
    return f"{LABEL_ROOT}/{_year_of(email_date)}/{leaf}"


def assess(email: dict, prefilter_route: Optional[str] = None) -> dict:
    """One call for the sweep: {is_financial, subtype, label}.

    `email` uses the shape email_brain/email_engine already pass around:
    {from|from_identity, subject, body, attachments, date}.
    """
    subject = email.get("subject")
    body = email.get("body")
    sender = email.get("from") or email.get("from_identity")
    attachments = email.get("attachments")
    date = email.get("date") or email.get("email_date")

    if not is_financial_document(subject, body, sender, attachments,
                                 prefilter_route=prefilter_route):
        return {"is_financial": False, "subtype": None, "label": None}

    subtype = financial_subtype(subject, body, sender, attachments)
    return {
        "is_financial": True,
        "subtype": subtype,
        "label": label_for(subtype, date),
        "has_amount_in_text": bool(_MONEY_RE.search(_text_of(subject, body))),
    }
