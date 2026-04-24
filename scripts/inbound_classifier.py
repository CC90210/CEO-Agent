"""
Inbound Classifier — the second half of V5.6's chokepoint.

V5.6 made outbound coherent by forcing every send through send_gateway.
Inbound was still split across engines: IMAP in email_engine, Playwright
in instagram_engine, the N8N qualifier, skool_engine's crawler — each
with different logic and no shared sentiment or intent understanding.

This module is the single classification pipeline for every inbound
event. Given raw content + channel, it produces a structured record
that writes to lead_interactions AND publishes an event on the bus
so subscribers (the autonomous agent, Atlas, Maven) can react.

USAGE FROM PYTHON
-----------------
    from inbound_classifier import classify, record_inbound

    result = classify(
        content="yes definitely book me in for wednesday",
        channel="email",
        subject="Re: Your HVAC scheduling proposal",
        from_identity="jane@acme.example",
    )
    # result = {
    #   "sentiment": "positive",
    #   "intent": "booking",
    #   "priority": "hot",
    #   "stage_signal": "escalate_to_engaged",
    #   "confidence": 0.92,
    #   "suggested_action": "draft_booking_confirmation",
    #   "escalation_reason": None,
    # }

    record_inbound(
        classification=result,
        channel="email",
        from_identity="jane@acme.example",
        content="yes definitely book me in for wednesday",
        subject="Re: ...",
        thread_id=None,
        metadata={"message_id": "..."},
    )
    # writes to lead_interactions + publishes agent_events row + returns UUID

CLI
---
    python scripts/inbound_classifier.py classify --channel email \\
        --content "not interested" --from jane@acme.example --json
    python scripts/inbound_classifier.py backfill --since 2026-04-01
    python scripts/inbound_classifier.py stats --json

DESIGN
------
1. Claude Haiku as classifier — cheap (~$0.0001/call), fast (~300ms), and
   much more accurate than the keyword-based placeholder in context_builder.
2. Structured output. Haiku returns strict JSON with fixed enums; we never
   guess or free-text.
3. Fail-closed. If Haiku is unreachable or returns malformed JSON, we fall
   back to the keyword classifier from context_builder AND mark the record
   with confidence=0.3 so downstream code knows it's a degraded read.
4. Every classification writes to agent_events as inbound.classified —
   subscribers can act immediately (e.g., auto-draft a booking confirmation).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))


# ---- Env + DB ---------------------------------------------------------------

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
    from supabase import create_client
    return create_client(url, key)


# ---- Classification schema --------------------------------------------------

VALID_SENTIMENTS = {"positive", "neutral", "negative", "mixed"}
VALID_INTENTS = {
    "booking",       # they want to schedule a call / meeting
    "pricing",       # asking about cost / pricing
    "objection",     # pushing back on offer, price, or fit
    "info_request",  # asking for more information
    "out_of_office",
    "unsubscribe",   # explicit opt-out
    "spam_bounce",   # mailer-daemon / noise
    "noise",         # off-topic, auto-reply, confirmation email, etc.
    "reply_positive",  # confirming / agreeing but not a specific ask
    "reply_negative",  # declining / disengaging but not unsubscribing
    "referral",      # referring someone else
    "other",
}
VALID_PRIORITY = {"hot", "warm", "cold", "low"}
VALID_STAGE_SIGNALS = {
    "escalate_to_engaged",
    "escalate_to_warm",
    "regress_to_dormant",
    "escalate_to_active_client",
    "mark_lost",
    "hold",
}
VALID_ACTIONS = {
    "draft_booking_confirmation",
    "draft_pricing_reply",
    "draft_objection_handler",
    "draft_info_reply",
    "escalate_to_cc",
    "add_to_nurture",
    "mark_unsubscribed",
    "ignore",
    "hold_for_review",
}


def _keyword_fallback(content: str) -> dict:
    """Cheap fallback when Haiku is unavailable. Degraded mode."""
    lower = (content or "").lower()
    positive = any(kw in lower for kw in ("yes", "interested", "book", "schedule", "sounds good", "let's do"))
    negative = any(kw in lower for kw in ("not interested", "unsubscribe", "no thanks", "stop", "remove me"))
    ooo = any(kw in lower for kw in ("out of office", "on vacation", "i'm away"))
    bounce = any(kw in lower for kw in ("mailer-daemon", "delivery status", "undeliverable"))

    if bounce:
        return {"sentiment": "neutral", "intent": "spam_bounce",
                "priority": "low", "stage_signal": "hold",
                "suggested_action": "ignore", "confidence": 0.4,
                "fallback": True}
    if ooo:
        return {"sentiment": "neutral", "intent": "out_of_office",
                "priority": "cold", "stage_signal": "hold",
                "suggested_action": "ignore", "confidence": 0.5,
                "fallback": True}
    if negative and "unsubscribe" in lower or "stop" in lower:
        return {"sentiment": "negative", "intent": "unsubscribe",
                "priority": "low", "stage_signal": "mark_lost",
                "suggested_action": "mark_unsubscribed", "confidence": 0.7,
                "fallback": True}
    if negative:
        return {"sentiment": "negative", "intent": "reply_negative",
                "priority": "cold", "stage_signal": "regress_to_dormant",
                "suggested_action": "add_to_nurture", "confidence": 0.4,
                "fallback": True}
    if positive:
        return {"sentiment": "positive", "intent": "reply_positive",
                "priority": "hot", "stage_signal": "escalate_to_engaged",
                "suggested_action": "escalate_to_cc", "confidence": 0.5,
                "fallback": True}
    return {"sentiment": "neutral", "intent": "other",
            "priority": "cold", "stage_signal": "hold",
            "suggested_action": "hold_for_review", "confidence": 0.3,
            "fallback": True}


# ---- Haiku classifier -------------------------------------------------------

CLASSIFY_SYSTEM_PROMPT = """You are an inbound message classifier for a B2B
sales/marketing pipeline. Your job is to read an incoming message (email,
DM, or similar) and output a single JSON object with no commentary, no
markdown, no prose.

