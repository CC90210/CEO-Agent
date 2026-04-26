"""Shared name-sanitization for any path that interpolates a lead's
first or full name into outbound copy (email body, calendar invite,
DM, SMS).

Surfaced 2026-04-25 by the "Hi Contact," disaster: 9 cold outreach
emails went out with `{{first_name}}` rendered as the literal CSV
import placeholder "Contact". Root cause was three layers (CRM data,
staging code, render path). This module is the render-path defense:
no matter what junk is upstream, what reaches a real recipient is
either a real human name or a sane generic fallback.

Public API:
    PLACEHOLDER_FIRST_NAMES — set[str] of lowercase placeholders to block
    safe_first_name(value, fallback="team")  -> str
    safe_full_name(value,  fallback="there") -> str
    sanitize_template_vars(variables, key="first_name", fallback="team") -> dict

Two fallbacks because the call sites differ:
    Templates render "Hi {{first_name}}," — `team` reads naturally for
        a generic inbox (info@, contact@) where no person is known.
    outreach_engine renders "Hi {lead_name},", where lead_name is a
        full name like "Jonathan Hutton" — `there` reads naturally as
        a fallback ("Hi there,").
"""

from __future__ import annotations


PLACEHOLDER_FIRST_NAMES: frozenset[str] = frozenset({
    "", "contact", "owner", "manager", "owner/manager", "admin", "info",
    "support", "sales", "team", "hello", "there", "office", "reception",
    "customer", "client", "user", "guest", "n/a", "na", "none", "null",
    "unknown", "no name", "noname", "first_name", "name",
})


def _is_placeholder(value: str) -> bool:
    """True if `value` (already lower+stripped) is a known placeholder
    or contains no letter characters at all (e.g. '...', '---', '???').
    """
    if value in PLACEHOLDER_FIRST_NAMES:
        return True
    if not any(c.isalpha() for c in value):
        return True
    return False


def safe_first_name(value, fallback: str = "team") -> str:
    """Return a render-safe first name.

    Behavior:
      - None / non-str / empty / whitespace → fallback
      - Placeholder string ("contact", "owner", "info", ...) → fallback
      - All-punctuation / digits-only → fallback
      - Real name → original (with surrounding whitespace stripped)

    Casing is preserved on real names ("jonathan" stays "jonathan",
    "JONATHAN" stays "JONATHAN") — the caller decides how to format.
    """
    if value is None:
        return fallback
    if not isinstance(value, str):
        return fallback
    stripped = value.strip()
    if not stripped:
        return fallback
    if _is_placeholder(stripped.lower()):
        return fallback
    return stripped


def safe_full_name(value, fallback: str = "there") -> str:
    """Return a render-safe full name (or fallback).

    Same rules as safe_first_name but with a different default fallback
    because full-name call sites typically render "Hi {lead_name},"
    where "Hi there," is the most natural generic.
    """
    return safe_first_name(value, fallback=fallback)


def sanitize_template_vars(
    variables: dict,
    key: str = "first_name",
    fallback: str = "team",
) -> dict:
    """Return a copy of `variables` with `key` normalized via
    safe_first_name. Other keys are passed through untouched.

    `company` and other business-critical fields are deliberately NOT
    sanitized — a missing company is a real data bug worth surfacing,
    not papering over with a generic.
    """
    if not isinstance(variables, dict):
        return variables
    out = dict(variables)
    out[key] = safe_first_name(out.get(key), fallback=fallback)
    return out
