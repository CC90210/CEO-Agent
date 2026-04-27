#!/usr/bin/env python
"""
Generate Maven's clean .env.agents:
- Copy shared-infra keys from Bravo
- Drop SunBiz-specific keys (those stay in SunBiz-Marketing repo)
- Add empty placeholders for Maven-specific OASIS/PropFlow/Nostalgic ad creds

Run once to migrate. Safe to re-run — backs up existing file.
"""
from pathlib import Path
from datetime import datetime

BRAVO_ENV = Path(r"C:\Users\User\Business-Empire-Agent\.env.agents")
MAVEN_ENV = Path(r"C:\Users\User\CMO-Agent\.env.agents")


def parse_env(path: Path) -> dict:
    if not path.exists():
        return {}
    d = {}
    for line in path.read_text(encoding="utf-8", errors="ignore").split("\n"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        d[k.strip()] = v
    return d


def main():
    bravo = parse_env(BRAVO_ENV)
    maven_old = parse_env(MAVEN_ENV)

    header = f"""# ═══════════════════════════════════════════════════════════════════════
# MAVEN (CMO-Agent) — Environment Credentials
# Generated: {datetime.utcnow().strftime('%Y-%m-%d')}
# ═══════════════════════════════════════════════════════════════════════
#
# SCOPE: Credentials for Maven's work on CC's portfolio only:
#   - OASIS AI (primary revenue brand)
#   - CC's personal brand (content engine top-of-funnel)
#   - PropFlow (real estate SaaS — launch pending)
#   - Nostalgic Requests (DJ/music SaaS)
#
# NOT IN THIS FILE: SunBiz Funding client credentials. Those live in the
# SunBiz-Marketing repo at C:\\Users\\User\\Marketing-Agent\\.env.agents.
# Maven shells out to that repo via subprocess for SunBiz legacy work.
#
# NEVER commit this file. Gitignored.
# ═══════════════════════════════════════════════════════════════════════
"""

    sections = [header]

    def section(title: str, keys: list, source: dict):
        sections.append(f"\n# ─── {title} " + "─" * max(0, 63 - len(title)))
        for k in keys:
            sections.append(f"{k}={source.get(k, '')}")

    section("Shared AI Tools", [
        "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "ELEVENLABS_API_KEY",
    ], {**bravo, **maven_old})

    section("Shared Infrastructure", [
        "GITHUB_PERSONAL_ACCESS_TOKEN", "VERCEL_TOKEN", "SUPABASE_ACCESS_TOKEN",
        "FIRECRAWL_API_KEY", "LATE_API_KEY",
        "N8N_API_URL", "N8N_API_KEY", "N8N_BEARER_TOKEN",
    ], bravo)

    section("Shared Supabase (cross-agent memory)", [
        "BRAVO_SUPABASE_URL", "BRAVO_SUPABASE_ANON_KEY", "BRAVO_SUPABASE_SERVICE_ROLE_KEY",
    ], bravo)

    section("OASIS AI Platform (Maven reads for marketing context)", [
        "OASIS_SUPABASE_URL", "OASIS_SUPABASE_ANON_KEY", "OASIS_SUPABASE_SERVICE_ROLE_KEY",
    ], bravo)

    section("Nostalgic Requests DB (Maven drives its marketing)", [
        "NOSTALGIC_SUPABASE_URL", "NOSTALGIC_SUPABASE_ANON_KEY", "NOSTALGIC_SUPABASE_SERVICE_ROLE_KEY",
    ], bravo)

    section("Google Workspace (calendar, drive, sender email)", [
        "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN",
        "GWS_CLIENT_ID", "GWS_CLIENT_SECRET", "GWS_GCP_PROJECT",
    ], bravo)

    section("CC Business Gmail (sender for OASIS outreach)", [
        "GMAIL_USER", "GMAIL_APP_PASSWORD",
    ], bravo)

    section("CC Social Accounts (content posting)", [
        "INSTAGRAM_USERNAME", "INSTAGRAM_PASSWORD",
        "LINKEDIN_EMAIL", "LINKEDIN_PASSWORD",
        "SKOOL_EMAIL", "SKOOL_PASSWORD",
    ], bravo)

    sections.append("""

# ═══════════════════════════════════════════════════════════════════════
# MAVEN-SPECIFIC — CC FILLS THESE IN WHEN EACH ACCOUNT IS CREATED
# ═══════════════════════════════════════════════════════════════════════
# These are CC's OWN OASIS/PropFlow/Nostalgic ad accounts — separate from
# the SunBiz client creds that live in the SunBiz-Marketing repo.
# ═══════════════════════════════════════════════════════════════════════

# ─── OASIS AI Meta Ads (CC's own ad account for OASIS campaigns) ──────
OASIS_META_APP_ID=
OASIS_META_APP_SECRET=
OASIS_META_ACCESS_TOKEN=
OASIS_META_AD_ACCOUNT_ID=
OASIS_META_PAGE_ID=
OASIS_META_PIXEL_ID=

# ─── OASIS AI Google Ads (CC's own Google Ads customer) ────────────────
OASIS_GOOGLE_ADS_DEVELOPER_TOKEN=
OASIS_GOOGLE_ADS_CUSTOMER_ID=
OASIS_GOOGLE_ADS_CLIENT_ID=
OASIS_GOOGLE_ADS_CLIENT_SECRET=
OASIS_GOOGLE_ADS_REFRESH_TOKEN=

# ─── PropFlow Meta Ads (fill when launch campaign starts) ─────────────
PROPFLOW_META_APP_ID=
PROPFLOW_META_APP_SECRET=
PROPFLOW_META_ACCESS_TOKEN=
PROPFLOW_META_AD_ACCOUNT_ID=
PROPFLOW_META_PAGE_ID=

# ─── Nostalgic Requests Shopify (for product ad rendering) ────────────
NOSTALGIC_SHOPIFY_STORE=
NOSTALGIC_SHOPIFY_ACCESS_TOKEN=

# ─── TikTok Business API (if CC creates app) ──────────────────────────
# TIKTOK_APP_ID=
# TIKTOK_APP_SECRET=
# TIKTOK_ACCESS_TOKEN=
""")

    # Backup old env if it exists
    if MAVEN_ENV.exists():
        backup = MAVEN_ENV.parent / ".env.agents.sunbiz_inherited_backup"
        backup.write_text(MAVEN_ENV.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"Backup saved: {backup}")

    new_env = "\n".join(sections)
    MAVEN_ENV.write_text(new_env, encoding="utf-8")

    new_keys = [
        l.split("=")[0]
        for l in new_env.split("\n")
        if l and not l.startswith("#") and "=" in l
    ]
    populated = sum(
        1
        for l in new_env.split("\n")
        if l and not l.startswith("#") and "=" in l and l.split("=", 1)[1]
    )
    placeholders = sum(
        1
        for l in new_env.split("\n")
        if l and not l.startswith("#") and "=" in l and not l.split("=", 1)[1]
    )
    removed = set(maven_old) - set(new_keys)

    print(f"\nMaven new env generated: {MAVEN_ENV}")
    print(f"  Total keys: {len(new_keys)}")
    print(f"  Populated with live values: {populated}")
    print(f"  Empty placeholders: {placeholders}")
    print(f"  SunBiz-specific keys removed: {len(removed)}")
    if removed:
        print(f"  Removed: {sorted(removed)}")


if __name__ == "__main__":
    main()
