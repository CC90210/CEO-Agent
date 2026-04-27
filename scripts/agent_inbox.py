#!/usr/bin/env python3
"""
agent_inbox — Async agent-to-agent messaging (mcp_agent_mail-inspired pattern).

Closes Bravo's coordination gap: sibling agents (Atlas, Maven, Aura, Codex)
can post structured messages that the orchestrator picks up at checkpoints
instead of blocking on synchronous polls.

Usage:
    # Post a message
    python scripts/agent_inbox.py post --from codex --to bravo \
        --subject "Task complete" --body "Refactor landed" --priority normal

    # List unread for a recipient
    python scripts/agent_inbox.py list --to bravo

    # Read + mark read (moves to read/)
    python scripts/agent_inbox.py read <message_id>

    # Reply in thread
    python scripts/agent_inbox.py reply --in-reply-to <msg_id> \
        --from bravo --body "Received, reviewing"

    # JSON output for agent consumption
    python scripts/agent_inbox.py list --to bravo --json

Storage: tmp/agent_inbox/ (gitignored). inbox/ unread, read/ acknowledged.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from datetime import datetime, timezone

REPO_ROOT = Path(__file__).resolve().parent.parent
INBOX_ROOT = REPO_ROOT / "tmp" / "agent_inbox"
INBOX_DIR = INBOX_ROOT / "inbox"
READ_DIR = INBOX_ROOT / "read"

VALID_PRIORITIES = {"low", "normal", "high", "urgent"}
KNOWN_AGENTS = {"bravo", "atlas", "maven", "aura", "codex", "cc", "broadcast"}

# Cross-repo routing — when this script posts `--to maven`, the message
# must land in MAVEN's inbox dir, not the sender's. Each agent reads
# only its own local inbox; the writer resolves the recipient's repo
# path and writes there. The path map lives in scripts/sibling_repos.py
# (single source of truth across Bravo). Per-machine overrides via env
# vars: BRAVO_REPO, MAVEN_REPO, ATLAS_REPO, AURA_REPO.
from sibling_repos import repo_for as _repo_for


def _inbox_path_for(recipient: str) -> Path:
    """Resolve the inbox directory for `recipient`.

    - Known sibling agents whose repo exists → their repo's
      tmp/agent_inbox/inbox (creates the dir tree if missing — first
      cross-post bootstraps the sibling's inbox).
    - Anything else (including 'cc', 'codex', 'broadcast', sub-agent
      names, OR a sibling whose repo isn't installed on this machine)
      → local inbox. 'broadcast' is read by every agent that lists
      messages addressed to itself OR to broadcast.
    """
    repo = _repo_for(recipient)
    if repo is not None:
        target = repo / "tmp" / "agent_inbox" / "inbox"
        target.mkdir(parents=True, exist_ok=True)
        return target
    return INBOX_DIR


def ensure_dirs() -> None:
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    READ_DIR.mkdir(parents=True, exist_ok=True)


def _validate_agent(name: str, role: str) -> None:
    # Known agents enforced; custom sub-agent names allowed with a warning tag.
    if name not in KNOWN_AGENTS:
        print(f"WARN: unknown {role} agent '{name}' — storing anyway", file=sys.stderr)


def cmd_post(args: argparse.Namespace) -> dict:
    ensure_dirs()
    _validate_agent(args.from_, "from")
    _validate_agent(args.to, "to")
    if args.priority not in VALID_PRIORITIES:
        raise SystemExit(f"ERROR: priority must be one of {sorted(VALID_PRIORITIES)}")

    msg_id = uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc).isoformat()
    body = args.body or sys.stdin.read()

    msg = {
        "message_id": msg_id,
        "from": args.from_,
        "to": args.to,
        "timestamp": now,
        "subject": args.subject,
        "body": body,
        "priority": args.priority,
        "requires_response": args.requires_response,
        "in_reply_to": args.in_reply_to,
        "thread_id": args.in_reply_to or msg_id,
    }

    # Filename sortable by time + priority (urgent sorts first via prefix)
    priority_prefix = {"urgent": "0", "high": "1", "normal": "2", "low": "3"}[args.priority]
    ts_slug = now.replace(":", "-").replace(".", "-")
    fname = f"{priority_prefix}_{ts_slug}_{args.to}_{msg_id}.json"
    # Cross-repo routing: write to recipient's inbox dir, not the sender's.
    target_dir = _inbox_path_for(args.to)
    (target_dir / fname).write_text(json.dumps(msg, indent=2), encoding="utf-8")
    msg["_delivered_to"] = str(target_dir)
    return msg


def _load_all(to: str | None = None) -> list[dict]:
    ensure_dirs()
    out: list[dict] = []
    for p in sorted(INBOX_DIR.glob("*.json")):
        try:
            m = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if to and m.get("to") not in (to, "broadcast"):
            continue
        m["_path"] = str(p)
        out.append(m)
    return out


def cmd_list(args: argparse.Namespace) -> list[dict]:
    msgs = _load_all(args.to)
    return msgs


def cmd_read(args: argparse.Namespace) -> dict | None:
    msgs = _load_all()
    target = next((m for m in msgs if m["message_id"] == args.message_id), None)
    if not target:
        raise SystemExit(f"ERROR: message {args.message_id} not found in inbox/")
    # Move to read/
    src = Path(target["_path"])
    dst = READ_DIR / src.name
    src.rename(dst)
    target["_path"] = str(dst)
    return target


def cmd_reply(args: argparse.Namespace) -> dict:
    msgs = _load_all() + [
        json.loads(p.read_text(encoding="utf-8"))
        for p in READ_DIR.glob("*.json")
    ]
    parent = next((m for m in msgs if m.get("message_id") == args.in_reply_to), None)
    if not parent:
        raise SystemExit(f"ERROR: parent message {args.in_reply_to} not found")
    # Route reply back to parent.from
    synthesized = argparse.Namespace(
        from_=args.from_,
        to=parent["from"],
        subject=f"Re: {parent.get('subject', '')}",
        body=args.body,
        priority=args.priority,
        requires_response=False,
        in_reply_to=args.in_reply_to,
    )
    return cmd_post(synthesized)


def _human_list(msgs: list[dict]) -> str:
    if not msgs:
        return "(no unread messages)"
    lines = [f"  {len(msgs)} unread:"]
    for m in msgs:
        prio = m.get("priority", "normal").upper()
        lines.append(f"  [{prio:7}] {m['message_id']} {m['from']:>8} -> {m['to']:<8} | {m.get('subject','')[:50]}")
    return "\n".join(lines)


def _human_msg(m: dict) -> str:
    lines = [
        "=" * 60,
        f"  {m['message_id']}  [{m['priority'].upper()}]",
        f"  From: {m['from']} -> {m['to']}",
        f"  At:   {m['timestamp']}",
        f"  Subject: {m.get('subject','')}",
        f"  Thread: {m.get('thread_id','')}",
        "-" * 60,
        m.get("body", ""),
        "=" * 60,
    ]
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description="Agent-to-agent async inbox")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    sub = p.add_subparsers(dest="cmd", required=True)

    post = sub.add_parser("post", help="post a new message")
    post.add_argument("--from", dest="from_", required=True)
    post.add_argument("--to", required=True)
    post.add_argument("--subject", required=True)
    post.add_argument("--body", default=None, help="message body (or pipe via stdin)")
    post.add_argument("--priority", default="normal")
    post.add_argument("--requires-response", action="store_true")
    post.add_argument("--in-reply-to", default=None)

    lst = sub.add_parser("list", help="list unread messages")
    lst.add_argument("--to", default=None, help="filter by recipient")

    rd = sub.add_parser("read", help="read + ack a message (moves to read/)")
    rd.add_argument("message_id")

    rep = sub.add_parser("reply", help="reply to a message in-thread")
    rep.add_argument("--from", dest="from_", required=True)
    rep.add_argument("--in-reply-to", required=True)
    rep.add_argument("--body", required=True)
    rep.add_argument("--priority", default="normal")

    args = p.parse_args()

    try:
        if args.cmd == "post":
            result = cmd_post(args)
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                print(f"Posted {result['message_id']} ({args.from_} -> {args.to})")
        elif args.cmd == "list":
            msgs = cmd_list(args)
            if args.json:
                print(json.dumps(msgs, indent=2, default=str))
            else:
                print(_human_list(msgs))
        elif args.cmd == "read":
            m = cmd_read(args)
            if args.json:
                print(json.dumps(m, indent=2, default=str))
            else:
                print(_human_msg(m))
        elif args.cmd == "reply":
            result = cmd_reply(args)
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                print(f"Replied {result['message_id']} ({args.from_} -> {result['to']})")
    except SystemExit:
        raise
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
