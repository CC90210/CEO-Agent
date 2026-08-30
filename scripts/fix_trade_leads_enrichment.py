"""
fix_trade_leads_enrichment.py — Enrich and clean up all CC Trade Leads in Turso.

Fixes:
1. Blank or generic business names ('trade name', 'trade business', '') -> Extracts clean name from URL domain or company name.
2. Missing descriptions & Battle Cards -> Formats rich, structured Battle Cards into notes, description, and audit_findings.
3. Maps all trade leads to WEBDEV_TENANT_ID (Oasis Web Studio) with vertical='CC Leads'.
"""

import sys
import json
import re
from urllib.parse import urlparse

sys.path.insert(0, 'scripts')
from lib.db_turso import get_db

# 2026-08-29: was 'ef8d389e…' (OASIS AI CRM tenant) — fourth instance of the
# wrong-tenant bug the Codex audit caught. Webdev = Oasis Web Studio.
WEBDEV_TENANT_ID = "42423fde-be8b-454f-932a-750e8c9b743d"

def domain_to_name(url):
    if not url:
        return None
    try:
        domain = urlparse(url).netloc or urlparse("http://" + url).netloc
        domain = re.sub(r'^www\.', '', domain.lower())
        parts = domain.split('.')
        if len(parts) > 1:
            name_part = parts[0]
            # Replace dashes/underscores with spaces
            name_part = name_part.replace('-', ' ').replace('_', ' ')
            # Split camelCase or concatenated words if possible
            words = re.findall(r'[A-Za-z]+|\d+', name_part)
            if words:
                clean_name = " ".join(w.capitalize() for w in words)
                # Specific cleanups
                clean_name = clean_name.replace('Hvac', 'HVAC').replace('Inc', 'Inc.').replace('Llc', 'LLC')
                return clean_name
    except Exception:
        pass
    return None

def build_battle_card(data, clean_name, city, province, phone, website):
    trade = data.get('industry') or data.get('niche') or 'Trades & Contractors'
    trade = trade.replace(' (CC Leads)', '')
    role = data.get('role') or 'Owner / Principal'
    findings = data.get('audit_findings') or ["Site audit pending — verify online presence on call"]
    if isinstance(findings, list):
        findings_str = " | ".join(findings)
    else:
        findings_str = str(findings)
    
    pitch = data.get('pitch_angle') or f"Local {trade} owner in {city} — pitch high-converting website rebuild and 24/7 missed-call text back."
    automations = data.get('automation_openings') or ["missed_call_recovery", "instant_quote_widget"]
    if isinstance(automations, list):
        auto_str = ", ".join(automations)
    else:
        auto_str = str(automations)

    card = (
        f"🎯 BATTLE CARD:\n"
        f"• Business: {clean_name}\n"
        f"• Industry: {trade}\n"
        f"• Contact Role: {role}\n"
        f"• Location: {city}, {province}\n"
        f"• Phone: {phone or 'N/A'}\n"
        f"• Website: {website or 'N/A'}\n"
        f"• Audit: {findings_str}\n"
        f"• Pitch Angle: \"{pitch}\"\n"
        f"• Recommended Automations: {auto_str}"
    )
    return card, findings_str, pitch

def run():
    db = get_db()
    rows = db.select('tenant_records', tenant_id=WEBDEV_TENANT_ID, where="data LIKE '%CC Leads%' OR data LIKE '%Trades%'", limit=1000)
    print(f"Loaded {len(rows)} trade lead tenant_records rows.")

    updated_count = 0
    for r in rows:
        raw = r['data']
        data = json.loads(raw) if isinstance(raw, str) else raw
        
        vertical = data.get('vertical')
        niche = data.get('niche') or ''
        is_cc_lead = vertical == 'CC Leads' or 'CC Leads' in str(data) or 'Trades' in str(niche)

        if not is_cc_lead:
            continue

        raw_name = (data.get('business_name') or data.get('name') or data.get('company') or '').strip()
        website = (data.get('website') or '').strip()
        phone = (data.get('phone') or '').strip()
        city = (data.get('business_city') or data.get('city') or 'Montreal').strip()
        province = (data.get('state') or data.get('region') or 'QC').strip()

        # Extract/clean name
        clean_name = raw_name
        if not clean_name or clean_name.lower() in ['', 'trade business', 'trade name', 'unnamed business', 'lead', 'null']:
            derived = domain_to_name(website)
            if derived:
                clean_name = derived
            else:
                clean_name = f"Local {data.get('niche', 'Trade')} Specialist ({city})"

        # Clean notes/battle card
        card, findings_str, pitch = build_battle_card(data, clean_name, city, province, phone, website)

        # Update data dictionary
        data['business_name'] = clean_name
        data['name'] = clean_name
        data['company'] = clean_name
        data['vertical'] = 'CC Leads'
        data['notes'] = card
        data['description'] = card
        data['summary'] = card
        data['audit_findings'] = [findings_str] if isinstance(findings_str, str) else findings_str
        data['pitch_angle'] = pitch

        # Update in database
        updated_data_json = json.dumps(data)
        db.execute('UPDATE tenant_records SET data = ? WHERE id = ? AND tenant_id = ?', [updated_data_json, r['id'], WEBDEV_TENANT_ID])
        updated_count += 1
        print(f"Updated lead {r['id']}: {clean_name} ({city}, {province})")

    print(f"\nSuccessfully enriched and cleaned {updated_count} CC Trade Leads!")

if __name__ == "__main__":
    run()
