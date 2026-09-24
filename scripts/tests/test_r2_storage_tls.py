"""Regression coverage for R2's TLS bootstrap boundary."""
from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from lib import r2_storage  # noqa: E402


def test_s3_bootstraps_os_trust_before_building_first_client(monkeypatch):
    """The R2 client must inherit the Windows OS trust store before TLS use."""
    events: list[str] = []
    client = object()

    class FakeEtl:
        @staticmethod
        def _client(credentials):
            events.append("client")
            assert credentials == {"synthetic": "credentials"}
            return client

    def bootstrap_trust():
        events.append("trust")

    def credentials():
        events.append("credentials")
        return {"synthetic": "credentials"}

    monkeypatch.setattr(r2_storage, "_S3", None)
    monkeypatch.setattr(r2_storage, "ensure_os_trust", bootstrap_trust, raising=False)
    monkeypatch.setattr(r2_storage, "_etl", lambda: FakeEtl())
    monkeypatch.setattr(r2_storage, "_creds", credentials)

    assert r2_storage._s3() is client
    assert events == ["trust", "credentials", "client"]

    # The cached client must not repeat bootstrap or construction work.
    assert r2_storage._s3() is client
    assert events == ["trust", "credentials", "client"]
