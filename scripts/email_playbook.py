"""email_playbook.py — the OASIS inbound-email rulebook.

Everything the retired n8n "OASIS Inbound Qualifier" knew about handling CC's
inbox, in one auditable place: who is safe to reply to, who must NEVER get an
automated reply, the exact copy constraints for a reply in CC's voice, and how
alerts are tagged.

WHY THIS EXISTS
---------------
The n8n workflow carried ~35k characters of hard-won operating rules spread
across four agent prompts. The first native port kept the 4-way category
routing and threw the rules away, which quietly produced three classes of bug:

  1. It could reply to things that must never receive an automated reply
     (a VC intro, a furious client, an outage, another OASIS agent).
  2. It could delete things that must never be dropped (no-reply vendor
     receipts — i.e. CC's deductible expenses).
  3. It generated replies with no booking link, no company signature, and no
     prohibition on quoting price or committing timelines.

SENDER TRIAGE runs BEFORE any model call. It is deterministic on purpose: the
"never auto-reply" set must not depend on an LLM's mood.
"""

from __future__ import annotations

import re
from typing import Optional

# ── Identity ─────────────────────────────────────────────────────────────────

OWNER_EMAILS = {"konamak@icloud.com", "conaugh@oasisai.work", "cc@oasisai.work"}
OWNER_DOMAINS = {"oasisai.work"}

BOOKING_LINK = "https://calendar.app.google/tpfvJYBGircnGu8G8"
SIGNATURE = "Conaugh McKenna\nOASIS AI Solutions\noasisai.work"

# ── Sender triage ────────────────────────────────────────────────────────────

# Local-part prefixes that mean "a machine sent this". NOTE: these are a
# SIGNAL, never a delete. The previous implementation dropped these before
# classification, which silently destroyed every Stripe / Google Cloud /
# Vercel / Apple receipt — CC's business expenses — before Atlas ever saw them.
AUTOMATED_PREFIXES = (
    "noreply@", "no-reply@", "donotreply@", "do-not-reply@", "notifications@",
    "notification@", "alerts@", "alert@", "mailer@", "automated@", "mailbot@",
    "system@", "postmaster@", "mailer-daemon@", "bounce@", "bounces@",
)

# Cold-outreach / mass-mail platforms. Mail from these is marketing at CC, not
# a real human conversation.
MASS_MAIL_DOMAINS = (
    "mailchimp.com", "hubspot.com", "salesloft.com", "apollo.io", "outreach.io",
    "lemlist.com", "instantly.ai", "smartlead.ai", "gmass.co", "sendgrid.net",
    "mailgun.org", "constantcontact.com", "klaviyo.com",
)

# Sibling agents in the fleet. Replying to these creates an agent-to-agent
# reply loop, which the n8n workflow explicitly prevented.
SIBLING_LOCALPARTS = (
    "agent", "bot", "bravo", "atlas", "maven", "aura", "hermes", "sentinel",
    "apex", "autoreply", "auto-reply",
)

SECURITY_SIGNALS = (
    "leakscanner", "dependabot", "snyk", "gitguardian", "github-security",
    "virustotal", "abuse@", "security@", "security-noreply",
)
SECURITY_SUBJECTS = (
    "verify your email", "confirm your subscription", "security alert",
    "suspicious sign-in", "new sign-in", "password reset", "secret detected",
)

# ── Never-auto-reply guards (content-driven) ─────────────────────────────────

# A production outage / revenue-loss email is the HIGHEST-stakes mail CC gets.
# It must never receive a generated reply and must never be silently archived.
OUTAGE_SIGNALS = (
    "outage", "is down", "site is down", "website is down", "not working at all",
    "completely broken", "can't take payments", "cannot take payments",
    "clients can't", "customers can't", "losing money", "urgent issue",
    "everything is broken", "nothing works", "down for", "500 error",
)

FRUSTRATION_SIGNALS = (
    "this is unacceptable", "i'm done", "im done", "fed up", "ridiculous",
    "considering canceling", "considering cancelling", "cancel my", "refund",
    "third time i", "still waiting", "no response", "unprofessional",
    "very disappointed", "extremely disappointed",
)

# Money inside any thread — never auto-answer a commercial term.
MONEY_SIGNALS = (
    "invoice", "refund", "price", "pricing", "cost", "quote", "discount",
    "monthly", "retainer", "contract", "payment", "billing", "how much",
    "charge", "fee",
)

# VC / press / acquirer — CC replies to these personally, always.
STRATEGIC_DOMAINS = (
    "a16z.com", "sequoiacap.com", "ycombinator.com", "techcrunch.com",
    "bloomberg.com", "forbes.com", "greylock.com", "accel.com", "index.vc",
)
STRATEGIC_SIGNALS = (
    "acquire", "acquisition", "investor", "investment", "introduce you to",
    "podcast guest", "feature you in", "interview you", "term sheet",
    "due diligence",
)

OPT_OUT_SIGNALS = (
    "unsubscribe", "stop emailing", "take me off", "remove me", "opt out",
    "opt-out", "do not contact", "don't contact",
)

