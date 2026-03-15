# BUSINESS EMPIRE AGENT — Setup Guide
## CC's Claude Code via Anti-Gravity IDE

---

## HOW THIS WORKS (30 seconds)

You're using Claude Code through Anti-Gravity's chat interface. That means:
- You type messages to the agent like a chat (not terminal commands)
- The agent can run terminal commands FOR you when needed
- You only touch the terminal for initial one-time setup stuff

**What makes Claude Code different from regular Claude:** It can see your files, run code, push to GitHub, query databases, and actually DO things on your machine — not just talk about them.

---

## WHAT YOU NEED TO DO (One-Time Setup)

### Step 1: Get Your API Keys Ready

You need these keys. Open each site, grab the key, save them somewhere safe:

| Key | Where to Get It | What It's For |
|-----|----------------|---------------|
| **Anthropic API Key** | console.anthropic.com → API Keys | Powers Claude Code itself |
| **GitHub Personal Access Token** | github.com → Settings → Developer Settings → Personal Access Tokens → Fine-grained | Push/pull code, manage repos |
| **Supabase Access Token** | supabase.com → Account → Access Tokens | Query/manage your databases |
| **n8n API Key** | Your n8n instance → Settings → API | Trigger/manage workflows |
| **OpenAI API Key** | platform.openai.com → API Keys | For workflows that use GPT |

**For the GitHub token**, when creating it:
- Select "Fine-grained personal access token"
- Give it access to your repos (oasis-ai, propflow, nostalgic-requests, etc.)
- Permissions: Contents (Read/Write), Pull Requests (Read/Write), Issues (Read/Write), Metadata (Read)

### Step 2: Set Environment Variables

Open PowerShell ONE TIME and paste these (replace with your actual keys):

```powershell
[System.Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY", "sk-ant-YOUR_KEY", "User")
[System.Environment]::SetEnvironmentVariable("GITHUB_PERSONAL_ACCESS_TOKEN", "github_pat_YOUR_TOKEN", "User")
[System.Environment]::SetEnvironmentVariable("SUPABASE_ACCESS_TOKEN", "sbp_YOUR_TOKEN", "User")
[System.Environment]::SetEnvironmentVariable("N8N_API_KEY", "YOUR_N8N_KEY", "User")
[System.Environment]::SetEnvironmentVariable("N8N_BASE_URL", "https://your-n8n-instance.com", "User")
[System.Environment]::SetEnvironmentVariable("OPENAI_API_KEY", "sk-YOUR_KEY", "User")
```

Then close and reopen Anti-Gravity so it picks them up.

### Step 3: Create Your Folder Structure

Tell Claude Code in the Anti-Gravity chat:

> "Create the following folder structure on my machine. My home directory is C:\Users\User. Create these directories:
> - C:\Users\User\.claude (with a CLAUDE.md file inside)
> - C:\Users\User\Projects\oasis-ai\.claude\commands
> - C:\Users\User\Projects\propflow\.claude\commands  
> - C:\Users\User\Projects\nostalgic-requests\.claude\commands
> - C:\Users\User\Projects\content-brand\.claude\commands
> - C:\Users\User\Projects\ai-training\.claude\commands"

Or just paste this into the chat and let it run:

```
Run this: mkdir -Force "$HOME\.claude"; $projects = @("oasis-ai","propflow","nostalgic-requests","content-brand","ai-training"); foreach($p in $projects){ mkdir -Force "$HOME\Projects\$p\.claude\commands" }
```

### Step 4: Place the Brain Files

Copy the files from this package to the right locations:

| File From This Package | Copy To |
|----------------------|---------|
| `GLOBAL_CLAUDE.md` | `C:\Users\User\.claude\CLAUDE.md` |
| `GLOBAL_SETTINGS.json` | `C:\Users\User\.claude\settings.json` |
| `GLOBAL_MCP.json` | `C:\Users\User\.mcp.json` |
| `OASIS_AI_CLAUDE.md` | `C:\Users\User\Projects\oasis-ai\CLAUDE.md` |
| `commands/*.md` | Each project's `.claude\commands\` folder |

**Easiest way:** Tell Claude Code in the chat to do it:
> "Copy the CLAUDE.md file I'm about to paste into C:\Users\User\.claude\CLAUDE.md"
> Then paste the contents of GLOBAL_CLAUDE.md

### Step 5: Install MCP Servers

Tell Claude Code to run these commands one at a time:

```
Run: claude mcp add github --scope user -- npx -y @modelcontextprotocol/server-github
Run: claude mcp add sequential-thinking --scope user -- npx -y @modelcontextprotocol/server-sequential-thinking
Run: claude mcp add context7 --scope user -- npx -y @upstash/context7-mcp@latest
Run: claude mcp add memory --scope user -- npx -y @modelcontextprotocol/server-memory
Run: claude mcp add fetch --scope user -- npx -y @modelcontextprotocol/server-fetch
Run: claude mcp add n8n --scope user -- npx -y n8n-mcp-server
```

### Step 6: Verify Everything

In the Anti-Gravity chat, type:
> "/mcp"

You should see all servers listed. If any show "disconnected", tell the agent:
> "The [name] MCP server isn't connecting. Debug it."

---

## THAT'S IT FOR SETUP

Everything else is done through the chat. The GLOBAL_CLAUDE.md file IS the agent's brain — it tells Claude Code who it is, what it does, and how to work. The project-specific CLAUDE.md files give it context for each business.

From here, you just open Anti-Gravity, navigate to a project folder, and start chatting with your Business Empire Agent.

---

## QUICK TROUBLESHOOTING

| Problem | Fix |
|---------|-----|
| MCP server won't connect | Tell agent: "Debug the [name] MCP connection" |
| Agent doesn't know project context | Make sure you're in the right project folder. Tell it: "Read the CLAUDE.md in this directory" |
| Agent is being too cautious | Say: "Just do it, I'll review after" |
| Agent forgot previous work | Say: "/compact" to free up context, or "/clear" for fresh start |
| Need to switch projects | Navigate to the other project folder in Anti-Gravity's file explorer |
| Agent hallucinating | Say: "Stop. Read the actual files before continuing. Don't assume." |
