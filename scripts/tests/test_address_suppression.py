"""Address-suppression legal guard + footer behavior (Codex audit 2026-06-25).

The per-send `suppress_business_address` flag removes the CASL/CAN-SPAM physical
mailing address from the email footer. That is lawful ONLY for allowlisted B2B
sources (shop-out funder submissions), never for a consumer commercial email.
These pure-logic tests lock that fail-closed invariant + the footer's
empty-address handling, without a live send.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from integrations.send_gateway import (  # noqa: E402
    _address_suppression_allowed,
    ADDRESS_SUPPRESS_ALLOWED_SOURCES,
)
from casl_compliance import build_casl_footer, build_casl_footer_html  # noqa: E402


def test_only_allowlisted_source_may_suppress():
    # Allowed: explicit True from the shop-out path (case-insensitive).
    assert _address_suppression_allowed(True, "shop_out") is True
    assert _address_suppression_allowed(True, "SHOP_OUT") is True
    # Denied: every other source, even with the flag explicitly True — a
    # consumer commercial send can NEVER drop its legal address.
    for src in ("outreach_engine", "cold_outreach", "manual_cc", "helios", "", "unknown"):
        assert _address_suppression_allowed(True, src) is False, src
    # Denied: no flag / None / False, even from the allowed source.
    assert _address_suppression_allowed(None, "shop_out") is False
    assert _address_suppression_allowed(False, "shop_out") is False


def test_allowlist_stays_narrow():
    assert "shop_out" in ADDRESS_SUPPRESS_ALLOWED_SOURCES
    for src in ("outreach_engine", "cold_outreach", "oasis", "helios"):
        assert src not in ADDRESS_SUPPRESS_ALLOWED_SOURCES, src


def test_footer_omits_empty_address_keeps_name():
    empty = build_casl_footer(
        "x@y.com", business_name="Sun Biz Funding", business_address="", sender_name="Ezra"
    )
    full = build_casl_footer(
        "x@y.com", business_name="Sun Biz Funding",
        business_address="221 W Hallandale Beach Blvd", sender_name="Ezra",
    )
    assert "221" not in empty and "Ezra" in empty and "Sun Biz Funding" in empty
    assert "221" in full  # ordinary (non-suppressed) send keeps the address
    he = build_casl_footer_html(
        "x@y.com", business_name="Sun Biz Funding", business_address="", sender_name="Ezra"
    )
    assert "221" not in he and "Ezra" in he


if __name__ == "__main__":
    test_only_allowlisted_source_may_suppress()
    test_allowlist_stays_narrow()
    test_footer_omits_empty_address_keeps_name()
    print("ok address-suppression guard + footer (3 tests)")
