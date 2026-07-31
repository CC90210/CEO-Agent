"""seed_sunbiz_application_form_fields.py — add SOP §4 inputs to SunBiz intake forms.

Adon MCA SOP §4 (2026-06-11) requires the application to collect:
  - business_state  (ISO 2-letter; feeds lender.restricted_states filter)
  - industry        (lowercase slug; feeds lender.restricted_industries filter)

Without these, the SOP §4 high-risk blocks never fire on a real shop-out
because ApplicationProfile.merchant_state and .industry stay undefined —
the scorer emits "info: missing_<field>" warnings instead of refusing
to suggest restricted lenders.

2026-06-11 rewrite per VPS-agent discovery: the SunBiz intake forms live
in the `forms` table (not `tenant_records` form_template — that table is
empty for SunBiz). The shape is steps[i].fields[] where each step has
key/label and fields is an array of {name, type, label, required, ...}.
Per lib/forms/types.ts the renderer supports type:"select" with
options:[{value,label}]. This script idempotently patches every ENABLED
SunBiz form's steps[0].fields to include business_state + industry as
required select fields. Safe to re-run.

Vocabulary list expanded 2026-06-11 to cover the off-vocabulary slugs the
migration discovered on Maison Capital Group + Olympus Lending lender
rows ("auto", "transportation", "staffing", "childcare") — so a straight
copy of legacy data into restricted_industries doesn't need re-mapping.

VPS / Adon / CC runs:

    python3 scripts/seed_sunbiz_application_form_fields.py [--dry-run]
    python3 scripts/seed_sunbiz_application_form_fields.py --id <FORM_ID>
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

CAPABILITY_META = {
    "category": "database.migration",
    "lifecycle": "one_off",
    "risk": "external_write",
    "triggers": ["seed sunbiz form fields", "add sunbiz intake fields", "patch sunbiz application form"],
    "owner": "bravo",
    "project": "sunbiz",
    "bridge": {"visible": False},
}

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

SUNBIZ_TENANT_ID = "aa04fa1f-ad6a-44b0-ac4b-2ff5d1067110"

US_STATES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI",
    "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN",
    "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH",
    "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA",
    "WV", "WI", "WY",
]

# SunBiz industry slugs. Expanded 2026-06-11 to include "auto",
# "transportation", "staffing", "childcare" so legacy lender data (Maison
# Capital Group, Olympus Lending) maps 1:1 without re-mapping. Adon can
# trim / extend via the manifest editor after the seed.
SUNBIZ_INDUSTRIES = [
    "restaurant", "retail", "ecommerce", "trucking", "transportation",
    "construction", "auto", "auto_repair", "auto_sales", "beauty_salon",
    "barbershop", "spa", "medical_practice", "dental_practice", "veterinary",
    "fitness_gym", "professional_services", "law_firm", "accounting",
    "real_estate", "wholesale", "manufacturing", "agriculture", "landscaping",
    "cleaning", "moving_storage", "hospitality_hotel", "bar_nightclub",
    "convenience_store", "gas_station", "liquor_store", "pharmacy",
    "cannabis", "staffing", "childcare", "other",
]


def _supabase():
    """Service-role client via scripts/lib/secret_loader.py."""
    from lib.secret_loader import load_env  # type: ignore
    env = load_env()
    url = (env.get("BRAVO_SUPABASE_URL") or "").strip()
    key = (env.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise RuntimeError("Supabase URL or service role key missing from .env.agents")
    from supabase import create_client  # type: ignore
    return create_client(url, key)


def _list_enabled_sunbiz_forms(sb) -> list[dict]:
    """All SunBiz forms with enabled=True. Schema per lib/forms/types.ts:
    {id, slug, name, steps[], enabled, ...}.
    """
    res = (
        sb.table("forms")
        .select("id, slug, name, steps, enabled")
        .eq("tenant_id", SUNBIZ_TENANT_ID)
        .eq("enabled", True)
        .execute()
    )
    return res.data or []


def _step_for_basic_fields(steps: list) -> tuple[int, dict] | None:
    """Pick the step whose `key` matches 'basic' / 'business' / 'about' /
    'contact'. Falls back to steps[0] when no semantic match exists —
    the business name + monthly revenue typically live there. Returns
    (index, step_obj) or None when steps is malformed.
    """
    if not isinstance(steps, list) or not steps:
        return None
    semantic_keys = {"basic", "business", "about", "contact", "company"}
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        key = str(step.get("key") or "").strip().lower()
        if key in semantic_keys:
            return i, step
    if isinstance(steps[0], dict):
        return 0, steps[0]
    return None


def _add_field_if_missing(fields: list, spec: dict, log: list[str]) -> bool:
    name = spec["name"]
    for f in fields:
        if isinstance(f, dict) and f.get("name") == name:
            log.append(f"    SKIP   {name}  (already present)")
            return False
    fields.append(spec)
    log.append(f"    ADD    {name}  ({spec.get('type','?')})")
    return True


def _patch_form_steps(steps: list, log: list[str]) -> list:
    """Add business_state + industry to the basic-info step of the form.
    Field shape matches lib/forms/types.ts: select fields use type='select'
    + options:[{value,label}]."""
    new_steps = copy.deepcopy(steps)
    target = _step_for_basic_fields(new_steps)
    if target is None:
        log.append("    WARN  steps is empty/malformed — cannot patch")
        return new_steps
    idx, step = target
    log.append(f"    Targeting steps[{idx}] (key={step.get('key')!r}, label={step.get('label')!r})")
    if not isinstance(step.get("fields"), list):
        log.append("    WARN  steps[i].fields is not a list — refusing to overwrite")
        return new_steps

    _add_field_if_missing(
        step["fields"],
        {
            "name": "business_state",
            "type": "select",
            "label": "Business State",
            "required": True,
            "options": [{"value": s, "label": s} for s in US_STATES],
            "help_text": "Feeds lender restricted-states pre-filter.",
        },
        log,
    )

    _add_field_if_missing(
        step["fields"],
        {
            "name": "industry",
            "type": "select",
            "label": "Industry",
            "required": True,
            "options": [{"value": v, "label": v.replace("_", " ").title()} for v in SUNBIZ_INDUSTRIES],
            "help_text": "Feeds lender restricted-industries pre-filter.",
        },
        log,
    )

    new_steps[idx] = step
    return new_steps


def main() -> int:
    p = argparse.ArgumentParser(prog="seed_sunbiz_application_form_fields")
    p.add_argument("--dry-run", action="store_true", help="Print diff without writing")
    p.add_argument("--id", help="Patch only this form id (skips list)")
    args = p.parse_args()

    sb = _supabase()

    forms: list[dict]
    if args.id:
        row = (
            sb.table("forms")
            .select("id, slug, name, steps, enabled, operating_mode")
            .eq("id", args.id)
            .eq("tenant_id", SUNBIZ_TENANT_ID)
            .maybe_single()
            .execute()
        )
        if not row.data:
            print(f"ERROR: form {args.id} not found in SunBiz tenant.", file=sys.stderr)
            return 2
        forms = [row.data]
    else:
        forms = _list_enabled_sunbiz_forms(sb)
        if not forms:
            print("ERROR: no enabled SunBiz forms found.", file=sys.stderr)
            return 2

    print(f"\nFound {len(forms)} enabled SunBiz form(s) to patch:\n")
    summary_changed = 0
    summary_unchanged = 0
    plans: list[tuple[dict, list, list[str]]] = []

    for form in forms:
        form_id = form["id"]
        slug = form.get("slug")
        name = form.get("name")
        print(f"Form {form_id}  slug={slug!r}  name={name!r}")
        log: list[str] = []
        steps = form.get("steps") or []
        new_steps = _patch_form_steps(steps, log)
        for line in log:
            print(line)
        if new_steps == steps:
            summary_unchanged += 1
            print("    (no changes)\n")
        else:
            summary_changed += 1
            plans.append((form, new_steps, log))
            print()

    print(f"Summary: {summary_changed} form(s) would be patched, {summary_unchanged} unchanged.\n")

    if not plans:
        print("Nothing to write. Done.")
        return 0

    if args.dry_run:
        print("--dry-run set, NOT writing.")
        return 0

    print("Applying patches...")
    for form, new_steps, _ in plans:
        result = (
            sb.table("forms")
            .update({"steps": new_steps})
            .eq("id", form["id"])
            .execute()
        )
        if not result.data:
            print(f"ERROR: update on form {form['id']} returned no data", file=sys.stderr)
            return 1
        print(f"  patched {form['id']}")
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
