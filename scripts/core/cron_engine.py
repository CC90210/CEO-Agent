"""
Cron Engine - Business Automation Job Manager
Defines and tracks all automated business workflows. Not a cron runner itself -
n8n handles scheduling. This is the source of truth for what should be automated,
seeded into Turso so the scheduler and agents share a single registry.

All credentials loaded from .env.agents (never hardcoded).

Usage:
  python scripts/core/cron_engine.py list [--active-only]
  python scripts/core/cron_engine.py add --name "Daily Content Post" --schedule "0 9 * * *" --type content_post --config '{"pillar": "ceo_log", "platform": "x"}'
  python scripts/core/cron_engine.py toggle <job_id>
  python scripts/core/cron_engine.py run <job_id>
  python scripts/core/cron_engine.py due
  python scripts/core/cron_engine.py seed
  python scripts/core/cron_engine.py --json <any command>
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# scripts/ on sys.path so `lib.tls_trust` resolves when this is run as
# `python scripts/core/cron_engine.py` (cwd-independent).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.tls_trust import ensure_os_trust  # noqa: E402
# Canonical sibling-repo resolver (honors the MAVEN_REPO override) — used by the
# one SEED_JOBS entry that runs a script outside this repo. Dependency-light
# (os/platform/pathlib only), which matters because the always-on scheduler
# imports this module.
from sibling_repos import SIBLING_REPOS  # noqa: E402


# -- Credential loading --------------------------------------------------------

def load_env() -> dict[str, str]:
    """Load .env.agents from project root."""
    env_path = Path(__file__).resolve().parent.parent.parent / ".env.agents"
    if not env_path.exists():
        print(f"ERROR: {env_path} not found", file=sys.stderr)
        sys.exit(1)

    env_vars: dict[str, str] = {}
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                env_vars[key.strip()] = value.strip()
    return env_vars


def get_client(env_vars: dict[str, str]):
    """Create the Turso-backed compatibility client for the Bravo project."""
    configure_ca_bundle()
    try:
        from supabase import create_client
    except ImportError:
        print("ERROR: 'supabase' package not installed. Run: pip install supabase", file=sys.stderr)
        sys.exit(1)

    url = env_vars.get("BRAVO_SUPABASE_URL") or "https://turso.compat"
    key = env_vars.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY") or "dummy-turso-key"

    return create_client(url, key)


def configure_ca_bundle() -> None:
    """Delegate to the canonical TLS helper — kept as a named function because
    call sites in this module already reference it.

    Was an inline copy of the truststore/certifi dance. Promoted 2026-07-29:
    lib/tls_trust also strips a poisoned SSLKEYLOGFILE, which this copy did not,
    and cron_engine sits directly on the path that outage took down. The old
    "is SSL_CERT_FILE set?" early-return also lived here — lib/tls_trust replaced
    that with _genuine_override(), which ignores stale and certifi-pointing
    values rather than treating them as operator intent.
    """
    ensure_os_trust()


# -- Seed definitions ----------------------------------------------------------

# Keys in a SEED_JOBS definition that are metadata for OTHER readers, not
# cron_jobs columns. cmd_seed strips these before INSERT. Add here when a seed
# needs to carry information for the watchdog / dashboards / docs.
SEED_METADATA_KEYS: frozenset[str] = frozenset({"daemon_backed"})

SEED_JOBS: list[dict] = [
    # Marketing/social cron jobs (content_post × 3, content_planning,
    # ig_research) were removed from this seed on 2026-04-26 when
    # marketing/social ownership transferred to Maven (CMO-Agent).
    # Maven seeds its own equivalents in CMO-Agent/scripts/core/cron_engine.py.
    # 'Lead Follow-up Check' removed 2026-05-22 — superseded by 'Nurture
    # Sequence Check' (both ran the same overdue-follow-up logic).
    {
        # 2026-07-23 — the native replacement for the n8n "OASIS Inbound
        # Qualifier (Bravo Aware)" 5-minute Gmail sweep. NOTHING scheduled the
        # inbox check before this: scheduler.py has always had an
        # 'email_inbox_check' handler, but no cron_jobs row ever invoked it, so
        # inbound email was handled ONLY by the n8n workflow. This row is what
        # makes the native multi-brain router (email_brain.py) actually run.
        # Requires EMAIL_BRAIN_ENABLED (set in ecosystem.config.js for
        # bravo-scheduler); without it the handler falls back to the legacy
        # notify-and-mark-read behavior.
        "name": "Inbound Email Sweep",
        "description": "Every 5 min: classify unread Gmail into 4 brains (support/opportunity/financial/low-priority), draft replies via send_gateway, hand Financial & Legal to Atlas, archive noise. Native n8n replacement.",
        "schedule": "*/5 * * * *",
        "action_type": "email_inbox_check",
        "action_config": {},
        "is_active": True,
    },
    {
        # Phase 5c — OASIS HQ daily AI brief. Local claude CLI narrates the
        # briefing_snapshot into a 5-bullet morning summary, shipped to
        # CC's Telegram via notify(force=True). No MRR — revenue reporting
        # is Atlas's (CFO). Empty pipeline data still produces a brief that
        # says "nothing happened" — the cron's job is to fire reliably.
        "name": "Daily Bravo Brief",
        "description": "AI-narrated morning brief — pipeline, follow-ups, client health — sent to CC's Telegram (no MRR; Atlas owns revenue)",
        "schedule": "0 6 * * *",
        "action_type": "daily_brief",
        "action_config": {"notify_channel": "telegram"},
        "is_active": True,
    },
    {
        # 2026-08-03 — the pulse producer that never existed. Atlas pages CC when
        # data/pulse/ceo_pulse.json is >14d old, and on 2026-08-03 it was 15d old
        # and correct: no cron had ever written it. Bravo's pulse was refreshed
        # only when a session happened to remember.
        #
        # This job runs `autorefresh`, NOT `refresh`. autorefresh writes only what
        # a machine can know — sibling pulse ages, V6 telemetry, the commit log —
        # and deliberately does NOT move `updated_at`. A nightly bare `refresh`
        # would have re-stamped the timestamp over 15-day-old strategy and
        # directives, silencing Atlas by making the data worse. The judgment
        # fields are written at session end (state_sync --pulse-*), because no
        # cron can honestly invent a CEO's strategic priority.
        #
        # 07:45 local: ahead of Atlas's 08:00 threshold scan, so the sibling-age
        # figures Atlas reads are same-morning. NOT seeded to Supabase until CC
        # reviews (production-scheduling mutation).
        "name": "Daily Pulse Mechanical Refresh",
        "description": "pulse_publish.py autorefresh — refresh machine-knowable pulse sections (sibling ages, V6 telemetry, commits). Never moves updated_at; judgment stays as stale as it is.",
        "schedule": "45 7 * * *",
        "action_type": "script_run",
        "action_config": {"script": "scripts/pulse_publish.py", "args": ["autorefresh"], "notify_channel": "telegram", "notify_on": "nonzero_exit"},
        "is_active": True,
    },
    {
        # 2026-08-20 — the Instagram DM closer. Replaces the keyword
        # autoresponder that read its own replies as prospect messages (it
        # compared an outgoing IGSID against a Zernio ObjectId, a comparison
        # that could never be true) and answered itself with the same template.
        #
        # */1 as of 2026-08-21 (was */5). A prospect waited 9 minutes for an answer
        # at */5 — correct per the config and unacceptable for a setter. The
        # per-run model budget drops to 2 so a run FINISHES inside its minute;
        # the O_EXCL lock makes an overrun skip the next tick rather than
        # double-send. Original sizing note follows.
        # The "~11s per model turn" figure this entry was first
        # written against is wrong: measured on this machine 2026-08-20,
        # run_claude_cli takes 29.2 / 26.7 / 28.1 / 25.8s — median 27.4s, because
        # the cost is `claude -p` process startup, not generation. decide() may
        # spend two subprocesses per conversation (one retry), so 12 turns is
        # ~330s worst case and would overrun a 120s tick on every run. The
        # poller's O_EXCL _RunLock refuses an overlapping tick rather than
        # doubling it, so the failure mode is a permanently-skipped automation
        # rather than a double-send — but it is still an automation that never
        # completes. 5 turns at */5 fits. timeout 600 overrides
        # SCRIPT_RUN_DEFAULT_TIMEOUT = 300.
        #
        # The duplicate is RESOLVED (2026-08-21). The legacy row "Instagram DM
        # Auto-Reply" was renamed in place to this entry's name and given these
        # args, so exactly ONE row now points at this script and `seed` skips it
        # by normalized name instead of creating a second. Two live crons on one
        # script is what answered CC twice; do not add a second row here.
        #
        # --book IS DELIBERATELY ABSENT. Without it the closer never runs and a
        # prospect who is ready to book becomes a Telegram handoff to CC instead
        # of a real calendar event and a Google invite to a stranger. Arming it
        # is CC's decision, not a seed default.
        #
        # NOT seeded until CC reviews: `cron_engine.py seed` is a
        # production-scheduling mutation.
        "name": "Instagram DM Closer",
        "description": "instagram_dm_poller.py — read each @oasisaisolutions DM thread in full, reply in CC's voice via the local Claude CLI, extract contact details, hand warm/blocked threads to CC. Booking stays disarmed.",
        "schedule": "* * * * *",
        "action_type": "script_run",
        "action_config": {
            "script": "scripts/integrations/instagram_dm_poller.py",
            "args": ["--live", "--json", "--limit", "25", "--max-model-calls", "2"],
            "timeout": 600,
            "notify_channel": "telegram",
            "notify_on": "nonzero_exit",
        },
        # DAEMON-BACKED — must stay False FOREVER. Execution moved to the PM2
        # process `bravo-ig-dm` (2026-08-21) because the shared scheduler queued
        # DM replies behind an 84s email sweep. The daemon reads this row at boot
        # and REFUSES TO START while it is armed (two runners answered every
        # prospect twice on 2026-08-20). Arming this row therefore takes the
        # setter OFFLINE — the exact inverse of what flipping a toggle ON should
        # do. The row exists as the config anchor the daemon checks, nothing
        # more. Control the setter with: pm2 start|stop bravo-ig-dm.
        "is_active": False,
        "daemon_backed": "bravo-ig-dm",
    },
    {
        # Phase 6a — OASIS auto-score sweep. Scans tenant_records for
        # OASIS leads with no ai_score and scores them in batches of 25
        # so the operator's morning view already has scores on
        # overnight-arrived leads. Daily at 05:45 — finishes before the
        # 06:00 Daily Brief so the brief can cite the new scores.
        "name": "OASIS Auto-Score Leads",
        "description": "Score any unscored OASIS leads in scorable stages (new/contacted/qualified/proposal/negotiation). Daily, batches of 25.",
        "schedule": "45 5 * * *",
        "action_type": "auto_score_leads",
        "action_config": {"batch_size": 25},
        "is_active": True,
    },
    {
        # Fleet V3 P6 — quarterly break-glass drill. Walks BREAK_GLASS.md's
        # preconditions in dry-run (can we stop / revoke / restore?) and reports
        # drift to Telegram. Changes nothing. 09:00 on the 1st of every 3rd month.
        # n8n handler for action_type 'break_glass_drill' runs
        # scripts/break_glass_drill.py --json; until that handler ships, run it
        # manually. NOT seeded to Supabase until CC reviews (production-scheduling mutation).
        "name": "Break-Glass Drill (quarterly)",
        "description": "Dry-run the emergency runbook; report drift between BREAK_GLASS.md and reality.",
        "schedule": "0 9 1 */3 *",
        "action_type": "break_glass_drill",
        "action_config": {"script": "scripts/break_glass_drill.py", "notify_channel": "telegram"},
        # NEVER RUN. A restore drill's first execution should be supervised, not a
        # 3am surprise — arm after one supervised run with CC.
        "is_active": False,
    },
    {
        # V7 EPIC 7F — Loud Failures Weekly Probe. system_health.py detects silent failures
        # (stale PM2 paths, missing cron/hook/MCP targets, scripts/*.py path drift) BEFORE
        # someone trips over them. Mondays 08:30 local; the probe Telegrams its own reds.
        # n8n handler for action_type 'script_run' runs the script; NOT seeded to Supabase
        # until CC reviews (production-scheduling mutation).
        #
        # --strict REMOVED 2026-08-03. It made the probe exit 1 on a finding, the scheduler
        # recorded "ERROR: script_run exit 1", and cron_health_check re-paged "1 cron(s)
        # failing" HOURLY for as long as the finding stood — a true signal delivered as a
        # metronome. EXECUTION_RULES § 19: a blocking condition exits 0 and reports. The
        # probe now owns its own alert (--notify), deduped on which checks are red, so it
        # fires once and decays. `--strict` still exits 1 for humans and CI.
        "name": "Loud Failures Weekly Probe",
        "description": "system_health.py --notify — surface silent failures (path drift, stale PM2, missing cron/hook/MCP targets).",
        "schedule": "30 8 * * 1",
        "action_type": "script_run",
        "action_config": {"script": "scripts/system_health.py", "args": ["--json", "--notify"], "notify_channel": "telegram", "notify_on": "nonzero_exit"},
        "is_active": True,
    },
    {
        # V7 EPIC 3 — weekly LanceDB compaction. Every PostToolUse edit appends a new
        # vector-store version with no cleanup (hit 410 versions / 32MB at the 2026-06-10
        # audit). optimize(cleanup_older_than=2d) compacts fragments + prunes stale versions,
        # keeping recent ones for safety. Saturdays 03:00 local. NOT seeded until CC reviews.
        "name": "LanceDB Compaction (weekly)",
        "description": "Compact the memory vector store; prune stale LanceDB versions (bounds unbounded growth).",
        "schedule": "0 3 * * 6",
        "action_type": "script_run",
        "action_config": {"script": "scripts/core/state_compact.py", "args": ["--retain-days", "2", "--json"]},
        "is_active": True,
    },
    {
        # Phase 10.2 — Morning Pow Wow Call. Claude drafts a ~120-word
        # motivational/flirty monologue, ElevenLabs renders it in Aura's
        # voice, Telegram sendVoice ships it as an inline voicemail at
        # 08:00 every morning. Cost ~$0.02/day. CC opts in/out via the
        # standard toggle.
        "name": "Morning Pow Wow Call",
        "description": "Aura's daily 8 a.m. voice note — a ~120-word motivational + flirty kickoff monologue delivered as a Telegram voice message. Lives in scripts/aura/. Cost ~$0.02/day (Claude draft + ElevenLabs TTS).",
        "schedule": "0 8 * * *",
        "action_type": "morning_powwow",
        "action_config": {"voice": "aura", "agent": "aura"},
        # 2026-07-09: matches live DB state (disabled since 2026-05-21) AND
        # scripts/aura/brain.py still drafts via the dead metered API key —
        # a reseed must not resurrect a job whose model call cannot succeed.
        # Re-enable only after porting aura/brain.py to lib/claude_cli.
        "is_active": False,
    },
    {
        "name": "Booking Reminders",
        "description": "Send reminders for tomorrow's bookings",
        "schedule": "0 18 * * *",
        "action_type": "booking_reminder",
        "action_config": {"hours_ahead": 24, "channels": ["email", "sms"]},
        "is_active": True,
    },
    {
        "name": "Stripe Revenue Sync",
        "description": "Sync latest Stripe events to revenue_events",
        "schedule": "0 6 * * *",
        "action_type": "stripe_sync",
        "action_config": {"lookback_hours": 25},
        # moved_to_atlas 2026-08-01 — Atlas (CFO-Agent) owns revenue sync; the live
        # row is a tombstone. Seed corrected 2026-08-22 so the watchdog stops
        # paging about a deliberate migration.
        "is_active": False,
    },
    {
        # Added 2026-05-18 — closes the manual-edit gap on user_profiles.mrr_current_usd
        # that surfaced during the primary-retainer cleanup. revenue_engine.calculate_mrr
        # (Stripe + manual retainer rows in revenue_events) is the source of truth;
        # sync_mrr.py upserts the result into user_profiles + writes today's
        # mrr_snapshots row. Runs 30 min after Stripe Revenue Sync so today's
        # Stripe events are already in revenue_events. Backstops the Vercel
        # snapshot-mrr cron which has been silently 401-ing since 2026-05-08.
        "name": "Daily MRR Auto-Sync",
        "description": "Compute MRR via revenue_engine + upsert user_profiles.mrr_current_usd + mrr_snapshots row",
        "schedule": "30 6 * * *",
        "action_type": "script_run",
        # 2026-06-06: dropped --json from args. With --json the script prints
        # an indented JSON block whose last stdout line is just "}" — the
        # scheduler wrapper grabs that as last_result and CC saw "Daily MRR
        # Auto-Sync: }" in Telegram. Non-JSON output is a single human line
        # ("sync_mrr [no-op] ...: $371 -> $371 ..."). The action handler's
        # last_result is now the readable summary.
        "action_config": {"script": "scripts/core/sync_mrr.py", "args": []},
        "is_active": True,
    },
    {
        "name": "Weekly MRR Report",
        "description": "Generate and log weekly MRR dashboard — ATLAS-OWNED reporting; disabled 2026-07-09 (Bravo does not report MRR). Re-home to Atlas (CFO-Agent) if CC wants the weekly digest back.",
        "schedule": "0 9 * * MON",
        "action_type": "revenue_report",
        "action_config": {"report_type": "mrr_weekly", "notify_channel": "telegram"},
        # 2026-07-09: toggled off in the live DB (row 68e3e96e) same day —
        # keep seed in lockstep so a reseed doesn't resurrect Bravo-sent
        # MRR digests. Data plumbing (Stripe Revenue Sync, Daily MRR
        # Auto-Sync) stays active — Atlas reads those tables.
        "is_active": False,
    },
    {
        "name": "Weekly Pipeline Review",
        "description": "Score all leads, identify hot prospects",
        "schedule": "0 10 * * MON",
        "action_type": "pipeline_review",
        "action_config": {"auto_score": True, "hot_threshold": 70},
        "is_active": True,
    },
    # RETIRED 2026-07-30, same root cause as 'Funnel Fast-Poll' below.
    # funnel_nurture.py touches exactly one table — funnel_leads (:248 select,
    # :267/:283/:294 update) — and nothing else, so with no writer feeding that
    # table there is nothing to nurture. It has matched 0 rows every weekday.
    #
    # The sharper reason to stop it: this job SENDS (Day-2 / Day-5 via
    # send_gateway). The single surviving funnel_leads row is CC's never-email
    # test account, currently status 'nurtured'. It is excluded only because
    # funnel_nurture.py:248 filters status in ("new","nurturing") — one status
    # flip and a live cron emails an address that must never be emailed. A job
    # with a send path and no legitimate audience is a loaded gun, not dead
    # weight.
    {
        "name": "Nurture Sequence Check",
        "description": "RETIRED 2026-07-30 — nurtures funnel_leads, which has had no writer since cc-funnel was retired 2026-06-18. Re-enable only once a live source writes that table again.",
        "schedule": "0 10 * * MON-FRI",
        "action_type": "nurture_check",
        "action_config": {"max_sends_per_run": 20},
        "is_active": False,
    },
    {
        "name": "Monthly Metrics Snapshot",
        "description": "Log monthly_metrics for the previous month",
        "schedule": "0 9 1 * *",
        "action_type": "monthly_snapshot",
        "action_config": {"tables": ["revenue_events", "leads", "content_calendar"]},
        # moved_to_atlas 2026-08-01 — same migration as Stripe Revenue Sync.
        "is_active": False,
    },
    {
        # Genome fitness loop (2026-07-09) — the verifiable-reward wire. Runs
        # the deterministic harness eval nightly at 03:30 (before Sleep Agent
        # at 04:00, so a red substrate is on record before consolidation) and
        # alerts CC's Telegram on any failing check. Closes the frontier gap
        # "the eval exists but feeds nothing" — the score now has a consumer.
        "name": "Bravo — Nightly Harness Eval",
        "description": "Deterministic 10-check harness eval (genome fitness) — Telegram alert on any red check",
        "schedule": "30 3 * * *",
        "action_type": "script_run",
        # NO --json here: the script_run wrapper stores the LAST stdout line as
        # last_result, and pretty JSON's last line is just "}" (the exact
        # 2026-06-06 Daily-MRR-Auto-Sync lesson). Plain mode ends with
        # "ALL GREEN — harness is turnkey for any runtime." on success and
        # exits 1 on any red check → notify_on nonzero_exit fires.
        "action_config": {"script": "scripts/harness_eval.py", "args": [], "notify_channel": "telegram", "notify_on": "nonzero_exit"},
        "is_active": True,
    },
    {
        # Broad weekly truth surface. Unlike the narrow nightly harness, this
        # also consumes fleet/pulse/inbox state and the complete Python suite.
        "name": "Weekly Full-Truth Health Digest",
        "description": "Sunday 07:00 ET — run self-audit, fleet health, and the complete Python suite; always send one private Telegram truth report.",
        "schedule": "0 7 * * SUN",
        "action_type": "script_run",
        # The child pytest gate has a 1200s hard stop. The scheduler must expire
        # after the child so its timeout diagnostic can be delivered and saved.
        "action_config": {
            "script": "scripts/weekly_truth_digest.py",
            "args": [],
            "timeout": 1500,
        },
        "is_active": True,
    },
    {
        # In the live DB since 2026-06 but was never seeded; a fresh-machine
        # reseed would silently lose it. Runs the Bravo/Atlas/Maven sweep.
        "name": "Cross-Agent Self-Improvement Sweep",
        "description": "Nightly cross-agent self-improvement sweep — mistakes/patterns digest across Bravo, Atlas, Maven",
        "schedule": "0 4 * * *",
        "action_type": "agent_self_improvement",
        "action_config": {},
        "is_active": True,
    },
    # SunBiz cron entries live in SunBiz-Agent/scripts/core/cron_registry.py
    # and seed into tenant_cron_jobs. Adding any here puts them in the
    # empire cron_jobs table where they leak into CC's /automations view.
    # 'Funnel Lead Sync' removed 2026-05-22 — overlapped with 'Funnel
    # Fast-Poll' below. Fast-Poll runs every 1 min and covers the same
    # funnel_leads source; the 5-min job was an older safety net.
    #
    # RETIRED 2026-07-30 — it was polling a table nobody writes to.
    #
    # `funnel_leads` was cc-funnel's table. cc-funnel was retired 2026-06-18 and
    # the poller was never repointed, so it has run 74,766 times against a table
    # holding ONE row (CC's never-email test account) for zero output. Verified
    # rather than assumed: a grep for `funnel_leads` across Business-Empire-Agent,
    # oasis-command-center and CMO-Agent finds reads and status UPDATEs but NOT A
    # SINGLE INSERT — and the Command Center, which serves the live funnel, never
    # mentions the table at all. It writes `tenant_records`.
    #
    # Nothing is lost by stopping. The push path already does this job better:
    # app/api/forms/submit/route.ts fires notifyOasisFunnelSubmission inline via
    # after() — Telegram ping AND welcome email, synchronously on submit, gated
    # to CC's exact tenant + slug. A poll can only ever be slower than the
    # request that created the row.
    #
    # Kept as a row (is_active False) rather than deleted so the history, the
    # run_count and this explanation stay attached to it.
    {
        "name": "Funnel Fast-Poll",
        "description": "RETIRED 2026-07-30 — polled funnel_leads, which has had no writer since cc-funnel was retired 2026-06-18. Superseded by the inline notify in oasis-command-center's form-submit route.",
        "schedule": "*/1 * * * *",
        "action_type": "funnel_fast_poll",
        "action_config": {"window_seconds": 120, "priority": True},
        "is_active": False,
    },
    {
        "name": "Daily Briefing Snapshot",
        "description": "Prep Table layer (brain/AGENTIC_OS_REFERENCE.md §3). Aggregates revenue/pipeline/health into state/snapshots/latest_briefing.json so ceo-briefing skill reads one JSON instead of running 4 engines live. Runnable manually until n8n handler exists.",
        "schedule": "0 6 * * *",
        "action_type": "snapshot_run",
        "action_config": {"script": "scripts/snapshots/briefing_snapshot.py", "args": []},
        "is_active": True,
    },
    {
        "name": "Weekly Qualified-Leads Snapshot",
        "description": "Saturday 22:00 ranking of leads scoring >= 60 by MRR potential. Output: state/snapshots/latest_leads.json. Revenue-Hunter agent cherry-picks from this instead of running opencli + scoring per session.",
        "schedule": "0 22 * * SAT",
        "action_type": "snapshot_run",
        "action_config": {"script": "scripts/snapshots/leads_snapshot.py", "args": ["--min-score", "60"]},
        # dormant since 2026-05-16 (last: qualified 0/0) — superseded by the OASIS
        # auto-score sweep + Pipeline board. Reversible: flip the live row.
        "is_active": False,
    },
    {
        "name": "Daily Client Alerts Snapshot",
        "description": "Daily 07:00 RED/ORANGE client extraction with risk factors + suggested actions. Output: state/snapshots/latest_client_alerts.json. Chief-of-Staff reads this instead of full health report.",
        "schedule": "0 7 * * *",
        "action_type": "snapshot_run",
        "action_config": {"script": "scripts/snapshots/client_alerts_snapshot.py", "args": []},
        "is_active": True,
    },
    {
        "name": "Daily State DB Backup",
        "description": "V6.8.3 nightly backup of empire_state.db + memory_index.db + site_reputation.db to state/backups/ with PRAGMA integrity_check verification. Keeps last 7. Uses sqlite3.Connection.backup() — consistent snapshot even in WAL mode.",
        "schedule": "0 3 * * *",
        "action_type": "script_run",
        "action_config": {"script": "scripts/state/backup_db.py", "args": ["backup", "--keep", "7"]},
        "is_active": True,
    },
    {
        # Added 2026-05-22 (V7.2) — sleep agent. Fixes the gap where
        # auto_dream.py only runs at graceful session end, so any session
        # killed abruptly (crash, hard close) loses its lessons. This runs
        # nightly regardless, reads last 24h of session_log + git activity,
        # asks Haiku what's worth remembering, appends to MISTAKES/PATTERNS/
        # DECISIONS with a git commit per entry. 7-day cooldown per topic
        # hash prevents the same lesson getting re-logged nightly.
        # Scheduled at 04:00 ET — one hour after Daily State DB Backup
        # (03:00) so the DB snapshot is fresh when the agent queries it.
        "name": "Bravo — Sleep Agent (Memory Consolidation)",
        "description": "Nightly 04:00 LLM-judged memory consolidation. Reads last 24h of session activity, identifies new lessons learned, appends to memory/MISTAKES.md, memory/PATTERNS.md, memory/DECISIONS.md with git-commit-per-entry. Uses Claude Haiku for cost efficiency. Fixes the abrupt-session-end gap where lessons evaporate.",
        "schedule": "0 4 * * *",
        "action_type": "script_run",
        "action_config": {"script": "scripts/bravo_sleep.py", "args": ["run"]},
        "is_active": True,
    },
    {
        # Added 2026-05-22 — meta-monitoring. Catches future broken crons
        # (like the Daily MRR Auto-Sync gap that sat silently failing
        # for days). Scans cron_jobs nightly for last_result starting with
        # ERROR / FAILED and Telegrams CC with a consolidated alert.
        # Self-monitoring: if THIS cron fails, its own FAILED row surfaces
        # in the dashboard's red-border treatment.
        # 2026-07-29: promoted from nightly (0 22 * * *) to hourly. A daily scan
        # means up to 24h of latency, which is exactly how the SSLKEYLOGFILE
        # outage ran unnoticed for a full working day — 31 failed inbox sweeps,
        # zero alerts. Hourly + notify.py's 1h dedup means a broken job surfaces
        # within the hour and then pings at most once an hour, not 12x a day.
        "name": "Bravo — Hourly Cron Health Check",
        "description": "Hourly scan of cron_jobs for last_result starting with ERROR or FAILED. Telegrams CC with the failing job name + snippet. Meta-cron: guards every other cron so silent breakage doesn't sit dead for days.",
        "schedule": "0 * * * *",
        "action_type": "script_run",
        "action_config": {"script": "scripts/core/cron_health_check.py", "args": ["--alert"]},
        "is_active": True,
    },
    {
        # Added 2026-07-29 — the closed review loop CC asked for.
        #
        # CodeRabbit / Vercel / CI review our pushes and email CC about it; that
        # signal used to die in a GitHub tab. The inbox sweep now detects those
        # notifications deterministically (email_playbook.detect_review_notification)
        # and queues (repo, pr) to tmp/review_harvest_queue.json; this job drains
        # the queue: harvest live thread state via gh, apply the fix, run the
        # repo's tests, push to the PR BRANCH, Telegram CC.
        #
        # NEVER merges, never pushes to main, never force-pushes, and skips
        # migrations / credentials / CI files / send_gateway / anything
        # money-adjacent (those escalate to CC). See scripts/review_fix.py.
        #
        # */15 not */5: each finding spawns a full Claude editing session plus a
        # test run, so a 5-minute cadence would overlap itself. review_loop
        # drains ONE PR per pass for the same reason.
        "name": "Bravo — Review Harvest",
        "description": "Every 15 min: drain the automated-review queue (CodeRabbit / Vercel / CI). Harvests UNRESOLVED review threads live via gh, applies the fix, runs tests, pushes to the PR branch, and Telegrams CC. Never merges or touches main.",
        "schedule": "*/15 * * * *",
        "action_type": "script_run",
        # timeout: a fix is a Claude editing session plus the target repo's full
        # test suite. The 300s script_run default would SIGKILL it mid-fix and
        # could leave uncommitted edits in a client repo. review_loop drains ONE
        # PR per pass, so 1500s is a ceiling, not an expectation.
        "action_config": {"script": "scripts/review_loop.py",
                          "args": ["--once", "--json"], "timeout": 1500},
        # Retired 2026-08-16 (CC). It only pays off on repos with active PR
        # review and there were no open PRs, so it was draining a slot every 15
        # minutes to do nothing. It also depends on a `gh` login that had
        # expired, which meant it was failing silently rather than idling.
        # Re-enable with `cron_engine.py toggle` if PR review becomes a habit.
        #
        # 2026-08-27 — BOTH RETIREMENT REASONS HAVE NOW REVERSED. Recorded here
        # rather than acted on, because re-enabling is CC's call:
        #   * "there were no open PRs" — there are now 21 open peer PRs in
        #     oasis-command-center touching Bravo-owned or contested surfaces.
        #   * "a `gh` login that had expired" — verified working 2026-08-27:
        #     review_harvest.py against PR #340 returned live thread state and
        #     correctly reported the one unresolved finding.
        # PR review has become a habit. Recommend toggling this back on.
        "is_active": False,
    },
    {
        # Added 2026-08-27. The peer-review half of the coordination contract:
        # APEX opens PRs against surfaces the ownership map assigns to Bravo,
        # and until now nothing looked at them on a schedule.
        #
        # SCANS ONLY — it never publishes a verdict unattended. A verdict posted
        # under Bravo's name is an outward effect the peer acts on, and a wrong
        # one spends the credibility of the whole channel. The scan says what is
        # waiting; the review itself is run deliberately.
        "name": "Bravo — Cross-Agent Review Scan",
        "description": "Twice daily: list APEX PRs touching Bravo-owned or contested "
                       "surfaces (scripts/cross_agent_review.py scan). Read-only. "
                       "Verdicts are published deliberately with `review --pr`, never on a timer.",
        "schedule": "0 9,17 * * *",
        "action_type": "script_run",
        "action_config": {"script": "scripts/cross_agent_review.py",
                          "args": ["scan", "--json"], "timeout": 600},
        # Inactive on arrival. Seeding the shared cron_jobs registry is a
        # production-scheduling mutation and CC reviews new entries first
        # (CLAUDE.md). Toggle on with `cron_engine.py toggle` after review.
        "is_active": False,
    },
    # 'Bravo — Override Queue Cleanup' removed 2026-05-22 along with the
    # entire exec_override approval-request system. exec_guard still blocks
    # destructive commands; it just doesn't create DB rows asking for human
    # approval. The block itself IS the protection.
    {
        # Added 2026-08-28. The eval suites had not run since 2026-06-10 —
        # accuracy was unmeasured for eleven weeks, and the first run after
        # building a runner found `routing` had drifted 100% -> 77.8%. Nothing
        # surfaced that, because nothing was looking.
        #
        # Only BASELINED suites can fail this job. routing_nl is deliberately
        # red (0.333) and `mistakes` is entirely rubric-scored, so gating on
        # them would make the alert permanently red and therefore ignored.
        #
        # Paging contract: scheduler.py ignores notify_on. A job pages CC by
        # exiting non-zero AND printing a line starting "ERROR:" — run_suites.py
        # does both. --json keeps the LAST stdout line a single compact object,
        # since scheduler stores out[-1][:200] as last_result.
        "name": "Weekly Eval Suites",
        "description": "Sunday 05:00 ET — score the eval suites against baselines.json and write evals/reports/. Pages only on a baselined suite regressing or a suite erroring; un-baselined suites are reported, not gated.",
        "schedule": "0 5 * * SUN",
        "action_type": "script_run",
        "action_config": {"script": "evals/run_suites.py", "args": ["--json"],
                          "timeout": 600},
        "is_active": True,
    },
    {
        # Added 2026-08-28. RULE -1 makes FTS retrieval the preferred path over
        # whole-file reads, so the whole retrieval-first design rests on this
        # index — and nothing rebuilt it. memory_index.db appeared in this file
        # only for BACKUP, so the index was only ever as fresh as the last
        # manual run (2026-08-24 when found). build() is incremental by default.
        "name": "Daily Memory Index Rebuild",
        "description": "Daily 04:30 ET — incremental FTS/semantic reindex of the vault so memory_retriever queries reflect the current state of memory/ and brain/.",
        "schedule": "30 4 * * *",
        "action_type": "script_run",
        "action_config": {"script": "scripts/core/memory_retriever.py", "args": ["build"],
                          "timeout": 900},
        "is_active": True,
    },
    {
        # Added 2026-06-06 (Phase 4 of system re-engineering). After the
        # one-shot tmp/ purge that recovered 6.0 GB, this keeps tmp/ bounded.
        # Allowlist preserves pm2-*.log, events_offline.jsonl, *.lock*, *.pid,
        # *.heartbeat, *.env. Anything else >30 days old gets purged.
        "name": "Weekly tmp/ Hygiene",
        "description": "Sunday 03:00 ET — purge orphan files in tmp/ older than 30 days. Allowlists active lock/log/env files. Recovered 6.0 GB on the initial run; this prevents drift back to that state.",
        "schedule": "0 3 * * SUN",
        "action_type": "script_run",
        "action_config": {"script": "scripts/utilities/tmp_hygiene.py", "args": ["--apply", "--json"]},
        "is_active": True,
    },
    {
        # Added 2026-06-06. Belt-and-braces over the SessionStart-fired
        # rotate_logs.py (12h idempotency). If CC goes a few days without
        # opening a session, this still keeps state/*.log under 5 MB.
        # --force bypasses the 12h stamp; rotation itself only fires on
        # files that exceeded MAX_BYTES, so daily runs are cheap when idle.
        "name": "Daily Log Rotation Audit",
        "description": "Daily 04:00 ET — force-run rotate_logs.py to keep state/*.log under 5 MB even when SessionStart hasn't fired in days. Discovered 2026-06-06: secret_access.log had reached 16 MB unrotated.",
        "schedule": "0 4 * * *",
        "action_type": "script_run",
        "action_config": {"script": "scripts/hooks/rotate_logs.py", "args": ["--force"]},
        "is_active": True,
    },
    {
        # Added 2026-06-06. event_bus.publish() writes to tmp/events_offline.jsonl
        # when Supabase is unreachable. Without a drain job, queued events
        # sit forever — observable cross-agent state silently degrades.
        # Every 10 min is a sweet spot: low cost when queue is empty, fast
        # recovery after an outage.
        "name": "Event Bus Offline Drain",
        "description": "Every 10 min — replay tmp/events_offline.jsonl into Postgres agent_events. Drains the V6 Apex offline-fallback queue so transient Supabase outages don't lose cross-agent events.",
        "schedule": "*/10 * * * *",
        "action_type": "script_run",
        "action_config": {"script": "scripts/core/event_bus.py", "args": ["drain"]},
        "is_active": True,
    },
    {
        # Added 2026-08-01 — closes the inventory-drift gap found in the
        # entry-point audit: the six root files quote hard counts (skills,
        # scripts, cron jobs, workflows, subagents, MCP servers) that went
        # stale between hand-syncs. generate_inventory.py rewrites
        # brain/INVENTORY.md with live counts; entry points now treat their
        # hard numbers as a snapshot and point at INVENTORY.md.
        "name": "Monthly Inventory Sync",
        "description": "Monthly 03:00 on the 1st — regenerate brain/INVENTORY.md with live repo counts (skills, scripts, SEED_JOBS, workflows, subagents, MCP servers) so entry-point inventory sections have a current source of truth.",
        "schedule": "0 3 1 * *",
        "action_type": "script_run",
        "action_config": {"script": "scripts/core/generate_inventory.py", "args": []},
        "is_active": True,
    },
    {
        # Added 2026-08-24 — the standing safety net the Kimi-receipt gap
        # proved was missing. receipts_audit.py reconcile re-scans the mailbox
        # on a rolling 45-day window and reconciles it against the Receipts/*
        # label tree. Only sender-identity-confident tiers auto-hand-off to
        # Atlas (billing-local: / vendor+subject: / forward:); subject-money
        # matches land in one Telegram review list instead, so a newsletter
        # quoting "$2,000" can never auto-book. Exit contract mirrors
        # weekly_truth_digest: nonzero only when the reconciliation itself
        # could not run or deliver its summary — findings are content.
        "name": "Monthly Receipts Reconciliation",
        "description": "Monthly 04:23 on the 2nd — reconcile the mailbox against Receipts/* labels (rolling 45d), auto-hand confident financial gaps to Atlas, one Telegram summary for anything held for review.",
        "schedule": "23 4 2 * *",
        "action_type": "script_run",
        # notify_on added when two concurrent sessions each wrote this seed
        # (2026-08-24) and the definitions were merged: the scheduler pages on
        # a nonzero exit, which under the delivery-based contract means THE
        # RECONCILER broke — findings never exit nonzero.
        "action_config": {"script": "scripts/receipts_audit.py", "args": ["reconcile"], "timeout": 900,
                          "notify_channel": "telegram", "notify_on": "nonzero_exit"},
        "is_active": True,
    },
    {
        # Added 2026-08-14. CC: "I should be able to click on one of these videos
        # and then manually post it to all the social media channels via our API
        # key that we have connected."
        #
        # The Command Center runs on Vercel and cannot call the only sanctioned
        # publisher — CMO-Agent/publishers/base.publish() is Python, runs
        # send_gateway first (killswitch, daily caps, audit trail) and needs
        # credentials that live on this machine. So the app records intent in
        # marketing_publish_intent and this drains it, here, where the gateway is.
        #
        # Every minute because a click should feel like a click. The drain claims
        # each intent with a compare-and-set, so an overlapping run cannot publish
        # the same reel twice — there is no unsending.
        # Added 2026-08-16. CC, looking at a Library that showed 41 assets "in
        # review" while five of them were live on Instagram: "we already have
        # posted the unpaved mile... some of it's not taken account for
        # correctly... it should automatically update itself."
        #
        # marketing_asset and post_analytics are filled by two different roads —
        # produced creative arrives via library_sync, live numbers arrive from
        # Zernio — and the id-based join between them only fires for posts Zernio
        # itself created. Everything Maven produced had no Zernio id, so the
        # Library could not tell posted from unposted and defaulted to "needs a
        # verdict" for all of it. The one-off backfill linked 14 assets across 54
        # analytics rows; this keeps it true without anyone remembering to run it.
        #
        # Hourly, because post_analytics itself is polled rather than pushed —
        # linking more often than the numbers arrive buys nothing. Idempotent and
        # a no-op once everything is linked, so a missed run costs nothing but a
        # later refresh.
        "name": "Library Post Linker",
        "description": "Hourly — link founders Library assets to the posts that actually went out (hook-to-caption match), stamping published_at and the real platform list. Precision-first: an ambiguous or multi-day match is reported, never guessed.",
        "schedule": "17 * * * *",
        "action_type": "script_run",
        "action_config": {"script": "scripts/link_library_to_posts.py", "args": ["--execute"], "timeout": 600},
        "is_active": True,
    },
    {
        "name": "Marketing Publish Drain",
        "description": "Every minute — publish assets the founders Library queued in marketing_publish_intent, through CMO-Agent's send_gateway (killswitch, daily caps, audit trail). No-ops when the queue is empty.",
        "schedule": "* * * * *",
        "action_type": "script_run",
        # 900s, not the 300s default: publishing a 10 MB reel to five networks
        # legitimately takes minutes, and a kill mid-publish is what strands an
        # intent in  — the state the reaper then has to rescue.
        "action_config": {"script": "scripts/marketing_publish_drain.py", "args": [], "timeout": 900},
        "is_active": True,
    },
    {
        # Added 2026-08-14. The Train Maven drop-zone enqueued links into
        # marketing_corpus and NOTHING consumed the queue — every link CC or
        # Adon dropped would have sat at "Waiting" forever, which is worse than
        # a disabled button because it looks like it worked.
        #
        # Five minutes, not one: each link is a real fetch (Firecrawl, escalating
        # to CloakBrowser) plus a model call. There is no hurry, and a tighter
        # loop would just collide with itself on a slow scrape.
        "name": "Training Corpus Ingest",
        "description": "Every 5 minutes — fetch and analyse links dropped in Train Maven, write style exemplars to CMO-Agent/brain/exemplars/. No-ops when the queue is empty.",
        "schedule": "*/5 * * * *",
        "action_type": "script_run",
        "action_config": {"script": "scripts/ingest_training_link.py", "args": [], "timeout": 900},
        "is_active": True,
    },
    {
        # Added 2026-08-14. The Performance tab was a greyed chip captioned
        # "Phase 5" while Zernio had been collecting the numbers the whole time —
        # 68 of 79 published posts carry non-zero metrics nobody could see.
        #
        # A POLLER, not a webhook: Zernio's /v1/webhooks path returns the
        # dashboard HTML rather than an API, so there is no event schema to parse
        # and no way to register an endpoint. Hourly because these are vanity
        # metrics on a slow clock — the networks refresh every few hours, so a
        # tighter loop would spend rate limit re-reading the same numbers.
        "name": "Post Analytics Sync",
        "description": "Hourly — pull per-post, per-platform metrics from Zernio into post_analytics so the founders Performance tab has real numbers.",
        "schedule": "17 * * * *",
        "action_type": "script_run",
        "action_config": {"script": "scripts/sync_post_analytics.py", "args": [], "timeout": 600},
        "is_active": True,
    },
    {
        # Added 2026-08-21 — the V8.6 carousel pivot. Until now, the job that
        # decides WHAT posts and HOW OFTEN was a Windows Task Scheduler task on
        # CC's box (MavenSchedulePosts) and appeared in NO cron table. That is
        # why the Automations tab could not tell CC the feed had been posting
        # 3x/day since 08-02 while he believed it was 1x. Registering it here is
        # what makes the tab honest about the feed.
        #
        # DAILY ON PURPOSE — do NOT "correct" this to "0 8 */2 * *". The run
        # happens every day; the every-2-days CADENCE is derived from the posted
        # ledger by _is_posting_day() in CMO-Agent/scripts/schedule_posts.py.
        # Encoding the cadence in the trigger as well would give one rule two
        # definitions, and they drift the first time a run is missed.
        #
        # FIRST CROSS-REPO SEED_JOB. scheduler.py's run_script_action() does
        # PROJECT_ROOT / script, which pathlib resolves to an absolute path
        # unchanged, then forces cwd to Bravo's root and IGNORES any "cwd" key.
        # That is safe *for this script specifically*: run_posting_cron.py
        # absolutizes every step path against its own ROOT and passes cwd=ROOT
        # to each subprocess, so it never reads the inherited cwd. Do not copy
        # this pattern for a cwd-dependent script — add a Bravo-side wrapper
        # instead, like the four Maven jobs above.
        #
        # 3600s is the scheduler's ceiling (SCRIPT_RUN_MAX_TIMEOUT) and it is
        # needed: a --dry-run measured 197s while SKIPPING the authoring and
        # render steps, so a real run has no chance under the 300s default —
        # it would be killed mid-render, which is exactly the state that
        # strands a half-written deck.
        "name": "Maven — Carousel Post",
        "description": (
            "Daily 08:00 — authors carousel specs, renders and queues them, then books ONE "
            "post every SECOND day at 17:00 UTC to Instagram, LinkedIn and Threads. The "
            "cadence decides whether a given day books, not this schedule. Also delivers "
            "finished renders to CC's Telegram and mirrors pieces into the founders Library."
        ),
        "schedule": "0 8 * * *",
        "action_type": "script_run",
        "action_config": {
            "script": str(SIBLING_REPOS["maven"] / "scripts" / "run_posting_cron.py"),  # path-drift-ok: CMO-Agent sibling path
            "args": [],
            "timeout": 3600,
        },
        "is_active": True,
    },
]


# -- Cron schedule parsing (next-run approximation) ----------------------------

def _next_run_approx(schedule: str) -> Optional[str]:
    """
    Best-effort approximation of the next UTC run time for a 5-field cron expression.

    Delegates to schedule_helpers.next_local_cron_run_iso (2026-05-17), which
    parses the expression in CC's local tz (America/Toronto by default) so
    "0 8 * * *" lands at 08:00 ET, not 08:00 UTC. The old in-file UTC parser
    fired Aura's 8am Pow Wow at 04:00 ET on Victoria Day weekend. Kept the
    function signature + name for callers in this module + cron_dispatcher.
    """
    try:
        # Local import: schedule_helpers is sibling-pathed under scripts/, and
        # cron_engine is sometimes imported by callers outside of scripts/.
        from pathlib import Path
        import sys as _sys
        _here = Path(__file__).resolve().parent
        if str(_here) not in _sys.path:
            _sys.path.insert(0, str(_here))
        from schedule_helpers import next_local_cron_run_iso
        return next_local_cron_run_iso(schedule)
    except Exception:
        return None


# -- Formatting helpers --------------------------------------------------------

def fmt_date(iso_str: str | None) -> str:
    """Format an ISO timestamp to a readable short datetime."""
    if not iso_str:
        return "-"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return iso_str[:16] if iso_str else "-"


def truncate(text: str, max_len: int = 40) -> str:
    if not text:
        return ""
    return text[: max_len - 1] + "..." if len(text) > max_len else text


# -- Command handlers ----------------------------------------------------------

def cmd_list(client, args, output_json: bool) -> None:
    """List cron jobs with optional active-only filter."""
    query = client.table("cron_jobs").select("*")

    if args.active_only:
        query = query.eq("is_active", True)

    query = query.order("created_at", desc=False)
    result = query.execute()
    jobs = result.data or []

    if output_json:
        print(json.dumps(jobs, indent=2, default=str))
        return

    if not jobs:
        print("No cron jobs found.")
        return

    col_id      = 8
    col_name    = 28
    col_sched   = 18
    col_type    = 20
    col_active  = 7
    col_runs    = 6
    col_last    = 16

    header = (
        f"{'ID':<{col_id}}  "
        f"{'NAME':<{col_name}}  "
        f"{'SCHEDULE':<{col_sched}}  "
        f"{'TYPE':<{col_type}}  "
        f"{'ACTIVE':<{col_active}}  "
        f"{'RUNS':>{col_runs}}  "
        f"{'LAST RUN':<{col_last}}"
    )
    sep = "-" * len(header)
    print(sep)
    print(header)
    print(sep)

    for job in jobs:
        job_id   = str(job.get("id", ""))[:col_id]
        name     = truncate(job.get("name", "-"), col_name)
        schedule = truncate(job.get("schedule", "-"), col_sched)
        jtype    = truncate(job.get("action_type", "-"), col_type)
        active   = "YES" if job.get("is_active") else "no"
        runs     = str(job.get("run_count") or 0)
        last_run = fmt_date(job.get("last_run_at"))

        print(
            f"{job_id:<{col_id}}  "
            f"{name:<{col_name}}  "
            f"{schedule:<{col_sched}}  "
            f"{jtype:<{col_type}}  "
            f"{active:<{col_active}}  "
            f"{runs:>{col_runs}}  "
            f"{last_run:<{col_last}}"
        )

    print(sep)
    active_count = sum(1 for j in jobs if j.get("is_active"))
    print(f"  {len(jobs)} job(s) - {active_count} active")


def cmd_add(client, args, output_json: bool) -> None:
    """Add a new cron job definition."""
    try:
        config = json.loads(args.config) if args.config else {}
    except json.JSONDecodeError:
        print("ERROR: --config must be valid JSON.", file=sys.stderr)
        sys.exit(1)

    now = datetime.now(timezone.utc).isoformat()
    next_run = _next_run_approx(args.schedule)

    payload: dict = {
        "name": args.name,
        "schedule": args.schedule,
        "action_type": args.type,
        "action_config": config,
        "is_active": True,
        "run_count": 0,
        "created_at": now,
        # cron_jobs.tenant_id is NOT NULL; cmd_seed always stamped it but
        # cmd_add never did, so every `add` failed 23502 (latent since the
        # column landed — caught 2026-07-09 wiring the harness-eval cron).
        "tenant_id": CC_EMPIRE_TENANT_ID,
    }
    if args.description:
        payload["description"] = args.description
    if next_run:
        payload["next_run_at"] = next_run

    result = client.table("cron_jobs").insert(payload).execute()
    job = result.data[0] if result.data else {}

    if output_json:
        print(json.dumps(job, indent=2, default=str))
        return

    print("Cron job added.")
    print(f"  ID:          {job.get('id', '?')}")
    print(f"  Name:        {job.get('name')}")
    print(f"  Schedule:    {job.get('schedule')}")
    print(f"  Type:        {job.get('action_type')}")
    print(f"  Next run:    {fmt_date(job.get('next_run_at'))}")
    print("  Active:      yes")


def cmd_toggle(client, args, output_json: bool) -> None:
    """Toggle a cron job's is_active state."""
    result = client.table("cron_jobs").select("id, name, is_active").eq("id", args.job_id).execute()
    if not result.data:
        print(f"ERROR: Cron job '{args.job_id}' not found.", file=sys.stderr)
        sys.exit(1)

    job = result.data[0]
    new_state = not job.get("is_active", False)

    updated_result = (
        client.table("cron_jobs")
        .update({"is_active": new_state})
        .eq("id", args.job_id)
        .execute()
    )
    updated = updated_result.data[0] if updated_result.data else {}

    if output_json:
        print(json.dumps(updated, indent=2, default=str))
        return

    state_label = "enabled" if new_state else "disabled"
    print(f"Cron job {state_label}: {job.get('name', args.job_id)}")
    print(f"  ID:     {args.job_id}")
    print(f"  Active: {'yes' if new_state else 'no'}")


