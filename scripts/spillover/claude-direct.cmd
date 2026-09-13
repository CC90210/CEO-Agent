@echo off
rem claude-direct: start Claude Code talking straight to https://api.anthropic.com.
rem It BYPASSES the Claude Spillover proxy entirely: no proxy, no fallback, no Python.
rem --settings outranks ~/.claude/settings.json, so the pinned ANTHROPIC_BASE_URL beats
rem the proxy URL for this session only. The process env var is pinned too, in case a
rem different value was inherited. All arguments pass through unchanged (%%*).
rem Use it when the proxy is down (ensure_spillover says so) or to force a direct session.
setlocal
set "ANTHROPIC_BASE_URL=https://api.anthropic.com"
claude --settings "{\"env\":{\"ANTHROPIC_BASE_URL\":\"https://api.anthropic.com\"}}" %*
exit /b %ERRORLEVEL%
