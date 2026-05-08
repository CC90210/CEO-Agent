@echo off
REM n8n MCP Server Wrapper — reads N8N_BEARER_TOKEN from .env.agents at runtime
REM Never hardcode credentials here. All secrets live in .env.agents (gitignored).
setlocal enabledelayedexpansion

set "ENV_FILE=%~dp0..\.env.agents"

if not exist "%ENV_FILE%" (
    echo ERROR: .env.agents not found at %ENV_FILE% 1>&2
    exit /b 1
)

for /f "usebackq tokens=1,* delims==" %%a in ("%ENV_FILE%") do (
    if "%%a"=="N8N_BEARER_TOKEN" set "N8N_BEARER_TOKEN=%%b"
    if "%%a"=="N8N_MCP_URL" set "N8N_MCP_URL=%%b"
)

if not defined N8N_BEARER_TOKEN (
    echo ERROR: N8N_BEARER_TOKEN not found in .env.agents 1>&2
    exit /b 1
)

if not defined N8N_MCP_URL set "N8N_MCP_URL=https://n8n.srv993801.hstgr.cloud/mcp-server/http"

npx -y supergateway --streamableHttp %N8N_MCP_URL% --header "authorization:Bearer %N8N_BEARER_TOKEN%"
