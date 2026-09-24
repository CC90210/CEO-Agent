"""vercel_secret_sync.py — recover Vercel prod env values into .env.agents for the CF migration.

Vercel's API decrypts type `encrypted`/`plain` env vars; only type `sensitive`
is unrecoverable. This script pulls each in-scope app's production values and
writes them into .env.agents under per-app namespaced keys, plus generates the
per-app Cloudflare secret manifest (config/cloudflare/manifests/<slug>.json).

Values flow API -> file ONLY. Nothing secret is ever printed; the LLM operating
this never sees a value. Sensitive-type keys are emitted as commented FILL
placeholders for CC.

A FILL line is NOT a "fetch it another way" marker: sensitive values are
unreadable by the API, by `vercel env pull` (proven — see
vercel_env_pull_sync.py's header) and by the Vercel dashboard itself. Each one
has to be recovered from its issuer or rotated on both sides;
brain/OASIS_CC_SECRET_FILL_GUIDE.md has the per-key routes.

    python scripts/integrations/vercel_secret_sync.py plan  [--app slug]
    python scripts/integrations/vercel_secret_sync.py apply [--app slug]

Namespacing: keys are stored as <SLUG_UPPER>__<KEY> (e.g. BREEZE_PORTAL__CRON_SECRET)
because the same key name carries DIFFERENT values across apps (five isolated
Turso DBs, per-app CRON_SECRETs). Manifests map worker key -> namespaced source.

Idempotent: each app's lines live between >>> cf-migration:<slug> markers and the
whole block is replaced atomically on re-run without creating another secret copy.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

CAPABILITY_META = {
    "category": "release.cloudflare",
    "lifecycle": "active",
    "risk": "local_write",
    "triggers": [
        "sync vercel env values into env agents",
        "recover vercel production secrets for cloudflare migration",
    ],
    "owner": "bravo",
    "project": "empire",
    "bridge": {"visible": False},
}

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from lib.env_store import locked_update_text  # noqa: E402

ENV_FILE = REPO_ROOT / ".env.agents"
REGISTRY_PATH = REPO_ROOT / "config" / "cloudflare" / "apps.json"
MANIFEST_DIR = REPO_ROOT / "config" / "cloudflare" / "manifests"

PLATFORM_KEYS = {"VERCEL"}
PLATFORM_PREFIXES = ("VERCEL_", "TURBO_", "NX_")


def _vercel_module():
    spec = importlib.util.spec_from_file_location(
        "vercel_env_tool", REPO_ROOT / "scripts" / "integrations" / "vercel_env_tool.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _registry() -> dict:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def _namespaced(slug: str, key: str) -> str:
    return slug.upper().replace("-", "_") + "__" + key


def _scope(key: str) -> str:
    if key.startswith("NEXT_PUBLIC_"):
        return "both"
    if key.startswith("VITE_"):
        return "build"
    return "runtime"


def _fetch(mod, vercel_project: str) -> tuple[list[tuple[str, str]], list[str], list[str]]:
    """Returns (recoverable [(key, value)], sensitive_keys, skipped_keys).

    The LIST endpoint returns ~1KB ciphertext blobs for `encrypted` vars even
    with decrypt=true (discovered 2026-08-29 when a "URL" came back 1088 chars).
    Only the per-id GET /v1/projects/{p}/env/{envId}?decrypt=true yields
    plaintext — so list for ids, then fetch each var individually."""
    res = mod._request("GET", f"/v10/projects/{vercel_project}/env",
                       params={"decrypt": "true"})
    envs = res.get("envs") if isinstance(res, dict) else res
    recoverable: list[tuple[str, str]] = []
    sensitive: list[str] = []
    skipped: list[str] = []
    for e in envs or []:
        key = e.get("key") or ""
        if "production" not in (e.get("target") or []):
            continue
        if key in PLATFORM_KEYS or key.startswith(PLATFORM_PREFIXES):
            continue
        if e.get("type") == "sensitive":
            sensitive.append(key)
            continue
        one = mod._request("GET", f"/v1/projects/{vercel_project}/env/{e['id']}",
                           params={"decrypt": "true"})
        value = one.get("value") if isinstance(one, dict) else None
        if value is None:
            sensitive.append(key)
            continue
        # Surrounding whitespace/newlines are paste artifacts — strip them.
        # Interior newlines or quote-edged values would be mangled by the flat
        # key=value parser, so those stay manual.
        v = str(value).strip()
        if not v or "\n" in v or "\r" in v or (
                v[:1] in {'"', "'"} or v[-1:] in {'"', "'"}):
            skipped.append(key)  # shape the flat parser would mangle — CC fills by hand
            continue
        recoverable.append((key, v))
    return recoverable, sorted(set(sensitive)), sorted(set(skipped))


def _write_block(slug: str, lines: list[str]) -> None:
    begin = f"# >>> cf-migration:{slug} — auto-generated by vercel_secret_sync.py, do not hand-edit"
    end = f"# <<< cf-migration:{slug}"
    block = "\n".join([begin, *lines, end])

    def replace_block(current: str) -> str:
        if begin in current:
            pre, _, rest = current.partition(begin)
            _, _, post = rest.partition(end)
            return pre + block + post
        separator = "" if current.endswith("\n") else "\n"
        return current + separator + "\n" + block + "\n"

    locked_update_text(ENV_FILE, replace_block)


def _write_manifest(slug: str, recoverable: list[tuple[str, str]],
                    sensitive: list[str], skipped: list[str]) -> None:
    entries = []
    for key, _v in sorted(recoverable):
        entries.append({"key": key, "source": _namespaced(slug, key), "scope": _scope(key)})
    for key in sorted(set(sensitive) | set(skipped)):
        entries.append({"key": key, "source": _namespaced(slug, key), "scope": _scope(key)})
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    (MANIFEST_DIR / f"{slug}.json").write_text(
        json.dumps({"secrets": entries}, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("verb", choices=["plan", "apply"])
    ap.add_argument("--app", action="append", default=None,
                    help="app slug(s) from apps.json; default = all")
    args = ap.parse_args()

    registry = _registry()
    apps = registry.get("apps") or {}
    slugs = args.app or sorted(apps)
    unknown = [s for s in slugs if s not in apps]
    if unknown:
        print(f"ERROR: unknown app(s): {', '.join(unknown)}", file=sys.stderr)
        return 2

    mod = _vercel_module()
    total_fill: list[str] = []
    for slug in slugs:
        vercel_project = apps[slug].get("vercel_project", slug)
        recoverable, sensitive, skipped = _fetch(mod, vercel_project)
        fill = [_namespaced(slug, k) for k in [*sensitive, *skipped]]
        print(f"{slug:25} recoverable={len(recoverable):3} "
              f"sensitive={len(sensitive):2} skipped={len(skipped)}")
        for k in sensitive:
            print(f"    FILL(sensitive) {_namespaced(slug, k)}")
        for k in skipped:
            print(f"    FILL(shape)     {_namespaced(slug, k)}")
        total_fill.extend(fill)
        if args.verb != "apply":
            continue
        lines = [f"{_namespaced(slug, k)}={v}" for k, v in sorted(recoverable)]
        lines += [f"# FILL {name}=" for name in fill]
        _write_block(slug, lines)
        _write_manifest(slug, recoverable, sensitive, skipped)

    if args.verb == "apply":
        print(f"\napplied. {len(total_fill)} FILL placeholders await CC "
              f"(commented lines in .env.agents).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
