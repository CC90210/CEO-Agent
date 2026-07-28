---
name: webapp-testing
description: Toolkit for interacting with and testing local web applications using Playwright. Supports verifying frontend functionality, debugging UI behavior, capturing browser screenshots, and viewing browser logs.
license: Complete terms in LICENSE.txt
triggers: [webapp test, local app test, frontend test, browser test, UI test]
tier: standard
dependencies: [browser-automation]
tags: [skill, webapp-testing]
last_updated: 2026-05-21
---

# Web Application Testing

To test local web applications, write native Python Playwright scripts.

> **Note:** A `scripts/with_server.py` helper (Anthropic-reference utility for server lifecycle management) is referenced in the original skill but is NOT bundled here. Start the dev server in a separate terminal (or with `subprocess.Popen` + `time.sleep`/`wait_for_port`) before running Playwright. The patterns below show both approaches.

## Decision Tree: Choosing Your Approach

```
User task → Is it static HTML?
    ├─ Yes → Read HTML file directly to identify selectors
    │         ├─ Success → Write Playwright script using selectors
    │         └─ Fails/Incomplete → Treat as dynamic (below)
    │
    └─ No (dynamic webapp) → Is the server already running?
        ├─ No → Start the dev server in another terminal
        │        (e.g., `npm run dev`), wait for it to bind the port,
        │        then run your Playwright script
        │
        └─ Yes → Reconnaissance-then-action:
            1. Navigate and wait for networkidle
            2. Take screenshot or inspect DOM
            3. Identify selectors from rendered state
            4. Execute actions with discovered selectors
```

## Example: Managing the server yourself

```bash
# Terminal 1: start the dev server
npm run dev

# Terminal 2: once the port is bound, run your automation
python your_automation.py
```

Or wrap the lifecycle in your Python script:

```python
import subprocess, socket, time
proc = subprocess.Popen(["npm", "run", "dev"], cwd="frontend")
# Wait until port 5173 is accepting connections
for _ in range(60):
    with socket.socket() as s:
        try: s.connect(("127.0.0.1", 5173)); break
        except OSError: time.sleep(0.5)
try:
    # ... Playwright automation ...
    pass
finally:
    proc.terminate()
```

Then the Playwright body looks the same as the bundled-helper version:
```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True) # Always launch chromium in headless mode
    page = browser.new_page()
    page.goto('http://localhost:5173') # Server already running and ready
    page.wait_for_load_state('networkidle') # CRITICAL: Wait for JS to execute
    # ... your automation logic
    browser.close()
```

## Reconnaissance-Then-Action Pattern

1. **Inspect rendered DOM**:
   ```python
   page.screenshot(path='/tmp/inspect.png', full_page=True)
   content = page.content()
   page.locator('button').all()
   ```

2. **Identify selectors** from inspection results

3. **Execute actions** using discovered selectors

## Common Pitfall

❌ **Don't** inspect the DOM before waiting for `networkidle` on dynamic apps
✅ **Do** wait for `page.wait_for_load_state('networkidle')` before inspection

## Best Practices

- **Use bundled scripts as black boxes** - To accomplish a task, consider whether one of the scripts available in `scripts/` can help. These scripts handle common, complex workflows reliably without cluttering the context window. Use `--help` to see usage, then invoke directly. 
- Use `sync_playwright()` for synchronous scripts
- Always close the browser when done
- Use descriptive selectors: `text=`, `role=`, CSS selectors, or IDs
- Add appropriate waits: `page.wait_for_selector()` or `page.wait_for_timeout()`

## Reference Files

- **examples/** - Examples showing common patterns:
  - `element_discovery.py` - Discovering buttons, links, and inputs on a page
  - `static_html_automation.py` - Using file:// URLs for local HTML
  - `console_logging.py` - Capturing console logs during automation
## Obsidian Links
- [[skills/INDEX.md]] | [[brain/CAPABILITIES]]
