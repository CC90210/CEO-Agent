@echo off
REM Supabase MCP Wrapper — reads credentials from .env.agents
REM This script is safe to commit to Git (no hardcoded keys)

set "ENV_FILE=%~dp0..\.env.agents"

REM Parse .env.agents for Supabase management token
for /f "usebackq tokens=1,* delims==" %%A in ("%ENV_FILE%") do (
    if "%%A"=="SUPABASE_ACCESS_TOKEN" set "SUPABASE_TOKEN=%%B"
)

npx -y @supabase/mcp-server-supabase@latest --access-token %SUPABASE_TOKEN%
