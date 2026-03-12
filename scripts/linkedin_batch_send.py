import os
import json
import subprocess
import time
import random

LEADS = [
    {"username": "brianyounghomepainterstoronto", "company": "Home Painters Toronto", "type": "painter"},
    {"username": "caleb-519-painters", "company": "519 Painters", "type": "painter"},
    {"username": "jonathan-sarafinchin-0a1b1b1b", "company": "Encore Painting Toronto", "type": "painter"},
    {"username": "ed-medeiros-0a1b1b1b", "company": "CertaPro Brampton", "type": "painter"},
    {"username": "corey-precision-painting", "company": "Precision Painting", "type": "painter"},
    {"username": "teresa-matamoros-71a1a121", "company": "Garden Holistics", "type": "wellness"},
    {"username": "drmelissalongo", "company": "Thrive Chiropractic", "type": "wellness"},
    {"username": "sunny-gill-0a1b1b1b", "company": "Full Range Physio", "type": "wellness"},
    {"username": "jonathan-hutton-7b1b1b1b", "company": "Basque Landscaping", "type": "landscaping"},
    {"username": "jason-newkirk-0a1b1b1b", "company": "JN Roofing", "type": "roofing"}
]

TEMPLATES = {
    "painter": "Hi, I came across {company} and noticed the scale of projects you're handling in Ontario. I'm curious — how are you managing the gap between a new inquiry and a finalized quote when the crews are at max capacity? Not sure if this would even be relevant for you, but we've been helping service businesses automate that 'middle' piece so no leads slip through. Worth a quick look?",
    "wellness": "Hi, love what you're doing at {company}. I noticed your team is heavily focused on patient experience — just wondering, what happens to the inquiries that come in after hours or when the front desk is slammed? We build systems that handle that follow-up automatically so the experience stays 5-star without the manual burnout. Open to seeing how that works?",
    "default": "Hi, I'm CC, building OASIS AI here in Collingwood. I saw {company}'s work and it's top-tier. I'm currently working with a few owners to automate their lead nurture and review cycles so they can step away from the inbox. Not sure if you're already 100% automated there, but thought I'd reach out. Worth a 2-minute chat?"
}

def send_outreach(lead):
    template = TEMPLATES.get(lead['type'], TEMPLATES['default'])
    message = template.format(company=lead['company'])
    
    print(f"Sending to {lead['username']} ({lead['company']})...")
    
    cmd = [
        "python", "scripts/linkedin_cli.py", "connect", 
        lead['username'], 
        "--message", message
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"SUCCESS: {result.stdout.strip()}")
        else:
            print(f"FAILED: {result.stderr.strip()}")
    except Exception as e:
        print(f"ERROR: {str(e)}")

if __name__ == "__main__":
    print(f"Starting LinkedIn Blitz for {len(LEADS)} leads...")
    for lead in LEADS:
        send_outreach(lead)
        # Wait between 15 and 45 seconds between sends for safety
        delay = random.uniform(15, 45)
        print(f"Sleeping for {delay:.1f}s...")
        time.sleep(delay)
    print("Blitz complete.")
