"""ingest_training_link — turn a dropped link into something Maven can learn from.

WHAT WAS MISSING
The Train Maven tab has worked for a while on the way IN:
app/api/founders/marketing/ingest/route.ts parses, canonicalises and enqueues
into `marketing_corpus` with state='queued'. Nothing has ever consumed that
queue. Every link CC or Adon dropped would have sat at "Waiting" forever, which
is worse than the drop-zone being disabled — it looks like it worked.

This is the consumer. queued -> extracting -> indexed | failed.

WHY marketing_corpus AND NOT training_corpus
Because marketing_corpus is the one that exists and the one the route writes to.
I created a `training_corpus` from a task description before checking, and
retired it in bravo__007 — two corpus tables would have meant two writers and
eventually two disagreeing answers to "what has Maven learned".

WHAT IT EXTRACTS
Fetch via scripts/research_fetch.py, which auto-escalates Firecrawl -> CloakBrowser
per domain and remembers what worked (state/site_reputation.db). Then a local
CLI model call (scripts/lib/claude_cli.py — subscription OAuth, never an API key)
turns the text into the four things a style exemplar needs: hook, pacing, tone,
and what to steal. Written to CMO-Agent/brain/exemplars/<slug>.md, because Maven
reads its brain, not this database.

NEVER INVENTS. If the fetch returns nothing usable the row fails loudly with the
reason. A fabricated "style analysis" of a page we could not read is worse than
an empty corpus — it would teach Maven from fiction.

  python scripts/ingest_training_link.py                       # drain the queue
  python scripts/ingest_training_link.py --dry-run             # show the work
  python scripts/ingest_training_link.py --url <u> --category do_more --author <email>
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys
import traceback
from datetime import datetime, timezone

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib import secret_loader  # noqa: E402
from integrations import supabase_tool  # noqa: E402

CMO = pathlib.Path(__import__("os").environ.get("CMO_REPO", r"C:\Users\User\CMO-Agent"))
EXEMPLARS = CMO / "brain" / "exemplars"
TENANT = "ef8d389e-3f15-43f2-ae00-3660f69a1452"

# The route's vocabulary, not a new one.
STATE_QUEUED, STATE_WORKING, STATE_DONE, STATE_FAILED = "queued", "extracting", "indexed", "failed"
MAX_ATTEMPTS = 3


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _db():
    return supabase_tool.get_client(secret_loader.bootstrap(), project="bravo")


def slugify(text: str, fallback: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:60]
    return s or fallback


def claim(db, row_id: str, attempts: int) -> bool:
    """queued -> extracting, and only if this call is what changed it.

    The returned rows are the lock. Same reasoning as the publish drain: a
    compare-and-set whose result is not checked is not a lock, and two workers
    fetching the same URL would double-spend a scrape budget and race on the
    exemplar file.
    """
    res = (
        db.table("marketing_corpus")
        .update({"state": STATE_WORKING, "attempts": attempts + 1, "updated_at": _now()})
        .eq("id", row_id)
        .eq("state", STATE_QUEUED)
        .select("id")
        .execute()
    )
    return bool(list(res.data or []))


def fetch_text(url: str) -> tuple[str, str]:
    """(text, how). Uses the empire's own escalation ladder — never a bare GET."""
    proc = subprocess.run(
        [sys.executable, str(HERE / "research_fetch.py"), url, "--json"],
        capture_output=True, text=True, timeout=300, cwd=HERE.parent,
    )
    out = proc.stdout or ""
    start = out.find("{")
    while start != -1:
        try:
            obj, _ = json.JSONDecoder().raw_decode(out[start:])
        except Exception:
            start = out.find("{", start + 1)
            continue
        if isinstance(obj, dict) and (obj.get("markdown") or obj.get("text") or obj.get("content")):
            text = obj.get("markdown") or obj.get("text") or obj.get("content") or ""
            return text, obj.get("via") or obj.get("source") or "research_fetch"
        start = out.find("{", start + 1)
    raise RuntimeError(
        f"research_fetch returned nothing usable for {url}. "
        f"stdout[:300]={out[:300]!r} stderr[:200]={(proc.stderr or '')[:200]!r}"
    )


ANALYSIS_PROMPT = """You are analysing ONE piece of content so a marketing agent can learn its craft.

Return STRICT JSON, no prose, with exactly these keys:
  "hook"        - the first line or opening move, quoted verbatim if present
  "pacing"      - how it controls attention over time, one or two sentences
  "tone"        - the register, one or two sentences
  "structure"   - the beats in order, as a short array of strings
  "steal"       - the ONE transferable technique, one sentence
  "avoid"       - anything that would NOT transfer to a different brand, one sentence

If the text is too thin to judge any field, set that field to null. Do NOT guess.
An honest null teaches more than a confident invention.

CONTENT:
"""


def analyse(text: str) -> dict:
    """Structured style read via the local CLI model. Never an API key."""
    # Imported here so --dry-run needs no model. run_claude_cli returns None on
    # ANY failure (missing binary, timeout, non-zero exit) rather than raising —
    # so a None must become a loud error here, not an empty analysis that would
    # be written to an exemplar as if we had read the page.
    from lib.claude_cli import run_claude_cli

    reply = run_claude_cli(
        ANALYSIS_PROMPT + text[:12000],
        system="You return strict JSON and nothing else. Never invent a field you cannot support from the text.",
        model="sonnet",
        timeout=180,
    )
    if not reply:
        raise RuntimeError(
            "claude CLI returned nothing (missing binary, timeout, or non-zero exit) — "
            "refusing to write an exemplar with no analysis in it"
        )
    start = reply.find("{")
    end = reply.rfind("}")
    if start == -1 or end == -1:
        raise RuntimeError(f"model did not return JSON; got {reply[:200]!r}")
    return json.loads(reply[start:end + 1])


