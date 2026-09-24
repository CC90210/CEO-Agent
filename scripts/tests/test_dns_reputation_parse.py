"""nslookup parsing must read TXT answers on Windows AND Linux (2026-09-24).

Windows prints the TXT value on the lines AFTER `text =`; the parser read only
the marker line, so the send-gateway doctor reported SPF/DKIM/DMARC missing for
oasisai.work while all three were published.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from dns_reputation import parse_nslookup_records  # noqa: E402

WINDOWS_SPF = """Server:  one.one.one.one
Address:  1.1.1.1

Non-authoritative answer:
oasisai.work\ttext =

\t"google-site-verification=abc"
oasisai.work\ttext =

\t"v=spf1 include:_spf.google.com ~all"
"""

WINDOWS_DKIM = """google._domainkey.oasisai.work\ttext =

\t"v=DKIM1;k=rsa;p=MIIBIjANBgkq"
\t"WNZpLakIXnP4j9B1a9qy9F+ZyIDAQAB"
"""

LINUX_TXT = 'oasisai.work\ttext = "v=spf1 include:_spf.google.com ~all"\n'

WINDOWS_MX = "oasisai.work\tMX preference = 1, mail exchanger = aspmx.l.google.com\n"


def test_windows_txt_values_on_following_lines_are_read():
    assert parse_nslookup_records(WINDOWS_SPF) == [
        "google-site-verification=abc",
        "v=spf1 include:_spf.google.com ~all",
    ]


def test_windows_multi_chunk_dkim_key_is_joined():
    assert parse_nslookup_records(WINDOWS_DKIM) == [
        "v=DKIM1;k=rsa;p=MIIBIjANBgkqWNZpLakIXnP4j9B1a9qy9F+ZyIDAQAB"
    ]


def test_linux_single_line_txt_still_works():
    assert parse_nslookup_records(LINUX_TXT) == ["v=spf1 include:_spf.google.com ~all"]


def test_mx_records_unchanged():
    assert parse_nslookup_records(WINDOWS_MX) == ["aspmx.l.google.com"]


def test_nxdomain_yields_no_records():
    assert parse_nslookup_records("*** one.one.one.one can't find _dmarc.example: Non-existent domain\n") == []
