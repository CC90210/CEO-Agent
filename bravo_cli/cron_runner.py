"""cron_runner.py — bridge-side cron poller for Phase I of giggly-reef.

The bridge calls poll_once() on every ping cycle. It:
  1. GETs /api/cron-jobs/poll with the bridge token. Returns the operator's
     enabled jobs for this tenant.
  2. For each job, evaluates its 5-field cron expression against the
     operator's local clock + the row's last_run_at. If due, fires the
     job's action.
  3. POSTs the result back to /api/cron-jobs/poll so the dashboard sees
     last_run_status / last_run_output / last_run_error / run_count.

The bridge owns execution. Dashboard only stores the spec. That separation
means cron jobs survive operator-machine reboots (dashboard persists),
keep working in air-gapped environments after the bridge boots (no need
to reach Vercel for the SPEC at tick time — only for the report-back),
and don't require Vercel-side workers (which would cost $$).

Action types (matching /api/cron-jobs/route.ts:VALID_ACTION_TYPES):

  script_run    — Run scripts/<X>.py with optional --json + args
                  via bravo_cli.bridge_tools._run_script.
  snapshot_run  — Shortcut for scripts/snapshots/<X>.py (same path, just
                  prefixed for clarity in the operator UI).
  agent_prompt  — Fire-and-forget chat turn against the agent_key with
                  the given prompt. Uses /api/chat with the bridge token.
                  (NOT implemented in v1 — needs a separate bridge-authed
                  chat path. Documented as future work.)
  webhook_post  — POST JSON body to a URL. Use for n8n triggers etc.

Cron evaluation: standard 5-field cron syntax (m h dom mon dow). No
extensions (L/W/#/named months). Time zone: operator-machine local
(matches what `cron` would do on Linux). last_run_at gates re-firing
within the same minute so two ticks within the polling cadence don't
double-fire.
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import requests

# CREATE_NO_WINDOW on Windows — prevents a console flicker every time the
# bridge-ping loop fires a cron job's script. capture_output=True alone is
# NOT enough: it redirects stdio AFTER process creation, but Windows still
# allocates a console window at CreateProcess() time unless this flag is
# passed. Setting it to 0 on non-Windows so the same call works portably.
_WINDOWLESS = 0x08000000 if sys.platform == "win32" else 0
from pathlib import Path
from typing import Any


# ─────────────────────────────────────────────────────────────────────
# Cron expression evaluation
# ─────────────────────────────────────────────────────────────────────


def _parse_cron_field(field: str, lo: int, hi: int) -> set[int]:
    """Expand a single cron field into the set of matching integer values."""
    if field == "*":
        return set(range(lo, hi + 1))
    out: set[int] = set()
    for part in field.split(","):
        step = 1
        if "/" in part:
            base, step_s = part.split("/", 1)
            step = int(step_s)
            if base == "*":
                base = f"{lo}-{hi}"
        else:
            base = part
        if "-" in base:
            a_s, b_s = base.split("-", 1)
            a, b = int(a_s), int(b_s)
            for v in range(a, b + 1, step):
                out.add(v)
        else:
            out.add(int(base))
    return out


def _cron_matches(expr: str, dt: datetime) -> bool:
    """True iff the cron expression matches the given local-time datetime
    (minute resolution). Mirrors standard cron: m h dom mon dow."""
    try:
        parts = expr.strip().split()
        if len(parts) != 5:
            return False
        m_set = _parse_cron_field(parts[0], 0, 59)
        h_set = _parse_cron_field(parts[1], 0, 23)
        dom_set = _parse_cron_field(parts[2], 1, 31)
        mon_set = _parse_cron_field(parts[3], 1, 12)
        # cron dow is 0-6 with 0=Sunday; Python weekday() is 0-6 with 0=Monday.
        # Convert: cron_dow = (python_weekday + 1) % 7.
        dow_set = _parse_cron_field(parts[4], 0, 7)
        # cron historically also accepts 7 for Sunday — normalize.
        if 7 in dow_set:
            dow_set.add(0)

        if dt.minute not in m_set: return False
        if dt.hour not in h_set: return False
        if dt.month not in mon_set: return False
        # cron semantic: if both dom and dow are restricted (neither is *),
        # the job runs when EITHER matches. If only one is restricted, only
        # that one matters. Implement by checking the original field.
        dom_restricted = parts[2] != "*"
        dow_restricted = parts[4] != "*"
        cron_dow = (dt.weekday() + 1) % 7
        if dom_restricted and dow_restricted:
            return dt.day in dom_set or cron_dow in dow_set
        if dom_restricted:
            return dt.day in dom_set
        if dow_restricted:
            return cron_dow in dow_set
        return True
    except (ValueError, IndexError):
        return False


# ─────────────────────────────────────────────────────────────────────
# Action execution
# ─────────────────────────────────────────────────────────────────────


# Maps tenant_cron_jobs.agent_key → the sibling-repo slug its scripts
# live in. Without this fallback, a row with agent_key="solara" would
# default to bravo even though Solara's scripts live in SunBiz-Agent.
SIBLING_ROOT_BY_AGENT_KEY: dict[str, str] = {
    "bravo": "bravo",
    "atlas": "atlas",
    "maven": "maven",
    "aura": "aura",
    "solara": "sunbiz",
    "helios": "sunbiz",
    "sunbiz": "sunbiz",
}


def _bravo_root() -> Path:
    """Same resolution as bridge_tools._bravo_root — keep them in sync if
    the rule changes. Falls back to bridge cwd when agent_roots is missing."""
    return _resolve_agent_root("bravo") or Path.cwd()


def _resolve_agent_root(slug: str) -> Path | None:
    """Generic sibling-root resolver. Returns None if the slug isn't
    registered in agent_roots.DEFAULTS or no candidate path exists.
    Callers that need a guaranteed Path should fall back to cwd."""
    try:
        try:
            from .agent_roots import resolve_root  # type: ignore
        except ImportError:
            from agent_roots import resolve_root  # type: ignore
        p = resolve_root(slug)
        return Path(p) if p else None
    except Exception:
        return None


def _exec_script_run(payload: dict, job: dict | None = None) -> dict:
    """Run scripts/<X>.py with args, capture stdout/stderr/exit_code. 5-min
    hard timeout — cron jobs that exceed this are misconfigured.

    Root resolution order:
      1. explicit action_payload.root
      2. job.agent_key mapped through SIBLING_ROOT_BY_AGENT_KEY
      3. default "bravo"
    """
    script = str(payload.get("script") or "").strip()
    if not script:
        return {"status": "error", "error": "missing script in action_payload"}
    if ".." in script or script.startswith("/") or script.startswith("\\"):
        return {"status": "error", "error": f"script path forbidden: {script}"}
    if not script.endswith(".py"):
        script = script + ".py"
    # tenant_cron_jobs.action_payload.script entries are written by the
    # dashboard ("scripts/pulse_publish.py") AND by older seed scripts
    # ("pulse_publish.py" — implicit scripts/ prefix). Accept both shapes
    # by stripping a leading scripts/ once before joining; otherwise the
    # path becomes bravo/scripts/scripts/pulse_publish.py and the cron
    # ERRORs every tick. Forbids absolute / traversal earlier so this
    # is just a normalisation.
    if script.startswith("scripts/"):
        script = script[len("scripts/"):]
    elif script.startswith("scripts\\"):
        script = script[len("scripts\\"):]
    args = payload.get("args") or []
    if not isinstance(args, list):
        return {"status": "error", "error": "args must be a list"}

    explicit_root = payload.get("root")
    if explicit_root:
        root_slug = str(explicit_root).strip().lower()
    elif job is not None:
        agent_key = str(job.get("agent_key") or "").strip().lower()
        root_slug = SIBLING_ROOT_BY_AGENT_KEY.get(agent_key, "bravo")
    else:
        root_slug = "bravo"
    if root_slug == "bravo":
        repo_root = _bravo_root()
    else:
        resolved = _resolve_agent_root(root_slug)
        if resolved is None:
            return {
                "status": "error",
                "error": f"unknown or unresolvable root: {root_slug!r} "
                         f"(register it in bravo_cli/agent_roots.py DEFAULTS "
                         f"or set BRAVO_AGENT_ROOT_{root_slug.upper()})",
            }
        repo_root = resolved

    script_path = repo_root / "scripts" / script
    if not script_path.is_file():
        return {"status": "error", "error": f"script not found: {root_slug}:scripts/{script}"}
    try:
        proc = subprocess.run(
            [sys.executable, str(script_path), *[str(a) for a in args]],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
            creationflags=_WINDOWLESS,
        )
    except subprocess.TimeoutExpired as e:
        return {
            "status": "error",
            "error": f"timeout after 300s (cron jobs should be quick — split into chunks if needed)",
            "output": (e.stdout or "")[:4000],
        }
    except OSError as e:
        return {"status": "error", "error": f"spawn_failed: {e}"}
    if proc.returncode != 0:
        return {
            "status": "error",
            "error": f"exit_code={proc.returncode}",
            "output": f"{proc.stdout}\n--- stderr ---\n{proc.stderr}"[:4000],
        }
    return {
        "status": "success",
        "output": proc.stdout[:4000] if proc.stdout else "(no output)",
    }


def _exec_snapshot_run(payload: dict, job: dict | None = None) -> dict:
    """Shortcut for scripts/snapshots/<X>.py — same as script_run with a
    fixed prefix. Operator UI uses this as a separate action type because
    snapshots have well-known semantics (briefing, leads, etc.).

    Forwards payload.root + the parent job so sibling-root resolution
    works for snapshot_run too."""
    snap = str(payload.get("snapshot") or "").strip()
    if not snap:
        return {"status": "error", "error": "missing snapshot in action_payload"}
    if not snap.endswith(".py"):
        snap = snap + ".py"
    forwarded: dict[str, object] = {
        "script": f"snapshots/{snap}",
        "args": payload.get("args") or [],
    }
    if payload.get("root") is not None:
        forwarded["root"] = payload["root"]
    return _exec_script_run(forwarded, job=job)


def _is_private_ipv4(ip: str) -> bool:
    """RFC-1918 + loopback + link-local + 0/8 + AWS/GCP metadata.
    Hostname → ip resolution check; partner to the API-side
    classifyUrlForSsrf which only sees the literal hostname.

    Range list MUST stay in sync with
    oasis-command-center/lib/url-safety.ts (classifyUrlForSsrf). A
    one-sided update creates an attack window through whichever
    check the attacker bypasses."""
    if ip in {"169.254.169.254", "127.0.0.1", "0.0.0.0", "::1"}:
        return True
    parts = ip.split(".")
    if len(parts) != 4:
        # IPv6 unique-local / link-local
        return ip.lower().startswith(("fc", "fd", "fe80", "fe81", "fe82",
                                       "fe83", "fe84", "fe85", "fe86", "fe87",
                                       "fe88", "fe89", "fe8a", "fe8b", "fe8c",
                                       "fe8d", "fe8e", "fe8f", "fe9",
                                       "fea", "feb"))
    try:
        a, b = int(parts[0]), int(parts[1])
    except ValueError:
        return False
    if a == 10: return True
    if a == 127: return True
    if a == 0: return True
    if a == 169 and b == 254: return True
    if a == 172 and 16 <= b <= 31: return True
    if a == 192 and b == 168: return True
    return False


def _check_resolved_addresses_safe(host: str) -> str | None:
    """Resolve the hostname and verify every returned address is on
    the public internet. Closes the DNS-rebinding gap left by the
    API-side hostname-only check: an attacker could submit a webhook
    whose DNS A record points at 1.2.3.4 at submission time and
    flips to 169.254.169.254 at request time. Returns an error string
    if any resolved address is private; None when all are public."""
    import socket
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        return f"dns resolution failed: {exc}"
    for info in infos:
        addr = info[4][0]
        if _is_private_ipv4(addr):
            return f"url resolves to private/internal address: {addr}"
    return None


def _exec_webhook_post(payload: dict) -> dict:
    """POST JSON to a URL. Useful for triggering n8n workflows, Zapier
    catches, Make scenarios — anything that exposes a webhook entry."""
    # Dry-run killswitch — webhook_post is direct outbound HTTP, so it must
    # honour BRAVO_FORCE_DRY_RUN the same way send_gateway does
    # (send_gateway.py ~1918). Without this gate a cron webhook fires a real
    # request even with the killswitch engaged.
    import os
    if str(os.environ.get("BRAVO_FORCE_DRY_RUN", "")).strip().lower() in ("1", "true", "yes", "on"):
        return {
            "status": "dry_run",
            "reason": "BRAVO_FORCE_DRY_RUN=1 — killswitch engaged, webhook_post suppressed, no HTTP sent",
            "output": f"[dry_run] would POST to {str(payload.get('url') or '').strip()}",
        }
    url = str(payload.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        return {"status": "error", "error": f"url must be http/https: {url}"}
    # Resolve + verify NO private/metadata addresses returned. The
    # dashboard classifyUrlForSsrf already caught literal-IP attacks
    # at submission time; this catches DNS-rebinding at request time.
    try:
        host = urllib.parse.urlparse(url).hostname or ""
    except Exception:
        host = ""
    if host:
        ssrf = _check_resolved_addresses_safe(host)
        if ssrf:
            return {"status": "error", "error": f"webhook_post {ssrf}"}
    body = payload.get("body") if isinstance(payload.get("body"), (dict, list)) else {}
    try:
        req = urllib.request.Request(
            url,
            method="POST",
            data=json.dumps(body).encode("utf-8"),
            headers={"content-type": "application/json", "user-agent": "oasis-cron/1.0"},
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            status_code = r.status
            preview = r.read(2000).decode("utf-8", errors="replace")
        return {
            "status": "success" if 200 <= status_code < 300 else "error",
            "output": f"HTTP {status_code}\n{preview}",
        }
    except urllib.error.HTTPError as e:
        return {"status": "error", "error": f"http_{e.code}: {e.reason}"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _exec_agent_prompt(payload: dict) -> dict:
    """v1 stub. Firing a chat turn from the bridge would require a separate
    bridge-authed chat path (today /api/chat is session-cookie gated, and
    chat is interactive — not a fire-and-forget surface). Documented as
    future work; for now log + report a clean error so the operator sees
    why their scheduled prompt didn't run."""
    prompt = str(payload.get("prompt") or "").trim() if hasattr(str, "trim") else str(payload.get("prompt") or "").strip()
    return {
        "status": "error",
        "error": "agent_prompt not yet supported in cron v1 — runs from chat only. Use script_run for a Python equivalent.",
        "output": f"would have run: {prompt[:200]}",
    }


