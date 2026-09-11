"""
tenant_brand.py — the ONE place that answers "which company is this send for?"

WHY THIS EXISTS (2026-09-09, after a client-visible incident)
-------------------------------------------------------------
Two legally distinct companies share one Command Center and one send path:

    OASIS AI Solutions   Montreal, QC, Canada   (CC + Adon)
    SunBiz Funding LLC   Hallandale, FL, USA    (a paying client)

Before this module, `brand` and `tenant_id` were two independent, unvalidated
arguments to the same function. Nothing checked that they agreed, and every
layer defaulted when the brand was absent — in OPPOSITE directions:

    send_gateway.DEFAULT_BRAND       = "oasis"    (Python)
    email_template._brand() fallback = "oasis"    (Python)
    lib/email/brands.ts resolveBrandKey()         -> "sunbiz"  (TypeScript)
    lib/config/email-signature.ts:115             -> "sunbiz"  (TypeScript)

So a brand string that went missing anywhere landed on OASIS on one side of the
stack and on SunBiz on the other. A SunBiz merchant could receive mail signed
"OASIS AI Solutions, Montreal", and an OASIS prospect could receive mail signed
"SunBiz Funding LLC" telling them they had submitted a funding inquiry — which
is false, and is the client's legal identity, not ours.

The ledger proves both directions happened (Turso, 2026-09-09):
    tenant oasis-ai-cc  with brand 'sunbiz' : 1 send  (2026-07-10)
    tenant submissions  with brand 'oasis'  : 1 send  (2026-08-01)
    ...and 2,569 of 4,654 email sends recorded NO brand at all, so what identity
    actually went out on them is not recoverable from the audit trail.

WHY A STATIC MAP AND NOT A DB LOOKUP
------------------------------------
A database error must never get a vote on which company a message claims to be
from. A lookup would have to answer *something* when the query fails, and every
available answer is a legal misattribution. A static map cannot fail, cannot
time out, and is diffable in review — changing who a tenant sends as becomes a
code change with an author, not a row someone edited.

It also fails closed for free: a tenant that is not listed resolves to None, and
callers refuse to send commercial mail rather than guessing. Verified against
the live tenants table on 2026-09-09: of 49 tenants, exactly TWO have ever sent
email (submissions: 4,595, oasis-ai-cc: 59). The other 47 are self-signup
accounts — including real third parties (Yoga Tantric LLC, Promptimagica,
Sarif' Ai) — that have sent zero. Refusing on unknown therefore costs nothing
today and stops a new signup from silently inheriting OASIS's legal identity.

ADDING A TENANT
---------------
Add the UUID here with its brand, and add the same brand to
send_gateway.BRAND_IDENTITY and email_template.BRAND_CONFIG. The parity test
(scripts/tests/test_tenant_brand.py) fails if the three disagree.
"""

from __future__ import annotations

from typing import Mapping, Optional

# NO LOCAL LIST OF BRAND NAMES LIVES HERE, deliberately.
#
# The first draft of this module declared its own KNOWN_BRANDS tuple "to avoid a
# circular import". That would have been a FOURTH brand vocabulary in a system
# whose defect was three brand vocabularies disagreeing — send_gateway's
# BRAND_IDENTITY, email_template's BRAND_CONFIG, and brands.ts's BrandKey, where
# a name valid in one silently became another company in the next.
#
# send_gateway.BRAND_IDENTITY is the authority for which brands exist. It
# validates `brand` itself right after calling this module, and
# scripts/tests/test_tenant_brand.py asserts every value mapped below is a key
# in it. A second list here could only ever drift from that one.

# tenant_id (UUID) -> brand key.
#
# Verified against the live Turso `tenants` table on 2026-09-09. The slug is in
# the comment because the UUID is what actually flows through the send path and
# the slug is what a human recognises; the two have already drifted once (see
# SLUG_BRAND below).
TENANT_BRAND: dict[str, str] = {
    # SunBiz Funding LLC — the client. slug "submissions", name "SunBiz".
    "aa04fa1f-ad6a-44b0-ac4b-2ff5d1067110": "sunbiz",
    # OASIS AI Solutions — CC's own agency CRM. slug "oasis-ai-cc".
    "ef8d389e-3f15-43f2-ae00-3660f69a1452": "oasis",
    # OASIS Web Studio — slug "oasis-webdev". Zero users, kept so a stray send
    # from the legacy web-leads path resolves to OASIS rather than to nothing.
    "42423fde-be8b-454f-932a-750e8c9b743d": "oasis",
}

