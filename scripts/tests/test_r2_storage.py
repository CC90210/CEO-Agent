"""The R2 storage surface that replaced Supabase Storage in the Python harness.

Two things are under test and both are failure-shaped:

  1. lib/r2_storage.py speaks supabase-py's dialect over R2 — key namespacing,
     RAISE-on-miss downloads, private-by-default URLs.
  2. send_gateway refuses to send when an attachment cannot be hydrated. The
     old code skipped the failed file, so a shop-out reached a funder with the
     contract missing and every log line reading "sent".

The S3 layer is faked so the suite is offline and deterministic; what is being
verified is the adapter's behaviour, not boto3's.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from lib import r2_storage  # noqa: E402
from lib.r2_storage import R2Storage, R2StorageError  # noqa: E402


class FakeS3:
    """Minimal S3 surface: a dict of key -> bytes, plus the calls we make."""

    def __init__(self, objects: dict[str, bytes] | None = None):
        self.objects = dict(objects or {})
        self.deleted: list[str] = []

    def get_object(self, Bucket, Key):  # noqa: N803 — boto3's casing
        if Key not in self.objects:
            raise RuntimeError(f"NoSuchKey: {Key}")
        return {"Body": SimpleNamespace(read=lambda: self.objects[Key])}

    def head_object(self, Bucket, Key):  # noqa: N803
        if Key not in self.objects:
            raise RuntimeError(f"404: {Key}")
        return {"ContentLength": len(self.objects[Key]), "ETag": '"abc"',
                "ContentType": "application/pdf", "Metadata": {}}

    def put_object(self, Bucket, Key, Body, **kw):  # noqa: N803
        self.objects[Key] = Body
        return {}

    def delete_object(self, Bucket, Key):  # noqa: N803
        self.deleted.append(Key)
        self.objects.pop(Key, None)
        return {}

    def list_objects_v2(self, Bucket, Prefix, Delimiter=None, MaxKeys=1000, **kw):  # noqa: N803
        contents = [{"Key": k, "Size": len(v)}
                    for k, v in sorted(self.objects.items()) if k.startswith(Prefix)]
        return {"Contents": contents[:MaxKeys], "IsTruncated": False}

    def generate_presigned_url(self, op, Params, ExpiresIn):  # noqa: N803
        return (f"https://acct.r2.cloudflarestorage.com/{Params['Bucket']}/"
                f"{Params['Key']}?X-Amz-Expires={ExpiresIn}&op={op}")


@pytest.fixture()
def r2(monkeypatch):
    """A configured adapter over FakeS3. Yields (storage, fake_s3)."""
    fake = FakeS3({
        "lead-documents/tenant-a/statement.pdf": b"%PDF-1.7 bank statement",
        "property-photos/listing/1.jpg": b"\xff\xd8jpeg",
    })
    monkeypatch.setattr(r2_storage, "_CREDS", {
        "R2_BUCKET": "oasis-storage",
        "R2_PUBLIC_BUCKET": "oasis-public",
        "CLOUDFLARE_ACCOUNT_ID": "acct", "R2_ACCESS_KEY_ID": "k",
        "R2_SECRET_ACCESS_KEY": "s",
    })
    monkeypatch.setattr(r2_storage, "_S3", fake)
    # Resolved separately from the credentials because it costs Cloudflare API
    # calls — see _public_base(). Pinned here so no test reaches the network.
    monkeypatch.setattr(r2_storage, "_PUBLIC_BASE", "https://pub-test.r2.dev")
    # PUBLIC_PREFIXES_DEFAULT is the canonical public list in etl_storage_to_r2;
    # stubbed here so the test does not exec the migration module.
    monkeypatch.setattr(r2_storage, "_ETL", SimpleNamespace(
        PUBLIC_PREFIXES_DEFAULT=frozenset({"property-photos", "tenant-assets"})))
    return R2Storage(), fake


# --------------------------------------------------------------- key namespacing

def test_key_is_supabase_bucket_slash_path(r2):
    """`<supabase-bucket>/<path>` is the contract etl_storage_to_r2 uploaded
    4,118 objects with. Get this wrong and every migrated object 404s."""
    assert r2_storage._object_key("lead-documents", "tenant-a/x.pdf") == \
        "lead-documents/tenant-a/x.pdf"
    # Leading slashes and Windows separators must not produce a different key
    # for the same object — the callers build these paths by string join.
    assert r2_storage._object_key("lead-documents", "/tenant-a/x.pdf") == \
        "lead-documents/tenant-a/x.pdf"
    assert r2_storage._object_key("lead-documents", "tenant-a\\x.pdf") == \
        "lead-documents/tenant-a/x.pdf"


def test_rewritten_absolute_url_maps_back_to_its_key(r2):
    """LIVE DATA. `etl_storage_to_r2 --apply` repointed all 3,406
    lead_documents.storage_path rows at https://pub-d5766….r2.dev/lead-documents/…
    — a domain that now 403s. The bytes never moved, so the URL still names a
    valid key; reading it from the private bucket with credentials is both the
    working path and the correct one for a bank statement."""
    storage, _ = r2
    url = ("https://pub-d5766f0ed61d4694b9fe1d65ac34f1ec.r2.dev/"
           "lead-documents/tenant-a/statement.pdf")
    assert storage.from_("lead-documents").download(url) == b"%PDF-1.7 bank statement"


def test_bucket_prefixed_path_is_not_double_prefixed(r2):
    storage, _ = r2
    assert storage.from_("lead-documents").download(
        "lead-documents/tenant-a/statement.pdf") == b"%PDF-1.7 bank statement"


def test_url_for_another_bucket_is_refused_not_guessed(r2):
    """A caller-supplied URL must not become an object key just because it is a
    URL — that would let a payload address storage it never named."""
    storage, _ = r2
    with pytest.raises(R2StorageError, match="refusing to guess"):
        storage.from_("lead-documents").download(
            "https://evil.example.com/some/other/thing.pdf")


def test_download_returns_raw_bytes(r2):
    storage, _ = r2
    got = storage.from_("lead-documents").download("tenant-a/statement.pdf")
    assert got == b"%PDF-1.7 bank statement"
    assert isinstance(got, bytes)


# ------------------------------------------------------------------- fail loud

def test_download_of_missing_object_raises_never_returns_empty(r2):
    """supabase-py raises; so does this. A soft return would let a caller
    attach zero bytes and call it a send."""
    storage, _ = r2
    with pytest.raises(R2StorageError, match="R2 download failed"):
        storage.from_("lead-documents").download("tenant-a/not-there.pdf")


def test_zero_byte_object_is_treated_as_a_failure(r2):
    storage, fake = r2
    fake.objects["lead-documents/tenant-a/empty.pdf"] = b""
    with pytest.raises(R2StorageError, match="empty"):
        storage.from_("lead-documents").download("tenant-a/empty.pdf")


def test_unconfigured_r2_raises_naming_the_missing_keys(monkeypatch):
    """The whole point of the cutover: with Supabase gone there is no fallback,
    so an unconfigured R2 must say exactly which key is absent."""
    monkeypatch.setattr(r2_storage, "_CREDS", None)
    monkeypatch.setattr(r2_storage, "_S3", None)
    monkeypatch.setattr(r2_storage, "_ETL", SimpleNamespace(
        load_env=lambda: {},
        _creds=lambda env: ({}, ["R2_ACCESS_KEY_ID", "CLOUDFLARE_ACCOUNT_ID"]),
        PUBLIC_PREFIXES_DEFAULT=frozenset()))
    with pytest.raises(R2StorageError) as exc:
        R2Storage().from_("lead-documents").download("tenant-a/x.pdf")
    assert "R2_ACCESS_KEY_ID" in str(exc.value)
    assert "CLOUDFLARE_ACCOUNT_ID" in str(exc.value)


def test_constructing_the_surface_never_touches_credentials(monkeypatch):
    """Every harness process constructs a client; only some read objects. A
    missing R2 key must not break `python scripts/anything.py`."""
    monkeypatch.setattr(r2_storage, "_CREDS", None)

    def explode():
        raise AssertionError("credentials resolved at construction time")

    monkeypatch.setattr(r2_storage, "_etl", explode)
    assert r2_storage.storage_surface().from_("lead-documents") is not None


# ------------------------------------------------------------- URL routing

def test_private_bucket_gets_a_signed_url_not_a_public_one(r2):
    """4,088 of these objects are merchant bank statements. get_public_url on a
    private prefix must never return an r2.dev address."""
    storage, _ = r2
    url = storage.from_("lead-documents").get_public_url("tenant-a/statement.pdf")
    assert "pub-test.r2.dev" not in url
    assert "X-Amz-Expires" in url


def test_public_prefix_gets_the_public_base_url(r2):
    storage, _ = r2
    url = storage.from_("property-photos").get_public_url("listing/1.jpg")
    assert url == "https://pub-test.r2.dev/property-photos/listing/1.jpg"


def test_signed_url_exposes_every_storage3_spelling(r2):
    storage, _ = r2
    res = storage.from_("lead-documents").create_signed_url("tenant-a/statement.pdf", 60)
    assert res["signedURL"] == res["signedUrl"] == res.signed_url


# ------------------------------------------------------------------- writes

def test_upload_writes_at_the_namespaced_key(r2):
    storage, fake = r2
    res = storage.from_("lead-documents").upload(
        "tenant-b/contract.pdf", b"signed", {"content-type": "application/pdf"})
    assert fake.objects["lead-documents/tenant-b/contract.pdf"] == b"signed"
    assert res["fullPath"] == "lead-documents/tenant-b/contract.pdf"


def test_upload_refuses_to_overwrite_unless_upsert(r2):
    """S3 overwrites by default; supabase-py does not. Silently replacing a
    signed contract is not a behaviour to inherit from the transport."""
    storage, _ = r2
    bucket = storage.from_("lead-documents")
    with pytest.raises(R2StorageError, match="Duplicate"):
        bucket.upload("tenant-a/statement.pdf", b"new bytes")
    bucket.upload("tenant-a/statement.pdf", b"new bytes", {"upsert": "true"})
    assert bucket.download("tenant-a/statement.pdf") == b"new bytes"


def test_list_is_not_recursive_matching_supabase(r2):
    storage, fake = r2
    fake.objects["lead-documents/tenant-a/sub/deep.pdf"] = b"x"
    names = [o["name"] for o in storage.from_("lead-documents").list("tenant-a")]
    assert names == ["statement.pdf"]


def test_remove_deletes_the_namespaced_key(r2):
    storage, fake = r2
    storage.from_("lead-documents").remove(["tenant-a/statement.pdf"])
    assert fake.deleted == ["lead-documents/tenant-a/statement.pdf"]


def test_list_buckets_refuses_rather_than_returning_empty(r2):
    storage, _ = r2
    with pytest.raises(R2StorageError, match="no R2 equivalent"):
        storage.list_buckets()


# ============================================ send_gateway all-or-nothing gate

@pytest.fixture()
def gateway(monkeypatch, r2):
    """send_gateway with its Supabase client swapped for the R2-backed one."""
    from integrations import send_gateway as sg

    storage, fake = r2
    monkeypatch.setattr(sg, "get_supabase",
                        lambda *a, **k: SimpleNamespace(storage=storage))
    return sg, fake


def _args(entries, tenant_id="tenant-a"):
    return argparse.Namespace(attachments=json.dumps(entries), tenant_id=tenant_id)


def test_attachments_hydrate_from_r2(gateway):
    sg, _ = gateway
    out = sg._resolve_cli_attachments(_args([
        {"storage_path": "tenant-a/statement.pdf", "filename": "statement.pdf",
         "mime_type": "application/pdf"}]))
    assert out == [{"filename": "statement.pdf",
                    "content": b"%PDF-1.7 bank statement",
                    "content_type": "application/pdf"}]


def test_one_missing_attachment_blocks_the_whole_send(gateway):
    """THE REGRESSION THIS FILE EXISTS FOR. Previously the unreachable file was
    logged to stderr and the other two went out — a funder receives a shop-out
    package with the bank statements missing and nothing reports a problem."""
    sg, _ = gateway
    with pytest.raises(sg.AttachmentResolutionError) as exc:
        sg._resolve_cli_attachments(_args([
            {"storage_path": "tenant-a/statement.pdf", "filename": "statement.pdf"},
            {"storage_path": "tenant-a/gone.pdf", "filename": "contract.pdf"}]))
    assert "1 of 2" in str(exc.value)
    assert "contract.pdf" in str(exc.value)


def test_every_attachment_failing_does_not_degrade_to_no_attachments(gateway):
    sg, _ = gateway
    with pytest.raises(sg.AttachmentResolutionError):
        sg._resolve_cli_attachments(_args([
            {"storage_path": "tenant-a/gone.pdf", "filename": "contract.pdf"}]))


def test_cross_tenant_path_blocks_the_send_rather_than_dropping_the_file(gateway):
    """Confused-deputy defence. Rejecting the file but sending the email would
    hide the attack AND ship an incomplete package."""
    sg, _ = gateway
    with pytest.raises(sg.AttachmentResolutionError, match="tenant prefix"):
        sg._resolve_cli_attachments(_args([
            {"storage_path": "tenant-b/statement.pdf", "filename": "x.pdf"}]))


def test_attachment_given_as_a_rewritten_url_still_passes_the_tenant_guard(gateway):
    """The dashboard reads lead_documents.storage_path, which is now a URL. The
    tenant guard must run on the path INSIDE that URL — not on "https:", which
    would report a live format change as a cross-tenant attack."""
    sg, _ = gateway
    out = sg._resolve_cli_attachments(_args([
        {"storage_path": "https://pub-d5766f0ed61d4694b9fe1d65ac34f1ec.r2.dev/"
                         "lead-documents/tenant-a/statement.pdf",
         "filename": "statement.pdf", "mime_type": "application/pdf"}]))
    assert out[0]["content"] == b"%PDF-1.7 bank statement"


def test_rewritten_url_for_another_tenant_is_still_blocked(gateway):
    """Normalizing the URL must not weaken the confused-deputy defence."""
    sg, _ = gateway
    with pytest.raises(sg.AttachmentResolutionError, match="tenant prefix"):
        sg._resolve_cli_attachments(_args([
            {"storage_path": "https://pub-d5766f0ed61d4694b9fe1d65ac34f1ec.r2.dev/"
                             "lead-documents/tenant-b/statement.pdf",
             "filename": "x.pdf"}]))


def test_malformed_attachments_json_blocks_the_send(gateway):
    sg, _ = gateway
    args = argparse.Namespace(attachments="{not json", tenant_id="tenant-a")
    with pytest.raises(sg.AttachmentResolutionError, match="not valid JSON"):
        sg._resolve_cli_attachments(args)


def test_no_attachments_flag_still_returns_none(gateway):
    sg, _ = gateway
    assert sg._resolve_cli_attachments(
        argparse.Namespace(attachments=None, tenant_id="tenant-a")) is None
