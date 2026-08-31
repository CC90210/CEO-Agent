"""secret_fuzzy_match.py — find outstanding secrets hiding under the wrong NAME.

`secret_disk_hunt.py` matches key names EXACTLY, so a value stored as
`BREEZE_ENC_KEY` when the manifest wants `BREEZE_ENCRYPTION_KEY` is invisible to
it. This scores every populated key in the agents store against every
outstanding gap.

Matching is MECHANICAL on purpose — token overlap plus value-shape
compatibility. No value is ever printed, logged, or sent anywhere; the operator
and the agent see key names, a score, and a shape class.

CONFIDENCE, and what each tier is allowed to do:
  exact-alias  token sets identical once app prefixes are stripped
               (BREEZE_PORTAL__ENCRYPTION_KEY vs BREEZE_ENCRYPTION_KEY).
               AUTO-APPLIED.
  strong       >=0.70 token overlap AND a compatible value shape. REPORTED for
               a human yes — never auto-applied, because a confidently wrong
               credential is worse than an absent one: it deploys clean and
               fails later, in production, under load.
  weak         everything else. Listed so the operator can see what was
               considered and rule it out, rather than wondering.

    python scripts/integrations/secret_fuzzy_match.py          # report
    python scripts/integrations/secret_fuzzy_match.py --apply  # exact-alias only
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import shutil
import sys
from pathlib import Path

CAPABILITY_META = {
    "category": "release.cloudflare",
    "lifecycle": "active",
    "risk": "credential_store_write",
    "triggers": ["find misnamed secrets", "fuzzy match env keys",
                 "secrets under the wrong prefix"],
    "owner": "bravo",
    "project": "empire",
    "bridge": {"visible": False},
}

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
STORE = ROOT / ".env.agents"
REGISTRY = ROOT / "config" / "cloudflare" / "apps.json"
MANIFESTS = ROOT / "config" / "cloudflare" / "manifests"

# Tokens carrying no discriminating signal — nearly every credential has them.
#
# `id` and `secret` are DELIBERATELY NOT HERE, and this is the whole reason the
# first run of this tool was unusable: with them stripped, GOOGLE_CLIENT_ID and
# GOOGLE_CLIENT_SECRET both reduce to {google, client}, score 1.00, and the tool
# proposed writing a client SECRET into a client ID field. The same trap catches
# anon/service, public/private, read/write. Tokens that invert a key's meaning
# are the most discriminating tokens there are — never treat them as noise.
NOISE = {"key", "token", "api", "next", "url", "value", "app"}

# Tenant-scoped credential families. A key from app A is NEVER a candidate for
# app B here, no matter how identical the names look: TIKTIK__..SUPABASE_URL and
# BREEZE_PORTAL__..SUPABASE_URL are the same NAME pointing at different
# PROJECTS, and swapping them silently points an app at another tenant's data.
#
# GOOGLE/OAUTH/CLIENT are included for the same reason: an OAuth client is
# per-project, and a refresh token is bound to the client that minted it. Taking
# one app's client id/secret for another breaks consent in a way that presents
# as a permissions bug, not a config error.
TENANT_SCOPED = ("SUPABASE", "TURSO", "DATABASE", "BRIDGE", "PLAID", "STRIPE",
                 "R2_", "WEBHOOK", "HMAC", "ENCRYPTION", "SESSION", "CRON",
                 "GOOGLE", "OAUTH", "CLIENT", "ANTHROPIC", "TELEGRAM")


def app_of(key: str) -> str | None:
    for p in APP_PREFIXES:
        if key.startswith(p):
            return p
    return None


def tenant_conflict(target_src: str, candidate: str) -> bool:
    """True when the two keys belong to different apps AND the credential is
    tenant-scoped — the case where a same-name match is actively wrong."""
    ta, ca = app_of(target_src), app_of(candidate)
    if ta is None or ca is None or ta == ca:
        return False
    name = (target_src + candidate).upper()
    return any(m in name for m in TENANT_SCOPED)
APP_PREFIXES = (
    "OASIS_COMMAND_CENTER__", "BREEZE_PORTAL__", "PROPFLOW__", "TIKTIK__",
    "IG_SETTER_PRO__", "NOSTALGIC_REQUESTS__", "OASIS_AI_PLATFORM__",
    "OPT_IN_VAULT__", "LISTING_STUDIO__", "SUNBIZ_FUNDING__",
    "ARTHRISIL_WEBSITE__", "BLUE_RISE_WEBSITE__", "BREEZEADVANCE_WEBSITE__",
)


def toks(name: str) -> set[str]:
    n = name
    for p in APP_PREFIXES:
        if n.startswith(p):
            n = n[len(p):]
    return {t for t in re.split(r"[^A-Za-z0-9]+", n.lower()) if t and t not in NOISE}


def shape(v: str) -> str:
    if not v:
        return "empty"
    if v.startswith(("http://", "https://", "libsql://", "postgres://")):
        return "url"
    if "@" in v and " " not in v and len(v) < 80:
        return "email"
    if v.count(".") >= 2 and len(v) > 100:
        return "jwt"
    if re.fullmatch(r"[0-9a-fA-F]{32,64}", v):
        return "hex"
    if re.fullmatch(r"(true|false|1|0|on|off|yes|no)", v, re.I):
        return "flag"
    return "long" if len(v) > 24 else "short"


def expected(name: str) -> set[str]:
    """Plausible shapes for a gap, from its name — vetoes a name-similar but
    type-incompatible candidate (a URL is not an encryption key)."""
    n = name.upper()
    if "URL" in n or "BASE" in n or n.endswith("_LINK"):
        return {"url"}
    if "EMAIL" in n or ("ADDRESS" in n and "CALENDAR" not in n):
        return {"email"}
    if "ANON_KEY" in n or "SERVICE_ROLE" in n or "JWT" in n:
        return {"jwt", "long"}
    if n.endswith("_ENV"):
        return {"short", "flag"}
    return {"long", "hex", "jwt", "short"}


def parse(p: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in p.read_text(encoding="utf-8", errors="replace").splitlines():
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


def gaps(text: str) -> dict[str, str]:
    """{namespaced FILL source: bare key name}"""
    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))["apps"]
    out: dict[str, str] = {}
    for slug in reg:
        m = MANIFESTS / f"{slug}.json"
        if not m.exists():
            continue
        for e in json.loads(m.read_text(encoding="utf-8")).get("secrets", []):
            src = e.get("source") or e["key"]
            if f"# FILL {src}=" in text:
                out[src] = e["key"]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    text = STORE.read_text(encoding="utf-8")
    populated = parse(STORE)
    g = gaps(text)
    print(f"{len(populated)} populated keys in the store; {len(g)} outstanding gaps\n")

    auto: dict[str, tuple[str, str, str]] = {}
    strong, weak = [], []
    for src, bare in sorted(g.items()):
        want, exp = toks(bare), expected(bare)
        scored = []
        for k, v in populated.items():
            if k in g or tenant_conflict(src, k):
                continue
            have = toks(k)
            if not have or not want:
                continue
            j = len(want & have) / len(want | have)
            sh = shape(v)
            if j > 0:
                scored.append((j, k, sh, sh in exp))
        scored.sort(reverse=True)
        if not scored:
            weak.append((bare, None, 0.0, None))
            continue
        j, k, sh, ok = scored[0]
        if j == 1.0 and ok:
            auto[src] = (k, populated[k], sh)
        elif j >= 0.70 and ok:
            strong.append((bare, k, j, sh))
        else:
            weak.append((bare, k, j, sh))

    if auto:
        print("EXACT ALIAS — same key, different prefix (auto-applied with --apply):")
        for src, (k, _v, sh) in sorted(auto.items()):
            print(f"   {src:46} <- {k}  [{sh}]")
    if strong:
        print("\nSTRONG candidate — NEEDS AN EXPLICIT YES, not auto-applied:")
        for bare, k, j, sh in strong:
            print(f"   {bare:46} <- {k}  (overlap {j:.2f}) [{sh}]")
    print(f"\nNO PLAUSIBLE CANDIDATE ANYWHERE IN THE FILE ({len(weak)}):")
    for bare, k, j, sh in weak:
        note = f"closest was {k} (overlap {j:.2f}, shape {sh})" if k else "nothing scored above zero"
        print(f"   {bare:46} {note}")

    if not args.apply:
        print("\nreport only — re-run with --apply to write the exact-alias matches.")
        return 0
    if not auto:
        print("\nno exact-alias matches to apply.")
        return 0
    stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    shutil.copy2(STORE, STORE.with_name(f".env.agents.bak.{stamp}"))
    for src, (_k, v, _s) in auto.items():
        text = text.replace(f"# FILL {src}=", f"{src}={v}", 1)
    STORE.write_text(text, encoding="utf-8", newline="\n")
    print(f"\napplied {len(auto)} exact-alias value(s); backup taken.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
