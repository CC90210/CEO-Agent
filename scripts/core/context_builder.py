"""
Context Builder — assembles the full conversational + relational context
for any lead/contact so LLM-drafted outbound communication can finally
speak with social awareness.

WHY THIS EXISTS
---------------
Before this module, every automated email was drafted in a vacuum. Claude
Haiku saw only {name, company, notes} — no prior-reply history, no
sentiment trajectory, no engagement signal. That is why tone
was flat, why cold-email language leaked into warm follow-ups, and why CC
described the AI as "not knowing the social cues."

This module exposes one function: `get_entity_context(lead_id)`. It returns
a structured dict that any drafting prompt can consume. The persona engine
(Phase 6 / follow-on) composes the actual system prompt from this data.

USAGE
-----
From any engine::

    from context_builder import get_entity_context

    ctx = get_entity_context(lead_id="<uuid>")
    # ctx = {
    #   "lead": {...},                       # full leads-table row
    #   "relationship_stage": "cold"|"warm"|"engaged"|"active_client"|"dormant",
    #   "days_since_first_touch": 14,
    #   "days_since_last_touch": 3,
    #   "interactions": [...],               # last N interactions, newest first
    #   "outbound_count": 4,
    #   "inbound_count": 1,
    #   "last_inbound": {...}|None,          # their most recent reply
    #   "last_outbound": {...}|None,         # our most recent send
    #   "sentiment_signal": "positive"|"neutral"|"negative"|"unknown",
    #   "in_cooldown": bool,
    #   "cooldown_until": "...",
    #   "channels_used": ["email", "instagram"],
    #   "tags": [...],
    #   "notes": "...",
    # }

    persona_prompt = compose_prompt(ctx, intent="follow_up")
    # -> system prompt tuned to this specific relationship

From the CLI::

    python scripts/core/context_builder.py show --lead-id <uuid>
    python scripts/core/context_builder.py show --email jane@acme.com --json
    python scripts/core/context_builder.py relationship-map --limit 20

DESIGN DECISIONS
----------------
1. Deterministic, no LLM calls at this layer. Sentiment is keyword-based
   for now (cheap, fast, predictable). A follow-on (reply_classifier.py)
   will replace it with Haiku when CC is ready.
2. Everything is derived from lead_interactions + leads tables. No new
   tables. Reuses the ledger the send_gateway writes to.
3. Relationship stage is a first-class concept. Five stages map to very
   different outbound tones — a dormant re-engage is not a cold pitch.
4. Consumed by any engine, any channel. The returned dict is stable — new
   keys can be added without breaking callers (additive only).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))


# ---- Env + DB (same pattern as send_gateway.py) -----------------------------

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


def get_supabase(env_vars: Optional[dict[str, str]] = None):
    env = env_vars if env_vars is not None else load_env()
    url = env.get("BRAVO_SUPABASE_URL") or os.environ.get("BRAVO_SUPABASE_URL")
    key = (env.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY")
           or os.environ.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY"))
    if not url or not key:
        raise RuntimeError("Missing Bravo Supabase credentials in .env.agents")
    from supabase import create_client
    return create_client(url, key)


# ---- Relationship stage inference -------------------------------------------

RELATIONSHIP_STAGES = (
    "cold",          # No interaction yet, or status='new' with no touches
    "contacted",     # We've reached out at least once, no reply
    "warm",          # They replied at least once, positive or neutral signal
    "engaged",       # Active back-and-forth within last 14 days
    "active_client", # status='won' or revenue event logged
    "dormant",       # No contact 30+ days AND prior engagement
    "lost",          # status='lost'
)

# Substring keywords for cheap sentiment classification. Replaced by Haiku
# in follow-on work (reply_classifier.py). Kept here so the gateway works
# end-to-end without an API call.
POSITIVE_KEYWORDS = (
    "yes", "interested", "sounds good", "let's do", "lets do", "great", "love",
    "awesome", "perfect", "thanks", "thank you", "appreciate", "tell me more",
    "more info", "book", "schedule", "call me", "absolutely", "definitely",
    "keen", "exactly", "this is helpful", "exactly what", "excited",
)
NEGATIVE_KEYWORDS = (
    "not interested", "no thanks", "unsubscribe", "remove me", "stop",
    "not a fit", "pass", "leave me alone", "spam", "scam", "angry", "furious",
    "complaint", "refund", "cancel", "too expensive", "can't afford",
)


def _infer_sentiment(content: str) -> str:
    """Keyword-based sentiment signal. Fast and predictable; a follow-on
    reply_classifier.py will replace with Haiku when CC enables it."""
    if not content:
        return "unknown"
    lower = content.lower()
    neg = sum(1 for k in NEGATIVE_KEYWORDS if k in lower)
    pos = sum(1 for k in POSITIVE_KEYWORDS if k in lower)
    if neg > pos and neg >= 1:
        return "negative"
    if pos > neg and pos >= 1:
        return "positive"
    return "neutral"


def _infer_relationship_stage(
    lead: dict,
    interactions: list[dict],
    now: datetime,
) -> str:
    """Apply the stage-decision tree. Order matters — earlier conditions
    are checked first, so e.g. 'lost' beats 'dormant'."""
    status = (lead.get("status") or "").lower()
    if status == "lost":
        return "lost"
    if status == "won":
        return "active_client"
    if not interactions:
        return "cold"

    # Split into outbound vs inbound
    inbound = [
        ix for ix in interactions
        if (ix.get("type") or "").endswith(("_received", "_reply"))
        or (ix.get("type") or "") in {"reply", "inbound", "note"}
    ]
    outbound = [ix for ix in interactions if ix not in inbound]

    # Most-recent interaction age
    try:
        latest_iso = interactions[0].get("created_at", "")
        latest_dt = datetime.fromisoformat((latest_iso or "").replace("Z", "+00:00"))
        days_since = (now - latest_dt).days
    except (ValueError, TypeError):
        days_since = 999

    # Engaged: reply within last 14 days
    if inbound and days_since <= 14:
        return "engaged"
    # Warm: any prior reply, older than 14 days
    if inbound:
        # If old but no new activity for 30+ days, classify as dormant
        if days_since > 30:
            return "dormant"
        return "warm"
    # Contacted: outbound only, within 30 days
    if outbound and days_since <= 30:
        return "contacted"
    # Dormant: outbound only, older than 30 days
    return "dormant"


# ---- Public API -------------------------------------------------------------

def get_entity_context(
    lead_id: Optional[str] = None,
    email: Optional[str] = None,
    max_interactions: int = 20,
    db: Any = None,
) -> dict:
    """Assemble the full context dict for a lead.

    Either `lead_id` or `email` must be provided. Returns an empty/minimal
    shape if the lead is not found rather than raising — callers should
    treat empty context as 'cold' stage.
    """
    db = db if db is not None else get_supabase()
    now = datetime.now(timezone.utc)

    # 1. Resolve lead
    lead: Optional[dict] = None
    if lead_id:
        try:
            r = db.table("leads").select("*").eq("id", lead_id).limit(1).execute()
            if r.data:
                lead = r.data[0]
        except Exception as exc:  # noqa: BLE001
            print(f"[context_builder] lead lookup by id failed: {exc}", file=sys.stderr)
    elif email:
        try:
            norm = email.strip().lower()
            r = db.table("leads").select("*").eq("email", norm).limit(1).execute()
            if r.data:
                lead = r.data[0]
                lead_id = lead["id"]
        except Exception as exc:  # noqa: BLE001
            print(f"[context_builder] lead lookup by email failed: {exc}", file=sys.stderr)

    if not lead:
        return {
            "lead": None,
            "lead_id": None,
            "email": email,
            "relationship_stage": "cold",
            "days_since_first_touch": None,
            "days_since_last_touch": None,
            "interactions": [],
            "outbound_count": 0,
            "inbound_count": 0,
            "last_inbound": None,
            "last_outbound": None,
            "sentiment_signal": "unknown",
            "in_cooldown": False,
            "cooldown_until": None,
            "channels_used": [],
            "tags": [],
            "notes": "",
            "warning": "lead not found — context minimal",
        }

    # 2. Interaction history
    try:
        rows = (
            db.table("lead_interactions")
            .select("*")
            .eq("lead_id", lead_id)
            .order("created_at", desc=True)
            .limit(max_interactions)
            .execute()
            .data
        ) or []
    except Exception as exc:  # noqa: BLE001
        print(f"[context_builder] interaction history query failed: {exc}", file=sys.stderr)
        rows = []

    # 3. Derive slices
    outbound: list[dict] = []
    inbound: list[dict] = []
    for ix in rows:
        t = (ix.get("type") or "").lower()
        if t.endswith(("_received", "_reply")) or t in {"reply", "inbound", "note"}:
            inbound.append(ix)
        else:
            outbound.append(ix)

    channels_used = sorted({(ix.get("channel") or "").lower() for ix in rows if ix.get("channel")})

    def _age_days(iso: Optional[str]) -> Optional[int]:
        if not iso:
            return None
        try:
            dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            return (now - dt).days
        except (ValueError, TypeError):
            return None

    last_inbound = inbound[0] if inbound else None
    last_outbound = outbound[0] if outbound else None

    # 4. Oldest interaction for first-touch
    first_touch_iso = rows[-1].get("created_at") if rows else lead.get("created_at")
    last_touch_iso = rows[0].get("created_at") if rows else lead.get("last_contacted_at")

    # 5. Active cooldown check
    cooldown_until: Optional[str] = None
    in_cooldown = False
    for ix in rows:
        cu = ix.get("cooldown_until")
        if not cu:
            continue
        try:
            cu_dt = datetime.fromisoformat(cu.replace("Z", "+00:00"))
            if cu_dt > now:
                # Pick the latest cooldown across channels — caller can
                # still query per-channel via send_gateway.can_act().
                if cooldown_until is None or cu_dt > datetime.fromisoformat(
                    cooldown_until.replace("Z", "+00:00")
                ):
                    cooldown_until = cu
                    in_cooldown = True
        except (ValueError, TypeError):
            continue

    # 6. Sentiment from most recent inbound
    sentiment = _infer_sentiment(last_inbound.get("content", "") if last_inbound else "")

    # 7. Relationship stage
    stage = _infer_relationship_stage(lead, rows, now)

    return {
        "lead": lead,
        "lead_id": lead_id,
        "email": lead.get("email"),
        "name": lead.get("name"),
        "company": lead.get("company"),
        "source": lead.get("source"),
        "status": lead.get("status"),
        "score": lead.get("score"),
        "relationship_stage": stage,
        "days_since_first_touch": _age_days(first_touch_iso),
        "days_since_last_touch": _age_days(last_touch_iso),
        "interactions": rows,
        "outbound_count": len(outbound),
        "inbound_count": len(inbound),
        "last_inbound": last_inbound,
        "last_outbound": last_outbound,
        "sentiment_signal": sentiment,
        "in_cooldown": in_cooldown,
        "cooldown_until": cooldown_until,
        "channels_used": channels_used,
        "tags": lead.get("tags") or [],
        "notes": lead.get("notes") or "",
    }


def compose_prompt_context(ctx: dict) -> str:
    """Turn a context dict into a compact string a system prompt can consume.

    Designed to be injected into a Claude system prompt. Kept short so it
    doesn't blow the token budget on batch runs. ~400 tokens max.
    """
    if ctx.get("lead") is None:
        return "NO PRIOR CONTEXT. Treat as a fresh cold outreach."

    stage = ctx["relationship_stage"]
    last_in = ctx.get("last_inbound")
    last_out = ctx.get("last_outbound")
    sentiment = ctx.get("sentiment_signal", "unknown")

    lines = [
        f"RELATIONSHIP STAGE: {stage}",
        f"LEAD: {ctx.get('name')} at {ctx.get('company') or 'unknown company'}",
        f"SOURCE: {ctx.get('source') or 'unknown'}",
        f"OUTBOUND SO FAR: {ctx['outbound_count']}  |  INBOUND: {ctx['inbound_count']}",
    ]
    if ctx.get("days_since_last_touch") is not None:
        lines.append(f"DAYS SINCE LAST CONTACT: {ctx['days_since_last_touch']}")
    if sentiment != "unknown":
        lines.append(f"LAST REPLY SENTIMENT: {sentiment}")
    if last_in:
        content = (last_in.get("content") or "")[:300]
        lines.append(f"LAST INBOUND MESSAGE (excerpt): {content}")
    if last_out:
        content = (last_out.get("content") or "")[:200]
        lines.append(f"LAST OUTBOUND (excerpt): {content}")
    if ctx.get("notes"):
        lines.append(f"NOTES: {ctx['notes'][:300]}")
    if ctx.get("in_cooldown"):
        lines.append(f"COOLDOWN ACTIVE until {ctx.get('cooldown_until')}")

    # Tone guidance per stage — this is the first brick of the persona engine.
    tone_hint = {
        "cold":          "No prior relationship. Lead with ONE specific pain point, "
                         "keep it under 120 words, never presume familiarity.",
        "contacted":     "They got our first touch but haven't replied. Do not repeat "
                         "the earlier pitch. Add new value or ask a diagnostic question.",
        "warm":          "They replied once. Reference their actual words. Respect the "
                         "reply — do not push for a meeting if they raised concerns.",
        "engaged":       "Active conversation. Match their tone precisely. Short replies "
                         "beg short responses; long emails invite long ones.",
        "active_client": "This person is already a client or won deal. Speak as partner, "
                         "not prospect. No pitching.",
        "dormant":       "Long gap. Open with genuine re-engagement (no guilt, no FOMO). "
                         "Reference the concrete thing that ended the last thread.",
        "lost":          "Deal is marked lost. Do not auto-contact. This path should have "
                         "been blocked upstream — escalate to CC.",
    }.get(stage, "")
    if tone_hint:
        lines.append(f"TONE GUIDANCE: {tone_hint}")

    return "\n".join(lines)


# ---- CLI --------------------------------------------------------------------

def _print_json(obj: Any) -> None:
    print(json.dumps(obj, indent=2, default=str))


def _cmd_show(args) -> int:
    db = get_supabase()
    ctx = get_entity_context(
        lead_id=args.lead_id,
        email=args.email,
        max_interactions=args.limit,
        db=db,
    )
    if args.output_json:
        _print_json(ctx)
        return 0

    if ctx.get("lead") is None:
        print(f"Lead not found (id={args.lead_id}, email={args.email}).")
        return 1

    print(f"Entity Context — {ctx.get('name')} ({ctx.get('email')})")
    print(f"  Stage:        {ctx['relationship_stage']}")
    print(f"  Source:       {ctx.get('source')}")
    print(f"  Status:       {ctx.get('status')}  score={ctx.get('score')}")
    print(f"  Days since last touch: {ctx.get('days_since_last_touch')}")
    print(f"  Outbound: {ctx['outbound_count']}  Inbound: {ctx['inbound_count']}")
    print(f"  Last reply sentiment: {ctx['sentiment_signal']}")
    if ctx.get("in_cooldown"):
        print(f"  Cooldown active until: {ctx['cooldown_until']}")
    if ctx.get("channels_used"):
        print(f"  Channels used: {', '.join(ctx['channels_used'])}")
    if ctx.get("interactions"):
        print(f"\n  Recent interactions ({len(ctx['interactions'])}):")
        for ix in ctx["interactions"][:5]:
            at = (ix.get("created_at") or "")[:19]
            typ = ix.get("type") or "-"
            ch = ix.get("channel") or "-"
            src = ix.get("agent_source") or "-"
            subj = (ix.get("subject") or "")[:60]
            print(f"    {at}  {ch:10}  {typ:14}  src={src}  {subj}")

    print("\n--- Prompt-ready context (for persona engine) ---")
    print(compose_prompt_context(ctx))
    return 0


def _cmd_map(args) -> int:
    """Scan recent leads and classify their relationship stage. Quick health
    check for the pipeline."""
    db = get_supabase()
    try:
        rows = (
            db.table("leads")
            .select("id,name,email,company,status,score,created_at,last_contacted_at")
            .order("created_at", desc=True)
            .limit(args.limit)
            .execute()
            .data
        ) or []
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    mapping: list[dict[str, Any]] = []
    for lead in rows:
        try:
            ctx = get_entity_context(lead_id=lead["id"], db=db, max_interactions=10)
            mapping.append({
                "id": lead["id"],
                "name": lead.get("name"),
                "email": lead.get("email"),
                "stage": ctx["relationship_stage"],
                "outbound": ctx["outbound_count"],
                "inbound": ctx["inbound_count"],
                "last_touch_days": ctx.get("days_since_last_touch"),
                "sentiment": ctx["sentiment_signal"],
            })
        except Exception as exc:  # noqa: BLE001
            print(f"[map] failed for lead {lead.get('id')}: {exc}", file=sys.stderr)

    if args.output_json:
        _print_json(mapping)
        return 0

    stage_counts: dict[str, int] = {}
    for m in mapping:
        stage_counts[m["stage"]] = stage_counts.get(m["stage"], 0) + 1

    print(f"Relationship map ({len(mapping)} leads):\n")
    for stage in RELATIONSHIP_STAGES:
        c = stage_counts.get(stage, 0)
        if c:
            print(f"  {stage:15} {c}")
    print()
    for m in mapping:
        days = m.get("last_touch_days")
        days_s = f"{days}d" if days is not None else "-"
        print(f"  [{m['stage']:12}] {m['name']:25}  "
              f"{m['email'] or '-':35}  "
              f"out={m['outbound']:2} in={m['inbound']:2}  "
              f"last={days_s:5}  sent={m['sentiment']}")
    return 0


def main() -> None:
    p = argparse.ArgumentParser(
        prog="context_builder.py",
        description="Assemble the full relationship context for any lead.",
    )
    p.add_argument("--json", dest="output_json", action="store_true")
    sub = p.add_subparsers(dest="command")

    p_show = sub.add_parser("show", help="Show the full context for a lead")
    p_show.add_argument("--lead-id", dest="lead_id", default=None)
    p_show.add_argument("--email", default=None)
    p_show.add_argument("--limit", type=int, default=20)

    p_map = sub.add_parser("relationship-map",
                            help="Classify recent leads by relationship stage")
    p_map.add_argument("--limit", type=int, default=30)

    args = p.parse_args()

    if args.command == "show":
        if not args.lead_id and not args.email:
            p_show.error("Provide --lead-id or --email")
        sys.exit(_cmd_show(args))
    elif args.command == "relationship-map":
        sys.exit(_cmd_map(args))
    else:
        p.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
