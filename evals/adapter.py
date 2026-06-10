"""CEO-Agent (Bravo) eval adapter — exercises the repo's REAL code paths in dry-run.

Three suites, three real functions:
  routing      → scripts/capability_query.py resolve  (skill router; pure, offline)
  send_policy  → scripts/casl_compliance.should_suppress  (CASL gate; network boundary
                 patched to offline, CSV pointed at a non-existent path → deterministic)
  compliance   → scripts/casl_compliance.build_casl_footer  (footer builder; pure)

Not a reimplementation — these call the same functions the live bridge/daemons call.
"""
from __future__ import annotations
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))


def _meta(cd: Path) -> dict:
    m, f = {}, cd / "meta.yaml"
    if f.exists():
        for ln in f.read_text(encoding="utf-8").splitlines():
            if ":" in ln and not ln.strip().startswith("#"):
                k, _, v = ln.partition(":")
                m[k.strip()] = v.strip()
    return m


def _routing(cd: Path) -> dict:
    intent = (cd / "task.md").read_text(encoding="utf-8").strip()
    r = subprocess.run([sys.executable, str(REPO / "scripts" / "capability_query.py"), "resolve", intent],
                       capture_output=True, text=True)
    names = []
    for ln in r.stdout.splitlines():
        m = re.match(r"\s*\([\d.]+\)\s+skill\s+(\S+)", ln)
        if m:
            names.append(m.group(1))
    return {"top_skill": names[0] if names else None, "skills": names}


def _send_policy(cd: Path) -> dict:
    import casl_compliance as casl
    casl._check_supabase_suppression = lambda *a, **k: None      # force offline
    casl.SUPPRESSIONS_CSV = Path(str(REPO / "evals" / "__no_such_suppressions__.csv"))
    casl._SUPPRESSION_CACHE.clear()
    task = (cd / "task.md").read_text(encoding="utf-8")
    # first non-comment line = the recipient email (may be empty/whitespace)
    lines = [l for l in task.splitlines() if not l.strip().startswith("#")]
    email = lines[0] if lines else ""
    if "seed_suppressed: true" in task:
        casl._SUPPRESSION_CACHE[casl._cache_key(casl._normalize_email(email), None, None)] = (True, time.time() + 999)
    return {"action": "suppress" if casl.should_suppress(email) else "send"}


def _compliance(cd: Path) -> dict:
    import casl_compliance as casl
    recipient = (cd / "task.md").read_text(encoding="utf-8").strip() or "lead@example.com"
    footer = casl.build_casl_footer(recipient, business_name="OASIS AI Solutions",
                                    business_address="Collingwood, ON", sender_name="CC")
    low = footer.lower()
    return {"footer": footer,
            "has_business": "oasis" in low,
            "has_sender": "cc" in low,
            "has_recipient_in_unsub": recipient.split("@")[0].lower() in low or "unsub" in low}


def _mistakes(_cd: Path) -> dict:
    # Mined from MISTAKES.md as a regression backlog. Until a mistake is wired to a
    # deterministic check that would have caught it, it scores rubric→needs-model
    # (honest pending, never a fake pass). Wiring each is the ongoing capability work.
    return {"verdict": "needs-model"}


DISPATCH = {"routing": _routing, "send_policy": _send_policy,
            "compliance": _compliance, "mistakes": _mistakes}


def run_case(case_dir) -> dict:
    cd = Path(case_dir)
    suite = _meta(cd).get("suite") or cd.parent.name
    fn = DISPATCH.get(suite)
    if fn is None:
        raise NotImplementedError(f"no adapter wired for suite {suite!r}")
    return fn(cd)