# ── Alert taxonomy (greppable, matches the n8n vocabulary) ───────────────────

ALERT_TAGS = {
    "outage": "[OUTAGE]",
    "hot_lead": "[HOT-LEAD]",
    "strategic": "[BD-STRATEGIC]",
    "frustrated": "[FRUSTRATED]",
    "opt_out": "[BD-OPT-OUT]",
    "security": "[SECURITY]",
    "ambiguous": "[BD-AMBIGUOUS]",
    "needs_review": "[NEEDS-REVIEW]",
    "inbound": "[BD-INBOUND]",
    "financial": "[FINANCIAL]",
    "legal": "[LEGAL]",
}

# Alerts that must break through notify.py's silent categories.
LOUD_ALERTS = {"outage", "hot_lead", "strategic", "frustrated", "security", "legal"}


def _lc(s: Optional[str]) -> str:
    return (s or "").lower()


def _local_and_domain(addr: str) -> tuple[str, str]:
    a = _lc(addr).strip()
    if "<" in a and ">" in a:
        a = a[a.rfind("<") + 1: a.rfind(">")]
    local, _, domain = a.partition("@")
    return local, domain


def classify_sender(from_addr: str, subject: str = "", body: str = "") -> dict:
    """Deterministic sender triage — runs BEFORE any model call.

    Returns {kind, is_automated, may_reply, reason} where kind is one of:
      owner     — CC himself (often forwarding something in to be processed)
      sibling   — another OASIS agent; never reply (loop risk)
      security  — scanner/verification mail; alert, never reply
      automated — machine-sent (no-reply, mass-mail platform); never reply,
                  but ALWAYS still classified (vendor receipts live here)
      human     — a real person; eligible for the reply brains
    """
    local, domain = _local_and_domain(from_addr)
    full = f"{local}@{domain}"
    subj = _lc(subject)
    text = _lc(body)[:4000]

    if full in OWNER_EMAILS or (domain in OWNER_DOMAINS and local in ("cc", "conaugh")):
        return {"kind": "owner", "is_automated": False, "may_reply": False,
                "reason": "from CC himself — treat as an instruction/forward, never reply"}

    if domain in OWNER_DOMAINS and any(s in local for s in SIBLING_LOCALPARTS):
        return {"kind": "sibling", "is_automated": True, "may_reply": False,
                "reason": "sibling OASIS agent — replying would create an agent loop"}

    if (any(s in full for s in SECURITY_SIGNALS)
            or any(s in subj for s in SECURITY_SUBJECTS)):
        return {"kind": "security", "is_automated": True, "may_reply": False,
                "reason": "security/verification mail — alert CC, never reply"}

    automated = (
        any(full.startswith(p.rstrip("@") + "@") or p in full for p in AUTOMATED_PREFIXES)
        or any(domain.endswith(d) for d in MASS_MAIL_DOMAINS)
        or "list-unsubscribe" in text
    )
    if automated:
        return {"kind": "automated", "is_automated": True, "may_reply": False,
                "reason": "machine-sent — classify it (vendor receipts live here) but never reply"}

    return {"kind": "human", "is_automated": False, "may_reply": True,
            "reason": "real human sender"}


def detect_red_flags(subject: str, body: str, from_addr: str = "") -> list[str]:
    """Content signals that BLOCK an automated reply regardless of category.

    Each of these was an explicit hard rule in the n8n prompts, and each maps to
    a real failure: auto-replying to an outage, arguing with a furious client,
    quoting money, or sending a machine reply to an investor.
    """
    hay = f"{_lc(subject)} \n {_lc(body)[:6000]}"
    _, domain = _local_and_domain(from_addr)
    flags: list[str] = []

    if any(s in hay for s in OUTAGE_SIGNALS):
        flags.append("outage")
    if any(s in hay for s in FRUSTRATION_SIGNALS):
        flags.append("frustrated")
    if any(s in hay for s in OPT_OUT_SIGNALS):
        flags.append("opt_out")
    if any(s in hay for s in MONEY_SIGNALS):
        flags.append("money")
    if any(domain.endswith(d) for d in STRATEGIC_DOMAINS) or \
       any(s in hay for s in STRATEGIC_SIGNALS):
        flags.append("strategic")
    # ALL-CAPS shouting is a frustration signal the keyword list can miss.
    letters = [c for c in (subject or "") if c.isalpha()]
    if len(letters) >= 8 and sum(1 for c in letters if c.isupper()) / len(letters) > 0.7:
        if "frustrated" not in flags:
            flags.append("frustrated")
    return flags


def is_forwarded(subject: str, body: str) -> bool:
    s = _lc(subject)
    b = _lc(body)[:2000]
    return (s.startswith("fwd:") or s.startswith("fw:")
            or "begin forwarded message" in b
            or "---------- forwarded message" in b)


# Sentinel used when a message is clearly a forward but the original sender is
# unrecoverable. Routing on this instead of `None`/`?` keeps a headerless
# forward in plain human review and OUT of any automated/financial path.
UNKNOWN_FORWARD_SENDER = "unknown_forward@system"


