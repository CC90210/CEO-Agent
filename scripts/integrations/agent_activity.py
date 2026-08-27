"""
agent_activity — Bravo's client for the cross-org coordination channel.

The `agent_activity` table (bravo Supabase) is how Bravo (CC's agent) and APEX
(Adon's agent, @KnutRPEbot) read each other. Telegram bots cannot see each
other's messages, so this table — NOT the group chat — is the agent<->agent
source of truth. Each agent also mirrors its status into the OASIS Telegram
group (-5165125484) so CC + Adon see who's doing what.

This CLI is shared by two callers:
  • coordination_agent.js — the standalone group bridge (reads peers, posts status)
  • any spawned Claude/Codex session — so the agent doing the work can claim
    files, post progress, and release, consistently (CLI-first per RULE 2).

PROTOCOL (both agents follow it):
  1. BEFORE starting a task: read recent rows + peer claims. Do NOT edit files
     the other agent has an open start/working row on.
  2. On start/working/done/blocked: insert a row AND mirror the line to the group.

Usage:
  python scripts/integrations/agent_activity.py recent [--hours 3] [--limit 30] [--json]
  python scripts/integrations/agent_activity.py peers [--hours 6] [--json]      # what APEX has open
  python scripts/integrations/agent_activity.py claims [--hours 6] [--json]     # files APEX is touching
  python scripts/integrations/agent_activity.py post --status start \
        --task "Batch 3 (app doc slot)" --files components/x.tsx,app/y.ts \
        --branch cc/batch-3 --detail "starting" [--mirror] [--json]
  python scripts/integrations/agent_activity.py line --status done --task "Batch 3"   # preview only

Credentials come from .env.agents via supabase_tool (service-role, bravo project).
Never hardcode secrets. Telegram mirror uses CC_AGENT_BOT_TOKEN + COORD_GROUP_CHAT_ID.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Sibling import — supabase_tool.py lives in this directory and owns the
# canonical .env.agents loader + service-role client construction.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import supabase_tool  # noqa: E402

# Windows consoles default to cp1252 and choke on the status emojis. The
# Telegram HTTP path sends UTF-8 regardless; this only fixes local stdout.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

TABLE = "agent_activity"
DEFAULT_GROUP_ID = -5165125484  # OASIS coordination group

# This agent's identity in the table (the APEX contract value) and the
# human-facing label in the group line. Both overridable via env.
# Bravo's WIRE key stays "cc-agent" until APEX acknowledges the rename.
#
# Canonical identity is "bravo" (see brain/OWNERSHIP_MAP.yaml and coord_claim.ME),
# and this SHOULD become "bravo". It has not been flipped yet on purpose: APEX's
# poller filters Bravo's rows with agent=eq.cc-agent, so flipping unilaterally
# would make Bravo invisible to APEX. That is not hypothetical — on 2026-08-16 a
# single row was written under "bravo" instead of "cc-agent" and APEX never saw
# it. Renaming a key both sides filter on is a COORDINATED change; it is gated on
# APEX confirming it reads SELF_KEYS, per the handover doc's rename step.
ME_KEY = os.environ.get("COORD_AGENT_KEY", "cc-agent")
ME_LABEL = os.environ.get("COORD_AGENT_LABEL", "BRAVO")
# Every key that has ever meant "this agent". Used for self-exclusion so Bravo
# never reacts to its own rows regardless of which key wrote them — the 90 days
# to 2026-08-27 contain rows under BOTH "cc-agent" (108) and "bravo" (1).
SELF_KEYS = [k.strip() for k in os.environ.get(
    "COORD_SELF_KEYS", "cc-agent,bravo").split(",") if k.strip()]
# Adon's agent answers to BOTH names: "Apex" is the persona, "Knut" is the bot
# (@KnutRPEbot). They are one system, not two peers. Defaulting to "apex" alone
# meant a row written under agent="knut" was invisible to every peer read —
# claims(), peers(), and the coordination bridge's fresh-row poll all filter on
# this list, so a Knut-authored file claim would not have blocked Bravo from
# editing the same file. Same entity, both keys.
PEER_KEYS = [k.strip() for k in os.environ.get("COORD_PEER_KEYS", "apex,knut").split(",") if k.strip()]

# `ack` added 2026-08-27: two-step verification. A change to a surface the
# ownership map assigns to the OTHER agent needs that agent to acknowledge it
# before merge. Without a distinct status there was no way to record "the peer
# has seen and accepted this" — it lived in prose in the group chat, where
# neither agent could query it.
VALID_STATUS = ("start", "working", "done", "blocked", "ack")
_STATUS_EMOJI = {"start": "🟧", "working": "🟧", "done": "🟩",
                 "blocked": "🟥", "ack": "🟦"}

# Channel-isolation denylists, IMPORTED from notify.py rather than copied.
#
# This module and notify.py are the two Python doors into the OASIS partner
# group, and they must agree. A first version duplicated the pattern here with
# a comment saying "kept in sync" — and it drifted within the hour: notify.py
# gained _NOT_BRAVO_DOMAIN_RE (TextTorrent / TPS / phone_lookup, dropped on CC's
# 2026-08-03 instruction) while this copy did not, so "TextTorrent sender pool
# exhausted" was still mirrorable straight into the group. One definition
# removes the failure mode instead of testing for it.
#
# This is the lane that actually REACHES the group: telegram_identity_audit.py
# shows notify.py's group=True lane resolving no chat id at all ("sends on this
# lane are refused"), while this module holds a live handle on
# @BravoGCAdon_bot -> group:OASIS 🏝️💸. Guarding only notify.py guarded the
# dead door.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from notify import (  # noqa: E402
    _GROUP_BLOCKED_TERMS_RE,   # wrong AUDIENCE — internal ops, not for partners
    _NOT_BRAVO_DOMAIN_RE,      # wrong OWNER — APEX/Adon's domain, drop entirely
)


def _client():
    env = supabase_tool.load_env()
    return supabase_tool.get_client(env, project="bravo")


def _env_value(key):
    """Read a single value from .env.agents without echoing the whole file."""
    env_path = Path(__file__).resolve().parent.parent.parent / ".env.agents"
    if not env_path.exists():
        return None
    for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if line.startswith(f"{key}="):
            return line.partition("=")[2].strip() or None
    return None


# --------------------------------------------------------------------------
# Formatting
# --------------------------------------------------------------------------

def format_line(status, task, files=None, branch=None, detail=None, label=None):
    """Build the canonical status line (matches the APEX/coordination doc)."""
    label = label or ME_LABEL
    emoji = _STATUS_EMOJI.get(status, "⬜")
    parts = [f"{emoji} {label} · {status.upper()}", task or "(no task)"]
    if files:
        flist = files if isinstance(files, list) else [files]
        parts.append("files: " + ", ".join(flist))
    if branch:
        parts.append(f"branch {branch}")
    if detail:
        parts.append(detail)
    return " · ".join(parts)


# --------------------------------------------------------------------------
# Reads
# --------------------------------------------------------------------------

def _since(hours):
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


def recent(hours=3, limit=30, exclude_agent=None):
    q = (_client().table(TABLE)
         .select("id,agent,status,task,files,branch,detail,created_at")
         .gte("created_at", _since(hours))
         .order("created_at", desc=True)
         .limit(limit))
    if exclude_agent:
        q = q.neq("agent", exclude_agent)
    return q.execute().data or []


def peer_open(hours=6, peers=None):
    """Open work by the OTHER agent(s): latest row per (agent, task) whose
    status is start/working (i.e. not yet done/blocked)."""
    peers = peers or PEER_KEYS
    rows = recent(hours=hours, limit=200)
    # Filter to peers AND explicitly drop every self key. Belt and braces: a
    # misconfigured COORD_PEER_KEYS that included one of our own aliases would
    # otherwise make Bravo treat its own claim as a peer's and block itself.
    rows = [r for r in rows if r.get("agent") in peers and r.get("agent") not in SELF_KEYS]
    latest = {}
    for r in rows:  # rows are newest-first; first seen per key is the latest
        key = (r.get("agent"), r.get("task"))
        if key not in latest:
            latest[key] = r
    return [r for r in latest.values() if r.get("status") in ("start", "working")]


def claims(hours=6, peers=None):
    """Files/areas the other agent currently has claimed (open start/working)."""
    out = {}
    for r in peer_open(hours=hours, peers=peers):
        for f in (r.get("files") or []):
            out.setdefault(f, []).append({"agent": r["agent"], "task": r["task"], "branch": r.get("branch")})
    return out


# --------------------------------------------------------------------------
# Writes
# --------------------------------------------------------------------------

def post(status, task, files=None, branch=None, detail=None, mirror=False, agent=None):
    if status not in VALID_STATUS:
        raise ValueError(f"status must be one of {VALID_STATUS}, got {status!r}")
    row = {
        "agent": agent or ME_KEY,
        "status": status,
        "task": task,
        "files": files or None,
        "branch": branch,
        "detail": detail,
    }
    inserted = _client().table(TABLE).insert(row).execute().data
    line = format_line(status, task, files, branch, detail)
    mirrored = False
    if mirror:
        mirrored = telegram_post(line)
    return {"row": inserted[0] if inserted else None, "line": line, "mirrored": mirrored}


def telegram_post(text):
    """Mirror a status line into the OASIS group. Uses the dedicated coordination
    bot if set, else the existing DM bot (@Bravo_2003bot, also in the group).
    Sending needs no polling, so either token works with no new credential.

    CHANNEL ISOLATION: refuses to mirror internal operational noise. The row is
    still written to `agent_activity` by the caller — the DB is the agent↔agent
    channel and loses nothing — only the human-facing broadcast is withheld.
    Returns False, which `post()` already surfaces as `mirrored: False`.
    """
    # Wrong OWNER first — TPS / TextTorrent / phone-lookup belong to APEX/Adon,
    # and CC asked on 2026-08-03 that Bravo stop surfacing them anywhere. Same
    # ordering as notify.py: ownership outranks audience, because several of
    # these strings match BOTH lists and the audience rule alone would merely
    # move them rather than stop them.
    owner_hit = _NOT_BRAVO_DOMAIN_RE.search(text or "")
    if owner_hit:
        print(f"[agent_activity] NOT mirrored — not Bravo's domain (matched: "
              f"{owner_hit.group(0)!r}). TPS / TextTorrent work is owned by "
              f"APEX/Adon. Row recorded in {TABLE}; the agent↔agent channel is "
              f"unaffected.", file=sys.stderr)
        return False

    hit = _GROUP_BLOCKED_TERMS_RE.search(text or "")
    if hit:
        print(f"[agent_activity] Suppressed operational noise from shared OASIS "
              f"group chat (matched: {hit.group(0)!r}). Row recorded in "
              f"{TABLE}; not mirrored.", file=sys.stderr)
        return False
    token = _env_value("CC_AGENT_BOT_TOKEN") or _env_value("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("COORD_GROUP_CHAT_ID") or _env_value("COORD_GROUP_CHAT_ID") or DEFAULT_GROUP_ID
    if not token:
        print("WARN: no bot token (CC_AGENT_BOT_TOKEN / TELEGRAM_BOT_TOKEN) — table updated but NOT mirrored to Telegram.", file=sys.stderr)
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=15) as r:
            return json.loads(r.read().decode()).get("ok", False)
    except Exception as e:  # noqa: BLE001
        print(f"WARN: Telegram mirror failed: {str(e)[:160]}", file=sys.stderr)
        return False


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _print(obj, as_json):
    if as_json:
        print(json.dumps(obj, indent=2, default=str))
    elif isinstance(obj, list):
        if not obj:
            print("(none)")
        for r in obj:
            print(format_line(r.get("status", "?"), r.get("task", ""), r.get("files"),
                              r.get("branch"), r.get("detail"),
                              label=(r.get("agent") or "?").upper()))
    else:
        print(obj)


def main():
    p = argparse.ArgumentParser(description="Bravo's agent_activity coordination client.")
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("recent", help="recent rows, newest first")
    pr.add_argument("--hours", type=float, default=3)
    pr.add_argument("--limit", type=int, default=30)
    pr.add_argument("--exclude-agent")
    pr.add_argument("--json", action="store_true")

    pp = sub.add_parser("peers", help="open work by the other agent(s)")
    pp.add_argument("--hours", type=float, default=6)
    pp.add_argument("--json", action="store_true")

    pc = sub.add_parser("claims", help="files the other agent has claimed")
    pc.add_argument("--hours", type=float, default=6)
    pc.add_argument("--json", action="store_true")

    po = sub.add_parser("post", help="insert a status row (optionally mirror to group)")
    po.add_argument("--status", required=True, choices=VALID_STATUS)
    po.add_argument("--task", required=True)
    po.add_argument("--files", help="comma-separated file/area list")
    po.add_argument("--branch")
    po.add_argument("--detail")
    po.add_argument("--agent", help=f"override agent key (default {ME_KEY})")
    po.add_argument("--mirror", action="store_true", help="also post the line to the OASIS group")
    po.add_argument("--json", action="store_true")

    pl = sub.add_parser("line", help="format a status line without inserting")
    pl.add_argument("--status", required=True, choices=VALID_STATUS)
    pl.add_argument("--task", required=True)
    pl.add_argument("--files")
    pl.add_argument("--branch")
    pl.add_argument("--detail")

    a = p.parse_args()
    files = [f.strip() for f in a.files.split(",")] if getattr(a, "files", None) else None

    if a.cmd == "recent":
        _print(recent(a.hours, a.limit, a.exclude_agent), a.json)
    elif a.cmd == "peers":
        _print(peer_open(a.hours), a.json)
    elif a.cmd == "claims":
        # claims() returns a dict {file: [claimants]} — always structured.
        print(json.dumps(claims(a.hours), indent=2, default=str))
    elif a.cmd == "post":
        res = post(a.status, a.task, files, a.branch, a.detail, mirror=a.mirror, agent=a.agent)
        _print(res if a.json else res["line"], a.json)
    elif a.cmd == "line":
        print(format_line(a.status, a.task, files, a.branch, a.detail))


if __name__ == "__main__":
    main()
