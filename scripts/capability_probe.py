#!/usr/bin/env python3
"""Credential-first capability probe — answer "do I actually have access to X?"

WHY THIS EXISTS
---------------
The most expensive agent failure in this system is not a wrong edit — it is a
confident *false negative*: "I don't have access to Stripe, so you'll need to do
this manually." The key was in `.env.agents` the whole time. CC then does by hand
something the agent was fully authorized to do.

Agents cannot resolve this themselves by reading `.env.agents`: RULE 3 and
`scripts/state/secret_guard.py` block LLM reads of `.env*` by design. So the
answer has to come from a wrapper that reports **presence, never values**.

That is this tool. It reports which credentials exist and which CLI to invoke,
and it never emits a secret — values are reduced to a boolean before they can
reach a model's context. If a key is present, the agent is authorized: stop
hedging and run the tool.

CONTRACT
--------
  * Output contains key NAMES and booleans only. No values, no prefixes, no
    lengths, no hashes. A leak here would defeat the secret guard.
  * Exit 0 = capability available. Exit 1 = genuinely unavailable (the only
    case in which "I don't have access" is a true statement).

USAGE
  python scripts/capability_probe.py list                    # every service + status
  python scripts/capability_probe.py check stripe            # one service
  python scripts/capability_probe.py check stripe --json
  python scripts/capability_probe.py have STRIPE_API_KEY     # one raw key
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = REPO_ROOT / "docs" / "ENV_KEYS_TEMPLATE.md"

sys.path.insert(0, str(REPO_ROOT / "scripts"))

# Service -> (required key groups, how to actually invoke it).
#
# `requires` is a list of ANY-OF groups, and EVERY group must be satisfied. That
# distinction matters: reporting a service available because *some* matching key
# exists is a false positive, and a false positive is as harmful as the false
# negative this tool was built to kill — the agent proceeds, the wrapper fails to
# authenticate, and the error is far from the cause. A lone `SUPABASE_URL` with no
# service-role key is NOT access. An entry ending in `_` matches any key with that
# prefix, which keeps a renamed-but-present credential from reading as missing.
#
# The invoke string is half the value: knowing a key exists is useless if the agent
# still doesn't know which wrapper to call.
SERVICES: dict[str, tuple[list[list[str]], str]] = {
    "anthropic": ([["CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY"]],
                  "python scripts/lib/claude_cli.py  (subscription CLI — never the API key)"),
    "openai": ([["OPENAI_API_KEY"]],
               "node ~/.claude/codex-plugin/scripts/codex-companion.mjs task --write '<ctx>'"),
    "openrouter": ([["OPENROUTER_API_KEY"]], "python scripts/model_router.py"),
    "supabase": ([["SUPABASE_URL", "SUPABASE_URL_BRAVO", "BRAVO_SUPABASE_URL"],
                  ["SUPABASE_SERVICE_ROLE_KEY", "BRAVO_SUPABASE_SERVICE_ROLE_KEY",
                   "SUPABASE_SERVICE_ROLE_KEY_BRAVO"]],
                 "python scripts/integrations/supabase_tool.py <verb> --json"),
    # An account id is not a credential — require an actual secret key.
    "stripe": ([["STRIPE_ORG_KEY", "STRIPE_SECRET_KEY", "STRIPE_API_KEY"]],
               "python scripts/integrations/stripe_tool.py <verb> --json"),
    "google": ([["GMAIL_USER", "GMAIL_ADDRESS"], ["GMAIL_APP_PASSWORD"]],
               "python scripts/integrations/google_tool.py <verb> --json"),
    "n8n": ([["N8N_API_KEY"], ["N8N_API_URL", "N8N_BASE_URL", "N8N_URL"]],
            "python scripts/integrations/n8n_tool.py <verb> --json"),
    "vercel": ([["VERCEL_TOKEN"]],
               "python scripts/integrations/vercel_env_tool.py <verb> --json"),
    "cloudflare": ([["CLOUDFLARE_API_TOKEN", "CLOUDFLARE_TOKEN"]],
                   "python scripts/integrations/cloudflare_admin.py <verb>"),
    # notify.py gates on TELEGRAM_BOT_TOKEN + TELEGRAM_ALLOWED_USERS. It does NOT
    # read TELEGRAM_CHAT_ID — requiring that key here produced a false negative on
    # a service that works, which is the failure this whole tool exists to prevent.
    # Derive required sets from what the wrapper reads, never from the docs table.
    "telegram": ([["TELEGRAM_BOT_TOKEN", "CC_AGENT_BOT_TOKEN"], ["TELEGRAM_ALLOWED_USERS"]],
                 "python scripts/notify.py '<message>'"),
    "firecrawl": ([["FIRECRAWL_API_KEY"]],
                  "python scripts/research_fetch.py <url>   (auto-escalates)"),
    # late_tool.py lives in Maven's repo, not here. Naming the local path would
    # authorize the service and then hand the agent a No-such-file — the exact
    # false positive this tool exists to prevent.
    "late": ([["LATE_API_KEY", "ZERNIO_"]],
             "python ../CMO-Agent/scripts/late_tool.py   (Maven's repo — route content to Maven)"),
    "lendsaas": ([["LENDSAAS_API_TOKEN", "LENDSAAS_"]],
                 "python scripts/integrations/lendsaas_tool.py"),
    "github": ([["GITHUB_TOKEN", "GITHUB_PERSONAL_ACCESS_TOKEN", "GH_TOKEN"]],
               "gh <cmd>   (or plain git)"),
}

KEY_RE = re.compile(r"`([A-Z][A-Z0-9_]{2,})`")


def template_keys() -> list[str]:
    """Every env key name documented in ENV_KEYS_TEMPLATE.md (names only)."""
    if not TEMPLATE.is_file():
        return []
    text = TEMPLATE.read_text(encoding="utf-8", errors="replace")
    seen: list[str] = []
    for m in KEY_RE.finditer(text):
        k = m.group(1)
        if k not in seen:
            seen.append(k)
    return seen


def present_keys() -> set[str]:
    """Names of env keys that hold a non-empty value. Values never leave here."""
    try:
        from lib.secret_loader import load_env  # noqa: PLC0415

        env = load_env()
    except Exception:  # noqa: BLE001 — refused, missing file, anything
        import os

        env = os.environ
    # The comprehension below is the security boundary: only the NAME survives.
    return {k for k, v in env.items() if isinstance(v, str) and v.strip()}


def _satisfy(group: list[str], have: set[str]) -> list[str]:
    """Keys in `have` that satisfy this any-of group (empty = unsatisfied)."""
    return sorted(
        k for k in have
        if any(k == p or (p.endswith("_") and k.startswith(p)) for p in group)
    )


def probe(service: str, have: set[str]) -> dict:
    groups, invoke = SERVICES[service]
    matched: list[str] = []
    unsatisfied: list[str] = []
    for group in groups:
        hits = _satisfy(group, have)
        if hits:
            matched.extend(hits)
        else:
            # Name the canonical key so the operator knows what to add.
            unsatisfied.append(group[0])
    return {
        "service": service,
        # EVERY required group must be satisfied — see the SERVICES comment.
        "available": not unsatisfied,
        "keys_present": sorted(set(matched)),
        "keys_missing": unsatisfied,
        "invoke": invoke,
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    # --json lives on a shared parent so it is accepted AFTER the subcommand,
    # which is the form every doc and example uses. Registered only on the
    # top-level parser, argparse rejects `check stripe --json` outright.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true")
    ap.add_argument("--json", action="store_true", help=argparse.SUPPRESS)

    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", parents=[common], help="status of every known service")
    c = sub.add_parser("check", parents=[common], help="status of one service")
    c.add_argument("service")
    h = sub.add_parser("have", parents=[common], help="is one specific env key set?")
    h.add_argument("key")
    args = ap.parse_args()

    have = present_keys()

    if args.cmd == "have":
        ok = args.key in have
        if args.json:
            print(json.dumps({"key": args.key, "present": ok}))
        else:
            print(f"{args.key}: {'PRESENT — you are authorized' if ok else 'not set'}")
        return 0 if ok else 1

    if args.cmd == "check":
        svc = args.service.lower()
        if svc not in SERVICES:
            print(f"unknown service '{svc}'. known: {', '.join(sorted(SERVICES))}",
                  file=sys.stderr)
            return 2
        r = probe(svc, have)
        if args.json:
            print(json.dumps(r, indent=2))
        else:
            print(f"{svc}: {'AVAILABLE' if r['available'] else 'NOT CONFIGURED'}")
            if r["keys_present"]:
                print(f"  keys present : {', '.join(r['keys_present'])}")
            if r["keys_missing"]:
                print(f"  keys missing : {', '.join(r['keys_missing'])}")
            print(f"  invoke       : {r['invoke']}")
        return 0 if r["available"] else 1

    results = [probe(s, have) for s in sorted(SERVICES)]
    if args.json:
        print(json.dumps({
            "available": [r["service"] for r in results if r["available"]],
            "unavailable": [r["service"] for r in results if not r["available"]],
            "services": results,
            "documented_keys": len(template_keys()),
            "keys_set": len(have),
        }, indent=2))
        return 0

    ready = [r for r in results if r["available"]]
    print(f"CAPABILITY PROBE — {len(ready)}/{len(results)} services authorized "
          f"({len(have)} env keys set, {len(template_keys())} documented)\n")
    for r in results:
        mark = "OK " if r["available"] else "-- "
        print(f"  {mark} {r['service']:<12} {r['invoke']}")
    print("\nA service marked OK is one you are authorized to use RIGHT NOW.")
    print("Saying \"I don't have access\" to any of them is a false statement.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
