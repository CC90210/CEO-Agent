"""The CI build env must carry every manifest key — pinned after it didn't.

2026-08-30. `wrangler_tool.py` builds each app two ways: locally via
`_build_env()`, and in CI via the workflow that `cmd_workflow()` generates.
Both are supposed to inject the same environment. They didn't.

`_build_env()` injected EVERY manifest key, because Vercel does and because
Next.js executes module-scope code during page-data collection — a route with
`const stripe = new Stripe(process.env.STRIPE_SECRET_KEY)` at the top needs that
RUNTIME-scoped secret at BUILD time. The generator injected only the
`build`/`both`-scoped subset, which looked reasonable: those are the keys the
bundler inlines.

So the local build passed and CI failed, on nostalgic-requests:

    Error: Failed to collect configuration for /api/stripe/webhook
      [cause]: Error: Neither apiKey nor config.authenticator provided

The two sites now carry comments telling each other to stay in sync. A comment
is not an enforcement mechanism — this test is. It reads no secret VALUES, only
key names.

Run: python -m pytest scripts/tests/test_cf_build_env_parity.py -v
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "config" / "cloudflare" / "apps.json"
MANIFEST_DIR = ROOT / "config" / "cloudflare" / "manifests"


def _apps() -> dict:
    if not REGISTRY.exists():
        pytest.skip("cloudflare registry not present")
    return json.loads(REGISTRY.read_text(encoding="utf-8"))["apps"]


def _manifest_keys(slug: str) -> set[str]:
    p = MANIFEST_DIR / f"{slug}.json"
    if not p.exists():
        return set()
    return {e["key"] for e in json.loads(p.read_text(encoding="utf-8")).get("secrets", [])}


def test_oasis_worker_excludes_separated_tenant_bindings() -> None:
    app = _apps()["oasis-command-center"]
    excluded = set(app.get("exclude_env_keys") or [])
    assert excluded, "the OASIS Worker needs an explicit deployment-boundary denylist"
    active = _manifest_keys("oasis-command-center")
    assert not (active & excluded), (
        "separated-tenant keys remain in the OASIS Cloudflare manifest: "
        f"{sorted(active & excluded)}"
    )
    assert app.get("deploy_surface") == "oasis"


def test_generated_workflows_stamp_platform_and_surface() -> None:
    source = (ROOT / "scripts" / "integrations" / "wrangler_tool.py").read_text(encoding="utf-8")
    assert "--var DEPLOY_PLATFORM:cloudflare" in source
    assert "--var DEPLOY_SURFACE:" in source
    assert "app.get('deploy_surface') or slug" in source


def _workflow_build_env(app_dir: Path) -> set[str] | None:
    wf = app_dir / ".github" / "workflows" / "deploy-cloudflare.yml"
    if not wf.exists():
        return None
    doc = yaml.safe_load(wf.read_text(encoding="utf-8"))
    steps = doc["jobs"]["deploy"]["steps"]
    build = [s for s in steps if str(s.get("name", "")).startswith("Build")]
    assert build, f"{wf} has no Build step"
    return set((build[0].get("env") or {}).keys())


@pytest.mark.parametrize("slug", sorted(_apps()))
def test_ci_build_env_covers_every_manifest_key(slug: str) -> None:
    """A key in the manifest but absent from the CI build env is the exact
    2026-08-30 failure: the build dies on module-scope SDK init."""
    app = _apps()[slug]
    if app.get("dropped"):
        pytest.skip(f"{slug} is dropped from the migration")
    env_keys = _workflow_build_env(Path(app["dir"]))
    if env_keys is None:
        pytest.skip(f"{slug} has no generated workflow yet")
    missing = _manifest_keys(slug) - env_keys
    assert not missing, (
        f"{slug}: the CI build env is missing {sorted(missing)}. Regenerate with "
        f"`wrangler_tool.py workflow --app {slug}` — the local builder injects "
        f"every manifest key and CI must match, or the build fails only in CI."
    )
