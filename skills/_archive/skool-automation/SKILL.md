---
name: skool-automation
description: Manage Skool community content (lessons, about page, courses) using Playwright MCP browser automation
triggers: [Skool, lesson, classroom, community, Tiptap, course, Skool edit]
tier: specialized
dependencies: [browser-automation]
disable-model-invocation: true
tags: [skill, archive, _archive]
last_updated: 2026-05-21
---

# Skool Automation — Community Content Management

## Overview

Manage Skool community content (lessons, about page, courses) using Playwright MCP browser automation. No official Skool API exists — all operations use the browser.

**Registry:** `courses/SKOOL_REGISTRY.md` — master list of all courses, lessons, URLs, and local content paths.

## Prerequisites

- Logged into Skool as admin (Conaugh McKenna account) in the Playwright browser session
- Playwright MCP connected and working
- Target community: `https://www.skool.com/agency-accelerants-6209`

## Operations

### 1. Edit a Lesson

**Input:** Course name + lesson number + HTML content (from file or inline)

**Steps:**
```
1. Navigate to the lesson URL in Skool Classroom
   browser_navigate → https://www.skool.com/agency-accelerants-6209/classroom

2. Click into the target course, then the target lesson
   browser_snapshot → find course link → browser_click
   browser_snapshot → find lesson link → browser_click

3. Click the Edit button (second button in the button group near lesson title)
   browser_snapshot → identify edit button → browser_click

4. Find the Tiptap editor content div
   browser_snapshot → find element with class "tiptap ProseMirror skool-editor2"
   The editor is a contenteditable div inside the lesson body

5. Inject HTML content via JavaScript
   browser_evaluate on the editor ref:
   (el) => {
     el.innerHTML = `<CONTENT_HTML>`;
     el.dispatchEvent(new Event('input', { bubbles: true }));
     return 'injected';
   }

   CRITICAL: The input event with bubbles:true is required to enable the SAVE button.

6. Click SAVE via JavaScript (avoids stale ref issues)
   browser_evaluate:
   () => {
     const saves = [...document.querySelectorAll('button')]
       .filter(b => b.textContent.trim() === 'SAVE' && !b.disabled);
     if (saves.length) { saves[0].click(); return 'clicked'; }
     return 'not found';
   }

7. Wait 2 seconds for save to complete
   browser_wait_for → time=2
```

**Known Issues:**
- `browser_wait_for text="Page updated"` sometimes times out — use `time=2` instead
- For empty lessons, the editor may be a `<p>` element — use `el.closest('.tiptap') || el.parentElement` to find the container
- Refs become stale after ANY navigation or DOM change — always re-snapshot

### 2. Edit the About Page

**Steps:**
```
1. Navigate to About page
   browser_navigate → https://www.skool.com/agency-accelerants-6209/about

2. Click on the description content area (ref with cursor=pointer containing the about text)
   browser_snapshot → find the content wrapper → browser_click
   This opens the inline Tiptap editor with Cancel/Save buttons

3. Note the character limit: 1000 characters max
   The counter shows at bottom of editor (e.g., "835 / 1000")

4. Inject HTML content via browser_evaluate on the editor ref
   Same pattern as lesson editing

5. Click Save button (regular ref click works here, or use JS method)

6. Wait 2 seconds for save
```

**Known Issues:**
- Admin toolbar dropdown can intercept clicks — dismiss with:
  ```javascript
  () => {
    const bg = document.querySelector('.styled__DropdownBackground-sc-1c1jt59-11');
    if (bg) { bg.remove(); return 'removed'; }
    return 'not found';
  }
  ```
- Or press Escape first, then remove dropdown via JS if it persists

### 3. Batch Push (Multiple Lessons)

**Steps:**
```
1. Load content files from courses/ directory
   Each lesson has an HTML file with the gamified content

2. For each lesson in sequence:
   a. Navigate directly to lesson URL (faster than clicking through UI)
   b. Click edit button
   c. Inject content
   d. Save
   e. Wait 2 seconds
   f. Navigate to next lesson

3. Report results: X/Y lessons updated successfully
```

**Speed Optimization:**
- Navigate directly to lesson URLs instead of clicking through the classroom UI
- Use JS evaluate for SAVE clicks (no stale ref issues)
- 2-second wait between saves is sufficient (no need for text-based waits)
- Process lessons sequentially within a course, then move to next course

### 4. Create a New Course

Skool course creation must be done through the UI:
```
1. browser_navigate → https://www.skool.com/agency-accelerants-6209/classroom
2. browser_snapshot → find "New course" or "+" button
3. browser_click → create course button
4. Fill in course name, description, and settings
5. Add lessons one by one using the lesson creation flow
6. Edit each lesson with content using Operation 1
```

## HTML Content Format

All lesson content uses Tiptap-compatible HTML:

```html
<h2>Title — Subtitle</h2>
<p></p>
<p><strong>XP Reward: +XXX XP</strong> | Running Total: X,XXX XP</p>
<p><strong>Level: Name (LX)</strong> — Description.</p>
<p></p>
<h3>Section Header</h3>
<p>Content paragraph.</p>
<p></p>
<p><strong>Callout Type:</strong> Callout text.</p>
```

**Supported Tiptap elements:**
- `<h2>`, `<h3>` — Headers (h1 not used in lessons)
- `<p>` — Paragraphs (empty `<p></p>` for spacing)
- `<strong>` — Bold text
- `<em>` — Italic text
- `<ul>`, `<ol>`, `<li>` — Lists
- `<blockquote>` — Quotes
- `<code>` — Inline code
- `<a href="">` — Links

**NOT supported in Tiptap on Skool:**
- `<div>` — converted to `<p>`
- `<span>` — stripped
- `<table>` — not rendered
- Custom CSS/styles — stripped
- `<img>` — must be added manually through Skool's image upload

## Gamification Callout Patterns

```
⚡ QUICK WIN:     — Easy dopamine hit, small action
💡 PRO TIP:       — Expert insight, non-obvious
💀 COMMON MISTAKE: — What NOT to do
🧠 KEY TAKEAWAY:  — Core concept to remember
🔥 CHALLENGE:     — Hands-on exercise with XP
🏆 BOSS LEVEL:    — End-of-lesson capstone challenge
⚠️ WARNING:       — Critical gotcha or danger zone
✅ CHECKPOINT:     — Progress verification step
```

## Level Progression

| Level | Name | XP Range | Badge |
|-------|------|----------|-------|
| L0 | Explorer | 0-999 | Day 0 |
| L1 | Builder | 1,000-4,999 | Days 1-3 |
| L2 | Integrator | 5,000-9,999 | Days 4-6 |
| L3 | Architect | 10,000-14,999 | Days 7-10 |
| L4 | Operator | 15,000+ | Agency Blueprint |

## Adapting for Other Communities

This skill works for ANY Skool community CC manages (DJ, AI agency, etc.):
1. Create a new registry file: `courses/SKOOL_REGISTRY_<community>.md`
2. Update the base URL in all navigation steps
3. Same Playwright automation patterns apply — Skool's editor is identical across communities
4. Content format and gamification patterns are reusable

## Obsidian Links
- [[skills/INDEX.md]] | [[brain/CAPABILITIES]]