# slug -> brand, for the callers that only ever see a slug.
#
# "submissions" is SunBiz's TENANT slug; its dashboard PROFILE slug is "sun".
# Both appear in the codebase and they are not the same string — a migration
# already no-op'd because it queried tenants.slug='sun'. Both are mapped here.
#
# NOTE the near-miss: a self-signup tenant exists with slug
# "submissions-5f63d7e6". It is NOT SunBiz. Never prefix-match a slug.
SLUG_BRAND: dict[str, str] = {
    "submissions": "sunbiz",
    "sunbiz": "sunbiz",
    "sun": "sunbiz",
    "oasis-ai-cc": "oasis",
    "oasis-webdev": "oasis",
    "oasis": "oasis",
}


# Authenticated mailbox -> tenant_id.
#
# The mailbox a process authenticates as IS the company it is acting for. This
# is a stronger signal than anything inferred from message content: an inbound
# sweep binds to exactly one credential, so every message it reads belongs to
# that mailbox's tenant, whatever the sender claims.
#
# Added 2026-09-09 because email_engine.cmd_check_inbox stamped
# "tenant_id": None on every message it read, which meant the autonomous
# reply path had no tenant, therefore no brand, therefore the OASIS default.
MAILBOX_TENANT: dict[str, str] = {
    "conaugh@oasisai.work": "ef8d389e-3f15-43f2-ae00-3660f69a1452",       # OASIS
    "submissions@sunbizfunding.com": "aa04fa1f-ad6a-44b0-ac4b-2ff5d1067110",  # SunBiz
}


# brand -> the domain its mail MUST leave from.
#
# This is the last line of defence, and the one that would have caught the
# 2026-09-09 incident on its own. Everything upstream decides what a message
# SAYS; this decides whether the mailbox actually authenticating is entitled to
# say it. A message composed as OASIS but authenticated as
# submissions@sunbizfunding.com is a client's mailbox asserting our identity —
# and it is also DKIM-misaligned, so a receiver sees a domain that does not
# match the From header.
#
# Only brands with a real, verified sending domain are listed. A brand that is
# absent here is NOT checked, which keeps the semi-retired
# conaugh_mckenna / nostalgic brands sending exactly as they do today rather
# than failing closed on a domain nobody has established.
#
# Safe to enforce, verified against the live ledger 2026-09-09: every recorded
# outbound from_address is already domain-correct for its tenant
# (oasis-ai-cc -> conaugh@oasisai.work; submissions -> *@sunbizfunding.com).
# Zero cross-domain sends exist, so this refuses nothing that currently works.
BRAND_SENDING_DOMAIN: dict[str, str] = {
    "oasis": "oasisai.work",
    "sunbiz": "sunbizfunding.com",
    "bluerise": "bluerisebusinesscapital.com",
}


def mailbox_matches_brand(
    brand: Optional[str],
    mailbox: Optional[str],
) -> tuple[bool, str]:
    """May this mailbox send as this brand?

    Returns (ok, reason). ok is True when they agree, when the brand has no
    established sending domain, or when either value is missing — this answers
    only the DISAGREEMENT question, exactly like brand_matches_tenant. Deciding
    what to do about a missing value stays with the caller.
    """
    b = (brand or "").strip().lower()
    expected = BRAND_SENDING_DOMAIN.get(b)
    if not expected:
        return True, f"brand '{b}' has no pinned sending domain — not checked"

    addr = (mailbox or "").strip().lower()
    if "<" in addr and ">" in addr:
        addr = addr[addr.rfind("<") + 1 : addr.rfind(">")].strip()
    if "@" not in addr:
        return True, "no mailbox to check"

    got = addr.rsplit("@", 1)[1].strip()
    # Accept the exact domain or any subdomain of it.
    if got == expected or got.endswith("." + expected):
        return True, f"mailbox {addr} is on {expected}"
    return False, (
        f"brand '{b}' must send from {expected}, but the authenticating mailbox "
        f"is {addr} (domain {got})"
    )