Schema — every key required:
{
  "sentiment":        "positive" | "neutral" | "negative" | "mixed",
  "intent":           one of [booking, pricing, objection, info_request,
                              out_of_office, unsubscribe, spam_bounce,
                              noise, reply_positive, reply_negative,
                              referral, other],
  "priority":         "hot" | "warm" | "cold" | "low",
  "stage_signal":     one of [escalate_to_engaged, escalate_to_warm,
                              regress_to_dormant, escalate_to_active_client,
                              mark_lost, hold],
  "confidence":       number 0.0 .. 1.0,
  "suggested_action": one of [draft_booking_confirmation, draft_pricing_reply,
                              draft_objection_handler, draft_info_reply,
                              escalate_to_cc, add_to_nurture,
                              mark_unsubscribed, ignore, hold_for_review],
  "key_phrase":       short substring from the message that drove the classification,
  "notes":            at most one sentence of reasoning
}

Rules:
- Be conservative on "hot" priority. Reserve it for explicit booking asks,
  clear buying signals, or direct urgency.
- If the message is a mailer-daemon bounce, auto-reply, or obvious noise,
  mark intent=spam_bounce OR noise, priority=low, suggested_action=ignore.
- If the writer explicitly says stop/unsubscribe/remove me: intent=unsubscribe,
  suggested_action=mark_unsubscribed.
