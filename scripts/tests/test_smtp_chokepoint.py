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

# ════ The same invariant for the OTHER transport: the Gmail API ════════════
#
# "Only smtp_send imports smtplib" is a MECHANISM check, and a mechanism check is
# blind to anything that reaches the same outcome another way. The Gmail API is
# exactly that: google_tool's --plain path hands a raw message to gws
# users.messages.send and never touches smtplib, so this file stayed green while
# that path signed every mailbox as CC. (Codex, PR #73.)
#
# Every Gmail-API send site must be listed here WITH the reason its From identity
# is the account that actually sends. A new site fails until someone writes that
# reason down — and wherever the reason can be checked, it is checked below.
GMAIL_API_SENDERS: dict[str, str] = {
    "scripts/integrations/google_tool.py":
        "--plain send via gws; the From comes from the gws-authenticated account "
        "(users.getProfile), never from GMAIL_USER",
    "scripts/integrations/user_gmail_oauth.py":
        "defines send_via_gmail_api, the per-user OAuth transport itself",
    "scripts/integrations/send_gateway.py":
        "per-user OAuth: gmail_user = user_gmail_bundle['gmail_address'] and the "
        "token comes from the same bundle, so From and sender are one account",
    "scripts/dashboard_email_consumer.py":
        "per-user OAuth: gmail_from = user_bundle['gmail_address'] and the token "
        "comes from the same bundle, so From and sender are one account",
}
_GMAIL_SEND_FUNCS = {"send_via_gmail_api", "_send_via_gmail_api"}


def _gmail_api_send_lines(tree: ast.AST) -> list[int]:
    """Line numbers that send mail over the Gmail API, by any spelling found here."""
    hits: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in _GMAIL_SEND_FUNCS:
            hits.append(node.lineno)
        elif (isinstance(node, ast.Constant) and isinstance(node.value, str)
              and "/messages/send" in node.value):
            hits.append(node.lineno)
        elif isinstance(node, ast.Call):
            f = node.func
            name = f.id if isinstance(f, ast.Name) else (
                f.attr if isinstance(f, ast.Attribute) else "")
            if name in _GMAIL_SEND_FUNCS:
                hits.append(node.lineno)
            # google-api-python-client: service.users().messages().send(...)
            if (isinstance(f, ast.Attribute) and f.attr == "send"
                    and isinstance(f.value, ast.Call)
                    and isinstance(f.value.func, ast.Attribute)
                    and f.value.func.attr == "messages"):
                hits.append(node.lineno)
            # a gws argv list: [..., "messages", "send", ...]
            for arg in node.args:
                if isinstance(arg, ast.List):
                    vals = [el.value for el in arg.elts
                            if isinstance(el, ast.Constant) and isinstance(el.value, str)]
                    if any(a == "messages" and b == "send" for a, b in zip(vals, vals[1:])):
                        hits.append(node.lineno)
    return sorted(set(hits))


_gmail_found: dict[str, list[int]] = {}
for path in _FILES:
    rel = _rel(path)
    if "tests" in Path(rel).parts:
        continue  # tests mock these transports; they are not send paths
    try:
        _tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    except (OSError, UnicodeDecodeError, SyntaxError):
        continue  # the smtplib pass above already reports unreadable files
    _lines = _gmail_api_send_lines(_tree)
    if _lines:
        _gmail_found[rel] = _lines

for rel, _lines in sorted(_gmail_found.items()):
    if rel not in GMAIL_API_SENDERS:
        failures.append(
            f"{rel}:{_lines[0]}: sends over the Gmail API but is not in "
            f"GMAIL_API_SENDERS. That transport never passes lib.smtp_send's "
            f"identity guard, so list it with the reason its From identity is "
            f"the account that actually sends — or route it through smtp_send."
        )
for rel in GMAIL_API_SENDERS:
    if rel not in _gmail_found:
        failures.append(
            f"GMAIL_API_SENDERS lists {rel}, which no longer sends over the Gmail "
            f"API — remove it, or the list stops describing reality"
        )

# Where a reason can be checked, check it: a reason nobody verifies is the same
# broken promise as the docstring this file was written to replace.
_gt_src = (_REPO / "scripts/integrations/google_tool.py").read_text(encoding="utf-8")
_gt_tree = ast.parse(_gt_src)
_enc = next((n for n in _gt_tree.body
             if isinstance(n, ast.FunctionDef) and n.name == "_encode_email"), None)
if _enc is None:
    failures.append("google_tool._encode_email is gone — re-check the --plain Gmail API path")