def cmd_run(client, args, output_json: bool) -> None:
    """Mark a cron job as run: update last_run_at and increment run_count."""
    result = client.table("cron_jobs").select("*").eq("id", args.job_id).execute()
    if not result.data:
        print(f"ERROR: Cron job '{args.job_id}' not found.", file=sys.stderr)
        sys.exit(1)

    job = result.data[0]
    now = datetime.now(timezone.utc).isoformat()
    new_count = (job.get("run_count") or 0) + 1
    next_run = _next_run_approx(job.get("schedule", ""))

    updates: dict = {
        "last_run_at": now,
        "run_count": new_count,
        "last_result": args.result or "ok",
    }
    if next_run:
        updates["next_run_at"] = next_run

    updated_result = client.table("cron_jobs").update(updates).eq("id", args.job_id).execute()
    updated = updated_result.data[0] if updated_result.data else {}

    if output_json:
        print(json.dumps(updated, indent=2, default=str))
        return

    print(f"Cron job marked as run: {job.get('name', args.job_id)}")
    print(f"  Run count:  {new_count}")
    print(f"  Last run:   {fmt_date(now)}")
    print(f"  Next run:   {fmt_date(next_run)}")
    print(f"  Result:     {updates['last_result']}")


def _machine_name() -> str:
    import os
    import socket
    return os.environ.get("COORD_MACHINE") or socket.gethostname()


