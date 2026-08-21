"""instagram_dm_poller.py — answer OASIS Instagram DMs and turn them into leads.

Someone DMs @oasisaisolutions with buying intent; they get the AI-audit form
back within a minute and land in the CRM as a lead with their handle attached.

WHY POLLING AND NOT A WEBHOOK. Zernio supports both. Polling was chosen because
every endpoint it needs is verified working today, it needs no public URL or
dashboard step, and — the operator's actual requirement — a cron job SHOWS UP in
the Automations tab and can be switched off there. A passive webhook endpoint
would be invisible on that screen. The classify/reply/upsert core is identical
either way, so moving to webhooks later costs nothing.

VERIFIED ZERNIO API (probed live 2026-08-20, see docs/INSTAGRAM_DM_AUTOMATION_SPEC.md):
    GET  /v1/inbox/conversations
    GET  /v1/inbox/conversations/{id}/messages?accountId=...
    POST /v1/inbox/conversations/{id}/messages  {"accountId":..., "message":...}
Zernio answers 200 with its web-app HTML for ANY unknown path, so never treat a
200 as proof a route exists — compare the body against a known-fake control.

SAFETY, in the order it is enforced:
  1. Dry run unless --live. Nothing leaves the machine by default.
  2. Only @oasisaisolutions on instagram. Every other connected profile is out
     of scope, exactly as the New Haven build pinned to its own profile.
  3. --only-handle restricts sending to one handle, so the first live test goes
     to CC's own account and never a real prospect.
  4. One auto-reply per sender per 24h, keyed on participantId.
  5. Non-matching DMs are logged, never answered. A wrong auto-reply to a real
     human costs more than a missed one.

Usage:
    python scripts/integrations/instagram_dm_poller.py                  # dry run
    python scripts/integrations/instagram_dm_poller.py --live --only-handle ccmckennaa
    python scripts/integrations/instagram_dm_poller.py --live           # armed
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "integrations"))

CAPABILITY_META = {
    "category": "growth.inbound",
    "lifecycle": "active",
    "risk": "external_send",
    "triggers": ["instagram dm automation", "poll instagram dms", "answer instagram dms"],
    "owner": "bravo",
    "project": "oasis",
    "bridge": {"visible": True},
}

API_BASE = "https://zernio.com/api"
TARGET_PLATFORM = "instagram"
TARGET_ACCOUNT = "oasisaisolutions"

OASIS_TENANT_ID = "ef8d389e-3f15-43f2-ae00-3660f69a1452"
STATE_PATH = PROJECT_ROOT / "state" / "instagram_dm_state.json"
COOLDOWN_HOURS = 24

AUDIT_FORM_URL = "https://oasisai.work/f/oasis-ai-cc/ai-audit"

# Buying intent for an AI-automation agency. Deliberately narrower than a
# catch-all: a false positive auto-replies to a human who did not ask.
INTENT_KEYWORDS = (
    "audit", "automation", "automate", "automating", "website", "web site",
    "site", "pricing", "price", "cost", "quote", "how much", "interested",
    "info", "information", "help", "book", "call", "demo", "consult", "ai",
    "agent", "chatbot", "lead", "crm", "work with", "hire",
)

REPLY_TEMPLATE = (
    "Hey {name} — thanks for reaching out.\n\n"
    "Quickest way to get you a real answer: this short form asks what you're "
    "running and where the time goes. It takes about a minute and I read every "
    "one personally.\n\n"
    "{url}\n\n"
    "Once it's in I'll come back with the specific bottleneck I'd automate first."
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _api_key() -> str:
    from lib.secret_loader import load_env  # type: ignore

    key = (load_env().get("LATE_API_KEY") or "").strip()
    if not key:
        raise SystemExit("ERROR: LATE_API_KEY missing from the agents env")
    return key


def _request(key: str, path: str, method: str = "GET", body: dict | None = None) -> dict:
    """Call Zernio. Raises on a non-JSON body, because a 200 of HTML means the
    route does not exist and must never be read as success."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        API_BASE + path,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"{method} {path} -> HTTP {exc.code}: {detail}") from exc
    if raw.lstrip().startswith("<"):
        raise RuntimeError(f"{method} {path} returned HTML — that route does not exist")
    return json.loads(raw) if raw.strip() else {}


def _load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print("  [warn] state file unreadable; starting fresh", file=sys.stderr)
    return {"replied": {}, "seen_messages": []}


def _save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Keep the seen list bounded so the file cannot grow without limit.
    state["seen_messages"] = state.get("seen_messages", [])[-2000:]
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _in_cooldown(state: dict, participant_id: str) -> bool:
    last = state.get("replied", {}).get(participant_id)
    if not last:
        return False
    try:
        return datetime.fromisoformat(last) > _now() - timedelta(hours=COOLDOWN_HOURS)
    except ValueError:
        return False


def matches_intent(text: str) -> str | None:
    """Return the keyword that matched, or None. Exposed for testing."""
    low = (text or "").lower()
    for kw in INTENT_KEYWORDS:
        if kw in low:
            return kw
    return None


def _incoming_text(messages: list[dict], account_id: str) -> tuple[str, str]:
    """Newest message that came FROM the contact, as (message_id, text).

    Skips our own outbound messages — replying to ourselves would loop.
    """
    for m in reversed(messages):
        sender = str(m.get("senderId") or m.get("from") or "")
        if sender and sender == account_id:
            continue
        if str(m.get("direction") or "").lower() in {"out", "outbound", "sent"}:
            continue
        text = m.get("text") or m.get("message") or m.get("body") or ""
        if text:
            return str(m.get("id") or m.get("_id") or ""), str(text)
    return "", ""


