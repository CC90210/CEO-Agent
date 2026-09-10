"""
test_smtp_identity_guard.py — a message may not claim one company's identity
while being sent from another's mailbox.

THE INCIDENT THIS EXISTS FOR. On 2026-09-09 a SunBiz contact received
OASIS-branded mail from their own mailbox. A brand/mailbox guard was added to
send_gateway.send() and did NOT fire, because dashboard_email_consumer never
calls send_gateway — its own header says it "queues operator-composed lead
emails straight to lib.smtp_send, bypassing send_gateway".

Six OASIS-tenant rows had already gone out from submissions@sunbizfunding.com
on that path (2026-08-17T17:13:31Z, 17:13:49Z, 21:12:07Z, 21:58:12Z,
2026-09-09T15:01:19Z, 22:53:56Z), the last two being the messages the client
screenshotted.

lib/smtp_send is the ONLY module both paths share, which is why the guard lives
there and why these tests exercise it directly rather than through a caller.

Run: python scripts/tests/test_smtp_identity_guard.py
"""

from __future__ import annotations

import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.smtp_send import _identity_conflict  # noqa: E402

OASIS_FOOTER = (
    "\n\n---\nOASIS AI Solutions\n6993 Decarie Blvd\nMontreal, QC H3W 0B5, Canada\n\n"
    "You received this email because we reached out about your business. "
    "To stop receiving emails, reply UNSUBSCRIBE."
)
SUNBIZ_FOOTER = (
    "\n\n---\nSunBiz Funding LLC\n221 W Hallandale Beach Blvd, Suite 518\n"
    "Hallandale, FL 33009\n\n"
    "You received this email because you submitted a funding inquiry. "
    "To stop receiving emails, reply UNSUBSCRIBE."
)

failures: list[str] = []


def check(label: str, got, want) -> None:
    if got != want:
        failures.append(f"{label}\n     got:  {got!r}\n     want: {want!r}")


def msg(text: str, html: str | None = None) -> MIMEMultipart:
    m = MIMEMultipart("alternative")
    m["Subject"] = "probe"
    m.attach(MIMEText(text, "plain", "utf-8"))
    if html:
        m.attach(MIMEText(html, "html", "utf-8"))
    return m


# ---- THE INCIDENT, reduced to one assertion -------------------------------
conflict = _identity_conflict(
    msg("Hi Mac,\n\nThanks for taking my call." + OASIS_FOOTER),
    "submissions@sunbizfunding.com",
)
check("OASIS-identified mail from the client's mailbox is REFUSED", conflict is not None, True)
check("...and the reason names the entitled domain", "oasisai.work" in (conflict or ""), True)

# The mirror image: SunBiz identification out of the OASIS mailbox.
conflict = _identity_conflict(msg("Hi,\n\nAbout your application." + SUNBIZ_FOOTER),
                              "conaugh@oasisai.work")
check("SunBiz-identified mail from the OASIS mailbox is REFUSED", conflict is not None, True)

# ---- Correct pairings must pass, or the guard is just an outage -----------
check("OASIS mail from the OASIS mailbox",
      _identity_conflict(msg("Hi." + OASIS_FOOTER), "conaugh@oasisai.work"), None)
check("SunBiz mail from the SunBiz mailbox",
      _identity_conflict(msg("Hi." + SUNBIZ_FOOTER), "submissions@sunbizfunding.com"), None)
# A rep's own address on the sending domain, not just the shared mailbox.
# Synthetic on purpose: a real employee address does not belong in a test file
# that ships in the repo. (CodeRabbit, PR #72.)
check("SunBiz mail from a rep's own SunBiz address",
      _identity_conflict(msg("Hi." + SUNBIZ_FOOTER), "rep.example@sunbizfunding.com"), None)
# Bluerise shares SunBiz's premises by agreement, so either domain may carry it.
check("the shared Hallandale address from the Bluerise domain",
      _identity_conflict(msg("Hi." + SUNBIZ_FOOTER),
                         "submissions@bluerisebusinesscapital.com"), None)
# A subdomain of an entitled domain is still entitled.
check("subdomain of the sending domain",
      _identity_conflict(msg("Hi." + OASIS_FOOTER), "bot@mail.oasisai.work"), None)

# ---- The HTML part alone must be enough -----------------------------------
# The branded shell puts the identification in the markup; a guard that read
# only text/plain would be blind on exactly the path that produced the incident.
html_only = _identity_conflict(
    msg("plain body with no identification",
        "<p>Hi Mac,</p><div>OASIS AI Solutions, 6993 Decarie Blvd, Montreal, QC H3W 0B5, Canada</div>"),
    "submissions@sunbizfunding.com",
)
check("an identification present ONLY in the HTML part is caught", html_only is not None, True)

# ---- MARKUP MUST NOT HIDE THE IDENTIFICATION ------------------------------
# A raw substring match over HTML is trivially defeated by ordinary markup:
# every shape below renders as the identification a human reads, and none of
# them contains the literal "6993 decarie blvd". A guard a template change can
# step around is not a guard. (CodeRabbit, PR #72.)
for label, markup in [
    ("non-breaking spaces", "OASIS AI Solutions, 6993&nbsp;Decarie&nbsp;Blvd, Montreal"),
    ("a span mid-address", "OASIS AI Solutions, 6993 <span>Decarie</span> Blvd, Montreal"),
    ("a line break", "OASIS AI Solutions,<br>6993 Decarie<br />Blvd, Montreal"),
    ("a tag splitting a word", "6993 Deca<b>rie</b> Blvd, Montreal"),
    ("an anchor around it", '<a href="#">6993 Decarie Blvd</a>, Montreal'),
    ("collapsed whitespace", "6993\n\n   Decarie\t Blvd, Montreal"),
    ("HTML entity encoding", "6993 Decarie&#32;Blvd, Montreal"),
]:
    got = _identity_conflict(
        msg("plain body with no identification", f"<div>{markup}</div>"),
        "submissions@sunbizfunding.com",
    )
    check(f"markup cannot hide the identification — {label}", got is not None, True)

# ---- What must NOT be refused ---------------------------------------------
# No identification block at all — internal and transactional mail that never
# claims a company. Refusing these would break ops alerting for no benefit.
check("a message with no identification block is not a conflict",
      _identity_conflict(msg("Heads up: the cron failed."), "submissions@sunbizfunding.com"), None)
# A passing MENTION of another company is prose, not a claim. This is why the
# guard keys on the postal address and not the company name.
check("merely naming another company is not a claim",
      _identity_conflict(
          msg("We also work with Bluerise Business Capital on some files." + SUNBIZ_FOOTER),
          "submissions@sunbizfunding.com"),
      None)
check("naming OASIS in SunBiz prose is not a claim",
      _identity_conflict(
          msg("Our partner OASIS AI Solutions built the portal." + SUNBIZ_FOOTER),
          "submissions@sunbizfunding.com"),
      None)
# Case and spacing in the message must not launder a mismatch.
check("uppercase identification is still caught",
      _identity_conflict(msg("HI." + OASIS_FOOTER.upper()), "submissions@sunbizfunding.com")
      is not None, True)
# A malformed mailbox is the credential guard's problem, not this one.
check("malformed mailbox defers to the credential guard",
      _identity_conflict(msg("Hi." + OASIS_FOOTER), "not-an-address"), None)

if failures:
    print(f"FAIL — {len(failures)} assertion(s):\n")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("test_smtp_identity_guard.py — all assertions passed")
