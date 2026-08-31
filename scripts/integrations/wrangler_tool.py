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
import datetime as _dt
import json
import os
import re
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
    """The REGISTRY wins for deploy targeting.

    It used to be the other way round, and that made the registry's
    `account_id` decorative: on 2026-08-30 the fleet was re-pointed at the
    zone-owning account by editing the registry, and every command silently
    kept hitting the old account because the env store still held the previous
    id. A migration would have been reported as done against an account it
    never touched. The registry is the explicit, version-controlled, per-fleet
    declaration of WHERE the fleet lives; the env var remains the fallback (and
    is still what other tools use for R2, which lives elsewhere)."""
    v = (registry.get("account_id") or "").strip() or (loaded.get("CLOUDFLARE_ACCOUNT_ID") or "").strip()
    if not v:
        raise RuntimeError("No account id: set registry account_id or CLOUDFLARE_ACCOUNT_ID")
    return v


def _wrangler_env(registry: dict, extra: dict | None = None) -> dict[str, str]:
    """Child env for wrangler/opennextjs invocations. Values never printed.

    Wrangler's identity vars are applied AFTER `extra`: an app's own env can
    legitimately carry CLOUDFLARE_ACCOUNT_ID for its R2 API calls (nostalgic
    does, pointing at the R2-owning account) and must never redirect the
    DEPLOY to that account."""
    loaded = _secrets()
    env = dict(os.environ)
    if extra:
        env.update(extra)
    env["CLOUDFLARE_API_TOKEN"] = _cf_token(loaded)
    env["CLOUDFLARE_ACCOUNT_ID"] = _account_id(registry, loaded)
    env.setdefault("WRANGLER_SEND_METRICS", "false")
    return env


# ---------------------------------------------------------------- REST reads