def _upsert_lead(conv: dict, text: str, matched: str) -> str:
    """Create the CRM lead if this handle is new. Returns a status word."""
    from supabase_tool import get_client, load_env  # type: ignore

    db = get_client(load_env())
    handle = conv.get("participantUsername") or conv.get("participantId") or "unknown"
    rows = (
        db.table("tenant_records")
        .select("id,data")
        .eq("tenant_id", OASIS_TENANT_ID)
        .eq("entity_type", "lead")
        .limit(500)
        .execute()
    ).data or []
    for r in rows:
        d = r.get("data") or {}
        if isinstance(d, str):
            try:
                d = json.loads(d)
            except json.JSONDecodeError:
                continue
        if (d.get("instagram_handle") or "").lower() == str(handle).lower():
            return "existing"

    now = _iso(_now())
    data = {
        "name": conv.get("participantName") or handle,
        "company": None,
        "email": None,
        "phone": None,
        "source": "instagram_dm",
        "stage": "researched",
        "score": 55,
        "value_estimate": None,
        "notes": f"Instagram DM (@{handle}) matched '{matched}': {text[:180]}",
        "instagram_handle": handle,
        "instagram_profile_url": conv.get("url"),
        "first_dm_at": now,
        "first_dm_text": text[:500],
        "stage_entered_at": now,
        "created_from": "instagram_dm_poller",
    }
    db.table("tenant_records").insert(
        {
            "id": str(uuid.uuid4()),
            "tenant_id": OASIS_TENANT_ID,
            "entity_type": "lead",
            "data": data,
            "created_at": now,
            "updated_at": now,
        }
    ).execute()
    return "created"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--live", action="store_true", help="actually send replies")
    p.add_argument("--only-handle", help="send only to this handle (first live test)")
    p.add_argument("--limit", type=int, default=25, help="max conversations to examine")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    key = _api_key()
    state = _load_state()
    summary = {
        "scanned": 0, "in_scope": 0, "matched": 0,
        "replied": 0, "skipped_cooldown": 0, "skipped_no_match": 0,
        "skipped_seen": 0, "leads_created": 0, "errors": 0,
        "live": args.live,
    }

    convos = _request(key, "/v1/inbox/conversations").get("data") or []
    print(f"{len(convos)} conversation(s) in the Zernio inbox"
          f"{' — DRY RUN' if not args.live else ' — LIVE'}")

    for conv in convos[: args.limit]:
        summary["scanned"] += 1
        if conv.get("platform") != TARGET_PLATFORM:
            continue
        if (conv.get("accountUsername") or "").lower() != TARGET_ACCOUNT:
            continue
        summary["in_scope"] += 1

        handle = conv.get("participantUsername") or conv.get("participantId") or "?"
        pid = str(conv.get("participantId") or handle)
        account_id = conv.get("accountId") or ""
        conv_id = conv.get("id") or ""

        try:
            # NOTE: this endpoint returns {"messages": [...]}, while
            # /v1/inbox/conversations returns {"data": [...]}. Reading "data"
            # here silently yields zero messages and every conversation looks
            # empty — which is exactly how the first dry run reported 8 in-scope
            # conversations and no text at all.
            msgs = _request(
                key, f"/v1/inbox/conversations/{conv_id}/messages?accountId={account_id}"
            ).get("messages") or []
        except RuntimeError as exc:
            summary["errors"] += 1
            print(f"  [error] @{handle}: {exc}", file=sys.stderr)
            continue

        msg_id, text = _incoming_text(msgs, account_id)
        if not text:
            continue
        if msg_id and msg_id in state.get("seen_messages", []):
            summary["skipped_seen"] += 1
            continue

        matched = matches_intent(text)
        if not matched:
            summary["skipped_no_match"] += 1
            print(f"  @{handle}: no intent match — logged only: {text[:60]!r}")
            if msg_id:
                state.setdefault("seen_messages", []).append(msg_id)
            continue

        summary["matched"] += 1
        if _in_cooldown(state, pid):
            summary["skipped_cooldown"] += 1
            print(f"  @{handle}: matched '{matched}' but replied within {COOLDOWN_HOURS}h — skipping")
            continue
        if args.only_handle and str(handle).lower() != args.only_handle.lower():
            print(f"  @{handle}: matched '{matched}' — held (--only-handle {args.only_handle})")
            continue

        reply = REPLY_TEMPLATE.format(
            name=(conv.get("participantName") or handle).split()[0],
            url=AUDIT_FORM_URL,
        )
        if not args.live:
            print(f"  @{handle}: WOULD REPLY (matched '{matched}')")
            continue

        try:
            _request(
                key,
                f"/v1/inbox/conversations/{conv_id}/messages",
                method="POST",
                body={"accountId": account_id, "message": reply},
            )
        except RuntimeError as exc:
            summary["errors"] += 1
            print(f"  [error] send to @{handle}: {exc}", file=sys.stderr)
            continue

        summary["replied"] += 1
        state.setdefault("replied", {})[pid] = _iso(_now())
        if msg_id:
            state.setdefault("seen_messages", []).append(msg_id)
        print(f"  @{handle}: REPLIED (matched '{matched}')")

        try:
            if _upsert_lead(conv, text, matched) == "created":
                summary["leads_created"] += 1
                print(f"  @{handle}: lead created")
        except Exception as exc:  # noqa: BLE001
            summary["errors"] += 1
            print(f"  [error] lead upsert for @{handle}: {exc}", file=sys.stderr)

    _save_state(state)
    print()
    print(json.dumps(summary, indent=2) if args.json
          else "  " + "  ".join(f"{k}={v}" for k, v in summary.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
