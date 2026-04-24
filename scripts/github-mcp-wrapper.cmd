@echo off
REM GitHub MCP Server Wrapper — reads credentials from .env.agents at runtime
REM Never hardcode credentials here. All secrets live in .env.agents (gitignored).
setlocal enabledelayedexpansion

REM Locate .env.agents relative to this script (scripts\ is one level below repo root)
set "ENV_FILE=%~dp0..\.env.agents"

if not exist "%ENV_FILE%" (
    echo ERROR: .env.agents not found at %ENV_FILE%
    exit /b 1
)

REM Extract GITHUB_PERSONAL_ACCESS_TOKEN
for /f "usebackq tokens=1,* delims==" %%a in ("%ENV_FILE%") do (
    if "%%a"=="GITHUB_PERSONAL_ACCESS_TOKEN" set "GITHUB_PERSONAL_ACCESS_TOKEN=%%b"
)

if not defined GITHUB_PERSONAL_ACCESS_TOKEN (
    echo ERROR: GITHUB_PERSONAL_ACCESS_TOKEN not found in .env.agents
    exit /b 1
)

npx -y @modelcontextprotocol/server-github
