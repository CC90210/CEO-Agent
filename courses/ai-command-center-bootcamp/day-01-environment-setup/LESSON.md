# Day 1: Environment Setup — Your AI Workstation

> **Level:** Builder (Level 1)
> **Duration:** ~2.5 hours
> **Prerequisites:** Day 0 completed, a computer (Windows, Mac, or Linux)
> **Goal:** By end of day, you have a fully working AI development environment.

---

## Module 1: Terminal Basics (30 min)

### What Is a Terminal?

A terminal is a text-based way to talk to your computer. Instead of clicking buttons, you type commands.

**Why use it?** AI tools like Claude Code run in the terminal. It's faster, more powerful, and how professionals work.

### Opening Your Terminal

| OS | How to Open |
|----|-------------|
| **Windows** | Search "Terminal" or "PowerShell" in Start menu |
| **Mac** | Cmd+Space → type "Terminal" → Enter |
| **Linux** | Ctrl+Alt+T |

### Essential Commands

```bash
# Where am I?
pwd                     # Print working directory (shows your current location)

# What's in this folder?
ls                      # List files and folders
ls -la                  # List ALL files (including hidden) with details

# Move around
cd Documents            # Go into the Documents folder
cd ..                   # Go up one level
cd ~                    # Go to home directory

# Create things
mkdir my-project        # Create a new folder called "my-project"
touch index.html        # Create a new empty file

# Delete things (BE CAREFUL)
rm file.txt             # Delete a file
rm -r folder-name       # Delete a folder and everything inside

# See what's in a file
cat file.txt            # Print file contents to screen
```

### Practice Exercise
```bash
# Create your first project folder
mkdir ~/ai-bootcamp
cd ~/ai-bootcamp
mkdir day-01
cd day-01
pwd                     # Should show something like /Users/you/ai-bootcamp/day-01
```

---

## Module 2: Node.js & npm (20 min)

### What Is Node.js?
Node.js lets you run JavaScript outside of a web browser. Claude Code and most AI tools are built on it.

### What Is npm?
npm (Node Package Manager) is like an app store for code packages. `npm install` downloads tools others have built.

### Install Node.js

**Go to:** https://nodejs.org
**Download:** LTS version (Long Term Support — the stable one)
**Install:** Run the installer, click Next through everything.

**Verify installation:**
```bash
node --version          # Should show v20.x.x or higher
npm --version           # Should show 10.x.x or higher
```

**If it doesn't work:**
- Close and reopen your terminal
- Windows: Make sure you checked "Add to PATH" during install
- Mac: Try `brew install node` if you have Homebrew

---

## Module 3: Git & GitHub (30 min)

### What Is Git?
Git tracks changes to your files over time. Think of it as "undo history" on steroids. Every change is saved forever and you can go back to any point.

### What Is GitHub?
GitHub is where your code lives online. Like Google Drive, but for code. Others can see it, collaborate, and contribute.

### Install Git

