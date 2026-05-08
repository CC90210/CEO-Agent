@echo off
REM Late (Zernio) MCP Server Wrapper — reads LATE_API_KEY from .env.agents at runtime
REM Never hardcode credentials here. All secrets live in .env.agents (gitignored).
setlocal enabledelayedexpansion

set "ENV_FILE=%~dp0..\.env.agents"

if not exist "%ENV_FILE%" (
    echo ERROR: .env.agents not found at %ENV_FILE% 1>&2
    exit /b 1
)

for /f "usebackq tokens=1,* delims==" %%a in ("%ENV_FILE%") do (
    if "%%a"=="LATE_API_KEY" set "LATE_API_KEY=%%b"
)

if not defined LATE_API_KEY (
    echo ERROR: LATE_API_KEY not found in .env.agents 1>&2
    exit /b 1
)

uvx --from late-sdk[mcp] late-mcp