def extract_forwarded_sender(body: str, header_from: str = "") -> Optional[str]:
    """Pull the ORIGINAL sender out of a forwarded block so CC forwarding a
    vendor invoice in gets classified on the vendor, not on CC.

    Hardened 2026-07-24: the quoted 'From:' line is tried first; if the body is
    missing/malformed, fall back to the envelope From header; if BOTH fail,
    return the UNKNOWN_FORWARD_SENDER sentinel (never None/'?') so downstream
    code has a valid, non-routable address to work with instead of a '?' that
    leaked into alerts."""
    # 1. Quoted "From:" inside the forwarded block.
    if body:
        m = re.search(r"(?im)^\s*from:\s*(.+)$", body[:4000])
        if m:
            addr = re.search(r"[\w.+-]+@[\w.-]+\.\w+", m.group(1))
            if addr:
                return addr.group(0).lower()
    # 2. Fall back to the envelope From header.
    if header_from:
        addr = re.search(r"[\w.+-]+@[\w.-]+\.\w+", header_from)
        if addr:
            return addr.group(0).lower()
    # 3. Clearly a forward but unrecoverable — never emit None/'?'.
    return UNKNOWN_FORWARD_SENDER


def alert(tag_key: str, sender: str, subject: str, extra: str = "") -> tuple[str, bool]:
    """Build a greppable alert line + whether it must be loud.

    n8n emitted 8 distinct tagged prefixes so CC could grep his own Telegram
    history; the first native port flattened them all to one bland string and
    sent hot leads SILENTLY (notify.py mutes the 'email' category).
    """
    tag = ALERT_TAGS.get(tag_key, "[INBOUND]")
    line = f"{tag} {sender}: {subject}".strip()
    if extra:
        line += f"\n{extra}"
    return line, tag_key in LOUD_ALERTS


# ── Copy constraints for generated replies ───────────────────────────────────

BANNED_OPENERS = (
    "thank you for reaching out", "thanks for reaching out",
    "i appreciate you taking the time", "thanks for the email",
    "i hope this finds you well", "i hope this email finds you well",
    "i trust this email finds you well", "greetings",
)
BANNED_CLOSERS = (
    "best regards", "sincerely", "kind regards", "warmest regards", "cheers",
    "looking forward to your response",
)
BANNED_FILLER = (
    "going forward", "at your earliest convenience", "per our conversation",
    "as discussed", "reaching out to", "touch base", "circle back", "synergy",
    "leverage", "unlock", "empower", "please feel free to", "kindly", "as per",
    "i appreciate your patience",
)

HARD_RULES = """HARD RULES — these override everything else:
1. NEVER quote a price, rate, or range. Deflect to a call.
2. NEVER commit to a timeline beyond "15 min on Zoom this week".
3. NEVER claim specific work OASIS did for this person. If you don't know the
   setup, hedge: "best to walk through the specifics on the call".
4. Include the booking link AT MOST ONCE, and only when proposing a call.
5. No P.S. lines. No emoji in the sign-off. No bullet lists where prose works.
6. Match their length — a two-line email gets a two-line reply.
7. 3-6 sentences. Anything over 80 words needs a reason to exist."""


def voice_rules() -> str:
    """The full copy ruleset for a reply drafted as CC."""
    return (
        "VOICE — write as Conaugh McKenna, founder of OASIS AI Solutions.\n"
        "Open with a SPECIFIC reference to what they actually wrote (if they said "
        "HVAC, the word HVAC appears in sentence one — specificity is the strongest "
        "anti-bot signal). Real contractions. Vary sentence length. Hedge honestly "
        "(\"I think\", \"probably\", \"depending on what you've already got set up\").\n\n"
        "NEVER open with: " + "; ".join(BANNED_OPENERS) + ".\n"
        "NEVER close with: " + "; ".join(BANNED_CLOSERS) + ".\n"
        "NEVER use: " + "; ".join(BANNED_FILLER) + ".\n"
        "Never start two consecutive sentences with the same word.\n\n"
        + HARD_RULES + "\n\n"
        f"Sign off exactly:\n{SIGNATURE}\n\n"
        f"Booking link (the ONLY booking mechanism — never propose times yourself):\n{BOOKING_LINK}"
    )


def lint_draft(body: str) -> list[str]:
    """Cheap deterministic check that a generated reply obeys the copy rules.
    Returns a list of violations (empty == clean)."""
    b = _lc(body)
    out: list[str] = []
    for phrase in BANNED_OPENERS + BANNED_CLOSERS + BANNED_FILLER:
        if phrase in b:
            out.append(f"banned phrase: {phrase}")
    if b.count(BOOKING_LINK.lower()) > 1:
        out.append("booking link appears more than once")
    if re.search(r"(?im)^\s*p\.?s\.?[:\s]", body or ""):
        out.append("contains a P.S. line")
    if re.search(r"\$\s?\d", body or ""):
        out.append("quotes a dollar figure")
    words = len((body or "").split())
    if words > 160:
        out.append(f"too long ({words} words)")
    return out
