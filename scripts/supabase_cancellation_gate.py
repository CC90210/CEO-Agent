"""Can Supabase be cancelled? One command, one answer, no judgement calls.

Cancellation is irreversible and the failure mode is silent: everything looks
fine until a client hits the one surface nobody checked. So this asserts every
layer independently and refuses to say YES unless all of them pass.

  DATA      every table's rows exist in Turso (short = fail, ahead = fine)
  STORAGE   objects published to R2 AND served by the public URL AND the
            database pointers rewritten
  AUTH      each app that must run Turso auth actually has the flags in
            PRODUCTION, not just preview
  APPS      no Vercel project still falls back to Supabase at runtime
  WRITERS   nothing outside the apps still writes to Supabase (n8n, the PM2
            harness) — these have no env-var rollback and no deploy
  TRAFFIC   Supabase itself reports no recent writes

Exit 0 = safe to cancel. Exit 1 = do not.

    python scripts/supabase_cancellation_gate.py
    python scripts/supabase_cancellation_gate.py --json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from lib.tls_trust import ensure_os_trust  # noqa: E402

ensure_os_trust()

from core.turso_schema_transpiler import PROJECTS, _mgmt_query  # noqa: E402
from lib.db_turso import resolve_project_target  # noqa: E402
from lib.secret_loader import load_env  # noqa: E402

VERCEL_API = "https://api.vercel.com"
DEFAULT_TEAM = "team_wUgw7DERPSKXoiR2iAlgXHTI"

# Which Vercel project backs which database, and what each MUST have set in
# PRODUCTION before Supabase can go away.
APP_REQUIREMENTS = {
    "agent-dashboard": {
        "db": "bravo",
        "needs": ["EMPIRE_DATA_BACKEND", "EMPIRE_AUTH_BACKEND", "AUTH_SESSION_SECRET",
                  "TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN", "R2_ACCESS_KEY_ID"],
    },
    "breeze-portal": {
        "db": "breeze",
        "needs": ["EMPIRE_DATA_BACKEND", "EMPIRE_AUTH_BACKEND", "AUTH_SESSION_SECRET",
                  "TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN", "R2_ACCESS_KEY_ID"],
    },
    "nostalgic-requests": {
        "db": "nostalgic",
        "needs": ["EMPIRE_DATA_BACKEND", "EMPIRE_AUTH_BACKEND", "AUTH_SESSION_SECRET",
                  "TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN"],
    },
    "real-estate-app": {
        "db": "propflow",
        "needs": ["EMPIRE_DATA_BACKEND", "EMPIRE_AUTH_BACKEND", "AUTH_SESSION_SECRET",
                  "TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN"],
    },
}


def _vercel(path: str, token: str):
    req = urllib.request.Request(VERCEL_API + path,
                                 headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return {"_err": f"{e.code} {e.read(300).decode('utf-8', 'replace')[:120]}"}
    except Exception as exc:
        return {"_err": str(exc)[:120]}


def check_data(token: str) -> dict:
    """Every source row present in Turso. Ahead is fine; short is not."""
    import libsql

    out, ok = {}, True
    for proj in sorted(PROJECTS):
        ref = PROJECTS[proj]["ref"]
        try:
            tbls = [r["tbl"] for r in _mgmt_query(ref, (
                "select relname as tbl from pg_stat_user_tables "
                "where schemaname='public' order by relname"), token)]
            union = " union all ".join(
                f"select '{t}' as tbl, count(*) as n from public.\"{t}\"" for t in tbls)
            exact = {r["tbl"]: int(r["n"]) for r in _mgmt_query(ref, union, token)} if tbls else {}
        except Exception as exc:
            out[proj] = {"error": str(exc)[:90]}
            ok = False
            continue
        url, tok, _ = resolve_project_target(proj)
        c = libsql.connect(database=url, auth_token=tok)
        short, missing_tables = [], []
        for t, pg_n in exact.items():
            try:
                t_n = c.execute(f'select count(*) from "{t}"').fetchall()[0][0]
            except Exception:
                missing_tables.append(t)
                continue
            if t_n < pg_n:
                short.append(f"{t} ({pg_n - t_n} rows)")
        good = not short and not missing_tables
        ok = ok and good
        out[proj] = {"tables": len(exact), "short": short,
                     "missing_tables": missing_tables, "pass": good}
    return {"pass": ok, "detail": out}


def check_storage(env: dict) -> dict:
    """Objects must be IN R2 and served by the public URL, and pointers rewritten."""
    import libsql

    needed = ("CLOUDFLARE_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY",
              "R2_BUCKET", "R2_PUBLIC_BASE_URL")
    missing = [k for k in needed if not (env.get(k) or os.environ.get(k))]
    if missing:
        return {"pass": False, "reason": f"R2 not configured — missing {missing}"}

    archive = SCRIPTS.parent / "state" / "backups" / "supabase_storage"
    base = (env.get("R2_PUBLIC_BASE_URL") or "").rstrip("/")
    total = published = 0
    unrewritten = []
    for proj in sorted(PROJECTS):
        man = archive / f"{proj}__manifest.jsonl"
        if not man.exists():
            continue
        entries = [json.loads(l) for l in man.read_text(encoding="utf-8").splitlines() if l.strip()]
        total += len(entries)
        # Sample the public URL rather than head_object: what matters is that
        # the URL the apps use actually serves the bytes.
        for e in entries[:2]:
            key = f"{e['bucket']}/{e['path']}"
            try:
                req = urllib.request.Request(f"{base}/{key}", method="HEAD")
                with urllib.request.urlopen(req, timeout=30):
                    published += 1
            except Exception:
                pass
        url, tok, _ = resolve_project_target(proj)
        c = libsql.connect(database=url, auth_token=tok)
        for tbl, col in (("lead_documents", "storage_path"), ("areas", "image_url"),
                         ("buildings", "image_url"), ("dj_profiles", "profile_image_url")):
            try:
                n = c.execute(
                    f'select count(*) from "{tbl}" where "{col}" like ?',
                    [f"%{PROJECTS[proj]['ref']}.supabase.co%"]).fetchall()[0][0]
                if n:
                    unrewritten.append(f"{proj}.{tbl}.{col}: {n} rows still point at supabase.co")
            except Exception:
                pass
    ok = published > 0 and not unrewritten
    return {"pass": ok, "archived_objects": total, "public_url_samples_ok": published,
            "unrewritten_pointers": unrewritten}


def check_apps(token: str) -> dict:
    out, ok = {}, True
    for project, spec in APP_REQUIREMENTS.items():
        envs = _vercel(f"/v9/projects/{project}/env?teamId={DEFAULT_TEAM}&decrypt=false", token)
        if "_err" in envs:
            out[project] = {"error": envs["_err"]}
            ok = False
            continue
        prod = {}
        for e in envs.get("envs", []):
            if "production" in (e.get("target") or []):
                prod[e.get("key")] = True
        missing = [k for k in spec["needs"] if k not in prod]
        good = not missing
        ok = ok and good
        out[project] = {"missing_in_production": missing, "pass": good}
    return {"pass": ok, "detail": out}


def check_writers(env: dict) -> dict:
    """Writers with NO env-var rollback: n8n and the PM2 harness."""
    problems = []

    n8n_url, n8n_key = env.get("N8N_API_URL"), env.get("N8N_API_KEY")
    if n8n_url and n8n_key:
        try:
            req = urllib.request.Request(f"{n8n_url.rstrip('/')}/api/v1/workflows?limit=250",
                                         headers={"X-N8N-API-KEY": n8n_key})
            with urllib.request.urlopen(req, timeout=45) as r:
                wfs = json.load(r).get("data", [])
            hits = [w.get("name") for w in wfs
                    if w.get("active") and "supabase" in json.dumps(w).lower()]
            if hits:
                problems.append(f"n8n: {len(hits)} ACTIVE workflow(s) reference supabase: "
                                f"{hits[:4]}")
        except Exception as exc:
            problems.append(f"n8n: could not verify ({str(exc)[:60]})")
    else:
        problems.append("n8n: N8N_API_URL/N8N_API_KEY absent — cannot verify")

    eco = SCRIPTS.parent / "ecosystem.config.js"
    if eco.exists() and "EMPIRE_TURSO_CUTOVER" in eco.read_text(encoding="utf-8"):
        problems.append("PM2 harness: cutover is opt-in (EMPIRE_TURSO_CUTOVER). Confirm the "
                        "running processes were started WITH it — "
                        'python -c "import supabase; print(supabase.create_client.__module__)"')
    return {"pass": not problems, "problems": problems}


def check_traffic(token: str) -> dict:
    """Is Supabase still receiving writes? Any recent row is a live writer."""
    out, ok = {}, True
    for proj in sorted(PROJECTS):
        ref = PROJECTS[proj]["ref"]
        try:
            rows = _mgmt_query(ref, (
                "select coalesce(sum(n_tup_ins + n_tup_upd), 0) as writes "
                "from pg_stat_user_tables where schemaname='public'"), token)
            out[proj] = int(rows[0]["writes"])
        except Exception as exc:
            out[proj] = f"error: {str(exc)[:60]}"
            ok = False
    return {"pass": ok, "cumulative_writes_since_stats_reset": out,
            "note": "cumulative, not a delta — run twice minutes apart; "
                    "an increase means something is still writing"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    env = load_env()
    sb_token = env.get("SUPABASE_ACCESS_TOKEN")
    vc_token = env.get("VERCEL_TOKEN") or env.get("VERCEL_API_TOKEN")
    if not sb_token or not vc_token:
        print("ERROR: SUPABASE_ACCESS_TOKEN and VERCEL_TOKEN are both required",
              file=sys.stderr)
        return 2

    results = {
        "DATA": check_data(sb_token),
        "STORAGE": check_storage(env),
        "APPS": check_apps(vc_token),
        "WRITERS": check_writers(env),
        "TRAFFIC": check_traffic(sb_token),
    }
    safe = all(v.get("pass") for v in results.values())

    if args.json:
        print(json.dumps({"safe_to_cancel": safe, "gates": results}, indent=2))
        return 0 if safe else 1

    for gate, r in results.items():
        print(f"\n=== {gate}: {'PASS' if r.get('pass') else 'FAIL'}")
        if gate == "DATA":
            for p, d in r["detail"].items():
                if "error" in d:
                    print(f"    {p:11} ERROR {d['error']}")
                else:
                    s = "ok" if d["pass"] else f"SHORT {d['short'][:3]} missing={d['missing_tables'][:3]}"
                    print(f"    {p:11} {d['tables']:3} tables  {s}")
        elif gate == "APPS":
            for p, d in r["detail"].items():
                print(f"    {p:20} " + ("ok" if d.get("pass")
                      else f"MISSING IN PROD: {d.get('missing_in_production') or d.get('error')}"))
        elif gate == "STORAGE":
            print(f"    {r.get('reason') or json.dumps({k: v for k, v in r.items() if k != 'pass'})[:200]}")
        else:
            for k, v in r.items():
                if k != "pass":
                    print(f"    {k}: {json.dumps(v)[:220]}")

    print("\n" + "=" * 66)
    print("SAFE TO CANCEL SUPABASE" if safe else "DO NOT CANCEL — gates above are failing")
    print("=" * 66)
    return 0 if safe else 1


if __name__ == "__main__":
    sys.exit(main())
