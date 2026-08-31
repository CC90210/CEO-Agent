"""List recent Vercel deployments — a verification check, so it fails loud.

Two defects Codex caught on review, both of which made this report green when
it should have reported nothing at all:

  * it asked the secret loader for VERCEL_BEARER_TOKEN. The fleet's canonical
    name is VERCEL_TOKEN (see scripts/integrations/vercel_env_tool.py), so the
    lookup returned None and the request went out as "Bearer None" — a
    guaranteed 401 on a correctly configured machine.

  * the except printed the error and fell off the end, exiting 0. Anything
    treating this as a deployment gate would read an auth failure, a network
    drop, or an API change as "no problem here". A check that cannot run has
    not passed.
"""

import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.lib.secret_loader import get  # noqa: E402

API = "https://api.vercel.com/v6/deployments?limit=5"


def main() -> int:
    token = get("VERCEL_TOKEN")
    if not token:
        sys.stderr.write(
            "VERCEL_TOKEN is not available from the secret loader — cannot check "
            "deployments. This is a failure, not an empty result.\n")
        return 1

    req = urllib.request.Request(API, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:            # noqa: BLE001 — reported, never swallowed
        sys.stderr.write(f"Vercel API query FAILED: {e}\n")
        return 1

    deployments = data.get("deployments", [])
    print(f"Found {len(deployments)} recent Vercel deployments:")
    for d in deployments:
        commit = ((d.get("meta") or {}).get("githubCommitSha") or "n/a")[:7]
        print(f"Project: {d.get('name')} | State: {d.get('state')} | "
              f"SHA: {commit} | URL: https://{d.get('url')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
