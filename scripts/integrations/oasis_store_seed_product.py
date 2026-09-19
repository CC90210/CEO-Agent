#!/usr/bin/env python
"""Load a product-page JSON into the store as a DRAFT, or update it in place.

    python scripts/integrations/oasis_store_seed_product.py <path-to-page.json> [--replace]

The admin can build a product by hand; this exists for the other direction —
turning a written page (from research, a copywriter, or a previous product's
export) into a real row set without twenty form submits. It always lands as
`draft`: nothing reaches a shopper until someone opens /admin, syncs prices to
Stripe and flips the status, which is the gate that enforces "no public product
without a working price".

The JSON shape is the one in APPS/oasis-store/docs/product-research/*-page-copy.json:
  { name, slug, tagline, unit_label, hero{headline,subhead,bullets[]},
    seo{title,description}, tiers[{units,label,badge,onetime_usd,
    compare_at_usd,subscribe_usd,is_default}], sections[{type,data}] }
Extra keys (claims_rule, pricing_note, notes) are documentation and ignored.
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "integrations"))

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

import oasis_store_db as db  # noqa: E402

SECTION_TYPES = {"benefits", "how_it_works", "comparison", "ugc", "specs", "guarantee", "reviews", "faq", "cta"}


def cents(value) -> int | None:
    if value is None:
        return None
    return int(round(float(value) * 100))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("page", help="path to the page JSON")
    parser.add_argument("--replace", action="store_true", help="replace sections and tiers if the slug already exists")
    args = parser.parse_args(argv)

    page = json.loads(Path(args.page).read_text(encoding="utf-8"))
    slug = page["slug"]
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    bad = [s.get("type") for s in page.get("sections", []) if s.get("type") not in SECTION_TYPES]
    if bad:
        raise SystemExit(f"unknown section type(s): {bad}. Known: {sorted(SECTION_TYPES)}")
    if not page.get("tiers"):
        raise SystemExit("refusing: a product with no tiers cannot be priced or bought")

    existing = db.query("SELECT id, status FROM products WHERE slug = ?", [slug])
    if existing and not args.replace:
        print(f"{slug} already exists ({existing[0]['status']}). Re-run with --replace to overwrite its copy.")
        return 0

    pid = existing[0]["id"] if existing else "prd_" + uuid.uuid4().hex[:21]
    stmts: list[str] = []
    argv_rows: list[list] = []

    if existing:
        # Copy is replaced; media and reviews are deliberately NOT touched.
        for table in ("product_sections", "product_tiers"):
            stmts.append(f"DELETE FROM {table} WHERE product_id = ?")
            argv_rows.append([pid])
        stmts.append(
            "UPDATE products SET name = ?, tagline = ?, hero_headline = ?, hero_subhead = ?, hero_bullets_json = ?, "
            "seo_title = ?, seo_description = ?, unit_label = ?, updated_at = ? WHERE id = ?"
        )
        argv_rows.append([
            page["name"], page.get("tagline", ""), page["hero"]["headline"], page["hero"]["subhead"],
            json.dumps(page["hero"].get("bullets", [])[:4]), page.get("seo", {}).get("title"),
            page.get("seo", {}).get("description"), page.get("unit_label", "unit"), now, pid,
        ])
    else:
        stmts.append(
            "INSERT INTO products (id, slug, status, name, tagline, hero_headline, hero_subhead, hero_bullets_json, "
            "seo_title, seo_description, unit_label, supplier_json, created_at, updated_at) "
            "VALUES (?, ?, 'draft', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
        argv_rows.append([
            pid, slug, page["name"], page.get("tagline", ""), page["hero"]["headline"], page["hero"]["subhead"],
            json.dumps(page["hero"].get("bullets", [])[:4]), page.get("seo", {}).get("title"),
            page.get("seo", {}).get("description"), page.get("unit_label", "unit"),
            json.dumps({"adapter": "manual", "warehouse": "CA"}), now, now,
        ])

    for i, s in enumerate(page.get("sections", [])):
        stmts.append(
            "INSERT INTO product_sections (id, product_id, position, type, enabled, data_json, updated_at) "
            "VALUES (?, ?, ?, ?, 1, ?, ?)"
        )
        argv_rows.append(["sec_" + uuid.uuid4().hex[:21], pid, i, s["type"], json.dumps(s["data"]), now])

    for i, t in enumerate(page["tiers"]):
        stmts.append(
            "INSERT INTO product_tiers (id, product_id, position, units, label, badge, onetime_cents, "
            "compare_at_cents, subscribe_cents, is_default, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
        argv_rows.append([
            "tier_" + uuid.uuid4().hex[:21], pid, i, int(t.get("units", 1)), t.get("label", ""), t.get("badge"),
            cents(t["onetime_usd"]), cents(t.get("compare_at_usd")), cents(t["subscribe_usd"]),
            1 if t.get("is_default") else 0, now,
        ])

    db.execute(stmts, argv_rows)
    verb = "updated" if existing else "created"
    print(f"{verb} {slug} ({pid}) as DRAFT — {len(page.get('sections', []))} sections, {len(page['tiers'])} tiers")
    print("Next: /admin/products -> upload media -> 'Sync prices to Stripe' -> set unlisted, then live.")
    print("It is invisible to shoppers until then; a draft slug 404s publicly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
