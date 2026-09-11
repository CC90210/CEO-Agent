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

EVERYTHING RUNS UNDER monkeypatch. An earlier version of this file did its work
at import time, which left google_tool.smtp_send bound to the stub for the rest
of the pytest process and removed BRAVO_* variables instead of restoring them —
so it could change the result of any later suite that sends mail.
(CodeRabbit, PR #73.)

Run: python scripts/tests/test_google_tool_brand.py
"""

from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1]
for _p in (str(_SCRIPTS), str(_SCRIPTS / "integrations")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import lib.smtp_send as transport  # noqa: E402

OASIS_IDENTIFICATION = (
    "OASIS AI Solutions, 6993 Decarie Blvd, Montreal, QC H3W 0B5, Canada"
)


def _checks(mp) -> list[str]:
    """Every assertion, against a monkeypatched environment.

    Returns the list of failures. Takes `mp` rather than touching os.environ
    or module attributes directly so nothing leaks into the rest of the
    process — under pytest this module shares both with every other suite.
    """
    failures: list[str] = []
    seen: dict[str, object] = {}

    def check(label: str, got, want) -> None:
        if got != want:
            failures.append(f"{label}\n     got:  {got!r}\n     want: {want!r}")

    gt = importlib.import_module("google_tool")
    import email_template
    import send_gateway

    def stub_transport(user, pw, mime, to, timeout=30, require_from_domain=None):
        """Stub the socket, run the REAL identity guard.

        Stubbing the guard too would make this pass against a codebase with no
        guard at all — the failure mode this branch exists to fix.
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
        seen.clear()
        seen.update({
            "from": mime["From"],
            "auth": user,
            "oasis_chrome": "oasis ai solutions" in flat,
            "sunbiz_chrome": "sunbiz" in flat,
        })
        return True, None

    mp.setattr(gt, "smtp_send", stub_transport)
    mp.setenv("GMAIL_APP_PASSWORD", "stub-not-a-real-credential")

    # SET these, do not clear them. An earlier version POPPED
    # BRAVO_FROM_DISPLAY and USER_FULL_NAME "so they would not mask the brand
    # default" — manufacturing a clean host that does not exist. Every box
    # Bravo runs on has CC's operator identity in these variables, and with
    # them set the resolvers preferred them over the brand, so a SunBiz send
    # went out as "Conaugh McKenna <submissions@sunbizfunding.com>". The test
    # passed throughout; Codex found it in review.
    mp.setenv("BRAVO_FROM_DISPLAY", "Conaugh McKenna")
    mp.setenv("USER_FULL_NAME", "Conaugh McKenna")

    def send(mailbox: str, body: str = "Body text", *, branded: bool = True):
        seen.clear()
        mp.setenv("GMAIL_USER", mailbox)
        return gt.gmail_send_smtp("contact@example.com", "Subject", body,
                                  branded=branded)

    # ---- The incident shape: branded send from the client's mailbox --------
    res, err = send("submissions@sunbizfunding.com")
    check("a branded send from the client's mailbox still goes out", res is not None, True)
    check("...but carries NO OASIS chrome", seen.get("oasis_chrome"), False)
    check("...and is signed as the client", seen.get("sunbiz_chrome"), True)
    check("...with a From header on the client's own identity",
          "sunbizfunding.com" in str(seen.get("from", "")), True)
    check("...and never OASIS's name in the From header",
          "oasis" in str(seen.get("from", "")).lower(), False)
    # THE REGRESSION CODEX CAUGHT. The host-global operator name must not reach
    # a client's From header just because it is set on the sending box.
    check("...and not CC's name off a host-global either",
          "conaugh" in str(seen.get("from", "")).lower(), False)
    check("...the From display is the client's own",
          "SunBiz Submissions" in str(seen.get("from", "")), True)

    # ---- Control: the same call from the OASIS mailbox ---------------------
    res, err = send("conaugh@oasisai.work")
    check("a branded send from the OASIS mailbox goes out", res is not None, True)
    check("...and DOES carry OASIS chrome", seen.get("oasis_chrome"), True)
    check("...with an oasisai.work From header",
          "oasisai.work" in str(seen.get("from", "")), True)

    # A rep's own mailbox on an entitled domain resolves by domain, not roster.
    res, err = send("rep.example@sunbizfunding.com")
    check("a rep's own address on the sending domain resolves", res is not None, True)
    check("...to the client's brand, not OASIS", seen.get("oasis_chrome"), False)

    # ---- An unregistered mailbox must refuse, not guess --------------------
    res, err = send("someone@randomdomain.example")
    check("an unregistered mailbox refuses rather than defaulting to OASIS",
          res is None, True)
    check("...and the refusal names the mailbox",
          "randomdomain.example" in (err or ""), True)
    check("...and says how to fix it",
          "BRAND_SENDING_DOMAIN" in (err or ""), True)

    # ---- The transport guard still backstops an identification block -------
    # Belt and braces: the brand fix stops the CHROME, this stops a body that
    # carries another company's legal identification whatever the chrome says.
    res, err = send("submissions@sunbizfunding.com",
                    f"Hi,\n\n{OASIS_IDENTIFICATION}", branded=False)
    check("an OASIS identification block from the client's mailbox is refused",
          res is None, True)
    check("...by the identity guard specifically", "identity guard" in (err or ""), True)

    # ---- A brand with no configured identity must FAIL CLOSED --------------
    # bluerise has a registered sending domain but no BRAND_CONFIG entry, so
    # _from_display raises. The first version of _brand_from_display caught
    # ANY exception and returned "Conaugh McKenna", which put CC's name on a
    # separate company's mailbox — the leak, reintroduced through an except
    # branch, and invisible to the transport guard because a From header
    # carries no postal address. (CodeRabbit, PR #73.)
    check("a brand with no configured identity returns None, not the operator default",
          gt._brand_from_display("bluerise"), None)
    check("...and CC's own brands still resolve",
          gt._brand_from_display("oasis"), "Conaugh McKenna")
    for _alias in ("conaugh_mckenna", "nostalgic"):
        check(f"...including the alias {_alias}",
              gt._brand_from_display(_alias), "Conaugh McKenna")
    check("a client brand resolves to the client, never the operator",
          gt._brand_from_display("sunbiz"), "SunBiz Submissions")

    # ---- THE FIFTH DOOR: the --plain path, over the Gmail API -------------
    # `gmail send` routes branded sends to SMTP and --plain sends through
    # _encode_email to the external gws CLI. That path never touches
    # lib.smtp_send, so the transport guard cannot see it, and the chokepoint
    # test cannot either (it enforces "only smtp_send imports smtplib", and
    # this is not smtplib). It used to hardcode `From: Conaugh McKenna
    # <{GMAIL_USER}>`, so on the SunBiz VPS it signed CC's name on the
    # client's mailbox. Getting the From header right here is the whole of
    # this path's protection.
    import base64
    import email as _email

    def plain_from(mailbox: str):
        # `sender` is the gws-authenticated account, passed explicitly: the
        # encoder no longer reads GMAIL_USER at all.
        raw = gt._encode_email("contact@example.com", "Subject", "Body",
                               sender=mailbox)
        return _email.message_from_bytes(base64.urlsafe_b64decode(raw))["from"]

    check("the --plain path signs as the client from the client's mailbox",
          plain_from("submissions@sunbizfunding.com"),
          "SunBiz Submissions <submissions@sunbizfunding.com>")
    check("...and never as CC, whose name is set host-globally right now",
          "conaugh" in plain_from("submissions@sunbizfunding.com").lower(), False)
    check("...a rep's own address resolves by domain",
          plain_from("rep.example@sunbizfunding.com"),
          "SunBiz Submissions <rep.example@sunbizfunding.com>")
    check("...and CC's own mailbox still signs as CC",
          plain_from("conaugh@oasisai.work"),
          "Conaugh McKenna <conaugh@oasisai.work>")

    for _bad, _why in (("ops@bluerisebusinesscapital.com", "no configured sending identity"),
                       ("someone@unknown.example", "no brand is registered")):
        try:
            plain_from(_bad)
            failures.append(f"the --plain path sent under a guessed identity for {_bad}")
        except ValueError as _exc:
            check(f"the --plain path refuses {_bad}", _why in str(_exc), True)

    # ---- Codex, PR #73: the identity comes from the account that SENDS -----
    # gws sends as its own OAuth login. Taking the From from GMAIL_USER let a
    # SunBiz From ride on an OASIS-authenticated send (or the reverse) whenever
    # the two credentials disagreed. Drive gmail_send itself, with gws faked,
    # through exactly that disagreement in both directions.
    import json as _json
    import types as _types
    sent_raw: list[str] = []

    def fake_gws(profile_addr=None, profile_err=None):
        def _run(args_list, timeout=30):
            if args_list[:3] == ["gmail", "users", "getProfile"]:
                if profile_err:
                    return None, profile_err
                return {"emailAddress": profile_addr}, None
            if args_list[:4] == ["gmail", "users", "messages", "send"]:
                payload = _json.loads(args_list[args_list.index("--json") + 1])
                sent_raw.append(payload["raw"])
                return {"id": "fake-message-id"}, None
            return None, f"unexpected gws call {args_list[:4]}"
        return _run

    def plain_send():
        sent_raw.clear()
        seen.clear()
        args = _types.SimpleNamespace(
            to="contact@example.com", subject="Subject", body="Body",
            branded=False, plain=True, cta_label=None, cta_url=None,
            json_output=True)
        try:
            gt.gmail_send(args)
            return None
        except SystemExit as exc:
            return exc.code

    def sent_from():
        return _email.message_from_bytes(base64.urlsafe_b64decode(sent_raw[0]))["from"]

    # gws logged in as OASIS while GMAIL_USER names the SunBiz mailbox.
    mp.setenv("GMAIL_USER", "submissions@sunbizfunding.com")
    mp.setattr(gt, "run_gws", fake_gws(profile_addr="conaugh@oasisai.work"))
    code = plain_send()
    check("a --plain send with gws authenticated as OASIS goes out", code, None)
    check("...through gws, exactly once", len(sent_raw), 1)
    if sent_raw:
        check("...with the From of the account that actually SENDS",
              sent_from(), "Conaugh McKenna <conaugh@oasisai.work>")
        check("...and never the SunBiz identity GMAIL_USER names",
              "sunbiz" in sent_from().lower(), False)

    # The mirror: gws logged in as SunBiz while GMAIL_USER names OASIS.
    mp.setenv("GMAIL_USER", "conaugh@oasisai.work")
    mp.setattr(gt, "run_gws", fake_gws(profile_addr="submissions@sunbizfunding.com"))
    code = plain_send()
    check("gws authenticated as SunBiz goes out", code, None)
    if sent_raw:
        check("...as SunBiz, whatever GMAIL_USER says",
              sent_from(), "SunBiz Submissions <submissions@sunbizfunding.com>")
    else:
        failures.append("gws authenticated as SunBiz produced no gws send")

    # gws cannot say who it is: skip gws entirely and fall back to SMTP, which
    # authenticates AS GMAIL_USER — consistent by construction.
    mp.setenv("GMAIL_USER", "submissions@sunbizfunding.com")
    mp.setattr(gt, "run_gws", fake_gws(profile_err="AUTH_EXPIRED"))
    code = plain_send()
    check("an unknown gws identity never sends through gws", len(sent_raw), 0)
    check("...it falls back to SMTP, authenticated as GMAIL_USER",
          seen.get("auth"), "submissions@sunbizfunding.com")
    check("...and the fallback goes out", code, None)

    # gws authenticated as an account with no registered brand: refuse, and do
    # NOT silently switch to a different sending account over SMTP.
    mp.setattr(gt, "run_gws", fake_gws(profile_addr="someone@unknown.example"))
    code = plain_send()
    check("an unregistered gws account refuses", code, 1)
    check("...without a gws send", len(sent_raw), 0)
    check("...and without quietly switching accounts over SMTP",
          seen.get("auth"), None)

    # ---- The template registry must refuse an unknown brand ---------------
    # The last of the fail-open family named in the root-cause assessment:
    # email_template returned the OASIS config for ANY unrecognised string.
    try:
        email_template._brand("sunbiz-funding")  # a plausible typo of a real brand
        failures.append("email_template._brand('sunbiz-funding') fell back instead of raising")
    except ValueError as exc:
        check("an unknown brand names the known ones", "oasis" in str(exc), True)

    check("an ABSENT brand still resolves to this module's own",
          email_template._brand(None) is email_template.BRAND_CONFIG["oasis"], True)
    check("a known brand resolves to itself",
          email_template._brand("sunbiz") is email_template.BRAND_CONFIG["sunbiz"], True)

    # The aliases are the reason refusing is safe. conaugh_mckenna and
    # nostalgic are live brands in send_gateway.BRAND_IDENTITY and in
    # email_engine's --brand choices; before the alias map they reached OASIS
    # chrome via the fail-open, so refusing without listing them would have
    # stripped their shell silently through send_gateway's except-branch.
    for _alias in ("conaugh_mckenna", "nostalgic"):
        check(f"{_alias} still renders OASIS chrome (it is the same legal entity)",
              email_template._brand(_alias) is email_template.BRAND_CONFIG["oasis"], True)

    # Every brand send_gateway can be asked for must render, or the alias map
    # has drifted from the identity registry and a live send loses its shell.
    for _b in send_gateway.BRAND_IDENTITY:
        try:
            email_template._brand(_b)
        except ValueError:
            failures.append(
                f"send_gateway.BRAND_IDENTITY has {_b!r} but email_template "
                f"refuses it — a live send with that brand loses its HTML shell"
            )

    # ---- A generic operator var must not outrank another brand's default ---
    # The defect was in all five resolvers, not just the one whose symptom
    # showed up in the From header.
    mp.setenv("BRAVO_WEBSITE_URL", "https://oasisai.work")
    mp.setenv("BRAVO_FROM_PHONE", "+1-514-555-0100")
    mp.setenv("BRAVO_SIGNATURE_TAGLINE", "Founder, OASIS AI Solutions")

    check("a global website does not leak into a client render",
          email_template._website("sunbiz"), "https://sunbizfunding.com")
    check("a global phone does not leak into a client render",
          email_template._from_phone("sunbiz"), "")
    check("a global tagline does not leak into a client render",
          email_template._signature_block("sunbiz"), "SunBiz Funding LLC")
    # ...while still applying to this module's own brand, which is whose they are.
    check("the same globals DO apply to OASIS",
          email_template._website("oasis"), "https://oasisai.work")

    # An ALIASED brand is the own brand, so CC's generics must still reach it.
    # conaugh_mckenna and nostalgic are his personal sending identities on the
    # same legal entity; comparing the raw name against the own brand would
    # have quietly stopped BRAVO_FROM_DISPLAY applying to them while still
    # applying to "oasis" — a difference nobody would notice until a signature
    # looked wrong.
    mp.setenv("BRAVO_FROM_DISPLAY", "CC")
    for _own in ("oasis", "conaugh_mckenna", "nostalgic"):
        check(f"a generic operator override still reaches {_own}",
              email_template._from_display(_own), "CC")
    check("...but never reaches the client's brand",
          email_template._from_display("sunbiz"), "SunBiz Submissions")

    # A brand-scoped override outranks the generic, on an aliased brand too.
    mp.setenv("BRAVO_FROM_DISPLAY_NOSTALGIC", "Nostalgic Desk")
    check("a scoped override wins on an aliased brand too",
          email_template._from_display("nostalgic"), "Nostalgic Desk")

    # Bluerise is deliberately NOT aliased: a separate legal entity may not
    # borrow another's chrome. It must refuse until it has its own entry.
    try:
        email_template._brand("bluerise")
        failures.append("bluerise silently borrowed another company's chrome")
    except ValueError:
        pass

    return failures


def test_brand_follows_the_mailbox(monkeypatch) -> None:
    """The pytest entry point.

    monkeypatch restores every env var and the patched google_tool.smtp_send
    when the test ends, so nothing here can change another suite's result.
    """
    failures = _checks(monkeypatch)
    assert not failures, (
        f"{len(failures)} assertion(s) failed:\n\n  - " + "\n  - ".join(failures)
    )


if __name__ == "__main__":
    import pytest

    with pytest.MonkeyPatch.context() as _mp:
        _failures = _checks(_mp)
    if _failures:
        print(f"FAIL — {len(_failures)} assertion(s):\n")
        for _f in _failures:
            print(f"  - {_f}")
        sys.exit(1)
    print("test_google_tool_brand.py — all assertions passed")