else:
    _kw = [a.arg for a in _enc.args.kwonlyargs]
    _kw_default = dict(zip(_kw, _enc.args.kw_defaults))
    if "sender" not in _kw or _kw_default.get("sender") is not None:
        failures.append(
            "google_tool._encode_email must take a REQUIRED keyword-only `sender` "
            "(the authenticated account), so no caller can fall back to an "
            "environment variable")
    # An env LOOKUP, not prose. The docstring explains why GMAIL_USER was the
    # wrong source, so a substring search over the source flagged the very
    # comment documenting the fix. The key as a string literal is what a
    # regression would actually contain: os.environ.get("GMAIL_USER").
    if any(isinstance(n, ast.Constant) and n.value == "GMAIL_USER"
           for n in ast.walk(_enc)):
        failures.append(
            "google_tool._encode_email reads GMAIL_USER again — the From must come "
            "from the account gws is authenticated as")
_gs = next((n for n in _gt_tree.body
            if isinstance(n, ast.FunctionDef) and n.name == "gmail_send"), None)
if _gs is None or "_gws_authenticated_address" not in (ast.get_source_segment(_gt_src, _gs) or ""):
    failures.append(
        "google_tool.gmail_send no longer asks gws which account it is "
        "authenticated as before a --plain send")
for rel, needle in (("scripts/integrations/send_gateway.py",
                     'gmail_user = user_gmail_bundle["gmail_address"]'),
                    ("scripts/dashboard_email_consumer.py",
                     'gmail_from = user_bundle["gmail_address"]')):
    if needle not in (_REPO / rel).read_text(encoding="utf-8"):
        failures.append(
            f"{rel}: the per-user OAuth From no longer visibly comes from the same "
            f"bundle as the token ({needle!r}) — re-verify before keeping it in "
            f"GMAIL_API_SENDERS")

# The dashboard consumer's Gmail API send is listed above as safe because the
# From and the token come from one bundle. That is necessary, not sufficient: a
# rep's bundle can sit on the OTHER company's domain. It is safe because the send
# is refused first when the mailbox belongs to the other company. (Codex +
# CodeRabbit, PR #73.)
#
# Checked on the syntax tree of _send_one(), not the file's text. The first
# version searched for "_refuse_other_company(", which the helper's own `def`
# line satisfies, so deleting every call left it green. (CodeRabbit, PR #73.)
# Now each transport call must have, earlier in its OWN branch or an enclosing
# one, a gate: `if _refuse_other_company(...): return ...`, where the test IS the
# call and the body is only the return. A refusal in the other branch does not
# count, and neither does one whose verdict is ignored.
#
# Hardened after Codex (PR #73) showed the first AST version could stay green
# while a send went unguarded. A gate buried inside a preceding statement (an
# `except`, another `if`) counted as guarding what follows, and a transport
# reached through an alias or getattr() was never inspected. Now nothing is
# searched inside a preceding statement. Every name a transport is imported or
# re-bound as is followed. Any use of a transport other than calling it (or
# testing it against None) fails, so it cannot be carried past the gate.
_TRANSPORTS = ("smtp_send", "send_via_gmail_api")


def _is_refusal_if(stmt: ast.AST) -> bool:
    """A direct `if _refuse_other_company(...): return ...` and nothing else.

    Never a guard found by searching inside another statement, and never one
    inside a loop: a loop can run zero times, so a guard in its body proves
    nothing about the send after it."""
    return (isinstance(stmt, ast.If)
            and isinstance(stmt.test, ast.Call)
            and isinstance(stmt.test.func, ast.Name)
            and stmt.test.func.id == "_refuse_other_company"
            and len(stmt.body) == 1
            and isinstance(stmt.body[0], ast.Return))


def _dominating(fn: ast.FunctionDef, node: ast.AST, parents: dict) -> list:
    """Every statement that runs, unconditionally, before `node` in its own
    branch or an enclosing one."""
    out: list = []
    while node is not fn:
        parent = parents[node]
        for field in ("body", "orelse", "finalbody"):
            seq = getattr(parent, field, None)
            if isinstance(seq, list) and node in seq:
                out.extend(seq[:seq.index(node)])
        node = parent
    return out


def _guarded_mailboxes(fn: ast.FunctionDef, node: ast.AST, parents: dict) -> set:
    """The names a dominating direct guard checked, via its mailbox= argument."""
    names: set = set()
    for stmt in _dominating(fn, node, parents):
        if _is_refusal_if(stmt):
            for kw in stmt.test.keywords:
                if kw.arg == "mailbox" and isinstance(kw.value, ast.Name):
                    names.add(kw.value.id)
    return names


