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
from datetime import datetime, timedelta, timezone

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

    # path-drift-ok: "scripts/publishers/base.py" is rooted at CMO,
    # the CMO-Agent repo, not at this one. system_health's drift check reads
    # segmented Path builds without knowing their root, so it reports a file
    # that is deliberately not here.
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


def _download(bucket: str, key: str, dest: pathlib.Path) -> pathlib.Path:
    dest.write_bytes(r2_storage.storage_surface().from_(bucket).download(key))
    return dest


def fetch_media(asset_id: str, tenant_id: str, db,
                asset: dict | None = None) -> tuple[pathlib.Path, str, list[pathlib.Path]] | None:
    """(cover, kind, extra_slides). Every slide for a carousel, in ORDER.

    THIS USED TO RETURN ONE FILE. It took the first video row, or failing that
    `next(m for m in rows if kind == "image")` — whichever image row the driver
    happened to return first. So a five-slide carousel published as a SINGLE
    image, and after the slide backfill it was not even reliably slide 1: row
    order is not slide order, and nothing had ever made it be.

    The order lives in marketing_asset.media_urls, recorded from the render
    manifest at migration time. That is the only ordering that means anything —
    the media rows carry no rank, and sorting by storage_path would sort by an
    upload timestamp embedded in the key.
    """
    r = db.table("marketing_asset_media").select(
        "kind, storage_bucket, storage_path, mime"
    ).eq("tenant_id", tenant_id).eq("asset_id", asset_id).execute()
    rows = list(r.data or [])
    if not rows:
        return None

    tmpdir = pathlib.Path(tempfile.gettempdir())
    by_path = {str(m.get("storage_path")): m for m in rows}

    ordered: list[str] = []
    raw = (asset or {}).get("media_urls")
    if isinstance(raw, list):
        ordered = [str(x) for x in raw]
    elif isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            ordered = [str(x) for x in parsed] if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            print("    media_urls is unparseable; falling back to the cover only")

    # Only trust the recorded order for paths that actually exist as media rows.
    ordered = [p for p in ordered if p in by_path]

    if (asset or {}).get("asset_type") == "carousel" and len(ordered) > 1:
        paths: list[pathlib.Path] = []
        for i, key in enumerate(ordered, 1):
            m = by_path[key]
            suffix = pathlib.Path(key).suffix or ".png"
            paths.append(_download(m["storage_bucket"], key,
                                   tmpdir / f"publish_{asset_id}_slide{i}{suffix}"))
        return paths[0], "image", paths[1:]

    pick = next((m for m in rows if m.get("kind") == "video"), None) or \
        next((m for m in rows if m.get("kind") == "image"), None)
    if not pick:
        return None
    key = pick["storage_path"]
    suffix = pathlib.Path(key).suffix or (".mp4" if pick.get("kind") == "video" else ".jpg")
    cover = _download(pick["storage_bucket"], key, tmpdir / f"publish_{asset_id}{suffix}")
    return cover, pick.get("kind", "video"), []


def claim(db, intent_id: str, attempts: int = 0) -> bool:
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
        .update({"state": "running", "started_at": _now(), "attempts": attempts + 1})
        .eq("id", intent_id)
        .eq("state", "queued")
        .select("id")
        .execute()
    )
    return bool(list(res.data or []))


# How long a `running` intent may sit before it is presumed dead, and how many
# times we will re-try it before giving up for good.
STALE_AFTER_MINUTES = 20
MAX_ATTEMPTS = 3


