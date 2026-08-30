"""vercel_env_pull_sync.py — recover Vercel PRODUCTION values via the Vercel CLI.

⚠ READ THIS BEFORE RE-RUNNING IT FOR SENSITIVE VARS: **it cannot recover them,
and neither can anything else.** This tool was built on the theory that the CLI
might return what the REST API withholds. It does not. Measured 2026-08-30:

  * control run, `listing-studio`  -> 17 of 18 values returned; the ONE
    `sensitive`-type var came back EMPTY. So the mechanism itself works.
  * `agent-dashboard`              -> all 26 sensitive vars EMPTY.
  * Vercel docs: sensitive values are "non-readable once created"; the edit
    dialog shows "The current value is hidden". The DASHBOARD cannot reveal
    them either, so there is no human fallback to fall back to.

Recovering a sensitive var is therefore not an extraction problem — it is
recovery-from-the-issuer or rotation-on-both-sides, per key. That work is
scoped in brain/OASIS_CC_SECRET_FILL_GUIDE.md. Do not re-run this hoping for a
different answer.

WHAT IT IS STILL GOOD FOR: pulling `encrypted`/`plain` production values from a
LINKED repo. It overlaps `vercel_secret_sync.py` (the API path, which needs no
link and namespaces everything); prefer that one for bulk recovery and use this
when a repo is already linked or you want to compare the two sources.

SAFETY CONTRACT (this file is the reason the operation is allowed at all):
  * VERCEL_TOKEN is injected into the child's ENV, never onto argv.
  * The pull target is a file in the SCRATCHPAD — never inside an app repo, so
    a stray `git add -A` can never commit production secrets — and it is
    deleted in a finally block, best-effort overwritten first.
  * Nothing prints a value. Output is key NAMES plus a shape class
    (url / jwt-like / short / long) so the operator can sanity-check without
    the agent ever seeing a secret.
  * Only keys that already exist as `# FILL <NS>__<KEY>=` placeholders are
    filled. It will not invent keys or overwrite an existing value.

    python scripts/integrations/vercel_env_pull_sync.py plan  --app oasis-command-center
    python scripts/integrations/vercel_env_pull_sync.py apply --app oasis-command-center
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

CAPABILITY_META = {
    "category": "release.cloudflare",
    "lifecycle": "active",
    "risk": "credential_store_write",
    "triggers": [
        "pull vercel production secrets via cli",
        "fill the remaining FILL placeholders",
    ],
    "owner": "bravo",
    "project": "empire",
    "bridge": {"visible": False},
}

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from lib.secret_loader import load_env  # noqa: E402
from lib.subprocess_helpers import safe_run  # noqa: E402

ENV_FILE = REPO_ROOT / ".env.agents"
REGISTRY = REPO_ROOT / "config" / "cloudflare" / "apps.json"
SCRATCH = Path(os.environ.get("TEMP", tempfile.gettempdir())) / "bravo-vercel-pull"

PLATFORM_PREFIXES = ("VERCEL_", "TURBO_", "NX_")


def _shape(v: str) -> str:
    if not v:
        return "EMPTY"
    if v.startswith(("http://", "https://", "libsql://", "postgres://")):
        return f"url({len(v)})"
    if v.count(".") >= 2 and len(v) > 100:
        return f"jwt-like({len(v)})"
    return f"{'short' if len(v) <= 12 else 'long'}({len(v)})"


def _ns(slug: str, key: str) -> str:
    return slug.upper().replace("-", "_") + "__" + key


def _parse(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        if k and not k.startswith(PLATFORM_PREFIXES) and k != "VERCEL":
            out[k] = v
    return out


def _shred(path: Path) -> None:
    """Overwrite then unlink. Best-effort — the point is not forensic erasure,
    it is that the plaintext does not sit around after the run."""
    try:
        if path.exists():
            path.write_bytes(b"0" * max(1, path.stat().st_size))
            path.unlink()
    except OSError:
        pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("verb", choices=["plan", "apply"])
    ap.add_argument("--app", required=True)
    args = ap.parse_args()

    apps = json.loads(REGISTRY.read_text(encoding="utf-8"))["apps"]
    if args.app not in apps:
        print(f"ERROR: unknown app {args.app}", file=sys.stderr)
        return 2
    app_dir = Path(apps[args.app]["dir"])
    # Either link shape works: project.json (single project) or repo.json
    # (repo-level link, which `vercel link` writes when the dir is a git root).
    vdir = app_dir / ".vercel"
    if not ((vdir / "project.json").exists() or (vdir / "repo.json").exists()):
        print(f"ERROR: {app_dir} is not linked to Vercel — run:\n"
              f"  npx vercel link --yes --project {apps[args.app]['vercel_project']}")
        return 2

    loaded = load_env()
    token = (loaded.get("VERCEL_TOKEN") or "").strip()
    if not token:
        print("ERROR: VERCEL_TOKEN missing from the agents env store")
        return 2

    SCRATCH.mkdir(parents=True, exist_ok=True)
    target = SCRATCH / f"{args.app}.pull"
    env = dict(os.environ)
    env["VERCEL_TOKEN"] = token
    if (loaded.get("VERCEL_TEAM_ID") or "").strip():
        env["VERCEL_ORG_ID"] = loaded["VERCEL_TEAM_ID"].strip()

    try:
        npx = shutil.which("npx") or "npx"
        proc = safe_run([npx, "vercel", "env", "pull", str(target),
                         "--environment=production", "--yes"],
                        cwd=str(app_dir), env=env, capture_output=True, text=True,
                        encoding="utf-8", errors="replace", timeout=300)
        if proc.returncode != 0 or not target.exists():
            tail = (proc.stderr or proc.stdout or "")[-500:]
            print(f"vercel env pull FAILED (rc={proc.returncode}):\n{tail}")
            return 1

        pulled = _parse(target)
        text = ENV_FILE.read_text(encoding="utf-8")
        fills = [k for k in pulled if f"# FILL {_ns(args.app, k)}=" in text]
        empty = [k for k in pulled if not pulled[k]]

        print(f"pulled {len(pulled)} production vars from {apps[args.app]['vercel_project']}")
        print(f"of those, {len(fills)} match an outstanding FILL placeholder:\n")
        for k in sorted(fills):
            print(f"  {k:44} {_shape(pulled[k])}")
        if empty:
            print(f"\n{len(empty)} came back EMPTY (still withheld by Vercel): {', '.join(sorted(empty)[:8])}")

        if args.verb != "apply":
            print("\nplan only — re-run with `apply` to write these into the store.")
            return 0

        stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        shutil.copy2(ENV_FILE, ENV_FILE.with_name(f".env.agents.bak.{stamp}"))
        written = 0
        for k in fills:
            v = pulled[k]
            if not v or "\n" in v or "\r" in v:
                continue
            text = text.replace(f"# FILL {_ns(args.app, k)}=", f"{_ns(args.app, k)}={v}", 1)
            written += 1
        ENV_FILE.write_text(text, encoding="utf-8", newline="\n")
        print(f"\nwrote {written} value(s) into the agents env store (backup taken).")
        return 0
    finally:
        _shred(target)


if __name__ == "__main__":
    sys.exit(main())
