# Lead Cleanup & Enrichment Handover

## 🎯 Objective
The command centre currently contains over 30,000 leads. Many of these are low-quality, generic corporate entries without a direct business owner identified or a direct phone number. 

Our core philosophy is **Quality over Quantity**. The sales reps need highly targeted leads where they can reach the actual business owner. Your task is to mass-filter, enrich, and delete unqualified leads. **If this means deleting more than half of the 30k+ database, do it.**

## 🛑 Critical System Context
- **Database Engine:** We use **Turso (libSQL)**, *not* Supabase. All database interactions must happen via Turso.
- **CLI Tooling:** Use `python scripts/integrations/turso_tool.py` for CLI reads, and the `lib.db_turso` module (or `integrations.supabase_tool`'s Turso compatibility layer) for Python scripts.
- **Tenant Scoping:** The `leads` table is tenant-scoped! Any `SELECT` or `DELETE` must include the `tenant_id` predicate, or you must explicitly pass `allow_unscoped=True` with a reason.
- **Destructive Operations:** You have explicit permission to run `DELETE FROM leads...` as part of this specific cleanup mandate.

## 🔍 The 2-Step Enrichment Pipeline
The standard enrichment process was recently upgraded in `scripts/scrape_firecrawl_leads.py`. It uses a two-step method to find owner cell phones and social profiles, bypassing generic website footers:
1. **Discovery:** Find the company name and owner name.
2. **Deep Enrichment:** Use `ScrapeGraphAI` to run a targeted DuckDuckGo search: `"{Owner Name} {Company Name} {City} LinkedIn owner phone number"`.

## 🛠️ Execution Plan

### Step 1: Audit the Leads
1. Query the Turso `leads` table.
2. Identify leads that do not have a distinct `first_name` / `name`, or lack an `owner_phone` in their `notes` / metadata. 

### Step 2: Enrich or Delete
You will need to write a Python script (e.g., `scripts/mass_lead_cleanup.py`) that loops through the unqualified leads:
1. **Try to Enrich:** If the lead has a company name but no owner, try to scrape their website using Firecrawl or ScrapeGraph to find an owner name. If you find an owner, run the DuckDuckGo enrichment search to get their direct phone number and LinkedIn.
2. **Delete if Unsalvageable:** If the lead is a generic corporation (e.g. "Walmart", "Home Depot"), has no identifiable owner, or no direct contact info can be enriched, **delete the lead row entirely**.

### Step 3: Implement the Script
Below is a foundational template for your cleanup script. **Review it, refine it, and run it.**

```python
import sys
from lib.db_turso import get_db

def main():
    db = get_db()
    
    # 1. Fetch leads that might be generic/unqualified
    # (Update WHERE clause based on how empty names are stored)
    print("Fetching leads to audit...")
    leads = db.query(
        "SELECT id, name, company, website, notes FROM leads WHERE name = '' OR name IS NULL",
        allow_unscoped=True,
        reason="Mass lead cleanup and optimization"
    )
    
    print(f"Found {len(leads)} leads missing owner names.")
    
    delete_ids = []
    
    for lead in leads:
        # TODO: Call the enrichment pipeline here.
        # Example logic:
        # owner_name = extract_owner_from_website(lead['website'])
        # if owner_name:
        #     enrich_data = _enrich_owner(owner_name, lead['company'])
        #     update_lead_in_turso(lead['id'], enrich_data)
        # else:
        
        # If no owner can be found, mark for deletion
        delete_ids.append(lead['id'])
        
    # 2. Mass Delete Unqualified Leads
    if delete_ids:
        print(f"Deleting {len(delete_ids)} unqualified leads...")
        for i in range(0, len(delete_ids), 100):
            chunk = delete_ids[i:i+100]
            placeholders = ",".join(["?"] * len(chunk))
            db.query(
                f"DELETE FROM leads WHERE id IN ({placeholders})",
                params=chunk,
                allow_unscoped=True,
                reason="Mass deletion of low-quality generic leads"
            )
        print("Deletion complete.")

if __name__ == "__main__":
    main()
```

## 📝 Next Steps for the AI
When you assume this context:
1. Validate the number of total leads using `python scripts/integrations/turso_tool.py sql "SELECT COUNT(*) FROM leads" --allow-unscoped --reason "Audit"`.
2. Review `scripts/scrape_firecrawl_leads.py` (specifically `_enrich_owner`) to understand the exact API payloads for ScrapeGraph.
3. Finalize the cleanup script and execute it to prune the database down to only high-quality, owner-verified leads.
