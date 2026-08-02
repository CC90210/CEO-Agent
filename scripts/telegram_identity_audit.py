#!/usr/bin/env python3
# bridge_mutating: false
#   Reviewed and declared read-only rather than left on the builder's safe
#   default. This tool issues exactly two Telegram API calls, getMe and getChat,
#   both GETs that read identity; it sends no message and writes no config. The
#   point is that it can be run freely — from the bridge, from cron — the moment
#   an alert looks like it went missing. Requiring a confirm step on a
#   diagnostic is how the diagnostic stops getting run.
#
#   Kept above the docstring deliberately: build_bridge_manifest.py:110-115
#   scans only the first 2000 characters, and the WHY section below is longer
#   than that, so a flag placed after it is silently ignored.
"""Resolve every Telegram alert lane to its ACTUAL destination.

WHY THIS EXISTS
---------------
2026-08-01: the oasisai.work funnel had been sending lead alerts to
`@KnutRPEbot` — APEX, Adon's bot — for 34 days. Every send returned `ok: true`.
Nothing was broken: retries, timeouts, status checks and the `alert_failed`
marker in `lead_interactions` all worked perfectly and all reported success,
because it *was* a success. The transport was healthy. The destination was
someone else's chat. CC simply never got the notifications and had no way to
tell why.

That failure is invisible to every check this fleet had, because every check
asked the wrong question. `capability_probe.py` asks "does a Telegram token
exist?" — it did. `notify.py` asks "did the API accept the message?" — it did.
Neither asks the only question that matters: **whose chat does this actually
reach?**

A misrouted message is indistinguishable from a delivered one at every layer a
program can observe. The single point where it becomes visible is identity
resolution: ask Telegram to name the bot and name the chat, then look at whether
that is a human who reads it.

Codex found a second instance the same day (`notify.py` group lane reading
`GROUP_TELEGRAM_CHAT_ID`, a key defined nowhere in the repo, while the
established group key is `COORD_GROUP_CHAT_ID`). Two confirmed instances across
eleven configured Telegram keys is a class of bug, not an incident — so this is
a standing check rather than a one-off script.

CONTRACT
--------
  * READ-ONLY. Calls `getMe` and `getChat`. Sends no messages, changes no
    config. Safe to run at any time, including from cron.
  * Prints IDENTIFIERS ONLY — bot usernames, chat titles, numeric ids. Never a
    token, not even a prefix or a length. A leak here would defeat
    `secret_guard`, and the whole point is that this is safe to run and read.
  * Exit 0 = every configured lane resolves to a reachable destination.
    Exit 1 = at least one lane is broken or unverifiable. A lane with no
    credential configured is not a failure; it is simply not in use.

USAGE
  python scripts/telegram_identity_audit.py
  python scripts/telegram_identity_audit.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

# Windows consoles default to cp1252, and this tool prints names chosen by other
# people — group titles, display names — which routinely contain characters
# cp1252 cannot encode. Without this the audit crashes partway through its own
# report, which would make a diagnostic that exists to expose silent failures
# fail silently itself.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001 — not a TextIOWrapper (piped/redirected)
        pass

# AVG MITMs TLS on CC's Windows rigs, so certifi cannot verify the chain and a
# stale SSLKEYLOGFILE handle can make context creation raise outright. Same
# guarded-import shape as notify.py: this must never fail to import.
try:
    from lib.tls_trust import ensure_os_trust

    ensure_os_trust()
except Exception:  # noqa: BLE001 — lib/ unreachable for this caller
    try:
        import truststore

        truststore.inject_into_ssl()
    except Exception:  # noqa: BLE001
        pass

import requests  # noqa: E402 — must follow ensure_os_trust()

TIMEOUT = 10

# Every Telegram lane the fleet actually uses, modelled on what the CODE reads —
# never on the docs table.
#
# The first version of this file got that wrong and reported three lanes broken
# when only one was, which is worth recording because it is the same mistake in
# a different coat. `capability_probe.py:80-84` already carries a comment saying
# notify.py resolves TELEGRAM_ALLOWED_USERS and *not* TELEGRAM_CHAT_ID; I keyed
# off the documented name anyway. A probe that cries wolf gets ignored, and an
# ignored probe is how the next silent misroute survives.
#
# So `chats` is a resolution ORDER, matching the `or` chains in the callers, and
# `chat_default` records a hardcoded fallback where one exists (agent_activity.py
# and coordination_agent.js both default the OASIS group id). A key being unset
# is only a failure when nothing downstream supplies a value.
#
# `reader` records who is supposed to see this lane. That is the field that would
# have caught the funnel bug: the token resolved fine and the chat resolved fine,
# and the defect was visible only as "this reaches Adon, not CC."
LANES: list[dict] = [
    {
        "lane": "bravo-bridge",
        "token": "TELEGRAM_BOT_TOKEN",
        # notify.py:226 — ("TELEGRAM_BOT_TOKEN", "TELEGRAM_ALLOWED_USERS").
        "chats": ["TELEGRAM_ALLOWED_USERS"],
        "reader": "CC (private DM)",
        "used_by": "scripts/notify.py",
    },
    {
        "lane": "coordination-group",
        "token": "CC_AGENT_BOT_TOKEN",
        "chats": ["COORD_GROUP_CHAT_ID"],
        # agent_activity.py:56 DEFAULT_GROUP_ID, coordination_agent.js:73.
        "chat_default": "-5165125484",
        "reader": "OASIS group (CC + Adon + Bravo + APEX)",
        "used_by": "coordination_agent.js, scripts/integrations/agent_activity.py",
    },
    {
        "lane": "notify-group-broadcast",
        "token": "TELEGRAM_BOT_TOKEN",
        # notify.py:343 — no fallback; an unset key means the send is refused.
        "chats": ["GROUP_TELEGRAM_CHAT_ID"],
        "reader": "OASIS group",
        "used_by": "scripts/notify.py (group=True)",
    },
    {
        "lane": "atlas-cfo",
        "token": "ATLAS_TELEGRAM_TOKEN",
        # notify.py:228 — Atlas is the one agent that really does use _CHAT_ID.
        "chats": ["ATLAS_TELEGRAM_CHAT_ID"],
        "reader": "CC",
        "used_by": "Atlas agent",
    },
    {
        "lane": "maven-cmo",
        "token": "MAVEN_TELEGRAM_BOT_TOKEN",
        # notify.py:227 + CMO-Agent/scripts/notify.py:99-106.
        "chats": ["MAVEN_TELEGRAM_ALLOWED_USERS", "MAVEN_TELEGRAM_CHAT_ID"],
        "reader": "CC",
        "used_by": "Maven agent (CMO-Agent)",
    },
    {
        "lane": "ezra",
        "token": "EZRA_TELEGRAM_BOT_TOKEN",
        # notify.py:374-379 — ALLOWED_USERS first, then _CHAT_ID.
        "chats": ["EZRA_TELEGRAM_ALLOWED_USERS", "EZRA_TELEGRAM_CHAT_ID"],
        "reader": "whoever Ezra serves — confirm, do not assume CC",
        "used_by": "Ezra agent (ezra-telegram-bridge, scrubber)",
    },
]

# The site's funnel alerts live in Vercel's production env, not .env.agents, so
# they are out of reach here. Naming them explicitly is deliberate: a silent
# omission is how the original bug hid, and an audit that quietly skips the lane
# that actually broke is worse than no audit.
OUT_OF_SCOPE = [
    (
        "oasisai.work funnel (OASIS_TELEGRAM_BOT_TOKEN / OASIS_TELEGRAM_CHAT_ID)",
        "Vercel production env — verify via GET /api/notify/telegram-identity "
        "on oasisai.work while signed in.",
    ),
]


def load_present() -> dict[str, str]:
    """Env values, kept inside this process. Nothing here is ever printed."""
    try:
        from lib.secret_loader import load_env  # noqa: PLC0415

        return dict(load_env() or {})
    except Exception as exc:  # noqa: BLE001
        print(f"[audit] could not load env: {exc}", file=sys.stderr)
        return {}


def api(token: str, method: str, params: dict | None = None) -> tuple[bool, dict | str]:
    """One Telegram API call. Returns (ok, payload-or-error-description).

    Errors surface Telegram's own `description` rather than a bare status code:
    "chat not found" and "bot was blocked by the user" are different problems
    with different fixes, and collapsing them into "failed" is what makes an
    alerting bug take 34 days to find.
    """
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{token}/{method}",
            params=params or {},
            timeout=TIMEOUT,
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"transport error: {type(exc).__name__}"
    try:
        body = r.json()
    except ValueError:
        return False, f"HTTP {r.status_code}, non-JSON body"
    if not body.get("ok"):
        return False, str(body.get("description") or f"HTTP {r.status_code}")
    return True, body.get("result") or {}


def describe_chat(result: dict) -> str:
    """Human-readable chat identity. Identifiers only."""
    kind = result.get("type") or "?"
    if result.get("title"):
        name = result["title"]
    elif result.get("username"):
        name = "@" + result["username"]
    else:
        name = " ".join(
            str(result.get(k) or "") for k in ("first_name", "last_name")
        ).strip() or "(unnamed)"
    return f"{kind}:{name} (id {result.get('id')})"


def resolve_chat(lane: dict, env: dict[str, str]) -> tuple[str, str]:
    """Chat id for a lane, following the caller's own resolution order.

    Returns (chat_id, which-source-supplied-it). ALLOWED_USERS keys hold a comma
    list and notify.py:394 takes the first entry, so this does too — auditing a
    different element than the code sends to would prove nothing.
    """
    for key in lane["chats"]:
        raw = (env.get(key) or "").strip()
        if not raw:
            continue
        first = next((c.strip() for c in raw.split(",") if c.strip()), "")
        if first:
            return first, key
    default = lane.get("chat_default")
    if default:
        return default, "hardcoded default in caller"
    return "", ""


def audit_lane(lane: dict, env: dict[str, str]) -> dict:
    """Resolve one lane. Never returns or logs a token."""
    out: dict = {
        "lane": lane["lane"],
        "reader_expected": lane["reader"],
        "used_by": lane["used_by"],
        "token_key": lane["token"],
        "chat_keys": lane["chats"],
    }
    token = (env.get(lane["token"]) or "").strip()
    chat, source = resolve_chat(lane, env)
    out["chat_source"] = source

    if not token and not chat:
        out["status"] = "not-configured"
        out["detail"] = "no token, no chat id — lane unused"
        return out
    if not token:
        out["status"] = "BROKEN"
        out["detail"] = f"a chat id is set but {lane['token']} is missing"
        return out
    if not chat:
        out["status"] = "BROKEN"
        out["detail"] = (
            f"{lane['token']} is set but no chat id resolves from "
            + " -> ".join(lane["chats"])
            + " (and the caller has no fallback), so sends on this lane are refused"
        )
        return out

    ok, me = api(token, "getMe")
    if not ok:
        out["status"] = "BROKEN"
        out["detail"] = f"getMe failed: {me}"
        return out
    out["bot"] = "@" + str(me.get("username") or "?")
    out["bot_id"] = me.get("id")

    ok, chat_info = api(token, "getChat", {"chat_id": chat})
    if not ok:
        out["status"] = "BROKEN"
        out["detail"] = (
            f"{out['bot']} cannot reach chat {chat}: {chat_info}. "
            "The bot and the chat id belong to different accounts, or the bot "
            "was never started in that chat."
        )
        return out
    out["status"] = "ok"
    out["destination"] = describe_chat(chat_info)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    env = load_present()
    results = [audit_lane(lane, env) for lane in LANES]

    if args.json:
        print(json.dumps({"lanes": results, "unverifiable": OUT_OF_SCOPE}, indent=2))
    else:
        print("TELEGRAM IDENTITY AUDIT — where each alert lane actually lands\n")
        for r in results:
            mark = {"ok": "OK  ", "BROKEN": "FAIL", "not-configured": "--  "}[r["status"]]
            print(f"  {mark} {r['lane']}")
            if r["status"] == "ok":
                print(f"       bot         {r['bot']} (id {r['bot_id']})")
                print(f"       reaches     {r['destination']}")
                print(f"       should read {r['reader_expected']}")
                print(f"       chat from   {r['chat_source']}")
            else:
                print(f"       {r['detail']}")
            print(f"       used by     {r['used_by']}")
            print()

        # Two lanes resolving to the same destination is normal. Two lanes that
        # are SUPPOSED to reach the same human but resolve differently is the
        # funnel bug — so print the grouping and let it be obvious.
        live = [r for r in results if r["status"] == "ok"]
        if live:
            byd: dict[str, list[str]] = {}
            for r in live:
                byd.setdefault(r["destination"], []).append(r["lane"])
            print("  destinations in use:")
            for dest, lanes in byd.items():
                print(f"    {dest}  <-  {', '.join(lanes)}")
            print()

        print("  NOT verifiable from this repo:")
        for name, how in OUT_OF_SCOPE:
            print(f"    {name}\n      {how}")
        print()

    broken = [r for r in results if r["status"] == "BROKEN"]
    if broken:
        print(
            f"{len(broken)} lane(s) broken: "
            + ", ".join(r["lane"] for r in broken),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
