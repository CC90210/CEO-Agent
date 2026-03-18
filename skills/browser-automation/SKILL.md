---
name: browser-automation
description: Comprehensive reference for browser automation using Playwright MCP. Use for web research, testing, scraping, form filling, screenshots, and any browser-based interaction. This is the primary browser tool for all Claude Code and Gemini CLI operations.
triggers: [playwright, browser, navigate, screenshot, click, snapshot, web research, scrape]
tier: standard
dependencies: []
---

# Browser Automation with Playwright MCP

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

## Comparison: Playwright MCP vs agent-browser CLI
| Feature | Playwright MCP (ours) | agent-browser CLI |
|---------|----------------------|-------------------|
| Platform | Windows, Mac, Linux | Linux/macOS/WSL only |
| Integration | Native MCP tool calls | Shell commands |
| Refs | `ref="refXXX"` from snapshot | `@e1, @e2` from snapshot |
| Forms | `browser_fill_form` (batch) | `fill @e1 "text"` (one at a time) |
| Sessions | Single session | `--session name` (parallel) |
| State save | Not built-in | `state save/load` |
| Recording | Not built-in | `record start/stop` |
| Accessibility | `browser_snapshot` | `snapshot -i` |

**Our Playwright MCP covers all essential workflows.** agent-browser adds session persistence and recording but requires Linux/WSL.
