"""marketing_publish_drain — turn queued publish intents into published posts.

WHY THIS EXISTS AND WHY IT LIVES HERE
CC, 2026-08-14: "I should be able to click on one of these videos and then
manually post it to all the social media channels via our API key that we have
connected."

The Command Center runs on Vercel and cannot do that itself. The only sanctioned
publisher is CMO-Agent/scripts/publishers/base.publish(): Python, runs
send_gateway FIRST (killswitch, daily caps, audit trail), and needs credentials
that live on this machine. The dashboard therefore records INTENT in
`marketing_publish_intent`, and this drains it.

The tempting alternative — have the Next route call Zernio's HTTP API directly —
skips the killswitch, the caps and the audit row (late_adapter's own docstring
calls that a bug) and forks per-platform knowledge that took real failures to
learn: Instagram video must declare contentType: reel, YouTube needs a <=95-char
title. Tried by hand first; Zernio answered "Instagram posts require media
content". That is what a second, thinner publisher looks like on day one.

SAFETY
  * Claims each intent with a guarded UPDATE (queued -> running) and checks the
    row actually changed before doing anything. Two overlapping drains must not
    both publish the same asset — there is no unsending.
  * send_gateway still runs inside publish(); this never bypasses it.
  * A failure is recorded with its reason, never swallowed.

USAGE
  python scripts/marketing_publish_drain.py            # drain everything queued
  python scripts/marketing_publish_drain.py --dry-run  # claim nothing, show work
  python scripts/marketing_publish_drain.py --once     # at most one intent
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import tempfile
import traceback
from datetime import datetime, timezone

HERE = pathlib.Path(__file__).resolve().parent
BRAVO = HERE.parent
CMO = pathlib.Path(os.environ.get("CMO_REPO", r"C:\Users\User\CMO-Agent"))

sys.path.insert(0, str(HERE))

from lib import secret_loader, r2_storage  # noqa: E402
from integrations import supabase_tool  # noqa: E402


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _db():
    """The same client every other Bravo integration uses.

    supabase_tool.get_client routes through the Turso compat shim, so this drain
    reads and writes exactly what the Command Center does — no second data path.
    """
    return supabase_tool.get_client(secret_loader.bootstrap(), project="bravo")


# ── the publisher, imported with Bravo's credentials in the environment ──────
def _load_publisher():
    """Import CMO-Agent's publisher with the ledger credentials it needs.

    send_gateway.get_supabase() looks for MAVEN_* then BRAVO_* in its own
    .env.agents and then os.environ (send_gateway.py:225-234). CMO-Agent's env
    has neither, so the gateway could not query the interaction ledger and
    refused every publish. Bravo holds the BRAVO_* pair, so put them in the
    process environment before the import.

    Nothing is written to disk or logged — the same "invoke, never copy" borrow
    CMO-Agent/scripts/publish_to_library.py documents for R2.
    """
    for key in ("BRAVO_SUPABASE_URL", "BRAVO_SUPABASE_SERVICE_ROLE_KEY",
                "LATE_API_KEY", "TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN",
                "EMPIRE_DATA_BACKEND"):
        val = secret_loader.get(key)
        if val and not os.environ.get(key):
            os.environ[key] = val

    if not (CMO / "scripts" / "publishers" / "base.py").exists():
        raise SystemExit(
            f"no publisher at {CMO}. Set CMO_REPO to CMO-Agent's path — this drain "
            f"deliberately has no publishing code of its own."
        )
    sys.path.insert(0, str(CMO / "scripts"))
    from publishers.base import PublishRequest, publish   # noqa: E402
    import publishers.late_adapter                        # noqa: E402,F401
    return PublishRequest, publish


# LinkedIn takes a different register from the short-form networks — the same
# split CMO-Agent/scripts/schedule_posts.py makes (SHORT_FORM vs its own post).
SHORT_FORM = {"instagram", "tiktok", "youtube", "twitter", "threads"}


def caption_for(asset: dict, professional: bool) -> str:
    """Build the caption from the copy Maven already wrote for the asset.

    Never invents copy. If Maven left the fields empty the title is the honest
    fallback — a publisher is not the place to start writing brand voice.
    """
    hook = (asset.get("hook") or "").strip()
    body = (asset.get("body") or "").strip()
    cta = (asset.get("cta") or "").strip()
    landing = (asset.get("landing_url") or "").strip()

    parts = []
    if professional:
        # LinkedIn: lead with the argument, not the hook line.
        if body:
            parts.append(body)
        elif hook:
            parts.append(hook)
    else:
        if hook:
            parts.append(hook)
        if body:
            parts.append(body)
    if not parts:
        parts.append(asset.get("title") or "")
    if cta and landing:
        parts.append(f"{cta[:1].upper()}{cta[1:]} → {landing}")
    elif landing:
        parts.append(landing)
    return "\n\n".join(p for p in parts if p).strip()


def fetch_media(asset_id: str, tenant_id: str, db) -> tuple[pathlib.Path, str] | None:
    """Pull the asset's video (or image) out of R2 into a temp file."""
    r = db.table("marketing_asset_media").select(
        "kind, storage_bucket, storage_path, mime"
    ).eq("tenant_id", tenant_id).eq("asset_id", asset_id).execute()
    rows = list(r.data or [])
    pick = next((m for m in rows if m.get("kind") == "video"), None) or \
        next((m for m in rows if m.get("kind") == "image"), None)
    if not pick:
        return None
    bucket = pick["storage_bucket"]
    key = pick["storage_path"]
    suffix = pathlib.Path(key).suffix or (".mp4" if pick.get("kind") == "video" else ".jpg")
    surface = r2_storage.storage_surface().from_(bucket)
    tmp = pathlib.Path(tempfile.gettempdir()) / f"publish_{asset_id}{suffix}"
    tmp.write_bytes(surface.download(key))
    return tmp, pick.get("kind", "video")


