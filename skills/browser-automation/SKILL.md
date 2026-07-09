---
name: browser-automation
description: Comprehensive reference for browser automation using Playwright MCP. Use for web research, testing, scraping, form filling, screenshots, and any browser-based interaction on UNPROTECTED sites. For bot-protected sites (Cloudflare, DataDome, reCAPTCHA), escalate to CloakBrowser instead — see Bot-Protection Escalation Ladder below.
triggers: [playwright, browser, navigate, screenshot, click, snapshot, web research, scrape]
tier: standard
dependencies: []
last_updated: 2026-05-15
---

# Browser Automation with Playwright MCP

## Bot-Protection Escalation Ladder (mandatory before any fresh-session scrape)

Before reaching for Playwright MCP on a third-party site, classify the target:

```
0. DEFAULT for "fetch URL content" → use research_fetch (V6.7+, 2026-05-16):
       python scripts/research_fetch.py <url> --json
   Auto-escalates Firecrawl → CloakBrowser based on actual response and
   remembers which tier worked per domain. Skill: skills/research-fetch/SKILL.md.

The tiers below are still the authoritative mental model and remain useful when
you need a tier's unique features (Firecrawl extract/crawl/map, Cloak
interactive goto, Harness CC-auth, Playwright snapshot).

1. Public unprotected page (need Firecrawl-specific features) →
       python scripts/integrations/firecrawl_tool.py scrape <url>

2. Bot-protected (Cloudflare Turnstile, reCAPTCHA v3, DataDome, ShieldSquare,
   FingerprintJS, Akamai, Kasada, PerimeterX) OR Firecrawl returned 403/429/empty
   AND you need to force the stealth tier or use its interactive features →
       python scripts/browser/cloak_browser_tool.py scrape <url> --json
   (research_fetch handles the escalation for you in the common case)

3. Need to act AS CC inside CC's logged-in account → use Browser Harness
   (CC's real Chrome on port 9222) — see skills/browser-harness/SKILL.md.

4. ONLY use Playwright MCP (this skill) when the site is unprotected AND you
   need interactive flow / visual snapshots / screenshots beyond what
   Firecrawl gives.
```

Raw Playwright MCP fingerprints are obvious to modern bot defenses. Cloudflare typically blocks within 1-3 requests. If you see a Turnstile widget, an "Are you a robot?" page, or a 403 from Cloudflare, **stop and switch to CloakBrowser** — do not retry Playwright.

Full reference: [[skills/cloak-browser/SKILL.md]] · [[skills/web-scraping/SKILL.md]] · [[skills/browser-harness/SKILL.md]].

---

## Core Workflow
1. **Navigate:** `browser_navigate` to URL
2. **Snapshot:** `browser_snapshot` to get accessibility tree with refs
3. **Interact:** Use refs from snapshot to click, type, fill forms
4. **Re-snapshot:** After any navigation or DOM change, refs become stale — always re-snapshot
5. **Screenshot:** `browser_take_screenshot` for visual verification

## Navigation
```
browser_navigate          url="https://example.com"
browser_navigate_back     (go back)
browser_close             (close page)
browser_tabs              action="list|new|close|select"
```

## Page Analysis (ALWAYS do this before interacting)
```
browser_snapshot          → Full accessibility tree with element refs
browser_take_screenshot   type="png" → Visual capture (can't act on this, use snapshot)
browser_console_messages  level="error" → JS console output
browser_network_requests  includeStatic=false → API calls and failures
```

## Interactions (use refs from browser_snapshot)
```
browser_click             ref="ref123"  element="Submit button"
browser_type              ref="ref456"  text="hello@email.com"
browser_fill_form         fields=[{name:"Email", type:"textbox", ref:"ref456", value:"hello@email.com"}]
browser_hover             ref="ref789"  element="Menu item"
browser_select_option     ref="ref012"  values=["option1"]
browser_press_key         key="Enter"
browser_drag              startRef="ref1" endRef="ref2"
browser_file_upload       paths=["/path/to/file.pdf"]
```

## Screenshots & Recording
```
browser_take_screenshot   type="png"                    → Viewport capture
browser_take_screenshot   type="png" fullPage=true      → Full scrollable page
browser_take_screenshot   ref="ref123" element="Chart"  → Specific element
browser_take_screenshot   filename="evidence.png"       → Save to specific file
```

## JavaScript Execution
```
browser_evaluate    function="() => document.title"
browser_evaluate    function="() => document.querySelectorAll('.item').length"
browser_evaluate    ref="ref123" function="(el) => el.textContent"
```

