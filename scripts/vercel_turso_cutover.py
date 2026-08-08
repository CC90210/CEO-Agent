#!/usr/bin/env python3
"""Put the Turso / R2 cutover variables on the Vercel projects.

The cutover is env-driven by design — the same build runs on Supabase or Turso
depending on three flags — which means the flags ARE the migration. Setting them
by hand across five projects and three environments is ~75 dashboard fields and
one typo away from a half-cut app reading one backend and writing another.

    python scripts/vercel_turso_cutover.py --status
    python scripts/vercel_turso_cutover.py --apply                # all projects
    python scripts/vercel_turso_cutover.py --apply --project nostalgic-requests

SECRETS: values are read through lib.secret_loader and pushed straight to the
Vercel API. Nothing is printed but key NAMES and whether they are set.

NOT DONE HERE: removing the Supabase variables. They stay until the
subscription is actually cancelled, so that flipping EMPIRE_DATA_BACKEND back
is a one-field rollback rather than a restore.
"""
from __future__ import annotations

import argparse
import base64
import time
import secrets as _secrets
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from lib.tls_trust import ensure_os_trust  # noqa: E402

ensure_os_trust()

import requests  # noqa: E402

from lib.db_turso import resolve_project_target  # noqa: E402
from lib.secret_loader import load_env  # noqa: E402

VERCEL_API = "https://api.vercel.com"
ALL_ENVS = ["production", "preview", "development"]

# Default to production only. The live apps already follow that convention, and
# widening EMPIRE_DATA_BACKEND to preview would point every preview deployment
# at the PRODUCTION Turso database — a branch build writing real client rows.
# R2 is the exception: it is the same bucket either way, so preview serving the
# same objects is correct rather than dangerous.
DEFAULT_TARGETS = ["production"]
ALWAYS_ALL_ENVS = {"CLOUDFLARE_ACCOUNT_ID", "R2_ACCESS_KEY_ID",
                   "R2_SECRET_ACCESS_KEY", "R2_BUCKET", "R2_PUBLIC_BASE_URL"}

# Vercel project slug -> the Turso project key its data lives under.
# `oasis-ai-platform` is deliberately absent: it is a Vite SPA with no server
# tier, so it cannot hold a Turso token and needs a different answer.
PROJECTS: dict[str, dict] = {
    "agent-dashboard": {"turso": "bravo", "auth": True, "storage": True},
    "breeze-portal": {"turso": "breeze", "auth": True, "storage": True},
    "nostalgic-requests": {"turso": "nostalgic", "auth": True, "storage": True},
    "real-estate-app": {"turso": "propflow", "auth": True, "storage": True},
}

R2_KEYS = ("CLOUDFLARE_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY",
           "R2_BUCKET", "R2_PUBLIC_BASE_URL")


def _headers(token: str) -> dict:
    return {"authorization": f"Bearer {token}", "content-type": "application/json"}


def _api(method: str, path: str, token: str, team: str | None, **kw):
    params = kw.pop("params", {}) or {}
    if team:
        params["teamId"] = team
    return requests.request(method, f"{VERCEL_API}{path}", headers=_headers(token),
                            params=params, timeout=45, **kw)


def list_env(project: str, token: str, team: str | None) -> dict[str, set]:
    r = _api("GET", f"/v9/projects/{project}/env", token, team)
    if r.status_code != 200:
        raise RuntimeError(f"{project}: list env HTTP {r.status_code} {r.text[:160]}")
    out: dict[str, set] = {}
    for e in r.json().get("envs", []):
        out.setdefault(e["key"], set()).update(e.get("target") or [])
    return out


