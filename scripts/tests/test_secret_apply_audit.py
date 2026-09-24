"""Authorized env writes must never create a second plaintext secret store."""
from __future__ import annotations

import json
from integrations import secret_apply_authorized as tool


def test_set_audit_record_contains_digest_and_shape_but_not_plaintext():
    secret = "super-secret-value-that-must-not-be-logged"
    record = tool._set_audit_record(
        stamp="20260923T000000Z",
        key="EXAMPLE_TOKEN",
        value=secret,
        reason="operator-approved",
    )

    rendered = json.dumps(record, sort_keys=True)
    assert secret not in rendered
    assert "value" not in record
    assert record["target"] == "EXAMPLE_TOKEN"
    assert record["shape"] == "opaque"
    assert record["value_sha256"].startswith("sha256:")


def test_config_set_output_uses_fingerprints_not_raw_values(capsys):
    current = "legacy-mode-marker"
    replacement = "modern-mode-marker"

    count, updated = tool._set_values(
        f"FEATURE_MODE={current}\n",
        [f"FEATURE_MODE={replacement}"],
        apply=True,
    )

    output = capsys.readouterr().out
    assert count == 1
    assert replacement in updated
    assert current not in output
    assert replacement not in output
    assert "sha256:" in output


def test_config_set_rejects_secret_like_replacement_without_echoing_it(capsys):
    secret = "replacement-secret-value-that-must-stay-private"

    count, updated = tool._set_values(
        "FEATURE_MODE=legacy\n",
        [f"FEATURE_MODE={secret}"],
        apply=True,
    )

    output = capsys.readouterr().out
    assert count == -1
    assert updated == "FEATURE_MODE=legacy\n"
    assert secret not in output


def test_config_set_rejects_credential_named_key_even_for_short_value(capsys):
    replacement = "short-value"

    count, updated = tool._set_values(
        "SERVICE_API_KEY=disabled\n",
        [f"SERVICE_API_KEY={replacement}"],
        apply=True,
    )

    output = capsys.readouterr().out
    assert count == -1
    assert updated == "SERVICE_API_KEY=disabled\n"
    assert replacement not in output


def test_malformed_set_argument_is_not_echoed(capsys):
    malformed = "raw-secret-like-text-without-an-equals-sign"

    count, updated = tool._set_values("FEATURE_MODE=legacy\n", [malformed], apply=True)

    output = capsys.readouterr().out
    assert count == -1
    assert updated == "FEATURE_MODE=legacy\n"
    assert malformed not in output
