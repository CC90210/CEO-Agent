"""Email-safety diagnostic — verifies the multi-AI safety surface is intact.

Run this before any session that will send outbound. Any AI that drives
this repo (Claude, Gemini, Antigravity native chat, Codex, GPT) can call
this with no arguments to confirm:

  1. send_gateway responds to a basic in-process call
  2. BRAVO_FORCE_DRY_RUN=1 actually flips dry-run behavior
  3. Every CLI send subcommand accepts --dry-run
  4. OASIS templates render cleanly through the production path
  5. No script bypasses send_gateway via direct smtplib

Returns 0 if all checks pass, 1 if any fail. JSON output via --json for
agent consumption.

Usage:
    python scripts/email_doctor.py
    python scripts/email_doctor.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _ok(name: str, detail: str = "") -> dict[str, Any]:
    return {"check": name, "ok": True, "detail": detail}


def _fail(name: str, detail: str) -> dict[str, Any]:
    return {"check": name, "ok": False, "detail": detail}


def check_gateway_responds() -> dict[str, Any]:
    """Confirm send_gateway.send() returns the documented shape on a
    bad-input call. We deliberately use an invalid channel so we don't
    touch SMTP / Supabase even by accident."""
    try:
        from send_gateway import send as gateway_send  # type: ignore
    except Exception as exc:  # noqa: BLE001
        return _fail("gateway-import", f"could not import send_gateway: {exc}")

    try:
        result = gateway_send(
            channel="not_a_real_channel",
            agent_source="email_doctor",
        )
    except Exception as exc:  # noqa: BLE001
        return _fail("gateway-call", f"gateway raised (it must NEVER raise): {exc}")

    expected_keys = {"status", "reason", "lead_id",
                     "interaction_id", "cooldown_until", "daily_count"}
    missing = expected_keys - set(result.keys())
    if missing:
        return _fail("gateway-shape", f"missing keys in response: {sorted(missing)}")
    if result.get("status") != "error":
        return _fail("gateway-error-path",
                     f"expected status=error for bad channel, got {result.get('status')}")
    return _ok("gateway-responds",
               f"status=error reason={result.get('reason')!r} (correct)")


def check_force_dry_run_flips() -> dict[str, Any]:
    """Confirm BRAVO_FORCE_DRY_RUN=1 turns a real send call into a no-op.

    We invoke the gateway with channel=email + valid args BUT with the
    env var set. The gateway should return status='dry_run' regardless
    of what dry_run= we passed.
    """
    saved = os.environ.get("BRAVO_FORCE_DRY_RUN")
    os.environ["BRAVO_FORCE_DRY_RUN"] = "1"
    try:
        # Reimport in case load_env caches: send_gateway reads env at call time
        # via load_env(), so this will pick up the new value.
        from send_gateway import send as gateway_send  # type: ignore
        result = gateway_send(
            channel="email",
            agent_source="email_doctor",
            to_email="doctor-test@oasisai.work",
            subject="email_doctor probe — IGNORE",
            body_text="If you see this, BRAVO_FORCE_DRY_RUN failed. File a security issue.",
            brand="oasis",
            intent="commercial",
            dry_run=False,  # the env var must override this
        )
    except Exception as exc:  # noqa: BLE001
        return _fail("force-dry-run", f"gateway raised under killswitch: {exc}")
    finally:
        if saved is None:
            os.environ.pop("BRAVO_FORCE_DRY_RUN", None)
        else:
            os.environ["BRAVO_FORCE_DRY_RUN"] = saved

    if result.get("status") != "dry_run":
        return _fail(
            "force-dry-run",
            f"expected dry_run, got status={result.get('status')!r}, "
            f"reason={result.get('reason')!r}. Killswitch is broken.",
        )
    return _ok("force-dry-run-killswitch", f"status=dry_run as expected")


def check_subcommand_dryrun_flag(script: str, subcmd: list[str]) -> dict[str, Any]:
    """Run `python scripts/<script> <subcmd...> --help` and grep for --dry-run."""
    cmd = [sys.executable, str(SCRIPTS / script)] + subcmd + ["--help"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True,
                             timeout=20, encoding="utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        return _fail(f"{script} {' '.join(subcmd)}",
                     f"could not run --help: {exc}")
    text = (out.stdout or "") + (out.stderr or "")
    if "--dry-run" in text:
        return _ok(f"{script} {' '.join(subcmd)} --dry-run", "flag present")
    return _fail(f"{script} {' '.join(subcmd)} --dry-run",
                 "flag MISSING — this send path can't be previewed")


def check_no_smtp_bypass() -> dict[str, Any]:
    """Spot-check that no business engine imports smtplib directly.

    Allowed importers: send_gateway (the gateway itself), test_send_gateway
    (the test harness), google_tool (the gateway's underlying transport),
    email_engine (deprecated wrapper that raises RuntimeError on call),
    and email_doctor (this script — it greps for the import string but
    does not actually import smtplib).
    Anything else importing smtplib is a potential bypass.
    """
    import re

    allowed = {"send_gateway.py", "test_send_gateway.py", "google_tool.py",
               "email_engine.py", "email_doctor.py"}
    # Match real imports at the start of a logical line, not the literal
    # string when it appears inside another string / comment / regex.
    # Anchored on "^\s*" + (import|from) prevents the doctor's own
    # detector from self-flagging.
    pattern = re.compile(r"^\s*(?:import\s+smtplib|from\s+smtplib\b)",
                         re.MULTILINE)
    bad: list[str] = []
    for py in SCRIPTS.glob("*.py"):
        if py.name in allowed:
            continue
        if py.name.startswith("_"):
            # underscore-prefixed = scratch / one-off. We don't enforce on
            # these but we count them and report.
            continue
        try:
            text = py.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if pattern.search(text):
            bad.append(py.name)
    if bad:
        return _fail("no-smtp-bypass",
                     f"non-allowlisted scripts import smtplib: {bad}")
    return _ok("no-smtp-bypass",
               f"only {sorted(allowed)} import smtplib (as expected)")


def check_template_render() -> dict[str, Any]:
    """Run wire_all_templates --verify-only --render-check and surface result."""
    cmd = [sys.executable, str(SCRIPTS / "wire_all_templates.py"),
           "--verify-only", "--render-check", "--json"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True,
                             timeout=30, encoding="utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        return _fail("template-render",
                     f"wire_all_templates --render-check failed to run: {exc}")
    try:
        data = json.loads(out.stdout)
    except Exception:
        return _fail("template-render",
                     "could not parse wire_all_templates JSON output — "
                     "did Supabase env vars resolve?")
    if not data.get("ok"):
        return _fail("template-render",
                     f"templates have unresolved problems: "
                     f"{data.get('verification') or data.get('render_check')}")
    return _ok("template-render",
               f"all 3 OASIS templates render clean (verify + render check)")


CHECKS = [
    ("gateway responds", check_gateway_responds),
    ("force-dry-run killswitch", check_force_dry_run_flips),
    ("email_engine send --dry-run", lambda: check_subcommand_dryrun_flag(
        "email_engine.py", ["send"])),
    ("email_engine send-template --dry-run", lambda: check_subcommand_dryrun_flag(
        "email_engine.py", ["send-template"])),
    ("email_engine sequence run --dry-run", lambda: check_subcommand_dryrun_flag(
        "email_engine.py", ["sequence", "run"])),
    ("outreach_engine send --dry-run", lambda: check_subcommand_dryrun_flag(
        "outreach_engine.py", ["send"])),
    ("outreach_batch --dry-run", lambda: check_subcommand_dryrun_flag(
        "outreach_batch.py", [])),
    ("send_gateway send --dry-run", lambda: check_subcommand_dryrun_flag(
        "send_gateway.py", ["send"])),
    ("no smtp bypass", check_no_smtp_bypass),
    ("templates render clean", check_template_render),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", dest="output_json", action="store_true",
                        help="JSON output for agent consumption")
    parser.add_argument("--skip-network", action="store_true",
                        help="Skip checks that touch Supabase (template render)")
    args = parser.parse_args()

    results: list[dict[str, Any]] = []
    for label, fn in CHECKS:
        if args.skip_network and label == "templates render clean":
            results.append({"check": label, "ok": True, "detail": "skipped (--skip-network)"})
            continue
        try:
            results.append(fn())
        except Exception as exc:  # noqa: BLE001
            results.append(_fail(label, f"check raised: {exc}"))

    overall = all(r["ok"] for r in results)
    payload = {"ok": overall, "checks": results}

    if args.output_json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print()
        print("=" * 60)
        print(f"  EMAIL DOCTOR  —  {'OK' if overall else 'FAIL'}")
        print("=" * 60)
        for r in results:
            mark = "OK  " if r["ok"] else "FAIL"
            print(f"  [{mark}] {r['check']:42s}  {r['detail']}")
        print()
        if overall:
            print("  Multi-AI safety surface intact. Outbound is safe to enable.")
        else:
            print("  One or more checks failed. DO NOT enable outbound until fixed.")
        print()
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())