def reap_stale(db) -> int:
    """Rescue intents left `running` by a drain that died mid-publish.

    WITHOUT THIS, ONE CRASH BLOCKS AN ASSET FOREVER. `running` exists so two
    drains cannot publish the same reel twice, but nothing releases it: if the
    process is killed — cron timeout, reboot, an exception outside the handler —
    the row stays `running`, the drain skips it (it only reads `queued`) and the
    API keeps returning 409 "already queued" for that asset. Silent, permanent,
    and invisible until someone asks why a video will not post.

    Found exactly that way: a probe intent sat `running` while the cron logged
    "nothing queued" every minute afterwards.

    Retries are capped. An intent that dies three times is failing for a reason
    that will not fix itself, and re-queueing forever would hide it.
    """
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(minutes=STALE_AFTER_MINUTES)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    stuck = db.table("marketing_publish_intent").select("*").eq("state", "running").execute()
    rescued = 0
    for row in list(stuck.data or []):
        started = str(row.get("started_at") or "")
        if started and started > cutoff:
            continue  # still plausibly working
        attempts = int(row.get("attempts") or 0)
        if attempts >= MAX_ATTEMPTS:
            db.table("marketing_publish_intent").update({
                "state": "failed",
                "error": (f"abandoned after {attempts} attempts — the drain died mid-publish "
                          f"each time. Check the platform response and requeue deliberately."),
                "finished_at": _now(),
            }).eq("id", row["id"]).eq("state", "running").execute()
            print(f"  reaped {row['id']}: giving up after {attempts} attempts")
        else:
            db.table("marketing_publish_intent").update({
                "state": "queued", "started_at": None,
            }).eq("id", row["id"]).eq("state", "running").execute()
            print(f"  reaped {row['id']}: back to queued (attempt {attempts} died)")
        rescued += 1
    return rescued


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

    if not claim(db, iid, int(intent.get("attempts") or 0)):
        print("    another drain claimed it first — skipping")
        return False

    media = None
    slides: list[pathlib.Path] = []
    try:
        got = fetch_media(asset_id, tenant_id, db, asset)
        if not got:
            finish(db, iid, state="failed", result={}, error="no media attached to the asset")
            print("    FAILED: no media attached")
            return False
        media, _kind, slides = got
        if slides:
            print(f"    carousel: {len(slides) + 1} slides in recorded order")

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
                extra_media_paths=[str(p) for p in slides] or None,
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
        # Both arms of the old `if any_ok and not errors else (if any_ok ...)`
        # returned "done", so it read as if it distinguished a partial publish
        # and did not. It cannot: state is CHECK-constrained to
        # queued/running/done/failed (bravo__003), and there is no `partial`.
        #
        # `done` here means "at least one network took it", which is the only
        # answer that keeps the reaper from re-queueing an intent whose post is
        # already live — a re-publish cannot be undone. What actually failed is
        # not lost: `error` carries every refusal, `result` carries per-platform
        # detail, and the asset records ONLY the platforms that accepted it (see
        # `landed` below), so nothing downstream claims a distribution that did
        # not happen.
        finish(db, iid,
               state="done" if any_ok else "failed",
               result=result,
               error="; ".join(errors) if errors else None)

        if any_ok:
            # The library must stop claiming this is still awaiting a verdict.
            first_id = next((v.get("post_id") for v in result.values() if v.get("ok")), None)
            # Stamp WHERE IT ACTUALLY WENT. `channel` holds one value and an
            # asset goes to six places, which is the whole reason the Library
            # read INSTAGRAM for everything (CC: "it's only posting to
            # Instagram"). Only the platforms that ACCEPTED it are recorded —
            # a refusal is not a distribution.
            landed = sorted(p for p, v in result.items() if v.get("ok"))
            db.table("marketing_asset").update({
                "status": "published",
                "published_at": _now(),
                "external_id": first_id,
                "platforms": json.dumps(landed),
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
        # Every slide, not just the cover — a carousel leaves N temp files.
        for f in [media, *(slides or [])]:
            if f and f.exists():
                try:
                    f.unlink()
                except OSError:
                    pass


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="show queued work, claim nothing")
    ap.add_argument("--once", action="store_true", help="drain at most one intent")
    args = ap.parse_args()

    db = _db()

    # Before anything: release intents a dead drain is still holding, or they
    # block their asset forever.
    reaped = reap_stale(db)
    if reaped:
        print(f"reaped {reaped} stale claim(s)")

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
    failed = len(queued) - done
    print(f"published: {done}/{len(queued)}"
          + (f"  ·  failed: {failed}" if failed else ""))

    # Non-zero when ANY intent failed. This returned 0 unconditionally, so a run
    # where every publish was refused reported healthy — the cron badge stayed
    # green and the watchdog never paged, which is the same defect the analytics
    # poller had (`return 1 if failed and not wrote else 0`). A publish that did
    # not happen is exactly the thing CC needs told about.
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