def _cf_call(method: str, path: str, token: str, body: dict | None = None, timeout: int = 40) -> dict:
    """One mutating-call shape for the whole tool. Was open-coded three times
    (www cutover, Blue Rise attach, zone probes) before this existed."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{CF_BASE}{path}", data=data, method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                 "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read())
        except Exception:
            return {"success": False, "http_status": e.code}


def _cf_delete(path: str, token: str) -> dict:
    return _cf_call("DELETE", path, token)


def _cf_put(path: str, token: str, body: dict) -> dict:
    return _cf_call("PUT", path, token, body)


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


def _cf_patch(path: str, token: str, payload: dict, timeout: int = 30) -> dict:
    req = urllib.request.Request(
        f"{CF_BASE}{path}",
        data=json.dumps(payload).encode(),
        method="PATCH",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "User-Agent": UA},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"success": False, "http_status": e.code, "body": e.read().decode()[:300]}


def cmd_zone_https(registry: dict, args: argparse.Namespace) -> int:
    """Report (and optionally fix) zones that still serve cleartext HTTP.

    Vercel answered plain HTTP with a 308 to HTTPS. Cloudflare does not do that
    by default, so every hostname moved to Workers in this migration began
    serving its login page over cleartext — measured on all six. Session cookies
    marked Secure are not sent over HTTP, so sessions do not leak directly, but
    serving the login FORM unencrypted is an SSL-strip surface: an attacker on
    the path can rewrite it before it reaches the user.

    `Always Use HTTPS` is a per-zone setting, so it must be checked per zone
    rather than fixed once. This only ever turns encryption ON — there is no
    path here that weakens a zone.
    """
    token = _cf_token(_secrets())
    out = _cf_get("/zones?per_page=50", token)
    if not out.get("success"):
        print(json.dumps(out, indent=2))
        return 1
    zones = out.get("result") or []
    if args.zone:
        zones = [z for z in zones if z["name"] == args.zone]
        if not zones:
            print(f"no zone named {args.zone} visible to this token")
            return 1

    offenders, rc = [], 0
    for z in zones:
        s = _cf_get(f"/zones/{z['id']}/settings/always_use_https", token)
        if not s.get("success"):
            print(f"  {z['name']:38} UNREADABLE — {s.get('body', s.get('http_status'))}")
            rc = 1                      # unreadable is not the same as compliant
            continue
        value = (s.get("result") or {}).get("value")
        if value == "on":
            print(f"  {z['name']:38} https-only ON")
            continue
        offenders.append(z)
        print(f"  {z['name']:38} CLEARTEXT ALLOWED (always_use_https={value})")

    if not offenders:
        print("\nevery visible zone forces HTTPS.")
        return rc
    if not args.enable:
        print(f"\n{len(offenders)} zone(s) still serve cleartext. Re-run with --enable to fix.")
        return 1

    for z in offenders:
        res = _cf_patch(f"/zones/{z['id']}/settings/always_use_https", token, {"value": "on"})
        ok = res.get("success") and (res.get("result") or {}).get("value") == "on"
        print(f"  {'ENABLED ' if ok else 'FAILED  '} {z['name']}")
        if not ok:
            print(f"           {res.get('body', res)}")
            rc = 1
    return rc


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
         stdin_text: str | None = None,
         timeout: float | None = None) -> subprocess.CompletedProcess:
    kwargs: dict = {"cwd": str(cwd), "env": env}
    if timeout is not None:
        kwargs["timeout"] = timeout
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
        # A zone stuck at `pending` is waiting on the REGISTRAR, and the single
        # most useful thing to print is the exact pair to enter there. Twice a
        # repoint was reported done while the registrar still served its old
        # nameservers, and "still pending" was not actionable feedback.
        if z.get("status") == "pending":
            assigned = z.get("name_servers") or []
            current = z.get("original_name_servers") or []
            print(f"{'':40} SET THESE AT THE REGISTRAR: {', '.join(assigned) or 'not yet assigned'}")
            if current:
                print(f"{'':40} registrar currently serves:  {', '.join(current)}")
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


def cmd_zone_baseline(registry: dict, args: argparse.Namespace) -> int:
    """Snapshot every visible zone's DNS records to state/cloudflare_baselines/<date>/.

    This is the rollback reference for every cutover, and the integrity check
    after one. It also flags the failure that actually bites when a zone is
    onboarded: Cloudflare's record scan is best-effort, so a zone can go
    ACTIVE with its MX records missing — mail stops, silently, and DNS looks
    fine. Any active zone with no MX is called out loudly here.
    """
    token = _cf_token(_secrets())
    out = REPO_ROOT / "state" / "cloudflare_baselines" / (args.date or _dt.date.today().isoformat())
    out.mkdir(parents=True, exist_ok=True)
    zres = _cf_get("/zones?per_page=50", token)
    if not zres.get("success"):
        print(json.dumps(zres, indent=2))
        return 1
    problems = 0
    for z in sorted(zres.get("result") or [], key=lambda x: x["name"]):
        recs = _cf_get(f"/zones/{z['id']}/dns_records?per_page=200", token)
        rows = recs.get("result") or []
        (out / f"{z['name']}.dns_records.json").write_text(
            json.dumps(rows, indent=2), encoding="utf-8")
        counts: dict[str, int] = {}
        for r in rows:
            counts[r["type"]] = counts.get(r["type"], 0) + 1
        mx = counts.get("MX", 0)
        print(f"\n=== {z['name']}  [{z['status']}]  {len(rows)} records  {counts}")
        print(f"    NS: {', '.join((z.get('name_servers') or [])[:2])}")
        if mx:
            print(f"    mail: {mx} MX record(s)")
        elif z["status"] == "active":
            problems += 1
            print("    *** NO MX RECORDS AND THE ZONE IS ACTIVE — inbound mail for this "
                  "domain is going nowhere. Verify against the previous DNS host. ***")
        else:
            print("    mail: no MX (zone still pending — add before repointing nameservers)")
        for r in rows:
            if r["type"] in ("A", "AAAA", "CNAME") and r["name"] in (z["name"], f"www.{z['name']}"):
                print(f"    {r['type']:6} {r['name']:32} -> {r['content'][:44]} proxied={r.get('proxied')}")
    print(f"\nbaselines written to {out}")
    if problems:
        print(f"WARNING: {problems} ACTIVE zone(s) have no MX records.")
    return 0


def _title_of(url: str) -> str | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=25) as r:
            body = r.read(200_000).decode("utf-8", "replace")
    except Exception:
        return None
    m = re.search(r"<title[^>]*>(.*?)</title>", body, re.I | re.S)
    return " ".join(m.group(1).split()) if m else None


def cmd_attach_domain(registry: dict, args: argparse.Namespace) -> int:
    """Point a hostname at an app's Worker: delete the existing A/AAAA/CNAME,
    then bind the Workers custom domain.

    THE TITLE GUARD IS THE POINT. On 2026-08-30 an instruction to attach
    breezeadvance.credit to `breezeadvance-website` would have replaced a live
    CLIENT PORTAL with a marketing page — the registry's domain map was wrong,
    and only comparing what the live host actually serves against what the
    Worker serves caught it. That comparison is now mandatory: a mismatch
    ABORTS unless --force is passed with eyes open.

    Rollback values for every deleted record are printed BEFORE deletion.
    """
    app = _app(registry, args.app)
    loaded = _secrets()
    token = _cf_token(loaded)
    acct = _account_id(registry, loaded)
    host = args.hostname

    zres = _cf_get(f"/zones?name={host.split('.', 1)[1] if host.count('.') > 1 else host}", token)
    zones = zres.get("result") or []
    if not zones:
        zres = _cf_get(f"/zones?name={host}", token)
        zones = zres.get("result") or []
    if not zones:
        print(f"no Cloudflare zone found for {host} — onboard the zone first")
        return 1
    zone = zones[0]
    print(f"[zone] {zone['name']} ({zone['status']}) {zone['id']}")

    worker_url = f"https://{app['worker_name']}.{args.subdomain}.workers.dev/"
    live_title, worker_title = _title_of(f"https://{host}/"), _title_of(worker_url)
    print(f"[live]   {host} -> {live_title!r}")
    print(f"[worker] {app['worker_name']} -> {worker_title!r}")
    if worker_title is None:
        print("ABORT: the Worker did not respond with HTML — deploy/verify it first.")
        return 1
    if live_title is not None and live_title != worker_title and not args.force:
        print("\nABORT: the live host and the Worker serve DIFFERENT pages.\n"
              "  This is the check that caught breezeadvance.credit serving a client\n"
              "  portal while its 'marketing' Worker served a brochure. Confirm which\n"
              "  app should own this hostname (check the Vercel project's domains),\n"
              "  then re-run with --force only if the difference is intended.")
        return 1

    for rtype in ("A", "AAAA", "CNAME"):
        recs = _cf_get(f"/zones/{zone['id']}/dns_records?name={host}&type={rtype}", token)
        for r in recs.get("result") or []:
            print(f"[rollback] {r['type']} {r['name']} -> {r['content']} "
                  f"proxied={r.get('proxied')} ttl={r.get('ttl')}")
            if args.dry_run:
                continue
            d = _cf_delete(f"/zones/{zone['id']}/dns_records/{r['id']}", token)
            if not d.get("success"):
                print("DELETE FAILED:", [e.get("message") for e in (d.get("errors") or [])][:1])
                return 1
    if args.dry_run:
        print("\ndry run — no records deleted, no binding created.")
        return 0

    out = _cf_put(f"/accounts/{acct}/workers/domains", token,
                  {"environment": "production", "hostname": host,
                   "service": app["worker_name"], "zone_id": zone["id"]})
    if not out.get("success"):
        print("BIND FAILED:", [f"{e.get('code')}: {e.get('message')}" for e in (out.get("errors") or [])][:2])
        print("Recreate the records printed above to roll back.")
        return 1
    print(f"BOUND {host} -> {app['worker_name']}")
    return 0


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
    missing = plan["missing_from_env_agents"]
    if missing and not getattr(args, "allow_missing", False):
        print(f"REFUSED: gaps in the agents env store: {', '.join(missing)}")
        print("Deploying a half-configured Worker is how a secret becomes a runtime 500.\n"
              "If every missing key is genuinely optional AND fails CLOSED when unset,\n"
              "re-run with --allow-missing; the skipped names are printed either way.")
        return 1
    if missing:
        # Loud on purpose: an override that prints nothing becomes the default.
        print(f"WARNING --allow-missing: deploying WITHOUT {len(missing)} secret(s): "
              f"{', '.join(missing)}")
    loaded = _secrets()
    values: dict[str, str] = {}
    for m in _manifest(args.app):
        if m.get("scope", "runtime") in ("runtime", "both"):
            v = (loaded.get(m.get("source") or m["key"]) or "").strip()
            # Skip empties: setting a secret to "" is NOT the same as leaving it
            # unset. Code that branches on `=== undefined`, or that treats ""
            # as a configured-but-blank value, behaves differently between the
            # two — and the fail-closed reasoning that justified --allow-missing
            # was about the key being ABSENT.
            if v:
                values[m["key"]] = v
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
    """Vercel injects the FULL env at build (module-scope code like
    `new Stripe(process.env.KEY)` runs during page-data collection), so the
    build env gets every manifest key. `scope` only governs which keys are
    pushed as worker secrets at deploy."""
    app = _app(registry, slug)
    loaded = _secrets()
    extra = dict(app.get("build_env") or {})
    # Marks the build as Cloudflare-bound: apps gate migration-only next.config
    # behavior (e.g. heavy tracing includes) on this so their VERCEL builds,
    # which still ship production, stay untouched.
    extra["CF_MIGRATION_BUILD"] = "1"
    for m in _manifest(slug):
        v = (loaded.get(m.get("source") or m["key"]) or "").strip()
        if v:
            extra[m["key"]] = v
    return _wrangler_env(registry, extra)


# Single source of truth for "how does this kind of app build/deploy" — shared
# by the local runner (_opennext) and the CI generator (cmd_workflow) so a new
# kind can't be added to one and forgotten in the other.
BUILD_COMMAND = {
    "opennext": "npx opennextjs-cloudflare build",
    "static-worker": "npm run build",
}
BUILD_LABEL = {
    "opennext": "OpenNext -> Cloudflare Worker",
    "static-worker": "Vite static assets",
}


def _opennext(registry: dict, slug: str, verb: str, capture: bool = True) -> int:
    """capture defaults True: the .cmd shim + windowless flags swallow child
    stdout otherwise, which turns real failures into silent ones."""
    app = _app(registry, slug)
    if app["kind"] == "static-worker":
        cmd = {"build": BUILD_COMMAND["static-worker"].split(),
               "preview": [_npx(), "wrangler", "dev"],
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
    # Name the destination on every deploy. An account switch that is invisible
    # is an account switch that gets reported as having happened when it did not.
    print(f"[target] account={_account_id(registry, _secrets())} app={slug}")
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


WRANGLER_JSONC_TEMPLATE = """{
  "$schema": "node_modules/wrangler/config-schema.json",
  "name": "%(name)s",
  "main": ".open-next/worker.js",
  "compatibility_date": "2026-08-01",
  "compatibility_flags": ["nodejs_compat", "global_fetch_strictly_public"],
  "assets": {
    "binding": "ASSETS",
    "directory": ".open-next/assets"
  },
  "services": [
    { "binding": "WORKER_SELF_REFERENCE", "service": "%(name)s" }
  ],
  "observability": {
    "enabled": true
  }
}
"""

OPEN_NEXT_CONFIG = """import { defineCloudflareConfig } from "@opennextjs/cloudflare";

