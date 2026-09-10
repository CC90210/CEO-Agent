"""test_smtp_chokepoint.py — lib/smtp_send is the ONLY module that may open
an SMTP connection.

WHY THIS TEST EXISTS. smtp_send.py's own docstring claimed "no other file
should import smtplib directly" — and on 2026-09-10 that claim was false in
three places at once:

  scripts/integrations/google_tool.py:285   its own smtplib.SMTP_SSL, with
                                            branded=True by default and
                                            gmail_user from the host-global
                                            GMAIL_USER
  scripts/tests/live_financial_filing_probe.py:113
                                            its own smtplib.SMTP_SSL
  scripts/integrations/send_gateway.py:92   import smtplib, unused

That is the same defect class as the incident this whole branch is about:
prose asserting a guarantee that nothing enforces. The sender-identity guard
lives in smtp_send precisely because it is the one module every path shares —
so a second door does not just skip a check, it silently voids the fix.

A comment cannot hold this invariant. A test can. If a new caller needs SMTP,
the fix is to route it through smtp_send, not to widen ALLOWED.

Run: python scripts/tests/test_smtp_chokepoint.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]

# The one module permitted to speak SMTP, repo-relative and POSIX-normalised.
ALLOWED = {"scripts/lib/smtp_send.py"}

_SKIP_PARTS = {
    ".venv", "venv", "node_modules", "__pycache__", "_archive", "tmp",
    ".git", "site-packages", "build", "dist",
}

failures: list[str] = []


def _iter_py() -> list[Path]:
    out = []
    for path in _REPO.rglob("*.py"):
        if _SKIP_PARTS & set(path.parts):
            continue
        out.append(path)
    return out


def _rel(path: Path) -> str:
    return path.relative_to(_REPO).as_posix()


_FILES = _iter_py()

for path in _FILES:
    rel = _rel(path)
    try:
        # utf-8-sig: a BOM is legal in Python source (PEP 263) and CPython
        # accepts it, but ast.parse rejects the U+FEFF if it is left in the
        # string. Two files in this repo carry one.
        source = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        # Unreadable is not innocent — say so rather than skipping silently.
        failures.append(f"{rel}: could not be read, so it could not be checked")
        continue
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        failures.append(f"{rel}: does not parse ({exc.msg} at line {exc.lineno})")
        continue

    if rel in ALLOWED:
        continue

    for node in ast.walk(tree):
        # `import smtplib`, `import smtplib as x`
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "smtplib" or alias.name.startswith("smtplib."):
                    failures.append(
                        f"{rel}:{node.lineno}: imports smtplib. Only "
                        f"{sorted(ALLOWED)[0]} may — route the send through "
                        f"`from lib.smtp_send import smtp_send` so the "
                        f"sender-identity guard cannot be walked around."
                    )
        # `from smtplib import SMTP_SSL`
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "") == "smtplib":
                failures.append(
                    f"{rel}:{node.lineno}: imports from smtplib. Only "
                    f"{sorted(ALLOWED)[0]} may — route the send through "
                    f"`from lib.smtp_send import smtp_send`."
                )
        # importlib.import_module("smtplib") / __import__("smtplib") — the
        # obvious way around an import check, so it is worth one branch.
        elif isinstance(node, ast.Call):
            fname = ""
            if isinstance(node.func, ast.Name):
                fname = node.func.id
            elif isinstance(node.func, ast.Attribute):
                fname = node.func.attr
            if fname in {"import_module", "__import__"}:
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and arg.value == "smtplib":
                        failures.append(
                            f"{rel}:{node.lineno}: imports smtplib dynamically. "
                            f"Only {sorted(ALLOWED)[0]} may."
                        )

# The allowlist must describe reality, or it is the same broken promise one
# level up: a file listed here that no longer exists would let a real
# violation be renamed into the gap.
for allowed in ALLOWED:
    if not (_REPO / allowed).is_file():
        failures.append(f"ALLOWED names {allowed}, which does not exist")

# And the chokepoint must still BE one. Routing every caller through a module
# that no longer opens a connection, or no longer runs the guard, would satisfy
# every check above while protecting nothing.
#
# These are AST checks against the body of smtp_send(), not substring searches.
# A substring search passes when the guard is merely DEFINED — the exact shape
# of the original bug, where the check existed in a module nothing called.
# (CodeRabbit, PR #73.)
_chokepoint_src = (_REPO / "scripts/lib/smtp_send.py").read_text(encoding="utf-8")
_chokepoint_tree = ast.parse(_chokepoint_src)
_smtp_send_fn = next(
    (n for n in _chokepoint_tree.body
     if isinstance(n, ast.FunctionDef) and n.name == "smtp_send"),
    None,
)
if _smtp_send_fn is None:
    failures.append("scripts/lib/smtp_send.py no longer defines smtp_send()")
else:
    _called: set[str] = set()
    _attrs: set[str] = set()
    for _n in ast.walk(_smtp_send_fn):
        if isinstance(_n, ast.Call):
            _f = _n.func
            if isinstance(_f, ast.Name):
                _called.add(_f.id)
            elif isinstance(_f, ast.Attribute):
                _called.add(_f.attr)
                if isinstance(_f.value, ast.Name):
                    _attrs.add(f"{_f.value.id}.{_f.attr}")
    if "SMTP_SSL" not in _called and "smtplib.SMTP_SSL" not in _attrs:
        failures.append(
            "smtp_send() no longer CALLS smtplib.SMTP_SSL — this test would "
            "then be enforcing an empty invariant"
        )
    if "_identity_conflict" not in _called:
        failures.append(
            "smtp_send() no longer CALLS _identity_conflict — routing every "
            "caller through it is only worth doing while it checks something. "
            "(Defining the function is not calling it: that is the shape of "
            "the original bug.)"
        )

checked = len(_FILES)

def test_no_failures() -> None:
    """The pytest entry point.

    Every assertion above runs at import. Without a real test function pytest
    collects ZERO tests from this file, and a failure surfaces as SystemExit
    during collection — an INTERNALERROR that aborts the WHOLE run and hides
    every suite after it. One red test is the correct signal.
    """
    assert not failures, (
        f"{len(failures)} assertion(s) failed:\n\n  - "
        + "\n  - ".join(failures)
    )


if __name__ == "__main__":
    if failures:
        print(f"FAIL — {len(failures)} assertion(s):\n")
        for _f in failures:
            print(f"  - {_f}")
        sys.exit(1)
    print(f"test_smtp_chokepoint.py — {checked} files checked, "
          f"lib/smtp_send.py is the only SMTP door")