def brand_for_mailbox(address: Optional[str]) -> Optional[str]:
    """The brand this mailbox is entitled to send as, or None.

    The inverse of BRAND_SENDING_DOMAIN. None means nobody has decided what
    company this mailbox speaks for, and the caller must refuse rather than
    pick one — a renderer that guesses is how the OASIS shell went out of
    submissions@sunbizfunding.com.

    Deliberately keyed on the DOMAIN, not the individual address, so a rep's
    own mailbox on an entitled domain resolves without being enumerated.
    """
    a = (address or "").strip().lower()
    if not a:
        return None
    if "<" in a and ">" in a:
        a = a[a.rfind("<") + 1 : a.rfind(">")].strip()
    if a.count("@") != 1:
        return None
    domain = a.rsplit("@", 1)[1].strip()
    for brand, entitled in BRAND_SENDING_DOMAIN.items():
        if domain == entitled or domain.endswith("." + entitled):
            return brand
    return None


# brand -> the legal COMPANY it belongs to.
#
# The cross-tenant question that matters is not "is this mailbox on the brand's
# own domain" but "does this mailbox belong to the OTHER company". A SunBiz rep
# who connected a personal Gmail is not another company's identity, and refusing
# them would be a new SunBiz outage. A SunBiz mailbox sending an OASIS message is
# the 2026-09-09 incident.
#
# SunBiz Funding and Bluerise Business Capital share premises by agreement
# (Adon, 2026-08-05), and lib/smtp_send already lets either domain carry the
# Hallandale identification block, so they are one side of the line and OASIS is
# the other. test_dashboard_consumer_tenant_scope asserts this map agrees with
# smtp_send's entitlement sets, so the two cannot drift apart.
BRAND_COMPANY: dict[str, str] = {
    "oasis": "oasis",
    "sunbiz": "sunbiz",
    "bluerise": "sunbiz",
}


def mailbox_is_other_company(
    brand: Optional[str], mailbox: Optional[str]
) -> tuple[bool, str]:
    """True when the mailbox belongs to a DIFFERENT company than `brand`.

    Only a definite conflict counts: the brand's company and the mailbox's
    company must both be known, and differ. A personal or unregistered mailbox
    resolves to no company, so it is not a conflict — it cannot claim another
    company's identity, and lib/smtp_send still inspects whatever it sends.
    """
    b = (brand or "").strip().lower()
    mine = BRAND_COMPANY.get(b)
    mb_brand = brand_for_mailbox(mailbox)
    theirs = BRAND_COMPANY.get(mb_brand) if mb_brand else None
    if mine is None or theirs is None:
        return False, "not a cross-company pair"
    if mine == theirs:
        return False, f"mailbox and brand '{b}' belong to the same company"
    addr = (mailbox or "").strip().lower()
    return True, (
        f"brand '{b}' belongs to {mine}, but the sending mailbox {addr} belongs "
        f"to {theirs}; one company's message may not leave from the other's mailbox"
    )


def tenants_for_mailbox(mailbox: Optional[str]) -> list[str]:
    """Tenant ids whose mail this mailbox's company is entitled to send.

    [] when the mailbox belongs to no registered company: the caller must then
    send NOTHING, not everything. Used to scope a shared queue — a consumer
    authenticated as one company must not even CLAIM the other company's rows,
    or they are either leaked (the incident) or refused into 'failed' when the
    right consumer could have sent them.
    """
    mb_brand = brand_for_mailbox(mailbox)
    company = BRAND_COMPANY.get(mb_brand) if mb_brand else None
    if company is None:
        return []
    return sorted(tid for tid, b in TENANT_BRAND.items()
                  if BRAND_COMPANY.get(b) == company)