// Fleet default: no R2 incremental cache (pages are static or dynamic;
// add r2IncrementalCache only if ISR behavior is observed to need it).
export default defineCloudflareConfig({});
"""


def cmd_scaffold(registry: dict, args: argparse.Namespace) -> int:
    """Write wrangler.jsonc + open-next.config.ts + .gitignore entries for an
    opennext-kind app. Refuses to overwrite an existing wrangler.jsonc unless
    --force (a hand-tuned config must not be silently regenerated)."""
    app = _app(registry, args.app)
    if app["kind"] != "opennext":
        print(f"{args.app} is kind={app['kind']} — scaffold only handles opennext")
        return 2
    wj = app["path"] / "wrangler.jsonc"
    if wj.exists() and not args.force:
        print(f"REFUSED: {wj} exists (use --force to overwrite)")
        return 1
    wj.write_text(WRANGLER_JSONC_TEMPLATE % {"name": app["worker_name"]},
                  encoding="utf-8", newline="\n")
    onc = app["path"] / "open-next.config.ts"
    if not onc.exists() or args.force:
        onc.write_text(OPEN_NEXT_CONFIG, encoding="utf-8", newline="\n")
    gi = app["path"] / ".gitignore"
    text = gi.read_text(encoding="utf-8") if gi.exists() else ""
    if ".open-next" not in text:
        text += "\n# Cloudflare/OpenNext build output\n.open-next/\n.wrangler/\n"
        gi.write_text(text, encoding="utf-8", newline="\n")
    print(f"scaffolded {args.app}: wrangler.jsonc + open-next.config.ts + .gitignore")
    return 0


WORKFLOW_TEMPLATE = """# Deploy to Cloudflare Workers — GENERATED by
# Business-Empire-Agent `scripts/integrations/wrangler_tool.py workflow --app %(slug)s`.
# Regenerate rather than hand-editing (the build env is derived from the app's
# secret manifest, which is the single source of truth for key NAMES).
#
# WHAT THIS DOES: every push to main builds the Worker%(build_desc)s and deploys it.
# WHAT IT DOES NOT DO: push Worker SECRETS. Those stay operator-managed from the
# agents env store (`wrangler_tool.py secrets-push --app %(slug)s`) — a deploy does
# not clear a Worker's existing secrets, so CI never needs them at runtime.
#
# REQUIRED REPO SECRETS (CC adds these in Settings → Secrets → Actions):
#   CLOUDFLARE_API_TOKEN   — Workers Scripts:Edit on the deploying account
#   CLOUDFLARE_ACCOUNT_ID  — %(account_id)s
%(build_secret_docs)s#
# Until CLOUDFLARE_API_TOKEN exists the job still BUILDS (real signal on build
# breakage) and SKIPS the deploy with a warning — no red CI while the migration
# waits on operator gates.
name: Deploy to Cloudflare Workers

