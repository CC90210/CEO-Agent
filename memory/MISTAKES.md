# MISTAKES LOG
> Every mistake logged with root cause and prevention. Check this BEFORE repeating a task type.

### 2026-03-19 — scheduler.py subprocess.run cp1252 UnicodeDecodeError on Windows
**What happened:** `bravo-scheduler` (PM2) restarted 4 times. `Monthly Metrics Snapshot` cron job was logging `FAILED (exit 1): UnicodeEncodeError: 'charmap' codec can't encode character '\u2500'`. `scheduler.py`'s `run_script()` used `subprocess.run(..., text=True)` without specifying encoding. On Windows, `text=True` defaults to the system locale encoding (`cp1252`), which cannot represent Unicode box-drawing characters printed by `revenue_engine.py` and `stripe_tool.py`.
**Root cause:** `subprocess.run(text=True)` on Windows uses `locale.getpreferredencoding()` = cp1252. Child scripts printing `\u2500` (─), `\u2014` (—), checkmarks (`\u2705`), etc. cause a decode failure in the parent process.
**Fix applied:** Added `encoding="utf-8"` to the `subprocess.run()` call in `run_script()` (`scripts/scheduler.py` line 181).
**Prevention:** Any `subprocess.run(text=True)` on Windows MUST include `encoding="utf-8"` explicitly. Apply this rule to all future subprocess wrappers in this project.

### 2026-03-16 — ta library ADXIndicator crashes on slices smaller than 2*period
**What happened:** `RSIMeanReversionStrategy` (and any strategy using `adx()`) threw `IndexError: index 14 is out of bounds` during backtesting. The backtesting engine passes growing slices `df.iloc[:i+1]` to each strategy. When the slice had fewer than `2 * period` rows, `ta.trend.ADXIndicator.adx()` crashed with an index-out-of-bounds error inside the ta library itself.
**Root cause:** The `ta` library's `ADXIndicator` requires at least `2 * window` rows to compute correctly (it needs one full `window` for True Range + another for smoothing). The strategy's `_min_bars` guard was set to `max(periods) + 5 = 25`, but `adx(period=14)` needs `28` rows minimum. The strategy guard fired too late.
**Fix applied:** Added a `len(df) < 2 * period` guard at the top of `adx()` in `strategies/technical/indicators.py` that returns a NaN-filled DataFrame instead of calling ta. This is safe because all strategies check `.iloc[-1]` against NaN or use `_min_bars` guards that would have already returned `None`.
**Prevention:** When wrapping `ta` indicators, test with small slices during development. For ADX specifically, always require `>= 2 * period` rows, not just `>= period`. Consider adding similar guards to other multi-pass indicators (ATR, Stochastic RSI) proactively.

### 2026-03-04 — CLI Newline Escaping & IMAP Sent Sync Failure
**What happened:** Emails sent via `scripts/send_email.py` from the command line contained literal `\n` characters instead of line breaks, and were not visible in the Gmail "Sent" folder.
**Root cause:** Shell arguments treat `\n` as a literal string. Additionally, SMTP-only sending does not trigger a sync to the IMAP 'Sent' folder in Gmail.
**Prevention:** 
1. **Newline Fix:** In Python scripts, use `body.replace('\\n', '\n')` to decode escaped newlines passed from the CLI.
2. **IMAP Sync:** Manually append sent messages to `"[Gmail]/Sent Mail"` via `imaplib` to ensure visibility.
3. **URL Formatting:** Always prefix domain links with `https://` to ensure they are clickable in plain-text email clients.

---

### 2026-02-27 — Pydantic `__future__` Syntax Error via Monkey Patching
**What happened:** A regex text replacement prepended `import typing` to `models.py` in the Late SDK cache, inadvertently moving `from __future__ import annotations` from line 1 to line 2. This caused a `SyntaxError` that prevented the whole MCP server from booting.
**Root cause:** Python inherently requires `__future__` module imports to appear at the absolute top of the file before any other code or imports. Monkey patching without checking for `__future__` headers violated this.
**Prevention:** Whenever monkey patching Python files, always use `sed` or regex to append lines *after* the `__future__` block, or explicitly check for its existence first. Never indiscriminately prepend to line 1.