_DISPATCHERS = {
    "script_run": _exec_script_run,
    "snapshot_run": _exec_snapshot_run,
    "webhook_post": _exec_webhook_post,
    "agent_prompt": _exec_agent_prompt,
}


# ─────────────────────────────────────────────────────────────────────
# Polling loop entry point
# ─────────────────────────────────────────────────────────────────────


# Module-level HTTP session — reuses TCP/TLS connections across poll cycles
# AND across local_bridge's ping loop. Both run in the same process and
# both target the same dashboard Vercel URL, so a single shared urllib3
# pool keeps one warm connection instead of two. urllib.request opens a
# fresh socket per call; on a 60s combined ping+poll cadence that's
# ~2 TLS handshakes/min (~100-200ms each) we never pay. Pool size of 4
# covers GET+POST overlap during a single tick.
DASHBOARD_HTTP = requests.Session()
DASHBOARD_HTTP.headers.update({"user-agent": "oasis-cron/1.0"})
_ADAPTER = requests.adapters.HTTPAdapter(pool_connections=2, pool_maxsize=4)
DASHBOARD_HTTP.mount("https://", _ADAPTER)
DASHBOARD_HTTP.mount("http://", _ADAPTER)


def _http_get_json(url: str, token: str) -> dict | None:
    try:
        r = DASHBOARD_HTTP.get(
            url,
            headers={"authorization": f"Bearer {token}"},
            timeout=15,
        )
        if not (200 <= r.status_code < 300):
            return None
        return r.json()
    except Exception:
        return None


