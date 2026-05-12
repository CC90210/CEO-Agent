---
description: Edit a single Skool lesson or the About page using Playwright browser automation
---
// turbo-all

## Trigger
`/skool-edit <target>`

Examples:
- `/skool-edit about` — Edit the About page description
- `/skool-edit ai-foundations L1` — Edit lesson 1 of AI Foundations
- `/skool-edit live-closes L3` — Edit lesson 3 of Live Closes

## Skill
Load `skills/skool-automation/SKILL.md` for the full Playwright workflow reference.

## Steps

1. **Parse the target:**
   - If "about" → About page edit flow
   - Otherwise → parse course slug + lesson number
   - Reference `courses/SKOOL_REGISTRY.md` for course details

2. **Check for local content file:**
   - Look in `courses/` directory for matching content file
   - If found, load the HTML content from file
   - If not found, ask CC what content to inject (or write new content)

3. **Navigate to Skool:**
   - `browser_navigate` to the target URL
   - `browser_snapshot` to verify page loaded and we're logged in
   - If not logged in, STOP and tell CC to log in manually

4. **Enter edit mode:**
   - For lessons: Click the Edit button (second button near lesson title)
   - For about: Click on the description content area (cursor=pointer)
   - `browser_snapshot` to verify Tiptap editor is active

5. **Inject content:**
   ```javascript
   browser_evaluate on editor ref:
   (el) => {
     el.innerHTML = `<CONTENT_HTML>`;
     el.dispatchEvent(new Event('input', { bubbles: true }));
     return 'injected';
   }
   ```

6. **Save:**
   ```javascript
   browser_evaluate:
   () => {
     const saves = [...document.querySelectorAll('button')]
       .filter(b => b.textContent.trim() === 'SAVE' && !b.disabled);
     if (saves.length) { saves[0].click(); return 'clicked'; }
     return 'not found';
   }
   ```

7. **Wait & verify:**
   - `browser_wait_for time=2`
   - `browser_snapshot` to confirm content saved
   - Report success to CC

## About Page Character Limit
The About page has a hard 1000-character limit. Always check the counter after injecting content. If over limit, compress the copy.

## Obsidian Links
- [[.agents/workflows/INDEX]] | [[brain/CAPABILITIES]]


## Related (graph)

- [[.agents/workflows/INDEX]]
- [[.agents/workflows/browser-harness]]
- [[.agents/workflows/ceo-briefing]]
- [[.agents/workflows/cli-anything]]