# How each company is named in its own operators' alerts.
COMPANY_DISPLAY_NAME: dict[str, str] = {"oasis": "OASIS AI", "sunbiz": "SunBiz"}


def host_mailbox(env: Mapping[str, str]) -> str:
    """The mailbox a box authenticates as, which decides the company it serves.

    The dashboard consumer (what its queue may claim) and the queue monitor
    (what it watches) both read it here, so they cannot disagree about which
    company this box works for. Each candidate is stripped BEFORE precedence:
    a whitespace-only GMAIL_USER, which is truthy, must not mask a real
    GMAIL_ADDRESS. (Codex, PR #73.)
    """
    for key in ("GMAIL_USER", "GMAIL_ADDRESS"):
        value = (env.get(key) or "").strip()
        if value:
            return value
    return ""


def company_for_mailbox(mailbox: Optional[str]) -> Optional[str]:
    """The company ('oasis' or 'sunbiz') a mailbox belongs to, or None."""
    brand = brand_for_mailbox(mailbox)
    return BRAND_COMPANY.get(brand) if brand else None


def resolve_tenant_for_mailbox(address: Optional[str]) -> Optional[str]:
    """The tenant that owns this mailbox, or None.

    None means the caller must not assume a company. A mailbox that is not
    listed here is one nobody has decided the ownership of, and inventing an
    answer is how a client's thread gets answered under another company's name.
    """
    a = (address or "").strip().lower()
    if not a:
        return None
    # Tolerate an RFC 5322 display-name form: "OASIS AI <conaugh@oasisai.work>".
    if "<" in a and ">" in a:
        a = a[a.rfind("<") + 1 : a.rfind(">")].strip()
    return MAILBOX_TENANT.get(a)


def resolve_brand_for_tenant(
    tenant_id: Optional[str] = None,
    slug: Optional[str] = None,
) -> Optional[str]:
    """The brand this tenant sends as, or None when we do not know.

    None is a legitimate, expected answer and means "refuse to send commercial
    mail", never "use the default". Callers that turn None into a brand
    reintroduce the exact defect this module exists to remove.

    The tenant_id wins when both are supplied: the UUID is the primary key and
    the slug is display text that has already drifted from it once.
    """
    tid = (tenant_id or "").strip().lower()
    s = (slug or "").strip().lower()

    # A SUPPLIED BUT UNMAPPED id returns None. It does NOT fall through to the
    # slug.
    #
    # The first version fell through, which contradicted the docstring above and
    # reopened the hole one layer down: resolve_brand_for_tenant(<stranger's
    # tenant>, "submissions") would have answered "sunbiz". The id is the
    # primary key — holding one we do not recognise is exactly the case where
    # guessing is worst. (Codex, adversarial review, 2026-09-09.)
    if tid:
        brand = TENANT_BRAND.get(tid)
        if not brand:
            return None
        # If a slug was also supplied and disagrees, refuse rather than choose.
        if s:
            by_slug = SLUG_BRAND.get(s)
            if by_slug and by_slug != brand:
                return None
        return brand

    if s:
        # Exact match only. "submissions-5f63d7e6" is a different company.
        return SLUG_BRAND.get(s)
    return None


def brand_matches_tenant(
    brand: Optional[str],
    tenant_id: Optional[str] = None,
    slug: Optional[str] = None,
) -> tuple[bool, str]:
    """Does the caller's brand agree with the tenant's real identity?

    Returns (ok, reason). `ok` is True when they agree, when the tenant is
    unknown (nothing to contradict), or when no tenant was supplied at all —
    this function answers only the DISAGREEMENT question. Deciding what to do
    about a missing brand or an unknown tenant is the caller's policy choice,
    made once in send_gateway.send().
    """
    expected = resolve_brand_for_tenant(tenant_id, slug)
    if expected is None:
        return True, "tenant unknown — nothing to contradict"
    b = (brand or "").strip().lower()
    if not b:
        return True, "no brand supplied — caller should derive, not validate"
    if b == expected:
        return True, f"brand '{b}' matches tenant"
    return False, (
        f"brand '{b}' does not match tenant {tenant_id or slug} "
        f"(that tenant sends as '{expected}')"
    )
