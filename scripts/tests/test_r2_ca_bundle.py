from __future__ import annotations

import sys
import types
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import etl_storage_to_r2 as etl  # noqa: E402


def test_r2_client_receives_file_backed_system_ca(monkeypatch, tmp_path):
    seen: dict = {}

    class Config:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    def client(service, **kwargs):
        seen["service"] = service
        seen.update(kwargs)
        return object()

    monkeypatch.setitem(sys.modules, "boto3", types.SimpleNamespace(client=client))
    monkeypatch.setitem(sys.modules, "botocore.config", types.SimpleNamespace(Config=Config))
    bundle = tmp_path / "system-ca.pem"
    bundle.write_text("test", encoding="ascii")
    monkeypatch.setattr(etl, "_r2_ca_bundle", lambda: str(bundle))

    etl._client({
        "CLOUDFLARE_ACCOUNT_ID": "acct",
        "R2_ACCESS_KEY_ID": "access",
        "R2_SECRET_ACCESS_KEY": "secret",
    })

    assert seen["service"] == "s3"
    assert seen["verify"] == str(bundle)
