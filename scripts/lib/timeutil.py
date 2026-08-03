"""One correct way to read a stored ISO timestamp.

Four call sites across pulse_publish.py and state_sync.py had grown their own
copy of the same three lines: swap a trailing `Z` for `+00:00`, parse, and — in
three of the four — attach UTC when the value came back naive. `validate()` was
the fourth and skipped the tzinfo step, so a naive timestamp validated fine and
then produced a wrong age everywhere downstream.

That asymmetry is the reason this exists. The `Z` swap is trivial; remembering
that `datetime.fromisoformat` hands back a naive object for a naive string, and
that subtracting it from an aware `now()` raises, is the part that gets dropped
on the fourth copy. One function, one behaviour.
"""
from __future__ import annotations

from datetime import datetime, timezone


def parse_iso_utc(value: object) -> datetime | None:
    """Parse an ISO-8601 string to an aware datetime **in UTC**, or None.

    The name promises UTC, so the result is normalized to it — an offset like
    +02:00 comes back as the same instant expressed in UTC. Arithmetic is
    identical either way, but `.hour` is not, and a function that says utc while
    handing back a +02:00 object is a landmine for the first caller that formats
    the result.

    Returns None for anything unparseable — callers decide whether that is an
    error (a schema check) or information (a sibling agent that has never
    published). Never raises: a bad timestamp must not take down the caller.
    """
    if isinstance(value, datetime):
        aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return aware.astimezone(timezone.utc)
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except (ValueError, TypeError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def age_hours(value: object, now: datetime | None = None) -> float | None:
    """Hours since `value`, or None if it cannot be read."""
    parsed = parse_iso_utc(value)
    if parsed is None:
        return None
    return ((now or datetime.now(timezone.utc)) - parsed).total_seconds() / 3600


def age_days(value: object, now: datetime | None = None) -> float | None:
    """Days since `value`, or None if it cannot be read."""
    hours = age_hours(value, now)
    return None if hours is None else hours / 24