def filter_by_machine(jobs: list) -> tuple[list, list]:
    """Split jobs into (mine, someone-elses) by `owner_machine`.

    `cron_jobs` is a SHARED Turso registry. Once APEX's machine polls it too,
    an unfiltered `due` means BOTH engines fire the same job — two digests, or
    worse, two sends. Double-sending is not recoverable by retry logic, so the
    filter lives here, at the one place that decides what runs.

    owner_machine IS NULL means unpinned: any engine may run it. That keeps
    every pre-existing row behaving exactly as before.
    """
    me = _machine_name()
    mine, theirs = [], []
    for j in jobs:
        owner = (j.get("owner_machine") or "").strip()
        (mine if not owner or owner == me else theirs).append(j)
    return mine, theirs


def cmd_due(client, args, output_json: bool) -> None:
    """Show active jobs whose next_run_at is now or overdue."""
    now_iso = datetime.now(timezone.utc).isoformat()

    result = (
        client.table("cron_jobs")
        .select("*")
        .eq("is_active", True)
        .lte("next_run_at", now_iso)
        .not_.is_("next_run_at", "null")
        .order("next_run_at", desc=False)
        .execute()
    )
    jobs, other_machine = filter_by_machine(result.data or [])
    if other_machine:
        # Say it out loud on BOTH output paths. A silently-skipped job looks
        # identical to a job that was never due. The JSON path is the one
        # automation reads, so hiding it there is where a job pinned to a stale
        # or offline hostname disappears from the fleet entirely — nobody is
        # running it and nothing reports that (Codex adversarial review,
        # 2026-08-27). JSON consumers get the skipped set explicitly.
        if output_json:
            print(json.dumps({
                "machine": _machine_name(),
                "due": jobs,
                "skipped_other_machine": [
                    {"name": j.get("name"), "owner_machine": j.get("owner_machine"),
                     "next_run_at": j.get("next_run_at")} for j in other_machine],
            }, indent=2, default=str))
            return
        print(f"[cron] skipping {len(other_machine)} job(s) pinned to another machine "
              f"(this machine is {_machine_name()}): "
              + ", ".join(f"{j.get('name','?')}->{j.get('owner_machine')}"
                          for j in other_machine[:5]))

    if output_json:
        print(json.dumps(jobs, indent=2, default=str))
        return

    if not jobs:
        print("No cron jobs are due right now.")
        return

    now_display = fmt_date(now_iso)
    print(f"Due now (as of {now_display}):\n")
    for job in jobs:
        next_run = fmt_date(job.get("next_run_at"))
        overdue = " [OVERDUE]" if (job.get("next_run_at") or "") < now_iso else ""
        print(f"  {next_run}{overdue}")
        print(f"    [{str(job.get('id', ''))[:8]}] {job.get('name', '-')} - {job.get('action_type', '-')}")
        if job.get("description"):
            print(f"    {job['description']}")
        print()

    print(f"  {len(jobs)} job(s) due.")


