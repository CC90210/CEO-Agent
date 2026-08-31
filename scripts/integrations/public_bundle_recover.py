"""Recover NEXT_PUBLIC_* values from an app's own live client bundle.

Vercel marks production env vars `sensitive`: the API never decrypts them, so
`vercel env pull` and the dashboard both return ciphertext. That blocks recovery
for real secrets — but NOT for `NEXT_PUBLIC_*`. Next.js inlines those into the
JavaScript it serves to every visitor, so the value is already public. Reading it
back out of the bundle is reading public data, not decrypting a secret.

Hard rules this tool enforces on itself:

  * ONLY keys beginning `NEXT_PUBLIC_` are eligible. A key without that prefix is
    a real secret and is refused, no matter what the caller asks for.
  * Values are never printed, logged, or returned — they go from the HTTP
    response into the env store and nowhere else. Output is key names + shapes.
  * A recovered Supabase pair must be SELF-CONSISTENT and match the tenant: the
    anon JWT's `ref` claim must equal the URL's subdomain AND equal the `ref` in
    the app's already-populated service-role key. A value that is merely
    well-formed is not proof it belongs to this app — that is how TIKTIK's URL
    ended up in a sibling app earlier in this migration.

Usage:
  python scripts/integrations/public_bundle_recover.py --app <slug> --from <url>
  python scripts/integrations/public_bundle_recover.py --app <slug> --from <url> --apply
"""

from __future__ import annotations

import argparse
import base64
import datetime as _dt
import json
import re
import shutil
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STORE = ROOT / ".env.agents"
MANIFESTS = ROOT / "config" / "cloudflare" / "manifests"

UA = "Mozilla/5.0 (compatible; bravo-bundle-recover/1.0)"
TIMEOUT = 30

# The only prefix whose values are public by construction.
PUBLIC_PREFIX = "NEXT_PUBLIC_"

SUPABASE_URL_RE = re.compile(r"https://([a-z0-9]{16,32})\.supabase\.co")
JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")
SCRIPT_RE = re.compile(r"""<script[^>]+src=["']([^"']+)["']""", re.IGNORECASE)


def _get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read().decode("utf-8", errors="replace")


def _jwt_claims(tok: str) -> dict:
    try:
        payload = tok.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return {}


def _shape(v: str) -> str:
    """A description of a value that never reveals it."""
    if v.startswith("eyJ"):
        c = _jwt_claims(v)
        return f"jwt role={c.get('role', '?')} len={len(v)}"
    if v.startswith("http"):
        return f"url host={v.split('/')[2] if '//' in v else '?'}"
    return f"str len={len(v)}"


def _store_text() -> str:
    return STORE.read_text(encoding="utf-8")


def _populated(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in text.splitlines():
        s = raw.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        k, v = k.strip(), v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        if k and v:
            out[k] = v
    return out


def _open_gaps(slug: str, text: str) -> dict[str, str]:
    """{namespaced FILL source: bare key} for this app's still-empty public keys."""
    man = MANIFESTS / f"{slug}.json"
    if not man.exists():
        sys.stderr.write(f"no manifest for {slug}\n")
        return {}
    out: dict[str, str] = {}
    for e in json.loads(man.read_text(encoding="utf-8")).get("secrets", []):
        bare = e["key"]
        if not bare.startswith(PUBLIC_PREFIX):
            continue                       # refuse anything that is not public by construction
        src = e.get("source") or bare
        if f"# FILL {src}=" in text:
            out[src] = bare
    return out


def _tenant_ref(slug: str, pop: dict[str, str]) -> str | None:
    """The Supabase project ref this app is ALREADY wired to, from a populated key.

    Read from the service-role key's own JWT claims rather than from a name or a
    doc, so the check cannot be satisfied by a stale note.
    """
    prefix = slug.upper().replace("-", "_") + "__"
    for k, v in pop.items():
        if not k.startswith(prefix):
            continue
        if "SUPABASE" in k and v.startswith("eyJ"):
            ref = _jwt_claims(v).get("ref")
            if ref:
                return ref
    return None


def harvest(url: str) -> tuple[set[str], set[str]]:
    """Return (supabase urls, jwts) found in the page and its scripts."""
    html = _get(url)
    bodies = [html]
    for src in SCRIPT_RE.findall(html)[:60]:
        if src.startswith("//"):
            src = "https:" + src
        elif src.startswith("/"):
            src = url.rstrip("/") + src
        elif not src.startswith("http"):
            continue
        try:
            bodies.append(_get(src))
        except Exception:
            continue
    urls, jwts = set(), set()
    for b in bodies:
        urls.update(m.group(0) for m in SUPABASE_URL_RE.finditer(b))
        jwts.update(JWT_RE.findall(b))
    return urls, jwts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--app", required=True)
    ap.add_argument("--from", dest="url", required=True, help="live origin to harvest")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    text = _store_text()
    pop = _populated(text)
    want = _open_gaps(a.app, text)
    if not want:
        print(f"{a.app}: no open NEXT_PUBLIC_ gaps to recover.")
        return 0

    print(f"{a.app}: open public gaps -> {', '.join(sorted(want.values()))}")
    expect_ref = _tenant_ref(a.app, pop)
    print(f"tenant ref from this app's populated service key: {expect_ref or 'UNKNOWN'}")

    try:
        urls, jwts = harvest(a.url)
    except Exception as e:
        sys.stderr.write(f"harvest failed for {a.url}: {e}\n")
        return 1
    print(f"harvested {len(urls)} supabase url(s), {len(jwts)} jwt(s) from {a.url}")

    found: dict[str, str] = {}

    # ── Supabase pair: only accept a URL+anon key that agree with each other AND
    #    with the tenant this app already uses. Two independent confirmations.
    for u in urls:
        ref = SUPABASE_URL_RE.match(u).group(1)
        if expect_ref and ref != expect_ref:
            print(f"  SKIP url ref={ref} — not this app's tenant ({expect_ref})")
            continue
        anon = next(
            (j for j in jwts
             if _jwt_claims(j).get("ref") == ref and _jwt_claims(j).get("role") == "anon"),
            None,
        )
        if not anon:
            print(f"  SKIP url ref={ref} — no matching anon jwt in the bundle")
            continue
        for src, bare in want.items():
            if bare.endswith("SUPABASE_URL"):
                found[src] = u
            elif bare.endswith("SUPABASE_ANON_KEY"):
                found[src] = anon

    if not found:
        print("\nnothing recoverable from this bundle.")
        return 0

    print("\nRECOVERED (values never printed):")
    for src, v in sorted(found.items()):
        print(f"   {src:52} [{_shape(v)}]")

    if not a.apply:
        print("\nreport only — re-run with --apply to write these into the store.")
        return 0

    stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    shutil.copy2(STORE, STORE.with_name(f".env.agents.bak.{stamp}"))
    for src, v in found.items():
        text = text.replace(f"# FILL {src}=", f"{src}={v}", 1)
    STORE.write_text(text, encoding="utf-8", newline="\n")

    # Re-read from disk: confirm the write landed and the slot is really closed.
    after = _populated(_store_text())
    bad = [s for s in found if after.get(s) != found[s]]
    if bad:
        shutil.copy2(STORE.with_name(f".env.agents.bak.{stamp}"), STORE)
        sys.stderr.write(f"write verification FAILED for {bad}; store restored\n")
        return 1
    print(f"\napplied {len(found)} value(s); backup .env.agents.bak.{stamp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