def _http_post_json(url: str, token: str, body: dict) -> bool:
    try:
        r = DASHBOARD_HTTP.post(
            url,
            headers={
                "content-type": "application/json",
                "authorization": f"Bearer {token}",
            },
            data=json.dumps(body).encode("utf-8"),
            timeout=15,
        )
        return 200 <= r.status_code < 300
    except Exception:
        return False


#: Last minute poll_once evaluated, so a pass can tell which minutes went by
#: since the previous one. None until the first pass of this process.
_LAST_EVAL_MINUTE: datetime | None = None

#: Ceiling on how far back one pass will catch up. A restart or a suspended
#: laptop must not replay hours of schedule; anything older than this is
#: genuinely missed and stays missed.
_MAX_CATCHUP_MINUTES = 10


def _minutes_to_evaluate(now_local: datetime) -> list[datetime]:
    """The minutes this pass is responsible for: everything after the previous
    pass, up to and including now.

    The ping loop sleeps a flat 60s AFTER running due jobs, so its period is
    60s + however long the work took. Any job that runs for more than a moment
    therefore pushes the next poll past the next minute boundary, and a
    schedule that matches only one minute — `30 6 * * *`, or `*/15` — is
    stepped over entirely. That is not hypothetical: with the shop-out sender
    resumed the cycle reached ~108s and ~half of all scheduled slots were
    being skipped.

    Returning the skipped minutes lets a job that was due during the gap still
    fire. Callers must fire a matching job ONCE per pass regardless of how many
    of these minutes it matches, so `* * * * *` still means "once a cycle" and
    never multiplies.
    """
    global _LAST_EVAL_MINUTE
    this_minute = now_local.replace(second=0, microsecond=0)
    previous, _LAST_EVAL_MINUTE = _LAST_EVAL_MINUTE, this_minute
    # First pass of the process, or a clock that moved backwards: evaluate the
    # current minute only. Never replay history at startup.
    if previous is None or previous >= this_minute:
        return [this_minute]
    gap = int((this_minute - previous).total_seconds() // 60)
    span = min(gap, _MAX_CATCHUP_MINUTES)
    return [this_minute - timedelta(minutes=offset) for offset in range(span - 1, -1, -1)]


def poll_once(token: str, dashboard_url: str) -> int:
    """One pass: fetch jobs → check due → execute → report. Returns the
    number of jobs that actually fired. Called from local_bridge.run_loop()
    after every successful ping."""
    poll_url = f"{dashboard_url.rstrip('/')}/api/cron-jobs/poll"
    payload = _http_get_json(poll_url, token)
    if not payload or not payload.get("ok"):
        return 0
    jobs: list[dict[str, Any]] = payload.get("jobs") or []
    if not jobs:
        return 0

    now_local = datetime.now()
    # Use UTC for last_run_at comparisons since the dashboard stores UTC.
    now_utc = datetime.now(timezone.utc)
    # Every minute this pass owns — the current one plus any the previous pass
    # ran long enough to step over. `any()` below keeps it to one fire per job
    # per pass no matter how many of those minutes it matches.
    due_minutes = _minutes_to_evaluate(now_local)
    ran = 0
    for job in jobs:
        schedule = str(job.get("schedule") or "").strip()
        if not any(_cron_matches(schedule, minute) for minute in due_minutes):
            continue
        # Debounce: if we already fired in the same minute, skip. The bridge
        # ping cadence (60s) means we could fire twice for a job whose
        # minute matches across two consecutive ping cycles. Compare the
        # minute portion of last_run_at vs now.
        last_run_raw = job.get("last_run_at")
        if last_run_raw:
            try:
                last = datetime.fromisoformat(str(last_run_raw).replace("Z", "+00:00"))
                if last.year == now_utc.year and last.month == now_utc.month \
                   and last.day == now_utc.day and last.hour == now_utc.hour \
                   and last.minute == now_utc.minute:
                    continue
            except ValueError:
                pass

        action_type = str(job.get("action_type") or "")
        dispatcher = _DISPATCHERS.get(action_type)
        if not dispatcher:
            outcome = {"status": "error", "error": f"unknown action_type: {action_type}"}
        else:
            try:
                # script_run / snapshot_run consume agent_key for the
                # sibling-root fallback; webhook_post / agent_prompt
                # don't accept job=... and raise TypeError below.
                outcome = dispatcher(job.get("action_payload") or {}, job=job)
            except TypeError:
                outcome = dispatcher(job.get("action_payload") or {})
            except Exception as e:
                outcome = {"status": "error", "error": f"{type(e).__name__}: {e}"}

        # Report back. Failures here just log; the bridge keeps going.
        _http_post_json(
            poll_url,
            token,
            {
                "job_id": job.get("id"),
                "status": outcome.get("status", "error"),
                "output": outcome.get("output"),
                "error": outcome.get("error"),
            },
        )
        ran += 1
    return ran
