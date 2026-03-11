import os
import asyncio
import random
from playwright.async_api import async_playwright
from dotenv import load_dotenv

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env.agents'))

# Persistent profile location
PROFILE_DIR = os.path.join(os.path.dirname(__file__), "chrome_profile")

# LEADS LIST (Top 10 from our Blitz list)
LEADS = [
    {"name": "Brian Young", "company": "Home Painters Toronto", "url": "https://www.linkedin.com/in/brianyounghomepainterstoronto", "type": "painter"},
    {"name": "Caleb", "company": "519 Painters", "url": "https://www.linkedin.com/in/caleb-519-painters", "type": "painter"},
    {"name": "Jonathan Sarafinchin", "company": "Encore Painting Toronto", "url": "https://www.linkedin.com/in/jonathan-sarafinchin-0a1b1b1b", "type": "painter"},
    {"name": "Ed Medeiros", "company": "CertaPro Brampton", "url": "https://www.linkedin.com/in/ed-medeiros-0a1b1b1b", "type": "painter"},
    {"name": "Corey", "company": "Precision Painting", "url": "https://www.linkedin.com/in/corey-precision-painting", "type": "painter"},
    {"name": "Teresa Matamoros", "company": "Garden Holistics", "url": "https://www.linkedin.com/in/teresa-matamoros-71a1a121", "type": "wellness"},
    {"name": "Dr. Melissa Longo", "company": "Thrive Chiropractic", "url": "https://www.linkedin.com/in/drmelissalongo", "type": "wellness"},
    {"name": "Sunny Gill", "company": "Full Range Physio", "url": "https://www.linkedin.com/in/sunny-gill-0a1b1b1b", "type": "wellness"},
    {"name": "Jonathan Hutton", "company": "Basque Landscaping", "url": "https://www.linkedin.com/in/jonathan-hutton-7b1b1b1b", "type": "landscaping"},
    {"name": "Jason Newkirk", "company": "JN Roofing", "url": "https://www.linkedin.com/in/jason-newkirk-0a1b1b1b", "type": "roofing"}
]

TEMPLATES = {
    "painter": "Hi {name}, I came across {company} and noticed the scale of projects you're handling in Ontario. I'm curious — how are you managing the gap between a new inquiry and a finalized quote when the crews are at max capacity? Not sure if this would even be relevant for you, but we've been helping service businesses automate that 'middle' piece so no leads slip through. Worth a quick look?",
    "wellness": "Hi {name}, love what you're doing at {company}. I noticed your team is heavily focused on patient experience — just wondering, what happens to the inquiries that come in after hours or when the front desk is slammed? We build systems that handle that follow-up automatically so the experience stays 5-star without the manual burnout. Open to seeing how that works?",
    "default": "Hi {name}, I'm CC, building OASIS AI here in Collingwood. I saw {company}'s work and it's top-tier. I'm currently working with a few owners to automate their lead nurture and review cycles so they can step away from the inbox. Not sure if you're already 100% automated there, but thought I'd reach out. Worth a 2-minute chat?"
}

async def send_message(page, lead):
    """Navigates to a profile and sends a connection request with a personalized message."""
    print(f"Processing lead: {lead['name']} ({lead['company']})")
    await page.goto(lead['url'])
    await asyncio.sleep(random.uniform(4, 6))
    
    try:
        # 1. Try to find the Connect button directly
        connect_button = page.get_by_role("button", name="Connect").first
        
        # 2. If not visible, look in the 'More' menu
        if not await connect_button.is_visible():
            print(f"Connect button not immediate for {lead['name']}, checking 'More' menu...")
            more_button = page.get_by_role("button", name="More actions").first
            if await more_button.is_visible():
                await more_button.click()
                await asyncio.sleep(1)
                connect_button = page.locator('div[role="button"]:has-text("Connect")').first
        
        if await connect_button.is_visible():
            print(f"Found Connect button for {lead['name']}")
            await connect_button.click()
            await asyncio.sleep(2)
            
            # 3. Handle 'How do you know?' popup if it appears
            other_option = page.get_by_role("button", name="Other").first
            if await other_option.is_visible():
                await other_option.click()
                await page.get_by_role("button", name="Connect").click()
                await asyncio.sleep(1)

            # 4. Click 'Add a note'
            add_note_button = page.get_by_role("button", name="Add a note").first
            if await add_note_button.is_visible():
                await add_note_button.click()
                await asyncio.sleep(1)
                
                # Fill the message
                template = TEMPLATES.get(lead['type'], TEMPLATES['default'])
                message = template.format(name=lead['name'].split()[0], company=lead['company'])
                
                await page.fill('textarea[name="message"]', message)
                await asyncio.sleep(1)
                
                # 5. Send!
                send_button = page.get_by_role("button", name="Send").first
                if await send_button.is_visible():
                    await send_button.click()
                    print(f"SUCCESS: Connection request sent to {lead['name']}")
                    return True
            else:
                print(f"No 'Add a note' button for {lead['name']}")
        else:
            print(f"Could not find Connect button for {lead['name']}. Might be already connected or restricted.")
    except Exception as e:
        print(f"Error processing {lead['name']}: {e}")
    
    return False

async def main():
    print("Initializing Deep-Outreach LinkedIn Blitz...")
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=PROFILE_DIR,
            headless=False,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720}
        )
        
        page = context.pages[0] if context.pages else await context.new_page()
        
        # Verify login
        await page.goto("https://www.linkedin.com/feed/")
        await asyncio.sleep(3)
        
        if not await page.locator('a[href*="/in/"]').first.is_visible():
            print("Session expired or not found. Please log in again.")
            return

        # Process leads 5-10
        success_count = 0
        for lead in LEADS[5:]:
            if await send_message(page, lead):
                success_count += 1
            await asyncio.sleep(random.uniform(7, 12))
            
        print(f"Blitz complete. {success_count} connection requests sent.")
        await context.close()

if __name__ == "__main__":
    asyncio.run(main())
