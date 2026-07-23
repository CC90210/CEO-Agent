"""RLS baseline regression guard (empire DB phctllmtsogkovoilwos).

Security audit 2026-06-21 (P1-8). 27 public tables have RLS ENABLED but ZERO
policies — i.e. deny-all to anon/authenticated, reachable only via the
service-role key. For the agent/state/internal tables that is the intended,
SECURE posture (the server writes them; no client should touch them). We do NOT
blindly add policies (that could wrongly OPEN access or break a service-role
flow). Instead we PIN this set as the reviewed baseline and fail CI if a NEW
table appears with RLS-but-no-policy, so every future one gets a human decision:
either add an explicit policy, or add it here with a reason.

Exit 0 = baseline matches (or only shrank — a table gained a policy).
Exit 1 = a NEW unexpected RLS-no-policy table appeared → review it.

Usage:  python scripts/state/assert_rls_baseline.py
Requires the bravo Supabase exec_sql RPC (same as supabase_tool.py).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.subprocess_helpers import safe_run  # noqa: E402

# Reviewed 2026-06-21: intentional service-role-only (RLS deny-all). If you add
# a table here, say why in the trailing comment.
APPROVED_SERVICE_ROLE_ONLY = {
    "agent_activity",            # agent<->agent coordination channel (service-role only)
    "agent_decisions",           # internal agent telemetry
    "agent_state_snapshot",      # internal agent state
    "booking_slots",             # written server-side; public reads go via API route
    "bookings",                  # written server-side; public reads go via API route
    "bridge_activity",           # bridge telemetry
    "content_calendar",          # Maven/agent-owned
    "content_templates",         # agent-owned
    "cron_jobs",                 # scheduler internal
    "drift_alerts",              # anti-drift internal
    "drift_baselines",           # anti-drift internal
    "email_log",                 # send-gateway internal
    "email_templates",           # agent-owned
    "funnel_entries",            # written via service-role submit route (not anon-direct)
    "funnels",                   # config, served via API route
    "lead_edges",                # graph internal
    "leads_outreach",            # outreach internal
    "memories_episodic",         # memory engine internal
    "memories_procedural",       # memory engine internal
    "memories_semantic",         # memory engine internal
    "monthly_metrics",           # analytics internal
    "nurture_sequences",         # drip config, agent-owned
    "pair_attempts",             # pairing internal
    "revenue_events",            # finance internal
    "shadow_decisions",          # shadow-mode telemetry
    "template_performance",      # analytics internal
    "vertical_response_patterns",# learning internal
}

_QUERY = (
    "SELECT c.relname AS tbl FROM pg_class c "
    "JOIN pg_namespace n ON n.oid=c.relnamespace "
    "WHERE n.nspname='public' AND c.relkind='r' AND c.relrowsecurity "
    "AND NOT EXISTS (SELECT 1 FROM pg_policy p WHERE p.polrelid=c.oid) ORDER BY 1"
)


def _live_rls_no_policy() -> set[str]:
    tool = Path(__file__).resolve().parent.parent / "integrations" / "supabase_tool.py"
    out = safe_run(
        [sys.executable, str(tool), "rpc", "exec_sql", json.dumps({"sql_query": _QUERY})],
        capture_output=True, text=True,
    ).stdout
    start = out.find("{")
    if start == -1:
        raise SystemExit("could not reach exec_sql RPC (is the bravo project configured?)")
    data = json.loads(out[start:])
    return {r["tbl"] for r in data.get("rows", [])}


def main() -> int:
    live = _live_rls_no_policy()
    new = sorted(live - APPROVED_SERVICE_ROLE_ONLY)
    gained_policy = sorted(APPROVED_SERVICE_ROLE_ONLY - live)

    if gained_policy:
        print(f"[info] {len(gained_policy)} baseline table(s) now have a policy (fine): {', '.join(gained_policy)}")
    if new:
        print("RLS BASELINE REGRESSION — new RLS-enabled tables with NO policy:")
        for t in new:
            print(f"  !! {t}")
        print("Decide for each: add an explicit RLS policy, or add it to "
              "APPROVED_SERVICE_ROLE_ONLY with a reason. Failing CI.")
        return 1

    print(f"[ok] RLS baseline matches — {len(live)} reviewed service-role-only tables, no new gaps.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
