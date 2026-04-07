@echo off
REM Firecrawl MCP Server Wrapper — reads credentials from .env.agents at runtime
REM Never hardcode credentials here. All secrets live in .env.agents (gitignored).
REM
REM ACTION REQUIRED: Add the following line to .env.agents before using this server:
REM   FIRECRAWL_API_KEY=<your-key-from-firecrawl.dev>
setlocal enabledelayedexpansion

REM Locate .env.agents relative to this script (scripts\ is one level below repo root)
set "ENV_FILE=%~dp0..\.env.agents"

if not exist "%ENV_FILE%" (
    echo ERROR: .env.agents not found at %ENV_FILE%
    exit /b 1
)

REM Extract FIRECRAWL_API_KEY
for /f "usebackq tokens=1,* delims==" %%a in ("%ENV_FILE%") do (
    if "%%a"=="FIRECRAWL_API_KEY" set "FIRECRAWL_API_KEY=%%b"
)

if not defined FIRECRAWL_API_KEY (
    echo ERROR: FIRECRAWL_API_KEY not found in .env.agents
    echo Add: FIRECRAWL_API_KEY=^<your-key-from-firecrawl.dev^>
    exit /b 1
)

npx -y firecrawl-mcp
