"""test_google_tool_brand.py — the operator CLI renders the mailbox's brand,
never the module's.

THE THIRD DOOR. The 2026-09-09 cross-brand leak was traced to
dashboard_email_consumer and closed at the shared transport (lib/smtp_send).
google_tool.gmail_send_smtp was a third path, and it was worse than the other
two in one specific way:

  * `gmail send` defaults --branded ON, so the branded path is the DEFAULT
  * it passed no brand, and email_template defaulted to OASIS
  * gmail_user comes from the host-global GMAIL_USER

On the SunBiz VPS, GMAIL_USER is the client's own mailbox. So one
`google_tool.py gmail send ...` there rendered the OASIS shell — logo,
"Founder, OASIS AI Solutions", oasisai.work — authenticated as
submissions@sunbizfunding.com.

The transport's identity guard could NOT have caught this. That guard keys on
the postal address inside a CASL identification block, and the branded shell
renders no postal address at all. So the two fixes are complementary and both
are pinned here:

  brand-follows-mailbox   makes the wrong chrome unrepresentable
  transport identity guard catches an identification block that slips past

Run: python scripts/tests/test_google_tool_brand.py
"""

from __future__ import annotations

import importlib
import os
import re
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1]
for _p in (str(_SCRIPTS), str(_SCRIPTS / "integrations")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import lib.smtp_send as transport  # noqa: E402

# This module drives the CLI through os.environ, which under pytest is SHARED
# with every other test in the process. Snapshot what we touch and put it back
# at the end, or a later suite inherits a GMAIL_USER it never set.
_ENV_KEYS = ("GMAIL_USER", "GMAIL_APP_PASSWORD", "BRAVO_FROM_DISPLAY",
             "USER_FULL_NAME")
_ENV_SAVED = {k: os.environ.get(k) for k in _ENV_KEYS}

os.environ["GMAIL_APP_PASSWORD"] = "stub-not-a-real-credential"

# SET these, do not clear them. An earlier version of this file POPPED
# BRAVO_FROM_DISPLAY and USER_FULL_NAME "so they would not mask the brand
# default" — which manufactured a clean host that does not exist. Every box
# Bravo runs on has CC's operator identity in these variables, and with them
# set the resolvers preferred them over the brand, so a SunBiz send went out
# as "Conaugh McKenna <submissions@sunbizfunding.com>". The test passed
# throughout. Codex found it in review; the test had been hiding it.
#
# So the fixture is now the REAL host: CC's globals present, and the
# assertions below require the client's brand to survive them.
os.environ["BRAVO_FROM_DISPLAY"] = "Conaugh McKenna"
os.environ["USER_FULL_NAME"] = "Conaugh McKenna"

gt = importlib.import_module("google_tool")

failures: list[str] = []
_seen: dict[str, object] = {}


def check(label: str, got, want) -> None:
    if got != want:
        failures.append(f"{label}\n     got:  {got!r}\n     want: {want!r}")


def _stub_transport(user, pw, mime, to, timeout=30, require_from_domain=None):
    """Stub the socket, run the REAL identity guard.

    Stubbing the guard too would make this test pass against a codebase with
    no guard at all — which is exactly the failure mode this branch exists to
    fix, so it is worth the extra line.
    """
    conflict = transport._identity_conflict(mime, user)
    if conflict:
        return False, f"sender-identity guard: {conflict}"
    text = "\n".join(
        (part.get_payload(decode=True) or b"").decode("utf-8", "replace")
        for part in mime.walk()
        if part.get_content_maintype() == "text"
    )
    flat = re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", text)).lower()
    _seen.clear()
    _seen.update({
        "from": mime["From"],
        "auth": user,
        "oasis_chrome": "oasis ai solutions" in flat,
        "sunbiz_chrome": "sunbiz" in flat,
    })
    return True, None


gt.smtp_send = _stub_transport


def send(mailbox: str, body: str = "Body text", *, branded: bool = True):
    _seen.clear()
    os.environ["GMAIL_USER"] = mailbox
    return gt.gmail_send_smtp("contact@example.com", "Subject", body,
                              branded=branded)


# ---- The incident shape: branded send from the client's mailbox ------------
res, err = send("submissions@sunbizfunding.com")
check("a branded send from the client's mailbox still goes out", res is not None, True)
check("...but carries NO OASIS chrome", _seen.get("oasis_chrome"), False)
check("...and is signed as the client", _seen.get("sunbiz_chrome"), True)
check("...with a From header on the client's own identity",
      "sunbizfunding.com" in str(_seen.get("from", "")), True)
check("...and never OASIS's name in the From header",
      "oasis" in str(_seen.get("from", "")).lower(), False)
# THE REGRESSION CODEX CAUGHT. The host-global operator name must not reach a
# client's From header just because it is set on the box doing the sending.
check("...and not CC's name off a host-global either",
      "conaugh" in str(_seen.get("from", "")).lower(), False)
check("...the From display is the client's own",
      "SunBiz Submissions" in str(_seen.get("from", "")), True)

# ---- Control: the same call from the OASIS mailbox -------------------------
res, err = send("conaugh@oasisai.work")
check("a branded send from the OASIS mailbox goes out", res is not None, True)
check("...and DOES carry OASIS chrome", _seen.get("oasis_chrome"), True)
check("...with an oasisai.work From header",
      "oasisai.work" in str(_seen.get("from", "")), True)

# A rep's own mailbox on an entitled domain resolves by domain, not by roster.
res, err = send("rep.example@sunbizfunding.com")
check("a rep's own address on the sending domain resolves", res is not None, True)
check("...to the client's brand, not OASIS", _seen.get("oasis_chrome"), False)

# ---- An unregistered mailbox must refuse, not guess ------------------------
res, err = send("someone@randomdomain.example")
check("an unregistered mailbox refuses rather than defaulting to OASIS",
      res is None, True)
check("...and the refusal names the mailbox",
      "randomdomain.example" in (err or ""), True)
check("...and says how to fix it",
      "BRAND_SENDING_DOMAIN" in (err or ""), True)

# ---- The transport guard still backstops an identification block -----------
# Belt and braces: the brand fix stops the CHROME, this stops a body that
# carries another company's legal identification whatever the chrome says.
res, err = send(
    "submissions@sunbizfunding.com",
    "Hi,\n\nOASIS AI Solutions, 6993 Decarie Blvd, Montreal, QC H3W 0B5, Canada",
    branded=False,
)
check("an OASIS identification block from the client's mailbox is refused",
      res is None, True)
check("...by the identity guard specifically", "identity guard" in (err or ""), True)

# ---- The template registry must refuse an unknown brand -------------------
# The last of the fail-open family named in the root-cause assessment:
# email_template used to return the OASIS config for ANY unrecognised string.
import email_template  # noqa: E402

try:
    email_template._brand("sunbiz-funding")  # a plausible typo of a real brand
    failures.append("email_template._brand('sunbiz-funding') fell back instead of raising")
except ValueError as exc:
    check("an unknown brand names the known ones", "oasis" in str(exc), True)

check("an ABSENT brand still resolves to this module's own",
      email_template._brand(None) is email_template.BRAND_CONFIG["oasis"], True)
check("a known brand resolves to itself",
      email_template._brand("sunbiz") is email_template.BRAND_CONFIG["sunbiz"], True)

# The aliases are the reason refusing is safe. conaugh_mckenna and nostalgic
# are live brands in send_gateway.BRAND_IDENTITY and in email_engine's --brand
# choices; before the alias map they reached OASIS chrome via the fail-open, so
# refusing without listing them would have stripped their shell silently
# through send_gateway's except-branch.
for _alias in ("conaugh_mckenna", "nostalgic"):
    check(f"{_alias} still renders OASIS chrome (it is the same legal entity)",
          email_template._brand(_alias) is email_template.BRAND_CONFIG["oasis"], True)

# Every brand send_gateway can be asked for must render, or the alias map has
# drifted from the identity registry and a live send degrades to bare text.
import send_gateway  # noqa: E402
for _b in send_gateway.BRAND_IDENTITY:
    try:
        email_template._brand(_b)
    except ValueError:
        failures.append(
            f"send_gateway.BRAND_IDENTITY has {_b!r} but email_template refuses "
            f"it — a live send with that brand loses its HTML shell"
        )

# A generic operator env var must not outrank another brand's default, in ANY
# of the identity fields — the defect was in all five resolvers, not just the
# one whose symptom showed up in the From header.
for _k, _v in {
    "BRAVO_WEBSITE_URL": "https://oasisai.work",
    "BRAVO_FROM_PHONE": "+1-514-555-0100",
    "BRAVO_SIGNATURE_TAGLINE": "Founder, OASIS AI Solutions",
}.items():
    os.environ[_k] = _v

check("a global website does not leak into a client render",
      email_template._website("sunbiz"), "https://sunbizfunding.com")
check("a global phone does not leak into a client render",
      email_template._from_phone("sunbiz"), "")
check("a global tagline does not leak into a client render",
      email_template._signature_block("sunbiz"), "SunBiz Funding LLC")
# ...while still applying to this module's own brand, which is whose they are.
check("the same globals DO apply to OASIS",
      email_template._website("oasis"), "https://oasisai.work")
# A brand-scoped override outranks everything.
os.environ["BRAVO_FROM_DISPLAY_SUNBIZ"] = "Alex from SunBiz"
check("a brand-scoped override still wins",
      email_template._from_display("sunbiz"), "Alex from SunBiz")
for _k in ("BRAVO_WEBSITE_URL", "BRAVO_FROM_PHONE", "BRAVO_SIGNATURE_TAGLINE",
           "BRAVO_FROM_DISPLAY_SUNBIZ"):
    os.environ.pop(_k, None)

# Bluerise is deliberately NOT aliased: a separate legal entity may not borrow
# another's chrome. It must refuse until it has its own BRAND_CONFIG entry.
try:
    email_template._brand("bluerise")
    failures.append("bluerise silently borrowed another company's chrome")
except ValueError:
    pass


# Put the environment back before anything else in this pytest process runs.
for _k, _v in _ENV_SAVED.items():
    if _v is None:
        os.environ.pop(_k, None)
    else:
        os.environ[_k] = _v


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
    print("test_google_tool_brand.py — all assertions passed")