on:
  push:
    branches: [main]
  workflow_dispatch:

concurrency:
  group: cf-deploy-${{ github.ref }}
  cancel-in-progress: true

jobs:
  deploy:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '22'
          cache: npm

      - name: Install dependencies
        run: npm ci

      # NOTE: the deploy step below is gated on this step's OUTPUT, not on
      # `if: ${{ secrets.CLOUDFLARE_API_TOKEN != '' }}`. GitHub does not expose
      # the `secrets` context to `if:` at job OR step level (docs, Context
      # availability: step-level `if` gets github/needs/strategy/matrix/job/
      # runner/env/vars/steps/inputs only). Written that way the condition never
      # sees the token, evaluates false, and the deploy SILENTLY never runs.
      # Reading the secret into `env` here is the supported workaround.
      - name: Preflight - is the Cloudflare token configured?
        id: preflight
        env:
          TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
        run: |
          if [ -n "$TOKEN" ]; then
            echo "ready=true" >> "$GITHUB_OUTPUT"
          else
            echo "ready=false" >> "$GITHUB_OUTPUT"
            # notice, not warning: an un-provisioned repo is an expected state
            # during the migration and must not decorate every run with a
            # yellow annotation operators learn to ignore.
            echo "::notice::CLOUDFLARE_API_TOKEN not set - build-only run, deploy skipped."
          fi

      - name: Build (%(build_label)s)
        run: %(build_cmd)s
        env:
