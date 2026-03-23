---
tags: [mistakes, prevention]
---
# MISTAKES LOG
> Every mistake logged with root cause and prevention. Check this BEFORE repeating a task type.

> [[brain/BRAIN_LOOP]] | [[memory/PATTERNS]] | [[memory/SELF_REFLECTIONS]]

### 2026-03-23 — Assumed shared _lib/ dynamic imports would bypass bundler
**What happened:** Spent multiple iterations trying dynamic imports from shared `api/_lib/stripe.ts`. Vercel's @vercel/nft traces ALL dependency paths regardless of import style.
**Prevention:** When debugging Vercel FUNCTION_INVOCATION_FAILED: create two minimal test endpoints (one with suspected import, one without) as FIRST diagnostic step.

### 2026-03-23 — Watchdog spawned 67+ zombie Python processes
**What happened:** `os.kill(pid, 0)` unreliable on Windows — watchdog thought daemon was dead every 5 minutes and spawned new ones. `/rl highest` made them unkillable without admin.
**Prevention:** On Windows use `tasklist`-based process detection, never `os.kill(pid, 0)`. Never use `/rl highest` for Task Scheduler tasks. Use `CREATE_NO_WINDOW` flag for headless daemons.

### 2026-03-19 — subprocess.run cp1252 UnicodeDecodeError on Windows
**What happened:** `text=True` defaults to cp1252 on Windows. Unicode chars (─, —, ✅) from child scripts cause decode failure.
**Prevention:** Any `subprocess.run(text=True)` on Windows MUST include `encoding="utf-8"`.

### 2026-03-16 — ta library ADXIndicator crashes on small slices
**What happened:** `adx(period=14)` needs 28 rows minimum (2×period). Strategy guard was only 25.
**Prevention:** When wrapping `ta` indicators, test with small slices. ADX needs `>= 2 * period` rows.

### 2026-03-04 — CLI Newline Escaping & IMAP Sent Sync
**Prevention:** Use `body.replace('\\n', '\n')` for CLI args. Append to IMAP Sent folder after SMTP send. Prefix URLs with `https://`.

### 2026-03-03 — Stale cross-references after file deletion
**What happened:** Deleted files left 15+ broken references across the project.
**Prevention:** After ANY file rename/delete, run `grep -rn "filename" --include="*.md"` across full project. Non-negotiable.

### 2026-03-03 — Stale counts in CAPABILITIES.md
**Prevention:** After adding/removing agents/skills/workflows, verify actual file counts match documented counts.

### 2026-03-02 — Double outreach email execution
**Prevention:** Scripts with external side effects MUST implement idempotency checks (sent flag, DB check) before execution.

### 2026-02-27 — Platform-specific mistakes (archived patterns)
- **Twitter char limit:** ALWAYS validate content length per platform BEFORE posting (X=280, Threads=500, IG=2200, LinkedIn=3000)
- **__future__ import ordering:** NEVER insert code above `__future__` import in Python files
- **PowerShell encoding:** Use `Out-File -Encoding utf8`, never `>` redirection for programmatic consumption
- **Inline JS scripts:** Write complex scripts to disk, don't golf inline `node -e` commands
- **Late MCP Pydantic:** Test with single call first. If schema error, report — don't patch SDK

*Last updated: 2026-03-23*
