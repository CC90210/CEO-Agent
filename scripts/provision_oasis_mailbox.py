"""Provision the shared OASIS sending mailbox, without the secret passing
through a shell, a log, or an agent's context.

WHAT THIS IS FOR. CC, 2026-09-08: "use my app password, then just CC/forward the
reps with their emails, and make this as easy as possible." One shared mailbox
sends every OASIS rep email and each rep is CC'd on their own, so no rep has to
connect anything and a new rep works on day one.

WHY A LAUNCHER AND NOT JUST THE NODE SCRIPT. Two secrets have to meet in one
process and neither may be seen by the operator running it or by an agent:

  GMAIL_USER / GMAIL_APP_PASSWORD   live in .env.agents, readable only through
                                    the sanctioned loader (RULE 3 / secret_guard)
  BRAVO_FIELD_ENCRYPTION_KEY        lives in Vercel, and it MUST be the
                                    production value: the row is encrypted at
                                    rest, so a row written under a different key
                                    is stored successfully and is then
                                    undecryptable in production. That failure is
                                    silent - sends simply keep falling back to
                                    the bridge and nobody learns why.

So this loads the first pair through secret_loader, takes the second from an env
file pulled from Vercel, hands both to the Node writer through its ENVIRONMENT,
and prints neither. Nothing is interpolated into a command line, where it would
land in shell history and process listings.

USAGE:
  # once, to get the production encryption key into a local file:
  #   cd <command-center> && npx vercel env pull .env.provision.local
  python scripts/provision_oasis_mailbox.py --env-file <path> [--verify]

  --verify sends a test email to the mailbox itself (never to a prospect) and
  proves the credential actually authenticates. A stored credential is not a
  working one, and the first person to discover that should not be a rep on a
  live call.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from lib.secret_loader import load_env  # noqa: E402

COMMAND_CENTER = Path(r"C:\Users\User\APPS\oasis-command-center")
OASIS_TENANT_ID = "ef8d389e-3f15-43f2-ae00-3660f69a1452"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--env-file", required=True,
                    help="Env file pulled from Vercel production (holds BRAVO_FIELD_ENCRYPTION_KEY)")
    ap.add_argument("--verify", action="store_true",
                    help="Send a test email to the mailbox itself to prove it authenticates")
    ap.add_argument("--tenant", default=OASIS_TENANT_ID)
    args = ap.parse_args()

    env_file = Path(args.env_file)
    if not env_file.is_absolute():
        env_file = (COMMAND_CENTER / env_file).resolve()
    if not env_file.exists():
        print(f"[provision] env file not found: {env_file}\n"
              f"  Create it with:  cd {COMMAND_CENTER} && npx vercel env pull {env_file.name}",
              file=sys.stderr)
        return 1

    # The mailbox credential. load_env returns the dict; nothing is printed.
    secrets = load_env(required=["GMAIL_USER", "GMAIL_APP_PASSWORD"])
    mail_from = (secrets.get("GMAIL_USER") or "").strip()
    app_password = (secrets.get("GMAIL_APP_PASSWORD") or "").strip()
    if not mail_from or not app_password:
        print("[provision] GMAIL_USER / GMAIL_APP_PASSWORD missing from the credential store.",
              file=sys.stderr)
        return 1

    child_env = dict(os.environ)
    child_env["OASIS_MAIL_FROM"] = mail_from
    child_env["OASIS_MAIL_APP_PASSWORD"] = app_password
    child_env["OASIS_TENANT_ID"] = args.tenant

    # --env-file is Node's own loader: the production key is read INSIDE the
    # node process. It never crosses a shell, so it cannot reach shell history,
    # a process listing, or this program's stdout.
    cmd = [
        "node",
        f"--env-file={env_file}",
        "--import", "tsx",
        "scripts/provision-oasis-mailbox.mjs",
    ]
    if args.verify:
        cmd.append("--verify")

    print(f"[provision] writing the shared OASIS mailbox for tenant {args.tenant}")
    print(f"[provision] from address resolves to {mail_from}")
    print("[provision] the app password is passed to the writer through its environment "
          "and is never printed.")
    proc = subprocess.run(cmd, cwd=str(COMMAND_CENTER), env=child_env)
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
