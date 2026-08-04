"""Canonical contract every scraping agent must fulfil when inserting a lead.

The dashboard's lead-detail surface (see [LeadDetailDrawer.tsx](../../../APPS/oasis-command-center/components/leads/LeadDetailDrawer.tsx)
+ /pipeline/[id]/page.tsx) expects a stable set of fields on every lead so
the operator never sees blank-card surprises. CC's directive
(2026-05-21): "There are still some inconsistencies and issues. Some
of the leads are coming up as 'untitled' just because there is no name
listed. We should also train our scraping agents on what they need to
get."

This module is the one-stop check every writer goes through before
hitting the DB. It does TWO things:

  1. validate_lead(row) → list[str] of missing required keys.
     Used in tests + CI to catch a scraper that's dropping fields.

  2. enrich_lead_defaults(row) → row with sensible defaults filled in
     and missing_info[] populated. The dashboard's ManifestKanban /
     LeadPipelineView render missing_info as a red chip so the
     operator sees AT A GLANCE which leads need enrichment before
     the next outbound touch.

Required fields (CC's contract, 2026-05-21):
  - name OR contact_name OR company (something for the card title)
  - email   (the primary outreach channel — drop the lead if absent)
  - phone   (fallback channel + bot-detection signal)
  - source  (provenance — firecrawl / sunbiz / referral / website-form / ...)
  - stage   (where in pipeline — defaults to 'new')
  - score   (0-100; auto_score_leads fills it in if 0)
  - value_estimate  (USD/CAD estimate of deal size; null until enriched)
  - notes   (free-form context, ideally including AI rationale from auto-score)
"""
from __future__ import annotations

from typing import Any


# Fields the dashboard expects on every lead. Order matters for the
# missing_info chip rendering — most-important first.
REQUIRED_FIELDS: tuple[str, ...] = (
    "name",
    "company",
    "email",
    "phone",
    "source",
    "stage",
    "score",
    "value_estimate",
    "notes",
)

# Subset that MUST be present (lead is rejected if missing). Everything
# else gets flagged in missing_info but the row still goes in — the
# operator can enrich later.
HARD_REQUIRED: tuple[str, ...] = ("email", "source")

# Default values for soft-required fields when the scraper didn't supply one.
SOFT_DEFAULTS: dict[str, Any] = {
    "stage": "new",
    "score": 0,
    "value_estimate": None,
    "notes": "",
}


def _is_present(v: Any) -> bool:
    """Lead-contract notion of "present": non-None, non-empty string,
    non-zero for numeric (zero score is treated as 'unscored' = missing)."""
    if v is None:
        return False
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, (list, tuple, set, dict)):
        return len(v) > 0
    return True


def validate_lead(row: dict[str, Any]) -> list[str]:
    """Return list of missing required fields. Empty list = valid."""
    return [k for k in REQUIRED_FIELDS if not _is_present(row.get(k))]


def has_hard_required(row: dict[str, Any]) -> bool:
    """True if every HARD_REQUIRED field is present. False → reject the insert."""
    return all(_is_present(row.get(k)) for k in HARD_REQUIRED)


# ── Who is even eligible to BE a lead ──────────────────────────────────────
# has_hard_required() answers "is this row well-formed". It does not answer
# "should this sender exist in the CRM at all", and nothing did — so every
# inbound email and every outbound recipient auto-created a lead. On
# 2026-08-04 that was 37 of 63 rows (59%): Google/Stripe/Vercel/LinkedIn
# notifications, vendor newsletters, and one send-path probe to an RFC-2606
# reserved domain. Lead counts and pipeline metrics were reading 2.4x reality.

# RFC 2606 / RFC 6761 reserved TLDs — guaranteed undeliverable, so a message
# to one is a test, never a prospect.
_RESERVED_TLDS: tuple[str, ...] = (".invalid", ".test", ".example", ".localhost")
_BARE_RESERVED: frozenset[str] = frozenset({"invalid", "test", "example", "localhost"})

# Local-parts that are machines by definition. Deliberately CONSERVATIVE:
# "hello@", "info@" and "team@" are NOT here, because on an inbound-first
# funnel a real prospect can absolutely write from one. A junk row costs a
# metric; a dropped prospect costs revenue.
#
# Matched against the local-part with separators stripped, because production
# uses every arrangement: noreply@, no-reply@, payments-noreply@,
# cloudplatform-noreply@, notifications-noreply@. A first draft only handled
# the prefix form and let 3 of those through.
_MACHINE_SUBSTRINGS: tuple[str, ...] = (
    "noreply", "donotreply", "mailerdaemon",
)
# Whole-word only — "bounce" as a substring would catch a real "bouncer@".
_MACHINE_EXACT: frozenset[str] = frozenset({"bounce", "bounces", "postmaster"})

# Model-assigned intents that mean "not a person doing business with us".
_NON_LEAD_INTENTS: frozenset[str] = frozenset({
    "spam_bounce", "noise", "out_of_office", "unsubscribe",
})


def should_create_lead(email: str,
                       classification: dict[str, Any] | None = None) -> tuple[bool, str]:
    """Should this sender/recipient become a CRM lead? Returns (create, reason).

    Two tiers, in this order, and the order is the point:

    1. DETERMINISTIC veto — reserved TLDs and machine local-parts. Always
       applied, never overridable by a model. [[pattern_degraded_classifier_must_not_book]]:
       a degraded LLM read must not be the only thing standing between vendor
       mail and the CRM.
    2. CLASSIFIER veto — low_priority / spam_bounce / noise, but ONLY when the
       classifier is healthy. A `fallback: True` read is the keyword degraded
       path, and acting on it here would silently drop real prospects during a
       model outage. When degraded we CREATE and let a human sort it out:
       failing toward keeping the lead is the only safe bias for an
       inbound-first funnel.
    """
    addr = (email or "").strip().lower()
    if not addr or "@" not in addr:
        return False, "not an email address"

    domain = addr.rsplit("@", 1)[-1]
    # `endswith` alone misses a BARE reserved name — "harness@localhost" has
    # domain "localhost", which does not end with ".localhost".
    if domain.endswith(_RESERVED_TLDS) or domain in _BARE_RESERVED:
        return False, f"reserved/undeliverable domain ({domain})"

    local = addr.split("@", 1)[0]
    flat = "".join(ch for ch in local if ch.isalnum())
    if any(machine in flat for machine in _MACHINE_SUBSTRINGS) or flat in _MACHINE_EXACT:
        return False, f"automated sender ({local}@)"

    if classification:
        if classification.get("fallback") is True:
            return True, "classifier degraded — creating rather than risk dropping a prospect"
        if str(classification.get("category", "")).strip().lower() == "low_priority":
            return False, "classified low_priority (newsletter/notification)"
        if str(classification.get("intent", "")).strip().lower() in _NON_LEAD_INTENTS:
            return False, f"intent={classification.get('intent')}"

    return True, "eligible"


def enrich_lead_defaults(row: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of row with soft defaults applied and missing_info[] set.

    The dashboard reads missing_info from row.data and renders a red chip
    listing which fields the operator should fill before the next touch.
    Idempotent — re-running on an already-enriched row is a no-op.
    """
    out = dict(row)
    for k, default in SOFT_DEFAULTS.items():
        if k not in out or not _is_present(out.get(k)):
            out[k] = default
    out["missing_info"] = validate_lead(out)
    return out
