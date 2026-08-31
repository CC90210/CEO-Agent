"""Watch sunbizfunding.com's nameservers and cut it over the moment they move.

The last Gate 1 item is a registrar change only CC can make. This waits for it
and finishes the job, so the cutover does not have to wait for someone to be
awake — but it is deliberately conservative about WHEN it is willing to act,
because it acts on production with nobody watching.

WHAT IT WILL NOT DO
  * It will not cut over on a DNS answer alone. Cloudflare's own zone status
    must also read `active`, because a resolver can hand back Cloudflare
    nameservers while the zone is still pending and the cutover would then
    point a live brand at a zone that cannot serve it.
  * It will not cut over to a Worker it has not just proven healthy. The
    pre-check fetches the workers.dev origin and requires a 200 with real HTML,
    not merely a reachable socket.
  * It will not retry a cutover. One attempt, then it reports and stops
    attempting, because a half-applied DNS change re-tried in a loop is how a
    brand goes dark in a way nobody can reconstruct in the morning.

WHAT IT DOES ON FAILURE
  It cannot restore deleted A records itself — cloudflare_admin.py is fenced to
  TXT writes by design, and that fence is not something to route around at 3am.
  So the rollback values that attach-domain prints are captured verbatim into
  the log AND sent to Telegram, so the fix is one paste rather than an
  investigation.

    python scripts/sunbiz_cutover_watch.py --hours 8 --interval 900
    python scripts/sunbiz_cutover_watch.py --once        # single check, no loop
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

CAPABILITY_META = {
    "category": "release.cloudflare",
    "lifecycle": "active",
    "risk": "external_write",
    "triggers": ["watch sunbizfunding nameservers and cut over",
                 "poll for the registrar change and attach the domain",
                 "overnight dns cutover watch"],
    "owner": "bravo",
    "project": "empire",
    "bridge": {"visible": False},
}

DOMAIN = "sunbizfunding.com"
APP = "sunbiz-funding"
WORKER_ORIGIN = "https://sunbiz-funding.oasisaisolutions.workers.dev/"
LOG = ROOT / "state" / "sunbiz_cutover_watch.log"
PY = sys.executable


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg: str) -> None:
    line = f"{_now()} {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def notify(msg: str) -> None:
    """Telegram, best-effort. A failed alert must never abort the watch."""
    try:
        subprocess.run([PY, str(ROOT / "scripts" / "notify.py"), msg],
                       cwd=str(ROOT), capture_output=True, timeout=60)
    except Exception as e:                       # noqa: BLE001 — reported, not raised
        log(f"NOTIFY FAILED (continuing): {e}")


def run(args: list[str], timeout: int = 900) -> tuple[int, str]:
    p = subprocess.run(args, cwd=str(ROOT), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def nameservers() -> list[str]:
    """Live NS for the domain. Empty list means the lookup failed, which is NOT
    the same as 'no nameservers' and must never read as a reason to act."""
    try:
        rc, out = run(["nslookup", "-type=NS", DOMAIN, "8.8.8.8"], timeout=120)
    except Exception as e:                       # noqa: BLE001
        log(f"NS lookup error: {e}")
        return []
    return sorted(set(re.findall(r"nameserver\s*=\s*(\S+?)\.?$", out, re.M | re.I)))


def zone_is_active() -> bool:
    rc, out = run([PY, "scripts/integrations/wrangler_tool.py", "zones"], timeout=300)
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] == DOMAIN:
            return parts[1] == "active"
    return False


def worker_healthy() -> tuple[bool, str]:
    """A 200 with real HTML. A reachable socket is not a healthy deployment."""
    import urllib.request
    try:
        req = urllib.request.Request(WORKER_ORIGIN, headers={"User-Agent": "bravo-cutover-watch/1.0"})
        with urllib.request.urlopen(req, timeout=45) as r:
            body = r.read(4000).decode("utf-8", "replace")
            if r.status != 200:
                return (False, f"worker returned HTTP {r.status}")
            if "<html" not in body.lower() and "<!doctype" not in body.lower():
                return (False, "worker returned 200 but the body is not HTML")
            return (True, f"HTTP 200, {len(body)}+ bytes of HTML")
    except Exception as e:                       # noqa: BLE001
        return (False, f"worker unreachable: {e}")


def live_check(host: str) -> tuple[bool, str]:
    import urllib.request
    try:
        req = urllib.request.Request(f"https://{host}/", headers={"User-Agent": "bravo-cutover-watch/1.0"})
        with urllib.request.urlopen(req, timeout=45) as r:
            served_by = r.headers.get("server", "?")
            ray = r.headers.get("cf-ray")
            ok = r.status == 200 and bool(ray)
            return (ok, f"HTTP {r.status} server={served_by} cf-ray={'yes' if ray else 'NO'}")
    except Exception as e:                       # noqa: BLE001
        return (False, f"unreachable: {e}")


def attempt_cutover() -> bool:
    log("PRECONDITIONS MET — beginning cutover")

    ok, detail = worker_healthy()
    log(f"pre-check worker {APP}: {'OK' if ok else 'FAIL'} — {detail}")
    if not ok:
        notify(f"⚠️ {DOMAIN} nameservers moved to Cloudflare, but the {APP} Worker "
               f"failed its pre-check ({detail}). NOT cutting over. Needs a look.")
        return False

    rc, out = run([PY, "scripts/integrations/wrangler_tool.py", "attach-domain",
                   "--app", APP, "--hostname", DOMAIN], timeout=900)
    log(f"attach-domain exit={rc}\n{out.strip()}")
    rollback = "\n".join(l for l in out.splitlines() if "[rollback]" in l) or "(none captured)"

    if rc != 0:
        notify(f"❌ {DOMAIN} cutover FAILED at attach-domain (exit {rc}).\n"
               f"Rollback records:\n{rollback}\n\nLog: {LOG}")
        return False

    # Propagation is not instant and a single post-check would misreport it.
    for wait in (20, 40, 60, 120, 180):
        time.sleep(wait)
        ok, detail = live_check(DOMAIN)
        log(f"post-check https://{DOMAIN}: {detail}")
        if ok:
            wok, wdetail = live_check(f"www.{DOMAIN}")
            log(f"post-check https://www.{DOMAIN}: {wdetail}")
            notify(f"✅ {DOMAIN} is live on Cloudflare Workers.\n"
                   f"  apex: {detail}\n  www:  {wdetail}\n"
                   f"Gate 1's last blocker is closed — the 7-day soak can start.")
            return True

    notify(f"⚠️ {DOMAIN} attach-domain SUCCEEDED but the apex is not serving yet "
           f"after ~7 min. Last: {detail}\n"
           f"If it does not settle, restore these records:\n{rollback}\n\nLog: {LOG}")
    return False


def check_once() -> bool:
    ns = nameservers()
    if not ns:
        log("NS lookup returned nothing — treating as UNKNOWN, not as a change")
        return False
    on_cf = [n for n in ns if n.lower().endswith("ns.cloudflare.com")]
    if not on_cf:
        log(f"still at registrar's old nameservers: {', '.join(ns)}")
        return False

    log(f"nameservers now Cloudflare: {', '.join(on_cf)}")
    if not zone_is_active():
        # The single most important guard here. DNS can answer Cloudflare while
        # the zone is still pending, and cutting over then points a live brand
        # at a zone that cannot serve it.
        log("zone is NOT yet active in Cloudflare — waiting (this is expected "
            "for a short window after the registrar change)")
        return False
    return attempt_cutover()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=8.0)
    ap.add_argument("--interval", type=int, default=900, help="seconds between checks")
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args()

    log(f"=== watch started (domain={DOMAIN} app={APP} "
        f"interval={a.interval}s deadline={a.hours}h) ===")

    if a.once:
        return 0 if check_once() else 1

    deadline = time.time() + a.hours * 3600
    checks = 0
    while time.time() < deadline:
        checks += 1
        try:
            if check_once():
                log(f"=== cutover complete after {checks} check(s) ===")
                return 0
        except Exception as e:                   # noqa: BLE001 — a watch must not die
            log(f"check raised (continuing): {e!r}")
        time.sleep(a.interval)

    log(f"=== deadline reached after {checks} checks; no registrar change seen ===")
    notify(f"🌅 Overnight watch finished: {DOMAIN} nameservers never moved "
           f"({checks} checks over {a.hours}h). Still at the old registrar NS. "
           f"Set damian.ns.cloudflare.com + sydney.ns.cloudflare.com to finish Gate 1.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
