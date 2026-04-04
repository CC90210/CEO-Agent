---
description: Batch push content to multiple Skool lessons from local content files
---
// turbo-all

## Trigger
`/skool-push <scope>`

Examples:
- `/skool-push all` — Push ALL courses (full redeploy)
- `/skool-push ai-foundations` — Push all lessons in AI Foundations
- `/skool-push live-closes L2 L3` — Push specific lessons only

## Skill
Load `skills/skool-automation/SKILL.md` for the full Playwright workflow reference.

## Steps

1. **Parse scope and build lesson queue:**
   - Reference `courses/SKOOL_REGISTRY.md` for course → lesson mapping
   - Build ordered list of lessons to push
   - Verify local content files exist for each lesson in queue
   - Report: "Pushing X lessons across Y courses. Proceed?"

2. **Confirm with CC before starting batch:**
   - Show the full list of lessons that will be updated
   - Wait for CC's go-ahead

3. **For each lesson in queue:**

   a. Navigate directly to lesson URL
      ```
      browser_navigate → lesson URL
      ```

   b. Snapshot and click edit
      ```
      browser_snapshot → find edit button → browser_click
      ```

   c. Snapshot and find editor
      ```
      browser_snapshot → find Tiptap editor ref
      ```

   d. Inject content from local file
      ```javascript
      browser_evaluate on editor ref:
      (el) => {
        el.innerHTML = `<CONTENT_FROM_FILE>`;
        el.dispatchEvent(new Event('input', { bubbles: true }));
        return 'injected';
      }
      ```

   e. Save via JS
      ```javascript
      browser_evaluate:
      () => {
        const saves = [...document.querySelectorAll('button')]
          .filter(b => b.textContent.trim() === 'SAVE' && !b.disabled);
        if (saves.length) { saves[0].click(); return 'clicked'; }
        return 'not found';
      }
      ```

   f. Wait 2 seconds
      ```
      browser_wait_for time=2
      ```

   g. Log result: "✅ [Course] L[X] — saved" or "❌ [Course] L[X] — FAILED: [reason]"

4. **Report results:**
   ```
   ## Skool Push Complete
   **Pushed:** X/Y lessons
   **Failed:** Z lessons (list with reasons)
   **Time:** ~Xm Ys
   ```

## Error Handling

- If not logged in → STOP, tell CC
- If edit button not found → skip lesson, log error, continue
- If SAVE returns "not found" → re-snapshot, retry once, then skip
- If navigation fails → retry once, then skip
- Never retry more than once per lesson — log and move on

## Speed Targets

- ~15-20 seconds per lesson (navigate + edit + inject + save + wait)
- Full 16-course push (~60 lessons): ~15-20 minutes
- Single course push (4-5 lessons): ~1-2 minutes

## Obsidian Links
- [[.agents/workflows/INDEX]] | [[brain/CAPABILITIES]]