%(build_env)s
      - name: Deploy to Cloudflare Workers
        if: steps.preflight.outputs.ready == 'true'
        uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          accountId: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
          command: %(deploy_cmd)s
"""


def cmd_workflow(registry: dict, args: argparse.Namespace) -> int:
    """Generate .github/workflows/deploy-cloudflare.yml for an app, with the
    build env derived from its secret manifest (names only — values come from
    GitHub repo secrets that CC adds)."""
    app = _app(registry, args.app)
    slug = app["slug"]
    kind = app["kind"]
    build_cmd = BUILD_COMMAND[kind]
    build_label = BUILD_LABEL[kind]
    build_desc = (" (static assets + router worker)" if kind == "static-worker"
                  else " with @opennextjs/cloudflare")

    lines: list[str] = []
    docs: list[str] = []
    for key, value in (app.get("build_env") or {}).items():
        lines.append(f"          {key}: {json.dumps(value)}")
    lines.append('          CF_MIGRATION_BUILD: "1"')
    # EVERY manifest key, not just build-scoped ones — this must mirror
    # _build_env() exactly. Next runs module-scope code during page-data
    # collection (`const stripe = new Stripe(process.env.STRIPE_SECRET_KEY)`),
    # so a RUNTIME-scoped secret can still be required at BUILD time. CI proved
    # it on 2026-08-30: nostalgic-requests failed with "Neither apiKey nor
    # config.authenticator provided" because the generator emitted only the
    # build-scoped subset while the local builder injected everything.
    for m in _manifest(slug):
        lines.append("          %s: ${{ secrets.%s }}" % (m["key"], m["key"]))
        scope = m.get("scope", "runtime")
        docs.append(f"#   {m['key']}{'  (inlined into the client bundle)' if scope in ('build', 'both') else ''}\n")
    if docs:
        docs.insert(0, "#   -- every manifest key: the build needs runtime secrets too,\n"
                       "#      because module-scope SDK init runs during page-data collection\n")

    text = WORKFLOW_TEMPLATE % {
        "slug": slug,
        "account_id": registry.get("account_id", "<account id>"),
        "build_cmd": build_cmd,
        "deploy_cmd": "deploy",  # wrangler-action reads the repo's wrangler.jsonc
        "build_label": build_label,
        "build_desc": build_desc,
        "build_env": "\n".join(lines) + "\n",
        "build_secret_docs": "".join(docs),
    }
    dest = app["path"] / ".github" / "workflows" / "deploy-cloudflare.yml"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {dest} ({len(docs)} build secret(s) referenced)")
    return 0


def cmd_tail(registry: dict, args: argparse.Namespace) -> int:
    """Bounded log sample (default 120s). An unbounded stream is useless here:
    the windowless .cmd shim swallows inherited stdout (discovered 2026-08-30 —
    a 400s tail produced zero bytes), and agent workflows need a capture that
    terminates. On expiry the captured lines are printed."""
    app = _app(registry, args.app)
    from lib.subprocess_helpers import safe_popen
    cmd = [_npx(), "wrangler", "tail", "--format", "pretty", app["worker_name"]]
    proc = safe_popen(cmd, cwd=str(app["path"]), env=_wrangler_env(registry),
                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                      text=True, encoding="utf-8", errors="replace")
    try:
        out, _ = proc.communicate(timeout=args.seconds)
    except subprocess.TimeoutExpired:  # expected exit path for a tail sample
        # The npx .cmd shim's grandchild (node/wrangler) survives a plain
        # kill() and keeps the pipe open forever — kill the whole tree.
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                       capture_output=True)
        out, _ = proc.communicate()
    print((out or "")[-8000:] or "(no log lines captured in the window)")
    return 0


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
    add("zone-https", cmd_zone_https,
        **{"--zone": {"default": None, "help": "one zone name; default is every visible zone"},
           "--enable": {"action": "store_true", "help": "turn Always Use HTTPS on where it is off"}})
    add("zone-baseline", cmd_zone_baseline, **{"--date": {"default": None}})
    add("attach-domain", cmd_attach_domain, needs_app=True,
        **{"--hostname": {"required": True},
           "--subdomain": {"default": "oasisaisolutions"},
           "--dry-run": {"action": "store_true", "dest": "dry_run"},
           "--force": {"action": "store_true", "dest": "force"}})
    add("registrar-status", cmd_registrar_status, **{"--domain": {"required": True}})
    add("subdomain", cmd_subdomain, **{"--register": {"default": None}})
    add("list-workers", cmd_list_workers)
    add("secrets-plan", cmd_secrets_plan, needs_app=True,
        **{"--vercel-diff": {"action": "store_true", "dest": "vercel_diff"}})
    add("secrets-push", cmd_secrets_push, needs_app=True,
        **{"--allow-missing": {"action": "store_true", "dest": "allow_missing"}})
    add("secrets-list", cmd_secrets_list, needs_app=True)
    add("build", cmd_build, needs_app=True)
    add("preview", cmd_preview, needs_app=True)
    add("upload", cmd_upload, needs_app=True)
    add("deploy", cmd_deploy, needs_app=True,
        **{"--skip-build": {"action": "store_true", "dest": "skip_build"},
           "--skip-secrets": {"action": "store_true", "dest": "skip_secrets"}})
    add("tail", cmd_tail, needs_app=True,
        **{"--seconds": {"type": float, "default": 120.0, "dest": "seconds"}})
    add("workflow", cmd_workflow, needs_app=True)
    add("scaffold", cmd_scaffold, needs_app=True,
        **{"--force": {"action": "store_true", "dest": "force"}})

    args = ap.parse_args()
    try:
        registry = _registry()
        return args.fn(registry, args)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
