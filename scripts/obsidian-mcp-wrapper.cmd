@echo off
REM Obsidian MCP Server Wrapper — reads OBSIDIAN_API_KEY from .env.agents at runtime
REM Never hardcode credentials here. All secrets live in .env.agents (gitignored).
REM
REM PREREQUISITES:
REM   1. Obsidian desktop app running with "Local REST API" community plugin enabled
REM   2. Add to .env.agents:
REM        OBSIDIAN_API_KEY=<key-from-Obsidian-Settings-Local-REST-API>
REM        OBSIDIAN_BASE_URL=http://127.0.0.1:27123   (optional — this is the default)
setlocal enabledelayedexpansion

set "ENV_FILE=%~dp0..\.env.agents"

if not exist "%ENV_FILE%" (
    echo ERROR: .env.agents not found at %ENV_FILE%
    exit /b 1
)

for /f "usebackq tokens=1,* delims==" %%a in ("%ENV_FILE%") do (
    if "%%a"=="OBSIDIAN_API_KEY" set "OBSIDIAN_API_KEY=%%b"
    if "%%a"=="OBSIDIAN_BASE_URL" set "OBSIDIAN_BASE_URL=%%b"
)

if not defined OBSIDIAN_API_KEY (
    echo ERROR: OBSIDIAN_API_KEY not found in .env.agents
    echo 1. Install "Local REST API" plugin in Obsidian Settings ^> Community plugins
    echo 2. Copy the API key from Obsidian Settings ^> Local REST API
    echo 3. Add to .env.agents: OBSIDIAN_API_KEY=^<key^>
    exit /b 1
)

if not defined OBSIDIAN_BASE_URL set "OBSIDIAN_BASE_URL=http://127.0.0.1:27123"
set "OBSIDIAN_VERIFY_SSL=false"
set "OBSIDIAN_ENABLE_CACHE=true"

npx -y obsidian-mcp-server