CC_EMPIRE_TENANT_ID = "ef8d389e-3f15-43f2-ae00-3660f69a1452"


def _normalize_dash(s: str) -> str:
    """Fold em/en/minus dashes to ASCII '-' and squash whitespace.

    Keep in lockstep with harness_eval._normalize_dash — that copy is what
    decides whether the nightly eval recognises its OWN cron row.
    """
    if not s:
        return ""
    for dash in ("—", "–", "‒", "−", "‐", "‑", "­"):
        s = s.replace(dash, "-")
    return " ".join(s.split())


def cmd_seed(client, args, output_json: bool) -> None:
    """Seed registered automation jobs (skips existing by normalized name).

    Migration 084 made cron_jobs.tenant_id NOT NULL. Every seed row written
    here is empire-scoped to CC's tenant by construction — SunBiz / Atlas
    / other-tenant crons live in tenant_cron_jobs. ``--only`` is the safe path
    for adding one newly approved production schedule without inserting other
    definitions that happen to be absent on that machine.
    """
    existing_result = client.table("cron_jobs").select("name").execute()
    # Dash-normalized so a row registered as "Bravo - X" is recognised as the
    # same job as SEED_JOBS' "Bravo — X". Exact matching here would not error —
    # it would INSERT A DUPLICATE cron, and the fleet would then run that job
    # twice a night with two rows to keep green. Mirrors
    # harness_eval._normalize_dash (kept as a local 5-liner rather than an
    # import: cron_engine is loaded by the always-on scheduler and should not
    # pull in the eval to compare two strings).
    existing_names: set[str] = {
        _normalize_dash(r["name"]) for r in (existing_result.data or [])
    }

    only = getattr(args, "only", None)
    definitions = SEED_JOBS
    if only:
        wanted = _normalize_dash(only).casefold()
        definitions = [
            definition for definition in SEED_JOBS
            if _normalize_dash(definition["name"]).casefold() == wanted
        ]
        if not definitions:
            print(f"ERROR: no SEED_JOBS definition named {only!r}", file=sys.stderr)
            raise SystemExit(2)

    inserted: list[dict] = []
    skipped: list[str] = []

    now = datetime.now(timezone.utc).isoformat()

    for definition in definitions:
        if _normalize_dash(definition["name"]) in existing_names:
            skipped.append(definition["name"])
            continue

        next_run = _next_run_approx(definition["schedule"])
        payload = {
            **definition,
            "tenant_id": CC_EMPIRE_TENANT_ID,
            "run_count": 0,
            "created_at": now,
        }
        # Seed definitions may carry METADATA keys that are not cron_jobs
        # columns — `daemon_backed` (read by cron_health_check to watch the
        # PM2 process behind a deliberately-disarmed row) was the first. The
        # `**definition` spread would hand them to INSERT as columns and a
        # FRESH seed would die with "no such column" — latent today only
        # because every current row already exists and is skipped by name.
        # Strip metadata here, at the single point where seeds become rows,
        # so the next metadata key someone adds cannot re-create the trap.
        for meta_key in SEED_METADATA_KEYS:
            payload.pop(meta_key, None)
        if next_run:
            payload["next_run_at"] = next_run

        result = client.table("cron_jobs").insert(payload).execute()
        if result.data:
            inserted.append(result.data[0])

    if output_json:
        print(json.dumps({"inserted": inserted, "skipped": skipped}, indent=2, default=str))
        return

    if inserted:
        print(f"Seeded {len(inserted)} cron job(s):\n")
        for job in inserted:
            print(f"  [{str(job.get('id', ''))[:8]}] {job.get('name', '-')}")
            print(f"    Schedule: {job.get('schedule', '-')}  Type: {job.get('action_type', '-')}")
            print(f"    Next run: {fmt_date(job.get('next_run_at'))}")
            print()
    else:
        print("No new jobs inserted.")

    if skipped:
        print(f"Skipped {len(skipped)} already-existing job(s):")
        for name in skipped:
            print(f"  - {name}")


