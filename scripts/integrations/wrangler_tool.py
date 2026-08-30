"""wrangler_tool.py — Cloudflare Workers deploy/secrets pipeline for the fleet migration.

House pattern (run_dashboard_script.py): credentials load via the sanctioned
secret_loader and are injected into the CHILD process environment only — never
printed, never written to disk, never placed on argv. The LLM operating this
tool never sees a value; `secrets-plan` reports key NAMES and presence only.

    python scripts/integrations/wrangler_tool.py whoami
    python scripts/integrations/wrangler_tool.py zones
    python scripts/integrations/wrangler_tool.py registrar-status --domain oasisai.work
    python scripts/integrations/wrangler_tool.py list-workers
    python scripts/integrations/wrangler_tool.py secrets-plan --app tiktik [--vercel-diff]
    python scripts/integrations/wrangler_tool.py secrets-push --app tiktik
    python scripts/integrations/wrangler_tool.py secrets-list --app tiktik
    python scripts/integrations/wrangler_tool.py build|preview|upload|deploy|tail --app tiktik

Registry:  config/cloudflare/apps.json          (dirs, worker names, kinds, domains)
Manifests: config/cloudflare/manifests/<app>.json (secret KEY NAMES only + scope)

Writes nothing to any Cloudflare zone. DNS stays in cloudflare_admin.py, whose
TXT-only write fence is deliberate. This tool's mutations are Workers-scoped:
secret pushes and deploys, always for a registry-listed app, always explicit.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

CAPABILITY_META = {
    "category": "release.cloudflare",
    "lifecycle": "active",
    "risk": "external_write",
    "triggers": [
        "deploy an app to cloudflare workers",
        "push secrets to a cloudflare worker",
        "check cloudflare account, zones, or registrar auto-renew",
        "vercel to cloudflare migration",
    ],
    "owner": "bravo",
    "project": "empire",
    "bridge": {"visible": False},
}

# Windows console defaults to cp1252; wrangler emits emoji/box-drawing chars.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from lib.secret_loader import load_env  # noqa: E402
from lib.subprocess_helpers import safe_run  # noqa: E402

CF_BASE = "https://api.cloudflare.com/client/v4"
# Cloudflare error 1010 blocks stock Python-urllib UAs (see cloudflare_admin.py).
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

REGISTRY_PATH = REPO_ROOT / "config" / "cloudflare" / "apps.json"
MANIFEST_DIR = REPO_ROOT / "config" / "cloudflare" / "manifests"

# Vercel-injected platform vars — never expected in .env.agents, excluded from gap math.
VERCEL_PLATFORM_KEYS = ("VERCEL",)
VERCEL_PLATFORM_PREFIXES = ("VERCEL_", "TURBO_", "NX_")


# ---------------------------------------------------------------- credentials

def _secrets() -> dict:
    return load_env()


def _cf_token(loaded: dict) -> str:
    for key in ("CLOUDFLARE_WORKERS_API_TOKEN", "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_TOKEN"):
        v = (loaded.get(key) or os.environ.get(key) or "").strip()
        if v:
            return v
    raise RuntimeError("No Cloudflare token in .env.agents (CLOUDFLARE_API_TOKEN)")


def _account_id(registry: dict, loaded: dict) -> str:
    v = (loaded.get("CLOUDFLARE_ACCOUNT_ID") or "").strip() or registry.get("account_id", "")
    if not v:
        raise RuntimeError("No account id: set CLOUDFLARE_ACCOUNT_ID or registry account_id")
    return v


def _wrangler_env(registry: dict, extra: dict | None = None) -> dict[str, str]:
    """Child env for wrangler/opennextjs invocations. Values never printed."""
    loaded = _secrets()
    env = dict(os.environ)
    env["CLOUDFLARE_API_TOKEN"] = _cf_token(loaded)
    env["CLOUDFLARE_ACCOUNT_ID"] = _account_id(registry, loaded)
    env.setdefault("WRANGLER_SEND_METRICS", "false")
    if extra:
        env.update(extra)
    return env


# ---------------------------------------------------------------- REST reads

def _cf_get(path: str, token: str, timeout: int = 30) -> dict:
    req = urllib.request.Request(
        f"{CF_BASE}{path}",
        method="GET",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "User-Agent": UA},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"success": False, "http_status": e.code, "body": e.read().decode()[:300]}


# ---------------------------------------------------------------- registry

def _registry() -> dict:
    if not REGISTRY_PATH.exists():
        raise RuntimeError(f"registry missing: {REGISTRY_PATH}")
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def _app(registry: dict, slug: str) -> dict:
    apps = registry.get("apps") or {}
    if slug not in apps:
        raise RuntimeError(f"app '{slug}' not in registry ({', '.join(sorted(apps))})")
    app = dict(apps[slug])
    app["slug"] = slug
    app_dir = Path(app["dir"])
    if not app_dir.exists():
        raise RuntimeError(f"app dir not found: {app_dir}")
    app["path"] = app_dir
    app.setdefault("worker_name", slug)
    app.setdefault("kind", "opennext")
    return app


def _manifest(slug: str) -> list[dict]:
    p = MANIFEST_DIR / f"{slug}.json"
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    return data.get("secrets") or []


def _npx() -> str:
    npx = shutil.which("npx")
    if not npx:
        raise RuntimeError("npx not found on PATH")
    return npx


def _run(cmd: list[str], *, cwd: Path, env: dict, capture: bool = False,
         stdin_text: str | None = None) -> subprocess.CompletedProcess:
    kwargs: dict = {"cwd": str(cwd), "env": env}
    if capture:
        # Explicit utf-8: Windows text mode defaults to cp1252 and wrangler's
        # output contains bytes cp1252 cannot decode (kills the reader thread).
        kwargs.update(capture_output=True, text=True, encoding="utf-8", errors="replace")
    if stdin_text is not None:
        kwargs.update(input=stdin_text)
        if "text" not in kwargs:
            kwargs.update(text=True, encoding="utf-8", errors="replace")
    return safe_run(cmd, **kwargs)


# ---------------------------------------------------------------- verbs

def cmd_whoami(registry: dict, args: argparse.Namespace) -> int:
    cwd = _app(registry, args.app)["path"] if args.app else REPO_ROOT
    wrangler = ["npx", "wrangler"] if args.app else ["npx", "-y", "wrangler@4"]
    proc = _run([_npx(), *wrangler[1:], "whoami"], cwd=cwd, env=_wrangler_env(registry), capture=True)
    print(proc.stdout.strip() or proc.stderr.strip())
    return proc.returncode


def cmd_zones(registry: dict, args: argparse.Namespace) -> int:
    out = _cf_get("/zones?per_page=50", _cf_token(_secrets()))
    if not out.get("success"):
        print(json.dumps(out, indent=2))
        return 1
    zones = out.get("result") or []
    if not zones:
        print("no zones visible to this token")
        print(json.dumps({k: out.get(k) for k in ("result_info", "messages")}, indent=2))
        return 0
    for z in zones:
        print(f"{z['name']:40} {z['status']:10} {z['id']}")
    return 0


def cmd_accounts(registry: dict, args: argparse.Namespace) -> int:
    out = _cf_get("/accounts", _cf_token(_secrets()))
    if not out.get("success"):
        print(json.dumps(out, indent=2))
        return 1
    for a in out.get("result") or []:
        print(f"{a.get('name', '?'):45} {a.get('id')}")
    return 0


def cmd_subdomain(registry: dict, args: argparse.Namespace) -> int:
    """Show (or register) the account's workers.dev subdomain."""
    loaded = _secrets()
    acct = _account_id(registry, loaded)
    token = _cf_token(loaded)
    if args.register:
        body = json.dumps({"subdomain": args.register}).encode()
        req = urllib.request.Request(
            f"{CF_BASE}/accounts/{acct}/workers/subdomain", data=body, method="PUT",
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json", "User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                out = json.loads(r.read())
        except urllib.error.HTTPError as e:
            print(f"register failed: {e.code} {e.read().decode()[:300]}")
            return 1
    else:
        out = _cf_get(f"/accounts/{acct}/workers/subdomain", token)
    print(json.dumps(out.get("result") or out, indent=2))
    return 0 if out.get("success") else 1


def cmd_registrar_status(registry: dict, args: argparse.Namespace) -> int:
    loaded = _secrets()
    acct = _account_id(registry, loaded)
    out = _cf_get(f"/accounts/{acct}/registrar/domains/{args.domain}", _cf_token(loaded))
    if not out.get("success"):
        print(f"registrar API unavailable for {args.domain} "
              f"(status {out.get('http_status')}) — likely token scope; CC checks the "
              f"Domain Registration dashboard instead.")
        return 1
    r = out.get("result") or {}
    print(json.dumps({
        "domain": args.domain,
        "auto_renew": r.get("auto_renew"),
        "expires_at": r.get("expires_at"),
        "locked": r.get("locked"),
        "current_registrar": r.get("current_registrar"),
    }, indent=2))
    return 0


def cmd_list_workers(registry: dict, args: argparse.Namespace) -> int:
    loaded = _secrets()
    out = _cf_get(f"/accounts/{_account_id(registry, loaded)}/workers/scripts", _cf_token(loaded))
    if not out.get("success"):
        print(json.dumps(out, indent=2))
        return 1
    for s in out.get("result") or []:
        print(s.get("id"))
    return 0


def _vercel_prod_keys(vercel_project: str) -> list[str]:
    """Key NAMES only, via the existing masked-by-design tool."""
    proc = safe_run(
        [sys.executable, str(REPO_ROOT / "scripts" / "integrations" / "vercel_env_tool.py"),
         "--json", "list", "--project", vercel_project, "--env", "production"],
        capture_output=True, text=True, cwd=str(REPO_ROOT), env=dict(os.environ),
    )
    if proc.returncode != 0:
        raise RuntimeError(f"vercel_env_tool list failed for {vercel_project}: {proc.stderr.strip()[:200]}")
    payload = json.loads(proc.stdout)
    envs = payload.get("result", payload)
    if isinstance(envs, dict):
        envs = envs.get("envs") or envs.get("result") or []
    keys = []
    for e in envs:
        k = e.get("key") if isinstance(e, dict) else None
        if not k or k in VERCEL_PLATFORM_KEYS or k.startswith(VERCEL_PLATFORM_PREFIXES):
            continue
        keys.append(k)
    return sorted(set(keys))


def _plan(registry: dict, slug: str, vercel_diff: bool) -> dict:
    app = _app(registry, slug)
    manifest = _manifest(slug)
    manifest_keys = {m["key"]: m for m in manifest}
    loaded = _secrets()

    def present(entry: dict) -> bool:
        source = entry.get("source") or entry["key"]
        return bool((loaded.get(source) or "").strip())

    ok = sorted(k for k, m in manifest_keys.items() if present(m))
    missing = sorted(k for k, m in manifest_keys.items() if not present(m))
    vercel_only, extra_local = [], []
    if vercel_diff:
        vkeys = _vercel_prod_keys(app.get("vercel_project", slug))
        vercel_only = sorted(k for k in vkeys if k not in manifest_keys)
        for k in vercel_only:
            if not (loaded.get(k) or "").strip():
                missing.append(k)
        missing = sorted(set(missing))
        extra_local = sorted(k for k in manifest_keys if k not in vkeys)
    return {"app": slug, "ok": ok, "missing_from_env_agents": missing,
            "vercel_keys_not_in_manifest": vercel_only,
            "manifest_keys_not_in_vercel": extra_local}


def cmd_secrets_plan(registry: dict, args: argparse.Namespace) -> int:
    plan = _plan(registry, args.app, args.vercel_diff)
    print(json.dumps(plan, indent=2))
    return 1 if plan["missing_from_env_agents"] else 0


def cmd_secrets_push(registry: dict, args: argparse.Namespace) -> int:
    app = _app(registry, args.app)
    plan = _plan(registry, args.app, vercel_diff=False)
    if plan["missing_from_env_agents"]:
        print(f"REFUSED: gaps in .env.agents: {', '.join(plan['missing_from_env_agents'])}")
        return 1
    loaded = _secrets()
    values: dict[str, str] = {}
    for m in _manifest(args.app):
        if m.get("scope", "runtime") in ("runtime", "both"):
            values[m["key"]] = (loaded.get(m.get("source") or m["key"]) or "").strip()
    if not values:
        print(f"no runtime-scope secrets in manifest for {args.app}; nothing to push")
        return 0
    env = _wrangler_env(registry)
    # Bulk first (values via stdin JSON, never argv); per-key stdin fallback.
    proc = _run([_npx(), "wrangler", "secret", "bulk", "--name", app["worker_name"]],
                cwd=app["path"], env=env, capture=True, stdin_text=json.dumps(values))
    if proc.returncode == 0:
        print(f"pushed {len(values)} secrets to {app['worker_name']} (bulk): "
              f"{', '.join(sorted(values))}")
        return 0
    print(f"bulk push failed (rc={proc.returncode}); falling back to per-key put")
    failures = []
    for key in sorted(values):
        p = _run([_npx(), "wrangler", "secret", "put", key, "--name", app["worker_name"]],
                 cwd=app["path"], env=env, capture=True, stdin_text=values[key] + "\n")
        status = "ok" if p.returncode == 0 else "FAIL"
        print(f"  {key}: {status}")
        if p.returncode != 0:
            failures.append((key, (p.stderr or p.stdout or "").strip()[:200]))
    for key, err in failures:
        print(f"FAIL {key}: {err}")
    return 1 if failures else 0


def cmd_secrets_list(registry: dict, args: argparse.Namespace) -> int:
    app = _app(registry, args.app)
    proc = _run([_npx(), "wrangler", "secret", "list", "--name", app["worker_name"]],
                cwd=app["path"], env=_wrangler_env(registry), capture=True)
    print(proc.stdout.strip() or proc.stderr.strip())
    return proc.returncode


def _build_env(registry: dict, slug: str) -> dict[str, str]:
    app = _app(registry, slug)
    loaded = _secrets()
    extra = dict(app.get("build_env") or {})
    for m in _manifest(slug):
        if m.get("scope") in ("build", "both"):
            v = (loaded.get(m.get("source") or m["key"]) or "").strip()
            if v:
                extra[m["key"]] = v
    return _wrangler_env(registry, extra)


def _opennext(registry: dict, slug: str, verb: str, capture: bool = True) -> int:
    """capture defaults True: the .cmd shim + windowless flags swallow child
    stdout otherwise, which turns real failures into silent ones."""
    app = _app(registry, slug)
    if app["kind"] == "static-worker":
        cmd = {"build": ["npm", "run", "build"], "preview": [_npx(), "wrangler", "dev"],
               "upload": [_npx(), "wrangler", "versions", "upload"],
               "deploy": [_npx(), "wrangler", "deploy"]}[verb]
        if cmd[0] == "npm":
            cmd[0] = shutil.which("npm") or "npm"
    else:
        cmd = [_npx(), "opennextjs-cloudflare", verb]
    if verb == "preview":
        capture = False  # interactive local server — stream it
    proc = _run(cmd, cwd=app["path"], env=_build_env(registry, slug), capture=capture)
    if capture:
        print(proc.stdout[-6000:] if proc.stdout else "", end="")
        if proc.returncode != 0 and proc.stderr:
            print(proc.stderr[-6000:], file=sys.stderr)
    return proc.returncode


def cmd_build(registry: dict, args: argparse.Namespace) -> int:
    return _opennext(registry, args.app, "build")


def cmd_preview(registry: dict, args: argparse.Namespace) -> int:
    return _opennext(registry, args.app, "preview")


def cmd_upload(registry: dict, args: argparse.Namespace) -> int:
    return _opennext(registry, args.app, "upload")


def cmd_deploy(registry: dict, args: argparse.Namespace) -> int:
    """build -> deploy (creates the worker on first run) -> secrets push.

    A worker must exist before `versions upload` or `secret put` can target it,
    so deploy comes first; pushing secrets afterwards binds them to the live
    worker immediately (each push creates a new version). The seconds-long
    window where the fresh worker lacks secrets serves zero traffic — nothing
    routes to a brand-new workers.dev URL."""
    slug = args.app
    if not args.skip_build and _opennext(registry, slug, "build"):
        print("build failed; aborting deploy")
        return 1
    if _opennext(registry, slug, "deploy"):
        print("deploy failed")
        return 1
    if not args.skip_secrets and cmd_secrets_push(registry, args):
        print("deploy is live but secrets push FAILED — worker may error until pushed")
        return 1
    return 0


def cmd_tail(registry: dict, args: argparse.Namespace) -> int:
    app = _app(registry, args.app)
    proc = _run([_npx(), "wrangler", "tail", "--format", "pretty", app["worker_name"]],
                cwd=app["path"], env=_wrangler_env(registry))
    return proc.returncode


# ---------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description="Cloudflare Workers pipeline (fleet migration)")
    sub = ap.add_subparsers(dest="verb", required=True)

    def add(name, fn, needs_app=False, **extra_flags):
        p = sub.add_parser(name)
        if needs_app:
            p.add_argument("--app", required=True)
        else:
            p.add_argument("--app", default=None)
        for flag, kw in extra_flags.items():
            p.add_argument(flag, **kw)
        p.set_defaults(fn=fn)

    add("whoami", cmd_whoami)
    add("accounts", cmd_accounts)
    add("zones", cmd_zones)
    add("registrar-status", cmd_registrar_status, **{"--domain": {"required": True}})
    add("subdomain", cmd_subdomain, **{"--register": {"default": None}})
    add("list-workers", cmd_list_workers)
    add("secrets-plan", cmd_secrets_plan, needs_app=True,
        **{"--vercel-diff": {"action": "store_true", "dest": "vercel_diff"}})
    add("secrets-push", cmd_secrets_push, needs_app=True)
    add("secrets-list", cmd_secrets_list, needs_app=True)
    add("build", cmd_build, needs_app=True)
    add("preview", cmd_preview, needs_app=True)
    add("upload", cmd_upload, needs_app=True)
    add("deploy", cmd_deploy, needs_app=True,
        **{"--skip-build": {"action": "store_true", "dest": "skip_build"},
           "--skip-secrets": {"action": "store_true", "dest": "skip_secrets"}})
    add("tail", cmd_tail, needs_app=True)

    args = ap.parse_args()
    try:
        registry = _registry()
        return args.fn(registry, args)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
