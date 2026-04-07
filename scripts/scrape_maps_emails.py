import asyncio
from playwright.async_api import async_playwright
import re
import json
import os
import csv
import time

CITIES = ["Collingwood", "Wasaga Beach", "Owen Sound", "Orillia", "Midland", "Stayner", "Meaford", "Thornbury", "Blue Mountains", "Barrie", "Newmarket", "Vaughan", "Richmond Hill", "Oakville", "Burlington", "Hamilton", "Kitchener", "London", "Guelph", "Kingston"]
NICHES = [
    ("HVAC", "HVAC"),
    ("Plumbing", "Plumber"),
    ("Roofing", "Roofer"),
    ("Physiotherapy", "Physiotherapist"),
    ("Chiropractic", "Chiropractor"),
    ("Landscaping", "Landscaper"),
    ("Med Spa", "Medical Spa"),
    ("Electrical", "Electrician"),
    ("Auto Repair", "Auto Repair"),
    ("Dentist", "Dentist")
]

CSV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "memory", "LEAD_TRACKER.csv")

def get_existing_emails():
    emails = set()
    if os.path.exists(CSV_PATH):
        try:
            with open(CSV_PATH, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    email = row.get('Email/Contact', '').lower().strip()
                    if email:
                        emails.add(email)
        except Exception as e:
            print(f"Warning: Could not read CSV: {e}")
    return emails

async def get_emails_from_url(page, url):
    try:
        # Check if the URL is valid
        if not url.startswith('http'): url = 'https://' + url
        await page.goto(url, timeout=10000, wait_until='domcontentloaded')
        content = await page.content()
        # Find mailto: links first
        mailto_emails = re.findall(r'mailto:([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', content)
        # Then regex for any email
        all_emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', content)
        
        emails = list(set(mailto_emails + all_emails))
        # Filter out common junk
        emails = [e.lower() for e in emails if not e.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg', 'sentry.io', 'email.com', 'example.com', 'wixpress.com', 'squarespace.com'))]
        return emails
    except:
        return []

async def scrape_google_maps(page, browser, city, category, niche_label, existing_emails, leads_list, target_count):
    query = f"{category} in {city} Ontario"
    print(f"\n--- Searching Google Maps: {query} ---")
    try:
        await page.goto(f"https://www.google.com/maps/search/{query.replace(' ', '+')}", timeout=15000)
        await page.wait_for_selector('div[role="feed"]', timeout=10000)
    except:
        print(f"  No results or captcha for {city} {category}")
        return

    # Extract business names and URLs
    links = await page.query_selector_all('a[aria-label]')
    business_links = []
    for link in links:
        label = await link.get_attribute('aria-label')
        href = await link.get_attribute('href')
        if label and href and "https://www.google.com/maps/place" in href:
            business_links.append((label, href))
    
    print(f"  Found {len(business_links)} businesses")
    
    # Store other businesses from same search as competitors
    competitor_pool = [b[0].split('|')[0].split('-')[0].strip() for b in business_links]

    for name, href in business_links:
        if len(leads_list) >= target_count: break
        
        clean_name = name.split('|')[0].split('-')[0].strip()
        print(f"  Checking {clean_name}...")
        
        try:
            # Go to details to find website
            await page.goto(href, timeout=10000)
            # Find website button or link
            website_link = await page.query_selector('a[data-item-id="authority"]')
            if website_link:
                url = await website_link.get_attribute('href')
                print(f"    Website: {url}")
                
                # Check website for email in a new tab
                email_page = await browser.new_page()
                emails = await get_emails_from_url(email_page, url)
                await email_page.close()
                
                if emails:
                    found_email = emails[0].lower().strip()
                    if found_email not in existing_emails and found_email not in [l['email'] for l in leads_list]:
                        # Pick a competitor from the same city/category
                        comp_name = "local competition"
                        for c in competitor_pool:
                            if c.lower() not in clean_name.lower() and clean_name.lower() not in c.lower():
                                comp_name = c
                                break
                        
                        leads_list.append({
                            "name": "there",
                            "business": clean_name.title(),
                            "email": found_email,
                            "city": city,
                            "category": niche_label,
                            "competitor": comp_name,
                            "website": url
                        })
                        print(f"    ✅ NEW LEAD: {found_email} (Comp: {comp_name})")
                    else:
                        print(f"    Skipping (existing): {found_email}")
                else:
                    print(f"    No email found on website.")
            else:
                print(f"    No website listed.")
        except Exception as e:
            print(f"    Error getting details: {e}")
        
        await asyncio.sleep(1)

async def main():
    existing_emails = get_existing_emails()
    leads = []
    target_total = 50
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # Use a real User-Agent
        page = await browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        for city in CITIES:
            if len(leads) >= target_total: break
            for category, niche_label in NICHES:
                if len(leads) >= target_total: break
                await scrape_google_maps(page, browser, city, category, niche_label, existing_emails, leads, target_total)
                # Save partial results
                with open("tmp/scraped_leads_maps.json", "w") as f:
                    json.dump(leads, f, indent=2)
                
        await browser.close()
    
    print(f"\nFinal total leads found: {len(leads)}")
    with open("tmp/scraped_leads_maps.json", "w") as f:
        json.dump(leads, f, indent=2)

if __name__ == "__main__":
    asyncio.run(main())