## Waiting
```
browser_wait_for    text="Success"              → Wait for text to appear
browser_wait_for    textGone="Loading..."        → Wait for text to disappear
browser_wait_for    time=3                       → Wait N seconds
```

## Viewport & Settings
```
browser_resize      width=1080 height=1920       → Portrait mobile
browser_resize      width=1920 height=1080       → Desktop
browser_resize      width=375 height=812         → iPhone size
```

## Dialog Handling
```
browser_handle_dialog    accept=true              → Accept alert/confirm
browser_handle_dialog    accept=false             → Dismiss
browser_handle_dialog    accept=true promptText="input"  → Fill prompt dialog
```

## Common Patterns

### Web Research
```
1. browser_navigate → search engine or target URL
2. browser_snapshot → find links/content
3. browser_click → navigate to result
4. browser_snapshot → read content
5. Repeat as needed
```

### Form Submission
```
1. browser_navigate → form page
2. browser_snapshot → get refs for all fields
3. browser_fill_form → fill all fields at once
4. browser_click → submit button ref
5. browser_wait_for → success message
6. browser_snapshot → verify result
```

### Authentication Flow
```
1. browser_navigate → login page
2. browser_snapshot → get email/password refs
3. browser_type → email field
4. browser_type → password field
5. browser_click → sign in button
6. browser_wait_for → dashboard text or URL change
7. browser_snapshot → verify logged in
```

### Screenshot Evidence Chain
```
1. browser_take_screenshot filename="step1-before.png"
2. [perform action]
3. browser_wait_for text="Expected result"
4. browser_take_screenshot filename="step2-after.png"
```

### Responsive Testing
```
1. browser_resize width=375 height=812    → Test mobile
2. browser_take_screenshot filename="mobile.png"
3. browser_resize width=768 height=1024   → Test tablet
4. browser_take_screenshot filename="tablet.png"
5. browser_resize width=1440 height=900   → Test desktop
6. browser_take_screenshot filename="desktop.png"
```

## Critical Rules

1. **ALWAYS re-snapshot after navigation or DOM changes** — refs become invalid
2. **Use browser_snapshot for actions, browser_take_screenshot for evidence** — screenshots are visual only
3. **Check browser_console_messages for JS errors** after page loads
4. **Use browser_wait_for before interacting** with dynamically loaded content
5. **Close the browser** when done: `browser_close`
6. **Never hardcode selectors** — always discover via snapshot refs
7. **For research:** Prefer Playwright over WebFetch for any page that requires JavaScript

## Two Modes: MCP (Interactive) vs CLI (Data Extraction)

| Need | Use | How |
|------|-----|-----|
| **Data from a page** (text, links, tables) | **CLI script** | `node .claude/skills/playwright/scripts/run.js <url>` |
| **Interactive session** (login, click flows, Stripe/Vercel dashboard work) | **MCP tools** | `browser_navigate`, `browser_snapshot`, etc. |
| **Batch scrape** (10+ pages) | **CLI script** | Loop over URLs, get JSON back |
| **Visual verification** | **MCP screenshot** | `browser_take_screenshot` |

### Token Cost Comparison

| Approach | 10 pages scraped | Data format | Context cost |
|----------|-----------------|-------------|-------------|
| MCP screenshots | 20,000-30,000 tokens | Claude interprets image | Massive |
| **CLI script** | **200-500 tokens** | **Clean JSON** | **Minimal** |

**Rule:** Default to CLI for data extraction. Use MCP only for stateful interactive sessions.

Full CLI reference: `.claude/skills/playwright/SKILL.md`

---

## Resilient Selector Strategy

When interacting with elements, use this priority order. Higher entries are more stable across page updates.

```
Priority 1 — data-testid attributes (most stable — purpose-built for automation)
  ref = element with data-testid="submit-button"

Priority 2 — ARIA roles and labels (accessible and semantic)
  ref = button with aria-label="Submit form"
  ref = input with aria-label="Email address"

Priority 3 — Text content (readable but fragile if copy changes)
  ref = button containing text "Submit"

Priority 4 — CSS selectors (structure-dependent — breaks on redesigns)
  ref = .submit-btn (use only if above options unavailable)

Priority 5 — XPath (last resort — extremely brittle)
  browser_evaluate function="() => document.evaluate('//button[text()=\"Submit\"]', document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue"
```

**Rule:** Always use `browser_snapshot` first to discover what refs and roles are available. Never hardcode a selector you haven't verified from a live snapshot.

---

## Wait Strategies

Flaky automation almost always fails because of premature interaction — clicking before an element is ready. Use these strategies in order of preference.

### Strategy 1 — Wait for Text (Most Reliable)

