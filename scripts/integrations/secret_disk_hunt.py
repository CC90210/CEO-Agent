"""secret_disk_hunt.py — recover outstanding secrets from anything already on disk.

Vercel will not return `sensitive` values to the API, the CLI, or its own
dashboard. But those values were typed by a human once, which means they may
still exist on this machine: a `.env.local` in the app repo, a `.env.agents`
backup taken before a key was dropped, a dump in `tmp/`.

This searches for them. It is the one remaining fully-automatic avenue, and it
costs nothing to try.

SAFETY CONTRACT — the reason an agent may run this at all:
  * The agent never sees a value. Output is KEY NAMES, the file that supplied
    them, and a shape class (url / jwt-like / hex-32 / short / long).
  * Candidate values are compared by SHA-256 prefix when they disagree between
    sources, so "two files hold different values for this key" is reportable
    without printing either.
  * `--apply` writes only into `# FILL <NS>__<KEY>=` placeholders that already
    exist. It never invents a key, never overwrites a populated one, and takes
    a timestamped backup first.
  * Files are read, never modified, and nothing is copied anywhere.

    python scripts/integrations/secret_disk_hunt.py           # report only
    python scripts/integrations/secret_disk_hunt.py --apply   # fill the FILLs
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

CAPABILITY_META = {
    "category": "release.cloudflare",
    "lifecycle": "active",
    "risk": "credential_store_write",
    "triggers": ["recover secrets from disk", "find the missing secret values",
                 "hunt for old env files"],
    "owner": "bravo",
    "project": "empire",
    "bridge": {"visible": False},
}

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

ENV_FILE = REPO_ROOT / ".env.agents"
REGISTRY = REPO_ROOT / "config" / "cloudflare" / "apps.json"
MANIFEST_DIR = REPO_ROOT / "config" / "cloudflare" / "manifests"

# Where a human-typed secret plausibly still lives on this machine.
SEARCH_ROOTS = [
    REPO_ROOT,
    Path(r"C:\Users\User\APPS"),
    Path(r"C:\Users\User\realestate-App"),
]
# Anything that looks like an env dump. Deliberately wide — a value is a value
# wherever it was left.
NAME_HINTS = (".env", ".env.", "env.local", "env.production", "env.backup")
SUFFIX_HINTS = (".bak", ".backup", ".old", ".orig", ".local", ".save")
SKIP_DIRS = {"node_modules", ".git", ".next", ".open-next", "__pycache__",
             ".wrangler", "dist", "build", ".vercel"}
MAX_BYTES = 2_000_000


# Template files document the SHAPE of a key with a placeholder value. Treating
# them as a credential source manufactures conflicts against the real store and,
# worse, could fill a worker with the literal string "your-secret-here".
TEMPLATE_MARKERS = ("example", "sample", "template", "dist", ".ci")


def _looks_like_env(p: Path) -> bool:
    n = p.name.lower()
    if any(part in SKIP_DIRS for part in p.parts):
        return False
    if any(m in n for m in TEMPLATE_MARKERS):
        return False
    if n.startswith(".env") or "env.agents" in n:
        return True
    if any(h in n for h in NAME_HINTS) and p.suffix.lower() in SUFFIX_HINTS + (".txt", ".env", ""):
        return True
    return False


def _shape(v: str) -> str:
    if not v:
        return "EMPTY"
    if v.startswith(("http://", "https://", "libsql://", "postgres://")):
        return f"url({len(v)})"
    if "@" in v and " " not in v and len(v) < 80:
        return f"email({len(v)})"
    if v.count(".") >= 2 and len(v) > 100:
        return f"jwt-like({len(v)})"
    if len(v) in (32, 64) and all(c in "0123456789abcdefABCDEF" for c in v):
        return f"hex-{len(v)}"
    return f"{'short' if len(v) <= 12 else 'long'}({len(v)})"


def _digest(v: str) -> str:
    return hashlib.sha256(v.encode("utf-8", "replace")).hexdigest()[:8]


def _parse(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        if path.stat().st_size > MAX_BYTES:
            return out
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip()
        if k.lower().startswith("export "):
            k = k[7:].strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        if k and v:
            out[k] = v
    return out


def _wanted() -> dict[str, list[tuple[str, str]]]:
    """{bare KEY: [(app slug, namespaced source name), ...]} for every FILL line."""
    text = ENV_FILE.read_text(encoding="utf-8")
    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))["apps"]
    want: dict[str, list[tuple[str, str]]] = {}
    for slug in reg:
        man = MANIFEST_DIR / f"{slug}.json"
        if not man.exists():
            continue
        for e in json.loads(man.read_text(encoding="utf-8")).get("secrets", []):
            src = e.get("source") or e["key"]
            if f"# FILL {src}=" in text:
                want.setdefault(e["key"], []).append((slug, src))
    return want


# Values that can be DERIVED rather than recovered, each from a source that is
# authoritative for it. Deliberately narrow: a derivation is only listed here
# when getting it wrong would be obvious rather than silent. Anything whose
# wrongness would surface as a subtle production fault (OAuth client pairs,
# per-integration shared secrets) is NOT here and never will be.
#
#   ("alias", OTHER_KEY)  take the value already in the store under another name
#   ("literal", VALUE)    a value established from code or live infrastructure
DERIVATIONS: dict[str, tuple[str, str, str]] = {
    # Supabase is RETIRED. scripts/run_dashboard_script.py:49 already ships
    # these exact compat placeholders because they only satisfy a startup check.
    "BRAVO_SUPABASE_URL": ("literal", "https://bravo.turso.compat",
                           "run_dashboard_script.py COMPAT_DEFAULTS — Supabase retired"),
    "BRAVO_SUPABASE_SERVICE_ROLE_KEY": ("literal", "turso-compat-key",
                                        "run_dashboard_script.py COMPAT_DEFAULTS — Supabase retired"),
    # The booking link is one URL for the business; BOOKING_LINK was recovered
    # from disk and NEXT_PUBLIC_ is the client-side copy of the same value.
    "NEXT_PUBLIC_BOOKING_URL": ("alias", "BOOKING_LINK",
                                "client-side copy of the same booking URL"),
    # The app's own production origin, per Vercel's domain list for the project.
    "PUBLIC_APP_URL": ("literal", "https://oasisai.work",
                       "the project's production domain (Vercel domains API)"),
    # The VPS bridge hostname, verified live: bearer-gated, answers 401.
    "BRIDGE_VPS_URL": ("literal", "https://bridge.oasisai.work",
                       "live tunnel hostname, verified answering 401 (bearer-gated)"),
}


# Keys that may be ROTATED (a fresh random value minted here) because every
# counterpart that must agree is reachable and is updated as part of the
# documented cutover. This allowlist is the whole safety mechanism — a key is
# added only after tracing who else holds it.
#
# DELIBERATELY EXCLUDED, with reasons, so nobody adds them casually:
#   BRIDGE_BEARER_TOKEN / _OASIS_AI_CC  outbound to the VPS bridge
#       (lib/bridge-proxy.ts:15 — "the bridge requires a matching" value). The
#       VPS is not reachable from here, so rotating silently breaks the bridge.
#   TT_PG_BRIDGE_TOKEN                  same shape, TextTorrent side.
#   OASIS_OUTBOUND_HMAC_SECRET          rotating invalidates every outbound link
#       already issued. (Recovered from disk anyway.)
#   BREEZE_ENCRYPTION_KEY               encrypts Plaid access tokens AT REST;
#       rotating forces every merchant to re-link their bank.
ROTATABLE: dict[str, str] = {
    # Inbound validation on the app's own cron routes. The only caller is
    # .github/workflows/cron-driver.yml, which TODAY targets the Vercel
    # deployment — so a fresh value on the Worker is independent of production
    # and breaks nothing. AT CUTOVER the GitHub secret OASIS_CRON_SECRET must be
    # set to this same value (gh secret set, reading from the store) in the same
    # change that repoints the driver. Until then the Worker's cron routes
    # answer 401 (configured) instead of 500 (not configured).
    "CRON_SECRET": "inbound cron auth; sole caller is cron-driver.yml, aligned at cutover",
}


def _rotate(keys: list[str]) -> dict[str, tuple[str, str]]:
    import secrets as _secrets
    out = {}
    for k in keys:
        if k not in ROTATABLE:
            print(f"  REFUSED   {k}: not in the rotation allowlist — a counterpart "
                  f"holds this value and cannot be updated from here")
            continue
        out[k] = (_secrets.token_urlsafe(32), ROTATABLE[k])
    return out


def _derive(loaded_get) -> dict[str, tuple[str, str]]:
    """{KEY: (value, justification)} for derivations whose source resolves."""
    out = {}
    for key, (kind, ref, why) in DERIVATIONS.items():
        if kind == "literal":
            out[key] = (ref, why)
        else:
            v = (loaded_get(ref) or "").strip()
            if v:
                out[key] = (v, f"{why} (from {ref})")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--infer", action="store_true",
                    help="also fill values derivable from code/live infra (see DERIVATIONS)")
    ap.add_argument("--rotate", action="append", default=[],
                    help="mint a NEW value for an allowlisted key (see ROTATABLE)")
    args = ap.parse_args()

    want = _wanted()
    if not want:
        print("no outstanding FILL placeholders — nothing to hunt for")
        return 0

    files: list[Path] = []
    for root in SEARCH_ROOTS:
        if not root.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root, onerror=lambda e: None):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for fn in filenames:
                p = Path(dirpath) / fn
                if _looks_like_env(p):
                    files.append(p)

    # {KEY: {digest: (value, [files])}} — collision-aware without printing values
    found: dict[str, dict[str, tuple[str, list[str]]]] = {}
    for p in files:
        for k, v in _parse(p).items():
            if k in want:
                d = _digest(v)
                slot = found.setdefault(k, {})
                if d in slot:
                    slot[d][1].append(str(p))
                else:
                    slot[d] = (v, [str(p)])

    print(f"scanned {len(files)} env-shaped file(s) for {len(want)} outstanding key(s)\n")
    resolved, conflicted = {}, {}
    for k in sorted(want):
        slot = found.get(k)
        if not slot:
            continue
        if len(slot) == 1:
            d, (v, srcs) = next(iter(slot.items()))
            resolved[k] = v
            print(f"  FOUND     {k:42} {_shape(v):16} <- {Path(srcs[0]).name}")
        else:
            conflicted[k] = slot
            print(f"  CONFLICT  {k:42} {len(slot)} different values:")
            for d, (v, srcs) in slot.items():
                print(f"              sha256:{d} {_shape(v):16} <- {', '.join(Path(s).name for s in srcs[:2])}")

    if args.infer:
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        from lib.secret_loader import load_env  # noqa: PLC0415
        loaded = load_env()
        derived = _derive(loaded.get)
        for k, (v, why) in sorted(derived.items()):
            if k in want and k not in resolved:
                resolved[k] = v
                print(f"  DERIVED   {k:42} {_shape(v):16} <- {why}")

    if args.rotate:
        for k, (v, why) in _rotate(args.rotate).items():
            if k in want and k not in resolved:
                resolved[k] = v
                print(f"  ROTATED   {k:42} {_shape(v):16} <- new value; {why}")

    missing = [k for k in want if k not in found and k not in resolved]
    print(f"\nrecoverable: {len(resolved)}   conflicting: {len(conflicted)}   "
          f"not on disk: {len(missing)}")
    if missing:
        print("  still missing: " + ", ".join(sorted(missing)))
    if conflicted:
        print("\nCONFLICTS ARE NOT AUTO-FILLED. Two files disagree; picking one blind is how a\n"
              "worker gets a stale credential that fails only under load. Resolve by hand.")

    if not args.apply:
        print("\nreport only — re-run with --apply to write the recoverable values.")
        return 0
    if not resolved:
        print("\nnothing to apply.")
        return 0

    stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    shutil.copy2(ENV_FILE, ENV_FILE.with_name(f".env.agents.bak.{stamp}"))
    text = ENV_FILE.read_text(encoding="utf-8")
    written = 0
    for k, v in resolved.items():
        if "\n" in v or "\r" in v:
            continue
        for _slug, src in want[k]:
            marker = f"# FILL {src}="
            if marker in text:
                text = text.replace(marker, f"{src}=", 1)
                text = text.replace(f"{src}=\n", f"{src}={v}\n", 1)
                written += 1
    ENV_FILE.write_text(text, encoding="utf-8", newline="\n")
    print(f"\nwrote {written} value(s) into the agents env store (backup: .env.agents.bak.{stamp})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
