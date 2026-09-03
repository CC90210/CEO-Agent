"""Region inference for outreach emails.

Given a lead row (dict from Turso `leads` table), return a phrase like
"the Collingwood area" or "the Toronto area" so outreach templates can say
"as a fellow local business owner in {{region}}" with the right geography.

Inference order:
  1. City name detected in company / contact / notes blob (most accurate).
  2. Phone area code → broad regional bucket.
  3. Generic "your area" fallback (template still reads naturally).

CC's directive 2026-04-27: build rapport via geo-matching. Truthful enough
since OASIS serves online and works with Ontario clients across regions.
The CASL legal address (Collingwood, ON) stays in the small grey footer.
"""
from __future__ import annotations
from typing import Optional


# Ontario phone area codes → regional phrase.
ONTARIO_AREA_CODES: dict[str, str] = {
    "705": "Central Ontario",
    "249": "Central Ontario",
    "416": "the Toronto area",
    "647": "the Toronto area",
    "437": "the Toronto area",
    "905": "the Greater Toronto area",
    "289": "the Greater Toronto area",
    "365": "the Greater Toronto area",
    "519": "Southwestern Ontario",
    "226": "Southwestern Ontario",
    "548": "Southwestern Ontario",
    "613": "the Ottawa area",
    "343": "the Ottawa area",
    "807": "Northwestern Ontario",
}

# City names — order matters, longer/more-specific first so "Niagara Falls"
# beats "Niagara" if we add it. All matched case-insensitively as substrings.
ONTARIO_CITIES: list[str] = [
    "Collingwood", "Wasaga Beach", "Wasaga", "Owen Sound", "Blue Mountain",
    "Thornbury", "Meaford", "Stayner", "Creemore", "Barrie", "Orillia",
    "Midland", "Penetanguishene",
    "Toronto", "Etobicoke", "Scarborough", "North York",
    "Hamilton", "Burlington", "Oakville", "Mississauga", "Brampton",
    "Markham", "Vaughan", "Richmond Hill", "Newmarket", "Aurora",
    "Oshawa", "Whitby", "Pickering", "Ajax",
    "London", "Kitchener", "Waterloo", "Cambridge", "Guelph", "Windsor",
    "Sarnia", "St. Catharines", "Niagara Falls", "Niagara",
    "Ottawa", "Kingston", "Belleville", "Peterborough",
    "Sudbury", "Thunder Bay", "Sault Ste. Marie", "North Bay", "Timmins",
]


def _normalize_phone(phone: Optional[str]) -> str:
    if not phone:
        return ""
    return "".join(ch for ch in phone if ch.isdigit())


def _area_code(phone: Optional[str]) -> Optional[str]:
    digits = _normalize_phone(phone)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) >= 3:
        return digits[:3]
    return None


def infer_region(lead: dict, default: str = "your area") -> str:
    """Return a region phrase for use in outreach templates.

    Prefers city detected in company/name/notes. Falls back to phone
    area code → regional phrase. Falls back to `default` if nothing
    matches. Always returns a string, never None.
    """
    if not lead:
        return default

    blob = " ".join([
        str(lead.get("company") or ""),
        str(lead.get("name") or ""),
        str(lead.get("notes") or ""),
        str(lead.get("city") or ""),
        str(lead.get("address") or ""),
    ]).lower()

    for city in ONTARIO_CITIES:
        if city.lower() in blob:
            return f"the {city} area"

    ac = _area_code(lead.get("phone"))
    if ac and ac in ONTARIO_AREA_CODES:
        return ONTARIO_AREA_CODES[ac]

    return default


if __name__ == "__main__":
    import json
    import sys
    if len(sys.argv) > 1:
        lead = json.loads(sys.argv[1])
        print(infer_region(lead))
    else:
        # Self-test
        cases = [
            ({"company": "Collingwood Charters"}, "the Collingwood area"),
            ({"company": "Iron Skillet", "phone": "(705) 429-1144"}, "Central Ontario"),
            ({"company": "Acme Co", "phone": "(416) 555-1212"}, "the Toronto area"),
            ({"company": "Acme Co", "phone": "905-555-1212"}, "the Greater Toronto area"),
            ({"company": "Burlington Bistro"}, "the Burlington area"),
            ({"company": "Acme Co"}, "your area"),
            ({}, "your area"),
        ]
        for lead, expected in cases:
            got = infer_region(lead)
            ok = "OK" if got == expected else "FAIL"
            print(f"  [{ok}] {lead} -> {got!r} (expected {expected!r})")
