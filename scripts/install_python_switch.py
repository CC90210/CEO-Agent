#!/usr/bin/env python3
"""Install the Turso data-backend switch into the active venv.

WHY THIS EXISTS
    The switch must run before harness code binds `create_client`. site-packages
    is therefore where it has to LIVE — but that directory is not in any repo,
    so the file existed on exactly one machine, in no git history, and the VPS
    never had it. Setting EMPIRE_DATA_BACKEND=turso_cloud there did nothing,
    silently, and those daemons kept writing to the database we are cancelling.

    The tracked source is scripts/_bootstrap/sitecustomize.py.

WHY A .pth AND NOT sitecustomize.py (changed 2026-08-08)
    `sitecustomize` is a single global name and Python imports the FIRST one on
    sys.path. Debian ships /usr/lib/python3.12/sitecustomize.py (a symlink to
    /etc/python3.12/sitecustomize.py), and the stdlib directory sits at sys.path
    index 2 while a venv's site-packages is index 4. Measured on the SunBiz VPS:

        importlib.util.find_spec("sitecustomize").origin
          -> /usr/lib/python3.12/sitecustomize.py

    So writing site-packages/sitecustomize.py there produces a file Python never
    imports. The switch would silently never apply and all 13 daemons would keep
    writing to Supabase while every surface reported success — the precise
    failure this migration exists to eliminate.

    .pth files have no such collision: site.py executes every `import ...` line
    in every .pth found in site-packages, and the filename only affects ordering.
    The zzz_ prefix makes this run last, after any path-setup .pth. This is also
    why the module is installed under a private name — nothing else can shadow
    `empire_turso_switch`.

    python scripts/install_python_switch.py            # install / update
    python scripts/install_python_switch.py --check    # report only, exit 1 if stale
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import shutil
import site
import sys
import sysconfig
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SOURCE = REPO / "scripts" / "_bootstrap" / "sitecustomize.py"

# Installed under a private name, not `sitecustomize`: that name is global and
# first-match-wins, and Debian already owns it two sys.path entries earlier.
MODULE_NAME = "empire_turso_switch"
# Leading zzz_ so site.py runs it after any path-setup .pth (e.g. the
# distutils-precedence.pth setuptools ships). Ordering within a directory is
# by filename.
PTH_NAME = "zzz_empire_turso_switch.pth"

sys.path.insert(0, str(REPO / "scripts"))
from lib import turso_switch  # noqa: E402


def _shadowing_sitecustomize() -> str | None:
    """Return the path of a sitecustomize that would win over site-packages.

    This is the check whose absence made the switch a guaranteed silent no-op
    on Debian. Reported by --check so the hazard surfaces before flip time,
    not after.
    """
    try:
        spec = importlib.util.find_spec("sitecustomize")
    except Exception:  # noqa: BLE001
        return None
    if spec is None or not spec.origin:
        return None
    sp = _site_packages()
    if sp and Path(spec.origin).parent == sp:
        return None          # it is ours / in site-packages: not shadowing
    return spec.origin


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
    target = sp / f"{MODULE_NAME}.py"
    pth = sp / PTH_NAME

    print(f"interpreter : {sys.executable}")
    print(f"site-packages: {sp}")
    print(f"source      : {SOURCE.relative_to(REPO)}")

    shadow = _shadowing_sitecustomize()
    if shadow:
        print(f"note        : {shadow} would shadow a site-packages "
              f"sitecustomize.py — which is exactly why this installs a .pth "
              f"under a private module name instead")

    want = _sha(SOURCE)
    pth_line = f"import {MODULE_NAME}\n"
    fresh = (target.exists() and _sha(target) == want
             and pth.exists()
             and pth.read_text(encoding="utf-8").strip() == pth_line.strip())
    if fresh:
        print("status      : up to date")
        return 0
    if target.exists():
        print(f"status      : STALE (installed {_sha(target)[:12]}, "
              f"source {want[:12]})")
    else:
        print("status      : NOT INSTALLED — this interpreter has no switch, so "
              "EMPIRE_DATA_BACKEND=turso_cloud would be silently ignored")

    if args.check:
        return 1

    # A previous install wrote site-packages/sitecustomize.py. On Debian that
    # file was never imported; on Windows it was. Retire ours so the .pth is the
    # single mechanism everywhere — two live copies is how they drift.
    legacy = sp / "sitecustomize.py"
    if legacy.exists():
        head = legacy.read_text(encoding="utf-8", errors="replace")[:400]
        if "Empire data-backend switch" in head:
            legacy.rename(legacy.with_suffix(".py.superseded"))
            print("note        : retired our old sitecustomize.py "
                  "(superseded by the .pth)")
        else:
            print("note        : left a foreign sitecustomize.py in place")

    shutil.copy2(SOURCE, target)
    pth.write_text(pth_line, encoding="utf-8")
    installed = _sha(target)
    ok = installed == want
    print(f"installed   : {'OK' if ok else 'MISMATCH'} ({installed[:12]}) "
          f"as {target.name} + {pth.name}")

    # Proving the file landed is not the same as proving the swap works: a
    # sitecustomize can be present and still be stale, shadowed, or unable to
    # import what it needs.
    status = turso_switch.probe()
    print(f"live check  : create_client -> {status.module or '(no output)'} "
          f"{'OK' if status.active else 'FAILED'}")
    if not status.active and status.error:
        print(f"              {status.error[:160]}")
    return 0 if (ok and status.active) else 1


if __name__ == "__main__":
    raise SystemExit(main())
