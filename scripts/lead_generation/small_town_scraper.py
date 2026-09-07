"""Small Town Lead Scraper

This script acts as a specialized wrapper around the primary ScrapeGraphAI lead
scraper, targeting small towns in Ontario where business owners are more likely
to be directly contactable and involved in the day-to-day operations.

It focuses on niches like chiropractors, med spas, hair salons, and local shops.

Usage:
  python scripts/lead_generation/small_town_scraper.py --target 50
"""

import sys
import argparse
from pathlib import Path

# Add scripts directory to path to import the main scraper
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

try:
    import scrape_firecrawl_leads
except ImportError:
    print("Error: Could not import scrape_firecrawl_leads.py. Make sure it exists in the scripts/ directory.")
    sys.exit(1)


SMALL_TOWNS = [
    "Collingwood", "Stayner", "Wasaga Beach", "Midland", "Orillia", 
    "Bracebridge", "Huntsville", "Gravenhurst", "Port Elgin", "Goderich", 
    "Stratford", "St. Marys", "Paris", "Elora", "Fergus", "Meaford", 
    "Thornbury", "Creemore"
]

SMALL_BUSINESS_NICHES = [
    "chiropractor", "med spa", "hair salon", "barbershop", 
    "physiotherapy", "dentist", "optometrist", "massage therapy",
    "boutique", "local cafe", "plumbing", "hvac", "roofing"
]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=int, default=50,
                   help="Stop scraping after this many qualified leads (default 50)")
    parser.add_argument("--cities", default=",".join(SMALL_TOWNS),
                        help="Comma-separated list of cities to scrape")
    parser.add_argument("--niches", default=",".join(SMALL_BUSINESS_NICHES),
                        help="Comma-separated list of niches to scrape")
    parser.add_argument("--dry-run", action="store_true",
                   help="Don't write to Turso, just produce the JSON")
    parser.add_argument("--json", action="store_true", help="Output JSON summary")
    parser.add_argument("--tenant", default=None,
                   help="Tenant UUID to stamp on inserted leads")
    
    # We intercept the arguments to override the defaults for scrape_firecrawl_leads
    args = parser.parse_args()
    
    # We must patch sys.argv so that when scrape_firecrawl_leads.main() calls parse_args,
    # it gets our overridden values.
    patched_argv = [sys.argv[0]]
    patched_argv.extend(["--target", str(args.target)])
    patched_argv.extend(["--cities", args.cities])
    patched_argv.extend(["--niches", args.niches])
    if args.dry_run:
        patched_argv.append("--dry-run")
    if args.json:
        patched_argv.append("--json")
    if args.tenant:
        patched_argv.extend(["--tenant", args.tenant])
        
    sys.argv = patched_argv
    
    print(f"Starting Small Town Scraper targeted at {len(args.cities.split(','))} towns and {len(args.niches.split(','))} niches.")
    print("Delegating to primary ScrapeGraphAI lead engine...")
    
    # Run the main scraper
    scrape_firecrawl_leads.main()

if __name__ == "__main__":
    main()
