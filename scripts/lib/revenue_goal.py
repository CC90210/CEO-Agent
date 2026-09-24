"""The active company revenue goal — one source for every CLI that mentions it.

The goal lives in the OASIS Command Center's `revenue_goals` table (Turso,
migration 182). Before 2026-09-24 five scripts each hard-coded their own copy
("$10,000 Net MRR by 2026-09-30"); when CC reset OASIS to live Stripe numbers
and set a collected-revenue sprint, every copy was instantly wrong. Read the
row; never restate the number.

The goal is REVENUE COLLECTED in a period (net of refunds, own-day FX), not an
MRR target — MRR is reported on its own and has no target. Progress is computed
by the Command Center's Finances ledger (Today page); this module only says
what the goal is.
"""
from __future__ import annotations

import datetime

OASIS_TENANT_ID = "ef8d389e-3f15-43f2-ae00-3660f69a1452"


def active_revenue_goal(tenant_id: str = OASIS_TENANT_ID) -> dict | None:
    """The active goal row, or None when none is set. Raises on a DB failure —
    a script that silently printed "no goal" would read as "no target"."""
    from lib.db_turso import get_db

    rows = get_db().query(
        "SELECT label, target_cents, currency, period_start, period_end "
        "FROM revenue_goals WHERE tenant_id = ? AND metric = 'revenue_collected' "
        "AND status = 'active' LIMIT 1",
        [tenant_id],
    )
    if not rows:
        return None
    row = dict(rows[0])
    # libSQL over HTTP returns integers as strings; coerce at the boundary.
    row["target_cents"] = int(row["target_cents"])
    return row


def days_left(goal: dict, today: datetime.date | None = None) -> int:
    """Calendar days left INCLUDING today; the end date is inclusive."""
    today = today or datetime.date.today()
    end = datetime.date.fromisoformat(goal["period_end"])
    return max((end - today).days + 1, 0)


def describe(goal: dict | None) -> str:
    if not goal:
        return "No active revenue goal (set one in the Command Center)."
    amount = goal["target_cents"] / 100
    return (f"{goal['label']}: >= {goal['currency']} {amount:,.0f} collected, "
            f"{goal['period_start']} -> {goal['period_end']} "
            f"(progress: Command Center > Today)")
