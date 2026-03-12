import os
import json
import time
import random
import requests
from outreach_engine import send_outreach

# Load leads
LEADS_FILE = os.path.join("tmp", "scraped_leads_maps.json")
with open(LEADS_FILE, "r") as f:
    leads = json.load(f)

# Telegram Config
TELEGRAM_TOKEN = "8210144004:AAHS4zmx1vAIRNwj0ysmCrr04W1zySZOsw8"

def send_telegram(message):
    """Try to send a message to the user via Telegram by finding the latest chat ID."""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
        res = requests.get(url).json()
        if res["ok"] and res["result"]:
            # Get all unique chat IDs from recent updates
            chat_ids = set()
            for update in res["result"]:
                if "message" in update:
                    chat_ids.add(update["message"]["chat"]["id"])
            
            for chat_id in chat_ids:
                send_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
                requests.post(send_url, json={"chat_id": chat_id, "text": message})
                print(f"Telegram sent to {chat_id}")
        else:
            print("No recent Telegram updates found to identify chat ID.")
    except Exception as e:
        print(f"Error sending Telegram: {e}")

def execute_outreach():
    print(f"Starting outreach for {len(leads)} leads...")
    send_telegram(f"🏋️ Gym session outreach started. Target: {len(leads)} leads.")
    
    success_count = 0
    error_count = 0
    
    for i, lead in enumerate(leads):
        print(f"[{i+1}/{len(leads)}] Sending to {lead['email']} ({lead['name']})...")
        
        # Determine business type
        b_type = lead.get("category", "Service")
        
        # Send via outreach engine
        res = send_outreach(
            lead_name=lead["name"],
            lead_email=lead["email"],
            business_name=lead["business"],
            business_type=b_type,
            meeting_datetime="2026-03-12T14:00:00", # Suggesting tomorrow at 2pm
            dry_run=False
        )
        
        if res["status"] == "sent":
            success_count += 1
        else:
            error_count += 1
            print(f"  FAILED: {res.get('error', 'Unknown error')}")
            
        # Pacing: 30-90 seconds between emails to avoid spam filters
        if i < len(leads) - 1:
            delay = random.uniform(30, 90)
            print(f"  Pacing: Sleeping for {delay:.1f}s...")
            time.sleep(delay)
            
        # Update every 5 sends
        if (i + 1) % 5 == 0:
            send_telegram(f"✅ Outreach update: {i+1}/{len(leads)} processed. ({success_count} sent, {error_count} failed)")

    final_msg = f"🏁 Outreach Blitz Complete!\nTotal: {len(leads)}\nSuccess: {success_count}\nFailed: {error_count}\nOnly good things."
    print(final_msg)
    send_telegram(final_msg)

if __name__ == "__main__":
    execute_outreach()
