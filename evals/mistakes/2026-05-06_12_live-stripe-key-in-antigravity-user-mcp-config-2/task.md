# Regression: Live Stripe Key in Antigravity User MCP Config — 2-Month Plaintext Leak (2026-05-06)

## What went wrong
`C:\Users\User\AppData\Roaming\Antigravity\User\mcp.json` contained a live Stripe restricted key (`rk_live_...`), live Supabase access token (`sbp_...`), and live n8n bearer JWT — all in plaintext, on disk, since 2026-03-01. The 2026-03-11 "MCP Security Hardening" sweep migrated `.claude/mcp.json`, `.vscode/mcp.json`, and `~/.gemini/settings.json` to wrapper-script pattern reading from `.env.agents`, but **missed the Antigravity-IDE-native user MCP config** — it lives in a different config tree that `claude mcp list` doesn't surface. Stripe MCP `v0.3.1` later switched to OAuth proxy mode and rejected `--api-key`, causing 60s subprocess-init timeouts on every new chat spawn — masking the real issue (broken MCP) on top of the security issue (plaintext live key) for 2+ months. CC discovered t

## The behavior that must NOT recur
1. **`scripts/audit_mcp_secrets.py` (NEW)** — scans 11 known MCP config locations across all four IDEs/CLIs for plaintext live secrets (Stripe `sk_live_` / `rk_live_`, Anthropic `sk-ant-`, OpenAI `sk-proj-`, Supabase `sbp_`, JWTs, GitHub PATs, AWS keys, Late `sk_42…`). Recognizes `[REDACTED-…]` tags as safe. Emits human or `--json` output. Exit 1 on any leak. Run: `python scripts/audit_mcp_secrets.py`.
2. **SessionStart hook wired** — `.claude/settings.local.json` now runs the audit on every Claude Code session boot via `python scripts/audit_mcp_secrets.py --quiet`. Future regressions surface immediately, not in 2 months.
3. **Three new wrappers** — `scripts/supabase-mcp-wrapper.cmd`, `scripts/n8n-mcp-wrapper.cmd`, `scripts/late-mcp-wrapper.cmd`. Same pattern as `github-mcp-wrapper.cmd`: `
