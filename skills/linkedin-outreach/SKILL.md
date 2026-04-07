---
name: linkedin-outreach
description: Use the CLI-Anything wrapper to send connection requests and messages on LinkedIn, completely bypassing UI/browser restrictions.
triggers: [LinkedIn, outreach, lead, prospect, DM, connection request]
tier: specialized
dependencies: [browser-automation]
---

# LinkedIn Outreach Engine (CLI-Anything)

## Overview
Because LinkedIn aggressively blocks Playwright-based DOM scraping (e.g., hiding buttons behind menus, removing 'Add a note' features), this skill uses the **Voyager API** (via `linkedin-api` Python package). It interacts directly with LinkedIn's internal endpoints exactly as the official mobile app does.

## Setup Requirements

1. **Credentials:** You must add the following to `.env.agents`:
   ```env
   LINKEDIN_EMAIL=your_email@domain.com
   LINKEDIN_PASSWORD=your_password
   ```

2. **Dependencies:**
   ```bash
   pip install linkedin-api click python-dotenv
   ```

## Usage Commands

All operations run through `scripts/linkedin_cli.py`.

### 1. Verify Authentication
Run this to ensure your credentials are valid and the API can authenticate:
```bash
python scripts/linkedin_cli.py verify
```

### 2. Send a Connection Request
Use the prospect's public username (the part of the URL after `/in/`).
For example, for `https://www.linkedin.com/in/john-doe-1234/`, the username is `john-doe-1234`.

```bash
python scripts/linkedin_cli.py connect john-doe-1234 --message "Hi John, I saw your work and wanted to connect. -CC"
```

### 3. Send a Direct Message
If you are already 1st-degree connections, you can DM them directly:
```bash
python scripts/linkedin_cli.py message john-doe-1234 "Hey John, following up on..."
```

## Advantages over Playwright
- **Speed:** Instant network requests. No waiting for page loads or random timeouts.
- **Reliability:** Immune to UI changes (A/B testing, changed CSS classes, hidden buttons).
- **Headless by Default:** Does not pop open a browser window or steal focus.
- **Agent Native:** Returns JSON output via standard `click` CLI patterns, making it easy for the Bravo agent to parse results and track campaign success in `memory/`.

## Obsidian Links
- [[skills/INDEX]] | [[brain/CAPABILITIES]]