# -- Argument parser -----------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cron_engine.py",
        description="Cron Engine - Business Automation Job Manager (Turso-backed)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s list
  %(prog)s list --active-only
  %(prog)s add --name "Daily Content Post" --schedule "0 9 * * *" --type content_post --config '{"pillar": "ceo_log", "platform": "x"}'
  %(prog)s toggle <job_id>
  %(prog)s run <job_id>
  %(prog)s run <job_id> --result "error: timeout"
  %(prog)s due
  %(prog)s seed
  %(prog)s seed --only "Weekly Full-Truth Health Digest"
  %(prog)s --json list
  %(prog)s --json due
        """,
    )

    parser.add_argument(
        "--json",
        dest="output_json",
        action="store_true",
        help="Output raw JSON for agent consumption",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # -- list ------------------------------------------------------------------
    p_list = subparsers.add_parser("list", help="List all cron jobs")
    p_list.add_argument(
        "--active-only",
        dest="active_only",
        action="store_true",
        help="Only show active jobs",
    )

    # -- add -------------------------------------------------------------------
    p_add = subparsers.add_parser("add", help="Add a new cron job definition")
    p_add.add_argument("--name", required=True, help="Human-readable job name")
    p_add.add_argument("--schedule", required=True, help="5-field cron expression (e.g. '0 9 * * *')")
    p_add.add_argument("--type", required=True, dest="type", help="action_type identifier (e.g. content_post)")
    p_add.add_argument("--config", default="{}", help="JSON action_config object")
    p_add.add_argument("--description", help="Human-readable description of what this job does")

    # -- toggle ----------------------------------------------------------------
    p_toggle = subparsers.add_parser("toggle", help="Enable or disable a cron job")
    p_toggle.add_argument("job_id", help="Cron job UUID")

    # -- run -------------------------------------------------------------------
    p_run = subparsers.add_parser("run", help="Mark a job as run (updates last_run_at and run_count)")
    p_run.add_argument("job_id", help="Cron job UUID")
    p_run.add_argument("--result", help="Result string to store in last_result (default: 'ok')")

    # -- due -------------------------------------------------------------------
    subparsers.add_parser("due", help="Show active jobs that are due or overdue right now")

    # -- seed ------------------------------------------------------------------
    p_seed = subparsers.add_parser("seed", help="Seed registered business automation jobs")
    p_seed.add_argument(
        "--only",
        help="Seed exactly one definition by name (recommended for production changes)",
    )

    return parser


# -- Entry point ---------------------------------------------------------------

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    output_json: bool = getattr(args, "output_json", False)

    if not args.command:
        parser.print_help()
        sys.exit(1)

    env_vars = load_env()
    client = get_client(env_vars)

    dispatch = {
        "list":   cmd_list,
        "add":    cmd_add,
        "toggle": cmd_toggle,
        "run":    cmd_run,
        "due":    cmd_due,
        "seed":   cmd_seed,
    }

    handler = dispatch.get(args.command)
    if handler:
        try:
            handler(client, args, output_json)
        except Exception as e:
            if output_json:
                print(json.dumps({"error": str(e)}, indent=2))
            else:
                print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
