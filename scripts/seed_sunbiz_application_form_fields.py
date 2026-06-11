"""seed_sunbiz_application_form_fields.py — add SOP §4 inputs to SunBiz application form.

Adon MCA SOP §4 (2026-06-11) requires the application to collect:
  - business_state  (ISO 2-letter; feeds lender.restricted_states filter)
  - industry        (lowercase slug; feeds lender.restricted_industries filter)

Without these, the SOP §4 high-risk blocks never fire on a real shop-out
because ApplicationProfile.merchant_state and .industry stay undefined —
the scorer emits "info: missing_<field>" warnings instead of refusing
to suggest restricted lenders.

This script idempotently patches the SunBiz application form_template's
JSONB schema. Safe to re-run (skips fields that already exist; logs what
it added vs skipped). Adon / CC / VPS agent runs:

    python3 scripts/seed_sunbiz_application_form_fields.py [--dry-run]

Dry-run prints the diff without writing.

The form_template entity lives in tenant_records, scoped to the SunBiz
tenant. We resolve the right row by:
  1. entity_type='form_template'
  2. tenant_id=aa04fa1f-ad6a-44b0-ac4b-2ff5d1067110 (SunBiz)
  3. data.slug ILIKE '%application%'  OR  data.is_default_application=true

If multiple match, the script lists them and asks the operator to pick.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

SUNBIZ_TENANT_ID = "aa04fa1f-ad6a-44b0-ac4b-2ff5d1067110"

# US states — short list for the dropdown. The full 50-state set is in
# every form library; this is the SunBiz operator-friendly set.
US_STATES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI",
    "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN",
    "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH",
    "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA",
    "WV", "WI", "WY",
]

# SunBiz industry list — common MCA verticals. Lowercase slugs match the
# format match-fitness expects (industries are .toLowerCase()'d at compare).
# Adon can extend via the manifest editor after the seed.
SUNBIZ_INDUSTRIES = [
    "restaurant", "retail", "ecommerce", "trucking", "construction",
    "auto_repair", "auto_sales", "beauty_salon", "barbershop", "spa",
    "medical_practice", "dental_practice", "veterinary", "fitness_gym",
    "professional_services", "law_firm", "accounting", "real_estate",
    "wholesale", "manufacturing", "agriculture", "landscaping", "cleaning",
    "moving_storage", "hospitality_hotel", "bar_nightclub",
    "convenience_store", "gas_station", "liquor_store", "pharmacy",
    "cannabis", "other",
]


def _supabase():
    """Service-role client via scripts/lib/secret_loader.py — same pattern
    as supabase_tool.py + every other daemon. Loads .env.agents."""
    from lib.secret_loader import load_env  # type: ignore
    env = load_env()
    url = (env.get("BRAVO_SUPABASE_URL") or "").strip()
    key = (env.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        raise RuntimeError("Supabase URL or service role key missing from .env.agents")
    from supabase import create_client  # type: ignore
    return create_client(url, key)


def _resolve_form_template(sb) -> dict:
    """Find the SunBiz application form_template. Lists candidates if
    multiple match and exits non-zero asking for explicit ID."""
    rows = (
        sb.table("tenant_records")
        .select("id, data")
        .eq("tenant_id", SUNBIZ_TENANT_ID)
        .eq("entity_type", "form_template")
        .execute()
    )
    candidates = []
    for row in rows.data or []:
        d = row.get("data") or {}
        slug = str(d.get("slug") or "").lower()
        name = str(d.get("name") or "").lower()
        is_default = bool(d.get("is_default_application"))
        if "application" in slug or "application" in name or is_default:
            candidates.append({"id": row["id"], "data": d})

    if not candidates:
        print("ERROR: no SunBiz form_template matched 'application' criteria.", file=sys.stderr)
        print("List all form_templates for SunBiz to debug:", file=sys.stderr)
        for row in rows.data or []:
            d = row.get("data") or {}
            print(f"  id={row['id']} slug={d.get('slug')!r} name={d.get('name')!r}", file=sys.stderr)
        sys.exit(2)

    if len(candidates) == 1:
        return candidates[0]

    print("Multiple application form_templates matched — pick one:", file=sys.stderr)
    for i, c in enumerate(candidates):
        d = c["data"]
        print(f"  [{i+1}] id={c['id']} slug={d.get('slug')!r} name={d.get('name')!r}", file=sys.stderr)
    choice = input("Enter number (or Ctrl-C to abort): ").strip()
    try:
        idx = int(choice) - 1
        return candidates[idx]
    except (ValueError, IndexError):
        print("Invalid choice.", file=sys.stderr)
        sys.exit(2)


def _add_field_if_missing(fields: list[dict], spec: dict, log: list[str]) -> bool:
    """Append spec to fields if no entry shares its name. Mutates fields
    in place. Returns True if added."""
    name = spec["name"]
    for f in fields:
        if isinstance(f, dict) and f.get("name") == name:
            log.append(f"  SKIP   {name}  (already present)")
            return False
    fields.append(spec)
    log.append(f"  ADD    {name}  ({spec.get('type','?')})")
    return True


def _patch_form_data(data: dict, log: list[str]) -> dict:
    """Return a deep-copied dict with business_state + industry added to
    the schema's field list."""
    new_data = copy.deepcopy(data)

    # The field list may live at data.schema.fields OR data.fields
    # depending on which form-template shape the dashboard wrote.
    schema = new_data.get("schema")
    if isinstance(schema, dict) and isinstance(schema.get("fields"), list):
        fields = schema["fields"]
    elif isinstance(new_data.get("fields"), list):
        fields = new_data["fields"]
    else:
        log.append("  WARN  no fields list found — synthesizing schema.fields")
        if not isinstance(schema, dict):
            new_data["schema"] = schema = {}
        schema["fields"] = []
        fields = schema["fields"]

    _add_field_if_missing(
        fields,
        {
            "name": "business_state",
            "type": "enum",
            "label": "Business State",
            "required": True,
            "enum_values": US_STATES,
            "help_text": (
                "SOP §4: feeds lender.restricted_states filter — pre-blocks "
                "lenders that don't fund this state"
            ),
        },
        log,
    )

    _add_field_if_missing(
        fields,
        {
            "name": "industry",
            "type": "enum",
            "label": "Industry",
            "required": True,
            "enum_values": SUNBIZ_INDUSTRIES,
            "help_text": (
                "SOP §4: feeds lender.restricted_industries filter — "
                "pre-blocks lenders that don't fund this industry"
            ),
        },
        log,
    )

    return new_data