```
browser_wait_for    text="Dashboard"          → Wait until page confirms navigation
browser_wait_for    text="Loading..."         → Wait for loader to appear
browser_wait_for    textGone="Loading..."     → Wait for loader to disappear
browser_wait_for    text="Error"              → Detect failure state early
```

### Strategy 2 — Wait for Specific Time (Fallback Only)

```
browser_wait_for    time=2    → Wait 2 seconds (use only when no text signal exists)
```

Use time-based waits only for:
- Animations completing before screenshot
- Rate-limited actions (posting, submitting forms)
- Third-party redirects with no visible text change

**Maximum wait time:** 10 seconds. If an expected element hasn't appeared in 10 seconds, it's a failure — screenshot and report, do not keep waiting.

### Strategy 3 — Network Idle (via Evaluate)

For SPAs where content loads after the page shell:

```javascript
// Wait for any in-flight XHR/fetch to complete
browser_evaluate function="() => new Promise(resolve => {
  if (document.readyState === 'complete') { resolve(); return; }
  window.addEventListener('load', resolve);
})"
```

---

## Error Recovery Patterns

When an action fails, follow this recovery sequence. Never silently retry the same action more than twice.

### Recovery Sequence

```
Step 1: Take a screenshot immediately
  browser_take_screenshot filename="error-state-[timestamp].png"

Step 2: Check console for errors
  browser_console_messages level="error"

Step 3: Check network for failures
  browser_network_requests includeStatic=false

Step 4: Diagnose
  - 404/500 from API → backend issue, not automation issue
  - JS error → page broke during interaction
  - Element not found → selector stale, re-snapshot
  - Page blank → navigation failed, try browser_navigate again

Step 5: Retry with modified approach (max 2 retries)
  Retry 1: Re-snapshot → get fresh refs → retry interaction
  Retry 2: Navigate back to the start of the flow → re-snapshot → retry from beginning

Step 6: If 2 retries fail → surface to CC with screenshot and error logs. Do not attempt Fix 3.
```

### Retry with Backoff (for Rate-Limited Pages)

```
Attempt 1: Immediate
Attempt 2: Wait 3 seconds, retry
Attempt 3: Wait 10 seconds, retry
If all 3 fail: Stop. Report the failure with the screenshot taken in Step 1.
```

---

## Session Persistence (Cookie and Auth State)

For flows that require authentication, preserve session state across multi-step operations.

### Pattern — Authenticate Once, Reuse Session

```
Step 1: Navigate to login page
  browser_navigate url="[login-url]"

Step 2: Authenticate
  browser_snapshot → get email/password field refs
  browser_type ref="[email-ref]" text="[email from .env.agents]"
  browser_type ref="[password-ref]" text="[password from .env.agents]"
  browser_click ref="[submit-ref]" element="Sign in button"

Step 3: Verify authenticated state
  browser_wait_for text="[Dashboard / Home / indicator that login worked]"
  browser_snapshot → confirm you're on the right page

Step 4: Proceed with the actual task
  [All subsequent navigation inherits the authenticated session]
  [Do NOT navigate back to the login page mid-flow — session persists in the same browser context]
```

### Session Expiry Detection

Before running any authenticated flow, verify the session is still valid:

```
browser_snapshot → look for "Sign in", "Log in", or "Session expired" text
If found → re-authenticate before proceeding
If not found → session is active, continue
```

**Warning:** Never store passwords in markdown files, session logs, or any file tracked by git. Credentials come only from `.env.agents` at runtime.

---

## Multi-Tab Orchestration

For workflows that require parallel browser contexts (e.g., comparing two pages, opening multiple results).

### Open and Switch Between Tabs

```
# Open a new tab
browser_tabs action="new"
browser_navigate url="[second-url]"

# List all open tabs (returns tab IDs)
browser_tabs action="list"

# Switch to a specific tab
browser_tabs action="select" index=0   → tab 1 (original)
browser_tabs action="select" index=1   → tab 2

# Close a specific tab
browser_tabs action="close" index=1
```

### Multi-Tab Pattern — Parallel Data Collection

```
Step 1: Open Tab 1 → navigate to Source A → browser_snapshot → extract data A
Step 2: Open Tab 2 → navigate to Source B → browser_snapshot → extract data B
Step 3: Switch back to Tab 1 → proceed with comparison or combined action
Step 4: Close all secondary tabs → browser_tabs action="close" (for each)
Step 5: browser_close when done
```

**Rule:** Never have more than 3 tabs open simultaneously. Each tab costs context tokens for its snapshot. Two tabs is optimal for comparison workflows.

---

## Obsidian Links
- [[skills/INDEX.md]] | [[brain/CAPABILITIES]] | [[skills/e2e-testing/SKILL.md]]
