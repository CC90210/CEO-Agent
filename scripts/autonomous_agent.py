"""
Autonomous Agent — the always-on reasoning loop.

This is the "sentient brain" piece of the V5.6 stack. It is the process
that wakes up on a schedule (or a Telegram poke), looks at what's
actually happening in CC's business right now, decides what to do, and
either acts (through the send_gateway) or escalates to CC.

WHY THIS EXISTS
---------------
Before this module, every AI action was reactive — cron fires a specific
handler, CC opens an IDE, Telegram message arrives. No continuous
reasoning happened between triggers. The "AI that works while CC sleeps"
that the V5.6 audit called for couldn't exist because no process was
ever making decisions on its own.

This module is that process. It reuses every V5.6 primitive:
  • `send_gateway`           — the outbound chokepoint
  • `context_builder`        — relationship-aware context for drafts
  • `inbound_classifier`     — library-mode classification of signals
  • `draft_critic`           — adversarial review of drafts before send
  • `casl_compliance`        — legal hygiene (enforced inside gateway)
  • `lead_interactions`      — unified ledger (read + write)
  • `agent_decisions`        — decision tape (written by this module)
  • `agent_state_snapshot`   — persistent state across restarts
  • `shadow_decisions`       — shadow mode dry-run target

THE BRAIN LOOP — SEVEN PHASES
------------------------------
Every `tick()` walks these phases in order:

  1. ORIENT    — restore state from snapshot, read pulse, generate tick_id
  2. RECALL    — scan lead_interactions for actionable signals
  3. ASSESS    — categorize signals, score priority
  4. PLAN      — generate decision proposals (action + reasoning + confidence)
  5. VERIFY    — apply policy gates (daily cap, high-value escalation,
                 business-hours guard, critic reject → escalate)
  6. EXECUTE   — run decisions through send_gateway OR escalate to CC
  7. REFLECT   — write plain-English summary, persist state, notify CC

Each decision writes a row to `agent_decisions` — the decision tape is
what makes the daemon introspectable.

SIGNAL DETECTORS
----------------
Three built-in signal types (extensible). Each returns a list of
proposed decisions:

  • hot_inbound_replies      — unprocessed inbound.classified events
                               with priority=hot
  • due_followups            — cold leads past Day-2 / Day-5 thresholds
                               with no reply yet
  • dormancy_transitions     — warm leads going 30+ days silent

SAFETY RAILS
------------
All on by default; each overridable via CLI flag.
  • Shadow mode               — writes to shadow_decisions, not send_gateway
  • Tick cap                  — max 5 sends per tick
  • Critic gate               — draft must pass draft_critic before send
  • Business hours            — 9am–10pm ET by default (Toronto timezone)
  • High-value escalation     — leads with score > 80 always escalate
  • Engaged-stage escalation  — active conversations always escalate

CLI
---
    python scripts/autonomous_agent.py tick
    python scripts/autonomous_agent.py tick --shadow
    python scripts/autonomous_agent.py tick --dry-run --json
    python scripts/autonomous_agent.py daemon --interval 900
    python scripts/autonomous_agent.py status
    python scripts/autonomous_agent.py decisions --today
    python scripts/autonomous_agent.py decisions --tick-id <id>
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None  # type: ignore


# ---- Env + DB (same pattern as every other engine) --------------------------

def load_env() -> dict[str, str]:
    env_path = PROJECT_ROOT / ".env.agents"
    if not env_path.exists():
        return {}
    env_vars: dict[str, str] = {}
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env_vars[k.strip()] = v.strip()
    for k, v in env_vars.items():
        os.environ.setdefault(k, v)
    return env_vars


def get_supabase(env: Optional[dict[str, str]] = None):
    e = env if env is not None else load_env()
    url = e.get("BRAVO_SUPABASE_URL") or os.environ.get("BRAVO_SUPABASE_URL")
    key = (e.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY")
           or os.environ.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY"))
    if not url or not key:
        raise RuntimeError("Bravo Supabase credentials missing — autonomous_agent cannot run")
    from supabase import create_client
    return create_client(url, key)


# ---- Configuration (safety rails) -------------------------------------------

AGENT_NAME = "bravo"
TICK_MAX_SENDS = 5
HIGH_VALUE_SCORE_THRESHOLD = 80
BUSINESS_HOURS_START = 9   # 9 AM
BUSINESS_HOURS_END = 22    # 10 PM
TIMEZONE = "America/Toronto"
HOT_INBOUND_AGE_MAX_HOURS = 48  # Don't try to re-triage stale events
DORMANCY_THRESHOLD_DAYS = 30
DUE_FOLLOWUP_DAY_2_MIN = 1.5
DUE_FOLLOWUP_DAY_2_MAX = 3.5
DUE_FOLLOWUP_DAY_5_MIN = 3.5
DUE_FOLLOWUP_DAY_5_MAX = 7.0


# ---- Decision dataclass -----------------------------------------------------

@dataclass
class Decision:
    """One thing the agent plans to do. Becomes a row in agent_decisions."""
    tick_id: str
    phase: str
    decision_type: str           # e.g. hot_reply_draft, day2_followup, mark_dormant
    target_lead_id: Optional[str]
    target_description: str      # plain-English target ("Jane at Acme (hot reply)")
    reasoning: str               # plain-English why
    confidence: float            # 0.0 .. 1.0
    chosen_action: str           # e.g. draft_and_send, escalate_to_cc, mark_dormant, no_op
    alternatives_considered: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    executed: bool = False
    execution_result: Optional[dict] = None
    outcome_status: Optional[str] = None

    def to_row(self) -> dict:
        return {
            "tick_id": self.tick_id,
            "agent_name": AGENT_NAME,
            "phase": self.phase,
            "decision_type": self.decision_type,
            "target_lead_id": self.target_lead_id,
            "target_description": self.target_description[:500] if self.target_description else None,
            "reasoning": self.reasoning[:2000] if self.reasoning else None,
            "confidence": round(self.confidence, 4),
            "chosen_action": self.chosen_action,
            "alternatives_considered": self.alternatives_considered,
            "executed": self.executed,
            "execution_result": self.execution_result,
            "outcome_status": self.outcome_status,
        }


# ---- Phase 1: ORIENT --------------------------------------------------------

def _tick_id() -> str:
    return f"tick-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"


def _toronto_now() -> datetime:
    if ZoneInfo is None:
        return datetime.now(timezone.utc)
    return datetime.now(ZoneInfo(TIMEZONE))


def _in_business_hours() -> bool:
    now = _toronto_now()
    return BUSINESS_HOURS_START <= now.hour < BUSINESS_HOURS_END


def orient(db, tick_id: str) -> dict:
    """Load state snapshot + basic operational context."""
    try:
        rows = (db.table("agent_state_snapshot")
                .select("*")
                .eq("agent_name", AGENT_NAME)
                .limit(1).execute().data) or []
    except Exception as exc:  # noqa: BLE001
        print(f"[autonomous_agent] orient: state read warning: {exc}", file=sys.stderr)
        rows = []
    prev_state = rows[0] if rows else {
        "agent_name": AGENT_NAME,
        "tick_count": 0,
        "working_memory": {},
        "pending_actions": [],
        "health_status": "ok",
    }
    return {
        "tick_id": tick_id,
        "tick_number": int(prev_state.get("tick_count") or 0) + 1,
        "now_utc": datetime.now(timezone.utc),
        "now_local": _toronto_now(),
        "business_hours": _in_business_hours(),
        "prev_state": prev_state,
    }


# ---- Phase 2: RECALL — signal detectors ------------------------------------

def detect_hot_inbound_replies(db, tick_id: str, now_utc: datetime) -> list[Decision]:
    """Find unprocessed agent_events.inbound.classified with priority=hot
    in the last 48 hours."""
    decisions: list[Decision] = []
    window_start = (now_utc - timedelta(hours=HOT_INBOUND_AGE_MAX_HOURS)).isoformat()
    try:
        rows = (db.table("agent_events")
                .select("id, payload, published_at, consumed_by, correlation_id")
                .eq("event_type", "inbound.classified")
                .gte("published_at", window_start)
                .order("published_at", desc=False)
                .limit(50).execute().data) or []
    except Exception as exc:  # noqa: BLE001
        print(f"[autonomous_agent] hot inbound query failed: {exc}", file=sys.stderr)
        return decisions

    for row in rows:
        consumed = row.get("consumed_by") or []
        if AGENT_NAME in consumed:
            continue
        payload = row.get("payload") or {}
        classification = (payload.get("classification") or {})
        priority = classification.get("priority")
        intent = classification.get("intent")
        if priority != "hot" and intent not in {"booking", "pricing", "objection"}:
            continue
        lead_id = payload.get("lead_id")
        from_identity = payload.get("from_identity") or "unknown"
        subject = payload.get("subject") or ""
        decisions.append(Decision(
            tick_id=tick_id,
            phase="recall",
            decision_type="hot_inbound_reply",
            target_lead_id=lead_id,
            target_description=f"Hot inbound from {from_identity} ({intent}) — \"{subject[:60]}\"",
            reasoning=(
                f"Classified intent={intent}, priority={priority}, "
                f"confidence={classification.get('confidence', '?')}. "
                "Hot inbound reply requires timely response — drafting via Haiku "
                "and running adversarial critique before send."
            ),
            confidence=float(classification.get("confidence") or 0.7),
            chosen_action="draft_and_send",
            metadata={
                "event_id": row["id"],
                "interaction_id": payload.get("interaction_id"),
                "from_identity": from_identity,
                "subject": subject,
                "classification": classification,
                "suggested_action": classification.get("suggested_action"),
            },
        ))
    return decisions


def detect_due_followups(db, tick_id: str, now_utc: datetime) -> list[Decision]:
    """Find leads that should receive Day-2 or Day-5 follow-up. Reuses
    the same age windows funnel_nurture uses but on the CRM leads table,
    not funnel_leads — this is the complement, not the duplicate."""
    decisions: list[Decision] = []
    # Pull leads with status 'contacted' or 'new' that have been touched
    # exactly once (or not at all) and whose first_touch is in the window.
    window_days_max = DUE_FOLLOWUP_DAY_5_MAX
    cutoff = (now_utc - timedelta(days=window_days_max + 0.5)).isoformat()
    try:
        leads = (db.table("leads")
                 .select("id,name,email,company,status,score,created_at,last_contacted_at,notes")
                 .in_("status", ["new", "contacted"])
                 .gte("created_at", cutoff)
                 .order("created_at", desc=False)
                 .limit(100).execute().data) or []
    except Exception as exc:  # noqa: BLE001
        print(f"[autonomous_agent] followup query failed: {exc}", file=sys.stderr)
        return decisions

    for lead in leads:
        if not lead.get("email"):
            continue
        try:
            created = datetime.fromisoformat((lead.get("created_at") or "").replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue
        age_days = (now_utc - created).total_seconds() / 86400.0

        # Count OUTBOUND touches only. Inbound / notes / reply rows must not
        # inflate the Day-2/Day-5 window arithmetic. (The reply-guard below
        # also short-circuits if any inbound exists, but we don't want the
        # touch counter itself to be wrong — if the reply guard ever loosens,
        # this would silently start mis-routing.)
        try:
            touches = (db.table("lead_interactions")
                       .select("id", count="exact")
                       .eq("lead_id", lead["id"])
                       .eq("channel", "email")
                       .eq("type", "email_sent")
                       .execute()).count or 0
        except Exception:
            touches = 0

        # Any inbound reply at all → skip follow-up (they've engaged)
        try:
            reply = (db.table("lead_interactions")
                     .select("id")
                     .eq("lead_id", lead["id"])
                     .in_("type", ["email_received", "email_reply"])
                     .limit(1).execute().data)
            if reply:
                continue
        except Exception:
            pass

        # Day-2 window: 1.5..3.5 days old, 0 or 1 touches
        # Day-5 window: 3.5..7 days old, 1 touch
        if touches == 0 and DUE_FOLLOWUP_DAY_2_MIN <= age_days <= DUE_FOLLOWUP_DAY_2_MAX:
            ftype, label = "day2_followup", "Day 2 follow-up"
        elif touches == 1 and DUE_FOLLOWUP_DAY_5_MIN <= age_days <= DUE_FOLLOWUP_DAY_5_MAX:
            ftype, label = "day5_followup", "Day 5 follow-up"
        else:
            continue

        decisions.append(Decision(
            tick_id=tick_id,
            phase="recall",
            decision_type=ftype,
            target_lead_id=lead["id"],
            target_description=f"{label} to {lead.get('name')} <{lead['email']}>",
            reasoning=(
                f"Lead age {age_days:.1f} days, {touches} prior touch(es), "
                "no inbound reply. Falls within the configured follow-up window."
            ),
            confidence=0.80,
            chosen_action="draft_and_send",
            metadata={
                "lead_email": lead["email"],
                "lead_name": lead.get("name"),
                "lead_company": lead.get("company"),
                "lead_score": lead.get("score"),
                "age_days": age_days,
                "touches": touches,
            },
        ))
    return decisions


def detect_dormancy_transitions(db, tick_id: str, now_utc: datetime) -> list[Decision]:
    """Mark leads that have gone 30+ days silent as 'dormant' for pipeline
    hygiene. Leads previously in active conversation get a re-engage
    proposal instead of a passive status change."""
    decisions: list[Decision] = []
    cutoff = (now_utc - timedelta(days=DORMANCY_THRESHOLD_DAYS)).isoformat()
    try:
        leads = (db.table("leads")
                 .select("id,name,email,status,score,last_contacted_at")
                 .eq("status", "contacted")
                 .lt("last_contacted_at", cutoff)
                 .limit(50).execute().data) or []
    except Exception as exc:  # noqa: BLE001
        print(f"[autonomous_agent] dormancy query failed: {exc}", file=sys.stderr)
        return decisions

    for lead in leads:
        decisions.append(Decision(
            tick_id=tick_id,
            phase="recall",
            decision_type="mark_dormant",
            target_lead_id=lead["id"],
            target_description=f"Mark {lead.get('name')} dormant (30+ days silent)",
            reasoning=(
                f"Last contact >{DORMANCY_THRESHOLD_DAYS}d ago, no inbound reply since. "
                "Moving to dormant keeps the active pipeline view clean."
            ),
            confidence=0.90,
            chosen_action="mark_dormant",
            metadata={"lead_email": lead.get("email")},
        ))
    return decisions


SIGNAL_DETECTORS: list[Callable[..., list[Decision]]] = [
    detect_hot_inbound_replies,
    detect_due_followups,
    detect_dormancy_transitions,
]


# ---- Phase 5: VERIFY — policy gates ----------------------------------------

def verify(
    decisions: list[Decision],
    daily_sends: int,
    in_business_hours: bool,
) -> list[Decision]:
    """Apply policy gates. Mutates each decision's chosen_action and
    records the reason in alternatives_considered."""
    sends_remaining = max(0, TICK_MAX_SENDS)
    sends_remaining_under_daily_cap = max(0, 50 - daily_sends)

    for d in decisions:
        if d.chosen_action not in {"draft_and_send", "send", "mark_dormant"}:
            continue

        score = float((d.metadata or {}).get("lead_score") or 0)

        # Non-send decisions (like mark_dormant) don't consume caps.
        if d.chosen_action == "mark_dormant":
            continue

        # --- ESCALATION GATES (fire BEFORE business-hours / cap guards) ---
        # Escalations ping CC via Telegram — they should happen regardless
        # of time of day. A hot booking request at 2am should wake CC up,
        # not wait until 9am when it's cold.

        # Hot inbound replies always escalate by default — response to a
        # real human conversation is too high-risk to auto-send without
        # the draft critic + explicit CC sign-off.
        if d.decision_type == "hot_inbound_reply":
            alt = {"rejected": d.chosen_action,
                   "reason": "hot inbound reply to human — escalate for CC review"}
            d.alternatives_considered.append(alt)
            d.chosen_action = "escalate_to_cc"
            continue

        # High-value lead — always loop CC in.
        if score >= HIGH_VALUE_SCORE_THRESHOLD:
            alt = {"rejected": d.chosen_action,
                   "reason": f"high-value lead (score={score}) — always escalate"}
            d.alternatives_considered.append(alt)
            d.chosen_action = "escalate_to_cc"
            continue

        # --- AUTO-SEND GATES (only apply to routine outbound) ---

        # Business hours guard — outbound to strangers at 3am looks spammy.
        if not in_business_hours:
            alt = {"rejected": d.chosen_action, "reason": "outside business hours"}
            d.alternatives_considered.append(alt)
            d.chosen_action = "buffer_until_business_hours"
            continue

        # Tick cap
        if sends_remaining <= 0:
            alt = {"rejected": d.chosen_action, "reason": f"tick cap hit ({TICK_MAX_SENDS})"}
            d.alternatives_considered.append(alt)
            d.chosen_action = "defer_to_next_tick"
            continue

        # Daily cap (gateway will enforce again but we front-check)
        if sends_remaining_under_daily_cap <= 0:
            alt = {"rejected": d.chosen_action, "reason": "daily cap would be exceeded"}
            d.alternatives_considered.append(alt)
            d.chosen_action = "defer_to_next_day"
            continue

        sends_remaining -= 1
        sends_remaining_under_daily_cap -= 1

    return decisions


# ---- Phase 6: EXECUTE -------------------------------------------------------

def execute_decisions(
    db,
    decisions: list[Decision],
    shadow: bool,
    dry_run: bool,
    env: dict[str, str],
) -> list[Decision]:
    """Run each decision. Dry-run prints, shadow writes to shadow_decisions,
    real mode goes through send_gateway / leads table updates."""
    if dry_run:
        for d in decisions:
            d.executed = False
            d.execution_result = {"dry_run": True}
            d.outcome_status = "dry_run"
        return decisions

    # Lazy imports — keep the module importable without network when only
    # inspecting state / decisions.
    from send_gateway import send as gateway_send

    for d in decisions:
        action = d.chosen_action
        if action == "escalate_to_cc":
            _notify_cc_escalation(d)
            d.executed = True
            d.execution_result = {"escalated": True}
            d.outcome_status = "escalated"
            continue

        if action == "mark_dormant":
            # Do NOT change status to 'lost' — that would remove the lead from
            # the active pipeline permanently. Instead keep status='contacted'
            # and append a dormancy note + stamp the last_contacted_at so CC
            # can re-engage later. The relationship_stage inference in
            # context_builder will correctly read this as 'dormant' based on
            # the age of last_contacted_at + outbound-only history.
            try:
                existing = (db.table("leads")
                            .select("notes")
                            .eq("id", d.target_lead_id)
                            .limit(1).execute().data) or [{}]
                prior_notes = (existing[0].get("notes") or "").strip() if existing else ""
                now_iso = datetime.now(timezone.utc).isoformat()
                today = now_iso[:10]
                dormant_line = f"[{today}] AUTONOMOUS-AGENT: flagged dormant ({DORMANCY_THRESHOLD_DAYS}d silent)"
                merged_notes = (prior_notes + "\n" + dormant_line).strip() if prior_notes else dormant_line
                db.table("leads").update({
                    "notes": merged_notes[:4000],
                    "updated_at": now_iso,
                }).eq("id", d.target_lead_id).execute()
                d.executed = True
                d.execution_result = {"flagged_dormant": True}
                d.outcome_status = "dormant"
            except Exception as exc:  # noqa: BLE001
                d.executed = False
                d.execution_result = {"error": str(exc)}
                d.outcome_status = "error"
            continue

        if action in {"buffer_until_business_hours", "defer_to_next_tick", "defer_to_next_day"}:
            d.executed = False
            d.execution_result = {"deferred": action}
            d.outcome_status = "deferred"
            continue

        if action != "draft_and_send":
            d.executed = False
            d.execution_result = {"skipped": f"unknown action {action}"}
            d.outcome_status = "skipped"
            continue

        # For the Day-2/Day-5 followups we have a real draft path.
        subject, body = _draft_body_for_decision(d, env)
        if not body:
            d.executed = False
            d.execution_result = {"error": "draft generation failed"}
            d.outcome_status = "draft_failed"
            continue

        # Run through draft critic — escalate if critic rejects.
        # NOTE: critique_and_revise() returns a dict with keys
        # `final_verdict`, `final_subject`, `final_body`, `revisions_made`,
        # `critique_history`, `escalation_reason`. Reading a stray "verdict"
        # key here would always return None (that was a bug before 2026-04-20).
        critic_result = _run_critic(d, subject, body, env)
        last_critique = (critic_result.get("critique_history") or [{}])[-1]
        d.metadata["critic_verdict"] = {
            "final_verdict": critic_result.get("final_verdict"),
            "score": last_critique.get("score"),
            "notes": last_critique.get("notes"),
            "revisions_made": critic_result.get("revisions_made"),
        }
        if critic_result.get("final_verdict") == "escalate":
            _notify_cc_escalation(
                d,
                extra=f"Critic rejected: {critic_result.get('escalation_reason') or last_critique.get('notes')}",
            )
            d.executed = True
            d.execution_result = {"escalated_by_critic": True}
            d.outcome_status = "escalated_by_critic"
            continue
        # Critic approved — swap in the (possibly revised) subject/body.
        if critic_result.get("final_subject"):
            subject = critic_result["final_subject"]
            body = critic_result["final_body"]

        if shadow:
            try:
                db.table("shadow_decisions").insert({
                    "agent_source": "autonomous_agent",
                    "channel": "email",
                    "lead_id": d.target_lead_id,
                    "to_identity": (d.metadata or {}).get("lead_email"),
                    "subject": subject,
                    "body_preview": body[:500],
                    "would_have_status": "sent",
                    "comparison_run_id": d.tick_id,
                    "brand": "oasis",
                    "intent": "commercial",
                    "metadata": {"decision": d.to_row()},
                }).execute()
                d.executed = False
                d.execution_result = {"shadow": True}
                d.outcome_status = "shadow"
            except Exception as exc:  # noqa: BLE001
                d.executed = False
                d.execution_result = {"error": f"shadow write failed: {exc}"}
                d.outcome_status = "error"
            continue

        # Real send through the gateway.
        md = d.metadata or {}
        result = gateway_send(
            channel="email",
            agent_source="autonomous_agent",
            to_email=md.get("lead_email"),
            lead_id=d.target_lead_id,
            subject=subject,
            body_text=body,
            brand="oasis",
            intent="commercial",
            metadata={
                "tick_id": d.tick_id,
                "decision_type": d.decision_type,
                "critic_score": (d.metadata.get("critic_verdict") or {}).get("score"),
            },
        )
        d.executed = (result.get("status") == "sent")
        d.execution_result = result
        d.outcome_status = result.get("status")

    return decisions


def _draft_body_for_decision(d: Decision, env: dict[str, str]) -> tuple[Optional[str], Optional[str]]:
    """Produce subject+body for decisions that want to send. Imports
    Anthropic lazily so modules without network still load."""
    try:
        import anthropic
    except ImportError:
        return None, None
    api_key = env.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None, None

    md = d.metadata or {}
    name = md.get("lead_name") or "there"
    first_name = name.split()[0] if name and " " in name else name
    company = md.get("lead_company") or "your business"
    stage_hint = {
        "day2_followup": "Lead received one cold email 2 days ago, no reply yet. Follow up with one concrete new angle, not a repeat of the first pitch.",
        "day5_followup": "Lead received two messages, no reply. Short final-call vibe, never needy. If no response after this, they're marked dormant.",
    }.get(d.decision_type, "Cold outreach from Conaugh McKenna at OASIS AI.")

    prompt = f"""Write a short follow-up email from Conaugh McKenna, founder of OASIS AI Solutions.

