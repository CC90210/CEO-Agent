#!/usr/bin/env python3
"""Install the Turso data-backend switch into the active venv.

WHY THIS EXISTS
    The switch is a `sitecustomize.py`, because that is the only module Python
    imports before harness code can bind `create_client`. site-packages is
    therefore where it has to LIVE — but that directory is not in any repo, so
    the file existed on exactly one machine, in no git history, and the VPS
    never had it. Setting EMPIRE_DATA_BACKEND=turso_cloud there did nothing,
    silently, and those daemons kept writing to the database we are trying to
    cancel.

    The tracked source is scripts/_bootstrap/sitecustomize.py. This copies it
    into whichever interpreter is running this script, so provisioning a rig or
    a VPS is one command on either platform.

    python scripts/install_python_switch.py            # install / update
    python scripts/install_python_switch.py --check    # report only, exit 1 if stale
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import site
import sys
import sysconfig
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SOURCE = REPO / "scripts" / "_bootstrap" / "sitecustomize.py"


def _site_packages() -> Path | None:
    """Where this interpreter would import sitecustomize from.

    sysconfig knows the layout for the platform we are actually on, which is
    the whole point — hardcoding Lib/site-packages is what made the previous
    arrangement Windows-only.
    """
    purelib = sysconfig.get_paths().get("purelib")
    if purelib and Path(purelib).is_dir():
        return Path(purelib)
    for cand in (site.getsitepackages() if hasattr(site, "getsitepackages") else []):
        if Path(cand).is_dir():
            return Path(cand)
    return None


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="report only; exit 1 if missing or out of date")
    args = ap.parse_args()

    if not SOURCE.exists():
        print(f"ERROR: tracked source missing: {SOURCE}", file=sys.stderr)
        return 2

    sp = _site_packages()
    if sp is None:
        print("ERROR: could not determine site-packages for this interpreter",
              file=sys.stderr)
        return 2
    target = sp / "sitecustomize.py"

    print(f"interpreter : {sys.executable}")
    print(f"site-packages: {sp}")
    print(f"source      : {SOURCE.relative_to(REPO)}")

    want = _sha(SOURCE)
    if target.exists():
        have = _sha(target)
        if have == want:
            print("status      : up to date")
            return 0
        print(f"status      : STALE (installed {have[:12]}, source {want[:12]})")
    else:
        print("status      : NOT INSTALLED — this interpreter has no switch, so "
              "EMPIRE_DATA_BACKEND=turso_cloud would be silently ignored")

    if args.check:
        return 1

    # Never clobber a foreign sitecustomize without saying so — another tool may
    # legitimately own this filename.
    if target.exists():
        head = target.read_text(encoding="utf-8", errors="replace")[:400]
        if "Empire data-backend switch" not in head:
            backup = target.with_suffix(".py.pre-empire")
            shutil.copy2(target, backup)
            print(f"note        : existing sitecustomize.py was NOT ours; "
                  f"backed up to {backup.name}")

    shutil.copy2(SOURCE, target)
    installed = _sha(target)
    ok = installed == want
    print(f"installed   : {'OK' if ok else 'MISMATCH'} ({installed[:12]})")

    # Proving the file landed is not the same as proving the swap works.
    import os
    import subprocess
    probe = subprocess.run(
        [sys.executable, "-c",
         "import supabase;print(getattr(supabase.create_client,'__module__','?'))"],
        capture_output=True, text=True, timeout=120,
        env={**os.environ, "EMPIRE_DATA_BACKEND": "turso_cloud"})
    module = (probe.stdout or "").strip().splitlines()[-1] if probe.stdout else ""
    live = module == "lib.turso_supabase_compat"
    print(f"live check  : create_client -> {module or '(no output)'} "
          f"{'OK' if live else 'FAILED'}")
    if not live and probe.stderr:
        print(f"              {probe.stderr.strip().splitlines()[-1][:160]}")
    return 0 if (ok and live) else 1


if __name__ == "__main__":
    raise SystemExit(main())
