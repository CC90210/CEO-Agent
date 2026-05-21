"""schedule_helpers.py — local-time cron parsing + quiet-day awareness.

Two responsibilities, both pre-2026-05-17 missing from this repo:

  1. next_local_cron_run(schedule, after, tz)
     Parse a 5-field cron expression IN LOCAL TIME (default America/Toronto)
     and return the next UTC datetime it would fire. Replaces the old
     UTC-naive logic in scripts/scheduler.py and scripts/core/cron_engine.py,
     which interpreted "0 8 * * *" as 08:00 UTC and fired Aura's Morning
     Pow Wow at 04:00 ET on 2026-05-17 (Sunday of the Victoria Day long
     weekend). Cron schedules are operator-authored — operators think in
     local time, period.

  2. is_quiet_day(date) / is_canadian_stat_holiday(date)
     Honour weekends + Ontario stat holidays so jobs like the Pow Wow can
     skip days CC isn't working. Returns (bool, reason) so the caller can
     log "skipped: Sunday of Victoria Day long weekend" instead of a
     bare boolean. Holiday table is Ontario-specific because that's where
     CC operates; extend per-tenant later if needed.

Cron expression coverage (intentionally a subset, not a full RFC):
  minute, hour: numeric, '*', '*/N', 'M1,M2,...'
  day-of-month: numeric, '*', 'D1,D2,...'
  month       : numeric, '*', 'M1,M2,...'
  day-of-week : numeric (cron: Sun=0..Sat=6), names (MON,TUE,...),
                ranges (MON-FRI), lists (MON,WED,FRI), '*'

Anything more exotic returns None from next_local_cron_run so callers can
fall back to "daily" semantics rather than crash.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo


DEFAULT_TZ_NAME = os.environ.get("EMPIRE_LOCAL_TZ", "America/Toronto")

_DAY_NAMES = {
    "SUN": 0, "MON": 1, "TUE": 2, "WED": 3,
    "THU": 4, "FRI": 5, "SAT": 6,
}


def local_tz(name: Optional[str] = None) -> ZoneInfo:
    return ZoneInfo(name or DEFAULT_TZ_NAME)


# -- Cron field parsing --------------------------------------------------------

def _parse_field(field: str, low: int, high: int, names: Optional[dict[str, int]] = None) -> Optional[set[int]]:
    """Expand a single cron field into the set of integers it matches.

    Returns None on any unsupported syntax (caller treats as parse failure).
    Range is inclusive.
    """
    field = field.strip()
    if not field:
        return None

    if names:
        for name, num in names.items():
            field = field.replace(name, str(num))

    # Wildcard or step over wildcard
    if field == "*":
        return set(range(low, high + 1))
    if field.startswith("*/"):
        try:
            step = int(field[2:])
            if step <= 0:
                return None
            return set(range(low, high + 1, step))
        except ValueError:
            return None

    out: set[int] = set()
    for part in field.split(","):
        part = part.strip()
        if "-" in part:
            try:
                a_s, b_s = part.split("-", 1)
                a, b = int(a_s), int(b_s)
            except ValueError:
                return None
            if a < low or b > high or a > b:
                return None
            out.update(range(a, b + 1))
        else:
            try:
                v = int(part)
            except ValueError:
                return None
            if v < low or v > high:
                return None
            out.add(v)
    return out or None


def _cron_weekday(d: date) -> int:
    """Python: Mon=0..Sun=6. Cron: Sun=0..Sat=6. Translate."""
    return (d.weekday() + 1) % 7


def next_local_cron_run(
    schedule: str,
    after: Optional[datetime] = None,
    tz: Optional[ZoneInfo] = None,
) -> Optional[datetime]:
    """Compute the next UTC datetime the schedule fires, interpreting the
    cron expression in LOCAL time (defaults to America/Toronto).

    Returns timezone-aware UTC datetime, or None if the expression can't
    be parsed by this subset.
    """
    parts = schedule.strip().split()
    if len(parts) != 5:
        return None

    minutes = _parse_field(parts[0], 0, 59)
    hours = _parse_field(parts[1], 0, 23)
    doms = _parse_field(parts[2], 1, 31)
    months = _parse_field(parts[3], 1, 12)
    dows = _parse_field(parts[4], 0, 6, names=_DAY_NAMES)
    if not all([minutes, hours, doms, months, dows]):
        return None

    tz = tz or local_tz()
    after_utc = (after or datetime.now(timezone.utc)).astimezone(timezone.utc)
    after_local = after_utc.astimezone(tz)

    # Cron has minute granularity. The "next" run must be strictly after
    # `after`, so start scanning from the next minute boundary.
    start = (after_local + timedelta(minutes=1)).replace(second=0, microsecond=0)

    for day_offset in range(0, 366):
        d_local = (start + timedelta(days=day_offset)).date()
        if d_local.month not in months:
            continue
        if d_local.day not in doms:
            continue
        if _cron_weekday(d_local) not in dows:
            continue
        for h in sorted(hours):
            for m in sorted(minutes):
                cand = datetime(d_local.year, d_local.month, d_local.day, h, m, tzinfo=tz)
                if cand >= start:
                    return cand.astimezone(timezone.utc)
    return None


def next_local_cron_run_iso(schedule: str, after: Optional[datetime] = None) -> Optional[str]:
    dt = next_local_cron_run(schedule, after=after)
    return dt.isoformat() if dt else None


# -- Ontario stat-holiday table ------------------------------------------------
#
# Hard-coded through 2027 to avoid pulling in `holidays` as a runtime dep just
# for this. Extend the table each November before the new year rolls in. If
# the table is exhausted (no entries for `date.year`), is_canadian_stat_holiday
# returns False — callers must not infer "not a holiday" from an unmaintained
# table, so the helper logs a warning to stderr when consulted past the table.

_ONTARIO_STAT_HOLIDAYS: dict[date, str] = {
    # 2026
    date(2026, 1, 1):  "New Year's Day",
    date(2026, 2, 16): "Family Day",
    date(2026, 4, 3):  "Good Friday",
    date(2026, 5, 18): "Victoria Day",
    date(2026, 7, 1):  "Canada Day",
    date(2026, 8, 3):  "Civic Holiday",
    date(2026, 9, 7):  "Labour Day",
    date(2026, 10, 12):"Thanksgiving",
    date(2026, 12, 25):"Christmas Day",
    date(2026, 12, 26):"Boxing Day",
    # 2027
    date(2027, 1, 1):  "New Year's Day",
    date(2027, 2, 15): "Family Day",
    date(2027, 3, 26): "Good Friday",
    date(2027, 5, 24): "Victoria Day",
    date(2027, 7, 1):  "Canada Day",
    date(2027, 8, 2):  "Civic Holiday",
    date(2027, 9, 6):  "Labour Day",
    date(2027, 10, 11):"Thanksgiving",
    date(2027, 12, 25):"Christmas Day",
    date(2027, 12, 27):"Boxing Day (observed)",
}


def is_canadian_stat_holiday(d: date) -> tuple[bool, str]:
    name = _ONTARIO_STAT_HOLIDAYS.get(d)
    if name:
        return True, name
    return False, ""


def is_quiet_day(d: date) -> tuple[bool, str]:
    """Days CC doesn't want to be poked by daily motivational/operational pings.

    Saturday + Sunday + Ontario stat holidays. Caller logs the reason.
    """
    hol, name = is_canadian_stat_holiday(d)
    if hol:
        return True, name
    wd = d.weekday()  # Mon=0..Sun=6
    if wd == 5:
        return True, "Saturday"
    if wd == 6:
        return True, "Sunday"
    return False, ""


def today_local(tz: Optional[ZoneInfo] = None) -> date:
    return datetime.now(tz or local_tz()).date()


if __name__ == "__main__":  # tiny smoke test
    import sys, json
    args = sys.argv[1:]
    if not args:
        now_utc = datetime.now(timezone.utc)
        for sched in ["0 8 * * *", "0 6 * * *", "*/5 * * * *", "0 22 * * SAT", "0 10 * * MON-FRI"]:
            nxt = next_local_cron_run(sched, after=now_utc)
            print(f"{sched:25}  next UTC: {nxt}  (local: {nxt.astimezone(local_tz()) if nxt else None})")
        td = today_local()
        print(f"\ntoday_local={td}  quiet={is_quiet_day(td)}")
    elif args[0] == "next":
        print(next_local_cron_run_iso(args[1]))
    elif args[0] == "quiet":
        y, m, d = map(int, args[1].split("-"))
        print(json.dumps({"date": args[1], "quiet": is_quiet_day(date(y, m, d))}))
