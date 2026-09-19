#!/usr/bin/env python
"""Create or inspect a GitHub repository with the PAT from the agents env.

    python scripts/github_repo_tool.py create --name <repo> [--public] [--description "..."]
    python scripts/github_repo_tool.py get    --name <repo>

Complements git_push_tool.py (which pushes but assumes the remote exists). The
token is read through lib.secret_loader and sent only as an Authorization
header; the owner is whoever the token belongs to (queried, never assumed).
Never prints the token.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from lib.secret_loader import load_env  # noqa: E402

API = "https://api.github.com"


def _token() -> str:
    env = load_env()
    for k in ("GITHUB_PERSONAL_ACCESS_TOKEN", "GITHUB_TOKEN", "GH_TOKEN"):
        if env.get(k):
            return env[k]
    raise SystemExit("no GitHub token in the agents env (GITHUB_PERSONAL_ACCESS_TOKEN)")


def gh(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    req = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={
            "Authorization": f"Bearer {_token()}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "github-repo-tool/1.0",
            **({"Content-Type": "application/json"} if body is not None else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        try:
            payload = json.load(e)
        except Exception:
            payload = {"message": e.read().decode("utf-8", "replace")[:400]}
        return e.code, payload


def owner() -> str:
    status, me = gh("GET", "/user")
    if status != 200 or not me.get("login"):
        raise SystemExit(f"token cannot identify its owner (HTTP {status}): {me.get('message')}")
    return me["login"]


def cmd_get(args) -> int:
    login = owner()
    status, repo = gh("GET", f"/repos/{login}/{args.name}")
    if status == 200:
        print(json.dumps({"full_name": repo["full_name"], "private": repo["private"], "clone_url": repo["clone_url"], "default_branch": repo.get("default_branch")}, indent=2))
        return 0
    print(f"{login}/{args.name}: HTTP {status} {repo.get('message')}")
    return 1


def cmd_create(args) -> int:
    login = owner()
    status, existing = gh("GET", f"/repos/{login}/{args.name}")
    if status == 200:
        print(f"exists: {existing['full_name']} ({'private' if existing['private'] else 'public'}) {existing['clone_url']}")
        return 0
    status, repo = gh("POST", "/user/repos", {"name": args.name, "private": not args.public, "description": args.description or "", "auto_init": False})
    if status not in (200, 201):
        print(f"create failed: HTTP {status} {repo.get('message')} {repo.get('errors', '')}")
        return 1
    print(f"created: {repo['full_name']} ({'private' if repo['private'] else 'public'}) {repo['clone_url']}")
    return 0


def cmd_rename(args) -> int:
    """Rename a repo. GitHub redirects the old URL, but a stale `origin` still says the old name."""
    login = owner()
    status, repo = gh("PATCH", f"/repos/{login}/{args.name}", {"name": args.to})
    if status != 200:
        print(f"rename failed: HTTP {status} {repo.get('message')}")
        return 1
    print(f"renamed: {login}/{args.name} -> {repo['full_name']} ({repo['clone_url']})")
    print(f"update the local remote: git -C <repo> remote set-url origin {repo['clone_url']}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("create"); p.add_argument("--name", required=True); p.add_argument("--public", action="store_true"); p.add_argument("--description")
    p = sub.add_parser("get"); p.add_argument("--name", required=True)
    p = sub.add_parser("rename"); p.add_argument("--name", required=True); p.add_argument("--to", required=True)
    args = parser.parse_args(argv)
    return {"create": cmd_create, "get": cmd_get, "rename": cmd_rename}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