def upsert(project: str, key: str, value: str, token: str, team: str | None,
           existing: dict[str, set], targets: list[str]) -> str:
    """Create or replace one variable on the given environments."""
    if key in existing:
        # Vercel rejects a create that collides, and a PATCH needs the id, so
        # delete-then-create keeps this idempotent and re-runnable. Only the
        # entries covering our targets are removed — a production-scoped value
        # must not be destroyed while setting preview.
        r = _api("GET", f"/v9/projects/{project}/env", token, team)
        for e in r.json().get("envs", []):
            if e["key"] == key and set(e.get("target") or []) & set(targets):
                _api("DELETE", f"/v9/projects/{project}/env/{e['id']}", token, team)
    r = _api("POST", f"/v10/projects/{project}/env", token, team,
             json={"key": key, "value": value, "type": "encrypted", "target": targets})
    if r.status_code in (200, 201):
        return "set"
    return f"FAILED {r.status_code} {r.text[:120]}"


def redeploy_production(slug: str, token: str, team: str | None,
                        wait_s: int = 900) -> tuple[bool, str]:
    """Rebuild production from its latest READY deployment, and WAIT.

    Returning as soon as the build is queued would report success for something
    that can still fail, so this blocks until Vercel settles. A cutover that
    reports OK while the build errors is worse than one that reports slowly.
    """
    r = _api("GET", "/v6/deployments", token, team,
             params={"app": slug, "limit": 1, "target": "production",
                     "state": "READY"})
    deps = r.json().get("deployments", []) if r.status_code == 200 else []
    if not deps:
        return False, f"no READY production deployment to rebuild from ({slug})"

    r = _api("POST", "/v13/deployments", token, team, params={"forceNew": "1"},
             json={"name": slug, "deploymentId": deps[0]["uid"],
                   "target": "production",
                   "meta": {"redeployReason": "turso cutover env"}})
    if r.status_code not in (200, 201):
        return False, f"redeploy rejected HTTP {r.status_code} {r.text[:120]}"

    dep_id = r.json().get("id")
    deadline = time.time() + wait_s
    state = "UNKNOWN"
    while time.time() < deadline:
        time.sleep(15)
        s = _api("GET", f"/v13/deployments/{dep_id}", token, team)
        body = s.json() if s.status_code == 200 else {}
        state = body.get("readyState") or body.get("status") or "UNKNOWN"
        if state in ("READY", "ERROR", "CANCELED"):
            break
    return state == "READY", f"{slug} -> {state}"


