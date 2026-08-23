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
import re
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


def markdown_to_html(md: str) -> str:
    """Minimal markdown -> HTML so Docs renders headings and tables.

    Deliberately small: these agreements use headings, bold, bullets, tables and
    horizontal rules and nothing else. A full markdown library would be a
    dependency carried for six constructs.
    """
    import html as _html

    def inline(text: str) -> str:
        text = _html.escape(text)
        return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)

    out: list[str] = []
    in_table = False
    for raw in md.splitlines():
        line = raw.rstrip()
        if re.match(r"^\|[\s:\-]+\|$", line):      # table separator
            continue
        if line.startswith("|"):
            if not in_table:
                out.append('<table border="1" cellpadding="6" cellspacing="0">')
                in_table = True
            cells = [c.strip() for c in line.strip("|").split("|")]
            out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in cells) + "</tr>")
            continue
        if in_table:
            out.append("</table>")
            in_table = False
        if line.startswith("### "):
            out.append(f"<h3>{inline(line[4:])}</h3>")
        elif line.startswith("## "):
            out.append(f"<h2>{inline(line[3:])}</h2>")
        elif line.startswith("# "):
            out.append(f"<h1>{inline(line[2:])}</h1>")
        elif line.startswith("- "):
            out.append(f"<li>{inline(line[2:])}</li>")
        elif line.strip() == "---":
            out.append("<hr/>")
        elif not line.strip():
            out.append("<br/>")
        else:
            out.append(f"<p>{inline(line)}</p>")
    if in_table:
        out.append("</table>")
    return "<html><body>" + "\n".join(out) + "</body></html>"


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
        # HTML, written INSIDE the working directory, and both details are
        # load-bearing:
        #
        #   --content stages its own html in the system temp dir, and
        #   google_tool's uploader refuses any path outside the cwd
        #   ("resolves to ... which is outside the current directory"). --html
        #   takes a path we choose, so the file goes under tmp/.
        #
        #   Markdown pasted as plain text arrives in Docs as literal '##' and
        #   '|---|' — unreadable in a document someone signs. Converting to
        #   HTML first is what makes the tables and headings render.
        html_path = out.with_suffix(".html")
        html_path.write_text(markdown_to_html(body), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "scripts/integrations/google_tool.py", "docs", "create",
             "--title", title, "--html", str(html_path), "--json"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        blob = ((proc.stdout or "") + (proc.stderr or "")).strip()
        doc_id = None
        # The tool pretty-prints its JSON, so a line-by-line parse misses it —
        # that exact mistake made a SUCCESSFUL run report failure and produced a
        # duplicate set of documents in Drive.
        try:
            for chunk in re.findall(r"\{[\s\S]*?\}", blob):
                obj = json.loads(chunk)
                doc_id = obj.get("id") or obj.get("documentId")
                if doc_id:
                    break
        except Exception:
            doc_id = None
        if proc.returncode == 0 and doc_id:
            result["gdoc"] = f"https://docs.google.com/document/d/{doc_id}/edit"
        else:
            # The .md is already written, so the work is not lost — say what
            # failed rather than pretending the Doc exists.
            result["gdoc_error"] = blob[-400:] or "docs create failed"
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