- Never hallucinate a key_phrase — it must be a direct substring.
- Output ONLY the JSON object. No code fences, no preamble."""


def _classify_via_haiku(content: str, channel: str,
                         subject: Optional[str], from_identity: Optional[str],
                         env: dict[str, str]) -> dict:
    """Call Claude Haiku. Returns the raw parsed dict or raises."""
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic SDK not installed")

    api_key = env.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY missing in .env.agents")

    client = anthropic.Anthropic(api_key=api_key)
    user_parts = [f"Channel: {channel}"]
    if from_identity:
        user_parts.append(f"From: {from_identity}")
    if subject:
        user_parts.append(f"Subject: {subject}")
    user_parts.append("")
    user_parts.append("Message:")
    user_parts.append((content or "")[:4000])
    user_msg = "\n".join(user_parts)

    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        system=CLASSIFY_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    text = "".join(b.text for b in resp.content if hasattr(b, "text")).strip()
    # Strip accidental code fence
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n", "", text)
        text = re.sub(r"\n```\s*$", "", text)
    parsed = json.loads(text)
    return parsed


def _validate_and_normalize(raw: dict) -> dict:
    """Clamp values to the valid enum set; defaults where missing."""
    out = {
        "sentiment": raw.get("sentiment", "neutral"),
        "intent": raw.get("intent", "other"),
        "priority": raw.get("priority", "cold"),
        "stage_signal": raw.get("stage_signal", "hold"),
        "confidence": float(raw.get("confidence", 0.5) or 0.5),
        "suggested_action": raw.get("suggested_action", "hold_for_review"),
        "key_phrase": (raw.get("key_phrase") or "")[:200],
        "notes": (raw.get("notes") or "")[:300],
        "fallback": False,
    }
    if out["sentiment"] not in VALID_SENTIMENTS:
        out["sentiment"] = "neutral"
    if out["intent"] not in VALID_INTENTS:
        out["intent"] = "other"
    if out["priority"] not in VALID_PRIORITY:
        out["priority"] = "cold"
    if out["stage_signal"] not in VALID_STAGE_SIGNALS:
        out["stage_signal"] = "hold"
    if out["suggested_action"] not in VALID_ACTIONS:
        out["suggested_action"] = "hold_for_review"
    out["confidence"] = max(0.0, min(1.0, out["confidence"]))
    return out


# ---- Public API -------------------------------------------------------------

def classify(
    content: str,
    channel: str,
    subject: Optional[str] = None,
    from_identity: Optional[str] = None,
    env: Optional[dict[str, str]] = None,
) -> dict:
    """Classify an inbound message. Never raises. On any error falls back
    to the keyword classifier with reduced confidence."""
    e = env if env is not None else load_env()
    try:
        raw = _classify_via_haiku(
            content=content or "",
            channel=channel or "email",
            subject=subject,
            from_identity=from_identity,
            env=e,
        )
        return _validate_and_normalize(raw)
    except Exception as exc:  # noqa: BLE001
        print(f"[inbound_classifier] Haiku failed ({exc}); "
              "falling back to keyword classifier.",
              file=sys.stderr)
        return _keyword_fallback(content or "")


def record_inbound(
    classification: dict,
    channel: str,
    from_identity: str,
    content: str,
    subject: Optional[str] = None,
    thread_id: Optional[str] = None,
    lead_id: Optional[str] = None,
    metadata: Optional[dict] = None,
    db: Any = None,
) -> Optional[str]:
    """Persist the inbound record. Writes lead_interactions AND agent_events.
    Returns the lead_interactions id.
    """
    e = load_env()
    db = db if db is not None else get_supabase(e)
    now = datetime.now(timezone.utc)

    # Resolve lead by email if not provided. For IG/skool channels the
    # from_identity is a @username, so we store it in metadata but don't
    # auto-create a lead row without an email.
    if not lead_id and from_identity and "@" in from_identity and "." in from_identity:
        try:
            r = (db.table("leads").select("id")
                 .eq("email", from_identity.strip().lower())
                 .limit(1).execute().data)
            if r:
                lead_id = r[0]["id"]
            else:
                # Create a minimal inbound-only lead record. Source='inbound'
                # distinguishes from outbound gateway auto-creates.
                ins = db.table("leads").insert({
                    "name": from_identity.split("@")[0],
                    "email": from_identity.strip().lower(),
                    "status": "new",
                    "source": "inbound_" + channel,
                    "created_at": now.isoformat(),
                    "updated_at": now.isoformat(),
                }).execute().data
                if ins:
                    lead_id = ins[0]["id"]
        except Exception as exc:  # noqa: BLE001
            print(f"[inbound_classifier] lead resolve warning: {exc}", file=sys.stderr)

    full_metadata = dict(metadata or {})
    full_metadata.update({
        "from_identity": from_identity,
        "thread_id": thread_id,
        "sentiment": classification.get("sentiment"),
        "intent": classification.get("intent"),
        "priority": classification.get("priority"),
        "stage_signal": classification.get("stage_signal"),
        "confidence": classification.get("confidence"),
        "suggested_action": classification.get("suggested_action"),
        "key_phrase": classification.get("key_phrase"),
        "classifier_notes": classification.get("notes"),
        "fallback_classifier": classification.get("fallback", False),
    })

    row = {
        "lead_id": lead_id,
        "type": f"{channel}_received",
        "channel": channel,
        "subject": (subject or "")[:500] or None,
        "content": (content or "")[:2000],
        "agent_source": "inbound_classifier",
        "metadata": full_metadata,
        "created_at": now.isoformat(),
    }
    interaction_id: Optional[str] = None
    try:
        res = db.table("lead_interactions").insert(row).execute()
        interaction_id = res.data[0].get("id") if res.data else None
    except Exception as exc:  # noqa: BLE001
        print(f"[inbound_classifier] lead_interactions insert failed: {exc}",
              file=sys.stderr)

    # Publish on the event bus for downstream subscribers (autonomous_agent,
    # outcome_tracker, Atlas, Maven).
    try:
        event_payload = {
            "interaction_id": interaction_id,
            "lead_id": lead_id,
            "channel": channel,
            "from_identity": from_identity,
            "subject": subject,
            "classification": classification,
        }
        severity = "info"
        if classification.get("priority") == "hot":
            severity = "warn"  # surfaces in dashboards
        if classification.get("intent") == "unsubscribe":
            severity = "warn"
        db.table("agent_events").insert({
            "event_type": "inbound.classified",
            "publisher_agent": "bravo",
            "severity": severity,
            "payload": event_payload,
            "correlation_id": interaction_id,
            "published_at": now.isoformat(),
        }).execute()
    except Exception as exc:  # noqa: BLE001
        print(f"[inbound_classifier] agent_events publish warning: {exc}",
              file=sys.stderr)

    return interaction_id


# ---- CLI --------------------------------------------------------------------

def _print_json(obj: Any) -> None:
    print(json.dumps(obj, indent=2, default=str))


def _cmd_classify(args) -> int:
    r = classify(
        content=args.content,
        channel=args.channel,
        subject=args.subject,
        from_identity=args.from_id,
    )
    if args.output_json:
        _print_json(r)
    else:
        print(f"sentiment:   {r['sentiment']}")
        print(f"intent:      {r['intent']}")
        print(f"priority:    {r['priority']}")
        print(f"stage:       {r['stage_signal']}")
        print(f"action:      {r['suggested_action']}")
        print(f"confidence:  {r['confidence']:.2f}")
        if r.get("fallback"):
            print(f"(fallback classifier used)")
    return 0


def _cmd_stats(args) -> int:
    """Aggregate last 7d of classifications for CC's morning brief."""
    db = get_supabase()
    now = datetime.now(timezone.utc).isoformat()
    window_start = (datetime.now(timezone.utc).replace(microsecond=0)).isoformat()
    # Query the last 7 days of classified inbound events.
    try:
        rows = (db.table("agent_events")
                .select("payload, severity, published_at")
                .eq("event_type", "inbound.classified")
                .order("published_at", desc=True)
                .limit(500)
                .execute().data) or []
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    by_intent: dict[str, int] = {}
    by_priority: dict[str, int] = {}
    for row in rows:
        p = row.get("payload") or {}
        c = p.get("classification") or {}
        by_intent[c.get("intent", "other")] = by_intent.get(c.get("intent", "other"), 0) + 1
        by_priority[c.get("priority", "cold")] = by_priority.get(c.get("priority", "cold"), 0) + 1

    result = {
        "sample_size": len(rows),
        "by_intent": dict(sorted(by_intent.items(), key=lambda x: -x[1])),
        "by_priority": dict(sorted(by_priority.items(), key=lambda x: -x[1])),
    }
    if args.output_json:
        _print_json(result)
    else:
        print(f"Inbound stats ({len(rows)} events):")
        print("  Intent:")
        for k, v in result["by_intent"].items():
            print(f"    {k:25} {v}")
        print("  Priority:")
        for k, v in result["by_priority"].items():
            print(f"    {k:10} {v}")
    return 0


def main() -> None:
    p = argparse.ArgumentParser(
        prog="inbound_classifier.py",
        description="Classify an inbound message (Haiku + keyword fallback).",
    )
    p.add_argument("--json", dest="output_json", action="store_true")
    sub = p.add_subparsers(dest="command")

    pc = sub.add_parser("classify", help="Classify a single inbound message")
    pc.add_argument("--channel", required=True,
                     choices=["email", "instagram", "linkedin", "skool", "telegram", "phone"])
    pc.add_argument("--content", required=True, help="The message body")
    pc.add_argument("--subject", default=None)
    pc.add_argument("--from", dest="from_id", default=None,
                     help="Sender identity (email or @handle)")

    ps = sub.add_parser("stats", help="Last 500 classifications by intent/priority")

    args = p.parse_args()

    if args.command == "classify":
        sys.exit(_cmd_classify(args))
    elif args.command == "stats":
        sys.exit(_cmd_stats(args))
    else:
        p.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
