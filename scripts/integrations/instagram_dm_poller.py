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
import os
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
LOCK_PATH = PROJECT_ROOT / "state" / "instagram_dm_poller.lock"
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

# A greeting to a BUSINESS account is an inbound lead, not noise. The first
# build only answered explicit buying intent, so a real "Hello" from a real
# prospect sat unanswered — safe, but it loses the lead. Greetings now get a
# warm opener that asks the qualifying question instead of the form link;
# pushing a form at someone who only said hi reads like a bot.
GREETING_KEYWORDS = (
    "hello", "hey", "hi ", "hi!", "hi.", "yo", "sup", "howdy", "good morning",
    "good afternoon", "good evening", "what's up", "whats up", "wsp",
)

REPLY_TEMPLATE = (
    "Hey {name} — thanks for reaching out.\n\n"
    "Quickest way to get you a real answer: this short form asks what you're "
    "running and where the time goes. It takes about a minute and I read every "
    "one personally.\n\n"
    "{url}\n\n"
    "Once it's in I'll come back with the specific bottleneck I'd automate first."
)

GREETING_TEMPLATE = (
    "Hey {name} — thanks for the message.\n\n"
    "I'm the AI side of OASIS. What are you working on, and what's the part of "
    "it that eats the most of your week? If it's a website or something "
    "repetitive in your day-to-day, that's exactly what we build away.\n\n"
    "If you'd rather skip straight to it, this takes about a minute: {url}"
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


class _RunLock:
    """Refuse to start when another poll is already in flight.

    Persisting the cooldown per-reply narrows the double-send window but does
    not close it: two runs can still pass the same cooldown check microseconds
    apart. One run at a time is the actual guarantee. O_EXCL creation is atomic
    on Windows and POSIX alike, so the loser of the race gets the error rather
    than a second copy of the conversation.
    """

    def __init__(self, path: Path, stale_after_minutes: int = 15):
        self.path = path
        self.stale_after = timedelta(minutes=stale_after_minutes)
        self.acquired = False

    def __enter__(self) -> "_RunLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            # A killed run must not wedge the automation permanently.
            age = _now() - datetime.fromtimestamp(
                self.path.stat().st_mtime, tz=timezone.utc
            )
            if age > self.stale_after:
                print(f"  [warn] clearing stale lock ({int(age.total_seconds())}s old)",
                      file=sys.stderr)
                self.path.unlink(missing_ok=True)
        try:
            fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise SystemExit("another poll is already running — exiting without sending")
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        self.acquired = True
        return self

    def __exit__(self, *_exc) -> None:
        if self.acquired:
            self.path.unlink(missing_ok=True)


def _in_cooldown(state: dict, participant_id: str) -> bool:
    last = state.get("replied", {}).get(participant_id)
    if not last:
        return False
    try:
        return datetime.fromisoformat(last) > _now() - timedelta(hours=COOLDOWN_HOURS)
    except ValueError:
        return False


def matches_intent(text: str) -> str | None:
    """Return the buying-intent keyword that matched, or None."""
    low = (text or "").lower()
    for kw in INTENT_KEYWORDS:
        if kw in low:
            return kw
    return None


def classify(text: str) -> tuple[str, str | None]:
    """('intent'|'greeting'|'none', matched_keyword).

    Two tiers because they deserve different answers. Explicit buying intent
    gets the form. A bare greeting to a business account gets a human question —
    it is still a lead, but answering "hi" with a form link reads like a bot and
    burns the first impression.
    """
    kw = matches_intent(text)
    if kw:
        return "intent", kw
    low = (text or "").strip().lower()
    for g in GREETING_KEYWORDS:
        if low.startswith(g.strip()) or low == g.strip():
            return "greeting", g.strip()
    # Short openers with no other signal read as greetings too ("yooo", "hiya").
    if len(low) <= 12 and low.replace("!", "").replace(".", "").isalpha():
        return "greeting", low[:12]
    return "none", None


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


def _lead_exists(handle: str) -> bool:
    """Is there already a lead for this Instagram handle?

    Asks SQL to do the matching. The previous version read a 500-row page of
    tenant_records and compared handles in Python — against 31k leads that page
    never contained the handle, so every run believed the sender was new and
    inserted another lead. Filtering has to happen where the rows are.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from lib.db_turso import get_db  # type: ignore

    # query() returns rows; execute() returns a cursor that is truthy even when
    # it selected nothing, which would report every handle as already existing.
    rows = get_db().query(
        "select 1 as hit from tenant_records "
        "where tenant_id = ? and entity_type = 'lead' "
        "and lower(json_extract(data, '$.instagram_handle')) = lower(?) limit 1",
        (OASIS_TENANT_ID, str(handle)),
    )
    return bool(rows)


def _upsert_lead(conv: dict, text: str, matched: str) -> str:
    """Create the CRM lead if this handle is new. Returns a status word."""
    from supabase_tool import get_client, load_env  # type: ignore

    db = get_client(load_env())
    handle = conv.get("participantUsername") or conv.get("participantId") or "unknown"
    if _lead_exists(handle):
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

    # A dry run sends nothing, so it neither takes the lock nor waits on one.
    if not args.live:
        return _poll(args)
    with _RunLock(LOCK_PATH):
        return _poll(args)


def _poll(args) -> int:
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

        kind, matched = classify(text)
        if kind == "none":
            summary["skipped_no_match"] += 1
            print(f"  @{handle}: no intent or greeting — logged only: {text[:60]!r}")
            # Only a LIVE pass may consume a message. A dry run that marks
            # messages seen makes the subsequent live run skip the very DM it
            # was meant to answer -- which is exactly what swallowed CC's first
            # real test.
            if msg_id and args.live:
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

        template = REPLY_TEMPLATE if kind == "intent" else GREETING_TEMPLATE
        reply = template.format(
            name=(conv.get("participantName") or handle).split()[0],
            url=AUDIT_FORM_URL,
        )
        if not args.live:
            print(f"  @{handle}: WOULD REPLY [{kind}] (matched '{matched}')")
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
        # Persist the cooldown the moment it is earned, not at the end of the
        # run. Holding it in memory until the final save meant a run that took
        # longer than the cron interval let the next run read pre-reply state
        # and message the same person twice.
        _save_state(state)
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
