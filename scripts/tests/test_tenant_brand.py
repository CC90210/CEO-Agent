"""
test_tenant_brand.py — the cross-company identity boundary, asserted.

Every case here corresponds to something that actually happened or was
reachable in production on 2026-09-09:

  * an OASIS-branded email reaching a SunBiz operation (client-reported)
  * tenant oasis-ai-cc sending as 'sunbiz'  (1 row, 2026-07-10, in the ledger)
  * tenant submissions sending as 'oasis'   (1 row, 2026-08-01, in the ledger)
  * a caller passing tenant_id and omitting brand, silently becoming OASIS
    because the parameter defaulted to DEFAULT_BRAND (email_draft_action)
  * a caller passing a SunBiz tenant_id AND brand="oasis" in the same call
    (email_brain.py:687)

Run: python scripts/tests/test_tenant_brand.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.tenant_brand import (  # noqa: E402
    MAILBOX_TENANT,
    SLUG_BRAND,
    TENANT_BRAND,
    brand_matches_tenant,
    resolve_brand_for_tenant,
    resolve_tenant_for_mailbox,
)

SUNBIZ = "aa04fa1f-ad6a-44b0-ac4b-2ff5d1067110"
OASIS = "ef8d389e-3f15-43f2-ae00-3660f69a1452"
# A real self-signup tenant. Named "OASIS AI" in the tenants table because that
# is the default display name at signup — which is exactly why the display name
# must never be used to infer a sending identity.
YOGA_TANTRIC = "481c4d9b-c3b1-47e1-adef-c16dcd0e111f"

failures: list[str] = []


def check(label: str, got, want) -> None:
    if got != want:
        failures.append(f"{label}\n     got:  {got!r}\n     want: {want!r}")


# ---- resolution ------------------------------------------------------------
check("SunBiz tenant resolves to sunbiz", resolve_brand_for_tenant(SUNBIZ), "sunbiz")
check("OASIS tenant resolves to oasis", resolve_brand_for_tenant(OASIS), "oasis")

# The whole point of failing closed: an unmapped tenant has NO brand. If this
# ever returns a string, a third party's signup account starts sending
# commercial mail under one of CC's legal identities.
check("unmapped tenant resolves to None", resolve_brand_for_tenant(YOGA_TANTRIC), None)
check("no tenant at all resolves to None", resolve_brand_for_tenant(None), None)
check("empty string resolves to None", resolve_brand_for_tenant(""), None)
check("garbage resolves to None", resolve_brand_for_tenant("not-a-uuid"), None)

# Slug fallback, and the near-miss that must NOT match.
check("slug submissions -> sunbiz", resolve_brand_for_tenant(None, "submissions"), "sunbiz")
check("profile slug sun -> sunbiz", resolve_brand_for_tenant(None, "sun"), "sunbiz")
check("slug oasis-ai-cc -> oasis", resolve_brand_for_tenant(None, "oasis-ai-cc"), "oasis")
# "submissions-5f63d7e6" is a DIFFERENT company that merely starts with the same
# characters as SunBiz's slug. A prefix match here would hand a stranger's
# signup account the client's sending identity.
check(
    "submissions-5f63d7e6 is NOT SunBiz",
    resolve_brand_for_tenant(None, "submissions-5f63d7e6"),
    None,
)
# A SUPPLIED but unmapped id must NOT fall through to the slug. The first
# version did, so (stranger's tenant, slug "submissions") answered "sunbiz" —
# reopening the hole one layer down. (Codex, adversarial review, 2026-09-09.)
check(
    "unmapped id does not borrow the slug's brand",
    resolve_brand_for_tenant(YOGA_TANTRIC, "submissions"),
    None,
)
# An id and a slug naming DIFFERENT companies refuse rather than picking one.
check(
    "id/slug disagreement refuses",
    resolve_brand_for_tenant(OASIS, "submissions"),
    None,
)
# Agreeing id + slug still resolve.
check("id and slug agreeing resolves", resolve_brand_for_tenant(OASIS, "oasis-ai-cc"), "oasis")
check("id alone still resolves", resolve_brand_for_tenant(OASIS), "oasis")


# ---- disagreement detection ------------------------------------------------
ok, _ = brand_matches_tenant("sunbiz", SUNBIZ)
check("sunbiz brand on SunBiz tenant is allowed", ok, True)
ok, _ = brand_matches_tenant("oasis", OASIS)
check("oasis brand on OASIS tenant is allowed", ok, True)

# The two rows that are actually in the ledger.
ok, why = brand_matches_tenant("sunbiz", OASIS)
check("sunbiz brand on OASIS tenant is REFUSED (ledger 2026-07-10)", ok, False)
check("...and the reason names the real brand", "oasis" in why, True)

ok, _ = brand_matches_tenant("oasis", SUNBIZ)
check("oasis brand on SunBiz tenant is REFUSED (ledger 2026-08-01)", ok, False)

# email_brain.py:687 shape — SunBiz tenant, brand hardcoded to "oasis".
ok, _ = brand_matches_tenant("oasis", SUNBIZ)
check("email_brain hardcoded-oasis on a SunBiz lead is REFUSED", ok, False)

# Case and whitespace must not launder a mismatch.
ok, _ = brand_matches_tenant("  OASIS  ", SUNBIZ)
check("case/space does not launder a mismatch", ok, False)

# An absent brand is not a disagreement — send() derives it instead.
ok, _ = brand_matches_tenant(None, SUNBIZ)
check("absent brand is not a disagreement", ok, True)
# An unknown tenant has nothing to contradict; the refusal for that case is
# send()'s policy, not this function's job.
ok, _ = brand_matches_tenant("oasis", YOGA_TANTRIC)
check("unknown tenant cannot contradict", ok, True)


# ---- mailbox -> tenant -----------------------------------------------------
# The inbound sweep binds to ONE credential, so the mailbox is the company.
check(
    "OASIS mailbox -> OASIS tenant",
    resolve_tenant_for_mailbox("conaugh@oasisai.work"),
    OASIS,
)
check(
    "SunBiz mailbox -> SunBiz tenant",
    resolve_tenant_for_mailbox("submissions@sunbizfunding.com"),
    SUNBIZ,
)
check(
    "display-name form is unwrapped",
    resolve_tenant_for_mailbox("OASIS AI <conaugh@oasisai.work>"),
    OASIS,
)
check(
    "case is normalised",
    resolve_tenant_for_mailbox("Conaugh@OasisAI.Work"),
    OASIS,
)
# An unmapped mailbox must NOT resolve. This is the hardcoded-None case that
# left every autonomous reply brandless, and therefore OASIS by default.
check("unknown mailbox -> None", resolve_tenant_for_mailbox("someone@elsewhere.com"), None)
check("empty mailbox -> None", resolve_tenant_for_mailbox(""), None)
check("None mailbox -> None", resolve_tenant_for_mailbox(None), None)

# Every mailbox must point at a tenant that itself has a brand, or the chain
# mailbox -> tenant -> brand breaks silently at the last hop.
for addr, tid in MAILBOX_TENANT.items():
    check(f"mailbox {addr} maps to a branded tenant", resolve_brand_for_tenant(tid) is not None, True)


# ---- registry coherence ----------------------------------------------------
# ONE vocabulary, not two. send_gateway.BRAND_IDENTITY is the authority for
# which brands exist; this module deliberately keeps no local list, because a
# second list is how the original defect happened (three registries whose key
# spaces disagreed, so a name valid in one became another company in the next).
try:
    from integrations.send_gateway import BRAND_IDENTITY  # noqa: E402

    for tid, brand in TENANT_BRAND.items():
        check(f"TENANT_BRAND[{tid}] -> '{brand}' is a brand send_gateway knows",
              brand in BRAND_IDENTITY, True)
    for slug, brand in SLUG_BRAND.items():
        check(f"SLUG_BRAND[{slug}] -> '{brand}' is a brand send_gateway knows",
              brand in BRAND_IDENTITY, True)
except Exception as exc:  # noqa: BLE001
    failures.append(f"could not import send_gateway.BRAND_IDENTITY: {exc}")


# ---- send() policy ---------------------------------------------------------
# The resolver only reports disagreement; send() decides what to do about it.
# These assert the DECISION, which is the part a caller actually feels. Each
# case returns before any database or SMTP work, so no fixture is needed.
try:
    from integrations.send_gateway import send  # noqa: E402

    def send_probe(**kw):
        base = dict(
            channel="email",
            agent_source="test_tenant_brand",
            to_email="probe@example.org",
            subject="probe",
            body_text="probe",
            dry_run=True,
        )
        base.update(kw)
        return send(**base)

    # The email_brain.py:687 shape — a SunBiz tenant with brand hardcoded to
    # "oasis" — must be refused, not sent.
    r = send_probe(tenant_id=SUNBIZ, brand="oasis")
    check("send() refuses oasis-brand on a SunBiz tenant", r.get("status"), "error")
    check(
        "...and says why",
        "mismatch" in str(r.get("reason", "")).lower(),
        True,
    )

    # The 2026-07-10 ledger row, inverted.
    r = send_probe(tenant_id=OASIS, brand="sunbiz")
    check("send() refuses sunbiz-brand on an OASIS tenant", r.get("status"), "error")

    # A commercial message with no brand and an unmapped tenant has no honest
    # sender identity. Refuse rather than pick a company.
    r = send_probe(tenant_id=YOGA_TANTRIC)
    check(
        "send() refuses a commercial send it cannot attribute",
        r.get("status"),
        "error",
    )
    check(
        "...and names the missing identity, not some unrelated gate",
        "legal sender identity" in str(r.get("reason", "")),
        True,
    )

    # Derivation must WORK, or the gate is just an outage. A SunBiz tenant with
    # no brand should get past brand resolution entirely — it fails later, on a
    # different gate, which is what proves resolution succeeded.
    r = send_probe(tenant_id=SUNBIZ)
    reason = str(r.get("reason", ""))
    check(
        "send() derives the brand from a mapped tenant instead of refusing",
        ("legal sender identity" not in reason) and ("mismatch" not in reason),
        True,
    )

    # A correct explicit pairing must keep working.
    r = send_probe(tenant_id=OASIS, brand="oasis")
    reason = str(r.get("reason", ""))
    check(
        "send() still accepts a correct explicit pairing",
        ("legal sender identity" not in reason) and ("mismatch" not in reason),
        True,
    )
except Exception as exc:  # noqa: BLE001
    # ANNOUNCED SKIP, not a silent pass and not a failure.
    #
    # Importing send_gateway constructs a database client, so this section needs
    # live credentials and network. A reviewer on a restricted box cannot run it
    # (Codex hit exactly this on 2026-09-09), and failing there would make the
    # suite red for a reason that has nothing to do with the code under test.
    #
    # The resolver assertions above are pure and always run; only the
    # send()-level POLICY probe is skipped. Printed loudly so a green run never
    # implies this was checked.
    print(
        f"\n!! SKIPPED the send() policy probe — {type(exc).__name__}: {exc}\n"
        "   (needs DB credentials; the pure resolver assertions above still ran).\n"
        "   The refusal behaviour it covers is NOT verified in this run.\n"
    )


# ---- report ----------------------------------------------------------------
if failures:
    print(f"FAIL — {len(failures)} assertion(s):\n")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("test_tenant_brand.py — all assertions passed")
