
import sys
import os
from pathlib import Path

# Add scripts to path
scripts_dir = Path("c:/Users/User/Business-Empire-Agent/scripts")
sys.path.insert(0, str(scripts_dir))

from email_template import render_branded_html

body = "Yo, what's up? Let's get in a meeting sometime soon."
subject = "Quick Catch Up"
html = render_branded_html(body, subject=subject)

with open("c:/Users/User/Business-Empire-Agent/scratch/gen_html.html", "w", encoding="utf-8") as f:
    f.write(html)

print("HTML generated successfully.")