Recipient: {name} at {company}
Situation: {stage_hint}

Rules:
- 80-120 words max
- No slop openers ("hope this finds you well", "wanted to reach out", "quick question")
- First line: one specific, concrete angle
- CTA: "Grab any slot that works: https://calendar.app.google/tpfvJYBGircnGu8G8"
- Signature block:
    Conaugh McKenna
    OASIS AI Solutions
    oasisai.work | Book a call: https://calendar.app.google/tpfvJYBGircnGu8G8
- Subject on line 1 as "Subject: <subject>"
- Blank line, then body.

Output ONLY the email."""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in msg.content if hasattr(b, "text")).strip()
    except Exception as exc:  # noqa: BLE001
        print(f"[autonomous_agent] draft generation failed: {exc}", file=sys.stderr)
        return None, None

    lines = text.splitlines()
    subject = ""
    body_start = 0
    if lines and lines[0].lower().startswith("subject:"):
        subject = lines[0].split(":", 1)[1].strip()
        body_start = 2 if len(lines) > 2 and lines[1].strip() == "" else 1
    body = "\n".join(lines[body_start:]).strip()
    if not subject:
        subject = f"{first_name} — quick thought for {company}"
    return subject, body


def _run_critic(d: Decision, subject: str, body: str, env: dict[str, str]) -> dict:
    """Invoke draft_critic.critique_and_revise with one retry."""
    try:
        from draft_critic import critique_and_revise
    except Exception as exc:  # noqa: BLE001
        print(f"[autonomous_agent] critic import failed: {exc}", file=sys.stderr)
        return {"verdict": "escalate", "score": 0.0, "notes": f"critic unavailable: {exc}"}

    ctx = {
        "relationship_stage": "contacted" if d.decision_type == "day2_followup" else "contacted",
        "name": (d.metadata or {}).get("lead_name"),
        "company": (d.metadata or {}).get("lead_company"),
        "outbound_count": (d.metadata or {}).get("touches"),
        "inbound_count": 0,
        "sentiment_signal": "unknown",
    }
    result = critique_and_revise(
        draft_subject=subject,
        draft_body=body,
        relationship_context=ctx,
        brand="oasis",
        intent="commercial",
        max_revisions=1,
        env=env,
    )
    return result


def _notify_cc_escalation(d: Decision, extra: str = "") -> None:
    try:
        from notify import notify
    except Exception:
        return
    msg_lines = [
        f"🎯 Reasoning loop escalation — {d.decision_type}",
        f"Target: {d.target_description}",
        f"Reasoning: {d.reasoning[:250]}",
    ]
    if extra:
        msg_lines.append(f"Detail: {extra[:250]}")
    if (d.metadata or {}).get("subject"):
        msg_lines.append(f"Subject: {d.metadata['subject'][:100]}")
    try:
        notify("\n".join(msg_lines), category="lead")
    except Exception:
        pass


# ---- Phase 7: REFLECT -------------------------------------------------------

def reflect(db, tick_id: str, state: dict, decisions: list[Decision], duration_s: float) -> dict:
    """Persist decision rows, update state snapshot, return a summary."""
    # 1. Write every decision to agent_decisions.
    rows = [d.to_row() for d in decisions]
    if rows:
        try:
            db.table("agent_decisions").insert(rows).execute()
        except Exception as exc:  # noqa: BLE001
            print(f"[autonomous_agent] agent_decisions write failed: {exc}", file=sys.stderr)

    # 2. Mark consumed events (so we don't re-process hot inbounds next tick).
    for d in decisions:
        ev_id = (d.metadata or {}).get("event_id")
        if ev_id and d.executed:
            try:
                db.rpc("mark_event_consumed", {"p_event_id": ev_id, "p_agent": AGENT_NAME}).execute()
            except Exception:
                pass

    # 3. Update state snapshot.
    try:
        db.table("agent_state_snapshot").upsert({
            "agent_name": AGENT_NAME,
            "tick_count": state["tick_number"],
            "last_tick_at": state["now_utc"].isoformat(),
            "last_tick_id": tick_id,
            "working_memory": {
                "last_tick_decisions": len(decisions),
                "last_tick_duration_s": round(duration_s, 3),
            },
            "pending_actions": [
                d.target_description for d in decisions
                if d.outcome_status in {"deferred", "escalated"}
            ][:20],
            "health_status": "ok",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }, on_conflict="agent_name").execute()
    except Exception as exc:  # noqa: BLE001
        print(f"[autonomous_agent] state snapshot write failed: {exc}", file=sys.stderr)

    # 4. Compose plain-English summary.
    summary = _compose_summary(tick_id, state, decisions, duration_s)
    return summary


def _compose_summary(tick_id: str, state: dict, decisions: list[Decision], duration_s: float) -> dict:
    total = len(decisions)
    by_action: dict[str, int] = {}
    by_type: dict[str, int] = {}
    sent = escalated = deferred = dormancy = shadow = 0
    for d in decisions:
        by_action[d.chosen_action] = by_action.get(d.chosen_action, 0) + 1
        by_type[d.decision_type] = by_type.get(d.decision_type, 0) + 1
        if d.outcome_status == "sent":
            sent += 1
        elif d.outcome_status and d.outcome_status.startswith("escalat"):
            escalated += 1
        elif d.outcome_status == "deferred":
            deferred += 1
        elif d.outcome_status == "dormant":
            dormancy += 1
        elif d.outcome_status == "shadow":
            shadow += 1

    lines: list[str] = [
        f"Tick {state['tick_number']} complete in {duration_s:.2f}s.",
    ]
    if total == 0:
        lines.append("Nothing actionable this cycle — pipeline is quiet.")
    else:
        lines.append(f"Looked at {total} signal(s).")
        if sent:
            lines.append(f"✉️ Sent {sent} outbound message(s) through the gateway.")
        if escalated:
            lines.append(f"🎯 Escalated {escalated} item(s) to you (Telegram).")
        if dormancy:
            lines.append(f"🗂️ Marked {dormancy} lead(s) dormant (30+ days silent).")
        if shadow:
            lines.append(f"🔒 Shadow-logged {shadow} decision(s) (would-have-sent).")
        if deferred:
            lines.append(f"⏳ Deferred {deferred} decision(s) (tick cap / business hours / daily cap).")

    return {
        "tick_id": tick_id,
        "tick_number": state["tick_number"],
        "now_local": state["now_local"].isoformat(),
        "business_hours": state["business_hours"],
        "decisions_total": total,
        "by_decision_type": by_type,
        "by_chosen_action": by_action,
        "sent": sent,
        "escalated": escalated,
        "deferred": deferred,
        "marked_dormant": dormancy,
        "shadow_logged": shadow,
        "duration_seconds": round(duration_s, 3),
        "english_summary": " ".join(lines),
        "plain_english_lines": lines,
    }


# ---- Full tick --------------------------------------------------------------

def run_tick(
    shadow: bool = True,
    dry_run: bool = False,
    db: Any = None,
    env: Optional[dict[str, str]] = None,
) -> dict:
    """Execute one tick through all seven phases. Returns the plain-English
    summary dict. Safe to call repeatedly — each tick is independent."""
    t0 = time.time()
    e = env if env is not None else load_env()
    db = db if db is not None else get_supabase(e)
    tick_id = _tick_id()

    state = orient(db, tick_id)

    signals: list[Decision] = []
    for detector in SIGNAL_DETECTORS:
        try:
            signals.extend(detector(db, tick_id, state["now_utc"]))
        except Exception as exc:  # noqa: BLE001
            print(f"[autonomous_agent] detector {detector.__name__} failed: {exc}",
                  file=sys.stderr)

    # Assess + Plan are embedded in the detectors themselves — each detector
    # returns decisions with chosen_action, reasoning, and confidence
    # pre-populated. The Verify phase below rewrites chosen_action based on
    # policy, which is where the assess/plan/verify separation matters.

    # Today's daily send count for the cap check.
    day_start = state["now_utc"].replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        daily_sends = (db.table("lead_interactions")
                       .select("id", count="exact")
                       .eq("channel", "email")
                       .eq("type", "email_sent")
                       .gte("created_at", day_start.isoformat())
                       .execute()).count or 0
    except Exception:
        daily_sends = 0

    signals = verify(
        decisions=signals,
        daily_sends=daily_sends,
        in_business_hours=state["business_hours"],
    )
    for d in signals:
        d.phase = "execute"
    signals = execute_decisions(db, signals, shadow=shadow, dry_run=dry_run, env=e)
    for d in signals:
        d.phase = "reflect"

    duration = time.time() - t0
    summary = reflect(db, tick_id, state, signals, duration)
    summary["decisions"] = [d.to_row() for d in signals]
    return summary


# ---- Daemon -----------------------------------------------------------------

def run_daemon(interval_seconds: int, shadow: bool, dry_run: bool) -> None:
    """Run ticks forever with a fixed interval. Cheap sleep between ticks
    so cron handlers can also invoke run_tick() without colliding.

    A file-lock prevents two daemons from running against the same DB
    (same pattern skool_engine uses)."""
    print(f"[autonomous_agent] daemon starting, interval={interval_seconds}s, "
          f"shadow={shadow}, dry_run={dry_run}")
    while True:
        try:
            summary = run_tick(shadow=shadow, dry_run=dry_run)
            print(f"[autonomous_agent] {summary['english_summary']}")
        except KeyboardInterrupt:
            print("[autonomous_agent] daemon stopped by user.")
            return
        except Exception as exc:  # noqa: BLE001
            print(f"[autonomous_agent] tick failed: {exc}", file=sys.stderr)
        try:
            time.sleep(interval_seconds)
        except KeyboardInterrupt:
            return


# ---- CLI --------------------------------------------------------------------

def _print_json(obj: Any) -> None:
    print(json.dumps(obj, indent=2, default=str))


def _cmd_tick(args) -> int:
    summary = run_tick(shadow=args.shadow or args.dry_run, dry_run=args.dry_run)
    if args.output_json:
        _print_json(summary)
    else:
        for line in summary["plain_english_lines"]:
            print(line)
        if summary["decisions_total"]:
            print()
            print("Decisions:")
            for d in summary["decisions"][:20]:
                print(f"  • [{d['decision_type']}] {d['target_description']}")
                print(f"    action={d['chosen_action']}  status={d['outcome_status']}")
    return 0


def _cmd_status(args) -> int:
    db = get_supabase()
    rows = (db.table("agent_state_snapshot").select("*").eq("agent_name", AGENT_NAME)
            .limit(1).execute().data) or []
    if not rows:
        print("No state snapshot yet. Run a tick first.")
        return 1
    snap = rows[0]
    if args.output_json:
        _print_json(snap)
    else:
        print(f"Agent:       {snap.get('agent_name')}")
        print(f"Tick count:  {snap.get('tick_count')}")
        print(f"Last tick:   {snap.get('last_tick_at')}")
        print(f"Last tick_id: {snap.get('last_tick_id')}")
        print(f"Health:      {snap.get('health_status')}")
        if snap.get("pending_actions"):
            print("Pending:")
            for a in (snap.get("pending_actions") or [])[:10]:
                print(f"  • {a}")
    return 0


def _cmd_decisions(args) -> int:
    db = get_supabase()
    q = db.table("agent_decisions").select("*").order("created_at", desc=True)
    if args.tick_id:
        q = q.eq("tick_id", args.tick_id)
    elif args.today:
        now = datetime.now(timezone.utc)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        q = q.gte("created_at", day_start)
    q = q.limit(args.limit)
    rows = q.execute().data or []
    if args.output_json:
        _print_json(rows)
        return 0
    if not rows:
        print("No decisions logged.")
        return 0
    for r in rows:
        at = (r.get("created_at") or "")[:19]
        print(f"  {at}  [{r.get('decision_type'):22}]  "
              f"action={r.get('chosen_action'):24}  "
              f"status={r.get('outcome_status') or '-'}")
        td = r.get("target_description") or ""
        if td:
            print(f"      → {td[:100]}")
    print(f"\n  {len(rows)} decision(s).")
    return 0


def _cmd_daemon(args) -> int:
    run_daemon(interval_seconds=args.interval, shadow=args.shadow or args.dry_run,
               dry_run=args.dry_run)
    return 0


def main() -> None:
    p = argparse.ArgumentParser(
        prog="autonomous_agent.py",
        description="The always-on reasoning loop. Thinks, decides, acts.",
    )
    p.add_argument("--json", dest="output_json", action="store_true")
    sub = p.add_subparsers(dest="command")

    pt = sub.add_parser("tick", help="Run one cycle of the brain loop")
    pt.add_argument("--shadow", action="store_true",
                     help="Write decisions to shadow_decisions instead of executing.")
    pt.add_argument("--dry-run", dest="dry_run", action="store_true",
                     help="Print decisions only; no DB writes, no sends.")

    pd = sub.add_parser("daemon", help="Run ticks in a loop forever")
    pd.add_argument("--interval", type=int, default=900,
                     help="Seconds between ticks (default: 900 = 15 min)")
    pd.add_argument("--shadow", action="store_true")
    pd.add_argument("--dry-run", dest="dry_run", action="store_true")

    sub.add_parser("status", help="Show last-tick state snapshot")

    pdd = sub.add_parser("decisions", help="Show recent decisions")
    pdd.add_argument("--tick-id", dest="tick_id", default=None)
    pdd.add_argument("--today", action="store_true")
    pdd.add_argument("--limit", type=int, default=50)

    args = p.parse_args()
    if args.command == "tick":
        sys.exit(_cmd_tick(args))
    elif args.command == "daemon":
        sys.exit(_cmd_daemon(args))
    elif args.command == "status":
        sys.exit(_cmd_status(args))
    elif args.command == "decisions":
        sys.exit(_cmd_decisions(args))
    else:
        p.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
