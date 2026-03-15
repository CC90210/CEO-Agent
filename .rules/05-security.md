---
description: Security rules — never hardcode secrets, validate inputs
---

# Security Protocol

- **NEVER** hardcode API keys, tokens, or passwords in any file
- All credentials live in `.env.agents` (gitignored)
- If an exposed secret is detected: **STOP** and initiate rotation immediately
- Validate all inputs at system boundaries
- Enforce RLS on Supabase — never leave tables publicly accessible
- Sandbox risky scripts in `tmp/`
- Confirm with CC before any destructive database operations
- MCP credential servers use `scripts/*-wrapper.cmd` — credentials read at runtime from `.env.agents`