def _names_in(expr: ast.AST) -> set:
    return {n.id for n in ast.walk(expr) if isinstance(n, ast.Name)}


def _send_identities(fn: ast.FunctionDef, call: ast.Call, parents: dict) -> set:
    """Every mailbox a send uses: the account smtp_send() logs in as (its first
    argument), and the From of each message built before it (the second
    argument of _build_message). Codex, PR #73: a checker that only asks
    whether SOME guard precedes the send stays green when the From's guard is
    deleted, because the login's guard still precedes it."""
    ids: set = set()
    if (isinstance(call.func, ast.Name) and _gate_canon.get(call.func.id) == "smtp_send"
            and call.args):
        ids |= _names_in(call.args[0])
    for stmt in _dominating(fn, call, parents):
        for n in ast.walk(stmt):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                    and n.func.id == "_build_message" and len(n.args) >= 2):
                ids |= _names_in(n.args[1])
    return ids


def _send_is_guarded(fn: ast.FunctionDef, call: ast.Call, parents: dict) -> bool:
    ids = _send_identities(fn, call, parents)
    return bool(ids) and ids <= _guarded_mailboxes(fn, call, parents)


_dec_rel = "scripts/dashboard_email_consumer.py"
_dec_tree = ast.parse((_REPO / _dec_rel).read_text(encoding="utf-8"))
# Every local name a transport is bound to: `from x import smtp_send as y`
# anywhere in the module, then module-level `z = y` re-bindings.
_gate_canon = {t: t for t in _TRANSPORTS}
for _node in ast.walk(_dec_tree):
    if isinstance(_node, ast.ImportFrom):
        for _alias in _node.names:
            if _alias.name in _TRANSPORTS:
                _gate_canon[_alias.asname or _alias.name] = _alias.name
for _ in range(3):
    for _node in _dec_tree.body:
        if (isinstance(_node, ast.Assign) and isinstance(_node.value, ast.Name)
                and _node.value.id in _gate_canon):
            for _target in _node.targets:
                if isinstance(_target, ast.Name):
                    _gate_canon[_target.id] = _gate_canon[_node.value.id]
_send_one_fn = next((n for n in _dec_tree.body
                     if isinstance(n, ast.FunctionDef) and n.name == "_send_one"), None)
if _send_one_fn is None:
    failures.append(f"{_dec_rel} no longer defines _send_one() — re-check which "
                    "function drains the dashboard queue before trusting this test")
else:
    _gate_par = {child: parent for parent in ast.walk(_send_one_fn)
                 for child in ast.iter_child_nodes(parent)}
    _gate_called: set = set()
    for _node in ast.walk(_send_one_fn):
        _name = (_node.id if isinstance(_node, ast.Name)
                 else _node.attr if isinstance(_node, ast.Attribute) else None)
        if _name in _gate_canon:
            _up = _gate_par.get(_node)
            if isinstance(_up, ast.Call) and _up.func is _node:
                _gate_called.add(_gate_canon[_name])
                _ids = _send_identities(_send_one_fn, _up, _gate_par)
                _unguarded = sorted(_ids - _guarded_mailboxes(_send_one_fn, _up, _gate_par))
                if not _ids or _unguarded:
                    failures.append(
                        f"{_dec_rel}:{_node.lineno}: _send_one() calls {_name}() as "
                        f"{', '.join(_unguarded) or 'an identity it cannot name'} with no "
                        "`if _refuse_other_company(..., mailbox=<that name>): return` before "
                        "it in its branch — a mailbox on the other company's domain can send "
                        "that company's mail")
            elif not isinstance(_up, ast.Compare):
                failures.append(
                    f"{_dec_rel}:{_node.lineno}: _send_one() uses transport {_name} other "
                    "than by calling it — an alias or callback carries it past the refusal gate")
        elif (isinstance(_node, ast.Constant) and isinstance(_node.value, str)
                and _node.value in _gate_canon):
            failures.append(
                f"{_dec_rel}:{_node.lineno}: _send_one() names transport {_node.value!r} as a "
                "string — a getattr() call cannot be checked for a refusal gate")
    for _t in _TRANSPORTS:
        if _t not in _gate_called:
            failures.append(f"{_dec_rel}: _send_one() no longer calls {_t}() — "
                            "this check would then pass while guarding nothing")