### 2026-02-27 — Exceeded Twitter Character Limit via Late API
**What happened:** The API rejected the payload with "Tweet text is too long", throwing a 207 Multi-Status error where LinkedIn succeeded and Twitter failed.
**Root cause:** I failed to calculate the string length of the payload and cross-reference it with the target platform's specifications (Twitter max characters = 280) before attempting to submit the post.
**Prevention:** **PRE-FLIGHT CHECK PROTOCOL**: Before sending any content to an external API (like social media), calculate the exact payload length and assert it against the platform's known limitations. Do not guess or assume.

### 2026-02-27 — Powershell Output Redirection Encoding (UTF-16LE)
**What happened:** Reading a `>` redirected file output from PowerShell in Node.js failed because the `JSON.parse` could not interpret the string.
**Root cause:** PowerShell's default output encoding for `>` redirection is `UTF-16LE`, whereas Node expects `UTF-8` or standard ASCII. 
**Prevention:** Avoid `>` redirection in PowerShell when capturing command outputs for programmatic environments (like Node/Python). Use `Out-File -Encoding utf8` or, preferably, write the file explicitly within the tool script (e.g. `fs.writeFileSync`).

### 2026-02-27 — Inline JS String Escape Syntax Errors
**What happened:** A Node.js inline script (`node -e "..."`) crashed because unescaped single quotes within the JS payload conflicted with the outer command's execution context.
**Root cause:** Attempting to write complex JSON schemas or multi-line strings directly into terminal arguments creates parsing chaos.
**Prevention:** For complex requests or texts, always write a dedicated `.js` or `.py` file to disk using the file writer tool, run it traditionally (`node script.js`), and delete it afterward. Stop trying to golf inline scripts.

### 2026-02-27 — Late MCP Pydantic Schema Crash
**What happened:** Late API returns `profileId` as a dict object, but the Late Python SDK Pydantic models expect a string. Calls to `accounts_list`, `profiles_list`, `posts_list` fail with validation errors.
**Root cause:** Late API schema changed; SDK models not updated.
**Prevention:** Before using Late list operations, test with a single call first. If Pydantic error occurs, report to CC — do NOT patch SDK files from within agent code.

### 2026-02-27 — X/Twitter Post Rejected for Length
**What happened:** Content drafted for LinkedIn (3000 char limit) was sent to X (280 char limit). Late API returned Error Code 207 "Tweet text is too long."
**Root cause:** No per-platform character validation before posting.
**Prevention:** ALWAYS validate content length against platform limits BEFORE calling Late MCP. See social-publisher.md for the limits table.

### 2026-02-27 — __future__ Import Ordering Broke Late MCP Server
**What happened:** Patching Pydantic models in uv cache to fix profileId pushed `from __future__ import annotations` to line 2 instead of line 1, causing a Python SyntaxError on server boot.
**Root cause:** `__future__` imports must be the first statement in a Python file. The patch inserted an import above it.
**Prevention:** When patching Python SDK files, NEVER insert code above the `__future__` import line. Verify the file loads after patching: `python -c "import module"`.

### 2026-03-01 — Gemini CLI Writes Literal `\n` Instead of Newlines to Markdown Files
**What happened:** Gemini CLI sessions appended to SESSION_LOG.md but wrote literal backtick-n characters instead of actual newline characters, corrupting the markdown formatting.
**Root cause:** Gemini CLI's headless file-write operation (likely via `write_to_file` or similar) does not properly interpret escape sequences in string content. The `\n` characters are treated as literal text rather than newline escape codes.
**Prevention:** After any Gemini CLI session that modifies memory files, the next Claude Code session should verify file integrity. Add a SESSION_LOG encoding check to the heartbeat protocol. If Gemini CLI must write multi-line content, use actual file operations with proper line breaks rather than string concatenation.

