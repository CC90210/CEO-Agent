---
name: security-protocol
description: Secrets and authentication management. Ensures API keys, tokens, and credentials are NEVER exposed in plain text. Use when handling any credential, API key, or sensitive configuration.
triggers: [secret, credential, API key, exposed, rotation, security, token, password]
tier: core
dependencies: []
---

# SECRETS AND AUTHENTICATION MANAGEMENT

> **Purpose:** Ensures API keys, tokens, and database credentials are NEVER exposed in plain text files when different AI platforms interact with this workspace.

## Core Rules
1. **Never Hardcode Secrets:** No credentials of any kind are to be placed in entry points (`CLAUDE.md`, `ANTIGRAVITY.md`, `GEMINI.md`), or any script.
2. **The Source of Truth:** All agents must read tokens exclusively from the `.env.agents` file located in the root directory.
3. **MCP Configs:** When generating configuration files for new MCP servers, instruct the server initialization process to absorb the keys from the `.env.agents` or local shell environment variables rather than typing them out locally.

## `.env.agents` Setup
CC provides the actual tokens inside the `.env.agents` file. This file is tracked by `.gitignore` so it never commits to a repository. 
If an agent detects its MCP server is unauthorized (e.g., Supabase or GitHub returns a 401), it must:
1. Verify if `.env.agents` contains the value.
2. Notify CC directly if it is missing: "I am missing the SUPABASE_ACCESS_TOKEN in .env.agents. Please update it."
3. Wait for confirmation before proceeding.

## Safe Handling in Subagents
If an architect agent or writer agent spawns a subagent that requires API access to test code, it must pass the environment variables to the subagent invocation process rather than pasting the raw string into the prompt structure.
