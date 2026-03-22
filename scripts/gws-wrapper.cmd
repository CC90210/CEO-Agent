@echo off
REM GWS CLI wrapper — loads credentials from .env.agents
for /f "usebackq tokens=1,* delims==" %%A in ("%~dp0..\.env.agents") do (
    if "%%A"=="GWS_CLIENT_ID" set "GOOGLE_WORKSPACE_CLI_CLIENT_ID=%%B"
    if "%%A"=="GWS_CLIENT_SECRET" set "GOOGLE_WORKSPACE_CLI_CLIENT_SECRET=%%B"
    if "%%A"=="GWS_GCP_PROJECT" set "GOOGLE_WORKSPACE_PROJECT_ID=%%B"
)
gws %*