### 2026-03-02 — Double Outreach Email Execution
**What happened:** I executed the outreach campaign script twice (`scripts/execute_campaign.js`), resulting in 13 leads receiving two separate (though slightly different) emails with overlapping Google Meet invites.
**Root cause:** I ran the initial version of the script to "get it done," and then, upon receiving further instructions for personalization and DJ-specific logic, I updated the script and *ran it again* without checking if the previous run had already successfully dispatched emails to the same list. I prioritized "perfection" of the content over the "safety" of the delivery frequency.
**Prevention:** **IDEMPOTENCY CHECK**: Any script that performs external side effects (email, social post, API call) MUST implement a state-check (e.g., reading a `SENT.json` or checking a database flag) before execution. Furthermore, as an agent, I must always verify whether a previous execution was successful before attempting a "better" version of the same action.

### 2026-03-03 — 15+ Stale Cross-References After File Consolidation
**What happened:** Deleted `AGENT_CORE_DIRECTIVES.md` and `brain/ROUTING_MAP.md` as redundancies. However, 15+ files across agents/, commands/, skills/, APPS_CONTEXT/, memory/, and brain/ still referenced the deleted files. Any agent loading those documents would have been directed to read non-existent files.
**Root cause:** **NO REFERENTIAL INTEGRITY CHECK.** When files are renamed or deleted, there is no protocol to scan the entire project for references to those files. Changes are made to the target but the web of cross-references is left broken.
**Prevention:** After ANY file rename/delete/move, run `grep -rn "deleted_filename" --include="*.md"` across the full project. Added to `/commit` workflow as mandatory pre-commit step. Added to BRAIN_LOOP Step 10 (HEAL).

### 2026-03-03 — Stale Counts in CAPABILITIES.md (12→14 agents, 40→41 skills)
**What happened:** CAPABILITIES.md listed "Sub-Agents (12)" when 14 existed in agents/ folder. Skills listed as 40 when 41 existed. Workflows listed as 10 when 11 existed.
**Root cause:** **NO AUTOMATED COUNT VERIFICATION.** Hardcoded numbers are scattered across documentation files. When a new agent/skill/workflow is added, nobody updates the counts in CAPABILITIES.md, README.md, or entry points.
**Prevention:** During `/commit` or `/sync`, verify actual file counts against documented counts. Count formula: `ls agents/*.md | wc -l` vs what CAPABILITIES.md says.

### 2026-03-03 — Redundant Files Never Formally Deprecated
**What happened:** `AGENT_CORE_DIRECTIVES.md` existed alongside 4 entry points that contained the same information. Over time, edits went to the entry points but the "core directives" file became stale without anyone noticing.
**Root cause:** **NO DEPRECATION LIFECYCLE.** When a file's responsibilities are absorbed by other files, the old file is never formally marked deprecated. It lingers, confusing agents about which is the source of truth.
**Prevention:** When merging/consolidating files, immediately: 1) Delete the old file, 2) Grep for ALL references to it, 3) Update every reference, 4) Log the deprecation in CHANGELOG.md. Added as "File Deprecation Protocol" in INTERACTION_PROTOCOL.md.

### 2026-03-04 — CLI Newline Escaping & IMAP Sent Sync Failure
**What happened:** Emails sent via `scripts/send_email.py` from the command line contained literal `\n` characters instead of line breaks, and were not visible in the Gmail "Sent" folder.
**Root cause:** Shell arguments treat `\n` as a literal string. Additionally, SMTP-only sending does not trigger a sync to the IMAP 'Sent' folder in Gmail.
**Prevention:** 
1. **Newline Fix:** In Python scripts, use `body.replace('\\n', '\n')` to decode escaped newlines passed from the CLI.
2. **IMAP Sync:** Manually append sent messages to `"[Gmail]/Sent Mail"` via `imaplib` to ensure visibility.
3. **URL Formatting:** Always prefix domain links with `https://` to ensure they are clickable in plain-text email clients.

---
