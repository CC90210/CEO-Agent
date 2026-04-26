---
tags: [patterns, learning]
---
# LEARNED PATTERNS
> `[V]` = validated 3+. `[P]` = probationary. [[memory/MISTAKES]] | [[memory/SOP_LIBRARY]]

### [P] Daemon Redeploy (2026-04-02)
EDIT → KILL (by StartTime) → CLEAN (__pycache__) → VERIFY DEAD (log timestamps) → RESTART

### [V] Zernio Posting
Validate char limits → rewrite per platform → present to CC → post via ../CMO-Agent/scripts/late_tool.py

### [V] Query-First MCP — Question → tool → call → return real data. Never describe.

### [V] Cross-File Sync — Change config → update ALL refs. After delete: grep + fix.

### [V] MCP Error Recovery — Report error → suggest fix → STOP. Never retry loop.

### [V] Names — B2B: "Conaugh McKenna". DJ: "CC". Meet link != booking link.

### [V] Anti-Bloat — Update existing files. Lean brain = faster + more accurate.

### [V] Multi-Agent — Simple → Gemini. Architecture → Claude. Research → Anti-Gravity.

## Anti-Patterns
MCP failure → report+STOP | PowerShell → `Out-File -Encoding utf8` | Rewrite per platform | Context7 before coding | `grep -rn` before deleting
*Last updated: 2026-04-03*
