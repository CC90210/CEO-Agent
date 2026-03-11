@echo off
REM Stripe MCP Wrapper — reads credentials from .env.agents
REM This script is safe to commit to Git (no hardcoded keys)

set "ENV_FILE=%~dp0..\.env.agents"

REM Parse .env.agents for Stripe restricted key
for /f "usebackq tokens=1,* delims==" %%A in ("%ENV_FILE%") do (
    if "%%A"=="STRIPE_RESTRICTED_KEY" set "STRIPE_KEY=%%B"
)

npx -y @stripe/mcp@latest --api-key=%STRIPE_KEY%