def claim(db, intent_id: str) -> bool:
    """queued -> running, and ONLY if this call is the one that changed it.

    The returned rows are the lock. An earlier version updated with the same
    guard and then re-read the row, which looks equivalent and is not: the read
    cannot tell "I set this to running" from "someone else did", so a second
    drain saw `running` and happily concluded it held the claim. Caught by
    tests/marketing_publish_drain_test.py, which claims twice on purpose.

    `.select()` on the update makes the guard observable — rows come back only
    for rows that actually matched `state = 'queued'`. Empty means someone else
    got there first, which is the whole question being asked. Two drains
    publishing the same reel is unrecoverable; there is no unsending.
    """
    res = (
        db.table("marketing_publish_intent")
        .update({"state": "running", "started_at": _now()})
        .eq("id", intent_id)
        .eq("state", "queued")
        .select("id")
        .execute()
    )
    return bool(list(res.data or []))


def finish(db, intent_id: str, *, state: str, result: dict, error: str | None) -> None:
    db.table("marketing_publish_intent").update({
        "state": state,
        "result": json.dumps(result),
        "error": (error or "")[:2000] or None,
        "finished_at": _now(),
    }).eq("id", intent_id).execute()


def drain_one(db, intent: dict, PublishRequest, publish, dry_run: bool) -> bool:
    iid = intent["id"]
    tenant_id = intent["tenant_id"]
    asset_id = intent["asset_id"]
    raw = intent.get("platforms")
    platforms = raw if isinstance(raw, list) else json.loads(raw or "[]")

    a = db.table("marketing_asset").select("*").eq("tenant_id", tenant_id).eq("id", asset_id).execute()
    assets = list(a.data or [])
    if not assets:
        print(f"  intent {iid}: asset {asset_id} is gone")
        if not dry_run:
            finish(db, iid, state="failed", result={}, error="asset no longer exists")
        return False
    asset = assets[0]

    print(f"  intent {iid}: {asset.get('title')!r} -> {', '.join(platforms)}")
    if dry_run:
        print("    (dry run — not claimed, nothing published)")
        return False

    if not claim(db, iid):
        print("    another drain claimed it first — skipping")
        return False

    media = None
    try:
        got = fetch_media(asset_id, tenant_id, db)
        if not got:
            finish(db, iid, state="failed", result={}, error="no media attached to the asset")
            print("    FAILED: no media attached")
            return False
        media, _kind = got

        short = [p for p in platforms if p in SHORT_FORM]
        longform = [p for p in platforms if p not in SHORT_FORM]

        result: dict = {}
        errors: list[str] = []
        for group, pro in ((short, False), (longform, True)):
            if not group:
                continue
            req = PublishRequest(
                brand="oasis",                       # the CAMPAIGN's brand, never the handle
                caption=caption_for(asset, professional=pro),
                platforms=group,
                media_path=str(media),
                title=(asset.get("title") or "")[:95],
                creative_id=asset_id,
                idempotency_key=f"intent-{iid}-{'pro' if pro else 'short'}",
                metadata={"campaign": asset.get("campaign"), "intent_id": iid, "via": "drain"},
            )
            bad = req.validate()
            if bad:
                errors.append(f"{group}: {bad}")
                for p in group:
                    result[p] = {"ok": False, "error": "; ".join(bad)}
                continue
            res = publish(req)
            ok = bool(getattr(res, "ok", False))
            pid = getattr(res, "post_id", None)
            reason = getattr(res, "reason", None)
            for p in group:
                result[p] = {"ok": ok, "post_id": pid, "reason": reason if not ok else None}
            if not ok:
                errors.append(f"{group}: {reason}")

        any_ok = any(v.get("ok") for v in result.values())
        finish(db, iid,
               state="done" if any_ok and not errors else ("done" if any_ok else "failed"),
               result=result,
               error="; ".join(errors) if errors else None)

        if any_ok:
            # The library must stop claiming this is still awaiting a verdict.
            first_id = next((v.get("post_id") for v in result.values() if v.get("ok")), None)
            db.table("marketing_asset").update({
                "status": "published",
                "published_at": _now(),
                "external_id": first_id,
                "updated_at": _now(),
            }).eq("tenant_id", tenant_id).eq("id", asset_id).execute()

        for p, v in result.items():
            print(f"    {p:11} {'ok' if v.get('ok') else 'FAILED'} {v.get('post_id') or v.get('reason') or ''}")
        return any_ok
    except Exception as exc:  # noqa: BLE001 — recorded, never swallowed
        finish(db, iid, state="failed", result={}, error=f"{exc}\n{traceback.format_exc()[-1200:]}")
        print(f"    FAILED: {exc}")
        return False
    finally:
        if media and media.exists():
            try:
                media.unlink()
            except OSError:
                pass


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="show queued work, claim nothing")
    ap.add_argument("--once", action="store_true", help="drain at most one intent")
    args = ap.parse_args()

    db = _db()
    q = db.table("marketing_publish_intent").select("*").eq("state", "queued").execute()
    queued = sorted(list(q.data or []), key=lambda r: str(r.get("created_at") or ""))
    if not queued:
        print("nothing queued")
        return 0

    print(f"{len(queued)} queued intent(s)")
    PublishRequest = publish = None
    if not args.dry_run:
        PublishRequest, publish = _load_publisher()

    done = 0
    for intent in queued:
        if drain_one(db, intent, PublishRequest, publish, args.dry_run):
            done += 1
        if args.once:
            break
    print(f"published: {done}/{len(queued)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