def desired_for(slug: str, cfg: dict, env: dict) -> dict[str, str]:
    """Everything this project needs, resolved. Values never printed."""
    want: dict[str, str] = {"EMPIRE_DATA_BACKEND": "turso_cloud"}

    url, tok, _ = resolve_project_target(cfg["turso"])
    want["TURSO_DATABASE_URL"] = url
    want["TURSO_AUTH_TOKEN"] = tok

    if cfg.get("auth"):
        want["EMPIRE_AUTH_BACKEND"] = "turso"
        # Per-project, not shared: one leaked secret must not mint valid
        # sessions for a different product.
        want["AUTH_SESSION_SECRET"] = base64.urlsafe_b64encode(
            _secrets.token_bytes(48)).decode().rstrip("=")

    if cfg.get("storage"):
        # Reuse the resolution the storage ETL already does, so the bucket and
        # public URL cannot drift between what was uploaded and what is served.
        from etl_storage_to_r2 import resolve_r2  # noqa: PLC0415
        creds, missing, _notes = resolve_r2(env)
        if missing:
            raise RuntimeError(f"R2 not resolvable: missing {', '.join(missing)}")
        for k in R2_KEYS:
            want[k] = creds[k]
    return want


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", choices=sorted(PROJECTS))
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--rotate-session-secret", action="store_true",
                    help="replace AUTH_SESSION_SECRET even if one is already set "
                         "(this signs every user out)")
    ap.add_argument("--redeploy", action="store_true",
                    help="rebuild production after writing env vars, and wait for "
                         "it. Without this the variables are set but the RUNNING "
                         "build has never seen them — Vercel bakes env at build "
                         "time, so a cutover looks applied and is not.")
    ap.add_argument("--targets", default=",".join(DEFAULT_TARGETS),
                    help="comma-separated environments for the cutover flags "
                         "(default: production). R2 keys always cover all three.")
    args = ap.parse_args()
    base_targets = [t.strip() for t in args.targets.split(",") if t.strip()]
    bad = [t for t in base_targets if t not in ALL_ENVS]
    if bad:
        print(f"ERROR: unknown environment(s): {', '.join(bad)}", file=sys.stderr)
        return 2

    env = load_env()
    token = env.get("VERCEL_TOKEN")
    team = env.get("VERCEL_TEAM_ID") or None
    if not token:
        print("ERROR: VERCEL_TOKEN absent from the agents env", file=sys.stderr)
        return 2

    targets = [args.project] if args.project else list(PROJECTS)
    failures = 0

    for slug in targets:
        cfg = PROJECTS[slug]
        try:
            existing = list_env(slug, token, team)
        except Exception as exc:
            print(f"\n=== {slug}: {exc}")
            failures += 1
            continue

        try:
            want = desired_for(slug, cfg, env)
        except Exception as exc:
            print(f"\n=== {slug}: cannot resolve config — {exc}")
            failures += 1
            continue

        def targets_for(key: str) -> list[str]:
            return ALL_ENVS if key in ALWAYS_ALL_ENVS else base_targets

        unmet = [k for k in want
                 if not set(targets_for(k)).issubset(existing.get(k, set()))]

        wrote_any = False
        print(f"\n=== {slug} ({cfg['turso']})  targets={','.join(base_targets)}")
        print(f"    already covered : {len(want) - len(unmet)}/{len(want)}")
        if unmet:
            print(f"    NOT COVERED     : {', '.join(sorted(unmet))}")

        if not args.apply:
            continue

        for key, value in want.items():
            tg = targets_for(key)
            # An existing session secret is left alone: replacing it invalidates
            # every live cookie and signs the whole userbase out mid-migration.
            #
            # But "already set" has to mean set ON THE TARGETS WE ARE WRITING.
            # This used to check `key in existing`, i.e. set ANYWHERE — so a
            # secret that existed only on PREVIEW blocked the production write,
            # silently. PropFlow ended up with EMPIRE_AUTH_BACKEND=turso and no
            # AUTH_SESSION_SECRET in production, which is the worst of the three
            # states: the data plane is on Turso, auth falls back to Supabase,
            # and the browser bridge 404s because it requires both. It looks
            # healthy until someone logs in.
            if (key == "AUTH_SESSION_SECRET"
                    and set(tg).issubset(existing.get(key, set()))
                    and not args.rotate_session_secret):
                print(f"    keep      {key} (already covers {','.join(tg)}; "
                      f"--rotate-session-secret to replace)")
                continue
            if set(tg).issubset(existing.get(key, set())):
                print(f"    ok        {key}")
                continue
            result = upsert(slug, key, value, token, team, existing, tg)
            if result != "set":
                failures += 1
            wrote_any = wrote_any or result == "set"
            print(f"    {result:<9} {key} -> {','.join(tg)}")

        # Vercel bakes env vars at BUILD time, so everything above is inert
        # until a fresh deployment. This tool used to end by printing "redeploy
        # each project" and leaving it — which is how a cutover ends up half
        # applied: the flags read as set, the running build has never seen them,
        # and the status check above says covered.
        if wrote_any and args.redeploy:
            ok, detail = redeploy_production(slug, token, team)
            failures += not ok
            print(f"    {'redeploy ':<9} {detail}")
        elif wrote_any:
            print(f"    NOTE: {slug} still runs the OLD env until it is "
                  f"redeployed — pass --redeploy, or deploy it yourself.")

    print("\n" + "=" * 58)
    if args.apply and not args.redeploy:
        print("Anything written above is INERT until that project is rebuilt — "
              "Vercel bakes env at build time. Re-run with --redeploy, or deploy "
              "each changed project yourself.")
    print(f"{'FAILURES: ' + str(failures) if failures else 'OK'}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
