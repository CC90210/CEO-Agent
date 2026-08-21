#!/usr/bin/env python3
"""generate_contractor_agreement — render an OASIS contractor agreement.

WHY THIS EXISTS
CC hires openers, closers, sales managers and builders. Each needs an agreement
stating the exact rates the payout engine will pay them. Retyping those rates
into a Google Doc is how a contract ends up promising something the software
does not do — so the rates are never typed here either.

HOW IT STAYS HONEST
This script does NOT contain a single rate. It shells into the command centre
and renders lib/contracts/templates.ts, which imports its numbers from
lib/website-sales-comp.ts — the same module the close path uses to decide what
to pay. One source, three consumers: the payout, the rep-facing Playbook, and
this document.

    python scripts/generate_contractor_agreement.py \\
        --role closer --name "Jordan Example" --email jordan@example.com

    # ...and push it straight to Google Docs (CC's stated preference over .md):
    python scripts/generate_contractor_agreement.py \\
        --role closer --name "Jordan Example" --email jordan@example.com --gdoc

WHAT IT DELIBERATELY DOES NOT DO
Send anything. It writes a file and, with --gdoc, creates a Doc. Sharing it with
the contractor is a human act with legal weight, and an agent should not be the
one performing it.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

APP_DIR_CANDIDATES = [
    Path.home() / "APPS" / "oasis-command-center",
    Path.home() / "APPS" / "ocs-leadfix",
]
ROLES = ("opener", "closer", "manager", "builder")


def resolve_app_dir(explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit)
        if not (p / "lib" / "contracts" / "templates.ts").exists():
            sys.exit(f"ERROR: {p} has no lib/contracts/templates.ts")
        return p
    for p in APP_DIR_CANDIDATES:
        if (p / "lib" / "contracts" / "templates.ts").exists():
            return p
    sys.exit(
        "ERROR: could not find the command centre checkout. Pass --app-dir.\n"
        f"Looked in: {', '.join(str(p) for p in APP_DIR_CANDIDATES)}"
    )


def render(app_dir: Path, role: str, name: str, email: str, effective: str) -> str:
    """Render through tsx so the contract is produced by the SAME code the app
    ships — not by a Python re-implementation that could drift from it."""
    payload = json.dumps(
        {"contractorName": name, "contractorEmail": email, "effectiveDate": effective}
    )
    script = (
        "import {renderContract} from './lib/contracts/templates';"
        f"process.stdout.write(renderContract({json.dumps(role)} as never, {payload}));"
    )
    entry = app_dir / ".contract-render.mts"
    entry.write_text(script, encoding="utf-8")
    try:
        proc = subprocess.run(
            ["npx", "--yes", "tsx", str(entry)],
            cwd=app_dir,
            capture_output=True,
            text=True,
            # EXPLICIT utf-8. Without it Python decodes with the Windows console
            # codepage (cp1252), and every em-dash and accented character in the
            # template arrives as mojibake — "â€”" instead of "—", and "Québec"
            # mangled in the governing-law clause. That is not a cosmetic bug in
            # a document someone signs.
            encoding="utf-8",
            errors="strict",
            shell=(sys.platform == "win32"),
        )
        if proc.returncode != 0:
            # Loud, with the real reason. A silent empty contract is the one
            # failure mode that could actually reach a signature.
            sys.exit(f"ERROR: render failed ({proc.returncode})\n{proc.stderr.strip()[:2000]}")
        if not proc.stdout.strip():
            sys.exit("ERROR: renderer produced an EMPTY document — refusing to write it")
        return proc.stdout
    finally:
        entry.unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--role", required=True, choices=ROLES)
    ap.add_argument("--name", required=True, help="the contractor's legal name")
    ap.add_argument("--email", required=True)
    ap.add_argument("--effective", default=date.today().isoformat())
    ap.add_argument("--app-dir", default=None)
    ap.add_argument("--out", default=None, help="output path (default: tmp/contracts/)")
    ap.add_argument("--gdoc", action="store_true", help="also create a Google Doc")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    app_dir = resolve_app_dir(args.app_dir)
    body = render(app_dir, args.role, args.name, args.email, args.effective)

    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in args.name).strip("-")
    out = Path(args.out) if args.out else Path("tmp/contracts") / f"{args.role}-{slug}-{args.effective}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body, encoding="utf-8")

    result = {"ok": True, "role": args.role, "file": str(out), "chars": len(body)}

    if args.gdoc:
        title = f"OASIS {args.role.title()} Agreement — {args.name} ({args.effective})"
        proc = subprocess.run(
            [sys.executable, "scripts/integrations/google_tool.py", "docs-create",
             "--title", title, "--body-file", str(out), "--json"],
            capture_output=True, text=True,
        )
        if proc.returncode == 0:
            result["gdoc"] = proc.stdout.strip()[-500:]
        else:
            # The .md is already written, so the work is not lost — say what
            # failed rather than pretending the Doc exists.
            result["gdoc_error"] = proc.stderr.strip()[:500] or "google_tool docs-create failed"
            result["ok"] = False

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"{args.role} agreement -> {out}  ({len(body):,} chars)")
        if "gdoc" in result:
            print(f"google doc: {result['gdoc']}")
        if "gdoc_error" in result:
            print(f"WARNING: Google Doc not created — {result['gdoc_error']}")
        print("\nNOT SENT. Review it, then share it yourself — that is a human act.")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
