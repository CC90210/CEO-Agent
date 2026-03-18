# Day 4: APIs & Scripting — JSON to Python

> **Level:** Integrator (Level 2)
> **Duration:** ~3 hours
> **Prerequisites:** Day 3 complete
> **Goal:** Understand APIs, read JSON, write Python scripts, build CLI tools.

---

## Module 1: What Is an API? (20 min)

### The Restaurant Analogy

- **You** = the app (customer)
- **The menu** = API documentation (what you can order)
- **Your order** = API request (what you're asking for)
- **The kitchen** = the server (processes your request)
- **Your food** = API response (what you get back)

### REST API Basics

Most APIs use REST (Representational State Transfer). Four operations:

| HTTP Method | What It Does | Example |
|------------|-------------|---------|
| **GET** | Read data | Get all customers |
| **POST** | Create data | Add a new customer |
| **PUT/PATCH** | Update data | Change customer email |
| **DELETE** | Delete data | Remove a customer |

### Anatomy of an API Request

```
GET https://api.weather.com/v1/current?city=Toronto
     ↑         ↑              ↑          ↑
  method    base URL       endpoint    parameters
```

### Anatomy of an API Response

```json
{
  "status": "success",
  "data": {
    "city": "Toronto",
    "temperature": 22,
    "conditions": "Sunny",
    "humidity": 45
  }
}
```

This is **JSON** — JavaScript Object Notation. The universal language of APIs.

### Authentication

Most APIs require a key to identify you:

```
GET https://api.example.com/data
Headers:
  Authorization: Bearer sk-your-api-key-here
```

**NEVER share your API keys. NEVER commit them to GitHub.**

---

## Module 2: Reading JSON (20 min)

### JSON Structure

JSON has two building blocks:

**Objects** (key-value pairs, wrapped in `{}`):
```json
{
  "name": "CC",
  "age": 22,
  "city": "Collingwood"
}
```

**Arrays** (ordered lists, wrapped in `[]`):
```json
["Monday", "Tuesday", "Wednesday"]
```

**Nested** (objects inside objects, arrays of objects):
```json
{
  "business": {
    "name": "OASIS AI Solutions",
    "services": [
      {"name": "Automation", "price": 500},
      {"name": "Chatbot", "price": 300}
    ]
  }
}
```

### Reading Nested JSON

To get the price of "Automation" from above:
```
business → services → [0] → price = 500
```

In Python:
```python
data["business"]["services"][0]["price"]  # 500
```

---

## Module 3: Python Basics (30 min)

### Why Python?

- Most readable programming language (reads like English)
- Massive ecosystem of libraries
- Best language for API work, automation, data processing
- AI/ML industry standard

### Install Python

**Check if installed:**
```bash
python3 --version       # Mac/Linux
python --version        # Windows
```

**If not installed:**
- **Windows:** Download from python.org (check "Add to PATH")
- **Mac:** `brew install python3`
- **Linux:** `sudo apt install python3 python3-pip`

### Python in 10 Minutes

```python
# Variables
name = "CC"
age = 22
is_builder = True

# Strings
greeting = f"Hello, {name}! You are {age} years old."
print(greeting)

# Lists
tools = ["Claude Code", "Supabase", "n8n"]
tools.append("Stripe")
print(tools[0])  # "Claude Code"

# Dictionaries (like JSON objects)
business = {
    "name": "OASIS AI",
    "mrr": 2191,
    "clients": 5
}
print(business["mrr"])  # 2191

# Functions
def calculate_revenue(mrr, months):
    return mrr * months

annual = calculate_revenue(2191, 12)
print(f"Annual revenue: ${annual}")  # $26,292

# Loops
for tool in tools:
    print(f"I use {tool}")

# Conditionals
if business["mrr"] > 1000:
    print("MRR goal exceeded!")
else:
    print("Keep pushing!")
```

### Virtual Environments

Keep project dependencies isolated:
```bash
# Create a virtual environment
python3 -m venv venv

# Activate it
# Mac/Linux:
source venv/bin/activate
# Windows:
venv\Scripts\activate

# Install packages inside it
pip install requests

# Deactivate when done
deactivate
```

---

## Module 4: API Calls in Python (30 min)

### The `requests` Library

```bash
pip install requests
```

### GET Request (Read Data)

```python
import requests

# Public API — no auth needed
response = requests.get("https://api.github.com/users/octocat")

# Check status
print(response.status_code)  # 200 = success

# Get JSON data
data = response.json()
print(data["name"])           # The Octocat
print(data["public_repos"])   # 8
```

### POST Request (Create Data)

```python
import requests

url = "https://api.example.com/contacts"
headers = {
    "Authorization": "Bearer your-api-key",
    "Content-Type": "application/json"
}
payload = {
    "name": "Jane Smith",
    "email": "jane@example.com"
}

response = requests.post(url, json=payload, headers=headers)
print(response.status_code)  # 201 = created
print(response.json())
```

### Error Handling

```python
import requests

try:
    response = requests.get("https://api.example.com/data", timeout=10)
    response.raise_for_status()  # Raises exception for 4xx/5xx errors
    data = response.json()
    print(data)
except requests.exceptions.Timeout:
    print("Request timed out — try again")
except requests.exceptions.HTTPError as e:
    print(f"HTTP error: {e}")
except requests.exceptions.RequestException as e:
    print(f"Something went wrong: {e}")
```

---

## Module 5: JSON to Python Scripts (30 min)

### The Pattern

1. Call an API
2. Get JSON response
3. Extract the data you need
4. Format it for human reading
5. Optionally save it somewhere

### Real Example: GitHub Profile Summary

```python
import requests
import json

def get_github_profile(username):
    """Fetch and display a GitHub user's profile."""
    url = f"https://api.github.com/users/{username}"
    response = requests.get(url)

    if response.status_code != 200:
        print(f"Error: Could not find user '{username}'")
        return

    data = response.json()

    print(f"{'='*40}")
    print(f"GitHub Profile: {data['login']}")
    print(f"{'='*40}")
    print(f"Name:    {data.get('name', 'N/A')}")
    print(f"Bio:     {data.get('bio', 'N/A')}")
    print(f"Repos:   {data['public_repos']}")
    print(f"Follow:  {data['followers']} followers, {data['following']} following")
    print(f"Created: {data['created_at'][:10]}")
    print(f"URL:     {data['html_url']}")

# Use it
get_github_profile("CC90210")
```

---

## Module 6: CLI Wrappers — The CLI-Anything Pattern (30 min)

### What Is a CLI Wrapper?

A command-line tool that wraps an API. Instead of writing API calls every time, you run a command:

```bash
python github_tool.py profile CC90210
python github_tool.py repos CC90210
python github_tool.py repos CC90210 --json
```

### The CLI-Anything Pattern

Rules:
1. **Never reimplement core logic** — always wrap the official API/SDK
2. **Always support `--json`** — machine-readable output for AI agents
3. **Never hardcode credentials** — load from environment variables
4. **Human-friendly by default, machine-friendly with flags**

### Building a CLI Tool

```python
#!/usr/bin/env python3
"""GitHub CLI Tool — wraps GitHub API for terminal use."""

import os
import sys
import json
import requests

def load_token():
    """Load GitHub token from environment."""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("Warning: GITHUB_TOKEN not set. Rate limits will apply.")
    return token

def get_profile(username, as_json=False):
    """Fetch GitHub profile."""
    token = load_token()
    headers = {"Authorization": f"token {token}"} if token else {}

    response = requests.get(
        f"https://api.github.com/users/{username}",
        headers=headers
    )

    if response.status_code != 200:
        print(f"Error: {response.status_code}")
        return

    data = response.json()

    if as_json:
        print(json.dumps(data, indent=2))
    else:
        print(f"Name:  {data.get('name', 'N/A')}")
        print(f"Repos: {data['public_repos']}")
        print(f"URL:   {data['html_url']}")

def get_repos(username, as_json=False):
    """List user's repositories."""
    token = load_token()
    headers = {"Authorization": f"token {token}"} if token else {}

    response = requests.get(
        f"https://api.github.com/users/{username}/repos?sort=updated&per_page=10",
        headers=headers
    )

    data = response.json()

    if as_json:
        print(json.dumps(data, indent=2))
    else:
        for repo in data:
            stars = repo.get("stargazers_count", 0)
            print(f"  {repo['name']:<30} ★ {stars}  {repo.get('language', 'N/A')}")

def main():
    if len(sys.argv) < 3:
        print("Usage: python github_tool.py <command> <username> [--json]")
        print("Commands: profile, repos")
        sys.exit(1)

    command = sys.argv[1]
    username = sys.argv[2]
    as_json = "--json" in sys.argv

    if command == "profile":
        get_profile(username, as_json)
    elif command == "repos":
        get_repos(username, as_json)
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)

if __name__ == "__main__":
    main()
```

**Usage:**
```bash
python github_tool.py profile CC90210
python github_tool.py repos CC90210
python github_tool.py repos CC90210 --json   # Machine-readable
```

---

## Module 7: Environment Variables & Secrets (15 min)

### The Golden Rule

**NEVER put API keys in your code. NEVER commit them to GitHub.**

### Using .env Files

Install python-dotenv:
```bash
pip install python-dotenv
```

Create `.env`:
```
GITHUB_TOKEN=ghp_your_token_here
OPENAI_API_KEY=sk-your-key-here
```

Load in Python:
```python
from dotenv import load_dotenv
import os

load_dotenv()  # Reads .env file
token = os.environ.get("GITHUB_TOKEN")
```

### .gitignore

Create `.gitignore` to prevent committing secrets:
```
.env
*.pyc
__pycache__/
venv/
node_modules/
```

**Always create .gitignore BEFORE your first commit.**

---

## Exercise: Build Your First CLI Tool

**Pick a public API from this list:**
- Weather: `https://wttr.in/CityName?format=j1`
- Quotes: `https://api.quotable.io/random`
- Dad Jokes: `https://icanhazdadjoke.com/` (header: Accept: application/json)
- News: `https://hacker-news.firebaseio.com/v0/topstories.json`

**Build a CLI tool that:**
1. Fetches data from the API
2. Displays it in human-readable format
3. Supports `--json` flag for raw output
4. Handles errors gracefully
5. Uses environment variables for any API keys

**Use Claude Code to help you build it:**
```bash
cd ~/ai-bootcamp/day-04
claude
```

Tell Claude Code what API you picked and what you want the tool to do.

**Push to GitHub:**
```bash
git add .
git commit -m "day 4: CLI tool for [API name]"
git push
```

---

## Checklist Before Moving On

- [ ] Understand REST APIs (GET, POST, PUT, DELETE)
- [ ] Can read and navigate JSON structures
- [ ] Python installed and basic syntax understood
- [ ] Can make API calls with the requests library
- [ ] Built a CLI wrapper following the CLI-Anything pattern
- [ ] Using .env for secrets and .gitignore to protect them
- [ ] Completed and pushed the exercise

**All boxes checked?** You can now turn any API into a command-line tool. That's power.

---

**Next:** [Day 5 — Database & Backend](../day-05-database-and-backend/LESSON.md)
