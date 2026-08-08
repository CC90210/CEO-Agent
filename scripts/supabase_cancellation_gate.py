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
from lib import turso_switch  # noqa: E402
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

    # Resolve through the ETL rather than re-reading env here. The agents env
    # names these differently from the R2 docs, and the account id, bucket and
    # public URL are all derivable — duplicating that lookup is how this gate
    # came to report "R2 not configured" against a fully provisioned R2.
    from etl_storage_to_r2 import PUBLIC_PREFIXES_DEFAULT, resolve_r2  # noqa: PLC0415

    creds, missing, _notes = resolve_r2(env)
    if missing:
        return {"pass": False, "reason": f"R2 not configured — missing {missing}"}

    s3 = _r2_client(creds)
    archive = SCRIPTS.parent / "state" / "backups" / "supabase_storage"
    base = (creds.get("R2_PUBLIC_BASE_URL") or "").rstrip("/")
    private_bucket = creds["R2_BUCKET"]
    public_bucket = creds["R2_PUBLIC_BUCKET"]

    total = 0
    unrewritten: list[str] = []
    absent: list[str] = []       # object is not in R2 at all
    unserved: list[str] = []     # public object the public URL will not serve
    exposed: list[str] = []      # private object the public URL WILL serve

    # Sample per project and require EVERY sample to hold. An earlier version
    # counted successes across all projects and passed on `published > 0`, so
    # one working object out of 4,118 would have cleared the gate — and it
    # referenced a name that was never assigned, so it raised NameError the
    # moment R2 was configured. The gate that authorises the decision was
    # broken in exactly the situation where it matters.
    SAMPLES = 5
    for proj in sorted(PROJECTS):
        man = archive / f"{proj}__manifest.jsonl"
        if not man.exists():
            continue
        entries = [json.loads(l) for l in man.read_text(encoding="utf-8").splitlines()
                   if l.strip()]
        total += len(entries)
        if not entries:
            continue
        # Spread the samples across the manifest rather than taking the head —
        # the first N objects are often all from one bucket uploaded together.
        step = max(1, len(entries) // SAMPLES)
        for e in entries[::step][:SAMPLES]:
            key = f"{e['bucket']}/{e['path']}"
            is_public = e["bucket"] in PUBLIC_PREFIXES_DEFAULT

            # Every object, public or private, must actually be in R2.
            bucket = public_bucket if is_public else private_bucket
            try:
                s3.head_object(Bucket=bucket, Key=key)
            except Exception as exc:
                absent.append(f"{proj}: {key} not in {bucket} ({str(exc)[:60]})")

            # Public objects must serve; private objects must NOT. Requiring a
            # public URL for everything would demand that 4,088 merchant bank
            # statements be world-readable in order to pass.
            served = _public_head(base, key)
            if is_public and served is not True:
                unserved.append(f"{proj}: {key} -> {served}")
            if not is_public and served is True:
                exposed.append(f"{proj}: {key} IS PUBLICLY READABLE")

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

    ok = not (unrewritten or absent or unserved or exposed)
    return {"pass": ok, "archived_objects": total,
            "private_bucket": private_bucket, "public_bucket": public_bucket,
            "objects_absent_from_r2": absent,
            "public_objects_not_served": unserved,
            "PRIVATE_OBJECTS_EXPOSED": exposed,
            "unrewritten_pointers": unrewritten}


def _r2_client(creds: dict):
    import boto3  # noqa: PLC0415
    from botocore.config import Config  # noqa: PLC0415

    return boto3.client(
        "s3",
        endpoint_url=f"https://{creds['CLOUDFLARE_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=creds["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=creds["R2_SECRET_ACCESS_KEY"],
        config=Config(signature_version="s3v4", retries={"max_attempts": 3}),
        region_name="auto",
    )


def _public_head(base: str, key: str):
    """True if the public URL serves it, else the status/reason. Never raises."""
    if not base:
        return "no public base url"
    try:
        req = urllib.request.Request(f"{base}/{key}", method="HEAD")
        with urllib.request.urlopen(req, timeout=30) as r:
            return True if r.status < 400 else r.status
    except Exception as exc:
        return getattr(exc, "code", None) or str(exc)[:50]


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

    # The Python switch is a sitecustomize.py in site-packages — not in any
    # repo by nature, so "the flag is set" and "the flag does anything" are
    # different facts. It was absent on the VPS entirely, which meant those
    # daemons kept writing to Supabase while the operator believed otherwise.
    # Asking the INTERPRETER is the only honest check.
    status = turso_switch.probe()
    if not status.active:
        problems.append(
            f"Python switch NOT active on this interpreter ({status.detail}). "
            f"Run: python scripts/install_python_switch.py")

    # A process that tried to patch and failed leaves this behind. stderr is
    # discarded under PM2, so without the marker the failure is invisible.
    rec = turso_switch.failure_record()
    if rec:
        problems.append(
            f"Python switch FAILED on {rec.get('host','?')} at "
            f"{rec.get('at','?')}: {str(rec.get('error'))[:90]} — that process "
            f"was still writing to Supabase. Fix, then delete "
            f"{turso_switch.FAILURE_MARKER.name}.")

    eco = SCRIPTS.parent / "ecosystem.config.js"
    if eco.exists() and "EMPIRE_TURSO_CUTOVER" in eco.read_text(encoding="utf-8"):
        problems.append("PM2 harness: cutover is opt-in (EMPIRE_TURSO_CUTOVER). Confirm the "
                        "running processes were started WITH it — "
                        'python -c "import supabase; print(supabase.create_client.__module__)"')

    # Off-machine writers are the ones this gate has been blindest to. The VPS
    # runs SunBiz-Agent plus three daemons that no check here can see, and the
    # traffic gate proves something is still writing without naming where.
    problems.append(
        "VPS: no check here can see it. Confirm the switch is installed there "
        "(python scripts/install_python_switch.py) and its PM2 processes were "
        "restarted with EMPIRE_TURSO_CUTOVER=1, or those daemons keep writing "
        "to a cancelled database.")

    return {"pass": not problems, "problems": problems}


def check_traffic(token: str, window_s: int = 45) -> dict:
    """Is anything STILL WRITING to Supabase? Sampled twice, not just read once.

    The first version read cumulative counters, printed "run this twice minutes
    apart", and returned pass=True regardless of what it saw — a gate that
    cannot fail. It would have reported PASS while n8n was actively inserting.

    Now it takes two samples separated by `window_s` and FAILS on any increase.
    A live writer during the sample window is a writer that will still be there
    the moment the project is deleted.
    """
    import time

    def sample() -> dict:
        out = {}
        for proj in sorted(PROJECTS):
            try:
                rows = _mgmt_query(PROJECTS[proj]["ref"], (
                    "select coalesce(sum(n_tup_ins + n_tup_upd + n_tup_del), 0) as writes "
                    "from pg_stat_user_tables where schemaname='public'"), token)
                out[proj] = int(rows[0]["writes"])
            except Exception as exc:
                out[proj] = f"error: {str(exc)[:60]}"
        return out

    first = sample()
    time.sleep(window_s)
    second = sample()

    deltas, errors = {}, []
    for proj in sorted(PROJECTS):
        a, b = first.get(proj), second.get(proj)
        if not isinstance(a, int) or not isinstance(b, int):
            errors.append(f"{proj}: {a if not isinstance(a, int) else b}")
            continue
        if b > a:
            deltas[proj] = b - a

    return {
        "pass": not deltas and not errors,
        "window_seconds": window_s,
        "still_writing": deltas,
        "errors": errors,
        "note": ("no writes observed during the window"
                 if not deltas else
                 "SOMETHING IS STILL WRITING to these projects — find and move it "
                 "before cancelling, or those writes are lost"),
    }


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
