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

from typing import Optional

# Brand keys that carry a real legal identity (name + postal address) and are
# therefore lawful to attach to a commercial electronic message.
#
# Kept as a plain tuple rather than imported from send_gateway to avoid a
# circular import: send_gateway imports THIS module, not the other way around.
KNOWN_BRANDS: tuple[str, ...] = ("oasis", "sunbiz", "conaugh_mckenna", "nostalgic")

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
    if tid:
        brand = TENANT_BRAND.get(tid)
        if brand:
            return brand
    s = (slug or "").strip().lower()
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