def write_exemplar(slug: str, url: str, label: str, author: str,
                   analysis: dict, text: str) -> pathlib.Path:
    EXEMPLARS.mkdir(parents=True, exist_ok=True)
    path = EXEMPLARS / f"{slug}.md"
    verdict = {
        "do_more": "A MODEL TO WORK TOWARD",
        "never_do": "A BOUNDARY — DO NOT PRODUCE THIS",
        "context": "CONTEXT ONLY — neither target nor warning",
    }.get(label, label)

    def field(key: str) -> str:
        v = analysis.get(key)
        if v is None:
            return "_not judgeable from the text we could read_"
        if isinstance(v, list):
            return "\n".join(f"{i}. {s}" for i, s in enumerate(v, 1))
        return str(v)

    path.write_text(
        f"""---
source: {url}
verdict: {label}
submitted_by: {author}
ingested_at: {_now()}
---

# {slug}

**{verdict}**

## Hook
{field("hook")}

## Pacing
{field("pacing")}

## Tone
{field("tone")}

## Structure
{field("structure")}

## The one thing to steal
{field("steal")}

## What would not transfer
{field("avoid")}

---
_Extracted text, first 2000 chars, for provenance:_

```
{text[:2000]}
```
""",
        encoding="utf-8",
    )
    return path


def process(db, row: dict, dry_run: bool) -> bool:
    rid = row["id"]
    url = row.get("source_url") or ""
    label = row.get("label") or "context"
    author = row.get("contributed_by") or "unknown"
    attempts = int(row.get("attempts") or 0)

    print(f"\n  {url}\n    verdict={label} by={author} attempt={attempts + 1}")
    if dry_run:
        print("    (dry run — not claimed, nothing fetched)")
        return False

    if attempts >= MAX_ATTEMPTS:
        db.table("marketing_corpus").update({
            "state": STATE_FAILED,
            "last_error": f"abandoned after {attempts} attempts",
            "updated_at": _now(),
        }).eq("id", rid).execute()
        print(f"    giving up after {attempts} attempts")
        return False

    if not claim(db, rid, attempts):
        print("    another worker claimed it first")
        return False

    try:
        text, via = fetch_text(url)
        if len(text.strip()) < 120:
            raise RuntimeError(f"only {len(text.strip())} chars extracted via {via} — too thin to learn from")
        analysis = analyse(text)
        slug = slugify(row.get("title") or url, rid[:8])
        path = write_exemplar(slug, url, label, author, analysis, text)

        db.table("marketing_corpus").update({
            "state": STATE_DONE,
            "transcript": text[:200000],
            "extraction": json.dumps({**(row.get("extraction") or {}), "analysis": analysis,
                                      "exemplar": str(path.relative_to(CMO)), "via": via}),
            "search_text": " ".join(filter(None, [
                str(analysis.get("hook") or ""), str(analysis.get("steal") or "")])),
            "indexed_at": _now(),
            "updated_at": _now(),
        }).eq("id", rid).execute()
        print(f"    indexed via {via} -> {path.relative_to(CMO)}")
        return True
    except Exception as exc:  # noqa: BLE001 — recorded with its traceback, never swallowed
        db.table("marketing_corpus").update({
            "state": STATE_FAILED if attempts + 1 >= MAX_ATTEMPTS else STATE_QUEUED,
            "last_error": f"{exc}\n{traceback.format_exc()[-1200:]}",
            "updated_at": _now(),
        }).eq("id", rid).execute()
        print(f"    FAILED: {exc}")
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="show the queue, claim nothing")
    ap.add_argument("--once", action="store_true", help="process at most one link")
    ap.add_argument("--url", help="enqueue this URL first (manual entry point)")
    ap.add_argument("--category", choices=["do_more", "never_do", "context"], default="context")
    ap.add_argument("--author", default="conaugh@oasisai.work")
    args = ap.parse_args()

    db = _db()

    if args.url:
        existing = db.table("marketing_corpus").select("id, state").eq(
            "tenant_id", TENANT).eq("source_url", args.url).execute()
        live = [r for r in list(existing.data or []) if r.get("state") != STATE_FAILED]
        if live:
            print(f"already queued: {args.url} (state={live[0].get('state')})")
        else:
            db.table("marketing_corpus").insert({
                "tenant_id": TENANT,
                "kind": "link",
                "label": args.category,
                "title": args.url,
                "source_url": args.url,
                "state": STATE_QUEUED,
                "contributed_by": args.author,
                "extraction": "{}",
                "created_at": _now(),
                "updated_at": _now(),
            }).execute()
            print(f"queued: {args.url} ({args.category}, by {args.author})")

    q = db.table("marketing_corpus").select("*").eq("state", STATE_QUEUED).execute()
    rows = sorted(list(q.data or []), key=lambda r: str(r.get("created_at") or ""))
    if not rows:
        print("nothing queued")
        return 0

    print(f"{len(rows)} queued link(s)")
    done = 0
    for row in rows:
        if process(db, row, args.dry_run):
            done += 1
        if args.once:
            break
    print(f"\nindexed: {done}/{len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