# The gate checker is itself tested, on small synthetic send functions, so an
# edit that loosens it fails here instead of quietly approving a bypass. Each
# rejected shape was named by CodeRabbit or Codex on PR #73; the accepted ones
# include the shapes _send_one() really uses.
def _gate_verdict(body: str) -> bool:
    import textwrap
    src = "def _send_one():\n" + textwrap.indent(textwrap.dedent(body).strip("\n") + "\n", "    ")
    fn = ast.parse(src).body[0]
    par = {child: parent for parent in ast.walk(fn) for child in ast.iter_child_nodes(parent)}
    sends = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == "smtp_send"]
    return bool(sends) and all(_send_is_guarded(fn, s, par) for s in sends)


for _label, _want, _body in (
    ("guards on the login and on the From", True, """
        if _refuse_other_company(mailbox=user):
            return "failed"
        if _refuse_other_company(mailbox=sender):
            return "failed"
        msg = _build_message(row, sender or user)
        smtp_send(user, pw, msg)
    """),
    ("guard, then the send inside a try", True, """
        if _refuse_other_company(mailbox=user):
            return "failed"
        msg = _build_message(row, user)
        try:
            smtp_send(user, pw, msg)
        except Exception:
            pass
    """),
    ("guard enclosing a nested send", True, """
        if _refuse_other_company(mailbox=user):
            return "failed"
        if ready:
            smtp_send(user, pw, msg)
    """),
    ("login guarded, From not", False, """
        if _refuse_other_company(mailbox=user):
            return "failed"
        msg = _build_message(row, sender or user)
        smtp_send(user, pw, msg)
    """),
    ("guard on a different mailbox", False, """
        if _refuse_other_company(mailbox=someone_else):
            return "failed"
        smtp_send(user, pw, msg)
    """),
    ("no guard", False, """
        smtp_send(user, pw, msg)
    """),
    ("guard after the send", False, """
        smtp_send(user, pw, msg)
        if _refuse_other_company(mailbox=user):
            return "failed"
    """),
    ("negated", False, """
        if not _refuse_other_company(mailbox=user):
            return "failed"
        smtp_send(user, pw, msg)
    """),
    ("conjunctive", False, """
        if strict and _refuse_other_company(mailbox=user):
            return "failed"
        smtp_send(user, pw, msg)
    """),
    ("wrapped", False, """
        if bool(_refuse_other_company(mailbox=user)):
            return "failed"
        smtp_send(user, pw, msg)
    """),
    ("verdict ignored", False, """
        _refuse_other_company(mailbox=user)
        smtp_send(user, pw, msg)
    """),
    ("conditional return", False, """
        if _refuse_other_company(mailbox=user):
            if strict:
                return "failed"
        smtp_send(user, pw, msg)
    """),
    ("guard inside an except", False, """
        try:
            pass
        except Exception:
            if _refuse_other_company(mailbox=user):
                return "failed"
        smtp_send(user, pw, msg)
    """),
    ("guard inside another if", False, """
        if strict:
            if _refuse_other_company(mailbox=user):
                return "failed"
        smtp_send(user, pw, msg)
    """),
    ("guard in the other branch", False, """
        if use_api:
            if _refuse_other_company(mailbox=user):
                return "failed"
        else:
            smtp_send(user, pw, msg)
    """),
    ("guard inside a loop that may not run", False, """
        for mb in mailboxes:
            if _refuse_other_company(mailbox=user):
                return "failed"
        smtp_send(user, pw, msg)
    """),
):
    if _gate_verdict(_body) is not _want:
        failures.append(
            f"the refusal-gate checker misjudges the {_label!r} shape: it should be "
            f"{'accepted' if _want else 'rejected'}. A checker that approves a bypass "
            "is worse than none, and one that refuses the real guard trains people "
            "to delete it")

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
            # Record each callee EXACTLY. The first version also added the
            # bare attribute name for every attribute call, so an unrelated
            # `transport.SMTP_SSL()` or `guard._identity_conflict()` satisfied
            # the checks below while neither guard was actually called.
            # (CodeRabbit, PR #73.) Names go in _called; `receiver.attr` pairs
            # go in _attrs; nothing is matched on the final name alone.
            if isinstance(_f, ast.Name):
                _called.add(_f.id)
            elif isinstance(_f, ast.Attribute) and isinstance(_f.value, ast.Name):
                _attrs.add(f"{_f.value.id}.{_f.attr}")
    if "smtplib.SMTP_SSL" not in _attrs:
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
