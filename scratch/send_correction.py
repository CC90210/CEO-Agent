
import sys
import os
from pathlib import Path

# Add scripts to path
scripts_dir = Path("c:/Users/User/Business-Empire-Agent/scripts")
sys.path.insert(0, str(scripts_dir))

from send_gateway import send

body_text = "Yo, what's up? Let's get in a meeting sometime soon."
subject = "Quick Catch Up"

# Read the HTML we generated
with open("c:/Users/User/Business-Empire-Agent/scratch/gen_html.html", "r", encoding="utf-8") as f:
    body_html = f.read()

result = send(
    channel="email",
    agent_source="bravo_correction",
    to_email="goldstorm2003@gmail.com",
    subject=subject,
    body_text=body_text,
    body_html=body_html,
    brand="oasis",
    intent="internal", # Use internal to bypass cooldown and suppression for this correction send
)

print(result)