**Windows:** Download from https://git-scm.com/download/win
**Mac:** Run `git --version` in terminal (it'll prompt to install if needed)
**Linux:** `sudo apt install git` (Ubuntu) or `sudo dnf install git` (Fedora)

**Verify:**
```bash
git --version           # Should show git version 2.x.x
```

### Configure Git
```bash
git config --global user.name "Your Name"
git config --global user.email "your@email.com"
```

### Create GitHub Account
1. Go to https://github.com
2. Sign up (free account is fine)
3. Remember your username — you'll use it a lot

### Your First Repository
```bash
cd ~/ai-bootcamp
git init                # Initialize Git tracking in this folder
echo "# AI Bootcamp" > README.md
git add README.md       # Stage the file (prepare it for saving)
git commit -m "first commit"  # Save with a message
```

**Push to GitHub:**
1. On GitHub, click "New Repository"
2. Name it `ai-bootcamp`
3. Don't add README (we already have one)
4. Follow the "push an existing repository" instructions:
```bash
git remote add origin https://github.com/YOUR-USERNAME/ai-bootcamp.git
git branch -M main
git push -u origin main
```

---

## Module 4: Claude Code Install (20 min)

### Get Your API Key

1. Go to https://console.anthropic.com
2. Sign up / log in
3. Go to "API Keys"
4. Create a new key
5. **COPY IT AND SAVE IT SOMEWHERE SAFE** — you can't see it again

**CRITICAL:** Never paste your API key in a public place. Never commit it to GitHub. Never share it.

### Install Claude Code

```bash
npm install -g @anthropic-ai/claude-code
```

The `-g` flag means "global" — install it system-wide so you can use it from any folder.

**Verify:**
```bash
claude --version        # Should show the version number
```

### Set Your API Key

```bash
# Option 1: Set for current session
export ANTHROPIC_API_KEY="sk-ant-your-key-here"

# Option 2: Add to your shell profile (persists across sessions)
# For bash:
echo 'export ANTHROPIC_API_KEY="sk-ant-your-key-here"' >> ~/.bashrc
source ~/.bashrc

# For zsh (Mac default):
echo 'export ANTHROPIC_API_KEY="sk-ant-your-key-here"' >> ~/.zshrc
source ~/.zshrc
```

### Test It

```bash
cd ~/ai-bootcamp
claude
```

You should see Claude Code start up. Try typing:
> "What can you do?"

Claude will explain its capabilities. You're in.

---

## Module 5: First Conversation with Claude Code (20 min)

### How to Talk to Claude Code

Claude Code isn't a chatbot — it's an **agent**. It can:
- Read and write files on your computer
- Run terminal commands
- Search your codebase
- Build entire features

### Your First Build

In your Claude Code session:

```
Create a simple HTML landing page with:
- A headline that says "Welcome to AI Bootcamp"
- A subtitle: "Day 1 Complete"
- A dark theme with centered text
- Save it as index.html
```

Claude will create the file. Then:

```
Open index.html in the browser
```

You just built a webpage using AI. That's the game.

### Key Commands in Claude Code

| What You Type | What Happens |
|--------------|--------------|
| `/help` | Show available commands |
| `/clear` | Clear conversation history |
| `/compact` | Summarize conversation to save context |
| `/cost` | Show token usage and cost |
| `Ctrl+C` | Cancel current action |
| `Ctrl+D` | Exit Claude Code |

### Permission Modes

When Claude Code wants to do something (edit a file, run a command), it asks permission.

- **Default:** Asks before every action (safest)
- **Auto-accept:** Says yes to everything (fastest, use with caution)
- **Plan mode:** Plans but doesn't act until you approve

Start with default. Switch to auto-accept when you trust the task.

---

## Module 6: IDE Setup (30 min)

### VS Code (Recommended for Beginners)

1. Download from https://code.visualstudio.com
2. Install and open
3. File → Open Folder → select `~/ai-bootcamp`

**Essential Extensions:**
- **Anti-Gravity** — Claude AI native chat in your IDE
- **ESLint** — Code quality checking
- **Prettier** — Auto-format code
- **GitLens** — Enhanced Git integration

**Install extensions:** Click the Extensions icon (square grid) in the left sidebar → search → install.

### Alternative: Cursor

If you want an AI-first experience:
1. Download from https://cursor.com
2. It's VS Code but with AI built deeper into the experience
3. Good for people who want AI help while typing code

### Connecting IDE to Terminal

In VS Code, open the built-in terminal:
- **Windows/Linux:** Ctrl + `
- **Mac:** Cmd + `

Now you can use Claude Code inside VS Code. Best of both worlds.

---

## Exercise: Hello World to GitHub

**Step 1:** Open terminal in your IDE

**Step 2:** Navigate to your project
```bash
cd ~/ai-bootcamp/day-01
```

**Step 3:** Start Claude Code
```bash
claude
```

**Step 4:** Ask Claude to build
```
Create a "Hello World" webpage that includes:
- My name
- Today's date
- A list of 3 things I want to learn about AI
- Style it with CSS (dark background, light text, centered)
- Save as index.html
```

**Step 5:** Preview it (open index.html in your browser)

**Step 6:** Exit Claude Code (`Ctrl+D`)

**Step 7:** Push to GitHub
```bash
cd ~/ai-bootcamp
git add day-01/
git commit -m "day 1: first webpage built with Claude Code"
git push
```

**Step 8:** Check GitHub — your code is live online.

---

## Checklist Before Moving On

- [ ] Terminal opens and runs commands
- [ ] Node.js installed (`node --version` works)
- [ ] Git installed and configured
- [ ] GitHub account created, first repo pushed
- [ ] Claude Code installed (`claude --version` works)
- [ ] API key set and working
- [ ] First conversation with Claude Code completed
- [ ] IDE installed (VS Code or Cursor)
- [ ] Hello World page built and pushed to GitHub

**All boxes checked?** You're a Builder. Welcome to Level 1.

---

**Next:** [Day 2 — Claude Code Deep Dive](../day-02-claude-code/LESSON.md)
