"""Offline tests for scripts/integrations/wise_tool.py — request building and
masking. Nothing here touches the network or the credential store: the
network call is replaced, and credentials are a fake pair."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def tool():
    return _load("wise_tool_test", ROOT / "integrations" / "wise_tool.py")


def test_build_request_puts_token_only_in_the_header(tool):
    url, headers = tool.build_request("tok-secret-123", "/v4/profiles/42/balances", {"types": "STANDARD", "skip": None})
    assert url == "https://api.transferwise.com/v4/profiles/42/balances?types=STANDARD"
    assert "tok-secret-123" not in url
    assert headers["Authorization"] == "Bearer tok-secret-123"
    assert headers["Accept"] == "application/json"
    assert "python" not in headers["User-Agent"].lower(), "a named client, not the default Python agent"


def test_build_request_rejects_a_relative_path(tool):
    with pytest.raises(ValueError):
        tool.build_request("t", "v1/profiles")


def test_mask_value_keeps_last_four(tool):
    assert tool.mask_value("200123453111") == "****3111"
    assert tool.mask_value("BE12 3456 7890 1234") == "****1234"
    assert tool.mask_value("621") == "621", "short bank codes stay readable"


def test_sanitize_masks_account_numbers_but_not_bank_codes_or_dates(tool):
    statement_block = {
        "bankDetails": [
            {
                "accountNumbers": [{"accountType": "Account number", "accountNumber": "200123453111"}],
                "bankCodes": [
                    {"scheme": "Institution number", "value": "621"},
                    {"scheme": "Transit number", "value": "16001"},
                    {"scheme": "Swift/BIC", "value": "TRWICAW1XXX"},
                ],
                "deprecated": False,
            }
        ],
        "transactions": [
            {
                "date": "2026-09-23T19:20:08.077529Z",
                "referenceNumber": "TRANSFER-1234567890",
                "details": {"type": "DEPOSIT", "senderAccount": "(12345678901)", "recipientAccountNumber": "200123453111", "iban": "GB29 NWBK 6016 1331 9268 19"},
            }
        ],
    }
    out = tool.sanitize_details(statement_block)
    block = out["bankDetails"][0]
    assert block["accountNumbers"][0]["accountNumber"] == "****3111"
    assert block["accountNumbers"][0]["accountType"] == "Account number", "labels are not masked"
    assert [c["value"] for c in block["bankCodes"]] == ["621", "16001", "TRWICAW1XXX"]
    txn = out["transactions"][0]
    assert txn["date"] == "2026-09-23T19:20:08.077529Z", "a timestamp is not an account number"
    assert txn["referenceNumber"] == "TRANSFER-1234567890", "Wise's transaction reference stays usable"
    assert txn["details"]["recipientAccountNumber"] == "****3111"
    assert txn["details"]["senderAccount"] == "(****8901)", "an unlabelled long digit run is masked too"
    assert txn["details"]["iban"] == "****6819"
    dumped = json.dumps(out)
    assert "200123453111" not in dumped and "12345678901" not in dumped


def test_account_details_reads_the_statement_bank_block(tool, monkeypatch):
    calls = []

    def fake_get(path, params=None):
        calls.append((path, params))
        if path.endswith("/balances"):
            return [{"id": 7, "currency": "CAD"}, {"id": 8, "currency": "USD"}]
        assert path == "/v1/profiles/42/balance-statements/7/statement.json"
        assert params["currency"] == "CAD" and params["type"] == "COMPACT"
        return {
            "accountHolder": {"businessName": "OASISAI"},
            "bankDetails": [
                {"deprecated": True, "accountNumbers": [{"accountType": "Account number", "accountNumber": "999999999999"}]},
                {"deprecated": False, "accountNumbers": [{"accountType": "Account number", "accountNumber": "200123453111"}], "bankCodes": []},
            ],
        }

    monkeypatch.setattr(tool, "_credentials", lambda: ("tok", "42"))
    monkeypatch.setattr(tool, "wise_get", fake_get)
    out = tool.cmd_account_details(type("A", (), {"currency": "cad"})())
    assert out == [{"currency": "CAD", "holder": "OASISAI", "bankDetails": [{"deprecated": False, "accountNumbers": [{"accountType": "Account number", "accountNumber": "****3111"}], "bankCodes": []}]}]
    assert all(not p.startswith("http") for p, _ in calls)


def test_there_is_no_write_verb(tool):
    assert set(tool.COMMANDS) == {"profiles", "balances", "account-details", "activities", "statement"}
    src = (ROOT / "integrations" / "wise_tool.py").read_text(encoding="utf-8")
    assert "requests.post" not in src and "requests.put" not in src and "requests.delete" not in src
