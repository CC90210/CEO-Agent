@echo off
REM Supabase MCP Server Wrapper — reads SUPABASE_ACCESS_TOKEN from .env.agents at runtime
REM Never hardcode credentials here. All secrets live in .env.agents (gitignored).
setlocal enabledelayedexpansion

set "ENV_FILE=%~dp0..\.env.agents"

if not exist "%ENV_FILE%" (
    echo ERROR: .env.agents not found at %ENV_FILE% 1>&2
    exit /b 1
)

for /f "usebackq tokens=1,* delims==" %%a in ("%ENV_FILE%") do (
    if "%%a"=="SUPABASE_ACCESS_TOKEN" set "SUPABASE_ACCESS_TOKEN=%%b"
)

if not defined SUPABASE_ACCESS_TOKEN (
    echo ERROR: SUPABASE_ACCESS_TOKEN not found in .env.agents 1>&2
    exit /b 1
)

npx -y @supabase/mcp-server-supabase@latest --access-token=%SUPABASE_ACCESS_TOKEN%