def main() -> int:
    p = argparse.ArgumentParser(prog="seed_sunbiz_application_form_fields")
    p.add_argument("--dry-run", action="store_true", help="Print diff without writing")
    p.add_argument("--id", help="Skip auto-resolution; patch this form_template id")
    args = p.parse_args()

    sb = _supabase()

    if args.id:
        row = (
            sb.table("tenant_records")
            .select("id, data")
            .eq("id", args.id)
            .eq("tenant_id", SUNBIZ_TENANT_ID)
            .eq("entity_type", "form_template")
            .maybe_single()
            .execute()
        )
        if not row.data:
            print(f"ERROR: form_template {args.id} not found in SunBiz tenant.", file=sys.stderr)
            return 2
        target = {"id": row.data["id"], "data": row.data["data"] or {}}
    else:
        target = _resolve_form_template(sb)

    print(f"\nPatching SunBiz application form_template id={target['id']}")
    print(f"  slug={target['data'].get('slug')!r}  name={target['data'].get('name')!r}\n")

    log: list[str] = []
    patched = _patch_form_data(target["data"], log)

    print("Changes:")
    for line in log:
        print(line)

    if patched == target["data"]:
        print("\nNo changes — both fields already present. Exiting.")
        return 0

    if args.dry_run:
        print("\n--dry-run set, NOT writing.")
        return 0

    print("\nApplying patch...")
    result = (
        sb.table("tenant_records")
        .update({"data": patched})
        .eq("id", target["id"])
        .execute()
    )
    if not result.data:
        print("ERROR: update returned no data — check tenant_records row state.", file=sys.stderr)
        return 1

    print("Done.")
    print(
        "\nNext: the dashboard /forms editor will pick up the new fields on "
        "next load. Existing in-flight applications keep their old shape; "
        "only new submissions enforce the required business_state + industry.",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
